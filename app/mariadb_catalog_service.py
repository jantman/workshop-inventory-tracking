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
from sqlalchemy import case, exists, func, or_
from sqlalchemy.exc import IntegrityError

from .database import Product, Purchase, Attachment, ProductIdentifier, ProductTag
from .models import (IdentifierType, ScanKind, ScanResolution,
                     VENDOR_SCOPED_IDENTIFIER_TYPES)
from .mariadb_storage import MariaDBStorage
from .db import resolve_engine
from .exceptions import ConfigurationError, ValidationError
from .utils import gtin, gs1
from .utils import category as category_util
from .utils import internal_id as internal_id_util
from .utils import scan_router
from .utils import sql_text
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

# How many items a collision message may name before it starts summarizing:
# tags in `set_product_tags`, and in `rename_tag` both the conflicting
# spellings and the product ids carrying them. A flash listing every one of
# MAX_TAGS_PER_PRODUCT (50) tags is not actionable — and the product-id list
# has no ceiling of its own at all, since every product carrying the source tag
# could end up in it, which is the stronger reason to bound it.
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
# rule and not a second copy of the scan trim (`MAX_SCAN_LENGTH` lives in
# app/utils/scan_input.py): it is a database-safety bound, because a LIKE
# pattern has a length limit that a search box has no reason to respect.
# SQLite raises `OperationalError: LIKE or GLOB pattern too complex` past
# SQLITE_MAX_LIKE_PATTERN_LENGTH (50000, and escaping doubles the query's
# metacharacters on the way there), which would break NFR8's "no scan text
# raises" on the only backend the suite runs. 4096 is far under that on both
# backends and coincides with the route's own scan cap, so no scan can reach it.
SEARCH_QUERY_MAX_LENGTH = 4096


def _clean(value):
    """Trim strings and coerce blank strings to None (backfill-forward: absent
    optional fields must store NULL, not '').

    Shared by the product write path -- `manufacturer`, `mpn`, `description`,
    `notes` -- and by `record_purchase`'s `vendor`, `vendor_sku`,
    `order_number` and `source_url`. NOT by every writer of those purchase
    columns: `record_amazon_purchase` sets `vendor` from the already-stripped
    vendor scope and `vendor_sku` from the ASIN, neither through here. So this
    is a list of callers, not a guarantee about columns.

    For `mpn` the trim carries weight the others' does not, which is why it
    belongs here and not at either route. `create_product` and `update_product`
    are that column's only writers, so what this strips is what `_ecia_match`
    compares a scanned part number against; `add_identifier` strips an `MPN`
    identifier row's value the same way, and `_ecia_candidates` strips what it
    queries BY. A padded stored value would miss the exact lookup and silently
    degrade to the free-text fallthrough, which finds it anyway by substring
    (DW-7). Leading whitespace is what bites on either backend; a trailing pad
    of ordinary spaces misses under the unit suite's SQLite but compares equal
    in production, where `utf8mb4_unicode_ci` is PAD SPACE -- which pads U+0020
    and nothing else, so a trailing tab or newline misses on both.

    Two limits, so that agreement is not read as wider than it is:
    `_ecia_candidates` ALSO drops what `sql_text.is_storable_text` rejects and
    nothing here does, and `add_identifier`'s `str()` coercion is not copied —
    a non-string passes through to SQLAlchemy, which stringifies it into the
    column rather than raising.
    """
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


# How many rows the suggestion read turns into ORM row objects at a time, and
# that is ALL it bounds. Not transfer — the query itself is unbounded for the
# reason `get_field_value_suggestions` states, and no client-side batching
# changes what the server sorts or sends. Not process memory either, since a
# buffering driver has the whole result in hand before the first batch is
# built. Comfortably above the 50-value ceiling, so the ordinary case does one
# batch and stops.
SUGGESTION_ROW_BATCH = 100

# The two ECIA data identifiers a part-number lookup may be built from, in the
# order they are tried (Story 4.4, FR38). `1P` leads because the ECIA spec makes
# the supplier part number the required field; which of the two a given
# distributor prints the MANUFACTURER part number in is a property of that
# label, not of this system, so both are tried rather than one being guessed.
_ECIA_CANDIDATE_KEYS = ('1P', 'P')


def _ecia_candidates(classification) -> List[str]:
    """
    The part numbers an `ecia` classification may be looked up and searched by.

    The ONE home for the candidate rule, because three places need exactly the
    same list and a second copy of it is a rule that can drift: `resolve_scan`'s
    lookup walk, its per-candidate fallthrough, and `scan_search_text` — which
    the route calls to rebuild the `q` the operator's browser will send back.
    That last caller is why this is a module-level function taking a
    classification rather than something private to the arm.

    Four filters, each closing a defect rather than expressing a preference,
    applied in this order:

    - **Trimmed.** `ecia.parse_fields` keeps a value exactly as the label
      carried it, which is right for the parser — Story 4.5 pre-fills a create
      form from those fields and must show what was printed — but a part number
      is never legitimately surrounded by spaces, and an untrimmed candidate can
      only ever MISS the exact lookup while the fallthrough silently succeeds
      (`search_products` strips its own query). The trim lives here so what 4.5
      pre-fills is still verbatim.
    - **Non-blank.** A `1P` holding three spaces is truthy, so before the trim
      it became the first candidate and the fallthrough searched for nothing,
      dead-ending a label whose OTHER identifier was perfectly usable.
    - **Storable** (`sql_text.is_storable_text`, DW-80). A candidate carrying a
      NUL or an unpaired surrogate cannot be bound or cannot be compared whole,
      so nothing stored can equal or contain it; dropping it from the LIST
      rather than guarding the query means it can be neither looked up nor
      searched nor reported as the searched text, and a CLEAN candidate beside
      it still resolves. This is the per-arm half of the guard that used to
      judge the whole envelope — under which an unstorable `K` order number or
      `9D` date, in a record no query ever touches, suppressed a part-number
      lookup that would have landed.
    - **De-duplicated, folding ASCII case.** The routine single-source part
      prints the same number in both fields; without this it would be looked up
      twice and searched twice for one answer. Comparing the values EXACTLY
      missed the near-routine variant of that — `1P='ABC-9'` beside
      `P='Abc-9'` — so the second spelling still cost a lookup and a search
      that could not add anything: both consumers fold ASCII case already
      (`_ecia_match`'s `LOWER(column) = LOWER(candidate)` disjunct, and
      `search_products`' `LOWER(column) LIKE LOWER(q)`), so for an ASCII value
      the second candidate's match set is provably a SUBSET of the first's.
      The `isascii()` half of the key is load-bearing rather than defensive:
      Python's `str.lower()` is full-Unicode while SQLite's `LOWER()` is
      ASCII-only, so `'WÜRTH-1'` and `'WüRTH-1'` fold equal HERE and not in the
      database — merging them would drop a lookup the binary
      `column = candidate` disjunct can still satisfy (verified: `_ecia_match`
      finds a product stored `WÜRTH-1` for the first spelling and not for the
      second). Non-ASCII values are therefore compared exactly, as before. The
      FIRST-seen spelling is the candidate that survives, so `1P` still leads
      and the text reported as searched is the one the label actually printed
      there.

    Reads `ecia_fields` defensively (`or {}`) because `ScanClassification`
    permits `ECIA` with None even though `classify()` never produces it, and
    returns `[]` for every non-`ecia` classification by construction — no other
    kind carries the mapping at all.

    Args:
        classification: Any `ScanClassification`.

    Returns:
        A fresh list of candidate part numbers, `1P` before `P`, possibly empty.
    """
    fields = classification.ecia_fields or {}
    candidates = []
    seen = set()
    for key in _ECIA_CANDIDATE_KEYS:
        value = (fields.get(key) or '').strip()
        if not value or not sql_text.is_storable_text(value):
            continue
        # ASCII values fold; non-ASCII ones do not, because only the ASCII fold
        # is one both backends agree with. See the docstring above.
        seen_key = value.lower() if value.isascii() else value
        if seen_key not in seen:
            seen.add(seen_key)
            candidates.append(value)
    return candidates


