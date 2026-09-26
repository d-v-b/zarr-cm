"""cs convention: https://github.com/R-CF/zarr_conventions_cs

The coordinate set convention attaches axes and coordinate values to the
dimensions of a Zarr array. It uses two attribute keys, one per node type:

- `cs` (arrays): a coordinate set, whose `crs` list holds CRS objects inline or
  `ref` objects pointing at a CRS defined on a group elsewhere in the store.
- `crs` (groups): named CRS objects that arrays can reference.

Snapshot of upstream at commit 33df41a6164e5af1761b32c6686b342bfe4beb3c.
Upstream has no tags, and the `schema_url` its README tells writers to declare
points at the moving `main` branch -- of a repository named
`zarr_convention_cs`, which does not resolve (the repository is
`zarr_conventions_cs`). This module writes the URL the spec prescribes (its
schema enforces it as a `const`) and also reads the resolving URL of the same
branch as an alias. The single revision is labelled `"main"` after that
branch.

The schema `$ref`s four other conventions' definitions; this module checks
them by hand the same way:

- `ref` objects (the `ref` convention's `$defs/ref`): closed objects with a
  required string `node`, and optional string `uri` and JSON-pointer
  `attribute`.
- CRS identifiers (`id`, `geolocation.*.crs`): the proj convention's
  attributes, checked with `zarr_cm.proj.r3.validate` -- a `proj:projjson`
  value is only checked for being a JSON object, as in the proj module.
- `unit` objects: the uom convention's `uom` object, checked with
  `zarr_cm.uom.validate`.
- `geolocation`: the geolocation convention's object, `geodetic` and/or
  `planar` arrays, each with required `x`/`y` refs and an optional `crs`.

Beyond the schema, validation enforces the spec rules a single node's metadata
can show to be broken: an axis `abbreviation` is one of `X`, `Y`, `Z`, `T`
and occurs at most once per CRS and per coordinate set; a `regular` increment
is not 0; coordinate sets of one axis have distinct names; `unit` and `time`
are not both given; and on arrays, `dimension_names` is set and -- when every
CRS is inline, so all axes are known -- each dimension has an axis. Rules that
need other nodes (resolving a `ref`, the length of an external coordinate
array) are out of reach of a single document and are not checked.
"""

from __future__ import annotations

import re

# Imported at runtime, not under TYPE_CHECKING: the class-form `TypedDict`s
# below store their annotations as strings, and downstream consumers
# (pydantic's `model_rebuild()`, `typing.get_type_hints()`) evaluate them in
# this module's namespace.
from collections.abc import Mapping, Sequence
from typing import Final, Literal, NotRequired, cast

from typing_extensions import TypedDict

from zarr_cm import uom as _uom
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
from zarr_cm.proj import _r3 as _proj_r3
from zarr_cm.proj._r3 import GeoProjAttrs
from zarr_cm.uom import UomAttrs

class CsRef(TypedDict, closed=True):
    """A reference to a Zarr node, and optionally an attribute in it.

    The cs schema uses the ref convention's `ref` definition for CRS
    references and external coordinate arrays. This type models the spec
    defined at https://github.com/R-CF/zarr_convention_ref/blob/b5dfde613d8d1dbf45dd8710eedb55f0a112d7f6/README.md#ref-object"""

    node: str
    uri: NotRequired[str]
    attribute: NotRequired[str]


class CsExternal(TypedDict, extra_items=JSONValue):
    """An external array of coordinate or boundary values.

    See https://github.com/R-CF/zarr_conventions_cs/blob/33df41a6164e5af1761b32c6686b342bfe4beb3c/README.md#external"""

    ref: CsRef


class CsValues(TypedDict, extra_items=JSONValue):
    """Exactly one of `regular`, `external`, `explicit`.

    This type models the spec defined at https://github.com/R-CF/zarr_conventions_cs/blob/33df41a6164e5af1761b32c6686b342bfe4beb3c/README.md#values-object"""

    regular: NotRequired[Sequence[float]]
    external: NotRequired[CsExternal]
    explicit: NotRequired[Sequence[JSONValue]]


