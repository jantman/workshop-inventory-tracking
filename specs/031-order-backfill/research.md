# Research: Backfilling Past Orders

**Feature**: 031-order-backfill | **Date**: 2026-08-28 | **Spec**: [spec.md](./spec.md)

Everything below was established by reading the code in this repository or by reading the
vendors' own published documentation. Where something could not be established, it says so and
names the task that closes it.

---

## §1 — The arrival seam already exists, and it is one line

`CatalogService.capture_order_lines` (`app/catalog_service.py:1818`) builds every purchase for
every vendor in one place, and the field this feature needs is already there, hard-coded:

```python
purchase = Purchase(
    product_id=product.id,
    vendor=vendor.name,
    order_date=order.order_date or datetime.now(),
    # Outstanding at capture, whatever the vendor says about
    # shipping. Shipped is their state; received is the
    # operator's, and only they can say it.
    received_date=None,
    ...
)
```

**Decision**: FR-024 is `received_date=None` becoming `received_date=<the operator's date>` when
the line's decision says it arrived. Nothing else in the write path changes.

**Rationale**: the comment above that line is still right — received is the operator's state and
only they can say it. This feature does not weaken that; it gives them a second place to say it,
on an order they are telling the catalog is historical. The write is the same write.

**Alternatives considered**:

- *Call `receive_purchase` for each new purchase after capture.* Rejected: it reopens a session
  per line (the docstring on `capture_order_lines` explains why the whole order writes in one
  session), and it drags in the count and flag side effects that §2 establishes must not happen.
- *A separate "settle this order" action on the order screen.* This was one of the options put to
  the operator during `/speckit-specify`; they chose capture-time. It would also have meant a
  second pass over the whole history.

**Where it is decided**: `_order_decisions` (`app/product/routes.py:1236`) already walks the
order and builds one dict per line from `include[key]`, `description[key]`, `quantity[key]`,
`unit_price[key]`, `resolution[key]`, `apply_change[key]`. One more key — `arrived[key]` — is the
whole route-side change, and it lands in the one function both confirm routes call.

---

## §2 — Arrival at capture must not touch counts or flags, and that is a decision, not an omission

`receive_purchase` (`app/catalog_service.py:1503`) does four things: sets `received_date`, amends
quantity/price/description, **adds the received quantity to a tracked product's count**, and
**clears the product's manual low flag and that flag's date**.

**Decision**: capture-time arrival does the first and none of the other three. A purchase created
with `received_date` already set never passes through `receive_purchase`, so this is satisfied by
construction rather than by a guard — but it is stated here, tested explicitly, and said out loud
on the review, because it is a real asymmetry that a reader will otherwise assume is a bug.

**Rationale**: FR-028 requires it, and the requirement is right. A delivery from two years ago has
already been consumed; adding it to today's count would make the count wrong in exactly the way
backfill exists to avoid. The same argument covers the low flag: a flag set last month is a
statement about today's shelf, and a 2023 delivery is not evidence against it.

**The case this gets wrong, and why that is acceptable**: an order captured *today* that arrived
*yesterday* — a real use for the same control — will not bump a tracked count. The operator's
recourse is the `+`/`−` buttons on the product, which is the shelf-counting path anyway. Making
the behaviour conditional would be a knob for a case nobody has reported, which Constitution I
prohibits.

**Consequence for FR-027, which is free**: the reorder list's "on the way" is
`Product.purchases.any(Purchase.received_date.is_(None))` (`app/catalog_service.py:597`), and the
captured-orders list counts outstanding lines with
`case((Purchase.received_date.is_(None), 1), else_=0)` (`app/catalog_service.py:2505`). Both are
derived from `received_date` and nothing else, so setting it at capture makes both correct with no
change to either. `CapturedOrder.is_complete` follows.

---

## §3 — Re-capture already leaves delivered lines alone (FR-030)

`capture_order_lines` settles "already captured" before the include gate:

```python
existing = recorded.get(line.form_key)
if existing is not None:
    lines_already_captured += 1
    if decision.get('apply_change'):
        ...
    continue
```

`_apply_order_change` (`app/catalog_service.py:2182`) writes quantity and unit price only.

