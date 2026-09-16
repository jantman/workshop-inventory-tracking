"""
E2E tests for bulk label printing from the products list.

Feature 045 / issue #157: the products list gains the check-rows-and-print
behaviour the inventory list already had. The dialog is the shared one
(app/static/js/bulk-label-print.js), so what these tests really pin down
is the products side of it -- the selection, and that each product's label goes
to that product's own endpoint.

Products are seeded through `live_server.add_test_products` rather than the Add
Product form: the form costs about three seconds per product and is not what is
under test here.
"""

import json
import re

import pytest
from playwright.sync_api import expect

from tests.e2e.waits import (
    wait_for_modal_hidden,
    wait_for_modal_shown,
    wait_for_select_populated,
)

MODAL = "productBulkLabelPrintingModal"
SELECT = "product-bulk-label-type"
COUNT = "product-bulk-label-count"
PRINT_BTN = "#product-bulk-print-all-btn"
DONE_BTN = "#product-bulk-print-done-btn"
STATUS = "#product-bulk-print-status"
PROGRESS = "#product-bulk-print-progress"
ERRORS = "#product-bulk-print-errors"
LIST_BTN = "#product-print-labels-btn"
COUNT_BADGE = "#product-selected-count"


def _capture_label_posts(page):
    """Collect (product_id, body) for every POST to a label endpoint."""
    posts = []

    def handle_request(request):
        match = re.search(r"/api/products/(\d+)/label$", request.url)
        if match and request.method == "POST":
            posts.append((match.group(1), json.loads(request.post_data)))

    page.on("request", handle_request)
    return posts


def _seed(live_server, descriptions):
    return live_server.add_test_products(
        [{"description": description} for description in descriptions]
    )


def _open_list(page, live_server, expected_rows):
    """Go to the products list and establish the table before reading it.

    The rows are server-rendered, so they are present at load -- but every
    count()/is_checked() read below still needs the region established first,
    and a negative assertion needs it most of all.
    """
    page.goto(f"{live_server.url}/products")
    rows = page.locator("#product-table tbody tr")
    expect(rows).to_have_count(expected_rows)


def _tick(page, product):
    page.locator(
        f'input.product-checkbox[data-product-id="{product.id}"]'
    ).check()


def _open_dialog(page):
    """Open the dialog and wait for it to have finished loading its stocks."""
    page.locator(LIST_BTN).click()
    wait_for_modal_shown(page, MODAL)
    wait_for_select_populated(page, SELECT)


def _print(page, stock="Sato 2x4", count=None):
    page.locator(f"#{SELECT}").select_option(stock)
    # The print button is armed by the select's change handler; waiting for it
    # is what proves the handler ran, rather than assuming it did.
    expect(page.locator(PRINT_BTN)).to_be_enabled()
    if count is not None:
        page.locator(f"#{COUNT}").fill(str(count))
    page.locator(PRINT_BTN).click()


def _wait_for_run_to_finish(page):
    """The Done button is revealed after the loop's last await.

    A rendered Done button cannot predate a settled run, which makes it a
    complete signal. The status line is not -- it holds per-product progress
    several times before it holds the completion text.
    """
    expect(page.locator(DONE_BTN)).to_be_visible()


@pytest.mark.e2e
def test_labels_print_for_every_selected_product(page, live_server):
    """US1: tick several rows, print once, get a label for each"""
    widget, gizmo, doohickey = _seed(
        live_server, ["Blue widget", "Green gizmo", "Red doohickey"]
    )
    posts = _capture_label_posts(page)

    _open_list(page, live_server, 3)
    _tick(page, widget)
    _tick(page, doohickey)
    _open_dialog(page)
    _print(page)
    _wait_for_run_to_finish(page)

    assert sorted(product_id for product_id, _ in posts) == sorted(
        [str(widget.id), str(doohickey.id)]
    )
    # The unticked product was not printed.
    assert str(gizmo.id) not in [product_id for product_id, _ in posts]
    expect(page.locator(STATUS)).to_have_text(
        "Complete: 2 labels for 2 products, 0 failed"
    )


