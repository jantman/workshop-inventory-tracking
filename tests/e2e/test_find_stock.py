"""
E2E Tests for the Stock Fit Search

The geometry is proved exhaustively in `tests/unit/test_fit.py`, which runs in
milliseconds. What is here is what only a browser can observe: that the page
drives the search end to end, that the shared results table renders the fit
information without changing on the pages that already use it, and that the
server's ordering survives first render.

Every wait is on observable state. There is no `wait_for_timeout` and no
`time.sleep` in this file, and none is needed: the handler appends rows only
after awaiting the fetch, so a rendered row cannot predate a completed search.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.pages.find_stock_page import FindStockPage
from tests.e2e.pages.inventory_list_page import InventoryListPage
from tests.e2e.pages.search_page import SearchPage

MATERIAL = "Carbon Steel"

# The columns the inventory list and the advanced search have always shown:
# selection, JA ID, Type, Shape, Material, Dimensions, Length, Location,
# Sub-Location, Status, Actions.
SHARED_TABLE_COLUMNS = 11


def bar(ja_id, **fields):
    """One seeded inventory row of the material these tests search for."""
    row = {
        "ja_id": ja_id,
        "item_type": "Bar",
        "shape": "Rectangular",
        "material": MATERIAL,
        "location": "Shop A",
    }
    row.update(fields)
    return row


@pytest.mark.e2e
def test_the_shared_table_does_not_gain_a_fit_column_elsewhere(page, live_server):
    """FR-028, SC-007: the table was extended, not changed underneath its users.

    This is the test that catches a shared-table change leaking onto the pages
    that already render it. Both pages are driven, because the macro has a
    sortable and a non-sortable branch and only the rendered page proves which
    one each takes.
    """
    live_server.add_test_data([bar("JA027001", length="4", width="3", thickness="0.5")])

    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    headers = page.locator("#inventory-table thead th")
    assert headers.count() == SHARED_TABLE_COLUMNS
    assert "Fit" not in (page.locator("#inventory-table thead").text_content() or "")

    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    search_page.search_by_material(MATERIAL)

    headers = page.locator("#results-table thead th")
    assert headers.count() == SHARED_TABLE_COLUMNS
    assert "Fit" not in (page.locator("#results-table thead").text_content() or "")


@pytest.mark.e2e
def test_the_fit_search_shows_the_fit_column(page, live_server):
    """FR-022: the same table, with one column added for this page only."""
    live_server.add_test_data([bar("JA027001", length="4", width="3", thickness="0.5")])

    find_stock = FindStockPage(page, live_server.url)
    find_stock.navigate()
    find_stock.search_rectangular(MATERIAL, "0.5", "3", "4")
    find_stock.expect_result_count(1)

    assert find_stock.column_headers()[-2] == "Fit"
    fit = find_stock.fit_text_for("JA027001")
    assert "3.0000" in fit
    assert "0.5000" in fit


@pytest.mark.e2e
def test_orientation_stops_hiding_stock(page, live_server):
    """User Story 1, SC-001: the same set comes back whichever order was typed.

    One bar, recorded 4 x 3 x 0.5, asked for in three different word orders.
    """
    live_server.add_test_data([bar("JA027001", length="4", width="3", thickness="0.5")])

    find_stock = FindStockPage(page, live_server.url)
    find_stock.navigate()

    for length, width, thickness in [("0.5", "3", "4"),
                                     ("3", "4", "0.5"),
                                     ("4", "0.5", "3")]:
        find_stock.search_rectangular(MATERIAL, length, width, thickness)
        find_stock.expect_result_count(1)
        assert find_stock.result_ja_ids() == ["JA027001"], (
            f"{length} x {width} x {thickness} did not find the bar"
        )


@pytest.mark.e2e
def test_an_item_too_small_in_every_ordering_is_absent(page, live_server):
    """Story 1 scenario 3, and the reason a negative answer can be trusted.

    `expect_result_count(0)` establishes the region before anything reads it:
    against a table that has not loaded, "the item is absent" would pass for the
    wrong reason.
    """
    live_server.add_test_data([bar("JA027001", length="4", width="3", thickness="0.5")])

    find_stock = FindStockPage(page, live_server.url)
    find_stock.navigate()
    find_stock.search_rectangular(MATERIAL, "0.75", "3", "4")

    find_stock.expect_result_count(0)
    find_stock.expect_no_results()
    find_stock.expect_counters_to_contain("0 of 1")


@pytest.mark.e2e
def test_a_bigger_piece_of_any_shape_is_still_stock(page, live_server):
    """User Story 2: only a square bar and a block on the shelf, both usable.

    Neither is round and neither is the size asked for; both can yield the part.
    """
    live_server.add_test_data([
        bar("JA027002", shape="Square", length="12", width="3"),
        bar("JA027003", length="6", width="6", thickness="6"),
    ])

    find_stock = FindStockPage(page, live_server.url)
    find_stock.navigate()
    find_stock.search_round(MATERIAL, "2", "2")

    find_stock.expect_result_count(2)
    assert sorted(find_stock.result_ja_ids()) == ["JA027002", "JA027003"]


@pytest.mark.e2e
def test_hollow_stock_is_excluded_and_counted(page, live_server):
    """FR-010 and SC-006: a tube's outside dimensions describe a shell.

    The 3" square tube is larger in every outside dimension than the 3" square
    bar that does match, so its absence can only be the hollow rule.
    """
    live_server.add_test_data([
        bar("JA027002", shape="Square", length="12", width="3"),
        bar("JA027004", item_type="Tube", shape="Square",
            length="24", width="4", wall_thickness="0.125"),
    ])

    find_stock = FindStockPage(page, live_server.url)
    find_stock.navigate()
    find_stock.search_round(MATERIAL, "2", "2")

    find_stock.expect_result_count(1)
    assert find_stock.result_ja_ids() == ["JA027002"]
    find_stock.expect_counters_to_contain("1 skipped as hollow")


@pytest.mark.e2e
def test_an_incompletely_recorded_item_is_excluded_and_counted(page, live_server):
    """FR-011: the operator is told how many were skipped for want of a figure."""
    live_server.add_test_data([
        bar("JA027002", shape="Square", length="12", width="3"),
        bar("JA027005", length="12", width="6"),
    ])

    find_stock = FindStockPage(page, live_server.url)
    find_stock.navigate()
    find_stock.search_round(MATERIAL, "2", "2")

    find_stock.expect_result_count(1)
    find_stock.expect_counters_to_contain("1 skipped for a missing dimension")


@pytest.mark.e2e
def test_the_closest_fit_is_at_the_top(page, live_server):
    """User Story 3: the operator takes the first row and stops reading.

    The round bar of exactly the right diameter removes nothing; the square bar
    and the block remove progressively more.
    """
    live_server.add_test_data([
        bar("JA027006", length="24", width="8", thickness="8"),
        bar("JA027007", shape="Square", length="12", width="3"),
        bar("JA027008", shape="Round", length="12", width="2"),
    ])

    find_stock = FindStockPage(page, live_server.url)
    find_stock.navigate()
    find_stock.search_round(MATERIAL, "2", "2")

    find_stock.expect_result_count(3)
    assert find_stock.result_ja_ids() == ["JA027008", "JA027007", "JA027006"]


@pytest.mark.e2e
def test_the_servers_order_survives_first_render_and_sorting_still_works(page, live_server):
    """FR-029, and the guard on `setItems()` never gaining a sort.

    The three JA IDs are assigned so that the fit ranking matches neither
    ascending nor descending JA ID order. A table that re-sorted on entry -- or
    one whose Fit header did nothing -- is caught here rather than passing by
    coincidence.
    """
    live_server.add_test_data([
        bar("JA027009", shape="Square", length="12", width="3"),
        bar("JA027010", shape="Round", length="12", width="2"),
        bar("JA027011", length="24", width="8", thickness="8"),
    ])

    find_stock = FindStockPage(page, live_server.url)
    find_stock.navigate()
    find_stock.search_round(MATERIAL, "2", "2")

    find_stock.expect_result_count(3)
    assert find_stock.result_ja_ids() == ["JA027010", "JA027009", "JA027011"]

    # The table starts out reporting JA ID ascending, so the first click on that
    # header toggles it to descending -- which is neither the arrival order nor
    # the ascending one.
    find_stock.sort_by_column("JA ID")
    assert find_stock.result_ja_ids() == ["JA027011", "JA027010", "JA027009"]

    find_stock.sort_by_column("Fit")
    assert find_stock.result_ja_ids() == ["JA027010", "JA027009", "JA027011"]


@pytest.mark.e2e
def test_a_tolerance_is_opt_in_per_dimension(page, live_server):
    """User Story 4: a bar a hair short, found only once its length may give.

    The same search is run twice against the same inventory: without a tolerance
    the bar is absent, with one on the length alone it is present and marked.
    """
    live_server.add_test_data([
        bar("JA027012", shape="Round", length="1.98", width="2"),
    ])

    find_stock = FindStockPage(page, live_server.url)
    find_stock.navigate()

    find_stock.search_round(MATERIAL, "2", "2")
    find_stock.expect_result_count(0)
    find_stock.expect_no_results()

    find_stock.search_round(MATERIAL, "2", "2", tolerances={"length": "0.02"})
    find_stock.expect_result_count(1)
    assert find_stock.result_ja_ids() == ["JA027012"]

    fit = find_stock.fit_text_for("JA027012")
    assert "Within tolerance" in fit
    assert "Length" in fit


@pytest.mark.e2e
def test_a_refused_request_names_what_is_wrong(page, live_server):
    """FR-017: a tolerance as large as its dimension is refused, naming it.

    The negative-tolerance case is not driven here: the input carries min="0",
    so the browser refuses it before the form ever submits and there is nothing
    on the page to observe. `tests/unit/test_routes.py` covers the server's
    answer to it.
    """
    live_server.add_test_data([bar("JA027001", length="4", width="3", thickness="0.5")])

    find_stock = FindStockPage(page, live_server.url)
    find_stock.navigate()
    find_stock.search_rectangular(MATERIAL, "4", "3", "0.5",
                                  tolerances={"thickness": "0.5"})

    expect(page.locator(find_stock.ERROR)).to_contain_text("Thickness")
