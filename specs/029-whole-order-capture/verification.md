# Verification: Whole-Order Capture for Every Vendor

**Feature**: `specs/029-whole-order-capture/` | **Implementation run**: 2026-08-26

Two halves, following the pattern feature 028 set. **Part A is done and recorded
below** — every automated gate, and the live-site investigation that closed the
plan's one TBD. **Part B is the manual walk**, which needs real orders from three
vendors and real boxes, and is left for the operator.

---

## Part A — what was verified automatically

### A1. The regression gate — the whole safety argument

This feature refactored two shipped order-capture flows into one. The condition
set in plan.md was that the existing DigiKey and McMaster suites pass
**unedited** — they are the specification of the behaviour being consolidated, so
if a shared implementation could not satisfy them as written, the seam was in the
wrong place.

| | Baseline (before) | After | Regression tests edited |
|---|---|---|---|
| `nox -s tests` | 2010 passed | **2095 passed** | **none** |
| `nox -s e2e` | 691 passed | **722 passed** | **none** |

Baseline measured on `a1f3c77` before any change. The growth is entirely new
tests: +85 unit and +31 e2e.

The eight unit files and six e2e files named in quickstart.md as the gate are
byte-identical to what they were before this feature. `git diff` over
`tests/unit/test_digikey_*.py`, `tests/unit/test_mcmaster_*.py` and
`tests/e2e/test_digikey_*.py`, `tests/e2e/test_mcmaster_*.py` is empty.

### A2. The gate pushed back four times, and was right each time

Worth recording, because each one was a real defect the refactor would otherwise
have shipped:

1. **A shadowed helper.** Renaming the McMaster payload scalars to `_payload_*`
   collided with an **existing** `_payload_string` used by `ListingCapture` — same
   name, different contract (`Optional[str]` vs `str`). Python resolves at call
   time, so the later definition silently took over and Amazon's *single-listing*
   capture began returning `''` where it had returned `None`.
   `test_capture.py::test_a_price_sent_as_a_json_number_is_refused_rather_than_coerced`
   caught it. Renamed to `_order_*`.
2. **Redirects broke four order-screen tests.** The converged order route first
   redirected from the old DigiKey and McMaster addresses; the tests read those
   pages' bodies and got a 302. The old addresses now render by delegating —
   still one implementation, and a better reading of FR-044.
3. **A shipped URL would have moved.** `_receive_url` was first written to send
   every scan to `/products/orders/<vendor>/<number>`. A gate test asserts a
   DigiKey scan lands on `/products/digikey/orders/<n>`, and it is right to: that
   address is user-visible and scans have gone there since 024. Which address an
   order is shown at is now one documented branch in the route layer.
4. **A dropped MPN fallback.** McMaster's product lookup has a
   manufacturer-part-number fallback that `contracts/order-vendor.md` did not
   record. Consolidating without it would have been a silent behaviour change.

### A3. What the consolidation actually removed

| Was two | Is one |
|---|---|
| `_recorded_digikey_lines` + `_recorded_mcmaster_lines` | `_recorded_order_lines` |
| `_orphaned_digikey_purchases` + `_orphaned_mcmaster_purchases` | `_orphaned_order_purchases` |
| `_review_digikey_line` + `_review_mcmaster_line` | `_review_order_line` |
| `_apply_digikey_change` + `_apply_mcmaster_change` | `_apply_order_change` |
| `_digikey_product_for` + `_mcmaster_product_for` | `_product_for_order_line` |
| `review_digikey_order` + `review_mcmaster_order` | `review_order` |
| `capture_digikey_order` + `capture_mcmaster_order` | `capture_order_lines` |
| `DigiKeyCaptureResult` + `McMasterCaptureResult` | `OrderCaptureResult` |
| `_digikey_decisions` + `_mcmaster_decisions` | `_order_decisions` |
| `_digikey_capture_summary` + `_mcmaster_capture_summary` | `_order_capture_summary` |
| `find_order_lines` + `find_mcmaster_order_lines` | `find_order_lines_for` |
| `digikey_order_review.html` (184) + `mcmaster_order_review.html` (288) | `order_review.html` (373) |
| `digikey_order.html` (98) + `mcmaster_order.html` (121) | `order.html` (139) |
| two order-detail routes | `GET /products/orders/<vendor>/<number>` |

**And Amazon is the proof it worked** (FR-037): adding a third vendor took one
`OrderVendor` value, one reader in the capture agent, one payload type and one
confirm route. No third copy of the review, the confirmation, the order screen or
the receiving path.

**One payoff arrived by construction**: DigiKey's change-application gained the
PR #123 fix — not counting a skipped write as "1 line(s) updated" — which had only
ever been applied to the McMaster copy. That asymmetry is exactly the duplication
cost the consolidation existed to remove.

### A4. The Amazon investigation (T001–T004)

Read off the live site on 2026-08-26 in the operator's own signed-in browser.
Written up in [research.md §2–§8](./research.md); the findings that changed the
design:

