"""
Unit tests for deleting a purchase (feature 032, issue #130).

A purchase written in error used to be permanent without shell access to the
database host. These cover the removal itself and, more importantly, its
boundaries: what survives it and what it must not touch.

**Most of this file is about things that do not happen.** FR-005 (the product
and its siblings survive), FR-006 (a shared photo survives), FR-007 (the counted
quantity does not move) and FR-012 (a failure rolls the whole thing back) are all
statements the code does not make anywhere -- there is no line saying "the count
stays put", only an absence of the line that would move it. These tests are what
keeps that absence deliberate.

Note on the database: these run against SQLite through the project's fixtures.
The ORM-level `cascade='all, delete-orphan'` on ``Purchase.attachments`` is what
removes the attachment rows here; MariaDB additionally enforces it with
``ON DELETE CASCADE``. Both paths lead to the same place, and the assertions
below are about the outcome rather than about which mechanism produced it.
"""

import io
from datetime import datetime
from decimal import Decimal

import pytest
from PIL import Image

from app.catalog_service import CatalogService
from app.database import ItemPhotoAssociation, Photo, ProductAttachment, Purchase
from app.photo_service import PhotoService


def png_bytes(color=(10, 120, 200)):
    """A real, small PNG -- the photo service actually decodes what it is given.

    The color is a parameter because the service deduplicates on a content hash:
    two uploads of identical bytes would be one photo row, which would silently
    turn a two-photo test into a one-photo test.
    """
    buffer = io.BytesIO()
    Image.new('RGB', (40, 30), color).save(buffer, format='PNG')
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
    return service.create_product(description='ELECROW ESP32 E-Ink 4.2in')


@pytest.fixture
def purchase(service, product):
    """An outstanding purchase -- received_date is None, which *is* that state."""
    return service.record_purchase(
        product.id,
        vendor='Amazon',
        vendor_item_id='B0G43FCHFX',
        order_date=datetime(2026, 7, 23),
        quantity=1,
        unit_price='37.59',
        supplier_order_reference='111-9281973-9357866',
    )


def rows(service, model, **filters):
    """Count rows of a model, going around the service to check what really landed"""
    with service._session() as session:
        query = session.query(model)
        for column, value in filters.items():
            query = query.filter(getattr(model, column) == value)
        return query.count()


class TestTheRowGoes:
    def test_an_outstanding_purchase_is_deleted(self, service, purchase):
        assert service.delete_purchase(purchase.id) is not None

        assert service.get_purchase(purchase.id) is None
        assert rows(service, Purchase, id=purchase.id) == 0

    def test_a_received_purchase_is_deleted(self, service, product):
        """FR-013: no state a mis-captured purchase can be in is undeletable"""
        received = service.record_purchase(
            product.id,
            vendor='DigiKey',
            order_date=datetime(2026, 7, 23),
            received_date=datetime(2026, 7, 27),
            quantity=5,
        )

        service.delete_purchase(received.id)

        assert service.get_purchase(received.id) is None

    def test_an_unknown_purchase_returns_none(self, service):
        """FR-011. None rather than raising, matching get_purchase and
        remove_identifier -- the not-found decision belongs to the route."""
        assert service.delete_purchase(999999) is None

    def test_deleting_twice_reports_the_second_as_missing(self, service, purchase):
        assert service.delete_purchase(purchase.id) is not None
        assert service.delete_purchase(purchase.id) is None


class TestTheSummary:
    def test_it_reports_what_was_removed(self, service, product, purchase):
        """FR-008: the route has to say what went, after the row is gone"""
        deletion = service.delete_purchase(purchase.id)

        assert deletion.purchase_id == purchase.id
        assert deletion.product_id == product.id
        assert deletion.vendor == 'Amazon'
        assert deletion.order_date == datetime(2026, 7, 23)
        assert deletion.quantity == 1
        assert deletion.supplier_order_reference == '111-9281973-9357866'

    def test_the_price_comes_back_as_a_decimal(self, service, purchase):
        """Constitution III: a price never round-trips through binary floating point"""
        deletion = service.delete_purchase(purchase.id)

        assert isinstance(deletion.unit_price, Decimal)
        assert deletion.unit_price == Decimal('37.59')

    def test_a_purchase_with_no_files_reports_zero(self, service, purchase):
        assert service.delete_purchase(purchase.id).attachments_deleted == 0

    def test_the_file_count_is_what_went(self, service, photos, purchase):
        photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'listing.png', 'image/png'
        )
        photos.upload_purchase_attachment(
            purchase.id, png_bytes((200, 30, 10)), 'receipt.png', 'image/png'
        )

        assert service.delete_purchase(purchase.id).attachments_deleted == 2

    def test_no_supplier_order_reference_is_reported_as_none(self, service, product):
        """There is no order to go back to, and that has to be visible to the route"""
        hand_recorded = service.record_purchase(product.id, vendor='eBay')

        assert service.delete_purchase(hand_recorded.id).supplier_order_reference is None


