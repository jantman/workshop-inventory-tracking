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
be automated. `quickstart.md` has the full script.

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

### The one open input (T005)

**Deferred, not closed.** How a quantity **greater than 1** renders in
`[data-component="quantity"]` is still unverified: no order in the ten most recent
contained such a line, and trawling further back through the operator's order
history was judged disproportionate to what it would settle.

**Why this is safe to ship:**

* The confirmed rendering — empty means 1 — is implemented and tested.
* The reader takes any digits it finds and falls back to 1, which is correct for
  the confirmed case and the safe failure for the other.
* **It cannot corrupt anything.** The quantity is shown on the review and is
  editable there, before any row is written.

**To close it**: open any order containing a line with quantity ≥ 2 and run

```js
[...document.querySelectorAll('[data-component="purchasedItemsRightGrid"]')]
  .map(r => JSON.stringify((r.querySelector('[data-component="quantity"]')||{}).innerText))
```

then record the shape in research.md §6 and, if it differs from "digits somewhere
in the element", adjust `amazonQuantity` in `app/static/js/capture-agent.js`.
