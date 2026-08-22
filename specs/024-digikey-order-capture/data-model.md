# Data Model: DigiKey Order Capture and Receiving

**Feature**: `specs/024-digikey-order-capture/` | **Date**: 2026-08-22

Two kinds of thing live here and they must not be confused:

- **Persisted** — one new column on an existing table. That is the entire schema change.
- **In-flight** — frozen dataclasses in `app/models.py` that carry DigiKey's answer and the
  review of it from the client, through the service, to the template. None of them is stored.

The reason the second list is so much longer than the first is decision §6 of
[research.md](./research.md): a captured DigiKey order is *derived* from the purchases it
produced, not recorded a second time beside them.

---

## 1. Schema change

### `purchases.supplier_order_reference`

| Property | Value |
|---|---|
| Type | `String(200)` |
| Nullable | Yes — every purchase predating this feature, and every non-DigiKey purchase |
| Indexed | Yes, non-unique |
| Meaning | The **supplier's** order number: ECIA `1K`, DigiKey's sales order number |

It sits beside the existing `order_reference`, which holds the **customer's** order number
(ECIA `K`) and keeps that meaning unchanged. The two are different numbers and one column
cannot hold both.

The name is not invented: `supplier_order_reference` is already this codebase's word for `1K`
in `CatalogService.resolve_scan` (`app/catalog_service.py:1702`) and in `ECIA_PREFILL_FIELDS`
(`app/product/routes.py:98-99`). Until now the value had nowhere to go and was written into a
note on the product.

**Two places must be changed together.** Constitution V requires the Alembic revision, and
`app/database.py` carries the same comment the codebase already uses for this hazard: the unit
suite builds its schema with `create_all` and never runs Alembic, so a column added to only one
of them passes `nox -s tests` and fails on the real database.

- `app/database.py` — add the column to `Purchase`, and to `Purchase.to_dict()`.
- `migrations/versions/<rev>_add_supplier_order_reference.py` — `add_column` + `create_index`
  in `upgrade`, `drop_index` + `drop_column` in `downgrade`, in that order (Constitution V
  requires the downgrade be exercised, and MariaDB will not drop a column an index still
  covers).

**Nothing is backfilled.** An existing purchase has no sales order number to recover.

### What is deliberately *not* added

No `digikey_orders` table and no `digikey_order_lines` table. Every question the spec asks of
an order answers from the purchases:

| Question | Answer |
|---|---|
| What are this order's lines? (FR-017) | `vendor = 'DigiKey' AND supplier_order_reference = ?` |
| How many are outstanding? (FR-018) | …`AND received_date IS NULL` |
| Is this line already captured? (FR-012) | …`AND vendor_item_id = <DigiKey part number>` |
| Which recorded line has the order lost? (FR-013) | recorded set minus fetched set |
| Which line does this bag belong to? (FR-019) | `1K` → reference, `P` → `vendor_item_id`, outstanding |

The cost is that an *excluded* line (FR-007) is not remembered, because there is no row in
which to remember it. Re-capturing offers it again. This is written into the spec's edge cases
and is arguably the better behaviour.

---

## 2. Field mapping — a DigiKey line becomes a Purchase

| Purchase column | Source | Note |
|---|---|---|
| `product_id` | matched or newly created product | FR-005, FR-008 |
| `vendor` | literal `'DigiKey'` | matches `_vendor_from_url`'s existing mapping |
| `vendor_item_id` | line's `DigiKeyProductNumber` | half of the receive-scan key |
| `supplier_order_reference` | order's `SalesOrderId` | the other half; the new column |
| `order_reference` | order's `PurchaseOrder` | the customer's own PO, may be blank |
| `listing_title` | line's `Description` | DigiKey's words, kept verbatim, as an Amazon listing title is |
| `listing_url` | `NULL` | there is no listing; a part page is not what was ordered |
| `order_date` | order's `DateEntered` | verified present on v4; falls back to today if ever absent |
| `quantity` | line's `QuantityOrdered` | |
| `unit_price` | line's `UnitPrice` | `Decimal`, never `float` — research §3 |
| `received_date` | `NULL` | FR-009: outstanding at capture, whatever the order's shipping state |

