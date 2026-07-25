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
from typing import Dict, List, Optional, Tuple
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import sessionmaker, defer
from sqlalchemy import create_engine, case, func, or_
from sqlalchemy.exc import IntegrityError

from .database import Product, Purchase, Attachment, ProductIdentifier
from .models import IdentifierType, VENDOR_SCOPED_IDENTIFIER_TYPES
from .mariadb_storage import MariaDBStorage
from .exceptions import ValidationError
from .utils import gtin, gs1
from .utils import category as category_util
from .utils import internal_id as internal_id_util
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
# (Story 3.1). Deliberately shaped exactly like
# InventoryService.FIELD_SUGGESTION_COLUMNS — public field name -> Product
# column attribute name — so the ONE endpoint
# (/api/inventory/field-suggestions/<field>) can dispatch on membership without
# a second URL or a parallel field set (AD-14). No products query belongs in
# the inventory service, which is why this lives here rather than there
# (AD-1/AD-2).
FIELD_SUGGESTION_COLUMNS = {
    'category_path': 'category_path',
}


def _clean(value):
    """Trim strings and coerce blank strings to None (backfill-forward: absent
    optional fields must store NULL, not '')."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


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
        # Unreachable while category_path is the only whitelisted field, and
        # deliberately loud rather than a plausible-looking fallback: a second
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
        Return distinct existing values for a whitelisted Product field,
        suitable for autocomplete on the product Add/Edit forms (FR14, FR15).

        The category "tree" IS the distinct set of assigned
        products.category_path values — there is no node table — so this
        DISTINCT query is the whole vocabulary source. It accretes purely from
        use: nothing is offered until some product carries it, and ancestors
        are not synthesized (typing `a/b/c` makes `a/b/c` available, not bare
        `a`).

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

        column = getattr(Product, column_name)
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
        else:
            # Unreachable while category_path is the only whitelisted field.
            # NOT a fallback to normalize_suggestion_value: that method answers
            # a different question (what to ECHO, where a rejected query is
            # None) and reading its None here would mean "no filter" — the
            # whole-vocabulary leak the branch above exists to prevent. A
            # second catalog field registers its matching rule here, next to
            # its echo rule in normalize_suggestion_value.
            raise NotImplementedError(
                f'No suggestion matching rule registered for {field!r}')

        # Escape user-supplied LIKE wildcards so a query like "10%" doesn't act
        # as a wildcard. SQLAlchemy's like() takes an escape character we
        # declare here. (Same helper as the inventory service — kept local so
        # neither side has to import the other across the AD-1 seam.)
        def _escape_like(s: str) -> str:
            return (
                s.replace('\\', '\\\\')
                .replace('%', '\\%')
                .replace('_', '\\_')
            )

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
