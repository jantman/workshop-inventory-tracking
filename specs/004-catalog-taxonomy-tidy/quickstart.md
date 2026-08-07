# Quickstart: Validating "Keep the Catalogue Tidy"

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

How to run and verify this feature end to end. Scenarios map to the spec's user stories and success criteria; shapes and payloads live in [data-model.md](./data-model.md) and [contracts/](./contracts/) rather than being repeated here.

---

## Prerequisites

- Repository virtualenv at `venv/`. **Invoke its binaries by path** — `venv/bin/nox`, `venv/bin/python`.
- Python 3.13 on PATH for nox to build its environments (the system Python is newer):
  ```bash
  PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
  ```
- MariaDB reachable per `.env` for migrations and e2e.

No label printer is needed. This feature prints nothing.

---

## Setup

```bash
venv/bin/python manage.py db upgrade       # apply b1a0c0d10006 (products.sub_location)
venv/bin/python manage.py db downgrade -1  # exercise the downgrade
venv/bin/python manage.py db upgrade       # and come back
```

Exercising the downgrade is not optional — Constitution V requires it, and against **MariaDB**, not SQLite. A plain nullable column add is the least likely revision to break on the way down, but "least likely" is not the standard.

---

## Running the suites

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests   # unit, SQLite, network blocked
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e     # Playwright — 15-minute tool timeout
```

Never invoke `pytest` directly (Constitution IV). The `e2e` session needs a 15-minute timeout set on the tool running it, not on the command line; it runs in about 8m 15s warm, and the margin is for a cold start that pulls the MariaDB image and installs browsers.

**Screenshots are mandatory for this change.** It touches `app/templates/product/**` and `app/static/js/**`, so:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify
```

Commit the regenerated images with the change. CI blocks merge on stale screenshots. Note that `nox -s e2e` deliberately excludes screenshot tests, so an e2e run must leave the working tree clean — if it does not, something has gone wrong with the marker selection.

---

## Manual validation

Start the app and work through the four stories. Each is independently checkable; you do not need the others in place.

```bash
venv/bin/python app.py
```

### US1 — Rename a category

1. Create three products with categories `elctronics`, `elctronics/passives`, and `elctronics/passives/resistors`. Create a fourth with `elctronics-surplus`.
2. Go to **Products → Categories**. Rename `elctronics` to `electronics`.
3. Before confirming, check the dialog reports **3 products** affected — not 4. The fourth merely starts with the same letters.
4. Confirm. Expect: the three products now read `electronics`, `electronics/passives`, `electronics/passives/resistors`; `elctronics-surplus` is untouched; the old name is gone from the list and the new one carries the same counts.

**The refusals** — each should leave the tree exactly as it was, with a message naming the obstruction:

| Try | Expect |
|---|---|
| Rename `electronics` → `electronics/passives` | Refused: the target would sit inside the category being renamed. |
| Create a product under `hardware`, then rename `electronics` → `hardware` | Refused: that category already exists. |
| Rename `electronics` → `Electronics` | Refused as a no-op: normalization already treats them as one category. |
| Rename `electronics` → a 500-character name | Refused: a path beneath it would exceed the limit. Nothing is truncated. |

Verify after each refusal that **no** product changed — this is SC-005, and a partial rename is the failure that matters.

### US2 — Rename and merge a tag

1. Tag one product `surpluss` and another `surplus`. Tag a third with both.
2. Go to **Products → Tags**. The page lists both spellings with their counts — which is how you spot the problem in the first place.
3. Rename `surpluss` → `newname` (unused). Expect a plain rename: one tag, same products, old name gone.
4. Rename `newname` → `surplus` (in use). Expect the dialog to say it will **merge**, not rename.
5. Confirm. Expect one tag named `surplus`, carrying all three products, each exactly once. Filtering the catalogue by `surplus` returns all three.

Repeat step 4 in the other direction on fresh data — merging `a` into `b` and `b` into `a` must leave the same set of products on the surviving tag.

### US3 — Shared vocabulary

1. On a metal stock item, record location `M1-A` and vendor `McMaster-Carr`.
2. Add a product. Start typing `M1` in **Storage Location** — expect `M1-A` offered. Add a purchase and start typing `McM` in **Vendor** — expect `McMaster-Carr`.
3. Now the other direction: record location `Drawer 3` and vendor `Digi-Key` on a product/purchase.
4. Go to **Add Item** (metal stock). Type `Draw` in Location and `Digi` in Vendor — expect both offered, with no intervening step (SC-006).
5. Type something that matches nothing. Expect no dropdown, and expect the value to save anyway (FR-018, SC-008).
6. Record `amazon` on a purchase where metal stock already has `Amazon`. Expect **one** suggestion, not two.

Worth checking explicitly: a vendor recorded only on a *deactivated* metal stock item is still offered (FR-019).

### US4 — Product sub-location

1. Add a product with location `Drawer 3` and sub-location `Bin 7`. Both save; both appear on the product page.
2. Add a second product, type `Drawer 3` in Location, then focus Sub-Location — expect `Bin 7` offered first, because it is already recorded under that location.
3. Open a product created before this change. Expect its location unchanged and its sub-location empty — not an error (FR-023).

---

## What the automated tests cover

| Story | Unit | E2E |
|---|---|---|
| US1 — category rename | `test_category.py` (path arithmetic, boundary-is-the-separator, self-nesting), `test_catalog_service.py` (each refusal, subtree carry, rollback-leaves-nothing-changed) | `test_category_rename.py` |
| US2 — tag rename/merge | `test_catalog_service.py` (rename, merge, product carrying both, direction independence) | `test_tag_rename.py` |
| US3 — shared vocabulary | `test_vocabulary.py` (relocated ranking/escaping/dedup tests, plus the union cases) | `test_field_autocomplete.py` additions |
| US4 — sub-location | `test_catalog_service.py`, `test_product_model.py` | `test_product_crud.py` additions |

**A note for whoever writes the e2e tests.** The rename flows are form posts that navigate, so `expect()` on the resulting page is the whole wait — there is nothing async to race. The suggestion dropdown is the render-implies-completion case (CLAUDE.md pattern C): `field-autocomplete.js`'s `render()` appends items only after its `fetch` resolves, so `expect(dropdown.locator('.dropdown-item')).to_have_count(n)` is a complete signal. Do **not** assert "no suggestions" with `count()` against a region nothing has established first — that passes trivially against a dropdown that has not rendered yet. Use `expect(dropdown).not_to_be_visible()`, after a positive assertion has shown the component is live.

Seed products directly rather than driving the add form; the rename tests need several products across a subtree and the form costs about three seconds each. `tests/e2e/test_server.py` has `add_test_data` for inventory items and `add_material_taxonomy` for the taxonomy but nothing for products, so a matching `add_test_products` helper built on `CatalogService` is part of this feature's work and lands before the rename e2e tests.

---

## Definition of done

- `nox -s tests` and `nox -s e2e` green.
- `nox -s screenshots_headless` run and its output committed; `nox -s screenshots_verify` green.
- The new Alembic revision upgraded **and** downgraded against MariaDB.
- The working tree is clean after a test run.
