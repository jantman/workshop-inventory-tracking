"""
Unit tests for the pure GS1 module (Stories 2.4 and 2.5, app/utils/gs1.py).

Exercises encode / decode / InternalPayload and the pure rows of both stories'
I/O & edge-case matrices. This module is the single source of truth for the
AI-96 element-string grammar, so it is tested here in isolation (no Flask/DB),
with particular attention to (a) FNC1 transmission variance, (b) foreign
payloads never resolving as internal ones — exhaustively, by barcode family, in
TestForeignPayloadRejection — and (c) the two grammar bounds Story 2.5 added:
the data field's length and the barred 43xx AI series.
"""

import copy
import dataclasses
import inspect
import pickle

import pytest

from app.utils.gs1 import (
    FNC1,
    MAX_DATA_FIELD_LENGTH,
    InternalPayload,
    InvalidGs1PayloadError,
    decode,
    decode_trade_item_number,
    encode,
)

# The deployed grammar (config defaults GS1_INTERNAL_AI / GS1_INTERNAL_TOKEN).
AI = '96'
TOKEN = 'WIT'
ID = 'ABC1234567'

# The other element string this module recognizes (DW-70): GS1's AI 01, whose
# predefined-length field is a 14-digit trade item number. `TRADE_ITEM` is the
# canonical form of the EAN-13 `9506000134352` the rest of the repo uses as its
# GTIN vector, and `EL` is the element string a manufacturer encodes it as.
TRADE_ITEM = '09506000134352'
EL = '01' + TRADE_ITEM


class TestEncode:

    @pytest.mark.unit
    def test_emits_one_element_string_fnc1_first(self):
        assert encode(ID, ai=AI, token=TOKEN) == '\x1d96WITABC1234567'

    @pytest.mark.unit
    def test_structure_is_fnc1_then_ai_then_token_then_id(self):
        """Nothing between the parts, and nothing appended (FR12b)."""
        out = encode(ID, ai=AI, token=TOKEN)
        assert out[0] == FNC1
        assert FNC1 == '\x1d'
        assert out == FNC1 + AI + TOKEN + ID
        assert out.count(FNC1) == 1          # no second AI / separator
        assert len(out) == 1 + len(AI) + len(TOKEN) + len(ID)

    @pytest.mark.unit
    def test_ai_and_token_are_keyword_only_with_no_defaults(self):
        """FR12c: the grammar must always be supplied explicitly."""
        with pytest.raises(TypeError):
            encode(ID)                       # no ai/token at all
        with pytest.raises(TypeError):
            encode(ID, AI, TOKEN)            # positional

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_id', ['', None, 123, b'ABC1234567', 12.0, ['A']])
    def test_blank_or_non_str_internal_id_rejected(self, bad_id):
        with pytest.raises(InvalidGs1PayloadError):
            encode(bad_id, ai=AI, token=TOKEN)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_ai', ['', '   ', None, 96])
    def test_blank_or_non_str_ai_rejected(self, bad_ai):
        with pytest.raises(InvalidGs1PayloadError):
            encode(ID, ai=bad_ai, token=TOKEN)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_token', ['', '   ', None, 0])
    def test_blank_or_non_str_token_rejected(self, bad_token):
        """A blank token would make every foreign AI-96 payload look internal."""
        with pytest.raises(InvalidGs1PayloadError):
            encode(ID, ai=AI, token=bad_token)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_id', [
        'ABC\x1d234567',    # embedded FNC1 — would split the data field
        'ABC 234567',       # space
        'ABC\t234567',      # tab
        'ABC\n234567',      # newline
        'ABC\r234567',      # carriage return
        ' ABC1234567',      # leading space (never silently trimmed)
        'ABC1234567 ',      # trailing space
        'ABC\x00234567',    # NUL
        'ABC\x7f234567',    # DEL
    ])
    def test_whitespace_or_control_characters_in_id_rejected(self, bad_id):
        with pytest.raises(InvalidGs1PayloadError):
            encode(bad_id, ai=AI, token=TOKEN)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_id', ['ABC123456é', 'ABC 234567', 'ÄBC1234567'])
    def test_non_ascii_id_rejected(self, bad_id):
        """The data field is printable ASCII; nothing else is GS1-encodable."""
        with pytest.raises(InvalidGs1PayloadError):
            encode(bad_id, ai=AI, token=TOKEN)

    @pytest.mark.unit
    @pytest.mark.parametrize('padded', [' 96', '96 ', '\t96'])
    def test_padded_ai_rejected(self, padded):
        """A '.env' value with an invisible trailing space would otherwise be
        concatenated into every element string — and still round-trip through
        this module, hiding the fault until a third-party parser reads it."""
        with pytest.raises(InvalidGs1PayloadError):
            encode(ID, ai=padded, token=TOKEN)

    @pytest.mark.unit
    @pytest.mark.parametrize('padded', [' WIT', 'WIT ', 'WIT\n'])
    def test_padded_token_rejected(self, padded):
        with pytest.raises(InvalidGs1PayloadError):
            encode(ID, ai=AI, token=padded)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad', ['9 6', 'W IT', '9\x1d6', 'WIT\x00', '96é'])
    def test_unencodable_ai_or_token_rejected(self, bad):
        """Interior whitespace, a control character (FNC1 among them, which
        would split the data field) or a non-ASCII character is as unencodable
        in the prefix as it is in the id. Padding was already rejected; these
        sit inside the value, where .strip() cannot see them, and would still
        round-trip through this module's own decode under the same bad config."""
        with pytest.raises(InvalidGs1PayloadError):
            encode(ID, ai=bad, token=TOKEN)
        with pytest.raises(InvalidGs1PayloadError):
            encode(ID, ai=AI, token=bad)

    @pytest.mark.unit
    def test_error_is_a_valueerror_subclass(self):
        assert issubclass(InvalidGs1PayloadError, ValueError)


