"""
Unit tests for product and purchase attachments.

Both owner paths round-trip, and the exactly-one-owner rule holds.

Note on where the constraint is real: SQLite, which these tests run against
through the project's fixtures, does enforce CHECK constraints -- but FK cascades
and enforcement details differ from MariaDB, so the assertions here are about the
service refusing to create a bad row, and the database-level rejection is
asserted separately below and again by the migration round-trip against MariaDB.
"""

import io

import pytest
from PIL import Image

from app.catalog_service import CatalogService
from app.database import ProductAttachment
from app.photo_service import PhotoService


def png_bytes(size=(40, 30)):
    """A real, small PNG -- the service actually decodes what it is given"""
    buffer = io.BytesIO()
    Image.new('RGB', size, (10, 120, 200)).save(buffer, format='PNG')
    return buffer.getvalue()


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def photos(test_storage):
    photo_service = PhotoService(test_storage)
    yield photo_service
    photo_service.close()


@pytest.fixture
def product(service):
    return service.create_product(description='LM358 op-amp')


@pytest.fixture
def purchase(service, product):
    return service.record_purchase(product.id, vendor='DigiKey')


class TestProductAttachments:
    def test_a_datasheet_attaches_to_a_product(self, photos, product):
        attachment = photos.upload_product_attachment(
            product.id, png_bytes(), 'datasheet.png', 'image/png'
        )

        assert attachment.id is not None
        assert attachment.product_id == product.id
        assert attachment.purchase_id is None

    def test_it_reads_back(self, photos, product):
        photos.upload_product_attachment(
            product.id, png_bytes(), 'datasheet.png', 'image/png'
        )
        found = photos.get_product_attachments(product.id)

        assert len(found) == 1
        assert found[0].photo.filename == 'datasheet.png'

    def test_the_bytes_are_stored_in_the_existing_photos_table(self, photos, product):
        attachment = photos.upload_product_attachment(
            product.id, png_bytes(), 'datasheet.png', 'image/png'
        )
        data, content_type = photos.get_photo_data(attachment.photo_id, 'original')

        assert content_type == 'image/png'
        assert len(data) > 0

    def test_display_order_increments(self, photos, product):
        first = photos.upload_product_attachment(
            product.id, png_bytes(), 'one.png', 'image/png'
        )
        second = photos.upload_product_attachment(
            product.id, png_bytes(), 'two.png', 'image/png'
        )
        assert second.display_order > first.display_order

    def test_attaching_to_a_missing_product_is_refused(self, photos):
        with pytest.raises(ValueError):
            photos.upload_product_attachment(99999, png_bytes(), 'x.png', 'image/png')

    def test_a_product_with_nothing_attached_reads_back_empty(self, photos, product):
        assert photos.get_product_attachments(product.id) == []


class TestPurchaseAttachments:
    def test_a_saved_listing_attaches_to_a_purchase(self, photos, purchase):
        attachment = photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'listing.png', 'image/png'
        )

        assert attachment.purchase_id == purchase.id
        assert attachment.product_id is None

    def test_it_reads_back(self, photos, purchase):
        photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'listing.png', 'image/png'
        )
        found = photos.get_purchase_attachments(purchase.id)

        assert len(found) == 1
        assert found[0].photo.filename == 'listing.png'

    def test_attaching_to_a_missing_purchase_is_refused(self, photos):
        with pytest.raises(ValueError):
            photos.upload_purchase_attachment(99999, png_bytes(), 'x.png', 'image/png')

    def test_a_purchase_attachment_is_not_a_product_attachment(self, photos, product, purchase):
        """The two owners are genuinely separate lists"""
        photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'listing.png', 'image/png'
        )
        assert photos.get_product_attachments(product.id) == []
        assert len(photos.get_purchase_attachments(purchase.id)) == 1


