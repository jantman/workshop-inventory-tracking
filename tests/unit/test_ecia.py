"""
Unit tests for ISO/IEC 15434 format-06 distributor label parsing.

Covers app/utils/ecia.py -- FR-016 extraction and the never-raise-on-a-str
guarantee that keeps a damaged scan from dead-ending.
"""

import pytest

from app.utils.ecia import EOT, GS, RS, parse


def envelope(*records: str, trailer: str = RS + EOT) -> str:
    """Build a well-formed format-06 envelope around the given records."""
    return "[)>" + RS + "06" + GS + GS.join(records) + trailer


class TestWellFormedEnvelopes:
    """The seven identifiers this catalogue has a home for"""

    def test_extracts_manufacturer_part_number(self):
        assert parse(envelope("1PLM358N")) == {"1P": "LM358N"}

    def test_extracts_all_seven_identifiers(self):
        scan = envelope(
            "P296-1234-5-ND",
            "1PLM358N",
            "Q100",
            "K12345678",
            "1KSO987654",
            "9D2431",
            "10D2430",
        )
        assert parse(scan) == {
            "P": "296-1234-5-ND",
            "1P": "LM358N",
            "Q": "100",
            "K": "12345678",
            "1K": "SO987654",
            "9D": "2431",
            "10D": "2430",
        }

    def test_unrecognized_identifiers_are_ignored_silently(self):
        """A lot code has no screen to show it on; it is not a damaged scan"""
        scan = envelope("1PLM358N", "1TLOT4471", "4LUS", "30PXYZ")
        assert parse(scan) == {"1P": "LM358N"}

    def test_values_are_uncoerced_strings(self):
        """FR-017: a malformed date is data the operator can read for themselves"""
        result = parse(envelope("Q0100", "9Dnot-a-date"))
        assert result["Q"] == "0100"
        assert result["9D"] == "not-a-date"

    def test_quantity_is_not_converted_to_int(self):
        assert parse(envelope("Q100"))["Q"] == "100"
        assert isinstance(parse(envelope("Q100"))["Q"], str)

    def test_trailing_newline_from_the_wedge_is_tolerated(self):
        assert parse(envelope("1PLM358N") + "\r\n") == {"1P": "LM358N"}

    def test_empty_records_are_skipped(self):
        scan = "[)>" + RS + "06" + GS + GS + "1PLM358N" + GS + RS + EOT
        assert parse(scan) == {"1P": "LM358N"}

    def test_identifier_with_no_value_carries_nothing(self):
        assert parse(envelope("1P")) == {}


class TestTrailerVariants:
    """The trailer arrives in more than one shape"""

    def test_full_trailer(self):
        assert parse(envelope("1PLM358N", trailer=RS + EOT)) == {"1P": "LM358N"}

    def test_record_separator_only(self):
        assert parse(envelope("1PLM358N", trailer=RS)) == {"1P": "LM358N"}

    def test_no_trailer_at_all(self):
        assert parse(envelope("1PLM358N", trailer="")) == {"1P": "LM358N"}

    def test_half_delivered_trailer_does_not_read_eot_as_data(self):
        """Research edge case: <data> EOT with no RS"""
        assert parse(envelope("1PLM358N", trailer=EOT)) == {"1P": "LM358N"}


class TestNotAnEnvelope:
    """Shapes that resemble an envelope but are not one"""

    def test_character_glued_onto_the_format_indicator(self):
        """Research edge case: the indicator was never delimited"""
        scan = "[)>" + RS + "06X" + GS + "1PLM358N" + RS + EOT
        assert parse(scan) == {}

    def test_leading_separator_before_the_header(self):
        scan = RS + "[)>" + RS + "06" + GS + "1PLM358N" + RS + EOT
        assert parse(scan) == {}

    def test_wrong_format_indicator(self):
        scan = "[)>" + RS + "05" + GS + "1PLM358N" + RS + EOT
        assert parse(scan) == {}

    def test_missing_record_separator_after_the_header(self):
        scan = "[)>" + "06" + GS + "1PLM358N" + RS + EOT
        assert parse(scan) == {}

    def test_format_indicator_never_delimited_by_a_group_separator(self):
        scan = "[)>" + RS + "06"
        assert parse(scan) == {}

    def test_well_formed_envelope_carrying_nothing_readable(self):
        """kind is ECIA implies ecia_fields is non-empty -- so this yields {}"""
        assert parse(envelope("1TLOT4471", "4LUS")) == {}

    def test_empty_envelope(self):
        assert parse(envelope("")) == {}


class TestNeverRaises:
    """SC-008: a scan must never dead-end, and an exception is a dead end"""

    @pytest.mark.parametrize(
        "scan",
        [
            "",
            " ",
            "plain free text",
            "JA000123",
            "WIT0123456789",
            "012345678905",
            "\x00\x01\x02\x03\x04",
            "\x1d" * 4096,
            "\x1e\x1d\x04",
            "[)>",
            "[)>\x1e",
            "\ud800",  # lone surrogate
            "[)>" + RS + "06" + GS + "\x00\x01\x02",
        ],
    )
    def test_does_not_raise(self, scan):
        assert parse(scan) == {} or isinstance(parse(scan), dict)

    def test_four_kilobytes_of_control_characters(self):
        assert parse("\x1d\x1e\x04" * 1400) == {}

    def test_non_string_raises_type_error(self):
        """A broken caller, not a property of the scan"""
        with pytest.raises(TypeError):
            parse(None)
        with pytest.raises(TypeError):
            parse(b"[)>")
