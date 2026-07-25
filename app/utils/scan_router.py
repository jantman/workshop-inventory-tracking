"""
Structural classification of one captured scan (Story 4.2, FR36/FR37).

This module is the epic's single routing authority. Given the text of one
keyboard-wedge scan it decides *what kind of thing was scanned* — a label this
system printed, a distributor's ISO/IEC 15434 envelope, a manufacturer trade
item number, or none of those — and nothing else. It is a PURE module:
standard library, `app.models`, `app.utils.gs1` and `app.utils.gtin` only. No
Flask, no `current_app`, no config, no SQLAlchemy, no I/O (AD-4, AD-5). That is
what lets Epic 7's capture path and the unit suite call `classify()` with no
application context and no database.

The precedence (FR36)
---------------------
Exactly four rules, tried in this order, first match wins, and rule 4 always
matches — so every scan is classified and none dead-ends:

1. An internal element string under the configured grammar -> `INTERNAL`.
2. An ISO/IEC 15434 format-06 envelope header            -> `ECIA`.
3. A bare, check-digit-valid trade item number           -> `GTIN`.
4. Anything else                                         -> `FREE_TEXT`.

The order is not arbitrary. Rules 1 and 3 overlap by construction: an internal
payload whose configured token happens to be numeric can also be a
check-digit-valid all-digit string, so an ordering is required and "ours wins"
is the only safe one — a label this shop printed must never resolve to somebody
else's trade item. Rule 2 precedes rule 3 only because an envelope is never
all-digits; the ordering there is documentation, not arbitration.

What this module deliberately does not do
-----------------------------------------
- **No lookup.** No database, no `CatalogService`, no fallthrough-to-search.
  `resolve_scan()` and `search_products()` belong to Story 4.3 (AD-4/AD-5), and
  a classifier that could touch a session would not be callable from Epic 7.
- **No internal-payload matching of its own (AD-16).** Rule 1 is delegated
  whole to `gs1.decode()`. This module never pattern-matches the Application
  Identifier or the token, holds no literal default for either, and never
  re-derives the grammar. The pair arrives as keyword arguments from the one
  named config pair the service reads, exactly as
  `mariadb_catalog_service.encode_internal_payload` already passes them into
  `gs1.encode` — so one config change moves the encoder and this router
  together, with no code edit.
- **No check-digit or 14-digit arithmetic (AD-16 again).** Rule 3 asks
  `gtin.is_valid_gtin` and `gtin.normalize_gtin`; the accepted lengths, the
  mod-10 weights and the canonical key length all stay in `app/utils/gtin.py`.
- **No ECIA field parsing.** Rule 2 recognizes the *header* and stops.
  Extracting `P` / `1P` / `Q` / `K` / `1K` / `9D` / `10D` is Story 4.4's, which
  is also where a valid header with unparseable contents degrades back to free
  text. The two halves satisfy NFR8 jointly.
- **No trimming of its own.** `classify()` never trims. Its caller has already
  applied the single cleaning rule (`_clean_scan_input` in
  `app/main/routes.py`, which trims space/tab/CR/LF and nothing else, because a
  bare `str.strip()` would eat the RS that terminates an envelope). Re-cleaning
  here would be a third copy of that rule rather than a shared one.

  Be precise about what that does *not* say. Rule 1 is delegated to
  `gs1.decode`, which begins with `raw.strip()` as its FNC1/CR-LF transmission
  tolerance, so a padded internal payload still classifies as `INTERNAL` while
  a padded GTIN or envelope does not. The two policies are asymmetric on
  purpose — the tolerance belongs to the grammar that needs it, and inventing a
  matching tolerance here would be the third copy of the trim rule — but the
  asymmetry is real, it is pinned by tests, and it means correct routing for
  rules 2-4 depends on the caller having cleaned the input. It also means a
  leading space defeats the AIM strip below.

  And it does not stop at spaces, which is the half worth stating out loud.
  Python's `str.strip()` also eats `\x1c`-`\x1f`, so `gs1.decode` absorbs a
  transmitted GS/RS while `_clean_scan_input` deliberately does not — that
  cleaner exists precisely to preserve the separators an envelope is built
  from. Net effect: a wedge that prefixes a GS routes an internal label
  correctly (`'\x1d' + internal` -> INTERNAL) and misroutes a distributor
  label (`'\x1d[)>' RS '06'...` -> FREE_TEXT), because rule 2 anchors on the
  header and judges the scan as it arrived. Neither this module nor the
  cleaner can close that alone — absorbing separators here would re-open the
  trim rule this module refuses to own, and stripping them in the cleaner
  would destroy the envelope's structure — so the case is pinned by
  `TestWhitespaceAsymmetryBetweenRules` and left to the story that owns the
  caller seam. It has never been observed on the deployed Tera HW0009, which
  emits no separator prefix at all.

- **No consumer contract beyond `ScanClassification`.** In particular, the
  candidate this module classifies (AIM prefix removed) is not carried on the
  result: AD-15 freezes exactly four fields and `raw` is the verbatim scan. A
  consumer that needs to *use* the scan text rather than classify it — Story
  4.3 searching free text, Story 4.4 parsing an envelope — must call the
  exported `strip_aim_prefix()` on `raw` first, or it will search for and parse
  a string that still begins `]d1`. That helper is public for exactly this
  reason; re-deriving the AIM shape in a second place is what it prevents.

Never raises on scan data (NFR8)
--------------------------------
No value of a `str` `raw` produces an exception — not an empty string, not
control characters, not four kilobytes of garbage. Exactly two exceptions are
reachable and both are caller faults rather than properties of the scan: a
`TypeError` when `raw` is not a `str` (a malformed caller, not a scan), and
`gs1.InvalidGs1PayloadError` propagated unchanged when the configured grammar
is malformed. The second is propagated on purpose: swallowing it would silently
disable rule 1, and every label this shop ever printed would quietly start
classifying as free text.
"""

