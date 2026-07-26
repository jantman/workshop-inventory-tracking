"""Transport-level request body limit (app/request_limits.py).

**Read this before adding or changing a test here.** Five consecutive
implementations of this feature were reverted, and *four* of them shipped a
fully green suite that was **structurally incapable** of seeing the defect:

* The Flask test client never sets `wsgi.input_terminated`. Gunicorn — the
  server named in `wsgi.py` and `app.py` — sets it on **every** request,
  including every `GET`. An implementation that keyed on that flag returned 411
  for every request in production while the suite stayed green.
* A shared helper that injected `Transfer-Encoding: chunked` into every request
  turned a "without the flag" test into a duplicate of the "with the flag" one,
  and the untested limb was where the bug lived.
* 139 tests asserted `status_code == 413` on exactly the undeclared-length and
  chunked rows — and the defect was that those rows returned a correct 413
  *after* 64 MiB of a 64 MiB body was resident against a 1 MiB cap. A status
  code cannot see a memory bound.
* The iteration that fixed *that* asserted `largest_read_requested <= cap + 1`,
  which **declares the one-giant-read shape correct** — and every test stream
  here manufactures only `min(size, remaining)` bytes, so no test in the module
  was capable of observing an over-allocation at all. The real defect was that
  `io.BufferedReader.read(n)` allocates `n` up front: a 7-byte multipart POST
  peaked at 24.03 MiB against the 24 MiB upload cap, on every request, behind a
  green suite.

Hence the four hard rules here:

1. **Every test applies `environ_overrides` at its own call site.** No helper
   sets the flag, the method, or any header. `_oversize_body` returns bytes and
   nothing else; `_generating_stream` returns a stream and nothing else.
2. **Every test name states what it asserts**, including whether a header is
   present or absent, and asserts exactly that.
3. **Every oversize row asserts a bound on BYTES READ, not only the status.**
   Those rows drive an instrumented `wsgi.input` that *generates* its bytes on
   demand (`_GeneratingStream`) and records the size of every read it is asked
   for, and assert through `_assert_body_bytes_were_bounded` that neither the
   total nor any single read exceeds its bound — end-to-end through the real
   app, not only as a unit test of `CappedStream`. A status-only assertion on an
   oversize row is the thing this module exists to forbid.
4. **Each INDIVIDUAL read is asserted against a small constant, never against
   the cap.** `<= cap + 1` is not a bound on anything that matters; it is the
   defect written down as an assertion. And because a stream that manufactures
   `min(size, remaining)` bytes physically cannot over-allocate, at least one
   test drives a real `io.BufferedReader` — which allocates what it is *asked*
   for, before it knows what exists — and measures with `tracemalloc`. See
   `TestTinyBodyDoesNotAllocateTheCap`.

Limits are read from `app.config`, never hardcoded: `.env.example` invites a
deployer to set both variables, and a suite that hardcodes 1048576 turns red on
their machine for no reason. The shipped *defaults* are pinned separately, in
`TestDocumentedDefaults`, from the source rather than from a live config.
"""

import ast
import inspect
import io
import json
import logging
import os
import subprocess
import sys
import textwrap
import tracemalloc
from pathlib import Path
from unittest import mock

import pytest
from werkzeug.exceptions import RequestEntityTooLarge

import config as config_module
from app import create_app
from app.error_handlers import (CATALOG_JSON_ENDPOINTS,
                                JSON_HTML_HYBRID_ENDPOINTS, LOGGED_PATH_CHARS,
                                LOG_TRUNCATION_MARKER,
                                REQUEST_TOO_LARGE_MESSAGE)
# `config`, not `app.exceptions`: config.py owns the leaf definition so that it
# stays importable without executing app/__init__.py, and the app-side class
# subclasses it -- so this name catches configuration failures raised on either
# side of that line. TestExceptionHierarchy pins the relationship.
from config import ConfigurationError
from app.request_limits import (BodyLimitMiddleware, CappedStream,
                                MAX_SANE_LIMIT_BYTES, UPLOAD_ENDPOINTS,
                                UPLOAD_MIMETYPE, _LARGEST_SERVICE_FILE_LIMIT,
                                is_multipart, validate_limits)
from tests.test_config import TestConfig

REPO_ROOT = Path(__file__).resolve().parents[2]

# The two source files carrying blueprint views, and the blueprint each one
# registers under. Both are scanned by the structural pins: an upload or catalog
# route added to the admin blueprint must not slip past a guard that only ever
# looked at app/main/routes.py.
VIEW_MODULES = {
    'app/main/routes.py': 'main',
    'app/admin/routes.py': 'admin',
}

# The literal 413 sentence a client renders. Asserted against this constant AND
# against a hand-written literal (test_message_constant_is_the_shipped_sentence),
# so an accidental edit to the constant cannot silently rewrite what five JS
# clients display.
_EXPECTED_413_SENTENCE = (
    'The submitted data was too large to accept. Try again with a smaller file, '
    'less text in a single field, or fewer items at once.'
)

# Gunicorn sets this on every request. Written out at each call site rather than
# hidden in a helper; see the module docstring.
_TERMINATED = {'wsgi.input_terminated': True}

# How many times the cap an oversize generating body is willing to produce. The
# reverted iteration was measured at exactly this multiple: a 64 MiB body
# against the 1 MiB cap, all of it resident, behind a green `== 413`.
_OVERSIZE_MULTIPLE = 64


def _json_log_warnings(captured):
    """WARNING-or-worse messages emitted through the JSON pipeline that
    `setup_logging` installs, read off the captured streams.

    `caplog` cannot be used for anything emitted during `create_app`:
    `setup_logging` removes every handler from the root logger, pytest's
    capturing handler included.
    """
    messages = []
    for stream in (captured.out, captured.err):
        for line in stream.splitlines():
            if not line.startswith('{'):
                continue
            try:
                record = json.loads(line)
            except ValueError:       # pragma: no cover - not a log line
                continue
            if record.get('level') in ('WARNING', 'ERROR', 'CRITICAL'):
                messages.append(record.get('message', ''))
    return messages


def _oversize_body(app, over='MAX_REQUEST_BODY_BYTES'):
    """Bytes comfortably past `app.config[over]`. Adds NO headers and NO environ
    keys -- the transport shape is always the calling test's own business."""
    return b'a' * (app.config[over] + 4096)