class CsBoundaries(TypedDict, extra_items=JSONValue):
    """Exactly one of `regular`, `external`.

    This type models the spec defined at https://github.com/R-CF/zarr_conventions_cs/blob/33df41a6164e5af1761b32c6686b342bfe4beb3c/README.md#boundaries-object"""

    regular: NotRequired[Sequence[float]]
    external: NotRequired[CsExternal]
    attributes: NotRequired[JSONDict]


class CsTime(TypedDict, extra_items=JSONValue):
    """This type models the spec defined at https://github.com/R-CF/zarr_conventions_cs/blob/33df41a6164e5af1761b32c6686b342bfe4beb3c/README.md#time-object"""

    unit: str
    epoch: str
    calendar: NotRequired[str]


class CsParametric(TypedDict, extra_items=JSONValue):
    """This type models the spec defined at https://github.com/R-CF/zarr_conventions_cs/blob/33df41a6164e5af1761b32c6686b342bfe4beb3c/README.md#parametric-object"""

    formula: str
    terms: Mapping[str, CsValues]


class CsCoordinates(TypedDict, extra_items=JSONValue):
    """This type models the spec defined at https://github.com/R-CF/zarr_conventions_cs/blob/33df41a6164e5af1761b32c6686b342bfe4beb3c/README.md#coordinates-object"""

    values: CsValues
    name: NotRequired[str]
    direction: NotRequired[str]
    unit: NotRequired[str | UomAttrs]
    time: NotRequired[CsTime]
    boundaries: NotRequired[CsBoundaries]
    parametric: NotRequired[CsParametric]
    attributes: NotRequired[JSONDict]


class CsAxis(TypedDict, extra_items=JSONValue):
    """This type models the spec defined at https://github.com/R-CF/zarr_conventions_cs/blob/33df41a6164e5af1761b32c6686b342bfe4beb3c/README.md#axis-object"""

    abbreviation: NotRequired[Literal["X", "Y", "Z", "T"]]
    coordinates: NotRequired[Sequence[CsCoordinates]]
    attributes: NotRequired[JSONDict]


class CsGeolocationArrays(TypedDict, closed=True):
    """Geolocation arrays: references to the `x` and `y` arrays, and their CRS.

    This type models the spec defined at https://github.com/R-CF/zarr_convention_geolocation/blob/21f6f42bd4d8d61694e1fefae2119fb531499b44/README.md#arrays-object"""

    x: CsRef
    y: CsRef
    crs: NotRequired[GeoProjAttrs]


class CsGeolocation(TypedDict, closed=True):
    """At least one of `geodetic`, `planar`.

    This type models the spec defined at https://github.com/R-CF/zarr_convention_geolocation/blob/21f6f42bd4d8d61694e1fefae2119fb531499b44/README.md#geolocation-object"""

    geodetic: NotRequired[CsGeolocationArrays]
    planar: NotRequired[CsGeolocationArrays]


CrsType = Literal["compound", "planar", "vertical", "temporal", "undefined"]
"""The CRS types the spec defines."""


class CsCrs(TypedDict, extra_items=JSONValue):
    """This type models the spec defined at https://github.com/R-CF/zarr_conventions_cs/blob/33df41a6164e5af1761b32c6686b342bfe4beb3c/README.md#crs-object"""

    type: CrsType
    axes: Mapping[str, CsAxis]
    name: NotRequired[str]
    description: NotRequired[str]
    id: NotRequired[GeoProjAttrs]
    geolocation: NotRequired[CsGeolocation]


class CsCoordinateSet(TypedDict, extra_items=JSONValue):
    """The array-level `cs` object: CRS objects inline, or references to them.

    This type models the spec defined at https://github.com/R-CF/zarr_conventions_cs/blob/33df41a6164e5af1761b32c6686b342bfe4beb3c/README.md#array-properties"""

    crs: Sequence[CsCrs | CsRef]
    name: NotRequired[str]
    id: NotRequired[GeoProjAttrs]
    attributes: NotRequired[JSONDict]


