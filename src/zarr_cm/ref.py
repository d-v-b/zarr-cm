"""ref convention: https://github.com/R-CF/zarr_convention_ref

References an external Zarr node (array or group) -- or an item in its
`zarr.json` -- from the attributes of an array or group. Applies to both node
types.

Single revision, labeled `"r1"` package-locally. Upstream publishes its
schema and spec only at `main` branch URLs, and the schema requires those
exact URLs as `const`s, so they are the `schema_url`/`spec_url` this module
writes: a declaration carrying any other URL is not valid per the convention's
own schema. The rules modeled here are a snapshot of upstream `main` at commit
b5dfde613d8d1dbf45dd8710eedb55f0a112d7f6 (vendored and tracked for drift like
every other convention). That repository's `v1` tag predates a breaking
redesign -- it referenced nodes via mutually exclusive `array`/`group` fields
rather than today's single `node` field, with a bare attribute name rather than
a JSON pointer -- and is not modeled: every known implementation follows the
`node` form.

The spec places a `ref` object "at the location in the attributes of the
referencing Zarr object where the referenced object is required", but its
schema and examples only define the top-level `ref` attribute, which is what
this module inserts, extracts and validates. `validate()` checks a bare ref
object, so it also serves for `ref` objects nested inside other data.

Like every convention in this package, this module works on plain
attributes/metadata dicts -- it does no Zarr store I/O and never resolves a
reference.
"""

from __future__ import annotations

import re
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


_COMMIT: Final = "b5dfde613d8d1dbf45dd8710eedb55f0a112d7f6"


class RefAttrs(TypedDict, closed=True):
    """This type models the spec defined at https://github.com/R-CF/zarr_convention_ref/blob/b5dfde613d8d1dbf45dd8710eedb55f0a112d7f6/README.md#ref-object

    Closed: the schema sets `additionalProperties: false` on the ref object.
    """

    node: str
    uri: NotRequired[str]
    attribute: NotRequired[str]


class RefConventionAttrs(TypedDict, extra_items=JSONValue):
    """`RefAttrs` plus its `zarr_conventions` registration.

    See https://github.com/R-CF/zarr_convention_ref/blob/b5dfde613d8d1dbf45dd8710eedb55f0a112d7f6/README.md#convention-registration"""

    zarr_conventions: Sequence[ConventionMetadataObject]
    ref: RefAttrs


UUID: Final = "d89b30cf-ed8c-43d5-9a16-b492f0cd8786"
SCHEMA_URL: Final = (
    "https://raw.githubusercontent.com/R-CF/zarr_convention_ref/main/schema.json"
)
SPEC_URL: Final = (
    "https://raw.githubusercontent.com/R-CF/zarr_convention_ref/main/README.md"
)

CMO: Final[ConventionMetadataObject] = {
    "uuid": UUID,
    "schema_url": SCHEMA_URL,
    "spec_url": SPEC_URL,
    "name": "ref",
    # The schema pins `description` to this `const`; the README's registration
    # example uses different wording, which the schema would reject.
    "description": "External Reference Convention",
}


ALIAS_SCHEMA_URLS: Final[frozenset[str]] = frozenset()
"""Other schema_urls this revision recognizes: none besides `SCHEMA_URL`."""

RECOGNIZED_SCHEMA_URLS: Final[frozenset[str]] = frozenset(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}
)
"""Every schema_url this revision reads as its own: `SCHEMA_URL` plus aliases."""

CONVENTION_KEYS: Final = {"ref"}

REVISION_BY_SCHEMA_URL: Final[dict[str, str]] = dict.fromkeys(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}, "r1"
)

_FIELDS: Final = frozenset({"node", "uri", "attribute"})

# RFC 6901 JSON pointer, exactly as the upstream schema spells it.
_JSON_POINTER: Final = re.compile(r"^(|(/([^~/]|~[01])*)*)$")


def detect(attrs: Mapping[str, JSONValue]) -> str | None:
    """Return the revision label this document claims for the ref convention.

    Ref has a single revision (`"r1"`); returns it when present with the
    known schema_url, `None` if present with an unrecognized schema_url, and
    raises `ValueError` if the convention is absent.
    """
    return resolve_revision_label(attrs, UUID, REVISION_BY_SCHEMA_URL, "ref")


def create(
    *,
    node: str,
    uri: str | None = None,
    attribute: str | None = None,
) -> RefAttrs:
    """Create a `RefAttrs` dict from keyword arguments."""
    result = RefAttrs(node=node)
    if uri is not None:
        result["uri"] = uri
    if attribute is not None:
        result["attribute"] = attribute
    validate(result)
    return result


def create_convention_attrs(
    *,
    node: str,
    uri: str | None = None,
    attribute: str | None = None,
) -> RefConventionAttrs:
    """Create a stand-alone attributes dict carrying ref and nothing else.

    The result is a complete `attributes` value: the convention data from
    `create()` plus the `zarr_conventions` entry that declares it. Use
    `insert()` instead to add this convention to attributes that already
    exist -- that is what `insert` is for.
    """
    return RefConventionAttrs(
        zarr_conventions=[CMO],
        ref=create(node=node, uri=uri, attribute=attribute),
    )


