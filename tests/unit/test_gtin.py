"""
Unit tests for the pure GTIN module (Story 2.2, app/utils/gtin.py).

Exhaustively exercises normalize_gtin / is_valid_gtin / compute_check_digit and
the pure rows of the story's I/O & edge-case matrix. This module is the single
source of truth for GTIN validity and normalization, so it is tested here in
isolation (no Flask/DB).
"""

import pytest

from app.utils.gtin import (
    InvalidGtinError,
    compute_check_digit,
    is_valid_gtin,
    normalize_gtin,
)


class TestComputeCheckDigit:

    @pytest.mark.unit
    @pytest.mark.parametrize('data13, expected', [
        ('0001234567890', 5),   # UPC-A 012345678905 padded
        ('0000000000000', 0),   # all zeros → 0
        ('0000000001234', 8),   # GTIN-8 00012348 padded
        ('0001234567892', 9),   # a distinct valid GTIN's data
    ])
    def test_matches_known_vectors(self, data13, expected):
        assert compute_check_digit(data13) == expected

    @pytest.mark.unit
    def test_check_digit_completes_the_valid_number(self):
        """Appending the computed digit yields a self-consistent GTIN-14."""
        data13 = '0001234567890'
        cd = compute_check_digit(data13)
        assert is_valid_gtin(data13 + str(cd))

    @pytest.mark.unit
    @pytest.mark.parametrize('bad', ['12', '00000000000000', 'abcdefghijklm', 1234567890123, None])
    def test_out_of_contract_input_raises_invalidgtin_not_bare_valueerror(self, bad):
        """The public surface only ever signals via InvalidGtinError."""
        with pytest.raises(InvalidGtinError):
            compute_check_digit(bad)


class TestNormalizeGtin:

    @pytest.mark.unit
    def test_upc_a_normalizes_to_14(self):
        assert normalize_gtin('012345678905') == '00012345678905'

    @pytest.mark.unit
    def test_gtin14_is_idempotent(self):
        assert normalize_gtin('00012345678905') == '00012345678905'

    @pytest.mark.unit
    def test_gtin8_normalizes_to_14(self):
        # 00012348 is a check-digit-valid GTIN-8 (check digit 8).
        assert normalize_gtin('00012348') == '00000000012348'

    @pytest.mark.unit
    def test_ean13_normalizes_to_14(self):
        # A valid 13-digit form left-pads to 14 with the same check digit.
        key = normalize_gtin('0012345678905')
        assert key == '00012345678905'
        assert len(key) == 14

    @pytest.mark.unit
    def test_all_four_forms_of_one_product_share_the_key(self):
        """GTIN-8/UPC-A/EAN-13/GTIN-14 of one number yield one 14-digit key.

        Uses a number small enough to be expressible in all four lengths (its
        14-digit key has six leading zeros), so slicing produces each form.
        """
        key = '00000000012348'   # check-digit-valid
        gtin8 = key[6:]          # 8 digits
        upc_a = key[2:]          # 12 digits
        ean13 = key[1:]          # 13 digits
        assert normalize_gtin(gtin8) == key
        assert normalize_gtin(upc_a) == key
        assert normalize_gtin(ean13) == key
        assert normalize_gtin(key) == key

    @pytest.mark.unit
    def test_strips_surrounding_whitespace(self):
        assert normalize_gtin('  012345678905  ') == '00012345678905'

    @pytest.mark.unit
    def test_bad_check_digit_raises_mentioning_check_digit(self):
        with pytest.raises(InvalidGtinError) as exc:
            normalize_gtin('012345678900')
        assert 'check digit' in str(exc.value).lower()

    @pytest.mark.unit
    @pytest.mark.parametrize('bad', ['ABC123', 'abcdefgh', '0123-5678905'])
    def test_non_digit_raises(self, bad):
        with pytest.raises(InvalidGtinError):
            normalize_gtin(bad)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad', [
        '1234567',          # 7 (too short)
        '123456789',        # 9
        '1234567890',       # 10
        '12345678901',      # 11
        '123456789012345',  # 15 (too long)
        '',                 # empty
    ])
    def test_wrong_length_raises(self, bad):
        with pytest.raises(InvalidGtinError):
            normalize_gtin(bad)

    @pytest.mark.unit
    def test_non_ascii_digits_rejected(self):
        # Arabic-Indic digits are .isdigit() True but not ASCII → rejected.
        with pytest.raises(InvalidGtinError):
            normalize_gtin('٠١٢٣٤٥٦٧')

    @pytest.mark.unit
    def test_error_is_a_valueerror_subclass(self):
        assert issubclass(InvalidGtinError, ValueError)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad', [None, 12345678905, b'012345678905', 12.0])
    def test_non_str_raises_invalidgtin_not_attributeerror(self, bad):
        """Non-str input fails as InvalidGtinError, never a raw AttributeError."""
        with pytest.raises(InvalidGtinError):
            normalize_gtin(bad)


class TestIsValidGtin:

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        '012345678905',
        '00012345678905',
        '00012348',
        '0012345678905',
    ])
    def test_true_for_valid(self, value):
        assert is_valid_gtin(value) is True

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        '012345678900',   # bad check digit
        'ABC123',         # non-digit
        '1234567',        # wrong length
        '',               # empty
        None,             # non-str — must not raise (contract: never raises)
        12345678905,      # int — must not raise
    ])
    def test_false_for_invalid_never_raises(self, value):
        assert is_valid_gtin(value) is False


class TestPureModuleHasNoAppImports:

    @pytest.mark.unit
    def test_module_imports_only_stdlib(self):
        """The pure module must not pull in Flask/SQLAlchemy/app packages."""
        import app.utils.gtin as gtin_mod

        source = gtin_mod.__file__
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
