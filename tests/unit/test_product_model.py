"""
Unit tests for the Product ORM model (catalog subsystem, Story 1.1).

Exercises the Product entity via the SQLite test engine (Base.metadata.create_all).
These tests validate the ORM class, not the Alembic migration — keep the two in sync.
"""

import ast
import re
import pytest
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import sessionmaker

import app.database
from app.database import Product


def _make_session(test_storage):
    """Build a session bound to the test engine (SQLite)."""
    Session = sessionmaker(bind=test_storage.engine)
    return Session()


class TestProductModel:
    """Tests for the Product enhanced-ORM entity."""

    @pytest.mark.unit
    def test_tablename_and_columns(self):
        """Product maps to 'products' with the FR2 columns + internal_id (2.4)."""
        assert Product.__tablename__ == 'products'
        cols = set(Product.__table__.columns.keys())
        assert cols == {
            'id', 'internal_id', 'manufacturer', 'mpn', 'description', 'notes',
            'category_path', 'attributes', 'created_at', 'updated_at',
            # Story 5.1
            'quantity_on_hand', 'quantity_verified_at', 'location',
            'sub_location',
            # Story 5.2. The threshold is stored; the Effective-Low signal it
            # feeds is NOT — `is_effective_low` is derived at read (AD-6), so a
            # column by that name appearing here would be the defect.
            'reorder_threshold',
            # Story 5.3. The MANUAL assertion and the date it was last changed.
            # These are stored for the same reason the signal is not: they are
            # what the operator SAID, and nothing derives them.
            'stock_status', 'stock_status_at',
        }
        assert 'is_effective_low' not in cols

    @pytest.mark.unit
    def test_persist_and_reload(self, test_storage):
        """A Product persists and reloads with all FR2 fields intact."""
        session = _make_session(test_storage)
        try:
            product = Product(
                internal_id='PR0D000001',
                manufacturer='Texas Instruments',
                mpn='LM317T',
                description='LM317 adjustable voltage regulator, TO-220',
                notes='Bought a reel of these',
                category_path='electronics/power/linear-regulators',
                attributes={'package': 'TO-220', 'v_out_max': '37V'},
            )
            session.add(product)
            session.commit()
            product_id = product.id

            session.expunge_all()
            reloaded = session.get(Product, product_id)
            assert reloaded is not None
            assert reloaded.manufacturer == 'Texas Instruments'
            assert reloaded.mpn == 'LM317T'
            assert reloaded.description == 'LM317 adjustable voltage regulator, TO-220'
            assert reloaded.notes == 'Bought a reel of these'
            assert reloaded.category_path == 'electronics/power/linear-regulators'
        finally:
            session.close()

    @pytest.mark.unit
    def test_attributes_json_roundtrip(self, test_storage):
        """The attributes JSON column round-trips a Python dict."""
        session = _make_session(test_storage)
        try:
            specs = {'voltage': '12V', 'pins': 8, 'rohs': True, 'tags': ['a', 'b']}
            product = Product(internal_id='PR0D000002', description='Widget',
                              attributes=specs)
            session.add(product)
            session.commit()
            product_id = product.id

            session.expunge_all()
            reloaded = session.get(Product, product_id)
            assert reloaded.attributes == specs
            assert reloaded.attributes['pins'] == 8
            assert reloaded.attributes['tags'] == ['a', 'b']
        finally:
            session.close()

    @pytest.mark.unit
    def test_optional_fields_default_none(self, test_storage):
        """All FR2 fields except the PK/timestamps/internal_id accept NULL.

        internal_id is the one NOT NULL business column (Story 2.4): it has no
        DB default, so it must always be supplied by its sole writer.
        """
        session = _make_session(test_storage)
        try:
            product = Product(internal_id='PR0D000003')  # no other field at all
            session.add(product)
            session.commit()
            product_id = product.id

            session.expunge_all()
            reloaded = session.get(Product, product_id)
            assert reloaded.manufacturer is None
            assert reloaded.mpn is None
            assert reloaded.description is None
            assert reloaded.notes is None
            assert reloaded.category_path is None
            assert reloaded.attributes is None
            # Story 5.1: all four are nullable with NO server default, so a bare
            # insert leaves the product UNTRACKED. `quantity_on_hand IS NULL` is
            # the state FR23 names, and a server default of 0 would silently
            # claim every product in the catalog had been counted and found
            # empty.
            assert reloaded.quantity_on_hand is None
            assert reloaded.quantity_verified_at is None
            assert reloaded.location is None
            assert reloaded.sub_location is None
            # Story 5.2: nullable with no server default too. A default of 0
            # would give every product in the catalog a threshold nobody chose,
            # and — since `0` is a REAL threshold — would flag every product
            # that ever reached zero on hand as low.
            assert reloaded.reorder_threshold is None
            # Story 5.3 is the one exception on this list, and deliberately so:
            # `stock_status` is NOT NULL with a default, because a NULL inside
            # the Effective-Low expression would make its negation drop rows
            # (see the column comment). `unknown` is the honest value for a
            # product nobody has asserted anything about, and it carries no
            # date because no assertion has been made.
            assert reloaded.stock_status == 'unknown'
            assert reloaded.stock_status_at is None
        finally:
            session.close()

    @pytest.mark.unit
    def test_quantity_zero_persists_distinctly_from_none(self, test_storage):
        """`0` and NULL are two different stored states, not one (FR23/FR24).

        The whole story rests on the column being able to tell "tracked, none on
        hand" from "not tracked", so this asserts it at the storage layer rather
        than trusting that Python's `0 is not None` survives a round trip
        through the driver — which is exactly where a NOT NULL column with a
        default, or a coercion in the model, would collapse the two.
        """
        session = _make_session(test_storage)
        try:
            tracked = Product(internal_id='PR0D000010', description='Counted',
                              quantity_on_hand=0,
                              quantity_verified_at=datetime(2026, 7, 29, 9, 0))
            untracked = Product(internal_id='PR0D000011',
                                description='Uncounted')
            session.add_all([tracked, untracked])
            session.commit()
            tracked_id, untracked_id = tracked.id, untracked.id

            session.expunge_all()
            reloaded_tracked = session.get(Product, tracked_id)
            reloaded_untracked = session.get(Product, untracked_id)
            assert reloaded_tracked.quantity_on_hand == 0
            assert reloaded_tracked.quantity_on_hand is not None
            assert reloaded_tracked.quantity_verified_at == \
                datetime(2026, 7, 29, 9, 0)
            assert reloaded_untracked.quantity_on_hand is None
        finally:
            session.close()

    @pytest.mark.unit
    def test_reorder_threshold_zero_persists_distinctly_from_none(
            self, test_storage):
        """`0` and NULL are two different thresholds, not one (FR26/FR30).

        A stored `0` means "low only once the count reaches zero" — a threshold
        the operator deliberately set — while NULL means there is no threshold
        at all and the signal's threshold branch simply does not apply. Asserted
        at the storage layer for the reason the quantity's twin is: a NOT NULL
        column with a default, or a truthiness coercion anywhere on the write
        path, is what would collapse the two.
        """
        session = _make_session(test_storage)
        try:
            zeroed = Product(internal_id='PR0D000020', description='Zero rule',
                             reorder_threshold=0)
            none = Product(internal_id='PR0D000021', description='No rule')
            session.add_all([zeroed, none])
            session.commit()
            zeroed_id, none_id = zeroed.id, none.id

            session.expunge_all()
            reloaded_zero = session.get(Product, zeroed_id)
            assert reloaded_zero.reorder_threshold == 0
            assert reloaded_zero.reorder_threshold is not None
            assert session.get(Product, none_id).reorder_threshold is None
        finally:
            session.close()

    @pytest.mark.unit
    def test_location_pair_persists(self, test_storage):
        """The FR27 location pair round-trips; both are plain optional strings."""
        session = _make_session(test_storage)
        try:
            product = Product(internal_id='PR0D000012', description='Shelved',
                              location='Bin 7', sub_location='Left tray')
            session.add(product)
            session.commit()
            product_id = product.id

            session.expunge_all()
            reloaded = session.get(Product, product_id)
            assert reloaded.location == 'Bin 7'
            assert reloaded.sub_location == 'Left tray'
        finally:
            session.close()

    @pytest.mark.unit
    def test_timestamps_autopopulate(self, test_storage):
        """created_at and updated_at populate automatically on insert."""
        session = _make_session(test_storage)
        try:
            product = Product(internal_id='PR0D000004', description='Timestamped')
            session.add(product)
            session.commit()

            assert isinstance(product.created_at, datetime)
            assert isinstance(product.updated_at, datetime)
        finally:
            session.close()

    @pytest.mark.unit
    def test_to_dict(self, test_storage):
        """to_dict() returns the FR2 fields with ISO-formatted timestamps."""
        session = _make_session(test_storage)
        try:
            product = Product(
                internal_id='PR0D000005',
                manufacturer='Bourns',
                mpn='3386P-1-103',
                description='10k trimmer potentiometer',
                category_path='electronics/passives/potentiometers',
                attributes={'resistance': '10k'},
            )
            session.add(product)
            session.commit()

            d = product.to_dict()
            assert set(d.keys()) == {
                'id', 'internal_id', 'manufacturer', 'mpn', 'description', 'notes',
                'category_path', 'attributes', 'created_at', 'updated_at',
                # Story 5.1 — this dict IS the audit snapshot, so a column
                # missing from it is a column no audit record can show changing.
                'quantity_on_hand', 'quantity_verified_at', 'location',
                'sub_location',
                # Story 5.2, for the same reason.
                'reorder_threshold',
                # Story 5.3, for the same reason: this pair IS the manual
                # assertion, so an audit record without it cannot answer who
                # said the product was low, or when.
                'stock_status', 'stock_status_at',
            }
            # And the derived signal is NOT in it: the snapshot records what was
            # STORED, and a computed value in it would read as a column changing
            # when nothing was written (AD-6).
            assert 'is_effective_low' not in d
            assert d['internal_id'] == 'PR0D000005'
            assert d['manufacturer'] == 'Bourns'
            assert d['mpn'] == '3386P-1-103'
            assert d['attributes'] == {'resistance': '10k'}
            # timestamps serialized as ISO strings
            assert isinstance(d['created_at'], str)
            datetime.fromisoformat(d['created_at'])
        finally:
            session.close()

    @pytest.mark.unit
    def test_to_dict_carries_the_stock_columns(self, test_storage):
        """The Story 5.1/5.2/5.3 columns appear with their stored values.

        `quantity_verified_at` is serialized like the other timestamps (ISO
        string, or None), and `quantity_on_hand` is emitted RAW so that the
        audit log records `0` as `0` rather than as an empty-looking value —
        the one thing the tri-state contract cannot afford to lose.
        """
        session = _make_session(test_storage)
        try:
            stamped = Product(internal_id='PR0D000013', description='Counted',
                              quantity_on_hand=0,
                              quantity_verified_at=datetime(2026, 7, 29, 9, 30),
                              reorder_threshold=0,
                              stock_status='low',
                              stock_status_at=datetime(2026, 7, 29, 9, 45),
                              location='Bin 7', sub_location='Left tray')
            untracked = Product(internal_id='PR0D000014', description='Bare')
            session.add_all([stamped, untracked])
            session.commit()

            d = stamped.to_dict()
            assert d['quantity_on_hand'] == 0
            assert d['quantity_verified_at'] == '2026-07-29T09:30:00'
            # Story 5.2, raw for the same reason: a `0` threshold logged as an
            # empty-looking value is indistinguishable from no threshold.
            assert d['reorder_threshold'] == 0
            # Story 5.3: the stored string, and its date serialized like every
            # other timestamp here.
            assert d['stock_status'] == 'low'
            assert d['stock_status_at'] == '2026-07-29T09:45:00'
            assert d['location'] == 'Bin 7'
            assert d['sub_location'] == 'Left tray'

            bare = untracked.to_dict()
            assert bare['quantity_on_hand'] is None
            assert bare['quantity_verified_at'] is None
            assert bare['reorder_threshold'] is None
            # The ONE column on this list that is not None on a bare product,
            # and the difference is the whole reason it is NOT NULL: `unknown`
            # is a stored value meaning "nobody has asserted anything", not an
            # absence. An audit snapshot reading None here would mean the
            # column's default had not been applied.
            assert bare['stock_status'] == 'unknown'
            assert bare['stock_status_at'] is None
            assert bare['location'] is None
            assert bare['sub_location'] is None
        finally:
            session.close()

    @pytest.mark.unit
    def test_repr(self):
        """__repr__ is informative and does not raise."""
        product = Product(internal_id='PR0D000006', mpn='LM317T',
                          description='regulator')
        r = repr(product)
        assert 'Product' in r
        assert 'LM317T' in r


