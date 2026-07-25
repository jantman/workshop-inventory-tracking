"""
Unit tests for the pure category module (Stories 3.1/3.2,
app/utils/category.py).

Exhaustively exercises normalize_category_path (Story 3.1) and the
segment-boundary helpers the rename is built on (Story 3.2) over the pure rows
of both stories' I/O & edge-case matrices. This module is the single source of
truth for the canonical category-path form and for segment-boundary containment
(FR13, FR17, AD-4), so it is tested here in isolation (no Flask/DB) — pure utils
get exhaustive tests (NFR7).
"""

import pytest

from decimal import Decimal

from app.utils.category import (
    ancestor_paths,
    CATEGORY_LIKE_ESCAPE_CHAR,
    CATEGORY_PATH_SEPARATOR,
    descendant_like_pattern,
    InvalidCategoryPathError,
    is_descendant_path,
    MAX_CATEGORY_PATH_LENGTH,
    normalize_category_path,
    rewrite_category_path,
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

    @pytest.mark.unit
    def test_like_escape_char_is_a_single_backslash(self):
        """The character every caller must also pass as `escape=` (FR17)."""
        assert CATEGORY_LIKE_ESCAPE_CHAR == '\\'
        assert len(CATEGORY_LIKE_ESCAPE_CHAR) == 1


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


class TestIsDescendantPath:
    """The one segment-boundary containment rule the rename, its collision
    check and Epic 8's facet all ask (Story 3.2, FR17, AD-4)."""

    @pytest.mark.unit
    @pytest.mark.parametrize('candidate, ancestor, expected', [
        ('a/b/c', 'a/b', True),                    # direct descendant
        ('a/b', 'a/b', True),                      # at-or-under is inclusive
        ('a/b/c/d', 'a', True),                    # arbitrary depth
        ('a', 'a/b', False),                       # ancestor is not a descendant
        ('a/z', 'a/b', False),                     # sibling
        ('thermal/heatgun-parts', 'thermal/heat', False),   # THE near miss
        ('ab', 'a', False),                        # string prefix, not a path one
        ('a/bc', 'a/b', False),                    # near miss one level down
        ('x/a/b', 'a/b', False),                   # containment is not a suffix
        ('a/b', 'b', False),                       # last segment is not the root
    ])
    def test_matrix(self, candidate, ancestor, expected):
        """Each containment row of the story's matrix (FR17)."""
        assert is_descendant_path(candidate, ancestor) is expected

    @pytest.mark.unit
    def test_boundary_is_the_separator_not_the_string(self):
        """Every one-character continuation of an ancestor is outside it,
        except the separator itself."""
        for suffix in ('x', '-', '_', ' ', '.', '%'):
            assert is_descendant_path(f'thermal/heat{suffix}', 'thermal/heat') is False
        assert is_descendant_path('thermal/heat/x', 'thermal/heat') is True

    @pytest.mark.unit
    @pytest.mark.parametrize('candidate, ancestor', [
        (None, 'a'),        # NULL candidate — callers filter these out
        ('a', None),        # missing ancestor
        (5, 'a'),           # non-string candidate
        ('a', 5),           # non-string ancestor
        ('', 'a'),          # blank candidate
        ('a', ''),          # blank ancestor: '' would "contain" everything
    ])
    def test_non_canonical_arguments_rejected(self, candidate, ancestor):
        """These take ALREADY-canonical paths; anything else is a caller fault."""
        with pytest.raises(InvalidCategoryPathError):
            is_descendant_path(candidate, ancestor)


class TestDescendantLikePattern:
    """The SQL half of the predicate. Canonical paths legitimately contain `_`
    and `%` (normalization never rewrites segment contents), so the wildcards
    must be escaped (Story 3.2, FR17)."""

    @pytest.mark.unit
    @pytest.mark.parametrize('ancestor, expected', [
        ('a/b', 'a/b/%'),                                    # nothing to escape
        ('electronics/power', 'electronics/power/%'),        # the AC's path
        ('50%', '50\\%/%'),                                  # literal percent
        ('power_supplies', 'power\\_supplies/%'),            # literal underscore
        ('a\\b', 'a\\\\b/%'),                                # literal backslash
        ('power_supplies/50%', 'power\\_supplies/50\\%/%'),  # the matrix row
    ])
    def test_matrix(self, ancestor, expected):
        """Each escaping row of the story's matrix (FR17)."""
        assert descendant_like_pattern(ancestor) == expected

    @pytest.mark.unit
    def test_the_matrix_pattern_is_22_characters(self):
        """The matrix pins the length, so an over- or under-escaped pattern
        (e.g. escaping the escape character twice) fails here too."""
        assert len(descendant_like_pattern('power_supplies/50%')) == 22

    @pytest.mark.unit
    def test_only_the_trailing_wildcard_is_unescaped(self):
        """The pattern's own `%` is the only live metacharacter left."""
        pattern = descendant_like_pattern('power_supplies/50%')
        assert pattern.endswith('/%')
        # Every other metacharacter is preceded by the escape character.
        body = pattern[:-2]
        for index, char in enumerate(body):
            if char in ('%', '_'):
                # index == 0 has no preceding character at all, and `body[-1]`
                # would silently wrap to the last one — which is exactly the
                # shape a broken escaper produces, so it is failed explicitly.
                assert index > 0, f'unescaped {char!r} at the start: {pattern}'
                assert body[index - 1] == CATEGORY_LIKE_ESCAPE_CHAR, pattern

    @pytest.mark.unit
    def test_a_leading_metacharacter_is_escaped_too(self):
        """The index-0 case the guard above exists for."""
        assert descendant_like_pattern('%wild') == '\\%wild/%'
        assert descendant_like_pattern('_lead') == '\\_lead/%'

    @pytest.mark.unit
    def test_the_node_itself_is_not_matched_by_the_pattern(self):
        """Strict descendants only — the caller ORs in an equality test."""
        assert descendant_like_pattern('a/b') != 'a/b'
        assert not descendant_like_pattern('a/b').startswith('a/b%')

    @pytest.mark.unit
    @pytest.mark.parametrize('ancestor', [None, 5, '', ['a']])
    def test_non_canonical_ancestor_rejected(self, ancestor):
        """A blank ancestor would yield '/%' — refused, never guessed at."""
        with pytest.raises(InvalidCategoryPathError):
            descendant_like_pattern(ancestor)


class TestRewriteCategoryPath:
    """The per-row half of the rename: the node becomes the new root and every
    descendant keeps its own suffix (Story 3.2, FR17)."""

    @pytest.mark.unit
    @pytest.mark.parametrize('path, old_root, new_root, expected', [
        ('a/b/c', 'a/b', 'x/y', 'x/y/c'),                    # descendant
        ('a/b', 'a/b', 'x/y', 'x/y'),                        # the node itself
        ('a/b/c/d', 'a', 'z', 'z/b/c/d'),                    # deep suffix kept
        ('electronics/power/dc-dc', 'electronics/power',
         'electronics/psu', 'electronics/psu/dc-dc'),        # the AC's case
        ('a/x', 'a', 'a/b', 'a/b/x'),                        # into its own subtree
        ('a/b/c', 'a/b', 'a', 'a/c'),                        # promote
    ])
    def test_matrix(self, path, old_root, new_root, expected):
        """Each rewrite row of the story's matrix (FR17)."""
        assert rewrite_category_path(path, old_root, new_root) == expected

    @pytest.mark.unit
    def test_the_suffix_is_carried_across_verbatim(self):
        """Segment contents are never re-normalized on the way through."""
        assert rewrite_category_path('a/50% off_stock', 'a', 'b') == 'b/50% off_stock'

    @pytest.mark.unit
    @pytest.mark.parametrize('path, old_root', [
        ('a/z', 'a/b'),                              # the matrix row: sibling
        ('thermal/heatgun-parts', 'thermal/heat'),   # near miss, not a descendant
        ('a', 'a/b'),                                # the ancestor, not a descendant
    ])
    def test_non_descendant_rejected(self, path, old_root):
        """Rewriting a path outside the subtree is a caller fault: the caller
        selects the subtree before rewriting it."""
        with pytest.raises(InvalidCategoryPathError):
            rewrite_category_path(path, old_root, 'x')

    @pytest.mark.unit
    def test_result_at_the_limit_is_accepted(self):
        """Exactly MAX_CATEGORY_PATH_LENGTH characters still fits the column."""
        new_root = 'b' * (MAX_CATEGORY_PATH_LENGTH - 2)
        assert rewrite_category_path('a/c', 'a', new_root) == f'{new_root}/c'

    @pytest.mark.unit
    def test_over_length_result_rejected(self):
        """A rewritten descendant the column could not hold is rejected —
        which is what lets the service refuse the rename before writing."""
        new_root = 'b' * (MAX_CATEGORY_PATH_LENGTH - 1)
        with pytest.raises(InvalidCategoryPathError):
            rewrite_category_path('a/c', 'a', new_root)

    @pytest.mark.unit
    @pytest.mark.parametrize('path, old_root, new_root', [
        (None, 'a', 'b'),       # NULL path
        ('a/b', None, 'b'),     # missing source root
        ('a/b', 'a', None),     # missing destination root
        ('a/b', 'a', ''),       # blank destination
        ('a/b', 'a', 5),        # non-string destination
    ])
    def test_non_canonical_arguments_rejected(self, path, old_root, new_root):
        with pytest.raises(InvalidCategoryPathError):
            rewrite_category_path(path, old_root, new_root)


class TestAncestorPaths:
    """The tree is stored only as the paths products carry, so its interior
    nodes have to be recovered from them (Story 3.2, FR17)."""

    @pytest.mark.unit
    @pytest.mark.parametrize('path, expected', [
        ('a/b/c', ['a', 'a/b']),                                  # every level
        ('a/b', ['a']),                                           # one ancestor
        ('a', []),                                                # root: none
        ('electronics/power/dc-dc', ['electronics',
                                     'electronics/power']),       # the AC's tree
        ('power supplies/dc dc', ['power supplies']),             # spaces kept
        ('a/b/c/d/e', ['a', 'a/b', 'a/b/c', 'a/b/c/d']),          # deep, ordered
    ])
    def test_matrix(self, path, expected):
        """Proper ancestors only, shallowest first (FR17)."""
        assert ancestor_paths(path) == expected

    @pytest.mark.unit
    def test_the_path_itself_is_never_included(self):
        """Callers add the assigned paths themselves; a duplicate row would be
        a second Rename link for the same node."""
        assert 'a/b/c' not in ancestor_paths('a/b/c')

    @pytest.mark.unit
    def test_every_ancestor_contains_the_path(self):
        """The two halves of the predicate agree: an ancestor of a path is one
        the path is a descendant of."""
        path = 'electronics/power/dc-dc'
        assert all(is_descendant_path(path, a) for a in ancestor_paths(path))

    @pytest.mark.unit
    @pytest.mark.parametrize('path', [None, 5, '', ['a']])
    def test_non_canonical_path_rejected(self, path):
        """Same caller-fault contract as the other three helpers."""
        with pytest.raises(InvalidCategoryPathError):
            ancestor_paths(path)


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
