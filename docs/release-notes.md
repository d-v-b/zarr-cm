# Release notes

Changes per released version, newest first. Each entry lists what a user of the
package sees: new capabilities, fixes, and — under **Breaking** — anything that
requires a change on the caller's side when upgrading. Dependency-bot bumps and
internal refactors are omitted. Every version links to its
[GitHub release](https://github.com/zarr-conventions/zarr-cm/releases), which
carries the full pull-request list.

<!-- Keep the newest version at the top. Sections: Highlights, Added, Changed,
Fixed, Breaking, Internal — include only the ones with content. -->

## 0.5.0 (unreleased)

### Highlights

- A sixth convention: [`stac`](https://github.com/zarr-conventions/stac) (v0.1)
  — embed a STAC Item or Collection in a Zarr group's attributes, or reference
  one by store key or link.
- Whole-document validation: `validate_group_metadata`,
  `validate_array_metadata` and `validate_node_metadata` take a complete
  `zarr.json` document and check the rules that depend on the node type — the
  spec makes `spatial:dimensions` required on arrays only, `multiscales` applies
  to groups only, and `uom` to arrays only. Every convention module and every
  revision provides all three.
- Reads are more forgiving of the declarations found in the wild, without
  becoming permissive: each revision recognizes a set of `schema_url`s (its
  canonical one plus aliases), a declaration may identify its convention by
  `schema_url` alone, and a URL outside the recognized set still fails rather
  than being guessed at.
- A property-based test layer generates valid data for every revision of every
  convention and checks the package's invariants across all of them (see
  [Internal](#internal)).

### Added

- `zarr_cm.stac`: the STAC convention (single revision `v0.1`, group-only —
  arrays are rejected like `multiscales`). Exactly one of `stac:item`,
  `stac:collection`, `stac:key`, `stac:link` must be present; embedded
  Items/Collections are checked only for being JSON objects — validating them as
  STAC is STAC's own job. Ships the full module surface (`create`,
  `create_convention_attrs`, `insert`, `extract`, `validate`, the node-level
  validators), participates in every multi-convention function (`"stac"` is in
  `CONVENTION_NAMES`), and exports `StacAttrs`, `StacConventionAttrs` and
  `StacLink` at the top level. Tracked by the upstream drift check and covered
  by the property-based tests like every other convention.
- `validate_group_metadata`, `validate_array_metadata`, `validate_node_metadata`
  on every convention module and revision submodule; typed as
  `GroupMetadata[…]`, `ArrayMetadata[…]`, `Metadata[…]` documents whose
  `attributes` are narrowed to the convention's TypedDict.
- `create_convention_attrs(...)` on every convention module: a complete
  stand-alone `attributes` dict — the convention data plus its
  `zarr_conventions` entry — for when there is nothing to `insert` into.
- `zarr_cm.latest_revisions()`: which revision each revisioned convention writes
  by default (`{"proj": "r3", "spatial": "r3", "multiscales": "r2"}`), so
  downstream packages can pin against it.
- `zarr_cm.convention_metadata(name, *, revision=None)`: the `zarr_conventions`
  entry a convention writes, per revision.
- `zarr_cm.CONVENTION_ALIASES` (`{"geo-proj": "proj"}`) and
  `zarr_cm.CanonicalConventionName`.
- Per revision: `ALIAS_SCHEMA_URLS` (other URLs read as this revision) and
  `RECOGNIZED_SCHEMA_URLS` (`SCHEMA_URL` plus aliases). Per convention package:
  `REVISION_BY_SCHEMA_URL`, the `{url: revision}` map every read consults.
  Recognized aliases today: the never-published `refs/tags/v1` URLs that early
  writers copied from the draft READMEs (→ `r2`), and the commit-pinned URLs
  that `zarr-cm` 0.4 wrote for `proj` and `spatial` (→ `r3`).
- Document types re-exported at the top level: `ArrayMetadata`, `GroupMetadata`,
  `Metadata`, `ArrayMetadataInput`, `GroupMetadataInput`, `NodeMetadataInput`,
  and the JSON aliases `JSONValue`, `JSONDict`.
- Every example under `examples/` is now a page on the docs site, and this
  release-notes page was added to the docs.
- Every spec-defined TypedDict's docstring links to the section of the spec that
  defines its shape, pinned to the same commit or tag the module's `SPEC_URL`
  uses; a test keeps the next convention from arriving without one.
- A `justfile` collects the development tasks (`just check`, `just test`,
  `just lint`, `just typecheck`, `just docs`, …).

### Changed

- The canonical name of the CRS convention is `"proj"` (upstream renamed the
  repository from `geo-proj`). `"geo-proj"` is still accepted everywhere a name
  is _input_; see Breaking for where it is no longer _reported_.
- `spatial:dimensions` is optional at the attribute level in `spatial` r2 and r3
  (`spatial.create()` no longer requires `dimensions=`), matching upstream,
  which requires it only when `node_type` is `"array"`. The array-node
  requirement is enforced by `validate_array_metadata`.
- Multi-convention functions raise `ValueError` when `revisions=` names a
  revision for a convention that has none (`license`, `uom`), instead of
  silently ignoring the label — the same rule `convention_metadata()` applies.
- `insert()` merges `zarr_conventions` declarations rather than replacing the
  array: declarations already present survive, ones carried by the inserted data
  are added, and the inserted convention's entry supersedes any prior
  declaration of the same convention in place. Re-inserting at another revision
  therefore updates the declaration instead of leaving two entries claiming the
  same convention.
- The node-level validators' document types and `JSONValue` are structurally
  identical to
  [zarr-metadata](https://zarr.readthedocs.io/projects/zarr-metadata/en/latest/)'s,
  so zarr-metadata documents pass in and out with no cast. zarr-metadata is not
  a dependency; `typing_extensions` remains the only one.

### Fixed

- `proj` and `spatial` declarations now validate against the published v0.1
  schemas: `r3` writes the `refs/tags/v0.1` `schema_url`/`spec_url` the schemas
  require as `const`s, instead of commit-pinned URLs, and every revision writes
  `name` as `"proj"`/`"spatial"` (upstream dropped the trailing colon in May
  2026). Documents written by 0.4 still read as `r3`.
- Documents declaring the upstream `refs/tags/v0.1` schema URL for `proj` or
  `spatial` — the URL upstream's own READMEs and schema `$id`s tell writers to
  use — were rejected as "unsupported schema_url". They now read as `r3`.
- Documents declaring the draft-era `refs/tags/v1` schema URLs (as written by
  rioxarray, topozarr and others) now detect and validate as `r2` rather than
  failing.
- `insert()` given data that carried its own `zarr_conventions` (as
  `create_convention_attrs()` output does) silently dropped every other declared
  convention.
- A `zarr_conventions` entry that identifies its convention by `schema_url`
  alone (legal per the spec, which requires any one of `uuid`, `schema_url`,
  `spec_url`) was invisible to `detect`, `validate`, `extract` and the `*_all`
  functions.
- A `zarr_conventions` entry with _no_ identifier at all (neither `uuid`,
  `schema_url` nor `spec_url` — which the spec forbids) was accepted by every
  read and write path; `validate_convention_metadata_object` existed but was
  never called. Every path that parses `zarr_conventions` now enforces it.
- Reading a `zarr_conventions` entry silently dropped any field beyond the five
  the spec defines, so `insert` on attributes carrying a foreign declaration
  with a future field lost that field. Unknown fields now pass through
  untouched; only the known fields are validated.
- The convention TypedDicts' annotations resolve at runtime again, so
  `typing.get_type_hints()` and pydantic's `model_rebuild()` work on them
  without `NameError`.
- The build pins `hatchling < 1.32` so published metadata stays at version 2.4,
  which `twine check --strict` still requires.

### Breaking

- `zarr_cm.JsonValue` and `zarr_cm.JsonDict` were renamed to `JSONValue` and
  `JSONDict`, matching zarr-metadata's spelling. There is no alias for the old
  spellings.
- `zarr_cm.CONVENTION_NAMES` contains `"proj"`, not `"geo-proj"`, and the
  functions that _report_ names — `detect_revisions()`, `extract_all()` — key
  their results by `"proj"`. Code that keyed on `"geo-proj"` in those results
  must switch. (`"geo-proj"` remains valid as input, and the `zarr_cm.geo_proj`
  module alias remains.)
- `proj.SCHEMA_URL`/`SPEC_URL`/`CMO` and their `spatial` counterparts changed
  value (tag URLs instead of commit URLs, and `name` without the trailing
  colon), so newly written `zarr_conventions` entries differ from 0.4's. Code
  that compared declarations against hard-coded 0.4 values must update; reads
  are unaffected.
- A declared `schema_url` that no revision recognizes now raises `ValueError`
  from `validate`/`extract` (and the node-level validators) instead of silently
  falling back to the latest revision. `detect` continues to return `None` for
  it. Recognized aliases cover the URLs known to be in circulation; a document
  that fails here is declaring a revision this version does not know.
- `spatial:dimensions` is `NotRequired` in `SpatialAttrs`; code that assumed the
  key is always present in a validated `SpatialAttrs` must check for it.
- `*ConventionAttrs.zarr_conventions` is typed
  `Sequence[ConventionMetadataObject]` rather than
  `tuple[ConventionMetadataObject, ...]` (type-level only).
- `ConventionMetadataObject` is a closed TypedDict (`closed=True`), per the
  spec's "MUST NOT contain additional fields". Typed construction of a
  declaration with extra fields — including through a pydantic model — is now
  rejected. Reading is unaffected: documents carrying unknown declaration fields
  still parse, and the fields are preserved.
- A `zarr_conventions` entry lacking every identifier (`uuid`, `schema_url`,
  `spec_url`) now raises `ValueError` wherever `zarr_conventions` is parsed,
  including `validate_all`, `detect_revisions`, `insert` and `extract`.

### Upgrading from 0.4

Working through this list top to bottom upgrades a 0.4 codebase; each item names
the symptom of skipping it.

1. **Rename the JSON aliases.** `JsonValue` → `JSONValue`, `JsonDict` →
   `JSONDict`, everywhere. The old names no longer import.
2. **Key results on `"proj"`.** `detect_revisions()` and `extract_all()` report
   the CRS convention as `"proj"`; code doing `extracted["geo-proj"]` gets a
   `KeyError`. Passing `"geo-proj"` _in_ — to `create_many`, `validate_many`,
   `revisions=` — still works.
3. **Decide what an unrecognized `schema_url` should mean.** 0.4 silently
   validated such documents as the latest revision; 0.5 raises `ValueError` from
   `validate`/`extract` and the node-level validators. If you read documents
   whose declarations you do not control, probe with `detect()` first (it
   returns `None` for an unrecognized URL) or catch the `ValueError`; to
   deliberately reproduce the old fallback, pin `revision=` explicitly. Most
   documents that failed this way under 0.4.x were declaring the upstream tag
   URLs, which 0.5 recognizes — so expect _fewer_ failures, not more.
4. **Stop assuming `spatial:dimensions` is present.** It is `NotRequired` in
   `SpatialAttrs`, so index it with `.get()`. A validated _group_ document may
   genuinely lack it; arrays are still required to carry it, enforced by
   `validate_array_metadata`.
5. **Give every declaration an identifier.** A `zarr_conventions` entry with
   none of `uuid`, `schema_url`, `spec_url` now raises `ValueError` wherever the
   array is parsed — reads and writes. Such an entry was always invalid per the
   spec; fix the data.
6. **Do not put extra fields on a `ConventionMetadataObject` you construct.**
   The TypedDict is closed: type checkers and pydantic now reject additional
   fields. Unknown fields on declarations you _read_ still pass through
   untouched.
7. **Type-level only:** `*ConventionAttrs.zarr_conventions` is
   `Sequence[ConventionMetadataObject]`, not `tuple[...]`; annotations that
   spelled the tuple form may need updating. No runtime change.
8. **Rewrite stored `proj`/`spatial` declarations if they must pass the
   published schemas.** 0.4 wrote commit-pinned `schema_url`/`spec_url` values
   and `"proj:"`/`"spatial:"` names, which fail the upstream v0.1 schemas (and
   validators built on them, such as inspect.geozarr.org). 0.5 still reads those
   documents as `r3`; `insert(..., overwrite=True)` replaces the declaration
   with the canonical one. Code that compares declarations against hard-coded
   0.4 values (`name == "proj:"`, the commit URLs) must update.

### Internal

- Property-based tests (`hypothesis`, test dependency): `tests/strategies.py`
  registers a generator of valid `create()` input for every revision of every
  convention, checked against the vendored upstream JSON schemas;
  `tests/test_properties.py` runs the round-trip, detection, declaration and
  multi-convention invariants across the whole registry.
- Vendored upstream schemas for every supported revision under `tests/schemas/`,
  and a weekly workflow that diffs them against upstream `main` and opens an
  issue when they drift.
- The drift check now covers `license` and `uom` too, and a test pins its
  tracked set to `zarr_cm.CONVENTION_NAMES` so a new convention can't ship
  untracked.

## 0.4.1 — 2026-06-21

### Fixed

- A pydantic model embedding one of the convention TypedDicts raised
  `RecursionError` in `model_rebuild()`, because the `JsonValue` alias was not a
  real recursive type. `JsonValue` is now a `TypeAliasType`, and the TypedDicts'
  `extra_items=JsonValue` resolves.
  ([#18](https://github.com/zarr-conventions/zarr-cm/issues/18))

### Added

- `zarr_cm.JsonValue` and `zarr_cm.JsonDict` exported at the top level.

### Breaking

- The `r1` revisions of `spatial`, `proj` and `multiscales` were removed — their
  `schema_url` pointed at a location that never resolved, so they could not
  produce valid self-describing metadata. `revision="r1"` now raises
  `ValueError`; `spatial.r1`, `proj.r1`, `multiscales.r1` and the `*R1`
  TypedDicts (`SpatialAttrsR1`, `GeoProjAttrsR1`, `LayoutObjectR1`,
  `TransformR1`, …) are gone. Surviving revisions keep their `r2`/`r3` labels,
  which are local to this package and never appear in documents.

### Internal

- Type checking moved to pyright; runtime `cast`s were replaced by narrowing.

## 0.4.0 — 2026-06-19

### Changed

- Public functions are precisely typed. `create`, `insert`, `validate` and
  `extract` on the revisioned packages carry `@overload`s keyed on the
  `revision` literal, so `spatial.create(..., revision="r2")` is typed as
  returning `SpatialAttrsR2` and `proj.validate(data)` as
  `GeoProjAttrsR2 | GeoProjAttrsR3`. The multi-convention functions and `_core`
  helpers dropped `Any` in favor of `JsonDict`/`JsonValue`.

### Added

- Per-revision TypedDicts exported at the top level: `SpatialAttrsR1/R2/R3`,
  `SpatialConventionAttrsR1/R2/R3`, `GeoProjAttrsR1/R2/R3`,
  `GeoProjConventionAttrsR1/R2/R3`, `MultiscalesAttrsR1/R2`,
  `MultiscalesConventionAttrsR1/R2`, `LayoutObjectR1/R2`, `TransformR1/R2`. The
  unsuffixed names continue to alias the latest revision.

## 0.3.0 — 2026-06-17

### Highlights

- Convention **revisions**. Upstream conventions changed shape between their
  drafts and their v0.1 releases; this release models each shape as a revision.
  `spatial`, `proj` and `multiscales` became packages exposing per-revision
  submodules (`spatial.r1`/`r2`/`r3`, `proj.r1`/`r2`/`r3`,
  `multiscales.r1`/`r2`), and their package-level functions take a keyword-only
  `revision=` that defaults to the latest revision for writes and auto-detects
  for reads.
- **Auto-detection on read**: `validate` and `extract` resolve the revision from
  the document's own `zarr_conventions` entry, by its `schema_url`. Public
  `detect()` on every convention module returns the revision label a document
  claims (or `None` if unrecognized), and `zarr_cm.detect_revisions()` does so
  for every convention present.

### Added

- `spatial` r2 (strict 2D: every dimension-bearing key has a fixed length) and
  r3 (the v0.1 snapshot). `spatial.LATEST == "r3"`.
- `zarr_cm.proj`, the renamed CRS convention: r1 (the original geo-proj shape),
  r2 (corrected URLs and `proj:code` regex), r3 (v0.1: relaxed `proj:code`
  pattern, and _at least one_ of code/wkt2/projjson rather than exactly one).
  `zarr_cm.geo_proj` remains as a compatibility alias exposing the latest `proj`
  revision.
- `multiscales` r1 and r2 (r2 pins the v0.1 tag URLs, which the upstream schema
  requires as a `const`).
- `revisions=` keyword on the multi-convention functions (`create_many`,
  `insert_many`, `validate_many`, `extract_many`, `validate_all`, `extract_all`)
  to override the revision per convention.
- `LATEST`, `SCHEMA_URL_BY_REVISION` and the `_core.resolve_revision_label`
  helper.
- Runnable examples for every convention under `examples/`, executed as part of
  the test suite.

### Fixed

- `validate_many` and `extract_many` lost the detected revision on argument-less
  reads: extraction removed the declaration before validation resolved the
  revision. The revision is now detected once and threaded to both.

### Internal

- `_contract.ConventionModule` protocol; every convention module and revision
  submodule is statically checked against it.
- Upstream schemas for spatial and proj are vendored, revision output is
  validated against them, and CI tracks drift against upstream `main`.
- Documentation site (mkdocs, Read the Docs).

## 0.2.0 — 2026-02-06

### Added

- Multi-convention API at the package top level, dispatching on convention name:
  `create_many`, `insert_many`, `validate_many`, `extract_many`, `validate_all`,
  `extract_all`. The `*_all` forms detect which conventions a document declares
  by UUID.
- `ConventionName` literal, `CONVENTION_NAMES`, `ALL_CONVENTION_KEYS`, and the
  `MultiConventionAttrs` TypedDict covering every convention's keys.

## 0.1.0 — 2026-02-06

Initial release.

- Modules for five conventions: `geo_proj`, `spatial`, `multiscales`, `license`,
  `uom`. Each exposes `create`, `validate`, `insert`, `extract`; the identifying
  constants `UUID`, `SCHEMA_URL`, `SPEC_URL`, `CMO`, `CONVENTION_KEYS`; and
  TypedDicts for the convention data (`*Attrs`) and for an attributes dict
  declaring it (`*ConventionAttrs`).
- `ConventionMetadataObject` and `ConventionAttrs` TypedDicts for the
  `zarr_conventions` array, and `validate_convention_metadata_object`.
