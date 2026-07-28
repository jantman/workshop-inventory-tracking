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
Exactly five rules, tried in this order, first match wins, and rule 5 always
matches — so every scan is classified and none dead-ends:

1. An internal element string under the configured grammar -> `INTERNAL`.
2. An ISO/IEC 15434 format-06 envelope carrying at least
   one recognized data identifier                        -> `ECIA`.
3. A GS1 element string opening with AI 01 -> its trade item number becomes
   the value rule 4 judges.
4. A check-digit-valid trade item number                 -> `GTIN`.
5. Anything else                                         -> `FREE_TEXT`.

The order is not arbitrary. Rules 1 and 4 overlap by construction: an internal
payload whose configured token happens to be numeric can also be a
check-digit-valid all-digit string, so an ordering is required and "ours wins"
is the only safe one — a label this shop printed must never resolve to somebody
else's trade item. Rule 2 precedes the rest only because an envelope is never
all-digits; the ordering there is documentation, not arbitration.

Rule 3 is the odd one: it is not a classification at all but a *substitution*,
which is why it has no `ScanKind` of its own. A manufacturer's GS1-128 or GS1
DataMatrix carries a GTIN as the element string `01` + 14 digits, and once
those digits are extracted the scan simply *is* a GTIN scan — so rule 3 hands
them to rule 4 and every question of GTIN validity is answered exactly once, by
the arm a bare GTIN already went through. It cannot steal a bare GTIN from rule
4 either: an AI-01 match needs at least 16 characters and every length rule 4
accepts is 8, 12, 13 or 14, so the two candidate sets are disjoint.

Rule 2 is the one rule that can recognize its own shape and still decline. A
valid format-06 header wrapping nothing this system can read — an empty
message, or records in no identifier grammar — does NOT classify `ECIA`: it
falls through to rules 3-5 and lands on `FREE_TEXT` carrying the raw scan
(AD-5, NFR8). `ECIA` exists so a consumer can pre-fill a form from named
fields, and answering it with no fields would put the operator on a screen that
says "distributor label" about a scan nothing could be read from, while
`free_text` puts the raw scan into a search — which is what "surfaced for
manual handling" means everywhere else in this epic. The consequence worth
stating: `kind is ECIA` implies `ecia_fields` is a NON-EMPTY mapping, because
this module is its only producer.

What this module deliberately does not do
-----------------------------------------
- **No lookup.** No database, no `CatalogService`, no fallthrough-to-search.
  `resolve_scan()` and `search_products()` belong to Story 4.3 (AD-4/AD-5), and
  a classifier that could touch a session would not be callable from Epic 7.
- **No element-string matching of its own (AD-16).** Rules 1 and 3 are
  delegated whole to `app/utils/gs1.py`, which owns GS1 element-string grammar
  — `gs1.decode()` for the internal one, `gs1.decode_trade_item_number()` for
  AI 01. This module never pattern-matches an Application Identifier, holds no
  AI literal and no literal default for the internal grammar, and does no
  element-string field arithmetic. The internal pair arrives as keyword
  arguments from the one named config pair the service reads, exactly as
  `mariadb_catalog_service.encode_internal_payload` already passes them into
  `gs1.encode` — so one config change moves the encoder and this router
  together, with no code edit. AI 01 takes no argument at all, because GS1
  assigns it and this deployment does not.
- **No check-digit or 14-digit arithmetic (AD-16 again).** Rules 3 and 4 share
  **one** arm, which makes exactly one call, `gtin.normalize_gtin`, and reads
  its refusal as "not a GTIN". Every question of GTIN validity stays in
  `app/utils/gtin.py` — the accepted lengths, the mod-10 weights, the canonical
  key length, and the refusal of an all-zero run (the wedge no-read), which
  reaches the arm as an ordinary `InvalidGtinError` and falls through to
  `free_text` with no code here. A local zero-run test would be the second copy
  of GTIN validity this bullet exists to prevent. Sharing one arm is what makes
  "an AI-01 scan resolves exactly as the bare number would" a structural fact
  rather than two implementations that currently agree.
- **No format-06 grammar of its own (AD-16 again).** Rule 2 is delegated whole
  to `app/utils/ecia.py`, which owns the message header, envelope recognition
  and the MH10.8.2 identifier grammar. This module never re-derives the header
  and never reads a data record; it asks `ecia.is_envelope` and
  `ecia.parse_fields` and decides only what their answers mean for routing. A
  second copy of the header literal is exactly the defect this repo keeps
  finding in itself, so there is exactly one copy anywhere under `app/`, and it
  is `ecia.py`'s.
