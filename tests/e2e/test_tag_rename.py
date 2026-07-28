"""
E2E tests for the tag rename-and-merge page (DW-48, FR16).

The rename is the only tag mutation the operator has that is not "edit every
carrying product one form at a time", and its distinguishing behavior is the
merge: renaming onto a tag that already exists unions the two rather than
refusing, which is the opposite of the sibling category rename. So the
browser-level path is pinned here: the listing offers a Rename link per assigned
tag, the form previews the tag and its count before it is submitted, a plain
rename retags every carrying product, a rename onto an existing tag merges
without leaving a product carrying it twice or losing an unrelated tag, and a
refused rename comes back on the form having written nothing — the same third
path ``test_category_rename.py`` pins for its own sibling page.

Isolation note: ``tests/e2e/test_server.py``'s ``clear_test_data()`` empties the
catalog by deleting every row of each table in FK order — ``product_tags``
explicitly among them, not by cascade from ``products`` — along with photos and
inventory items, and ``live_server`` is function-scoped, so every test (and
every ``--reruns`` replay, which re-runs setup) starts from an empty catalog.
Each test still mints a fresh unique tag prefix, because "empty at setup" is not
"empty here": by the time a test asserts, the catalog holds the tags that test
just wrote. Assertions are positive (containment) wherever a page is shared with
other tests' data; the few that assert ABSENCE are scoped to one product's own
``#product-tags`` list, where this test wrote every tag present.
"""

import uuid

import pytest
from playwright.sync_api import expect


def _unique_prefix(label):
    """A tag fragment no other test (or rerun) can have created."""
    return f'e2etag-{label}-{uuid.uuid4().hex[:8]}'


def _add_product(page, live_server, description, tags):
    """Create a product carrying `tags` (a comma-separated string); returns its
    detail-page URL."""
    page.goto(f'{live_server.url}/products/add')
    expect(page.locator('#tags')).to_be_visible()
    page.locator('#description').fill(description)
    page.locator('#tags').fill(tags)
    page.locator('button[type="submit"]').click()
    # The detail page renders the stored tags — waiting for one of them also
    # guarantees the redirect has landed before page.url is read.
    expect(page.locator('#product-tags')).to_contain_text(
        tags.split(',')[0].strip(), timeout=10000)
    return page.url


def _open_rename_form(page, live_server, tag):
    """Reach the rename form the way the operator does: from the listing."""
    page.goto(f'{live_server.url}/products/tags')
    link = page.locator(f'a[href="/products/tags/rename?tag={tag}"]')
    expect(link).to_be_visible(timeout=10000)
    link.click()
    expect(page.locator('#new_tag')).to_be_visible(timeout=10000)


@pytest.mark.e2e
def test_rename_retags_every_carrying_product(page, live_server):
    """A plain rename moves every product carrying the tag (FR16)."""
    prefix = _unique_prefix('plain')
    source = f'{prefix}-ssr'
    destination = f'{prefix}-relay'

    first_url = _add_product(page, live_server, 'E2E rename first', source)
    second_url = _add_product(page, live_server, 'E2E rename second', source)

    _open_rename_form(page, live_server, source)

    # The preview names the tag and the count BEFORE submission — it is the
    # confirmation.
    expect(page.locator('#rename-source')).to_have_text(source)
    expect(page.locator('#rename-total')).to_have_text('2')

    page.locator('#new_tag').fill(destination)
    page.get_by_role('button', name='Rename Tag').click()

    # Back on the listing, with a flash reporting what moved. Asserted on the
    # flash text itself rather than on the page as a whole, which also holds the
    # new listing row.
    expect(page.locator('.alert-success')).to_contain_text(
        f'Renamed tag "{source}" to "{destination}" — 2 product(s) updated',
        timeout=10000)

    # Both products carry the new tag and neither carries the old one.
    for url in (first_url, second_url):
        page.goto(url)
        expect(page.locator('#product-tags')).to_contain_text(destination)
        expect(page.locator('#product-tags')).not_to_contain_text(source)


@pytest.mark.e2e
def test_rename_onto_an_existing_tag_merges(page, live_server):
    """A destination that already exists is a MERGE, not a conflict: the
    product carrying both ends up with one copy of the destination and keeps
    every unrelated tag."""
    prefix = _unique_prefix('merge')
    source = f'{prefix}-ssr'
    destination = f'{prefix}-relay'
    bystander = f'{prefix}-keepme'

    moved_url = _add_product(page, live_server, 'E2E merge source', source)
    merged_url = _add_product(page, live_server, 'E2E merge carrier',
                              f'{source}, {destination}, {bystander}')

    _open_rename_form(page, live_server, source)
    expect(page.locator('#rename-total')).to_have_text('2')
    page.locator('#new_tag').fill(destination)
    page.get_by_role('button', name='Rename Tag').click()

    # One product was rewritten and one merged, and the flash says so
    # separately — the merged product's row count went DOWN, which a single
    # "2 product(s) updated" would have misdescribed.
    flash = page.locator('.alert-success')
    expect(flash).to_contain_text(
        f'Renamed tag "{source}" to "{destination}" — 1 product(s) updated',
        timeout=10000)
    expect(flash).to_contain_text(
        f'1 product(s) already carried "{destination}"')

    page.goto(moved_url)
    expect(page.locator('#product-tags')).to_contain_text(destination)

    # The merged product carries the destination ONCE and lost nothing else.
    page.goto(merged_url)
    tags = page.locator('#product-tags')
    expect(tags).to_contain_text(destination)
    expect(tags).to_contain_text(bystander)
    expect(tags).not_to_contain_text(source)
    assert page.locator(
        f'#product-tags a[href="/products/tags/filter?tag={destination}"]'
    ).count() == 1


@pytest.mark.e2e
def test_a_refused_rename_comes_back_on_the_form_and_changes_nothing(
        page, live_server):
    """A refusal must reach the operator as a page, not as a silent no-op.

    The destination here differs from the source only in case, and
    normalization lowercases — so the two are the same tag and there is nothing
    to rename. The form carries ``novalidate``, so the browser posts it and the
    SERVER is what refuses, which is the point: the refusal has to survive the
    round trip with the message visible, the typed value retained, and the tag
    exactly where it was.
    """
    prefix = _unique_prefix('refuse')
    source = f'{prefix}-ssr'
    destination = source.upper()

    product_url = _add_product(page, live_server, 'E2E refusal source', source)

    _open_rename_form(page, live_server, source)
    page.locator('#new_tag').fill(destination)
    page.get_by_role('button', name='Rename Tag').click()

    # Still on the form, with the reason and the typed value intact.
    error = page.locator('#rename-error')
    expect(error).to_be_visible(timeout=10000)
    expect(error).to_contain_text('is already this tag')
    expect(page.locator('#new_tag')).to_have_value(destination)
    # The destination is what was refused, so the destination is what is marked.
    assert 'is-invalid' in page.locator('#new_tag').get_attribute('class')

    # Nothing was written: the product still carries the tag it started with,
    # and the listing still offers to rename it.
    page.goto(product_url)
    expect(page.locator('#product-tags')).to_contain_text(source)
    page.goto(f'{live_server.url}/products/tags')
    expect(page.locator(
        f'a[href="/products/tags/rename?tag={source}"]')).to_be_visible(
            timeout=10000)
