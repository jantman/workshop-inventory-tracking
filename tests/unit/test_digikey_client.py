"""
Unit tests for the DigiKey client (feature 024).

**Nothing here touches the network.** The unit session runs with pytest-blockage,
so every response is served from the two fixtures recorded off the live API on
2026-08-22 and redacted -- see
``specs/024-digikey-order-capture/verification.md``.

The assertion that matters most is that a price is a ``Decimal``. It is easy to
write a client that works perfectly and quietly turns 6.9 into
6.9000000000000004, and nothing would notice until a reconciliation months later.
``test_unit_price_is_decimal_not_float`` is that guard; do not delete it.
"""

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from app.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ItemNotFoundError,
    RateLimitError,
    TemporaryError,
)
from app.models import DigiKeyOrder, DigiKeyPart
from app.services.digikey import DigiKeyClient

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'digikey'

pytestmark = pytest.mark.unit


def _fixture(name):
    return (FIXTURES / name).read_text()


def _client(**kwargs):
    defaults = dict(
        client_id='test-client-id',
        client_secret='test-client-secret',
        account_id='99999999',
        base_url='https://api.example.invalid',
    )
    defaults.update(kwargs)
    return DigiKeyClient(**defaults)


def _response(status=200, text='', headers=None):
    r = Mock(spec=requests.Response)
    r.status_code = status
    r.text = text
    r.headers = headers or {}
    return r


def _token_response():
    return _response(200, json.dumps({
        'access_token': 'a-test-token', 'token_type': 'Bearer', 'expires_in': 599
    }))


class TestGetOrder:
    """The recorded sales order becomes a DigiKeyOrder"""

    def _order(self, body=None):
        client = _client()
        with patch('app.services.digikey.requests.post', return_value=_token_response()), \
                patch('app.services.digikey.requests.get',
                      return_value=_response(200, body or _fixture('salesorder.json'))):
            return client.get_order('100882558')

    def test_reads_the_order_header(self):
        order = self._order()
        assert order.sales_order_number == '100882558'
        assert order.currency == 'USD'
        # The sales order id arrives as a JSON int; it is a reference, not
        # arithmetic, so it must come back as a string.
        assert isinstance(order.sales_order_number, str)

    def test_reads_the_order_date(self):
        # v4 carries DateEntered. The v3 shape did not, and the plan had a
        # two-step fallback for it that T001 made unnecessary.
        order = self._order()
        assert order.order_date is not None
        assert (order.order_date.year, order.order_date.month) == (2026, 8)

    def test_reads_every_line(self):
        order = self._order()
        assert len(order.lines) == 2
        first = order.lines[0]
        assert first.digikey_part_number == '1866-3027-ND'
        assert first.manufacturer_part_number == 'IRM-05-5'
        assert first.description == 'AC/DC CONVERTER 5V 5W'
        assert first.quantity == 5
        assert first.quantity_shipped == 5
        assert first.quantity_backorder == 0
        assert first.country_of_origin == 'CN'

    def test_line_number_comes_from_detail_id(self):
        # PoLineItemNumber is null on every v4 response observed.
        order = self._order()
        assert [line.line_number for line in order.lines] == [1, 2]

    def test_unit_price_is_decimal_not_float(self):
        """The one that would fail silently. Never delete this."""
        order = self._order()
        assert order.lines[0].unit_price == Decimal('6.5')
        assert order.lines[1].unit_price == Decimal('6.9')
        for line in order.lines:
            assert isinstance(line.unit_price, Decimal)
            assert not isinstance(line.unit_price, float)

    def test_a_line_carries_no_manufacturer(self):
        """A v4 order line has no manufacturer name -- that is why capture enriches."""
        order = self._order()
        assert not hasattr(order.lines[0], 'manufacturer')

    def test_personal_details_are_never_read(self):
        order = self._order()
        for attribute in ('contact', 'email', 'shipping_address', 'customer_id'):
            assert not hasattr(order, attribute)

    def test_a_missing_field_costs_that_field_only(self):
        body = json.loads(_fixture('salesorder.json'))
        del body['Currency']
        del body['LineItems'][0]['CountryOfOrigin']
        order = self._order(json.dumps(body))
        assert order.currency == ''
        assert order.lines[0].country_of_origin == ''
        # Everything else survived.
        assert order.lines[0].unit_price == Decimal('6.5')
        assert len(order.lines) == 2

    def test_a_line_with_no_manufacturer_part_number_still_parses(self):
        # FR-016. No order on the developer's account has such a line, so this
        # fixture is hand-built from the real one and says so.
        body = json.loads(_fixture('salesorder.json'))
        body['LineItems'][0]['ManufacturerProductNumber'] = ''
        order = self._order(json.dumps(body))
        assert order.lines[0].manufacturer_part_number == ''
        assert order.lines[0].digikey_part_number == '1866-3027-ND'

    def test_a_line_with_no_digikey_part_number_is_dropped(self):
        # It is half the key a scanned bag matches on; a line without one is not
        # a line this catalog can do anything with.
        body = json.loads(_fixture('salesorder.json'))
        body['LineItems'][0]['DigiKeyProductNumber'] = ''
        order = self._order(json.dumps(body))
        assert len(order.lines) == 1
        assert order.lines[0].digikey_part_number == '1866-3032-ND'

    def test_a_200_naming_no_order_is_not_found(self):
        with pytest.raises(ItemNotFoundError):
            self._order('{"Something": "else"}')


