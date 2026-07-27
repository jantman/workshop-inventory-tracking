"""
Fixtures scoped to the unit suite.

Anything here is deliberately NOT visible to `tests/e2e/`: these fixtures read
the per-test SQLite database behind `test_storage`, which is not the database
the e2e Flask server writes to. A fixture like `product_ids` placed in the root
`tests/conftest.py` would be offered to e2e tests as well, where it would
cheerfully report an empty catalog forever.
"""

import pytest
from sqlalchemy.orm import sessionmaker

from app.database import Product


@pytest.fixture
def product_ids(test_storage):
    """Every product id in the catalog, so a "nothing was written" assertion is
    about the product set rather than about autoincrement arithmetic.

    A callable rather than a value because it has to be sampled AFTER the
    request under test runs.

    Bound to `test_storage.engine` directly rather than through
    `CatalogService`. DW-32 removed the `_create_engine()` fallback that used to
    make that indirection actively dangerous — a service could silently end up
    on `Config.SQLALCHEMY_DATABASE_URI` instead of the database the route wrote
    to, against which every `== set()` assertion would pass vacuously. Services
    now always share their storage's engine, but reading the engine straight off
    the fixture keeps that guarantee local and checkable here.
    """
    engine = getattr(test_storage, 'engine', None)
    assert engine is not None, (
        'test_storage has no engine, so product_ids would query the wrong '
        'database and every emptiness assertion would be vacuous')
    Session = sessionmaker(bind=engine)

    def _ids():
        session = Session()
        try:
            return {row[0] for row in session.query(Product.id).all()}
        finally:
            session.close()

    return _ids
