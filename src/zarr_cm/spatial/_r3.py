"""spatial convention, revision r3 (strict 2D, v0.1).

Snapshot of upstream at commit 54d81b7ced0376e63ee10f34db31db7d08dcc28d.
Narrows every dimension-bearing key to a fixed 2D length and requires shape
items to be positive. `spatial:dimensions` is optional here: upstream makes
it required only when `node_type` is `"array"`, and these functions see
attributes without the surrounding node, so a group carrying only
`spatial:bbox` is valid.
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
)
from zarr_cm._node import NodeContext, node_convention_data, node_type_of, prepare_node

SpatialAttrs = TypedDict(
    "SpatialAttrs",
    {
        "spatial:dimensions": NotRequired[Sequence[str]],
        "spatial:bbox": NotRequired[Sequence[float]],
        "spatial:transform_type": NotRequired[str],
        "spatial:transform": NotRequired[Sequence[float]],
        "spatial:shape": NotRequired[Sequence[int]],
        "spatial:registration": NotRequired[str],
    },
    extra_items=JSONValue,
)
"""This type models the spec defined at https://github.com/zarr-conventions/spatial/blob/54d81b7ced0376e63ee10f34db31db7d08dcc28d/README.md#properties"""

SpatialConventionAttrs = TypedDict(
    "SpatialConventionAttrs",
    {
        "zarr_conventions": Sequence[ConventionMetadataObject],
        "spatial:dimensions": NotRequired[Sequence[str]],
        "spatial:bbox": NotRequired[Sequence[float]],
        "spatial:transform_type": NotRequired[str],
        "spatial:transform": NotRequired[Sequence[float]],
        "spatial:shape": NotRequired[Sequence[int]],
        "spatial:registration": NotRequired[str],
    },
    extra_items=JSONValue,
)
"""`SpatialAttrs` plus its `zarr_conventions` registration.

See https://github.com/zarr-conventions/spatial/blob/54d81b7ced0376e63ee10f34db31db7d08dcc28d/README.md#convention-registration"""

# UUID identifies the convention *family*, not the revision; it is shared by
# every revision. Revisions are distinguished by the SCHEMA_URL below, which is what
# revision detection on read matches against.
#
# The upstream v0.1 schema ENFORCES schema_url/spec_url as `const` equal to the
# refs/tags/v0.1 URLs (no escape hatch), so we must emit those exact tag URLs to
# validate. The snapshot is still taken at commit _COMMIT; _TAG is the
# published tag at that commit.
UUID: Final = "689b58e2-cf7b-45e0-9fff-9cfc0883d6b4"
_COMMIT: Final = "54d81b7ced0376e63ee10f34db31db7d08dcc28d"
_TAG: Final = "v0.1"
SCHEMA_URL: Final = f"https://raw.githubusercontent.com/zarr-conventions/spatial/refs/tags/{_TAG}/schema.json"
SPEC_URL: Final = f"https://github.com/zarr-conventions/spatial/blob/{_TAG}/README.md"

CMO: Final[ConventionMetadataObject] = {
    "uuid": UUID,
    "schema_url": SCHEMA_URL,
    "spec_url": SPEC_URL,
    "name": "spatial",
    "description": "Spatial coordinate information",
}


ALIAS_SCHEMA_URLS: Final[frozenset[str]] = frozenset(
    {
        f"https://raw.githubusercontent.com/zarr-conventions/spatial/{_COMMIT}/schema.json",
    }
)
"""Other schema_urls this revision recognizes as its own identity.

The commit-pinned URL is what earlier `zarr-cm` releases wrote before the
`v0.1` tag URL was confirmed resolvable; documents carrying it must still read
as this revision.
"""

RECOGNIZED_SCHEMA_URLS: Final[frozenset[str]] = frozenset(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}
)
"""Every schema_url this revision reads as its own: `SCHEMA_URL` plus aliases."""

CONVENTION_KEYS: Final = {
    "spatial:dimensions",
    "spatial:bbox",
    "spatial:transform_type",
    "spatial:transform",
    "spatial:shape",
    "spatial:registration",
}

# r3: every dimension-bearing key is a fixed 2D length.
_VALID_LENGTHS: Final[dict[str, int]] = {
    "spatial:dimensions": 2,
    "spatial:bbox": 4,
    "spatial:transform": 6,
    "spatial:shape": 2,
}

_VALID_REGISTRATIONS: Final = ("node", "pixel")


