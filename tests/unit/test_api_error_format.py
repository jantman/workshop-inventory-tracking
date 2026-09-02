"""An /api/ route answers a failure with JSON, never with a redirect (#132).

``request.is_json`` reports what the caller **sent**. A DELETE has no body and no
Content-Type, so every centralized error handler used to answer one with a flash
message and a 302 -- which ``fetch`` follows, reads as a 200, and reports as
success. The client branch written to handle the failure never ran.

The fix is one predicate, ``wants_json()``, asked at every handler. These tests
cover it from both ends: the predicate directly over the paths that matter, and
the handlers through real routes, with no request body, which is the shape that
was broken.
"""

import pytest

from app.error_handlers import wants_json


class TestWantsJson:
    """The predicate itself.

    The branch it replaces is character-identical at all nine call sites, so
    this is the test that carries the change. The route-level tests below prove
    it is wired in; this one proves it is right.
    """

    def test_an_api_path_wants_json(self, app):
        with app.test_request_context('/api/products/1'):
            assert wants_json() is True

    def test_an_admin_api_path_wants_json(self, app):
        """The admin blueprint carries url_prefix='/admin'.

        Its routes are declared ``@bp.route('/api/materials/validate')`` and
        served at ``/admin/api/materials/validate``. Reading the decorators is
        what makes a bare '/api/' prefix check look sufficient; it is not.
        """
        with app.test_request_context('/admin/api/materials/validate'):
            assert wants_json() is True

    def test_a_page_path_does_not(self, app):
        with app.test_request_context('/products/1'):
            assert wants_json() is False

    def test_a_page_path_with_api_as_a_variable_segment_does_not(self, app):
        """``/products/orders/<vendor>/<order_number>`` with vendor 'api'.

        A substring test -- ``'/api/' in request.path`` -- would call this page
        request machine-facing on the strength of one order's vendor name. The
        prefix tuple cannot be defeated that way, which is why it is a tuple and
        not an ``in``.
        """
        with app.test_request_context('/products/orders/api/12345'):
            assert wants_json() is False

    def test_a_page_path_that_sent_json_still_does(self, app):
        """The ``or request.is_json`` clause, which is what makes the predicate
        a superset of the one it replaces: a caller getting JSON today keeps it.
        """
        with app.test_request_context('/products/1',
                                      content_type='application/json'):
            assert wants_json() is True


class TestApiRoutesAnswerWithJson:
    """Through real routes, with no request body -- the broken shape.

    Every id named here does not exist, so nothing is destroyed. The assertion
    that encodes the bug is ``'Location' not in response.headers``: a redirect is
    what the client could not tell apart from success.
    """

    @pytest.mark.parametrize('method,path', [
        ('get', '/api/products/999999'),
        ('delete', '/api/attachments/999999'),
        ('delete', '/api/products/1/identifiers/999999'),
    ])
    def test_a_missing_item_is_a_json_404(self, client, method, path):
        response = getattr(client, method)(path)

        assert response.status_code == 404
        assert response.content_type == 'application/json'
        assert response.get_json()['success'] is False
        assert 'Location' not in response.headers

    def test_an_unrouted_api_path_is_a_json_404(self, client):
        """Was a 302 to /index -- so a misspelled endpoint returned the home
        page with a 200 once ``fetch`` had followed it.
        """
        response = client.get('/api/no-such-route')

        assert response.status_code == 404
        assert response.content_type == 'application/json'
        assert 'Location' not in response.headers

    def test_the_payload_is_the_one_json_callers_already_got(self, client):
        """FR-005. The set of requests answered with JSON widened; the JSON did
        not change. Asserted by comparing the two requests that used to differ:
        same route, same (absent) body, one declaring a content type.
        """
        without = client.get('/api/products/999999').get_json()
        with_type = client.get(
            '/api/products/999999', content_type='application/json'
        ).get_json()

        assert set(without) == {
            'success', 'error_id', 'error_code', 'error_type',
            'message', 'details', 'recovery_suggestions',
        }
        # error_id is a timestamp, so it differs between any two calls.
        without.pop('error_id')
        with_type.pop('error_id')
        assert without == with_type


class TestPageRoutesAreUnchanged:
    """The half of the contract that must not move.

    The predicate preserves this by construction -- it only ever adds requests
    to the JSON set. That is a claim about the code; these are the tests that
    make it a claim about the behaviour.
    """

    def test_a_missing_product_page_still_redirects(self, client):
        response = client.get('/products/999999')

        assert response.status_code == 302
        assert response.headers['Location'].endswith('/inventory')

    def test_a_page_route_asked_in_json_still_answers_in_json(self, client):
        response = client.get('/products/999999',
                              content_type='application/json')

        assert response.status_code == 404
        assert response.content_type == 'application/json'
