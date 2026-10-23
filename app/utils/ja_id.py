"""
JA ID recognition for the scan path.

A JA ID is ``JA`` followed by exactly six digits -- the same shape the database's
``ck_valid_ja_id_format`` constraint enforces. It names an inventory item, not a
product, which makes it the one scan that does not lead to the catalog.

Lowercase is accepted and uppercased, as the header's old JA ID lookup box did,
and surrounding whitespace is stripped because a keyboard-wedge scanner may
append a terminator.

Pure module: standard library only.  No Flask, no database, no config.

Author: Jason Antman, 2026.
"""

import re
from typing import Optional

JA_ID_PATTERN = re.compile(r"^JA[0-9]{6}$")


def normalize_ja_id(value: str) -> Optional[str]:
    """Return the canonical JA ID a scan carries, or None if it is not one.

    Args:
        value: The candidate string, exactly as captured.

    Returns:
        The JA ID uppercased with whitespace stripped, or None.
    """
    candidate = value.strip().upper()
    if JA_ID_PATTERN.match(candidate) is None:
        return None
    return candidate
