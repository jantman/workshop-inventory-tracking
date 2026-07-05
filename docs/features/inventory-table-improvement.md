# Feature: Inventory Table Improvement

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Requirements

Both the item list (`/inventory`) and advanced search (`/inventory/search`) views share a common inventory/result table. However, there is an issue in the display of dimensions. Currently, the "Dimensions" column includes the width, thickness, length displayed as "<width> x <thickness> x <length>", but right next to it is a "length" column. This results in these tables showing the length twice but not showing the (optional) wall thickness. Similarly, for threaded rod, the "Dimensions" field includes both the thread and diameter, as well as the length.

1. Remove the duplicated length from the "Dimensions" field on these tables.
2. If present and non-null/non-zero, add the "wall thickness" as a third dimension in the Dimension column.
3. Update tests accordingly.
4. Re-generate screenshots.

## Implementation Plan

This is a small, single-milestone feature. Commit prefix: `Inventory Table Improvement - 1.1`.

### Background / root cause

The `/inventory` list and `/inventory/search` views render a shared table whose rows
are built client-side by `app/static/js/components/inventory-table.js`
(`createRow`), which delegates the two relevant cells to helpers in
`app/static/js/components/item-formatters.js`:

- **Dimensions** column → `formatFullDimensions(dimensions, itemType, thread)`
- **Length** column → `formatDimensions(dimensions, itemType)`

`formatFullDimensions` currently appends the length to every physical-dimension
string (e.g. rectangular `width" × thickness" × length"`, round/square
`⌀width" × length"`, threaded rod `🔩thread ⌀diameter" × length"`), which is the
same value shown in the dedicated Length column — hence the duplication. It never
references `wall_thickness`, even though the field exists on the `Dimensions`
model, is serialized to the frontend via `Dimensions.to_dict()`, and is returned
by both `/api/inventory/list` and `/api/inventory/search`.

### Changes

1. **`app/static/js/components/item-formatters.js` — `formatFullDimensions`**
   - Stop emitting `length` in the Dimensions column (it lives in the Length column).
   - Append `wall_thickness` as an additional dimension when it is present and
     non-zero, so:
     - Rectangular: `width" × thickness"` → `width" × thickness" × wall_thickness"`
     - Round / Square: `⌀width"` → `⌀width" × wall_thickness"`
     - Threaded rod: `🔩thread ⌀diameter"` (+ wall thickness if present)
   - Update the function's JSDoc examples to match the new output.
   - `formatDimensions` (Length column) is unchanged — it already shows only length.

2. **Tests (`tests/e2e/test_dimensions_display.py`, new)**
   - There are currently **no** tests (JS or e2e) that assert on the formatted
     dimension strings, so add e2e coverage. Parametrized over `list` and `search`
     pages using the existing `InventoryTableMixin.get_table_items()` helper, assert:
     - Round bar (no wall thickness): Dimensions = `⌀W"`, no length; Length column = length.
     - Round tube (wall thickness): Dimensions = `⌀W" × WT"`.
     - Rectangular bar (no wall thickness): Dimensions = `W" × T"`, no length.
     - Rectangular tube (wall thickness): Dimensions = `W" × T" × WT"`.
     - In all cases the Dimensions cell does **not** contain the item's length value.

3. **Documentation** — the user-manual / README text does not describe the exact
   table-cell format, so no prose changes are expected; re-verify during the final
   docs pass and update if needed.

4. **Screenshots** — regenerate via `nox -s screenshots_headless`. The affected
   images are `docs/images/screenshots/readme/inventory_list.png` and
   `docs/images/screenshots/user-manual/search_results.png`. The screenshot
   fixtures (`tests/e2e/fixtures/screenshot_data.py`) already include tube items
   with wall thickness (e.g. JA000102, JA000107, JA000109, JA000112), so the new
   behavior will be visible.

### Verification (feature completion)

- Run the full unit suite and the full e2e suite (≤15 min, with an explicit
  long Bash timeout) and ensure everything passes.
- Regenerate and verify screenshots.

## Progress

Implementation complete (commit prefix `Inventory Table Improvement - 1.1`):

1. **Done** — `formatFullDimensions` (`app/static/js/components/item-formatters.js`)
   no longer emits the length in the Dimensions column and now appends
   `wall_thickness` (when present and non-zero) as an additional dimension.
   JSDoc examples updated. The Length-column helper is unchanged.
2. **Done** — Added `tests/e2e/test_dimensions_display.py`, parametrized over the
   list and search pages, asserting (a) the Dimensions column no longer duplicates
   the length and (b) wall thickness is shown for round/rectangular tubes.
3. **Done** — Reviewed docs; no prose described the exact table-cell format, so no
   documentation changes were required. (`docs/deployment-guide.md` already notes
   that Wall Thickness is shown "when available", which is now accurate.)
4. **Done** — Regenerated screenshots via `nox -s screenshots_headless` and verified
   with `nox -s screenshots_verify`. `readme/inventory_list.png`,
   `user-manual/search_results.png`, and `user-manual/batch_operations_menu.png`
   now show the corrected Dimensions column (e.g. `⌀2" × 0.125"` for a round tube,
   `2" × 2" × 0.125"` for an angle, and threaded rod `🔩1/2-13 UNC ⌀0.5"` with no
   duplicated length).

### Test results

- Unit suite (`nox -s tests`): **342 passed**.
- E2E suite (`nox -s e2e`): **301 passed, 1 skipped** (full run, ~18 min).

_Awaiting human verification before moving this document to `complete/` and opening a PR._