class TestGetPart:
    """The recorded product detail becomes a DigiKeyPart"""

    def _part(self, body=None):
        client = _client()
        with patch('app.services.digikey.requests.post', return_value=_token_response()), \
                patch('app.services.digikey.requests.get',
                      return_value=_response(200, body or _fixture('productdetails.json'))):
            return client.get_part('1866-3027-ND')

    def test_unwraps_the_nested_fields(self):
        # Manufacturer, Description and Category are objects in v4, not strings.
        part = self._part()
        assert part.manufacturer == 'MEAN WELL USA Inc.'
        assert part.description == 'AC/DC CONVERTER 5V 5W'
        assert part.category_path == 'Power Supplies - Board Mount'
        assert part.manufacturer_part_number == 'IRM-05-5'

    def test_reads_the_documents(self):
        part = self._part()
        assert part.datasheet_url.startswith('https://')
        assert part.photo_url.startswith('https://')
        assert part.product_url.startswith('https://')

    def test_reads_the_parameters_in_order(self):
        part = self._part()
        assert len(part.parameters) == 17
        names = [name for name, _ in part.parameters]
        assert names[0] == 'Type'
        assert all(isinstance(v, str) for _, v in part.parameters)

    def test_unit_price_is_decimal(self):
        part = self._part()
        assert isinstance(part.unit_price, Decimal)
        assert part.unit_price == Decimal('6.8')

    def test_missing_nested_objects_do_not_raise(self):
        body = json.loads(_fixture('productdetails.json'))
        del body['Product']['Manufacturer']
        del body['Product']['Category']
        del body['Product']['Parameters']
        part = self._part(json.dumps(body))
        assert part.manufacturer == ''
        assert part.category_path == ''
        assert part.parameters == ()
        # The rest is intact -- a missing datasheet is a part without a
        # datasheet, never a failed lookup.
        assert part.manufacturer_part_number == 'IRM-05-5'

    def test_a_200_naming_no_product_is_not_found(self):
        with pytest.raises(ItemNotFoundError):
            self._part('{"Product": null}')


