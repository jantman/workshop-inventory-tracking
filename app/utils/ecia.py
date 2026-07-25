"""
The ISO/IEC 15434 format-06 grammar for distributor labels (Story 4.4, FR38).

This module is the single source of truth for what a DigiKey/Mouser/Avnet 2D
label *is* and what can be read out of it. It answers exactly two questions
about one captured scan — "is this a format-06 envelope?" and "what MH10.8.2
data identifiers does it carry?" — and nothing else. It is a PURE module on the
AD-4 pattern (`gtin.py`, `gs1.py`, `internal_id.py`, `category.py`): standard
library only, no Flask, no `current_app`, no config, no SQLAlchemy, no I/O, and
in particular no import of `app.models` or `app.utils.scan_router`. The
dependency therefore runs one way — `scan_router` -> `ecia` — and cannot cycle.

The structure it implements
---------------------------
An ECIA label carries an ISO/IEC 15434 message::

    '[)>' RS '06' GS <record> GS <record> ... RS EOT

`'[)>' RS '06'` is the message header: the three message-header characters, a
record separator, and the two-digit format indicator that says "format 06, the
ANSI MH10.8.2 data-identifier format". Each record after it is one data
identifier immediately followed by its value, and the RS after the last record
terminates format 06 — what follows is either another format's data or the
`RS EOT` trailer. Data identifiers are drawn from ANSI MH10.8.2; the seven this
system cares about are named by FR38 and listed in `ECIA_FIELD_KEYS` below.
Their meanings are recorded once, in the PRD addendum
(`_bmad-output/planning-artifacts/prds/prd-workshop-inventory-tracking-2026-07-21/addendum.md:27`):
`P` customer part number, `1P` supplier part number (required per the ECIA
spec), `Q` quantity, `K` customer order number, `1K` supplier order number,
`9D`/`10D` date in `YYWW`.

Never raises on a `str` (NFR8)
------------------------------
No value of a `str` argument produces an exception from either function — not
an empty string, not a header with garbage behind it, not four kilobytes of
control characters, not a lone surrogate. A scan that cannot be parsed is
answered with `{}`, and `app/utils/scan_router.py` turns that into a
`free_text` classification carrying the raw scan (AD-5): an operator holding a
damaged label lands on a search, never on an error page.

Exactly one exception is reachable from either function, and it is a caller
fault rather than a property of the scan: `TypeError` when the argument is not
a `str`. That is the same door `scan_router.classify()` keeps, and for the same
reason — the scan transport hands these functions text or rejects the request
before it gets here, so a non-string means a broken caller, and classifying it
as "not an envelope" would bury that bug in a search result. The message names
the parameter and `type(x).__name__` and deliberately does NOT interpolate the
value: bounding an untrusted, unbounded value for a log message is a solved
problem living in `scan_router._bounded_repr`, and a second copy of it here
would be one more thing to keep in agreement for the sake of a diagnostic that
the type name already carries.

What this module deliberately does not do
-----------------------------------------
- **No date parsing and no quantity coercion.** `9D`/`10D` are `YYWW` and `Q`
  is a count, but the frozen field type is `Mapping[str, str]`
  (`app/models.py`), so every value stays the string it was scanned as and
  interpretation belongs to the consumer (Story 4.5's pre-filled create form,
  Epic 7's order-time capture).
- **No validation of field content.** An unparseable date or a non-numeric
  quantity is extracted as scanned, not rejected — rejecting it would lose data
  the operator can read off the label with their own eyes.
- **No separator tolerance.** A scan missing the RS or the GS separators, or
  carrying a *leading* separator before the header, is not an envelope and
  falls through to free text. Inventing a transmission form nobody has observed
  would promote genuinely damaged scans to `ecia`; the open ledger entries on
  what the deployed Tera HW0009 actually emits are aimed at the story that owns
  the caller seam, not at this grammar. Ending the body at an EOT that arrived
  without its RS is not an exception to this: it promotes nothing, changes no
  scan's `kind`, and only declines to read a transmission terminator as part of
  a value.
- **No lookup and no classification precedence.** Resolving a parsed part
  number against the catalog is `mariadb_catalog_service.resolve_scan`'s, and
  the order the four FR36 rules are tried in is `scan_router.classify`'s. This
  module only reads the label.
"""

