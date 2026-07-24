"""
GS1 element-string grammar for internal identifiers (Story 2.4).

This module is the single source of truth for how a workshop-internal
identifier is encoded into, and recognized out of, a GS1 element string
(AD-16). Encoder and scan router both call in here, so the two can never drift
apart. It is a PURE module: standard library only, no Flask/DB/app-package
imports, no I/O. Its only failure signal is `InvalidGs1PayloadError`, a plain
`ValueError` subclass; the service layer translates it into a domain
`ValidationError`.

The element string
------------------
One element string, built from exactly four parts in this order:

    <FNC1><ai><token><internal_id>

- `FNC1` — the GS character `0x1D`, emitted in first position.
- `ai`   — the Application Identifier (the deployed value is `96`).
- `token` — a short literal (the deployed value is `WIT`) that opens the single
  variable-length data field.
- `internal_id` — the rest of that data field.

There is no separator, no second AI, and nothing appended. `ai` and `token` are
keyword-only with **no defaults**: the caller supplies both from one named
config pair, so a single config change moves encoder and decoder together
(FR12c).

Why the token exists
--------------------
AI 96 is a general-purpose company-internal AI, so a foreign barcode may
legitimately carry it. The token is what makes an internal symbol
self-identifying: a payload whose data field does not open with the configured
token is not one of ours, and `decode` returns None for it rather than
resolving it to a product (FR12a).

FNC1 transmission variance
--------------------------
Scanners disagree about FNC1. `decode` therefore absorbs all three
transmissions it can arrive as: the GS character itself, a
configured substitute character, or stripped entirely — the deployed hardware
does the last of these, so the bare string `96WITxxxxxxxxxx` must decode. It
also tolerates surrounding whitespace, including the trailing CR/LF that a
keyboard-wedge scanner appends. `decode` never raises on `raw` (NFR8): a
scan is untrusted input, and unrecognized input is a None, not an exception.

The bounded data field
----------------------
AI 96 sits in the GS1 company-internal series (90-99). That series' data field
was `X..30` until GSCN 16-000528 ("AI 91 to 99 - Data Length Extension",
effective 2017-07-31) raised it to `X..90`, which is the current General
Specifications limit. `MAX_DATA_FIELD_LENGTH` deliberately pins the older, three
times tighter 30 rather than tracking the ceiling: this grammar's whole data
field is a 3-character token plus a 10-character id, so 30 is already more than
double anything it can legitimately produce, and the tighter bound dismisses a
garbled or hostile scan that much sooner. Both sides of the pair enforce it
(Story 2.5).

It is a bound on the element string's own field, not on our id: the id's shape
(its length, its alphabet) belongs to `app/utils/internal_id.py` and is
deliberately not duplicated here, because an encoder that re-derives the id's
rules is the drift AD-16 exists to prevent. Raising the constant to 90 would
stay standards-conformant; adding `is_valid_internal_id` here would not be the
same kind of change at all. The bound has teeth either way — without it, any
foreign scan that happens to open with `96WIT` yields an unbounded `internal_id`
that a future resolver (Epic 4) would carry into a DB query, and that the
UNTRUSTED `raw` field would carry into logs today.

Ownership text is not encoded (FR12d)
-------------------------------------
Ownership/return information is human-readable label text only, composited into
the label's text region by Epic 6 and reached through
`CatalogService.ownership_label_text()`. No 43xx element string is ever
produced: rather than leave that a documented intention, both `encode` and
`decode` refuse outright any grammar whose element string would open `43`, so
the negative is a machine-checked invariant. There is exactly one encoder and
its AI comes from config, so a reconfigured `GS1_INTERNAL_AI` was the only way
such a string could ever have appeared; it now fails loudly at the first encode.

The invariant is about the AI, not about the text. Nothing stops a caller from
handing ownership text to `encode` as an `internal_id` — a string with a space
in it is refused, but a short one like `ReturnTo:J.Antman` is not. What holds
the two regions apart is that no code path passes `ownership_label_text()` into
this module at all; the character rule is a backstop for the common case, not
the guarantee.

Future extensibility:
--------------------
`decode` deliberately does NOT strip an AIM symbology identifier (e.g. `]d1`) —
per FR37 that belongs to the scan classifier, which inspects the prefix before
delegating here. A renderer that needs the bare data field without FNC1 should
gain a parameter on `encode` here rather than re-deriving the grammar somewhere
else.
"""

