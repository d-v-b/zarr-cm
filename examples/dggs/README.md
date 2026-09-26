# Dggs

This example demonstrates the [dggs](https://github.com/zarr-conventions/dggs)
convention, which describes the discrete global grid system (DGGS) -- such as
HEALPix or H3 -- that a Zarr group or array is laid out on.

The example shows how to:

- Create a stand-alone attributes dict with `dggs.create_convention_attrs`, for
  a HEALPix subdomain on the WGS84 ellipsoid
- See a spec rule enforced on the way in (HEALPix `nested` levels stop at 29)
- Detect the revision of a stored document with `dggs.detect`, and fall back to
  the spec's default sphere when no `ellipsoid` is given
- Scaffold a migration: dggs has a single revision today, so the migrate step is
  an identity re-stamp, written the way a real cross-revision migration would be

## Running the Example

From the repository root, [uv](https://docs.astral.sh/uv/) runs the script in
the project environment, installing zarr-cm on the way in:

```bash
uv run examples/dggs/dggs.py
```

Alternatively, run it with plain Python in any environment where `zarr-cm` is
installed:

```bash
python examples/dggs/dggs.py
```

Every example prints a trace of what it does and ends with `OK`; the test suite
runs them all and asserts exactly that (`tests/test_examples.py`).
