# Research: Whole-Order Capture for Every Vendor

**Feature**: `specs/029-whole-order-capture/` | **Date**: 2026-08-26

Two questions had to be answered before this feature could be planned: **what does Amazon's
order page actually look like**, and **what is genuinely shared between the two order captures
that already exist**. Both are now closed. The first was closed by reading the live site; the
second by reading the code.

---

## Part A — Amazon

### §1. There is no order interface to read an order back from

**Decision**: the order is read off the page by the capture agent, in the operator's own
signed-in browser. No credentials, no registration, no server-side fetch.

**Rationale**: Amazon's published programmatic interfaces are seller-facing. Nothing in them
lets a customer read back their own retail orders, so there is no equivalent of the DigiKey
route (feature 024), and the McMaster route (feature 028) is what is left. This is settled
rather than discovered — it is the premise the spec was written on (FR-002).

A same-origin credentialed `fetch` from the page was additionally **blocked by the browser
extension** during this investigation. That is a guardrail rather than a finding, and it was
not worked around; it is noted because it removes the last "maybe we could fetch it" option
from consideration.

**Alternatives rejected**: seller APIs (wrong audience); the privacy data-export request (an
asynchronous, slow, whole-account dump — the wrong shape for "I just placed an order"); and
screen-scraping from the server (the address requires a session, and this is the reason the
bookmarklet exists at all).

### §2. The address, and why dispatch has to change

Read on 2026-08-26 against the live site.

| | |
|---|---|
| **Canonical order page** | `/your-orders/order-details?orderID=<id>` |
| **Legacy address** | `/gp/css/order-details?orderID=<id>` — **302s to the canonical one** |
| **Order id shape** | `\d{3}-\d{7}-\d{7}` |
| **Order *list*** | `/your-orders/orders` and `/gp/css/order-history` |

**Decision**: dispatch on the path `/your-orders/order-details`, and read the order id from
`location.search`.

**This is a change to shared code.** `pageKind()` in `app/static/js/capture-agent.js` takes
`location.pathname` and nothing else, because every page it has had to recognize so far — an
Amazon listing, a McMaster product, a McMaster order — carries its identifier *in the path*.
Amazon's order id is in the **query string**, so the existing signature cannot express this
page. `pageKind` must take the location (or path plus search).

**Rationale for keying on the path anyway**: it is what the agent already does, and — per
research on feature 028 §3 — keying on the *hostname* would leave the readers with no
end-to-end coverage, because the e2e harness serves vendor fixtures from the application's own
origin. That reasoning is unchanged and still binding.

**FR-024 (a list page must not be read as an order) is satisfied by the path alone.** Verified:
`/your-orders/orders` carries **zero** of the order-detail components below — no line
containers, no `orderId`. The two page types are cleanly separable and no content-based
tie-breaker is needed.

### §3. Amazon anchors on `data-component`, not on classes

**This is the single most useful finding of the investigation.** The order page carries 58
distinct `data-component` attributes with semantic, unhashed names:

```
orderId  orderDate  shipments  shipmentStatus  purchasedItems
purchasedItemsLeftGrid  purchasedItemsRightGrid  itemImage
itemTitle  quantity  unitPrice  orderedMerchant  itemCondition
```

**Decision**: every Amazon selector keys on `[data-component="..."]`.

**Rationale**: this is markedly more stable than what the other two vendors offer. McMaster
required two different conventions on two page types — plain names (`dtl-row`) on order pages
and CSS-module-hashed names (`_price_1y02s_5`) on product pages, where the hash is a build
artifact that changes when they rebuild. Amazon's names are semantic and describe the *role*
of the node. They are still not a contract — FR-021's "a dead selector costs one field" rule
applies exactly as before — but the expected rate of breakage is lower than the McMaster
reader's, not higher.

### §4. The line container is not the obvious one

**Decision**: one order line = one `[data-component="purchasedItemsRightGrid"]`.

**`[data-component="purchasedItems"]` is a group, not a line**, and reading it as a line is the
first mistake available here. Measured on a real four-line order:

| Selector | Count on a 4-line order |
|---|---|
| `[data-component="purchasedItems"]` | **2** (groups of 3 and 1) |
| `[data-component="purchasedItemsRightGrid"]` | **4** ✔ |
| `[data-component="itemTitle"]` | 4 |

Confirmed against a one-line order: 1 and 1.

**The second trap is worse, and it is the one to write a test for.** The order page carries
**26 `/dp/` links covering 9 distinct ASINs** — but the order has **4 lines**. The rest are
recommendations ("buy it again", "related to items you've viewed"). A document-wide ASIN sweep
would therefore invent five order lines out of Amazon's advertising. Every field read MUST be
scoped to the row, and the row count MUST come from the row selector.

