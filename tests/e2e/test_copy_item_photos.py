"""
E2E Tests for Manual Photo Copying Feature

Tests the copy/paste photo workflow from the inventory list page.
"""

import pytest
import tempfile
import os
from PIL import Image
from playwright.sync_api import expect
from tests.e2e.pages.base_page import BasePage
from app.photo_service import PhotoService
from app.database import Photo, ItemPhotoAssociation
from sqlalchemy import func


class InventoryListPhotoCopyPage(BasePage):
    """Page object for inventory list photo copy/paste workflow"""

    def navigate_to_list(self):
        """Navigate to inventory list page"""
        self.page.goto(f"{self.base_url}/inventory")
        self.page.wait_for_load_state("networkidle")

    def select_item(self, ja_id):
        """Select an item by checking its checkbox"""
        checkbox = self.page.locator(f'input[type="checkbox"][data-ja-id="{ja_id}"]')
        checkbox.check(force=True)  # Force the check to ensure it works
        # Verify the checkbox is actually checked
        assert checkbox.is_checked(), f"Checkbox for {ja_id} was not checked"
        self.page.wait_for_timeout(300)

    def select_multiple_items(self, ja_ids):
        """Select multiple items by checking their checkboxes"""
        for ja_id in ja_ids:
            self.select_item(ja_id)

    def click_options_dropdown(self):
        """Open the Options dropdown menu"""
        self.page.locator('button:has-text("Options")').click()
        self.page.wait_for_timeout(200)

    def click_copy_photos_button(self):
        """Click 'Copy Photos From This Item' in Options menu"""
        self.click_options_dropdown()
        self.page.locator('#copy-photos-btn').click()
        self.page.wait_for_timeout(500)

    def click_paste_photos_button(self):
        """Click 'Paste Photos To Selected' in Options menu"""
        self.click_options_dropdown()
        self.page.locator('#paste-photos-btn').click()
        self.page.wait_for_timeout(500)

    def click_clear_clipboard_button(self):
        """Click 'Clear' button in photo clipboard banner"""
        self.page.locator('#clear-photo-clipboard-btn').click()
        self.page.wait_for_timeout(300)

    def is_clipboard_banner_visible(self):
        """Check if photo clipboard banner is visible"""
        banner = self.page.locator('#photo-clipboard-banner')
        return banner.is_visible()

    def get_clipboard_banner_text(self):
        """Get the text from the clipboard banner"""
        return self.page.locator('#photo-clipboard-info').inner_text()

    def get_toast_message(self):
        """Get the toast notification message (latest if multiple exist)"""
        # Use .last to get the most recent toast when multiple exist
        toast = self.page.locator('.alert.position-fixed').last
        if toast.is_visible():
            return toast.inner_text()
        return None

    def wait_for_toast(self, timeout=3000):
        """Wait for a toast message to appear"""
        self.page.wait_for_selector('.alert.position-fixed', timeout=timeout)
        self.page.wait_for_timeout(300)

    def is_copy_photos_button_enabled(self):
        """Check if Copy Photos button is enabled"""
        self.click_options_dropdown()
        button = self.page.locator('#copy-photos-btn')
        is_disabled = button.get_attribute('disabled') is not None
        # Close dropdown
        self.page.keyboard.press('Escape')
        return not is_disabled

    def is_paste_photos_button_enabled(self):
        """Check if Paste Photos button is enabled"""
        self.click_options_dropdown()
        button = self.page.locator('#paste-photos-btn')
        is_disabled = button.get_attribute('disabled') is not None
        # Close dropdown
        self.page.keyboard.press('Escape')
        return not is_disabled


