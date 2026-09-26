"""coords convention: https://github.com/zarr-conventions/coords

Single revision (v1, Proposal maturity), snapshot of the upstream draft at
commit 79c8bdedfed9517991aa87ee216d0942a0593c25 of
https://github.com/christophenoel/zarr-coords, where the convention is
currently developed. The spec tells writers to declare the
`zarr-conventions/coords` `refs/tags/v1` URLs below (the upstream schema pins
them as `const`), so those are what this module writes -- even though, at the
time of the snapshot, that repository and tag had not been published yet.
The spec follows an "integer major + URL pin" contract: every v1.x change is
additive, so a single `v1` revision covers them all.

`coords:coordinates` maps a key to one of four coordinate descriptors,
discriminated by `type`: `"array"`, `"reference"`, `"inline"` and
`"interval"`. Descriptors are open: they may carry extra fields (CF
`standard_name`, `units`, ...), which are preserved but not interpreted.

The convention applies to groups and arrays. On an array, the spec ties the
map keys to the array's own `dimension_names`: each key must name a
dimension, except an `"array"` descriptor with `indexed_by`, whose key is a
free coordinate name and whose `indexed_by` entries must name dimensions.
`validate` sees attributes only, so it cannot check that;
`validate_array_metadata` does. On a group the keys refer to the children's
dimensions, which a single node cannot see, so they go unchecked.

Like every convention in this package, this module works on plain
attributes/metadata dicts -- it does no Zarr store I/O. In particular, an
`"array"` descriptor's `path` is carried as a string; whether a sibling array
exists there (and whether its `dimension_names` match `indexed_by`, as the
spec requires) is not checked.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, Literal, NotRequired, TypeAlias, cast

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


class CoordsArrayDescriptor(TypedDict, extra_items=JSONValue):
    """This type models the spec defined at https://github.com/zarr-conventions/coords/blob/v1/README.md#type-array--explicit-coordinate-array"""

    type: Literal["array"]
    path: str
    indexed_by: NotRequired[Sequence[str]]


class CoordsReferenceDescriptor(TypedDict, extra_items=JSONValue):
    """This type models the spec defined at https://github.com/zarr-conventions/coords/blob/v1/README.md#type-reference--delegate-to-a-sibling-convention"""

    type: Literal["reference"]
    convention: str


class CoordsInlineDescriptor(TypedDict, extra_items=JSONValue):
    """This type models the spec defined at https://github.com/zarr-conventions/coords/blob/v1/README.md#type-inline--embed-small-coordinate-vectors"""

    type: Literal["inline"]
    values: Sequence[JSONValue]


class CoordsIntervalDescriptor(TypedDict, extra_items=JSONValue):
    """This type models the spec defined at https://github.com/zarr-conventions/coords/blob/v1/README.md#type-interval--implicit-regularly-spaced-values

    Either all of `start`, `end`, `step` are numbers (`step` non-zero), or
    `start`/`end` are ISO 8601 date-time strings and `step` is an ISO 8601
    duration."""

    type: Literal["interval"]
    start: float | str
    end: float | str
    step: float | str


CoordsDescriptor: TypeAlias = (
    CoordsArrayDescriptor
    | CoordsReferenceDescriptor
    | CoordsInlineDescriptor
    | CoordsIntervalDescriptor
)
"""A coordinate descriptor: one of the four shapes, discriminated by `type`.

See https://github.com/zarr-conventions/coords/blob/v1/README.md#coordinate-descriptors"""


CoordsAttrs = TypedDict(
    "CoordsAttrs",
    {
        "coords:coordinates": Mapping[str, CoordsDescriptor],
        "coords:version": NotRequired[Literal[1]],
    },
    extra_items=JSONValue,
)
"""This type models the spec defined at https://github.com/zarr-conventions/coords/blob/v1/README.md#properties"""

