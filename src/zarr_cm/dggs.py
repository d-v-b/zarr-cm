"""dggs convention: https://github.com/zarr-conventions/dggs

Discrete Global Grid Systems. Single revision (`v1`, Pilot maturity), so this
follows the flat, unrevisioned shape of `license.py`/`uom.py`: the convention
data is one JSON object nested under the `dggs` key, valid on both groups and
arrays.

`validate()` enforces the README's normative rules, which are stricter than
the upstream JSON schema in a few places the schema does not (yet) encode:

- `name` must be lower-cased.
- `coordinate` and `compression` must be given together or not at all.
- A `null` `refinement_level` requires a `coordinate`, and its `compression`
  must be `"none"` -- except for HEALPix `"compacted"` coordinates, which the
  HEALPix compression table pins to `zuniq` at a `null` level (the more
  specific rule wins over the general one it contradicts).
- An `ellipsoid` must be exactly one of the three shapes the README defines
  (sphere by `radius`; ellipsoid by `semi_major_axis` plus one of
  `semi_minor_axis`/`inverse_flattening`), with no mixing.
- HEALPix `"compacted"`/`"ranges"` coordinates must use the indexing scheme and
  level from the README's compression table.

Rules that relate a node to *another* node -- the array named by `coordinate`
existing, its shape matching `compression`, and the group-to-child-array
inheritance model -- cannot be checked from a single document and are left to
the caller.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Final, Literal, NotRequired, cast

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


Compression = Literal["none", "compacted", "ranges"]
"""The cell id compression methods the spec defines."""


class DggsEllipsoid(TypedDict, closed=True):
    """This type models the spec defined at https://github.com/zarr-conventions/dggs/blob/v1/README.md#ellipsoid-object

    Exactly one shape is valid: a sphere (`name`, `radius`), or an ellipsoid
    (`name`, `semi_major_axis`, and one of `semi_minor_axis` or
    `inverse_flattening`)."""

    name: str
    radius: NotRequired[float]
    semi_major_axis: NotRequired[float]
    semi_minor_axis: NotRequired[float]
    inverse_flattening: NotRequired[float]


class DggsAttrs(TypedDict, extra_items=JSONValue):
    """This type models the spec defined at https://github.com/zarr-conventions/dggs/blob/v1/README.md#dggs-object

    Additional DGGS-specific parameters are allowed as extra keys;
    `indexing_scheme` is the one the spec standardizes (required for HEALPix)."""

    name: str
    refinement_level: int | None
    spatial_dimension: str
    ellipsoid: NotRequired[DggsEllipsoid]
    coordinate: NotRequired[str]
    compression: NotRequired[Compression]
    indexing_scheme: NotRequired[str]


class DggsConventionAttrs(TypedDict, extra_items=JSONValue):
    """`DggsAttrs` plus its `zarr_conventions` registration.

    See https://github.com/zarr-conventions/dggs/blob/v1/README.md#configuration"""

    zarr_conventions: Sequence[ConventionMetadataObject]
    dggs: DggsAttrs


UUID: Final = "7b255807-140c-42ca-97f6-7a1cfecdbc38"
_TAG: Final = "v1"
SCHEMA_URL: Final = f"https://raw.githubusercontent.com/zarr-conventions/dggs/refs/tags/{_TAG}/schema.json"
SPEC_URL: Final = f"https://github.com/zarr-conventions/dggs/blob/{_TAG}/README.md"

CMO: Final[ConventionMetadataObject] = {
    "uuid": UUID,
    "schema_url": SCHEMA_URL,
    "spec_url": SPEC_URL,
    "name": "dggs",
    "description": "Discrete Global Grid Systems convention for zarr",
}


ALIAS_SCHEMA_URLS: Final[frozenset[str]] = frozenset()
"""Other schema_urls this revision recognizes: none besides `SCHEMA_URL`."""

RECOGNIZED_SCHEMA_URLS: Final[frozenset[str]] = frozenset(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}
)
"""Every schema_url this revision reads as its own: `SCHEMA_URL` plus aliases."""

CONVENTION_KEYS: Final = {"dggs"}

REVISION_BY_SCHEMA_URL: Final[dict[str, str]] = dict.fromkeys(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}, _TAG
)

