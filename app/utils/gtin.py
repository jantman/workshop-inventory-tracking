"""
GTIN normalization and check-digit validation utilities (Story 2.2).

This module is the single source of truth for GTIN validity, the GS1 mod-10
check digit, and the canonical 14-digit key. It is a PURE module: standard
library only, no Flask/DB/app imports, no I/O. Its only failure signal is
`InvalidGtinError`, a plain `ValueError` subclass. The service layer
(`app/mariadb_catalog_service.py`) calls into it and translates its errors into
domain `ValidationError`s; routes/templates never re-derive this logic.

GTIN forms and the shared key
-----------------------------
The four GS1 trade-item numbering forms differ only in length:

- GTIN-8  (8 digits)  — e.g. small-package EAN-8
- UPC-A   (12 digits) — North American retail
- EAN-13  (13 digits) — international retail
- GTIN-14 (14 digits) — trade/packaging unit

Every form left-zero-pads to a 14-digit key, so all four encodings of one
product resolve to the same canonical value. Leading zeros contribute nothing
to the weighted sum, so a single set of fixed weights applied to the padded 14
is uniform and correct across all forms.

GS1 mod-10 check digit
----------------------
Over the 13 digits to the left of the check digit, each digit is multiplied by
3 or 1 in alternating positions (weight 3 on the rightmost of those 13, then
alternating). The check digit is the amount that rounds the weighted sum up to
the next multiple of 10.

The all-zero refusal
--------------------
An all-zero run of any accepted length — `'00000000'`, `'000000000000'`,
`'0000000000000'`, `'00000000000000'` — is refused as a GTIN even though it
passes the mod-10 check (zero is the correct check digit over all zeros). It is
the classic keyboard-wedge no-read output, and accepting it would let a failed
scan resolve to a plausible-looking trade item number indistinguishable from a
real one. The rule lives here and only here, so every caller inherits it
without re-deriving it: the scan router (the no-read becomes `free_text`), the
service write path (it can no longer be stored as a validated `GTIN`), the
lookup path (`find_product_id_by_gtin` returns `None` for it), and the routes.
Only an all-zero run qualifies; a GTIN that merely ends in a zero check digit,
or one with leading zeros, is untouched.

Future extensibility:
--------------------
Only the four fixed-length forms in {8, 12, 13, 14} are handled (FR9). Longer
GS1 structures (e.g. SSCC-18, GSIN) are deliberately out of scope; do not add
handling for them here without a corresponding requirement. Note that the
all-zero refusal is an equality against the 14-wide key: a length above
`_GTIN_KEY_LENGTH` would survive `zfill` unpadded and stop matching, so any
requirement that widens the accepted set must revisit that check as well.
"""

# Accepted raw-input lengths (before left-zero-padding to 14).
_VALID_GTIN_LENGTHS = frozenset({8, 12, 13, 14})

# The canonical key length all forms normalize to.
_GTIN_KEY_LENGTH = 14

# The wedge no-read, as it looks once padded. Named rather than built inline so
# the rule is greppable and sits beside its two siblings above.
_ALL_ZERO_KEY = '0' * _GTIN_KEY_LENGTH


class InvalidGtinError(ValueError):
    """
    Raised when a value is not a valid GTIN (not a string, non-digit, wrong
    length, all zeros, or a failed mod-10 check digit). A plain `ValueError`
    subclass so this module stays free of any app/framework dependency; callers
    translate it into a domain error.
    """