@pytest.mark.e2e
def test_the_dialog_names_the_selected_products(page, live_server):
    """US1: the operator sees what they are about to print, before it"""
    widget, gizmo = _seed(live_server, ["Blue widget", "Green gizmo"])

    _open_list(page, live_server, 2)
    _tick(page, widget)
    _tick(page, gizmo)
    _open_dialog(page)

    expect(page.locator("#product-bulk-print-summary")).to_have_text(
        "You have selected 2 product(s) to print labels for."
    )
    items = page.locator("#product-bulk-label-items-list li")
    expect(items).to_have_count(2)
    expect(items.nth(0)).to_have_text("Blue widget")
    expect(items.nth(1)).to_have_text("Green gizmo")


@pytest.mark.e2e
def test_a_count_of_four_prints_four_of_each(page, live_server):
    """US1 / SC-002: labels produced = products selected x copies requested"""
    products = _seed(
        live_server, ["Blue widget", "Green gizmo", "Red doohickey"]
    )
    posts = _capture_label_posts(page)

    _open_list(page, live_server, 3)
    for product in products:
        _tick(page, product)
    _open_dialog(page)
    _print(page, count=4)
    _wait_for_run_to_finish(page)

    assert len(posts) == 3
    assert all(body["label_count"] == 4 for _, body in posts)
    expect(page.locator(STATUS)).to_have_text(
        "Complete: 12 labels for 3 products, 0 failed"
    )


@pytest.mark.e2e
def test_one_product_at_count_one_reads_singular(page, live_server):
    """US1: "1 label for 1 product", not "1 labels ... 1 products" """
    widget = _seed(live_server, ["Blue widget"])[0]

    _open_list(page, live_server, 1)
    _tick(page, widget)
    _open_dialog(page)
    _print(page)
    _wait_for_run_to_finish(page)

    expect(page.locator(STATUS)).to_have_text(
        "Complete: 1 label for 1 product, 0 failed"
    )


@pytest.mark.e2e
def test_all_six_stocks_are_offered(page, live_server):
    """US1 FR-005 / SC-006: the same set the inventory labels offer"""
    widget = _seed(live_server, ["Blue widget"])[0]

    _open_list(page, live_server, 1)
    _tick(page, widget)
    _open_dialog(page)

    options = page.locator(f"#{SELECT} option")
    # Six stocks plus the "Select label type..." placeholder.
    expect(options).to_have_count(7)
    for stock in ("Sato 1x2", "Sato 1x2 Flag", "Sato 2x4",
                  "Sato 2x4 Flag", "Sato 4x6", "Sato 4x6 Flag"):
        option = page.locator(f"#{SELECT} option[value='{stock}']")
        expect(option).to_have_count(1)


@pytest.mark.e2e
@pytest.mark.parametrize("refused", [
    "0",     # below the range
    "100",   # above it
    "2.5",   # not a whole number
    "",      # cleared -- the only way a number input reaches "not a number",
             # since the browser refuses to let text be typed into one at all
])
def test_a_refused_count_prints_nothing_at_all(page, live_server, refused):
    """US1 FR-007 / SC-005: not even the first product in the selection"""
    products = _seed(live_server, ["Blue widget", "Green gizmo"])
    posts = _capture_label_posts(page)

    _open_list(page, live_server, 2)
    for product in products:
        _tick(page, product)
    _open_dialog(page)
    _print(page, count=refused)

    # Two conditions, not one. The warning alone would also be satisfied by a
    # run that started and then failed; the progress region never appearing is
    # what says nothing was attempted.
    expect(page.locator(ERRORS)).to_be_visible()
    expect(page.locator(ERRORS)).to_contain_text(
        "Label count must be a whole number between 1 and 99"
    )
    expect(page.locator(PROGRESS)).to_be_hidden()
    assert posts == []


