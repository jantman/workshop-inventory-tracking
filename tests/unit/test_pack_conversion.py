"""Packs recorded as units, and what a pack was kept (feature 046, issue #137).

An Amazon order line states how many *of the listing* were bought and what one
of the listing cost. When the listing is a pack of 100 screws, both numbers are
packs -- and the catalog records individual items. Capturing the reported order
recorded one item at the price of a whole pack.

Two contracts are exercised here, and the file is organised by them:

* ``contracts/pack-conversion.md`` -- the arithmetic (§1), and the rule that
  decides whether a submitted number follows the pack size or overrides it (§2).
* ``contracts/purchase-pack-fields.md`` -- what the two new columns mean, and
  the invariants every writer has to hold (§2).

The arithmetic is ``Decimal`` throughout (Constitution III). A test that builds
a price from a float would pass while proving the opposite of what it claims.
"""

import json
import re
from decimal import Decimal

import pytest

from app.catalog_service import (
    AMAZON_ORDER_VENDOR,
    AMAZON_VENDOR,
    CatalogService,
    _amazon_line_fields,
)
from app.exceptions import ValidationError
from app.models import (
    AMAZON_PAYLOAD_VENDOR,
    AMAZON_PAYLOAD_VERSION,
    AmazonOrder,
    AmazonOrderLine,
    McMasterOrderLine,
    pack_size_from_title,
)

pytestmark = pytest.mark.unit

# The order from issue #137 -- four lines, every one a multi-item pack.
ORDER_NUMBER = '111-1533738-5610601'


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


def build_order(lines=None, **overrides):
    """One Amazon order payload. The shape ``test_amazon_capture`` uses."""
    body = {
        'version': AMAZON_PAYLOAD_VERSION,
        'vendor': AMAZON_PAYLOAD_VENDOR,
        'order_number': ORDER_NUMBER,
        'order_date': 'September 19, 2026',
        'source_url': 'https://www.amazon.com/your-orders/order-details'
                      '?orderID=' + ORDER_NUMBER,
        'lines': lines if lines is not None else [
            {'asin': 'B0PACK100', 'title': 'Widget Screws (Pack of 100)',
             'quantity': 1, 'unit_price': '13.23'},
        ],
    }
    body.update(overrides)
    return AmazonOrder.from_payload(body)


def line(**kwargs):
    """An Amazon line with the pack fields set directly."""
    return AmazonOrderLine(asin='B0X', title='thing', **kwargs)


# ---------------------------------------------------------------------------
# contracts/pack-conversion.md §1 -- the arithmetic
# ---------------------------------------------------------------------------

# The worked table from the contract, verbatim. Every row is a case the review
# can actually produce; none is invented to fill the table out.
WORKED = [
    # packs, pack_size, pack_price,     quantity, unit_price, rounds
    (1,      None,      Decimal('13.23'), 1,   Decimal('13.23'), False),
    (1,      100,       Decimal('13.23'), 100, Decimal('0.13'),  True),
    (2,      100,       Decimal('13.23'), 200, Decimal('0.13'),  True),
    (2,      100,       Decimal('6.66'),  200, Decimal('0.07'),  True),
    (1,      10000,     Decimal('4.99'),  10000, Decimal('0.00'), True),
    (1,      3,         Decimal('17.99'), 3,   Decimal('6.00'),  True),
]


@pytest.mark.parametrize('packs,pack_size,pack_price,quantity,unit_price,rounds', WORKED)
def test_the_worked_table(packs, pack_size, pack_price, quantity, unit_price, rounds):
    got = line(packs=packs, pack_size=pack_size, pack_price=pack_price)
    assert got.quantity == quantity
    assert got.unit_price == unit_price
    assert got.price_rounds is rounds


def test_a_pack_size_never_invents_a_quantity():
    """C3, FR-009. An unread quantity stays unread however big the pack is."""
    assert line(packs=None, pack_size=100, pack_price=Decimal('13.23')).quantity is None


def test_a_pack_size_never_invents_a_price():
    """C3, FR-009. The same, in the other direction."""
    got = line(packs=1, pack_size=100, pack_price=None)
    assert got.quantity == 100
    assert got.unit_price is None


