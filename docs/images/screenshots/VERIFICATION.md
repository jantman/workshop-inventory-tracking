# Screenshot Verification Report

**Generated:** 2026-08-10
**Status:** All valid

Regenerated from the files actually on disk. The previous edition of this report was
dated 2025-12-17 and claimed 8 screenshots against 12 present -- it was missing
`move_items.png`, `shorten_items.png`, `history_view.png` and `batch_operations_menu.png`,
all of which were embedded in the manual at the time. Regenerate this file rather than
appending to it.

## Summary

- **Total Screenshots:** 18
- **Total Size:** 2.49 MB
- **Average Size:** 141.7 KB
- **Target:** < 500 KB per screenshot
- **Largest:** 236.7 KB
- **Result:** All screenshots under target

## Screenshots

### README Screenshots (1)

| Filename | Size | Dimensions | Mode | Status |
|----------|------|------------|------|--------|
| readme/inventory_list.png | 236.7 KB | 1920x1366 | RGB | Valid |

### User Manual Screenshots (17)

| Filename | Size | Dimensions | Mode | Status |
|----------|------|------------|------|--------|
| user-manual/add_item_form.png | 185.2 KB | 1920x1806 | RGB | Valid |
| user-manual/batch_operations_menu.png | 152.6 KB | 1920x1080 | RGB | Valid |
| user-manual/bulk_creation_preview.png | 9.2 KB | 298x118 | RGB | Valid |
| user-manual/category_tree.png | 93.0 KB | 1920x1080 | RGB | Valid |
| user-manual/edit_item_form.png | 163.2 KB | 1920x1466 | RGB | Valid |
| user-manual/history_view.png | 143.7 KB | 1920x1080 | RGB | Valid |
| user-manual/move_items.png | 112.7 KB | 1920x1080 | RGB | Valid |
| user-manual/order_capture.png | 197.6 KB | 1920x1080 | RGB | Valid |
| user-manual/photo_gallery.png | 201.4 KB | 1920x2190 | RGB | Valid |
| user-manual/photo_upload.png | 163.2 KB | 1920x1466 | RGB | Valid |
| user-manual/product_add_form.png | 141.7 KB | 1920x1349 | RGB | Valid |
| user-manual/product_detail.png | 165.9 KB | 1920x1457 | RGB | Valid |
| user-manual/product_search.png | 137.1 KB | 1920x1080 | RGB | Valid |
| user-manual/reorder_list.png | 91.0 KB | 1920x1080 | RGB | Valid |
| user-manual/search_form.png | 126.6 KB | 1920x1417 | RGB | Valid |
| user-manual/search_results.png | 169.7 KB | 1920x1645 | RGB | Valid |
| user-manual/shorten_items.png | 60.3 KB | 1920x1080 | RGB | Valid |

## Quality Checks

- All files are valid PNG images
- All files under the 500 KB size limit
- All full-page screenshots use 1920px width
- All images use RGB colour mode
- PNG optimization applied

## How to Reproduce

```bash
nox -s screenshots_headless   # regenerates every file listed above
nox -s screenshots_verify     # the gate this report records
```

Deleting any of these files and running `screenshots_headless` brings it back; there is no
manual capture step. The catalog screenshots share the `_seed_catalog` helper in
`tests/e2e/test_screenshot_generation.py`.
