"""
E2E tests for a long scanning session on the Move page (issue #107).

The reported defect is that after a long run of scanning, Validate & Preview
never becomes available and the whole session's manual work is stranded. The
suite covered two items; the report is fourteen pairs, and FR-020 exists because
the difference between those two numbers is where the defect lived.

Two further paths are covered here because nothing else in the suite has ever
executed them:

* the state machine's recovery when a JA ID arrives while a location is expected
  -- the wedge, which used to warn and leave the state untouched, so every
  subsequent scan bounced off it and nothing was ever queued; and
* a scan with no trailing newline (FR-017, FR-021). Every other scan in this
  suite is `.type()` then `.press("Enter")`, and Enter cancels the 100 ms
  fallback timer, so the fallback path has never run under test.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.waits import scan_on_move_page, wait_for_move_executed

# Fourteen, matching the report. Locations are all M-prefixed so isLocation()
# classifies them as locations rather than sub-locations.
PAIRS = [(f"JA20{n:04d}", f"M{n}-A") for n in range(1, 15)]


def _seed(live_server, pairs=PAIRS):
    live_server.add_test_data([
        {
            "ja_id": ja_id,
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "12.0",
            "width": "0.5",
            "location": "Storage A",
            "active": True,
        }
        for ja_id, _ in pairs
    ])


@pytest.mark.e2e
def test_fourteen_pairs_can_be_validated_and_executed(page, live_server):
    """FR-014, FR-015, FR-016, FR-020 and acceptance scenarios 1-3 of US2."""
    _seed(live_server)
    page.goto(f"{live_server.url}/inventory/move")
    expect(page.locator("#barcode-input")).to_be_focused()

    for ja_id, location in PAIRS:
        scan_on_move_page(page, ja_id)
        scan_on_move_page(page, location)

    # Thirteen are queued; the fourteenth is still in progress until >>DONE<<.
    expect(page.locator("#queue-count")).to_have_text("13 items")

    scan_on_move_page(page, ">>DONE<<")

    # The last pair is queued, every pair is present, and validation is reachable.
    expect(page.locator("#queue-count")).to_have_text("14 items")
    expect(page.locator("#validate-btn")).to_be_enabled()
    rows = page.locator("#queue-items tr")
    expect(rows).to_have_count(14)
    for ja_id, location in PAIRS:
        expect(rows.filter(has_text=ja_id)).to_contain_text(location)

    # FR-016: no spurious input warning. The scanner's Enter used to reach
    # processInput() after handleBarcodeInput() had already consumed >>DONE<<
    # and emptied the field, which raised "Please enter a value" every time.
    expect(page.locator("#form-alerts")).not_to_contain_text("Please enter a value")

    page.locator("#validate-btn").click()
    expect(page.locator("#validation-section")).to_be_visible()
    expect(page.locator("#execute-moves-btn")).to_be_enabled()

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#execute-moves-btn").click()
    wait_for_move_executed(page)


@pytest.mark.e2e
def test_a_ja_id_while_a_location_is_expected_resolves_the_machine(page, live_server):
    """data-model.md section 5's invariant: no input may leave the machine in a
    state from which no valid input makes progress.

    A JA ID arriving here unambiguously means the previous item's location was
    missed. The old code warned and left `currentExpectedInput` at `location`,
    so every subsequent JA-ID scan bounced off it, nothing was ever queued, and
    >>DONE<< then reported an empty queue -- which is exactly the report.
    """
    _seed(live_server, PAIRS[:3])
    page.goto(f"{live_server.url}/inventory/move")
    expect(page.locator("#barcode-input")).to_be_focused()

    scan_on_move_page(page, "JA200001")
    # The location for JA200001 is missed; the next scan is the next item.
    scan_on_move_page(page, "JA200002")

    # The machine has moved on to the new item rather than bouncing, and the
    # abandoned one is named rather than lost silently.
    assert page.evaluate("() => window.moveManager.currentJaId") == "JA200002"
    assert page.evaluate("() => window.moveManager.currentExpectedInput") == "location"
    expect(page.locator("#form-alerts .alert").last).to_contain_text("JA200001")

    # And the session continues normally from there.
    scan_on_move_page(page, "M2-A")
    scan_on_move_page(page, "JA200003")
    scan_on_move_page(page, "M3-A")
    scan_on_move_page(page, ">>DONE<<")

    expect(page.locator("#queue-count")).to_have_text("2 items")
    expect(page.locator("#validate-btn")).to_be_enabled()
    rows = page.locator("#queue-items tr")
    expect(rows.filter(has_text="JA200002")).to_contain_text("M2-A")
    expect(rows.filter(has_text="JA200003")).to_contain_text("M3-A")
    expect(rows.filter(has_text="JA200001")).to_have_count(0)


@pytest.mark.e2e
def test_repeated_rejections_are_all_visible(page, live_server):
    """showAlert() used to assign innerHTML, so fourteen failed scans rendered
    as one message and a stale `warning` never auto-dismissed. A user scanning
    into a machine that is refusing everything could not see that it was."""
    _seed(live_server, PAIRS[:3])
    page.goto(f"{live_server.url}/inventory/move")
    expect(page.locator("#barcode-input")).to_be_focused()

    # Three sub-locations while a JA ID is expected: three refusals.
    for text in ("Drawer 1", "Drawer 2", "Drawer 3"):
        scan_on_move_page(page, text)

    expect(page.locator("#form-alerts .alert")).to_have_count(3)


@pytest.mark.e2e
def test_a_scanner_without_a_trailing_newline_behaves_identically(page, live_server):
    """FR-017, FR-021 and acceptance scenario 4 of US2.

    Nothing here waits on a clock: handleBarcodeInput()'s 100 ms fallback timer
    fires on its own and every assertion below is on observable state, so the
    only difference from the test above is that Enter is never pressed.
    """
    _seed(live_server, PAIRS[:4])
    page.goto(f"{live_server.url}/inventory/move")
    expect(page.locator("#barcode-input")).to_be_focused()

    for ja_id, location in PAIRS[:4]:
        scan_on_move_page(page, ja_id, press_enter=False)
        scan_on_move_page(page, location, press_enter=False)

    scan_on_move_page(page, ">>DONE<<", press_enter=False)

    expect(page.locator("#queue-count")).to_have_text("4 items")
    expect(page.locator("#validate-btn")).to_be_enabled()
    rows = page.locator("#queue-items tr")
    for ja_id, location in PAIRS[:4]:
        expect(rows.filter(has_text=ja_id)).to_contain_text(location)

    page.locator("#validate-btn").click()
    expect(page.locator("#execute-moves-btn")).to_be_enabled()
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#execute-moves-btn").click()
    wait_for_move_executed(page)


@pytest.mark.e2e
def test_a_half_entered_item_explains_why_validation_is_unavailable(page, live_server):
    """FR-018 and acceptance scenario 5 of US2. The button being disabled with
    thirteen items queued is correct; being disabled without saying why is what
    made the reported defect impossible to act on."""
    _seed(live_server, PAIRS[:2])
    page.goto(f"{live_server.url}/inventory/move")
    expect(page.locator("#barcode-input")).to_be_focused()

    scan_on_move_page(page, "JA200001")
    scan_on_move_page(page, "M1-A")
    scan_on_move_page(page, "JA200002")

    # JA200001 is queued; JA200002 has no location yet.
    expect(page.locator("#queue-count")).to_have_text("1 item")
    expect(page.locator("#validate-btn")).to_be_disabled()
    expect(page.locator("#validate-hint")).to_contain_text("JA200002")

    scan_on_move_page(page, "M2-A")
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("2 items")
    expect(page.locator("#validate-btn")).to_be_enabled()
    expect(page.locator("#validate-hint")).to_be_empty()