And on the product side:

| Identifier | Value | Vendor scope |
|---|---|---|
| `MPN` | line's `ManufacturerProductNumber` | none (empty string) |
| `DISTRIBUTOR` | line's `DigiKeyProductNumber` | `DigiKey` |
| `INTERNAL` | generated | as for every product |

`products.manufacturer_part_number` takes the line's value and `products.description` takes
what the operator authored, defaulting to DigiKey's description (FR-006).

**`products.manufacturer` comes from the enrichment call, not from the order line** — a v4
order line has no manufacturer name. So does the product's category, its datasheet, its photo
and its parametric detail. See §3a.

---

## 3. In-flight: what the client returns

Frozen dataclasses in `app/models.py`, alongside `ListingCapture` and following its
`from_json` precedent. Every one is constructed by `app/services/digikey.py` and by nothing
else. **A DigiKey JSON field name appears nowhere past these constructors** — that is the seam
that absorbs a v4 schema surprise (research §5, R2).

### `DigiKeyOrderLine`

| Field | Type | From |
|---|---|---|
| `line_number` | `int` | `DetailId` — **`PoLineItemNumber` is `null` in v4** |
| `digikey_part_number` | `str` | `DigiKeyProductNumber` |
| `manufacturer_part_number` | `str` | `ManufacturerProductNumber` — may be empty (FR-016) |
| `description` | `str` | `Description` |
| `quantity` | `Optional[int]` | `QuantityOrdered` |
| `unit_price` | `Optional[Decimal]` | `UnitPrice` |
| `quantity_shipped` | `Optional[int]` | `QuantityShipped` |
| `quantity_backorder` | `Optional[int]` | `QuantityBackOrder` |
| `country_of_origin` | `str` | `CountryOfOrigin` |

There is **no** `manufacturer` field: a v4 order line does not carry one.

`quantity_shipped` and `quantity_backorder` are display-only: they are what lets the review say
"4 of 10 shipped, 6 on backorder" without inventing a partial-receipt state the model does not
have.

### `DigiKeyOrder`

| Field | Type | From |
|---|---|---|
| `sales_order_number` | `str` | `SalesOrderId`, as a string — it is a reference, never arithmetic |
| `purchase_order` | `str` | `PurchaseOrder` |
| `order_date` | `Optional[datetime]` | `DateEntered`, verified present |
| `currency` | `str` | `Currency`, recorded and displayed, never converted |
| `lines` | `Tuple[DigiKeyOrderLine, ...]` | `LineItems` |

### `DigiKeyPart`

Used by **both** Story 1 (enrichment, §3a) and Story 3 (capturing one part). Several v4 fields
are nested objects rather than flat strings:

| Field | Type | v4 path |
|---|---|---|
| `digikey_part_number` | `str` | `Product.ProductVariations[]` |
| `manufacturer_part_number` | `str` | `Product.ManufacturerProductNumber` |
| `manufacturer` | `str` | `Product.Manufacturer.Name` — **nested** |
| `description` | `str` | `Product.Description.ProductDescription` — **nested** |
| `detailed_description` | `str` | `Product.Description.DetailedDescription` — **nested** |
| `datasheet_url` | `str` | `Product.DatasheetUrl` |
| `photo_url` | `str` | `Product.PhotoUrl` |
| `product_url` | `str` | `Product.ProductUrl` |
| `category_path` | `str` | `Product.Category.Name` — a suggestion, never imposed |
| `unit_price` | `Optional[Decimal]` | `Product.UnitPrice` |
| `parameters` | `Tuple[Tuple[str, str], ...]` | `Product.Parameters[]`, order preserved |

`parameters` becomes product specifications (FR-030), through the same merge rule captured
listings already use: **a specification the operator has edited wins and is not examined.**

**Parsing rules that apply to all three** (they are why these are dataclasses and not dicts):

