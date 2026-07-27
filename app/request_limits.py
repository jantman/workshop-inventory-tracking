"""Transport-level bound on the request body, enforced at the WSGI layer.

The app is unauthenticated and every JSON route is `@csrf.exempt`, so without a
bound here an arbitrarily large body is buffered and parsed in full before any
application-level check can look at it. The per-payload guards
(`MAX_SCAN_LENGTH` in `app/utils/scan_input.py`, `ATTACHMENT_MAX_SIZE`,
`PhotoService.MAX_FILE_SIZE`) all run *after* the bytes are already in memory;
this module is what stops them getting there.

**Why the enforcement is on the stream and not on the headers.** The obvious
implementation — a `before_request` hook that inspects `Content-Length`,
`Transfer-Encoding` and `wsgi.input_terminated` and decides whether Werkzeug is
about to read a body — is a trap, and four consecutive attempts at it were
reverted. The question is genuinely undecidable from headers: gunicorn (the
server named in `wsgi.py`) sets `wsgi.input_terminated` on EVERY request
including every `GET`, Werkzeug parses `Content-Length` with a narrower grammar
than `int()`, and `LimitedStream(..., is_max=True)` TRUNCATES where every reader
assumes it raises. Guessing one way took the app down under gunicorn (every GET
a redirect loop); guessing the other way let oversize bodies through truncated
with a 200.

So this module does not ask the question. It *controls* the stream: it wraps
`environ['wsgi.input']` in a `CappedStream` that raises the moment a read would
carry the running total past the cap. A bodyless `GET` still has one read
*issued* against it by the hook below — it is not exempted, because exempting it
would mean predicting again — but that read returns zero bytes, so the cap is
never approached and the response is byte-identical either way; any body —
chunked, undeclared, or misdeclared —
raises on the read that crosses the cap, whatever the headers claimed.

**Flask's own body-limit config key must stay `None`.** See the block comment
below, which names it. This is the one counterintuitive invariant of the design,
and setting that key silently disables the whole thing.

**Ordering constraint (CSRF).** `init_request_limits(app)` must be called
*before* `csrf.init_app(app)` in the application factory. It is no longer what
makes the rejection work — a capped stream raises wherever the read happens,
including inside `CSRFProtect`'s own `before_request` hook, which parses the
form — but registering first keeps the rejection attributable to this feature
(a clean 413) rather than surfacing as a confusing CSRF failure. It must also
be called *after* `setup_logging(app)`, because `setup_logging` calls
`app.logger.handlers.clear()` and would otherwise discard the startup
validation warning.
"""

from flask import request
from werkzeug.exceptions import ClientDisconnected, RequestEntityTooLarge

from app.exceptions import ConfigurationError

# Endpoints that get the raised ceiling, by BLUEPRINT-QUALIFIED ENDPOINT NAME
# rather than by URL prefix: a URL string match is a second, silently drifting
# copy of the routing table. These are exactly the two views that read
# `request.files`; tests/unit/test_request_limits.py pins both directions of
# that correspondence.
UPLOAD_ENDPOINTS = frozenset({
    'main.product_upload_attachment',
    'main.upload_photo',
})

# The one content type the raised ceiling exists for.
UPLOAD_MIMETYPE = 'multipart/form-data'


