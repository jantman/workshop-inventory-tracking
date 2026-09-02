"""
E2E tests for adding and removing a product's identifiers after it was created.

The defect this covers (#136) was invisible to every service-level test: both
API routes worked and neither had a caller, so a test that reached the service
passed against the broken build. What was missing was the control, which is why
everything here drives the page.

Seeding goes through ``live_server.add_test_products`` -- the Add Product form is
the subject in exactly one test, the FR-003 parity check, which has to read that
form's own type list.

**On waiting.** Both mutating paths end in ``window.location.reload()``, so a
rendered row cannot predate the completed request (CLAUDE.md pattern C) and
``expect(rows).to_have_count(n)`` is the whole wait. The refusal paths do not
reload, so the condition there is the alert's text. Every negative assertion is
preceded by a positive ``expect`` that establishes the list first -- against a
page that has not rendered, "the row is gone" passes for the wrong reason.
"""

import re

import pytest
from playwright.sync_api import expect

ROWS = "#identifier-list .identifier-row"
VALUES = "#identifier-list .identifier-value"
ALERT = "#identifier-alerts"

# A real UPC-A off a cataloged product, and the key it is stored as.
VALID_UPC = "687117723741"
VALID_GTIN_KEY = "00687117723741"

# Right length, wrong check digit.
BAD_CHECK_DIGIT = "687117723742"


@pytest.fixture
def product(live_server):
    """Seeded directly -- the Add Product form is not what is under test"""
    return live_server.add_test_products([{"description": "Dorhea ESP32-S3-DevKit"}])[0]


def open_detail(page, live_server, product):
    page.goto(f"{live_server.url}/products/{product.id}")
    # The card is server-rendered, so its presence is the page having loaded.
    expect(page.locator("#internal-code")).to_be_visible()


def add_identifier(page, id_type, value, vendor=None, override=False):
    """Fill the card's form and save. Does not wait -- the caller says for what."""
    page.click("#add-identifier-btn")
    expect(page.locator("#new-identifier-value")).to_be_visible()

    page.select_option("#new-identifier-type", id_type)
    page.fill("#new-identifier-value", value)
    if vendor is not None:
        page.fill("#new-identifier-vendor", vendor)
    if override:
        page.check("#new-identifier-override")
    page.click("#save-identifier-btn")


def scan(page, text):
    """Type into the global scan box and terminate it the way a wedge does"""
    page.click("#global-scan-input")
    page.keyboard.type(text)
    page.keyboard.press("Enter")


# --- User Story 1: make an already-cataloged product scannable ---------------


@pytest.mark.e2e
def test_a_barcode_can_be_added_after_the_product_exists(page, live_server, product):
    """FR-001, FR-005: the whole of #136 in one test"""
    open_detail(page, live_server, product)
    expect(page.locator(ROWS)).to_have_count(0)

    add_identifier(page, "GTIN", VALID_UPC)

    expect(page.locator(ROWS)).to_have_count(1)
    # Stored as the key, not as typed -- which is why the card re-renders from
    # the server rather than echoing the input.
    expect(page.locator(VALUES)).to_have_text([VALID_GTIN_KEY])


@pytest.mark.e2e
def test_an_added_barcode_scans_back_to_its_product(page, live_server, product):
    """SC-002: the fourth GS1 vector -- a cataloged GTIN lands on its product"""
    open_detail(page, live_server, product)
    add_identifier(page, "GTIN", VALID_UPC)
    expect(page.locator(ROWS)).to_have_count(1)

    scan(page, VALID_UPC)

    expect(page).to_have_url(re.compile(rf"/products/{product.id}(\?|$)"))
    expect(page.locator("#internal-code")).to_have_text(product.internal_code)


@pytest.mark.e2e
def test_a_bad_check_digit_is_refused_and_the_typing_survives(page, live_server, product):
    """FR-006, FR-011: nothing stored, and nothing to retype"""
    open_detail(page, live_server, product)

    add_identifier(page, "GTIN", BAD_CHECK_DIGIT)

    expect(page.locator(ALERT)).to_contain_text("not a valid barcode")
    expect(page.locator("#new-identifier-value")).to_have_value(BAD_CHECK_DIGIT)
    expect(page.locator(ROWS)).to_have_count(0)


@pytest.mark.e2e
def test_the_override_stores_a_failing_barcode_visibly(page, live_server, product):
    """FR-006: kept, with the override on the row rather than silent"""
    open_detail(page, live_server, product)

    add_identifier(page, "GTIN", BAD_CHECK_DIGIT, override=True)

    expect(page.locator(ROWS)).to_have_count(1)
    expect(page.locator(ROWS).first).to_contain_text("Validation overridden")


@pytest.mark.e2e
def test_an_all_zero_read_is_refused_even_with_the_override(page, live_server, product):
    """FR-007: a scanner no-read is not a trade item, and no tick makes it one"""
    open_detail(page, live_server, product)

    add_identifier(page, "GTIN", "00000000000000", override=True)

    expect(page.locator(ALERT)).to_contain_text("zeros")
    expect(page.locator(ROWS)).to_have_count(0)


