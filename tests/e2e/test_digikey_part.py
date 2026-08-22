"""
E2E tests for cataloging one DigiKey part (feature 024, US3).

The part capture and the bag-scan enrichment both go through the same
``get_part`` call; what differs is where the operator started. DigiKey is the
same loopback fake the order tests use.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.test_digikey_order import digikey_api  # noqa: F401 -- fixture

RS, GS, EOT = "\x1e", "\x1d", "\x04"

PART_URL = (
    'https://www.digikey.com/en/products/detail/mean-well-usa-inc/IRM-05-5/7704652'
)


def look_up(page, live_server, value):
    page.goto(f"{live_server.url}/products/digikey/part")
    page.fill('#part_number', value)
    page.click('#look-up-part')
    return page


@pytest.mark.e2e
def test_a_part_number_fills_in_the_draft(page, live_server, digikey_api):
    """FR-028, SC-006. Nothing typed but the part number."""
    look_up(page, live_server, '1866-3027-ND')

    expect(page.locator('#part-detail')).to_be_visible()
    expect(page.locator('#part-manufacturer')).to_have_text('MEAN WELL USA Inc.')
    expect(page.locator('#part-mpn')).to_have_text('IRM-05-5')
    expect(page.locator('#description')).to_have_value('AC/DC CONVERTER 5V 5W')


@pytest.mark.e2e
def test_a_product_page_address_works_the_same(page, live_server, digikey_api):
    """FR-027. The trailing path segment is a product id, not a part number."""
    look_up(page, live_server, PART_URL)

    expect(page.locator('#part-detail')).to_be_visible()
    expect(page.locator('#part-mpn')).to_have_text('IRM-05-5')


@pytest.mark.e2e
def test_creating_the_product_keeps_digikeys_detail(page, live_server, digikey_api):
    """FR-028, FR-030. Specifications, both part numbers, the operator's words."""
    look_up(page, live_server, '1866-3027-ND')
    expect(page.locator('#description')).to_have_value('AC/DC CONVERTER 5V 5W')

    page.fill('#description', '5V 5W enclosed brick')
    page.click('#create-part')

    # Landing on the product page is the signal the write finished.
    expect(page.locator('h2')).to_contain_text('5V 5W enclosed brick')
    body = page.locator('body')
    expect(body).to_contain_text('MEAN WELL USA Inc.')
    expect(body).to_contain_text('IRM-05-5')
    # DigiKey's parametric detail came across as specifications.
    expect(body).to_contain_text('Enclosed')


@pytest.mark.e2e
def test_the_operators_description_wins_over_digikeys(page, live_server, digikey_api):
    """FR-029. DigiKey's words are a default, not a decision."""
    look_up(page, live_server, '1866-3027-ND')
    expect(page.locator('#description')).to_have_value('AC/DC CONVERTER 5V 5W')

    page.fill('#description', 'The little 5 volt one')
    page.click('#create-part')
    expect(page.locator('h2')).to_contain_text('The little 5 volt one')


@pytest.mark.e2e
def test_a_part_already_cataloged_names_it(page, live_server, digikey_api):
    """FR-031. Rather than inviting a second one."""
    from app.catalog_service import CatalogService

    CatalogService(live_server.storage).create_product(
        description='5V PSU I already own',
        identifiers=[{'id_type': 'MPN', 'value': 'IRM-05-5'}],
    )

    look_up(page, live_server, '1866-3027-ND')
    expect(page.locator('#part-already-cataloged')).to_be_visible()
    expect(page.locator('#part-already-cataloged')).to_contain_text('5V PSU I already own')


@pytest.mark.e2e
def test_an_unknown_part_number_offers_the_ordinary_form(page, live_server, digikey_api):
    """FR-032. A plain statement and a way forward, never an error page."""
    look_up(page, live_server, 'NOT-A-REAL-PART')

    expect(page.locator('#digikey-part-not-found')).to_be_visible()
    # And what they typed is still there to correct.
    expect(page.locator('#part_number')).to_have_value('NOT-A-REAL-PART')


@pytest.mark.e2e
def test_a_bag_for_an_uncataloged_part_gets_digikeys_detail(page, live_server, digikey_api):
    """FR-033. The draft used to carry only what the label itself said."""
    label = (
        "[)>" + RS + "06" + GS + "P1866-3027-ND" + GS + "1PIRM-05-5" + GS
        + "Q5" + GS + "1K999999999" + RS + EOT
    )
    page.goto(live_server.url)
    result = page.evaluate(
        """async (scan) => {
            const r = await fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scan: scan })
            });
            return await r.json();
        }""",
        label,
    )
    assert result['outcome'] == 'create'
    page.goto(f"{live_server.url}{result['url']}")

    # Not just the label's own four values: DigiKey's too.
    expect(page.locator('#description')).to_have_value('AC/DC CONVERTER 5V 5W')
    expect(page.locator('#manufacturer')).to_have_value('MEAN WELL USA Inc.')


@pytest.mark.e2e
def test_without_digikey_the_part_page_says_so(page, live_server):
    """FR-036. And the by-hand route is still offered."""
    previous = live_server.app.config.get('DIGIKEY_CLIENT')
    live_server.app.config['DIGIKEY_CLIENT'] = None
    try:
        page.goto(f"{live_server.url}/products/digikey/part")
        expect(page.locator('#digikey-not-configured')).to_be_visible()
    finally:
        live_server.app.config['DIGIKEY_CLIENT'] = previous
