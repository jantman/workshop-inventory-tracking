# Data Model: McMaster-Carr Order and Product Capture

**Feature**: 028-mcmaster-order-capture | **Date**: 2026-08-24

Three layers change, and the change gets smaller at each one. The **payload** types are new
and hold what the agent read. The **schema** change is a single column rename. The
**display** types are the ones feature 024 already built, reused unchanged.

---

## 1. Schema change: one column, renamed

### `purchases.digikey_line_number` → `purchases.order_line_number`

| | |
|---|---|
| **Type** | `Integer`, nullable, not indexed — unchanged |
| **Migration** | one new Alembic revision, `down_revision` = current head |
| **Reversible** | `downgrade` renames it back; both directions exercised (Constitution V) |
| **Frozen** | migration `a7c4e1b0f221`, which created it, is not edited |

**Why a rename and not a second column**: research.md §8. In short — the column exists because
pairing lines to purchases positionally corrupted data when one part appeared on two lines of
one order, FR-014 needs exactly that for McMaster, and two nullable columns meaning one thing
is the duplication "boring, obvious code" exists to prevent.

**Two things that must stay in step**, both already flagged in the source:

* The ORM column definition in `app/database.py` must match the revision **exactly**. The unit
  suite builds its schema with `create_all` and never runs Alembic, so drift passes
  `nox -s tests` and fails on the real database (`app/database.py:1085`).
* `Purchase.to_dict()` emits the key. Renaming the column renames the key, which
  `tests/unit/test_digikey_capture.py` asserts on.

**Call sites**: eleven, across `app/database.py`, `app/catalog_service.py` and
`tests/unit/test_digikey_capture.py`. All mechanical.

### Nothing else in the schema moves

Everything this feature records has a column already, and reusing them is what makes a McMaster
order openable and receivable with no new tables:

| Field | Column | Note |
|---|---|---|
| Vendor | `purchases.vendor` | `'McMaster-Carr'` — the value `_vendor_from_url` already derives from `mcmaster.com` (`app/product/routes.py:831`) |
| McMaster part number | `purchases.vendor_item_id` | indexed; half the key a receiving scan matches on |
| McMaster order number | `purchases.supplier_order_reference` | indexed; FR-013's "field of its own, not free text in a note" |
| Which line of that order | `purchases.order_line_number` | FR-014 |
| Quantity (units) | `purchases.quantity` | `Integer`, `CHECK > 0`; packs × pack size is an integer |
| Unit price | `purchases.unit_price` | `Numeric(10, 2)`; written through `price_to_cents` |
| Order date | `purchases.order_date` | nullable — a page that does not state one leaves it blank |
| Outstanding | `purchases.received_date IS NULL` | there is no status column and this feature does not add one |
| Order page address | `purchases.listing_url` | where the capture was read from |
| McMaster's own wording | `purchases.listing_title` | kept distinct from the operator's `products.description` (FR-023) |

**No `McMasterOrder` table.** A captured order *is* the purchases carrying its number, exactly
as a DigiKey order is (024 research §6) and as the reorder list is derived rather than stored.

---

## 2. Payload types — new, in `app/models.py`, not persisted

These live between the hidden form field and the service, the way `ListingCapture` already does.
Frozen dataclasses, built only by `from_payload`, and **never raising on a JSON value**: a field
McMaster stops emitting costs that field alone (FR-036).

### `McMasterOrderLine`

| Field | Type | Source | Rules |
|---|---|---|---|
| `part_number` | `str` | the line's McMaster part number | may be `''` — a shipping or handling line has none (FR-019) |
| `description` | `str` | McMaster's wording for the line | may be `''` |
| `packs` | `Optional[int]` | quantity ordered, as the page states it | `> 0` or `None` |
| `pack_size` | `Optional[int]` | units in a pack, where the page says | `None` means "not pack-priced"; treated as 1 |
| `pack_price` | `Optional[Decimal]` | price as the page states it | string in JSON, `Decimal` here — never a float, in transit or at rest (Constitution III) |
| `line_number` | `Optional[int]` | 1-based position within the order as read | identity, per FR-014 |

Derived, and the whole of FR-020:

| Property | Definition |
|---|---|
| `quantity` | `packs × (pack_size or 1)` — units, not packs |
| `unit_price` | `price_to_cents(pack_price / (pack_size or 1))` |
| `price_rounds` | whether that division lost precision to the cent, so the review can say so |
| `form_key` | `str(line_number)`, falling back to `part_number` — what a per-line form control is named by |

