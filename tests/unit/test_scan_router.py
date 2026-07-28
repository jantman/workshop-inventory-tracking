"""
Unit tests for the pure scan classifier (Story 4.2, app/utils/scan_router.py).

Exercises `classify()` and the frozen `ScanClassification` / `ScanKind` shapes
against every row of the story's I/O & edge-case matrix: FR36's four-rule
precedence, FR37's optional AIM symbology prefix, FR37a's bare deployed-wedge
form, and NFR8's "a scan never raises".

Requires **no fixtures at all** — the same posture as tests/unit/test_gtin.py
and tests/unit/test_gs1.py. That is not incidental tidiness: AD-4/AD-5 make the
classifier pure, so needing a Flask app, a client or a database here would
itself be the failure. Every test below constructs its input from literals and
calls the function.

The one thing this module imports beyond the code under test is `Config`, and
only `TestModulePurity` uses it. That import is not fixture-free in the strict
sense — `config.py` calls `load_dotenv()` at import — but AD-16 is a statement
about the *configured* grammar, so a test that restated the grammar as a
literal would keep guarding a pair that was no longer deployed. Reading it is
the point of that test; see its own docstring.

The `ScanClassification` shape is tested here rather than in a models test
because it is this epic's contract, not a metal-stock domain model: it exists
so Stories 4.3/4.5 and Epics 7/9 can be written against one frozen structure,
and the tests that pin it belong beside the only code that produces it.
"""

import ast
import copy
import dataclasses
from collections import defaultdict
from pathlib import Path
from types import MappingProxyType

import pytest

from app import models
from app.models import ScanClassification, ScanKind
from app.utils import ecia, scan_router
from app.utils.gs1 import MAX_DATA_FIELD_LENGTH, InvalidGs1PayloadError
from app.utils.gtin import is_valid_gtin
from app.utils.scan_router import classify, strip_aim_prefix
from config import Config

# The deployed grammar (config defaults GS1_INTERNAL_AI / GS1_INTERNAL_TOKEN),
# passed explicitly on every call — the classifier holds no default (AD-16).
AI = '96'
TOKEN = 'WIT'
ID = 'ABC1234567'
INTERNAL_SCAN = AI + TOKEN + ID                 # '96WITABC1234567'

# The repo's canonical ECIA vectors (tests/unit/test_gs1.py, test_scan_routes.py).
ECIA_SHORT = '[)>\x1e06\x1dP123\x1e\x04'
ECIA_FULL = '[)>\x1e06\x1dP12345\x1d1PABC\x1dQ10\x1d\x1e\x04'

# A check-digit-valid EAN-13 and its canonical 14-digit key.
GTIN13 = '9506000134352'
GTIN13_KEY = '09506000134352'


class TestScanClassificationShape:
    """AD-15: the frozen four-field contract every scan consumer depends on."""

    @pytest.mark.unit
    def test_has_exactly_the_four_ad15_fields_in_order(self):
        names = tuple(f.name for f in dataclasses.fields(ScanClassification))
        assert names == ('kind', 'normalized_value', 'ecia_fields', 'raw')

    @pytest.mark.unit
    def test_is_frozen(self):
        """Consumers pass a classification around without defensive copying."""
        c = classify(INTERNAL_SCAN, ai=AI, token=TOKEN)
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.kind = ScanKind.FREE_TEXT

    @pytest.mark.unit
    @pytest.mark.parametrize('field_name', [
        'kind',                 # which rule matched
        'normalized_value',     # the canonical form, or None
        'ecia_fields',          # the parsed MH10.8.2 identifiers, or None
        'raw',                  # the verbatim scan
    ])
    def test_every_field_is_mutation_proof(self, field_name):
        c = classify(GTIN13, ai=AI, token=TOKEN)
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(c, field_name, None)

    @pytest.mark.unit
    @pytest.mark.parametrize('kwargs', [
        {},                                                          # nothing at all
        {'kind': ScanKind.GTIN},                                     # kind only
        {'kind': ScanKind.GTIN, 'normalized_value': GTIN13_KEY},     # missing ecia_fields/raw
        {'kind': ScanKind.GTIN, 'normalized_value': GTIN13_KEY,
         'ecia_fields': None},                                       # missing raw
    ])
    def test_all_four_fields_are_required_with_no_defaults(self, kwargs):
        """No consumer can construct a half-populated classification."""
        with pytest.raises(TypeError):
            ScanClassification(**kwargs)

    @pytest.mark.unit
    def test_no_field_carries_a_default(self):
        for f in dataclasses.fields(ScanClassification):
            assert f.default is dataclasses.MISSING
            assert f.default_factory is dataclasses.MISSING

    @pytest.mark.unit
    def test_scan_kind_has_exactly_the_four_fr36_members(self):
        assert [k.name for k in ScanKind] == [
            'INTERNAL', 'ECIA', 'GTIN', 'FREE_TEXT']

    @pytest.mark.unit
    @pytest.mark.parametrize('member, wire_value', [
        (ScanKind.INTERNAL, 'internal'),      # AD-15 spells the kinds lowercase...
        (ScanKind.ECIA, 'ecia'),              # ...because they are serialized as JSON,
        (ScanKind.GTIN, 'gtin'),              # beside the existing `outcome: 'unrouted'`,
        (ScanKind.FREE_TEXT, 'free_text'),    # and are never persisted.
    ])
    def test_wire_values_are_the_lowercase_ad15_spellings(self, member, wire_value):
        assert member.value == wire_value
        assert ScanKind(wire_value) is member