@pytest.mark.e2e
def test_correcting_a_refused_count_clears_the_warning(page, live_server):
    """US1: a stale warning must not sit above a successful completion line"""
    widget = _seed(live_server, ["Blue widget"])[0]

    _open_list(page, live_server, 1)
    _tick(page, widget)
    _open_dialog(page)
    _print(page, count=0)
    expect(page.locator(ERRORS)).to_be_visible()

    page.locator(f"#{COUNT}").fill("2")
    page.locator(PRINT_BTN).click()
    _wait_for_run_to_finish(page)

    expect(page.locator(ERRORS)).to_be_hidden()
    expect(page.locator(STATUS)).to_have_text(
        "Complete: 2 labels for 1 product, 0 failed"
    )


@pytest.mark.e2e
def test_print_is_unavailable_with_nothing_selected(page, live_server):
    """US1 FR-004: no selection, no dialog"""
    _seed(live_server, ["Blue widget", "Green gizmo"])

    _open_list(page, live_server, 2)

    # A positive assertion that polls. `not_to_be_enabled` would also be
    # satisfied by a button no handler had reached yet.
    expect(page.locator(LIST_BTN)).to_be_disabled()
    expect(page.locator(COUNT_BADGE)).to_have_text("0")


@pytest.mark.e2e
def test_the_dialog_resets_when_it_is_reopened(page, live_server):
    """US1 FR-013: no count, progress or error carried over from a run"""
    widget = _seed(live_server, ["Blue widget"])[0]

    _open_list(page, live_server, 1)
    _tick(page, widget)
    _open_dialog(page)
    _print(page, count=7)
    _wait_for_run_to_finish(page)

    page.locator(DONE_BTN).click()
    wait_for_modal_hidden(page, MODAL)

    _open_dialog(page)

    expect(page.locator(f"#{COUNT}")).to_have_value("1")
    expect(page.locator(f"#{SELECT}")).to_have_value("")
    expect(page.locator(PROGRESS)).to_be_hidden()
    expect(page.locator(ERRORS)).to_be_hidden()
    expect(page.locator(PRINT_BTN)).to_be_disabled()


# --------------------------------------------------------------------------
# US2 -- selection
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_select_all_ticks_every_listed_product(page, live_server):
    """US2 FR-002: one control selects the whole list"""
    _seed(live_server, ["Blue widget", "Green gizmo", "Red doohickey"])

    _open_list(page, live_server, 3)
    page.locator("#product-select-all").check()

    expect(page.locator(COUNT_BADGE)).to_have_text("3")
    expect(page.locator(LIST_BTN)).to_be_enabled()


@pytest.mark.e2e
def test_select_all_again_clears_the_selection(page, live_server):
    """US2: and the print action goes away with it"""
    _seed(live_server, ["Blue widget", "Green gizmo"])

    _open_list(page, live_server, 2)
    page.locator("#product-select-all").check()
    expect(page.locator(COUNT_BADGE)).to_have_text("2")

    page.locator("#product-select-all").uncheck()

    expect(page.locator(COUNT_BADGE)).to_have_text("0")
    expect(page.locator(LIST_BTN)).to_be_disabled()


@pytest.mark.e2e
def test_a_partial_selection_shows_as_partial(page, live_server):
    """US2 FR-003: three states; "some" is neither of the extremes"""
    widget = _seed(
        live_server, ["Blue widget", "Green gizmo", "Red doohickey"]
    )[0]

    _open_list(page, live_server, 3)
    select_all = page.locator("#product-select-all")

    # None selected: neither checked nor indeterminate.
    expect(page.locator(COUNT_BADGE)).to_have_text("0")
    assert select_all.is_checked() is False
    assert select_all.evaluate("el => el.indeterminate") is False

    _tick(page, widget)

    # `indeterminate` is a property, not an attribute, so it has to be read off
    # the element rather than matched as markup.
    expect(page.locator(COUNT_BADGE)).to_have_text("1")
    assert select_all.is_checked() is False
    assert select_all.evaluate("el => el.indeterminate") is True

    page.locator("#product-select-all").check()

    expect(page.locator(COUNT_BADGE)).to_have_text("3")
    assert select_all.is_checked() is True
    assert select_all.evaluate("el => el.indeterminate") is False


