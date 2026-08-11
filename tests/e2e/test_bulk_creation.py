"""
E2E Tests for Bulk Item Creation

Tests the "Quantity to Create" feature that allows creating multiple identical
items with sequential JA IDs in a single form submission.
"""

import json
import re

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.base_page import BasePage
from tests.e2e.waits import (
    wait_for_modal_hidden,
    wait_for_modal_shown,
    wait_for_select_populated,
)


def count_add_posts(page):
    """Count POST requests to /inventory/add dispatched from this point on.

    Returns a single-element list used as a mutable counter; read it as
    `counter[0]`. This counts requests *dispatched*, not responses received,
    which is exactly what FR-001 constrains: one press of a submit button must
    produce one request, regardless of how the server answers it.

    Attach this before the submission being measured -- Playwright delivers
    `request` events for the page's whole lifetime, so a listener attached
    afterwards sees nothing.
    """
    counter = [0]

    def _on_request(request):
        if request.method == "POST" and request.url.endswith("/inventory/add"):
            counter[0] += 1

    page.on("request", _on_request)
    return counter


class BulkCreationPage(BasePage):
    """Page object for bulk item creation workflow"""

    def navigate_to_add_page(self):
        """Navigate to add inventory page"""
        self.page.goto(f"{self.base_url}/inventory/add")
        self.page.wait_for_load_state("domcontentloaded")

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
        """Set the quantity to create field.

        updateBulkCreationInfo() is bound to `input` and rewrites the preview
        synchronously, so it has already run by the time fill() returns and
        get_bulk_creation_info_text() cannot read a stale message.
        """
        self.page.locator("#quantity_to_create").fill(str(quantity))

    def get_bulk_creation_info_text(self):
        """Get the bulk creation info message"""
        info_div = self.page.locator("#bulk-creation-info")
        if info_div.is_visible():
            return self.page.locator("#bulk-creation-message").inner_text()
        return None

    def submit_form(self):
        """Submit the add item form and wait for the submission to resolve.

        The form takes two different paths and this helper drives both. With
        quantity 1 it is an ordinary POST that replaces the document, so marking
        the document and waiting for the marker to vanish is the signal. With
        quantity > 1 it is AJAX: the handler awaits the POST and only then raises
        a toast and opens the bulk label modal, so either of those appearing
        proves the response landed. Any earlier toast is cleared first so this
        cannot settle on a stale one.
        """
        self.page.evaluate(
            """() => {
                window.__awaitingSubmit = true;
                const c = document.getElementById('toast-container');
                if (c) c.innerHTML = '';
            }"""
        )
        self.page.locator("#submit-btn").click()
        self.page.wait_for_function(
            """() => window.__awaitingSubmit === undefined
                  || !!document.querySelector('#toast-container .toast')
                  || !!document.querySelector('#bulkLabelPrintingModal.show')"""
        )

    def submit_and_continue(self):
        """Press **Add & Continue** and wait for that submission to resolve.

        Same settling strategy as submit_form(), for the same reasons -- see
        its docstring. The only difference is which button is pressed, so the
        body is deliberately identical rather than a second waiting strategy
        that could drift from the first.
        """
        self.page.evaluate(
            """() => {
                window.__awaitingSubmit = true;
                const c = document.getElementById('toast-container');
                if (c) c.innerHTML = '';
            }"""
        )
        self.page.locator("#submit-and-continue-btn").click()
        self.page.wait_for_function(
            """() => window.__awaitingSubmit === undefined
                || !!document.querySelector('#toast-container .toast')
                || !!document.querySelector('#bulkLabelPrintingModal.show')"""
        )

    def get_success_message(self):
        """Get success message text"""
        alert = self.page.locator(".alert-success").first
        expect(alert).to_be_visible()
        return alert.inner_text()

    def is_bulk_label_modal_visible(self):
        """Check if bulk label printing modal is shown.

        is_visible() does not wait, so the modal has to be established first --
        Bootstrap fades it in after the AJAX response, and every caller here is
        asserting that it did appear.
        """
        wait_for_modal_shown(self.page, "bulkLabelPrintingModal")
        modal = self.page.locator("#bulkLabelPrintingModal")
        return modal.is_visible()

    def get_modal_ja_ids(self):
        """Get the list of JA IDs shown in the modal.

        count() does not wait either, and the list is rendered by the same
        handler that opens the modal, so an unestablished modal reads as zero
        JA IDs rather than as "not ready yet".
        """
        wait_for_modal_shown(self.page, "bulkLabelPrintingModal")
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
        """Close the bulk label printing modal and wait for it to finish closing.

        Bootstrap fades the modal out; until that finishes the backdrop still
        intercepts clicks, so anything the caller does next lands on nothing.
        """
        self.page.locator("#bulk-label-modal-close-btn").click()
        wait_for_modal_hidden(self.page, "bulkLabelPrintingModal")


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
        'shape': 'Hex',
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
        assert item.shape == 'Hex'
        assert item.material == 'Brass'
        assert item.length == 36.0
        assert item.width == 0.5
        assert item.location == 'Storage B'
        assert item.sub_location == 'Shelf 3'
        assert item.notes == 'Comprehensive field test'
        assert item.purchase_location == 'McMaster-Carr'
        assert item.vendor == 'McMaster'
        assert item.vendor_part == '8974K123'


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
def test_bulk_add_and_continue_sends_one_request(page, live_server):
    """One press of Add & Continue at quantity > 1 dispatches exactly one POST.

    This is FR-001 asserted directly rather than inferred from a symptom, and
    it holds the single-submission property in place now that the continue
    button is wired through one listener rather than two.
    """
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    item_data = {
        'item_type': 'Bar',
        'shape': 'Round',
        'material': 'Aluminum',
        'length': '24',
        'width': '1',
        'location': 'Storage A',
    }
    bulk_page.fill_item_details(item_data)
    bulk_page.set_quantity_to_create(3)

    post_count = count_add_posts(page)

    bulk_page.submit_and_continue()
    wait_for_modal_shown(page, "bulkLabelPrintingModal")

    assert post_count[0] == 1, (
        f"Add & Continue dispatched {post_count[0]} POSTs to /inventory/add; "
        "one press must produce exactly one request"
    )


