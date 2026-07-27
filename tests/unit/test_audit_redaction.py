"""
Secrets must never reach the audit log.

Seven route handlers pass `request.form.to_dict()` straight into
`log_audit_operation`, so every form POST used to persist its `csrf_token` into
the audit trail. The fix is a single redaction choke point inside the audit
helpers themselves (`app/logging_config.py`), which is what these tests pin:
one place covers all 40+ existing call sites and any future one.

Companion to `tests/unit/test_audit_json_fix.py`, which pins the opposite
requirement — that the benign reconstruction data still round-trips intact.
"""

import io
import json
import logging
import re
from collections import deque, namedtuple
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import ImmutableMultiDict

import app as app_package
from app.logging_config import (
    JSONFormatter,
    MAX_REDACTION_DEPTH,
    REDACTED_VALUE,
    SENSITIVE_FIELD_SUBSTRINGS,
    _is_sensitive_name,
    _redact_payload,
    _redact_sensitive,
    log_audit_batch_operation,
    log_audit_operation,
)

LOGGER_NAME = 'test_audit_redaction'


@pytest.mark.unit
class TestAuditRedaction:
    """Direct helper-level coverage of the redaction choke point."""

    def setup_method(self):
        """Capture the dedicated logger through the real JSON formatter."""
        self.log_capture = io.StringIO()
        self.handler = logging.StreamHandler(self.log_capture)
        self.handler.setFormatter(JSONFormatter())

        self.logger = logging.getLogger(LOGGER_NAME)
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()
        self.logger.addHandler(self.handler)
        # Keep these records off the root handlers: whether a secret was
        # redacted must not depend on what another test left configured there.
        self.logger.propagate = False

    def teardown_method(self):
        self.logger.handlers.clear()

    def _logged(self):
        """The single emitted record, parsed back out of its JSON form."""
        output = self.log_capture.getvalue().strip()
        assert output, 'nothing was logged'
        lines = output.splitlines()
        # Asserted rather than left to json.loads, which would fail with an
        # opaque JSONDecodeError if a second record ever landed in the buffer.
        assert len(lines) == 1, f'expected one record, got {len(lines)}: {lines}'
        return json.loads(lines[0])

    def test_csrf_token_in_form_data_is_redacted(self):
        log_audit_operation('add_item', 'input',
                            item_id='JA000123',
                            form_data={'ja_id': 'JA1', 'csrf_token': 'abc'},
                            logger_name=LOGGER_NAME)

        form_data = self._logged()['audit_data']['form_data']
        assert form_data == {'ja_id': 'JA1', 'csrf_token': REDACTED_VALUE}

    @pytest.mark.parametrize('field_name', [
        'csrf_token',
        'CSRF_Token',
        'X_CSRFToken',
        'password',
        'PASSWORD',
        'passwd',
        'client_secret',
        'api_key',
        'apikey',
        'Authorization',
        'aws_credentials',
        'private_key',
        'session_id',
    ])
    def test_secret_field_name_variants_are_all_redacted(self, field_name):
        """Case-insensitive substring matching, not exact names."""
        log_audit_operation('add_item', 'input',
                            form_data={field_name: 'super-secret'},
                            logger_name=LOGGER_NAME)

        assert self._logged()['audit_data']['form_data'] == {
            field_name: REDACTED_VALUE}

    @pytest.mark.parametrize('field_name', [
        'ja_id', 'material', 'length', 'notes', 'request_key', 'photo_id',
    ])
    def test_benign_fields_are_logged_verbatim(self, field_name):
        """The audit log exists for reconstruction; `request_key` in particular
        is why the denylist carries `api_key`/`private_key` and not a bare
        `key`."""
        log_audit_operation('add_item', 'input',
                            form_data={field_name: 'real-value'},
                            logger_name=LOGGER_NAME)

        assert self._logged()['audit_data']['form_data'] == {
            field_name: 'real-value'}

    def test_nested_dicts_and_lists_are_redacted_with_structure_preserved(self):
        log_audit_operation('edit_item', 'success',
                            item_after={
                                'meta': {'csrf_token': 'x', 'material': 'Steel'},
                                'rows': [{'token': 'y'}, {'ja_id': 'JA2'}],
                            },
                            logger_name=LOGGER_NAME)

        item_after = self._logged()['audit_data']['item_after']
        assert item_after == {
            'meta': {'csrf_token': REDACTED_VALUE, 'material': 'Steel'},
            'rows': [{'token': REDACTED_VALUE}, {'ja_id': 'JA2'}],
        }

    def test_every_dict_payload_of_log_audit_operation_is_redacted(self):
        """form_data, item_before, item_after and changes — not just the one
        the routes happen to pass today."""
        secret = {'csrf_token': 'abc', 'material': 'Steel'}

        log_audit_operation('edit_item', 'success',
                            item_id='JA000456',
                            form_data=dict(secret),
                            item_before=dict(secret),
                            item_after=dict(secret),
                            changes={'csrf_token': {'before': 'a', 'after': 'b'},
                                     'material': {'before': 'Steel',
                                                  'after': 'Aluminum'}},
                            logger_name=LOGGER_NAME)

        audit_data = self._logged()['audit_data']
        for section in ('form_data', 'item_before', 'item_after'):
            assert audit_data[section] == {'csrf_token': REDACTED_VALUE,
                                           'material': 'Steel'}, section
        assert audit_data['changes'] == {
            'csrf_token': REDACTED_VALUE,
            'material': {'before': 'Steel', 'after': 'Aluminum'},
        }

    def test_callers_dict_is_never_mutated(self):
        """Routes reuse the dict they log — `_render_product_add(form_data, ...)`
        re-renders the very dict handed to the audit helper."""
        form_data = {'ja_id': 'JA1', 'csrf_token': 'abc',
                     'nested': {'token': 'xyz'}}

        log_audit_operation('add_item', 'input',
                            form_data=form_data,
                            logger_name=LOGGER_NAME)

        assert form_data == {'ja_id': 'JA1', 'csrf_token': 'abc',
                             'nested': {'token': 'xyz'}}

    @pytest.mark.parametrize('payload', [None, {}, '', 0])
    def test_falsy_payloads_are_still_dropped(self, payload):
        """Pre-existing behaviour: falsy payloads produce no audit_data section."""
        log_audit_operation('add_item', 'input',
                            form_data=payload,
                            logger_name=LOGGER_NAME)

        assert 'audit_data' not in self._logged()

    @pytest.mark.parametrize('payload', ['a raw string', 42, ['a', 'b']])
    def test_non_dict_payloads_pass_through_without_raising(self, payload):
        log_audit_operation('add_item', 'input',
                            form_data=payload,
                            logger_name=LOGGER_NAME)

        assert self._logged()['audit_data']['form_data'] == payload

    def test_batch_payloads_are_redacted_too(self):
        """`log_audit_batch_operation` hardcodes the `inventory` logger, so the
        capture is pointed at that name for this one case."""
        inventory_logger = logging.getLogger('inventory')
        previous_handlers = inventory_logger.handlers[:]
        previous_level = inventory_logger.level
        inventory_logger.handlers = [self.handler]
        inventory_logger.setLevel(logging.INFO)
        try:
            log_audit_batch_operation(
                'batch_move_items', 'success',
                batch_data={'csrf_token': 'abc',
                            'items': [{'ja_id': 'JA1', 'token': 'x'}]},
                results={'successful_count': 1, 'session_id': 'sid'})
        finally:
            inventory_logger.handlers = previous_handlers
            inventory_logger.setLevel(previous_level)

        audit_data = self._logged()['audit_data']
        assert audit_data['batch_input'] == {
            'csrf_token': REDACTED_VALUE,
            'items': [{'ja_id': 'JA1', 'token': REDACTED_VALUE}],
        }
        assert audit_data['batch_results'] == {'successful_count': 1,
                                               'session_id': REDACTED_VALUE}

    def test_error_details_is_redacted_too(self):
        """Annotated `str`, but nothing enforces that. If a caller ever passes a
        dict, it must not become the one payload that escapes the choke point."""
        log_audit_operation('add_item', 'error',
                            error_details={'csrf_token': 'abc',
                                           'message': 'boom'},
                            logger_name=LOGGER_NAME)

        assert self._logged()['audit_data']['error_details'] == {
            'csrf_token': REDACTED_VALUE, 'message': 'boom'}

    def test_error_details_strings_are_unchanged(self):
        """Every real caller passes `str(e)`; that must survive intact."""
        log_audit_operation('add_item', 'error',
                            error_details='Service update_item returned False',
                            logger_name=LOGGER_NAME)

        assert (self._logged()['audit_data']['error_details']
                == 'Service update_item returned False')

    def test_a_payload_deeper_than_the_walk_fails_closed(self):
        """The depth cap must drop the subtree, not hand it over unfiltered.

        A guard on a security control that returns the raw value once it gives
        up is worse than no guard: it is a documented, predictable bypass.
        """
        deep = {'csrf_token': 'LEAK'}
        for _ in range(MAX_REDACTION_DEPTH + 2):
            deep = {'wrapper': deep}

        log_audit_operation('add_item', 'input',
                            form_data=deep,
                            logger_name=LOGGER_NAME)

        assert 'LEAK' not in self.log_capture.getvalue()

    def test_a_payload_within_the_walk_is_fully_redacted_not_truncated(self):
        """The complement: nesting the app actually produces stays legible."""
        deep = {'csrf_token': 'LEAK', 'material': 'Steel'}
        for _ in range(MAX_REDACTION_DEPTH - 2):
            deep = {'wrapper': deep}

        log_audit_operation('add_item', 'input',
                            form_data=deep,
                            logger_name=LOGGER_NAME)

        output = self.log_capture.getvalue()
        assert 'LEAK' not in output
        assert 'Steel' in output, 'benign data was truncated by the depth guard'

    @pytest.mark.parametrize('depth,benign_survives', [
        (MAX_REDACTION_DEPTH, True),
        (MAX_REDACTION_DEPTH + 1, False),
    ])
    def test_the_depth_cliff_sits_exactly_at_max_redaction_depth(
            self, depth, benign_survives):
        """Pins both sides of the boundary, not just far from it.

        The two tests above sample MAX-2 and MAX+2, which an off-by-one in
        either direction would slip through. The secret must be gone on both
        sides; what changes at the cliff is whether the benign sibling is still
        walked or the whole subtree is dropped.
        """
        deep = {'csrf_token': 'LEAK', 'material': 'Steel'}
        for _ in range(depth):
            deep = {'wrapper': deep}

        log_audit_operation('add_item', 'input',
                            form_data=deep,
                            logger_name=LOGGER_NAME)

        output = self.log_capture.getvalue()
        assert 'LEAK' not in output
        assert ('Steel' in output) is benign_survives