# --- Stories 5.2/5.3: the Effective-Low predicate ----------------------------

# The story's I/O matrix, as data, so that the Python getter and the SQL
# expression are held to the SAME rows rather than to two lists that could drift
# apart — which is the very failure AD-6's single-expression rule exists to
# prevent. Each row is
# (label, stock_status, quantity_on_hand, reorder_threshold, is low).
#
# Story 5.3 added the status dimension rather than a second table, because the
# predicate is ONE `or_` and the rows that matter most are the ones where the
# two branches disagree: a manual `low` on a product with no count at all (the
# threshold branch cannot fire) and a manual `ok` under a crossed threshold (the
# status branch cannot suppress it).
_EFFECTIVE_LOW_MATRIX = [
    # The Story 5.2 rows, unchanged in meaning and now carrying the status the
    # column defaults to. `unknown` is the ABSENCE of an assertion, so none of
    # these answers may move.
    ('below the threshold', 'unknown', 2, 3, True),
    ('at the threshold', 'unknown', 3, 3, True),   # the comparison is `<=`
    ('above the threshold', 'unknown', 4, 3, False),
    ('a zero threshold with a zero count', 'unknown', 0, 0, True),
    ('a zero threshold with stock on hand', 'unknown', 1, 0, False),
    # Not "low because empty": with no threshold the branch is false however the
    # quantity reads (FR30).
    ('no threshold', 'unknown', 0, None, False),
    ('untracked with a threshold', 'unknown', None, 3, False),
    ('neither set', 'unknown', None, None, False),

    # Story 5.3 (FR28/FR29/FR31). The manual branch stands entirely on its own:
    # these rows track nothing and have no threshold, which is the case the
    # whole story exists for — flagging something low is never gated on
    # committing to count it.
    ('flagged low with nothing tracked', 'low', None, None, True),
    ('flagged out with nothing tracked', 'out', None, None, True),
    ('flagged ok with nothing tracked', 'ok', None, None, False),
    # A manual flag on a product that IS counted and is comfortably stocked.
    # The two branches disagree and the OR settles it: the operator looked in
    # the bin more recently than the count did.
    ('flagged low above its threshold', 'low', 9, 3, True),
    ('flagged out with a count and no threshold', 'out', 9, None, True),
    # And the other direction, which is the one an `elif`-shaped implementation
    # gets wrong: asserting `ok` does NOT suppress the threshold branch (FR30,
    # AD-6). The operator's opinion cannot outrank a count they recorded against
    # a threshold they set.
    ('flagged ok below its threshold', 'ok', 2, 3, True),
    ('flagged ok at its threshold', 'ok', 3, 3, True),
    ('flagged ok above its threshold', 'ok', 4, 3, False),
]

