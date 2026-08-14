# Composition

This example demonstrates the workflow every GeoZarr writer performs:
several conventions composed on one node, placement split across group and
array documents, and validation of whole `zarr.json` documents. It mirrors
how real adopters (GDAL, rio-tiler, rioxarray, tile servers) lay out
convention metadata.

The example shows how to:

- Compose proj, spatial, and multiscales into a single attributes dict with
  `create_many`, which validates each convention and merges their
  declarations into one `zarr_conventions` array
- Embed per-level `spatial:shape` / `spatial:transform` overrides inside the
  multiscales layout — the composition tile readers use to pick a resolution
  level
- Follow the placement adopters use: `proj:` and `multiscales` on the group,
  each array carrying its own `spatial:` grid
- Validate complete group and array metadata documents with the node-level
  validators, which enforce the rules attribute-level validation cannot see:
  arrays must carry `spatial:dimensions`, and `multiscales` is rejected on
  array nodes

## Running the Example

From the repository root, [uv](https://docs.astral.sh/uv/) runs the script in
the project environment, installing zarr-cm on the way in:

```bash
uv run examples/composition/composition.py
```

Alternatively, run it with plain Python in any environment where `zarr-cm` is
installed:

```bash
python examples/composition/composition.py
```

Every example prints a trace of what it does and ends with `OK`; the test suite
runs them all and asserts exactly that (`tests/test_examples.py`).