@pytest.mark.unit
class TestRedactionContainerTypes:
    """The walk must not fail *open* on a container it does not recognise.

    `JSONFormatter` serializes with `default=str`, so anything the walk returns
    untouched is `str()`-ed into the record with its secret intact — which is
    why the type check has to be as fail-closed as the depth guard beside it.
    """

    def test_a_mapping_that_is_not_a_dict_is_walked(self):
        """SQLAlchemy's `RowMapping` is exactly this shape."""
        class ReadOnlyMapping(Mapping):
            def __init__(self, data):
                self._data = data

            def __getitem__(self, key):
                return self._data[key]

            def __iter__(self):
                return iter(self._data)

            def __len__(self):
                return len(self._data)

        redacted = _redact_sensitive(
            ReadOnlyMapping({'csrf_token': 'LEAK', 'material': 'Steel'}))

        assert redacted == {'csrf_token': REDACTED_VALUE, 'material': 'Steel'}
        assert 'LEAK' not in json.dumps(redacted, default=str)

    def test_a_multidict_is_walked(self):
        """Nothing stops a caller handing over `request.form` itself rather
        than a `to_dict()` copy — it is a `Mapping`, and the walk must treat it
        as one instead of `str()`-ing the whole thing into the record."""
        redacted = _redact_sensitive(
            ImmutableMultiDict([('csrf_token', 'LEAK'), ('ja_id', 'JA1')]))

        assert redacted == {'csrf_token': REDACTED_VALUE, 'ja_id': 'JA1'}

    @pytest.mark.parametrize('factory,expected', [
        (lambda: deque([{'csrf_token': 'LEAK'}]), [{'csrf_token': REDACTED_VALUE}]),
        (lambda: {'row': {'csrf_token': 'LEAK'}}.values(),
         [{'csrf_token': REDACTED_VALUE}]),
        (lambda: frozenset(['plain']), ['plain']),
    ], ids=['deque', 'dict_values', 'frozenset'])
    def test_a_sequence_that_is_not_a_list_or_tuple_is_walked(
            self, factory, expected):
        """The mirror of the `Mapping` case, and the same fail-open shape.

        `deque`, a `dict_values` view and a `frozenset` are none of
        `list`/`tuple`; recognising containers by concrete type rather than by
        ABC would hand each straight to `default=str` with its nested secret
        intact.
        """
        redacted = _redact_sensitive(factory())

        assert redacted == expected
        assert 'LEAK' not in json.dumps(redacted, default=str)

    def test_a_one_shot_iterator_fails_closed(self):
        """Walking a generator would consume the caller's object, which the
        "never mutate the caller" contract forbids; passing it through would be
        a bypass. Neither is acceptable, so the payload is dropped."""
        payload = (item for item in [{'csrf_token': 'LEAK'}])

        assert _redact_sensitive(payload) == REDACTED_VALUE

    def test_non_string_keys_do_not_bypass_the_denylist(self):
        """A `bytes` or Enum key names the same secret a `str` key would."""
        assert _redact_sensitive({b'csrf_token': 'LEAK'}) == {
            'csrf_token': REDACTED_VALUE}
        assert _is_sensitive_name(b'csrf_token')
        assert not _is_sensitive_name(b'ja_id')

    def test_a_redacted_payload_is_always_json_serializable(self):
        """Redacting the value but keeping an unserializable KEY loses the
        whole record, which is worse than the leak it prevents.

        `json.dumps(..., default=str)` applies to values only: a `bytes` key
        raises `TypeError` out of `JSONFormatter.format`, logging swallows it,
        and nothing at all is emitted. The keys must be coerced too.
        """
        redacted = _redact_sensitive(
            {b'csrf_token': 'LEAK', 'ja_id': 'JA1', 3: 'int key',
             None: 'none key', ('tuple', 'key'): 'tuple key'})

        # Would raise TypeError if any key came back unserializable.
        round_tripped = json.loads(json.dumps(redacted, default=str))
        assert round_tripped['csrf_token'] == REDACTED_VALUE
        assert round_tripped['ja_id'] == 'JA1'
        assert 'LEAK' not in json.dumps(redacted, default=str)

    def test_a_payload_that_raises_never_breaks_the_caller(self):
        """`log_audit_operation` is called from inside request handlers. A walk
        that raises would turn a logging call into a failed request — so the
        payload collapses to the marker instead."""
        class ExplodingMapping(dict):
            def items(self):
                raise RuntimeError('payload blew up mid-walk')

        # Raises unguarded...
        with pytest.raises(RuntimeError):
            _redact_sensitive(ExplodingMapping({'csrf_token': 'LEAK'}))

        # ...but the helper the audit functions actually call fails closed.
        assert _redact_payload(ExplodingMapping({'csrf_token': 'LEAK'})) == \
            REDACTED_VALUE

    def test_a_namedtuple_is_redacted_by_field_name(self):
        """Walked positionally, its named secret would survive."""
        Row = namedtuple('Row', ['ja_id', 'csrf_token'])

        redacted = _redact_sensitive(Row(ja_id='JA1', csrf_token='LEAK'))

        assert redacted == {'ja_id': 'JA1', 'csrf_token': REDACTED_VALUE}

    def test_a_tuple_is_copied_not_coerced_into_a_list(self):
        """The docstring promises a copy; a silent type change is not one."""
        redacted = _redact_sensitive(({'csrf_token': 'LEAK'}, {'ja_id': 'JA1'}))

        assert isinstance(redacted, tuple)
        assert redacted == ({'csrf_token': REDACTED_VALUE}, {'ja_id': 'JA1'})

    def test_strings_and_bytes_are_not_walked_as_sequences(self):
        """Both are `Sequence`s; walking them would shred every audit value."""
        assert _redact_sensitive('Service returned False') == \
            'Service returned False'
        assert _redact_sensitive(b'raw') == b'raw'

    def test_an_arbitrary_object_is_documented_as_a_scalar(self):
        """Pins the deliberate boundary rather than leaving it to be
        rediscovered: the walk does not reflect over `__dict__`, because doing
        so on a logging path risks dragging in ORM instrumentation state. A
        caller with an object must convert it (`_item_to_audit_dict`) first —
        which is what every caller in this app already does."""
        obj = SimpleNamespace(csrf_token='LEAK')

        assert _redact_sensitive(obj) is obj


