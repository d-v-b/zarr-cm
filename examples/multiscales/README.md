# Multiscales

This example demonstrates the
[multiscales](https://github.com/zarr-conventions/multiscales) convention,
which records the layout of a multiscale image pyramid on a Zarr group.

The example shows how to:

- Create a stand-alone attributes dict with
  `multiscales.create_convention_attrs`, describing a two-level layout
- Detect the revision of a stored document with `multiscales.detect`
- Handle a document declaring an unrecognized `schema_url` defensively:
  detection reports it rather than validating it as something it is not
- Round-trip the data through `multiscales.extract` and re-insertion

Multiscales currently ships a single revision (r2, at upstream v0.1), so
there is no cross-revision migration to show.

## Running the Example

From the repository root, [uv](https://docs.astral.sh/uv/) runs the script in
the project environment, installing zarr-cm on the way in:

```bash
uv run examples/multiscales/multiscales.py
```

Alternatively, run it with plain Python in any environment where `zarr-cm` is
installed:

```bash
python examples/multiscales/multiscales.py
```

Every example prints a trace of what it does and ends with `OK`; the test suite
runs them all and asserts exactly that (`tests/test_examples.py`).
