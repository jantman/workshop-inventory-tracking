# Phase 1 Data Model: Document Structure

This feature has no database entities. Its "data model" is the structure of
`docs/user-manual.md` — the section inventory, the old→new heading map, and the anchor
consequences. This is the artifact FR-002 through FR-007 are checked against.

---

## Current structure

`docs/user-manual.md`, 1,817 lines. **Fourteen** `##` sections; the table of contents lists
**thirteen** — `## Quick Reference Card` (line 1798) is already missing from it.

| Line | `##` Section | Half |
|---|---|---|
| 19 | Getting Started | orientation |
| 41 | Overview | orientation |
| 52 | Adding New Inventory | inventory |
| 173 | Label Printing | inventory |
| 283 | Managing Existing Inventory | inventory |
| 475 | **Product Catalogue** | **catalog — all of it** |
| 837 | Advanced Search | inventory |
| 915 | Batch Operations | inventory |
| 1025 | Data Export | both |
| 1300 | REST API | both |
| 1681 | Help and Utilities | both |
| 1702 | Tips and Best Practices | both |
| 1734 | Troubleshooting | both |
| 1798 | Quick Reference Card *(absent from TOC)* | both |

The catalog occupies lines 475–836 as one section with twelve `###` subsections, and it sits
*between* two inventory sections (`Managing Existing Inventory` and `Advanced Search`). That
placement is why the two halves cannot simply be re-levelled in place — the catalog block has
to move for the halves to be contiguous.

---

## Movement decision

**Move the catalog block down, past `## Batch Operations`.** Do not move the inventory
sections up.

Both produce two contiguous halves. Moving the catalog block relocates only catalog content
and leaves every inventory section in its existing relative order, which keeps the diff
inside the feature's stated scope (*"restructuring sections unrelated to the catalog is out
of scope"*). Moving `Advanced Search` and `Batch Operations` up would reorder inventory
material this feature was not asked to touch.

---

## Old → new heading map

Twelve `###` subsections become eleven `##` sections plus one retained `###`; the unheaded
intro prose at lines 477–485 becomes a twelfth `##`.

| Old | Old level | New | New level | Change |
|---|---|---|---|---|
| *(intro prose, 477–485)* | — | The Product Catalog | `##` | **new heading** over existing prose |
| Product Catalogue | `##` | *(dissolved)* | — | the container goes away |
| Adding a Product | `###` | Adding a Product | `##` | promoted |
| Identifiers | `###` | Product Identifiers | `##` | promoted + renamed |
| Scanning | `###` | Scanning Products | `##` | promoted + renamed |
| Distributor Labels | `###` | Distributor Labels | `###` | **stays nested**, now under *Scanning Products* |
| Recording Purchases | `###` | Recording Purchases | `##` | promoted |
| Capturing an Order When You Place It | `###` | Capturing an Order When You Place It | `##` | promoted |
| Labels | `###` | Printing Product Labels | `##` | promoted + renamed |
| Quantity, and Knowing What to Reorder | `###` | Stock Levels and Reordering | `##` | promoted + renamed |
| Attachments | `###` | Product Attachments | `##` | promoted + renamed |
| Finding Things | `###` | Finding Products | `##` | promoted + renamed + **split** |
| Fixing a Misspelled Category or Tag | `###` | Categories and Tags | `##` | promoted + renamed + **absorbs** |
| One Vocabulary for Locations and Vendors | `###` | Locations and Vendors: One Shared Vocabulary | `##` | promoted + renamed, placed as the bridge section |

### Three renames exist to remove a collision

- **Identifiers → Product Identifiers.** Bare *Identifiers* at `##` level reads as though it
  covers JA IDs too.
- **Labels → Printing Product Labels.** There is already a `## Label Printing` for inventory.
  Two top-level sections called *Labels* and *Label Printing* is unusable; each should
  cross-reference the other.
- **Attachments → Product Attachments.** Distinguishes it from `### Photo Management` under
  inventory.

### One split and one absorption