_EFFECTIVE_LOW_PARAMS = [
    pytest.param(status, quantity, threshold, low, id=label.replace(' ', '-'))
    for label, status, quantity, threshold, low in _EFFECTIVE_LOW_MATRIX
]


@pytest.mark.unit
class TestTheEffectiveLowPredicate:
    """FR30's signal in both of its encodings, held to one answer per row.

    `Product.is_effective_low` is the single home of the predicate (AD-6): the
    Python getter serves the detail page off a detached instance, the SQL
    expression serves Story 5.6's reorder view and Epic 8's stock facet. The
    point of these tests is not that either encoding is individually right but
    that they AGREE — so both are driven from `_EFFECTIVE_LOW_MATRIX` above, and
    the SQL side is checked in both directions because the negation is where a
    NULL-returning expression fails silently rather than loudly.
    """

    @pytest.mark.parametrize('status, quantity, threshold, low',
                             _EFFECTIVE_LOW_PARAMS)
    def test_the_python_getter_answers_the_matrix(self, status, quantity,
                                                  threshold, low):
        """Read off an unsaved instance on purpose: the getter must depend on
        nothing but the three mapped scalars, so it has to work with no session,
        no identity and no row behind it — which is the same thing that makes it
        safe on the detached Product the detail page renders."""
        product = Product(internal_id='PR0D000030', description='Matrix row',
                          stock_status=status,
                          quantity_on_hand=quantity,
                          reorder_threshold=threshold)
        assert product.is_effective_low is low

    def test_the_getter_returns_a_real_bool_not_a_truthy_value(self):
        """`is` comparisons above would pass for `1`/`0` if the getter leaked an
        int out of the comparison chain, but every caller that treats the answer
        as a domain flag — the template's `{% if %}` included — deserves a real
        bool, and a caller doing `is True` deserves not to be surprised.

        Story 5.3 makes this less obvious than it looks rather than more: the
        body is now an `or` of two sub-expressions, and `or` returns one of its
        OPERANDS. A membership test and an `and`-chain both happen to yield
        bools, but a status branch written as (say) `self.stock_status and …`
        would leak a string out of the very first row below.
        """
        low = Product(internal_id='PR0D000031', quantity_on_hand=2,
                      reorder_threshold=3)
        flagged = Product(internal_id='PR0D000035', stock_status='low')
        untracked = Product(internal_id='PR0D000032')
        assert type(low.is_effective_low) is bool
        assert type(flagged.is_effective_low) is bool
        assert type(untracked.is_effective_low) is bool

    def test_the_getter_answers_for_an_unset_status_attribute(self):
        """The column is NOT NULL, but a Python instance that has never been
        flushed has not had its default applied — `Product(...)` leaves
        `stock_status` at None until the INSERT. The getter must read that as
        "not low" rather than raising, because it is the state every one of the
        Story 5.2 rows above is constructed in, and because `create_product`
        evaluates nothing but is one `to_dict()` away from an instance in it.
        """
        bare = Product(internal_id='PR0D000036')
        assert bare.stock_status is None
        assert bare.is_effective_low is False

    def test_the_getter_reads_no_relationship(self, test_storage):
        """`CatalogService.get_product` returns a DETACHED Product, so touching
        `product.purchases` in this property would raise DetachedInstanceError
        on the one page it exists to render. Exercised exactly the way
        `get_product` produces that instance — a read-only query on its own
        session, which is then closed — rather than by expunging a freshly
        committed one, whose expired attributes would raise on ANY column and so
        would prove nothing about relationships."""
        session = _make_session(test_storage)
        try:
            session.add(Product(internal_id='PR0D000033',
                                description='Detached',
                                quantity_on_hand=2, reorder_threshold=3))
            session.commit()
        finally:
            session.close()

        reader = _make_session(test_storage)
        try:
            detached = (reader.query(Product)
                        .filter(Product.internal_id == 'PR0D000033').first())
        finally:
            reader.close()

        assert detached.is_effective_low is True

    def test_the_sql_expression_answers_the_same_matrix(self, test_storage):
        """The same rows through a `WHERE`, and — the half that matters — through
        its negation.

        `filter(~Product.is_effective_low)` is where a missing `IS NOT NULL`
        guard shows up: a bare comparison against a NULL column is NULL, `NOT
        NULL` is NULL, and every untracked product would quietly vanish from
        "everything that is not low" while the positive filter still looked
        right. So this asserts the two result sets PARTITION the seeded rows
        rather than merely checking each one's membership.

        Story 5.3 puts a second three-valued hazard in the same expression and
        answers it differently: `stock_status IN ('low','out')` is NULL for a
        NULL status, and `OR(NULL, FALSE)` is NULL, so the whole predicate would
        go back to dropping rows from both halves. The guard there is the
        COLUMN's `NOT NULL DEFAULT 'unknown'` rather than anything in the
        expression — which is why the partition assertion below is what would
        catch a later widening that made the column nullable again.
        """
        session = _make_session(test_storage)
        try:
            expected_low, expected_not_low = set(), set()
            for index, (label, status, quantity, threshold, low) in enumerate(
                    _EFFECTIVE_LOW_MATRIX):
                product = Product(internal_id=f'PR0DLOW{index:04d}',
                                  description=label,
                                  stock_status=status,
                                  quantity_on_hand=quantity,
                                  reorder_threshold=threshold)
                session.add(product)
                session.flush()  # assigns the id this row is recorded under
                (expected_low if low else expected_not_low).add(product.id)
            session.commit()

            low_ids = {p.id for p in session.query(Product)
                       .filter(Product.is_effective_low)}
            not_low_ids = {p.id for p in session.query(Product)
                           .filter(~Product.is_effective_low)}

            assert low_ids == expected_low
            assert not_low_ids == expected_not_low
            # A true complement: every seeded row is in exactly one side.
            assert low_ids | not_low_ids == expected_low | expected_not_low
            assert low_ids & not_low_ids == set()
        finally:
            session.close()

    def test_reading_the_predicate_writes_nothing(self, test_storage):
        """AD-6/FR30: the signal is derived at read, so evaluating it must leave
        the session clean, issue no UPDATE and leave `updated_at` where it was.

        A derived value that quietly writes is worse than a stored column: it
        makes the row's modification history a record of who LOOKED at it.
        """
        from sqlalchemy import event

        session = _make_session(test_storage)
        try:
            product = Product(internal_id='PR0D000034', description='Untouched',
                              quantity_on_hand=2, reorder_threshold=3)
            session.add(product)
            session.commit()
            product_id = product.id
            stored_updated_at = product.updated_at

            statements = []

            def _record(conn, cursor, statement, parameters, context,
                        executemany):
                statements.append(statement)

            event.listen(test_storage.engine, 'before_cursor_execute', _record)
            try:
                assert product.is_effective_low is True
                assert not session.dirty
                # Commit AFTER the read: anything the property had pending would
                # be flushed here and show up in the captured statements.
                session.commit()
            finally:
                event.remove(test_storage.engine, 'before_cursor_execute',
                             _record)

            assert not [s for s in statements if 'UPDATE' in s.upper()], \
                statements

            session.expunge_all()
            assert session.get(Product, product_id).updated_at == \
                stored_updated_at
        finally:
            session.close()


