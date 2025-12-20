# Feature: Documentation Screenshots

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Overview

The project has comprehensive documentation but lacks visual aids to help users understand the interface and workflows. This feature will add screenshots of important functionality to the documentation and create an automated system to generate and update these screenshots using the existing e2e test infrastructure with realistic test data.

### Current State

**Documentation:**
- `README.md` - Project overview and quick start
- `docs/user-manual.md` - Complete feature guide (13 sections, text-only)
- `docs/deployment-guide.md` - Production deployment and configuration
- `docs/development-testing-guide.md` - Testing framework and development workflow
- `docs/troubleshooting-guide.md` - Problem-solving and diagnostics

**Current Limitation:**
- All documentation is text-only without visual aids
- Users must rely on descriptions to understand UI features
- No way to automatically update screenshots when UI changes
- Difficult for new users to quickly understand the application

### Desired Behavior

This feature will add:

#### 1. Documentation Screenshots

Add screenshots to documentation in the following locations:

**README.md:**
- Main inventory list view showing key features
- Add item form showing field layout

**docs/user-manual.md:**
- **Adding New Inventory** section:
  - Add item form with all fields visible
  - Barcode scanner integration example
  - Auto-complete dropdown examples
  - Bulk creation preview with JA ID range
- **Label Printing** section:
  - Label preview modal
  - Bulk label printing interface
  - Label customization options
- **Managing Existing Inventory** section:
  - Item details modal
  - Edit item form
  - Photo upload interface with gallery
  - History view with modification timeline
- **Photo Management** section:
  - Photo gallery with multiple photos
  - Photo viewer (lightbox)
  - Copy/paste photos workflow (clipboard banner)
- **Advanced Search** section:
  - Search form with multiple filters
  - Search results table
  - Export options
- **Batch Operations** section:
  - Move items interface
  - Shorten items interface
  - Batch selection and options menu

**docs/deployment-guide.md:**
- Database migration output example
- Health check endpoint response

**docs/development-testing-guide.md:**
- Test execution output
- E2E test running in browser

#### 2. Automated Screenshot Generation System

Create a dedicated screenshot generation system that:

**Screenshot Infrastructure:**
- New Python module: `tests/e2e/screenshot_generator.py`
  - Screenshot capture utilities
  - Image processing and optimization
  - Metadata tracking (which test generated which screenshot)
  - Consistent viewport sizes and styling
- New directory: `docs/images/screenshots/`
  - Organized subdirectories by documentation file
  - Naming convention: `{section}_{description}.png`
- Configuration file: `tests/e2e/screenshot_config.yaml`
  - Defines which screenshots to generate
  - Screenshot metadata (viewport size, wait conditions, etc.)
  - Documentation insertion points

**Screenshot Generation Features:**
- Capture full page or specific element screenshots
- Apply consistent viewport sizes (1920x1080 for desktop views, 375x667 for mobile examples)
- Wait for animations/transitions to complete
- Add optional annotations (arrows, highlights, labels)
- Optimize image file sizes (PNG compression)
- Generate light/dark mode versions (if theme support added later)

**Realistic Test Data:**
- Create comprehensive test data fixtures in `tests/e2e/fixtures/screenshot_data.py`
- Sample inventory items representing real workshop materials:
  - Metal stock (rods, tubes, sheets, bars) with realistic dimensions
  - Hardware items (bolts, nuts, washers) with proper threading specs
  - Various materials (Steel, Aluminum, Brass, Stainless Steel)
  - Multiple locations and sub-locations
  - Photos attached to some items
  - Purchase information with dates and vendors
  - Complete history records showing shortening operations
- Ensure data is visually complete (no empty fields in screenshots)

**Screenshot Test Suite:**
- New test file: `tests/e2e/test_screenshot_generation.py`
  - Dedicated test suite that generates all documentation screenshots
  - Each test sets up realistic data, navigates to the feature, and captures screenshot
  - Tests can be run independently or as a suite
  - Includes validation that screenshots were created successfully
  - Can be run in CI/CD to detect visual regressions