import re
from typing import Dict, Tuple

# The record separator, which appears twice in the grammar and does two
# different jobs: it delimits the format indicator inside the header, and it
# terminates format 06's data. Named because the parser needs it apart from GS.
_RS = '\x1e'

# The group separator that delimits one data record from the next.
_GS = '\x1d'

# The second half of the ISO/IEC 15434 trailer, `RS EOT`. The body normally
# ends at the RS and this character is never reached, but the two arrive as
# separate keystrokes from a wedge and only the RS is also used elsewhere in
# the grammar — so the half-delivered trailer `<data> EOT` is a shape the
# parser must not read as data. EOT terminates the transmission by definition;
# nothing at or after it belongs to any record, exactly as for the RS.
_EOT = '\x04'

# The ISO/IEC 15434 message header for format 06 — the three message-header
# characters, RS, and the format indicator. Composed from `_RS` rather than
# spelled with an escape, so the separator has one definition in this module.
# The format indicator is exactly two digits, so a different one (or a missing
# RS) is a different message envelope, not this one.
_HEADER = f'[)>{_RS}06'

# What may legally follow that header. GS opens the first data record; RS
# closes an empty message. Nothing else may abut the format indicator:
# ISO/IEC 15434 is header RS format-indicator GS ... RS EOT, so a character
# glued straight onto the indicator means the two-digit indicator was never
# actually delimited and the string only *resembles* an envelope. Calling such
# a string an envelope would hand the parser below something it cannot read
# when free text is the honest answer.
_SEPARATORS = (_GS, _RS)

# The seven MH10.8.2 data identifiers AD-15 freezes as the keys of
# `ScanClassification.ecia_fields`, and the ones FR38 requires. FR38 says "at
# minimum", so any other legal MH10.8.2 identifier a distributor prints ('1T'
# lot code, '4L' country of origin, '30P' and the rest) is ignored silently
# rather than treated as an error — an unknown identifier is a label this
# system has no field for, not a damaged scan.
ECIA_FIELD_KEYS: Tuple[str, ...] = ('P', '1P', 'Q', 'K', '1K', '9D', '10D')

# A data identifier: optional digits followed by exactly one uppercase ASCII
# letter, anchored at the start of a record ('P', '1P', '10D', and equally the
# ones above that are ignored). Uppercase only, because MH10.8.2 identifiers
# are uppercase and a lowercase letter is data that happens to lead a record.
# `[0-9]` rather than `\d` for the same reason: `\d` matches Arabic-Indic and
# every other Unicode decimal digit, so '١PABC' would parse as the identifier
# '١P'. Harmless today — no Unicode-digit identifier can equal one of the ASCII
# keys above, so such a record is dropped either way — but the grammar this
# module documents is ASCII, and an implementation that quietly means something
# wider is the kind of gap a later `ECIA_FIELD_KEYS` entry would fall into.
# Compiled once at import: `parse_fields` runs per record, per scan.
_DATA_IDENTIFIER_RE = re.compile(r'[0-9]*[A-Z]')


def is_envelope(value: str) -> bool:
    """
    True if `value` opens with a well-formed ISO/IEC 15434 format-06 header.

    The header alone is judged, not the contents. A header with no body at all
    is still an envelope — a legal, empty message — and so is one whose records
    are unreadable; what happens to such a scan is a routing decision, made by
    `scan_router.classify()` on the strength of what `parse_fields` below can
    actually read out of it (AD-5, NFR8), not a recognition one made here.

    Args:
        value: The candidate string, AIM prefix already removed by the caller
            (`scan_router.strip_aim_prefix`). Judged exactly as it arrived:
            this module trims nothing, so a leading space or separator means
            "not an envelope".

    Returns:
        True for a format-06 envelope, False for a truncated header, a
        different format indicator, or a header not delimited from what
        follows it.

    Raises:
        TypeError: if `value` is not a `str` — a caller fault, not a scan.
    """
    if not isinstance(value, str):
        raise TypeError(
            f'value must be a str, got {type(value).__name__}.')

    if not value.startswith(_HEADER):
        return False
    rest = value[len(_HEADER):]
    # End-of-string is accepted for the same reason a separator is: both mean
    # the two-digit format indicator ended where the standard says it ends.
    return not rest or rest[0] in _SEPARATORS


