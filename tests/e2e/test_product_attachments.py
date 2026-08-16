"""
E2E tests for a product's attachments: pasting one in, and looking through them.

**On the clipboard.** A real system clipboard cannot be driven reliably from a
headless browser, so the paste is a synthetic ``ClipboardEvent`` carrying a real
``File`` in a real ``DataTransfer``. That exercises everything the handler
actually does -- reading ``clipboardData.items``, picking the first image entry,
``getAsFile()``, and the upload through ``csrfFetch`` -- and stops exactly at the
boundary where the browser hands the event over. What it cannot prove is that
Ctrl+V produces such an event, which is the one part no automated test here
could, and is in quickstart.md's by-hand list instead.
"""

import base64
import io
import re

import pytest
from PIL import Image
from playwright.sync_api import expect

CARDS = "#attachment-list .attachment-row"
SELECTORS = ".attachment-select"
SELECT_ALL = "#select-all-attachments"
DELETE_SELECTED = "#delete-selected-attachments"


def png_base64(size=(64, 48), colour=(10, 120, 200)):
    """A real PNG -- the server decodes what it is given"""
    buffer = io.BytesIO()
    Image.new('RGB', size, colour).save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


@pytest.fixture
def product(live_server):
    """Seeded directly: the form is not what is under test here."""
    return live_server.add_test_products([{'description': 'LM358 op-amp'}])[0]


def wait_for_paste_listener(page):
    """Wait until the page is listening for a paste.

    ``initProductAttachments`` binds the handler on ``DOMContentLoaded``, and an
    upload ends in ``window.location.reload()``. So after any upload there is a
    window in which the tiles have rendered -- a count assertion is already
    satisfied -- but the listener is not bound yet, and a ``ClipboardEvent``
    dispatched into it lands on nothing and is lost without a trace.

    ``readyState === 'complete'`` is the observable side of that: ``load``
    cannot fire before ``DOMContentLoaded`` has, so by then the handler is bound.
    """
    page.wait_for_function("document.readyState === 'complete'")


def paste_image(page, encoded, name='pasted.png'):
    wait_for_paste_listener(page)
    page.evaluate(
        """([encoded, name]) => {
            const binary = atob(encoded);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) {
                bytes[i] = binary.charCodeAt(i);
            }
            const transfer = new DataTransfer();
            transfer.items.add(new File([bytes], name, { type: 'image/png' }));
            document.dispatchEvent(
                new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true })
            );
        }""",
        [encoded, name],
    )


def paste_text(page, text="just some ordinary text"):
    wait_for_paste_listener(page)
    page.evaluate(
        """(text) => {
            const transfer = new DataTransfer();
            transfer.setData('text/plain', text);
            document.dispatchEvent(
                new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true })
            );
        }""",
        text,
    )


def open_with_attachments(page, live_server, product, count):
    """Seed ``count`` attachments and open the product with the grid settled.

    Seeded rather than pasted: the selection tests are not about pasting, and
    pasting each one costs a full page reload -- see
    ``TestServer.add_product_attachments`` for why that is also a race.
    """
    live_server.add_product_attachments(product.id, count)
    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator(CARDS)).to_have_count(count)


def record_dialogs(page, accept=True):
    """Record every ``confirm`` the page raises, and answer them all.

    The count is the point. The defect this feature exists to prevent is *one
    action, N prompts*, and a test that waits for a single dialog cannot see the
    extra ones -- so every dialog is answered and appended, and the test asserts
    on how many arrived.

    ``page.on`` rather than ``page.once`` deliberately: with ``once``, a second
    prompt would go unanswered and block the page until the test timed out
    somewhere unrelated, instead of failing here with a legible list.
    """
    messages = []

    def handler(dialog):
        messages.append(dialog.message)
        dialog.accept() if accept else dialog.dismiss()

    page.on("dialog", handler)
    return messages


@pytest.mark.e2e
def test_pasting_an_image_attaches_it_to_the_product(page, live_server, product):
    """FR-023: the fastest path from "I have a picture of it" to "it is filed" """
    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#no-attachments")).to_be_visible()

    paste_image(page, png_base64())

    expect(page.locator(CARDS)).to_have_count(1)
    expect(page.locator("#no-attachments")).to_have_count(0)