class TestDecode:

    @pytest.mark.unit
    def test_decodes_gs_prefixed_payload(self):
        raw = '\x1d96WITABC1234567'
        assert decode(raw, ai=AI, token=TOKEN) == InternalPayload(
            internal_id=ID, ai=AI, token=TOKEN, raw=raw)

    @pytest.mark.unit
    def test_decodes_substitute_prefixed_payload(self):
        raw = '~96WITABC1234567'
        assert decode(raw, ai=AI, token=TOKEN, fnc1_substitute='~') == InternalPayload(
            internal_id=ID, ai=AI, token=TOKEN, raw=raw)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_substitute', ['', '~~', '96', 5, b'~', ['~']])
    def test_malformed_fnc1_substitute_is_a_config_fault_and_raises(self, bad_substitute):
        """The third grammar knob is validated like ai/token. A non-string would
        otherwise raise a bare TypeError out of a function contracted never to
        raise on scan data, and a multi-character one would eat the AI."""
        with pytest.raises(InvalidGs1PayloadError):
            decode('96WITABC1234567', ai=AI, token=TOKEN,
                   fnc1_substitute=bad_substitute)

    @pytest.mark.unit
    def test_explicit_gs_substitute_is_accepted(self):
        """GS is whitespace to str.strip(), but passing it explicitly is legal."""
        assert decode('\x1d96WITABC1234567', ai=AI, token=TOKEN,
                      fnc1_substitute=FNC1).internal_id == ID

    @pytest.mark.unit
    def test_decodes_bare_payload_with_fnc1_stripped(self):
        """The deployed Tera HW0009 strips FNC1 entirely (Q1 hardware spike)."""
        raw = '96WITABC1234567'
        assert decode(raw, ai=AI, token=TOKEN) == InternalPayload(
            internal_id=ID, ai=AI, token=TOKEN, raw=raw)

    @pytest.mark.unit
    def test_decodes_bare_payload_with_trailing_crlf(self):
        """A keyboard-wedge scanner's trailing CR/LF is tolerated; raw is kept."""
        raw = '96WITABC1234567\r\n'
        payload = decode(raw, ai=AI, token=TOKEN)
        assert payload == InternalPayload(internal_id=ID, ai=AI, token=TOKEN, raw=raw)
        assert payload.raw == raw              # verbatim, un-stripped

    @pytest.mark.unit
    def test_round_trips_encode_output(self):
        assert decode(encode(ID, ai=AI, token=TOKEN),
                      ai=AI, token=TOKEN).internal_id == ID

    @pytest.mark.unit
    def test_substitute_is_not_recognized_unless_supplied(self):
        """Without fnc1_substitute, a '~' prefix is just a foreign payload."""
        assert decode('~96WITABC1234567', ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '9612345',            # AI 96 but no token — a coincidental foreign code
        '0109506000134352',   # a GTIN-14 element string (AI 01)
        '96WIT',              # token present, empty id
        '',                   # empty string
        '   ',                # whitespace only
        None,                 # non-str
        '96witABC1234567',    # wrong case
        '96WitABC1234567',    # wrong case
        '97WITABC1234567',    # wrong AI
        'WIT96ABC1234567',    # token/AI transposed
        'ABC1234567',         # bare id with no grammar at all
        ']d196WITABC1234567',  # AIM prefix is the classifier's job (FR37)
    ])
    def test_foreign_or_junk_returns_none(self, raw):
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [None, 123, b'96WITABC1234567', 12.0, ['x'], object()])
    def test_non_str_raw_returns_none_never_raises(self, raw):
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '\x1d96WIT', '\x1d', '96', 'WIT', '96W', '\x1d0109506000134352',
    ])
    def test_truncated_payloads_return_none_never_raise(self, raw):
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    def test_ai_and_token_are_keyword_only_with_no_defaults(self):
        with pytest.raises(TypeError):
            decode('96WITABC1234567')
        with pytest.raises(TypeError):
            decode('96WITABC1234567', AI, TOKEN)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad', ['', '   ', None, 96])
    def test_blank_grammar_is_a_config_fault_and_raises(self, bad):
        """decode never raises on `raw`, but a blank ai/token is a config bug."""
        with pytest.raises(InvalidGs1PayloadError):
            decode('96WITABC1234567', ai=bad, token=TOKEN)
        with pytest.raises(InvalidGs1PayloadError):
            decode('96WITABC1234567', ai=AI, token=bad)

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '96WITABC1234567\r\n2026-07-24 ERROR forged',  # log-forging attempt
        '96WITABC\x1d234567',   # interior FNC1/GS
        '96WITABC\t234567',     # interior tab
        '96WITABC\x00234567',   # NUL
        '96WITABC123456é',      # non-ASCII
    ])
    def test_interior_control_or_non_ascii_id_returns_none(self, raw):
        """Only what encode() could have emitted counts as internal: an id
        carrying an interior control character (e.g. a CR/LF that would forge a
        second audit-log line) or a non-ASCII character is not ours."""
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '\x1d96WITABC1234567', '96WITABC1234567', '96WITWIT1234567',
        '  96WIT0000000001\r\n',
    ])
    def test_whatever_decode_accepts_encode_can_re_emit(self, raw):
        """The pair is closed: no decoded payload is un-encodable."""
        payload = decode(raw, ai=AI, token=TOKEN)
        assert payload is not None
        assert decode(encode(payload.internal_id, ai=AI, token=TOKEN),
                      ai=AI, token=TOKEN).internal_id == payload.internal_id

    @pytest.mark.unit
    @pytest.mark.parametrize('padded', [' 96', '96 ', ' WIT', 'WIT '])
    def test_padded_grammar_is_a_config_fault_and_raises(self, padded):
        with pytest.raises(InvalidGs1PayloadError):
            decode('96WITABC1234567', ai=padded, token=TOKEN)
        with pytest.raises(InvalidGs1PayloadError):
            decode('96WITABC1234567', ai=AI, token=padded)

    @pytest.mark.unit
    def test_id_containing_the_token_again_is_not_truncated(self):
        """Only the leading AI+token is consumed; the rest is the id verbatim."""
        payload = decode('96WITWIT1234567', ai=AI, token=TOKEN)
        assert payload.internal_id == 'WIT1234567'