class TestFailureMapping:
    """Each condition raises the exception the operator's message is built from"""

    def _call(self, get_response=None, post_response=None, **client_kwargs):
        client = _client(**client_kwargs)
        with patch('app.services.digikey.requests.post',
                   return_value=post_response or _token_response()), \
                patch('app.services.digikey.requests.get',
                      return_value=get_response or _response(200, '{}')):
            return client.get_order('100882558')

    def test_no_credentials_is_configuration(self):
        with pytest.raises(ConfigurationError) as e:
            self._call(client_id='', client_secret='')
        assert 'DIGIKEY_CLIENT_ID' in str(e.value)

    def test_no_account_id_is_configuration_not_authentication(self):
        """The distinction that matters: telling them to re-authorize is useless."""
        with pytest.raises(ConfigurationError) as e:
            self._call(account_id='')
        assert 'DIGIKEY_ACCOUNT_ID' in str(e.value)

    def test_account_id_must_not_be_zero_is_configuration(self):
        # DigiKey's own wording when nothing named the account. A 400 that would
        # otherwise read as a bad request.
        body = '{"status": 400, "detail": "Account ID must not be 0"}'
        with pytest.raises(ConfigurationError) as e:
            self._call(get_response=_response(400, body))
        assert 'DIGIKEY_ACCOUNT_ID' in str(e.value)

    @pytest.mark.parametrize('status', [401, 403])
    def test_refused_request_is_authentication(self, status):
        with pytest.raises(AuthenticationError):
            self._call(get_response=_response(status, 'nope'))

    def test_refused_token_is_authentication(self):
        with pytest.raises(AuthenticationError):
            self._call(post_response=_response(401, 'bad client'))

    def test_404_is_not_found(self):
        with pytest.raises(ItemNotFoundError):
            self._call(get_response=_response(404, 'no such order'))

    def test_429_is_rate_limited_and_says_when(self):
        with pytest.raises(RateLimitError) as e:
            self._call(get_response=_response(
                429, 'slow down', {'X-RateLimit-ResetTime': '2026-08-22T18:00:00Z'}
            ))
        assert '2026-08-22T18:00:00Z' in str(e.value)

    def test_500_is_temporary(self):
        with pytest.raises(TemporaryError):
            self._call(get_response=_response(500, 'boom'))

    def test_unreachable_is_temporary(self):
        client = _client()
        with patch('app.services.digikey.requests.post', return_value=_token_response()), \
                patch('app.services.digikey.requests.get',
                      side_effect=requests.ConnectionError('no route to host')):
            with pytest.raises(TemporaryError):
                client.get_order('100882558')

    def test_unparseable_body_is_temporary(self):
        with pytest.raises(TemporaryError):
            self._call(get_response=_response(200, 'this is not json'))

    def test_a_404_on_a_part_says_part_not_order(self):
        client = _client()
        with patch('app.services.digikey.requests.post', return_value=_token_response()), \
                patch('app.services.digikey.requests.get',
                      return_value=_response(404, 'nope')):
            with pytest.raises(ItemNotFoundError) as e:
                client.get_part('NOT-A-PART')
        assert 'part NOT-A-PART' in str(e.value)


class TestToken:
    """Token handling -- reused while live, never written to disk"""

    def test_token_is_reused_across_calls(self):
        client = _client()
        with patch('app.services.digikey.requests.post',
                   return_value=_token_response()) as post, \
                patch('app.services.digikey.requests.get',
                      return_value=_response(200, _fixture('salesorder.json'))):
            client.get_order('100882558')
            client.get_order('100882558')
        assert post.call_count == 1

    def test_expired_token_is_refetched(self):
        client = _client()
        with patch('app.services.digikey.requests.post',
                   return_value=_token_response()) as post, \
                patch('app.services.digikey.requests.get',
                      return_value=_response(200, _fixture('salesorder.json'))):
            client.get_order('100882558')
            client._token_expires_at = 0.0  # as though ten minutes had passed
            client.get_order('100882558')
        assert post.call_count == 2

    def test_the_secret_is_not_in_the_repr(self):
        client = _client(client_secret='super-secret-value')
        assert 'super-secret-value' not in repr(client)


class TestNoResponseJson:
    """The module-level prohibition, enforced rather than documented"""

    def test_module_never_calls_response_json(self):
        """Read the AST, not the text.

        A text search finds the module's own docstring explaining the ban, and a
        guard that fires on its own documentation is a guard nobody keeps.
        """
        import ast

        source = (Path(__file__).resolve().parents[2]
                  / 'app' / 'services' / 'digikey.py').read_text()
        offenders = [
            node.lineno
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'json'
        ]
        assert not offenders, (
            f"app/services/digikey.py calls .json() at line(s) {offenders}. It "
            f"must parse with json.loads(body, parse_float=Decimal): "
            f"response.json() returns float prices and violates Constitution III"
        )

    def test_the_guard_would_catch_a_real_offender(self):
        """The guard above is worthless if it cannot fail. Prove it can."""
        import ast

        offenders = [
            node.lineno
            for node in ast.walk(ast.parse('data = response.json()'))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'json'
        ]
        assert offenders == [1]


