"""
The shared location and vendor vocabulary.

Both halves of the application record the same kinds of names -- a shelf, a bin,
a vendor -- and they should offer each other what they already know rather than
drifting apart by spelling. This is where "what has been typed before" is
answered for both.

The vocabulary is derived, never curated: there is no table of approved names, no
publishing step, and no way to add one except by recording it on something. That
is the same shape categories already have, and it is why a name recorded on a
product is offered on the Add Item form with nothing in between.

Ranking, LIKE-escaping and case-insensitive deduplication were moved here from
``MariaDBInventoryService`` unchanged. What is new is that ``location``,
``sub_location`` and ``vendor`` read the catalog's columns as well as metal
stock's.
"""

from typing import Any, List, Optional, Tuple

from sqlalchemy import case, create_engine, func
from sqlalchemy.orm import sessionmaker

from ..database import InventoryItem, Product, Purchase
from ..mariadb_storage import MariaDBStorage
from ..utils.sql import escape_like
from config import Config


# Whitelist of fields exposed for value-suggestion autocomplete.
#
# Keys are the public field names accepted in API paths; values are the
# ``(model, value column, location column)`` sources that contribute. The
# location column is only consulted for ``sub_location``, where a suggestion is
# scoped to the location already typed -- and each source is scoped against its
# own location column, never the other's.
#
# ``thread_size`` and ``purchase_location`` stay single-source because nothing in
# the catalog records either. Adding a source is a line in this table.
FIELD_SUGGESTION_COLUMNS = {
    'thread_size': (
        (InventoryItem, 'thread_size', None),
    ),
    'purchase_location': (
        (InventoryItem, 'purchase_location', None),
    ),
    'vendor': (
        (InventoryItem, 'vendor', None),
        (Purchase, 'vendor', None),
    ),
    'location': (
        (InventoryItem, 'location', None),
        (Product, 'location', None),
    ),
    'sub_location': (
        (InventoryItem, 'sub_location', 'location'),
        (Product, 'sub_location', 'location'),
    ),
}


# Kept as a module-level name so this file's existing call sites read unchanged.
# The rule itself lives in app/utils/sql.py because the catalog needs it too.
_escape_like = escape_like