class TestFnc1SubstituteCollidesWithTheMarker:
    """
    A substitute equal to the marker's first character breaks recognition.

    `decode` removes one leading substitute BEFORE testing the marker, so with
    ai='96' and fnc1_substitute='9' the genuine label '96WIT…' is consumed down
    to '6WIT…' and fails the match. That is every label the shop actually
    prints and scans: `decode` exists to absorb all three FNC1 transmissions,
    and this collision costs it two of them — stripped (the deployed Tera
    HW0009) and GS. It is refused the same way the token-room rule refuses the
    same class of silent failure: loudly, as a grammar fault, before `raw` is
    looked at.

    It IS a behavioral narrowing, not only a repair, and the last test here
    pins the case that is given up: a scan that really does carry the
    substitute used to decode and no longer does.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '96WITABC1234567',        # bare, as the deployed Tera HW0009 emits it
        '\x1d96WITABC1234567',    # ...and GS-framed, which strip() unwraps first
    ])
    def test_a_colliding_substitute_is_refused_not_silently_none(self, raw):
        with pytest.raises(InvalidGs1PayloadError):
            decode(raw, ai=AI, token=TOKEN, fnc1_substitute=AI[0])

    @pytest.mark.unit
    def test_the_rule_fires_before_raw_is_inspected(self):
        """It is a grammar fault, so it does not depend on what arrived: even
        the non-str input that `decode` otherwise answers with None (NFR8)
        raises, exactly as a blank token already does."""
        with pytest.raises(InvalidGs1PayloadError):
            decode(None, ai=AI, token=TOKEN, fnc1_substitute=AI[0])
        with pytest.raises(InvalidGs1PayloadError):
            decode(object(), ai=AI, token=TOKEN, fnc1_substitute=AI[0])

    @pytest.mark.unit
    def test_only_the_marker_s_first_character_is_barred(self):
        """The rule is deliberately narrow: it bars the one character `decode`
        would strip off the front of a genuine label, not every character the
        marker happens to contain. A substitute matching the AI's second
        character, or the token's first, strips nothing and still decodes —
        barring those would refuse working grammars for no reason."""
        assert decode('96WITABC1234567', ai=AI, token=TOKEN,
                      fnc1_substitute=AI[1]).internal_id == ID
        assert decode('96WITABC1234567', ai=AI, token=TOKEN,
                      fnc1_substitute=TOKEN[0]).internal_id == ID

    @pytest.mark.unit
    def test_a_non_colliding_substitute_still_strips_and_decodes(self):
        """The repair must not cost the feature: an ordinary substitute keeps
        working exactly as before."""
        assert decode('~96WITABC1234567', ai=AI, token=TOKEN,
                      fnc1_substitute='~').internal_id == ID

    @pytest.mark.unit
    def test_gs_itself_is_still_accepted_as_a_substitute(self):
        """GS can never collide with a marker (the marker is printable ASCII),
        so the explicit-GS case the module already supported is untouched."""
        assert decode('\x1d96WITABC1234567', ai=AI, token=TOKEN,
                      fnc1_substitute=FNC1).internal_id == ID

    @pytest.mark.unit
    def test_the_substitute_carrying_form_is_given_up_deliberately(self):
        """The cost of the rule, stated as a test rather than left for someone
        to rediscover. `'996WIT…'` — a scanner that always emits its substitute
        — strips cleanly to the marker and decoded correctly before this rule
        existed. It is refused now because a grammar readable by only one
        scanner behaviour, out of the three this function is contracted to
        absorb, is not one to accept silently."""
        with pytest.raises(InvalidGs1PayloadError):
            decode('996WITABC1234567', ai=AI, token=TOKEN,
                   fnc1_substitute=AI[0])


class TestForeignPayloadRejection:
    """
    The exhaustive foreign-payload matrix (Story 2.5, FR12a, NFR8).

    Epic 4 scan routing delegates internal-symbol recognition to `decode`, so
    "this barcode is not one of ours" has to be pinned family by family rather
    than by a handful of ad-hoc strings. Every case below is a payload this
    workshop can realistically scan; every one must return None, and none may
    raise. `TestDecode`'s own foreign cases stay — this class widens them, it
    does not replace them.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '9612345',            # AI 96, digits, no token — a legitimate foreign use of 96
        '96ACME1234567',      # AI 96 with someone else's token
        '\x1d96FOO123',       # ...even FNC1-framed, exactly like ours
        '9612345678903',      # a UPC-A whose digits merely start '96'
    ])
    def test_foreign_ai_96_without_the_token_is_not_ours(self, raw):
        """The token is what makes a symbol ours; AI 96 alone is shared (FR12a)."""
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '012345678905',       # UPC-A (12)
        '0012345678905',      # EAN-13
        '00012348',           # GTIN-8
        '00012345678905',     # GTIN-14
    ])
    def test_retail_digit_strings_are_not_internal(self, raw):
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '0109506000134352',                    # AI 01, GTIN-14 element string
        '\x1d0109506000134352\x1d10LOT42',     # AI 01 + AI 10 batch/lot
        '\x1d00123456789012345675',            # AI 00, SSCC
        '\x1d21SN0001',                        # AI 21, serial number
        '\x1d17260101',                        # AI 17, expiry date
    ])
    def test_other_gs1_element_strings_are_not_internal(self, raw):
        """A well-formed GS1 symbol under any other AI is still foreign."""
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '[)>\x1e06\x1dP12345\x1d1PABC\x1dQ10\x1d\x1e\x04',  # ECIA ISO-15434 label
        'B08N5WRWNW',              # Amazon ASIN
        'X001ABCDEF',              # Amazon FNSKU
        'https://example.com/p/1',  # a QR code carrying a URL
        'JA000123',                # this system's own legacy metal-stock JA ID
        'M1-A',                    # a storage-location label
    ])
    def test_distributor_and_vendor_payloads_are_not_internal(self, raw):
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        ']d296WITABC1234567',      # DataMatrix, GS1 FNC1 in first position
        ']d2 96WITABC1234567',     # ...and with the separating space some wedges add
        ']C10109506000134352',     # GS1-128
        ']Q396WITABC1234567',      # QR code
        ']d196WITABC1234567',      # plain DataMatrix
    ])
    def test_aim_prefixed_payloads_are_not_stripped_here(self, raw):
        """Prefix stripping belongs to the scan classifier (Story 4.2, FR37) —
        this module sees the prefix as part of the payload and says no."""
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '096WITABC1234567',        # a leading digit
        '9WITABC1234567',          # AI truncated
        'WITABC1234567',           # AI missing entirely
        '96 WITABC1234567',        # space between AI and token
        '96-WITABC1234567',        # punctuation between AI and token
        '96witABC1234567',         # token lower-cased
        '96WitABC1234567',         # token mixed-case
        '96WIT',                   # grammar complete, data field empty
        '96WIT   ',                # ...and the same once trailing padding is stripped
    ])
    def test_near_miss_prefixes_are_not_internal(self, raw):
        """The match is exact and case-sensitive: near enough is not ours."""
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '９６WITABC1234567',   # full-width digits '96'
        '96WIT​ABC1234567',      # zero-width space inside the data field
        '96WITABC123456é',       # a non-ASCII character in the id
        '٩٦WITABC1234567',  # Arabic-Indic digits '96'
    ])
    def test_unicode_homoglyph_payloads_are_not_internal(self, raw):
        """Homoglyphs never resolve to a product: the AI and token are matched
        as literal ASCII, and the data field is printable ASCII or nothing."""
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '\x1d96WITABC1234567\x1d10LOT42',   # ours, then an AI 10 batch/lot
        '96WITABC1234567\x1d21SN0001',      # ...unframed, then an AI 21 serial
        '\x1d10LOT42\x1d96WITABC1234567',   # ...and with ours second
    ])
    def test_our_marker_inside_a_composite_symbol_is_not_internal(self, raw):
        """The grammar is exactly one element string with no separator (FR12b),
        so a composite symbol is foreign even where our own AI+token appears
        inside it. Worth pinning explicitly: the first two open with our marker
        and clear the length bound, and are refused only by the interior FNC1 —
        this is the ours/foreign boundary a real multi-AI label produces, and
        the answer Epic 4 routing will see while separator handling stays
        deferred."""
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    def test_token_superstring_decodes_by_design(self):
        """'96WITTY42' matches the grammar and yields 'TY42' — correct, not a
        hole: the grammar is satisfied, and whether an id exists is the
        product lookup's question, not this module's (AD-16)."""
        payload = decode('96WITTY42', ai=AI, token=TOKEN)
        assert payload is not None
        assert payload.internal_id == 'TY42'