- Integration with existing e2e tests:
  - Add optional screenshot capture to existing tests
  - Use pytest markers to enable/disable screenshot generation
  - Environment variable to control screenshot generation mode

#### 3. Documentation Updates

**Markdown Image Insertion:**
- Insert screenshots at appropriate locations in documentation
- Use descriptive alt text for accessibility
- Add captions explaining what the screenshot shows
- Maintain responsive image sizing
- Link to full-size images where appropriate

**Screenshot Update Workflow:**
- Document how to regenerate screenshots after UI changes
- Add npm/make command for screenshot generation: `make screenshots`
- Update development guide with screenshot maintenance procedures
- Add screenshot validation to CI/CD pipeline

### Technical Requirements

#### 1. Screenshot Infrastructure

**Screenshot Generator Module (`tests/e2e/screenshot_generator.py`):**
```python
class ScreenshotGenerator:
    """Utility class for capturing and managing documentation screenshots"""

    def __init__(self, page, output_dir='docs/images/screenshots'):
        self.page = page
        self.output_dir = output_dir
        self.metadata = {}

    def capture_full_page(self, filename, wait_for_selector=None,
                         hide_selectors=None, annotations=None):
        """Capture full page screenshot with optional element hiding"""

    def capture_element(self, selector, filename, padding=10):
        """Capture screenshot of specific element with padding"""

    def capture_viewport(self, filename, viewport_size=(1920, 1080)):
        """Capture screenshot at specific viewport size"""

    def add_annotation(self, image_path, annotations):
        """Add arrows, highlights, or text annotations to screenshot"""

    def optimize_image(self, image_path, quality=85):
        """Optimize PNG file size while maintaining quality"""

    def save_metadata(self):
        """Save JSON metadata about when/how screenshots were generated"""
```

**Configuration Format (`tests/e2e/screenshot_config.yaml`):**
```yaml
screenshots:
  - name: "inventory_list_main"
    description: "Main inventory list view"
    test: "test_screenshot_inventory_list"
    output: "docs/images/screenshots/user-manual/inventory_list.png"
    viewport: [1920, 1080]
    documentation_files:
      - file: "README.md"
        section: "## Features"
        caption: "Main inventory list interface"
      - file: "docs/user-manual.md"
        section: "## Managing Existing Inventory"
        caption: "Figure 1: Inventory list with search and filtering"

  - name: "add_item_form"
    description: "Add item form with all fields"
    test: "test_screenshot_add_item_form"
    output: "docs/images/screenshots/user-manual/add_item_form.png"
    viewport: [1920, 1080]
    wait_for: "#add-item-form"
    hide_elements: [".toast-container"]
    documentation_files:
      - file: "docs/user-manual.md"
        section: "## Adding New Inventory"
        caption: "Figure 2: Add item form showing all available fields"
```

#### 2. Test Data Fixtures

**Realistic Test Data (`tests/e2e/fixtures/screenshot_data.py`):**
```python
SCREENSHOT_INVENTORY_DATA = [
    {
        "ja_id": "JA000101",
        "type": "Rod",
        "shape": "Round",
        "material": "Steel - 1018 Cold Rolled",
        "length": "72",
        "width": "1.5",
        "location": "Metal Storage Rack A",
        "sub_location": "Section 3, Shelf 2",
        "purchase_date": "2024-11-15",
        "purchase_price": "45.99",
        "vendor": "OnlineMetals.com",
        "notes": "General purpose machining stock",
        "photos": ["tests/fixtures/images/steel_rod_sample.jpg"]
    },
    {
        "ja_id": "JA000102",
        "type": "Tube",
        "shape": "Round",
        "material": "Aluminum - 6061-T6",
        "length": "96",
        "width": "2",
        "wall_thickness": "0.125",
        "location": "Metal Storage Rack B",
        "sub_location": "Section 1",
        "purchase_date": "2024-10-22",
        "purchase_price": "78.50",
        "vendor": "McMaster-Carr",
        "part_number": "9056K141"
    },
    # ... more realistic items
]

SCREENSHOT_HISTORY_DATA = [
    {
        "original_ja_id": "JA000101",
        "action": "shorten",
        "new_ja_id": "JA000150",
        "new_length": "24",
        "timestamp": "2024-12-01 14:30:00"
    }
]
```

