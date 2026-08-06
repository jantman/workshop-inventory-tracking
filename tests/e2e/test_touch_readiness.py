"""
E2E tests for touch and handheld use.

SC-010: every action reachable at the workshop cart is reachable on a touch
device with no keyboard. These drive a phone-sized touch viewport and tap rather
than click, and never send a key -- if something here needs typing, it fails.

The single responsive interface is the point. There is no separate mobile UI and
none is being tested for.
"""

import re

import pytest
from playwright.sync_api import expect

# A small phone in portrait -- the narrowest thing this has to work on.
TOUCH_VIEWPORT = {"width": 390, "height": 844}


@pytest.fixture
def touch_page(browser, live_server):
    """A touch-only context: no keyboard is used by anything below"""
    context = browser.new_context(
        viewport=TOUCH_VIEWPORT,
        has_touch=True,
        is_mobile=True,
        ignore_https_errors=True,
    )
    page = context.new_page()
    page.set_default_timeout(60000)
    yield page
    context.close()


def seed_product(page, base_url, description):
    """Create a product with the keyboard, before the touch-only part begins"""
    page.goto(f"{base_url}/products/new")
    page.fill("#description", description)
    page.click("#save-product-btn")
    # Saving redirects to the detail page; wait for that page's own content
    # rather than for the form page we are navigating away from.
    expect(page.locator("#stock-card")).to_be_visible()
    return page.url


@pytest.mark.e2e
def test_a_scan_result_is_self_sufficient_on_a_touch_screen(page, touch_page, live_server):
    """Everything needed after a scan is on that one screen"""
    detail_url = seed_product(page, live_server.url, "Blue widget, 10mm")

    touch_page.goto(f"{detail_url}?from_scan=1")
    touch_page.wait_for_load_state("domcontentloaded")

    # No hover-only affordances and no second window: the actions are visible.
    expect(touch_page.locator("#scan-match-banner")).to_be_visible()
    expect(touch_page.locator("#add-purchase-to-this-btn")).to_be_visible()
    expect(touch_page.locator("#print-product-label-btn")).to_be_visible()
    expect(touch_page.locator("#internal-code")).to_be_visible()


@pytest.mark.e2e
def test_quantity_is_adjustable_by_tapping(touch_page, page, live_server):
    """FR-036: a touch target, not a type-a-number-only field"""
    detail_url = seed_product(page, live_server.url, "Tappable widget")

    touch_page.goto(detail_url)
    touch_page.wait_for_load_state("domcontentloaded")

    touch_page.tap("#start-tracking-btn")
    touch_page.wait_for_load_state("domcontentloaded")
    expect(touch_page.locator("#quantity-value")).to_contain_text("None on hand")

    touch_page.tap("#quantity-increment")
    touch_page.wait_for_load_state("domcontentloaded")
    expect(touch_page.locator("#quantity-value")).to_contain_text("1")

    touch_page.tap("#quantity-decrement")
    touch_page.wait_for_load_state("domcontentloaded")
    expect(touch_page.locator("#quantity-value")).to_contain_text("None on hand")


@pytest.mark.e2e
def test_stock_status_is_settable_by_tapping(touch_page, page, live_server):
    detail_url = seed_product(page, live_server.url, "Flaggable widget")

    touch_page.goto(detail_url)
    touch_page.tap("#flag-low-btn")
    # The button PATCHes and then reloads; wait for the reloaded styling, or the
    # goto below aborts the request that is still in flight.
    expect(touch_page.locator("#flag-low-btn")).to_have_class(
        re.compile(r"\bbtn-warning\b")
    )

    touch_page.goto(f"{live_server.url}/products/reorder")
    expect(touch_page.locator("#reorder-table")).to_contain_text("Flaggable widget")

    touch_page.goto(detail_url)
    touch_page.tap("#clear-flag-btn")
    expect(touch_page.locator("#flag-low-btn")).to_have_class(
        re.compile(r"\bbtn-outline-warning\b")
    )

    touch_page.goto(f"{live_server.url}/products/reorder")
    expect(touch_page.locator("#nothing-to-reorder")).to_be_visible()


@pytest.mark.e2e
def test_the_reorder_view_is_usable_on_a_touch_screen(touch_page, page, live_server):
    """SC-010 over the reorder view specifically"""
    detail_url = seed_product(page, live_server.url, "Needs reordering")

    touch_page.goto(detail_url)
    touch_page.tap("#flag-low-btn")
    # The flag PATCHes and reloads; wait for the reloaded styling so the goto
    # below cannot abort the request.
    expect(touch_page.locator("#flag-low-btn")).to_have_class(
        re.compile(r"\bbtn-warning\b")
    )

    touch_page.goto(f"{live_server.url}/products/reorder")
    expect(touch_page.locator(".reorder-row")).to_be_visible()

    # And the action on each row is reachable by tapping it.
    touch_page.tap(".reorder-row a")
    expect(touch_page.locator("#product-description")).to_have_text("Needs reordering")


@pytest.mark.e2e
def test_the_stock_controls_are_large_enough_to_hit(touch_page, page, live_server):
    """A 44px target is the smallest thing a thumb reliably lands on"""
    detail_url = seed_product(page, live_server.url, "Widget")

    touch_page.goto(detail_url)
    touch_page.wait_for_load_state("domcontentloaded")

    for selector in ["#flag-low-btn", "#flag-out-btn", "#clear-flag-btn",
                     "#start-tracking-btn"]:
        box = touch_page.locator(selector).bounding_box()
        assert box is not None, f"{selector} is not visible on a touch viewport"
        assert box["height"] >= 44, f"{selector} is only {box['height']}px tall"


@pytest.mark.e2e
def test_the_page_does_not_scroll_sideways_on_a_phone(touch_page, page, live_server):
    """A horizontal scrollbar is how a desktop layout announces it is not responsive"""
    detail_url = seed_product(page, live_server.url, "Widget")

    for url in [f"{live_server.url}/products",
                f"{live_server.url}/products/reorder",
                detail_url]:
        touch_page.goto(url)
        touch_page.wait_for_load_state("domcontentloaded")
        overflow = touch_page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 1, f"{url} scrolls {overflow}px sideways on a phone"


@pytest.mark.e2e
def test_the_scan_entry_point_is_reachable_on_a_phone(touch_page, live_server):
    """Story 1 begins wherever the operator is, including on the handheld"""
    touch_page.goto(live_server.url)
    touch_page.wait_for_load_state("domcontentloaded")

    # Collapsed behind the navbar toggle on a phone, but reachable by tapping.
    touch_page.tap(".navbar-toggler")
    expect(touch_page.locator("#global-scan-input")).to_be_visible()