@pytest.mark.e2e
def test_bulk_add_and_continue_creates_exact_count(page, live_server):
    """Add & Continue at quantity N creates exactly N items and shows no error.

    FR-002 and FR-003. Both assertions are here because a duplicated bulk
    submission can show up either way: two concurrent creations that collide on
    JA IDs surface as an error toast beside the success dialog, while two that
    serialise record 2N items and show no error at all. The count is the
    assertion that catches the silent variant.
    """
    from app.mariadb_inventory_service import InventoryService

    service = InventoryService(live_server.storage)
    count_before = len(service.get_all_items())

    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    item_data = {
        'item_type': 'Plate',
        'shape': 'Rectangular',
        'material': 'Steel',
        'length': '12',
        'width': '6',
        'thickness': '0.25',
        'location': 'Shop Floor',
    }
    bulk_page.fill_item_details(item_data)
    bulk_page.set_quantity_to_create(3)

    bulk_page.submit_and_continue()

    # The open modal is what establishes the toast region for the negative
    # assertion below -- "no error toast" passes trivially against a page that
    # has not finished the submission.
    wait_for_modal_shown(page, "bulkLabelPrintingModal")

    error_toasts = page.locator("#toast-container .toast.text-bg-error")
    expect(error_toasts).to_have_count(0)

    count_after = len(service.get_all_items())
    assert count_after - count_before == 3, (
        f"expected 3 new items, got {count_after - count_before}"
    )


