"""
E2E tests for the product form's tri-state quantity, its location pair and its
reorder threshold (Stories 5.1/5.2, FR23/FR24/FR25/FR26/FR27/FR30).

Four claims here need a real browser and a real round trip to be worth anything.

The first is the RENDERING contract. FR23/FR24 do not merely ask that the column
distinguish three states; they ask that a reader can tell them apart at a
glance, which is a fact about the page, not about the row. So this walks one
product through all three — untracked, zero, N, and back to untracked — and
reads the literal text off the detail page each time. A unit test asserting on
the template context would pass on a page where `In stock: 0` never rendered.

The second is the RE-STAMP rule (FR25), which is the one claim a unit test can
only ever approximate. The reason key presence cannot mean "I counted it" is
that a BROWSER re-posts the pre-filled quantity on every save — so the honest
test is to let a real browser submit a real edit form with only the description
touched, and check that the displayed age did not move. The recount checkbox is
then exercised the same way: same form, nothing changed but the tick.

The third is that FR27's vocabulary really is BIDIRECTIONAL through the shared
autocomplete. The merge happens in the route, but the thing that makes it useful
is a dropdown appearing on a LATER form containing a value the operator typed on
an EARLIER one, and the wiring in between (the ids the auto-init list matches,
the endpoint the component calls, the merged response body) has no other place
it is exercised end to end.

The fourth is that the Effective-Low signal really is DERIVED (Story 5.2, FR30,
AD-6). Nothing stores it, so the only way to see whether it is right is to
change one of its inputs through the form and re-read the page: raise the count
past the threshold and the badge must be gone, clear the threshold and it must
be gone, never set a count and it must never appear. A stored flag would have
passed the first of those and failed the rest — which is exactly why the epic
forbids one.

Isolation note: ``tests/e2e/test_server.py``'s ``clear_test_data()`` truncates
``products`` and the inventory items, and ``live_server`` is function-scoped, so
every test — and every ``--reruns`` replay, which re-runs setup — starts from an
empty catalog. Each test still mints a run-unique location string and asserts
only positively (containment), in the style of
``tests/e2e/test_category_autocomplete.py``: "empty at setup" is not "empty
here", since by the time a test asserts, the catalog holds what that test wrote.
"""

import re
import uuid

import pytest
from playwright.sync_api import expect


def _unique_location(label):
    """A location string no other test (or rerun) can have created."""
    return f'E2Eloc-{label}-{uuid.uuid4().hex[:8]}'


def _backdate_stamp(live_server, product_id, days):
    """Age the product's `quantity_verified_at` by `days`, in the database.

    Written straight to the row on purpose. The service's whole contract is that
    a count is stamped NOW, so there is no supported way to assert one in the
    past — and "the age did not move" is only observable if the stored age is
    old enough for a re-stamp to change the rendered words. Everything else in
    this module goes through the browser.
    """
    from datetime import datetime, timedelta
    from sqlalchemy.orm import sessionmaker

    from app.database import Product

    Session = sessionmaker(bind=live_server.engine)
    session = Session()
    try:
        session.query(Product).filter(Product.id == int(product_id)).update(
            {'quantity_verified_at': datetime.now() - timedelta(days=days)})
        session.commit()
    finally:
        session.close()


def _add_product(page, live_server, description, **fields):
    """Fill and submit Add Product; return the new product's id from the URL."""
    page.goto(f'{live_server.url}/products/add')
    expect(page.locator('#description')).to_be_visible()
    page.locator('#description').fill(description)
    for field, value in fields.items():
        page.locator(f'#{field}').fill(value)
    page.locator('button[type="submit"]').click()
    expect(page).to_have_url(re.compile(r'/products/\d+$'), timeout=10000)
    return page.url.rstrip('/').rsplit('/', 1)[-1]


def _set_quantity(page, live_server, product_id, value):
    """Open the edit form, set Quantity On Hand to `value`, save."""
    _edit_stock_field(page, live_server, product_id, 'quantity_on_hand', value)


def _edit_stock_field(page, live_server, product_id, field, value):
    """Open the edit form, set one Stock & Location field, save.

    Everything else on the form is left exactly as it was rendered and re-posted
    by the browser, which is the point: these tests are about what a save does
    to the OTHER fields as much as to the one that was typed in.
    """
    page.goto(f'{live_server.url}/products/edit/{product_id}')
    expect(page.locator(f'#{field}')).to_be_visible()
    page.locator(f'#{field}').fill(value)
    page.locator('button[type="submit"]').click()
    expect(page).to_have_url(re.compile(rf'/products/{product_id}$'),
                             timeout=10000)


