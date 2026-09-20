"""E2E: the packed extension, loaded for real (feature 048).

Every other capture test injects ``extension/capture-agent.js`` from disk into
an ordinary page. These load the extension itself -- its manifest, its service
worker, its options screen and its submit page -- because that plumbing exists
nowhere else and is exactly what issue #133 needed built.

**Why a separate browser.** Chromium runs extensions only under a persistent
context, and the ``chromium`` channel is what lets one run headless. Putting the
~158 injected-reader tests behind that launch mode would risk the suite's
largest file to cover plumbing a handful of tests can cover, so the split is
deliberate (048 research.md §9).

**The one thing these cannot drive, stated plainly.** ``activeTab`` grants host
access at the moment the operator clicks the toolbar control, and there is no
toolbar to click in a headless browser -- an action click dispatched from the
worker confers no grant, so every ``executeScript`` below would be refused. So
the extension is copied to a temporary directory and given
``host_permissions`` for ``http://127.0.0.1/*``, the harness's own origin and
nothing else, and the copy is what is loaded.

That divergence is one manifest key wide and it is contained on both sides. The
**shipped** manifest's permission set is asserted exactly, and asserted to carry
no host permissions at all, in ``tests/unit/test_extension_manifest.py``; so a
permission creeping into the real package fails there rather than hiding here.
And the real ``activeTab`` grant is checked by hand against real vendor pages,
which is quickstart.md §3 -- the same pass that has to be run anyway, because no
local fixture carries McMaster's content policy and nothing but a real McMaster
page proves the bug is fixed.
"""

import json
import re
import shutil
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import expect

FIXTURES = Path(__file__).parent / "fixtures"
EXTENSION = Path(__file__).parents[2] / "extension"

# The four page kinds, at the paths the reader dispatches on. Served from the
# application's own origin for the reason every capture module gives: Chrome
# will not let one origin load a subresource from a more-private address space,
# so a convincing ``https://www.amazon.com/...`` would never work locally. That
# is why the dispatch keys on the path and never the hostname.
ASIN = "B0CKXJLP4B"
LISTING_ROUTE = re.compile(r"/dp/[A-Z0-9]{10}")
MCMASTER_PART = "91290A115"
MCMASTER_PRODUCT_ROUTE = re.compile(r"/91290A115/$")
MCMASTER_ORDER_ID = "6a5ffba81f17e12ac4fb7d70"
MCMASTER_ORDER_ROUTE = re.compile(r"/order-history/order/[0-9a-f]{24}")
AMAZON_ORDER_ID = "111-2223334-5556667"
AMAZON_ORDER_ROUTE = re.compile(r"/your-orders/order-details")

# What the fixtures' own markup says.
MCMASTER_LINE_COUNT = 11
AMAZON_LINE_COUNT = 4


# --------------------------------------------------------------------------
# Loading the extension
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def packed_extension():
    """``extension/``, copied, with the harness's origin added to the manifest.

    See the module docstring for why the copy exists and what keeps the
    divergence honest. Everything else in the directory is the shipped package,
    byte for byte -- including the reader, the worker, the options screen and
    the submit page, which are what these tests are about.
    """
    with tempfile.TemporaryDirectory() as workspace:
        packed = Path(workspace) / "extension"
        shutil.copytree(EXTENSION, packed)

        manifest_path = packed / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["host_permissions"] = ["http://127.0.0.1/*"]
        manifest_path.write_text(json.dumps(manifest, indent=2))

        yield packed


