"""
MariaDB Catalog Service

Business logic for the product catalog (Products, and — in later epics —
identifiers, scan resolution, search, capture, derived stock signals). All
catalog queries and mutations go through this service (AD-2); routes contain no
ORM/SQL and build the HTTP response themselves.

Story 1.3 introduces the create / read / update surface for Products; Story 2.4
makes create_product the sole writer of the generated internal_id. Later stories
extend this class (scan resolution, search_products, capture, derived signals).
"""

import logging
from collections.abc import Mapping
from typing import Dict, List, Optional, Tuple
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import sessionmaker, defer
from sqlalchemy import create_engine, case, exists, func, or_
from sqlalchemy.exc import IntegrityError

from .database import Product, Purchase, Attachment, ProductIdentifier, ProductTag
from .models import (IdentifierType, ScanKind, ScanResolution,
                     VENDOR_SCOPED_IDENTIFIER_TYPES)
from .mariadb_storage import MariaDBStorage
from .exceptions import ValidationError
from .utils import gtin, gs1
from .utils import category as category_util
from .utils import internal_id as internal_id_util
from .utils import scan_router
from .utils import tag as tag_util
from config import Config

# The logger setup_logging() already configures for this module.
logger = logging.getLogger('mariadb_catalog_service')


# Product fields the create/update surface accepts. internal_id is deliberately
# ABSENT (Story 2.4): it is assigned once by create_product and is immutable, so
# update_product silently ignores any attempt to change it.
_PRODUCT_FIELDS = (
    'manufacturer', 'mpn', 'description', 'notes', 'category_path', 'attributes',
)

# How many internal-id candidates create_product will try before giving up
# (Story 2.4, AD-8). The candidate space is ~1.1e15, so a single collision is
# already vanishingly unlikely; this budget exists so a pathological or
# mis-seeded generator fails loudly instead of looping forever.
INTERNAL_ID_MAX_ATTEMPTS = 5

# Attachment policy (Story 1.5). Whitelist is enforced only here (single source
# of truth); the DB carries the structural XOR + positive-size CHECKs.
# image/svg+xml is deliberately excluded (script-carrying → inline-XSS vector).
ATTACHMENT_ALLOWED_TYPES = {
    'application/pdf', 'image/jpeg', 'image/png', 'image/webp', 'image/gif',
}
# Exact MEDIUMBLOB ceiling: 2**24 - 1 bytes. Using the full column capacity
# while rejecting anything the DB can't store (so oversize surfaces as a clean
# ValidationError, never a raw DB error at insert time).
ATTACHMENT_MAX_SIZE = 16 * 1024 * 1024 - 1
ATTACHMENT_MAX_FILENAME = 255  # matches the filename column length

# Identifier bounds (Story 2.1). Guarded here as ValidationErrors before any DB
# write so oversize surfaces cleanly, never as a raw DataError at flush time
# (SQLite silently stores overlong strings; MariaDB strict mode rejects them).
IDENTIFIER_MAX_LENGTH = 255  # matches the value / vendor_scope column lengths

# Catalog-side whitelist of fields exposed for value-suggestion autocomplete
# (Stories 3.1, 3.3). Deliberately shaped exactly like
# InventoryService.FIELD_SUGGESTION_COLUMNS — public field name -> column
# attribute name (see _FIELD_SUGGESTION_MODELS for the class it lives on) — so
# the ONE endpoint
# (/api/inventory/field-suggestions/<field>) can dispatch on membership without
# a second URL or a parallel field set (AD-14). No products query belongs in
# the inventory service, which is why this lives here rather than there
# (AD-1/AD-2).
FIELD_SUGGESTION_COLUMNS = {
    'category_path': 'category_path',
    'tags': 'tag',
}

# Which mapped class each whitelisted field's column lives on. Product is the
# default because the whitelist began as Product columns alone; `tags` (Story
# 3.3) is the first entry sourced from a child table, and resolving the class
# here is what lets FIELD_SUGGESTION_COLUMNS stay a flat field -> column-name
# map that the ONE endpoint can still dispatch on by membership.
_FIELD_SUGGESTION_MODELS = {
    'tags': ProductTag,
}

# How many tags a collision message may name before it starts summarizing. A
# flash listing every one of MAX_TAGS_PER_PRODUCT (50) tags is not actionable.
MAX_TAGS_NAMED_IN_ERROR = 8

# Free-text search bounds (Story 4.3, AD-17). No requirement caps the number of
# results a search may return, so this bound is a deliberate choice rather than
# a stated one: every sibling listing method in this class fetches unbounded
# (deferred-work ledger, "catalog vocabulary listings and the tag filter result
# page fetch and render without any bound"), and a scan fallthrough that
# materializes the whole catalog into a UI list would be that same defect with a
# new entry point. Epic 8 owns paging, which is what makes a larger result set
# navigable rather than merely fetched; until then the default is what one
# screen of scan results can usefully show and the max is the ceiling a caller
# may ask for.
SEARCH_RESULTS_DEFAULT_LIMIT = 50
SEARCH_RESULTS_MAX_LIMIT = 200

# Longest query search_products will build a LIKE pattern from. Not a cleaning
# rule and not a second copy of the route's scan trim (`MAX_SCAN_LENGTH` stays
# in app/main/routes.py): it is a database-safety bound, because a LIKE pattern
# has a length limit that a search box has no reason to respect. SQLite raises
# `OperationalError: LIKE or GLOB pattern too complex` past
# SQLITE_MAX_LIKE_PATTERN_LENGTH (50000, and escaping doubles the query's
# metacharacters on the way there), which would break NFR8's "no scan text
# raises" on the only backend the suite runs. 4096 is far under that on both
# backends and coincides with the route's own scan cap, so no scan can reach it.
SEARCH_QUERY_MAX_LENGTH = 4096


