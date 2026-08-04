"""
Retail barcode (GTIN) normalization and check-digit validation.

Every retail barcode is normalized to a 14-digit key by left-padding with zeros,
which is the GS1-sanctioned way to make UPC-A ``012345678905`` and its EAN-13
form ``0012345678905`` the same value.  Storing the normalized key is what makes
FR-009 ("equivalent forms resolve to a single product") a unique-index property
rather than application logic that a future read path could bypass.

Pure module: standard library only.  No Flask, no database, no config.
"""

import re
from typing import Optional

# str.isdigit() is True for Arabic-Indic and other Unicode digits, which would
# let a non-ASCII string become a stored GTIN key. A barcode is ASCII digits.
_ASCII_DIGITS = re.compile(r"^[0-9]+$")

# GTIN-8, UPC-A, EAN-13, GTIN-14. Anything else is not a retail barcode.
ACCEPTED_LENGTHS = (8, 12, 13, 14)

GTIN_KEY_LENGTH = 14

# The shape a keyboard-wedge scanner emits on a no-read. Never a real product.
ALL_ZERO_KEY = "0" * GTIN_KEY_LENGTH


def normalize(value: str) -> Optional[str]:
    """Normalize a raw barcode to its 14-digit GTIN key.

    Args:
        value: The raw scan or typed barcode.

    Returns:
        The 14-digit key, or None if the value is not a plausible GTIN
        (wrong length, or not all digits).  Normalization does not validate
        the check digit -- see :func:`is_valid`.
    """
    if not isinstance(value, str):
        return None

    stripped = value.strip()
    if len(stripped) not in ACCEPTED_LENGTHS or not _ASCII_DIGITS.match(stripped):
        return None

    return stripped.zfill(GTIN_KEY_LENGTH)


def check_digit(payload: str) -> int:
    """Compute the GS1 mod-10 check digit for a payload.

    Args:
        payload: The digits preceding the check digit.

    Returns:
        The check digit, 0-9.

    Raises:
        ValueError: If the payload is not all digits.
    """
    if not _ASCII_DIGITS.match(payload):
        raise ValueError(f"Check digit payload must be all digits: {payload!r}")

    # Weights alternate 3,1,3,1... reading right to left from the position
    # immediately left of the check digit.
    total = 0
    for position, char in enumerate(reversed(payload)):
        weight = 3 if position % 2 == 0 else 1
        total += int(char) * weight

    return (10 - (total % 10)) % 10


def is_valid(key: str) -> bool:
    """Report whether a 14-digit GTIN key has a correct check digit.

    An all-zero key is refused outright regardless of its check digit, because
    that is what a wedge scanner emits on a no-read rather than a trade item.

    Args:
        key: A 14-digit GTIN key, as produced by :func:`normalize`.

    Returns:
        True when the key is a valid GTIN.
    """
    if not isinstance(key, str):
        return False
    if len(key) != GTIN_KEY_LENGTH or not _ASCII_DIGITS.match(key):
        return False
    if key == ALL_ZERO_KEY:
        return False

    return check_digit(key[:-1]) == int(key[-1])


def normalize_and_validate(value: str) -> Optional[str]:
    """Normalize a raw barcode and return it only if it is a valid GTIN.

    This is the classifier's entry point: a scan is a GTIN when, and only when,
    this returns a key.

    Args:
        value: The raw scan or typed barcode.

    Returns:
        The 14-digit key, or None if the value is not a valid GTIN.
    """
    key = normalize(value)
    if key is None or not is_valid(key):
        return None
    return key


def is_all_zero(value: str) -> bool:
    """Report whether a value normalizes to the all-zero no-read key.

    The operator may override a failed check digit (FR-010), but never this --
    so the override path needs to be able to ask.

    Args:
        value: The raw scan or typed barcode.

    Returns:
        True when the value normalizes to fourteen zeros.
    """
    return normalize(value) == ALL_ZERO_KEY