@pytest.fixture
def extension(playwright, packed_extension, live_server, image_host):
    """The loaded extension, its worker, and the vendor fixtures it can read.

    Yields an object carrying the browser context, the service worker, and the
    extension's own identifier -- recovered from the worker's address, which is
    what makes ``chrome-extension://<id>/options.html`` addressable from a test.

    The worker starts asynchronously, and "wait a moment for the worker" is
    exactly the wrong reflex. Playwright surfaces the worker as an event, so the
    condition is observable and is waited on that way (Constitution IV).
    """
    with tempfile.TemporaryDirectory() as profile:
        context = playwright.chromium.launch_persistent_context(
            profile,
            channel="chromium",
            headless=True,
            viewport={"width": 1280, "height": 720},
            args=[
                f"--disable-extensions-except={packed_extension}",
                f"--load-extension={packed_extension}",
            ],
        )
        context.set_default_timeout(60000)
        context.set_default_navigation_timeout(60000)

        worker = (
            context.service_workers[0]
            if context.service_workers
            else context.wait_for_event("serviceworker")
        )

        _serve_fixtures(context, image_host)

        requests = []
        context.on(
            "request",
            lambda request: (
                requests.append(request)
                if request.url.endswith("/api/capture") and request.method == "POST"
                else None
            ),
        )

        yield _Extension(
            context=context,
            worker=worker,
            id=worker.url.split("/")[2],
            server=live_server,
            captures=requests,
        )

        context.close()


class _Extension:
    """What a test needs to drive the extension, in one object."""

    def __init__(self, context, worker, id, server, captures):
        self.context = context
        self.worker = worker
        self.id = id
        self.server = server
        #: Every POST to /api/capture the context has made, in order. Recorded
        #: rather than asserted on arrival, because the field that matters most
        #: (FR-003) is one that must be *absent*.
        self.captures = captures

    # -- configuration ----------------------------------------------------

    def seed_address(self, address=None):
        """Put an address into `chrome.storage.sync` without the options screen.

        US1 is independently testable this way and not independently usable --
        a person installing only US1 would have no way to set the address. US3
        is what makes it usable, and `configure_address` below is that path.
        """
        page = self.context.new_page()
        page.goto(f"chrome-extension://{self.id}/options.html")
        page.evaluate(
            "(value) => chrome.storage.sync.set({applicationAddress: value})",
            address if address is not None else self.server.url,
        )
        page.close()

    def options(self):
        """The options screen, open."""
        page = self.context.new_page()
        page.goto(f"chrome-extension://{self.id}/options.html")
        # The stored value is written into the field by an awaited read, so the
        # save control being present does not mean the field is filled yet.
        expect(page.locator("#save")).to_be_visible()
        return page

    def configure_address(self, entered):
        """Enter an address on the options screen and save it. FR-009."""
        page = self.options()
        page.fill("#address", entered)
        page.click("#save")
        # `#saved` is written after the store resolves, so it is the completion
        # signal; the field's own value is set before it and would lie.
        expect(page.locator("#saved")).to_be_visible()
        return page

    # -- invoking ---------------------------------------------------------

    def open_vendor_page(self, path):
        """Open a vendor fixture and return its tab."""
        page = self.context.new_page()
        page.goto(f"{self.server.url}{path}")
        return page

    def invoke(self, tab, through="action"):
        """Start a capture on `tab`, through either entry point.

        The toolbar control cannot be clicked in a headless browser, so the
        registered listener is dispatched instead. That still exercises the
        registration -- a worker that never called `addListener` dispatches to
        nothing and no capture happens.

        The tab is brought to the front first and the worker then asks for the
        active one, which is how both entry points really arrive: the operator
        clicks on the tab they are looking at. Asking by address is not open to
        the worker -- reading a tab's URL needs the `tabs` permission, which the
        extension deliberately does not request.
        """
        tab.bring_to_front()
        event = (
            "chrome.action.onClicked"
            if through == "action"
            else "chrome.contextMenus.onClicked"
        )
        argument = (
            "active" if through == "action"
            else "{menuItemId: 'workshop-capture'}, active"
        )
        self.worker.evaluate(
            """async () => {
                const [active] = await chrome.tabs.query(
                    {active: true, currentWindow: true}
                );
                %s.dispatch(%s);
            }""" % (event, argument)
        )

    def capture_from(self, path, through="action"):
        """Capture a vendor page and return (the vendor tab, the landing tab).

        The landing tab is the one the worker opened on the submit page, after
        that page's form has navigated it to the application. Waiting on
        `expect_page` rather than on a count is what makes this observable:
        the tab does not exist until the reader's promise has settled.
        """
        vendor = self.open_vendor_page(path)
        with self.context.expect_page() as opened:
            self.invoke(vendor, through=through)
        return vendor, opened.value