Within a row, the ASIN is deduplicated from `/dp/<ASIN>` links inside the row's enclosing
`.a-fixed-left-grid` (the image link and the title link both carry it): **exactly one distinct
ASIN per row on every row sampled**.

### §5. Per-field extraction

| Field | Source | Note |
|---|---|---|
| Order number | `[data-component="orderId"]` | Exact; matched the URL's `orderID` on every order read |
| Order date | `[data-component="orderDate"]` | US long form, e.g. `August 22, 2026` — needs parsing, and a locale-dependent format is a field that can fail per FR-021 |
| Line title | `[data-component="itemTitle"]` within the row | Read cleanly at 50–195 characters |
| Line ASIN | `/dp/<ASIN>` links within the row, deduplicated | §4 |
| Line unit price | `[data-component="unitPrice"] .a-offscreen` | **See below** |
| Shipment status | `[data-component="shipmentStatus"]` | Display only — FR-011 keeps every captured purchase outstanding regardless |

**The price needs `.a-offscreen`, not `innerText`.** Amazon renders the price twice — once in an
`.a-offscreen` span for screen readers and once in an `aria-hidden="true"` span for sight — so
`innerText` on the component yields `"$9.99 $9.99"`. Taking `.a-offscreen` yields `"$9.99"`.
This is Amazon's standard price markup and it appears on every row.

**The unit price is genuinely a *unit* price.** The spec assumed otherwise (it said Amazon
"prices a listing, not a unit" and that there was nothing to compute from). The page has a
component named `unitPrice` and it is per-unit. That assumption in `spec.md` is wrong and is
corrected by this research; nothing else in the spec depends on it, and it makes the Amazon
capture *simpler* than the McMaster one rather than harder — there is no pack arithmetic here
at all.

### §6. Quantity — the one rule that is not fully confirmed

`[data-component="quantity"]` exists on every row and **renders empty when the quantity is 1** —
literally `<span class="a-size-small"></span>` with no text.

**Decision**: an empty quantity component means 1.

**What is confirmed**: the empty-means-one rendering, on every row of every order sampled.

**What is not**: how a quantity **greater than 1** renders — whether as a bare `2`, as `Qty: 2`,
or somewhere other than this component. **No order in the ten most recent contained a line with
quantity above 1**, and trawling further back through the operator's order history to manufacture
an example was judged disproportionate to what it would settle.

**How this is bounded** rather than left as a hole:

* It is one implementation task (`T00x`), closed by opening one real order that has a
  multi-quantity line and reading that component — a minute's work when such an order exists.
* Until it is closed, the reader takes any digits it finds in the component and falls back to 1
  when it finds none. That is correct for the confirmed case and is the safe failure for the
  other: a quantity read as 1 when it was 3 is **visible on the review before anything is
  written** (FR-003), and the review's quantity field is editable (FR-016's sibling behaviour).
* It is a per-field failure, so per FR-021 it cannot cost anything else.

This is deliberately *not* modelled as a blocking unknown. It cannot corrupt data, because
nothing is written until the operator has looked at the number.

### §7. Amazon numbers nothing, so line identity is positional

**Decision**: `line_number` is the **1-based index of the row in document order**, and the
capture writes it to `purchases.order_line_number` exactly as the other two vendors do.

**This is the one place Amazon is weaker than both existing vendors**, and the spec already
flagged it (FR-018, SC-005). DigiKey supplies `DetailId`; McMaster prints its own line numbers.
Amazon supplies neither, so position is the only candidate.

**Why this is acceptable**: the failure mode that made positional pairing catastrophic in
feature 024 was pairing *purchases* to lines positionally at re-capture time, where a change
could be written to the wrong row. Here the position is **captured once, at read time, and
stored**, which is what `order_line_number` is for. A re-capture then pairs on the stored
number, not on position — the same first pass both existing vendors use.

**The residual risk**: if Amazon reorders the rows between capture and re-capture, stored line 2
pairs to what is now displayed as line 3. Two consequences, both bounded:

* Where the two lines carry **different** ASINs, the review shows a mismatched pairing that the
  operator can see, because the row names its product.
* Where they carry the **same** ASIN, the two lines are interchangeable anyway and the mispairing
  is not observable — and not harmful, since the recorded quantity and price are identical.

**Alternative rejected**: pairing on ASIN alone. That is precisely the bug PR #116 fixed; an
order can carry the same item twice and a part number does not identify a line.

### §8. What is deliberately not read