class CsAttrs(TypedDict, extra_items=JSONValue):
    """`cs` (array property) and/or `crs` (group property); at least one.

    This type models the spec defined at https://github.com/R-CF/zarr_conventions_cs/blob/33df41a6164e5af1761b32c6686b342bfe4beb3c/README.md#group-properties"""

    cs: NotRequired[CsCoordinateSet]
    crs: NotRequired[Mapping[str, CsCrs]]


class CsConventionAttrs(TypedDict, extra_items=JSONValue):
    """`CsAttrs` plus its `zarr_conventions` registration.

    See https://github.com/R-CF/zarr_conventions_cs/blob/33df41a6164e5af1761b32c6686b342bfe4beb3c/README.md#convention-registration"""

    zarr_conventions: Sequence[ConventionMetadataObject]
    cs: NotRequired[CsCoordinateSet]
    crs: NotRequired[Mapping[str, CsCrs]]


UUID: Final = "e4dbf0b7-7a00-4ce6-b23e-484292014ab4"
_BRANCH: Final = "main"
SCHEMA_URL: Final = (
    f"https://raw.githubusercontent.com/R-CF/zarr_convention_cs/{_BRANCH}/schema.json"
)
SPEC_URL: Final = (
    f"https://raw.githubusercontent.com/R-CF/zarr_convention_cs/{_BRANCH}/README.md"
)

# The upstream schema's `conventionMetadata` definition fixes `schema_url`,
# `spec_url` and `description` as `const`s, so a declaration has to use exactly
# these values to validate. (The README's own registration example uses a
# different description, "Coordinate set for n-dimensional arrays", which the
# schema would reject.)
CMO: Final[ConventionMetadataObject] = {
    "uuid": UUID,
    "schema_url": SCHEMA_URL,
    "spec_url": SPEC_URL,
    "name": "cs",
    "description": "Coordinate set convention for Zarr arrays",
}


ALIAS_SCHEMA_URLS: Final[frozenset[str]] = frozenset(
    {
        f"https://raw.githubusercontent.com/R-CF/zarr_conventions_cs/{_BRANCH}/schema.json",
    }
)
"""Other schema_urls this revision recognizes as its own identity.

The spec's `SCHEMA_URL` names a repository (`zarr_convention_cs`) that does not
exist; the schema actually resolves under `zarr_conventions_cs`, so a writer
who declares the URL that works must still read as this revision.
"""

RECOGNIZED_SCHEMA_URLS: Final[frozenset[str]] = frozenset(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}
)
"""Every schema_url this revision reads as its own: `SCHEMA_URL` plus aliases."""

CONVENTION_KEYS: Final = {"cs", "crs"}

REVISION_BY_SCHEMA_URL: Final[dict[str, str]] = dict.fromkeys(
    {SCHEMA_URL, *ALIAS_SCHEMA_URLS}, _BRANCH
)

CRS_TYPES: Final = frozenset({"compound", "planar", "vertical", "temporal", "undefined"})
ABBREVIATIONS: Final = frozenset({"X", "Y", "Z", "T"})

_REF_KEYS: Final = frozenset({"node", "uri", "attribute"})
_JSON_POINTER: Final = re.compile(r"^(|(/([^~/]|~[01])*)*)$")
_DIMENSION_NAME: Final = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
_GEOLOCATION_KEYS: Final = frozenset({"geodetic", "planar"})
_GEOLOCATION_ARRAYS_KEYS: Final = frozenset({"x", "y", "crs"})


def detect(attrs: Mapping[str, JSONValue]) -> str | None:
    """Return the revision label this document claims for the cs convention.

    Cs has a single revision (`"main"`, after the branch its schema_url points
    at); returns it when present with a recognized schema_url, `None` if
    present with an unrecognized schema_url, and raises `ValueError` if the
    convention is absent.
    """
    return resolve_revision_label(attrs, UUID, REVISION_BY_SCHEMA_URL, "cs")


def create(
    *,
    cs: CsCoordinateSet | None = None,
    crs: Mapping[str, CsCrs] | None = None,
) -> CsAttrs:
    """Create a `CsAttrs` dict from keyword arguments.

    Pass `cs` for an array's coordinate set, `crs` for the named CRS objects a
    group shares with arrays; at least one is required.
    """
    result = CsAttrs()
    if cs is not None:
        result["cs"] = cs
    if crs is not None:
        result["crs"] = crs
    validate(result)
    return result


