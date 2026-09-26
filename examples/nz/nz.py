"""Example: the nz (NZ-1.0, NetCDF - Zarr) convention.

Run: `python examples/nz/nz.py`. Declares NZ-1.0 on a root group alongside
another convention, marks an array's semantic missing value, and shows the
node-level rules: groups need `conventions`, arrays need `dimension_names`.
"""

from __future__ import annotations

from typing import Any

import zarr_cm
from zarr_cm import nz


def workflow_root_group() -> dict[str, Any]:
    """1. Declare NZ-1.0 (and CF) on a root group, next to a license."""
    attrs = zarr_cm.insert_many(
        {"title": "Example dataset"},
        {
            "nz": nz.create(conventions="NZ-1.0 CF-1.12"),
            "license": {"spdx": "CC-BY-4.0"},
        },
    )
    group = {"zarr_format": 3, "node_type": "group", "attributes": attrs}
    nz.validate_group_metadata(group)  # type: ignore[arg-type]
    print(f"[group] conventions = {attrs['conventions']!r}")
    print(f"[group] detected revisions = {zarr_cm.detect_revisions(attrs)}")
    return group


def workflow_array() -> dict[str, Any]:
    """2. An array with a semantic `_FillValue` and named dimensions."""
    array = {
        "zarr_format": 3,
        "node_type": "array",
        "shape": [365, 180, 360],
        "data_type": "float32",
        "dimension_names": ["time", "lat", "lon"],
        "chunk_grid": {
            "name": "regular",
            "configuration": {"chunk_shape": [30, 180, 360]},
        },
        "chunk_key_encoding": {"name": "default"},
        "fill_value": 0.0,
        "codecs": [{"name": "bytes", "configuration": {"endian": "little"}}],
        "attributes": nz.create_convention_attrs(fill_value=-9999.0),
    }
    nz.validate_array_metadata(array)  # type: ignore[arg-type]
    _, data = nz.extract(array["attributes"])
    print(f"[array] _FillValue = {data['_FillValue']!r} (storage fill_value = 0.0)")
    return array


def workflow_rejections(group: dict[str, Any], array: dict[str, Any]) -> None:
    """3. What a single node's metadata can get wrong."""
    no_dims = {k: v for k, v in array.items() if k != "dimension_names"}
    try:
        nz.validate_array_metadata(no_dims)  # type: ignore[arg-type]
    except ValueError as exc:
        print(f"[reject] array: {exc}")
    wrong = {**group, "attributes": {**group["attributes"], "conventions": "CF-1.12"}}
    try:
        nz.validate_group_metadata(wrong)  # type: ignore[arg-type]
    except ValueError as exc:
        print(f"[reject] group: {exc}")


if __name__ == "__main__":
    root = workflow_root_group()
    temperature = workflow_array()
    workflow_rejections(root, temperature)
    print("OK")
