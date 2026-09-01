# Verification: Delete a Purchase

**Feature**: `specs/032-delete-purchase` | **Branch**: `issues/130` | **Date**: 2026-08-31

## Automated

| Suite | Result |
|---|---|
| `nox -s tests` | **2241 passed**, 771 deselected, 37s |
| `nox -s e2e` | **747 passed**, 0 failed, 2265 deselected, 15m26s |
| `nox -s screenshots_verify` | 21 screenshots, all valid PNG, all under 500KB |
| Working tree after `nox -s e2e` | **clean** (Constitution IV) |

New coverage: 44 unit tests and 15 E2E tests in `tests/unit/test_purchase_delete.py`
and `tests/e2e/test_purchase_delete.py`.

**A note on the E2E wall clock.** This run took **15m26s**, which is *past* the
constitution's 15-minute allowance rather than inside it. The feature added 15 tests
(~50s); the suite was already at roughly 13m45s for 602 tests and is now 747. Nothing here
waits on a clock — the suite still executes zero `wait_for_timeout` — so this is growth,
not regression. It is flagged because the next feature to add tests will be over the
allowance on a warm machine as well, and the allowance or the parallelism will have to
move. It is not a defect in this feature.

## Quickstart scenarios

`quickstart.md` lists eight. Seven are covered by automated tests; the eighth needs live
vendor pages and is left for the operator.

| # | Scenario | Covered by |
|---|---|---|
| 1 | The headline case — delete one of two, cancel changes nothing | `test_one_of_two_purchases_is_deleted_and_the_other_stays`, `test_the_confirmation_names_the_purchase_it_is_about_to_delete`, `test_cancelling_changes_nothing`, `test_it_says_what_was_removed` |
| 2 | Attachments — the count is stated, the files go, a datasheet survives | `test_the_file_count_is_what_went`, `test_an_unshared_photo_goes`, `test_a_product_level_attachment_survives`, `test_it_says_how_many_files_go` |
| 3 | The count does not move | `TestWhatDoesNotMove` — quantity, its age, and a hand-set flag, all three |
| 4 | The order screen | `test_deleting_a_line_returns_to_the_re_derived_order`, `test_the_confirmation_is_the_same_one`, `test_the_line_is_gone_from_its_product_too` |
| 5 | Deleting an order's last line | `test_deleting_the_last_line_leaves_the_order_saying_so` |
| 6 | The derived views | `test_an_outstanding_purchase_stops_being_on_order`, `test_the_order_leaves_the_captured_orders_list`, `TestTheDerivedViews` |
| 7 | Already gone — two tabs | `test_deleting_it_twice_reports_it_and_changes_nothing` |
| 8 | **The #129 reproduction** | **Not automated.** Needs a live Amazon listing capture followed by a live capture of the order containing it. Left for the operator's manual pass. |

## Left for the operator

- **Quickstart scenario 8.** Capture a real Amazon listing, then capture the order it came
  from, and delete the duplicate purchase. Confirms SC-002 end to end against the real
  vendor rather than against seeded rows.
- **The ~20 checks parked on issue #130** (inherited from #80). This feature was their
  blocker: every one of them writes a purchase, and a mistake could not be undone. They
  are unblocked now.
- **Sequencing.** #129 should land first or alongside. This feature is how the operator
  *recovers* from the duplicate #129 produces; it does not fix the duplication, and no
  capture path was changed.
