"""E2E: Set Category on several products (feature 063, issue #201).

**Waiting note.** Confirming the dialog awaits `POST /api/products/category`
and only then reloads the page, so the flashed success message is a complete
signal (render-implies-completion): it cannot appear before the write
committed. Every read after it is made against the reloaded page. The failure
path never reloads; its signal is the error alert in the dialog, which is set
after the awaited response.

The suggestions datalist is filled after an awaited `GET /api/categories`, so
its options are asserted with `expect(...).to_have_count`, which polls.

Products and purchases are seeded straight into the database.
"""

from datetime import datetime

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService
from tests.e2e.waits import wait_for_modal_shown

MODAL = "bulkCategoryModal"
FLASH_OK = ".alert-success.alert-dismissible"
CATEGORY_BTN = "#bulk-category-btn"


def set_category(page, category):
    """Open the dialog from the ticked rows, type, and confirm."""
    page.locator(CATEGORY_BTN).click()
    wait_for_modal_shown(page, MODAL)
    page.locator("#bulk-category-input").fill(category)
    page.locator("#bulk-category-submit").click()


# -- Products list ------------------------------------------------------------

def seed_products(live_server):
    service = CatalogService(live_server.storage)
    return service, [
        service.create_product(description="Washer", category_path="fasteners"),
        service.create_product(description="Nut", category_path="hardware"),
        service.create_product(description="Bolt"),
    ]


def product_row(page, product):
    return page.locator("#product-table tbody tr").filter(
        has=page.locator(f'input.product-checkbox[data-product-id="{product.id}"]'))


def product_box(page, product):
    return page.locator(f'input.product-checkbox[data-product-id="{product.id}"]')


def open_products(page, live_server, rows, query=""):
    page.goto(f"{live_server.url}/products{query}")
    expect(page.locator("#product-table tbody tr")).to_have_count(rows)


@pytest.mark.e2e
def test_products_list_sets_category_and_clears_selection(page, live_server):
    """US1: two of three products get the category; nothing is ticked after."""
    service, (washer, nut, bolt) = seed_products(live_server)

    open_products(page, live_server, 3)
    expect(page.locator(CATEGORY_BTN)).to_be_disabled()
    product_box(page, washer).check()
    product_box(page, bolt).check()
    expect(page.locator(CATEGORY_BTN)).to_be_enabled()

    page.locator(CATEGORY_BTN).click()
    wait_for_modal_shown(page, MODAL)
    expect(page.locator("#bulk-category-summary")).to_have_text(
        "2 products will be given this category.")
    # Suggestions come from the same source as Edit Product's field.
    expect(page.locator('#bulk-category-suggestions option[value="hardware"]')).to_have_count(1)
    page.locator("#bulk-category-input").fill("Tools / Hand ")
    page.locator("#bulk-category-submit").click()

    expect(page.locator(FLASH_OK, has_text='Set category "tools/hand" on 2 products.')
           ).to_be_visible()
    expect(product_row(page, washer).locator(".product-category")).to_have_text("tools/hand")
    expect(product_row(page, bolt).locator(".product-category")).to_have_text("tools/hand")
    expect(product_row(page, nut).locator(".product-category")).to_have_text("hardware")
    expect(page.locator("input.product-checkbox:checked")).to_have_count(0)
    expect(page.locator("#product-selected-count")).to_have_text("0")
    expect(page.locator(CATEGORY_BTN)).to_be_disabled()

    assert service.get_product(washer.id).category_path == "tools/hand"


@pytest.mark.e2e
def test_products_list_keeps_its_filters(page, live_server):
    """FR-010: the reload keeps the query string."""
    _, (washer, nut, _bolt) = seed_products(live_server)

    open_products(page, live_server, 1, query="?q=Washer")
    product_box(page, washer).check()
    set_category(page, "tools")

    expect(page.locator(FLASH_OK, has_text="on 1 product.")).to_be_visible()
    assert page.url.endswith("/products?q=Washer")
    expect(page.locator("#product-table tbody tr")).to_have_count(1)
    expect(product_row(page, washer).locator(".product-category")).to_have_text("tools")


@pytest.mark.e2e
def test_a_blank_category_is_refused_and_the_selection_kept(page, live_server):
    """FR-006 / FR-011: blank sets nothing; cancelling leaves the boxes ticked."""
    service, (washer, nut, _bolt) = seed_products(live_server)

    open_products(page, live_server, 3)
    product_box(page, washer).check()
    product_box(page, nut).check()
    set_category(page, "   ")

    expect(page.locator("#bulk-category-error")).to_contain_text("Enter a category")
    page.locator(f"#{MODAL} .btn-secondary").click()
    expect(page.locator(f"#{MODAL}")).to_be_hidden()
    expect(product_box(page, washer)).to_be_checked()
    expect(product_box(page, nut)).to_be_checked()
    expect(page.locator(CATEGORY_BTN)).to_be_enabled()
    assert service.get_product(washer.id).category_path == "fasteners"


