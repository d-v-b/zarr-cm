"""Example: the cs (coordinate set) convention.

Run: `python examples/cs/cs.py`. Demonstrates a group sharing named CRS objects,
an array referencing them, an array with an inline coordinate set, and the
node-level rules (`dimension_names` must be set, and every dimension needs an
axis).
"""

from __future__ import annotations

from typing import Any

from zarr_cm import CsCrs, cs

WGS84: CsCrs = {
    "type": "planar",
    "axes": {
        "lon": {
            "abbreviation": "X",
            "coordinates": [
                {
                    "direction": "east",
                    "unit": "degrees",
                    "values": {"regular": [-179.75, 0.5]},
                }
            ],
        },
        "lat": {
            "abbreviation": "Y",
            "coordinates": [
                {
                    "direction": "north",
                    "unit": "degrees",
                    "values": {"regular": [-89.75, 0.5]},
                }
            ],
        },
    },
    "id": {"proj:code": "EPSG:4326"},
}

CALENDAR: CsCrs = {
    "type": "temporal",
    "axes": {
        "time": {
            "abbreviation": "T",
            "coordinates": [
                {
                    "direction": "future",
                    "time": {"unit": "day", "epoch": "1900-01-01"},
                    # irregular time steps live in a sibling array
                    "values": {"external": {"ref": {"node": "../time"}}},
                }
            ],
        }
    },
}

_ARRAY_SHELL: dict[str, Any] = {
    "zarr_format": 3,
    "node_type": "array",
    "shape": [1464, 360, 720],
    "data_type": "float32",
    "chunk_grid": {
        "name": "regular",
        "configuration": {"chunk_shape": [12, 360, 720]},
    },
    "chunk_key_encoding": {"name": "default"},
    "fill_value": 0.0,
    "codecs": [{"name": "bytes"}],
}


def workflow_shared_crs() -> None:
    """1. A group defines named CRS objects; an array references them."""
    group: dict[str, Any] = {
        "zarr_format": 3,
        "node_type": "group",
        "attributes": cs.create_convention_attrs(
            crs={"WGS84": WGS84, "standard_calendar": CALENDAR}
        ),
    }
    cs.validate_node_metadata(group)
    print(f"[group] crs objects: {sorted(group['attributes']['crs'])}")

    array: dict[str, Any] = {
        **_ARRAY_SHELL,
        "dimension_names": ["time", "lat", "lon"],
        "attributes": cs.create_convention_attrs(
            cs={
                "crs": [
                    {"node": "..", "attribute": "/attributes/crs/WGS84"},
                    {"node": "..", "attribute": "/attributes/crs/standard_calendar"},
                ]
            }
        ),
    }
    cs.validate_node_metadata(array)
    print("[array] references both CRS objects on its parent group")


def workflow_inline_and_extract() -> None:
    """2. An inline coordinate set, added to existing attributes and read back."""
    data = cs.create(cs={"name": "CRU monthly", "crs": [WGS84, CALENDAR]})
    attrs = cs.insert({"long_name": "near-surface temperature"}, data)
    print(f"[insert] revision = {cs.detect(attrs)}")
    remaining, extracted = cs.extract(attrs)
    assert extracted == data
    print(f"[extract] other attributes: {remaining}")


def workflow_node_rules() -> None:
    """3. Array rules: `dimension_names` must be set, and each needs an axis."""
    attrs = cs.create_convention_attrs(cs={"crs": [WGS84, CALENDAR]})
    for dimension_names in (None, ["time", "lat", "lon", "band"]):
        array: dict[str, Any] = {**_ARRAY_SHELL, "attributes": attrs}
        if dimension_names is not None:
            array["dimension_names"] = dimension_names
        try:
            cs.validate_node_metadata(array)
        except ValueError as exc:
            print(f"[rules] rejected: {exc}")


if __name__ == "__main__":
    workflow_shared_crs()
    workflow_inline_and_extract()
    workflow_node_rules()
    print("OK")
