"""
The item hand-off -- how a list page names items to a working page.

Four controls hand items across: both Bulk Move Selected buttons and the row
level Move and Shorten actions. They all use one convention, defined in
specs/026-fix-bulk-move-handoff/contracts/handoff.md: a single query parameter
``ja_id`` carrying a comma-separated list, where a single item is a list of one.
Two spellings is the condition that produced the bug this module exists to fix,
so there is deliberately only one.

Two functions, in the order the contract applies them: ``parse_ja_ids`` does the
textual half (split, trim, discard empties, collapse duplicates) and
``resolve_handoff`` does the storage half (accept the active row, reject
everything else *by name*).

Nothing handed off is ever silently dropped. A malformed identifier is reported
as ``not_found`` rather than filtered away, because a hand-off that quietly
loses an item is the original bug in miniature (FR-005). Validation here serves
correctness, not defense: a bad identifier is rejected because it cannot name an
item, not because it might be hostile.
"""

import re
from dataclasses import dataclass, field

# The same shape the Move page's isJaId() applies to a scan, so an identifier
# that the page would refuse from a scanner is refused from a URL too.
_JA_ID = re.compile(r'^JA[0-9]+$')

#: No row carries this JA ID -- or the text is not a JA ID at all.
NOT_FOUND = 'not_found'

#: A row carries this JA ID but it is not the active one. Queueing a historical
#: row for a move would violate the one-active-row-per-JA-ID invariant.
INACTIVE = 'inactive'


@dataclass(frozen=True)
class Handoff:
    """What a hand-off URL asked for, once storage has had its say.

    ``preselected_items`` holds the JA IDs that can be acted on, in payload
    order. The identifier is all a receiving page needs: the Move page resolves
    each item's current location through the existing ``/api/items/{ja_id}``
    endpoint, and the Shorten page prefills a field the user could have typed.
    """

    preselected_items: list = field(default_factory=list)
    rejected_items: list = field(default_factory=list)

    @property
    def has_hand_off(self) -> bool:
        """Whether anything was handed off at all.

        An arrival where every item was rejected must not be indistinguishable
        from a normal empty arrival, so "nothing usable" and "nothing asked for"
        are different answers.
        """
        return bool(self.preselected_items or self.rejected_items)

    @property
    def first_accepted(self) -> str | None:
        """The item a single-item page acts on, or None.

        Shorten handles one item and its row action only ever sends one, so a
        longer list is not an error (contract section 2, step 6).
        """
        return self.preselected_items[0] if self.preselected_items else None


def parse_ja_ids(raw: str | None) -> list[str]:
    """Split the ``ja_id`` parameter into an ordered list of unique elements.

    Contract section 2, steps 1, 2 and 4. Absent or empty yields no hand-off;
    elements are trimmed and empties discarded; duplicates collapse to their
    first occurrence so the queue reads in the order the user saw on the list.

    Elements are *not* filtered by shape here -- that is step 3, and it produces
    a rejection to report rather than a value to drop.
    """
    if not raw:
        return []

    ordered: list[str] = []
    for element in raw.split(','):
        element = element.strip()
        if element and element not in ordered:
            ordered.append(element)
    return ordered


def resolve_handoff(raw: str | None, service) -> Handoff:
    """Resolve a ``ja_id`` parameter against storage.

    Contract section 2, steps 3 and 5. Each element is accepted if it names an
    active row, and otherwise rejected with the reason that fits: ``inactive``
    when the JA ID exists but the row is historical, ``not_found`` when it names
    nothing -- including when it is not a JA ID at all.

    Args:
        raw: The raw ``ja_id`` query parameter, or None when there was none.
        service: An InventoryService, used only through ``get_active_item`` and
            ``ja_id_exists`` so no query is written into a route.
    """
    preselected: list[str] = []
    rejected: list[dict] = []

    for ja_id in parse_ja_ids(raw):
        if not _JA_ID.match(ja_id):
            rejected.append({'ja_id': ja_id, 'reason': NOT_FOUND})
        elif service.get_active_item(ja_id) is not None:
            preselected.append(ja_id)
        elif service.ja_id_exists(ja_id, only_active=False):
            rejected.append({'ja_id': ja_id, 'reason': INACTIVE})
        else:
            rejected.append({'ja_id': ja_id, 'reason': NOT_FOUND})

    return Handoff(preselected_items=preselected, rejected_items=rejected)