def create(
    *,
    dimensions: list[str] | tuple[str, ...] | None = None,
    bbox: list[float] | tuple[float, ...] | None = None,
    transform_type: str | None = None,
    transform: list[float] | tuple[float, ...] | None = None,
    shape: list[int] | tuple[int, ...] | None = None,
    registration: str | None = None,
) -> SpatialAttrs:
    """Create a `SpatialAttrs` dict (r3, strict 2D) from keyword arguments."""
    result = SpatialAttrs()
    if dimensions is not None:
        result["spatial:dimensions"] = dimensions
    if bbox is not None:
        result["spatial:bbox"] = bbox
    if transform_type is not None:
        result["spatial:transform_type"] = transform_type
    if transform is not None:
        result["spatial:transform"] = transform
    if shape is not None:
        result["spatial:shape"] = shape
    if registration is not None:
        result["spatial:registration"] = registration
    validate(result)
    return result


def create_convention_attrs(
    *,
    dimensions: list[str] | tuple[str, ...] | None = None,
    bbox: list[float] | tuple[float, ...] | None = None,
    transform_type: str | None = None,
    transform: list[float] | tuple[float, ...] | None = None,
    shape: list[int] | tuple[int, ...] | None = None,
    registration: str | None = None,
) -> SpatialConventionAttrs:
    """Create a stand-alone attributes dict carrying spatial (r3) and nothing else.

    The result is a complete `attributes` value: the convention data from
    `create()` plus the `zarr_conventions` entry that declares it. Use
    `insert()` instead to add this convention to attributes that already
    exist -- that is what `insert` is for.
    """
    return cast(
        "SpatialConventionAttrs",
        {
            "zarr_conventions": [CMO],
            **create(
                dimensions=dimensions,
                bbox=bbox,
                transform_type=transform_type,
                transform=transform,
                shape=shape,
                registration=registration,
            ),
        },
    )


def insert(
    attrs: Mapping[str, JSONValue], data: SpatialAttrs, *, overwrite: bool = False
) -> JSONDict:
    """Insert spatial (r3) convention metadata into an attributes dict."""
    return insert_convention(
        attrs, CMO, data, overwrite=overwrite, schema_urls=RECOGNIZED_SCHEMA_URLS
    )


def extract(
    attrs: Mapping[str, JSONValue],
) -> tuple[JSONDict, SpatialAttrs]:
    """Extract spatial (r3) convention metadata from an attributes dict."""
    remaining, convention_data = extract_convention(
        attrs,
        CONVENTION_KEYS,
        lambda cmo: declares_convention(cmo, UUID, RECOGNIZED_SCHEMA_URLS),
    )
    return remaining, cast("SpatialAttrs", convention_data)


def _fixed_length_array(
    label: str, value: JSONValue, key: str
) -> list[JSONValue] | tuple[JSONValue, ...]:
    """Check *value* is an array of the length `_VALID_LENGTHS` fixes for *key*."""
    expected = _VALID_LENGTHS[key]
    if isinstance(value, (list, tuple)):
        if len(value) == expected:
            return value
        msg = f"'{label}' must have exactly {expected} items, got {len(value)}"
    else:
        # A ValueError, not a TypeError: this has always been reported as a
        # length violation, and callers match on it.
        msg = f"'{label}' must be an array with exactly {expected} items, got {type(value).__name__}"
    raise ValueError(msg)


def _validate_numbers(label: str, value: JSONValue, key: str) -> None:
    for item in _fixed_length_array(label, value, key):
        if isinstance(item, bool) or not isinstance(item, int | float):
            msg = f"'{label}' items must be numbers"
            raise TypeError(msg)


def _validate_shape(label: str, value: JSONValue) -> None:
    for item in _fixed_length_array(label, value, "spatial:shape"):
        if isinstance(item, bool) or not isinstance(item, int):
            msg = f"'{label}' items must be integers"
            raise TypeError(msg)
        if item < 1:
            msg = f"'{label}' items must be positive (>= 1)"
            raise ValueError(msg)


def validate(data: Mapping[str, JSONValue]) -> SpatialAttrs:
    """Validate spatial (r3) convention data: strict 2D, positive shape items.

    `spatial:dimensions` is not required: upstream requires it only for
    `node_type == "array"`, which is not visible from *data* alone.
    """
    if "spatial:dimensions" in data:
        dimensions = data["spatial:dimensions"]
        for item in _fixed_length_array(
            "spatial:dimensions", dimensions, "spatial:dimensions"
        ):
            if not isinstance(item, str):
                msg = "'spatial:dimensions' items must be strings"
                raise TypeError(msg)

    for key in ("spatial:bbox", "spatial:transform"):
        if key in data:
            _validate_numbers(key, data[key], key)

    if "spatial:transform_type" in data and not isinstance(
        data["spatial:transform_type"], str
    ):
        msg = "'spatial:transform_type' must be a string"
        raise TypeError(msg)

    if "spatial:shape" in data:
        _validate_shape("spatial:shape", data["spatial:shape"])

    if (
        "spatial:registration" in data
        and data["spatial:registration"] not in _VALID_REGISTRATIONS
    ):
        msg = f"'spatial:registration' must be one of {_VALID_REGISTRATIONS}, got {data['spatial:registration']!r}"
        raise ValueError(msg)
    return cast("SpatialAttrs", data)


