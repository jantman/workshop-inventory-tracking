"""
Scan classification -- what kind of thing was scanned?

One pure function, six rules, first match wins, and the last rule always
matches. That last property is the whole point: FR-018 and SC-008 require that a
scan never dead-ends, so an unparseable scan is answered with FREE_TEXT carrying
the raw text rather than an exception.

The rules, in order: (1) our own printed code; (2) a distributor's format-06
envelope; (3) a GS1 element string opening with AI 01, whose trade item number
becomes the value rule 4 judges; (4) a check-digit-valid trade item number;
(5) a vendor item id, which is not structural and lives in resolution; (6)
anything else. Rules 3 and 4 share **one** arm on purpose -- see below.

Classification is **structural only**. It takes text and returns a kind; it
performs no database lookup. Turning a kind into a product -- including the two
rules that genuinely need a lookup: a vendor item id such as an ASIN, which has
no distinguishing shape, and a distributor label that names a line of an order
this catalog has captured -- is CatalogService.resolve_scan()'s job.

That second one is why resolution now has four outcomes rather than three. It
changes nothing here: a format-06 envelope is classified ECIA either way, and
what differs is only what resolution does with it.

Every rule delegates its grammar to a sibling parser; this module owns the
precedence and nothing else. Two of those siblings strip their own padding
(``internal_id`` and ``gs1``) and two do not (``ecia`` rstrips newlines only,
``gtin`` strips inside ``normalize``), so tolerance for a wedge's whitespace is
the delegate's business rather than a rule applied here.

Pure module: standard library plus app.models and the sibling app/utils parsers.
No Flask, no database, no config.
"""

from app.models import ScanClassification, ScanKind
from app.utils import ecia, gs1, gtin, internal_id


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
        A ScanClassification. ``raw`` is always the scan as given -- an AIM
        symbology prefix, a transmitted separator and any trailing element
        string are preserved there even though they are ignored for matching.

    Note:
        A manufacturer's 2D barcode and the bare retail barcode it carries
        produce the same ``kind`` and the same ``value``; only ``raw`` differs.

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

    # Rule 3: a manufacturer's own 2D barcode, which carries the retail barcode
    # inside a GS1 element string rather than printing it bare. The extracted
    # digits are UNJUDGED -- rule 4 below decides whether they are a trade item,
    # using the same call a bare barcode goes through, so the two forms cannot
    # diverge (009 FR-002) and a bad one is refused by one rule, not two
    # (009 FR-006).
    #
    # This cannot capture a scan that resolved before feature 009. A match needs
    # at least sixteen characters ('01' plus fourteen digits) and every length
    # gtin.ACCEPTED_LENGTHS admits is 8, 12, 13 or 14 -- disjoint sets, so no
    # bare barcode can reach here. Rules 1 and 2 run first, so an internal code
    # and an envelope cannot either (009 FR-008).
    trade_item = gs1.decode_trade_item_number(scan)

    # Rule 4: a retail barcode, in any of its equivalent lengths.
    gtin_key = gtin.normalize_and_validate(scan if trade_item is None else trade_item)
    if gtin_key is not None:
        return ScanClassification(
            kind=ScanKind.GTIN,
            value=gtin_key,
            raw=scan,
        )

    # Rule 5 is not structural: a vendor item id looks like free text, so it can
    # only be found by looking it up. Resolution tries it after this returns.

    # Rule 6: always matches. Nothing dead-ends.
    return ScanClassification(
        kind=ScanKind.FREE_TEXT,
        value=scan,
        raw=scan,
    )