- Values are extracted **uncoerced** except for two: `quantity` is an `int` and `unit_price` is
  a `Decimal`, parsed via `json.loads(body, parse_float=Decimal)` so no price is ever a float.
- A missing or `null` field becomes `''` / `None`, never a `KeyError`. A response that has lost
  a field must cost that field and nothing else — the same rule the capture agent follows.
- Construction never raises on a well-formed JSON object. A response that is not one is the
  client's problem (research §7), not the dataclass's.

---

## 3a. In-flight: enrichment

A v4 order line carries the two part numbers, a description, a quantity and a price — and
nothing else. Manufacturer, category, datasheet, photo and parametric detail all come from one
`DigiKeyPart` per line, fetched separately
([contracts/digikey-api.md](./contracts/digikey-api.md) §5).

`ReviewedLine` therefore carries an optional `part: Optional[DigiKeyPart]`, and its absence is
an ordinary state rather than an error:

| `part` | Means | Review shows |
|---|---|---|
| Set | The lookup succeeded | Manufacturer, category, parameter count, datasheet present |
| `None` | The lookup failed or the part is unknown to DigiKey | The line, marked as having come back thin |

**A `None` here never blocks a capture.** The line still becomes a purchase carrying everything
the order gave. Only a failed *order* fetch fails a capture — the distinction
[contracts/digikey-api.md](./contracts/digikey-api.md) §5 sets out, and the same one
`listing_images.py` already makes.

---

## 4. In-flight: the review

Nothing is written until the operator confirms (FR-004), so the review is a value object
computed from the fetched order plus the catalog, and rendered.

### `OrderLineState` (`Enum`)

| Member | Meaning | What the review offers |
|---|---|---|
| `NEW` | No product matches this line | An editable description, pre-filled from DigiKey's (FR-006) |
| `MATCHED` | A product carries this MPN or this DigiKey part number, corroborated | Attach to it; no description field (FR-005) |
| `CONFLICT` | The DigiKey part number names a product whose MPN contradicts the line's | A required choice: attach, or separate product (FR-015) |
| `CAPTURED` | A purchase already exists for this order and this part | Shown, not offered; plus any quantity/price change (FR-012, FR-014) |

The four are exclusive and tested in that order.

### `ReviewedLine`

| Field | Type | Note |
|---|---|---|
| `line` | `DigiKeyOrderLine` | |
| `part` | `Optional[DigiKeyPart]` | The enrichment (§3a). `None` is ordinary, never an error |
| `state` | `OrderLineState` | |
| `suggested_description` | `str` | DigiKey's description, trimmed to the 255-character column limit (FR — the "too long" edge case) |
| `product_id` | `Optional[int]` | Set for `MATCHED`, `CONFLICT`, `CAPTURED` |
| `product_description` | `Optional[str]` | For naming the product in the page |
| `product_manufacturer_part_number` | `Optional[str]` | What makes a `CONFLICT` legible |
| `purchase_id` | `Optional[int]` | Set for `CAPTURED` |
| `recorded_quantity` | `Optional[int]` | `CAPTURED` only — for FR-014's change display |
| `recorded_unit_price` | `Optional[Decimal]` | `CAPTURED` only |

### `OrderCaptureReview`

| Field | Type | Note |
|---|---|---|
| `order` | `DigiKeyOrder` | |
| `lines` | `Tuple[ReviewedLine, ...]` | In DigiKey's order |
| `orphaned` | `Tuple[int, ...]` | Purchase ids recorded against this sales order whose DigiKey part number the fetched order no longer contains (FR-013). **Reported, never deleted.** |

`OrderCaptureReview` and `ReviewedLine` are display objects and carry plain values rather than
ORM rows, for the reason `CaptureAssessment` already documents: a relationship that was not
eagerly loaded does not survive the session closing, and a display object has no business
carrying that hazard.

### What comes back from the form

One decision per line, keyed by `digikey_part_number`:

