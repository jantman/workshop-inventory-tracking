"""
Regression tests for the create/edit forms not losing what the operator typed.

Two ways this feature managed to promise something and not deliver it, both
found in review:

- The distributor-label fields were rendered as editable inputs inside the form,
  posted with it, and then read by nothing at all.
- A rejected edit re-rendered the unchanged database row, discarding the typing
  that had just been rejected.

Both are silent: no error, no warning, and the operator only finds out by
noticing later that something they entered is not there.
"""

import pytest

from app.catalog_service import CatalogService


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


class TestDistributorLabelFieldsArePersisted:
    """FR-017 promises they stay editable; editable-then-discarded is worse"""

    def test_the_extracted_fields_survive_a_save(self, client, service):
        response = client.post('/products/new', data={
            'description': 'LM358 dual op-amp',
            'ecia_quantity': '100',
            'ecia_order_reference': '12345678',
            'ecia_supplier_order_reference': 'SO987654',
            'ecia_date_code': '2431',
            'ecia_distributor_part_number': '296-1234-5-ND',
        }, follow_redirects=True)
        assert response.status_code == 200

        product = service.list_products()[0]
        for value in ('100', '12345678', 'SO987654', '2431', '296-1234-5-ND'):
            assert value in product.notes, f"{value} was dropped on save"

    def test_an_operator_amendment_is_what_gets_stored(self, client, service):
        """Not the scanned value -- the one they corrected it to"""
        client.post('/products/new', data={
            'description': 'LM358 dual op-amp',
            'ecia_quantity': '42',
        }, follow_redirects=True)

        assert '42' in service.list_products()[0].notes

    def test_the_operators_own_notes_are_not_clobbered(self, client, service):
        client.post('/products/new', data={
            'description': 'LM358 dual op-amp',
            'notes': 'from the surplus bin',
            'ecia_quantity': '100',
        }, follow_redirects=True)

        notes = service.list_products()[0].notes
        assert 'from the surplus bin' in notes
        assert '100' in notes

    def test_a_product_with_no_label_fields_gets_no_note_block(self, client, service):
        client.post('/products/new', data={
            'description': 'Hand-entered thing',
            'notes': 'just my notes',
        }, follow_redirects=True)

        assert service.list_products()[0].notes == 'just my notes'

    def test_blank_label_fields_are_not_recorded(self, client, service):
        client.post('/products/new', data={
            'description': 'Hand-entered thing',
            'ecia_quantity': '   ',
        }, follow_redirects=True)

        assert service.list_products()[0].notes is None


class TestARejectedEditKeepsTheTyping:
    def test_the_form_comes_back_carrying_what_was_submitted(self, client, service):
        product = service.create_product(description='Original', location='Bin 4')

        # Description is required, so this is rejected -- but the location edit
        # alongside it must not be thrown away.
        response = client.post(f'/products/{product.id}/edit', data={
            'description': '',
            'location': 'Bin 9, moved this morning',
        })

        assert response.status_code == 200
        assert b'Bin 9, moved this morning' in response.data

    def test_the_stored_product_is_unchanged_by_a_rejected_edit(self, client, service):
        product = service.create_product(description='Original', location='Bin 4')

        client.post(f'/products/{product.id}/edit', data={
            'description': '',
            'location': 'Bin 9, moved this morning',
        })

        assert service.get_product(product.id).location == 'Bin 4'

    def test_a_valid_edit_still_saves(self, client, service):
        product = service.create_product(description='Original', location='Bin 4')

        client.post(f'/products/{product.id}/edit', data={
            'description': 'Renamed',
            'location': 'Bin 9',
        }, follow_redirects=True)

        updated = service.get_product(product.id)
        assert updated.description == 'Renamed'
        assert updated.location == 'Bin 9'


class TestTheBookmarkletSurvivesAFailedCapture:
    """An empty href is a bookmark to the current page, saved silently"""

    def test_a_rejected_capture_still_renders_the_bookmarklet(self, client):
        # No URL and no vendor -- capture_order rejects it.
        response = client.post('/products/capture', data={'url': '', 'vendor': ''})

        assert response.status_code == 200
        assert b'href="javascript:' in response.data
        assert b'id="capture-bookmarklet"\n                       href=""' not in response.data

    def test_the_submitted_values_come_back_too(self, client):
        response = client.post('/products/capture', data={
            'url': '', 'vendor': '', 'listing_title': 'Half-typed title',
        })
        assert b'Half-typed title' in response.data
