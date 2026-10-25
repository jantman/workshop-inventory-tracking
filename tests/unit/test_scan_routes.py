"""
Route tests for POST /api/scan.

The endpoint's contract in one line: 200 for every well-formed request, and 4xx
only when the *request* is malformed. "Unrecognized" is a successful answer.
"""

import pytest

from app.catalog_service import CatalogService

VALID_UPC_A = "012345678905"


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


class TestSuccessfulAnswers:
    def test_a_known_code_returns_the_product_and_where_to_go(self, client, service):
        product = service.create_product(description='Blue widget')

        response = client.post('/api/scan', json={'scan': product.internal_code})

        assert response.status_code == 200
        body = response.get_json()
        assert body['outcome'] == 'product'
        assert body['product']['id'] == product.id
        # from_scan is what makes the destination offer "add a purchase to this
        # one" rather than just displaying it (FR-019).
        assert body['url'].startswith(f'/products/{product.id}')
        assert 'from_scan=1' in body['url']

    def test_an_unknown_barcode_is_200_with_an_offer_to_create(self, client):
        """Not a 404 -- FR-018"""
        response = client.post('/api/scan', json={'scan': VALID_UPC_A})

        assert response.status_code == 200
        body = response.get_json()
        assert body['outcome'] == 'create'
        assert body['prefill']['identifier'] == '00012345678905'
        assert '/products/new' in body['url']
        assert 'identifier=00012345678905' in body['url']

    def test_a_ja_id_is_200_and_goes_to_the_items_edit_page(self, client):
        """Feature 067: no existence check -- the edit page answers a miss"""
        response = client.post('/api/scan', json={'scan': 'ja000123'})

        assert response.status_code == 200
        body = response.get_json()
        assert body['outcome'] == 'item'
        assert body['product'] is None
        assert body['url'] == '/inventory/edit/JA000123'

    def test_junk_is_200_with_a_search(self, client):
        response = client.post('/api/scan', json={'scan': 'total nonsense'})

        assert response.status_code == 200
        body = response.get_json()
        assert body['outcome'] == 'search'
        assert '/products' in body['url']

    def test_an_empty_scan_is_a_successful_search_not_an_error(self, client):
        response = client.post('/api/scan', json={'scan': ''})
        assert response.status_code == 200
        assert response.get_json()['outcome'] == 'search'

    def test_control_characters_do_not_break_the_endpoint(self, client):
        response = client.post('/api/scan', json={'scan': '\x1d\x1e\x04junk'})
        assert response.status_code == 200

    def test_the_raw_scan_is_echoed_back(self, client):
        response = client.post('/api/scan', json={'scan': '  012345678905  '})
        assert response.get_json()['classification']['raw'] == '  012345678905  '


class TestMalformedRequests:
    """4xx is reserved for the request, never for the scan"""

    def test_a_missing_scan_field_is_400(self, client):
        response = client.post('/api/scan', json={})
        assert response.status_code == 400

    def test_a_non_string_scan_is_400(self, client):
        response = client.post('/api/scan', json={'scan': 12345})
        assert response.status_code == 400

    def test_a_null_scan_is_400(self, client):
        response = client.post('/api/scan', json={'scan': None})
        assert response.status_code == 400

    def test_no_body_at_all_is_400(self, client):
        response = client.post('/api/scan')
        assert response.status_code == 400


class TestCreateFormCarriesTheScan:
    """FR-018: the offer to create arrives with the identifier already on it"""

    def test_the_create_url_opens_a_form_carrying_the_identifier(self, client):
        url = client.post('/api/scan', json={'scan': VALID_UPC_A}).get_json()['url']

        page = client.get(url)
        assert page.status_code == 200
        assert b'00012345678905' in page.data


