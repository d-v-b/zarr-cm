"""The nz (NZ-1.0) convention.

Each error case gets its own test, and each also checks the vendored upstream
schema's verdict on the same document, so the hand-written validation is
pinned to agree with it -- or, where the spec asks for more than the schema
checks, pinned to differ deliberately.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

import zarr_cm
from zarr_cm import nz

SCHEMA = json.loads((Path(__file__).parent / "schemas" / "nz.json").read_text())
_VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def schema_accepts(node: Any) -> bool:
    return _VALIDATOR.is_valid(node)  # type: ignore[reportUnknownMemberType]


# The upstream examples (zarr-conventions/nz@7c923cf, examples/), trimmed to
# the fields the convention looks at.
_UPSTREAM_CMO: dict[str, Any] = {
    "schema_url": "https://raw.githubusercontent.com/zarr-conventions/nz/refs/tags/v1/schema.json",
    "spec_url": "https://github.com/zarr-conventions/nz/blob/v1/README.md",
    "uuid": "d0a980b5-c644-4dcc-85a1-283799a58f40",
    "name": "NZ-1.0",
    "description": "Structural interoperability layer for scientific array conventions on Zarr v3",
}


def _array(attrs: Any, *, shape: Any, dimension_names: Any) -> dict[str, Any]:
    return {
        "zarr_format": 3,
        "node_type": "array",
        "shape": shape,
        "data_type": "float32",
        "dimension_names": dimension_names,
        "chunk_grid": {"name": "regular", "configuration": {"chunk_shape": shape}},
        "chunk_key_encoding": {"name": "default"},
        "fill_value": "NaN",
        "codecs": [{"name": "bytes"}],
        "attributes": attrs,
    }


def _group(attrs: Any) -> dict[str, Any]:
    return {"zarr_format": 3, "node_type": "group", "attributes": attrs}


def _valid_array() -> dict[str, Any]:
    return _array(
        {"zarr_conventions": [_UPSTREAM_CMO]},
        shape=[8760, 721, 1440],
        dimension_names=["time", "lat", "lon"],
    )


def _valid_group() -> dict[str, Any]:
    return _group({"zarr_conventions": [_UPSTREAM_CMO], "conventions": "NZ-1.0"})


UPSTREAM_EXAMPLES: dict[str, dict[str, Any]] = {
    "array_basic": _valid_array(),
    "array_fillvalue": _array(
        {"zarr_conventions": [_UPSTREAM_CMO], "_FillValue": -9999.0},
        shape=[365, 180, 360],
        dimension_names=["time", "lat", "lon"],
    ),
    "dimension_coordinate": _array(
        {"zarr_conventions": [_UPSTREAM_CMO]}, shape=[721], dimension_names=["lat"]
    ),
    "root_group": _group(
        {
            "zarr_conventions": [_UPSTREAM_CMO],
            "conventions": "NZ-1.0",
            "title": "Example NZ dataset",
        }
    ),
    "root_group_cf": _group(
        {
            "zarr_conventions": [_UPSTREAM_CMO],
            "conventions": "NZ-1.0 CF-1.12",
            "title": "ERA5 hourly data on single levels",
        }
    ),
}


def test_cmo_matches_upstream_registration() -> None:
    """The schema pins schema_url/spec_url/name as consts; we emit them."""
    assert nz.CMO == _UPSTREAM_CMO


# --- create / validate ----------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, {}),
        ({"conventions": "NZ-1.0"}, {"conventions": "NZ-1.0"}),
        ({"conventions": "CF-1.12 NZ-1.0"}, {"conventions": "CF-1.12 NZ-1.0"}),
        ({"fill_value": -9999.0}, {"_FillValue": -9999.0}),
        ({"fill_value": "NaN"}, {"_FillValue": "NaN"}),
        (
            {"conventions": "NZ-1.0 CF-1.12", "fill_value": 0},
            {"conventions": "NZ-1.0 CF-1.12", "_FillValue": 0},
        ),
    ],
)
def test_create(kwargs: dict[str, Any], expected: dict[str, Any]) -> None:
    created = nz.create(**kwargs)
    assert created == expected
    assert nz.validate(created) == expected
    attrs = nz.create_convention_attrs(**kwargs)
    assert attrs == {"zarr_conventions": [nz.CMO], **expected}
    assert nz.extract(attrs) == ({}, expected)


def test_validate_rejects_non_string_conventions() -> None:
    with pytest.raises(TypeError, match="'conventions' must be a string"):
        nz.validate({"conventions": ["NZ-1.0"]})


def test_validate_rejects_conventions_without_identifier() -> None:
    with pytest.raises(ValueError, match="must list 'NZ-1.0'"):
        nz.create(conventions="CF-1.12")


def test_insert_collides_with_existing_conventions() -> None:
    with pytest.raises(ValueError, match="overwritten"):
        nz.insert({"conventions": "CF-1.12"}, nz.create(conventions="NZ-1.0 CF-1.12"))


# --- node-level validation --------------------------------------------------------


WRITTEN_EXAMPLES: dict[str, dict[str, Any]] = {
    "group_cf": _group(nz.create_convention_attrs(conventions="NZ-1.0 CF-1.12")),
    "group_fill_value": _group(
        nz.create_convention_attrs(conventions="NZ-1.0", fill_value=-1)
    ),
    "array": _array(
        nz.create_convention_attrs(), shape=[2, 3], dimension_names=["y", "x"]
    ),
    "array_fill_value": _array(
        nz.create_convention_attrs(fill_value=-9999), shape=[4], dimension_names=["t"]
    ),
    "scalar_array": _array(nz.create_convention_attrs(), shape=[], dimension_names=[]),
    # `conventions` on an array is not NZ's to police
    "array_foreign_conventions": _array(
        {"zarr_conventions": [nz.CMO], "conventions": "CF-1.12"},
        shape=[1],
        dimension_names=["x"],
    ),
}


@pytest.mark.parametrize(
    "node",
    [*UPSTREAM_EXAMPLES.values(), *WRITTEN_EXAMPLES.values()],
    ids=[*UPSTREAM_EXAMPLES, *WRITTEN_EXAMPLES],
)
def test_valid_nodes(node: dict[str, Any]) -> None:
    """Upstream's examples, and what we write, validate here and upstream."""
    assert schema_accepts(node)
    assert nz.validate_node_metadata(node) == node  # type: ignore[arg-type]


