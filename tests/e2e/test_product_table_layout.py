"""E2E: the product list's Location/Sub-location columns and width (feature 066, issue #212).

**Waiting note.** The product list is server-rendered, so after `goto()` the rows
are in the DOM once the page loads; `expect(...)` on the seeded row establishes
the table before any geometry is read from it.

Products are seeded straight into the database.
"""

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService

ROWS = "#product-table tbody tr"


def seed(live_server):
    """One wide row: a long description, several tags, a location and a sub-location."""
    service = CatalogService(live_server.storage)
    service.create_product(
        description=("Socket head cap screw, M6 x 1.0 x 40mm, alloy steel, "
                     "black oxide, fully threaded, DIN 912 / ISO 4762"),
        manufacturer="McMaster-Carr",
        category_path="Hardware/Fasteners/Screws/Socket Head",
        location="Fastener cabinet 2",
        sub_location="Drawer 14, rear bin",
        tags=["metric", "surplus", "din-912", "bulk"],
    )


@pytest.mark.e2e
def test_the_workshop_screen_shows_every_column_without_scrolling(page, live_server):
    """US2: at 1920x915 the table spans the window and Sub-location is in view."""
    seed(live_server)
    page.set_viewport_size({"width": 1920, "height": 915})

    page.goto(f"{live_server.url}/products")
    expect(page.locator(f"{ROWS} td.product-sub-location")).to_have_text("Drawer 14, rear bin")
    expect(page.locator(f"{ROWS} td.product-location")).to_have_text("Fastener cabinet 2")

    table = page.locator("#product-table")
    assert table.bounding_box()["width"] >= 1800

    wrapper = page.locator("#product-table").locator("xpath=..")
    assert wrapper.evaluate("el => el.scrollWidth <= el.clientWidth")
    expect(page.locator("#product-table th", has_text="Sub-location")).to_be_in_viewport()


@pytest.mark.e2e
@pytest.mark.parametrize("width, height", [(768, 1024), (390, 844)])
def test_small_screens_scroll_the_table_not_the_page(page, live_server, width, height):
    """US2: tablets and phones still render; only the table may scroll sideways."""
    seed(live_server)
    page.set_viewport_size({"width": width, "height": height})

    page.goto(f"{live_server.url}/products")
    expect(page.locator(f"{ROWS} td.product-sub-location")).to_have_text("Drawer 14, rear bin")

    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )
