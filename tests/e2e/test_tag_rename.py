"""
E2E tests for renaming and merging a tag (US2).

Same shape as the category rename tests: the submit is a form post that
navigates, so `expect()` on the resulting list is the whole wait. Products are
seeded directly -- the Add Product form is not what is under test here.
"""

import pytest
from playwright.sync_api import expect


NEAR_DUPLICATES = [
    {'description': 'misspelled widget', 'tags': ['surpluss']},
    {'description': 'correct widget', 'tags': ['surplus']},
    {'description': 'both widget', 'tags': ['surpluss', 'surplus']},
]


def open_tags(page, base_url):
    """Load the tags page and wait for the list to render."""
    page.goto(f"{base_url}/products/tags")
    tags = page.locator("#tag-list")
    expect(tags).to_be_visible()
    return tags


def submit_rename(page, base_url, old_name, new_name):
    """Drive the rename dialog for one tag row and submit it."""
    open_tags(page, base_url)
    page.locator(f'.rename-btn[data-rename-value="{old_name}"]').click()

    target = page.locator("#rename-new-value")
    expect(target).to_be_visible()
    target.fill(new_name)

    page.locator("#rename-submit").click()

    tags = page.locator("#tag-list")
    expect(tags).to_be_visible()
    return tags


@pytest.mark.e2e
def test_the_page_shows_both_spellings_with_their_counts(page, live_server):
    """FR-013: a near-duplicate cannot be corrected until it can be seen"""
    live_server.add_test_products(NEAR_DUPLICATES)

    tags = open_tags(page, live_server.url)

    expect(tags.locator('.tag-row[data-rename-value="surpluss"]')).to_have_count(1)
    expect(tags.locator('.tag-row[data-rename-value="surplus"]')).to_have_count(1)
    expect(
        tags.locator('.tag-row[data-rename-value="surpluss"] .badge')
    ).to_have_text("2")
    expect(
        tags.locator('.tag-row[data-rename-value="surplus"] .badge')
    ).to_have_text("2")


@pytest.mark.e2e
def test_a_plain_rename_keeps_the_products(page, live_server):
    """FR-008: the target is free, so this is a rename and not a merge"""
    live_server.add_test_products(
        [{'description': 'misspelled widget', 'tags': ['surpluss']}]
    )

    tags = submit_rename(page, live_server.url, 'surpluss', 'newname')

    expect(tags.locator('.tag-row[data-rename-value="newname"]')).to_have_count(1)
    expect(tags.locator('.tag-row[data-rename-value="surpluss"]')).to_have_count(0)
    expect(tags.locator('.tag-row[data-rename-value="newname"] .badge')).to_have_text("1")


@pytest.mark.e2e
def test_the_dialog_says_merge_when_the_target_is_in_use(page, live_server):
    """FR-011: the operator is told it is a merge before committing to one"""
    live_server.add_test_products(NEAR_DUPLICATES)

    open_tags(page, live_server.url)
    page.locator('.rename-btn[data-rename-value="surpluss"]').click()

    impact = page.locator("#rename-impact")
    expect(impact).to_be_visible()
    page.locator("#rename-new-value").fill("surplus")
    expect(impact).to_contain_text("MERGE")


@pytest.mark.e2e
def test_renaming_onto_an_existing_tag_merges_them(page, live_server):
    """FR-009/FR-010: one tag remains, carrying all three, each exactly once"""
    live_server.add_test_products(NEAR_DUPLICATES)

    tags = submit_rename(page, live_server.url, 'surpluss', 'surplus')

    expect(tags.locator('.tag-row[data-rename-value="surplus"]')).to_have_count(1)
    expect(tags.locator('.tag-row[data-rename-value="surpluss"]')).to_have_count(0)
    # Three products, not four: the one that carried both carries the survivor
    # once, which is what the composite key would have raised over.
    expect(tags.locator('.tag-row[data-rename-value="surplus"] .badge')).to_have_text("3")


