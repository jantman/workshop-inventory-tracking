"""E2E tests for removing several of an item's photos at once (issue #96).

The gallery already had checkboxes and a "Delete Selected" button. What it did
with them was confirm the batch and then confirm again for every photo in it --
thirteen prompts to delete twelve photos -- and it offered no select-all. These
tests pin both corrections.

**The assertions that matter are counts of dialogs.** A test that waits for *a*
confirmation passes against the defect this file exists to prevent, because the
defect is the extra twelve.
"""

import io

import pytest
from PIL import Image
from playwright.sync_api import expect

from app.photo_service import PhotoService

GALLERY = "#photo-manager-container"
CARDS = f"{GALLERY} .photo-card"
SELECTORS = f"{GALLERY} .photo-select"
SELECT_ALL = f"{GALLERY} .select-all-photos"
DELETE_SELECTED = f"{GALLERY} .delete-selected-btn"
DELETE_ONE = f"{CARDS} .photo-delete-btn"


def jpeg_bytes(colour):
    """A real JPEG -- the server decodes and resizes what it is given."""
    buffer = io.BytesIO()
    Image.new('RGB', (120, 90), color=colour).save(buffer, format='JPEG')
    return buffer.getvalue()


def record_dialogs(page, accept=True):
    """Record every ``confirm`` the page raises, and answer them all.

    ``page.on`` rather than ``page.once``: an unanswered second prompt blocks the
    page until something unrelated times out, which is a far worse failure to
    read than a list with two entries in it.
    """
    messages = []

    def handler(dialog):
        messages.append(dialog.message)
        dialog.accept() if accept else dialog.dismiss()

    page.on("dialog", handler)
    return messages


@pytest.fixture
def item_with_photos(live_server):
    """An item carrying four photos, seeded directly.

    Driving the upload widget four times costs seconds per photo and the widget
    is not what is under test here.

    **The product attachments are load-bearing, not scenery.** A photo has two
    ids -- the ``Photo`` row and the ``ItemPhotoAssociation`` that ties it to an
    item -- and the two API routes disagree about which one they take: ``GET``
    wants the Photo, ``DELETE`` wants the association. They are equal only while
    every Photo has exactly one association, which is true of a fresh database
    and of nothing else. Attaching images to a product first creates Photo rows
    with no association at all and pushes the sequences apart, which is the
    ordinary state of any database this application has been used on.

    Without this, every test below passes against a gallery that deletes by the
    wrong id.
    """
    product = live_server.add_test_products([{'description': 'id-sequence spacer'}])[0]
    live_server.add_product_attachments(product.id, 3)

    ja_id = "JA000900"
    live_server.add_test_data([{
        'ja_id': ja_id,
        'item_type': 'Bar',
        'shape': 'Rectangular',
        'material': 'Steel',
        'length': '24',
        'width': '2',
        'thickness': '0.25',
        'location': 'Bin A',
        'active': True,
    }])

    colours = ['red', 'green', 'blue', 'yellow']
    with PhotoService(live_server.storage) as photos:
        for index, colour in enumerate(colours):
            photos.upload_photo(
                ja_id, jpeg_bytes(colour), f"photo{index}.jpg", "image/jpeg"
            )

    return ja_id


def open_gallery(page, live_server, ja_id, count):
    """Open the Edit Item form and leave the gallery settled at ``count``."""
    page.goto(f"{live_server.url}/inventory/edit/{ja_id}")
    expect(page.locator(CARDS)).to_have_count(count)


@pytest.mark.e2e
def test_deleting_a_selection_asks_once(page, live_server, item_with_photos):
    """FR-015: one action, one prompt. US3 scenario 1.

    Three of the four are taken so the remaining one proves the batch stopped
    where it was told to.
    """
    open_gallery(page, live_server, item_with_photos, 4)

    messages = record_dialogs(page)
    for index in range(3):
        page.locator(SELECTORS).nth(index).check()
    page.locator(DELETE_SELECTED).click()

    expect(page.locator(CARDS)).to_have_count(1)
    assert messages == ["Delete 3 photos?"], messages