@pytest.mark.e2e
def test_selection_covers_only_what_the_filter_lists(page, live_server):
    """US2 FR-015: a product the list no longer shows cannot be selected"""
    _seed(
        live_server,
        ["Blue widget", "Blue widget large", "Green gizmo", "Red doohickey"],
    )

    page.goto(f"{live_server.url}/products?q=widget")
    expect(page.locator("#product-table tbody tr")).to_have_count(2)

    page.locator("#product-select-all").check()

    # Two, not four -- the two gizmo/doohickey rows are not on the page to be
    # selected, which is the whole point of reading the selection off the DOM.
    expect(page.locator(COUNT_BADGE)).to_have_text("2")


@pytest.mark.e2e
def test_an_empty_list_offers_nothing_to_print(page, live_server):
    """US2: no rows, nothing to select, nothing to print"""
    page.goto(f"{live_server.url}/products?q=nothingmatchesthis")

    # Establish the empty state before asserting the negative, so the assertion
    # cannot pass against a page that simply has not rendered.
    expect(page.locator("#no-products")).to_be_visible()
    expect(page.locator("input.product-checkbox")).to_have_count(0)
    expect(page.locator(LIST_BTN)).to_be_disabled()


# --------------------------------------------------------------------------
# US3 -- failures
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_one_failure_does_not_take_the_run_with_it(page, live_server):
    """US3 FR-011/FR-012 / SC-004: four still print, and the fifth is named"""
    products = _seed(
        live_server,
        ["Blue widget", "Green gizmo", "Red doohickey",
         "Black bracket", "White washer"],
    )
    doomed = products[2]
    posts = _capture_label_posts(page)

    page.route(
        f"**/api/products/{doomed.id}/label",
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps({"success": False, "error": "Printer on fire"}),
        ),
    )

    _open_list(page, live_server, 5)
    for product in products:
        _tick(page, product)
    _open_dialog(page)
    _print(page)
    _wait_for_run_to_finish(page)

    expect(page.locator(STATUS)).to_have_text(
        "Complete: 4 labels for 5 products, 1 failed"
    )
    errors = page.locator(ERRORS)
    expect(errors).to_be_visible()
    # Named by what the operator sees in the list, not by an internal id.
    expect(errors).to_contain_text("Red doohickey: Printer on fire")

    # The run was not abandoned: every product was still attempted.
    assert len(posts) == 5


@pytest.mark.e2e
def test_progress_names_which_product_of_how_many(page, live_server):
    """US3 FR-010: the operator can see where a run has got to"""
    products = _seed(
        live_server, ["Blue widget", "Green gizmo", "Red doohickey"]
    )

    # Hold the first request open so the run is observably mid-flight rather
    # than over before the assertion runs.
    released = []
    page.route(
        f"**/api/products/{products[0].id}/label",
        lambda route: released.append(route),
    )

    _open_list(page, live_server, 3)
    for product in products:
        _tick(page, product)
    _open_dialog(page)
    _print(page, count=3)

    expect(page.locator(STATUS)).to_have_text(
        "Printing 1 of 3: Blue widget (3 labels)"
    )

    released[0].continue_()
    _wait_for_run_to_finish(page)

    expect(page.locator(STATUS)).to_have_text(
        "Complete: 9 labels for 3 products, 0 failed"
    )


@pytest.mark.e2e
def test_a_run_in_which_everything_fails_claims_nothing(page, live_server):
    """US3: printer unavailable -- zero labels, not a false success"""
    products = _seed(live_server, ["Blue widget", "Green gizmo"])

    page.route(
        "**/api/products/*/label",
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps({"success": False, "error": "No printer"}),
        ),
    )

    _open_list(page, live_server, 2)
    for product in products:
        _tick(page, product)
    _open_dialog(page)
    _print(page, count=5)
    _wait_for_run_to_finish(page)

    # Zero, not ten: a failed product contributes no labels at all.
    expect(page.locator(STATUS)).to_have_text(
        "Complete: 0 labels for 2 products, 2 failed"
    )
    expect(page.locator(ERRORS)).to_contain_text("Blue widget: No printer")
    expect(page.locator(ERRORS)).to_contain_text("Green gizmo: No printer")
