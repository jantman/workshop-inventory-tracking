"""
The scheme the browser used, not the one the proxy handed us (issue #89).

nginx terminates TLS and talks plain HTTP to the app, so without
``ProxyFix`` Werkzeug reports ``request.scheme == 'http'`` for a page the
operator loaded over ``https``. The capture page is where that stops being
cosmetic: its bookmarklet bakes in ``url_for(..., _external=True)`` addresses
when the page renders, so it shipped ``http://`` addresses that a vendor's
``upgrade-insecure-requests`` rewrote to ``https`` and broke -- while the page
displayed a warning telling the operator to do the thing they had already done.

The warning itself is still right and still tested: reached over plain http, with
no proxy in front, nothing has changed.
"""

import html
import re

import pytest


def bookmarklet_of(response):
    """The bookmarklet's href, unescaped"""
    match = re.search(
        r'id="capture-bookmarklet"\s*\n\s*href="([^"]*)"', response.data.decode(),
    )
    assert match, 'the bookmarklet is not on the page'
    return html.unescape(match.group(1))


@pytest.mark.unit
class TestTheForwardedSchemeIsBelieved:
    def test_the_warning_is_gone_when_the_proxy_says_https(self, client):
        response = client.get(
            '/products/capture', headers={'X-Forwarded-Proto': 'https'},
        )

        assert response.status_code == 200
        assert b'id="bookmarklet-http-warning"' not in response.data

    def test_both_baked_in_addresses_are_https(self, client):
        """The failure the warning box exists to prevent, caused by the app itself"""
        href = bookmarklet_of(client.get(
            '/products/capture', headers={'X-Forwarded-Proto': 'https'},
        ))

        assert "s.src='https://localhost/static/js/capture-agent.js" in href
        assert "s.dataset.endpoint='https://localhost/api/capture'" in href
        assert 'http://' not in href

    def test_the_forwarded_host_is_believed_too(self, client):
        """A container's own hostname is no use to a browser on the LAN"""
        href = bookmarklet_of(client.get('/products/capture', headers={
            'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'shop.example.com',
        }))

        assert "s.src='https://shop.example.com/static/js/capture-agent.js" in href
        assert "s.dataset.endpoint='https://shop.example.com/api/capture'" in href


@pytest.mark.unit
class TestPlainHttpIsUnchanged:
    """No proxy, no headers: the app reads the connection it actually got"""

    def test_the_warning_is_shown(self, client):
        response = client.get('/products/capture')

        assert b'id="bookmarklet-http-warning"' in response.data

    def test_both_baked_in_addresses_are_http(self, client):
        href = bookmarklet_of(client.get('/products/capture'))

        assert "s.src='http://localhost/static/js/capture-agent.js" in href
        assert "s.dataset.endpoint='http://localhost/api/capture'" in href
