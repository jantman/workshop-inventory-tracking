# Implementation Plan: Manage Product Identifiers After Creation

**Branch**: `speckit/036-manage-product-identifiers` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/036-manage-product-identifiers/spec.md`

## Summary

Everything this feature needs on the server already exists and is already correct.
`CatalogService.add_identifier` and `.remove_identifier` implement the whole rule set the spec
asks for — check-digit validation, the all-zero no-read refusal, the override flag, the vendor
requirement for vendor-scoped types, cross-product duplicate detection naming the owning
product, and idempotent re-add — and `POST/DELETE /api/products/<id>/identifiers[/<id>]` expose
them. Neither route has a caller.

So this is a UI feature: an add form and per-row remove controls on the Identifiers card of the
product detail page, driven by one new `product-identifiers.js` against the two existing
endpoints. No service method, no route, no model, and **no schema change or Alembic revision**.
The one non-UI edit is lifting the identifier type list out of `add.html`'s hardcoded literal
into a single constant, because FR-003 makes "the same types in both places" a requirement and
two hardcoded lists drift.

The docs are already ahead of the code: `docs/user-manual.md:1272` tells the operator to "Add it
by hand from the product's **Identifiers** card" — a control that does not exist. This makes
that sentence true.

## Technical Context

**Language/Version**: Python 3.13; vanilla ES6 in `app/static/js/` (no build step, no framework)

**Primary Dependencies**: Flask 3.1.x, SQLAlchemy 2.0.x, Jinja2, Bootstrap 5.3.2 — all present.
No new package.

**Storage**: MariaDB via PyMySQL. `product_identifiers` already holds every column this feature
writes (`id_type`, `value`, `vendor`, `validation_overridden`). **No migration.**

**Testing**: `nox -s tests` (pytest against SQLite through the `Storage` ABC) and `nox -s e2e`
(Playwright, `-m "e2e and not screenshot"`). No new pytest marker.

**Target Platform**: Flask app on a home LAN, driven from a desktop browser and a handheld at
the workshop cart.

**Project Type**: Server-rendered web application (Jinja2 + progressive-enhancement JS).

**Performance Goals**: None. There is no measured problem; the card renders at most a handful of
rows and each action is one request.

**Constraints**:
- The detail page must not scroll sideways at 390px — `test_touch_readiness.py` asserts it, and
  this adds a form and a per-row button to a narrow column.
- Template and JS changes trip the constitution's screenshot gate. `user-manual/product_detail.png`
  captures this exact card, so it genuinely changes; the other captures churn per run and are
  not committed.
- CSRF is on: every write goes through `csrfFetch`.

**Scale/Scope**: 1 constant, 3 `render_template` call sites, 2 templates, 1 new JS file,
2 test files, 1 docs section. No file over a few dozen new lines.

## Constitution Check

*GATE: passed before Phase 0, re-checked after Phase 1 design — see the re-check at the end.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Simplicity First | **PASS** | No new service, route, abstraction or dependency. The one deduplication (`OPERATOR_IDENTIFIER_TYPES`) removes an existing duplicate that FR-003 forbids drifting; it is a module constant, not an interface. Success reloads the page exactly as `product-stock.js` and `product-attachments.js` do, rather than inventing a client-side model of the list. |
| II. Layered Architecture Boundaries | **PASS** | Routes stay thin and unchanged: all logic is already in `CatalogService`. No ORM query or raw SQL is added anywhere. |
| III. Exact Numerics | **N/A** | Identifiers are strings. No measured quantity is touched. |
| IV. Test Discipline Through Nox | **PASS** | Unit tests for the request/response contract the UI depends on; e2e for the operator flows. E2E waits on elements only — no `wait_for_timeout`, no `networkidle`. Products are seeded through `live_server.add_test_products`, except where the Add Product form is itself the subject (FR-003). |
| V. MariaDB Is the Source of Truth | **PASS** | No schema change, so no Alembic revision. This is the strongest reason to keep the feature UI-only. |
| VI. Item Lifecycle and History Invariants | **N/A** | Products and their identifiers, not inventory items. No JA ID, active-row or parent-child path is touched. |
| Operating Context / Threat Model | **PASS** | Validation is for correctness (a wrong barcode breaks lookup), not defense. CSRF stays as it is via `csrfFetch`; nothing further is added. |
| Technology Constraints | **PASS** | Server-rendered Jinja + Bootstrap, no frontend framework. Type hints on the touched Python. Existing `app/exceptions.py` types and the central handlers do the erroring. |
| Development Workflow | **PASS** | On feature branch `speckit/036-manage-product-identifiers`, merging by PR. Screenshot regeneration is a task, not an afterthought. |

**No violations. The Complexity Tracking table is therefore omitted.**

## Project Structure

### Documentation (this feature)

```text
specs/036-manage-product-identifiers/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── identifiers.md   # Phase 1 output: the HTTP contract consumed + the DOM contract produced
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
├── models.py                          # + OPERATOR_IDENTIFIER_TYPES beside IdentifierType
├── catalog_service.py                 # UNCHANGED — add_identifier/remove_identifier already correct
├── product/
│   └── routes.py                      # 3 render_template sites pass identifier_types; routes unchanged
├── templates/product/
│   ├── add.html                       # hardcoded ['MPN','GTIN',...] -> the shared constant
│   └── detail.html                    # Identifiers card: add form, per-row remove, alerts region
└── static/js/
    └── product-identifiers.js         # NEW — the only new file

