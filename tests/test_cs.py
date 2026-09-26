"""The cs convention: valid coordinate sets, and one test per rejection.

Every rejection the upstream schema also expresses is checked against the
vendored schema too, so the hand-written validation and the schema are seen to
agree; rules that only the spec's prose states are marked `by_schema=False`.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsonschema
import pytest
from conftest import as_sequence
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7
from strategies import cs_external_schemas

from zarr_cm import cs

if TYPE_CHECKING:
    from collections.abc import Callable

SCHEMA = json.loads((Path(__file__).parent / "schemas" / "cs.json").read_text())

# PROJJSON is opaque to zarr-cm, as in the proj tests: accept any object.
_EXTERNAL: Registry[Any] = Registry().with_resources(  # type: ignore[assignment]
    (url, Resource.from_contents(schema, default_specification=DRAFT7))
    for url, schema in [
        *cs_external_schemas(),
        ("https://proj.org/schemas/v0.7/projjson.schema.json", {}),
    ]
)


def _schema_accepts(node: dict[str, Any]) -> bool:
    validator = jsonschema.Draft7Validator(SCHEMA, registry=_EXTERNAL)
    return validator.is_valid(node)  # type: ignore[reportUnknownMemberType]


# --- fixtures: a feature-complete store ------------------------------------------

_LON_LAT: dict[str, Any] = {
    "type": "planar",
    "name": "WGS84",
    "axes": {
        "lon": {
            "abbreviation": "X",
            "coordinates": [
                {
                    "direction": "east",
                    "unit": "degrees",
                    "values": {"regular": [0.625, 1.25]},
                    "boundaries": {"regular": [-0.625, 0.625]},
                }
            ],
        },
        "lat": {
            "abbreviation": "Y",
            "coordinates": [
                {
                    "direction": "north",
                    "unit": "degrees",
                    "values": {"regular": [-89.5, 1]},
                }
            ],
        },
    },
    "id": {"proj:code": "EPSG:4326"},
}

_TIME: dict[str, Any] = {
    "type": "temporal",
    "axes": {
        "time": {
            "abbreviation": "T",
            "coordinates": [
                {
                    "direction": "future",
                    "time": {"unit": "day", "epoch": "1850-01-01", "calendar": "noleap"},
                    "values": {"external": {"ref": {"node": "../time"}}},
                    "boundaries": {"external": {"ref": {"node": "../time_bnds"}}},
                }
            ],
        }
    },
}

_LEVEL: dict[str, Any] = {
    "type": "vertical",
    "axes": {
        "lev": {
            "abbreviation": "Z",
            "coordinates": [
                {
                    "name": "sigma",
                    "direction": "down",
                    "unit": {"ucum": {"unit": "1"}, "description": "dimensionless"},
                    "values": {"explicit": [0.1, 0.5, 0.9]},
                    "parametric": {
                        "formula": "atmosphere_sigma_coordinate",
                        "terms": {
                            "sigma": {"explicit": [0.1, 0.5, 0.9]},
                            "ps": {"external": {"ref": {"node": "../ps"}}},
                            "ptop": {"explicit": [1000]},
                        },
                    },
                },
                {"name": "labels", "values": {"explicit": ["low", "mid", "high"]}},
            ],
        }
    },
}

_ROTATED: dict[str, Any] = {
    "type": "planar",
    "axes": {
        "rlon": {
            "abbreviation": "X",
            "coordinates": [
                {"direction": "east", "unit": "degrees", "values": {"regular": [0, 1]}}
            ],
        },
        "rlat": {
            "abbreviation": "Y",
            "coordinates": [
                {"direction": "north", "unit": "degrees", "values": {"regular": [0, 1]}}
            ],
        },
    },
    "geolocation": {
        "geodetic": {
            "x": {"node": "../lon"},
            "y": {"node": "../lat"},
            "crs": {"proj:code": "EPSG:4326"},
        }
    },
}

_BAND: dict[str, Any] = {"type": "undefined", "axes": {"band": {}}}

_ARRAY_SHELL: dict[str, Any] = {
    "zarr_format": 3,
    "node_type": "array",
    "data_type": "float32",
    "chunk_grid": {"name": "regular", "configuration": {"chunk_shape": [1, 1, 1, 1]}},
    "chunk_key_encoding": {"name": "default"},
    "fill_value": 0.0,
    "codecs": [{"name": "bytes"}],
}


def _array(cs_value: Any, dimension_names: list[str]) -> dict[str, Any]:
    return {
        **_ARRAY_SHELL,
        "shape": [1] * len(dimension_names),
        "dimension_names": dimension_names,
        "attributes": cs.create_convention_attrs(cs=cs_value),
    }


def _group(crs_value: Any) -> dict[str, Any]:
    return {
        "zarr_format": 3,
        "node_type": "group",
        "attributes": cs.create_convention_attrs(crs=crs_value),
    }


def _full_array() -> dict[str, Any]:
    return _array(
        {"name": "model", "crs": [_LON_LAT, _TIME, _LEVEL], "attributes": {}},
        ["time", "lev", "lat", "lon"],
    )


def _full_group() -> dict[str, Any]:
    return _group({"WGS84": _LON_LAT, "calendar": _TIME})


_VALID_NODES: list[dict[str, Any]] = [
    _full_array(),
    _full_group(),
    # an array whose CRSs live on its parent group, referenced by JSON pointer
    _array(
        {
            "crs": [
                {"node": "..", "attribute": "/attributes/crs/WGS84"},
                {"node": "..", "attribute": "/attributes/crs/calendar"},
            ]
        },
        ["time", "lat", "lon"],
    ),
    # geolocation arrays; an ordinal axis; a compound identifier on the set
    _array(
        {"crs": [_ROTATED, _BAND], "id": {"proj:wkt2": "COMPOUNDCRS[...]"}},
        ["band", "rlat", "rlon"],
    ),
    # a length-1 axis absent from dimension_names is allowed
    _array({"crs": [_LON_LAT, _LEVEL]}, ["lat", "lon"]),
]


@pytest.mark.parametrize("node", _VALID_NODES, ids=range(len(_VALID_NODES)))
def test_valid_nodes(node: dict[str, Any]) -> None:
    """create, insert/extract and node validation agree, and upstream's schema does too."""
    attrs = node["attributes"]
    data = {k: v for k, v in attrs.items() if k != "zarr_conventions"}
    assert cs.create(**data) == data
    assert cs.validate(data) == data
    remaining, extracted = cs.extract(cs.insert({"foo": 1}, cs.create(**data)))
    assert (remaining, extracted) == ({"foo": 1}, data)
    assert as_sequence(attrs["zarr_conventions"]) == [cs.CMO]
    assert cs.validate_node_metadata(node) == node  # type: ignore[arg-type]
    assert cs.detect(attrs) == "main"
    assert _schema_accepts(node)


