"""
Product catalog service.

All business logic for the product catalog lives here: routes in the ``product``
blueprint stay thin and issue no ORM queries and no raw SQL.

Session handling follows the InventoryService precedent -- take ``storage.engine``
and build a sessionmaker from it -- rather than routing catalog queries through
the sheet-shaped ``Storage`` ABC, which cannot express them. ``expire_on_commit``
is off so that an object handed back to a route is still readable after its
session closes.
"""

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, case, create_engine, func, or_
from sqlalchemy.orm import selectinload, sessionmaker

from .database import (
    ItemPhotoAssociation,
    Photo,
    Product,
    ProductAttachment,
    ProductIdentifier,
    ProductSpecification,
    ProductTag,
    Purchase,
    Tag,
)
from .exceptions import (
    CaptureDecisionRequired,
    DuplicateItemError,
    ItemNotFoundError,
    ValidationError,
)
from .mariadb_storage import MariaDBStorage
from .services import order_vendors
from .models import (
    CandidatePurchase,
    CaptureAssessment,
    price_to_cents,
    CapturedBarcode,
    DigiKeyOrder,
    IdentifierType,
    ListingCapture,
    CapturedOrder,
    OrderCaptureResult,
    McMasterOrder,
    OrderCaptureReview,
    OrderLineState,
    PurchaseDeletion,
    ReviewedLine,
    ScanClassification,
    ScanKind,
    ScanResolution,
    StockStatus,
    normalized_row_name,
)
from .utils import category as category_utils
from .utils import gtin as gtin_utils
from .utils import internal_id as internal_id_utils
from .utils import catalog_taxonomy
from .utils.scan_router import classify
from .utils.sql import escape_like as _escape_like
from config import Config

logger = logging.getLogger(__name__)

MAX_DESCRIPTION_LENGTH = 255
MAX_CATEGORY_PATH_LENGTH = 512
MAX_TAG_LENGTH = 64
MAX_SPECIFICATION_NAME_LENGTH = 100

# The identifier types whose meaning depends on knowing whose identifier it is.
VENDOR_SCOPED_TYPES = (IdentifierType.VENDOR, IdentifierType.DISTRIBUTOR)

# Specification row names that mean "this value is a retail barcode" (016 FR-001).
# A captured row carrying one of these is a candidate for promotion to a GTIN
# identifier; see _promote_barcode_rows. The list is closed and short, and adding
# to it is a one-line change -- which is why it is a constant and not a setting.
BARCODE_ROW_NAMES = frozenset({'UPC', 'EAN', 'GTIN', 'ISBN', 'GTIN-13', 'UPC-A'})

# The vendor name a DigiKey capture files purchases under. Matches what
# ``_vendor_from_url`` already derives from a digikey.com address, so a capture
# and a hand-typed purchase land in the same place. Existing rows spelled
# 'Digi-Key' are left as they are; this feature does not rewrite history.
DIGIKEY_VENDOR = 'DigiKey'

# The vendor name a McMaster-Carr capture files purchases under. This **must**
# equal what ``_vendor_from_url`` derives from an mcmaster.com address
# (app/product/routes.py) -- the two are compared, and a mismatch would make
# every captured order unfindable and every scanned bag unreceivable.
MCMASTER_VENDOR = 'McMaster-Carr'

# The vendor name an Amazon capture files purchases under. Same rule as the two
# above: it **must** equal what ``_vendor_from_url`` derives from an amazon.com
# address, because an order captured from an order page and a listing captured
# from a product page have to land under the same vendor or the order screen
# cannot find them.
AMAZON_VENDOR = 'Amazon'

# How far apart two order dates may be before they cannot describe the same
# physical purchase (033 FR-003).
#
# **This is the range within which the operator is asked, not a range within
# which anything is merged.** Nothing is ever joined without an answer, so a
# generous window costs an occasional question about a genuine repeat purchase
# and buys never missing a real duplicate that an operator's typed date put
# weeks away from the vendor's. The case this exists for was four days apart
# (issue #129); the window is ninety.
#
# A constant rather than a setting: Constitution I forbids a configuration knob
# for a future that has not arrived, and there is one operator with one answer.
CANDIDATE_WINDOW = timedelta(days=90)