@pytest.mark.e2e
def test_the_merged_tag_finds_every_product(page, live_server):
    """The merge is real in the catalog, not only on the tags page"""
    live_server.add_test_products(NEAR_DUPLICATES)
    submit_rename(page, live_server.url, 'surpluss', 'surplus')

    page.goto(f"{live_server.url}/products?tag=surplus")
    table = page.locator("#product-table")
    expect(table).to_contain_text("misspelled widget")
    expect(table).to_contain_text("correct widget")
    expect(table).to_contain_text("both widget")


@pytest.mark.e2e
def test_a_product_carrying_both_ends_up_with_the_survivor_once(page, live_server):
    """FR-010, on the product itself rather than on the count"""
    live_server.add_test_products(NEAR_DUPLICATES)
    submit_rename(page, live_server.url, 'surpluss', 'surplus')

    page.goto(f"{live_server.url}/products?tag=surplus")
    row = page.locator("#product-table tr", has_text="both widget")
    expect(row).to_have_count(1)
    expect(row.locator(".badge", has_text="surplus")).to_have_count(1)


# ---------------------------------------------------------------------------
# Collation regression. These belong here rather than in tests/unit/ because the
# bug they cover cannot exist on SQLite: it needs MariaDB's utf8mb4_unicode_ci,
# which resolves to ...uca1400_ai_ci and folds accents, so 'würth' = 'wurth' is
# true in SQL and false in Python. The unit suite runs on SQLite's BINARY
# collation and passes either way; the e2e testcontainer is configured with the
# deployed collation, so only a test here can fail when this regresses.
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_removing_an_accent_renames_the_tag_and_keeps_its_products(page, live_server):
    """Regression: this used to delete the tag and strip it from every product.

    The rename/merge decision compared strings in Python but looked the survivor
    up in SQL. Under a folding collation the lookup returned the source row
    itself, so the merge branch moved nothing and then deleted the only tag.
    """
    live_server.add_test_products([
        {'description': f'accented widget {i}', 'tags': ['würth']}
        for i in range(5)
    ])

    tags = submit_rename(page, live_server.url, 'würth', 'wurth')

    expect(tags.locator('.tag-row[data-rename-value="wurth"]')).to_have_count(1)
    expect(tags.locator('.tag-row[data-rename-value="wurth"] .badge')).to_have_text("5")
    expect(tags.locator('.tag-row[data-rename-value="würth"]')).to_have_count(0)

    # The associations survived, which is the part that was being destroyed.
    page.goto(f"{live_server.url}/products?tag=wurth")
    table = page.locator("#product-table")
    expect(table).to_contain_text("accented widget 0")
    expect(table.locator("tbody tr")).to_have_count(5)


@pytest.mark.e2e
def test_a_stale_page_cannot_destroy_a_tag(page, live_server):
    """The server decides from the stored name, not from what the page showed.

    Submitting `old_name` as rendered is the documented design: the page is a
    courtesy and the server re-validates. That only holds if the guard compares
    the *stored* name -- a stale "würth" still finds the row a folding collation
    considers equal, and the old code took that for a merge and deleted it.

    Renaming through the UI always submits the current name, so this state is
    only reachable when the tag changed after the page was drawn. That is
    precisely the case the server is supposed to be authoritative for.
    """
    from app.catalog_service import CatalogService

    live_server.add_test_products([{'description': 'plain widget', 'tags': ['würth']}])

    tags = open_tags(page, live_server.url)
    expect(tags.locator('.tag-row[data-rename-value="würth"]')).to_have_count(1)

    # The tag changes behind the page's back; the rendered button is now stale.
    CatalogService(live_server.storage).rename_tag('würth', 'wurth')

    page.locator('.rename-btn[data-rename-value="würth"]').click()
    target = page.locator("#rename-new-value")
    expect(target).to_be_visible()
    target.fill("wurth")
    page.locator("#rename-submit").click()

    tags = page.locator("#tag-list")
    expect(tags).to_be_visible()
    expect(page.locator(".alert-danger")).to_contain_text("Nothing to rename")
    expect(tags.locator('.tag-row[data-rename-value="wurth"]')).to_have_count(1)
    expect(tags.locator('.tag-row[data-rename-value="wurth"] .badge')).to_have_text("1")
