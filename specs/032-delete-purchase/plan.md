# Implementation Plan: Delete a Purchase

**Branch**: `032-delete-purchase` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/032-delete-purchase/spec.md`

## Summary

Give the operator a way to delete a single purchase, from the product page's purchase
history and from the order screen, behind a confirmation that names the purchase and
states its two invisible consequences. Closes issue #130, which is the precondition for
recovering from #129 and for roughly twenty parked manual verification checks.

The approach is deliberately small: **one service method, one route, one new template,
two touched templates, and no schema change.** Deletion is a server-rendered
GET-confirm / POST-delete page — the same shape `purchase_receive` already has — reached
from both entry points, so FR-015's "identical wherever it is offered" costs nothing to
hold. `Purchase.attachments` already cascades at both the ORM and the database level, so
the only genuinely new logic is dropping a stored photo that nothing references any more,
in the same transaction (FR-006, FR-012).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x (app-factory), SQLAlchemy 2.0.x (legacy `Query`
API, matching the surrounding files), Jinja2 + Bootstrap 5.3.2 server-rendered UI. No new
dependency, and no new JavaScript.

**Storage**: MariaDB via PyMySQL, source of truth. Unit tests run the same code against
SQLite through the `Storage` ABC. **No schema change and therefore no Alembic revision** —
the two foreign keys this feature relies on (`product_attachments.purchase_id` →
`purchases.id` `ON DELETE CASCADE`, and `product_attachments.photo_id` → `photos.id`)
already exist from `b1a0c0d10005`.

**Testing**: `nox -s tests` (pytest, network blocked, fixtures through
`tests/conftest.py`) and `nox -s e2e` (Playwright, `-m "e2e and not screenshot"`).

**Target Platform**: Linux, single Flask process on a home LAN.

**Project Type**: Server-rendered Flask web application.

**Performance Goals**: None, and none are to be invented. A deletion is one `SELECT`, one
`DELETE` that cascades to a handful of attachment rows, and at most a few photo deletes.
Principle I forbids adding caching or batching without a measurement, and there is
nothing here to measure.

**Constraints**: The confirmation must render `unit_price` from its `Decimal` without
passing through `float` (Principle III). CSRF stays enabled, so the POST form carries
`csrf_token()`. Template changes trigger the screenshot regeneration gate.

**Scale/Scope**: One operator; a few thousand purchases at the outside; one purchase
deleted at a time.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Basis |
|---|---|---|
| **I. Simplicity First** | PASS | No new dependency, table, migration, JS file, or abstraction. No soft delete, trash, undo or audit row — the confirmation is the safeguard, and a tombstone table would be scale machinery for one person's typo. No bulk selection. One service method, one route, one template. |
| **II. Layered Architecture Boundaries** | PASS | Deletion logic lands in `CatalogService`; the route stays thin (load, render, call, flash, redirect) with no ORM query or raw SQL. `CatalogService` reads `Photo` / `ProductAttachment` / `ItemPhotoAssociation` from `app/database.py` — the ORM layer it already consumes — rather than acquiring a second service. No new layer or repository. |
| **III. Exact Numerics** | PASS | The only measured quantity in play is `unit_price`, a `Numeric(10, 2)` → `Decimal`. It is rendered on the confirmation and echoed in the flash; it is never arithmetic'd and never converted to `float`. The feature performs no arithmetic on any measurement — notably it does **not** subtract a received quantity from the product's count (FR-007). |
| **IV. Test Discipline Through Nox** | PASS | Unit tests for the service method and the route; E2E for both entry points. Run through `nox`. Every E2E wait is a navigation or an `expect()` on a rendered row — the flow is form-POST-and-redirect, so there is no `fetch` boundary and no dialog to trap. No new pytest marker. |
| **V. MariaDB Is the Source of Truth** | PASS | No schema change, so no revision and no `downgrade` to exercise. The whole deletion — purchase, attachment rows, newly-unreferenced photos — happens inside one `CatalogService._session()`, which commits once or rolls back entirely (FR-012). |
| **VI. Item Lifecycle and History Invariants** | PASS (not engaged) | Purchases are catalog rows. No JA ID, no `InventoryItem`, no active/inactive row, no parent-child link is read or written. A unit test asserts that deleting a purchase leaves `inventory_items` untouched, so the "not engaged" claim is checked rather than asserted. |
| **Operating Context / Threat Model** | PASS | No auth is added. CSRF stays on because it is already wired up. The redirect target is **not** a caller-supplied URL — see research R3 — so there is no open-redirect question to answer and no sanitization layer to add. |
| **Workflow gates** | NOTED | Non-trivial code change → feature branch + PR. `app/templates/**` changes → `nox -s screenshots` regenerated and committed, passing `screenshots_verify`. |

**Result: no violations. Complexity Tracking is empty.**

Re-checked after Phase 1 design: unchanged. The design added one value object
(`PurchaseDeletion`) and one template, both alongside existing peers of the same kind.

## Project Structure

### Documentation (this feature)

```text
specs/032-delete-purchase/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── purchase-delete.md   # Phase 1 output: HTTP + service contracts
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
├── models.py                        # + PurchaseDeletion value object
├── catalog_service.py               # + CatalogService.delete_purchase()
├── database.py                      # unchanged (FKs and cascades already present)
├── photo_service.py                 # unchanged
├── product/
│   └── routes.py                    # + purchase_delete (GET/POST)
├── templates/product/
│   ├── purchase_delete.html         # NEW: the confirmation
│   ├── detail.html                  # + per-row Delete control (US1)
│   └── order.html                   # + per-line Delete control (US2)
└── static/js/                       # untouched — no JavaScript in this feature

tests/
├── unit/
│   ├── test_purchase_delete.py      # NEW: service + route behavior
│   └── test_purchase_history.py     # existing peer, for reference
└── e2e/
    └── test_purchase_delete.py      # NEW: both entry points, end to end

docs/
├── user-manual.md                   # + how to remove a purchase recorded in error
└── images/screenshots/              # regenerated (template change gate)

migrations/                          # untouched — no schema change
```

**Structure Decision**: The existing Flask layout is used as-is. This feature adds no
directory and no module: the service method joins its peers in `app/catalog_service.py`,
the route joins `purchase_receive` in `app/product/routes.py`, the value object joins
`OrderCaptureResult` and friends in `app/models.py`, and the confirmation template joins
`receive.html` in `app/templates/product/`.

## Complexity Tracking

> No Constitution Check violations. This section is intentionally empty.
