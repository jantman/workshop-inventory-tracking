"""
The scheme, host and port the browser used, not the ones the proxy handed us.

nginx terminates TLS and talks plain HTTP to the app, so without
``ProxyFix`` Werkzeug reports ``request.scheme == 'http'`` for a page the
operator loaded over ``https``. The capture page is where that stops being
cosmetic: its bookmarklet bakes in ``url_for(..., _external=True)`` addresses
when the page renders, so it shipped ``http://`` addresses that a vendor's
``upgrade-insecure-requests`` rewrote to ``https`` and broke -- while the page
displayed a warning telling the operator to do the thing they had already done.

The warning itself is still right and still tested: reached over plain http, with
no proxy in front, nothing has changed.

The port is the second half of that story and it cost more (issue #114).
``x_host=1`` makes Werkzeug believe an ``X-Forwarded-Host`` that carries no
port, overwriting an ``HTTP_HOST`` that did -- so a deployment behind a proxy
on a non-default port ends up believing it lives where the browser never was.
The reported symptom was a bookmarklet pointing at 443, where nothing listens.
The disabling one was that every CSRF-protected form over https was refused
with "The referrer does not match the host", because that check compares the
referrer against ``request.host``. Reads were unaffected, which is why the
deployment looked healthy right up until someone tried to save something.

Until then every test in this file used either the default host or a bare
hostname. **No test anywhere used a non-default port**, so the one
configuration that breaks was the one configuration never exercised, and a
defect that disabled every write shipped unnoticed for two days. That is the
gap the port tests below exist to close.
"""

import html
import re

import pytest
from flask import request
from flask_wtf.csrf import same_origin

#: What a TLS-terminating proxy declares for a browser on ``https``. The port
#: is deliberately absent: it is the variable under test in what follows.
PROXY_HEADERS = {
    'X-Forwarded-Proto': 'https',
    'X-Forwarded-Host': 'titan.example.com',
}


def bookmarklet_of(response):
    """The bookmarklet's href, unescaped"""
    match = re.search(
        r'id="capture-bookmarklet"\s*\n\s*href="([^"]*)"', response.data.decode(),
    )
    assert match, 'the bookmarklet is not on the page'
    return html.unescape(match.group(1))


def addresses_of(response):
    """The bookmarklet's two baked-in addresses: the agent, and the endpoint.

    The agent's keeps its ``?v=`` cache-buster, which is why callers match its
    prefix rather than the whole string.
    """
    href = bookmarklet_of(response)
    agent = re.search(r"s\.src='([^']*)'", href)
    endpoint = re.search(r"s\.dataset\.endpoint='([^']*)'", href)
    assert agent and endpoint, f'the bookmarklet lost an address: {href}'
    return agent.group(1), endpoint.group(1)


@pytest.fixture
def believing_client(app):
    """A client that also reports the address the application believed in.

    ``response.request`` is no use for this. It describes the environ as the
    test client built it, *before* ``ProxyFix`` rewrites it, so it answers
    ``localhost`` for every case below and would make each of these tests pass
    or fail for reasons unconnected to the thing being tested. The value that
    matters is the one Flask's ``request`` holds while the view runs: it is
    what ``url_for(..., _external=True)`` builds from, and what Flask-WTF's
    referrer check compares against.

    Registering the hook here is safe because the ``app`` fixture is
    function-scoped, so this runs before that app has served anything.
    """
    believed = {}

    @app.after_request
    def _capture(response):
        believed['host'] = request.host
        believed['is_secure'] = request.is_secure
        return response

    client = app.test_client()

    def get(path, **kwargs):
        believed.clear()
        return client.get(path, **kwargs), dict(believed)

    return get


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