The order page also carries the shipping address, the buyer's name, the payment method and the
order total. **None of it is read**, on the same principle both existing order models state:
personal detail the catalog has no use for is not read, rather than read and discarded.

This research recorded no ASINs, product titles or order numbers from the operator's account
into this repository, for the same reason.

---

## Part B — the consolidation

### §9. What is actually shared today, and what is not

Read out of `app/catalog_service.py`, `app/product/routes.py`, `app/models.py` and the
templates. The honest measurement matters, because "these two are duplicates" is easy to assert
and the plan has to act on the parts that really are.

**Already shared — nothing to do**:

* `OrderCaptureReview` and `ReviewedLine` (`app/models.py:1616`, `:1693`). Both order flows
  already build the same review type. **The seam this feature needs already half exists**, which
  is the single biggest reason this consolidation is cheap.
* `OrderLineState`, `Purchase`, `Product`, `ProductIdentifier`, `receive_purchase`.
* `purchases.supplier_order_reference`, `.order_line_number`, `.vendor_order_id`.

**Duplicated, and near-identical**:

| Pair | Lines | How they differ |
|---|---|---|
| `_recorded_digikey_lines` / `_recorded_mcmaster_lines` | ~70 each | How the rows are fetched, and `line.digikey_part_number` vs `line.part_number`. The two-pass pairing algorithm is **character-for-character the same idea**, comments included |
| `_review_digikey_line` / `_review_mcmaster_line` | ~90 each | Where the suggested description comes from, and which identifier looks the product up |
| `capture_digikey_order` / `capture_mcmaster_order` | 154 / 197 | Enrichment (DigiKey only), which identifiers get written, and what the result type reports |
| `_orphaned_digikey_purchases` / `_orphaned_mcmaster_purchases` | ~25 each | The vendor filter |
| `_apply_digikey_change` / `_apply_mcmaster_change` | ~25 each | McMaster's honours an operator override and returns whether it changed anything |
| `DigiKeyCaptureResult` / `McMasterCaptureResult` | 2 dataclasses | One extra field each, and they are the *same* field wearing different names: `lines_unenriched` vs `lines_incomplete` — both are "lines that came back thin, named rather than counted" |
| `digikey_order_review.html` / `mcmaster_order_review.html` | 184 / 288 | Pack arithmetic, and the enrichment column |
| `digikey_order.html` / `mcmaster_order.html` | 98 / 121 | Column set |
| `_digikey_decisions` / `_mcmaster_decisions`, `_digikey_capture_summary` / `_mcmaster_capture_summary` | ~20/~35 each | Field names |

**Genuinely vendor-specific — the irreducible remainder**:

1. **How an order is obtained.** API call (DigiKey) vs agent payload (McMaster, Amazon).
2. **What identifies a line.** `DetailId` / McMaster's printed number / positional index.
3. **What identifies an item, and which identifiers a captured line writes.** DigiKey writes a
   `DISTRIBUTOR` part number *and* an `MPN`; McMaster writes a `DISTRIBUTOR` part number and an
   `MPN` only where the page stated one; Amazon writes an ASIN.
4. **Where the suggested description comes from.** Enriched part detail / the page / the title.
5. **Enrichment.** DigiKey only, and it is network I/O that must stay outside the session.
6. **Line arithmetic.** McMaster's packs-to-units conversion; nobody else has one.
7. **Where a scan of a delivered package lands.** §11.
8. **What extra columns the review and order screens show.** Backorder counts / pack figures /
   nothing.

That list is FR-036, and it is short enough to be worth the consolidation.

### §10. Where the vendor-specific part goes

**Decision**: one `OrderVendor` value per vendor — a small frozen dataclass in
`app/services/order_vendors.py` holding the vendor name, the identifier types a captured line
writes, and the handful of callables from §9 that genuinely differ. The shared flow is one set
of methods on `CatalogService` that take it.

**Rationale, stated against Constitution I because it has to be**: "no abstraction for a single
implementation; one implementation needs no interface" is the rule, and it is the right rule.
This is **three** implementations, two of which have already shipped and been through review, so
the differences are *measured* (§9) rather than anticipated. The prohibition is on speculative
generality; generalizing across three known cases is the opposite of speculative.

The check that it stayed honest is FR-037: a fourth vendor is a reader plus one `OrderVendor`
value. If a future vendor needs a fourth branch inside the shared flow, the seam was drawn in
the wrong place.

**Alternatives rejected**:

* **A class hierarchy with a `VendorOrderCapture` base and three subclasses.** More machinery
  than the problem has: the variation is data and a few functions, not behaviour needing
  polymorphic dispatch across a deep call tree. A dataclass of callables is the boring version.