class TestInternalRecognition:
    """FR36 rule 1 / FR37a: a label this system printed, recognized by delegation."""

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        INTERNAL_SCAN,                        # FR37a: the deployed wedge strips FNC1 entirely
        '\x1d' + INTERNAL_SCAN,               # GS transmitted in first position
        ']d1' + INTERNAL_SCAN,                # FR37: behind a DataMatrix AIM identifier
        ']C1' + INTERNAL_SCAN,                # ...and behind a GS1-128 one
    ])
    def test_every_transmission_form_classifies_internal(self, raw):
        c = classify(raw, ai=AI, token=TOKEN)
        assert c.kind is ScanKind.INTERNAL

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        INTERNAL_SCAN,                        # bare
        '\x1d' + INTERNAL_SCAN,               # FNC1 transmitted
        ']d1' + INTERNAL_SCAN,                # AIM-prefixed
    ])
    def test_normalized_value_is_the_token_stripped_id(self, raw):
        """Exactly what gs1.decode returns and what Story 2.4 stored — a
        resolver must never have to strip it a second time (AD-16)."""
        assert classify(raw, ai=AI, token=TOKEN).normalized_value == ID

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        INTERNAL_SCAN,                        # bare
        '\x1d' + INTERNAL_SCAN,               # the FNC1 stays on `raw`...
        ']d1' + INTERNAL_SCAN,                # ...and so does the AIM prefix
    ])
    def test_raw_is_the_verbatim_argument(self, raw):
        assert classify(raw, ai=AI, token=TOKEN).raw == raw

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '96XYZ' + ID,                          # AI 96 but a foreign token (FR12a)
        '0109506000134352',                    # AI 01 GTIN-14 element string
        '\x1d21SN0001',                        # AI 21 serial number
        'B08N5WRWNW',                          # Amazon ASIN
        'JA000123',                            # this system's legacy metal-stock JA ID
        ECIA_FULL,                             # a distributor envelope
    ])
    def test_foreign_payloads_are_never_internal(self, raw):
        assert classify(raw, ai=AI, token=TOKEN).kind is not ScanKind.INTERNAL

    @pytest.mark.unit
    def test_recognition_follows_the_configured_grammar_not_a_literal(self):
        """AD-16: one config change moves the encoder and this router together.

        The same string is internal under one grammar and free text under
        another, and vice versa — proof the classifier pattern-matches nothing
        itself.
        """
        assert classify(INTERNAL_SCAN, ai=AI, token=TOKEN).kind is ScanKind.INTERNAL
        assert classify(INTERNAL_SCAN, ai='97', token=TOKEN).kind is ScanKind.FREE_TEXT
        assert classify(INTERNAL_SCAN, ai=AI, token='XYZ').kind is ScanKind.FREE_TEXT

        other = '97XYZ' + ID
        assert classify(other, ai=AI, token=TOKEN).kind is ScanKind.FREE_TEXT
        assert classify(other, ai='97', token='XYZ').kind is ScanKind.INTERNAL
        assert classify(other, ai='97', token='XYZ').normalized_value == ID

    @pytest.mark.unit
    def test_ecia_fields_is_none_for_an_internal_scan(self):
        assert classify(INTERNAL_SCAN, ai=AI, token=TOKEN).ecia_fields is None


class TestEciaEnvelopeRecognition:
    """FR36 rule 2: an ISO/IEC 15434 format-06 envelope that something could
    actually be read out of. The header is recognized and the records are
    parsed by `app/utils/ecia.py` (whose own grammar tests are
    tests/unit/test_ecia.py); this class pins what `classify()` does with the
    two answers."""

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        ECIA_SHORT,                            # the short repo vector
        ECIA_FULL,                             # the full P/1P/Q record vector
        ']d1' + ECIA_SHORT,                    # FR37: behind an AIM identifier
        '[)>\x1e06\x1dP123',                   # no trailing RS/EOT
        '[)>\x1e06\x1d1TLOT9\x1dP123',         # an unrecognized identifier alongside a known one
    ])
    def test_an_envelope_carrying_a_recognized_identifier_classifies_ecia(self, raw):
        assert classify(raw, ai=AI, token=TOKEN).kind is ScanKind.ECIA

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '[)>\x1e06',                           # header with no body — a legal but empty message
        '[)>\x1e06\x1e',                       # header closed immediately by RS
        '[)>\x1e06\x1d',                       # ...and by a bare GS
        '[)>\x1e06\x1d!!!garbage!!!',          # a valid header, an unreadable body
        '[)>\x1e06\x1d1TLOT9\x1d4LUS\x1e\x04',  # only identifiers this system has no field for
        '[)>\x1e06\x1dQ\x1e\x04',              # a recognized identifier with an empty value
        ']d1[)>\x1e06',                        # ...and the same behind an AIM prefix
    ])
    def test_an_envelope_carrying_nothing_recognized_degrades_to_free_text(self, raw):
        """NFR8/AD-5, and the one behavior this story CHANGES: at `035f226`
        these classified `ecia` with no fields. `ECIA` exists so a consumer can
        pre-fill a form from named fields, so answering it with none would put
        the operator on a screen that says "distributor label" about a scan
        nothing could be read from. `free_text` puts the raw scan into a search
        instead, which is what "surfaced for manual handling" means everywhere
        else in this epic."""
        c = classify(raw, ai=AI, token=TOKEN)
        assert c.kind is ScanKind.FREE_TEXT
        assert c.ecia_fields is None
        assert c.normalized_value is None
        assert c.raw == raw

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '[)>06\x1dP123',                       # RS missing after the message-header characters
        '[)>\x1e05\x1dP123',                   # format 05, not 06
        '[)>\x1e06P123',                       # indicator not delimited — only resembles an envelope
        '[)>\x1e0612345',                      # ...same, with digits abutting the indicator
        '[)>\x1e0',                            # truncated indicator
        '[)>\x1e',                             # truncated header
        '[)>',                                 # message-header characters alone
        ' [)>\x1e06\x1dP123',                  # leading space: classify() never re-trims
        'PRE[)>\x1e06\x1dP123',                # header not at the front
    ])
    def test_damaged_or_foreign_headers_fall_through_to_free_text(self, raw):
        """NFR8: never an exception, and never a false `ecia` handed to 4.5."""
        assert classify(raw, ai=AI, token=TOKEN).kind is ScanKind.FREE_TEXT

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        ECIA_SHORT,                            # the short repo vector
        ECIA_FULL,                             # the full P/1P/Q record vector
        ']d1' + ECIA_FULL,                     # FR37: the parse runs on the stripped candidate
        '[)>\x1e06\x1dP123',                   # no trailer
    ])
    def test_ecia_carries_the_parsed_fields_and_no_normalized_value(self, raw):
        """The fields are whatever the grammar module reads out of the
        AIM-STRIPPED candidate — asserted against `ecia.parse_fields` rather
        than against a written-out dict, so this test cannot drift from the
        single source of truth it delegates to."""
        c = classify(raw, ai=AI, token=TOKEN)
        assert c.normalized_value is None
        assert c.raw == raw
        expected = ecia.parse_fields(strip_aim_prefix(raw))
        assert expected                        # or this vector belongs above
        assert dict(c.ecia_fields) == expected

    @pytest.mark.unit
    def test_the_canonical_vector_yields_the_ad15_keys(self):
        """One end-to-end statement of what a DigiKey label actually produces,
        so the delegation above is not the only thing pinning it."""
        c = classify(ECIA_FULL, ai=AI, token=TOKEN)
        assert dict(c.ecia_fields) == {'P': '12345', '1P': 'ABC', 'Q': '10'}

    @pytest.mark.unit
    def test_an_aim_prefix_changes_nothing_but_raw(self):
        bare = classify(ECIA_FULL, ai=AI, token=TOKEN)
        prefixed = classify(']d1' + ECIA_FULL, ai=AI, token=TOKEN)
        assert dict(prefixed.ecia_fields) == dict(bare.ecia_fields)
        assert prefixed.raw.startswith(']d1')

    @pytest.mark.unit
    def test_the_fields_are_read_only_and_not_shared_between_calls(self):
        """`__post_init__` copies the parser's fresh dict into a proxy, so two
        classifications of one scan share no mutable state and neither can be
        written through."""
        first = classify(ECIA_FULL, ai=AI, token=TOKEN)
        second = classify(ECIA_FULL, ai=AI, token=TOKEN)
        assert first.ecia_fields is not second.ecia_fields
        assert first.ecia_fields == second.ecia_fields
        with pytest.raises(TypeError):
            first.ecia_fields['P'] = 'MUTATED'