import re
from typing import Any

from app.models import ScanClassification, ScanKind
from app.utils import gs1
from app.utils import gtin

# The ISO/IEC 15434 message header for format 06 — '[)>' RS '06'. The format
# indicator is exactly two digits, so a different one (or a missing RS) is a
# different message envelope, not this one. Vector: tests/unit/test_gs1.py.
_ECIA_HEADER = '[)>\x1e06'

# What may legally follow that header. GS (\x1d) opens the first data record;
# RS (\x1e) closes an empty message. Nothing else may abut the format
# indicator: ISO/IEC 15434 is header RS format-indicator GS ... RS EOT, so a
# character glued straight onto the indicator means the two-digit indicator was
# never actually delimited and the string only *resembles* an envelope. Calling
# such a string 'ecia' would hand Story 4.4 something it cannot parse when
# free text is the honest answer.
_ECIA_SEPARATORS = ('\x1d', '\x1e')

# An AIM symbology identifier: ']' + one ASCII letter (the code character,
# identifying the symbology) + one digit (the modifier). Anchored and exactly
# three characters, because that is the whole of the prefix — a leading ']'
# in any other shape is data.
_AIM_PREFIX_RE = re.compile(r'\][A-Za-z][0-9]')

# How much of a rejected non-string `raw` is rendered into the TypeError below.
# Matches the intent of `_SCAN_LOG_CHARS` in `app/main/routes.py`: the value is
# untrusted and unbounded, and an exception message ends up in a log.
_FAULT_REPR_CHARS = 512

# The types a wrongly-typed `raw` is plausibly one of that also slice cheaply
# and WITHOUT SIDE EFFECTS. The allow-list is the point: `value[:n]` on an
# arbitrary object calls its `__getitem__`, and for a `defaultdict` that
# *inserts* a key — so describing a bad argument would mutate the caller's
# object, which a module whose whole contract is purity must never do.
_SLICEABLE_FAULT_TYPES = (str, bytes, bytearray, list, tuple)


