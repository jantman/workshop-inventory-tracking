"""Handheld screen routes (feature 068), under ``/h/``.

Thin by design (Constitution II): each route reads through the same service
call its desktop counterpart makes and renders a template extending
``handheld/base.html``. contracts/handheld-routes.md lists every route.

Author: Jason Antman, 2026.
"""

from flask import abort, render_template, request
from werkzeug.wrappers import Response

from app.handheld import bp
from app.main.routes import _get_inventory_service, handle_shorten_post
from app.photo_service import PhotoService
from app.product.routes import (
    _get_catalog_service,
    _get_storage_backend,
    _product_or_404,
    _received_total,
)
from app.utils.handoff import resolve_handoff, resolve_product_handoff

# The wording the desktop move wrappers (inventory/move.html, product/move.html)
# pass to the move macro, keyed by ``?kind=``.
_MOVE_KINDS: dict[str, dict[str, str]] = {
    'items': {'noun': 'item', 'nouns': 'items', 'id_label': 'JA ID',
              'selection_heading': 'Items From Your Selection',
              'not_found_text': 'not found in the inventory'},
    'products': {'noun': 'product', 'nouns': 'products', 'id_label': 'Product Code',
                 'selection_heading': 'Product To Move',
                 'not_found_text': 'no product carries this code'},
}


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
    """A product's handheld screen: summary, Stock card, label, attachments (US2).

    The same reads as the desktop product page (``product_detail``), so the
    included Stock card and label modal see the same context.
    """
    service = _get_catalog_service()
    catalog_product = _product_or_404(service, product_id)
    purchases = service.get_purchase_history(product_id)
    with PhotoService(_get_storage_backend()) as photos:
        attachments = [a.to_dict() for a in photos.get_product_attachments(product_id)]
    return render_template(
        'handheld/product.html',
        title=catalog_product.description,
        product=catalog_product,
        purchases=purchases,
        received_total=_received_total(purchases),
        attachments=attachments,
    )


@bp.route('/move')
def move():
    """Handheld Move for items or products (US3), driven by the desktop MoveManager.

    ``?kind=items`` takes ``?ja_id=`` hand-offs and ``?kind=products`` takes
    ``?code=``, resolved exactly as the desktop move pages resolve them.
    """
    kind = request.args.get('kind')
    if kind not in _MOVE_KINDS:
        abort(404)
    if kind == 'items':
        handoff = resolve_handoff(request.args.get('ja_id'), _get_inventory_service())
    else:
        handoff = resolve_product_handoff(request.args.get('code'), _get_catalog_service())
    wording = _MOVE_KINDS[kind]
    return render_template(
        'handheld/move.html',
        title=f"Move {wording['nouns'].title()}",
        kind=kind,
        preselected_items=handoff.preselected_items,
        rejected_items=handoff.rejected_items,
        **wording,
    )


@bp.route('/shorten', methods=['GET', 'POST'])
def shorten() -> str | Response:
    """Handheld Shorten (US5), driven by the desktop InventoryShortenManager.

    GET takes a ``?ja_id=`` hand-off exactly as the desktop shorten page does.
    POST runs the desktop's own handler, so validation, audit logging, flashes
    and the history-preserving shortening are the same code (FR-013).
    """
    if request.method == 'POST':
        return handle_shorten_post(request.form, 'handheld.shorten')
    handoff = resolve_handoff(request.args.get('ja_id'), _get_inventory_service())
    return render_template(
        'handheld/shorten.html',
        title='Shorten',
        preselected_ja_id=handoff.first_accepted,
        rejected_items=handoff.rejected_items,
    )
