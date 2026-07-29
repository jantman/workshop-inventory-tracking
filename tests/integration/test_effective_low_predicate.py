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

What is deliberately NOT re-tested here: the Python getter (no database in it)
and the write contract (SQLite arbitrates it identically).
"""

import pytest

from app.database import Product

# The same rows as the unit tier's `_EFFECTIVE_LOW_MATRIX`, kept as
# (internal_id, quantity_on_hand, reorder_threshold, is low). Duplicated rather
# than imported so a later edit to the unit tier's table cannot silently
# redefine what THIS tier considers correct.
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
    ('EFFL0W0001', 2, 3, True),       # below
    ('EFFL0W0002', 3, 3, True),       # at -- the comparison is `<=`
    ('EFFL0W0003', 4, 3, False),      # above
    ('EFFL0W0004', 0, 0, True),       # a zero threshold is a threshold
    ('EFFL0W0005', 1, 0, False),
    ('EFFL0W0006', 0, None, False),   # no threshold: the branch is false (FR30)
    ('EFFL0W0007', None, 3, False),   # untracked: nothing to compare
    ('EFFL0W0008', None, None, False),
]

_LOW = {internal_id for internal_id, _, _, low in _ROWS if low}
_NOT_LOW = {internal_id for internal_id, _, _, low in _ROWS if not low}


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
                    quantity_on_hand=quantity, reorder_threshold=threshold)
            for internal_id, quantity, threshold, _ in _ROWS
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
        """
        assert self._internal_ids(seeded, ~Product.is_effective_low) == _NOT_LOW

    def test_the_two_halves_partition_the_table(self, seeded):
        """Stated as a partition because that is the property Story 5.6 and
        Epic 8 will rely on: every product is on exactly one side."""
        low = self._internal_ids(seeded, Product.is_effective_low)
        not_low = self._internal_ids(seeded, ~Product.is_effective_low)
        assert low & not_low == set()
        assert low | not_low == {internal_id for internal_id, _, _, _ in _ROWS}

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