def test_a_pack_of_one_is_the_identity():
    """C4, FR-002. What a review nobody touched must still record."""
    stated = line(packs=3, pack_size=None, pack_price=Decimal('4.50'))
    explicit_one = line(packs=3, pack_size=1, pack_price=Decimal('4.50'))
    assert stated.quantity == explicit_one.quantity == 3
    assert stated.unit_price == explicit_one.unit_price == Decimal('4.50')
    assert stated.price_rounds is explicit_one.price_rounds is False


def test_a_price_that_divides_evenly_does_not_warn():
    """The negative half of FR-008 -- the warning has to mean something."""
    assert line(packs=1, pack_size=100, pack_price=Decimal('12.00')).price_rounds is False


def test_the_zero_cent_unit_price_is_a_value_not_a_refusal():
    """A pack of 10,000 washers is legitimate and its unit price is $0.00."""
    got = line(packs=1, pack_size=10000, pack_price=Decimal('4.99'))
    assert got.unit_price == Decimal('0.00')
    assert got.price_rounds is True


def test_mcmaster_uses_the_same_arithmetic():
    """The mixin is shared, so McMaster's line must not have moved (FR-039)."""
    got = McMasterOrderLine(part_number='91290A115', packs=2, pack_size=100,
                            pack_price=Decimal('6.66'))
    assert (got.quantity, got.unit_price, got.price_rounds) == (200, Decimal('0.07'), True)


def test_the_division_is_never_a_float():
    """Constitution III. A float reaching the arithmetic is the whole risk."""
    got = line(packs=1, pack_size=3, pack_price=Decimal('17.99'))
    assert isinstance(got.exact_unit_price, Decimal)
    assert isinstance(got.unit_price, Decimal)


# ---------------------------------------------------------------------------
# contracts/pack-conversion.md §2 -- override detection
# ---------------------------------------------------------------------------
#
# The rule: a value the operator did not change follows the pack size; a value
# they changed wins. These tests are the reason the rule exists -- without it a
# pack size entered with JavaScript disabled records the wrong number silently.


def decisions_for(order, **fields):
    return {ln.form_key: dict({'include': True}, **fields) for ln in order.lines}


def unsuggested_order():
    """An order whose title names no pack, so the review renders a pack of 1.

    Deliberately not the default order: that one's title says "Pack of 100",
    so the review has already drawn 100 and a submitted 1 is a real override.
    Override detection is only interesting where the rendered value is 1.
    """
    return build_order(lines=[
        {'asin': 'B0QUIET', 'title': 'Widget Screws, Stainless',
         'quantity': 1, 'unit_price': '13.23'},
    ])


def test_untouched_quantity_follows_the_pack_size(catalog):
    """§2 row 1, without JavaScript.

    The operator typed a pack size and the browser did not rewrite the
    quantity input, so it still holds the rendered 1. **Recording that 1 is
    the defect this feature exists to fix**, arriving through the back door.
    """
    ln = unsuggested_order().lines[0]
    got = _amazon_line_fields(
        catalog, ln,
        {'include': True, 'pack_size': '100', 'quantity': '1', 'unit_price': '13.23'},
    )
    assert got['quantity'] == 100
    assert got['unit_price'] == Decimal('0.13')


def test_a_submitted_value_matching_a_suggestion_is_not_an_override(catalog):
    """The same rule where the review pre-filled the pack size itself.

    The title says "Pack of 100", so the review drew 100 items at 0.13 and the
    form comes back holding exactly that. Nothing was overridden.
    """
    got = _amazon_line_fields(
        catalog, build_order().lines[0],
        {'include': True, 'pack_size': '100', 'quantity': '100', 'unit_price': '0.13'},
    )
    assert got['quantity'] == 100
    assert got['unit_price'] == Decimal('0.13')


def test_overriding_a_suggested_line_still_wins(catalog):
    """And the operator can still disagree with a suggestion's arithmetic."""
    got = _amazon_line_fields(
        catalog, build_order().lines[0],
        {'include': True, 'pack_size': '100', 'quantity': '96', 'unit_price': '0.13'},
    )
    assert got['quantity'] == 96