- **No trimming of its own.** `classify()` never trims. Its caller has already
  applied the single cleaning rule (`clean_scan_input` in
  `app/utils/scan_input.py`, which trims space/tab/CR/LF and nothing else,
  because a bare `str.strip()` would eat the RS that terminates an envelope).
  Re-cleaning here would be a third copy of that rule rather than a shared one.

  Be precise about what that does *not* say. Rules 1 and 3 are delegated to
  `app/utils/gs1.py`, and both of its recognizers begin with `raw.strip()` as
  their FNC1/CR-LF transmission tolerance — they read element strings arriving
  from the same symbologies through the same wedge, so they share one
  transmission policy. A padded internal payload therefore classifies as
  `INTERNAL`, and since DW-70 a padded AI-01 element string classifies as
  `GTIN`, while a padded *bare* GTIN or envelope does not. The two policies are
  asymmetric on purpose — the tolerance belongs to the grammar that needs it,
  and inventing a matching tolerance here would be the third copy of the trim
  rule — but the asymmetry is real, it is pinned by tests, and it means correct
  routing for rules 2, 4 and 5 depends on the caller having cleaned the input.
  It also means a leading space defeats the AIM strip below. Note the line the
  asymmetry falls on is which *module* judges the value, not which kind comes
  out: the same `GTIN` classification tolerates padding when it arrived inside
  an element string and refuses it when it arrived bare.

  And it does not stop at spaces, which is the half worth stating out loud.
  Python's `str.strip()` also eats `\x1c`-`\x1f`, so both `gs1` recognizers
  absorb a transmitted GS/RS while `clean_scan_input` deliberately does not
  — that cleaner exists precisely to preserve the separators an envelope is
  built from. Net effect: a wedge that prefixes a GS routes an internal label
  correctly (`'\x1d' + internal` -> INTERNAL) and misroutes a distributor
  label (`'\x1d' + envelope` -> FREE_TEXT), because rule 2 anchors on the
  header and judges the scan as it arrived. An FNC1-framed AI-01 element
  string is on the tolerant side, being rule 3's, so a GS-framed
  manufacturer barcode routes correctly where a GS-framed envelope does not.
  Neither this module nor the cleaner can close that alone — absorbing
  separators here would re-open the trim rule this module refuses to own, and
  stripping them in the cleaner would destroy the envelope's structure — so
  the case is pinned by
  `TestWhitespaceAsymmetryBetweenRules` and left to the story that owns the
  caller seam. It has never been observed on the deployed Tera HW0009, which
  emits no separator prefix at all.

- **No consumer contract beyond `ScanClassification`.** In particular, the
  candidate this module classifies (AIM prefix removed) is not carried on the
  result: AD-15 freezes exactly four fields and `raw` is the verbatim scan. A
  consumer that needs to *use* the scan text rather than classify it — Story
  4.3's resolver searching free text, for instance — must call the exported
  `strip_aim_prefix()` on `raw` first, or it will search for a string that
  still begins `]d1`. That helper is public for exactly this reason;
  re-deriving the AIM shape in a second place is what it prevents. The envelope
  parse is the one case a consumer does NOT have to do this for: `classify()`
  runs `ecia.parse_fields` on the AIM-stripped candidate itself and carries the
  result on `ecia_fields`, so `']d1' + envelope` yields exactly the fields the
  bare envelope does and nothing downstream re-parses `raw`.

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
from app.utils import ecia
from app.utils import gs1
from app.utils import gtin

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
    here, at the front, means all five rules see the same candidate and no rule
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


