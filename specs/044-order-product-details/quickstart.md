# Quickstart: Proving Feature 044 Works

All commands run from the repository root through the main checkout's virtualenv, using `nox`
only (Constitution IV). Put Python 3.13 on `PATH` first:

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
NOX=/home/jantman/GIT/workshop-inventory-tracking/venv/bin/nox
```

## 1. Red first: the reported defect

Before any production change, add the unit test for SC-001 and watch it fail:

1. Capture an Amazon order through `capture_order_lines` holding ASIN X. This creates a thin
   product with one purchase.
2. POST the listing capture for X to `/products/capture` with `intent=details` and
   `details_product_id=<that product>`.
3. **Assert:**
   - the product now has specification rows
   - it still has exactly **one** purchase
   - the response redirects to the order page

On today's code the POST ignores `intent`, raises the decision, and re-renders. The test fails on
the redirect. Record the failure in the PR.

```bash
$NOX -s tests -- tests/unit/test_order_product_details.py
```

## 2. Unit scenarios (`nox -s tests`)

| Scenario | Proves |
|---|---|
| Details-only fills blanks, writes no purchase, leaves quantity/stock alone | FR-002, FR-003 |
| A differing held value is kept unless `replace` names it; named ones only are replaced | FR-004, FR-005 |
| Repeating the same details-only capture changes nothing, and no duplicate rows, GTINs or pictures appear | FR-006 |
| `find_listing_match` returns `from_order` only for an order-captured purchase on the same product, in the window | FR-009, FR-012 |
| The landing page renders `#order-item-match` with `#intent-details` checked, and never both old warnings | FR-009, FR-010 |
| Collapsed "separate purchase" records one purchase with no further question | FR-011 |
| Plain mode defaults to purchase; submitting without `intent` is today's request | FR-012, FR-008 |
| `#attach-new` carries the consequence sentence | FR-013 |
| `products_missing_details` classifies an order-created product as missing and a listing-captured one as captured | FR-014, FR-015 |
| Order page: counts, badges, links, "every product has its details" | FR-016, FR-017 |
| Product page notice renders only for an Amazon-identified product with no rows | FR-018 |
| `AmazonOrderLine.from_payload` reads `listing` / `listing_problem`; a malformed listing never refuses the line | FR-024 |
| Confirm with listings: new products get details; matched ones only fill blanks; not-read lines stay thin | FR-026, FR-027, FR-028 |
| Re-capture of an already-captured order with listings fills details and writes no purchase; the flash does not say "Nothing new" | FR-030 |
| Existing `test_capture.py`, `test_repeat_purchase.py` pass **unedited** | FR-008, research.md §11 |

## 3. End to end (`nox -s e2e`, detached)

The suite takes about 17 minutes and outlasts the Bash tool's 10-minute cap, so run it detached
and wait on the log:

```bash
nohup $NOX -s e2e > /tmp/claude-e2e.log 2>&1 &
```

New journeys go in `tests/e2e/test_order_product_details.py`. Each one names its wait.

1. **One-click order.** Serve the order fixture, and fulfil `/dp/<ASIN>` with
   `amazon_listing.html`. Run the agent and confirm.
   - Wait on `.line-listing-summary` in the review. This is pattern C: the review renders after
     the POST that carried the listings.
   - Then on `#details-progress` reading "Every product".
2. **One line throttled.** Route one ASIN to a new `amazon_robot_check.html` fixture, a page with
   no `#productTitle`.
   - The review shows `.details-not-read` on that line.
   - After confirming, `#details-progress` reads "1 of N", and that line has `a.open-listing`.
3. **Checklist round trip.** From that order page, capture the listing for the missing line
   through the agent.
   - Wait for `#order-item-match` in the new tab, with `#intent-details` checked.
   - Confirm.
   - Wait for the order page's `#details-progress` to read "Every product". Pattern C: the redirect
     lands after the write.
   - Then assert the purchase count for that product is still one.
4. **Negative assertion guard.** Before asserting there is no `#duplicate-warning` on the collapsed
   page, establish the page with `expect(page.locator('#order-item-match')).to_be_visible()`.
   Otherwise the absence passes against an unloaded page (CLAUDE.md, *Never snapshot a
   JavaScript-rendered region*).

Existing order e2e tests route `/dp/<ASIN>`, or assert `.details-not-read`, per research.md §11.

## 4. Screenshots

Templates change, so regenerate the documentation screenshots and verify them:

```bash
$NOX -s screenshots_headless && $NOX -s screenshots_verify
git status --short docs/images/screenshots/
```

Commit only the screenshots of pages this feature changed: capture confirmation, order review,
order page and product page. Other screenshots churn every run (memory: e2e screenshot churn).

## 5. Manual check against the live site (optional, after merge)

This needs the app on TLS (see `/api/capture`'s docstring):

1. Open yesterday's order on Amazon and click the bookmarklet. Watch the progress element count
   through the lines.
2. The review shows each line's listing summary. Lines already captured say so.
3. Confirm. The flash reports "Details added to N product(s)", and the order page reads "Every
   product on this order has its details".