class TestWhatSurvives:
    def test_the_product_survives_its_last_purchase(self, service, product, purchase):
        """FR-005. Deleting a purchase is not a way to delete a product."""
        service.delete_purchase(purchase.id)

        survivor = service.get_product(product.id)
        assert survivor is not None
        assert survivor.description == 'ELECROW ESP32 E-Ink 4.2in'

    def test_the_products_other_purchases_survive(self, service, product, purchase):
        """The whole point: one of two duplicate rows goes, the other stays (#129)"""
        keeper = service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 7, 27), quantity=1
        )

        service.delete_purchase(purchase.id)

        assert [p.id for p in service.get_purchase_history(product.id)] == [keeper.id]

    def test_a_product_level_attachment_survives(self, service, photos, product, purchase):
        """FR-005: a datasheet belongs to the product, not to any purchase"""
        datasheet = photos.upload_product_attachment(
            product.id, png_bytes(), 'datasheet.png', 'image/png'
        )

        service.delete_purchase(purchase.id)

        assert rows(service, ProductAttachment, id=datasheet.id) == 1
        assert rows(service, Photo, id=datasheet.photo_id) == 1

    def test_a_photo_another_attachment_still_wants_survives(
        self, service, photos, product, purchase
    ):
        """FR-006. The purchase's claim on the bytes goes; the bytes do not.

        The second reference is built directly rather than by uploading the same
        file twice, because ``upload_*_attachment`` deduplicates *per owner* --
        two uploads of identical bytes to different owners produce two Photo rows
        and would not exercise this branch at all.
        """
        on_purchase = photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'listing.png', 'image/png'
        )
        with service._session() as session:
            session.add(ProductAttachment(
                photo_id=on_purchase.photo_id, product_id=product.id
            ))

        service.delete_purchase(purchase.id)

        assert rows(service, ProductAttachment, id=on_purchase.id) == 0
        assert rows(service, ProductAttachment, photo_id=on_purchase.photo_id) == 1
        assert rows(service, Photo, id=on_purchase.photo_id) == 1

    def test_a_photo_an_inventory_item_still_wants_survives(
        self, service, photos, purchase
    ):
        """The other branch of the same predicate: an item photo, not an
        attachment. Both tables have to be checked or the sweep takes bytes an
        inventory item is still showing."""
        on_purchase = photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'listing.png', 'image/png'
        )
        with service._session() as session:
            session.add(ItemPhotoAssociation(
                ja_id='JA000123', photo_id=on_purchase.photo_id, display_order=0
            ))

        service.delete_purchase(purchase.id)

        assert rows(service, ProductAttachment, id=on_purchase.id) == 0
        assert rows(service, Photo, id=on_purchase.photo_id) == 1

    def test_an_unshared_photo_goes(self, service, photos, purchase):
        """The other half of FR-006: nothing else wants it, so it goes"""
        attachment = photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'listing.png', 'image/png'
        )

        service.delete_purchase(purchase.id)

        assert rows(service, ProductAttachment, id=attachment.id) == 0
        assert rows(service, Photo, id=attachment.photo_id) == 0


