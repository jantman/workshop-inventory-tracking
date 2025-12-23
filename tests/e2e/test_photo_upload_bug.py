"""
E2E Test for Photo Upload Bug

This test reproduces the bug where:
1. Uploading a photo shows undefined in the initial view
2. After page refresh/navigation, the photo shows the wrong data (from a different photo)

The root cause is:
1. JavaScript bug: photo-manager.js line 342 accesses result.photo_id which doesn't exist
2. Backend bug: get_photo_data() queries by ItemPhotoAssociation.id instead of Photo.id
"""

import pytest
import os
import tempfile
from PIL import Image
from playwright.sync_api import expect
from tests.e2e.pages.add_item_page import AddItemPage
from app.photo_service import PhotoService
from app.mariadb_inventory_service import InventoryService
from app.database import InventoryItem


@pytest.fixture
def sample_images():
    """Create multiple temporary image files for testing"""
    images = []
    colors = ['red', 'green', 'blue']

    for color in colors:
        image = Image.new('RGB', (200, 200), color=color)
        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        image.save(temp_file.name, format='JPEG', quality=90)
        temp_file.close()
        images.append((color, temp_file.name))

    yield images

    # Clean up
    for _, filepath in images:
        try:
            os.unlink(filepath)
        except OSError:
            pass


