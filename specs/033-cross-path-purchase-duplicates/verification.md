# Verification: Recognize a Listing Capture and an Order Line as One Purchase

**Feature**: `specs/033-cross-path-purchase-duplicates` | **Branch**: `issues/129` | **Date**: 2026-09-01

## Automated

| Suite | Result |
|---|---|
| `nox -s tests` | **2288 passed**, 774 deselected, 37s |
| `nox -s e2e` | **750 passed**, 0 failed, 2312 deselected, 15m22s |
| `nox -s lint` | Fails repo-wide on E501 **before this branch as well** — see the note below |
| Working tree after `nox -s e2e` | **clean** (Constitution IV) — `test-debug-output/` is gitignored |

New coverage: 40 unit tests in `tests/unit/test_cross_path_duplicates.py` and 3 E2E
journeys appended to `tests/e2e/test_amazon_order.py`.

**The regression test was confirmed red first** (FR-023, and issue #129's own
instruction). `TestTheReportedFailure::test_capturing_the_order_adopts_the_listing_capture`
failed with `assert 2 == 1` against the pre-change code — the exact doubling the issue
reports — and passes after.

**On `nox -s lint`.** It is not a CI gate: `.github/workflows/test.yml` runs `tests`,
`coverage` and `e2e` only, and the noxfile's own docstring calls the lint session a "future
enhancement". It fails on `main` with several thousand E501s across files this branch never
touches (`test_taxonomy.py`, `test_vocabulary.py`, `test_stock_status.py` and many more),
because flake8's default 79-column limit does not match the repository's ~88-column house
style. The files this branch changes were checked against that norm: **the only non-E501
finding was one E122, and it was fixed.**

## FR-022 — existing tests pass unedited

Verified by inspection (T031). `git diff --stat -- tests/` shows exactly two pre-existing
files touched, both additions and neither an edited assertion:

| File | Change |
|---|---|
| `tests/unit/test_mcmaster_routes.py` | +5 — three parametrize cases added to `test_the_fallback_agrees_with_wrote_anything`, which exists to catch a new kind of write taught to the flash but not to `wrote_anything` |
| `tests/e2e/test_amazon_order.py` | +99 — three appended journeys, nothing above them altered |

Untouched, as required: `test_order_vendors.py`, `test_digikey_capture.py`,
`test_mcmaster_capture.py`, `test_amazon_capture.py`, `test_capture.py`.

## No production code was needed for US3

FR-021 asked for all three vendors. The candidate lookup asks for a vendor name, a vendor
item id and an order date, all three written identically by both capture paths — so the two
McMaster and DigiKey tests were written against the Amazon implementation and **passed on
the first run with nothing added**. That is the standing check that the feature 029 seam is
in the right place (029 FR-037): if either had needed a branch, the seam would have been
wrong.

## No schema change

`migrations/versions/` is untouched (T038). Third consecutive order feature to ship no
Alembic revision — `vendor`, `vendor_item_id`, `order_date`, `supplier_order_reference` and
`order_line_number` were all already there and already written by both paths.

## Quickstart scenarios

`quickstart.md` lists a matrix of unit scenarios, two E2E journeys and two manual checks.

| Scenario | Covered by |
|---|---|
| Listing capture, then order capture, `adopt` | `TestTheReportedFailure::test_capturing_the_order_adopts_the_listing_capture` |
| …with `separate` | `TestTheOtherTwoAnswers::test_separate_records_a_second_purchase` |
| …with no answer | `test_an_unanswered_line_refuses_the_capture`, `test_nothing_at_all_is_written_including_the_other_lines` |
| Line excluded | `test_an_unanswered_line_the_operator_excluded_refuses_nothing` |
| Candidate already received | `TestAdoptingPreserves::test_a_received_purchase_stays_received`, `test_a_tracked_count_does_not_move_and_a_low_flag_is_not_cleared` |
| Candidate 100 days away | `TestWhatIsNotACandidate::test_a_purchase_outside_the_window_is_not_offered` |
| Candidate carrying another order's number | `test_a_purchase_carrying_another_orders_number_is_not_offered` |
| Same item on two lines, one candidate | `TestOneCandidatePerLine` — three tests |
| Order or purchase with no date | `test_a_purchase_with_no_order_date_is_not_offered`, `test_an_order_with_no_date_offers_nothing` |
| Re-capture after adoption | `TestAfterAdopting::test_a_re_capture_asks_nothing_and_writes_nothing` |
| Adopt-only capture, `orphaned` empty | `test_an_adopted_row_is_not_reported_as_orphaned` — research.md §8, the trap |
| Adopt-only capture, the flash | `test_the_fallback_agrees_with_wrote_anything[purchases_adopted]` |
| `apply_change` on an adopted line | `TestWhatAdoptingWrites::test_apply_change_takes_the_orders_values`, `test_the_review_offers_that_change` |
| `order_date` guard against a recorded receipt | `test_the_order_date_is_not_pushed_past_a_recorded_receipt` |
| McMaster and DigiKey | `TestTheOtherTwoVendors` — two tests, no production code |
| Order capture, then listing capture 4 days later | `TestCapturingAListingAfterItsOrder::test_a_listing_captured_days_later_raises_the_question` |
| …acknowledged | `test_acknowledging_it_records_a_separate_purchase` |
| Listing then listing, months apart | `test_two_listing_captures_months_apart_are_unchanged` |
| `/api/capture` JSON | `test_the_json_representation_names_the_order` |
| E2E: the review asks | `test_a_line_already_captured_from_its_listing_asks_rather_than_duplicating` |
| E2E: adopting | `test_adopting_it_leaves_one_purchase_carrying_the_order` |
| E2E: the refusal | `test_leaving_the_question_unanswered_refuses_the_whole_capture` |

## A defect the tests did not find

Worth recording, because it was found by re-reading the diff rather than by any test.

``capture_order_lines`` derives an order date for an order the vendor did not date --
falling back to the arrival date, then to today (031 FR-026) -- while ``review_order`` has
no such fallback and uses the stated date alone. Matching candidates on the *derived* date
would have found rows the review never showed, and then refused the capture over a question
the re-rendered page carries no control to answer: an unresolvable dead end reachable only
from an undated order.

Fixed by matching on the stated date and stamping with the derived one. Two tests hold the
two halves in step -- ``TestTheReviewAndTheCaptureAgree`` -- and the second is the general
form: whatever the review asks about is exactly what the capture will accept.

## Manual checks — the two that need a person

Inherited from issue #129's own comment. Both involve real vendor pages and real vendor
data, so neither can be automated.

- [ ] **Re-run the exact case that found this.** Capture a product from its Amazon listing
      page, then capture the order it came on from `/your-orders/order-details`. The review
      must name the purchase already recorded; answering *Same purchase* must leave one
      purchase, carrying the order number.
- [ ] **The reverse direction, with mismatched dates.** Capture an order first, then the
      listing, typing an order date that differs from Amazon's by several days. The
      duplicate warning must appear and must name the order.

**Existing bad data.** Product 10 carries purchases 10 and 11 for one physical purchase
(issue #129's table). It is a ready-made fixture for checking the fix behaves sensibly
against data that already went wrong. **Cleaning it up is feature 032's delete, not this
feature's job** — this feature stops new duplicates being created and does not repair old
ones.
