"""Declarations identified by `spec_url`.

The conventions spec lets a declaration identify its convention by any one of
`uuid`, `schema_url`, or `spec_url`, with a fixed precedence: "If `uuid` is
present, it serves as the primary unique identifier ... If `uuid` is not
present and both `schema_url` and `spec_url` are present, the `schema_url`
serves as the identifier. If only `spec_url` is present (and no `uuid`), it
serves as the identifier."
https://github.com/zarr-conventions/zarr-conventions-spec/blob/main/README.md#convention-metadata-object

Each revision recognizes a set of spec_urls -- its `SPEC_URL` plus
`ALIAS_SPEC_URLS` -- exactly as it does schema_urls.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import wrap_attrs
from strategies import REVISIONS, Revision

import zarr_cm
from zarr_cm import multiscales, proj, spatial
from zarr_cm._core import build_revision_by_spec_url

# One valid `create()` input per convention.
_KWARGS: dict[str, dict[str, Any]] = {
    "proj": {"code": "EPSG:4326"},
    "spatial": {"dimensions": ["y", "x"]},
    "multiscales": {"layout": [{"asset": "0"}]},
    "license": {"spdx": "MIT"},
    "uom": {"ucum": {"unit": "m"}},
    "stac": {"key": "item.json"},
}

UNKNOWN_URL = "https://example.com/not-a-known-convention/README.md"


def _canonical_attrs(rev: Revision) -> dict[str, Any]:
    return dict(rev.module.create_convention_attrs(**_KWARGS[rev.convention]))


def _declared_attrs(rev: Revision, declaration: dict[str, str]) -> dict[str, Any]:
    """Valid attributes for *rev* whose only declaration is *declaration*."""
    return _canonical_attrs(rev) | {"zarr_conventions": [declaration]}


def _expected_label(rev: Revision) -> str:
    if rev.label is not None:
        return rev.label
    return rev.package.detect(_canonical_attrs(rev))


def _declarations(rev: Revision) -> list[tuple[str, dict[str, str]]]:
    """Every way a declaration may name this revision through its spec_url."""
    cases: list[tuple[str, dict[str, str]]] = []
    for url in sorted(rev.module.RECOGNIZED_SPEC_URLS):
        cases.append((f"spec_url-only:{url}", {"spec_url": url}))
        cases.append(
            (f"uuid+spec_url:{url}", {"uuid": rev.module.UUID, "spec_url": url})
        )
    # schema_url outranks spec_url: an unknown spec_url does not disturb a
    # declaration its schema_url already identifies.
    cases.append(
        (
            "schema_url+unknown-spec_url",
            {"schema_url": rev.module.SCHEMA_URL, "spec_url": UNKNOWN_URL},
        )
    )
    return cases


_CASES = [
    pytest.param(rev, declaration, id=f"{rev.convention}-{rev.label}-{name}")
    for rev in REVISIONS
    for name, declaration in _declarations(rev)
]


@pytest.mark.parametrize(("rev", "declaration"), _CASES)
def test_spec_url_declarations_read_as_their_revision(
    rev: Revision, declaration: dict[str, str]
) -> None:
    attrs = _declared_attrs(rev, declaration)
    node = wrap_attrs(attrs, node_type=rev.node_type)
    label = _expected_label(rev)

    assert rev.package.detect(attrs) == label
    assert zarr_cm.detect_revisions(attrs) == {rev.convention: label}
    remaining, extracted = rev.package.extract(attrs)
    assert remaining == {}
    assert extracted == rev.package.extract(_canonical_attrs(rev))[1]
    rev.package.validate(extracted)
    rev.package.validate_node_metadata(node)
    if rev.label is not None:
        rev.package.validate_node_metadata(node, revision=rev.label)
    rev.module.validate_node_metadata(node)
    zarr_cm.validate_all(attrs)
    assert set(zarr_cm.extract_all(attrs)[1]) == {rev.convention}
    # Re-inserting replaces the spec_url-only declaration rather than adding a
    # second one for the same convention.
    data = rev.module.create(**_KWARGS[rev.convention])
    assert rev.module.insert(attrs, data, overwrite=True)["zarr_conventions"] == [
        rev.module.CMO
    ]


@pytest.mark.parametrize("rev", REVISIONS, ids=repr)
def test_unknown_spec_url_only_declaration_is_not_declared(rev: Revision) -> None:
    attrs = _declared_attrs(rev, {"spec_url": UNKNOWN_URL})
    with pytest.raises(ValueError, match="is not present"):
        rev.package.detect(attrs)
    with pytest.raises(ValueError, match="is not declared"):
        rev.package.validate_node_metadata(wrap_attrs(attrs, node_type=rev.node_type))
    assert zarr_cm.detect_revisions(attrs) == {}


@pytest.mark.parametrize("rev", REVISIONS, ids=repr)
def test_unknown_schema_url_is_not_rescued_by_a_known_spec_url(rev: Revision) -> None:
    """With no uuid, the schema_url identifies the declaration -- not the spec_url."""
    attrs = _declared_attrs(
        rev, {"schema_url": UNKNOWN_URL, "spec_url": rev.module.SPEC_URL}
    )
    with pytest.raises(ValueError, match="is not present"):
        rev.package.detect(attrs)
    with pytest.raises(ValueError, match="is not declared"):
        rev.package.validate_node_metadata(wrap_attrs(attrs, node_type=rev.node_type))
    assert zarr_cm.detect_revisions(attrs) == {}


@pytest.mark.parametrize("pkg", [proj, spatial], ids=lambda p: p.__name__)
def test_spec_url_of_another_revision_conflicts_with_a_pin(pkg: Any) -> None:
    attrs: dict[str, Any] = {
        "zarr_conventions": [{"uuid": pkg.UUID, "spec_url": pkg.r2.SPEC_URL}],
        **pkg.r3.create(**_KWARGS[pkg.__name__.rsplit(".", 1)[-1]]),
    }
    node = wrap_attrs(attrs, node_type="group")
    with pytest.raises(ValueError, match="does not match revision 'r3'"):
        pkg.validate_group_metadata(node, revision="r3")


def test_spec_url_map_construction_refuses_a_shared_url() -> None:
    with pytest.raises(ValueError, match=r"spec_url .* claimed by revisions"):
        build_revision_by_spec_url(
            {
                "r2": ("https://example/r2.md", frozenset()),
                "r3": ("https://example/r3.md", frozenset({"https://example/r2.md"})),
            }
        )


def test_no_spec_url_is_claimed_by_two_revisions() -> None:
    for pkg in (spatial, proj, multiscales):
        claimed: dict[str, str] = {}
        for label, module in pkg._REVISIONS.items():
            assert module.SPEC_URL not in module.ALIAS_SPEC_URLS
            for url in (module.SPEC_URL, *module.ALIAS_SPEC_URLS):
                assert url not in claimed
                claimed[url] = label
        assert claimed == pkg.REVISION_BY_SPEC_URL
