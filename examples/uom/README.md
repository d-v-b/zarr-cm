# Uom

This example demonstrates the
[uom](https://github.com/clbarnes/zarr-convention-uom) convention, which
records units of measurement for a Zarr array as UCUM codes.

The example shows how to:

- Create a stand-alone attributes dict with `uom.create_convention_attrs`,
  carrying a UCUM unit
- Detect the revision of a stored document with `uom.detect`
- Handle a document declaring an unrecognized `schema_url` defensively
- Scaffold a migration: uom has a single revision today, so the migrate step
  is an identity re-stamp, written the way a real cross-revision migration
  would be

## Running the Example

From the repository root, [uv](https://docs.astral.sh/uv/) runs the script in
the project environment, installing zarr-cm on the way in:

```bash
uv run examples/uom/uom.py
```

Alternatively, run it with plain Python in any environment where `zarr-cm` is
installed:

```bash
python examples/uom/uom.py
```

Every example prints a trace of what it does and ends with `OK`; the test suite
runs them all and asserts exactly that (`tests/test_examples.py`).