@pytest.mark.e2e
def test_the_three_quantity_states_render_distinctly(page, live_server):
    """Untracked -> 0 -> 4 -> untracked, read off the page at every step.

    The zero step is the one that matters most: it is the state a naive
    `{{ value or '—' }}` renders identically to "no value at all", which is
    exactly the confusion FR24 forbids.
    """
    product_id = _add_product(page, live_server, 'E2E stock walk')
    quantity = page.locator('#product-quantity')

    # Created through the ordinary form with nothing else filled in.
    expect(quantity).to_have_text(re.compile(r'^\s*Not tracked\s*$'))

    _set_quantity(page, live_server, product_id, '0')
    expect(quantity).to_contain_text('In stock: 0')
    expect(quantity).not_to_contain_text('Not tracked')
    # FR25: the age of the assertion is shown beside the count.
    expect(quantity).to_contain_text('counted just now')

    _set_quantity(page, live_server, product_id, '4')
    expect(quantity).to_contain_text('In stock: 4')
    expect(quantity).to_contain_text('counted just now')

    # Clearing the field is how the operator stops tracking, and the age goes
    # with the count — an age beside no number would describe a count nobody
    # made.
    _set_quantity(page, live_server, product_id, '')
    expect(quantity).to_have_text(re.compile(r'^\s*Not tracked\s*$'))
    expect(quantity).not_to_contain_text('counted')


@pytest.mark.e2e
def test_editing_another_field_does_not_reset_the_displayed_age(
        page, live_server):
    """THE defect the re-stamp rule exists to prevent, in a real browser.

    The edit form renders Quantity On Hand pre-filled, so submitting it — for
    any reason at all — re-posts the number. If that counted as an assertion,
    fixing a typo in the description would re-date a count taken three months
    ago and the page would claim a stale number was fresh. The count is aged in
    the database first, because "the age did not move" is only visible when the
    stored age is old enough to have words of its own.
    """
    product_id = _add_product(page, live_server, 'E2E stale count',
                             quantity_on_hand='4')
    _backdate_stamp(live_server, product_id, days=95)

    page.goto(f'{live_server.url}/products/{product_id}')
    quantity = page.locator('#product-quantity')
    expect(quantity).to_contain_text('counted 3 months ago')

    # An ordinary edit of an unrelated field. Nothing is typed into the quantity
    # box and the recount box is left alone; the browser submits both anyway.
    page.goto(f'{live_server.url}/products/edit/{product_id}')
    expect(page.locator('#quantity_on_hand')).to_have_value('4')
    expect(page.locator('#quantity_recounted')).not_to_be_checked()
    page.locator('#description').fill('E2E stale count (typo fixed)')
    page.locator('button[type="submit"]').click()
    expect(page).to_have_url(re.compile(rf'/products/{product_id}$'),
                             timeout=10000)

    expect(quantity).to_contain_text('In stock: 4')
    expect(quantity).to_contain_text('counted 3 months ago')
    expect(quantity).not_to_contain_text('just now')


@pytest.mark.e2e
def test_the_recount_checkbox_refreshes_the_verification_date(
        page, live_server):
    """The one assertion a value comparison cannot see: recounted, same number.

    Same form, same number, nothing changed but the tick — so this is exactly
    the submission the test above proves does NOT re-stamp, plus the checkbox.
    """
    product_id = _add_product(page, live_server, 'E2E recount',
                             quantity_on_hand='4')
    _backdate_stamp(live_server, product_id, days=95)

    page.goto(f'{live_server.url}/products/{product_id}')
    quantity = page.locator('#product-quantity')
    expect(quantity).to_contain_text('counted 3 months ago')

    page.goto(f'{live_server.url}/products/edit/{product_id}')
    page.locator('#quantity_recounted').check()
    page.locator('button[type="submit"]').click()
    expect(page).to_have_url(re.compile(rf'/products/{product_id}$'),
                             timeout=10000)

    expect(quantity).to_contain_text('In stock: 4')
    expect(quantity).to_contain_text('counted just now')


@pytest.mark.e2e
def test_the_recount_checkbox_is_not_on_the_add_form(page, live_server):
    """The deliberate parity exception, checked where it is visible: on a create
    there is no stored count to re-confirm, so the control would be a switch
    with nothing behind it."""
    page.goto(f'{live_server.url}/products/add')
    expect(page.locator('#quantity_on_hand')).to_be_visible()
    expect(page.locator('#quantity_recounted')).to_have_count(0)


@pytest.mark.e2e
def test_the_reorder_signal_appears_and_clears_as_its_inputs_move(
        page, live_server):
    """The Effective-Low signal walked across the threshold in both directions.

    Nothing stores it, so every step here is a re-derivation: set a threshold
    above the count and the badge appears, raise the count above the threshold
    and it goes, clear the threshold and it stays gone. A cached or stored flag
    would survive one of those and be caught by the next.
    """
    product_id = _add_product(page, live_server, 'E2E reorder walk',
                              quantity_on_hand='2')
    signal = page.locator('#product-effective-low')
    threshold = page.locator('#product-reorder-threshold')

    # No threshold yet: two on hand is not low, because nothing says what low is.
    expect(threshold).to_have_text(re.compile(r'^\s*—\s*$'))
    expect(signal).to_have_text(re.compile(r'^\s*—\s*$'))

    _edit_stock_field(page, live_server, product_id, 'reorder_threshold', '3')
    expect(threshold).to_have_text(re.compile(r'^\s*3\s*$'))
    expect(signal).to_contain_text('Low stock')

    # Restocked past the threshold. The count is the only thing that changed.
    _set_quantity(page, live_server, product_id, '4')
    expect(threshold).to_have_text(re.compile(r'^\s*3\s*$'))
    expect(signal).to_have_text(re.compile(r'^\s*—\s*$'))

    # Back below it, then the threshold itself is removed — which must clear the
    # signal even though the count did not move.
    _set_quantity(page, live_server, product_id, '2')
    expect(signal).to_contain_text('Low stock')
    _edit_stock_field(page, live_server, product_id, 'reorder_threshold', '')
    expect(threshold).to_have_text(re.compile(r'^\s*—\s*$'))
    expect(signal).to_have_text(re.compile(r'^\s*—\s*$'))


