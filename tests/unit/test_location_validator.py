"""
Unit tests for location pattern validation utilities.

Tests the centralized location pattern validation logic in app/utils/location_validator.py
"""

import pytest
from app.utils.location_validator import is_ja_id, is_location, classify_input


class TestIsJaId:
    """Tests for JA ID pattern validation"""

    def test_valid_ja_id_with_zeros(self):
        """Test JA ID with leading zeros"""
        assert is_ja_id("JA000123") is True

    def test_valid_ja_id_single_digit(self):
        """Test JA ID with single digit"""
        assert is_ja_id("JA1") is True

    def test_valid_ja_id_many_digits(self):
        """Test JA ID with many digits"""
        assert is_ja_id("JA999999") is True

    def test_invalid_ja_id_no_digits(self):
        """Test that 'JA' alone is not valid"""
        assert is_ja_id("JA") is False

    def test_invalid_ja_id_with_letters(self):
        """Test that JA followed by letters is not valid"""
        assert is_ja_id("JA123ABC") is False

    def test_invalid_ja_id_lowercase(self):
        """Test that lowercase 'ja' is not valid"""
        assert is_ja_id("ja123") is False

    def test_invalid_ja_id_wrong_prefix(self):
        """Test that other prefixes are not valid"""
        assert is_ja_id("AB123") is False

    def test_invalid_empty_string(self):
        """Test that empty string is not valid"""
        assert is_ja_id("") is False

    def test_invalid_none(self):
        """Test that None is not valid"""
        assert is_ja_id(None) is False

    def test_invalid_location_pattern(self):
        """Test that location patterns are not recognized as JA IDs"""
        assert is_ja_id("M1-A") is False
        assert is_ja_id("T-5") is False

    def test_invalid_with_spaces(self):
        """Test that JA ID with spaces is not valid"""
        assert is_ja_id("JA 123") is False


class TestIsLocation:
    """Tests for location pattern validation"""

    # Metal storage location tests (M pattern)
    def test_valid_metal_location_simple(self):
        """Test simple metal storage location"""
        assert is_location("M1") is True

    def test_valid_metal_location_with_dash(self):
        """Test metal storage location with dash"""
        assert is_location("M1-A") is True

    def test_valid_metal_location_with_suffix(self):
        """Test metal storage location with suffix"""
        assert is_location("M2-B") is True
        assert is_location("M10-Shelf3") is True

    def test_valid_metal_location_complex(self):
        """Test complex metal storage location"""
        assert is_location("M99-Row2-Bin5") is True

    # Threaded storage location tests (T pattern)
    def test_valid_threaded_location_simple(self):
        """Test simple threaded storage location"""
        assert is_location("T1") is True

    def test_valid_threaded_location_with_dash(self):
        """Test threaded storage location with dash"""
        assert is_location("T-5") is True

    def test_valid_threaded_location_with_suffix(self):
        """Test threaded storage location with suffix"""
        assert is_location("T1-Row2") is True
        assert is_location("T99-Shelf5") is True

    # Other location tests
    def test_valid_other_location(self):
        """Test 'Other' location"""
        assert is_location("Other") is True

    def test_invalid_other_case_insensitive(self):
        """Test that 'Other' is case-sensitive"""
        assert is_location("other") is False
        assert is_location("OTHER") is False

    # Invalid location tests
    def test_invalid_location_ja_id(self):
        """Test that JA IDs are not recognized as locations"""
        assert is_location("JA000123") is False

    def test_invalid_location_sub_location(self):
        """Test that sub-locations are not recognized as locations"""
        assert is_location("Drawer 3") is False
        assert is_location("Shelf 2") is False
        assert is_location("Storage Bin A") is False

    def test_invalid_location_wrong_prefix(self):
        """Test that wrong prefixes are not valid locations"""
        assert is_location("A1-B") is False
        assert is_location("X99") is False

    def test_invalid_location_m_without_number(self):
        """Test that M without a number is not valid"""
        assert is_location("M-A") is False
        assert is_location("M") is False

    def test_invalid_location_t_without_number(self):
        """Test that T without a number is not valid"""
        assert is_location("T-A") is False
        assert is_location("T") is False

    def test_invalid_empty_string(self):
        """Test that empty string is not a valid location"""
        assert is_location("") is False

    def test_invalid_none(self):
        """Test that None is not a valid location"""
        assert is_location(None) is False


class TestClassifyInput:
    """Tests for input classification"""

    def test_classify_ja_id(self):
        """Test classification of JA IDs"""
        assert classify_input("JA000123") == 'ja_id'
        assert classify_input("JA1") == 'ja_id'

    def test_classify_metal_location(self):
        """Test classification of metal storage locations"""
        assert classify_input("M1-A") == 'location'
        assert classify_input("M2-B") == 'location'
        assert classify_input("M99") == 'location'

    def test_classify_threaded_location(self):
        """Test classification of threaded storage locations"""
        assert classify_input("T-5") == 'location'
        assert classify_input("T1") == 'location'
        assert classify_input("T99-Row2") == 'location'

    def test_classify_other_location(self):
        """Test classification of 'Other' location"""
        assert classify_input("Other") == 'location'

    def test_classify_sub_location(self):
        """Test classification of sub-locations"""
        assert classify_input("Drawer 3") == 'sub_location'
        assert classify_input("Shelf 2") == 'sub_location'
        assert classify_input("Storage Bin A") == 'sub_location'

    def test_classify_arbitrary_strings(self):
        """Test classification of arbitrary strings as sub-locations"""
        assert classify_input("Some Random Text") == 'sub_location'
        assert classify_input("12345") == 'sub_location'
        assert classify_input("AB-CD-EF") == 'sub_location'

    def test_classify_edge_cases(self):
        """Test classification of edge cases"""
        # lowercase 'other' is not a location, so it's a sub-location
        assert classify_input("other") == 'sub_location'
        # JA without digits is not a JA ID, and doesn't match location, so sub-location
        assert classify_input("JA") == 'sub_location'
