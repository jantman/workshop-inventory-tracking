"""
The e2e suite's isolation guarantee, asserted rather than assumed.

`E2ETestServer.clear_test_data()` is what every other e2e module depends on for
a clean starting state, and it is the one piece of shared machinery no other
test can fail on: the catalog-facing modules assert only positively
(containment), so rows left behind by a broken clear go unnoticed and the whole
suite passes green on stale data. This module is the exception — it seeds a row
in every table `clear_test_data()` is responsible for, clears, and asserts that
nothing survived.

It also pins the delete ORDER. `attachments` references both `products` and
`purchases`; `product_tags`, `product_identifiers` and `purchases` reference
`products`; `item_photo_associations` references `photos`. Getting that wrong
raises under MariaDB's real FK constraints (and not under SQLite, where the unit
suite runs), so this test only means anything against the e2e database — which
is where it lives.

Every table is seeded before the clear that is supposed to empty it. An
assertion that a table is empty after clearing a database that never held a row
in it passes whether or not the delete is there at all, which is the same
"green on stale data" failure this module exists to rule out.
"""

import uuid

import pytest
from sqlalchemy.orm import sessionmaker

from app.database import (Attachment, InventoryItem, ItemPhotoAssociation,
                          MaterialTaxonomy, Photo, Product, ProductIdentifier,
                          ProductTag, Purchase)


CATALOG_MODELS = (Product, Purchase, Attachment, ProductIdentifier, ProductTag)

# The tables `clear_test_data()` handled before the catalog deletes were added.
INVENTORY_MODELS = (InventoryItem, Photo, ItemPhotoAssociation)


def _seed_catalog(session):
    """One row in every catalog table, wired together so the FKs are real.

    A product with no children would pass a delete written in any order, which
    is the mistake this test exists to catch.
    """
    product = Product(internal_id=f'CLR{uuid.uuid4().hex[:8].upper()}',
                      description='clear_test_data probe')
    session.add(product)
    session.flush()  # assigns product.id for the children below

    purchase = Purchase(product_id=product.id, vendor='Probe Vendor', quantity=1)
    session.add(purchase)
    session.flush()

    session.add(ProductIdentifier(product_id=product.id,
                                  identifier_type='GTIN',
                                  value=f'{uuid.uuid4().int % 10 ** 13:013d}',
                                  vendor_scope=''))
    session.add(ProductTag(product_id=product.id, tag='probe'))
    # Attachments are the reason order matters twice over — they reference
    # products AND purchases. It takes two rows to exercise both edges:
    # `ck_attachment_one_owner` is an XOR, so a single attachment can carry
    # only one of the two FKs and leaves the other edge untested.
    session.add(Attachment(purchase_id=purchase.id,
                           filename='probe-purchase.txt',
                           content_type='text/plain',
                           file_size=5,
                           content=b'probe'))
    session.add(Attachment(product_id=product.id,
                           filename='probe-product.txt',
                           content_type='text/plain',
                           file_size=5,
                           content=b'probe'))
    session.commit()


def _seed_inventory_side(session):
    """One row in each table the clear handled before this sweep touched it.

    `item_photo_associations` points at `photos`, so these pin an ordering
    constraint of their own.
    """
    ja_id = f'JA{uuid.uuid4().int % 10 ** 6:06d}'  # ck_valid_ja_id_format
    session.add(InventoryItem(ja_id=ja_id, item_type='Bar', material='Steel'))

    photo = Photo(filename='probe.jpg',
                  content_type='image/jpeg',  # ck_photo_valid_content_type
                  file_size=5,
                  thumbnail_data=b'probe',
                  medium_data=b'probe',
                  original_data=b'probe')
    session.add(photo)
    session.flush()  # assigns photo.id for the association below

    session.add(ItemPhotoAssociation(ja_id=ja_id, photo_id=photo.id))
    session.commit()


def _counts(engine, models):
    session = sessionmaker(bind=engine)()
    try:
        return {model.__tablename__: session.query(model).count()
                for model in models}
    finally:
        session.close()


@pytest.mark.e2e
def test_clear_test_data_removes_every_catalog_row(live_server):
    """Given a product carrying a purchase, two attachments, an identifier and a
    tag, when `clear_test_data()` runs, then every one of those tables is empty
    and no IntegrityError was raised."""
    session = sessionmaker(bind=live_server.engine)()
    try:
        _seed_catalog(session)
    finally:
        session.close()

    seeded = _counts(live_server.engine, CATALOG_MODELS)
    assert all(count > 0 for count in seeded.values()), \
        f'the probe rows did not land ({seeded}), so the clear would prove nothing'

    live_server.clear_test_data()  # raises if the FK order is wrong

    assert _counts(live_server.engine, CATALOG_MODELS) == \
        {model.__tablename__: 0 for model in CATALOG_MODELS}


@pytest.mark.e2e
def test_clear_test_data_still_clears_the_inventory_side_and_reseeds_materials(
        live_server):
    """The catalog deletes were added to an existing method; what it already
    did must survive. The material taxonomy is re-seeded afterwards, so it is
    the one table expected NON-empty."""
    session = sessionmaker(bind=live_server.engine)()
    try:
        _seed_inventory_side(session)
    finally:
        session.close()

    seeded = _counts(live_server.engine, INVENTORY_MODELS)
    assert all(count > 0 for count in seeded.values()), \
        f'the probe rows did not land ({seeded}), so the clear would prove nothing'

    live_server.clear_test_data()

    assert _counts(live_server.engine, INVENTORY_MODELS) == \
        {model.__tablename__: 0 for model in INVENTORY_MODELS}

    session = sessionmaker(bind=live_server.engine)()
    try:
        assert session.query(MaterialTaxonomy).count() > 0
    finally:
        session.close()


@pytest.mark.e2e
def test_clear_test_data_is_safe_on_an_already_empty_catalog(live_server):
    """`live_server` cleared on the way in, so the call below runs against a
    database this test has written nothing to: the empty-input case. It must
    commit cleanly rather than raise on zero rows."""
    live_server.clear_test_data()

    assert _counts(live_server.engine, CATALOG_MODELS + INVENTORY_MODELS) == \
        {model.__tablename__: 0
         for model in CATALOG_MODELS + INVENTORY_MODELS}