def _under_limit_scan_body(app):
    """A valid `/api/scan` payload padded to roughly half the global limit."""
    return json.dumps({'raw': '0123',
                       'pad': 'x' * (app.config['MAX_REQUEST_BODY_BYTES'] // 2)}).encode()


class _GeneratingStream:
    """A `wsgi.input` that MANUFACTURES its bytes on demand and records the size
    of every read it is asked for.

    Both properties are the point of the class:

    1. **It never allocates the whole body.** Proving that a 64 MiB body does
       not become 64 MiB of resident memory must not itself cost 64 MiB -- and,
       more importantly, a test that pre-allocates the body cannot tell
       "the app read 1 MiB" from "the app read all of it", because the bytes
       were already there either way.
    2. **It records what was ASKED for**, not only what came back. The reverted
       iteration's defect was a single `read(-1)`: the response was a correct
       413, the status assertion passed, and 64 MiB was resident. Only the
       requested size shows that.

    Deliberately newline-free, so `readline` has to face one enormous "line".
    """

    def __init__(self, size, fill=b'a'):
        self.size = size
        self._remaining = size
        self._fill = fill
        self.requested = []     # the `size` argument of every read call
        self.returned = []      # how many bytes each call actually produced

    def _take(self, size):
        self.requested.append(size)
        wanted = (self._remaining if size is None or size < 0
                  else min(size, self._remaining))
        self._remaining -= wanted
        self.returned.append(wanted)
        return self._fill * wanted

    def read(self, size=-1):
        return self._take(size)

    def readline(self, size=-1):
        return self._take(size)

    def readlines(self, hint=-1):
        line = self.readline()
        return [line] if line else []

    def __iter__(self):
        while True:
            line = self.readline()
            if not line:
                return
            yield line

    @property
    def largest_read_requested(self):
        """The largest number of bytes any one call asked this stream for.

        An unsized read (`-1` / `None`) counts as the WHOLE remaining body,
        because that is exactly what it would have returned -- which is the
        defect being guarded against, and it must not be able to score zero.
        """
        if not self.requested:
            return 0
        return max(self.size if size is None or size < 0 else size
                   for size in self.requested)

    @property
    def bytes_generated(self):
        return sum(self.returned)


def _generating_stream(app, over='MAX_REQUEST_BODY_BYTES',
                       multiple=_OVERSIZE_MULTIPLE):
    """A stream willing to produce `multiple` x the named cap.

    Adds NO headers and NO environ keys: as with `_oversize_body`, the transport
    shape is always the calling test's own business (see the module docstring).
    """
    return _GeneratingStream(app.config[over] * multiple)


# The bound on each INDIVIDUAL read, read from the implementation so the two
# cannot drift. `TestPerReadBoundIsASmallConstant` pins that it really is small
# and really is independent of the configured caps -- because the whole point is
# that this number does NOT scale with the cap.
_MAX_SINGLE_READ = CappedStream._CHUNK


def _assert_body_bytes_were_bounded(stream, cap):
    """Assert both bounds this feature exists to provide.

    `status_code == 413` says the RESPONSE was right. It says nothing about
    whether the body was resident first -- the measured iteration-5 defect
    returned a textbook-correct 413 with 64 MiB in memory, behind 139 green
    tests that asserted only the status. So every oversize row asserts this too.

    TWO bounds, and the second is not a refinement of the first:

    * TOTAL bytes pulled <= the allowance. Bounds the attacker's leverage.
    * EACH INDIVIDUAL read <= `_MAX_SINGLE_READ`, a small CONSTANT. Bounds what
      the wrapped stream is asked to allocate. `io.BufferedReader.read(n)`
      allocates `n` before it knows how much data exists, so a single read of
      the whole remaining allowance costs the entire configured cap on every
      request, however small the body. The previous iteration asserted
      `largest_read_requested <= cap + 1` here, which is that defect stated as
      a passing test. Never compare a per-read size against the cap.
    """
    assert stream.requested, (
        'the body was never read at all, so this assertion proves nothing; '
        'the test is not exercising the path it names')
    assert stream.largest_read_requested <= _MAX_SINGLE_READ, (
        f'a single read asked the transport for {stream.largest_read_requested} '
        f'bytes; no individual read may exceed {_MAX_SINGLE_READ}. Asking for '
        f'the remaining allowance ({cap}) in one call makes every request cost '
        'the whole cap, because a buffered stream allocates what it is asked '
        'for before it looks at the data')
    assert stream.bytes_generated <= cap + 1, (
        f'{stream.bytes_generated} bytes were pulled through a cap of {cap}')


@pytest.mark.unit
class TestTransportMatrix:
    """The required cross-product of method x `wsgi.input_terminated` x
    length-shape. Every rejection here is a 413; there is no 411 rule."""

    # ---- GET / HEAD / OPTIONS: the iteration-3 outage ----------------------

    def test_get_index_is_identical_with_and_without_input_terminated(self, client):
        """The whole reason iteration 3 was reverted: with the flag set, `GET
        /index` 302'd to itself forever, on every page and every health check."""
        plain = client.get('/index')
        terminated = client.get('/index', environ_overrides=dict(_TERMINATED))
        assert plain.status_code == 200
        assert terminated.status_code == plain.status_code
        assert terminated.headers.get('Location') == plain.headers.get('Location')
        assert terminated.data == plain.data

    def test_get_root_is_identical_with_and_without_input_terminated(self, client):
        plain = client.get('/')
        terminated = client.get('/', environ_overrides=dict(_TERMINATED))
        assert plain.status_code == 200
        assert terminated.status_code == plain.status_code
        assert terminated.headers.get('Location') is None
        assert terminated.data == plain.data

    def test_head_root_is_identical_with_and_without_input_terminated(self, client):
        plain = client.head('/')
        terminated = client.head('/', environ_overrides=dict(_TERMINATED))
        assert plain.status_code == 200
        assert terminated.status_code == plain.status_code
        assert terminated.headers.get('Location') is None

    def test_options_root_is_identical_with_and_without_input_terminated(self, client):
        plain = client.open('/', method='OPTIONS')
        terminated = client.open('/', method='OPTIONS',
                                 environ_overrides=dict(_TERMINATED))
        assert plain.status_code == 200
        assert terminated.status_code == plain.status_code
        assert terminated.headers.get('Location') is None

    def test_get_root_with_input_terminated_yields_no_body_bytes(self, client):
        """A bodyless GET is NOT exempted from the forced read -- exempting it
        would mean predicting again, which is what this design exists to stop.
        One read is issued and returns nothing, so the cap is never approached.

        Asserted on bytes RETURNED and on the sizes REQUESTED, separately. An
        earlier version of this test recorded `len(chunk)` over an empty stream
        and asserted the sum was zero -- which is true however many reads are
        issued and however large, so it could not fail. It also documented
        "zero bytes are read ... by construction", which is not what happens:
        a `read(65536)` IS issued. The instrument must record what was ASKED
        for, not only what came back.
        """
        source = _GeneratingStream(0)
        resp = client.get('/', environ_overrides={
            'CONTENT_LENGTH': None,
            'wsgi.input': source,
            **_TERMINATED,
        })
        assert resp.status_code == 200
        assert source.bytes_generated == 0
        # Whatever is asked for, it must stay within the per-read constant --
        # never the cap.
        assert all(size <= _MAX_SINGLE_READ for size in source.requested), \
            source.requested

    # ---- bodyless / under-limit POSTs remain untouched ---------------------

    def test_bodyless_post_to_api_scan_is_the_existing_400_without_the_flag(self, client):
        assert client.post('/api/scan').status_code == 400

    def test_bodyless_post_to_api_scan_is_the_existing_400_with_input_terminated(
            self, client):
        assert client.post('/api/scan',
                           environ_overrides=dict(_TERMINATED)).status_code == 400

    def test_post_with_content_length_under_the_limit_is_served_without_the_flag(
            self, client, app):
        resp = client.post('/api/scan', data=_under_limit_scan_body(app),
                           content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['raw'] == '0123'

    def test_post_with_content_length_under_the_limit_is_served_with_input_terminated(
            self, client, app):
        resp = client.post('/api/scan', data=_under_limit_scan_body(app),
                           content_type='application/json',
                           environ_overrides=dict(_TERMINATED))
        assert resp.status_code == 200
        assert resp.get_json()['raw'] == '0123'

    def test_transfer_encoding_gzip_with_a_valid_under_limit_length_is_served(
            self, client, app):
        """`Transfer-Encoding` is not `Transfer-Encoding: chunked`. An earlier
        iteration tested the header by presence and 411'd a perfectly
        enforceable gzip request."""
        resp = client.post('/api/scan', data=_under_limit_scan_body(app),
                           content_type='application/json',
                           headers={'Transfer-Encoding': 'gzip'},
                           environ_overrides=dict(_TERMINATED))
        assert resp.status_code == 200
        assert resp.get_json()['raw'] == '0123'

    # ---- oversize bodies ---------------------------------------------------
    #
    # EVERY row below asserts a bound on BYTES READ as well as the status code.
    # A 413 says the response was right; it says nothing about whether the body
    # was resident first, and the measured iteration-5 defect was precisely a
    # correct 413 with 64 MiB in memory. Each drives an instrumented stream that
    # GENERATES its bytes on demand (`_GeneratingStream`), so an unclamped read
    # is visible rather than free.

    def test_post_with_content_length_over_the_limit_is_413_without_the_flag(
            self, client, app):
        stream = _generating_stream(app)
        resp = client.post('/api/scan', content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': str(stream.size),
                                              'wsgi.input': stream})
        assert resp.status_code == 413
        # The declared-length fast path rejects before a single byte is read,
        # which is stronger than the clamp and is why it exists.
        assert stream.requested == []

    def test_post_with_content_length_over_the_limit_is_413_with_input_terminated(
            self, client, app):
        stream = _generating_stream(app)
        resp = client.post('/api/scan', content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': str(stream.size),
                                              'wsgi.input': stream,
                                              **_TERMINATED})
        assert resp.status_code == 413
        assert stream.requested == []

    def test_chunked_oversize_body_with_no_length_is_never_read_without_the_flag(
            self, client, app):
        """See `TestWerkzeugSafeFallbackWithoutInputTerminated`: with no
        `wsgi.input_terminated` and no usable length, Werkzeug substitutes an
        empty `BytesIO` and the body is never read. Not a 413, and not a bypass
        -- nothing oversize reaches the view. No real server produces this shape
        for a chunked request anyway: gunicorn sets the flag on every request
        and Werkzeug's own dev server sets it precisely for chunked."""
        resp = client.post('/api/scan', data=_oversize_body(app),
                           content_type='application/json',
                           headers={'Transfer-Encoding': 'chunked'},
                           environ_overrides={'CONTENT_LENGTH': None})
        assert resp.status_code == 400
        assert resp.get_json()['error']['field'] == 'raw'

    def test_chunked_oversize_body_with_no_length_is_413_and_bounded_with_input_terminated(
            self, client, app):
        """Chunked is one of the two shapes the declared-length fast path cannot
        cover, so the clamp is the ONLY thing bounding memory here."""
        stream = _generating_stream(app)
        resp = client.post('/api/scan', content_type='application/json',
                           headers={'Transfer-Encoding': 'chunked'},
                           environ_overrides={'CONTENT_LENGTH': None,
                                              'wsgi.input': stream,
                                              **_TERMINATED})
        assert resp.status_code == 413
        _assert_body_bytes_were_bounded(stream, app.config['MAX_REQUEST_BODY_BYTES'])

    @pytest.mark.parametrize('bad_length', ['+50', '1_0'])
    def test_malformed_content_length_with_an_oversize_body_is_413_with_input_terminated(
            self, client, app, bad_length):
        """`+50` and `1_0` are accepted by `int()` and REJECTED by Werkzeug's
        `_plain_int`, which then reports a length of 0. Under this design that
        disagreement is not a bypass: the length simply fails the hook's fast
        path and the cap still applies -- and bounds the memory while doing it."""
        stream = _generating_stream(app)
        resp = client.post('/api/scan', content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': bad_length,
                                              'wsgi.input': stream,
                                              **_TERMINATED})
        assert resp.status_code == 413
        _assert_body_bytes_were_bounded(stream, app.config['MAX_REQUEST_BODY_BYTES'])

    @pytest.mark.parametrize('bad_length', ['+50', '1_0'])
    def test_malformed_content_length_with_an_oversize_body_is_never_read_without_the_flag(
            self, client, app, bad_length):
        """Werkzeug reports an unparseable length as 0 and, with no
        `wsgi.input_terminated`, wraps the stream in `LimitedStream(stream, 0)`
        -- so no byte of the oversize body is read. See
        `TestWerkzeugSafeFallbackWithoutInputTerminated`."""
        resp = client.post('/api/scan', data=_oversize_body(app),
                           content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': bad_length})
        assert resp.status_code == 400
        assert resp.get_json()['error']['field'] == 'raw'

    def test_non_str_content_length_in_the_environ_is_413_not_an_attribute_error(
            self, client, app):
        """The declared length is a small *int*, under the cap, so the hook's
        fast path does not fire and Werkzeug's own `get_content_length` is what
        reads it. Without the environ normalisation in `BodyLimitMiddleware`,
        `_plain_int` calls `.strip()` on an int and the request is a 500 raised
        from inside Werkzeug."""
        stream = _generating_stream(app)
        resp = client.post('/api/scan', content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': 10,
                                              'wsgi.input': stream,
                                              **_TERMINATED})
        assert resp.status_code == 413
        _assert_body_bytes_were_bounded(stream, app.config['MAX_REQUEST_BODY_BYTES'])

    def test_non_str_content_length_in_the_environ_is_not_a_500_without_the_flag(
            self, client, app):
        """Same environ repair, other transport column: the normalisation is
        what keeps this out of Werkzeug's unguarded `.strip()`. Here the
        declared 10 bytes bound the read, so the request is served as a short
        one rather than rejected -- what matters is that it is not a 5xx."""
        resp = client.post('/api/scan', data=_oversize_body(app),
                           content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': 10})
        assert resp.status_code == 400
        assert resp.status_code < 500

    def test_content_length_of_5000_digits_with_an_oversize_body_is_413_not_500(
            self, client, app):
        """CPython caps integer-string conversion at 4300 digits, so `int()` on
        this value raises `ValueError`. An earlier iteration let that escape
        `before_request`, handing any unauthenticated caller a one-header remote
        500 on every route in the app."""
        stream = _generating_stream(app)
        resp = client.post('/api/scan', content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': '9' * 5000,
                                              'wsgi.input': stream,
                                              **_TERMINATED})
        assert resp.status_code == 413
        _assert_body_bytes_were_bounded(stream, app.config['MAX_REQUEST_BODY_BYTES'])

    def test_non_str_content_type_in_the_environ_is_413_not_an_attribute_error(
            self, client, app):
        """`werkzeug.http.parse_options_header` calls `.partition()` unguarded,
        so a non-`str` CONTENT_TYPE is `AttributeError: 'int' object has no
        attribute 'partition'` raised from inside Werkzeug -- measured as a 500.
        Like the CONTENT_LENGTH case it is repairable only by normalising the
        environ before Werkzeug reads it, and the forced
        `get_data(parse_form_data=True)` puts every route in its blast radius."""
        stream = _generating_stream(app)
        resp = client.post('/api/scan',
                           environ_overrides={'CONTENT_TYPE': 12345,
                                              'CONTENT_LENGTH': None,
                                              'wsgi.input': stream,
                                              **_TERMINATED})
        assert resp.status_code == 413
        _assert_body_bytes_were_bounded(stream, app.config['MAX_REQUEST_BODY_BYTES'])

    def test_non_str_content_type_on_an_under_limit_body_is_served_not_a_500(
            self, client, app):
        """The other half of the same repair: a small body with a nonsense
        environ content type must reach the app as an ordinary request."""
        resp = client.post('/api/scan', data=json.dumps({'raw': '0123'}).encode(),
                           environ_overrides={'CONTENT_TYPE': 12345, **_TERMINATED})
        assert resp.status_code < 500

    def test_content_length_of_5000_digits_is_never_a_500_without_the_flag(
            self, client, app):
        resp = client.post('/api/scan', data=_oversize_body(app),
                           content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': '9' * 5000})
        assert resp.status_code == 400
        assert resp.status_code < 500

    # ---- the bold row: no declared length at all ---------------------------

    @pytest.mark.parametrize('absent_length', [None, '', '   '],
                             ids=['absent', 'empty', 'whitespace'])
    def test_oversize_body_with_no_usable_length_is_413_and_bounded_with_input_terminated(
            self, client, app, absent_length):
        """**The row both revert-causing defects lived on.**

        Iteration 4: with the flag set and no usable `Content-Length`, the view
        got exactly `limit` bytes of a longer body and a 200.

        Iteration 5: it became a correct 413 -- after the whole 64 MiB body had
        been pulled into memory by a single unclamped `read(-1)`, because
        `Request.get_data()` issues exactly that and nothing declared a length
        to reject on. Hence the byte-bound assertion; the status alone was green
        throughout.
        """
        stream = _generating_stream(app)
        resp = client.post('/api/scan', content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': absent_length,
                                              'wsgi.input': stream,
                                              **_TERMINATED})
        assert resp.status_code == 413
        _assert_body_bytes_were_bounded(stream, app.config['MAX_REQUEST_BODY_BYTES'])

    @pytest.mark.parametrize('absent_length', [None, '', '   '],
                             ids=['absent', 'empty', 'whitespace'])
    def test_oversize_body_with_no_usable_length_reads_zero_bytes_without_the_flag(
            self, client, app, absent_length):
        """Without `wsgi.input_terminated` and with no length, Werkzeug returns
        an empty `BytesIO` rather than the real stream, so no body is read at
        all -- the request is served as the bodyless POST it looks like. This is
        Werkzeug's own safe fallback, recorded here so a future reader does not
        mistake the 400 for a defect."""
        resp = client.post('/api/scan', data=_oversize_body(app),
                           content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': absent_length})
        assert resp.status_code == 400
        assert resp.get_json()['error']['field'] == 'raw'


@pytest.mark.unit
class TestWerkzeugSafeFallbackWithoutInputTerminated:
    """Why several "without the flag" rows above are a served 400 rather than a
    413, pinned against the installed Werkzeug rather than asserted in prose.

    `werkzeug.wsgi.get_input_stream` only reaches the real stream without
    `wsgi.input_terminated` when it has a usable `Content-Length`. With no
    usable length it substitutes `io.BytesIO()`; with an unparseable one
    `get_content_length` reports `0` and it wraps the stream in
    `LimitedStream(stream, 0)`. Either way **no oversize body is read**, which
    is why those rows are safe without being rejections.

    This shape barely exists in production: gunicorn and waitress set the flag
    on every request, and Werkzeug's dev server sets it for chunked. If a future
    Werkzeug drops the safe fallback, these tests turn red and point straight at
    the rows that depend on it.
    """

    def test_unparseable_content_length_is_reported_as_zero(self):
        from werkzeug.sansio.utils import get_content_length
        assert get_content_length('+50', None) == 0
        assert get_content_length('1_0', None) == 0
        assert get_content_length('9' * 5000, None) == 0

    def test_chunked_transfer_encoding_is_reported_as_no_length(self):
        from werkzeug.sansio.utils import get_content_length
        assert get_content_length(None, 'chunked') is None
        # ...but a non-chunked Transfer-Encoding leaves the length alone.
        assert get_content_length('42', 'gzip') == 42

    def test_unknown_length_without_the_flag_yields_an_empty_stream(self):
        from werkzeug.wsgi import get_input_stream
        environ = {'wsgi.input': io.BytesIO(b'x' * 5000)}
        assert get_input_stream(environ).read() == b''

    def test_unknown_length_with_the_flag_yields_the_raw_stream_when_no_max_is_set(self):
        """The branch the whole design rests on: with `max_content_length`
        `None`, the stream this middleware installed is returned untouched, so
        the cap is authoritative."""
        from werkzeug.wsgi import get_input_stream
        stream = CappedStream(io.BytesIO(b'x' * 5000), 10)
        environ = {'wsgi.input': stream, 'wsgi.input_terminated': True}
        assert get_input_stream(environ, max_content_length=None) is stream

    def test_unknown_length_with_the_flag_and_a_max_yields_the_truncating_limiter(self):
        """And the branch that must never be armed: `LimitedStream(...,
        is_max=True)` stops at the limit instead of raising."""
        from werkzeug.wsgi import get_input_stream, LimitedStream
        environ = {'wsgi.input': io.BytesIO(b'x' * 5000), 'wsgi.input_terminated': True}
        wrapped = get_input_stream(environ, max_content_length=10)
        assert isinstance(wrapped, LimitedStream)
        assert wrapped.read() == b'x' * 10          # truncated, not raised


class _RecordingStream(io.BytesIO):
    """A `wsgi.input` that records the size of every read, for the zero-bytes
    assertions above."""

    def __init__(self, data, sizes):
        super().__init__(data)
        self._sizes = sizes

    def read(self, size=-1):
        chunk = super().read(size)
        self._sizes.append(len(chunk))
        return chunk


@pytest.mark.unit
class TestMaxContentLengthInvariant:
    """`app.config['MAX_CONTENT_LENGTH']` must stay `None`.

    This is the single counterintuitive invariant of the design, so it gets two
    tests: one asserting it, and one *demonstrating* the regression that setting
    it causes. The assertion alone reads like a tidy-up and invites deletion.
    """

    def test_create_app_leaves_max_content_length_none(self, app):
        """Setting this key makes `werkzeug.wsgi.get_input_stream` return
        `LimitedStream(..., is_max=True)` on a terminated stream -- which
        TRUNCATES at the limit instead of raising, handing the view a partial
        body with a 200."""
        assert app.config['MAX_CONTENT_LENGTH'] is None

    def test_no_module_in_the_app_mentions_flasks_body_limit_key_outside_the_warning(self):
        """`grep -rn MAX_CONTENT_LENGTH config.py app/` must find the explanatory
        comment in `app/request_limits.py` and nothing else. A hit anywhere else
        is either an assignment (the regression) or a second, drifting copy of
        the explanation."""
        key = 'MAX_CONTENT' + '_LENGTH'   # split so this line is not itself a hit
        offenders = []
        for path in [REPO_ROOT / 'config.py'] + sorted(
                (REPO_ROOT / 'app').rglob('*.py')):
            if path.name == 'request_limits.py':
                continue
            if key in path.read_text():
                offenders.append(str(path.relative_to(REPO_ROOT)))
        assert offenders == []

    def test_max_content_length_left_none_makes_an_undeclared_oversize_body_413(
            self, test_storage):
        """Control for the test below: same app, same request, key left `None`."""
        app = _app_with_body_size_probe(test_storage)
        assert app.config['MAX_CONTENT_LENGTH'] is None
        resp = app.test_client().post(
            '/__body_size__', data=_oversize_body(app),
            environ_overrides={'CONTENT_LENGTH': None, **_TERMINATED})
        assert resp.status_code == 413

    def test_setting_max_content_length_returns_200_carrying_exactly_limit_bytes(
            self, test_storage):
        """The iteration-4 defect, reproduced on demand. If a future reader
        "notices" that Flask has a built-in body limit and wires it up, this
        test turns red and says exactly what breaks."""
        app = _app_with_body_size_probe(test_storage)
        limit = app.config['MAX_REQUEST_BODY_BYTES']
        app.config['MAX_CONTENT_LENGTH'] = limit

        resp = app.test_client().post(
            '/__body_size__', data=_oversize_body(app),
            environ_overrides={'CONTENT_LENGTH': None, **_TERMINATED})

        assert resp.status_code == 200
        assert resp.get_json()['size'] == limit


def _app_with_body_size_probe(test_storage):
    """An app carrying one extra route that reports how many body bytes the
    view actually received."""
    from flask import jsonify, request

    app = create_app(TestConfig, storage_backend=test_storage)

    @app.route('/__body_size__', methods=['POST'])
    def _body_size():
        return jsonify({'size': len(request.get_data())})

    return app


@pytest.mark.unit
class TestEnforcementPointIsAheadOfEveryView:
    """The bound must be imposed before any view runs.

    Most JSON views in this app read the body inside a `try` whose tail is
    `except Exception: return 500`. A 413 raised lazily inside such a view is
    caught and downgraded -- measured on an earlier iteration as a 500 that then
    died with `UnboundLocalError`.
    """

    # Every JSON route named in the acceptance criteria whose view wraps its
    # body read in a broad `except Exception`.
    CATCH_ALL_ROUTES = [
        '/api/inventory/batch-move',
        '/api/inventory/search',
        '/api/validate/type-shape',
        '/api/labels/print',
        '/api/photos/copy',
        '/api/items/JA000001/duplicate',
        '/admin/api/materials/validate',
    ]

    @pytest.mark.parametrize('path', CATCH_ALL_ROUTES)
    def test_declared_oversize_body_is_413_on_every_catch_all_json_route(
            self, client, app, path):
        resp = client.post(path, data=_oversize_body(app),
                           content_type='application/json')
        assert resp.status_code == 413
        assert b'Werkzeug' not in resp.data

    @pytest.mark.parametrize('path', CATCH_ALL_ROUTES)
    def test_undeclared_oversize_body_is_413_and_bounded_on_every_catch_all_json_route(
            self, client, app, path):
        """Without the forced `request.get_data(...)` in `before_request` this
        is a 500: the cap raises inside the view, where the catch-all eats it.

        These are the routes the clamp matters most on. Every one of them is a
        JSON route, so `get_data()` issues `read(-1)`, and an attacker reaches
        this row simply by omitting `Content-Length` -- the same "one header
        undoes the fix" shape that caused three earlier reverts."""
        stream = _generating_stream(app)
        resp = client.post(path, content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': None,
                                              'wsgi.input': stream,
                                              **_TERMINATED})
        assert resp.status_code == 413
        assert b'Werkzeug' not in resp.data
        _assert_body_bytes_were_bounded(stream, app.config['MAX_REQUEST_BODY_BYTES'])

    def test_declared_over_limit_length_is_rejected_before_a_single_byte_is_read(
            self, client, app, monkeypatch):
        """The eager `raise` in `before_request` is the fast path every real
        client takes. Delete it and the request is still rejected -- but only
        after the whole oversize body has been pulled through the cap, which is
        the cost the fast path exists to avoid."""
        reads = []
        original = CappedStream.read

        def _spy(self, size=-1):
            reads.append(size)
            return original(self, size)

        monkeypatch.setattr(CappedStream, 'read', _spy)

        resp = client.post('/api/scan', data=_oversize_body(app),
                           content_type='application/json')
        assert resp.status_code == 413
        assert reads == []

    def test_oversize_form_field_under_the_body_limit_is_413_not_a_leaked_500(
            self, client, app):
        """Flask's untouched 500 KB `MAX_FORM_MEMORY_SIZE` raises the same
        `RequestEntityTooLarge`, lazily, from inside the parser. Without
        `parse_form_data=True` in the hook that lands inside `upload_photo`'s
        catch-all as a 500 leaking raw Werkzeug text."""
        field_size = app.config['MAX_FORM_MEMORY_SIZE'] + 100_000
        assert field_size < app.config['MAX_UPLOAD_BODY_BYTES']

        resp = client.post(
            '/api/items/JA000001/photos',
            data={'notes': 'x' * field_size,
                  'file': (io.BytesIO(b'\xff\xd8\xff'), 'tiny.jpg')},
            content_type='multipart/form-data')

        assert resp.status_code == 413
        assert resp.get_json()['error'] == _EXPECTED_413_SENTENCE

    def test_a_urlencoded_body_between_the_form_and_body_limits_is_413_WITH_a_declared_length(
            self, client, app):
        """The documented boundary, executed -- in the column where it holds.

        Flask's untouched 500 KB `MAX_FORM_MEMORY_SIZE` -- not
        `MAX_REQUEST_BODY_BYTES` -- is the real ceiling for a urlencoded body,
        and it is LOWER than the 1 MiB default, so a 600 KB form POST is a 413
        and raising `MAX_REQUEST_BODY_BYTES` does not move it.

        The test name says `WITH a declared length` because that is a real
        precondition, not a detail:
        `test_..._is_NOT_a_413_without_a_declared_length` below is the other
        column, and it does not behave the same way.
        """
        assert app.config['MAX_FORM_MEMORY_SIZE'] < app.config['MAX_REQUEST_BODY_BYTES']
        size = app.config['MAX_FORM_MEMORY_SIZE'] + 100_000
        assert size < app.config['MAX_REQUEST_BODY_BYTES']

        resp = client.post('/admin/api/materials/validate',
                           data={'note': 'x' * size},
                           content_type='application/x-www-form-urlencoded')
        assert resp.status_code == 413

    def test_the_same_urlencoded_body_is_NOT_a_413_without_a_declared_length(
            self, client, app):
        """The gunicorn column, which the reverted iteration documented wrongly
        and never tested.

        `werkzeug.formparser.FormDataParser._parse_urlencoded` applies
        `max_form_memory_size` only when `content_length is not None`. On the
        exact transport this feature is built around -- `wsgi.input_terminated`
        set, no `Content-Length` -- the same 600 KB field is therefore NOT
        rejected by the form limit at all (measured: 400, the field simply does
        not parse). Both `.env` templates now scope the claim to the declared
        column and say what governs this one instead; this test is why they can.

        This is not a hole: `MAX_REQUEST_BODY_BYTES` still bounds the body, as
        `test_a_urlencoded_body_over_the_transport_cap_is_413_in_BOTH_columns`
        shows. It is only the *form-field* limit that is column-dependent.
        """
        size = app.config['MAX_FORM_MEMORY_SIZE'] + 100_000
        assert size < app.config['MAX_REQUEST_BODY_BYTES']

        # An HTML form route rather than one of the catch-all JSON routes: those
        # answer an unparsed body with their own 500, which would mask the one
        # thing this test is about.
        resp = client.post('/inventory/add',
                           data=b'note=' + b'x' * size,
                           content_type='application/x-www-form-urlencoded',
                           environ_overrides={'CONTENT_LENGTH': None,
                                              **_TERMINATED})
        assert resp.status_code != 413, (
            'if this is now a 413, Werkzeug changed its behaviour and both '
            '.env templates can drop the conditional wording')
        assert resp.status_code < 500

        # Control, same route and same body, WITH a declared length.
        declared = client.post('/inventory/add',
                               data=b'note=' + b'x' * size,
                               content_type='application/x-www-form-urlencoded')
        assert declared.status_code == 413, (
            'the two columns are supposed to differ; if they agree, this test '
            'and the .env wording are both measuring nothing')

    @pytest.mark.parametrize('overrides,label', [
        ({}, 'declared_content_length'),
        ({'CONTENT_LENGTH': None, 'wsgi.input_terminated': True},
         'no_content_length_terminated'),
    ], ids=['declared', 'undeclared_terminated'])
    def test_a_urlencoded_body_over_the_transport_cap_is_413_in_BOTH_columns(
            self, client, app, overrides, label):
        """What the templates may claim unconditionally: the transport cap is
        the one limit that behaves identically in both columns."""
        body = b'note=' + b'x' * (app.config['MAX_REQUEST_BODY_BYTES'] + 4096)
        resp = client.post('/admin/api/materials/validate', data=body,
                           content_type='application/x-www-form-urlencoded',
                           environ_overrides=overrides)
        assert resp.status_code == 413, label

    def test_multipart_upload_does_not_cache_the_raw_body_beside_the_parsed_file(
            self, app, test_storage):
        """`parse_form_data=True` also means the parser consumes the stream and
        `get_data` caches `b''`. With it `False`, a 24 MiB photo is buffered
        twice."""
        from flask import request

        seen = {}
        probe_app = create_app(TestConfig, storage_backend=test_storage)

        @probe_app.route('/__cache_probe__', methods=['POST'])
        def _cache_probe():
            seen['cached'] = request._cached_data
            seen['files'] = sorted(request.files.keys())
            seen['form'] = sorted(request.form.keys())
            return 'ok'

        resp = probe_app.test_client().post(
            '/__cache_probe__',
            data={'note': 'hello', 'file': (io.BytesIO(b'x' * 2048), 'a.bin')},
            content_type='multipart/form-data')

        assert resp.status_code == 200
        assert seen['cached'] == b''
        # ...and the parsed upload still arrives intact.
        assert seen['files'] == ['file']
        assert seen['form'] == ['note']


@pytest.mark.unit
class TestNoViewCodeRuns:
    """A rejected request must not reach the view at all -- not merely produce a
    413 the view happened not to spoil."""

    def test_oversize_scan_never_calls_resolve_scan(self, client, app, monkeypatch):
        from app.mariadb_catalog_service import CatalogService

        calls = []
        original = CatalogService.resolve_scan

        def _spy(self, raw):
            calls.append(raw)
            return original(self, raw)

        monkeypatch.setattr(CatalogService, 'resolve_scan', _spy)

        assert client.post('/api/scan', data=_oversize_body(app),
                           content_type='application/json').status_code == 413
        assert calls == []

    def test_oversize_undeclared_scan_never_calls_resolve_scan(
            self, client, app, monkeypatch):
        from app.mariadb_catalog_service import CatalogService

        calls = []
        original = CatalogService.resolve_scan

        def _spy(self, raw):
            calls.append(raw)
            return original(self, raw)

        monkeypatch.setattr(CatalogService, 'resolve_scan', _spy)

        assert client.post('/api/scan', data=_oversize_body(app),
                           content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': None,
                                              **_TERMINATED}).status_code == 413
        assert calls == []

    def test_oversize_photo_upload_never_constructs_a_photo_service(
            self, client, app, monkeypatch):
        import app.photo_service as photo_service

        calls = []
        original = photo_service.PhotoService.__init__

        def _spy(self, storage_backend=None):
            calls.append(storage_backend)
            return original(self, storage_backend)

        monkeypatch.setattr(photo_service.PhotoService, '__init__', _spy)

        resp = client.post(
            '/api/items/JA000001/photos',
            data={'file': (io.BytesIO(_oversize_body(app, 'MAX_UPLOAD_BODY_BYTES')),
                           'huge.jpg')},
            content_type='multipart/form-data')
        assert resp.status_code == 413
        assert calls == []


