"""Example: composing several conventions on real metadata documents.

Run: `python examples/composition/composition.py`. Demonstrates the workflow
every GeoZarr writer performs: several conventions on one node, split across
group and array documents, validated as whole `zarr.json` documents.
"""

from __future__ import annotations

import json
from typing import Any

from zarr_cm import create_many, multiscales, proj, spatial, validate_all


def build_group_attrs() -> dict[str, Any]:
    """1. Compose proj + spatial + multiscales into one attributes dict.

    Real writers declare several conventions on the same node; `create_many`
    validates each convention's data and merges their declarations into a
    single `zarr_conventions` array.
    """
    attrs = create_many(
        {
            "geo-proj": {"proj:code": "EPSG:4326"},
            "spatial": {
                "spatial:dimensions": ["y", "x"],
                "spatial:bbox": [-180.0, -90.0, 180.0, 90.0],
            },
            "multiscales": {
                # Per-level spatial: overrides inside the layout: the spatial
                # convention defines this composition, and tile readers use it
                # to pick a resolution level.
                "layout": [
                    {
                        "asset": "0",
                        "spatial:shape": [1024, 2048],
                        "spatial:transform": [0.17, 0.0, -180.0, 0.0, -0.17, 90.0],
                    },
                    {
                        "asset": "1",
                        "derived_from": "0",
                        "transform": {"scale": [2.0, 2.0]},
                        "spatial:shape": [512, 1024],
                        "spatial:transform": [0.35, 0.0, -180.0, 0.0, -0.35, 90.0],
                    },
                ],
                "resampling_method": "average",
            },
        }
    )
    declared = sorted(c["name"] for c in attrs["zarr_conventions"])
    print(f"[group] one attributes dict declares: {declared}")
    validate_all(attrs)
    print("[group] validate_all: every declared convention checks out")
    return attrs


def build_array_attrs() -> dict[str, Any]:
    """2. Give the array node its own spatial grid.

    Following the GeoZarr placement convention adopters use: `proj:` lives on
    the group; the per-array grid (`spatial:transform`, `spatial:shape`) lives
    on each array.
    """
    attrs = spatial.create_convention_attrs(
        dimensions=["y", "x"],
        shape=[1024, 2048],
        transform=[0.17, 0.0, -180.0, 0.0, -0.17, 90.0],
    )
    print("[array] spatial grid on the array node itself")
    return attrs


def validate_documents(
    group_attrs: dict[str, Any], array_attrs: dict[str, Any]
) -> None:
    """3. Assemble and validate whole `zarr.json` documents.

    The node-level validators see `node_type`, so they enforce what
    attribute-level validation cannot: `multiscales` applies to groups only,
    and arrays must carry `spatial:dimensions`.
    """
    group_doc = {"zarr_format": 3, "node_type": "group", "attributes": group_attrs}
    array_doc = {
        "zarr_format": 3,
        "node_type": "array",
        "data_type": "float64",
        "shape": [1024, 2048],
        "chunk_grid": {"name": "regular", "configuration": {"chunk_shape": [256, 256]}},
        "chunk_key_encoding": {"name": "default"},
        "fill_value": 0.0,
        "codecs": [{"name": "bytes"}],
        "attributes": array_attrs,
    }

    for convention in (proj, spatial, multiscales):
        convention.validate_group_metadata(group_doc)
    print("[node] group document valid under proj, spatial, and multiscales")

    spatial.validate_array_metadata(array_doc)
    print("[node] array document valid under spatial")

    # The group-only rule: the same attributes that validate on the group are
    # rejected when the node claims to be an array.
    mislabeled = {**array_doc, "attributes": group_attrs}
    try:
        multiscales.validate_array_metadata(mislabeled)
    except ValueError as exc:
        print(f"[node] multiscales on an array is rejected: {exc}")

    print("[node] the group zarr.json, ready to write:")
    print(json.dumps(group_doc, indent=2)[:220] + " ...")


if __name__ == "__main__":
    group = build_group_attrs()
    array = build_array_attrs()
    validate_documents(group, array)
    print("OK")
