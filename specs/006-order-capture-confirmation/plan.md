# Implementation Plan: Order Capture Confirmation

**Branch**: `issues/58` | **Date**: 2026-08-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-order-capture-confirmation/spec.md`

## Summary

Capture stops writing on arrival and starts writing on confirmation, and the whole feature follows from that one move.

`CatalogService.capture_order` (`app/catalog_service.py:866`) gains three inputs the operator supplies while the listing is on screen — `description`, `manufacturer`, `manufacturer_part_number` — and two that carry a decision they have already made: `acknowledged_duplicate_of` and `attach_to`. When it finds something it cannot decide alone — a purchase that looks like this one already, or a vendor item number that already names a product without corroboration — it raises `CaptureDecisionRequired` carrying a plain-data `CaptureAssessment`, and writes nothing. The route catches it exactly as it already catches `ValidationError`, re-renders the capture form with the warning panels, and the operator's choice comes back as a form field.

The bookmarklet's landing changes accordingly: `POST /api/capture` with a form body now **renders the pre-filled capture form** instead of creating a purchase and redirecting to the receive screen. Its JSON representation still writes, and still returns 201 on the unambiguous path, so `tests/unit/test_product_csrf.py:176` stands unaltered. The single CSRF exemption stays single, and gets narrower: the exempt path that arrives from a vendor's origin no longer writes anything at all.

One schema change: `purchases.listing_url`, a nullable `VARCHAR(1000)` on Alembic revision `b1a0c0d10008`. FR-013 requires the duplicate check to fall back to the listing address when the URL yields no item number, and today that address is smuggled into `purchases.notes` — a field the receive screen invites the operator to overwrite. The revision backfills the column from `notes` where notes holds a URL, and its `downgrade` folds the value back into an empty `notes` before dropping, so the round trip loses nothing in either direction.

At the other end, `receive_purchase` (`app/catalog_service.py:971`) takes a `description` and applies it in the same transaction that sets the received date — including on an already-received purchase, where the received date is a no-op and the description is not.

Deliberately **not** built: a drafts table or any server-side session storage (an unconfirmed capture is a form, not a record); URL normalization (see [research.md](./research.md#why-the-url-is-compared-exactly)); any new JavaScript; a link back to the vendor's listing from the receive screen, which the new column would make trivial and which no requirement asks for; and any change to what receiving does to a tracked quantity, which the spec excludes.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x (app-factory, blueprints), SQLAlchemy 2.0.x (legacy `Query` API, matching `catalog_service.py`), Alembic, Jinja2 + Bootstrap 5.3.2. No new dependency, and no new JavaScript file — every part of the confirmation step is server-rendered.

**Storage**: MariaDB via PyMySQL. Adds `purchases.listing_url`. Reads and writes `products` (description, manufacturer, manufacturer_part_number), `purchases`, and `product_identifiers`. No other table is touched.

**Testing**: `nox -s tests` (pytest + SQLite through the `Storage` seam), `nox -s e2e` (Playwright against a MariaDB testcontainer, 15-minute tool timeout), plus a **manual Alembic round-trip** — neither suite runs migrations (`tests/conftest.py:51` and `tests/e2e/test_server.py:62` both build the schema with `Base.metadata.create_all`).

**Target Platform**: Single Flask app on a home LAN, server-rendered HTML.

**Project Type**: Web application, single deployable. Existing structure; no new top-level directories.

**Performance Goals**: None stated and none measured. The duplicate lookup is one indexed-ish query over a table holding tens of rows, scoped to a one-day window. No index is added for `listing_url` — see [research.md](./research.md#why-listing_url-is-not-indexed).

**Constraints**: The deployment's collation — `utf8mb4_unicode_ci`, resolving to `utf8mb4_uca1400_ai_ci` on MariaDB 11 — folds case *and* accents, while SQLite collates `BINARY`. Every comparison this feature adds is classified in [research.md](./research.md#the-collation-question) as either Python-side (identical on both backends, provable by the unit suite) or SQL-side-and-harmless (a warning the operator can overrule). The corroboration test in FR-019 decides whether the operator is asked a question, so it is Python-side and not negotiable.

**Scale/Scope**: One operator, no concurrency. Roughly: 1 Alembic revision (schema + data, both directions), 1 new column, 1 new dataclass, 1 new exception, 3 changed service methods plus 2 private helpers, 3 changed routes, 2 changed templates, 0 new JS files. Two existing test classes assert behaviour this feature inverts and are rewritten rather than deleted.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1 design — see below.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | No drafts table, no server-side session, no client-side state, no new endpoint, no new JS. An unconfirmed capture is a rendered form and nothing else, which is why FR-009 ("leave no trace") costs zero lines to satisfy. The decision round-trip is an ordinary form re-render — the same shape the routes already use for `ValidationError`. The one thing added rather than avoided is the `CaptureDecisionRequired` exception, and it is justified below rather than waved through. **PASS** |
| **II. Layered Architecture Boundaries** | `CaptureAssessment` is a `@dataclass` in `app/models.py` where domain types live; the new column goes in `app/database.py`; all logic — detection, corroboration, attach-or-create — lives in `CatalogService`. The routes parse the form, call one service method, catch two exceptions, and render. No ORM query and no raw SQL in a route. The Alembic revision is the only place raw SQL appears, wrapped in `sa.text(...)`. **PASS** |
| **III. Exact Numerics** | Price handling is untouched: `capture_order` and `receive_purchase` both keep routing price through `_validate_price`, which refuses a `float` outright. This feature adds no arithmetic of any kind. **PASS** |
| **IV. Test Discipline Through Nox** | Unit tests cover every new service behaviour, and the corroboration rule is deliberately Python-side so SQLite can prove it. E2E covers each of the four user stories against MariaDB. Two existing classes assert the inverted behaviour — `TestIdempotency` (`tests/unit/test_capture.py:82`) and `test_capturing_the_same_listing_twice_creates_nothing_new` (`tests/e2e/test_order_capture.py:48`) — and are rewritten to assert the new contract, not deleted. Every new wait is on an element; the capture and receive flows are full-page form navigations, so `expect(...)` on the landed page is the whole wait. No new pytest marker. **PASS** |
| **V. MariaDB Is the Source of Truth** | One revision, `b1a0c0d10008`, on the current head `b1a0c0d10007`. It carries data in both directions: `upgrade` backfills `listing_url` from `notes`, `downgrade` folds it back into an empty `notes` before dropping the column, so neither direction loses a URL. **Neither test suite runs Alembic**, so this has no automated coverage; the scripted round-trip in [quickstart.md](./quickstart.md#3-exercise-the-migration-both-ways) is a required step, not a suggestion, and it runs against a disposable MariaDB container rather than the deployment. **PASS — with an obligation recorded** |
| **VI. Item Lifecycle and History Invariants** | `inventory_items` is neither read nor written. No add, move, shorten, edit, or search path for inventory items is touched. **N/A** |
| **Operating Context / Threat Model** | The exemption count stays at one, so the assertion at `tests/unit/test_product_csrf.py` that counts `@csrf.exempt` still passes. The exemption also gets *narrower*: the form representation of `/api/capture` — the one that arrives from a vendor's origin — now renders a page and writes nothing. No sanitization layer, no new validation-as-defense. Descriptions render through Jinja autoescaping as they already do. **PASS** |
| **Technology Constraints** | Server-rendered Jinja + Bootstrap, no frontend framework, no build step, no new dependency. New code carries type hints and raises the project's own exceptions. SQLAlchemy stays on the legacy `Query` API to match the surrounding file. **PASS** |
| **Development Workflow** | Feature branch `issues/58`, merged via PR. `app/templates/product/**` changes, so `nox -s screenshots_headless` runs — the screenshot set contains no product-catalogue page, so the expected result is *no diff*, and the run must leave the working tree clean. **PASS — with an obligation recorded in tasks** |

No violations. The Complexity Tracking table is therefore omitted.

### Why `CaptureDecisionRequired` is an exception and not a return value

This is the one design choice that adds a moving part, so it gets argued rather than asserted.

The alternative is a separate read — `assess_capture(...)` returning an assessment, which the route consults before calling `capture_order`. That is a two-call protocol, and the invariant FR-007 states ("MUST NOT create a product or a purchase until the operator confirms") would then be a property of *the route remembering to make the first call*. A route that forgets, or a second caller added later that never knew, silently gets the old silent behaviour back — and the failure is invisible, which is precisely the failure mode this feature exists to remove.

Raising from inside `capture_order` makes the invariant a property of the service. There is no way to reach a write without either supplying the decision or handling the signal. It also costs less code than the two-call version, because the assessment is built exactly once, at the point that already has the matched rows loaded.

The shape is not novel here: `product_capture` and `purchase_receive` already catch `ValidationError` and re-render the form from it. `CaptureDecisionRequired` is caught in the same `try` and rendered the same way. It subclasses `WorkshopInventoryError` but is deliberately *not* given a global handler — there is no registered handler for the base class today (`app/error_handlers.py` registers `ValidationError`, `StorageError`, `ItemNotFoundError`, `AuthenticationError`, `ConfigurationError`, 500 and 404), so an unhandled one would surface as a 500. That is the correct outcome: it is not an error page, it is a step in a flow, and any route that reaches it must say what to do.

### Post-design re-check (after Phase 1)

Re-read after [data-model.md](./data-model.md) and the contracts were written. Four points:

- **The migration is genuinely reversible, not merely re-runnable.** Dropping a column normally loses whatever was written into it. Here `downgrade` writes `listing_url` back into `notes` for rows whose notes are empty first, which restores exactly the pre-feature representation — the URL living in the notes field, which is where `capture_order` puts it today (`app/catalog_service.py:948`). A row whose notes the operator has since written into keeps those notes and loses the separate URL; that is stated in [data-model.md](./data-model.md#reversibility) rather than glossed. Still **PASS** under Principle V.
- **Capture stops writing the URL into `notes`.** That is a behaviour change beyond the letter of the spec, and it is the direct consequence of the column existing: keeping both would mean two copies of one fact, and the copy in `notes` is the one the receive screen lets the operator destroy. `tests/unit/test_capture.py:75` asserts the old placement and is rewritten. Still **PASS** under Principle I — one fact, one home.
- **`attach_to` naming a product that no longer exists falls back to creating one**, rather than raising. The spec's edge-case list calls for this ("it creates the product it would have created had there been no match"), and the alternative is an obscure failure on a page the operator cannot fix. It is logged. Still **PASS**.
- **The unit suite cannot prove the duplicate lookup's string comparisons**, because `listing_url` and `vendor` are compared in SQL and SQLite disagrees with the deployment about folding. This is accepted rather than fixed: both comparisons feed a *warning* the operator can overrule, so folding produces a question that need not have been asked, never a silent wrong write. The one comparison that decides something without asking — FR-019's corroboration — is Python-side for exactly this reason. Argued in [research.md](./research.md#the-collation-question). Still **PASS**.

## Project Structure

### Documentation (this feature)

```text
specs/006-order-capture-confirmation/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — decisions and rejected alternatives
├── data-model.md        # Phase 1 output — the column, the migration, the assessment type
├── quickstart.md        # Phase 1 output — how to run and validate, including the migration round-trip
├── contracts/
│   ├── catalog-service.md      # Changed and new CatalogService surface
│   └── http-routes.md          # Changed HTTP surface, including the bookmarklet landing
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 output — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
app/
├── models.py                       # + CaptureAssessment dataclass
├── exceptions.py                   # + CaptureDecisionRequired
├── database.py                     # + Purchase.listing_url column
├── catalog_service.py              # capture_order, _find_captured_purchase, receive_purchase,
│                                   #   record_purchase; + _corroborates, + _fold
├── product/
│   └── routes.py                   # product_capture, api_capture, purchase_receive
└── templates/product/
    ├── capture.html                # + description/manufacturer/MPN fields, + two decision panels
    └── receive.html                # description becomes editable

migrations/versions/
└── b1a0c0d10008_add_purchase_listing_url.py    # new

tests/
├── unit/
│   └── test_capture.py             # TestIdempotency rewritten; new classes for decisions,
│                                   #   corroboration, and description handling
└── e2e/
    └── test_order_capture.py       # two tests rewritten; four added, one per user story
```

**Structure Decision**: no new module, no new package, no new blueprint. Everything lands in files that already own the concept: the capture and receive routes are already together in `app/product/routes.py`, the capture and receipt service methods are already adjacent in `app/catalog_service.py`, and the two templates already exist. The only new file in `app/` would have been a JavaScript module for the decision UI, and there isn't one, because the decision UI is two Jinja blocks and a radio group.

## Phase 0 — Research

See [research.md](./research.md). It resolves:

- Where an unconfirmed capture lives between the bookmarklet's click and the operator's confirmation.
- Why the listing URL becomes a column instead of being matched out of `notes`.
- Why the URL is compared exactly, with no normalization layer.
- Which comparisons may be done in SQL and which must be done in Python, given the collation.
- Why the corroboration rule requires both manufacturer *and* part number.
- Why `listing_url` gets no index.

No `NEEDS CLARIFICATION` markers were carried in from the spec, and none were raised during design.

## Phase 1 — Design

- [data-model.md](./data-model.md) — the new column and its migration in both directions, the `CaptureAssessment` shape and why it carries plain values rather than an ORM row, and every existing reader of the fields this feature repurposes.
- [contracts/catalog-service.md](./contracts/catalog-service.md) — the changed `capture_order` and `receive_purchase` signatures, the new exception, and the decision-resolution rules stated as a table.
- [contracts/http-routes.md](./contracts/http-routes.md) — the changed behaviour of `POST /api/capture` in both representations, the decision fields on `POST /products/capture`, and the new `description` field on the receive form.
- [quickstart.md](./quickstart.md) — how to run each user story by hand, and the required Alembic round-trip against a disposable container.