class _UnderSendingStream:
    """Delivers fewer bytes than the request declared -- a client disconnect.

    Werkzeug's `LimitedStream` raises `ClientDisconnected` when the declared
    `Content-Length` is not delivered. Before this feature, only a route that
    actually read the body noticed.
    """

    def __init__(self, data):
        self._data = io.BytesIO(data)

    def read(self, size=-1):
        return self._data.read(size)

    def readline(self, size=-1):
        return self._data.readline(size)


@pytest.mark.unit
class TestTheForcedReadDoesNotInventAnswers:
    """The hook reads the body speculatively, on every request. That must not
    change the answer to any question it was not asked.

    Two measured ways it did:

    * a client that disconnects or under-sends its declared body raised
      `ClientDisconnected` from the hook on routes that never touch the body,
      answering a raw Werkzeug 400 where the route had always returned normally;
    * an over-limit body sent to a URL that 404s, 405s or redirects was answered
      413 -- telling the caller their body was too large for a resource that
      does not exist or does not accept bodies.
    """

    def test_a_disconnect_does_not_change_a_route_that_never_reads_the_body(
            self, client):
        """A `GET` that reads nothing must be answered exactly as it always was.

        Note this cannot mask an oversize body: `RequestEntityTooLarge` is not a
        `ClientDisconnected`, and
        `test_the_disconnect_tolerance_does_not_swallow_an_oversize_body` below
        is the control.
        """
        baseline = client.get('/health')
        resp = client.get('/health', environ_overrides={
            'wsgi.input': _UnderSendingStream(b'ab'),
            'CONTENT_LENGTH': '5000'})

        assert resp.status_code == baseline.status_code
        assert resp.status_code < 400, (
            'a client hanging up made a bodyless route fail; the hook is '
            'reading speculatively and reporting what it found')

    def test_a_disconnect_on_a_route_that_does_read_the_body_still_surfaces(
            self, client):
        """Swallowing it in the hook must not swallow it for the view: a route
        that genuinely needs the body hits the same disconnect itself and is
        answered exactly as it was before this feature existed."""
        resp = client.post('/api/scan', environ_overrides={
            'wsgi.input': _UnderSendingStream(b'ab'),
            'CONTENT_LENGTH': '5000'},
            content_type='application/json')
        assert resp.status_code == 400
        assert resp.status_code < 500

    def test_the_disconnect_tolerance_does_not_swallow_an_oversize_body(
            self, client, app):
        """Control for the two above."""
        resp = client.post('/api/scan', data=_oversize_body(app),
                           content_type='application/json')
        assert resp.status_code == 413

    def test_an_oversize_body_to_a_nonexistent_url_is_404_not_413(
            self, client, app):
        resp = client.post('/no/such/url/at/all', data=_oversize_body(app),
                           content_type='application/json')
        assert resp.status_code == 404

    def test_an_oversize_body_with_the_wrong_method_is_405_not_413(
            self, client, app):
        resp = client.put('/api/scan', data=_oversize_body(app),
                          content_type='application/json')
        assert resp.status_code == 405

    def test_an_oversize_body_to_a_redirecting_url_gets_the_redirect_not_413(
            self, app, test_storage):
        """Werkzeug's `strict_slashes` redirect is a routing *exception*, raised
        after `before_request` runs -- so the hook has to stand aside for it the
        same way it does for a 404. No shipped rule ends in a slash, hence the
        probe route."""
        probe_app = create_app(TestConfig, storage_backend=test_storage)

        @probe_app.route('/__needs_slash__/', methods=['POST'])
        def _needs_slash():
            return 'ok'

        resp = probe_app.test_client().post(
            '/__needs_slash__', data=_oversize_body(probe_app),
            content_type='application/json')

        assert resp.status_code in (307, 308), resp.status_code
        assert resp.headers['Location'].endswith('/__needs_slash__/')

    def test_an_oversize_body_to_a_REAL_route_is_still_413(self, client, app):
        """The converse of all four above: standing aside for routing failures
        must not stand aside for anything else."""
        resp = client.post('/api/inventory/search', data=_oversize_body(app),
                           content_type='application/json')
        assert resp.status_code == 413


@pytest.mark.unit
class TestJsonEnvelopes:
    """Two conventions, chosen by endpoint. There is no single correct shape:
    `scan-capture.js:457` reads `data.error.message`; `inventory-move.js:704`
    interpolates `${result.error}` and renders "[object Object]" if handed the
    object shape."""

    def test_message_constant_is_the_shipped_sentence(self):
        """Pins the constant to a literal, so an edit to the wording is a
        deliberate act rather than a silent change to five UIs."""
        assert REQUEST_TOO_LARGE_MESSAGE == _EXPECTED_413_SENTENCE

    @pytest.mark.parametrize('remedy', ['smaller file', 'field', 'fewer items'])
    def test_a_file_is_not_offered_as_the_only_remedy(self, remedy):
        """A file is not the only cause. Flask's 500 KB `MAX_FORM_MEMORY_SIZE`
        is reached by one long text field with no file involved at all, and the
        transport cap by an over-large batch, so wording that says only "try a
        smaller file" is wrong advice for two of the three reachable causes.
        The rendered page has to cover the same ground as the JSON sentence."""
        assert remedy in REQUEST_TOO_LARGE_MESSAGE
        template = (REPO_ROOT / 'app/templates/errors/413.html').read_text()
        assert remedy in template

    def test_catalog_route_gets_the_ad13_object_envelope(self, client, app):
        resp = client.post('/api/scan', data=_oversize_body(app),
                           content_type='application/json')
        assert resp.status_code == 413
        body = resp.get_json()
        assert body['success'] is False
        assert body['error'] == {'code': 'request_too_large',
                                 'message': _EXPECTED_413_SENTENCE}

    def test_scan_capture_js_error_message_path_resolves_to_the_sentence(
            self, client, app):
        """`scan-capture.js:457`: `data && data.error && data.error.message`."""
        resp = client.post('/api/scan', data=_oversize_body(app),
                           content_type='application/json')
        assert resp.get_json()['error']['message'] == _EXPECTED_413_SENTENCE

    def test_legacy_route_gets_the_string_error_envelope(self, client, app):
        resp = client.post('/api/inventory/batch-move', data=_oversize_body(app),
                           content_type='application/json')
        assert resp.status_code == 413
        body = resp.get_json()
        assert body['success'] is False
        assert body['error'] == _EXPECTED_413_SENTENCE

    def test_inventory_move_js_renders_a_sentence_and_never_object_object(
            self, client, app):
        """`inventory-move.js:704`: `Move failed: ${result.error}`. JS renders a
        plain object as "[object Object]", so the value must be a string."""
        resp = client.post('/api/inventory/batch-move', data=_oversize_body(app),
                           content_type='application/json')
        rendered = f"Move failed: {resp.get_json()['error']}"
        assert rendered == f'Move failed: {_EXPECTED_413_SENTENCE}'
        assert '[object Object]' not in rendered

    def test_photo_manager_js_reads_the_top_level_message(self, client, app):
        """`photo-manager.js:338`: `errorData.message || 'Upload failed'`."""
        resp = client.post(
            '/api/items/JA000001/photos',
            data={'file': (io.BytesIO(_oversize_body(app, 'MAX_UPLOAD_BODY_BYTES')),
                           'huge.jpg')},
            content_type='multipart/form-data')
        assert resp.status_code == 413
        assert resp.get_json()['message'] == _EXPECTED_413_SENTENCE

    def test_admin_api_route_without_a_json_content_type_still_gets_json(
            self, client, app):
        """`startswith('/api/')` would miss `/admin/api/...`. The check is on
        the REGISTERED RULE, `request.url_rule.rule`, which carries the
        blueprint prefix and is written in this repo rather than by the
        caller."""
        resp = client.post('/admin/api/materials/validate',
                           data=_oversize_body(app),
                           content_type='application/x-www-form-urlencoded')
        assert resp.status_code == 413
        assert resp.get_json()['error'] == _EXPECTED_413_SENTENCE

    def test_an_html_route_whose_URL_contains_api_still_gets_the_html_page(
            self, app, test_storage):
        """`'/api/' in request.path` is a substring test on caller-chosen text.

        A product slug, a category segment, or `/products/edit/api/x` puts that
        substring in the path of a route that renders HTML, and the caller was
        then handed a JSON body where the browser expected a page. The rule
        string cannot be steered that way: this probe route's registered rule is
        `/pages/<path:rest>` whatever the caller puts in `rest`.
        """
        probe_app = create_app(TestConfig, storage_backend=test_storage)

        @probe_app.route('/pages/<path:rest>', methods=['POST'])
        def _html_page(rest):
            return 'ok'

        resp = probe_app.test_client().post(
            '/pages/api/x', data=_oversize_body(probe_app),
            content_type='application/x-www-form-urlencoded')

        assert resp.status_code == 413
        assert '/api/' in resp.request.path, 'the probe no longer probes'
        assert resp.mimetype == 'text/html', resp.data[:200]
        assert b'Submission Too Large' in resp.data

    def test_a_json_content_type_still_wins_on_a_non_api_rule(self, app,
                                                              test_storage):
        """The `is_json` limb is not redundant: a route outside `/api/` that a
        client posts JSON to still gets JSON back."""
        probe_app = create_app(TestConfig, storage_backend=test_storage)

        @probe_app.route('/not-an-api-rule', methods=['POST'])
        def _json_ish():
            return 'ok'

        resp = probe_app.test_client().post(
            '/not-an-api-rule', data=_oversize_body(probe_app),
            content_type='application/json')

        assert resp.status_code == 413
        assert resp.get_json()['error'] == _EXPECTED_413_SENTENCE

    def test_the_json_branch_reads_the_registered_rule_not_the_request_path(self):
        """Structural pin on the EXECUTABLE source -- the comment above the
        branch deliberately names the retired form, and that history is the
        point of the comment."""
        code = _executable_source('app/error_handlers.py',
                                  'handle_request_too_large')
        assert "'/api/' in request.path" not in code
        assert 'request.url_rule' in code

    def test_the_handler_degrades_to_a_plain_text_413_if_the_render_raises(
            self, app, test_storage, monkeypatch):
        """The render is the last thing in the handler that can raise, and the
        handler exists to prevent 500s. A Jinja error or an endpoint
        `base.html` cannot resolve must not become the very failure this code
        was written to stop."""
        import app.error_handlers as error_handlers

        probe_app = create_app(TestConfig, storage_backend=test_storage)

        def _boom(*args, **kwargs):
            raise RuntimeError('template exploded')

        monkeypatch.setattr(error_handlers, 'render_template', _boom)

        resp = probe_app.test_client().post(
            '/products/edit/1', data=_oversize_body(probe_app),
            content_type='application/x-www-form-urlencoded')

        assert resp.status_code == 413
        assert resp.mimetype == 'text/plain'
        assert _EXPECTED_413_SENTENCE.encode() in resp.data

    def test_catalog_json_endpoints_is_exactly_the_views_reaching_catalog_json_error(self):
        """Structural pin: a new catalog route that forgets to appear in
        `CATALOG_JSON_ENDPOINTS` would silently serve the legacy envelope to a
        client that reads `error.message`.

        Scans both blueprint route modules, and follows helper indirection --
        the previous version did neither, so an admin catalog route, or one
        reaching `_catalog_json_error` through a helper, passed it silently."""
        assert CATALOG_JSON_ENDPOINTS == _qualified_views_reaching(
            _calls_function('_catalog_json_error'))

    def test_the_structural_scan_covers_every_module_that_registers_views(self, app):
        """A guard that only ever looked at `app/main/routes.py` is how an admin
        upload or catalog route could be added in silence. Pin the scanned
        module list to the blueprints actually registered on the app, so
        dropping one -- or adding a third blueprint -- turns this red."""
        registered = {rule.endpoint.split('.')[0]
                      for rule in app.url_map.iter_rules() if '.' in rule.endpoint}
        assert registered <= set(VIEW_MODULES.values())

    def test_the_structural_scan_covers_every_FILE_that_defines_a_view(self, app):
        """The blueprint check above is not enough on its own, and the gap is
        the realistic one: `VIEW_MODULES` names FILES, while that test compares
        BLUEPRINT NAMES. Splitting `main`'s views into a new
        `app/main/upload_routes.py` keeps the blueprint name `main`, so it stays
        green -- and `_qualified_views_reaching` never opens the new file, so a
        `request.files` view there silently gets the 1 MiB cap and a
        `_catalog_json_error` view there silently gets the wrong JSON envelope.

        Pin the source file of every registered view instead, which is the thing
        the scanner actually reads."""
        scanned = {str(REPO_ROOT / relative) for relative in VIEW_MODULES}
        offenders = {}
        for endpoint, view in app.view_functions.items():
            if '.' not in endpoint:      # Flask's own `static`, etc.
                continue
            source = inspect.getsourcefile(inspect.unwrap(view))
            if source is not None and str(Path(source).resolve()) not in scanned:
                offenders[endpoint] = source
        assert offenders == {}, (
            'these views live outside VIEW_MODULES, so the structural pins '
            f'never see them: {offenders}')

    def test_the_structural_scanner_actually_follows_helper_indirection(self):
        """Self-test for the scanner. Without it, a guard that quietly stopped
        following helpers would keep passing forever on a codebase that happens
        to call everything inline today."""
        source = textwrap.dedent('''
            def _envelope(message):
                return _catalog_json_error(message)

            def _wrapper(message):
                return _envelope(message)

            @bp.route('/direct')
            def direct_view():
                return _catalog_json_error('x')

            @bp.route('/indirect')
            def indirect_view():
                return _wrapper('x')

            @bp.route('/unrelated')
            def unrelated_view():
                return 'ok'
        ''')
        assert _views_reaching_in_source(
            source, _calls_function('_catalog_json_error')) == {
                'direct_view', 'indirect_view'}


