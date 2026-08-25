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

from sqlalchemy import and_, create_engine, func, or_
from sqlalchemy.orm import selectinload, sessionmaker

from .database import (
    Product,
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
from .models import (
    CaptureAssessment,
    price_to_cents,
    CapturedBarcode,
    DigiKeyCaptureResult,
    DigiKeyOrder,
    IdentifierType,
    ListingCapture,
    OrderCaptureReview,
    OrderLineState,
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

            return query.first()

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


    # -- DigiKey orders ----------------------------------------------------
    #
    # An order is not stored. It *is* the purchases carrying its sales order
    # number, the way the reorder list is derived rather than kept. What lives
    # here is the pair the capture flow needs: a read that decides and writes
    # nothing, and a write that does the whole order or none of it.

    def review_digikey_order(
        self,
        order: DigiKeyOrder,
        digikey_client=None,
    ) -> OrderCaptureReview:
        """Decide what capturing this order would do, without doing any of it.

        **Writes nothing** (FR-004). An operator who closes the tab leaves no
        product, no purchase and no trace -- there was never a record, only a
        page.

        Args:
            order: What DigiKey said, already parsed.
            digikey_client: Used to enrich each line with the part detail an
                order line does not carry (FR-040). None means no enrichment,
                which is an ordinary state and not an error.

        Returns:
            An OrderCaptureReview: one ReviewedLine per line of the order, plus
            any purchase recorded against this sales order whose part the order
            no longer contains (FR-013).
        """
        # Enrichment happens **before** the session opens, for the reason
        # capture_digikey_order gives: this is network I/O at ten seconds a call,
        # and holding a transaction open across twenty-five of them is a
        # long-lived lock in exchange for nothing.
        #
        # The exposure here is worse than capture's, not better -- a review
        # enriches every line, where a capture enriches only the included ones.
        # This read used to sit inside the session, which contradicted the
        # comment on its sibling forty lines below. PR #116 review.
        parts = {
            line.digikey_part_number: self._digikey_part(
                digikey_client, line.digikey_part_number
            )
            for line in order.lines
        }

        with self._session() as session:
            recorded = self._recorded_digikey_lines(session, order)

            reviewed = [
                self._review_digikey_line(
                    session, line, parts.get(line.digikey_part_number), recorded
                )
                for line in order.lines
            ]
            orphaned = self._orphaned_digikey_purchases(session, order, recorded)

        return OrderCaptureReview(
            order=order,
            lines=tuple(reviewed),
            orphaned=orphaned,
        )

    def capture_digikey_order(
        self,
        order: DigiKeyOrder,
        decisions: Dict[str, Dict[str, Any]],
        digikey_client=None,
    ) -> DigiKeyCaptureResult:
        """Record a reviewed order: one outstanding purchase per included line.

        **The whole order writes in one session, or none of it does** (FR-039).
        That is the reason this lives on CatalogService rather than in a service
        of its own: every method here opens its own session, so building a
        24-line order from outside would be forty-eight transactions and a
        half-written order when line thirteen fails.

        ``capture_order`` is deliberately not called. It encodes Amazon's
        decision model -- a same-day vendor+item duplicate heuristic, a listing
        title fallback, pack pricing, captured-barcode promotion. A sales order
        number is an *exact* idempotency key, so that heuristic is not merely
        unnecessary here, it is wrong: two lines of one order are two purchases
        and it would query one of them.

        Args:
            order: What DigiKey said, re-read at confirmation time -- the fetched
                order is the authority, not the form.
            decisions: Keyed by DigiKey part number. ``include`` absent or false
                excludes the line (FR-007); ``description`` overrides DigiKey's
                (FR-006); ``resolution`` is 'attach' or 'separate' and is
                required on a conflicted line (FR-015); ``apply_change`` applies
                a changed quantity or price to an already-captured line (FR-014).
            digikey_client: For enrichment, as above.

        Returns:
            A DigiKeyCaptureResult describing what happened.

        Raises:
            ValidationError: A conflicted line with no resolution, or a refused
                description. Either way nothing is written.
        """
        # Enrichment happens before the session opens: it is network I/O, and
        # holding a transaction open across twenty-five HTTP calls would be a
        # long-lived lock in exchange for nothing.
        parts = {
            line.digikey_part_number: self._digikey_part(
                digikey_client, line.digikey_part_number
            )
            for line in order.lines
            if (decisions.get(line.form_key) or {}).get('include')
        }

        purchase_ids = []
        products_created = products_attached = 0
        lines_excluded = lines_already_captured = lines_updated = 0

        with self._session() as session:
            recorded = self._recorded_digikey_lines(session, order)

            for line in order.lines:
                decision = decisions.get(line.form_key) or {}

                # **Already captured is a fact about the line, not a decision
                # about it**, so it is settled before the include gate below.
                #
                # The ordering is load-bearing and was wrong once: the review
                # renders no "take this line" checkbox for a line already
                # captured -- there is nothing to decide -- so ``include`` is
                # always false for one. Gating here on ``include`` therefore
                # made the "Update it?" tick-box (FR-014) dead through the form
                # while passing a unit test that built the decision by hand, and
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
                        self._apply_digikey_change(existing, line)
                        lines_updated += 1
                    continue

                if not decision.get('include'):
                    lines_excluded += 1
                    continue

                part = parts.get(line.digikey_part_number)
                reviewed = self._review_digikey_line(session, line, part, recorded)
                product, created = self._digikey_product_for(
                    session, reviewed, line, part, decision
                )
                if created:
                    products_created += 1
                else:
                    products_attached += 1

                purchase = Purchase(
                    product_id=product.id,
                    vendor=DIGIKEY_VENDOR,
                    vendor_item_id=line.digikey_part_number,
                    supplier_order_reference=order.sales_order_number,
                    # Which line, so a re-review pairs them exactly rather than
                    # guessing from the part number. PR #116 review.
                    order_line_number=line.line_number,
                    order_reference=order.purchase_order or None,
                    # DigiKey's own words, kept as an Amazon listing title is.
                    listing_title=line.description or None,
                    order_date=order.order_date or datetime.now(),
                    quantity=line.quantity,
                    # Through _validate_price so a DigiKey sub-cent quote is
                    # rounded deliberately rather than by the column.
                    unit_price=self._validate_price(line.unit_price),
                    # FR-009: outstanding at capture whatever DigiKey says about
                    # shipping. Shipped is their state; received is the
                    # operator's, and only they can say it.
                    received_date=None,
                )
                session.add(purchase)
                session.flush()
                purchase_ids.append(purchase.id)

        result = DigiKeyCaptureResult(
            purchase_ids=tuple(purchase_ids),
            products_created=products_created,
            products_attached=products_attached,
            lines_excluded=lines_excluded,
            lines_already_captured=lines_already_captured,
            lines_updated=lines_updated,
            lines_unenriched=tuple(
                number for number, part in parts.items() if part is None
            ),
        )
        logger.info(
            f"Captured DigiKey order {order.sales_order_number}: "
            f"{len(purchase_ids)} purchase(s), {products_created} product(s) created"
        )
        return result

    def find_order_lines(self, sales_order_number: str) -> List[Purchase]:
        """The purchases that make up one DigiKey order (FR-017).

        This is the whole of "open a captured order": there is no order record
        to load, only the purchases carrying its number.

        Returns:
            The purchases, oldest first, each with its product loaded. Empty for
            a sales order number nothing was captured against -- which the route
            renders as "not captured", never as a 404.
        """
        cleaned = (sales_order_number or '').strip()
        if not cleaned:
            return []

        with self._session() as session:
            return (
                session.query(Purchase)
                .options(selectinload(Purchase.product))
                .filter(
                    Purchase.vendor == DIGIKEY_VENDOR,
                    Purchase.supplier_order_reference == cleaned,
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

    def _recorded_digikey_lines(self, session, order) -> Dict[str, Purchase]:
        """Pair this order's lines to the purchases already recorded for it.

        Returns a mapping of ``line.form_key`` to its Purchase, so a caller can
        ask about a *line* rather than about a part number.

        **A part number does not identify a line**, and this used to pretend it
        did -- first by keeping one purchase per part, then by pairing them
        positionally. Both corrupt data on a duplicated part: capture one of two
        such lines, re-open the order, and the other line claims its purchase,
        reads as captured with the wrong quantity, and applying a change writes
        to the wrong row. The information needed to pair them is not derivable,
        so ``purchases.order_line_number`` stores it. PR #116 review.

        Two passes, and the order matters:

        1. **By line number.** Exact, and the only pass that runs for anything
           this feature captured.
        2. **By part number, for purchases carrying no line number** -- a
           purchase recorded by hand against a sales order, or captured before
           this column existed. Each is claimed once, by the first line that
           wants it, and never by a line that already matched exactly.

        A purchase no line claims is orphaned, which the caller reports (FR-013).
        """
        cleaned = (order.sales_order_number or '').strip()
        if not cleaned:
            return {}

        rows = (
            session.query(Purchase)
            .filter(
                Purchase.vendor == DIGIKEY_VENDOR,
                Purchase.supplier_order_reference == cleaned,
            )
            .order_by(Purchase.id)
            .all()
        )

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
            for row in unclaimed:
                if row.vendor_item_id == line.digikey_part_number:
                    paired[line.form_key] = row
                    claimed.add(id(row))
                    unclaimed.remove(row)
                    break

        return paired

    def _orphaned_digikey_purchases(self, session, order, paired) -> tuple:
        """Purchases recorded against this order that no line of it claims (FR-013)."""
        cleaned = (order.sales_order_number or '').strip()
        if not cleaned:
            return ()

        claimed = {purchase.id for purchase in paired.values()}
        return tuple(
            row.id
            for row in session.query(Purchase)
            .filter(
                Purchase.vendor == DIGIKEY_VENDOR,
                Purchase.supplier_order_reference == cleaned,
            )
            .order_by(Purchase.id)
            .all()
            if row.id not in claimed
        )

    def _review_digikey_line(self, session, line, part, recorded) -> ReviewedLine:
        """Decide one line's state. Reads only.

        The four states are exclusive and tested in this order: already
        captured, then a recycled identifier, then an ordinary match, then new.
        CAPTURED comes first because a line already recorded is not a line to
        decide anything else about.
        """
        suggested = ((part.description if part else '') or line.description or '')[
            :MAX_DESCRIPTION_LENGTH
        ]

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

        product = self._digikey_product_by_identifier(
            session, IdentifierType.DISTRIBUTOR, line.digikey_part_number,
            vendor=DIGIKEY_VENDOR,
        )
        if product is not None:
            # A distributor recycling a part number for a different part is the
            # failure this catches, and it is the most damaging one in the
            # feature because nothing looks wrong afterwards -- the price history
            # of one product quietly becomes the history of two.
            contradicted = (
                line.manufacturer_part_number
                and product.manufacturer_part_number
                and line.manufacturer_part_number != product.manufacturer_part_number
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
            )

        if line.manufacturer_part_number:
            product = self._digikey_product_by_identifier(
                session, IdentifierType.MPN, line.manufacturer_part_number,
            )
            if product is not None:
                return ReviewedLine(
                    line=line,
                    state=OrderLineState.MATCHED,
                    part=part,
                    suggested_description=suggested,
                    product_id=product.id,
                    product_description=product.description,
                    product_manufacturer_part_number=product.manufacturer_part_number,
                )

        return ReviewedLine(
            line=line,
            state=OrderLineState.NEW,
            part=part,
            suggested_description=suggested,
        )

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

    def _digikey_product_for(self, session, reviewed, line, part, decision):
        """The product this line's purchase attaches to, creating one if needed.

        Returns:
            ``(product, created)``.

        Raises:
            ValidationError: A conflicted line with no resolution. Raised inside
                the session, so the whole capture rolls back rather than this
                one line being skipped -- the operator answered a question about
                an order, not about a line, and half an order is worse than none.
        """
        if reviewed.state is OrderLineState.CONFLICT:
            resolution = (decision.get('resolution') or '').strip().lower()
            if resolution not in ('attach', 'separate'):
                raise ValidationError(
                    f"{line.digikey_part_number} already names "
                    f"{reviewed.product_description!r}, whose part number is "
                    f"{reviewed.product_manufacturer_part_number!r} rather than "
                    f"{line.manufacturer_part_number!r}. Say whether to attach to "
                    f"that product or create a separate one.",
                    field=f'resolution[{line.digikey_part_number}]',
                )
            if resolution == 'attach':
                return session.get(Product, reviewed.product_id), False
            # 'separate': a new product, and the existing one is left entirely
            # alone -- including its identifiers. The contested DigiKey part
            # number stays where it is; the new product records it on the
            # purchase instead, via vendor_item_id.
            return self._create_digikey_product(
                session, line, part, decision, claim_distributor=False
            ), True

        if reviewed.state is OrderLineState.MATCHED:
            product = session.get(Product, reviewed.product_id)
            self._enrich_digikey_product(session, product, part)
            return product, False

        return self._create_digikey_product(session, line, part, decision), True

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

    def _apply_digikey_change(self, purchase: Purchase, line) -> None:
        """Bring a recorded purchase into line with what the order now says (FR-014)."""
        if line.quantity is not None:
            purchase.quantity = line.quantity
        if line.unit_price is not None:
            purchase.unit_price = self._validate_price(line.unit_price)

    # -- Scanning ----------------------------------------------------------

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

        # FREE_TEXT. Rule 4 lives here rather than in the classifier: a vendor
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