def _fallthrough_text(classification) -> str:
    """
    The text the three PURE arms fall through to a search on.

    The ONE home for that rule, in the literal sense: `resolve_scan`'s shared
    tail calls this and so does `scan_search_text`, so neither derives it
    independently. Moving the rule out of the route and into this module would
    otherwise have relocated the duplicate rather than removed it — the two
    copies would simply have been a few hundred lines apart instead of a module
    apart, which is a harder drift to notice, not an easier one.

    `ecia` is excluded BY CONSTRUCTION and not by omission: its text is per
    candidate and is a fact about the database (which candidate's search came
    back non-empty), so it cannot be a pure function of the classification at
    all. `_ecia_fallthrough` owns it, and `resolve_scan`'s `ecia` arm returns
    before the shared tail, so the tail only ever sees the other three.

    - `internal` -> `normalized_value`, the bare token-stripped id, which is
      what `products.internal_id` actually stores; the `<ai><token>` prefix is
      an encoding artifact present in no column, so searching the raw scan
      would find nothing by construction.
    - `gtin` and `free_text` -> the AIM-stripped raw scan. For `gtin` that is
      deliberately NOT the normalized 14-digit key: the key was just looked up
      exactly, so re-searching it adds nothing, while the scanned form can
      substring-match a `GTIN_UNVALIDATED` row stored exactly as it was typed.

    Args:
        classification: A `ScanClassification` of kind INTERNAL, GTIN or
            FREE_TEXT. ECIA is not a legal argument — it has no single text.

    Returns:
        A `str`, possibly empty.

    Raises:
        ValueError: For an ECIA classification. Enforced rather than merely
            documented because the silent answer would be the AIM-stripped RAW
            ENVELOPE — separators and all — which is the one text this arm must
            never search, and which no caller could tell apart from a legitimate
            free-text fallthrough. Both callers branch on `kind` before reaching
            here, so this raises for nobody today; that is the point.
    """
    if classification.kind is ScanKind.ECIA:
        raise ValueError(
            'ecia has no single fallthrough text — its text is per candidate; '
            'use CatalogService.scan_search_text()')
    if classification.kind is ScanKind.INTERNAL:
        return classification.normalized_value
    return scan_router.strip_aim_prefix(classification.raw)


