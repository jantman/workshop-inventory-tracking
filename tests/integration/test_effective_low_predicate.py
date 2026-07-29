"""``Product.is_effective_low``'s SQL half, against the engine that will run it.

The unit tier (tests/unit/test_product_model.py::TestTheEffectiveLowPredicate)
drives both encodings of the predicate through the same matrix, but it does so
on SQLite -- and this is one of the places where that proves less than it looks
like it does:

* The predicate's stated consumers (Story 5.6's reorder view, Epic 8's stock
  facet, AD-6) filter in the DATABASE. Production is MariaDB/InnoDB.
* The very hazard that justifies ``update_product``'s ``reorder_threshold``
  branch -- ``'3'`` reaching an ``Integer`` column and being compared as text --
  is SQLite-specific, so the engine that makes the branch necessary is not the
  engine that runs the comparison in anger.
* The story's subtle invariant is the NEGATION: the two ``IS NOT NULL`` guards
  lead the ``and_`` so that a non-qualifying row is FALSE rather than NULL, and
  ``~Product.is_effective_low`` is therefore a true complement. Three-valued
  logic is exactly the area where a dialect could differ, and a row silently
  missing from BOTH halves of a partition is invisible to a one-sided test.
* Story 5.3 put a SECOND three-valued hazard in the same expression and guarded
  it differently. ``stock_status IN ('low','out')`` is NULL for a NULL status
  and ``OR(NULL, FALSE)`` is NULL, so the negation would go straight back to
  dropping rows — but the guard is the COLUMN's ``NOT NULL DEFAULT 'unknown'``
  rather than anything in the expression, which means it is a property of the
  MIGRATED schema and not of the Python. On SQLite the unit tier builds that
  schema with ``create_all``; here it is the one Alembic actually shipped, and a
  ``VARCHAR IN (…)`` against it is what keeps the negation two-valued in
  production.

* The status branch is a STRING comparison, so its answer depends on the
  column's COLLATION -- something SQLite has no equivalent of. Under the
  utf8mb4_unicode_ci that `products` otherwise inherits, ``stock_status IN
  ('low','out')`` is TRUE for ``'LOW'``, ``'Low'`` and ``'lòw'`` while the
  Python getter's frozenset membership is FALSE for all three, and neither
  tier's matrix would notice because both seed only the four canonical
  spellings. The column is pinned ``utf8mb4_bin`` for that reason; the last two
  tests below assert the consequence, including the one case the pin does not
  close.

What is deliberately NOT re-tested here: the Python getter (no database in it)
and the write contract (SQLite arbitrates it identically).
"""

import pytest

from app.database import Product

# The same rows as the unit tier's `_EFFECTIVE_LOW_MATRIX`, kept as
# (internal_id, stock_status, quantity_on_hand, reorder_threshold, is low).
# Duplicated rather than imported so a later edit to the unit tier's table
# cannot silently redefine what THIS tier considers correct.
#
# What the duplication does not buy, said plainly because the obvious reading
# overstates it: these rows are a transcription, so an expected answer that was
# already wrong when it was copied is wrong in both tiers, and one author
# adding a row to both files in a single sitting defeats the separation
# outright. It guards against DRIFT -- one table edited later, alone -- not
# against a shared mistake. The claim that the two ENCODINGS agree is not
# resting on this table either: `test_the_expression_agrees_with_the_getter_
# row_for_row` below compares the implementations against each other directly
# and never reads it.
_ROWS = [
    # The threshold branch alone, with the status the column defaults to.
    ('EFFL0W0001', 'unknown', 2, 3, True),       # below
    ('EFFL0W0002', 'unknown', 3, 3, True),       # at -- the comparison is `<=`
    ('EFFL0W0003', 'unknown', 4, 3, False),      # above
    ('EFFL0W0004', 'unknown', 0, 0, True),       # a zero threshold IS one
    ('EFFL0W0005', 'unknown', 1, 0, False),
    ('EFFL0W0006', 'unknown', 0, None, False),   # no threshold (FR30)
    ('EFFL0W0007', 'unknown', None, 3, False),   # untracked: nothing to compare
    ('EFFL0W0008', 'unknown', None, None, False),

    # Story 5.3's manual branch, standing entirely on its own: no count and no
    # threshold, so nothing but `stock_status IN (…)` can make these true. These
    # are also the rows that would vanish from the negation below if the column
    # were ever made nullable and a row arrived with a NULL in it.
    ('EFFL0W0009', 'low', None, None, True),
    ('EFFL0W0010', 'out', None, None, True),
    ('EFFL0W0011', 'ok', None, None, False),
    # The two branches disagreeing, in both directions. `ok` does not suppress a
    # crossed threshold and `low` does not need one (FR30, AD-6).
    ('EFFL0W0012', 'low', 9, 3, True),
    ('EFFL0W0013', 'ok', 2, 3, True),
    ('EFFL0W0014', 'ok', 9, 3, False),
    ('EFFL0W0015', 'out', 9, None, True),
]

