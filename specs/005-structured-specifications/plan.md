# Implementation Plan: Structured Specifications

**Branch**: `issues/71` | **Date**: 2026-08-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-structured-specifications/spec.md`

## Summary

One column becomes one child table, and everything else follows from that.

`products.specifications TEXT` is replaced by a `product_specifications` table of `(product_id, name, value, display_order)` rows. The Alembic revision carries every existing paragraph across as a single row named `Specifications` before dropping the column, and its `downgrade` folds the rows back into one block of text. The data copy is done in Python through the Alembic connection rather than in dialect-specific SQL, because `GROUP_CONCAT` ordering is the kind of thing that differs between MariaDB and SQLite and this is the one step in the feature that cannot be re-run to fix a mistake.

Above that: `Product.specifications` changes from a string to a relationship, `CatalogService` gains list-replacement semantics on create and update plus two vocabulary readers next to the `list_tags` / `list_categories` it already has, `search_products` gains a `spec_name` / `spec_value` pair of filters, the shared form partial grows a repeating row editor, and the detail page renders a definition list whose entries link back into the filtered catalogue.

Four things are deliberately *not* built: a unique constraint on `(product_id, name)`, a specification-name rename, per-name typing or units, and any change to the scan or label paths. The first has a real reason and is argued in [research.md](./research.md); the rest are the spec's stated scope boundaries.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x (app-factory, blueprints), SQLAlchemy 2.0.x (legacy `Query` API, matching the surrounding files), Alembic, Jinja2 + Bootstrap 5.3.2. No new dependency.

**Storage**: MariaDB via PyMySQL. Adds `product_specifications`; drops `products.specifications`. No other table is read or written.

**Testing**: `nox -s tests` (pytest + SQLite through the `Storage` seam), `nox -s e2e` (Playwright against a MariaDB testcontainer, 15-minute tool timeout), `nox -s screenshots_headless` + `screenshots_verify` because templates and JS change.

**Target Platform**: Single Flask app on a home LAN, server-rendered HTML.

**Project Type**: Web application, single deployable. Existing structure; no new top-level directories.

**Performance Goals**: None stated and none measured. The catalogue holds tens of products. The specification filter is an `EXISTS` subquery over a table with an index on `name`; no further indexing, no caching, no denormalized copy.

**Constraints**: The collation the deployment runs — `utf8mb4_unicode_ci`, which resolves to `utf8mb4_uca1400_ai_ci` on MariaDB 11 — folds case **and accents**, while SQLite collates `BINARY`. Commit `091e918` is what happens when a feature lets that difference decide something. Every comparison in this feature is therefore either deliberately made backend-independent in Python/`func.lower()`, or is a read-only filter where folding is harmless and is written down as accepted. See [research.md](./research.md#the-collation-question).

**Scale/Scope**: One operator, no concurrency. Roughly: 1 new table, 1 Alembic revision (schema + data, both directions), 1 new ORM model, 4 changed/new `CatalogService` methods, 2 new API endpoints, 2 new search filters, 1 new JS file, 1 changed JS file, 5 templates touched.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1 design — see below.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | One table, no unique constraint that would mean two different things on two backends, no per-name schema, no units, no rename machinery, no separate "unstructured remainder" field kept alongside. The suggestion readers are two methods next to the two identical ones the catalogue already has, not a new service. The one place complexity is *added* rather than avoided is the draft-persistence hook in `product-form.js`, and it is there to stop an existing feature (FR-035 draft restore) regressing on the field this feature replaces. **PASS** |
| **II. Layered Architecture Boundaries** | The ORM model goes in `app/database.py`, all logic in `CatalogService`, routes stay thin — parse the form into a list of dicts, call one service method, flash, redirect. No ORM query or raw SQL in a route. The Alembic revision is the one place raw SQL is used, wrapped in `sa.text(...)` as the technology constraint requires. **PASS** |
| **III. Exact Numerics** | A specification value is operator-typed text and is never parsed as a number — that is an explicit scope boundary in the spec ("no numeric comparison"). No `Decimal`, and critically no `float`, enters this feature. A value reading `12 V` is the string `12 V`. **PASS** |
| **IV. Test Discipline Through Nox** | Unit tests for the service (create, replace, duplicate refusal, half-row refusal, ordering, both filters, both vocabulary readers) and e2e for each user story. **The case-insensitivity requirements (FR-004, FR-015, FR-019) cannot be proved by the unit suite** — SQLite is BINARY, so a case-sensitive implementation passes it. Those get e2e coverage against the testcontainer, which is the lesson `091e918` paid for. No new pytest marker. **PASS** |
| **V. MariaDB Is the Source of Truth** | One Alembic revision, `b1a0c0d10007`, on top of the current head `b1a0c0d10006`. It carries data in both directions and its `downgrade` must be exercised against MariaDB, not merely written. **This is the gap worth stating plainly: neither suite runs Alembic** — `tests/conftest.py:51` and `tests/e2e/test_server.py:61` both build the schema with `Base.metadata.create_all`, so the data migration has no automated coverage at all. The mitigation is a scripted manual round-trip in [quickstart.md](./quickstart.md), and it is a required step, not a suggestion. **PASS — with an obligation recorded** |
| **VI. Item Lifecycle and History Invariants** | No inventory item path is touched. `inventory_items` is neither read nor written by this feature. **N/A** |
| **Operating Context / Threat Model** | No auth, no sanitization layer. LIKE wildcards in the operator's filter text are escaped because an unescaped `%` returns wrong answers, not because anyone is attacking. Names and values render through Jinja autoescaping. **PASS** |
| **Technology Constraints** | Server-rendered Jinja + Bootstrap; no frontend framework, no build step. `product-specifications.js` is a plain IIFE matching the existing files. New code carries type hints and raises the project's `ValidationError`. SQLAlchemy stays on the legacy `Query` API to match `catalog_service.py`. **PASS** |
| **Development Workflow** | Feature branch `issues/71`, merged via PR. `app/templates/product/**` and `app/static/js/**` both change, so `nox -s screenshots_headless` runs and its output is committed. **PASS — with an obligation recorded in tasks** |

No violations. The Complexity Tracking table is therefore omitted.

### Post-design re-check (after Phase 1)

Re-read after [data-model.md](./data-model.md) and the contracts were written. Three points, none of them new risks:

- **Reusing the attribute name `specifications` for the relationship** was checked for silent breakage rather than assumed safe. Every reader in the repository is enumerated in [data-model.md](./data-model.md#every-reader-of-the-old-field); the two that would fail silently rather than loudly (the detail template's `{{ product.specifications }}` and the draft-persisting `#specifications` textarea) are both rewritten by this feature, and the rest raise `AttributeError` immediately. Still **PASS** under Principle I: a second name for the same concept would be worse than a rename that fails loudly.
- **No `UniqueConstraint('product_id', 'name')`.** Under the deployed collation it would enforce something stricter than FR-004 states (rejecting `Volt` against `Vôlt`) and surface as an `IntegrityError` rather than the message FR-008 requires; under SQLite it would enforce something looser. A constraint that means two different things on two backends is worse than none, and the invariant it would protect is cosmetic, not integrity — a product with two `Voltage` rows is untidy, never corrupt. The service check against the loaded rows is the authority. Argued in [research.md](./research.md#why-no-unique-constraint). Still **PASS**.
- **The draft-persistence hook is the one piece of speculative-looking machinery**, so it is worth being explicit that it is not speculative: `tests/e2e/test_draft_persistence.py:26` fills `#specifications` today and asserts it restores. Deleting that textarea without teaching `product-form.js` about repeating rows is a regression with a test already written for it. The hook is 20-ish lines and has exactly one consumer. Still **PASS**.

## Project Structure

### Documentation (this feature)

```text
specs/005-structured-specifications/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — decisions and rejected alternatives
├── data-model.md        # Phase 1 output — the table, the migration, every reader of the old field
├── quickstart.md        # Phase 1 output — how to run and validate, including the migration round-trip
├── contracts/
│   ├── catalog-service.md      # Changed and new CatalogService methods
│   └── http-routes.md          # New and changed HTTP surface
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 output — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
app/
├── database.py                        # + ProductSpecification model; Product.specifications
│                                      #   becomes a relationship; to_dict emits a list
├── catalog_service.py                 # create_product/update_product take a list;
│                                      #   + _validate_specifications, + spec filters in
│                                      #   search_products, + list_specification_names/values
├── product/
│   └── routes.py                      # form -> list of dicts; + 2 suggestion endpoints;
│                                      #   + spec_name/spec_value on both search routes
├── static/js/
│   ├── product-specifications.js      # NEW — repeating rows + value datalist per row
│   └── product-form.js                # + repeated-name draft collect/restore
└── templates/product/
    ├── _form_fields.html              # textarea -> repeating row editor + row template
    ├── detail.html                    # paragraph -> definition list, each entry a filter link
    ├── search.html                    # + spec name/value filter inputs
    ├── add.html                       # + product-specifications.js
    └── edit.html                      # + product-specifications.js

migrations/versions/
└── b1a0c0d10007_structured_product_specifications.py   # NEW — schema + data, both directions

tests/
├── unit/
│   ├── test_catalog_service.py        # + create/replace/refusals/ordering
│   ├── test_product_search.py         # + spec_name/spec_value filters, + free-text over specs
│   └── test_product_model.py          # + to_dict shape
└── e2e/
    ├── test_product_specifications.py # NEW — US1 round-trip, refusals, US2 filter, US3 suggestions,
    │                                  #   and the case-insensitivity cases SQLite cannot prove
    ├── test_draft_persistence.py      # rewritten for repeating rows
    ├── test_product_crud.py           # specifications= kwarg and #product-specifications assertions
    ├── test_product_search.py         # create_product helper fills rows, not a textarea
    └── test_wedge_scan.py             # same helper change
```

**Structure Decision**: The existing layout is used unchanged, and nothing new is created outside it. The catalogue already owns a blueprint, a service, a template directory and a JS convention, and every part of this feature has an obvious home among them. In particular the specification vocabulary readers go on `CatalogService` beside `list_tags` and `list_categories` rather than into `app/services/vocabulary.py` — that module exists for names shared between the *two halves* of the application, and metal stock has no specifications. See [research.md](./research.md#where-the-vocabulary-readers-live).

## Implementation Notes by Slice

### Slice 1 — The table and the migration (FR-001..FR-006, FR-022..FR-024)

`ProductSpecification` in `app/database.py`, alongside `ProductIdentifier` and `ProductTag`, with `product_id` FK `ondelete='CASCADE'`, `name VARCHAR(100) NOT NULL`, `value TEXT NOT NULL` (Text because FR-003 requires it to hold anything the old column held), `display_order INTEGER NOT NULL` mirroring `ProductAttachment`, and one index on `name` for the filter. `Product.specifications` becomes the relationship, `cascade='all, delete-orphan'`, `order_by='ProductSpecification.display_order'`.

Revision `b1a0c0d10007` does three things on the way up — create the table, copy every non-empty `products.specifications` into one row named `Specifications` with `display_order` 0, drop the column — and the mirror on the way down. The copy runs in Python over `op.get_bind()`, iterating rows and inserting with bound parameters; the join on the way down builds each product's text in Python too, restoring a bare paragraph when the product's only row is the untouched legacy one and `name: value` lines otherwise. The exact rule is written out in [data-model.md](./data-model.md#the-migration).

### Slice 2 — Service semantics (FR-004..FR-009, FR-011)

`create_product` and `update_product` take `specifications` as a list of `{'name', 'value'}` dicts. `_validate_specifications` is the single gate: it drops entries where both name and value are blank (FR-009), raises `ValidationError` naming the entry when exactly one is blank (FR-008), trims both (FR-005), enforces the name length, and refuses a case-folded duplicate within the submitted list (FR-004) — comparing `name.strip().lower()`, in Python, never in SQL.

`update_product` replaces the whole list when the key is present and leaves it alone when absent, which is the same "a caller that knows about three fields cannot blank the other ten" contract the method already documents. Replacement is delete-all-then-insert rather than a diff: the form always posts the complete set, row identity is not exposed anywhere, and a diff would be more code for no observable difference.

`Product.to_dict` emits `specifications` as a list of `{'name', 'value'}` in display order (FR-011).

### Slice 3 — The form and the display (FR-007, FR-010, FR-018)

`_form_fields.html` replaces the textarea with a container of rows, each a `name`/`value` pair plus a remove button, followed by an "Add specification" button and a hidden `<template>` row. Both inputs in every row carry the *same* names — `spec_name` and `spec_value` — so the route pairs them positionally with `request.form.getlist`, which needs no index bookkeeping in the markup and no renumbering when a row is removed.

`product-specifications.js` clones the template on add, removes a row on click, and keeps at least one blank row present. It also swaps each row's value datalist when that row's name changes (Slice 5).

`detail.html`'s Specifications card becomes a `<dl>`; each entry's value links to `/products?spec_name=…&spec_value=…` (FR-018). The card is still omitted entirely when the list is empty.

`product-form.js` gains repeated-name handling: `collect()` stores an array when a name appears more than once, and `apply()` clicks the add-row button until the row count matches before assigning positionally. Without this, `tests/e2e/test_draft_persistence.py` is not merely broken but the feature it tests is silently lost for this field.

### Slice 4 — Filtering (FR-012..FR-017)

`search_products` gains `spec_name` and `spec_value`. The clause is `Product.specifications.any(...)` — the same `.any()` idiom the tag filter already uses — with `func.lower(ProductSpecification.name) == spec_name.strip().lower()` for the name (FR-015; `func.lower` rather than `==` because SQLite's `==` is case-sensitive and FR-015 is not) and an escaped `.like('%…%')` for the value (FR-014). A value without a name is ignored rather than erroring, matching how the existing filters treat input they cannot use.

The free-text `query` branch swaps `Product.specifications.like(pattern)` — which will now raise, since the attribute is a relationship — for an `any()` over both columns (FR-017).

Both the page route and `/api/products/search` pass the two new arguments through; `search.html` grows the two inputs.

### Slice 5 — Suggestions (FR-019..FR-021)

`list_specification_names(prefix=None)` and `list_specification_values(name, prefix=None)` sit beside `list_tags`, served by `/api/specification-names` and `/api/specification-values?name=`. Both dedupe **case-insensitively in Python** rather than leaning on `SELECT DISTINCT`, because DISTINCT folds under the deployed collation and does not under SQLite — the same reason `VocabularyService._rank_and_dedupe` already does its dedup in Python.

The client side is datalists, not `FieldAutocomplete`: that component is constructed per DOM id, and these rows are cloned at runtime with no stable ids. One shared `<datalist>` behind every name input, filled once on load; one per-row datalist for values, refilled when that row's name changes. Every input stays a plain `<input list=…>`, so FR-021 holds by construction — a datalist cannot restrict entry.

## Risks and Obligations

- **The data migration has no automated coverage.** Both suites use `create_all`; nothing in CI runs `alembic upgrade`. This is the feature's only irreversible step and its data-integrity requirements (FR-022, FR-024, SC-002, SC-003) rest on it. [quickstart.md](./quickstart.md#the-migration-round-trip) scripts the round-trip against MariaDB with real rows, including a product whose paragraph contains a colon and a newline, and it is a required step before merge.
- **`nox -s tests` cannot prove FR-004, FR-015 or FR-019.** SQLite collates BINARY; a case-sensitive implementation of all three passes the unit suite. The e2e tests carrying those cases are named in the quickstart's coverage table, and they must be confirmed to fail against a deliberately case-sensitive implementation before being trusted — the same discipline `091e918` applied to its four regression tests.
- **Screenshots.** Templates and JS both change, so `nox -s screenshots_headless` must run and its output be committed; CI blocks merge on stale images. `nox -s e2e` must still leave the working tree clean.
- **Four existing e2e tests fill `#specifications` and will fail as soon as the textarea is gone.** They are listed in the structure tree above; updating them is part of the feature, not follow-up work.
- **`nox -s e2e` needs a 15-minute tool timeout.**