from dataclasses import dataclass
from typing import Any, Optional

# FNC1 is transmitted as the ASCII group separator (GS, 0x1D).
FNC1 = '\x1d'

# The most characters the single variable-length data field (token + id) may
# carry. The GS1 company-internal series (AIs 90-99) permits `X..90` since GSCN
# 16-000528 (2017); 30 is this module's deliberately tighter cap — see "The
# bounded data field" above. Raising it is a standards-conformant change; the
# constant exists so that decision is made in one place.
MAX_DATA_FIELD_LENGTH = 30

# No element string may open with this prefix. FR12d: ownership / return
# information is human-readable label text, never an encoded element string, and
# the 43xx logistics AIs are where such information would otherwise be carried.
# Matched against the AI+token marker rather than the AI alone — the marker is
# what an element string actually opens with, so one comparison catches both a
# 43xx AI and a split configuration (ai='4', token='311') that assembles the
# identical string. Matched as a prefix, so the whole 43nn range goes at once.
_FORBIDDEN_AI_PREFIX = '43'


def _is_encodable_id_char(char: str) -> bool:
    """
    True if `char` may appear inside the data field.

    The accepted set is 0x21-0x7E: printable ASCII excluding the space. Anything
    at or below 0x20, DEL (0x7F), or above it is either a control or whitespace
    character that would break the element string (FNC1 itself among them) or
    outside what a GS1 symbology encodes. The space is excluded too — it is
    printable, but a data field is a single unbroken token and a space in a
    scanned id is a transmission artefact, never part of the id.
    """
    return 0x20 < ord(char) < 0x7f


class InvalidGs1PayloadError(ValueError):
    """
    Raised when a payload cannot be encoded: a blank/padded/non-string `ai` or
    `token`, a grammar whose marker opens `43` (FR12d), a token that leaves no
    room for an id, an `internal_id` that is blank, not a string, or carries a
    character outside printable ASCII (a rule `ai` and `token` are held to as
    well — every part of the element string must be encodable), or a data field
    longer than `MAX_DATA_FIELD_LENGTH`. A plain `ValueError` subclass so this
    module stays free of any framework dependency; callers translate it into a
    domain error.

    The split is by *source*, not by condition: a fault in the configured
    grammar raises out of both functions, while anything wrong with `raw` — an
    oversized data field included — is only ever a None from `decode`, which
    never raises on scan data (NFR8). So an overlong payload is an exception
    when `encode` is asked to build it and a None when `decode` is asked to
    recognize it, and a scanned string opening `43` is simply foreign: it fails
    the marker match like any other non-matching payload, with the
    `_FORBIDDEN_AI_PREFIX` rule never consulted.
    """


@dataclass(frozen=True)
class InternalPayload:
    """
    A successfully recognized internal element string.

    Frozen so a decoded scan cannot be mutated downstream. Carries the grammar
    it was decoded under alongside the extracted id, so a caller never has to
    re-read config to know which AI/token matched.

    Attributes:
        internal_id: The identifier extracted from the data field.
        ai: The Application Identifier the payload matched.
        token: The literal token the data field opened with.
        raw: The exact input string as received, before whitespace/FNC1
            handling — kept verbatim for audit and troubleshooting. UNTRUSTED:
            unlike `internal_id`, it is not character-filtered, so it may still
            carry the CR/LF a keyboard-wedge scanner appended (or anything else
            that arrived). Escape it (`repr`/`!r`) before writing it to a log —
            interpolating it raw is a log-forging vector.
    """

    internal_id: str
    ai: str
    token: str
    raw: str


