"""
E2E Tests for Documentation Screenshot Generation

This test suite generates screenshots for documentation using realistic test data.
Use pytest marker @pytest.mark.screenshot to run only screenshot tests.

Run with: pytest tests/e2e/test_screenshot_generation.py -m screenshot
"""

import pytest
from playwright.sync_api import expect
from pathlib import Path
from sqlalchemy.orm import sessionmaker
from decimal import Decimal

from tests.e2e.screenshot_generator import ScreenshotGenerator
from tests.e2e.fixtures.screenshot_data import (
    get_inventory_items,
    get_items_with_photos,
    SCREENSHOT_INVENTORY_DATA
)
from tests.e2e.pages.inventory_list_page import InventoryListPage
from tests.e2e.pages.add_item_page import AddItemPage
from tests.e2e.pages.search_page import SearchPage
from app.database import InventoryItem
from app.models import ItemType, ItemShape, Dimensions, Thread, ThreadSeries, ThreadHandedness


class TestDocumentationScreenshots:
    """Generate all documentation screenshots with realistic data"""

    @pytest.fixture(autouse=True)
    def setup_screenshot_generator(self, page):
        """Initialize screenshot generator for all tests"""
        self.screenshot = ScreenshotGenerator(page)
        yield
        # Save metadata after each test
        if self.screenshot.get_screenshot_count() > 0:
            self.screenshot.save_metadata()

    def _create_inventory_item_in_db(self, session, item_data):
        """
        Helper to create an inventory item directly in the database.

        Args:
            session: SQLAlchemy session
            item_data: Item data dictionary
        """
        from datetime import datetime

        # Parse purchase_date if it's a string
        purchase_date = None
        if item_data.get('purchase_date'):
            try:
                purchase_date = datetime.strptime(item_data['purchase_date'], '%Y-%m-%d')
            except:
                purchase_date = None

        # Create inventory item using correct field names
        item = InventoryItem(
            ja_id=item_data['ja_id'],
            item_type=item_data.get('type', 'Bar'),  # Use item_type, not type_value
            shape=item_data.get('shape', 'Round'),    # Use shape, not shape_value
            material=item_data.get('material', ''),
            length=Decimal(item_data['length']) if item_data.get('length') else None,
            width=Decimal(item_data['width']) if item_data.get('width') else None,
            thickness=Decimal(item_data['thickness']) if item_data.get('thickness') else None,
            wall_thickness=Decimal(item_data['wall_thickness']) if item_data.get('wall_thickness') else None,
            location=item_data.get('location', ''),
            sub_location=item_data.get('sub_location', ''),
            notes=item_data.get('notes', ''),
            purchase_date=purchase_date,
            purchase_price=Decimal(item_data['purchase_price']) if item_data.get('purchase_price') else None,
            purchase_location=item_data.get('purchase_location', ''),
            vendor=item_data.get('vendor', ''),
            vendor_part=item_data.get('part_number', ''),  # Note: vendor_part in DB
            active=item_data.get('active', 'yes') == 'yes',
            thread_series=item_data.get('thread_series'),
            thread_size=item_data.get('thread_size'),
            thread_handedness=item_data.get('thread_handedness')
        )

        session.add(item)
        return item

    def _load_inventory_data(self, live_server, items):
        """
        Load multiple inventory items directly into the database.

        Args:
            live_server: E2E test server
            items: List of item data dictionaries
        """
        if not hasattr(live_server, 'engine'):
            raise RuntimeError("live_server does not have engine attribute")

        Session = sessionmaker(bind=live_server.engine)
        session = Session()
        try:
            for item in items:
                self._create_inventory_item_in_db(session, item)
            session.commit()
            print(f"✓ Loaded {len(items)} items into database")
        except Exception as e:
            session.rollback()
            raise RuntimeError(f"Failed to load inventory data: {e}")
        finally:
            session.close()

    # ========================================================================
    # Milestone 2.1: Inventory and Search Screenshots
    # ========================================================================

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_inventory_list(self, page, live_server):
        """Generate inventory list screenshot for README and user manual"""
        # Load realistic test data
        items = get_inventory_items(count=12)  # Load all items for a full list
        self._load_inventory_data(live_server, items)

        # Navigate to inventory list
        list_page = InventoryListPage(page, live_server.url)
        list_page.navigate()

        # Wait for table to load
        list_page.wait_for_items_loaded()
        page.wait_for_timeout(1000)  # Extra time for any animations

        # Capture screenshot for README
        self.screenshot.capture_viewport(
            "readme/inventory_list.png",
            viewport_size=(1920, 1080),
            wait_for_selector="table.inventory-table",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print(f"✓ Generated screenshot: readme/inventory_list.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_search_form(self, page, live_server):
        """Generate search form screenshot"""
        # Load some test data first so the page isn't empty
        items = get_inventory_items(count=5)
        self._load_inventory_data(live_server, items)

        # Navigate to search page
        search_page = SearchPage(page, live_server.url)
        search_page.navigate()

        # Wait for form to be visible
        page.wait_for_selector("#advanced-search-form", timeout=5000)
        page.wait_for_timeout(500)

        # Fill in some example search criteria (but don't submit)
        # This makes the screenshot more informative
        page.fill("#material", "Aluminum")
        page.fill("#length_min", "24")
        page.fill("#length_max", "72")

        # Capture screenshot
        self.screenshot.capture_viewport(
            "user-manual/search_form.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#advanced-search-form",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print(f"✓ Generated screenshot: user-manual/search_form.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_search_results(self, page, live_server):
        """Generate search results screenshot"""
        # Load test data
        items = get_inventory_items()
        self._load_inventory_data(live_server, items)

        # Navigate to search page
        search_page = SearchPage(page, live_server.url)
        search_page.navigate()

        # Perform a search for Aluminum items
        page.fill("#material", "Aluminum")
        page.click("button[type='submit']")

        # Wait for results
        page.wait_for_selector("#results-table-container .table", timeout=5000)
        page.wait_for_timeout(1000)

        # Capture screenshot
        self.screenshot.capture_viewport(
            "user-manual/search_results.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#results-table-container .table",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print(f"✓ Generated screenshot: user-manual/search_results.png")

    # ========================================================================
    # Milestone 2.2: Add/Edit Item Screenshots
    # ========================================================================

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_add_item_form(self, page, live_server):
        """Generate add item form screenshot with all fields visible"""
        # Navigate to add item page
        add_page = AddItemPage(page, live_server.url)
        add_page.navigate()

        # Fill in form with realistic data using page object (but don't submit)
        add_page.fill_basic_item_data(
            ja_id="JA000201",
            item_type="Bar",  # Use actual enum values
            shape="Round",
            material="Steel - 1018 Cold Rolled"
        )
        add_page.fill_dimensions(length="72", width="1.5")
        add_page.fill_location_and_notes(
            location="Metal Storage Rack A",
            notes="General purpose machining stock"
        )

        # Also fill sub_location which isn't in the helper
        page.fill("#sub_location", "Section 3, Shelf 2")

        # Wait for form to be fully rendered
        page.wait_for_timeout(500)

        # Capture screenshot
        self.screenshot.capture_viewport(
            "user-manual/add_item_form.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#add-item-form",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print(f"✓ Generated screenshot: user-manual/add_item_form.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_bulk_creation_preview(self, page, live_server):
        """Generate bulk creation preview screenshot"""
        add_page = AddItemPage(page, live_server.url)
        add_page.navigate()

        # Fill basic data using page object
        add_page.fill_basic_item_data(
            ja_id="JA000300",
            item_type="Bar",
            shape="Square",
            material="Aluminum - 6061-T651"
        )
        add_page.fill_location_and_notes(location="Metal Storage Rack A")

        # Set quantity to create multiple items
        page.fill("#quantity_to_create", "5")
        page.wait_for_timeout(1000)  # Wait for any JS updates

        # Capture the quantity section of the form
        # The element might have a different ID/class, so let's just capture the form section
        try:
            # Try to find a preview element first
            if page.locator("#quantity-preview").count() > 0:
                self.screenshot.capture_element(
                    "#quantity-preview",
                    "user-manual/bulk_creation_preview.png",
                    padding=20
                )
            else:
                # Fall back to capturing the quantity input area
                self.screenshot.capture_element(
                    "#quantity_to_create",
                    "user-manual/bulk_creation_preview.png",
                    padding=40
                )
        except Exception as e:
            print(f"Warning: Could not capture bulk creation preview: {e}")
            # Skip this screenshot if element not found
            return

        print(f"✓ Generated screenshot: user-manual/bulk_creation_preview.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_edit_item_form(self, page, live_server):
        """Generate edit item form screenshot with populated data"""
        # First create an item to edit
        items = get_inventory_items(count=1)
        self._load_inventory_data(live_server, items)

        # Navigate to edit page
        ja_id = items[0]['ja_id']
        page.goto(f"{live_server.url}/inventory/edit/{ja_id}")

        # Wait for form to load with data
        page.wait_for_selector("#add-item-form", timeout=5000)
        page.wait_for_timeout(1000)

        # Capture screenshot
        self.screenshot.capture_viewport(
            "user-manual/edit_item_form.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#add-item-form",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print(f"✓ Generated screenshot: user-manual/edit_item_form.png")

    # ========================================================================
    # Helper Tests for Debugging (not in config, but useful)
    # ========================================================================

    @pytest.mark.screenshot
    @pytest.mark.e2e
    @pytest.mark.skip(reason="Debug helper - run manually if needed")
    def test_screenshot_metadata_summary(self):
        """Print summary of what screenshots were generated"""
        metadata = self.screenshot.get_metadata()
        print("\n" + "=" * 60)
        print("Screenshot Generation Summary")
        print("=" * 60)
        print(f"Total screenshots generated: {len(metadata['screenshots'])}")
        print(f"Generated at: {metadata['generated_at']}")
        print("\nScreenshots:")
        for screenshot in metadata['screenshots']:
            print(f"  - {screenshot['filename']} ({screenshot['capture_type']})")
        print("=" * 60)
