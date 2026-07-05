"""
Dimensions Column Display Tests

Verifies the formatting of the shared inventory table's "Dimensions" column
(rendered by formatFullDimensions in item-formatters.js) across both the
inventory list (/inventory) and advanced search (/inventory/search) views.

Two behaviors are covered:
  1. The length is NOT duplicated into the Dimensions column (it has its own
     dedicated Length column).
  2. When present and non-zero, the wall thickness is shown as an additional
     dimension.
"""

import pytest

from tests.e2e.pages.inventory_list_page import InventoryListPage
from tests.e2e.pages.search_page import SearchPage


# One item per shape/wall-thickness combination exercised by formatFullDimensions.
# Lengths are chosen so they cannot appear as a substring of any dimension value.
DIMENSION_ITEMS = [
    {
        # Round bar, no wall thickness -> "⌀20""
        "ja_id": "JA070001",
        "item_type": "Bar",
        "shape": "Round",
        "material": "Carbon Steel",
        "length": "250",
        "width": "20",
        "location": "Test Storage A",
        "active": True,
    },
    {
        # Round tube, with wall thickness -> "⌀2" × 0.125""
        "ja_id": "JA070002",
        "item_type": "Tube",
        "shape": "Round",
        "material": "Aluminum",
        "length": "96",
        "width": "2",
        "wall_thickness": "0.125",
        "location": "Test Storage A",
        "active": True,
    },
    {
        # Rectangular bar, no wall thickness -> "3" × 0.5""
        "ja_id": "JA070003",
        "item_type": "Bar",
        "shape": "Rectangular",
        "material": "Carbon Steel",
        "length": "24",
        "width": "3",
        "thickness": "0.5",
        "location": "Test Storage A",
        "active": True,
    },
    {
        # Rectangular tube, with wall thickness -> "8" × 4" × 0.125""
        "ja_id": "JA070004",
        "item_type": "Tube",
        "shape": "Rectangular",
        "material": "Aluminum",
        "length": "72",
        "width": "8",
        "thickness": "4",
        "wall_thickness": "0.125",
        "location": "Test Storage A",
        "active": True,
    },
]

# Expected Dimensions cell text keyed by JA ID.
EXPECTED_DIMENSIONS = {
    "JA070001": '⌀20"',
    "JA070002": '⌀2" × 0.125"',
    "JA070003": '3" × 0.5"',
    "JA070004": '8" × 4" × 0.125"',
}

# Expected Length cell text keyed by JA ID (length lives in its own column).
EXPECTED_LENGTH = {
    "JA070001": '250"',
    "JA070002": '96"',
    "JA070003": '24"',
    "JA070004": '72"',
}


def _load_page(page, live_server, page_type):
    """Load the requested table page with all items visible."""
    if page_type == "list":
        test_page = InventoryListPage(page, live_server.url)
        test_page.navigate()
        test_page.wait_for_items_loaded()
    else:  # search
        test_page = SearchPage(page, live_server.url)
        test_page.navigate()
        # Empty criteria returns all items.
        test_page.click_search()
    return test_page


@pytest.mark.e2e
@pytest.mark.parametrize("page_type", ["list", "search"])
def test_dimensions_column_excludes_length(page, live_server, page_type):
    """The Dimensions column must not repeat the length shown in the Length column."""
    live_server.add_test_data(DIMENSION_ITEMS)

    test_page = _load_page(page, live_server, page_type)

    rows = {item["ja_id"]: item for item in test_page.get_table_items()}

    for ja_id, expected_length in EXPECTED_LENGTH.items():
        assert ja_id in rows, f"{ja_id} not shown on {page_type} page"
        dimensions_cell = rows[ja_id]["dimensions"]
        length_cell = rows[ja_id]["length"]

        # Length is shown in its own column...
        assert length_cell == expected_length, (
            f"{ja_id} Length column: expected {expected_length!r}, got {length_cell!r}"
        )
        # ...and must NOT be duplicated into the Dimensions column.
        length_value = expected_length.rstrip('"')
        assert length_value not in dimensions_cell, (
            f"{ja_id} Dimensions column {dimensions_cell!r} unexpectedly "
            f"contains the length value {length_value!r}"
        )


@pytest.mark.e2e
@pytest.mark.parametrize("page_type", ["list", "search"])
def test_dimensions_column_shows_wall_thickness(page, live_server, page_type):
    """The Dimensions column shows width/thickness and, when present, wall thickness."""
    live_server.add_test_data(DIMENSION_ITEMS)

    test_page = _load_page(page, live_server, page_type)

    rows = {item["ja_id"]: item for item in test_page.get_table_items()}

    for ja_id, expected in EXPECTED_DIMENSIONS.items():
        assert ja_id in rows, f"{ja_id} not shown on {page_type} page"
        dimensions_cell = rows[ja_id]["dimensions"]
        assert dimensions_cell == expected, (
            f"{ja_id} Dimensions column: expected {expected!r}, got {dimensions_cell!r}"
        )
