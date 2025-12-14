"""
E2E tests for move items with sub-location support.

Tests all scenarios specified in the feature requirements:
- Moving items with no sub-location to a location with no sub-location
- Moving items with no sub-location to a location with a sub-location
- Moving items with a sub-location to a location with no sub-location (clearing)
- Moving items with a sub-location to a location with a different sub-location
- Moving items with a sub-location to a location with the same sub-location
- Batch moves with mixed sub-location scenarios
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
class TestMoveItemsSubLocation:
    """E2E tests for move items with sub-location functionality"""

    def add_test_item(self, page, live_server, ja_id, location, sub_location=None):
        """Helper to add a test item via the UI"""
        page.goto(f'{live_server.url}/inventory/add')
        page.wait_for_load_state('networkidle')

        # Fill in basic required fields
        page.fill('#ja_id', ja_id)
        page.select_option('#item_type', 'Bar')
        page.select_option('#shape', 'Round')
        page.fill('#material', 'Steel')
        page.fill('#length', '100')
        page.fill('#width', '10')
        page.fill('#location', location)
        if sub_location:
            page.fill('#sub_location', sub_location)

        # Submit form
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')

    def test_move_no_sub_to_no_sub(self, page, live_server):
        """Test moving item with no sub-location to location with no sub-location"""
        # Add test item without sub-location
        self.add_test_item(page, live_server, 'JA000001', 'M1-A', None)

        # Navigate to move page
        page.goto(f'{live_server.url}/inventory/move')
        page.wait_for_load_state('networkidle')

        # Enter move: JA ID -> Location (no sub-location)
        barcode_input = page.locator('#barcode-input')
        barcode_input.fill('JA000001')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        barcode_input.fill('M2-B')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Complete scanning
        barcode_input.fill('>>DONE<<')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Verify queue shows correct sub-location info
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(2)).to_contain_text('None')  # Current sub-location
        expect(queue_table.locator('td').nth(4)).to_contain_text('None')  # New sub-location

        # Validate and execute
        page.locator('#validate-btn').click()
        page.wait_for_load_state('networkidle')

        # Handle confirmation dialog
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute-moves-btn').click()
        page.wait_for_load_state('networkidle')

        # Wait a bit for database transaction to fully commit
        page.wait_for_timeout(500)

        # Verify item was moved via API
        response = page.request.get(f'{live_server.url}/api/items/JA000001')
        data = response.json()
        assert data['item']['location'] == 'M2-B'
        assert data['item']['sub_location'] is None

    def test_move_no_sub_to_with_sub(self, page, live_server):
        """Test moving item with no sub-location to location with sub-location"""
        # Add test item without sub-location
        self.add_test_item(page, live_server, 'JA000002', 'M1-A', None)

        # Navigate to move page
        page.goto(f'{live_server.url}/inventory/move')
        page.wait_for_load_state('networkidle')

        # Enter move: JA ID -> Location -> Sub-location
        barcode_input = page.locator('#barcode-input')
        barcode_input.fill('JA000002')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        barcode_input.fill('M3-C')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        barcode_input.fill('Drawer 3')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Complete scanning
        barcode_input.fill('>>DONE<<')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Verify queue shows correct sub-location info
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(2)).to_contain_text('None')  # Current sub-location
        expect(queue_table.locator('td').nth(4)).to_contain_text('Drawer 3')  # New sub-location

        # Validate and execute
        page.locator('#validate-btn').click()
        page.wait_for_load_state('networkidle')

        # Handle confirmation dialog
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute-moves-btn').click()
        page.wait_for_load_state('networkidle')

        # Wait a bit for database transaction to fully commit
        page.wait_for_timeout(500)

        # Verify item has sub-location via API
        response = page.request.get(f'{live_server.url}/api/items/JA000002')
        data = response.json()
        assert data['success'] is True
        assert data['item']['location'] == 'M3-C'
        assert data['item']['sub_location'] == 'Drawer 3'

    def test_move_with_sub_to_no_sub_clears(self, page, live_server):
        """Test moving item with sub-location to location without sub-location (clearing)"""
        # Add test item with sub-location
        self.add_test_item(page, live_server, 'JA000003', 'M1-A', 'Drawer 1')

        # Navigate to move page
        page.goto(f'{live_server.url}/inventory/move')
        page.wait_for_load_state('networkidle')

        # Enter move: JA ID -> Location (no sub-location)
        barcode_input = page.locator('#barcode-input')
        barcode_input.fill('JA000003')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        barcode_input.fill('M4-D')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Complete scanning (this should finalize without sub-location)
        barcode_input.fill('>>DONE<<')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Verify queue shows sub-location being cleared
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(2)).to_contain_text('Drawer 1')  # Current sub-location
        expect(queue_table.locator('td').nth(4)).to_contain_text('Cleared')  # New sub-location shows "Cleared"

        # Validate and execute
        page.locator('#validate-btn').click()
        page.wait_for_load_state('networkidle')

        # Handle confirmation dialog
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute-moves-btn').click()
        page.wait_for_load_state('networkidle')

        # Wait a bit for database transaction to fully commit
        page.wait_for_timeout(500)

        # Verify sub-location was cleared via API
        response = page.request.get(f'{live_server.url}/api/items/JA000003')
        data = response.json()
        assert data['success'] is True
        assert data['item']['location'] == 'M4-D'
        assert data['item']['sub_location'] is None

    def test_move_with_sub_to_different_sub(self, page, live_server):
        """Test moving item with sub-location to location with different sub-location"""
        # Add test item with sub-location
        self.add_test_item(page, live_server, 'JA000004', 'M1-A', 'Shelf 2')

        # Navigate to move page
        page.goto(f'{live_server.url}/inventory/move')
        page.wait_for_load_state('networkidle')

        # Enter move: JA ID -> Location -> Different Sub-location
        barcode_input = page.locator('#barcode-input')
        barcode_input.fill('JA000004')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        barcode_input.fill('M5-E')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        barcode_input.fill('Shelf 10')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Complete scanning
        barcode_input.fill('>>DONE<<')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Verify queue shows sub-location change
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(2)).to_contain_text('Shelf 2')  # Current sub-location
        expect(queue_table.locator('td').nth(4)).to_contain_text('Shelf 10')  # New sub-location

        # Validate and execute
        page.locator('#validate-btn').click()
        page.wait_for_load_state('networkidle')

        # Handle confirmation dialog
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute-moves-btn').click()
        page.wait_for_load_state('networkidle')

        # Wait a bit for database transaction to fully commit
        page.wait_for_timeout(500)

        # Verify sub-location was changed via API
        response = page.request.get(f'{live_server.url}/api/items/JA000004')
        data = response.json()
        assert data['success'] is True
        assert data['item']['location'] == 'M5-E'
        assert data['item']['sub_location'] == 'Shelf 10'

    def test_move_with_sub_to_same_sub(self, page, live_server):
        """Test moving item with sub-location to same location and same sub-location"""
        # Add test item with sub-location
        self.add_test_item(page, live_server, 'JA000005', 'T-5', 'Bin A')

        # Navigate to move page
        page.goto(f'{live_server.url}/inventory/move')
        page.wait_for_load_state('networkidle')

        # Enter move: JA ID -> Location -> Same Sub-location
        barcode_input = page.locator('#barcode-input')
        barcode_input.fill('JA000005')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        barcode_input.fill('T-10')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        barcode_input.fill('Bin A')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Complete scanning
        barcode_input.fill('>>DONE<<')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Validate and execute
        page.locator('#validate-btn').click()
        page.wait_for_load_state('networkidle')

        # Handle confirmation dialog
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute-moves-btn').click()
        page.wait_for_load_state('networkidle')

        # Wait a bit for database transaction to fully commit
        page.wait_for_timeout(500)

        # Verify location changed but sub-location stayed the same
        response = page.request.get(f'{live_server.url}/api/items/JA000005')
        data = response.json()
        assert data['success'] is True
        assert data['item']['location'] == 'T-10'
        assert data['item']['sub_location'] == 'Bin A'

    def test_batch_move_mixed_sub_locations(self, page, live_server):
        """Test batch move with mixed sub-location scenarios"""
        # Add multiple test items
        self.add_test_item(page, live_server, 'JA000101', 'M1-A', None)
        self.add_test_item(page, live_server, 'JA000102', 'M2-B', 'Drawer 1')
        self.add_test_item(page, live_server, 'JA000103', 'T-5', 'Shelf 2')

        # Navigate to move page
        page.goto(f'{live_server.url}/inventory/move')
        page.wait_for_load_state('networkidle')

        barcode_input = page.locator('#barcode-input')

        # Move 1: No sub -> With sub
        barcode_input.fill('JA000101')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)
        barcode_input.fill('M10-Z')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)
        barcode_input.fill('Storage Bin A')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Move 2: With sub -> No sub (clearing)
        barcode_input.fill('JA000102')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)
        barcode_input.fill('M11-Y')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Move 3: With sub -> Different sub
        barcode_input.fill('JA000103')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)
        barcode_input.fill('T-20')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)
        barcode_input.fill('Shelf 99')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Complete scanning
        barcode_input.fill('>>DONE<<')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Verify queue has 3 items
        expect(page.locator('#queue-count')).to_contain_text('3 items')

        # Validate and execute
        page.locator('#validate-btn').click()
        page.wait_for_load_state('networkidle')

        # Handle confirmation dialog
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute-moves-btn').click()
        page.wait_for_load_state('networkidle')

        # Wait a bit for database transaction to fully commit
        page.wait_for_timeout(500)

        # Verify all items were moved correctly
        response1 = page.request.get(f'{live_server.url}/api/items/JA000101')
        data1 = response1.json()
        assert data1['item']['location'] == 'M10-Z'
        assert data1['item']['sub_location'] == 'Storage Bin A'

        response2 = page.request.get(f'{live_server.url}/api/items/JA000102')
        data2 = response2.json()
        assert data2['item']['location'] == 'M11-Y'
        assert data2['item']['sub_location'] is None

        response3 = page.request.get(f'{live_server.url}/api/items/JA000103')
        data3 = response3.json()
        assert data3['item']['location'] == 'T-20'
        assert data3['item']['sub_location'] == 'Shelf 99'

    def test_location_pattern_validation(self, page, live_server):
        """Test that location patterns are correctly recognized"""
        # Add test item
        self.add_test_item(page, live_server, 'JA000201', 'M1-A', None)

        # Navigate to move page
        page.goto(f'{live_server.url}/inventory/move')
        page.wait_for_load_state('networkidle')

        barcode_input = page.locator('#barcode-input')

        # Test Metal storage pattern (M*)
        barcode_input.fill('JA000201')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        barcode_input.fill('M99-TestLoc')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Next input should be treated as sub-location or next JA ID
        # Let's enter a sub-location
        barcode_input.fill('Test Sub-Location')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Verify it was added to queue
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(3)).to_contain_text('M99-TestLoc')
        expect(queue_table.locator('td').nth(4)).to_contain_text('Test Sub-Location')

    def test_threaded_location_pattern(self, page, live_server):
        """Test that threaded storage pattern (T*) is recognized"""
        # Add test item
        self.add_test_item(page, live_server, 'JA000202', 'M1-A', None)

        # Navigate to move page
        page.goto(f'{live_server.url}/inventory/move')
        page.wait_for_load_state('networkidle')

        barcode_input = page.locator('#barcode-input')

        barcode_input.fill('JA000202')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Test Threaded storage pattern (T*)
        barcode_input.fill('T-99')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        barcode_input.fill('>>DONE<<')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Verify location was recognized
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(3)).to_contain_text('T-99')

    def test_other_location_pattern(self, page, live_server):
        """Test that 'Other' location is recognized"""
        # Add test item
        self.add_test_item(page, live_server, 'JA000203', 'M1-A', None)

        # Navigate to move page
        page.goto(f'{live_server.url}/inventory/move')
        page.wait_for_load_state('networkidle')

        barcode_input = page.locator('#barcode-input')

        barcode_input.fill('JA000203')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Test 'Other' location
        barcode_input.fill('Other')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Add sub-location
        barcode_input.fill('Special Storage Area')
        barcode_input.press('Enter')
        page.wait_for_timeout(200)

        # Verify both were recognized correctly
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(3)).to_contain_text('Other')
        expect(queue_table.locator('td').nth(4)).to_contain_text('Special Storage Area')