**Decision**: FR-030 needs no code. It needs a test, because it is currently true by accident of
ordering rather than by intent, and the ordering comment in that function records that the
ordering has been got wrong once already (PR #116 review).

---

## §4 — Per-line hold-back, and where the date lives (FR-029)

**Decision**: `arrived` is **per line**, in `decisions`, alongside `include`. The date is **per
order**, submitted once as `arrived_date` and passed to `capture_order_lines` as an argument.

**Rationale**: keeping `arrived` in the per-line decision dict makes it uniform with every other
line-level choice the form already carries, so `_order_decisions` grows one line and the service
reads it exactly where it reads `include`. Putting the date per line would be five hundred date
inputs on a thirty-line order for a value that is the same on all of them.

**The UI shape**: one order-level checkbox ("This order has already arrived") plus one date input,
and a per-line checkbox rendered only when the order-level one is ticked. The order-level box is a
convenience that ticks the per-line ones; the server reads only the per-line ones. This matches
how `include-line` already behaves in `order_review.html` and needs no new JavaScript file.

**Validation**: `_validate_receipt_order` (`app/catalog_service.py:1661`) already refuses a
received date earlier than the order date, and it is the same check receiving uses. The arrival
date is validated once, before the session opens, for the same reason `receive_purchase`
validates before opening one: a refusal must leave nothing half-written. A blank date with the box
ticked falls back to the order's own date (FR-026), which is the best available answer and is
never today's date.

---

## §5 — DigiKey has an order-listing endpoint, and its exact shape is the one open input

**What is established.** DigiKey's OrderStatus v4 changelog states the history route moved from
`/History` to `/orders`, that a new OrderSearch "returns all orders placed within the specified
timeframe and includes the details for each order", that paging was added ("page through orders,
like on Digikey.com"), that `includeCompanyOrders` was renamed `shared`, and that `openOnly` and
`includes` were removed. The portal publishes a SearchOrders endpoint under
`products/order-status/orderstatus/searchorders`.

That gives the path with high confidence — `GET {base}/orderstatus/v4/orders` — because it is the
documented rename and it sits under the same `/orderstatus/v4/` prefix as
`/orderstatus/v4/salesorder/{id}`, which this codebase already calls successfully
(`app/services/digikey.py:132`).

**What was not established from documentation**: the exact query parameter names for the date
range and paging, and the exact response field names per order. The portal renders those only
inside its Swagger file, which is not fetchable as text.

> **CLOSED 2026-08-28 by T001 — see [verification.md](./verification.md).** The endpoint returns
> 200 on the 2-legged token this application already holds; no 3-legged flow is needed and the
> fallback below is not taken. The window is set by `startDate` / `endDate` as `YYYY-MM-DD`, and
> **omitting them is wrong rather than merely unfiltered** — the default window is narrow. Three
> findings changed the implementation: the identifier the capture screen takes is `SalesOrderId`,
> nested inside each order's `SalesOrders` array rather than the top-level `OrderNumber`; one order
> can hold several sales orders, so the listing flattens to one row per sales order; and each sales
> order carries its `LineItems`, so the line count costs no second call.

**Decision**: treat the parameter names as an input to be closed by one live call, exactly as
feature 024 closed its own unknowns — `specs/024-digikey-order-capture/verification.md` records
that the `X-DIGIKEY-Account-ID` behaviour was verified against the live API on 2026-08-22, and the
same account and credentials are configured here. The task that does this is the first task of the
DigiKey slice, and it writes its findings into `verification.md` before any client code is
written.

**The stated fallback, per the spec's Assumptions**: if the endpoint turns out not to be reachable
on the 2-legged token this application holds — the plausible failure, since a 2-legged token
identifies the *application* and orders are scoped by `X-DIGIKEY-Account-ID`, and DigiKey could
reasonably gate a whole-account listing behind 3-legged auth — then FR-018 through FR-022 are
**dropped to McMaster's shape**: the operator reads sales order numbers off DigiKey's own order
history page in the browser and feeds them to the screen that already exists, and the
documentation says so. **A 3-legged OAuth flow is not the fallback and must not be built**: it
means a browser redirect, an HTTPS callback and a refresh token on disk, which is a login system
for an application whose constitution says it has none.

**Authentication and account scoping**: unchanged. The listing goes through `DigiKeyClient._get`,
which already attaches the token and `X-DIGIKEY-Account-ID` and already maps
`account id must not be 0` to `ConfigurationError` — which is exactly what FR-021 asks for, at no
cost.

**Decimal**: `list_orders` parses with `json.loads(body, parse_float=Decimal)` through the
existing `_get`. The module docstring in `app/services/digikey.py` says "no `.json()` in this
module" twice; the listing does not become the exception.

---

## §6 — Where the DigiKey listing goes: the screen that already exists

**Decision**: the listing renders on `GET /products/digikey/orders`
(`app/product/routes.py:1134`), above the sales-order-number form that is already there. No new
route, no new template, no new navigation entry.

**Rationale**: that screen is already the answer to "I want to capture a DigiKey order", it is
already where every DigiKey failure lands back (its template says so), and it already includes
`_digikey_problem.html`, which is the not-configured message FR-021 requires. Adding a second
screen would mean a second place the not-configured state has to be got right.

**Each row is a submit**, posting `sales_order_number` to the same route — so FR-019 reaches the
existing review with no new confirm path, and the capture-by-number form stays on the page as the
fallback FR-022 requires.

**A failure to list must not break the form.** The listing is rendered from a value that may be
absent; a `WorkshopInventoryError` from `list_orders` is caught at the route and turned into a
message beside a form that still works.

---

## §7 — The Amazon export: file, columns, and what the command may assume

**The file.** Amazon's *Request Your Data* → *Your Orders* delivers a zip whose retail order file
has been named `Retail.OrderHistory.1.csv` and `Retail.OrderHistory.2.csv` in recent exports;
issue #125 refers to it by an older name, `Your Amazon Orders/Order History.csv`. Both shapes have
existed.

**Decision**: the command takes a **path to a file** the operator names. It does not look inside
the zip, does not guess the filename, and does not care what the file is called. This is one
argument instead of an archive layout that Amazon has already changed at least once.

**The columns.** The published column set for the retail order history export includes: `Website`,
`Order ID`, `Order Date`, `Purchase Order Number`, `Currency`, `Unit Price`, `Unit Price Tax`,
`Shipping Charge`, `Total Discounts`, `Total Owed`, `Shipment Item Subtotal`,
`Shipment Item Subtotal Tax`, `ASIN`, `Product Condition`, `Quantity`, `Payment Instrument Type`,
`Order Status`, `Shipment Status`, `Ship Date`, `Shipping Option`, `Shipping Address`,
`Billing Address`, `Carrier Name & Tracking Number`, `Product Name`, `Gift Message`,
`Gift Sender Name`, `Gift Recipient Contact Details`.

**Decision**: the command requires exactly two of them — `Order ID` and `Website` — and reads
`Order Status` if it is present. Requiring two columns rather than twenty-seven is what lets the
command survive Amazon adding, removing or renaming the other twenty-five, and FR-014's "refuse
plainly, naming what it could not find" is then a real message about a real missing column rather
than a whole-schema match.

**Why `Website`**: the export can contain orders from `amazon.co.uk` as well as `amazon.com`, and
an order id is only meaningful against the site that issued it. The address the command emits is
built from the row's own `Website` value, so a mixed export does not produce thirty dead links.

**Order id shape.** The capture agent recognizes an Amazon order page by
`AMAZON_ORDER_PATH = '/your-orders/order-details'` and
`AMAZON_ORDER_ID_PATTERN = /(?:^|[?&])orderID=(\d{3}-\d{7}-\d{7})(?:&|$)/`
(`app/static/js/capture-agent.js:82-83`).

**Decision**: the command emits `https://{website}/gp/css/order-details?orderID={id}` only for ids
matching `\d{3}-\d{7}-\d{7}`, and reports the count of rows whose id did not match rather than
emitting them. The legacy `/gp/css/` address is deliberate: the agent's own comment records that
it 302s to the canonical `/your-orders/order-details` path, so the agent only ever runs on the
canonical one — and the legacy form is the shorter, stabler thing to write into a file.

Digital orders (ids beginning `D01-`) live in a different file in the export and are filtered out
by that pattern for free, which is the right outcome: they are not physical goods.

**`Order Status` is reported, never filtered.** A cancelled or returned order is a real edge case
in the spec, and the operator's edit of the file is authoritative (FR-012). So the command counts
how many of the orders it is about to emit carry a status other than the ordinary one and says so
in its summary. It does not drop them, because dropping rows the operator kept would make the
command's output disagree with the file they edited — and a filter would be a knob.

**No prices, no arithmetic.** The command reads `Order ID`, `Website` and `Order Status` and
nothing else. Constitution III is not at risk because no monetary value is ever parsed: prices come
from the order page at capture, as they always have.

---

## §8 — Where the reduction command lives

**Decision**: the parsing is a pure function in a new module `app/services/amazon_order_export.py`;
`manage.py` gains an `orders` group with one command that reads the file, calls it, and prints.

**Rationale**: `manage.py` is already a `click` group-of-groups (`db`, `photos`, `audit`), so a
fourth group costs nothing and the operator already knows `python manage.py ...`. Keeping the logic
out of the click callback is the same rule Constitution II applies to routes — thin entry point,
logic in a service — and it is what lets `tests/unit/test_amazon_order_export.py` test the
behaviour with a list of dicts and no CLI runner.

**Alternatives considered**: a top-level `scripts/` directory (rejected: the repository has none,
and one file does not justify inventing a tree); a web upload (rejected explicitly in the spec,
FR-016 — it would be an upload path, a parser and a screen for a job run once).

**Dependencies**: `csv` from the standard library. No new package, per Constitution I.

---

## §9 — No schema change

`Purchase.received_date` already exists and is already nullable — it is what the whole outstanding
model rests on. Setting it earlier in a purchase's life is not a schema concern.

**Decision**: no Alembic revision. This is the second consecutive order feature not to ship one.
Constitution V is satisfied by there being nothing to migrate, not by an empty migration.

---

## §10 — What this feature does *not* add to the vendor seam

`OrderVendor` (`app/services/order_vendors.py`) is the measured list of what one vendor's capture
may differ from another's, and its own docstring sets the standing test: a fourth vendor should be
one value there plus a reader, and "if a future vendor needs a branch inside the shared flow
instead, the seam is wrong".

**Decision**: arrival adds **no member** to `OrderVendor`. Whether an order has already arrived is
a fact about the order the operator is capturing, not about the vendor they bought it from, and it
is identical for all three. The DigiKey listing likewise adds nothing: it is enumeration, which
happens before the seam and never crosses it.

This is worth stating because the temptation is to add a `supports_arrival` flag. There is no
vendor for which the answer is no.

---

## §11 — Documentation shape

**Decision**: one new user-manual chapter, **Backfilling Past Orders**, placed after the three
vendor chapters and before *Printing Product Labels*, with a table-of-contents entry and a
one-line cross-reference added to each of the three vendor sections.

**Rationale**: FR-001 requires it to be discoverable from the user documentation, and the manual's
existing shape already answers "how do I capture from vendor X" per vendor. Backfill is the
cross-vendor procedure, so it reads as its own chapter rather than as three paragraphs repeated
three times. FR-003, FR-004 and FR-008 are per-vendor statements *inside* that chapter.

**Spelling**: `catalog`, never `catalogue`, per `CLAUDE.md`. The check that matters is
`grep -ric "catalogue" README.md docs/ app/ tests/` returning nothing.

---

## §12 — Testing approach

**Unit** (`nox -s tests`, network blocked, fixtures via `tests/conftest.py`):

- `tests/unit/test_order_backfill.py` — arrival at capture, for all three vendors through the one
  flow: date recorded; blank date falls back to the order date; a date before the order date
  refused with nothing written; a held-back line left outstanding; **a tracked product's count and
  its manual low flag both unchanged** (§2); re-capture of a delivered line leaves it untouched
  (§3); the captured-orders list reports the order complete and the reorder list does not mark it
  on the way (§2's free consequence, asserted rather than assumed).
- `tests/unit/test_amazon_order_export.py` — dedupe, order-id shape filtering, per-row `Website`,
  a missing required column refused by name, the counts in the summary.
- `tests/unit/test_digikey_client.py` (existing file) — `list_orders` against a mocked response:
  the path called, `Decimal` in the parsed result, and each error mapped the way `get_order`'s are.

**E2E** (`nox -s e2e`, 15-minute timeout, run detached per `CLAUDE.md`):

- `tests/e2e/test_order_backfill.py` — capture an order with the arrival box ticked and assert on
  the order screen and the captured-orders list.

**Waiting**, per Constitution IV and the `CLAUDE.md` practice section: the confirm is a form POST
that navigates, so the landed page is the signal — pattern C, render-implies-completion. The
order-level checkbox that ticks the per-line ones is synchronous DOM work with no fetch behind it,
so `expect(line_box).to_be_checked()` is the condition. **No `count()` or `is_visible()` against
the orders table before an `expect(...)` has established it**, and the negative assertion "no
outstanding lines" is the one most at risk of passing against a table that has not rendered.

**No new pytest marker**, so `pytest.ini` is untouched under `--strict-markers`.

---

## Sources

- [OrderStatus Changelog — DigiKey Developer Portal](https://developer.digikey.com/dk-api-changelogs/orderstatus-changelog)
- [SearchOrders — DigiKey Developer Portal](https://developer.digikey.com/products/order-status/orderstatus/searchorders)
- [OrderStatus — DigiKey Developer Portal](https://developer.digikey.com/products/order-status/orderstatus)
- [How to Export Your Amazon Order History to a Spreadsheet — iTechGuides](https://www.itechguides.com/how-to-export-your-amazon-order-history-to-a-spreadsheet/)
- [Analysing 12 years of Amazon purchases — Jake Lee](https://jakelee.co.uk/analysing-my-amazon-purchases/)