| Field | Values | Applies to |
|---|---|---|
| include | present / absent | Every line. Absent means excluded (FR-007) |
| description | free text | `NEW` lines; blank falls back to DigiKey's (FR-006) |
| resolution | `attach` / `separate` | `CONFLICT` lines only; **required**, no default (FR-015) |
| apply_change | present / absent | `CAPTURED` lines whose quantity or price differs (FR-014) |

A submitted decision for a line the fetched order no longer contains is ignored rather than
acted on — the order is re-read at confirmation, and the fetched order is the authority.

---

## 5. In-flight: `ScanResolution` gains an outcome

`ScanResolution.outcome` becomes one of `'product'`, `'create'`, `'search'`, `'receive'`.

| Field | Change |
|---|---|
| `outcome` | Fourth member `'receive'` |
| `purchases` | **New.** `List[Any]` — the purchases matching the label's `1K` + `P`. Empty for every other outcome. Typed loosely for the same reason `product` is: `app/models.py` must not import `app/database.py` |

`'receive'` is produced only from the ECIA branch, and only when the label carries both `1K`
and `P` and at least one purchase matches. The list may hold already-received purchases; the
route distinguishes:

| Matching purchases | Route behaviour | Requirement |
|---|---|---|
| Exactly one outstanding | Straight to that purchase's receive screen, quantity pre-filled from `Q` | FR-019, FR-020 |
| More than one outstanding | The captured-order screen, with the candidates marked; the operator chooses | FR-026 |
| None outstanding, some received | "Already received", naming the line; nothing is received | FR-023 |
| None at all | Falls through to today's behaviour unchanged | FR-024, FR-025 |

**The lookup runs before the existing `1P` → MPN product lookup**, or a bag for a part already
in the catalog would open the product page instead of the receipt — satisfying FR-019 only for
parts never bought before, which is the opposite of the common case.

---

## 6. State transitions

There is exactly one, and it is the one the application already has:

```
Purchase   received_date IS NULL  ──receive──▶  received_date = <date>
           ("outstanding")                       ("received")
```

**No partial-receipt state is added.** The spec says so and the assumption is recorded there:
outstanding is represented by the absence of a date, with nothing to keep in step with it, and
a third state would touch every screen that reads a purchase. A split shipment is the operator
receiving the line with the quantity that arrived and recording the remainder as its own
purchase — visible, and their decision.

The derived order state follows from its lines and is not stored:

| Lines | Order reads as |
|---|---|
| None captured | Not captured |
| Some outstanding | *n* of *m* outstanding |
| None outstanding | Complete |

---

## 7. Validation rules

| Rule | Source | Where enforced |
|---|---|---|
| A sales order number is required to capture | FR-001 | Route, `ValidationError` |
| Nothing is written before confirmation | FR-004 | The review method performs no write |
| An excluded line writes nothing | FR-007 | Write method skips it |
| A line already captured for this order writes nothing | FR-012 | `OrderLineState.CAPTURED`, and re-checked inside the write's session |
| A `CONFLICT` line must carry a resolution | FR-015 | Write method refuses the whole capture with `ValidationError` |
| A line with no MPN is still capturable | FR-016 | No required-field check on `manufacturer_part_number` |
| A description over 255 characters is refused, not truncated | Edge case | Route, at the point of entry, with the limit stated |
| A blank description falls back to DigiKey's | FR-006 | Write method |
| Prices are `Decimal` | Constitution III | `json.loads(..., parse_float=Decimal)` in the client — verified on live data |
| A failed part lookup costs that line's detail only | FR-041 | `ReviewedLine.part is None`; the capture proceeds |
| A failed capture writes nothing | FR-039 | One `_session()` for the whole order — research §9 |
| A hand-edited specification is not overwritten | FR-030 | The existing capture merge rule |

---

## 8. What this feature does not touch

Inventory items, JA IDs, shortening history and parent-child relationships (Constitution VI)
are not involved. This is the product catalog, whose records have no lifecycle invariants of
that kind. No migration, query or route in this feature reads or writes `inventory_items`.
