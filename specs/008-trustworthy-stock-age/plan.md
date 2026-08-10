# Implementation Plan: Trustworthy Stock Age

**Branch**: `issues/59` | **Date**: 2026-08-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-trustworthy-stock-age/spec.md`

## Summary

Two changes to what the catalogue is allowed to assert about stock, and both are small.

**One column.** `products.stock_status_updated_at`, nullable, no backfill. `set_stock_status` stamps it when a flag is set and clears it when the flag is cleared; a `stock_status_age` property mirrors the `quantity_age` that already exists; two templates render it through the `relative_age` filter that already exists.

**One deleted line.** `receive_purchase` currently writes `product.quantity_updated_at = datetime.now()` alongside the increment. That line is the whole of FR-008: with it gone, a count's age means the last time a person counted, the increment still happens, and the screen stops claiming a verification that never occurred.

The shape of the work is set by two properties of the code as it stands. The stock write surface is tiny — `create_product`, `set_quantity`, `set_stock_status` and `receive_purchase` are the only four places that touch `quantity_updated_at` or `stock_status`, and `update_product` explicitly refuses both fields — so "what resets the age" (SC-003) is a claim that can be read off four functions rather than argued about. And `product-stock.js` responds to every successful PATCH with `window.location.reload()`, so the new age lines are server-rendered like everything else and this feature ships **no JavaScript at all**.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x, SQLAlchemy 2.0.x (legacy `Query` API, per the surrounding file), Alembic, Jinja2 + Bootstrap 5.3.2. No new dependency.

**Storage**: MariaDB via PyMySQL. One Alembic revision, `b1a0c0d10010`, on top of the current head `b1a0c0d10009`.

**Testing**: `nox -s tests` (pytest against SQLite through `test_storage`), `nox -s e2e` (Playwright against MariaDB, 15-minute tool timeout).

**Target Platform**: Flask app on a home LAN, reached from a desktop and a handheld.

**Project Type**: Server-rendered web application.

**Performance Goals**: None. This feature adds one nullable column, one property, and two lines of Jinja; it removes a write. There is nothing here to measure.

**Constraints**: No backfill of the new column (FR-005, SC-006). Reversible migration. No new screen and no JavaScript.

**Scale/Scope**: ~4 production files, 1 migration, 2 templates, 2 test files, 1 documentation section.

## Constitution Check

*GATE: passed before Phase 0, re-checked after Phase 1.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | The feature adds one column and deletes one statement. Three simpler-looking options were considered and rejected in `research.md` — a second "last changed" timestamp, a CHECK constraint pairing the flag with its date, and a second Jinja filter — and each was rejected for adding a moving part the requirement does not need. Nothing here is speculative: every artifact traces to an FR. |
| **II. Layered Architecture Boundaries** | The column goes on the ORM model, the rules go in `CatalogService`, the routes are untouched, and the templates read properties. `relative_age` stays where it is, in `app/product/routes.py`, because that is where the filter is registered and moving it would be churn. No new layer, no repository, no DTO. |
| **III. Exact Numerics** | Not engaged. No measured quantity is involved; the counts here are `int` piece counts, as they already are, and the new column is a `DateTime`. |
| **IV. Test Discipline Through Nox** | Behaviour changes, so tests land with it. Unit tests carry FR-007 through FR-011 because they can backdate a timestamp; E2E carries the two display requirements and the one end-to-end path (receive through the UI, age unchanged). No new pytest marker. Every new wait is an `expect()` on a server-rendered element. |
| **V. MariaDB Is the Source of Truth** | One Alembic revision, `upgrade` adds the column and `downgrade` drops it. The downgrade loses the flag ages and nothing else; that is inherent to reversing an added column and is stated in `data-model.md`. Exercised against a disposable MariaDB container, not against `.env`. |
| **VI. Item Lifecycle and History Invariants** | Not engaged. This feature does not touch `inventory_items`, JA IDs, active rows or shortening history. The product catalogue is a separate table with no history semantics. |

**Deviation to record, not to fix here.** The Development Workflow section requires regenerating documentation screenshots for any change under `app/templates/**`. This change touches `product/detail.html` and `product/reorder.html`, and **no committed screenshot shows either page** — `tests/e2e/screenshot_config.yaml` covers the metal-stock screens only. Regenerating would rewrite eleven unrelated PNGs with rasterization noise, which `.github/workflows/screenshots.yml` documents as non-reproducible (issue #77) and which the constitution's own "no mass reformatting, it destroys review signal" rationale argues against. Screenshots are therefore not regenerated. Separately, the constitution says CI blocks on stale screenshots and the workflow says it is informational; the two disagree and one of them should be corrected, but not by this feature.

No violations requiring justification, so there is no Complexity Tracking table.

### Why one age and not two

Recorded fully in `research.md`; the short form is that FR-015 was a decision, not an omission. A second `quantity_changed_at` beside `quantity_counted_at` would buy one line of display and cost a rule that every future write of a count has to get right — and the change it would advertise is already recorded, with its date, vendor and quantity, on the purchase that caused it. The count's age answers "should I trust this number?"; the purchase list answers "why did it move?". Splitting the first question across two dates makes it harder to answer, not easier.

### Why the flag's age is a plain column and not an event

The obvious "proper" design is a small history of flag transitions. It is refused under Principle I: nothing in the spec asks who flagged what when — there is one operator — and FR-001 needs exactly one date. A table would be a schema, a relationship, a cascade and a query in exchange for a fact one column holds.

### Post-design re-check (after Phase 1)

Nothing in Phase 1 introduced a new dependency, layer, table, endpoint, JavaScript file or configuration knob. The design got *smaller* than the first pass in two places: the CHECK constraint was dropped in favour of matching the existing `quantity` / `quantity_updated_at` precedent exactly, and the planned second Jinja filter became one optional parameter on the existing one. Gate still passes.

## Project Structure

### Documentation (this feature)

```text
specs/008-trustworthy-stock-age/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── catalog-service.md   # Service method semantics
│   ├── product-json.md      # The to_dict field addition
│   └── presentation.md      # The relative_age filter and what each template renders
├── checklists/
│   └── requirements.md  # From /speckit-specify, 16/16
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
├── database.py                      # +stock_status_updated_at column
│                                    # +stock_status_age property
│                                    # +field in to_dict
├── catalog_service.py               # set_stock_status: stamp / clear the date
│                                    # receive_purchase: delete the quantity_updated_at
│                                    #   write; clear the flag's date with the flag
├── product/
│   └── routes.py                    # relative_age gains one optional parameter
└── templates/product/
    ├── detail.html                  # flag age line under the flag buttons
    └── reorder.html                 # flag age line under the "Flagged low" badge

migrations/versions/
└── b1a0c0d10010_add_stock_status_updated_at.py

tests/
├── unit/
│   └── test_stock_status.py         # extended: the age rules and the receive path
└── e2e/
    ├── test_reorder_view.py         # extended: flag age on the reorder row
    └── test_stock_age.py            # new: the aged/unknown/receive display cases

docs/
└── user-manual.md                   # the two sentences that are now wrong
```

**Structure Decision**: The existing layout, unchanged. The catalogue already has its `product` blueprint, its `CatalogService`, and its two stock templates; this feature adds no file to `app/` at all and one file to `tests/e2e/`.

## Phase 0 / Phase 1 outputs

- `research.md` — the decisions and what was rejected: one age versus two, no CHECK constraint, no backfill, one filter parameter instead of a second filter, and how a test backdates a timestamp when the UI can only write "now".
- `data-model.md` — the column, the migration and its reverse, the two properties, and what deliberately is not modelled.
- `contracts/` — the three surfaces this touches: `CatalogService` methods, the product JSON, and the template-facing filter.
- `quickstart.md` — how to run the suites, and the four things to check by hand against a real database, including the legacy-row case a fresh database cannot produce.
