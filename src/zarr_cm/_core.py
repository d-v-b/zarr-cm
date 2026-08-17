from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from typing import (
    TYPE_CHECKING,
    Final,
    Generic,
    Literal,
    NotRequired,
    TypeAlias,
    TypeGuard,
    cast,
)

from typing_extensions import ReadOnly, TypeAliasType, TypedDict, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# `JSONValue`: a JSON-encodable value.
#
# Structurally identical to `zarr_metadata.JSONValue`, and deliberately so: two
# recursive `TypeAliasType`s of the same shape unify under pyright and ty, so a
# zarr-metadata document's `attributes` flow into zarr-cm and back with no cast
# -- identity of the alias object is not required, only its shape. Two
# properties of that shape are load-bearing:
#
# * The array arm is the covariant `Sequence`, not the invariant `list`/`tuple`,
#   so concrete JSON-shaped values -- and the convention `TypedDict`s, whose
#   fields carry narrower types like `Sequence[str]` -- are assignable to it. A
#   JSON array is still a `list` at runtime; the `Sequence` arm just declines to
#   require a particular container at the type level.
# * It is a real recursive `TypeAliasType`, which is what lets a downstream
#   pydantic model embed the convention `TypedDict`s (which use it as
#   `extra_items`) without `RecursionError` in `model_rebuild()`. See
#   https://github.com/zarr-conventions/zarr-cm/issues/18.
#
# On 3.12+ the alias comes from `_json_alias` as a native PEP 695 `type`
# statement, which pyright resolves cleanly across modules; on 3.11 -- where
# `type` is a syntax error -- the runtime-equivalent `TypeAliasType` below is
# used. The project type-checks at `pythonVersion = 3.12`, so pyright sees the
# native form. Both are real recursive `TypeAliasType`s at runtime.
if sys.version_info >= (3, 12):
    from ._json_alias import JSONValue
else:  # pragma: no cover - exercised only on Python 3.11
    JSONValue = TypeAliasType(
        "JSONValue",
        int
        | float
        | bool
        | str
        | Sequence["JSONValue"]
        | Mapping[str, "JSONValue"]
        | None,
    )


class NamedConfig(TypedDict):
    """This type models the spec defined at https://zarr-specs.readthedocs.io/en/latest/v3/core/index.html#extension-points"""

    name: str
    configuration: NotRequired[Mapping[str, JSONValue]]
    must_understand: NotRequired[bool]


MetadataField: TypeAlias = "str | NamedConfig"
"""The JSON shape of a v3 metadata extension-point entry.

Either a bare short-hand name string or a `NamedConfig` envelope. Mirrors
`zarr_metadata.ZarrV3MetadataFieldJSON` structurally.
"""

NodeType = Literal["array", "group"]
"""The two node types a Zarr v3 metadata document can describe."""

NODE_TYPES: Final[frozenset[NodeType]] = frozenset({"array", "group"})
"""Every value `node_type` may take in a Zarr v3 metadata document."""

JSONDict = TypeAliasType("JSONDict", dict[str, JSONValue])
"""A mutable JSON object: what `json.loads` yields for a JSON document.

Named to match zarr-metadata's `JSONValue` grammar; zarr-metadata itself
exports no dict alias, so this is the one JSON name this package defines.
"""


AttrsT_co = TypeVar("AttrsT_co", covariant=True)
"""Type parameter for a metadata document's `attributes` field.

Covariant, so a document whose attributes satisfy a *narrower* TypedDict is
assignable wherever a wider one is expected.
"""


class GroupMetadata(TypedDict, Generic[AttrsT_co], extra_items=JSONValue):
    """Zarr v3 group metadata, generic over `attributes`.

    This type models the spec defined at https://zarr-specs.readthedocs.io/en/latest/v3/core/index.html#group-metadata

    The type parameter states what is known about `attributes`; the
    `validate_*_metadata` functions narrow it."""

    zarr_format: Literal[3]
    node_type: ReadOnly[Literal["group"]]
    attributes: ReadOnly[AttrsT_co]