_LOW = {internal_id for internal_id, _, _, _, low in _ROWS if low}
_NOT_LOW = {internal_id for internal_id, _, _, _, low in _ROWS if not low}

# Spellings of `low` that are NOT the stored one, seeded the way the fixture
# below seeds states the write contract will not produce. Every one of these is
# a distinct string from `'low'` in Python, so the getter's frozenset
# membership is False for all of them -- and under the collation `products`
# would otherwise inherit (utf8mb4_unicode_ci, which folds case AND accents)
# the SQL `IN ('low','out')` is TRUE for all of them. That is a row-for-row
# disagreement between the two encodings AD-6 requires to agree, and this is
# the only tier that can see it: SQLite compares binary whatever the schema
# says. The fix is the column's `utf8mb4_bin` pin.
#
# Kept OUT of `_ROWS` on purpose. `_ROWS` is the transcription of the unit
# tier's matrix and both tiers must keep agreeing about it; these rows exist to
# probe the SERVER's string comparison and have no unit-tier counterpart.
_FOLDED_SPELLINGS = (
    ('EFFL0WF001', 'LOW'),    # case
    ('EFFL0WF002', 'Low'),    # case again, the spelling the form's label uses
    ('EFFL0WF003', 'lòw'),  # accent -- utf8mb4_unicode_ci folds it too
)

# The one folded spelling the pin does NOT close, kept separate because it is a
# known boundary rather than a covered case. See the test at the bottom of this
# module.
_PADDED_SPELLING = ('EFFL0WF004', 'low ')


@pytest.fixture
def seeded(integration_catalog_service):
    """Every matrix row committed to the live database.

    Written through the ORM rather than the service so a row can hold a state
    the write contract will not produce (a threshold on an untracked product):
    the predicate has to answer for whatever is in the table, including rows a
    restore or a hand-run UPDATE left there.
    """
    session = integration_catalog_service.Session()
    try:
        session.add_all([
            Product(internal_id=internal_id, description=internal_id,
                    stock_status=status,
                    quantity_on_hand=quantity, reorder_threshold=threshold)
            for internal_id, status, quantity, threshold, _ in _ROWS
        ])
        session.commit()
    finally:
        session.close()
    return integration_catalog_service


