"""
E2E Tests for Duplicate Item Functionality

Tests the duplicate button feature on the edit page that allows creating
copies of existing items with new sequential JA IDs.
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.base_page import BasePage


class DuplicateItemPage(BasePage):
    """Page object for item duplication workflow"""

    def navigate_to_edit_page(self, ja_id):
        """Navigate to edit page for a specific item"""
        self.page.goto(f"{self.base_url}/inventory/edit/{ja_id}")
        self.page.wait_for_load_state("networkidle")

    def click_duplicate_button(self):
        """Click the duplicate item button"""
        self.page.locator("#duplicate-item-btn").click()
        self.page.wait_for_timeout(500)

    def is_duplicate_modal_visible(self):
        """Check if duplicate modal is shown"""
        modal = self.page.locator("#duplicateItemModal")
        return modal.is_visible()

    def get_duplicate_modal_ja_id(self):
        """Get the source JA ID shown in modal"""
        return self.page.locator("#duplicate-source-ja-id").inner_text()

    def get_duplicate_quantity_value(self):
        """Get current quantity value in modal"""
        return self.page.locator("#duplicate-quantity").input_value()

    def set_duplicate_quantity(self, quantity):
        """Set the quantity to duplicate"""
        self.page.locator("#duplicate-quantity").fill(str(quantity))
        self.page.wait_for_timeout(200)

    def get_preview_message(self):
        """Get the preview message showing JA ID range"""
        preview = self.page.locator("#duplicate-preview-message")
        if preview.is_visible():
            return preview.inner_text()
        return None

    def is_unsaved_changes_warning_visible(self):
        """Check if unsaved changes warning is shown"""
        warning = self.page.locator("#duplicate-unsaved-warning")
        return warning.is_visible()

    def select_save_changes_option(self):
        """Select the 'Save changes' radio option"""
        self.page.locator("input[name='unsaved-changes-action'][value='save']").check()

    def select_discard_changes_option(self):
        """Select the 'Discard changes' radio option"""
        self.page.locator("input[name='unsaved-changes-action'][value='discard']").check()

    def click_create_duplicates_button(self):
        """Click the create duplicates button in modal"""
        self.page.locator("#duplicate-create-btn").click()
        self.page.wait_for_load_state("networkidle")

    def modify_item_field(self, field_id, value):
        """Modify a field to create unsaved changes"""
        self.page.locator(f"#{field_id}").fill(value)

    def get_toast_message(self):
        """Get the toast notification message"""
        toast = self.page.locator(".toast-body").first
        if toast.is_visible(timeout=3000):
            return toast.inner_text()
        return None


@pytest.mark.e2e
def test_duplicate_button_visibility(page, live_server):
    """Test that duplicate button is visible on edit page"""
    # Add a test item
    from app.database import InventoryItem
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    item = InventoryItem(
        ja_id="JA000100",
        item_type="Bar",
        shape="Round",
        material="Steel",
        length=24.0,
        width=1.0,
        location="Storage A",
        notes="Test item for duplicate",
        active=True
    )
    service.add_item(item)

    # Navigate to edit page
    dup_page = DuplicateItemPage(page, live_server.url)
    dup_page.navigate_to_edit_page("JA000100")

    # Verify duplicate button is visible
    duplicate_btn = page.locator("#duplicate-item-btn")
    expect(duplicate_btn).to_be_visible()
    expect(duplicate_btn).to_contain_text("Duplicate")


@pytest.mark.e2e
def test_duplicate_modal_opens_and_shows_item_info(page, live_server):
    """Test that duplicate modal opens and displays source item information"""
    # Add a test item
    from app.database import InventoryItem
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    item = InventoryItem(
        ja_id="JA000101",
        item_type="Plate",
        shape="Rectangular",
        material="Aluminum",
        length=12.0,
        width=6.0,
        thickness=0.25,
        location="Shop Floor",
        notes="Modal test item",
        active=True
    )
    service.add_item(item)

    dup_page = DuplicateItemPage(page, live_server.url)
    dup_page.navigate_to_edit_page("JA000101")

    # Click duplicate button
    dup_page.click_duplicate_button()

    # Verify modal is visible
    assert dup_page.is_duplicate_modal_visible()

    # Verify source JA ID is shown
    assert dup_page.get_duplicate_modal_ja_id() == "JA000101"

    # Verify item details are shown in modal
    modal_content = page.locator("#duplicateItemModal .modal-body").inner_text()
    assert "Aluminum" in modal_content
    assert "Plate" in modal_content
    assert "Rectangular" in modal_content


@pytest.mark.e2e
def test_duplicate_single_item(page, live_server):
    """Test duplicating a single item (quantity=1)"""
    from app.database import InventoryItem
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    item = InventoryItem(
        ja_id="JA000102",
        item_type="Bar",
        shape="Square",
        material="Brass",
        length=36.0,
        width=0.5,
        location="Storage B",
        notes="Single duplicate test",
        active=True
    )
    service.add_item(item)

    dup_page = DuplicateItemPage(page, live_server.url)
    dup_page.navigate_to_edit_page("JA000102")

    # Open modal and verify default quantity is 1
    dup_page.click_duplicate_button()
    assert dup_page.get_duplicate_quantity_value() == "1"

    # Create duplicate
    dup_page.click_create_duplicates_button()

    # Verify success message
    toast_msg = dup_page.get_toast_message()
    assert toast_msg is not None
    assert "successfully" in toast_msg.lower()

    # Verify item was created in database
    all_items = service.get_all_items()
    brass_items = [i for i in all_items if i.material == "Brass" and i.location == "Storage B"]
    assert len(brass_items) == 2  # Original + duplicate

    # Verify duplicate has different JA ID but same properties
    original = service.get_item("JA000102")
    duplicate = [i for i in brass_items if i.ja_id != "JA000102"][0]

    assert duplicate.ja_id != original.ja_id
    assert duplicate.item_type == original.item_type
    assert duplicate.shape == original.shape
    assert duplicate.material == original.material
    assert duplicate.length == original.length
    assert duplicate.width == original.width
    assert duplicate.location == original.location
    assert duplicate.notes == original.notes


@pytest.mark.e2e
def test_duplicate_multiple_items(page, live_server):
    """Test duplicating multiple items with quantity=5"""
    from app.database import InventoryItem
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    item = InventoryItem(
        ja_id="JA000103",
        item_type="Threaded Rod",
        shape="Round",
        material="Stainless Steel",
        length=48.0,
        width=0.375,
        thread_series="UNC",
        thread_size="3/8-16",
        thread_handedness="Right",
        location="Hardware Bin",
        notes="Multiple duplicate test",
        active=True
    )
    service.add_item(item)

    dup_page = DuplicateItemPage(page, live_server.url)
    dup_page.navigate_to_edit_page("JA000103")

    # Open modal and set quantity to 5
    dup_page.click_duplicate_button()
    dup_page.set_duplicate_quantity(5)

    # Verify preview message shows JA ID range
    preview = dup_page.get_preview_message()
    assert preview is not None
    assert "5" in preview
    assert "JA" in preview

    # Create duplicates
    dup_page.click_create_duplicates_button()

    # Verify success message mentions 5 items
    toast_msg = dup_page.get_toast_message()
    assert "5" in toast_msg

    # Verify 5 duplicates were created
    all_items = service.get_all_items()
    stainless_items = [i for i in all_items if i.material == "Stainless Steel" and i.location == "Hardware Bin"]
    assert len(stainless_items) == 6  # Original + 5 duplicates

    # Verify all have different JA IDs but same properties
    original = service.get_item("JA000103")
    duplicates = [i for i in stainless_items if i.ja_id != "JA000103"]

    for dup_item in duplicates:
        assert dup_item.ja_id != original.ja_id
        assert dup_item.item_type == original.item_type
        assert dup_item.material == original.material
        assert dup_item.length == original.length
        assert dup_item.thread_series == original.thread_series
        assert dup_item.thread_size == original.thread_size


@pytest.mark.e2e
def test_duplicate_field_copying_comprehensive(page, live_server):
    """Test that all fields are copied accurately including optional fields"""
    from app.database import InventoryItem
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    item = InventoryItem(
        ja_id="JA000104",
        item_type="Plate",
        shape="Rectangular",
        material="Copper",
        length=24.0,
        width=12.0,
        thickness=0.0625,
        location="Materials Rack",
        sub_location="Shelf 5",
        notes="Comprehensive field copy test",
        purchase_location="Online Metals",
        vendor="Online Metals",
        vendor_part_number="CU110-24x12x0.0625",
        active=True
    )
    service.add_item(item)

    dup_page = DuplicateItemPage(page, live_server.url)
    dup_page.navigate_to_edit_page("JA000104")

    # Create duplicate
    dup_page.click_duplicate_button()
    dup_page.click_create_duplicates_button()

    # Get the duplicate item
    all_items = service.get_all_items()
    copper_items = [i for i in all_items if i.material == "Copper" and i.location == "Materials Rack"]
    duplicate = [i for i in copper_items if i.ja_id != "JA000104"][0]

    # Verify all fields copied
    original = service.get_item("JA000104")
    assert duplicate.item_type == original.item_type
    assert duplicate.shape == original.shape
    assert duplicate.material == original.material
    assert duplicate.length == original.length
    assert duplicate.width == original.width
    assert duplicate.thickness == original.thickness
    assert duplicate.location == original.location
    assert duplicate.sub_location == original.sub_location
    assert duplicate.notes == original.notes
    assert duplicate.purchase_location == original.purchase_location
    assert duplicate.vendor == original.vendor
    assert duplicate.vendor_part_number == original.vendor_part_number


@pytest.mark.e2e
def test_duplicate_photos_not_copied(page, live_server):
    """Test that photos are NOT copied to duplicated items"""
    from app.database import InventoryItem
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    # Create item with photos
    item = InventoryItem(
        ja_id="JA000105",
        item_type="Bar",
        material="Steel",
        length=18.0,
        location="Storage C",
        photos='["/static/uploads/photo1.jpg", "/static/uploads/photo2.jpg"]',
        active=True
    )
    service.add_item(item)

    dup_page = DuplicateItemPage(page, live_server.url)
    dup_page.navigate_to_edit_page("JA000105")

    # Create duplicate
    dup_page.click_duplicate_button()
    dup_page.click_create_duplicates_button()

    # Get the duplicate
    all_items = service.get_all_items()
    steel_items = [i for i in all_items if i.material == "Steel" and i.location == "Storage C"]
    duplicate = [i for i in steel_items if i.ja_id != "JA000105"][0]

    # Verify duplicate has no photos
    assert duplicate.photos is None or duplicate.photos == "" or duplicate.photos == "[]"


@pytest.mark.e2e
def test_duplicate_history_not_copied(page, live_server):
    """Test that item history is NOT copied to duplicated items"""
    from app.database import InventoryItem
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    # Create original item
    original = InventoryItem(
        ja_id="JA000106",
        item_type="Bar",
        material="Aluminum",
        length=48.0,
        location="Shop",
        active=True
    )
    service.add_item(original)

    # Shorten the original to create history
    service.shorten_item("JA000106", 24.0, "Cut in half")

    # Get the current active item (after shortening)
    current = service.get_item("JA000106")

    # Navigate to edit page
    dup_page = DuplicateItemPage(page, live_server.url)
    dup_page.navigate_to_edit_page("JA000106")

    # Create duplicate
    dup_page.click_duplicate_button()
    dup_page.click_create_duplicates_button()

    # Get the duplicate
    all_items = service.get_all_items()
    alu_items = [i for i in all_items if i.material == "Aluminum"]
    duplicate = [i for i in alu_items if i.ja_id not in ["JA000106"]][0]

    # Verify duplicate has no history (only one active row for its JA ID)
    dup_history = service.get_item_history(duplicate.ja_id)
    assert len(dup_history) == 1  # Only the duplicate itself, no history


@pytest.mark.e2e
def test_duplicate_with_unsaved_changes_save_option(page, live_server):
    """Test duplicating with unsaved changes and choosing 'save' option"""
    from app.database import InventoryItem
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    item = InventoryItem(
        ja_id="JA000107",
        item_type="Bar",
        material="Steel",
        length=36.0,
        location="Shop A",
        notes="Original notes",
        active=True
    )
    service.add_item(item)

    dup_page = DuplicateItemPage(page, live_server.url)
    dup_page.navigate_to_edit_page("JA000107")

    # Make changes to the form (unsaved)
    dup_page.modify_item_field("notes", "Modified notes - unsaved")

    # Open duplicate modal
    dup_page.click_duplicate_button()

    # Verify unsaved changes warning is shown
    assert dup_page.is_unsaved_changes_warning_visible()

    # Select 'save changes' option
    dup_page.select_save_changes_option()

    # Create duplicate
    dup_page.click_create_duplicates_button()

    # Verify original item was updated with new notes
    original = service.get_item("JA000107")
    assert original.notes == "Modified notes - unsaved"

    # Verify duplicate also has the updated notes
    all_items = service.get_all_items()
    steel_items = [i for i in all_items if i.material == "Steel" and i.location == "Shop A"]
    duplicate = [i for i in steel_items if i.ja_id != "JA000107"][0]
    assert duplicate.notes == "Modified notes - unsaved"


@pytest.mark.e2e
def test_duplicate_with_unsaved_changes_discard_option(page, live_server):
    """Test duplicating with unsaved changes and choosing 'discard' option"""
    from app.database import InventoryItem
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    item = InventoryItem(
        ja_id="JA000108",
        item_type="Bar",
        material="Brass",
        length=24.0,
        location="Shop B",
        notes="Original notes",
        active=True
    )
    service.add_item(item)

    dup_page = DuplicateItemPage(page, live_server.url)
    dup_page.navigate_to_edit_page("JA000108")

    # Make changes to the form (unsaved)
    dup_page.modify_item_field("notes", "Modified notes - will be discarded")

    # Open duplicate modal
    dup_page.click_duplicate_button()

    # Select 'discard changes' option
    dup_page.select_discard_changes_option()

    # Create duplicate
    dup_page.click_create_duplicates_button()

    # Verify original item still has original notes
    original = service.get_item("JA000108")
    assert original.notes == "Original notes"

    # Verify duplicate also has original notes (changes were discarded)
    all_items = service.get_all_items()
    brass_items = [i for i in all_items if i.material == "Brass" and i.location == "Shop B"]
    duplicate = [i for i in brass_items if i.ja_id != "JA000108"][0]
    assert duplicate.notes == "Original notes"


@pytest.mark.e2e
def test_duplicate_validation_limits(page, live_server):
    """Test that quantity validation enforces min=1, max=100"""
    from app.database import InventoryItem
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    item = InventoryItem(
        ja_id="JA000109",
        item_type="Bar",
        material="Steel",
        length=12.0,
        location="Storage",
        active=True
    )
    service.add_item(item)

    dup_page = DuplicateItemPage(page, live_server.url)
    dup_page.navigate_to_edit_page("JA000109")

    # Open modal
    dup_page.click_duplicate_button()

    quantity_input = page.locator("#duplicate-quantity")

    # Verify HTML5 validation attributes
    expect(quantity_input).to_have_attribute("min", "1")
    expect(quantity_input).to_have_attribute("max", "100")
    expect(quantity_input).to_have_attribute("type", "number")

    # Test valid values
    dup_page.set_duplicate_quantity(1)
    expect(quantity_input).to_have_value("1")

    dup_page.set_duplicate_quantity(50)
    expect(quantity_input).to_have_value("50")

    dup_page.set_duplicate_quantity(100)
    expect(quantity_input).to_have_value("100")


@pytest.mark.e2e
def test_duplicate_ja_id_sequence_from_existing(page, live_server):
    """Test that duplicate JA IDs continue from the highest existing JA ID"""
    from app.database import InventoryItem
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    # Add items to establish a baseline
    for i in range(110, 113):
        item = InventoryItem(
            ja_id=f"JA{i:06d}",
            item_type="Bar",
            material="Steel",
            length=12.0,
            location="Storage",
            active=True
        )
        service.add_item(item)

    dup_page = DuplicateItemPage(page, live_server.url)
    dup_page.navigate_to_edit_page("JA000112")

    # Create 3 duplicates
    dup_page.click_duplicate_button()
    dup_page.set_duplicate_quantity(3)

    # Check preview shows correct range
    preview = dup_page.get_preview_message()
    assert "JA000113" in preview
    assert "JA000115" in preview

    dup_page.click_create_duplicates_button()

    # Verify items were created with correct JA IDs
    assert service.get_item("JA000113") is not None
    assert service.get_item("JA000114") is not None
    assert service.get_item("JA000115") is not None
