"""
Unit tests for GS1 element-string recognition.

Covers app/utils/gs1.py -- 009 FR-001 through FR-007, the recognizer that lets a
manufacturer's own 2D barcode resolve as the trade item number it carries
instead of degrading to a text search.

The class that matters most here is TestItDoesNotValidate. Extraction and
validity are separate questions asked by separate modules, and the whole design
rests on this one not answering the second.
"""

import pytest

from app.utils.gs1 import decode_trade_item_number

GS = "\x1d"  # FNC1, as transmitted
RS = "\x1e"
EOT = "\x04"

# A real EAN-13 and the element string carrying it.
GTIN_13 = "9506000134352"
DIGITS = "09506000134352"
EL = "01" + DIGITS


class TestRecognizedForms:
    """009 FR-001, FR-003 -- every shape a wedge may emit for the same code"""

    @pytest.mark.parametrize(
        "raw",
        [
            EL,                    # bare, the deployed wedge's usual output
            GS + EL,               # FNC1 transmitted
            "]d1" + EL,            # AIM: GS1-128
            "]C1" + EL,            # AIM: Code 128, FNC1 in first position
            "]d2" + EL,            # AIM: DataMatrix, FNC1 in first position
            "]e0" + EL,            # AIM: GS1 DataBar
            "]C1" + GS + EL,       # AIM identifier and a transmitted FNC1 together
            " " + EL + " ",        # padding, matching rule 1's tolerance
            EL + "\r\n",           # the terminator a keyboard wedge appends
            EL + GS,               # trailing separator, absorbed by strip()
            EL + RS,               # RS is whitespace to Python, so also absorbed
        ],
    )
    def test_the_trade_item_number_is_extracted(self, raw):
        assert decode_trade_item_number(raw) == DIGITS

    def test_every_accepted_gtin_length_fits_inside_the_element_string(self):
        """AI 01 always carries fourteen digits, whatever the bare form's length"""
        assert decode_trade_item_number("01" + "00000000012348") == "00000000012348"
        assert decode_trade_item_number("01" + "00012345678905") == "00012345678905"


class TestTrailingElementStrings:
    """009 FR-004 -- AI 01 is fixed-length, so the next AI abuts it directly"""

    @pytest.mark.parametrize(
        "raw",
        [
            EL + "17260101",       # abutted: AI 17, an expiry date
            EL + "10LOT42",        # abutted: AI 10, a batch number
            EL + GS + "10LOT42",   # GS-separated, the variable-length case
            EL + "3103000123",     # abutted: AI 3103, a net weight
        ],
    )
    def test_a_following_element_string_is_ignored_not_fatal(self, raw):
        assert decode_trade_item_number(raw) == DIGITS

    def test_the_separator_is_consumed_but_only_one_of_them(self):
        """Asymmetric with the leading side, where strip() absorbs any number.
        A doubled separator encloses an empty element string the grammar does
        not permit, so the second one is left as the opener and refuses."""
        assert decode_trade_item_number(EL + GS + "10LOT42") == DIGITS
        assert decode_trade_item_number(EL + GS + GS + "10LOT42") is None


