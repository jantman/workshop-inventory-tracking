"""
Unit tests for the pure category module (Story 3.1, app/utils/category.py).

Exhaustively exercises normalize_category_path over the pure rows of the
story's I/O & edge-case matrix. This module is the single source of truth for
the canonical category-path form (FR13, AD-4), so it is tested here in
isolation (no Flask/DB) — pure utils get exhaustive tests (NFR7).
"""

import pytest

from decimal import Decimal

from app.utils.category import (
    CATEGORY_PATH_SEPARATOR,
    InvalidCategoryPathError,
    MAX_CATEGORY_PATH_LENGTH,
    normalize_category_path,
)


# Every (input, expected) pair the matrix pins down. Reused by the idempotence
# test so no case can be canonicalized without also being checked for
# stability under a second pass.
_MATRIX_CASES = [
    ('electronics/power/dc-dc-converters',
     'electronics/power/dc-dc-converters'),      # canonical passthrough
    ('  Electronics/Power  ', 'electronics/power'),      # case + outer space
    ('/electronics//power/', 'electronics/power'),       # slash noise
    ('electronics///power', 'electronics/power'),        # repeated separators
    ('Electronics / Power / DC-DC',
     'electronics/power/dc-dc'),                         # space around slashes
    ('a\t/\nb', 'a/b'),                                  # tab/newline padding
    ('Power Supplies/DC DC', 'power supplies/dc dc'),    # intra-segment spaces
    ('thermal/heat-sinks', 'thermal/heat-sinks'),        # hyphens preserved
    ('a', 'a'),                                          # single segment
    ('', None),                                          # empty
    ('   ', None),                                       # whitespace only
    ('/', None),                                         # bare separator
    ('///', None),                                       # separators only
    (' / / ', None),                                     # padded separators
    (None, None),                                        # absent value
]


class TestPublicConstants:

    @pytest.mark.unit
    def test_separator_is_a_single_forward_slash(self):
        """The materialized path separator the whole epic keys off (FR13)."""
        assert CATEGORY_PATH_SEPARATOR == '/'

    @pytest.mark.unit
    def test_max_length_mirrors_the_column(self):
        """The limit is read off products.category_path, not asserted against
        a second copy of 512.

        The util is pure and cannot import the ORM, so the two numbers are
        kept in step by this test alone — which means comparing against the
        column itself. `assert MAX_CATEGORY_PATH_LENGTH == 512` would still
        pass if the column were widened, and would be mirroring nothing. The
        import is local: this module otherwise tests the util in isolation.
        """
        from app.database import Product

        column_length = Product.__table__.c.category_path.type.length
        assert column_length == 512, 'column changed; update the util'
        assert MAX_CATEGORY_PATH_LENGTH == column_length

    @pytest.mark.unit
    def test_error_is_a_value_error(self):
        """Module-local failure signal, never app.exceptions.ValidationError."""
        assert issubclass(InvalidCategoryPathError, ValueError)


class TestNormalizeCategoryPath:

    @pytest.mark.unit
    @pytest.mark.parametrize('value, expected', _MATRIX_CASES)
    def test_matrix(self, value, expected):
        """Each row of the story's normalization matrix (FR13, AD-4)."""
        assert normalize_category_path(value) == expected

    @pytest.mark.unit
    @pytest.mark.parametrize('value, expected', _MATRIX_CASES)
    def test_is_idempotent(self, value, expected):
        """normalize(normalize(x)) == normalize(x) for every matrix case."""
        once = normalize_category_path(value)
        assert normalize_category_path(once) == once
        assert once == expected

    @pytest.mark.unit
    @pytest.mark.parametrize('value, expected', [
        ('Электроника/Питание', 'электроника/питание'),   # str.lower() only
        ('Ünïcode/Ségments', 'ünïcode/ségments'),         # accents preserved
        ('a/B/c', 'a/b/c'),                               # mixed case segments
        ('DC-DC_Converters', 'dc-dc_converters'),         # underscores kept
        ('10%/50_off', '10%/50_off'),                     # LIKE metacharacters
        ("o'brien/parts", "o'brien/parts"),               # apostrophes kept
    ])
    def test_segment_contents_are_only_lowercased(self, value, expected):
        """Normalization never slugs, folds, or rewrites segment contents."""
        assert normalize_category_path(value) == expected

    @pytest.mark.unit
    def test_blank_is_never_an_error(self):
        """Blank means 'no category' — the field is optional (FR13)."""
        for blank in ('', '   ', '/', '///', ' / / ', '\t\n', None):
            assert normalize_category_path(blank) is None

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
        with pytest.raises(InvalidCategoryPathError):
            normalize_category_path(value)

    @pytest.mark.unit
    def test_result_at_the_limit_is_accepted(self):
        """Exactly MAX_CATEGORY_PATH_LENGTH characters still fits the column."""
        value = 'a' * MAX_CATEGORY_PATH_LENGTH
        assert normalize_category_path(value) == value

    @pytest.mark.unit
    def test_over_length_result_rejected(self):
        """A normalized value the column could not hold is rejected."""
        with pytest.raises(InvalidCategoryPathError):
            normalize_category_path('a' * (MAX_CATEGORY_PATH_LENGTH + 1))

    @pytest.mark.unit
    def test_length_is_measured_after_normalization(self):
        """Slash noise that normalizes away does not count toward the limit."""
        value = '/' * 50 + 'a' * MAX_CATEGORY_PATH_LENGTH + '/' * 50
        assert normalize_category_path(value) == 'a' * MAX_CATEGORY_PATH_LENGTH

    @pytest.mark.unit
    def test_deep_paths_are_supported(self):
        """Materialized paths are of arbitrary depth."""
        deep = '/'.join(f'Level{i}' for i in range(20))
        assert normalize_category_path(deep) == '/'.join(
            f'level{i}' for i in range(20))


class TestPureModuleHasNoAppImports:

    @pytest.mark.unit
    def test_module_imports_only_stdlib(self):
        """The pure module must not pull in Flask/SQLAlchemy/app packages."""
        import app.utils.category as category_mod

        source = category_mod.__file__
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
