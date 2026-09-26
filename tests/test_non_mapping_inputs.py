"""Non-mapping attributes and metadata documents fail with `TypeError`."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

import pytest
from strategies import REVISIONS, Revision

import zarr_cm

if TYPE_CHECKING:
    from collections.abc import Callable

NON_MAPPINGS: list[object] = [None, [], "attrs", 3]


def _insert_nothing(insert: Callable[..., object], attrs: Any) -> object:
    return insert(attrs, {})


def _attrs_entry_points(rev: Revision) -> dict[str, Callable[[Any], object]]:
    """Every entry point that reads attributes through the shared layer.

    A revision module's own `validate` is convention-specific data checking,
    not a shared entry point, so it is not listed; for conventions without
    revisions that is also the package-level `validate`.
    """
    points: dict[str, Callable[[Any], object]] = {
        "package.detect": rev.package.detect,
        "package.extract": rev.package.extract,
        "module.extract": rev.module.extract,
        "module.insert": partial(_insert_nothing, rev.module.insert),
    }
    if rev.label is not None:
        points["package.validate"] = rev.package.validate
        points["package.validate(revision)"] = partial(
            rev.package.validate, revision=rev.label
        )
        points["package.extract(revision)"] = partial(
            rev.package.extract, revision=rev.label
        )
    return points


_MULTI_ENTRY_POINTS: dict[str, Callable[[Any], object]] = {
    "validate_all": zarr_cm.validate_all,
    "extract_all": zarr_cm.extract_all,
    "detect_revisions": zarr_cm.detect_revisions,
    "validate_many": partial(zarr_cm.validate_many, conventions=["proj"]),
    "extract_many": partial(zarr_cm.extract_many, conventions=["proj"]),
    "insert_many": partial(zarr_cm.insert_many, conventions={}),
}

_ATTRS_CASES = [
    pytest.param(fn, value, id=f"{rev!r}-{name}-{value!r}")
    for rev in REVISIONS
    for name, fn in _attrs_entry_points(rev).items()
    for value in NON_MAPPINGS
] + [
    pytest.param(fn, value, id=f"{name}-{value!r}")
    for name, fn in _MULTI_ENTRY_POINTS.items()
    for value in NON_MAPPINGS
]


@pytest.mark.parametrize(("fn", "value"), _ATTRS_CASES)
def test_non_mapping_attributes_raise_type_error(
    fn: Callable[[Any], object], value: object
) -> None:
    with pytest.raises(TypeError, match="attributes must be a JSON object"):
        fn(value)


def _metadata_entry_points(rev: Revision) -> dict[str, Callable[[Any], object]]:
    return {
        f"{where}.{fn}": getattr(getattr(rev, where), fn)
        for where in ("package", "module")
        for fn in (
            "validate_group_metadata",
            "validate_array_metadata",
            "validate_node_metadata",
        )
    }


_METADATA_CASES = [
    pytest.param(fn, value, id=f"{rev!r}-{name}-{value!r}")
    for rev in REVISIONS
    for name, fn in _metadata_entry_points(rev).items()
    for value in NON_MAPPINGS
]


@pytest.mark.parametrize(("fn", "value"), _METADATA_CASES)
def test_non_mapping_metadata_raises_type_error(
    fn: Callable[[Any], object], value: object
) -> None:
    with pytest.raises(TypeError, match="metadata document must be a JSON object"):
        fn(value)