#### 3. Screenshot Generation Test Suite

**Test File Structure (`tests/e2e/test_screenshot_generation.py`):**
```python
import pytest
from tests.e2e.screenshot_generator import ScreenshotGenerator
from tests.e2e.fixtures.screenshot_data import SCREENSHOT_INVENTORY_DATA

class TestDocumentationScreenshots:
    """Generate all documentation screenshots with realistic data"""

    @pytest.fixture(autouse=True)
    def setup_screenshot_generator(self, page):
        """Initialize screenshot generator for all tests"""
        self.screenshot = ScreenshotGenerator(page)
        yield
        self.screenshot.save_metadata()

    @pytest.mark.screenshot
    def test_screenshot_inventory_list(self, page, live_server):
        """Generate inventory list screenshot"""
        # Load realistic test data
        self._load_inventory_data(SCREENSHOT_INVENTORY_DATA)

        # Navigate to inventory list
        page.goto(f"{live_server.url}/inventory")

        # Wait for table to load
        page.wait_for_selector("table.inventory-table")

        # Capture screenshot
        self.screenshot.capture_viewport(
            "user-manual/inventory_list.png",
            viewport_size=(1920, 1080)
        )

    @pytest.mark.screenshot
    def test_screenshot_add_item_form(self, page, live_server):
        """Generate add item form screenshot"""
        # Navigate to add item page
        page.goto(f"{live_server.url}/inventory/add")

        # Fill form with realistic data (but don't submit)
        self._fill_form_for_screenshot(page, SCREENSHOT_INVENTORY_DATA[0])

        # Capture full page
        self.screenshot.capture_full_page(
            "user-manual/add_item_form.png",
            hide_selectors=[".toast-container"]
        )

    @pytest.mark.screenshot
    def test_screenshot_photo_gallery(self, page, live_server):
        """Generate photo gallery screenshot"""
        # Create item with multiple photos
        item_with_photos = self._create_item_with_photos("JA000201")

        # Navigate to edit page
        page.goto(f"{live_server.url}/inventory/edit/JA000201")

        # Capture photo section
        self.screenshot.capture_element(
            "#photo-manager-container",
            "user-manual/photo_gallery.png",
            padding=20
        )

    # ... more screenshot tests
```

#### 4. Documentation Integration

**Image Directory Structure:**
```
docs/images/
├── screenshots/
│   ├── readme/
│   │   ├── inventory_list.png
│   │   └── add_item.png
│   ├── user-manual/
│   │   ├── add_item_form.png
│   │   ├── bulk_creation_preview.png
│   │   ├── label_printing.png
│   │   ├── item_details_modal.png
│   │   ├── photo_gallery.png
│   │   ├── photo_viewer.png
│   │   ├── photo_copy_workflow.png
│   │   ├── search_form.png
│   │   ├── search_results.png
│   │   ├── move_items.png
│   │   ├── shorten_items.png
│   │   └── history_view.png
│   ├── deployment-guide/
│   │   ├── migration_output.png
│   │   └── health_check.png
│   └── development-guide/
│       ├── test_execution.png
│       └── e2e_browser.png
├── annotations/
│   └── (annotated versions of screenshots)
└── metadata.json
```