def is_multipart(environ):
    """Is this request shaped like a `multipart/form-data` submission?

    Read straight off the environ rather than via `request.mimetype`, because
    the middleware that needs this runs BEFORE routing and outside any request
    context. Total by construction: the middleware normalises a non-`str`
    CONTENT_TYPE first, but this coerces again rather than trusting that,
    because `_cap_for` must not be able to raise.

    A non-empty `boundary` parameter is REQUIRED, not just the mimetype. The
    mimetype alone is one caller-chosen word, so `Content-Type: multipart/
    form-data` on a JSON body would buy the raised ceiling for free; a body
    with no boundary is not parseable as multipart by Werkzeug either, so
    demanding one costs a real upload nothing. Note what this still does NOT
    establish: the header remains caller-supplied, so the honest statement of
    the bound is "the upload ceiling applies to the two upload endpoints for
    anything SHAPED like a multipart body", not "only for real uploads". The
    `config.py` comment says exactly that.
    """
    content_type = environ.get('CONTENT_TYPE') or ''
    if not isinstance(content_type, str):
        content_type = str(content_type)
    # Split the parameters off by hand (`; boundary=...`) rather than calling
    # Werkzeug's parser: this runs on every request including every GET, and a
    # hostile value must not be able to raise out of it.
    mimetype, _, params = content_type.partition(';')
    if mimetype.strip().lower() != UPLOAD_MIMETYPE:
        return False
    for param in params.split(';'):
        name, sep, value = param.partition('=')
        if sep and name.strip().lower() == 'boundary':
            # Quoted boundaries are legal (RFC 2046) and Werkzeug accepts them,
            # so strip the quotes before deciding the value is non-empty -- and
            # strip again afterwards, so `boundary="   "` is the empty boundary
            # it really is rather than three characters of "content".
            return bool(value.strip().strip('"').strip())
    return False

# The largest service-layer file limit (PhotoService.MAX_FILE_SIZE, 20 MiB).
# It is duplicated here as a plain literal, and pinned to the real constants by
# a named test, purely as a CHEAP GATE: reading the real values means importing
# app.photo_service and app.mariadb_catalog_service, which drag in PIL,
# PyMuPDF and the ORM. app/main/routes.py has thirteen in-function
# `photo_service` imports placed specifically to keep those out of startup, and
# `validate_limits` runs inside `create_app`, so importing them here would
# defeat all thirteen in order to compare two integers. Below this value a
# floor *might* be breached and it is worth paying for the real numbers; at or
# above it, none can be, and nothing is imported.
_LARGEST_SERVICE_FILE_LIMIT = 20 * 1024 * 1024

# A file of exactly N bytes does not arrive as N bytes on the wire: multipart
# framing (boundaries, Content-Disposition, the filename, trailers) adds a bit.
# The ceiling therefore has to clear the floor PLUS that framing, or the app
# boots without a warning while 413-ing every maximum-size upload. Measured: a
# 20971520-byte photo posts as 20971762 wire bytes, so a ceiling set to exactly
# PhotoService.MAX_FILE_SIZE is 242 bytes short and warns about nothing. 4 KiB
# is a generous allowance for a long filename and several fields, and it is
# small enough not to make the shipped 24 MiB default warn.
_MULTIPART_FRAMING_ALLOWANCE = 4096

# Cap used if a limit key is somehow absent from `app.config`. Unreachable in a
# booted app -- `validate_limits` refuses to start without both keys -- but
# `_cap_for` promises never to raise, and a `KeyError` out of WSGI middleware is
# a bare 500 with no error handler to catch it. The GLOBAL default is used for
# both, because falling back to the tighter limit is the safe direction.
_FALLBACK_CAP_BYTES = 1 * 1024 * 1024

# No configured limit may exceed this. A limit is an ALLOCATION bound now, not
# just a policy number, so a value large enough to remove the bound entirely is
# treated as a typo rather than as a decision. Nothing this app accepts is
# remotely near 1 GiB.
#
# BE HONEST ABOUT THE REACH: this catches only the absurd end. A single extra
# digit on the upload ceiling (251658240 for 25165824) is 240 MiB -- well under
# this bound -- and still boots perfectly cleanly. There is no way to separate
# that from a deliberate 240 MiB choice without asking the operator, and the
# ceiling is a two-way knob on purpose, so this guard stops the runaway case and
# nothing finer. `test_an_implausibly_large_limit_raises_configuration_error`
# is what pins it; do not read it as validating that a limit is *sensible*.
MAX_SANE_LIMIT_BYTES = 1024 * 1024 * 1024

