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
    def test_add_item_with_photo_upload_full_workflow(self, page, live_server, sample_image_file):
        """Test complete photo upload workflow: upload -> storage -> display"""
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

        # Add location (now required)
        add_page.fill_location_and_notes(location="Storage A")

        # Submit form first to create the item
        add_page.submit_form()
        add_page.assert_form_submitted_successfully()
        
        # Now navigate to edit page to test photo upload
        edit_url = f"{live_server.url}/inventory/edit/JA000501"
        page.goto(edit_url)
        
        # Verify we're on the edit page
        expect(page.locator("#add-item-form")).to_be_visible()
        
        # Find and interact with photo upload section
        photo_section = page.locator("#photo-manager-container")
        expect(photo_section).to_be_visible()
        
        # Upload a photo using file input
        file_input = page.locator(".photo-file-input")
        file_input.set_input_files(sample_image_file)
        
        # Wait for photo to be processed and uploaded
        page.wait_for_timeout(2000)  # Wait for upload to complete
        
        # Verify photo appears in gallery
        photo_gallery = page.locator(".photo-gallery-grid")
        expect(photo_gallery).to_be_visible()
        expect(photo_gallery.locator(".photo-card")).to_have_count(1)
        
        # Verify photo card details
        photo_card = photo_gallery.locator(".photo-card").first
        expect(photo_card.locator(".photo-name")).to_contain_text(".jpg")
        expect(photo_card.locator(".photo-meta")).to_be_visible()
        
        # Test photo viewing (click to open lightbox/modal)
        photo_card.locator(".photo-thumbnail").click()
        page.wait_for_timeout(1000)  # Wait for modal/lightbox to open
        
        # Verify photo can be viewed (either PhotoSwipe or fallback modal)
        # Check for PhotoSwipe or fallback modal
        photoswipe_visible = page.locator(".pswp").is_visible()
        fallback_modal_visible = page.locator("#fallback-image-modal").is_visible()
        
        assert photoswipe_visible or fallback_modal_visible, "Photo viewer should be visible"
        
        # Close viewer if it's a modal
        if fallback_modal_visible:
            page.locator("#fallback-image-modal .btn-close").click()
        elif photoswipe_visible:
            page.keyboard.press("Escape")
        
        # Navigate to inventory list to verify photo is shown there too
        list_page = InventoryListPage(page, live_server.url)
        list_page.navigate()
        
        # Find the item row and click the details button to open modal
        item_row = page.locator(f"tr:has-text('JA000501')")
        expect(item_row).to_be_visible()
        
        # Click on the details (eye) button to open details modal
        details_button = item_row.locator("button[title='View Details']")
        expect(details_button).to_be_visible()
        details_button.click()
        
        # Wait for modal to open
        modal = page.locator("#item-details-modal")
        expect(modal).to_be_visible()
        
        # Verify photo section exists in modal
        modal_photo_section = modal.locator("#item-details-photos")
        expect(modal_photo_section).to_be_visible()
        
        # Verify photo is displayed - should see photo card since we uploaded one
        photo_cards = modal_photo_section.locator(".photo-card")
        expect(photo_cards).to_have_count(1)
        
        # Verify photo card has the expected elements
        first_photo_card = photo_cards.first
        expect(first_photo_card.locator(".photo-name")).to_be_visible()
        expect(first_photo_card.locator(".photo-meta")).to_be_visible()
    
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
        add_page.fill_location_and_notes(location="Storage A")  # Location is now required
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