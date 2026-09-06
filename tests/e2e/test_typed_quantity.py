"""
E2E tests for typing a count rather than clicking to it (039, issue #139).

Recording a counted forty used to be forty presses of the increment button,
because a stepper was the only way to move a count at all. These drive the
entry that replaced that, and the two things that have to remain true beside it:
the steppers still work, and beginning a count with an untouched field still
begins it at zero.

**How these wait.** ``product-stock.js`` reloads the page after a successful
PATCH rather than patching the DOM, so a committed count is observable as
server-rendered text and the rendered value cannot predate the completed request
(``CLAUDE.md`` pattern C). A *refused* entry does not reload -- it writes
``#stock-alert`` and stops -- so that element is both the signal for a refusal
and the proof that no reload happened, since a reload would wipe it. Nothing
here waits on a clock.
"""

from datetime import timedelta

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService
from app.utils.clock import utc_now


def seed(live_server, description='Resistor', **fields):
    """A product, straight into the database. The form is not what is tested."""
    service = CatalogService(live_server.storage)
    return service.create_product(description=description, **fields)


def days_ago(days):
    """On the application clock, which is what the age properties subtract from."""
    return utc_now() - timedelta(days=days)


def open_product(page, live_server, product):
    page.goto(f"{live_server.url}/products/{product.id}")
    # Establish the card before anything reads or fills part of it.
    expect(page.locator("#stock-card")).to_be_visible()


# --------------------------------------------------------------------------
# US1 -- record a count that was just taken
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_a_counted_quantity_is_typed_once_not_clicked_forty_times(page, live_server):
    """FR-001, FR-002, SC-001 -- the reported defect."""
    product = seed(live_server, quantity=3)

    open_product(page, live_server, product)
    page.fill("#quantity-input", "40")
    page.click("#quantity-set-btn")

    # The reload is the completion signal: this text is server-rendered.
    expect(page.locator("#quantity-value")).to_contain_text("40")


@pytest.mark.e2e
def test_the_entry_arrives_holding_the_current_count(page, live_server):
    """So committing an unchanged field is a re-verification, not an accident."""
    product = seed(live_server, quantity=17)

    open_product(page, live_server, product)

    expect(page.locator("#quantity-input")).to_have_value("17")


@pytest.mark.e2e
def test_committing_an_unchanged_count_refreshes_its_age(page, live_server):
    """FR-003 -- re-entering the count is "I have just looked again"."""
    product = seed(live_server, quantity=40)
    live_server.backdate_product(product.id, quantity_updated_at=days_ago(100))

    open_product(page, live_server, product)
    expect(page.locator("#quantity-age")).to_contain_text("3 months ago")

    page.click("#quantity-set-btn")

    expect(page.locator("#quantity-age")).to_contain_text("just now")
    expect(page.locator("#quantity-value")).to_contain_text("40")


@pytest.mark.e2e
def test_a_typed_zero_leaves_the_product_counted(page, live_server):
    """FR-005. Zero on hand and not counted at all are different states, and
    the button that produces the second one is a different button."""
    product = seed(live_server, quantity=5)

    open_product(page, live_server, product)
    page.fill("#quantity-input", "0")
    page.click("#quantity-set-btn")

    expect(page.locator("#quantity-value")).to_contain_text("None on hand")
    # Still counted: the control offered is the one that stops counting.
    expect(page.locator("#stop-tracking-btn")).to_be_visible()


@pytest.mark.e2e
def test_the_steppers_still_work_beside_the_entry(page, live_server):
    """FR-009. The typed entry is an addition; this is the interaction it must
    not have cost us."""
    product = seed(live_server, quantity=40)

    open_product(page, live_server, product)
    page.click("#quantity-decrement")

    expect(page.locator("#quantity-value")).to_contain_text("39")
    # And the entry reflects the stepped value, so a subsequent Set is not
    # committing a stale number.
    expect(page.locator("#quantity-input")).to_have_value("39")