@pytest.mark.e2e
def test_an_untracked_product_with_a_threshold_never_signals(page,
                                                             live_server):
    """A threshold with no count to compare against says nothing (FR30).

    Worth a browser of its own because it is the state a naive implementation
    reads as "zero, therefore low": the quantity column is NULL, and a comparison
    that treats absent as empty would flag every product an operator has ever
    written a threshold on without committing to counting it.
    """
    product_id = _add_product(page, live_server, 'E2E rule without a count',
                              reorder_threshold='3')

    expect(page.locator('#product-quantity')).to_have_text(
        re.compile(r'^\s*Not tracked\s*$'))
    expect(page.locator('#product-reorder-threshold')).to_have_text(
        re.compile(r'^\s*3\s*$'))
    expect(page.locator('#product-effective-low')).to_have_text(
        re.compile(r'^\s*—\s*$'))

    # And it stays silent once a count that is comfortably above it arrives.
    _set_quantity(page, live_server, product_id, '9')
    expect(page.locator('#product-effective-low')).to_have_text(
        re.compile(r'^\s*—\s*$'))


@pytest.mark.e2e
def test_a_zero_threshold_survives_a_round_trip_through_the_edit_form(
        page, live_server):
    """`0` is a real threshold — "tell me the moment this runs out" — and the
    one value a falsy-zero bug anywhere on the path would silently discard.
    Saved, re-opened, and re-saved untouched, because the re-save is where a
    blank-rendered box would turn into "no threshold"."""
    product_id = _add_product(page, live_server, 'E2E zero threshold',
                              quantity_on_hand='1', reorder_threshold='0')
    expect(page.locator('#product-reorder-threshold')).to_have_text(
        re.compile(r'^\s*0\s*$'))
    expect(page.locator('#product-effective-low')).to_have_text(
        re.compile(r'^\s*—\s*$'))

    page.goto(f'{live_server.url}/products/edit/{product_id}')
    expect(page.locator('#reorder_threshold')).to_have_value('0')
    page.locator('button[type="submit"]').click()
    expect(page).to_have_url(re.compile(rf'/products/{product_id}$'),
                             timeout=10000)
    expect(page.locator('#product-reorder-threshold')).to_have_text(
        re.compile(r'^\s*0\s*$'))

    # And it signals exactly when the shelf is empty, not before.
    _set_quantity(page, live_server, product_id, '0')
    expect(page.locator('#product-effective-low')).to_contain_text('Low stock')


@pytest.mark.e2e
def test_a_product_location_is_offered_on_a_later_product_form(
        page, live_server):
    """FR27, product -> product: a location typed on one product form is in the
    dropdown on the next one, which is the whole point of feeding the shared
    vocabulary from the products table as well."""
    location = _unique_location('prod')
    _add_product(page, live_server, 'E2E location seed', location=location)

    page.goto(f'{live_server.url}/products/add')
    expect(page.locator('#location')).to_be_visible()
    page.locator('#location').fill(location[:12])

    dropdown = page.locator('#location-suggestions')
    expect(dropdown).to_be_visible(timeout=5000)
    expect(dropdown).to_contain_text(location, timeout=5000)


@pytest.mark.e2e
def test_a_product_location_is_offered_on_the_item_form(page, live_server):
    """FR27's other direction, and the one that proves the vocabulary is really
    SHARED rather than merely duplicated: the item form asks the same endpoint
    under the same field name and is offered the product's value."""
    location = _unique_location('item')
    _add_product(page, live_server, 'E2E cross-form seed', location=location)

    page.goto(f'{live_server.url}/inventory/add')
    expect(page.locator('#location')).to_be_visible()
    page.locator('#location').fill(location[:12])

    dropdown = page.locator('#location-suggestions')
    expect(dropdown).to_be_visible(timeout=5000)
    expect(dropdown).to_contain_text(location, timeout=5000)


@pytest.mark.e2e
def test_the_stored_location_pair_shows_on_the_detail_page(page, live_server):
    location = _unique_location('pair')
    _add_product(page, live_server, 'E2E located product',
                 location=location, sub_location='Left tray')
    expect(page.locator('#product-location')).to_contain_text(location)
    expect(page.locator('#product-location')).to_contain_text('Left tray')