def parse_fields(value: str) -> Dict[str, str]:
    """
    Extract the AD-15 data identifiers from a format-06 envelope (FR38).

    The grammar, stated once and in full:

    - The message body is everything after the header, truncated at the FIRST
      RS. Per ISO/IEC 15434 the RS after the data terminates format 06, so what
      follows is a different format or the `RS EOT` trailer — either way it is
      not this message's data. The body is truncated at the first EOT as well,
      because the trailer's two characters can arrive apart: a transmission
      that drops the terminating RS but keeps the EOT would otherwise glue that
      control character onto the last record's value, so a label whose part
      number is stored character-for-character would MISS the exact lookup and
      Story 4.5 would pre-fill a create form with `'RC0805-10K\\x04'`. EOT ends
      the transmission by definition, so nothing at or after it is data — the
      same reasoning the RS gets, applied to the character that means it more
      strongly. This is not separator TOLERANCE: it changes no scan's `kind`
      and invents no envelope, it only declines to read a terminator as data.
    - The body splits on GS. Empty elements are skipped: a canonical vector
      opens with a GS (the one introducing the first record) and often closes
      with one, and neither is a record.
    - A data identifier is `<optional digits><one uppercase ASCII letter>` at
      the start of an element; everything after it is the value, VERBATIM — no
      trimming, no case folding, no type coercion. An element that does not
      open with that shape is ignored.
    - Only `ECIA_FIELD_KEYS` are kept; every other legal identifier is ignored.
    - A recognized identifier with an EMPTY value contributes nothing: there is
      nothing to pre-fill a form with and nothing to look a product up by.
    - A repeated identifier keeps its FIRST NON-EMPTY occurrence —
      deterministic, and it preserves the leading record of a label that
      repeats one. The two rules compose in the only order that is useful: an
      empty first occurrence was never recorded, so it cannot shadow a later
      real one, and `'1P' GS '1PABC'` yields `{'1P': 'ABC'}` rather than
      nothing. Stated because "empty is dropped" and "first wins" are
      separately obvious and jointly ambiguous.

    Args:
        value: The candidate string, AIM prefix already removed by the caller.

    Returns:
        A FRESH, plain, mutable `dict` on every call — the caller owns it, and
        `ScanClassification.__post_init__` copies and proxies it, so no state
        is shared between two calls or between this module and a
        classification. `{}` for anything that is not an envelope and for an
        envelope carrying nothing recognized; the classifier reads that empty
        result as "degrade to free text" (AD-5, NFR8).

    Raises:
        TypeError: if `value` is not a `str` — a caller fault, not a scan. No
            `str`, however hostile, raises anything.

    Examples:
        >>> parse_fields('[)>\\x1e06\\x1dP12345\\x1d1PABC\\x1dQ10\\x1d\\x1e\\x04')
        {'P': '12345', '1P': 'ABC', 'Q': '10'}
        >>> parse_fields('RES 10K 0805 1%')
        {}
    """
    if not isinstance(value, str):
        raise TypeError(
            f'value must be a str, got {type(value).__name__}.')

    if not is_envelope(value):
        return {}

    # Both terminators, not just the RS: see the grammar above. Whichever comes
    # first ends the body, so a well-formed `... RS EOT` message is unaffected
    # (its RS is always first) and a half-delivered trailer stops costing the
    # last record its value.
    body = value[len(_HEADER):].split(_RS, 1)[0].split(_EOT, 1)[0]

    fields: Dict[str, str] = {}
    for element in body.split(_GS):
        match = _DATA_IDENTIFIER_RE.match(element)
        if match is None:
            continue
        identifier = match.group()
        data = element[match.end():]
        # Three conditions, none of them redundant: an identifier this system
        # has no field for is ignored (FR38 is a minimum, not a whitelist), an
        # empty value carries nothing, and a repeat loses to the first
        # occurrence — first NON-EMPTY, since an empty one never landed in
        # `fields` to shadow it.
        if identifier in ECIA_FIELD_KEYS and data and identifier not in fields:
            fields[identifier] = data
    return fields
