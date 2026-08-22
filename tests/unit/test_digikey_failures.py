"""
Unit tests for what the operator is told when DigiKey does not work
(feature 024, US4).

FR-038 asks that five states be distinguishable, and the reason is practical
rather than tidy: the operator's next action differs completely in each. "Not
configured" means edit .env; "refused" means look at the developer portal; "not
found" means retype or wait a minute; "throttled" means come back later;
"unreachable" means try again now. Collapsing them into "DigiKey didn't work"
turns a five-second fix into an afternoon.

The one worth singling out is the account id. DigiKey answers ``400 Account ID
must not be 0`` when nothing named the account, which reads like a refusal and
is not one -- it is configuration. Telling the operator to renew an
authorization would send them somewhere with nothing to fix.
"""

import pytest

from app.catalog_service import CatalogService
from app.database import Product, Purchase
from app.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ItemNotFoundError,
    RateLimitError,
    TemporaryError,
)

pytestmark = pytest.mark.unit


class BrokenDigiKey:
    """Fails every call with one chosen exception."""

    def __init__(self, error):
        self.error = error

    def get_order(self, number):
        raise self.error

    def get_part(self, number):
        raise self.error


FAILURES = [
    (ConfigurationError('DIGIKEY_ACCOUNT_ID is not set', config_key='DIGIKEY_ACCOUNT_ID'),
     b'digikey-not-configured'),
    (AuthenticationError('DigiKey refused the credentials'), b'digikey-unauthorized'),
    (ItemNotFoundError('no such order', item_id='1'), b'digikey-not-found'),
    (RateLimitError('slow down', service='DigiKey'), b'digikey-throttled'),
    (TemporaryError('could not connect'), b'digikey-unavailable'),
]


def counts(test_storage):
    session = test_storage._get_session()
    try:
        return (session.query(Product).count(), session.query(Purchase).count())
    finally:
        session.close()


class TestOrderRouteFailures:

    @pytest.mark.parametrize('error,marker', FAILURES)
    def test_each_state_has_its_own_message(self, app, client, error, marker):
        """FR-038. Five states, five things to do about them."""
        app.config['DIGIKEY_CLIENT'] = BrokenDigiKey(error)
        response = client.post('/products/digikey/orders',
                               data={'sales_order_number': '100882558'})
        assert response.status_code == 200, 'a failure is a message, not an error page'
        assert marker in response.data

    @pytest.mark.parametrize('error,marker', FAILURES)
    def test_nothing_is_recorded_when_a_capture_fails(
            self, app, client, test_storage, error, marker):
        """FR-039."""
        app.config['DIGIKEY_CLIENT'] = BrokenDigiKey(error)
        before = counts(test_storage)
        response = client.post('/products/digikey/orders/capture',
                               data={'sales_order_number': '100882558'})
        assert response.status_code == 200
        assert marker in response.data
        assert counts(test_storage) == before

    def test_a_missing_account_id_is_configuration_not_authorization(self, app, client):
        """T053. The one that would send the operator to the wrong place."""
        app.config['DIGIKEY_CLIENT'] = BrokenDigiKey(
            ConfigurationError('DigiKey does not know which account to read',
                               config_key='DIGIKEY_ACCOUNT_ID')
        )
        response = client.post('/products/digikey/orders',
                               data={'sales_order_number': '100882558'})
        assert b'digikey-not-configured' in response.data
        assert b'digikey-unauthorized' not in response.data
        assert b'DIGIKEY_ACCOUNT_ID' in response.data

    def test_a_blank_order_number_asks_rather_than_calling_digikey(self, app, client):
        app.config['DIGIKEY_CLIENT'] = BrokenDigiKey(TemporaryError('should not be called'))
        response = client.post('/products/digikey/orders', data={'sales_order_number': ''})
        assert b'digikey-blank' in response.data

    def test_a_retry_after_the_cause_is_fixed_succeeds(self, app, client, test_storage,
                                                       digikey_fixture_client):
        """FR-039: safe to retry, with no cleanup needed."""
        app.config['DIGIKEY_CLIENT'] = BrokenDigiKey(TemporaryError('down'))
        client.post('/products/digikey/orders/capture',
                    data={'sales_order_number': '100882558'})
        assert counts(test_storage) == (0, 0)

        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client
        response = client.post('/products/digikey/orders/capture', data={
            'sales_order_number': '100882558',
            'include[1866-3027-ND]': 'on',
            'include[1866-3032-ND]': 'on',
        }, follow_redirects=True)
        assert response.status_code == 200
        assert counts(test_storage) == (2, 2)


