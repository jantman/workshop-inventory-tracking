"""An order whose vendor name contains '/' is reachable (issue #219).

The vendor is a URL segment on both the desktop and handheld order screens.
With the default ``string`` converter a vendor such as ``A / B`` built a URL
that no route matched, so every link to the order ended in "not found". The
routes take the vendor with the ``path`` converter; these tests follow the
links the app itself builds and assert they land on the order.

Copyright 2026 Jason Antman
"""

import re

import pytest

from app.catalog_service import CatalogService

pytestmark = pytest.mark.unit

VENDOR = 'Bolt Depot / Fastenal'
ORDER = 'ORD-7'


@pytest.fixture
def service(test_storage) -> CatalogService:
    return CatalogService(test_storage)


@pytest.fixture
def lines(service: CatalogService) -> list:
    product = service.create_product(description='Widget')
    return [
        service.record_purchase(product.id, vendor=VENDOR, supplier_order_reference=ORDER,
                                quantity=2, vendor_item_id=f'P-{n}')
        for n in range(2)
    ]


def _href(html: str, prefix: str) -> str:
    match = re.search(r'href="(%s[^"]*)"' % re.escape(prefix), html)
    assert match, f'no link starting {prefix!r}'
    return match.group(1)


class TestDesktop:
    def test_the_orders_list_links_to_a_page_that_opens(self, client, lines) -> None:
        href = _href(client.get('/products/orders').get_data(as_text=True), '/products/orders/')

        response = client.get(href)

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'not-captured' not in html
        assert 'P-0' in html and 'P-1' in html

    def test_the_outstanding_page_links_to_a_page_that_opens(self, client, lines) -> None:
        html = client.get('/products/outstanding').get_data(as_text=True)
        href = _href(html, '/products/orders/')

        response = client.get(href)

        assert response.status_code == 200
        assert 'not-captured' not in response.get_data(as_text=True)

    def test_receive_lands_back_on_the_order(self, client, service, lines) -> None:
        response = client.post(f'/products/orders/{VENDOR}/{ORDER}/receive',
                               data={'purchase_id': [str(lines[0].id)]})

        assert response.status_code == 302
        assert client.get(response.headers['Location']).status_code == 200
        assert service.get_purchase(lines[0].id).received_date is not None
        assert service.get_purchase(lines[1].id).received_date is None

    def test_the_edit_page_opens(self, client, lines) -> None:
        response = client.get(f'/products/orders/{VENDOR}/{ORDER}/edit')

        assert response.status_code == 200


class TestHandheld:
    def test_the_orders_list_links_to_a_page_that_opens(self, client, lines) -> None:
        href = _href(client.get('/h/orders').get_data(as_text=True), '/h/orders/')

        response = client.get(href)

        assert response.status_code == 200
        boxes = re.findall(r'name="purchase_id"\s+value="(\d+)"',
                           response.get_data(as_text=True))
        assert sorted(boxes) == sorted(str(line.id) for line in lines)

    def test_receive_lands_back_on_the_order(self, client, service, lines) -> None:
        response = client.post(f'/h/orders/{VENDOR}/{ORDER}/receive',
                               data={'purchase_id': [str(lines[1].id)]})

        assert response.status_code == 302
        assert client.get(response.headers['Location']).status_code == 200
        assert service.get_purchase(lines[1].id).received_date is not None
