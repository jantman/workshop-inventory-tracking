"""Handheld screen routes (feature 068), under ``/h/``.

Thin by design (Constitution II): each route reads through the same service
call its desktop counterpart makes and renders a template extending
``handheld/base.html``. contracts/handheld-routes.md lists every route.

Author: Jason Antman, 2026.
"""

from flask import render_template

from app.handheld import bp
from app.main.routes import _get_inventory_service
from app.product.routes import _get_catalog_service, _product_or_404


@bp.route('/')
def landing():
    """The handheld home: a scan entry and the four task buttons (US1)."""
    return render_template('handheld/landing.html', title='Handheld')


@bp.route('/item/<ja_id>')
def item(ja_id: str):
    """An inventory item's handheld screen (US1; US4 completes it).

    A missing or inactive JA ID is a 200 in its own state, not a 404, because
    the screen says what is wrong and links to the desktop page.
    """
    inventory_item = _get_inventory_service().get_canonical_item(ja_id)
    if inventory_item is None:
        state = 'missing'
    elif not inventory_item.active:
        state = 'inactive'
    else:
        state = 'active'
    return render_template(
        'handheld/item.html', title=ja_id, ja_id=ja_id, item=inventory_item, state=state,
    )


@bp.route('/product/<int:product_id>')
def product(product_id: int):
    """A product's handheld screen (US1; US2 completes it). Unknown id is a 404."""
    catalog_product = _product_or_404(_get_catalog_service(), product_id)
    return render_template(
        'handheld/product.html', title=catalog_product.description, product=catalog_product,
    )