class TestWhatDoesNotMove:
    """FR-007. Receiving history and current stock are separate claims.

    Nothing on a purchase records whether its receipt ever moved a count -- one
    received through the receive screen did, one captured with an arrival date
    did not -- so deleting one must not guess. The operator adjusts the count
    with the controls already on the product page.
    """

    @pytest.fixture
    def counted(self, service):
        return service.create_product(description='M3x10 socket head cap screw')

    def test_a_tracked_count_does_not_move(self, service, counted):
        service.set_quantity(counted.id, 40)
        received = service.record_purchase(
            counted.id, vendor='McMaster-Carr',
            received_date=datetime(2026, 7, 27), quantity=25,
        )

        service.delete_purchase(received.id)

        assert service.get_product(counted.id).quantity == 40

    def test_the_counts_age_does_not_move(self, service, counted):
        """quantity_updated_at means the last time somebody counted, and
        deleting a receipt is not counting."""
        service.set_quantity(counted.id, 40)
        counted_at = service.get_product(counted.id).quantity_updated_at
        received = service.record_purchase(
            counted.id, vendor='McMaster-Carr',
            received_date=datetime(2026, 7, 27), quantity=25,
        )

        service.delete_purchase(received.id)

        assert service.get_product(counted.id).quantity_updated_at == counted_at

    def test_a_hand_set_stock_flag_does_not_clear(self, service, counted):
        """Receiving clears a manual flag (FR-029). Deleting the receipt does
        not set it back, and must not clear one either."""
        flagged = service.set_stock_status(counted.id, 'LOW')
        flagged_at = flagged.stock_status_updated_at
        received = service.record_purchase(
            counted.id, vendor='McMaster-Carr',
            received_date=datetime(2026, 7, 27), quantity=25,
        )

        service.delete_purchase(received.id)

        survivor = service.get_product(counted.id)
        assert survivor.stock_status == flagged.stock_status
        assert survivor.stock_status is not None
        assert survivor.stock_status_updated_at == flagged_at

    def test_no_inventory_item_is_touched(self, service, test_storage, purchase):
        """Constitution VI is not engaged by this feature, and this is what keeps
        that a checked claim rather than an assertion. Purchases are catalog
        rows: no JA ID, no active-row invariant, no parent-child link."""
        from app.database import InventoryItem

        with service._session() as session:
            before = session.query(InventoryItem).count()

        service.delete_purchase(purchase.id)

        with service._session() as session:
            assert session.query(InventoryItem).count() == before


class TestAtomicity:
    """FR-012: all of it, or none of it.

    The purchase and its attachment rows are already flushed by the time the
    photo cleanup runs, so a failure there is exactly the "part way through" case
    -- and it is the one that matters, because it is the only step that can fail
    for a reason other than the database being gone.
    """

    def test_a_failure_during_photo_cleanup_rolls_the_whole_thing_back(
        self, service, photos, purchase, monkeypatch
    ):
        attachment = photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'listing.png', 'image/png'
        )

        # Break the second half of the reference check. The photo is unshared, so
        # the ProductAttachment count is zero and this branch is always reached.
        class NotAnEntity:
            pass

        monkeypatch.setattr('app.catalog_service.ItemPhotoAssociation', NotAnEntity)

        with pytest.raises(Exception):
            service.delete_purchase(purchase.id)

        assert service.get_purchase(purchase.id) is not None
        assert rows(service, Purchase, id=purchase.id) == 1
        assert rows(service, ProductAttachment, id=attachment.id) == 1
        assert rows(service, Photo, id=attachment.photo_id) == 1


class TestTheDerivedViews:
    """FR-009 at the service level. Every purchase-derived read loses the row,
    because they are all worked out from the purchases rather than stored."""

    def test_it_leaves_the_purchase_history(self, service, product, purchase):
        service.delete_purchase(purchase.id)

        assert service.get_purchase_history(product.id) == []

    def test_it_leaves_its_order(self, service, product, purchase):
        """An order *is* the purchases carrying its number, so there is nothing
        to fix up -- and deleting the last one leaves no order at all."""
        assert len(service.find_order_lines_for('Amazon', '111-9281973-9357866')) == 1

        service.delete_purchase(purchase.id)

        assert service.find_order_lines_for('Amazon', '111-9281973-9357866') == []

    def test_the_order_keeps_the_lines_it_still_has(self, service, product, purchase):
        keeper = service.record_purchase(
            product.id,
            vendor='Amazon',
            order_date=datetime(2026, 7, 23),
            supplier_order_reference='111-9281973-9357866',
        )

        service.delete_purchase(purchase.id)

        remaining = service.find_order_lines_for('Amazon', '111-9281973-9357866')
        assert [p.id for p in remaining] == [keeper.id]

    def test_it_leaves_the_captured_orders_list(self, service, purchase):
        service.delete_purchase(purchase.id)

        assert '111-9281973-9357866' not in [
            order.order_number for order in service.find_captured_orders()
        ]


