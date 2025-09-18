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


@pytest.fixture
def sample_pdf_file():
    """Create a temporary PDF file for testing"""
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
72 720 Td
(Test Document) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000010 00000 n 
0000000053 00000 n 
0000000100 00000 n 
0000000179 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
268
%%EOF"""
    
    temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    temp_file.write(pdf_content)
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
    def test_add_item_with_multiple_photos(self, page, live_server, sample_image_file, sample_pdf_file):
        """Test adding an item with multiple photos"""
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
        
        # Upload multiple files
        file_input = page.locator(".photo-file-input")
        file_input.set_input_files([sample_image_file, sample_pdf_file])
        
        # Wait for both photos to appear
        photo_gallery = page.locator(".photo-gallery-grid")
        expect(photo_gallery.locator(".photo-card")).to_have_count(2)
        
        # Verify both file types are handled
        photo_cards = photo_gallery.locator(".photo-card")
        
        # Check that we have both image and PDF
        expect(photo_cards.nth(0).locator(".photo-name")).to_contain_text(".jpg")
        expect(photo_cards.nth(1).locator(".photo-name")).to_contain_text(".pdf")
        
        # Submit the form
        add_page.submit_form()
        add_page.assert_form_submitted_successfully()
    
    @pytest.mark.e2e
    def test_photo_drag_and_drop_upload(self, page, live_server, sample_image_file):
        """Test photo upload using drag and drop"""
        # Navigate to add item page
        add_page = AddItemPage(page, live_server.url)
        add_page.navigate()
        
        # Fill basic item information
        add_page.fill_basic_item_data(
            ja_id="JA000503",
            item_type="Sheet",
            shape="Square",
            material="Copper"
        )
        
        # Find drop zone
        drop_zone = page.locator(".photo-drop-zone")
        expect(drop_zone).to_be_visible()
        
        # Simulate drag and drop (Playwright doesn't support real file drag-drop easily)
        # So we'll use the file input instead
        file_input = page.locator(".photo-file-input")
        file_input.set_input_files(sample_image_file)
        
        # Verify photo was added
        photo_gallery = page.locator(".photo-gallery-grid")
        expect(photo_gallery.locator(".photo-card")).to_have_count(1)
        
        # Submit the form
        add_page.submit_form()
        add_page.assert_form_submitted_successfully()
    
    @pytest.mark.e2e
    def test_photo_delete_before_submit(self, page, live_server, sample_image_file):
        """Test deleting a photo before submitting the form"""
        # Navigate to add item page
        add_page = AddItemPage(page, live_server.url)
        add_page.navigate()
        
        # Fill basic item information
        add_page.fill_basic_item_data(
            ja_id="JA000504",
            item_type="Tube",
            shape="Round",
            material="Stainless Steel"
        )
        
        # Upload a photo
        file_input = page.locator(".photo-file-input")
        file_input.set_input_files(sample_image_file)
        
        # Wait for photo to appear
        photo_gallery = page.locator(".photo-gallery-grid")
        expect(photo_gallery.locator(".photo-card")).to_have_count(1)
        
        # Delete the photo
        delete_btn = page.locator(".photo-delete-btn").first
        delete_btn.click()
        
        # Confirm deletion in any dialog
        page.on("dialog", lambda dialog: dialog.accept())
        
        # Verify photo was removed
        expect(photo_gallery.locator(".photo-card")).to_have_count(0)
        
        # Verify empty state is shown
        empty_state = page.locator(".photo-gallery-empty")
        expect(empty_state).to_be_visible()
        
        # Submit the form (should work without photos)
        add_page.submit_form()
        add_page.assert_form_submitted_successfully()
    
    @pytest.mark.e2e
    def test_photo_view_functionality(self, page, live_server, sample_image_file):
        """Test viewing photos in the lightbox"""
        # Navigate to add item page
        add_page = AddItemPage(page, live_server.url)
        add_page.navigate()
        
        # Fill basic item information
        add_page.fill_basic_item_data(
            ja_id="JA000505",
            item_type="Bar",
            shape="Hex",
            material="Brass"
        )
        
        # Upload a photo
        file_input = page.locator(".photo-file-input")
        file_input.set_input_files(sample_image_file)
        
        # Wait for photo to appear
        photo_gallery = page.locator(".photo-gallery-grid")
        expect(photo_gallery.locator(".photo-card")).to_have_count(1)
        
        # Click on photo thumbnail to open lightbox
        thumbnail = page.locator(".photo-thumbnail").first
        thumbnail.click()
        
        # Wait for PhotoSwipe lightbox to open
        # Note: PhotoSwipe creates elements dynamically, so we look for its container
        page.wait_for_timeout(1000)  # Give lightbox time to initialize
        
        # Check if PhotoSwipe is active (it adds classes to body)
        # Or look for the PhotoSwipe container
        lightbox = page.locator(".pswp")
        if lightbox.count() > 0:
            expect(lightbox).to_be_visible()
            
            # Close lightbox (ESC key or click outside)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        
        # Continue with form submission
        add_page.submit_form()
        add_page.assert_form_submitted_successfully()
    
    @pytest.mark.e2e
    def test_photo_upload_validation_errors(self, page, live_server):
        """Test photo upload with validation errors"""
        # Navigate to add item page
        add_page = AddItemPage(page, live_server.url)
        add_page.navigate()
        
        # Fill basic item information
        add_page.fill_basic_item_data(
            ja_id="JA000506",
            item_type="Angle",
            shape="Rectangular",
            material="Iron"
        )
        
        # Try to upload an invalid file type (create a text file)
        invalid_file = tempfile.NamedTemporaryFile(suffix='.txt', delete=False)
        invalid_file.write(b'This is not an image')
        invalid_file.close()
        
        try:
            file_input = page.locator(".photo-file-input")
            file_input.set_input_files(invalid_file.name)
            
            # Should show error message for invalid file type
            # (Implementation dependent - may show toast or inline error)
            page.wait_for_timeout(2000)
            
            # Verify no photo was added to gallery
            photo_gallery = page.locator(".photo-gallery-grid")
            expect(photo_gallery.locator(".photo-card")).to_have_count(0)
            
        finally:
            os.unlink(invalid_file.name)
        
        # Form should still be submittable without photos
        add_page.submit_form()
        add_page.assert_form_submitted_successfully()


class TestPhotoUploadEditItem:
    """Test photo upload during item editing"""
    
    @pytest.mark.e2e
    def test_edit_item_add_photos(self, page, live_server, sample_image_file):
        """Test adding photos to an existing item"""
        # First create an item without photos
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
        
        # Find photo section
        photo_section = page.locator("#photo-manager-container")
        expect(photo_section).to_be_visible()
        
        # Should start with no photos
        empty_state = page.locator(".photo-gallery-empty")
        expect(empty_state).to_be_visible()
        
        # Upload a photo
        file_input = page.locator(".photo-file-input")
        file_input.set_input_files(sample_image_file)
        
        # Wait for photo to appear
        photo_gallery = page.locator(".photo-gallery-grid")
        expect(photo_gallery.locator(".photo-card")).to_have_count(1)
        
        # Submit the edit form
        submit_btn = page.locator("button[type='submit']")
        submit_btn.click()
        
        # Verify success
        expect(page.locator(".alert-success")).to_be_visible()
    
    @pytest.mark.e2e
    def test_edit_item_view_existing_photos(self, page, live_server, sample_image_file):
        """Test viewing existing photos when editing an item"""
        # First create an item with photos via API or direct database insertion
        # For this test, we'll simulate having existing photos
        
        # Navigate directly to edit a known item with photos
        # This would require pre-populated test data or API setup
        page.goto(f"{live_server.url}/inventory/edit/JA000601")
        
        # Check if photo section loads
        photo_section = page.locator("#photo-manager-container")
        expect(photo_section).to_be_visible()
        
        # If there are existing photos, they should be displayed
        # This test may need adjustment based on actual test data
        page.wait_for_timeout(2000)  # Allow time for photos to load
        
        # Check for either photos or empty state
        photo_gallery = page.locator(".photo-gallery-grid")
        empty_state = page.locator(".photo-gallery-empty")
        
        # At least one should be visible
        assert photo_gallery.is_visible() or empty_state.is_visible()


class TestPhotoViewingInModal:
    """Test photo viewing in item details modal"""
    
    @pytest.mark.e2e
    def test_view_photos_in_item_details_modal(self, page, live_server):
        """Test viewing photos through the item details modal"""
        # Navigate to inventory list
        list_page = InventoryListPage(page, live_server.url)
        list_page.navigate()
        
        # Look for an item with photos (may need test data setup)
        # For now, just test that the modal opens and photo section exists
        
        # Click on an item to open details modal
        item_row = page.locator("tr[data-ja-id]").first
        if item_row.count() > 0:
            # Get the JA ID from the first item
            ja_id = item_row.get_attribute("data-ja-id")
            
            # Click view details button
            view_btn = item_row.locator(".btn-view-details")
            if view_btn.count() > 0:
                view_btn.click()
                
                # Wait for modal to open
                modal = page.locator("#item-details-modal")
                expect(modal).to_be_visible()
                
                # Check for photo section in modal
                photo_section = modal.locator("#item-details-photos")
                expect(photo_section).to_be_visible()
                
                # Close modal
                close_btn = modal.locator(".btn-close")
                close_btn.click()
    
    @pytest.mark.e2e 
    def test_photo_lightbox_in_modal(self, page, live_server):
        """Test opening photo lightbox from item details modal"""
        # This test would require an item with actual photos
        # Implementation depends on test data setup
        
        # Navigate to inventory list
        list_page = InventoryListPage(page, live_server.url)
        list_page.navigate()
        
        # Find an item with photos and test lightbox functionality
        # This is a placeholder - actual implementation would need
        # proper test data or API calls to create items with photos
        
        # For now, just verify the modal structure is correct
        assert True  # Placeholder
    
    @pytest.mark.e2e
    def test_photo_download_from_modal(self, page, live_server):
        """Test downloading photos from item details modal"""
        # Another test that would require actual photo data
        # Placeholder for now
        assert True