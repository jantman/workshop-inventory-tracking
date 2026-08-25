"""E2E: capturing one McMaster-Carr part from its product page (US2).

The same harness as ``test_mcmaster_order.py`` and, before it,
``test_product_page_capture.py``: the fixture is served from **this
application's own origin**, because Chrome will not let one origin load a
subresource from a more-private address space and the agent would never load
from a convincing ``http://www.mcmaster.com/...``.

This is the issue's first half, and the visibly broken case before this
feature: clicking the bookmarklet on a McMaster page yielded the address and
nothing else, because every selector the agent knew was Amazon's.

The reader under test here keys on **stems** of CSS-module class names --
``[class*="_price_"]`` rather than ``_price_1y02s_5`` -- because the trailing
hash is a build artifact that changes without warning. The fixture carries the
real hashes so that substring matching is exercised rather than assumed.
"""

import json

import pytest
from playwright.sync_api import expect

from tests.e2e.test_product_page_capture import (
    FIXTURES,
    image_host,  # noqa: F401  -- a fixture, used by injection
    run_bookmarklet,
)

PART_NUMBER = "91290A115"
PRODUCT_ROUTE = "**/91290A115/"

# What the fixture's own markup says.
TITLE = ("Black-Oxide Alloy Steel Socket Head Screw, "
         "M3 x 0.5 mm Thread Size, 10 mm Long")
PACK_PRICE = "13.23"
PACK_SIZE = "100"


def serve_product(page, image_host, fixture="mcmaster_product.html"):
    body = (FIXTURES / fixture).read_text().replace("__IMAGE_HOST__", image_host)
    page.route(
        PRODUCT_ROUTE,
        lambda route: route.fulfill(
            status=200, content_type="text/html", body=body
        ),
    )


def capture_product(page, live_server, image_host):
    """Serve the fixture product page and click the real bookmarklet on it."""
    serve_product(page, image_host)
    return run_bookmarklet(
        page, live_server, f"{live_server.url}/{PART_NUMBER}/"
    )


def payload_of(landed):
    return json.loads(landed.locator("input[name='listing']").input_value())


@pytest.mark.e2e
def test_the_confirmation_form_arrives_pre_filled(page, live_server, image_host):
    """US2 scenario 1: nothing typed, and all of it is on the page."""
    landed = capture_product(page, live_server, image_host)

    expect(landed.locator("#vendor_item_id")).to_have_value(PART_NUMBER)
    expect(landed.locator("#vendor")).to_have_value("McMaster-Carr")
    # McMaster's own wording goes in `listing_title`. `description` is left
    # blank on purpose and stays that way: it is the operator's *label*
    # description, kept distinct from the vendor's (FR-023), and prefilling it
    # from the listing is not what the Amazon path does either.
    expect(landed.locator("#listing_title")).to_have_value(TITLE)
    expect(landed.locator("#description")).to_have_value("")


@pytest.mark.e2e
def test_the_vendor_is_declared_by_the_agent_not_derived_from_the_host(
    page, live_server, image_host
):
    """research.md §4. Under this harness the fixture is served from
    127.0.0.1, so a derived vendor would be the loopback host -- and for
    McMaster the vendor is not cosmetic: it is half of every query that finds
    a captured order or a receivable line."""
    landed = capture_product(page, live_server, image_host)

    expect(landed.locator("#vendor")).to_have_value("McMaster-Carr")


@pytest.mark.e2e
def test_the_pack_price_and_pack_size_fill_the_017_fields(
    page, live_server, image_host
):
    """US2 scenario 3. McMaster states both in one string -- "$13.23 per pack
    of 100" -- and the unit price is worked out from them exactly as it is for
    a multi-pack captured from any other vendor."""
    landed = capture_product(page, live_server, image_host)

    expect(landed.locator("#pack_price")).to_have_value(PACK_PRICE)
    expect(landed.locator("#pack_size")).to_have_value(PACK_SIZE)


@pytest.mark.e2e
def test_the_specification_table_comes_across(page, live_server, image_host):
    """The table nests: a group row ("Thread") carries an empty value and is
    followed by indented rows for its members. The group heading is not a fact
    about the part and must not arrive as an empty specification."""
    landed = capture_product(page, live_server, image_host)

    specifications = payload_of(landed)["specifications"]
    by_name = {row["name"]: row["value"] for row in specifications}

    assert by_name.get("Size") == "M3"
    assert by_name.get("Pitch") == "0.5 mm"
    assert by_name.get("Material") == "Alloy Steel"
    assert "Thread" not in by_name, (
        'the group heading arrived as a specification with no value'
    )
    assert all(row["value"] for row in specifications)