@pytest.mark.e2e
def test_a_refused_update_keeps_the_dialog_and_selection(page, live_server):
    """FR-007 / FR-011: a product gone since the page loaded fails the whole set.

    The catalog has no product delete, so the stale row is made by pointing a
    checkbox at an id that names no product.
    """
    service, (washer, nut, _bolt) = seed_products(live_server)

    open_products(page, live_server, 3)
    product_box(page, washer).check()
    stale = product_box(page, nut)
    stale.check()
    stale.evaluate("el => { el.dataset.productId = '99999'; }")
    set_category(page, "tools")

    expect(page.locator("#bulk-category-error")).to_contain_text("99999")
    expect(page.locator(f"#{MODAL}")).to_be_visible()
    expect(product_box(page, washer)).to_be_checked()
    expect(page.locator("input.product-checkbox:checked")).to_have_count(2)
    assert service.get_product(washer.id).category_path == "fasteners"


# -- Order page and Outstanding Products -------------------------------------

def seed_orders(live_server):
    service = CatalogService(live_server.storage)

    def line(product, vendor, order, quantity=1):
        return service.record_purchase(
            product.id, vendor=vendor, vendor_item_id=product.description,
            order_date=datetime(2026, 9, 1), quantity=quantity,
            supplier_order_reference=order,
        )

    washer = service.create_product(description="Washer")
    nut = service.create_product(description="Nut", category_path="hardware")
    bolt = service.create_product(description="Bolt")
    lines = {
        "washer": line(washer, "McMaster-Carr", "7001CAT"),
        # The same product twice on one order.
        "washer_again": line(washer, "McMaster-Carr", "7001CAT", quantity=3),
        "nut": line(nut, "McMaster-Carr", "7001CAT"),
        "bolt": line(bolt, "Amazon", "111-0000000-0000063"),
    }
    service.receive_purchase(lines["washer_again"].id, received_date="2026-09-05")
    return service, {"washer": washer, "nut": nut, "bolt": bolt}, lines


def line_box(page, purchase):
    return page.locator(f'input.order-line-checkbox[value="{purchase.id}"]')


@pytest.mark.e2e
def test_order_page_sets_category_on_each_product_once(page, live_server):
    """US2: two ticked lines naming one product update it once."""
    service, products, lines = seed_orders(live_server)

    page.goto(f"{live_server.url}/products/orders/McMaster-Carr/7001CAT")
    expect(page.locator("input.order-line-checkbox")).to_have_count(3)
    line_box(page, lines["washer"]).check()
    line_box(page, lines["washer_again"]).check()
    set_category(page, "fasteners/washers")

    expect(page.locator(FLASH_OK, has_text='Set category "fasteners/washers" on 1 product.')
           ).to_be_visible()
    expect(page.locator("input.order-line-checkbox")).to_have_count(3)
    expect(page.locator("input.order-line-checkbox:checked")).to_have_count(0)
    expect(page.locator("#bulk-category-btn")).to_be_disabled()
    expect(page.locator("#order-receive-btn")).to_be_disabled()

    assert service.get_product(products["washer"].id).category_path == "fasteners/washers"
    assert service.get_product(products["nut"].id).category_path == "hardware"
    # Receipt state is untouched.
    assert service.get_purchase(lines["washer"].id).received_date is None
    assert service.get_purchase(lines["washer_again"].id).received_date == datetime(2026, 9, 5)


@pytest.mark.e2e
def test_outstanding_page_sets_category_across_orders(page, live_server):
    """US3: one line from each order; both stay outstanding."""
    service, products, lines = seed_orders(live_server)

    page.goto(f"{live_server.url}/products/outstanding")
    rows = page.locator("#order-lines tbody tr.outstanding-line")
    expect(rows).to_have_count(3)
    line_box(page, lines["nut"]).check()
    line_box(page, lines["bolt"]).check()
    set_category(page, "hardware/misc")

    expect(page.locator(FLASH_OK, has_text='Set category "hardware/misc" on 2 products.')
           ).to_be_visible()
    expect(rows).to_have_count(3)
    expect(page.locator("input.order-line-checkbox:checked")).to_have_count(0)

    assert service.get_product(products["nut"].id).category_path == "hardware/misc"
    assert service.get_product(products["bolt"].id).category_path == "hardware/misc"
    assert service.get_product(products["washer"].id).category_path is None