class TestTheConfirmationPage:
    """FR-002, FR-003, FR-004. Nothing is removed until the operator has seen
    what they are about to lose and the two consequences the row does not show."""

    def test_it_renders(self, client, purchase):
        response = client.get(f'/purchases/{purchase.id}/delete')

        assert response.status_code == 200

    def test_it_names_the_purchase(self, client, purchase):
        """Two near-identical rows is the case this exists for (#129), so the
        page has to say which one is going."""
        body = client.get(f'/purchases/{purchase.id}/delete').data.decode()

        assert 'Amazon' in body
        assert '2026-07-23' in body
        assert '37.59' in body
        assert '111-9281973-9357866' in body

    def test_it_says_the_count_will_not_change(self, client, purchase):
        """FR-004: the operator cannot see this from the row"""
        body = client.get(f'/purchases/{purchase.id}/delete').data.decode().lower()

        assert 'counted quantity' in body
        assert 'not change' in body

    def test_it_says_how_many_files_go(self, client, photos, purchase):
        photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'listing.png', 'image/png'
        )
        photos.upload_purchase_attachment(
            purchase.id, png_bytes((200, 30, 10)), 'receipt.png', 'image/png'
        )

        body = client.get(f'/purchases/{purchase.id}/delete').data.decode()

        assert '2 attached file' in body

    def test_it_says_so_when_there_are_no_files(self, client, purchase):
        """Stated rather than omitted -- silence is something to infer from"""
        body = client.get(f'/purchases/{purchase.id}/delete').data.decode().lower()

        assert 'no attached files' in body

    def test_a_get_changes_nothing(self, client, service, purchase):
        client.get(f'/purchases/{purchase.id}/delete')

        assert service.get_purchase(purchase.id) is not None

    def test_an_unknown_purchase_is_reported_not_rendered(self, client):
        """Through the existing centralized handler, which for a browser request
        flashes a warning and redirects rather than returning a bare 404. That is
        the app-wide convention (``purchase_receive`` behaves the same way); this
        feature adds no error machinery of its own."""
        response = client.get('/purchases/999999/delete', follow_redirects=True)

        assert response.status_code == 200
        assert b'not found' in response.data


class TestTheDeletion:
    def test_it_deletes_and_returns_to_the_product(self, client, service, product, purchase):
        response = client.post(f'/purchases/{purchase.id}/delete')

        assert response.status_code == 302
        assert response.headers['Location'].endswith(f'/products/{product.id}')
        assert service.get_purchase(purchase.id) is None

    def test_it_says_what_went(self, client, purchase):
        """FR-008"""
        response = client.post(f'/purchases/{purchase.id}/delete', follow_redirects=True)

        body = response.data.decode()
        assert 'Deleted' in body
        assert 'Amazon' in body

    def test_the_row_is_gone_from_the_history(self, client, service, product, purchase):
        keeper = service.record_purchase(product.id, vendor='eBay')

        client.post(f'/purchases/{purchase.id}/delete')

        assert [p.id for p in service.get_purchase_history(product.id)] == [keeper.id]

    def test_deleting_it_twice_reports_it_and_changes_nothing(
        self, client, service, product, purchase
    ):
        """FR-011: the same product open in two tabs. The second attempt says so
        rather than reporting a success that did nothing."""
        keeper = service.record_purchase(product.id, vendor='eBay')
        client.post(f'/purchases/{purchase.id}/delete')

        response = client.post(f'/purchases/{purchase.id}/delete', follow_redirects=True)

        assert b'not found' in response.data
        assert [p.id for p in service.get_purchase_history(product.id)] == [keeper.id]

    def test_an_unknown_purchase_is_reported_not_deleted(self, client):
        response = client.post('/purchases/999999/delete', follow_redirects=True)

        assert response.status_code == 200
        assert b'not found' in response.data


