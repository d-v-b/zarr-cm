# License

This example demonstrates the
[license](https://github.com/clbarnes/zarr-convention-license) convention,
which attaches a license specifier (SPDX identifier, URL, or text) to a Zarr
node.

The example shows how to:

- Create a stand-alone attributes dict with `license.create_convention_attrs`
- Detect the revision of a stored document with `license.detect`
- Handle a document declaring an unrecognized `schema_url` defensively
- Scaffold a migration: license has a single revision today, so the migrate
  step is an identity re-stamp, written the way a real cross-revision
  migration would be

## Running the Example

From the repository root, [uv](https://docs.astral.sh/uv/) runs the script in
the project environment, installing zarr-cm on the way in:

```bash
uv run examples/license/license.py
```

Alternatively, run it with plain Python in any environment where `zarr-cm` is
installed:

```bash
python examples/license/license.py
```

Every example prints a trace of what it does and ends with `OK`; the test suite
runs them all and asserts exactly that (`tests/test_examples.py`).
