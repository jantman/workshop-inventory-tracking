"""
Distributor 2D label parsing -- ISO/IEC 15434 format-06 envelopes.

DigiKey and Mouser print an envelope of the shape::

    '[)>' RS '06' GS <record> GS <record> ... RS EOT

where each record is one ANSI MH10.8.2 data identifier immediately followed by
its value.  Seven identifiers have a home in this catalogue; every other legal
identifier a distributor prints is ignored silently, because an unrecognized
identifier is a field with no screen to show it on, not a damaged scan.

Values are extracted **uncoerced**.  No date parsing, no quantity-to-int, no
content validation -- FR-017 requires every extracted value stay editable, and
rejecting a malformed date would lose data the operator can read off the label
with their own eyes.

**Never raises on a str.**  A scan that is not an envelope, or is an envelope
carrying nothing readable, yields an empty mapping and falls through to
free-text handling.

Pure module: standard library only.  No Flask, no database, no config.
"""

import re
from typing import Dict

RS = "\x1e"  # record separator
GS = "\x1d"  # group separator
EOT = "\x04"  # end of transmission

HEADER = "[)>"
FORMAT_INDICATOR = "06"

# The seven MH10.8.2 identifiers this catalogue has a home for.
RECOGNIZED_IDENTIFIERS = frozenset({"P", "1P", "Q", "K", "1K", "9D", "10D"})

# An MH10.8.2 data identifier is an optional numeric qualifier followed by a
# letter; the value is everything after it.
_RECORD_PATTERN = re.compile(r"^(\d*[A-Z])(.*)$", re.DOTALL)


def parse(scan: str) -> Dict[str, str]:
    """Extract recognized data identifiers from a format-06 envelope.

    Args:
        scan: The raw scan, exactly as captured.

    Returns:
        A mapping of data identifier to its uncoerced string value.  Empty when
        the scan is not a well-formed envelope, or is one carrying no
        recognized identifier with a non-empty value.

    Raises:
        TypeError: If ``scan`` is not a ``str``.  That is a broken caller, not a
            property of the scan.
    """
    if not isinstance(scan, str):
        raise TypeError(f"scan must be a str, got {type(scan).__name__}")

    body = _envelope_body(scan)
    if body is None:
        return {}

    fields: Dict[str, str] = {}
    for record in body.split(GS):
        if not record:
            continue

        match = _RECORD_PATTERN.match(record)
        if match is None:
            continue

        identifier, value = match.group(1), match.group(2)
        if identifier not in RECOGNIZED_IDENTIFIERS or not value:
            continue

        # First occurrence wins; a distributor repeating an identifier is not a
        # case anyone has observed, and overwriting would silently prefer the
        # last one for no stated reason.
        fields.setdefault(identifier, value)

    return fields


def _envelope_body(scan: str) -> "str | None":
    """Return the record body of a format-06 envelope, or None if it is not one.

    Three shapes must not be read as envelopes, each learned from a real scan:

    - A character glued onto the format indicator (``06X``) means the indicator
      was never delimited, so the string only *resembles* an envelope.
    - A leading separator before the header means the header is not the header.
    - A half-delivered trailer (data followed by ``EOT`` with no ``RS``) must not
      read the ``EOT`` as part of the value.
    """
    # A wedge terminates with Enter; trailing newlines are transport, not data.
    text = scan.rstrip("\r\n")

    if not text.startswith(HEADER):
        return None

    rest = text[len(HEADER):]
    if not rest.startswith(RS):
        return None

    rest = rest[len(RS):]

    # The format indicator must be delimited by the group separator that follows
    # it -- '06X' is not '06'.
    indicator, separator, body = rest.partition(GS)
    if not separator or indicator != FORMAT_INDICATOR:
        return None

    return _strip_trailer(body)


def _strip_trailer(body: str) -> str:
    """Remove the message trailer, in whichever form it arrived."""
    if body.endswith(RS + EOT):
        return body[: -len(RS + EOT)]
    if body.endswith(EOT):
        # Half-delivered trailer: the EOT terminates the transmission and is not
        # part of the value it happens to follow.
        return body[: -len(EOT)]
    if body.endswith(RS):
        return body[: -len(RS)]
    return body
