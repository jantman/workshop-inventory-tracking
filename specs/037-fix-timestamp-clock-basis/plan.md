# Implementation Plan: One Clock for Recorded Timestamps

**Branch**: `speckit/037-fix-timestamp-clock-basis` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/037-fix-timestamp-clock-basis/spec.md`

## Summary

Every timestamp the application records for itself moves onto one basis — **naive UTC, produced
in Python** — and every place that compares one against "now" moves with it. A single module,
`app/utils/clock.py`, becomes the only answer to "what time is it, for the purpose of recording
an event", and the column defaults in `app/database.py` stop asking the database server.

The five call sites that default a *calendar day* rather than an instant — order date, received
date, arrival date, the year for a bare "14 Mar", the purchase date — stay on local time and say
so by calling `local_now()`, because converting them would move an evening entry onto the next
day.

No schema change, no Alembic revision, no migration of existing rows. Research (R6) records the
one accepted consequence: ages already stored on the local clock will read about four hours older
after the deploy, once, and then never again.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x, SQLAlchemy 2.0.x (legacy `Query` style), Alembic, Jinja2 —
no new dependency. The fix is standard-library `datetime` only.

**Storage**: MariaDB via PyMySQL, `DateTime` columns (no offset stored). SQLite through the same
`Storage` interface for unit tests.

**Testing**: `nox -s tests` (unit, sub-second, network blocked) and `nox -s e2e` (Playwright,
`-m "e2e and not screenshot"`, 15-minute timeout, run detached per `CLAUDE.md`).

**Target Platform**: single Linux host on a home LAN; one operator; the host's local timezone is
`America/New_York` in this deployment.

**Project Type**: server-rendered Flask web application.

**Performance Goals**: none. The change replaces one call with another call; there is nothing to
measure.

**Constraints**: the stored column type cannot carry an offset, so the basis has to be a
convention rather than a type (research R2). Existing rows are not correctable and are not
touched (R6).

**Scale/Scope**: 10 column definitions, roughly 20 write call sites, 2 read properties, 2 e2e
seed helpers. One new module of two functions.

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Principle | Verdict | Note |
|---|---|---|
| **I. Simplicity First** | PASS | One module, two functions, no configuration knob, no clock-injection framework, no migration. Both functions have live call sites today — neither is speculative. The one deliberate restraint is R7: log and report timestamps are left alone rather than swept along. |
| **II. Layered Architecture Boundaries** | PASS | The helper lands in `app/utils/`, which is where the workflow rules put helpers. No layer is collapsed and no boundary moves. The change slightly *improves* the boundary by deleting four writes in `app/main/routes.py` that set persistence fields the service then discards (R1). |
| **III. Exact Numerics** | N/A | No measured quantity is touched. No `Decimal` and no `float` appears in this feature. |
| **IV. Test Discipline Through Nox** | PASS | Run through `nox`. New coverage is unit-level (R9); no new pytest marker; no new e2e test, so no new wait of any kind is introduced. Two existing e2e seed helpers are retargeted, and neither gains a fixed wait. |
| **V. MariaDB Is the Source of Truth** | PASS | No schema change and therefore no Alembic revision (R3 — SQLAlchemy `default=` is client-side, not DDL). The existing `server_default` DDL is deliberately left in place and becomes unreachable; R4 records why removing it would cost a migration to delete a dead path. |
| **VI. Item Lifecycle and History Invariants** | **TOUCHED — gated** | `inventory_items.date_added` orders history rows and selects the current row (R8). Nothing is observably wrong today, but only because this deployment is west of Greenwich. The existing active-status and history e2e tests are a required gate for this feature, not an optional one. |

**Operating Context / Threat Model**: unchanged. This is the data-integrity carve-out — stored
data that does not mean what it says — not hardening.

No violations. Complexity Tracking is therefore omitted.

## Project Structure

### Documentation (this feature)

```text
specs/037-fix-timestamp-clock-basis/
├── plan.md              # This file
├── research.md          # Phase 0 output — R1..R10 and the decision table
├── data-model.md        # Phase 1 output — the column inventory and its two kinds
├── quickstart.md        # Phase 1 output — reproduce, verify, and what changes on deploy
├── contracts/
│   └── clock.md         # The application clock's surface, and the unchanged JSON contract
└── checklists/
    └── requirements.md  # Spec quality checklist (from /speckit-specify)
```

### Source Code (repository root)

```text
app/
├── utils/
│   └── clock.py                        # NEW — utc_now(), local_now()
├── database.py                         # 10 column defaults; 2 age properties (:967, :983)
├── catalog_service.py                  # recorded: :223, :445, :499
│                                       # calendar (stay local): :1151, :1620, :2072
├── mariadb_materials_admin_service.py  # recorded: :180, :181, :250, :354
├── mariadb_inventory_service.py        # recorded: :603, :637, :638, :953, :1133, :1166
├── mariadb_storage.py                  # recorded: :430, :442
├── photo_service.py                    # recorded: :118, :119, :133, :423, :873
├── models.py                           # calendar (stays local): :1438
└── main/routes.py                      # dead writes to delete: :742, :2403, :2472, :2473

