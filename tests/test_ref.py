from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from conftest import as_sequence, wrap_attrs

from zarr_cm import ref

SCHEMA_PATH = Path(__file__).parent / "schemas" / "ref.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())

_URI = "https://data.earthdatahub.destine.eu/public/test-dataset-v0.zarr"

# The upstream examples (README.md and examples/*.json at the vendored commit),
# verbatim apart from the node type, which the upstream files leave as "array".
_UPSTREAM_DECLARATION = {
    "name": "ref",
    "schema_url": "https://raw.githubusercontent.com/R-CF/zarr_convention_ref/main/schema.json",
    "spec_url": "https://raw.githubusercontent.com/R-CF/zarr_convention_ref/main/README.md",
    "uuid": "d89b30cf-ed8c-43d5-9a16-b492f0cd8786",
}
_UPSTREAM_REFS: list[dict[str, Any]] = [
    {"node": "../sibling_array"},
    {"node": "..", "attribute": "/attributes/interesting_thing"},
    {"uri": _URI, "node": "/year"},
]


def _schema_accepts(ref_object: Any, node_type: str = "array") -> bool:
    node = wrap_attrs({"zarr_conventions": [ref.CMO], "ref": ref_object}, node_type=node_type)
    return jsonschema.Draft202012Validator(SCHEMA).is_valid(node)  # type: ignore[reportUnknownMemberType]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"node": "../sibling"}, {"node": "../sibling"}),
        ({"node": ".."}, {"node": ".."}),
        ({"node": ""}, {"node": ""}),
        (
            {"node": "..", "attribute": "/attributes/a~1b/c~0d"},
            {"node": "..", "attribute": "/attributes/a~1b/c~0d"},
        ),
        ({"node": "child", "attribute": ""}, {"node": "child", "attribute": ""}),
        ({"uri": _URI, "node": "/year"}, {"uri": _URI, "node": "/year"}),
        (
            {"uri": _URI, "node": "/", "attribute": "/attributes"},
            {"uri": _URI, "node": "/", "attribute": "/attributes"},
        ),
    ],
)
@pytest.mark.parametrize("node_type", ["array", "group"])
def test_create(kwargs: dict[str, Any], expected: dict[str, Any], node_type: str) -> None:
    """Valid field combinations round-trip through every layer and match the schema."""
    created = ref.create(**kwargs)
    assert created == expected
    assert ref.validate(created) == expected
    attrs = ref.create_convention_attrs(**kwargs)
    assert attrs == {"zarr_conventions": [ref.CMO], "ref": expected}
    node: Any = wrap_attrs(attrs, node_type=node_type)
    assert ref.validate_node_metadata(node) == node
    assert _schema_accepts(created, node_type)


@pytest.mark.parametrize("ref_object", _UPSTREAM_REFS)
@pytest.mark.parametrize("node_type", ["array", "group"])
def test_upstream_examples_validate(ref_object: dict[str, Any], node_type: str) -> None:
    node: Any = {
        "zarr_format": 3,
        "node_type": node_type,
        "attributes": {"zarr_conventions": [_UPSTREAM_DECLARATION], "ref": ref_object},
    }
    assert jsonschema.Draft202012Validator(SCHEMA).is_valid(node)  # type: ignore[reportUnknownMemberType]
    assert ref.validate_node_metadata(node) == node
    assert ref.detect(node["attributes"]) == "r1"


# ---------------------------------------------------------------------------
# validate: one test per error case. Where the upstream schema expresses the
# rule, it must reject the same input.
# ---------------------------------------------------------------------------


def test_validate_rejects_missing_node() -> None:
    data: Any = {"attribute": "/attributes/x"}
    with pytest.raises(ValueError, match="'node' is required"):
        ref.validate(data)
    assert not _schema_accepts(data)


def test_validate_rejects_non_string_node() -> None:
    data: Any = {"node": 1}
    with pytest.raises(TypeError, match="'node' must be a string"):
        ref.validate(data)
    assert not _schema_accepts(data)