class TestPartRouteFailures:

    @pytest.mark.parametrize('error,marker', FAILURES)
    def test_each_state_has_its_own_message(self, app, client, error, marker):
        app.config['DIGIKEY_CLIENT'] = BrokenDigiKey(error)
        response = client.post('/products/digikey/part',
                               data={'part_number': '1866-3027-ND'})
        assert response.status_code == 200
        assert marker in response.data

    def test_an_unknown_part_offers_the_by_hand_form(self, app, client):
        """FR-032."""
        app.config['DIGIKEY_CLIENT'] = BrokenDigiKey(
            ItemNotFoundError('no such part', item_id='NOPE')
        )
        response = client.post('/products/digikey/part', data={'part_number': 'NOPE'})
        assert b'digikey-part-by-hand' in response.data
        assert b'NOPE' in response.data

    def test_the_by_hand_link_actually_carries_the_part_number(self, app, client):
        """FR-032, by following the link rather than believing it.

        PR #116 review: this link was built with ``identifier_value`` /
        ``identifier_type`` -- the names of the *form fields* -- while
        ``product_new``'s GET branch reads ``identifier`` / ``id_type``. The
        parameters were silently ignored and the form opened blank, which the
        assertion above could not see because it only checked the link was
        there.
        """
        import re

        app.config['DIGIKEY_CLIENT'] = BrokenDigiKey(
            ItemNotFoundError('no such part', item_id='NOT-A-PART')
        )
        page = client.post('/products/digikey/part',
                           data={'part_number': 'NOT-A-PART'}).get_data(as_text=True)

        block = page[page.index('digikey-part-by-hand'):]
        href = re.search(r'href="([^"]+)"', block).group(1).replace('&amp;', '&')

        followed = client.get(href).get_data(as_text=True)
        value = re.search(r'id="identifier_value"[^>]*value="([^"]*)"', followed)
        assert value is not None, 'the create form has no identifier field'
        assert value.group(1) == 'NOT-A-PART', (
            f'the link dropped the part number: {href}'
        )


class TestNotConfigured:
    """FR-036, FR-037. Absent DigiKey is an ordinary state, not a broken app."""

    @pytest.mark.parametrize('path', [
        '/products/digikey/orders',
        '/products/digikey/part',
    ])
    def test_the_digikey_pages_say_so(self, app, client, path):
        app.config['DIGIKEY_CLIENT'] = None
        response = client.get(path)
        assert response.status_code == 200
        assert b'digikey-not-configured' in response.data

    @pytest.mark.parametrize('path', [
        '/products',
        '/products/new',
        '/products/capture',
        '/products/reorder',
        '/products/categories',
        '/products/tags',
    ])
    def test_every_other_page_is_unaffected(self, app, client, path):
        """FR-037. Including the Amazon capture, which shares nothing with this."""
        app.config['DIGIKEY_CLIENT'] = None
        assert client.get(path).status_code == 200

    def test_scanning_is_unaffected(self, app, client, test_storage):
        app.config['DIGIKEY_CLIENT'] = None
        catalog = CatalogService(test_storage)
        catalog.create_product(
            description='A thing', identifiers=[{'id_type': 'MPN', 'value': 'LM358N'}]
        )
        response = client.post('/api/scan', json={'scan': 'LM358N'})
        assert response.status_code == 200
        assert response.get_json()['outcome'] == 'search'

    def test_a_distributor_label_still_makes_a_draft(self, app, client):
        """The pre-024 behaviour, with no DigiKey to enrich it."""
        app.config['DIGIKEY_CLIENT'] = None
        RS, GS, EOT = "\x1e", "\x1d", "\x04"
        label = ("[)>" + RS + "06" + GS + "P296-1234-5-ND" + GS + "1PLM358N"
                 + GS + "Q100" + RS + EOT)
        payload = client.post('/api/scan', json={'scan': label}).get_json()
        assert payload['outcome'] == 'create'
        assert payload['prefill']['identifier'] == 'LM358N'

    def test_receiving_a_purchase_is_unaffected(self, app, client, test_storage):
        app.config['DIGIKEY_CLIENT'] = None
        catalog = CatalogService(test_storage)
        product = catalog.create_product(description='A thing')
        purchase = catalog.record_purchase(product.id, vendor='Mouser')
        assert client.get(f'/purchases/{purchase.id}/receive').status_code == 200