`form_key` is not decoration. Keying a form by part number gave two lines of one order a single
shared `include[]` / `description[]` (024, PR #116 review); the same trap exists here and the
same answer closes it.

**A line with no part number is kept, not dropped.** It is capturable on its description alone
or excludable (FR-019). A line with *nothing* — no part number and no description — is dropped,
because there is nothing for the operator to decide about.

### `McMasterOrder`

| Field | Type | Rules |
|---|---|---|
| `order_number` | `str` | required — no order number, no order |
| `order_date` | `Optional[datetime]` | parsed leniently; `None` is ordinary |
| `source_url` | `str` | the order page it was read from |
| `lines` | `tuple[McMasterOrderLine, ...]` | may be empty |
| `lines_read` | `int` | how many line elements the agent saw, including any it could not use — FR-004 |

`from_payload` returns `None` for: a non-object, a version it does not recognize, or a body
naming no order number. `None` is what makes a stale cached agent harmless rather than a 500,
and it is what FR-038 renders as "this page yielded no order" rather than as an empty review.

`lines_read` is separate from `len(lines)` **on purpose**. Equal, it says nothing; different, it
is the difference between "your order has three lines" and "I could only read three of your
fourteen lines", and FR-004 exists because those must not look the same.

### The product-page payload: `ListingCapture`, unchanged

A McMaster product page fills the type that already exists — `source_url`, `vendor_item_id`
(the McMaster part number), `listing_title`, `price`, `description_text`, `specifications`,
`images`. Two additions to the *transport*, neither of which changes the type:

* `vendor` is submitted as its own form field, declared by the agent (research.md §4).
  `product_capture()` already prefers a submitted vendor over a derived one
  (`app/product/routes.py:468`).
* `pack_price` and `pack_size` populate the confirmation form's existing pack fields, which
  feature 017 put there. They are UI-only and recorded nowhere
  (`app/templates/product/capture.html:212`); what is stored is a unit price.

`brand` stays empty for most McMaster goods, and that is correct rather than missing: McMaster
sells to its own specification and mostly names no manufacturer.

---

## 3. Display types — reused, not rewritten

`OrderLineState` and `ReviewedLine` (`app/models.py:1160`, `:1173`) are already plain frozen
value objects with string annotations, and they already carry everything a McMaster review
needs to render. They are reused as-is.

| State | Means, for McMaster |
|---|---|
| `CAPTURED` | a purchase already exists for this order number and this line number (FR-015) |
| `CONFLICT` | this part number names a product whose recorded identity contradicts the line — the operator must choose (FR-018) |
| `MATCHED` | a product carries this McMaster part number; the purchase attaches to it (FR-007) |
| `NEW` | nothing matches; confirming creates a product (FR-008) |

Tested in that order, `CAPTURED` first: a line already recorded is not a line to decide anything
else about.

`ReviewedLine.part` stays `None` for every McMaster line. For DigiKey it holds the separate part
lookup; McMaster has no such lookup because **the page is the detail**. `is_enriched` is
therefore always `False` here and the McMaster review does not render it.

---

## 4. What a confirmed capture writes

Per included line, in one transaction, nothing before the operator confirms (FR-005):

**Product** — created only for a `NEW` line, from the operator's authored description
(pre-filled with McMaster's, refused over `MAX_DESCRIPTION_LENGTH` = 255 at the point of entry
rather than truncated).

**Product identifiers** (FR-012):

| Kind | Value | Vendor scope | When |
|---|---|---|---|
| `DISTRIBUTOR` | the McMaster part number | `McMaster-Carr` | always, where the line has one |
| `MPN` | the manufacturer part number | — | **only** where the page actually stated one |

This is the inverse of the DigiKey case, where the MPN is the primary name. Writing an `MPN`
McMaster never stated would be inventing an identifier, and identifiers are unique — an invented
one collides with a real one later.

**Purchase** — one per included line, `received_date` NULL (FR-011), carrying the vendor, the
order number, the line number, the units, the unit price, the order date and the page address.

An **excluded** line writes nothing at all, and its exclusion is not recorded — an excluded line
"becomes nothing" (FR-009), which is also why scanning its bag later falls through to ordinary
behaviour.

---

## 5. Re-capture: what reconciles, and against what

A re-capture reads the page again and pairs each line to the purchases already recorded for that
order number. Pairing is **by `order_line_number`, never by position and never by part number** —
the rule `_recorded_digikey_lines` learned the hard way (`app/catalog_service.py:1939`).

| Situation | Outcome |
|---|---|
| Line already captured, unchanged | shown as captured; nothing written (FR-015, SC-003) |
| Line already captured, quantity or price differs | change shown against what is recorded; applied **only** on the operator's say-so (FR-017) |
| Line not captured | offered normally |
| A recorded purchase no line claims | reported, **never deleted** (FR-016) |

Change detection compares **both sides rounded**. The recorded price has been through a
`Numeric(10, 2)` column and the freshly-read one has not; comparing raw against stored made
"Update it?" reappear on every review of a sub-cent line with no way to clear it (PR #116
review). The same trap is reachable here through pack division.

---

## 6. Receiving

**Finding the line**: outstanding McMaster purchases whose `vendor_item_id` equals the scanned
value. Both columns are indexed already (`app/database.py:1049`, `:1086`).

| Matches | Outcome |
|---|---|
| exactly one | the receipt for that purchase, quantity pre-filled and editable (FR-032) |
| more than one | the chooser, one row per candidate with its order (FR-032a) — the catalog does not pick |
| none | falls through to today's scan behaviour, unchanged (FR-032b) |

Unlike DigiKey's `find_receivable`, this filters to **outstanding only**. DigiKey's includes
received rows deliberately, so it can tell "already received" apart from "no such line" for a
label that names an order. A bare part number names no order, so there is no such distinction to
draw and an already-received part is simply a part the catalog holds.

**Receiving itself is `receive_purchase`, untouched** (FR-029): the purchase is marked received,
a counted product's quantity rises, and a manual low/out flag is cleared.

**All-or-nothing per line.** `received_date IS NULL` *is* the outstanding state — there is no
status column that could disagree with it, and no partial state is added.
