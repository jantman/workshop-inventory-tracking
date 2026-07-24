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

from typing import Optional
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from .database import Product
from .mariadb_storage import MariaDBStorage
from .exceptions import ValidationError
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

        This is a read-only query (no commit), so the returned detached ORM
        object's scalar columns stay readable after the session closes. Do not
        access relationship attributes (e.g. .purchases) on the result — that
        would lazy-load on a detached instance (Story 1.4 concern).
        """
        try:
            session = self.Session()
            return session.query(Product).filter(Product.id == product_id).first()
        except Exception as e:
            from .logging_config import log_audit_operation
            log_audit_operation('get_product', 'error', item_id=str(product_id),
                                error_details=str(e), logger_name='mariadb_catalog_service')
            return None
        finally:
            if 'session' in locals():
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
            session.commit()
            new_id = product.id
            log_audit_operation('create_product', 'success', item_id=str(new_id),
                                item_after=product.to_dict(),
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

            session.commit()
            log_audit_operation('update_product', 'success', item_id=str(product_id),
                                item_after=product.to_dict(),
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
