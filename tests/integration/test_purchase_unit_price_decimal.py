"""
``_purchase_unit_price``'s return value against a real ``DECIMAL(10, 2)`` column.

The unit tier reads its purchases back through SQLite, which stores
``Numeric(10, 2)`` as a float and rebuilds it with ``'%.2f'``. Everything is
normalized on the way out of that column, whatever shape went in, so no unit
test can answer the question this rule exists for: does the value the helper
hands to ``record_purchase`` reach MariaDB as a literal the column takes?

It is the *spelling* of the ``Decimal`` and not its value that decides. PyMySQL
renders a ``Decimal`` parameter with ``str()``, and ``Decimal`` keeps spellings
that are not decimal literals at all: ``str(Decimal('1E+7'))`` is ``'1E+7'``,
``str(Decimal('-0'))`` is ``'-0'``, and
``str(Decimal('0.00E-99999999999999999'))`` is ``'0E-100000000000000001'``. All
three were accepted by the route and handed to the driver as typed before
``_purchase_unit_price`` began returning its quantized result, and they did NOT
fare alike: MariaDB reads ``'-0'`` and ``'1E+7'`` (the latter as an
approximate-value literal) and stores the right number, but refuses
``'0E-100000000000000001'`` outright -- ``record_purchase`` swallowed the error
into None, and each caller then said so in its own words ("Failed to record the
purchase" on the purchase form, a 500 on the JSON endpoint, "its first receipt
was not recorded" on the create form), none of them naming a field, over a price
the form had just accepted.

So this file is not asserting that every un-normalized spelling used to fail. It
is asserting the thing that makes the difference stop mattering: whatever
spelling was typed, what reaches the column is one two-place ``Decimal``, the
column takes it, and it comes back as the number meant. The comparison is on
``str()`` rather than ``==`` for the reason it is on ``str()`` in the unit tier
too -- every spelling of a number compares equal to the number, so ``==`` cannot
state the claim being made.
"""

import pytest

from app.main.routes import _purchase_unit_price

# ``(raw spelling, the string the column must hand back)``. The same values the
# unit tier's ``_UNIT_PRICE_VERDICTS`` accepts, restricted to the ones whose
# point is the STORAGE rather than the acceptance: the three zeros that are
# spelled differently, the exponent form of a whole number, and the largest
# value eight digits hold -- which is here as the boundary the quantized result
# must not have grown past.
_ROUND_TRIP = [
    ('-0', '0.00'),
    ('0', '0.00'),
    ('0.00E-99999999999999999', '0.00'),
    ('1E+7', '10000000.00'),
    ('99999999.99', '99999999.99'),
]


class TestNormalizedUnitPriceRoundTripsThroughMariaDB:
    """One product, one purchase, one price, read back from InnoDB."""

    @pytest.mark.integration
    @pytest.mark.parametrize('raw, expected', _ROUND_TRIP)
    def test_the_column_takes_it_and_gives_it_back_unchanged(
            self, integration_catalog_service, raw, expected):
        price, message = _purchase_unit_price(raw)
        assert message is None, \
            f'{raw!r} was refused before it ever reached the column: {message}'

        pid = integration_catalog_service.create_product(
            description=f'Part priced {raw}')
        snapshot = integration_catalog_service.record_purchase(
            pid, unit_price=price)
        # `record_purchase` swallows every backend error into None -- which is
        # exactly how the un-normalized `'0E-100000000000000001'` used to lose a
        # receipt without saying why -- so this is the assertion that catches a
        # literal MariaDB refused. Without it the read below would find no rows
        # and blame the wrong thing.
        assert snapshot is not None, \
            f'the column refused {str(price)!r} (from {raw!r})'

        purchases = integration_catalog_service.get_purchases_for_product(pid)
        assert len(purchases) == 1
        assert str(purchases[0].unit_price) == expected