class TestNotAnElementString:
    """009 FR-005, FR-007 -- what merely resembles one is not one"""

    @pytest.mark.parametrize(
        "raw",
        [
            EL + "ABC",            # a letter cannot open an AI
            EL + " RES 10K 0805",  # the case that makes prose a barcode if accepted
            EL + EOT,              # EOT is not whitespace, not a GS, not a digit
            EL + RS + "10LOT42",   # an interior RS is not a group separator
            "01" + "0950600013435",       # thirteen digits, one short
            "01" + "0" * 13 + "X",        # a letter inside the fixed-length field
            "01" + "0" * 13 + "\n" + "17260101",  # newline inside the field: see below
            "01" + "٠١٢٣٤٥٦٧٨٩٠١٢٣",     # str.isdigit() is True for these; ASCII is required
            GS + "21SN0001",              # AI 21, a serial number
            GS + "17260101",              # AI 17, a date
            GS + "00123456789012345675",  # AI 00, an SSCC
            GS + "10LOT42" + GS + EL,     # AI 01 present but not first (FR-007)
            "0",
            "01",
            "",
            " ",
            "]d2",
            "]" + EL,              # a bare bracket is not an AIM identifier
            "]dd" + EL,            # AIM is a letter then a digit, not two letters
            GTIN_13,               # the bare barcode is rule 4's, not this rule's
        ],
    )
    def test_it_is_declined(self, raw):
        assert decode_trade_item_number(raw) is None

    @pytest.mark.parametrize(
        "raw,why",
        [
            (EL + "1ABC",            "one digit then letters"),
            (EL + "1 RES 10K 0805",  "one digit then prose -- the reported case"),
            (EL + "1",               "a lone digit is not a complete AI"),
            (EL + "1\x04",           "one digit then a control character"),
            (EL + GS + "RES 10K",    "the separator is a delimiter, not an exemption"),
            (EL + GS + "1ABC",       "and what follows it faces the same test"),
            (EL + GS + GS + "10LOT42",  "a doubled separator opens with a separator"),
            (EL + GS + "1",          "one digit after a separator is still not an AI"),
        ],
    )
    def test_a_tail_that_is_not_an_element_string_is_refused(self, raw, why):
        """Regression, PR #82 review.

        Every one of these returned the trade item number when the tail rule
        asked for one digit rather than two, and each therefore classified as
        GTIN '00012345678905' -- a key a real product can carry. The failure was
        not "malformed input accepted", it was free text with a lucky sixteen-
        character prefix resolving to somebody's product.

        The archived branch's review found the one-digit form twice and the
        separator exemption once. Do not relax this back.
        """
        assert decode_trade_item_number(raw) is None

    def test_a_newline_inside_the_field_is_not_a_digit(self):
        """Regression, PR #82 review.

        Python's '$' matches immediately before a trailing newline as well as at
        end-of-string, so '^[0-9]+$' called thirteen digits plus a newline
        fourteen digits' worth of match. The newline is interior here, so
        strip() never sees it. It mattered because gtin.normalize() *does* strip
        it, then sees a thirteen-digit accepted length and zero-pads it -- so a
        malformed label resolved to a real product rather than to a search,
        which is the exact wrong-match failure this module exists to avoid.
        """
        assert decode_trade_item_number("010012345678905\n17260101") is None

    @pytest.mark.parametrize(
        "whitespace",
        ["\n", "\r", "\t", " ", "\x0b", "\x0c"],
    )
    def test_no_whitespace_character_can_stand_in_for_a_digit(self, whitespace):
        """The newline was the reachable one; none of its siblings may be either"""
        assert decode_trade_item_number(
            "01" + "0" * 13 + whitespace + "17260101"
        ) is None


class TestItDoesNotValidate:
    """The seam: these digits are extracted, and app/utils/gtin.py judges them.

    If either of the first two cases starts returning None, extraction has begun
    making validity decisions and gtin.py has stopped being the single source of
    truth for what a trade item number is. The classifier depends on that split:
    a bad number must be refused by exactly the code that refuses a bad bare
    barcode, not by a second copy of the rule living here.
    """

    def test_a_bad_check_digit_is_still_extracted(self):
        assert decode_trade_item_number("0109506000134353") == "09506000134353"

    def test_the_wedge_no_read_value_is_still_extracted(self):
        assert decode_trade_item_number("01" + "0" * 14) == "0" * 14

    def test_a_length_gtin_would_reject_is_still_extracted(self):
        """Fourteen digits is the field's length, not a claim about the number"""
        assert decode_trade_item_number("01" + "99999999999999") == "99999999999999"


class TestNeverRaises:
    """009 NFR -- a shape test used in a boolean position must not throw"""

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            123,
            b"0109506000134352",
            [],
            {},
            object(),
        ],
    )
    def test_a_non_string_returns_none_rather_than_raising(self, raw):
        """Unlike classify(), which treats a non-str as a broken caller"""
        assert decode_trade_item_number(raw) is None

    @pytest.mark.parametrize(
        "raw",
        [
            "\x00",
            "\ud800",              # lone surrogate
            "\x1d\x1e\x04",
            "\x00\x01\x02\x03" * 1024,
            "]" * 4096,
        ],
    )
    def test_hostile_input_is_declined_without_raising(self, raw):
        assert decode_trade_item_number(raw) is None

    def test_a_very_long_payload_opening_with_ai_01_still_reads_only_its_field(self):
        """Length is not a rejection reason; only the first fourteen digits are read"""
        assert decode_trade_item_number("01" * 4096) == "01010101010101"
