"""
Internal identifier candidate generation (Story 2.4).

This module is the single source of truth for the shape of a workshop-internal
product identifier: its alphabet, its length, and what counts as a well-formed
value. It is a PURE module: standard library only, no Flask/DB/app-package
imports, no I/O. Its only failure signal is `InvalidInternalIdError`, a plain
`ValueError` subclass. The service layer calls into it and translates its
errors into domain `ValidationError`s.

Candidate, not identity
-----------------------
`generate_internal_id()` returns a *candidate* only — it never reads or writes
the database, so it cannot know whether the value it produced is already in
use. Authority over uniqueness belongs entirely to the create-service (AD-8):
the service performs the insert, lets the `UNIQUE` constraint arbitrate, and
retries with a fresh candidate on collision. Consequently the column carries no
generating database default, and there is exactly one writer.

Alphabet and collision space
----------------------------
Values are drawn with `secrets.choice` from Crockford's base-32 alphabet: the
ten digits plus the twenty-two upper-case letters that remain after removing
`I`, `L`, `O`, and `U`. Dropping `I`/`L`/`O` removes the pairs most often
confused with `1` and `0` by both OCR and humans re-typing an identifier;
dropping `U` avoids accidental obscenities in generated strings. Ten characters
from a 32-symbol alphabet is ~1.1e15 distinct values, which makes a collision
effectively unreachable at workshop scale — but correctness does not rest on
that estimate, because the service's retry loop handles a collision regardless.

Future extensibility:
--------------------
The alphabet and length are the printed/scanned contract: changing either
invalidates every label already applied to a physical part, so treat both as
frozen once ids are in circulation. `generate_internal_id` accepts a `length`
override for tests and hypothetical future formats; `is_valid_internal_id`
deliberately validates against the single canonical `INTERNAL_ID_LENGTH`, since
a stored id of any other length is not something this system ever issued.
"""

import secrets
from typing import Any

# Crockford base-32: 0-9 plus A-Z minus I, L, O, U (32 symbols).
ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'

# Canonical length of an issued internal identifier.
INTERNAL_ID_LENGTH = 10


class InvalidInternalIdError(ValueError):
    """
    Raised when internal-id generation is asked for something it cannot
    produce (currently: a non-positive or non-integer length). A plain
    `ValueError` subclass so this module stays free of any framework
    dependency; callers translate it into a domain error.
    """


def generate_internal_id(*, length: int = INTERNAL_ID_LENGTH) -> str:
    """
    Return a fresh internal-id *candidate*.

    Each character is drawn independently with `secrets.choice` from
    `ALPHABET`, so the result is unpredictable and uniformly distributed. The
    value is a candidate only: this function never consults storage, so the
    caller must treat a `UNIQUE` violation on insert as an expected outcome and
    retry with a new candidate (AD-8).

    Args:
        length: How many characters to draw. Keyword-only; defaults to
            `INTERNAL_ID_LENGTH`. Must be a positive integer.

    Returns:
        A string of `length` characters, every one of them in `ALPHABET`.

    Raises:
        InvalidInternalIdError: if `length` is not a positive integer.

    Examples:
        >>> value = generate_internal_id()
        >>> len(value)
        10
        >>> set(value) <= set(ALPHABET)
        True
    """
    # bool is an int subclass; True would silently mean length 1, so exclude it.
    if isinstance(length, bool) or not isinstance(length, int):
        raise InvalidInternalIdError(
            f'Internal id length must be an integer, got '
            f'{type(length).__name__}: {length!r}.')
    if length <= 0:
        raise InvalidInternalIdError(
            f'Internal id length must be positive, got {length}.')
    return ''.join(secrets.choice(ALPHABET) for _ in range(length))


def is_valid_internal_id(value: Any) -> bool:
    """
    Return True if `value` is a well-formed internal identifier, False
    otherwise. Never raises.

    Well-formed means: a `str` of exactly `INTERNAL_ID_LENGTH` characters, every
    one of them drawn from `ALPHABET`. The check is case-sensitive — the
    alphabet is upper-case, and silently upper-casing input would let two
    different scanned strings map to one identifier.

    Args:
        value: Any object; non-strings simply return False.

    Returns:
        True if the value has the canonical issued shape, False otherwise.

    Examples:
        >>> is_valid_internal_id('ABC1234567')
        True
        >>> is_valid_internal_id('abc1234567')
        False
        >>> is_valid_internal_id(None)
        False
    """
    if not isinstance(value, str):
        return False
    if len(value) != INTERNAL_ID_LENGTH:
        return False
    return all(char in ALPHABET for char in value)
