# Implementation Plan: Type a tracked count instead of clicking to it

**Branch**: `robot-army/issue-139-a-tracked-count-can-only-be-changed-one` | **Date**: 2026-09-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/039-typed-quantity-entry/spec.md`

## Summary

A product's on-hand count can currently only be moved one at a time, so recording a counted forty
takes forty clicks. The recording capability is already complete — `CatalogService.set_quantity()`
takes an absolute count and `PATCH /api/products/<id>/quantity` forwards it — and nothing has ever
sent it an arbitrary number. This feature adds the input that does.

Three changes, all in the presentation layer:

1. **A numeric entry on the Stock card** (`app/templates/product/detail.html`) with a commit
   button, sitting alongside the existing `+`/`−` steppers rather than replacing them. The steppers
   are the right tool for "I just used one" and are the only count control that works on a
   keyboardless handheld; the touch tests encode that and keep passing.
2. **A commit path in `app/static/js/product-stock.js`** that sends the typed number as an
   absolute quantity, and that refuses an empty or malformed entry *locally* — because
   `_validate_quantity` reads `''` as "stop counting", which is not what an empty box means.
3. **A received total on the Stock card** of a product that is not being counted, computed in
   `product_detail` from the purchases it already holds. Stated, never pre-filled: receiving into
   an untracked product moves no count, so the number is worth showing, but the record cannot say
   how much of it has since been used.

No schema change, no migration, no service change, no endpoint change.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x (app-factory), SQLAlchemy 2.0.x, Jinja2, Bootstrap 5.3.2.
No new dependency, and no new JavaScript beyond a method on an existing class.

**Storage**: MariaDB via SQLAlchemy in production, SQLite through the same `Storage` interface in
unit tests. **Unchanged by this feature** — no table, column, index or constraint is touched, and
there is no Alembic revision.

**Testing**: `nox -s tests` (pytest, network blocked) and `nox -s e2e` (Playwright,
`-m "e2e and not screenshot"`). New unit tests in `tests/unit/`, new E2E tests in `tests/e2e/`,
plus one extension to an existing touch test's selector list.

**Target Platform**: Server-rendered Flask app on a home LAN. Two client shapes matter: a desktop
browser at a workbench, and a handheld touchscreen at the shelf with no physical keyboard.

**Project Type**: Web application, server-rendered. No frontend framework and no build step.

**Performance Goals**: None. The change adds one `sum()` over a list the route already has in
memory. No measurement exists that would justify anything else (Constitution I).

**Constraints**: Every control on the Stock card stays at least 44px tall and operable by touch
alone. The typed entry is additive: no existing control is removed, resized, renamed, or given a
new meaning.

**Scale/Scope**: One template region, one JavaScript class method plus a validator, one derived
value in one route. Roughly 60 lines of application code; the test and documentation surface is
larger than the change.

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design. Both passes below.*

### I. Simplicity First (NON-NEGOTIABLE) — PASS

- **Built for the requirement in front of us.** The endpoint, the service method and the validation
  all already exist; the feature adds the missing input and nothing else. No delta endpoint, no
  new service method, no abstraction over "ways to change a count".
- **No premature optimization.** The received total is a `sum()` over a list already in memory. No
  query, no cache, no index.
- **No scale machinery.** None added.
- **No new dependency.**
- **Boring code.** One new method on the existing `StockControls` class, in the style of the
  methods beside it.
- One deliberate act of *not* generalizing is recorded in `research.md` §2: `_validate_quantity`
  reads `''` as "stop counting", which is right for the product form and wrong here. The fix is a
  three-line guard in the one client that can tell the cases apart, not a change to a validator
  two other callers depend on.

### II. Layered Architecture Boundaries — PASS

- No ORM query and no raw SQL is added to a route. `received_total` is arithmetic over
  `service.get_purchase_history(product_id)`, which the route already calls, in the same shape as
  the `outstanding=[...]` comprehension already on the line above it.
- No business logic moves into the template: the template renders `received_total`, it does not
  compute it.
- No new layer, repository, or DTO tier.

### III. Exact Numerics for Physical Measurements — PASS, not applicable

A count of discrete parts is an `int` and always has been. No `Decimal` quantity and no `float`
arithmetic is introduced. `Purchase.unit_price` is not touched.

### IV. Test Discipline Through Nox — PASS

- Tests run through `nox`; `nox -s tests` and `nox -s e2e` must both be green.
- **No fixed waits.** Every new E2E assertion waits on an element: `#quantity-value` for a
  committed count (the page reloads on success, so the rendered value cannot predate the completed
  request — `CLAUDE.md` pattern C), and `#stock-alert` for a refusal (no reload happens, and
  `showAlert()` writes that element only after refusing).
- The one negative assertion — no received total on a tracked product — establishes the card with
  a positive `expect()` on `#quantity-value` first, so it cannot pass against an unrendered page.
- Unit tests build fixtures through `tests/conftest.py` and mock nothing external, because nothing
  external is involved.
- No new pytest marker is introduced, so `--strict-markers` needs no `pytest.ini` change.
- Behavior changes land with the tests covering them.

### V. MariaDB Is the Source of Truth — PASS, nothing to do