def test_undeclared_convention_rejected() -> None:
    node = _valid_group()
    node["attributes"]["zarr_conventions"] = []
    assert not schema_accepts(node)
    with pytest.raises(ValueError, match="not declared"):
        nz.validate_group_metadata(node)  # type: ignore[arg-type]


def test_group_missing_conventions_rejected() -> None:
    node = _valid_group()
    del node["attributes"]["conventions"]
    assert not schema_accepts(node)
    with pytest.raises(ValueError, match="'conventions' is required on groups"):
        nz.validate_group_metadata(node)  # type: ignore[arg-type]


def test_group_conventions_without_identifier_rejected() -> None:
    node = _valid_group()
    node["attributes"]["conventions"] = "CF-1.12"
    assert not schema_accepts(node)
    with pytest.raises(ValueError, match="must list 'NZ-1.0'"):
        nz.validate_group_metadata(node)  # type: ignore[arg-type]


def test_group_conventions_wrong_type_rejected() -> None:
    node = _valid_group()
    node["attributes"]["conventions"] = 1
    assert not schema_accepts(node)
    with pytest.raises(TypeError, match="'conventions' must be a string"):
        nz.validate_group_metadata(node)  # type: ignore[arg-type]


def test_group_conventions_identifier_must_be_a_whole_token() -> None:
    """Stricter than upstream: the schema's pattern is an unanchored search."""
    node = _valid_group()
    node["attributes"]["conventions"] = "NZ-1.01"
    assert schema_accepts(node)
    with pytest.raises(ValueError, match="must list 'NZ-1.0'"):
        nz.validate_group_metadata(node)  # type: ignore[arg-type]


