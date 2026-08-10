# Contract: Catalog Screenshot Manifest

Six new captures, added as six functions to `tests/e2e/test_screenshot_generation.py`.

This document is the specification. It is **not** read by anything at runtime — see
[research.md](../research.md) Finding 3 for why `tests/e2e/screenshot_config.yaml` is not
extended.

## Binding rules for every capture

- Decorated `@pytest.mark.screenshot` **and** `@pytest.mark.e2e`, matching the eleven
  existing capture tests. `nox -s e2e` selects `-m "e2e and not screenshot"`, so this is what
  keeps an e2e run from writing into `docs/images/screenshots/` (Principle IV, FR-021,
  SC-010).
- Seeded through `live_server.add_test_products(...)`, never by driving the Add Product form.
  Ages set with `live_server.backdate_product(...)`; purchases through
  `CatalogService(live_server.storage).record_purchase(...)`.
- Waits name an element. No `wait_for_timeout`, no `time.sleep`, no
  `wait_for_load_state("networkidle")`. All six pages are server-rendered and reached by
  `goto()`, so element presence is a complete signal (CLAUDE.md pattern **C**).
- Captured via `ScreenshotGenerator.capture_viewport(...)` at `(1920, 1080)`, `full_page=True`
  unless noted, `hide_selectors=[".toast-container"]` — the shape every existing capture uses.
- Prices are `Decimal`, never `float` (Principle III).
- Every output must pass `nox -s screenshots_verify`: valid PNG, RGB, under 500 KB.

## Shared seed data

One helper in the test file builds the catalog the captures share. Realistic enough that each
screen shows what it is for (FR-020) — a category tree with depth, tracked and untracked
quantities, a flagged product, an outstanding order, and identifiers of more than one kind.

| Description | Category | Tags | Qty | Threshold | Notes |
|---|---|---|---|---|---|
| Carbon film resistor, 10k 1/4W | `electronics/passives/resistors` | `surplus` | 240 | 50 | MPN + GTIN identifiers |
| Ceramic capacitor, 100nF 50V X7R | `electronics/passives/capacitors` | `rohs` | 12 | 25 | below threshold → on the reorder list |
| LM358 dual op-amp, DIP-8 | `electronics/active` | `surplus, rohs` | *not tracked* | — | flagged **Low** by hand, backdated 3 months |
| M4×16 hex bolt, stainless | `hardware/fasteners` | `surplus` | 0 | 10 | **None on hand** — the state that must look different from *not tracked* |
| Blue thread locker, 10ml | `chemicals/adhesives` | — | 3 | 2 | one received purchase, one outstanding |
| 24V 5A switching PSU | `electronics/power` | — | *not tracked* | — | DISTRIBUTOR identifier, purchase with price |

Backdating matters. `add_test_products` stamps every count with `datetime.now()`, so an
unbackdated capture shows *"counted today"* against every row — picturing the age feature at
the one value where it looks pointless. At least two products carry a backdated
`quantity_updated_at`, and the flagged one a backdated `stock_status_updated_at`, so
*"counted 8 months ago"* and *"Flagged low 3 months ago"* appear as the manual describes them.

---

## 1. `product_search.png`

| | |
|---|---|
| **Test** | `test_screenshot_product_search` |
| **Route** | `/products` |
| **Wait on** | `#product-table` |
| **Capture** | viewport 1920×1080, `full_page=True` |
| **Embedded in** | `docs/user-manual.md` → *Finding Products*; `README.md` → Features |
| **Shows** | the whole seeded catalog, the filter bar (`#product-filters`), and the three quantity states side by side |

The only capture used twice. It is the catalog's counterpart to
`readme/inventory_list.png`, which is why it carries the README duty (FR-017).

## 2. `product_detail.png`

