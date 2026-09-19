# Phase 1 Data Model: Packs Recorded as Units, and What a Pack Was Kept

Two persisted columns, one new mixin, and additions to two existing dataclasses. Nothing is
removed and nothing existing changes type.

---

## Persisted: `purchases` (`app/database.py`, `class Purchase`)

| Column | Type | Null | Index | Meaning |
|--------|------|------|-------|---------|
| `pack_size` | `Integer` | yes | no | How many individual items came in **one** of what the vendor sold. NULL when the vendor sold items rather than packs |
| `pack_price` | `Numeric(10, 2)` | yes | no | What **one pack** cost, as the vendor charged it |

**Both are a record of the vendor's line, never a derivation of this row** (research R7). The
purchase's own `quantity` and `unit_price` stay what they have always been: individual items, and
the price of one. The two pairs answer different questions and may legitimately disagree — a pack
of 100 ordered and 90 received is a true row.

### Rules

- **NULL, never 1.** A pack size of 1 is "no pack was stated" and stores NULL for both columns
  (FR-031). Storing 1 would make every purchase in the catalog claim to be a pack.
- **Written together or not at all.** `pack_size` without `pack_price` cannot restate the
  vendor's line (FR-029), and `pack_price` without `pack_size` states nothing.
- **`pack_price` goes through `_validate_price`**, like every other price on this path — the
  `Numeric(10, 2)` column rounds silently on write and the value stored must be one this code
  chose (Constitution III).
- **Never backfilled.** Existing rows keep NULL for both (FR-032). Nullable is what makes the
  upgrade rewrite nothing.
- **Not indexed.** Nothing queries by them; they are read only when a purchase is displayed.
- **The ORM model and the Alembic revision must match exactly** — the unit suite builds its
  schema with `create_all` and never runs Alembic, so drift passes `nox -s tests` and fails on
  MariaDB (research R9).

### Derived, not stored

**Packs ordered** = `quantity / pack_size`, exact whenever the operator did not override the
quantity. Rendered by the order page when it divides evenly and omitted when it does not, rather
than stored as a third column (research R5).

**Line total** = `packs × pack_price`, which is what reconciles against the vendor's invoice
(SC-007).

---

## Domain: `PackLine` mixin (`app/models.py`, new)

The four properties `McMasterOrderLine` already has, lifted so `AmazonOrderLine` can share them
rather than carry a second copy that must never drift (research R1).

**Requires of its host**: `packs: Optional[int]`, `pack_size: Optional[int]`,
`pack_price: Optional[Decimal]`.

| Member | Type | Meaning |
|--------|------|---------|
| `units_per_pack` | `int` | `pack_size or 1`. One unit is one unit when no pack was stated |
| `quantity` | `Optional[int]` | `packs × units_per_pack`. **None when `packs` is None** — a pack size must never invent a quantity the vendor did not state (FR-009) |
| `exact_unit_price` | `Optional[Decimal]` | `pack_price / units_per_pack`, unrounded. Nothing stores this; it exists so `price_rounds` has something to compare against |
| `unit_price` | `Optional[Decimal]` | `price_to_cents(exact_unit_price)` — rounded by this application, not by the column |
| `price_rounds` | `bool` | Whether the division lost precision to the cent. Drives the review's warning (FR-008) |

`McMasterOrderLine` keeps its existing field declarations and drops the four property bodies.
Its observable behaviour is unchanged (FR-039).

---

## Domain: `AmazonOrderLine` (`app/models.py`, changed)

| Field | Before | After |
|-------|--------|-------|
| `quantity` | stored field, `Optional[int]`, what the page stated | **removed as a field**; becomes the mixin's property |
| `unit_price` | stored field, `Optional[Decimal]` | **removed as a field**; becomes the mixin's property |
| `packs` | — | `Optional[int]`. What the order page stated as the quantity — how many *of the listing* |
| `pack_size` | — | `Optional[int]`. How many items are in one. None means none was stated or suggested |
| `pack_price` | — | `Optional[Decimal]`. What the page stated as the unit price — the price of one *of the listing* |

`from_payload` reads the payload's `quantity` into `packs` and `unit_price` into `pack_price`.
**The payload format does not change**, so an existing bookmarklet keeps working and a payload
captured before this feature reads identically.

Two existing behaviours are preserved exactly:

- **An absent quantity is 1, not None.** Amazon renders the quantity component empty for a
  quantity of one, so an empty read is the ordinary case rather than a failure. That now applies
  to `packs`.
- **`missing_fields` never reports a missing quantity**, for the same reason; it reports a missing
  price when `pack_price` is None.

### Suggestion (new, on the line)

| Member | Type | Meaning |
|--------|------|---------|
| `suggested_pack_size` | `Optional[int]` | The listing's structured `pack_size` if it has one, else a count parsed from the title, else None (research R4) |
| `pack_size_is_suggested` | `bool` | Whether the pack size in force came from the suggestion rather than the operator (FR-020) |

---

## Domain: `pack_size_from_title(text)` (`app/models.py`, new)

Pure function, no I/O, `str -> Optional[int]`. Recognises a digit run **adjacent to a pack word**:
`Pack(s) of N`, `N Pack` / `N-Pack` / `N Pk`, `N Pcs` / `N pieces` / `N pc` / `N ct` / `N count`,
`Set of N` / `Box of N` / `Bag of N`.

- Never fires on a bare number, so `M3 x 12mm`, `12V` and `1/4-20` yield None (FR-022).
- **Two different counts in one title yield None** — there is no basis for choosing.
- Returns None for a count of 0 or 1: neither is a pack.

---

## Domain: `ListingCapture` (`app/models.py`, changed)

| Member | Change |
|--------|--------|
| `pack_price`, `pack_size` | Unchanged as fields. **The docstring's claim that "neither is recorded anywhere" becomes false** and must be corrected (research R10) |
| `unit_price_from_pack` | Unchanged |
| `quantity_from_pack` | **New.** `pack_size` as a string, or None. Supplies the confirmation form's initial derived Quantity for one pack, the way `unit_price_from_pack` supplies the initial Unit Price — so a browser with no JavaScript still renders the right number (research R8) |

---

## Form contracts

### Order review — one new field per line

| Name | Meaning |
|------|---------|
| `pack_size[<form_key>]` | Items in one of what the vendor sold. Default 1, or the suggestion |

Read in `_order_decisions` (`app/product/routes.py:1536`) beside the fields it already reads.
**Keyed by `form_key`, never the item id** — an order can carry the same ASIN twice (FR-004).

`quantity[<form_key>]` and `unit_price[<form_key>]` keep their existing meaning for every vendor:
*what gets recorded*. Override detection (research R3, `contracts/pack-conversion.md`) decides
whether a submitted value follows the pack size or wins over it.

### Capture confirmation page — one new field

| Name | Meaning |
|------|---------|
| `packs` | How many packs were bought. Default 1 |

`pack_size` and `pack_price` already exist on this form and are currently ignored by the route;
both are now forwarded to `capture_order` and stored. `quantity` keeps its meaning — what gets
recorded, in items — and becomes derived rather than blank.

---

## What is deliberately **not** in the model

- **No `packs` column** on `purchases` — derivable (research R5).
- **No pack fields on `Product`** — a pack is a property of one purchase. The same screw is bought
  loose once and in a bag of 100 the next time.
- **No change to the capture agent's payload** — the suggestion is parsed server-side from a title
  the payload already carries (research R4).
- **No change to `DigiKeyOrderLine`** or any DigiKey path (FR-040).
- **No pack fields on `PurchaseDeletion`** — no requirement reads them, and it exists to say what
  was removed.
