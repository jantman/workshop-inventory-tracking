"""
Unit tests for scan classification.

Covers app/utils/scan_router.py -- FR-014 routing, the rule-1-outranks-rule-3
precedence, and the guarantee that classify() never raises on a str (SC-008: a
scan must never dead-end, and an exception is a dead end).
"""

import pytest

from app.models import ScanKind
from app.utils.ecia import EOT, GS, RS
from app.utils.scan_router import classify

VALID_INTERNAL = "WIT0123456789"
VALID_UPC_A = "012345678905"
VALID_GTIN_KEY = "00012345678905"

# A DigiKey-shaped format-06 envelope.
ENVELOPE = "[)>" + RS + "06" + GS + "1PLM358N" + GS + "Q100" + RS + EOT


class TestInternalCode:
    """Rule 1"""

    def test_internal_code_classifies_internal(self):
        result = classify(VALID_INTERNAL)
        assert result.kind is ScanKind.INTERNAL
        assert result.value == VALID_INTERNAL

    def test_wedge_terminator_is_stripped_from_the_value(self):
        result = classify(f"{VALID_INTERNAL}\r\n")
        assert result.kind is ScanKind.INTERNAL
        assert result.value == VALID_INTERNAL

    def test_raw_is_always_the_scan_as_captured(self):
        result = classify(f"  {VALID_INTERNAL}  ")
        assert result.raw == f"  {VALID_INTERNAL}  "

    def test_lookalike_with_an_excluded_letter_is_not_internal(self):
        assert classify("WITI123456789").kind is ScanKind.FREE_TEXT


class TestGtin:
    """Rule 3"""

    def test_upc_a_classifies_gtin_with_the_normalized_key(self):
        result = classify(VALID_UPC_A)
        assert result.kind is ScanKind.GTIN
        assert result.value == VALID_GTIN_KEY

    def test_ean_13_form_yields_the_same_key(self):
        assert classify("0012345678905").value == VALID_GTIN_KEY

    def test_bad_check_digit_falls_through_to_free_text(self):
        result = classify("012345678906")
        assert result.kind is ScanKind.FREE_TEXT
        assert result.value == "012345678906"

    def test_all_zero_no_read_falls_through_to_free_text(self):
        assert classify("00000000").kind is ScanKind.FREE_TEXT


class TestEcia:
    """Rule 2"""

    def test_a_format_06_envelope_classifies_ecia(self):
        result = classify(ENVELOPE)
        assert result.kind is ScanKind.ECIA
        assert result.ecia_fields == {'1P': 'LM358N', 'Q': '100'}

    def test_the_value_is_the_manufacturer_part_number(self):
        assert classify(ENVELOPE).value == 'LM358N'

    def test_the_value_falls_back_to_the_distributor_part_number(self):
        scan = "[)>" + RS + "06" + GS + "P296-1234-5-ND" + RS + EOT
        result = classify(scan)
        assert result.kind is ScanKind.ECIA
        assert result.value == '296-1234-5-ND'

    def test_an_envelope_carrying_nothing_readable_falls_through_to_free_text(self):
        """kind is ECIA implies ecia_fields is non-empty -- the contract relies on it"""
        scan = "[)>" + RS + "06" + GS + "1TLOT4471" + GS + "4LUS" + RS + EOT
        result = classify(scan)
        assert result.kind is ScanKind.FREE_TEXT
        assert result.ecia_fields == {}

    def test_something_that_only_looks_like_an_envelope_is_free_text(self):
        scan = "[)>" + RS + "06X" + GS + "1PLM358N" + RS + EOT
        assert classify(scan).kind is ScanKind.FREE_TEXT

    def test_an_internal_code_still_outranks_an_envelope_shaped_string(self):
        assert classify(VALID_INTERNAL).kind is ScanKind.INTERNAL


class TestPrecedence:
    """Rule 1 outranks rule 3 by design"""

    def test_internal_code_outranks_a_check_digit_valid_all_digit_string(self):
        """A label this shop printed must never resolve to a foreign trade item"""
        assert classify(VALID_INTERNAL).kind is ScanKind.INTERNAL
        # And the GTIN rule still works when the internal rule does not match.
        assert classify(VALID_UPC_A).kind is ScanKind.GTIN


class TestFreeText:
    """Rule 5 always matches"""

    def test_plain_text(self):
        result = classify("blue widget, 10mm")
        assert result.kind is ScanKind.FREE_TEXT
        assert result.value == "blue widget, 10mm"

    def test_asin_shaped_string_is_free_text_because_it_has_no_shape(self):
        """Rule 4 is not structural -- resolution looks it up afterwards"""
        assert classify("B0ABCDEFGH").kind is ScanKind.FREE_TEXT

    def test_ja_id_is_free_text(self):
        assert classify("JA000123").kind is ScanKind.FREE_TEXT

    def test_empty_string(self):
        result = classify("")
        assert result.kind is ScanKind.FREE_TEXT
        assert result.value == ""

    def test_ecia_fields_are_empty_when_not_ecia(self):
        assert classify("anything").ecia_fields == {}


class TestNeverRaises:
    """The guarantee the whole scan path rests on"""

    @pytest.mark.parametrize(
        "scan",
        [
            "",
            " ",
            "\n",
            "\x00",
            "\x1d\x1e\x04",
            "\x00\x01\x02\x03" * 1024,
            "\ud800",  # lone surrogate
            "[)>",
            "0" * 14,
            "-1",
            "٠١٢٣٤٥٦٧٨٩",  # Arabic-Indic digits: str.isdigit() is True for these
        ],
    )
    def test_does_not_raise_and_always_returns_a_kind(self, scan):
        result = classify(scan)
        assert isinstance(result.kind, ScanKind)
        assert result.raw == scan

    def test_four_kilobytes_of_control_characters(self):
        scan = "\x1d" * 4096
        assert classify(scan).kind is ScanKind.FREE_TEXT

    def test_non_string_raises_type_error(self):
        """A broken caller, not a property of the scan"""
        with pytest.raises(TypeError):
            classify(None)
        with pytest.raises(TypeError):
            classify(12345)
