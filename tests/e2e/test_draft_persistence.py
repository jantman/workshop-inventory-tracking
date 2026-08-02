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

LONG_DESCRIPTION = (
    "Blue widget, 10mm anodized aluminium shaft, M4 thread, from the surplus "
    "bin at the back -- the good ones with the knurled collar, not the smooth "
    "ones that slip under load"
)


@pytest.mark.e2e
def test_in_progress_text_is_offered_back_after_an_interruption(page, live_server):
    """Compose, get interrupted before submitting, come back"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", LONG_DESCRIPTION)
    page.fill("#specifications", "1/4W, 5% tolerance, 50V")

    # The interruption: the page goes away with nothing submitted.
    page.goto(f"{live_server.url}/products/new")
    page.wait_for_load_state("networkidle")

    expect(page.locator("#draft-restore-banner")).to_be_visible()

    page.click("#draft-restore-btn")
    expect(page.locator("#description")).to_have_value(LONG_DESCRIPTION)
    expect(page.locator("#specifications")).to_have_value("1/4W, 5% tolerance, 50V")


@pytest.mark.e2e
def test_the_draft_is_offered_not_applied_silently(page, live_server):
    """The operator may have walked away and come back to start something else"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", LONG_DESCRIPTION)

    page.goto(f"{live_server.url}/products/new")
    page.wait_for_load_state("networkidle")

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
    page.wait_for_load_state("networkidle")
    expect(page.locator("#draft-restore-banner")).to_have_count(0)


@pytest.mark.e2e
def test_a_successful_submit_clears_the_draft(page, live_server):
    """A draft that outlived its own save would be offered back on a blank form"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", LONG_DESCRIPTION)
    page.click("#save-product-btn")
    page.wait_for_load_state("networkidle")

    expect(page.locator("#product-description")).to_have_text(LONG_DESCRIPTION)

    page.goto(f"{live_server.url}/products/new")
    page.wait_for_load_state("networkidle")
    expect(page.locator("#draft-restore-banner")).to_have_count(0)


@pytest.mark.e2e
def test_a_reload_mid_compose_keeps_the_text(page, live_server):
    """The literal FR-035 scenario: reload, and it is still there to restore"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", LONG_DESCRIPTION)

    page.reload()
    page.wait_for_load_state("networkidle")

    page.click("#draft-restore-btn")
    expect(page.locator("#description")).to_have_value(LONG_DESCRIPTION)


@pytest.mark.e2e
def test_the_edit_form_keeps_its_own_draft(page, live_server):
    """Keyed per form, so an edit draft never lands on the create form"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", "Original")
    page.click("#save-product-btn")
    page.wait_for_load_state("networkidle")
    detail_url = page.url

    page.goto(f"{detail_url}/edit")
    page.fill("#description", "Half-typed replacement")
    page.goto(f"{live_server.url}/products/new")
    page.wait_for_load_state("networkidle")

    # The create form is untouched by the edit form's draft.
    expect(page.locator("#draft-restore-banner")).to_have_count(0)