# --------------------------------------------------------------------------
# THE LOAD-BEARING INVARIANT: `app.config['MAX_CONTENT_LENGTH']` must stay
# `None`. This comment is the ONLY place in `config.py` or `app/` that key is
# allowed to appear -- `grep -rn MAX_CONTENT_LENGTH config.py app/` should find
# this block and nothing else. Any assignment to it is the regression this
# whole module exists to prevent.
#
# Werkzeug 3.1.8 `wsgi.get_input_stream` has four branches. The one that
# matters: when `wsgi.input_terminated` is in the environ (gunicorn sets it
# unconditionally) AND `max_content_length is not None`, it returns
# `LimitedStream(stream, max_content_length, is_max=True)` — which stops at the
# limit and lets the view proceed with a truncated body, rather than raising.
# `flask.wrappers.Request.max_content_length` is exactly
# `current_app.config['MAX_CONTENT_LENGTH']` absent a per-request override, so
# that config key alone arms it. With the key left `None`, the same branch
# returns the raw stream — i.e. the CappedStream below — unwrapped, and the cap
# is authoritative.
#
# Measured on the installed Flask 3.1.3 / Werkzeug 3.1.8 with a gunicorn-shaped
# environ, oversize body, no `Content-Length`:
#   MAX_CONTENT_LENGTH = None   -> 413
#   MAX_CONTENT_LENGTH = limit  -> 200 carrying exactly `limit` bytes
# The second is a real defect that shipped here once. Do not "helpfully" wire up
# Flask's built-in limit; this project's limits are MAX_REQUEST_BODY_BYTES and
# MAX_UPLOAD_BODY_BYTES for exactly this reason.
# --------------------------------------------------------------------------