@pytest.mark.integration
class TestTheEffectiveLowExpressionOnMariaDB:

    def _internal_ids(self, service, criterion):
        session = service.Session()
        try:
            return {p.internal_id
                    for p in session.query(Product).filter(criterion).all()}
        finally:
            session.close()

    def test_the_where_clause_selects_exactly_the_low_rows(self, seeded):
        assert self._internal_ids(seeded, Product.is_effective_low) == _LOW

    def test_the_negation_selects_exactly_the_rest(self, seeded):
        """The half that a NULL-returning expression would fail silently.

        Without the leading `IS NOT NULL` guards the comparison is NULL for
        every untracked or threshold-less row; `WHERE NULL` drops it, and so
        does `WHERE NOT NULL` -- so the rows would be absent from BOTH results
        and the positive test above would still pass.

        Since Story 5.3 the same sentence is true of the status branch, with a
        different guard: `VARCHAR IN (…)` against a NOT NULL column is
        two-valued, and against a nullable one it is not. That guard lives in
        the schema this tier actually migrated, which is why this assertion is
        worth running here and not only on SQLite.
        """
        assert self._internal_ids(seeded, ~Product.is_effective_low) == _NOT_LOW

    def test_the_two_halves_partition_the_table(self, seeded):
        """Stated as a partition because that is the property Story 5.6 and
        Epic 8 will rely on: every product is on exactly one side."""
        low = self._internal_ids(seeded, Product.is_effective_low)
        not_low = self._internal_ids(seeded, ~Product.is_effective_low)
        assert low & not_low == set()
        assert low | not_low == {internal_id
                                 for internal_id, _, _, _, _ in _ROWS}

    def test_the_expression_agrees_with_the_getter_row_for_row(self, seeded):
        """AD-6's single-sourcing is a claim about AGREEMENT, and the two
        encodings can only disagree where one of them runs -- here."""
        low = self._internal_ids(seeded, Product.is_effective_low)
        session = seeded.Session()
        try:
            for product in session.query(Product).all():
                assert product.is_effective_low is (
                    product.internal_id in low), product.internal_id
        finally:
            session.close()

    def _seed_raw_status(self, service, internal_id, stored):
        """One product carrying a status string the write path would refuse.

        Through the raw ORM, like the `seeded` fixture above and for the same
        stated reason: the service will not produce this state, and the
        predicate has to answer for whatever is in the table. Its own session
        and its own row, so these never enter the partition assertions -- what
        is being probed is the SERVER's string comparison, not the matrix.
        """
        session = service.Session()
        try:
            session.add(Product(internal_id=internal_id, description=stored,
                                stock_status=stored))
            session.commit()
        finally:
            session.close()

    def _both_encodings(self, service, internal_id):
        """`(sql_says_low, python_says_low)` for one seeded row."""
        session = service.Session()
        try:
            product = session.query(Product).filter(
                Product.internal_id == internal_id).one()
            sql_low = internal_id in {
                p.internal_id for p in session.query(Product)
                .filter(Product.is_effective_low).all()}
            return sql_low, product.is_effective_low
        finally:
            session.close()

    @pytest.mark.parametrize('internal_id, stored', _FOLDED_SPELLINGS,
                             ids=['upper-case', 'title-case', 'accented'])
    def test_a_folded_spelling_of_low_reads_low_in_NEITHER_encoding(
            self, integration_catalog_service, internal_id, stored):
        """The collation half of the row-for-row agreement above.

        None of these is a stored status -- the write path refuses every one --
        but a hand-run UPDATE or a restored backup produces them, which is
        exactly the class of row every docstring around this predicate says it
        must answer for. Python's frozenset membership is False for each, and
        under the utf8mb4_unicode_ci `products` otherwise inherits the server's
        `IN ('low','out')` is TRUE for each: the two encodings disagreeing on
        the same row, silently, with only the SQL half wrong, and invisibly to
        both tiers' existing matrices because they seed only the four canonical
        spellings (and to SQLite, which compares binary regardless).

        `stock_status` is pinned `utf8mb4_bin` for that reason, and this
        asserts the CONSEQUENCE rather than the collation name -- the schema
        guards already compare names.
        """
        self._seed_raw_status(integration_catalog_service, internal_id, stored)

        sql_low, python_low = self._both_encodings(integration_catalog_service,
                                                   internal_id)
        assert python_low is False
        assert sql_low is False, (
            f'the SQL half matched {stored!r} as low where the Python getter '
            f'did not; products.stock_status is meant to be utf8mb4_bin')

    def test_a_trailing_space_is_the_folded_spelling_the_pin_does_NOT_close(
            self, integration_catalog_service):
        """The known remainder, pinned so it is a boundary and not a surprise.

        `utf8mb4_bin` is a PAD SPACE collation on MariaDB (verified on 11.8),
        so it closes case and accent folding and leaves trailing-space equality
        exactly where it was: `'low ' IN ('low','out')` is still TRUE on the
        server, while Python's frozenset membership is False. That is the same
        shape of disagreement as the cases above and it is deliberately not
        closed -- `utf8mb4_nopad_bin` would close it, at the cost of making
        `stock_status` the schema's only NO PAD column and splitting the one
        `utf8mb4_bin` pin every schema guard shares, for a spelling no writer
        produces and no restore realistically invents.

        Asserted rather than merely written down because the alternative is
        exactly the invisibility the pin exists to end. If this test ever
        FAILS, the collation changed: close the boundary in
        `app/database.py`'s column comment, in the migration's docstring and in
        `tests/integration/conftest.py` at the same time, and fold this row
        into the parametrized test above.
        """
        internal_id, stored = _PADDED_SPELLING
        self._seed_raw_status(integration_catalog_service, internal_id, stored)

        sql_low, python_low = self._both_encodings(integration_catalog_service,
                                                   internal_id)
        assert python_low is False
        assert sql_low is True, (
            'the SQL half no longer matches a trailing-space spelling -- the '
            'collation on products.stock_status changed; see this docstring')
