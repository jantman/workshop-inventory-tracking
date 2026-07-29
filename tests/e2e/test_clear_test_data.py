"""
The e2e suite's isolation guarantee, asserted rather than assumed.

`E2ETestServer.clear_test_data()` is what every other e2e module depends on for
a clean starting state, and it is the one piece of shared machinery no other
test can fail on: the catalog-facing modules assert only positively
(containment), so rows left behind by a broken clear go unnoticed and the whole
suite passes green on stale data. This module is the exception — it seeds a row
in every table `clear_test_data()` is responsible for, clears, and asserts that
nothing survived.

It also pins the delete ORDER. The clear no longer names any table: it walks
`reversed(Base.metadata.sorted_tables)`, which is children-before-parents
because `sorted_tables` is topologically sorted parents-first. The FK web that
order has to satisfy is real — `attachments` references both `products` and
`purchases`; `product_tags`, `product_identifiers` and `purchases` reference
`products`; `item_photo_associations` references `photos` — and it is enforced
only by MariaDB's real FK constraints (not by SQLite, where the unit suite
runs), so this test only means anything against the e2e database, which is
where it lives. Be honest about how much that proves: `start()` builds the
schema with `create_all` from the same metadata the sort reads, so a
topological sort cannot contradict the constraints it derived from. What the
seeded-then-cleared assertion still catches is the delete going missing, the
loop clearing the wrong set, or the commit not landing.

Every table is seeded before the clear that is supposed to empty it. An
assertion that a table is empty after clearing a database that never held a row
in it passes whether or not the delete is there at all, which is the same
"green on stale data" failure this module exists to rule out. Because the clear
is now generic and this proof is not, the coverage test below fails when a new
model is added to `Base.metadata` without being seeded here.

The remaining tests cover the paths that used to be silent: `clear_test_data()`
on a server that is not running raises instead of returning having cleared
nothing, a failed delete rolls back and re-raises, and a failed taxonomy
re-seed raises instead of leaving the suite green on an empty vocabulary. None
of them needs the Flask server, MariaDB or HTTP — they drive a bare
`E2ETestServer` with its attributes set by hand, against in-memory SQLite.
"""

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError, StatementError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (Attachment, Base, InventoryItem,
                          ItemPhotoAssociation, MaterialTaxonomy, Photo,
                          Product, ProductIdentifier, ProductTag, Purchase)
from tests.e2e.test_server import E2ETestServer


CATALOG_MODELS = (Product, Purchase, Attachment, ProductIdentifier, ProductTag)

# Split from CATALOG_MODELS only so the assertions below can name the two
# halves separately; `clear_test_data()` no longer distinguishes them, or any
# other table, since it stopped naming tables at all.
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


@pytest.mark.e2e
def test_every_metadata_table_is_covered_by_this_module():
    """`clear_test_data()` is generic; the proof above is not.

    The clear walks `Base.metadata` and so picks up a new model for free, but
    the seed helpers and the assertions still name their tables by hand. Left
    unchecked, a tenth model would be cleared with nothing proving it — the
    hand-maintenance this change removed, moved to the side where it is harder
    to notice. This is the tripwire: add a model, and it fails here, naming the
    table you have to seed.
    """
    proven = {model.__tablename__
              for model in CATALOG_MODELS + INVENTORY_MODELS}
    proven.add(MaterialTaxonomy.__tablename__)  # asserted NON-empty, above

    assert {table.name for table in Base.metadata.sorted_tables} == proven, \
        'clear_test_data() clears every table in Base.metadata, and this ' \
        'module must prove it for each one: seed a row in a table added to ' \
        'the metadata (or drop one removed from it) in CATALOG_MODELS / ' \
        'INVENTORY_MODELS, or in the MaterialTaxonomy exception above, ' \
        'which is asserted non-empty because the clear re-seeds it'


_NOT_SET = object()

# The guard only ever tests `storage` for truthiness, so a bare object stands
# in for it: no test below reaches a line that calls anything on storage.
_DUMMY_STORAGE = object()


@contextmanager
def _detached_server(storage=_NOT_SET, engine=_NOT_SET):
    """An `E2ETestServer` that was never `start()`ed, with the two attributes
    the guard reads set by hand.

    No Flask app, no thread, no MariaDB and no HTTP — the guard and both error
    paths are reachable without any of it, against in-memory SQLite. Disposes
    whatever engine it was handed so the connection does not outlive the test.
    """
    server = E2ETestServer()
    if storage is not _NOT_SET:
        server.storage = storage
    if engine is not _NOT_SET:
        server.engine = engine
    try:
        yield server
    finally:
        bound = getattr(server, 'engine', None)
        if bound is not None:
            bound.dispose()


