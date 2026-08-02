"""
Unit tests for internal product code generation and validation.

Covers app/utils/internal_id.py -- the FR-015 "codes this system printed are
distinguishable from foreign codes" property.
"""

import pytest

from app.utils.internal_id import (
    ALPHABET,
    generate_internal_id,
    is_internal_id,
    normalize_internal_id,
)


class TestAlphabet:
    """The alphabet is what makes a hand-retyped worn label work"""

    def test_alphabet_has_32_characters(self):
        assert len(ALPHABET) == 32

    def test_alphabet_excludes_ambiguous_letters(self):
        """I, L, O and U are the characters a person misreads"""
        for excluded in "ILOU":
            assert excluded not in ALPHABET

    def test_alphabet_has_no_duplicates(self):
        assert len(set(ALPHABET)) == len(ALPHABET)


class TestGenerate:
    """Generated codes must always validate"""

    def test_generated_value_validates(self):
        assert is_internal_id(generate_internal_id())

    def test_generated_value_has_expected_shape(self):
        code = generate_internal_id()
        assert code.startswith("WIT")
        assert len(code) == 13

    def test_generated_values_differ(self):
        """Not a randomness test -- a guard against a constant slipping in"""
        codes = {generate_internal_id() for _ in range(50)}
        assert len(codes) == 50

    def test_generated_body_uses_only_the_alphabet(self):
        for _ in range(50):
            body = generate_internal_id()[3:]
            assert set(body) <= set(ALPHABET)


class TestIsInternalId:
    """Malformed values must reject"""

    def test_valid_code(self):
        assert is_internal_id("WIT0123456789") is True

    def test_surrounding_whitespace_is_stripped(self):
        """A wedge scanner may append a terminator"""
        assert is_internal_id("  WIT0123456789\r\n") is True

    def test_wrong_prefix_rejects(self):
        assert is_internal_id("XYZ0123456789") is False

    def test_ja_id_is_not_an_internal_code(self):
        assert is_internal_id("JA000123") is False

    def test_too_short_rejects(self):
        assert is_internal_id("WIT012345678") is False

    def test_too_long_rejects(self):
        assert is_internal_id("WIT01234567890") is False

    def test_lowercase_rejects(self):
        assert is_internal_id("wit0123456789") is False

    def test_excluded_letters_reject(self):
        for excluded in "ILOU":
            assert is_internal_id(f"WIT{excluded}123456789") is False

    def test_empty_string_rejects(self):
        assert is_internal_id("") is False

    def test_non_string_rejects_without_raising(self):
        assert is_internal_id(None) is False
        assert is_internal_id(12345) is False

    def test_internal_whitespace_rejects(self):
        assert is_internal_id("WIT 0123456789") is False


class TestNormalize:
    """Normalization is strip-and-verify, nothing more"""

    def test_strips_whitespace(self):
        assert normalize_internal_id(" WIT0123456789 ") == "WIT0123456789"

    def test_rejects_invalid_value(self):
        with pytest.raises(ValueError):
            normalize_internal_id("not-a-code")