DEFAULT_RADIUS: Final = 6370997.0
"""Radius (in metres) of the sphere to assume when `ellipsoid` is absent."""

COMPRESSIONS: Final[tuple[Compression, ...]] = ("none", "compacted", "ranges")

HEALPIX_MAX_LEVEL: Final = 29
"""Largest `refinement_level` of the HEALPix base and `*uniq` indexing schemes."""

_STANDARD_KEYS: Final = frozenset(
    {
        "name",
        "refinement_level",
        "spatial_dimension",
        "ellipsoid",
        "coordinate",
        "compression",
        "indexing_scheme",
    }
)
_ELLIPSOID_SHAPES: Final = (
    frozenset({"radius"}),
    frozenset({"semi_major_axis", "semi_minor_axis"}),
    frozenset({"semi_major_axis", "inverse_flattening"}),
)
_ELLIPSOID_PARAMETERS: Final = frozenset(
    {"radius", "semi_major_axis", "semi_minor_axis", "inverse_flattening"}
)
_HEALPIX_UNIQ: Final = re.compile(r"[a-z_]*uniq")
# (indexing_scheme, refinement_level) the HEALPix compression table requires.
_HEALPIX_COMPRESSION: Final[dict[str, tuple[str, int | None]]] = {
    "compacted": ("zuniq", None),
    "ranges": ("nested", HEALPIX_MAX_LEVEL),
}


def detect(attrs: Mapping[str, JSONValue]) -> str | None:
    """Return the revision label this document claims for the dggs convention.

    Dggs has a single revision (`"v1"`); returns it when present with the
    known schema_url, `None` if present with an unrecognized schema_url, and
    raises `ValueError` if the convention is absent.
    """
    return resolve_revision_label(attrs, UUID, REVISION_BY_SCHEMA_URL, "dggs")


def create(
    *,
    name: str,
    refinement_level: int | None,
    spatial_dimension: str,
    ellipsoid: DggsEllipsoid | None = None,
    coordinate: str | None = None,
    compression: Compression | None = None,
    indexing_scheme: str | None = None,
    parameters: Mapping[str, JSONValue] | None = None,
) -> DggsAttrs:
    """Create a `DggsAttrs` dict from keyword arguments.

    `refinement_level` is required but may be `None` (variable-sized cells).
    `parameters` carries any further DGGS-specific parameters; it may not
    repeat a key that has its own keyword argument.
    """
    result = DggsAttrs(
        name=name,
        refinement_level=refinement_level,
        spatial_dimension=spatial_dimension,
    )
    if ellipsoid is not None:
        result["ellipsoid"] = ellipsoid
    if coordinate is not None:
        result["coordinate"] = coordinate
    if compression is not None:
        result["compression"] = compression
    if indexing_scheme is not None:
        result["indexing_scheme"] = indexing_scheme
    if parameters is not None:
        clashes = sorted(_STANDARD_KEYS.intersection(parameters))
        if clashes:
            msg = f"'parameters' may not set standard dggs fields: {clashes}"
            raise ValueError(msg)
        cast("JSONDict", result).update(parameters)
    validate(result)
    return result


def create_convention_attrs(
    *,
    name: str,
    refinement_level: int | None,
    spatial_dimension: str,
    ellipsoid: DggsEllipsoid | None = None,
    coordinate: str | None = None,
    compression: Compression | None = None,
    indexing_scheme: str | None = None,
    parameters: Mapping[str, JSONValue] | None = None,
) -> DggsConventionAttrs:
    """Create a stand-alone attributes dict carrying dggs and nothing else.

    The result is a complete `attributes` value: the convention data from
    `create()` plus the `zarr_conventions` entry that declares it. Use
    `insert()` instead to add this convention to attributes that already
    exist -- that is what `insert` is for.
    """
    return DggsConventionAttrs(
        zarr_conventions=[CMO],
        dggs=create(
            name=name,
            refinement_level=refinement_level,
            spatial_dimension=spatial_dimension,
            ellipsoid=ellipsoid,
            coordinate=coordinate,
            compression=compression,
            indexing_scheme=indexing_scheme,
            parameters=parameters,
        ),
    )


def insert(
    attrs: Mapping[str, JSONValue], data: DggsAttrs, *, overwrite: bool = False
) -> JSONDict:
    """Insert dggs convention metadata into an attributes dict."""
    return insert_convention(
        attrs,
        CMO,
        {"dggs": data},
        overwrite=overwrite,
        schema_urls=RECOGNIZED_SCHEMA_URLS,
    )


