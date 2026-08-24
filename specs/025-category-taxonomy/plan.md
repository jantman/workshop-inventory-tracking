# Implementation Plan: Initial Category Taxonomy for the Existing Workshop

**Branch**: `issues/98` (spec directory `025-category-taxonomy`) | **Date**: 2026-08-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/025-category-taxonomy/spec.md`

## Summary

The session the spec required has happened. Its output is `docs/category-taxonomy.md` — 142
branches across three roots, the seam and tie-break rules, the naming conventions, the tag
boundary, and a specification-key registry. FR-001 through FR-011 and FR-020 through FR-025
are satisfied by that document; `coverage-pass.md` is the evidence for FR-008 and SC-004.

What remains is the software half: FR-012 and FR-016 through FR-019, plus SC-009. A branch
nobody has filed into is invisible today, because a category exists only as a string on a
product. So the first product into each of the 142 branches would be typed free-hand — which
is exactly the drift the record exists to prevent.

The approach is a pure data module, `app/utils/catalog_taxonomy.py`, holding the record's
paths and specification keys as module constants, unioned into the three service methods that
answer "what categories are there" and "what specification names are there". No table, no
migration, no config, no seed command, and no new dependency.

**One consequence worth stating up front:** because the reference data is a module constant,
*establishing* it is shipping the code. FR-016 anticipated a load step and FR-017 required
that step to be repeatable without harm; with a constant there is no step, so FR-017 is
satisfied by construction rather than by a mechanism that has to be written and tested.

**Two additions beyond the literal requirements**, both flagged so they can be cut:

- **`in_taxonomy` on the browse-page rows.** FR-019 forbids the record, the reference data
  and the products' paths being left disagreeing. A test enforces the first two against each
  other. Nothing would surface the third — a path in use that the record does not name —
  without a marker, so one boolean is added.
- **Unioning the specification keys into `/api/specification-names`.** No FR demands it;
  SC-010 (zero near-duplicate keys) has no other mechanism, and specification names are the
  one vocabulary in the application with no rename to repair drift after the fact.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x, SQLAlchemy 2.0.x, Jinja2 + Bootstrap 5.3.2. **No new
dependency is introduced.** `app/utils/catalog_taxonomy.py` is standard library only, matching
the existing `app/utils/category.py`.

**Storage**: MariaDB in production, SQLite under the unit fixtures. **No schema change and no
Alembic revision** — this feature adds no column, table or index. The reference data is code,
not rows.

**Testing**: pytest through `nox -s tests` and `nox -s e2e`. Screenshots via
`nox -s screenshots` (a separate session; the E2E gate excludes them).

**Target Platform**: Linux, home LAN, single user.

**Project Type**: Server-rendered Flask web application.

**Performance Goals**: None. The added work is a union of a 142-element tuple with a `SELECT
DISTINCT` that already runs. No measurement exists that would justify caching it, and per
Principle I none is to be invented.

**Constraints**: Category paths stay at most 3 segments and 512 characters; the application's
canonical form (lowercase, separator-joined, blank segments dropped) is unchanged. Paths
outside the taxonomy remain acceptable (FR-015).

**Scale/Scope**: 142 branches, roughly 60 specification keys, one workshop, one operator.

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | **Pass, with one declared exception.** A tuple of strings in a pure module is the smallest thing that satisfies FR-016: no categories table (FR-016 forbids it), no placeholder products (likewise), no seed command, no new dependency, no caching. **The exception is the runtime override (FR-026..FR-030), which is a configuration knob and therefore squarely what Principle I prohibits.** It is taken deliberately, and the constitution's own escape is the written justification below rather than an amendment. |
| **II. Layered Architecture** | **Pass.** The union happens in `CatalogService`, so every consumer — form datalist, search filter, browse page — sees one answer (FR-018). Routes stay thin and templates stay presentational. The data module sits in `app/utils/` alongside `category.py`, per the module-placement rule. |
| **III. Exact Numerics** | **Not applicable.** No measured quantity is touched. |
| **IV. Test Discipline** | **Pass.** Unit tests for the union and for record↔module agreement; E2E for filing into an unoccupied branch. E2E waits on observable state, seeds through `live_server.add_test_data`, and no new pytest marker is introduced. |
| **V. MariaDB Is the Source of Truth** | **Pass, and worth stating: no migration.** No schema change means no Alembic revision. Nothing calls `create_all` outside the existing fixtures. |
| **VI. Item Lifecycle Invariants** | **Not applicable.** This touches products, not inventory items; no JA ID, active-row or history path is involved. |
| **Operating context / threat model** | **Pass.** No auth, no sanitization layer, no hardening. The reference data is trusted repository content. |
| **Workflow gates** | Work is on `issues/98` and merges by PR. `categories.html` changes, so `nox -s screenshots` must be regenerated and the churn reviewed before committing. |

### The one declared exception

Principle I prohibits "any configuration knob added for a future that has not arrived". The
override is a configuration knob.

**Where the decision came from.** Not from this plan. The repository owner raised it in review
of PR #117, having read the first implementation:

> these categories and specification keys are mine, but this application should be usable by
> anyone. I think we need a facility to override these defaults with something passed in at
> runtime, e.g. a JSON or YAML file. That code path should only be used if the appropriate
> environment variables are set, pointing to the file(s).

That matters for how this section should be read. The constitution's compliance review makes
every pull request the place where a principle is adjudicated, and the person adjudicating is
the one whose workshop, application and constitution these are. This section records a decision
already taken; it is not the argument that persuaded anyone. The shape below — two variables,
JSON, opt-in — follows that instruction rather than reinterpreting it.

**Why it is warranted.** The alternative is not "no knob" — it is that every deployment of this
application carries one particular workshop's category list in `app/utils/`, and cannot change
it without editing source. The future has already arrived: the moment feature 025 put 142
personal branches into the application, the data stopped being universal. The knob does not
anticipate a need, it repairs one this feature created.

**What bounds it.** Two environment variables, each naming a JSON array of strings. No format
negotiation, no merge semantics, no partial overrides, no schema, no new dependency, and no
code path at all when neither variable is set. It configures *what is suggested* and nothing
else: it cannot change how a category is stored, validated, renamed or searched.

**What would have been worse.** A settings table, a UI for editing the taxonomy, a plugin
point, or per-user vocabularies — each of which is the scale machinery Principle I actually
exists to prevent.

**No other violations. Complexity Tracking is therefore omitted.**

## Design

### The reference data

`app/utils/catalog_taxonomy.py` — standard library only, no Flask, no database:

- `DEFAULT_CATEGORY_PATHS: tuple[str, ...]` — all 142 branches from the record, roots and
  intermediate parents included, already in canonical form. Parents are included deliberately:
  the browse page renders depth from the path, and today a product at `a/b/c` produces no `a`
  or `a/b` row at all, so the tree it draws has holes. The taxonomy fills them.
- `DEFAULT_SPECIFICATION_KEYS: tuple[str, ...]` — the distinct keys from the record's registry.
- `category_paths()` / `specification_keys()` — what callers actually use. They return the
  defaults unless `CATEGORY_TAXONOMY_FILE` / `SPECIFICATION_KEYS_FILE` names a JSON array, in
  which case that array replaces the default entirely (FR-026..FR-030). With neither set,
  nothing is read from disk.

Read per call rather than cached: the file is a few kilobytes on a single-user LAN
application, and Principle I requires a measured problem before optimizing one away. A bad
file raises `TaxonomyFileError`, and `create_app` calls both loaders once at boot so that
failure lands at startup with the file named, rather than as a 500 on the first page that asks
for suggestions.

### The merge

Three methods in `CatalogService` change; nothing else does.

| Method | Change |
|---|---|
| `list_categories(prefix)` | Union the distinct in-use paths with `CATEGORY_PATHS` before the prefix filter and sort. Feeds the form datalist and the search filter. |
| `category_tree()` | Union in-use paths with `CATEGORY_PATHS`. Entries keep `path`, `depth`, `name`, `count` — `count` is 0 for a branch nobody occupies — and gain `in_taxonomy: bool`. |
| `list_specification_names(prefix)` | Union with `SPECIFICATION_KEYS`. |

Merging in the service, not per-caller, is what makes FR-018 hold everywhere: a branch on
offer and the same branch in use are one entry because the union deduplicates on the
canonical path.

### The rename control

`rename_category` **raises `ValidationError` when no product carries the path** —
`app/catalog_service.py:2822`, `There is no category "…" to rename.` Once unoccupied branches
appear on the browse page, every one of them would show a Rename button that cannot work.

The fix is presentational and touches no service code: render the Rename button only when
`count > 0`. An unoccupied branch is renamed by editing the record, which is correct — there is
nothing in the database to rewrite. Existing rename behavior and its tests are untouched.

Renaming an *occupied* taxonomy branch still succeeds, and afterwards the record still names
the old path while the new path is not in it. The browse page then shows the old branch at
count 0 and the new one flagged `in_taxonomy: false`. That is the FR-019 obligation made
visible rather than enforced, which is the right level for a single-user tool.

### The copy that becomes false

`app/templates/product/categories.html` currently reads: *"A category exists because a product
is in it. … There is nothing here to set up."* After this change there is something set up.
The paragraph is rewritten to say what is true: the branches come from the taxonomy record,
a branch with no products is on offer rather than in use, and a branch the record does not
name is one somebody typed.

### What deliberately does not change

- `_validate_category_path` — FR-015 keeps paths outside the taxonomy acceptable.
- `rename_category`, `rename_tag` — untouched.
- The canonical form, the 512-character limit, `Product.category_path`.
- Vendor specification names are **not** rewritten automatically on capture. FR-024 requires
  the record to *state* the normalization; making the application apply it is a separate
  feature with its own failure modes, and nothing has yet been observed going wrong.

## Project Structure

### Documentation (this feature)

```text
specs/025-category-taxonomy/
├── spec.md                 # the requirements
├── plan.md                 # this file
├── research.md             # Phase 0
├── data-model.md           # Phase 1
├── quickstart.md           # Phase 1
├── contracts/
│   └── http-endpoints.md   # Phase 1
├── session-draft-tree.md   # superseded; the session trail
├── coverage-pass.md        # evidence for FR-008 / SC-004
├── shop-inventory.txt      # the session's input
└── checklists/requirements.md
```

The taxonomy record itself is **not** here — it is `docs/category-taxonomy.md`, because it is
operator-facing reference material that outlives this feature.

### Source Code (repository root)

```text
app/
├── utils/
│   ├── category.py              # unchanged — canonical form, subtree matching
│   └── catalog_taxonomy.py      # NEW: CATEGORY_PATHS, SPECIFICATION_KEYS
├── catalog_service.py           # list_categories, category_tree,
│                                #   list_specification_names — union with the taxonomy
├── product/routes.py            # unchanged
└── templates/product/
    └── categories.html          # rewritten copy; rename button gated on count > 0;
                                 #   in_taxonomy marker