class TestExactlyOneOwner:
    """An attachment belongs to a product or a purchase, never both, never neither"""

    def test_the_service_never_offers_a_way_to_say_both(self, photos, product, purchase):
        product_attachment = photos.upload_product_attachment(
            product.id, png_bytes(), 'a.png', 'image/png'
        )
        purchase_attachment = photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'b.png', 'image/png'
        )

        for attachment in (product_attachment, purchase_attachment):
            owners = [attachment.product_id, attachment.purchase_id]
            assert sum(1 for owner in owners if owner is not None) == 1

    def test_the_database_rejects_a_two_owner_row(self, photos, product, purchase):
        """The constraint, exercised where it is enforced"""
        seed = photos.upload_product_attachment(
            product.id, png_bytes(), 'a.png', 'image/png'
        )

        photos.session.add(ProductAttachment(
            photo_id=seed.photo_id, product_id=product.id, purchase_id=purchase.id
        ))
        with pytest.raises(Exception):
            photos.session.commit()
        photos.session.rollback()

    def test_the_database_rejects_a_no_owner_row(self, photos, product):
        seed = photos.upload_product_attachment(
            product.id, png_bytes(), 'a.png', 'image/png'
        )

        photos.session.add(ProductAttachment(photo_id=seed.photo_id))
        with pytest.raises(Exception):
            photos.session.commit()
        photos.session.rollback()


class TestValidation:
    def test_an_unsupported_content_type_is_refused(self, photos, product):
        with pytest.raises(ValueError):
            photos.upload_product_attachment(
                product.id, b'MZ\x90\x00', 'thing.exe', 'application/x-msdownload'
            )

    def test_an_empty_file_is_refused(self, photos, product):
        with pytest.raises(ValueError):
            photos.upload_product_attachment(product.id, b'', 'empty.png', 'image/png')

    def test_a_missing_filename_is_refused(self, photos, product):
        with pytest.raises(ValueError):
            photos.upload_product_attachment(product.id, png_bytes(), '', 'image/png')

    def test_the_product_cap_is_its_own_constant(self):
        """Not a reuse of MAX_PHOTOS_PER_ITEM -- the two limits should move apart"""
        assert PhotoService.MAX_ATTACHMENTS_PER_PRODUCT != PhotoService.MAX_PHOTOS_PER_ITEM


class TestDeletion:
    def test_deleting_an_attachment_removes_it(self, photos, product):
        attachment = photos.upload_product_attachment(
            product.id, png_bytes(), 'a.png', 'image/png'
        )

        assert photos.delete_attachment(attachment.id) is True
        assert photos.get_product_attachments(product.id) == []

    def test_deleting_something_that_is_not_there_is_false_not_an_error(self, photos):
        assert photos.delete_attachment(99999) is False

    def test_the_bytes_go_when_nothing_else_references_them(self, photos, product):
        attachment = photos.upload_product_attachment(
            product.id, png_bytes(), 'a.png', 'image/png'
        )
        photo_id = attachment.photo_id
        photos.delete_attachment(attachment.id)

        assert photos.get_photo_data(photo_id, 'original') is None


class TestTheOrphanSweepLeavesAttachmentsAlone:
    """cleanup_orphaned_photos predates attachments and knew only about items.

    Its definition of "orphaned" was "no ItemPhotoAssociation", which every
    attachment satisfies from the moment it is uploaded -- and since
    product_attachments.photo_id cascades, running the sweep took the attachment
    rows with the bytes. That is silent data loss on an endpoint an operator can
    hit from the admin UI.
    """

    def test_a_product_attachment_survives_the_sweep(self, photos, product):
        attachment = photos.upload_product_attachment(
            product.id, png_bytes(), 'datasheet.png', 'image/png'
        )

        photos.cleanup_orphaned_photos()

        assert len(photos.get_product_attachments(product.id)) == 1
        assert photos.get_photo_data(attachment.photo_id, 'original') is not None

    def test_a_purchase_attachment_survives_the_sweep(self, photos, purchase):
        attachment = photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'listing.png', 'image/png'
        )

        photos.cleanup_orphaned_photos()

        assert len(photos.get_purchase_attachments(purchase.id)) == 1
        assert photos.get_photo_data(attachment.photo_id, 'original') is not None

    def test_a_genuinely_unreferenced_photo_is_still_swept(self, photos, product):
        """The sweep must still do its job"""
        from app.database import Photo

        orphan = Photo(
            filename='nobody.png', content_type='image/png', file_size=4,
            thumbnail_data=b'a', medium_data=b'b', original_data=b'c',
        )
        photos.session.add(orphan)
        photos.session.commit()
        orphan_id = orphan.id

        photos.cleanup_orphaned_photos()

        assert photos.get_photo_data(orphan_id, 'original') is None