`### Finding Things` currently carries two distinct jobs: searching for a product, and
browsing the category/tag trees. The browse paragraphs (*Products → Categories*,
*Products → Tags*) move into **Categories and Tags**, joining the rename rules that were in
*Fixing a Misspelled Category or Tag*. Search, the code-as-address note and the filter list
stay in **Finding Products**.

This is prose movement, not deletion — FR-004 requires every fact to survive. The
Categories/Tags material and the rename tables are checked individually in
[quickstart.md](./quickstart.md).

---

## New table of contents

Grouped, and including `Quick Reference Card`, which the current TOC omits:

```
Getting oriented
  1. Getting Started
  2. Overview

Inventory — tracking physical stock
  3. Adding New Inventory
  4. Label Printing
  5. Managing Existing Inventory
  6. Advanced Search
  7. Batch Operations

Product Catalog — what you bought, what it cost, where it came from
  8. The Product Catalog
  9. Adding a Product
 10. Product Identifiers
 11. Scanning Products
 12. Recording Purchases
 13. Capturing an Order When You Place It
 14. Printing Product Labels
 15. Stock Levels and Reordering
 16. Product Attachments
 17. Finding Products
 18. Categories and Tags

Across both halves
 19. Locations and Vendors: One Shared Vocabulary
 20. Data Export
 21. REST API
 22. Help and Utilities
 23. Tips and Best Practices
 24. Troubleshooting
 25. Quick Reference Card
```

`## Overview` (FR-005) is rewritten to name the two halves and what distinguishes them,
carrying forward the framing currently buried at lines 477–485: *a product is a kind of thing
you buy; an inventory item is a specific piece of stock with a JA ID and a cutting history.*

---

## Anchor map

GitHub derives anchors by lowercasing, stripping punctuation and hyphenating spaces.

| Old anchor | New anchor | Referenced anywhere? |
|---|---|---|
| `#product-catalogue` | `#the-product-catalog` | **Yes** — `docs/user-manual.md:10`, the TOC entry (rewritten anyway) |
| `#identifiers` | `#product-identifiers` | No |
| `#scanning` | `#scanning-products` | No |
| `#labels` | `#printing-product-labels` | No |
| `#quantity-and-knowing-what-to-reorder` | `#stock-levels-and-reordering` | No |
| `#attachments` | `#product-attachments` | No |
| `#finding-things` | `#finding-products` | No |
| `#fixing-a-misspelled-category-or-tag` | `#categories-and-tags` | No |
| `#one-vocabulary-for-locations-and-vendors` | `#locations-and-vendors-one-shared-vocabulary` | No |
| `#adding-a-product` | unchanged | No |
| `#recording-purchases` | unchanged | No |
| `#capturing-an-order-when-you-place-it` | unchanged | No |
| `#distributor-labels` | unchanged | No |

Per [research.md](./research.md) Finding 1, exactly one in-repository reference to any
catalog anchor exists, and the rework rewrites that line. No other document, template or
comment links into a catalog heading.

**Not verifiable from inside the repository**: external bookmarks to `#product-catalogue`.
The spec accepts this (User Story 1, scenario 4 — the change must be *deliberate*, not
avoided). It is deliberate: the British spelling cannot survive FR-008 in a heading, so the
anchor has to change.

---

## Screenshot embed points

Six captures, one per section that has a screen worth showing. Full capture parameters are in
[contracts/screenshot-manifest.md](./contracts/screenshot-manifest.md).

| Section | Screenshot |
|---|---|
| The Product Catalog | `user-manual/product_detail.png` |
| Adding a Product | `user-manual/product_add_form.png` |
| Capturing an Order When You Place It | `user-manual/order_capture.png` |
| Stock Levels and Reordering | `user-manual/reorder_list.png` |
| Finding Products | `user-manual/product_search.png` |
| Categories and Tags | `user-manual/category_tree.png` |

`README.md` embeds `user-manual/product_search.png` — reuse, not a seventh capture. The
README already reuses `user-manual/add_item_form.png` the same way, so this follows the
established convention rather than adding a `readme/` file.
