# Research: DigiKey Order Capture and Receiving

**Feature**: `specs/024-digikey-order-capture/` | **Date**: 2026-08-22

Everything below was checked either against DigiKey's developer portal or against this
repository. Where a fact could not be confirmed without an API key, it says so and names the
task that confirms it. **Nothing in the plan depends on an unconfirmed schema field without a
stated fallback.**

---

## 1. What DigiKey publishes, and what it costs

**Decision**: Use three of DigiKey's API products — Product Information V4, Order Status, and
(read-only) nothing else. Do not use the Ordering API.

**Findings** (developer.digikey.com/products, /tutorials-and-resources/shared-concepts):

| Product | What it gives us | Quota |
|---|---|---|
| Product Information V4 | Part detail by part number: manufacturer, MPN, description, datasheet, photo, category, parameters | 120/min, 1,000/day |
| Order Status | `GET /orders` (history in a date range) and `GET /salesorder/{salesOrderId}` (one order, with its line items) | 120/min, 1,000/day |
| Barcode | Decodes a 2D label server-side | 120/min, 1,000/day |
| Ordering | **Places** orders. **Requires an active DigiKey Credit account.** | 10/min |

1,000 calls a day against a workshop that places an order a fortnight is not a constraint
worth designing around. No caching layer, no batching, no backoff scheduler — Principle I.
A `429` is surfaced as `RateLimitError` and the operator retries.

**The Barcode API is deliberately not used.** `app/utils/ecia.py` already parses the format-06
envelope locally and has since the first release; sending the label to DigiKey to be told what
`1K` means would be a network round-trip to replace a working pure function.

