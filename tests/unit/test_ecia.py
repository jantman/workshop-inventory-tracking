"""
Unit tests for the pure format-06 grammar module (Story 4.4, app/utils/ecia.py).

Exercises `is_envelope()` and `parse_fields()` against every parser row of the
story's I/O & edge-case matrix: FR38's seven MH10.8.2 data identifiers, AD-5's
graceful degradation, NFR8's "a scan never raises", and AD-4's purity rule.

Requires **no fixtures at all** — the same posture as tests/unit/test_gtin.py,
tests/unit/test_gs1.py and tests/unit/test_scan_router.py. That is not
incidental tidiness: AD-4 makes this module pure, so needing a Flask app, a
client or a database here would itself be the failure. Every test below builds
its input from literals and calls the function.

Where the boundary with `tests/unit/test_scan_router.py` falls: this file tests
the GRAMMAR (what is an envelope, what comes out of one), and that file tests
what `classify()` does with the answers — in particular the NFR8 degradation,
which is a routing decision rather than a parsing one. The two overlap
deliberately on the envelope-recognition vectors, because that behavior MOVED
here from the router at `035f226` and must be unchanged by the move.
"""

import ast
from pathlib import Path

import pytest

from app.utils import ecia
from app.utils.ecia import ECIA_FIELD_KEYS, is_envelope, parse_fields

# The repo's canonical ECIA vectors (tests/unit/test_gs1.py,
# test_scan_router.py, test_scan_routes.py).
ECIA_SHORT = '[)>\x1e06\x1dP123\x1e\x04'
ECIA_FULL = '[)>\x1e06\x1dP12345\x1d1PABC\x1dQ10\x1d\x1e\x04'


