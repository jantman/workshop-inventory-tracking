# Data Model: Pack Quantity on Record a Purchase

There are no schema changes.

## Purchase (existing)

| Field | Meaning | Written by this feature |
|---|---|---|
| `quantity` | Items brought in | The typed value, or packs × pack size when it is empty and the pack size is 2 or more |
| `unit_price` | Price of one item (`Decimal`, cents) | The typed value, or pack price ÷ pack size rounded half-up when it is empty |
| `pack_size` | The vendor's units per pack | Pack size if it is 2 or more **and** a pack price is given, otherwise NULL |
| `pack_price` | What one pack cost, as charged | Pack price under the same condition, otherwise NULL |

Invariants: `_pack_fields` enforces "both or neither, and never a pack of 1"
(046 contract P1–P4).

## Form-only values (not stored)

- **Packs Bought** (`packs`): a whole number of 1 or more. Blank means 1. It is used only to
  derive Quantity.
