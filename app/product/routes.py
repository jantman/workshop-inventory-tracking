"""
Product catalogue routes.

Thin by design (Constitution II): no ORM queries and no raw SQL live here.
Everything delegates to CatalogService. Server-rendered pages return HTML,
``/api/*`` returns JSON, and errors go through the project's existing exceptions
rather than any new error machinery.
"""

import re
from urllib.parse import urlparse

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for

from app import csrf
from app.catalog_service import CatalogService
from app.exceptions import (
    CaptureDecisionRequired, DuplicateItemError, ItemNotFoundError, ValidationError
)
from app.models import ListingCapture
from app.photo_service import PhotoService
from app.product import bp
from app.services.listing_images import store_listing_images


def _get_storage_backend():
    """Get the storage backend for the current app context"""
    if 'STORAGE_BACKEND' in current_app.config:
        return current_app.config['STORAGE_BACKEND']

    from app.mariadb_storage import MariaDBStorage
    return MariaDBStorage()


def _get_catalog_service() -> CatalogService:
    """Get the catalogue service bound to this app's storage backend"""
    return CatalogService(_get_storage_backend())


def _product_or_404(service: CatalogService, product_id: int):
    """Load a product or raise the project's not-found exception"""
    product = service.get_product(product_id)
    if product is None:
        raise ItemNotFoundError(f"Product {product_id} not found", item_id=str(product_id))
    return product


def _form_specifications(form) -> list:
    """Pair the repeating specification inputs into entries, in DOM order.

    Every row posts under the same two names, so position is the only thing
    linking a name to its value -- and ``zip`` rather than an index walk because
    a walk would raise if the two lists ever came back different lengths.
    Nothing is validated here; the service is what decides what a valid entry is.
    """
    return [
        {'name': name, 'value': value}
        for name, value in zip(form.getlist('spec_name'), form.getlist('spec_value'))
    ]


def _form_product_fields(form) -> dict:
    """Pull the product fields out of a submitted form"""
    return {
        'description': form.get('description', ''),
        'manufacturer': form.get('manufacturer'),
        'manufacturer_part_number': form.get('manufacturer_part_number'),
        'specifications': _form_specifications(form),
        'category_path': form.get('category_path'),
        'location': form.get('location'),
        'sub_location': form.get('sub_location'),
        'notes': form.get('notes'),
        'reorder_threshold': form.get('reorder_threshold'),
    }


def _redisplay_values(form) -> dict:
    """What the operator typed, shaped for the form partial after a refusal.

    ``form.to_dict()`` keeps only the last value of a repeated field, which would
    silently drop every specification row but one. The rows are therefore paired
    back explicitly -- re-rendering the stored product instead would discard the
    edit the operator is being asked to correct.
    """
    values = form.to_dict()
    values['specifications'] = _form_specifications(form)
    return values


# The distributor-label fields the create form offers for editing. The values
# come off the scanned label uncoerced (FR-017) and the operator may amend any of
# them before saving.
ECIA_PREFILL_FIELDS = (
    ('distributor_part_number', 'Distributor part number'),
    ('quantity', 'Quantity'),
    ('order_reference', 'Order reference'),
    ('supplier_order_reference', 'Supplier order reference'),
    ('date_code', 'Date code'),
)


def _ecia_note(form) -> str:
    """Render the submitted distributor-label fields as a note block.

    These have no column of their own: quantity and order references describe a
    *purchase*, and a scanned label does not tell us which vendor to file one
    against. Rather than offer them for editing and then drop them -- which is
    what used to happen -- they are kept verbatim on the product, so the operator
    can raise the purchase from them later.

    Args:
        form: The submitted form.

    Returns:
        A note block, or an empty string when the label carried none of them.
    """
    lines = [
        f"{label}: {form.get('ecia_' + key).strip()}"
        for key, label in ECIA_PREFILL_FIELDS
        if (form.get('ecia_' + key) or '').strip()
    ]
    if not lines:
        return ''
    return "From the distributor label:\n" + "\n".join(lines)


def _split_tags(raw) -> list:
    """Split a comma-separated tag field into names"""
    if not raw:
        return []
    return [part.strip() for part in raw.split(',') if part.strip()]


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@bp.route('/products')
def product_search():
    """The catalogue list, with text search and category/tag/stock filters."""
    service = _get_catalog_service()
    filters = {
        'q': request.args.get('q', ''),
        'category': request.args.get('category', ''),
        'tag': request.args.get('tag', ''),
        'stock': request.args.get('stock', ''),
        'spec_name': request.args.get('spec_name', ''),
        'spec_value': request.args.get('spec_value', ''),
    }

    try:
        products = service.search_products(
            query=filters['q'],
            category=filters['category'],
            tag=filters['tag'],
            stock=filters['stock'],
            spec_name=filters['spec_name'],
            spec_value=filters['spec_value'],
        )
    except ValidationError as e:
        flash(e.message, 'error')
        products = []

    return render_template(
        'product/search.html',
        title='Products',
        products=products,
        filters=filters,
    )


