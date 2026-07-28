"""
E2E tests for free-form product tags (Story 3.3, FR16).

Tags are the retrieval affordance a category hierarchy cannot express, and the
whole point is the round trip: typed on the product form, rendered as a link on
the detail page, and followed to exactly the products carrying that tag whatever
their categories. The tag input's multi-value autocomplete has no unit-test
surface either — there is no JS test infra in this project — so the browser-level
behavior is pinned here.

Isolation note: ``tests/e2e/test_server.py``'s ``clear_test_data()`` truncates
``products`` and ``product_tags`` along with photos and inventory items (and
re-seeds the material taxonomy rather than leaving it empty), and
``live_server`` is function-scoped, so every test — and
every ``--reruns`` replay, which re-runs setup — starts from an empty catalog.
Each test still mints a fresh unique tag prefix and asserts on containment
rather than on counts, ordering, or "nothing else is here": it costs nothing,
and by the time a test asserts, the catalog holds that test's own rows.

An absence assertion is allowed only when the text it looks for CARRIES the
run-unique prefix — no row this test did not write can contain it, so the
assertion cannot decay. Asserting the absence of anything else (a bare tag
name, a shared description, a count) is a bet on the database being clean.
"""

import uuid

import pytest
from playwright.sync_api import expect


def _unique_prefix(label):
    """A tag no other test (or rerun) can have created."""
    return f'e2etag-{label}-{uuid.uuid4().hex[:8]}'


def _add_product(page, live_server, description, tags):
    """Create a product carrying `tags` (a comma-separated string); returns its
    detail-page URL."""
    page.goto(f'{live_server.url}/products/add')
    expect(page.locator('#tags')).to_be_visible()
    page.locator('#description').fill(description)
    page.locator('#tags').fill(tags)
    page.locator('button[type="submit"]').click()
    # The detail page renders the description — waiting for it also guarantees
    # the redirect has landed before page.url is read.
    expect(page.locator('body')).to_contain_text(description, timeout=10000)
    return page.url


@pytest.mark.e2e
def test_tags_round_trip_from_the_form_to_the_filter(page, live_server):
    """A tag typed on the form is shown on the detail page as a link, and that
    link lists exactly the products carrying it (FR16)."""
    shared = _unique_prefix('shared')
    other = _unique_prefix('other')
    tagged_a = f'E2E tag product A {shared}'
    tagged_b = f'E2E tag product B {shared}'
    untagged = f'E2E tag product C {shared}'

    first_url = _add_product(page, live_server, tagged_a, f'{shared}, spare')
    _add_product(page, live_server, tagged_b, shared.upper())
    _add_product(page, live_server, untagged, other)

    # The detail page shows the tag, canonicalized, as a badge link.
    page.goto(first_url)
    tags_cell = page.locator('#product-tags')
    expect(tags_cell).to_contain_text(shared, timeout=10000)

    # Follow the badge the way the operator does.
    tags_cell.locator(f'a:text-is("{shared}")').click()
    expect(page.locator('#filter-tag')).to_have_text(shared, timeout=10000)

    # Both tagged products are listed — including the one that typed the tag in
    # upper case, which proves the canonical form is what got stored.
    table = page.locator('#tagged-product-table')
    expect(table).to_contain_text(tagged_a, timeout=10000)
    expect(table).to_contain_text(tagged_b)
    # The product carrying a different tag is not in this table.
    expect(table).not_to_contain_text(untagged)


@pytest.mark.e2e
def test_the_tag_listing_links_to_the_filter(page, live_server):
    """The vocabulary page offers every assigned tag with its product count."""
    tag = _unique_prefix('listing')
    description = f'E2E tag listing product {tag}'

    _add_product(page, live_server, description, tag)

    page.goto(f'{live_server.url}/products/tags')
    row = page.locator('#tag-table tr', has_text=tag)
    expect(row).to_be_visible(timeout=10000)
    # Scoped to the filter link by href, not a bare `a`: DW-48 gave every row a
    # second action (Rename), so a bare locator is a strict-mode violation
    # rather than a miss — and this test is about the FILTER link specifically.
    row.locator('a[href*="/products/tags/filter"]').click()

    expect(page.locator('#filter-tag')).to_have_text(tag, timeout=10000)
    expect(page.locator('#tagged-product-table')).to_contain_text(
        description, timeout=10000)


