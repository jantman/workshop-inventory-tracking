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
    rename_descendant,
    segments,
    would_nest_within,
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


class TestRenameDescendant:
    """Rewriting a prefix carries the subtree's shape with it"""

    def test_the_renamed_level_itself(self):
        assert rename_descendant(
            "elctronics", "elctronics", "electronics"
        ) == "electronics"

    def test_a_child(self):
        assert rename_descendant(
            "elctronics/passives", "elctronics", "electronics"
        ) == "electronics/passives"

    def test_a_grandchild(self):
        assert rename_descendant(
            "elctronics/passives/resistors", "elctronics", "electronics"
        ) == "electronics/passives/resistors"

    def test_the_boundary_is_the_separator_not_the_character_count(self):
        """A category that merely starts with the same letters is a different one"""
        assert rename_descendant(
            "elctronics-surplus", "elctronics", "electronics"
        ) == "elctronics-surplus"

    def test_a_path_outside_the_subtree_is_unchanged(self):
        assert rename_descendant(
            "hardware/fasteners", "elctronics", "electronics"
        ) == "hardware/fasteners"

    def test_a_parent_of_the_renamed_level_is_unchanged(self):
        assert rename_descendant("power", "power/dc dc", "power/converters") == "power"

    def test_renaming_a_deeper_path_touches_only_that_subtree(self):
        assert rename_descendant(
            "power/dc dc/buck", "power/dc dc", "power/converters"
        ) == "power/converters/buck"

    def test_rename_can_change_depth(self):
        assert rename_descendant(
            "a/b", "a", "x/y"
        ) == "x/y/b"

    def test_both_operands_are_canonicalized(self):
        assert rename_descendant(
            " Elctronics / Passives ", "ELCTRONICS", " Electronics "
        ) == "electronics/passives"

    def test_blank_operands_leave_the_path_alone(self):
        assert rename_descendant("electronics", "", "hardware") == "electronics"
        assert rename_descendant("electronics", "electronics", "") == "electronics"

    def test_uncategorized_stays_uncategorized(self):
        assert rename_descendant(None, "electronics", "hardware") is None


class TestWouldNestWithin:
    """A category cannot be moved inside itself"""

    def test_direct_child_of_the_source_nests(self):
        assert would_nest_within("power/supplies", "power") is True

    def test_deeper_descendant_nests(self):
        assert would_nest_within("power/supplies/dc", "power") is True

    def test_the_same_path_counts_as_nesting(self):
        assert would_nest_within("power", "power") is True

    def test_an_unrelated_target_does_not_nest(self):
        assert would_nest_within("hardware", "power") is False

    def test_a_shared_prefix_without_a_separator_does_not_nest(self):
        assert would_nest_within("power-supplies", "power") is False

    def test_the_source_moving_under_its_own_parent_does_not_nest(self):
        assert would_nest_within("power", "power/supplies") is False

    def test_operands_are_canonicalized(self):
        assert would_nest_within(" Power / Supplies ", "POWER") is True

    def test_blank_operands_do_not_nest(self):
        assert would_nest_within(None, "power") is False
        assert would_nest_within("power/supplies", None) is False