class TestGtinRecognition:
    """FR36 rule 3: a bare trade item number, validated and normalized by gtin.py."""

    @pytest.mark.unit
    @pytest.mark.parametrize('raw, key', [
        ('00012348', '00000000012348'),         # GTIN-8
        ('012345678905', '00012345678905'),     # UPC-A
        (GTIN13, GTIN13_KEY),                   # EAN-13
        (GTIN13_KEY, GTIN13_KEY),               # GTIN-14, already canonical
        ('00000012345670', '00000012345670'),   # check digit 0 — not a no-read
    ])
    def test_every_accepted_length_normalizes_to_the_14_digit_key(self, raw, key):
        c = classify(raw, ai=AI, token=TOKEN)
        assert c.kind is ScanKind.GTIN
        assert c.normalized_value == key
        assert len(c.normalized_value) == 14
        assert c.raw == raw
        assert c.ecia_fields is None

    @pytest.mark.unit
    def test_all_four_forms_of_one_number_share_one_normalized_value(self):
        """Lookup is against the normalized-14 namespace, so the four
        encodings of one product must classify to one key."""
        key = '00000000012348'
        forms = [key[6:], key[2:], key[1:], key]     # GTIN-8 / UPC-A / EAN-13 / GTIN-14
        assert {classify(f, ai=AI, token=TOKEN).normalized_value for f in forms} == {key}

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '9506000134353',                        # bad check digit (last digit of GTIN13 + 1)
        '012345678900',                         # bad check digit, UPC-A length
        '00000000',                             # wedge no-read: mod-10 valid, refused by gtin.py
        '00000000000000',                       # the same no-read, already 14 wide
        '12345678901',                          # 11 digits — not an accepted length
        '0109506000134352',                     # 16 digits — an AI-01 element string, not a GTIN
        '1234567',                              # 7 digits
        '123456789',                            # 9 digits
        '950-6000134352',                       # separator
        '+9506000134352',                       # sign
        '950 6000134352',                       # interior space
        '٩٥٠٦٠٠٠١٣٤٣٥٢',                        # Arabic-Indic digits — ASCII only
        '\x1d9506000134352',                    # leading GS: gtin.py would strip it, we must not
        '9506000134352\x1e',                    # trailing RS, likewise
        ' 9506000134352 ',                      # surrounding spaces: classify() never re-trims
    ])
    def test_every_rejection_reason_falls_through_to_free_text(self, raw):
        c = classify(raw, ai=AI, token=TOKEN)
        assert c.kind is ScanKind.FREE_TEXT
        assert c.normalized_value is None

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        GTIN13,                                 # bare
        ']d1' + GTIN13,                         # FR37: the same symbology carries both kinds
        ']C1' + GTIN13,                         # ...whatever the symbology class
    ])
    def test_aim_prefixed_gtin_is_still_a_gtin(self, raw):
        c = classify(raw, ai=AI, token=TOKEN)
        assert c.kind is ScanKind.GTIN
        assert c.normalized_value == GTIN13_KEY
        assert c.raw == raw                     # the prefix survives on `raw`


class TestFreeTextFallthrough:
    """FR36 rule 4: always matches, so no scan ever dead-ends."""

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        'RES 10K 0805 1%',                      # a human-typed part description
        '',                                     # empty string
        '   ',                                  # whitespace only — classify() does not trim
        'B08N5WRWNW',                           # Amazon ASIN
        'X001ABCDEF',                           # Amazon FNSKU
        'https://example.com/p/1',              # a QR code carrying a URL
        'JA000123',                             # legacy metal-stock JA ID
        'M1-A',                                 # a storage-location label
        '\x00\x01\x02',                         # bare control characters
        '\n\t',                                 # whitespace the caller would have trimmed
    ])
    def test_unrecognized_input_classifies_free_text(self, raw):
        c = classify(raw, ai=AI, token=TOKEN)
        assert c.kind is ScanKind.FREE_TEXT
        assert c.normalized_value is None
        assert c.ecia_fields is None
        assert c.raw == raw

    @pytest.mark.unit
    def test_empty_string_keeps_an_empty_raw(self):
        c = classify('', ai=AI, token=TOKEN)
        assert c.kind is ScanKind.FREE_TEXT
        assert c.raw == ''


class TestPrecedenceOrder:
    """FR36: the first matching rule wins, and the result is deterministic."""

    @pytest.mark.unit
    def test_rule_1_beats_rule_3_when_the_token_is_numeric(self):
        """A value that is simultaneously a valid EAN-13 and an internal
        payload is OURS: a label this shop printed must never resolve to
        somebody else's trade item.
        """
        raw = '9601234567898'                   # valid EAN-13 check digit, opens '960'
        assert is_valid_gtin(raw)               # rule 3 would have matched
        c = classify(raw, ai=AI, token='0')     # ...but the grammar '96' + '0' matches first
        assert c.kind is ScanKind.INTERNAL
        assert c.normalized_value == '1234567898'
        # And with a grammar it does not match, the same string is a GTIN.
        assert classify(raw, ai=AI, token=TOKEN).kind is ScanKind.GTIN

    @pytest.mark.unit
    def test_rule_2_beats_rule_4_for_an_envelope(self):
        assert classify(ECIA_SHORT, ai=AI, token=TOKEN).kind is ScanKind.ECIA

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        INTERNAL_SCAN,                          # rule 1
        ECIA_SHORT,                             # rule 2
        GTIN13,                                 # rule 3
        'RES 10K 0805 1%',                      # rule 4
    ])
    def test_classification_depends_on_nothing_but_its_arguments(self, raw):
        """Deterministic and repeatable — no clock, no config read, no state."""
        first = classify(raw, ai=AI, token=TOKEN)
        assert first == classify(raw, ai=AI, token=TOKEN)
        assert first == classify(raw, ai=AI, token=TOKEN)

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        INTERNAL_SCAN,                          # rule 1
        ECIA_SHORT,                             # rule 2
        GTIN13,                                 # rule 3
        'RES 10K 0805 1%',                      # rule 4
        '',                                     # rule 4, degenerate
    ])
    def test_every_scan_gets_exactly_one_kind(self, raw):
        c = classify(raw, ai=AI, token=TOKEN)
        assert isinstance(c, ScanClassification)
        assert c.kind in set(ScanKind)

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        INTERNAL_SCAN,                          # internal
        GTIN13,                                 # gtin
        'RES 10K 0805 1%',                      # free text
        '[)>\x1e06',                            # an envelope that degraded to free text
    ])
    def test_ecia_fields_is_none_for_every_non_ecia_kind(self, raw):
        """AD-15's permanent rule, and `__post_init__` enforces it — but only
        the classifier can be wrong about which kind a scan is, and the
        degraded envelope is the vector where a sloppy rule 2 would leak an
        empty mapping onto a `FREE_TEXT` result."""
        c = classify(raw, ai=AI, token=TOKEN)
        assert c.kind is not ScanKind.ECIA
        assert c.ecia_fields is None


