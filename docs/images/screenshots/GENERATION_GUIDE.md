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

Two machine-readable files describe the screenshots, and
`nox -s screenshots_verify` keeps them honest. Prefer them over any prose
inventory — `VERIFICATION.md` in this directory is an old hand-written report
and is not maintained:

| File | Meaning |
|------|---------|
| `tests/e2e/screenshot_config.yaml` | The **expected** capture set — every screenshot the project intends to have, and its status |
| `docs/images/screenshots/metadata.json` | The **manifest** — what the most recent generation run actually captured |

To see the current set:

```bash
# Everything the project declares
grep -E '^\s+- name:|capture_status:' tests/e2e/screenshot_config.yaml

# Everything the last run captured
python -c "import json; print('\n'.join(s['filename'] for s in json.load(open('docs/images/screenshots/metadata.json'))['screenshots']))"
```

### `capture_status`

Every definition in `screenshot_config.yaml` declares one of:

| Status | Meaning | Must appear in the manifest? |
|--------|---------|------------------------------|
| `required` | An existing test captures it unconditionally | **Yes** — absence is a failure |
| `conditional` | An existing test captures it behind a runtime DOM guard (`if locator.count() > 0`, `try/except: return`), so the capture may not fire | Optional — absence is reported as a note, and a committed PNG left over from an earlier successful run is not treated as stale |
| `planned` | No capture code exists yet; `test:` names the future test | **No** — presence is a failure |

This is what makes "the manifest covers the configured set" assertable: without
it, the declared set and the captured set could never legitimately match.

### The manifest (`metadata.json`)

Written by `ScreenshotGenerator.save_metadata()` at the end of every screenshot
test. A session-scoped shared manifest accumulates entries across the whole run,
so the file describes the run as a whole and not just the last test.

```json
{
  "generated_at": "2026-07-25T14:00:34.606711",
  "screenshots": [
    {
      "filename": "user-manual/batch_operations_menu.png",
      "capture_type": "viewport",
      "timestamp": "2026-07-25T14:00:37.094143",
      "details": {
        "viewport_size": [1920, 1080],
        "full_page": false,
        "wait_for_selector": null,
        "hide_selectors": [".toast-container"]
      }
    }
  ]
}
```

Checked by the verifier:

- `filename` is a string; it is interpreted as a path relative to
  `docs/images/screenshots/`, and the cross-checks below are what catch a
  value that is not one
- `capture_type` is one of `full_page`, `element`, `viewport`
- `details` always carries `viewport_size` and `hide_selectors` keys (`null`
  allowed) whatever the capture type; other keys vary by type
- one entry per filename — no duplicates

Written by the generator but not re-checked by the verifier: entries are sorted
by `filename` and the file ends with a newline.

The manifest is a generated artifact. **Never hand-edit it** — regenerate and
commit the result. Note that `generated_at` and every entry's `timestamp` are
rewritten on each run, so the file always shows a diff after regeneration.

## Screenshot Infrastructure

### Test File Structure

```
tests/e2e/
├── test_screenshot_generation.py  # Main screenshot test suite
├── screenshot_generator.py        # Screenshot capture utility + manifest
├── screenshot_config_loader.py    # YAML config loader
├── screenshot_config.yaml         # Screenshot definitions
├── screenshot_verifier.py         # Manifest/config/quality verification
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
    output: "readme/inventory_list.png"      # relative to docs/images/screenshots/
    capture_status: "required"                # required | conditional | planned
    viewport: [1920, 1080]
    wait_for: "table.inventory-table"
    documentation_files:
      - file: "README.md"
        section: "## Features"
        caption: "Main inventory list interface"
```

`name`, `description`, `test`, `output`, `capture_status` and
`documentation_files` are all required; `output` must be a non-empty string,
unique across definitions. `nox -s screenshots_verify` enforces those rules.

Separately, `test` must name a real test method in
`tests/e2e/test_screenshot_generation.py` for `required` and `conditional`
entries. That one is *not* checked by the verify session — it is enforced by
`tests/unit/test_screenshot_infrastructure.py`, which runs under `nox -s tests`.

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

## What `nox -s screenshots_verify` Enforces

The session runs `tests/e2e/screenshot_verifier.py` (importable as
`python -m tests.e2e.screenshot_verifier`, and unit tested in
`tests/unit/test_screenshot_infrastructure.py`). It exits 0 when everything
agrees and 1 with a list of issues otherwise.

**Manifest integrity**

- `metadata.json` exists and is valid JSON with a `screenshots` list
- Every entry has a string `filename`, a `capture_type` drawn from
  `full_page`/`element`/`viewport`, a `timestamp`, and a `details` dict
  containing `viewport_size` and `hide_selectors`
- No two entries share a `filename`

**Manifest ↔ disk**

- Every PNG on disk is recorded in the manifest
  (otherwise: `<file>: on disk but not recorded in manifest`) — except PNGs
  belonging to a `conditional` capture, which may survive a run whose guard
  did not fire
- Every manifest entry has its PNG on disk
  (otherwise: `<file>: recorded in manifest but missing on disk`)

**Manifest ↔ config**

- Every manifest entry is declared in `screenshot_config.yaml`
  (otherwise: `<file>: not declared in screenshot_config.yaml`)
- Every `required` capture appears in the manifest
  (otherwise: `<output>: required capture missing from manifest`)
- No `planned` capture appears in the manifest
  (otherwise: `<name>: captured but marked planned; update capture_status`)
- Skipped `conditional` captures and outstanding `planned` ones are printed as
  informational notes, not failures

**Config sanity**

- Required fields present, every `capture_status` valid, no duplicate `output`

**Quality gate**

- At least one screenshot exists; all are valid PNGs under 500 KB in RGB/RGBA

A run that regenerates only some screenshots is therefore no longer
indistinguishable from a complete one: the manifest records exactly what that
run wrote, and any `required` capture it missed is reported.

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

Add an entry to `tests/e2e/screenshot_config.yaml`. **This is required, not
optional** — the YAML is the authoritative expected-capture set, and
`screenshots_verify` fails on any captured file that is not declared there.

Pick the right `capture_status`:

- `required` if the capture runs unconditionally in the new test
- `conditional` if it sits behind a runtime guard that may not fire
- `planned` if you are declaring the screenshot before writing the test

### 3. Generate and Verify

```bash
# Generate (rewrites docs/images/screenshots/metadata.json)
nox -s screenshots_headless      # or `nox -s screenshots` to watch the browser

# Verify manifest, config and quality
nox -s screenshots_verify
```

Commit the regenerated `metadata.json` alongside the new PNG.

Two things to know about regeneration:

- **Always run the whole suite.** `save_metadata()` writes the manifest for the
  session it ran in, so a filtered run (`-k`, `--lf`, a single test) truncates
  `metadata.json` to just those captures and every other `required` screenshot
  then fails verification.
- **Renaming or removing an `output` leaves its old PNG behind.** Nothing
  deletes it, and it will be reported as `on disk but not recorded in
  manifest` until you `rm` it yourself.

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