* **Leave the two as they are; write Amazon as a third copy.** Rejected by the spec (US3), and
  by the evidence: two of the defects fixed in review of PR #123 were the McMaster copy of
  behaviour the DigiKey copy had already had corrected. A third copy triples that.
* **Consolidate the templates only.** The templates are the *smallest* part of the duplication
  and the least dangerous; the orchestration is where the defects were.

### §11. Receiving: three vendors, three landings, one rule

`_receive_url()` in `app/product/routes.py:1812` currently branches on
`vendor == MCMASTER_VENDOR`. The rule underneath is already vendor-neutral and just needs
saying:

| Outstanding candidates a scan names | Where it lands |
|---|---|
| Exactly one | That line's receipt, quantity pre-filled from the label where it carried one |
| More than one | The choice page (`receive_choice.html`) — the catalog never picks |
| None, but some received | Said plainly; nothing is received twice |

DigiKey's current "several → the order screen" behaviour is a *special case* of the middle row,
available only because a DigiKey label names its order, so all candidates are lines of one order.
The choice page already handles the general case.

**Decision**: state the rule once for all vendors, and keep DigiKey's landing exactly as it is
today, because FR-041 forbids changing it and SC-011 measures that with the existing tests.

**Amazon adds nothing to this path.** An Amazon package names neither the order nor the line, and
a product created from an order line carries no barcode (§ FR-025 — no listing fetch). So an
Amazon line is reachable by scan only when the operator has *also* captured its listing page and
that listing yielded a barcode. This is why US2 is screen-driven and why it is its own story.

### §12. The captured-orders list

**Decision**: derive it, exactly as an individual order is derived. One query over `Purchase`
grouped by `(vendor, supplier_order_reference)`, ordered by most recent order date.

**Rationale**: there is no orders table and this feature does not add one — an order *is* the
purchases carrying its number, which is the invariant both shipped features rest on. Adding a
table would create a second place for the truth to live and a way for the two to disagree.

At this application's scale (one operator, a few orders a week) this is a small aggregate over a
table with an index on `supplier_order_reference`. Per Constitution I no further optimization is
warranted without a measurement.

### §13. No schema change

**Decision**: this feature ships **no Alembic revision**.

Amazon needs `supplier_order_reference` (exists, indexed), `order_line_number` (exists) and
`vendor_item_id` (exists, indexed). `vendor_order_id` — added for McMaster because McMaster shows
no order number — stays NULL for Amazon, because an Amazon order number is stable, visible and
printed on the page.

This is worth stating explicitly because both predecessor features needed one, and a reader
would reasonably expect a third.

### §14. Testing

**Fixtures**: one saved Amazon order-details page under `tests/e2e/fixtures/`, following the
precedent set by `mcmaster_order.html` and the Amazon listing fixtures — **scrubbed** of address,
buyer and payment before it is committed, and reduced to what the readers touch. Degraded
variants (a row with no ASIN, a page with no rows, a price that will not parse) follow
`mcmaster_order_unreadable.html`'s example.

The fixture must **keep** a realistic amount of recommendation markup, because §4's trap is
exactly what a stripped-down fixture would stop catching.

**The regression gate is the point.** FR-041 and SC-011 say the existing DigiKey and McMaster
tests pass **unchanged**. They are the specification of the behaviour being consolidated, so
they must not be edited to accommodate the refactor — if a shared implementation cannot satisfy
them as written, the seam is wrong. `tests/unit/test_digikey_capture.py`,
`test_digikey_receive.py`, `test_mcmaster_capture.py`, `test_mcmaster_receive.py`,
`test_mcmaster_routes.py` and the six e2e order files are the gate.

**E2E waits**: the review is server-rendered, so `expect(locator)` on the rendered review is the
condition — pattern C in `CLAUDE.md` ("render-implies-completion"). No new waiting problem is
introduced.

### §15. Risks

| # | Risk | Bound |
|---|---|---|
| R1 | The qty>1 rendering is unconfirmed (§6) | One task; safe failure; visible on the review before any write |
| R2 | The refactor changes shipped DigiKey/McMaster behaviour | The existing suites are the gate and must pass **unedited** (§14) |
| R3 | Amazon's markup changes | Per-field independence (FR-021) + the loss is stated (FR-022). Lower exposure than McMaster's hashed classes (§3) |
| R4 | Recommendation ASINs read as order lines | Row-scoped extraction, and a fixture that keeps the recommendation markup (§4, §14) |
| R5 | Positional line identity mispairs on re-capture | Captured once and stored, not re-derived (§7) |
| R6 | The consolidation grows beyond the feature | FR-037 is the test; if a vendor needs a branch inside the shared flow, stop and re-cut |