class TestPartEdgeCases:
    """US3's paths, which US1's enrichment does not exercise"""

    def _part(self, body):
        client = _client()
        with patch('app.services.digikey.requests.post', return_value=_token_response()), \
                patch('app.services.digikey.requests.get',
                      return_value=_response(200, body)):
            return client.get_part('1866-3027-ND')

    def test_an_unknown_part_number_is_not_found(self):
        client = _client()
        with patch('app.services.digikey.requests.post', return_value=_token_response()), \
                patch('app.services.digikey.requests.get',
                      return_value=_response(404, '{"detail": "not found"}')):
            with pytest.raises(ItemNotFoundError):
                client.get_part('NOT-A-REAL-PART')

    def test_a_product_with_no_parameters_is_not_an_error(self):
        body = json.loads(_fixture('productdetails.json'))
        body['Product']['Parameters'] = []
        assert self._part(json.dumps(body)).parameters == ()

    def test_a_parameter_missing_its_value_is_dropped_not_kept_blank(self):
        body = json.loads(_fixture('productdetails.json'))
        body['Product']['Parameters'][0]['ValueText'] = ''
        part = self._part(json.dumps(body))
        assert len(part.parameters) == 16

    def test_a_numeric_parameter_value_survives(self):
        """DigiKey sends some as JSON numbers; they are identifiers, not maths."""
        body = json.loads(_fixture('productdetails.json'))
        body['Product']['Parameters'][0]['ValueText'] = 12
        part = self._part(json.dumps(body))
        assert ('Type', '12') in part.parameters

    def test_a_missing_datasheet_costs_the_datasheet_only(self):
        body = json.loads(_fixture('productdetails.json'))
        body['Product']['DatasheetUrl'] = ''
        part = self._part(json.dumps(body))
        assert part.datasheet_url == ''
        assert part.photo_url.startswith('https://')
        assert part.manufacturer == 'MEAN WELL USA Inc.'

    def test_the_digikey_part_number_comes_off_the_variations(self):
        part = self._part(_fixture('productdetails.json'))
        assert part.digikey_part_number


class TestFixturesCarryNoRealIdentifiers:
    """The check that was missing when a real account number reached a public repo.

    PR #116 review. ``T003`` redacted the sales-order fixture's names and email
    and never looked at the product-details one at all, where DigiKey echoes the
    account back as ``AccountIdUsed`` / ``CustomerIdUsed``. A grep for names
    finds names; it does not find a number.

    So this asserts the shape of the thing instead: every account-ish field in
    every committed fixture must hold the documented placeholder. A future
    fixture recorded from a real call fails here rather than in public.
    """

    PLACEHOLDER = 99999999
    ACCOUNT_KEYS = frozenset({
        'AccountIdUsed', 'CustomerIdUsed', 'CustomerId', 'BillingAccount',
    })

    def _walk(self, node, path=''):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from self._walk(value, f'{path}.{key}')
                if key in self.ACCOUNT_KEYS:
                    yield f'{path}.{key}', value
        elif isinstance(node, list):
            for i, value in enumerate(node):
                yield from self._walk(value, f'{path}[{i}]')

    @pytest.mark.parametrize('name', ['salesorder.json', 'productdetails.json'])
    def test_every_account_field_is_the_placeholder(self, name):
        found = list(self._walk(json.loads(_fixture(name))))
        assert found, f'{name} has no account field -- has the schema changed?'
        for where, value in found:
            assert value == self.PLACEHOLDER, (
                f'{name}{where} is {value!r}, not the {self.PLACEHOLDER} placeholder. '
                f'This repository is public; scrub it before committing.'
            )

    @pytest.mark.parametrize('name', ['salesorder.json', 'productdetails.json'])
    def test_no_personal_details_survive(self, name):
        raw = _fixture(name)
        for marker in ('@', 'Phone"', 'FirstName": "', 'LastName": "'):
            if marker in raw:
                # Present is fine as long as the value was replaced.
                assert 'REDACTED' in raw, f'{name} still carries {marker!r} unredacted'