class CappedStream:
    """Wraps `wsgi.input`, raising rather than truncating past `cap` bytes.

    Every read path this object exposes must be **counted AND CLAMPED**.

    *Counted*, because an uncounted method is a silent bypass of the whole
    feature. That is also why there is no `__getattr__` delegating to the
    wrapped stream: `LimitedStream.readinto` probes
    `hasattr(self._stream, 'readinto')` and would use an inherited `readinto`
    directly, reading bytes this class never sees. With no such attribute it
    falls back to `read()`, which is counted.

    *Clamped*, because counting a read only bounds the RESPONSE — it does
    nothing about the memory, which is the entire point of the feature. An
    earlier iteration passed an unsized `read(-1)` straight through and counted
    afterwards; `Request.get_data()` issues exactly `read(-1)`, so a 64 MiB body
    against a 1 MiB cap produced a textbook-correct 413 *after* 64 MiB was
    resident (measured: one `read(-1)`, RSS +65.1 MiB). Multipart happened to be
    safe because Werkzeug's `_chunk_iter` issues 64 KiB sized reads, so the
    defect hid on uploads and bit on every JSON route.

    So no read is ever passed through larger than `_CHUNK` (see below), and the
    running total never exceeds `cap - already_read + 1`: one byte past the cap
    is all it takes to know the cap is broken, and asking for more can only buy
    the attacker memory. All four read paths go through the same
    `_read_bounded` loop, so none of them can drift out of that guarantee.

    **Memory, stated honestly.** The bytes still in flight at the peak are
    bounded by what is being *returned* — itself bounded by the remaining
    allowance — plus one copy of it, because `read()` must hand back an
    immutable `bytes` and the chunks are accumulated in a `bytearray` first.
    So the real factor is ~2x the bytes returned, not 1x. An earlier iteration
    accumulated into a list and `b''.join`ed it, which is the same 2x while
    claiming 1x in its docstring; the `bytearray` at least drops the per-chunk
    list overhead.
    """

    # THE BOUND ON EACH INDIVIDUAL READ -- not on the remaining allowance.
    #
    # `io.BufferedReader.read(n)` allocates `n` bytes UP FRONT, before it knows
    # how much data exists, and that is exactly what the Werkzeug dev server
    # (and any socket-backed stream) hands over as `wsgi.input`. Asking it for
    # the whole remaining allowance in one call therefore costs the whole
    # configured cap on every request, however small the body:
    #
    #   measured, `BufferedReader.read(24 MiB)` over a 9-byte body -> 24.00 MiB
    #   peak; measured end-to-end, a 7-BYTE multipart POST to
    #   /api/items/<ja_id>/photos -> 24.03 MiB peak.
    #
    # The `before_request` hook issues `get_data()` on every request, so that
    # was a cap-sized transient allocation on every request in the app,
    # including bodyless ones -- an iteration that traded an allocation
    # proportional to the attacker's body for one proportional to the
    # configured cap, unconditionally. 64 KiB matches the chunk size Werkzeug's
    # own multipart `_chunk_iter` uses.
    _CHUNK = 64 * 1024

    def __init__(self, stream, cap):
        self._stream = stream
        self._cap = cap
        self._read = 0

    @property
    def bytes_read(self):
        """Running total, for tests and diagnostics."""
        return self._read

    def _room(self):
        """The most this stream will ever pull in total: everything still
        allowed, plus the single byte that proves the cap is broken."""
        return self._cap - self._read + 1

    def _read_bounded(self, size, reader, stop_on_newline=False):
        """Pull at most `size` bytes (unsized => the whole remaining allowance)
        through `reader`, in `_CHUNK` steps, counting as we go.

        Loops for two independent reasons, and both matter:

        * a WSGI stream may legitimately return short, and this class promises
          never to return short of what was asked for -- a body UNDER the cap
          must arrive whole; and
        * each individual call to `reader` must stay small, because the wrapped
          stream may allocate whatever it is asked for before it looks at the
          data (see `_CHUNK`).

        `stop_on_newline` is what makes this usable as `readline`: a body with
        no newline in it is one enormous "line", so the SIZE bound -- not the
        newline -- has to be what terminates the read.
        """
        # Already past the cap: `_room()` is <= 0 here, so every branch below
        # would fall straight through the loop and return `b''` -- i.e. the
        # SILENT TRUNCATION this class exists to forbid, delivered by the very
        # method that promises never to truncate. Reaching this state means an
        # earlier read raised and something swallowed the exception; answer it
        # the same way that read did rather than handing back a short body.
        if self._read > self._cap:
            raise RequestEntityTooLarge()

        room = self._room()
        wanted = room if size is None or size < 0 else min(size, room)
        out = bytearray()
        while wanted > 0:
            chunk = reader(min(wanted, self._CHUNK))
            if not chunk:                       # EOF
                break
            self._read += len(chunk)
            if self._read > self._cap:
                raise RequestEntityTooLarge()
            out += chunk
            # `len(chunk)` rather than the requested size: a stream that
            # over-honours the request must not leave `wanted` overstated.
            wanted -= len(chunk)
            if stop_on_newline and b'\n' in chunk:
                break
        # One copy of what is being returned; see the class docstring on the
        # real memory factor. `read()` has to return `bytes`, not a bytearray.
        return bytes(out)

    def read(self, size=-1):
        return self._read_bounded(size, self._stream.read)

    def readline(self, size=-1):
        return self._read_bounded(size, self._stream.readline,
                                  stop_on_newline=True)

    def readlines(self, hint=-1):
        # Built on the clamped `readline` above, NOT on the wrapped stream's own
        # `readlines`, which would materialise the whole body first. `hint` is
        # deliberately ignored beyond terminating on EOF: it is advisory, and
        # honouring it could only ever read MORE than the cap allows.
        lines = []
        while True:
            line = self.readline()
            if not line:
                return lines
            lines.append(line)

    def __iter__(self):
        # Likewise built on the clamped `readline`, not on `iter(self._stream)`.
        while True:
            line = self.readline()
            if not line:
                return
            yield line

    # Non-reading protocol members. Explicit rather than delegated, so adding a
    # new *reading* method here is a deliberate act that has to count.
    def close(self):
        """Deliberately a no-op.

        PEP 3333 reserves `wsgi.input` to the server: "the server MUST NOT close
        the input stream", and by the same token an application-side wrapper
        must not close it either. Delegating here let any caller that closes the
        request stream tear down a connection the server still owns and intends
        to reuse.

        Note this class deliberately implements no `__enter__`/`__exit__`, so a
        `with` block over it is a `TypeError` rather than a benign no-op close.
        Nothing in Werkzeug's request path uses one; the omission is recorded
        here only so the docstring does not name a caller shape that would in
        fact raise. The same goes for `tell`, `flush` and `fileno`, which are
        absent because nothing calls them -- unlike `readinto`/`read1`, whose
        absence is load-bearing and documented on the class.
        """

    def readable(self):
        return True

    def writable(self):
        return False

    def seekable(self):
        return False