@bp.route('/products/new', methods=['GET', 'POST'])
def product_new():
    """Create a product.

    Accepts ``?identifier=`` and ``?id_type=`` so an unrecognized scan can land
    here with the scanned code already attached rather than dead-ending (FR-018).
    """
    service = _get_catalog_service()

    if request.method == 'POST':
        fields = _form_product_fields(request.form)
        identifiers = []
        identifier_value = request.form.get('identifier_value', '').strip()
        if identifier_value:
            identifiers.append({
                'id_type': request.form.get('identifier_type', 'MPN'),
                'value': identifier_value,
                'vendor': request.form.get('identifier_vendor'),
                'override': request.form.get('identifier_override') == 'on',
            })

        label_note = _ecia_note(request.form)
        if label_note:
            fields['notes'] = '\n\n'.join(
                part for part in (fields.get('notes'), label_note) if part
            )

        try:
            product = service.create_product(
                identifiers=identifiers,
                tags=_split_tags(request.form.get('tags')),
                **fields
            )
        except ValidationError as e:
            flash(str(e.message), 'error')
            return render_template(
                'product/add.html',
                title='Add Product',
                form_data=_redisplay_values(request.form),
                prefill={},
            )

        flash(f'Created "{product.description}".', 'success')
        return redirect(url_for('product.product_detail', product_id=product.id))

    # Everything a scan yielded arrives as query parameters so the create form
    # opens already carrying it -- an unknown scan offers creation, never an
    # error (FR-018), and every extracted value stays editable (FR-017).
    ecia_fields = {
        key: request.args[key]
        for key, _label in ECIA_PREFILL_FIELDS
        if request.args.get(key)
    }

    prefill = {
        'identifier_value': request.args.get('identifier', ''),
        'identifier_type': request.args.get('id_type', 'MPN'),
        'description': request.args.get('description', ''),
        'raw_scan': request.args.get('raw_scan', ''),
        'ecia_fields': ecia_fields,
    }
    return render_template(
        'product/add.html',
        title='Add Product',
        form_data={},
        prefill=prefill,
    )


@bp.route('/products/<int:product_id>')
def product_detail(product_id):
    """Show everything known about one product."""
    service = _get_catalog_service()
    product = _product_or_404(service, product_id)

    from app.photo_service import PhotoService

    purchases = service.get_purchase_history(product_id)

    with PhotoService(_get_storage_backend()) as photos:
        attachments = [a.to_dict() for a in photos.get_product_attachments(product_id)]
        purchase_attachments = {
            purchase.id: [a.to_dict() for a in photos.get_purchase_attachments(purchase.id)]
            for purchase in purchases
        }

    return render_template(
        'product/detail.html',
        title=product.description,
        product=product,
        purchases=purchases,
        latest_price=service.get_latest_price(product_id),
        from_scan=bool(request.args.get('from_scan')),
        outstanding=[p for p in purchases if p.is_outstanding],
        attachments=attachments,
        purchase_attachments=purchase_attachments,
    )


@bp.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
def product_edit(product_id):
    """Edit a product's own fields."""
    service = _get_catalog_service()
    product = _product_or_404(service, product_id)

    if request.method == 'POST':
        try:
            product = service.update_product(product_id, **_form_product_fields(request.form))
            product = service.set_tags(product_id, _split_tags(request.form.get('tags')))
        except ValidationError as e:
            flash(str(e.message), 'error')
            # form_data, not just the product: re-rendering the unchanged DB row
            # would silently discard everything the operator had typed.
            return render_template(
                'product/edit.html',
                title='Edit Product',
                product=product,
                form_data=_redisplay_values(request.form),
            )

        flash('Saved.', 'success')
        return redirect(url_for('product.product_detail', product_id=product_id))

    return render_template('product/edit.html', title='Edit Product', product=product)


@bp.route('/products/<int:product_id>/purchases/new', methods=['GET', 'POST'])
def purchase_new(product_id):
    """Record a purchase against an existing product (FR-004, FR-019)."""
    service = _get_catalog_service()
    product = _product_or_404(service, product_id)

    if request.method == 'POST':
        try:
            service.record_purchase(
                product_id,
                vendor=request.form.get('vendor', ''),
                vendor_item_id=request.form.get('vendor_item_id'),
                listing_title=request.form.get('listing_title'),
                order_date=request.form.get('order_date'),
                received_date=request.form.get('received_date'),
                quantity=request.form.get('quantity'),
                unit_price=request.form.get('unit_price'),
                order_reference=request.form.get('order_reference'),
                notes=request.form.get('notes'),
            )
        except ValidationError as e:
            flash(e.message, 'error')
            return render_template(
                'product/purchase_add.html',
                title='Record a Purchase',
                product=product,
                form_data=request.form,
            )

        flash('Purchase recorded.', 'success')
        return redirect(url_for('product.product_detail', product_id=product_id))

    return render_template(
        'product/purchase_add.html',
        title='Record a Purchase',
        product=product,
        form_data={},
    )


