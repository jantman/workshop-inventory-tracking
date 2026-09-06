# Phase 0 Research: A Vendor's Category Is Not the Shop's Category

Three questions were open when planning began. All three are resolved.

## 1. How many places carry a vendor category toward a product?

**Decision: four, not the one the issue names.** The issue points at
`_create_digikey_product`. A search for every reader of a part's `category_path` found three more.

| # | Site | What it does today | Disposition |
|---|---|---|---|
| 1 | `CatalogService._create_digikey_product` (`app/catalog_service.py`) | Passes `part.category_path` into the new `Product` during an order capture | Remove the argument; the column is nullable and defaults to unset |
| 2 | `CatalogService._enrich_digikey_product` | Fills a **blank** `category_path` from the part detail, for a product an order line matched | Remove the category clause; keep the manufacturer and specification clauses untouched |
| 3 | `app/templates/product/digikey_part_review.html` | Posts `part.category_path` to `product_new` as a **hidden** input | Remove the hidden input; add a visible, empty Category field (FR-004) |
| 4 | `product_new`'s scan-prefill branch (`app/product/routes.py`) | Copies `part.category_path` into the `prefill` mapping that fills the Add Product form after a bag scan | Drop the one key; every other pre-loaded value stays |

**Rationale**: the defect is not "one line pre-fills a field", it is "a vendor's vocabulary can
reach a field whose values are the shop's taxonomy". Fixing one door and leaving three is the
failure mode the issue itself describes — a value nobody looks at, paid for in the tree.

Site 4 deserves its own note because it is the *least* wrong of the four: the value lands in the
visible Category input, labelled, editable, with the shop's own suggestions in its datalist. The
operator can see it. But a pre-loaded value that is simply accepted is exactly how a vendor name
becomes a branch, and FR-005 draws the line at "presented as, or pre-loaded into, a field that will
be recorded" rather than at "hidden". So it goes too.

**Alternatives considered**:
- *Fix only the order-capture site the issue names.* Rejected: sites 3 and 4 write the same wrong
  value into the same field, and site 3 does it invisibly.
- *Leave site 4, on the grounds that it is visible and editable.* Rejected on the rule above, and
  because it would leave the two DigiKey capture pages disagreeing with each other again — which is
  the exact inconsistency (018 FR-013 applied to one path and not another) that produced this bug.

## 2. Does removing the hidden field strand the single-part capture page?

**Decision: yes, so a visible Category field replaces it (spec FR-004).**

The single-part capture page (`digikey_part_review.html`) offers Description, Storage Location and
Sub-Location as visible inputs, and carries Category only as a hidden pre-filled value. Delete the
hidden input alone and the page becomes the only capture surface in the application that can state
where a thing is stored but not what it is — while `product/capture.html` and the add/edit forms
all offer Category, Location and Sub-Location together through the shared
`product/_classification_fields.html` partial (018 FR-007, FR-008).

**Implementation note**: the shared partial renders all three fields, and this page already renders
its own Location and Sub-Location. Including the partial would duplicate those two. The Category
input is therefore written inline on this page, matching the partial's contract — `id="category_path"`,
`name="category_path"`, `maxlength="512"`, `list="category-suggestions"` and a sibling
`<datalist id="category-suggestions">` — because `catalog-suggestions.js` binds that id, and a
renamed id silently switches the shop's own category suggestions off.

**Alternatives considered**:
- *Include `_classification_fields.html` and delete the page's own Location/Sub-Location markup.*
  Tempting, and rejected for this change: the page's two location inputs are plain (no
  autocomplete dropdown siblings), so adopting the partial changes three fields' behavior to fix
  one. It is a reasonable follow-up, not part of a bug fix.
- *No Category field at all; file it from the product's edit page afterwards.* Rejected — it makes
  the fix cost the operator a step it did not need to.

## 3. Does anything downstream require a captured product to have a category?

**Decision: no. A blank category is an ordinary, fully-supported state.**

Evidence:
- `Product.category_path` is `String(512), nullable=True` (`app/database.py`). Blank is the column's
  own default state.
- `tests/unit/test_product_model.py` asserts a freshly-made product's `category_path` is `None`.
- Every reader tolerates it: `product/detail.html` wraps the row in `{% if product.category_path %}`,
  `product/search.html` renders `or ''`, and the taxonomy helpers build the tree from the distinct
  values *in use*, so a product with none simply is not in it.
- Every other capture path already produces uncategorized products: the Amazon listing capture by
  the explicit rule of 018 FR-013, the Amazon and McMaster order captures because those vendors
  have no part lookup to read a category from. The DigiKey order capture is the outlier being
  brought into line, not the norm being broken.

**Consequence for the spec's FR-006**: nothing needs to be added to keep a blank category
acceptable. The requirement is a prohibition on introducing a check, not a feature to build.

## Tests that currently assert the defect

Three assertions encode the behavior being removed and must be rewritten, not deleted — the
assertion is where the decision is recorded, so it records the new one:

| Test | Asserts today | Becomes |
|---|---|---|
| `tests/unit/test_digikey_capture.py::TestEnrichment::test_enrichment_fills_the_product_the_order_could_not` | `product.category_path is not None` | the manufacturer and specifications are filled **and** the category is not |
| `tests/unit/test_order_enrichment.py::TestAMatchedProductIsEnriched::test_a_blank_category_is_filled` | a blank category is filled by enrichment | a blank category is **left** blank by enrichment (rename the test to match) |
| `tests/unit/test_order_enrichment.py` module docstring | lists "no category" among the gaps DigiKey fills | lists the two gaps it still fills, and says why the category is not one |

`tests/unit/test_digikey_client.py`'s two assertions on `part.category_path` are **not** touched:
they test that the client reads DigiKey's payload correctly, which it must keep doing — the value
is still displayed to the operator (FR-005). Reading it and recording it are different things, and
that distinction is the whole feature.

## Documentation that promises the removed behavior

`docs/user-manual.md` states in three places that a DigiKey capture fills in the category: the
order-capture section (~line 1450), the single-part section (~line 1504) and the backfill section
(~line 1726). `app/templates/product/order_review.html`'s unenriched-lines warning implies it in a
fourth. All four are corrected; a manual that promises a category the capture no longer records is
worse than one that never mentioned it.
