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

    def _add_item_via_ui(self, page, add_page, item_data):
        """
        Add an inventory item via the UI.

        Args:
            page: Playwright page object
            add_page: AddItemPage object
            item_data: Item data dictionary
        """
        add_page.navigate()
        add_page.fill_basic_item_data(
            ja_id=item_data['ja_id'],
            item_type=item_data.get('type', 'Bar'),
            shape=item_data.get('shape', 'Round'),
            material=item_data['material']
        )

        # Fill dimensions
        if item_data.get('length') or item_data.get('width'):
            add_page.fill_dimensions(
                length=item_data.get('length', ''),
                width=item_data.get('width', ''),
                diameter=item_data.get('width', '')  # For round items
            )

        # Fill location
        if item_data.get('location'):
            add_page.fill_location_and_notes(
                location=item_data['location'],
                notes=item_data.get('notes', '')
            )

        # Submit
        add_page.submit_form()
        page.wait_for_timeout(500)  # Wait for submission

    def _load_inventory_data(self, page, live_server, items):
        """
        Load multiple inventory items via UI.

        Args:
            page: Playwright page object
            live_server: E2E test server
            items: List of item data dictionaries
        """
        add_page = AddItemPage(page, live_server.url)
        for item in items:
            self._add_item_via_ui(page, add_page, item)

    # ========================================================================
    # Milestone 2.1: Inventory and Search Screenshots
    # ========================================================================

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_inventory_list(self, page, live_server):
        """Generate inventory list screenshot for README and user manual"""
        # Load realistic test data
        items = get_inventory_items(count=12)  # Load all items for a full list
        self._load_inventory_data(page, live_server, items)

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
        self._load_inventory_data(page, live_server, items)

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
        self._load_inventory_data(page, live_server, items)

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
