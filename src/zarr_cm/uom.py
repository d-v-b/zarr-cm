"""uom convention: https://github.com/clbarnes/zarr-convention-uom"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final, NotRequired, cast

from typing_extensions import TypedDict

from zarr_cm._core import (
    ArrayMetadata,
    ArrayMetadataInput,
    ConventionMetadataObject,
    GroupMetadata,
    GroupMetadataInput,
    JSONDict,
    JSONValue,
    Metadata,
    NodeMetadataInput,
    declares_convention,
    extract_convention,
    insert_convention,
    resolve_revision_label,
    validate_json_object,
)
from zarr_cm._node import NodeContext, node_convention_data, node_type_of, prepare_node

if TYPE_CHECKING:
    from collections.abc import Mapping


class UCUM(TypedDict, extra_items=JSONValue):
    """Unified Code for Units of Measurement information."""

    unit: NotRequired[str]
    version: NotRequired[str]


class UomAttrs(TypedDict, extra_items=JSONValue):
    """Unit of measurement metadata for a Zarr array."""

    ucum: UCUM
    description: NotRequired[str]


class UomConventionAttrs(TypedDict, extra_items=JSONValue):
    """Attributes dict containing uom convention metadata."""

    zarr_conventions: Sequence[ConventionMetadataObject]
    uom: UomAttrs


UUID: Final = "3bbe438d-df37-49fe-8e2b-739296d46dfb"
SCHEMA_URL: Final = "https://raw.githubusercontent.com/clbarnes/zarr-convention-uom/refs/tags/v1/schema.json"
SPEC_URL: Final = "https://github.com/clbarnes/zarr-convention-uom/blob/v1/README.md"

CMO: Final[ConventionMetadataObject] = {
    "uuid": UUID,
    "schema_url": SCHEMA_URL,
    "spec_url": SPEC_URL,
    "name": "uom",
    "description": "Units of measurement for Zarr arrays",
}


ALIAS_SCHEMA_URLS: Final[frozenset[str]] = frozenset()
"""Other schema_urls this revision recognizes: none besides `SCHEMA_URL`."""

RECOGNIZED_SCHEMA_URLS: Final[frozenset[str]] = frozenset(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}
)
"""Every schema_url this revision reads as its own: `SCHEMA_URL` plus aliases."""

CONVENTION_KEYS: Final = {"uom"}

REVISION_BY_SCHEMA_URL: Final[dict[str, str]] = dict.fromkeys(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}, "v1"
)


def detect(attrs: Mapping[str, JSONValue]) -> str | None:
    """Return the revision label this document claims for the uom convention.

    Uom has a single revision (`"v1"`); returns it when present with the
    known schema_url, `None` if present with an unrecognized schema_url, and
    raises `ValueError` if the convention is absent.
    """
    return resolve_revision_label(attrs, UUID, REVISION_BY_SCHEMA_URL, "uom")


def create(
    *,
    ucum: UCUM,
    description: str | None = None,
) -> UomAttrs:
    """Create a `UomAttrs` dict from keyword arguments."""
    result = UomAttrs(ucum=ucum)
    if description is not None:
        result["description"] = description
    validate(result)
    return result


def create_convention_attrs(
    *,
    ucum: UCUM,
    description: str | None = None,
) -> UomConventionAttrs:
    """Create a stand-alone attributes dict carrying uom and nothing else.

    The result is a complete `attributes` value: the convention data from
    `create()` plus the `zarr_conventions` entry that declares it. Use
    `insert()` instead to add this convention to attributes that already
    exist -- that is what `insert` is for.
    """
    return UomConventionAttrs(
        zarr_conventions=[CMO],
        uom=create(ucum=ucum, description=description),
    )


def insert(
    attrs: Mapping[str, JSONValue], data: UomAttrs, *, overwrite: bool = False
) -> JSONDict:
    """Insert uom convention metadata into an attributes dict."""
    return insert_convention(
        attrs,
        CMO,
        {"uom": data},
        overwrite=overwrite,
        schema_urls=RECOGNIZED_SCHEMA_URLS,
    )


def extract(
    attrs: Mapping[str, JSONValue],
) -> tuple[JSONDict, UomAttrs]:
    """Extract uom convention metadata from an attributes dict."""
    remaining, convention_data = extract_convention(
        attrs,
        CONVENTION_KEYS,
        lambda cmo: declares_convention(cmo, UUID, RECOGNIZED_SCHEMA_URLS),
    )
    if not convention_data:
        return remaining, UomAttrs(ucum={})
    if "uom" not in convention_data:
        msg = "Extracted convention data does not contain 'uom' key"
        raise KeyError(msg)
    value = convention_data["uom"]
    if not isinstance(value, dict):
        msg = f"'uom' must be a JSON object, got {type(value).__name__}"
        raise TypeError(msg)
    return remaining, cast("UomAttrs", value)


def validate(data: Mapping[str, JSONValue]) -> UomAttrs:
    """Validate uom convention data.

    `ucum` must be present.
    """
    if "ucum" not in data:
        msg = "'ucum' is required"
        raise ValueError(msg)
    ucum_value = data["ucum"]
    if not isinstance(ucum_value, dict):
        msg = f"'ucum' must be a JSON object, got {type(ucum_value).__name__}"
        raise TypeError(msg)
    ucum = validate_json_object(ucum_value)
    for key in ("unit", "version"):
        if key in ucum and not isinstance(ucum[key], str):
            msg = f"'ucum.{key}' must be a string, got {type(ucum[key]).__name__}"
            raise TypeError(msg)
    if "description" in data and not isinstance(data["description"], str):
        msg = (
            f"'description' must be a string, got {type(data['description']).__name__}"
        )
        raise TypeError(msg)
    return cast("UomAttrs", data)


def _validate_context(context: NodeContext) -> None:
    """Validate uom against an already prepared node."""
    data = node_convention_data(
        context, CMO, CONVENTION_KEYS, schema_urls=RECOGNIZED_SCHEMA_URLS
    )
    if "uom" not in data:
        msg = "'uom' is required"
        raise ValueError(msg)
    value = data["uom"]
    if not isinstance(value, dict):
        msg = f"'uom' must be a JSON object, got {type(value).__name__}"
        raise TypeError(msg)
    validate(validate_json_object(value))


def validate_group_metadata(
    metadata: GroupMetadataInput,
) -> GroupMetadata[UomConventionAttrs]:
    """Validate a v3 group metadata document against the uom convention."""
    context = prepare_node(metadata, expected_node_type="group")
    _validate_context(context)
    return cast("GroupMetadata[UomConventionAttrs]", context.metadata)


def validate_array_metadata(
    metadata: ArrayMetadataInput,
) -> ArrayMetadata[UomConventionAttrs]:
    """Validate a v3 array metadata document against the uom convention.

    The uom convention places no node-type-specific requirements on either
    node type, so this matches `validate_group_metadata()`.
    """
    context = prepare_node(metadata, expected_node_type="array")
    _validate_context(context)
    return cast("ArrayMetadata[UomConventionAttrs]", context.metadata)


def validate_node_metadata(
    metadata: NodeMetadataInput,
) -> Metadata[UomConventionAttrs]:
    """Validate a v3 node metadata document against the uom convention.

    Dispatches on the document's `node_type` to
    `validate_array_metadata()` or `validate_group_metadata()`.
    """
    if node_type_of(metadata) == "array":
        return validate_array_metadata(cast("ArrayMetadataInput", metadata))
    return validate_group_metadata(cast("GroupMetadataInput", metadata))
