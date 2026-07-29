"""
Merging several ordered suggestion lists into one (Story 5.1, FR27).

This module is the single source of truth for combining the value-suggestion
lists that two different services produced for the SAME public field. It is a
PURE module: standard library only, no Flask/DB/framework imports, no I/O.

It is not, however, total over its arguments: `limit` goes through `int()`, so a
caller passing something that is not int-like (`None`, `'abc'`) gets the
`TypeError`/`ValueError` that raises. Stated rather than swallowed. Both service
callers clamp a bad `limit` to their own default before this is reached, and
that default is theirs to pick — a pure merge has no business inventing a page
size for a caller who asked for an incoherent one, and silently substituting one
would hide the caller's bug instead of surfacing it. Everything else here is
tolerant by design: non-string entries and blanks are skipped, and an empty or
absent source list is simply nothing to merge.

Why this exists at all
----------------------
FR27 wants ONE location vocabulary drawn from two tables — `inventory_items`
(owned by `InventoryService`) and `products` (owned by `CatalogService`). A
`UNION` would put a catalog query inside the item service, and adding `location`
to the catalog dispatch whitelist would silently route ITEM lookups at the
products table (AD-1/AD-2; `tests/unit/test_catalog_service.py` pins the two
whitelists as disjoint for exactly that reason). So each service queries its own
table under the same ordering rule, and this function re-ranks the two already
ordered lists into the single answer one query would have given.

Why re-ranking the truncated lists is not an approximation
----------------------------------------------------------
Each source returns the top-`limit` of its own rows under a TOTAL order that
this function reproduces exactly. Any value one source omitted was beaten there
by `limit` values that source did return, so it is beaten in the union too and
cannot belong in the union's top-`limit`. Taking the top-`limit` of each source
and re-ranking therefore yields exactly the top-`limit` of the union — not
merely a good approximation of it.

The order, which is the endpoint's and not this module's
--------------------------------------------------------
Copied from `InventoryService.get_field_value_suggestions` /
`CatalogService.get_field_value_suggestions`, because a merged answer that
sorted differently from an unmerged one would make the same field behave
differently depending on which tables happened to hold rows:

1. exact match on the (lower-cased) query first, then starts-with, then the
   remaining contains matches — one tier only when there is no query;
2. within a tier, alphabetized case-insensitively;
3. ties broken BYTE-WISE, which is what decides WHICH casing of a value stored
   in several is the one offered. Both services push this key into SQL through
   `db.binary_order_key`; here it is `str.encode('utf-8')`, the same comparison
   SQLite makes natively and the one `COLLATE utf8mb4_bin` makes on MariaDB.

Where that reproduction is exact, and where it is not
-----------------------------------------------------
Exactly, for ASCII values — which is what a location or sub-location is in
practice, and what every test here and in the two services uses.

NOT exactly, for values carrying accents or other non-ASCII letters, and the
equivalence argument above is correspondingly weaker for them. The services
rank in SQL, so on MariaDB tier 1 and tier 2 are evaluated under the column's
`utf8mb4_unicode_ci` collation, which folds accents: `Café` counts as an exact
match for `cafe`, and `É` sorts beside `E`. Python's `str.lower()` folds case
only, so the same value ranks in the `contains` tier and sorts after every
ASCII character. A merged answer can therefore order two values differently
from a single UNION over both tables, and — only when more than `limit` values
match — offer a different one of them. It is a suggestion list and both spellings
remain reachable by typing more of the value, so this is a known and accepted
imprecision rather than a claim of equality; `unicodedata`-based folding here
would be a third, hand-rolled collation to keep in step with two real ones.
SQLite (the unit-test backend) folds neither, so it agrees with this module.

Dedup is case-insensitive and happens AFTER the sort, so the surviving spelling
is the byte-wise-lowest one — the same spelling either service alone would have
offered, rather than an accident of which source was listed first.

    >>> merge_suggestions([['Bin 7', 'Bin 70'], ['bin 7', 'Bin 71']], query='bin')
    ['Bin 7', 'Bin 70', 'Bin 71']

Note what that shows and what it does not: the sources were already FILTERED by
their own services, so nothing here re-checks that a value matches `query`. The
query is a ranking input only. Handing this function a value no source would
have returned puts it in the answer, in the `contains` tier.

The tiers, in order — an exact match outranks a prefix, which outranks a
substring, whatever the alphabet says:

    >>> merge_suggestions([['Shelf'], ['Top Shelf', 'Shelf A']], query='shelf')
    ['Shelf', 'Shelf A', 'Top Shelf']

With no query there is one tier and the answer is simply alphabetical, folded:

    >>> merge_suggestions([['rack 3'], ['Attic', 'Bin 7']])
    ['Attic', 'Bin 7', 'rack 3']

Case-insensitive dedup, byte-wise tiebreak — over ASCII the upper-case spelling
is the binary-lowest, so it is the one that survives:

    >>> merge_suggestions([['bin 7'], ['BIN 7'], ['Bin 7']])
    ['BIN 7']

`limit` truncates the merged answer, never the inputs:

    >>> merge_suggestions([['a', 'c'], ['b', 'd']], limit=3)
    ['a', 'b', 'c']

Blank and whitespace-only entries carry no value and are dropped, and each
surviving value is offered stripped — the same thing both services' read loops
do to their own rows:

    >>> merge_suggestions([['  Attic  ', '', '   '], [None]])
    ['Attic']
"""

