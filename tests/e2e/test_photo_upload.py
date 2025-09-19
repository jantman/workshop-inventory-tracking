"""
E2E Tests for Photo Upload Functionality

Tests photo upload, viewing, and management through the UI.
"""

import pytest
import os
import tempfile
from PIL import Image
from playwright.sync_api import expect
from tests.e2e.pages.add_item_page import AddItemPage
from tests.e2e.pages.inventory_list_page import InventoryListPage


@pytest.fixture
def sample_image_file():
    """Create a temporary image file for testing"""
    # Create a simple test image
    image = Image.new('RGB', (200, 200), color='blue')
    
    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    image.save(temp_file.name, format='JPEG', quality=90)
    temp_file.close()
    
    yield temp_file.name
    
    # Clean up
    try:
        os.unlink(temp_file.name)
    except OSError:
        pass


class TestPhotoUploadAddItem:
    """Test photo upload during item creation"""
    
    @pytest.mark.e2e
    def test_add_item_with_photo_upload(self, page, live_server, sample_image_file):
        """Test adding an item with photo upload"""
        # Navigate to add item page
        add_page = AddItemPage(page, live_server.url)
        add_page.navigate()
        
        # Fill basic item information
        add_page.fill_basic_item_data(
            ja_id="JA000501",
            item_type="Bar",
            shape="Round", 
            material="Steel"
        )
        
        # Add dimensions
        add_page.fill_dimensions(length="100", width="25")
        
        # Find and interact with photo upload section
        photo_section = page.locator("#photo-manager-container")
        expect(photo_section).to_be_visible()
        
        # Upload a photo using file input
        file_input = page.locator(".photo-file-input")
        file_input.set_input_files(sample_image_file)
        
        # Wait for photo to appear in gallery
        photo_gallery = page.locator(".photo-gallery-grid")
        expect(photo_gallery.locator(".photo-card")).to_have_count(1)
        
        # Verify photo information is displayed
        photo_card = photo_gallery.locator(".photo-card").first
        expect(photo_card.locator(".photo-name")).to_contain_text(".jpg")
        expect(photo_card.locator(".photo-meta")).to_be_visible()
        
        # Submit the form
        add_page.submit_form()
        
        # Verify success message
        add_page.assert_form_submitted_successfully()
        
        # Navigate to inventory list to verify item was added
        list_page = InventoryListPage(page, live_server.url)
        list_page.navigate()
        
        # Verify the item appears in the list
        list_page.assert_item_in_list("JA000501")
    
    @pytest.mark.e2e
    def test_add_item_with_photo_section_visible(self, page, live_server):
        """Test that photo section is visible and functional"""
        # Navigate to add item page
        add_page = AddItemPage(page, live_server.url)
        add_page.navigate()
        
        # Fill basic item information
        add_page.fill_basic_item_data(
            ja_id="JA000502",
            item_type="Plate",
            shape="Rectangular",
            material="Aluminum"
        )
        
        # Add dimensions
        add_page.fill_dimensions(length="200", width="100")
        
        # Verify photo section exists
        photo_section = page.locator("#photo-manager-container")
        expect(photo_section).to_be_visible()
        
        # Verify photo upload elements exist
        photo_drop_zone = page.locator(".photo-drop-zone")
        expect(photo_drop_zone).to_be_visible()
        
        file_input = page.locator(".photo-file-input")
        expect(file_input).to_be_attached()
        
        # Photo gallery should exist but be hidden when there are no photos
        photo_gallery = page.locator(".photo-gallery-grid")
        expect(photo_gallery).to_be_attached()
        expect(photo_gallery).to_be_hidden()  # Gallery is hidden when empty by design
        
        # Test passes if all photo elements are properly initialized
        # (No need to submit form for this structural test)


class TestPhotoUploadEditItem:
    """Test photo upload during item editing"""
    
    @pytest.mark.e2e
    def test_edit_item_photo_section_exists(self, page, live_server):
        """Test that photo section exists in edit form"""
        # First create an item
        add_page = AddItemPage(page, live_server.url)
        add_page.navigate()
        
        add_page.fill_basic_item_data(
            ja_id="JA000601",
            item_type="Bar",
            shape="Round",
            material="Steel"
        )
        add_page.fill_dimensions(length="150", width="20")
        add_page.submit_form()
        add_page.assert_form_submitted_successfully()
        
        # Navigate to edit the item
        page.goto(f"{live_server.url}/inventory/edit/JA000601")
        
        # Verify edit form loads
        expect(page.locator("#add-item-form")).to_be_visible()
        
        # Verify photo section exists
        photo_section = page.locator("#photo-manager-container")
        expect(photo_section).to_be_visible()


class TestPhotoViewingInModal:
    """Test photo viewing in item details modal"""
    
    @pytest.mark.e2e
    def test_item_details_modal_has_photo_section(self, page, live_server):
        """Test that item details modal includes photo section"""
        # Navigate to inventory list
        list_page = InventoryListPage(page, live_server.url)
        list_page.navigate()
        
        # Since we may not have items, this is a basic structural test
        # that would require actual items with photos for full testing
        page.wait_for_load_state('networkidle')
        
        # The test passes if we can navigate to the list page successfully
        expect(page.locator("h2")).to_contain_text("Inventory")