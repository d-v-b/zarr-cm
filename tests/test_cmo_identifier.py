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