@pytest.mark.e2e
def test_dismissing_the_confirmation_deletes_no_photos(
    page, live_server, item_with_photos
):
    """US3 scenario 2: declining has to mean nothing happened."""
    open_gallery(page, live_server, item_with_photos, 4)

    messages = record_dialogs(page, accept=False)
    for index in range(2):
        page.locator(SELECTORS).nth(index).check()
    page.locator(DELETE_SELECTED).click()

    assert messages == ["Delete 2 photos?"], messages
    expect(page.locator(CARDS)).to_have_count(4)

    # Nothing reached the server either -- a reload is the only honest way to ask.
    open_gallery(page, live_server, item_with_photos, 4)


@pytest.mark.e2e
def test_select_all_ticks_every_photo_and_toggles_back_off(
    page, live_server, item_with_photos
):
    """FR-016, US3 scenario 3: the gallery had checkboxes but no way to tick
    them all."""
    open_gallery(page, live_server, item_with_photos, 4)

    page.locator(SELECT_ALL).check()

    boxes = page.locator(SELECTORS)
    for index in range(4):
        expect(boxes.nth(index)).to_be_checked()
    expect(page.locator(DELETE_SELECTED)).to_contain_text("4")

    page.locator(SELECT_ALL).uncheck()

    for index in range(4):
        expect(boxes.nth(index)).not_to_be_checked()


@pytest.mark.e2e
def test_select_all_then_delete_clears_the_gallery_in_one_prompt(
    page, live_server, item_with_photos
):
    """FR-015 and FR-016 together -- the whole point of the story."""
    open_gallery(page, live_server, item_with_photos, 4)

    messages = record_dialogs(page)
    page.locator(SELECT_ALL).check()
    page.locator(DELETE_SELECTED).click()

    expect(page.locator(CARDS)).to_have_count(0)
    assert messages == ["Delete 4 photos?"], messages


@pytest.mark.e2e
def test_one_photo_is_named_in_the_singular(page, live_server, item_with_photos):
    """"1 photo(s)" reads as a bug in the application."""
    open_gallery(page, live_server, item_with_photos, 4)

    messages = record_dialogs(page)
    page.locator(SELECTORS).first.check()
    page.locator(DELETE_SELECTED).click()

    expect(page.locator(CARDS)).to_have_count(3)
    assert messages == ["Delete 1 photo?"], messages


@pytest.mark.e2e
def test_the_single_photo_delete_still_confirms_for_itself(
    page, live_server, item_with_photos
):
    """FR-017: the per-photo button keeps its own confirmation and deletes only
    its own photo. US3 scenario 5."""
    open_gallery(page, live_server, item_with_photos, 4)

    messages = record_dialogs(page)
    page.locator(DELETE_ONE).first.click()

    expect(page.locator(CARDS)).to_have_count(3)
    assert len(messages) == 1, messages
    assert "photo0.jpg" in messages[0], messages


@pytest.mark.e2e
def test_a_read_only_gallery_offers_no_selection_controls(
    page, live_server, item_with_photos
):
    """FR-016, US3 scenario 4.

    The read-only gallery is the item details modal on the inventory list. It
    has never offered the per-photo delete or the checkboxes, and the select-all
    must not be the thing that breaks that -- which it cannot be, because it
    lives inside the block that is already omitted when read-only.
    """
    page.goto(f"{live_server.url}/inventory")

    row = page.locator(f"tr:has-text('{item_with_photos}')")
    expect(row).to_be_visible()
    row.locator("button[title='View Details']").click()

    modal = page.locator("#item-details-modal")
    expect(modal).to_be_visible()

    # Establish the gallery first: every assertion below is a negative, and an
    # unrendered region satisfies all of them.
    photos = modal.locator("#item-details-photos")
    expect(photos.locator(".photo-card")).to_have_count(4)

    expect(photos.locator(".select-all-photos")).to_have_count(0)
    expect(photos.locator(".delete-selected-btn")).to_have_count(0)
    expect(photos.locator(".photo-select")).to_have_count(0)
    expect(photos.locator(".photo-delete-btn")).to_have_count(0)
