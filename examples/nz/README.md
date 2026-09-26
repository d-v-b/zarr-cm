# NZ

This example demonstrates the [nz](https://github.com/zarr-conventions/nz)
convention (NZ-1.0, "NetCDF - Zarr Convention"), the structural layer that lets
netCDF-style domain conventions such as CF apply to Zarr v3 data.

The example shows how to:

- Declare `NZ-1.0` in a root group's `conventions` attribute alongside another
  identifier (`"NZ-1.0 CF-1.12"`), composed with another convention through
  `zarr_cm.insert_many`
- Mark an array's semantic missing value with `_FillValue`, distinct from the
  storage-level `fill_value`
- Validate whole `zarr.json` documents: a group must carry `conventions` listing
  `NZ-1.0`, and an array must carry a fully populated `dimension_names`, one
  non-empty name per axis of `shape`

Unlike the other conventions, NZ-1.0's attributes are not namespaced:
`conventions` and `_FillValue` are the plain netCDF names. The rules that span
several nodes -- arrays in a group that share a dimension label must share its
length, and identifying dimension coordinate arrays -- are outside what
`zarr-cm` checks, since it works on one document at a time.

## Running the Example

From the repository root, [uv](https://docs.astral.sh/uv/) runs the script in
the project environment, installing zarr-cm on the way in:

```bash
uv run examples/nz/nz.py
```

Alternatively, run it with plain Python in any environment where `zarr-cm` is
installed:

```bash
python examples/nz/nz.py
```

Every example prints a trace of what it does and ends with `OK`; the test suite
runs them all and asserts exactly that (`tests/test_examples.py`).