| Question | Answer |
|---|---|
| Order-page path shape (the plan's one TBD) | `/your-orders/order-details?orderID=<3-7-7>`; the legacy `/gp/css/order-details` 302s to it |
| What does the markup anchor on? | **`data-component`** — semantic, unhashed. The most stable of the three vendors |
| Is `purchasedItems` a line? | **No.** It is a *group*: a 4-line order rendered as two of them holding 3 and 1. The line is `purchasedItemsRightGrid` |
| Can ASINs be swept from the document? | **No.** 26 `/dp/` links, 9 distinct ASINs, 4 real lines. The rest are recommendations |
| Is the price readable as text? | Only via `.a-offscreen` — the visible span has an `aria-hidden` twin, so `innerText` yields `"$9.99 $9.99"` |
| Does Amazon state a unit price? | **Yes** — which disproved a spec assumption and made Amazon *simpler* than McMaster: no pack arithmetic at all |
| Does Amazon number its lines? | **No.** Position is the only line identity available |
| Where is the quantity? | A badge over the image in the **left** grid, `.od-item-view-qty`. `[data-component="quantity"]` is always empty — see T005 below |

Two consequences the plan did not anticipate:

1. **`pageKind()` had to change signature.** It took `location.pathname`; Amazon's
   order id is in the query string, so it now takes the location. Every other
   branch reads the path exactly as before.
2. **No Alembic revision.** Every column Amazon needs was added by 024 and 028.
   This is the first of the three order-capture features to ship without a
   migration.

### A5. The other gates

| Gate | Result |
|---|---|
| `nox -s tests` | 2095 passed |
| `nox -s e2e` | 722 passed, 0 failed, 15m40s |
| E2E left the working tree clean | **yes**, verified by diffing `git status` before and after |
| `nox -s screenshots_headless` | 23 passed, 1 skipped |
| `nox -s screenshots_verify` | all valid PNG, all under 500KB, 2.92 MB total |
| Spelling (`catalogue` in README/docs/app/tests) | none |
| `float` on any price or quantity path | none — `Decimal` throughout (Constitution III) |
| `nox -s lint` on the files this feature added | no issues beyond `E501`, which the surrounding codebase carries throughout |

19 screenshots changed. That is expected rather than churn: the new *Captured
Orders* navigation entry appears on every page, and `digikey_order.png` shows the
merged order screen.

---

## Part B — the manual walk (T059), for the operator

Everything below needs a real signed-in browser and real boxes, so none of it can
be automated. `quickstart.md` has the full script. The one open input recorded
here previously (T005) is **closed** — see below.

- [ ] Capture a real multi-line Amazon order from `/your-orders/order-details`
      with the bookmarklet. Confirm the review lists **exactly** the ordered
      items — no recommendations — with the right quantities and unit prices.
- [ ] Exclude a line, edit a description, confirm; check one outstanding purchase
      per included line, each carrying the order number, line number and ASIN.
- [ ] Re-capture the same order: every line reads as already captured, nothing
      new is written.
- [ ] Receive lines from the order screen as boxes arrive, amending one quantity.
- [ ] Capture a real DigiKey order and a real McMaster order, and confirm both
      behave exactly as they did before this feature.
- [ ] Open `/products/orders` with all three outstanding and confirm each shows
      its vendor, number, date and outstanding count.

### T005 — closed, and it was a defect rather than an unknown

**Closed 2026-08-27.** This was previously recorded here as "deferred, safe to
ship". That was wrong twice over, and the correction is worth keeping.

**What was claimed**: that `[data-component="quantity"]` holds the quantity and
renders empty for a quantity of one, and that no order in the ten most recent had
a line above one, so the >1 rendering could not be confirmed.

**What is true**: `[data-component="quantity"]` is present on every row and is
**always empty** — including on a line of four. The quantity is a badge over the
product image, `<div class="od-item-view-qty"><span>4</span></div>`, sitting in
`purchasedItemsLeftGrid` — the *other* grid from the one the reader was scoped to.
And two of the ten orders on the first page did have multi-quantity lines all
along.

**So this was not a gap in coverage; it was a live defect.** The shipped reader
would have recorded **every multi-quantity line as a single item, silently**,
with a plausible-looking review showing "1" and nothing to suggest otherwise. The
operator would have discovered it during a stock reconciliation, or not at all.
It is exactly the class of failure Constitution I says cannot be absorbed.

**How the wrong conclusion was reached**, since that is the reusable part: nine
of the ten orders were never opened. The check that produced "no order has one"
ran against the order-*history* page, which does not render per-line quantities
in the form that check looked for. The claim was stated with the confidence of a
survey and the evidence of two samples — and it took the operator saying "that's
wrong, I have two such orders" to reopen it. Believing that correction
immediately, rather than re-verifying it, would have found the defect several
steps sooner.

**Now confirmed** against two live orders, with the subtotal corroborating each:
a quantity of 2 at $5.47 against a $10.94 subtotal, and a quantity of 4 at
$14.99. The order-history page renders the same badge as `product-image__qty`, so
both classes are accepted.

**Covered by**: `test_a_multi_quantity_line_is_read_from_its_badge` and
`test_a_line_with_no_badge_reads_as_one` in `tests/e2e/test_amazon_order.py`,
against a fixture whose row 2 now carries the real badge markup in the real
place. A reader scoped to the right grid, as the original was, fails both.