class TestAimSymbologyPrefix:
    """FR37: an AIM identifier narrows the symbology class, never the handler."""

    @pytest.mark.unit
    @pytest.mark.parametrize('prefix', [
        ']d1',                                  # DataMatrix
        ']d2',                                  # DataMatrix, GS1 FNC1 in first position
        ']C1',                                  # GS1-128
        ']Q3',                                  # QR code
        ']E0',                                  # EAN/UPC
        ']z9',                                  # Aztec Code — a letter this shop never sees
    ])
    def test_any_well_formed_prefix_is_stripped_before_the_rules_run(self, prefix):
        assert classify(prefix + INTERNAL_SCAN, ai=AI, token=TOKEN).kind is ScanKind.INTERNAL
        assert classify(prefix + GTIN13, ai=AI, token=TOKEN).kind is ScanKind.GTIN
        assert classify(prefix + ECIA_SHORT, ai=AI, token=TOKEN).kind is ScanKind.ECIA

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        ']' + INTERNAL_SCAN,                    # ']9...' — second char is not a letter
        ']]d1' + INTERNAL_SCAN,                 # doubled bracket
        ']dd' + INTERNAL_SCAN,                  # third char is not a digit
        ']d' + ECIA_SHORT,                      # only two characters before the payload
        '] d1' + INTERNAL_SCAN,                 # a space where the code character belongs
        ']1d' + INTERNAL_SCAN,                  # letter and digit transposed
        ' ]d1' + INTERNAL_SCAN,                 # not at the front — classify() never trims
    ])
    def test_a_leading_bracket_in_any_other_shape_is_data_not_a_prefix(self, raw):
        """Only the exact 3-character AIM shape is a prefix; the rest is payload."""
        assert classify(raw, ai=AI, token=TOKEN).kind is ScanKind.FREE_TEXT

    @pytest.mark.unit
    def test_the_prefix_is_stripped_exactly_once(self):
        """A second identifier is data emitted by a doubly-prefixing scanner,
        not a nested prefix."""
        assert classify(']d1]d1' + INTERNAL_SCAN,
                        ai=AI, token=TOKEN).kind is ScanKind.FREE_TEXT

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        ']d1',                                  # a prefix and nothing else
        ']d1]d1',                               # ...twice
        ']d1RES 10K',                           # a prefix in front of free text
    ])
    def test_a_prefix_alone_or_in_front_of_junk_is_free_text(self, raw):
        c = classify(raw, ai=AI, token=TOKEN)
        assert c.kind is ScanKind.FREE_TEXT
        assert c.raw == raw                     # never re-emitted without the prefix

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        ']d1' + INTERNAL_SCAN,                  # internal
        ']d1' + ECIA_SHORT,                     # ecia
        ']d1' + GTIN13,                         # gtin
        ']d1RES 10K',                           # free text
    ])
    def test_raw_always_keeps_the_prefix(self, raw):
        """The prefix is removed to choose a rule, never from the result."""
        assert classify(raw, ai=AI, token=TOKEN).raw == raw
        assert classify(raw, ai=AI, token=TOKEN).raw.startswith(']d1')


class TestNeverRaisesOnScanData:
    """NFR8: no value of a `str` raw is an exception."""

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        '',                                     # empty
        ' ',                                    # blank
        '\x00' * 100,                           # NUL run
        ''.join(chr(i) for i in range(32)),     # every C0 control character
        '\x1d' * 50,                            # a storm of GS separators
        '[)>' * 50,                             # repeated message-header characters
        ']' * 50,                               # repeated AIM brackets
        '9' * 4096,                             # a very long all-digit string
        '\U0001f600' * 100,                     # astral-plane characters
        '\ud83d',                               # a lone surrogate, as Python allows in a str
    ])
    def test_hostile_scan_data_still_returns_a_classification(self, raw):
        c = classify(raw, ai=AI, token=TOKEN)
        assert isinstance(c, ScanClassification)
        assert c.raw == raw

    @pytest.mark.unit
    def test_a_4096_character_adversarial_payload_is_free_text(self):
        """A full `app.utils.scan_input.MAX_SCAN_LENGTH` worth of the nastiest
        bytes a keyboard wedge could plausibly emit."""
        chunk = ']d1[)>\x1e0\x1d\x1e\x04]\x00\x1f96WIT'
        raw = (chunk * (4096 // len(chunk) + 1))[:4096]
        assert len(raw) == 4096
        c = classify(raw, ai=AI, token=TOKEN)
        assert c.kind is ScanKind.FREE_TEXT
        assert c.raw == raw

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        INTERNAL_SCAN[:1],                      # a truncated internal payload...
        INTERNAL_SCAN[:2],
        INTERNAL_SCAN[:4],
        INTERNAL_SCAN[:5],                      # ...right up to AI + token with no id
        ECIA_SHORT[:1],                         # ...and a truncated envelope, one char at a time
        ECIA_SHORT[:3],
        ECIA_SHORT[:4],
        ECIA_SHORT[:5],
        GTIN13[:12],                            # a GTIN missing its check digit
    ])
    def test_truncated_payloads_classify_without_raising(self, raw):
        assert isinstance(classify(raw, ai=AI, token=TOKEN), ScanClassification)


