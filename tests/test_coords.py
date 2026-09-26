from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from conftest import as_sequence, wrap_attrs

from zarr_cm import coords

SCHEMA_PATH = Path(__file__).parent / "schemas" / "coords.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())


def _schema_accepts(attrs: dict[str, Any]) -> bool:
    """Whether the vendored upstream schema accepts *attrs* (declared) on a group."""
    node = wrap_attrs({"zarr_conventions": [coords.CMO], **attrs}, node_type="group")
    validator = jsonschema.Draft7Validator(SCHEMA)
    return validator.is_valid(node)  # type: ignore[reportUnknownMemberType]


# ---------------------------------------------------------------------------
# validate(): one test over the valid inputs, one per error case. Every case
# is also checked against the vendored schema, so the hand-written rules and
# upstream's agree.
# ---------------------------------------------------------------------------

_TIME_ARRAY = {"type": "array", "path": "../time"}
_SPATIAL_REF = {"type": "reference", "convention": "spatial"}


@pytest.mark.parametrize(
    "data",
    [
        {"coords:coordinates": {}},
        {"coords:coordinates": {"time": _TIME_ARRAY}, "coords:version": 1},
        {"coords:coordinates": {"y": _SPATIAL_REF, "x": _SPATIAL_REF}},
        {"coords:coordinates": {"lat": {**_TIME_ARRAY, "indexed_by": ["y", "x"]}}},
        {"coords:coordinates": {"band": {"type": "inline", "values": [0.49, 0.56]}}},
        {"coords:coordinates": {"band": {"type": "inline", "values": []}}},
        {
            "coords:coordinates": {
                "az": {"type": "interval", "start": 0, "end": 360, "step": 15}
            }
        },
        {
            "coords:coordinates": {
                "z": {"type": "interval", "start": 2.0, "end": 1.0, "step": -0.25}
            }
        },
        {
            "coords:coordinates": {
                "time": {
                    "type": "interval",
                    "start": "2026-01-01T00:00:00Z",
                    "end": "2026-01-31T00:00:00Z",
                    "step": "P1D",
                }
            }
        },
        # descriptors are open: CF fields ride along unchecked
        {
            "coords:coordinates": {
                "time": {**_TIME_ARRAY, "units": "days since 2020-01-01", "axis": "T"}
            }
        },
    ],
)
def test_validate_accepts_valid_data(data: dict[str, Any]) -> None:
    assert coords.validate(data) == data
    assert _schema_accepts(data)


def _assert_rejected(
    data: dict[str, Any], error: type[Exception], match: str
) -> None:
    with pytest.raises(error, match=match):
        coords.validate(data)
    assert not _schema_accepts(data)


def test_validate_missing_coordinates() -> None:
    _assert_rejected({"coords:version": 1}, ValueError, "'coords:coordinates' is required")


def test_validate_coordinates_not_object() -> None:
    _assert_rejected(
        {"coords:coordinates": []}, TypeError, "'coords:coordinates' must be a JSON object"
    )


def test_validate_descriptor_not_object() -> None:
    _assert_rejected(
        {"coords:coordinates": {"t": "../time"}},
        TypeError,
        r"'coords:coordinates\.t' must be a JSON object",
    )


def test_validate_descriptor_missing_type() -> None:
    _assert_rejected(
        {"coords:coordinates": {"t": {"path": "../time"}}},
        ValueError,
        "missing required key 'type'",
    )


def test_validate_descriptor_unknown_type() -> None:
    _assert_rejected(
        {"coords:coordinates": {"y": {"type": "affine"}}},
        ValueError,
        r"'coords:coordinates\.y\.type' must be one of",
    )


def test_validate_array_missing_path() -> None:
    _assert_rejected(
        {"coords:coordinates": {"t": {"type": "array"}}},
        ValueError,
        "of type 'array' is missing required key 'path'",
    )


