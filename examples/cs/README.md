# cs

This example demonstrates the [cs](https://github.com/R-CF/zarr_conventions_cs)
(coordinate set) convention, which attaches axes and coordinate values to the
dimensions of a Zarr array.

The example shows how to:

- Define named CRS objects on a group with `cs.create_convention_attrs(crs=...)`
- Reference those CRS objects from an array's `cs` object, by node path and
  JSON pointer
- Add an inline coordinate set to existing attributes with `cs.insert`, and read
  it back with `cs.extract`
- Check the array-level rules with `validate_node_metadata`: `dimension_names`
  must be set, and when every CRS is inline, each dimension needs an axis

The convention uses one attribute key per node type: `cs` on arrays, `crs` on
groups. References are carried and checked for shape only; resolving them
against the rest of the store is the caller's job, since `zarr-cm` works on one
metadata document at a time and does no store I/O.

## Running the Example

From the repository root, [uv](https://docs.astral.sh/uv/) runs the script in
the project environment, installing zarr-cm on the way in:

```bash
uv run examples/cs/cs.py
```

Alternatively, run it with plain Python in any environment where `zarr-cm` is
installed:

```bash
python examples/cs/cs.py
```

Every example prints a trace of what it does and ends with `OK`; the test suite
runs them all and asserts exactly that (`tests/test_examples.py`).
