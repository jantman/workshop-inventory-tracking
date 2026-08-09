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


def png_base64(size=(64, 48), colour=(10, 120, 200)):
    """A real PNG -- the server decodes what it is given"""
    buffer = io.BytesIO()
    Image.new('RGB', size, colour).save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


@pytest.fixture
def product(live_server):
    """Seeded directly: the form is not what is under test here."""
    return live_server.add_test_products([{'description': 'LM358 op-amp'}])[0]


def paste_image(page, encoded, name='pasted.png'):
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