def test_validate_array_path_not_string() -> None:
    _assert_rejected(
        {"coords:coordinates": {"t": {"type": "array", "path": 1}}},
        TypeError,
        r"'coords:coordinates\.t\.path' must be a string",
    )


def test_validate_indexed_by_not_array() -> None:
    _assert_rejected(
        {"coords:coordinates": {"lat": {**_TIME_ARRAY, "indexed_by": "sample"}}},
        TypeError,
        r"'coords:coordinates\.lat\.indexed_by' must be an array",
    )


def test_validate_indexed_by_empty() -> None:
    _assert_rejected(
        {"coords:coordinates": {"lat": {**_TIME_ARRAY, "indexed_by": []}}},
        ValueError,
        "must not be empty",
    )


def test_validate_indexed_by_items_not_strings() -> None:
    _assert_rejected(
        {"coords:coordinates": {"lat": {**_TIME_ARRAY, "indexed_by": [0]}}},
        TypeError,
        "items must be strings",
    )


def test_validate_reference_missing_convention() -> None:
    _assert_rejected(
        {"coords:coordinates": {"y": {"type": "reference"}}},
        ValueError,
        "of type 'reference' is missing required key 'convention'",
    )


def test_validate_inline_values_not_array() -> None:
    _assert_rejected(
        {"coords:coordinates": {"band": {"type": "inline", "values": 1}}},
        TypeError,
        r"'coords:coordinates\.band\.values' must be an array",
    )


def test_validate_interval_missing_field() -> None:
    _assert_rejected(
        {"coords:coordinates": {"z": {"type": "interval", "start": 0, "end": 1}}},
        ValueError,
        "of type 'interval' is missing required key 'step'",
    )


def test_validate_interval_zero_step() -> None:
    _assert_rejected(
        {
            "coords:coordinates": {
                "z": {"type": "interval", "start": 0, "end": 1, "step": 0}
            }
        },
        ValueError,
        "must be non-zero",
    )


def test_validate_interval_step_not_a_duration() -> None:
    _assert_rejected(
        {
            "coords:coordinates": {
                "t": {"type": "interval", "start": "2026", "end": "2027", "step": "1D"}
            }
        },
        ValueError,
        "must be an ISO 8601 duration",
    )


def test_validate_interval_mixed_types() -> None:
    _assert_rejected(
        {
            "coords:coordinates": {
                "t": {"type": "interval", "start": "2026", "end": 1, "step": "P1D"}
            }
        },
        TypeError,
        "all numbers, or all strings",
    )


def test_validate_version_not_integer() -> None:
    _assert_rejected(
        {"coords:coordinates": {}, "coords:version": "1"},
        TypeError,
        "'coords:version' must be an integer",
    )


def test_validate_version_not_one() -> None:
    _assert_rejected(
        {"coords:coordinates": {}, "coords:version": 2},
        ValueError,
        "'coords:version' must be 1",
    )


# ---------------------------------------------------------------------------
# create / insert / extract / detect
# ---------------------------------------------------------------------------


def test_create() -> None:
    assert coords.create(coordinates={"time": _TIME_ARRAY}) == {  # type: ignore[typeddict-item]
        "coords:coordinates": {"time": _TIME_ARRAY}
    }
    assert coords.create(coordinates={}, version=1) == {
        "coords:coordinates": {},
        "coords:version": 1,
    }


def test_insert_and_extract_roundtrip() -> None:
    data = coords.create(coordinates={"y": {"type": "reference", "convention": "spatial"}})
    inserted = coords.insert({"foo": "bar"}, data)
    assert coords.CMO in as_sequence(inserted["zarr_conventions"])
    remaining, extracted = coords.extract(inserted)
    assert extracted == data
    assert remaining == {"foo": "bar"}


def test_insert_collision_raises() -> None:
    data = coords.create(coordinates={})
    with pytest.raises(ValueError, match="overwritten"):
        coords.insert({"coords:coordinates": {"t": _TIME_ARRAY}}, data)