class TestTheComparisonHasExactlyOneHome:
    """A source tripwire for the Story 5.2/5.3 acceptance criterion (AD-6).

    > Given the finished implementation, when the codebase is searched for a
    > `quantity_on_hand`/`reorder_threshold` comparison or for a `('low','out')`
    > membership test, then each appears only inside `Product
    > .is_effective_low`'s two bodies and the one enum-adjacent constant that
    > names the set.

    Every docstring around the predicate repeats that a hand-written copy of
    the comparison elsewhere "is a defect, not a shortcut" — and until this
    file, prose was the entire enforcement. That is the weakest possible guard
    on the invariant the whole story rests on, because the two moments a second
    copy becomes tempting are one behind and one ahead: Story 5.3 widened the
    predicate (making the two bodies disagree with anything that had copied
    them) and Story 5.6 adds the first query consumer (whose author may find
    writing the `WHERE` by hand easier than importing the expression). A
    grep-shaped invariant needs a grep-shaped test; the repo already writes
    several (`test_doctest_scope.py`, `test_autocomplete_markup.py`,
    `test_keydown_focus_guards.py`).

    Story 5.3's branch needed its own detector rather than fitting the existing
    one, and the reason is worth stating because it is why the original test
    neither broke nor protected the new term: the status branch is not an
    ordering comparison at all, and it has THREE structurally different
    spellings — `self.stock_status in LOW_STOCK_STATUS_VALUES` is an
    `ast.Compare`, `cls.stock_status.in_(…)` is a `Call` that no `Compare` walk
    can see, and a hand-written copy is as likely to be spelled
    `p.stock_status == 'low' or p.stock_status == 'out'`, which is a `Compare`
    with neither `In` nor a collection literal anywhere in it. The detector
    covers all three; `_status_low_tests` says why the equality arm has to be
    narrowed to the two low values rather than to the column alone.

    What this asserts is STRUCTURE, and the limit is worth stating rather than
    discovering: it finds a comparison that names both columns, or a low-status
    test that names the status column, not one that means the same thing by
    other means. A copy that first assigns the columns to locals, or compares
    `getattr(p, 'reorder_threshold')`, passes. It is a tripwire against the
    obvious duplication, not a proof of single-sourcing.
    """

    _COLUMNS = {'quantity_on_hand', 'reorder_threshold'}
    _STATUS_COLUMN = 'stock_status'
    _ORDERING_OPERATORS = ('<=', '>=', '<', '>')
    # The stored values that mean low. Spelled out HERE on purpose, and this is
    # the one place in the repo outside `app.models` that may: a tripwire that
    # imported the constant it is policing would pass by construction if the
    # constant were emptied.
    _LOW_STATUS_VALUES = {'low', 'out'}
    # The whole stored vocabulary, spelled out for the same reason. Only the
    # Jinja walk uses it, and `test_no_template_tests_the_status` says why it
    # needs all four where the AST walks need only the two low ones.
    _STORED_STATUS_VALUES = {'unknown', 'ok', 'low', 'out'}

    def _app_root(self):
        return Path(app.database.__file__).resolve().parent

    def _comparisons_naming_both_columns(self, tree):
        """`(dotted scope, lineno)` per comparison that names both columns.

        Walks the parsed tree rather than the text on purpose: every docstring
        and comment in `app/database.py` discusses this comparison in prose,
        and a text scan would drown in the very documentation that states the
        rule.
        """
        found = []
        scope = []

        class _Visitor(ast.NodeVisitor):

            def _scoped(self, node):
                scope.append(node.name)
                self.generic_visit(node)
                scope.pop()

            visit_FunctionDef = _scoped
            visit_AsyncFunctionDef = _scoped
            visit_ClassDef = _scoped

            def visit_Compare(self, node):
                names = set()
                for child in ast.walk(node):
                    if isinstance(child, ast.Attribute):
                        names.add(child.attr)
                    elif isinstance(child, ast.Name):
                        names.add(child.id)
                if TestTheComparisonHasExactlyOneHome._COLUMNS <= names:
                    found.append(('.'.join(scope), node.lineno))
                self.generic_visit(node)

        _Visitor().visit(tree)
        return found

    def _status_low_tests(self, tree):
        """`(dotted scope, lineno)` per test of `stock_status` against LOW.

        THREE spellings, because the predicate's two bodies already use two
        different ones and a hand-written copy could use any of them:

        * `<anything>.stock_status in <anything>` (or `not in`) — an
          `ast.Compare` whose operator is `In`/`NotIn`. This is the Python
          getter's form.
        * `<anything>.stock_status.in_(…)` — an `ast.Call` on an attribute
          named `in_`. This is the SQLAlchemy `@expression`'s form, and it is
          invisible to any walk of `Compare` nodes.
        * `<anything>.stock_status == 'low'` (or `!=`, or against `'out'`) —
          an `ast.Compare` whose operator is `Eq`/`NotEq` and one of whose
          operands is the string `'low'` or `'out'`.

        The third was the hole, and it was a real one: `if p.stock_status ==
        'low' or p.stock_status == 'out':` is a complete duplicate of the
        predicate's status branch, and it escaped BOTH the membership walk
        above (no `In`, no `in_`) and
        `test_no_module_spells_the_low_status_set_by_hand` below (no collection
        literal to find — the two values never sit in one). This walk's Jinja
        twin, `test_no_template_tests_the_status`, already said out loud that
        it "has to be WIDER" for exactly this reason; the same reasoning simply
        had not been applied here.

        The equality arm is narrowed to the LOW values on purpose, and it is
        the narrowing that keeps this test usable at all: `stock_status ==
        StockStatus.UNKNOWN.value` is legitimate, appears in both
        `app/main/routes.py` (the detail page's age gate) and
        `app/mariadb_catalog_service.py` (the write contract's clear branch),
        and is not a copy of anything — the predicate is about `low`/`out` and
        says nothing about `unknown`. Only a comparison whose CONSTANT operand
        is one of the two low spellings duplicates the branch.

        Names are matched the way `_comparisons_naming_both_columns` matches
        them — as an attribute or a bare name — which deliberately does NOT
        catch `'stock_status' in form_data`, a STRING constant testing a form
        key rather than the column. That construct is ordinary route code and
        appears several times; treating it as a copy of the predicate would
        make this test unusable.
        """
        found = []
        scope = []
        status_column = TestTheComparisonHasExactlyOneHome._STATUS_COLUMN
        low_values = TestTheComparisonHasExactlyOneHome._LOW_STATUS_VALUES

        def _names(node):
            names = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Attribute):
                    names.add(child.attr)
                elif isinstance(child, ast.Name):
                    names.add(child.id)
            return names

        def _string_constants(node):
            return {child.value for child in ast.walk(node)
                    if isinstance(child, ast.Constant)
                    and isinstance(child.value, str)}

        class _Visitor(ast.NodeVisitor):

            def _scoped(self, node):
                scope.append(node.name)
                self.generic_visit(node)
                scope.pop()

            visit_FunctionDef = _scoped
            visit_AsyncFunctionDef = _scoped
            visit_ClassDef = _scoped

            def visit_Compare(self, node):
                names = _names(node)
                membership = (any(isinstance(op, (ast.In, ast.NotIn))
                                  for op in node.ops)
                              and status_column in names)
                # `elif` in effect, via the `or`: one node is one site however
                # many ways it offends, so a `stock_status in ('low','out')`
                # is not counted twice and the "exactly two" assertions below
                # keep meaning what they say.
                equality = (any(isinstance(op, (ast.Eq, ast.NotEq))
                                for op in node.ops)
                            and status_column in names
                            and bool(low_values & _string_constants(node)))
                if membership or equality:
                    found.append(('.'.join(scope), node.lineno))
                self.generic_visit(node)

            def visit_Call(self, node):
                func = node.func
                if (isinstance(func, ast.Attribute) and func.attr == 'in_'
                        and status_column in _names(func.value)):
                    found.append(('.'.join(scope), node.lineno))
                self.generic_visit(node)

        _Visitor().visit(tree)
        return found

    def _sites(self, finder):
        """`[('<path>:<lineno>', '<dotted scope>'), …]` over every module in `app/`.

        A LIST of pairs rather than a mapping keyed by location, because the
        `len(...) == 2` assertions below rest on the counting: two offending
        nodes on ONE physical line are two sites, and a dict keyed
        `path:lineno` silently collapsed them into one. That collapse was a
        hole rather than a cosmetic detail — a duplicate could hide by sharing
        a line with a legitimate site, in the one property whose whole claim is
        "exactly two, and a third inside it is as much a violation".
        """
        app_root = self._app_root()
        sites = []
        for path in sorted(app_root.rglob('*.py')):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for dotted_scope, lineno in finder(tree):
                sites.append(
                    (f'{path.relative_to(app_root.parent)}:{lineno}',
                     dotted_scope))
        return sites

    def test_only_the_predicate_compares_the_two_columns(self):
        sites = self._sites(self._comparisons_naming_both_columns)

        assert {scope for _site, scope in sites} == \
            {'Product.is_effective_low'}, sites
        # Exactly two: the Python getter and the SQL `@expression`. AD-6 does
        # not say "few" comparisons, it says two encodings — so a THIRD inside
        # the property is as much a violation as one outside it, and a drop to
        # one means an encoding was lost rather than that the rule tightened.
        assert len(sites) == 2, sites
        assert all(site.startswith('app/database.py:')
                   for site, _scope in sites), sites

    def test_only_the_predicate_tests_the_status_against_a_low_value(self):
        """Story 5.3's half of the same invariant.

        The status branch is one `or` term in the getter and one `or_` term in
        the expression — the same two bodies, counted the same way. A third
        inside the property is as much a violation as one outside it (AD-6 says
        two ENCODINGS, not "few tests"), and a drop to one means a branch was
        lost rather than that the rule tightened.

        Counted per NODE, which `_sites` says why: `p.stock_status == 'low' or
        p.stock_status == 'out'` is TWO `ast.Compare` nodes and therefore two
        sites on its own, even written on one line — so it fails this assertion
        twice over, which is the intended outcome.

        This test needs no separate positive control: it asserts an exact count
        and an exact scope, so a finder that stopped finding things fails here
        rather than passing quietly. The two `== {}` tripwires below are the
        ones that need one, and they carry it.
        """
        sites = self._sites(self._status_low_tests)

        assert {scope for _site, scope in sites} == \
            {'Product.is_effective_low'}, sites
        assert len(sites) == 2, sites
        assert all(site.startswith('app/database.py:')
                   for site, _scope in sites), sites

    def test_no_module_spells_the_low_status_set_by_hand(self):
        """The other way a second copy of "which statuses mean low" arrives.

        `app.models.LOW_STOCK_STATUS_VALUES` is built from the enum members, so
        the two stored strings appear together in no literal anywhere — and a
        later `if product.stock_status in ('low', 'out')` is exactly the defect
        the walk above catches only when it names the column directly. This
        catches the COLLECTION instead, so a copy assigned to a local first, or
        passed to a helper, is still found.

        Its scope is exactly `ast.Tuple` / `ast.List` / `ast.Set` — a SEQUENCE
        or set literal containing both strings — and that is narrower than
        "every literal". Two exclusions are deliberate rather than accidental:

        * DICT literals are not inspected, and must not be.
          `app.main.routes._STOCK_STATUS_LABELS` is a legitimate dict keyed by
          all four stored values, so it contains both of these; widening this
          walk to `ast.Dict` would flag the single mapping the whole display
          layer is built from, every run, and the only way to keep the test
          green would be to delete the test or split the mapping. A dict
          mapping the vocabulary to something is not a copy of "which statuses
          mean low" — it says nothing about lowness at all.
        * A collection holding the two values by other means — built from the
          enum, or assembled at runtime — is invisible here for the same reason
          the walks above are structural. That is the tripwire's standing
          limit, not a gap specific to this test.

        Asserting an EMPTY result is the shape that can pass vacuously, so the
        walk is exercised against a synthetic offender first: a typo in the node
        types, or a `_LOW_STATUS_VALUES` that lost a member, then fails here
        instead of reporting a clean repo forever.
        """
        known_bad = ast.parse(
            "def is_low(p):\n"
            "    return p.stock_status in ('low', 'out')\n")
        assert self._collections_spelling_the_low_set(known_bad), (
            'the walk found nothing in a module that spells the set by hand')

        offenders = {}
        app_root = self._app_root()
        for path in sorted(app_root.rglob('*.py')):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for lineno, values in self._collections_spelling_the_low_set(tree):
                offenders[
                    f'{path.relative_to(app_root.parent)}:{lineno}'
                ] = values

        assert offenders == {}, offenders

    def _collections_spelling_the_low_set(self, tree):
        """`[(lineno, sorted values), …]` per sequence/set literal holding both."""
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
                continue
            values = {element.value for element in node.elts
                      if isinstance(element, ast.Constant)
                      and isinstance(element.value, str)}
            if self._LOW_STATUS_VALUES <= values:
                found.append((node.lineno, sorted(values)))
        return found

    def test_no_template_compares_the_two_columns(self):
        """The other place a copy could live, and the one AST cannot see.

        `detail.html` receives the answer as a finished `effective_low` boolean
        precisely so it never has to ask the question, and its own comment says
        the template neither computes nor compares. Jinja would let it.
        """
        offenders = []
        templates = self._app_root() / 'templates'
        for path in sorted(templates.rglob('*.html')):
            text = path.read_text(encoding='utf-8')
            # Only inside Jinja delimiters: raw HTML is made of `<` and `>`.
            for block in re.findall(r'\{[{%].*?[%}]\}', text, re.DOTALL):
                if 'reorder_threshold' not in block:
                    continue
                if any(op in block for op in self._ORDERING_OPERATORS):
                    offenders.append((str(path.name), block.strip()))

        assert not offenders, offenders

    def test_no_template_tests_the_status(self):
        """The Story 5.3 twin of the check above, and it has to be WIDER.

        The threshold copy needs an ordering operator to be one; a status copy
        needs nothing but the value — `{% if product.stock_status in ['low',
        'out'] %}`, `{% if product.stock_status == 'low' %}` and
        `{{ 'Low stock' if product.stock_status != 'ok' }}` are all the same
        defect, and only the first carries an operator this file already looks
        for. So any Jinja block that names the column AND quotes ANY of the four
        stored values is an offender.

        All four rather than the two low ones, because the third spelling above
        quotes NEITHER low value and is the likeliest way to write the copy
        wrongly — it is also the exact spelling that gets FR30's non-override
        rule backwards, since `!= 'ok'` reads `unknown` as low. A tripwire blind
        to it would have been blind to the worst version of the defect.

        The templates legitimately name `stock_status` — the two forms render
        the select from `form_data` and choose the `selected` option by
        comparing against each choice's own value — so naming it is not the
        offence. Quoting a stored value beside it is: the option loop reads the
        values out of the route's list rather than spelling any of them.

        Exercised against a synthetic offender first, for the reason the walk
        above is: `not offenders` passes just as happily when the regex stops
        matching Jinja delimiters at all.
        """
        known_bad = "{{ 'Low stock' if product.stock_status != 'ok' }}"
        assert self._jinja_blocks_testing_the_status(known_bad), (
            'the walk found nothing in a template that tests the status')

        offenders = []
        templates = self._app_root() / 'templates'
        for path in sorted(templates.rglob('*.html')):
            text = path.read_text(encoding='utf-8')
            for block in self._jinja_blocks_testing_the_status(text):
                offenders.append((str(path.name), block))

        assert not offenders, offenders

    def _jinja_blocks_testing_the_status(self, text):
        """The Jinja blocks in `text` that name the column and quote a value."""
        found = []
        for block in re.findall(r'\{[{%].*?[%}]\}', text, re.DOTALL):
            if self._STATUS_COLUMN not in block:
                continue
            if any(f"'{value}'" in block or f'"{value}"' in block
                   for value in self._STORED_STATUS_VALUES):
                found.append(block.strip())
        return found