| | |
|---|---|
| **Test** | `test_screenshot_product_detail` |
| **Route** | `/products/<id>` for *Blue thread locker* |
| **Wait on** | `#stock-card`, then `#identifier-list` |
| **Capture** | viewport 1920×1080, `full_page=True` |
| **Embedded in** | `docs/user-manual.md` → *The Product Catalog* |
| **Shows** | internal code (`#internal-code`), identifiers, purchase history with `#latest-price`, tracked quantity with its age |

Chosen for the intro section because it is the one screen that answers the question the
catalog exists for — *what is this, what did it cost, where did it come from* — in one view.

**Size risk.** The longest of the six: stock card, identifiers, specifications, purchase
history and attachments stacked. If it exceeds 500 KB at `full_page=True`, drop to
`full_page=False` at 1920×1080 rather than raising the ceiling. The verification session is
the gate, not a judgment call.

## 3. `product_add_form.png`

| | |
|---|---|
| **Test** | `test_screenshot_product_add_form` |
| **Route** | `/products/new` |
| **Wait on** | `#product-form` |
| **Capture** | viewport 1920×1080, `full_page=True` |
| **Embedded in** | `docs/user-manual.md` → *Adding a Product* |
| **Shows** | every field the section walks through, in order, with only Description required |

Seeding still runs first: the location and sub-location fields autocomplete from what exists,
and an empty database makes that invisible.

## 4. `order_capture.png`

| | |
|---|---|
| **Test** | `test_screenshot_order_capture` |
| **Route** | `/products/capture` |
| **Wait on** | `#capture-form` |
| **Capture** | viewport 1920×1080, `full_page=True` |
| **Embedded in** | `docs/user-manual.md` → *Capturing an Order When You Place It* |
| **Shows** | the paste-URL box and the *Capture to Workshop* bookmarklet (`#capture-bookmarklet`) |

**`#bookmarklet-http-warning` must be visible, not hidden.** The test server runs over plain
HTTP, so the page renders its HTTPS warning — and the manual devotes a block quote to exactly
that warning and how to resolve it. Hiding it would picture a state the manual then spends a
paragraph explaining. This is the one place the manifest deliberately keeps a warning banner
in frame.

## 5. `reorder_list.png`

| | |
|---|---|
| **Test** | `test_screenshot_reorder_list` |
| **Route** | `/products/reorder` |
| **Wait on** | `#reorder-table` |
| **Capture** | viewport 1920×1080, `full_page=True` |
| **Embedded in** | `docs/user-manual.md` → *Stock Levels and Reordering* |
| **Shows** | a threshold-derived low, a hand-flagged low with its age, an **on the way** row, and **None on hand** |

The seed must produce a non-empty list. `#nothing-to-reorder` renders instead when nothing
qualifies, and a screenshot of an empty reorder list documents nothing. The test asserts the
table is present before capturing, which also fails loudly if the seed stops qualifying.

## 6. `category_tree.png`

| | |
|---|---|
| **Test** | `test_screenshot_category_tree` |
| **Route** | `/products/categories` |
| **Wait on** | `#category-tree` |
| **Capture** | viewport 1920×1080, `full_page=True` |
| **Embedded in** | `docs/user-manual.md` → *Categories and Tags* |
| **Shows** | three-level nesting under `electronics`, per-category counts, and the **Rename** control the section documents |

Depth is the point. `electronics/passives/resistors` exists in the seed so the tree shows
more than one level, which is what makes the "renaming carries everything beneath it" rule
legible.

---

## Inventory documents to update (FR-023)

| File | Now | After |
|---|---|---|
| `docs/images/screenshots/GENERATION_GUIDE.md` | 1 readme + 11 user-manual = **12** | 1 readme + 17 user-manual = **18** |
| `docs/images/screenshots/VERIFICATION.md` | claims **8**, dated 2025-12-17 — already wrong by 4 | regenerated: **18**, with real sizes and dimensions |
| `docs/images/screenshots/metadata.json` | written by the suite | regenerated |
| `tests/e2e/screenshot_config.yaml` | declares 20, 9 nonexistent, unread by anything | **untouched** — see research.md Finding 3 |

`product_search.png` is one file embedded in two documents; it counts once.