class BodyLimitMiddleware:
    """WSGI middleware installing a `CappedStream` on every request.

    Must not raise for any environ: it runs ahead of Flask entirely, so an
    exception escaping here is a bare 500 with no error handler involved.
    """

    def __init__(self, wsgi_app, app):
        self.wsgi_app = wsgi_app
        self.app = app

    def __call__(self, environ, start_response):
        # Repair the environ BEFORE Werkzeug parses it. Both of these are
        # `.strip()`/`.partition()`-ed unguarded from inside Werkzeug itself,
        # so a non-`str` value is an AttributeError raised out of WERKZEUG's own
        # code — measured, as a 500 — which no amount of totality in this app
        # can catch. It has to be fixed here or nowhere:
        #
        #   CONTENT_LENGTH  werkzeug.sansio.utils.get_content_length ->
        #                   _plain_int -> `.strip()`
        #   CONTENT_TYPE    werkzeug.http.parse_options_header ->
        #                   `.partition()`  ("AttributeError: 'int' object has
        #                   no attribute 'partition'", measured)
        #
        # CONTENT_TYPE used to matter only to views that touched the form; the
        # forced `get_data(parse_form_data=True)` below widened it to every
        # route in the app, so the hook and this normalisation are a matched
        # pair.
        for key in ('CONTENT_LENGTH', 'CONTENT_TYPE'):
            value = environ.get(key)
            if value is not None and not isinstance(value, str):
                # `bytes` is decoded rather than `str()`-ed: `str(b'123')` is
                # "b'123'", which would turn a valid length into an unparseable
                # one and a valid `multipart/form-data` content type into a
                # non-multipart one -- silently dropping a real upload from the
                # 24 MiB ceiling to the 1 MiB global limit. latin-1 is the WSGI
                # transport encoding and cannot fail.
                environ[key] = (value.decode('latin-1')
                                if isinstance(value, (bytes, bytearray))
                                else str(value))

        stream = environ.get('wsgi.input')
        if stream is None:
            # PEP 3333 mandates the key, but this class's docstring claims
            # totality for ANY environ and that claim is what justifies the
            # design, so honour it: pass such an environ through untouched
            # rather than KeyError-ing out of the middleware. Nothing can be
            # read from a request with no input stream anyway.
            return self.wsgi_app(environ, start_response)

        environ['wsgi.input'] = CappedStream(stream, self._cap_for(environ))
        return self.wsgi_app(environ, start_response)

    def _cap_for(self, environ):
        """Cap for this request: the upload ceiling for an actual upload to one
        of the upload endpoints, the global limit for everything else.

        Endpoint identity alone is NOT enough. Keying on it and nothing else
        meant a measured 8 MiB `application/json` body to the unauthenticated,
        `@csrf.exempt` `main.upload_photo` was accepted and cached under the
        24 MiB ceiling — handing back most of the exposure this feature exists
        to close. The raised ceiling exists for multipart file uploads, so it
        applies only to a `multipart/form-data` request.

        Any routing failure at all — no match, a redirect, a method mismatch, a
        malformed PATH_INFO — falls back to the TIGHTER limit. That is the safe
        direction, and it means a routing miss can never raise out of the
        middleware.

        Both limits are read with `.get(...)` and a literal fallback rather than
        `config['...']`. `validate_limits` refuses to boot without either key,
        so a missing one is unreachable in a running app — but a subscript here
        would turn "unreachable" into a `KeyError` escaping the middleware as a
        bare 500 with no error handler in the picture, which is precisely what
        this docstring promises cannot happen.

        The multipart test comes FIRST because it is the cheap half of a
        conjunction and it is false for essentially all traffic. Matching the
        URL map first meant every request in the app — every static asset,
        every health check — paid a full route match (a second one; Flask then
        matches again) to answer a question that can only ever come out `True`
        for a multipart body aimed at one of two endpoints.
        """
        if not is_multipart(environ):
            return self.app.config.get('MAX_REQUEST_BODY_BYTES',
                                       _FALLBACK_CAP_BYTES)
        try:
            # `server_name` is passed exactly as `Flask.create_url_adapter`
            # passes it. It is `None` today (nothing sets SERVER_NAME), so this
            # changes nothing now -- but if it were ever set, an adapter built
            # without it could resolve an endpoint the app's own adapter does
            # not, and the `before_request` fast path reads `request.endpoint`,
            # i.e. Flask's answer. The two must not be able to disagree.
            adapter = self.app.url_map.bind_to_environ(
                environ, server_name=self.app.config.get('SERVER_NAME'))
            endpoint, _ = adapter.match()
            if endpoint in UPLOAD_ENDPOINTS:
                return self.app.config.get('MAX_UPLOAD_BODY_BYTES',
                                           _FALLBACK_CAP_BYTES)
        except Exception:
            pass
        return self.app.config.get('MAX_REQUEST_BODY_BYTES',
                                   _FALLBACK_CAP_BYTES)