No schema change, therefore no Alembic revision and no `downgrade` to exercise. Google Sheets is
untouched.

### VI. Item Lifecycle and History Invariants — PASS, not applicable

This feature touches products and purchases. It does not touch inventory items, JA IDs, active-row
selection, shortening history, or parent-child relationships. No file under those paths is
modified.

### Operating Context and Threat Model — PASS

Validation is added because an empty box must not silently stop a count — a correctness concern
about the operator's data, not a defense against an attacker. No sanitization layer, no rate
limiting, no auth. CSRF stays as it is: the commit goes through the existing `csrfFetch` helper
that every other control on this card already uses.

### Development Workflow and Quality Gates — PASS, with one obligation

`app/templates/**` and `app/static/js/**` are both modified, which requires regenerating
documentation screenshots and committing them alongside the change.
`tests/e2e/screenshot_config.yaml` has no product-detail entry, so this is expected to produce no
content change — but the session is run and the diff is inspected either way, and only screenshots
whose content actually changed are committed (screenshot output churns between runs regardless of
content). `nox -s screenshots_verify` must pass.

**Result: no violations. The Complexity Tracking table below is empty and stays empty.**

### Post-design re-evaluation

Re-checked after Phase 1. The design added: one template block, one route context value, one
JavaScript method with a validator, three element ids, and no files outside
`app/templates/product/detail.html`, `app/static/js/product-stock.js` and `app/product/routes.py`.
Nothing in the design introduces an abstraction, a query, a layer, a dependency, or a schema
change. **Still no violations.**

## Project Structure

### Documentation (this feature)

```text
specs/039-typed-quantity-entry/
├── plan.md                      # This file
├── spec.md                      # Feature specification
├── research.md                  # Phase 0: decisions and rejected alternatives
├── data-model.md                # Phase 1: entities touched, state transitions, no schema change
├── quickstart.md                # Phase 1: how to run and verify this by hand
├── contracts/
│   ├── stock-card-ui.md         # Element ids, what is added, what must not move
│   └── quantity-commit.md       # Request/response and client-side validation
├── checklists/
│   └── requirements.md          # Spec quality checklist
└── tasks.md                     # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
app/
├── product/
│   └── routes.py                # MODIFIED: product_detail passes received_total.
│                                #   api_set_quantity is NOT modified.
├── templates/product/
│   └── detail.html              # MODIFIED: #quantity-input, #quantity-set-btn,
│                                #   #received-total inside #stock-card.
├── static/js/
│   └── product-stock.js         # MODIFIED: read + validate + commit the typed count.
├── catalog_service.py           # UNCHANGED — set_quantity and _validate_quantity as they are.
└── database.py                  # UNCHANGED — no schema change.

migrations/                      # UNCHANGED — no revision.

tests/
├── unit/
│   └── test_typed_quantity.py   # NEW: received_total in the detail context and its rendering;
│                                #   the absolute-set path through the endpoint.
└── e2e/
    ├── test_typed_quantity.py   # NEW: type a count, start a count at a number, refusals,
    │                            #   the received-total line and its absence.
    └── test_touch_readiness.py  # MODIFIED: #quantity-set-btn added to the 44px selector list.

docs/images/screenshots/         # Regenerated; committed only if content actually changed.
```

**Structure Decision**: The existing layout, unchanged. This is a presentation-layer feature in a
server-rendered Flask application: a Jinja template, the JavaScript that drives it, and one derived
value in the blueprint route that renders it. There is no new module, no new service, and no new
directory. Tests follow the project's split — `tests/unit/` for the route context and the endpoint,
`tests/e2e/` for what the operator can actually do on the page.

## Phase 0 — Research

Complete. See [research.md](./research.md). Nine decisions recorded, each with the alternatives
rejected; no open questions and no `NEEDS CLARIFICATION` markers remain. The two that most shape
the implementation:

- **§2** — `_validate_quantity` maps `''` to `None`, i.e. "stop counting". The empty-entry guard
  therefore belongs in the client, which is the only place the two meanings are distinguishable,
  and the validator is left alone.
- **§4** — one input, two possible commit buttons. `#quantity-set-btn` when the product is counted,
  `#start-tracking-btn` when it is not. This is what lets FR-004 (empty means zero when starting)
  and FR-006 (empty is refused when setting) both hold without either being a special case, and it
  preserves the existing behavior three E2E tests already assert.

## Phase 1 — Design & Contracts

Complete.

- [data-model.md](./data-model.md) — the tri-state and its transitions, the new routes through it,
  and the `received_total` derivation. Explicitly: no schema change, no migration.
- [contracts/stock-card-ui.md](./contracts/stock-card-ui.md) — the element ids the E2E suite binds
  to, which existing ones must not move, and what the three new ones are.
- [contracts/quantity-commit.md](./contracts/quantity-commit.md) — the request the client sends,
  the one value it must never send, the validation order, and a table of behavioral equivalences
  that must still hold afterwards.
- [quickstart.md](./quickstart.md) — how to run this and see it work.

## Complexity Tracking

No Constitution Check violations. Nothing to justify.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *(none)*  | —          | —                                    |