@pytest.mark.unit
class TestDenylistDoesNotSwallowRealFields:
    """The spec's "Block If": a denylist substring colliding with a real field
    name would silently delete data the audit trail exists to preserve. Checked
    against the actual schema and the actual forms, not against a constant."""

    def test_no_database_column_name_is_redacted(self):
        source = (Path(app_package.__file__).parent / 'database.py').read_text()
        columns = set(re.findall(r'^\s+(\w+)\s*=\s*(?:Column|mapped_column)\(',
                                 source, re.MULTILINE))
        assert columns, 'column scan found nothing; the pattern has rotted'

        swallowed = sorted(c for c in columns if _is_sensitive_name(c))
        assert not swallowed, (
            f'denylist would redact real audit data: {swallowed}')

    def test_csrf_token_is_the_only_redacted_form_field(self):
        templates = Path(app_package.__file__).parent / 'templates'
        fields = set()
        for path in templates.rglob('*.html'):
            # `[^"\']+` rather than `\w+`: a hyphenated field name is a real
            # HTML name, and skipping those would leave the collision check
            # blind to exactly the fields it exists to protect.
            fields.update(re.findall(r'<(?:input|select|textarea)\b[^>]*'
                                     r'(?<![-\w])name\s*=\s*["\']([^"\']+)["\']',
                                     path.read_text(encoding='utf-8'),
                                     re.IGNORECASE))
        assert 'csrf_token' in fields, 'field scan has rotted'

        redacted = sorted(f for f in fields if _is_sensitive_name(f))
        assert redacted == ['csrf_token'], (
            f'denylist redacts form fields beyond the CSRF token: {redacted}')

    def test_denylist_excludes_a_bare_key_substring(self):
        """Guards the deliberate omission: `key` would swallow `request_key`."""
        assert 'key' not in SENSITIVE_FIELD_SUBSTRINGS