def compute_check_digit(data13: str) -> int:
    """
    Compute the GS1 mod-10 check digit for the 13 digits left of the check
    digit.

    The rightmost of the 13 digits gets weight 3, then weights alternate
    1, 3, 1, ... moving left. The check digit brings the weighted sum up to the
    next multiple of 10.

    Args:
        data13: Exactly the 13 digits to the left of the check digit (as they
            appear in the left-zero-padded 14-digit key). Callers are
            responsible for passing 13 ASCII digits; this function does not
            re-validate length.

    Returns:
        The check digit, an int in 0..9.

    Examples:
        >>> compute_check_digit('0000001234567')
        0
        >>> compute_check_digit('0001234567890')
        5
    """
    if (not isinstance(data13, str) or len(data13) != 13
            or not data13.isascii() or not data13.isdigit()):
        # Honor the module contract: the only failure signal is
        # InvalidGtinError, never a bare ValueError from int() on a non-digit.
        raise InvalidGtinError(
            f'compute_check_digit requires 13 ASCII digits, got {data13!r}.')
    total = sum((3 if i % 2 == 0 else 1) * int(d)
                for i, d in enumerate(reversed(data13)))
    return (10 - (total % 10)) % 10


def normalize_gtin(value: str) -> str:
    """
    Normalize any accepted GTIN form to its canonical 14-digit, left-zero-padded
    key, validating the mod-10 check digit.

    Steps: strip surrounding whitespace; require all-ASCII digits and a length
    in {8, 12, 13, 14}; left-zero-pad to 14; refuse an all-zero run; verify the
    GS1 mod-10 check digit over the padded 14 digits.

    Args:
        value: A GTIN in any of the four accepted forms.

    Returns:
        The canonical 14-digit key.

    Raises:
        InvalidGtinError: if the input is not a string, is not all ASCII
            digits, has an unsupported length, is an all-zero run (the wedge
            no-read), or fails check-digit validation.

    Examples:
        >>> normalize_gtin('012345678905')
        '00012345678905'
        >>> normalize_gtin('00012345678905')
        '00012345678905'
    """
    if not isinstance(value, str):
        # Non-str input (None, int, bytes, ...) fails as InvalidGtinError, not a
        # bare AttributeError from .strip(), so is_valid_gtin never raises and
        # callers only ever catch this module's one failure signal.
        raise InvalidGtinError(
            f'GTIN must be a string, got {type(value).__name__}: {value!r}.')
    s = value.strip()
    # str.isdigit() also accepts some non-ASCII digit characters; require ASCII
    # so we never build a key that can't be compared/stored as plain digits.
    if not s.isascii() or not s.isdigit():
        raise InvalidGtinError(
            f'GTIN must contain only digits: {value!r}.')
    if len(s) not in _VALID_GTIN_LENGTHS:
        raise InvalidGtinError(
            f'GTIN must be 8, 12, 13, or 14 digits, got {len(s)}: {value!r}.')

    padded = s.zfill(_GTIN_KEY_LENGTH)
    # Judged on the padded key so all four accepted forms of the wedge no-read
    # collapse to one rule. Placed after the length check so '00000' keeps its
    # wrong-length message, and before the check-digit check because zero IS the
    # correct check digit over all zeros — reporting a check-digit failure here
    # would be a lie, and reporting nothing would let the no-read through.
    if padded == _ALL_ZERO_KEY:
        raise InvalidGtinError(
            f'GTIN must not be all zeros: {value!r}.')
    expected = compute_check_digit(padded[:13])
    if expected != int(padded[13]):
        raise InvalidGtinError(
            f'GTIN check digit is invalid: expected {expected}, '
            f'got {padded[13]} in {value!r}.')
    return padded


def is_valid_gtin(value: str) -> bool:
    """
    Return True if `value` is a valid GTIN (normalizes cleanly), False
    otherwise. Never raises.

    Args:
        value: Candidate GTIN string (any accepted form).

    Returns:
        True if `normalize_gtin` would succeed, False otherwise.

    Examples:
        >>> is_valid_gtin('012345678905')
        True
        >>> is_valid_gtin('012345678900')
        False
        >>> is_valid_gtin('00000000')
        False
        >>> is_valid_gtin('not-a-gtin')
        False
    """
    try:
        normalize_gtin(value)
        return True
    except InvalidGtinError:
        return False