def _serve_fixtures(context, image_host):
    """Fulfil each vendor path with its fixture, for every tab in the context.

    On the context rather than a page, because the tabs these tests read are
    opened by the extension and by helpers rather than handed over by a fixture.
    """
    def serve(route_pattern, fixture):
        body = (FIXTURES / fixture).read_text().replace("__IMAGE_HOST__", image_host)
        context.route(
            route_pattern,
            lambda route: route.fulfill(
                status=200, content_type="text/html", body=body
            ),
        )

    serve(LISTING_ROUTE, "amazon_listing.html")
    serve(MCMASTER_PRODUCT_ROUTE, "mcmaster_product.html")
    serve(MCMASTER_ORDER_ROUTE, "mcmaster_order.html")
    serve(AMAZON_ORDER_ROUTE, "amazon_order.html")


def submitted(request):
    """The fields a capture POST carried, parsed out of its body."""
    return dict(
        pair.split("=", 1) for pair in request.post_data.split("&") if "=" in pair
    )


# --------------------------------------------------------------------------
# US1 -- a McMaster order, which is what could not be captured at all
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_a_mcmaster_order_captures_through_the_extension(extension):
    """The defect, closed. Issue #133's own case, end to end.

    Every step in the path is exercised: the stored address, the injection, the
    reader's promise, the hand-off through session storage, the submit page's
    form, and the order review the application renders from it.
    """
    extension.seed_address()

    _, landed = extension.capture_from(f"/order-history/order/{MCMASTER_ORDER_ID}")

    # A full navigation, so the review's own table is the completion signal and
    # a count read before it lands would read zero (pattern C).
    expect(landed.locator("#order-lines")).to_be_visible()
    expect(landed.locator("#order-lines tbody tr.order-line")).to_have_count(
        MCMASTER_LINE_COUNT
    )


@pytest.mark.e2e
def test_the_vendor_tab_is_left_where_it_was(extension):
    """What moving the submission off the vendor page buys (research.md §3).

    Nothing else in the suite would notice this regressing: every assertion
    about a capture is made on the landing tab. If a submission ever went back
    to being made from the vendor's document, this is the test that says so.
    """
    extension.seed_address()
    vendor_path = f"/order-history/order/{MCMASTER_ORDER_ID}"

    vendor, landed = extension.capture_from(vendor_path)

    expect(landed.locator("#order-lines")).to_be_visible()
    assert not vendor.is_closed()
    assert vendor.url == f"{extension.server.url}{vendor_path}"


# --------------------------------------------------------------------------
# US2 -- everything that already worked, still working
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_an_amazon_order_captures_with_its_per_line_listings(extension):
    """The path whose same-origin `/dp/<ASIN>` fetches research.md §2 is about.

    An isolated-world content script keeps the page's origin for network
    purposes, so these reads behave as the page's own -- which is what the
    per-line summaries below can only exist if it is true.
    """
    extension.seed_address()

    _, landed = extension.capture_from(
        f"/your-orders/order-details?orderID={AMAZON_ORDER_ID}"
    )

    expect(landed.locator("#order-lines")).to_be_visible()
    expect(landed.locator("#order-lines tbody tr.order-line")).to_have_count(
        AMAZON_LINE_COUNT
    )
    expect(landed.locator(".line-listing-summary")).to_have_count(AMAZON_LINE_COUNT)


