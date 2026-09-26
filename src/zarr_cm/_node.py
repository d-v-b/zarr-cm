"""Internal orchestration for validating convention-bearing Zarr nodes."""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from types import MappingProxyType
from typing import Final, NamedTuple, cast

from ._core import (
    NODE_TYPES,
    ConventionMetadataObject,
    JSONDict,
    JSONValue,
    NodeType,
    find_declaration,
    require_attributes,
    validate_convention_metadata_objects,
    validate_json_object,
)

_NO_URLS: Final[Mapping[str, str]] = MappingProxyType({})


def node_attributes(metadata: Mapping[str, object]) -> JSONDict:
    """Normalize the `attributes` object of a Zarr v3 metadata document."""
    attributes = metadata.get("attributes", {})
    if not isinstance(attributes, Mapping):
        msg = f"'attributes' must be a JSON object, got {type(attributes).__name__}"
        raise TypeError(msg)
    return validate_json_object(cast("Mapping[object, object]", attributes))


def node_type_of(
    metadata: object,
    *,
    expected: NodeType | None = None,
) -> NodeType:
    """Validate and return a Zarr v3 document's `node_type`.

    Typed `object` because this is the first check every node-level entry
    point runs: a non-mapping document raises `TypeError` here rather than an
    `AttributeError` further in.
    """
    if not isinstance(metadata, Mapping):
        msg = (
            "a Zarr metadata document must be a JSON object, "
            f"got {type(metadata).__name__}"
        )
        raise TypeError(msg)
    metadata = cast("Mapping[str, object]", metadata)
    zarr_format = metadata.get("zarr_format")
    if zarr_format != 3:
        msg = f"conventions are defined for zarr_format 3, got {zarr_format!r}"
        raise ValueError(msg)

    node_type = metadata.get("node_type")
    if node_type not in NODE_TYPES:
        msg = f"'node_type' must be one of {sorted(NODE_TYPES)}, got {node_type!r}"
        raise ValueError(msg)

    if expected is not None and node_type != expected:
        msg = f"expected a {expected!r} metadata document, got node_type {node_type!r}"
        raise ValueError(msg)

    return "array" if node_type == "array" else "group"


class NodeContext(NamedTuple):
    """Convention-relevant node data, normalized and parsed once."""

    node_type: NodeType
    metadata: dict[str, object]
    attributes: JSONDict
    declarations: tuple[ConventionMetadataObject, ...]


def prepare_node(
    metadata: Mapping[str, object],
    *,
    expected_node_type: NodeType | None = None,
) -> NodeContext:
    """Normalize and parse the convention-bearing parts of a Zarr v3 document."""
    node_type = node_type_of(metadata, expected=expected_node_type)
    attributes = node_attributes(metadata)
    declarations = tuple(
        validate_convention_metadata_objects(attributes.get("zarr_conventions"))
    )
    normalized_metadata = dict(metadata)
    normalized_metadata["attributes"] = attributes
    return NodeContext(node_type, normalized_metadata, attributes, declarations)


def node_convention_data(
    context: NodeContext,
    cmo: ConventionMetadataObject,
    convention_keys: set[str],
    *,
    schema_urls: AbstractSet[str],
    spec_urls: AbstractSet[str] = frozenset(),
) -> JSONDict:
    """Extract a declared convention's keys from a prepared node context.

    *schema_urls* and *spec_urls* are the calling revision's input type: every
    schema_url and spec_url it recognizes as its own identity. A declared
    schema_url must be a member of *schema_urls* -- the one this revision
    writes, or any it reads. A declaration may identify the convention by
    `uuid`; lacking one, by a recognized `schema_url`; lacking both, by a
    recognized `spec_url` (see `declares_convention`).
    """
    uuid = cmo.get("uuid")
    declaration = (
        None
        if uuid is None
        else find_declaration(context.declarations, uuid, schema_urls, spec_urls)
    )
    if uuid is None or declaration is None:
        name = cmo.get("name") or uuid or "<unnamed>"
        msg = f"the {name!r} convention is not declared in this document's 'zarr_conventions'"
        raise ValueError(msg)
    declared_schema_url = declaration.get("schema_url")
    if declared_schema_url is not None and declared_schema_url not in schema_urls:
        name = cmo.get("name") or uuid
        msg = (
            f"the {name!r} convention declares schema_url "
            f"{declared_schema_url!r}, which this revision does not recognize"
        )
        raise ValueError(msg)
    return {
        key: value
        for key, value in context.attributes.items()
        if key in convention_keys
    }