# ---------------------------------------------------------------------------
# Node-level validation: array keys must name dimension_names.
# ---------------------------------------------------------------------------

_DECLARATION = {
    "schema_url": coords.SCHEMA_URL,
    "spec_url": coords.SPEC_URL,
    "uuid": coords.UUID,
    "name": "coords",
    "description": "Domain-agnostic mapping between Zarr array index space and coordinate space.",
}


def _array(dimension_names: list[str] | None, coordinates: dict[str, Any]) -> Any:
    node: dict[str, Any] = {
        "zarr_format": 3,
        "node_type": "array",
        "attributes": {
            "zarr_conventions": [_DECLARATION],
            "coords:coordinates": coordinates,
            "coords:version": 1,
        },
    }
    if dimension_names is not None:
        node["dimension_names"] = dimension_names
    return node


# The upstream examples/*.json at the snapshot commit, verbatim.
_UPSTREAM_EXAMPLES = [
    _array(
        ["time", "y", "x"],
        {"time": _TIME_ARRAY, "y": _SPATIAL_REF, "x": _SPATIAL_REF},
    ),
    _array(
        ["time", "elevation", "azimuth"],
        {
            "time": {
                "type": "interval",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-31T00:00:00Z",
                "step": "P1D",
            },
            "elevation": {"type": "interval", "start": 1.0, "end": 2.0, "step": 0.25},
            "azimuth": {"type": "interval", "start": 0, "end": 360, "step": 15},
        },
    ),
    _array(
        ["sample"],
        {
            name: {"type": "array", "indexed_by": ["sample"], "path": f"../{name}"}
            for name in ("lat", "lon", "time")
        },
    ),
    _array(
        ["y", "x"],
        {
            name: {"type": "array", "indexed_by": ["y", "x"], "path": f"../{name}"}
            for name in ("lat", "lon")
        },
    ),
]


@pytest.mark.parametrize(
    "node",
    [
        *_UPSTREAM_EXAMPLES,
        # an array without dimension_names can still carry an empty map
        _array(None, {}),
        # null entries in dimension_names are allowed; named ones still resolve
        _array([None, "x"], {"x": _SPATIAL_REF}),  # type: ignore[list-item]
        # on a group, keys name the children's dimensions and go unchecked
        {**_array(None, {"anything": _TIME_ARRAY}), "node_type": "group"},
    ],
)
def test_node_metadata_accepts_valid_documents(node: Any) -> None:
    assert coords.validate_node_metadata(node) == node
    assert jsonschema.Draft7Validator(SCHEMA).is_valid(node)  # type: ignore[reportUnknownMemberType]


def test_array_key_not_a_dimension_name() -> None:
    node = _array(["time", "y"], {"x": _SPATIAL_REF})
    with pytest.raises(ValueError, match="key 'x' is not one of the array's"):
        coords.validate_array_metadata(node)


def test_array_indexed_by_not_a_dimension_name() -> None:
    node = _array(["y", "x"], {"lat": {**_TIME_ARRAY, "indexed_by": ["sample"]}})
    with pytest.raises(ValueError, match=r"indexed_by' names 'sample'"):
        coords.validate_array_metadata(node)


def test_array_without_dimension_names_rejects_keys() -> None:
    node = _array(None, {"time": _TIME_ARRAY})
    with pytest.raises(ValueError, match="key 'time' is not one of the array's"):
        coords.validate_array_metadata(node)


def test_array_dimension_names_not_an_array() -> None:
    node: Any = {**_array(None, {}), "dimension_names": "time"}
    with pytest.raises(TypeError, match="'dimension_names' must be an array"):
        coords.validate_array_metadata(node)


def test_upstream_schema_pins_the_declaration_we_write() -> None:
    """The upstream schema `const`-pins every declaration field; ours match."""
    assert coords.CMO == _DECLARATION