class TestCallerFaults:
    """The only two reachable exceptions, both faults of the caller."""

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        123,                                    # an int
        None,                                   # absent
        b'96WIT',                               # bytes — the transport decodes, we do not
        ['96WIT'],                              # a list
        12.0,                                   # a float
        object(),                               # anything else
    ])
    def test_non_str_raw_raises_typeerror(self, raw):
        """A non-string is a malformed caller, not a scan: it must not be
        buried as a free-text search result."""
        with pytest.raises(TypeError):
            classify(raw, ai=AI, token=TOKEN)

    @pytest.mark.unit
    @pytest.mark.parametrize('ai, token', [
        ('', TOKEN),                            # blank AI
        ('   ', TOKEN),                         # whitespace-only AI
        (None, TOKEN),                          # non-string AI
        (96, TOKEN),                            # an int AI
        (AI, ''),                               # blank token — would make every AI-96 label ours
        (AI, None),                             # non-string token
        (AI, ' WIT'),                           # a padded token from a .env file
        ('43', '1'),                            # FR12d: no element string may open 43xx
        ('4', '311'),                           # ...including the split configuration
        (AI, 'W' * MAX_DATA_FIELD_LENGTH),      # a token with no room for an id after it
    ])
    def test_malformed_grammar_propagates_invalidgs1payloaderror(self, ai, token):
        """A config fault must surface, not silently disable rule 1 and
        reclassify every internal label as free text."""
        with pytest.raises(InvalidGs1PayloadError):
            classify(INTERNAL_SCAN, ai=ai, token=token)

    @pytest.mark.unit
    def test_the_rejected_value_is_bounded_before_it_is_rendered(self):
        """The message ends up in a log, and the value is untrusted and of
        unknown size. Bounding after `repr()` would cap the log line but not
        the multi-megabyte escaped string built to produce it, which is what
        the bound was for.

        The length assertion alone cannot tell the two implementations apart —
        a post-slice-only version produces a 566-character message and passes
        it — so the slice order is pinned directly: this probe reports one
        thing when sliced and another when repr'd whole.
        """
        class SlicesSmallReprsHuge:
            def __getitem__(self, index):
                return 'SLICED'

            def __repr__(self):
                return 'X' * 5_000_000

        with pytest.raises(TypeError) as exc:
            classify(b'\x00' * 5_000_000, ai=AI, token=TOKEN)
        assert len(str(exc.value)) < 2_000

        # Not sliceable-by-allow-list, so this one proves the *other* branch:
        # repr'd whole, then truncated, and still bounded.
        with pytest.raises(TypeError) as exc:
            classify(SlicesSmallReprsHuge(), ai=AI, token=TOKEN)
        assert len(str(exc.value)) < 2_000

    @pytest.mark.unit
    def test_describing_a_bad_raw_does_not_mutate_it(self):
        """`value[:512]` on an arbitrary object runs its `__getitem__`, and a
        `defaultdict` answers that by *inserting* the key. A module whose
        entire contract is purity must not modify what it was handed, least of
        all while building an error message about it — so only types known to
        slice without side effects are sliced."""
        victim = defaultdict(list)
        with pytest.raises(TypeError):
            classify(victim, ai=AI, token=TOKEN)
        assert dict(victim) == {}

    @pytest.mark.unit
    def test_a_hostile_repr_does_not_replace_the_documented_typeerror(self):
        """`classify` promises TypeError for a non-str `raw`. Letting an
        object's own `__repr__` raise through the guard would break that
        contract for the sake of a diagnostic."""
        class Hostile:
            def __repr__(self):
                raise RuntimeError('no repr for you')

        with pytest.raises(TypeError):
            classify(Hostile(), ai=AI, token=TOKEN)

    @pytest.mark.unit
    def test_ai_and_token_are_keyword_only_with_no_defaults(self):
        """AD-16: the grammar must always be supplied explicitly."""
        with pytest.raises(TypeError):
            classify(INTERNAL_SCAN)                      # no grammar at all
        with pytest.raises(TypeError):
            classify(INTERNAL_SCAN, AI, TOKEN)           # positional