def test_a_javascript_converted_submission_reaches_the_same_answer(catalog):
    """§2 row 1, with JavaScript. The inputs already hold the converted pair.

    The same submission as the no-JavaScript case above reaches the same
    number by the other branch, which is the property that keeps the script an
    ergonomic aid rather than part of the write path.
    """
    ln = unsuggested_order().lines[0]
    got = _amazon_line_fields(
        catalog, ln, {'include': True, 'pack_size': '100', 'quantity': '100', 'unit_price': '0.13'},
    )
    assert got['quantity'] == 100
    assert got['unit_price'] == Decimal('0.13')


def test_a_typed_quantity_wins_over_the_pack_size(catalog):
    """§2 row 2, FR-007. The operator can see the box; this code cannot."""
    got = _amazon_line_fields(
        catalog, unsuggested_order().lines[0],
        {'include': True, 'pack_size': '100', 'quantity': '90', 'unit_price': '0.13'},
    )
    assert got['quantity'] == 90


def test_a_typed_price_wins_over_the_pack_size(catalog):
    got = _amazon_line_fields(
        catalog, unsuggested_order().lines[0],
        {'include': True, 'pack_size': '100', 'quantity': '100', 'unit_price': '0.15'},
    )
    assert got['unit_price'] == Decimal('0.15')


def test_touching_nothing_records_what_the_order_stated(catalog):
    """§2 row 3, FR-002, SC-005. The change costs nothing when unused."""
    order = build_order(lines=[
        {'asin': 'B0PLAIN', 'title': 'Digital Calipers', 'quantity': 2,
         'unit_price': '9.99'},
    ])
    got = _amazon_line_fields(
        catalog, order.lines[0],
        {'include': True, 'pack_size': '1', 'quantity': '2', 'unit_price': '9.99'},
    )
    assert got['quantity'] == 2
    assert got['unit_price'] == Decimal('9.99')


def test_an_absent_pack_field_is_an_older_form(catalog):
    """A form posted without the field behaves as it did before this feature."""
    order = build_order(lines=[
        {'asin': 'B0PLAIN', 'title': 'Digital Calipers', 'quantity': 2,
         'unit_price': '9.99'},
    ])
    got = _amazon_line_fields(
        catalog, order.lines[0], {'include': True, 'quantity': '2', 'unit_price': '9.99'},
    )
    assert got['quantity'] == 2
    assert got['unit_price'] == Decimal('9.99')


# ---------------------------------------------------------------------------
# Refusals -- FR-011, FR-013
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('bad', ['0', '-1', '1.5', 'many', '-100'])
def test_a_bad_pack_size_is_refused_and_never_coerced(catalog, bad):
    order = unsuggested_order()
    with pytest.raises(ValidationError) as excinfo:
        _amazon_line_fields(
            catalog, order.lines[0],
            {'include': True, 'pack_size': bad, 'quantity': '1', 'unit_price': '13.23'},
        )
    # The message has to name the line: a fifteen-line order refused without
    # saying which line is a page the operator cannot act on.
    assert order.lines[0].form_key in excinfo.value.field


def test_clearing_a_suggested_pack_size_removes_the_pack(catalog):
    """FR-021. Clearing the field is how you refuse a guess.

    The review renders the suggestion pre-filled, so a blank coming back is
    the operator saying "this is not a pack". Falling back to the suggestion
    here would put it straight back with no way to overrule it -- and it would
    then be *stored*, because a pack is kept now.
    """
    got = _amazon_line_fields(
        catalog, build_order().lines[0],
        {'include': True, 'pack_size': '', 'quantity': '1', 'unit_price': '13.23'},
    )
    assert got['quantity'] == 1
    assert got['unit_price'] == Decimal('13.23')
    assert got['pack_size'] is None


def test_a_blank_pack_size_is_not_a_refusal(catalog):
    """Blank is "no pack", which is the default, not an error."""
    order = unsuggested_order()
    got = _amazon_line_fields(
        catalog, order.lines[0],
        {'include': True, 'pack_size': '', 'quantity': '1', 'unit_price': '13.23'},
    )
    assert got['quantity'] == 1