class ArrayMetadata(TypedDict, Generic[AttrsT_co], extra_items=JSONValue):
    """Zarr v3 array metadata, generic over `attributes`.

    This type models the spec defined at https://zarr-specs.readthedocs.io/en/latest/v3/core/index.html#array-metadata

    The type parameter states what is known about `attributes`; the
    `validate_*_metadata` functions narrow it."""

    zarr_format: Literal[3]
    node_type: ReadOnly[Literal["array"]]
    data_type: MetadataField
    shape: tuple[int, ...]
    chunk_grid: MetadataField
    chunk_key_encoding: MetadataField
    fill_value: JSONValue
    codecs: tuple[MetadataField, ...]
    attributes: ReadOnly[AttrsT_co]
    storage_transformers: NotRequired[tuple[MetadataField, ...]]
    dimension_names: NotRequired[tuple[str | None, ...]]


Metadata = TypeAliasType(
    "Metadata",
    ArrayMetadata[AttrsT_co] | GroupMetadata[AttrsT_co],
    type_params=(AttrsT_co,),
)
"""Zarr v3 metadata generic over its `attributes` type.

The type parameter states what is known about `attributes`.
`Metadata[Mapping[str, JSONValue]]` is the wide form, and the
`validate_*_metadata` functions narrow it. The array and group arms retain their
node discriminator and all base Zarr fields.

`attributes` is `ReadOnly`, which makes the parameter covariant and lets
validators chain without discarding an earlier validated document at input.

Validators return a normalized document whose `attributes` tree uses concrete
JSON containers. They do not mutate the input mapping.
"""


ArrayMetadataInput: TypeAlias = ArrayMetadata[Mapping[str, JSONValue]]
"""What an array validator accepts: the wide `ArrayMetadata`.

Covariance means every narrowed array document is assignable to it too, so
validators chain: `proj.validate_array_metadata(spatial.validate_array_metadata(doc))`.
It is structural, so a `zarr_metadata.ZarrV3ArrayMetadataJSON` document
satisfies it directly, with no cast and without zarr-metadata installed.
"""

GroupMetadataInput: TypeAlias = GroupMetadata[Mapping[str, JSONValue]]
"""What a group validator accepts; see `ArrayMetadataInput`."""

NodeMetadataInput: TypeAlias = ArrayMetadataInput | GroupMetadataInput
"""What a node validator accepts: either node type, raw or narrowed."""


def _is_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence) and not isinstance(
        value, str | bytes | bytearray
    )


class ConventionMetadataObject(TypedDict, closed=True):
    """This type models the spec defined at https://github.com/zarr-conventions/zarr-conventions-spec/blob/v1/README.md#convention-identity

    Closed: the spec says the object MUST NOT contain fields beyond these
    five, so unlike the convention attributes types it takes no `extra_items`
    -- a writer cannot mint a declaration with extra fields. Readers are more
    tolerant: `validate_convention_metadata_objects` preserves unknown fields
    it encounters rather than rejecting them.
    """

    uuid: NotRequired[str]
    schema_url: NotRequired[str]
    spec_url: NotRequired[str]
    name: NotRequired[str]
    description: NotRequired[str]


class ConventionAttrs(TypedDict, extra_items=JSONValue):
    """This type models the spec defined at https://github.com/zarr-conventions/zarr-conventions-spec/blob/main/README.md#convention-registration-via-zarr_conventions"""

    zarr_conventions: Sequence[ConventionMetadataObject]