docs/
└── category-taxonomy.md         # the record (already committed)

tests/
├── unit/
│   ├── test_catalog_taxonomy.py # NEW: record ↔ module agreement, shape invariants
│   └── test_catalog_service.py  # union behavior on the three methods
└── e2e/
    └── test_category_taxonomy.py # NEW: file into an unoccupied branch
```

**Structure Decision**: the existing single-project layout is used unchanged. The one new
runtime module goes in `app/utils/` beside `category.py`, following the constitution's
module-placement rule. It is deliberately **not** called `app/taxonomy.py`, which already
exists and holds the *material* taxonomy — a different concept in a different table, and one
this feature is required to leave alone (FR-010).

## Phase Outputs

- **Phase 0** — [research.md](./research.md): six decisions, with what was rejected and why,
  including the `rename_category` refusal that shapes the browse page.
- **Phase 1** — [data-model.md](./data-model.md), [contracts/http-endpoints.md](./contracts/http-endpoints.md),
  [quickstart.md](./quickstart.md).

## Constitution Re-check (post-design)

Re-evaluated against the design above: unchanged. The design adds one pure module, three
one-line unions, one template edit and two test files. No layer is crossed, no schema changes,
no dependency is added, and nothing is optimized without a measurement. The two judgment calls
are declared in the Summary rather than buried.