@pytest.mark.e2e
def test_photo_upload_with_existing_shared_photos(page, live_server, sample_images):
    """
    Test photo upload bug where new photo shows wrong data due to ID confusion.

    Scenario:
    1. Create multiple items with shared photos (one photo associated with multiple items)
    2. Upload a new photo to a new item
    3. Verify the photo displays correctly immediately after upload
    4. Navigate away and back (simulating "Update Item" workflow)
    5. Verify the photo still shows correct data (not another photo's data)
    """
    service = InventoryService(live_server.storage)

    # Create items with shared photos (similar to database state in bug report)
    # This creates associations where association IDs != photo IDs
    items_with_shared_photo = []
    for i in range(5):
        item = InventoryItem(
            ja_id=f"JA{263+i:06d}",  # JA000263-JA000267
            item_type="Bar",
            material="Steel",
            length=12.0,
            location="Storage",
            active=True
        )
        service.add_item(item)
        items_with_shared_photo.append(item.ja_id)

    # Create one additional item with its own photo
    item_with_own_photo = InventoryItem(
        ja_id="JA000591",
        item_type="Plate",
        material="Aluminum",
        length=24.0,
        location="Storage",
        active=True
    )
    service.add_item(item_with_own_photo)

    # Upload photos to create specific database state
    # Photo 1: Associated with JA000591
    # Photo 2: Associated with JA000263-JA000267 (5 associations for 1 photo)

    with PhotoService(live_server.storage) as photo_service:
        # Upload first photo for JA000591
        red_color, red_image_path = sample_images[0]
        with open(red_image_path, 'rb') as f:
            photo_data = f.read()
        assoc1 = photo_service.upload_photo(item_with_own_photo.ja_id, photo_data, "red.jpg", "image/jpeg")
        red_photo_id = assoc1.photo_id

        # Upload second photo and associate it with multiple items
        green_color, green_image_path = sample_images[1]
        with open(green_image_path, 'rb') as f:
            photo_data = f.read()
        assoc2 = photo_service.upload_photo(items_with_shared_photo[0], photo_data, "green.jpg", "image/jpeg")
        green_photo_id = assoc2.photo_id

        # Copy this photo to the other items (creates multiple associations for same photo)
        for ja_id in items_with_shared_photo[1:]:
            photo_service.copy_photos(items_with_shared_photo[0], ja_id)

    # At this point, we have:
    # - Multiple associations created
    # - Association IDs don't match Photo IDs
    # - Similar to the production bug scenario

    # Now create a new item and upload a photo via UI
    new_item_ja_id = "JA000592"
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    add_page.fill_basic_item_data(
        ja_id=new_item_ja_id,
        item_type="Bar",
        shape="Round",
        material="Steel"  # Use a standard material name
    )
    add_page.fill_dimensions(length="96.5", width="0.5")
    add_page.fill_location_and_notes(location="Storage")
    add_page.submit_form()
    add_page.assert_form_submitted_successfully()

    # Navigate to edit page to upload photo
    edit_url = f"{live_server.url}/inventory/edit/{new_item_ja_id}"
    page.goto(edit_url)

    # Verify we're on the edit page
    expect(page.locator("#add-item-form")).to_be_visible()

    # Upload a blue photo
    blue_color, blue_image_path = sample_images[2]
    file_input = page.locator(".photo-file-input")
    file_input.set_input_files(blue_image_path)

    # Wait for photo to be processed and uploaded
    page.wait_for_timeout(2000)

    # Verify photo appears in gallery
    photo_gallery = page.locator(".photo-gallery-grid")
    expect(photo_gallery).to_be_visible()
    expect(photo_gallery.locator(".photo-card")).to_have_count(1)

    # Get the photo card
    photo_card = photo_gallery.locator(".photo-card").first

    # BUG CHECK 1: Photo filename should be displayed (not "undefined")
    photo_name = photo_card.locator(".photo-name")
    photo_name_text = photo_name.text_content()
    assert photo_name_text is not None, "Photo name should not be None"
    assert "undefined" not in photo_name_text.lower(), f"BUG: Photo name contains 'undefined': {photo_name_text}"
    assert ".jpg" in photo_name_text, f"Photo name should contain .jpg extension: {photo_name_text}"

    # BUG CHECK 2: Try to view the photo - should not be broken
    # Wait a bit for the gallery to update with the server URL (may start as data URL)
    page.wait_for_timeout(1000)

    # Get the thumbnail src to check the photo ID (img is inside the thumbnail div)
    thumbnail_img = photo_card.locator(".photo-thumbnail img")
    thumbnail_src = thumbnail_img.get_attribute("src")
    assert thumbnail_src is not None, "Thumbnail should have src attribute"

    # The src might be a data URL initially, or an API URL
    # If it's a data URL, that's ok for now - we'll check after navigation
    # If it's an API URL, make sure it doesn't contain "undefined"
    import re
    if "/api/photos/" in thumbnail_src:
        assert "/api/photos/undefined" not in thumbnail_src, f"BUG: Thumbnail src contains undefined: {thumbnail_src}"
        match = re.search(r'/api/photos/(\d+)\?size=thumbnail', thumbnail_src)
        if match:
            displayed_photo_id = int(match.group(1))
        else:
            displayed_photo_id = None
    else:
        # Data URL is fine for now
        displayed_photo_id = None

    # Click thumbnail to view full photo
    photo_card.locator(".photo-thumbnail").click()
    page.wait_for_timeout(1000)

    # Verify photo viewer opens (either PhotoSwipe or fallback modal)
    photoswipe_visible = page.locator(".pswp").is_visible()
    fallback_modal_visible = page.locator("#fallback-image-modal").is_visible()
    assert photoswipe_visible or fallback_modal_visible, "Photo viewer should be visible"

    # Close viewer
    if fallback_modal_visible:
        # Check that the image src is not undefined
        modal_img = page.locator("#fallback-image-modal img")
        modal_img_src = modal_img.get_attribute("src")
        assert "/api/photos/undefined" not in modal_img_src, f"BUG: Modal image src contains undefined: {modal_img_src}"
        page.locator("#fallback-image-modal .btn-close").click()
    elif photoswipe_visible:
        page.keyboard.press("Escape")

    # Now simulate the "Update Item" workflow - click Update Item button
    # This will redirect to the inventory list
    update_button = page.locator('button:has-text("Update Item")')
    update_button.click()

    # Wait for redirect to inventory list
    page.wait_for_url(f"{live_server.url}/inventory")

    # Navigate back to the edit page
    page.goto(edit_url)
    expect(page.locator("#add-item-form")).to_be_visible()

    # Wait for photos to load
    page.wait_for_timeout(1000)

    # BUG CHECK 3: After navigation, photo should still be correct
    photo_gallery = page.locator(".photo-gallery-grid")
    expect(photo_gallery).to_be_visible()
    expect(photo_gallery.locator(".photo-card")).to_have_count(1)

    photo_card = photo_gallery.locator(".photo-card").first

    # Verify the thumbnail src points to the correct photo (img is inside thumbnail div)
    thumbnail_img_after = photo_card.locator(".photo-thumbnail img")
    thumbnail_src_after = thumbnail_img_after.get_attribute("src")
    assert thumbnail_src_after is not None, "Thumbnail should have src attribute after navigation"

    # Extract photo ID from thumbnail src
    match_after = re.search(r'/api/photos/(\d+)\?size=thumbnail', thumbnail_src_after)
    assert match_after is not None, f"Could not extract photo ID from thumbnail src after navigation: {thumbnail_src_after}"
    displayed_photo_id_after = int(match_after.group(1))

    # Get the actual photo ID from database for this item
    with PhotoService(live_server.storage) as photo_service:
        photos = photo_service.get_photos(new_item_ja_id)
        assert len(photos) == 1, f"Expected 1 photo for {new_item_ja_id}, got {len(photos)}"
        actual_photo_id = photos[0].photo_id

    # CRITICAL BUG CHECK: The displayed photo ID should match the actual photo ID
    # NOT some other photo's ID (like the green photo)
    assert displayed_photo_id_after == actual_photo_id, \
        f"BUG: Displayed photo ID {displayed_photo_id_after} != actual photo ID {actual_photo_id}. " \
        f"Photo is showing wrong data!"

    # Verify it's not showing the green photo's ID
    assert displayed_photo_id_after != green_photo_id, \
        f"BUG: Displaying green photo (ID {green_photo_id}) instead of blue photo (ID {actual_photo_id})"

    # Try to actually fetch the photo data via API to verify it returns correct data
    response = page.request.get(f"{live_server.url}/api/photos/{displayed_photo_id_after}?size=original")
    assert response.status == 200, f"Failed to fetch photo {displayed_photo_id_after}: {response.status}"

    # Check content type - should be image/jpeg (not application/pdf or wrong type)
    content_type = response.headers.get("content-type", "")
    assert "image/jpeg" in content_type, \
        f"BUG: Photo {displayed_photo_id_after} returned wrong content type: {content_type}"

    # Verify photo data size is reasonable (blue photo should be similar to red/green)
    photo_data = response.body()
    assert len(photo_data) > 1000, f"Photo data is suspiciously small: {len(photo_data)} bytes"
    assert len(photo_data) < 10_000_000, f"Photo data is suspiciously large: {len(photo_data)} bytes"
