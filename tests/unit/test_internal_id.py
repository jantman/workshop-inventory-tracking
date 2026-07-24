"""
Unit tests for the pure internal-id module (Story 2.4, app/utils/internal_id.py).

Exercises generate_internal_id / is_valid_internal_id and the pure rows of the
story's I/O & edge-case matrix. This module is the single source of truth for
the shape of an issued internal identifier, so it is tested here in isolation
(no Flask/DB).
"""

import pytest

from app.utils.internal_id import (
    ALPHABET,
    INTERNAL_ID_LENGTH,
    InvalidInternalIdError,
    generate_internal_id,
    is_valid_internal_id,
)


class TestGenerateInternalId:

    @pytest.mark.unit
    def test_default_length_is_ten(self):
        assert INTERNAL_ID_LENGTH == 10
        assert len(generate_internal_id()) == 10

    @pytest.mark.unit
    def test_all_characters_come_from_the_alphabet(self):
        """Every drawn character is a Crockford-32 symbol."""
        for _ in range(200):
            assert set(generate_internal_id()) <= set(ALPHABET)

    @pytest.mark.unit
    def test_alphabet_excludes_ambiguous_letters(self):
        """I/L/O/U are absent (OCR + human transcription ambiguity)."""
        assert len(ALPHABET) == 32
        assert len(set(ALPHABET)) == 32
        for excluded in ('I', 'L', 'O', 'U'):
            assert excluded not in ALPHABET
        # ...and nothing lower-case or non-alphanumeric crept in.
        assert ALPHABET == ALPHABET.upper()
        assert all(c.isalnum() for c in ALPHABET)

    @pytest.mark.unit
    def test_one_thousand_draws_are_all_distinct(self):
        """Collision resistance: 1000 candidates yield 1000 distinct values."""
        drawn = {generate_internal_id() for _ in range(1000)}
        assert len(drawn) == 1000

    @pytest.mark.unit
    def test_explicit_length_is_honored(self):
        assert len(generate_internal_id(length=1)) == 1
        assert len(generate_internal_id(length=24)) == 24

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_length', [0, -1, -10])
    def test_non_positive_length_rejected(self, bad_length):
        with pytest.raises(InvalidInternalIdError):
            generate_internal_id(length=bad_length)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_length', [None, '10', 10.0, True])
    def test_non_integer_length_raises_invalidinternalid_not_typeerror(self, bad_length):
        """The public surface only ever signals via InvalidInternalIdError."""
        with pytest.raises(InvalidInternalIdError):
            generate_internal_id(length=bad_length)

    @pytest.mark.unit
    def test_length_is_keyword_only(self):
        """A positional call is a TypeError — length is never passed by accident."""
        with pytest.raises(TypeError):
            generate_internal_id(8)

    @pytest.mark.unit
    def test_generated_values_validate(self):
        """The generator and the validator agree on the canonical shape."""
        for _ in range(100):
            assert is_valid_internal_id(generate_internal_id()) is True

    @pytest.mark.unit
    def test_error_is_a_valueerror_subclass(self):
        assert issubclass(InvalidInternalIdError, ValueError)


class TestIsValidInternalId:

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        'ABC1234567',
        '0000000000',
        'ZZZZZZZZZZ',
        '0123456789',
    ])
    def test_true_for_canonical_values(self, value):
        assert is_valid_internal_id(value) is True

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        'ABC',              # too short
        'ABC12345678',      # too long
        'abc1234567',       # lower-case
        'IIIIIIIIII',       # right length, excluded letter
        'LLLLLLLLLL',       # excluded letter
        'OOOOOOOOOO',       # excluded letter
        'UUUUUUUUUU',       # excluded letter
        'ABC123456-',       # punctuation
        'ABC 123456',       # embedded space
        '',                 # empty
        '  ABC1234567  ',   # untrimmed (never silently repaired)
    ])
    def test_false_for_malformed_values(self, value):
        assert is_valid_internal_id(value) is False

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [None, 1234567890, b'ABC1234567', 12.0, ['A']])
    def test_non_str_returns_false_never_raises(self, value):
        assert is_valid_internal_id(value) is False


class TestPureModuleHasNoAppImports:

    @pytest.mark.unit
    def test_module_imports_only_stdlib(self):
        """The pure module must not pull in Flask/SQLAlchemy/app packages."""
        import app.utils.internal_id as internal_id_mod

        source = internal_id_mod.__file__
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
