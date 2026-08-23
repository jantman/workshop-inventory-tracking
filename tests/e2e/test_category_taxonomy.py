"""
E2E tests for filing into a branch the taxonomy names but nothing occupies (US2).

The point of the feature is the moment before any product exists in a branch:
until 025 the category field suggested only paths already in use, so the first
product into every branch was typed by hand, and that is where two spellings of
one category come from.

The suggestions datalist is filled by a fetch (catalog-suggestions.js), so the
options are not in the DOM when the page load settles. Every assertion about it
goes through expect() on an option locator, which polls -- reading option count
directly would read zero against a datalist that has not been filled yet.
"""

import pytest
from playwright.sync_api import expect


# A branch of docs/category-taxonomy.md that no test seeds a product into.
UNOCCUPIED = "fasteners/machine screws & bolts/socket head cap"
# Another, used where the test needs to occupy one.
OCCUPIED = "electronics/dev boards/arduino"
# Not in the record, and legitimate: the tree is a default, not a whitelist.
OUTSIDE = "workshop/salvage"


def open_categories(page, base_url):
    page.goto(f"{base_url}/products/categories")
    tree = page.locator("#category-tree")
    expect(tree).to_be_visible()
    return tree


def row(tree, path):
    return tree.locator(f'.category-row[data-rename-value="{path}"]')


@pytest.mark.e2e
def test_an_unoccupied_branch_is_offered_while_filing(page, live_server):
    """025 FR-012, SC-009: offered before anything is in it"""
    page.goto(f"{live_server.url}/products/new")

    option = page.locator(
        f'#category-suggestions option[value="{UNOCCUPIED}"]'
    )
    # The datalist is filled by a fetch; expect() polls until it lands.
    expect(option).to_have_count(1)


@pytest.mark.e2e
def test_filing_into_an_unoccupied_branch_stores_the_record_path(page, live_server):
    """025 FR-013: one path, not two near-identical ones"""
    page.goto(f"{live_server.url}/products/new")
    expect(
        page.locator(f'#category-suggestions option[value="{UNOCCUPIED}"]')
    ).to_have_count(1)

    page.fill("#description", "1/4-20 SHCS, 1 inch, stainless")
    page.fill("#category_path", UNOCCUPIED)
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

    tree = open_categories(page, live_server.url)
    # Character-for-character: a variant spelling would render as its own row.
    expect(row(tree, UNOCCUPIED)).to_have_count(1)
    expect(row(tree, UNOCCUPIED)).to_contain_text("1")


@pytest.mark.e2e
def test_an_occupied_taxonomy_branch_appears_once(page, live_server):
    """025 FR-018: offered and occupied are one branch, not two"""
    live_server.add_test_products([
        {'description': 'Arduino Uno R3', 'category_path': OCCUPIED},
    ])

    tree = open_categories(page, live_server.url)
    expect(row(tree, OCCUPIED)).to_have_count(1)


@pytest.mark.e2e
def test_the_rename_control_follows_the_products_not_the_record(page, live_server):
    """Research D4: rename_category refuses a category no product carries.

    So the control belongs on the occupied row and must not appear on the
    unoccupied one, where it could only ever fail.
    """
    live_server.add_test_products([
        {'description': 'Arduino Uno R3', 'category_path': OCCUPIED},
    ])

    tree = open_categories(page, live_server.url)
    # Positive first: this establishes the tree rendered, so the absence below
    # means the button is missing rather than the page.
    expect(row(tree, OCCUPIED).locator(".rename-btn")).to_have_count(1)
    expect(row(tree, UNOCCUPIED).locator(".rename-btn")).to_have_count(0)


@pytest.mark.e2e
def test_a_path_outside_the_taxonomy_still_saves_and_is_marked(page, live_server):
    """025 FR-015: a strong default, not a constraint enforced against the operator"""
    live_server.add_test_products([
        {'description': 'Mystery bracket', 'category_path': OUTSIDE},
    ])

    tree = open_categories(page, live_server.url)
    expect(row(tree, OUTSIDE)).to_have_count(1)
    # 025 FR-019: the divergence between the record and what products carry is
    # visible, because nothing else would surface it.
    expect(row(tree, OUTSIDE).locator(".untaxonomied")).to_have_count(1)
    expect(row(tree, OCCUPIED).locator(".untaxonomied")).to_have_count(0)
