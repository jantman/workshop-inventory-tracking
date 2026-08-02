"""
CSRF behaviour of the product catalogue's AJAX endpoints, with protection ON.

The rest of the suite runs with ``WTF_CSRF_ENABLED = False``, which is what let a
real bug through review: every one of these endpoints is called by fetch() from
the browser, none of them carried a token, and all six returned 400 in any
configuration that is not a test. Nothing in the suite could see it.

These tests build an app with CSRF **enabled** -- the production setting -- so the
failure mode is reproducible here rather than only on the workshop cart.
"""

import io
import re

import pytest

from app import create_app
from app.catalog_service import CatalogService
from tests.test_config import TestConfig


class CsrfEnabledConfig(TestConfig):
    """TestConfig, except CSRF is on -- as it is everywhere but the tests"""
    WTF_CSRF_ENABLED = True


@pytest.fixture
def csrf_app(test_storage):
    app = create_app(CsrfEnabledConfig, storage_backend=test_storage)
    with app.app_context():
        yield app


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


@pytest.fixture
def token(csrf_client):
    """The token the browser would use: read off the meta tag in base.html.

    It has to come from a page fetched by *this* client, because a CSRF token is
    bound to the session that issued it -- one minted in a detached request
    context belongs to a different session and is rejected.
    """
    body = csrf_client.get('/products').data.decode()
    match = re.search(r'name="csrf-token" content="([^"]+)"', body)
    assert match, 'base.html is not rendering the csrf-token meta tag'
    return match.group(1)


@pytest.fixture
def product(test_storage):
    return CatalogService(test_storage).create_product(description='Blue widget')


def header(token):
    """The header Flask-WTF accepts, and the one js/csrf.js sends"""
    return {'X-CSRFToken': token}


class TestProtectionIsActuallyOn:
    """If these start passing without a token, the config stopped protecting"""

    def test_scan_without_a_token_is_rejected(self, csrf_client):
        assert csrf_client.post('/api/scan', json={'scan': 'x'}).status_code == 400

    def test_quantity_without_a_token_is_rejected(self, csrf_client, product):
        response = csrf_client.patch(
            f'/api/products/{product.id}/quantity', json={'quantity': 1}
        )
        assert response.status_code == 400

    def test_label_without_a_token_is_rejected(self, csrf_client, product):
        response = csrf_client.post(
            f'/api/products/{product.id}/label', json={'label_type': 'Sato 2x4'}
        )
        assert response.status_code == 400


class TestTheClientCanReachEveryEndpoint:
    """What js/csrf.js sends must be accepted, or the feature is dead in prod"""

    def test_scan(self, csrf_client, token, product):
        response = csrf_client.post(
            '/api/scan', json={'scan': product.internal_code}, headers=header(token)
        )
        assert response.status_code == 200
        assert response.get_json()['outcome'] == 'product'

    def test_set_quantity(self, csrf_client, token, product):
        response = csrf_client.patch(
            f'/api/products/{product.id}/quantity',
            json={'quantity': 3}, headers=header(token),
        )
        assert response.status_code == 200
        assert response.get_json()['product']['quantity'] == 3

    def test_stop_tracking_quantity(self, csrf_client, token, product):
        response = csrf_client.patch(
            f'/api/products/{product.id}/quantity',
            json={'quantity': None}, headers=header(token),
        )
        assert response.status_code == 200
        assert response.get_json()['product']['quantity'] is None

    def test_set_stock_status(self, csrf_client, token, product):
        response = csrf_client.patch(
            f'/api/products/{product.id}/stock-status',
            json={'stock_status': 'low'}, headers=header(token),
        )
        assert response.status_code == 200
        assert response.get_json()['product']['stock_status'] == 'low'

    def test_print_label(self, csrf_client, token, product):
        response = csrf_client.post(
            f'/api/products/{product.id}/label',
            json={'label_type': 'Sato 2x4'}, headers=header(token),
        )
        assert response.status_code == 200

    def test_add_identifier(self, csrf_client, token, product):
        response = csrf_client.post(
            f'/api/products/{product.id}/identifiers',
            json={'id_type': 'MPN', 'value': 'ACME-1'}, headers=header(token),
        )
        assert response.status_code == 201

    def test_create_product(self, csrf_client, token):
        response = csrf_client.post(
            '/api/products', json={'description': 'From JSON'}, headers=header(token)
        )
        assert response.status_code == 201

    def test_upload_and_delete_an_attachment(self, csrf_client, token, product):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new('RGB', (20, 20), (0, 0, 0)).save(buffer, format='PNG')
        buffer.seek(0)

        created = csrf_client.post(
            f'/api/products/{product.id}/attachments',
            data={'file': (buffer, 'datasheet.png')},
            content_type='multipart/form-data',
            headers=header(token),
        )
        assert created.status_code == 201

        attachment_id = created.get_json()['attachment']['id']
        deleted = csrf_client.delete(
            f'/api/attachments/{attachment_id}', headers=header(token)
        )
        assert deleted.status_code == 204


class TestReadsNeedNoToken:
    """CSRF governs state changes; a GET must not be made harder than it is"""

    @pytest.mark.parametrize('path', [
        '/api/categories',
        '/api/tags',
        '/api/products/search',
        '/api/labels/types',
    ])
    def test_get_endpoints_work_without_a_token(self, csrf_client, path):
        assert csrf_client.get(path).status_code == 200


class TestTheCaptureExemption:
    """The one endpoint that genuinely cannot carry a token"""

    def test_capture_is_exempt_because_it_arrives_from_a_vendors_origin(self, csrf_client):
        response = csrf_client.post('/api/capture', json={
            'url': 'https://www.amazon.com/dp/B0ABCDEFGH',
            'listing_title': 'Blue Widget',
        })
        assert response.status_code == 201

    def test_and_it_is_the_only_exemption_this_feature_adds(self):
        """A new exemption should be a deliberate act, not a drift"""
        import re
        from pathlib import Path

        source = Path('app/product/routes.py').read_text()
        assert len(re.findall(r'^@csrf\.exempt', source, re.M)) == 1


class TestPagesCarryTheToken:
    """js/csrf.js reads the token from a meta tag; it has to be there"""

    @pytest.mark.parametrize('path', ['/products', '/products/new', '/products/reorder'])
    def test_the_meta_tag_is_rendered(self, csrf_client, path):
        body = csrf_client.get(path).data
        assert b'name="csrf-token"' in body
