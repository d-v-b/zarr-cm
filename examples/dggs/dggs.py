"""Example: the dggs (Discrete Global Grid Systems) convention.

Run: `python examples/dggs/dggs.py`. Demonstrates create / read-unknown /
migrate. Dggs has a single revision today (identity migrate scaffold).
"""

from __future__ import annotations

from typing import Any

from zarr_cm import dggs


def workflow_create() -> dict[str, Any]:
    """1. Create new dggs data: a HEALPix subdomain on the WGS84 ellipsoid."""
    attrs = dggs.create_convention_attrs(
        name="healpix",
        refinement_level=10,
        indexing_scheme="nested",
        spatial_dimension="cells",
        ellipsoid={
            "name": "WGS84",
            "semi_major_axis": 6378137.0,
            "inverse_flattening": 298.257223563,
        },
        coordinate="cell_ids",
        compression="none",
    )
    print(f"[create] wrote dggs data; revision = {dggs.detect(attrs)}")

    # The spec's rules are checked on the way in: a HEALPix "nested" grid
    # stops at refinement level 29.
    try:
        dggs.create(
            name="healpix",
            refinement_level=30,
            indexing_scheme="nested",
            spatial_dimension="cells",
        )
    except ValueError as err:
        print(f"[create] rejected: {err}")
    return attrs


def workflow_read_unknown() -> None:
    """2. Read dggs data, branching on the detected revision."""
    doc = dggs.create_convention_attrs(
        name="h3", refinement_level=5, spatial_dimension="cell"
    )
    rev = dggs.detect(doc)
    print(f"[read] detected revision {rev!r}")
    _, data = dggs.extract(doc)
    if rev is None:
        print(f"[read] unknown revision; raw fields: {dict(data)}")
    else:
        dggs.validate(dict(data))
        # No ellipsoid means the spec's default sphere.
        radius = data.get("ellipsoid", {}).get("radius", dggs.DEFAULT_RADIUS)
        print(f"[read] validated under {rev!r}: {data['name']}, radius {radius} m")


def workflow_migrate() -> None:
    """3. Identity migration scaffold (one revision today)."""
    doc = workflow_create()
    rev = dggs.detect(doc)
    _, old = dggs.extract(doc)
    migrated = dggs.insert({}, dggs.validate(dict(old)))
    print(f"[migrate] {rev} -> {dggs.detect(migrated)} (identity; single revision)")


if __name__ == "__main__":
    workflow_read_unknown()
    workflow_migrate()
    print("OK")