@bp.route('/products/capture', methods=['GET', 'POST'])
def product_capture():
    """Paste-a-URL capture -- the path that cannot break when a vendor changes.

    The bookmarklet is the fast path, but it depends on the vendor's page letting
    a form POST out. This form depends on nothing but the operator's clipboard.

    This is also where the write happens for both paths: the bookmarklet lands on
    this form pre-filled and the operator submits it from here. The route detects
    nothing of its own -- it forwards the form and renders whatever the service
    hands back, including the questions it declines to answer.

    It is also where the extracted listing stops being a string. ``listing`` is
    parsed here rather than at ``/api/capture`` because this is the first point
    at which anything is written, and a payload it cannot read is not an error:
    ``from_json`` returns None and every line below behaves exactly as it did
    before this feature existed (FR-007).
    """
    service = _get_catalog_service()

    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        vendor = request.form.get('vendor', '') or _vendor_from_url(url)
        vendor_item_id = request.form.get('vendor_item_id', '') or _asin_from_url(url)
        listing = ListingCapture.from_json(request.form.get('listing'))

        # The listing fills the blanks and never overwrites: the operator was
        # looking at the thing, and a value they typed wins over one a selector
        # found (US1 scenario 3).
        #
        # **Absent, not merely empty.** The confirmation form always submits both
        # of these -- pre-filled from the same payload -- so a field that arrives
        # empty is one the operator *cleared*, and clearing is a change like any
        # other. Falling back on empty would quietly put the extracted value back
        # and there would be no way to say "the listing is wrong about this".
        # Falling back on absent still covers a POST that carries the payload and
        # nothing else.
        manufacturer = request.form.get('manufacturer')
        unit_price = request.form.get('unit_price')
        if listing is not None:
            if manufacturer is None:
                manufacturer = listing.brand
            if unit_price is None:
                unit_price = listing.price

        try:
            purchase = service.capture_order(
                vendor=vendor,
                vendor_item_id=vendor_item_id,
                listing_title=request.form.get('listing_title'),
                url=url,
                unit_price=unit_price,
                quantity=request.form.get('quantity'),
                order_date=request.form.get('order_date'),
                description=request.form.get('description'),
                manufacturer=manufacturer,
                manufacturer_part_number=request.form.get('manufacturer_part_number'),
                acknowledged_duplicate_of=request.form.get('acknowledged_duplicate_of'),
                attach_to=request.form.get('attach_to'),
                listing=listing,
            )
        except CaptureDecisionRequired as e:
            # Not an error page: a step in the flow. Nothing was written, and the
            # form comes back with the question attached.
            return render_template(
                'product/capture.html',
                title='Capture an Order',
                form_data=request.form,
                listing=listing,
                assessment=e.assessment,
                bookmarklet=_capture_bookmarklet(),
            )
        except ValidationError as e:
            flash(e.message, 'error')
            return render_template(
                'product/capture.html',
                title='Capture an Order',
                form_data=request.form,
                listing=listing,
                bookmarklet=_capture_bookmarklet(),
            )

        flash('Captured. Confirm the details when it arrives.', 'success')

        # After capture_order returns, and before the redirect. The ordering is
        # the contract: the operator lands on a finished capture rather than on
        # one still filling in behind them. It is also what makes this POST take
        # eight to fifteen seconds for a full gallery, which is expected rather
        # than a defect -- see research.md, "Why image retrieval is synchronous".
        if listing is not None and listing.images:
            images = store_listing_images(
                purchase.product_id,
                listing.images,
                _get_storage_backend(),
                vendor_item_id=vendor_item_id,
            )
            flash(_image_tally(images), 'success' if images.stored else 'warning')

        return redirect(url_for('product.purchase_receive', purchase_id=purchase.id))

    return render_template(
        'product/capture.html',
        title='Capture an Order',
        form_data=request.args,
        listing=ListingCapture.from_json(request.args.get('listing')),
        bookmarklet=_capture_bookmarklet(),
    )


def _image_tally(images) -> str:
    """Say what landed and what did not (FR-020, FR-021, FR-022).

    Everything that did not land is named. A capture that quietly stored nine of
    fourteen images is the failure the operator cannot see and cannot reproduce
    later, because by then the listing is gone.
    """
    parts = [f"Stored {images.stored} image{'' if images.stored == 1 else 's'}"]
    if images.failed:
        parts.append(f"{images.failed} could not be retrieved")
    if images.skipped:
        parts.append(f"{images.skipped} skipped as an unsupported type or too large")
    if images.duplicates:
        parts.append(f"{images.duplicates} already on this product")
    if images.cap_reached:
        parts.append(
            f"stopped at the limit of {PhotoService.MAX_ATTACHMENTS_PER_PRODUCT} "
            f"attachments"
        )
    return '; '.join(parts) + '.'


