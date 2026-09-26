"""Example: the ref (external reference) convention.

Run: `python examples/ref/ref.py`. Demonstrates referencing a sibling node,
an attribute of the parent group, and a node in another store; reading a
reference back; and rejecting a document written against the superseded
upstream `v1` tag. Ref applies to arrays and groups alike.
"""

from __future__ import annotations

from typing import Any

from zarr_cm import ref


def workflow_create() -> list[dict[str, Any]]:
    """1. Create references of each kind."""
    sibling = ref.create_convention_attrs(node="../sibling_array")
    parent_attr = ref.create_convention_attrs(
        node="..", attribute="/attributes/interesting_thing"
    )
    external = ref.create_convention_attrs(
        uri="https://data.earthdatahub.destine.eu/public/test-dataset-v0.zarr",
        node="/year",
    )
    for attrs in (sibling, parent_attr, external):
        print(f"[create] ref = {attrs['ref']}; revision = {ref.detect(attrs)}")
    return [sibling, parent_attr, external]


def workflow_read(docs: list[dict[str, Any]]) -> None:
    """2. Read a reference back out of a node's attributes."""
    for attrs in docs:
        node: Any = {"zarr_format": 3, "node_type": "group", "attributes": attrs}
        ref.validate_node_metadata(node)
        _, data = ref.extract(attrs)
        where = f"store {data['uri']!r}" if "uri" in data else "this store"
        item = f", item {data['attribute']!r}" if "attribute" in data else ""
        print(f"[read] node {data['node']!r}{item} in {where}")


def workflow_reject_v1() -> None:
    """3. The upstream `v1` tag's `array`/`group` fields are not valid today."""
    attrs: Any = {"zarr_conventions": [ref.CMO], "ref": {"array": "/path/to/array"}}
    try:
        ref.validate(attrs["ref"])
    except ValueError as err:
        print(f"[reject] {err}")
    else:
        msg = "expected the v1-shaped ref to be rejected"
        raise AssertionError(msg)


if __name__ == "__main__":
    workflow_read(workflow_create())
    workflow_reject_v1()
    print("OK")