def insert(
    attrs: Mapping[str, JSONValue], data: RefAttrs, *, overwrite: bool = False
) -> JSONDict:
    """Insert ref convention metadata into an attributes dict."""
    return insert_convention(
        attrs,
        CMO,
        {"ref": cast("JSONDict", data)},
        overwrite=overwrite,
        schema_urls=RECOGNIZED_SCHEMA_URLS,
    )


def extract(
    attrs: Mapping[str, JSONValue],
) -> tuple[JSONDict, RefAttrs]:
    """Extract ref convention metadata from an attributes dict.

    Returns an empty dict as the convention data when the convention is not
    declared.
    """
    remaining, convention_data = extract_convention(
        attrs,
        CONVENTION_KEYS,
        lambda cmo: declares_convention(cmo, UUID, RECOGNIZED_SCHEMA_URLS),
    )
    if not convention_data:
        return remaining, cast("RefAttrs", {})
    if "ref" not in convention_data:
        msg = "Extracted convention data does not contain 'ref' key"
        raise KeyError(msg)
    value = convention_data["ref"]
    if not isinstance(value, dict):
        msg = f"'ref' must be a JSON object, got {type(value).__name__}"
        raise TypeError(msg)
    return remaining, cast("RefAttrs", value)


def validate(data: Mapping[str, JSONValue]) -> RefAttrs:
    """Validate a ref object.

    - `node` is required and must be a string.
    - `uri` and `attribute`, when present, must be strings.
    - `attribute` must be an RFC 6901 JSON pointer (`""` or `/`-prefixed
      segments, with `~` only as `~0`/`~1`), as the schema's `pattern` requires.
    - No other fields are allowed (the schema's `additionalProperties: false`).
      The superseded `array`/`group` fields of the upstream `v1` tag are
      rejected with a pointer to `node`.
    - Beyond the schema, the README fixes `node`'s form by `uri`: with a `uri`
      the path is absolute from the external store's root and starts with
      `"/"`; without one it is relative to the referencing node (e.g.
      `"../sibling"`) and so must not start with `"/"`.

    `uri` is only checked for being a string, not for RFC 3986 conformance.
    """
    legacy = sorted({"array", "group"} & data.keys())
    if legacy:
        msg = (
            f"unknown ref field(s) {legacy}: the 'array'/'group' fields of the "
            "upstream v1 tag were replaced by a single 'node' path"
        )
        raise ValueError(msg)
    unknown = sorted(data.keys() - _FIELDS)
    if unknown:
        msg = f"unknown ref field(s) {unknown}; allowed: {sorted(_FIELDS)}"
        raise ValueError(msg)
    if "node" not in data:
        msg = "'node' is required"
        raise ValueError(msg)
    node = data["node"]
    if not isinstance(node, str):
        msg = f"'node' must be a string, got {type(node).__name__}"
        raise TypeError(msg)
    for key in ("uri", "attribute"):
        if key in data and not isinstance(data[key], str):
            msg = f"'{key}' must be a string, got {type(data[key]).__name__}"
            raise TypeError(msg)
    attribute = data.get("attribute")
    if isinstance(attribute, str) and not _JSON_POINTER.match(attribute):
        msg = (
            f"'attribute' must be a JSON pointer (RFC 6901) such as "
            f"'/attributes/name', got {attribute!r}"
        )
        raise ValueError(msg)
    if "uri" in data and not node.startswith("/"):
        msg = (
            "'node' must be an absolute path starting with '/' when 'uri' is "
            f"given, got {node!r}"
        )
        raise ValueError(msg)
    if "uri" not in data and node.startswith("/"):
        msg = (
            "'node' must be a path relative to the referencing node when 'uri' "
            f"is absent, got {node!r}"
        )
        raise ValueError(msg)
    return cast("RefAttrs", data)


def _validate_context(context: NodeContext) -> None:
    """Validate ref against an already prepared node."""
    data = node_convention_data(
        context, CMO, CONVENTION_KEYS, schema_urls=RECOGNIZED_SCHEMA_URLS
    )
    if "ref" not in data:
        msg = "'ref' is required"
        raise ValueError(msg)
    value = data["ref"]
    if not isinstance(value, dict):
        msg = f"'ref' must be a JSON object, got {type(value).__name__}"
        raise TypeError(msg)
    validate(validate_json_object(value))


def validate_group_metadata(
    metadata: GroupMetadataInput,
) -> GroupMetadata[RefConventionAttrs]:
    """Validate a v3 group metadata document against the ref convention."""
    context = prepare_node(metadata, expected_node_type="group")
    _validate_context(context)
    return cast("GroupMetadata[RefConventionAttrs]", context.metadata)


def validate_array_metadata(
    metadata: ArrayMetadataInput,
) -> ArrayMetadata[RefConventionAttrs]:
    """Validate a v3 array metadata document against the ref convention."""
    context = prepare_node(metadata, expected_node_type="array")
    _validate_context(context)
    return cast("ArrayMetadata[RefConventionAttrs]", context.metadata)


def validate_node_metadata(
    metadata: NodeMetadataInput,
) -> Metadata[RefConventionAttrs]:
    """Validate a v3 node metadata document against the ref convention.

    Dispatches on the document's `node_type` to
    `validate_array_metadata()` or `validate_group_metadata()`.
    """
    if node_type_of(metadata) == "array":
        return validate_array_metadata(cast("ArrayMetadataInput", metadata))
    return validate_group_metadata(cast("GroupMetadataInput", metadata))
