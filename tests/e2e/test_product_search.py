"""
E2E tests for classifying and finding products.

Story 7: nested categories, cross-cutting tags, and a search that reaches
description, specification and identifier alike.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.specification_rows import set_specifications


def create_product(page, base_url, description, category=None, tags=None,
                   specifications=None, mpn=None):
    page.goto(f"{base_url}/products/new")
    page.fill("#description", description)
    if category:
        page.fill("#category_path", category)
    if tags:
        page.fill("#tags", tags)
    if specifications:
        set_specifications(page, specifications)
    if mpn:
        page.fill("#manufacturer_part_number", mpn)
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")


def seed(page, base_url):
    create_product(page, base_url, "Carbon film resistor, 10k",
                   category="Electronics/Passives/Resistors", tags="surplus",
                   specifications=[("Power rating", "1/4W"),
                                   ("Tolerance", "5% tolerance")])
    create_product(page, base_url, "Ceramic capacitor, 100nF",
                   category="Electronics/Passives/Capacitors", tags="rohs",
                   specifications=[("Voltage", "50V"), ("Dielectric", "X7R")])
    create_product(page, base_url, "LM358 op-amp",
                   category="Electronics/Active", tags="surplus, rohs", mpn="LM358N")
    create_product(page, base_url, "M4 hex bolt",
                   category="Hardware/Fasteners", tags="surplus")


def listed(page):
    """Descriptions currently shown in the catalog table"""
    links = page.locator("#product-table tbody tr td:first-child a")
    return sorted(links.nth(i).inner_text().strip() for i in range(links.count()))


@pytest.mark.e2e
def test_a_category_filter_includes_its_sub_categories(page, live_server):
    """Story 7 scenario 1"""
    seed(page, live_server.url)

    page.goto(f"{live_server.url}/products?category=electronics")
    assert listed(page) == [
        "Carbon film resistor, 10k", "Ceramic capacitor, 100nF", "LM358 op-amp",
    ]


@pytest.mark.e2e
def test_a_deeper_category_narrows_further(page, live_server):
    seed(page, live_server.url)

    page.goto(f"{live_server.url}/products?category=electronics/passives")
    assert listed(page) == ["Carbon film resistor, 10k", "Ceramic capacitor, 100nF"]


@pytest.mark.e2e
def test_a_tag_filter_ignores_category(page, live_server):
    """Story 7 scenario 2"""
    seed(page, live_server.url)

    page.goto(f"{live_server.url}/products?tag=surplus")
    assert listed(page) == [
        "Carbon film resistor, 10k", "LM358 op-amp", "M4 hex bolt",
    ]


@pytest.mark.e2e
def test_search_reaches_description_specification_and_identifier(page, live_server):
    """Story 7 scenario 3"""
    seed(page, live_server.url)

    page.goto(f"{live_server.url}/products?q=resistor")
    assert listed(page) == ["Carbon film resistor, 10k"]

    page.goto(f"{live_server.url}/products?q=X7R")
    assert listed(page) == ["Ceramic capacitor, 100nF"]

    page.goto(f"{live_server.url}/products?q=LM358N")
    assert listed(page) == ["LM358 op-amp"]


@pytest.mark.e2e
def test_the_filter_form_drives_the_same_results(page, live_server):
    seed(page, live_server.url)

    page.goto(f"{live_server.url}/products")
    page.fill("#filter-q", "capacitor")
    page.click("#apply-filters-btn")
    page.wait_for_load_state("domcontentloaded")

    assert listed(page) == ["Ceramic capacitor, 100nF"]


@pytest.mark.e2e
def test_a_category_typed_during_creation_is_created_with_no_setup_step(page, live_server):
    """Story 7 scenario 4"""
    create_product(page, live_server.url, "Something new",
                   category="Brand/New/Category")

    page.goto(f"{live_server.url}/products/categories")
    expect(page.locator("#category-tree")).to_contain_text("brand/new/category")


@pytest.mark.e2e
def test_the_category_page_links_into_a_filtered_list(page, live_server):
    seed(page, live_server.url)

    page.goto(f"{live_server.url}/products/categories")
    # 025 put a `fasteners` root on this page, so `text=fasteners` now matches
    # the taxonomy root before the seeded `hardware/fasteners` row and filters
    # to a category with nothing in it. Click the row, not the word.
    page.locator('.category-row[data-rename-value="hardware/fasteners"] a').click()
    page.wait_for_load_state("domcontentloaded")

    # listed() reads with count(), which does not wait. Establish the table
    # first or an unsettled page reads as "no products" and the assertion
    # fails for a reason that has nothing to do with the filter.
    expect(page.locator("#product-table tbody tr")).to_have_count(1)
    assert listed(page) == ["M4 hex bolt"]


@pytest.mark.e2e
def test_an_empty_category_cannot_exist(page, live_server):
    """Removing the last product in a category removes the category"""
    create_product(page, live_server.url, "Only member", category="Temporary/Category")

    page.goto(f"{live_server.url}/products/categories")
    expect(page.locator("#category-tree")).to_contain_text("temporary/category")

    page.goto(f"{live_server.url}/products")
    page.click("#product-table tbody tr td:first-child a")
    page.click("text=Edit")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#category_path", "")
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

    page.goto(f"{live_server.url}/products/categories")
    tree = page.locator("#category-tree")
    # The tree is never empty now -- 025 puts every taxonomy branch on it -- so
    # establish that it rendered before reading the absence of one row, which
    # would otherwise pass just as well against a page that had not loaded.
    expect(tree.locator('.category-row[data-rename-value="fasteners"]')).to_have_count(1)
    expect(
        tree.locator('.category-row[data-rename-value="temporary/category"]')
    ).to_have_count(0)


@pytest.mark.e2e
def test_category_and_tag_suggestions_are_offered(page, live_server):
    """Suggestions only -- typing something new is how one gets created"""
    seed(page, live_server.url)

    page.goto(f"{live_server.url}/products/new")

    # Both datalists are empty in the served HTML and filled by
    # catalog-suggestions.js once GET /api/categories and GET /api/tags resolve.
    # count() does not wait, so without this both reads are 0 and the assertions
    # below fail for a reason that has nothing to do with what they test.
    page.wait_for_function(
        "() => document.querySelectorAll('#category-suggestions option').length >= 4"
        "   && document.querySelectorAll('#tag-suggestions option').length >= 2"
    )

    categories = page.locator("#category-suggestions option")
    tags = page.locator("#tag-suggestions option")
    assert categories.count() >= 4
    assert tags.count() >= 2


@pytest.mark.e2e
def test_the_search_api_returns_the_same_matches(page, live_server):
    seed(page, live_server.url)
    page.goto(live_server.url)

    result = page.evaluate(
        """async () => {
            const r = await fetch('/api/products/search?category=electronics&tag=surplus');
            return await r.json();
        }"""
    )

    assert result["success"] is True
    assert sorted(p["description"] for p in result["products"]) == [
        "Carbon film resistor, 10k", "LM358 op-amp",
    ]