def _capture_bookmarklet() -> str:
    """Build the capture bookmarklet, bound to this server's own address.

    **It is a loader and nothing else.** It appends
    ``app/static/js/capture-agent.js`` to the vendor's page with the endpoint on
    a data attribute, and the agent does the reading and the submitting. What
    used to be four lines of extraction inline in a ``javascript:`` URL is now an
    ordinary reviewable file in this repository.

    ``?v=' + Date.now()`` is what makes FR-024 true: the browser never serves a
    cached agent, so editing that file is the whole deployment story and the
    operator never re-drags this bookmarklet. It costs one uncached ~10 KB fetch
    per capture, which is not worth a version-stamping mechanism.

    Both addresses are absolute and are fixed when *this* page renders, which is
    why the TLS caveat below is about where you drag it from.

    The agent still submits a **form into a new tab** rather than issuing a
    fetch: the vendor page is HTTPS and this app is plain HTTP on the LAN, so a
    fetch is refused as mixed content before CSRF, CORS or the page's CSP are
    ever consulted, whereas a form submission is a navigation and is exempt from
    that rule.

    The new tab lands on this app's own confirmation page, which is also where
    the operator amends anything the listing did not yield.
    """
    endpoint = url_for('product.api_capture', _external=True)
    agent = url_for('static', filename='js/capture-agent.js', _external=True)

    script = (
        "javascript:(function(){"
        "var s=document.createElement('script');"
        f"s.src='{agent}?v='+Date.now();"
        f"s.dataset.endpoint='{endpoint}';"
        "document.body.appendChild(s);"
        "})();"
    )
    return script


@bp.route('/api/capture', methods=['POST'])
@csrf.exempt
def api_capture():
    """Land a capture from a vendor's listing (FR-007, FR-008, FR-009).

    Two representations, and they no longer do the same thing.

    **A form body -- the bookmarklet -- writes nothing.** It renders the capture
    form, pre-filled with what the URL and the page title yielded, and the
    operator confirms it from this application's own origin. That is what makes
    the description authorable while the listing is still on screen, and it is
    why an abandoned capture leaves no trace: there was never a record to clean
    up, only a page that got closed.

    **A JSON body still writes**, honouring the same decision parameters
    ``product_capture`` forwards, and answering 409 with the assessment when the
    capture would otherwise have guessed.

    **This is the only CSRF exemption the product catalogue adds**, and the only
    one it needs. (It is not the only one in the application: app/main/routes.py
    carries fourteen pre-existing ones, which this feature neither added nor
    audited. The planning documents assert this would be the sole exemption in
    the app; that was mistaken about the existing code, and the claim is recorded
    accurately here instead.)

    The bookmarklet posts from the vendor's own origin, so a CSRF token cannot
    travel with it. The exemption is proportionate under the constitution's
    stated threat model: the app is LAN-only, has one trusted user, and treats
    hostile input as out of scope -- and it is now narrower than it was, because
    the representation that arrives from a vendor's origin does not write at all.

    Accepts a form POST as well as JSON, because the bookmarklet submits a form
    into a new tab rather than issuing a fetch: a fetch from an HTTPS vendor page
    to an HTTP host is refused as mixed content before CSRF, CORS or the page's
    CSP are ever consulted.

    **A form submission is not a way around that, and an earlier version of this
    docstring claimed it was.** Chrome's mixed-content *blocking* does treat a
    form POST as a navigation and let it through, but a vendor sending
    ``Content-Security-Policy: upgrade-insecure-requests`` -- which Amazon does --
    rewrites every insecure URL its document initiates, form submissions
    included, from http to https. Against a plain-HTTP server the POST arrives as
    a TLS handshake and dies with ERR_SSL_PROTOCOL_ERROR. There is no carve-out
    to exploit.

    **The bookmarklet therefore works only when this application is served over
    TLS**, and only when it was dragged from the https page -- the address it
    posts to is fixed when that page renders. Both confirmed working against a
    real Amazon listing. The paste-a-URL page works either way and is the one
    covered by tests.
    """
    service = _get_catalog_service()
    data = request.get_json(silent=True) or request.form or {}

    url = (data.get('url') or '').strip()
    vendor = data.get('vendor') or _vendor_from_url(url)
    vendor_item_id = data.get('vendor_item_id') or _asin_from_url(url)

    if not request.is_json:
        # The bookmarklet's new tab lands here. Show the operator what the URL
        # yielded and let them finish it; the write happens when they submit to
        # product_capture, which is on this app's origin and carries a token.
        return render_template(
            'product/capture.html',
            title='Capture an Order',
            form_data={
                'url': url,
                'vendor': vendor,
                'vendor_item_id': vendor_item_id,
                'listing_title': data.get('listing_title') or '',
                # Forwarded verbatim, deliberately not parsed *into form_data*.
                # Nothing is written by this representation, so there is nothing
                # yet to validate; the string that goes back out on the hidden
                # field has to be byte-identical to the one that arrived.
                'listing': data.get('listing') or '',
            },
            # Parsed separately, and only for rendering: the form fields fall
            # back to it (US1 scenarios 1 and 2) and the "what will be written"
            # panel is built from it (FR-017). Reading it is not writing it.
            listing=ListingCapture.from_json(data.get('listing')),
            from_bookmarklet=True,
            bookmarklet=_capture_bookmarklet(),
        )

    try:
        purchase = service.capture_order(
            vendor=vendor,
            vendor_item_id=vendor_item_id,
            listing_title=data.get('listing_title'),
            url=url,
            unit_price=data.get('price') or data.get('unit_price'),
            quantity=data.get('quantity'),
            order_date=data.get('order_date'),
            description=data.get('description'),
            manufacturer=data.get('manufacturer'),
            manufacturer_part_number=data.get('manufacturer_part_number'),
            acknowledged_duplicate_of=data.get('acknowledged_duplicate_of'),
            attach_to=data.get('attach_to'),
        )
    except CaptureDecisionRequired as e:
        return jsonify({
            'success': False,
            'error': e.message,
            'assessment': e.assessment.to_dict() if e.assessment else None,
        }), 409
    except ValidationError as e:
        return jsonify({'success': False, 'error': e.message}), 400

    return jsonify({
        'success': True,
        'purchase': purchase.to_dict(),
        'url': url_for('product.purchase_receive', purchase_id=purchase.id),
    }), 201