def test_extract_missing_convention() -> None:
    assert cs.extract({"foo": "bar"}) == ({"foo": "bar"}, {})


# --- rejections ------------------------------------------------------------------


def _rejected(
    node: dict[str, Any],
    error: type[Exception],
    match: str,
    *,
    by_schema: bool = True,
) -> None:
    with pytest.raises(error, match=match):
        cs.validate_node_metadata(node)  # type: ignore[arg-type]
    assert _schema_accepts(node) is not by_schema


def _array_with(edit: Callable[[dict[str, Any]], object]) -> dict[str, Any]:
    """A deep copy of the full array, with *edit* applied to its `cs` object."""
    node = copy.deepcopy(_full_array())
    edit(node["attributes"]["cs"])
    return node


def _coordinates(cs_value: dict[str, Any]) -> dict[str, Any]:
    """The first set of coordinates of the longitude axis."""
    return cs_value["crs"][0]["axes"]["lon"]["coordinates"][0]


def test_neither_cs_nor_crs() -> None:
    with pytest.raises(ValueError, match="At least one of 'cs', 'crs'"):
        cs.validate({})


def test_array_without_cs() -> None:
    node = {**_full_array(), "attributes": _full_group()["attributes"]}
    _rejected(node, ValueError, "'cs' is required on array nodes")