def validate_limits(config, logger):
    """Validate the configured limits at startup.

    Hard-fails only on values that are incoherent. The service-file floors are
    a WARNING, not a refusal to boot: the ceiling is a two-way knob, and a
    deployer who wants a stricter posture than 20 MiB on the unauthenticated,
    `@csrf.exempt`, read-fully-into-memory photo endpoint must be able to
    choose it. Refusing to boot would turn a security control into a floor on
    exposure.

    Every breached floor is reported, not just the first: the floors are
    unordered, so naming one leaves the operator to rediscover the rest one
    restart at a time.
    """
    limits = {}
    for name in ('MAX_REQUEST_BODY_BYTES', 'MAX_UPLOAD_BODY_BYTES'):
        value = config.get(name)
        if value is None:
            raise ConfigurationError(
                f'{name} is required but is missing or None', config_key=name)
        # `bool` excluded explicitly: `True` is an int and would sail through as
        # a cap of 1 byte.
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigurationError(
                f'{name} must be an integer number of bytes; got '
                f'{type(value).__name__}', config_key=name)
        if value < 1:
            raise ConfigurationError(
                f'{name} must be at least 1 byte; got {value}', config_key=name)
        if value > MAX_SANE_LIMIT_BYTES:
            # See MAX_SANE_LIMIT_BYTES: an implausibly large limit is far more
            # likely to be a typo than a decision, and it silently removes the
            # allocation bound this whole module exists to impose.
            raise ConfigurationError(
                f'{name} is implausibly large ({value} bytes); the maximum '
                f'accepted is {MAX_SANE_LIMIT_BYTES} bytes. A body limit is an '
                'allocation bound, so a mistyped digit here removes it',
                config_key=name)
        limits[name] = value

    # `<`, NOT `<=`. Equality is perfectly coherent -- the upload endpoints
    # simply get the same cap as everything else -- and it is the strictest
    # uniform posture an operator can express. Refusing to boot on it made the
    # simplest safe configuration inexpressible.
    if limits['MAX_UPLOAD_BODY_BYTES'] < limits['MAX_REQUEST_BODY_BYTES']:
        raise ConfigurationError(
            'MAX_UPLOAD_BODY_BYTES must be at least as large as '
            f"MAX_REQUEST_BODY_BYTES; got {limits['MAX_UPLOAD_BODY_BYTES']} < "
            f"{limits['MAX_REQUEST_BODY_BYTES']}",
            config_key='MAX_UPLOAD_BODY_BYTES')

    upload = limits['MAX_UPLOAD_BODY_BYTES']
    if upload >= _LARGEST_SERVICE_FILE_LIMIT + _MULTIPART_FRAMING_ALLOWANCE:
        # No floor can be breached, so do not pay to import the services.
        return

    # Only now — and only on a deliberately tightened ceiling — are the real
    # constants worth PIL / PyMuPDF / the ORM.
    from app.photo_service import PhotoService
    from app.mariadb_catalog_service import ATTACHMENT_MAX_SIZE

    breached = [
        f'{name} ({floor} bytes)'
        for name, floor in (('PhotoService.MAX_FILE_SIZE', PhotoService.MAX_FILE_SIZE),
                            ('ATTACHMENT_MAX_SIZE', ATTACHMENT_MAX_SIZE))
        if upload < floor + _MULTIPART_FRAMING_ALLOWANCE
    ]
    if breached:
        logger.warning(
            'MAX_UPLOAD_BODY_BYTES (%d bytes) does not clear these service file '
            'limits plus %d bytes of multipart framing: %s. Uploads at those '
            'sizes will be rejected with 413 at the transport layer before the '
            'service can report a specific error.',
            upload, _MULTIPART_FRAMING_ALLOWANCE, ', '.join(breached))


