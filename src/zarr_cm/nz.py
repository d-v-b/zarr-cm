"""nz (NZ-1.0, "NetCDF - Zarr Convention") convention: https://github.com/zarr-conventions/nz

Single revision (Proposal maturity), so this follows the flat, unrevisioned
shape of `license.py`/`uom.py`/`stac.py`. Like `stac`, its attributes are flat
rather than nested under one wrapper key; unlike every other convention here,
they are *not* namespaced: NZ-1.0 reserves the plain netCDF-style names
`conventions` (root group) and `_FillValue` (arrays).

The snapshot is taken from upstream `main` at commit `_COMMIT`, not from the
repository's only tag, `v1-proposed`: that tag predates the convention's rename
from "NZUG-1.0" to "NZ-1.0" (and the removal of the `_nczarr_attr` attribute
type annotations), so it describes a declaration token nobody is asked to
write any more. The upstream schema pins the `zarr_conventions` entry's
`schema_url`, `spec_url` and `name` as `const`s, so `CMO` carries exactly those
values -- the same reason multiscales/proj/spatial pin their tag URLs -- even
though the `v1` tag they point at is not published yet. The commit-pinned URL,
which does resolve, is recognized as an alias.

Node-level validation enforces what a single `zarr.json` can show:

- groups must carry a `conventions` string listing `NZ-1.0`;
- arrays must carry `shape` and a fully populated `dimension_names` (non-empty
  strings, one per axis of `shape`).

The hierarchy-level rules -- the shared dimension constraint (arrays in a group
that share a dimension label share its length), which group is the root, and
dimension coordinate identification -- need more than one node's metadata, so
they are out of this module's reach.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, NotRequired, cast

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
)
from zarr_cm._node import NodeContext, node_convention_data, node_type_of, prepare_node

NzAttrs = TypedDict(
    "NzAttrs",
    {
        "conventions": NotRequired[str],
        "_FillValue": NotRequired[JSONValue],
    },
    extra_items=JSONValue,
)
"""This type models the spec defined at https://github.com/zarr-conventions/nz/blob/7c923cf7b5467c1a873ca93c9223bf08d60efc07/README.md#properties"""

NzConventionAttrs = TypedDict(
    "NzConventionAttrs",
    {
        "zarr_conventions": Sequence[ConventionMetadataObject],
        "conventions": NotRequired[str],
        "_FillValue": NotRequired[JSONValue],
    },
    extra_items=JSONValue,
)
"""`NzAttrs` plus its `zarr_conventions` registration.

See https://github.com/zarr-conventions/nz/blob/7c923cf7b5467c1a873ca93c9223bf08d60efc07/README.md#convention-registration"""


UUID: Final = "d0a980b5-c644-4dcc-85a1-283799a58f40"
IDENTIFIER: Final = "NZ-1.0"
"""The token that declares NZ-1.0 in a root group's `conventions` string."""

_COMMIT: Final = "7c923cf7b5467c1a873ca93c9223bf08d60efc07"
_TAG: Final = "v1"
SCHEMA_URL: Final = f"https://raw.githubusercontent.com/zarr-conventions/nz/refs/tags/{_TAG}/schema.json"
SPEC_URL: Final = f"https://github.com/zarr-conventions/nz/blob/{_TAG}/README.md"

CMO: Final[ConventionMetadataObject] = {
    "uuid": UUID,
    "schema_url": SCHEMA_URL,
    "spec_url": SPEC_URL,
    "name": IDENTIFIER,
    "description": "Structural interoperability layer for scientific array conventions on Zarr v3",
}


ALIAS_SCHEMA_URLS: Final[frozenset[str]] = frozenset(
    {
        f"https://raw.githubusercontent.com/zarr-conventions/nz/{_COMMIT}/schema.json",
    }
)
"""Other schema_urls this revision recognizes as its own identity.

The commit-pinned URL of the snapshot resolves today, unlike the `v1` tag URL
the schema asks writers to declare.
"""

