"""
Unit tests for the pure tag module (Story 3.3, app/utils/tag.py).

Exhaustively exercises normalize_tag, parse_tag_list and format_tag_list over
the pure rows of the story's I/O & edge-case matrix. This module is the single
source of truth for the canonical tag form and for splitting the operator's
comma-separated tag field (FR16, AD-4), so it is tested here in isolation (no
Flask/DB) — pure utils get exhaustive tests (NFR7).
"""

import pytest

from decimal import Decimal

from app.utils.tag import (
    format_tag_list,
    InvalidTagError,
    MAX_TAG_LENGTH,
    MAX_TAGS_PER_PRODUCT,
    normalize_tag,
    parse_tag_list,
    TAG_SEPARATOR,
)


# Every (input, expected) pair the matrix pins down for a single tag. Reused by
# the idempotence test so no case can be canonicalized without also being
# checked for stability under a second pass.
_MATRIX_CASES = [
    ('ssr', 'ssr'),                          # canonical passthrough
    ('  SSR  Relay ', 'ssr relay'),          # trim + collapse + lowercase
    ('SSR', 'ssr'),                          # case folded
    ('heat sink', 'heat sink'),              # intra-tag space preserved
    ('heat\t\nsink', 'heat sink'),           # tab/newline collapse to one space
    ('  spaced  out  tag  ', 'spaced out tag'),  # repeated internal runs
    ('dc-dc', 'dc-dc'),                      # hyphens preserved
    ('', None),                              # empty
    ('   ', None),                           # whitespace only
    ('\t\n', None),                          # other whitespace only
    (None, None),                            # absent value
]


class TestPublicConstants:

    @pytest.mark.unit
    def test_separator_is_a_single_comma(self):
        """The one separator the form field and parse_tag_list key off."""
        assert TAG_SEPARATOR == ','
        assert len(TAG_SEPARATOR) == 1

    @pytest.mark.unit
    def test_max_length_mirrors_the_column(self):
        """The limit is read off product_tags.tag, not asserted against a
        second copy of 64.

        The util is pure and cannot import the ORM, so the two numbers are kept
        in step by this test alone — which means comparing against the column
        itself. `assert MAX_TAG_LENGTH == 64` would still pass if the column
        were widened, and would be mirroring nothing. The import is local: this
        module otherwise tests the util in isolation.
        """
        from app.database import ProductTag

        column_length = ProductTag.__table__.c.tag.type.length
        assert column_length == 64, 'column changed; update the util'
        assert MAX_TAG_LENGTH == column_length

    @pytest.mark.unit
    def test_max_tags_per_product(self):
        """The per-product bound parse_tag_list enforces before any write.

        Unlike MAX_TAG_LENGTH this mirrors no column, so there is nothing to
        compare it against — but it IS a real bound, so the test proves it is
        enforced rather than restating the literal (which would pass whatever
        the number became).
        """
        assert isinstance(MAX_TAGS_PER_PRODUCT, int)
        assert MAX_TAGS_PER_PRODUCT > 0
        at_limit = ','.join(f't{n}' for n in range(MAX_TAGS_PER_PRODUCT))
        assert len(parse_tag_list(at_limit)) == MAX_TAGS_PER_PRODUCT
        with pytest.raises(InvalidTagError):
            parse_tag_list(at_limit + f',t{MAX_TAGS_PER_PRODUCT}')

    @pytest.mark.unit
    def test_error_is_a_value_error(self):
        """Module-local failure signal, never app.exceptions.ValidationError."""
        assert issubclass(InvalidTagError, ValueError)