class TestModulePurity:
    """AD-4/AD-5/AD-16 are stated invariants no behavioral test can catch being
    violated: importing Flask or hardcoding the deployed grammar would leave
    the whole suite green. These read the source instead."""

    SOURCE_PATH = Path(scan_router.__file__)
    # One name per delegated rule: rule 1 to `gs1`, rule 2 to `ecia`, rule 3 to
    # `gtin`. Rule 4 has no grammar to delegate.
    ALLOWED_APP_UTILS_NAMES = frozenset({'ecia', 'gs1', 'gtin'})

    def _tree(self):
        return ast.parse(self.SOURCE_PATH.read_text(encoding='utf-8'))

    def _string_literals_outside_docstrings(self):
        """Every `str` constant the module actually executes.

        Docstrings are excluded because they are prose, not behavior: the
        module's own `classify()` example deliberately uses an illustrative
        grammar, and prose is where a two-character AI collides by accident.
        """
        tree = self._tree()
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                first = node.body[0] if node.body else None
                if (isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    docstrings.add(id(first.value))
        return [node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings]

    @pytest.mark.unit
    def test_only_gs1_and_gtin_are_taken_from_app_utils(self):
        """`from app.utils import <x>` must not smuggle in a non-pure sibling."""
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.ImportFrom) and node.module == 'app.utils':
                names = {alias.name for alias in node.names}
                assert names <= self.ALLOWED_APP_UTILS_NAMES, (
                    f'unexpected app.utils import: {sorted(names)}')

    @pytest.mark.unit
    def test_uses_no_relative_imports(self):
        """A relative import would slip past the module check above."""
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.ImportFrom):
                assert node.level == 0

    @pytest.mark.unit
    def test_no_executed_string_literal_holds_the_deployed_grammar(self):
        """AD-16: the AI and the token come from config and are passed in, so
        one config change moves the encoder and the router together. A literal
        that the module can *act on* is the drift that rule exists to prevent.

        The values are read from `Config`, not restated here. Hardcoding them
        would defeat the rule this test enforces: change the config pair and a
        literal test would keep guarding a grammar that is no longer deployed
        while the module hardcoded the new one and stayed green.

        Only executed string constants are searched, not the raw source. A
        substring scan over the whole file was a false-positive machine: the
        AI is two characters, this module is dense with prose, and its own
        `classify()` docstring carries a deliberately illustrative
        `ai='91', token='ZZ'` example — so configuring `GS1_INTERNAL_AI=91`
        red-built a module that had not changed and was not wrong. AD-16 is a
        claim about behavior, and a docstring has none.
        """
        literals = self._string_literals_outside_docstrings()
        for name in ('GS1_INTERNAL_AI', 'GS1_INTERNAL_TOKEN'):
            configured = getattr(Config, name)
            assert configured, f'{name} must be configured for this test to mean anything'
            offenders = [lit for lit in literals if configured in lit]
            assert not offenders, (
                f'app/utils/scan_router.py executes a string literal holding '
                f'the configured {name} ({configured!r}): {offenders!r}. '
                f'AD-16 requires it to arrive as an argument.')

    @pytest.mark.unit
    def test_the_whole_import_set_is_exactly_the_declared_four(self):
        """An allow-list, not a deny-list of modules somebody thought of.

        Rejecting only non-stdlib imports leaves `os` (i.e.
        `os.environ['GS1_INTERNAL_AI']` inside `classify()`), `pathlib`,
        `socket`, `sqlite3` and `logging` all green — and a hand-written deny
        list of those still misses `importlib`, whose
        `import_module('flask')` would defeat every other assertion in this
        class. AD-4/AD-5 say no config and no I/O, not merely no Flask, and
        the only airtight way to say that is to name what IS allowed.
        """
        imported = set()
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or '')
        assert imported == {'re', 'typing', 'app.models', 'app.utils'}, (
            f'app/utils/scan_router.py imports {sorted(imported)}; adding to '
            f'that set is an AD-4/AD-5 decision, not an incidental edit')

    @pytest.mark.unit
    def test_source_calls_no_builtin_that_touches_the_outside_world(self):
        """`open()`, `input()`, `print()` and `__import__()` need no import at
        all, so the import-based checks above cannot see them. `print` is here
        because it is I/O by any definition and is the one of these a debugging
        session plausibly leaves behind."""
        forbidden = {'open', 'input', 'print', 'eval', 'exec', '__import__'}
        called = {
            node.func.id for node in ast.walk(self._tree())
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not (called & forbidden), sorted(called & forbidden)

    @pytest.mark.unit
    def test_models_stays_a_leaf_module(self):
        """The dependency runs scan_router -> models, never back. `models.py`
        importing anything from `app.` would close the cycle — and it is a live
        temptation, because `ScanClassification`'s docstring is written
        entirely in terms of scan_router, gs1 and gtin."""
        tree = ast.parse(Path(models.__file__).read_text(encoding='utf-8'))
        offenders = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders.update(a.name for a in node.names if a.name.split('.')[0] == 'app')
            elif isinstance(node, ast.ImportFrom):
                if node.level or (node.module or '').split('.')[0] == 'app':
                    offenders.add(node.module or '<relative>')
        assert not offenders, (
            f'app/models.py must stay a leaf module; it imports {sorted(offenders)}')

    @pytest.mark.unit
    def test_has_no_function_level_imports(self):
        """The import check above walks the whole tree, but a reader should be
        able to see the module's entire dependency set at the top of the file:
        a deferred `import` inside a function body is how a pure module
        usually stops being one."""
        tree = self._tree()
        top_level = set(tree.body)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                assert node in top_level

    @pytest.mark.unit
    def test_classify_runs_with_no_app_context_or_database(self):
        """No Flask application, no request, no database — this whole test
        module is fixture-free, so reaching this assertion is the proof."""
        assert classify('anything at all', ai=AI, token=TOKEN).kind is ScanKind.FREE_TEXT


class TestWhitespaceAsymmetryBetweenRules:
    """`classify()` trims nothing itself, but rule 1 is delegated to
    `gs1.decode`, which opens with `raw.strip()` as its FNC1/CR-LF
    transmission tolerance. The result is that a padded internal payload
    classifies and a padded GTIN or envelope does not. That asymmetry is
    deliberate — a matching tolerance here would be a third copy of the trim
    rule the caller already owns — but it was previously undocumented and
    untested, so the module could have drifted either way unnoticed."""

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        ' ' + INTERNAL_SCAN + ' ',              # a wedge that emits padding
        INTERNAL_SCAN + '\r\n',                 # a CR+LF suffix the caller would have trimmed
        '\x1e\x1d' + INTERNAL_SCAN,             # RS/GS: Python counts \x1c-\x1f as whitespace
    ])
    def test_rule_1_tolerates_padding_because_gs1_decode_does(self, raw):
        assert classify(raw, ai=AI, token=TOKEN).kind is ScanKind.INTERNAL

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        ' ' + GTIN13 + ' ',                     # rule 3 judges the scan as it arrived...
        GTIN13 + '\r\n',
        ' ' + ECIA_SHORT,                       # ...and so does rule 2
        ' ]d1' + INTERNAL_SCAN,                 # a leading space even defeats the AIM strip
    ])
    def test_rules_2_to_4_do_not_tolerate_padding(self, raw):
        """Correct routing for these rules depends on the caller having applied
        `app.utils.scan_input.clean_scan_input`. Pinned so the dependency is
        visible rather than discovered by Story 4.3."""
        assert classify(raw, ai=AI, token=TOKEN).kind is ScanKind.FREE_TEXT

    @pytest.mark.unit
    def test_the_asymmetry_extends_to_the_separators_the_cleaner_preserves(self):
        """The half that actually costs something, and that the space-only
        cases above cannot show.

        `str.strip()` eats \\x1c-\\x1f, so `gs1.decode` absorbs a transmitted
        GS while `clean_scan_input` deliberately does not — it exists to
        preserve the separators an envelope is built from. So a wedge that
        prefixes a GS routes an internal label correctly and misroutes every
        distributor label to free text, and neither the cleaner nor
        `classify()` can close that alone. Pinned so the behavior is visible
        to the story that owns the caller seam rather than discovered from a
        DigiKey label that silently searched.
        """
        assert classify('\x1d' + INTERNAL_SCAN, ai=AI, token=TOKEN).kind is ScanKind.INTERNAL
        assert classify('\x1d' + ECIA_SHORT, ai=AI, token=TOKEN).kind is ScanKind.FREE_TEXT
        assert classify('\x1e' + ECIA_SHORT, ai=AI, token=TOKEN).kind is ScanKind.FREE_TEXT
        assert classify('\x1d' + GTIN13, ai=AI, token=TOKEN).kind is ScanKind.FREE_TEXT
        # And the cleaner cannot be the fix: its trim set is exactly ' \t\r\n'
        # because stripping GS/RS would destroy the envelope it is protecting.
        assert ('\x1d' + ECIA_SHORT).strip(' \t\r\n') == '\x1d' + ECIA_SHORT

    @pytest.mark.unit
    def test_the_cleaned_form_of_each_padded_case_classifies_correctly(self):
        """The other half of the contract: once the caller's rule has run, the
        same scans route as they should. The caller's rule
        (`app.utils.scan_input.clean_scan_input`) trims exactly ' \\t\\r\\n',
        restated here as a literal rather than imported: this file tests
        `classify()`, whose whole contract is that it does no trimming of its
        own, and importing the cleaner would make these cases pass by
        construction instead of pinning the caller's contract as this module
        assumes it. That rule's own coverage lives in
        `tests/unit/test_scan_input.py::TestCleanScanInput`."""
        for raw in (' ' + GTIN13 + ' ', GTIN13 + '\r\n'):
            assert classify(raw.strip(' \t\r\n'), ai=AI, token=TOKEN).kind is ScanKind.GTIN
        assert classify((' ' + ECIA_SHORT).strip(' \t\r\n'),
                        ai=AI, token=TOKEN).kind is ScanKind.ECIA
        assert classify((' ]d1' + INTERNAL_SCAN).strip(' \t\r\n'),
                        ai=AI, token=TOKEN).kind is ScanKind.INTERNAL


class TestAimPrefixIsExportedForConsumers:
    """AD-15 freezes four fields, so the AIM-stripped candidate is not carried
    on the result — `raw` is the verbatim scan. A consumer that needs to USE
    the scan text therefore has to strip it, and must not re-derive the shape
    to do it: Story 4.3's resolver calls this helper before searching free
    text. The envelope parse is the one exception, and it is why the helper is
    public rather than why it is needed twice — `classify()` runs
    `ecia.parse_fields` on the AIM-stripped candidate itself (Story 4.4), so
    `ecia_fields` is already correct for `']d1' + envelope` and nothing
    downstream re-parses `raw`."""

    @pytest.mark.unit
    def test_strip_aim_prefix_is_public(self):
        assert not scan_router.strip_aim_prefix.__name__.startswith('_')
        assert 'strip_aim_prefix' in dir(scan_router)

    @pytest.mark.unit
    @pytest.mark.parametrize('raw, expected', [
        (']d1RES 10K 0805', 'RES 10K 0805'),    # what 4.3 must search for
        (']d1' + ECIA_SHORT, ECIA_SHORT),       # what 4.4 must parse
        ('RES 10K 0805', 'RES 10K 0805'),       # no prefix: unchanged
        (']]d1x', ']]d1x'),                     # not the prefix shape: data
    ])
    def test_a_consumer_can_recover_the_classified_candidate(self, raw, expected):
        assert strip_aim_prefix(raw) == expected

    @pytest.mark.unit
    def test_raw_still_carries_the_prefix_so_nothing_is_lost(self):
        """The strip is a consumer's choice, not a silent edit: `classify` must
        never be the thing that discards a byte of the scan."""
        raw = ']d1RES 10K 0805'
        assert classify(raw, ai=AI, token=TOKEN).raw == raw

    @pytest.mark.unit
    def test_an_aim_prefix_and_a_transmitted_fnc1_arrive_together(self):
        """The canonical output of a GS1-128 scanner configured to emit both.
        The matrix covered each half alone; this is the combination that
        actually ships from such hardware."""
        assert classify(']C1\x1d' + INTERNAL_SCAN,
                        ai=AI, token=TOKEN).normalized_value == ID