@pytest.mark.e2e
def test_copy_paste_photos_single_target(live_server, page):
    """Test copying photos from one item to another"""
    from app.mariadb_inventory_service import InventoryService
    from app.database import InventoryItem
    service = InventoryService(live_server.storage)

    # Create source item with 2 photos
    item1 = InventoryItem(
        ja_id="JA000100",
        item_type="Rod",
        material="Aluminum",
        length=24.0,
        location="Bin A",
        active=True
    )
    service.add_item(item1)
    source_ja_id = item1.ja_id

    with PhotoService(live_server.storage) as photo_service:
        for i, color in enumerate(['red', 'blue']):
            image = Image.new('RGB', (150, 150), color=color)
            temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            image.save(temp_file.name, format='JPEG', quality=90)
            temp_file.close()

            with open(temp_file.name, 'rb') as f:
                photo_data = f.read()
            photo_service.upload_photo(source_ja_id, photo_data, f"photo{i+1}.jpg", "image/jpeg")
            os.unlink(temp_file.name)

    # Create target item with no photos
    item2 = InventoryItem(
        ja_id="JA000101",
        item_type="Rod",
        material="Steel",
        length=36.0,
        location="Bin B",
        active=True
    )
    service.add_item(item2)
    target_ja_id = item2.ja_id

    # Navigate to list and copy photos
    list_page = InventoryListPhotoCopyPage(page, live_server.url)
    list_page.navigate_to_list()

    # Select source item and copy photos
    list_page.select_item(source_ja_id)
    list_page.click_copy_photos_button()

    # Verify clipboard banner appears
    assert list_page.is_clipboard_banner_visible()
    banner_text = list_page.get_clipboard_banner_text()
    assert source_ja_id in banner_text
    assert "2 photo" in banner_text.lower()

    # Select target item and paste photos
    list_page.select_item(target_ja_id)

    # Set up dialog handler to accept confirmation
    page.on("dialog", lambda dialog: dialog.accept())
    list_page.click_paste_photos_button()
    list_page.wait_for_toast()

    # Verify success message
    toast = list_page.get_toast_message()
    assert toast is not None
    assert "2 photo" in toast.lower()
    assert "1 item" in toast.lower()

    # Verify target item now has 2 photos
    with PhotoService(live_server.storage) as photo_service:
        target_photos = photo_service.get_photos(target_ja_id)
        assert len(target_photos) == 2

    # Verify clipboard banner is gone
    assert not list_page.is_clipboard_banner_visible()


@pytest.mark.e2e
def test_copy_paste_photos_multiple_targets(live_server, page):
    """Test copying photos from one item to multiple items"""
    from app.mariadb_inventory_service import InventoryService
    from app.database import InventoryItem
    service = InventoryService(live_server.storage)

    # Create source item with 3 photos
    item1 = InventoryItem(
        ja_id="JA000102",
        item_type="Plate",
        material="Brass",
        length=12.0,
        width=12.0,
        location="Materials Rack",
        active=True
    )
    service.add_item(item1)
    source_ja_id = item1.ja_id

    with PhotoService(live_server.storage) as photo_service:
        for i, color in enumerate(['green', 'yellow', 'orange']):
            image = Image.new('RGB', (200, 200), color=color)
            temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            image.save(temp_file.name, format='JPEG', quality=90)
            temp_file.close()

            with open(temp_file.name, 'rb') as f:
                photo_data = f.read()
            photo_service.upload_photo(source_ja_id, photo_data, f"photo{i+1}.jpg", "image/jpeg")
            os.unlink(temp_file.name)

    # Create 3 target items with no photos
    target_ja_ids = []
    for i in range(3):
        item = InventoryItem(
            ja_id=f"JA{103+i:06d}",
            item_type="Plate",
            material="Copper",
            length=6.0,
            width=6.0,
            location="Storage",
            active=True
        )
        service.add_item(item)
        target_ja_ids.append(item.ja_id)

    # Navigate to list and copy photos
    list_page = InventoryListPhotoCopyPage(page, live_server.url)
    list_page.navigate_to_list()

    # Select source item and copy photos
    list_page.select_item(source_ja_id)
    list_page.click_copy_photos_button()

    # Verify clipboard banner
    assert list_page.is_clipboard_banner_visible()

    # Select all target items and paste photos
    list_page.select_multiple_items(target_ja_ids)

    # Set up dialog handler to accept confirmation
    page.on("dialog", lambda dialog: dialog.accept())
    list_page.click_paste_photos_button()
    list_page.wait_for_toast()

    # Verify success message
    toast = list_page.get_toast_message()
    assert toast is not None
    assert "3 photo" in toast.lower()
    assert "3 item" in toast.lower()

    # Verify all target items now have 3 photos
    with PhotoService(live_server.storage) as photo_service:
        for target_ja_id in target_ja_ids:
            target_photos = photo_service.get_photos(target_ja_id)
            assert len(target_photos) == 3


