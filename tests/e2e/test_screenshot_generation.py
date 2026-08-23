"""
E2E Tests for Documentation Screenshot Generation

This test suite generates screenshots for documentation using realistic test data.
Use pytest marker @pytest.mark.screenshot to run only screenshot tests.

Run with: pytest tests/e2e/test_screenshot_generation.py -m screenshot
"""

import re

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
from tests.e2e.waits import dismiss_material_suggestions, wait_for_modal_shown
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
        # wait_for_items_loaded() settles on the rendered table; the rows this
        # screenshot is of are in the DOM by then.

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

        # Perform a search for Bar items (guaranteed to have results)
        # Using item type instead of material to avoid taxonomy matching issues
        search_page.search_by_item_type("Bar")

        # Wait for results
        page.wait_for_selector("#results-table-container .table", state="visible", timeout=5000)
        # The table being visible means the results were rendered into it.
        expect(page.locator("#results-table-container .table tbody tr").first).to_be_visible()

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
            material="12L14"  # taxonomy entry; the form rejects anything else
        )
        # A material the taxonomy recognises opens the autocomplete, which then
        # overlays the Dimensions card. Close it before capturing.
        dismiss_material_suggestions(page)
        add_page.fill_dimensions(length="72", width="1.5")
        add_page.fill_location_and_notes(
            location="Metal Storage Rack A",
            notes="General purpose machining stock"
        )

        # Also fill sub_location which isn't in the helper
        page.fill("#sub_location", "Section 3, Shelf 2")

        # The form is server-rendered and every field above was filled through
        # Playwright, which waits for actionability, so it is already settled.

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
            material="6061-T6"  # taxonomy entry; the form rejects anything else
        )
        # As above: close the autocomplete so it does not cover the form.
        dismiss_material_suggestions(page)
        add_page.fill_location_and_notes(location="Metal Storage Rack A")

        # Set quantity to create multiple items
        page.fill("#quantity_to_create", "5")
        # updateBulkCreationInfo() runs synchronously on `input`; this is the
        # banner it writes, and it is what makes the screenshot worth taking.
        expect(page.locator("#bulk-creation-info")).to_be_visible()

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
        # The values are rendered by the server, but edit.html strips every
        # validation class 100ms after load and only then adds `needs-validation`
        # to the form -- a class the served HTML does not carry. Capturing before
        # that lands catches the form mid-restyle.
        expect(page.locator("#add-item-form")).to_have_class(re.compile(r"\bneeds-validation\b"))

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
    # Milestone 2.3: Photo Management Screenshots
    # ========================================================================

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_photo_upload_interface(self, page, live_server):
        """Generate photo upload interface screenshot"""
        # Create an item to upload photos to
        items = get_inventory_items(count=1)
        self._load_inventory_data(live_server, items)

        # Navigate to edit page where photos can be uploaded
        ja_id = items[0]['ja_id']
        page.goto(f"{live_server.url}/inventory/edit/{ja_id}")

        # Wait for photo manager to be visible
        page.wait_for_selector("#photo-manager-container", timeout=5000)

        # Scroll to the photo section. `behavior: 'instant'` means the scroll has
        # already happened when evaluate() returns -- there is no animation to
        # outlast.
        page.evaluate("document.querySelector('#photo-manager-container').scrollIntoView({behavior: 'instant', block: 'center'})")

        # Capture full page with photo upload section visible
        self.screenshot.capture_viewport(
            "user-manual/photo_upload.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#photo-manager-container",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print(f"✓ Generated screenshot: user-manual/photo_upload.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_photo_gallery(self, page, live_server):
        """Generate photo gallery screenshot with multiple photos"""
        from pathlib import Path

        # Create an item
        items = get_inventory_items(count=1)
        self._load_inventory_data(live_server, items)
        ja_id = items[0]['ja_id']

        # Navigate to edit page
        page.goto(f"{live_server.url}/inventory/edit/{ja_id}")
        page.wait_for_selector("#photo-manager-container", timeout=5000)

        # Upload multiple photos
        sample_images = [
            "tests/e2e/fixtures/images/steel_rod_sample.jpg",
            "tests/e2e/fixtures/images/aluminum_tube_sample.jpg",
            "tests/e2e/fixtures/images/brass_rod_sample.jpg",
        ]

        uploaded = 0
        for image_path in sample_images:
            if Path(image_path).exists():
                # Find the file input and upload
                file_input = page.locator(".photo-file-input")
                if file_input.count() > 0:
                    file_input.first.set_input_files(image_path)
                    # This is the edit page, so processSingleFile() awaits the
                    # upload POST before appending the card: one more card means
                    # one more completed upload.
                    expect(page.locator(".photo-card")).to_have_count(uploaded + 1)
                    uploaded += 1

        # Scroll to photo gallery section
        page.evaluate("document.querySelector('#photo-manager-container').scrollIntoView({behavior: 'instant', block: 'center'})")

        # Capture full page showing the photo gallery
        self.screenshot.capture_viewport(
            "user-manual/photo_gallery.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#photo-manager-container",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print(f"✓ Generated screenshot: user-manual/photo_gallery.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_photo_copy_workflow(self, page, live_server):
        """Generate photo copy/paste workflow screenshot with clipboard banner"""
        from pathlib import Path

        # Create two items - one with photos (source) and one without (target)
        items = get_inventory_items(count=2)
        self._load_inventory_data(live_server, items)

        # Upload photos to first item
        source_id = items[0]['ja_id']
        page.goto(f"{live_server.url}/inventory/edit/{source_id}")
        page.wait_for_selector("#photo-manager-container", timeout=5000)

        # Upload a photo
        sample_image = "tests/e2e/fixtures/images/steel_rod_sample.jpg"
        if Path(sample_image).exists():
            file_input = page.locator(".photo-file-input")
            if file_input.count() > 0:
                file_input.first.set_input_files(sample_image)
                expect(page.locator(".photo-card")).to_have_count(1)

        # Navigate to inventory list to use copy/paste
        page.goto(f"{live_server.url}/inventory")
        page.wait_for_selector("table.inventory-table", timeout=5000)

        # Select the source item and click "Copy Photos"
        # This will trigger the clipboard banner
        source_row = page.locator(f"tr:has-text('{source_id}')").first
        if source_row.count() > 0:
            checkbox = source_row.locator("input[type='checkbox']").first
            if checkbox.count() > 0:
                checkbox.check()
                expect(checkbox).to_be_checked()

                # Click options menu and copy photos
                options_btn = page.locator("#options-dropdown-btn").first
                if options_btn.count() > 0:
                    options_btn.click()

                    # Look for copy photos button
                    copy_btn = page.locator("button:has-text('Copy Photos')").first
                    if copy_btn.count() > 0:
                        expect(copy_btn).to_be_visible()
                        copy_btn.click()
                        # copyPhotosFromSelected() is synchronous and always ends
                        # in a toast; the banner below is what is being captured.
                        expect(page.locator(".alert.position-fixed").first).to_be_visible()

        # Check if the clipboard banner is visible (it should be after clicking Copy Photos)
        try:
            # Wait a short time for the banner to appear
            page.wait_for_selector("#photo-clipboard-banner:not(.d-none)", timeout=2000)

            # Capture the page with clipboard banner visible
            self.screenshot.capture_viewport(
                "user-manual/photo_copy_clipboard.png",
                viewport_size=(1920, 1080),
                wait_for_selector="#photo-clipboard-banner:not(.d-none)"
            )
            print(f"✓ Generated screenshot: user-manual/photo_copy_clipboard.png")
        except Exception as e:
            # Banner didn't appear - this feature may not be fully functional in the test environment
            # Skip this screenshot and continue
            print(f"Note: Photo clipboard banner did not appear, skipping screenshot: {e}")
            print("This is expected if the photo copy feature requires specific conditions.")

    # ========================================================================
    # Milestone 3.1: Batch Operation Screenshots
    # ========================================================================

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_move_items(self, page, live_server):
        """Generate move items interface screenshot"""
        # Load some test data so the move page has context
        items = get_inventory_items(count=5)
        self._load_inventory_data(live_server, items)

        # Navigate to move items page
        page.goto(f"{live_server.url}/inventory/move")

        # Wait for the page to load
        page.wait_for_selector("#batch-move-form", timeout=5000)

        # Add a JA ID to the form to show the interface in use
        ja_id = items[0]['ja_id']
        if page.locator("#barcode-input").count() > 0:
            page.fill("#barcode-input", ja_id)
            # fill() alone does not submit -- this shot is of the field holding
            # the value, which it does as soon as fill() returns.
            expect(page.locator("#barcode-input")).to_have_value(ja_id)

        # Capture the move items interface
        self.screenshot.capture_viewport(
            "user-manual/move_items.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#batch-move-form",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print(f"✓ Generated screenshot: user-manual/move_items.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_shorten_items(self, page, live_server):
        """Generate shorten items interface screenshot"""
        # Load test data - need some items to shorten
        items = get_inventory_items(count=3)
        self._load_inventory_data(live_server, items)

        # Navigate to shorten items page
        page.goto(f"{live_server.url}/inventory/shorten")

        # Wait for the form to load
        page.wait_for_selector("#shorten-form", timeout=5000)

        # Fill in an example JA ID to show the interface with data
        # Get the first item's JA ID
        ja_id = items[0]['ja_id']
        if page.locator("#ja_id").count() > 0:
            page.fill("#ja_id", ja_id)
            expect(page.locator("#ja_id")).to_have_value(ja_id)

        # Capture the shorten interface
        self.screenshot.capture_viewport(
            "user-manual/shorten_items.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#shorten-form",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print(f"✓ Generated screenshot: user-manual/shorten_items.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_label_printing(self, page, live_server):
        """Generate label printing modal screenshot"""
        # Load test data
        items = get_inventory_items(count=5)
        self._load_inventory_data(live_server, items)

        # Navigate to inventory list
        page.goto(f"{live_server.url}/inventory")
        page.wait_for_selector("table.inventory-table", timeout=5000)
        # count() below does not wait, so the rendered rows have to be
        # established before the selection is made against them.
        expect(page.locator("#inventory-table-body tr").first).to_be_visible()

        # Select some items (check a few checkboxes)
        checkboxes = page.locator("table.inventory-table input[type='checkbox']")
        if checkboxes.count() >= 2:
            checkboxes.nth(0).check()
            checkboxes.nth(1).check()
            expect(checkboxes.nth(1)).to_be_checked()

        # Click the options dropdown button
        options_btn = page.locator("#options-dropdown-btn")
        if options_btn.count() > 0:
            options_btn.click()

            # Click "Print Labels" button
            print_labels_btn = page.locator("#bulk-print-labels-btn")
            if print_labels_btn.count() > 0:
                expect(print_labels_btn).to_be_visible()
                print_labels_btn.click()
                # The modal wait just below is the readiness signal for this
                # click; capturing before it would catch a Bootstrap fade.

        # Wait for the label printing modal to appear
        try:
            page.wait_for_selector("#listBulkLabelPrintingModal.show", timeout=3000)
            # As above: wait out the fade, not just the class that starts it.
            wait_for_modal_shown(page, "listBulkLabelPrintingModal")

            # Capture the modal
            self.screenshot.capture_viewport(
                "user-manual/label_printing.png",
                viewport_size=(1920, 1080),
                wait_for_selector="#listBulkLabelPrintingModal.show",
                hide_selectors=[".toast-container"],
                full_page=False  # Just capture viewport since modal is centered
            )

            print(f"✓ Generated screenshot: user-manual/label_printing.png")
        except Exception as e:
            # Modal didn't appear - skip this screenshot
            print(f"Note: Label printing modal did not appear, skipping screenshot: {e}")
            print("This is expected if the feature requires specific configuration.")

    # ========================================================================
    # Milestone 3.2: History and Utility Screenshots
    # ========================================================================

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_history_view(self, page, live_server):
        """Generate item history view screenshot"""
        # Load test data
        items = get_inventory_items(count=1)
        self._load_inventory_data(live_server, items)
        ja_id = items[0]['ja_id']

        # Navigate to edit page
        page.goto(f"{live_server.url}/inventory/edit/{ja_id}")
        page.wait_for_selector(".btn-outline-warning", timeout=5000)

        # Click "View History" button
        history_btn = page.locator("button:has-text('View History')")
        if history_btn.count() > 0:
            history_btn.click()
            # The modal wait just below is this click's readiness signal.

        # Wait for history modal to appear
        try:
            page.wait_for_selector("#item-history-modal.show", timeout=3000)
            # `.show` goes on at the *start* of Bootstrap's fade, so capturing on
            # it catches the modal half-transparent -- which is what made this
            # screenshot differ from the committed one by a fifth of its pixels.
            # wait_for_modal_shown settles on full opacity and focus.
            wait_for_modal_shown(page, "item-history-modal")

            # Capture the history modal
            self.screenshot.capture_viewport(
                "user-manual/history_view.png",
                viewport_size=(1920, 1080),
                wait_for_selector="#item-history-modal.show",
                hide_selectors=[".toast-container"],
                full_page=False  # Just capture viewport since modal is centered
            )

            print(f"✓ Generated screenshot: user-manual/history_view.png")
        except Exception as e:
            # Modal didn't appear - might not have history data
            print(f"Note: History modal did not appear, skipping screenshot: {e}")
            print("This is expected if the item has no history records.")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_batch_operations(self, page, live_server):
        """Generate batch operations menu screenshot"""
        # Load test data
        items = get_inventory_items(count=5)
        self._load_inventory_data(live_server, items)

        # Navigate to inventory list
        page.goto(f"{live_server.url}/inventory")
        page.wait_for_selector("table.inventory-table", timeout=5000)
        expect(page.locator("#inventory-table-body tr").first).to_be_visible()

        # Select some items (check a few checkboxes)
        checkboxes = page.locator("table.inventory-table input[type='checkbox']")
        if checkboxes.count() >= 3:
            checkboxes.nth(0).check()
            checkboxes.nth(1).check()
            checkboxes.nth(2).check()
            expect(checkboxes.nth(2)).to_be_checked()

        # Click the "Options" button to show the dropdown menu
        options_btn = page.locator("button:has-text('Options')")
        if options_btn.count() > 0:
            options_btn.click()
            # This screenshot is of the open menu, so wait for it to be open --
            # Bootstrap toggles .show on the menu when it is.
            expect(page.locator(".dropdown-menu.show")).to_be_visible()

            # Capture the page with the options menu open
            self.screenshot.capture_viewport(
                "user-manual/batch_operations_menu.png",
                viewport_size=(1920, 1080),
                hide_selectors=[".toast-container"],
                full_page=False  # Just capture viewport to show the dropdown
            )

            print(f"✓ Generated screenshot: user-manual/batch_operations_menu.png")
        else:
            print("Note: Options button not found, skipping batch operations screenshot")

    # ========================================================================
    # Product Catalog Screenshots
    # ========================================================================

    def _seed_catalog(self, live_server):
        """Seed the catalog the six catalog screenshots share.

        Seeded through the service layer rather than the Add Product form --
        the form costs about three seconds per product and these pixels are
        identical either way (add_test_products' own docstring says so).

        Two things here are load-bearing and easy to undo by accident:

        - **The backdating.** create_product stamps every count with
          ``datetime.now()``, so an unbackdated capture reads "counted today"
          against every row -- picturing the quantity-age feature at the one
          value where it looks pointless. The manual describes "counted 8
          months ago" and "Flagged low 3 months ago"; these dates are what put
          those strings on the screen.
        - **The capacitor's outstanding purchase.** The reorder list is
          *only* the effectively-low products, and "on the way" is a status on
          those rows. An outstanding order against a product that is not low
          never appears there at all, so the order that makes the "on the way"
          row has to sit on a product that is also below its threshold.

        Returns:
            The seeded products keyed by short name -- ``resistor``,
            ``capacitor``, ``opamp``, ``bolt``, ``threadlocker``, ``psu`` and
            ``kit`` -- for the captures that need to address one directly.
        """
        from datetime import datetime, timedelta
        from app.catalog_service import CatalogService

        resistor, capacitor, opamp, bolt, threadlocker, psu, kit = live_server.add_test_products([
            {
                'description': 'Carbon film resistor, 10k 1/4W',
                'manufacturer': 'Yageo',
                'manufacturer_part_number': 'CF14JT10K0',
                'category_path': 'electronics/passives/resistors',
                'tags': ['surplus'],
                'location': 'Parts Cabinet',
                'sub_location': 'Drawer 3',
                'quantity': 240,
                'reorder_threshold': 50,
                'identifiers': [
                    {'id_type': 'MPN', 'value': 'CF14JT10K0'},
                    {'id_type': 'GTIN', 'value': '012345678905'},
                ],
            },
            {
                'description': 'Ceramic capacitor, 100nF 50V X7R',
                'manufacturer': 'Kemet',
                'manufacturer_part_number': 'C0805C104K5RAC',
                'category_path': 'electronics/passives/capacitors',
                'tags': ['rohs'],
                'location': 'Parts Cabinet',
                'sub_location': 'Drawer 4',
                'quantity': 12,
                'reorder_threshold': 25,
            },
            {
                'description': 'LM358 dual op-amp, DIP-8',
                'manufacturer': 'Texas Instruments',
                'manufacturer_part_number': 'LM358N',
                'category_path': 'electronics/active',
                'tags': ['surplus', 'rohs'],
                'location': 'Parts Cabinet',
                'sub_location': 'Drawer 1',
                'identifiers': [{'id_type': 'MPN', 'value': 'LM358N'}],
            },
            {
                'description': 'M4x16 hex bolt, stainless',
                'category_path': 'hardware/fasteners',
                'tags': ['surplus'],
                'location': 'Shop Wall',
                'sub_location': 'Bin 12',
                'quantity': 0,
                'reorder_threshold': 10,
            },
            {
                'description': 'Blue thread locker, 10ml',
                'manufacturer': 'Loctite',
                'manufacturer_part_number': '243',
                'category_path': 'chemicals/adhesives',
                'location': 'Shop Wall',
                'sub_location': 'Shelf 2',
                'quantity': 3,
                'reorder_threshold': 2,
                'notes': 'Medium strength -- the one for anything that comes apart again.',
                'specifications': [
                    {'name': 'Strength', 'value': 'Medium'},
                    {'name': 'Volume', 'value': '10 ml'},
                    {'name': 'Temperature range', 'value': '-55 to 150 C'},
                ],
                'identifiers': [
                    {'id_type': 'MPN', 'value': '243'},
                    {'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'},
                ],
            },
            {
                'description': '24V 5A switching PSU',
                'manufacturer': 'Mean Well',
                'manufacturer_part_number': 'LRS-120-24',
                'category_path': 'electronics/power',
                'location': 'Shop Wall',
                'sub_location': 'Shelf 1',
                'identifiers': [
                    {'id_type': 'DISTRIBUTOR', 'value': '1866-3789-ND', 'vendor': 'DigiKey'},
                ],
            },
            {
                # Filed at electronics/passives rather than under one of its
                # children, and that is the point. category_tree() lists only
                # the categories that hold a product *directly*, so an
                # intermediate category nobody has filed anything in does not
                # render at all -- without this row the tree shows
                # `capacitors` and `resistors` with no parent above them, and
                # "renaming carries everything beneath it" has nothing to
                # point at.
                'description': 'Resistor assortment kit, 1/4W E12',
                'category_path': 'electronics/passives',
                'tags': ['surplus'],
                'location': 'Parts Cabinet',
                'sub_location': 'Drawer 3',
                'quantity': 1,
            },
        ])

        service = CatalogService(live_server.storage)

        # The hand-set flag, and its age -- unreachable through the service,
        # which always writes datetime.now().
        service.set_stock_status(opamp.id, 'low')
        live_server.backdate_product(
            opamp.id, stock_status_updated_at=datetime.now() - timedelta(days=91)
        )

        # Counts of different ages, so the age line reads as evidence with a
        # date on it rather than as "today" repeated six times.
        live_server.backdate_product(
            resistor.id, quantity_updated_at=datetime.now() - timedelta(days=243)
        )
        live_server.backdate_product(
            capacitor.id, quantity_updated_at=datetime.now() - timedelta(days=61)
        )
        live_server.backdate_product(
            bolt.id, quantity_updated_at=datetime.now() - timedelta(days=17)
        )
        # The detail capture's subject. Without this it reads "counted just
        # now", which is the one value that makes the age line look pointless.
        live_server.backdate_product(
            threadlocker.id, quantity_updated_at=datetime.now() - timedelta(days=34)
        )
        live_server.backdate_product(
            kit.id, quantity_updated_at=datetime.now() - timedelta(days=128)
        )

        # Thread locker: a received purchase and an outstanding one, so the
        # detail page shows a history with a latest price rather than a single
        # row.
        service.record_purchase(
            product_id=threadlocker.id,
            vendor='Amazon',
            vendor_item_id='B0ABCDEFGH',
            listing_title='Loctite 243 Medium Strength Threadlocker, 10ml',
            order_date=datetime.now() - timedelta(days=400),
            received_date=datetime.now() - timedelta(days=393),
            quantity=2,
            unit_price=Decimal('8.47'),
            order_reference='114-2298471-3390612',
        )
        service.record_purchase(
            product_id=threadlocker.id,
            vendor='Amazon',
            vendor_item_id='B0ABCDEFGH',
            listing_title='Loctite 243 Medium Strength Threadlocker, 10ml',
            order_date=datetime.now() - timedelta(days=6),
            quantity=1,
            unit_price=Decimal('9.12'),
            order_reference='114-7781203-9948217',
        )

        # See the docstring: this is what puts an "on the way" row on the
        # reorder list. The capacitor is below its threshold, so it is on the
        # list to be marked in the first place.
        service.record_purchase(
            product_id=capacitor.id,
            vendor='DigiKey',
            listing_title='Kemet C0805C104K5RAC, 100 pcs',
            order_date=datetime.now() - timedelta(days=3),
            quantity=100,
            unit_price=Decimal('0.11'),
            order_reference='89234117',
        )

        service.record_purchase(
            product_id=psu.id,
            vendor='DigiKey',
            vendor_item_id='1866-3789-ND',
            listing_title='Mean Well LRS-120-24 switching power supply',
            order_date=datetime.now() - timedelta(days=210),
            received_date=datetime.now() - timedelta(days=203),
            quantity=1,
            unit_price=Decimal('24.60'),
            order_reference='89011455',
        )

        return {
            'resistor': resistor,
            'capacitor': capacitor,
            'opamp': opamp,
            'bolt': bolt,
            'threadlocker': threadlocker,
            'psu': psu,
            'kit': kit,
        }

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_product_search(self, page, live_server):
        """Generate the product list screenshot for the manual and the README"""
        self._seed_catalog(live_server)

        page.goto(f"{live_server.url}/products")
        expect(page.locator("#product-table tbody tr").first).to_be_visible()

        self.screenshot.capture_viewport(
            "user-manual/product_search.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#product-table",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print("✓ Generated screenshot: user-manual/product_search.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_product_detail(self, page, live_server):
        """Generate the product detail screenshot -- what it is, what it cost"""
        products = self._seed_catalog(live_server)

        page.goto(f"{live_server.url}/products/{products['threadlocker'].id}")
        expect(page.locator("#stock-card")).to_be_visible()
        expect(page.locator("#identifier-list")).to_be_visible()

        self.screenshot.capture_viewport(
            "user-manual/product_detail.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#identifier-list",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print("✓ Generated screenshot: user-manual/product_detail.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_product_add_form(self, page, live_server):
        """Generate the Add Product form screenshot"""
        # Seeded first on purpose: the location and sub-location fields
        # autocomplete from what already exists, and an empty database makes
        # that invisible.
        self._seed_catalog(live_server)

        page.goto(f"{live_server.url}/products/new")
        expect(page.locator("#product-form")).to_be_visible()

        self.screenshot.capture_viewport(
            "user-manual/product_add_form.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#product-form",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print("✓ Generated screenshot: user-manual/product_add_form.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_order_capture(self, page, live_server):
        """Generate the order capture screenshot"""
        page.goto(f"{live_server.url}/products/capture")
        expect(page.locator("#capture-form")).to_be_visible()

        # #bookmarklet-http-warning is deliberately NOT hidden. The test server
        # runs over plain HTTP so the page renders its HTTPS warning, and the
        # manual spends a block quote on exactly that warning -- hiding it would
        # picture a state the manual then explains.
        self.screenshot.capture_viewport(
            "user-manual/order_capture.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#capture-form",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print("✓ Generated screenshot: user-manual/order_capture.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_digikey_order_review(self, page, live_server):
        """Generate the DigiKey order review screenshot (feature 024).

        DigiKey is the same loopback fake the DigiKey e2e tests use, so the
        picture is of the real page reading a real recorded response.
        """
        from tests.e2e.test_digikey_order import (
            SALES_ORDER, _DigiKeyHandler, digikey_fake_server,
        )

        with digikey_fake_server(live_server):
            page.goto(f"{live_server.url}/products/digikey/orders")
            page.fill("#sales_order_number", SALES_ORDER)
            page.click("#review-order")
            expect(page.locator(".order-line")).to_have_count(2)

            self.screenshot.capture_viewport(
                "user-manual/digikey_order_review.png",
                viewport_size=(1920, 1080),
                wait_for_selector="#order-lines",
                hide_selectors=[".toast-container"],
                full_page=True
            )

        print("✓ Generated screenshot: user-manual/digikey_order_review.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_digikey_order(self, page, live_server):
        """Generate the captured DigiKey order screenshot, part-way received."""
        from tests.e2e.test_digikey_order import SALES_ORDER, digikey_fake_server

        with digikey_fake_server(live_server):
            page.goto(f"{live_server.url}/products/digikey/orders")
            page.fill("#sales_order_number", SALES_ORDER)
            page.click("#review-order")
            expect(page.locator(".order-line")).to_have_count(2)
            page.click("#confirm-capture")
            expect(page.locator("#order-progress")).to_contain_text("2 of 2")

            # One received, so the picture shows both states rather than a
            # column of identical rows.
            page.locator('.order-line[data-part="1866-3027-ND"] .receive-line').click()
            page.click('button[type="submit"]')
            page.goto(f"{live_server.url}/products/digikey/orders/{SALES_ORDER}")
            expect(page.locator("#order-progress")).to_contain_text("1 of 2")

            self.screenshot.capture_viewport(
                "user-manual/digikey_order.png",
                viewport_size=(1920, 1080),
                wait_for_selector="#order-lines",
                hide_selectors=[".toast-container"],
                full_page=True
            )

        print("✓ Generated screenshot: user-manual/digikey_order.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_reorder_list(self, page, live_server):
        """Generate the reorder list screenshot"""
        self._seed_catalog(live_server)

        page.goto(f"{live_server.url}/products/reorder")
        # #nothing-to-reorder renders instead when nothing qualifies, and a
        # screenshot of an empty reorder list documents nothing. Asserting the
        # table is here fails loudly if the seed ever stops qualifying.
        expect(page.locator("#reorder-table")).to_be_visible()
        expect(page.locator("#reorder-table tbody tr.reorder-row").first).to_be_visible()

        self.screenshot.capture_viewport(
            "user-manual/reorder_list.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#reorder-table",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print("✓ Generated screenshot: user-manual/reorder_list.png")

    @pytest.mark.screenshot
    @pytest.mark.e2e
    def test_screenshot_category_tree(self, page, live_server):
        """Generate the category tree screenshot"""
        # The seed's electronics/passives/resistors path is what makes the
        # three-level nesting -- and so the "renaming carries everything
        # beneath it" rule -- legible.
        self._seed_catalog(live_server)

        page.goto(f"{live_server.url}/products/categories")
        expect(page.locator("#category-tree")).to_be_visible()

        self.screenshot.capture_viewport(
            "user-manual/category_tree.png",
            viewport_size=(1920, 1080),
            wait_for_selector="#category-tree",
            hide_selectors=[".toast-container"],
            full_page=True
        )

        print("✓ Generated screenshot: user-manual/category_tree.png")

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