class TestHandheldFlag:
    """068: ``handheld: true`` changes only the URL, and only for the outcomes
    that have a handheld screen. The cases above are the flag-absent contract."""

    def test_an_item_goes_to_the_handheld_item_screen(self, client):
        response = client.post('/api/scan', json={'scan': 'ja000123', 'handheld': True})

        body = response.get_json()
        assert body['outcome'] == 'item'
        assert body['url'] == '/h/item/JA000123'

    def test_a_product_goes_to_the_handheld_product_screen(self, client, service):
        product = service.create_product(description='Blue widget')

        response = client.post(
            '/api/scan', json={'scan': product.internal_code, 'handheld': True}
        )

        body = response.get_json()
        assert body['outcome'] == 'product'
        assert body['product']['id'] == product.id
        assert body['url'] == f'/h/product/{product.id}'

    @pytest.mark.parametrize('scan', [VALID_UPC_A, 'total nonsense'])
    def test_create_and_search_keep_their_desktop_url(self, client, scan):
        desktop = client.post('/api/scan', json={'scan': scan}).get_json()
        handheld = client.post('/api/scan', json={'scan': scan, 'handheld': True}).get_json()

        assert desktop['outcome'] in ('create', 'search')
        assert handheld['outcome'] == desktop['outcome']
        assert handheld['url'] == desktop['url']

    @pytest.mark.parametrize('flag', [False, None, 0, ''])
    def test_a_falsy_flag_gives_the_desktop_url(self, client, flag):
        response = client.post('/api/scan', json={'scan': 'ja000123', 'handheld': flag})

        assert response.get_json()['url'] == '/inventory/edit/JA000123'


class TestHandheldReceiveUrls:
    """068 US6/US7 (scan-api.md): a receive scan with the flag lands on the
    handheld receive, choice or order screen; without it, today's URLs. The
    branching is the same either way."""

    DIGIKEY_ORDER = '100882558'
    DIGIKEY_PART = '1866-3032-ND'
    MCMASTER_PART = '97387A173'

    def _digikey_line(self, service, product, order=DIGIKEY_ORDER, **fields):
        return service.record_purchase(
            product.id, vendor='DigiKey', vendor_item_id=self.DIGIKEY_PART,
            supplier_order_reference=order, quantity=10, **fields,
        )

    def _mcmaster_line(self, service, product, order):
        return service.record_purchase(
            product.id, vendor='McMaster-Carr', vendor_item_id=self.MCMASTER_PART,
            supplier_order_reference=order, quantity=100,
        )

    def _urls(self, client, scan):
        desktop = client.post('/api/scan', json={'scan': scan}).get_json()
        handheld = client.post('/api/scan', json={'scan': scan, 'handheld': True}).get_json()
        assert desktop['outcome'] == handheld['outcome'] == 'receive'
        return desktop['url'], handheld['url']

    def test_one_outstanding_line_goes_to_the_handheld_receive_screen(self, client, service):
        from tests.unit.test_digikey_receive import bag_label

        product = service.create_product(description='AC/DC converter')
        line = self._digikey_line(service, product)

        desktop, handheld = self._urls(client, bag_label(quantity='3'))

        assert desktop == f'/purchases/{line.id}/receive?quantity=3'
        assert handheld == f'/h/receive/{line.id}?quantity=3'

    def test_several_mcmaster_lines_go_to_the_handheld_choice_page(self, client, service):
        product = service.create_product(description='Rivets')
        self._mcmaster_line(service, product, 'FIRST-ORDER')
        self._mcmaster_line(service, product, 'LATER-ORDER')

        desktop, handheld = self._urls(client, self.MCMASTER_PART)

        assert desktop == f'/products/purchases/receive-choice?scan={self.MCMASTER_PART}'
        assert handheld == f'/h/receive/choose?scan={self.MCMASTER_PART}'

    def test_several_digikey_lines_go_to_the_handheld_order_screen(self, client, service):
        from tests.unit.test_digikey_receive import bag_label

        product = service.create_product(description='AC/DC converter')
        self._digikey_line(service, product)
        self._digikey_line(service, product)

        desktop, handheld = self._urls(client, bag_label())

        assert desktop == (f'/products/digikey/orders/{self.DIGIKEY_ORDER}'
                           f'?highlight={self.DIGIKEY_PART}')
        assert handheld == (f'/h/orders/DigiKey/{self.DIGIKEY_ORDER}'
                            f'?highlight={self.DIGIKEY_PART}')

    def test_nothing_outstanding_flashes_and_goes_to_the_handheld_order_screen(
            self, client, service):
        from tests.unit.test_digikey_receive import bag_label

        product = service.create_product(description='AC/DC converter')
        line = self._digikey_line(service, product)
        service.receive_purchase(line.id)

        response = client.post('/api/scan', json={'scan': bag_label(), 'handheld': True})

        assert response.get_json()['url'] == (
            f'/h/orders/DigiKey/{self.DIGIKEY_ORDER}?highlight={self.DIGIKEY_PART}'
        )
        with client.session_transaction() as session:
            flashes = session.get('_flashes', [])
        assert ('info', f'That line of DigiKey order {self.DIGIKEY_ORDER} is already received.') \
            in flashes
        assert service.get_purchase(line.id).received_date is not None