def _require_grammar_part(name: str, value: Any) -> str:
    """
    Validate one half of the configured grammar (`ai` or `token`).

    Args:
        name: The parameter name, for the error message.
        value: The supplied value.

    Returns:
        The value unchanged.

    Raises:
        InvalidGs1PayloadError: if the value is not a non-blank string, carries
            surrounding whitespace, or contains a character `encode` would
            refuse inside the data field. A blank token in particular would
            defeat FR12a by making every foreign AI-96 barcode look internal,
            and a padded one (`GS1_INTERNAL_AI=96 ` in a .env file, invisible in
            an editor) would be concatenated into every element string —
            silently malforming every printed symbol while still round-tripping
            through this module's own decode. The character rule is the same one
            the id is held to, for the same reason and with the same blind spot:
            an interior space or control character (`GS1_INTERNAL_AI=9 6`, or a
            stray FNC1 that would split the data field) is just as unencodable
            in the prefix as in the id, and just as invisible to a round-trip
            test that reads the malformed value back out of the same config.
    """
    if not isinstance(value, str) or not value.strip():
        raise InvalidGs1PayloadError(
            f'{name} must be a non-blank string, got {value!r}.')
    if value != value.strip():
        raise InvalidGs1PayloadError(
            f'{name} must not carry surrounding whitespace, got {value!r}.')
    if not all(_is_encodable_id_char(char) for char in value):
        raise InvalidGs1PayloadError(
            f'{name} must contain only printable ASCII, with no interior '
            f'whitespace or control characters, got {value!r}.')
    return value


def _require_grammar(ai: Any, token: Any) -> str:
    """
    Validate the configured grammar as a whole and return its marker.

    Everything `_require_grammar_part` demands of each half, plus the two rules
    that only make sense once the halves are put together.

    Args:
        ai: The supplied Application Identifier.
        token: The supplied token.

    Returns:
        The marker `ai + token` — the exact prefix every element string under
        this grammar opens with.

    Raises:
        InvalidGs1PayloadError: if either half is malformed on its own, if the
            marker opens `43`, or if the token leaves no room for an id.

            **The 43 rule.** The 43xx AIs are GS1's logistics series — 4311 is
            return-to contact name, and the rest of the range carries the same
            kind of ship-to/return-to data — and FR12d's testable consequence is
            the negative "no 43xx element string is ever encoded". Enforcing it
            here converts that intention into an invariant: the grammar comes
            from config, so a reconfigured `GS1_INTERNAL_AI` was the only route
            by which such a string could have been produced, and it now fails at
            the first encode rather than printing a symbol that misrepresents
            ownership as machine-readable data. It is checked against the
            **marker** rather than the AI alone, so the split configuration
            `ai='4', token='311'` — which assembles the identical element string
            — cannot slip past it. Matching the marker does over-bar slightly:
            a single-character `ai='4'` with a token opening `3` is refused even
            though no 43xx AI is involved. That is accepted deliberately, since
            the PRD addendum rejected AI 4311 outright and nothing the addendum
            leaves legitimate lands in the over-barred corner — but it is the
            price of one comparison, not literally zero. Only a leading `43` is
            barred (FR12c preserved), and `decode` applies the same rule so the
            pair stays closed.

            **The token-room rule.** A token at or beyond
            `MAX_DATA_FIELD_LENGTH` leaves no characters for an id, so `encode`
            could never produce a payload and `decode` would return None for
            every scan of a genuine label — a total, silent outage of both
            directions. This module's standing choice is that a malformed
            grammar fails loudly at once rather than degrading into "nothing
            scans", so it is rejected here.
    """
    _require_grammar_part('ai', ai)
    _require_grammar_part('token', token)

    marker = ai + token
    if marker[:2] == _FORBIDDEN_AI_PREFIX:
        raise InvalidGs1PayloadError(
            f'no element string may open {_FORBIDDEN_AI_PREFIX}xx: ownership '
            f'and return information is human-readable label text only and is '
            f'never encoded as an element string (FR12d); ai={ai!r} and '
            f'token={token!r} would build {marker!r}.')
    if len(token) >= MAX_DATA_FIELD_LENGTH:
        raise InvalidGs1PayloadError(
            f'token must be shorter than the {MAX_DATA_FIELD_LENGTH}-character '
            f'data field so an id can follow it, got {len(token)}: {token!r}.')
    return marker