@pytest.mark.e2e
def test_progress_is_shown_on_the_vendor_page_while_it_reads(extension):
    """FR-007. The read takes seconds, so it has to say it is working.

    Half of `showProgress` used to write into a blank tab opened before the read
    began, to spend the click's activation before it expired. There is no such
    tab any more (research.md §3), so the banner on the vendor's page is the
    whole of it -- which makes it worth asserting that the remaining half still
    runs.

    **Recorded rather than caught.** The banner is appended when the read starts
    and removed when it finishes, so looking for it afterwards finds nothing and
    looking for it during is a race. A `MutationObserver` installed before the
    capture keeps the history; it is read once the landing has rendered, by which
    time the read is certainly over.

    The history is taken from the mutation *records*, not from the element. Each
    `banner.textContent = …` replaces the text node, so every record's added node
    is one message frozen at the moment it was written. Reading the live element
    inside the callback would report whatever it says when the callback happens
    to run, which on a fast read is only ever the last thing it said.
    """
    extension.seed_address()
    vendor = extension.open_vendor_page(
        f"/your-orders/order-details?orderID={AMAZON_ORDER_ID}"
    )
    vendor.evaluate(
        """() => {
            window.__progress = [];
            new MutationObserver((records) => {
                for (const record of records) {
                    if (record.target.id !== 'workshop-capture-progress') continue;
                    for (const node of record.addedNodes) {
                        window.__progress.push(node.data || '');
                    }
                }
            }).observe(document.body, {childList: true, subtree: true});
        }"""
    )

    with extension.context.expect_page() as opened:
        extension.invoke(vendor)
    expect(opened.value.locator("#order-lines")).to_be_visible()

    said = vendor.evaluate("() => window.__progress")
    assert any("reading the order" in text for text in said), said
    assert any("reading listing" in text for text in said), said
    # And it cleaned up after itself.
    expect(vendor.locator("#workshop-capture-progress")).to_have_count(0)


@pytest.mark.e2e
def test_a_mcmaster_product_captures_through_the_extension(extension):
    extension.seed_address()

    _, landed = extension.capture_from(f"/{MCMASTER_PART}/")

    expect(landed.locator("#capture-form")).to_be_visible()
    expect(landed.locator("#vendor_item_id")).to_have_value(MCMASTER_PART)
    # Declared by the reader rather than derived from the host, which on this
    # harness would be the loopback address.
    expect(landed.locator("#vendor")).to_have_value("McMaster-Carr")


@pytest.mark.e2e
def test_an_amazon_listing_captures_through_the_extension(extension):
    extension.seed_address()

    _, landed = extension.capture_from(f"/dp/{ASIN}/ref=sr_1_3")

    expect(landed.locator("#capture-form")).to_be_visible()
    expect(landed.locator("#vendor_item_id")).to_have_value(ASIN)


@pytest.mark.e2e
def test_a_plain_amazon_listing_sends_no_vendor_field_at_all(extension):
    """FR-003, on the one field whose absence is load-bearing.

    The bookmarklet sent no `vendor` for a plain listing, so the application
    derived it from the address. An *empty* `vendor` is not the same thing --
    it would override the derivation with nothing -- which is why the submit
    page builds its form from the payload's own keys and why this asserts on
    the request body rather than on what the landing page displays.
    """
    extension.seed_address()

    _, landed = extension.capture_from(f"/dp/{ASIN}/ref=sr_1_3")
    expect(landed.locator("#capture-form")).to_be_visible()

    fields = submitted(extension.captures[-1])
    assert "vendor" not in fields
    assert set(fields) == {"url", "listing_title", "listing"}


@pytest.mark.e2e
def test_a_page_it_cannot_read_says_so_and_sends_nothing(extension):
    """FR-008. A search results page, a family table, anything else.

    The banner is appended only after the refusal is decided, so its presence
    is what makes the assertions below safe to read: no tab can be opened and
    no request can be made after it (pattern C).
    """
    extension.seed_address()
    vendor = extension.open_vendor_page("/products")

    extension.invoke(vendor)

    message = vendor.locator("#workshop-capture-message")
    expect(message).to_be_visible()
    expect(message).to_contain_text("not a page it can read")
    assert extension.captures == []