def _bounded_repr(value: Any) -> str:
    """
    A short, safe `repr` of a rejected `raw`, for the TypeError message below.

    The value is untrusted and of unknown size, and an exception message ends
    up in a log — so this follows the house rule `app/main/routes.py` already
    applies to the scan it logs (`_SCAN_LOG_CHARS`).

    The slice happens *before* `repr` for the types listed above, not after:
    `repr` of a multi-megabyte `bytes` materializes the whole escaped string
    first, so truncating afterwards bounds the log line but not the memory
    spike it was meant to prevent. Anything not on that list is repr'd whole
    and truncated afterwards — slicing it could run arbitrary `__getitem__`
    code and mutate it. The post-slice is applied to already-escaped text, so
    it can land mid-escape: acceptable in a diagnostic, and the character count
    says what was dropped.

    A slice or a `repr` that raises is caught rather than propagated: this
    function exists inside the guard that promises `TypeError` for a bad `raw`,
    and letting a hostile `__repr__` replace that with some other exception
    would break the documented contract for the sake of a message.
    """
    try:
        head = (value[:_FAULT_REPR_CHARS]
                if isinstance(value, _SLICEABLE_FAULT_TYPES) else value)
        shown = repr(head)
    except Exception:
        return f'<unrepresentable {type(value).__name__}>'
    if len(shown) > _FAULT_REPR_CHARS:
        shown = f'{shown[:_FAULT_REPR_CHARS]}... ({len(shown)} chars)'
    return shown


def strip_aim_prefix(value: str) -> str:
    """
    Remove one leading AIM symbology identifier, if there is one.

    Why here and not in `gs1.decode`: per FR37 an AIM identifier only narrows
    the *symbology class* — it says "this came out of a DataMatrix", not "this
    is internal" — and the same symbology carries both internal labels and
    manufacturer GTINs. So the prefix can never select a handler; only the
    payload can. That makes stripping it a classification concern, and
    `app/utils/gs1.py` says so explicitly: `decode` sees a prefixed payload as
    foreign and returns None, leaving the strip to this module. Doing it once,
    here, at the front, means all four rules see the same candidate and no rule
    has to know AIM exists.

    Stripped **once**: a second identifier would be data emitted by a scanner
    that had already prefixed once, not a nested prefix. The deployed Tera
    HW0009 emits no AIM identifier at all, so this path must never be required
    for correct routing — it is tolerance, not grammar.

    Args:
        value: The candidate string.

    Returns:
        `value` without its leading three-character AIM identifier, or `value`
        unchanged if it does not open with exactly that shape.
    """
    return value[3:] if _AIM_PREFIX_RE.match(value) else value


def _is_ecia_envelope(value: str) -> bool:
    """
    True if `value` opens with a well-formed ISO/IEC 15434 format-06 header.

    The header alone is judged, not the contents — see the module docstring for
    where the 4.2/4.4 boundary falls. A header with no body at all is still an
    envelope (a legal, empty message); Story 4.4 is what degrades it.

    Args:
        value: The candidate string, AIM prefix already removed.

    Returns:
        True for a format-06 envelope, False for a truncated header, a
        different format indicator, or a header not delimited from what
        follows it.
    """
    if not value.startswith(_ECIA_HEADER):
        return False
    rest = value[len(_ECIA_HEADER):]
    # End-of-string is accepted for the same reason a separator is: both mean
    # the two-digit format indicator ended where the standard says it ends.
    return not rest or rest[0] in _ECIA_SEPARATORS


