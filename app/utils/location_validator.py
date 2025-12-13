"""
Location Pattern Validation Utilities

This module provides centralized validation functions for parsing inventory tracking
input strings. The validation logic distinguishes between three types of input:
1. JA IDs (item identifiers)
2. Location codes (storage location identifiers)
3. Sub-locations (free-form location details within a storage location)

IMPORTANT: This is the single source of truth for location pattern validation.
If new location types are added in the future (e.g., for new storage areas),
update the patterns in is_location() and document them here.

Pattern Rules (applied in order):
------------------------------
1. JA ID Pattern: ^JA[0-9]+$
   - Literal "JA" prefix followed by one or more digits
   - Example: JA000123, JA1, JA999999

2. Location Patterns:
   - Metal stock storage: ^M[0-9]+.*
     Starts with "M" followed by digits, then any characters
     Examples: M1-A, M2-B, M10-Shelf3

   - Threaded stock storage: ^T-?[0-9]+.*
     Starts with "T", optionally a dash, followed by digits, then any characters
     Examples: T-5, T1, T99-Row2

   - General/Other storage: Exact match "Other"
     Case-sensitive exact string match
     Example: Other

3. Sub-location Pattern: Any string NOT matching the above
   - Free-form text describing a position within a location
   - Examples: "Drawer 3", "Shelf 2", "Storage Bin A"

Future Extensibility:
--------------------
To add a new location type pattern:
1. Add the pattern to the LOCATION_PATTERNS list in is_location()
2. Document it in the docstring above
3. Add test cases in tests/unit/test_location_validator.py
4. Update relevant documentation (user manual, etc.)
"""

import re


def is_ja_id(value: str) -> bool:
    """
    Check if a string matches the JA ID pattern.

    JA IDs are item identifiers in the format "JA" followed by one or more digits.

    Args:
        value: String to check

    Returns:
        True if the string matches the JA ID pattern, False otherwise

    Examples:
        >>> is_ja_id("JA000123")
        True
        >>> is_ja_id("JA1")
        True
        >>> is_ja_id("JA")
        False
        >>> is_ja_id("M1-A")
        False
    """
    if not value or not isinstance(value, str):
        return False
    return bool(re.match(r'^JA[0-9]+$', value))


def is_location(value: str) -> bool:
    """
    Check if a string matches any of the valid location patterns.

    Valid location patterns are:
    - Metal stock storage: M followed by digits (e.g., M1-A, M2-B)
    - Threaded stock storage: T followed by digits (e.g., T-5, T1)
    - General storage: Exact string "Other"

    Args:
        value: String to check

    Returns:
        True if the string matches a location pattern, False otherwise

    Examples:
        >>> is_location("M1-A")
        True
        >>> is_location("T-5")
        True
        >>> is_location("Other")
        True
        >>> is_location("Drawer 3")
        False
        >>> is_location("JA000123")
        False
    """
    if not value or not isinstance(value, str):
        return False

    # IMPORTANT: This list defines all valid location patterns.
    # To add new location types in the future, add patterns here and update the
    # module docstring above with the new pattern documentation.
    LOCATION_PATTERNS = [
        r'^M[0-9]+.*',  # Metal stock storage (M + digits + optional suffix)
        r'^T-?[0-9]+.*',  # Threaded stock storage (T + optional dash + digits + optional suffix)
    ]

    # Check regex patterns
    for pattern in LOCATION_PATTERNS:
        if re.match(pattern, value):
            return True

    # Check exact match for "Other"
    if value == 'Other':
        return True

    return False


def classify_input(value: str) -> str:
    """
    Classify an input string as 'ja_id', 'location', or 'sub_location'.

    This function applies the validation rules in order:
    1. Check if it's a JA ID
    2. Check if it's a location
    3. Otherwise, it's a sub-location

    Args:
        value: String to classify

    Returns:
        One of: 'ja_id', 'location', 'sub_location'

    Examples:
        >>> classify_input("JA000123")
        'ja_id'
        >>> classify_input("M1-A")
        'location'
        >>> classify_input("Drawer 3")
        'sub_location'
    """
    if is_ja_id(value):
        return 'ja_id'
    elif is_location(value):
        return 'location'
    else:
        return 'sub_location'