def test_array_missing_dimension_names_rejected() -> None:
    node = _valid_array()
    del node["dimension_names"]
    assert not schema_accepts(node)
    with pytest.raises(ValueError, match="'dimension_names' is required on arrays"):
        nz.validate_array_metadata(node)  # type: ignore[arg-type]


def test_array_dimension_names_wrong_type_rejected() -> None:
    node = _valid_array()
    node["dimension_names"] = "time lat lon"
    assert not schema_accepts(node)
    with pytest.raises(TypeError, match="'dimension_names' must be a JSON array"):
        nz.validate_array_metadata(node)  # type: ignore[arg-type]


def test_array_null_dimension_name_rejected() -> None:
    node = _valid_array()
    node["dimension_names"] = ["time", None, "lon"]
    assert not schema_accepts(node)
    with pytest.raises(TypeError, match="'dimension_names' entries must be strings"):
        nz.validate_array_metadata(node)  # type: ignore[arg-type]


def test_array_empty_dimension_name_rejected() -> None:
    node = _valid_array()
    node["dimension_names"] = ["time", "", "lon"]
    assert not schema_accepts(node)
    with pytest.raises(ValueError, match="entries must not be empty"):
        nz.validate_array_metadata(node)  # type: ignore[arg-type]


def test_array_dimension_names_length_mismatch_rejected() -> None:
    """Stricter than upstream: the spec requires it, the schema does not check."""
    node = _valid_array()
    node["dimension_names"] = ["lat", "lon"]
    assert schema_accepts(node)
    with pytest.raises(ValueError, match="one entry per axis of 'shape'"):
        nz.validate_array_metadata(node)  # type: ignore[arg-type]


def test_array_missing_shape_rejected() -> None:
    node = _valid_array()
    del node["shape"]
    assert not schema_accepts(node)
    with pytest.raises(ValueError, match="'shape' is required"):
        nz.validate_array_metadata(node)  # type: ignore[arg-type]


def test_array_shape_wrong_type_rejected() -> None:
    node = _valid_array()
    node["shape"] = 10
    assert not schema_accepts(node)
    with pytest.raises(TypeError, match="'shape' must be a JSON array"):
        nz.validate_array_metadata(node)  # type: ignore[arg-type]


def test_array_shape_non_integer_rejected() -> None:
    node = _valid_array()
    node["shape"] = [8760, 721.5, 1440]
    assert not schema_accepts(node)
    with pytest.raises(TypeError, match="'shape' entries must be integers"):
        nz.validate_array_metadata(node)  # type: ignore[arg-type]


def test_array_shape_negative_rejected() -> None:
    node = _valid_array()
    node["shape"] = [8760, -1, 1440]
    assert not schema_accepts(node)
    with pytest.raises(ValueError, match="'shape' entries must be non-negative"):
        nz.validate_array_metadata(node)  # type: ignore[arg-type]


# --- composition ---------------------------------------------------------------------


def test_composes_with_other_conventions() -> None:
    """`conventions` and `_FillValue` sit alongside namespaced conventions."""
    attrs = zarr_cm.create_many(
        {
            "nz": {"conventions": "NZ-1.0 CF-1.12"},
            "license": {"spdx": "CC-BY-4.0"},
        }
    )
    assert zarr_cm.detect_revisions(attrs) == {"nz": "v1", "license": "v1"}
    remaining, extracted = zarr_cm.extract_all(attrs)
    assert remaining == {}
    assert extracted == {
        "nz": {"conventions": "NZ-1.0 CF-1.12"},
        "license": {"spdx": "CC-BY-4.0"},
    }
