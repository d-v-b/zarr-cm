"""Sources of valid convention metadata, one per revision of each convention.

Each `Revision` bundles a revision module with a Hypothesis strategy for the
keyword arguments its `create()` accepts, so a property test can say "for any
valid data of any revision, invariant X holds" and have that mean something.
The strategies are written against the upstream JSON schemas vendored under
`tests/schemas/`, and `test_properties.py` checks the generated data against
those schemas -- so a generator that drifted from the spec would fail there,
not silently narrow the tests.

Values are kept JSON-native (lists, not tuples; finite floats) so that the
same data can round-trip through `json.dumps`/`json.loads` unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from hypothesis import strategies as st

import zarr_cm
from zarr_cm import cs, multiscales, proj, spatial, stac, uom
from zarr_cm import license as license_

if TYPE_CHECKING:
    from types import ModuleType
    from uuid import UUID

SCHEMAS = Path(__file__).parent / "schemas"

Kwargs = dict[str, Any]

# --- primitive helpers -------------------------------------------------------

text = st.text(min_size=1, max_size=20)
finite_floats = st.floats(allow_nan=False, allow_infinity=False, width=32)
numbers: st.SearchStrategy[float] = st.one_of(finite_floats, st.integers(-1000, 1000))

json_values: st.SearchStrategy[Any] = st.recursive(
    st.none() | st.booleans() | st.integers() | finite_floats | st.text(max_size=10),
    lambda inner: st.lists(inner, max_size=3)
    | st.dictionaries(st.text(max_size=8), inner, max_size=3),
    max_leaves=6,
)


def optional(strategy: st.SearchStrategy[Any]) -> st.SearchStrategy[Any]:
    """`None` (meaning: leave the keyword out) or a drawn value."""
    return st.none() | strategy


def drop_none(kwargs: Kwargs) -> Kwargs:
    return {k: v for k, v in kwargs.items() if v is not None}


# --- proj --------------------------------------------------------------------

_PROJJSON = st.dictionaries(text, st.text(max_size=10) | st.integers(), max_size=3)


def _proj_kwargs(
    code: st.SearchStrategy[str], *, exactly_one: bool
) -> st.SearchStrategy[Kwargs]:
    """Choose which of code / wkt2 / projjson to set; r2 wants exactly one."""
    fields = ("code", "wkt2", "projjson")
    values = {"code": code, "wkt2": text, "projjson": _PROJJSON}
    if exactly_one:
        chosen = st.sampled_from(fields).map(lambda f: (f,))
    else:
        chosen = st.sets(st.sampled_from(fields), min_size=1).map(tuple)
    return chosen.flatmap(
        lambda names: st.fixed_dictionaries({name: values[name] for name in names})
    )


PROJ_R2_KWARGS = _proj_kwargs(
    st.from_regex(r"[A-Z]+:[0-9]+", fullmatch=True), exactly_one=True
)
PROJ_R3_KWARGS = _proj_kwargs(
    st.from_regex(r"[^:\n]+:[^:\n]+", fullmatch=True), exactly_one=False
)

# --- spatial -----------------------------------------------------------------

SPATIAL_KWARGS: st.SearchStrategy[Kwargs] = st.fixed_dictionaries(
    {
        "dimensions": optional(st.lists(text, min_size=2, max_size=2)),
        "bbox": optional(st.lists(numbers, min_size=4, max_size=4)),
        "transform_type": optional(text),
        "transform": optional(st.lists(numbers, min_size=6, max_size=6)),
        "shape": optional(st.lists(st.integers(1, 10_000), min_size=2, max_size=2)),
        "registration": optional(st.sampled_from(["node", "pixel"])),
    }
).map(drop_none)

# --- multiscales -------------------------------------------------------------

_PATH_SEGMENT = st.from_regex(r"[A-Za-z0-9_-]+", fullmatch=True)
_PATH = st.lists(_PATH_SEGMENT, min_size=1, max_size=3).map("/".join)
_TRANSFORM = st.fixed_dictionaries(
    {},
    optional={
        "scale": st.lists(numbers, min_size=1, max_size=3),
        "translation": st.lists(numbers, min_size=1, max_size=3),
    },
)


@st.composite
def _layout_object(draw: st.DrawFn) -> dict[str, Any]:
    entry: dict[str, Any] = {"asset": draw(_PATH)}
    if draw(st.booleans()):
        entry["derived_from"] = draw(_PATH)
        entry["transform"] = draw(_TRANSFORM)  # required alongside derived_from
    elif draw(st.booleans()):
        entry["transform"] = draw(_TRANSFORM)
    if draw(st.booleans()):
        entry["resampling_method"] = draw(text)
    return entry


MULTISCALES_KWARGS: st.SearchStrategy[Kwargs] = st.fixed_dictionaries(
    {
        "layout": st.lists(_layout_object(), min_size=1, max_size=4),
        "resampling_method": optional(text),
    }
).map(drop_none)

# --- license / uom -----------------------------------------------------------

LICENSE_KWARGS: st.SearchStrategy[Kwargs] = st.sets(
    st.sampled_from(["spdx", "url", "text", "file", "path"]), min_size=1
).flatmap(lambda names: st.fixed_dictionaries(dict.fromkeys(names, text)))

UOM_KWARGS: st.SearchStrategy[Kwargs] = st.fixed_dictionaries(
    {
        "ucum": st.fixed_dictionaries({}, optional={"unit": text, "version": text}),
        "description": optional(text),
    }
).map(drop_none)

# --- stac ----------------------------------------------------------------

# stac:item / stac:collection may be any JSON object: test_properties.py stubs
# their upstream $ref targets (schemas.stacspec.org) to accept anything.
_STAC_OBJECT = st.dictionaries(text, json_values, max_size=3)
_STAC_LINK = st.fixed_dictionaries({"href": text}, optional={"rel": text, "type": text})

STAC_KWARGS: st.SearchStrategy[Kwargs] = st.sampled_from(
    ["item", "collection", "key", "link"]
).flatmap(
    lambda field: st.fixed_dictionaries(
        {
            field: {
                "item": _STAC_OBJECT,
                "collection": _STAC_OBJECT,
                "key": text,
                "link": _STAC_LINK,
            }[field]
        }
    )
)

# --- cs ----------------------------------------------------------------------

_POINTER = st.lists(st.from_regex(r"[A-Za-z0-9_]*", fullmatch=True), max_size=3).map(
    lambda segments: "".join(f"/{s}" for s in segments)
)
_CS_REF = st.fixed_dictionaries(
    {"node": text}, optional={"uri": text, "attribute": _POINTER}
)
_CS_EXTERNAL = st.fixed_dictionaries({"ref": _CS_REF})
_CS_REGULAR = st.tuples(numbers, numbers.filter(lambda x: x != 0)).map(list)
_CS_VALUES = st.one_of(
    st.fixed_dictionaries({"regular": _CS_REGULAR}),
    st.fixed_dictionaries({"external": _CS_EXTERNAL}),
    st.fixed_dictionaries({"explicit": st.lists(json_values, max_size=3)}),
)
_CS_BOUNDARIES = st.one_of(
    st.fixed_dictionaries({"regular": st.lists(numbers, min_size=2, max_size=2)}),
    st.fixed_dictionaries({"external": _CS_EXTERNAL}),
)
_CS_TIME = st.fixed_dictionaries(
    {"unit": text, "epoch": text}, optional={"calendar": text}
)
_CS_UNIT = text | st.fixed_dictionaries(
    {"ucum": st.fixed_dictionaries({}, optional={"unit": text, "version": text})},
    optional={"description": text},
)
_CS_PARAMETRIC = st.fixed_dictionaries(
    {
        "formula": text,
        "terms": st.dictionaries(text, _CS_VALUES, min_size=1, max_size=2),
    }
)
_CS_PROJ = st.fixed_dictionaries({"proj:code": st.just("EPSG:4326")})
_CS_GEOLOCATION_ARRAYS = st.fixed_dictionaries(
    {"x": _CS_REF, "y": _CS_REF}, optional={"crs": _CS_PROJ}
)
_CS_GEOLOCATION = st.fixed_dictionaries(
    {}, optional={"geodetic": _CS_GEOLOCATION_ARRAYS}
).flatmap(
    lambda g: st.just(g)
    if g
    else st.fixed_dictionaries({"planar": _CS_GEOLOCATION_ARRAYS})
)


@st.composite
def _cs_coordinates(draw: st.DrawFn, name: str | None) -> dict[str, Any]:
    coordinates: dict[str, Any] = {"values": draw(_CS_VALUES)}
    if name is not None:
        coordinates["name"] = name
    kind = draw(st.sampled_from(["unit", "time", None]))
    if kind == "unit":
        coordinates["unit"] = draw(_CS_UNIT)
    elif kind == "time":
        coordinates["time"] = draw(_CS_TIME)
    optional_fields = {
        "direction": text,
        "boundaries": _CS_BOUNDARIES,
        "parametric": _CS_PARAMETRIC,
        "attributes": st.dictionaries(text, json_values, max_size=2),
    }
    for key, strategy in optional_fields.items():
        if draw(st.booleans()):
            coordinates[key] = draw(strategy)
    return coordinates


@st.composite
def _cs_axis(draw: st.DrawFn, abbreviation: str | None) -> dict[str, Any]:
    axis: dict[str, Any] = {}
    if abbreviation is not None:
        axis["abbreviation"] = abbreviation
    if draw(st.booleans()):  # absent coordinates: an ordinal axis
        # coordinate sets of one axis must have distinct names, if named
        axis["coordinates"] = [
            draw(_cs_coordinates(draw(st.sampled_from([f"set{i}", None]))))
            for i in range(draw(st.integers(1, 2)))
        ]
    return axis


@st.composite
def _cs_crs(draw: st.DrawFn, abbreviations: list[str]) -> dict[str, Any]:
    """A CRS object; its axes take (and consume) *abbreviations* as they go."""
    names = draw(st.lists(text, min_size=1, max_size=3, unique=True))
    axes = {}
    for name in names:
        abbreviation = (
            abbreviations.pop() if abbreviations and draw(st.booleans()) else None
        )
        axes[name] = draw(_cs_axis(abbreviation))
    crs: dict[str, Any] = {
        "type": draw(
            st.sampled_from(["compound", "planar", "vertical", "temporal", "undefined"])
        ),
        "axes": axes,
    }
    optional_fields = {
        "name": text,
        "description": text,
        "id": _CS_PROJ,
        "geolocation": _CS_GEOLOCATION,
    }
    for key, strategy in optional_fields.items():
        if draw(st.booleans()):
            crs[key] = draw(strategy)
    return crs


def _abbreviations() -> st.SearchStrategy[list[str]]:
    return st.permutations(["X", "Y", "Z", "T"]).map(list)


@st.composite
def _cs_coordinate_set(draw: st.DrawFn) -> dict[str, Any]:
    # abbreviations are unique across the inline CRSs of one coordinate set
    abbreviations = draw(_abbreviations())
    items = [
        draw(_CS_REF) if draw(st.booleans()) else draw(_cs_crs(abbreviations))
        for _ in range(draw(st.integers(0, 3)))
    ]
    cs: dict[str, Any] = {"crs": items}
    optional_fields = {
        "name": text,
        "id": _CS_PROJ,
        "attributes": st.dictionaries(text, json_values, max_size=2),
    }
    for key, strategy in optional_fields.items():
        if draw(st.booleans()):
            cs[key] = draw(strategy)
    return cs


@st.composite
def _cs_group_crs(draw: st.DrawFn) -> dict[str, Any]:
    # ...but each of a group's named CRSs stands alone
    names = draw(st.lists(text, min_size=1, max_size=2, unique=True))
    return {name: draw(_cs_crs(draw(_abbreviations()))) for name in names}


# Generated for a group: arrays additionally need `dimension_names` with an axis
# for each, which a bare attributes dict cannot supply. A group's `cs` is
# ignored by the schema and checked like any other by `validate`.
CS_KWARGS: st.SearchStrategy[Kwargs] = st.fixed_dictionaries(
    {"crs": _cs_group_crs(), "cs": optional(_cs_coordinate_set())}
).map(drop_none)

# The cs schema `$ref`s definitions of four other conventions by URL. proj's and
# uom's are the schemas vendored for those conventions; ref's and geolocation's
# are copied here, since zarr-cm does not model those conventions.
_CS_REF_SCHEMA: dict[str, Any] = {
    "$defs": {
        "ref": {
            "type": "object",
            "properties": {
                "uri": {"type": "string"},
                "node": {"type": "string"},
                "attribute": {
                    "type": "string",
                    "pattern": "^(|(/([^~/]|~[01])*)*)$",
                },
            },
            "required": ["node"],
            "additionalProperties": False,
        }
    }
}
_CS_GEOLOCATION_SCHEMA: dict[str, Any] = {
    "$defs": {
        "geolocation": {
            "type": "object",
            "properties": {
                "geodetic": {"$ref": "#/$defs/arrays"},
                "planar": {"$ref": "#/$defs/arrays"},
            },
            "anyOf": [{"required": ["geodetic"]}, {"required": ["planar"]}],
            "additionalProperties": False,
        },
        "arrays": {
            "type": "object",
            "properties": {
                "x": {
                    "$ref": "https://raw.githubusercontent.com/R-CF/zarr_convention_ref/main/schema.json#/$defs/ref"
                },
                "y": {
                    "$ref": "https://raw.githubusercontent.com/R-CF/zarr_convention_ref/main/schema.json#/$defs/ref"
                },
                "crs": {
                    "$ref": "https://raw.githubusercontent.com/zarr-conventions/geo-proj/main/schema.json#/$defs/projAttributes"
                },
            },
            "required": ["x", "y"],
            "additionalProperties": False,
        },
    }
}


def cs_external_schemas() -> list[tuple[str, dict[str, Any]]]:
    """The documents the cs schema `$ref`s, by the URL it refers to them by."""
    return [
        (
            "https://raw.githubusercontent.com/R-CF/zarr_convention_ref/main/schema.json",
            _CS_REF_SCHEMA,
        ),
        (
            "https://raw.githubusercontent.com/R-CF/zarr_convention_geolocation/main/schema.json",
            _CS_GEOLOCATION_SCHEMA,
        ),
        (
            "https://raw.githubusercontent.com/zarr-conventions/geo-proj/main/schema.json",
            _schema("proj-r3.json"),
        ),
        (
            "https://raw.githubusercontent.com/clbarnes/zarr-convention-uom/refs/tags/v1/schema.json",
            _schema("uom.json"),
        ),
    ]


# --- the registry ------------------------------------------------------------


class Revision(NamedTuple):
    """One revision of one convention, with a source of valid `create()` input."""

    convention: zarr_cm.CanonicalConventionName
    label: str | None
    """Revision label, or `None` for conventions that have no revisions."""
    module: ModuleType
    """The revision module: `proj.r2`, `spatial.r3`, `license`, ..."""
    package: ModuleType
    """The dispatching package: `proj`, `spatial`, `license`, ..."""
    schema: dict[str, Any]
    """The upstream JSON schema this revision snapshots."""
    node_type: str
    """A node type the convention's data is valid on without extra keys."""
    kwargs: st.SearchStrategy[Kwargs]
    """Keyword arguments for `module.create()` that always yield valid data."""

    def __repr__(self) -> str:  # keeps Hypothesis' failure output readable
        return f"Revision({self.convention}, {self.label})"