def create_convention_attrs(
    *,
    cs: CsCoordinateSet | None = None,
    crs: Mapping[str, CsCrs] | None = None,
) -> CsConventionAttrs:
    """Create a stand-alone attributes dict carrying cs and nothing else.

    The result is a complete `attributes` value: the convention data from
    `create()` plus the `zarr_conventions` entry that declares it. Use
    `insert()` instead to add this convention to attributes that already
    exist -- that is what `insert` is for.
    """
    return cast(
        "CsConventionAttrs",
        {"zarr_conventions": [CMO], **create(cs=cs, crs=crs)},
    )


def insert(
    attrs: Mapping[str, JSONValue], data: CsAttrs, *, overwrite: bool = False
) -> JSONDict:
    """Insert cs convention metadata into an attributes dict."""
    return insert_convention(
        attrs, CMO, data, overwrite=overwrite, schema_urls=RECOGNIZED_SCHEMA_URLS
    )


def extract(
    attrs: Mapping[str, JSONValue],
) -> tuple[JSONDict, CsAttrs]:
    """Extract cs convention metadata from an attributes dict."""
    remaining, convention_data = extract_convention(
        attrs,
        CONVENTION_KEYS,
        lambda cmo: declares_convention(cmo, UUID, RECOGNIZED_SCHEMA_URLS),
    )
    return remaining, cast("CsAttrs", convention_data)


# --- validation helpers ----------------------------------------------------------


def _type_error(path: str, expected: str, value: object) -> TypeError:
    return TypeError(f"'{path}' must be {expected}, got {type(value).__name__}")


def _object(value: JSONValue, path: str) -> Mapping[str, JSONValue]:
    if not isinstance(value, Mapping):
        raise _type_error(path, "a JSON object", value)
    return value


def _array(value: JSONValue, path: str) -> Sequence[JSONValue]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise _type_error(path, "a JSON array", value)
    return value


def _string(value: JSONValue, path: str) -> str:
    if not isinstance(value, str):
        raise _type_error(path, "a string", value)
    return value


