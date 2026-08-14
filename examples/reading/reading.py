"""Example: reading convention metadata the way consumers must.

Run: `python examples/reading/reading.py`. Demonstrates the reader-side
workflow tools like GDAL, rio-tiler, and rioxarray perform: detect whether a
convention is declared, then interpret its keys -- including documents written
by tools that declare revisions this library does not recognize.
"""

from __future__ import annotations

from typing import Any

from zarr_cm import proj, spatial


def stored_documents() -> dict[str, dict[str, Any]]:
    """Three attribute dicts as they might arrive from stores in the wild."""
    current = spatial.create_convention_attrs(
        dimensions=["y", "x"], registration="node"
    )
    # Several deployed writers copied the draft-era spec examples, which
    # declared a `refs/tags/v1` schema_url that was never released; documents
    # carrying it exist in the wild today.
    legacy = {
        "zarr_conventions": [
            {
                "uuid": spatial.UUID,
                "name": "spatial:",
                "schema_url": "https://raw.githubusercontent.com/zarr-conventions/spatial/refs/tags/v1/schema.json",
            }
        ],
        "spatial:dimensions": ["y", "x"],
        "spatial:transform": [30.0, 0.0, 323400.0, 0.0, -30.0, 4268400.0],
    }
    plain = {"description": "no conventions here"}
    return {"current": dict(current), "legacy": legacy, "plain": plain}


def declares_spatial(attrs: dict[str, Any]) -> bool:
    """1. Presence detection, by UUID.

    The UUID is the convention's permanent identity; names and schema_urls
    have both changed over the conventions' history, so match on the UUID.
    """
    conventions = attrs.get("zarr_conventions") or []
    return any(
        isinstance(cmo, dict) and cmo.get("uuid") == spatial.UUID for cmo in conventions
    )


def read_defensively(attrs: dict[str, Any]) -> None:
    """3. Interpret keys without validating, applying the spec's defaults.

    For documents whose revision this library does not recognize, read the
    keys directly and fall back to the defaults the spec defines:
    `spatial:registration` defaults to "pixel" and `spatial:transform_type`
    to "affine". The proj convention's own fallback order is wkt2, then code,
    then projjson.
    """
    dimensions = attrs.get("spatial:dimensions")
    registration = attrs.get("spatial:registration", "pixel")
    transform_type = attrs.get("spatial:transform_type", "affine")
    print(
        f"[read] dimensions={dimensions} registration={registration!r} "
        f"transform_type={transform_type!r}"
    )
    for key in ("proj:wkt2", "proj:code", "proj:projjson"):
        if key in attrs:
            print(f"[read] crs from {key}")
            break
    else:
        print(f"[read] no crs on this node (checked {proj.UUID[:8]}... keys)")


def read(name: str, attrs: dict[str, Any]) -> None:
    """2. The full reader flow for one stored document."""
    print(f"--- {name}")
    if not declares_spatial(attrs):
        print("[read] spatial not declared; nothing to interpret")
        return

    revision = spatial.detect(attrs)
    if revision is None:
        print("[read] declared at an unrecognized revision; reading defensively")
        read_defensively(attrs)
        return

    print(f"[read] recognized revision {revision!r}; validating")
    data = spatial.validate(dict(attrs), revision=revision)
    print(f"[read] validated: dimensions={data.get('spatial:dimensions')}")


if __name__ == "__main__":
    for name, attrs in stored_documents().items():
        read(name, attrs)
    print("OK")