def test_group_without_crs() -> None:
    node = {**_full_group(), "attributes": _full_array()["attributes"]}
    _rejected(node, ValueError, "'crs' is required on group nodes")


def test_array_without_dimension_names() -> None:
    node = _full_array()
    del node["dimension_names"]
    _rejected(node, ValueError, "'dimension_names' is required")


def test_dimension_name_pattern() -> None:
    node = {**_full_array(), "dimension_names": ["time", "lev", "lat", "1lon"]}
    _rejected(node, ValueError, r"'dimension_names\[3\]' must be a string matching")


def test_dimension_names_unique() -> None:
    node = {**_full_array(), "dimension_names": ["time", "lev", "lat", "lat"]}
    _rejected(node, ValueError, "'dimension_names' must be unique")


def test_dimension_without_axis() -> None:
    node = {**_full_array(), "dimension_names": ["time", "lev", "lat", "lon", "band"]}
    _rejected(node, ValueError, r"no axis for the dimension\(s\) \['band'\]", by_schema=False)


def test_cs_not_an_object() -> None:
    node = _full_array()
    node["attributes"]["cs"] = []
    _rejected(node, TypeError, "'cs' must be a JSON object")


def test_cs_without_crs() -> None:
    _rejected(
        _array_with(lambda c: c.pop("crs")), ValueError, "'cs' is missing required key 'crs'"
    )


def test_crs_without_type() -> None:
    _rejected(
        _array_with(lambda c: c["crs"][0].pop("type")),
        ValueError,
        r"'cs.crs\[0\]' is missing required key 'type'",
    )


def test_crs_unknown_type() -> None:
    _rejected(
        _array_with(lambda c: c["crs"][0].update(type="spatial")),
        ValueError,
        r"'cs.crs\[0\].type' must be one of",
    )


def test_crs_without_axes() -> None:
    _rejected(
        _array_with(lambda c: c["crs"][0].update(axes={})),
        ValueError,
        r"'cs.crs\[0\].axes' must have at least one axis",
    )


def test_group_crs_empty() -> None:
    node = _full_group()
    node["attributes"]["crs"] = {}
    _rejected(node, ValueError, "'crs' must have at least one CRS object")


def test_abbreviation_not_spatiotemporal() -> None:
    _rejected(
        _array_with(lambda c: c["crs"][0]["axes"]["lon"].update(abbreviation="lon")),
        ValueError,
        "abbreviation' must be one of",
        by_schema=False,
    )


def test_abbreviation_repeated_across_crs() -> None:
    _rejected(
        _array_with(lambda c: c["crs"][1]["axes"]["time"].update(abbreviation="X")),
        ValueError,
        r"'cs.crs' uses the axis abbreviation\(s\) \['X'\] more than once",
        by_schema=False,
    )


def test_coordinates_without_values() -> None:
    _rejected(
        _array_with(lambda c: _coordinates(c).pop("values")),
        ValueError,
        "is missing required key 'values'",
    )


def test_values_with_two_kinds() -> None:
    _rejected(
        _array_with(lambda c: _coordinates(c)["values"].update(explicit=[1, 2])),
        ValueError,
        "must have exactly one of",
    )


def test_regular_wrong_length() -> None:
    _rejected(
        _array_with(lambda c: _coordinates(c)["values"].update(regular=[0])),
        ValueError,
        r"regular' must have exactly 2 numbers",
    )


def test_regular_not_numbers() -> None:
    _rejected(
        _array_with(lambda c: _coordinates(c)["values"].update(regular=[0, True])),
        TypeError,
        r"regular\[1\]' must be a number",
    )


