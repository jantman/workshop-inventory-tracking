# Quickstart: Validating Cross-Path Purchase Recognition

**Feature**: `specs/033-cross-path-purchase-duplicates` | **Date**: 2026-09-01

How to prove this feature works, and how to prove it did not break the two capture paths it
sits between. Details of what is written live in [data-model.md](./data-model.md) and
[contracts/adopting-a-purchase.md](./contracts/adopting-a-purchase.md).

## Prerequisites

```bash
# venv binaries by path; nox needs python3.13 on PATH
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
```

Docker is needed for the e2e session (MariaDB) and Playwright browsers are installed by the
session itself.

## The regression test, confirmed red first

FR-023 is not "write a test", it is "watch it fail". Before any production change:

```bash
venv/bin/nox -s tests -- tests/unit/test_cross_path_duplicates.py
```

It must fail with **two** purchases where the test asserts one. A test that passes before the
fix is testing something else.

The shape, in one unit test against the SQLite-backed `catalog` fixture:

1. `capture_order(vendor='Amazon', vendor_item_id='B0G43FCHFX', order_date=<27 Jul>)`
2. `capture_order_lines(<an order dated 23 Jul carrying B0G43FCHFX>, AMAZON_ORDER_VENDOR,
   {key: {'include': True, 'same_purchase': 'adopt'}})`
3. Assert one purchase for that product, carrying the order number and line number.

## Unit suite

```bash
venv/bin/nox -s tests
```

Sub-second, network blocked. What the new tests must cover, by requirement:

| Scenario | Asserts |
|---|---|
| Listing capture, then order capture, `adopt` | One purchase; order number and line number stamped (FR-012, FR-013) |
| …with `separate` | Two purchases; the first untouched (US1 scenario 3) |
| …with no answer | `ValidationError`; **nothing written at all**, including the other lines (FR-008a, FR-016) |
| Line excluded | No answer needed; candidate untouched (FR-008b) |
| Candidate already received | `received_date` and quantity survive; no tracked count moves; no manual low flag clears (FR-014) |
| Candidate 100 days from the order | Not offered; a second purchase is recorded, no question (FR-003) |
| Candidate carrying another order's number | Not offered (FR-002) |
| Order carrying the same item twice, one candidate | One line is offered it, the other is not; adopting writes one row and creates one (FR-004) |
| Order or purchase with no date | Not offered (FR-006) |
| Re-capturing the same order after an adoption | The line reads CAPTURED, no question, nothing written (SC-004) |
| Adopt-only capture | `orphaned` is empty — the trap in research.md §8 |
| Adopt-only capture | The flash does **not** say "Nothing new to capture"; `wrote_anything` agrees |
| `apply_change` on an adopted line | Quantity and price take the order's values; `lines_updated` counts it (FR-009) |
| Adoption with a `received_date` earlier than the order's date | `order_date` is left alone rather than made invalid (research.md §5) |
| The same, for McMaster and for DigiKey | FR-021, one test each — the query is shared, these prove it |
| Order capture, then listing capture 4 days later | `CaptureDecisionRequired`, assessment names the purchase and its order number (FR-017, FR-018) |
| …acknowledged | A second purchase is recorded (FR-019) |
| Listing capture, then listing capture, months apart | Unchanged: no question, two purchases (FR-020, research.md §7) |

## E2E suite

```bash
# 15-minute timeout minimum; ~14 minutes warm. Run detached and poll — most agent
# bash tools cap at 10 minutes.
nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

Two journeys, added to `tests/e2e/test_amazon_order.py` beside the fixture that already drives
the order page:

1. **Adopt.** Seed a listing-captured purchase with `live_server.add_test_data`, drive the
   Amazon order fixture to its review, assert the line shows the recorded purchase, pick
   *Same purchase*, confirm, and assert the product page shows **one** purchase row carrying
   the order number.
2. **Refuse.** The same review, confirmed with the question unanswered: the review re-renders,
   the error is flashed, and the product page still shows one purchase — the seeded one.

Waiting rules apply in full (`CLAUDE.md`, "Writing e2e tests"). Both journeys click a button
that posts a form and navigates, so the condition to wait on is the destination page's own
content — pattern C, render-implies-completion. **The negative assertion in journey 2 is the
dangerous one**: establish the purchase-history table with `expect(...)` before counting rows,
or it passes against a table that has not rendered.

## Manual verification — the two things that need a person

Inherited from issue #129's comment; they involve real vendor data and cannot be automated.

1. **Re-run the case that found this.** Capture a product from its Amazon listing, then capture
   the order it came on from `/your-orders/order-details`. One purchase, after answering the
   question.
2. **The reverse, with mismatched dates.** Capture an order first, then the listing, typing an
   order date that differs from Amazon's by several days. The duplicate warning must appear and
   must name the order.

Product 10 (`B0G43FCHFX`, purchases 10 and 11) is the ready-made fixture for checking the fix
behaves sensibly against data that already went wrong. **Cleaning it up is feature 032's delete,
not this feature's job.**

## Lint

```bash
venv/bin/nox -s lint
```

## What "done" looks like

- The FR-023 regression test was red, and is green.
- `nox -s tests` and `nox -s e2e` pass, and the working tree is clean afterwards.
- No existing assertion was edited. The one addition to an existing test file is a parametrize
  case in `test_the_fallback_agrees_with_wrote_anything` (research.md §9).
- `git status` shows no migration in `migrations/versions/` — there is nothing to migrate.