def _resolve(engine_spec):
    if engine_spec == 'sqlite':
        return create_engine('sqlite://')
    return engine_spec


@pytest.mark.e2e
@pytest.mark.parametrize('storage, engine_spec', [
    # A fresh instance: `storage` is None and `engine` does not exist yet,
    # which is why the guard reads it through `getattr`, not `self.engine`.
    pytest.param(_NOT_SET, _NOT_SET, id='never_started'),
    # What `stop()` actually leaves behind — both nulled, attribute present.
    pytest.param(None, None, id='stopped'),
    # The state the old `hasattr(self, 'engine')` guard waved through: an
    # engine attribute that exists and is None.
    pytest.param(_DUMMY_STORAGE, None, id='half_stopped_engine_gone'),
    # ...and its mirror, which the old guard correctly rejected. Pinned so a
    # future rewrite of the guard cannot lose one half of it.
    pytest.param(None, 'sqlite', id='half_stopped_storage_gone'),
])
def test_clear_test_data_raises_when_the_server_is_not_running(storage,
                                                               engine_spec):
    """The clear used to return normally in every state below, having deleted
    nothing and skipped the re-seed: the silent-staleness outcome the re-raise
    in the handler was written to rule out, on a path the re-raise never sees.
    """
    engine = _resolve(engine_spec)
    with _detached_server(storage=storage, engine=engine) as srv:
        with pytest.raises(RuntimeError) as excinfo:
            srv.clear_test_data()

    assert 'NOT cleared' in str(excinfo.value), \
        'the message must say the catalog was not cleared, not just that ' \
        'something went wrong'


@pytest.mark.e2e
def test_clear_test_data_re_raises_when_a_delete_fails():
    """The handler's `raise` is the story's other half, and until now only
    incidentally covered. An engine whose schema is empty makes the first
    DELETE fail; a swallowed failure would return normally here and leave
    every later test running against a database it believes is clean.

    Only the re-raise is asserted, and the name says so. The handler's
    `session.rollback()` is not observable from here and no test can pin it:
    the failure is on the first DELETE, so there is nothing pending to undo,
    and the `finally: session.close()` below it discards uncommitted work
    anyway. That line is a belt-and-braces statement of intent, not behavior
    this module can hold to account.
    """
    with _detached_server(storage=_DUMMY_STORAGE,
                          engine=_resolve('sqlite')) as srv:
        with pytest.raises(SQLAlchemyError) as excinfo:
            srv.clear_test_data()

    statement = (getattr(excinfo.value, 'statement', '') or '').upper()
    assert 'DELETE' in statement, \
        f'the failure must come from the delete loop, not from connecting ' \
        f'or from anything before it: {statement!r}'


@pytest.mark.e2e
def test_setup_materials_taxonomy_raises_when_the_seeding_insert_fails():
    """The seeder used to swallow its exception, which left every
    material-facing e2e test asserting against an empty vocabulary — and
    passing, because they assert containment.

    The failure is forced into the INSERT half deliberately. The method opens
    with `session.query(MaterialTaxonomy).delete()`, so an engine with no
    tables at all fails there and never reaches the seeding loop — and would
    stay green against a regression that swallowed only the insert. A stub
    table with just an `id` column accepts the bare DELETE and rejects every
    INSERT, putting the failure where the name says it is.

    `StaticPool` is load-bearing, not decoration: a `sqlite://` database lives
    inside its connection, so the stub table created here is only visible to
    the session opened later if both get the same one. The default pool for
    in-memory SQLite happens to do that today, which would leave the test
    resting on a pooling default -- and it would not fail honestly if that
    changed, it would fail on the DELETE with the message below.
    """
    engine = create_engine('sqlite://', poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(
            text('CREATE TABLE material_taxonomy (id INTEGER PRIMARY KEY)'))

    with _detached_server(storage=_DUMMY_STORAGE, engine=engine) as srv:
        with pytest.raises(StatementError) as excinfo:
            srv.setup_materials_taxonomy()

    assert 'INSERT' in (excinfo.value.statement or '').upper(), \
        f'the failure must come from the seeding INSERT, not the DELETE ' \
        f'that precedes it: {excinfo.value.statement!r}'