@pytest.mark.unit
class TestRejectionLogLineIsSanitised:
    """Every value that reaches the 413 log line is caller-controlled, so every
    one of them is bounded and CR/LF-escaped.

    The reverted iteration truncated `Content-Length` to 32 characters while
    echoing an unbounded, CRLF-capable `request.path` in the same statement --
    careful about one attacker-chosen value and blind to the other in the same
    breath. The deployment guide tells operators to aggregate this JSON log, and
    a newline in either value forges whole records in it.
    """

    @staticmethod
    def _rejection_messages(caplog):
        """The rejection log lines, read via `caplog`.

        `capsys` is no use here: the handlers `setup_logging` installs captured
        their stream when the shared `app` fixture was built, long before any of
        these tests started capturing. (The `create_app`-ordering tests
        elsewhere in this module read the stream instead, precisely because they
        build their own app inside the test.)
        """
        return [record.getMessage() for record in caplog.records
                if 'rejected as too large' in record.getMessage()]

    # A path that ROUTES, with an attacker-chosen segment inside it. It has to
    # route: an over-limit body sent to a URL that 404s is answered 404, not
    # 413, so a made-up path would exercise nothing. `<ja_id>` is a plain string
    # converter, so the caller picks its content and its length.
    LONG_PATH = '/api/items/' + 'p' * 4000 + '/duplicate'
    CRLF_PATH = '/api/items/x%0d%0alevel=INFO/duplicate'

    def test_a_very_long_request_path_is_bounded_and_marked_as_truncated(
            self, client, app, caplog):
        with caplog.at_level(logging.WARNING):
            client.post(self.LONG_PATH, data=_oversize_body(app),
                        content_type='application/json')

        messages = self._rejection_messages(caplog)
        assert messages, 'no rejection was logged at all'
        assert LOG_TRUNCATION_MARKER in messages[0]
        # Bounded: nowhere near the 4000 characters the caller chose.
        assert 'p' * (LOGGED_PATH_CHARS + 1) not in messages[0]
        assert len(messages[0]) < 4000

    def test_crlf_in_the_request_path_cannot_forge_a_log_record(
            self, client, app, caplog):
        with caplog.at_level(logging.WARNING):
            client.post(self.CRLF_PATH, data=_oversize_body(app),
                        content_type='application/json')

        messages = self._rejection_messages(caplog)
        assert messages, 'no rejection was logged at all'
        assert '\r' not in messages[0] and '\n' not in messages[0]
        assert '\\r\\nlevel=INFO' in messages[0]

    def test_a_5000_digit_content_length_is_bounded_and_marked_as_truncated(
            self, client, app, caplog):
        stream = _generating_stream(app)
        with caplog.at_level(logging.WARNING):
            client.post('/api/scan', content_type='application/json',
                        environ_overrides={'CONTENT_LENGTH': '9' * 5000,
                                           'wsgi.input': stream,
                                           **_TERMINATED})

        messages = self._rejection_messages(caplog)
        assert messages, 'no rejection was logged at all'
        assert LOG_TRUNCATION_MARKER in messages[0]
        assert '9' * 200 not in messages[0]

    def test_an_ordinary_short_value_is_logged_verbatim_with_no_marker(
            self, client, app, caplog):
        """Control: the truncation marker must MEAN something. If it were
        appended unconditionally a clipped value would still be
        indistinguishable from a genuine one."""
        with caplog.at_level(logging.WARNING):
            client.post('/api/scan', data=_oversize_body(app),
                        content_type='application/json')

        messages = self._rejection_messages(caplog)
        assert messages, 'no rejection was logged at all'
        assert LOG_TRUNCATION_MARKER not in messages[0]
        assert '/api/scan' in messages[0]


@pytest.mark.unit
class TestHtmlBranchRendersAndNeverRedirects:
    """The HTML branch renders `errors/413.html`. Nothing about the response is
    derived from a request header -- which is what deletes the open redirect,
    the `javascript://` scheme bypass, the `urlsplit` 500 on `Referer:
    http://[::1`, and the `SCRIPT_NAME` self-redirect loop, all at once."""

    def test_oversize_form_post_renders_413_with_no_location_header(self, client, app):
        resp = client.post('/products/edit/1', data=_oversize_body(app),
                           content_type='application/x-www-form-urlencoded')
        assert resp.status_code == 413
        assert 'Location' not in resp.headers
        assert b'Submission Too Large' in resp.data

    @pytest.mark.parametrize('referer', [
        'http://[::1',                    # urlsplit() raises ValueError on this
        'javascript://localhost/x',       # scheme bypass
        'http://evil.example.com/x',      # external host
        'http://LOCALHOST:8080/products', # same host, different case and port
    ])
    def test_no_referer_value_changes_the_413_response(self, client, app, referer):
        baseline = client.post('/products/edit/1', data=_oversize_body(app),
                               content_type='application/x-www-form-urlencoded')
        resp = client.post('/products/edit/1', data=_oversize_body(app),
                           content_type='application/x-www-form-urlencoded',
                           headers={'Referer': referer})
        assert resp.status_code == 413
        assert 'Location' not in resp.headers
        assert resp.data == baseline.data

    def test_oversize_form_post_under_a_non_root_script_name_is_413_not_a_redirect(
            self, client, app):
        """Under a `/inv` mount an earlier iteration answered 302 -> `/inv/index`
        for an oversize `POST /index`: the self-redirect loop, restored."""
        resp = client.post('/products/edit/1', data=_oversize_body(app),
                           content_type='application/x-www-form-urlencoded',
                           environ_overrides={'SCRIPT_NAME': '/inv'})
        assert resp.status_code == 413
        assert 'Location' not in resp.headers

    def test_the_413_handler_neither_reads_the_referer_nor_redirects(self):
        """The property is structural, so assert it structurally -- prose in the
        handler's docstring is free to *mention* `Referer` (it explains why the
        subsystem was deleted); what must not exist is code that reads it or
        emits a redirect."""
        handler_code = _executable_source('app/error_handlers.py',
                                          'handle_request_too_large')
        for forbidden in ('referrer', 'Referer', 'REFERER',
                          'redirect', 'urlsplit', 'url_for'):
            assert forbidden not in handler_code, forbidden


@pytest.mark.unit
class TestUploadEndpoints:
    """`UPLOAD_ENDPOINTS` gets the raised ceiling. Both directions are pinned:
    every name must resolve to a real view, and every view reading
    `request.files` must be named."""

    def test_every_upload_endpoint_name_resolves_to_a_registered_view(self, app):
        registered = {rule.endpoint for rule in app.url_map.iter_rules()}
        assert UPLOAD_ENDPOINTS <= registered

    def test_every_view_reaching_request_files_is_an_upload_endpoint(self):
        """Scans `app/admin/routes.py` as well as `app/main/routes.py`, and
        follows helper indirection: a new upload route on either blueprint, or
        one that reaches `request.files` through a helper rather than by a
        direct attribute read, must not pass this guard in silence."""
        assert _qualified_views_reaching(_reads_request_files) == set(UPLOAD_ENDPOINTS)

    def test_attachment_above_the_global_limit_but_below_the_ceiling_reaches_the_view(
            self, client, app, test_storage):
        from app.mariadb_catalog_service import CatalogService

        product_id = CatalogService(test_storage).create_product(
            description='widget')
        payload = b'%PDF-1.4\n' + b'0' * (app.config['MAX_REQUEST_BODY_BYTES'] + 4096)
        assert len(payload) < app.config['MAX_UPLOAD_BODY_BYTES']

        resp = client.post(f'/products/{product_id}/attachments',
                           data={'file': (io.BytesIO(payload), 'big.pdf')},
                           content_type='multipart/form-data')

        assert resp.status_code == 302
        rows = CatalogService(test_storage).get_attachments_for_product(product_id)
        assert [row.filename for row in rows] == ['big.pdf']

    def test_photo_above_the_global_limit_but_below_the_ceiling_reaches_the_view(
            self, client, app):
        payload = b'\xff\xd8\xff' + b'0' * (app.config['MAX_REQUEST_BODY_BYTES'] + 4096)
        assert len(payload) < app.config['MAX_UPLOAD_BODY_BYTES']

        resp = client.post('/api/items/JA000001/photos',
                           data={'file': (io.BytesIO(payload), 'big.jpg')},
                           content_type='multipart/form-data')

        # The view ran: it answers about the item/photo, not about the body size.
        assert resp.status_code != 413

    def test_upload_above_the_upload_ceiling_is_413_not_swallowed_into_a_500(
            self, client, app):
        """`upload_photo` reads `request.files` inside a `try` whose tail is
        `except Exception: return 500`."""
        payload = _oversize_body(app, 'MAX_UPLOAD_BODY_BYTES')
        resp = client.post('/api/items/JA000001/photos',
                           data={'file': (io.BytesIO(payload), 'huge.jpg')},
                           content_type='multipart/form-data')
        assert resp.status_code == 413

    # ---- the ceiling requires an actual upload, not just the endpoint ------

    def test_declared_non_multipart_body_over_the_global_limit_is_413_at_an_upload_endpoint(
            self, client, app):
        """**Measured on the reverted iteration:** an 8 MiB `application/json`
        body to the unauthenticated, `@csrf.exempt` `main.upload_photo` was
        accepted and cached under the 24 MiB ceiling, because the ceiling keyed
        on the endpoint name alone. That handed back most of the exposure this
        feature exists to close. The raised ceiling is for multipart uploads."""
        size = app.config['MAX_REQUEST_BODY_BYTES'] + 4096
        assert size < app.config['MAX_UPLOAD_BODY_BYTES']

        stream = _GeneratingStream(size)
        resp = client.post('/api/items/JA000001/photos',
                           content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': str(size),
                                              'wsgi.input': stream,
                                              **_TERMINATED})
        assert resp.status_code == 413
        # Rejected on the declared-length fast path, at the GLOBAL limit.
        assert stream.requested == []

    def test_undeclared_non_multipart_body_over_the_global_limit_is_413_at_an_upload_endpoint(
            self, client, app):
        """The same rule has to hold in the middleware, not only in the hook:
        with no declared length the cap installed on the stream is the only
        thing choosing between 1 MiB and 24 MiB."""
        stream = _generating_stream(app)
        resp = client.post('/api/items/JA000001/photos',
                           content_type='application/json',
                           environ_overrides={'CONTENT_LENGTH': None,
                                              'wsgi.input': stream,
                                              **_TERMINATED})
        assert resp.status_code == 413
        _assert_body_bytes_were_bounded(stream, app.config['MAX_REQUEST_BODY_BYTES'])

    def test_the_upload_mimetype_constant_is_the_one_the_ceiling_keys_on(self):
        assert UPLOAD_MIMETYPE == 'multipart/form-data'


@pytest.mark.unit
class TestUploadsWithCsrfActuallyEnabled:
    """The default fixtures set `WTF_CSRF_ENABLED = False`, so `csrf_protect`
    short-circuits and never parses the form. These build a real CSRF-enabled
    app (precedent: tests/unit/test_scan_routes.py:336) so the ordering of
    `init_request_limits` against `csrf.init_app` is exercised for real, at the
    request level, rather than by comparing hook names."""

    @staticmethod
    def _csrf_app(test_storage):
        class CsrfEnabledConfig(TestConfig):
            WTF_CSRF_ENABLED = True

        return create_app(CsrfEnabledConfig, storage_backend=test_storage)

    def test_csrf_protection_is_genuinely_on_in_this_app(self, test_storage):
        """Control. Without it, the assertions below mean nothing."""
        app = self._csrf_app(test_storage)

        @app.route('/__csrf_control__', methods=['POST'])
        def _csrf_control():           # pragma: no cover - never reached
            return 'reached'

        assert app.test_client().post('/__csrf_control__').status_code == 400

    def test_over_ceiling_attachment_is_413_rather_than_a_csrf_error(self, test_storage):
        app = self._csrf_app(test_storage)
        from app.mariadb_catalog_service import CatalogService
        product_id = CatalogService(test_storage).create_product(
            description='widget')

        payload = _oversize_body(app, 'MAX_UPLOAD_BODY_BYTES')
        resp = app.test_client().post(
            f'/products/{product_id}/attachments',
            data={'file': (io.BytesIO(payload), 'huge.pdf')},
            content_type='multipart/form-data')

        assert resp.status_code == 413

    def test_over_global_limit_attachment_still_uploads_with_csrf_enabled(
            self, test_storage):
        """A >1 MiB attachment is above the global bound and below the upload
        ceiling: it must be accepted, CSRF token and all."""
        app = self._csrf_app(test_storage)
        from app.mariadb_catalog_service import CatalogService
        product_id = CatalogService(test_storage).create_product(
            description='widget')

        client = app.test_client()
        page = client.get(f'/products/{product_id}')
        token = _csrf_token_from(page.data)

        payload = b'%PDF-1.4\n' + b'0' * (app.config['MAX_REQUEST_BODY_BYTES'] + 4096)
        resp = client.post(
            f'/products/{product_id}/attachments',
            data={'csrf_token': token, 'file': (io.BytesIO(payload), 'big.pdf')},
            content_type='multipart/form-data')

        assert resp.status_code == 302
        rows = CatalogService(test_storage).get_attachments_for_product(product_id)
        assert [row.filename for row in rows] == ['big.pdf']


def _csrf_token_from(html_bytes):
    """Pull the hidden csrf_token value out of a rendered page."""
    import re
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html_bytes)
    assert match is not None, 'no csrf_token field on the page'
    return match.group(1).decode()


@pytest.mark.unit
class TestCappedStream:
    """Every read path the class exposes must be counted -- an uncounted method
    is a silent bypass of the whole feature."""

    def test_read_past_the_cap_raises(self):
        stream = CappedStream(io.BytesIO(b'x' * 100), 10)
        with pytest.raises(RequestEntityTooLarge):
            stream.read()

    def test_repeated_small_reads_accumulate_to_the_cap(self):
        stream = CappedStream(io.BytesIO(b'x' * 100), 10)
        for _ in range(5):
            assert stream.read(2) == b'xx'
        with pytest.raises(RequestEntityTooLarge):
            stream.read(2)

    def test_readline_past_the_cap_raises(self):
        stream = CappedStream(io.BytesIO(b'x' * 100 + b'\n'), 10)
        with pytest.raises(RequestEntityTooLarge):
            stream.readline()

    def test_readlines_past_the_cap_raises(self):
        stream = CappedStream(io.BytesIO(b'aaaa\nbbbb\ncccc\n'), 10)
        with pytest.raises(RequestEntityTooLarge):
            stream.readlines()

    def test_iteration_past_the_cap_raises(self):
        stream = CappedStream(io.BytesIO(b'aaaa\nbbbb\ncccc\n'), 10)
        with pytest.raises(RequestEntityTooLarge):
            list(stream)

    def test_reads_up_to_the_cap_are_returned_whole_and_never_truncated(self):
        stream = CappedStream(io.BytesIO(b'x' * 10), 10)
        assert stream.read() == b'x' * 10
        assert stream.bytes_read == 10

    def test_exposes_no_readinto_so_limitedstream_falls_back_to_counted_read(self):
        """`werkzeug.wsgi.LimitedStream.readinto` probes
        `hasattr(self._stream, 'readinto')` and uses it directly if present,
        reading bytes this class would never see. Absence of the attribute is
        load-bearing, which is also why there is no `__getattr__` delegate."""
        assert not hasattr(CappedStream(io.BytesIO(b''), 10), 'readinto')
        assert not hasattr(CappedStream(io.BytesIO(b''), 10), 'read1')

    def test_close_does_not_close_the_server_owned_wsgi_input(self):
        """PEP 3333 reserves `wsgi.input` to the server -- "the server MUST NOT
        close the input stream", and an application-side wrapper must not either.
        Delegating let any caller that closes the request stream tear down a
        connection the server still owns and intends to reuse."""
        wrapped = io.BytesIO(b'xyz')
        CappedStream(wrapped, 10).close()
        assert not wrapped.closed
        assert wrapped.read() == b'xyz'