@pytest.mark.e2e
def test_bulk_add_and_continue_returns_to_empty_form(page, live_server):
    """Dismissing the bulk dialog after Add & Continue lands on a fresh form.

    FR-006. Before the fix the bulk path had no notion of "continue" at all --
    the dialog closed and left the filled-in form exactly as it was, so the
    button did not do what its label says.
    """
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    bulk_page.fill_item_details({
        'item_type': 'Bar',
        'shape': 'Round',
        'material': 'Aluminum',
        'length': '24',
        'width': '1',
        'location': 'Storage A',
        'notes': 'Batch one',
    })
    bulk_page.set_quantity_to_create(3)

    bulk_page.submit_and_continue()
    wait_for_modal_shown(page, "bulkLabelPrintingModal")
    bulk_page.close_modal()

    expect(page).to_have_url(re.compile(r"/inventory/add$"))

    # CLAUDE.md pattern G: autoPopulateJaId() writes #ja_id only after awaiting
    # /api/inventory/next-ja-id, so the form is not actually ready -- and the
    # per-item assertions below are not meaningful -- until that write lands.
    expect(page.locator("#ja_id")).not_to_have_value("")

    expect(page.locator("#notes")).to_have_value("")
    expect(page.locator("#length")).to_have_value("")


@pytest.mark.e2e
def test_carry_forward_after_bulk_add_and_continue(page, live_server):
    """Carry Forward restores the batch just created (FR-008).

    The values reach the fresh form through sessionStorage, written by
    handleSubmit() before the request goes out, which is the same route the
    single-item continue path already uses.
    """
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    bulk_page.fill_item_details({
        'item_type': 'Plate',
        'shape': 'Rectangular',
        'material': 'Stainless Steel',
        'length': '12',
        'width': '6',
        'thickness': '0.25',
        'location': 'Materials Rack',
    })
    bulk_page.set_quantity_to_create(3)

    bulk_page.submit_and_continue()
    wait_for_modal_shown(page, "bulkLabelPrintingModal")
    bulk_page.close_modal()

    expect(page).to_have_url(re.compile(r"/inventory/add$"))
    expect(page.locator("#ja_id")).not_to_have_value("")

    page.locator("#carry-forward-btn").click()

    # carryForwardData() raises this toast as its last step, after populating
    # every field, so the toast appearing means the fields are written.
    expect(page.locator("#toast-container .toast-body")).to_contain_text(
        "carried forward"
    )

    expect(page.locator("#material")).to_have_value("Stainless Steel")
    expect(page.locator("#location")).to_have_value("Materials Rack")
    expect(page.locator("#item_type")).to_have_value("Plate")
    expect(page.locator("#shape")).to_have_value("Rectangular")


@pytest.mark.e2e
def test_bulk_add_does_not_return_to_empty_form(page, live_server):
    """Plain Add at quantity > 1 must NOT navigate away (FR-007).

    This is the assertion most easily lost: if Add starts continuing too, every
    count is still right and the two buttons have silently collapsed into one.
    """
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    bulk_page.fill_item_details({
        'item_type': 'Bar',
        'shape': 'Round',
        'material': 'Copper',
        'length': '18',
        'width': '0.75',
        'location': 'Storage D',
    })
    bulk_page.set_quantity_to_create(3)

    bulk_page.submit_form()
    wait_for_modal_shown(page, "bulkLabelPrintingModal")
    url_after_submit = page.url
    bulk_page.close_modal()

    assert page.url == url_after_submit
    expect(page.locator("#material")).to_have_value("Copper")


@pytest.mark.e2e
def test_plain_add_after_bulk_continue_is_not_a_continue(page, live_server):
    """A bulk Add & Continue must not turn a later plain Add into a continue.

    This is the one case in this file that was reproducibly broken before the
    fix. The old handler appended a fresh `submit_type=continue` input per
    continue submission, and a bulk submission never navigates away, so the
    input survived. The single-item path submits with form.submit(), which
    carries no submitter, leaving that stale input as the only `submit_type` in
    the payload -- so the next plain Add was read by the server as a continue
    and returned to the Add form instead of the inventory list.

    Two changes close it: the submit type now lives in one persistent field
    that is assigned on every submission, and a bulk continue re-renders the
    form.
    """
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()

    bulk_page.fill_item_details({
        'item_type': 'Bar',
        'shape': 'Round',
        'material': 'Aluminum',
        'length': '24',
        'width': '1',
        'location': 'Storage A',
    })
    bulk_page.set_quantity_to_create(3)
    bulk_page.submit_and_continue()
    wait_for_modal_shown(page, "bulkLabelPrintingModal")
    bulk_page.close_modal()

    expect(page).to_have_url(re.compile(r"/inventory/add$"))
    expect(page.locator("#ja_id")).not_to_have_value("")

    # Now a plain, single-item Add. It must land on the inventory list.
    bulk_page.fill_item_details({
        'item_type': 'Bar',
        'shape': 'Round',
        'material': 'Brass',
        'length': '10',
        'width': '1',
        'location': 'Storage B',
    })
    bulk_page.set_quantity_to_create(1)
    bulk_page.submit_form()

    expect(page).to_have_url(re.compile(r"/inventory(\?.*)?$"))


