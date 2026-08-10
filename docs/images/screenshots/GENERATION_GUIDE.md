# Screenshot Generation Guide

## Overview

This project uses automated screenshot generation via Playwright e2e tests to create documentation screenshots. All screenshots are generated with realistic test data and consistent styling.

## Quick Start

### Generate All Screenshots

```bash
# Development mode (visible browsers)
nox -s screenshots

# Headless mode (CI/CD)
nox -s screenshots_headless

# Verify screenshot quality
nox -s screenshots_verify
```

### Run Specific Screenshot Tests

Go through nox for these too — **never invoke `pytest` directly** (`CLAUDE.md`). Both
screenshot sessions forward extra arguments to pytest after a `--`, and the session is what
installs the Playwright browser and sets `HEADLESS`; running pytest yourself gets neither.

```bash
# One test, headless
nox -s screenshots_headless -- -k test_screenshot_product_detail

# One test, with a visible browser, for debugging
nox -s screenshots -- -k test_screenshot_product_detail
```

Regenerating a single screenshot still rewrites `metadata.json`, whose `generated_at` is a
timestamp — so expect that one file to show as modified even when the PNG comes back
byte-identical. Diff it before committing; the other seventeen entries should be untouched.

`metadata.json` is merged by filename rather than written over the top, so a targeted run
updates one entry and leaves the rest. This has not always been true: it used to be
overwritten wholesale by each test's own generator, which meant the committed file described
only whichever test ran last. An entry for a deleted screenshot survives until something
regenerates — the authoritative inventory is the directory, which is what
`nox -s screenshots_verify` and `VERIFICATION.md` both read.

## Generated Screenshots

### README Screenshots (1)
- `readme/inventory_list.png` - Main inventory list view

### User Manual Screenshots (17)

Inventory:

- `user-manual/add_item_form.png` - Add new item interface
- `user-manual/bulk_creation_preview.png` - Bulk item creation preview
- `user-manual/edit_item_form.png` - Edit item interface
- `user-manual/photo_gallery.png` - Photo gallery with multiple photos
- `user-manual/photo_upload.png` - Photo upload interface
- `user-manual/search_form.png` - Advanced search form
- `user-manual/search_results.png` - Search results display
- `user-manual/move_items.png` - Batch move items interface
- `user-manual/shorten_items.png` - Item shortening interface
- `user-manual/history_view.png` - Item modification history modal
- `user-manual/batch_operations_menu.png` - Batch operations dropdown menu

Product catalog:

- `user-manual/product_search.png` - Product list with filters (also embedded in the README)
- `user-manual/product_detail.png` - Product detail: identifiers, purchases, stock
- `user-manual/product_add_form.png` - Add Product form
- `user-manual/order_capture.png` - Capture an Order, including the HTTP bookmarklet warning
- `user-manual/reorder_list.png` - Reorder list, all four low states
- `user-manual/category_tree.png` - Category tree with rename controls

**Total:** 18 screenshots

`product_search.png` is one file embedded in two documents; it counts once. The six catalog
screenshots share one seed helper, `_seed_catalog`, in
`tests/e2e/test_screenshot_generation.py` -- read its docstring before changing the seed data,
because two parts of it are load-bearing and silently degrade the pictures if removed.

## Screenshot Infrastructure

### Test File Structure

```
tests/e2e/
├── test_screenshot_generation.py  # Main screenshot test suite
├── screenshot_generator.py        # Screenshot capture utility
├── screenshot_config_loader.py    # YAML config loader
├── screenshot_config.yaml         # Screenshot definitions
└── fixtures/
    ├── screenshot_data.py         # Realistic test data
    └── images/                    # Sample test images
```

### Configuration

**There is none, and `tests/e2e/screenshot_config.yaml` is not it.** Nothing reads that file.
`test_screenshot_generation.py` does not import the loader and does not mention the YAML;
every filename, viewport, wait selector and hide list is hardcoded in the test function. The
YAML declares 20 screenshots, nine of which do not exist on disk, and names `test:` functions
that do not exist either.

The list above, and the test file, are the only descriptions of what gets generated. Do not
add entries to the YAML — a new entry generates nothing and makes the file look more
authoritative than it is.

### Test Data

Realistic test data is defined in `tests/e2e/fixtures/screenshot_data.py`:
- 12 realistic inventory items (Steel, Aluminum, Brass)
- Complete purchase information
- Proper threading specifications
- Multiple locations and sub-locations

