"""
Unit tests for category path canonicalization and subtree matching.

Covers app/utils/category.py -- FR-030's arbitrary-depth inline categories and the
segment-boundary predicate FR-032's category filter depends on.
"""

import pytest

from app.utils.category import (
    canonical,
    descendant_like_pattern,
    is_descendant,
    segments,
)


class TestCanonical:
    """Normalization lowercases and shortens. It never slugs."""

    def test_lowercases(self):
        assert canonical("Power Supplies") == "power supplies"

    def test_preserves_spaces_and_does_not_slug(self):
        """The operator's own vocabulary is the taxonomy"""
        assert canonical("Power Supplies/DC DC") == "power supplies/dc dc"

    def test_strips_each_segment(self):
        assert canonical(" electronics / passives ") == "electronics/passives"

    def test_drops_empty_segments(self):
        assert canonical("electronics//passives") == "electronics/passives"

    def test_drops_leading_and_trailing_separators(self):
        assert canonical("/electronics/passives/") == "electronics/passives"

    def test_arbitrary_depth(self):
        assert canonical("A/B/C/D/E") == "a/b/c/d/e"

    def test_already_canonical_is_unchanged(self):
        assert canonical("electronics/passives") == "electronics/passives"

    def test_does_not_fold_unicode(self):
        assert canonical("Résistances") == "résistances"


class TestCanonicalBlankInputs:
    """Blank means 'no category', which is not an error"""

    def test_none(self):
        assert canonical(None) is None

    def test_empty_string(self):
        assert canonical("") is None

    def test_whitespace_only(self):
        assert canonical("   ") is None

    def test_bare_separator(self):
        assert canonical("/") is None

    def test_only_separators(self):
        assert canonical("///") is None

    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError):
            canonical(42)


class TestSegments:
    def test_splits_canonical_path(self):
        assert segments("Electronics/Passives/Resistors") == [
            "electronics",
            "passives",
            "resistors",
        ]

    def test_no_category_yields_empty_list(self):
        assert segments(None) == []
        assert segments("  ") == []


class TestIsDescendant:
    """The boundary is the separator, not the character count"""

    def test_a_category_is_its_own_descendant(self):
        assert is_descendant("electronics", "electronics") is True

    def test_child_matches(self):
        assert is_descendant("electronics/passives", "electronics") is True

    def test_grandchild_matches(self):
        assert is_descendant("electronics/passives/resistors", "electronics") is True

    def test_sibling_with_a_shared_prefix_does_not_match(self):
        """Filtering 'foo' must not pull in 'foo-bar'"""
        assert is_descendant("foo-bar", "foo") is False

    def test_shared_prefix_without_a_separator_does_not_match(self):
        assert is_descendant("electronicsx", "electronics") is False

    def test_parent_is_not_a_descendant_of_its_child(self):
        assert is_descendant("electronics", "electronics/passives") is False

    def test_unrelated_path_does_not_match(self):
        assert is_descendant("hardware/fasteners", "electronics") is False

    def test_inputs_are_canonicalized_before_comparison(self):
        assert is_descendant("Electronics/Passives", " electronics ") is True

    def test_uncategorized_candidate_is_not_a_descendant(self):
        assert is_descendant(None, "electronics") is False

    def test_filtering_on_no_category_selects_everything(self):
        assert is_descendant("electronics", None) is True
        assert is_descendant(None, None) is True


class TestDescendantLikePattern:
    """The SQL half of the same predicate"""

    def test_appends_the_boundary_wildcard(self):
        assert descendant_like_pattern("electronics") == "electronics/%"

    def test_escapes_like_wildcards_in_a_real_category_name(self):
        """A category literally named '100%' must not match everything"""
        assert descendant_like_pattern("100%") == "100\\%/%"

    def test_escapes_underscore(self):
        assert descendant_like_pattern("a_b") == "a\\_b/%"

    def test_escapes_backslash(self):
        assert descendant_like_pattern("a\\b") == "a\\\\b/%"