class TestNormalizeTag:

    @pytest.mark.unit
    @pytest.mark.parametrize('value, expected', _MATRIX_CASES)
    def test_matrix(self, value, expected):
        """Each row of the story's normalization matrix (FR16, AD-4)."""
        assert normalize_tag(value) == expected

    @pytest.mark.unit
    @pytest.mark.parametrize('value, expected', _MATRIX_CASES)
    def test_is_idempotent(self, value, expected):
        """normalize(normalize(x)) == normalize(x) for every matrix case."""
        once = normalize_tag(value)
        assert normalize_tag(once) == once
        assert once == expected

    @pytest.mark.unit
    @pytest.mark.parametrize('value, expected', [
        ('Электроника', 'электроника'),      # str.lower() only
        ('Café', 'café'),                    # accents preserved, never folded
        ('DC-DC_Converter', 'dc-dc_converter'),   # underscores kept
        ('10%', '10%'),                      # LIKE metacharacters kept
        ("o'brien", "o'brien"),              # apostrophes kept
        ('a/b', 'a/b'),                      # the CATEGORY separator is fine
    ])
    def test_tag_contents_are_only_lowercased(self, value, expected):
        """Normalization never slugs, folds, or rewrites tag contents."""
        assert normalize_tag(value) == expected

    @pytest.mark.unit
    def test_blank_is_never_an_error(self):
        """Blank means 'no tag' — tags are optional (FR16)."""
        for blank in ('', '   ', '\t\n', None):
            assert normalize_tag(blank) is None

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        5,                  # int
        ['a'],              # list
        b'a',               # bytes
        Decimal('1'),       # Decimal
        ('a', 'b'),         # tuple
        object(),           # arbitrary object
    ])
    def test_non_string_input_rejected(self, value):
        """A non-str (other than None) is a caller-type fault, not form data."""
        with pytest.raises(InvalidTagError):
            normalize_tag(value)

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        'a,b',              # two tags handed to the single-tag entry point
        ',',                # bare separator
        'ssr,',             # trailing separator
        ',ssr',             # leading separator
    ])
    def test_separator_inside_a_tag_rejected(self, value):
        """A tag containing the separator could not survive the form's
        round-trip, so it is refused rather than silently split."""
        with pytest.raises(InvalidTagError):
            normalize_tag(value)

    @pytest.mark.unit
    def test_result_at_the_limit_is_accepted(self):
        """Exactly MAX_TAG_LENGTH characters still fits the column."""
        value = 'a' * MAX_TAG_LENGTH
        assert normalize_tag(value) == value

    @pytest.mark.unit
    def test_over_length_result_rejected_naming_the_limit(self):
        """A canonical value the column could not hold is rejected, and the
        message tells the operator the number they have to meet."""
        with pytest.raises(InvalidTagError) as exc_info:
            normalize_tag('a' * (MAX_TAG_LENGTH + 1))
        assert str(MAX_TAG_LENGTH) in str(exc_info.value)

    @pytest.mark.unit
    def test_length_is_measured_after_normalization(self):
        """Padding that normalizes away does not count toward the limit."""
        value = '  ' + 'a' * MAX_TAG_LENGTH + '  '
        assert normalize_tag(value) == 'a' * MAX_TAG_LENGTH


