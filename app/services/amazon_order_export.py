"""Reduce an Amazon order-history export to the orders it names.

Feature 031. Backfilling Amazon is a selection problem before it is a capture
problem: DigiKey and McMaster sell nothing that is not a workshop item, but an
Amazon account is the household's, and the thirty orders worth cataloging are
buried in groceries, books and birthday presents. Amazon's *Request Your Data*
export exists to make that filtering possible away from the browser -- the
operator deletes the rows they do not want -- and this turns what is left into
the addresses to open.

**The export states one row per item.** An eleven-item order therefore appears
eleven times, and opening it eleven times would be eleven captures of the same
order. Reducing that to distinct orders is the whole job, and it is written down
here rather than retyped as a shell one-liner per backfill because it is exactly
the kind of step that is easy to get quietly wrong.

**Two columns are required, not twenty-seven.** Amazon has already renamed this
export at least once -- issue #125 refers to ``Your Amazon Orders/Order
History.csv`` and recent exports ship ``Retail.OrderHistory.1.csv`` -- so
matching the whole published schema would make their next change this project's
problem. ``Order ID`` and ``Website`` are what an address needs; everything else
is read only if it happens to be there.

**Nothing here parses a price.** Constitution III is not at risk because no
monetary value is read at all: prices come off the order page at capture, the
way they always have.

Pure. No Flask, no ORM, no network, no filesystem -- the caller opens the file.
"""

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app.exceptions import ValidationError

#: What an address cannot be built without.
REQUIRED_COLUMNS = ('Order ID', 'Website')

#: Read when present, for the summary only.
STATUS_COLUMN = 'Order Status'

#: The shape the capture agent recognizes, from
#: ``app/static/js/capture-agent.js``'s ``AMAZON_ORDER_ID_PATTERN``. Amazon's
#: digital orders (``D01-...``) live in a different file of the export and are
#: filtered out by this for free, which is the right outcome -- they are not
#: physical goods and there is nothing to receive.
ORDER_ID_PATTERN = re.compile(r'^\d{3}-\d{7}-\d{7}$')

#: The legacy address. The capture agent's own comment records that it 302s to
#: the canonical ``/your-orders/order-details`` path it runs on, and it is the
#: shorter, stabler thing to write into a file of thirty links.
ORDER_URL_TEMPLATE = 'https://{website}/gp/css/order-details?orderID={order_id}'

_SCHEME = re.compile(r'^https?://', re.IGNORECASE)


@dataclass(frozen=True)
class AmazonExportOrder:
    """One order the export names, however many item rows it contributed."""

    order_id: str
    website: str
    row_count: int = 1

    @property
    def url(self) -> str:
        """Where to open it.

        Built from the row's **own** ``Website``: an export can hold
        ``amazon.co.uk`` orders beside ``amazon.com`` ones, and an order id only
        means anything against the site that issued it. Assuming one host would
        produce dead links rather than an error.
        """
        return ORDER_URL_TEMPLATE.format(
            website=self.website, order_id=self.order_id
        )


@dataclass(frozen=True)
class AmazonExportSummary:
    """What one run found. Nothing here reaches the catalog."""

    orders: Tuple[AmazonExportOrder, ...] = ()
    rows_read: int = 0
    rows_unusable: int = 0
    #: ``(status, order count)`` over the orders being emitted, most common
    #: first. **Reported, never filtered** -- the operator's edit of the file is
    #: authoritative, and deciding for them which statuses are worth capturing
    #: would be a knob for a judgement they have already made.
    status_counts: Tuple[Tuple[str, int], ...] = ()

    def render(self) -> str:
        """The summary, as the command prints it.

        A file edited down to four rows that yields one order has to be visibly
        that rather than passing for a short history, which is why the counts are
        stated on every run and not only on a suspicious one.
        """
        lines = [
            f"Read {self.rows_read} row(s); "
            f"{len(self.orders)} distinct order(s)."
        ]
        if self.rows_unusable:
            lines.append(
                f"{self.rows_unusable} row(s) carried an order id this could "
                f"not use — digital orders and blank rows are expected here."
            )
        if len(self.status_counts) > 1:
            seen = ", ".join(f"{s} ({n})" for s, n in self.status_counts)
            lines.append(
                f"Order statuses seen: {seen}. Nothing was dropped — check any "
                f"cancelled or returned order before you capture it."
            )
        return "\n".join(lines)


def summarize(
    rows: Iterable[Mapping[str, str]],
    fieldnames: Optional[Sequence[str]] = None,
) -> AmazonExportSummary:
    """Reduce export rows to the distinct orders they name.

    Args:
        rows: What ``csv.DictReader`` yields over the operator's edited export.
        fieldnames: The file's header row, where the caller has it --
            ``csv.DictReader.fieldnames``. **Pass it.** A file edited down to
            its header alone yields no rows, so the columns cannot be seen from
            the rows, and a correctly-shaped file the operator emptied would
            otherwise be refused as unrecognizable. Absent, the first row's keys
            are used, and a file with neither is simply empty.

    Returns:
        The orders, in **first-seen order** -- the file's own order, which is
        the one the operator was just looking at when they edited it.

    Raises:
        ValidationError: The file does not carry the columns an address needs.
            Raised rather than returning a short list, because a partial result
            is indistinguishable from a successful run over a small file.
    """
    rows = list(rows)
    _require_columns(rows, fieldnames)

    by_id: Dict[str, List] = {}
    order_ids: List[str] = []
    statuses: Dict[str, str] = {}
    rows_read = 0
    rows_unusable = 0

    for row in rows:
        rows_read += 1
        order_id = (row.get('Order ID') or '').strip()
        if not ORDER_ID_PATTERN.match(order_id):
            rows_unusable += 1
            continue

        if order_id not in by_id:
            by_id[order_id] = [_website(row), 0]
            order_ids.append(order_id)
            statuses[order_id] = (row.get(STATUS_COLUMN) or '').strip()
        by_id[order_id][1] += 1

    orders = tuple(
        AmazonExportOrder(
            order_id=order_id,
            website=by_id[order_id][0],
            row_count=by_id[order_id][1],
        )
        for order_id in order_ids
    )

    return AmazonExportSummary(
        orders=orders,
        rows_read=rows_read,
        rows_unusable=rows_unusable,
        status_counts=_status_counts(statuses),
    )


def _require_columns(
    rows: List[Mapping[str, str]], fieldnames: Optional[Sequence[str]]
) -> None:
    """Refuse a file whose shape this does not recognize, naming what is missing."""
    if fieldnames is not None:
        present = set(fieldnames)
    elif rows:
        present = set(rows[0].keys())
    else:
        # Nothing to read and nothing to disbelieve. An empty result is the
        # honest answer; the caller passes fieldnames when it wants the
        # header-only case caught.
        return

    missing = [name for name in REQUIRED_COLUMNS if name not in present]
    if not missing:
        return

    found = ", ".join(sorted(k for k in present if k)) or "none"
    raise ValidationError(
        "This does not look like an Amazon order-history export: no "
        + " or ".join(f'"{name}"' for name in missing)
        + f" column. Columns found: {found}",
        field='Order ID',
    )


def _website(row: Mapping[str, str]) -> str:
    """The host to build this row's address against."""
    website = _SCHEME.sub('', (row.get('Website') or '').strip()).strip('/')
    return website or 'www.amazon.com'


def _status_counts(statuses: Mapping[str, str]) -> Tuple[Tuple[str, int], ...]:
    """How many orders carry each status, most common first."""
    counts: Dict[str, int] = {}
    for status in statuses.values():
        if status:
            counts[status] = counts.get(status, 0) + 1
    return tuple(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
