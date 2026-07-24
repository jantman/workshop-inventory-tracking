"""
Unit tests for the pure GS1 module (Story 2.4, app/utils/gs1.py).

Exercises encode / decode / InternalPayload and the pure rows of the story's
I/O & edge-case matrix. This module is the single source of truth for the AI-96
element-string grammar, so it is tested here in isolation (no Flask/DB), with
particular attention to (a) FNC1 transmission variance and (b) foreign payloads
never resolving as internal ones.
"""

import dataclasses

import pytest

from app.utils.gs1 import (
    FNC1,
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