@pytest.mark.e2e
def test_repeated_submission_creates_one_batch(page, live_server):
    """Two submissions fired back to back produce one batch (FR-005).

    Disabling the buttons covers a double *click*, but Enter still reaches the
    form while they are disabled, so the re-entrancy flag is what actually
    holds. requestSubmit() models that: it raises a real submit event carrying
    the continue button as submitter, exactly as Enter would, and bypasses the
    disabled state a second click would run into.
    """
    from app.mariadb_inventory_service import InventoryService

    service = InventoryService(live_server.storage)
    count_before = len(service.get_all_items())

    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()
    bulk_page.fill_item_details({
        'item_type': 'Bar',
        'shape': 'Round',
        'material': 'Aluminum',
        'length': '24',
        'width': '1',
        'location': 'Storage A',
    })
    bulk_page.set_quantity_to_create(4)

    post_count = count_add_posts(page)

    page.evaluate(
        """() => {
            const c = document.getElementById('toast-container');
            if (c) c.innerHTML = '';
            const form = document.getElementById('add-item-form');
            const btn = document.getElementById('submit-and-continue-btn');
            form.requestSubmit(btn);
            form.requestSubmit(btn);
        }"""
    )
    wait_for_modal_shown(page, "bulkLabelPrintingModal")

    assert post_count[0] == 1, (
        f"two rapid submissions dispatched {post_count[0]} requests"
    )
    assert len(service.get_all_items()) - count_before == 4

    # FR-005: both controls come back to their normal labels and enabled state.
    expect(page.locator("#submit-btn")).to_be_enabled()
    expect(page.locator("#submit-and-continue-btn")).to_be_enabled()
    expect(page.locator("#submit-btn")).not_to_contain_text("Adding...")


@pytest.mark.e2e
def test_enter_key_submits_as_plain_add(page, live_server):
    """Enter in a text field behaves as Add, not as Add & Continue.

    Implicit submission reports the form's first submit button as the
    submitter, which is #submit-btn. The observable consequence is that
    dismissing the dialog does not navigate away.
    """
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()
    bulk_page.fill_item_details({
        'item_type': 'Bar',
        'shape': 'Round',
        'material': 'Brass',
        'length': '24',
        'width': '1',
        'location': 'Storage E',
    })
    bulk_page.set_quantity_to_create(4)

    # Implicit submission is silent when the form is invalid -- it raises the
    # submit event, the handler finds checkValidity() false and returns, and
    # nothing observable happens. So both preconditions are established first:
    # the material is accepted (CLAUDE.md pattern F, is-valid rather than the
    # absence of is-invalid) and the auto-populated JA ID has landed (pattern
    # G, autoPopulateJaId() writes it only after awaiting its fetch).
    expect(page.locator("#material")).to_have_class(
        re.compile(r"\bis-valid\b"))
    expect(page.locator("#ja_id")).not_to_have_value("")

    post_count = count_add_posts(page)

    # #ja_id and #location swallow Enter for the barcode scanner, so this uses
    # an ordinary text field.
    page.locator("#width").press("Enter")
    wait_for_modal_shown(page, "bulkLabelPrintingModal")

    assert post_count[0] == 1

    url_after_submit = page.url
    bulk_page.close_modal()

    assert page.url == url_after_submit
    expect(page.locator("#material")).to_have_value("Brass")


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


