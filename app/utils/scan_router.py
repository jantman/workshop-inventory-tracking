"""
Scan classification -- what kind of thing was scanned?

One pure function, five rules, first match wins, and the last rule always
matches. That last property is the whole point: FR-018 and SC-008 require that a
scan never dead-ends, so an unparseable scan is answered with FREE_TEXT carrying
the raw text rather than an exception.

Classification is **structural only**. It takes text and returns a kind; it
performs no database lookup. Turning a kind into a product -- including the one
rule that genuinely needs a lookup, a vendor item id such as an ASIN, which has
no distinguishing shape -- is CatalogService.resolve_scan()'s job.

Pure module: standard library plus app.models and the sibling app/utils parsers.
No Flask, no database, no config.
"""

from app.models import ScanClassification, ScanKind
from app.utils import ecia, gtin, internal_id


def classify(scan: str) -> ScanClassification:
    """Classify a captured scan.

    **Never raises on any str** -- not on empty, not on four kilobytes of control
    characters, not on a lone surrogate. The one reachable exception is a
    TypeError when ``scan`` is not a str, which is a broken caller rather than a
    property of the scan; classifying it as free text would bury the bug in a
    search result.

    Args:
        scan: The raw text exactly as captured.

    Returns:
        A ScanClassification. ``raw`` is always the scan as given.

    Raises:
        TypeError: If ``scan`` is not a ``str``.
    """
    if not isinstance(scan, str):
        raise TypeError(f"scan must be a str, got {type(scan).__name__}")

    # Rule 1: our own code. This outranks the GTIN rule by design -- a label this
    # shop printed must never resolve to somebody else's trade item.
    if internal_id.is_internal_id(scan):
        return ScanClassification(
            kind=ScanKind.INTERNAL,
            value=scan.strip(),
            raw=scan,
        )

    # Rule 2: a distributor's 2D label. Note that this rule can recognize its own
    # shape and still decline: a well-formed format-06 envelope carrying nothing
    # readable falls through to free text rather than classifying ECIA with an
    # empty field set. The consequence is worth relying on -- kind is ECIA implies
    # ecia_fields is non-empty.
    ecia_fields = ecia.parse(scan)
    if ecia_fields:
        return ScanClassification(
            kind=ScanKind.ECIA,
            value=ecia_fields.get('1P') or ecia_fields.get('P', ''),
            raw=scan,
            ecia_fields=ecia_fields,
        )

    # Rule 3: a retail barcode, in any of its equivalent lengths.
    gtin_key = gtin.normalize_and_validate(scan)
    if gtin_key is not None:
        return ScanClassification(
            kind=ScanKind.GTIN,
            value=gtin_key,
            raw=scan,
        )

    # Rule 4 is not structural: a vendor item id looks like free text, so it can
    # only be found by looking it up. Resolution tries it after this returns.

    # Rule 5: always matches. Nothing dead-ends.
    return ScanClassification(
        kind=ScanKind.FREE_TEXT,
        value=scan,
        raw=scan,
    )
