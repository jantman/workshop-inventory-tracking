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

```bash
# Run a specific test
python -m pytest tests/e2e/test_screenshot_generation.py::TestDocumentationScreenshots::test_screenshot_inventory_list -v

# Run all screenshot tests
python -m pytest tests/e2e/test_screenshot_generation.py -m screenshot -v
```

## Generated Screenshots

### README Screenshots (1)
- `readme/inventory_list.png` - Main inventory list view

### User Manual Screenshots (11)
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

**Total:** 12 screenshots

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

Screenshots are defined in `tests/e2e/screenshot_config.yaml`:

```yaml
screenshots:
  - name: "inventory_list_main"
    description: "Main inventory list view"
    test: "test_screenshot_inventory_list"
    output: "docs/images/screenshots/readme/inventory_list.png"
    viewport: [1920, 1080]
    wait_for: "table.inventory-table"
```

### Test Data

Realistic test data is defined in `tests/e2e/fixtures/screenshot_data.py`:
- 12 realistic inventory items (Steel, Aluminum, Brass)
- Complete purchase information
- Proper threading specifications
- Multiple locations and sub-locations

## Quality Standards

All screenshots must meet these requirements:

- **File Size:** < 500 KB (current avg: 145.7 KB)
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
    # Load test data
    items = get_inventory_items(count=3)
    self._load_inventory_data(live_server, items)

    # Navigate to page
    page.goto(f"{live_server.url}/new-feature")
    page.wait_for_selector("#feature-element", timeout=5000)

    # Capture screenshot
    self.screenshot.capture_viewport(
        "user-manual/new_feature.png",
        viewport_size=(1920, 1080),
        wait_for_selector="#feature-element",
        hide_selectors=[".toast-container"],
        full_page=True
    )
```

### 2. Update Configuration

Add entry to `tests/e2e/screenshot_config.yaml` (optional).

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
3. Add appropriate wait conditions
4. Use `page.wait_for_timeout()` if needed

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
