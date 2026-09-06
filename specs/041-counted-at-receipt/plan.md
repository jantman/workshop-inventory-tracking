# Implementation Plan: An Explicit "I Counted the Shelf" at Receipt

**Branch**: `robot-army/issue-149-explicit-i-counted-the-shelf-option` | **Date**: 2026-09-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/041-counted-at-receipt/spec.md`

## Summary

Feature 008 stopped a receipt from refreshing a count's age. That was right, and it stays. It
left the operator with no way to say they *had* counted while the box was open, short of
finishing the receipt, opening the product, and re-typing a number.

This adds one opt-in checkbox to the receive form. Ticked, the receipt records the count's age
as well as the count. Untouched — its state on every page load — nothing about today's
behaviour moves.

Four files carry the change, and one docstring gives an instruction that would undo it:

1. **`CatalogService.receive_purchase`** (`app/catalog_service.py:1571`) gains
   `counted: bool = False`. When it is true and the product has a tracked count, the method sets
   `product.quantity_updated_at = utc_now()`. The write sits *outside* the
   `if not already_received` guard, next to the description amendment, for the same reason that
   one does: it is an assertion the operator is making now, not a repeat of the receipt's
   arithmetic. It is guarded by `product.quantity is not None` and deliberately **not** by
   `purchase.quantity` — the operator looked at the shelf whether or not the delivery carried a
   number.
2. **`product.purchase_receive`** (`app/product/routes.py:957`) reads
   `request.form.get('counted') == 'on'` and passes it through, matching the
   `identifier_override` precedent already in the file. The refusal path already re-renders with
   `form_data=request.form`, so nothing there changes.
3. **`app/templates/product/receive.html`** grows a Bootstrap `form-check` inside the "What
   actually arrived" card, shown only when `product.quantity is not none`, unticked unless
   `form_data` says the operator ticked it. Its already-received banner, which enumerates what a
   second submission does and does not touch, gains the count assertion to that list.
4. **`docs/user-manual.md`** states the old absolute rule in two places ("Receiving an order
   adds to the count without touching the age" and "What receiving deliberately leaves alone is
   the *count's* age"). Both become the rule plus its one named exception.
5. **`Product.quantity_age`** (`app/database.py:951`) currently instructs the reader: "Do not
   restore a timestamp write to `receive_purchase`". After this change there is one. The warning
   is narrowed to the unconditional write it was actually written against, rather than deleted.

Plus the amendment issue #149 asks for: `specs/008-trustworthy-stock-age/spec.md`'s FR-008,
SC-001, SC-003 and three passages of prose are brought into agreement with the code, keeping the
carve-out and naming its exception.

No schema change, no Alembic revision, no new service, no new route, no JavaScript, no new
dependency. The count itself, the manual flag, the reorder list, the age wording and every other
receive behaviour are untouched.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x (app-factory), SQLAlchemy 2.0.x, Jinja2, Bootstrap 5.3.2.
No new dependency, and no JavaScript — the control is a plain form field on a form that already
posts.

**Storage**: MariaDB via SQLAlchemy in production, SQLite through the same interface in unit
tests. **Unchanged.** `products.quantity_updated_at` already exists with exactly the meaning
this feature writes into it; no column, index or constraint is touched and there is no
migration. Constitution V has nothing to apply to.

**Testing**: `nox -s tests` (pytest, network blocked) and `nox -s e2e` (Playwright,
`-m "e2e and not screenshot"`). New unit tests go in `tests/unit/test_stock_status.py`, beside
the existing feature-008 receive tests; a new E2E test goes in `tests/e2e/test_stock_age.py`,
beside `test_receiving_does_not_reset_a_counted_age`, whose seeding and waiting it mirrors.

**Target Platform**: Server-rendered Flask app on a home LAN, single operator, often driving the
receive screen from a phone while unpacking.

**Project Type**: Web application — Flask blueprints, service layer, Jinja templates.

**Performance Goals**: None. The change adds one assignment inside a session that is already
open.

**Constraints**: The unticked path must be provably identical to today's behaviour (spec Story
2). The default on `receive_purchase` is what makes every existing call site — twenty-odd unit
tests, all of them asserting the 008 rule — a regression net for that without editing one of
them.

**Scale/Scope**: One service method, one route, one template, one docstring, two documentation
files, one amended spec. Roughly 40 lines of application change and a comparable amount of test.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* Checked against
`.specify/memory/constitution.md` v1.3.0.

| Principle | Assessment |
|---|---|
| **I. Simplicity First (NON-NEGOTIABLE)** | **PASS.** One boolean keyword argument with a `False` default, one checkbox, one conditional assignment. No new abstraction, no configuration knob, no per-purchase record of whether the assertion was made, no third state on the boolean. Three simpler-looking alternatives were considered and rejected in [research.md](./research.md) for being *more* machinery, not less. |
| **II. Layered Architecture Boundaries** | **PASS.** The rule about what receiving may assert lives in the service, where it is today. The route parses one form value and passes it; it runs no query and no ORM code. The template makes a display decision only — and the service keeps its own guard, so hiding the control is not what enforces the rule. |
| **III. Exact Numerics** | **N/A.** No measured quantity is touched. The count is an `Integer` and stays one. |
| **IV. Test Discipline Through Nox** | **PASS.** Run via `nox -s tests` and `nox -s e2e`; no new pytest marker. Behaviour change lands with tests. The new E2E test waits on `#quantity-value` and `#quantity-age` — server-rendered after a redirect — with `expect()`, no fixed wait, no `networkidle`, and seeds through `CatalogService` and `live_server.backdate_product` rather than driving forms. |
| **V. MariaDB Is the Source of Truth** | **PASS, vacuously.** No schema change, so no Alembic revision. Nothing calls `create_all` outside fixtures. |
| **VI. Item Lifecycle and History Invariants** | **N/A.** Products and purchases, not inventory items. No JA ID, no active-row or shortening path is touched. |
| **Operating Context and Threat Model** | **PASS.** CSRF stays as it is — the form already carries its token. No auth, no sanitization layer. The one validation involved (the boolean) exists so bad data does not break the inventory. |
| **Technology Constraints** | **PASS.** Server-rendered Jinja + Bootstrap, no frontend framework and no build step. New code carries type hints. `session.query(...)` style matches the surrounding file. `app/api_client.py` is untouched. |
| **Development Workflow and Quality Gates** | **PASS.** Feature branch and PR. `app/templates/**` changes, so screenshots are regenerated and verified per the gate — see the note below. |