CoordsConventionAttrs = TypedDict(
    "CoordsConventionAttrs",
    {
        "zarr_conventions": Sequence[ConventionMetadataObject],
        "coords:coordinates": Mapping[str, CoordsDescriptor],
        "coords:version": NotRequired[Literal[1]],
    },
    extra_items=JSONValue,
)
"""`CoordsAttrs` plus its `zarr_conventions` registration.

See https://github.com/zarr-conventions/coords/blob/v1/README.md#convention-registration"""


UUID: Final = "6ca4454a-658a-4348-a667-b39ced0e58cb"
_TAG: Final = "v1"
SCHEMA_URL: Final = f"https://raw.githubusercontent.com/zarr-conventions/coords/refs/tags/{_TAG}/schema.json"
SPEC_URL: Final = f"https://github.com/zarr-conventions/coords/blob/{_TAG}/README.md"

CMO: Final[ConventionMetadataObject] = {
    "uuid": UUID,
    "schema_url": SCHEMA_URL,
    "spec_url": SPEC_URL,
    "name": "coords",
    "description": "Domain-agnostic mapping between Zarr array index space and coordinate space.",
}


ALIAS_SCHEMA_URLS: Final[frozenset[str]] = frozenset()
"""Other schema_urls this revision recognizes: none besides `SCHEMA_URL`."""

RECOGNIZED_SCHEMA_URLS: Final[frozenset[str]] = frozenset(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}
)
"""Every schema_url this revision reads as its own: `SCHEMA_URL` plus aliases."""

CONVENTION_KEYS: Final = {"coords:coordinates", "coords:version"}

REVISION_BY_SCHEMA_URL: Final[dict[str, str]] = dict.fromkeys(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}, _TAG
)

DESCRIPTOR_TYPES: Final = ("array", "reference", "inline", "interval")
"""The `type` values a coordinate descriptor may take."""


def detect(attrs: Mapping[str, JSONValue]) -> str | None:
    """Return the revision label this document claims for the coords convention.

    Coords has a single revision (`"v1"`); returns it when present with the
    known schema_url, `None` if present with an unrecognized schema_url, and
    raises `ValueError` if the convention is absent.
    """
    return resolve_revision_label(attrs, UUID, REVISION_BY_SCHEMA_URL, "coords")


def create(
    *,
    coordinates: Mapping[str, CoordsDescriptor],
    version: Literal[1] | None = None,
) -> CoordsAttrs:
    """Create a `CoordsAttrs` dict from keyword arguments.

    *version* sets the optional `coords:version` pin; the declared
    `schema_url` already pins the major version, so it is left out by default.
    """
    result: CoordsAttrs = {"coords:coordinates": coordinates}
    if version is not None:
        result["coords:version"] = version
    validate(result)
    return result


def create_convention_attrs(
    *,
    coordinates: Mapping[str, CoordsDescriptor],
    version: Literal[1] | None = None,
) -> CoordsConventionAttrs:
    """Create a stand-alone attributes dict carrying coords and nothing else.

    The result is a complete `attributes` value: the convention data from
    `create()` plus the `zarr_conventions` entry that declares it. Use
    `insert()` instead to add this convention to attributes that already
    exist -- that is what `insert` is for.
    """
    return cast(
        "CoordsConventionAttrs",
        {
            "zarr_conventions": [CMO],
            **create(coordinates=coordinates, version=version),
        },
    )


def insert(
    attrs: Mapping[str, JSONValue], data: CoordsAttrs, *, overwrite: bool = False
) -> JSONDict:
    """Insert coords convention metadata into an attributes dict."""
    return insert_convention(
        attrs,
        CMO,
        cast("Mapping[str, JSONValue]", data),
        overwrite=overwrite,
        schema_urls=RECOGNIZED_SCHEMA_URLS,
    )


def extract(
    attrs: Mapping[str, JSONValue],
) -> tuple[JSONDict, CoordsAttrs]:
    """Extract coords convention metadata from an attributes dict."""
    remaining, convention_data = extract_convention(
        attrs,
        CONVENTION_KEYS,
        lambda cmo: declares_convention(cmo, UUID, RECOGNIZED_SCHEMA_URLS),
    )
    return remaining, cast("CoordsAttrs", convention_data)


