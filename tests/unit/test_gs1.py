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

import dataclasses

import pytest

from app.utils.gs1 import (
    FNC1,
    MAX_DATA_FIELD_LENGTH,
    InternalPayload,
    InvalidGs1PayloadError,
    decode,
    encode,
)

# The deployed grammar (config defaults GS1_INTERNAL_AI / GS1_INTERNAL_TOKEN).
AI = '96'
TOKEN = 'WIT'
ID = 'ABC1234567'


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