def _number(value: JSONValue, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _type_error(path, "a number", value)
    return value


def _require(data: Mapping[str, JSONValue], key: str, path: str) -> JSONValue:
    if key not in data:
        msg = f"'{path}' is missing required key '{key}'"
        raise ValueError(msg)
    return data[key]


def _optional_strings(
    data: Mapping[str, JSONValue], keys: Sequence[str], path: str
) -> None:
    for key in keys:
        if key in data:
            _string(data[key], f"{path}.{key}")


def _optional_object(data: Mapping[str, JSONValue], key: str, path: str) -> None:
    if key in data:
        _object(data[key], f"{path}.{key}")


def _exactly_one(
    data: Mapping[str, JSONValue], keys: Sequence[str], path: str
) -> str:
    present = [key for key in keys if key in data]
    if len(present) != 1:
        msg = f"'{path}' must have exactly one of {list(keys)}, got {present}"
        raise ValueError(msg)
    return present[0]


def _validate_ref(value: JSONValue, path: str) -> None:
    ref = _object(value, path)
    extra = sorted(set(ref) - _REF_KEYS)
    if extra:
        msg = f"'{path}' is a ref and allows only {sorted(_REF_KEYS)}, got {extra}"
        raise ValueError(msg)
    _string(_require(ref, "node", path), f"{path}.node")
    _optional_strings(ref, ("uri",), path)
    if "attribute" in ref:
        pointer = _string(ref["attribute"], f"{path}.attribute")
        if not _JSON_POINTER.match(pointer):
            msg = f"'{path}.attribute' must be a JSON pointer, got {pointer!r}"
            raise ValueError(msg)


def _validate_proj(value: JSONValue, path: str) -> None:
    try:
        _proj_r3.validate(_object(value, path))
    except (TypeError, ValueError) as error:
        raise type(error)(f"'{path}': {error}") from error


def _validate_regular(value: JSONValue, path: str) -> Sequence[JSONValue]:
    regular = _array(value, path)
    if len(regular) != 2:
        msg = f"'{path}' must have exactly 2 numbers, got {len(regular)}"
        raise ValueError(msg)
    for index, item in enumerate(regular):
        _number(item, f"{path}[{index}]")
    return regular


def _validate_external(value: JSONValue, path: str) -> None:
    external = _object(value, path)
    _validate_ref(_require(external, "ref", path), f"{path}.ref")


def _validate_values(value: JSONValue, path: str) -> None:
    values = _object(value, path)
    kind = _exactly_one(values, ("regular", "external", "explicit"), path)
    if kind == "regular":
        regular = _validate_regular(values["regular"], f"{path}.regular")
        if regular[1] == 0:
            msg = f"'{path}.regular' increment must not be 0"
            raise ValueError(msg)
    elif kind == "external":
        _validate_external(values["external"], f"{path}.external")
    else:
        _array(values["explicit"], f"{path}.explicit")


def _validate_boundaries(value: JSONValue, path: str) -> None:
    boundaries = _object(value, path)
    kind = _exactly_one(boundaries, ("regular", "external"), path)
    if kind == "regular":
        _validate_regular(boundaries["regular"], f"{path}.regular")
    else:
        _validate_external(boundaries["external"], f"{path}.external")
    _optional_object(boundaries, "attributes", path)


def _validate_time(value: JSONValue, path: str) -> None:
    time = _object(value, path)
    _string(_require(time, "unit", path), f"{path}.unit")
    _string(_require(time, "epoch", path), f"{path}.epoch")
    _optional_strings(time, ("calendar",), path)


def _validate_parametric(value: JSONValue, path: str) -> None:
    parametric = _object(value, path)
    _string(_require(parametric, "formula", path), f"{path}.formula")
    terms = _object(_require(parametric, "terms", path), f"{path}.terms")
    if not terms:
        msg = f"'{path}.terms' must have at least one term"
        raise ValueError(msg)
    for name, term in terms.items():
        _validate_values(term, f"{path}.terms.{name}")


def _validate_unit(value: JSONValue, path: str) -> None:
    if isinstance(value, str):
        return
    try:
        _uom.validate(_object(value, path))
    except (TypeError, ValueError) as error:
        raise type(error)(f"'{path}': {error}") from error


def _validate_coordinates(value: JSONValue, path: str) -> None:
    coordinates = _object(value, path)
    _validate_values(_require(coordinates, "values", path), f"{path}.values")
    _optional_strings(coordinates, ("name", "direction"), path)
    if "unit" in coordinates and "time" in coordinates:
        msg = f"'{path}' must not have both 'unit' and 'time'"
        raise ValueError(msg)
    if "unit" in coordinates:
        _validate_unit(coordinates["unit"], f"{path}.unit")
    if "time" in coordinates:
        _validate_time(coordinates["time"], f"{path}.time")
    if "boundaries" in coordinates:
        _validate_boundaries(coordinates["boundaries"], f"{path}.boundaries")
    if "parametric" in coordinates:
        _validate_parametric(coordinates["parametric"], f"{path}.parametric")
    _optional_object(coordinates, "attributes", path)


def _validate_axis(value: JSONValue, path: str) -> str | None:
    """Validate an axis object; return its abbreviation, if any."""
    axis = _object(value, path)
    abbreviation = None
    if "abbreviation" in axis:
        abbreviation = _string(axis["abbreviation"], f"{path}.abbreviation")
        if abbreviation not in ABBREVIATIONS:
            msg = (
                f"'{path}.abbreviation' must be one of {sorted(ABBREVIATIONS)}, "
                f"got {abbreviation!r}"
            )
            raise ValueError(msg)
    if "coordinates" in axis:
        names: set[str] = set()
        for index, item in enumerate(
            _array(axis["coordinates"], f"{path}.coordinates")
        ):
            item_path = f"{path}.coordinates[{index}]"
            _validate_coordinates(item, item_path)
            name = _object(item, item_path).get("name")
            if isinstance(name, str):
                if name in names:
                    msg = f"'{path}.coordinates' has more than one set named {name!r}"
                    raise ValueError(msg)
                names.add(name)
    _optional_object(axis, "attributes", path)
    return abbreviation


def _validate_geolocation(value: JSONValue, path: str) -> None:
    geolocation = _object(value, path)
    extra = sorted(set(geolocation) - _GEOLOCATION_KEYS)
    if extra:
        msg = f"'{path}' allows only {sorted(_GEOLOCATION_KEYS)}, got {extra}"
        raise ValueError(msg)
    if not geolocation:
        msg = f"'{path}' must have at least one of {sorted(_GEOLOCATION_KEYS)}"
        raise ValueError(msg)
    for kind, arrays_value in geolocation.items():
        arrays_path = f"{path}.{kind}"
        arrays = _object(arrays_value, arrays_path)
        extra = sorted(set(arrays) - _GEOLOCATION_ARRAYS_KEYS)
        if extra:
            msg = f"'{arrays_path}' allows only {sorted(_GEOLOCATION_ARRAYS_KEYS)}, got {extra}"
            raise ValueError(msg)
        for key in ("x", "y"):
            _validate_ref(_require(arrays, key, arrays_path), f"{arrays_path}.{key}")
        if "crs" in arrays:
            _validate_proj(arrays["crs"], f"{arrays_path}.crs")


def _validate_crs(value: JSONValue, path: str) -> list[str]:
    """Validate a CRS object; return the abbreviations of its axes."""
    crs = _object(value, path)
    crs_type = _string(_require(crs, "type", path), f"{path}.type")
    if crs_type not in CRS_TYPES:
        msg = f"'{path}.type' must be one of {sorted(CRS_TYPES)}, got {crs_type!r}"
        raise ValueError(msg)
    axes = _object(_require(crs, "axes", path), f"{path}.axes")
    if not axes:
        msg = f"'{path}.axes' must have at least one axis"
        raise ValueError(msg)
    abbreviations: list[str] = []
    for name, axis in axes.items():
        abbreviation = _validate_axis(axis, f"{path}.axes.{name}")
        if abbreviation is not None:
            abbreviations.append(abbreviation)
    _check_unique_abbreviations(abbreviations, path)
    _optional_strings(crs, ("name", "description"), path)
    if "id" in crs:
        _validate_proj(crs["id"], f"{path}.id")
    if "geolocation" in crs:
        _validate_geolocation(crs["geolocation"], f"{path}.geolocation")
    return abbreviations


def _check_unique_abbreviations(abbreviations: Sequence[str], path: str) -> None:
    repeated = sorted({a for a in abbreviations if abbreviations.count(a) > 1})
    if repeated:
        msg = f"'{path}' uses the axis abbreviation(s) {repeated} more than once"
        raise ValueError(msg)


def _is_crs_reference(item: Mapping[str, JSONValue]) -> bool:
    """A `cs.crs` item is a reference unless it looks like a CRS object.

    The schema makes each item `oneOf` a CRS object (which requires `type` and
    `axes`) or a ref (closed to `node`/`uri`/`attribute`), so no item can be
    both; this only picks which of the two to report errors against.
    """
    return "type" not in item and "axes" not in item


def _validate_coordinate_set(value: JSONValue, path: str) -> None:
    cs = _object(value, path)
    abbreviations: list[str] = []
    for index, item in enumerate(_array(_require(cs, "crs", path), f"{path}.crs")):
        item_path = f"{path}.crs[{index}]"
        if _is_crs_reference(_object(item, item_path)):
            _validate_ref(item, item_path)
        else:
            abbreviations.extend(_validate_crs(item, item_path))
    _check_unique_abbreviations(abbreviations, f"{path}.crs")
    _optional_strings(cs, ("name",), path)
    if "id" in cs:
        _validate_proj(cs["id"], f"{path}.id")
    _optional_object(cs, "attributes", path)


def _validate_group_crs(value: JSONValue, path: str) -> None:
    crs = _object(value, path)
    if not crs:
        msg = f"'{path}' must have at least one CRS object"
        raise ValueError(msg)
    for name, item in crs.items():
        _validate_crs(item, f"{path}.{name}")


def validate(data: Mapping[str, JSONValue]) -> CsAttrs:
    """Validate cs convention data.

    At least one of `cs` (a coordinate set) and `crs` (named CRS objects) must
    be present; each present key is checked against the schema and the spec
    rules listed in the module docstring.
    """
    if "cs" not in data and "crs" not in data:
        msg = "At least one of 'cs', 'crs' must be present"
        raise ValueError(msg)
    if "cs" in data:
        _validate_coordinate_set(data["cs"], "cs")
    if "crs" in data:
        _validate_group_crs(data["crs"], "crs")
    return cast("CsAttrs", data)


def _dimension_names(metadata: Mapping[str, object]) -> list[str]:
    if "dimension_names" not in metadata:
        msg = "'dimension_names' is required on array nodes using the 'cs' convention"
        raise ValueError(msg)
    value = metadata["dimension_names"]
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise _type_error("dimension_names", "a JSON array", value)
    names: list[str] = []
    for index, item in enumerate(cast("Sequence[object]", value)):
        if not isinstance(item, str) or not _DIMENSION_NAME.match(item):
            msg = (
                f"'dimension_names[{index}]' must be a string matching "
                f"{_DIMENSION_NAME.pattern!r}, got {item!r}"
            )
            raise ValueError(msg)
        if item in names:
            msg = f"'dimension_names' must be unique, got {item!r} twice"
            raise ValueError(msg)
        names.append(item)
    return names


def _check_dimension_axes(cs: Mapping[str, JSONValue], names: Sequence[str]) -> None:
    """Every dimension needs an axis -- checkable once every CRS is inline."""
    items = [cast("Mapping[str, JSONValue]", item) for item in _array(cs["crs"], "cs.crs")]
    if any(_is_crs_reference(item) for item in items):
        return
    axes = {
        name
        for item in items
        for name in cast("Mapping[str, JSONValue]", item["axes"])
    }
    missing = [name for name in names if name not in axes]
    if missing:
        msg = f"'cs' has no axis for the dimension(s) {missing}"
        raise ValueError(msg)


def _validate_context(context: NodeContext) -> None:
    """Validate cs against an already prepared node."""
    data = node_convention_data(
        context, CMO, CONVENTION_KEYS, schema_urls=RECOGNIZED_SCHEMA_URLS
    )
    if context.node_type == "array":
        if "cs" not in data:
            msg = "'cs' is required on array nodes"
            raise ValueError(msg)
        names = _dimension_names(context.metadata)
        validate(data)
        _check_dimension_axes(_object(data["cs"], "cs"), names)
    else:
        if "crs" not in data:
            msg = "'crs' is required on group nodes"
            raise ValueError(msg)
        validate(data)


def validate_group_metadata(
    metadata: GroupMetadataInput,
) -> GroupMetadata[CsConventionAttrs]:
    """Validate a v3 group metadata document against the cs convention.

    A group must carry `crs`: the named CRS objects its arrays reference.
    """
    context = prepare_node(metadata, expected_node_type="group")
    _validate_context(context)
    return cast("GroupMetadata[CsConventionAttrs]", context.metadata)


def validate_array_metadata(
    metadata: ArrayMetadataInput,
) -> ArrayMetadata[CsConventionAttrs]:
    """Validate a v3 array metadata document against the cs convention.

    An array must carry `cs` and set `dimension_names`; when every CRS in
    `cs.crs` is inline, each dimension must have an axis.
    """
    context = prepare_node(metadata, expected_node_type="array")
    _validate_context(context)
    return cast("ArrayMetadata[CsConventionAttrs]", context.metadata)


def validate_node_metadata(
    metadata: NodeMetadataInput,
) -> Metadata[CsConventionAttrs]:
    """Validate a v3 node metadata document against the cs convention.

    Dispatches on the document's `node_type` to
    `validate_array_metadata()` or `validate_group_metadata()`.
    """
    if node_type_of(metadata) == "array":
        return validate_array_metadata(cast("ArrayMetadataInput", metadata))
    return validate_group_metadata(cast("GroupMetadataInput", metadata))