def _schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMAS / name).read_text())


REVISIONS: tuple[Revision, ...] = (
    Revision(
        "proj", "r2", proj.r2, proj, _schema("proj-r2.json"), "group", PROJ_R2_KWARGS
    ),
    Revision(
        "proj", "r3", proj.r3, proj, _schema("proj-r3.json"), "group", PROJ_R3_KWARGS
    ),
    # spatial: arrays additionally require spatial:dimensions, so groups are the
    # node type on which *any* generated data is valid.
    Revision(
        "spatial",
        "r2",
        spatial.r2,
        spatial,
        _schema("spatial-r2.json"),
        "group",
        SPATIAL_KWARGS,
    ),
    Revision(
        "spatial",
        "r3",
        spatial.r3,
        spatial,
        _schema("spatial-r3.json"),
        "group",
        SPATIAL_KWARGS,
    ),
    # multiscales is group-only; uom's schema is array-only.
    Revision(
        "multiscales",
        "r2",
        multiscales.r2,
        multiscales,
        _schema("multiscales-r2.json"),
        "group",
        MULTISCALES_KWARGS,
    ),
    Revision(
        "license",
        None,
        license_,
        license_,
        _schema("license.json"),
        "group",
        LICENSE_KWARGS,
    ),
    Revision("uom", None, uom, uom, _schema("uom.json"), "array", UOM_KWARGS),
    Revision("stac", None, stac, stac, _schema("stac.json"), "group", STAC_KWARGS),
    Revision("cs", None, cs, cs, _schema("cs.json"), "group", CS_KWARGS),
)

