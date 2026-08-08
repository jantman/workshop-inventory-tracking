"""
Product catalogue service.

All business logic for the product catalogue lives here: routes in the ``product``
blueprint stay thin and issue no ORM queries and no raw SQL.

Session handling follows the InventoryService precedent -- take ``storage.engine``
and build a sessionmaker from it -- rather than routing catalogue queries through
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
from .exceptions import DuplicateItemError, ItemNotFoundError, ValidationError
from .mariadb_storage import MariaDBStorage
from .models import (
    IdentifierType,
    ScanClassification,
    ScanKind,
    ScanResolution,
    StockStatus,
)
from .utils import category as category_utils
from .utils import gtin as gtin_utils
from .utils import internal_id as internal_id_utils
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
        """List the catalogue, most recently added first.

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
            query: Matched against description, specifications, manufacturer part
                number and every recorded identifier value (FR-032).
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
        order_date: Optional[datetime] = None,
        received_date: Optional[datetime] = None,
        quantity: Optional[int] = None,
        unit_price: Optional[Any] = None,
        order_reference: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Purchase:
        """Record one acquisition of a product (FR-004, FR-005).

        Args:
            product_id: The product acquired.
            vendor: Who it came from. Required -- provenance is the point.
            vendor_item_id: The vendor's own identifier, if there is one.
            listing_title: The vendor's raw title, if captured at order time.
            order_date: When it was ordered.
            received_date: When it arrived. None means the order is outstanding.
            quantity: How many.
            unit_price: Price per unit, as a Decimal.
            order_reference: Order number.
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
                order_date=order_date,
                received_date=received_date,
                quantity=quantity,
                unit_price=price,
                order_reference=_clean(order_reference),
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
    ) -> Purchase:
        """Capture an order while the vendor's listing is still on screen.

        Creates an *unreceived* purchase (FR-020). It attaches to an existing
        product when the captured identifier already names one, and creates a
        product otherwise (FR-021) -- so a repeat buy joins one history rather
        than spawning a duplicate.

        Idempotent on ``(vendor, vendor_item_id, order_date)``: clicking the
        bookmarklet twice on the same listing captures nothing new, because
        double-clicking a bookmark is a thing people do.

        Args:
            vendor: The vendor, derived from the listing's host.
            vendor_item_id: The vendor's identifier, e.g. an Amazon ASIN.
            listing_title: The page title, as the vendor wrote it.
            url: The listing URL, kept in the notes for later reference.
            unit_price: Price, if the operator supplied one.
            quantity: Quantity, if the operator supplied one.
            order_date: When it was ordered. Defaults to today.

        Returns:
            The Purchase -- newly created, or the one already captured.

        Raises:
            ValidationError: If vendor is missing or a value fails validation.
        """
        vendor_name = _clean(vendor)
        if not vendor_name:
            raise ValidationError("Vendor is required to capture an order", field='vendor')

        item_id = _clean(vendor_item_id)
        title = _clean(listing_title)
        ordered = _parse_datetime(order_date, 'order_date') or datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        price = self._validate_price(unit_price)
        count = self._validate_purchase_quantity(quantity)

        existing = self._find_captured_purchase(vendor_name, item_id, ordered)
        if existing is not None:
            logger.info(
                f"Capture of {vendor_name}/{item_id} on {ordered.date()} already "
                f"recorded as purchase {existing.id}; nothing created"
            )
            return existing

        # FR-021: attach when the identifier already names a product.
        product = None
        if item_id:
            product = self.find_product_by_identifier(
                item_id, id_type=IdentifierType.VENDOR.value, vendor=vendor_name
            )

        if product is None:
            product = self.create_product(
                description=title or f"{vendor_name} item {item_id or 'without an identifier'}",
                notes=f"Captured from {url}" if url else None,
                identifiers=(
                    [{'id_type': IdentifierType.VENDOR.value,
                      'value': item_id, 'vendor': vendor_name}]
                    if item_id else None
                ),
            )

        return self.record_purchase(
            product.id,
            vendor=vendor_name,
            vendor_item_id=item_id,
            listing_title=title,
            order_date=ordered,
            quantity=count,
            unit_price=price,
            notes=url,
        )

    def _find_captured_purchase(
        self, vendor: str, vendor_item_id: Optional[str], order_date: datetime
    ) -> Optional[Purchase]:
        """The idempotency key: same vendor, same item, same day."""
        if not vendor_item_id:
            # Without an identifier there is nothing to be idempotent on -- two
            # captures of two untitled listings are two different purchases.
            return None

        day_start = order_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        with self._session() as session:
            return session.query(Purchase).filter(
                Purchase.vendor == vendor,
                Purchase.vendor_item_id == vendor_item_id,
                Purchase.order_date >= day_start,
                Purchase.order_date < day_end,
            ).first()

    def receive_purchase(
        self,
        purchase_id: int,
        received_date: Optional[datetime] = None,
        quantity: Optional[int] = None,
        unit_price: Optional[Any] = None,
        notes: Optional[str] = None,
    ) -> Purchase:
        """Mark an outstanding purchase received, amending it if reality differed.

        What arrives is allowed to differ from what was ordered, so quantity and
        price can be amended here.

        Receiving also **clears the product's manual low flag** (FR-029). This is
        the asymmetry worth stating: a threshold-derived low clears itself once
        the count changes, but a manually flagged product stays flagged until
        something clears it, and nothing else knows the operator's intent.

        Marking an already-received purchase received again is a no-op, not an
        error.

        Args:
            purchase_id: The purchase that arrived.
            received_date: When. Defaults to now.
            quantity: The quantity actually received, if it differed.
            unit_price: The price actually paid, if it differed.
            notes: Replacement notes, if any.

        Returns:
            The updated Purchase.

        Raises:
            ItemNotFoundError: If the purchase does not exist.
            ValidationError: If an amended value fails validation.
        """
        received = _parse_datetime(received_date, 'received_date') or datetime.now()
        amended_quantity = self._validate_purchase_quantity(quantity)
        amended_price = self._validate_price(unit_price)

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

            if product is not None and not already_received:
                # A tracked count goes up by what arrived, which clears any
                # threshold-derived low on its own.
                if product.quantity is not None and purchase.quantity:
                    product.quantity = product.quantity + purchase.quantity
                    product.quantity_updated_at = datetime.now()

                # The manual flag has to be cleared explicitly -- this is the
                # other half of FR-029, and the half nothing else covers.
                if product.stock_status is not None:
                    logger.info(
                        f"Clearing manual stock flag on product {product.id}: "
                        f"purchase {purchase_id} received"
                    )
                    product.stock_status = None

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
        return value

    def _validate_receipt_order(
        self, order_date: Optional[datetime], received_date: Optional[datetime]
    ) -> None:
        """Nothing arrives before it is ordered"""
        if order_date is not None and received_date is not None and received_date < order_date:
            raise ValidationError(
                "A purchase cannot be received before it was ordered",
                field='received_date'
            )

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

        Three outcomes and no fourth: the scan is a product we hold, an offer to
        create one with what was scanned already attached, or a search carrying
        the raw text. A scan that matches nothing is answered, not refused
        (FR-018, SC-008).

        Args:
            classification: The pure classifier's structural answer.

        Returns:
            A ScanResolution with outcome 'product', 'create' or 'search'.
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
            # catalogue that already has a claim on this value. Callers treat the
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
        """Every specification name in use, for the name datalists (FR-019).

        Args:
            prefix: Optionally narrow to names starting with this,
                case-insensitively.

        Returns:
            The distinct names, sorted case-insensitively.
        """
        with self._session() as session:
            query = session.query(ProductSpecification.name)
            cleaned = _clean(prefix)
            if cleaned:
                query = query.filter(func.lower(ProductSpecification.name).like(
                    f"{_escape_like(cleaned.lower())}%", escape='\\'
                ))
            return _dedupe_fold_case(row[0] for row in query.all())

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

        with self._session() as session:
            query = session.query(ProductSpecification.value).filter(
                func.lower(ProductSpecification.name) == cleaned_name.lower()
            )
            cleaned = _clean(prefix)
            if cleaned:
                query = query.filter(func.lower(ProductSpecification.value).like(
                    f"{_escape_like(cleaned.lower())}%", escape='\\'
                ))
            return _dedupe_fold_case(row[0] for row in query.all())

    # -- Categories --------------------------------------------------------

    def list_categories(self, prefix: Optional[str] = None) -> List[str]:
        """Every category path in use.

        There is no categories table: a category is a string on a product, so
        this is the distinct set of those strings. The consequence, stated
        plainly, is that an empty category cannot exist -- which for this
        workshop is the correct behaviour.

        Args:
            prefix: Optionally narrow to a subtree.

        Returns:
            Distinct category paths, alphabetically.
        """
        with self._session() as session:
            query = session.query(Product.category_path).filter(
                Product.category_path.isnot(None)
            ).distinct()

            ancestor = category_utils.canonical(prefix)
            if ancestor is not None:
                query = query.filter(or_(
                    Product.category_path == ancestor,
                    Product.category_path.like(
                        category_utils.descendant_like_pattern(ancestor), escape='\\'
                    ),
                ))

            return sorted(row[0] for row in query.all())

    def category_tree(self) -> List[Dict[str, Any]]:
        """The categories in use, with how many products sit directly in each.

        Args:
            None.

        Returns:
            One entry per category path: its path, its depth, and its direct
            product count.
        """
        with self._session() as session:
            rows = session.query(
                Product.category_path, func.count(Product.id)
            ).filter(
                Product.category_path.isnot(None)
            ).group_by(Product.category_path).all()

        return [
            {
                'path': path,
                'depth': len(category_utils.segments(path)),
                'name': category_utils.segments(path)[-1],
                'count': count,
            }
            for path, count in sorted(rows)
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