class TestWhereItGoesAfterwards:
    """FR-015, research R3. Two accepted values and nothing else; the order
    address is built from the deleted purchase's own vendor and order number, so
    no caller-supplied address is ever followed."""

    def test_return_to_order_goes_back_to_the_order(self, client, purchase):
        response = client.post(
            f'/purchases/{purchase.id}/delete', data={'return_to': 'order'}
        )

        assert response.status_code == 302
        assert '/products/orders/Amazon/111-9281973-9357866' in response.headers['Location']

    def test_the_default_is_the_product(self, client, product, purchase):
        response = client.post(f'/purchases/{purchase.id}/delete')

        assert response.headers['Location'].endswith(f'/products/{product.id}')

    def test_an_unrecognized_value_is_treated_as_the_product(
        self, client, product, purchase
    ):
        response = client.post(
            f'/purchases/{purchase.id}/delete', data={'return_to': 'somewhere-else'}
        )

        assert response.headers['Location'].endswith(f'/products/{product.id}')

    def test_a_url_in_return_to_is_not_followed(self, client, product, purchase):
        """The field is a flag, not an address. Nothing to validate, because
        nothing is accepted."""
        response = client.post(
            f'/purchases/{purchase.id}/delete',
            data={'return_to': 'https://example.com/'},
        )

        assert response.headers['Location'].endswith(f'/products/{product.id}')

    def test_no_order_to_return_to_falls_back_to_the_product(self, client, service, product):
        """A hand-recorded or listing-captured purchase carries no supplier order
        reference. There is no order to go back to, and that is a fallback rather
        than an error."""
        hand_recorded = service.record_purchase(product.id, vendor='eBay')

        response = client.post(
            f'/purchases/{hand_recorded.id}/delete', data={'return_to': 'order'}
        )

        assert response.status_code == 302
        assert response.headers['Location'].endswith(f'/products/{product.id}')

    def test_the_confirmation_carries_the_flag_forward(self, client, purchase):
        body = client.get(f'/purchases/{purchase.id}/delete?return_to=order').data.decode()

        assert 'name="return_to" value="order"' in body

    def test_cancelling_from_the_order_returns_to_the_order(self, client, purchase):
        """FR-002: cancel goes back where they came from"""
        body = client.get(f'/purchases/{purchase.id}/delete?return_to=order').data.decode()

        assert '/products/orders/Amazon/111-9281973-9357866' in body

    def test_cancelling_from_the_product_returns_to_the_product(
        self, client, product, purchase
    ):
        body = client.get(f'/purchases/{purchase.id}/delete').data.decode()

        assert f'/products/{product.id}' in body


class TestWhatTheFlashSays:
    """FR-008, and the deliberate asymmetry with the confirmation page.

    The confirmation states the file count even when it is zero, because it is a
    decision aid -- "will this take my saved listing?" needs an answer, and an
    absence inferred from silence is not one. The flash is a receipt for a
    decision already made and already shown, so it names files only when files
    went. Pinned in both directions, because it is a choice rather than an
    oversight.
    """

    def test_it_names_the_purchase(self, client, purchase):
        response = client.post(f'/purchases/{purchase.id}/delete', follow_redirects=True)

        body = response.data.decode()
        assert 'Deleted the Amazon purchase' in body
        assert 'ordered 2026-07-23' in body
        assert 'of 1' in body

    def test_it_counts_the_files_that_went(self, client, photos, purchase):
        photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'listing.png', 'image/png'
        )
        photos.upload_purchase_attachment(
            purchase.id, png_bytes((200, 30, 10)), 'receipt.png', 'image/png'
        )

        response = client.post(f'/purchases/{purchase.id}/delete', follow_redirects=True)

        assert '2 attached files went with it' in response.data.decode()

    def test_one_file_is_singular(self, client, photos, purchase):
        photos.upload_purchase_attachment(
            purchase.id, png_bytes(), 'listing.png', 'image/png'
        )

        response = client.post(f'/purchases/{purchase.id}/delete', follow_redirects=True)

        assert '1 attached file went with it' in response.data.decode()

    def test_it_says_nothing_about_files_when_none_went(self, client, purchase):
        """A receipt reporting zero of something is noise. The operator has just
        read "no attached files" on the confirmation they came from."""
        response = client.post(f'/purchases/{purchase.id}/delete', follow_redirects=True)

        assert 'attached file' not in response.data.decode()