@pytest.mark.unit
class TestCappedStreamClamps:
    """Counting a read bounds the RESPONSE. Clamping it bounds the MEMORY, and
    the memory is the entire point of the feature.

    Two reverted iterations live in this class. The first delegated an unsized
    `read(-1)` straight to `wsgi.input` and counted afterwards, so a 64 MiB body
    against a 1 MiB cap produced a correct 413 after 64 MiB was resident. The
    second translated that into a single `read(cap - already_read + 1)`, which
    is worse: `io.BufferedReader.read(n)` allocates `n` up front, so the cost
    stopped scaling with the attacker's body and started scaling with the
    CONFIGURED CAP, on every request in the app.

    So the cap here is deliberately many times `_MAX_SINGLE_READ`: with a cap
    smaller than one chunk, the per-read bound is never the binding constraint
    and this class would pass with the per-read clamp deleted.
    """

    CAP = _MAX_SINGLE_READ * 8          # so the per-read bound actually binds
    BODY = CAP * 64                     # 64x the cap, the measured ratio

    def _stream(self):
        """A generating source plus the wrapper under test."""
        source = _GeneratingStream(self.BODY)
        return source, CappedStream(source, self.CAP)

    @pytest.mark.parametrize('size', [-1, None], ids=['minus_one', 'none'])
    def test_an_unsized_read_asks_for_no_more_than_one_chunk_at_a_time(self, size):
        source, capped = self._stream()
        with pytest.raises(RequestEntityTooLarge):
            capped.read(size)
        _assert_body_bytes_were_bounded(source, self.CAP)

    def test_an_over_large_sized_read_is_chunked_too(self):
        source, capped = self._stream()
        with pytest.raises(RequestEntityTooLarge):
            capped.read(self.BODY)
        _assert_body_bytes_were_bounded(source, self.CAP)

    def test_an_unsized_readline_is_chunked_on_a_newline_free_body(self):
        """A body with no newline in it is one enormous "line", so the SIZE
        bound -- not the newline -- has to terminate the read."""
        source, capped = self._stream()
        with pytest.raises(RequestEntityTooLarge):
            capped.readline()
        _assert_body_bytes_were_bounded(source, self.CAP)

    def test_readlines_is_built_on_the_chunked_readline(self):
        """Delegating to the wrapped stream's own `readlines` would read
        everything first and count the pieces afterwards."""
        source, capped = self._stream()
        with pytest.raises(RequestEntityTooLarge):
            capped.readlines()
        _assert_body_bytes_were_bounded(source, self.CAP)

    def test_iteration_is_built_on_the_chunked_readline(self):
        source, capped = self._stream()
        with pytest.raises(RequestEntityTooLarge):
            list(capped)
        _assert_body_bytes_were_bounded(source, self.CAP)

    def test_the_total_bound_shrinks_as_the_running_total_grows(self):
        """The per-read bound is a constant; the TOTAL bound is not. After `n`
        bytes the wrapper may still only pull `cap - n + 1` more, in chunks."""
        source, capped = self._stream()
        capped.read(400)
        capped.read(400)
        with pytest.raises(RequestEntityTooLarge):
            capped.read()
        assert source.requested[:2] == [400, 400]
        assert source.largest_read_requested <= _MAX_SINGLE_READ
        assert source.bytes_generated <= self.CAP + 1

    def test_a_body_under_the_cap_still_arrives_whole_through_an_unsized_read(self):
        """The clamp must not become a truncation: `read()` on an under-cap body
        returns all of it, however many chunks that takes."""
        source = _GeneratingStream(self.CAP - 1)
        capped = CappedStream(source, self.CAP)
        assert capped.read() == b'a' * (self.CAP - 1)
        assert capped.bytes_read == self.CAP - 1
        assert source.largest_read_requested <= _MAX_SINGLE_READ

    def test_an_unsized_read_reassembles_a_stream_that_returns_short_reads(self):
        """A WSGI server is free to return fewer bytes than asked for. The
        clamped `read()` loops rather than returning short, so a body under the
        cap arrives whole even from a dribbling stream."""
        class _DribblingStream:
            def __init__(self, data, chunk):
                self._data, self._chunk = data, chunk

            def read(self, size=-1):
                take = min(self._chunk, size if size >= 0 else len(self._data))
                chunk, self._data = self._data[:take], self._data[take:]
                return chunk

        capped = CappedStream(_DribblingStream(b'y' * 900, chunk=7), self.CAP)
        assert capped.read() == b'y' * 900


class _UnderHonouringStream:
    """A stream that IGNORES the size hint and returns `blob` every time.

    Not a hypothetical: the reverted iteration's `readline`/`readlines`/
    `__iter__` passed the hint down to the wrapped stream and counted whatever
    came back, so a stream like this materialised the entire body before `_count`
    ever ran -- measured, 10,000,000 bytes through a 1,000-byte cap. What a
    clamped implementation controls is the size it ASKS for; that is what this
    class records.
    """

    def __init__(self, blob):
        self._blob = blob
        self.requested = []

    def read(self, size=-1):
        self.requested.append(size)
        return self._blob

    def readline(self, size=-1):
        self.requested.append(size)
        return self._blob


@pytest.mark.unit
class TestEveryReadPathClampsRatherThanPassingTheHintDown:
    """`readline`/`readlines`/`__iter__` must loop under their OWN bound.

    Handing the size hint to the wrapped stream and counting the result trusts
    the stream to honour it. Three of the four read paths did exactly that
    while the class docstring claimed all four were clamped.
    """

    CAP = 1000
    BLOB = b'a' * 10_000_000        # the measured over-honoured return

    def _capped(self):
        source = _UnderHonouringStream(self.BLOB)
        return source, CappedStream(source, self.CAP)

    @pytest.mark.parametrize('drive', [
        lambda s: s.read(-1),
        lambda s: s.read(None),
        lambda s: s.readline(),
        lambda s: s.readlines(),
        lambda s: list(s),
    ], ids=['read_minus_one', 'read_none', 'readline', 'readlines', 'iter'])
    def test_no_read_path_ever_asks_for_more_than_one_chunk(self, drive):
        source, capped = self._capped()
        with pytest.raises(RequestEntityTooLarge):
            drive(capped)
        assert source.requested, 'the path never touched the wrapped stream'
        assert max(source.requested) <= _MAX_SINGLE_READ, source.requested
        # And never more than the allowance either, which for this cap is the
        # tighter of the two.
        assert max(source.requested) <= self.CAP + 1, source.requested


@pytest.mark.unit
class TestPerReadBoundIsASmallConstant:
    """The per-read bound must not scale with the configured cap.

    That is the entire distinction between this iteration and the reverted one:
    `cap - already_read + 1` is also "a bound", and it is the one that made a
    7-byte POST cost 24 MiB.
    """

    def test_the_chunk_size_is_64_kib(self):
        assert CappedStream._CHUNK == 64 * 1024

    def test_the_chunk_size_is_far_below_both_shipped_caps(self, app):
        assert _MAX_SINGLE_READ < app.config['MAX_REQUEST_BODY_BYTES']
        assert _MAX_SINGLE_READ * 100 < app.config['MAX_UPLOAD_BODY_BYTES']

    def test_the_largest_read_does_not_grow_when_the_cap_grows(self):
        """A cap 1000x larger must not produce a larger individual read."""
        largest = []
        for cap in (_MAX_SINGLE_READ * 4, _MAX_SINGLE_READ * 4000):
            source = _GeneratingStream(cap * 2)
            capped = CappedStream(source, cap)
            with pytest.raises(RequestEntityTooLarge):
                # `readline` on a newline-free stream stops at the FIRST chunk
                # that breaks the cap, so this exercises the per-read bound
                # without accumulating the whole cap first. Driving `read()`
                # here instead made this single unit test allocate ~268 MiB on
                # the large-cap pass -- two orders of magnitude more than
                # anything else in the suite, for a property that does not need
                # the bytes to exist.
                while True:
                    if not capped.readline():
                        break
            largest.append(source.largest_read_requested)
        assert largest[0] == largest[1] == _MAX_SINGLE_READ, largest


class _AllocateOnRequestRaw(io.RawIOBase):
    """A raw stream, so `io.BufferedReader` can wrap it for real.

    `_GeneratingStream` and `io.BytesIO` both manufacture only
    `min(size, remaining)` bytes, so neither can EVER over-allocate however
    large a read it is handed -- which is why a suite built only on them was
    structurally incapable of seeing the defect. `io.BufferedReader.read(n)`
    allocates `n` bytes before it knows how much data exists, and it is what the
    Werkzeug dev server hands over as `wsgi.input`.
    """

    def __init__(self, data):
        self._data = io.BytesIO(data)

    def readable(self):
        return True

    def readinto(self, buffer):
        return self._data.readinto(buffer)


@pytest.mark.unit
class TestTinyBodyDoesNotAllocateTheCap:
    """A 7-byte request must not cost 24 MiB.

    Measured on the reverted iteration: `BufferedReader.read(24 MiB)` over a
    9-byte body peaked at 24.00 MiB, and end-to-end a 7-byte multipart POST to
    the photo endpoint peaked at 24.03 MiB. The `before_request` hook issues
    `get_data()` on EVERY request, so that was a cap-sized transient allocation
    on every request in the app -- the control acting as its own amplifier.
    """

    # Generous: the point is orders of magnitude, not a tight fit. The reverted
    # iteration peaked at 24.03 MiB here.
    PEAK_ALLOWANCE = 1024 * 1024

    def test_an_unsized_read_of_a_tiny_buffered_body_does_not_peak_at_the_cap(
            self, app):
        cap = app.config['MAX_UPLOAD_BODY_BYTES']
        stream = io.BufferedReader(_AllocateOnRequestRaw(b'123456789'))
        capped = CappedStream(stream, cap)

        tracemalloc.start()
        try:
            assert capped.read(-1) == b'123456789'
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

        assert peak < self.PEAK_ALLOWANCE, (
            f'reading a 9-byte body against a {cap}-byte cap peaked at '
            f'{peak} bytes: the read is sized from the cap, not from a small '
            'constant, and a BufferedReader allocates what it is asked for')

    def test_a_tiny_multipart_post_to_the_photo_endpoint_does_not_peak_at_the_cap(
            self, app):
        """The end-to-end shape that was measured at 24.03 MiB.

        `wsgi.input` is a real `io.BufferedReader`, the endpoint is one of the
        two that get the 24 MiB ceiling, and there is no `Content-Length`, so
        the hook's `get_data()` issues the unsized read the defect lived in.
        """
        boundary = 'BoUnDaRy'
        body = (f'--{boundary}\r\n'
                'Content-Disposition: form-data; name="photo"; filename="a.txt"\r\n'
                'Content-Type: text/plain\r\n\r\n'
                f'hi\r\n--{boundary}--\r\n').encode()
        cap = app.config['MAX_UPLOAD_BODY_BYTES']
        client = app.test_client()

        def post():
            return client.post(
                '/api/items/JA000001/photos',
                environ_overrides={
                    'wsgi.input': io.BufferedReader(_AllocateOnRequestRaw(body)),
                    'CONTENT_TYPE': f'multipart/form-data; boundary={boundary}',
                    'CONTENT_LENGTH': None,
                    **_TERMINATED})

        # Warm up: the first request through an app builds jinja environments,
        # url adapters and error-handler tables. Those are one-off allocations,
        # not per-request ones, and measuring them would only hide the number
        # this test is about.
        for _ in range(3):
            post()

        tracemalloc.start()
        try:
            post()
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

        assert peak < self.PEAK_ALLOWANCE, (
            f'a {len(body)}-byte multipart POST against a {cap}-byte upload cap '
            f'peaked at {peak} bytes')


@pytest.mark.unit
class TestMiddlewareTotality:
    """`BodyLimitMiddleware` runs ahead of Flask entirely, so anything escaping
    it is a bare 500 with no error handler involved."""

    @staticmethod
    def _environ(**overrides):
        base = {
            'REQUEST_METHOD': 'POST',
            'PATH_INFO': '/api/scan',
            'SCRIPT_NAME': '',
            'SERVER_NAME': 'localhost',
            'SERVER_PORT': '80',
            'wsgi.url_scheme': 'http',
            'wsgi.input': io.BytesIO(b''),
        }
        base.update(overrides)
        return base

    def test_cap_for_returns_the_global_limit_for_an_unmatched_path(self, app):
        middleware = BodyLimitMiddleware(app.wsgi_app, app)
        cap = middleware._cap_for(self._environ(PATH_INFO='/nothing/here/at/all'))
        assert cap == app.config['MAX_REQUEST_BODY_BYTES']

    def test_cap_for_returns_the_global_limit_for_a_malformed_path(self, app):
        middleware = BodyLimitMiddleware(app.wsgi_app, app)
        cap = middleware._cap_for(self._environ(PATH_INFO='\udcff\x00%%%'))
        assert cap == app.config['MAX_REQUEST_BODY_BYTES']

    def test_cap_for_returns_the_global_limit_for_an_environ_missing_every_key(self, app):
        middleware = BodyLimitMiddleware(app.wsgi_app, app)
        assert middleware._cap_for({}) == app.config['MAX_REQUEST_BODY_BYTES']

    def test_cap_for_returns_the_upload_ceiling_for_a_multipart_upload_endpoint(self, app):
        middleware = BodyLimitMiddleware(app.wsgi_app, app)
        cap = middleware._cap_for(self._environ(
            PATH_INFO='/api/items/JA1/photos',
            CONTENT_TYPE='multipart/form-data; boundary=----x'))
        assert cap == app.config['MAX_UPLOAD_BODY_BYTES']

    def test_cap_for_returns_the_upload_ceiling_under_a_non_root_script_name(self, app):
        middleware = BodyLimitMiddleware(app.wsgi_app, app)
        cap = middleware._cap_for(self._environ(
            SCRIPT_NAME='/inv', PATH_INFO='/api/items/JA1/photos',
            CONTENT_TYPE='multipart/form-data; boundary=----x'))
        assert cap == app.config['MAX_UPLOAD_BODY_BYTES']

    @pytest.mark.parametrize('content_type', [
        'application/json',
        'application/x-www-form-urlencoded',
        '',
    ], ids=['json', 'urlencoded', 'absent'])
    def test_cap_for_returns_the_global_limit_for_a_non_multipart_upload_endpoint(
            self, app, content_type):
        """Endpoint identity alone is not enough. Keying on it and nothing else
        meant a measured 8 MiB `application/json` body to the unauthenticated,
        `@csrf.exempt` `main.upload_photo` was accepted under the 24 MiB
        ceiling."""
        middleware = BodyLimitMiddleware(app.wsgi_app, app)
        cap = middleware._cap_for(self._environ(PATH_INFO='/api/items/JA1/photos',
                                                CONTENT_TYPE=content_type))
        assert cap == app.config['MAX_REQUEST_BODY_BYTES']

    def test_is_multipart_ignores_case_and_quoting_around_the_boundary(self):
        assert is_multipart({'CONTENT_TYPE': 'Multipart/Form-Data; boundary=xyz'})
        assert is_multipart({'CONTENT_TYPE': ' multipart/form-data ; BOUNDARY=xyz'})
        assert is_multipart({'CONTENT_TYPE': 'multipart/form-data; boundary="xyz"'})
        assert is_multipart({'CONTENT_TYPE':
                             'multipart/form-data; charset=utf-8; boundary=xyz'})
        assert not is_multipart({'CONTENT_TYPE': 'multipart/mixed; boundary=xyz'})
        assert not is_multipart({})

    @pytest.mark.parametrize('content_type', [
        'multipart/form-data',
        'multipart/form-data;',
        'multipart/form-data; boundary=',
        'multipart/form-data; boundary=""',
        'multipart/form-data; boundary="   "',
        'multipart/form-data; charset=utf-8',
    ], ids=['bare', 'empty_params', 'empty_boundary', 'quoted_empty',
            'whitespace_boundary', 'other_param_only'])
    def test_a_missing_or_empty_boundary_does_not_buy_the_raised_ceiling(
            self, content_type):
        """The mimetype alone is one caller-chosen word. Requiring a non-empty
        `boundary` costs a real upload nothing -- Werkzeug cannot parse a
        multipart body without one either -- and stops the 24 MiB ceiling being
        available for the price of a header."""
        assert is_multipart({'CONTENT_TYPE': content_type}) is False

    def test_a_boundary_free_multipart_body_is_capped_at_the_global_limit(
            self, app):
        """The same check, through `_cap_for` rather than the helper."""
        middleware = BodyLimitMiddleware(app.wsgi_app, app)
        cap = middleware._cap_for(self._environ(
            PATH_INFO='/api/items/JA1/photos',
            CONTENT_TYPE='multipart/form-data'))
        assert cap == app.config['MAX_REQUEST_BODY_BYTES']

    def test_a_boundary_free_multipart_upload_over_the_global_limit_is_413(
            self, client, app):
        """End-to-end: a body between the two limits, labelled multipart but
        carrying no boundary, must be rejected at the tighter limit."""
        resp = client.post('/api/items/JA000001/photos',
                           data=_oversize_body(app),
                           content_type='multipart/form-data')
        assert resp.status_code == 413

    def test_cap_for_falls_back_to_a_literal_when_a_limit_key_is_missing(self, app):
        """`config['...']` here would be a `KeyError` escaping WSGI middleware
        as a bare 500 -- the one thing `_cap_for`'s docstring promises cannot
        happen. `validate_limits` makes this unreachable in a booted app, which
        is exactly why nothing else would ever catch it."""
        from app.request_limits import _FALLBACK_CAP_BYTES

        middleware = BodyLimitMiddleware(app.wsgi_app, app)
        saved = {k: app.config[k] for k in
                 ('MAX_REQUEST_BODY_BYTES', 'MAX_UPLOAD_BODY_BYTES')}
        try:
            for key in saved:
                del app.config[key]
            assert middleware._cap_for(self._environ()) == _FALLBACK_CAP_BYTES
            # And the upload branch falls back to the same TIGHTER value.
            assert middleware._cap_for(self._environ(
                PATH_INFO='/api/items/JA1/photos',
                CONTENT_TYPE='multipart/form-data; boundary=x')
            ) == _FALLBACK_CAP_BYTES
        finally:
            app.config.update(saved)

    def test_is_multipart_does_not_raise_on_a_non_str_content_type(self):
        """`_cap_for` must not be able to raise, so its helper must be total on
        its own -- not merely total given the normalisation above it."""
        assert is_multipart({'CONTENT_TYPE': 12345}) is False

    def test_non_str_content_length_is_normalised_in_place(self, app):
        middleware = BodyLimitMiddleware(lambda environ, sr: [], app)
        environ = self._environ(CONTENT_LENGTH=17)
        middleware(environ, lambda *a, **k: None)
        assert environ['CONTENT_LENGTH'] == '17'

    def test_non_str_content_type_is_normalised_in_place(self, app):
        """Measured without it: `AttributeError: 'int' object has no attribute
        'partition'` raised from inside `werkzeug.http.parse_options_header`, as
        a 500. The forced `get_data(parse_form_data=True)` widened that from
        views that touch the form to every route in the app."""
        middleware = BodyLimitMiddleware(lambda environ, sr: [], app)
        environ = self._environ(CONTENT_TYPE=12345)
        middleware(environ, lambda *a, **k: None)
        assert environ['CONTENT_TYPE'] == '12345'

    def test_an_environ_with_no_wsgi_input_passes_through_untouched(self, app):
        """PEP 3333 mandates the key, but this middleware's docstring claims
        totality for ANY environ, and a `KeyError` here is a bare 500 with no
        error handler involved. Measured on the reverted iteration: `KeyError:
        'wsgi.input'`."""
        seen = {}

        def _downstream(environ, start_response):
            seen['environ'] = environ
            return [b'ok']

        middleware = BodyLimitMiddleware(_downstream, app)
        environ = self._environ()
        del environ['wsgi.input']

        assert middleware(environ, lambda *a, **k: None) == [b'ok']
        assert 'wsgi.input' not in seen['environ']


