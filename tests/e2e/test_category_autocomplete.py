"""
E2E tests for the product form's category autocomplete-with-create
(Story 3.1, FR13/FR14/FR15).

The create affordance has no unit-test surface — there is no JS test infra in
this project — so the browser-level behavior is pinned here: a never-before-seen
path is offered as a create entry showing the CANONICAL form the server would
store (never a value the browser derived), selecting it fills the input without
leaving the form, and once saved the path is offered as an ordinary suggestion
on the next product entry (the tree accretes from use).

Isolation note: ``tests/e2e/test_server.py``'s ``clear_test_data()`` clears
photos, inventory items and the material taxonomy but NOT ``products``, so
product rows accumulate across the session — and ``--reruns`` can replay a test
whose product already landed. Every test therefore mints a fresh unique path
prefix and asserts only positively (containment), never absence.
"""

import uuid

import pytest
from playwright.sync_api import expect


def _unique_prefix(label):
    """A category segment no other test (or rerun) can have created."""
    return f'e2ecat-{label}-{uuid.uuid4().hex[:8]}'


def _expect_dropdown_visible(page, contains_text=None):
    dropdown = page.locator('#category_path-suggestions')
    expect(dropdown).to_be_visible(timeout=5000)
    if contains_text is not None:
        expect(dropdown).to_contain_text(contains_text, timeout=5000)
    return dropdown


def _add_product(page, live_server, description, category_path):
    """Fill and submit the Add Product form; returns the resulting page."""
    page.goto(f'{live_server.url}/products/add')
    expect(page.locator('#category_path')).to_be_visible()
    page.locator('#description').fill(description)
    page.locator('#category_path').fill(category_path)
    page.locator('button[type="submit"]').click()
    return page


@pytest.mark.e2e
def test_novel_category_offers_create_and_stores_canonical(page, live_server):
    """Typing a never-before-seen path offers `+ Create "<canonical>"`;
    choosing it fills the input with the canonical form and saving stores
    exactly that (FR13, FR14)."""
    prefix = _unique_prefix('alpha')
    typed = f'{prefix.upper()}/Power Supplies/'
    canonical = f'{prefix}/power supplies'

    page.goto(f'{live_server.url}/products/add')
    expect(page.locator('#category_path')).to_be_visible()

    page.locator('#description').fill('E2E category create')
    category = page.locator('#category_path')
    category.fill(typed)

    # The entry shows the value the SERVER says would be stored — the browser
    # never normalizes anything itself.
    dropdown = _expect_dropdown_visible(page, contains_text=f'+ Create "{canonical}"')

    dropdown.locator('.dropdown-item', has_text='+ Create').click()
    expect(category).to_have_value(canonical)
    expect(dropdown).to_be_hidden()

    # Still on the form — no taxonomy screen was ever visited.
    expect(page.locator('#description')).to_have_value('E2E category create')
    page.locator('button[type="submit"]').click()

    expect(page.locator('body')).to_contain_text(canonical, timeout=10000)
    expect(page.locator('body')).to_contain_text('E2E category create')


@pytest.mark.e2e
def test_escape_dismisses_the_dropdown_for_good(page, live_server):
    """Escape must close the dropdown and keep it closed.

    Typing schedules a debounced fetch ~200ms out; if Escape only hid the
    dropdown, that fetch would re-open it a moment later with the field no
    longer focused, leaving a create entry sitting over the Save button where
    a click meant for Save lands on the entry's mousedown instead. With
    allowCreate the dropdown opens even when nothing matched — the ordinary
    case for a brand-new path — so this is widest on the very flow the create
    affordance exists for.
    """
    prefix = _unique_prefix('esc')

    page.goto(f'{live_server.url}/products/add')
    category = page.locator('#category_path')
    expect(category).to_be_visible()

    category.fill(f'{prefix}/Never Saved')
    dropdown = _expect_dropdown_visible(page, contains_text='+ Create')

    # One more keystroke, then Escape before the 200ms debounce can fire —
    # the whole point. Dispatched together so the window cannot be lost to
    # inter-command latency; both land on the component's real listeners.
    page.evaluate(
        """() => {
            const input = document.getElementById('category_path');
            input.value += 'x';
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(
                new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        }"""
    )
    expect(dropdown).to_be_hidden()

    # Well past the 200ms debounce: nothing in flight or scheduled may bring
    # it back.
    page.wait_for_timeout(700)
    expect(dropdown).to_be_hidden()


