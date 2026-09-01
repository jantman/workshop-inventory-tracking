"""E2E tests for downloading an item's photo (issue #131).

Both controls that offer a download -- the button on a gallery card and the one
in the full-size viewer -- built their URL from the Photo id and pointed at a
handler that resolved that id as an association. The handler is fixed; these
tests are what says the buttons reach it.

**The product attachments in the fixture are load-bearing, not scenery.** A
photo has two ids -- the ``Photo`` row and the ``ItemPhotoAssociation`` that
ties it to an item -- and the routes on ``/api/photos/<id>`` disagree about
which one they take: ``GET`` and download want the Photo, ``DELETE`` wants the
association. They are equal only while every Photo has exactly one association,
which is true of a fresh database and of nothing else. Attaching images to a
product first creates Photo rows with no association at all and pushes the
sequences apart, which is the ordinary state of any database this application
has been used on. Without it these tests pass against the bug.

**What these tests deliberately do not assert: the filename.**
``photo-manager.js`` sets ``link.download = photo.name`` before clicking, and a
same-origin anchor's ``download`` attribute overrides ``Content-Disposition``,
so ``download.suggested_filename`` reads back the name the *page* chose. It
would be correct against a server that sent no filename at all. That assertion
lives in ``tests/unit/test_photo_download.py``, against the header.
"""

import io

import pytest
from PIL import Image
from playwright.sync_api import expect

from app.photo_service import PhotoService

GALLERY = "#photo-manager-container"
CARDS = f"{GALLERY} .photo-card"
DOWNLOAD_ONE = f"{CARDS} .photo-download-btn"
VIEW_ONE = f"{CARDS} .photo-view-btn"
# The viewer under test is the fallback modal, not PhotoSwipe: base.html:20,157
# skip the PhotoSwipe CDN loads on localhost/127.0.0.1, so viewPhoto() always
# takes its showFallbackImageModal() branch here. Scoped to .modal-footer
# because .modal-download-btn also appears in the PDF-unavailable notice.
MODAL_DOWNLOAD = "#fallback-image-modal .modal-footer .modal-download-btn"

JA_ID = "JA000901"


def jpeg_bytes(colour="red"):
    """A real JPEG -- the server decodes and resizes what it is given."""
    buffer = io.BytesIO()
    Image.new('RGB', (120, 90), color=colour).save(buffer, format='JPEG')
    return buffer.getvalue()


@pytest.fixture
def item_with_photo(live_server):
    """An item carrying one photo, on a database with drifted id sequences."""
    product = live_server.add_test_products([{'description': 'id-sequence spacer'}])[0]
    live_server.add_product_attachments(product.id, 3)

    live_server.add_test_data([{
        'ja_id': JA_ID,
        'item_type': 'Bar',
        'shape': 'Rectangular',
        'material': 'Steel',
        'length': '24',
        'width': '2',
        'thickness': '0.25',
        'location': 'Bin A',
        'active': True,
    }])

    data = jpeg_bytes()
    with PhotoService(live_server.storage) as photos:
        association = photos.upload_photo(JA_ID, data, "hex-bar.jpg", "image/jpeg")
        photo_id = association.photo_id
        association_id = association.id

    assert photo_id != association_id, (
        "the fixture stopped producing drifted ids, so these tests would pass "
        "against the bug they exist to catch"
    )
    return {'ja_id': JA_ID, 'photo_id': photo_id, 'data': data}


def open_gallery(page, live_server, ja_id):
    """Open the Edit Item form and leave the gallery settled at one card."""
    page.goto(f"{live_server.url}/inventory/edit/{ja_id}")
    expect(page.locator(CARDS)).to_have_count(1)


def saved_bytes(download):
    return open(download.path(), 'rb').read()


@pytest.mark.e2e
def test_the_gallery_button_downloads_the_original(page, live_server, item_with_photo):
    """US1: the download button on a card saves the file that was uploaded."""
    open_gallery(page, live_server, item_with_photo['ja_id'])

    # expect_download IS the wait -- the click returns before the file lands.
    with page.expect_download() as info:
        page.locator(DOWNLOAD_ONE).click()
    download = info.value

    assert saved_bytes(download) == item_with_photo['data']
    # The Photo id, not the association id: this is what pins the UI to the
    # identifier the endpoint takes.
    assert download.url.endswith(
        f"/api/photos/{item_with_photo['photo_id']}/download"
    ), download.url


@pytest.mark.e2e
def test_the_viewer_control_downloads_the_original(page, live_server, item_with_photo):
    """US2: the viewer's Download control serves the same file."""
    open_gallery(page, live_server, item_with_photo['ja_id'])

    page.locator(VIEW_ONE).click()
    expect(page.locator(MODAL_DOWNLOAD)).to_be_visible()

    with page.expect_download() as info:
        page.locator(MODAL_DOWNLOAD).click()
    download = info.value

    assert saved_bytes(download) == item_with_photo['data']
    assert download.url.endswith(
        f"/api/photos/{item_with_photo['photo_id']}/download"
    ), download.url
