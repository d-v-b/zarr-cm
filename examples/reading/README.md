# Reading

This example demonstrates the reader-side workflow that consuming tools — GDAL,
rio-tiler, rioxarray, OpenLayers — perform on convention metadata they did not
write, including documents from the wild that declare revisions this library
does not recognize.

The example shows how to:

- Detect whether a convention is declared by matching its **UUID** in
  `zarr_conventions` — the convention's permanent identity. (Names and schema
  URLs have both changed over the conventions' history; some deployed readers
  match by name, which those changes can break.)
- Detect the declared revision with `spatial.detect`, and validate under it when
  it is recognized
- Read defensively when the revision is unrecognized: interpret keys directly,
  applying the defaults the spec defines (`spatial:registration` defaults to
  `"pixel"`, `spatial:transform_type` to `"affine"`) and the proj convention's
  `wkt2` → `code` → `projjson` fallback order
- Skip cleanly when the convention is not declared at all

The unrecognized-revision document is not hypothetical: the draft-era convention
specs published example declarations with a `refs/tags/v1` schema URL that was
never released (the specs shipped as `v0.1`), and tools that integrated during
that window write documents carrying it today.

## Running the Example

From the repository root, [uv](https://docs.astral.sh/uv/) runs the script in
the project environment, installing zarr-cm on the way in:

```bash
uv run examples/reading/reading.py
```

Alternatively, run it with plain Python in any environment where `zarr-cm` is
installed:

```bash
python examples/reading/reading.py
```

Every example prints a trace of what it does and ends with `OK`; the test suite
runs them all and asserts exactly that (`tests/test_examples.py`).