def extract(
    attrs: Mapping[str, JSONValue],
) -> tuple[JSONDict, DggsAttrs]:
    """Extract dggs convention metadata from an attributes dict.

    Returns an empty dict as the data when the convention is absent.
    """
    remaining, convention_data = extract_convention(
        attrs,
        CONVENTION_KEYS,
        lambda cmo: declares_convention(cmo, UUID, RECOGNIZED_SCHEMA_URLS),
    )
    if not convention_data:
        return remaining, cast("DggsAttrs", {})
    if "dggs" not in convention_data:
        msg = "Extracted convention data does not contain 'dggs' key"
        raise KeyError(msg)
    value = convention_data["dggs"]
    if not isinstance(value, dict):
        msg = f"'dggs' must be a JSON object, got {type(value).__name__}"
        raise TypeError(msg)
    return remaining, cast("DggsAttrs", value)


def _is_number(value: JSONValue) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _require_str(data: Mapping[str, JSONValue], key: str, where: str = "") -> str:
    if key not in data:
        msg = f"'{where}{key}' is required"
        raise ValueError(msg)
    value = data[key]
    if not isinstance(value, str):
        msg = f"'{where}{key}' must be a string, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _validate_ellipsoid(value: JSONValue) -> None:
    """Check `ellipsoid` against the README's sphere/ellipsoid shapes."""
    if not isinstance(value, dict):
        msg = f"'ellipsoid' must be a JSON object, got {type(value).__name__}"
        raise TypeError(msg)
    unknown = sorted(set(value) - _ELLIPSOID_PARAMETERS - {"name"})
    if unknown:
        msg = f"'ellipsoid' has unknown keys: {unknown}"
        raise ValueError(msg)
    _require_str(value, "name", "ellipsoid.")
    for key in _ELLIPSOID_PARAMETERS & value.keys():
        number = value[key]
        if not _is_number(number):
            msg = f"'ellipsoid.{key}' must be a number, got {type(number).__name__}"
            raise TypeError(msg)
        if cast("float", number) < 0:
            msg = f"'ellipsoid.{key}' must be non-negative, got {number}"
            raise ValueError(msg)
    if frozenset(value.keys() - {"name"}) not in _ELLIPSOID_SHAPES:
        msg = (
            "'ellipsoid' must have exactly one of: 'radius' (sphere); "
            "'semi_major_axis' and 'semi_minor_axis'; or 'semi_major_axis' and "
            f"'inverse_flattening'. Got: {sorted(value.keys() - {'name'})}"
        )
        raise ValueError(msg)


def _validate_healpix(data: Mapping[str, JSONValue], level: int | None) -> None:
    """Check the HEALPix-specific rules: indexing scheme and level range."""
    scheme = _require_str(data, "indexing_scheme")
    in_range = level is not None and level <= HEALPIX_MAX_LEVEL
    if scheme in {"nested", "ring"} and not in_range:
        msg = (
            f"HEALPix indexing scheme {scheme!r} requires an integer "
            f"'refinement_level' between 0 and {HEALPIX_MAX_LEVEL}, got {level}"
        )
        raise ValueError(msg)
    if _HEALPIX_UNIQ.fullmatch(scheme) and level is not None and not in_range:
        msg = (
            f"HEALPix indexing scheme {scheme!r} requires 'refinement_level' to "
            f"be null or between 0 and {HEALPIX_MAX_LEVEL}, got {level}"
        )
        raise ValueError(msg)
    compression = data.get("compression")
    if isinstance(compression, str) and compression in _HEALPIX_COMPRESSION:
        want_scheme, want_level = _HEALPIX_COMPRESSION[compression]
        if (scheme, level) != (want_scheme, want_level):
            msg = (
                f"HEALPix {compression!r} coordinates require indexing scheme "
                f"{want_scheme!r} at 'refinement_level' {want_level}, "
                f"got {scheme!r} at {level}"
            )
            raise ValueError(msg)