def _is_number(value: JSONValue) -> bool:
    return not isinstance(value, bool) and isinstance(value, int | float)


def _validate_interval(key: str, descriptor: JSONDict) -> None:
    """Check the numeric-or-ISO-8601 rule for an `"interval"` descriptor."""
    fields = ("start", "end", "step")
    for field in fields:
        if field not in descriptor:
            msg = f"'coords:coordinates.{key}' of type 'interval' is missing required key {field!r}"
            raise ValueError(msg)
    values = [descriptor[field] for field in fields]
    if all(_is_number(value) for value in values):
        if descriptor["step"] == 0:
            msg = f"'coords:coordinates.{key}.step' must be non-zero"
            raise ValueError(msg)
        return
    if all(isinstance(value, str) for value in values):
        step = cast("str", descriptor["step"])
        if not step.startswith("P"):
            msg = (
                f"'coords:coordinates.{key}.step' must be an ISO 8601 duration "
                f"starting with 'P', got {step!r}"
            )
            raise ValueError(msg)
        return
    msg = (
        f"'coords:coordinates.{key}' of type 'interval' must have 'start', 'end' "
        "and 'step' all numbers, or all strings (ISO 8601 date-times and a "
        f"duration), got {[type(value).__name__ for value in values]}"
    )
    raise TypeError(msg)


def _validate_descriptor(key: str, value: JSONValue) -> None:
    """Validate one coordinate descriptor against its `type`'s shape."""
    if not isinstance(value, dict):
        msg = f"'coords:coordinates.{key}' must be a JSON object, got {type(value).__name__}"
        raise TypeError(msg)
    descriptor = validate_json_object(value)
    if "type" not in descriptor:
        msg = f"'coords:coordinates.{key}' is missing required key 'type'"
        raise ValueError(msg)
    kind = descriptor["type"]
    if kind not in DESCRIPTOR_TYPES:
        msg = f"'coords:coordinates.{key}.type' must be one of {DESCRIPTOR_TYPES}, got {kind!r}"
        raise ValueError(msg)
    if kind == "interval":
        _validate_interval(key, descriptor)
        return
    required, expected = {
        "array": ("path", str),
        "reference": ("convention", str),
        "inline": ("values", list),
    }[cast("str", kind)]
    if required not in descriptor:
        msg = f"'coords:coordinates.{key}' of type {kind!r} is missing required key {required!r}"
        raise ValueError(msg)
    if not isinstance(descriptor[required], expected):
        noun = "a string" if expected is str else "an array"
        msg = (
            f"'coords:coordinates.{key}.{required}' must be {noun}, "
            f"got {type(descriptor[required]).__name__}"
        )
        raise TypeError(msg)
    if kind == "array" and "indexed_by" in descriptor:
        indexed_by = descriptor["indexed_by"]
        if not isinstance(indexed_by, list):
            msg = f"'coords:coordinates.{key}.indexed_by' must be an array, got {type(indexed_by).__name__}"
            raise TypeError(msg)
        if not indexed_by:
            msg = f"'coords:coordinates.{key}.indexed_by' must not be empty"
            raise ValueError(msg)
        if not all(isinstance(name, str) for name in indexed_by):
            msg = f"'coords:coordinates.{key}.indexed_by' items must be strings"
            raise TypeError(msg)


