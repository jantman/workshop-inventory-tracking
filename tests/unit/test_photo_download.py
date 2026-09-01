"""Unit tests for GET /api/photos/<id>/download (issue #131).

The endpoint had never returned a file. It resolved one id against two
different tables -- ``get_photo()`` takes an ``ItemPhotoAssociation`` id,
``get_photo_data()`` takes a ``Photo`` id -- and then read ``filename`` off the
association, which has no such attribute. So every id produced either a 404 or
a 500, and nothing in the existing tests noticed.

**Why the product attachment in the fixture is load-bearing.** A photo has two
ids and they are equal only while every ``Photo`` has exactly one association
and nothing else has created a ``Photo`` row. That describes a fresh test
database and nothing else: product and purchase attachments create ``Photo``
rows with no association at all and push the sequences apart, which is the
ordinary state of any database this application has been used on. Seeding one
first is what makes these tests able to fail against the bug -- without it they
pass against a handler that confuses the two ids. The fixture asserts the drift
it created rather than assuming it.

The same reasoning, and the same technique, is in
``tests/e2e/test_photo_bulk_delete.py``.
"""

import io

import pytest
from PIL import Image

from app.catalog_service import CatalogService
from app.database import InventoryItem
from app.photo_service import PhotoService

# The one place the server-sent filename can be asserted. The e2e tests cannot
# see it: photo-manager.js sets `link.download` before clicking, and a
# same-origin anchor's download attribute overrides Content-Disposition, so the
# browser's saved name is the page's choice and would be right even against a
# server that sent none.
PHOTO_FILENAME = 'hex-bar.jpg'
JA_ID = 'JA000900'

PDF_BYTES = b"""%PDF-1.4
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
>>
endobj
xref
0 4
0000000000 65535 f 
0000000010 00000 n 
0000000079 00000 n 
0000000173 00000 n 
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
301
%%EOF"""


def jpeg_bytes(colour='red', size=(120, 90)):
    """A real JPEG -- the service decodes and resizes what it is given."""
    buffer = io.BytesIO()
    Image.new('RGB', size, color=colour).save(buffer, format='JPEG', quality=90)
    return buffer.getvalue()


def png_bytes(size=(40, 30)):
    buffer = io.BytesIO()
    Image.new('RGB', size, (10, 120, 200)).save(buffer, format='PNG')
    return buffer.getvalue()


def add_item(test_storage, ja_id=JA_ID):
    """Insert an inventory item and commit it.

    ``PhotoService._item_exists`` opens its own session, so an uncommitted item
    is invisible to it and the upload is refused.
    """
    session = test_storage._get_session()
    try:
        session.add(InventoryItem(
            ja_id=ja_id,
            active=True,
            item_type='Bar',
            shape='Round',
            material='Steel',
            location='Bin A',
        ))
        session.commit()
    finally:
        session.close()


def seed_drifted_photo(test_storage, data, filename, content_type, ja_id=JA_ID):
    """Attach a file to an item on a database whose id sequences have drifted.

    Returns ``(photo_id, association_id)``, having asserted they differ.
    """
    product = CatalogService(test_storage).create_product(
        description='id-sequence spacer'
    )

    with PhotoService(test_storage) as photos:
        photos.upload_product_attachment(
            product.id, png_bytes(), 'spacer.png', 'image/png'
        )

    add_item(test_storage, ja_id)

    with PhotoService(test_storage) as photos:
        association = photos.upload_photo(ja_id, data, filename, content_type)
        photo_id = association.photo_id
        association_id = association.id

    assert photo_id != association_id, (
        "the fixture stopped producing drifted ids, so these tests would pass "
        "against the bug they exist to catch"
    )
    return photo_id, association_id


@pytest.fixture
def drifted_photo(test_storage):
    """One JPEG on an item, on a database where photo id != association id."""
    data = jpeg_bytes()
    photo_id, association_id = seed_drifted_photo(
        test_storage, data, PHOTO_FILENAME, 'image/jpeg'
    )
    return {
        'photo_id': photo_id,
        'association_id': association_id,
        'data': data,
        'filename': PHOTO_FILENAME,
    }


@pytest.mark.unit
class TestPhotoDownload:
    """FR-001, FR-002, FR-003: the original file, under its original name."""

    def test_downloads_the_original_bytes(self, client, drifted_photo):
        response = client.get(f"/api/photos/{drifted_photo['photo_id']}/download")

        assert response.status_code == 200
        assert response.data == drifted_photo['data']

    def test_reports_the_original_content_type(self, client, drifted_photo):
        response = client.get(f"/api/photos/{drifted_photo['photo_id']}/download")

        assert response.status_code == 200
        assert response.headers['Content-Type'] == 'image/jpeg'

    def test_sends_it_as_an_attachment_under_its_original_name(
        self, client, drifted_photo
    ):
        response = client.get(f"/api/photos/{drifted_photo['photo_id']}/download")

        disposition = response.headers['Content-Disposition']
        assert disposition.startswith('attachment')
        assert drifted_photo['filename'] in disposition

    def test_a_filename_that_needs_quoting_survives(self, client, test_storage):
        """Spec edge case: spaces and parentheses in an uploaded name."""
        awkward = 'bar stock (2).jpg'
        data = jpeg_bytes('green')
        photo_id, _ = seed_drifted_photo(test_storage, data, awkward, 'image/jpeg')

        response = client.get(f"/api/photos/{photo_id}/download")

        assert response.status_code == 200
        assert awkward in response.headers['Content-Disposition']

    def test_a_pdf_downloads_as_the_pdf_not_its_preview(self, client, test_storage):
        """FR-003. The thumbnail path substitutes image/jpeg for PDFs
        (``photo_service.get_photo_data``); download must not.
        """
        photo_id, _ = seed_drifted_photo(
            test_storage, PDF_BYTES, 'datasheet.pdf', 'application/pdf'
        )

        response = client.get(f"/api/photos/{photo_id}/download")

        assert response.status_code == 200
        assert response.data == PDF_BYTES
        assert response.headers['Content-Type'] == 'application/pdf'
        assert 'datasheet.pdf' in response.headers['Content-Disposition']


@pytest.mark.unit
class TestPhotoDownloadNotFound:
    """FR-005: a missing file is a not-found answer, and a present one never fails."""

    def test_an_unknown_id_is_not_found(self, client, drifted_photo):
        response = client.get('/api/photos/999999/download')

        assert response.status_code == 404
        assert response.get_json() == {
            'success': False,
            'error': 'Photo not found',
        }

    def test_the_association_id_does_not_produce_a_server_error(
        self, client, drifted_photo
    ):
        """The id that used to 500.

        On a drifted database the association id is some other photo, or
        nothing. Either is a fine answer; ``'ItemPhotoAssociation' object has
        no attribute 'filename'`` is not.
        """
        response = client.get(
            f"/api/photos/{drifted_photo['association_id']}/download"
        )

        assert response.status_code in (200, 404), response.get_data(as_text=True)

    def test_not_found_is_reached_without_raising(self, client, drifted_photo):
        """The 404 comes from the None return, not from the except block.

        A handler that fails and reports 500 is a different bug from one that
        answers 404, and the two are only distinguishable by the body.
        """
        response = client.get('/api/photos/999999/download')

        assert 'Failed to download photo' not in response.get_data(as_text=True)