@pytest.mark.unit
class TestConfigValidation:
    """`validate_limits` hard-fails only on incoherent values. The service-file
    floors are a warning: the ceiling is a two-way knob, and refusing to boot
    below 20 MiB would turn a security control into a floor on exposure."""

    class _Recorder:
        def __init__(self):
            self.warnings = []

        def warning(self, message, *args):
            self.warnings.append(message % args if args else message)

    def _config(self, **overrides):
        base = {'MAX_REQUEST_BODY_BYTES': 1024, 'MAX_UPLOAD_BODY_BYTES': 4096}
        base.update(overrides)
        return base

    @pytest.mark.parametrize('name', ['MAX_REQUEST_BODY_BYTES', 'MAX_UPLOAD_BODY_BYTES'])
    def test_missing_limit_raises_configuration_error_naming_the_key(self, name):
        with pytest.raises(ConfigurationError) as excinfo:
            validate_limits(self._config(**{name: None}), self._Recorder())
        assert excinfo.value.config_key == name

    @pytest.mark.parametrize('bad', ['1048576', 1.5, True])
    def test_non_integer_limit_raises_configuration_error(self, bad):
        with pytest.raises(ConfigurationError) as excinfo:
            validate_limits(self._config(MAX_REQUEST_BODY_BYTES=bad), self._Recorder())
        assert excinfo.value.config_key == 'MAX_REQUEST_BODY_BYTES'

    @pytest.mark.parametrize('bad', [0, -1])
    def test_limit_below_one_byte_raises_configuration_error(self, bad):
        with pytest.raises(ConfigurationError) as excinfo:
            validate_limits(self._config(MAX_REQUEST_BODY_BYTES=bad), self._Recorder())
        assert excinfo.value.config_key == 'MAX_REQUEST_BODY_BYTES'

    @pytest.mark.parametrize('ceiling', [1023, 512, 1])
    def test_upload_ceiling_below_the_global_limit_raises(self, ceiling):
        with pytest.raises(ConfigurationError) as excinfo:
            validate_limits(self._config(MAX_UPLOAD_BODY_BYTES=ceiling),
                            self._Recorder())
        assert excinfo.value.config_key == 'MAX_UPLOAD_BODY_BYTES'

    def test_an_upload_ceiling_EQUAL_to_the_global_limit_is_accepted(self):
        """`<`, not `<=`. Equality is coherent -- the upload endpoints simply
        get the same cap as everything else -- and it is the strictest uniform
        posture an operator can ask for. Refusing to boot on it made the
        simplest safe configuration inexpressible."""
        validate_limits(self._config(MAX_REQUEST_BODY_BYTES=4096,
                                     MAX_UPLOAD_BODY_BYTES=4096),
                        self._Recorder())

    def test_an_equal_pair_of_limits_boots_a_real_app(self, test_storage):
        class UniformConfig(TestConfig):
            MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024
            MAX_UPLOAD_BODY_BYTES = 2 * 1024 * 1024

        built = create_app(UniformConfig, storage_backend=test_storage)
        assert built.config['MAX_UPLOAD_BODY_BYTES'] == 2 * 1024 * 1024

    @pytest.mark.parametrize('name', ['MAX_REQUEST_BODY_BYTES',
                                      'MAX_UPLOAD_BODY_BYTES'])
    def test_an_implausibly_large_limit_raises_configuration_error(self, name):
        """A limit is an ALLOCATION bound now, not just a policy number. One
        mistyped digit -- 251658240 for 25165824 -- otherwise boots perfectly
        cleanly while effectively removing the bound, and nothing downstream
        would ever notice."""
        oversized = MAX_SANE_LIMIT_BYTES + 1
        config = self._config(MAX_REQUEST_BODY_BYTES=1024,
                              MAX_UPLOAD_BODY_BYTES=4096)
        config[name] = oversized
        with pytest.raises(ConfigurationError) as excinfo:
            validate_limits(config, self._Recorder())
        assert excinfo.value.config_key == name
        assert str(MAX_SANE_LIMIT_BYTES) in str(excinfo.value)

    def test_a_limit_exactly_at_the_sanity_ceiling_is_accepted(self):
        """Control: the bound is an upper limit, not an exclusive one, so the
        rejection above cannot be passing for an off-by-one reason."""
        validate_limits(self._config(MAX_REQUEST_BODY_BYTES=MAX_SANE_LIMIT_BYTES,
                                     MAX_UPLOAD_BODY_BYTES=MAX_SANE_LIMIT_BYTES),
                        self._Recorder())

    def test_the_shipped_defaults_are_inside_the_sanity_ceiling(self, app):
        assert app.config['MAX_UPLOAD_BODY_BYTES'] <= MAX_SANE_LIMIT_BYTES

    def test_create_app_raises_when_the_upload_ceiling_is_not_above_the_global_limit(
            self, test_storage):
        class BadConfig(TestConfig):
            MAX_REQUEST_BODY_BYTES = 4 * 1024 * 1024
            MAX_UPLOAD_BODY_BYTES = 1 * 1024 * 1024

        with pytest.raises(ConfigurationError):
            create_app(BadConfig, storage_backend=test_storage)

    def test_ceiling_below_both_service_floors_warns_naming_every_floor(self):
        from app.photo_service import PhotoService
        from app.mariadb_catalog_service import ATTACHMENT_MAX_SIZE

        recorder = self._Recorder()
        validate_limits(self._config(MAX_REQUEST_BODY_BYTES=1024,
                                     MAX_UPLOAD_BODY_BYTES=4096), recorder)

        assert len(recorder.warnings) == 1
        message = recorder.warnings[0]
        # Every breached floor, not just the first: the floors are unordered, so
        # naming one leaves the operator to rediscover the rest one restart at a
        # time.
        assert 'PhotoService.MAX_FILE_SIZE' in message
        assert str(PhotoService.MAX_FILE_SIZE) in message
        assert 'ATTACHMENT_MAX_SIZE' in message
        assert str(ATTACHMENT_MAX_SIZE) in message

    def test_ceiling_between_the_two_floors_warns_about_only_the_breached_one(self):
        """"Between" means clearing the lower floor's WIRE size, not its file
        size. `ATTACHMENT_MAX_SIZE + 1` used to qualify; it no longer does,
        because a 16777215-byte attachment posts as rather more than 16777216
        bytes once multipart framing is counted, so that ceiling genuinely
        breaches both floors and warning about both is the correct answer.
        """
        from app.photo_service import PhotoService
        from app.mariadb_catalog_service import ATTACHMENT_MAX_SIZE
        from app.request_limits import _MULTIPART_FRAMING_ALLOWANCE

        between = ATTACHMENT_MAX_SIZE + _MULTIPART_FRAMING_ALLOWANCE
        assert between < PhotoService.MAX_FILE_SIZE

        recorder = self._Recorder()
        validate_limits(self._config(MAX_REQUEST_BODY_BYTES=1024,
                                     MAX_UPLOAD_BODY_BYTES=between), recorder)

        assert len(recorder.warnings) == 1
        assert 'PhotoService.MAX_FILE_SIZE' in recorder.warnings[0]
        assert 'ATTACHMENT_MAX_SIZE' not in recorder.warnings[0]

    def test_ceiling_below_the_service_floors_still_boots(self, test_storage):
        """A deployer must be able to choose a stricter posture than 20 MiB on
        the unauthenticated, `@csrf.exempt` photo endpoint."""
        class StrictConfig(TestConfig):
            MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024
            MAX_UPLOAD_BODY_BYTES = 2 * 1024 * 1024

        app = create_app(StrictConfig, storage_backend=test_storage)
        assert app.config['MAX_UPLOAD_BODY_BYTES'] == 2 * 1024 * 1024

    def test_breached_floor_warning_reaches_the_json_log_pipeline_after_create_app(
            self, test_storage, capsys):
        """`setup_logging` calls `app.logger.handlers.clear()` AND removes every
        root handler, so a record emitted before it reaches neither the
        structured JSON pipeline operators are told to aggregate nor pytest's
        `caplog` (which is why this reads the captured stream instead).

        Emitting the warning through the CONFIGURED handlers is the assertion:
        the JSON envelope is only produced by the formatter `setup_logging`
        installs, so a record that arrived before `setup_logging` ran would
        appear in Flask's default plain-text format and fail this test. Calling
        `validate_limits` directly cannot see that ordering at all."""
        class StrictConfig(TestConfig):
            MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024
            MAX_UPLOAD_BODY_BYTES = 2 * 1024 * 1024

        capsys.readouterr()          # discard anything logged before this point
        create_app(StrictConfig, storage_backend=test_storage)

        warnings = _json_log_warnings(capsys.readouterr())
        assert any('MAX_UPLOAD_BODY_BYTES' in message
                   and 'PhotoService.MAX_FILE_SIZE' in message
                   for message in warnings), warnings

    def test_shipped_defaults_log_no_warning_at_all(self, test_storage, capsys):
        """A warning that fires on every boot of an unmodified deployment is
        noise, and it trains operators to filter the channel that carries the
        mis-set-ceiling diagnostic. An earlier iteration shipped exactly that
        (MAX_REQUEST_BODY_BYTES 1048576 > MAX_FORM_MEMORY_SIZE 500000)."""
        capsys.readouterr()
        create_app(TestConfig, storage_backend=test_storage)

        assert _json_log_warnings(capsys.readouterr()) == []

    def test_service_floor_gate_matches_the_real_service_constants(self):
        """`_LARGEST_SERVICE_FILE_LIMIT` is a duplicated literal used as a cheap
        gate so `validate_limits` need not import PIL/PyMuPDF/the ORM on the
        shipped defaults. If a service raises its own limit above this value, a
        real breach would go unwarned."""
        from app.photo_service import PhotoService
        from app.mariadb_catalog_service import ATTACHMENT_MAX_SIZE

        assert _LARGEST_SERVICE_FILE_LIMIT == max(PhotoService.MAX_FILE_SIZE,
                                                  ATTACHMENT_MAX_SIZE)


@pytest.mark.unit
class TestEnvOverrides:
    """`config._bytes_from_env` is the testable seam for env overrides. It
    exists so these cases need neither `importlib.reload(config)` -- which
    rebinds the `Config` class object captured by `TestConfig` and by every
    caller -- nor a hardcoded byte count."""

    def test_a_plain_digit_value_overrides_the_default(self, monkeypatch):
        monkeypatch.setenv('MAX_REQUEST_BODY_BYTES', '2048')
        assert config_module._bytes_from_env('MAX_REQUEST_BODY_BYTES', 999) == 2048

    def test_an_unset_variable_takes_the_default(self, monkeypatch):
        monkeypatch.delenv('MAX_REQUEST_BODY_BYTES', raising=False)
        assert config_module._bytes_from_env('MAX_REQUEST_BODY_BYTES', 999) == 999

    @pytest.mark.parametrize('blank', ['', '   '])
    def test_a_blank_value_reads_as_unset_and_takes_the_default(self, monkeypatch, blank):
        """A stray blank line in `.env` must not be a hard failure; this matches
        the `os.environ.get(...) or default` idiom used elsewhere in config.py."""
        monkeypatch.setenv('MAX_REQUEST_BODY_BYTES', blank)
        assert config_module._bytes_from_env('MAX_REQUEST_BODY_BYTES', 999) == 999

    @pytest.mark.parametrize('surrounded', ['1024 ', ' 1024', '  1024\t',
                                            '\n1024\n'])
    def test_surrounding_whitespace_is_stripped_rather_than_fatal(
            self, monkeypatch, surrounded):
        """`MAX_REQUEST_BODY_BYTES=1024 ` with one trailing space is the
        commonest hand-edited `.env` artifact there is. Refusing to boot on it
        while treating an all-whitespace value as *absent* is incoherent: the
        same character was fatal in one position and ignored in the other."""
        monkeypatch.setenv('MAX_REQUEST_BODY_BYTES', surrounded)
        assert config_module._bytes_from_env('MAX_REQUEST_BODY_BYTES', 999) == 1024

    @pytest.mark.parametrize('bad', ['1MB', '+1024', '1_048_576', '10 24', '-5',
                                     '1.5', '١٢'])
    def test_a_non_plain_digit_value_raises_configuration_error_naming_the_variable(
            self, monkeypatch, bad):
        """`1MB` is the one malformed value an operator actually writes. `+1024`
        and `1_048_576` are accepted by `int()` and promised against by the
        helper's own docstring; the last is Arabic-Indic digits, which `int()`
        also accepts."""
        monkeypatch.setenv('MAX_REQUEST_BODY_BYTES', bad)
        with pytest.raises(ConfigurationError) as excinfo:
            config_module._bytes_from_env('MAX_REQUEST_BODY_BYTES', 999)
        assert excinfo.value.config_key == 'MAX_REQUEST_BODY_BYTES'
        assert 'MAX_REQUEST_BODY_BYTES' in str(excinfo.value)

    def test_an_absurdly_long_digit_string_raises_configuration_error_not_valueerror(
            self, monkeypatch):
        """CPython caps integer-string conversion at 4300 digits, so the `int()`
        call inside the helper raises `ValueError` for an all-digits value that
        passes the grammar check."""
        monkeypatch.setenv('MAX_UPLOAD_BODY_BYTES', '9' * 5000)
        with pytest.raises(ConfigurationError) as excinfo:
            config_module._bytes_from_env('MAX_UPLOAD_BODY_BYTES', 999)
        assert excinfo.value.config_key == 'MAX_UPLOAD_BODY_BYTES'

    def test_test_config_inherits_both_limits_unchanged(self):
        """`TestConfig` must not override the limits, so the suite exercises the
        real bound rather than a test-only one."""
        assert TestConfig.MAX_REQUEST_BODY_BYTES == config_module.Config.MAX_REQUEST_BODY_BYTES
        assert TestConfig.MAX_UPLOAD_BODY_BYTES == config_module.Config.MAX_UPLOAD_BODY_BYTES

    def test_app_config_carries_the_config_class_values(self, app):
        assert app.config['MAX_REQUEST_BODY_BYTES'] == TestConfig.MAX_REQUEST_BODY_BYTES
        assert app.config['MAX_UPLOAD_BODY_BYTES'] == TestConfig.MAX_UPLOAD_BODY_BYTES


@pytest.mark.unit
class TestDocumentedDefaults:
    """The shipped 1 MiB / 24 MiB defaults, and the literals the two `.env`
    templates promise.

    Read from the SOURCE, not from a live `Config`: both variables are
    documented as overridable, so a developer whose `.env` sets them would
    otherwise see a red suite for no reason. And the expected value is written
    out here rather than passed in as an argument -- an earlier iteration's
    defaults test took its expectation as a parameter and could not fail.
    """

    ONE_MIB = 1048576
    TWENTY_FOUR_MIB = 25165824

    def _shipped_default(self, name):
        tree = ast.parse((REPO_ROOT / 'config.py').read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == '_bytes_from_env'
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == name):
                # The defaults are written as `1 * 1024 * 1024`, which
                # `literal_eval` rejects; this evaluates the arithmetic without
                # importing config or touching the environment.
                return eval(compile(ast.Expression(node.args[1]), '<default>', 'eval'),
                            {'__builtins__': {}}, {})
        raise AssertionError(f'no _bytes_from_env call for {name} in config.py')

    def test_global_body_limit_default_is_one_mebibyte(self):
        assert self._shipped_default('MAX_REQUEST_BODY_BYTES') == self.ONE_MIB

    def test_upload_ceiling_default_is_twenty_four_mebibytes(self):
        assert self._shipped_default('MAX_UPLOAD_BODY_BYTES') == self.TWENTY_FOUR_MIB

    def test_upload_ceiling_default_clears_both_service_file_limits(self):
        """24 MiB rather than 20: a body carrying a file at
        `PhotoService.MAX_FILE_SIZE` is larger than 20 MiB on the wire once
        multipart boundaries and part headers are counted."""
        from app.photo_service import PhotoService
        from app.mariadb_catalog_service import ATTACHMENT_MAX_SIZE

        ceiling = self._shipped_default('MAX_UPLOAD_BODY_BYTES')
        assert ceiling > PhotoService.MAX_FILE_SIZE
        assert ceiling > ATTACHMENT_MAX_SIZE

    @pytest.mark.parametrize('doc_path', ['.env.example', 'docs/deployment-guide.md'])
    def test_env_templates_document_both_variables_with_the_shipped_defaults(
            self, doc_path):
        text = (REPO_ROOT / doc_path).read_text()
        assert f'MAX_REQUEST_BODY_BYTES={self.ONE_MIB}' in text
        assert f'MAX_UPLOAD_BODY_BYTES={self.TWENTY_FOUR_MIB}' in text

    @pytest.mark.parametrize('doc_path', ['.env.example', 'docs/deployment-guide.md'])
    def test_env_template_value_lines_carry_no_trailing_comment(self, doc_path):
        """systemd `EnvironmentFile=` and `docker --env-file` do not strip a
        trailing `#` comment; the whole rest of the line becomes part of the
        value."""
        for line in (REPO_ROOT / doc_path).read_text().splitlines():
            if line.startswith(('MAX_REQUEST_BODY_BYTES=', 'MAX_UPLOAD_BODY_BYTES=')):
                assert '#' not in line, line

    @pytest.mark.parametrize('doc_path', ['.env.example', 'docs/deployment-guide.md'])
    def test_env_templates_say_which_limit_governs_which_kind_of_body(self, doc_path):
        """Both templates used to promise 1 MiB for "JSON/form" traffic while
        Flask's untouched 500 KB `MAX_FORM_MEMORY_SIZE` was the real ceiling for
        a form body -- measured, a 600 KB urlencoded POST is a 413 under a
        documented 1 MiB limit, and raising the variable does not move it. The
        templates must name the limit that actually governs each kind of body,
        including the one that is NOT set here."""
        text = (REPO_ROOT / doc_path).read_text()
        assert 'MAX_FORM_MEMORY_SIZE' in text
        # The upload ceiling is conditional on the content type, and saying so
        # is the difference between a documented control and a surprise.
        assert 'multipart/form-data' in text
        # The retired, wrong claim.
        assert 'JSON/form' not in text

    @pytest.mark.parametrize('doc_path', ['.env.example', 'docs/deployment-guide.md'])
    def test_env_templates_do_not_carry_the_retired_411_guidance(self, doc_path):
        """Chunked requests are now bounded like any other, so the previous
        draft's 411 / `proxy_request_buffering off` advice is obsolete and
        actively misleading."""
        text = (REPO_ROOT / doc_path).read_text()
        assert 'proxy_request_buffering' not in text
        assert '411' not in text
        assert 'Length Required' not in text


