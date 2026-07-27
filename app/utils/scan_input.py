r"""
The scan-text rule: what a captured scan is trimmed of, and how long it may be
(Story 4.1, FR35).

This module is the single source of truth for the two payload bounds every
consumer of a wedge scan needs before it can look at one: the exact set of
characters trimmed off the ends, and the upper bound on a captured value. It is
a PURE module on the AD-4 pattern (`gtin.py`, `gs1.py`, `ecia.py`,
`internal_id.py`): standard library only, no Flask, no `current_app`, no
config, no SQLAlchemy, no I/O, and no `app.*` imports. Not every module in this
package clears that bar — `category.py` reaches for `app/utils/sql_text.py` and
`scan_router.py` (a consumer of this rule, named below) imports `app.models`
and three sibling utils — so the list above is the set of modules to follow,
not an inventory of the package. `tests/unit/test_scan_input.py` pins the
stricter rule for this module rather than the looser one AD-4 tolerates. It can
therefore be called by a route, a service or a test with no app context and no
database. That is a statement about this module's own body, not about the cost
of reaching it: importing it package-qualified still runs `app/__init__.py`,
which imports Flask and `config`, exactly as it does for every other pure util
here.

It exists as a module rather than as two private names inside
`app/main/routes.py` because the rule is not a property of the route. The route
is one consumer of it; `app/utils/scan_router.py`'s `classify()` documents a
contract that depends on it, `app/mariadb_catalog_service.py`'s `resolve_scan`
inherits it from its caller, and `app/static/js/scan-capture.js` carries a
mirrored copy of the TRIM SET (only the trim set — see "The JavaScript copy"
below) in JavaScript. A rule with that many readers needs one public name in
one place, not an underscore-prefixed name reached across modules.

Why the trim set is spelled out
-------------------------------
`SCAN_TRIM` is deliberately NOT a bare `str.strip()` with no argument. Python
classifies `\x1c`-`\x1f` as whitespace, so a defaulted `.strip()` would eat the
trailing RS (`\x1e`) that terminates an ISO/IEC 15434 envelope, and
`app/utils/ecia.py`'s parser would then be handed a truncated record. The set is
exactly the four characters FR35 names — space, tab, CR and LF — which are the
characters a keyboard wedge realistically appends as a terminator or a
programmed suffix. Every other byte survives: GS (`\x1d`), RS (`\x1e`), EOT
(`\x04`), FS/US (`\x1c`/`\x1f`), VT/FF (`\x0b`/`\x0c`), NUL, NBSP, BOM,
interior whitespace and letter case. That narrowness is a deliberate
consequence, not an oversight — a scanner programmed with VT as its suffix hands
Story 4.4's parser a VT, and `tests/unit/test_scan_input.py` pins that so
widening the set has to be a conscious act.

Only the ENDS are trimmed, and only what is already there is removed. Nothing
here absorbs a *leading* separator: `'\x1d' + envelope` keeps its GS, because
stripping the separators an envelope is built from is exactly what this rule
exists to prevent. That leaves a known asymmetry with `gs1.decode`, which does
begin with a bare `raw.strip()` as its own FNC1/CR-LF tolerance; the asymmetry
is documented and pinned in `app/utils/scan_router.py` and belongs to the story
that owns the caller seam, not to this module.

Why the length bound exists
---------------------------
`MAX_SCAN_LENGTH` is far longer than any real wedge payload — a full ISO/IEC
15434 format-06 envelope is a few hundred characters — so it never refuses a
scan an operator actually made. It exists only so a runaway paste is refused
rather than echoed back, resolved against the catalog, or written into a log
line. It is a payload sanity bound counted in code points, NOT a transport or
memory guard: by the time it can be applied the body has already been read and
parsed. The transport bound is a separate, active control in
`app/request_limits.py`, which caps the request body at the WSGI layer. The two
are additive.

The JavaScript copy
-------------------
`ScanCapture.stripOuter` in `app/static/js/scan-capture.js` mirrors `SCAN_TRIM`
character for character, so the client's "is this blank" test agrees with the
server's. It is a genuine second copy — the browser cannot import Python — and
`tests/unit/test_scan_trim_rule.py` reads the JS regex character class out of
the source and asserts it equals `set(SCAN_TRIM)`, so the two cannot drift
silently.

`MAX_SCAN_LENGTH` is deliberately NOT mirrored there, and the scan field
carries no `maxlength`. An over-length paste is answered by the endpoint with
the AD-13 invalid-field envelope naming the limit, which is a visible refusal
the operator can act on; a client-side cap would instead truncate silently and
post a scan nobody scanned.
"""

# Upper bound on a captured scan, in code points. See "Why the length bound
# exists" above: a payload sanity bound, additive to the WSGI-layer body cap in
# app/request_limits.py, not a substitute for it.
MAX_SCAN_LENGTH = 4096

# The ONLY characters trimmed off a captured scan: space, tab, CR, LF. See "Why
# the trim set is spelled out" above — this is explicit precisely so it is not
# a bare str.strip(), which would eat the RS that terminates an ISO/IEC 15434
# envelope. `ScanCapture.stripOuter` mirrors this set exactly.
SCAN_TRIM = ' \t\r\n'


def clean_scan_input(value: str) -> str:
    r"""Strip leading/trailing space, tab, CR and LF from a captured scan.

    Every other byte — GS (`\x1d`), RS (`\x1e`), EOT (`\x04`), interior
    whitespace, letter case — survives untouched (FR35).

    Args:
        value: The scan text as captured. Callers pass a `str`; this function
            does not type-check, so a non-`str` surfaces the caller's own bug
            rather than being coerced into a scan. Which exception depends on
            the type — `bytes` reaches `bytes.strip` and raises `TypeError`,
            while `None`/`int`/`list` raise `AttributeError` — so a caller that
            wants to catch this must catch both. The scan transport rejects a
            non-`str` `raw` before it gets here (`app/main/routes.py`), so
            neither is reachable from a request.

    Returns:
        `value` with only the `SCAN_TRIM` characters removed from its ends.

    Examples:
        The characters that go, all at once, and interior whitespace staying:

        >>> clean_scan_input('  0123 \r\n')
        '0123'
        >>> clean_scan_input('a b\tc') == 'a b\tc'
        True
        >>> clean_scan_input('   ')
        ''

        The separators an ISO/IEC 15434 envelope is built from survive. Shown
        as a bare data record rather than a whole envelope on purpose: under
        `app/`, the format-06 header literal is spelled only in
        `app/utils/ecia.py`, which owns that grammar. (Tests spell it freely —
        they are asserting against it, not defining it.)

        >>> record = '\x1dP123\x1e\x04'
        >>> clean_scan_input(record) == record
        True

        The trailing RS is where a bare `str.strip()` does real damage —
        Python classifies `\x1c`-`\x1f` as whitespace, so it eats the
        separator that terminates the record and the parser sees a truncated
        one:

        >>> unterminated = '\x1dP123\x1e'
        >>> clean_scan_input(unterminated) == unterminated
        True
        >>> unterminated.strip() == unterminated
        False

        Control characters outside the set are kept, including the ones
        `str.strip()` would remove:

        >>> clean_scan_input('\x0bP123\x0c') == '\x0bP123\x0c'
        True
        >>> clean_scan_input('\x1c\x1f') == '\x1c\x1f'
        True
        >>> clean_scan_input('\x00') == '\x00'
        True
    """
    return value.strip(SCAN_TRIM)