class VocabularyService:
    """Distinct values already recorded, for autocompleting free-form fields."""

    def __init__(self, storage: MariaDBStorage = None) -> None:
        """Initialize with a MariaDB storage backend.

        Args:
            storage: The storage backend to borrow an engine from. A new
                MariaDBStorage is built from config when omitted.
        """
        if storage is None:
            storage = MariaDBStorage()

        self.storage = storage
        self.engine = storage.engine or self._create_engine()
        self.Session = sessionmaker(bind=self.engine)

    def _create_engine(self):
        """Create a database engine when the storage backend has none"""
        return create_engine(
            Config.SQLALCHEMY_DATABASE_URI,
            **Config.SQLALCHEMY_ENGINE_OPTIONS
        )

    def suggest(
        self,
        field: str,
        query: Optional[str] = None,
        limit: int = 10,
        location: Optional[str] = None,
    ) -> List[str]:
        """
        Return distinct existing values for a whitelisted field, suitable
        for autocomplete on the metal stock and catalog forms.

        Pulls DISTINCT values across every table that records the field,
        including inactive ``inventory_items`` history rows so deactivated
        items still seed suggestions. NULL and empty values are excluded.
        Comparisons are case-insensitive.

        Filtering, ordering, and the limit are pushed into SQL per source
        so each contributes at most ``limit`` rows (plus a small headroom
        for case-insensitive deduplication). Sources are then merged and
        re-ranked as a whole, so a better match from either source
        outranks a worse one from the other.

        Ordering when ``query`` is supplied: exact match first, then
        starts-with matches, then contains matches, each tier
        alphabetized (case-insensitive).

        Ordering when ``query`` is omitted: alphabetized
        (case-insensitive).

        Args:
            field: One of the keys in ``FIELD_SUGGESTION_COLUMNS``. Any
                other value raises ``ValueError``.
            query: Optional case-insensitive substring filter. When None
                or empty, returns ``limit`` distinct values in
                alphabetical order.
            limit: Maximum number of suggestions to return. Clamped to
                [1, 50].
            location: Only meaningful when ``field == 'sub_location'``.
                When provided, restricts results to sub-locations that
                appear under that location (case-insensitive), applied
                per source against that source's own location column.

        Returns:
            List of distinct value strings.

        Raises:
            ValueError: if ``field`` is not whitelisted.
        """
        sources = FIELD_SUGGESTION_COLUMNS.get(field)
        if sources is None:
            raise ValueError(f"Unsupported field for suggestions: {field!r}")

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))

        q = (query or '').strip().lower()

        # Note: unexpected exceptions are intentionally not swallowed
        # here. The route wrapper catches Exception and returns HTTP
        # 500 with the documented error response; swallowing here would
        # silently convert a backend failure into a 200 with an empty
        # suggestion list, breaking the documented status-code contract.
        session = self.Session()
        try:
            values: List[str] = []
            for model, column_name, location_column_name in sources:
                values.extend(self._source_values(
                    session, model, column_name, location_column_name,
                    q, limit, location,
                ))

            return self._rank_and_dedupe(values, q, limit)
        finally:
            session.close()

    def _source_values(
        self,
        session,
        model: Any,
        column_name: str,
        location_column_name: Optional[str],
        q: str,
        limit: int,
        location: Optional[str],
    ) -> List[str]:
        """Ranked, filtered values from one table's one column."""
        column = getattr(model, column_name)

        base = session.query(column).filter(
            column.isnot(None),
            func.trim(column) != '',
        )

        if location_column_name and location:
            # Each source is scoped against its own location column: a
            # product's sub-location belongs under the product's location,
            # not under some inventory item's.
            location_column = getattr(model, location_column_name)
            base = base.filter(
                func.lower(location_column) == func.lower(location)
            )

        if q:
            pattern = f'%{_escape_like(q)}%'
            base = base.filter(
                func.lower(column).like(pattern, escape='\\')
            )
            rank = case(
                (func.lower(column) == q, 0),
                (func.lower(column).like(
                    f'{_escape_like(q)}%', escape='\\'
                ), 1),
                else_=2,
            )
            base = base.order_by(rank, func.lower(column))
        else:
            base = base.order_by(func.lower(column))

        # Over-fetch slightly to give the post-DB case-insensitive
        # dedup pass headroom: the DB DISTINCT depends on the
        # column's collation, so two values differing only in case
        # may both reach Python.
        fetch_limit = limit * 3 + 10
        rows = base.distinct().limit(fetch_limit).all()
        return [
            row[0].strip()
            for row in rows
            if row[0] and row[0].strip()
        ]

    def _rank_and_dedupe(
        self, values: List[str], q: str, limit: int
    ) -> List[str]:
        """Merge several sources into one ranked, deduplicated list.

        Re-ranking here rather than trusting each source's own order is what
        makes multi-source results coherent: an exact match recorded on a
        product must outrank a contains-match recorded on a metal stock item.

        Deduplication is case-insensitive across sources, so ``Amazon`` on an
        item and ``amazon`` on a purchase offer one suggestion. The first
        spelling under the established ordering is the one kept.
        """
        def sort_key(value: str) -> Tuple[int, str]:
            lowered = value.lower()
            if not q:
                return (0, lowered)
            if lowered == q:
                return (0, lowered)
            if lowered.startswith(q):
                return (1, lowered)
            return (2, lowered)

        seen_lower = set()
        unique = []
        for value in sorted(values, key=sort_key):
            key = value.lower()
            if key in seen_lower:
                continue
            seen_lower.add(key)
            unique.append(value)

        return unique[:limit]