ITEM_DATA_FOR_PRINTING = {
    'item_type': 'Plate',
    'shape': 'Rectangular',
    'material': 'Steel',
    'length': '12',
    'width': '6',
    'thickness': '0.25',
    'location': 'Shop Floor',
}


def _capture_print_payloads(page):
    """Collect the decoded bodies of every POST to /api/labels/print."""
    payloads = []

    def handle_request(request):
        if "/api/labels/print" in request.url and request.method == "POST":
            payloads.append(json.loads(request.post_data))

    page.on("request", handle_request)
    return payloads


def _create_batch_and_open_print_dialog(page, live_server, quantity):
    """Create `quantity` items in bulk and return the page object plus JA IDs.

    The label type options now arrive from GET /api/labels/types rather than
    being hardcoded in the template, so the select has to be waited on.
    """
    bulk_page = BulkCreationPage(page, live_server.url)
    bulk_page.navigate_to_add_page()
    bulk_page.fill_item_details(ITEM_DATA_FOR_PRINTING)
    bulk_page.set_quantity_to_create(quantity)
    bulk_page.submit_form()

    assert bulk_page.is_bulk_label_modal_visible()
    wait_for_select_populated(page, "bulk-label-type")

    return bulk_page, bulk_page.get_modal_ja_ids()


@pytest.mark.e2e
def test_post_creation_dialog_offers_real_label_types(page, live_server):
    """Story 3 scenario 1: the real label types, and none of the old sizes"""
    _create_batch_and_open_print_dialog(page, live_server, 2)

    label_select = page.locator("#bulk-label-type")
    expect(label_select).to_be_visible()

    for label_type in ['Sato 1x2', 'Sato 1x2 Flag', 'Sato 2x4',
                       'Sato 2x4 Flag', 'Sato 4x6', 'Sato 4x6 Flag']:
        expect(label_select.locator(f"option[value='{label_type}']")).to_have_count(1)

    # The select is established above, so these negative assertions are real
    # rather than passing against a dialog that has not rendered. Nothing in
    # this dialog may read as a label *size* any more.
    for old_size in ['2.25x1.25', '2.25x0.5', 'custom']:
        expect(label_select.locator(f"option[value='{old_size}']")).to_have_count(0)

    expect(page.locator("#bulk-label-size")).to_have_count(0)

    # Print All stays disabled until a type is chosen, as on the list page.
    expect(page.locator("#bulk-print-all-btn")).to_be_disabled()
    page.locator("#bulk-label-type").select_option("Sato 1x2")
    expect(page.locator("#bulk-print-all-btn")).to_be_enabled()


@pytest.mark.e2e
def test_post_creation_dialog_prints_at_default_count(page, live_server):
    """Story 3 scenario 2: a default-count print succeeds -- it could not before"""
    payloads = _capture_print_payloads(page)

    bulk_page, ja_ids = _create_batch_and_open_print_dialog(page, live_server, 3)
    assert len(ja_ids) == 3

    page.locator("#bulk-label-type").select_option("Sato 1x2")
    page.locator("#bulk-print-all-btn").click()

    # The completion line renders after every request settles.
    status_span = page.locator("#bulk-print-status")
    expect(status_span).to_have_text('Complete: 3 labels for 3 items, 0 failed')

    # Zero failures: before this repair the dialog sent a label_size the
    # endpoint has no field for and omitted the label_type it requires, so
    # every one of these requests came back 400.
    expect(page.locator("#bulk-print-errors")).not_to_be_visible()

    assert payloads == [
        {"ja_id": ja_id, "label_type": "Sato 1x2", "label_count": 1}
        for ja_id in ja_ids
    ]


@pytest.mark.e2e
def test_post_creation_dialog_honors_a_label_count(page, live_server):
    """Story 3 scenario 3: a count of 2 sends one request per JA ID carrying it"""
    payloads = _capture_print_payloads(page)

    bulk_page, ja_ids = _create_batch_and_open_print_dialog(page, live_server, 4)
    assert len(ja_ids) == 4

    page.locator("#bulk-label-type").select_option("Sato 2x4")
    page.locator("#bulk-label-count").fill("2")
    page.locator("#bulk-print-all-btn").click()

    status_span = page.locator("#bulk-print-status")
    expect(status_span).to_have_text('Complete: 8 labels for 4 items, 0 failed')

    assert payloads == [
        {"ja_id": ja_id, "label_type": "Sato 2x4", "label_count": 2}
        for ja_id in ja_ids
    ]


