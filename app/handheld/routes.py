"""Handheld screen routes (feature 068), under ``/h/``.

Thin by design (Constitution II): each route reads through the same service
call its desktop counterpart makes and renders a template extending
``handheld/base.html``. contracts/handheld-routes.md lists every route.

Author: Jason Antman, 2026.
"""

from dataclasses import dataclass
from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for
from werkzeug.wrappers import Response

from app.handheld import bp
from app.exceptions import ItemNotFoundError, ValidationError
from app.main.routes import _get_inventory_service, handle_shorten_post
from app.photo_service import PhotoService
from app.product.routes import (
    _flash_bulk_receipt,
    _get_catalog_service,
    _get_storage_backend,
    _product_or_404,
    _receive_choice,
    _receive_purchase_from_form,
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
    outstanding = [p for p in purchases if p.is_outstanding]
    # Each distinct order with an outstanding line, first seen first (FR-023b).
    outstanding_orders: list[tuple[str, str]] = []
    for purchase in outstanding:
        reference = (purchase.supplier_order_reference or '').strip()
        key = (purchase.vendor or '', reference)
        if reference and key not in outstanding_orders:
            outstanding_orders.append(key)
    return render_template(
        'handheld/product.html',
        title=catalog_product.description,
        product=catalog_product,
        purchases=purchases,
        received_total=_received_total(purchases),
        attachments=attachments,
        outstanding=outstanding,
        outstanding_orders=outstanding_orders,
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


@bp.route('/receive/<int:purchase_id>', methods=['GET', 'POST'])
def receive(purchase_id: int) -> str | Response:
    """Receive one purchase line (US6, research.md D7).

    POST makes the same service call the desktop receipt page makes with
    nothing amended, through the same field mapping, so the effects are the
    same, a counted receipt included (FR-021).
    """
    service = _get_catalog_service()
    purchase = service.get_purchase(purchase_id)
    if purchase is None:
        raise ItemNotFoundError(f"Purchase {purchase_id} not found", item_id=str(purchase_id))
    catalog_product = _product_or_404(service, purchase.product_id)

    form_data = None
    scanned_quantity = request.args.get('quantity', '')
    if request.method == 'POST':
        try:
            _receive_purchase_from_form(service, purchase_id, request.form)
        except ValidationError as e:
            flash(e.message, 'error')
            form_data = request.form
            scanned_quantity = request.form.get('quantity', '')
        else:
            flash('Received.', 'success')
            return redirect(url_for('handheld.product', product_id=catalog_product.id))

    return render_template(
        'handheld/receive.html',
        title='Receive',
        purchase=purchase,
        product=catalog_product,
        scanned_quantity=scanned_quantity,
        form_data=form_data,
    )


@bp.route('/receive/choose')
def receive_choose() -> str:
    """Which outstanding line did this bag come from? (US6, FR-022)

    The desktop receive-choice page's candidates; the operator picks one and
    nothing is preselected.
    """
    scan = (request.args.get('scan') or '').strip()
    candidates, catalog_product = _receive_choice(scan)
    return render_template(
        'handheld/receive_choose.html',
        title='Which Line?',
        scan=scan,
        candidates=candidates,
        product=catalog_product,
    )


@dataclass
class OrderSummary:
    """One captured order with outstanding lines, for the handheld order list."""

    vendor: str
    order_number: str
    order_date: datetime | None
    outstanding: int


def group_outstanding_orders(purchases: list) -> list[OrderSummary]:
    """Group outstanding purchases by ``(vendor, order reference)`` (data-model.md).

    Presentation grouping only. Purchases with no order reference are skipped:
    there is no order screen for them, and their product's screen reaches them.
    The input order is kept, so the service's oldest-order-first sort carries
    through.
    """
    orders: dict[tuple[str, str], OrderSummary] = {}
    for line in purchases:
        reference = (line.supplier_order_reference or '').strip()
        if not reference:
            continue
        key = (line.vendor or '', reference)
        summary = orders.setdefault(key, OrderSummary(
            vendor=key[0], order_number=reference, order_date=line.order_date, outstanding=0,
        ))
        summary.outstanding += 1
    return list(orders.values())


@bp.route('/orders')
def orders() -> str:
    """Captured orders that still have outstanding lines (US7, FR-023a)."""
    service = _get_catalog_service()
    return render_template(
        'handheld/orders.html',
        title='Orders',
        orders=group_outstanding_orders(service.find_outstanding_purchases()),
    )


@bp.route('/orders/<vendor>/<order_number>')
def order(vendor: str, order_number: str) -> str:
    """One captured order's lines as selectable cards (US7, research.md D13).

    ``highlight`` marks the lines a scan named but selects none (FR-022). An
    order nothing was captured against is a 200 saying so, as on the desktop.
    """
    service = _get_catalog_service()
    return render_template(
        'handheld/order.html',
        title=f'{vendor} {order_number}',
        vendor=vendor,
        order_number=order_number,
        lines=service.find_order_lines_for(vendor, order_number),
        highlight=request.args.get('highlight', ''),
    )


@bp.route('/orders/<vendor>/<order_number>/receive', methods=['POST'])
def order_receive(vendor: str, order_number: str) -> Response:
    """Receive the selected lines, exactly as the desktop order page does (FR-023)."""
    service = _get_catalog_service()
    _flash_bulk_receipt(lambda: service.receive_order_lines(
        vendor,
        order_number,
        request.form.getlist('purchase_id'),
        received_date=request.form.get('received_date'),
    ))
    return redirect(url_for('handheld.order', vendor=vendor, order_number=order_number))
