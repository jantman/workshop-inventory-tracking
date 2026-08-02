"""
E2E tests for the keyboard-wedge scan path.

Drives the scan input the way the scanner does -- keystrokes terminated by Enter
-- rather than posting to the API, because the capture layer is where a scan can
be silently mangled and nothing else in the suite would notice.
"""

import pytest
from playwright.sync_api import expect

VALID_UPC_A = "012345678905"


def create_product(page, base_url, description, **fields):
    """Create a product through the form and return its detail URL"""
    page.goto(f"{base_url}/products/new")
    page.fill("#description", description)
    for field, value in fields.items():
        if field == "identifier_type":
            page.select_option("#identifier_type", value)
        else:
            page.fill(f"#{field}", value)
    page.click("#save-product-btn")
    page.wait_for_load_state("networkidle")
    return page.url


def scan(page, text):
    """Type a scan into the global scan input and terminate it like a wedge does"""
    page.click("#global-scan-input")
    page.keyboard.type(text)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")


@pytest.mark.e2e
def test_scanning_an_internal_code_lands_on_its_product(page, live_server):
    """SC-001: the scan answers 'what is this thing'"""
    create_product(page, live_server.url, "Blue widget, 10mm", specifications="10mm, blue")
    code = page.locator("#internal-code").inner_text().strip()

    page.goto(live_server.url)
    scan(page, code)

    expect(page.locator("#product-description")).to_have_text("Blue widget, 10mm")
    expect(page.locator("#internal-code")).to_have_text(code)


@pytest.mark.e2e
def test_scanning_an_unknown_barcode_lands_on_a_create_form_carrying_it(page, live_server):
    """FR-018: an unrecognized scan offers creation, it does not dead-end"""
    page.goto(live_server.url)
    scan(page, VALID_UPC_A)

    # The create form, with the barcode already normalized and attached.
    expect(page.locator("#description")).to_be_visible()
    expect(page.locator("#identifier_value")).to_have_value("00012345678905")
    expect(page.locator("#identifier_type")).to_have_value("GTIN")


@pytest.mark.e2e
def test_the_offered_product_can_be_created_from_there(page, live_server):
    """The offer is real: filling it in produces a product carrying the scan"""
    page.goto(live_server.url)
    scan(page, VALID_UPC_A)

    page.fill("#description", "Newly catalogued thing")
    page.click("#save-product-btn")
    page.wait_for_load_state("networkidle")

    expect(page.locator("#product-description")).to_have_text("Newly catalogued thing")
    expect(page.locator("#identifier-list")).to_contain_text("00012345678905")


@pytest.mark.e2e
def test_scanning_junk_lands_on_search_with_the_raw_scan(page, live_server):
    """Story 4 scenario 3: the raw scan is surfaced, not silently swallowed"""
    page.goto(live_server.url)
    scan(page, "utterly unrecognizable gibberish")

    expect(page.locator("#raw-scan-notice")).to_contain_text("utterly unrecognizable gibberish")
    expect(page.locator("#product-table")).to_be_visible()


@pytest.mark.e2e
def test_scanning_a_stored_vendor_identifier_lands_on_its_product(page, live_server):
    """Rule 4: an ASIN has no shape, so it is found by looking it up"""
    create_product(
        page, live_server.url, "Amazon widget",
        identifier_type="VENDOR", identifier_value="B0ABCDEFGH",
        identifier_vendor="Amazon",
    )

    page.goto(live_server.url)
    scan(page, "B0ABCDEFGH")

    expect(page.locator("#product-description")).to_have_text("Amazon widget")


@pytest.mark.e2e
def test_the_capture_layer_preserves_control_characters(page, live_server):
    """The single most breakable link in the feature.

    A wedge sends GS/RS/EOT as Ctrl-key events. A capture that drops them passes
    every other test here and fails only against a real distributor label, so
    this asserts the mapping directly rather than through a round trip.
    """
    page.goto(live_server.url)

    mapped = page.evaluate(
        """() => {
            const map = window.WorkshopScanCapture.controlCharacterFor;
            const ev = (key) => ({ ctrlKey: true, altKey: false, metaKey: false, key: key });
            return {
                gs: map(ev(']')),
                rs: map(ev('^')),
                eot: map(ev('d')),
                plain: map({ ctrlKey: false, altKey: false, metaKey: false, key: 'a' })
            };
        }"""
    )

    assert mapped["gs"] == "\x1d"
    assert mapped["rs"] == "\x1e"
    assert mapped["eot"] == "\x04"
    assert mapped["plain"] is None


@pytest.mark.e2e
def test_a_scan_is_available_from_wherever_the_operator_already_is(page, live_server):
    """Contract: scanning is not confined to a dedicated page"""
    for path in ["/", "/products", "/inventory"]:
        page.goto(f"{live_server.url}{path}")
        expect(page.locator("#global-scan-input")).to_be_visible()