class TestParseTagList:

    @pytest.mark.unit
    def test_an_absurdly_long_field_is_refused_before_the_split(self):
        """The count check runs on the DE-DUPLICATED list, so 'a,a,a,...' would
        pass it however long it was — while still allocating one element per
        separator on the way there. This ceiling is measured on the raw string,
        before any splitting."""
        with pytest.raises(InvalidTagError) as exc_info:
            parse_tag_list('a,' * 100000)
        assert 'too long' in str(exc_info.value)

    @pytest.mark.unit
    @pytest.mark.parametrize('separator', [
        ',',        # no padding at all
        ', ',       # the form's own round-trip spelling
        ' , ',      # padded both sides — 3347 characters, over a (64+2)*50 bound
        '  ,\t ',   # the widest noise a person plausibly types
    ])
    def test_a_full_legal_list_is_still_accepted(self, separator):
        """The pre-split ceiling must not be able to refuse anything a legal
        list could contain: MAX_TAGS_PER_PRODUCT tags of MAX_TAG_LENGTH
        characters, however the operator spaces their commas.

        The ceiling is measured on the RAW string, before normalization trims
        anything, so a bound sized on the tags alone rejects a list that is
        exactly at the limit — telling the operator they exceeded a limit they
        are standing on.
        """
        longest = separator.join(
            (chr(ord('a') + n % 26) * MAX_TAG_LENGTH)
            for n in range(MAX_TAGS_PER_PRODUCT))
        assert len(parse_tag_list(longest)) == 26  # 26 distinct letters

    @pytest.mark.unit
    @pytest.mark.parametrize('value, expected', [
        (' SSR, rectifier ,, ssr ', ['ssr', 'rectifier']),  # THE matrix row
        ('ssr', ['ssr']),                          # a single tag
        ('ssr, rectifier', ['ssr', 'rectifier']),  # ordinary two
        ('rectifier, ssr', ['rectifier', 'ssr']),  # first-seen order, not sorted
        ('SSR,ssr,SsR', ['ssr']),                  # dedup on the canonical form
        ('  a  b , c  ', ['a b', 'c']),            # internal runs collapsed
        ('', []),                                  # empty
        (',', []),                                 # bare separator
        (',,,', []),                               # separators only
        ('  ,  ,  ', []),                          # padded separators
        (None, []),                                # absent value
    ])
    def test_matrix(self, value, expected):
        """Each row of the story's parsing matrix (FR16)."""
        assert parse_tag_list(value) == expected

    @pytest.mark.unit
    def test_is_idempotent_through_format(self):
        """parse(format(parse(x))) == parse(x) — the form's round trip."""
        once = parse_tag_list(' SSR, rectifier ,, ssr ')
        assert parse_tag_list(format_tag_list(once)) == once

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        5,                  # int
        ['a', 'b'],         # a list — the caller must join it themselves
        b'a,b',             # bytes
    ])
    def test_non_string_input_rejected(self, value):
        """A non-str (other than None) is a caller-type fault."""
        with pytest.raises(InvalidTagError):
            parse_tag_list(value)

    @pytest.mark.unit
    def test_an_over_length_tag_rejects_the_whole_list(self):
        """One unusable tag fails the parse — nothing is written, so the
        operator fixes the field rather than discovering a silent drop."""
        with pytest.raises(InvalidTagError):
            parse_tag_list('ssr, ' + 'a' * (MAX_TAG_LENGTH + 1))

    @pytest.mark.unit
    def test_at_the_tag_count_limit_is_accepted(self):
        """Exactly MAX_TAGS_PER_PRODUCT distinct tags is allowed."""
        value = ','.join(f't{i}' for i in range(MAX_TAGS_PER_PRODUCT))
        assert len(parse_tag_list(value)) == MAX_TAGS_PER_PRODUCT

    @pytest.mark.unit
    def test_too_many_tags_rejected_naming_the_limit(self):
        """51 distinct tags is refused before any write, and the message names
        the 50 the operator has to meet."""
        value = ','.join(f't{i}' for i in range(MAX_TAGS_PER_PRODUCT + 1))
        with pytest.raises(InvalidTagError) as exc_info:
            parse_tag_list(value)
        assert str(MAX_TAGS_PER_PRODUCT) in str(exc_info.value)

    @pytest.mark.unit
    def test_the_count_limit_is_measured_after_dedup(self):
        """Duplicates are one tag, so repeating one 100 times is not 100
        tags — the bound counts what would be STORED."""
        value = ','.join(['ssr'] * (MAX_TAGS_PER_PRODUCT + 50))
        assert parse_tag_list(value) == ['ssr']


class TestFormatTagList:

    @pytest.mark.unit
    @pytest.mark.parametrize('tags, expected', [
        (['ssr', 'rectifier'], 'ssr, rectifier'),  # THE matrix row
        (['ssr'], 'ssr'),                          # one tag, no separator
        ([], ''),                                  # none
        (None, ''),                                # absent
        (('a', 'b'), 'a, b'),                      # any iterable
    ])
    def test_matrix(self, tags, expected):
        """The inverse of parse_tag_list for the edit form's round trip."""
        assert format_tag_list(tags) == expected

    @pytest.mark.unit
    def test_round_trips_through_parse(self):
        """Formatting then parsing returns the same list, in order."""
        tags = ['rectifier', 'ssr', 'heat sink']
        assert parse_tag_list(format_tag_list(tags)) == tags


class TestPureModuleHasNoAppImports:

    @pytest.mark.unit
    def test_module_imports_only_stdlib(self):
        """The pure module must not pull in Flask/SQLAlchemy/app packages."""
        import app.utils.tag as tag_mod

        source = tag_mod.__file__
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
        # also occurs in prose where it is not an import at all.
        for line in text.splitlines():
            assert not line.lstrip().startswith('from .'), line