class CatalogService:
    """Business logic for products, identifiers, purchases and reorder state."""

    def __init__(self, storage: MariaDBStorage = None):
        """Initialize with a MariaDB storage backend.

        Args:
            storage: The storage backend to borrow an engine from. A new
                MariaDBStorage is built from config when omitted.
        """
        if storage is None:
            storage = MariaDBStorage()

        self.storage = storage
        self.engine = storage.engine or self._create_engine()
        # expire_on_commit=False: a Product returned to a route must still be
        # readable after the session that loaded it has closed.
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _create_engine(self):
        """Create a database engine when the storage backend has none"""
        return create_engine(
            Config.SQLALCHEMY_DATABASE_URI,
            **Config.SQLALCHEMY_ENGINE_OPTIONS
        )

    @contextmanager
    def _session(self):
        """Session scope that commits on success and rolls back on failure."""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -- Products ----------------------------------------------------------

    def create_product(
        self,
        description: str,
        manufacturer: Optional[str] = None,
        manufacturer_part_number: Optional[str] = None,
        specifications: Optional[List[Dict[str, str]]] = None,
        category_path: Optional[str] = None,
        location: Optional[str] = None,
        sub_location: Optional[str] = None,
        quantity: Optional[int] = None,
        reorder_threshold: Optional[int] = None,
        notes: Optional[str] = None,
        identifiers: Optional[List[Dict[str, Any]]] = None,
        tags: Optional[List[str]] = None,
    ) -> Product:
        """Create a product and give it an internal code.

        The internal identifier is assigned here, not when a label is first
        printed, so every product is scannable from the moment it exists
        (FR-015).

        Args:
            description: The operator's human-readable identity for the product.
            manufacturer: Optional manufacturer name.
            manufacturer_part_number: Optional convenience copy of the MPN.
            specifications: Optional list of ``{'name', 'value'}`` entries, in
                the order they should display. ``None`` and ``[]`` both mean
                "no specifications" and are not distinguished.
            category_path: Optional category path; normalized before storage.
            location: Optional storage location (FR-033).
            sub_location: Optional bin or drawer within the location. NULL is an
                ordinary state, the same way location's is.
            quantity: Optional count. None means "not tracked" (FR-023).
            reorder_threshold: Optional threshold; only valid alongside a count.
            notes: Optional notes.
            identifiers: Optional list of ``{id_type, value, vendor?, override?}``.
            tags: Optional list of tag names.

        Returns:
            The created Product, with identifiers and tags loaded.

        Raises:
            ValidationError: If any field or identifier fails validation.
        """
        description = self._validate_description(description)
        category_path = self._validate_category_path(category_path)
        quantity = self._validate_quantity(quantity)
        reorder_threshold = self._validate_reorder_threshold(reorder_threshold, quantity)
        # Validated before the session opens, so a refused specification means no
        # product is created at all.
        entries = self._validate_specifications(specifications)

        with self._session() as session:
            product = Product(
                description=description,
                manufacturer=_clean(manufacturer),
                manufacturer_part_number=_clean(manufacturer_part_number),
                category_path=category_path,
                location=_clean(location),
                sub_location=_clean(sub_location),
                quantity=quantity,
                quantity_updated_at=datetime.now() if quantity is not None else None,
                reorder_threshold=reorder_threshold,
                notes=_clean(notes),
            )
            session.add(product)
            session.flush()  # assign product.id

            # display_order is the surviving list index, so dropping a blank row
            # leaves no gap.
            for order, entry in enumerate(entries):
                session.add(ProductSpecification(
                    product_id=product.id,
                    name=entry['name'],
                    value=entry['value'],
                    display_order=order,
                ))

            # Every product carries its own code from the start.
            session.add(ProductIdentifier(
                product_id=product.id,
                id_type=IdentifierType.INTERNAL.value,
                value=self._unique_internal_code(session),
                vendor='',
                validation_overridden=False,
            ))

            for spec in (identifiers or []):
                try:
                    self._add_identifier(session, product.id, **spec)
                except DuplicateItemError as clash:
                    # FR-008: identity is this product's own row. A vendor that
                    # reuses an item identifier for a different product must not
                    # merge the two or mutate the first, so the new product is
                    # created and the colliding identifier is simply left off for
                    # the operator to resolve.
                    logger.warning(
                        f"Identifier {spec.get('value')!r} already belongs to product "
                        f"{clash.item_id}; created product {product.id} without it"
                    )

            for name in (tags or []):
                self._attach_tag(session, product, name)

            session.flush()
            product_id = product.id

        logger.info(f"Created product {product_id}: {description}")
        return self.get_product(product_id)

    def get_product(self, product_id: int) -> Optional[Product]:
        """Load one product with its identifiers, purchases and tags.

        Args:
            product_id: The product's surrogate id.

        Returns:
            The Product, or None when no such product exists.
        """
        with self._session() as session:
            return (
                session.query(Product)
                .options(
                    selectinload(Product.identifiers),
                    selectinload(Product.purchases),
                    selectinload(Product.tags),
                    # _session() closes before the caller sees this, so the
                    # detail page's <dl> and to_dict would hit a detached
                    # instance without it.
                    selectinload(Product.specifications),
                )
                .filter(Product.id == product_id)
                .first()
            )

    def list_products(self, limit: int = 500) -> List[Product]:
        """List the catalog, most recently added first.

        Args:
            limit: Most products to return.

        Returns:
            A list of Products with their tags loaded.
        """
        with self._session() as session:
            return (
                session.query(Product)
                .options(
                    selectinload(Product.tags),
                    selectinload(Product.identifiers),
                    selectinload(Product.specifications),
                )
                .order_by(Product.date_added.desc())
                .limit(limit)
                .all()
            )

    def search_products(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        stock: Optional[str] = None,
        spec_name: Optional[str] = None,
        spec_value: Optional[str] = None,
        limit: int = 500,
    ) -> List[Product]:
        """Find products by text, category subtree, tag, stock state and spec.

        Args:
            query: Matched against description, specifications, manufacturer,
                manufacturer part number, notes and every recorded identifier
                value (FR-032, 009 FR-010).
            category: A category path; matches it *and its sub-categories*, on
                segment boundaries, so filtering "foo" never pulls in "foo-bar".
            tag: A tag name; ignores category entirely (FR-031).
            stock: One of 'low', 'on-order', 'tracked', 'untracked',
                'none-on-hand'. The last two are the distinction SC-007 requires
                stay unambiguous.
            spec_name: A specification name, matched whole and case-insensitively
                (FR-012, FR-015).
            spec_value: With ``spec_name``, narrows to values *containing* this
                text (FR-013, FR-014). On its own it adds no clause -- a value
                filter without a name is not offered, and unusable input is
                dropped rather than raised, matching the other filters.
            limit: Most products to return.

        Returns:
            The matching products, ordered by description.
        """
        with self._session() as session:
            statement = session.query(Product).options(
                selectinload(Product.tags),
                # Loaded up front: a caller reading product.internal_code off a
                # result would otherwise hit a detached instance.
                selectinload(Product.identifiers),
                selectinload(Product.specifications),
            )

            text = (query or '').strip()
            if text:
                pattern = f"%{text}%"
                matching_ids = session.query(ProductIdentifier.product_id).filter(
                    ProductIdentifier.value.like(pattern)
                )
                statement = statement.filter(or_(
                    Product.description.like(pattern),
                    # FR-017: free text still reaches everything it reached when
                    # specifications were one column of text.
                    Product.specifications.any(or_(
                        ProductSpecification.name.like(pattern),
                        ProductSpecification.value.like(pattern),
                    )),
                    Product.manufacturer_part_number.like(pattern),
                    Product.manufacturer.like(pattern),
                    # 009 FR-010: the one field the operator writes prose in was
                    # the one field they could not search. `like`, not `ilike`,
                    # deliberately -- matching the clauses around it is what
                    # stops notes and description ever drifting apart, and a
                    # NULL note is simply never true rather than an error.
                    Product.notes.like(pattern),
                    Product.id.in_(matching_ids),
                ))

            category_path = category_utils.canonical(category)
            if category_path is not None:
                statement = statement.filter(or_(
                    Product.category_path == category_path,
                    Product.category_path.like(
                        category_utils.descendant_like_pattern(category_path), escape='\\'
                    ),
                ))

            tag_name = _clean(tag)
            if tag_name:
                statement = statement.filter(
                    Product.tags.any(Tag.name == tag_name.lower())
                )

            statement = self._apply_specification_filter(
                statement, spec_name, spec_value
            )

            statement = self._apply_stock_filter(session, statement, stock)

            return statement.order_by(Product.description).limit(limit).all()

    def set_quantity(self, product_id: int, quantity: Optional[int]) -> Product:
        """Set, change or stop tracking a product's quantity (FR-022, FR-023).

        Three states, and the caller must be able to reach all three: a number
        counts, ``0`` means tracked with none on hand, and ``None`` means stop
        tracking. Setting a count stamps ``quantity_updated_at``; switching
        tracking off clears it, because an age for a count that no longer exists
        is worse than no age at all.

        Args:
            product_id: The product.
            quantity: The count, or None to stop tracking.

        Returns:
            The updated Product.

        Raises:
            ItemNotFoundError: If the product does not exist.
            ValidationError: If the quantity is not a non-negative whole number.
        """
        value = self._validate_quantity(quantity)

        with self._session() as session:
            product = session.query(Product).filter(Product.id == product_id).first()
            if product is None:
                raise ItemNotFoundError(
                    f"Product {product_id} not found", item_id=str(product_id)
                )

            if value is None:
                product.quantity = None
                product.quantity_updated_at = None
                # A threshold with nothing to compare against means nothing.
                product.reorder_threshold = None
            else:
                product.quantity = value
                product.quantity_updated_at = datetime.now()

        return self.get_product(product_id)

    def set_stock_status(self, product_id: int, stock_status: Optional[str]) -> Product:
        """Set or clear the operator's manual low/out flag (FR-025).

        Independent of any count: an untracked product can be flagged low, which
        is the whole point -- the operator knows things the count does not.

        Storing a flag also records **when** it was stored (008 FR-001), and
        that happens even when the value stored equals the value already there
        (008 FR-002): re-pressing "Low" on a product already flagged low is the
        operator saying "I have just looked and it is still low", which is the
        only way to renew the evidence on a product that has no count. It is
        also what makes the re-assertion produce an UPDATE at all -- assigning
        an identical string is no change as far as SQLAlchemy is concerned, so
        before feature 008 that button press did nothing.

        Clearing the flag discards its date with it (008 FR-003), so a later
        flag can never inherit an older one's.

        Args:
            product_id: The product.
            stock_status: 'low', 'out', or None to clear the flag.

        Returns:
            The updated Product.

        Raises:
            ItemNotFoundError: If the product does not exist.
            ValidationError: If the status is not a valid value.
        """
        if stock_status is None or stock_status == '':
            value = None
        else:
            try:
                value = StockStatus(str(stock_status).lower()).value
            except ValueError:
                valid = ', '.join(s.value for s in StockStatus)
                raise ValidationError(
                    f"Unknown stock status {stock_status!r}. Valid values: {valid}, or null",
                    field='stock_status', value=str(stock_status)
                )

        with self._session() as session:
            product = session.query(Product).filter(Product.id == product_id).first()
            if product is None:
                raise ItemNotFoundError(
                    f"Product {product_id} not found", item_id=str(product_id)
                )
            product.stock_status = value
            # Written unconditionally, including when `value` equals what is
            # already stored: 008 FR-002 makes a re-assertion a fresh look.
            product.stock_status_updated_at = datetime.now() if value else None

        return self.get_product(product_id)

    # -- Reorder -----------------------------------------------------------

    def get_reorder_products(self) -> List[Dict[str, Any]]:
        """Everything that needs buying, with what is already coming marked.

        All of it is computed here, at query time. There is no stored status
        column and no background job, so there is nothing that can drift out of
        step with the purchase data it would have been derived from.

        Args:
            None.

        Returns:
            One entry per low product: the Product, why it is low, and whether an
            order for it is already outstanding.
        """
        with self._session() as session:
            products = (
                session.query(Product)
                .options(selectinload(Product.tags), selectinload(Product.purchases))
                .filter(self._effectively_low_clause())
                .order_by(Product.description)
                .all()
            )

            on_order_ids = {
                row[0] for row in session.query(Product.id).filter(
                    self._on_order_clause()
                ).all()
            }

        return [
            {
                'product': product,
                'is_threshold_low': product.is_threshold_low,
                'is_manually_low': product.is_manually_low,
                'is_on_order': product.id in on_order_ids,
                'outstanding': [p for p in product.purchases if p.received_date is None],
            }
            for product in products
        ]

    def _apply_specification_filter(
        self, statement, spec_name: Optional[str], spec_value: Optional[str]
    ):
        """Narrow a product query to one recorded specification (FR-012..FR-015).

        ``func.lower`` on the name rather than ``==``: SQLite compares BINARY, and
        FR-015 is case-insensitive. This is a *read*, so the deployed collation
        also folding accents is accepted -- it returns a near-spelling the
        operator probably wanted, and nothing is written.
        """
        name = _clean(spec_name)
        if not name:
            # A value with no name adds no clause, matching how the other
            # filters treat input they cannot use.
            return statement

        conditions = [func.lower(ProductSpecification.name) == name.lower()]

        value = _clean(spec_value)
        if value:
            # Contained, not exact (FR-014). The operator's own wildcards are
            # escaped because an unescaped % returns wrong answers.
            #
            # func.lower on both sides for the same reason the name uses it: a
            # bare LIKE is case-insensitive on MariaDB because of the collation
            # and only incidentally so on SQLite, which folds ASCII but obeys
            # `PRAGMA case_sensitive_like`. Lowering both sides makes the two
            # backends agree rather than leaving it to each one's defaults. No
            # index is lost -- FR-014 matches with a leading wildcard, which no
            # index serves, which is why `value` has none.
            conditions.append(func.lower(ProductSpecification.value).like(
                f"%{_escape_like(value.lower())}%", escape='\\'
            ))

        return statement.filter(Product.specifications.any(and_(*conditions)))

    def _apply_stock_filter(self, session, statement, stock: Optional[str]):
        """Narrow a product query by stock state, all of it derived at query time"""
        if not stock:
            return statement

        if stock == 'tracked':
            return statement.filter(Product.quantity.isnot(None))
        if stock == 'untracked':
            return statement.filter(Product.quantity.is_(None))
        if stock == 'none-on-hand':
            return statement.filter(Product.quantity == 0)
        if stock == 'low':
            return statement.filter(self._effectively_low_clause())
        if stock == 'on-order':
            return statement.filter(self._on_order_clause())

        valid = "'low', 'on-order', 'tracked', 'untracked', 'none-on-hand'"
        raise ValidationError(
            f"Unknown stock filter {stock!r}. Valid values: {valid}",
            field='stock', value=str(stock)
        )

    def _effectively_low_clause(self):
        """FR-027: manually flagged, or tracked and at/below its threshold"""
        return or_(
            Product.stock_status.in_([StockStatus.LOW.value, StockStatus.OUT.value]),
            and_(
                Product.quantity.isnot(None),
                Product.reorder_threshold.isnot(None),
                Product.quantity <= Product.reorder_threshold,
            ),
        )

    def _on_order_clause(self):
        """FR-028: derived from purchase data, never recorded separately"""
        return Product.purchases.any(Purchase.received_date.is_(None))

    def update_product(self, product_id: int, **fields: Any) -> Product:
        """Update a product's editable fields.

        Only the fields present in ``fields`` are touched, so a caller that knows
        about three fields cannot blank the other ten.

        Args:
            product_id: The product to update.
            **fields: Any of description, manufacturer, manufacturer_part_number,
                specifications, category_path, location, sub_location, notes,
                reorder_threshold.

                ``specifications`` is a list of ``{'name', 'value'}`` entries and
                *replaces* the product's complete set. Omitting the key leaves
                the existing rows alone; passing ``[]`` or ``None`` clears them.

        Returns:
            The updated Product.

        Raises:
            ItemNotFoundError: If the product does not exist.
            ValidationError: If a supplied field fails validation.
        """
        # Deliberately excludes quantity, stock_status and both of their dates.
        # Those are written by set_quantity, set_stock_status, create_product and
        # receive_purchase, and by nothing else -- which is the whole of why
        # "what can reset an age" (008 SC-003) is answerable by reading four
        # functions rather than auditing the codebase. Do not add them here.
        editable = {
            'description', 'manufacturer', 'manufacturer_part_number',
            'specifications', 'category_path', 'location', 'sub_location',
            'notes', 'reorder_threshold',
        }
        unknown = set(fields) - editable
        if unknown:
            raise ValidationError(
                f"Not editable through update_product: {', '.join(sorted(unknown))}",
                field=sorted(unknown)[0]
            )

        # Validated before the session opens for the same reason create does it:
        # a refused specification must leave the product's other fields alone.
        entries = (
            self._validate_specifications(fields['specifications'])
            if 'specifications' in fields else None
        )

        with self._session() as session:
            product = session.query(Product).options(
                selectinload(Product.specifications)
            ).filter(Product.id == product_id).first()
            if product is None:
                raise ItemNotFoundError(f"Product {product_id} not found", item_id=str(product_id))

            if entries is not None:
                # Replacement, not merge: the form always posts the complete set
                # and no row has an identity to diff against.
                product.specifications.clear()
                product.specifications.extend(
                    ProductSpecification(
                        name=entry['name'],
                        value=entry['value'],
                        display_order=order,
                    )
                    for order, entry in enumerate(entries)
                )

            if 'description' in fields:
                product.description = self._validate_description(fields['description'])
            if 'category_path' in fields:
                product.category_path = self._validate_category_path(fields['category_path'])
            if 'reorder_threshold' in fields:
                product.reorder_threshold = self._validate_reorder_threshold(
                    fields['reorder_threshold'], product.quantity
                )

            # specifications is not in this loop: it is a list of rows, not a
            # scalar, and is replaced above.
            for name in ('manufacturer', 'manufacturer_part_number',
                         'location', 'sub_location', 'notes'):
                if name in fields:
                    setattr(product, name, _clean(fields[name]))

        logger.info(f"Updated product {product_id}")
        return self.get_product(product_id)

    def merge_specifications(
        self, product_id: int, entries: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """Add captured specification rows without disturbing what is there.

        The counterpart to ``update_product``'s replace-on-write, and not a
        variant of it: the form posts a complete set, a capture posts an
        incomplete one. A capture landing on an existing product and *replacing*
        its specifications would delete every row the operator had typed, which
        FR-011 forbids in as many words.

        The rule, and the whole of it:

        * A captured name the product already carries is dropped whole, value
          included (FR-010). The operator looked at the thing; a selector did
          not.
        * Survivors are appended after the highest existing ``display_order``,
          so no existing row moves.
        * **Nothing is ever removed.** That is a property of this method rather
          than of its callers, which is the point of it being a method.

        Validation runs **row by row rather than as a batch**, so one over-long
        name costs one row and not the other twenty-four (FR-008 scenario 8). A
        capture is all-or-nothing about nothing.

        Args:
            product_id: The product to add to.
            entries: ``{'name', 'value'}`` dicts, as the agent found them.

        Returns:
            The validated entries it appended, in the order it appended them.
            Empty is an ordinary outcome -- recapturing an unchanged listing adds
            nothing the second time -- and not a failure.

            **The rows rather than a count, because the caller needs to know
            which ones.** ``_promote_barcode_rows`` turns a captured ``UPC`` row
            into a GTIN identifier, and 016 FR-003 limits that to rows this
            capture actually added. Whether a row was added is decided here and
            nowhere else, so reporting it here is what keeps the drop rule from
            being implemented twice.

        Raises:
            ItemNotFoundError: If the product does not exist.
        """
        with self._session() as session:
            product = session.query(Product).options(
                selectinload(Product.specifications)
            ).filter(Product.id == product_id).first()
            if product is None:
                raise ItemNotFoundError(
                    f"Product {product_id} not found", item_id=str(product_id)
                )

            # Folded in Python, never in SQL. The deployment's collation folds
            # accents as well as case, so a comparison pushed into SQL would
            # call "Volt" and "Vôlt" one name on MariaDB and two under the unit
            # suite -- a rule meaning two different things on two backends.
            # ProductSpecification's own docstring already says
            # _validate_specifications is the authority and compares in Python;
            # this joins it.
            existing = {row.name.lower() for row in product.specifications}
            next_order = max(
                (row.display_order for row in product.specifications), default=-1
            ) + 1

            added = []
            for entry in entries or []:
                try:
                    validated = self._validate_specifications([entry])
                except ValidationError as e:
                    logger.info(f"Captured specification dropped: {e.message}")
                    continue
                if not validated:
                    continue

                name = validated[0]['name']
                key = name.lower()
                if key in existing:
                    continue

                existing.add(key)
                product.specifications.append(ProductSpecification(
                    name=name,
                    value=validated[0]['value'],
                    display_order=next_order,
                ))
                next_order += 1
                added.append(validated[0])

        if added:
            logger.info(
                f"Merged {len(added)} captured specifications into product {product_id}"
            )
        return added

    # -- Identifiers -------------------------------------------------------

    def add_identifier(
        self,
        product_id: int,
        id_type: str,
        value: str,
        vendor: Optional[str] = None,
        override: bool = False,
    ) -> ProductIdentifier:
        """Attach a coded name to a product (FR-007).

        Args:
            product_id: The product to attach to.
            id_type: One of the IdentifierType values.
            value: The identifier as scanned or typed; normalized before storage.
            vendor: Required for VENDOR and DISTRIBUTOR types, which are only
                meaningful within a vendor.
            override: Store a GTIN whose check digit failed anyway (FR-010). The
                override is recorded on the row so it is visible rather than
                silent. There is no override for an all-zero no-read.

        Returns:
            The created ProductIdentifier.

        Raises:
            ItemNotFoundError: If the product does not exist.
            ValidationError: If the identifier fails validation or already
                belongs to another product.
        """
        with self._session() as session:
            if session.query(Product).filter(Product.id == product_id).first() is None:
                raise ItemNotFoundError(f"Product {product_id} not found", item_id=str(product_id))

            identifier = self._add_identifier(
                session, product_id, id_type=id_type, value=value,
                vendor=vendor, override=override,
            )
            session.flush()
            identifier_id = identifier.id

        with self._session() as session:
            return session.query(ProductIdentifier).filter(
                ProductIdentifier.id == identifier_id
            ).first()

    def remove_identifier(self, product_id: int, identifier_id: int) -> bool:
        """Detach a coded name from a product.

        Removing every identifier a product has leaves the product itself intact:
        identity is the product row, never one of its names (FR-008).

        Args:
            product_id: The owning product.
            identifier_id: The identifier row to remove.

        Returns:
            True when a row was removed, False when there was nothing to remove.
        """
        with self._session() as session:
            identifier = session.query(ProductIdentifier).filter(
                ProductIdentifier.id == identifier_id,
                ProductIdentifier.product_id == product_id,
            ).first()
            if identifier is None:
                return False

            session.delete(identifier)
            return True

    def find_product_by_identifier(
        self,
        value: str,
        id_type: Optional[str] = None,
        vendor: Optional[str] = None,
    ) -> Optional[Product]:
        """Find the product carrying a given identifier value.

        The unique key makes "at most one product" true, so this returns a
        product or nothing -- never a list to disambiguate.

        Args:
            value: The identifier value, already normalized by the caller.
            id_type: Optionally narrow to one IdentifierType.
            vendor: Optionally narrow to one vendor's scope.

        Returns:
            The owning Product, or None.
        """
        if not isinstance(value, str) or not value.strip():
            return None

        with self._session() as session:
            query = session.query(ProductIdentifier).filter(
                ProductIdentifier.value == value.strip()
            )
            if id_type is not None:
                identifier_type = self._validate_identifier_type(id_type)
                query = query.filter(ProductIdentifier.id_type == identifier_type.value)
            if vendor is not None:
                query = query.filter(ProductIdentifier.vendor == (vendor.strip() or ''))

            identifier = query.first()
            if identifier is None:
                return None

        return self.get_product(identifier.product_id)

    # -- Purchases ---------------------------------------------------------

    def record_purchase(
        self,
        product_id: int,
        vendor: str,
        vendor_item_id: Optional[str] = None,
        listing_title: Optional[str] = None,
        listing_url: Optional[str] = None,
        order_date: Optional[datetime] = None,
        received_date: Optional[datetime] = None,
        quantity: Optional[int] = None,
        unit_price: Optional[Any] = None,
        order_reference: Optional[str] = None,
        supplier_order_reference: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Purchase:
        """Record one acquisition of a product (FR-004, FR-005).

        Args:
            product_id: The product acquired.
            vendor: Who it came from. Required -- provenance is the point.
            vendor_item_id: The vendor's own identifier, if there is one.
            listing_title: The vendor's raw title, if captured at order time.
            listing_url: The listing's address, if captured at order time. Its
                own field rather than a line in notes, because the duplicate
                check reads it and notes is the operator's to overwrite.
            order_date: When it was ordered.
            received_date: When it arrived. None means the order is outstanding.
            quantity: How many.
            unit_price: Price per unit, as a Decimal.
            order_reference: The *customer's* order number -- ECIA ``K``.
            supplier_order_reference: The *supplier's* order number -- ECIA
                ``1K``, which for DigiKey is the sales order number. A different
                number from the one above; both are printed on the same label.
            notes: Free text.

        Returns:
            The created Purchase.

        Raises:
            ItemNotFoundError: If the product does not exist.
            ValidationError: If a field fails validation.
        """
        vendor_name = _clean(vendor)
        if not vendor_name:
            raise ValidationError("Vendor is required on a purchase", field='vendor')

        order_date = _parse_datetime(order_date, 'order_date')
        received_date = _parse_datetime(received_date, 'received_date')
        quantity = self._validate_purchase_quantity(quantity)
        price = self._validate_price(unit_price)
        self._validate_receipt_order(order_date, received_date)

        with self._session() as session:
            if session.query(Product).filter(Product.id == product_id).first() is None:
                raise ItemNotFoundError(f"Product {product_id} not found", item_id=str(product_id))

            purchase = Purchase(
                product_id=product_id,
                vendor=vendor_name,
                vendor_item_id=_clean(vendor_item_id),
                listing_title=_clean(listing_title),
                listing_url=_clean(listing_url),
                order_date=order_date,
                received_date=received_date,
                quantity=quantity,
                unit_price=price,
                order_reference=_clean(order_reference),
                supplier_order_reference=_clean(supplier_order_reference),
                notes=_clean(notes),
            )
            session.add(purchase)
            session.flush()
            purchase_id = purchase.id

        logger.info(f"Recorded purchase {purchase_id} of product {product_id} from {vendor_name}")
        return self.get_purchase(purchase_id)

    def get_purchase(self, purchase_id: int) -> Optional[Purchase]:
        """Load one purchase.

        Args:
            purchase_id: The purchase's id.

        Returns:
            The Purchase, or None.
        """
        with self._session() as session:
            return session.query(Purchase).filter(Purchase.id == purchase_id).first()

    def get_purchase_history(self, product_id: int) -> List[Purchase]:
        """Every purchase of a product, oldest order first (FR-006).

        Args:
            product_id: The product.

        Returns:
            The purchases in chronological order. Purchases with no order date
            sort last, because an unknown date is not an early one.
        """
        with self._session() as session:
            purchases = session.query(Purchase).filter(
                Purchase.product_id == product_id
            ).all()

        return sorted(
            purchases,
            key=lambda p: (p.order_date is None, p.order_date or datetime.min, p.id),
        )

    def get_latest_purchase(self, product_id: int) -> Optional[Purchase]:
        """The most recent purchase by order date (FR-006).

        Undated purchases are *not* candidates while any dated one exists. The
        history sorts them last on the grounds that an unknown date is not an
        early one -- but "last in that list" is not the same as "most recent",
        and treating it that way turns an honest agnosticism about the date into
        a false claim of recency.

        Args:
            product_id: The product.

        Returns:
            The most recent dated purchase; the last-added undated one if none of
            them carry a date at all; None if there are no purchases.
        """
        history = self.get_purchase_history(product_id)
        dated = [p for p in history if p.order_date is not None]

        if dated:
            return dated[-1]
        return history[-1] if history else None

    def get_latest_price(self, product_id: int) -> Optional[Decimal]:
        """The unit price of the most recent purchase by order date (FR-006).

        Args:
            product_id: The product.

        Returns:
            The price as a Decimal, or None when nothing priced has been bought.
        """
        history = self.get_purchase_history(product_id)
        dated = [p for p in history if p.order_date is not None]

        # A dated purchase always beats an undated one, however recently the
        # undated row happened to be entered.
        for candidate in (dated, history):
            for purchase in reversed(candidate):
                if purchase.unit_price is not None:
                    return purchase.unit_price
        return None

    def capture_order(
        self,
        vendor: str,
        vendor_item_id: Optional[str] = None,
        listing_title: Optional[str] = None,
        url: Optional[str] = None,
        unit_price: Optional[Any] = None,
        quantity: Optional[int] = None,
        order_date: Optional[datetime] = None,
        description: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_part_number: Optional[str] = None,
        acknowledged_duplicate_of: Optional[Any] = None,
        attach_to: Optional[Any] = None,
        listing: Optional[ListingCapture] = None,
        category_path: Optional[str] = None,
        location: Optional[str] = None,
        sub_location: Optional[str] = None,
    ) -> Purchase:
        """Capture an order while the vendor's listing is still on screen.

        Creates an *unreceived* purchase (FR-020) and either attaches it to the
        product the captured identifier already names or creates one (FR-021).

        **It confirms rather than guesses.** Two things it used to decide alone
        it now refuses to decide: a capture that looks like one already recorded,
        and an item id that already names a product without corroboration. Either
        raises ``CaptureDecisionRequired`` carrying a ``CaptureAssessment``, and
        raises it *before anything is written* -- a caller handling that exception
        is looking at a database this call has not touched.

        Args:
            vendor: The vendor, derived from the listing's host.
            vendor_item_id: The vendor's identifier, e.g. an Amazon ASIN.
            listing_title: The page title, as the vendor wrote it.
            url: The listing URL, recorded on the purchase.
            unit_price: Price, if the operator supplied one.
            quantity: Quantity, if the operator supplied one.
            order_date: When it was ordered. Defaults to today.
            description: The operator's own wording for the product, authored
                while the listing is on screen. **Blank falls back to the listing
                title** rather than raising -- the opposite of the rule at
                receipt, where there is nothing to fall back to.
            manufacturer: Optional; recorded on a newly created product, and half
                of the corroboration test.
            manufacturer_part_number: Optional; the other half.
            acknowledged_duplicate_of: The id of a purchase the operator was
                shown and chose to record alongside anyway.
            attach_to: ``None`` to decide automatically, ``'new'`` to force a new
                product, or a product id to attach to.
            category_path: Where the operator files the product. Validated and
                normalized up front, with the price and the quantity, so an
                over-length path is refused before any question is raised.
            location: The storage location, as the operator states it.
            sub_location: The bin or drawer. Accepted with or without a
                ``location``, because the catalog stores one without the other.

                **None of these three is ever read off the listing** (018
                FR-013). No selector can produce a category or a shelf, and a
                guessed value that looks stated is worse than a blank one. On a
                product this call *creates*, blank means uncategorized, which is
                an ordinary state. On one it *attaches to*, a stated value
                replaces what the product held -- the rule ``description``
                already follows -- and a blank one changes nothing.
            listing: What the capture agent read off the vendor's page, if
                anything. ``None`` is exactly today's behaviour, which is what
                keeps the paste-a-URL form and the JSON representation of
                ``/api/capture`` working untouched. Its specification rows and
                its description are merged onto the product **after the product
                is resolved** -- the merge target is not known until the
                duplicate and recycled-identifier questions have been settled,
                so applying it any earlier would apply it to the wrong product.
                It never fetches an image; that is the route's job, and
                deliberately outside this transaction.

        Returns:
            The newly created Purchase.

        Raises:
            ValidationError: If vendor is missing or a value fails validation.
            CaptureDecisionRequired: If a duplicate or an uncorroborated
                identifier match needs the operator's answer. Nothing is written.
        """
        vendor_name = _clean(vendor)
        if not vendor_name:
            raise ValidationError("Vendor is required to capture an order", field='vendor')

        item_id = _clean(vendor_item_id)
        title = _clean(listing_title)
        listing_url = _clean(url)
        ordered = _parse_datetime(order_date, 'order_date') or datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        price = self._validate_price(unit_price)
        count = self._validate_purchase_quantity(quantity)
        # Here rather than inside create_product/update_product so that an
        # over-length path is refused before the duplicate and recycled-
        # identifier questions are put to the operator, keeping this method's
        # "a refused capture writes nothing" contract in one place.
        filed_under = self._validate_category_path(category_path)

        # Blank is not an error here, it is a fallback (FR-003). Only a
        # non-blank description is held to the length limit (FR-006).
        wording = _clean(description)
        if wording is not None:
            wording = self._validate_description(wording)

        acknowledged = _as_int(acknowledged_duplicate_of)
        requested_product_id = None if attach_to == 'new' else _as_int(attach_to)
        create_new_requested = attach_to == 'new'

        # Both questions are worked out before either is raised, so a capture
        # that is a probable repeat *and* lands on a recycled identifier asks
        # once and is answered once. Nothing below writes.
        duplicate = self._find_captured_purchase(vendor_name, item_id, listing_url, ordered)
        duplicate_open = duplicate is not None and acknowledged != duplicate.id

        # FR-021: attach when the identifier already names a product -- but only
        # silently when the operator asked for it, or when the manufacturer and
        # part number both agree (FR-019).
        match = None
        if item_id:
            match = self.find_product_by_identifier(
                item_id, id_type=IdentifierType.VENDOR.value, vendor=vendor_name
            )

        product = None
        match_open = False
        if create_new_requested:
            product = None
        elif requested_product_id is not None:
            if match is not None and match.id != requested_product_id:
                # The answer was about a different product; it is stale.
                match_open = True
            else:
                product = self.get_product(requested_product_id)
                if product is None:
                    # The spec's stated edge case: the choice named a product
                    # that has since gone. Creating one is what would have
                    # happened had there been no match, and beats failing on a
                    # page the operator cannot fix from.
                    logger.info(
                        f"Capture asked to attach to product {requested_product_id}, which "
                        f"no longer exists; creating a product instead"
                    )
        elif match is not None:
            if _corroborates(match, manufacturer, manufacturer_part_number):
                product = match
            else:
                match_open = True

        if duplicate_open or match_open:
            reasons = []
            assessment = {}
            if duplicate_open:
                reasons.append(
                    f"a purchase from {vendor_name} for this listing is already recorded "
                    f"on {duplicate.order_date.date():%Y-%m-%d}"
                    if duplicate.order_date else
                    f"a purchase from {vendor_name} for this listing is already recorded"
                )
                assessment.update(
                    duplicate_purchase_id=duplicate.id,
                    duplicate_order_date=duplicate.order_date,
                    duplicate_vendor=duplicate.vendor,
                    # Set only when the recognized row is a line of an order
                    # (033 FR-018). Naming the order is what tells the operator
                    # which record they are being asked about, and it is the
                    # only thing distinguishing this from the same-day case.
                    duplicate_order_reference=duplicate.supplier_order_reference,
                )
            if match_open:
                reasons.append(f"vendor item {item_id} already names a product")
                assessment.update(
                    matched_product_id=match.id,
                    matched_product_description=match.description,
                    matched_product_manufacturer=match.manufacturer,
                    matched_product_part_number=match.manufacturer_part_number,
                )

            logger.info(f"Capture needs a decision: {'; '.join(reasons)}; nothing written")
            raise CaptureDecisionRequired(
                f"This capture needs a decision: {'; '.join(reasons)}.",
                CaptureAssessment(**assessment),
            )

        if product is None:
            product = self.create_product(
                description=(
                    wording
                    or title
                    or f"{vendor_name} item {item_id or 'without an identifier'}"
                ),
                manufacturer=manufacturer,
                manufacturer_part_number=manufacturer_part_number,
                notes=f"Captured from {listing_url}" if listing_url else None,
                identifiers=(
                    # Only when the identifier is free. A vendor item id names
                    # at most one product per vendor, so a deliberately separate
                    # product cannot claim one the matched product already
                    # holds -- the purchase still records it as its own
                    # vendor_item_id, which is where it belongs anyway.
                    [{'id_type': IdentifierType.VENDOR.value,
                      'value': item_id, 'vendor': vendor_name}]
                    if item_id and match is None else None
                ),
                category_path=filed_under,
                location=location,
                sub_location=sub_location,
            )
        else:
            # FR-005: the operator is looking at the listing and is the
            # authority. Manufacturer and part number are deliberately *not*
            # written onto an existing product -- a mismatch there is the
            # evidence the recycled-identifier question depends on.
            #
            # **Filing is written by presence, not by value** (018 FR-010).
            # ``_clean('')`` and ``canonical('')`` are both None, and
            # update_product writes every key it is given -- so passing these
            # three unconditionally would set the columns to NULL and unfile a
            # product on every capture where the operator touched none of them.
            # Omitting the key is how "I am not saying" is said.
            changes = {}
            if wording is not None and wording != product.description:
                changes['description'] = wording
            # The two tests differ on purpose: _clean('///') is truthy and reads
            # as stated, while canonical('///') is None and would be stored as
            # NULL. Each field is asked the question its own normalizer answers.
            if filed_under is not None:
                changes['category_path'] = filed_under
            if _clean(location) is not None:
                changes['location'] = location
            if _clean(sub_location) is not None:
                changes['sub_location'] = sub_location
            if changes:
                self.update_product(product.id, **changes)

        if listing is not None:
            self._apply_listing(product.id, listing)

        return self.record_purchase(
            product.id,
            vendor=vendor_name,
            vendor_item_id=item_id,
            listing_title=title,
            listing_url=listing_url,
            order_date=ordered,
            quantity=count,
            unit_price=price,
        )

    def _apply_listing(self, product_id: int, listing: ListingCapture) -> None:
        """Write the parts of a capture that belong to the product.

        The rows and the description, through one ``merge_specifications`` call
        so that both obey the same "already present wins" rule. A product that
        already has a ``Description`` keeps the one it has, which is the same
        rule as everything else and is what "the operator's value wins" means
        when the operator has not touched it.

        The brand is **not** written here. It reaches ``products.manufacturer``
        through the ``manufacturer`` parameter, which the route fills from the
        listing when the operator left it blank -- and onto an *existing* product
        ``capture_order`` deliberately does not write it at all, because a
        mismatch there is the evidence the recycled-identifier question depends
        on.
        """
        entries = list(listing.specifications)
        if listing.description_text:
            entries.append({'name': 'Description', 'value': listing.description_text})
        if entries:
            self._promote_barcode_rows(
                product_id, self.merge_specifications(product_id, entries)
            )

    def _promote_barcode_rows(
        self, product_id: int, added: List[Dict[str, str]]
    ) -> None:
        """Turn the barcode-named rows a capture added into GTIN identifiers.

        016's whole feature. A listing that publishes a UPC has handed us the
        thing that makes the product findable by the barcode on its box, and
        storing it only as a specification throws that away.

        **It reads the rows the merge added, not the rows the listing carried,
        and that is FR-003 in its entirety.** A captured row whose name the
        product already lists is dropped by ``merge_specifications`` and never
        reaches this list, so it cannot be promoted -- what is in the
        specification list is what was promoted, and no identifier can contradict
        a row the operator can see.

        **There is no override, deliberately** (FR-004). A value that fails its
        check digit is skipped and stays a specification row. ``add_identifier``
        has an override for a value an operator typed and stood behind; nobody
        typed this one, so nobody would see the prompt, and an unattended
        override is how a wrong barcode becomes permanent.

        Nothing here can fail the capture (FR-011). The purchase is already
        resolved by the time this runs, and a barcode the catalog will not accept
        is a smaller problem than a capture that refuses to complete.
        """
        for entry in added:
            if not _is_barcode_row_name(entry.get('name')):
                continue

            raw = entry.get('value') or ''
            key = gtin_utils.normalize_and_validate(raw)
            if key is None:
                logger.info(
                    f"Captured {entry.get('name')} row {raw!r} is not a valid barcode; "
                    f"kept as a specification on product {product_id}"
                )
                continue

            try:
                self.add_identifier(product_id, IdentifierType.GTIN.value, key)
                logger.info(f"Promoted captured barcode {key} onto product {product_id}")
            except DuplicateItemError as e:
                # FR-006: the catalog already has a claim on this value. Leaving
                # it as a specification is the only answer that does not guess.
                logger.info(
                    f"Captured barcode {key} not promoted onto product {product_id}: "
                    f"product {e.item_id} already holds it"
                )
            except ValidationError as e:
                # Belt and braces: normalize_and_validate has already agreed the
                # value is storable, so reaching here means the identifier rules
                # changed underneath this and the capture should still finish.
                logger.warning(
                    f"Captured barcode {key} refused by add_identifier: {e.message}"
                )

    def describe_captured_barcodes(
        self, product_id: int, listing: ListingCapture
    ) -> List[CapturedBarcode]:
        """What became of a listing's barcode-named rows, for the operator.

        Read-only, and called by the capture route **after** the write, so every
        outcome is derived from the catalog's final state rather than carried out
        of the write path. See the class docstring on
        :class:`~app.models.CapturedBarcode` for why the report is state-shaped.

        Args:
            product_id: The product the capture resolved to.
            listing: What the capture agent read off the vendor's page.

        Returns:
            One entry per barcode-named row, in listing order, deduplicated by
            normalized key -- a listing carrying both a 12-digit ``UPC`` and its
            13-digit ``EAN`` form is publishing one barcode, and two lines saying
            so reads as two. Empty when the listing carried no barcode-named row,
            which is when the route says nothing at all (FR-013).
        """
        notes: List[CapturedBarcode] = []
        seen = set()

        product = self.get_product(product_id)
        # What the product's specification list holds *now*, folded the way
        # merge_specifications folds it. This is how a row that did not survive
        # the merge is recognized -- see the first test in the loop.
        listed = {_fold(row.name): row.value for row in (product.specifications if product else [])}

        for entry in listing.specifications if listing else []:
            name = entry.get('name') or ''
            if not _is_barcode_row_name(name):
                continue

            raw = (entry.get('value') or '').strip()
            key = gtin_utils.normalize_and_validate(raw)

            # Only equivalent *valid* forms are one barcode (FR-009). Two rows
            # carrying the same unusable text are still two rows, and FR-009
            # wants every one of them accounted for.
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)

            listed_value = listed.get(_fold(name))
            kept = listed_value == raw

            # **Tested first, before anything about the value itself.** The
            # product already carries a row of this name holding something else,
            # so the merge dropped this one whole and the captured value is
            # stored nowhere (FR-010). Every outcome below would tell the
            # operator where the value is, and it is not anywhere.
            if listed_value is not None and not kept:
                notes.append(CapturedBarcode(
                    row_name=name, value=raw, outcome='not_examined',
                    kept_as_specification=False,
                ))
                continue

            if key is None:
                notes.append(CapturedBarcode(
                    row_name=name, value=raw, outcome='unusable',
                    kept_as_specification=kept,
                ))
                continue

            holder = self.find_product_by_identifier(key, id_type=IdentifierType.GTIN.value)
            if holder is not None and holder.id == product_id:
                notes.append(CapturedBarcode(
                    row_name=name, value=key, outcome='recorded',
                    kept_as_specification=kept,
                ))
            elif holder is not None:
                notes.append(CapturedBarcode(
                    row_name=name, value=key, outcome='taken',
                    holder_id=holder.id, holder_description=holder.description,
                    kept_as_specification=kept,
                ))
            else:
                # Inferred, not flagged: every row the merge *added* was either
                # promoted -- so this product holds it -- or refused because
                # another product does. A valid barcode nobody holds, on a row
                # whose value is already listed, is the same-value drop (FR-010).
                notes.append(CapturedBarcode(
                    row_name=name, value=key, outcome='not_examined',
                    kept_as_specification=kept,
                ))

        return notes

    def _find_captured_purchase(
        self,
        vendor: str,
        vendor_item_id: Optional[str],
        listing_url: Optional[str],
        order_date: datetime,
    ) -> Optional[Purchase]:
        """What a repeat capture looks like: same vendor, same listing, same day.

        The item id is the key when there is one. When there is not -- most
        vendors' URLs yield none -- the listing's address stands in for it
        (FR-013), which is what makes a second click on the bookmarklet
        recognizable rather than a second purchase.

        The address is compared **exactly**, and deliberately not normalized. The
        case this has to catch is one page captured twice in a sitting, where
        ``location.href`` is byte-identical between clicks. Stripping "tracking
        junk" would need per-vendor rules -- Amazon puts ``/ref=sr_1_3`` in the
        path, not the query -- and a normalizer that is right for one vendor and
        wrong for the next produces false warnings on genuinely different
        listings, which is worse than a missed one.

        **A second arm, for one specific case** (033 FR-017). The same-day rule
        above is right for two clicks on one listing and wrong for a listing
        captured after the *order* it came on was: the operator types the date
        they remember and the vendor states its own, and the reported case had
        them four days apart (issue #129). So when the same-day query finds
        nothing, one more is tried -- and it is restricted to purchases that
        carry a supplier order number.

        **That restriction is what keeps the blast radius to this feature.** An
        ordinary repeat capture of a listing months later still meets only the
        same-day rule and still records a second purchase without a question;
        only a row an order capture wrote can be recognized across days. The
        listing-URL fallback is not widened either, and could not be: an order
        capture writes the *order page* address into ``listing_url``, never the
        listing's.
        """
        day_start = order_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        with self._session() as session:
            query = session.query(Purchase).filter(
                Purchase.vendor == vendor,
                Purchase.order_date >= day_start,
                Purchase.order_date < day_end,
            )
            if vendor_item_id:
                query = query.filter(Purchase.vendor_item_id == vendor_item_id)
            elif listing_url:
                query = query.filter(Purchase.listing_url == listing_url)
            else:
                # No identifier and no address: nothing to recognize, and saying
                # so is more honest than matching on the vendor and the date.
                return None

            same_day = query.first()
            if same_day is not None or not vendor_item_id:
                return same_day

            ordered = (
                session.query(Purchase)
                .filter(
                    Purchase.vendor == vendor,
                    Purchase.vendor_item_id == vendor_item_id,
                    Purchase.supplier_order_reference.isnot(None),
                    Purchase.order_date.isnot(None),
                    Purchase.order_date >= order_date - CANDIDATE_WINDOW,
                    Purchase.order_date <= order_date + CANDIDATE_WINDOW,
                )
                .order_by(Purchase.id)
                .all()
            )
            if not ordered:
                return None

            # Nearest by date, ties by lowest id -- the same choice
            # ``_assign_candidates`` makes, for the same reason: the operator is
            # about to be told which row this is, so which row it is must not
            # depend on how the database felt like ordering them.
            return min(
                ordered,
                key=lambda row: (abs(row.order_date - order_date), row.id),
            )

    def receive_purchase(
        self,
        purchase_id: int,
        received_date: Optional[datetime] = None,
        quantity: Optional[int] = None,
        unit_price: Optional[Any] = None,
        notes: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Purchase:
        """Mark an outstanding purchase received, amending it if reality differed.

        What arrives is allowed to differ from what was ordered, so quantity and
        price can be amended here -- and so can the product's description, which
        is the whole point of confirming it with the thing in hand (FR-022).

        Receiving also **clears the product's manual low flag** (FR-029). This is
        the asymmetry worth stating: a threshold-derived low clears itself once
        the count changes, but a manually flagged product stays flagged until
        something clears it, and nothing else knows the operator's intent.

        A tracked count goes up by what arrived, and its **age does not move**
        (008 FR-007, FR-008). Those are two halves of one rule: the number the
        catalog reports should account for the delivery, and the date beside it
        should keep meaning "the last time a person counted". Adding to a count
        from a packing slip is not counting, and a screen that says otherwise
        undermines the age display everything else here depends on. What the
        receipt changed is recorded, with its date and quantity, on the purchase
        that changed it.

        Marking an already-received purchase received again is a no-op, not an
        error.

        Args:
            purchase_id: The purchase that arrived.
            received_date: When. Defaults to now.
            quantity: The quantity actually received, if it differed.
            unit_price: The price actually paid, if it differed.
            notes: Replacement notes, if any.
            description: The product's description, confirmed or corrected
                against the thing in hand. ``None`` leaves it alone; **blank is
                refused** (FR-024) -- unlike at capture, there is no listing
                title here to fall back to.

        Returns:
            The updated Purchase.

        Raises:
            ItemNotFoundError: If the purchase does not exist.
            ValidationError: If an amended value fails validation.
        """
        received = _parse_datetime(received_date, 'received_date') or datetime.now()
        amended_quantity = self._validate_purchase_quantity(quantity)
        amended_price = self._validate_price(unit_price)
        # Validated before the session opens, so a refusal leaves the received
        # state alone as well as the description.
        amended_description = (
            self._validate_description(description) if description is not None else None
        )

        with self._session() as session:
            purchase = session.query(Purchase).filter(Purchase.id == purchase_id).first()
            if purchase is None:
                raise ItemNotFoundError(
                    f"Purchase {purchase_id} not found", item_id=str(purchase_id)
                )

            self._validate_receipt_order(purchase.order_date, received)

            already_received = purchase.received_date is not None
            if not already_received:
                purchase.received_date = received

            if amended_quantity is not None:
                purchase.quantity = amended_quantity
            if amended_price is not None:
                purchase.unit_price = amended_price
            if notes is not None:
                purchase.notes = _clean(notes)

            product = session.query(Product).filter(
                Product.id == purchase.product_id
            ).first()

            # Outside the already-received guard on purpose (FR-025). Receiving
            # twice is a no-op for the received date and for the count; it is
            # not a no-op for a description the operator has just corrected with
            # the thing in front of them.
            if (
                product is not None
                and amended_description is not None
                and amended_description != product.description
            ):
                product.description = amended_description

            if product is not None and not already_received:
                # A tracked count goes up by what arrived, which clears any
                # threshold-derived low on its own (008 FR-007).
                #
                # The count's age is deliberately *not* touched (008 FR-008).
                # Arithmetic against a packing slip is not a verification: the
                # number moved, but nobody has looked in the drawer, and
                # quantity_updated_at means the last time somebody did.
                if product.quantity is not None and purchase.quantity:
                    product.quantity = product.quantity + purchase.quantity

                # The manual flag has to be cleared explicitly -- this is the
                # other half of FR-029, and the half nothing else covers. Its
                # date goes with it (008 FR-006), so that a flag set again
                # later cannot inherit this one's age.
                if product.stock_status is not None:
                    logger.info(
                        f"Clearing manual stock flag and its date on product "
                        f"{product.id}: purchase {purchase_id} received"
                    )
                    product.stock_status = None
                    product.stock_status_updated_at = None

        return self.get_purchase(purchase_id)

    def delete_purchase(self, purchase_id: int) -> Optional[PurchaseDeletion]:
        """Remove one purchase recorded in error (032 FR-001, issue #130).

        A duplicate, a mis-captured line, an order captured twice by different
        paths. Several deliberate decisions elsewhere are written up as safe
        *because* the operator can delete a purchase afterwards -- an orphaned
        purchase is "reported and never deleted", a line excluded at capture is
        offered again -- and until this existed, all of them terminated in a
        decision the operator could not act on.

        **The product's counted quantity is deliberately left alone** (FR-007),
        along with its age and any hand-set stock flag. Receiving history and
        current stock are separate claims. Nothing on a purchase records whether
        its receipt ever moved a count -- one received through the receive
        screen did, one captured with an arrival date did not (031 FR-028) -- so
        subtracting would invent a loss for half of them, and would move a number
        nobody has looked at, which is what ``quantity_updated_at`` exists to
        prevent. The product page's own +/- controls are how a count gets fixed.

        Everything happens in one session (FR-012): the purchase, its attachment
        rows, and any photo those attachments were the last reference to.

        Args:
            purchase_id: The purchase to remove.

        Returns:
            A PurchaseDeletion describing what went, or None when there was no
            such purchase. None rather than raising, matching ``get_purchase``
            and ``remove_identifier`` -- the not-found decision is the route's.
        """
        with self._session() as session:
            purchase = session.query(Purchase).filter(
                Purchase.id == purchase_id
            ).first()
            if purchase is None:
                return None

            # Read before the delete: by the time the caller is told, the row is
            # gone, and a deleted ORM instance is not a thing to hand back.
            photo_ids = [attachment.photo_id for attachment in purchase.attachments]
            deletion = PurchaseDeletion(
                purchase_id=purchase.id,
                product_id=purchase.product_id,
                vendor=purchase.vendor,
                order_date=purchase.order_date,
                quantity=purchase.quantity,
                unit_price=purchase.unit_price,
                supplier_order_reference=purchase.supplier_order_reference,
                attachments_deleted=len(photo_ids),
            )

            session.delete(purchase)
            # The attachment rows go with it -- Purchase.attachments is
            # delete-orphan, and product_attachments.purchase_id is ON DELETE
            # CASCADE. Flush so the reference check below sees that.
            session.flush()

            # FR-006: the bytes go only when nothing else wants them.
            #
            # **This is the third statement of one rule.** The other two are
            # PhotoService.delete_attachment and
            # PhotoService.cleanup_orphaned_photos; a change to the rule has to
            # find all three. It is restated rather than shared because
            # PhotoService holds a *separate* session, so calling into it here
            # would make this two transactions -- and a crash between them would
            # leave photos this method promised were gone.
            for photo_id in photo_ids:
                still_referenced = session.query(ProductAttachment).filter(
                    ProductAttachment.photo_id == photo_id
                ).count() or session.query(ItemPhotoAssociation).filter(
                    ItemPhotoAssociation.photo_id == photo_id
                ).count()

                if not still_referenced:
                    photo = session.query(Photo).filter(Photo.id == photo_id).first()
                    if photo is not None:
                        session.delete(photo)

        logger.info(
            f"Deleted purchase {purchase_id} "
            f"({deletion.vendor}, product {deletion.product_id}) "
            f"and {deletion.attachments_deleted} attachment(s)"
        )
        return deletion

    def _validate_purchase_quantity(self, quantity: Any) -> Optional[int]:
        """A purchase of zero is not a purchase"""
        if quantity is None or quantity == '':
            return None

        try:
            value = int(quantity)
        except (TypeError, ValueError):
            raise ValidationError(
                f"Purchase quantity must be a whole number: {quantity!r}", field='quantity'
            )

        if value <= 0:
            raise ValidationError("Purchase quantity must be greater than zero", field='quantity')
        return value

    def _validate_price(self, price: Any) -> Optional[Decimal]:
        """Constitution III: a price is a Decimal, and it is never built from a float"""
        if price is None or price == '':
            return None

        if isinstance(price, float):
            raise ValidationError(
                "A price must not be a float -- pass a Decimal or a string",
                field='unit_price', value=repr(price)
            )

        try:
            value = Decimal(str(price).strip())
        except (InvalidOperation, ValueError):
            raise ValidationError(f"Not a price: {price!r}", field='unit_price')

        if value < 0:
            raise ValidationError("A price cannot be negative", field='unit_price')

        # Rounded here rather than by the Numeric(10, 2) column, which does it
        # silently. See app/models.py:price_to_cents. PR #116 review.
        return price_to_cents(value)

    def _validate_receipt_order(
        self, order_date: Optional[datetime], received_date: Optional[datetime]
    ) -> None:
        """Nothing arrives before it is ordered"""
        if order_date is not None and received_date is not None and received_date < order_date:
            raise ValidationError(
                "A purchase cannot be received before it was ordered",
                field='received_date'
            )

    def _resolve_arrival_date(
        self, arrived_date: Any, stated: Optional[datetime], fallback: datetime,
    ) -> datetime:
        """When a backfilled order arrived (031 FR-026).

        Blank falls back to the **order's own date**, which is the best answer
        available and is the whole point: a delivery from 2023 recorded as
        arriving today would be wrong in exactly the way backfilling exists to
        avoid. Where the vendor gave no date at all, the fallback is now, and
        the purchase's ``order_date`` and ``received_date`` then agree rather
        than differing by a microsecond -- which is the least wrong answer
        available rather than a good one.

        Args:
            arrived_date: What the operator typed, possibly blank.
            stated: The order's own date **as the vendor gave it**, so ``None``
                where they gave none. That None is the point: it is the
                validation floor, and there is no floor under an order nobody
                can date. Substituting now() here refused a real 2023 arrival
                date on an undated order -- the exact case backfilling exists
                for -- because the floor was today. Found in review of PR #128.
            fallback: What to use when nothing was typed. Never None.

        Validated against the same rule receiving uses, so the two screens
        cannot disagree about whether a date is allowed.

        Raises:
            ValidationError: Unreadable, or earlier than a date the order
                actually states. Called before the write session opens, so a
                refusal leaves nothing.
        """
        arrived = _parse_datetime(arrived_date, 'arrived_date') or fallback
        self._validate_receipt_order(stated, arrived)
        return arrived


    # -- DigiKey orders ----------------------------------------------------
    #
    # An order is not stored. It *is* the purchases carrying its sales order
    # number, the way the reorder list is derived rather than kept. What lives
    # here is the pair the capture flow needs: a read that decides and writes
    # nothing, and a write that does the whole order or none of it.

    def _mcmaster_quantity(self, line, decision) -> Optional[int]:
        """The quantity to record: what the operator typed, else the computed one.

        FR-020a. The computed value is packs x pack size; an edit overrules it,
        because the operator can see the box and the page and this code can only
        see the page.
        """
        edited = decision.get('quantity')
        if edited not in (None, ''):
            try:
                value = int(str(edited).strip())
            except (TypeError, ValueError):
                value = None
            if value is not None and value > 0:
                return value
        return line.quantity

    def _mcmaster_unit_price(self, line, decision) -> Optional[Decimal]:
        """The unit price to record: what the operator typed, else the computed one.

        Through ``_validate_price`` either way, so a sub-cent unit price from a
        pack division is rounded deliberately here rather than silently by the
        Numeric(10, 2) column.
        """
        edited = decision.get('unit_price')
        if edited not in (None, ''):
            try:
                return self._validate_price(Decimal(str(edited).strip()))
            except (InvalidOperation, ValueError):
                pass
        return self._validate_price(line.unit_price)

    def _product_for_order_line(self, session, reviewed, line, part, decision, vendor):
        """The product this line's purchase attaches to, creating one if needed.

        Returns:
            ``(product, created)``.

        Raises:
            ValidationError: A conflicted line with no resolution. Raised inside
                the session, so the whole capture rolls back rather than this
                one line being skipped -- the operator answered a question about
                an order, not about a line, and half an order is worse than
                none.

        One implementation since feature 029. The error's ``field`` is keyed by
        ``form_key`` for every vendor now; DigiKey's used to key it by part
        number, which two lines of one order can share. Nothing reads it -- the
        route flashes ``e.message`` only -- so this is a correctness tidy rather
        than a visible change.
        """
        if reviewed.state is OrderLineState.CONFLICT:
            resolution = (decision.get('resolution') or '').strip().lower()
            if resolution not in ('attach', 'separate'):
                raise ValidationError(
                    f"{vendor.item_id_of(line)} already names "
                    f"{reviewed.product_description!r}, whose part number is "
                    f"{reviewed.product_manufacturer_part_number!r} rather than "
                    f"{line.manufacturer_part_number!r}. Say whether to attach to "
                    f"that product or create a separate one.",
                    field=f'resolution[{line.form_key}]',
                )
            if resolution == 'attach':
                return session.get(Product, reviewed.product_id), False
            # 'separate': a new product, and the existing one is left entirely
            # alone -- including its identifiers. The contested item id stays
            # where it is; the new product records it on the purchase instead,
            # via vendor_item_id.
            return vendor.create_product(
                self, session, line, part, decision, claim_distributor=False
            ), True

        if reviewed.state is OrderLineState.MATCHED:
            # The product predates this order and may have blanks the vendor can
            # fill. Enrichment writes gaps only -- a manufacturer someone
            # corrected or a category someone filed always wins.
            #
            # **Only on MATCHED.** A CONFLICT resolved with 'attach' deliberately
            # does not enrich: the operator has just said two things the catalog
            # thought were different are the same, which is not a licence to
            # write one's detail onto the other. That was the behaviour before
            # this was consolidated and it is preserved exactly.
            product = session.get(Product, reviewed.product_id)
            if vendor.enrich_product is not None:
                vendor.enrich_product(self, session, product, part)
            return product, False

        return vendor.create_product(self, session, line, part, decision), True

    def review_order(self, order, vendor, client=None) -> OrderCaptureReview:
        """Decide what capturing this order would do, without doing any of it.

        **Writes nothing.** An operator who closes the tab leaves no product, no
        purchase and no trace -- there was never a record, only an order.

        Args:
            order: The order, however this vendor's reader obtained it.
            vendor: Which vendor's half of capture to drive.
            client: Passed to the vendor's enrichment where it has any. None
                means no enrichment, which is an ordinary state and not an error.

        Returns:
            An OrderCaptureReview: one ReviewedLine per line, plus any purchase
            recorded against this order that no line of it claims.

        One implementation since feature 029; it was written twice before.
        """
        # **Enrichment happens before the session opens.** It is network I/O at
        # up to ten seconds a call, and holding a transaction open across
        # twenty-five of them is a long-lived lock in exchange for nothing.
        #
        # The exposure here is worse than a capture's, not better -- a review
        # enriches every line, where a capture enriches only the included ones.
        # This read used to sit inside the session, which contradicted the
        # comment on its sibling. PR #116 review; do not move it back.
        parts = {}
        if vendor.enrich is not None:
            parts = vendor.enrich(self, client, order.lines)

        with self._session() as session:
            recorded = self._recorded_order_lines(session, order, vendor)
            # Read in the same session as the pairing above, and after it: a
            # candidate is only offered to a line the pairing left undecided
            # (033 FR-005).
            candidates = self._assign_candidates(
                session, order, vendor, order.order_date, recorded,
            )

            reviewed = [
                self._review_order_line(
                    session, line, parts.get(vendor.item_id_of(line)),
                    recorded, vendor, candidates,
                )
                for line in order.lines
            ]
            orphaned = self._orphaned_order_purchases(
                session, order, vendor, recorded
            )

        return OrderCaptureReview(
            order=order,
            lines=tuple(reviewed),
            orphaned=orphaned,
        )

    def capture_order_lines(
        self, order, vendor, decisions: Dict[str, Dict[str, Any]], client=None,
        arrived_date=None,
    ) -> OrderCaptureResult:
        """Record a reviewed order: one purchase per included line.

        **The whole order writes in one session, or none of it does.** Every
        other method here opens its own session, so building a twenty-four line
        order from outside would be forty-eight transactions and a half-written
        order when line thirteen fails.

        ``capture_order`` is deliberately not called. It encodes Amazon's
        single-listing decision model -- a same-day vendor+item duplicate
        heuristic, a listing title fallback, pack pricing, captured-barcode
        promotion. An order number plus a line number is an *exact* idempotency
        key, so that heuristic is not merely unnecessary here, it is wrong: two
        lines of one order are two purchases and it would merge them.

        Args:
            order: The order. For a vendor that can be re-read it is the
                authority; for one read off a page it is what the review
                displayed, carried through the confirmation.
            vendor: Which vendor's half of capture to drive.
            decisions: Keyed by ``line.form_key``. ``include`` absent or false
                excludes the line; ``description`` overrides the suggested one;
                ``quantity`` and ``unit_price`` overrule the computed values
                where the vendor offers that; ``resolution`` is 'attach' or
                'separate' and is required on a conflicted line;
                ``apply_change`` applies a changed quantity or price to an
                already-captured line.
            client: Passed to the vendor's enrichment where it has any.
            arrived_date: When a backfilled order arrived. Applies only to the
                lines whose decision says ``arrived``; blank falls back to the
                order's own date, **never to today** (031 FR-026). See
                :meth:`_resolve_arrival_date`.

        Returns:
            An OrderCaptureResult describing what happened.

        Raises:
            ValidationError: A conflicted line with no resolution, or a refused
                description. Either way **nothing is written** -- the session
                rolls back whole, because the operator answered a question about
                an order rather than about a line.

        One implementation since feature 029; it was written twice before.
        """
        # Validated before the session opens, for the reason receiving does the
        # same: a refused date must leave nothing half-written. It is also the
        # only thing here that can raise on the operator's own input rather
        # than on the vendor's.
        #
        # **Only when a line actually claims to have arrived.** The review's
        # date field is hidden with `d-none` when the operator unticks "already
        # arrived", and `display: none` does not keep a field out of a
        # submission -- only `disabled` does. So a date typed and then thought
        # better of still arrives here, and validating it unconditionally
        # refused the whole capture over a value no line would have used, with
        # the offending field hidden on the re-render. Gated on the server
        # because a fix in the page's JavaScript is only as good as the
        # JavaScript having run. Found in review of PR #128.
        now = datetime.now()
        stated = order.order_date
        arrived = None
        if any((d or {}).get('arrived') for d in decisions.values()):
            arrived = self._resolve_arrival_date(arrived_date, stated, stated or now)

        # **An order the vendor did not date takes the arrival date as its own.**
        # The two defaults used to be chosen independently -- the stored
        # order_date fell back to today while the arrival date was whatever the
        # operator typed -- so backfilling an undated 2023 order wrote a
        # purchase ordered today and received in 2023. That is the row
        # `_validate_receipt_order` exists to refuse and that every other write
        # path does refuse, and the product page renders the pair side by side,
        # so the contradiction was visible. Found in review of PR #128.
        #
        # Deriving one from the other keeps the property the blank-arrival-date
        # case already had -- the two agree rather than contradict -- and today
        # is only reached when nothing at all is known about when this happened.
        order_date = stated or arrived or now

        # Before the session, and only for the lines a confirmation will act on
        # -- unlike the review above, which enriches every line.
        parts = {}
        if vendor.enrich is not None:
            parts = vendor.enrich(self, client, [
                line for line in order.lines
                if (decisions.get(line.form_key) or {}).get('include')
            ])

        purchase_ids = []
        adopted_ids = []
        # The candidate rows this capture has already claimed. A row is offered
        # to every line that could be its line, so this is what keeps it to one.
        claimed = set()
        products_created = products_attached = 0
        lines_excluded = lines_already_captured = lines_updated = 0
        lines_arrived = 0
        lines_incomplete = []
        renamed_from = ''

        with self._session() as session:
            recorded = self._recorded_order_lines(session, order, vendor)
            if vendor.adopts_renames:
                renamed_from = self._adopt_renamed_order(session, order)

            # Re-computed here rather than carried from the review, for the same
            # reason ``recorded`` is: the review ran against an earlier read, and
            # a purchase may have been recorded or deleted since. The assignment
            # is deterministic, so the row the operator was shown is the row this
            # claims (033 FR-004).
            #
            # **``stated``, not ``order_date``.** The two differ for an order the
            # vendor did not date, where ``order_date`` above falls back to the
            # arrival date or to today. ``review_order`` has no such fallback and
            # matches on the stated date alone, so matching on the derived one
            # here would find candidates the review never showed -- and refuse
            # the capture over a question that was never asked, with no control
            # on the re-rendered page able to answer it. The stamp below still
            # uses the derived date, because that is what the order's other rows
            # carry.
            candidates = self._assign_candidates(
                session, order, vendor, stated, recorded,
            )

            order_fields = vendor.order_fields(order)

            for line in order.lines:
                decision = decisions.get(line.form_key) or {}

                # **Already captured is a fact about the line, not a decision
                # about it**, so it is settled before the include gate below.
                #
                # The ordering is load-bearing and was wrong once: the review
                # renders no "take this line" checkbox for a line already
                # captured -- there is nothing to decide -- so ``include`` is
                # always false for one. Gating here on ``include`` therefore
                # made the "Update it?" tick-box dead through the form while
                # passing a unit test that built the decision by hand, and
                # counted every already-captured line as excluded, so a
                # re-capture reported "2 skipped" rather than "2 already
                # captured". PR #116 review.
                #
                # Re-checked inside the session rather than trusted from the
                # review: the review ran against an earlier read.
                existing = recorded.get(line.form_key)
                if existing is not None:
                    lines_already_captured += 1
                    if decision.get('apply_change'):
                        if self._apply_order_change(
                            existing, line, decision, vendor
                        ):
                            lines_updated += 1
                    continue

                if not decision.get('include'):
                    lines_excluded += 1
                    continue

                # Read before the adoption branch rather than after it. The
                # branch used to `continue` past this, which skipped the only
                # place a CONFLICT line's `resolution` is enforced -- so an
                # operator who said "different part, make a new product" *and*
                # "same purchase" got the purchase claimed onto the contradicted
                # product with no error. PR #144 review.
                part = parts.get(vendor.item_id_of(line))
                reviewed = self._review_order_line(
                    session, line, part, recorded, vendor
                )

                # **A purchase for this item may already exist, written by a path
                # that knew nothing about this order** (033 FR-001). The operator
                # says whether it is the same physical purchase; nothing here
                # decides it, because nothing here can.
                candidate = candidates.get(line.form_key)
                if candidate is not None:
                    answer = (decision.get('same_purchase') or '').strip().lower()
                    if answer not in ('adopt', 'separate'):
                        # Raised inside the session, so the whole order rolls
                        # back rather than this one line being skipped -- the
                        # operator answered a question about an order, and half
                        # an order is worse than none. The same rule an
                        # unanswered CONFLICT already follows.
                        raise ValidationError(
                            f"A purchase for {vendor.item_id_of(line)} is "
                            f"already recorded and carries no order number. Say "
                            f"whether it is this order's line or a separate "
                            f"purchase.",
                            field=f'same_purchase[{line.form_key}]',
                        )
                    # **The first line to want it takes it** (FR-004). Two
                    # lines carrying one item id are both offered the same row,
                    # so that excluding one does not lose the question -- and one
                    # purchase cannot be two lines of an order, so a second line
                    # wanting a row already claimed is an ordinary line and
                    # records its own purchase. That is the right answer as well
                    # as the safe one: the operator bought the thing twice.
                    if answer == 'adopt' and candidate.purchase_id not in claimed:
                        # **A contradicted item id has to be settled first.** A
                        # candidate is found by item id alone, and CONFLICT means
                        # that id has probably been recycled -- in which case the
                        # purchase recorded under it belongs to the *old* part
                        # and cannot be this line's. Only the operator saying
                        # "same thing, attach" makes the two coherent; 'separate'
                        # and a blank answer are both refused rather than
                        # silently overruled (FR-015). PR #144 review.
                        if reviewed.state is OrderLineState.CONFLICT:
                            resolution = (
                                decision.get('resolution') or ''
                            ).strip().lower()
                            if resolution != 'attach':
                                raise ValidationError(
                                    f"{vendor.item_id_of(line)} names "
                                    f"{reviewed.product_description!r}, whose "
                                    f"part number contradicts this line, so a "
                                    f"purchase already recorded under it may not "
                                    f"be this one's. Say the two are the same "
                                    f"thing, or record a separate purchase.",
                                    field=f'resolution[{line.form_key}]',
                                )

                        # No product resolution and no new Purchase: the row
                        # already exists and already has a product, and creating
                        # one here would be the duplicate this closes (FR-013,
                        # FR-015). products_created and products_attached
                        # deliberately do not move.
                        purchase = session.get(Purchase, candidate.purchase_id)
                        self._claim_purchase(
                            purchase, line, order_fields, order_date,
                        )
                        adopted_ids.append(purchase.id)
                        claimed.add(purchase.id)
                        if decision.get('apply_change') and self._apply_order_change(
                            purchase, line, decision, vendor
                        ):
                            lines_updated += 1

                        # **An adopted line arrives like any other** (031 FR-024).
                        # The review renders the same "arrived" box for it, and
                        # the order-level box ticks every one of them, so
                        # backfilling a delivered order is the natural way to
                        # reach this. Dropping the tick left the purchase on
                        # order for ever and under-counted the flash. FR-014 asks
                        # that an *already received* purchase keep its receipt --
                        # which is why this only fills an empty one -- not that a
                        # fresh arrival be discarded. PR #144 review.
                        #
                        # The column is set directly, exactly as the create path
                        # below does: no tracked count moves and no manual low
                        # flag clears (031 FR-028).
                        if decision.get('arrived') and purchase.received_date is None:
                            purchase.received_date = arrived
                            lines_arrived += 1
                        continue

                product, created = self._product_for_order_line(
                    session, reviewed, line, part, decision, vendor
                )
                if created:
                    products_created += 1
                else:
                    products_attached += 1

                # Outstanding at capture, whatever the vendor says about
                # shipping. Shipped is their state; received is the operator's,
                # and only they can say it -- which they now get two chances to
                # do. A backfilled order arrived long ago, and saying so here is
                # what stops the reorder list and the captured-orders list
                # reporting a two-year-old delivery as still in transit
                # (031 FR-024).
                #
                # **This deliberately does not do what receive_purchase does.**
                # No tracked count goes up and no manual low flag is cleared:
                # goods delivered two years ago have already been consumed, and
                # a flag set last month is a statement about today's shelf
                # (031 FR-028). Satisfied by construction -- a purchase born
                # with a received_date never passes through receive_purchase --
                # and pinned by tests/unit/test_order_backfill.py, which is the
                # only thing that will notice if that ever changes.
                has_arrived = bool(decision.get('arrived'))
                purchase = Purchase(
                    product_id=product.id,
                    vendor=vendor.name,
                    order_date=order_date,
                    received_date=arrived if has_arrived else None,
                    **order_fields,
                    **vendor.line_fields(self, line, decision),
                )
                if has_arrived:
                    lines_arrived += 1
                session.add(purchase)
                session.flush()
                purchase_ids.append(purchase.id)

                if vendor.incomplete_label is not None:
                    label = vendor.incomplete_label(line, part)
                    if label:
                        lines_incomplete.append(label)

            # The ids just written are passed in: they are flushed, so the
            # re-query inside this session returns them, and `recorded` was
            # built before the loop and cannot account for them.
            # Adopted ids belong here for exactly the reason the freshly
            # written ones do, and it is easier to miss: claiming stamps this
            # order's reference onto the row *inside this session*, so the
            # re-query below returns it -- while `recorded` was built before the
            # loop and cannot name it. Omit them and every adoption is reported
            # back to the operator as a stale line.
            orphaned = self._orphaned_order_purchases(
                session, order, vendor, recorded,
                also_claimed=purchase_ids + adopted_ids,
            )

        result = OrderCaptureResult(
            purchase_ids=tuple(purchase_ids),
            purchases_adopted=tuple(adopted_ids),
            products_created=products_created,
            products_attached=products_attached,
            lines_excluded=lines_excluded,
            lines_already_captured=lines_already_captured,
            lines_updated=lines_updated,
            lines_arrived=lines_arrived,
            lines_incomplete=tuple(lines_incomplete),
            orphaned=orphaned,
            renamed_from=renamed_from,
        )
        logger.info(
            f"Captured {vendor.name} order "
            f"{order_fields.get('supplier_order_reference')}: "
            f"{len(purchase_ids)} purchase(s), "
            f"{len(adopted_ids)} adopted, "
            f"{products_created} product(s) created"
        )
        return result

    # -- The vendor-named entry points -------------------------------------
    #
    # Thin wrappers over the one flow above. They exist because the routes and
    # the two shipped test suites call them by name, and those suites are this
    # feature's regression gate -- they are not edited to accommodate the
    # refactor.

    def review_digikey_order(self, order, digikey_client=None) -> OrderCaptureReview:
        """Review a DigiKey sales order. See :meth:`review_order`."""
        return self.review_order(order, DIGIKEY_ORDER_VENDOR, digikey_client)

    def capture_digikey_order(
        self, order, decisions: Dict[str, Dict[str, Any]], digikey_client=None,
        arrived_date=None,
    ) -> OrderCaptureResult:
        """Confirm a reviewed DigiKey order. See :meth:`capture_order_lines`."""
        return self.capture_order_lines(
            order, DIGIKEY_ORDER_VENDOR, decisions, digikey_client,
            arrived_date=arrived_date,
        )

    def review_mcmaster_order(self, order) -> OrderCaptureReview:
        """Review a McMaster order read off its page. See :meth:`review_order`."""
        return self.review_order(order, MCMASTER_ORDER_VENDOR)

    def capture_mcmaster_order(
        self, order, decisions: Dict[str, Dict[str, Any]], arrived_date=None,
    ) -> OrderCaptureResult:
        """Confirm a reviewed McMaster order. See :meth:`capture_order_lines`."""
        return self.capture_order_lines(
            order, MCMASTER_ORDER_VENDOR, decisions, arrived_date=arrived_date,
        )

    def _candidate_order_purchases(self, session, order, vendor, order_date):
        """Purchases that might already record a line of this order (033 FR-001).

        The blind spot this closes: every vendor's ``order_purchases`` finds rows
        by ``supplier_order_reference``, and a single-listing capture leaves that
        NULL -- so the pairing below has never been handed one to claim, and an
        order capture wrote a second purchase for a product the operator had
        already captured from its listing page (issue #129).

        **Vendor-agnostic on purpose, and that is what makes FR-021 free.** The
        three facts this needs are written identically by both paths: the vendor
        name (``OrderVendor.name`` must equal what ``_vendor_from_url`` derives,
        which is what ``capture_order`` records), ``vendor_item_id``, and
        ``order_date``. Nothing here differs per vendor, so nothing here belongs
        on :class:`OrderVendor` -- adding a member would be the speculative
        generality Constitution I forbids, and would need editing three times.

        **Deliberately not folded into ``order_purchases``.** Those rows feed
        ``_orphaned_order_purchases``, which reports "recorded against this order
        and claimed by no line". A listing capture is recorded against no order
        at all, and reporting one as a stale line of this one would be a new
        false alarm.

        Restrictions, each one a requirement:

        * ``supplier_order_reference IS NULL`` -- a purchase that already names an
          order is a line of *that* order, never of this one (FR-002).
        * within :data:`CANDIDATE_WINDOW` of the order's date (FR-003).
        * a date on both sides; nothing can be dated against nothing (FR-006).
        """
        if order_date is None:
            return []

        item_ids = {
            item_id for item_id in (
                vendor.item_id_of(line) for line in order.lines
            ) if item_id
        }
        if not item_ids:
            return []

        return (
            session.query(Purchase)
            .filter(
                Purchase.vendor == vendor.name,
                Purchase.vendor_item_id.in_(item_ids),
                Purchase.supplier_order_reference.is_(None),
                Purchase.order_date.isnot(None),
                Purchase.order_date >= order_date - CANDIDATE_WINDOW,
                Purchase.order_date <= order_date + CANDIDATE_WINDOW,
            )
            .order_by(Purchase.id)
            .all()
        )

    def _assign_candidates(
        self, session, order, vendor, order_date, recorded,
    ) -> Dict[str, 'CandidatePurchase']:
        """Which lines are offered which candidate purchase (033 FR-004).

        Returns a mapping of ``line.form_key`` to a :class:`CandidatePurchase`.

        **Every line that could be the candidate's line is offered it**, so two
        lines carrying the same item id are both asked. This is not the obvious
        design and the obvious one was wrong: draining a pool as lines matched
        gave the row to the *first* line only, and if the operator then excluded
        that line, the second captured with no question raised and wrote exactly
        the duplicate this feature exists to prevent. Found in review of PR #144,
        and reproduced before it was fixed.

        The assignment therefore cannot depend on the operator's decisions --
        ``review_order`` has none, and a capture that asked about a line the
        review never offered a control for would be unanswerable. So it depends
        on nothing but the order and the database, and **which line actually
        gets the row is settled at claim time** by ``capture_order_lines``:
        the first line to answer "same purchase" takes it, and a second line
        wanting the same row is an ordinary line, because one purchase cannot be
        two lines of an order.

        **A line already paired exactly takes nothing.** CAPTURED is settled
        before anything else and is not a question (FR-005).

        Where an item has two candidates -- the same thing bought twice inside
        the window -- the one **closest in date** to the order's is the one
        offered, ties by lowest id. Deterministic, so the review and the
        confirmation that follows it name the same row. The other is left alone
        rather than being offered to a second line: a purchase this capture does
        not claim stays exactly as it was, which is the conservative half of
        every choice in this flow.
        """
        rows = self._candidate_order_purchases(session, order, vendor, order_date)
        if not rows:
            return {}

        def nearness(row):
            return abs(row.order_date - order_date), row.id

        nearest: Dict[str, Purchase] = {}
        for row in rows:
            held = nearest.get(row.vendor_item_id)
            if held is None or nearness(row) < nearness(held):
                nearest[row.vendor_item_id] = row

        assigned: Dict[str, CandidatePurchase] = {}
        for line in order.lines:
            if line.form_key in recorded:
                continue
            item_id = vendor.item_id_of(line)
            if not item_id:
                continue
            row = nearest.get(item_id)
            if row is None:
                continue
            assigned[line.form_key] = CandidatePurchase(
                purchase_id=row.id,
                product_id=row.product_id,
                order_date=row.order_date,
                quantity=row.quantity,
                unit_price=row.unit_price,
                product_description=(
                    row.product.description if row.product else None
                ),
                is_received=row.received_date is not None,
            )

        return assigned

    def _recorded_order_lines(self, session, order, vendor) -> Dict[str, Purchase]:
        """Pair this order's lines to the purchases already recorded for it.

        Returns a mapping of ``line.form_key`` to its Purchase, so a caller can
        ask about a *line* rather than about an item id.

        **An item id does not identify a line**, and an order can carry the same
        item twice. Pairing them positionally, or by counting item-id
        occurrences, corrupts data as soon as that happens: capture one of two
        such lines, re-open the order, and the other line claims its purchase,
        reads as captured with the wrong quantity, and applying a change writes
        to the wrong row. The information is not derivable, so
        ``purchases.order_line_number`` stores it. PR #116 review.

        Reading a page rather than a service makes that case stronger, not
        weaker: a page's line ordering is not a contract at all.

        Two passes, and the order matters:

        1. **By line number.** Exact, and the only pass that runs for anything
           an order capture wrote.
        2. **By item id, for purchases carrying no line number** -- one recorded
           by hand against the same order, or captured before that column
           existed. Each is claimed once, by the first line that wants it, and
           never by a line that already matched exactly.

        A purchase no line claims is orphaned, which the caller reports.

        One implementation since feature 029; it was written twice before, once
        per vendor, with the item id substituted. What the vendor supplies is
        how its rows are found and what its item id is.
        """
        rows = vendor.order_purchases(self, session, order)
        if not rows:
            return {}

        by_line_number = {
            row.order_line_number: row
            for row in rows
            if row.order_line_number is not None
        }

        paired: Dict[str, Purchase] = {}
        claimed = set()
        for line in order.lines:
            row = by_line_number.get(line.line_number)
            if row is not None and id(row) not in claimed:
                paired[line.form_key] = row
                claimed.add(id(row))

        # Pass two: the ones with no line number to pair on.
        unclaimed = [
            row for row in rows
            if row.order_line_number is None and id(row) not in claimed
        ]
        for line in order.lines:
            if line.form_key in paired or not unclaimed:
                continue
            item_id = vendor.item_id_of(line)
            # A line with nothing to identify its item by cannot claim a
            # purchase this way. McMaster's reader has always skipped these;
            # DigiKey's never produced one, because a line without a DigiKey
            # part number is not built at all.
            if not item_id:
                continue
            for row in unclaimed:
                if row.vendor_item_id == item_id:
                    paired[line.form_key] = row
                    claimed.add(id(row))
                    unclaimed.remove(row)
                    break

        return paired

    def _mcmaster_order_purchases(self, session, order) -> List[Purchase]:
        """Every purchase already recorded for this order.

        **Two passes, and the order matters** -- because the Purchase Order
        string is editable in place on McMaster's page and is auto-generated as
        MMDD+SURNAME, so it is neither stable nor guaranteed unique
        (research.md §14).

        1. **By ``vendor_order_id``**, the stable id from the order's URL. This
           is what survives a renamed Purchase Order, and what tells two orders
           sharing an auto-generated name apart.
        2. **By ``supplier_order_reference``, for rows carrying no
           ``vendor_order_id``** -- anything recorded by hand, or captured
           before that column existed.

        Pass two is deliberately *not* a plain union with pass one. A union
        would hand order Y every row belonging to order X whenever the two share
        an auto-generated name, which is the collision this is here to prevent.
        Restricting it to rows with no id at all limits it to the genuinely
        ambiguous case, where there is nothing better to go on.

        When the payload carries no ``order_id``, the order number is all there
        is, and every row under it is taken -- which is exactly today's
        behaviour.
        """
        cleaned = (order.order_number or '').strip()
        if not cleaned:
            return []

        if not order.order_id:
            return (
                session.query(Purchase)
                .filter(
                    Purchase.vendor == MCMASTER_VENDOR,
                    Purchase.supplier_order_reference == cleaned,
                )
                .order_by(Purchase.id)
                .all()
            )

        return (
            session.query(Purchase)
            .filter(
                Purchase.vendor == MCMASTER_VENDOR,
                or_(
                    Purchase.vendor_order_id == order.order_id,
                    and_(
                        Purchase.vendor_order_id.is_(None),
                        Purchase.supplier_order_reference == cleaned,
                    ),
                ),
            )
            .order_by(Purchase.id)
            .all()
        )

    def _adopt_renamed_order(self, session, order) -> str:
        """Carry a renamed Purchase Order onto the rows already recorded for it.

        Returns the name they were filed under before, or `''` if nothing moved.

        **The id is the identity; the Purchase Order string is a label.** When
        the operator renames an order on McMaster's site, ``vendor_order_id``
        still recognizes it -- that is what the column is for -- but the rows go
        on carrying the old name, and the order screen is keyed by the *name*
        because that is the only thing a human can type. Left alone, a
        re-capture reconciles perfectly and then redirects the operator to a
        page reading "Nothing captured under this order", and a rename that also
        adds a line splits one order across two names with no view showing it
        whole. PR #123 review.

        So the record follows the vendor's own label. Only rows matched by id
        are touched: a row found by name already carries the name, and a row
        with no id is one this feature never wrote and has no business
        renaming.

        Not gated on ``apply_change``. That gate is for a quantity or price the
        operator is being asked to decide about; this is the catalog keeping up
        with a rename that has already happened, and leaving it stale breaks
        the screen rather than preserving anything.
        """
        cleaned = (order.order_number or '').strip()
        if not cleaned or not order.order_id:
            return ''

        stale = (
            session.query(Purchase)
            .filter(
                Purchase.vendor == MCMASTER_VENDOR,
                Purchase.vendor_order_id == order.order_id,
                Purchase.supplier_order_reference != cleaned,
            )
            .all()
        )
        if not stale:
            return ''

        previous = stale[0].supplier_order_reference or ''
        for row in stale:
            row.supplier_order_reference = cleaned
        session.flush()
        logger.info(
            f"McMaster order {order.order_id} was renamed from {previous!r} "
            f"to {cleaned!r}; {len(stale)} purchase(s) refiled"
        )
        return previous

    def _claim_purchase(self, purchase: Purchase, line, order_fields, order_date):
        """Make an existing purchase a line of this order (033 FR-012).

        The operator has said this row and this line are one physical purchase.
        What that means for the row is settled by a split
        :class:`~app.services.order_vendors.OrderVendor` already makes:

        * **Order-level fields are the order's.** The purchase is a line of it
          now, and every sibling row carries them. The reference and the line
          number are stamped unconditionally -- that is what makes a *second*
          capture of this order pair to it exactly and ask nothing.
        * **Line-level fields stay the operator's**, changed only through the
          "Update it?" tick the caller applies. They have had the box in their
          hands; the page has not.

        The remaining order fields are **gap-filled only**, the rule
        ``enrich_product`` already follows. Amazon's ``order_fields`` sets
        ``listing_url`` to the *order page* address, and overwriting a listing
        capture's ``/dp/...`` with it would destroy the one field that says where
        the item can be bought again.

        ``order_date`` is stamped so the order does not report two dates for
        itself -- ``find_captured_orders`` derives an order's date as the minimum
        across its rows, so a row left on the operator's typed date makes the
        order read as older than it is. **Except** where that would place the
        order after a recorded receipt: nothing arrives before it is ordered
        (``_validate_receipt_order``), and a claim must not create the row every
        other write path refuses.

        Never written: ``product_id`` (FR-015), ``received_date`` (FR-014),
        ``notes`` and ``listing_title``.

        The line number is read off the line rather than out of
        ``vendor.line_fields``, which also carries it. All three vendors derive
        it the same way, and ``line_fields`` computes the quantity and the unit
        price as well -- including running the operator's edited values through
        validation. Calling it here would let a quantity this claim is not
        writing refuse the claim.
        """
        purchase.supplier_order_reference = order_fields.get(
            'supplier_order_reference'
        )
        purchase.order_line_number = line.line_number

        if order_date is not None and not (
            purchase.received_date is not None
            and purchase.received_date < order_date
        ):
            purchase.order_date = order_date

        for field, value in order_fields.items():
            if field == 'supplier_order_reference' or value is None:
                continue
            if getattr(purchase, field, None) is None:
                setattr(purchase, field, value)

    def _apply_order_change(self, purchase: Purchase, line, decision, vendor) -> bool:
        """Bring a recorded purchase into line with what the order now says.

        The vendor's own line fields are used, so the operator's edited values
        win here exactly as they do on a fresh capture wherever that vendor
        offers an edit -- "apply this change" applies what the review displayed.

        Returns whether anything was actually written. **A field the vendor did
        not give is not applied**, there being nothing to apply, and the caller
        must not count that as an update or the flash reports "1 line(s)
        updated" for a write that was skipped. PR #123 review.

        One implementation since feature 029, and DigiKey's half gains that last
        paragraph by it: the fix landed on the McMaster copy and had never been
        applied back to the DigiKey one, which is the exact duplication cost the
        consolidation exists to remove.
        """
        fields = vendor.line_fields(self, line, decision)
        wrote = False

        quantity = fields.get('quantity')
        if quantity is not None and quantity != purchase.quantity:
            purchase.quantity = quantity
            wrote = True

        unit_price = fields.get('unit_price')
        if unit_price is not None and unit_price != purchase.unit_price:
            purchase.unit_price = unit_price
            wrote = True

        return wrote

    def _review_order_line(
        self, session, line, part, recorded, vendor, candidates=None,
    ) -> ReviewedLine:
        """Decide one line's state. Reads only.

        The four states are exclusive and tested in this order: already
        captured, then a contradicted item id, then an ordinary match, then new.
        CAPTURED comes first because a line already recorded is not a line to
        decide anything else about.

        ``part`` is the vendor's own detail for the item where it has any. Only
        DigiKey does; for the others the page *is* the detail and this is None,
        which is an ordinary state rather than an error.

        ``candidates`` is feature 033, and it is deliberately **not** a fifth
        state. A line whose candidate the operator calls a separate purchase is
        whatever it already was -- NEW, MATCHED or CONFLICT -- so folding the two
        into one value would throw that answer away and force a second question.
        The candidate rides alongside the state instead, and a line can carry
        both it and a CONFLICT: two questions, asked side by side, exactly as
        ``capture_order`` already asks its two.

        One implementation since feature 029.
        """
        suggested = vendor.suggested_description(line, part)[:MAX_DESCRIPTION_LENGTH]
        candidate = (candidates or {}).get(line.form_key)

        existing = recorded.get(line.form_key)
        if existing is not None:
            return ReviewedLine(
                line=line,
                state=OrderLineState.CAPTURED,
                part=part,
                suggested_description=suggested,
                product_id=existing.product_id,
                product_description=(
                    existing.product.description if existing.product else None
                ),
                purchase_id=existing.id,
                recorded_quantity=existing.quantity,
                recorded_unit_price=existing.unit_price,
            )

        product, by_own_item_id = vendor.find_product(self, session, line)
        if product is not None:
            # **A contradiction is only possible on a match found by the
            # vendor's own item id.** A distributor recycling a part number for
            # a different part is the most damaging failure in the feature,
            # because nothing looks wrong afterwards -- the price history of one
            # product quietly becomes the history of two. A product found *by*
            # its manufacturer part number cannot contradict that same number,
            # which is why the flag exists rather than checking unconditionally.
            contradicted = (
                by_own_item_id
                and line.manufacturer_part_number
                and product.manufacturer_part_number
                and line.manufacturer_part_number
                != product.manufacturer_part_number
            )
            return ReviewedLine(
                line=line,
                state=(OrderLineState.CONFLICT if contradicted
                       else OrderLineState.MATCHED),
                part=part,
                suggested_description=suggested,
                product_id=product.id,
                product_description=product.description,
                product_manufacturer_part_number=product.manufacturer_part_number,
                candidate=candidate,
            )

        return ReviewedLine(
            line=line,
            state=OrderLineState.NEW,
            part=part,
            suggested_description=suggested,
            candidate=candidate,
        )

    def _orphaned_order_purchases(
        self, session, order, vendor, paired, also_claimed=(),
    ) -> tuple:
        """Purchases recorded for this order that no line of it claims.

        **Reported and never deleted.** A purchase the operator can see and
        cancel is better than one that vanishes, and a line missing from a
        re-read order is at least as likely to be a selector that stopped
        matching as an order that changed.

        ``also_claimed`` is the ids written by the caller's own capture, and it
        is not optional decoration. A capture re-queries inside its open
        session, so rows its loop has just added and flushed come back from that
        query -- while ``paired`` was built *before* the loop and cannot name
        them. Without them, every line of a brand-new order is reported as
        orphaned by the capture that created it, and the flash tells the
        operator the lines they just captured are stale. The read-only review
        needs none of this, because nothing writes between its query and its
        pairing, and it passes nothing.

        One implementation since feature 029.
        """
        claimed = {purchase.id for purchase in paired.values()}
        claimed.update(also_claimed)
        return tuple(
            row.id
            for row in vendor.order_purchases(self, session, order)
            if row.id not in claimed
        )

    def _mcmaster_product_by_part_number(
        self, session, part_number: str,
    ) -> Optional[Product]:
        """The product a McMaster part number names, however it was recorded.

        **Both vendor-scoped identifier types are tried**, and that is not
        belt-and-braces. This feature's order capture writes `DISTRIBUTOR`
        (FR-012), but the product-page capture goes through ``capture_order``,
        which writes `VENDOR` for every vendor it has ever handled. Looking for
        only one of them would mean an order capture failed to recognize a part
        the operator had already cataloged from its product page, and would
        create a second product for it -- the duplicate FR-007 exists to
        prevent.

        Editing ``capture_order`` to write a different type for one vendor was
        the alternative, and it was rejected: it is the write path every Amazon
        capture goes through, SC-010 requires that path to behave identically
        after this feature, and both types are vendor-scoped and both are in
        ``VENDOR_SCOPED_TYPES``, so a scan finds either one already.
        """
        for id_type in (IdentifierType.DISTRIBUTOR, IdentifierType.VENDOR):
            product = self._mcmaster_product_by_identifier(
                session, id_type, part_number, vendor=MCMASTER_VENDOR,
            )
            if product is not None:
                return product
        return None

    def _mcmaster_product_by_identifier(
        self, session, id_type: IdentifierType, value: str, vendor: str = '',
    ) -> Optional[Product]:
        """Find a product by one identifier, inside a session already open.

        ``find_product_by_identifier`` opens its own session, which is no use
        from inside a transaction that has to stay open across the whole order.
        """
        if not value:
            return None
        row = (
            session.query(ProductIdentifier)
            .filter(
                ProductIdentifier.id_type == id_type.value,
                ProductIdentifier.value == value.strip(),
                ProductIdentifier.vendor == vendor,
            )
            .first()
        )
        return row.product if row is not None else None

    def _create_mcmaster_product(
        self, session, line, decision, claim_distributor: bool = True,
    ) -> Product:
        """Create the product one order line names, inside the open session.

        Deliberately not ``create_product``: that opens its own session, and the
        whole point of this path is that the order writes as one transaction.
        """
        description = self._validate_description(
            (decision.get('description') or '').strip()
            or line.description
            or line.part_number
        )

        product = Product(
            description=description,
            # McMaster names no manufacturer on the great majority of its goods
            # (research.md §5). Left blank rather than filled with 'McMaster-
            # Carr', which would be a claim about who made the thing rather
            # than about who sold it -- and the vendor is on the purchase.
            manufacturer_part_number=_clean(line.manufacturer_part_number),
        )
        session.add(product)
        session.flush()

        session.add(ProductIdentifier(
            product_id=product.id,
            id_type=IdentifierType.INTERNAL.value,
            value=self._unique_internal_code(session),
            vendor='',
            validation_overridden=False,
        ))

        # FR-012, and it is the inverse of the DigiKey case. There the MPN is
        # the primary name; here it is written **only** where the page actually
        # stated one, because inventing an identifier McMaster never gave would
        # collide with a real MPN later and identifiers are unique.
        if line.manufacturer_part_number:
            self._add_mcmaster_identifier(
                session, product.id, IdentifierType.MPN,
                line.manufacturer_part_number,
            )
        if claim_distributor and line.part_number:
            self._add_mcmaster_identifier(
                session, product.id, IdentifierType.DISTRIBUTOR,
                line.part_number, vendor=MCMASTER_VENDOR,
            )

        return product

    def _amazon_product_by_asin(self, session, asin: str) -> Optional[Product]:
        """Find a product by its ASIN, scoped to Amazon, inside an open session."""
        if not asin:
            return None
        return self._digikey_product_by_identifier(
            session, IdentifierType.VENDOR, asin, vendor=AMAZON_VENDOR,
        )

    def _create_amazon_product(self, session, line, decision,
                               claim_distributor: bool = True) -> Product:
        """Create the product one Amazon order line names, inside the session.

        Deliberately not ``create_product``: that opens its own session, and the
        whole point of this path is that the order writes as one transaction.

        **What this creates is thin, and 029 FR-026 says so out loud.** An order
        page states a title, a quantity and a price; the gallery, the
        specification rows, the bullet points and the barcodes are all on the
        *listing* page, one page per line. Running the existing single-listing
        capture against the same ASIN later fills the product in and attaches to
        this one rather than creating a second (FR-027).

        No manufacturer: Amazon's order page names a *seller*, which is a claim
        about who sold it rather than who made it, and the vendor is on the
        purchase already.
        """
        description = self._validate_description(
            (decision.get('description') or '').strip()
            or line.title
        )

        product = Product(description=description)
        session.add(product)
        session.flush()

        session.add(ProductIdentifier(
            product_id=product.id,
            id_type=IdentifierType.INTERNAL.value,
            value=self._unique_internal_code(session),
            vendor='',
            validation_overridden=False,
        ))

        # The ASIN, scoped to Amazon -- the same identifier a single-listing
        # Amazon capture writes, which is what lets FR-027's later enrichment
        # find this product instead of making another.
        if claim_distributor and line.asin:
            self._add_mcmaster_identifier(
                session, product.id, IdentifierType.VENDOR,
                line.asin, vendor=AMAZON_VENDOR,
            )

        return product

    def _add_mcmaster_identifier(
        self, session, product_id, id_type, value, vendor='',
    ):
        """Add one identifier, tolerating a value another product already holds.

        A product's identity is its own row. A vendor that reuses an identifier
        must not merge two products or mutate the first, so a clash leaves the
        identifier off and says so -- the same thing ``create_product`` does.
        """
        try:
            self._add_identifier(
                session, product_id, id_type.value, value, vendor=vendor,
            )
        except DuplicateItemError as clash:
            logger.warning(
                f"Identifier {value!r} already belongs to product "
                f"{clash.item_id}; product {product_id} was created without it"
            )

    def find_captured_orders(self) -> List[CapturedOrder]:
        """Every captured order, across every vendor, most recent first.

        029 FR-033. One aggregate over ``purchases`` grouped by vendor and order
        number -- **derived, not stored**, exactly as an individual order screen
        is. There is no orders table and this does not add one.

        A purchase carrying no supplier order reference belongs to no order and
        appears in none: that is a hand-recorded purchase or a single-listing
        capture, and it is reachable from its product.

        No index work and no caching: ``supplier_order_reference`` is already
        indexed, the table holds a few thousand rows at this application's scale,
        and Constitution I asks for a measurement before optimizing.
        """
        with self._session() as session:
            rows = (
                session.query(
                    Purchase.vendor,
                    Purchase.supplier_order_reference,
                    func.min(Purchase.order_date).label('order_date'),
                    func.count(Purchase.id).label('line_count'),
                    func.sum(
                        case((Purchase.received_date.is_(None), 1), else_=0)
                    ).label('outstanding'),
                )
                .filter(
                    Purchase.supplier_order_reference.isnot(None),
                    Purchase.supplier_order_reference != '',
                )
                .group_by(Purchase.vendor, Purchase.supplier_order_reference)
                .all()
            )

        orders = [
            CapturedOrder(
                vendor=row.vendor,
                order_number=row.supplier_order_reference,
                order_date=row.order_date,
                line_count=int(row.line_count or 0),
                outstanding_count=int(row.outstanding or 0),
            )
            for row in rows
        ]
        # Sorted in Python rather than by the query: order_date is nullable, and
        # the two backends disagree about where NULLs sort. An order with no date
        # goes last either way.
        orders.sort(
            key=lambda o: (o.order_date is not None, o.order_date or datetime.min),
            reverse=True,
        )
        return orders

    def find_order_lines_for(self, vendor_name: str, order_number: str) -> List[Purchase]:
        """The purchases that make up one order, for any vendor.

        This is the whole of "open a captured order": there is no order record
        to load, only the purchases carrying its number. Derived rather than
        stored, so it cannot fall out of step with them -- it has nothing of its
        own to drift.

        One implementation since feature 029. ``find_order_lines`` and
        ``find_mcmaster_order_lines`` remain as the vendor-named entry points
        their callers and the regression suites use.
        """
        cleaned = (order_number or '').strip()
        if not cleaned:
            return []

        with self._session() as session:
            return (
                session.query(Purchase)
                .options(selectinload(Purchase.product))
                .filter(
                    Purchase.vendor == vendor_name,
                    Purchase.supplier_order_reference == cleaned,
                )
                .order_by(Purchase.id)
                .all()
            )

    def find_mcmaster_order_lines(self, order_number: str) -> List[Purchase]:
        """The purchases that make up one McMaster order (028 FR-027).

        Keyed by the Purchase Order string, because that is the only order
        identifier the operator can recognize or type.

        See :meth:`find_order_lines_for`.
        """
        return self.find_order_lines_for(MCMASTER_VENDOR, order_number)

    def find_order_lines(self, sales_order_number: str) -> List[Purchase]:
        """The purchases that make up one DigiKey order (024 FR-017).

        See :meth:`find_order_lines_for`.
        """
        return self.find_order_lines_for(DIGIKEY_VENDOR, sales_order_number)

    def find_mcmaster_receivable(self, part_number: str) -> List[Purchase]:
        """The outstanding McMaster lines a scanned part number names (FR-032).

        **Outstanding only** -- and that is the one place this deliberately
        differs from ``find_receivable`` next door, which includes received
        rows on purpose so it can tell "you already received this" apart from
        "this order has no such line" for a label that names an order.

        A bare part number names no order, so there is no such distinction to
        draw. An already-received part is simply a part the catalog holds, and
        falling through to today's behaviour is the right answer for it
        (FR-032b).

        Returns:
            The outstanding purchases, oldest first, each with its product
            loaded. Normally a list of one; longer when the same part is
            outstanding on two orders, and the caller must then ask rather than
            pick (FR-032a).
        """
        cleaned = (part_number or '').strip()
        if not cleaned:
            return []

        with self._session() as session:
            return (
                session.query(Purchase)
                .options(selectinload(Purchase.product))
                .filter(
                    Purchase.vendor == MCMASTER_VENDOR,
                    Purchase.vendor_item_id == cleaned,
                    Purchase.received_date.is_(None),
                )
                .order_by(Purchase.id)
                .all()
            )

    def find_receivable(
        self, sales_order_number: str, digikey_part_number: str,
    ) -> List[Purchase]:
        """The purchases a scanned bag label names (FR-019).

        A label's ``1K`` and ``P`` together identify one line of one order, so
        this is normally a list of one. It can be longer when the same part was
        ordered twice on one order, and the caller must then ask rather than pick
        (FR-026).

        **Received purchases are included**, deliberately. The caller needs to
        tell "you already received this" (FR-023) apart from "this order has no
        such line" (FR-024), and an outstanding-only filter collapses the two.
        """
        order_number = (sales_order_number or '').strip()
        part_number = (digikey_part_number or '').strip()
        if not order_number or not part_number:
            return []

        with self._session() as session:
            return (
                session.query(Purchase)
                .options(selectinload(Purchase.product))
                .filter(
                    Purchase.vendor == DIGIKEY_VENDOR,
                    Purchase.supplier_order_reference == order_number,
                    Purchase.vendor_item_id == part_number,
                )
                .order_by(Purchase.id)
                .all()
            )

    # -- DigiKey internals -------------------------------------------------

    def _digikey_part(self, digikey_client, part_number: str):
        """DigiKey's detail for one part, or None.

        **None is an ordinary state** (FR-041). A part DigiKey will not answer
        for costs that line its manufacturer, category and parametric detail,
        and nothing else: the line still captures on everything the order gave.
        Only a failed *order* read refuses a capture.

        This is the same split ``store_listing_images`` already makes for an
        unreachable image host, and for the same reason.
        """
        if digikey_client is None or not part_number:
            return None
        try:
            return digikey_client.get_part(part_number)
        except Exception as e:
            # Deliberately broad. Anything the client can raise -- not found,
            # throttled, unreachable -- means the same thing here: this line has
            # no extra detail, and that must not cost the operator the capture.
            logger.info(f"No DigiKey detail for {part_number}: {e}")
            return None

    def _digikey_product_by_identifier(
        self, session, id_type: IdentifierType, value: str, vendor: str = '',
    ) -> Optional[Product]:
        """Find a product by one identifier, inside a session already open.

        ``find_product_by_identifier`` opens its own session, which is no use
        from inside a transaction that has to stay open across the whole order.
        """
        if not value:
            return None
        row = (
            session.query(ProductIdentifier)
            .filter(
                ProductIdentifier.id_type == id_type.value,
                ProductIdentifier.value == value.strip(),
                ProductIdentifier.vendor == vendor,
            )
            .first()
        )
        return row.product if row is not None else None

    def _create_digikey_product(
        self, session, line, part, decision, claim_distributor: bool = True,
    ) -> Product:
        """Create the product one order line names, inside the open session.

        Deliberately not ``create_product``: that opens its own session, and the
        whole point of this path is that the order writes as one transaction.
        """
        description = self._validate_description(
            (decision.get('description') or '').strip()
            or (part.description if part else '')
            or line.description
        )

        product = Product(
            description=description,
            # The order response has no manufacturer name; this is the only
            # place it can come from (FR-040).
            manufacturer=_clean(part.manufacturer) if part else None,
            manufacturer_part_number=_clean(line.manufacturer_part_number),
            # DigiKey's category is a suggestion about their catalog, not a
            # statement about this workshop's shelves. It is offered because a
            # blank is worse, and the operator can change it like any other.
            category_path=self._validate_category_path(
                part.category_path if part else None
            ),
        )
        session.add(product)
        session.flush()

        session.add(ProductIdentifier(
            product_id=product.id,
            id_type=IdentifierType.INTERNAL.value,
            value=self._unique_internal_code(session),
            vendor='',
            validation_overridden=False,
        ))

        if line.manufacturer_part_number:
            self._add_digikey_identifier(
                session, product.id, IdentifierType.MPN,
                line.manufacturer_part_number,
            )
        if claim_distributor:
            self._add_digikey_identifier(
                session, product.id, IdentifierType.DISTRIBUTOR,
                line.digikey_part_number, vendor=DIGIKEY_VENDOR,
            )

        self._enrich_digikey_product(session, product, part)
        return product

    def _add_digikey_identifier(self, session, product_id, id_type, value, vendor=''):
        """Add one identifier, tolerating a value another product already holds.

        FR-008: a product's identity is its own row. A vendor that reuses an
        identifier must not merge two products or mutate the first, so a clash
        leaves the identifier off and says so -- the same thing
        ``create_product`` does.
        """
        try:
            self._add_identifier(
                session, product_id, id_type.value, value, vendor=vendor,
            )
        except DuplicateItemError as clash:
            logger.warning(
                f"Identifier {value!r} already belongs to product {clash.item_id}; "
                f"product {product_id} was created without it"
            )

    def _enrich_digikey_product(self, session, product, part) -> None:
        """Write DigiKey's part detail onto a product, filling gaps only.

        **A value the operator has already set wins.** Enrichment fills what is
        blank; it does not overwrite a manufacturer someone corrected or a
        category someone filed. The same rule a captured listing's
        specifications already follow.
        """
        if product is None or part is None:
            return

        if part.manufacturer and not product.manufacturer:
            product.manufacturer = part.manufacturer
        if part.category_path and not product.category_path:
            product.category_path = self._validate_category_path(part.category_path)

        if not part.parameters:
            return

        existing = {
            normalized_row_name(row.name)
            for row in session.query(ProductSpecification)
            .filter(ProductSpecification.product_id == product.id)
            .all()
        }
        order = len(existing)
        for name, value in part.parameters:
            if normalized_row_name(name) in existing:
                # The operator's row wins and is not examined (FR-030).
                continue
            session.add(ProductSpecification(
                product_id=product.id, name=name, value=value, display_order=order,
            ))
            existing.add(normalized_row_name(name))
            order += 1

    def scan(self, raw: str) -> ScanResolution:
        """Classify a raw scan and resolve it in one step.

        Args:
            raw: The text exactly as the scanner or the operator produced it.

        Returns:
            A ScanResolution. Every well-formed scan gets one; nothing 404s.
        """
        return self.resolve_scan(classify(raw))

    def resolve_scan(self, classification: ScanClassification) -> ScanResolution:
        """Turn "what kind of thing is this?" into "what should happen next?".

        Four outcomes: the scan is a product we hold, a line of a captured
        DigiKey order waiting to be received, an offer to create a product with
        what was scanned already attached, or a search carrying the raw text. A
        scan that matches nothing is answered, not refused (FR-018, SC-008).

        **This said "three outcomes and no fourth" until feature 024.** The
        requirements it cited say that nothing dead-ends, and the fourth answer
        does not weaken that: the free-text rule below still always matches. What
        changed is that a bag from a captured order has a better answer than
        "here is the product" -- see the ECIA branch.

        Args:
            classification: The pure classifier's structural answer.

        Returns:
            A ScanResolution with outcome 'product', 'receive', 'create' or
            'search'.
        """
        kind = classification.kind

        if kind in (ScanKind.INTERNAL, ScanKind.GTIN):
            id_type = (
                IdentifierType.INTERNAL if kind is ScanKind.INTERNAL else IdentifierType.GTIN
            )
            product = self.find_product_by_identifier(
                classification.value, id_type=id_type.value
            )
            if product is not None:
                return ScanResolution('product', classification, product=product)

            return ScanResolution('create', classification, prefill={
                'identifier': classification.value,
                'id_type': id_type.value,
                'raw_scan': classification.raw,
            })

        if kind is ScanKind.ECIA:
            fields = classification.ecia_fields
            manufacturer_part_number = fields.get('1P', '')

            # A bag from a captured DigiKey order: 1K names the order and P names
            # the line within it (024 FR-019).
            #
            # **This runs before the MPN lookup below, and the order is
            # load-bearing.** Capturing an order creates products carrying these
            # part numbers, so the MPN lookup would match happily -- and a bag
            # for a part you have bought before would open the product page
            # instead of its receipt. That would satisfy FR-019 only for parts
            # you have never bought, which is exactly backwards.
            #
            # Nothing matching falls through to the behaviour below unchanged
            # (FR-024, FR-025).
            receivable = self.find_receivable(
                fields.get('1K', ''), fields.get('P', '')
            )
            if receivable:
                return ScanResolution(
                    'receive', classification, purchases=receivable
                )

            if manufacturer_part_number:
                product = self.find_product_by_identifier(
                    manufacturer_part_number, id_type=IdentifierType.MPN.value
                )
                if product is not None:
                    return ScanResolution('product', classification, product=product)

            # Every extracted value goes into the draft, and every one of them
            # stays editable (FR-017) -- values were never coerced on the way in.
            prefill = {
                'identifier': manufacturer_part_number or fields.get('P', ''),
                'id_type': IdentifierType.MPN.value,
                'raw_scan': classification.raw,
            }
            for key, target in (
                ('1P', 'manufacturer_part_number'),
                ('P', 'distributor_part_number'),
                ('Q', 'quantity'),
                ('K', 'order_reference'),
                ('1K', 'supplier_order_reference'),
                ('9D', 'date_code'),
                ('10D', 'date_code_alt'),
            ):
                if fields.get(key):
                    prefill[target] = fields[key]

            return ScanResolution('create', classification, prefill=prefill)

        # FREE_TEXT.
        #
        # **This lookup comes first, and the precedence is load-bearing.** A
        # McMaster bag carries a bare part number and nothing else, and
        # capturing an order creates products carrying those part numbers as
        # vendor-scoped identifiers -- so the lookup below would match happily
        # and open the *product page* for a part you have bought before, while
        # working correctly only for parts you never had. That is exactly
        # backwards, and it is the trap the ECIA branch above already documents.
        receivable = self.find_mcmaster_receivable(classification.value)
        if receivable:
            return ScanResolution(
                'receive', classification, purchases=receivable
            )

        # Rule 4 lives here rather than in the classifier: a vendor
        # item id such as an ASIN has no distinguishing shape, so the only way to
        # recognize one is to look it up.
        for id_type in VENDOR_SCOPED_TYPES:
            product = self.find_product_by_identifier(
                classification.value, id_type=id_type.value
            )
            if product is not None:
                return ScanResolution(
                    'product',
                    ScanClassification(
                        kind=ScanKind.VENDOR,
                        value=classification.value.strip(),
                        raw=classification.raw,
                    ),
                    product=product,
                )

        return ScanResolution('search', classification)

    def _add_identifier(
        self,
        session,
        product_id: int,
        id_type: str,
        value: str,
        vendor: Optional[str] = None,
        override: bool = False,
    ) -> ProductIdentifier:
        """Validate, normalize and insert one identifier inside an open session."""
        identifier_type = self._validate_identifier_type(id_type)
        vendor = _clean(vendor) or ''

        if identifier_type in VENDOR_SCOPED_TYPES and not vendor:
            raise ValidationError(
                f"{identifier_type.value} identifiers require a vendor -- a vendor's "
                f"item id is only meaningful within that vendor",
                field='vendor'
            )

        normalized, overridden = self._normalize_identifier_value(
            identifier_type, value, override
        )

        existing = session.query(ProductIdentifier).filter(
            ProductIdentifier.id_type == identifier_type.value,
            ProductIdentifier.value == normalized,
            ProductIdentifier.vendor == vendor,
        ).first()
        if existing is not None:
            if existing.product_id == product_id:
                return existing
            # Not a ValidationError: the operator's input is fine, it is the
            # catalog that already has a claim on this value. Callers treat the
            # two cases differently.
            raise DuplicateItemError(
                f"Identifier {normalized} already belongs to product {existing.product_id}",
                item_id=str(existing.product_id),
                duplicate_field='value',
            )

        identifier = ProductIdentifier(
            product_id=product_id,
            id_type=identifier_type.value,
            value=normalized,
            vendor=vendor,
            validation_overridden=overridden,
        )
        session.add(identifier)
        return identifier

    def _normalize_identifier_value(
        self, identifier_type: IdentifierType, value: str, override: bool
    ) -> tuple:
        """Return the storable form of an identifier value and its override flag."""
        if not isinstance(value, str) or not value.strip():
            raise ValidationError("Identifier value is required", field='value')

        raw = value.strip()

        if identifier_type is IdentifierType.GTIN:
            # An all-zero key is what a wedge emits on a no-read. It is never a
            # trade item, so there is no override for it (FR-010).
            if gtin_utils.is_all_zero(raw):
                raise ValidationError(
                    "That barcode reads as all zeros, which is a scanner no-read "
                    "rather than a product. Rescan it.",
                    field='value', value=raw
                )

            key = gtin_utils.normalize_and_validate(raw)
            if key is not None:
                return key, False

            if not override:
                raise ValidationError(
                    f"{raw} is not a valid barcode (wrong length or bad check digit). "
                    f"Store it anyway only if you mean to.",
                    field='value', value=raw
                )

            # Keep the operator's value as they gave it, normalized to the
            # 14-digit key when the shape allows -- and record that they meant it.
            return gtin_utils.normalize(raw) or raw, True

        if identifier_type is IdentifierType.INTERNAL:
            if not internal_id_utils.is_internal_id(raw):
                raise ValidationError(
                    "Internal codes are generated by this system, not entered by hand",
                    field='value', value=raw
                )
            return internal_id_utils.normalize_internal_id(raw), False

        if len(raw) > 128:
            raise ValidationError(
                f"Identifier value is longer than 128 characters", field='value', value=raw
            )

        return raw, False

    def _unique_internal_code(self, session) -> str:
        """Generate an internal code that is not already in use."""
        for _ in range(10):
            candidate = internal_id_utils.generate_internal_id()
            clash = session.query(ProductIdentifier).filter(
                ProductIdentifier.id_type == IdentifierType.INTERNAL.value,
                ProductIdentifier.value == candidate,
            ).first()
            if clash is None:
                return candidate

        # 32^10 values and ten tries: reaching here means something is wrong with
        # the generator, and silently reusing a code would be worse than failing.
        raise ValidationError("Could not generate an unused internal product code")

    # -- Tags --------------------------------------------------------------

    def set_tags(self, product_id: int, names: List[str]) -> Product:
        """Replace a product's tags, creating any that are new (FR-031).

        Args:
            product_id: The product.
            names: The tag names it should end up with. Created inline the same
                way categories are -- there is no setup step.

        Returns:
            The updated Product.

        Raises:
            ItemNotFoundError: If the product does not exist.
        """
        with self._session() as session:
            product = session.query(Product).options(
                selectinload(Product.tags)
            ).filter(Product.id == product_id).first()
            if product is None:
                raise ItemNotFoundError(
                    f"Product {product_id} not found", item_id=str(product_id)
                )

            wanted = {
                _clean(name).lower() for name in (names or []) if _clean(name)
            }

            for tag in list(product.tags):
                if tag.name not in wanted:
                    product.tags.remove(tag)

            for name in wanted:
                self._attach_tag(session, product, name)

        return self.get_product(product_id)

    def list_tags(self, prefix: Optional[str] = None) -> List[str]:
        """Every tag name in use, for the filter and the inline-create datalist.

        Args:
            prefix: Optionally narrow to tags starting with this.

        Returns:
            Tag names, alphabetically.
        """
        with self._session() as session:
            query = session.query(Tag.name)
            cleaned = _clean(prefix)
            if cleaned:
                query = query.filter(Tag.name.like(f"{cleaned.lower()}%"))
            return [row[0] for row in query.order_by(Tag.name).all()]

    # -- Specification vocabulary -------------------------------------------

    def list_specification_names(self, prefix: Optional[str] = None) -> List[str]:
        """Every specification name in use, plus the keys the taxonomy pins.

        For the name datalists (FR-019). The keys are offered before any product
        carries them (025 SC-010) for a sharper reason than categories are:
        ``rename_category`` and ``rename_tag`` exist and there is no
        ``rename_specification``, so ``Thread`` beside ``Thread Size`` cannot be
        repaired in bulk once both are in use. Prevention at the point of typing
        is the only mechanism there is.

        The prefix is applied in Python because half the candidates are not
        rows. ``_dedupe_fold_case`` then keeps one spelling per folded name,
        and its sort makes that the record's spelling rather than a lowercase
        variant somebody typed -- which is the one worth keeping.

        Args:
            prefix: Optionally narrow to names starting with this,
                case-insensitively.

        Returns:
            The distinct names, sorted case-insensitively.
        """
        candidates = list(
            self._distinct_specification_column(ProductSpecification.name, None)
        ) + list(catalog_taxonomy.specification_keys())

        cleaned = _clean(prefix)
        if cleaned:
            lowered = cleaned.lower()
            candidates = [
                name for name in candidates if name.lower().startswith(lowered)
            ]

        return _dedupe_fold_case(candidates)

    def list_specification_values(
        self, name: str, prefix: Optional[str] = None
    ) -> List[str]:
        """Every value recorded under one specification name (FR-020).

        Args:
            name: The specification name, matched whole and case-insensitively --
                the same way the filter matches it.
            prefix: Optionally narrow the values.

        Returns:
            The distinct values, sorted case-insensitively. A blank or
            unrecorded name returns ``[]``: an unknown name is an ordinary
            state, because the operator is mid-word.
        """
        cleaned_name = _clean(name)
        if not cleaned_name:
            return []

        return self._distinct_specification_column(
            ProductSpecification.value,
            prefix,
            scope=func.lower(ProductSpecification.name) == cleaned_name.lower(),
        )

    def _distinct_specification_column(
        self, column, prefix: Optional[str], scope=None
    ) -> List[str]:
        """The distinct values of one specification column, for a datalist.

        Both vocabulary readers are this same shape -- open a session, narrow by
        an optional case-insensitive prefix, fold-case dedupe -- and differ only
        in the column and whether the rows are scoped to one name.

        Args:
            column: The ProductSpecification column to read.
            prefix: Optionally narrow to values starting with this.
            scope: An optional extra filter clause.

        Returns:
            The distinct values, sorted and deduplicated case-insensitively.
        """
        with self._session() as session:
            query = session.query(column)
            if scope is not None:
                query = query.filter(scope)

            cleaned = _clean(prefix)
            if cleaned:
                query = query.filter(func.lower(column).like(
                    f"{_escape_like(cleaned.lower())}%", escape='\\'
                ))

            return _dedupe_fold_case(row[0] for row in query.all())

    # -- Categories --------------------------------------------------------

    def list_categories(self, prefix: Optional[str] = None) -> List[str]:
        """Every category path in use, plus every branch the taxonomy names.

        There is still no categories table: a category is a string on a product,
        so an occupied category is the distinct set of those strings. What the
        taxonomy adds is the branches nobody has filed into yet (025 FR-012) --
        otherwise the first product into each of them gets typed by hand, which
        is where two spellings of one category come from.

        Listing a branch creates nothing, and a path in use that the taxonomy
        does not name is never dropped (025 FR-017). A path that is both offered
        and occupied appears once, because the union is a set (025 FR-018).

        The subtree filter is applied in Python rather than as a LIKE. Half the
        candidates are not rows, and ``is_descendant`` is the same
        segment-boundary rule the SQL encodes -- without the collation's
        case and accent folding, which ``rename_category`` documents as a source
        of false matches.

        Args:
            prefix: Optionally narrow to a subtree.

        Returns:
            Distinct category paths, alphabetically.
        """
        with self._session() as session:
            rows = session.query(Product.category_path).filter(
                Product.category_path.isnot(None)
            ).distinct().all()

        paths = {row[0] for row in rows} | set(catalog_taxonomy.category_paths())

        ancestor = category_utils.canonical(prefix)
        if ancestor is not None:
            paths = {
                path for path in paths
                if category_utils.is_descendant(path, ancestor)
            }

        return sorted(paths)

    def category_tree(self) -> List[Dict[str, Any]]:
        """Every category, with how many products sit directly in each.

        The union of the paths products carry and the branches the taxonomy
        names, so the page shows the tree rather than the subset of it that
        happens to be occupied.

        ``count`` is 0 for a branch on offer that nobody has filed into, which
        was previously an entry that could not exist. ``in_taxonomy`` is False
        for a path somebody typed that the record does not name -- legitimate
        (025 FR-015), and the only thing that makes that divergence visible
        (025 FR-019).

        ``subtree_count`` is what a caller must gate a rename control on, and
        it is deliberately not ``count``. ``rename_category`` rewrites every
        product at *or under* the path and refuses only when that whole set is
        empty -- so a parent branch holding nothing directly, with an occupied
        child, renames perfectly well and carries the child with it. Gating on
        ``count`` would hide the control for most of the parents a taxonomy
        adds, because filing happens at the leaves.

        Args:
            None.

        Returns:
            One entry per category path: its path, its depth, its name, its
            direct product count, the count at or under it, and whether the
            taxonomy names it.
        """
        with self._session() as session:
            rows = session.query(
                Product.category_path, func.count(Product.id)
            ).filter(
                Product.category_path.isnot(None)
            ).group_by(Product.category_path).all()

        counts = {path: count for path, count in rows}
        taxonomy = set(catalog_taxonomy.category_paths())

        def subtree_total(path: str) -> int:
            """Products at or under ``path`` -- the set a rename would move."""
            return sum(
                occupants for occupied, occupants in counts.items()
                if category_utils.is_descendant(occupied, path)
            )

        return [
            {
                'path': path,
                'depth': len(category_utils.segments(path)),
                'name': category_utils.segments(path)[-1],
                'count': counts.get(path, 0),
                'subtree_count': subtree_total(path),
                'in_taxonomy': path in taxonomy,
            }
            for path in sorted(set(counts) | taxonomy)
        ]

    def _subtree_clause(self, path: str):
        """The pair of conditions that select a category and everything under it.

        Equality plus the escaped LIKE, which is what makes the boundary the
        separator: ``elctronics-surplus`` is a different category from
        ``elctronics`` and neither condition matches it.
        """
        return or_(
            Product.category_path == path,
            Product.category_path.like(
                category_utils.descendant_like_pattern(path), escape='\\'
            ),
        )

    def rename_category(self, old_path: str, new_path: str) -> Dict[str, Any]:
        """Rename a category, carrying its sub-categories and their products.

        A category has no row of its own -- it is a materialized path on the
        product -- so a rename is a prefix rewrite across a set of products.
        Every check runs before any write, and a refusal raises, which the
        session context manager turns into a rollback: a refused rename leaves
        every product exactly as it was (FR-007).

        Args:
            old_path: The category to rename, as displayed. Canonicalized.
            new_path: What it becomes. Canonicalized.

        Returns:
            ``{'from', 'to', 'products', 'categories'}`` -- the canonical forms
            actually applied, the number of rows rewritten, and the number of
            distinct paths rewritten.

        Raises:
            ValidationError: On any refusal, naming the specific obstruction.
        """
        source = category_utils.canonical(old_path)
        target = category_utils.canonical(new_path)

        if source is None:
            raise ValidationError(
                "There is no category to rename -- the current name is blank.",
                field='category_path', value=old_path
            )
        if target is None:
            raise ValidationError(
                "A rename needs a new name; blank is not a category.",
                field='category_path', value=new_path
            )
        if source == target:
            raise ValidationError(
                f'Nothing to rename: "{old_path}" and "{new_path}" are already the '
                f'same category ("{source}") -- capitalization and spacing do not '
                f'distinguish two categories.',
                field='category_path', value=target
            )
        # Checked after equality purely so the equal case gets the clearer
        # message; self-nesting would otherwise subsume it.
        if category_utils.would_nest_within(target, source):
            raise ValidationError(
                f'"{target}" sits inside "{source}", so the rename would put the '
                f'category inside itself.',
                field='category_path', value=target
            )

        with self._session() as session:
            in_source = self._subtree_clause(source)

            # Rows the *database* puts in the source subtree. Its collation folds
            # case and accents (utf8mb4_unicode_ci resolves to ...uca1400_ai_ci on
            # MariaDB 11), so this can sweep in paths that are a different
            # category to us: "café" is not "cafe", however the server compares
            # them. Everything downstream works from the Python-side split.
            candidates = session.query(Product).filter(in_source).all()
            products = [
                product for product in candidates
                if category_utils.is_descendant(product.category_path, source)
            ]
            folded = [
                product for product in candidates
                if not category_utils.is_descendant(product.category_path, source)
            ]

            # A collision is a category at or under the target that is not part
            # of the subtree being moved. The exclusion is load-bearing:
            # renaming "a" to "b" when "a/b" exists must succeed, because "a/b"
            # is coming along and becomes "b/b".
            collision = session.query(Product.category_path).filter(
                self._subtree_clause(target),
                ~in_source,
            ).first()
            collision_path = collision[0] if collision is not None else None

            # The query above cannot see a folded row: `~in_source` excluded it,
            # because the database thinks it *is* the source. Renaming onto one
            # would merge two genuinely distinct categories, which FR-004 refuses.
            if collision_path is None:
                for product in folded:
                    if category_utils.is_descendant(product.category_path, target):
                        collision_path = product.category_path
                        break

            if collision_path is not None:
                raise ValidationError(
                    f'"{collision_path}" already exists. Renaming does not merge '
                    f'categories, so this rename is refused (FR-004).',
                    field='category_path', value=target
                )

            # The deepest descendant is the one at risk when a short parent gets
            # a long new name, and it is not the row the operator is looking at
            # -- so the limit is checked across the subtree, not at the renamed
            # level. Over-length is a rejection, never a truncation.
            rewritten = []
            for product in products:
                candidate = category_utils.rename_descendant(
                    product.category_path, source, target
                )
                if len(candidate) > MAX_CATEGORY_PATH_LENGTH:
                    raise ValidationError(
                        f'"{candidate}" would be longer than '
                        f'{MAX_CATEGORY_PATH_LENGTH} characters.',
                        field='category_path', value=candidate
                    )
                rewritten.append((product, candidate))

            if not products:
                raise ValidationError(
                    f'There is no category "{source}" to rename.',
                    field='category_path', value=source
                )

            distinct_paths = {product.category_path for product, _ in rewritten}
            for product, candidate in rewritten:
                product.category_path = candidate

            report = {
                'from': source,
                'to': target,
                'products': len(rewritten),
                'categories': len(distinct_paths),
            }

        logger.info(
            f"Renamed category {source!r} to {target!r}: "
            f"{report['products']} products across {report['categories']} categories"
        )
        return report

    def rename_tag(self, old_name: str, new_name: str) -> Dict[str, Any]:
        """Rename a tag, merging into the target when the target already exists.

        Args:
            old_name: The tag to rename. Trimmed and lowercased, as
                ``_attach_tag`` already does.
            new_name: What it becomes, or the tag to merge into.

        Returns:
            ``{'from', 'to', 'merged', 'products'}``. ``products`` counts the
            products that gained the survivor because of this call, which for a
            merge excludes those that already carried both.

        Raises:
            ValidationError: On any refusal.
        """
        source = (_clean(old_name) or '').lower()
        target = (_clean(new_name) or '').lower()

        if not source:
            raise ValidationError(
                "There is no tag to rename -- the current name is blank.",
                field='tag', value=old_name
            )
        if not target:
            raise ValidationError(
                "A rename needs a new name; a tag cannot be blank.",
                field='tag', value=new_name
            )
        if source == target:
            raise ValidationError(
                f'Nothing to rename: tags are stored lowercase, so "{old_name}" and '
                f'"{new_name}" are already the same tag ("{source}").',
                field='tag', value=target
            )
        if len(target) > MAX_TAG_LENGTH:
            raise ValidationError(
                f"Tag is longer than {MAX_TAG_LENGTH} characters",
                field='tag', value=target
            )

        with self._session() as session:
            # Load each product's own tags alongside the source's products: the
            # merge branch asks every one of them whether it already carries the
            # survivor, and Product.tags is lazy, so without this the membership
            # check costs a SELECT per product.
            tag = session.query(Tag).options(
                selectinload(Tag.products).selectinload(Product.tags)
            ).filter(Tag.name == source).first()
            if tag is None:
                raise ValidationError(
                    f'There is no tag "{source}" to rename.',
                    field='tag', value=source
                )

            # The stored name can differ from what was typed: the lookup above
            # matched under the database's collation, which folds case *and*
            # accents (utf8mb4_unicode_ci resolves to ...uca1400_ai_ci on
            # MariaDB 11). Compare the stored name to decide "nothing to do",
            # because "würth" -> "wurth" is a real rename that Python sees and
            # SQL does not.
            if tag.name == target:
                raise ValidationError(
                    f'Nothing to rename: the tag is already "{target}".',
                    field='tag', value=target
                )

            survivor = session.query(Tag).options(
                selectinload(Tag.products)
            ).filter(Tag.name == target).first()

            # Same folding, one step further: a lookup for "wurth" comes back
            # with the "würth" row itself. That is not a second tag to merge
            # into -- treating it as one would move nothing and then delete the
            # only row, taking every association with it.
            if survivor is not None and survivor.id == tag.id:
                survivor = None

            if survivor is None:
                # A free name: the associations are already right, only the
                # label is wrong.
                moved = len(tag.products)
                tag.name = target
                merged = False
            else:
                # product_tags' composite primary key makes a duplicate
                # association impossible, but inserting one raises rather than
                # succeeding -- so a product already carrying both has to be
                # skipped, which is the no-op FR-010 requires. Deleting the
                # source takes its remaining associations with it via cascade.
                moved = 0
                for product in list(tag.products):
                    if survivor not in product.tags:
                        product.tags.append(survivor)
                        moved += 1
                session.delete(tag)
                merged = True

        logger.info(
            f"{'Merged' if merged else 'Renamed'} tag {source!r} "
            f"{'into' if merged else 'to'} {target!r}: {moved} products"
        )
        return {'from': source, 'to': target, 'merged': merged, 'products': moved}

    def tag_list_with_counts(self) -> List[Dict[str, Any]]:
        """Every tag with how many products carry it, for the tags page.

        Args:
            None.

        Returns:
            ``[{'id', 'name', 'count'}]``, alphabetically by name. A tag carried
            by nothing is included with a count of 0 -- an orphaned tag is
            exactly the debris the page exists to reveal.
        """
        with self._session() as session:
            rows = (
                session.query(Tag.id, Tag.name, func.count(ProductTag.product_id))
                .outerjoin(ProductTag, ProductTag.tag_id == Tag.id)
                .group_by(Tag.id, Tag.name)
                .order_by(Tag.name)
                .all()
            )

        return [
            {'id': tag_id, 'name': name, 'count': count}
            for tag_id, name, count in rows
        ]

    def _attach_tag(self, session, product: Product, name: str) -> Optional[Tag]:
        """Attach a tag to a product, creating the tag if it is new."""
        cleaned = _clean(name)
        if not cleaned:
            return None

        normalized = cleaned.lower()
        if len(normalized) > MAX_TAG_LENGTH:
            raise ValidationError(
                f"Tag is longer than {MAX_TAG_LENGTH} characters",
                field='tag', value=normalized
            )

        tag = session.query(Tag).filter(Tag.name == normalized).first()
        if tag is None:
            tag = Tag(name=normalized)
            session.add(tag)
            session.flush()

        if tag not in product.tags:
            product.tags.append(tag)

        return tag

    # -- Validation --------------------------------------------------------

    def _validate_description(self, description: Any) -> str:
        """A product with no description cannot be identified, which is the point"""
        if not isinstance(description, str) or not description.strip():
            raise ValidationError("Description is required", field='description')

        cleaned = description.strip()
        if len(cleaned) > MAX_DESCRIPTION_LENGTH:
            raise ValidationError(
                f"Description is longer than {MAX_DESCRIPTION_LENGTH} characters",
                field='description'
            )
        return cleaned

    def _validate_specifications(
        self, entries: Optional[List[Dict[str, str]]]
    ) -> List[Dict[str, str]]:
        """The one definition of a valid specification list (FR-004..FR-009).

        Called by both ``create_product`` and ``update_product`` so the two
        cannot drift.

        Args:
            entries: The submitted list of ``{'name', 'value'}`` dicts, or None.

        Returns:
            The surviving entries, trimmed, in the order given. The caller
            assigns ``display_order`` from the index, so a dropped blank row
            leaves no gap.

        Raises:
            ValidationError: For a half-filled entry, an over-long name, or a
                duplicate name within the submitted list.
        """
        if entries is None:
            entries = []
        # A str is iterable, so without this the old contract -- specifications
        # as one block of text -- would be walked character by character and
        # crash on the first one. POST /api/products passes whatever a client
        # sends straight through, and that client has no way to know the shape
        # changed, so it has to be refused as a ValidationError (a 400) rather
        # than an AttributeError (a 500).
        if isinstance(entries, (str, bytes)) or not isinstance(entries, (list, tuple)):
            raise ValidationError(
                "Specifications must be a list of {name, value} entries",
                field='specifications', value=str(entries)[:100]
            )

        surviving: List[Dict[str, str]] = []
        seen: Dict[str, str] = {}

        for entry in entries:
            if not isinstance(entry, dict):
                raise ValidationError(
                    "Each specification must be an object with a name and a "
                    f"value; got {type(entry).__name__}",
                    field='specifications', value=str(entry)[:100]
                )

            name = _clean(entry.get('name')) or ''
            value = _clean(entry.get('value')) or ''

            if not name and not value:
                # An untouched row on the form is not an error (FR-009).
                continue

            if not name:
                raise ValidationError(
                    f'Specification value "{value}" has no name.',
                    field='specifications', value=value
                )
            if not value:
                raise ValidationError(
                    f'Specification "{name}" has no value.',
                    field='specifications', value=name
                )
            if len(name) > MAX_SPECIFICATION_NAME_LENGTH:
                raise ValidationError(
                    f"Specification name is longer than "
                    f"{MAX_SPECIFICATION_NAME_LENGTH} characters",
                    field='specifications', value=name
                )

            # Compared in Python, never in SQL: the deployed collation also folds
            # accents and would call "Volt" and "Vôlt" one name, where FR-004
            # speaks only of case and whitespace.
            key = name.lower()
            if key in seen:
                raise ValidationError(
                    f'Specification "{name}" is recorded twice -- '
                    f'"{seen[key]}" is already used on this product.',
                    field='specifications', value=name
                )
            seen[key] = name

            surviving.append({'name': name, 'value': value})

        return surviving

    def _validate_category_path(self, category_path: Any) -> Optional[str]:
        """Normalize a category path; over-length is a rejection, not a truncation"""
        normalized = category_utils.canonical(category_path)
        if normalized is not None and len(normalized) > MAX_CATEGORY_PATH_LENGTH:
            raise ValidationError(
                f"Category path is longer than {MAX_CATEGORY_PATH_LENGTH} characters",
                field='category_path', value=normalized
            )
        return normalized

    def _validate_quantity(self, quantity: Any) -> Optional[int]:
        """None means not tracked, which is the default and not an error"""
        if quantity is None or quantity == '':
            return None

        try:
            value = int(quantity)
        except (TypeError, ValueError):
            raise ValidationError(
                f"Quantity must be a whole number: {quantity!r}", field='quantity'
            )

        if value < 0:
            raise ValidationError("Quantity cannot be negative", field='quantity')
        return value

    def _validate_reorder_threshold(
        self, threshold: Any, quantity: Optional[int]
    ) -> Optional[int]:
        """A threshold with nothing to compare against is meaningless (FR-026)"""
        if threshold is None or threshold == '':
            return None

        try:
            value = int(threshold)
        except (TypeError, ValueError):
            raise ValidationError(
                f"Reorder threshold must be a whole number: {threshold!r}",
                field='reorder_threshold'
            )

        if value < 0:
            raise ValidationError("Reorder threshold cannot be negative", field='reorder_threshold')
        if quantity is None:
            raise ValidationError(
                "A reorder threshold only means something for a product whose "
                "quantity is tracked",
                field='reorder_threshold'
            )
        return value

    def _validate_identifier_type(self, id_type: Any) -> IdentifierType:
        """Map a string onto the enum, or say what the valid values are"""
        if isinstance(id_type, IdentifierType):
            return id_type
        try:
            return IdentifierType(str(id_type).upper())
        except ValueError:
            valid = ', '.join(t.value for t in IdentifierType)
            raise ValidationError(
                f"Unknown identifier type {id_type!r}. Valid types: {valid}",
                field='id_type', value=str(id_type)
            )


def _parse_datetime(value: Any, field: str) -> Optional[datetime]:
    """Accept a datetime, an ISO string or a date input's YYYY-MM-DD."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise ValidationError(f"Not a date: {value!r}", field=field)


def _clean(value: Any) -> Optional[str]:
    """Strip a free-text field, turning blank into None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: Any) -> Optional[int]:
    """Read an id off a form field, treating anything unreadable as absent.

    A decision field carries an id the page itself put there. If it comes back
    as something else, the safe reading is that no decision was made -- which
    re-asks the question rather than acting on a value nobody chose.
    """
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fold(value: Optional[str]) -> str:
    """Case-fold and trim, for comparisons that must mean one thing everywhere."""
    return (value or '').strip().casefold()


def _is_barcode_row_name(name: Optional[str]) -> bool:
    """Whether a specification row's name means "this value is a barcode".

    016 FR-001: case and whitespace are folded, so ``upc``, ``UPC `` and ``Upc``
    are one name. The comparison is against the **whole** folded name and not a
    substring: ``Manufacturer UPC`` and ``UPC Code`` are not ``UPC`` rows. A
    feature that promised six names should promote six names, and this runs with
    nobody watching.

    The fold itself lives in ``models.normalized_row_name``, shared with 019's
    part-number names so the two lists cannot drift apart.
    """
    return normalized_row_name(name) in BARCODE_ROW_NAMES


def _corroborates(product: Product, manufacturer: Any, part_number: Any) -> bool:
    """Whether a capture's own evidence agrees with the product it matched.

    Both values are required (FR-019). A manufacturer name matches across a
    vendor's entire catalog and a bare part number collides between
    manufacturers, so only the pair is evidence. A matched product carrying no
    manufacturer can never corroborate, which falls out: a truthy manufacturer
    cannot fold to the empty string.

    **Compared in Python, deliberately.** This is the one comparison in capture
    that acts without asking the operator, and the deployed collation folds
    accents where SQLite folds nothing -- so as a WHERE clause it would mean two
    different things to the two test suites, and the suite that could not see the
    difference is the one that runs on every commit. Case folding only: `Wurth`
    and `Wuerth` are not reliably one manufacturer.
    """
    made_by = _clean(manufacturer)
    number = _clean(part_number)
    if not made_by or not number:
        return False

    return (
        _fold(made_by) == _fold(product.manufacturer)
        and _fold(number) == _fold(product.manufacturer_part_number)
    )


def _dedupe_fold_case(values: Any) -> List[str]:
    """Sort case-insensitively, keeping one spelling of each folded value.

    Done here rather than with ``SELECT DISTINCT`` because DISTINCT folds under
    the deployed collation and does not under SQLite, so the two backends would
    disagree about whether ``Voltage`` and ``voltage`` are one suggestion or two.
    ``VocabularyService._rank_and_dedupe`` deduplicates in Python for the same
    reason. The first spelling in sort order wins.
    """
    kept: Dict[str, str] = {}
    for value in sorted(values, key=lambda v: (v.lower(), v)):
        kept.setdefault(value.lower(), value)
    return list(kept.values())




# -- The order-capture vendors (feature 029) --------------------------------
#
# What differs between one vendor's order capture and another's, as measured in
# 029 research.md §9 rather than anticipated. The shape lives in
# app/services/order_vendors.py; the behaviour lives here, because every one of
# these needs the service's leaf helpers and moving those would drag half the
# service with them.
#
# Registered at import time. `tests/unit/test_order_vendors.py` asserts that the
# two differ only where the vendors genuinely differ.


def _digikey_order_purchases(service, session, order):
    """Every purchase already recorded against this sales order."""
    cleaned = (order.sales_order_number or '').strip()
    if not cleaned:
        return []
    return (
        session.query(Purchase)
        .filter(
            Purchase.vendor == DIGIKEY_VENDOR,
            Purchase.supplier_order_reference == cleaned,
        )
        .order_by(Purchase.id)
        .all()
    )


def _digikey_order_fields(order) -> Dict[str, Any]:
    """The Purchase fields a DigiKey *order* supplies."""
    return {
        'supplier_order_reference': order.sales_order_number,
        'order_reference': order.purchase_order or None,
    }


def _digikey_line_fields(service, line, decision) -> Dict[str, Any]:
    """The Purchase fields a DigiKey *line* supplies.

    ``decision`` is unused: DigiKey's review offers no quantity or price
    override, because the fetched order is the authority and can be re-read.
    """
    return {
        'vendor_item_id': line.digikey_part_number,
        # DigiKey's own words, kept as an Amazon listing title is.
        'listing_title': line.description or None,
        'order_line_number': line.line_number,
        'quantity': line.quantity,
        # Through _validate_price so a DigiKey sub-cent quote is rounded
        # deliberately rather than by the column.
        'unit_price': service._validate_price(line.unit_price),
    }


def _digikey_find_product(service, session, line):
    """A DigiKey line's product: by DigiKey part number, then by MPN."""
    product = service._digikey_product_by_identifier(
        session, IdentifierType.DISTRIBUTOR, line.digikey_part_number,
        vendor=DIGIKEY_VENDOR,
    )
    if product is not None:
        # Found by DigiKey's own number, so a contradicting MPN means the
        # number has been recycled for a different part.
        return product, True

    if line.manufacturer_part_number:
        product = service._digikey_product_by_identifier(
            session, IdentifierType.MPN, line.manufacturer_part_number,
        )
        if product is not None:
            # Found *by* the manufacturer part number, which therefore cannot
            # contradict it.
            return product, False

    return None, False


def _digikey_suggested_description(line, part) -> str:
    """DigiKey's part detail if the lookup answered, else the order line's."""
    return (part.description if part else '') or line.description or ''


def _digikey_incomplete_label(line, part) -> Optional[str]:
    """Names a line DigiKey's part lookup would not answer for (024 FR-041)."""
    return line.digikey_part_number if part is None else None


def _mcmaster_order_fields(order) -> Dict[str, Any]:
    """The Purchase fields a McMaster *order* supplies."""
    return {
        # McMaster shows no order number; this is the customer's Purchase Order
        # string, the only order identifier on the page (028 research.md §5).
        'supplier_order_reference': order.order_number,
        # The stable id out of the order's URL. Never displayed -- it is what
        # lets a re-capture still recognize this order after the Purchase Order
        # string has been renamed.
        'vendor_order_id': order.order_id or None,
        'listing_url': order.source_url or None,
    }


def _mcmaster_line_fields(service, line, decision) -> Dict[str, Any]:
    """The Purchase fields a McMaster *line* supplies.

    Unlike DigiKey's, these consult the decision: the page cannot be re-read, so
    the operator is allowed to overrule the computed quantity and unit price
    (028 FR-020a).
    """
    return {
        'vendor_item_id': line.part_number or None,
        # McMaster's own wording, kept distinct from the operator's product
        # description (028 FR-023).
        'listing_title': line.description or None,
        'order_line_number': line.line_number,
        'quantity': service._mcmaster_quantity(line, decision),
        'unit_price': service._mcmaster_unit_price(line, decision),
    }


def _mcmaster_find_product(service, session, line):
    """A McMaster line's product: by McMaster part number, then by MPN.

    The same two stages DigiKey uses. The second almost never fires -- McMaster
    states no manufacturer part number on the great majority of its goods, so
    ``line.manufacturer_part_number`` is usually '' -- but it is there, and
    dropping it in the consolidation would have been a silent behaviour change.
    """
    product = service._mcmaster_product_by_part_number(session, line.part_number)
    if product is not None:
        return product, True

    if line.manufacturer_part_number:
        product = service._mcmaster_product_by_identifier(
            session, IdentifierType.MPN, line.manufacturer_part_number,
        )
        if product is not None:
            return product, False

    return None, False


def _mcmaster_suggested_description(line, part) -> str:
    """The page's description. ``part`` is always None -- McMaster has no lookup."""
    return line.description or ''


def _mcmaster_incomplete_label(line, part) -> Optional[str]:
    """Names a line the *page* did not fully give up (028 FR-037)."""
    if not line.missing_fields:
        return None
    return line.description or line.part_number or line.form_key


DIGIKEY_ORDER_VENDOR = order_vendors.register(order_vendors.OrderVendor(
    name=DIGIKEY_VENDOR,
    item_id_of=lambda line: line.digikey_part_number,
    order_purchases=_digikey_order_purchases,
    order_fields=_digikey_order_fields,
    line_fields=_digikey_line_fields,
    find_product=_digikey_find_product,
    create_product=lambda service, session, line, part, decision, claim_distributor=True: (
        service._create_digikey_product(
            session, line, part, decision, claim_distributor=claim_distributor
        )
    ),
    suggested_description=_digikey_suggested_description,
    # A DigiKey bag label names its sales order *and* its part, so every
    # candidate a scan turns up is a line of one order -- and that order's
    # screen shows them all.
    receive_landing=order_vendors.LANDING_ORDER_SCREEN,
    enrich=lambda service, client, lines: {
        line.digikey_part_number: service._digikey_part(
            client, line.digikey_part_number
        )
        for line in lines
    },
    incomplete_label=_digikey_incomplete_label,
    enrich_product=lambda service, session, product, part: (
        service._enrich_digikey_product(session, product, part)
    ),
    review_columns=('shipped', 'backorder'),
    confirm_endpoint='product.digikey_order_confirm',
))


MCMASTER_ORDER_VENDOR = order_vendors.register(order_vendors.OrderVendor(
    name=MCMASTER_VENDOR,
    item_id_of=lambda line: line.part_number,
    order_purchases=lambda service, session, order: (
        service._mcmaster_order_purchases(session, order)
    ),
    order_fields=_mcmaster_order_fields,
    line_fields=_mcmaster_line_fields,
    find_product=_mcmaster_find_product,
    create_product=lambda service, session, line, part, decision, claim_distributor=True: (
        service._create_mcmaster_product(
            session, line, decision, claim_distributor=claim_distributor
        )
    ),
    suggested_description=_mcmaster_suggested_description,
    # A McMaster bag names only the part, and the same part can be outstanding
    # on two orders placed weeks apart -- so no single order screen shows the
    # candidates and the operator has to choose.
    receive_landing=order_vendors.LANDING_CHOICE_PAGE,
    incomplete_label=_mcmaster_incomplete_label,
    review_columns=('packs', 'pack_size', 'pack_price'),
    confirm_endpoint='product.mcmaster_order_confirm',
    carries_payload=True,
    # The order "number" is the customer's editable Purchase Order string.
    adopts_renames=True,
))


def _amazon_order_purchases(service, session, order):
    """Every purchase already recorded against this Amazon order.

    One pass, unlike McMaster's two: an Amazon order number is stable and printed
    on the page, so there is no renamed-order problem and ``vendor_order_id``
    stays NULL.
    """
    cleaned = (order.order_number or '').strip()
    if not cleaned:
        return []
    return (
        session.query(Purchase)
        .filter(
            Purchase.vendor == AMAZON_VENDOR,
            Purchase.supplier_order_reference == cleaned,
        )
        .order_by(Purchase.id)
        .all()
    )


def _amazon_order_fields(order) -> Dict[str, Any]:
    """The Purchase fields an Amazon *order* supplies."""
    return {
        'supplier_order_reference': order.order_number,
        'listing_url': order.source_url or None,
    }


def _amazon_line_fields(service, line, decision) -> Dict[str, Any]:
    """The Purchase fields an Amazon *line* supplies.

    Consults the decision, as McMaster's does and DigiKey's does not: the page
    cannot be re-read, so the operator is allowed to overrule what was read.
    """
    return {
        'vendor_item_id': line.asin or None,
        # Amazon's own words, kept distinct from the operator's product
        # description.
        'listing_title': line.title or None,
        'order_line_number': line.line_number,
        'quantity': service._mcmaster_quantity(line, decision),
        'unit_price': service._mcmaster_unit_price(line, decision),
    }


def _amazon_find_product(service, session, line):
    """An Amazon line's product: by ASIN, scoped to Amazon.

    One stage, not two. Amazon states no manufacturer part number on an order
    page, so there is no MPN fallback to make -- unlike both other vendors.
    """
    product = service._amazon_product_by_asin(session, line.asin)
    return (product, True) if product is not None else (None, False)


def _amazon_suggested_description(line, part) -> str:
    """Amazon's title. ``part`` is always None -- there is no lookup."""
    return line.title or ''


def _amazon_incomplete_label(line, part) -> Optional[str]:
    """Names a line the *page* did not fully give up (FR-022)."""
    if not line.missing_fields:
        return None
    return line.title or line.asin or line.form_key


AMAZON_ORDER_VENDOR = order_vendors.register(order_vendors.OrderVendor(
    name=AMAZON_VENDOR,
    item_id_of=lambda line: line.asin,
    order_purchases=_amazon_order_purchases,
    order_fields=_amazon_order_fields,
    line_fields=_amazon_line_fields,
    find_product=_amazon_find_product,
    create_product=lambda service, session, line, part, decision, claim_distributor=True: (
        service._create_amazon_product(
            session, line, decision, claim_distributor=claim_distributor
        )
    ),
    suggested_description=_amazon_suggested_description,
    # An Amazon package names neither the order nor the line, and a product
    # created from an order line carries no barcode -- so a scan only ever
    # reaches a line through the product's own barcode, and that can name lines
    # on more than one order. The operator chooses.
    receive_landing=order_vendors.LANDING_CHOICE_PAGE,
    incomplete_label=_amazon_incomplete_label,
    # Neither shipped/backorder counts nor pack arithmetic: the order page states
    # a unit price and a quantity directly.
    review_columns=(),
    confirm_endpoint='product.amazon_order_confirm',
    carries_payload=True,
))