def test_validate_rejects_non_string_uri() -> None:
    data: Any = {"uri": 1, "node": "/year"}
    with pytest.raises(TypeError, match="'uri' must be a string"):
        ref.validate(data)
    assert not _schema_accepts(data)


def test_validate_rejects_non_string_attribute() -> None:
    data: Any = {"node": "..", "attribute": ["attributes"]}
    with pytest.raises(TypeError, match="'attribute' must be a string"):
        ref.validate(data)
    assert not _schema_accepts(data)


@pytest.mark.parametrize("attribute", ["attributes/x", "/attributes/a~b", "/x~2"])
def test_validate_rejects_attribute_not_a_json_pointer(attribute: str) -> None:
    data: Any = {"node": "..", "attribute": attribute}
    with pytest.raises(ValueError, match="must be a JSON pointer"):
        ref.validate(data)
    assert not _schema_accepts(data)


def test_validate_rejects_unknown_field() -> None:
    data: Any = {"node": "..", "extra": 1}
    with pytest.raises(ValueError, match=r"unknown ref field\(s\) \['extra'\]"):
        ref.validate(data)
    assert not _schema_accepts(data)


@pytest.mark.parametrize("field", ["array", "group"])
def test_validate_rejects_superseded_v1_fields(field: str) -> None:
    data: Any = {field: "/path/to/node"}
    with pytest.raises(ValueError, match="replaced by a single 'node' path"):
        ref.validate(data)
    assert not _schema_accepts(data)


def test_validate_rejects_relative_node_with_uri() -> None:
    # A README rule the schema does not encode.
    with pytest.raises(ValueError, match="absolute path starting with '/'"):
        ref.validate({"uri": _URI, "node": "year"})


def test_validate_rejects_absolute_node_without_uri() -> None:
    # A README rule the schema does not encode.
    with pytest.raises(ValueError, match="relative to the referencing node"):
        ref.validate({"node": "/path/to/array"})


# ---------------------------------------------------------------------------
# insert / extract / detect
# ---------------------------------------------------------------------------


def test_insert_and_extract_roundtrip() -> None:
    data = ref.create(node="../sibling", attribute="/attributes/x")
    inserted = ref.insert({"foo": "bar"}, data)
    assert inserted["ref"] == data
    assert ref.CMO in as_sequence(inserted["zarr_conventions"])
    remaining, extracted = ref.extract(inserted)
    assert extracted == data
    assert remaining == {"foo": "bar"}


def test_insert_collision_raises() -> None:
    with pytest.raises(ValueError, match="overwritten"):
        ref.insert({"ref": {"node": "other"}}, ref.create(node="../sibling"))


def test_extract_missing_convention() -> None:
    remaining, extracted = ref.extract({"foo": "bar"})
    assert remaining == {"foo": "bar"}
    assert extracted == {}


def test_extract_rejects_non_object_ref() -> None:
    attrs = {"ref": "../sibling", "zarr_conventions": [ref.CMO]}
    with pytest.raises(TypeError, match="'ref' must be a JSON object"):
        ref.extract(attrs)


def test_detect_absent_raises() -> None:
    with pytest.raises(ValueError, match="ref"):
        ref.detect({})


# ---------------------------------------------------------------------------
# node-level validation errors
# ---------------------------------------------------------------------------


def test_node_metadata_rejects_missing_ref() -> None:
    node: Any = wrap_attrs({"zarr_conventions": [ref.CMO]}, node_type="group")
    with pytest.raises(ValueError, match="'ref' is required"):
        ref.validate_group_metadata(node)


def test_node_metadata_rejects_non_object_ref() -> None:
    node: Any = wrap_attrs({"zarr_conventions": [ref.CMO], "ref": ".."}, node_type="array")
    with pytest.raises(TypeError, match="'ref' must be a JSON object"):
        ref.validate_array_metadata(node)


def test_node_metadata_rejects_undeclared_convention() -> None:
    node: Any = wrap_attrs({"ref": {"node": ".."}}, node_type="array")
    with pytest.raises(ValueError, match="not declared"):
        ref.validate_node_metadata(node)