def _validate_level(data: Mapping[str, JSONValue]) -> int | None:
    if "refinement_level" not in data:
        msg = "'refinement_level' is required"
        raise ValueError(msg)
    level = data["refinement_level"]
    if level is None:
        return None
    if not isinstance(level, int) or isinstance(level, bool):
        msg = (
            f"'refinement_level' must be an integer or null, got {type(level).__name__}"
        )
        raise TypeError(msg)
    if level < 0:
        msg = f"'refinement_level' must be non-negative, got {level}"
        raise ValueError(msg)
    return level


def _validate_coordinate(
    data: Mapping[str, JSONValue], name: str, level: int | None
) -> None:
    """Check `coordinate`/`compression` and how they relate to the level."""
    if "coordinate" in data:
        _require_str(data, "coordinate")
    compression: str | None = None
    if "compression" in data:
        compression = _require_str(data, "compression")
        if compression not in COMPRESSIONS:
            msg = f"'compression' must be one of {list(COMPRESSIONS)}, got {compression!r}"
            raise ValueError(msg)
    if ("coordinate" in data) != (compression is not None):
        msg = (
            "'compression' must be given when 'coordinate' is given, "
            "and must be absent otherwise"
        )
        raise ValueError(msg)
    if level is None:
        if compression is None:
            msg = "a null 'refinement_level' requires a 'coordinate'"
            raise ValueError(msg)
        # The HEALPix compression table pins `compacted` to a null level, which
        # the general rule below would forbid; the specific rule wins.
        healpix_compacted = name == "healpix" and compression == "compacted"
        if compression != "none" and not healpix_compacted:
            msg = (
                "a null 'refinement_level' requires 'compression' to be 'none', "
                f"got {compression!r}"
            )
            raise ValueError(msg)


def validate(data: Mapping[str, JSONValue]) -> DggsAttrs:
    """Validate dggs convention data.

    `name` (lower-cased), `refinement_level` (a non-negative integer, or
    `null`) and `spatial_dimension` are required. See the module docstring for
    the conditional rules on `ellipsoid`, `coordinate`/`compression` and
    HEALPix. Extra DGGS-specific parameters are accepted as-is.
    """
    name = _require_str(data, "name")
    if name != name.lower():
        msg = f"'name' must be lower-cased, got {name!r}"
        raise ValueError(msg)
    level = _validate_level(data)
    _require_str(data, "spatial_dimension")
    if "ellipsoid" in data:
        _validate_ellipsoid(data["ellipsoid"])
    _validate_coordinate(data, name, level)
    if name == "healpix":
        _validate_healpix(data, level)
    return cast("DggsAttrs", data)


def _validate_context(context: NodeContext) -> None:
    """Validate dggs against an already prepared node."""
    data = node_convention_data(
        context, CMO, CONVENTION_KEYS, schema_urls=RECOGNIZED_SCHEMA_URLS
    )
    if "dggs" not in data:
        msg = "'dggs' is required"
        raise ValueError(msg)
    value = data["dggs"]
    if not isinstance(value, dict):
        msg = f"'dggs' must be a JSON object, got {type(value).__name__}"
        raise TypeError(msg)
    validate(validate_json_object(value))


def validate_group_metadata(
    metadata: GroupMetadataInput,
) -> GroupMetadata[DggsConventionAttrs]:
    """Validate a v3 group metadata document against the dggs convention."""
    context = prepare_node(metadata, expected_node_type="group")
    _validate_context(context)
    return cast("GroupMetadata[DggsConventionAttrs]", context.metadata)


def validate_array_metadata(
    metadata: ArrayMetadataInput,
) -> ArrayMetadata[DggsConventionAttrs]:
    """Validate a v3 array metadata document against the dggs convention.

    The dggs convention places no node-type-specific requirements that a
    single document can show, so this matches `validate_group_metadata()`.
    """
    context = prepare_node(metadata, expected_node_type="array")
    _validate_context(context)
    return cast("ArrayMetadata[DggsConventionAttrs]", context.metadata)


def validate_node_metadata(
    metadata: NodeMetadataInput,
) -> Metadata[DggsConventionAttrs]:
    """Validate a v3 node metadata document against the dggs convention.

    Dispatches on the document's `node_type` to
    `validate_array_metadata()` or `validate_group_metadata()`.
    """
    if node_type_of(metadata) == "array":
        return validate_array_metadata(cast("ArrayMetadataInput", metadata))
    return validate_group_metadata(cast("GroupMetadataInput", metadata))