@pytest.mark.unit
class TestFactoryWiring:
    """The factory order is load-bearing; see `create_app`'s own comment."""

    def test_body_limit_hook_is_registered_before_the_csrf_hook(self, app):
        names = [f.__name__ for f in app.before_request_funcs[None]]
        assert 'enforce_request_body_limit' in names
        assert 'csrf_protect' in names
        assert names.index('enforce_request_body_limit') < names.index('csrf_protect')

    def test_wsgi_app_is_wrapped_by_the_body_limit_middleware(self, app):
        assert isinstance(app.wsgi_app, BodyLimitMiddleware)


@pytest.mark.unit
class TestConfigurationErrorHierarchy:
    """`ConfigurationError` is defined in `config.py` -- a leaf module -- and
    adopted by `app/exceptions.py`, rather than the other way round.

    That direction is what keeps `config.py` importable from a cold interpreter
    without executing `app/__init__.py`, which in turn is what lets the factory
    take `Config` as a plain default argument. The relationship is pinned here
    because it is load-bearing in both directions and easy to "tidy" away.
    """

    def test_the_app_side_error_subclasses_the_leaf_one(self):
        from app.exceptions import ConfigurationError as AppConfigurationError

        assert issubclass(AppConfigurationError, ConfigurationError)
        assert AppConfigurationError is not ConfigurationError

    def test_the_app_side_error_keeps_its_place_in_the_app_hierarchy(self):
        """`app/error_handlers.py` dispatches on
        `isinstance(error, WorkshopInventoryError)` to read `.code`/`.details`,
        so the leaf base must be added to that hierarchy, not substituted for
        it."""
        from app.exceptions import (ConfigurationError as AppConfigurationError,
                                    WorkshopInventoryError)

        assert issubclass(AppConfigurationError, WorkshopInventoryError)

    def test_both_classes_carry_the_same_attribute_surface(self):
        leaf = ConfigurationError('bad', config_key='MAX_REQUEST_BODY_BYTES')
        assert leaf.config_key == 'MAX_REQUEST_BODY_BYTES'
        assert leaf.message == 'bad'

        from app.exceptions import ConfigurationError as AppConfigurationError

        app_side = AppConfigurationError('bad', config_key='MAX_REQUEST_BODY_BYTES')
        assert app_side.config_key == 'MAX_REQUEST_BODY_BYTES'
        assert app_side.message == 'bad'
        assert app_side.code == 'CONFIGURATION_ERROR'
        assert app_side.details['config_key'] == 'MAX_REQUEST_BODY_BYTES'

    def test_catching_the_leaf_class_catches_a_startup_validation_failure(self):
        """`validate_limits` raises the app-side class; a caller that catches
        the leaf one -- the name this module imports -- must still see it."""
        with pytest.raises(ConfigurationError):
            validate_limits({'MAX_REQUEST_BODY_BYTES': 4096,
                             'MAX_UPLOAD_BODY_BYTES': 1024}, logging.getLogger('probe'))

    def test_the_mro_is_exactly_the_documented_chain(self):
        """Pin the ORDER, not just the ancestry. Everything below depends on
        `WorkshopInventoryError` sitting between the leaf and the subclass."""
        from app.exceptions import (ConfigurationError as AppConfigurationError,
                                    WorkshopInventoryError)

        assert AppConfigurationError.__mro__[:4] == (
            AppConfigurationError, WorkshopInventoryError, ConfigurationError,
            Exception)

    def test_the_cooperative_init_chain_actually_reaches_the_leaf(self):
        """The two-base MRO used to work only by accidental signature
        compatibility: `WorkshopInventoryError.__init__`'s
        `super().__init__(message)` lands on the LEAF's `__init__`, which nobody
        wrote it to do. Both bases are now initialised explicitly by name -- and
        this pins that the hop still happens and still carries the message, so
        a future change to either signature fails here rather than silently."""
        from app.exceptions import ConfigurationError as AppConfigurationError

        seen = []
        original = ConfigurationError.__init__

        def _spy(self, message, config_key=None):
            seen.append((message, config_key))
            return original(self, message, config_key=config_key)

        ConfigurationError.__init__ = _spy
        try:
            error = AppConfigurationError('boom', config_key='MAX_UPLOAD_BODY_BYTES')
        finally:
            ConfigurationError.__init__ = original

        # Twice: once through WorkshopInventoryError's cooperative super() call
        # (which cannot pass `config_key`), once from the explicit call.
        assert seen == [('boom', None), ('boom', 'MAX_UPLOAD_BODY_BYTES')], seen
        # The explicit call is what makes the final state right.
        assert error.config_key == 'MAX_UPLOAD_BODY_BYTES'
        assert error.message == 'boom'
        assert error.code == 'CONFIGURATION_ERROR'

    @pytest.mark.parametrize('which', ['leaf', 'app_side'])
    def test_either_class_raised_in_a_request_context_is_handled_not_a_500(
            self, test_storage, which):
        """A leaf raised inside a request used to be an unhandled 500: only the
        app-side subclass had an `errorhandler`, so a catchable
        configuration-error class sat outside the dispatch its own docstring
        documents. Both are registered now."""
        from app.exceptions import ConfigurationError as AppConfigurationError

        cls = ConfigurationError if which == 'leaf' else AppConfigurationError
        probe_app = create_app(TestConfig, storage_backend=test_storage)

        @probe_app.route('/__raises_config_error__')
        def _raises():
            raise cls('bad limit', config_key='MAX_REQUEST_BODY_BYTES')

        resp = probe_app.test_client().get('/__raises_config_error__')
        # The registered handler flashes and redirects for the HTML branch; the
        # assertion that matters is that a HANDLER ran at all rather than the
        # exception escaping as an unhandled 500.
        assert resp.status_code == 302, resp.data[:300]
        assert b'Traceback' not in resp.data


@pytest.mark.unit
class TestColdInterpreterImports:
    """`config.py` defines `ConfigurationError` ITSELF and imports nothing from
    the `app` package; `app/exceptions.py` imports it from there, and
    `app/__init__.py` imports `config.Config` at module scope.

    That is the direction this class exists to enforce, and the previous
    docstring here described the reverse -- the arrangement that forces a
    lazy-import workaround in the factory. Both import orders must work from a
    cold interpreter, which only a subprocess can prove: inside pytest both
    modules are already in `sys.modules` and any cycle is invisible.
    """

    def _run(self, source, env=None):
        return subprocess.run(
            [sys.executable, '-c', textwrap.dedent(source)],
            cwd=REPO_ROOT, capture_output=True, text=True,
            env={**os.environ, **(env or {})})

    def test_importing_config_first_works_in_a_fresh_interpreter(self):
        result = self._run("""
            import config
            assert isinstance(config.Config.MAX_REQUEST_BODY_BYTES, int)
            assert isinstance(config.Config.MAX_UPLOAD_BODY_BYTES, int)
            print('ok')
        """)
        assert result.returncode == 0, result.stderr
        assert 'ok' in result.stdout

    def test_importing_config_does_not_execute_the_app_package(self):
        """`config.py` is a LEAF: it defines `ConfigurationError` itself instead
        of importing one from `app.exceptions`, so a cold `import config` never
        runs `app/__init__.py`. That is precisely what lets `app/__init__.py`
        say a plain module-scope `from config import Config` again, with no
        lazy-import workaround inside the factory."""
        result = self._run("""
            import sys
            import config
            print('APP_MODULES=' + repr(sorted(
                m for m in sys.modules if m == 'app' or m.startswith('app.'))))
        """)
        assert result.returncode == 0, result.stderr
        assert 'APP_MODULES=[]' in result.stdout

    def test_config_module_imports_nothing_from_the_app_package(self):
        """The structural half of the test above: prose in a comment does not
        stop someone re-adding `from app.exceptions import ConfigurationError`."""
        tree = ast.parse((REPO_ROOT / 'config.py').read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or '')
        offenders = sorted(name for name in imported
                           if name == 'app' or name.startswith('app.'))
        assert offenders == []

    def test_create_app_takes_config_as_a_plain_default_argument(self):
        """The lazy-import workaround is gone, and must stay gone: it existed
        only because `config.py` used to import from the `app` package."""
        import inspect

        signature = inspect.signature(create_app)
        assert signature.parameters['config_class'].default is config_module.Config
        # The blueprint imports inside the factory are deliberate and unrelated;
        # only a deferred `config` import would be the workaround coming back.
        assert 'from config import' not in inspect.getsource(create_app)

    def test_importing_app_first_works_in_a_fresh_interpreter(self):
        result = self._run("""
            import app
            from config import Config
            assert callable(app.create_app)
            assert isinstance(Config.MAX_REQUEST_BODY_BYTES, int)
            print('ok')
        """)
        assert result.returncode == 0, result.stderr
        assert 'ok' in result.stdout

    def test_a_malformed_env_value_raises_configuration_error_on_a_cold_import(self):
        """`MAX_REQUEST_BODY_BYTES=1MB` must name the variable, not surface as a
        bare `ValueError` traceback out of the `class Config` body."""
        result = self._run("""
            import config
        """, env={'MAX_REQUEST_BODY_BYTES': '1MB'})
        assert result.returncode != 0
        assert 'ConfigurationError' in result.stderr
        assert 'MAX_REQUEST_BODY_BYTES' in result.stderr

    def test_validating_limits_imports_neither_pil_nor_pymupdf_nor_the_services(self):
        """`validate_limits` runs inside `create_app`, and `app/main/routes.py`
        has thirteen in-function `photo_service` imports placed specifically to
        keep PIL and PyMuPDF out of startup. Comparing two integers must not
        defeat all thirteen."""
        result = self._run("""
            import sys
            from app.request_limits import validate_limits
            import logging
            validate_limits({'MAX_REQUEST_BODY_BYTES': 1048576,
                             'MAX_UPLOAD_BODY_BYTES': 25165824},
                            logging.getLogger('probe'))
            loaded = [m for m in ('PIL', 'fitz', 'pymupdf',
                                  'app.photo_service', 'app.mariadb_catalog_service')
                      if m in sys.modules]
            print('LOADED=' + repr(loaded))
        """)
        assert result.returncode == 0, result.stderr
        assert 'LOADED=[]' in result.stdout

    def test_create_app_on_shipped_defaults_imports_neither_pil_nor_pymupdf(self):
        result = self._run("""
            import sys
            from app import create_app
            from tests.test_config import TestConfig
            create_app(TestConfig)
            loaded = [m for m in ('PIL', 'fitz', 'pymupdf') if m in sys.modules]
            print('LOADED=' + repr(loaded))
        """)
        assert result.returncode == 0, result.stderr
        assert 'LOADED=[]' in result.stdout


# --------------------------------------------------------------------------
# ast helpers for the structural pins above
# --------------------------------------------------------------------------

def _executable_source(relative_path, function_name):
    """The named function's source with its docstring and comments stripped.

    The 413 handler's docstring deliberately *names* `Referer`, `urlsplit` and
    the redirect it replaced -- that history is the point of the comment. Only
    the executable code may be searched for them.
    """
    tree = ast.parse((REPO_ROOT / relative_path).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]
            return '\n'.join(ast.unparse(statement) for statement in body)
    raise AssertionError(f'{function_name} not found in {relative_path}')


