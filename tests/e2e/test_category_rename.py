"""
E2E tests for the category listing and rename-with-descendants pages
(Story 3.2, FR17).

The rename is the one category mutation the operator has, and its whole value
is that it carries descendants atomically — so the browser-level path is pinned
here: the listing offers a Rename link per assigned path, the form previews
exactly what will move before it is submitted, a successful rename refiles every
product in the subtree, and a colliding rename explains itself and changes
nothing.

Isolation note: ``tests/e2e/test_server.py``'s ``clear_test_data()`` truncates
``products`` along with photos and inventory items (and re-seeds the material
taxonomy rather than leaving it empty), and ``live_server`` is function-scoped, so every test — and every ``--reruns``
replay, which re-runs setup — starts from an empty catalog. Each test still
mints a fresh unique path prefix and asserts only positively (containment),
never absence: it costs nothing, and "empty at setup" is not "empty here" —
by the time a test asserts, the catalog holds the paths that test just wrote.
"""

import uuid

import pytest
from playwright.sync_api import expect


def _unique_prefix(label):
    """A category segment no other test (or rerun) can have created."""
    return f'e2eren-{label}-{uuid.uuid4().hex[:8]}'


def _add_product(page, live_server, description, category_path):
    """Create a product at `category_path`; returns its detail-page URL."""
    page.goto(f'{live_server.url}/products/add')
    expect(page.locator('#category_path')).to_be_visible()
    page.locator('#description').fill(description)
    page.locator('#category_path').fill(category_path)
    page.locator('button[type="submit"]').click()
    # The detail page renders the stored path — waiting for it also guarantees
    # the redirect has landed before page.url is read.
    expect(page.locator('body')).to_contain_text(category_path, timeout=10000)
    return page.url


def _open_rename_form(page, live_server, path):
    """Reach the rename form the way the operator does: from the listing."""
    page.goto(f'{live_server.url}/products/categories')
    link = page.locator(f'a[href="/products/categories/rename?path={path}"]')
    expect(link).to_be_visible(timeout=10000)
    link.click()
    expect(page.locator('#new_path')).to_be_visible(timeout=10000)


@pytest.mark.e2e
def test_rename_carries_descendants_through_the_form(page, live_server):
    """Renaming a node refiles it AND everything under it (FR17)."""
    prefix = _unique_prefix('carry')
    parent = f'{prefix}/power'
    child = f'{prefix}/power/dc-dc'
    renamed_parent = f'{prefix}/psu'
    renamed_child = f'{prefix}/psu/dc-dc'

    parent_url = _add_product(page, live_server, 'E2E rename parent', parent)
    child_url = _add_product(page, live_server, 'E2E rename child', child)

    _open_rename_form(page, live_server, parent)

    # The preview names the subtree and the product count BEFORE submission —
    # it is the confirmation.
    expect(page.locator('#affected-table')).to_contain_text(parent)
    expect(page.locator('#affected-table')).to_contain_text(child)
    expect(page.locator('#rename-total')).to_have_text('2')

    page.locator('#new_path').fill(renamed_parent)
    page.get_by_role('button', name='Rename Category').click()

    # Back on the listing, with a flash reporting what moved. Asserted on the
    # flash text itself: a bare containment check for `renamed_parent` would
    # also be satisfied by the listing row for `renamed_child`, which contains
    # it as a prefix — i.e. it would pass if only the child had moved.
    expect(page.locator('.alert-success')).to_contain_text(
        f'Renamed category "{parent}" to "{renamed_parent}" — 2 product(s) updated',
        timeout=10000)

    # Both products are refiled — the descendant kept its own suffix.
    page.goto(parent_url)
    expect(page.locator('body')).to_contain_text(renamed_parent)
    page.goto(child_url)
    expect(page.locator('body')).to_contain_text(renamed_child)


@pytest.mark.e2e
def test_colliding_rename_is_refused_and_changes_nothing(page, live_server):
    """A destination node that already holds products is a conflict, not a
    merge: the form re-renders with the reason and the path is untouched."""
    prefix = _unique_prefix('collide')
    source = f'{prefix}/power'
    destination = f'{prefix}/psu'

    source_url = _add_product(page, live_server, 'E2E collide source', source)
    _add_product(page, live_server, 'E2E collide blocker', destination)

    _open_rename_form(page, live_server, source)
    page.locator('#new_path').fill(destination)
    page.get_by_role('button', name='Rename Category').click()

    # Still on the form, with an explanation and the typed value retained.
    expect(page.locator('#rename-error')).to_be_visible(timeout=10000)
    expect(page.locator('#rename-error')).to_contain_text('already exists')
    expect(page.locator('#new_path')).to_have_value(destination)

    # The source product never moved.
    page.goto(source_url)
    expect(page.locator('body')).to_contain_text(source)