class TestOverlongInternalPayloadFallsThrough:
    """`gs1.decode` returns None — foreign, not malformed — for a payload that
    opens with the marker but whose data field exceeds
    `MAX_DATA_FIELD_LENGTH`. So a corrupted or concatenated label this shop
    printed becomes an ordinary search rather than an error (no dead end), and
    that limit is an input to classification even though rule 1 never names
    it."""

    @pytest.mark.unit
    def test_a_data_field_over_the_grammar_limit_is_free_text(self):
        """Exactly one character over, not merely somewhere over: an id of
        `MAX_DATA_FIELD_LENGTH` characters is three past the limit once the
        token is counted, so the constant could have been raised by two
        without either test in this class noticing."""
        overlong = AI + TOKEN + 'A' * (MAX_DATA_FIELD_LENGTH - len(TOKEN) + 1)
        assert classify(overlong, ai=AI, token=TOKEN).kind is ScanKind.FREE_TEXT

    @pytest.mark.unit
    def test_the_longest_legal_data_field_still_classifies(self):
        """The boundary from the other side, so the limit cannot drift down
        without a test noticing."""
        longest = AI + TOKEN + 'A' * (MAX_DATA_FIELD_LENGTH - len(TOKEN))
        assert classify(longest, ai=AI, token=TOKEN).kind is ScanKind.INTERNAL