@pytest.mark.e2e
def test_an_empty_entry_is_refused_rather_than_stopping_the_count(page, live_server):
    """FR-006. The service reads an empty quantity as "stop counting", which is
    not what an empty box is saying -- so this must never reach it."""
    product = seed(live_server, quantity=40)

    open_product(page, live_server, product)
    page.fill("#quantity-input", "")
    page.click("#quantity-set-btn")

    # The alert is the signal, and its survival is the proof no reload happened.
    expect(page.locator("#stock-alert")).to_be_visible()
    expect(page.locator("#quantity-value")).to_contain_text("40")
    expect(page.locator("#stop-tracking-btn")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.parametrize("bad,message", [("-5", "negative"), ("lots", "whole number"),
                                         ("2.5", "whole number")])
def test_an_unusable_entry_is_refused_with_a_reason(page, live_server, bad, message):
    """FR-007. Three entries, three different things wrong, and the operator is
    told which."""
    product = seed(live_server, quantity=40)

    open_product(page, live_server, product)
    page.fill("#quantity-input", bad)
    page.click("#quantity-set-btn")

    expect(page.locator("#stock-alert")).to_contain_text(message)
    expect(page.locator("#quantity-value")).to_contain_text("40")


@pytest.mark.e2e
def test_a_refused_entry_can_be_corrected_without_reloading(page, live_server):
    """FR-008. The refusal does not reload, so the correction lands on the same
    page the mistake was made on."""
    product = seed(live_server, quantity=40)

    open_product(page, live_server, product)
    page.fill("#quantity-input", "")
    page.click("#quantity-set-btn")
    expect(page.locator("#stock-alert")).to_be_visible()

    page.fill("#quantity-input", "12")
    page.click("#quantity-set-btn")

    expect(page.locator("#quantity-value")).to_contain_text("12")


# --------------------------------------------------------------------------
# US2 -- start counting at the number it is actually at
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_a_count_can_begin_at_a_typed_number(page, live_server):
    """FR-004, SC-002 -- twelve in the bag is one entry, not twelve clicks."""
    product = seed(live_server)

    open_product(page, live_server, product)
    expect(page.locator("#quantity-value")).to_contain_text("Not tracked")

    page.fill("#quantity-input", "12")
    page.click("#start-tracking-btn")

    expect(page.locator("#quantity-value")).to_contain_text("12")
    expect(page.locator("#quantity-age")).to_contain_text("just now")


@pytest.mark.e2e
def test_beginning_a_count_with_an_untouched_field_still_starts_at_zero(
    page, live_server
):
    """FR-004's other half, and the behavior this button already had. An
    untouched field is the absence of an entry, not an entry of nothing."""
    product = seed(live_server)

    open_product(page, live_server, product)
    page.click("#start-tracking-btn")

    expect(page.locator("#quantity-value")).to_contain_text("None on hand")


@pytest.mark.e2e
def test_an_unusable_starting_entry_leaves_the_product_uncounted(page, live_server):
    """A non-empty entry that cannot be read is refused here too -- the
    difference between the two buttons is only what *emptiness* means."""
    product = seed(live_server)

    open_product(page, live_server, product)
    page.fill("#quantity-input", "-5")
    page.click("#start-tracking-btn")

    expect(page.locator("#stock-alert")).to_contain_text("negative")
    expect(page.locator("#quantity-value")).to_contain_text("Not tracked")


@pytest.mark.e2e
def test_the_set_button_is_not_offered_before_there_is_a_count(page, live_server):
    """FR-011. Two commit buttons saying different things would be ambiguous."""
    product = seed(live_server)

    open_product(page, live_server, product)

    # #quantity-input establishes the region, so the absence below is not the
    # absence of a page that has not rendered.
    expect(page.locator("#quantity-input")).to_be_visible()
    expect(page.locator("#quantity-set-btn")).to_have_count(0)
    expect(page.locator("#start-tracking-btn")).to_be_visible()


@pytest.mark.e2e
def test_stopping_a_count_is_still_its_own_action(page, live_server):
    """FR-015. Nothing about the typed entry reaches the third state."""
    product = seed(live_server, quantity=12)

    open_product(page, live_server, product)
    page.click("#stop-tracking-btn")

    expect(page.locator("#quantity-value")).to_contain_text("Not tracked")
    expect(page.locator("#quantity-set-btn")).to_have_count(0)


# --------------------------------------------------------------------------
# US3 -- be told what was already received
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_stock_received_while_untracked_is_stated(page, live_server):
    """FR-012. Receiving guards on an existing count, so a hundred received
    into an untracked product moved nothing -- and this is what the operator
    would otherwise reconstruct from the order history."""
    service = CatalogService(live_server.storage)
    product = service.create_product(description='Resistor')
    service.record_purchase(
        product.id, vendor='DigiKey', quantity=100, received_date=utc_now()
    )

    open_product(page, live_server, product)

    expect(page.locator("#received-total")).to_contain_text("100")


@pytest.mark.e2e
def test_the_received_total_is_advisory_and_never_committed(page, live_server):
    """FR-013. Stated, not filled in: the record says what arrived and nothing
    says what has since been used."""
    service = CatalogService(live_server.storage)
    product = service.create_product(description='Resistor')
    service.record_purchase(
        product.id, vendor='DigiKey', quantity=100, received_date=utc_now()
    )

    open_product(page, live_server, product)
    expect(page.locator("#received-total")).to_contain_text("100")
    # Nothing was pre-filled, so pressing the button commits zero, not a
    # hundred.
    expect(page.locator("#quantity-input")).to_have_value("")

    page.click("#start-tracking-btn")

    expect(page.locator("#quantity-value")).to_contain_text("None on hand")


@pytest.mark.e2e
def test_the_received_total_disappears_once_the_product_is_counted(page, live_server):
    """FR-013's other half. Receiving already adds to a tracked count, so
    restating the total there would invite adding it twice."""
    service = CatalogService(live_server.storage)
    product = service.create_product(description='Resistor', quantity=12)
    service.record_purchase(
        product.id, vendor='DigiKey', quantity=100, received_date=utc_now()
    )

    open_product(page, live_server, product)

    # Establish the rendered card first -- a bare negative assertion would
    # also pass against a page that has not loaded.
    expect(page.locator("#quantity-value")).to_contain_text("12")
    expect(page.locator("#received-total")).to_have_count(0)


@pytest.mark.e2e
def test_an_outstanding_order_states_nothing(page, live_server):
    """FR-014. It has not arrived; nothing about it is on any shelf."""
    service = CatalogService(live_server.storage)
    product = service.create_product(description='Resistor')
    service.record_purchase(product.id, vendor='DigiKey', quantity=100)

    open_product(page, live_server, product)

    expect(page.locator("#quantity-value")).to_contain_text("Not tracked")
    expect(page.locator("#received-total")).to_have_count(0)