tests/
├── unit/
│   └── test_clock_basis.py             # NEW — the two tests from R9, plus FR-008
└── e2e/
    ├── test_stock_age.py               # days_ago() seeds onto the application clock
    └── test_reorder_view.py            # same, at :236 and :239
```

**Structure Decision**: the existing layout, unchanged. The only new file is
`app/utils/clock.py`, placed per the workflow rule that helpers live in `app/utils/`. Nothing
moves between layers and no new package appears.

## Phase 0: Research

Complete — see [research.md](./research.md). Ten questions, summarized by the decision table at
its end. The three findings that shaped the plan:

- **The bug is on two tables, not one** (R1). `material_taxonomy` has the identical defect, unreported:
  `mariadb_materials_admin_service` passes local `datetime.now()` over the UTC column defaults.
- **`date_added` selects the current history row** (R8). That puts Principle VI in the path and
  makes the existing history e2e tests a gate. Today's ordering is correct only because local
  time here runs behind UTC; the same code inverts history east of Greenwich.
- **The naive regression test passes on the bug** (R9). SQLite's `CURRENT_TIMESTAMP` is UTC, so
  "assert the two columns agree" only fails on a machine that is not on UTC. The timezone has to
  be forced in the test, or the clock has to be patched — the plan does both, once each.

No `NEEDS CLARIFICATION` items were raised in Technical Context, and none survive from the spec.

## Phase 1: Design

### The clock module

Two functions, both returning naive `datetime`, documented in [contracts/clock.md](./contracts/clock.md):

- `utc_now()` — the instant an event was recorded. Every persisted recorded timestamp, and both
  sides of every age subtraction, come from here.
- `local_now()` — the operator's wall clock, for defaulting a calendar day they would otherwise
  have typed. Five call sites, enumerated in [data-model.md](./data-model.md).

Naive rather than aware, for the reason in R2: the column cannot hold an offset, and this
codebase has already taken a production 500 from mixing the two (`app/models.py:_naive`, PR #128).

### The sweep

1. **Column defaults** (`app/database.py`, 10 columns): `default=func.now()` → `default=utc_now`,
   `onupdate=func.now()` → `onupdate=utc_now`. Client-side default, so no DDL and no revision.
2. **Recorded write sites** (roughly 20, listed in the tree above): every `datetime.now()`,
   `datetime.now(timezone.utc)`, `datetime.utcnow()` and stray `func.now()` assignment becomes
   `utc_now()`. This also retires the `datetime.utcnow()` calls, which are deprecated on 3.13.
3. **Read sites** (`app/database.py:967,983`): `datetime.now() - self.<column>` becomes
   `utc_now() - self.<column>`. These are the only two places an age is computed; the renderer at
   `app/product/routes.py` takes a `timedelta` and needs no change.
4. **Calendar sites** (5, listed above): `datetime.now()` → `local_now()`. Same value, named
   intent. `catalog_service.py:1151` keeps its `.replace(hour=0, ...)`.
5. **Dead writes** (`app/main/routes.py:742,2403,2472,2473`): deleted, not converted (R1, D8).

### Interface contracts

The feature exposes no new external interface, and deliberately changes none.
[contracts/clock.md](./contracts/clock.md) documents two things: the internal clock surface above,
and the JSON timestamp contract that must **not** change — same field names, same naive ISO-8601
text, same absence of an offset (FR-010). Only the values become mutually consistent.

### Data model

[data-model.md](./data-model.md) is the authoritative inventory: every persisted timestamp column,
which of the two kinds it is, who writes it today, and what it becomes.

### Validation

[quickstart.md](./quickstart.md) covers reproducing the defect before the fix, the automated
checks, the by-hand verification, and — the part that is not a test — what the operator should
expect to see change on the first deploy (R6).

### Post-Design Constitution Re-check

Re-evaluated against the design above; the verdicts in the Constitution Check table stand.

Two points are worth restating because the design is where they could have gone wrong:

- **Principle I.** The design was pushed twice more toward less. The clock module has no
  injectable now, no freeze hook, and no configuration: tests patch the module attribute, which
  is the ordinary Python thing to do and needs no production affordance. And R7's line — logs and
  report labels stay local — is held, so the diff stops at persisted data instead of touching
  every `datetime.now()` in the tree.
- **Principle VI.** Because `date_added` selects the current history row, the design does not
  treat `inventory_items` as "already fine, skip it". It gets swept with the rest, and the
  existing active-status and history e2e tests must pass before merge.

## Risks and Accepted Consequences

| Risk | Handling |
|---|---|
| Stock ages on products counted before the deploy read ~4h older, once. | Accepted (R6). Bounded by the UTC offset, decays to noise, and not correctable — the write-time offset was never recorded. Called out in the quickstart so it is expected rather than reported as a new bug. |
| A recorded timestamp added later on the wrong clock. | The patched-clock unit test (R9) asserts every recorded column on a new row equals the sentinel, so a new recorded column added on the wrong basis fails it. |
| A future sweep converts the calendar-date sites. | They call `local_now()`, which is a statement of intent a sweep has to override deliberately rather than a `datetime.now()` that looks like every other one. |
| History ordering regressions from touching `date_added`. | Principle VI gate: the existing active-status and history e2e tests are required, per R8. |
