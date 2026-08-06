"""
E2E tests for scanning a distributor's 2D label.

Story 4: a format-06 envelope produces a populated, editable draft; a corrupted
one surfaces the raw scan for manual handling rather than failing silently.

The scan is delivered through the same POST the wedge capture makes, control
characters and all -- driving Ctrl-key events for GS and RS through Playwright
would test the browser's keyboard model more than this feature's.
"""

import pytest
from playwright.sync_api import expect

RS = "\x1e"
GS = "\x1d"
EOT = "\x04"

ENVELOPE = (
    "[)>" + RS + "06" + GS
    + "P296-1234-5-ND" + GS + "1PLM358N" + GS + "Q100" + GS
    + "K12345678" + GS + "1KSO987654" + GS + "9D2431"
    + RS + EOT
)

# The format indicator was never delimited, so this only resembles an envelope.
CORRUPTED = "[)>" + RS + "06X" + GS + "1PLM358N" + RS + EOT


def scan_via_api(page, base_url, scan):
    """Resolve a scan and follow where it says to go"""
    page.goto(base_url)
    result = page.evaluate(
        """async (scan) => {
            const r = await fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scan: scan })
            });
            return await r.json();
        }""",
        scan,
    )
    page.goto(f"{base_url}{result['url']}")
    page.wait_for_load_state("domcontentloaded")
    return result


@pytest.mark.e2e
def test_a_distributor_label_produces_a_populated_editable_draft(page, live_server):
    """SC-004: manufacturer part number, quantity and order references, all editable"""
    result = scan_via_api(page, live_server.url, ENVELOPE)
    assert result["outcome"] == "create"

    # The identifier the ECIA spec requires, already on the form.
    expect(page.locator("#identifier_value")).to_have_value("LM358N")

    # And everything else the label carried, each of them in an editable field
    # rather than as display text.
    expect(page.locator("#ecia-prefill")).to_be_visible()
    expect(page.locator("#ecia_quantity")).to_have_value("100")
    expect(page.locator("#ecia_order_reference")).to_have_value("12345678")
    expect(page.locator("#ecia_supplier_order_reference")).to_have_value("SO987654")
    expect(page.locator("#ecia_date_code")).to_have_value("2431")
    expect(page.locator("#ecia_distributor_part_number")).to_have_value("296-1234-5-ND")


@pytest.mark.e2e
def test_every_extracted_value_can_be_changed_before_saving(page, live_server):
    """FR-017"""
    scan_via_api(page, live_server.url, ENVELOPE)

    quantity_field = page.locator("#ecia_quantity")
    expect(quantity_field).to_be_editable()
    quantity_field.fill("42")
    expect(quantity_field).to_have_value("42")


@pytest.mark.e2e
def test_the_draft_can_be_saved_as_a_product_carrying_the_part_number(page, live_server):
    scan_via_api(page, live_server.url, ENVELOPE)

    page.fill("#description", "LM358 dual op-amp, DIP-8")
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

    expect(page.locator("#product-description")).to_have_text("LM358 dual op-amp, DIP-8")
    expect(page.locator("#identifier-list")).to_contain_text("LM358N")


@pytest.mark.e2e
def test_scanning_the_same_label_again_finds_the_product(page, live_server):
    """No new label is printed and no duplicate is created"""
    scan_via_api(page, live_server.url, ENVELOPE)
    page.fill("#description", "LM358 dual op-amp")
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

    result = scan_via_api(page, live_server.url, ENVELOPE)
    assert result["outcome"] == "product"
    expect(page.locator("#product-description")).to_have_text("LM358 dual op-amp")


@pytest.mark.e2e
def test_a_corrupted_envelope_surfaces_the_raw_scan(page, live_server):
    """Story 4 scenario 3: manual handling, not a silent failure"""
    result = scan_via_api(page, live_server.url, CORRUPTED)

    assert result["outcome"] == "search"
    expect(page.locator("#raw-scan-notice")).to_be_visible()
    expect(page.locator("#raw-scan-notice")).to_contain_text("1PLM358N")


@pytest.mark.e2e
def test_an_envelope_carrying_nothing_readable_does_not_dead_end(page, live_server):
    """A well-formed header wrapping only identifiers we have no home for"""
    scan = "[)>" + RS + "06" + GS + "1TLOT4471" + GS + "4LUS" + RS + EOT
    result = scan_via_api(page, live_server.url, scan)

    assert result["outcome"] == "search"
    expect(page.locator("#product-table")).to_be_visible()