def _route_decorated_functions(tree):
    """Every function in `tree` carrying a `bp.route`/`bp.get`/... decorator."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            call = decorator.func if isinstance(decorator, ast.Call) else decorator
            if (isinstance(call, ast.Attribute)
                    and isinstance(call.value, ast.Name)
                    and call.value.id == 'bp'
                    and call.attr in ('route', 'get', 'post', 'put',
                                      'patch', 'delete')):
                yield node
                break


def _calls_function(function_name):
    """Predicate: does this function call `function_name` by bare name?"""
    def predicate(node):
        return any(isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                   and sub.func.id == function_name
                   for sub in ast.walk(node))
    return predicate


def _reads_request_files(node):
    """Predicate: does this function read `request.files`?"""
    return any(isinstance(sub, ast.Attribute) and sub.attr == 'files'
               and isinstance(sub.value, ast.Name) and sub.value.id == 'request'
               for sub in ast.walk(node))


def _views_reaching_in_source(source, predicate):
    """Route-decorated views in `source` that satisfy `predicate` DIRECTLY or
    through any chain of module-level helpers in the same file.

    Indirection is the point. A view that calls `_save_upload(request)` which
    touches `request.files`, or one that returns `_json_error(...)` which builds
    its envelope with `_catalog_json_error`, is exactly as much an upload or
    catalog route as one that does it inline -- and a guard that only looked for
    the direct call would wave both through.
    """
    tree = ast.parse(source)
    functions = {node.name: node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef)}
    matches = {name: bool(predicate(node)) for name, node in functions.items()}
    callees = {
        name: {call.func.id for call in ast.walk(node)
               if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)}
        for name, node in functions.items()
    }

    # Fixpoint: keep promoting "calls something that matches" to "matches" until
    # nothing changes, so a chain of any depth is followed.
    changed = True
    while changed:
        changed = False
        for name in functions:
            if not matches[name] and any(matches.get(callee)
                                         for callee in callees[name]):
                matches[name] = changed = True

    return {view.name for view in _route_decorated_functions(tree)
            if matches.get(view.name)}


def _views_reaching(relative_path, predicate):
    return _views_reaching_in_source((REPO_ROOT / relative_path).read_text(),
                                     predicate)


def _qualified_views_reaching(predicate):
    """`blueprint.view` names, across EVERY module that carries blueprint views.

    `app/admin/routes.py` is scanned as well as `app/main/routes.py`: a new
    upload or catalog route registered on the admin blueprint would otherwise
    pass both guards in silence.
    """
    found = set()
    for relative_path, blueprint in VIEW_MODULES.items():
        found |= {f'{blueprint}.{name}'
                  for name in _views_reaching(relative_path, predicate)}
    return found


@pytest.mark.unit
class TestReviewPassThreePatches:
    """Regression tests for the four defects found in review pass 3.

    Each was measured against the working tree before the fix; each assertion
    below fails if its guard is removed.
    """

    def test_a_mid_body_client_reset_is_not_a_500_on_any_route(self, client):
        """Under gunicorn the `CappedStream` is handed back UNWRAPPED (that is
        the `MAX_CONTENT_LENGTH is None` invariant), so no `LimitedStream` is in
        the chain to convert a socket error into `ClientDisconnected` -- the
        reader raises a bare `ConnectionResetError`. Catching only
        `ClientDisconnected` therefore left a routine client hang-up as an
        unhandled 500 plus an ERROR log on EVERY route, including ones that
        never touch the body.
        """
        class _Resetting(io.RawIOBase):
            def readable(self):
                return True

            def read(self, size=-1):
                raise ConnectionResetError(104, 'Connection reset by peer')

            def readline(self, size=-1):
                raise ConnectionResetError(104, 'Connection reset by peer')

        resp = client.get('/', environ_overrides={
            'CONTENT_LENGTH': '', 'wsgi.input': _Resetting(), **_TERMINATED,
        })
        assert resp.status_code == 200

    def test_an_ajax_json_consumer_outside_api_still_gets_a_json_413(self, app, client):
        """`main.inventory_add` posts a FormData by fetch() and calls
        `response.json()` on the result, but its rule is `/inventory/add` -- no
        `/api/` in it and the request is not `is_json`. Rule-matching alone
        handed it an HTML page, so the client's `response.json()` threw and the
        message was lost entirely.

        SENDS WHAT THE REAL CLIENT SENDS. `app/static/js/inventory-add.js:702`
        is `fetch(this.form.action, {method: 'POST', body: formData})` -- no
        headers object at all, so no `X-Requested-With` and the browser's own
        `Accept: */*`. An earlier version of this test injected
        `X-Requested-With: XMLHttpRequest`, a header nothing in
        `app/static/js/` sets, so it went green against a mechanism while the
        shipped path stayed broken. Adding a header the test name says is
        absent is the exact failure this module's docstring warns about.
        """
        resp = client.post(
            '/inventory/add',
            data=b'x' * (app.config['MAX_REQUEST_BODY_BYTES'] + 4096),
            content_type='multipart/form-data; boundary=x',
            headers={'Accept': '*/*'},
            environ_overrides=dict(_TERMINATED))
        assert resp.status_code == 413
        assert resp.is_json
        assert resp.get_json()['error'] == REQUEST_TOO_LARGE_MESSAGE

    def test_no_client_in_this_repo_sends_the_xhr_marker(self):
        """The guard above cannot be allowed to regress back to header
        sniffing: no JavaScript or template in this repo sets
        `X-Requested-With`, so a branch keyed on it is dead code for every
        caller the app actually has."""
        hits = []
        for path in (REPO_ROOT / 'app' / 'static' / 'js').rglob('*.js'):
            if 'X-Requested-With' in path.read_text(encoding='utf-8'):
                hits.append(str(path))
        assert hits == []

    def test_a_real_browser_navigation_to_the_same_endpoint_gets_html(self, app, client):
        """The other direction, and the reason the Accept vote is scoped to
        `JSON_HTML_HYBRID_ENDPOINTS` rather than applied globally.
        `/inventory/add` also serves an ordinary form submit (quantity 1), which
        is a top-level browser navigation -- answering that with raw JSON in the
        address bar would be its own defect. A navigation's Accept header
        explicitly prefers `text/html`; `fetch()`'s `*/*` does not.
        """
        resp = client.post(
            '/inventory/add',
            data=b'x' * (app.config['MAX_REQUEST_BODY_BYTES'] + 4096),
            content_type='multipart/form-data; boundary=x',
            headers={'Accept': 'text/html,application/xhtml+xml,'
                               'application/xml;q=0.9,*/*;q=0.8'},
            environ_overrides=dict(_TERMINATED))
        assert resp.status_code == 413
        assert not resp.is_json
        assert 'Location' not in resp.headers

    def test_every_hybrid_endpoint_resolves_to_a_real_view(self, app):
        """Same structural guard `UPLOAD_ENDPOINTS` gets: a renamed or deleted
        view must not leave a silently-dead name in the set."""
        assert JSON_HTML_HYBRID_ENDPOINTS <= set(app.view_functions)

    @pytest.mark.parametrize('declared', ['+1048586', '1_048_577'])
    def test_a_length_werkzeug_would_ignore_does_not_cause_a_false_413(
            self, test_storage, declared):
        """`int()` accepts `+50` and `1_0`; Werkzeug's `_plain_int` does not and
        reports such a length as 0, so nothing would ever have read a body on
        the strength of it. Trusting `int()` in the fast path 413'd an 11-byte
        request -- a false rejection, the opposite error from the bypasses this
        module is mostly about.

        Asserted by proving the request REACHED A VIEW, not merely that it was
        not a 413: `!= 413` is satisfied by a 500 too, and this whole module is
        a monument to assertions that were weaker than their names.
        """
        from flask import request

        app = create_app(TestConfig, storage_backend=test_storage)
        seen = {}

        @app.route('/probe-fast-path', methods=['POST'])
        def probe_fast_path():
            seen['body'] = request.get_data()
            return 'reached'

        resp = app.test_client().post(
            '/probe-fast-path', data=b'{"raw":"A"}',
            content_type='application/json',
            environ_overrides={'CONTENT_LENGTH': declared, **_TERMINATED})
        assert resp.status_code == 200
        assert seen['body'] == b'{"raw":"A"}'

    def test_a_bytes_content_type_is_decoded_not_repr_ed(self, app):
        """`str(b'multipart/form-data; boundary=x')` is
        `"b'multipart/form-data; boundary=x'"`, which stops matching -- silently
        dropping a real upload from the 24 MiB ceiling to the 1 MiB limit.
        """
        environ = {
            'REQUEST_METHOD': 'POST',
            'PATH_INFO': '/api/items/JA000001/photos',
            'CONTENT_TYPE': b'multipart/form-data; boundary=x',
            'wsgi.input': io.BytesIO(b''),
            'SERVER_NAME': 'localhost', 'SERVER_PORT': '80',
            'wsgi.url_scheme': 'http',
        }
        BodyLimitMiddleware(lambda e, s: [b''], app)(environ, lambda *a: None)
        assert environ['CONTENT_TYPE'] == 'multipart/form-data; boundary=x'
        assert is_multipart(environ) is True


@pytest.mark.unit
class TestReviewPassFourPatches:
    """Regression tests for the defects found in review pass 4.

    Each was measured against the working tree before the fix; each assertion
    below fails if its guard is removed.
    """

    def test_the_forced_read_survives_an_environ_with_no_wsgi_input(
            self, test_storage):
        """`BodyLimitMiddleware` deliberately passes such an environ through
        untouched, and `TestMiddlewareTotality` pins that -- against a STUB
        downstream, so it never reaches the hook the middleware installs.
        `request.get_data()` then subscripts the same key from inside
        `werkzeug.wsgi.get_input_stream`. Measured end-to-end: 500 with the hook
        installed, 200 without it. The middleware's totality claim is worth
        nothing if the hook it registers breaks on the same environ.
        """
        app = create_app(TestConfig, storage_backend=test_storage)
        wrapped = app.wsgi_app

        def _strip_input(environ, start_response):
            environ.pop('wsgi.input', None)
            return wrapped(environ, start_response)

        app.wsgi_app = _strip_input
        assert app.test_client().get('/health').status_code == 200

    def test_a_ceiling_equal_to_a_service_floor_warns_because_of_framing(
            self, test_storage, capsys):
        """A file of exactly N bytes does not arrive as N bytes: multipart
        framing adds a couple of hundred more. Measured: a 20971520-byte photo
        posts as 20971762 wire bytes, so a ceiling set to exactly
        `PhotoService.MAX_FILE_SIZE` 413s every maximum-size upload -- and the
        old `upload < floor` comparison booted silently, warning about nothing.
        The warning exists precisely to catch a ceiling that breaks legitimate
        uploads, so its boundary has to be the wire size, not the file size.
        """
        from app.photo_service import PhotoService

        class ExactlyTheFloorConfig(TestConfig):
            MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024
            MAX_UPLOAD_BODY_BYTES = PhotoService.MAX_FILE_SIZE

        capsys.readouterr()
        create_app(ExactlyTheFloorConfig, storage_backend=test_storage)

        warnings = _json_log_warnings(capsys.readouterr())
        assert any('PhotoService.MAX_FILE_SIZE' in message
                   for message in warnings), warnings

    def test_the_framing_allowance_covers_a_real_maximum_size_upload(self):
        """Pins the allowance to a MEASURED wire size rather than to a number
        that merely looks generous. If multipart framing ever grew past the
        allowance, the warning boundary would silently go back to being wrong.
        """
        from werkzeug.test import EnvironBuilder
        from app.photo_service import PhotoService
        from app.request_limits import _MULTIPART_FRAMING_ALLOWANCE

        builder = EnvironBuilder(
            method='POST', path='/api/items/JA000001/photos',
            data={'photo': (io.BytesIO(b'x' * PhotoService.MAX_FILE_SIZE),
                            'a-reasonably-long-photo-filename.jpeg')})
        wire_bytes = int(builder.get_environ()['CONTENT_LENGTH'])

        overhead = wire_bytes - PhotoService.MAX_FILE_SIZE
        assert 0 < overhead <= _MULTIPART_FRAMING_ALLOWANCE, overhead

    def test_the_shipped_default_ceiling_still_warns_about_nothing(
            self, test_storage, capsys):
        """The framing allowance must not be large enough to make the shipped
        24 MiB ceiling warn -- an unconditional warning is the noise defect
        `test_shipped_defaults_log_no_warning_at_all` exists to prevent, and
        widening the comparison is exactly how it would come back."""
        capsys.readouterr()
        create_app(TestConfig, storage_backend=test_storage)
        assert _json_log_warnings(capsys.readouterr()) == []

    def test_a_non_multipart_request_never_pays_for_a_route_match(self, app):
        """`_cap_for` can only ever return the raised ceiling for a multipart
        body, so matching the URL map first made every request in the app --
        every static asset, every health check -- pay a full route match (a
        second one; Flask then matches again) to answer a question already
        settled by a header. The cheap half of the conjunction goes first.
        """
        from werkzeug.routing import MapAdapter

        calls = []
        original = MapAdapter.match

        def _counting_match(self, *args, **kwargs):
            calls.append(1)
            return original(self, *args, **kwargs)

        middleware = BodyLimitMiddleware(lambda e, s: [b''], app)
        environ = {
            'REQUEST_METHOD': 'GET', 'PATH_INFO': '/health',
            'wsgi.input': io.BytesIO(b''),
            'SERVER_NAME': 'localhost', 'SERVER_PORT': '80',
            'wsgi.url_scheme': 'http',
        }
        with mock.patch.object(MapAdapter, 'match', _counting_match):
            cap = middleware._cap_for(environ)

        assert calls == []
        assert cap == app.config['MAX_REQUEST_BODY_BYTES']

    def test_the_upload_ceiling_still_needs_the_route_match(self, app):
        """The converse of the test above: the short-circuit must not have
        turned the endpoint check into dead code. A multipart body still has to
        resolve to an upload endpoint to earn the raised ceiling."""
        def _environ(path):
            return {
                'REQUEST_METHOD': 'POST', 'PATH_INFO': path,
                'CONTENT_TYPE': 'multipart/form-data; boundary=x',
                'wsgi.input': io.BytesIO(b''),
                'SERVER_NAME': 'localhost', 'SERVER_PORT': '80',
                'wsgi.url_scheme': 'http',
            }

        middleware = BodyLimitMiddleware(lambda e, s: [b''], app)
        assert middleware._cap_for(_environ('/api/items/JA000001/photos')) == \
            app.config['MAX_UPLOAD_BODY_BYTES']
        assert middleware._cap_for(_environ('/inventory/add')) == \
            app.config['MAX_REQUEST_BODY_BYTES']

    def test_the_middleware_adapter_is_built_the_way_flask_builds_its_own(self):
        """`Flask.create_url_adapter` passes `server_name=config['SERVER_NAME']`.
        The middleware did not, so with `SERVER_NAME` set the two adapters could
        resolve differently -- and the `before_request` fast path reads
        `request.endpoint`, i.e. Flask's answer. The dangerous direction is
        reachable: the hook grants the 24 MiB ceiling and waves a declared
        20 MiB length through, while the stream the middleware installed is
        capped at 1 MiB and raises mid-body.
        """
        source = (REPO_ROOT / 'app' / 'request_limits.py').read_text(
            encoding='utf-8')
        assert 'server_name=self.app.config.get(\'SERVER_NAME\')' in source

    def test_the_hook_reads_its_limits_defensively_like_cap_for_does(self,
                                                                    client):
        """`_cap_for` uses `.get(..., _FALLBACK_CAP_BYTES)` with a five-line
        docstring paragraph explaining that a subscript would turn "unreachable"
        into a `KeyError`. The hook applied the same rule with a subscript, so
        the same unreachable condition was a bare 500 from a `before_request` on
        every route in one copy and handled in the other.
        """
        client.application.config.pop('MAX_REQUEST_BODY_BYTES')
        assert client.get('/health').status_code == 200

    @pytest.mark.parametrize('doc_path', ['.env.example',
                                          'docs/deployment-guide.md'])
    def test_the_documented_attachment_limit_is_the_real_constant(self,
                                                                  doc_path):
        """`ATTACHMENT_MAX_SIZE` is `16 * 1024 * 1024 - 1`. Both templates
        rounded it to "16 MiB", while the startup warning prints the real
        value -- so an operator who tightened the ceiling to exactly 16 MiB from
        the doc got a warning contradicting the document they configured from.
        """
        from app.mariadb_catalog_service import ATTACHMENT_MAX_SIZE

        text = (REPO_ROOT / doc_path).read_text(encoding='utf-8')
        assert str(ATTACHMENT_MAX_SIZE) in text
        assert '16 MiB for an attachment' not in text

    def test_the_two_env_templates_carry_a_byte_identical_block(self):
        """The block is duplicated verbatim across the two files, and
        `TestDocumentedDefaults` pins four properties of it -- leaving the other
        ~55 lines of prose free to drift apart silently. This change refuses a
        second silently-drifting copy for the routing table and for
        `MAX_CONTENT_LENGTH`; the docs get the same treatment.
        """
        def _block(path):
            lines = (REPO_ROOT / path).read_text(encoding='utf-8').splitlines()
            start = next(i for i, line in enumerate(lines)
                         if line.startswith('# Request body size limits'))
            end = next(i for i in range(start, len(lines))
                       if not lines[i].startswith('#'))
            block = lines[start:end]
            assert len(block) > 40, (path, len(block))
            return block

        assert _block('.env.example') == _block('docs/deployment-guide.md')


@pytest.mark.unit
class TestReviewPassFivePatches:
    """Regression tests for the defects found in review pass 5.

    Each was measured against the working tree before the fix; each assertion
    below fails if its guard is removed.
    """

    @pytest.mark.parametrize('headers', [
        {'X-Requested-With': 'XMLHttpRequest'},
        {'Accept': 'application/json, text/plain, */*'},
    ])
    def test_a_request_header_cannot_turn_an_html_page_into_json(
            self, app, client, headers):
        """The 413 handler's own comment says the JSON branch is chosen from
        evidence that is NOT caller-chosen -- and then two caller-chosen limbs
        were live in the expression underneath it:
        `X-Requested-With: XMLHttpRequest` (which the comment itself calls dead
        code, and which no client in this repo sends) and an UNSCOPED
        `accept_mimetypes.best == 'application/json'` (exactly the global Accept
        rule `JSON_HTML_HYBRID_ENDPOINTS`' comment says was rejected on
        purpose).

        Measured before the fix: an oversize `POST /products/edit/1` -- an
        ordinary HTML page -- returned `application/json` for BOTH headers
        below, the second being nothing more exotic than axios' default Accept.
        """
        resp = client.post(
            '/products/edit/1',
            data=b'a=' + b'y' * (app.config['MAX_REQUEST_BODY_BYTES'] + 4096),
            content_type='application/x-www-form-urlencoded',
            headers=headers)
        assert resp.status_code == 413
        assert not resp.is_json
        assert resp.mimetype == 'text/html'
        assert 'Location' not in resp.headers

    def test_a_wsgi_input_of_none_is_not_a_500(self, client):
        """Companion to `test_the_forced_read_survives_an_environ_with_no_wsgi_input`,
        and the same defect one value along. The middleware tests the VALUE
        (`stream = environ.get('wsgi.input'); if stream is None`) and passes such
        an environ through unwrapped; the hook tested the KEY, so a key present
        but `None` sailed past it into `get_data()`.

        Measured before the fix: `AttributeError: 'NoneType' object has no
        attribute 'read'` -- a bare 500 out of a `before_request`, on a route
        that reads no body at all.
        """
        resp = client.get('/health',
                          environ_overrides={'wsgi.input': None, **_TERMINATED})
        assert resp.status_code != 500

    def test_a_read_after_the_cap_was_breached_raises_rather_than_returning_empty(self):
        """`_room()` goes non-positive once the cap is broken, so `wanted` was
        <= 0, the loop never ran, and `read()` returned `b''` -- SILENT
        TRUNCATION, from the one class in this module whose entire purpose is to
        raise instead of truncating. Only reachable if something swallows the
        first rejection, which is precisely what this app's `except Exception`
        views do, so it must answer the same way twice.
        """
        stream = CappedStream(io.BytesIO(b'x' * 100), 10)
        with pytest.raises(RequestEntityTooLarge):
            stream.read()
        with pytest.raises(RequestEntityTooLarge):
            stream.read(1)
        with pytest.raises(RequestEntityTooLarge):
            stream.readline()

    def test_a_form_field_with_no_declared_length_is_parsed_in_full(
            self, test_storage):
        """Pins BOTH columns of the `MAX_FORM_MEMORY_SIZE` row that the two
        `.env` templates document, because the templates got that row wrong
        again: they said that with no `Content-Length` the oversize field "is
        simply not parsed". Measured -- it is parsed IN FULL, all 614400 bytes
        of it, and `MAX_FORM_MEMORY_SIZE` is never consulted, so the only thing
        bounding a form field in the gunicorn column is
        `MAX_REQUEST_BODY_BYTES`.
        """
        from flask import request

        app = create_app(TestConfig, storage_backend=test_storage)

        @app.route('/probe-form-columns', methods=['POST'])
        def probe_form_columns():
            return {'n': len(request.form.get('note', ''))}

        body = b'note=' + b'x' * 614400
        assert len(body) < app.config['MAX_REQUEST_BODY_BYTES']
        assert 614400 > 500000, 'must exceed Flask MAX_FORM_MEMORY_SIZE'
        client = app.test_client()

        no_length = client.post(
            '/probe-form-columns', data=body,
            content_type='application/x-www-form-urlencoded',
            environ_overrides={'CONTENT_LENGTH': '', **_TERMINATED})
        assert no_length.status_code == 200
        assert no_length.get_json()['n'] == 614400

        declared = client.post(
            '/probe-form-columns', data=body,
            content_type='application/x-www-form-urlencoded')
        assert declared.status_code == 413

    @pytest.mark.parametrize('doc_path', ['.env.example', 'docs/deployment-guide.md'])
    def test_the_templates_state_the_form_limit_row_truthfully(self, doc_path):
        """The claim above, pinned in the documents themselves, in both copies.
        """
        text = (REPO_ROOT / doc_path).read_text(encoding='utf-8')
        assert 'is bounded at 1 MiB, NOT at 500 KB' in text
        assert 'simply not' not in text

    def test_a_parser_io_error_is_not_swallowed_as_a_client_disconnect(
            self, client):
        """The disconnect limb caught a BARE `OSError`. The forced
        `parse_form_data=True` runs Werkzeug's multipart parser, which SPOOLS a
        large upload to a temp file -- so `ENOSPC`/`EACCES` from that spool is an
        `OSError` too, and was swallowed as "the client hung up", letting the
        request reach a view holding a silently incomplete `request.files`.

        Narrowed to the socket shapes (`ConnectionError`, `TimeoutError`); the
        companion assertion keeps the pass-3-patch behaviour that a real reset
        is still swallowed on a route that never reads the body.
        """
        import flask

        # Reaches the app's own error handling instead of being silently
        # dropped. `TESTING` propagates it rather than rendering the 500, which
        # is a stronger demonstration than a status code: the hook did not
        # absorb it. Before the fix this was a plain 200.
        with mock.patch.object(flask.Request, 'get_data',
                               side_effect=OSError(28, 'No space left on device')):
            with pytest.raises(OSError):
                client.get('/health')

        with mock.patch.object(flask.Request, 'get_data',
                               side_effect=ConnectionResetError(104, 'reset')):
            assert client.get('/health').status_code == 200

        with mock.patch.object(flask.Request, 'get_data',
                               side_effect=TimeoutError('read timed out')):
            assert client.get('/health').status_code == 200