@pytest.mark.e2e
def test_the_tag_input_autocompletes_after_a_comma(page, live_server):
    """The multi-value autocomplete queries only the fragment after the last
    separator, so an existing tag is offered while a SECOND tag is being typed —
    and selecting it appends rather than overwriting the first (AD-14)."""
    existing = _unique_prefix('autocomplete')
    kept = _unique_prefix('kept')

    # Seed the vocabulary: a tag is only offered once some product carries it.
    _add_product(page, live_server, f'E2E tag seed {existing}', existing)

    page.goto(f'{live_server.url}/products/add')
    tags = page.locator('#tags')
    expect(tags).to_be_visible()
    page.locator('#description').fill('E2E tag autocomplete')

    # First tag committed with a comma, then a fragment of a second one. The
    # fragment is the UNIQUE suffix, not a leading slice: `product_tags` is
    # never cleared, so every previous run of this test left an
    # `e2etag-autocomplete-*` tag behind, and a shared prefix would eventually
    # push this run's own tag past the endpoint's 10-suggestion cap. Matching
    # is a substring LIKE, so a suffix filters just as well and cannot collide.
    tags.fill(f'{kept}, {existing[-8:]}')

    dropdown = page.locator('#tags-suggestions')
    expect(dropdown).to_be_visible(timeout=5000)
    expect(dropdown).to_contain_text(existing, timeout=5000)

    dropdown.locator('.dropdown-item', has_text=existing).first.click()

    # The committed tag survived, the fragment was replaced by the full tag,
    # and the field is ready for the next one.
    expect(tags).to_have_value(f'{kept}, {existing}, ')
    expect(dropdown).to_be_hidden()

    # Still on the form — no tag had to be defined anywhere else first.
    page.locator('button[type="submit"]').click()
    expect(page.locator('#product-tags')).to_contain_text(existing, timeout=10000)
    expect(page.locator('#product-tags')).to_contain_text(kept)


@pytest.mark.e2e
def test_a_tag_the_field_already_carries_is_not_offered_again(page, live_server):
    """A suggestion the field already holds is filtered out of the dropdown,
    CASE-INSENSITIVELY.

    The server de-duplicates on save, so offering it would show the operator
    something other than what gets stored (`SSR, ss` completing to
    `SSR, ssr, `). On the add form every value in the field is what the
    operator typed, in whatever case they typed it — so comparing the exact
    text, as the filter first did, misses the ordinary case.
    """
    shared = _unique_prefix('dupfilter')
    taken = f'{shared}-taken'
    free = f'{shared}-free'

    # One product carries both, so both are in the vocabulary.
    _add_product(page, live_server, f'E2E dup filter seed {shared}',
                 f'{taken}, {free}')

    page.goto(f'{live_server.url}/products/add')
    tags = page.locator('#tags')
    expect(tags).to_be_visible()

    # The field already carries `taken` — typed in UPPER case, which is what an
    # operator does and what the stored form never looks like. The fragment
    # matches both seeded tags.
    tags.fill(f'{taken.upper()}, {shared}')

    dropdown = page.locator('#tags-suggestions')
    expect(dropdown).to_be_visible(timeout=5000)
    expect(dropdown).to_contain_text(free, timeout=5000)
    # Absence is safe here only because the text carries this run's unique
    # prefix — no row this test did not write can contain it.
    expect(dropdown).not_to_contain_text(taken)


@pytest.mark.e2e
def test_completing_a_middle_tag_leaves_the_caret_where_it_was(page, live_server):
    """The fragment being completed is the one the CARET sits in, and the caret
    stays with it.

    Assigning `input.value` parks the caret at the end of the field in every
    browser, so without restoring it the operator who completes the FIRST of two
    tags finds their next keystroke landing on the last one instead (AD-14).
    """
    existing = _unique_prefix('caret')
    kept = _unique_prefix('kept')

    _add_product(page, live_server, f'E2E caret seed {existing}', existing)

    page.goto(f'{live_server.url}/products/add')
    tags = page.locator('#tags')
    expect(tags).to_be_visible()

    # A finished second tag, and an unfinished FIRST one for the caret to sit
    # in. The dropdown opens on the fragment the caret is in, not the last one.
    fragment = existing[-8:]
    tags.fill(f'{fragment}, {kept}')
    tags.evaluate(
        """(el, pos) => {
            el.focus();
            el.setSelectionRange(pos, pos);
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }""",
        len(fragment))

    dropdown = page.locator('#tags-suggestions')
    expect(dropdown).to_be_visible(timeout=5000)
    expect(dropdown).to_contain_text(existing, timeout=5000)
    dropdown.locator('.dropdown-item', has_text=existing).first.click()

    # The first tag was completed, the second survived untouched, and no stray
    # separator was injected in the middle.
    expect(tags).to_have_value(f'{existing}, {kept}')
    assert tags.evaluate('el => el.selectionStart') == len(existing), \
        'the caret jumped away from the tag that was just completed'