@pytest.mark.e2e
def test_post_creation_label_count_starts_at_one_not_the_quantity(page, live_server):
    """Story 3 scenario 4: a batch of 8 still opens with a label count of 1"""
    _create_batch_and_open_print_dialog(page, live_server, 8)

    count_input = page.locator("#bulk-label-count")
    expect(count_input).to_be_visible()
    # How many items were created and how many labels each gets are different
    # numbers; nothing reads one to seed the other.
    expect(count_input).to_have_value("1")

    expect(page.locator("label[for='bulk-label-count']")).to_have_text(
        'Labels per item'
    )


@pytest.mark.e2e
def test_post_creation_dialog_dismissed_leaves_items_intact(page, live_server):
    """Story 3 scenario 5: dismissing the dialog does not touch the created items"""
    bulk_page, ja_ids = _create_batch_and_open_print_dialog(page, live_server, 3)
    assert len(ja_ids) == 3

    bulk_page.close_modal()

    # Printing is an offer, never a condition of the creation.
    from app.mariadb_inventory_service import InventoryService
    service = InventoryService(live_server.storage)
    for ja_id in ja_ids:
        item = service.get_item(ja_id)
        assert item is not None, f"Item {ja_id} not found after dismissing the dialog"
        assert item.active is True


@pytest.mark.e2e
@pytest.mark.parametrize("bad_count", ["0", "100", "2.5", ""])
def test_post_creation_label_count_refused_prints_nothing(page, live_server, bad_count):
    """An invalid count on this dialog prints nothing and says why"""
    payloads = _capture_print_payloads(page)

    _create_batch_and_open_print_dialog(page, live_server, 2)

    page.locator("#bulk-label-type").select_option("Sato 1x2")
    page.locator("#bulk-label-count").fill(bad_count)
    page.locator("#bulk-print-all-btn").click()

    # Written synchronously before the loop would have started, so its
    # visibility establishes that the handler ran and returned early.
    errors_div = page.locator("#bulk-print-errors")
    expect(errors_div).to_be_visible()
    expect(errors_div).to_contain_text(
        'Label count must be a whole number between 1 and 99'
    )

    assert payloads == []

    expect(page.locator("#bulkLabelPrintingModal")).to_be_visible()
    expect(page.locator("#bulk-label-type")).to_have_value("Sato 1x2")
    expect(page.locator("#bulk-print-progress")).not_to_be_visible()


@pytest.mark.e2e
def test_post_creation_corrected_count_clears_the_earlier_warning(page, live_server):
    """A refused count's warning must not survive the corrected retry.

    Same defect as the list page's dialog: the reset only runs when the modal
    is shown, so the warning would otherwise remain visible above a successful
    completion line.
    """
    _create_batch_and_open_print_dialog(page, live_server, 2)

    page.locator("#bulk-label-type").select_option("Sato 1x2")
    page.locator("#bulk-label-count").fill("0")
    page.locator("#bulk-print-all-btn").click()

    errors_div = page.locator("#bulk-print-errors")
    expect(errors_div).to_be_visible()

    page.locator("#bulk-label-count").fill("3")
    page.locator("#bulk-print-all-btn").click()

    status_span = page.locator("#bulk-print-status")
    expect(status_span).to_have_text('Complete: 6 labels for 2 items, 0 failed')

    expect(errors_div).not_to_be_visible()


# The singular "1 item" branch is deliberately not tested on this dialog: it
# only opens for a quantity of 2 or more (a quantity of 1 takes the ordinary
# single-item path), so one item is unreachable here. The list page's dialog,
# where a single item can be selected, covers that branch --
# test_bulk_summary_uses_singular_nouns_for_one.