def _validate_dimension_names(
    dimensions: Sequence[str], dimension_names: object
) -> None:
    """Check each `spatial:dimensions` entry names one of the array's dimensions.

    The spec: every entry MUST match a name in the array's top-level
    `dimension_names`, so arrays using this convention MUST declare it. The
    schema cannot express the cross-reference, so it is enforced only here.
    """
    if dimension_names is None:
        msg = "arrays carrying 'spatial:dimensions' must declare 'dimension_names'"
        raise ValueError(msg)
    if not isinstance(dimension_names, (list, tuple)):
        msg = (
            f"'dimension_names' must be an array, got {type(dimension_names).__name__}"
        )
        raise TypeError(msg)
    missing = [name for name in dimensions if name not in dimension_names]
    if missing:
        msg = f"'spatial:dimensions' entries {missing} are not in the array's 'dimension_names' {dimension_names!r}"
        raise ValueError(msg)


def _validate_multiscales_layout(attributes: Mapping[str, JSONValue]) -> None:
    """Check the per-level `spatial:shape`/`spatial:transform` in a multiscales layout.

    The schema constrains these wherever a `multiscales` key appears, declared
    or not, so this does too; the rest of the layout is multiscales' own job.
    """
    if "multiscales" not in attributes:
        return
    multiscales = attributes["multiscales"]
    if not isinstance(multiscales, Mapping):
        msg = f"'multiscales' must be an object, got {type(multiscales).__name__}"
        raise TypeError(msg)
    if "layout" not in multiscales:
        return
    layout = multiscales["layout"]
    if not isinstance(layout, (list, tuple)):
        msg = f"'multiscales.layout' must be an array, got {type(layout).__name__}"
        raise TypeError(msg)
    for i, item in enumerate(layout):
        label = f"multiscales.layout[{i}]"
        if not isinstance(item, Mapping):
            msg = f"'{label}' must be an object, got {type(item).__name__}"
            raise TypeError(msg)
        if "spatial:shape" in item:
            _validate_shape(f"{label}.spatial:shape", item["spatial:shape"])
        if "spatial:transform" in item:
            _validate_numbers(
                f"{label}.spatial:transform",
                item["spatial:transform"],
                "spatial:transform",
            )


def _validate_context(context: NodeContext) -> SpatialAttrs:
    """Validate spatial against an already prepared node."""
    data = validate(
        node_convention_data(
            context, CMO, CONVENTION_KEYS, schema_urls=RECOGNIZED_SCHEMA_URLS
        )
    )
    _validate_multiscales_layout(context.attributes)
    if context.node_type == "array":
        if "spatial:dimensions" not in data:
            msg = "'spatial:dimensions' is required on array nodes"
            raise ValueError(msg)
        _validate_dimension_names(
            data["spatial:dimensions"], context.metadata.get("dimension_names")
        )
    return data


def validate_group_metadata(
    metadata: GroupMetadataInput,
) -> GroupMetadata[SpatialConventionAttrs]:
    """Validate a v3 group metadata document against spatial (r3).

    `spatial:dimensions` is not required here: upstream marks it required only
    when `node_type` is `"array"`, so a group may carry the other spatial:
    keys -- a union footprint, say -- on their own. `spatial:shape` and
    `spatial:transform` inside `multiscales.layout` items are checked too.
    """
    context = prepare_node(metadata, expected_node_type="group")
    _validate_context(context)
    return cast("GroupMetadata[SpatialConventionAttrs]", context.metadata)


def validate_array_metadata(
    metadata: ArrayMetadataInput,
) -> ArrayMetadata[SpatialConventionAttrs]:
    """Validate a v3 array metadata document against spatial (r3).

    Arrays must carry `spatial:dimensions`; groups need not. Each of its
    entries must name one of the array's `dimension_names`, which the array
    must therefore declare.
    """
    context = prepare_node(metadata, expected_node_type="array")
    _validate_context(context)
    return cast("ArrayMetadata[SpatialConventionAttrs]", context.metadata)


def validate_node_metadata(
    metadata: NodeMetadataInput,
) -> Metadata[SpatialConventionAttrs]:
    """Validate a v3 node metadata document against spatial (r3).

    Dispatches on the document's `node_type` to
    `validate_array_metadata()` or `validate_group_metadata()`.
    """
    if node_type_of(metadata) == "array":
        return validate_array_metadata(cast("ArrayMetadataInput", metadata))
    return validate_group_metadata(cast("GroupMetadataInput", metadata))
