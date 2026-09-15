# Verification: Feature 044

## Red before the fix (T004)

The SC-001 regression test, `tests/unit/test_order_product_details.py::TestTheReportedFailure`,
was written before any production change and run against the unchanged code:

```text
tests/unit/test_order_product_details.py::TestTheReportedFailure::test_a_listing_capture_after_its_order_fills_the_product_in FAILED [100%]

tests/unit/test_order_product_details.py:114: in test_a_listing_capture_after_its_order_fills_the_product_in
    assert response.status_code == 302
E   assert 200 == 302
E    +  where 200 = <WrapperTestResponse streamed [200 OK]>.status_code
============================== 1 failed in 0.55s ===============================
```

The listing capture of an item an order had already captured was re-rendered with its two
questions (200) rather than filling the product in. That is issue #156: no answer to either
question avoided a second purchase.

After US1 and US2 were implemented, the same test passes unchanged.

## Existing tests edited

**None.** research.md §11 expected two groups to need edits. Neither did:

- **T017.** `tests/unit/test_cross_path_duplicates.py::TestCapturingAListingAfterItsOrder`
  exercises `CatalogService.capture_order` directly, and never renders the confirmation page.
  FR-009 changes only what the page shows, and the service still raises the same assessment. The
  class passes unedited.
- **T030.** `tests/e2e/test_amazon_order.py`, `test_amazon_receive.py` and
  `test_amazon_degraded.py` pass unedited.
  - Their unrouted `/dp/<ASIN>` reads now reach the application and return 404, so each line
    reads "details not read". No assertion in those files depends on the payload's exact shape.
  - `#order-page-detail-note` still renders when no listing was read, so
    `test_the_review_says_the_products_will_be_thin` still holds.

Every other suite, including `tests/unit/test_capture.py` and `tests/e2e/test_repeat_purchase.py`,
also passes unedited. That confirms the paths research.md §3 and §4 promised to leave unchanged:
the default-to-purchase page and the untouched purchase path.

## Test runs

| Suite | Result |
|---|---|
| `nox -s tests` (full unit suite) | 2625 passed |
| `nox -s e2e`: this feature's journeys plus the Amazon order, receive, degraded, product-page-capture and paste-form files | 104 passed, 0 failed, in a run the host stopped at 80% for low memory, well after this feature's files had finished |
| `nox -s e2e`: `test_order_capture.py` and `test_repeat_purchase.py`, the files the stopped run had not finished | 42 passed |

The e2e runs were stopped twice by the session host because its swap was full. Other workloads on
the machine were responsible; the suite itself failed nothing. The CI `test.yml` run on the pull
request is the full-suite gate.

## Screenshots (T043)

`nox -s screenshots_headless` generated 23 screenshots and skipped 1, and `nox -s screenshots_verify`
passed: all 21 are valid PNGs under 500 KB. Ten files came back modified, but none of them shows
anything this feature changed:

- **`product_detail.png`.** Its product, the thread locker, has specification rows, so the new
  missing-details notice correctly does not render. The image is otherwise unchanged.
- **`order_capture.png`.** It shows the empty paste form. There is no item number on that form, so
  there is no match and none of the new blocks render.
- **`digikey_order.png`.** It shows a DigiKey order. The checklist and the per-line listing summary
  are Amazon-only.
- **The other seven:** add item, search, batch operations, find stock, history and bulk creation.
  None of them is a page this feature touches.

The differences are rendering churn from regeneration. `.github/workflows/screenshots.yml` records
that this happens on every run, and that CI only reminds rather than checks. Committing the churn
would bury the change in noise, so no screenshot is committed. None of the documentation
screenshots depicts the confirmation page's new blocks, the Amazon order checklist, or the review's
listing summaries.

## Payload size (T031)

`test_one_order_capture_fills_in_every_product` asserts that a four-line order carrying four
fixture listings stays under the raised `MAX_FORM_MEMORY_SIZE` (16 MiB). The exact byte count was
not printed in the runs above, so it is not recorded here.

The limit was raised on the reasoning in research.md §7, not on this fixture. Werkzeug's default
is 500 000 bytes per field, and a real listing's uncapped `description_text` and image list are
tens of kilobytes, so a large order would exceed that default.

## Success criteria

| SC | Shown by |
|---|---|
| SC-001 | `TestTheReportedFailure` (unit) and `test_a_listing_after_its_order_asks_once_and_fills_the_product` (e2e) |
| SC-002 | `TestApplyListingDetails`, `test_details_only_fills_a_product_in_without_a_purchase`, `test_recapturing_an_order_fills_in_what_it_created` |
| SC-003 | `test_a_held_value_is_kept_unless_named`, `test_only_the_named_values_are_replaced`, `test_a_product_already_in_the_catalog_only_gains_what_it_lacks` |
| SC-004 | `test_one_order_capture_fills_in_every_product` |
| SC-005 | `TestTheOrderChecklist`, `test_the_order_page_walks_through_each_product` |
| SC-006 | `test_a_listing_amazon_would_not_serve_falls_back_to_the_checklist`, `test_a_line_not_read_stays_thin_and_reads_as_missing` |
| SC-007 | Not measurable against a local fixture. The agent reads listings sequentially and shows `#workshop-capture-progress` throughout. The live check is quickstart.md §5 |