def test_regular_zero_increment() -> None:
    _rejected(
        _array_with(lambda c: _coordinates(c)["values"].update(regular=[0, 0])),
        ValueError,
        "increment must not be 0",
        by_schema=False,
    )


def test_explicit_not_an_array() -> None:
    _rejected(
        _array_with(lambda c: _coordinates(c).update(values={"explicit": 3})),
        TypeError,
        "explicit' must be a JSON array",
    )


def test_external_without_ref() -> None:
    _rejected(
        _array_with(lambda c: _coordinates(c).update(values={"external": {}})),
        ValueError,
        "external' is missing required key 'ref'",
    )


def test_ref_extra_key() -> None:
    _rejected(
        _array_with(lambda c: c["crs"].append({"node": "..", "path": "x"})),
        ValueError,
        r"'cs.crs\[3\]' is a ref and allows only",
    )


def test_ref_without_node() -> None:
    _rejected(
        _array_with(lambda c: c["crs"].append({"uri": "s3://bucket/store"})),
        ValueError,
        r"'cs.crs\[3\]' is missing required key 'node'",
    )


def test_ref_attribute_not_a_pointer() -> None:
    _rejected(
        _array_with(lambda c: c["crs"].append({"node": "..", "attribute": "crs"})),
        ValueError,
        "attribute' must be a JSON pointer",
    )


def test_time_without_epoch() -> None:
    _rejected(
        _array_with(lambda c: c["crs"][1]["axes"]["time"]["coordinates"][0]["time"].pop("epoch")),
        ValueError,
        "time' is missing required key 'epoch'",
    )


def test_unit_and_time() -> None:
    _rejected(
        _array_with(
            lambda c: _coordinates(c).update(time={"unit": "day", "epoch": "2000"})
        ),
        ValueError,
        "must not have both 'unit' and 'time'",
        by_schema=False,
    )


def test_unit_object_without_ucum() -> None:
    _rejected(
        _array_with(lambda c: _coordinates(c).update(unit={"description": "metre"})),
        ValueError,
        r"unit': 'ucum' is required",
    )


def test_boundaries_with_two_kinds() -> None:
    _rejected(
        _array_with(
            lambda c: _coordinates(c)["boundaries"].update(
                external={"ref": {"node": "../lon_bnds"}}
            )
        ),
        ValueError,
        "boundaries' must have exactly one of",
    )


def test_parametric_without_terms() -> None:
    _rejected(
        _array_with(
            lambda c: c["crs"][2]["axes"]["lev"]["coordinates"][0]["parametric"].update(
                terms={}
            )
        ),
        ValueError,
        "terms' must have at least one term",
    )


def test_coordinate_set_names_repeated() -> None:
    _rejected(
        _array_with(
            lambda c: c["crs"][2]["axes"]["lev"]["coordinates"][1].update(name="sigma")
        ),
        ValueError,
        "has more than one set named 'sigma'",
        by_schema=False,
    )


def test_id_without_crs_definition() -> None:
    _rejected(
        _array_with(lambda c: c["crs"][0].update(id={"name": "WGS84"})),
        ValueError,
        r"'cs.crs\[0\].id': At least one of 'proj:code'",
    )


def test_geolocation_without_y() -> None:
    node = _array({"crs": [copy.deepcopy(_ROTATED)]}, ["rlat", "rlon"])
    del node["attributes"]["cs"]["crs"][0]["geolocation"]["geodetic"]["y"]
    _rejected(node, ValueError, "geodetic' is missing required key 'y'")


def test_geolocation_unknown_kind() -> None:
    node = _array({"crs": [copy.deepcopy(_ROTATED)]}, ["rlat", "rlon"])
    geolocation = node["attributes"]["cs"]["crs"][0]["geolocation"]
    geolocation["projected"] = geolocation["geodetic"]
    _rejected(node, ValueError, "geolocation' allows only")
