"""How `zarr_conventions` declarations are matched, merged, and superseded.

A convention metadata object identifies its convention by `uuid`, by
`schema_url`, or by both -- the spec requires at least one. Readers must
therefore recognize a declaration that carries only a recognized `schema_url`,
and writers must merge declarations rather than replace or duplicate them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

import zarr_cm
from zarr_cm import license as license_
from zarr_cm import proj, spatial
from zarr_cm._core import declares_convention, find_declaration, insert_convention

if TYPE_CHECKING:
    from zarr_metadata import ZarrV3GroupMetadataJSON


# --- matching -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("cmo", "expected"),
    [
        ({"uuid": proj.UUID}, True),
        ({"uuid": proj.UUID, "schema_url": "https://elsewhere/schema.json"}, True),
        ({"schema_url": proj.SCHEMA_URL}, True),
        ({"schema_url": proj.r2.SCHEMA_URL}, True),
        ({"schema_url": "https://elsewhere/schema.json"}, False),
        ({"uuid": spatial.UUID, "schema_url": proj.SCHEMA_URL}, False),
        ({"spec_url": proj.SPEC_URL}, False),
    ],
)
def test_declares_convention(cmo: dict[str, Any], expected: bool) -> None:
    """uuid wins when present; a uuid-less declaration matches by schema_url."""
    assert declares_convention(cmo, proj.UUID, proj.REVISION_BY_SCHEMA_URL) is expected  # type: ignore[arg-type]


def test_find_declaration_returns_first_match_or_none() -> None:
    cmos = [{"uuid": spatial.UUID}, {"schema_url": proj.SCHEMA_URL}, {"uuid": proj.UUID}]
    assert find_declaration(cmos, proj.UUID, proj.REVISION_BY_SCHEMA_URL) is cmos[1]  # type: ignore[arg-type]
    assert find_declaration(cmos, license_.UUID) is None  # type: ignore[arg-type]


# --- schema_url-only declarations are read ------------------------------------


def schema_url_only_attrs() -> dict[str, Any]:
    return {
        "zarr_conventions": [{"schema_url": proj.SCHEMA_URL}],
        "proj:code": "EPSG:4326",
    }


def test_schema_url_only_declaration_is_detected() -> None:
    attrs = schema_url_only_attrs()
    assert proj.detect(attrs) == "r3"
    assert zarr_cm.detect_revisions(attrs) == {"proj": "r3"}


def test_schema_url_only_declaration_is_validated_and_extracted() -> None:
    attrs = schema_url_only_attrs()
    assert proj.validate(attrs).get("proj:code") == "EPSG:4326"
    remaining, data = proj.extract(attrs)
    assert data == {"proj:code": "EPSG:4326"}
    assert remaining == {}  # the declaration was removed too
    _, extracted = zarr_cm.extract_all(attrs)
    assert set(extracted) == {"proj"}


def test_schema_url_only_declaration_still_validates_content() -> None:
    attrs = schema_url_only_attrs()
    attrs["proj:code"] = "not a code"
    with pytest.raises(ValueError, match="proj:code"):
        zarr_cm.validate_all(attrs)


def test_schema_url_only_declaration_at_node_level() -> None:
    node: ZarrV3GroupMetadataJSON = {
        "zarr_format": 3,
        "node_type": "group",
        "attributes": schema_url_only_attrs(),
    }
    proj.validate_group_metadata(node)
    proj.validate_group_metadata(node, revision="r3")
    with pytest.raises(ValueError, match="does not match revision 'r2'"):
        proj.validate_group_metadata(node, revision="r2")


def test_schema_url_only_r2_declaration_selects_r2() -> None:
    attrs = {
        "zarr_conventions": [{"schema_url": proj.r2.SCHEMA_URL}],
        "proj:code": "EPSG:4326",
    }
    assert proj.detect(attrs) == "r2"


# --- insert merges declarations -----------------------------------------------


def test_insert_keeps_declarations_from_attrs_when_data_carries_its_own() -> None:
    """`create_convention_attrs()` output passed to `insert()` must not
    wipe the conventions already declared in *attrs*."""
    attrs = spatial.insert({}, spatial.create(dimensions=["y", "x"]))
    standalone = proj.create_convention_attrs(code="EPSG:4326")
    out = proj.insert(attrs, standalone, revision="r3")  # untyped `data` arm
    assert zarr_cm.detect_revisions(out) == {"proj": "r3", "spatial": "r3"}
    assert out["zarr_conventions"] == [spatial.CMO, proj.CMO]


def test_insert_adds_foreign_declarations_carried_by_data() -> None:
    foreign = {"uuid": "00000000-0000-0000-0000-000000000000", "name": "other"}
    out = insert_convention(
        {}, proj.CMO, {"zarr_conventions": [foreign], "proj:code": "EPSG:4326"}
    )
    assert out["zarr_conventions"] == [foreign, proj.CMO]


def test_reinsert_at_another_revision_supersedes_the_declaration() -> None:
    old = proj.insert({}, proj.create(code="EPSG:4326", revision="r2"), revision="r2")
    assert proj.detect(old) == "r2"
    new = proj.insert(old, proj.create(code="EPSG:32633"), overwrite=True)
    assert proj.detect(new) == "r3"
    assert new["zarr_conventions"] == [proj.CMO]


def test_reinsert_supersedes_a_schema_url_only_declaration() -> None:
    (alias,) = proj.r3.ALIAS_SCHEMA_URLS
    attrs = {"zarr_conventions": [{"schema_url": alias}]}
    out = proj.insert(attrs, proj.create(code="EPSG:4326"))
    assert out["zarr_conventions"] == [proj.CMO]


def test_reinsert_preserves_position_and_other_declarations() -> None:
    attrs = zarr_cm.create_many(
        {"proj": {"proj:code": "EPSG:4326"}, "license": {"spdx": "MIT"}},
        revisions={"proj": "r2"},
    )
    out = proj.insert(attrs, proj.create(code="EPSG:4326"), overwrite=True)
    assert out["zarr_conventions"] == [proj.CMO, license_.CMO]


def test_insert_is_still_idempotent() -> None:
    once = proj.insert({}, proj.create(code="EPSG:4326"))
    twice = proj.insert(once, proj.create(code="EPSG:4326"), overwrite=True)
    assert once == twice
