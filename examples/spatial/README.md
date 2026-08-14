# Spatial

This example demonstrates the full lifecycle of the
[spatial](https://github.com/zarr-conventions/spatial) convention, which
describes the relationship between array indices and spatial coordinates.

The example shows how to:

- Create a stand-alone attributes dict at the latest revision with
  `spatial.create_convention_attrs` (dimensions and a bounding box)
- Detect the revision a stored document was written under with
  `spatial.detect`, and refuse automatic extraction when the revision is
  unrecognized
- Read a document written under an older revision by pinning `revision=` on
  `spatial.extract` and `spatial.validate`
- Migrate a document from r2 to the latest revision by extracting under the
  source revision and re-creating under the target one

## Running the Example

From the repository root, [uv](https://docs.astral.sh/uv/) runs the script in
the project environment, installing zarr-cm on the way in:

```bash
uv run examples/spatial/spatial.py
```

Alternatively, run it with plain Python in any environment where `zarr-cm` is
installed:

```bash
python examples/spatial/spatial.py
```

Every example prints a trace of what it does and ends with `OK`; the test suite
runs them all and asserts exactly that (`tests/test_examples.py`).