def _clean(value):
    """Trim strings and coerce blank strings to None (backfill-forward: absent
    optional fields must store NULL, not '')."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _escape_like_wildcards(value: str) -> str:
    """
    Escape the LIKE metacharacters in user-supplied text against `\\`.

    So a query like `10%` matches the literal string `10%` instead of acting as
    a wildcard. Every caller must pass the same escape character to
    SQLAlchemy's `.like(..., escape='\\')`.

    Module-level rather than nested in one method because this file now has two
    callers (`get_field_value_suggestions` and `search_products`) and the
    ledger already records LIKE escaping as duplicated between this file and
    `app/utils/category.py`'s `descendant_like_pattern`; a third independent
    copy inside one module is the version of that defect worth not writing.
    (Kept local to this file rather than imported from the inventory side, so
    neither service has to import the other across the AD-1 seam.)
    """
    return (
        value.replace('\\', '\\\\')
        .replace('%', '\\%')
        .replace('_', '\\_')
    )


def _is_storable_text(value: str) -> bool:
    """
    Whether `value` can reach the database intact and mean what it says
    (Story 4.3, NFR8). Two character classes make that false:

    - An UNPAIRED SURROGATE, which Python permits in a `str` but which has no
      UTF-8 encoding, so a driver raises `UnicodeEncodeError` when binding it
      as a parameter. A caller that must not raise on arbitrary text has to
      answer such a query without querying.
    - A NUL (`\\x00`). It binds without error, but SQLite's `LIKE` reads its
      pattern as a C string and stops at the first NUL, so the pattern that
      actually runs is a PREFIX of the one built — and since every pattern
      here is wrapped in `%…%`, a leading NUL degenerates to the bare `%` that
      matches EVERY row. Verified: with five products stored,
      `search_products('\\x00')` returned all five, and `'a\\x00b'` ran as
      `'%a'` and returned the rows *ending* in `a`. Both are the silent
      wrong-answer failure that `search_products`' length bound refuses to
      make by truncating; NUL was making it one character class over. The
      divergence is backend-specific in the direction the unit suite cannot
      see — PyMySQL escapes `\\0` in the emitted literal, so MariaDB compares
      the whole pattern and answers nothing.

    In both cases the honest answer is the no-match one, reached without a
    query: no value this application stores can equal or contain text that
    cannot be sent or cannot be compared whole.

    The surrogate half is observed under SQLite, the only backend any test in
    this repo runs `CatalogService` against; PyMySQL encodes bound parameters
    to the connection charset and is expected to raise the same way, but that
    is inferred rather than measured, and the absent MariaDB coverage is an
    open ledger entry.
    """
    if '\x00' in value:
        return False
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True


class CatalogService:
    """Service for managing catalog Products through the MariaDB backend."""

    def __init__(self, storage: MariaDBStorage = None):
        """Initialize with MariaDB storage."""
        if storage is None:
            storage = MariaDBStorage()

        self.storage = storage

        # Direct database access for queries (same pattern as InventoryService).
        self.engine = getattr(storage, 'engine', None) or self._create_engine()
        self.Session = sessionmaker(bind=self.engine)

    def _create_engine(self):
        """Create database engine if not provided by storage."""
        return create_engine(
            Config.SQLALCHEMY_DATABASE_URI,
            **Config.SQLALCHEMY_ENGINE_OPTIONS
        )

    def get_product(self, product_id: int) -> Optional[Product]:
        """
        Return the Product with the given surrogate id, or None if not found.

        None strictly means "no such product" — database errors propagate to
        the caller (and Flask's error handlers) rather than masquerading as
        not-found. This is a read-only query (no commit), so the returned
        detached ORM object's scalar columns stay readable after the session
        closes. Do not access relationship attributes (e.g. .purchases) on the
        result — that would lazy-load on a detached instance (Story 1.4
        concern).
        """
        session = self.Session()
        try:
            return session.query(Product).filter(Product.id == product_id).first()
        finally:
            session.close()

    def _internal_id_is_taken(self, session, candidate: str) -> bool:
        """
        Return True if `candidate` is already held by a Product or by an
        INTERNAL identifier row (Story 2.4).

        Used to classify an IntegrityError raised while inserting a new
        Product: only a genuine collision on one of those two unique
        constraints justifies a retry. Must run after the failed flush has been
        rolled back, so the session can query again.
        """
        if (session.query(Product)
                .filter(Product.internal_id == candidate).first()) is not None:
            return True
        # Matches the unique constraint exactly — (type, value, vendor_scope) —
        # so a row that could not have caused this flush to fail is never read
        # as a collision (which would burn the retry budget and hide the real
        # integrity error behind a fabricated one). INTERNAL is global, so the
        # scope the derived row is written with is always ''.
        return (session.query(ProductIdentifier)
                .filter_by(identifier_type=IdentifierType.INTERNAL.value,
                           value=candidate, vendor_scope='')
                .first()) is not None

    def create_product(self, *, manufacturer=None, mpn=None, description=None,
                        notes=None, category_path=None, attributes=None) -> Optional[int]:
        """
        Create a Product and return its new integer id, or None on failure.

        Every field is optional except the caller's own required-field policy
        (the route requires a Label Description); blank strings are coerced to
        NULL. Returns the id (captured before the session closes) rather than
        the ORM object to avoid detached-attribute access downstream.

        This is the SOLE writer of products.internal_id (Story 2.4, AD-8). It
        draws a candidate from the pure generator, writes the Product AND its
        derived INTERNAL ProductIdentifier row (global scope, same value) on one
        session, and lets the UNIQUE constraints arbitrate: a collision rolls the
        whole attempt back and retries with a fresh candidate, so either both
        rows land or neither does. An IntegrityError that is NOT a collision on
        that candidate is re-raised rather than mislabelled. Exhausting
        INTERNAL_ID_MAX_ATTEMPTS falls into the established failure contract
        below (audit-log 'error', return None) having written nothing.
        """
        from .logging_config import log_audit_operation
        try:
            session = self.Session()
            for attempt in range(INTERNAL_ID_MAX_ATTEMPTS):
                candidate = internal_id_util.generate_internal_id()
                product = Product(
                    internal_id=candidate,
                    manufacturer=_clean(manufacturer),
                    mpn=_clean(mpn),
                    description=_clean(description),
                    notes=_clean(notes),
                    # Story 3.1: create_product and update_product are the only
                    # writers of category_path, so normalizing here (and only
                    # here) is what makes "every stored path is canonical or
                    # NULL" true. normalize_category_path subsumes _clean for
                    # this field — blank normalizes to None.
                    category_path=category_util.normalize_category_path(category_path),
                    attributes=attributes,
                )
                session.add(product)
                # The derived read index (FR7): same transactional step, same
                # value, global scope (INTERNAL is not vendor-scoped, AD-9).
                # Linking by relationship lets the one flush assign the FK.
                session.add(ProductIdentifier(
                    product=product,
                    identifier_type=IdentifierType.INTERNAL.value,
                    value=candidate,
                    vendor_scope='',
                ))
                try:
                    # Flush (assigns the PK, fires column defaults) and capture
                    # the id and audit snapshot BEFORE commit: a post-commit
                    # attribute access triggers a refresh SELECT that can fail
                    # even though the row was committed, which would falsely
                    # report failure and invite a duplicate-creating retry.
                    session.flush()
                    break
                except IntegrityError:
                    # Roll the whole attempt back (Product AND identifier), then
                    # confirm the candidate really is taken. If it is not, this
                    # was some other integrity failure — re-raise it rather than
                    # retry forever against a condition retrying cannot fix.
                    session.rollback()
                    if not self._internal_id_is_taken(session, candidate):
                        raise
                    # A real collision is a ~1-in-1.1e15 event, so even one is
                    # worth a line: retrying silently means a degenerate
                    # generator (a truncated ALPHABET, a monkeypatch left in
                    # place, a shortened length) shows up only as the eventual
                    # exhausted-retry failure, with nothing recorded about the
                    # near misses that led there. The audit log carries only
                    # 'success' on the attempt that lands.
                    logger.warning(
                        'internal_id collision on attempt %d/%d (candidate %r '
                        'already in use); retrying with a fresh candidate',
                        attempt + 1, INTERNAL_ID_MAX_ATTEMPTS, candidate)
            else:
                raise RuntimeError(
                    f'Could not generate a unique internal_id after '
                    f'{INTERNAL_ID_MAX_ATTEMPTS} attempts.')
            new_id = product.id
            audit_snapshot = product.to_dict()
            # The retry loop covers flush-time failures only, which is where
            # both backends surface a UNIQUE violation: MariaDB/InnoDB and
            # SQLite evaluate these constraints per statement, not deferred to
            # COMMIT. A collision raised here instead would fall to the generic
            # handler below (audit 'error', return None) rather than retrying —
            # correct, just less forgiving. Revisit if a deferred-constraint
            # backend is ever introduced.
            session.commit()
            log_audit_operation('create_product', 'success', item_id=str(new_id),
                                item_after=audit_snapshot,
                                logger_name='mariadb_catalog_service')
            return new_id
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            log_audit_operation('create_product', 'error',
                                error_details=str(e), logger_name='mariadb_catalog_service')
            return None
        finally:
            if 'session' in locals():
                session.close()

    def update_product(self, product_id: int, **fields) -> bool:
        """
        Update the given Product's fields. Returns True on success, False if the
        product does not exist or the update fails. Only recognized product
        fields are applied; blank strings become NULL. `updated_at` is bumped
        automatically by the model's onupdate.

        Together with create_product this is one of the only two writers of
        products.category_path, so a supplied value is canonicalized through
        app/utils/category.py on the way in (Story 3.1) — see the field loop.
        """
        from .logging_config import log_audit_operation
        try:
            session = self.Session()
            product = session.query(Product).filter(Product.id == product_id).first()
            if product is None:
                log_audit_operation('update_product', 'error', item_id=str(product_id),
                                    error_details='Product not found',
                                    logger_name='mariadb_catalog_service')
                return False

            for key, value in fields.items():
                if key not in _PRODUCT_FIELDS:
                    continue
                if key == 'attributes':
                    cleaned = value
                elif key == 'category_path':
                    # Story 3.1: the other write path onto category_path, so it
                    # canonicalizes too (a blank still clears to NULL — that is
                    # normalize's own contract, not a special case here). A key
                    # ABSENT from `fields` is untouched, as before.
                    cleaned = category_util.normalize_category_path(value)
                else:
                    cleaned = _clean(value)
                setattr(product, key, cleaned)

            # Flush and snapshot before commit (see create_product).
            session.flush()
            audit_snapshot = product.to_dict()
            session.commit()
            log_audit_operation('update_product', 'success', item_id=str(product_id),
                                item_after=audit_snapshot,
                                logger_name='mariadb_catalog_service')
            return True
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            log_audit_operation('update_product', 'error', item_id=str(product_id),
                                error_details=str(e), logger_name='mariadb_catalog_service')
            return False
        finally:
            if 'session' in locals():
                session.close()

    # --- Field-value suggestions (Story 3.1) ------------------------------

    def normalize_suggestion_value(self, field: str, value) -> Optional[str]:
        """
        Return the canonical form of a raw suggestion query for a catalog
        field, or None when it carries nothing (Story 3.1, FR14).

        This is what the endpoint echoes back as `normalized`, and it is the
        create affordance's source of truth: the browser displays the string
        that would actually be STORED if the operator accepted the create,
        instead of reimplementing normalization in JavaScript where it could
        silently drift from app/utils/category.py (AD-4).

        An over-length query cannot become a stored path, so it yields None
        (no create offered) rather than raising — a suggestion lookup is a
        read, and a rejected query is nothing the operator could create.
        Note this is the ECHO only: `get_field_value_suggestions` treats the
        same query as unmatchable and returns no rows, rather than reading
        the None as "no filter".

        Args:
            field: One of the keys in the module-level
                FIELD_SUGGESTION_COLUMNS. Any other value raises ValueError,
                mirroring get_field_value_suggestions.
            value: The raw query as typed, or None.

        Returns:
            The canonical value, or None.

        Raises:
            ValueError: if `field` is not whitelisted.
            NotImplementedError: if `field` IS whitelisted but has no
                normalizer registered below — a wiring error, not a request
                error, so it is deliberately not the route's 400 path.
        """
        if FIELD_SUGGESTION_COLUMNS.get(field) is None:
            raise ValueError(f"Unsupported field for suggestions: {field!r}")
        if field == 'category_path':
            try:
                return category_util.normalize_category_path(value)
            except category_util.InvalidCategoryPathError:
                return None
        if field == 'tags':
            # The input carries a LIST, but only the fragment after the last
            # separator is ever sent as `q` (the multi-value autocomplete
            # option), so the echo is the canonical form of ONE tag. An
            # over-length or comma-bearing query cannot become a stored tag,
            # so it yields None and no create is offered — same rule as an
            # unstorable category path.
            try:
                return tag_util.normalize_tag(value)
            except tag_util.InvalidTagError:
                return None
        # Deliberately loud rather than a plausible-looking fallback: a further
        # catalog field needs its OWN normalizer here. Falling back to _clean
        # would echo a non-canonical value, which get_field_value_suggestions
        # lowercases anyway and which the browser's create check assumes is
        # already canonical.
        raise NotImplementedError(
            f'No suggestion normalizer registered for {field!r}')

    def get_field_value_suggestions(
        self,
        field: str,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> List[str]:
        """
        Return distinct existing values for a whitelisted catalog field,
        suitable for autocomplete on the product Add/Edit forms (FR14, FR15).

        The category "tree" IS the distinct set of assigned
        products.category_path values — there is no node table — so this
        DISTINCT query is the whole vocabulary source. It accretes purely from
        use: nothing is offered until some product carries it, and ancestors
        are not synthesized (typing `a/b/c` makes `a/b/c` available, not bare
        `a`). The tag vocabulary (Story 3.3, `tags`) works the same way over
        product_tags.tag: there is no vocabulary table, and a tag stops being
        offered when the last product drops it.

        (Both orderings sort on LOWER(category_path) and a filtered lookup is
        a leading-wildcard LIKE, so neither can use the column's index — this
        scans, which is fine at this table's size. The index earns its keep on
        the equality and prefix lookups Story 3.2 and Epic 8 will add.)

        Deliberately mirrors InventoryService.get_field_value_suggestions in
        name, signature, ValueError-on-unknown-field, [1, 50] limit clamp, LIKE
        escaping, and exact -> starts-with -> contains ranking, so the shared
        endpoint can dispatch on the whitelist alone (AD-14). It takes no
        `location` argument: that parameter is meaningful only for the
        inventory sub_location field.

        NULL and blank values are excluded and comparison is case-insensitive.
        The query is canonicalized before matching (so `Elec` and `elec` behave
        identically, and `Electronics / Power` matches the stored
        `electronics/power`).

        Args:
            field: One of the keys in the module-level FIELD_SUGGESTION_COLUMNS.
            query: Optional filter, normalized then matched case-insensitively
                as a substring. When None or empty, returns `limit` distinct
                values in alphabetical order.
            limit: Maximum number of suggestions. Clamped to [1, 50];
                non-integer values fall back to 10.

        Returns:
            List of distinct canonical value strings.

        Raises:
            ValueError: if `field` is not whitelisted.
        """
        column_name = FIELD_SUGGESTION_COLUMNS.get(field)
        if column_name is None:
            raise ValueError(f"Unsupported field for suggestions: {field!r}")

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))

        # Normalizing the query (rather than a bare .strip().lower()) is what
        # lets a half-typed 'Electronics / Pow' find 'electronics/power'.
        #
        # A query the util REJECTS (over-length) is unmatchable: no stored path
        # can equal it, so the answer is "nothing", not "no filter". Reading
        # the None as an absent query here would silently drop the filter and
        # return the entire vocabulary. A query that merely normalizes AWAY
        # ('', '   ', '/', '///') is different: it carries no path content at
        # all, so it means "no filter", same as an omitted q.
        if field == 'category_path':
            try:
                q = category_util.normalize_category_path(query) or ''
            except category_util.InvalidCategoryPathError:
                return []
        elif field == 'tags':
            # Same division as above: a query the util REJECTS (over-length,
            # or carrying the separator) is unmatchable, because no stored tag
            # can equal it — the answer is "nothing", not "the whole tag
            # vocabulary". A query that merely normalizes AWAY ('', '   ')
            # carries no tag content and means "no filter".
            try:
                q = tag_util.normalize_tag(query) or ''
            except tag_util.InvalidTagError:
                return []
        else:
            # NOT a fallback to normalize_suggestion_value: that method answers
            # a different question (what to ECHO, where a rejected query is
            # None) and reading its None here would mean "no filter" — the
            # whole-vocabulary leak the branches above exist to prevent. A
            # further catalog field registers its matching rule here, next to
            # its echo rule in normalize_suggestion_value.
            raise NotImplementedError(
                f'No suggestion matching rule registered for {field!r}')

        # Resolved AFTER the dispatch above, deliberately. A field whitelisted
        # without its `_FIELD_SUGGESTION_MODELS` entry resolves against Product
        # by default, and for a column that lives on a child table (as `tag`
        # does) that getattr raises AttributeError — a 500 through the route's
        # generic handler, hiding the wiring error the NotImplementedError
        # above exists to state plainly. Ordering it this way means the loud
        # failure wins whichever half of the registration was forgotten.
        column = getattr(_FIELD_SUGGESTION_MODELS.get(field, Product),
                         column_name)

        # Unexpected exceptions are intentionally not swallowed here: the route
        # wrapper catches Exception and returns HTTP 500, and swallowing would
        # turn a backend failure into a 200 with an empty suggestion list.
        session = self.Session()
        try:
            base = session.query(column).filter(
                column.isnot(None),
                func.trim(column) != '',
            )

            if q:
                pattern = f'%{_escape_like_wildcards(q)}%'
                base = base.filter(
                    func.lower(column).like(pattern, escape='\\')
                )
                rank = case(
                    (func.lower(column) == q, 0),
                    (func.lower(column).like(
                        f'{_escape_like_wildcards(q)}%', escape='\\'
                    ), 1),
                    else_=2,
                )
                base = base.order_by(rank, func.lower(column))
            else:
                base = base.order_by(func.lower(column))

            # Over-fetch slightly to give the post-DB case-insensitive dedup
            # pass headroom: the DB DISTINCT depends on the column's collation,
            # so two values differing only in case may both reach Python.
            # Stored paths are canonical (lowercase) since this story, but rows
            # written before the data migration ran must not double up.
            fetch_limit = limit * 3 + 10
            rows = base.distinct().limit(fetch_limit).all()
            values = [
                row[0].strip()
                for row in rows
                if row[0] and row[0].strip()
            ]

            seen_lower = set()
            unique = []
            for v in values:
                key = v.lower()
                if key in seen_lower:
                    continue
                seen_lower.add(key)
                unique.append(v)

            return unique[:limit]

        finally:
            session.close()

    # --- Category tree (Story 3.2) ----------------------------------------

    def list_category_paths(self) -> List[Tuple[str, int]]:
        """
        Return every assigned category path with the number of products filed
        directly under it, alphabetically (Story 3.2, FR17).

        This is the category tree's only listing: there is no node table, so
        the tree IS the distinct set of assigned products.category_path values
        (the same source get_field_value_suggestions draws on). NULL and blank
        paths are excluded — they mean "no category", not a node named ''.

        The count is per exact path, not per subtree: a row for `a` counts the
        products filed at `a` alone, and its descendants appear as their own
        rows. Callers that want a subtree total add the rows up through
        `is_descendant_path` (the rename preview does exactly that).

        Grouping happens in PYTHON, not in SQL. Under MariaDB's default
        case-insensitive PAD SPACE collation, `GROUP BY category_path` folds
        `Electronics/Power`, `electronics/power ` and `electronics/power` into
        ONE group with an arbitrary representative spelling and a summed count
        — hiding a distinct stored path from the one page that exists to
        surface it, and attributing its products to a row a rename would not
        move. Story 3.1's backfill migration documents avoiding exactly this
        (it reads rows individually rather than `SELECT DISTINCT`), and its
        skipped rows are precisely the non-canonical values that make the two
        spellings coexist. The SQL narrows; Python decides — the same division
        rename_category_path makes with its LIKE.

        Returns:
            List of (canonical_path, product_count) tuples, ordered by path.
        """
        session = self.Session()
        try:
            rows = (session.query(Product.category_path)
                    .filter(Product.category_path.isnot(None),
                            func.trim(Product.category_path) != '')
                    .all())
            counts: Dict[str, int] = {}
            for (path,) in rows:
                # Re-decided here rather than trusted from the filter above:
                # the blank test is a string comparison too.
                if path is None or not path.strip():
                    continue
                counts[path] = counts.get(path, 0) + 1
            return sorted(counts.items())
        finally:
            session.close()

    def rename_category_path(self, old_path, new_path) -> int:
        """
        Rename a category path, carrying its descendants and every product
        filed under them, and return how many products were updated (Story
        3.2, FR17).

        Both arguments are normalized first, so the operator may type
        `' /Electronics/Power/ '` for the stored `electronics/power`. The whole
        subtree — the node and every path under it, on the segment boundary
        `app/utils/category.py` defines — is loaded on ONE session, rewritten
        row by row, and committed ONCE: either every affected product moves or
        none does. Products outside the subtree (siblings, near-miss string
        prefixes like `thermal/heatgun-parts` under a `thermal/heat` rename)
        and every NULL/blank row are never touched.

        A rename onto a node that ALREADY EXISTS is rejected rather than
        silently merging the two branches. "Already exists" means some product
        OUTSIDE the source subtree sits at or under the destination — which is
        what still allows a promote (`a/b` -> `a` when only the subtree lives
        under `a`) and a rename INTO the subtree (`a` -> `a/b`), both
        well-defined and reversible.

        That rejection is a check-then-write, not a database constraint: there
        is no uniqueness to enforce (many products legitimately share a path),
        so a product inserted at the destination by a CONCURRENT writer between
        the SELECT and the COMMIT would still slip through. This is a
        single-operator workshop application; the guarantee is against the
        operator's own mistakes, not against a race.

        Unlike create_product/update_product, failures are RAISED, not
        swallowed into a False: a refused rename is an operator-facing
        decision that has to explain itself.

        Args:
            old_path: The category to rename, as typed.
            new_path: The path it becomes, as typed.

        Returns:
            The number of products whose category_path was rewritten.

        Raises:
            ValidationError: with field='old_path' when the source is blank,
                unstorable or holds no products; with field='new_path' when
                the destination is blank, unstorable, identical to the source,
                already occupied, or would push a rewritten descendant past
                the column width. Nothing is written in any of those cases.
        """
        from .logging_config import log_audit_operation

        # --- Argument checks run BEFORE the session is opened: they are pure,
        # they can be answered without the database, and keeping them out here
        # means the handlers below never have to ask whether a session exists.
        # (A rejection is a request error, not a 500: the util's ValueError
        # never leaks out.) ---
        try:
            old_canonical = category_util.normalize_category_path(old_path)
        except category_util.InvalidCategoryPathError as e:
            raise ValidationError(str(e), field='old_path', value=str(old_path))
        try:
            new_canonical = category_util.normalize_category_path(new_path)
        except category_util.InvalidCategoryPathError as e:
            raise ValidationError(str(e), field='new_path', value=str(new_path))

        if old_canonical is None:
            raise ValidationError(
                'Select a category to rename.',
                field='old_path', value=str(old_path))
        if new_canonical is None:
            raise ValidationError(
                'Enter the new category path.',
                field='new_path', value=str(new_path))
        if old_canonical == new_canonical:
            # Refused on the arguments alone, whether or not the path exists.
            raise ValidationError(
                f"'{new_canonical}' is already this category's path — "
                f'nothing to rename.',
                field='new_path', value=new_canonical)

        # Keyed on the CANONICAL source, matching the `changes` payload below:
        # keying on the value as typed would file the same category's history
        # under `category: /Electronics/Power/ ` and `category:electronics/power`
        # depending on how the operator spelled it that day.
        audit_id = f'category:{old_canonical}'

        escape = category_util.CATEGORY_LIKE_ESCAPE_CHAR
        session = self.Session()
        try:
            # One query for both subtrees; the pure predicate — not the LIKE —
            # decides which row belongs to which. The LIKE narrows the scan to
            # the two subtrees, the predicate is the authority on segment
            # boundaries.
            rows = (session.query(Product)
                    # Only category_path is read and written here, so the row's
                    # TEXT column stays on the server — the same reason
                    # get_attachments defers Attachment.content. A top-level
                    # rename otherwise drags every product's notes blob across
                    # to change one varchar per row.
                    .options(defer(Product.notes))
                    .filter(Product.category_path.isnot(None),
                            func.trim(Product.category_path) != '')
                    .filter(or_(
                        Product.category_path == old_canonical,
                        Product.category_path.like(
                            category_util.descendant_like_pattern(old_canonical),
                            escape=escape),
                        Product.category_path == new_canonical,
                        Product.category_path.like(
                            category_util.descendant_like_pattern(new_canonical),
                            escape=escape),
                    ))
                    .all())

            moving = [p for p in rows
                      if category_util.is_descendant_path(p.category_path,
                                                          old_canonical)]
            # Excluding the source subtree is what makes a promote legal while
            # still rejecting a merge onto an occupied node.
            blockers = [p for p in rows
                        if category_util.is_descendant_path(p.category_path,
                                                            new_canonical)
                        and not category_util.is_descendant_path(
                            p.category_path, old_canonical)]

            # A row the SQL matched but NEITHER predicate claims can only be a
            # non-canonical value that a case-insensitive collation folded onto
            # one of the two paths (MariaDB is _ci; the Python predicate is
            # not). Story 3.1's backfill makes those vanishingly rare — only a
            # value that cannot be normalized survives it — but silently
            # dropping one would leave a row stranded at the old path, or let
            # through exactly the branch merge this method exists to refuse.
            # So it is reported instead of ignored.
            claimed = {id(p) for p in moving} | {id(p) for p in blockers}
            unclaimed = [p for p in rows if id(p) not in claimed]
            if unclaimed:
                # The id list is capped, but the cap is STATED: an operator who
                # fixes the twenty named rows and hits the identical-looking
                # error again would otherwise have no way to know the list was
                # ever partial (the Story 3.1 migration reports its own skipped
                # rows the same way).
                shown = ', '.join(str(p.id) for p in unclaimed[:20])
                if len(unclaimed) > 20:
                    shown += f', ... ({len(unclaimed)} in total)'
                raise ValidationError(
                    f'Cannot rename: product(s) {shown} carry a '
                    f'non-canonical category path that overlaps this rename. '
                    f'Fix those products first.',
                    field='old_path', value=old_canonical)
            if not moving:
                raise ValidationError(
                    f"No products are filed under category "
                    f"'{old_canonical}'.",
                    field='old_path', value=old_canonical)
            if blockers:
                raise ValidationError(
                    f"Category '{new_canonical}' already exists and holds "
                    f'{len(blockers)} product(s). Rename it or pick another '
                    f'path — merging two branches is not supported.',
                    field='new_path', value=new_canonical)

            # Compute EVERY rewrite before assigning any, so an over-length
            # descendant is refused with nothing written.
            rewrites = []
            for product in moving:
                try:
                    rewrites.append((product,
                                     category_util.rewrite_category_path(
                                         product.category_path,
                                         old_canonical, new_canonical)))
                except category_util.InvalidCategoryPathError as e:
                    # Name the product. A row that is ALREADY past the column
                    # width (Story 3.1's backfill leaves those in place) fails
                    # this check for every destination that is not shorter than
                    # the source, so a message about `new_path` alone sends the
                    # operator hunting for a shorter destination when the fix
                    # is one specific product.
                    raise ValidationError(
                        f'{e} (product {product.id}).',
                        field='new_path', value=new_canonical)

            for product, rewritten in rewrites:
                product.category_path = rewritten

            session.commit()
        except ValidationError:
            # A refused rename is ordinary validation, not an operational
            # failure — same as add_attachment, it rolls back and re-raises
            # without an audit-error record.
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            try:
                log_audit_operation('rename_category_path', 'error',
                                    item_id=audit_id, error_details=str(e),
                                    logger_name='mariadb_catalog_service')
            except Exception as audit_err:
                # An audit sink that is down must not REPLACE the failure it was
                # asked to record: the caller would then see 'audit sink down'
                # in place of the database error that actually killed the
                # rename, and the real cause would appear nowhere at all. Same
                # guarantee the success path already gives.
                logger.warning(
                    f'Category rename {old_canonical!r} -> {new_canonical!r} '
                    f'failed, and its audit log failed too: {audit_err}')
            raise
        finally:
            session.close()

        # Past the commit the rename HAS happened. Audit-logging therefore sits
        # outside the try and cannot raise: the caller renders a failure
        # message from any exception, and telling the operator to retry a
        # rename that already succeeded would send them to a source path that
        # no longer exists.
        try:
            log_audit_operation('rename_category_path', 'success',
                                item_id=audit_id,
                                changes={'old_path': old_canonical,
                                         'new_path': new_canonical,
                                         'products_updated': len(rewrites)},
                                logger_name='mariadb_catalog_service')
        except Exception as e:
            logger.warning(
                f'Category rename {old_canonical!r} -> {new_canonical!r} '
                f'committed, but its audit log failed: {e}')
        return len(rewrites)

    # --- Product tags (Story 3.3) -----------------------------------------

    @staticmethod
    def _is_duplicate_key_violation(exc: IntegrityError) -> bool:
        """
        Return True when an IntegrityError is a UNIQUE/PRIMARY KEY violation
        rather than some other integrity failure (Story 3.3).

        `set_product_tags` translates a duplicate-key failure into an
        operator-facing ValidationError naming the colliding tags, so it has to
        know that is what happened: every other integrity failure (an FK broken
        by a concurrently-deleted product, a column constraint, a storage-level
        error) must keep its own identity and reach the audit log. The
        re-query the handler performs cannot make that distinction — after a
        rolled-back flush of NEW rows there is nothing committed to find, so an
        unrelated failure looks exactly like a collation collision.

        SQLAlchemy exposes no portable error classification, so the DBAPI error
        itself is inspected: MariaDB/MySQL report errno 1062 (ER_DUP_ENTRY,
        "Duplicate entry ... for key ..."), SQLite reports "UNIQUE constraint
        failed". Matching is deliberately loose — a false positive only costs a
        more specific message for a failure that would have been re-raised.
        """
        orig = getattr(exc, 'orig', None)
        args = getattr(orig, 'args', ()) or ()
        if args and args[0] == 1062:  # MySQL/MariaDB ER_DUP_ENTRY
            return True
        text = str(orig if orig is not None else exc).lower()
        return 'duplicate' in text or 'unique constraint' in text

    def _canonical_tags(self, tags) -> List[str]:
        """
        Return the canonical, de-duplicated tag list for a caller-supplied
        value, or raise ValidationError (Story 3.3, FR16).

        Accepts either the raw comma-separated form field (a string) or an
        already-split iterable, because both callers exist: the route parses
        the field itself so an operator's typo is refused BEFORE the product is
        written, while a programmatic caller passes a list. Either way the
        canonical form comes from app/utils/tag.py alone — nothing here splits,
        trims or lowercases a tag (AD-4).
        """
        try:
            if tags is None:
                canonical = []
            elif isinstance(tags, str):
                canonical = tag_util.parse_tag_list(tags)
            else:
                # De-duplicated on the canonical form, first-seen order, so
                # ['SSR', 'ssr'] is one tag rather than a uniqueness violation
                # the operator would have to decode from an error page — the
                # same rule parse_tag_list applies to the string form.
                canonical = []
                seen = set()
                for raw in tags:
                    value = tag_util.normalize_tag(raw)
                    if value is None or value in seen:
                        continue
                    seen.add(value)
                    canonical.append(value)
        except tag_util.InvalidTagError as e:
            raise ValidationError(str(e), field='tags', value=str(tags))
        except TypeError as e:
            # A non-iterable, non-string argument (5, an object) is a caller
            # fault, but this method's contract is that it raises
            # ValidationError and nothing else — a bare TypeError from the for
            # loop would reach the route's generic 500 handler instead.
            raise ValidationError(f'Tags must be a string, an iterable of '
                                  f'strings, or None: {e}',
                                  field='tags', value=str(tags))

        if len(canonical) > tag_util.MAX_TAGS_PER_PRODUCT:
            raise ValidationError(
                f'Too many tags: {len(canonical)} '
                f'(max {tag_util.MAX_TAGS_PER_PRODUCT} per product).',
                field='tags', value=str(tags))
        return canonical

    def get_tags_for_product(self, product_id: int) -> List[str]:
        """
        Return a product's tags alphabetically. [] for an untagged or unknown
        product (Story 3.3, FR16).

        A dedicated query — NOT relationship navigation, which would lazy-load
        on the detached Product `get_product` returns. Read-only, so the plain
        strings it hands back stay usable after the session closes.
        """
        session = self.Session()
        try:
            rows = (session.query(ProductTag.tag)
                    .filter(ProductTag.product_id == product_id)
                    .all())
            return sorted(row[0] for row in rows)
        finally:
            session.close()

    def set_product_tags(self, product_id, tags) -> List[str]:
        """
        Replace a product's whole tag set and return the stored tags, sorted
        (Story 3.3, FR16).

        REPLACE-ALL, because that is what the form submits: there is no
        per-tag add/remove UI, so the field's whole value is the requested set
        and `[]` clears every tag. The stored rows are DIFFED against it rather
        than deleted and re-inserted, so an unchanged tag keeps its row (and
        its created_at) and re-submitting an unchanged form writes nothing.
        That also makes the operation idempotent, which is the route's whole
        retry story: the only way to recover from a failed tag write is to save
        the form again, and doing so is always safe.

        Everything the arguments alone can decide is decided BEFORE the session
        opens, so an operator-caused rejection never leaves a half-written
        transaction. The remaining rejections (unknown product, a collation
        collision) roll back and raise. Unlike create_product/update_product,
        failures are RAISED, not swallowed into a False: a refused tag write is
        an operator-facing decision that has to explain itself.

        Args:
            product_id: The product to retag.
            tags: The complete requested tag set — the raw comma-separated
                form field, or an iterable of tags.

        Returns:
            The product's tags after the write, sorted alphabetically.

        Raises:
            ValidationError: with field='tags' when a tag is unusable, when
                there are too many, when two requested tags collide under the
                database's collation, or when a concurrent save wrote one of
                them first; with field='product_id' when the product does not
                exist. Nothing is written in any of those cases. Any OTHER
                integrity failure keeps its own identity and is re-raised.

                The concurrent-save case additionally carries `retryable=True`:
                the requested list is fine and succeeds on the next attempt,
                unlike a collision, which is refused for as long as the tags
                stay as they are. Callers deciding what to tell an operator
                must read that rather than the field alone.
        """
        from .logging_config import log_audit_operation

        # Pure argument checks first: they need no database, and keeping them
        # out here means the handlers below never have to ask whether a session
        # exists. (A rejection is a request error, not a 500: the util's
        # ValueError never leaks out.)
        requested = self._canonical_tags(tags)

        session = self.Session()
        try:
            if session.query(Product).filter(
                    Product.id == product_id).first() is None:
                raise ValidationError(f'Product not found (product:{product_id}).',
                                      field='product_id', value=str(product_id))

            current = {row.tag: row
                       for row in session.query(ProductTag)
                       .filter(ProductTag.product_id == product_id)}
            removed = sorted(set(current) - set(requested))
            added = [t for t in requested if t not in current]

            for tag in removed:
                session.delete(current[tag])
            if removed:
                # Deletes are flushed FIRST, deliberately: SQLAlchemy's unit of
                # work emits inserts before deletes, so replacing 'café' with
                # 'cafe' would insert the new row while the old one is still
                # present — and under MariaDB's accent-folding unique index
                # that is a collision with a row on its way out. Same
                # transaction either way; only the statement order changes.
                session.flush()
            for tag in added:
                session.add(ProductTag(product_id=product_id, tag=tag))

            try:
                session.flush()
            except IntegrityError as exc:
                # Reachable on MariaDB and not on SQLite: utf8mb4_unicode_ci
                # folds accents, so 'café' and 'cafe' — two DISTINCT canonical
                # tags in Python — collide on uq_product_tags_product_tag
                # there. Roll the failed flush back so the conflict lookup can
                # run, then work out which of the three shapes this is.
                session.rollback()
                if not self._is_duplicate_key_violation(exc):
                    # Not a uniqueness violation at all (a concurrently-deleted
                    # product breaking the FK, a column constraint, a disk-level
                    # failure). Nothing below can diagnose it, and dressing it
                    # up as a tag collision would send the operator hunting for
                    # a conflict that does not exist AND erase the failure from
                    # the audit log, since a ValidationError is deliberately not
                    # audited. It is re-raised as the operational failure it is.
                    raise
                concurrent: List[str] = []
                for tag in added:
                    existing = (session.query(ProductTag)
                                .filter(ProductTag.product_id == product_id,
                                        ProductTag.tag == tag)
                                .first())
                    if existing is None:
                        continue
                    if existing.tag == tag:
                        # The very row this save is adding: a concurrent writer
                        # committed the identical tag first. Not a collation
                        # collision, and no sentence naming a tag as
                        # conflicting with itself — but not silently fine
                        # either, because this save's OTHER rows rolled back
                        # with it. Reported below as the retryable race it is.
                        concurrent.append(tag)
                        continue
                    raise ValidationError(
                        f"Tag '{tag}' conflicts with '{existing.tag}', "
                        f'which this product already carries — the '
                        f'database treats them as the same tag.',
                        field='tags', value=tag)
                if session.query(Product).filter(
                        Product.id == product_id).first() is None:
                    # The FK target vanished mid-write. Re-raised: the product
                    # is gone, so there is no tag advice worth giving.
                    raise
                if concurrent:
                    listed = ', '.join(f"'{t}'" for t in concurrent)
                    error = ValidationError(
                        f'Another save added {listed} to this product at the '
                        f'same time, so these tags were not written.',
                        field='tags', value=', '.join(added))
                    # RETRYABLE, unlike the two collisions below: nothing about
                    # the requested list is wrong, so the IDENTICAL list
                    # succeeds once the racing transaction is done. Saying so
                    # on the exception is what stops the route telling the
                    # operator to change tags that were never the problem —
                    # the field alone cannot distinguish the two.
                    error.retryable = True
                    raise error
                if len(added) > 1:
                    # A duplicate-key violation, nothing COMMITTED conflicts and
                    # the FK target is still there, so the collision is between
                    # the tags this save is adding: the database folds two of
                    # them onto each other. Which pair cannot be read off a
                    # rolled-back flush, so all of them are named — the operator
                    # has to drop one either way. Without this the
                    # IntegrityError escaped as a 500 for exactly the
                    # both-tags-new case this method exists to refuse cleanly.
                    #
                    # Naming ALL of them is bounded, not exhaustive: with
                    # MAX_TAGS_PER_PRODUCT at 50, a pasted list would render a
                    # flash naming fifty tags, which is no more actionable than
                    # naming none. The first few plus a count is.
                    shown = added[:MAX_TAGS_NAMED_IN_ERROR]
                    listed = ', '.join(f"'{t}'" for t in shown)
                    if len(added) > len(shown):
                        listed += f' (and {len(added) - len(shown)} more)'
                    raise ValidationError(
                        f'These tags cannot be saved together: the database '
                        f'treats two of {listed} as the same tag. Remove one '
                        f'of them.',
                        field='tags', value=', '.join(added))
                # A single insert with nothing committed to conflict with:
                # unexplained, so it keeps its own identity rather than being
                # mislabelled as a duplicate the operator could act on.
                raise

            session.commit()
        except ValidationError:
            # A refused retag is ordinary validation, not an operational
            # failure — same as add_identifier, it rolls back and re-raises
            # without an audit-error record.
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            try:
                log_audit_operation('set_product_tags', 'error',
                                    item_id=f'product:{product_id}',
                                    error_details=str(e),
                                    logger_name='mariadb_catalog_service')
            except Exception as audit_err:
                # An audit sink that is down must not REPLACE the failure it
                # was asked to record.
                logger.warning(
                    f'Tag write for product {product_id} failed, and its '
                    f'audit log failed too: {audit_err}')
            raise
        finally:
            session.close()

        # Past the commit the tags HAVE changed, so audit-logging sits outside
        # the try and cannot raise: the caller renders a failure message from
        # any exception, and reporting a failure for a write that succeeded
        # would send the operator to fix something that is already right.
        #
        # A save that changed nothing writes no record: the route calls this on
        # every product edit that carries the field, so auditing a no-op would
        # file a tag event against every edit and bury the real ones.
        if added or removed:
            try:
                log_audit_operation('set_product_tags', 'success',
                                    item_id=f'product:{product_id}',
                                    changes={'tags': requested,
                                             'added': added,
                                             'removed': removed},
                                    logger_name='mariadb_catalog_service')
            except Exception as e:
                logger.warning(
                    f'Tag write for product {product_id} committed, but its '
                    f'audit log failed: {e}')
        return sorted(requested)

    def list_tags(self) -> List[Tuple[str, int]]:
        """
        Return every assigned tag with the number of products carrying it,
        alphabetically (Story 3.3, FR16).

        This is the tag vocabulary's only listing: there is no vocabulary
        table, so the vocabulary IS the distinct set of assigned
        product_tags.tag values. A tag appears the moment a product carries it
        and disappears when the last one drops it.

        Grouping happens in PYTHON, not in SQL, for the reason
        `list_category_paths` states: under MariaDB's case- and
        accent-insensitive collation `GROUP BY tag` would fold 'café' and
        'cafe' into ONE group with an arbitrary representative spelling and a
        summed count — hiding a distinct stored tag from the one page that
        exists to surface it. The SQL narrows; Python decides.

        Returns:
            List of (tag, product_count) tuples, ordered by tag.
        """
        session = self.Session()
        try:
            rows = session.query(ProductTag.tag).all()
            counts: Dict[str, int] = {}
            for (tag,) in rows:
                if not tag:
                    continue
                # One row per (product_id, tag) pair is guaranteed by the
                # unique constraint, so counting rows counts products.
                counts[tag] = counts.get(tag, 0) + 1
            return sorted(counts.items())
        finally:
            session.close()

    def find_products_by_tag(self, tag) -> List[Product]:
        """
        Return exactly the products carrying `tag`, ordered by description,
        REGARDLESS of their categories (Story 3.3, FR16).

        This is FR16's filter. The argument is normalized first, so the
        operator may type `'  SSR '` for the stored `ssr`. A value that carries
        no tag at all, or that no stored tag could equal (over-length,
        comma-bearing), yields [] — unmatchable, never "no filter": reading it
        as an absent argument would hand back the whole catalog.

        The tag equality is re-checked in PYTHON after the query, for the same
        reason `list_tags` counts there: the SQL comparison runs under the
        column's collation, which on MariaDB matches 'cafe' against a stored
        'café'. The SQL narrows to a candidate set; Python decides which rows
        actually carry the tag.

        Read-only (no commit), so the detached Product rows keep their scalar
        columns for template rendering. Do not access relationship attributes
        on them.

        Args:
            tag: The tag to filter by, as typed.

        Returns:
            The matching Products, ordered by description then id. [] when the
            argument is unusable or nothing carries the tag — an empty result
            is an answer, not an error.
        """
        try:
            canonical = tag_util.normalize_tag(tag)
        except tag_util.InvalidTagError:
            return []
        if canonical is None:
            return []

        session = self.Session()
        try:
            rows = (session.query(Product, ProductTag.tag)
                    .join(ProductTag, ProductTag.product_id == Product.id)
                    .filter(ProductTag.tag == canonical)
                    .order_by(Product.description.asc(), Product.id.asc())
                    .all())
            products = []
            seen = set()
            for product, stored_tag in rows:
                if stored_tag != canonical or product.id in seen:
                    continue
                seen.add(product.id)
                products.append(product)
            return products
        finally:
            session.close()

    # --- Purchases (Story 1.4) -------------------------------------------

    def get_purchases_for_product(self, product_id: int) -> List[Purchase]:
        """
        Return the product's Purchases in chronological order (oldest first).

        A dedicated query — NOT `product.purchases` relationship navigation,
        which would lazy-load on the detached Product `get_product` returns
        (DetachedInstanceError). Read-only, so the returned detached rows keep
        their scalar columns for template rendering. Returns [] for an unknown
        product.
        """
        session = self.Session()
        try:
            return (session.query(Purchase)
                    .filter(Purchase.product_id == product_id)
                    .order_by(Purchase.order_date.asc(), Purchase.id.asc())
                    .all())
        finally:
            session.close()

    def get_last_paid_price(self, product_id: int) -> Optional[Decimal]:
        """
        Return the unit_price of the most recent priced Purchase (by order_date,
        tie-break id), or None if the product has no purchase with a price
        (FR21 "Last paid"). Per-product; group-awareness is Epic 10.
        """
        session = self.Session()
        try:
            purchase = (session.query(Purchase)
                        .filter(Purchase.product_id == product_id,
                                Purchase.unit_price.isnot(None))
                        .order_by(Purchase.order_date.desc(), Purchase.id.desc())
                        .first())
            return purchase.unit_price if purchase else None
        finally:
            session.close()

    def record_purchase(self, product_id: int, *, vendor=None, vendor_sku=None,
                        order_date=None, received_date=None, quantity=None,
                        unit_price=None, order_number=None, source_url=None
                        ) -> Optional[dict]:
        """
        Record a Purchase against an existing Product (FR18, FR22).

        Returns the created purchase's to_dict() snapshot (captured before the
        session closes, so the caller can echo the resource without a detached
        re-fetch), or None if the product does not exist or the insert fails.
        A missing order_date defaults to today (the server-side capture-date
        convention; Epic 7 reuses it). Callers pass already-typed values
        (Decimal price, date fields, int quantity); parsing is the route's job.
        Does not accept request_key — idempotent capture is Epic 7.
        """
        from .logging_config import log_audit_operation
        try:
            session = self.Session()
            product = session.query(Product).filter(Product.id == product_id).first()
            if product is None:
                log_audit_operation('record_purchase', 'error', item_id=str(product_id),
                                    error_details='Product not found',
                                    logger_name='mariadb_catalog_service')
                return None

            purchase = Purchase(
                product_id=product_id,
                vendor=_clean(vendor),
                vendor_sku=_clean(vendor_sku),
                order_date=order_date if order_date is not None else date.today(),
                received_date=received_date,
                quantity=quantity,
                unit_price=unit_price,
                order_number=_clean(order_number),
                source_url=_clean(source_url),
            )
            session.add(purchase)
            # Flush + snapshot before commit (see create_product rationale).
            session.flush()
            snapshot = purchase.to_dict()
            session.commit()
            log_audit_operation('record_purchase', 'success', item_id=str(product_id),
                                item_after=snapshot, logger_name='mariadb_catalog_service')
            return snapshot
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            log_audit_operation('record_purchase', 'error', item_id=str(product_id),
                                error_details=str(e), logger_name='mariadb_catalog_service')
            return None
        finally:
            if 'session' in locals():
                session.close()

    def record_amazon_purchase(self, product_id: int, *, asin, vendor='Amazon',
                               order_date=None, received_date=None, quantity=None,
                               unit_price=None, order_number=None, source_url=None
                               ) -> Optional[dict]:
        """
        Record an Amazon Purchase and index its ASIN in one transaction (FR11,
        AD-9).

        Unlike composing record_purchase + add_identifier (each of which commits
        its own session), this writes both the Purchase (with vendor_sku = the
        ASIN) and the ASIN-type ProductIdentifier on the SAME session and commits
        once: on any conflict nothing is committed (no orphan Purchase). The ASIN
        is vendor-scoped — its vendor_scope and the Purchase's vendor both come
        from `vendor` (default 'Amazon') — and stored as entered (stripped only,
        never normalized). Idempotent when this Product already carries the ASIN
        (repeat buys record a new Purchase but not a second identifier); an ASIN
        already indexed on a DIFFERENT Product is rejected as a caught
        ValidationError naming that Product (never silently re-attached), leaving
        neither Product's identity changed. Returns the Purchase's to_dict()
        snapshot (captured before commit), mirroring record_purchase.
        """
        from .logging_config import log_audit_operation

        # --- Validate ASIN (coerce non-str, strip; ASIN stored as entered) ---
        asin = ('' if asin is None else str(asin)).strip()
        if not asin:
            raise ValidationError('ASIN must not be blank.',
                                  field='asin', value=asin)
        if len(asin) > IDENTIFIER_MAX_LENGTH:
            raise ValidationError(
                f'Identifier value is too long (max {IDENTIFIER_MAX_LENGTH} characters).',
                field='value', value=asin)

        # --- Compute scope (ASIN is vendor-scoped, AD-9) ---
        scope = (vendor or '').strip()
        if len(scope) > IDENTIFIER_MAX_LENGTH:
            raise ValidationError(
                f'Vendor is too long (max {IDENTIFIER_MAX_LENGTH} characters).',
                field='vendor', value=scope)

        itype = IdentifierType.ASIN

        def _conflict_error(owner_product_id):
            where = f" (vendor '{scope}')" if scope else ''
            return ValidationError(
                f"Identifier {itype.value} '{asin}'{where} already exists on "
                f"product {owner_product_id}.", field='value', value=asin)

        try:
            session = self.Session()
            if session.query(Product).filter(Product.id == product_id).first() is None:
                raise ValidationError(f'Product not found (product:{product_id}).',
                                      field='product_id', value=str(product_id))

            # Resolve the ASIN index FIRST, flushing it on its own so a unique-index
            # IntegrityError is unambiguously about the ASIN (not the Purchase).
            # Reuse Story 2.1's vendor-scoped uniqueness.
            existing = (session.query(ProductIdentifier)
                        .filter_by(identifier_type=itype.value, value=asin, vendor_scope=scope)
                        .first())
            if existing is not None and existing.product_id != product_id:
                # Owned by a DIFFERENT Product — reject, name it, write nothing.
                raise _conflict_error(existing.product_id)
            if existing is None:
                # First sight of this ASIN — index it on THIS Product.
                session.add(ProductIdentifier(
                    product_id=product_id,
                    identifier_type=itype.value,
                    value=asin,
                    vendor_scope=scope,
                ))
                try:
                    session.flush()
                except IntegrityError:
                    # Lost a concurrent-insert race on the unique ASIN index. Roll
                    # back the pending identifier, then re-read who owns it: a
                    # DIFFERENT Product is a real conflict; the SAME Product means a
                    # peer transaction indexed our ASIN first, so fall through and
                    # record the Purchase idempotently. If nothing matches, it was
                    # some other integrity failure — re-raise it, never mislabel it.
                    session.rollback()
                    conflict = (session.query(ProductIdentifier)
                                .filter_by(identifier_type=itype.value, value=asin,
                                           vendor_scope=scope)
                                .first())
                    if conflict is not None and conflict.product_id != product_id:
                        raise _conflict_error(conflict.product_id)
                    if conflict is None:
                        raise
            # else: this Product already carries the ASIN — idempotent, skip insert.

            # Store the stripped vendor (== vendor_scope) so the Purchase and the
            # ASIN identifier never disagree on the vendor string.
            purchase = Purchase(
                product_id=product_id,
                vendor=(scope or None),
                vendor_sku=asin,
                order_date=order_date if order_date is not None else date.today(),
                received_date=received_date,
                quantity=quantity,
                unit_price=unit_price,
                order_number=_clean(order_number),
                source_url=_clean(source_url),
            )
            session.add(purchase)
            session.flush()

            # Snapshot before commit (see create_product rationale).
            snapshot = purchase.to_dict()
            session.commit()
            log_audit_operation('record_amazon_purchase', 'success',
                                item_id=f'product:{product_id}', item_after=snapshot,
                                logger_name='mariadb_catalog_service')
            return snapshot
        except ValidationError:
            if 'session' in locals():
                session.rollback()
            raise
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            log_audit_operation('record_amazon_purchase', 'error',
                                item_id=f'product:{product_id}', error_details=str(e),
                                logger_name='mariadb_catalog_service')
            raise
        finally:
            if 'session' in locals():
                session.close()

    # --- Attachments (Story 1.5) -----------------------------------------

    def add_attachment(self, *, product_id=None, purchase_id=None, filename,
                       content, content_type) -> dict:
        """
        Store a file attachment owned by exactly one of a Product or Purchase
        (AD-12). Returns the created attachment's BLOB-free to_dict() snapshot.

        Validation failures are raised as ValidationError (caught domain errors,
        not raw IntegrityError): the XOR one-owner rule, empty/oversize content,
        disallowed content_type, and a non-existent owner.
        """
        from .logging_config import log_audit_operation

        # --- Validation (app-level invariants) ---
        if (product_id is None) == (purchase_id is None):
            raise ValidationError('An attachment must have exactly one owner '
                                  '(a product or a purchase, not both or neither).')
        if not content:
            raise ValidationError('Attachment content is empty.')
        if len(content) > ATTACHMENT_MAX_SIZE:
            raise ValidationError(
                f'Attachment exceeds the maximum size of {round(ATTACHMENT_MAX_SIZE / (1024 * 1024))} MB.')
        if content_type not in ATTACHMENT_ALLOWED_TYPES:
            raise ValidationError(f'Unsupported attachment type: {content_type}.')
        clean_filename = (filename or '').strip() or 'attachment'
        if len(clean_filename) > ATTACHMENT_MAX_FILENAME:
            raise ValidationError(
                f'Filename is too long (max {ATTACHMENT_MAX_FILENAME} characters).')

        owner_label = f'product:{product_id}' if product_id is not None else f'purchase:{purchase_id}'
        try:
            session = self.Session()
            owner_cls = Product if product_id is not None else Purchase
            owner_id = product_id if product_id is not None else purchase_id
            if session.query(owner_cls).filter(owner_cls.id == owner_id).first() is None:
                raise ValidationError(f'Owner not found ({owner_label}).')

            attachment = Attachment(
                product_id=product_id,
                purchase_id=purchase_id,
                filename=clean_filename,
                content_type=content_type,
                file_size=len(content),
                content=content,
            )
            session.add(attachment)
            session.flush()
            snapshot = attachment.to_dict()
            session.commit()
            log_audit_operation('add_attachment', 'success', item_id=owner_label,
                                item_after=snapshot, logger_name='mariadb_catalog_service')
            return snapshot
        except ValidationError:
            if 'session' in locals():
                session.rollback()
            raise
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            log_audit_operation('add_attachment', 'error', item_id=owner_label,
                                error_details=str(e), logger_name='mariadb_catalog_service')
            raise
        finally:
            if 'session' in locals():
                session.close()

    def get_attachments_for_product(self, product_id: int) -> List[Attachment]:
        """
        Return a product's attachments (metadata only — the BLOB is deferred so
        listing never pulls megabytes into memory), oldest first. [] if none.
        """
        session = self.Session()
        try:
            return (session.query(Attachment)
                    .options(defer(Attachment.content))
                    .filter(Attachment.product_id == product_id)
                    .order_by(Attachment.created_at.asc(), Attachment.id.asc())
                    .all())
        finally:
            session.close()

    def get_attachment_data(self, attachment_id: int) -> Optional[Tuple[bytes, str, str]]:
        """Return (content_bytes, content_type, filename) for serving, or None."""
        session = self.Session()
        try:
            att = session.query(Attachment).filter(Attachment.id == attachment_id).first()
            if att is None:
                return None
            return att.content, att.content_type, att.filename
        finally:
            session.close()

    def add_identifier(self, product_id, *, identifier_type, value, vendor=None) -> dict:
        """
        Attach a typed (identifier_type, value) identifier to a Product (FR7).
        Returns the created row's to_dict() snapshot.

        Uniqueness is DB-enforced over (identifier_type, value, vendor_scope)
        (AD-9): VENDOR_SKU/ASIN/FNSKU are vendor-scoped; every other type is
        global (vendor_scope=''). A duplicate surfaces as a caught
        ValidationError naming the conflicting Product — never a raw
        IntegrityError. Invalid type, blank value, and unknown product are
        also rejected with ValidationError before insert.

        INTERNAL is NOT addable here (Story 2.4, FR7): that row is derived by
        create_product from products.internal_id in one transaction, and letting
        it be added or replaced by hand is exactly how the index would come to
        disagree with the column it mirrors.
        """
        from .logging_config import log_audit_operation

        # --- Coerce/validate identifier_type ---
        if isinstance(identifier_type, IdentifierType):
            itype = identifier_type
        else:
            try:
                itype = IdentifierType(identifier_type)
            except ValueError:
                raise ValidationError(f'Invalid identifier type: {identifier_type!r}.',
                                      field='identifier_type', value=str(identifier_type))

        if itype is IdentifierType.INTERNAL:
            raise ValidationError(
                f'{IdentifierType.INTERNAL.value} identifiers are generated with '
                f'the product and cannot be added or changed by hand.',
                field='identifier_type', value=itype.value)

        # --- Validate value (coerce non-str input, e.g. an integer barcode) ---
        value = ('' if value is None else str(value)).strip()
        if not value:
            raise ValidationError('Identifier value must not be blank.',
                                  field='value', value=value)
        if len(value) > IDENTIFIER_MAX_LENGTH:
            raise ValidationError(
                f'Identifier value is too long (max {IDENTIFIER_MAX_LENGTH} characters).',
                field='value', value=value)

        # --- Normalize + check-digit-validate GTIN (Story 2.2, FR9/FR10) ---
        # Only GTIN is normalized: the stored, snapshotted, and
        # uniqueness-checked value becomes the canonical 14-digit key, so every
        # encoding of one product collides on the shared key. A check-digit
        # failure is surfaced as a domain ValidationError (never a raw
        # InvalidGtinError) that offers the GTIN_UNVALIDATED path.
        # GTIN_UNVALIDATED is stored exactly as entered — never normalized.
        if itype is IdentifierType.GTIN:
            try:
                value = gtin.normalize_gtin(value)
            except gtin.InvalidGtinError as e:
                raise ValidationError(
                    f'{e} Store it as {IdentifierType.GTIN_UNVALIDATED.value} '
                    f'to keep it without check-digit validation.',
                    field='value', value=value)

        # --- Compute scope (AD-9) ---
        scope = (vendor or '').strip() if itype in VENDOR_SCOPED_IDENTIFIER_TYPES else ''
        if len(scope) > IDENTIFIER_MAX_LENGTH:
            raise ValidationError(
                f'Vendor is too long (max {IDENTIFIER_MAX_LENGTH} characters).',
                field='vendor', value=scope)

        try:
            session = self.Session()
            if session.query(Product).filter(Product.id == product_id).first() is None:
                raise ValidationError(f'Product not found (product:{product_id}).',
                                      field='product_id', value=str(product_id))

            identifier = ProductIdentifier(
                product_id=product_id,
                identifier_type=itype.value,
                value=value,
                vendor_scope=scope,
            )
            session.add(identifier)
            try:
                session.flush()
            except IntegrityError:
                # Rollback the failed flush so the conflict lookup can run, then
                # confirm this really was the uniqueness violation. If no
                # matching row exists it was some other integrity failure (e.g.
                # a concurrently-deleted product breaking the FK) — re-raise it
                # rather than mislabel it as a duplicate.
                session.rollback()
                existing = (session.query(ProductIdentifier)
                            .filter_by(identifier_type=itype.value, value=value, vendor_scope=scope)
                            .first())
                if existing is None:
                    raise
                where = f" (vendor '{scope}')" if scope else ''
                raise ValidationError(
                    f"Identifier {itype.value} '{value}'{where} already exists on "
                    f"product {existing.product_id}.", field='value', value=value)

            snapshot = identifier.to_dict()
            session.commit()
            log_audit_operation('add_identifier', 'success', item_id=f'product:{product_id}',
                                item_after=snapshot, logger_name='mariadb_catalog_service')
            return snapshot
        except ValidationError:
            if 'session' in locals():
                session.rollback()
            raise
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            log_audit_operation('add_identifier', 'error', item_id=f'product:{product_id}',
                                error_details=str(e), logger_name='mariadb_catalog_service')
            raise
        finally:
            if 'session' in locals():
                session.close()

    def get_identifiers_for_product(self, product_id: int) -> List[ProductIdentifier]:
        """Return a product's identifiers, oldest first. [] if none."""
        session = self.Session()
        try:
            return (session.query(ProductIdentifier)
                    .filter(ProductIdentifier.product_id == product_id)
                    .order_by(ProductIdentifier.created_at.asc(), ProductIdentifier.id.asc())
                    .all())
        finally:
            session.close()

    def encode_internal_payload(self, internal_id: str) -> str:
        """
        Return the GS1 element string for an internal identifier (Story 2.4,
        FR12/FR12b).

        This is the single config seam (AD-16): the AI and token come from the
        one named pair (GS1_INTERNAL_AI / GS1_INTERNAL_TOKEN) and are passed
        explicitly into app/utils/gs1.py, which holds no literal defaults. One
        config change therefore moves the encoder and every decoder together,
        with no code edit (FR12c). The pair is read from Config on every call
        rather than captured at import, so nothing here caches a stale grammar
        — though Config itself reads the environment once, at import, so a
        changed .env still needs a process restart.

        Raises:
            ValidationError: if the id (or the configured grammar) cannot be
                encoded — the pure module's InvalidGs1PayloadError never leaks.
        """
        try:
            return gs1.encode(internal_id,
                              ai=Config.GS1_INTERNAL_AI,
                              token=Config.GS1_INTERNAL_TOKEN)
        except gs1.InvalidGs1PayloadError as e:
            raise ValidationError(str(e), field='internal_id',
                                  value=str(internal_id))

    def ownership_label_text(self) -> str:
        """
        Return the configured ownership/return text for a label (Story 2.5,
        FR12d).

        The counterpart of encode_internal_payload, and deliberately its
        structural opposite. FR12d says ownership/return information is
        human-readable label text and never an encoded element string, so this
        is the one place that text comes from: Epic 6 composites the return
        value into the label's text region, while the symbol beside it carries
        only what encode_internal_payload produced. What keeps the two regions
        apart is that nothing passes this value into gs1.encode — not the shape
        of the text itself. A typical return-to string is unencodable because it
        carries spaces, but a short compact one ('ReturnTo:J.Antman') is not, so
        that is a backstop rather than the guarantee.

        Config.LABEL_OWNER_TEXT is read on every call rather than captured at
        import, mirroring the GS1 pair above (Config itself still reads the
        environment once, so a changed .env needs a process restart). The value
        is stripped; unset, blank or whitespace-only yields '', meaning the
        label simply has no ownership region — a valid configuration, not an
        error. No length or wrapping rule is applied: that depends on media
        geometry, which belongs to the label renderer.

        Returns:
            The ownership text, stripped, or '' when none is configured.
        """
        return (Config.LABEL_OWNER_TEXT or '').strip()

    def find_product_id_by_gtin(self, value) -> Optional[int]:
        """
        Resolve any GTIN encoding to the owning Product's id, or None (Story
        2.2, FR9).

        The input is normalized to the canonical 14-digit key (matching how
        add_identifier stores GTINs), so GTIN-8, UPC-A, EAN-13, and GTIN-14
        forms of one product all resolve to the same Product. Returns None if
        the input is not a valid GTIN (never raises) or no GTIN identifier
        matches. GTIN_UNVALIDATED rows are outside the GTIN namespace and are
        never matched.
        """
        try:
            key = gtin.normalize_gtin('' if value is None else str(value))
        except gtin.InvalidGtinError:
            return None
        session = self.Session()
        try:
            row = (session.query(ProductIdentifier)
                   .filter(ProductIdentifier.identifier_type == IdentifierType.GTIN.value,
                           ProductIdentifier.value == key)
                   .first())
            return row.product_id if row else None
        finally:
            session.close()

    # --- Scan resolution & search (Story 4.3) ------------------------------

    def search_products(self, query, filters=None, *,
                        limit: int = SEARCH_RESULTS_DEFAULT_LIMIT) -> List[Product]:
        """
        Free-text search across the catalog (Story 4.3, AD-17, FR36).

        AD-17's SOLE free-text search implementation: the scan fallthrough in
        `resolve_scan` below calls it today and Epic 8's search page calls the
        same method later, so there is never a second search path to keep in
        agreement. `query` is matched case-insensitively as a CONTIGUOUS
        substring — there is no tokenization, so `'RES 0805'` does not match a
        product described `'RES 10K 0805 1%'` and a one-character query matches
        most of the catalog. That is a property of the mechanism AD-17 defers
        to Epic 8, it is pinned by `TestSearchProducts` and recorded in the
        ledger, and it is worth knowing before treating the FR36 fallthrough as
        a working search. The match runs against six columns, in four groups:

        - `products.internal_id` (the label this shop printed),
        - `products.description`, `products.notes`,
        - `products.manufacturer`, `products.mpn`,
        - `product_identifiers.value`, EVERY identifier type — including
          `GTIN_UNVALIDATED`, which is outside the GTIN lookup namespace (AD-7)
          and is therefore only ever reachable through this search. "Reachable"
          means reachable by SUBSTRING, which for a `GTIN_UNVALIDATED` row is
          one-directional: it is stored exactly as it was typed, so scanning
          `'9506000134352'` finds a row stored as `'09506000134352'`, and
          scanning the ITF-14 form of a row stored in its 13-digit form finds
          nothing at all — the added leading zero is not a substring of what
          is stored. That asymmetry is pinned by `TestGtinResolution` and
          deferred; closing it needs either normalization at write time or the
          Epic 8 mechanism.

        What is deliberately NOT searched, so a reader does not have to diff
        this list against the `Product` model: `products.category_path`,
        `products.attributes` and the `product_tags` rows. AD-17 hands the
        field set to Epic 8 along with the mechanism, and widening it here
        would change what the fixed signature means without changing the
        signature.

        The *mechanism* is deliberately the simplest thing that satisfies the
        fallthrough. AD-17 defers ranking, relevance ordering, pagination,
        faceting and FULLTEXT to Epic 8; the signature here is what is fixed
        now, so Epic 8 can change the mechanism behind it without touching a
        call site. Results come back in ascending `products.id` — insertion
        order, deterministic and stable across repeated calls — which is an
        arbitrary-but-fixed order, not a relevance one.

        Results are additionally capped at `limit`. Note what ordering plus a
        cap amounts to: ascending id is not merely a display order, it is the
        SELECTION rule for which matches survive the cap, and the row cut first
        is the most recently created product — plausibly the one the operator
        just added. The result carries no total and no truncation flag, so a
        caller cannot say "showing 50 of 61". Both are deferred: a signal would
        have to reach `ScanResolution`, whose three fields AD-15 freezes.

        Four implementation choices worth stating, because each has a wrong
        obvious alternative:

        - Identifier values are matched with a correlated `EXISTS` rather than a
          join. `Product` has no `identifiers` relationship (every child model
          here is one-directional), and a join would return one row per matching
          identifier — so a product carrying three matching identifiers would
          appear three times. `EXISTS` collapses that to one row WITHOUT a SQL
          `DISTINCT`, which matters: under MariaDB's folding collation
          `DISTINCT` drops rows Python should have judged (the same hazard the
          ledger records against `get_field_value_suggestions`).
        - `func.lower()` is applied explicitly on both sides rather than
          relying on the column collation, so that ASCII case-insensitivity
          holds on SQLite (whose default collation is binary and would
          otherwise make the unit suite case-SENSITIVE) as well as on MariaDB.
          Be precise about what this does NOT buy: it is an ASCII fold only,
          and the two backends still disagree outside that range. SQLite's
          built-in `LOWER()` leaves non-ASCII untouched, so a product described
          `'WÜRTH'` is unreachable by any casing of that word under the unit
          suite, while MariaDB's `utf8mb4_unicode_ci` folds `Ü`/`ü` — and
          `LOWER()` does not change MariaDB's comparison collation, so there an
          accent-insensitive `cafe`/`café` match survives too. The divergence
          is the one already recorded at `app/database.py:1084-1088`; it is
          pinned by `TestSearchProducts` and deferred rather than papered over,
          because closing it means either a custom SQLite collation (an
          app-level engine change) or the Epic 8 mechanism decision AD-17
          defers.
        - No `IS NOT NULL` guard is needed on the nullable columns: `LIKE`
          against `NULL` yields `NULL`, which `OR` treats as not-true, so a
          product with a NULL description simply fails that disjunct.
        - The leading `%` means no index can be used and this scans the table.
          That is acceptable at the working set the PRD describes (hundreds to
          low thousands of products) and is precisely the cost Epic 8's chosen
          mechanism is expected to remove.

        Read-only: no commit, no audit log. The returned Products are detached
        ORM rows — their scalar columns stay readable, but do NOT touch a
        relationship attribute (e.g. `.purchases`) on them, which would
        lazy-load on a detached instance and raise.

        Args:
            query: The text to search for — a `str`, or None meaning "no
                query". Stripped with a bare `str.strip()`, which is WIDER than
                the route's `_clean_scan_input` (that one strips only
                `' \\t\\r\\n'`, deliberately preserving the separators an ECIA
                envelope is built from): here a leading GS or RS is noise in a
                search box, not structure. This is the one cleaning
                `resolve_scan` inherits by delegating here, and it is a
                property of the search entrypoint rather than a second copy of
                the scan trim rule. A blank, whitespace-only or None query
                returns `[]` rather than the whole catalog, as does text that
                cannot reach the database intact (`_is_storable_text`:
                unpaired surrogates and NULs) and text longer than
                SEARCH_QUERY_MAX_LENGTH, which no LIKE pattern can safely
                carry. LIKE wildcards in it (`%`, `_`, `\\`) are escaped and
                match literally.
            filters: Reserved for Epic 8's faceted filtering (AD-17). None or an
                empty mapping means "no filters"; anything else raises — see
                Raises.
            limit: Maximum number of products returned. Clamped to
                [1, SEARCH_RESULTS_MAX_LIMIT]; a non-integer — `bool` included,
                despite being an int subclass — falls back to
                SEARCH_RESULTS_DEFAULT_LIMIT, mirroring
                `get_field_value_suggestions`.

        Returns:
            Matching Products, ascending by id, at most `limit` of them.

        Raises:
            TypeError: if `filters` is neither None nor a Mapping, or if
                `query` is neither None nor a `str`. Both are caller faults
                that would otherwise degrade silently — see the guards below.
            NotImplementedError: if `filters` is a non-empty Mapping. Story 4.3
                fixes the parameter so Epic 8 changes no call sites, but
                implements no filter; silently ignoring one would hand a caller
                unfiltered rows it believes are filtered. Story 8.2 is where it
                lands.
        """
        # ALL the type checks first, then the combination check — the taxonomy
        # `ScanResolution.__post_init__` uses, and the order the Raises: block
        # above presents. Both arguments are checked before either verdict is
        # reached, so `search_products(b'zebra', {'a': 1})` reports the wrong
        # type it was handed rather than the unimplemented feature it also
        # asked for; a caller fixing the second would otherwise hit the first
        # on the next run.
        #
        # A non-`str` query is refused, not coerced. `str(b'zebra')` is
        # `"b'zebra'"` and a transport that forgot to decode would look like a
        # catalog with no matches; but bytes are not the only shape with that
        # failure, and they are not the worst. `str(object())` is `'<object
        # object at 0x7f...>'`, a query derived from a memory address that
        # differs between runs, and `str(10)` searched `'10'` and returned real
        # rows for `'10K'` — a wrong-typed caller getting plausible hits is
        # worse than one getting none. `resolve_scan` rejects a non-`str` at
        # its own door (via `classify`); the sibling entrypoint Epic 8 calls is
        # held to the same contract. None stays legal and means "no query" —
        # the I/O matrix pins `None` alongside `''` and `'   '`.
        if query is not None and not isinstance(query, str):
            raise TypeError(
                f'query must be str or None, not {type(query).__name__} — '
                f'decode or convert it rather than searching its repr.')
        # A non-Mapping `filters` must be named rather than reaching the
        # message builder below: `sorted(5)` raises a bare TypeError instead of
        # the documented NotImplementedError, and `sorted('abc')` explodes a
        # string into characters — the same coercion trap
        # `ScanResolution.__post_init__` rejects one module over.
        if filters is not None and not isinstance(filters, Mapping):
            raise TypeError(
                f'filters must be a mapping of facet name to value, got '
                f'{type(filters).__name__}.')

        if filters:
            # `sorted(map(repr, ...))` rather than `sorted(...)`: keys of mixed
            # types are not mutually comparable, and `sorted({1: 'a', 'b': 2})`
            # raises a bare `TypeError: '<' not supported between instances of
            # 'str' and 'int'` from inside the message builder — the very
            # substitution of a bare TypeError for the documented exception
            # that the guard above exists to prevent.
            raise NotImplementedError(
                f'search_products filters are Story 8.2 (AD-17); this story '
                f'fixes the parameter but implements no filter. Got: '
                f'{sorted(map(repr, filters))}.')

        q = ('' if query is None else query).strip()
        if not q:
            return []
        # A LIKE pattern has a length ceiling the caller has no reason to know
        # about: past it SQLite raises OperationalError, which would escape a
        # method contracted never to raise on scan text (NFR8). Answering `[]`
        # rather than truncating: a truncated pattern answers a DIFFERENT
        # question — it returns rows that do not contain the query — and
        # silently returning wrong hits is the failure this method's type guard
        # above already refuses to make. Unreachable from a scan (the route
        # caps input at 4096 before `resolve_scan` ever sees it); reachable
        # from Epic 8's search box, which is why the bound lives here.
        if len(q) > SEARCH_QUERY_MAX_LENGTH:
            return []
        # Same reason `resolve_scan` guards its scan text: text carrying an
        # unpaired surrogate cannot be bound at all, and text carrying a NUL
        # cannot be compared whole — SQLite truncates the LIKE pattern there,
        # so `'\x00'` alone would return the ENTIRE catalog and `'a\x00b'`
        # would return the rows ending in `a`. Nothing stored can equal or
        # contain either, so `[]` is the correct answer and not merely a safe
        # one; see `_is_storable_text`. This check runs before the pattern is
        # built, because the defect is in the pattern.
        if not _is_storable_text(q):
            return []

        # OverflowError joins the tuple because `int(float('inf'))` raises it
        # rather than ValueError, and the docstring promises every non-integer
        # falls back rather than escaping. `bool` is checked first and by type,
        # because it IS an int: `int(True)` is 1, so a caller passing a flag or
        # a truthiness-coerced request argument got exactly one row back from a
        # method documented to fall back to the default.
        if isinstance(limit, bool):
            limit = SEARCH_RESULTS_DEFAULT_LIMIT
        try:
            limit = int(limit)
        except (TypeError, ValueError, OverflowError):
            limit = SEARCH_RESULTS_DEFAULT_LIMIT
        limit = max(1, min(limit, SEARCH_RESULTS_MAX_LIMIT))

        pattern = f'%{_escape_like_wildcards(q.lower())}%'

        def _matches(column):
            return func.lower(column).like(pattern, escape='\\')

        identifier_match = (
            exists()
            .where(ProductIdentifier.product_id == Product.id)
            .where(_matches(ProductIdentifier.value))
        )

        session = self.Session()
        try:
            return (session.query(Product)
                    .filter(or_(
                        _matches(Product.internal_id),
                        _matches(Product.description),
                        _matches(Product.notes),
                        _matches(Product.manufacturer),
                        _matches(Product.mpn),
                        identifier_match,
                    ))
                    .order_by(Product.id.asc())
                    .limit(limit)
                    .all())
        finally:
            session.close()

    def resolve_scan(self, raw) -> ScanResolution:
        """
        Resolve one captured scan against the catalog (Story 4.3, FR36, AD-15).

        Classifies `raw` with the pure `app/utils/scan_router.classify()`, looks
        the result up where a lookup is defined, and falls through to
        `search_products` when nothing matched — so no scan dead-ends (FR36),
        with two deliberate exceptions, both of which answer without a lookup
        AND without a search: text that cannot be stored (the guard below), and
        an `ecia` envelope carrying no part number at all (only
        quantity/order/date identifiers), for which no part-number search could
        mean anything. Returns a `ScanResolution` in every case.

        "No dead ends" is a promise about the PATH, not a guarantee of hits:
        several arms can legitimately return no product and no hits, and the
        per-arm list below names each one it knows of, because Story 4.5 turns
        that state into a pre-filled create form rather than an error.

        **The config seam (AD-16).** `Config.GS1_INTERNAL_AI` and
        `Config.GS1_INTERNAL_TOKEN` are read here, in the body, on every call,
        and passed explicitly into the pure classifier — exactly as
        `encode_internal_payload` above passes them into `gs1.encode`. Neither
        this method nor the classifier holds a literal default, so one config
        change moves the label encoder and the scan router together with no code
        edit. The pair is never captured at import or cached on `self` (Config
        itself reads the environment once, so a changed .env still needs a
        process restart).

        **`raw` arrives already cleaned**, the same contract `classify()`
        states: the caller (`app/main/routes.py`'s `_clean_scan_input`) owns
        the scan trim rule and the scan length bound. This method restates
        neither — a service that re-cleaned its scan input would be a third
        copy of that rule rather than a shared one. Be precise about what that
        does and does not mean: `raw` is classified exactly as handed over, and
        the text that reaches a LOOKUP is untouched apart from the AIM strip.
        The text that reaches the fallthrough SEARCH is additionally subject to
        whatever `search_products` does to a query — a bare `str.strip()` and a
        pattern-length bound — because that is search-entrypoint behavior every
        caller of it gets, not a scan rule re-implemented here.

        **What each arm searches, and why it differs:**

        - `internal`: looks up `products.internal_id` (AD-3 makes it the
          scan-lookup business key). On a miss it searches
          `classification.normalized_value` — the bare, token-stripped id, which
          is what the column actually stores. The `<ai><token>` prefix is an
          encoding artifact present in no column, so searching the raw scan
          would find nothing by construction.
        - `gtin`: looks up a `GTIN` identifier row on
          `classification.normalized_value`, which the classifier already
          normalized to the canonical 14-digit key (AD-7: lookup is against the
          normalized-14 namespace, and `GTIN_UNVALIDATED` rows are outside it
          and are never matched by this arm). On a miss it searches the
          AIM-stripped raw digits as scanned, NOT the 14-digit key: the key was
          just searched exactly, so re-searching it adds nothing, while the
          scanned form can substring-match a `GTIN_UNVALIDATED` row, which is
          stored exactly as it was typed. "Can" is the operative word — the
          match is a substring one, so it bridges the encodings in only one
          direction. Scanning a shorter form finds a row stored in a longer,
          zero-padded one; scanning the padded form of a row stored short does
          NOT, and that scan is a genuine FR36 dead end (no product, no hits).
          Deferred rather than patched: the fix is normalizing
          `GTIN_UNVALIDATED` at write time or Epic 8's mechanism, both outside
          this story.
        - `free_text`: no lookup; searches the AIM-stripped raw.
        - `ecia` (Story 4.4, FR38): looks up the part numbers
          `app/utils/ecia.py` parsed off the label — `1P` first (the supplier
          part number, which the ECIA spec makes the required field), then `P`
          — never the raw envelope, whose control characters and record
          separators would be a query with no meaning. Which of the two a given
          distributor prints the manufacturer part number in is a property of
          that label, not of this system, so BOTH are tried against BOTH places
          a part number lives: the `products.mpn` column and an `MPN`
          identifier row. Values are trimmed and de-duplicated first, and the
          match is an equality one — never a substring. Be precise about what
          "equality" reaches, because it is not the same on both backends and
          this arm returns a single product rather than a hit list: the
          predicate is `column = value OR LOWER(column) = LOWER(value)`, which
          under SQLite (the only backend any test here runs) means
          byte-identical or ASCII-case-folded, and under MariaDB's
          `utf8mb4_unicode_ci` means whatever that collation equates —
          accent-insensitive and PAD SPACE, since `LOWER()` does not change
          MariaDB's comparison collation. So `WURTH-1` can land on a product
          stored `WÜRTH-1` in production and cannot in the unit suite. That is
          the same backend divergence `search_products` documents and the
          ledger records; it is wider here only in consequence, because there
          it adds a hit and here it can pick the landing. Exactly one product
          matching resolves to it; zero OR more than one resolves to nothing
          and falls through to a search on the FIRST candidate, because two
          products genuinely can share a part number and silently returning the
          oldest of several would answer a question nobody asked. Be exact
          about WHERE the sharing is possible, because the two homes are not
          alike: `products.mpn` is nullable and carries no unique constraint,
          so any number of products may hold the same one. Two MPN identifier
          ROWS cannot collide — `MPN` is global-scoped (`vendor_scope=''`) and
          `uq_product_identifiers_type_value_scope` is over
          `(identifier_type, value, vendor_scope)`, so the DB rejects the
          second, which is why `add_identifier` raises `ValidationError` there.
          Global scoping is what makes an identifier row UNIQUE across
          products, not what makes it shareable. The second real ambiguity is
          therefore a CROSS-home one: one product's `mpn` column colliding with
          another product's `MPN` identifier row, which nothing constrains and
          which `test_an_ambiguity_across_the_two_homes_also_falls_through`
          pins. Those two are the whole set.
          An envelope carrying no NON-BLANK part-number identifier is answered
          with no product and no hits, without any query — normally a label
          carrying only `Q`/`K`/`9D`, but a `1P` holding nothing but spaces
          reaches the same terminal state, since the candidates are trimmed
          before they are counted.

          Three consequences of "one query over both candidates, one search on
          the first", all real and none hypothetical, so a caller can plan
          around them rather than discover them:

          1. The count is over the UNION of the candidates, so a unique `1P`
             hit is discarded when `P` happens to match a DIFFERENT product —
             the arm sees two rows and calls it ambiguous. `1P` leads the
             candidate list but does not take precedence in the query. The
             right product USUALLY still reaches the operator, since it is in
             the `1P` search that follows, but as a hit rather than a landing —
             and not always: that search is bounded at
             `SEARCH_RESULTS_DEFAULT_LIMIT` rows ordered by id, so an exact
             match sitting behind enough substring matches on the same text is
             dropped from the list entirely. "Ambiguous falls through to hits"
             is therefore a statement about which QUERY runs, not a guarantee
             that the exact matches are in what comes back.
          2. Only the first candidate is searched, so a product reachable ONLY
             by the second one — a `P` value in a description, say, with `1P`
             matching nothing anywhere — comes back with no product and no
             hits. Presence of an extra identifier makes that label resolve to
             LESS than the same label carrying `P` alone.
          3. The two compose into the worst case, which is neither of them: if
             `1P` matches nothing and `P` matches two products EXACTLY, the
             union is ambiguous so both exact matches are discarded, and the
             fallthrough then searches `1P` and finds nothing. The arm holds
             two exact matches in hand and answers with no product and no hits.
             The same label carrying `P` alone returns both as hits.

          All three are recorded in the deferred-work ledger; closing any of
          them changes the frozen intent contract for this arm, whose fix is
          the same in every case — query per candidate in order and take the
          first unambiguous answer, at a cost of one more query.

          Two exclusions a reader would otherwise have to diff the model to
          find. (1) `VENDOR_SKU` identifier rows are not consulted, even though
          a distributor part number in `P` is conceptually one: `VENDOR_SKU` is
          vendor-scoped (AD-9), so its uniqueness is per vendor and an unscoped
          exact match could resolve a DigiKey label to a product identified by
          an identical Mouser number. The scan carries no vendor and FR39 names
          MPN as what a distributor scan pre-fills. `IdentifierType.MPN` is
          global-scoped, so this lookup correctly needs no `vendor_scope`
          filter. (2) The ASCII-case fold is one of the two disjuncts per
          candidate rather than the only one — see `_matches` in the arm for
          why a byte-identical comparison runs beside it, and for what
          non-ASCII case-insensitivity still does not do under SQLite.

          A note on the `free_text` arm above, since this arm's first sentence
          reads as though it contradicts it: an envelope whose records are
          unreadable never reaches here at all. `classify()` degrades it to
          `free_text` (AD-5, NFR8), and that arm then does search the raw
          envelope, separators and all. That is not the same thing as searching
          the envelope INSTEAD of a parsed part number — it is what "surface
          the raw scan for manual handling" means when there is nothing else
          left, and it usually returns nothing, which Story 4.5 lands on a
          create form. Note the asymmetry it creates: a label carrying only
          `Q`/`9D` classifies `ECIA` and terminates here with no query, while a
          label carrying only identifiers this system has no field for (`1T`,
          `4L`) classifies `free_text` and gets that raw search. Both are "a
          distributor label with no part number"; they differ because the first
          is recognized-and-useless and the second is unrecognized, and only
          the first can be told apart from damage.

        Text that gets *used* is AIM-stripped first via the exported
        `scan_router.strip_aim_prefix()`, never re-derived here.
        `classification.raw` deliberately keeps the prefix.

        Read-only, like `search_products`: there is no commit, no rollback and
        no audit log, so scan resolution is idempotent by construction. Session
        count per scan is one for a lookup that hits, one for a `free_text`
        scan (the search), and two for an `internal`/`gtin`/`ecia` MISS (the
        lookup, then `search_products`' own) — minus any search that answers
        without querying. `search_products` returns `[]` for text that is
        blank, unstorable or over-long before it opens anything, so an
        unencodable scan and an empty scan open ZERO, and a lookup miss whose
        fallthrough text is blank opens one rather than two. The `ecia` arm
        opens one for its lookup, or ZERO when the envelope carries no
        part-number identifier and it therefore neither looks up nor searches.
        The Product and every Product in `free_text_hits` are therefore
        detached rows: scalar columns stay readable, relationship attributes
        must not be touched.

        Args:
            raw: The scan text, already cleaned by the caller.

        Returns:
            A `ScanResolution`. Never None.

        Raises:
            TypeError: propagated from `classify` when `raw` is not a `str` — a
                caller fault, not a scan.
            gs1.InvalidGs1PayloadError: propagated UNCHANGED when the configured
                grammar is malformed. This is the one place this file
                deliberately does not do what `encode_internal_payload` does:
                that method translates the same exception into a
                `ValidationError` because its bad input is a user-supplied id,
                whereas here the input is a *deployment* fault. Translating it
                would dress a broken configuration up as a rejected scan, and
                swallowing it would silently disable rule 1 so every label this
                shop ever printed would quietly start resolving as free text.

            Database errors also propagate, as they do from every read method
            here — a backend failure must not masquerade as "no match".
        """
        classification = scan_router.classify(
            raw,
            ai=Config.GS1_INTERNAL_AI,
            token=Config.GS1_INTERNAL_TOKEN,
        )
        kind = classification.kind

        # NFR8 is a promise about `resolve_scan`, not only about the pure
        # classifier: no `str` scan may raise, and none may quietly answer a
        # different question. Classification alone cannot break either, but
        # this method is the first to send scan text to a database. Text that
        # will not encode to UTF-8 makes the driver raise UnicodeEncodeError on
        # the way out — verified with a lone surrogate ('\ud800'), which
        # `_clean_scan_input` passes through untouched. Text carrying a NUL
        # binds fine and then compares WRONG, because SQLite truncates a LIKE
        # pattern at the first NUL: '\x00' * 4096 — the classic wedge no-read,
        # and a vector this suite already had — resolved to every product in
        # the catalog. No stored value can equal or contain either shape, so
        # the honest answer is the no-match one, reached without a query.
        # Checking `raw` covers every arm: a GTIN candidate is all ASCII digits
        # by construction, and any other arm's text is derived from `raw`.
        if not _is_storable_text(raw):
            return ScanResolution(classification=classification, product=None,
                                  free_text_hits=())

        if kind is ScanKind.INTERNAL:
            session = self.Session()
            try:
                product = (session.query(Product)
                           .filter(Product.internal_id ==
                                   classification.normalized_value)
                           .first())
            finally:
                session.close()
            fallthrough_text = classification.normalized_value

        elif kind is ScanKind.GTIN:
            session = self.Session()
            try:
                # The same (type, value) namespace find_product_id_by_gtin
                # queries, inline rather than by delegation: that method takes
                # an unnormalized value and would re-run normalize_gtin on a key
                # the classifier already normalized, returns an id rather than a
                # row, and opens a third session per scan. The duplication is
                # one filter pair, and TestNamespaceAgreement pins the two
                # against drift.
                product = (session.query(Product)
                           .join(ProductIdentifier,
                                 ProductIdentifier.product_id == Product.id)
                           .filter(ProductIdentifier.identifier_type ==
                                   IdentifierType.GTIN.value,
                                   ProductIdentifier.value ==
                                   classification.normalized_value)
                           .first())
            finally:
                session.close()
            fallthrough_text = scan_router.strip_aim_prefix(classification.raw)

        elif kind is ScanKind.ECIA:
            # The candidate part numbers, in the order the docstring states:
            # `1P` first because the ECIA spec makes the supplier part number
            # the required field, then `P`. Which of the two a given
            # distributor prints the MANUFACTURER part number in is a property
            # of that distributor's label, not of this system, so both are
            # tried — hard-coding "1P is the MPN" would fail silently on any
            # label that does it the other way and the operator would create a
            # duplicate product. Read defensively (`or {}`) because
            # `ScanClassification` permits `ECIA` with None even though
            # `classify()` never produces it.
            fields = classification.ecia_fields or {}
            # Trimmed and de-duplicated on the way in. `parse_fields` keeps a
            # value exactly as the label carried it, which is right for the
            # parser — Story 4.5 pre-fills a form from those fields and must
            # show what was printed — but a part number is never legitimately
            # surrounded by spaces, and an untrimmed candidate can only ever
            # MISS the exact lookup while the fallthrough silently succeeds
            # (`search_products` strips its own query), so a padded label would
            # degrade to a hit list for no reason. Trimming also removes the
            # whitespace-only candidate, which is truthy and would otherwise
            # become `candidates[0]` and search for nothing, dead-ending a
            # label whose OTHER identifier was perfectly usable. The dedupe is
            # for the routine single-source part that prints the same number in
            # both fields: without it the same predicate is emitted twice.
            candidates = list(dict.fromkeys(
                value.strip()
                for value in (fields.get('1P'), fields.get('P'))
                if value and value.strip()))
            if not candidates:
                # An envelope carrying only quantity/order/date identifiers.
                # A legal terminal state, and the one place `resolve_scan`
                # still answers without searching: there is no part number, so
                # there is no question a part-number search could be asking.
                return ScanResolution(classification=classification,
                                      product=None, free_text_hits=())

            def _matches(column):
                # TWO disjuncts per candidate, and both are load-bearing.
                #
                # `func.lower()` on both sides, explicitly, is the same
                # construction `search_products` uses and for the same reason:
                # SQLite's default collation is binary, so relying on the
                # column's collation would make this lookup case-SENSITIVE
                # under the unit suite and case-insensitive in production.
                #
                # But that fold is ASCII-only on SQLite — `str.lower()` is
                # full-Unicode while SQLite's `LOWER()` leaves non-ASCII
                # untouched — so the two sides of a folded comparison can never
                # agree for a non-ASCII part number, and a stored 'WÜRTH-1'
                # scanned as the byte-identical 'WÜRTH-1' matched NOTHING: an
                # exact lookup failing on an exact value. The unfolded equality
                # closes that. Under SQLite it adds exactly the rows a
                # byte-identical value should have matched all along and
                # nothing else, because that backend's default collation is
                # binary; what it does NOT buy there is non-ASCII
                # case-INsensitivity ('würth-1' still misses), which needs an
                # engine-level collation or Epic 8's mechanism decision.
                #
                # Under MariaDB it is NOT a byte comparison and this disjunct
                # is not the narrow one: `=` runs under the column's
                # `utf8mb4_unicode_ci` collation, which is case- AND
                # accent-insensitive and PAD SPACE, and `LOWER()` does not
                # change that, so both disjuncts are collation-folded and
                # 'WURTH-1' can equal a stored 'WÜRTH-1'. The docstring states
                # the consequence: what "equality" reaches here is
                # backend-dependent, and this arm picks a landing rather than
                # adding a hit, so the divergence `search_products` already
                # records costs more in this seam than in that one.
                return or_(*(
                    predicate
                    for value in candidates
                    for predicate in (column == value,
                                      func.lower(column) == value.lower())))

            # An EXISTS rather than a join, for the reason search_products
            # states: a product matching on both its `mpn` column and an
            # identifier row (or on two identifier rows) must appear ONCE,
            # without a SQL DISTINCT. Only IdentifierType.MPN is consulted.
            # VENDOR_SKU rows are deliberately outside this lookup — see the
            # docstring.
            identifier_match = (
                exists()
                .where(ProductIdentifier.product_id == Product.id)
                .where(ProductIdentifier.identifier_type ==
                       IdentifierType.MPN.value)
                .where(_matches(ProductIdentifier.value))
            )

            session = self.Session()
            try:
                # limit(2) because the only question is "exactly one, or not",
                # and fetching the rest would only cost rows nothing reads. Two
                # rows are genuinely reachable: `products.mpn` carries no
                # unique constraint, and a product's `mpn` column can collide
                # with a DIFFERENT product's MPN identifier row, which nothing
                # cross-checks. NOT two identifier rows — `MPN` is
                # global-scoped, so `uq_product_identifiers_type_value_scope`
                # already forbids that pair (see the docstring).
                matches = (session.query(Product)
                           .filter(or_(_matches(Product.mpn),
                                       identifier_match))
                           .order_by(Product.id.asc())
                           .limit(2)
                           .all())
            finally:
                session.close()
            # Zero OR more than one is "no product": silently returning the
            # oldest of several would answer a question nobody asked. The
            # fallthrough below covers both, and since `search_products`
            # searches `mpn` too, an ambiguous set comes back as hits.
            product = matches[0] if len(matches) == 1 else None
            fallthrough_text = candidates[0]

        else:
            # ScanKind.FREE_TEXT, rule 4 — the fallthrough that always matches,
            # so there is nothing to look up and the search always runs.
            product = None
            fallthrough_text = scan_router.strip_aim_prefix(classification.raw)

        if product is not None:
            return ScanResolution(classification=classification,
                                  product=product, free_text_hits=())

        # FR36: a miss is never a dead end — it becomes a search, within the
        # same scan, through AD-17's single entrypoint. search_products manages
        # its own session and returns [] for a blank query (an empty scan), so
        # this never degenerates into "every product".
        return ScanResolution(
            classification=classification,
            product=None,
            free_text_hits=tuple(self.search_products(fallthrough_text)),
        )