@pytest.mark.e2e
def test_copy_paste_photos_append_behavior(live_server, page):
    """Test that pasting photos appends to existing photos (doesn't replace)"""
    from app.mariadb_inventory_service import InventoryService
    from app.database import InventoryItem
    service = InventoryService(live_server.storage)

    # Create source item with 2 photos
    item1 = InventoryItem(
        ja_id="JA000106",
        item_type="Tube",
        material="Aluminum",
        length=48.0,
        location="Tube Rack",
        active=True
    )
    service.add_item(item1)
    source_ja_id = item1.ja_id

    with PhotoService(live_server.storage) as photo_service:
        for i, color in enumerate(['cyan', 'magenta']):
            image = Image.new('RGB', (180, 180), color=color)
            temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            image.save(temp_file.name, format='JPEG', quality=90)
            temp_file.close()

            with open(temp_file.name, 'rb') as f:
                photo_data = f.read()
            photo_service.upload_photo(source_ja_id, photo_data, f"source{i+1}.jpg", "image/jpeg")
            os.unlink(temp_file.name)

    # Create target item with 1 existing photo
    item2 = InventoryItem(
        ja_id="JA000107",
        item_type="Tube",
        material="Steel",
        length=24.0,
        location="Tube Rack",
        active=True
    )
    service.add_item(item2)
    target_ja_id = item2.ja_id

    with PhotoService(live_server.storage) as photo_service:
        image = Image.new('RGB', (180, 180), color='white')
        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        image.save(temp_file.name, format='JPEG', quality=90)
        temp_file.close()

        with open(temp_file.name, 'rb') as f:
            photo_data = f.read()
        photo_service.upload_photo(target_ja_id, photo_data, "existing.jpg", "image/jpeg")
        os.unlink(temp_file.name)

    # Navigate to list and copy/paste
    list_page = InventoryListPhotoCopyPage(page, live_server.url)
    list_page.navigate_to_list()

    list_page.select_item(source_ja_id)
    list_page.click_copy_photos_button()

    list_page.select_item(target_ja_id)

    # Set up dialog handler to accept confirmation
    page.on("dialog", lambda dialog: dialog.accept())
    list_page.click_paste_photos_button()
    list_page.wait_for_toast()

    # Verify target item now has 3 photos (1 existing + 2 pasted)
    with PhotoService(live_server.storage) as photo_service:
        target_photos = photo_service.get_photos(target_ja_id)
        assert len(target_photos) == 3


@pytest.mark.e2e
def test_copy_photos_from_item_with_no_photos(live_server, page):
    """Test error when trying to copy photos from item with no photos"""
    from app.mariadb_inventory_service import InventoryService
    from app.database import InventoryItem
    service = InventoryService(live_server.storage)

    # Create item with no photos
    item = InventoryItem(
        ja_id="JA000108",
        item_type="Sheet",
        material="Aluminum",
        length=48.0,
        width=24.0,
        location="Materials Storage",
        active=True
    )
    service.add_item(item)

    list_page = InventoryListPhotoCopyPage(page, live_server.url)
    list_page.navigate_to_list()

    # Try to copy photos from item with no photos
    list_page.select_item(item.ja_id)
    list_page.click_copy_photos_button()

    # Verify error toast appears
    list_page.wait_for_toast()
    toast = list_page.get_toast_message()
    assert toast is not None
    assert "no photos" in toast.lower()

    # Verify clipboard banner does NOT appear
    assert not list_page.is_clipboard_banner_visible()


@pytest.mark.e2e
def test_clear_photo_clipboard(live_server, page):
    """Test clearing the photo clipboard"""
    from app.mariadb_inventory_service import InventoryService
    from app.database import InventoryItem
    service = InventoryService(live_server.storage)

    # Create item with photos
    item = InventoryItem(
        ja_id="JA000109",
        item_type="Rod",
        material="Steel",
        length=12.0,
        location="Bin A",
        active=True
    )
    service.add_item(item)

    with PhotoService(live_server.storage) as photo_service:
        image = Image.new('RGB', (150, 150), color='purple')
        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        image.save(temp_file.name, format='JPEG', quality=90)
        temp_file.close()

        with open(temp_file.name, 'rb') as f:
            photo_data = f.read()
        photo_service.upload_photo(item.ja_id, photo_data, "photo.jpg", "image/jpeg")
        os.unlink(temp_file.name)

    list_page = InventoryListPhotoCopyPage(page, live_server.url)
    list_page.navigate_to_list()

    # Copy photos
    list_page.select_item(item.ja_id)
    list_page.click_copy_photos_button()

    # Verify banner appears
    assert list_page.is_clipboard_banner_visible()

    # Clear clipboard
    list_page.click_clear_clipboard_button()
    list_page.wait_for_toast()

    # Verify banner disappears
    assert not list_page.is_clipboard_banner_visible()

    # Verify toast message
    toast = list_page.get_toast_message()
    assert "cleared" in toast.lower()