class TestEnvelopeRecognition:
    """The behavior that moved here from `scan_router._is_ecia_envelope` at
    `035f226`, vector for vector, so the move cannot have changed it.

    The header alone is judged, never the contents: what a valid header with an
    unreadable body ROUTES to is `classify()`'s decision (AD-5), and it needs
    this function to say "yes, an envelope" before it can make it.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        ECIA_SHORT,                            # the short repo vector
        ECIA_FULL,                             # the full P/1P/Q record vector
        '[)>\x1e06',                           # header with no body — a legal empty envelope
        '[)>\x1e06\x1e',                       # header closed immediately by RS
        '[)>\x1e06\x1dP123',                   # no trailing RS/EOT
        '[)>\x1e06\x1d!!!garbage!!!',          # a valid header, an unreadable body
    ])
    def test_a_well_formed_format_06_header_is_an_envelope(self, value):
        assert is_envelope(value) is True

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        '[)>06\x1dP123',                       # RS missing after the message-header characters
        '[)>\x1e05\x1dP123',                   # format 05, not 06
        '[)>\x1e06P123',                       # indicator not delimited — only resembles an envelope
        '[)>\x1e0612345',                      # ...same, with digits abutting the indicator
        '[)>\x1e0',                            # truncated indicator
        '[)>\x1e',                             # truncated header
        '[)>',                                 # message-header characters alone
        ' [)>\x1e06\x1dP123',                  # leading space: this module never trims
        '\x1d[)>\x1e06\x1dP123',               # a leading separator, likewise
        'PRE[)>\x1e06\x1dP123',                # header not at the front
    ])
    def test_a_damaged_or_foreign_header_is_not_an_envelope(self, value):
        """NFR8's other half: never a false envelope, so a damaged scan reaches
        the operator as free text rather than as a distributor label with
        nothing on it."""
        assert is_envelope(value) is False

    @pytest.mark.unit
    def test_an_aim_prefixed_envelope_is_not_one_until_the_prefix_is_stripped(self):
        """The AIM strip is `scan_router`'s, done once at the front before any
        rule runs, and this module is deliberately not a second place that
        knows the shape of a symbology identifier."""
        assert is_envelope(']d1' + ECIA_SHORT) is False
        assert is_envelope(ECIA_SHORT) is True


class TestFieldExtraction:
    """FR38: the seven AD-15 data identifiers, read out of the GS-delimited
    records exactly as the label carries them."""

    @pytest.mark.unit
    def test_the_canonical_vector_yields_its_three_identifiers(self):
        """The trailing GS and the `RS EOT` trailer are consumed, not read as
        records."""
        assert parse_fields(ECIA_FULL) == {'P': '12345', '1P': 'ABC', 'Q': '10'}

    @pytest.mark.unit
    def test_the_short_vector_yields_its_one_identifier(self):
        assert parse_fields(ECIA_SHORT) == {'P': '123'}

    @pytest.mark.unit
    def test_all_seven_ad15_identifiers_are_extracted(self):
        """Each with its own value, so no key is silently folded onto another
        (`P` vs `1P`, `K` vs `1K`, `9D` vs `10D` are three collisions waiting
        for a sloppy prefix match)."""
        value = ('[)>\x1e06\x1dP1\x1d1P2\x1dQ3\x1dK4\x1d1K5\x1d9D6\x1d10D7'
                 '\x1e\x04')
        assert parse_fields(value) == {
            'P': '1', '1P': '2', 'Q': '3', 'K': '4', '1K': '5',
            '9D': '6', '10D': '7',
        }

    @pytest.mark.unit
    def test_the_seven_keys_are_declared_once_and_are_exactly_ad15s(self):
        assert ECIA_FIELD_KEYS == ('P', '1P', 'Q', 'K', '1K', '9D', '10D')

    @pytest.mark.unit
    def test_unrecognized_identifiers_are_ignored_not_rejected(self):
        """FR38 says "at minimum", so a legal MH10.8.2 identifier this system
        has no field for (`1T` lot code, `4L` country of origin) is dropped
        silently. Rejecting the label would lose the fields it DOES carry."""
        value = '[)>\x1e06\x1d1PABC\x1d1TLOT9\x1d4LUS\x1e\x04'
        assert parse_fields(value) == {'1P': 'ABC'}

    @pytest.mark.unit
    def test_an_envelope_with_no_trailer_still_parses(self):
        """A wedge that drops the `RS EOT` is a transmission variant, not a
        different grammar — the last record simply runs to end-of-string."""
        assert parse_fields('[)>\x1e06\x1dP123') == {'P': '123'}

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        '[)>\x1e06\x1d1PRC0805-10K\x04',            # trailer arrived without its RS
        '[)>\x1e06\x1d1PRC0805-10K\x1e\x04',        # ...the well-formed message
        '[)>\x1e06\x1d1PRC0805-10K\x04\x1dQ10',     # ...and records behind the EOT
    ])
    def test_the_trailer_is_never_read_as_data(self, value):
        """The `RS EOT` trailer's two characters arrive as separate keystrokes
        from a wedge, so `<data> EOT` with no RS is a reachable shape. EOT ends
        the transmission by definition, so the body ends there too — otherwise
        the control character rides along INSIDE the part number, which no
        `.strip()` removes (`'\\x04'.isspace()` is False), so the exact lookup
        in `resolve_scan`'s ECIA arm misses a product stored character for
        character and Story 4.5 pre-fills a create form with the terminator.

        All three vectors yield the SAME fields, which is the point: the
        well-formed message is unaffected (its RS always comes first), and a
        record behind the terminator is dropped for the reason a record behind
        the RS is."""
        assert parse_fields(value) == {'1P': 'RC0805-10K'}

    @pytest.mark.unit
    def test_data_after_the_first_rs_is_not_this_messages_data(self):
        """Per ISO/IEC 15434 the RS after the data terminates format 06; what
        follows is another format's records or the trailer. Reading past it
        would let a second format's `1P` overwrite this one's."""
        assert parse_fields('[)>\x1e06\x1dP1\x1e07\x1d1PX\x1e\x04') == {'P': '1'}

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        '[)>\x1e06\x1dQ\x1e\x04',              # a recognized identifier, nothing behind it
        '[)>\x1e06\x1dQ',                      # ...at end-of-string
        '[)>\x1e06\x1d10D\x1e\x04',            # ...and the longest identifier
    ])
    def test_a_recognized_identifier_with_an_empty_value_is_omitted(self, value):
        """There is nothing to pre-fill a form with and nothing to look a
        product up by, so the key is absent rather than present-and-empty —
        which a consumer would have to special-case."""
        assert parse_fields(value) == {}

    @pytest.mark.unit
    def test_a_repeated_identifier_keeps_its_first_occurrence(self):
        """Deterministic, and it preserves the LEADING record of a label that
        repeats one."""
        assert parse_fields('[)>\x1e06\x1dP1\x1dP2\x1e\x04') == {'P': '1'}

    @pytest.mark.unit
    def test_an_empty_first_occurrence_does_not_shadow_a_later_real_one(self):
        """Where the empty-value rule and the first-wins rule meet. Separately
        each is obvious; jointly they could mean either "the empty one was the
        first, so nothing" or "the empty one was never recorded, so the later
        one stands". It is the second — an empty value never entered the map,
        so there is nothing for it to win against, and a label that prints a
        blank field before the real one still parses."""
        assert parse_fields('[)>\x1e06\x1d1P\x1d1PABC\x1e\x04') == {'1P': 'ABC'}

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        '[)>\x1e06\x1d١PABC\x1e\x04',     # ARABIC-INDIC DIGIT ONE before 'P'
        '[)>\x1e06\x1d１PABC\x1e\x04',     # FULLWIDTH DIGIT ONE
    ])
    def test_a_unicode_digit_is_not_part_of_an_identifier(self, value):
        """The identifier grammar this module documents is ASCII, so the regex
        says `[0-9]` and not `\\d` — which matches every Unicode decimal digit
        and would read '١P' as an identifier. Nothing recognized comes of
        either shape today, since no Unicode-digit identifier can equal one of
        the ASCII keys; the point is that the implementation means what the
        grammar says rather than agreeing with it by accident."""
        assert parse_fields(value) == {}

    @pytest.mark.unit
    @pytest.mark.parametrize('value, expected', [
        ('[)>\x1e06\x1d1P rc0805 \x1e\x04', ' rc0805 '),   # spaces both sides
        ('[)>\x1e06\x1d1PrC0805\x1e\x04', 'rC0805'),       # mixed case
        ('[)>\x1e06\x1d1P0010\x1e\x04', '0010'),           # leading zeros, still a str
        ('[)>\x1e06\x1d1P[)>\x1e\x04', '[)>'),             # header characters as data
    ])
    def test_values_are_kept_verbatim(self, value, expected):
        """No trimming, no case folding, no type coercion: the value is what
        the label printed, and interpreting it belongs to the consumer."""
        assert parse_fields(value) == {'1P': expected}

    @pytest.mark.unit
    def test_a_quantity_is_a_string_and_a_date_is_not_parsed(self):
        """`Q` is a count and `9D` is `YYWW`, but the frozen field type is
        `Mapping[str, str]` (AD-15), so both stay strings — including a
        quantity no integer parse would accept and a date no calendar has."""
        fields = parse_fields('[)>\x1e06\x1dQ1.5e3\x1d9D9999\x1e\x04')
        assert fields == {'Q': '1.5e3', '9D': '9999'}
        assert all(isinstance(v, str) for v in fields.values())

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        '[)>\x1e06\x1dp123\x1e\x04',           # the recognized identifier, lowercased
        '[)>\x1e06\x1d1p123\x1e\x04',          # ...and the two-character one
        '[)>\x1e06\x1d10d123\x1e\x04',
    ])
    def test_a_lowercase_identifier_is_not_an_identifier(self, value):
        """MH10.8.2 identifiers are uppercase. A lowercase leading letter is
        data that happens to start a record — folding it would invent a
        grammar the standard does not have."""
        assert parse_fields(value) == {}

    @pytest.mark.unit
    def test_a_leading_gs_after_the_header_is_not_an_empty_record(self):
        """The canonical vector opens with the GS that introduces the first
        record, and a label often closes with one too. Neither is a record, and
        an implementation that read them as such would trip over its own
        empty-element handling rather than skipping them."""
        assert parse_fields('[)>\x1e06\x1d\x1dP1\x1d\x1d\x1e\x04') == {'P': '1'}

    @pytest.mark.unit
    def test_an_element_that_does_not_open_with_an_identifier_is_ignored(self):
        """The neighbouring records still parse — one unreadable record does
        not cost the operator the rest of the label."""
        value = '[)>\x1e06\x1d!!!\x1dP1\x1d \x1d1PX\x1e\x04'
        assert parse_fields(value) == {'P': '1', '1P': 'X'}


class TestNotAnEnvelope:
    """Everything that is not a format-06 message parses to nothing — which is
    what `classify()` reads as "this is not rule 2's" (AD-5)."""

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        'RES 10K',                             # a human-typed part description
        '',                                    # empty
        '   ',                                 # blank
        '9506000134352',                       # a trade item number
        '[)>\x1e05\x1dP1',                     # a different format indicator
        ' ' + ECIA_SHORT,                      # padded: this module never trims
        '\x1d' + ECIA_SHORT,                   # ...including with a separator
        ']d1' + ECIA_SHORT,                    # AIM-prefixed: the router strips, not this
        'P12345',                              # records with no envelope around them
    ])
    def test_a_non_envelope_parses_to_an_empty_dict(self, value):
        assert parse_fields(value) == {}

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        '[)>\x1e06',                           # a legal but empty message
        '[)>\x1e06\x1e',                       # closed immediately by RS
        '[)>\x1e06\x1d!!!garbage!!!',          # a valid header, an unreadable body
        '[)>\x1e06\x1d1TLOT9\x1e\x04',         # ...and one carrying only foreign identifiers
    ])
    def test_an_envelope_carrying_nothing_recognized_parses_to_an_empty_dict(
            self, value):
        """The NFR8 degradation seam: `is_envelope` says yes and `parse_fields`
        says nothing, and the router turns that pair into `free_text` with the
        raw scan rather than into an `ecia` classification with no fields."""
        assert is_envelope(value) is True
        assert parse_fields(value) == {}


class TestNeverRaisesOnScanData:
    """NFR8: no value of a `str` is an exception from either function. Asserted
    as "a dict came back", not merely as "nothing was raised" — the second
    passes for a function that returns None."""

    HOSTILE = [
        '',                                          # empty
        ' ',                                         # blank
        '\x00' * 100,                                # a NUL run
        ''.join(chr(i) for i in range(32)),          # every C0 control character
        ''.join(chr(i) for i in range(32)) * 128,    # ...4096 characters of them
        '\x1d' * 50,                                 # a storm of GS separators
        '\x1e' * 50,                                 # ...and of RS
        '[)>' * 50,                                  # repeated message-header characters
        '\U0001f600' * 100,                          # astral-plane characters
        '\ud83d',                                    # a lone surrogate, as Python allows
        '[)>\x1e06\x1d' + '\x00' * 100,              # a real envelope full of NULs
        '[)>\x1e06\x1d' + '\ud800',                  # ...and one carrying a surrogate
        '[)>\x1e06\x1dP' + '9' * 4096,               # a 4 KB field value
        '[)>\x1e06' + '\x1d' * 4096,                 # 4 KB of empty records
        '[)>\x1e06\x1d1P' + '\U0001f600' * 100,      # emoji as a part number
    ]

    @pytest.mark.unit
    @pytest.mark.parametrize('value', HOSTILE)
    def test_parse_fields_always_returns_a_dict(self, value):
        result = parse_fields(value)
        assert isinstance(result, dict)
        assert all(isinstance(k, str) and isinstance(v, str)
                   for k, v in result.items())

    @pytest.mark.unit
    @pytest.mark.parametrize('value', HOSTILE)
    def test_is_envelope_always_returns_a_bool(self, value):
        assert isinstance(is_envelope(value), bool)

    @pytest.mark.unit
    @pytest.mark.parametrize('length', [1, 2, 3, 4, 5, 6, 7, 8])
    def test_every_truncation_of_a_real_envelope_parses_without_raising(
            self, length):
        """One character at a time through the header, which is where an
        index-based parser goes wrong."""
        assert isinstance(parse_fields(ECIA_FULL[:length]), dict)

    @pytest.mark.unit
    def test_a_four_kilobyte_adversarial_payload_is_answered(self):
        """A full `app.utils.scan_input.MAX_SCAN_LENGTH` worth of the nastiest
        characters a keyboard wedge could plausibly emit, in an order designed
        to look like an envelope without being one."""
        chunk = '[)>\x1e0\x1d\x1e\x04]\x001P'
        value = (chunk * (4096 // len(chunk) + 1))[:4096]
        assert len(value) == 4096
        assert parse_fields(value) == {}


class TestCallerFaults:
    """The only reachable exception from either function, and it is a property
    of the caller rather than of the scan."""

    NON_STRINGS = [
        b'[)>',                                # bytes — the transport decodes, we do not
        None,                                  # absent
        123,                                   # an int
        12.0,                                  # a float
        ['[)>'],                               # a list
        {'P': '1'},                            # the RESULT shape, passed back in
        object(),                              # anything else
    ]

    @pytest.mark.unit
    @pytest.mark.parametrize('value', NON_STRINGS)
    def test_parse_fields_rejects_a_non_str(self, value):
        with pytest.raises(TypeError):
            parse_fields(value)

    @pytest.mark.unit
    @pytest.mark.parametrize('value', NON_STRINGS)
    def test_is_envelope_rejects_a_non_str(self, value):
        with pytest.raises(TypeError):
            is_envelope(value)

    @pytest.mark.unit
    @pytest.mark.parametrize('func', [parse_fields, is_envelope])
    @pytest.mark.parametrize('value', NON_STRINGS)
    def test_the_message_names_the_type_and_not_the_value(self, func, value):
        """The type name is the diagnostic; the value is untrusted, unbounded
        and headed for a log. Bounding it safely is a solved problem living in
        `scan_router._bounded_repr`, and a second copy here would be one more
        thing to keep in agreement for the sake of a message.

        Asserted as an EXACT message rather than as "the repr is absent": for
        `None` the repr is a substring of the type name it is supposed to be
        distinguishable from, so the negative form would be vacuously true for
        one case and misleadingly strict for the rest."""
        with pytest.raises(TypeError) as exc:
            func(value)
        assert str(exc.value) == (
            f'value must be a str, got {type(value).__name__}.')

    @pytest.mark.unit
    def test_a_hostile_repr_cannot_replace_the_typeerror(self):
        """A value whose `__repr__` raises must still produce the documented
        TypeError — which it does by construction here, because the message
        never renders the value at all."""
        class Hostile:
            def __repr__(self):
                raise RuntimeError('no repr for you')

        with pytest.raises(TypeError):
            parse_fields(Hostile())

    @pytest.mark.unit
    def test_describing_a_bad_value_does_not_touch_it(self):
        """A module whose entire contract is purity must not run arbitrary
        `__getitem__` / `__repr__` code on what it was handed — the hazard
        `scan_router` documents against a `defaultdict`. Naming only the type
        sidesteps it entirely."""
        touched = []

        class Tattletale:
            def __getitem__(self, index):
                touched.append(index)
                return 'x'

            def __repr__(self):
                touched.append('repr')
                return 'x'

        with pytest.raises(TypeError):
            parse_fields(Tattletale())
        assert touched == []


class TestPurity:
    """AD-4 is a stated invariant no behavioral test can catch being violated:
    importing Flask, SQLAlchemy or `app.models` here would leave the whole
    suite green while the dependency direction quietly reversed. These read the
    source instead, the way `tests/unit/test_scan_router.py` pins the same rule
    for the router."""

    SOURCE_PATH = Path(ecia.__file__)

    def _tree(self):
        return ast.parse(self.SOURCE_PATH.read_text(encoding='utf-8'))

    @pytest.mark.unit
    def test_the_whole_import_set_is_exactly_the_declared_two(self):
        """An allow-list, not a deny-list of modules somebody thought of.
        Rejecting only Flask and SQLAlchemy leaves `os`, `pathlib`, `socket`,
        `sqlite3` and — fatally — `importlib` all green, and AD-4 says no
        config and no I/O rather than merely no Flask."""
        imported = set()
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or '')
        assert imported == {'re', 'typing'}, (
            f'app/utils/ecia.py imports {sorted(imported)}; adding to that set '
            f'is an AD-4 decision, not an incidental edit')

    @pytest.mark.unit
    @pytest.mark.parametrize('forbidden', [
        'app.models',                          # would make the leaf a branch
        'app.utils.scan_router',               # would close the dependency cycle
        'flask',
        'sqlalchemy',
    ])
    def test_the_forbidden_dependencies_are_absent_by_name(self, forbidden):
        """The allow-list above already implies this, but the four names worth
        stating are stated: the router imports THIS module, so an import back
        would be a cycle, and `app.models` must stay a leaf."""
        source = self.SOURCE_PATH.read_text(encoding='utf-8')
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name != forbidden for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or '') != forbidden

    @pytest.mark.unit
    def test_uses_no_relative_imports(self):
        """A relative import would slip past the check above."""
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.ImportFrom):
                assert node.level == 0

    @pytest.mark.unit
    def test_has_no_function_level_imports(self):
        """A deferred `import` inside a function body is how a pure module
        usually stops being one, and it would defeat the allow-list's purpose
        of showing the whole dependency set at the top of the file."""
        tree = self._tree()
        top_level = set(tree.body)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                assert node in top_level

    @pytest.mark.unit
    def test_source_calls_no_builtin_that_touches_the_outside_world(self):
        """`open()`, `input()`, `print()` and `__import__()` need no import at
        all, so the import checks cannot see them."""
        forbidden = {'open', 'input', 'print', 'eval', 'exec', '__import__'}
        called = {
            node.func.id for node in ast.walk(self._tree())
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not (called & forbidden), sorted(called & forbidden)

    @pytest.mark.unit
    def test_the_header_literal_lives_only_here(self):
        """The header moved out of `scan_router` rather than being copied: a
        second spelling of it is exactly the defect this repo keeps finding in
        itself (three copies of the scan trim rule, two LIKE escapers). Scanned
        over the whole app package, because the point is that no OTHER module
        holds it."""
        app_root = Path(ecia.__file__).resolve().parent.parent
        holders = sorted(
            path.relative_to(app_root).as_posix()
            for path in app_root.rglob('*.py')
            if '[)>' in path.read_text(encoding='utf-8'))
        assert holders == ['utils/ecia.py'], (
            f'the format-06 header literal appears in {holders}; AD-4 makes '
            f'this module its single source of truth')

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [ECIA_FULL, ECIA_SHORT, 'RES 10K'])
    def test_two_calls_return_equal_but_not_identical_dicts(self, value):
        """The caller owns the result. A cached or module-level dict would be
        shared by every classification of every scan, and mutating one — which
        `ScanClassification` cannot prevent before it copies — would rewrite
        the others."""
        first, second = parse_fields(value), parse_fields(value)
        assert first == second
        assert first is not second

    @pytest.mark.unit
    def test_the_returned_dict_is_plain_and_mutable(self):
        """`ScanClassification.__post_init__` copies and proxies it, so this
        module deliberately does NOT pre-wrap: a caller that is not building a
        classification gets an ordinary dict it can do as it likes with."""
        fields = parse_fields(ECIA_FULL)
        assert type(fields) is dict
        fields['P'] = 'MUTATED'
        assert parse_fields(ECIA_FULL)['P'] == '12345'

    @pytest.mark.unit
    def test_parsing_is_deterministic_and_needs_no_context(self):
        """No Flask application, no request, no database — this whole test
        module is fixture-free, so reaching this assertion is the proof."""
        assert parse_fields(ECIA_FULL) == parse_fields(ECIA_FULL)
        assert is_envelope(ECIA_FULL) is is_envelope(ECIA_FULL)
