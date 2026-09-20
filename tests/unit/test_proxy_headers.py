"""
The scheme, host and port the browser used, not the ones the proxy handed us.

nginx terminates TLS and talks plain HTTP to the app, so without ``ProxyFix``
Werkzeug reports ``request.scheme == 'http'`` for a page the operator loaded
over ``https``, and believes an ``X-Forwarded-Host`` that carries no port over
an ``HTTP_HOST`` that did. A deployment behind a proxy on a non-default port
then believes it lives where the browser never was.

**What that costs is every write.** Every CSRF-protected form over https is
refused with "The referrer does not match the host", because that check
compares the referrer against ``request.host``. Reads are unaffected, which is
why such a deployment looks healthy right up until someone tries to save
something (issue #114).

The original symptom was cosmetic by comparison: the capture page baked
``url_for(..., _external=True)`` addresses into a bookmarklet, and shipped a
bookmarklet pointing at port 443 where nothing listens (issue #89, issue #114).
Feature 048 removed that bookmarklet -- the browser extension is told the
application's address by the operator rather than reading it off a rendered
page -- so **no address this application builds is absolute any more**. The
assertions below are therefore about what the application *believes*, which is
what the referrer check reads and the only thing left that a misdeclared port
can break.

Until issue #114 every test in this file used either the default host or a bare
hostname. **No test anywhere used a non-default port**, so the one
configuration that breaks was the one configuration never exercised, and a
defect that disabled every write shipped unnoticed for two days. That is the
gap the port tests below exist to close.
"""

import pytest
from flask import request
from flask_wtf.csrf import same_origin

#: What a TLS-terminating proxy declares for a browser on ``https``. The port
#: is deliberately absent: it is the variable under test in what follows.
PROXY_HEADERS = {
    'X-Forwarded-Proto': 'https',
    'X-Forwarded-Host': 'titan.example.com',
}


@pytest.fixture
def believing_client(app):
    """A client that also reports the address the application believed in.

    ``response.request`` is no use for this. It describes the environ as the
    test client built it, *before* ``ProxyFix`` rewrites it, so it answers
    ``localhost`` for every case below and would make each of these tests pass
    or fail for reasons unconnected to the thing being tested. The value that
    matters is the one Flask's ``request`` holds while the view runs: it is
    what Flask-WTF's referrer check compares against.

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
    def test_the_proxy_s_https_is_believed(self, believing_client):
        """``request.is_secure`` is what the referrer check gates itself on"""
        response, believed = believing_client(
            '/products/capture', headers={'X-Forwarded-Proto': 'https'},
        )

        assert response.status_code == 200
        assert believed['is_secure']

    def test_the_forwarded_host_is_believed_too(self, believing_client):
        """A container's own hostname is no use to a browser on the LAN"""
        _, believed = believing_client('/products/capture', headers={
            'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'shop.example.com',
        })

        assert believed['host'] == 'shop.example.com'


@pytest.mark.unit
class TestPlainHttpIsUnchanged:
    """No proxy, no headers: the app reads the connection it actually got"""

    def test_the_connection_stands(self, believing_client):
        _, believed = believing_client('/products/capture')

        assert believed['host'] == 'localhost'
        assert not believed['is_secure']


@pytest.mark.unit
class TestTheForwardedPortIsBelieved:
    """A deployment behind a proxy on a non-default port (issue #114)"""

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
        _, believed = believing_client(
            '/products/capture',
            headers={**PROXY_HEADERS, 'X-Forwarded-Port': '443'},
        )

        assert believed['host'] == 'titan.example.com'
        assert same_origin(
            'https://titan.example.com/products/capture',
            f"https://{believed['host']}/",
        )

    def test_http_on_80_carries_no_port(self, believing_client):
        _, believed = believing_client('/products/capture', headers={
            'X-Forwarded-Proto': 'http',
            'X-Forwarded-Host': 'titan.example.com',
            'X-Forwarded-Port': '80',
        })

        assert believed['host'] == 'titan.example.com'


@pytest.mark.unit
class TestAMalformedPortIsRefused:
    """FR-007. The one input where trusting the declaration is worse than not.

    ``ProxyFix`` composes ``titan.example.com:not-a-port``, and ``get_host``
    returns the **empty string** for a host containing characters a host
    cannot contain. The application then believes it lives nowhere, with no
    error and no log line -- and every secure write is refused, because the
    referrer can match no such host. Before the port was trusted at all the
    same input was simply ignored, so these tests are what keep the worse
    outcome from being new.
    """

    @pytest.mark.parametrize(
        'port',
        [
            'not-a-port', '15603abc', '-1', '15603 80', '',
            # Numeric but out of range. `isdigit` alone admits these, and
            # `get_host` keeps them because its check is character-class based
            # rather than range based -- so the believed host would carry
            # `:99999999`, and `same_origin` *raises* `ValueError: Port out of
            # range 0-65535` rather than returning False. Every secure write
            # becomes an unhandled 500 instead of a readable 400: reads healthy,
            # writes failing, which is the exact shape of the bug this fixes.
            '65536', '99999999',
        ],
    )
    def test_the_arriving_host_stands(self, believing_client, port):
        _, believed = believing_client(
            '/products/capture',
            headers={**PROXY_HEADERS, 'X-Forwarded-Port': port},
        )

        assert believed['host'] == 'titan.example.com'
        assert same_origin(
            'https://titan.example.com/products/capture',
            f"https://{believed['host']}/",
        )

    def test_the_highest_real_port_is_still_honoured(self, believing_client):
        """The bound must reject what cannot be a port, not what is unusual.

        65535 is a legal port. A guard that turned "reject the absurd" into
        "reject the unfamiliar" would be a new version of the defect this
        feature exists to fix -- a deployment that works, refusing to believe
        its own address.
        """
        _, believed = believing_client(
            '/products/capture',
            headers={**PROXY_HEADERS, 'X-Forwarded-Port': '65535'},
        )

        assert believed['host'] == 'titan.example.com:65535'