def test_a_refused_pack_size_writes_nothing_for_any_line(catalog):
    """FR-013. An order is answered whole; half an order is worse than none."""
    order = build_order(lines=[
        {'asin': 'B0GOOD', 'title': 'Digital Calipers', 'quantity': 1,
         'unit_price': '9.99'},
        {'asin': 'B0PACK100', 'title': 'Widget Screws (Pack of 100)',
         'quantity': 1, 'unit_price': '13.23'},
    ])
    decisions = decisions_for(order)
    decisions[order.lines[1].form_key]['pack_size'] = '0'

    with pytest.raises(ValidationError):
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, decisions)

    # Not "the bad line was skipped" -- nothing at all.
    assert catalog.search_products() == []


# ---------------------------------------------------------------------------
# pack_size_from_title -- FR-019, FR-022
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('title,expected', [
    ('Widget Screws (Pack of 100)', 100),
    ('Widget Screws, Packs of 50', 50),
    ('M3 Standoffs 5 Pack', 5),
    ('M3 Standoffs 5-Pack', 5),
    ('Assorted Washers 10 Pk', 10),
    ('Resistor Kit 600 Pcs', 600),
    ('Resistor Kit 600 pieces', 600),
    ('Heat Shrink 120 pc', 120),
    ('Cable Ties 250 ct', 250),
    ('Cable Ties 250 count', 250),
    ('Hex Keys Set of 9', 9),
    ('Drill Bits Box of 29', 29),
    ('Anchors Bag of 40', 40),
    ('WIDGET SCREWS (PACK OF 100)', 100),
])
def test_a_pack_count_is_read_from_the_title(title, expected):
    assert pack_size_from_title(title) == expected


@pytest.mark.parametrize('title', [
    # A bare number is never a pack count. These are the titles that make a
    # naive parse dangerous, and every one of them is an ordinary Amazon title.
    'M3 x 12mm Socket Head Cap Screws',
    '12V 5A Power Supply',
    '1/4-20 Threaded Rod',
    'Digital Calipers 0-6 Inch',
    'MEAN WELL IRM-05-5',
    '',
    # A pack of one is not a pack, and a pack of none is nothing.
    'Widget (Pack of 1)',
    'Widget (Pack of 0)',
    # Two different counts: no basis for choosing, so no suggestion.
    'Screws Pack of 100 and Nuts Pack of 50',
])
def test_what_must_not_be_read_as_a_pack_count(title):
    assert pack_size_from_title(title) is None


def test_the_same_count_twice_is_still_read():
    """Two mentions agreeing is not ambiguity -- only disagreement is."""
    assert pack_size_from_title('Pack of 100 Screws, 100 Pcs') == 100


def test_the_parse_is_pure():
    """Override detection reconstructs what was rendered from it (research R3).

    A suggestion that varied between render and submit would misclassify an
    override as an untouched field, so this has to be a function of its
    argument and nothing else.
    """
    assert pack_size_from_title('Pack of 100') == pack_size_from_title('Pack of 100')


# ---------------------------------------------------------------------------
# contracts/purchase-pack-fields.md §2 -- the stored invariants
# ---------------------------------------------------------------------------


def test_a_pack_line_stores_the_vendors_line(catalog):
    """FR-028, FR-029. What the vendor charged, so the invoice reconciles."""
    order = build_order()
    decisions = decisions_for(order, pack_size='100', quantity='100', unit_price='0.13')
    catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, decisions)

    purchase = catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)[0]
    assert purchase.quantity == 100
    assert purchase.unit_price == Decimal('0.13')
    assert purchase.pack_size == 100
    assert purchase.pack_price == Decimal('13.23')


def test_a_pack_of_one_stores_null_and_not_one(catalog):
    """P2, FR-031. "Nothing was stated" and "a pack of one" must stay distinct."""
    order = build_order(lines=[
        {'asin': 'B0PLAIN', 'title': 'Digital Calipers', 'quantity': 1,
         'unit_price': '9.99'},
    ])
    catalog.capture_order_lines(
        order, AMAZON_ORDER_VENDOR, decisions_for(order, pack_size='1'),
    )

    purchase = catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)[0]
    assert purchase.pack_size is None
    assert purchase.pack_price is None