REVISIONED: tuple[Revision, ...] = tuple(r for r in REVISIONS if r.label is not None)

BY_CONVENTION: dict[str, tuple[Revision, ...]] = {
    name: tuple(r for r in REVISIONS if r.convention == name)
    for name in zarr_cm.CONVENTION_NAMES
}

revisions = st.sampled_from(REVISIONS)
"""Any revision of any convention."""


@st.composite
def revision_pairs(draw: st.DrawFn) -> tuple[Revision, Revision]:
    """Two *different* revisions of the same convention."""
    name = draw(st.sampled_from([n for n, rs in BY_CONVENTION.items() if len(rs) > 1]))
    first, second = draw(st.permutations(BY_CONVENTION[name]))[:2]
    return first, second


@st.composite
def revision_selections(
    draw: st.DrawFn,
) -> dict[zarr_cm.CanonicalConventionName, Revision]:
    """A non-empty choice of conventions, one revision each: a `create_many` input."""
    names = draw(st.sets(st.sampled_from(sorted(zarr_cm.CONVENTION_NAMES)), min_size=1))
    return {name: draw(st.sampled_from(BY_CONVENTION[name])) for name in sorted(names)}


# --- things that are *not* ours -----------------------------------------------

_reserved = zarr_cm.ALL_CONVENTION_KEYS | {"zarr_conventions"}

foreign_attrs: st.SearchStrategy[dict[str, Any]] = st.dictionaries(
    st.text(min_size=1, max_size=10).filter(lambda k: k not in _reserved),
    json_values,
    max_size=4,
)
"""Attributes belonging to nobody: keys no convention claims, arbitrary values."""

_known_uuids = {r.module.UUID for r in REVISIONS}


def _foreign_declaration(u: UUID, name: str) -> dict[str, str]:
    return {"uuid": str(u), "name": name}


foreign_declarations: st.SearchStrategy[list[dict[str, str]]] = st.lists(
    st.builds(
        _foreign_declaration,
        st.uuids().filter(lambda u: str(u) not in _known_uuids),
        text,
    ),
    max_size=3,
)
"""`zarr_conventions` entries for conventions this package does not know."""