@pytest.mark.unit
class TestTheForwardedPortIsBelieved:
    """A deployment behind a proxy on a non-default port (issue #114)"""

    def test_both_baked_in_addresses_carry_the_port(self, client):
        """FR-008. The bookmarklet must work from a *vendor's* origin.

        Every other address the app builds is relative and was unaffected,
        which is most of why this went unnoticed.
        """
        agent, endpoint = addresses_of(client.get(
            '/products/capture',
            headers={**PROXY_HEADERS, 'X-Forwarded-Port': '15603'},
        ))

        assert agent.startswith(
            'https://titan.example.com:15603/static/js/capture-agent.js'
        )
        assert endpoint == 'https://titan.example.com:15603/api/capture'

    def test_the_believed_host_carries_the_port(self, believing_client):
        """FR-009. ``request.host`` is what the referrer check compares."""
        _, believed = believing_client(
            '/products/capture',
            headers={**PROXY_HEADERS, 'X-Forwarded-Port': '15603'},
        )

        assert believed['host'] == 'titan.example.com:15603'

    def test_a_form_from_that_port_is_same_origin(self, believing_client):
        """FR-004. The 400 the deployment returned, expressed as its cause.

        ``CSRFProtect.protect`` builds ``f'https://{request.host}/'`` and
        compares the referrer against it with this same function. Asserting
        the comparison rather than the host is what makes this a test of the
        refused POST instead of a test near one -- the port is precisely what
        ``same_origin`` compares, and it is the only part that was wrong.
        """
        _, believed = believing_client(
            '/products/capture',
            headers={**PROXY_HEADERS, 'X-Forwarded-Port': '15603'},
        )

        assert believed['is_secure'], 'the check only runs on a secure request'
        assert same_origin(
            'https://titan.example.com:15603/products/capture',
            f"https://{believed['host']}/",
        )


@pytest.mark.unit
class TestADefaultPortIsNeverWritten:
    """FR-003. A standard port must not reach an address, or the referrer
    check starts refusing the deployments that work today.

    Worth testing precisely because ``ProxyFix``'s own source predicts
    otherwise: its ``x_port`` branch appends the declared port to the host
    with no check for whether it is the scheme's default. What saves it is a
    layer further down, in ``werkzeug.sansio.utils.get_host``, which omits
    standard ports. If that ever changed, every deployment on 443 declaring
    its port would begin refusing its own forms -- ``same_origin`` compares
    parsed ports, and 443 is not ``None``.
    """

    def test_https_on_443_carries_no_port(self, believing_client):
        response, believed = believing_client(
            '/products/capture',
            headers={**PROXY_HEADERS, 'X-Forwarded-Port': '443'},
        )
        _, endpoint = addresses_of(response)

        assert believed['host'] == 'titan.example.com'
        assert endpoint == 'https://titan.example.com/api/capture'
        assert same_origin(
            'https://titan.example.com/products/capture',
            f"https://{believed['host']}/",
        )

    def test_http_on_80_carries_no_port(self, believing_client):
        response, believed = believing_client('/products/capture', headers={
            'X-Forwarded-Proto': 'http',
            'X-Forwarded-Host': 'titan.example.com',
            'X-Forwarded-Port': '80',
        })
        _, endpoint = addresses_of(response)

        assert believed['host'] == 'titan.example.com'
        assert endpoint == 'http://titan.example.com/api/capture'


@pytest.mark.unit
class TestAMalformedPortIsRefused:
    """FR-007. The one input where trusting the declaration is worse than not.

    ``ProxyFix`` composes ``titan.example.com:not-a-port``, and ``get_host``
    returns the **empty string** for a host containing characters a host
    cannot contain. Every address the application builds then comes out as
    ``https:///...``, with no error and no log line -- a site whose every link
    is malformed. Before the port was trusted at all the same input was simply
    ignored, so these tests are what keep the worse outcome from being new.
    """

    @pytest.mark.parametrize(
        'port', ['not-a-port', '15603abc', '-1', '15603 80', ''],
    )
    def test_the_arriving_host_stands(self, believing_client, port):
        response, believed = believing_client(
            '/products/capture',
            headers={**PROXY_HEADERS, 'X-Forwarded-Port': port},
        )
        agent, endpoint = addresses_of(response)

        assert believed['host'] == 'titan.example.com'
        assert endpoint == 'https://titan.example.com/api/capture'
        assert 'https:///' not in agent
