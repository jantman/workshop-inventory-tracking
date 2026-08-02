"""
Unit tests for GTIN normalization and check-digit validation.

Covers app/utils/gtin.py -- the FR-009 property that equivalent forms of one
barcode resolve to a single product, and the FR-010 all-zero refusal.
"""

from app.utils.gtin import (
    ALL_ZERO_KEY,
    check_digit,
    is_all_zero,
    is_valid,
    normalize,
    normalize_and_validate,
)

# UPC-A and its EAN-13 form. These are the same trade item.
UPC_A = "012345678905"
EAN_13 = "0012345678905"
SHARED_KEY = "00012345678905"

VALID_GTIN_8 = "96385074"


class TestNormalize:
    """Left-zero-padding to fourteen digits is the whole of normalization"""

    def test_upc_a_and_ean_13_normalize_to_the_same_key(self):
        """FR-009: equivalent forms must collide, by construction"""
        assert normalize(UPC_A) == SHARED_KEY
        assert normalize(EAN_13) == SHARED_KEY

    def test_gtin_8_normalizes(self):
        assert normalize(VALID_GTIN_8) == "00000096385074"

    def test_gtin_14_passes_through(self):
        assert normalize(SHARED_KEY) == SHARED_KEY

    def test_surrounding_whitespace_is_stripped(self):
        assert normalize(f"  {UPC_A}\r\n") == SHARED_KEY

    def test_unaccepted_length_rejects(self):
        assert normalize("12345") is None
        assert normalize("123456789012345") is None

    def test_non_digits_reject(self):
        assert normalize("01234567890X") is None

    def test_empty_string_rejects(self):
        assert normalize("") is None

    def test_non_string_rejects_without_raising(self):
        assert normalize(None) is None


class TestCheckDigit:
    """The standard GS1 mod-10"""

    def test_upc_a_check_digit(self):
        assert check_digit(UPC_A[:-1]) == int(UPC_A[-1])

    def test_gtin_8_check_digit(self):
        assert check_digit(VALID_GTIN_8[:-1]) == int(VALID_GTIN_8[-1])

    def test_padding_does_not_change_the_check_digit(self):
        assert check_digit(SHARED_KEY[:-1]) == int(SHARED_KEY[-1])


class TestIsValid:
    """Bad check digits reject; the all-zero no-read refuses outright"""

    def test_valid_key(self):
        assert is_valid(SHARED_KEY) is True

    def test_bad_check_digit_rejects(self):
        assert is_valid("00012345678906") is False

    def test_all_zero_key_refuses(self):
        """The shape a wedge scanner emits on a no-read, not a trade item"""
        assert check_digit(ALL_ZERO_KEY[:-1]) == 0  # it would otherwise pass
        assert is_valid(ALL_ZERO_KEY) is False

    def test_wrong_length_rejects(self):
        assert is_valid(UPC_A) is False

    def test_non_digits_reject(self):
        assert is_valid("0001234567890X") is False

    def test_non_string_rejects_without_raising(self):
        assert is_valid(None) is False


class TestNormalizeAndValidate:
    """The classifier's entry point"""

    def test_both_equivalent_forms_yield_the_same_key(self):
        assert normalize_and_validate(UPC_A) == SHARED_KEY
        assert normalize_and_validate(EAN_13) == SHARED_KEY

    def test_bad_check_digit_yields_none(self):
        assert normalize_and_validate("012345678906") is None

    def test_all_zero_no_read_yields_none(self):
        """There is no override for this one -- FR-010"""
        assert normalize_and_validate("00000000") is None
        assert normalize_and_validate(ALL_ZERO_KEY) is None

    def test_free_text_yields_none(self):
        assert normalize_and_validate("B0ABCDEFGH") is None


class TestIsAllZero:
    """The override path needs to be able to ask"""

    def test_all_zero_forms(self):
        assert is_all_zero("00000000") is True
        assert is_all_zero(ALL_ZERO_KEY) is True

    def test_real_barcode_is_not_all_zero(self):
        assert is_all_zero(UPC_A) is False