def validate_json_value(value: object) -> JSONValue:
    """Validate and return a JSON-shaped value."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if _is_mapping(value):
        return validate_json_object(value)
    if _is_sequence(value):
        return [validate_json_value(item) for item in value]
    msg = f"expected a JSON value, got {type(value).__name__}"
    raise TypeError(msg)


def validate_json_object(value: object) -> JSONDict:
    """Validate and return a mutable JSON object with string keys."""
    if not _is_mapping(value):
        msg = f"expected a JSON object, got {type(value).__name__}"
        raise TypeError(msg)
    result: JSONDict = {}
    for key, item in value.items():
        if not isinstance(key, str):
            msg = f"expected JSON object keys to be str, got {type(key).__name__}"
            raise TypeError(msg)
        result[key] = validate_json_value(item)
    return result


_CMO_IDENTIFIERS: Final = ("uuid", "schema_url", "spec_url")
_CMO_FIELDS: Final = frozenset({*_CMO_IDENTIFIERS, "name", "description"})
"""The complete field set of a convention metadata object; the spec closes it."""


def validate_convention_metadata_object(cmo: Mapping[str, object]) -> None:
    """Validate that a convention metadata object carries an identifier.

    The Zarr conventions specification requires that at least one of `uuid`,
    `schema_url`, or `spec_url` be present; a declaration with none of them
    identifies no convention.
    https://github.com/zarr-conventions/zarr-conventions-spec/blob/v1/README.md#convention-identity
    """
    if not any(k in cmo for k in _CMO_IDENTIFIERS):
        msg = "ConventionMetadataObject must have at least one of 'uuid', 'schema_url', or 'spec_url'"
        raise ValueError(msg)


def validate_convention_metadata_objects(
    value: object,
) -> list[ConventionMetadataObject]:
    """Validate a `zarr_conventions` value.

    Every entry must be a JSON object whose known fields, when present, are
    strings, and each must carry an identifier
    (`validate_convention_metadata_object`). Fields beyond the five the spec
    defines are preserved, not rejected or dropped: readers stay tolerant of
    spec evolution and vendor fields, and round-trips lose nothing. This is the
    one place a `zarr_conventions` array is parsed, so those rules hold on
    every read and write path that goes through it.
    """
    if value is None:
        return []
    if not _is_sequence(value):
        msg = "zarr_conventions must be an array of convention metadata objects"
        raise TypeError(msg)

    result: list[ConventionMetadataObject] = []
    for item in value:
        obj = validate_json_object(item)
        for key in _CMO_FIELDS:
            if key in obj and not isinstance(obj[key], str):
                msg = f"ConventionMetadataObject field {key!r} must be a string"
                raise TypeError(msg)
        # Reader-liberal: fields the current spec does not define are carried
        # through untouched rather than dropped, so a document written to a
        # later spec revision (or with vendor fields) round-trips through
        # extract/insert without silent data loss, and reads do not fail on
        # spec evolution. Only the five known fields are validated. The static
        # `ConventionMetadataObject` type is closed, so a *writer* cannot mint
        # extra fields; the widening here is confined to what we read.
        cmo = cast("ConventionMetadataObject", obj)
        validate_convention_metadata_object(cmo)
        result.append(cmo)
    return result


def declares_convention(
    cmo: ConventionMetadataObject,
    uuid: str,
    schema_urls: AbstractSet[str] | Mapping[str, str] = frozenset(),
) -> bool:
    """Report whether *cmo* declares the convention identified by *uuid*.

    A convention metadata object identifies its convention by `uuid`, by
    `schema_url`, or by both (the spec requires at least one identifier). A
    declaration matches when its `uuid` is *uuid*, or -- for declarations that
    carry no `uuid` -- when its `schema_url` is one of *schema_urls* (any set or
    `{url: label}` map of the URLs the convention recognizes). A declaration
    that names a *different* uuid never matches, whatever its schema_url says.
    """
    declared_uuid = cmo.get("uuid")
    if declared_uuid is not None:
        return declared_uuid == uuid
    return cmo.get("schema_url") in schema_urls


def find_declaration(
    cmos: Iterable[ConventionMetadataObject],
    uuid: str,
    schema_urls: AbstractSet[str] | Mapping[str, str] = frozenset(),
) -> ConventionMetadataObject | None:
    """Return the first of *cmos* that declares the convention, or `None`.

    See `declares_convention` for the matching rule.
    """
    return next(
        (cmo for cmo in cmos if declares_convention(cmo, uuid, schema_urls)), None
    )


def convention_present(
    attrs: Mapping[str, JSONValue],
    uuid: str,
    schema_urls: AbstractSet[str] | Mapping[str, str] = frozenset(),
) -> bool:
    """Report whether *attrs* declares the convention identified by *uuid*.

    *schema_urls* lets declarations that carry only a `schema_url` count as
    well; see `declares_convention`.
    """
    return (
        find_declaration(
            validate_convention_metadata_objects(attrs.get("zarr_conventions")),
            uuid,
            schema_urls,
        )
        is not None
    )


def insert_convention(
    attrs: Mapping[str, JSONValue],
    cmo: ConventionMetadataObject,
    convention_data: Mapping[str, JSONValue],
    *,
    overwrite: bool = False,
    schema_urls: AbstractSet[str] | Mapping[str, str] = frozenset(),
) -> JSONDict:
    """Insert convention metadata into an attributes dict.

    Returns a new dict with the convention data merged in and *cmo* declared
    in the `zarr_conventions` array.

    Declarations are merged, never replaced: every entry already declared in
    *attrs* survives, entries declared inside *convention_data* (as a
    `create_convention_attrs()` result carries) are added if new, and *cmo*
    supersedes any existing declaration of the same convention -- so
    re-inserting at another revision updates the declaration in place rather
    than leaving two entries claiming the same convention. An existing
    declaration is "the same convention" when it matches *cmo*'s `uuid`, or,
    carrying no `uuid`, when its `schema_url` is *cmo*'s own or one of
    *schema_urls* (see `declares_convention`).

    Args:
        attrs: The existing attributes dict.
        cmo: The convention metadata object that declares the convention.
        convention_data: Convention-specific keys to merge into `attrs`.
        overwrite: Whether convention data may replace existing keys.
        schema_urls: Other schema_urls under which the convention may already
            be declared without a `uuid`.
    """
    if not overwrite:
        collisions = set(attrs) & (set(convention_data) - {"zarr_conventions"})
        if collisions:
            msg = f"attrs already contains keys that would be overwritten by convention data: {sorted(collisions)}. Pass overwrite=True to allow."
            raise ValueError(msg)
    result: JSONDict = {**attrs, **convention_data}
    declarations = validate_convention_metadata_objects(attrs.get("zarr_conventions"))
    for extra in validate_convention_metadata_objects(
        convention_data.get("zarr_conventions")
    ):
        if extra not in declarations:
            declarations.append(extra)

    uuid = cmo.get("uuid")
    schema_url = cmo.get("schema_url")
    known_urls = set(schema_urls)
    if schema_url is not None:
        known_urls.add(schema_url)
    merged: list[ConventionMetadataObject] = []
    replaced = False
    for existing in declarations:
        same = existing == cmo or (
            uuid is not None and declares_convention(existing, uuid, known_urls)
        )
        if same:
            if not replaced:
                merged.append(cmo)
                replaced = True
            continue
        merged.append(existing)
    if not replaced:
        merged.append(cmo)
    result["zarr_conventions"] = merged
    return result


def extract_convention(
    attrs: Mapping[str, JSONValue],
    convention_keys: set[str],
    match_fn: Callable[[ConventionMetadataObject], bool],
) -> tuple[JSONDict, JSONDict]:
    """Extract convention metadata from an attributes dict.

    Returns `(remaining_attrs, convention_data)` where the matching CMO
    is removed from `zarr_conventions` and the convention-specific keys
    are separated out.
    """
    remaining: JSONDict = {}
    convention_data: JSONDict = {}

    for key, value in attrs.items():
        if key == "zarr_conventions":
            continue
        if key in convention_keys:
            convention_data[key] = value
        else:
            remaining[key] = value

    old_conventions = validate_convention_metadata_objects(
        attrs.get("zarr_conventions")
    )
    new_conventions = [cmo for cmo in old_conventions if not match_fn(cmo)]
    if new_conventions:
        remaining["zarr_conventions"] = new_conventions

    return remaining, convention_data


def build_revision_by_schema_url(
    revisions: Mapping[str, tuple[str, AbstractSet[str]]],
) -> dict[str, str]:
    """Build a convention's `{schema_url: revision label}` map from its revisions.

    *revisions* maps each label to `(SCHEMA_URL, ALIAS_SCHEMA_URLS)`. Every URL
    -- canonical or alias -- becomes a key. Because `detect` and validation both
    look the declared URL up here, a URL claimed by two revisions would resolve
    to whichever happened to be inserted last; that is an ambiguity in the
    convention's own definition, so this refuses to build the map rather than
    let it be silently shadowed.

    Raises `ValueError` if any URL is claimed by more than one revision.
    """
    result: dict[str, str] = {}
    for label, (canonical, aliases) in revisions.items():
        for url in (canonical, *aliases):
            if url in result and result[url] != label:
                msg = (
                    f"schema_url {url!r} is claimed by revisions "
                    f"{result[url]!r} and {label!r}; a URL must identify one revision"
                )
                raise ValueError(msg)
            result[url] = label
    return result


def resolve_revision_label(
    attrs: Mapping[str, JSONValue],
    uuid: str,
    revision_by_schema_url: Mapping[str, str],
    convention_name: str,
) -> str | None:
    """Return the revision label a document claims for a convention.

    Returns the label whose `schema_url` matches the convention's CMO, or
    `None` if the convention's `uuid` is present but its `schema_url` is
    unrecognized (an older/newer/foreign revision). Raises `ValueError` if the
    convention is absent (no CMO with *uuid*) -- asking which revision is present
    for a convention that is not there is a caller error.
    """
    if not convention_present(attrs, uuid, revision_by_schema_url):
        msg = f"convention {convention_name!r} is not present in attrs"
        raise ValueError(msg)
    return detect_revision(attrs, uuid, revision_by_schema_url)


def detect_revision(
    attrs: Mapping[str, JSONValue],
    uuid: str,
    revision_by_schema_url: Mapping[str, str],
) -> str | None:
    """Return the revision label whose recognized schema_urls include the document's.

    Looks for a convention-metadata object in `attrs['zarr_conventions']`
    that declares the convention -- by *uuid*, or, for a declaration with no
    `uuid`, by a `schema_url` in *revision_by_schema_url* (see
    `declares_convention`). If found, looks its `schema_url` up in
    *revision_by_schema_url* -- the convention's input type, every schema_url
    any revision recognizes mapped to that revision's label. Returns `None` if
    the convention is absent, or present but carrying a schema_url no revision
    recognizes (a future or foreign URL). Callers must decide how to handle
    that uncertainty; validation must not silently select the latest revision.

    Entries in `zarr_conventions` are assumed to be CMO dicts (consistent
    with the rest of this module).
    """
    cmo = find_declaration(
        validate_convention_metadata_objects(attrs.get("zarr_conventions")),
        uuid,
        revision_by_schema_url,
    )
    if cmo is None:
        return None
    schema_url = cmo.get("schema_url")
    if isinstance(schema_url, str):
        return revision_by_schema_url.get(schema_url)
    return None


__all__ = [
    "ArrayMetadata",
    "ArrayMetadataInput",
    "ConventionAttrs",
    "ConventionMetadataObject",
    "GroupMetadata",
    "GroupMetadataInput",
    "JSONDict",
    "JSONValue",
    "Metadata",
    "NodeMetadataInput",
    "NodeType",
    "convention_present",
    "declares_convention",
    "detect_revision",
    "extract_convention",
    "find_declaration",
    "insert_convention",
    "resolve_revision_label",
    "validate_convention_metadata_object",
    "validate_convention_metadata_objects",
    "validate_json_object",
    "validate_json_value",
]