def encode(internal_id: str, *, ai: str, token: str) -> str:
    """
    Build the single GS1 element string for an internal identifier.

    The result is `FNC1 + ai + token + internal_id` — one element string, FNC1
    first, one variable-length data field, no separator and nothing appended
    (FR12b).

    Args:
        internal_id: The identifier to encode.
        ai: The Application Identifier. Keyword-only, no default (FR12c).
        token: The literal opening the data field. Keyword-only, no default.
            Together `ai` and `token` must not build a marker opening `43`
            (FR12d).

    Returns:
        The element string, ready to be rendered as a symbol.

    Raises:
        InvalidGs1PayloadError: if the grammar is malformed — see
            `_require_grammar` — or if `internal_id` is blank, not a string, or
            contains a control or whitespace character (which includes FNC1
            itself — an embedded separator would silently split the data
            field), or if the resulting data field (`token + internal_id`) is
            longer than `MAX_DATA_FIELD_LENGTH`.

    Examples:
        >>> encode('ABC1234567', ai='96', token='WIT') == '\\x1d96WITABC1234567'
        True
    """
    marker = _require_grammar(ai, token)

    if not isinstance(internal_id, str):
        # Non-str input fails as InvalidGs1PayloadError, never a raw TypeError
        # from string concatenation, so callers only ever catch this module's
        # one failure signal.
        raise InvalidGs1PayloadError(
            f'internal_id must be a string, got '
            f'{type(internal_id).__name__}: {internal_id!r}.')
    if not internal_id:
        raise InvalidGs1PayloadError('internal_id must not be blank.')
    # The id is never trimmed or repaired: an id carrying whitespace, a control
    # character or a non-ASCII character is a bug upstream, and silently fixing
    # it would encode a value that no longer matches the stored one.
    if not all(_is_encodable_id_char(char) for char in internal_id):
        raise InvalidGs1PayloadError(
            f'internal_id must contain only printable ASCII, with no '
            f'whitespace or control characters: {internal_id!r}.')
    # The bound is on the whole data field, token included, because the token is
    # what the AI's format counts: `96WIT...` is one field of `len(token) +
    # len(internal_id)` characters, not two. This is a rule about the element
    # string's field, not about the id's shape — see the module docstring for
    # why that distinction is load-bearing.
    if len(token) + len(internal_id) > MAX_DATA_FIELD_LENGTH:
        raise InvalidGs1PayloadError(
            f'the data field (token + internal_id) must be at most '
            f'{MAX_DATA_FIELD_LENGTH} characters, got '
            f'{len(token) + len(internal_id)}: {internal_id!r}.')

    # Built from the marker `_require_grammar` returned, which is the same value
    # `decode` matches against. The two functions therefore agree on what an
    # element string opens with by construction rather than by both spelling out
    # `ai + token` — the encoder/decoder drift AD-16 exists to prevent.
    return FNC1 + marker + internal_id