@pytest.mark.e2e
def test_copy_paste_no_blob_duplication(live_server, page):
    """Test that photo BLOB data is NOT duplicated when copying photos"""
    from app.mariadb_inventory_service import InventoryService
    from app.database import InventoryItem
    service = InventoryService(live_server.storage)

    # Create source item with 2 photos
    item1 = InventoryItem(
        ja_id="JA000110",
        item_type="Bar",
        material="Aluminum",
        length=24.0,
        location="Materials",
        active=True
    )
    service.add_item(item1)
    source_ja_id = item1.ja_id

    with PhotoService(live_server.storage) as photo_service:
        for i, color in enumerate(['lime', 'teal']):
            image = Image.new('RGB', (250, 250), color=color)
            temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            image.save(temp_file.name, format='JPEG', quality=90)
            temp_file.close()

            with open(temp_file.name, 'rb') as f:
                photo_data = f.read()
            photo_service.upload_photo(source_ja_id, photo_data, f"photo{i+1}.jpg", "image/jpeg")
            os.unlink(temp_file.name)

    # Create target items
    target_ja_ids = []
    for i in range(2):
        item = InventoryItem(
            ja_id=f"JA{111+i:06d}",
            item_type="Bar",
            material="Steel",
            length=36.0,
            location="Materials",
            active=True
        )
        service.add_item(item)
        target_ja_ids.append(item.ja_id)

    # Count photos BEFORE copy/paste
    with PhotoService(live_server.storage) as photo_service:
        photo_count_before = photo_service.session.query(func.count(Photo.id)).scalar()
        assoc_count_before = photo_service.session.query(func.count(ItemPhotoAssociation.id)).scalar()

    # Copy and paste photos via UI
    list_page = InventoryListPhotoCopyPage(page, live_server.url)
    list_page.navigate_to_list()

    list_page.select_item(source_ja_id)
    list_page.click_copy_photos_button()

    list_page.select_multiple_items(target_ja_ids)

    # Set up dialog handler to accept confirmation
    page.on("dialog", lambda dialog: dialog.accept())
    list_page.click_paste_photos_button()
    list_page.wait_for_toast()

    # Count photos AFTER copy/paste
    with PhotoService(live_server.storage) as photo_service:
        photo_count_after = photo_service.session.query(func.count(Photo.id)).scalar()
        assoc_count_after = photo_service.session.query(func.count(ItemPhotoAssociation.id)).scalar()

    # CRITICAL: BLOB count should remain unchanged
    assert photo_count_after == photo_count_before, \
        f"Photo BLOB count should remain {photo_count_before}, but got {photo_count_after}"

    # Association count should increase by (2 photos × 2 targets) = 4
    expected_assoc_increase = 2 * 2
    actual_assoc_increase = assoc_count_after - assoc_count_before
    assert actual_assoc_increase == expected_assoc_increase, \
        f"Association count should increase by {expected_assoc_increase}, but increased by {actual_assoc_increase}"


@pytest.mark.e2e
def test_button_states_based_on_selection(live_server, page):
    """Test that copy/paste buttons are enabled/disabled correctly"""
    from app.mariadb_inventory_service import InventoryService
    from app.database import InventoryItem
    service = InventoryService(live_server.storage)

    # Create items
    item1 = InventoryItem(
        ja_id="JA000113",
        item_type="Plate",
        material="Aluminum",
        length=12.0,
        width=6.0,
        location="Storage",
        active=True
    )
    service.add_item(item1)

    with PhotoService(live_server.storage) as photo_service:
        image = Image.new('RGB', (150, 150), color='gold')
        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        image.save(temp_file.name, format='JPEG', quality=90)
        temp_file.close()

        with open(temp_file.name, 'rb') as f:
            photo_data = f.read()
        photo_service.upload_photo(item1.ja_id, photo_data, "photo.jpg", "image/jpeg")
        os.unlink(temp_file.name)

    item2 = InventoryItem(
        ja_id="JA000114",
        item_type="Plate",
        material="Steel",
        length=12.0,
        width=6.0,
        location="Storage",
        active=True
    )
    service.add_item(item2)

    list_page = InventoryListPhotoCopyPage(page, live_server.url)
    list_page.navigate_to_list()
    page.reload()  # Ensure fresh data is loaded
    page.wait_for_load_state("networkidle")

    # Initially, with nothing selected, both buttons should be disabled
    # (Copy requires 1 selected, Paste requires selection + clipboard)
    assert not list_page.is_copy_photos_button_enabled()
    assert not list_page.is_paste_photos_button_enabled()

    # Select one item with photos - Copy should be enabled, Paste still disabled
    list_page.select_item(item1.ja_id)
    page.wait_for_timeout(500)  # Wait for button state to update
    assert list_page.is_copy_photos_button_enabled()
    assert not list_page.is_paste_photos_button_enabled()

    # Copy photos - clipboard now active
    list_page.click_copy_photos_button()
    assert list_page.is_clipboard_banner_visible()

    # Select target item - Paste should now be enabled
    list_page.select_item(item2.ja_id)
    page.wait_for_timeout(500)  # Wait for button state to update
    assert list_page.is_paste_photos_button_enabled()
