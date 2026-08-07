"""
E2E tests for renaming a category (US1).

The rename is a form post that navigates, so `expect()` on the resulting page is
the whole wait -- there is nothing async to race. What does need care is the
refusal cases: asserting "the tree did not change" against a region nothing has
established would pass just as well against a page that has not loaded, so every
assertion here goes through `expect()` on the rendered tree.

Products are seeded through `live_server.add_test_products` rather than the Add
Product form: these tests need four products across a subtree and the form costs
about three seconds each.
"""

import pytest
from playwright.sync_api import expect


SUBTREE = [
    {'description': 'top widget', 'category_path': 'elctronics'},
    {'description': 'child widget', 'category_path': 'elctronics/passives'},
    {'description': 'deep widget', 'category_path': 'elctronics/passives/resistors'},
    {'description': 'prefix sibling', 'category_path': 'elctronics-surplus'},
]


def open_categories(page, base_url):
    """Load the categories page and wait for the tree to render."""
    page.goto(f"{base_url}/products/categories")
    tree = page.locator("#category-tree")
    expect(tree).to_be_visible()
    return tree


def submit_rename(page, base_url, old_path, new_path):
    """Drive the rename dialog for one row and submit it.

    Returns the categories page's tree locator, established with an expect() so
    that a caller reading it is reading a rendered region.
    """
    open_categories(page, base_url)
    page.locator(f'.rename-btn[data-rename-value="{old_path}"]').click()

    target = page.locator("#rename-new-value")
    expect(target).to_be_visible()
    target.fill(new_path)

    page.locator("#rename-submit").click()

    tree = page.locator("#category-tree")
    expect(tree).to_be_visible()
    return tree


@pytest.mark.e2e
def test_renaming_a_category_carries_its_subtree(page, live_server):
    """FR-001..FR-003: one action moves the category, its children and their products"""
    live_server.add_test_products(SUBTREE)

    tree = submit_rename(page, live_server.url, 'elctronics', 'electronics')

    expect(tree).to_contain_text('electronics/passives/resistors')
    expect(tree.locator('.category-row[data-rename-value="electronics"]')).to_have_count(1)
    expect(tree.locator('.category-row[data-rename-value="electronics/passives"]')).to_have_count(1)
    expect(
        tree.locator('.category-row[data-rename-value="electronics/passives/resistors"]')
    ).to_have_count(1)
    expect(tree.locator('.category-row[data-rename-value="elctronics"]')).to_have_count(0)


@pytest.mark.e2e
def test_a_sibling_sharing_a_prefix_is_untouched(page, live_server):
    """The boundary is the separator: 'elctronics-surplus' is a different category"""
    live_server.add_test_products(SUBTREE)

    tree = submit_rename(page, live_server.url, 'elctronics', 'electronics')

    # The positive assertion establishes the tree has re-rendered post-rename;
    # only then does the untouched sibling mean anything.
    expect(tree.locator('.category-row[data-rename-value="electronics"]')).to_have_count(1)
    expect(
        tree.locator('.category-row[data-rename-value="elctronics-surplus"]')
    ).to_have_count(1)


@pytest.mark.e2e
def test_the_dialog_reports_the_subtree_total_not_the_whole_page(page, live_server):
    """FR-006: told before committing, and told the right number"""
    live_server.add_test_products(SUBTREE)

    open_categories(page, live_server.url)
    page.locator('.rename-btn[data-rename-value="elctronics"]').click()

    impact = page.locator("#rename-impact")
    expect(impact).to_be_visible()
    # Three products in three categories -- the prefix sibling is not among them.
    expect(impact).to_contain_text("3 products")
    expect(impact).to_contain_text("3 categories")


@pytest.mark.e2e
def test_a_colliding_rename_is_refused_and_changes_nothing(page, live_server):
    """FR-004: renaming does not merge categories"""
    live_server.add_test_products(
        SUBTREE + [{'description': 'occupant', 'category_path': 'hardware'}]
    )

    tree = submit_rename(page, live_server.url, 'elctronics', 'hardware')

    expect(page.locator(".alert-danger")).to_contain_text("hardware")
    # Every path is exactly where it was.
    expect(tree.locator('.category-row[data-rename-value="elctronics"]')).to_have_count(1)
    expect(tree.locator('.category-row[data-rename-value="elctronics/passives"]')).to_have_count(1)
    expect(
        tree.locator('.category-row[data-rename-value="elctronics/passives/resistors"]')
    ).to_have_count(1)
    expect(tree.locator('.category-row[data-rename-value="hardware"]')).to_have_count(1)


@pytest.mark.e2e
def test_a_self_nesting_rename_is_refused_and_changes_nothing(page, live_server):
    """FR-005: a category cannot be moved inside itself"""
    live_server.add_test_products(SUBTREE)

    tree = submit_rename(
        page, live_server.url, 'elctronics', 'elctronics/passives/deeper'
    )

    expect(page.locator(".alert-danger")).to_contain_text("inside")
    expect(tree.locator('.category-row[data-rename-value="elctronics"]')).to_have_count(1)
    expect(tree.locator('.category-row[data-rename-value="elctronics/passives"]')).to_have_count(1)
    expect(
        tree.locator('.category-row[data-rename-value="elctronics/passives/resistors"]')
    ).to_have_count(1)


@pytest.mark.e2e
def test_the_renamed_products_are_findable_under_the_new_category(page, live_server):
    """The rename is real in the catalogue, not only on the categories page"""
    live_server.add_test_products(SUBTREE)
    submit_rename(page, live_server.url, 'elctronics', 'electronics')

    page.goto(f"{live_server.url}/products?category=electronics")
    table = page.locator("#product-table")
    expect(table).to_contain_text("top widget")
    expect(table).to_contain_text("deep widget")
    expect(table).not_to_contain_text("prefix sibling")