def test_a_hand_recorded_purchase_states_no_pack(catalog):
    """P5. Nothing may be inferred for a purchase nobody captured."""
    product = catalog.create_product(description='Shop Rag')
    purchase = catalog.record_purchase(
        product.id, vendor='Hardware Store', quantity=12, unit_price='0.99',
    )
    assert purchase.pack_size is None
    assert purchase.pack_price is None


def test_the_stored_pack_price_is_a_decimal(catalog):
    """P4, Constitution III. Never a float, never a raw string."""
    order = build_order()
    catalog.capture_order_lines(
        order, AMAZON_ORDER_VENDOR,
        decisions_for(order, pack_size='100', quantity='100', unit_price='0.13'),
    )
    purchase = catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)[0]
    assert isinstance(purchase.pack_price, Decimal)


def test_the_unit_price_cannot_be_multiplied_back_to_the_pack_price(catalog):
    """Why pack_price is a column at all (research R5).

    This is the measurement behind the schema change: the rounding the feature
    performs destroys the invoice figure, so nothing short of storing it
    recovers what the card was charged.
    """
    order = build_order()
    catalog.capture_order_lines(
        order, AMAZON_ORDER_VENDOR,
        decisions_for(order, pack_size='100', quantity='100', unit_price='0.13'),
    )
    purchase = catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)[0]
    assert purchase.unit_price * purchase.pack_size == Decimal('13.00')
    assert purchase.pack_price == Decimal('13.23')


# ---------------------------------------------------------------------------
# The other two vendors -- FR-030, FR-039, FR-040
# ---------------------------------------------------------------------------


def test_mcmaster_now_keeps_the_pack_it_converted(catalog):
    """FR-030. It converted correctly and threw the pack away until 046."""
    from app.catalog_service import MCMASTER_ORDER_VENDOR, _mcmaster_line_fields

    got = _mcmaster_line_fields(
        catalog,
        McMasterOrderLine(part_number='91290A115', packs=2, pack_size=100,
                          pack_price=Decimal('6.66'), line_number=1),
        {'include': True},
    )
    assert got['quantity'] == 200
    assert got['unit_price'] == Decimal('0.07')
    assert got['pack_size'] == 100
    assert got['pack_price'] == Decimal('6.66')
    assert MCMASTER_ORDER_VENDOR.name == 'McMaster-Carr'


def test_mcmaster_pairs_state_no_count_and_store_no_pack(catalog):
    """A "Pair" is plainly not one item, and McMaster states no count for it.

    Recording a silent 2 would be inventing data (028 FR-037), so the honest
    record is no pack at all -- which is also what keeps the stored column
    meaning "the vendor said so".
    """
    from app.catalog_service import _mcmaster_line_fields

    got = _mcmaster_line_fields(
        catalog,
        McMasterOrderLine(part_number='91290A115', packs=3, pack_size=None,
                          pack_price=Decimal('4.50'), line_number=1),
        {'include': True},
    )
    assert got['quantity'] == 3
    assert got['pack_size'] is None
    assert got['pack_price'] is None


def test_digikey_states_no_pack_at_all(catalog):
    """FR-040. Its quantities come from a service already in items."""
    from app.catalog_service import _digikey_line_fields
    from app.models import DigiKeyOrderLine

    got = _digikey_line_fields(
        catalog,
        DigiKeyOrderLine(digikey_part_number='296-1234-ND', quantity=10,
                         unit_price=Decimal('0.42')),
        {'include': True},
    )
    assert 'pack_size' not in got
    assert 'pack_price' not in got


# ---------------------------------------------------------------------------
# research R7 -- amending a purchase leaves the vendor's line alone
# ---------------------------------------------------------------------------


def test_receiving_a_short_delivery_leaves_the_pack_alone(catalog):
    """A pack of 100 ordered and 90 received is a true row, not a conflict.

    The two pairs answer different questions: what the vendor charged, and
    what the catalog holds. Forcing them to agree would either destroy the
    invoice record or refuse a legitimate short delivery.
    """
    order = build_order()
    catalog.capture_order_lines(
        order, AMAZON_ORDER_VENDOR,
        decisions_for(order, pack_size='100', quantity='100', unit_price='0.13'),
    )
    purchase = catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)[0]

    catalog.receive_purchase(purchase.id, quantity=90)

    after = catalog.get_purchase(purchase.id)
    assert after.quantity == 90
    assert after.pack_size == 100
    assert after.pack_price == Decimal('13.23')


