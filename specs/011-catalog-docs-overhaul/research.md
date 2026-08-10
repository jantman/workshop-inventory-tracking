# Phase 0 Research: Product Catalog Documentation Overhaul

Five findings. Two correct figures carried in the spec, one removes a planned concern, one
identifies a trap, and one is pre-existing damage that FR-023 obliges this feature to repair.

---

## Finding 1 — Only one anchor reference exists in the repository

**Decision**: FR-006 and FR-007 (chase every reference to a changed catalog anchor) are
satisfied by updating a single line. No cross-document link hunt is needed.

**Measurement**:

```
$ grep -rn "#product-catalogue\|#product-catalog\|user-manual.md#" --exclude-dir=.git .
docs/user-manual.md:10:6. [Product Catalogue](#product-catalogue)
```

That is the manual's own table-of-contents entry. No other document, and no application
template, links into a catalog heading.

**Rationale**: The spec treated broken anchors as a live risk (Edge Case *"Anchors that break
silently"*, FR-007, SC-004) because a markdown link that stops resolving renders as plain
text and fails no build. The risk is real in general; measured, its blast radius here is one
line the rework rewrites anyway.

**Alternatives considered**: Adding a link-checking step to the plan. Rejected — building a
link checker to guard one link is exactly the speculative machinery Principle I prohibits.
The quickstart validates anchors by extraction and comparison in a few lines of shell.

**Consequence for the plan**: FR-007 costs nothing. SC-004 stays as a validation step, not a
work item.

---

## Finding 2 — FR-011 is ten renames, not eighty-five

**Decision**: **Keep FR-011** (the identifier rename). The spec marked it separable on the
basis of an 85-occurrence count and recommended it be reconsidered at planning. Measured
properly, the count is misleading: 85 is the number of *references*, and they are driven by
ten names.

**Measurement**:

| What | Count | Where |
|---|---|---|
| pytest fixtures named `catalogue` | **2** | `tests/unit/test_product_search.py:22`, `tests/unit/test_capture.py:435` |
| references to those two fixtures | ~89 | 71 in `test_product_search.py`, 20 in `test_capture.py` (includes the definitions) |
| test *function* names embedding the spelling | **8** | `test_scan_resolution.py:69`, `test_vocabulary.py:228`, `test_vocabulary.py:238`, `test_catalog_service.py:316`, `test_catalog_service.py:586`, `test_reorder_view.py:154`, `test_product_specifications.py:334`, `test_product_crud.py:90` |
| **distinct identifiers to rename** | **10** | |

**Rationale**: Renaming a pytest fixture is one edit at the definition and a
find-and-replace across its references; a missed reference is an immediate `fixture
'catalogue' not found` error, not a silent wrong answer. The eight function renames are
independent one-line edits. Ten mechanical edits with loud failure modes is a different
proposition from eighty-five hand-audited ones, and the spec's separability carve-out was
sized against the wrong number.

**Alternatives considered**: Dropping FR-011 as the spec suggested. Rejected on the corrected
measurement — leaving two fixtures named `catalogue` in a tree where every comment around
them says `catalog` reintroduces exactly the inconsistency option C was chosen to remove, and
it saves roughly twenty minutes.

**The one non-mechanical case**: `tests/unit/test_scan_resolution.py:69` reads
`test_an_uncatalogued_barcode_offers_creation_with_it_attached`. A blind
`catalogue` → `catalog` substitution yields `uncatalogd`. The American form is
**`uncataloged`** (single `g`, one `e`). This is the sole occurrence of the `uncatalogu-`
stem in the repository, so it is a one-site exception, not a class of them.

**The one silent failure mode**: a pytest function renamed to something no longer starting
with `test_` is simply not collected, and the suite still passes with less in it. FR-012
requires collection counts to match; the quickstart records the before/after command.

---

## Finding 3 — `tests/e2e/screenshot_config.yaml` is dead config

**Decision**: Do not extend it, do not delete it in this feature. Record it and defer.

**Measurement**: `tests/e2e/test_screenshot_generation.py` does not import
`screenshot_config_loader` and contains no reference to the YAML — every capture's filename,
viewport, wait selector and hide list is hardcoded in the test function. The only consumer of
the loader is `tests/unit/test_screenshot_infrastructure.py`, which tests the loader against
the config rather than testing that the config describes reality.

The config declares 20 screenshots. Nine do not exist on disk:

```
MISSING readme/add_item_form.png            MISSING user-manual/photo_copy_clipboard.png
MISSING user-manual/autocomplete_dropdown.png   MISSING user-manual/batch_selection.png
MISSING user-manual/label_preview.png       MISSING deployment-guide/migration_output.png
MISSING user-manual/bulk_label_printing.png MISSING development-guide/test_execution.png
MISSING user-manual/item_details_modal.png
```

Its `test:` keys also name functions that do not exist (`test_screenshot_bulk_creation` vs
the actual `test_screenshot_bulk_creation_preview`; `test_screenshot_edit_item` vs
`test_screenshot_edit_item_form`).

**Rationale**: Adding six catalog entries would make the file *look* like the manifest while
still driving nothing — the worst outcome, because the next person to add a screenshot would
edit the YAML and wonder why no PNG appeared.

**Alternatives considered**:

- *Extend the YAML.* Rejected: encodes a lie.
- *Make the suite actually read the YAML.* Rejected: that is building a config-driven
  screenshot framework, which Principle I forbids absent a measured need. Six more hardcoded
  test functions is the smaller, honest change.
- *Delete the YAML and its loader.* Constitutionally the right end state, and the one this
  research recommends as a follow-up — but it means deleting `screenshot_config_loader.py`
  and the unit tests covering it, which is a cleanup with its own justification. Burying it
  in a documentation diff would hide it.

**Consequence for the plan**: the screenshot manifest lives in
[contracts/screenshot-manifest.md](./contracts/screenshot-manifest.md) as a specification
artifact, and `GENERATION_GUIDE.md` remains the human-readable list of what exists. Recorded
as deferred work in plan.md's Complexity Tracking.

---

## Finding 4 — `VERIFICATION.md` is already stale, and FR-023 obliges fixing it

**Decision**: Regenerate it as part of this feature rather than inheriting the error.

**Measurement**: `docs/images/screenshots/VERIFICATION.md` is dated 2025-12-17 and reports
**8** screenshots totalling 1.25 MB. Twelve exist on disk. It is missing
`move_items.png`, `shorten_items.png`, `history_view.png` and `batch_operations_menu.png` —
all of which are embedded in the manual today.

`GENERATION_GUIDE.md` is correct at 12 (1 readme + 11 user-manual) and becomes 18 with this
feature (`product_search.png` is embedded in both README and manual but is one file).

**Rationale**: FR-023 requires the screenshot inventory documents to carry correct totals.
That requirement is not satisfiable by only adding the new rows to a document whose existing
rows are wrong.

**Alternatives considered**: Scope-limiting to "add the six new rows, leave the stale ones".
Rejected — it leaves a document that FR-023 says must be correct in a state where it is not,
and the fix is a regeneration, not an investigation.

---

## Finding 5 — The seeding path for catalog screenshots already exists

**Decision**: Seed with `live_server.add_test_products()` and `live_server.backdate_product()`.
Add one local helper in the test file for the purchase/identifier decoration that
`add_test_products` does not cover. Do not drive the Add Product form.

**Measurement**: `tests/e2e/test_server.py:193` already provides `add_test_products`, whose
docstring states the reason directly — *"Driving the Add Product form costs about three
seconds per product"*. It forwards kwargs to `CatalogService.create_product`, which accepts
`description`, `manufacturer`, `manufacturer_part_number`, `specifications`, `category_path`,
`location`, `sub_location`, `quantity`, `reorder_threshold`, `notes`, `identifiers` and
`tags` — everything the screenshots need except purchases.

`tests/e2e/test_server.py:217` provides `backdate_product`, which writes stock timestamp
columns directly. This matters for FR-020: the manual documents quantity ages
(*"counted 8 months ago"*) and flag ages (*"Flagged low 3 months ago"*), and a screenshot
taken against freshly-seeded data shows *"counted today"* for everything — picturing the
feature at exactly the value where it looks pointless.

Purchases come from `CatalogService.record_purchase` (`app/catalog_service.py:844`),
reachable the same way through `live_server.storage`, as `tests/e2e/test_reorder_view.py:230`
already does.

**Rationale**: This is the project's established pattern and matches CLAUDE.md's *"Seed data
directly"* rule. It also keeps the new tests fast enough not to lengthen
`nox -s screenshots_headless` meaningfully.

**Alternatives considered**: Driving the forms for realism. Rejected — three seconds per
product across six screenshots' worth of seed data, for pixels identical to what the service
path produces.

**Wait targets confirmed on each page** (Principle IV forbids timed waits; each is a stable
`id` read from the template):

| Page | Wait on |
|---|---|
| `/products` | `#product-table` |
| `/products/<id>` | `#stock-card`, `#identifier-list` |
| `/products/new` | `#product-form` |
| `/products/capture` | `#capture-form` |
| `/products/reorder` | `#reorder-table` |
| `/products/categories` | `#category-tree` |

Per CLAUDE.md pattern **C** (render-implies-completion), these are server-rendered pages
reached by `goto()`, so the element's presence is a complete signal. None of the six captures
involves a `fetch` boundary.
