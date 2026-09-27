"""E2E: vendor links in the product page's Details panel (feature 054, issue #180).

The page is server-rendered, so ``expect()`` on the Details panel is the whole
wait. Products are seeded through the service; the form is not under test.
"""

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_the_details_panel_links_to_each_vendor(page, live_server):
    """US1, US2: one link per vendor, opening in a new tab.

    McMaster's part number is seeded as VENDOR, the type captures wrote before
    049, so the legacy shape is what is proved to link.
    """
    [product] = live_server.add_test_products([{
        'description': 'Socket head cap screw, M3 x 10',
        'identifiers': [
            {'id_type': 'VENDOR', 'value': 'B0EXAMPLE1', 'vendor': 'Amazon'},
            {'id_type': 'VENDOR', 'value': '91251A540', 'vendor': 'McMaster-Carr'},
            {'id_type': 'DISTRIBUTOR', 'value': '296-1395-5-ND', 'vendor': 'DigiKey'},
        ],
    }])

    page.goto(f"{live_server.url}/products/{product.id}")

    links = page.locator("#product-vendor-links .vendor-link")
    expect(links).to_have_count(3)
    for vendor, href in [
        ('Amazon', 'https://www.amazon.com/dp/B0EXAMPLE1'),
        ('McMaster-Carr', 'https://www.mcmaster.com/91251A540/'),
        ('DigiKey', 'https://www.digikey.com/en/products/result?keywords=296-1395-5-ND'),
    ]:
        link = page.locator(f'.vendor-link[data-vendor="{vendor}"]')
        expect(link).to_have_attribute('href', href)
        expect(link).to_have_attribute('target', '_blank')
        expect(link).to_have_attribute('rel', 'noopener')


@pytest.mark.e2e
def test_a_product_with_nothing_to_link_has_no_row(page, live_server):
    """FR-007"""
    [product] = live_server.add_test_products([{
        'description': 'Op amp, dual',
        'identifiers': [{'id_type': 'MPN', 'value': 'LM358N'}],
    }])

    page.goto(f"{live_server.url}/products/{product.id}")

    # Establish the panel first, so the absence below is not a page that has
    # not rendered.
    expect(page.locator("#product-description")).to_have_text('Op amp, dual')
    expect(page.locator("#product-vendor-links")).to_have_count(0)