@pytest.mark.e2e
def test_a_value_another_product_owns_names_and_links_it(page, live_server):
    """FR-009: the operator resolves it, so they are told where to go"""
    owner, target = live_server.add_test_products(
        [{"description": "The one that has it"}, {"description": "The one that wants it"}]
    )
    page.goto(f"{live_server.url}/products/{owner.id}")
    expect(page.locator("#internal-code")).to_be_visible()
    add_identifier(page, "GTIN", VALID_UPC)
    expect(page.locator(ROWS)).to_have_count(1)

    page.goto(f"{live_server.url}/products/{target.id}")
    expect(page.locator("#internal-code")).to_be_visible()
    add_identifier(page, "GTIN", VALID_UPC)

    expect(page.locator(ALERT)).to_contain_text("already belongs to product")
    link = page.locator(f'{ALERT} a[href="/products/{owner.id}"]')
    expect(link).to_be_visible()
    expect(page.locator(ROWS)).to_have_count(0)


# --- User Story 2: remove an identifier that is wrong -----------------------


@pytest.mark.e2e
def test_one_identifier_can_be_removed_leaving_the_others(page, live_server, product):
    """FR-013, FR-016"""
    open_detail(page, live_server, product)
    add_identifier(page, "MPN", "ACME-1")
    expect(page.locator(ROWS)).to_have_count(1)
    add_identifier(page, "MPN", "ACME-2")
    expect(page.locator(ROWS)).to_have_count(2)

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator(".remove-identifier-btn").first.click()

    expect(page.locator(ROWS)).to_have_count(1)
    expect(page.locator(VALUES)).to_have_text(["ACME-2"])


@pytest.mark.e2e
def test_declining_the_confirmation_removes_nothing(page, live_server, product):
    """FR-015"""
    open_detail(page, live_server, product)
    add_identifier(page, "MPN", "ACME-1")
    expect(page.locator(ROWS)).to_have_count(1)

    page.once("dialog", lambda dialog: dialog.dismiss())
    page.locator(".remove-identifier-btn").first.click()

    # Nothing reloads on a decline, so the condition is that the row is still
    # there once the click has been handled -- established positively above.
    expect(page.locator(VALUES)).to_have_text(["ACME-1"])


@pytest.mark.e2e
def test_the_product_survives_losing_its_last_identifier(page, live_server, product):
    """FR-017, SC-005: identity is the product row, never one of its names"""
    open_detail(page, live_server, product)
    add_identifier(page, "MPN", "ACME-1")
    expect(page.locator(ROWS)).to_have_count(1)

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator(".remove-identifier-btn").first.click()

    expect(page.locator(ROWS)).to_have_count(0)
    expect(page.locator("#identifier-list")).to_contain_text("No other identifiers")
    expect(page.locator("#internal-code")).to_have_text(product.internal_code)


@pytest.mark.e2e
def test_the_internal_code_has_no_remove_control(page, live_server, product):
    """FR-014: it is generated, so there is nothing to detach"""
    open_detail(page, live_server, product)
    add_identifier(page, "MPN", "ACME-1")
    # Establish the card first: one row, so exactly one remove control exists.
    expect(page.locator(ROWS)).to_have_count(1)

    expect(page.locator(".remove-identifier-btn")).to_have_count(1)
    expect(page.locator("#internal-code")).to_have_text(product.internal_code)


# --- User Story 3: an identifier learned after the fact ----------------------


@pytest.mark.e2e
def test_a_vendor_scoped_type_needs_its_vendor(page, live_server, product):
    """FR-008, FR-011: refused, and what was typed is still there to correct"""
    open_detail(page, live_server, product)

    add_identifier(page, "VENDOR", "B0ABCDEFGH")

    expect(page.locator(ALERT)).to_contain_text("vendor")
    expect(page.locator("#new-identifier-value")).to_have_value("B0ABCDEFGH")
    expect(page.locator(ROWS)).to_have_count(0)


@pytest.mark.e2e
def test_a_vendor_identifier_is_listed_with_its_vendor(page, live_server, product):
    """FR-003, FR-012: the type the barcode case never exercises"""
    open_detail(page, live_server, product)

    add_identifier(page, "VENDOR", "B0ABCDEFGH", vendor="Amazon")

    expect(page.locator(ROWS)).to_have_count(1)
    expect(page.locator(ROWS).first).to_contain_text("B0ABCDEFGH")
    expect(page.locator(ROWS).first).to_contain_text("Amazon")


@pytest.mark.e2e
def test_the_card_offers_the_same_types_as_the_add_product_form(page, live_server, product):
    """FR-003: the test that catches the two lists drifting apart again.

    The Add Product form is the subject here, so this is the one test in the
    file that drives it rather than seeding.
    """
    page.goto(f"{live_server.url}/products/new")
    expect(page.locator("#identifier_type")).to_be_visible()
    on_add_form = page.locator("#identifier_type option").all_inner_texts()

    open_detail(page, live_server, product)
    page.click("#add-identifier-btn")
    expect(page.locator("#new-identifier-type")).to_be_visible()
    on_detail_card = page.locator("#new-identifier-type option").all_inner_texts()

    assert [text.strip() for text in on_detail_card] == [
        text.strip() for text in on_add_form
    ]
    assert "INTERNAL" not in [text.strip() for text in on_detail_card]
