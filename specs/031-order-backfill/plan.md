# Implementation Plan: Backfilling Past Orders

**Branch**: `031-order-backfill` | **Date**: 2026-08-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/031-order-backfill/spec.md`

## Summary

Let the operator walk a vendor's order history and feed it through the capture paths that already
exist, and keep the catalog's account of *what is still on its way* true afterwards.

The approach in one line: **three small, independent pieces of code plus the chapter that ties
them together — an arrival mark on the review, a listing on the DigiKey screen, and a command that
turns an edited Amazon export into order addresses.**

Four facts make this much smaller than the spec's thirty-one requirements suggest, and all four
came out of reading the code rather than being assumed:

1. **The arrival seam is one hard-coded line.** `capture_order_lines` builds every purchase for
   every vendor in one place and writes `received_date=None` with a comment explaining why
   (`app/catalog_service.py:1933`). FR-024 is that line becoming a value. See research.md §1.
2. **FR-027 costs nothing.** Both "on the way" on the reorder list and the outstanding count on the
   captured-orders list are derived from `received_date` alone
   (`app/catalog_service.py:597` and `:2505`). Setting it at capture makes both correct with no
   change to either. research.md §2.
3. **FR-030 is already true.** `capture_order_lines` settles already-captured lines before the
   include gate and `continue`s, so a re-capture cannot re-date a delivered line. It needs a test,
   not code — and it needs one because the ordering that makes it true has been got wrong once
   before (PR #116 review). research.md §3.
4. **No schema change.** `Purchase.received_date` already exists and is already nullable. This is
   the second consecutive order feature to ship no Alembic revision. research.md §9.

**The one open input** is DigiKey's order-listing endpoint. The path is established with high
confidence from DigiKey's own changelog (`/History` → `/orders` under the same `/orderstatus/v4/`
prefix this client already calls), but the query parameter names and response fields are published
only inside a Swagger file that is not fetchable as text. It is closed by one live call before any
client code is written, the way feature 024 closed its own unknowns, and the spec already carries
the fallback: drop to McMaster's shape — enumerate in the browser, capture by number — and say so
in the documentation. **3-legged OAuth is not the fallback and must not be built.** research.md §5.

**Order of work is not the story priority order.** US3 (arrival) is P3 by value and first by
sequence, because it is the piece that touches the shared flow all three vendors run through, and
because the documentation US1 requires cannot honestly be written until the mechanisms it
describes exist. Docs land last, which is the reverse of how this feature reads.

## Technical Context

**Language/Version**: Python 3.13 (server); `click` for the one new CLI command. No browser
JavaScript beyond a few lines in the existing review template's inline script — the capture agent
is untouched by this feature.

**Primary Dependencies**: Flask, SQLAlchemy, Alembic, PyMySQL, Jinja2, click, requests — all
present. **No new dependency.** The CSV work is `csv` from the standard library.

**Storage**: MariaDB via `MariaDBStorage`; SQLite through the same interface under unit test.
**No schema change and no Alembic revision** — research.md §9.

**Testing**: pytest through `nox` (`tests`, `e2e`, `lint`); Playwright for e2e. **No new pytest
marker**, so `pytest.ini` is untouched under `--strict-markers`.

**Target Platform**: Flask app on the LAN, no login, single operator. The reduction command runs
on the operator's own machine against a file they downloaded.

**Project Type**: Server-rendered Flask web application plus a `click` management CLI. No SPA, no
build pipeline, no bundler.

**Performance Goals**: none new. The DigiKey listing is one API call rendering one table. Per
Constitution I, no caching or paging machinery without a measurement — DigiKey's own paging
parameters are used to ask for one page and that page is what is shown.

**Constraints**: the bookmarklet's text cannot change. Nothing may be written before the operator
confirms. Arrival at capture must not adjust a tracked count or clear a manual low flag
(research.md §2) — this is a requirement, not an oversight, and is tested as one.

**Scale/Scope**: one operator; a backfill of tens of orders and hundreds of lines, run once. Three
production files gain code (`catalog_service.py`, `digikey.py`, `product/routes.py`), two are
created (`app/services/amazon_order_export.py`, an `orders` group in `manage.py`), two templates
change, one manual chapter is written.

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design. Both passes recorded.*

| Principle | Pre-Phase 0 | Post-Phase 1 | Note |
|---|---|---|---|
| I. Simplicity First | PASS | PASS | One new dependency-free module, one new client method, one new CLI group. The one thing that looks like growth — the DigiKey listing — is a capability the operator explicitly chose over the browser-side alternative during `/speckit-specify`. No knobs: the reduction command filters nothing and takes no options beyond the file path (research.md §7). |
| II. Layered Architecture | PASS | PASS | Client stays isolated (`app/services/digikey.py` imports nothing from Flask or the ORM); parsing lives in `app/services/amazon_order_export.py` and the click callback stays thin, the same rule routes follow; no ORM query moves into a route. |
| III. Exact Numerics | PASS | PASS | `list_orders` parses through the existing `_get`, which uses `json.loads(parse_float=Decimal)` — the module docstring's "no `.json()` in this module" is not given an exception. The reduction command parses **no monetary value at all** (research.md §7). |
| IV. Test Discipline | PASS | PASS | `nox` sessions only; no new marker; e2e waits on observable state, with the conditions named in research.md §12. The negative assertion "nothing outstanding" is called out as the one most likely to pass against an unrendered table. |
| V. MariaDB Source of Truth | PASS | PASS | No schema change, so no revision (research.md §9). Nothing new is stored: an order is still its purchases, and the reduction command's output is a file on the operator's disk that the catalog never sees. |
| VI. Item Lifecycle | PASS | PASS | Untouched. This feature is entirely within products and purchases; no JA ID, active-row or parent-child path is on any code path it changes. |
| Threat model | PASS | PASS | The reduction command reads a local file the operator supplies. Validation is for correctness — a missing column named plainly — not defense. No upload path, no new network surface except one authenticated call to a vendor the app already calls. |

**Complexity Tracking**: not required — no violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/031-order-backfill/
├── plan.md                       # This file
├── research.md                   # Phase 0 — the twelve decisions above
├── data-model.md                 # Phase 1
├── quickstart.md                 # Phase 1
├── contracts/
│   ├── digikey-order-listing.md  # The DigiKey call and the screen it feeds
│   ├── amazon-export-command.md  # The CLI contract
│   └── arrival-at-capture.md     # The form and service contract
├── checklists/
│   └── requirements.md           # From /speckit-specify
├── verification.md               # Written by the live DigiKey call (research.md §5)
└── tasks.md                      # /speckit-tasks — NOT created here
```