## Quality Standards

All screenshots must meet these requirements:

- **File Size:** < 500 KB per file (`nox -s screenshots_verify` is the gate; see
  [VERIFICATION.md](VERIFICATION.md) for the current sizes rather than a figure duplicated
  here that goes stale)
- **Format:** PNG with RGB/RGBA color mode
- **Dimensions:** 1920px width for full-page screenshots
- **Optimization:** PNG compression enabled
- **Consistency:** Same viewport size, no animations, hidden toast messages

## Adding New Screenshots

### 1. Add Test Method

Add a new test method to `tests/e2e/test_screenshot_generation.py`:

```python
@pytest.mark.screenshot
@pytest.mark.e2e
def test_screenshot_new_feature(self, page, live_server):
    """Generate new feature screenshot"""
    # Seed directly -- driving the forms costs seconds per record for
    # pixels the service path produces identically.
    items = get_inventory_items(count=3)
    self._load_inventory_data(live_server, items)

    # Navigate, then wait on the thing you are photographing.
    page.goto(f"{live_server.url}/new-feature")
    expect(page.locator("#feature-element")).to_be_visible()

    # Capture screenshot
    self.screenshot.capture_viewport(
        "user-manual/new_feature.png",
        viewport_size=(1920, 1080),
        wait_for_selector="#feature-element",
        hide_selectors=[".toast-container"],
        full_page=True
    )
```

Both markers are required. `@pytest.mark.screenshot` is what keeps the test out of
`nox -s e2e`, which selects `-m "e2e and not screenshot"` — without it an ordinary e2e run
writes PNGs into `docs/` and leaves the working tree dirty.

**Wait with `expect(locator)`, which polls.** No `wait_for_timeout`, no `time.sleep`, no
`wait_for_load_state("networkidle")` — `CLAUDE.md`'s *Writing e2e tests* section is the
normative source and explains why. Resist `page.wait_for_selector(..., timeout=N)` in the test
body as well: the `timeout=` is a ceiling rather than a duration, so it is not itself a fixed
wait, but it is the shape that drifts into one, and against a JS-rendered region it is the
habit that leads to snapshot reads like `count()` returning zero.

A screenshot of a page that renders server-side needs one `expect` and nothing more — the
element existing after `goto()` is a complete signal.

### 2. Update This Guide

Add the file to the list above and correct the total. Do **not** add an entry to
`tests/e2e/screenshot_config.yaml`; see Configuration above for why.

### 3. Generate and Verify

```bash
# Generate
nox -s screenshots

# Verify
nox -s screenshots_verify
```

### 4. Update Documentation

Add screenshot reference to relevant documentation files with markdown:

```markdown
![New Feature](images/screenshots/user-manual/new_feature.png)
*Figure: Description of the new feature*
```

## Troubleshooting

### Screenshots Not Generating

1. Check Playwright is installed: `python -m playwright install chromium`
2. Verify test data is loading correctly
3. Check for timeout errors in test output
4. Run in headed mode to see browser: `nox -s screenshots`

### Screenshots Too Large

1. Check PNG optimization is enabled in `screenshot_generator.py`
2. Reduce viewport size if appropriate
3. Consider hiding unnecessary UI elements

### Element Not Found Errors

1. Verify element selector is correct
2. Check if element is visible on page load
3. Wait on the element with `expect(...)`, which polls

Do **not** reach for `page.wait_for_timeout()`. Fixed waits are prohibited (`CLAUDE.md`), and
a screenshot that needs one is a screenshot taken before the page finished — find the element
whose appearance means the work is done and wait on that instead.

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Generate Screenshots
  run: nox -s screenshots_headless

- name: Verify Screenshots
  run: nox -s screenshots_verify

- name: Upload Screenshots
  uses: actions/upload-artifact@v3
  with:
    name: screenshots
    path: docs/images/screenshots/
```

## Maintenance

### When to Regenerate

Regenerate screenshots when:
- UI changes affect documentation screenshots
- New features need documentation
- Screenshot quality standards change
- Test data needs updating

### Verification Schedule

Run verification:
- Before committing screenshot changes
- After UI updates
- As part of CI/CD pipeline
- Before documentation releases

## Resources

- [Playwright Documentation](https://playwright.dev/python/)
- [Screenshot Configuration Schema](screenshot_config.yaml)
- [Test Data Fixtures](../fixtures/screenshot_data.py)
- [Nox Documentation](https://nox.thea.codes/)