class TestDecodeTradeItemNumber:
    """
    The second element string this module recognizes (DW-70, FR36 rule 3).

    AI 01 is how a manufacturer encodes a GTIN on a box, and the scan
    classifier needs the 14 digits out of it so the scan routes as the GTIN it
    carries. Recognition lives here rather than in `scan_router.py` because
    element-string grammar has exactly one owner (AD-16).

    Two things this class exists to pin above all others. First, the function
    does not *judge*: it returns the digits verbatim and unvalidated, because
    `app/utils/gtin.py` alone decides whether digits are a GTIN. Second, only a
    payload *opening* with AI 01 is read — AI 01 is predefined-length
    (`n2+n14`) so nothing delimits its field, and the tail rule (a digit, a
    FNC1, or nothing) is what separates a real element-string chain from free
    text that happens to start with sixteen useful-looking characters.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        EL,                            # bare — what the deployed Tera HW0009 emits (FR37a)
        FNC1 + EL,                     # FNC1 transmitted as GS
        ' ' + EL + ' ',                # a wedge that pads
        EL + '\r\n',                   # ...and the trailing CR/LF a keyboard wedge appends
        EL + '17260101',               # an abutted AI 17 expiry date — no separator exists
        EL + '10LOT42',                # ...or an abutted AI 10 batch/lot
        EL + FNC1 + '10LOT42',         # a GS-separated variable-length field after it
        EL + FNC1,                     # a trailing separator — absorbed by strip(), never seen as a tail
        FNC1 + EL + FNC1 + '10LOT42',  # the realistic full GS1-128 transmission
    ])
    def test_every_transmission_shape_yields_the_trade_item_number(self, raw):
        assert decode_trade_item_number(raw) == TRADE_ITEM

    @pytest.mark.unit
    def test_the_digits_are_returned_verbatim(self):
        """Not re-padded, not re-derived: exactly the 14 characters that
        followed the AI, leading zero and all."""
        assert decode_trade_item_number(EL) == EL[2:]
        assert len(decode_trade_item_number(EL)) == 14

    @pytest.mark.unit
    @pytest.mark.parametrize('raw, expected', [
        ('0109506000134353', '09506000134353'),   # a broken mod-10 check digit
        ('0100000000000000', '00000000000000'),   # the wedge no-read (DW-69)
        ('0100000000012348', '00000000012348'),   # a GTIN-8's value, zero-padded into the field
        ('0100012345678905', '00012345678905'),   # ...and a UPC-A's
    ])
    def test_the_number_is_returned_unjudged(self, raw, expected):
        """The function answers "an AI-01 element string was here, and this is
        its field" and nothing else. Validity is `app/utils/gtin.py`'s alone
        (AD-16), so a broken check digit and the all-zero no-read both come
        back cheerfully — the classifier then refuses them in the same arm that
        refuses the bare numbers."""
        assert decode_trade_item_number(raw) == expected

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        EL + 'ABC',                    # a letter cannot open an AI
        EL + ' RES 10K',               # ...nor a space: this is free text with a lucky prefix
        EL + '\x1e10LOT42',            # RS is not the separator GS1 uses between fields
        EL + '-17260101',              # punctuation
        EL + ']d1',                    # an AIM prefix in the wrong place
        EL + '1 RES 10K 0805',         # one digit then text — the case tail[0] alone admitted
        EL + '5X',                     # ...and its shortest form
        EL + '1',                      # a single trailing digit: no AI is one character
        EL + FNC1 + 'RES 10K 0805',    # a GS is a separator, not a licence for anything
        EL + FNC1 + '1 RES 10K',       # ...so the two-digit test applies past it too
        EL + FNC1 + ']d1[)>',          # ...including to a second symbology's worth of junk
        EL + FNC1 + FNC1 + '10LOT42',  # a doubled GS encloses an empty element string
        EL + FNC1 + ' 10LOT42',        # ...and a separator does not license padding either
    ])
    def test_a_tail_that_is_not_another_element_string_is_not_a_match(self, raw):
        """AI 01 is predefined-length, so what follows the 14 digits is either
        another AI, a FNC1, or the end of the scan — and an AI is two to four
        digits, so the tail is judged on its first TWO characters. Judging only
        the first would make `'0109506000134352' + '1 RES 10K 0805'` a GTIN
        scan, which is the free text this rule exists to keep out.

        A FNC1 does not exempt what follows it. It separates one element string
        from the next, so the next one is still an element string and is held
        to the same test — exempting it would have made a single transmitted GS
        enough to admit any free text at all behind a lucky prefix.

        Exactly one FNC1 is consumed, so a doubled separator leaves a FNC1 as
        the opener and is refused. That is deliberate — a doubled GS encloses
        an empty element string, which the grammar does not permit — and it is
        asymmetric with the leading side, where `str.strip()` absorbs any
        number of separators before the AI. The asymmetry is pinned here and
        in `test_the_leading_side_absorbs_separators_the_tail_does_not` rather
        than left to be rediscovered."""
        assert decode_trade_item_number(raw) is None

    @pytest.mark.unit
    def test_the_leading_side_absorbs_separators_the_tail_does_not(self):
        """The two sides of the element string do not tolerate the same thing,
        and the difference is `str.strip()` rather than a decision: it eats any
        run of leading separators (Python counts 0x1C-0x1F as whitespace),
        while the tail slice consumes exactly one. Stated as a test because
        neither side's behavior is obvious from the other's."""
        assert decode_trade_item_number(FNC1 * 3 + EL) == TRADE_ITEM
        assert decode_trade_item_number(EL + FNC1 * 2 + '10LOT42') is None
        # And a doubled separator with nothing after it is read, because
        # `strip()` removes the whole trailing run before any tail is seen.
        assert decode_trade_item_number(EL + FNC1 * 2) == TRADE_ITEM

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        EL + '789',                    # a 19-digit run: indistinguishable from AI 78 + data
        EL + '17260101' + '2',         # ...and a legal chain with one digit too many
        EL + '17ABC',                  # two digits then anything: the test cannot look past them
        EL + FNC1 + '17 RES 10K',      # ...and that is just as true past a separator
    ])
    def test_a_tail_opening_with_two_digits_is_read_and_that_is_accepted(self, raw):
        """The residual the two-digit test cannot close, pinned so it is a
        stated property rather than a surprise, and pinned at its true width:
        the test reads exactly two characters, so *anything* may follow them.

        A pure digit run is character-for-character identical to a legal
        element-string chain, and telling them apart needs an AI table this
        module deliberately has no part of. Note what the cost of that is: the
        digits handed back are a valid GTIN by construction, so if the catalog
        holds it the scan resolves to that product rather than falling through
        to a free-text search. A wrong answer, not a wasted lookup — accepted
        because the alternative is refusing the legal `01`+`17`+`10` chains
        this rule exists to read."""
        assert decode_trade_item_number(raw) == TRADE_ITEM

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '010950600013435',             # 13 digits — one short
        '01950600013435',              # 12 digits
        '01',                          # the AI alone
        '019',                         # the AI and one digit
        '01' + '0' * 14 + 'X',         # 14 digits then a non-digit, non-GS tail
        '01' + '0' * 13 + 'X' + '0',   # a non-digit *inside* the fixed-length field
    ])
    def test_the_field_must_be_exactly_fourteen_digits(self, raw):
        assert decode_trade_item_number(raw) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '01' + '٩٥٠٦٠٠٠١٣٤٣٥٢',        # Arabic-Indic digits: str.isdigit() accepts them
        '01' + '０１２３４５６７８９０１２３',   # full-width digits, likewise
        '01' + '١' * 14,               # a whole field of them
    ])
    def test_non_ascii_digits_are_not_a_trade_item_number(self, raw):
        """`str.isdigit()` alone would build a key that cannot be compared or
        stored as plain digits — the same reason `gtin.normalize_gtin` demands
        ASCII."""
        assert decode_trade_item_number(raw) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        FNC1 + '00123456789012345675',  # AI 00, SSCC
        FNC1 + '21SN0001',              # AI 21, serial number
        FNC1 + '17260101',              # AI 17, expiry date
        FNC1 + '10LOT42',               # AI 10, batch/lot
        '0209506000134352',             # AI 02, a trade item number of a *contained* item
        AI + TOKEN + ID,                # this module's own internal element string
    ])
    def test_any_other_ai_is_not_read(self, raw):
        """There is no AI table here and there is not meant to be one: exactly
        one foreign AI is recognized, and widening that is a decision."""
        assert decode_trade_item_number(raw) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        FNC1 + '10LOT42' + FNC1 + EL,   # ours second, after a variable-length field
        '17260101' + EL,                # ...abutted after a fixed-length one
        FNC1 + '21SN0001' + FNC1 + EL,  # ...after a serial number
    ])
    def test_ai_01_after_another_element_string_is_not_read(self, raw):
        """Only a payload *opening* with AI 01 is read. Finding one further in
        would mean knowing where a variable-length field ends, which is the
        general GS1 parser this module deliberately is not."""
        assert decode_trade_item_number(raw) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        ']d1' + EL,                    # DataMatrix
        ']d2' + EL,                    # DataMatrix, FNC1 in first position
        ']C1' + EL,                    # GS1-128
    ])
    def test_an_aim_prefix_is_not_stripped_here(self, raw):
        """Exactly as `decode` refuses one: per FR37 the prefix narrows the
        symbology class and stripping it is the classifier's job, which has
        already run by the time this is called."""
        assert decode_trade_item_number(raw) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        None,                          # absent
        123,                           # an int
        b'0109506000134352',           # bytes — the transport decodes, we do not
        12.0,                          # a float
        ['0109506000134352'],          # a list
        object(),                      # anything else
    ])
    def test_a_non_str_returns_none_and_never_raises(self, raw):
        """NFR8 goes further here than in `decode`: there is no grammar to be
        misconfigured, so this function has no reachable exception at all."""
        assert decode_trade_item_number(raw) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '',                            # empty
        '   ',                         # whitespace only
        FNC1 * 50,                     # a storm of separators
        '\x00' * 100,                  # a NUL run
        ''.join(chr(i) for i in range(32)),  # every C0 control character
        '\x01\x1f' * 2048,             # 4096 characters of control characters
        '0' * 4096,                    # ...and of digits, which open like an AI
        '\U0001f600' * 100,            # astral-plane characters
        '\ud83d',                      # a lone surrogate, as Python allows in a str
    ])
    def test_hostile_scan_data_returns_none_and_never_raises(self, raw):
        assert decode_trade_item_number(raw) is None

    @pytest.mark.unit
    def test_it_takes_no_grammar_arguments(self):
        """AI 01 is assigned by GS1, not by this deployment, so unlike `decode`
        this function reads no configuration and has no `ai`/`token`/
        `fnc1_substitute` knob to be handed a bad value for.

        Asserted on the signature rather than only on the `TypeError`: the
        raise proves nothing about this design, since any callable lacking
        those keywords produces it. The parameter list is the claim.
        """
        assert (list(inspect.signature(decode_trade_item_number).parameters)
                == ['raw'])
        with pytest.raises(TypeError):
            decode_trade_item_number(EL, ai=AI, token=TOKEN)

    @pytest.mark.unit
    def test_the_two_recognizers_disagree_about_the_same_string_on_purpose(self):
        """The boundary DW-70 had to preserve. `decode` says "not ours" for an
        AI-01 element string — Story 2.4/2.5 froze that, and
        `TestForeignPayloadRejection` pins it — while
        `decode_trade_item_number` says "a trade item number, here it is".
        Both answers are correct, and a sibling function is what keeps them
        machine-checked instead of overloading one return type."""
        assert decode(EL, ai=AI, token=TOKEN) is None
        assert decode_trade_item_number(EL) == TRADE_ITEM
        # ...and the mirror image, so neither recognizer has quietly widened.
        internal = AI + TOKEN + ID
        assert decode(internal, ai=AI, token=TOKEN).internal_id == ID
        assert decode_trade_item_number(internal) is None


class TestDataFieldLengthBound:
    """
    The single data field is bounded (Story 2.5).

    The company-internal series (AIs 90-99) permits `X..90` since GSCN
    16-000528; 30 is this module's deliberately tighter cap, applied on both
    sides so the pair stays closed. It is a bound on the element string's field,
    never a rule about the id's shape, which `internal_id.py` owns (AD-16).
    """

    @pytest.mark.unit
    def test_bound_is_thirty(self):
        assert MAX_DATA_FIELD_LENGTH == 30

    @pytest.mark.unit
    def test_encode_accepts_a_data_field_exactly_at_the_bound(self):
        """token 'WIT' (3) + 27 id characters = 30."""
        assert encode('A' * 27, ai=AI, token=TOKEN) == '\x1d96WIT' + 'A' * 27

    @pytest.mark.unit
    def test_encode_rejects_a_data_field_one_over_the_bound(self):
        with pytest.raises(InvalidGs1PayloadError):
            encode('A' * 28, ai=AI, token=TOKEN)

    @pytest.mark.unit
    def test_at_bound_payload_round_trips(self):
        payload = decode(encode('A' * 27, ai=AI, token=TOKEN), ai=AI, token=TOKEN)
        assert payload is not None
        assert payload.internal_id == 'A' * 27

    @pytest.mark.unit
    def test_decode_accepts_a_data_field_exactly_at_the_bound(self):
        payload = decode('96WIT' + 'A' * 27, ai=AI, token=TOKEN)
        assert payload is not None
        assert payload.internal_id == 'A' * 27

    @pytest.mark.unit
    def test_the_bound_is_measured_after_the_fnc1_substitute_is_stripped(self):
        """The separator is not part of the data field, so an at-bound payload
        stays valid however FNC1 arrived — the module's headline hazard."""
        at_bound = '~96WIT' + 'A' * 27
        payload = decode(at_bound, ai=AI, token=TOKEN, fnc1_substitute='~')
        assert payload is not None
        assert payload.internal_id == 'A' * 27
        assert decode('~96WIT' + 'A' * 28, ai=AI, token=TOKEN,
                      fnc1_substitute='~') is None

    @pytest.mark.unit
    @pytest.mark.parametrize('overlong', [
        'A' * 28,       # one character over
        'A' * 100,      # a garbled scan
        'A' * 100000,   # a 100 KB payload that happens to open '96WIT'
    ])
    def test_decode_rejects_an_oversized_data_field_without_raising(self, overlong):
        """NFR8: an oversized scan is foreign input, so it is a None. The check
        precedes the character scan, so the 100 KB case is dismissed on its
        length rather than walked character by character."""
        assert decode('96WIT' + overlong, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    def test_the_bound_counts_the_token_so_a_longer_token_shortens_the_id(self):
        """The data field is one field, token included — not two."""
        assert encode('A' * 20, ai=AI, token='TOKENTOKEN').endswith('A' * 20)
        with pytest.raises(InvalidGs1PayloadError):
            encode('A' * 21, ai=AI, token='TOKENTOKEN')

    @pytest.mark.unit
    def test_a_token_leaving_no_room_for_an_id_is_a_loud_config_error(self):
        """A token at or beyond the bound would make encode impossible and every
        decode of a real label a silent None — a total two-way outage. The
        module's standing choice is to fail loudly on a malformed grammar."""
        for func in (lambda t: encode('X', ai=AI, token=t),
                     lambda t: decode('96' + t + 'X', ai=AI, token=t)):
            with pytest.raises(InvalidGs1PayloadError):
                func('T' * MAX_DATA_FIELD_LENGTH)

    @pytest.mark.unit
    def test_the_deployed_id_length_fits_inside_the_bound(self):
        """A cross-module fit check, not a shape rule: gs1.py deliberately knows
        nothing about the id's length or alphabet (AD-16), but the bound it now
        enforces must never be able to strand the id length actually issued.
        Raising INTERNAL_ID_LENGTH past it would make every encode fail at the
        label printer; this fails in the suite instead."""
        from app.utils.internal_id import INTERNAL_ID_LENGTH

        assert len(TOKEN) + INTERNAL_ID_LENGTH <= MAX_DATA_FIELD_LENGTH

    @pytest.mark.unit
    def test_no_id_shape_rule_leaked_in_with_the_bound(self):
        """The bound is the element string's, not the id's: a 27-character id
        outside the internal-id alphabet still encodes and decodes here
        (AD-16)."""
        raw = encode('lower-case_and.punctuation!', ai=AI, token=TOKEN)
        payload = decode(raw, ai=AI, token=TOKEN)
        assert payload is not None
        assert payload.internal_id == 'lower-case_and.punctuation!'


class TestForbiddenAiSeries:
    """FR12d: no 43xx element string can be produced or recognized."""

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_ai', [
        '4311',   # 'return-to contact name' — the AI the addendum rejected
        '4300',   # the series' first member ('ship-to company name')
        '43',     # the bare series prefix
        '4399',   # past the last assigned member, still in the barred range
    ])
    def test_encode_refuses_the_series(self, bad_ai):
        """The one encoder reads its AI from config, so refusing the series here
        is what makes "no 43xx element string is ever encoded" an invariant
        rather than a comment: a reconfigured GS1_INTERNAL_AI fails loudly at
        the first encode."""
        with pytest.raises(InvalidGs1PayloadError):
            encode('X', ai=bad_ai, token=TOKEN)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_ai', ['4311', '4300', '43', '4399'])
    def test_decode_refuses_the_series(self, bad_ai):
        """Refused on the decode side too, purely to keep the pair closed. This
        is a config fault — the grammar itself is illegal — so unlike every
        other rejection in decode it raises rather than returning None."""
        with pytest.raises(InvalidGs1PayloadError):
            decode(bad_ai + 'WITX', ai=bad_ai, token=TOKEN)

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '4311J. ANTMAN',       # a real 43xx element string from someone else
        '\x1d4300ACME CORP',   # ...FNC1-framed
        '43',                  # the bare prefix
    ])
    def test_a_scanned_43_payload_is_merely_foreign_not_an_error(self, raw):
        """The rule is about the configured *grammar*, never about `raw`. Under
        the deployed 96/WIT grammar a scan that happens to open '43' fails the
        ordinary marker match like any other foreign payload — the forbidden
        prefix is never consulted — so it is a None, not a raise (NFR8). This is
        the one input that touches both of the story's new rules at once."""
        assert decode(raw, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    def test_a_split_grammar_cannot_assemble_the_series(self):
        """The guard matches the marker, not the AI alone: ai='4' with
        token='311' builds the identical '4311…' element string, so checking
        only `ai` would have left the FR12d invariant one config away from
        being false."""
        with pytest.raises(InvalidGs1PayloadError):
            encode('X', ai='4', token='311')
        with pytest.raises(InvalidGs1PayloadError):
            decode('4311X', ai='4', token='311')

    @pytest.mark.unit
    @pytest.mark.parametrize('good_ai', [
        '96',    # the deployed AI
        '97',    # its neighbour in the company-internal series
        '01',    # GTIN
        '8200',  # a four-digit AI
        '4',     # a leading '4' alone is not the series
        '3',     # ...nor a leading '3'
        '34',    # ...nor the digits reversed
        '243',   # ...nor '43' anywhere but the front
    ])
    def test_only_a_leading_43_is_barred(self, good_ai):
        """FR12c is preserved: the rest of the AI space still round-trips. The
        short values are boundary probes for the prefix match, not a claim that
        every one of them is a registered GS1 AI — this module has never
        validated AI *formats*, only its own grammar (AD-16)."""
        out = encode('X', ai=good_ai, token=TOKEN)
        assert out == FNC1 + good_ai + TOKEN + 'X'
        payload = decode(out, ai=good_ai, token=TOKEN)
        assert payload is not None
        assert payload.internal_id == 'X'


class TestOwnershipTextIsNotEncodable:
    """FR12d: ownership/return information is label text, never a symbol."""

    @pytest.mark.unit
    @pytest.mark.parametrize('owner_text', [
        'If found, return to J. Antman — 555-0100',   # the realistic case
        'Return to: Workshop',                        # spaces alone are enough
        'J. Antman 555-0100',                         # ...as here
    ])
    def test_encode_refuses_human_readable_ownership_text(self, owner_text):
        """A return-to string carries spaces, so the printable-ASCII rule that
        guards the data field refuses it. A backstop for the ordinary case —
        see the test below for what it does not cover."""
        with pytest.raises(InvalidGs1PayloadError):
            encode(owner_text, ai=AI, token=TOKEN)

    @pytest.mark.unit
    def test_a_compact_ownership_string_is_encodable_so_the_rule_is_not_the_guarantee(self):
        """Pinned deliberately, against the temptation to read the case above as
        a proof: a short space-free return-to string is perfectly encodable
        (a longer one is refused for its length, which is not the same rule and
        not a guarantee either). What actually keeps the label's two regions
        apart is that no code path passes ownership_label_text() into this
        module (FR12d)."""
        assert encode('ReturnTo:J.Antman', ai=AI, token=TOKEN) == \
            FNC1 + AI + TOKEN + 'ReturnTo:J.Antman'


class TestConfigDrivenGrammar:
    """FR12c/AD-16: one config pair moves encoder and decoder together."""

    @pytest.mark.unit
    def test_alternate_grammar_round_trips(self):
        out = encode(ID, ai='97', token='ZZZ')
        assert out == '\x1d97ZZZABC1234567'
        assert decode(out, ai='97', token='ZZZ') == InternalPayload(
            internal_id=ID, ai='97', token='ZZZ', raw=out)

    @pytest.mark.unit
    def test_alternate_grammar_payload_does_not_decode_under_the_default(self):
        out = encode(ID, ai='97', token='ZZZ')
        assert decode(out, ai=AI, token=TOKEN) is None

    @pytest.mark.unit
    def test_default_grammar_payload_does_not_decode_under_the_alternate(self):
        out = encode(ID, ai=AI, token=TOKEN)
        assert decode(out, ai='97', token='ZZZ') is None

    @pytest.mark.unit
    def test_payload_reports_the_grammar_it_matched(self):
        payload = decode('97ZZZABC1234567', ai='97', token='ZZZ')
        assert (payload.ai, payload.token) == ('97', 'ZZZ')


class TestErrorAttribution:
    """
    Every failure says whose it is, as data rather than as English.

    The one exception class covers two entirely different faults: a malformed
    configured grammar (an operator's, in a named config key) and a malformed
    `internal_id` (a caller's, in user data). The service layer has to raise a
    different domain error for each, and parsing the message to decide would be
    a second, silently drifting copy of the rules. So `source` says which, and
    `part` names the knob when one is named.
    """

    @pytest.mark.unit
    def test_the_two_sources_are_named_constants(self):
        """Callers branch on these, so they are part of the module's contract
        and not string literals to be re-spelled at each call site."""
        assert InvalidGs1PayloadError.GRAMMAR == 'grammar'
        assert InvalidGs1PayloadError.PAYLOAD == 'payload'

    @pytest.mark.unit
    def test_source_is_required_and_keyword_only(self):
        """A raise site that forgets to classify itself must fail loudly here
        rather than land in whichever branch the caller happened to write
        first."""
        with pytest.raises(TypeError):
            InvalidGs1PayloadError('boom')
        with pytest.raises(TypeError):
            InvalidGs1PayloadError('boom', InvalidGs1PayloadError.GRAMMAR)

    @pytest.mark.unit
    def test_an_unrecognized_source_is_refused_at_construction(self):
        """Requiring the argument is only half the guarantee. The service's
        branch is asymmetric on purpose — only an explicit PAYLOAD blames the
        id — so a misspelled source would not fail anywhere, it would quietly
        report a bad id as a configuration fault, which is this attribute's own
        defect running backwards. It is refused where it is written instead."""
        with pytest.raises(ValueError):
            InvalidGs1PayloadError('boom', source='typo')
        with pytest.raises(ValueError):
            InvalidGs1PayloadError('boom', source=None)

    @pytest.mark.unit
    def test_the_message_is_still_the_str_of_the_error(self):
        """The service carries the message through verbatim; the new attributes
        sit beside it rather than in front of it."""
        error = InvalidGs1PayloadError('boom',
                                       source=InvalidGs1PayloadError.GRAMMAR)
        assert str(error) == 'boom'
        assert error.part is None

    @pytest.mark.unit
    def test_the_classification_survives_copying_and_pickling(self):
        """Exceptions get copied and pickled by logging, task queues and test
        helpers without anyone deciding to. A keyword-only `source` defeats
        BaseException's default `__reduce__`, so the module supplies its own —
        without it, `copy(err)` raises TypeError and the fault classification is
        lost at exactly the boundary where it is being carried somewhere."""
        original = InvalidGs1PayloadError(
            'boom', source=InvalidGs1PayloadError.GRAMMAR, part='token')
        for rebuilt in (copy.copy(original), copy.deepcopy(original),
                        pickle.loads(pickle.dumps(original))):
            assert isinstance(rebuilt, InvalidGs1PayloadError)
            assert str(rebuilt) == 'boom'
            assert rebuilt.source == InvalidGs1PayloadError.GRAMMAR
            assert rebuilt.part == 'token'

    @pytest.mark.unit
    def test_the_copy_is_faithful_and_not_merely_classified(self):
        """A hand-written `__reduce__` decides what survives, so what it leaves
        out is a silent loss rather than an error. Rebuilding the base class by
        name would downcast a subclass; the two-element form would drop both any
        attribute a caller had attached and every arg after the first, changing
        `str()` on the way through. All three are pinned here so the copy stays
        a copy."""
        class Subclass(InvalidGs1PayloadError):
            pass

        original = Subclass('boom', source=InvalidGs1PayloadError.PAYLOAD)
        original.args = ('boom', 'and the rest')
        original.annotated_by_a_handler = 'still here'

        rebuilt = copy.deepcopy(original)
        assert type(rebuilt) is Subclass
        assert rebuilt.args == ('boom', 'and the rest')
        assert str(rebuilt) == str(original)
        assert rebuilt.annotated_by_a_handler == 'still here'
        assert rebuilt.source == InvalidGs1PayloadError.PAYLOAD

    @pytest.mark.unit
    @pytest.mark.parametrize('call, part', [
        # Every raise site that names a knob, one case each.
        (lambda: encode(ID, ai='', token=TOKEN), 'ai'),                # blank
        (lambda: encode(ID, ai=AI, token=' WIT'), 'token'),            # padded
        (lambda: encode(ID, ai='9\t6', token=TOKEN), 'ai'),            # control
        (lambda: encode(ID, ai='4311', token=TOKEN), 'marker'),        # 43xx
        (lambda: encode(ID, ai=AI,                                     # no room
                        token='W' * MAX_DATA_FIELD_LENGTH), 'token'),
        (lambda: decode('96WITABC1234567', ai=AI, token=TOKEN,
                        fnc1_substitute='~~'), 'fnc1_substitute'),
        (lambda: decode('96WITABC1234567', ai=AI, token=TOKEN,
                        fnc1_substitute=AI[0]), 'fnc1_substitute'),
    ])
    def test_grammar_faults_name_their_source_and_part(self, call, part):
        with pytest.raises(InvalidGs1PayloadError) as exc:
            call()
        assert exc.value.source == InvalidGs1PayloadError.GRAMMAR
        assert exc.value.part == part

    @pytest.mark.unit
    def test_the_split_pair_is_attributed_to_the_marker_not_to_one_half(self):
        """ai='4' and token='311' assemble the barred string with neither half
        wrong on its own, so naming one key would send an operator to the wrong
        line of .env."""
        with pytest.raises(InvalidGs1PayloadError) as exc:
            encode('X', ai='4', token='311')
        assert exc.value.part == 'marker'

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_id', [
        '', None, 'ABC 234567',
        # Overlong: computed from the bound and this file's own TOKEN, not
        # spelled. The field counts token + id together, so a literal length is
        # a grammar hardcode wearing a different hat — raising the bound or
        # shortening TOKEN would make it a perfectly valid id and the case would
        # stop testing anything, silently.
        'A' * (MAX_DATA_FIELD_LENGTH - len(TOKEN) + 1),
    ])
    def test_id_faults_are_payload_faults_naming_no_knob(self, bad_id):
        """Blank, non-str, unencodable and overlong: all four of `encode`'s id
        rules. None of them is anybody's configuration."""
        with pytest.raises(InvalidGs1PayloadError) as exc:
            encode(bad_id, ai=AI, token=TOKEN)
        assert exc.value.source == InvalidGs1PayloadError.PAYLOAD
        assert exc.value.part is None


