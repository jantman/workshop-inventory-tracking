"""
E2E tests for draft persistence.

FR-035: composing a long description and losing the connection part-way through
must not discard the typing. This is a client-side draft and nothing more --
full offline operation is explicitly out of scope, and the network is the thing
that just failed, so a server-side draft would need the one resource that is
gone.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.specification_rows import (
    ROWS,
    VALUE_INPUT,
    row_pairs,
    set_specifications,
)

LONG_DESCRIPTION = (
    "Blue widget, 10mm anodized aluminium shaft, M4 thread, from the surplus "
    "bin at the back -- the good ones with the knurled collar, not the smooth "
    "ones that slip under load"
)

THREE_SPECS = [
    ("Power rating", "1/4W"),
    ("Tolerance", "5%"),
    ("Voltage", "50V"),
]


@pytest.mark.e2e
def test_in_progress_text_is_offered_back_after_an_interruption(page, live_server):
    """Compose, get interrupted before submitting, come back"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", LONG_DESCRIPTION)
    set_specifications(page, THREE_SPECS)

    # The interruption: the page goes away with nothing submitted.
    page.goto(f"{live_server.url}/products/new")
    page.wait_for_load_state("domcontentloaded")

    expect(page.locator("#draft-restore-banner")).to_be_visible()

    page.click("#draft-restore-btn")
    expect(page.locator("#description")).to_have_value(LONG_DESCRIPTION)

    # All three, with their names, values and order. Asserting only the first
    # would pass against the bug this test exists to prevent: product-form.js
    # keyed its draft by field name, so three rows sharing two names collapsed
    # to one and the restore silently kept the last.
    expect(page.locator(ROWS)).to_have_count(3)
    assert row_pairs(page) == THREE_SPECS


@pytest.mark.e2e
def test_restoring_a_one_row_draft_does_not_duplicate_it_across_the_form(
    page, live_server
):
    """A draft with fewer rows than the page renders must shrink it, not smear.

    `collect()` used to store a repeated field as a list only when two or more
    rows existed *at save time*. Leaving exactly one row therefore saved
    `spec_name`/`spec_value` as scalars, and `apply()` wrote a scalar into every
    element sharing that name -- so restoring a one-row draft onto an edit form
    showing the product's two stored rows produced two identical rows, which the
    duplicate-name rule then refused on save.
    """
    product = live_server.add_test_products([{
        'description': 'Buck converter',
        'specifications': [
            {'name': 'Voltage', 'value': '12 V'},
            {'name': 'Output current', 'value': '3 A'},
        ],
    }])[0]

    page.goto(f"{live_server.url}/products/{product.id}/edit")
    rows = page.locator(ROWS)
    expect(rows).to_have_count(2)

    # Down to a single edited row, then interrupted before saving.
    rows.nth(1).locator(".remove-specification-btn").click()
    expect(rows).to_have_count(1)
    rows.nth(0).locator(VALUE_INPUT).fill("24 V")

    page.goto(f"{live_server.url}/products/{product.id}/edit")
    # The form comes back showing the two rows still in the database.
    expect(rows).to_have_count(2)
    expect(page.locator("#draft-restore-banner")).to_be_visible()

    page.click("#draft-restore-btn")

    # The draft is the whole answer for these rows: the one it holds, and the
    # other blanked rather than left showing a stale "Output current".
    assert row_pairs(page) == [("Voltage", "24 V"), ("", "")]

    # And it saves as the single row the operator actually left.
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")
    names = page.locator("#product-specifications .specification-name")
    expect(names).to_have_count(1)
    expect(names.nth(0)).to_have_text("Voltage")


@pytest.mark.e2e
def test_a_draft_of_only_specifications_is_still_offered_back(page, live_server):
    """Nothing typed but the specification rows, and it must still come back.

    `offerRestore()` runs in product-form.js's own DOMContentLoaded listener,
    which is registered before product-specifications.js's -- and it is the
    latter that adds the blank row when the page renders none. So the check for
    "did the operator type anything?" ran against a DOM holding zero
    `.specification-row` elements, found no field matching `spec_name`, and
    concluded the draft was empty. It is judged by the draft's own keys now,
    not by which inputs happen to exist yet.
    """
    page.goto(f"{live_server.url}/products/new")
    set_specifications(page, [("Voltage", "12 V"), ("Output current", "3 A")])

    page.goto(f"{live_server.url}/products/new")
    page.wait_for_load_state("domcontentloaded")

    expect(page.locator("#draft-restore-banner")).to_be_visible()
    page.click("#draft-restore-btn")

    expect(page.locator(ROWS)).to_have_count(2)
    assert row_pairs(page) == [("Voltage", "12 V"), ("Output current", "3 A")]


@pytest.mark.e2e
def test_the_draft_is_offered_not_applied_silently(page, live_server):
    """The operator may have walked away and come back to start something else"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", LONG_DESCRIPTION)

    page.goto(f"{live_server.url}/products/new")
    page.wait_for_load_state("domcontentloaded")

    # The form is blank until the offer is accepted.
    expect(page.locator("#description")).to_have_value("")
    expect(page.locator("#draft-restore-banner")).to_be_visible()


@pytest.mark.e2e
def test_the_draft_can_be_discarded(page, live_server):
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", LONG_DESCRIPTION)

    page.goto(f"{live_server.url}/products/new")
    page.click("#draft-discard-btn")
    expect(page.locator("#draft-restore-banner")).to_have_count(0)

    page.goto(f"{live_server.url}/products/new")
    page.wait_for_load_state("domcontentloaded")
    expect(page.locator("#draft-restore-banner")).to_have_count(0)


@pytest.mark.e2e
def test_a_successful_submit_clears_the_draft(page, live_server):
    """A draft that outlived its own save would be offered back on a blank form"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", LONG_DESCRIPTION)
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

    expect(page.locator("#product-description")).to_have_text(LONG_DESCRIPTION)

    page.goto(f"{live_server.url}/products/new")
    page.wait_for_load_state("domcontentloaded")
    expect(page.locator("#draft-restore-banner")).to_have_count(0)


@pytest.mark.e2e
def test_a_reload_mid_compose_keeps_the_text(page, live_server):
    """The literal FR-035 scenario: reload, and it is still there to restore"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", LONG_DESCRIPTION)

    page.reload()
    page.wait_for_load_state("domcontentloaded")

    page.click("#draft-restore-btn")
    expect(page.locator("#description")).to_have_value(LONG_DESCRIPTION)


@pytest.mark.e2e
def test_the_edit_form_keeps_its_own_draft(page, live_server):
    """Keyed per form, so an edit draft never lands on the create form"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", "Original")
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")
    detail_url = page.url

    page.goto(f"{detail_url}/edit")
    page.fill("#description", "Half-typed replacement")
    page.goto(f"{live_server.url}/products/new")
    page.wait_for_load_state("domcontentloaded")

    # The create form is untouched by the edit form's draft.
    expect(page.locator("#draft-restore-banner")).to_have_count(0)
