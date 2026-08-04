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