**Markdown Integration Example:**
```markdown
## Adding New Inventory

### Using the Add Item Form

The add item form provides fields for all inventory attributes:

![Add Item Form](../images/screenshots/user-manual/add_item_form.png)
*Figure 1: Add item form showing required fields (marked with *) and optional fields*

1. **Navigate**: Click "Add Item"
2. **Required Fields** (marked with *):
   - **JA ID**: Unique identifier (e.g., "JA12345")
   ...
```

#### 5. Automation and CI/CD Integration

**Makefile Target:**
```makefile
.PHONY: screenshots
screenshots:
	@echo "Generating documentation screenshots..."
	pytest tests/e2e/test_screenshot_generation.py -m screenshot --headed
	@echo "Screenshots generated in docs/images/screenshots/"

.PHONY: screenshots-headless
screenshots-headless:
	@echo "Generating documentation screenshots (headless)..."
	pytest tests/e2e/test_screenshot_generation.py -m screenshot
```

**GitHub Actions Workflow:**
- Add optional workflow to regenerate screenshots on UI changes
- Store screenshots as artifacts
- Create PR with updated screenshots when UI changes detected

#### 6. Screenshot Quality Standards

**Technical Standards:**
- **Format**: PNG with compression
- **Desktop viewport**: 1920x1080 (primary), 1366x768 (secondary)
- **Mobile viewport**: 375x667 (iPhone SE), 414x896 (iPhone XR)
- **File size**: < 500KB per screenshot (optimized)
- **Color depth**: 24-bit RGB
- **DPI**: 72 (web standard)

**Content Standards:**
- Use realistic, representative data (no "test123" or placeholder text)
- Show successful states (not error states unless demonstrating error handling)
- Include enough data to show features (e.g., 5-10 items in list views)
- Hide sensitive information (if any)
- Consistent UI state (no transient loading spinners)
- Clean state (no debug overlays, toast notifications unless relevant)

**Accessibility Standards:**
- All screenshots must have descriptive alt text
- Figure captions should explain what the screenshot demonstrates
- Don't rely solely on screenshots to convey information
- Ensure text in screenshots is readable (minimum 12px font size visible)

### Test Coverage Requirements

**Screenshot Generation:**
- All defined screenshots in config generate successfully
- Screenshots saved to correct paths
- Metadata file created with generation timestamp and test info
- Image optimization reduces file sizes appropriately
- Screenshots are visually correct (manual validation initially)

**Test Data:**
- Fixtures create realistic inventory items
- Data covers all field types (dimensions, threading, locations, photos)
- History records are properly associated
- Photos upload and display correctly
- No missing or placeholder data in screenshots

**Documentation Integration:**
- All screenshot references in markdown are valid
- Image paths are correct and accessible
- Screenshots display in rendered markdown
- Alt text is present for all images
- File sizes are within acceptable limits

**Automation:**
- `make screenshots` command works correctly
- Screenshots can be regenerated on demand
- Headless mode works for CI/CD
- Screenshot generation doesn't interfere with regular test suite
- Pytest markers correctly filter screenshot tests

**Visual Regression (Future):**
- Baseline screenshots stored for comparison
- Visual diff detection when UI changes
- Automated alerts when screenshots become outdated

### Implementation Plan

The feature is broken down into 4 milestones:

### Milestone 1: Screenshot Infrastructure & Test Data
**Prefix: `Documentation Screenshots - M1`**

- **M1.1**: Create directory structure and screenshot generator module
  - Create `docs/images/screenshots/` directory with subdirectories
  - Implement `ScreenshotGenerator` class in `tests/e2e/screenshot_generator.py`
  - Add Pillow and other image processing dependencies
- **M1.2**: Create screenshot configuration system
  - Implement `screenshot_config.yaml` with initial screenshot definitions
  - Create config loader in screenshot generator
  - Add metadata tracking system
- **M1.3**: Create realistic test data fixtures
  - Implement `tests/e2e/fixtures/screenshot_data.py` with comprehensive inventory data
  - Create sample image files for photo testing
  - Add helper functions to load test data into database