def _vendor_from_url(url: str) -> str:
    """Derive a vendor name from a listing URL's host.

    The host is a far more stable thing to read than any page element.
    """
    if not url:
        return ''

    host = urlparse(url).hostname or ''
    host = host.lower().removeprefix('www.').removeprefix('smile.')
    if not host:
        return ''

    known = {
        'amazon.com': 'Amazon',
        'digikey.com': 'DigiKey',
        'mouser.com': 'Mouser',
        'ebay.com': 'eBay',
        'mcmaster.com': 'McMaster-Carr',
        'aliexpress.com': 'AliExpress',
    }
    for domain, name in known.items():
        if host == domain or host.endswith('.' + domain):
            return name

    return host


def _asin_from_url(url: str) -> str:
    """Pull an Amazon ASIN out of a URL path.

    Reads the URL, never DOM selectors: Amazon's markup is not a contract but
    ``/dp/<ASIN>/`` has been one for a very long time. Anything it cannot find is
    left blank for the operator to fill in.
    """
    if not url:
        return ''

    match = re.search(r'/(?:dp|gp/product|product)/([A-Z0-9]{10})(?:[/?]|$)', url)
    return match.group(1) if match else ''


@bp.route('/purchases/<int:purchase_id>/receive', methods=['GET', 'POST'])
def purchase_receive(purchase_id):
    """Confirm or amend a purchase on arrival (FR-005, FR-029).

    The captured details are already here; what arrived is allowed to differ from
    what was ordered, so quantity, price and the product's own description stay
    editable. The description is the reason this screen exists in the shape it
    does: correcting it against the thing in hand should not mean leaving here,
    opening the product, saving, and coming back.
    """
    service = _get_catalog_service()
    purchase = service.get_purchase(purchase_id)
    if purchase is None:
        raise ItemNotFoundError(f"Purchase {purchase_id} not found", item_id=str(purchase_id))

    product = _product_or_404(service, purchase.product_id)

    if request.method == 'POST':
        try:
            service.receive_purchase(
                purchase_id,
                received_date=request.form.get('received_date'),
                quantity=request.form.get('quantity'),
                unit_price=request.form.get('unit_price'),
                notes=request.form.get('notes'),
                description=request.form.get('description'),
            )
        except ValidationError as e:
            flash(e.message, 'error')
            return render_template(
                'product/receive.html',
                title='Receive a Purchase',
                purchase=purchase,
                product=product,
                # What they submitted, not what is stored -- a refused
                # description they spent time on should still be on the page.
                form_data=request.form,
            )

        flash('Received.', 'success')
        return redirect(url_for('product.product_detail', product_id=product.id))

    return render_template(
        'product/receive.html',
        title='Receive a Purchase',
        purchase=purchase,
        product=product,
        form_data=None,
    )


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@bp.app_template_filter('relative_age')
def relative_age(age) -> str:
    """Render a timedelta the way a person would say it (FR-024).

    "counted 8 months ago" is a judgement the operator can make. A bare number
    presents a count as currently authoritative when it may be a year stale, and
    a staleness *flag* would need a policy -- how old is stale? -- that nobody has
    measured and the spec does not state.
    """
    if age is None:
        return 'never counted'

    days = age.days
    if days < 0:
        return 'just now'
    if days == 0:
        hours = age.seconds // 3600
        if hours < 1:
            return 'just now'
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if days == 1:
        return 'yesterday'
    if days < 31:
        return f"{days} days ago"
    if days < 365:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"

    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