RECOGNIZED_SCHEMA_URLS: Final[frozenset[str]] = frozenset(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}
)
"""Every schema_url this revision reads as its own: `SCHEMA_URL` plus aliases."""

CONVENTION_KEYS: Final = {"conventions", "_FillValue"}

REVISION_BY_SCHEMA_URL: Final[dict[str, str]] = dict.fromkeys(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}, _TAG
)


def detect(attrs: Mapping[str, JSONValue]) -> str | None:
    """Return the revision label this document claims for the nz convention.

    Nz has a single revision (`"v1"`); returns it when present with a
    recognized schema_url, `None` if present with an unrecognized schema_url,
    and raises `ValueError` if the convention is absent.
    """
    return resolve_revision_label(attrs, UUID, REVISION_BY_SCHEMA_URL, "nz")


def create(
    *,
    conventions: str | None = None,
    fill_value: JSONValue | None = None,
) -> NzAttrs:
    """Create an `NzAttrs` dict from keyword arguments.

    Args:
        conventions: The root group's space-separated `conventions` string,
            e.g. `"NZ-1.0 CF-1.12"`. Must list `NZ-1.0`.
        fill_value: The `_FillValue` attribute -- the *semantic* missing-data
            indicator, distinct from the array's storage-level `fill_value`.
    """
    result = NzAttrs()
    if conventions is not None:
        result["conventions"] = conventions
    if fill_value is not None:
        result["_FillValue"] = fill_value
    validate(result)
    return result


def create_convention_attrs(
    *,
    conventions: str | None = None,
    fill_value: JSONValue | None = None,
) -> NzConventionAttrs:
    """Create a stand-alone attributes dict carrying nz and nothing else.

    The result is a complete `attributes` value: the convention data from
    `create()` plus the `zarr_conventions` entry that declares it. Use
    `insert()` instead to add this convention to attributes that already
    exist -- that is what `insert` is for.
    """
    return cast(
        "NzConventionAttrs",
        {
            "zarr_conventions": [CMO],
            **create(conventions=conventions, fill_value=fill_value),
        },
    )


def insert(
    attrs: Mapping[str, JSONValue], data: NzAttrs, *, overwrite: bool = False
) -> JSONDict:
    """Insert nz convention metadata into an attributes dict.

    `conventions` is a plain attribute that other netCDF-style conventions
    (CF, ...) list themselves in too, so an existing `conventions` value
    collides like any other key: pass the combined string (e.g.
    `"NZ-1.0 CF-1.12"`) with `overwrite=True` to replace it.
    """
    return insert_convention(
        attrs, CMO, data, overwrite=overwrite, schema_urls=RECOGNIZED_SCHEMA_URLS
    )


def extract(
    attrs: Mapping[str, JSONValue],
) -> tuple[JSONDict, NzAttrs]:
    """Extract nz convention metadata from an attributes dict."""
    remaining, convention_data = extract_convention(
        attrs,
        CONVENTION_KEYS,
        lambda cmo: declares_convention(cmo, UUID, RECOGNIZED_SCHEMA_URLS),
    )
    return remaining, cast("NzAttrs", convention_data)


def validate(data: Mapping[str, JSONValue]) -> NzAttrs:
    """Validate nz convention data.

    Both keys are optional at this level (`conventions` is required on
    groups; see `validate_group_metadata()`):

    - `conventions`, if present, must be a string whose space-separated
      tokens include `NZ-1.0`, matched exactly (case included, as the
      upstream schema does);
    - `_FillValue` may be any JSON value.
    """
    if "conventions" in data:
        value = data["conventions"]
        if not isinstance(value, str):
            msg = f"'conventions' must be a string, got {type(value).__name__}"
            raise TypeError(msg)
        if IDENTIFIER not in value.split():
            msg = f"'conventions' must list {IDENTIFIER!r}, got {value!r}"
            raise ValueError(msg)
    return cast("NzAttrs", data)


