# Contract: `purchases.pack_size` and `purchases.pack_price`

What the two columns mean, who may write them, and what may be concluded from them.

---

## 1. Meaning

> **They record what the vendor charged. They are not a derivation of this row.**

| Column | Holds |
|--------|-------|
| `pack_size` | How many individual items came in **one** of what the vendor sold |
| `pack_price` | What **one pack** cost, as the vendor charged it |

The purchase's own `quantity` and `unit_price` are unchanged in meaning: individual items, and
the price of one item. The two pairs answer different questions.

**They may legitimately disagree.** A pack of 100 ordered and 90 received is a true row: the
vendor charged for 100, the shelf gained 90. Nothing may treat that as an inconsistency to repair
(research R7).

This is what FR-033 binds in practice: **every page displaying these fields must label them as the
vendor's line, never as the arithmetic that produced the catalog's numbers.** A page that renders
them as "100 × $0.13 = this purchase" is wrong even when the numbers happen to agree.

---

## 2. Invariants

| # | Invariant |
|---|-----------|
| P1 | Both NULL, or both set. Never one alone — `pack_size` alone cannot restate the vendor's line, `pack_price` alone states nothing |
| P2 | **`pack_size` is never 1.** A pack of one is no pack; it stores NULL (FR-031). "Nothing was stated" and "a pack of one was stated" must stay distinguishable |
| P3 | `pack_size >= 2` when set |
| P4 | `pack_price` is a `Decimal` that has been through `_validate_price` — never a `float`, never a raw string handed to the column |
| P5 | A purchase recorded by hand, or before this feature, holds NULL for both, and no page may render it as a pack of 1 (FR-031, FR-032) |
| P6 | Neither column is ever inferred, backfilled or recomputed from `quantity` and `unit_price` |

---

## 3. Writers

| Writer | Source | Notes |
|--------|--------|-------|
| `_amazon_line_fields` | the pack size in force for the line; the line's stated per-listing price | Only when the pack size exceeds 1 |
| `_mcmaster_line_fields` | `line.pack_size`, `line.pack_price`, straight off the line | The page already reads them; today they are discarded. NULL for "Each" and for **"Pairs"**, where McMaster states no count — inventing 2 there would be inventing data |
| `capture_order` (single listing) | the confirmation form's `pack_size` and `pack_price` | The route currently drops both |
| `_apply_order_change` | the same as the matching `line_fields` | A re-capture that updated the quantity and left a stale pack size is exactly the contradiction §1 forbids |

**No other writer.** In particular the receive screen (`purchase_receive`) amends `quantity`,
`unit_price`, `notes` and the product description, and **leaves both pack columns alone** — what
arrived is allowed to differ from what was ordered.

DigiKey writes neither (FR-040).

---

## 4. Readers

| Reader | Shows |
|--------|-------|
| A captured order's page | Both views per line: the vendor's — *N packs of S at $P* — beside the catalog's — *Q items at $U* (FR-034) |
| The receive screen | The pack, where the purchase carries one, as context for what arrived |

### Derived for display, never stored

| Value | Expression | When omitted |
|-------|-----------|--------------|
| Packs ordered | `quantity / pack_size` | When it does not divide evenly — the operator overrode the quantity, and no packs figure is honest |
| Line total | `packs × pack_price` | Whenever packs is omitted |

---

## 5. Migration

One Alembic revision, `down_revision = 'd0817b3ea45c'`.

- `upgrade`: add `pack_size` `Integer NULL`, `pack_price` `Numeric(10, 2) NULL`. No data migration
  (FR-032).
- `downgrade`: drop both. No dependency ordering to get wrong — no index, no foreign key.
- **The ORM model in `app/database.py` and the revision must match exactly.** The unit suite
  builds its schema with `create_all` and never runs Alembic, so any drift passes `nox -s tests`
  and fails on MariaDB. This trap is already documented on `supplier_order_reference`.