@pytest.mark.unit
class TestRedactionThroughARealRoute:
    """Proof the choke point covers real callers, not only direct helper calls.

    `POST /products/add` passes `request.form.to_dict()` verbatim into
    `log_audit_operation` (app/main/routes.py), which is exactly the leak this
    change closes.
    """

    def test_posted_csrf_token_is_redacted_in_the_emitted_record(self, client):
        inventory_logger = logging.getLogger('inventory')
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setFormatter(JSONFormatter())

        previous_handlers = inventory_logger.handlers[:]
        previous_level = inventory_logger.level
        # TestConfig pins LOG_LEVEL='WARNING', so the audit INFO record would
        # otherwise be dropped before it reached any handler.
        inventory_logger.handlers = [handler]
        inventory_logger.setLevel(logging.INFO)
        try:
            client.post('/products/add', data={
                'csrf_token': 'a-real-looking-token',
                'description': 'Widget',
                'manufacturer': 'Acme',
                'mpn': 'W-1',
            })
        finally:
            inventory_logger.handlers = previous_handlers
            inventory_logger.setLevel(previous_level)

        records = [json.loads(line)
                   for line in log_capture.getvalue().splitlines() if line]
        inputs = [r for r in records
                  if r.get('audit_operation') == 'product_add'
                  and r.get('audit_phase') == 'input']
        assert inputs, 'the route emitted no product_add input audit record'

        form_data = inputs[0]['audit_data']['form_data']
        assert form_data['csrf_token'] == REDACTED_VALUE
        # ...and nothing else was touched.
        assert form_data['description'] == 'Widget'
        assert form_data['manufacturer'] == 'Acme'
        assert form_data['mpn'] == 'W-1'
        assert 'a-real-looking-token' not in log_capture.getvalue()
