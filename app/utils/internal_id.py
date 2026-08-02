"""
Internal product code generation and validation.

The internal code is the literal token ``WIT`` followed by 10 Crockford base32
characters.  The fixed prefix is what makes FR-015 work: no GTIN (all digits) and
no ECIA envelope (begins ``[)>``) can collide with it, so a scan either is one of
ours or it is not, with no ambiguity.

Crockford's alphabet omits I, L, O and U, which are the characters a person
misreads when retyping a scuffed label -- and FR-012 puts the code on the label in
human-readable form precisely so a worn label stays usable.

Pure module: standard library only.  No Flask, no database, no config.
"""

import re
import secrets

# Crockford base32: digits plus A-Z less I, L, O, U.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

PREFIX = "WIT"
CODE_LENGTH = 10

INTERNAL_ID_PATTERN = re.compile(r"^WIT[0-9A-HJKMNP-TV-Z]{10}$")


def generate_internal_id() -> str:
    """Generate a new internal product code.

    Returns:
        A code of the form ``WIT`` + 10 Crockford base32 characters.
    """
    body = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    return PREFIX + body


def is_internal_id(value: str) -> bool:
    """Report whether a string is a well-formed internal product code.

    Leading and trailing whitespace is stripped first, because a keyboard-wedge
    scanner may append a terminator.  Anything else -- lowercase, a wrong length,
    an excluded letter -- is not one of ours.

    Args:
        value: The candidate string.

    Returns:
        True when the value is a valid internal code.
    """
    if not isinstance(value, str):
        return False
    return INTERNAL_ID_PATTERN.match(value.strip()) is not None


def normalize_internal_id(value: str) -> str:
    """Return the canonical form of an internal code.

    Args:
        value: The candidate string.

    Returns:
        The whitespace-stripped code.

    Raises:
        ValueError: If the value is not a valid internal code.
    """
    if not is_internal_id(value):
        raise ValueError(f"Not a valid internal product code: {value!r}")
    return value.strip()
