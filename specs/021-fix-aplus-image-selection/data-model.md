# Data Model: A+ Description Images

**Feature**: [spec.md](spec.md) | **Phase**: 1

## There is no schema change

No table is added, no column is added, widened or retyped, and **no Alembic revision ships with this
feature**. This document exists to say that explicitly, so that "where does the corrected image list
live" cannot be answered later by inventing a column.

Everything this feature changes is *which* rows get written to storage that already exists:

| Store | Table | What changes |
|---|---|---|
| Product attachments | `product_attachments` | **Membership only.** Fewer rows on a listing with a brand story (`B0FX4PDW6M`: 61 description images → 7), one fewer on any A+ listing with deferred-loading images (the grey placeholder stops being stored). No column changes. |
| Product | `products.description` | **Value only, on affected listings.** `B0FX4PDW6M` stores the product's own description in place of the vendor's company bio. Same column, same type, same length allowance — the column was widened to 16,777,215 bytes by `b1a0c0d10009` and the corrected text is *shorter* than what it replaces. |
| Product specifications | `product_specifications` | **Nothing.** Not read, not written, not reordered by this feature. |

## Entities in play

These are payload-level entities, not persisted ones. They live between extraction and confirmation
and are never stored in this shape.

### Description block

A container element that holds the vendor's written description. **Zero or more per listing** —
this is the change. Previously the reader assumed at most one and stopped at the first.

| Attribute | Meaning | Source |
|---|---|---|
| element | The container | `#productDescription`, `#aplus`, or `#aplus_feature_div` |
| has text | Whether the block carries prose after stripping | `textOf(block)` — unchanged |
| is cross-sell | Whether the block lies inside `#aplusBrandStory_feature_div` | **new** |

A listing may present the same block under two selectors (`#aplus` nested inside
`#aplus_feature_div` — the shape on `B09GM8FB3X` and `B0DMNXC4CD`) or two genuinely different
blocks under the same selector (two `id="aplus"` elements — the shape on `B0FX4PDW6M`). The reader
must be correct under both, which is why it gathers rather than chooses.

### Description image

A picture inside a description block, classified into exactly one of four states:

| State | Rule | Outcome | Status |
|---|---|---|---|
| Cross-sell | Inside `#aplusBrandStory_feature_div` | dropped | **new** |
| Placeholder | Address is a known deferred-loading placeholder | dropped | **new** |
| Furniture | Some establishable edge < 300 px | dropped | unchanged (007 FR-019) |
| Content | Everything else, including unestablishable dimensions | **kept** | unchanged |

Order matters: cross-sell and placeholder are tested *before* the size rule, because both categories
contain images that pass the size rule comfortably. That ordering is the whole feature.

### Image address

One string per image. Previously always `img.getAttribute('src')`; now `data-src` when present,
falling back to `src`, with placeholder addresses rejected. `withoutTransform()` then strips the
resolution token to yield the original — unchanged, and confirmed by the probe to handle the real
double-underscore token shape correctly (research §4).

## Invariants preserved

- **007 FR-018 — one stored image per owner, judged by content.** Untouched. Gathering across
  containers relies on it: the same image reachable from a nested `#aplus` and its
  `#aplus_feature_div` parent is deduplicated by the extractor's `seen` map by address, and by the
  server by content.
- **007 FR-019 — the 300-pixel rule and its keep-on-unknown clause.** Untouched, threshold
  unchanged. Spec FR-005 forbids moving it and nothing here needs it moved.
- **007 FR-004 / spec FR-007 — original resolution.** Untouched. The probe confirmed the stripped
  addresses resolve at 1464×600, the full published size.
- **007 FR-022 — the attachment ceiling stops cleanly.** Untouched, and this feature makes it
  dramatically harder to reach on the listing that came closest to it.