# --------------------------------------------------------------------------
# US3 -- pointing it at your own installation
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_an_address_entered_on_the_options_screen_is_what_is_used(extension):
    """FR-009, FR-010. The screen, not the seeded value the other tests use."""
    options = extension.configure_address(extension.server.url)
    options.close()

    _, landed = extension.capture_from(f"/{MCMASTER_PART}/")

    expect(landed.locator("#capture-form")).to_be_visible()
    assert extension.captures[-1].url == f"{extension.server.url}/api/capture"


@pytest.mark.e2e
def test_a_trailing_slash_and_stray_spaces_still_reach_the_endpoint(extension):
    """FR-013. What a pasted address-bar value actually looks like.

    Normalization happens once, on save, so what is stored is a bare origin and
    the submit page composes `<origin>/api/capture` from it. Without it the POST
    would go to `<origin>//api/capture`.
    """
    options = extension.configure_address(f"  {extension.server.url}/  ")
    # The field is rewritten with what was stored, which is the observable proof
    # that the value was normalized before it was written.
    expect(options.locator("#address")).to_have_value(extension.server.url)
    options.close()

    _, landed = extension.capture_from(f"/{MCMASTER_PART}/")

    expect(landed.locator("#capture-form")).to_be_visible()
    assert extension.captures[-1].url == f"{extension.server.url}/api/capture"


@pytest.mark.e2e
def test_an_insecure_address_is_saved_and_warned_about(extension):
    """FR-012. The operator is told, not blocked -- it is their installation.

    Said here, where the address is typed, rather than on the application's
    capture page where the old warning sat: this is where the mistake is made.
    """
    options = extension.configure_address("http://workshop.example.com")

    expect(options.locator("#warning")).to_be_visible()
    expect(options.locator("#warning")).to_contain_text("not https")
    expect(options.locator("#error")).to_be_hidden()
    # Saved anyway.
    assert options.evaluate(
        "async () => (await chrome.storage.sync.get('applicationAddress'))"
        ".applicationAddress"
    ) == "http://workshop.example.com"


@pytest.mark.e2e
def test_the_options_screen_shows_the_extension_s_own_version(extension):
    """FR-014, so it can be compared with the application's footer."""
    manifest = json.loads((EXTENSION / "manifest.json").read_text())

    options = extension.options()

    expect(options.locator("#version")).to_contain_text(manifest["version"])


@pytest.mark.e2e
def test_with_no_address_configured_it_says_so_and_opens_the_options(extension):
    """FR-011, and the most important test in this file.

    The bug this whole feature fixes presents as *nothing happening*. An
    extension that captured nothing and said nothing when it had no address
    would have reproduced that symptom exactly, in a new place. So: a message
    on the page, the options screen opened, and nothing sent.
    """
    vendor = extension.open_vendor_page(f"/{MCMASTER_PART}/")

    with extension.context.expect_page() as opened:
        extension.invoke(vendor)
    options = opened.value

    expect(vendor.locator("#workshop-capture-message")).to_contain_text(
        "no application address is configured"
    )
    assert options.url == f"chrome-extension://{extension.id}/options.html"
    assert extension.captures == []


# --------------------------------------------------------------------------
# US5 -- the right-click entry
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_the_context_menu_captures_exactly_as_the_toolbar_control_does(extension):
    """FR-016. One registration, and no capture logic of its own behind it.

    The other half of FR-016 -- that no entry is offered on a site it does not
    read -- is not asserted here. A browser context menu cannot be opened from a
    headless test at all, and `chrome.contextMenus` offers no way to read back
    what was registered, so the only thing a test could assert is the text of
    the registration it is testing. That is quickstart.md §3e's job.
    """
    extension.seed_address()

    _, landed = extension.capture_from(
        f"/order-history/order/{MCMASTER_ORDER_ID}", through="menu"
    )

    expect(landed.locator("#order-lines")).to_be_visible()
    expect(landed.locator("#order-lines tbody tr.order-line")).to_have_count(
        MCMASTER_LINE_COUNT
    )

