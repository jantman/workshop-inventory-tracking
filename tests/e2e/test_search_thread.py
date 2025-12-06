"""
E2E Tests for Search Thread Filters

Tests to verify that the Thread Size and Thread Series filters work correctly on the search form.
"""

import pytest
from tests.e2e.pages.search_page import SearchPage


@pytest.mark.e2e
def test_search_by_thread_size_workflow(page, live_server):
    """Test searching for items by thread size"""
    # Add test data with different thread sizes
    from app.database import InventoryItem

    threaded_rod_1 = InventoryItem(
        ja_id="JA080001",
        item_type="Threaded Rod",
        shape="Round",
        material="Carbon Steel",
        length=36,
        width=0.25,
        thread_series="UNC",
        thread_handedness="Right",
        thread_size="1/4-20",
        location="Storage A",
        notes="1/4-20 threaded rod",
        active=True
    )

    threaded_rod_2 = InventoryItem(
        ja_id="JA080002",
        item_type="Threaded Rod",
        shape="Round",
        material="Stainless Steel",
        length=48,
        width=0.375,
        thread_series="UNC",
        thread_handedness="Right",
        thread_size="3/8-16",
        location="Storage B",
        notes="3/8-16 threaded rod",
        active=True
    )

    threaded_rod_3 = InventoryItem(
        ja_id="JA080003",
        item_type="Threaded Rod",
        shape="Round",
        material="Carbon Steel",
        length=36,
        width=0.5,
        thread_series="UNC",
        thread_handedness="Right",
        thread_size="1/2-13",
        location="Storage C",
        notes="1/2-13 threaded rod",
        active=True
    )

    test_items = [threaded_rod_1, threaded_rod_2, threaded_rod_3]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Verify search form is visible
    search_page.assert_search_form_visible()

    # Search for items with thread size "1/4-20"
    search_page.search_by_thread_size("1/4-20")

    # Verify results - should find only the 1/4-20 rod
    search_page.assert_results_found(1)
    search_page.assert_result_contains_item("JA080001")


@pytest.mark.e2e
def test_search_by_thread_series_workflow(page, live_server):
    """Test searching for items by thread series"""
    # Add test data with different thread series
    from app.database import InventoryItem

    unc_rod = InventoryItem(
        ja_id="JA081001",
        item_type="Threaded Rod",
        shape="Round",
        material="Carbon Steel",
        length=36,
        width=0.25,
        thread_series="UNC",
        thread_handedness="Right",
        thread_size="1/4-20",
        location="Storage A",
        notes="UNC threaded rod",
        active=True
    )

    unf_rod = InventoryItem(
        ja_id="JA081002",
        item_type="Threaded Rod",
        shape="Round",
        material="Stainless Steel",
        length=48,
        width=0.25,
        thread_series="UNF",
        thread_handedness="Right",
        thread_size="1/4-28",
        location="Storage B",
        notes="UNF threaded rod",
        active=True
    )

    metric_rod = InventoryItem(
        ja_id="JA081003",
        item_type="Threaded Rod",
        shape="Round",
        material="Carbon Steel",
        length=1000,
        width=6,
        thread_series="Metric",
        thread_handedness="Right",
        thread_size="M6x1.0",
        location="Storage C",
        notes="Metric threaded rod",
        active=True
    )

    test_items = [unc_rod, unf_rod, metric_rod]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for items with thread series "UNC"
    search_page.search_by_thread_series("UNC")

    # Verify results - should find only the UNC rod
    search_page.assert_results_found(1)
    search_page.assert_result_contains_item("JA081001")


@pytest.mark.e2e
def test_search_by_thread_size_and_series_workflow(page, live_server):
    """Test searching with both thread size and series filters"""
    # Add test data with various combinations
    from app.database import InventoryItem

    unc_quarter_20 = InventoryItem(
        ja_id="JA082001",
        item_type="Threaded Rod",
        shape="Round",
        material="Carbon Steel",
        length=36,
        width=0.25,
        thread_series="UNC",
        thread_handedness="Right",
        thread_size="1/4-20",
        location="Storage A",
        notes="UNC 1/4-20",
        active=True
    )

    unf_quarter_28 = InventoryItem(
        ja_id="JA082002",
        item_type="Threaded Rod",
        shape="Round",
        material="Stainless Steel",
        length=48,
        width=0.25,
        thread_series="UNF",
        thread_handedness="Right",
        thread_size="1/4-28",
        location="Storage B",
        notes="UNF 1/4-28",
        active=True
    )

    unc_half_13 = InventoryItem(
        ja_id="JA082003",
        item_type="Threaded Rod",
        shape="Round",
        material="Carbon Steel",
        length=36,
        width=0.5,
        thread_series="UNC",
        thread_handedness="Right",
        thread_size="1/2-13",
        location="Storage C",
        notes="UNC 1/2-13",
        active=True
    )

    test_items = [unc_quarter_20, unf_quarter_28, unc_half_13]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for UNC threaded rods (should find 2)
    search_page.search_by_thread_series("UNC")

    # Verify results
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA082001")
    search_page.assert_result_contains_item("JA082003")
