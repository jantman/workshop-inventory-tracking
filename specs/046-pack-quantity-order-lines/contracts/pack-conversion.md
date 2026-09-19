# Contract: The Pack Conversion

The arithmetic, and the rule that decides whether a submitted number follows the pack size or
overrides it. Binding on both pages that offer a pack size — the Amazon order review and the
single-listing confirmation page — and on the server in both cases.

---

## 1. The arithmetic

Given what the vendor stated and a pack size:

```
units_per_pack = pack_size or 1

quantity   = packs x units_per_pack                        # None when packs is None
unit_price = round_half_up_to_cents(pack_price / units_per_pack)   # None when pack_price is None
```

### Rules

| # | Rule |
|---|------|
| C1 | `Decimal` throughout on the server; `BigInt` digit-string arithmetic in the browser. No `float`, no `parseFloat`, no `toFixed`, at any point including in transit (Constitution III) |
| C2 | The rounding is `ROUND_HALF_UP` to two places, performed by `price_to_cents` so the stored value is one this code chose rather than one `Numeric(10, 2)` imposed silently |
| C3 | A pack size **never creates a value the vendor did not state**. `packs is None` yields `quantity is None`; `pack_price is None` yields `unit_price is None`. The line stays marked unread for that field (FR-009) |
| C4 | `units_per_pack` of 1 is the identity: same quantity, same price, byte for byte, as before this feature (FR-002, FR-026, SC-005) |
| C5 | A pack size that is not a whole number of at least 1 is **refused**, naming the line. It is never coerced to 1 (FR-011) |
| C6 | Where `pack_price / units_per_pack` is inexact, the page says so on that line before confirmation (FR-008) |

### Worked cases

| packs | pack_size | pack_price | quantity | unit_price | rounds? |
|------:|----------:|-----------:|---------:|-----------:|:-------:|
| 1 | — | 13.23 | 1 | 13.23 | no |
| 1 | 100 | 13.23 | 100 | 0.13 | yes |
| 2 | 100 | 13.23 | 200 | 0.13 | yes |
| 2 | 100 | 6.66 | 200 | 0.07 | yes |
| 1 | 10000 | 4.99 | 10000 | 0.00 | yes |
| 1 | 3 | 17.99 | 3 | 6.00 | yes |
| None | 100 | 13.23 | **None** | 0.13 | yes |
| 1 | 100 | None | 100 | **None** | — |

The `0.00` row is a real outcome and is stated, not refused (spec, *Edge Cases*).

---

## 2. Override detection

The review's `quantity[<key>]` and `unit_price[<key>]` mean *what gets recorded*, for every
vendor. This rule decides whether a submitted one follows the pack size or wins.

```
rendered_pack     = suggested_pack_size(line)          # pure function of the payload
rendered_quantity = packs x rendered_pack
rendered_price    = round_half_up_to_cents(pack_price / rendered_pack)

submitted_pack    = pack_size[<key>] if present, else rendered_pack

quantity   = submitted_quantity if submitted_quantity != rendered_quantity
             else packs x submitted_pack

unit_price = submitted_price if submitted_price != rendered_price
             else round_half_up_to_cents(pack_price / submitted_pack)
```

**In words: a value the operator did not change follows the pack size; a value they changed wins.**

### Why it is correct in both browsers

| | With JavaScript | Without |
|---|---|---|
| Operator sets pack size, types nothing | JS rewrites the field to `packs x submitted_pack`; that differs from `rendered_quantity`, so branch 1 returns it — the same number branch 2 would compute | Field still holds `rendered_quantity`, so branch 2 computes `packs x submitted_pack` |
| Operator sets pack size, then types a quantity | Their value differs from `rendered_quantity`; branch 1 returns it | Same |
| Operator touches nothing | `submitted == rendered`, `submitted_pack == rendered_pack`; branch 2 returns the identical number | Same |

Both columns reach the same answer in every row. That is the property that makes the JavaScript an
ergonomic aid rather than a load-bearing part of the write path.

### The one residual case

The operator changes the pack size **and** separately types the rendered value back by hand. Branch
2 fires and records the converted number. No data is lost, and the conversion marking (§4) states
plainly what was recorded.

### Preconditions

- `rendered_pack` must be **pure** — a function of the payload alone, with no clock, no request
  state and no database read — or the server cannot reconstruct what it drew. This is why the
  suggestion is a title parse rather than anything fetched (research R4).
- The payload must ride the form. It already does, in `#order-payload`, for every
  payload-carrying vendor.

---

## 3. Precedence of the pack size

For each line, first of:

1. What the operator entered on this submission
2. `ListingCapture.pack_size`, where the line's listing was read and states one (FR-018)
3. `pack_size_from_title(line.title)` (FR-019)
4. `1`

A value the operator set is **never** replaced by a suggestion on a re-render (FR-021), which
falls out of 1 outranking 2 and 3 on every submission.

---

## 4. What the review must show

| Requirement | Condition |
|---|---|
| FR-014 | A line with `units_per_pack > 1` is marked as converted; one at 1 is not |
| FR-015 | A converted line states its arithmetic: `packs × pack_size`, `pack_price ÷ pack_size` |
| FR-016 | The vendor's own numbers stay visible beside the catalog's |
| FR-017 | The banner's *"as Amazon stated them"* is not asserted of a converted line |
| FR-020 | A pack size in force from a suggestion is marked as read from the listing, distinguishably from one the operator entered, until it is confirmed |
| FR-008 | An inexact division says so on that line |

---

## 5. Browser behaviour

Both pages reuse `window.unitPriceFromPack(paid, packSize)` from `pack-unit-price.js` unchanged.
Two rules carry over verbatim from that file, and both are load-bearing:

- **Write a derived field only once the operator has typed in a pack field — never on load.** A
  re-render after a refusal may carry a value the operator typed over the derived one, and writing
  on load discards it with no trace. The server supplies the initial derived value instead.
- **Nothing listens on the derived field itself.** Typing in Quantity or Unit Price is overruling
  the derivation; a derivation that recomputed over the top of it would be useless.

The inexactness note is shown on load as well as on edit, so a rounded price still explains itself
on the far side of a question.

Each script is inert on any page lacking its hooks.