@pytest.mark.e2e
def test_escape_dismisses_a_dropdown_that_has_not_opened_yet(page, live_server):
    """Escape must also cancel a fetch scheduled but not yet rendered.

    The widest form of the race the test above covers: between the keystroke
    and the debounce firing, the dropdown is still HIDDEN. An Escape gated on
    the dropdown already being visible would do nothing here, and the fetch
    would open the dropdown ~200ms later anyway — over the Save button, with
    the operator believing they had dismissed it.
    """
    prefix = _unique_prefix('esc2')

    page.goto(f'{live_server.url}/products/add')
    category = page.locator('#category_path')
    expect(category).to_be_visible()

    category.fill(f'{prefix}/Never Saved')
    dropdown = _expect_dropdown_visible(page, contains_text='+ Create')

    # Close it first, so the dropdown is genuinely hidden when the second
    # Escape lands.
    page.evaluate(
        """() => document.getElementById('category_path').dispatchEvent(
            new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))"""
    )
    expect(dropdown).to_be_hidden()

    # Now type-then-Escape entirely within the hidden window. Dispatched
    # together so no inter-command latency can let the debounce fire in
    # between and hand Escape a visible dropdown.
    page.evaluate(
        """() => {
            const input = document.getElementById('category_path');
            input.value += 'y';
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(
                new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        }"""
    )

    # Well past the 200ms debounce.
    page.wait_for_timeout(700)
    expect(dropdown).to_be_hidden()


@pytest.mark.e2e
def test_create_entry_is_selectable_by_keyboard(page, live_server):
    """ArrowDown + Enter accepts the create entry, exactly like a stored
    suggestion (FR14).

    The create entry is deliberately rendered as one more `.dropdown-item`
    carrying `data-value` so keyboard handling needs no special case — this
    pins that claim rather than leaving it to the click path alone.
    """
    prefix = _unique_prefix('kbd')
    typed = f'{prefix.upper()}/Fasteners / Socket Head'
    canonical = f'{prefix}/fasteners/socket head'

    page.goto(f'{live_server.url}/products/add')
    category = page.locator('#category_path')
    expect(category).to_be_visible()

    category.fill(typed)
    dropdown = _expect_dropdown_visible(page, contains_text=f'+ Create "{canonical}"')

    # The path is unique to this run, so nothing can match it: the create
    # entry is the only row, and one ArrowDown lands on it. Waiting for the
    # single-item dropdown also proves the FILTERED response is on screen,
    # not the unfiltered focus render.
    expect(dropdown.locator('.dropdown-item')).to_have_count(1)

    category.press('ArrowDown')
    category.press('Enter')

    expect(category).to_have_value(canonical)
    expect(dropdown).to_be_hidden()

    # Enter selected the entry; it must not have submitted the form.
    expect(page.locator('#description')).to_be_visible()


@pytest.mark.e2e
def test_stored_category_is_offered_on_the_next_product(page, live_server):
    """Once a path is assigned, a later product form offers it from a prefix —
    the tree accretes purely from use (FR15)."""
    prefix = _unique_prefix('beta')
    canonical = f'{prefix}/thermal/heat sinks'

    _add_product(page, live_server, 'E2E category seed',
                 f'/{prefix.upper()}//Thermal/Heat Sinks/')
    expect(page.locator('body')).to_contain_text(canonical, timeout=10000)

    # A brand-new product form: type only the first segment.
    page.goto(f'{live_server.url}/products/add')
    category = page.locator('#category_path')
    expect(category).to_be_visible()
    category.fill(prefix)

    dropdown = _expect_dropdown_visible(page, contains_text=canonical)

    # And it selects like any other suggestion.
    dropdown.locator('.dropdown-item', has_text=canonical).click()
    expect(category).to_have_value(canonical)

    # Selecting must not re-open the dropdown: the entry we just accepted
    # would be re-offered on top of the Save button.
    page.wait_for_timeout(600)
    expect(dropdown).to_be_hidden()

    # Typing the full existing path offers it as an ordinary suggestion and
    # NOT as a create — it already exists. Safe to assert absence: this path
    # is unique to this run and was just stored.
    #
    # Pin the assertion to the FILTERED response, not just "some dropdown is
    # up": focusing the field fires an immediate unfiltered fetch, and that
    # vocabulary render also carries no create entry, so a bare
    # to_have_count(0) could pass without the typed query ever being answered.
    # This path is unique to the run, so exactly one row can match it —
    # waiting for a single-item dropdown means the filtered response is the
    # one on screen.
    category.fill('')
    category.type(canonical, delay=20)
    _expect_dropdown_visible(page, contains_text=canonical)
    expect(dropdown.locator('.dropdown-item')).to_have_count(1)
    expect(dropdown.locator('.dropdown-item').first).to_have_text(canonical)
