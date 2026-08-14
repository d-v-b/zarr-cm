# Proj

This example demonstrates the full lifecycle of the
[proj](https://github.com/zarr-conventions/proj) convention, which carries
coordinate reference system information (`proj:code`, `proj:wkt2`,
`proj:projjson`).

The example shows how to:

- Create a stand-alone attributes dict at the latest revision with
  `proj.create_convention_attrs`
- Detect the revision a stored document was written under with `proj.detect`,
  and refuse automatic extraction when the revision is unrecognized
- Migrate a document from r2 to the latest revision, observing that the
  commit-pinned `schema_url` changes while the data fields survive unchanged
- Use a relaxation in the latest revision: r3 accepts `proj:code` values that
  r2's stricter authority pattern rejected

## Running the Example

From the repository root, [uv](https://docs.astral.sh/uv/) runs the script in
the project environment, installing zarr-cm on the way in:

```bash
uv run examples/proj/proj.py
```

Alternatively, run it with plain Python in any environment where `zarr-cm` is
installed:

```bash
python examples/proj/proj.py
```

Every example prints a trace of what it does and ends with `OK`; the test suite
runs them all and asserts exactly that (`tests/test_examples.py`).
