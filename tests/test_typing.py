"""Static-typing contract tests for the public aggregate API.

These tests are primarily exercised by pyright (run over `tests` in strict mode);
they also run under pytest to confirm the runtime behavior matches.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import zarr_cm

if TYPE_CHECKING:
    from collections.abc import Mapping

    from zarr_metadata import ZarrV3ArrayMetadataJSON, ZarrV3GroupMetadataJSON

from zarr_cm import (
    ArrayMetadata,
    ConventionName,
    GeoProjAttrs,
    GroupMetadata,
    JSONDict,
    JSONValue,
    Metadata,
    SpatialAttrs,
    SpatialConventionAttrs,
    create_many,
    insert_many,
    spatial,
)


def test_json_aliases_are_public() -> None:
    # (1) Referencing the public aliases must type-check (and resolve at runtime).
    d: JSONDict = {"a": 1}
    v: JSONValue = [1, "b", {"c": True}]
    assert d == {"a": 1}
    assert v == [1, "b", {"c": True}]


def test_create_many_accepts_convention_typeddicts() -> None:
    # (2) Passing a mapping of the package's own exported TypedDicts must
    # type-check with no cast and no suppression comment.
    spatial_attrs: SpatialAttrs = {"spatial:dimensions": ["x", "y"]}
    proj: GeoProjAttrs = {"proj:code": "EPSG:4326"}
    conv: dict[ConventionName, SpatialAttrs | GeoProjAttrs] = {
        "spatial": spatial_attrs,
        "geo-proj": proj,
    }
    result = create_many(conv)
    assert "proj:code" in result


def test_insert_many_accepts_convention_typeddicts() -> None:
    # (3)
    proj: GeoProjAttrs = {"proj:code": "EPSG:4326"}
    conv: dict[ConventionName, GeoProjAttrs] = {"geo-proj": proj}
    result = insert_many({}, conv)
    assert "proj:code" in result


def _group_doc() -> GroupMetadata[Mapping[str, JSONValue]]:
    """A group document at the wide type: attributes are just a JSON object."""
    attrs = spatial.create_convention_attrs(bbox=[0.0, 0.0, 1.0, 1.0])
    return {"zarr_format": 3, "node_type": "group", "attributes": attrs}


def test_validation_narrows_the_attributes_type() -> None:
    """(4) Validating narrows `Metadata[Mapping]` to `Metadata[TheConvention]`.

    A signature can require a document validated against a specific convention,
    and the narrowed value keeps its field types -- `attributes` is the
    convention's own TypedDict rather than an untyped JSON object.

    The commented-out line is the point: the wide document does not satisfy the
    narrowed parameter, so a forgotten validation call is caught by pyright
    rather than reaching a writer. pyright runs over `tests` in strict mode,
    so uncommenting it fails `just typecheck`.
    """
    group_doc = _group_doc()

    def writes_spatial_group(
        node: Metadata[SpatialConventionAttrs],
    ) -> SpatialConventionAttrs:
        # Field access on the narrowed value is fully typed.
        return node["attributes"]

    # writes_spatial_group(group_doc)   # wide document: type error
    narrowed = spatial.validate_group_metadata(group_doc)
    attrs = writes_spatial_group(narrowed)
    assert attrs.get("spatial:bbox") == [0.0, 0.0, 1.0, 1.0]
    assert narrowed == group_doc
    assert narrowed is not group_doc  # validation returns normalized containers


def test_narrowed_documents_chain_and_widen() -> None:
    """(5) A narrowed document still satisfies the wide input forms.

    The `attributes` type parameter is covariant (the field is `ReadOnly`), so
    `Metadata[SpatialConventionAttrs]` is assignable to
    `Metadata[Mapping[str, JSONValue]]`, and validators chain.

    Narrowing does not accumulate: each single-convention validator returns its
    own convention's type, and there is no intersection type to combine two of
    them.
    """
    narrowed = spatial.validate_group_metadata(_group_doc())

    def takes_wide(node: Metadata[Mapping[str, JSONValue]]) -> None:
        assert node["node_type"] in {"array", "group"}

    takes_wide(narrowed)
    again = spatial.validate_group_metadata(narrowed)
    assert again == narrowed
    assert again is not narrowed


def test_jsonvalue_is_a_recursive_type_alias() -> None:
    """(6) `JSONValue` is a real recursive `TypeAliasType`, not a bare union.

    That is what lets pydantic embed the convention TypedDicts (which use it as
    `extra_items`) without `RecursionError` -- issue #18 -- and it holds on
    every supported Python: the native PEP 695 form on 3.12+, the
    `typing_extensions.TypeAliasType` fallback on 3.11. It is deliberately a
    *local* alias, structurally identical to `zarr_metadata.JSONValue`: two
    recursive aliases of the same shape unify under pyright and ty, so identity
    with zarr-metadata's object was never required for interop, and zarr-cm
    carries no runtime dependency on that package.
    """
    import sys  # noqa: PLC0415
    import typing  # noqa: PLC0415

    import typing_extensions  # noqa: PLC0415

    # The native `type` statement yields `typing.TypeAliasType`; the 3.11
    # fallback yields `typing_extensions.TypeAliasType`. They are distinct
    # classes, so accept whichever this interpreter is on.
    alias_types: tuple[type, ...] = (typing_extensions.TypeAliasType,)
    if sys.version_info >= (3, 12):
        alias_types = (typing.TypeAliasType, *alias_types)
    assert isinstance(zarr_cm.JSONValue, alias_types)
    assert zarr_cm.JSONValue.__name__ == "JSONValue"
    # And it is genuinely recursive: the alias names itself in its own value.
    assert "JSONValue" in repr(zarr_cm.JSONValue.__value__)


def test_unifies_with_zarr_metadata_documents() -> None:
    """(7) zarr-cm attributes flow into zarr-metadata documents without casts.

    zarr-cm's `JSONValue` and zarr-metadata's are separate but structurally
    identical recursive aliases; pyright unifies them, so building a
    `ZarrV3GroupMetadataJSON` from a zarr-cm attributes dict type-checks bare
    -- and their document flows back into our validators, whose input types
    are our own generics, which any structurally conforming document satisfies.
    (An earlier version of this package briefly re-exported zarr-metadata's
    alias on the mistaken belief that identity was required; it is not.)
    """
    attrs = spatial.create_convention_attrs(bbox=[0.0, 0.0, 1.0, 1.0])
    doc: ZarrV3GroupMetadataJSON = {
        "zarr_format": 3,
        "node_type": "group",
        "attributes": attrs,
    }
    # ...and zarr-metadata documents flow into our validators.
    narrowed = spatial.validate_group_metadata(doc)
    assert narrowed == doc
    assert narrowed is not doc


def test_array_validation_preserves_base_metadata_types() -> None:
    attrs = spatial.create_convention_attrs(dimensions=["y", "x"])
    doc: ZarrV3ArrayMetadataJSON = {
        "zarr_format": 3,
        "node_type": "array",
        "data_type": "float64",
        "shape": (100, 200),
        "chunk_grid": {"name": "regular"},
        "chunk_key_encoding": {"name": "default"},
        "fill_value": 0.0,
        "codecs": ({"name": "bytes"},),
        "attributes": attrs,
    }

    validated = spatial.validate_array_metadata(doc, revision="r3")

    def consume(value: ArrayMetadata[SpatialConventionAttrs]) -> None:
        node_type: Literal["array"] = value["node_type"]
        shape: tuple[int, ...] = value["shape"]
        assert node_type == "array"
        assert shape == (100, 200)

    consume(validated)


def test_group_validation_preserves_node_discriminator() -> None:
    validated = spatial.validate_group_metadata(_group_doc(), revision="r3")

    def consume(value: GroupMetadata[SpatialConventionAttrs]) -> None:
        node_type: Literal["group"] = value["node_type"]
        assert node_type == "group"

    consume(validated)
