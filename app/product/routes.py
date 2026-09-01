"""
Product catalog routes.

Thin by design (Constitution II): no ORM queries and no raw SQL live here.
Everything delegates to CatalogService. Server-rendered pages return HTML,
``/api/*`` returns JSON, and errors go through the project's existing exceptions
rather than any new error machinery.
"""

import json
import logging
import re
from decimal import Decimal
from typing import List
from urllib.parse import unquote, urlparse

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for

from app import csrf
from app.catalog_service import (
    AMAZON_ORDER_VENDOR,
    AMAZON_VENDOR,
    DIGIKEY_ORDER_VENDOR,
    DIGIKEY_VENDOR,
    MCMASTER_ORDER_VENDOR,
    MCMASTER_VENDOR,
    VENDOR_SCOPED_TYPES,
    CatalogService,
)
from app.services import order_vendors
from app.exceptions import (
    AuthenticationError, CaptureDecisionRequired, ConfigurationError,
    DuplicateItemError, ItemNotFoundError, RateLimitError, TemporaryError,
    ValidationError, WorkshopInventoryError,
)
from app.models import (
    AmazonOrder,
    CapturedBarcode,
    IdentifierType,
    ListingCapture,
    McMasterOrder,
)
from app.photo_service import PhotoService
from app.product import bp
from app.services.listing_images import store_listing_images
from app.utils import internal_id


logger = logging.getLogger(__name__)


def _get_storage_backend():
    """Get the storage backend for the current app context"""
    if 'STORAGE_BACKEND' in current_app.config:
        return current_app.config['STORAGE_BACKEND']

    from app.mariadb_storage import MariaDBStorage
    return MariaDBStorage()


def _get_catalog_service() -> CatalogService:
    """Get the catalog service bound to this app's storage backend"""
    return CatalogService(_get_storage_backend())