@pytest.mark.e2e
def test_the_product_images_are_captured_and_the_catalog_chrome_is_not(
    page, live_server, image_host
):
    """A real page carries about forty catalog-navigation icons under
    /init/gfx/. A reader that takes every <img> captures the browse menu."""
    landed = capture_product(page, live_server, image_host)

    images = payload_of(landed).get("images", [])
    assert images, 'no product image was captured'
    assert not [src for src in images if "/init/gfx/" in src], (
        'the catalog navigation icons were captured as product images'
    )


@pytest.mark.e2e
def test_no_manufacturer_is_invented(page, live_server, image_host):
    """McMaster sells to its own specification and names no manufacturer on
    the great majority of its goods. Blank is a fact about the vendor, not a
    missed selector -- and it is why FR-012 writes an MPN only where a page
    states one."""
    landed = capture_product(page, live_server, image_host)

    assert not payload_of(landed).get("brand")
    expect(landed.locator("#manufacturer")).to_have_value("")


@pytest.mark.e2e
def test_the_price_crosses_the_boundary_as_a_string(
    page, live_server, image_host
):
    """Constitution III."""
    landed = capture_product(page, live_server, image_host)

    raw = landed.locator("input[name='listing']").input_value()
    assert f'"pack_price": "{PACK_PRICE}"' in raw or \
           f'"pack_price":"{PACK_PRICE}"' in raw
    assert isinstance(payload_of(landed)["pack_price"], str)


@pytest.mark.e2e
def test_confirming_creates_the_product_with_the_scoped_identifier(
    page, live_server, image_host
):
    """US2 scenarios 2 and 5: the operator's own label description wins, and
    the part number is recorded scoped to McMaster-Carr so a scan finds it."""
    landed = capture_product(page, live_server, image_host)
    landed.fill("#description", "Socket head screw, M3 x 10, black oxide")
    landed.fill("#quantity", "100")
    landed.click("#capture-btn")

    # A capture creates an outstanding purchase and lands on its receipt, which
    # is a full navigation -- so the receipt's own button is the completion
    # signal, and a field read before it lands would read empty (pattern C).
    expect(landed.locator("#confirm-receive-btn")).to_be_visible()
    # The label description is an editable field here, not page text.
    expect(landed.locator("#description")).to_have_value(
        "Socket head screw, M3 x 10, black oxide"
    )
    expect(landed.locator("#receive-vendor")).to_have_text("McMaster-Carr")
    expect(landed.locator("#receive-vendor-item")).to_have_text(PART_NUMBER)
    # McMaster's own wording is kept alongside the operator's (FR-023).
    expect(landed.locator("#receive-listing")).to_have_text(TITLE)


@pytest.mark.e2e
def test_a_pasted_mcmaster_address_needs_no_agent(page, live_server):
    """US2 scenario 6, FR-025. The path that cannot break when a vendor
    changes their markup: the address alone yields the vendor and the part."""
    page.goto(f"{live_server.url}/products/capture")
    expect(page.locator("#capture-form")).to_be_visible()

    page.fill("#url", f"https://www.mcmaster.com/{PART_NUMBER}/")
    page.fill("#description", "Socket head screw, pasted")
    page.click("#capture-btn")

    # The vendor and the part number are read off the address **server-side**,
    # on submit -- nothing derives them in the browser -- so the receipt this
    # lands on is the first place they can be seen.
    expect(page.locator("#confirm-receive-btn")).to_be_visible()
    expect(page.locator("#description")).to_have_value("Socket head screw, pasted")
    expect(page.locator("#receive-vendor")).to_have_text("McMaster-Carr")
    expect(page.locator("#receive-vendor-item")).to_have_text(PART_NUMBER)


@pytest.mark.e2e
def test_the_existing_duplicate_handling_applies_unchanged(
    page, live_server, image_host
):
    """US2 scenario 4, FR-026. The operator is shown the match and must choose
    before anything is written -- this feature adds no second answer to a
    question the catalog already answers."""
    landed = capture_product(page, live_server, image_host)
    landed.fill("#description", "Socket head screw, first capture")
    landed.fill("#quantity", "100")
    landed.click("#capture-btn")
    expect(landed.locator("#confirm-receive-btn")).to_be_visible()
    landed.close()

    again = capture_product(page, live_server, image_host)
    again.fill("#description", "Socket head screw, second capture")
    again.fill("#quantity", "50")
    again.click("#capture-btn")

    # The catalog stops and asks rather than guessing: it comes back to the
    # form carrying the question, naming the product it matched. Established
    # with an expect() before anything is read off the page.
    expect(again.locator("#capture-form")).to_be_visible()
    expect(again.locator("body")).to_contain_text("first capture")