**Alternatives rejected**: scraping DigiKey's order and product pages with the existing capture
agent (the user chose against it, and DigiKey's markup is not a contract); importing the CSV
DigiKey lets you download per order (a manual step per order, and it carries no part detail).

---

## 2. Authentication: try 2-legged first

**Decision**: `grant_type=client_credentials` (2-legged) against
`POST {base}/v1/oauth2/token`, with `client_id` and `client_secret` from the environment. Cache
the token in memory on the client object until shortly before its stated expiry.

**Rationale**: DigiKey's product page states that Order Status "supports two-legged and
three-legged" OAuth, and the RetrieveSalesOrder endpoint page repeats it ("Both 2 and 3-legged
OAuth"). 2-legged needs no browser round-trip, no HTTPS redirect URI, and no token file on
disk — which matters here, because the 3-legged flow's `redirect_uri` **must use TLS**, and
this application is not always served over TLS (the Amazon bookmarklet's whole documented
caveat is exactly that).

Token lifetimes, from DigiKey's own flow documentation: 2-legged access token **10 minutes**;
3-legged access token 30 minutes with a refresh token that **does not expire**.

**This is the plan's single largest unverified assumption**, and it is gated rather than
assumed. `T001` in tasks is a manual verification against the real API with a real sales order
number, run *before* any capture code is written. Two ways it can come back:

- **2-legged returns the order** → build as planned. Config is two secrets, nothing on disk.
- **2-legged returns nothing / 401 / an empty order** → fall back to the 3-legged flow: a
  one-time authorization in a browser, the refresh token stored in an untracked
  `credentials/digikey_token.json` alongside the Google `token.json`, refreshed on demand.
  This adds one small module and one route; it changes no other decision in this plan.

**A third possibility must be reported, not worked around**: DigiKey's API FAQ says "We
require customers to have a DigiKey Credit Account before API orders can be *placed*" — which
is scoped to the Ordering API, not to Order Status. If Order Status nevertheless refuses a
personal account, **User Story 1 is not buildable as specified** and the feature reduces to
Stories 2–4 minus order capture. That is a finding to bring back to the user, not something to
route around by scraping. `T001` exists to find this out on day one rather than in week three.

**Alternatives rejected**: 3-legged unconditionally (more machinery than the verification might
show is needed, and it needs TLS this deployment does not guarantee); storing a long-lived
token by hand (no refresh path).

---

## 3. Do not use the `digikey-api` package

**Decision**: Write a ~200-line client in `app/services/digikey.py` using `requests` (already in
`requirements.txt` at 2.33.1) and the standard library.

**Rationale**, in the order that matters:

1. **It types prices as `float`.** The generated model at
   `digikey/v3/ordersupport/models/line_item.py` declares `'unit_price': 'float'` and
   `'total_price': 'float'`. Constitution III prohibits binary floating point for measured
   quantities, and a price is one. Our client parses with
   `json.loads(body, parse_float=Decimal)` so a price never exists as a float at any point.
2. **Its released code is v3.** The published package wraps OrderDetails v3; v4 support exists
   only in an unmerged pull request.
3. **Principle I**: dependencies must earn their place. Four endpoints, all `GET`, all returning
   JSON, is not a package.

**What the package is still good for**: it is a public, machine-generated record of the v3
response shapes, and §5 below is taken from it.

---

## 4. Distributor label identifiers — already solved in this repo

**Decision**: Read the sales order number from ECIA `1K` and the DigiKey part number from `P`.
Change nothing in `app/utils/ecia.py`.

**Confirmed three ways**: `specs/001-product-catalog/research.md:145` records `1K` as "Supplier
order number"; `app/catalog_service.py:1701-1702` already maps `K` → `order_reference` and
`1K` → `supplier_order_reference`; and an independent teardown of a real DigiKey label
(hackaday.io/project/90456, log 131388) gives `P` = item code assigned by customer (DigiKey's
own part number), `1P` = item code assigned by supplier (the manufacturer's), `K` = order
number assigned by customer, `1K` = order number assigned by supplier, `10K` = invoice number.

`ecia.parse()` already extracts all seven identifiers this feature needs (`P`, `1P`, `Q`, `K`,
`1K`, `9D`, `10D`). **The gap was never the parsing — it was that `1K` had nowhere to go.**
`specs/001-product-catalog/data-model.md:70` claims `order_reference` is "also filled from ECIA
`K` / `1K`"; in the shipped code only `K` reaches it and `1K` is rendered into a note on the
product (`_ecia_note` in `app/product/routes.py`). Section 6 gives it a column.

**Pre-existing risk, not introduced here**: all of this depends on the scanner wedge
transmitting the `GS` separators. The user manual already warns about this. The issue's own
example label is pasted with the separators stripped by GitHub, which is why it reads as one
run-together string.

---

## 5. Response shapes

**Decision**: Parse into our own frozen dataclasses (§7 of `data-model.md`), never pass
DigiKey's JSON past `app/services/digikey.py`.

**Order Status — confirmed for v3, to be re-confirmed for v4 in `T001`.** The v3 generated
models give:

*Sales order*: `SalesorderId`, `CustomerId`, `BillingAccount`, `Email`, `PurchaseOrder`,
`PaymentMethod`, `Supplier`, `ShippingMethod`, `ShipmentType`, `Currency`, `ShippingAddress`,
`BillingAddress`, `ShippingDetails[]`, `LineItems[]`.

*Line item*: `PoLineItemNumber`, `DigiKeyPartNumber`, `ManufacturerPartNumber`,
`ProductDescription`, `Manufacturer`, `CountryOfOrigin`, `Quantity`, `CustomerReference`,
`UnitPrice`, `TotalPrice`, `QuantityBackorder`, `BackOrderDetails`, `QuantityShipped`,
`InvoiceId`, `DefaultShipping`, `Schedule[]`.

That is every field FR-003 asks the review to show, plus `Currency` for the assumption about
not converting currency.

**The order date is the one field to watch.** The v3 sales-order response has **no** date; only
the history item does (`SalesorderId`, `CustomerId`, `DateEntered`, `PurchaseOrder`). v4 very
likely added it. **Fallback if it did not**: read the date from `GET /orders` filtered to that
sales order, one extra call at capture time. **Second fallback**: today's date, which is what
`capture_order` already defaults to. Neither costs a redesign.

**Product Information V4** — request `GET {base}/products/v4/search/{productNumber}/productdetails`,
which accepts a DigiKey part number or a manufacturer part number. The response carries a
`Product` object with the description, manufacturer, manufacturer product number, product
variations (each with its DigiKey part number and standard pricing), datasheet URL, photo URL,
product URL, category, and a `Parameters` list of `{ParameterText, ValueText}` pairs. The
endpoint's own documentation page is behind a portal login; **`T001` records one real response
to `tests/fixtures/digikey/productdetails.json` and the dataclass is written from that file**,
not from memory. Field names that turn out to differ cost one mapping edit in one module.

---

## 6. Storage: one column, no new table

**Decision**: Add `purchases.supplier_order_reference` (`String(200)`, nullable, indexed). Add
**no** table for DigiKey orders. A captured order *is* the set of purchases with
`vendor = 'DigiKey'` and that reference.

**Rationale**: everything the spec asks of an order is derivable from its purchases — its lines
(FR-017), how many are outstanding (FR-018, from `received_date IS NULL`), whether a line is
already captured (FR-012), and which recorded line the order no longer contains (FR-013). This
is the same choice the reorder list already makes, and the user manual already sells it:
"Nothing on this page is stored; it is all derived when you open it, so it cannot drift out of
step with your purchases." A `digikey_orders` table would be a second place for the same fact
to live, and Principle I plus Principle V both point away from that.

**The index is the obvious one, not a speculative one**: it is the column every bag scan looks
up by, and it sits beside the existing indexes on `vendor_item_id` (the other half of that
lookup) and `received_date` (the reorder view). At `String(200)` in utf8mb4 it is 800 bytes,
well inside InnoDB's 3072-byte key limit.

**The name is not new.** `supplier_order_reference` is already this codebase's word for ECIA
`1K` (`app/catalog_service.py:1702`, `ECIA_PREFILL_FIELDS` in `app/product/routes.py`). The
column gives an existing name a home.

**One consequence, accepted and stated**: an excluded line (FR-007) is not remembered, because
remembering it would need the table this decision refuses. Re-capturing an order offers a
previously excluded line again. That is arguably the better behaviour — the operator may have
changed their mind — and it is written into the spec's edge cases.

**Alternatives rejected**: a `digikey_orders` + `digikey_order_lines` pair (two tables to keep
in step with the purchases that are the actual record); reusing `order_reference` for the sales
order number (it already holds the customer's own PO, `K`, and one column cannot mean two
things).

---

## 7. Failure states need no new exception class

**Decision**: Map FR-038's four states onto exceptions `app/exceptions.py` already defines.

| FR-038 state | Exception |
|---|---|
| Not configured | `ConfigurationError` |
| Authorization expired or refused | `AuthenticationError` |
| Order or part not found | `ItemNotFoundError` |
| Unreachable or erroring | `TemporaryError` |
| Throttled (`429`) | `RateLimitError` |

**Rationale**: the constitution says to use the project's custom exceptions and explicitly *not*
to "add new error-handling machinery on top of them". All five already exist and
`create_error_handlers(app)` already installs handling for them. This was a pleasant surprise
and it removes a whole design question.

---

## 8. Scan resolution gains a fourth outcome

**Decision**: `ScanResolution.outcome` becomes one of `product`, `create`, `search`, `receive`.
The `receive` payload is the list of purchases matching the label's `1K` + `P`.

**Rationale**: FR-019 requires a scanned bag to land on the *receipt for a line*, which is
neither "here is the product" nor "here is a blank draft". Encoding it as `product` plus a hint
would make the outcome mean two things.

**The invariant being amended, stated plainly**: `resolve_scan`'s docstring says "Three outcomes
and no fourth", citing 001 FR-018 and SC-008. Those requirements say *nothing dead-ends* — every
scan gets an answer. A fourth answer does not weaken that; the final free-text rule still always
matches. The docstring and `specs/001-product-catalog/` cross-references are updated as part of
the work rather than left contradicting the code.

**Ordering inside the ECIA branch is load-bearing**: the order-line lookup must run **before**
the existing `1P` → MPN product lookup. A bag for a part already in the catalog must open the
receipt, not the product page — otherwise FR-019 is satisfied only for parts you have never
bought before, which is the opposite of the common case.

**Zero matches changes nothing.** No captured order, or a part that order does not contain, and
the branch falls through to exactly the behaviour shipped today (FR-024, FR-025).

---

## 9. Where the write lives

**Decision**: The transactional write is a new method on `CatalogService`, in one `_session()`
for the whole order. The HTTP client is `app/services/digikey.py` and knows nothing about the
database. There is no third module.

**Rationale**: FR-039 requires that a failed capture leave nothing partially recorded. Every
`CatalogService` method opens its own session, so building a 24-line order by calling
`create_product` and `record_purchase` 24 times from outside would be 48 transactions and a
half-written order when line 13 fails. One session inside `CatalogService` is the only place
that atomicity is available without inventing a session-passing convention the codebase does
not have.

**`capture_order` is reused for its primitives, not called.** It encodes Amazon's decision
model: a same-day vendor+item duplicate heuristic, a listing-title description fallback, pack
pricing, and captured-barcode promotion. A sales order number is an *exact* idempotency key, so
the heuristic is not merely unnecessary here — it is wrong, because two lines of one order are
two purchases and the heuristic would query one of them. Bending one function to serve both
decision models would make both harder to read; Principle I says prefer the boring version.

**Routes stay thin.** The capture route calls the client, then a read-only review method, then
renders; on confirmation it calls the write method. That is the same two-call shape
`product_capture` already has (`capture_order` then `store_listing_images`), so no new pattern
is introduced.

**Alternative rejected**: a separate `app/digikey_service.py` orchestrating a `CatalogService`.
It reads well until it needs one transaction across the two, at which point it either leaks a
session across a module boundary or gives up atomicity.

---

## 10. Product photo and datasheet reuse the existing image path

**Decision**: For Story 3, fetch the photo and the datasheet through
`app/services/listing_images.py`, after the transactional write, exactly as a listing capture
does.

**Rationale**: that module is described in its own docstring as "the only place in `app/` that
makes an outbound HTTP request to a third party, and the reason the capture write is split in
two" — fast transactional half first, slow partially-failing half after. Every property it was
built for holds here: a datasheet DigiKey cannot serve must not cost the operator the product.
Its `_KNOWN_EXTENSIONS` already includes `.pdf`, and the application already renders PDF
thumbnails, so a datasheet is an attachment like any other.

The client itself makes no attachment requests; it returns URLs and the route decides.

---

## 11. Turning a DigiKey product URL into a part number

**Decision**: Read the manufacturer part number out of the path and look *that* up. Do not try
to derive a DigiKey part number from the URL.

**Findings**: a DigiKey product address has the shape
`digikey.com/en/products/detail/<manufacturer-slug>/<mpn-slug>/<numeric-product-id>`. The last
segment is DigiKey's internal product id, **not** the DigiKey part number — which is why
`tests/unit/test_capture.py:948` asserts that `_asin_from_url` correctly yields nothing for a
DigiKey address. The second-to-last segment is the manufacturer part number, and the
ProductDetails endpoint accepts a manufacturer part number as its `productNumber`.

**Fallback**: a URL whose shape does not match, or an MPN slug DigiKey does not resolve, is
FR-032 — say so and offer the ordinary product form carrying what was entered. No guessing.

---

## 12. Testing without the network

**Decision**: Unit tests parse recorded JSON fixtures; E2E tests point `DIGIKEY_API_BASE` at a
stdlib `http.server` thread serving those same fixtures.

**Rationale**: Constitution IV blocks the network in unit tests (`--blockage`) and requires all
external calls be mocked. `tests/e2e/test_product_page_capture.py` already stands up a
`ThreadingHTTPServer` on a loopback port to play the part of Amazon's image host, for precisely
this reason, so the pattern is established rather than invented. Because the E2E fake needs it,
`DIGIKEY_API_BASE` is a present requirement and not a speculative configuration knob.

**Fixtures are recorded, not written from memory**: `T001` saves one real sales-order response
and one real product-details response into `tests/fixtures/digikey/`, redacting the shipping
and billing addresses, the email, the customer id and the billing account. What the tests then
assert is what DigiKey actually sends.

**Injection point**: the client is built from config and stashed on the app, in the same shape
as the storage backend (`app.config['STORAGE_BACKEND']`), so a test injects a fake by setting
`app.config['DIGIKEY_CLIENT']` and no code learns it is being tested.

---

## 13. Open risks, carried into tasks

| # | Risk | Where it bites | Mitigation |
|---|---|---|---|
| R1 | Order Status may refuse a non-business account, or 2-legged may not see this account's orders | US1 unbuildable as written | `T001` verifies against the live API before any code; §2 states both fallbacks and the report-back |
| R2 | v4 response field names differ from the v3 record in §5 | The client's mapping | Fixtures recorded from the real API in `T001`; the mapping is one module |
| R3 | The sales-order response may carry no order date | FR-008 | Two fallbacks in §5, neither structural |
| R4 | A wedge that eats `GS` separators breaks label scanning | US2 | Pre-existing and already documented in the user manual; not introduced here |
| R5 | A DigiKey product URL may not carry a resolvable MPN | US3 | §11 — refuse plainly per FR-032 rather than guess |