class CatalogService:
    """Service for managing catalog Products through the MariaDB backend."""

    def __init__(self, storage: MariaDBStorage = None):
        """Initialize with MariaDB storage."""
        if storage is None:
            storage = MariaDBStorage()

        self.storage = storage

        # Direct database access for queries (same pattern as InventoryService).
        # The engine belongs to the storage (DW-32).
        self.engine = resolve_engine(storage)
        self.Session = sessionmaker(bind=self.engine)

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

        Text that is not storable (`sql_text.is_storable_text`) yields None for
        the same reason, and the reason is worth stating because the column
        would in fact accept it: a path carrying a NUL can be written, but no
        suggestion or search could ever match it back, so offering to create
        one is offering to file a product where the operator cannot find it.
        The echo has to agree with the lookup — a `normalized` value beside an
        empty `suggestions` list is exactly the "not found, create it?" signal.

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
        if isinstance(value, str) and not sql_text.is_storable_text(value):
            return None
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
        products.category_path values — there is no node table — so this query
        is the whole vocabulary source. It accretes purely from
        use: nothing is offered until some product carries it, and ancestors
        are not synthesized (typing `a/b/c` makes `a/b/c` available, not bare
        `a`). The tag vocabulary (Story 3.3, `tags`) works the same way over
        product_tags.tag: there is no vocabulary table, and a tag stops being
        offered when the last product drops it.

        "Distinct" is decided in PYTHON, case-insensitively, and nowhere else —
        the SQL carries no DISTINCT, for the same reason `list_category_paths`
        and `list_tags` do their own grouping. See the read loop below.

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
                values in alphabetical order. Text that cannot reach the
                database intact (`sql_text.is_storable_text`: NULs and unpaired
                surrogates) answers `[]` without querying.
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

        # Judged on the argument AS PASSED, before normalization, and answered
        # without opening a session — the same shape `resolve_scan` uses on its
        # whole `raw` envelope. Normalization only strips whitespace and
        # separators, so a NUL survives it and reaches the LIKE pattern either
        # way; there it truncates the pattern to a prefix of itself, and a
        # bare `'\x00'` degenerates to the `%` that offers the WHOLE vocabulary
        # (see `sql_text.is_storable_text`). `[]` is the correct answer and not
        # merely a safe one: no value this application MEANS to store can equal
        # or contain text that cannot be compared whole — a premise the write
        # path does not yet enforce, which `is_storable_text` records. This is
        # HTTP 200 with no suggestions, never an error — the endpoint's
        # contract does not change.
        if isinstance(query, str) and not sql_text.is_storable_text(query):
            return []

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
                escaped = sql_text.escape_like_literal(q)
                pattern = f'%{escaped}%'
                base = base.filter(
                    func.lower(column).like(
                        pattern, escape=sql_text.LIKE_ESCAPE_CHAR)
                )
                rank = case(
                    (func.lower(column) == q, 0),
                    (func.lower(column).like(
                        f'{escaped}%', escape=sql_text.LIKE_ESCAPE_CHAR
                    ), 1),
                    else_=2,
                )
                base = base.order_by(rank, func.lower(column), column)
            else:
                base = base.order_by(func.lower(column), column)

            # SQL narrows, Python decides — the same division that
            # `list_category_paths` and `list_tags` make. There is deliberately
            # NO `.distinct()` here: MariaDB's folding collation would collapse
            # `café` and `cafe` (and any pre-migration case variant) into ONE
            # row before the pass below ever sees them, so one of two genuinely
            # distinct stored values would never be offered, and no amount of
            # over-fetching can restore a row the database already dropped.
            #
            # Without DISTINCT a fetch limit counts ROWS, not values, so the
            # old `limit * 3 + 10` ceiling had to go with it: 100 products
            # sharing one category_path would fill it and return a single
            # suggestion where ten distinct ones exist. A larger row ceiling
            # only moves that starvation threshold — it does not remove it —
            # so the query is left unbounded, which is what every sibling
            # listing method in this class already does (see the note on
            # SEARCH_RESULTS_DEFAULT_LIMIT: the unbounded vocabulary read is a
            # known, ledgered property of this table's screens, not a new one).
            #
            # What the lazy read below DOES bound is the Python side: rows
            # arrive already ordered, so the first `limit` distinct values are
            # the right ones and no further row is turned into a Python object.
            # It does NOT bound what crosses the wire — a buffering driver has
            # already fetched everything, and PyMySQL's server-side cursor
            # drains the remainder when the cursor closes. The row count, not
            # the transfer, is what the `ORDER BY` already forced.
            #
            # The `column` tiebreak breaks the ties DISTINCT used to hide:
            # without it every duplicate row sorts equal, and the early break
            # lets the plan decide which spelling of a value the operator is
            # offered. It makes the ordering TOTAL only under a binary
            # collation — SQLite, where the suite runs. Under MariaDB's folding
            # `_ci` collation the tiebreak column compares case- and
            # accent-insensitively too, so genuine case variants still tie on
            # both keys and the spelling offered stays plan-dependent there.
            # Deferred: closing it needs a `COLLATE utf8mb4_bin` tiebreak
            # behind a dialect branch the SQLite-only suite cannot verify.
            seen_lower = set()
            unique = []
            for (value,) in base.yield_per(SUGGESTION_ROW_BATCH):
                v = value.strip() if value else ''
                if not v:
                    continue
                key = v.lower()
                if key in seen_lower:
                    continue
                seen_lower.add(key)
                unique.append(v)
                if len(unique) >= limit:
                    break

            return unique

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
        # Normalization strips whitespace and separators, so a NUL or an
        # unpaired surrogate survives it and reaches BOTH
        # `descendant_like_pattern` LIKEs below. SQLite truncates such a
        # pattern at the NUL, which NARROWS both subtree scans: a narrowed
        # `moving` set merely produces the "No products are filed under…"
        # rejection, but a narrowed `blockers` set is how the branch merge this
        # method exists to refuse could slip through unnoticed. Refused up
        # front, before the session opens, so nothing is written either way —
        # and so the docstring's existing "unstorable" promise is true in both
        # senses. See `sql_text.is_storable_text`.
        #
        # RAISES here, where the suggestion lookups above answer `[]`, and the
        # rule behind the difference is the method's own: a read is being asked
        # a question and "nothing matches" is a true answer to it, while a
        # rename is being told to change rows and silently changing none is
        # not. This one also judges the CANONICAL value rather than the
        # argument as typed, because the canonical value is what the patterns
        # and the audit key are built from.
        if not sql_text.is_storable_text(old_canonical):
            raise ValidationError(
                'The category to rename contains characters that cannot be '
                'stored or matched.',
                field='old_path', value=str(old_path))
        if not sql_text.is_storable_text(new_canonical):
            raise ValidationError(
                'The new category path contains characters that cannot be '
                'stored or matched.',
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

    def rename_tag(self, old_tag, new_tag) -> Tuple[int, int]:
        """
        Rename a tag across every product carrying it, MERGING it into the
        destination where a product already carries that too, and return
        (renamed, merged) (DW-48, FR16).

        Both arguments are normalized first, so the operator may type
        `'  SSR '` for the stored `ssr`. Every affected row is loaded on ONE
        session, rewritten or deleted, and committed ONCE: either every
        carrying product ends up on the new tag or none does.

        That is a promise about the rows the SELECT below SAW, not about the
        tag as a whole: nothing is locked, so a concurrent writer that ADDS the
        source tag to some other product between that SELECT and the COMMIT
        leaves that product behind, still carrying a tag this rename reported
        having moved everywhere. `rename_category_path` documents the same
        limitation on its own check-then-write, and for the same reason: this
        is a single-operator workshop application, and the guarantee is against
        the operator's own mistakes, not against a race.

        A rename onto a tag that ALREADY EXISTS is a MERGE, not a rejection —
        the opposite of `rename_category_path`, and for the reason that method
        states in reverse. A Product carries at most one category, so folding
        two branches together would have to discard one of them; a Product
        carries many tags, so the union of two tag sets is lossless and
        well-defined. A product already carrying the destination simply has its
        source row DELETED (it would otherwise become a duplicate the unique
        constraint refuses), which is what the second return value counts.

        What is refused is the OTHER collision kind, the one Python cannot
        resolve on its own: `product_tags.tag` is `utf8mb4_unicode_ci`, which
        folds case AND accents, so a product carrying `café` and `ssr` cannot
        take a rename of `ssr` -> `cafe` — the two are one row to the index and
        two deliberately different strings to the operator. Silently dropping
        either is the one outcome neither this method nor `set_product_tags`
        allows, so it is named and refused with nothing written. That check
        runs BEFORE any row is touched, which is what leaves the IntegrityError
        handler below as a backstop for a concurrent writer alone.

        SQL narrows, Python decides. The single query matches under the
        column's collation, so it also hands back near-misses (`café` for a
        `cafe` filter); membership in the moving set and in the occupied set is
        settled by exact Python string equality, never by what the SQL matched.
        A folded near-miss on a product that is NOT moving is left exactly
        where it is.

        Unlike create_product/update_product, failures are RAISED, not
        swallowed into a False: a refused rename is an operator-facing decision
        that has to explain itself.

        Args:
            old_tag: The tag to rename, as typed.
            new_tag: The tag it becomes, as typed.

        Returns:
            (renamed, merged): how many rows were rewritten to the new tag, and
            how many were removed because their product already carried it.
            Their sum is the number of products affected.

        Raises:
            ValidationError: with field='old_tag' when the source is blank,
                unusable, unstorable or carried by no product; with
                field='new_tag' when the destination is blank, unusable,
                unstorable, identical to the source, or folds onto a tag a
                moving product already carries. Nothing is written in any of
                those cases. Any integrity failure that is NOT a duplicate key
                keeps its own identity and is re-raised.

                The concurrent-writer case additionally carries
                `retryable=True`, the same signal `set_product_tags` sets:
                nothing about the rename is wrong and the identical submission
                succeeds once the racing transaction is done, unlike a folded
                collision, which is refused for as long as the tags stay as
                they are.
        """
        from .logging_config import log_audit_operation

        # --- Argument checks run BEFORE the session is opened: they are pure,
        # they can be answered without the database, and keeping them out here
        # means the handlers below never have to ask whether a session exists.
        # (A rejection is a request error, not a 500: the util's
        # InvalidTagError never leaks out.) ---
        try:
            old_canonical = tag_util.normalize_tag(old_tag)
        except tag_util.InvalidTagError as e:
            raise ValidationError(str(e), field='old_tag', value=str(old_tag))
        try:
            new_canonical = tag_util.normalize_tag(new_tag)
        except tag_util.InvalidTagError as e:
            raise ValidationError(str(e), field='new_tag', value=str(new_tag))

        if old_canonical is None:
            raise ValidationError(
                'Select a tag to rename.',
                field='old_tag', value=str(old_tag))
        if new_canonical is None:
            raise ValidationError(
                'Enter the new tag.',
                field='new_tag', value=str(new_tag))
        # Normalization collapses whitespace and lowercases, so a NUL or an
        # unpaired surrogate survives it and reaches the equality filter below
        # as a bound parameter. A surrogate cannot be encoded at all (the
        # driver raises), and a NUL compares as something other than what it
        # says on at least one backend — so the source would match nothing
        # (reported as the wrong problem) or the destination would be WRITTEN
        # in a form no later lookup could find. Refused up front, before the
        # session opens, so nothing is written either way. See
        # `sql_text.is_storable_text`.
        if not sql_text.is_storable_text(old_canonical):
            raise ValidationError(
                'The tag to rename contains characters that cannot be stored '
                'or matched.',
                field='old_tag', value=str(old_tag))
        if not sql_text.is_storable_text(new_canonical):
            raise ValidationError(
                'The new tag contains characters that cannot be stored or '
                'matched.',
                field='new_tag', value=str(new_tag))
        if old_canonical == new_canonical:
            # Refused on the arguments alone, whether or not the tag exists.
            # `ssr` -> `SSR` normalizes to the same value, so there is nothing
            # to rename and no row to report having renamed.
            raise ValidationError(
                f"'{new_canonical}' is already this tag — nothing to rename.",
                field='new_tag', value=new_canonical)

        # Keyed on the CANONICAL source, matching the `changes` payload below:
        # keying on the value as typed would file the same tag's history under
        # `tag:  SSR ` and `tag:ssr` depending on how the operator spelled it
        # that day.
        audit_id = f'tag:{old_canonical}'

        session = self.Session()
        try:
            # ONE query for both tags. Under MariaDB's collation the equality
            # filter also matches folded near-misses, which is deliberate: they
            # are exactly what the partition below has to see in order to
            # refuse the one collision it cannot resolve. The SQL narrows; the
            # exact Python comparisons decide.
            rows = (session.query(ProductTag)
                    .filter(or_(ProductTag.tag == old_canonical,
                                ProductTag.tag == new_canonical))
                    .all())

            moving = [row for row in rows if row.tag == old_canonical]
            occupied = {row.product_id for row in rows
                        if row.tag == new_canonical}
            # Empty on SQLite (binary collation), non-empty only where the
            # database folded something onto one of the two tags.
            folded = [row for row in rows
                      if row.tag not in (old_canonical, new_canonical)]

            if not moving:
                raise ValidationError(
                    f"No products carry tag '{old_canonical}'.",
                    field='old_tag', value=old_canonical)

            moving_products = {row.product_id for row in moving}
            # A folded row on a product that is NOT moving is none of this
            # rename's business — `café` stays put while `cafe` is renamed away
            # from underneath it. A folded row on a product that IS moving is
            # the refusal: that product already carries a tag the index treats
            # as the destination, so rewriting its source row would collide
            # with a row it also means to keep. Detected here, before anything
            # is written, rather than left to the IntegrityError below — a
            # rolled-back flush cannot say WHICH products were involved, and
            # that is the only actionable part of the message.
            #
            # A folded row on a MOVING product can only be folding onto the
            # destination, never onto the source, and that is what lets the
            # message below call these rows "the same tag" as the destination
            # without checking which side of the filter each one matched:
            # `uq_product_tags_product_tag` is under the same folding
            # collation, so one product physically cannot hold both `ssr` and a
            # spelling the index reads as `ssr`. If that constraint ever stops
            # folding, this message starts lying and the partition has to be
            # split by side.
            conflicts = [row for row in folded
                         if row.product_id in moving_products]
            if conflicts:
                # Both lists are capped, and the cap is STATED: an operator who
                # fixes the named products and hits the identical-looking error
                # again would otherwise have no way to know the list was ever
                # partial (`set_product_tags` bounds its own collision message
                # the same way, for the same reason).
                shown = sorted({row.product_id for row in conflicts})
                listed = ', '.join(str(pid)
                                   for pid in shown[:MAX_TAGS_NAMED_IN_ERROR])
                if len(shown) > MAX_TAGS_NAMED_IN_ERROR:
                    listed += f', ... ({len(shown)} in total)'
                # The spellings are capped and marked the same way, for the
                # same reason: a silently sliced list of spellings sends the
                # operator to fix the ones it named, and the rename is refused
                # again by a spelling that was there all along and never
                # appeared on screen.
                distinct = sorted({row.tag for row in conflicts})
                spellings = ', '.join(
                    f"'{tag}'" for tag in distinct[:MAX_TAGS_NAMED_IN_ERROR])
                if len(distinct) > MAX_TAGS_NAMED_IN_ERROR:
                    spellings += f', ... ({len(distinct)} in total)'
                raise ValidationError(
                    f"Cannot rename to '{new_canonical}': product(s) {listed} "
                    f'already carry {spellings}, which the database treats as '
                    f'the same tag. Rename those first, or pick another '
                    f'destination.',
                    field='new_tag', value=new_canonical)

            # The merge, decided in Python and applied as a DELETE: a product
            # already carrying the destination would otherwise end up with two
            # rows the unique constraint refuses — and a tag set is a set, so
            # dropping the duplicate loses nothing.
            merges = [row for row in moving if row.product_id in occupied]
            rewrites = [row for row in moving
                        if row.product_id not in occupied]
            # Captured HERE, before the deletes below: the merge is the one
            # part of this rename that renaming back does NOT undo (that would
            # carry the destination's original members along with it), and a
            # count cannot say WHICH products lost the old tag. Since the audit
            # log is the only record the operation leaves, the ids go in it, or
            # the merge is unreconstructible. Read now because a deleted row
            # stops being able to answer for its product_id once the session
            # has flushed and committed.
            merged_ids = sorted(row.product_id for row in merges)

            try:
                for row in merges:
                    session.delete(row)
                if merges:
                    # Deletes are flushed FIRST, deliberately, for the reason
                    # `set_product_tags` documents: SQLAlchemy's unit of work
                    # emits inserts and updates before deletes, so a row on its
                    # way out would still be present when a sibling row is
                    # rewritten onto the destination — and under the folding
                    # unique index that is a collision with a row that is
                    # already leaving. Same transaction either way; only the
                    # statement order changes.
                    session.flush()
                for row in rewrites:
                    row.tag = new_canonical
                session.flush()
            except IntegrityError as exc:
                # Everything this method can decide has been decided, so a
                # duplicate key here means a CONCURRENT writer committed the
                # destination tag onto one of the moving products between the
                # SELECT above and this flush. Roll the failed flush back, then
                # work out whether that is what happened at all.
                session.rollback()
                if not self._is_duplicate_key_violation(exc):
                    # Not a uniqueness violation (an FK broken by a
                    # concurrently-deleted product, a column constraint, a
                    # storage-level failure). Nothing here can diagnose it, and
                    # dressing it up as a tag conflict would send the operator
                    # hunting for one that does not exist AND erase the failure
                    # from the audit log, since a ValidationError is
                    # deliberately not audited.
                    raise
                error = ValidationError(
                    f"Another change added '{new_canonical}' to one of these "
                    f'products at the same time, so nothing was renamed.',
                    field='new_tag', value=new_canonical)
                # RETRYABLE, unlike the folded collision above: nothing about
                # this rename is wrong, so the IDENTICAL submission succeeds
                # once the racing transaction is done. Saying so on the
                # exception is what stops a caller telling the operator to pick
                # a different destination that was never the problem — the
                # field alone cannot distinguish the two.
                error.retryable = True
                raise error

            session.commit()
        except ValidationError:
            # A refused rename is ordinary validation, not an operational
            # failure — same as set_product_tags, it rolls back and re-raises
            # without an audit-error record.
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            try:
                log_audit_operation('rename_tag', 'error', item_id=audit_id,
                                    error_details=str(e),
                                    logger_name='mariadb_catalog_service')
            except Exception as audit_err:
                # An audit sink that is down must not REPLACE the failure it
                # was asked to record: the caller would then see 'audit sink
                # down' in place of the database error that actually killed the
                # rename, and the real cause would appear nowhere at all.
                logger.warning(
                    f'Tag rename {old_canonical!r} -> {new_canonical!r} '
                    f'failed, and its audit log failed too: {audit_err}')
            raise
        finally:
            session.close()

        # Past the commit the rename HAS happened. Audit-logging therefore sits
        # outside the try and cannot raise: the caller renders a failure
        # message from any exception, and telling the operator to retry a
        # rename that already succeeded would send them to a tag that no longer
        # exists.
        try:
            log_audit_operation('rename_tag', 'success', item_id=audit_id,
                                changes={'old_tag': old_canonical,
                                         'new_tag': new_canonical,
                                         'products_renamed': len(rewrites),
                                         'products_merged': len(merges),
                                         'merged_product_ids': merged_ids},
                                logger_name='mariadb_catalog_service')
        except Exception as e:
            logger.warning(
                f'Tag rename {old_canonical!r} -> {new_canonical!r} '
                f'committed, but its audit log failed: {e}')
        return len(rewrites), len(merges)

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
        # encoding of one product collides on the shared key. ANY refusal by
        # `normalize_gtin` — a non-digit, a wrong length, an all-zero run (the
        # wedge no-read) or a failed check digit — is surfaced as a domain
        # ValidationError (never a raw InvalidGtinError) that offers the
        # GTIN_UNVALIDATED path.
        # GTIN_UNVALIDATED is stored exactly as entered — never normalized.
        #
        # DW-23: `_validate_product_create_form` now calls the same util and
        # refuses this BEFORE `create_product` commits, so the operator meets
        # the rule beside the field with nothing yet written, and states the
        # same recovery clause verbatim (only its verb differs — there the type
        # is still a `<select>` to change). That route is `add_identifier`'s
        # only caller in the app today, so this raise is now the invariant
        # rather than the message anyone reads — it must stay, because the
        # form's check is a courtesy and this one is the guarantee. Its wording
        # names an action that EXISTS: re-adding the identifier with type
        # GTIN_UNVALIDATED, which the create form's type `<select>` offers. It
        # used to say "Store it as GTIN_UNVALIDATED" — a storage outcome, not an
        # action: nothing anywhere stores-as, and the sentence never named the
        # one control that does it.
        if itype is IdentifierType.GTIN:
            try:
                value = gtin.normalize_gtin(value)
            except gtin.InvalidGtinError as e:
                raise ValidationError(
                    f'{e} Add it with identifier type '
                    f'{IdentifierType.GTIN_UNVALIDATED.value} to keep the value '
                    f'exactly as entered, without check-digit validation.',
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

        The pure module's InvalidGs1PayloadError never leaks, but which domain
        error replaces it depends on whose fault it reports — that is what the
        error's `source` carries. A malformed grammar is a deployment fault in a
        named config key and has nothing to do with the id handed in; reporting
        it as a ValidationError on `internal_id` would put a perfectly valid id
        in the error's `value` and send the operator (and the UI, which
        interpolates `field` into "Please check the ... field") after the one
        thing that is not wrong.

        Raises:
            ConfigurationError: if the configured grammar is malformed, with
                `config_key` naming the key to change. The 43xx and split-pair
                rules are checked against `ai + token` jointly, so neither half
                is individually at fault and the pair is named instead.
            ValidationError: if `internal_id` itself cannot be encoded — blank,
                not a string, unencodable, or too long for the data field —
                with `field='internal_id'` as before.
        """
        try:
            return gs1.encode(internal_id,
                              ai=Config.GS1_INTERNAL_AI,
                              token=Config.GS1_INTERNAL_TOKEN)
        except gs1.InvalidGs1PayloadError as e:
            # Only an explicit PAYLOAD source blames the id. Everything else —
            # including a source this method has never heard of — is attributed
            # to the configuration, because blaming a valid id is the failure
            # this branch exists to prevent and it must not be what an
            # unclassified fault falls back to.
            if e.source == gs1.InvalidGs1PayloadError.PAYLOAD:
                raise ValidationError(str(e), field='internal_id',
                                      value=str(internal_id)) from e
            # part='marker' is the case that actually reaches the default: the
            # 43xx and split-pair rules are violated by the pair, not by either
            # half. part='fnc1_substitute' lands there too — it has no config
            # key of its own and cannot reach here today, since encode takes no
            # substitute — rather than being mapped onto an unrelated key.
            config_key = {
                'ai': 'GS1_INTERNAL_AI',
                'token': 'GS1_INTERNAL_TOKEN',
            }.get(e.part, 'GS1_INTERNAL_AI/GS1_INTERNAL_TOKEN')
            raise ConfigurationError(str(e), config_key=config_key) from e

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
          accent-insensitive `cafe`/`café` match survives too. That is the
          PINNED MariaDB collation, not an inherited one — every table is
          `utf8mb4_unicode_ci` by declaration (`app/database.py`'s
          `MYSQL_TABLE_OPTIONS`, migration a977ca7315df) — so the divergence is
          a fixed property of the two backends rather than of a deployment. It
          is the one `ProductTag`'s docstring records; it is
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
                `app.utils.scan_input.clean_scan_input` (that one strips only
                `' \\t\\r\\n'`, deliberately preserving the separators an ECIA
                envelope is built from): here a leading GS or RS is noise in a
                search box, not structure. This is the one cleaning
                `resolve_scan` inherits by delegating here, and it is a
                property of the search entrypoint rather than a second copy of
                the scan trim rule. A blank, whitespace-only or None query
                returns `[]` rather than the whole catalog, as does text that
                cannot reach the database intact (`sql_text.is_storable_text`:
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
        # one; see `sql_text.is_storable_text`. This check runs before the
        # pattern is built, because the defect is in the pattern.
        if not sql_text.is_storable_text(q):
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

        pattern = f'%{sql_text.escape_like_literal(q.lower())}%'

        def _matches(column):
            return func.lower(column).like(
                pattern, escape=sql_text.LIKE_ESCAPE_CHAR)

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

    def _ecia_match(self, candidate: str) -> Optional[Product]:
        """
        The ONE product `candidate` identifies, or None for zero or several.

        One candidate, one query, one session — the unit `resolve_scan`'s ECIA
        walk is built from. Both places a manufacturer part number can live are
        consulted at once: the `products.mpn` column and an `MPN` identifier
        row. Ordered by `Product.id.asc()` and capped at two rows, because the
        only question is "exactly one, or not" and fetching the rest would cost
        rows nothing reads.

        Two rows are genuinely reachable: `products.mpn` carries no unique
        constraint, so any number of products may hold the same one; and one
        product's `mpn` column can collide with a DIFFERENT product's `MPN`
        identifier row, which nothing cross-checks. NOT two identifier rows —
        `MPN` is global-scoped (`vendor_scope=''`) and
        `uq_product_identifiers_type_value_scope` already forbids that pair,
        which is why `add_identifier` raises `ValidationError` there. Global
        scoping is what makes an identifier row UNIQUE across products, not what
        makes it shareable.

        Zero or more than one is "no product" for this candidate: `mpn` is not
        unique, so silently returning the oldest of several would answer a
        question nobody asked. The caller decides what happens next — it walks
        on to the next candidate, and only a total absence of an unambiguous
        answer reaches the fallthrough.

        The caller is responsible for the candidate being trimmed, non-blank and
        storable; `_ecia_candidates` is the only supported source.

        Args:
            candidate: One part number, exactly as it will be compared.

        Returns:
            A detached `Product`, or None. Scalar columns stay readable;
            relationship attributes must not be touched.
        """
        def _matches(column):
            # TWO disjuncts, and both are load-bearing.
            #
            # `func.lower()` on both sides, explicitly, is the same construction
            # `search_products` uses and for the same reason: SQLite's default
            # collation is binary, so relying on the column's collation would
            # make this lookup case-SENSITIVE under the unit suite and
            # case-insensitive in production.
            #
            # But that fold is ASCII-only on SQLite — `str.lower()` is
            # full-Unicode while SQLite's `LOWER()` leaves non-ASCII untouched —
            # so the two sides of a folded comparison can never agree for a
            # non-ASCII part number, and a stored 'WÜRTH-1' scanned as the
            # byte-identical 'WÜRTH-1' matched NOTHING: an exact lookup failing
            # on an exact value. The unfolded equality closes that. Under SQLite
            # it adds exactly the rows a byte-identical value should have
            # matched all along and nothing else, because that backend's default
            # collation is binary; what it does NOT buy there is non-ASCII
            # case-INsensitivity ('würth-1' still misses), which needs an
            # engine-level collation or Epic 8's mechanism decision.
            #
            # Under MariaDB it is NOT a byte comparison and this disjunct is not
            # the narrow one: `=` runs under the column's collation, which for
            # both `products.mpn` and `product_identifiers.value` is PINNED to
            # `utf8mb4_unicode_ci` (`app/database.py`, migration a977ca7315df)
            # rather than inherited from the server, and which is case- AND
            # accent-insensitive and PAD SPACE, and `LOWER()` does not change
            # that, so both disjuncts are collation-folded and 'WURTH-1' can
            # equal a stored 'WÜRTH-1'.
            # `resolve_scan`'s docstring states the consequence: what "equality"
            # reaches here is backend-dependent, and this method picks a landing
            # rather than adding a hit, so the divergence `search_products`
            # already records costs more in this seam than in that one.
            return or_(column == candidate,
                       func.lower(column) == candidate.lower())

        # An EXISTS rather than a join, for the reason search_products states: a
        # product matching on both its `mpn` column and an identifier row must
        # appear ONCE, without a SQL DISTINCT. Only IdentifierType.MPN is
        # consulted. VENDOR_SKU rows are deliberately outside this lookup — see
        # `resolve_scan`'s docstring.
        identifier_match = (
            exists()
            .where(ProductIdentifier.product_id == Product.id)
            .where(ProductIdentifier.identifier_type ==
                   IdentifierType.MPN.value)
            .where(_matches(ProductIdentifier.value))
        )

        session = self.Session()
        try:
            matches = (session.query(Product)
                       .filter(or_(_matches(Product.mpn), identifier_match))
                       .order_by(Product.id.asc())
                       .limit(2)
                       .all())
        finally:
            session.close()
        return matches[0] if len(matches) == 1 else None

    def _ecia_fallthrough(self, candidates: List[str]) -> Tuple[str, tuple]:
        """
        The FR36 fallthrough for an `ecia` scan that resolved to no product.

        Searches the candidates in order through `search_products` (AD-17, no
        second search path) and returns the FIRST non-empty hit list together
        with the candidate that produced it. If no candidate yields hits, the
        hits are empty and the reported searched text is `candidates[0]` — the
        supplier part number, which is what a reader of the resolution would
        expect to have been asked about.

        First-non-empty rather than a MERGED hit list, which is what the ledger
        entry proposed. `ScanResolution` may not grow a fourth field (AD-15), so
        the route has to rebuild the searched text and put it in `q`; a union
        across two candidates cannot be reproduced from a single `q`, so
        `/products/search?q=…` would show a different set than `hit_count`
        promised — the exact failure `TestSearchTextAgreesWithTheResolver`
        exists to prevent. Keeping `free_text_hits` equal to
        `search_products(<one text>)` is therefore a constraint on the shape of
        this method, not a simplification of it.

        At most one search per candidate, and it stops at the first non-empty
        one, so the ordinary single-candidate label costs exactly what it always
        did. An empty candidate list costs nothing at all, answering below
        without a search. The one further discount is over-long text:
        `search_products` also answers `[]` before opening a session for a query
        past its pattern bound, so a candidate longer than that costs a call and
        no query. Its other two short-circuits — blank and unstorable text —
        cannot fire here, because `_ecia_candidates`, documented above as this
        method's only supported source, has already removed both.

        Args:
            candidates: `_ecia_candidates`' list, possibly empty.

        Returns:
            `(searched_text, hits)` — the text `free_text_hits` came from, and
            the hits as a tuple. `('', ())` when there are no candidates.
        """
        if not candidates:
            # No part number at all: a legal terminal state, and the one place
            # `resolve_scan` still answers without searching, since there is no
            # question a part-number search could be asking.
            return '', ()
        for candidate in candidates:
            hits = tuple(self.search_products(candidate))
            if hits:
                return candidate, hits
        return candidates[0], ()

    def scan_search_text(self, resolution: ScanResolution) -> str:
        """
        For a resolution that produced NO product: the text whose
        `search_products()` reproduces `resolution.free_text_hits`.

        The scope is deliberate and the round trip is not universal. A
        resolution that LANDED on a product carries `free_text_hits == ()`
        while the text returned here is `candidates[0]` (or the arm's
        fallthrough text) — which may still find that product, and may equally
        find NOTHING, since a landing on the SECOND candidate is still reported
        as the first. Either way `search_products(...)` and `free_text_hits`
        disagree for such a resolution. That is not a defect to fix: the
        method is total rather than partial so a caller reading a resolution
        need not know which branch produced it before asking, and the route
        never asks, because `_scan_destination` only builds a `q` on the
        `search` outcome, which by definition has no product and non-empty hits.

        AD-15 freezes `ScanResolution` to three fields, so the searched text is
        not carried on the resolution — but Story 4.5's router has to put it in
        `q` on the `/products/search` URL it hands the browser, or the results
        page shows a different set than `hit_count` counted. This method is the
        SINGLE implementation of that rule. It used to be a second copy in
        `app/main/routes.py`, which was safe only while the rule was a pure
        function of the classification; the per-candidate fallthrough above made
        the answer depend on the DATABASE, which no route can compute. So the
        rule moved here and the route calls it, the direction this repo has
        repeatedly chosen (one LIKE escaper, one format-06 grammar).

        Per arm, and by CALLING what `resolve_scan` calls rather than by
        agreeing with it: the three pure arms go through the shared
        `_fallthrough_text` (`internal` -> `normalized_value`, `gtin` and
        `free_text` -> the AIM-stripped raw), which `resolve_scan`'s tail also
        uses, so there is no second derivation to drift. Re-deriving the same
        three here in parallel would have moved the duplicate this method exists
        to remove from cross-module to intra-module, not removed it.

        `ecia` is the one arm this method reasons about itself, because its text
        is per candidate: the candidate whose search produced the hits, or
        `candidates[0]` when none did, or `''` when the envelope carries no
        usable part number at all.

        Cost, stated because it is the price of removing the duplicate: for an
        `ecia` resolution carrying hits AND more than one candidate, the winning
        candidate has to be re-established, at one bounded `LIKE` search per
        candidate EXCEPT the last. The last is free by the rule rather than by
        measurement: hits are known non-empty, so if every earlier candidate
        finds nothing the winner can only be the last one. With the two
        candidates this arm actually has, that is exactly one search rather than
        two. Both cheaper cases cost nothing at all: one candidate can only be
        the answer, and no hits means no candidate produced any, so the reported
        text is `candidates[0]` by rule.

        **The residual of re-deriving rather than carrying.** Those searches run
        AFTER `resolve_scan` returned, against a catalog that may have moved: a
        write landing in between can make a different candidate win, so `q` can
        name a candidate other than the one `hit_count` was counted from. This
        is a narrower flavour of a staleness that already exists and is not
        fixable here — the page the operator's browser renders is a THIRD query,
        later still, so `hit_count` and that page can disagree whatever this
        method does. Carrying the winning text on the resolution would close the
        narrow half; it would also make `ScanResolution` four fields, which is
        the shape AD-15 and the spec's intent contract prescribe as three. So it
        is recorded as deferred work rather than taken here (DW-173, which also
        carries the redundant search below).

        The result is what the caller must search by; it is deliberately NOT
        bounded or sanitized here (`_scan_url_value` owns the URL budget), so
        the derivation rule stays assertable on its own.

        Args:
            resolution: Any `ScanResolution` this service produced.

        Returns:
            A `str`, possibly empty — never None, since `search_products('')`
            is `[]` and an empty search is the honest answer for an envelope
            with nothing to search by.
        """
        classification = resolution.classification
        if classification.kind is ScanKind.ECIA:
            candidates = _ecia_candidates(classification)
            if not candidates:
                return ''
            if len(candidates) == 1 or not resolution.free_text_hits:
                return candidates[0]
            # One search settles it, not one per candidate. `free_text_hits` is
            # non-empty here, so SOME candidate's search came back non-empty and
            # the first such candidate is the winner by the first-non-empty
            # rule; a candidate whose search finds anything is therefore that
            # winner, and if none of the earlier ones does, the last is the only
            # one left. Asking the last would be asking a question whose answer
            # is already known.
            for candidate in candidates[:-1]:
                if self.search_products(candidate):
                    return candidate
            return candidates[-1]
        return _fallthrough_text(classification)

    def resolve_scan(self, raw) -> ScanResolution:
        """
        Resolve one captured scan against the catalog (Story 4.3, FR36, AD-15).

        Classifies `raw` with the pure `app/utils/scan_router.classify()`, looks
        the result up where a lookup is defined, and falls through to
        `search_products` when nothing matched — so no scan dead-ends (FR36),
        with one deliberate exception that answers without a lookup AND without
        a search: an `ecia` envelope carrying no usable part number at all
        (only quantity/order/date identifiers, or ones that are blank or
        unstorable), for which no part-number search could mean anything.
        Returns a `ScanResolution` in every case.

        Unstorable text used to be a second such exception, answered before the
        branch. It is not one any more: the guard moved onto the text each arm
        BINDS (see the comment on the branch below, and `_ecia_candidates`), so
        a scan carrying a NUL or an unpaired surrogate now takes its arm's
        ordinary path and is refused inside `search_products` instead. What that
        preserves exactly: such text still reaches no LIKE pattern and still
        opens no session. What it changes: `search_products` is now CALLED for
        it, and a clean part number beside a dirty record resolves.

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
        states: the caller (via `app/utils/scan_input.py`'s `clean_scan_input`
        and `MAX_SCAN_LENGTH`) owns the scan trim rule and the scan length
        bound. This method restates neither — a service that re-cleaned its
        scan input would be a third copy of that rule rather than a shared one.
        Be precise about what that does and does not mean: `raw` is classified
        exactly as handed over, and the text that reaches a LOOKUP is untouched
        apart from the AIM strip.
        The text that reaches the fallthrough SEARCH is additionally subject to
        whatever `search_products` does to a query — a bare `str.strip()` and a
        pattern-length bound — because that is search-entrypoint behavior every
        caller of it gets, not a scan rule re-implemented here.

        **What each arm searches, and why it differs.** For the three arms whose
        answer is a pure function of the classification the rule is not written
        down in the arm at all — the shared tail calls `_fallthrough_text`, and
        so does `scan_search_text`, so the description below is of one executed
        rule rather than of two that agree today:

        - `internal`: looks up `products.internal_id` (AD-3 makes it the
          scan-lookup business key). On a miss it searches
          `classification.normalized_value` — the bare, token-stripped id, which
          is what the column actually stores. The `<ai><token>` prefix is an
          encoding artifact present in no column, so searching the raw scan
          would find nothing by construction. This lookup is an exact `==` and
          it means the SAME thing on both backends: `products.internal_id` is
          pinned to `utf8mb4_bin` (`app/database.py`, migration a977ca7315df),
          which is the case-sensitive comparison `is_valid_internal_id`
          already performs and the binary one SQLite performs by default. So a
          lower-cased scan of a valid id resolves to no product HERE and falls
          through to the free-text search on both — the divergence DW-73
          recorded, closed by pinning rather than by folding the filter (which
          would have made this lookup disagree with the UNIQUE constraint that
          admitted the row).
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
          identifier row. `_ecia_candidates` states which values qualify
          (trimmed, non-blank, storable, de-duplicated) and is the only place
          that rule lives.

          **One query per candidate, in order, first unambiguous answer wins.**
          Each candidate is asked on its own (`_ecia_match`): exactly one
          product matching resolves to it and the walk stops; zero OR more than
          one contributes nothing and the walk moves to the next candidate,
          because two products genuinely can share a part number and silently
          returning the oldest of several would answer a question nobody asked.
          Zero or several on EVERY candidate is "no product". So an ambiguous
          `1P` beside a unique `P` resolves to the `P` product — first
          UNAMBIGUOUS, not first non-empty — and a unique `1P` resolves even
          when `P` matches something else entirely. Cost is at most one query
          per candidate and the ordinary single-hit label still costs one.

          This replaced a single query ORing both candidates together and
          counting rows over the union, which produced three verified ways a
          label resolved to LESS than it supported (DW-78/79/82, all closed
          here): a unique `1P` hit discarded as a false ambiguity because `P`
          matched a different product; a product reachable only by `P`
          dead-ending entirely once a `1P` record was present; and, worst, `1P`
          matching nothing while `P` matched two products EXACTLY — the union
          was ambiguous so both exact matches were dropped, and the single
          fallthrough search then ran on `1P` and found nothing. The walk is
          strictly a tightening: the union landed only when exactly one product
          matched EITHER candidate, and each candidate then matched that
          product or nothing, so every scan that resolved before resolves to
          the same product now.

          Be precise about what "equality" reaches, because it is not the same
          on both backends and this arm returns a single product rather than a
          hit list: the predicate is
          `column = value OR LOWER(column) = LOWER(value)`, which under SQLite
          (the only backend any test here runs) means byte-identical or
          ASCII-case-folded, and under the `utf8mb4_unicode_ci` both columns
          are PINNED to on MariaDB (`app/database.py`, migration a977ca7315df)
          means whatever that collation equates — accent-insensitive and PAD
          SPACE, since `LOWER()` does not change MariaDB's comparison
          collation. So
          `WURTH-1` can land on a product stored `WÜRTH-1` in production and
          cannot in the unit suite. That is the same backend divergence
          `search_products` documents and the ledger records; it is wider here
          only in consequence, because there it adds a hit and here it can pick
          the landing.

          Be exact about WHERE a shared part number is possible, because the
          two homes are not alike: `products.mpn` is nullable and carries no
          unique constraint, so any number of products may hold the same one.
          Two MPN identifier ROWS cannot collide — `MPN` is global-scoped
          (`vendor_scope=''`) and `uq_product_identifiers_type_value_scope` is
          over `(identifier_type, value, vendor_scope)`, so the DB rejects the
          second, which is why `add_identifier` raises `ValidationError` there.
          Global scoping is what makes an identifier row UNIQUE across
          products, not what makes it shareable. The second real ambiguity is
          therefore a CROSS-home one: one product's `mpn` column colliding with
          another product's `MPN` identifier row, which nothing constrains and
          which `test_an_ambiguity_across_the_two_homes_also_falls_through`
          pins. Those two are the whole set.

          **The fallthrough is per candidate too** (`_ecia_fallthrough`): on no
          product the candidates are searched IN ORDER and the FIRST non-empty
          hit list is the answer, so a product reachable only by the second
          candidate is reached. Not a merged or de-duplicated union across
          candidates: `free_text_hits` must stay exactly
          `search_products(<one text>)`, or the `/products/search?q=…` page the
          route builds could not reproduce what `hit_count` counted (AD-15
          freezes the resolution at three fields, so the text is re-derived by
          `scan_search_text` rather than carried). When no candidate yields
          hits the reported searched text is the first candidate.

          An envelope carrying no USABLE part-number identifier is answered
          with no product and no hits, without any query — normally a label
          carrying only `Q`/`K`/`9D`, but a `1P` holding nothing but spaces, or
          one carrying a NUL or an unpaired surrogate, reaches the same
          terminal state, since those are filtered out before the candidates
          are counted.

          Two exclusions a reader would otherwise have to diff the model to
          find. (1) `VENDOR_SKU` identifier rows are not consulted, even though
          a distributor part number in `P` is conceptually one: `VENDOR_SKU` is
          vendor-scoped (AD-9), so its uniqueness is per vendor and an unscoped
          exact match could resolve a DigiKey label to a product identified by
          an identical Mouser number. The scan carries no vendor and FR39 names
          MPN as what a distributor scan pre-fills. `IdentifierType.MPN` is
          global-scoped, so this lookup correctly needs no `vendor_scope`
          filter. (2) The ASCII-case fold is one of the two disjuncts per
          candidate rather than the only one — see `_matches` inside
          `_ecia_match` for why a byte-identical comparison runs beside it, and
          for what non-ASCII case-insensitivity still does not do under SQLite.

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
        no audit log, so scan resolution is idempotent by construction.

        Session count per scan, which is one session per query issued. For
        `internal` and `gtin` it is one for a lookup that hits, one for a
        `free_text` scan (the search alone), and two for a MISS (the lookup,
        then `search_products`' own). For `ecia` it is PER CANDIDATE and there
        are at most two candidates, so the ceiling is two lookups plus two
        searches — four — reached only by a two-candidate label that resolves
        to nothing and whose first candidate finds no hits. The ordinary label
        is unchanged: a `1P` that hits costs exactly one.

        Subtract from all of that any search that answers without querying.
        `search_products` returns `[]` for text that is blank, unstorable or
        over-long before it opens anything, so an unencodable scan and an empty
        scan open ZERO sessions even though the search IS called, and a lookup
        miss whose fallthrough text is blank opens one rather than two. An
        `ecia` envelope with no usable candidate opens ZERO: it neither looks
        up nor searches. `scan_search_text` is a separate call with its own
        cost — see its docstring — and is not counted here.

        The Product and every Product in `free_text_hits` are detached rows:
        scalar columns stay readable, relationship attributes must not be
        touched.

        Args:
            raw: The scan text, already cleaned by the caller.

        Returns:
            A `ScanResolution`. Never None.

        Raises:
            TypeError: propagated from `classify` when `raw` is not a `str` — a
                caller fault, not a scan.
            gs1.InvalidGs1PayloadError: propagated UNCHANGED when the configured
                grammar is malformed. Both methods agree that this is a
                *deployment* fault and neither blames the scan or the id;
                they differ only in how far they translate it.
                `encode_internal_payload` has to catch it anyway (its other
                failure mode, a bad id, is a `ValidationError`) so it maps the
                grammar case onto a `ConfigurationError` naming the config key.
                Here there is nothing to disambiguate, so the pure error travels
                untouched: translating it would dress a broken configuration up
                as a rejected scan, and swallowing it would silently disable
                rule 1 so every label this shop ever printed would quietly start
                resolving as free text.

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
        # `clean_scan_input` passes through untouched. Text carrying a NUL
        # binds fine and then compares WRONG, because SQLite truncates a LIKE
        # pattern at the first NUL: '\x00' * 4096 — the classic wedge no-read,
        # and a vector this suite already had — resolved to every product in
        # the catalog. No stored value can equal or contain either shape, so
        # the honest answer is the no-match one, reached without a query.
        #
        # The guard is applied PER ARM, to the text that arm actually binds to
        # a lookup, and not once to `raw` before the branch (DW-80). Judging
        # the whole envelope is a stricter rule than the defect calls for and
        # it suppressed clean lookups: an ECIA label whose `K` order number or
        # `9D` date carried a stray NUL — a record no query here ever touches —
        # answered with no product and no hits even though its `1P` matched a
        # product character for character. Each arm below guards exactly what
        # it binds: `internal` and `gtin` their `normalized_value`, `ecia` each
        # candidate individually (in `_ecia_candidates`, which drops an
        # unstorable one from the list so it can be neither looked up nor
        # searched nor reported), and `free_text` nothing, because it binds
        # nothing. Every fallthrough SEARCH is already guarded inside
        # `search_products`, which answers `[]` for unstorable text before it
        # opens a session — so unstorable text still reaches no LIKE pattern
        # and still opens no session, which is the invariant that mattered.
        if kind is ScanKind.INTERNAL:
            # A formality on this arm, exactly as on `gtin` below, and kept for
            # the same reason: so that "every arm guards what it binds" is
            # checkable by reading the branch rather than by reasoning about the
            # classifier. `normalized_value` here is `gs1.decode`'s data field,
            # and `decode` returns None unless every character of it is
            # 0x21-0x7E (`_is_encodable_id_char`) — printable ASCII with no
            # space, which excludes NUL and every surrogate. So it is storable
            # by construction and this condition cannot be False.
            product = None
            if sql_text.is_storable_text(classification.normalized_value):
                session = self.Session()
                try:
                    product = (session.query(Product)
                               .filter(Product.internal_id ==
                                       classification.normalized_value)
                               .first())
                finally:
                    session.close()

        elif kind is ScanKind.GTIN:
            # The guard is a formality on this arm and is kept only so that
            # "every arm guards what it binds" is checkable by reading the
            # branch rather than by reasoning about the classifier:
            # `normalized_value` is fourteen ASCII digits by construction, so
            # it is storable by construction too.
            product = None
            if sql_text.is_storable_text(classification.normalized_value):
                session = self.Session()
                try:
                    # The same (type, value) namespace find_product_id_by_gtin
                    # queries, inline rather than by delegation: that method
                    # takes an unnormalized value and would re-run
                    # normalize_gtin on a key the classifier already
                    # normalized, returns an id rather than a row, and opens a
                    # third session per scan. The duplication is one filter
                    # pair, and TestNamespaceAgreement pins the two against
                    # drift.
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

        elif kind is ScanKind.ECIA:
            # The one arm that answers entirely on its own rather than joining
            # the shared tail below, because both halves of its answer are PER
            # CANDIDATE: it may issue two lookups, and its fallthrough may
            # issue two searches. A single `fallthrough_text` handed to the
            # tail could express neither.
            candidates = _ecia_candidates(classification)

            # Walk the candidates in order and take the FIRST unambiguous
            # answer. `1P` leads the list and now also takes precedence in the
            # RESULT, which is the whole of what changed here: the old arm ORed
            # both candidates into one query and counted rows over the union,
            # so a unique `1P` hit was discarded as a false ambiguity whenever
            # `P` happened to match a different product (DW-78), and a product
            # reachable only by `P` could not be reached at all (DW-79).
            #
            # A candidate matching zero or several contributes no product and
            # the walk continues; only a total absence of an unambiguous answer
            # reaches the fallthrough. The walk is monotone with respect to the
            # old behavior: the union query landed only when exactly one
            # product matched EITHER candidate, and in that state each
            # candidate matched that product or nothing — so every scan that
            # resolved before resolves to the same product now, and new
            # landings occur only where the union previously answered none.
            #
            # Cost: at most one query per candidate, and it stops at the first
            # landing, so a hit on `1P` — the ordinary label — still costs
            # exactly one query and one session.
            product = None
            for candidate in candidates:
                product = self._ecia_match(candidate)
                if product is not None:
                    break

            if product is not None:
                return ScanResolution(classification=classification,
                                      product=product, free_text_hits=())
            # No candidate was unambiguous, which includes the no-candidate
            # case: `_ecia_fallthrough` answers `('', ())` there without
            # searching at all, so an envelope carrying only quantity, order
            # and date identifiers — or a `1P` holding nothing but spaces —
            # still reaches its legal terminal state with no query issued.
            _, hits = self._ecia_fallthrough(candidates)
            return ScanResolution(classification=classification, product=None,
                                  free_text_hits=hits)

        else:
            # ScanKind.FREE_TEXT, the last FR36 rule — the fallthrough that
            # always matches (rule 4 before DW-70, rule 5 after it),
            # so there is nothing to look up and the search always runs.
            product = None

        if product is not None:
            return ScanResolution(classification=classification,
                                  product=product, free_text_hits=())

        # FR36: a miss is never a dead end — it becomes a search, within the
        # same scan, through AD-17's single entrypoint. search_products manages
        # its own session and returns [] for a blank query (an empty scan), so
        # this never degenerates into "every product".
        #
        # The searched text comes from the module-level `_fallthrough_text`
        # rather than from a variable each arm above set, and `scan_search_text`
        # calls the very same function — so the arm-to-text rule is executed
        # once and read twice, instead of being written down in two places that
        # have to be kept agreeing. Only the three PURE arms reach here; the
        # `ecia` arm returned above, because its text is per candidate.
        return ScanResolution(
            classification=classification,
            product=None,
            free_text_hits=tuple(
                self.search_products(_fallthrough_text(classification))),
        )