def _select_revision(
    declaration: ConventionMetadataObject | None,
    *,
    revision_by_schema_url: Mapping[str, str],
    revision_by_spec_url: Mapping[str, str],
    latest: str,
    convention_name: str,
    requested: str | None,
    declaration_required: bool,
) -> str:
    """Pick a revision label for a declaration.

    *revision_by_schema_url* and *revision_by_spec_url* are the convention's
    input type: every schema_url and spec_url any revision recognizes, mapped
    to that revision's label. A declared `schema_url` decides the revision
    alone, and an unrecognized one is an error. With no `schema_url`, a
    recognized `spec_url` decides it; an unrecognized `spec_url` on a
    declaration that carries a `uuid` says nothing about the revision, so it
    is treated as if absent.
    """
    if declaration is None:
        if declaration_required:
            msg = (
                f"the {convention_name!r} convention is not declared in this "
                "document's 'zarr_conventions'"
            )
            raise ValueError(msg)
        return latest if requested is None else requested

    schema_url = declaration.get("schema_url")
    if schema_url is None:
        spec_url = declaration.get("spec_url")
        declared = None if spec_url is None else revision_by_spec_url.get(spec_url)
        if declared is None:
            return latest if requested is None else requested
        if requested is not None and declared != requested:
            msg = (
                f"the {convention_name!r} convention declares spec_url "
                f"{spec_url!r}, which does not match revision {requested!r}"
            )
            raise ValueError(msg)
        return declared
    if requested is not None:
        if revision_by_schema_url.get(schema_url) != requested:
            msg = (
                f"the {convention_name!r} convention declares schema_url "
                f"{schema_url!r}, which does not match revision {requested!r}"
            )
            raise ValueError(msg)
        return requested
    try:
        return revision_by_schema_url[schema_url]
    except KeyError:
        msg = (
            f"the {convention_name!r} convention declares an unsupported "
            f"schema_url: {schema_url!r}"
        )
        raise ValueError(msg) from None


def resolve_attributes_revision(
    attrs: Mapping[str, JSONValue],
    *,
    uuid: str,
    revision_by_schema_url: Mapping[str, str],
    revision_by_spec_url: Mapping[str, str] = _NO_URLS,
    latest: str,
    convention_name: str,
    requested: str | None = None,
) -> str:
    """Resolve a revision for convention data or a complete attributes object.

    Raises `TypeError` if *attrs* is not a mapping.
    """
    attrs = require_attributes(attrs)
    if requested is not None:
        # Attribute-level APIs deliberately allow callers to interpret or migrate
        # data under an explicitly selected revision. Full-node validation uses
        # resolve_context_revision, which checks the declaration for consistency.
        return requested
    declaration = find_declaration(
        validate_convention_metadata_objects(attrs.get("zarr_conventions")),
        uuid,
        revision_by_schema_url,
        revision_by_spec_url,
    )
    return _select_revision(
        declaration,
        revision_by_schema_url=revision_by_schema_url,
        revision_by_spec_url=revision_by_spec_url,
        latest=latest,
        convention_name=convention_name,
        requested=requested,
        declaration_required=False,
    )


def resolve_context_revision(
    context: NodeContext,
    *,
    uuid: str,
    revision_by_schema_url: Mapping[str, str],
    revision_by_spec_url: Mapping[str, str] = _NO_URLS,
    latest: str,
    convention_name: str,
    requested: str | None = None,
) -> str:
    """Resolve the declared convention revision for a prepared node."""
    declaration = find_declaration(
        context.declarations, uuid, revision_by_schema_url, revision_by_spec_url
    )
    return _select_revision(
        declaration,
        revision_by_schema_url=revision_by_schema_url,
        revision_by_spec_url=revision_by_spec_url,
        latest=latest,
        convention_name=convention_name,
        requested=requested,
        declaration_required=True,
    )