def _get_digikey_client():
    """This app's DigiKey client, or None when it is not configured.

    None is an ordinary state and every DigiKey route handles it by saying so
    (024 FR-036). A test injects a fake by setting ``app.config['DIGIKEY_CLIENT']``.
    """
    return current_app.config.get('DIGIKEY_CLIENT')


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
    """The catalog list, with text search and category/tag/stock filters."""
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

        # A DigiKey part capture posts its DigiKey part number alongside the
        # manufacturer's, so the product scans back from either (024 FR-028).
        digikey_part_number = (request.form.get('digikey_part_number') or '').strip()
        if digikey_part_number:
            identifiers.append({
                'id_type': IdentifierType.DISTRIBUTOR.value,
                'value': digikey_part_number,
                'vendor': DIGIKEY_VENDOR,
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

        # The slow, partially-failing half, after the transaction has already
        # committed (024 FR-041). A datasheet DigiKey cannot serve must cost the
        # datasheet and never the product -- the same split store_listing_images
        # was written for.
        documents = [
            url for url in (
                request.form.get('digikey_photo_url'),
                request.form.get('digikey_datasheet_url'),
            )
            if (url or '').startswith(('http://', 'https://'))
        ]
        if documents:
            outcome = store_listing_images(
                product.id, documents, _get_storage_backend()
            )
            if getattr(outcome, 'stored', 0):
                flash(f'Attached {outcome.stored} file(s) from DigiKey.', 'info')

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

    # 024 FR-033: a scanned bag whose part this catalog does not hold, from an
    # order it did not capture, used to arrive as the four or five values the
    # label itself carries. If DigiKey is configured, fill in what they know
    # about the part as well.
    #
    # Silent when it fails, deliberately: the operator is looking at a draft, not
    # at a DigiKey screen, and the pre-024 draft is still a perfectly good one.
    distributor_part_number = ecia_fields.get('distributor_part_number')
    client = _get_digikey_client()
    if client is not None and distributor_part_number and not prefill['description']:
        try:
            part = client.get_part(distributor_part_number)
        except WorkshopInventoryError:
            part = None
        if part is not None:
            prefill.update({
                'description': part.description,
                'manufacturer': part.manufacturer,
                'manufacturer_part_number': part.manufacturer_part_number,
                'category_path': part.category_path,
                'digikey_part_number': part.digikey_part_number or distributor_part_number,
                'digikey_datasheet_url': part.datasheet_url,
                'digikey_photo_url': part.photo_url,
                'specifications': [
                    {'name': name, 'value': value} for name, value in part.parameters
                ],
            })
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


@bp.route('/products/<product_code>')
def product_by_code(product_code):
    """Reach a product by the permanent code printed on its label (009 FR-015).

    **Redirects rather than rendering.** 009 FR-015 asks for the same content
    and the same actions as the canonical page; a redirect makes that identical
    by construction instead of a claim to test, and keeps product_detail's
    assembly of purchases, photos and prices in one place. The record number
    stays canonical (009 FR-017), and the address bar is where that is said.

    **The code is upper-cased here, not in internal_id.** Crockford base32 omits
    I, L, O and U precisely so a person can retype a scuffed label, and someone
    typing a code into an address bar is that person. Its alphabet is
    uppercase-only, so folding is injective and cannot reach a different product
    (009 FR-018). Loosening ``internal_id.is_internal_id`` instead would make
    ``witabc...`` an internal code to the *scanner*, changing a classification
    that resolves today (009 FR-008) for a convenience owed to one route.

    Werkzeug ranks argument-free rules above parameterized ones and the integer
    converter above the string one, so ``/products/new`` and ``/products/42``
    keep their own handlers. That is defined behaviour, and
    ``tests/unit/test_product_routes.py`` pins it because it would otherwise
    fail silently and far from its cause.
    """
    code = product_code.upper()
    if not internal_id.is_internal_id(code):
        raise ItemNotFoundError(f"No product carries the code {product_code}")

    service = _get_catalog_service()
    product = service.find_product_by_identifier(
        code, id_type=IdentifierType.INTERNAL.value
    )
    if product is None:
        raise ItemNotFoundError(f"No product carries the code {code}")

    return redirect(url_for('product.product_detail', product_id=product.id))


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
                supplier_order_reference=request.form.get('supplier_order_reference'),
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
        vendor_item_id = (
            request.form.get('vendor_item_id', '')
            or _asin_from_url(url)
            or _mcmaster_part_from_url(url)
        )
        listing = ListingCapture.from_json(request.form.get('listing'))

        # The listing fills the blanks and never overwrites: the operator was
        # looking at the thing, and a value they typed wins over one a selector
        # found (US1 scenario 3).
        #
        # **Absent, not merely empty.** The confirmation form always submits all
        # three of these -- pre-filled from the same payload -- so a field that
        # arrives empty is one the operator *cleared*, and clearing is a change
        # like any other. Falling back on empty would quietly put the extracted
        # value back and there would be no way to say "the listing is wrong about
        # this". Falling back on absent still covers a POST that carries the
        # payload and nothing else.
        #
        # The part number joined the pair in 019: unlike the brand and the price,
        # which the agent puts on the payload, it is derived here from the
        # listing's own product-information rows. Same rule either way.
        manufacturer = request.form.get('manufacturer')
        unit_price = request.form.get('unit_price')
        manufacturer_part_number = request.form.get('manufacturer_part_number')
        if listing is not None:
            if manufacturer is None:
                manufacturer = listing.brand
            if unit_price is None:
                unit_price = listing.price
            if manufacturer_part_number is None:
                manufacturer_part_number = listing.manufacturer_part_number()

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
                manufacturer_part_number=manufacturer_part_number,
                acknowledged_duplicate_of=request.form.get('acknowledged_duplicate_of'),
                attach_to=request.form.get('attach_to'),
                listing=listing,
                # Straight from the form and from nowhere else. Unlike the two
                # fields above, these three have no listing fallback and must
                # not grow one (018 FR-013): no selector can read where a thing
                # goes in this shop, so a value that looked extracted would be a
                # guess wearing the clothes of a statement.
                category_path=request.form.get('category_path'),
                location=request.form.get('location'),
                sub_location=request.form.get('sub_location'),
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

        # Above the image tally, because what the product is called by matters
        # more than how many pictures of it landed. Read-only and derived from
        # the catalog's final state -- the write happened inside capture_order.
        if listing is not None:
            barcodes = service.describe_captured_barcodes(purchase.product_id, listing)
            if barcodes:
                flash(
                    _barcode_tally(barcodes),
                    'success' if all(n.outcome == 'recorded' for n in barcodes)
                    else 'warning',
                )

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


def _barcode_tally(barcodes: List[CapturedBarcode]) -> str:
    """Say what the listing's barcode rows came to (016 FR-009).

    Follows ``_image_tally``'s rule: everything that did not land is named, and
    named with the reason. A barcode that quietly failed its check digit is the
    failure the operator cannot see -- they find out months later when the box
    will not scan, by which time the listing is gone.

    The "kept as a specification" reassurance is conditional, because it is not
    always true: a row the merge dropped took its value with it. Telling the
    operator a value is on the product when it is not would be worse than saying
    nothing, which is the whole reason this tally exists.
    """
    sentences = []
    for note in barcodes:
        kept = " It is kept as a specification." if note.kept_as_specification else ""

        if note.outcome == 'recorded':
            sentences.append(f"Barcode {note.value} is recorded on this product.")
        elif note.outcome == 'unusable':
            sentences.append(
                f"The listing's {note.row_name} value \"{note.value}\" was not "
                f"recorded: it is not a valid barcode.{kept}"
            )
        elif note.outcome == 'taken':
            sentences.append(
                f"Barcode {note.value} was not recorded: product {note.holder_id} "
                f"({note.holder_description}) already holds it.{kept}"
            )
        elif note.outcome == 'not_examined':
            sentences.append(
                f"The listing's {note.row_name} row was not examined, because this "
                f"product already lists a {note.row_name} row."
            )
    return ' '.join(sentences)


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
        # "already stored" rather than "already on this product": a duplicate is
        # equally a second copy of something an earlier capture stored and a
        # second copy of something stored a moment ago in this one, and the
        # operator's next action is the same either way.
        parts.append(f"{images.duplicates} skipped as already stored")
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
    why the TLS caveat below is about where you drag it from. Their scheme is
    whatever ``request.scheme`` says, which behind a TLS-terminating proxy means
    whatever ``X-Forwarded-Proto`` says -- see the ``ProxyFix`` wrapping in
    ``create_app``. Without it the page renders over https and hands out http
    addresses, which is issue #89.

    Their **port** comes the same way, from ``X-Forwarded-Port``, and is the
    part that is easy to forget because it is invisible on any deployment
    sitting on 80 or 443. On a non-default port a proxy that does not declare
    it hands out a bookmarklet addressed to a port nothing listens on, so the
    agent never loads and clicking it does nothing at all -- issue #114. These
    two addresses are the only ones in the application that have to survive
    being read from another origin; everything else is relative and would not
    have noticed.

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

    **This is the only CSRF exemption the product catalog adds**, and the only
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
    vendor_item_id = (
        data.get('vendor_item_id')
        or _asin_from_url(url)
        or _mcmaster_part_from_url(url)
    )

    # An order read off a page rides the same endpoint as one extra form field,
    # because
    # the bookmarklet's text cannot change without the operator re-dragging it
    # (FR-034, research.md §2). **This still writes nothing** -- it is a read of
    # the payload plus a read of the catalog, and the operator can close the tab
    # with no trace left (FR-005).
    #
    # A request carrying no `order` field takes a path identical to today's,
    # which is what the existing capture tests assert and what makes SC-010
    # checkable by running them unchanged.
    if not request.is_json and data.get('order'):
        return _page_order_review(service, data.get('order'))

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


def _mcmaster_part_from_url(url: str) -> str:
    """Pull a McMaster part number out of a URL path.

    The same shape ``capture-agent.js`` dispatches on, and **deliberately
    duplicated** rather than shared: the two live on opposite sides of a machine
    boundary, the agent's copy decides which reader runs, and this one is what
    the paste-a-URL form uses with no agent involved at all (FR-025). The Amazon
    pair carries the same note.

    ``/91290A115/`` -- digits, an upper-case letter, then alphanumerics.
    Anything it cannot find is blank for the operator to fill in, never an
    error.

    **Matched on the path, never the host**, exactly as ``_asin_from_url`` is
    and for the same two reasons: a path is a contract in a way a host lookup
    table is not, and the e2e harness serves vendor fixtures from this
    application's own origin, so a host gate would leave this with no end-to-end
    coverage at all (research.md §3). The cost is the one the Amazon reader
    already accepts -- some other vendor's ``/12345A1/`` would prefill a part
    number -- and it is a prefill on a form whose whole purpose is to be checked
    before it is submitted.

    Two other shapes reach a McMaster part and neither is a product page:
    ``/catalog/<part>`` redirects to ``/products/<part-lowercased>/``, which is
    a filterable family *table* naming many part numbers. Neither yields a part
    here, because neither names one thing (research.md §5).
    """
    if not url:
        return ''

    path = urlparse(url).path if '//' in url else url
    match = re.match(r'^/(\d{1,5}[A-Z][0-9A-Z]{0,6})/?$', path)
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
                # The quantity goes the same way: a scanned bag's count, or a
                # hand-typed correction, must survive a refusal about some other
                # field.
                scanned_quantity=request.form.get('quantity', ''),
                form_data=request.form,
            )

        flash('Received.', 'success')
        return redirect(url_for('product.product_detail', product_id=product.id))

    return render_template(
        'product/receive.html',
        # FR-020: a scanned bag's label says what is in *this* bag, which is not
        # always what was ordered. Editable, and absent it behaves as it always
        # has.
        scanned_quantity=request.args.get('quantity', ''),
        title='Receive a Purchase',
        purchase=purchase,
        product=product,
        form_data=None,
    )


@bp.route('/purchases/<int:purchase_id>/delete', methods=['GET', 'POST'])
def purchase_delete(purchase_id):
    """Remove a purchase recorded in error (032 FR-001, issue #130).

    A duplicate, a mis-captured line, an order captured twice by different
    paths. GET confirms, POST deletes -- the same shape ``purchase_receive``
    has, and for the same reason: the details the operator needs to tell the
    right row from the wrong one are on the server, not in the row they clicked.

    **The attachment count is why this is a page rather than a dialog.** The
    order screen does not load attachments, so a confirmation built from the
    listing's own markup would need both listings to grow a count query. Here it
    is read once, for both entry points.
    """
    service = _get_catalog_service()
    purchase = service.get_purchase(purchase_id)
    if purchase is None:
        raise ItemNotFoundError(f"Purchase {purchase_id} not found", item_id=str(purchase_id))

    product = _product_or_404(service, purchase.product_id)
    return_to = _purchase_delete_return_to(request.values.get('return_to'))

    if request.method == 'POST':
        deletion = service.delete_purchase(purchase_id)
        if deletion is None:
            # Deleted between the load above and here -- the same product open
            # in two tabs. Report it rather than reporting a success that did
            # nothing (FR-011).
            raise ItemNotFoundError(
                f"Purchase {purchase_id} not found", item_id=str(purchase_id)
            )

        flash(_purchase_deleted_sentence(deletion), 'success')
        return redirect(_purchase_delete_destination(deletion, return_to))

    from app.photo_service import PhotoService

    with PhotoService(_get_storage_backend()) as photos:
        attachment_count = len(photos.get_purchase_attachments(purchase_id))

    return render_template(
        'product/purchase_delete.html',
        title='Delete a Purchase',
        purchase=purchase,
        product=product,
        attachment_count=attachment_count,
        return_to=return_to,
        cancel_url=_purchase_delete_cancel_url(purchase, return_to),
    )


def _purchase_delete_return_to(value) -> str:
    """Where to go afterwards, as a flag rather than as a URL.

    Two accepted values and nothing else. The order address is built from the
    purchase's own vendor and order number, so no caller-supplied address is
    ever followed and there is no open-redirect question to answer.
    """
    return 'order' if value == 'order' else 'product'


def _purchase_delete_destination(deletion, return_to: str) -> str:
    """Where a completed deletion lands.

    ``return_to='order'`` on a purchase carrying no supplier order reference
    falls back to the product: a hand-recorded or listing-captured purchase has
    no order to return to, which is a fallback rather than an error.
    """
    if return_to == 'order' and deletion.supplier_order_reference:
        return url_for(
            'product.order_detail',
            vendor=deletion.vendor,
            order_number=deletion.supplier_order_reference,
        )
    return url_for('product.product_detail', product_id=deletion.product_id)


def _purchase_delete_cancel_url(purchase, return_to: str) -> str:
    """Where Cancel goes -- back where they came from, changing nothing."""
    if return_to == 'order' and purchase.supplier_order_reference:
        return url_for(
            'product.order_detail',
            vendor=purchase.vendor,
            order_number=purchase.supplier_order_reference,
        )
    return url_for('product.product_detail', product_id=purchase.product_id)


def _purchase_deleted_sentence(deletion) -> str:
    """What was removed (FR-008).

    Names the purchase the same way the confirmation did, so the flash reads as
    a confirmation of the thing just seen rather than as a fresh claim.
    """
    parts = [f"Deleted the {deletion.vendor} purchase"]
    if deletion.order_date:
        parts.append(f"ordered {deletion.order_date.strftime('%Y-%m-%d')}")
    if deletion.quantity is not None:
        parts.append(f"of {deletion.quantity}")

    sentence = ' '.join(parts) + '.'
    if deletion.attachments_deleted:
        noun = 'file' if deletion.attachments_deleted == 1 else 'files'
        sentence += f" {deletion.attachments_deleted} attached {noun} went with it."
    return sentence


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@bp.app_template_filter('relative_age')
def relative_age(age, unknown: str = 'never counted') -> str:
    """Render a timedelta the way a person would say it (FR-024).

    "counted 8 months ago" is a judgement the operator can make. A bare number
    presents a count as currently authoritative when it may be a year stale, and
    a staleness *flag* would need a policy -- how old is stale? -- that nobody has
    measured and the spec does not state.

    A count's age and a manual flag's age are both rendered here, which is 008
    FR-012 satisfied by construction: two pieces of evidence on one screen
    cannot drift into different vocabularies if one function renders both. Only
    the no-date wording differs, hence ``unknown`` -- "never counted" is right
    for a count and wrong for a flag, which was certainly set; its date simply
    was not recorded. The flag templates pass 'at an unknown time'.

    Args:
        age: The timedelta to render, or None.
        unknown: What to say when there is no age to render.
    """
    if age is None:
        return unknown

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


# ---------------------------------------------------------------------------
# DigiKey orders (feature 024)
#
# Every one of these renders a message on a working page rather than an error
# page when DigiKey cannot be reached: the operator's next action is to retype
# or retry, and an error page is a dead end (FR-036, FR-038).
# ---------------------------------------------------------------------------

# What each exception the DigiKey client raises means to the operator. The four
# states FR-038 requires be distinguishable, plus throttling. No new exception
# class was needed; every one of these already existed.
_DIGIKEY_MESSAGES = (
    (ConfigurationError, 'not_configured'),
    (AuthenticationError, 'unauthorized'),
    (ItemNotFoundError, 'not_found'),
    (RateLimitError, 'throttled'),
    (TemporaryError, 'unavailable'),
)


def _digikey_problem(error) -> str:
    """Which of the five failure states this is, for the template to render."""
    for exception_type, state in _DIGIKEY_MESSAGES:
        if isinstance(error, exception_type):
            return state
    return 'unavailable'


def _digikey_part_from_url(value: str) -> str:
    """Pull a part number out of a DigiKey product address, or return it as given.

    A DigiKey product page is
    ``digikey.com/en/products/detail/<manufacturer-slug>/<mpn-slug>/<product-id>``.
    **The trailing segment is DigiKey's internal product id, not a part number**
    -- which is why ``_asin_from_url`` correctly yields nothing for a DigiKey
    address, and why deriving a part number from it would be wrong. The
    second-to-last segment is the manufacturer part number, and ProductDetails
    resolves one of those as happily as a DigiKey part number.

    Anything that is not a DigiKey product address is returned untouched, so a
    typed part number passes straight through.
    """
    text = (value or '').strip()
    if 'digikey.' not in text.lower() or '/products/detail/' not in text.lower():
        return text

    path = urlparse(text).path.rstrip('/')
    segments = [segment for segment in path.split('/') if segment]
    try:
        marker = segments.index('detail')
    except ValueError:
        return text

    # detail / manufacturer / mpn / product-id
    if len(segments) < marker + 4:
        return text
    return unquote(segments[marker + 2])


def _digikey_entry(problem=None, message=None, sales_order_number='', status=200,
                   recent=None, listing_error=None):
    """The sales order number form, optionally carrying a problem to explain.

    ``recent`` is the account's own order listing (031 FR-018), shown above the
    form so a backfill does not mean copying sales order numbers off DigiKey's
    website. It is absent whenever it could not be read, and the form below it
    works either way -- **a failure to enumerate must never remove the ability
    to capture by number** (FR-022).
    """
    return render_template(
        'product/digikey_order_entry.html',
        title='Capture a DigiKey Order',
        sales_order_number=sales_order_number,
        problem=problem,
        message=message,
        configured=_get_digikey_client() is not None,
        recent=recent,
        listing_error=listing_error,
    ), status


def _review_context(vendor, order, review, form_data, payload=None,
                    start_over_url=None):
    """The context the one order-review template needs, for any vendor.

    ``item_id`` is handed over as a callable rather than pre-computed per line
    because the template needs it inside its loop, and which attribute holds it
    is exactly the sort of thing that should stay on the OrderVendor rather than
    become a chain of ``{% if %}`` in a template (029 FR-036).
    """
    return {
        'vendor': vendor,
        'review': review,
        'order': order,
        'payload': payload,
        'form_data': form_data or {},
        'item_id': vendor.item_id_of,
        'order_number': (
            vendor.order_fields(order)['supplier_order_reference']
            if order is not None else ''
        ),
        'start_over_url': start_over_url or url_for('product.product_search'),
    }


@bp.route('/products/digikey/orders', methods=['GET', 'POST'])
def digikey_order_capture():
    """Enter a sales order number; get a review of what capturing it would do.

    **Writes nothing** (FR-004). The review is a read of DigiKey plus a read of
    the catalog, and the operator can close the tab with no trace left.
    """
    client = _get_digikey_client()

    if request.method == 'GET':
        # FR-036: say it before they type an order number, not after.
        if client is None:
            return _digikey_entry(problem='not_configured')[0]

        # 031 FR-018. One call, and its failure is a message rather than an
        # error page: the operator's next action either way is to use the form
        # underneath it.
        recent, listing_error = None, None
        try:
            recent = client.list_orders()
        except WorkshopInventoryError as e:
            listing_error = e.message

        return _digikey_entry(recent=recent, listing_error=listing_error)[0]

    sales_order_number = (request.form.get('sales_order_number') or '').strip()
    if not sales_order_number:
        return _digikey_entry(
            problem='blank',
            message='Enter the sales order number from your DigiKey order '
                    'confirmation, or scan a bag label.',
        )[0]

    if client is None:
        return _digikey_entry(
            problem='not_configured', sales_order_number=sales_order_number
        )[0]

    try:
        order = client.get_order(sales_order_number)
    except WorkshopInventoryError as e:
        return _digikey_entry(
            problem=_digikey_problem(e),
            message=e.message,
            sales_order_number=sales_order_number,
        )[0]

    service = _get_catalog_service()
    review = service.review_digikey_order(order, client)

    return render_template(
        'product/order_review.html',
        title=f'DigiKey Order {order.sales_order_number}',
        **_review_context(
            DIGIKEY_ORDER_VENDOR, order, review, {},
            start_over_url=url_for('product.digikey_order_capture'),
        ),
    )


@bp.route('/products/digikey/orders/capture', methods=['POST'])
def digikey_order_confirm():
    """Confirm a reviewed order and write it.

    The order is **re-read from DigiKey** rather than rebuilt from the form: the
    fetched order is the authority on what was bought, and a form is a thing the
    operator was looking at some seconds ago.
    """
    client = _get_digikey_client()
    sales_order_number = (request.form.get('sales_order_number') or '').strip()

    if client is None:
        return _digikey_entry(
            problem='not_configured', sales_order_number=sales_order_number
        )[0]

    try:
        order = client.get_order(sales_order_number)
    except WorkshopInventoryError as e:
        return _digikey_entry(
            problem=_digikey_problem(e),
            message=e.message,
            sales_order_number=sales_order_number,
        )[0]

    decisions = _order_decisions(request.form, order)
    service = _get_catalog_service()

    try:
        result = service.capture_digikey_order(
            order, decisions, client,
            arrived_date=request.form.get('arrived_date'),
        )
    except ValidationError as e:
        # Re-render the review carrying what was submitted, so a description the
        # operator spent time on is not lost. The same thing purchase_receive
        # already does for a refused description.
        review = service.review_digikey_order(order, client)
        flash(e.message, 'error')
        return render_template(
            'product/order_review.html',
            title=f'DigiKey Order {order.sales_order_number}',
            **_review_context(
                DIGIKEY_ORDER_VENDOR, order, review, request.form,
                start_over_url=url_for('product.digikey_order_capture'),
            ),
        )

    flash(_digikey_capture_summary(result), 'success')
    return redirect(url_for(
        'product.digikey_order_detail',
        sales_order_number=order.sales_order_number,
    ))


def _order_decisions(form, order):
    """The per-line decisions the form carries, keyed by ``line.form_key``.

    Built by walking the **order**, not the form: a decision submitted for a
    line the order does not carry is ignored rather than acted on.

    ``form_key``, not the item id: an order can carry the same item on two
    lines, and keying by item id gave them one shared set of fields so neither
    could be steered on its own. PR #116 review.

    ``quantity`` and ``unit_price`` are read for every vendor, and ignored by the
    ones that do not offer the edit -- their ``line_fields`` never looks at the
    decision, so an absent field costs nothing and there is no branch here.

    One implementation since feature 029.
    """
    decisions = {}
    for line in order.lines:
        key = line.form_key
        decisions[key] = {
            'include': form.get(f'include[{key}]') is not None,
            'description': form.get(f'description[{key}]') or '',
            'quantity': form.get(f'quantity[{key}]') or '',
            'unit_price': form.get(f'unit_price[{key}]') or '',
            'resolution': form.get(f'resolution[{key}]') or '',
            # Whether a purchase already recorded for this item is this line's
            # (033 FR-008). Its own field rather than sharing ``resolution``,
            # which answers the *contradicted item id* question with the same
            # word 'separate' -- a line can carry both questions, and one input
            # answering two of them applies the wrong answer to one.
            'same_purchase': form.get(f'same_purchase[{key}]') or '',
            'apply_change': form.get(f'apply_change[{key}]') is not None,
            # Per line rather than per order, so that an order which arrived
            # except for one back-ordered item can still say so (031 FR-029).
            # The order-level checkbox on the review is a convenience that ticks
            # these; it is never itself submitted, so what the operator can see
            # ticked is exactly what gets recorded.
            'arrived': form.get(f'arrived[{key}]') is not None,
        }
    return decisions


def _order_capture_summary(result, thin_sentence=None,
                           thin_products=False) -> str:
    """What just happened, in one sentence the operator can act on.

    **Every outcome that changed the database has to appear here.** A capture
    that only applies a quantity change writes no purchase, so leading on the
    purchase count alone would report "Nothing new to capture" over the top of
    an update that genuinely landed -- the same silent-write problem the
    apply_change fix exists to close, moved from the service to the flash.
    PR #116 review.

    **Every such outcome therefore goes in the block below, above the
    fallback.** Appending one after it produced exactly the contradiction the
    rule exists to prevent: a rename-only re-capture led with "Nothing new to
    capture" and then said it had refiled the order (PR #123 review). Keeping
    them together makes the fallback mean "none of the above happened" by
    construction rather than by a condition that has to be remembered.
    ``OrderCaptureResult.wrote_anything`` answers the same question, and
    ``test_the_fallback_agrees_with_wrote_anything`` holds the two in step.

    ``thin_sentence`` is the one part that is genuinely per-vendor: what "this
    line came back thin" *means* differs, so how it is worded does too. It is
    passed in by the route rather than carried on the OrderVendor, because it is
    presentation and the vendor is not the place for that.

    ``thin_products`` says the products this capture created carry only what an
    order page stated (029 FR-026). Said here as well as on the review because
    this is the message the operator leaves the page with, and a title-only
    product they do not know is title-only is one they will not think to fill in.
    """
    parts = []
    if result.purchase_ids:
        parts.append(f"Captured {len(result.purchase_ids)} line(s)")
    if result.purchases_adopted:
        # A write, and in the block above the fallback because of it: a capture
        # whose every line was adopted creates no purchase, and leading with
        # "Nothing new to capture" over the top of rows that just joined this
        # order is the contradiction this block exists to prevent (033 FR-011).
        parts.append(
            f"{len(result.purchases_adopted)} purchase(s) you had already "
            f"recorded added to this order rather than duplicated"
        )
    if result.lines_updated:
        parts.append(f"{result.lines_updated} line(s) updated")
    if result.renamed_from:
        # A write, and one the operator did not ask for line by line -- so it is
        # named rather than left silent.
        parts.append(
            f"Refiled from {result.renamed_from!r}, which this order was "
            f"renamed from on McMaster"
        )
    if not parts:
        # Nothing was written at all. Say so plainly rather than "Captured 0".
        parts.append("Nothing new to capture")

    if result.lines_arrived:
        # A write the operator did not make line by line: they ticked one box
        # and every line took a delivery date from it. Named for the same reason
        # the refile is (031 FR-024).
        parts.append(
            f"{result.lines_arrived} recorded as already arrived, so nothing "
            f"here is reported as on its way"
        )
    if result.products_created:
        parts.append(f"{result.products_created} new product(s)")
    if result.products_attached:
        parts.append(
            f"{result.products_attached} attached to products you already had"
        )
    if result.lines_already_captured:
        parts.append(f"{result.lines_already_captured} already captured")
    if result.lines_excluded:
        parts.append(f"{result.lines_excluded} skipped")
    if result.orphaned:
        # Reported, never deleted.
        parts.append(
            f"{len(result.orphaned)} recorded purchase(s) this order no longer "
            f"lists, left alone"
        )
    if result.lines_incomplete and thin_sentence is not None:
        parts.append(thin_sentence(result.lines_incomplete))
    if thin_products and result.products_created:
        parts.append(
            f"The {result.products_created} new product(s) carry only what the "
            f"order page stated — capture a listing page to fill one in"
        )
    return ". ".join(parts) + "."


def _digikey_thin_sentence(labels) -> str:
    """Named rather than counted, and all of them: a handful is the usual case."""
    return "DigiKey had no detail for " + ", ".join(labels)


def _page_thin_sentence(labels) -> str:
    """Named, but not all of them.

    DigiKey names every unenriched part because a handful is the usual case.
    Where the lines were read off a page, a selector that stops matching costs
    the same field on *every* line, and listing fifteen descriptions produces a
    flash nobody reads -- which loses the warning as surely as not showing it.
    The first few plus a count says the same thing and stays legible.
    """
    named = list(labels[:3])
    rest = len(labels) - len(named)
    thin = ", ".join(named)
    if rest:
        thin += f" and {rest} more"
    return "The page did not give up every field for " + thin


def _digikey_capture_summary(result) -> str:
    """See :func:`_order_capture_summary`. Kept by name: the tests import it."""
    return _order_capture_summary(result, _digikey_thin_sentence)


def _mcmaster_capture_summary(result) -> str:
    """See :func:`_order_capture_summary`. Kept by name: the tests import it."""
    return _order_capture_summary(result, _page_thin_sentence)


@bp.route('/products/orders')
def orders_list():
    """Every captured order, across every vendor (029 FR-033, FR-034).

    The catalog had no answer to "what is still on its way?" before this: an
    order was reachable only by typing its number or by being redirected onto it
    by a scan.

    Derived from the purchases, like every other order view here.
    """
    service = _get_catalog_service()
    orders = service.find_captured_orders()

    return render_template(
        'product/orders.html',
        title='Captured Orders',
        orders=orders,
        open_orders=[order for order in orders if not order.is_complete],
    )


@bp.route('/products/orders/<vendor>/<order_number>')
def order_detail(vendor, order_number):
    """A captured order, for any vendor (029 FR-028 to FR-032).

    Derived, never stored: the order *is* the purchases carrying its number. An
    order number nothing was captured against renders "not captured" with a way
    forward -- not a 404. Nothing dead-ends.

    ``vendor`` is the vendor's own name as it is stored on the purchase, so this
    also renders an order from a vendor no capture flow knows about --
    ``for_vendor`` returns None there rather than raising, and the page simply
    offers no "capture another" link.
    """
    service = _get_catalog_service()
    lines = service.find_order_lines_for(vendor, order_number)
    order_vendor = order_vendors.for_vendor(vendor)

    capture_url = None
    if vendor == DIGIKEY_VENDOR:
        capture_url = url_for('product.digikey_order_capture')

    receive_hint = 'Scan a part number off a bag to receive its line.'
    if order_vendor is not None:
        if order_vendor.receive_landing == order_vendors.LANDING_ORDER_SCREEN:
            receive_hint = "Scan a bag's label to receive its line."
        elif not order_vendor.carries_payload:
            receive_hint = 'Receive each line as it arrives.'
    if vendor == AMAZON_VENDOR:
        # An Amazon package names neither the order nor the line, and a product
        # created from an order line carries no barcode -- so the screen is the
        # receiving path here rather than a progress display (029 US2).
        receive_hint = 'Receive each line as its box arrives.'

    return render_template(
        'product/order.html',
        title=f'{vendor} Order {order_number}',
        vendor_name=vendor,
        order_number=order_number,
        lines=lines,
        outstanding=[line for line in lines if line.is_outstanding],
        highlight=request.args.get('highlight', ''),
        capture_url=capture_url,
        renameable=bool(order_vendor and order_vendor.adopts_renames),
        receive_hint=receive_hint,
    )


@bp.route('/products/digikey/orders/<sales_order_number>')
def digikey_order_detail(sales_order_number):
    """The address a DigiKey order lives at.

    Kept rather than removed: it is in the operator's history, and it is what
    ``_receive_url`` has been sending scans to since feature 024. 029 FR-044 --
    every order captured before this feature stays openable.

    It **renders** rather than redirecting. A redirect would be fine in a
    browser, but it would turn every existing assertion about this page into an
    assertion about a 302 -- and those suites are this feature's regression gate,
    so they are not edited to accommodate the refactor. Delegating keeps one
    implementation either way.
    """
    return order_detail(DIGIKEY_VENDOR, sales_order_number)


# -- McMaster-Carr orders ---------------------------------------------------


# The vendors whose orders are read off a page and ride /api/capture as one
# hidden JSON field. DigiKey is absent deliberately: its order is fetched by
# number and re-read at confirmation, so it has no payload and no ambiguity
# about which vendor a submission belongs to.
def _payload_vendors():
    """(OrderVendor, order type, page title) for each page-read vendor."""
    return (
        (MCMASTER_ORDER_VENDOR, McMasterOrder, 'Capture a McMaster-Carr Order'),
        (AMAZON_ORDER_VENDOR, AmazonOrder, 'Capture an Amazon Order'),
    )


def _page_order(raw):
    """Which page-read vendor's order a payload is, and the parsed order.

    Returns ``(vendor, order, title)``. ``order`` is None for a payload this
    server cannot read -- an unknown version, no order number, unparseable JSON
    -- and that is the ordinary answer rather than an error. It is what makes a
    stale cached agent harmless.

    The payload's own ``vendor`` field picks the reader, so an Amazon payload
    that is otherwise unreadable still renders Amazon's wording. When it names
    no vendor this tries each reader in turn, and when nothing matches it falls
    back to McMaster -- which is the vendor this endpoint had before Amazon
    existed, so a payload that was rendered a certain way yesterday still is.
    """
    candidates = _payload_vendors()

    if not raw:
        return candidates[0][0], None, candidates[0][2]

    try:
        body = json.loads(raw, parse_float=Decimal)
    except (TypeError, ValueError):
        logger.info('A capture payload carried an unreadable order field')
        return candidates[0][0], None, candidates[0][2]

    declared = body.get('vendor') if isinstance(body, dict) else None
    for vendor, order_type, title in candidates:
        if declared == vendor.name:
            return vendor, order_type.from_payload(body), title

    for vendor, order_type, title in candidates:
        order = order_type.from_payload(body)
        if order is not None:
            return vendor, order, title

    return candidates[0][0], None, candidates[0][2]


def _page_order_review(service, raw, form_data=None):
    """Render the review for a payload the agent just read. Writes nothing.

    A payload naming no order -- unreadable, or naming no order number --
    renders the "this page yielded no order" statement with the hand-entry way
    forward, rather than an error page.

    One implementation for every page-read vendor since feature 029.
    """
    vendor, order, title = _page_order(raw)

    if order is None:
        return render_template(
            'product/order_review.html',
            title=title,
            **_review_context(vendor, None, None, form_data, payload=raw or ''),
        )

    review = service.review_order(order, vendor)
    order_number = vendor.order_fields(order)['supplier_order_reference']
    return render_template(
        'product/order_review.html',
        title=f'{vendor.name} Order {order_number}',
        # `payload` is carried through verbatim. This is the FR-006 mechanism:
        # there is nothing to re-read at confirmation, so the payload the review
        # was built from has to survive the round trip or the capture is lost.
        **_review_context(vendor, order, review, form_data, payload=raw),
    )


def _confirm_page_order(expected_vendor, thin_sentence):
    """Confirm a reviewed order that was read off a page, and write it.

    **The payload is the authority**, and it is re-parsed here rather than
    trusted from the review's rendering. DigiKey's equivalent re-reads the order
    from DigiKey; there is nothing to re-read from a page the operator has since
    navigated away from, so what the review displayed is what this writes.

    One implementation for every page-read vendor since feature 029.
    """
    service = _get_catalog_service()
    raw = request.form.get('order') or ''
    vendor, order, _ = _page_order(raw)

    if order is None or vendor.name != expected_vendor.name:
        # Either unreadable, or posted to the wrong vendor's confirm route --
        # which a stale cached agent can do. Neither writes anything.
        return _page_order_review(service, raw, form_data=request.form)

    decisions = _order_decisions(request.form, order)

    try:
        result = service.capture_order_lines(
            order, vendor, decisions,
            arrived_date=request.form.get('arrived_date'),
        )
    except ValidationError as e:
        # Re-render the review carrying what was submitted, so a description the
        # operator spent time on is not lost.
        flash(e.message, 'error')
        return _page_order_review(service, raw, form_data=request.form)

    flash(
        _order_capture_summary(
            result, thin_sentence, thin_products=vendor.enrich is None
        ),
        'success',
    )
    return redirect(_order_url(
        vendor.name, vendor.order_fields(order)['supplier_order_reference']
    ))


@bp.route('/products/mcmaster/orders/capture', methods=['POST'])
def mcmaster_order_confirm():
    """Confirm a reviewed McMaster order. See :func:`_confirm_page_order`.

    Same-origin, so CSRF-protected like every other form in the application --
    unlike ``/api/capture``, which posts from the vendor's origin and cannot be.
    """
    return _confirm_page_order(MCMASTER_ORDER_VENDOR, _page_thin_sentence)


@bp.route('/products/amazon/orders/capture', methods=['POST'])
def amazon_order_confirm():
    """Confirm a reviewed Amazon order (029 FR-035). See :func:`_confirm_page_order`.

    Same-origin, so CSRF-protected, for the same reason McMaster's is.
    """
    return _confirm_page_order(AMAZON_ORDER_VENDOR, _page_thin_sentence)


@bp.route('/products/purchases/receive-choice')
def purchase_receive_choice():
    """Which outstanding line did this bag come from? (FR-032a)

    Reached when a scanned McMaster part number names more than one outstanding
    line. **The catalog does not pick one**, and it cannot: the same part can be
    outstanding on two orders placed weeks apart, and nothing about the bag says
    which.

    Its own page rather than DigiKey's answer, because DigiKey's candidates are
    two lines of *one* order and the order screen shows them both. McMaster's
    are not, and no single order screen shows them (research.md §11). DigiKey's
    path is left exactly as it was -- this is an additional landing, not a
    replacement.

    Zero candidates by the time it loads -- received in another tab -- renders
    "nothing outstanding for this part" and offers the product. Never an empty
    list, and never a 404.
    """
    service = _get_catalog_service()
    scan = (request.args.get('scan') or '').strip()
    candidates = service.find_mcmaster_receivable(scan)

    product = None
    if not candidates and scan:
        for id_type in VENDOR_SCOPED_TYPES:
            product = service.find_product_by_identifier(
                scan, id_type=id_type.value, vendor=MCMASTER_VENDOR
            )
            if product is not None:
                break

    return render_template(
        'product/receive_choice.html',
        title='Which Line Did This Come From?',
        scan=scan,
        candidates=candidates,
        product=product,
    )


@bp.route('/products/mcmaster/orders/<order_number>')
def mcmaster_order_detail(order_number):
    """The address a McMaster order lives at. See :func:`digikey_order_detail`."""
    return order_detail(MCMASTER_VENDOR, order_number)


@bp.route('/products/digikey/part', methods=['GET', 'POST'])
def digikey_part_capture():
    """Catalog one DigiKey part on its own (FR-027).

    Accepts a DigiKey part number, a manufacturer part number, or a DigiKey
    product-page address. **Writes nothing**: it renders a review whose form
    posts to the ordinary product-create route, so there is one place products
    are created rather than two.
    """
    client = _get_digikey_client()

    if request.method == 'GET':
        return render_template(
            'product/digikey_part_review.html',
            title='Capture a DigiKey Part',
            part=None,
            existing=None,
            part_number=request.args.get('part_number', ''),
            problem=None if client is not None else 'not_configured',
            message=None,
        )

    entered = (request.form.get('part_number') or '').strip()
    part_number = _digikey_part_from_url(entered)

    def _refuse(problem, message=None):
        return render_template(
            'product/digikey_part_review.html',
            title='Capture a DigiKey Part',
            part=None,
            existing=None,
            part_number=entered,
            problem=problem,
            message=message,
        )

    if not part_number:
        return _refuse('blank', 'Enter a DigiKey part number, a manufacturer '
                                'part number, or a DigiKey product page address.')
    if client is None:
        return _refuse('not_configured')

    try:
        part = client.get_part(part_number)
    except WorkshopInventoryError as e:
        # FR-032: say so plainly and offer the ordinary form carrying what they
        # typed. Never an error page, never a silent empty draft.
        return _refuse(_digikey_problem(e), e.message)

    # FR-031: if the catalog already holds it, name that product rather than
    # inviting a second one.
    service = _get_catalog_service()
    existing = service.find_product_by_identifier(
        part.manufacturer_part_number, id_type=IdentifierType.MPN.value
    ) or service.find_product_by_identifier(
        part.digikey_part_number or part_number,
        id_type=IdentifierType.DISTRIBUTOR.value,
        vendor=DIGIKEY_VENDOR,
    )

    return render_template(
        'product/digikey_part_review.html',
        title=f'Capture {part.manufacturer_part_number or part_number}',
        part=part,
        existing=existing,
        part_number=part_number,
        problem=None,
        message=None,
    )


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
    """Search and filter the catalog (FR-032)."""
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
    if resolution.outcome == 'receive':
        payload['url'] = _receive_url(resolution)
    elif resolution.outcome == 'product':
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


def _order_url(vendor, order_number, highlight=''):
    """The address a captured order lives at.

    DigiKey keeps its original address. Scans have landed there since feature
    024, it is in the operator's history, and 029 FR-041 says every existing
    path behaves exactly as it did. Everything else uses the converged one.

    **Both render the same view**, so this is about which address is shown and
    nothing else -- it is deliberately not a branch in the capture flow, which
    FR-036 keeps vendor-neutral.
    """
    if vendor == DIGIKEY_VENDOR:
        return url_for(
            'product.digikey_order_detail',
            sales_order_number=order_number,
            highlight=highlight,
        )
    return url_for(
        'product.order_detail',
        vendor=vendor,
        order_number=order_number,
        highlight=highlight,
    )


def _receive_url(resolution) -> str:
    """Where a scanned package should land.

    **One rule, every vendor** (029 FR-038 to FR-040). Three cases, and the
    difference between them is what the operator needs to be told:

    * **one outstanding line** -- straight to its receipt, with the label's own
      quantity pre-filled where the label carried one, because the label
      describes what is in the package rather than what was ordered;
    * **several** -- the operator chooses. The catalog does not pick one;
    * **none outstanding but some received** -- said plainly. Nothing is
      received twice.

    Which screen "the operator chooses" means is the vendor's one contribution,
    and it follows from what the package names. A DigiKey bag label names its
    sales order *and* its part, so every candidate is a line of one order and
    that order's screen shows them all -- ``LANDING_ORDER_SCREEN``. A McMaster
    bag names only the part, and the same part can be outstanding on two orders
    placed weeks apart, so no single order screen shows the candidates and the
    choice page does -- ``LANDING_CHOICE_PAGE``. Amazon is the choice page too,
    for a different reason: a package names neither, so a scan only ever reaches
    a line by the product's own barcode.

    **The vendor and the order number come off the matched purchases, not off
    the scan.** They used to be read from ``classification.ecia_fields``, which a
    distributor label populates and a **free-text scan leaves empty** -- so a
    McMaster match would have built an order URL with a blank order number. The
    purchases carry both either way, and they are the record rather than the
    scan.

    ``app/static/js/scan-capture.js`` navigates to whatever this returns without
    inspecting the outcome, so it needs no change.
    """
    purchases = resolution.purchases
    outstanding = [purchase for purchase in purchases if purchase.is_outstanding]
    fields = resolution.classification.ecia_fields

    # Off the purchases. A free-text scan has no ecia_fields at all.
    matched = outstanding or purchases
    vendor = matched[0].vendor if matched else ''
    order_number = matched[0].supplier_order_reference if matched else ''

    if len(outstanding) == 1:
        params = {'purchase_id': outstanding[0].id}
        if fields.get('Q'):
            # Uncoerced, as every value off a distributor label is: a cut-tape
            # quantity may be a length, and the field stays editable either way.
            params['quantity'] = fields['Q']
        return url_for('product.purchase_receive', **params)

    landing = order_vendors.for_vendor(vendor)
    if landing is not None and landing.receive_landing == order_vendors.LANDING_CHOICE_PAGE:
        return url_for(
            'product.purchase_receive_choice', scan=resolution.classification.value
        )

    if not outstanding:
        flash(
            f"That line of {vendor} order {order_number} is already received.",
            'info',
        )

    return _order_url(vendor, order_number, fields.get('P', ''))


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
