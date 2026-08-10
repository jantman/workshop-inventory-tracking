"""
Unit tests for scan classification.

Covers app/utils/scan_router.py -- FR-014 routing, the precedence that keeps a
label this shop printed ahead of every foreign code, and the guarantee that
classify() never raises on a str (SC-008: a scan must never dead-end, and an
exception is a dead end).

Feature 009 inserted the trade-item element string as rule 3, so the rules a
test names are: 1 internal, 2 ECIA envelope, 3 element string, 4 GTIN, 5 vendor
item id (not structural -- resolution looks it up), 6 free text.
"""

import pytest

from app.models import ScanKind
from app.utils.ecia import EOT, GS, RS
from app.utils.scan_router import classify

VALID_INTERNAL = "WIT0123456789"
VALID_UPC_A = "012345678905"
VALID_GTIN_KEY = "00012345678905"

# The same trade item as a GS1 element string, the form a manufacturer prints in
# a 2D symbol. AI 01 is fixed-length, so it is '01' plus the fourteen-digit key.
AI_01_UPC_A = "01" + VALID_GTIN_KEY

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
    """Rule 4"""

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


class TestTradeItemElementString:
    """Rule 3 -- a manufacturer's own 2D barcode (009 FR-001 .. FR-007)

    Every case here classified as FREE_TEXT before feature 009, which is what
    made a scan of a manufacturer's box land on a search for digits that appear
    nowhere in the catalogue.
    """

    @pytest.mark.parametrize(
        "scan",
        [
            AI_01_UPC_A,                      # bare
            GS + AI_01_UPC_A,                 # FNC1 transmitted
            "]d1" + AI_01_UPC_A,              # AIM: GS1-128
            "]C1" + AI_01_UPC_A,              # AIM: Code 128, FNC1 first position
            "]d2" + AI_01_UPC_A,              # AIM: DataMatrix, FNC1 first position
            "]C1" + GS + AI_01_UPC_A,         # both together
            AI_01_UPC_A + "17260101",         # a further AI, abutted
            AI_01_UPC_A + GS + "10LOT42",     # a further AI, GS-separated
            " " + AI_01_UPC_A + "\r\n",       # padding and a wedge terminator
        ],
    )
    def test_it_classifies_as_the_gtin_it_carries(self, scan):
        result = classify(scan)
        assert result.kind is ScanKind.GTIN
        assert result.value == VALID_GTIN_KEY
        assert result.raw == scan

    def test_it_is_indistinguishable_from_the_bare_barcode(self):
        """009 FR-002: one arm, so the two cannot diverge -- raw is the only difference"""
        structured = classify(AI_01_UPC_A)
        bare = classify(VALID_UPC_A)
        assert structured.kind is bare.kind
        assert structured.value == bare.value
        assert structured.ecia_fields == bare.ecia_fields
        assert structured.raw != bare.raw

    def test_a_bad_check_digit_falls_through_exactly_as_a_bare_one_does(self):
        """009 FR-006: refused by gtin.py, not by a second copy of the rule"""
        result = classify("0100012345678906")
        assert result.kind is ScanKind.FREE_TEXT
        assert result.value == "0100012345678906"

    def test_the_wedge_no_read_value_falls_through(self):
        assert classify("01" + "0" * 14).kind is ScanKind.FREE_TEXT

    @pytest.mark.parametrize(
        "scan",
        [
            AI_01_UPC_A + " RES 10K 0805",    # prose must not become a barcode
            AI_01_UPC_A + "ABC",              # a letter cannot open an AI
            "01" + "0001234567890",           # thirteen digits, one short
            GS + "10LOT42" + GS + AI_01_UPC_A,  # AI 01 present but not first
        ],
    )
    def test_something_that_only_resembles_one_stays_free_text(self, scan):
        assert classify(scan).kind is ScanKind.FREE_TEXT

    def test_a_newline_inside_the_field_does_not_reach_a_real_product(self):
        """Regression, PR #82 review.

        The interesting part is not that this is refused -- it is that when the
        extractor's anchor was '$' rather than '\\Z', this malformed payload
        classified as GTIN '00012345678905', which is a key a real product can
        carry. A scan that should have produced a search produced somebody's
        product instead.
        """
        result = classify("010012345678905\n17260101")
        assert result.kind is ScanKind.FREE_TEXT
        assert result.value != VALID_GTIN_KEY


class TestPrecedence:
    """Rule 1 outranks rule 3 by design"""

    def test_internal_code_outranks_a_check_digit_valid_all_digit_string(self):
        """A label this shop printed must never resolve to a foreign trade item"""
        assert classify(VALID_INTERNAL).kind is ScanKind.INTERNAL
        # And the GTIN rule still works when the internal rule does not match.
        assert classify(VALID_UPC_A).kind is ScanKind.GTIN

    def test_an_envelope_still_outranks_the_element_string_rule(self):
        """Rule 2 runs first; an envelope opens '[)>' and can never reach rule 3"""
        assert classify(ENVELOPE).kind is ScanKind.ECIA

    @pytest.mark.parametrize(
        "scan,expected",
        [
            (VALID_UPC_A, ScanKind.GTIN),          # bare barcode: 12 digits
            ("0012345678905", ScanKind.GTIN),      # its EAN-13 form
            (VALID_GTIN_KEY, ScanKind.GTIN),       # its 14-digit key
            ("96385074", ScanKind.GTIN),           # GTIN-8
            ("012345678906", ScanKind.FREE_TEXT),  # bad check digit
            ("00000000", ScanKind.FREE_TEXT),      # the no-read value
            (VALID_INTERNAL, ScanKind.INTERNAL),   # this shop's own code
            (ENVELOPE, ScanKind.ECIA),             # a distributor's 2D label
            ("B0ABCDEFGH", ScanKind.FREE_TEXT),    # an ASIN has no shape
            ("JA000123", ScanKind.FREE_TEXT),      # an inventory item id
            ("M3 standoff", ScanKind.FREE_TEXT),   # plain text
        ],
    )
    def test_no_scan_that_resolved_before_feature_009_resolves_differently(
        self, scan, expected
    ):
        """009 FR-008. A rule-3 match needs >= 16 characters and every accepted
        GTIN length is <= 14, so the two candidate sets are disjoint and the new
        rule cannot capture any of these."""
        assert classify(scan).kind is expected


class TestFreeText:
    """Rule 6 always matches"""

    def test_plain_text(self):
        result = classify("blue widget, 10mm")
        assert result.kind is ScanKind.FREE_TEXT
        assert result.value == "blue widget, 10mm"

    def test_asin_shaped_string_is_free_text_because_it_has_no_shape(self):
        """Rule 5 is not structural -- resolution looks it up afterwards"""
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
