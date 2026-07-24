"""
MariaDB Catalog Service

Business logic for the product catalog (Products, and — in later epics —
identifiers, scan resolution, search, capture, derived stock signals). All
catalog queries and mutations go through this service (AD-2); routes contain no
ORM/SQL and build the HTTP response themselves.

Story 1.3 introduces the create / read / update surface for Products. Later
stories extend this class (internal_id generation, scan resolution,
search_products, capture, derived signals).
"""

from typing import List, Optional
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from .database import Product, Purchase
from .mariadb_storage import MariaDBStorage
from config import Config


# Product fields the create/update surface accepts (Story 1.3 scope: FR2 minus
# internal_id/stock/equivalence, which arrive in later epics).
_PRODUCT_FIELDS = (
    'manufacturer', 'mpn', 'description', 'notes', 'category_path', 'attributes',
)


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

    def create_product(self, *, manufacturer=None, mpn=None, description=None,
                        notes=None, category_path=None, attributes=None) -> Optional[int]:
        """
        Create a Product and return its new integer id, or None on failure.

        Every field is optional except the caller's own required-field policy
        (the route requires a Label Description); blank strings are coerced to
        NULL. Returns the id (captured before the session closes) rather than
        the ORM object to avoid detached-attribute access downstream.
        """
        from .logging_config import log_audit_operation
        try:
            session = self.Session()
            product = Product(
                manufacturer=_clean(manufacturer),
                mpn=_clean(mpn),
                description=_clean(description),
                notes=_clean(notes),
                category_path=_clean(category_path),
                attributes=attributes,
            )
            session.add(product)
            # Flush (assigns the PK, fires column defaults) and capture the id
            # and audit snapshot BEFORE commit: a post-commit attribute access
            # triggers a refresh SELECT that can fail even though the row was
            # committed, which would falsely report failure and invite a
            # duplicate-creating retry.
            session.flush()
            new_id = product.id
            audit_snapshot = product.to_dict()
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
                setattr(product, key, value if key == 'attributes' else _clean(value))

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