def validate(data: Mapping[str, JSONValue]) -> CoordsAttrs:
    """Validate coords convention data.

    `coords:coordinates` is required and maps each key to a descriptor whose
    `type` is one of `DESCRIPTOR_TYPES`:

    - `"array"`: `path` (string) required; optional `indexed_by`, a
      non-empty array of strings.
    - `"reference"`: `convention` (string) required.
    - `"inline"`: `values` (array) required.
    - `"interval"`: `start`, `end`, `step` required; either all numbers with a
      non-zero `step`, or all strings with `step` starting with `"P"` (an
      ISO 8601 duration). The date-times are not parsed.

    `coords:version`, when present, must be the integer `1`. Descriptors may
    carry extra fields, which are not checked. Whether keys name the array's
    dimensions is a node-level rule; see `validate_array_metadata`.
    """
    if "coords:coordinates" not in data:
        msg = "'coords:coordinates' is required"
        raise ValueError(msg)
    coordinates = data["coords:coordinates"]
    if not isinstance(coordinates, dict):
        msg = f"'coords:coordinates' must be a JSON object, got {type(coordinates).__name__}"
        raise TypeError(msg)
    for key, value in validate_json_object(coordinates).items():
        _validate_descriptor(key, value)
    if "coords:version" in data:
        version = data["coords:version"]
        if isinstance(version, bool) or not isinstance(version, int):
            msg = f"'coords:version' must be an integer, got {type(version).__name__}"
            raise TypeError(msg)
        if version != 1:
            msg = f"'coords:version' must be 1, got {version}"
            raise ValueError(msg)
    return cast("CoordsAttrs", data)


def _dimension_names(metadata: Mapping[str, object]) -> frozenset[str]:
    """The string entries of an array document's `dimension_names`."""
    names = metadata.get("dimension_names")
    if names is None:
        return frozenset()
    if not isinstance(names, list | tuple):
        msg = f"'dimension_names' must be an array, got {type(names).__name__}"
        raise TypeError(msg)
    return frozenset(
        name for name in cast("Sequence[object]", names) if isinstance(name, str)
    )


def _validate_context(context: NodeContext) -> None:
    """Validate coords against an already prepared node."""
    data = validate(
        node_convention_data(
            context, CMO, CONVENTION_KEYS, schema_urls=RECOGNIZED_SCHEMA_URLS
        )
    )
    if context.node_type == "group":
        return
    dimensions = _dimension_names(context.metadata)
    for key, descriptor in data["coords:coordinates"].items():
        indexed_by = cast("Mapping[str, JSONValue]", descriptor).get("indexed_by")
        if descriptor["type"] == "array" and isinstance(indexed_by, list):
            for name in indexed_by:
                if name not in dimensions:
                    msg = (
                        f"'coords:coordinates.{key}.indexed_by' names {name!r}, "
                        f"which is not one of the array's dimension_names {sorted(dimensions)}"
                    )
                    raise ValueError(msg)
        elif key not in dimensions:
            msg = (
                f"'coords:coordinates' key {key!r} is not one of the array's "
                f"dimension_names {sorted(dimensions)}; only an 'array' "
                "descriptor with 'indexed_by' may use another key"
            )
            raise ValueError(msg)


def validate_group_metadata(
    metadata: GroupMetadataInput,
) -> GroupMetadata[CoordsConventionAttrs]:
    """Validate a v3 group metadata document against the coords convention.

    On a group, `coords:coordinates` is a catalogue shared by child arrays,
    so its keys (the children's dimension names) are not checked.
    """
    context = prepare_node(metadata, expected_node_type="group")
    _validate_context(context)
    return cast("GroupMetadata[CoordsConventionAttrs]", context.metadata)


def validate_array_metadata(
    metadata: ArrayMetadataInput,
) -> ArrayMetadata[CoordsConventionAttrs]:
    """Validate a v3 array metadata document against the coords convention.

    On top of `validate`, every `coords:coordinates` key must be one of the
    array's `dimension_names` -- except for an `"array"` descriptor with
    `indexed_by`, whose `indexed_by` entries must be instead. An array with
    no `dimension_names` therefore admits only an empty map.
    """
    context = prepare_node(metadata, expected_node_type="array")
    _validate_context(context)
    return cast("ArrayMetadata[CoordsConventionAttrs]", context.metadata)


def validate_node_metadata(
    metadata: NodeMetadataInput,
) -> Metadata[CoordsConventionAttrs]:
    """Validate a v3 node metadata document against the coords convention.

    Dispatches on the document's `node_type` to
    `validate_array_metadata()` or `validate_group_metadata()`.
    """
    if node_type_of(metadata) == "array":
        return validate_array_metadata(cast("ArrayMetadataInput", metadata))
    return validate_group_metadata(cast("GroupMetadataInput", metadata))