def classify(raw: Any, *, ai: str, token: str) -> ScanClassification:
    """
    Classify one captured scan by structure (FR36, FR37).

    Applies the five precedence rules described in the module docstring and
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
        A `ScanClassification`. `ecia_fields` is a non-empty mapping when
        `kind` is `ECIA` and None for every other kind — an envelope with
        nothing readable in it degrades to `FREE_TEXT` rather than to an empty
        mapping (see the module docstring). A `GTIN` result carries the
        canonical 14-digit key whether the number arrived bare or inside an
        AI-01 element string: rules 3 and 4 share one arm, so the two forms of
        one product are indistinguishable downstream except through `raw`.

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

        Rule 3 has the mirror-image exit, and it is deliberate: an AI-01
        element string is *recognized* by `gs1.decode_trade_item_number` but
        *judged* by rule 4, so `'0109506000134353'` (a broken check digit) and
        `'0100000000000000'` (the wedge no-read) are recognized, refused and
        fall through to `FREE_TEXT` — exactly as the bare numbers inside them
        would. There is no separate AI-01 failure path to keep in step.

    Examples:
        The grammar below is illustrative, not the deployed one — this module
        holds no literal default for either half (AD-16).

        >>> c = classify('91ZZABC1234567', ai='91', token='ZZ')
        >>> c.kind is ScanKind.INTERNAL, c.normalized_value
        (True, 'ABC1234567')
        >>> classify('9506000134352', ai='91', token='ZZ').normalized_value
        '09506000134352'
        >>> classify('0109506000134352', ai='91', token='ZZ').normalized_value
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

    # Rule 2 — a distributor envelope. Delegated whole to the format-06 grammar
    # module, exactly as rules 1 and 3 are delegated to gs1 and rule 4 to
    # gtin: this module asks the questions and arbitrates, and re-derives none
    # of the grammars.
    # Nothing to normalize — an envelope's content is its fields.
    #
    # The `if fields` is the NFR8 degradation, not an optimization: a valid
    # header carrying nothing recognized falls out of this branch and lands on
    # rule 5 with the raw scan, because an `ECIA` classification with nothing
    # in it is a kind whose whole purpose (pre-filling a form) has no input.
    # Neither call can raise on a `str`, so no rule below is reachable only by
    # luck.
    if ecia.is_envelope(candidate):
        fields = ecia.parse_fields(candidate)
        if fields:
            return ScanClassification(
                kind=ScanKind.ECIA,
                normalized_value=None,
                # A fresh dict per call, which `__post_init__` copies into a
                # read-only proxy — so two classifications of one scan share
                # no mutable state.
                ecia_fields=fields,
                raw=raw,
            )

    # Rule 3 — a manufacturer's AI-01 element string. Delegated whole to the
    # Epic 2 grammar module, exactly as rule 1 is: this module asks whether an
    # element string carrying a trade item number was scanned and takes the
    # digits, and holds no AI literal and no field arithmetic of its own
    # (AD-16). Like `gs1.decode` it never raises and absorbs the same FNC1 and
    # whitespace transmission variance.
    #
    # This is a substitution, not a classification — it produces no kind and no
    # early return, it only changes *which value* rule 4 judges. A miss cannot
    # lose a bare GTIN: an AI-01 match needs at least 16 characters (the
    # two-digit AI plus its 14-digit field) and every length rule 4 accepts is
    # 8, 12, 13 or 14, so the two candidate sets are disjoint and `candidate`
    # is what a non-match falls back to.
    #
    # It widens one thing worth stating out loud, because a consumer could
    # reasonably have assumed otherwise before DW-70: `raw` on a `GTIN`
    # classification is NO LONGER ASCII digits by construction. Until rule 3
    # existed, the only route to `GTIN` was the guard below, so a `GTIN`
    # classification's `raw` was always an optional AIM prefix plus digits.
    # A rule-3 hit now carries whatever the wedge sent — separators, a batch
    # and serial, trailing text, a lone surrogate — while `normalized_value`
    # stays exactly as narrow as it ever was. Read `normalized_value` for the
    # key; treat `raw` as untrusted scan data on every kind alike. The one
    # consumer that feeds `raw` onward is `_fallthrough_text`, whose
    # `search_products` landing already refuses unstorable text, and
    # `TestGtinRawIsNoLongerDigitsByConstruction` pins the widening so it
    # cannot be re-assumed silently.
    trade_item = gs1.decode_trade_item_number(candidate)
    gtin_candidate = candidate if trade_item is None else trade_item

    # Rule 4 — a trade item number, however it arrived. The ASCII-digit guard is
    # load-bearing rather than a restatement of what `normalize_gtin` checks:
    # `normalize_gtin` deliberately tolerates surrounding whitespace, and
    # Python counts GS/RS (\x1c-\x1f) as whitespace, so without this guard
    # '\x1d9506000134352' — a fragment of a distributor label — would classify
    # as a clean GTIN. A scan is judged as it arrived. The accepted lengths,
    # the check digit and the all-zero refusal stay behind `normalize_gtin`;
    # re-listing {8, 12, 13, 14} here — or re-testing for a zero run — would be
    # the second copy AD-16 exists to prevent. The guard is redundant for a
    # rule-3 hit, whose digits are ASCII by construction, and is kept as one
    # test rather than split so there is exactly one arm to keep correct.
    #
    # Normalization is attempted inside the guard rather than after asking
    # `is_valid_gtin` first, so NFR8 holds structurally rather than by luck.
    # `is_valid_gtin` happens to be implemented as try/normalize/except today,
    # which is why the two-call form could not raise — but that is a private
    # detail of gtin.py, and any future divergence between the predicate and
    # the normalizer would let `InvalidGtinError` escape a function contracted
    # never to raise on scan data. One call, one try, no double parse.
    if gtin_candidate.isascii() and gtin_candidate.isdigit():
        try:
            return ScanClassification(
                kind=ScanKind.GTIN,
                normalized_value=gtin.normalize_gtin(gtin_candidate),
                ecia_fields=None,
                raw=raw,
            )
        except gtin.InvalidGtinError:
            # Not a trade item number after all — fall through to rule 5. One
            # `except` for both rules, so an AI-01 payload with a broken check
            # digit or an all-zero no-read is refused by the same code that
            # refuses the bare number, rather than by a second copy of it.
            pass

    # Rule 5 — the fallthrough, which always matches. Not an error and not a
    # failure: an unrecognized scan is a search, and Story 4.5 lands it on
    # results or on a pre-filled create form.
    return ScanClassification(
        kind=ScanKind.FREE_TEXT,
        normalized_value=None,
        ecia_fields=None,
        raw=raw,
    )