def classify(raw: Any, *, ai: str, token: str) -> ScanClassification:
    """
    Classify one captured scan by structure (FR36, FR37).

    Applies the four precedence rules described in the module docstring and
    returns the first match. Deterministic: the result depends on nothing but
    `(raw, ai, token)` — no clock, no config read, no database, no global
    state.

    Args:
        raw: The scan text, already cleaned by the caller. Kept verbatim on the
            result, AIM prefix and all.
        ai: The Application Identifier of the internal grammar. Keyword-only,
            no default — it comes from the single named config pair, read in
            the service and passed in explicitly (AD-16).
        token: The literal that opens the internal grammar's data field.
            Keyword-only, no default, same source as `ai`.

    Returns:
        A `ScanClassification`. `ecia_fields` is always None in this story.

    Raises:
        TypeError: if `raw` is not a `str`. A non-string is a caller fault —
            the scan transport hands this function text or rejects the request
            before it gets here — so it fails loudly rather than classifying as
            free text and burying the bug in a search result.
        gs1.InvalidGs1PayloadError: if the configured grammar is malformed —
            a blank, padded, non-string or non-printable `ai` or `token`, a
            pair whose marker opens 43, or a token with no room for an id after
            it (`len(token) >= gs1.MAX_DATA_FIELD_LENGTH`). Propagated
            unchanged from `gs1.decode`: a configuration fault must surface,
            because catching it here would silently disable rule 1 and
            reclassify every internal label as free text.

    Note:
        Rule 1 has one exit worth naming, because it is `gs1.decode`'s and not
        visible here: a payload that opens with the configured marker but whose
        data field exceeds `gs1.MAX_DATA_FIELD_LENGTH`, or whose id carries a
        character `encode` would never have emitted, is *foreign* rather than
        malformed and returns None — so it falls through and classifies as
        `FREE_TEXT`. A corrupted or concatenated label this shop printed
        therefore becomes an ordinary search rather than an error, which is the
        no-dead-end behavior FR36 wants, but it does mean the id length limit
        is an input to classification.

    Examples:
        The grammar below is illustrative, not the deployed one — this module
        holds no literal default for either half (AD-16).

        >>> c = classify('91ZZABC1234567', ai='91', token='ZZ')
        >>> c.kind is ScanKind.INTERNAL, c.normalized_value
        (True, 'ABC1234567')
        >>> classify('9506000134352', ai='91', token='ZZ').normalized_value
        '09506000134352'
    """
    if not isinstance(raw, str):
        raise TypeError(
            f'raw must be a string, got {type(raw).__name__}: '
            f'{_bounded_repr(raw)}.')

    # Stripped once, before any rule runs, so every rule below sees the same
    # candidate. `raw` itself is never reassigned — it is what the result
    # carries verbatim.
    candidate = strip_aim_prefix(raw)

    # Rule 1 — ours. Delegated whole to the Epic 2 grammar module, which also
    # absorbs FNC1 transmission variance (GS transmitted, or stripped entirely
    # as the deployed hardware does). A foreign payload is a None from there,
    # never an exception; the only exception that can come out is a grammar
    # fault, which is deliberately not caught.
    payload = gs1.decode(candidate, ai=ai, token=token)
    if payload is not None:
        # The token-stripped id, exactly as decode returns it — which is
        # exactly what Story 2.4 stored. Handing the resolver anything else
        # would force it to strip a second time.
        return ScanClassification(
            kind=ScanKind.INTERNAL,
            normalized_value=payload.internal_id,
            ecia_fields=None,
            raw=raw,
        )

    # Rule 2 — a distributor envelope. Header only; nothing to normalize.
    if _is_ecia_envelope(candidate):
        return ScanClassification(
            kind=ScanKind.ECIA,
            normalized_value=None,
            ecia_fields=None,
            raw=raw,
        )

    # Rule 3 — a bare manufacturer trade item number. The ASCII-digit guard is
    # load-bearing rather than a restatement of what `is_valid_gtin` checks:
    # `normalize_gtin` deliberately tolerates surrounding whitespace, and
    # Python counts GS/RS (\x1c-\x1f) as whitespace, so without this guard
    # '\x1d9506000134352' — a fragment of a distributor label — would classify
    # as a clean GTIN. A scan is judged as it arrived. The accepted lengths and
    # the check digit stay behind `is_valid_gtin`; re-listing {8, 12, 13, 14}
    # here would be the second copy AD-16 exists to prevent.
    #
    # Normalization is attempted inside the guard rather than after asking
    # `is_valid_gtin` first, so NFR8 holds structurally rather than by luck.
    # `is_valid_gtin` happens to be implemented as try/normalize/except today,
    # which is why the two-call form could not raise — but that is a private
    # detail of gtin.py, and any future divergence between the predicate and
    # the normalizer would let `InvalidGtinError` escape a function contracted
    # never to raise on scan data. One call, one try, no double parse.
    if candidate.isascii() and candidate.isdigit():
        try:
            return ScanClassification(
                kind=ScanKind.GTIN,
                normalized_value=gtin.normalize_gtin(candidate),
                ecia_fields=None,
                raw=raw,
            )
        except gtin.InvalidGtinError:
            pass  # Not a trade item number after all — fall through to rule 4.

    # Rule 4 — the fallthrough, which always matches. Not an error and not a
    # failure: an unrecognized scan is a search, and Story 4.5 lands it on
    # results or on a pre-filled create form.
    return ScanClassification(
        kind=ScanKind.FREE_TEXT,
        normalized_value=None,
        ecia_fields=None,
        raw=raw,
    )