def decode(raw: Any, *, ai: str, token: str,
           fnc1_substitute: Optional[str] = None) -> Optional[InternalPayload]:
    """
    Recognize an internal element string, or return None.

    Never raises on `raw` (NFR8) — a scan is untrusted input, so anything that
    is not an internal payload under the supplied grammar simply returns None.
    Steps: non-string returns None; surrounding whitespace (including a
    scanner's trailing CR/LF) is stripped; one leading FNC1 — the GS character
    or `fnc1_substitute` — is removed if present; the remainder must open with
    exactly `ai + token` and leave behind a data field that is within
    `MAX_DATA_FIELD_LENGTH` and an identifier that is non-empty and
    printable ASCII (the same rules `encode` enforces, so the pair
    round-trips).

    Args:
        raw: The scanned/received string. Any object is accepted.
        ai: The Application Identifier to match. Keyword-only, no default.
        token: The literal the data field must open with. Keyword-only, no
            default; a payload without it is foreign and yields None (FR12a).
            `ai + token` must not open `43` (FR12d) — barred here purely to keep
            the pair closed with `encode`, which is where the invariant bites.
        fnc1_substitute: An extra single character some scanners emit in place
            of GS. Optional; None means only GS (or nothing) is recognized.
            Validated like the rest of the grammar — a multi-character value
            would silently eat part of the AI, making every scan return None.

    Returns:
        An `InternalPayload` if the input matches the grammar, else None.

    Raises:
        InvalidGs1PayloadError: only if the grammar (`ai`, `token`, or
            `fnc1_substitute`) is malformed — a configuration fault, never a
            property of `raw`. See `_require_grammar`.

    Examples:
        >>> decode('96WITABC1234567', ai='96', token='WIT').internal_id
        'ABC1234567'
        >>> decode('0109506000134352', ai='96', token='WIT') is None
        True
    """
    marker = _require_grammar(ai, token)
    if fnc1_substitute is not None:
        # The third grammar knob, held to the same standard as ai/token — but
        # checked here rather than by _require_grammar_part, which forbids
        # whitespace and would therefore reject GS itself. A non-string would
        # make startswith() raise TypeError out of a function contracted never
        # to raise on scan data; a multi-character value would strip more than
        # the separator (fnc1_substitute='96' silently eats the AI, so every
        # scan returns None).
        if not isinstance(fnc1_substitute, str) or len(fnc1_substitute) != 1:
            raise InvalidGs1PayloadError(
                f'fnc1_substitute must be a single character or None, got '
                f'{fnc1_substitute!r}.')

    if not isinstance(raw, str):
        return None

    # str.strip() already removes leading/trailing GS characters (Python counts
    # 0x1C-0x1F as whitespace), which is exactly the tolerance we want, so the
    # FNC1 arm of the loop below is redundant-but-explicit: it documents the
    # grammar rather than doing work. Only the substitute arm can actually fire.
    candidate = raw.strip()
    if not candidate:
        return None

    for prefix in (FNC1, fnc1_substitute):
        if prefix and candidate.startswith(prefix):
            candidate = candidate[len(prefix):]
            break

    if not candidate.startswith(marker):
        return None

    internal_id = candidate[len(marker):]
    if len(token) + len(internal_id) > MAX_DATA_FIELD_LENGTH:
        # Checked before the character scan below and before any payload is
        # built, so a 100 KB scan that happens to open with `96WIT` is dismissed
        # on its length rather than walked character by character. That is a
        # bound on the work done here, not on the memory: `raw.strip()` and the
        # slice above have already copied the input twice, and shortcutting that
        # would mean length-checking `raw` itself, before the FNC1 and
        # whitespace tolerance this module exists to provide. An overlong data
        # field exceeds what this grammar can encode, so it is a foreign
        # payload — a None, never an exception (NFR8).
        return None
    if not internal_id:
        # AI + token with an empty data field is not an identifier (FR12a).
        return None
    if not all(_is_encodable_id_char(char) for char in internal_id):
        # The data field only ever holds what encode() would have emitted, so a
        # payload carrying an interior control character (a garbled scan, or a
        # CR/LF that would forge a second line in the audit log) is not one of
        # ours. Rejecting here also closes the round trip: whatever decode
        # returns, encode accepts.
        return None

    return InternalPayload(internal_id=internal_id, ai=ai, token=token, raw=raw)
