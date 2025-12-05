"""
E2E Tests for Bulk Item Creation

Tests the "Quantity to Create" feature that allows creating multiple identical
items with sequential JA IDs in a single form submission.
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.base_page import BasePage


class BulkCreationPage(BasePage):
    """Page object for bulk item creation workflow"""

    def navigate_to_add_page(self):
        """Navigate to add inventory page"""
        self.page.goto(f"{self.base_url}/inventory/add")
        self.page.wait_for_load_state("networkidle")

    def fill_item_details(self, item_data):
        """Fill in item details on the add form"""
        if 'item_type' in item_data:
            self.page.locator("#item_type").select_option(item_data['item_type'])
        if 'shape' in item_data:
            self.page.locator("#shape").select_option(item_data['shape'])
        if 'material' in item_data:
            self.page.locator("#material").fill(item_data['material'])
        if 'length' in item_data:
            self.page.locator("#length").fill(str(item_data['length']))
        if 'width' in item_data:
            self.page.locator("#width").fill(str(item_data['width']))
        if 'thickness' in item_data:
            self.page.locator("#thickness").fill(str(item_data['thickness']))
        if 'location' in item_data:
            self.page.locator("#location").fill(item_data['location'])
        if 'notes' in item_data:
            self.page.locator("#notes").fill(item_data['notes'])

    def set_quantity_to_create(self, quantity):
        """Set the quantity to create field"""
        self.page.locator("#quantity_to_create").fill(str(quantity))
        self.page.wait_for_timeout(200)  # Allow preview update

    def get_bulk_creation_info_text(self):
        """Get the bulk creation info message"""
        info_div = self.page.locator("#bulk-creation-info")
        if info_div.is_visible():
            return self.page.locator("#bulk-creation-message").inner_text()
        return None

    def submit_form(self):
        """Submit the add item form"""
        self.page.locator("#submit-btn").click()
        # For bulk creation (AJAX), wait a moment for the request to complete
        self.page.wait_for_timeout(2000)

    def get_success_message(self):
        """Get success message text"""
        alert = self.page.locator(".alert-success").first
        expect(alert).to_be_visible()
        return alert.inner_text()

    def is_bulk_label_modal_visible(self):
        """Check if bulk label printing modal is shown"""
        modal = self.page.locator("#bulkLabelPrintingModal")
        return modal.is_visible()

    def get_modal_ja_ids(self):
        """Get the list of JA IDs shown in the modal"""
        ja_ids = []
        items = self.page.locator("#bulk-label-items-list .list-group-item")
        count = items.count()
        for i in range(count):
            text = items.nth(i).inner_text()
            # Extract JA ID from text like "JA000001 - Description"
            ja_id = text.split()[0]
            ja_ids.append(ja_id)
        return ja_ids

    def close_modal(self):
        """Close the bulk label printing modal"""
        self.page.locator("#bulk-label-modal-close-btn").click()
        self.page.wait_for_timeout(500)


@pytest.mark.e2e
def test_single_item_creation_quantity_one(page, live_server):
    """Test creating a single item with quantity_to_create=1 (default behavior)"""
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    # Fill in item details
    item_data = {
        'item_type': 'Bar',
        'shape': 'Round',
        'material': 'Aluminum',
        'length': '24',
        'width': '1',
        'location': 'Storage A',
        'notes': 'Single item test'
    }
    bulk_page.fill_item_details(item_data)

    # Verify quantity defaults to 1
    quantity_input = page.locator("#quantity_to_create")
    expect(quantity_input).to_have_value("1")

    # No bulk info should be shown for quantity=1
    info_text = bulk_page.get_bulk_creation_info_text()
    assert info_text is None

    # Submit form
    bulk_page.submit_form()

    # Should see standard success message (not bulk modal)
    success_text = bulk_page.get_success_message()
    assert "successfully" in success_text.lower()

    # Verify the item was created with correct JA ID
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)
    items = service.get_all_items()

    # Find the item we just created
    created_item = None
    for item in items:
        if item.material == 'Aluminum' and item.location == 'Storage A':
            created_item = item
            break

    assert created_item is not None
    assert created_item.length == 24.0
    assert created_item.width == 1.0
    assert created_item.notes == 'Single item test'


@pytest.mark.e2e
def test_bulk_creation_five_items(page, live_server):
    """Test creating 5 identical items with sequential JA IDs"""
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    # Fill in item details
    item_data = {
        'item_type': 'Plate',
        'shape': 'Rectangular',
        'material': 'Steel',
        'length': '12',
        'width': '6',
        'thickness': '0.25',
        'location': 'Shop Floor',
        'notes': 'Bulk creation test - 5 items'
    }
    bulk_page.fill_item_details(item_data)

    # Set quantity to 5
    bulk_page.set_quantity_to_create(5)

    # Verify bulk creation info is shown
    info_text = bulk_page.get_bulk_creation_info_text()
    assert info_text is not None
    assert "5 items" in info_text
    assert "JA" in info_text  # Should show JA ID range

    # Submit form
    bulk_page.submit_form()

    # Should show bulk label printing modal
    assert bulk_page.is_bulk_label_modal_visible()

    # Get the JA IDs from modal
    ja_ids = bulk_page.get_modal_ja_ids()
    assert len(ja_ids) == 5

    # Verify JA IDs are sequential
    for i in range(len(ja_ids) - 1):
        current_num = int(ja_ids[i].replace('JA', ''))
        next_num = int(ja_ids[i + 1].replace('JA', ''))
        assert next_num == current_num + 1, f"JA IDs not sequential: {ja_ids[i]} -> {ja_ids[i + 1]}"

    # Close modal
    bulk_page.close_modal()

    # Verify all items were created in database
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    created_items = []
    for ja_id in ja_ids:
        item = service.get_item(ja_id)
        assert item is not None, f"Item {ja_id} not found in database"
        created_items.append(item)

    # Verify all items have identical properties (except JA ID)
    for item in created_items:
        assert item.item_type == 'Plate'
        assert item.shape == 'Rectangular'
        assert item.material == 'Steel'
        assert item.length == 12.0
        assert item.width == 6.0
        assert item.thickness == 0.25
        assert item.location == 'Shop Floor'
        assert item.notes == 'Bulk creation test - 5 items'
        assert item.active is True


@pytest.mark.e2e
def test_bulk_creation_field_copying_accuracy(page, live_server):
    """Test that all fields are copied accurately to each bulk-created item"""
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    # Fill in comprehensive item details including optional fields
    item_data = {
        'item_type': 'Bar',
        'shape': 'Hexagonal',
        'material': 'Brass',
        'length': '36',
        'width': '0.5',
        'location': 'Storage B',
        'notes': 'Comprehensive field test'
    }
    bulk_page.fill_item_details(item_data)

    # Add optional fields
    page.locator("#sub_location").fill("Shelf 3")
    page.locator("#purchase_location").fill("McMaster-Carr")
    page.locator("#vendor").fill("McMaster")
    page.locator("#vendor_part_number").fill("8974K123")

    # Set quantity to 3
    bulk_page.set_quantity_to_create(3)

    # Submit form
    bulk_page.submit_form()

    # Get JA IDs from modal
    ja_ids = bulk_page.get_modal_ja_ids()
    assert len(ja_ids) == 3

    bulk_page.close_modal()

    # Verify all fields are identical across all items
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    for ja_id in ja_ids:
        item = service.get_item(ja_id)
        assert item.item_type == 'Bar'
        assert item.shape == 'Hexagonal'
        assert item.material == 'Brass'
        assert item.length == 36.0
        assert item.width == 0.5
        assert item.location == 'Storage B'
        assert item.sub_location == 'Shelf 3'
        assert item.notes == 'Comprehensive field test'
        assert item.purchase_location == 'McMaster-Carr'
        assert item.vendor == 'McMaster'
        assert item.vendor_part_number == '8974K123'


@pytest.mark.e2e
def test_bulk_creation_validation_limits(page, live_server):
    """Test that quantity validation enforces min=1, max=100"""
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    quantity_input = page.locator("#quantity_to_create")

    # Test minimum validation
    quantity_input.fill("0")
    quantity_input.blur()
    # HTML5 validation should prevent submission with value < 1
    expect(quantity_input).to_have_attribute("min", "1")

    # Test maximum validation
    quantity_input.fill("101")
    quantity_input.blur()
    expect(quantity_input).to_have_attribute("max", "100")

    # Test valid values
    quantity_input.fill("1")
    expect(quantity_input).to_have_value("1")

    quantity_input.fill("50")
    expect(quantity_input).to_have_value("50")

    quantity_input.fill("100")
    expect(quantity_input).to_have_value("100")


@pytest.mark.e2e
def test_bulk_creation_ja_id_sequence(page, live_server):
    """Test that JA IDs are assigned sequentially starting from next available"""
    # First, add some existing items to establish a baseline
    from app.database import InventoryItem
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)

    # Add a few items manually
    for i in range(1, 4):
        item = InventoryItem(
            ja_id=f"JA{i:06d}",
            item_type="Bar",
            material="Steel",
            length=12.0,
            location="Storage",
            active=True
        )
        service.add_item(item)

    # Now use bulk creation to add 3 more
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    item_data = {
        'item_type': 'Bar',
        'shape': 'Round',
        'material': 'Aluminum',
        'length': '24',
        'width': '1',
        'location': 'Storage C'
    }
    bulk_page.fill_item_details(item_data)
    bulk_page.set_quantity_to_create(3)

    # Check preview message shows correct JA ID range
    info_text = bulk_page.get_bulk_creation_info_text()
    assert "JA000004" in info_text
    assert "JA000006" in info_text

    bulk_page.submit_form()

    # Verify JA IDs in modal
    ja_ids = bulk_page.get_modal_ja_ids()
    assert ja_ids == ["JA000004", "JA000005", "JA000006"]


@pytest.mark.e2e
def test_bulk_creation_with_photos_not_duplicated(page, live_server):
    """Test that photos are NOT duplicated to bulk-created items"""
    # Photos are only uploaded on edit page, not add page
    # This test verifies that bulk-created items start with empty photo lists
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    item_data = {
        'item_type': 'Bar',
        'shape': 'Round',
        'material': 'Copper',
        'length': '18',
        'width': '0.75',
        'location': 'Storage D'
    }
    bulk_page.fill_item_details(item_data)
    bulk_page.set_quantity_to_create(2)

    bulk_page.submit_form()

    ja_ids = bulk_page.get_modal_ja_ids()
    bulk_page.close_modal()

    # Verify items have no photos
    from app.mariadb_inventory_service import InventoryService
    from app.photo_service import PhotoService
    service = InventoryService(live_server.storage)

    # Photos are in a separate table, check via PhotoService
    with PhotoService(live_server.storage) as photo_service:
        for ja_id in ja_ids:
            item = service.get_item(ja_id)
            assert item is not None
            photos = photo_service.get_photos(ja_id)
            assert len(photos) == 0, f"Item {ja_id} should have no photos"


@pytest.mark.e2e
def test_bulk_label_printing_modal_content(page, live_server):
    """Test that bulk label printing modal shows correct information"""
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    item_data = {
        'item_type': 'Plate',
        'shape': 'Rectangular',
        'material': 'Stainless Steel',
        'length': '24',
        'width': '12',
        'thickness': '0.125',
        'location': 'Materials Rack'
    }
    bulk_page.fill_item_details(item_data)
    bulk_page.set_quantity_to_create(4)

    bulk_page.submit_form()

    # Verify modal is shown
    assert bulk_page.is_bulk_label_modal_visible()

    # Verify modal title
    modal_title = page.locator("#bulkLabelPrintingModal .modal-title")
    expect(modal_title).to_contain_text("4 Items Created Successfully")

    # Verify item list is shown
    items_list = page.locator("#bulk-label-items-list")
    expect(items_list).to_be_visible()

    # Verify correct number of items
    ja_ids = bulk_page.get_modal_ja_ids()
    assert len(ja_ids) == 4

    # Verify each item shows display name
    items = page.locator("#bulk-label-items-list .list-group-item")
    for i in range(items.count()):
        item_text = items.nth(i).inner_text()
        assert "JA" in item_text
        assert "Stainless Steel" in item_text


@pytest.mark.e2e
def test_bulk_creation_preview_updates_dynamically(page, live_server):
    """Test that bulk creation preview updates when quantity changes"""
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    # Fill minimal item details
    item_data = {
        'item_type': 'Bar',
        'material': 'Steel',
        'location': 'Storage'
    }
    bulk_page.fill_item_details(item_data)

    # Test quantity = 1 (no info shown)
    bulk_page.set_quantity_to_create(1)
    info_text = bulk_page.get_bulk_creation_info_text()
    assert info_text is None

    # Test quantity = 3 (info shown)
    bulk_page.set_quantity_to_create(3)
    info_text = bulk_page.get_bulk_creation_info_text()
    assert info_text is not None
    assert "3 items" in info_text.lower()

    # Test quantity = 10 (info updates)
    bulk_page.set_quantity_to_create(10)
    info_text = bulk_page.get_bulk_creation_info_text()
    assert "10 items" in info_text.lower()

    # Test back to quantity = 1 (info hidden again)
    bulk_page.set_quantity_to_create(1)
    info_text = bulk_page.get_bulk_creation_info_text()
    assert info_text is None