class TestInternalPayload:

    @pytest.mark.unit
    def test_is_a_frozen_dataclass(self):
        """A decoded scan cannot be mutated downstream."""
        assert dataclasses.is_dataclass(InternalPayload)
        payload = InternalPayload(internal_id=ID, ai=AI, token=TOKEN, raw='96WITABC1234567')
        with pytest.raises(dataclasses.FrozenInstanceError):
            payload.internal_id = 'HACKED'

    @pytest.mark.unit
    def test_fields(self):
        names = [f.name for f in dataclasses.fields(InternalPayload)]
        assert names == ['internal_id', 'ai', 'token', 'raw']


class TestPureModuleHasNoAppImports:

    @pytest.mark.unit
    def test_module_imports_only_stdlib(self):
        """The pure module must not pull in Flask/SQLAlchemy/app packages."""
        import app.utils.gs1 as gs1_mod

        source = gs1_mod.__file__
        with open(source, 'r') as fh:
            text = fh.read()
        for forbidden in ('import flask', 'from flask', 'sqlalchemy',
                          'from app', 'import app'):
            assert forbidden not in text
        # The absolute forms above leave the hole that actually matters: every
        # intra-package import in this app is relative, so the realistic purity
        # violation is `from ..database import Product` — which matches none of
        # those five literals and would sail through. Checked per line at the
        # start of the statement rather than as a substring, because 'from .'
        # also occurs in prose (gtin.py has "a bare AttributeError from
        # .strip()") where it is not an import at all.
        for line in text.splitlines():
            assert not line.lstrip().startswith('from .'), line
