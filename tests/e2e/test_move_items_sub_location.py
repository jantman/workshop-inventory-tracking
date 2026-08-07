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

from tests.e2e.waits import scan_on_move_page, wait_for_move_executed


@pytest.mark.e2e
class TestMoveItemsSubLocation:
    """E2E tests for move items with sub-location functionality"""

    def add_test_item(self, page, live_server, ja_id, location, sub_location=None):
        """Helper to add a test item via the UI.

        Two things here are load-bearing and neither is obvious.

        The add page fills #ja_id itself, from GET /api/inventory/next-ja-id. Its
        "only if the field is empty" guard is checked *before* that await and the
        write lands *after* it, so a fill() issued in the gap has its selection
        collapsed by the page's write and appends instead of replacing --
        leaving "JA000102JA000102", which fails the field's pattern. Let the
        page's own write land first, and confirm ours stuck.

        And a submit the browser refuses leaves no trace in the DOM, so an item
        that was never created is invisible here. It resurfaces much later as a
        move that cannot be validated, with Execute greyed out and a 60s click
        timeout naming a button rather than the cause. Confirm the row exists.
        """
        page.goto(f'{live_server.url}/inventory/add')
        page.wait_for_load_state("domcontentloaded")

        # Fill in basic required fields
        ja_field = page.locator('#ja_id')
        expect(ja_field).not_to_have_value("")
        page.fill('#ja_id', ja_id)
        expect(ja_field).to_have_value(ja_id)
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
        page.wait_for_load_state("domcontentloaded")

        # See the docstring: confirm the item actually exists before any test
        # builds a move on top of it.
        response = page.request.get(f'{live_server.url}/api/items/{ja_id}')
        assert response.ok and response.json().get('success'), (
            f"{ja_id} was not created -- the add form refused the submit"
        )

    def test_move_no_sub_to_no_sub(self, page, live_server):
        """Test moving item with no sub-location to location with no sub-location"""
        # Add test item without sub-location
        self.add_test_item(page, live_server, 'JA000001', 'M1-A', None)

        # Navigate to move page
        page.goto(f'{live_server.url}/inventory/move')
        page.wait_for_load_state("domcontentloaded")

        # Enter move: JA ID -> Location (no sub-location).
        # Each scan waits on the signal for the transition it actually takes:
        # #scanner-status for the two synchronous ones, #queue-count after
        # >>DONE<< because handleDoneCode() finalises behind a fetch. See
        # scan_on_move_page.
        scan_on_move_page(page, 'JA000001')
        scan_on_move_page(page, 'M2-B')

        # Complete scanning
        scan_on_move_page(page, '>>DONE<<')

        # Verify queue shows correct sub-location info
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(2)).to_contain_text('None')  # Current sub-location
        expect(queue_table.locator('td').nth(4)).to_contain_text('None')  # New sub-location

        # Validate and execute
        page.locator('#validate-btn').click()

        # Handle confirmation dialog
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute-moves-btn').click()

        # executeMoves() awaits the batch-move POST and only then clears the
        # form; the server commits before it responds, so this is the commit.
        wait_for_move_executed(page)

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
        page.wait_for_load_state("domcontentloaded")

        # Enter move: JA ID -> Location -> Sub-location
        scan_on_move_page(page, 'JA000002')
        scan_on_move_page(page, 'M3-C')
        scan_on_move_page(page, 'Drawer 3')

        # Complete scanning
        scan_on_move_page(page, '>>DONE<<')

        # Verify queue shows correct sub-location info
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(2)).to_contain_text('None')  # Current sub-location
        expect(queue_table.locator('td').nth(4)).to_contain_text('Drawer 3')  # New sub-location

        # Validate and execute
        # Execute is disabled until validateMoves() has marked every queued item
        # validated, and click() waits for a button to be enabled, so the
        # validation round trip is waited on by the execute click below.
        page.locator('#validate-btn').click()

        # Handle confirmation dialog
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute-moves-btn').click()

        # executeMoves() awaits the batch-move POST and only then clears the
        # form; the server commits before it responds, so this is the commit.
        wait_for_move_executed(page)

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
        page.wait_for_load_state("domcontentloaded")

        # Enter move: JA ID -> Location (no sub-location)
        scan_on_move_page(page, 'JA000003')
        scan_on_move_page(page, 'M4-D')

        # Complete scanning (this should finalize without sub-location)
        scan_on_move_page(page, '>>DONE<<')

        # Verify queue shows sub-location being cleared
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(2)).to_contain_text('Drawer 1')  # Current sub-location
        expect(queue_table.locator('td').nth(4)).to_contain_text('Cleared')  # New sub-location shows "Cleared"

        # Validate and execute
        # Execute is disabled until validateMoves() has marked every queued item
        # validated, and click() waits for a button to be enabled, so the
        # validation round trip is waited on by the execute click below.
        page.locator('#validate-btn').click()

        # Handle confirmation dialog
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute-moves-btn').click()

        # executeMoves() awaits the batch-move POST and only then clears the
        # form; the server commits before it responds, so this is the commit.
        wait_for_move_executed(page)

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
        page.wait_for_load_state("domcontentloaded")

        # Enter move: JA ID -> Location -> Different Sub-location
        scan_on_move_page(page, 'JA000004')
        scan_on_move_page(page, 'M5-E')
        scan_on_move_page(page, 'Shelf 10')

        # Complete scanning
        scan_on_move_page(page, '>>DONE<<')

        # Verify queue shows sub-location change
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(2)).to_contain_text('Shelf 2')  # Current sub-location
        expect(queue_table.locator('td').nth(4)).to_contain_text('Shelf 10')  # New sub-location

        # Validate and execute
        # Execute is disabled until validateMoves() has marked every queued item
        # validated, and click() waits for a button to be enabled, so the
        # validation round trip is waited on by the execute click below.
        page.locator('#validate-btn').click()

        # Handle confirmation dialog
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute-moves-btn').click()

        # executeMoves() awaits the batch-move POST and only then clears the
        # form; the server commits before it responds, so this is the commit.
        wait_for_move_executed(page)

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
        page.wait_for_load_state("domcontentloaded")

        # Enter move: JA ID -> Location -> Same Sub-location
        scan_on_move_page(page, 'JA000005')
        scan_on_move_page(page, 'T-10')
        scan_on_move_page(page, 'Bin A')

        # Complete scanning
        scan_on_move_page(page, '>>DONE<<')

        # Validate and execute
        # Execute is disabled until validateMoves() has marked every queued item
        # validated, and click() waits for a button to be enabled, so the
        # validation round trip is waited on by the execute click below.
        page.locator('#validate-btn').click()

        # Handle confirmation dialog
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute-moves-btn').click()

        # executeMoves() awaits the batch-move POST and only then clears the
        # form; the server commits before it responds, so this is the commit.
        wait_for_move_executed(page)

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
        page.wait_for_load_state("domcontentloaded")


        # Move 1: No sub -> With sub
        scan_on_move_page(page, 'JA000101')
        scan_on_move_page(page, 'M10-Z')
        scan_on_move_page(page, 'Storage Bin A')

        # Move 2: With sub -> No sub (clearing)
        scan_on_move_page(page, 'JA000102')
        scan_on_move_page(page, 'M11-Y')

        # Move 3: With sub -> Different sub
        scan_on_move_page(page, 'JA000103')
        scan_on_move_page(page, 'T-20')
        scan_on_move_page(page, 'Shelf 99')

        # Complete scanning
        scan_on_move_page(page, '>>DONE<<')

        # Verify queue has 3 items
        expect(page.locator('#queue-count')).to_contain_text('3 items')

        # Validate and execute
        # Execute is disabled until validateMoves() has marked every queued item
        # validated, and click() waits for a button to be enabled, so the
        # validation round trip is waited on by the execute click below.
        page.locator('#validate-btn').click()

        # Handle confirmation dialog
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute-moves-btn').click()

        # executeMoves() awaits the batch-move POST and only then clears the
        # form; the server commits before it responds, so this is the commit.
        wait_for_move_executed(page)

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
        page.wait_for_load_state("domcontentloaded")


        # Test Metal storage pattern (M*)
        scan_on_move_page(page, 'JA000201')
        scan_on_move_page(page, 'M99-TestLoc')

        # Next input should be treated as sub-location or next JA ID
        # Let's enter a sub-location
        scan_on_move_page(page, 'Test Sub-Location')

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
        page.wait_for_load_state("domcontentloaded")


        scan_on_move_page(page, 'JA000202')

        # Test Threaded storage pattern (T*)
        scan_on_move_page(page, 'T-99')
        scan_on_move_page(page, '>>DONE<<')

        # Verify location was recognized
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(3)).to_contain_text('T-99')

    def test_other_location_pattern(self, page, live_server):
        """Test that 'Other' location is recognized"""
        # Add test item
        self.add_test_item(page, live_server, 'JA000203', 'M1-A', None)

        # Navigate to move page
        page.goto(f'{live_server.url}/inventory/move')
        page.wait_for_load_state("domcontentloaded")


        scan_on_move_page(page, 'JA000203')

        # Test 'Other' location
        scan_on_move_page(page, 'Other')

        # Add sub-location
        scan_on_move_page(page, 'Special Storage Area')

        # Verify both were recognized correctly
        queue_table = page.locator('#queue-items')
        expect(queue_table.locator('td').nth(3)).to_contain_text('Other')
        expect(queue_table.locator('td').nth(4)).to_contain_text('Special Storage Area')
