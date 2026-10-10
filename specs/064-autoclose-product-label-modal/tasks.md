# Tasks: Close the Product Label Dialog When Printing Finishes

**Input**: Design documents from `/specs/064-autoclose-product-label-modal/`

**Prerequisites**: plan.md, spec.md, research.md, contracts/auto-close.md, quickstart.md

**Tests**: e2e tests are included. The constitution requires every behavior change to carry a
test.

## Phase 1: Setup

None. There are no new files or dependencies.

## Phase 2: Foundational

None. The two dialogs are independent.

## Phase 3: User Story 1 - The product detail dialog closes after a successful print (P1)

**Goal**: A successful Print Label on a product's detail page closes the dialog 2 s after the
success message.

**Independent Test**: Print one label from a product page, then wait for
`#product-label-modal` to be hidden. A refused count leaves the dialog open.

- [X] T001 [US1] In app/static/js/product-label-modal.js, schedule `bootstrap.Modal.getOrCreateInstance(this.modalEl).hide()` 2000 ms after a successful print (`data.success`). Keep the timer handle. Clear it in `open()` and in a `hidden.bs.modal` listener added in `init()`.
- [X] T002 [US1] In tests/e2e/test_label_print.py, add tests for: a successful print closes the dialog (`wait_for_modal_hidden`); a refused count leaves it open after the warning shows; and a failed POST (routed to 500) leaves it open. Change `test_the_count_does_not_survive_into_the_next_job` to wait for the auto-close instead of clicking Cancel.

## Phase 4: User Story 2 - The bulk product label dialog closes after a successful run (P1)

**Goal**: On Products, an order's page and Outstanding Products, a run with no failures
closes the dialog 2 s after `Complete: …`. The inventory list is unchanged.

**Independent Test**: On each page, print two rows and wait for the modal to be hidden. A run
with a failure stays open.

- [X] T003 [US2] In app/static/js/bulk-label-print.js, add the constructor option `closeOnSuccess` (default `false`, documented in the JSDoc). At the end of `printAll()`, when it is set and `failureCount === 0`, schedule `bootstrap.Modal.getOrCreateInstance(modal).hide()` in 2000 ms. Clear any pending timer in `reset()`.
- [X] T004 [P] [US2] Pass `closeOnSuccess: true` in app/static/js/product-list-labels.js.
- [X] T005 [P] [US2] Pass `closeOnSuccess: true` in app/static/js/order-bulk-actions.js, which covers both the order page and Outstanding Products.
- [X] T006 [US2] In tests/e2e/test_bulk_label_printing_products.py, add tests for: a successful run closes the dialog; a run with a failure is still open after it completes. Change `test_the_dialog_resets_when_it_is_reopened` to wait for the auto-close instead of clicking Done.
- [X] T007 [P] [US2] In tests/e2e/test_order_bulk_actions.py, assert that the modal closes after the successful run in `test_labels_print_once_per_distinct_product`.
- [X] T008 [P] [US2] In tests/e2e/test_outstanding_products.py, assert that the modal closes after the successful run in `test_labels_print_once_per_product_across_orders`.

## Phase 5: Polish

- [X] T009 In docs/user-manual.md, note under "Printing Product Labels" and "Printing Labels for Several Products at Once" that the dialog closes itself after a fully successful print and stays open when anything fails.
- [ ] T010 Run `nox -s tests` and the four touched e2e files. Then run the full `nox -s e2e`, detached.

## Dependencies

- T001 → T002. T003 → T004, T005 → T006–T008. US1 and US2 are independent.
- T009 can be done at any time. T010 is last.

## Parallel Opportunities

- T004 ∥ T005, T007 ∥ T008, and the US1 work in parallel with the US2 work.

## Implementation Strategy

US1 alone is a shippable MVP, the detail page. US2 completes "on all pages that have it".
Deliver both in one PR.