@bp.route('/products/reorder')
def product_reorder():
    """One view of everything low, with what is already coming marked.

    Both halves are derived at query time (FR-027, FR-028): a manually flagged
    product and one at or below its threshold appear side by side, and the
    on-order marker comes from purchase data rather than from anything the
    operator recorded separately.
    """
    service = _get_catalog_service()
    return render_template(
        'product/reorder.html',
        title='Reorder List',
        entries=service.get_reorder_products(),
    )


@bp.route('/products/categories')
def product_categories():
    """Browse the category tree.

    A hierarchy is worth browsing, and a rename has to be aimed at a row you can
    see -- which is the same reason the tags page exists now that near-duplicate
    tags need spotting before they can be merged.
    """
    service = _get_catalog_service()
    return render_template(
        'product/categories.html',
        title='Categories',
        categories=service.category_tree(),
    )


@bp.route('/products/categories/rename', methods=['POST'])
def category_rename():
    """Rename a category, carrying its subtree (FR-001..FR-007)."""
    service = _get_catalog_service()

    try:
        report = service.rename_category(
            request.form.get('old_path', ''),
            request.form.get('new_path', ''),
        )
    except ValidationError as e:
        # Nothing was written -- the service validates inside the transaction and
        # a raise rolls it back, so the operator sees the tree exactly as it was.
        flash(str(e.message), 'error')
        return redirect(url_for('product.product_categories'))

    flash(
        f'Renamed "{report["from"]}" to "{report["to"]}" -- '
        f'{report["products"]} product{"" if report["products"] == 1 else "s"} '
        f'moved.',
        'success'
    )
    return redirect(url_for('product.product_categories'))


@bp.route('/products/tags')
def product_tags():
    """Every tag with its product count (FR-013).

    Near-duplicate spellings cannot be corrected until they can be seen next to
    each other, which is what this page is for.
    """
    service = _get_catalog_service()
    return render_template(
        'product/tags.html',
        title='Tags',
        tags=service.tag_list_with_counts(),
    )


@bp.route('/products/tags/rename', methods=['POST'])
def tag_rename():
    """Rename a tag, merging into the target when it already exists (FR-008..FR-013)."""
    service = _get_catalog_service()

    try:
        report = service.rename_tag(
            request.form.get('old_name', ''),
            request.form.get('new_name', ''),
        )
    except ValidationError as e:
        flash(str(e.message), 'error')
        return redirect(url_for('product.product_tags'))

    count = report['products']
    plural = '' if count == 1 else 's'
    if report['merged']:
        message = (
            f'Merged "{report["from"]}" into "{report["to"]}" -- '
            f'{count} product{plural} gained it.'
        )
    else:
        message = (
            f'Renamed "{report["from"]}" to "{report["to"]}" -- '
            f'{count} product{plural} carry it.'
        )
    flash(message, 'success')
    return redirect(url_for('product.product_tags'))


@bp.route('/api/categories')
def api_categories():
    """Distinct category paths, for the filter and the inline-create datalist."""
    service = _get_catalog_service()
    return jsonify({
        'success': True,
        'categories': service.list_categories(request.args.get('prefix')),
    })


@bp.route('/api/tags')
def api_tags():
    """Tag names in use (FR-031)."""
    service = _get_catalog_service()
    return jsonify({
        'success': True,
        'tags': service.list_tags(request.args.get('prefix')),
    })


@bp.route('/api/specification-names')
def api_specification_names():
    """Specification names in use, for the name datalists (FR-019)."""
    service = _get_catalog_service()
    return jsonify({
        'success': True,
        'specification_names': service.list_specification_names(
            request.args.get('prefix')
        ),
    })


@bp.route('/api/specification-values')
def api_specification_values():
    """Values recorded under one specification name (FR-020).

    A missing, blank or unrecorded ``name`` is 200 with an empty list rather than
    400: the operator is mid-word, and a suggestion endpoint that errors while
    someone types is worse than one that offers nothing.
    """
    service = _get_catalog_service()
    return jsonify({
        'success': True,
        'specification_values': service.list_specification_values(
            request.args.get('name', ''), request.args.get('prefix')
        ),
    })


@bp.route('/api/products/search')
def api_search_products():
    """Search and filter the catalogue (FR-032)."""
    service = _get_catalog_service()

    try:
        products = service.search_products(
            query=request.args.get('q'),
            category=request.args.get('category'),
            tag=request.args.get('tag'),
            stock=request.args.get('stock'),
            spec_name=request.args.get('spec_name'),
            spec_value=request.args.get('spec_value'),
        )
    except ValidationError as e:
        return jsonify({'success': False, 'error': e.message}), 400

    return jsonify({
        'success': True,
        'count': len(products),
        'products': [p.to_dict() for p in products],
    })