class TestEciaFieldsIsReadOnly:
    """The whole `__post_init__` contract: the read-only wrap and the two
    structural invariants the docstring asserts.

    `frozen=True` blocks rebinding the attribute, not mutation through it.
    `ecia_fields` is the only field that will ever hold a mutable object, so
    without the wrap the "pass it around without defensive copying" promise
    would be false for every distributor scan — and holding a mapping has two
    consequences (unhashable, unpicklable) that Story 4.5's serializer has to
    know about, so they are pinned here rather than discovered in a 500."""

    @pytest.mark.unit
    def test_a_populated_mapping_cannot_be_mutated_through_the_instance(self):
        source = {'P': '123', '1P': 'ABC'}
        c = ScanClassification(kind=ScanKind.ECIA, normalized_value=None,
                               ecia_fields=source, raw='x')
        with pytest.raises(TypeError):
            c.ecia_fields['P'] = 'MUTATED'

    @pytest.mark.unit
    def test_mutating_the_caller_s_original_dict_does_not_reach_the_instance(self):
        """The wrap copies, so a caller that keeps its dict cannot rewrite a
        classification it already handed on."""
        source = {'P': '123'}
        c = ScanClassification(kind=ScanKind.ECIA, normalized_value=None,
                               ecia_fields=source, raw='x')
        source['P'] = 'MUTATED'
        assert c.ecia_fields['P'] == '123'

    @pytest.mark.unit
    def test_contents_and_equality_survive_the_wrap(self):
        a = ScanClassification(kind=ScanKind.ECIA, normalized_value=None,
                               ecia_fields={'P': '123'}, raw='x')
        b = ScanClassification(kind=ScanKind.ECIA, normalized_value=None,
                               ecia_fields=a.ecia_fields, raw='x')
        assert dict(a.ecia_fields) == {'P': '123'}
        assert a == b

    @pytest.mark.unit
    def test_a_classification_without_ecia_fields_is_still_hashable(self):
        """The documented consequence, pinned in both directions: a
        classification with no `ecia_fields` hashes usably — equal values land
        in one set slot — and one carrying a mapping does not, whether it was
        hand-built or came straight out of `classify()`. A consumer keying a
        cache or a set on a classification therefore works for three kinds and
        raises on the fourth."""
        a = classify(GTIN13, ai=AI, token=TOKEN)
        b = classify(GTIN13, ai=AI, token=TOKEN)
        assert hash(a) == hash(b)
        assert len({a, b}) == 1
        with pytest.raises(TypeError):
            hash(ScanClassification(kind=ScanKind.ECIA, normalized_value=None,
                                    ecia_fields={'P': '123'}, raw='x'))
        with pytest.raises(TypeError):
            hash(classify(ECIA_FULL, ai=AI, token=TOKEN))

    @pytest.mark.unit
    @pytest.mark.parametrize('convert', [
        dataclasses.asdict,                     # the obvious route to Story 4.5's JSON
        copy.deepcopy,                          # and the obvious route to a defensive copy
    ])
    def test_the_wrap_breaks_asdict_and_deepcopy_for_a_populated_instance(self, convert):
        """The second consequence of holding a mapping, and the one that will
        actually bite: a `mappingproxy` cannot be pickled, so both of these
        raise. Story 4.5 must serialize field by field and convert
        `ecia_fields` with `dict(...)` rather than reaching for `asdict`.
        Pinned so that lands in a test run, not in a 500."""
        c = ScanClassification(kind=ScanKind.ECIA, normalized_value=None,
                               ecia_fields={'P': '123'}, raw='x')
        with pytest.raises(TypeError):
            convert(c)

    @pytest.mark.unit
    @pytest.mark.parametrize('convert', [dataclasses.asdict, copy.deepcopy])
    @pytest.mark.parametrize('raw', [
        INTERNAL_SCAN,                          # internal
        GTIN13,                                 # gtin
        'RES 10K 0805 1%',                      # free text
        '[)>\x1e06',                            # an envelope that degraded to free text
    ])
    def test_both_still_work_for_every_classification_without_fields(
            self, convert, raw):
        """The other side of it: `ecia_fields` is None on every kind but
        `ECIA`, so nothing but a real distributor label is affected."""
        assert convert(classify(raw, ai=AI, token=TOKEN)) is not None

    @pytest.mark.unit
    @pytest.mark.parametrize('convert', [dataclasses.asdict, copy.deepcopy])
    def test_both_now_break_for_a_classification_classify_itself_produces(
            self, convert):
        """The hazard the test above predicted for Story 4.5, now reachable
        from an ordinary scan rather than only from a hand-built instance: a
        `mappingproxy` cannot be pickled, so the obvious route from this frozen
        dataclass to JSON raises. A serializer must build its payload field by
        field and convert `ecia_fields` with `dict(...)`."""
        c = classify(ECIA_FULL, ai=AI, token=TOKEN)
        assert c.kind is ScanKind.ECIA
        with pytest.raises(TypeError):
            convert(c)

    @pytest.mark.unit
    def test_an_incoming_proxy_is_copied_rather_than_adopted(self):
        """A `MappingProxyType` is a *view*. Adopting one as-is would leave
        the dict behind it a live write channel into a frozen classification —
        the exact hole the wrap exists to close, reachable by a caller that
        wrapped its own dict first."""
        source = {'P': '123'}
        c = ScanClassification(kind=ScanKind.ECIA, normalized_value=None,
                               ecia_fields=MappingProxyType(source), raw='x')
        source['P'] = 'MUTATED'
        assert c.ecia_fields['P'] == '123'

    @pytest.mark.unit
    @pytest.mark.parametrize('fields', [
        ['ab', 'cd'],                           # a sequence of pairs: dict() would coerce it
        [('P', '123')],                         # ...including the well-meaning form
        'P123',                                 # a str: dict() raises an opaque ValueError
        42,                                     # an int: dict() raises 'not iterable'
        {'P', '1P'},                            # a set of keys with no values
    ])
    def test_a_non_mapping_is_rejected_by_name(self, fields):
        """`dict(fields)` accepts far more than the field's declared type, and
        silently turns `['ab', 'cd']` into `{'a': 'b', 'c': 'd'}`. The guard
        names the class and the field instead of leaking `dict()`'s message."""
        with pytest.raises(TypeError, match='ecia_fields'):
            ScanClassification(kind=ScanKind.ECIA, normalized_value=None,
                               ecia_fields=fields, raw='x')

    @pytest.mark.unit
    @pytest.mark.parametrize('kind, value', [
        (ScanKind.INTERNAL, ID),                # each kind's own legal
        (ScanKind.GTIN, GTIN13_KEY),            # normalized_value, so the
        (ScanKind.FREE_TEXT, None),             # ecia_fields rule is what fails
    ])
    def test_ecia_fields_cannot_be_attached_to_a_non_ecia_kind(self, kind, value):
        """The docstring says `None` for every non-ECIA kind, permanently.
        Enforced, so Stories 4.3/4.5/7/9 can rely on it rather than read it."""
        with pytest.raises(ValueError, match='ecia_fields'):
            ScanClassification(kind=kind, normalized_value=value,
                               ecia_fields={'P': '123'}, raw='x')

    @pytest.mark.unit
    @pytest.mark.parametrize('kind', [
        'gtin',                                 # the wire value, not the member
        'GTIN',                                 # the member name
        None,                                   # absent
        3,                                      # an index
    ])
    def test_kind_must_actually_be_a_scankind(self, kind):
        """Requiring all four fields stops a half-populated classification;
        this stops a self-contradictory one. `kind='gtin'` constructed cleanly
        before, and every `c.kind is ScanKind.GTIN` check downstream would
        have silently been False."""
        with pytest.raises(TypeError, match='kind'):
            ScanClassification(kind=kind, normalized_value=None,
                               ecia_fields=None, raw='x')

    @pytest.mark.unit
    @pytest.mark.parametrize('kind', [ScanKind.INTERNAL, ScanKind.GTIN])
    def test_a_kind_that_names_a_canonical_form_must_carry_one(self, kind):
        """The highest-consequence self-contradiction, and the one the
        cross-field guards previously left open: a `GTIN` with
        `normalized_value=None` constructed cleanly, and Story 4.3 would have
        keyed its lookup on `None`."""
        with pytest.raises(ValueError, match='normalized_value'):
            ScanClassification(kind=kind, normalized_value=None,
                               ecia_fields=None, raw='x')

    @pytest.mark.unit
    @pytest.mark.parametrize('kind', [ScanKind.ECIA, ScanKind.FREE_TEXT])
    def test_a_kind_that_normalizes_to_nothing_must_not_carry_a_value(self, kind):
        """The other half. Free text is searched via `raw`; an envelope's
        content lives in `ecia_fields`. A normalized_value on either invites a
        resolver to prefer a value the kind says does not exist."""
        with pytest.raises(ValueError, match='normalized_value'):
            ScanClassification(kind=kind, normalized_value='something',
                               ecia_fields=None, raw='x')

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        None,                                   # absent
        12345,                                  # an int
        b'x',                                   # bytes
    ])
    def test_raw_must_be_a_str(self, raw):
        """`classify()` rejects a non-str scan at its own door, but it is not
        the only route to this constructor — and a consumer calling
        `raw.startswith(']d1')` would meet an AttributeError in Story 4.3/4.4
        instead of a fault at the build."""
        with pytest.raises(TypeError, match='raw'):
            ScanClassification(kind=ScanKind.FREE_TEXT, normalized_value=None,
                               ecia_fields=None, raw=raw)

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [12348, b'0009', ['0009']])
    def test_normalized_value_must_be_a_str_or_none(self, value):
        with pytest.raises(TypeError, match='normalized_value'):
            ScanClassification(kind=ScanKind.GTIN, normalized_value=value,
                               ecia_fields=None, raw='x')

    @pytest.mark.unit
    @pytest.mark.parametrize('fields', [
        {1: 'x'},                               # non-str key -> invalid JSON object key
        {None: 'x'},                            # ...likewise
        {'P': b'123'},                          # non-str value
        {'P': ['a']},                           # a MUTABLE value: the read-only
                                                # promise would be false one level down
        {'P': {'nested': 'x'}},                 # ...same, one level further
    ])
    def test_ecia_fields_must_map_str_to_str(self, fields):
        """`Mapping[str, str]` is the declared type and the docstring names the
        seven legal keys, so checking only the container left the declared type
        unenforced — and a list value stayed writable through the proxy."""
        with pytest.raises(TypeError, match='ecia_fields'):
            ScanClassification(kind=ScanKind.ECIA, normalized_value=None,
                               ecia_fields=fields, raw='x')

    @pytest.mark.unit
    def test_a_type_fault_is_reported_as_a_type_fault_whatever_the_kind_says(self):
        """Error taxonomy: TypeError for a wrong type, ValueError for a wrong
        combination, type checked first. A non-mapping used to be reported as
        a *kind* problem, naming the one thing that was not wrong with it."""
        with pytest.raises(TypeError, match='ecia_fields'):
            ScanClassification(kind=ScanKind.GTIN, normalized_value=GTIN13_KEY,
                               ecia_fields=['ab', 'cd'], raw='x')

    @pytest.mark.unit
    @pytest.mark.parametrize('raw', [
        INTERNAL_SCAN,                          # internal
        ECIA_SHORT,                             # ecia
        GTIN13,                                 # gtin
        'RES 10K 0805 1%',                      # free text
        '',                                     # free text, degenerate
    ])
    def test_everything_classify_produces_satisfies_every_guard(self, raw):
        """The guards above are only worth having if the one producer cannot
        trip them — otherwise this pass would have turned a classifier that
        never raises on scan data (NFR8) into one that does."""
        c = classify(raw, ai=AI, token=TOKEN)
        assert dataclasses.replace(c) == c       # re-runs __post_init__
