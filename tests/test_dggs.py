"""dggs: one test of the valid combinations, then one test per error case.

Every case is also run through the vendored upstream schema. The hand-written
validator follows the README, which is stricter than the schema in a few
places (see `zarr_cm.dggs`); each error test records whether the schema agrees
(`schema_rejects`), so a schema change that closes or opens one of those gaps
shows up here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from conftest import as_sequence, wrap_attrs

from zarr_cm import dggs

SCHEMA_PATH = Path(__file__).parent / "schemas" / "dggs.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())

_WGS84_IF = {
    "name": "WGS84",
    "semi_major_axis": 6378137.0,
    "inverse_flattening": 298.257223563,
}
_WGS84_MINOR = {
    "name": "WGS84",
    "semi_major_axis": 6378137.0,
    "semi_minor_axis": 6356752.314,
}
_SPHERE = {"name": "sphere", "radius": 6370997.0}

_HEALPIX: dict[str, Any] = {
    "name": "healpix",
    "refinement_level": 10,
    "indexing_scheme": "nested",
    "spatial_dimension": "cells",
}
_H3: dict[str, Any] = {
    "name": "h3",
    "refinement_level": 10,
    "spatial_dimension": "cell",
}
# `create()`'s named keyword arguments; anything else goes in `parameters`.
_KEYWORDS = frozenset(
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


def _schema_accepts(data: dict[str, Any], node_type: str = "group") -> bool:
    node = wrap_attrs(
        {"zarr_conventions": [dggs.CMO], "dggs": data}, node_type=node_type
    )
    return jsonschema.Draft7Validator(SCHEMA).is_valid(node)  # type: ignore[reportUnknownMemberType]


def _rejects(
    data: dict[str, Any],
    error: type[Exception],
    match: str,
    *,
    schema_rejects: bool,
) -> None:
    with pytest.raises(error, match=match):
        dggs.validate(data)
    assert _schema_accepts(data) is not schema_rejects


# --- valid input ---------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        # the README's two examples
        _HEALPIX
        | {"ellipsoid": _WGS84_IF, "coordinate": "cell_ids", "compression": "none"},
        _HEALPIX | {"refinement_level": 16},
        # a generic DGGS: full domain, implicit sphere, every compression
        _H3,
        *(
            _H3 | {"coordinate": "cell_ids", "compression": c}
            for c in dggs.COMPRESSIONS
        ),
        # each ellipsoid shape
        _H3 | {"ellipsoid": _SPHERE},
        _H3 | {"ellipsoid": _WGS84_MINOR},
        _H3 | {"ellipsoid": _WGS84_IF},
        # variable-sized cells, with an explicit uncompressed coordinate
        _H3
        | {"refinement_level": None, "coordinate": "cell_ids", "compression": "none"},
        # HEALPix: base schemes at the level bounds
        _HEALPIX | {"indexing_scheme": "ring", "refinement_level": 0},
        _HEALPIX | {"refinement_level": dggs.HEALPIX_MAX_LEVEL},
        # HEALPix *uniq schemes: constant or variable level
        _HEALPIX | {"indexing_scheme": "zuniq"},
        _HEALPIX
        | {
            "indexing_scheme": "nuniq",
            "refinement_level": None,
            "coordinate": "cell_ids",
            "compression": "none",
        },
        # HEALPix compression table
        _HEALPIX
        | {
            "indexing_scheme": "zuniq",
            "refinement_level": None,
            "coordinate": "cell_ids",
            "compression": "compacted",
        },
        _HEALPIX
        | {"refinement_level": 29, "coordinate": "cell_ids", "compression": "ranges"},
        # HEALPix: other schemes carry no level restriction
        _HEALPIX | {"indexing_scheme": "unknown_scheme", "refinement_level": 100},
        # DGGS-specific parameters pass through
        _H3 | {"generic_parameter": "some_value"},
        _HEALPIX | {"generic_parameter": {"nested": [1, 2]}},
    ],
)
def test_valid(data: dict[str, Any]) -> None:
    assert dggs.validate(data) is data
    for node_type in ("array", "group"):
        assert _schema_accepts(data, node_type)
    # ...and the same data round-trips through create/insert/extract.
    kwargs = {k: v for k, v in data.items() if k in _KEYWORDS}
    extra = {k: v for k, v in data.items() if k not in _KEYWORDS}
    created = dggs.create(**kwargs, parameters=extra or None)
    assert created == data
    attrs = dggs.insert({"foo": "bar"}, created)
    assert as_sequence(attrs["zarr_conventions"]) == [dggs.CMO]
    assert dggs.extract(attrs) == ({"foo": "bar"}, data)
    assert dggs.create_convention_attrs(**kwargs, parameters=extra or None) == (
        dggs.insert({}, created)
    )


def test_extract_absent_convention() -> None:
    assert dggs.extract({"foo": "bar"}) == ({"foo": "bar"}, {})


# --- errors: required fields -------------------------------------------------------


@pytest.mark.parametrize("key", ["name", "refinement_level", "spatial_dimension"])
def test_missing_required_field(key: str) -> None:
    data = {k: v for k, v in _H3.items() if k != key}
    _rejects(data, ValueError, f"'{key}' is required", schema_rejects=True)


@pytest.mark.parametrize("key", ["name", "spatial_dimension", "coordinate"])
def test_string_field_wrong_type(key: str) -> None:
    data = _H3 | {"coordinate": "cell_ids", "compression": "none", key: 1}
    _rejects(data, TypeError, f"'{key}' must be a string", schema_rejects=True)


def test_name_not_lower_case() -> None:
    _rejects(
        _HEALPIX | {"name": "HEALPix"},
        ValueError,
        "must be lower-cased",
        schema_rejects=False,
    )


@pytest.mark.parametrize("level", [True, 1.5, "10"])
def test_refinement_level_wrong_type(level: object) -> None:
    _rejects(
        _H3 | {"refinement_level": level},
        TypeError,
        "'refinement_level' must be an integer or null",
        schema_rejects=True,
    )


def test_refinement_level_negative() -> None:
    _rejects(
        _H3 | {"refinement_level": -1},
        ValueError,
        "must be non-negative",
        schema_rejects=True,
    )


# --- errors: coordinate / compression ----------------------------------------------


def test_compression_unknown() -> None:
    _rejects(
        _H3 | {"coordinate": "cell_ids", "compression": "unknown"},
        ValueError,
        "'compression' must be one of",
        schema_rejects=True,
    )


@pytest.mark.parametrize(
    "extra", [{"coordinate": "cell_ids"}, {"compression": "none"}], ids=str
)
def test_coordinate_and_compression_unpaired(extra: dict[str, str]) -> None:
    _rejects(
        _H3 | extra,
        ValueError,
        "'compression' must be given when 'coordinate' is given",
        schema_rejects=False,
    )


def test_null_level_without_coordinate() -> None:
    _rejects(
        _H3 | {"refinement_level": None},
        ValueError,
        "requires a 'coordinate'",
        schema_rejects=False,
    )


def test_null_level_with_compressed_coordinate() -> None:
    _rejects(
        _H3 | {"refinement_level": None, "coordinate": "c", "compression": "ranges"},
        ValueError,
        "requires 'compression' to be 'none'",
        schema_rejects=False,
    )


# --- errors: ellipsoid -------------------------------------------------------------


def test_ellipsoid_not_an_object() -> None:
    _rejects(
        _H3 | {"ellipsoid": "WGS84"},
        TypeError,
        "'ellipsoid' must be a JSON object",
        schema_rejects=True,
    )


def test_ellipsoid_missing_name() -> None:
    _rejects(
        _H3 | {"ellipsoid": {"radius": 6370997.0}},
        ValueError,
        "'ellipsoid.name' is required",
        schema_rejects=True,
    )


def test_ellipsoid_unknown_key() -> None:
    _rejects(
        _H3 | {"ellipsoid": _SPHERE | {"flattening": 0.003}},
        ValueError,
        "unknown keys",
        schema_rejects=True,
    )


def test_ellipsoid_parameter_not_a_number() -> None:
    _rejects(
        _H3 | {"ellipsoid": {"name": "sphere", "radius": "6370997"}},
        TypeError,
        r"'ellipsoid\.radius' must be a number",
        schema_rejects=True,
    )


def test_ellipsoid_parameter_negative() -> None:
    _rejects(
        _H3 | {"ellipsoid": {"name": "sphere", "radius": -1.0}},
        ValueError,
        r"'ellipsoid\.radius' must be non-negative",
        schema_rejects=True,
    )


def _shape_id(value: object) -> str:
    return str(sorted(value)) if isinstance(value, dict) else str(value)  # pyright: ignore[reportUnknownArgumentType]


@pytest.mark.parametrize(
    ("ellipsoid", "schema_rejects"),
    [
        ({"name": "empty"}, True),
        ({"name": "x", "semi_major_axis": 1.0}, True),
        (_WGS84_IF | {"radius": 1.0}, True),
        (_WGS84_IF | {"semi_minor_axis": 1.0}, True),
        (_WGS84_MINOR | {"radius": 1.0}, True),
        # the schema's sphere branch only forbids all three axis keys together
        (_SPHERE | {"semi_major_axis": 1.0}, False),
        (_SPHERE | {"inverse_flattening": 1.0}, False),
        # ...and its third branch misspells `semi_minor_axis`, so every key at
        # once matches exactly one branch
        (_WGS84_IF | {"radius": 1.0, "semi_minor_axis": 1.0}, False),
    ],
    ids=_shape_id,
)
def test_ellipsoid_shape_ambiguous(
    ellipsoid: dict[str, Any], *, schema_rejects: bool
) -> None:
    _rejects(
        _H3 | {"ellipsoid": ellipsoid},
        ValueError,
        "'ellipsoid' must have exactly one of",
        schema_rejects=schema_rejects,
    )


# --- errors: HEALPix ---------------------------------------------------------------


def test_healpix_missing_indexing_scheme() -> None:
    data = {k: v for k, v in _HEALPIX.items() if k != "indexing_scheme"}
    _rejects(data, ValueError, "'indexing_scheme' is required", schema_rejects=True)


def test_healpix_indexing_scheme_wrong_type() -> None:
    _rejects(
        _HEALPIX | {"indexing_scheme": 1},
        TypeError,
        "'indexing_scheme' must be a string",
        schema_rejects=True,
    )


@pytest.mark.parametrize("scheme", ["nested", "ring"])
@pytest.mark.parametrize("level", [None, 30])
def test_healpix_base_scheme_level_out_of_range(scheme: str, level: int | None) -> None:
    data = _HEALPIX | {"indexing_scheme": scheme, "refinement_level": level}
    if level is None:
        data |= {"coordinate": "cell_ids", "compression": "none"}
    _rejects(
        data, ValueError, "requires an integer 'refinement_level'", schema_rejects=True
    )


def test_healpix_uniq_scheme_level_out_of_range() -> None:
    _rejects(
        _HEALPIX | {"indexing_scheme": "zuniq", "refinement_level": 30},
        ValueError,
        "requires 'refinement_level' to be null or between",
        schema_rejects=True,
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"compression": "compacted"},
        {"compression": "compacted", "indexing_scheme": "zuniq"},
        {"compression": "ranges"},
        {"compression": "ranges", "indexing_scheme": "ring", "refinement_level": 29},
    ],
    ids=str,
)
def test_healpix_compression_table_violated(extra: dict[str, Any]) -> None:
    _rejects(
        _HEALPIX | {"coordinate": "cell_ids"} | extra,
        ValueError,
        "coordinates require indexing scheme",
        schema_rejects=False,
    )


# --- errors: create / node-level ---------------------------------------------------


def test_create_parameters_clash_with_standard_field() -> None:
    with pytest.raises(ValueError, match="may not set standard dggs fields"):
        dggs.create(
            name="h3",
            refinement_level=5,
            spatial_dimension="cells",
            parameters={"coordinate": "cell_ids"},
        )


def test_extract_dggs_not_an_object() -> None:
    with pytest.raises(TypeError, match="'dggs' must be a JSON object"):
        dggs.extract({"zarr_conventions": [dggs.CMO], "dggs": "healpix"})


def test_node_missing_dggs_key() -> None:
    node: Any = wrap_attrs({"zarr_conventions": [dggs.CMO]}, node_type="group")
    with pytest.raises(ValueError, match="'dggs' is required"):
        dggs.validate_group_metadata(node)


def test_node_dggs_not_an_object() -> None:
    node: Any = wrap_attrs(
        {"zarr_conventions": [dggs.CMO], "dggs": "healpix"}, node_type="array"
    )
    with pytest.raises(TypeError, match="'dggs' must be a JSON object"):
        dggs.validate_node_metadata(node)
