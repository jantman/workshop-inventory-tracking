# Implementation Plan: Bulk-Receiving Outstanding Purchases from a Backfill

**Branch**: `robot-army/issue-140-no-way-to-bulk-receive-already-captured` | **Date**: 2026-09-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/042-bulk-receive-outstanding/spec.md`

## Summary

One management command that marks outstanding purchases received, dated from their own order
date — the retroactive equivalent of the capture-time "this order has already arrived" tick
feature 031 shipped.

```
python manage.py orders receive-outstanding --before 2026-01-01 [--vendor DigiKey] [--dry-run]
```

Five files carry it, and no schema, template, route, JavaScript or dependency changes:

1. **`app/models.py`** gains two frozen dataclasses beside `CapturedOrder` and
   `PurchaseDeletion`: `OutstandingReceipt` (one candidate line, flattened for rendering) and
   `OutstandingReceiptPlan` (the candidates plus the count of purchases skipped for having no
   order date), with a `render()` that produces the operator-facing listing. The `render()`
   precedent is `app/services/amazon_order_export.py`'s summary, which `manage.py` prints the
   same way.
2. **`CatalogService.plan_outstanding_receipts(vendor=None, before=...)`**
   (`app/catalog_service.py`, beside `find_captured_orders`) selects the outstanding, dated
   purchases before the cutoff and returns the plan. Reads only.
3. **`CatalogService.apply_outstanding_receipts(plan)`** sets `received_date = order_date` on
   each of the plan's purchases inside one `_session()` block and returns how many it wrote.
   **It writes that one column and nothing else** — no count, no count age, no stock flag, no
   quantity, price, notes or description. That is 031 FR-028 and the load-bearing decision of
   this feature.
4. **`manage.py`** gains `orders receive-outstanding` in the existing `orders` group: parse,
   plan, print, stop if `--dry-run` or empty, confirm, apply, report.
5. **`docs/user-manual.md`** gains a subsection after **Saying it already arrived**, restating
   the two things a backfill receipt deliberately does not do.

Plus `tests/unit/test_bulk_receive.py`: the selection rules, the date rule, and — the tests that
matter — that a swept purchase moves no on-hand count, no count age and no manual flag.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Click (already the CLI framework for `manage.py`), SQLAlchemy 2.0.x.
No new dependency. `click.DateTime` is stock Click and is what refuses a bad `--before`.

**Storage**: MariaDB via SQLAlchemy in production, SQLite through the same interface in unit
tests. **No schema change and no Alembic revision** — `purchases.received_date` already exists
with exactly the meaning this feature writes into it, and is already indexed. Constitution V has
nothing to apply to.

**Testing**: `nox -s tests` (pytest, network blocked). New unit tests in
`tests/unit/test_bulk_receive.py`, driving `CatalogService(test_storage)` the way
`tests/unit/test_order_backfill.py` does, plus `click.testing.CliRunner` coverage of the
command's dry-run / confirm / decline / empty paths. **No E2E test and no screenshots**: there
is no page. `nox -s e2e` must still pass and is untouched.

**Target Platform**: A command run at a terminal on the machine hosting the app, a handful of
times during a historical backfill. Not a screen, not scheduled, not an API.

**Project Type**: Single Flask application with a Click management CLI.

**Performance Goals**: None. The largest realistic sweep is a few hundred rows of a table
holding a few thousand.

**Constraints**: The sweep lands whole or not at all (FR-020) — satisfied by `_session()`, which
already commits on success and rolls back on any exception.

**Scale/Scope**: One operator, one backfill, a few thousand purchases in total.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1 design — see the re-check below.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First (NON-NEGOTIABLE)** | **PASS.** A command, not a screen, because the ask is a one-time job. Two selection filters and no third, no `--order`, no id list, no interactive picker — the issue is explicit that per-line handling belongs to the existing screens. No new module, no new abstraction: two methods on the service that already owns purchases, and two dataclasses beside the ones that already describe purchase outcomes. The write is a loop rather than a single correlated `UPDATE` precisely because there is no measurement to justify the cleverer form. |
| **II. Layered Architecture Boundaries** | **PASS.** All logic in `CatalogService`; `manage.py` parses arguments, prints, and prompts. No ORM query outside the service. The dataclasses live in `app/models.py` with `CapturedOrder` and `PurchaseDeletion`, which is where this codebase puts service return types. |
| **III. Exact Numerics** | **PASS, with care.** The feature does no arithmetic at all. `unit_price` is not read or written; `quantity` is read only to render it in the listing. No `float` appears. |
| **IV. Test Discipline Through Nox** | **PASS.** Tests run through `nox -s tests`. No new pytest marker (`pytestmark = pytest.mark.unit`, already registered). Unit tests mock nothing external because nothing external is touched, and the network stays blocked. No E2E test is added, so the waiting rules have nothing to bind; `nox -s e2e` is unaffected. |
| **V. MariaDB Is the Source of Truth** | **PASS.** No schema change, therefore no migration. No raw SQL. No `create_all` outside fixtures. The write goes through the ORM inside `_session()`. |
| **VI. Item Lifecycle and History Invariants** | **NOT APPLICABLE.** This feature does not touch `inventory_items`, JA IDs, shortening history or parent-child links. It reads and writes one column of `purchases`. |
| **Operating Context and Threat Model** | **PASS.** No auth, no sanitization layer, no new surface. Validation exists because a bad cutoff date would sweep the wrong rows, not because anyone hostile is typing it. The confirmation prompt is there to protect the operator from a typo, which is a correctness concern. |
| **Technology Constraints** | **PASS.** Legacy `Query` API, matching the surrounding file. Type hints on every new public method. Errors raised as the project's own `ValidationError` from `app/exceptions.py` where the service refuses something; Click reports its own argument errors. `app/api_client.py` untouched. |
| **Development Workflow and Quality Gates** | **PASS.** Feature branch and PR. No `app/templates/**`, `app/static/css/**` or `app/static/js/**` change, so the screenshot gate does not trigger. |

**Result: no violations. The Complexity Tracking table below stays empty.**

### Post-design re-check (after Phase 1)

Re-read after `data-model.md`, `contracts/` and `quickstart.md` were written. Nothing changed
the assessment. The three points worth restating because the design made them concrete:

- **The two dataclasses are the smallest thing that works, not a DTO tier.** `manage.py` needs
  to print a listing, prompt, and then write the exact rows it printed. A list of `Purchase` ORM
  instances would work for the printing and not for the rest — the objects belong to a closed
  session, and `expire_on_commit=False` makes reading them afterwards work by luck rather than
  by design. Flattening to a frozen record is what `PurchaseDeletion` already does for the same
  reason, stated in its own docstring.
- **Two methods, not one with a `dry_run` flag.** The read is the thing the operator confirms;
  the write takes what they confirmed. This is fewer branches, not more.
- **No `receive_purchase` reuse and no `backfill=` flag on it.** Argued in `research.md` §3. A
  method whose central behaviour is switched off by a boolean is two methods sharing a name.

## Project Structure

### Documentation (this feature)

```text
specs/042-bulk-receive-outstanding/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── cli-receive-outstanding.md    # the command's contract
│   └── service-receipts.md           # the two CatalogService methods
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
app/
├── models.py            # + OutstandingReceipt, OutstandingReceiptPlan
└── catalog_service.py   # + plan_outstanding_receipts, apply_outstanding_receipts

manage.py                # + orders receive-outstanding

docs/
└── user-manual.md       # + "If you forgot to say it", after "Saying it already arrived"

tests/
└── unit/
    └── test_bulk_receive.py    # new
```

**Structure Decision**: The existing layout, unchanged. No new package, no new module. The
service method goes beside `find_captured_orders` in the order-reading section of
`catalog_service.py`; the command goes in the `orders` group that `amazon-urls` already
established for backfill helpers.

## Phase 0: Research

Complete — see [research.md](./research.md). The spec carried no `[NEEDS CLARIFICATION]`
markers; research settled the date rule (§2), the deliberate non-reuse of `receive_purchase`
(§3), where the logic lives (§4), the write shape (§5), the selection predicate (§6), which
arguments exist and which are deliberately refused (§7), the issue's outdated irreversibility
premise (§8), and the test and documentation shape (§9, §10).

## Phase 1: Design

Complete — [data-model.md](./data-model.md), [contracts/](./contracts/),
[quickstart.md](./quickstart.md).

## Complexity Tracking

No Constitution Check violations. Nothing to justify.