def init_request_limits(app):
    """Install the body-size bound on `app`.

    Call order in the factory is load-bearing: after `setup_logging(app)` (which
    clears `app.logger.handlers`) and before `csrf.init_app(app)`. See the
    module docstring.
    """
    validate_limits(app.config, app.logger)
    app.wsgi_app = BodyLimitMiddleware(app.wsgi_app, app)

    @app.before_request
    def enforce_request_body_limit():
        # LET THE ROUTING ANSWER WIN. `before_request` runs BEFORE Flask raises
        # a routing failure, so without this an over-limit body aimed at a URL
        # that 404s, 405s or redirects was answered 413 -- telling the caller
        # their body was too large for a resource that does not accept bodies,
        # or does not exist. Measured. Nothing is going to read the body of an
        # unrouted request anyway, and the `CappedStream` is still installed if
        # something somehow does, so skipping here costs no enforcement.
        if request.routing_exception is not None:
            return

        # The middleware deliberately passes an environ with no `wsgi.input`
        # through untouched, because its docstring claims totality for ANY
        # environ. That claim is worth nothing if the hook it installs then
        # KeyErrors on the same environ: measured, a `GET` with the key removed
        # was a 500 WITH this hook and a 200 without it, because
        # `werkzeug.wsgi.get_input_stream` subscripts the key. PEP 3333 mandates
        # it, so this is a totality guard rather than a live path -- but so is
        # the middleware's, and the two must agree.
        #
        # TEST THE VALUE, NOT THE KEY, because that is what the middleware tests
        # (`stream = environ.get('wsgi.input'); if stream is None: ...`). A key
        # present but set to `None` passed this guard while the middleware had
        # already waved the environ through untouched, so nothing was wrapped
        # and `get_data()` then called `.read` on `None`. Measured: a POST with
        # `wsgi.input: None` and `wsgi.input_terminated` set was
        # `AttributeError: 'NoneType' object has no attribute 'read'` -- a bare
        # 500 out of a `before_request`, the same "totality claim defeated by
        # its own hook" shape this guard was added to close.
        if request.environ.get('wsgi.input') is None:
            return

        # Same rule as `BodyLimitMiddleware._cap_for`, and it must stay the same
        # rule: the raised ceiling applies only to an actual multipart upload,
        # never to an `application/json` body that merely happens to be aimed at
        # an upload endpoint. If this branch were more generous than the
        # middleware's, the fast path would wave through a body the stream then
        # rejects; if it were tighter, it would reject a legitimate upload.
        # `.get(...)` with the same literal fallback `_cap_for` uses, for the
        # same reason its docstring gives: `validate_limits` makes a missing key
        # unreachable in a running app, but a subscript would turn "unreachable"
        # into a KeyError raised from a `before_request` -- a bare 500 on every
        # route. Handling that defensively in one copy of the rule and not the
        # other was an asymmetry with no justification behind it.
        cap = (app.config.get('MAX_UPLOAD_BODY_BYTES', _FALLBACK_CAP_BYTES)
               if (request.endpoint in UPLOAD_ENDPOINTS
                   and is_multipart(request.environ))
               else app.config.get('MAX_REQUEST_BODY_BYTES',
                                   _FALLBACK_CAP_BYTES))

        # Fast path for the overwhelming majority of real clients, which do
        # declare a length: reject before reading a single byte. This parse is
        # NOT a security control — a length this cannot parse simply skips the
        # branch and the capped stream still applies — so a bare except is
        # exactly right. `int()` on a 5000-digit value raises ValueError
        # (CPython's 4300-digit conversion cap) and `.strip()` on a non-`str`
        # raises TypeError/AttributeError; either would otherwise be a
        # one-header remote 500 on every route in the app.
        # Plain ASCII digits ONLY, matching what Werkzeug's `_plain_int` will
        # accept. This is not parity-as-a-security-control (that idea is retired
        # -- an unparseable length just falls through to the cap). It avoids a
        # FALSE REJECTION in the other direction: `int()` happily accepts `+50`
        # and `1_048_577`, Werkzeug's parser does not and reports such a length
        # as 0, so trusting `int()` here 413'd an 11-byte body on the strength
        # of a declared length nothing would ever have read. Measured.
        raw = request.environ.get('CONTENT_LENGTH')
        declared = None
        if isinstance(raw, str):
            candidate = raw.strip()
            if candidate.isascii() and candidate.isdigit():
                try:
                    declared = int(candidate)
                except ValueError:
                    # >4300 digits: CPython's int-conversion cap. Falls through
                    # to the stream cap, which is the correct answer anyway.
                    declared = None
        if declared is not None and declared > cap:
            raise RequestEntityTooLarge()

        # Force the read HERE. Most JSON views in this app read the body inside
        # a `try` whose tail is `except Exception: return 500`, so a 413 raised
        # lazily inside a view is CAUGHT and downgraded — measured: an oversize
        # body to /api/inventory/batch-move became a 500, and the handler then
        # died with UnboundLocalError. Reading in the hook puts the raise ahead
        # of every view, including views not yet written.
        #
        # `parse_form_data=True` is not needed to keep `request.files` working
        # (`cache=True` alone does that). It is here because Flask's 500 KB
        # MAX_FORM_MEMORY_SIZE and MAX_FORM_PARTS raise the same
        # RequestEntityTooLarge from inside the parser, i.e. lazily, inside the
        # view — measured as a 500 leaking raw Werkzeug text. It also avoids
        # double-buffering: with it, the parser consumes the stream and
        # `get_data` caches b'' instead of a second copy of a 24 MiB upload.
        try:
            request.get_data(cache=True, parse_form_data=True)
        except (ClientDisconnected, ConnectionError, TimeoutError):
            # HANDLE A DISCONNECT AS A DISCONNECT, not as a request error. A
            # client that hangs up, or under-sends the body it declared, makes
            # Werkzeug's LimitedStream raise this. Before this hook existed the
            # only requests that noticed were the ones that actually read the
            # body; reading speculatively here turned it into a raw Werkzeug 400
            # on routes that never touch the body at all -- measured. So swallow
            # it and let the request proceed exactly as it would have: a view
            # that does read the body hits the same disconnect itself and is
            # answered the same way it always was, and a view that does not is
            # unaffected. This cannot mask an oversize body:
            # RequestEntityTooLarge is not a ClientDisconnected.
            #
            # THE SOCKET ERRORS ONLY -- `ConnectionError` (reset, broken pipe,
            # aborted) and `TimeoutError`, which is what a socket read timeout
            # raises since 3.10. A BARE `OSError` was too wide: the forced
            # `parse_form_data=True` runs Werkzeug's multipart parser, which
            # SPOOLS a large upload to a temp file, so an `ENOSPC` or `EACCES`
            # from that spool is an `OSError` too. Swallowing it let the request
            # continue to a view holding a silently incomplete `request.files`
            # instead of surfacing a truthful server error. Both shapes that
            # were actually measured here are `ConnectionError` subclasses, so
            # nothing this limb was added for is lost.
            #
            # A socket error is the case that actually matters in production.
            # Werkzeug converts a socket error into
            # ClientDisconnected inside `LimitedStream.readinto` -- but the
            # load-bearing `MAX_CONTENT_LENGTH is None` invariant means
            # `get_input_stream` hands back the `CappedStream` UNWRAPPED under
            # any server setting `wsgi.input_terminated`, so no LimitedStream is
            # in the chain and gunicorn's own reader raises a bare
            # ConnectionResetError straight through. Measured: without this,
            # a mid-body client reset is an unhandled 500 plus an ERROR log on
            # EVERY route, including ones that never read the body. A client
            # hanging up is routine, not an application error.
            pass