- **M1.4**: Test infrastructure and run unit tests
  - Verify screenshot generator can capture and save images
  - Test image optimization
  - Run unit test suite to ensure no regressions

### Milestone 2: Core Screenshot Generation Tests
**Prefix: `Documentation Screenshots - M2`**

- **M2.1**: Implement inventory and search screenshots
  - `test_screenshot_inventory_list` - Main inventory list view
  - `test_screenshot_search_form` - Advanced search interface
  - `test_screenshot_search_results` - Search results with filters
- **M2.2**: Implement add/edit item screenshots
  - `test_screenshot_add_item_form` - Complete add item form
  - `test_screenshot_bulk_creation` - Bulk creation preview
  - `test_screenshot_item_details_modal` - Item details view
- **M2.3**: Implement photo management screenshots
  - `test_screenshot_photo_upload` - Photo upload interface
  - `test_screenshot_photo_gallery` - Gallery with multiple photos
  - `test_screenshot_photo_copy_workflow` - Copy/paste photos with clipboard banner
- **M2.4**: Verify all screenshots generated correctly
  - Run screenshot test suite
  - Manually review screenshot quality and content
  - Verify metadata generated correctly

### Milestone 3: Additional Feature Screenshots & Automation
**Prefix: `Documentation Screenshots - M3`**

- **M3.1**: Implement batch operation screenshots
  - `test_screenshot_move_items` - Move items interface
  - `test_screenshot_shorten_items` - Shorten items interface
  - `test_screenshot_label_printing` - Label printing preview
- **M3.2**: Implement history and utility screenshots
  - `test_screenshot_history_view` - Item modification history
  - `test_screenshot_batch_operations` - Batch selection and options menu
- **M3.3**: Add deployment/development screenshots
  - `test_screenshot_database_migration` - Migration output (terminal screenshot)
  - `test_screenshot_test_execution` - Test running output
- **M3.4**: Create automation scripts
  - Add `make screenshots` Makefile target
  - Add `make screenshots-headless` for CI/CD
  - Document screenshot regeneration workflow
- **M3.5**: Run complete test suites
  - Run all screenshot tests
  - Run unit and e2e test suites to ensure no regressions
  - Verify all screenshots meet quality standards

### Milestone 4: Documentation Integration & Polish
**Prefix: `Documentation Screenshots - M4`**

- **M4.1**: Update README.md with screenshots
  - Add inventory list screenshot to Features section
  - Add add item form screenshot to Quick Start section
  - Verify markdown rendering
- **M4.2**: Update user-manual.md with screenshots
  - Add screenshots to all major sections (15+ screenshots total)
  - Write descriptive captions for each figure
  - Add alt text for accessibility
- **M4.3**: Update deployment-guide.md and development-testing-guide.md
  - Add deployment screenshots
  - Add testing screenshots
  - Add screenshot maintenance documentation to development guide
- **M4.4**: Final documentation polish
  - Review all screenshot placements
  - Verify all image links work
  - Optimize file sizes if needed
  - Add screenshot regeneration guide to development docs
- **M4.5**: Final testing and validation
  - Verify all documentation renders correctly with screenshots
  - Run complete test suite (unit + e2e)
  - Verify screenshot generation is reproducible
  - Update feature documentation (this file)

**Dependencies**: M1 → M2 → M3 → M4 (sequential)

**Implementation Notes:**
- Screenshot generation should be separate from regular e2e tests (use pytest markers)
- Initial implementation focuses on light mode; dark mode screenshots deferred
- Screenshot visual regression testing is out of scope; manual validation required
- CI/CD screenshot generation is optional and can be added after initial implementation
- Annotations (arrows, highlights) are optional for M1-M4; can be added later

## Progress

### Completed Milestones

(None yet - awaiting human approval to begin implementation)

## Implementation Status

**Status**: Planning phase - awaiting human approval

**Next Steps**:
1. Human review and approval of implementation plan
2. Begin Milestone 1: Screenshot Infrastructure & Test Data
