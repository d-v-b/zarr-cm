# Ref

This example demonstrates the
[ref](https://github.com/R-CF/zarr_convention_ref) convention, which references
an external Zarr node (array or group), or an item in its `zarr.json`, from the
attributes of an array or group.

The example shows how to:

- Create references with `ref.create_convention_attrs`: to a sibling node (a
  path relative to the referencing node), to an attribute of the parent group
  (an RFC 6901 JSON pointer), and to a node in another store (a `uri` plus an
  absolute path)
- Validate a whole node document with `ref.validate_node_metadata` and read the
  reference back with `ref.extract`
- Recognize a document written against the upstream `v1` tag, whose
  `array`/`group` fields were replaced by `node`

## Running the Example

From the repository root, [uv](https://docs.astral.sh/uv/) runs the script in
the project environment, installing zarr-cm on the way in:

```bash
uv run examples/ref/ref.py
```

Alternatively, run it with plain Python in any environment where `zarr-cm` is
installed:

```bash
python examples/ref/ref.py
```

Every example prints a trace of what it does and ends with `OK`; the test suite
runs them all and asserts exactly that (`tests/test_examples.py`).