from typing import Iterable, List, Optional, Sequence

# The three tiers, in the order they rank. Named so the sort key below reads as
# the contract rather than as three bare integers.
_TIER_EXACT = 0
_TIER_PREFIX = 1
_TIER_CONTAINS = 2


def _tier(folded: str, query: str) -> int:
    """Which ranking tier `folded` (already lower-cased) falls in for `query`.

    Mirrors the `case()` expression both services push into SQL. With no query
    every value is in one tier, so the caller passes `''` and every value ranks
    `_TIER_EXACT` — which is not a claim that it matched, only that the tier key
    is constant and the alphabetical key decides everything.
    """
    if not query:
        return _TIER_EXACT
    if folded == query:
        return _TIER_EXACT
    if folded.startswith(query):
        return _TIER_PREFIX
    return _TIER_CONTAINS


def merge_suggestions(sources: Iterable[Optional[Sequence[Optional[str]]]],
                      query: Optional[str] = None,
                      limit: int = 10) -> List[str]:
    """Merge already-ordered suggestion lists into one ordered, deduped list.

    Args:
        sources: The per-service lists, each already ordered and truncated by
            its own service. Order among the sources is irrelevant — the sort
            below decides everything, which is what keeps the endpoint's answer
            independent of which service happens to be asked first. A None
            source is treated as empty, so a caller that skipped one query does
            not have to substitute a list.
        query: The raw query the sources were filtered by, or None. Compared
            case-insensitively after stripping, exactly as the services compare
            it; a query that strips away means "no filter" and collapses the
            ranking to one alphabetical tier.
        limit: How many values to return. Applied to the MERGED list — the
            sources were each already held to it — and clamped to at least 1,
            because a caller asking for none of something is asking a question
            this endpoint has no way to answer.

    Returns:
        The merged values, stripped, deduped case-insensitively, at most
        `limit` of them.
    """
    q = (query or '').strip().lower()
    limit = max(1, int(limit))

    # Flattened first, deliberately WITHOUT deduping: dedup has to come after
    # the sort or the surviving spelling would be decided by source order
    # instead of by the byte-wise tiebreak.
    values = []
    for source in sources:
        if not source:
            continue
        for value in source:
            if not isinstance(value, str):
                continue
            stripped = value.strip()
            if stripped:
                values.append(stripped)

    # `str.encode('utf-8')` is the byte-wise key: `bytes` compares
    # lexicographically over unsigned bytes, which is what SQLite's native TEXT
    # comparison and MariaDB's `utf8mb4_bin` both do. Only this third key is
    # binary; the second is case-folded, which is what makes two spellings of
    # one value adjacent so the dedup below can keep the binary-lowest of them.
    # Case-folded and nothing more — see the module docstring on where that
    # stops matching a `utf8mb4_unicode_ci` ORDER BY.
    values.sort(key=lambda v: (_tier(v.lower(), q), v.lower(),
                               v.encode('utf-8')))

    seen = set()
    merged = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)
        if len(merged) >= limit:
            break
    return merged
