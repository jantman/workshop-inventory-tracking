"""
GS1 element-string recognition -- the trade item number a manufacturer prints.

When a manufacturer puts a retail barcode on a box inside a 2D symbol, the
standard way to do it is a GS1 element string: the application identifier ``01``
followed by the fourteen-digit trade item number.  ``ecia.py`` reads a
distributor's envelope and ``gtin.py`` knows what a valid trade item number *is*;
this module reads the one wrapper that carries one.

**It extracts, it does not judge.**  The digits come back verbatim -- bad check
digit, all zeros, whatever was printed -- because ``app/utils/gtin.py`` is the
only thing entitled to say whether they are a GTIN.  Keeping the two apart is
what lets ``scan_router`` route a structured scan and a bare barcode through one
arm, so a manufacturer's 2D code is refused by exactly the code that refuses a
bad bare barcode rather than by a second copy of the rule (009 FR-002, FR-006).

**Only a payload *opening* with AI 01 is read** (009 FR-007).  There is no AI
table here, no FNC1-delimited field splitting, and no extraction of lot codes,
dates or serial numbers from the same symbol -- those have no screen to show
them on.  Reading a number out of the middle of an arbitrary payload is how a
wrong match happens.

**Never raises.**  On any input at all, including a non-``str``, which returns
``None`` rather than a ``TypeError``: callers use this in a boolean position, so
a raise would be noise.  That differs deliberately from
``scan_router.classify``, where a non-``str`` is a broken caller worth surfacing.

Pure module: standard library only.  No Flask, no database, no config.
"""

import re
from typing import Optional

# str.isdigit() is True for Arabic-Indic and other Unicode digits, which would
# let a non-ASCII string be read as a trade item number. A barcode is ASCII.
_ASCII_DIGITS = re.compile(r"^[0-9]+$")

FNC1 = "\x1d"  # the group separator, as a wedge transmits it

# An AIM symbology identifier: ']' then one letter then one digit. ']C1' and
# ']d2' are the two that matter -- they mean "Code 128 / DataMatrix with FNC1 in
# first position", which is a scanner announcing that GS1 data follows.
_AIM_IDENTIFIER = re.compile(r"^\][A-Za-z][0-9]")
_AIM_LENGTH = 3

# AI 01 is predefined-length (n2+n14) in the GS1 General Specifications.
_TRADE_ITEM_AI = "01"
_TRADE_ITEM_LENGTH = 14


def decode_trade_item_number(raw: str) -> Optional[str]:
    """Extract the trade item number from a payload opening with AI 01.

    Args:
        raw: The raw scan, exactly as captured.

    Returns:
        The fourteen digits, **verbatim and unvalidated**, or None when the
        payload is not an AI-01 element string.  A returned value is not a claim
        that it is a valid GTIN -- see :func:`app.utils.gtin.is_valid`.

    Never raises, on any input.

    >>> decode_trade_item_number('0109506000134352')
    '09506000134352'
    >>> decode_trade_item_number('9506000134352') is None
    True
    """
    if not isinstance(raw, str):
        return None

    candidate = raw.strip()

    if _AIM_IDENTIFIER.match(candidate):
        candidate = candidate[_AIM_LENGTH:]

    # NOT redundant with the strip() above: '\x1d'.isspace() is True, so a *bare*
    # leading separator is already gone by now. This exists for ']C1\x1d01...',
    # where the separator sat behind the AIM identifier and was therefore
    # interior -- not at either end -- at the moment strip() ran.
    if candidate.startswith(FNC1):
        candidate = candidate[len(FNC1):]

    if not candidate.startswith(_TRADE_ITEM_AI):
        return None

    field_end = len(_TRADE_ITEM_AI) + _TRADE_ITEM_LENGTH
    digits = candidate[len(_TRADE_ITEM_AI):field_end]
    if len(digits) != _TRADE_ITEM_LENGTH or not _ASCII_DIGITS.match(digits):
        return None

    # AI 01 is fixed-length, so nothing delimits it: on a real label the next
    # element string abuts it directly, and every AI opens with a digit. What
    # follows must therefore be another element string -- a separator, a digit,
    # or nothing. Accepting an arbitrary tail would make '01<14> RES 10K 0805' a
    # barcode; accepting only end-of-input would reject the very common
    # 01+17+10 concatenation printed on real boxes.
    tail = candidate[field_end:]
    if tail and tail[0] != FNC1 and not _ASCII_DIGITS.match(tail[0]):
        return None

    return digits
