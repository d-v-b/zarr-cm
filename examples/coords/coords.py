"""Example: the coords convention.

Run: `python examples/coords/coords.py`. Demonstrates create with each
descriptor type / node-level checks against `dimension_names` / a group-level
catalogue.
"""

from __future__ import annotations

from typing import Any

from zarr_cm import coords


def workflow_create() -> dict[str, Any]:
    """1. Map each dimension of a (time, band, y, x) cube to a descriptor."""
    attrs = coords.create_convention_attrs(
        coordinates={
            # an explicit 1-D coordinate array next to this one
            "time": {"type": "array", "path": "../time"},
            # a short spectral axis, inline
            "band": {"type": "inline", "values": [0.490, 0.560, 0.665, 0.842]},
            # y / x come from the `spatial` convention's affine transform
            "y": {"type": "reference", "convention": "spatial"},
            "x": {"type": "reference", "convention": "spatial"},
        },
        version=1,
    )
    print(f"[create] wrote coords data; revision = {coords.detect(attrs)}")
    return attrs


def workflow_array_node(attrs: dict[str, Any]) -> None:
    """2. On an array, every key must name one of its `dimension_names`."""
    doc: dict[str, Any] = {
        "zarr_format": 3,
        "node_type": "array",
        "dimension_names": ["time", "band", "y", "x"],
        "attributes": attrs,
    }
    coords.validate_node_metadata(doc)
    print("[array] keys match dimension_names: document validates")

    mismatched = {**doc, "dimension_names": ["time", "wavelength", "y", "x"]}
    try:
        coords.validate_node_metadata(mismatched)
    except ValueError as exc:
        print(f"[array] mismatched key rejected: {exc}")


def workflow_auxiliary() -> None:
    """3. Auxiliary coordinates: `indexed_by` frees the key from the dimensions.

    On a curvilinear grid, `lat(y, x)` and `lon(y, x)` are keyed by their own
    names; it is their `indexed_by` entries that must be dimension names.
    """
    doc: dict[str, Any] = {
        "zarr_format": 3,
        "node_type": "array",
        "dimension_names": ["y", "x"],
        "attributes": coords.create_convention_attrs(
            coordinates={
                "lat": {"type": "array", "path": "../lat", "indexed_by": ["y", "x"]},
                "lon": {"type": "array", "path": "../lon", "indexed_by": ["y", "x"]},
            }
        ),
    }
    coords.validate_node_metadata(doc)
    print("[auxiliary] lat(y, x) / lon(y, x) validate")


def workflow_interval() -> None:
    """4. Regularly spaced axes, numeric or ISO 8601, without enumerating them."""
    data = coords.create(
        coordinates={
            "time": {
                "type": "interval",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-31T00:00:00Z",
                "step": "P1D",
            },
            "azimuth": {"type": "interval", "start": 0, "end": 360, "step": 15},
        }
    )
    print(f"[interval] {sorted(data['coords:coordinates'])} validate")
    try:
        coords.validate(
            {
                "coords:coordinates": {
                    "azimuth": {"type": "interval", "start": 0, "end": 360, "step": 0}
                }
            }
        )
    except ValueError as exc:
        print(f"[interval] zero step rejected: {exc}")


def workflow_group_catalogue() -> None:
    """5. On a group, the map is a catalogue for child arrays: keys go unchecked."""
    doc: dict[str, Any] = {
        "zarr_format": 3,
        "node_type": "group",
        "attributes": coords.create_convention_attrs(
            coordinates={"time": {"type": "array", "path": "time"}}
        ),
    }
    coords.validate_node_metadata(doc)
    print("[group] catalogue validates")


if __name__ == "__main__":
    workflow_array_node(workflow_create())
    workflow_auxiliary()
    workflow_interval()
    workflow_group_catalogue()
    print("OK")