**No violations. The Complexity Tracking table below stays empty.**

**On the screenshot gate**: the gate requires regeneration when `app/templates/**` changes, so
`nox -s screenshots_headless` and `nox -s screenshots_verify` are run. No documentation
screenshot shows the receive screen ([research.md](./research.md)), so the expectation is that
no PNG changes. `metadata.json` carries a `generated_at` that churns on every run regardless, so
the regeneration is run to *prove* nothing moved; only genuinely-changed images are committed,
and if none changed, nothing is.

**Post-Phase 1 re-check**: unchanged. The design produced no new file, no new module, no new
interface, and no entity. It is smaller than the plan above implies, because most of the listed
work is prose.

## Project Structure

### Documentation (this feature)

```text
specs/041-counted-at-receipt/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── receive-purchase.md   # Phase 1 output: the service and form contract
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
app/
├── catalog_service.py          # receive_purchase gains `counted`
├── database.py                 # Product.quantity_age docstring warning narrowed
├── product/
│   └── routes.py               # purchase_receive reads and forwards the checkbox
└── templates/product/
    └── receive.html            # the control, and the already-received banner's list

docs/
└── user-manual.md              # the two statements of the old absolute rule

specs/008-trustworthy-stock-age/
└── spec.md                     # FR-008 and its neighbours, amended not superseded

tests/
├── unit/
│   └── test_stock_status.py    # the ticked and unticked service paths
└── e2e/
    └── test_stock_age.py       # the operator ticking the box on the real screen
```

**Structure Decision**: No new module, package or directory. Every change lands in a file that
already owns the behaviour it changes — the service rule in the service, the form parse in the
route that owns the form, the control in that form's template. This follows the existing
blueprint/service layout described in Constitution II rather than extending it.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

None. The Constitution Check found no violations.