@pytest.mark.e2e
def test_pasting_ordinary_text_uploads_nothing_and_says_nothing(
    page, live_server, product
):
    """A paste is not a request to upload, so a rejection message would be noise.

    The absence is bounded by a positive: an image is pasted afterwards and
    waited for. If the text paste had uploaded anything the count would settle at
    two rather than one, so this cannot pass by simply never rendering.
    """
    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#no-attachments")).to_be_visible()

    paste_text(page)
    expect(page.locator("#attachment-alert")).to_have_count(0)

    paste_image(page, png_base64())
    expect(page.locator(CARDS)).to_have_count(1)


@pytest.mark.e2e
def test_the_attachments_are_a_thumbnail_grid(page, live_server, product):
    """FR-013: a captured gallery is a dozen images, and a filename list is
    not something anyone can look through."""
    page.goto(f"{live_server.url}/products/{product.id}")
    paste_image(page, png_base64(colour=(200, 40, 40)), name='first.png')
    expect(page.locator(CARDS)).to_have_count(1)
    paste_image(page, png_base64(colour=(40, 200, 40)), name='second.png')
    expect(page.locator(CARDS)).to_have_count(2)

    thumbnails = page.locator(f"{CARDS} img")
    expect(thumbnails).to_have_count(2)
    expect(thumbnails.first).to_have_attribute("src", re.compile(
        r"/api/photos/\d+\?size=thumbnail$"
    ))
    # The original is still one click away.
    expect(page.locator(f"{CARDS} a").first).to_have_attribute(
        "href", re.compile(r"/api/photos/\d+$")
    )


@pytest.mark.e2e
def test_a_pasted_attachment_can_be_removed_again(page, live_server, product):
    page.goto(f"{live_server.url}/products/{product.id}")
    paste_image(page, png_base64())
    expect(page.locator(CARDS)).to_have_count(1)

    page.click(".delete-attachment-btn")

    expect(page.locator(CARDS)).to_have_count(0)
    expect(page.locator("#no-attachments")).to_be_visible()


# --------------------------------------------------------------------------
# Selecting several and deleting them in one press (issue #96)
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_every_tile_carries_a_selection_control_and_none_is_ticked(
    page, live_server, product
):
    """FR-001: a capture that over-collects is pruned by ticking, not by a dozen
    round trips. US1 scenario 1."""
    open_with_attachments(page, live_server, product, 3)

    boxes = page.locator(SELECTORS)
    expect(boxes).to_have_count(3)
    for index in range(3):
        expect(boxes.nth(index)).not_to_be_checked()


@pytest.mark.e2e
def test_the_delete_action_is_unavailable_until_something_is_selected(
    page, live_server, product
):
    """FR-003, FR-004: nothing selected is not a delete anyone meant to press.
    US1 scenarios 2 and 3."""
    open_with_attachments(page, live_server, product, 3)

    delete_selected = page.locator(DELETE_SELECTED)
    expect(delete_selected).to_be_disabled()

    page.locator(SELECTORS).nth(0).check()
    page.locator(SELECTORS).nth(1).check()

    expect(delete_selected).to_be_enabled()
    expect(delete_selected).to_contain_text("2")


@pytest.mark.e2e
def test_deleting_a_selection_asks_once_and_removes_exactly_those(
    page, live_server, product
):
    """FR-005, FR-006: one confirmation naming the count, then the whole
    selection. US1 scenarios 4 and 5.

    The assertion that matters is ``len(messages) == 1``. A prompt per
    attachment is the failure mode this feature exists to remove, and it is
    invisible to a test that only checks that *a* dialog appeared.
    """
    open_with_attachments(page, live_server, product, 4)

    kept = page.locator(CARDS).nth(3).locator("img").get_attribute("src")

    messages = record_dialogs(page)
    for index in range(3):
        page.locator(SELECTORS).nth(index).check()
    page.locator(DELETE_SELECTED).click()

    expect(page.locator(CARDS)).to_have_count(1)
    assert messages == ["Delete 3 attachments?"], messages

    # The one that was not ticked is the one still there.
    expect(page.locator(f"{CARDS} img")).to_have_attribute("src", kept)