# ---------------------------------------------------------------------------
# Clearing a suggestion has to survive a re-render (PR #161 review)
# ---------------------------------------------------------------------------
#
# The payload is re-parsed on **every** render, and `from_payload` reapplies
# the title suggestion each time -- so the suggestion is always there waiting
# to come back. Only the submitted value can say the operator refused it, and
# a cleared field submits '', which Jinja's `or` treats as "nothing
# submitted". A line the operator had said is *not* a pack therefore became
# one again the moment some other line failed validation.


ORDER_JSON = json.dumps({
    'version': AMAZON_PAYLOAD_VERSION,
    'vendor': AMAZON_PAYLOAD_VENDOR,
    'order_number': ORDER_NUMBER,
    'order_date': 'September 19, 2026',
    'source_url': 'https://www.amazon.com/your-orders/order-details',
    'lines': [
        # Its title names a count, so the review pre-fills 100 and marks it a
        # guess. This is the line the operator clears.
        {'asin': 'B0PACK100', 'title': 'Widget Screws (Pack of 100)',
         'quantity': 1, 'unit_price': '13.23'},
        # A second line, so something else can fail and force the re-render.
        {'asin': 'B0OTHER', 'title': 'Digital Calipers',
         'quantity': 1, 'unit_price': '9.99'},
    ],
})


def confirm_post(client, **fields):
    data = {'order': ORDER_JSON, 'include[1]': 'on', 'include[2]': 'on'}
    data.update(fields)
    return client.post('/products/amazon/orders/capture', data=data)


def pack_field_value(html, key):
    """The value the re-rendered pack input carries for one line."""
    row = re.search(
        r'name="pack_size\[' + re.escape(key) + r'\]"[^>]*?value="([^"]*)"',
        html, re.S,
    )
    assert row is not None, f'no pack_size input for line {key}'
    return row.group(1)


def test_clearing_a_suggestion_survives_another_lines_refusal(client):
    """The reported regression. Line 2's bad pack must not restore line 1's.

    Without the fix the operator's cleared field comes back reading "100",
    with the "read from the title" marker back too -- and because that is also
    what override detection reconstructs as "the rendered value", a second
    submission records 100 items rather than the one they intended.
    """
    response = confirm_post(
        client,
        **{'pack_size[1]': '', 'quantity[1]': '1', 'unit_price[1]': '13.23',
           # Refused, which is what forces the re-render.
           'pack_size[2]': '0', 'quantity[2]': '1', 'unit_price[2]': '9.99'},
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert pack_field_value(html, '1') == ''


def test_a_cleared_suggestion_loses_its_guess_marker(client):
    """The marker follows the value. A field the operator emptied is theirs."""
    response = confirm_post(
        client,
        **{'pack_size[1]': '', 'quantity[1]': '1', 'unit_price[1]': '13.23',
           'pack_size[2]': '0', 'quantity[2]': '1', 'unit_price[2]': '9.99'},
    )

    html = response.get_data(as_text=True)
    # Exactly one line still carries a suggestion -- line 2, untouched. The
    # count is the assertion: "not present at all" would also pass against a
    # page that failed to render its rows.
    assert html.count('pack-size-suggested') == 0


def test_a_fresh_render_still_offers_the_suggestion(client):
    """The other half. `is not none` must not defeat the pre-fill itself."""
    response = confirm_post(
        client,
        **{'pack_size[1]': '100', 'quantity[1]': '100', 'unit_price[1]': '0.13',
           'pack_size[2]': '0', 'quantity[2]': '1', 'unit_price[2]': '9.99'},
    )

    html = response.get_data(as_text=True)
    assert pack_field_value(html, '1') == '100'


def test_a_corrected_suggestion_survives_the_refusal(client):
    """A value the operator typed over the guess comes back as theirs."""
    response = confirm_post(
        client,
        **{'pack_size[1]': '10', 'quantity[1]': '10', 'unit_price[1]': '1.32',
           'pack_size[2]': '0', 'quantity[2]': '1', 'unit_price[2]': '9.99'},
    )

    html = response.get_data(as_text=True)
    assert pack_field_value(html, '1') == '10'
