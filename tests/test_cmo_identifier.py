"""The Zarr conventions spec: a declaration MUST carry an identifier.

At least one of `uuid`, `schema_url`, or `spec_url` MUST be present on every
convention metadata object. `_core.validate_convention_metadata_object` is that
clause; `validate_convention_metadata_objects` -- the one place a
`zarr_conventions` array is parsed -- calls it per entry, so every read and
write path enforces it.
https://github.com/zarr-conventions/zarr-conventions-spec/blob/v1/README.md#convention-identity
"""

from __future__ import annotations

from typing import Any

import pytest

import zarr_cm
from zarr_cm import spatial
from zarr_cm._core import (
    validate_convention_metadata_object,
    validate_convention_metadata_objects,
)

# Non-conformant: named and described, but identifies no convention.
_UNIDENTIFIED: dict[str, Any] = {"name": "spatial:", "description": "no identifier"}
_MSG = "must have at least one of 'uuid', 'schema_url', or 'spec_url'"


@pytest.mark.parametrize("identifier", ["uuid", "schema_url", "spec_url"])
def test_any_single_identifier_satisfies_the_clause(identifier: str) -> None:
    """The requirement is *at least one*, so each identifier alone suffices."""
    cmo: dict[str, Any] = {identifier: "x", "name": "n"}
    validate_convention_metadata_object(cmo)  # no raise
    assert len(validate_convention_metadata_objects([cmo])) == 1


def test_predicate_rejects_a_declaration_with_no_identifier() -> None:
    with pytest.raises(ValueError, match=_MSG):
        validate_convention_metadata_object(_UNIDENTIFIED)


def test_parser_enforces_the_clause_per_entry() -> None:
    """One bad entry among good ones still fails: the check is per object."""
    with pytest.raises(ValueError, match=_MSG):
        validate_convention_metadata_objects([spatial.CMO, _UNIDENTIFIED])


def _attrs() -> dict[str, Any]:
    return {"zarr_conventions": [_UNIDENTIFIED], "spatial:dimensions": ["y", "x"]}


def test_every_path_that_parses_declarations_rejects_it() -> None:
    """The MUST holds on every API that reads or writes `zarr_conventions`.

    Before this check was wired in, each of these accepted the document and
    `validate_all` reported success on a non-conformant declaration.
    """
    attrs = _attrs()
    node: Any = {"zarr_format": 3, "node_type": "group", "attributes": _attrs()}
    with pytest.raises(ValueError, match=_MSG):
        zarr_cm.validate_all(attrs)
    with pytest.raises(ValueError, match=_MSG):
        spatial.extract(attrs)
    with pytest.raises(ValueError, match=_MSG):
        spatial.insert(attrs, spatial.create(dimensions=["y", "x"]), overwrite=True)
    with pytest.raises(ValueError, match=_MSG):
        zarr_cm.detect_revisions(attrs)
    # Node-level: the malformed declaration is reported as such, not as the
    # incidental "convention not declared" that a UUID lookup would surface.
    with pytest.raises(ValueError, match=_MSG):
        spatial.validate_group_metadata(node)


# ---------------------------------------------------------------------------
# The spec also closes the object: it MUST NOT contain fields beyond the five.
# That is enforced statically (`ConventionMetadataObject` is `closed=True`,
# so a writer cannot mint extras) but deliberately NOT at read time: a reader
# that rejected unknown fields would fail on documents written to a later
# spec revision, and one that dropped them would lose data on round-trip.
# ---------------------------------------------------------------------------

_FUTURE: dict[str, Any] = {
    "uuid": spatial.UUID,
    "schema_url": spatial.SCHEMA_URL,
    "future_field": {"added": "in a later spec revision"},
}


def test_reader_preserves_unknown_declaration_fields() -> None:
    """Unknown fields pass through the parser untouched -- not rejected, not dropped."""
    (cmo,) = validate_convention_metadata_objects([_FUTURE])
    assert cmo.get("uuid") == spatial.UUID
    assert dict(cmo)["future_field"] == {"added": "in a later spec revision"}


def test_reader_still_type_checks_the_known_fields() -> None:
    """Tolerance of unknown fields does not relax the checks on known ones."""
    with pytest.raises(TypeError, match="'name' must be a string"):
        validate_convention_metadata_objects([{"uuid": "x", "name": 7, "extra": 1}])


def test_unknown_fields_survive_an_extract_insert_round_trip() -> None:
    """The data-loss case: before this, `insert` silently dropped a declaration's extras.

    Attributes carry another convention's declaration bearing a future field;
    inserting spatial alongside it must leave that field intact.
    """
    foreign: dict[str, Any] = {"uuid": "other-uuid", "future_field": "keep me"}
    attrs: dict[str, Any] = {"zarr_conventions": [foreign]}
    result = spatial.insert(attrs, spatial.create(dimensions=["y", "x"]))
    declarations = validate_convention_metadata_objects(result["zarr_conventions"])
    by_uuid = {c.get("uuid"): dict(c) for c in declarations}
    assert by_uuid["other-uuid"]["future_field"] == "keep me"
    assert spatial.UUID in by_uuid


def test_written_declarations_carry_only_the_five_fields() -> None:
    """Writer-strict: what zarr-cm itself emits conforms exactly to the spec."""
    attrs = spatial.create_convention_attrs(dimensions=["y", "x"])
    (cmo,) = attrs["zarr_conventions"]
    assert set(cmo) <= {"uuid", "schema_url", "spec_url", "name", "description"}