@pytest.mark.e2e
def test_dismissing_the_confirmation_deletes_nothing(page, live_server, product):
    """FR-007: the confirmation is the safeguard, so declining it has to mean
    something. US1 scenario 6."""
    open_with_attachments(page, live_server, product, 3)

    record_dialogs(page, accept=False)
    for index in range(3):
        page.locator(SELECTORS).nth(index).check()
    page.locator(DELETE_SELECTED).click()

    # The selection survives a refusal -- the user still has it to act on.
    expect(page.locator(DELETE_SELECTED)).to_be_enabled()
    expect(page.locator(DELETE_SELECTED)).to_contain_text("3")
    for index in range(3):
        expect(page.locator(SELECTORS).nth(index)).to_be_checked()

    # And nothing reached the server: a reload is the only honest way to ask.
    page.reload()
    expect(page.locator(CARDS)).to_have_count(3)


@pytest.mark.e2e
def test_one_attachment_is_named_in_the_singular(page, live_server, product):
    """"1 attachment(s)" is the kind of thing that reads as a bug in the
    application. Edge case in spec.md."""
    open_with_attachments(page, live_server, product, 1)

    messages = record_dialogs(page)
    page.locator(SELECTORS).first.check()
    page.locator(DELETE_SELECTED).click()

    expect(page.locator(CARDS)).to_have_count(0)
    assert messages == ["Delete 1 attachment?"], messages


@pytest.mark.e2e
def test_ticking_a_tile_does_not_open_the_image(page, live_server, product):
    """The thumbnail is a link to the original, and the checkbox sits in the same
    card. Ticking must not navigate. Edge case in spec.md."""
    open_with_attachments(page, live_server, product, 2)
    product_url = page.url

    page.locator(SELECTORS).first.check()

    expect(page.locator(SELECTORS).first).to_be_checked()
    expect(page).to_have_url(product_url)
    expect(page.locator(CARDS)).to_have_count(2)


@pytest.mark.e2e
def test_select_all_ticks_everything_and_toggles_back_off(
    page, live_server, product
):
    """FR-002: clearing twenty images should not mean twenty ticks.
    US2 scenarios 1 and 2."""
    open_with_attachments(page, live_server, product, 3)

    page.locator(SELECT_ALL).check()

    boxes = page.locator(SELECTORS)
    for index in range(3):
        expect(boxes.nth(index)).to_be_checked()
    expect(page.locator(DELETE_SELECTED)).to_contain_text("3")

    page.locator(SELECT_ALL).uncheck()

    for index in range(3):
        expect(boxes.nth(index)).not_to_be_checked()
    expect(page.locator(DELETE_SELECTED)).to_be_disabled()


@pytest.mark.e2e
def test_select_all_keeps_what_was_already_ticked(page, live_server, product):
    """US2 scenario 4: select-all adds to a selection, it does not replace it."""
    open_with_attachments(page, live_server, product, 3)

    page.locator(SELECTORS).nth(1).check()
    expect(page.locator(DELETE_SELECTED)).to_contain_text("1")

    page.locator(SELECT_ALL).check()

    boxes = page.locator(SELECTORS)
    for index in range(3):
        expect(boxes.nth(index)).to_be_checked()
    expect(page.locator(DELETE_SELECTED)).to_contain_text("3")


@pytest.mark.e2e
def test_select_all_then_delete_empties_the_grid(page, live_server, product):
    """FR-014, US2 scenario 3: the whole capture goes in three actions, and the
    card says so itself rather than leaving an empty space."""
    open_with_attachments(page, live_server, product, 3)

    messages = record_dialogs(page)
    page.locator(SELECT_ALL).check()
    page.locator(DELETE_SELECTED).click()

    expect(page.locator(CARDS)).to_have_count(0)
    expect(page.locator("#no-attachments")).to_be_visible()
    assert messages == ["Delete 3 attachments?"], messages

    # The toolbar goes with them: a select-all over nothing is not a control.
    expect(page.locator(DELETE_SELECTED)).to_have_count(0)


@pytest.mark.e2e
def test_the_single_attachment_delete_is_unchanged(page, live_server, product):
    """FR-012: the per-tile trash button keeps deleting its own tile, and keeps
    asking nothing. US1 scenario 10."""
    open_with_attachments(page, live_server, product, 3)

    messages = record_dialogs(page)
    page.locator(f"{CARDS} .delete-attachment-btn").first.click()

    expect(page.locator(CARDS)).to_have_count(2)
    assert messages == [], messages