@bp.route('/api/scan', methods=['POST'])
def api_scan():
    """Resolve a scan to a product, an offer to create one, or a search.

    Returns 200 for every well-formed request. An unrecognized scan is not an
    error -- it is ``outcome='search'``, which is a successful answer (SC-008).
    4xx is reserved for a malformed *request*.
    """
    data = request.get_json(silent=True) or {}
    scan = data.get('scan')

    if not isinstance(scan, str):
        return jsonify({
            'success': False,
            'error': 'Request body must be {"scan": "<text>"} with scan as a string'
        }), 400

    service = _get_catalog_service()
    resolution = service.scan(scan)

    payload = resolution.to_dict()
    payload['success'] = True
    if resolution.outcome == 'product':
        # from_scan is what makes FR-019 work: arriving at a known product from a
        # scan offers "add a purchase to this one", because during receiving that
        # is what the operator is holding the thing to do.
        payload['url'] = url_for(
            'product.product_detail', product_id=resolution.product.id, from_scan=1
        )
    elif resolution.outcome == 'create':
        payload['url'] = _create_url(resolution)
    else:
        payload['url'] = url_for('product.product_search', q=resolution.classification.raw)

    return jsonify(payload)


def _create_url(resolution) -> str:
    """Build the create-form URL carrying everything the scan yielded (FR-018)."""
    prefill = resolution.prefill
    params = {
        'identifier': prefill.get('identifier', ''),
        'id_type': prefill.get('id_type', 'MPN'),
        'raw_scan': resolution.classification.raw,
    }
    if prefill.get('quantity'):
        params['quantity'] = prefill['quantity']
    if prefill.get('order_reference'):
        params['order_reference'] = prefill['order_reference']
    if prefill.get('supplier_order_reference'):
        params['supplier_order_reference'] = prefill['supplier_order_reference']
    if prefill.get('date_code'):
        params['date_code'] = prefill['date_code']
    if prefill.get('distributor_part_number'):
        params['distributor_part_number'] = prefill['distributor_part_number']
    return url_for('product.product_new', **params)


@bp.route('/api/products', methods=['POST'])
def api_create_product():
    """Create a product from JSON."""
    service = _get_catalog_service()
    data = request.get_json(silent=True) or {}

    try:
        product = service.create_product(
            description=data.get('description', ''),
            manufacturer=data.get('manufacturer'),
            manufacturer_part_number=data.get('manufacturer_part_number'),
            specifications=data.get('specifications'),
            category_path=data.get('category_path'),
            location=data.get('location'),
            quantity=data.get('quantity'),
            reorder_threshold=data.get('reorder_threshold'),
            notes=data.get('notes'),
            identifiers=data.get('identifiers'),
            tags=data.get('tags'),
        )
    except ValidationError as e:
        return jsonify({'success': False, 'error': e.message}), 400

    return jsonify({'success': True, 'product': product.to_dict(include_related=True)}), 201


@bp.route('/api/products/<int:product_id>', methods=['GET'])
def api_get_product(product_id):
    """Fetch one product as JSON."""
    service = _get_catalog_service()
    product = _product_or_404(service, product_id)
    return jsonify({'success': True, 'product': product.to_dict(include_related=True)})


@bp.route('/api/products/<int:product_id>/quantity', methods=['PATCH'])
def api_set_quantity(product_id):
    """Set, change or stop tracking a quantity (FR-022, FR-023).

    An explicit ``null`` stops tracking, which is a different thing from omitting
    the field -- that distinction is the API-level expression of the tri-state,
    and it is what SC-007 is measured on.
    """
    service = _get_catalog_service()
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or 'quantity' not in data:
        return jsonify({
            'success': False,
            'error': 'Request body must include "quantity" (a number, or null to stop tracking)'
        }), 400

    try:
        product = service.set_quantity(product_id, data['quantity'])
    except ValidationError as e:
        return jsonify({'success': False, 'error': e.message}), 400

    return jsonify({'success': True, 'product': product.to_dict()})


@bp.route('/api/products/<int:product_id>/stock-status', methods=['PATCH'])
def api_set_stock_status(product_id):
    """Set or clear the manual low/out flag (FR-025)."""
    service = _get_catalog_service()
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or 'stock_status' not in data:
        return jsonify({
            'success': False,
            'error': 'Request body must include "stock_status" ("low", "out", or null)'
        }), 400

    try:
        product = service.set_stock_status(product_id, data['stock_status'])
    except ValidationError as e:
        return jsonify({'success': False, 'error': e.message}), 400

    return jsonify({'success': True, 'product': product.to_dict()})


