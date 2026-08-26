"""What differs between one vendor's order capture and another's.

Feature 029. Order capture was specified and implemented twice -- DigiKey in
feature 024, McMaster-Carr in 028 -- and the two came out near-copies: the
pairing lookup, the per-line review, the confirmation orchestration, the
templates and the routes all written twice with small substitutions. Two of the
defects fixed in review of PR #123 were the McMaster copy of behaviour the
DigiKey copy had already had corrected, which is the cost of that shape and the
reason this module exists.

Everything a vendor is allowed to differ in is here. Everything else is one
implementation on :class:`CatalogService`.

**Why an abstraction is warranted at all**, given Constitution I forbids one for
a single implementation: this is three, two of which have shipped and been
reviewed, so the variation below is *measured* rather than anticipated. The
standing test that the seam is in the right place is FR-037 -- a fourth vendor is
one value here plus a reader. If a future vendor needs a branch inside the shared
flow instead, the seam is wrong and should be re-cut rather than branched.

**Grouped rather than enumerated.** The plan predicted eight points of variation;
reading both implementations end to end found closer to fifteen. Fifteen loose
callables on a dataclass is not the "boring, obvious code" the constitution asks
for, so they are grouped by what they are facts *about* -- the order, the line,
the product -- which brings it back to six members that each mean something.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple


# Where a scan of a delivered package lands when it names more than one
# outstanding line. Not a free-form string: it is compared.
LANDING_ORDER_SCREEN = 'order-screen'
LANDING_CHOICE_PAGE = 'choice-page'


@dataclass(frozen=True)
class OrderVendor:
    """One vendor's half of order capture.

    Callables take the :class:`CatalogService` as their first argument where they
    need its leaf helpers (``_validate_price``, ``_add_identifier``,
    ``_unique_internal_code``). They are plain functions rather than methods on a
    base class deliberately: the variation is data and a few functions, not
    behaviour needing polymorphic dispatch through a deep call tree.
    """

    #: What the catalog files this vendor's purchases under. Compared, so it must
    #: equal what ``_vendor_from_url`` derives and what the agent declares.
    name: str

    #: ``(order) -> dict`` of the Purchase fields this vendor derives from the
    #: *order*: supplier_order_reference, and optionally vendor_order_id,
    #: order_reference and listing_url.
    order_fields: Callable[[Any], Dict[str, Any]]

    #: ``(line) -> str``. The vendor's own id for the item on this line -- a
    #: DigiKey part number, a McMaster part number, an ASIN. Used for pairing a
    #: line to an already-recorded purchase when that purchase carries no line
    #: number, which is the only case where the item id has to stand in for
    #: line identity.
    item_id_of: Callable[[Any], str]

    #: ``(service, session, order) -> list[Purchase]``. Every purchase already
    #: recorded for this order. Its own member because the vendors disagree about
    #: what identifies an order: DigiKey's sales order number is stable, while
    #: McMaster's is the customer's editable Purchase Order string and needs a
    #: two-pass lookup through vendor_order_id first.
    order_purchases: Callable[..., Any]

    #: ``(service, line, decision) -> dict`` of the Purchase fields derived from
    #: the *line*: vendor_item_id, listing_title, quantity, unit_price,
    #: order_line_number. Takes the decision because McMaster lets the operator
    #: overrule the computed quantity and unit price (028 FR-020a).
    line_fields: Callable[..., Dict[str, Any]]

    #: ``(service, session, line) -> (Product | None, bool)``. How a line finds a
    #: product the catalog already holds.
    #:
    #: The bool says whether the match came from the vendor's **own** item id, in
    #: which case a manufacturer part number that contradicts the line's makes it
    #: a CONFLICT rather than a MATCH -- a distributor recycling a part number
    #: for a different part is the most damaging failure in the feature, because
    #: nothing looks wrong afterwards. A match found *by* manufacturer part
    #: number cannot contradict one, so it comes back False.
    find_product: Callable[..., Any]

    #: ``(service, session, line, part, decision, claim_distributor) -> Product``.
    #: Creates the product a line names, **inside the caller's session** -- never
    #: via ``CatalogService.create_product``, which opens its own and would break
    #: the whole-order-or-nothing transaction.
    #:
    #: ``part`` is the vendor's enriched detail where it has any; DigiKey writes
    #: the manufacturer, category, datasheet and parametrics from it. None for
    #: the vendors whose page is the detail, which simply ignore it.
    create_product: Callable[..., Any]

    #: ``(line, part) -> str``. Where the pre-filled label description comes
    #: from: enriched part detail, the page, or the listing title.
    suggested_description: Callable[[Any, Any], str]

    #: Where a scan naming several outstanding lines lands.
    receive_landing: str = LANDING_CHOICE_PAGE

    #: ``(client, lines) -> dict`` keyed by item id. DigiKey only; the other two
    #: have nothing to look up because the page *is* the detail.
    #:
    #: **Called before the write session opens**, always. It is network I/O at up
    #: to ten seconds a call and holding a transaction open across twenty-five of
    #: them is a long-lived lock in exchange for nothing. PR #116 moved a
    #: review's enrichment back out of its session once already.
    enrich: Optional[Callable[..., Dict[str, Any]]] = None

    #: ``(line) -> str | None``. Names a captured line that came back thin, so
    #: the operator knows which records to look over after leaving the review.
    #: DigiKey's thin lines are the ones its part lookup would not answer for;
    #: McMaster's and Amazon's are the ones the *page* did not give up.
    incomplete_label: Optional[Callable[[Any], Optional[str]]] = None

    #: The route that confirms a reviewed order for this vendor. Structural
    #: rather than decorative -- the shared review template posts to it.
    confirm_endpoint: str = ''

    #: Whether the review has to carry the read payload through the confirmation
    #: because the vendor cannot be re-read. True for every vendor read off a
    #: page; False for DigiKey, whose order is re-fetched at confirmation and is
    #: the authority.
    carries_payload: bool = False

    #: Extra columns the review and order screens show. DigiKey has shipped and
    #: backorder counts; McMaster has the pack arithmetic; Amazon has neither.
    review_columns: Tuple[str, ...] = ()

    #: Whether a re-capture must cope with the order having been renamed on the
    #: vendor's side. True only for McMaster, whose order "number" is the
    #: customer's editable Purchase Order string.
    adopts_renames: bool = False

    def __post_init__(self):
        if self.receive_landing not in (LANDING_ORDER_SCREEN, LANDING_CHOICE_PAGE):
            raise ValueError(f"unknown receive_landing {self.receive_landing!r}")


# Populated by app/catalog_service.py at import time, which is where the
# vendor-specific functions live -- they need the service's leaf helpers, and
# moving those here would drag half the service with them. This module owns the
# *shape*; the service owns the behaviour.
REGISTRY: Dict[str, OrderVendor] = {}


def register(vendor: OrderVendor) -> OrderVendor:
    """Add a vendor to the registry, keyed by its name."""
    REGISTRY[vendor.name] = vendor
    return vendor


def for_vendor(name: str) -> Optional[OrderVendor]:
    """The vendor filed under this name, or None.

    None rather than KeyError: a purchase can carry a vendor no order flow knows
    about -- anything recorded by hand -- and an order screen must render it
    rather than 500.
    """
    return REGISTRY.get(name)
