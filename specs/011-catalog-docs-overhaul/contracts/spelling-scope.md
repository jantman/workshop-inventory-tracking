# Contract: Spelling Sweep Scope

The exact, measured boundary of FR-008 through FR-014. Measurements taken 2026-08-10 at
commit `0f9cdfd`.

## In scope

| Tree | Occurrences | What they are |
|---|---|---|
| `README.md` | 0 | — (the README never mentions the catalog at all; that is FR-015) |
| `CLAUDE.md` | 0 | — (gains the rule itself, FR-014) |
| `docs/user-manual.md` | 10 | headings and prose; rewritten wholesale by the rework anyway |
| `docs/spec-product-catalog.md` | 22 | prose |
| `docs/product-functionality-gap.md` | 5 | prose |
| `app/` | 35 | 29 comments/docstrings, 4 template comments, **2 user-visible strings** |
| `tests/` | 121 | docstrings, comments, and ~89 identifier references |
| **Total** | **193** | |

## Out of scope — deliberately

| Tree | Occurrences | Why |
|---|---|---|
| `specs/` | ~150 across 40 files | The frozen record of what was specified at the time. Rewriting it falsifies the record. |
| `migrations/versions/*.py` | 2 | Alembic revision docstrings describe migrations as they shipped. Same reason. |

`CLAUDE.md` must state these exclusions (FR-014), or the next contributor running the same
search "fixes" them.

---

## The two user-visible strings (FR-009)

Confirmed: **no test asserts on either**, so changing them breaks nothing that exists.

**`app/templates/product/reorder.html:15`**

> Everything flagged low by hand, and everything tracked that has reached its threshold.
> Nothing here is stored -- it is worked out from what the **catalogue** already knows, so it
> cannot fall out of step with the orders below.

**`app/templates/product/detail.html:29`**

> This scan matched a product already in the **catalogue**.

The other four `app/templates/` occurrences are Jinja comments (`{# ... #}`) in
`_layout.html`, `_rename_modal.html` and `detail.html` — never rendered, but in scope under
FR-010 as comments.

---

## The ten identifier renames (FR-011)

Two fixture names carry ~89 of the 121 `tests/` occurrences. Rename the definition, then
replace references within the same file.

### Fixtures

| File | Line | `catalogue` → `catalog` | References in file |
|---|---|---|---|
| `tests/unit/test_product_search.py` | 22 | `def catalogue(service)` | 71 |
| `tests/unit/test_capture.py` | 435 | `def catalogued(...)` → `def cataloged(...)` | 20 |

A missed reference fails immediately with `fixture 'catalogue' not found`. There is no silent
failure mode for this half.

### Test functions

| File | Line | New name |
|---|---|---|
| `tests/unit/test_scan_resolution.py` | 69 | `test_an_uncataloged_barcode_offers_creation_with_it_attached` |
| `tests/unit/test_vocabulary.py` | 228 | `test_catalog_only_location_is_offered` |
| `tests/unit/test_vocabulary.py` | 238 | `test_catalog_only_sub_location_is_offered` |
| `tests/unit/test_catalog_service.py` | 316 | `test_empty_catalog_is_an_empty_list` |
| `tests/unit/test_catalog_service.py` | 586 | `test_empty_catalog_is_an_empty_list` |
| `tests/e2e/test_reorder_view.py` | 154 | `test_none_on_hand_and_not_tracked_look_different_in_the_catalog_list` |
| `tests/e2e/test_product_specifications.py` | 334 | `test_following_a_link_from_the_detail_page_lands_on_the_filtered_catalog` |
| `tests/e2e/test_product_crud.py` | 90 | `test_product_appears_in_the_catalog_list` |

`test_catalog_service.py` has two functions with the same name in different classes, at 316
and 586. Both rename to the same new name; that is pre-existing and stays that way.

---

## The two traps

**1. `uncatalogued` is not a plain substitution.** One site:
`tests/unit/test_scan_resolution.py:69`. A blind `catalogue` → `catalog` yields
`uncatalogd`. The American form is **`uncataloged`** — one `g`, one `e`. Verify with
`grep -rn "uncatalogd\|uncatalogued" app/ tests/` returning nothing afterwards.

**2. A test renamed out of collection passes silently.** A pytest function whose name no
longer starts with `test_` is not collected, and the suite still goes green with less in it.
A passing run does not catch this. **Collection counts do** — capture them before and after:

```bash
nox -s tests -- --collect-only -q | tail -1
```

FR-012 requires the counts to match.

---

## Verification

```bash
# in scope: must return nothing
grep -ric "catalogue" README.md CLAUDE.md docs/ app/ tests/

# out of scope: must still return matches
grep -ric "catalogue" specs/ migrations/

# the uncataloged trap: must return nothing
grep -rn "uncatalogd\|uncatalogued" app/ tests/
```