@bp.route('/api/products/<int:product_id>/label', methods=['POST'])
def api_print_product_label(product_id):
    """Compose and print a product label (FR-011, FR-013).

    Composes from the stored record every time -- there is no cached image, so a
    reprint after an edited description reflects the edit. What "no re-entry"
    means is that the operator types nothing, which holds unconditionally.
    """
    from app.services.label_printer import LABEL_TYPES, get_available_label_types
    from app.services.product_label import format_provenance, print_product_label

    service = _get_catalog_service()
    product = _product_or_404(service, product_id)

    data = request.get_json(silent=True) or {}
    label_type = str(data.get('label_type', '')).strip()

    if label_type not in LABEL_TYPES:
        return jsonify({
            'success': False,
            'error': f'Invalid label type. Available types: {get_available_label_types()}'
        }), 400

    # Not history[-1]: undated purchases sort last but are not the most recent.
    provenance = format_provenance(service.get_latest_purchase(product_id))

    try:
        print_product_label(
            description=product.description,
            code=product.internal_code,
            provenance=provenance,
            label_config=LABEL_TYPES[label_type],
        )
    except Exception as e:
        current_app.logger.error(f'Error printing product label for {product_id}: {e}')
        return jsonify({'success': False, 'error': 'Failed to print label'}), 500

    current_app.logger.info(
        f'Printed {label_type} label for product {product_id} ({product.internal_code})'
    )
    return jsonify({
        'success': True,
        'message': f'Label printed for {product.description}',
        'product_id': product_id,
        'code': product.internal_code,
        'label_type': label_type,
    })


@bp.route('/api/products/<int:product_id>/attachments', methods=['POST'])
def api_add_product_attachment(product_id):
    """Attach a file to a product -- a datasheet, a diagram (FR-034)."""
    return _upload_attachment('product', product_id)


@bp.route('/api/purchases/<int:purchase_id>/attachments', methods=['POST'])
def api_add_purchase_attachment(purchase_id):
    """Attach a file to a purchase -- a saved listing, a receipt (FR-034)."""
    return _upload_attachment('purchase', purchase_id)


@bp.route('/api/attachments/<int:attachment_id>', methods=['DELETE'])
def api_delete_attachment(attachment_id):
    """Remove an attachment, and its bytes if nothing else references them."""
    from app.photo_service import PhotoService

    with PhotoService(_get_storage_backend()) as photos:
        if not photos.delete_attachment(attachment_id):
            raise ItemNotFoundError(
                f"Attachment {attachment_id} not found", item_id=str(attachment_id)
            )

    return '', 204


def _upload_attachment(owner: str, owner_id: int):
    """Shared upload handling for both owners.

    An attachment belongs to a product **or** a purchase, never both -- which the
    database enforces, and which this keeps honest by never offering a way to say
    both at once.
    """
    from app.photo_service import PhotoService

    uploaded = request.files.get('file')
    if uploaded is None or not uploaded.filename:
        return jsonify({'success': False, 'error': 'A file is required'}), 400

    data = uploaded.read()

    try:
        with PhotoService(_get_storage_backend()) as photos:
            if owner == 'product':
                attachment = photos.upload_product_attachment(
                    owner_id, data, uploaded.filename, uploaded.mimetype
                )
            else:
                attachment = photos.upload_purchase_attachment(
                    owner_id, data, uploaded.filename, uploaded.mimetype
                )
            payload = attachment.to_dict()
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except RuntimeError as e:
        current_app.logger.error(f'Attachment upload failed: {e}')
        return jsonify({'success': False, 'error': 'Attachment upload failed'}), 500

    return jsonify({'success': True, 'attachment': payload}), 201


@bp.route('/api/products/<int:product_id>/identifiers', methods=['POST'])
def api_add_identifier(product_id):
    """Attach a coded name to a product (FR-007, FR-010)."""
    service = _get_catalog_service()
    data = request.get_json(silent=True) or {}

    try:
        identifier = service.add_identifier(
            product_id,
            id_type=data.get('id_type', ''),
            value=data.get('value', ''),
            vendor=data.get('vendor'),
            override=bool(data.get('override', False)),
        )
    except ValidationError as e:
        return jsonify({'success': False, 'error': e.message}), 400
    except DuplicateItemError as e:
        # The value is fine; another product already claims it. Say which one, so
        # the operator can resolve it rather than guess.
        return jsonify({
            'success': False,
            'error': e.message,
            'owning_product_id': int(e.item_id),
        }), 409

    return jsonify({'success': True, 'identifier': identifier.to_dict()}), 201


@bp.route('/api/products/<int:product_id>/identifiers/<int:identifier_id>', methods=['DELETE'])
def api_remove_identifier(product_id, identifier_id):
    """Detach a coded name. The product itself survives losing every name."""
    service = _get_catalog_service()

    if not service.remove_identifier(product_id, identifier_id):
        raise ItemNotFoundError(
            f"Identifier {identifier_id} not found on product {product_id}",
            item_id=str(identifier_id)
        )

    return '', 204