tests/
├── unit/
│   └── test_product_identifiers.py    # NEW — the HTTP contract the card depends on
└── e2e/
    └── test_product_identifiers.py    # NEW — the operator flows, including scan-back

docs/
└── user-manual.md                     # Product Identifiers section: where to add and remove one
```

**Structure Decision**: The existing layout is kept exactly. This feature adds one JS file and
two test files and edits four existing files. The Identifiers card is already in
`detail.html:384-414`; the work extends that card in place rather than introducing a new
template, partial or page.

## Phase 0 — Research

See [research.md](./research.md). Six decisions were open; all are resolved, none needed a
clarification round. In brief:

1. **Reload on success, render errors in place.** Matches `product-stock.js` and
   `product-attachments.js`, and makes FR-012's "shown list matches what is stored" true for
   free rather than by careful DOM patching.
2. **The add form is a Bootstrap `collapse` inside the card**, toggled by markup attributes with
   no JS of its own, so the card stays compact on a phone.
3. **`OPERATOR_IDENTIFIER_TYPES` in `app/models.py`**, passed explicitly to the three render
   sites. No context processor, no Jinja global, no shared partial.
4. **Two response shapes to read**, not one: the routes' own `{success, error}` /
   `{success, error, owning_product_id}`, and the central handler's `{success, message, ...}`
   for a missing product. The JS must read both or FR-019 shows "undefined".
5. **`response.ok || response.status === 404` is the delete success test**, the same reasoning
   `product-attachments.js:104` records — and, since #132 closed, that 404 is now real.
6. **No page object.** The e2e file drives ids directly, as the other product-detail e2e files do.

## Phase 1 — Design

- [data-model.md](./data-model.md) — the entities involved and, more usefully, the validation
  and normalization rules the UI must not restate, with where each already lives.
- [contracts/identifiers.md](./contracts/identifiers.md) — the two HTTP endpoints exactly as they
  behave today (this feature consumes them unchanged), plus the DOM contract the new markup owes
  the tests: element ids, data attributes and classes.
- [quickstart.md](./quickstart.md) — how to run it, the automated commands, and the by-hand
  checks that close SC-002 and the fourth GS1 verification vector inherited from #80.

### Constitution re-check after design

Re-evaluated against the artifacts above: still no violations. The design added no service
method, no route, no table, no dependency and no abstraction beyond one module constant. The
sharpest simplicity risk considered and rejected was a client-side render of the identifier list
after each action; reloading is fewer moving parts and cannot disagree with the database.

## Complexity Tracking

Not applicable — the Constitution Check records no violations.
