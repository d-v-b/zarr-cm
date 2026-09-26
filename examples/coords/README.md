# Coords

This example demonstrates the
[coords](https://github.com/christophenoel/zarr-coords) convention, which maps
each dimension of a Zarr array to a coordinate descriptor saying how its
coordinate values are represented and where they live.

The example shows how to:

- Create a stand-alone attributes dict with `coords.create_convention_attrs`,
  using `array`, `inline` and `reference` descriptors
- Validate an array document with `coords.validate_node_metadata`, which checks
  the keys against the array's `dimension_names`
- Declare auxiliary coordinates (`lat(y, x)`) with `indexed_by`
- Describe regularly spaced axes with `interval` descriptors, numeric or
  ISO 8601
- Use `coords:coordinates` on a group as a catalogue for its child arrays

## Running the Example

From the repository root, [uv](https://docs.astral.sh/uv/) runs the script in
the project environment, installing zarr-cm on the way in:

```bash
uv run examples/coords/coords.py
```

Alternatively, run it with plain Python in any environment where `zarr-cm` is
installed:

```bash
python examples/coords/coords.py
```

Every example prints a trace of what it does and ends with `OK`; the test suite
runs them all and asserts exactly that (`tests/test_examples.py`).