def _validate_array_structure(metadata: Mapping[str, object]) -> None:
    """Check `shape` and `dimension_names` of an array `zarr.json`."""
    if "shape" not in metadata:
        msg = "'shape' is required on arrays"
        raise ValueError(msg)
    raw_shape = metadata["shape"]
    if not isinstance(raw_shape, list):
        msg = f"'shape' must be a JSON array, got {type(raw_shape).__name__}"
        raise TypeError(msg)
    shape = cast("list[object]", raw_shape)
    for length in shape:
        if not isinstance(length, int) or isinstance(length, bool):
            msg = f"'shape' entries must be integers, got {type(length).__name__}"
            raise TypeError(msg)
        if length < 0:
            msg = f"'shape' entries must be non-negative, got {length}"
            raise ValueError(msg)
    if "dimension_names" not in metadata:
        msg = f"'dimension_names' is required on arrays under {IDENTIFIER}"
        raise ValueError(msg)
    raw_names = metadata["dimension_names"]
    if not isinstance(raw_names, list):
        msg = f"'dimension_names' must be a JSON array, got {type(raw_names).__name__}"
        raise TypeError(msg)
    names = cast("list[object]", raw_names)
    for name in names:
        if not isinstance(name, str):
            msg = f"'dimension_names' entries must be strings, got {type(name).__name__}"
            raise TypeError(msg)
        if not name:
            msg = "'dimension_names' entries must not be empty"
            raise ValueError(msg)
    if len(names) != len(shape):
        msg = (
            "'dimension_names' must have one entry per axis of 'shape' "
            f"({len(shape)}), got {len(names)}"
        )
        raise ValueError(msg)


def _validate_context(context: NodeContext) -> None:
    """Validate nz against an already prepared node."""
    data = node_convention_data(
        context, CMO, CONVENTION_KEYS, schema_urls=RECOGNIZED_SCHEMA_URLS
    )
    if context.node_type == "group":
        if "conventions" not in data:
            msg = f"'conventions' is required on groups under {IDENTIFIER}"
            raise ValueError(msg)
        validate(data)
        return
    # NZ-1.0 defines `conventions` for groups only, so an array's `conventions`
    # attribute (if any) is left alone, as the upstream schema leaves it.
    _validate_array_structure(context.metadata)


def validate_group_metadata(
    metadata: GroupMetadataInput,
) -> GroupMetadata[NzConventionAttrs]:
    """Validate a v3 group metadata document against the nz convention.

    Requires a `conventions` attribute listing `NZ-1.0`. The spec only
    requires it on the *root* group, but a single document cannot say whether
    it is the root, so -- as the upstream schema does -- every group declaring
    the convention must carry it.
    """
    context = prepare_node(metadata, expected_node_type="group")
    _validate_context(context)
    return cast("GroupMetadata[NzConventionAttrs]", context.metadata)


def validate_array_metadata(
    metadata: ArrayMetadataInput,
) -> ArrayMetadata[NzConventionAttrs]:
    """Validate a v3 array metadata document against the nz convention.

    Requires `shape` and a fully populated `dimension_names`: one non-empty
    string per axis of `shape`.
    """
    context = prepare_node(metadata, expected_node_type="array")
    _validate_context(context)
    return cast("ArrayMetadata[NzConventionAttrs]", context.metadata)


def validate_node_metadata(
    metadata: NodeMetadataInput,
) -> Metadata[NzConventionAttrs]:
    """Validate a v3 node metadata document against the nz convention.

    Dispatches on the document's `node_type` to
    `validate_array_metadata()` or `validate_group_metadata()`.
    """
    if node_type_of(metadata) == "array":
        return validate_array_metadata(cast("ArrayMetadataInput", metadata))
    return validate_group_metadata(cast("GroupMetadataInput", metadata))