### Source Code (repository root)

```text
app/
├── catalog_service.py            # capture_order_lines gains arrived_date; the
│                                 #   Purchase() call stops hard-coding None
├── models.py                     # + DigiKeyOrderSummary
├── product/
│   └── routes.py                 # _order_decisions reads arrived[key]; both confirm
│                                 #   routes pass arrived_date; the DigiKey entry
│                                 #   route renders the listing
├── services/
│   ├── digikey.py                # + DigiKeyClient.list_orders
│   └── amazon_order_export.py    # NEW — pure parsing, no Flask, no ORM
└── templates/product/
    ├── order_review.html         # + the arrival controls
    └── digikey_order_entry.html  # + the recent-orders table

manage.py                         # + an `orders` group with one command

docs/
└── user-manual.md                # + the "Backfilling Past Orders" chapter

tests/
├── unit/
│   ├── test_order_backfill.py    # NEW
│   ├── test_amazon_order_export.py  # NEW
│   └── test_digikey_client.py    # + list_orders cases
└── e2e/
    └── test_order_backfill.py    # NEW
```

**Structure Decision**: no new structure. Every path above is an existing directory of this
application, and the one new service module sits beside the five that are already there. The
feature deliberately adds no screen, no route and no template of its own: the DigiKey listing goes
on the screen that already answers "capture a DigiKey order" (research.md §6), and the arrival mark
goes on the review the operator is already reading.

## Order of Work

Four slices. The first three are independent of each other and could be built in any order; the
sequence below is by risk, not by dependency.

**Slice A — arrival at capture (US3, FR-024–FR-031).** Touches the one flow all three vendors run
through, so it carries the only real regression risk in the feature and goes first while there is
most attention to spend on it. `capture_order_lines` takes `arrived_date`; the `Purchase()` call
reads the line's decision; `_order_decisions` grows one key; both confirm routes pass the date;
`order_review.html` grows the controls; `_order_capture_summary` says how many lines were recorded
as already arrived. Ends with the existing DigiKey, McMaster and Amazon suites passing unchanged —
that is the gate, exactly as it was in feature 029.

**Slice B — the Amazon reduction command (US2, FR-009–FR-017).** Entirely isolated: a pure function,
a click command, and a unit test file. Nothing it does can affect the running application, which is
why it is second — it can be finished and set aside.

**Slice C — the DigiKey listing (US1's enumeration half, FR-018–FR-022).** Begins with the live
call that closes research.md §5 and writes `verification.md`. Only then the client method, the
model, the route change and the template. If the live call says the endpoint is not reachable on a
2-legged token, this slice becomes documentation and the fallback in research.md §5 applies.

**Slice D — the documentation (US1's procedure half, FR-001–FR-008, FR-023).** Last, because it
describes the three above and cannot be written honestly before they exist. One new manual chapter,
a table-of-contents entry, and a cross-reference in each of the three vendor sections. Ends with
`grep -ric "catalogue" README.md docs/ app/ tests/` returning nothing.

## Risks

**The DigiKey endpoint is the only one that can change the plan.** Everything else here is against
code in this repository. Its failure mode is understood, bounded and already has a written
fallback that costs the feature one capability and no rework — Slice C's own first task is the one
that finds out.

**The arrival mark's silence about counts is the thing most likely to be reported as a bug.** A
tracked product whose backfilled order is marked arrived does not move. That is FR-028 and it is
deliberate (research.md §2), it is stated on the review, and it is covered by a test whose name
says so. It is recorded here because a future reader comparing it against `receive_purchase` will
otherwise assume it was forgotten.

**Amazon's export format is not a contract.** It has already been renamed once. Requiring two
columns rather than twenty-seven, and refusing by name when one is missing, is what keeps that
from being this feature's problem later (research.md §7).
