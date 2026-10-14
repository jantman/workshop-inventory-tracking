"""E2E: the Missing filter and Products -> Needs Action (feature 065, issue #209).

**Waiting note.** The product list is server-rendered, so after `goto()` or a
filter-form submit the table rows are in the DOM as soon as the page loads;
`expect(rows).to_have_count(n)` establishes the table before any read of it.
Set Category awaits its POST and only then reloads, so its flashed success
message is a complete signal (render-implies-completion), as in
test_bulk_set_category.py.

Products are seeded straight into the database.
"""

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService
from tests.e2e.waits import wait_for_modal_shown

ROWS = "#product-table tbody tr"


def seed(live_server):
    service = CatalogService(live_server.storage)
    service.create_product(description="Both set", category_path="hardware",
                           location="Shelf A")
    service.create_product(description="No category", location="Shelf A")
    service.create_product(description="No location", category_path="hardware")
    service.create_product(description="Neither")


def expect_listed(page, descriptions):
    """Wait for exactly these products, in description order, to be listed."""
    expect(page.locator(ROWS)).to_have_count(len(descriptions))
    expect(page.locator(f"{ROWS} td.product-description a")).to_have_text(descriptions)


@pytest.mark.e2e
@pytest.mark.parametrize("value, expected", [
    ("category", ["Neither", "No category"]),
    ("location", ["Neither", "No location"]),
    ("either", ["Neither", "No category", "No location"]),
])
def test_the_filter_form_narrows_and_keeps_its_value(page, live_server, value, expected):
    """US1: each Missing choice lists exactly its products and stays selected."""
    seed(live_server)

    page.goto(f"{live_server.url}/products")
    expect(page.locator(ROWS)).to_have_count(4)

    page.locator("#filter-missing").select_option(value)
    page.locator("#apply-filters-btn").click()

    expect(page).to_have_url(f"{live_server.url}/products?" + "&".join([
        "q=", "category=", "tag=", "stock=", "spec_name=", "spec_value=",
        f"missing={value}",
    ]))
    expect_listed(page, expected)
    expect(page.locator("#filter-missing")).to_have_value(value)


@pytest.mark.e2e
def test_the_api_agrees_with_the_page(page, live_server):
    """The page and the search API take the same filters."""
    seed(live_server)

    response = page.request.get(f"{live_server.url}/api/products/search?missing=either")
    assert response.ok
    assert sorted(p["description"] for p in response.json()["products"]) == [
        "Neither", "No category", "No location",
    ]

    response = page.request.get(f"{live_server.url}/api/products/search?missing=banana")
    assert response.status == 400


@pytest.mark.e2e
def test_needs_action_is_in_the_products_menu(page, live_server):
    """US2: Products -> Needs Action lands on the filtered list."""
    seed(live_server)

    page.goto(f"{live_server.url}/")
    expect(page.locator("#products-nav")).to_be_visible()
    page.click("#products-nav")
    link = page.get_by_role("link", name="Needs Action")
    expect(link).to_be_visible()
    link.click()

    expect(page).to_have_url(f"{live_server.url}/products?missing=either")
    expect_listed(page, ["Neither", "No category", "No location"])
    expect(page.locator("#filter-missing")).to_have_value("either")


@pytest.mark.e2e
def test_a_product_given_a_category_leaves_the_list(page, live_server):
    """US3: the existing Set Category fills the gap and the product drops off."""
    seed(live_server)

    page.goto(f"{live_server.url}/products?missing=category")
    expect_listed(page, ["Neither", "No category"])

    page.locator("#product-table tbody tr", has_text="No category") \
        .locator("input.product-checkbox").check()
    page.locator("#bulk-category-btn").click()
    wait_for_modal_shown(page, "bulkCategoryModal")
    page.locator("#bulk-category-input").fill("hardware")
    page.locator("#bulk-category-submit").click()

    expect(page.locator(".alert-success.alert-dismissible",
                        has_text='Set category "hardware" on 1 product.')).to_be_visible()
    expect_listed(page, ["Neither"])
    expect(page.locator("#filter-missing")).to_have_value("category")
