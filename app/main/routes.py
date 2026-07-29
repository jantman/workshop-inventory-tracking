from flask import render_template, current_app, jsonify, abort, request, flash, redirect, url_for, send_file
from datetime import datetime, date
from typing import Any
from app.main import bp
from app import csrf
# DW-32: one connected storage -- and therefore one engine and one pool -- per
# Flask app. `app/db.py` owns that lifetime; routes never build engines.
from app.db import get_storage_backend as _resolve_storage_backend, resolve_engine
# Using unified InventoryService (MariaDB-based implementation)
from app.mariadb_inventory_service import InventoryService
from app.mariadb_catalog_service import (
    CatalogService,
    FIELD_SUGGESTION_COLUMNS as CATALOG_FIELD_SUGGESTION_COLUMNS,
)
# Performance optimizations removed - no longer needed with MariaDB
from app.taxonomy import type_shape_validator
from app.models import (ItemType, ItemShape, Dimensions, Thread, ThreadSeries,
                        ThreadHandedness, IdentifierType, ScanKind, StockStatus,
                        VENDOR_SCOPED_IDENTIFIER_TYPES)
from app.database import InventoryItem
# Story 3.2: routes call the pure category util for segment-boundary logic —
# they never re-derive it (AD-4).
from app.utils import category as category_util
# Story 4.5: the route needs ONE pure-util call from the classifier module —
# `strip_aim_prefix`, for the create-form `description` pre-fill and the
# `internal` banner, so a scan is never lost (FR40). It is no longer used to
# re-derive the text a fallthrough search ran on: `scan_search_text` on the
# service owns that rule. That is a util call, not classification (AD-4/AD-5):
# the route never calls classify() and never decides a kind.
from app.utils import scan_router
# Story 4.1 (FR35): the scan payload rule — what a captured scan is trimmed of
# and how long it may be — lives in a pure util the route CONSUMES. It is not
# the route's rule: the classifier's contract depends on it and the catalog
# service inherits it. scan-capture.js mirrors the TRIM SET only; the length
# bound is server-side on purpose, so an over-length paste gets a visible
# refusal rather than a silent client-side truncation (AD-4).
from app.utils.scan_input import MAX_SCAN_LENGTH, clean_scan_input
# Story 3.3: same rule for tags — the canonical form and the comma-separated
# list are the pure util's business, never re-derived here (AD-4).
from app.utils import tag as tag_util
# DW-23: same rule again for GTINs. The create form judges a scanned GTIN
# before it writes, and it does so by CALLING this module — the sole owner of
# GTIN validity, the mod-10 check digit and the canonical 14-digit key. The
# route derives none of that itself; it only catches `InvalidGtinError` and
# renders the message the util wrote (AD-4).
from app.utils import gtin
# Story 5.1: the two pure utils this story needs. `describe_age` turns a
# verification stamp into the phrase the product page shows beside the count
# (FR25) — the route computes it and the template renders it (AD-5).
# `merge_suggestions` re-ranks the item-sourced and product-sourced location
# lists into the one answer the shared suggestion endpoint returns (FR27); the
# merge is a pure function precisely so neither service has to query the other's
# table (AD-1/AD-2).
from app.utils.age_display import describe_age
from app.utils.suggestion_merge import merge_suggestions
from app.error_handlers import with_error_handling, ErrorHandler
from app.exceptions import ValidationError, StorageError, ItemNotFoundError
from app.logging_config import log_audit_operation, log_audit_batch_operation
from decimal import Decimal, InvalidOperation
# Story 4.5: `_bounded_scan_url` ranks its shrink candidates by what each one
# actually costs the URL — its encoded length under the rules werkzeug builds
# query strings with — not by how many characters it holds. See
# `_URL_QUERY_SAFE` for why the two are not the same thing.
from urllib.parse import quote_plus
import traceback
from config import Config

def _get_storage_backend():
    """Get the appropriate storage backend for the current app context

    Delegates to ``app.db``, which owns the single app-scoped connected
    ``MariaDBStorage`` (and therefore the single engine/pool) used in
    production. An injected ``STORAGE_BACKEND`` still wins.
    """
    return _resolve_storage_backend()

def _item_to_audit_dict(item):
    """Convert InventoryItem object to dictionary for audit logging"""
    if not item:
        return None
    return {
        'ja_id': item.ja_id,
        'item_type': item.item_type if item.item_type else None,  # InventoryItem stores as string
        'shape': item.shape if item.shape else None,  # InventoryItem stores as string
        'material': item.material,
        'dimensions': item.dimensions.to_dict() if item.dimensions else None,
        'thread': item.thread.to_dict() if item.thread else None,
        'location': item.location,
        'sub_location': item.sub_location,
        'purchase_date': item.purchase_date.isoformat() if item.purchase_date else None,
        'purchase_price': str(item.purchase_price) if item.purchase_price else None,
        'purchase_location': item.purchase_location,
        'notes': item.notes,
        'vendor': item.vendor,
        'vendor_part': item.vendor_part,
        'original_material': item.original_material,
        'original_thread': item.original_thread,
        'precision': item.precision,
        'active': item.active,
        'date_added': item.date_added.isoformat() if item.date_added else None,
        'last_modified': item.last_modified.isoformat() if item.last_modified else None
    }

def _detect_item_changes(item_before, item_after):
    """Detect changes between two Item objects for audit logging"""
    if not item_before or not item_after:
        return {}
    
    before_dict = _item_to_audit_dict(item_before)
    after_dict = _item_to_audit_dict(item_after)
    
    changes = {}
    for key, after_value in after_dict.items():
        before_value = before_dict.get(key)
        if before_value != after_value:
            changes[key] = {'before': before_value, 'after': after_value}
    
    return changes

def _get_inventory_service():
    """Get the MariaDB inventory service (only supported backend)"""
    storage = _get_storage_backend()

    # All storage now uses MariaDB backend
    return InventoryService(storage)

def _get_catalog_service():
    """Get the MariaDB catalog service (Products, Purchases, etc.)"""
    return CatalogService(_get_storage_backend())

def _get_photo_info(ja_id):
    """Get photo information for an item"""
    try:
        from app.photo_service import PhotoService
        with PhotoService(_get_storage_backend()) as photo_service:
            photos = photo_service.get_photos(ja_id)
            
            return {
                'count': len(photos),
                'photos': [photo.to_dict() for photo in photos]
            }
    except Exception as e:
        current_app.logger.error(f'Error getting photo info for {ja_id}: {e}')
        return {'count': 0, 'photos': []}

@bp.route('/')
@bp.route('/index')
def index():
    """Home page with application overview"""
    return render_template('index.html', title='Home')

@bp.route('/health')
def health():
    """Health check endpoint for monitoring"""
    return {'status': 'healthy', 'service': 'workshop-inventory-tracking'}

@bp.route('/inventory')
def inventory_list():
    """Inventory list view"""
    return render_template('inventory/list.html', title='Inventory', ItemType=ItemType)

def _get_valid_materials():
    """Get list of valid materials from the appropriate storage backend"""
    try:
        storage = _get_storage_backend()

        # All storage now uses MariaDB backend

        # For MariaDB, use the inventory service
        from app.mariadb_inventory_service import InventoryService
        service = InventoryService(storage)
        return service.get_valid_materials()

    except Exception as e:
        current_app.logger.error(f'Failed to load materials taxonomy: {e}')
        # Fallback to some basic materials if database query fails
        return ['Steel', 'Carbon Steel', 'Stainless Steel', 'Aluminum', 'Brass', 'Copper']


def _add_item_with_logging(service, item, operation='add_item', context=None):
    """
    Helper function to add an item and log the operation.

    Args:
        service: InventoryService instance
        item: InventoryItem object to add
        operation: Operation name for audit logging (default: 'add_item')
        context: Optional dict with logging context (e.g., bulk_context, duplicate_context)

    Returns:
        Tuple of (success: bool, ja_id: str, error_message: str or None)
    """
    try:
        result = service.add_item(item)

        if result:
            # AUDIT: Log successful operation
            log_audit_operation(operation, 'success',
                              item_id=item.ja_id,
                              item_after=_item_to_audit_dict(item),
                              form_data=context if context else None)

            return (True, item.ja_id, None)
        else:
            error_msg = 'Service add_item returned False'

            log_audit_operation(operation, 'error',
                              item_id=item.ja_id,
                              error_details=error_msg,
                              form_data=context if context else None)

            return (False, item.ja_id, error_msg)

    except Exception as e:
        error_msg = str(e)
        current_app.logger.error(f'Error adding item {item.ja_id}: {error_msg}')
        log_audit_operation(operation, 'error',
                          item_id=item.ja_id,
                          error_details=error_msg,
                          form_data=context if context else None)
        return (False, item.ja_id, error_msg)


def _create_single_item(
    service,
    form_data: dict,
    bulk_context: dict | None = None,
) -> tuple[bool, str | None, str | None, str | None]:
    """Parse, persist, and log a single add-item submission.

    Returns ``(success, ja_id, error_message, error_kind)`` where
    ``error_kind`` distinguishes user-input parse failures (the string
    ``'validation_error'``) from backend persistence failures (the
    string ``'error'``). It is ``None`` on success. Callers map
    ``error_kind`` onto an HTTP status — parse failures should surface
    as 400, persistence failures as 500.
    """
    try:
        item = _parse_item_from_form(form_data)
    except (ValueError, InvalidOperation) as e:
        error_msg = str(e)
        current_app.logger.error(f'Validation error parsing item: {error_msg}')
        return (False, form_data.get('ja_id'), error_msg, 'validation_error')
    except Exception as e:
        # Unexpected parse-stage failure (not user input). Treat as a
        # backend error rather than user-facing validation.
        error_msg = str(e)
        current_app.logger.error(f'Unexpected error parsing item: {error_msg}')
        return (False, form_data.get('ja_id'), error_msg, 'error')

    context = None
    if bulk_context:
        context = {
            'bulk_creation': True,
            'bulk_index': bulk_context['index'],
            'bulk_total': bulk_context['total'],
        }

    try:
        success, ja_id, error_msg = _add_item_with_logging(service, item, 'add_item', context)
    except Exception as e:
        error_msg = str(e)
        current_app.logger.error(f'Error persisting item: {error_msg}')
        return (False, form_data.get('ja_id'), error_msg, 'error')

    return (success, ja_id, error_msg, None if success else 'error')


def _process_item_creation(input_data: dict) -> dict[str, Any]:
    """Run validation, parsing, and persistence for an add-item
    submission, including bulk creation when ``quantity_to_create > 1``.
    Audit logging is performed inside.

    Args:
        input_data: form-style dict (string keys/values) such as
            ``request.form.to_dict()``. JSON callers should normalize
            their payload via ``_normalize_json_item_payload`` first.

    Returns:
        dict with keys:
            ``status`` - one of ``'ok'``, ``'partial'``,
                ``'validation_error'``, ``'error'``.
            ``created_ja_ids`` - list of successfully-created JA IDs.
            ``errors`` - list of ``{'index', 'ja_id', 'message'}``
                dicts. Indices are 1-based, matching the natural
                "Nth attempted item" phrasing.
            ``message`` - human-readable summary.
            ``requested_quantity`` - quantity the caller asked for
                (0 if validation failed before that field could be
                parsed).
    """
    log_audit_operation('add_item', 'input',
                        item_id=input_data.get('ja_id'),
                        form_data=input_data)

    def _validation_error(msg: str, requested_quantity: int = 0) -> dict[str, Any]:
        log_audit_operation('add_item', 'error',
                            item_id=input_data.get('ja_id'),
                            error_details=msg)
        return {
            'status': 'validation_error',
            'created_ja_ids': [],
            'errors': [{'index': 0, 'ja_id': input_data.get('ja_id'), 'message': msg}],
            'message': msg,
            'requested_quantity': requested_quantity,
        }

    required_fields = ['ja_id', 'item_type', 'shape', 'material', 'location']
    missing_fields = [field for field in required_fields if not input_data.get(field)]
    if missing_fields:
        return _validation_error(f'Missing required fields: {", ".join(missing_fields)}')

    material = input_data.get('material', '').strip()
    valid_materials = _get_valid_materials()
    valid_materials_lower = [m.lower() for m in (valid_materials or []) if m]
    if material and valid_materials_lower and material.lower() not in valid_materials_lower:
        return _validation_error(
            f'Material "{material}" is not valid. Please select from materials taxonomy.'
        )

    try:
        quantity_to_create = int(input_data.get('quantity_to_create', '1'))
    except (TypeError, ValueError):
        return _validation_error('Quantity to create must be a valid integer')

    current_app.logger.info(f'Add item: quantity_to_create={quantity_to_create} from input_data')

    if quantity_to_create < 1 or quantity_to_create > 100:
        return _validation_error(
            'Quantity to create must be between 1 and 100',
            requested_quantity=quantity_to_create,
        )

    service = _get_inventory_service()

    if quantity_to_create == 1:
        success, ja_id, error_msg, error_kind = _create_single_item(service, input_data)
        if success:
            return {
                'status': 'ok',
                'created_ja_ids': [ja_id],
                'errors': [],
                'message': 'Item added successfully',
                'requested_quantity': 1,
            }
        # Parse-time failures (invalid dimensions, etc.) are user input
        # validation errors and surface as 400, not 500.
        status = 'validation_error' if error_kind == 'validation_error' else 'error'
        return {
            'status': status,
            'created_ja_ids': [],
            'errors': [{'index': 0, 'ja_id': ja_id, 'message': error_msg or 'Failed to add item'}],
            'message': error_msg or 'Failed to add item',
            'requested_quantity': 1,
        }

    current_app.logger.info(
        f'Bulk creation: Creating {quantity_to_create} items starting from {input_data.get("ja_id")}'
    )

    next_number = service.get_max_ja_id_number() + 1

    starting_ja_id = input_data.get('ja_id', '').strip()
    if starting_ja_id and starting_ja_id.startswith('JA'):
        try:
            next_number = max(next_number, int(starting_ja_id[2:]))
        except ValueError:
            pass

    created_ja_ids: list[str] = []
    errors: list[dict[str, Any]] = []
    error_kinds: list[str] = []

    for i in range(quantity_to_create):
        ja_id = f"JA{next_number:06d}"
        next_number += 1
        position = i + 1

        item_input = dict(input_data)
        item_input['ja_id'] = ja_id

        bulk_context = {'index': position, 'total': quantity_to_create}
        success, created_ja_id, error_msg, error_kind = _create_single_item(
            service, item_input, bulk_context
        )

        if success:
            created_ja_ids.append(created_ja_id)
        else:
            current_app.logger.error(
                f'Failed to create item {position}/{quantity_to_create}: {ja_id} - {error_msg}'
            )
            errors.append({'index': position, 'ja_id': ja_id, 'message': error_msg or 'Unknown error'})
            error_kinds.append(error_kind or 'error')

    if len(created_ja_ids) == quantity_to_create:
        first_ja_id = created_ja_ids[0]
        last_ja_id = created_ja_ids[-1]
        current_app.logger.info(
            f'Bulk creation complete: Created {len(created_ja_ids)} items ({first_ja_id} - {last_ja_id})'
        )
        return {
            'status': 'ok',
            'created_ja_ids': created_ja_ids,
            'errors': [],
            'message': f'Successfully created {len(created_ja_ids)} items: {first_ja_id} - {last_ja_id}',
            'requested_quantity': quantity_to_create,
        }

    if created_ja_ids:
        msg = f'Created {len(created_ja_ids)} of {quantity_to_create} items. Some items failed.'
        log_audit_operation('add_item', 'error',
                            error_details=msg,
                            form_data={
                                'bulk_creation': True,
                                'bulk_total': quantity_to_create,
                                'bulk_succeeded': len(created_ja_ids),
                            })
        return {
            'status': 'partial',
            'created_ja_ids': created_ja_ids,
            'errors': errors,
            'message': msg,
            'requested_quantity': quantity_to_create,
        }

    msg = 'Failed to create any items'
    log_audit_operation('add_item', 'error',
                        error_details=msg,
                        form_data={
                            'bulk_creation': True,
                            'bulk_total': quantity_to_create,
                        })
    # If every failure was a parse-time validation problem, surface the
    # whole request as a 400 rather than 500 — bulk requests share input
    # data, so a parse failure on the first item is a request-level
    # validation problem.
    status = 'validation_error' if error_kinds and all(k == 'validation_error' for k in error_kinds) else 'error'
    return {
        'status': status,
        'created_ja_ids': [],
        'errors': errors or [{'index': 0, 'ja_id': None, 'message': msg}],
        'message': msg,
        'requested_quantity': quantity_to_create,
    }


_JSON_ITEM_FIELDS = frozenset({
    'item_type', 'shape', 'material',
    'length', 'width', 'thickness', 'wall_thickness', 'weight',
    'thread_series', 'thread_handedness', 'thread_size',
    'location', 'sub_location',
    'purchase_date', 'purchase_price', 'purchase_location',
    'vendor', 'vendor_part_number', 'notes',
    'active', 'precision',
    'quantity_to_create',
})
# Note: 'ja_id' is intentionally NOT accepted from JSON callers. The
# server always allocates the next free JA ID server-side, removing
# the round-trip a client would otherwise have to make to learn the
# next-free ID and the race that would imply.

_JSON_BOOLEAN_FIELDS = frozenset({'active', 'precision'})


def _normalize_json_item_payload(json_body: Any) -> dict[str, str]:
    """Convert a JSON request body into the form-style dict that
    ``_process_item_creation`` and ``_parse_item_from_form`` expect.

    Native booleans for ``active`` / ``precision`` are mapped to the
    HTML checkbox semantics used by the form parser ("on" when true,
    omitted when false). Numbers are coerced to strings for dimension
    parsing. Unknown top-level keys raise ``ValueError`` so typos
    surface as a 400 instead of being silently ignored. String inputs
    on boolean fields are rejected outright: the form parser only
    treats the literal ``"on"`` as truthy, so accepting unrestricted
    strings here would silently misinterpret values like ``"true"``
    or ``"yes"`` as false. JSON callers must send native booleans.
    """
    if not isinstance(json_body, dict):
        raise ValueError('Request body must be a JSON object')

    unknown = set(json_body.keys()) - _JSON_ITEM_FIELDS
    if unknown:
        raise ValueError(f'Unknown field(s): {", ".join(sorted(unknown))}')

    normalized = {}
    for key, value in json_body.items():
        if value is None:
            continue
        if key in _JSON_BOOLEAN_FIELDS:
            # Reject anything but a JSON boolean. Strings like "true" or
            # "yes" would otherwise be silently interpreted as false by
            # the form parser, which only recognizes the literal "on".
            # ``isinstance(value, bool)`` correctly excludes plain ints
            # (since 1/0 are not bool instances even though bool is an
            # int subclass).
            if isinstance(value, bool):
                if value:
                    normalized[key] = 'on'
                continue
            raise ValueError(
                f'Field "{key}" must be a JSON boolean (true or false)'
            )
        normalized[key] = str(value)

    return normalized


@bp.route('/api/inventory/items', methods=['POST'])
@csrf.exempt
def api_create_items() -> Any:
    """JSON API to create one or more inventory items.

    Returns 200 on full success, 207 on partial success, 400 on
    request-level validation errors, and 500 on unexpected failures.
    The response body always contains ``created_ja_ids`` and
    ``errors`` lists so callers can rely on a consistent shape.
    """
    json_body = request.get_json(silent=True)
    if json_body is None:
        msg = 'Request body must be a JSON object'
        return jsonify({
            'success': False,
            'created_ja_ids': [],
            'errors': [{'index': 0, 'ja_id': None, 'message': msg}],
            'error': msg,
        }), 400

    try:
        normalized = _normalize_json_item_payload(json_body)
    except ValueError as e:
        msg = str(e)
        return jsonify({
            'success': False,
            'created_ja_ids': [],
            'errors': [{'index': 0, 'ja_id': None, 'message': msg}],
            'error': msg,
        }), 400

    # The server always allocates JA IDs for JSON callers. The shared
    # helper expects ja_id to be present in input_data (it's required
    # by the form path and used by _parse_item_from_form), so we
    # allocate the next free ID and inject it before delegating. For
    # bulk requests, the helper's own loop allocates each per-item ID;
    # the value we set here becomes the floor for that loop, which
    # equals what the loop would have computed itself.
    try:
        service = _get_inventory_service()
        next_number = service.get_max_ja_id_number() + 1
        normalized['ja_id'] = f'JA{next_number:06d}'
    except Exception as e:
        current_app.logger.error(
            f'Failed to allocate JA ID for API request: {e}\n{traceback.format_exc()}'
        )
        return jsonify({
            'success': False,
            'created_ja_ids': [],
            'errors': [{'index': 0, 'ja_id': None, 'message': str(e)}],
            'error': f'Failed to allocate JA ID: {str(e)}',
        }), 500

    try:
        result = _process_item_creation(normalized)
    except Exception as e:
        current_app.logger.error(
            f'Unexpected error in API item creation: {e}\n{traceback.format_exc()}'
        )
        return jsonify({
            'success': False,
            'created_ja_ids': [],
            'errors': [{'index': 0, 'ja_id': normalized.get('ja_id'), 'message': str(e)}],
            'error': f'Unexpected error: {str(e)}',
        }), 500

    status_to_code = {
        'ok': 200,
        'partial': 207,
        'validation_error': 400,
        'error': 500,
    }
    http_status = status_to_code[result['status']]

    response = {
        'success': result['status'] == 'ok',
        'created_ja_ids': result['created_ja_ids'],
        'errors': result['errors'],
    }
    if result.get('message'):
        response['message'] = result['message']
    if result['status'] != 'ok':
        response['error'] = result['message']

    return jsonify(response), http_status


@bp.route('/inventory/add', methods=['GET', 'POST'])
def inventory_add():
    """Add new inventory item"""
    if request.method == 'GET':
        # Log add form access for carry forward debugging
        referer = request.headers.get('Referer', 'unknown')
        current_app.logger.info(f'Add form accessed: referer="{referer}" (for carry forward workflow debugging)')
        
        valid_materials = _get_valid_materials()
        return render_template('inventory/add.html', title='Add Item',
                             ItemType=ItemType, ItemShape=ItemShape, ThreadSeries=ThreadSeries,
                             valid_materials=valid_materials)
    
    # Handle POST request for adding item
    try:
        form_data = request.form.to_dict()

        result = _process_item_creation(form_data)

        if result['status'] == 'validation_error':
            return jsonify({
                'success': False,
                'error': result['message'],
            }), 400

        quantity = result['requested_quantity']

        if quantity > 1:
            if result['status'] == 'ok':
                return jsonify({
                    'success': True,
                    'count': len(result['created_ja_ids']),
                    'ja_ids': result['created_ja_ids'],
                    'message': result['message'],
                }), 200
            if result['status'] == 'partial':
                return jsonify({
                    'success': False,
                    'count': len(result['created_ja_ids']),
                    'ja_ids': result['created_ja_ids'],
                    'error': result['message'],
                }), 500
            return jsonify({
                'success': False,
                'error': result['message'],
            }), 500

        if result['status'] == 'ok':
            ja_id = result['created_ja_ids'][0]
            flash('Item added successfully!', 'success')

            submit_type = request.form.get('submit_type')
            current_app.logger.info(f'Add item workflow: submit_type="{submit_type}" for item {ja_id}')

            if submit_type == 'continue':
                current_app.logger.info(f'Add & Continue: Redirecting to add form after successfully adding item {ja_id}')
                log_audit_operation('add_item', 'continue_workflow', item_id=ja_id)
                return redirect(url_for('main.inventory_add'))
            current_app.logger.info(f'Normal Add: Redirecting to inventory list after adding item {ja_id}')
            return redirect(url_for('main.inventory_list'))

        flash('Failed to add item. Please try again.', 'error')
        return redirect(url_for('main.inventory_add'))

    except ValueError as e:
        # AUDIT: Log validation exception
        log_audit_operation('add_item', 'error', 
                          item_id=form_data.get('ja_id') if 'form_data' in locals() else None, 
                          error_details=f'Validation error: {str(e)}')
        current_app.logger.error(f'Validation error adding item: {e}')
        flash(f'Validation error: {str(e)}', 'error')
        return redirect(url_for('main.inventory_add'))
    except Exception as e:
        # AUDIT: Log general exception
        log_audit_operation('add_item', 'error', 
                          item_id=form_data.get('ja_id') if 'form_data' in locals() else None, 
                          error_details=f'Exception: {str(e)}')
        current_app.logger.error(f'Error adding item: {e}\n{traceback.format_exc()}')
        flash('An error occurred while adding the item. Please try again.', 'error')
        return redirect(url_for('main.inventory_add'))

@bp.route('/inventory/edit/<ja_id>', methods=['GET', 'POST'])
def inventory_edit(ja_id):
    """Edit inventory item"""
    try:
        service = _get_inventory_service()

        # Get the item (active or inactive)
        item = service.get_canonical_item(ja_id)
        if not item:
            flash(f'Item {ja_id} not found.', 'error')
            return redirect(url_for('main.inventory_list'))
        
        if request.method == 'GET':
            # Populate form with existing item data
            valid_materials = _get_valid_materials()
            return render_template('inventory/edit.html', title=f'Edit {ja_id}',
                                 item=item, ItemType=ItemType, ItemShape=ItemShape, ThreadSeries=ThreadSeries,
                                 valid_materials=valid_materials, validation_errors={})
        
        # Handle POST request for updating item
        form_data = request.form.to_dict()
        
        # AUDIT: Log input phase with original item and form data
        log_audit_operation('edit_item', 'input', 
                          item_id=ja_id, 
                          form_data=form_data,
                          item_before=_item_to_audit_dict(item))
        
        # Validate required fields
        required_fields = ['ja_id', 'item_type', 'shape', 'material', 'location']
        missing_fields = [field for field in required_fields if not form_data.get(field)]
        
        if missing_fields:
            error_msg = f'Missing required fields: {", ".join(missing_fields)}'
            # AUDIT: Log validation error
            log_audit_operation('edit_item', 'error', 
                              item_id=ja_id, 
                              error_details=error_msg)
            flash(error_msg, 'error')
            return redirect(url_for('main.inventory_edit', ja_id=ja_id))
        
        # Validate material is in taxonomy
        material = form_data.get('material', '').strip()
        valid_materials = _get_valid_materials()
        # Defensive: handle case where valid_materials might be None or contain None values
        valid_materials_lower = [m.lower() for m in (valid_materials or []) if m]

        if material and valid_materials_lower and material.lower() not in valid_materials_lower:
            error_msg = f'Material "{material}" is not valid. Please select from materials taxonomy.'
            # AUDIT: Log validation error
            log_audit_operation('edit_item', 'error',
                              item_id=ja_id,
                              error_details=error_msg)
            flash(error_msg, 'error')

            # Create a temporary item with the submitted form data to preserve user input
            temp_item = _parse_item_from_form(form_data)
            temp_item.date_added = item.date_added  # Preserve original dates

            # Re-render the form with validation errors and user input
            return render_template('inventory/edit.html', title=f'Edit {ja_id}',
                                 item=temp_item, ItemType=ItemType, ItemShape=ItemShape,
                                 ThreadSeries=ThreadSeries, valid_materials=valid_materials,
                                 validation_errors={'material': error_msg})
        
        # Parse form data into updated item
        updated_item = _parse_item_from_form(form_data)
        
        # Update the item (preserve dates from original)
        updated_item.date_added = item.date_added
        updated_item.last_modified = datetime.now()
        result = service.update_item(updated_item)
        
        if result:
            # AUDIT: Log successful edit operation with changes
            changes = _detect_item_changes(item, updated_item)
            log_audit_operation('edit_item', 'success', 
                              item_id=ja_id,
                              item_before=_item_to_audit_dict(item),
                              item_after=_item_to_audit_dict(updated_item),
                              changes=changes)
            flash('Item updated successfully!', 'success')
            return redirect(url_for('main.inventory_list'))
        else:
            # AUDIT: Log failed edit operation
            log_audit_operation('edit_item', 'error', 
                              item_id=ja_id, 
                              error_details='Service update_item returned False')
            flash('Failed to update item. Please try again.', 'error')
            return redirect(url_for('main.inventory_edit', ja_id=ja_id))
            
    except ValueError as e:
        # AUDIT: Log validation exception
        log_audit_operation('edit_item', 'error', 
                          item_id=ja_id, 
                          error_details=f'Validation error: {str(e)}')
        current_app.logger.error(f'Validation error updating item {ja_id}: {e}')
        flash(f'Validation error: {str(e)}', 'error')
        return redirect(url_for('main.inventory_edit', ja_id=ja_id))
    except Exception as e:
        # AUDIT: Log general exception
        log_audit_operation('edit_item', 'error', 
                          item_id=ja_id, 
                          error_details=f'Exception: {str(e)}')
        current_app.logger.error(f'Error updating item {ja_id}: {e}\n{traceback.format_exc()}')
        flash('An error occurred while updating the item. Please try again.', 'error')
        return redirect(url_for('main.inventory_list'))

# ---------------------------------------------------------------------------
# Product catalog pages (Story 1.3). Browser HTML forms — CSRF-protected,
# flash + redirect. Business logic lives in CatalogService (AD-2). Detail is
# keyed on the integer PK; internal_id-keyed URLs arrive in Epic 8.
# ---------------------------------------------------------------------------

# The Product columns whose limit is on the value AS SUBMITTED — not every
# bounded Product column (app/database.py).
# `category_path` is deliberately NOT a row here. Its column is measured against
# the NORMALIZED path, and normalization is not always a shortening — `'İ'.lower()`
# is two characters — so a raw-length row would be a second, differently-shaped
# rule for the same column. `_validate_product_form` asks app/utils/category.py
# instead, which owns that limit.
_PRODUCT_FIELD_LIMITS = {
    'description': ('Label Description', 255),
    'manufacturer': ('Manufacturer', 255),
    'mpn': ('MPN', 255),
    # Story 5.1 (FR27). Both columns are VARCHAR(100), the same width as their
    # inventory_items namesakes — the two tables feed one vocabulary, so a
    # value one side accepted and the other could not hold would be a
    # suggestion that cannot be taken.
    'location': ('Location', 100),
    'sub_location': ('Sub-Location', 100),
}

# Story 4.5: the create form's optional "first receipt" block writes a Purchase,
# not a Product, so its limits mirror the Purchase columns (app/database.py)
# rather than the Product ones above. Kept as a separate mapping so the two
# tables' constraints are not conflated in one dict.
_RECEIPT_FIELD_LIMITS = {
    'vendor': ('Vendor', 255),
    'vendor_sku': ('Vendor SKU', 255),
    'order_number': ('Order Number', 255),
}

# `product_identifiers.value` is VARCHAR(255) (app/database.py). Checked on the
# form because `add_identifier` runs AFTER `create_product` has committed and is
# non-fatal, so a value the column cannot hold would cost the identifier
# silently — and no UI exists to add it back.
_IDENTIFIER_VALUE_LIMIT = 255

# DW-20: `product_identifiers.vendor_scope` is its own VARCHAR(255) column, and
# it gets its own constant for the same reason `_RECEIPT_FIELD_LIMITS` is a
# separate mapping from `_PRODUCT_FIELD_LIMITS`: two columns that happen to be
# the same width today are still two columns, and folding them into one number
# would make either one's widening silently change the other's rule. Checked on
# the form for the reason the value limit is: `add_identifier` refuses an
# over-long scope too, but only after `create_product` has committed, and
# `_attach_scanned_identifier` turns that refusal into an advisory flash rather
# than a field error — so the product would exist with its identifier discarded
# and no surface anywhere to add one back.
_IDENTIFIER_VENDOR_LIMIT = 255

# `Purchase.quantity` is an INTEGER, which MariaDB stores in 32 bits. A longer
# digit string parses fine in Python and then overflows the column, so the form
# refuses it here rather than letting the write fail with the generic message.
_MAX_INT32 = 2147483647


def _non_negative_int_string(value):
    """The value as a non-negative 32-bit int, or None if it is not one.

    The SHARED rule, and the one `_positive_int_string` below is a narrowing of.
    Story 5.1 needed a `quantity_on_hand` that accepts `0` — that is a
    meaningful, distinct state (tracked, none on hand) rather than an absent
    value — and the alternative to sharing was a second copy of a rule with
    three separate subtleties in it, which is how two forms come to disagree
    about one column.

    Deliberately NOT `int()`. `int('1_0')` is 10 and `int('٥')` is 5, so a form
    that promises "a whole number" would silently store something the operator
    did not type. `.isascii() and .isdigit()` is the rule the message states:
    ASCII digits, nothing else — no sign, no separator, no exponent, no
    non-ASCII numeral. It also rules out `-1` and `2.5` without a rule of its
    own, which is why neither is mentioned in either message.
    """
    text = (value or '').strip()
    if not (text.isascii() and text.isdigit()):
        return None
    # `int()` is NOT total over digit strings: CPython refuses to parse one
    # longer than `sys.int_info.str_digits_check_threshold` (4300) and raises
    # ValueError rather than returning a value. That reaches an unguarded GET
    # (`/products/add?duplicate_of=<4301 digits>` goes straight through
    # `_prefill_form_data`) and both form POSTs, where it is an HTML 500 on a
    # scan destination. Leading zeros are dropped first so the bound is on the
    # magnitude, not on the typing: `0000000001` still means 1, and anything
    # with more than ten significant digits is past the 32-bit column anyway.
    digits = text.lstrip('0') or '0'
    if len(digits) > len(str(_MAX_INT32)):
        return None
    parsed = int(digits)
    if parsed > _MAX_INT32:
        return None
    return parsed


def _positive_int_string(value):
    """The value as a POSITIVE 32-bit int, or None if it is not one.

    Behaviourally unchanged by the Story 5.1 split: it is exactly
    `_non_negative_int_string` with zero excluded. Everything it judges —
    `Purchase.quantity`, `duplicate_of`, the scanned `Q` record, the JSON
    purchase API — treats `0` as meaningless, so the exclusion stays here rather
    than moving into the shared rule.
    """
    parsed = _non_negative_int_string(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _valid_duplicate_of(value):
    """The product id a create form claims this scan already matched, or ''.

    `duplicate_of` is rendered straight into `url_for('main.product_detail',
    product_id=…)`, whose `int` converter raises `ValueError` on anything that
    is not a decimal id — a 500 for a hand-edited query string. Anything that
    cannot name a product is therefore not a duplicate claim at all: it is
    dropped from the pre-fill, from the render and from the gate below, so the
    warning block simply does not render.

    "Decimal digits" is not the same test as "could be a product id": `0` and a
    sixty-digit number are both all-digits, and both make the warning block
    assert that this scan matched a product while linking to one that cannot
    exist. `_positive_int_string` is the id-shaped rule (positive, inside the
    32-bit column), the same one `quantity` is judged by.
    """
    text = (value or '').strip()
    return text if _positive_int_string(text) is not None else ''


# Story 5.3 (FR28/FR29/FR31): the ONE stored-value -> operator-facing-label
# mapping, and the only place either spelling of the four statuses is written
# out. Both consumers read it, which is the point (AD-5): the `<select>`'s
# option labels on the two product forms and the detail page's `Stock status`
# row. Two mappings would let the operator pick `Out of stock` on the form and
# read something else back on the page, over the same stored value.
#
# `unknown` renders as `Not set` rather than as the em dash every other absent
# field uses, for the reason the quantity's `Not tracked` does: it is a state
# the operator can deliberately choose (returning here is how an assertion is
# withdrawn), so it needs words rather than a blank-looking marker.
#
# Ordered as the select renders them — the default first, then increasing
# concern — and a plain dict, so the order is the literal one below.
_STOCK_STATUS_LABELS = {
    StockStatus.UNKNOWN.value: 'Not set',
    StockStatus.OK.value: 'OK',
    StockStatus.LOW.value: 'Low',
    StockStatus.OUT.value: 'Out of stock',
}

# What the shared validator will accept, and the order its refusal message
# enumerates. Built from `StockStatus` rather than from the label mapping above,
# so that "ordered as the enum declares them" is true by CONSTRUCTION: the
# service builds its own `_STOCK_STATUS_VALUES` from the enum too, and both
# tuples are read out verbatim into operator-visible refusal text, so an order
# that agreed only by two hand-written lists matching would be one edit away
# from two refusals enumerating differently. The label mapping's order is a
# DISPLAY decision (it drives the select) and is free to change; this one is
# the vocabulary's own order and must not drift from the service's.
#
# That the two agree about MEMBERSHIP — that nothing is renderable but
# unsubmittable, or the reverse — is asserted rather than assumed:
# `test_every_stored_status_has_an_operator_facing_label` compares this
# mapping's keys against the enum, and
# `test_the_route_and_the_service_enumerate_the_same_values` compares this
# tuple against the service's element for element.
_STOCK_STATUS_VALUES = tuple(member.value for member in StockStatus)


def _stock_status_choices():
    """The `(value, label)` pairs the two product forms render as options.

    Built here rather than in Jinja for the reason `identifier_type_choices` is:
    a template that imported the enum would be a second place the vocabulary
    lives, and this one additionally carries the operator-facing labels, which
    are a display decision and therefore the route's (AD-5).
    """
    return list(_STOCK_STATUS_LABELS.items())


def _selected_stock_status(form_data, stored=None):
    """Which option the two forms' `<select>` renders `selected` (AD-5).

    The submitted value when it is one this control can actually render;
    otherwise the STORED value when THAT is renderable; otherwise `unknown`.

    The fallback being the stored value rather than the submitted one is the
    whole reason this function exists, and it is deliberately the OPPOSITE of
    the `{**stored, **form_data}` "submitted wins" rule every other control on
    the edit form follows. Those are `<input>`s: an in-flight value that failed
    validation is rendered back into the box, the operator sees exactly what
    they typed, and they can correct it. A `<select>` cannot do that. An option
    list holds four values and nothing else, so a submitted `''` or `'bogus'`
    matches no option, NOTHING renders `selected`, and a browser then displays
    AND SUBMITS the first option — `Not set`. The bad value is invisible to the
    operator, uncorrectable by them, and silently replaced.

    That is not a cosmetic difference on this field. The page the operator is
    handed after a refusal is the page they fix and re-save, so a control that
    fell back to the submitted value would make an unrelated refusal (an
    over-long `location`, say, posted alongside a truncated `stock_status`)
    withdraw a stored `low` and NULL its assertion date on the very next save —
    with nothing on the page at any point saying the flag was there. Falling
    back to what is STORED means the worst a refused submit can do is show the
    operator the status they already had.

    `unknown` is the last resort, for the un-flushed/hand-built `Product` some
    tests construct (whose `stock_status` is `None`) and for a stored value
    outside the enum — a hand-run UPDATE or a restored backup. Rendering
    nothing selected is not an option there for the reason above.
    """
    # Membership is tested against the LABEL mapping, not against
    # `_STOCK_STATUS_VALUES`, because the mapping is what
    # `_stock_status_choices` renders and this function's whole claim is "a
    # value this control can actually render". The two agree today and a test
    # says so, but a later story adding a `StockStatus` member and forgetting
    # its label would make the accepted set the wider one — and returning a
    # value no `<option>` carries marks NOTHING selected, which is precisely the
    # silent first-option substitution described above. Reading the mapping
    # makes the docstring true by construction rather than by companion test.
    submitted = form_data.get('stock_status')
    if submitted in _STOCK_STATUS_LABELS:
        return submitted
    if stored in _STOCK_STATUS_LABELS:
        return stored
    return StockStatus.UNKNOWN.value


def _validate_product_form(form_data):
    """Validate what BOTH product forms carry. Returns field -> error message.

    This is the SHARED half: the Product columns `add.html` and `edit.html` both
    render, the tag field they both render, and the FR41 duplicate gate.

    The receipt, first-receipt `quantity` and identifier rules deliberately do
    NOT live here any more; they moved to `_validate_product_create_form`. Note
    that Story 5.1's `quantity_on_hand` is a DIFFERENT field on a different
    table and belongs here, precisely because both templates render it — the two
    names are near-neighbours and the split between them is the whole point of
    this docstring. Owning every rule
    centrally so no caller could bypass one sounded like the safe default and
    was not: `product_edit` renders no first-receipt block and no scanned
    identifier card, reads none of those keys and writes none of them, so an
    edit POST carrying one was refused with a 200 whose message had no field to
    render beside — nothing written, nothing said (DW-13, DW-29). A route may
    not refuse a write because of a field it neither renders nor reads.

    The FR41 duplicate gate stays SHARED even though `edit.html` has no
    `confirm_duplicate` checkbox, because scoping it to the create route would
    be a real hole rather than a cosmetic one: the destructive-by-accident
    outcome FR41 names is creating a SECOND product for a scan that already
    resolved, and (on the `inventory_shorten` precedent) a validation error
    before any write is the only way to guarantee nothing at all is written.
    That is exactly why `edit.html` carries an unkeyed fallback block — it
    renders any error key it has no OWN message slot for, `notes` included, so
    this gate and any rule this function gains later cannot be silent THERE.
    `add.html` has no such block; it renders an `invalid-feedback` for every
    field this function can currently key on, so nothing it emits today is
    homeless on the create form — but a rule keyed on `notes`, the one control
    neither template gives a message slot of its own, would be homeless there.
    """
    errors = {}
    if not (form_data.get('description') or '').strip():
        errors['description'] = 'Label Description is required.'
    for field, (label, limit) in _PRODUCT_FIELD_LIMITS.items():
        value = (form_data.get(field) or '').strip()
        if value and len(value) > limit and field not in errors:
            errors[field] = f'{label} must be {limit} characters or fewer.'

    # Normalized here — PURELY, with the result discarded — before anything is
    # written, so a path the column could not hold re-renders the form beside
    # the Category field instead of failing inside the service, which never
    # raises and so could only report it as a generic flash (Story 3.1). The
    # util's message names the length it MEASURED, which is the normalized one:
    # no length lives here, and the service stays the sole normalizer on the
    # write path (AD-4). A missing key normalizes to None, which is not an
    # error, so an edit POST that omits the field is untouched.
    try:
        category_util.normalize_category_path(form_data.get('category_path'))
    except category_util.InvalidCategoryPathError as e:
        errors['category_path'] = str(e)

    if _valid_duplicate_of(form_data.get('duplicate_of')) and \
            (form_data.get('confirm_duplicate') or '').strip() != 'yes':
        errors['confirm_duplicate'] = (
            'This scan already matched an existing product. Confirm below that '
            'you want to create a separate product anyway.')

    if 'tags' in form_data:
        # Parsed here — PURELY, before anything is written — so an unusable
        # tag re-renders the form and no product is ever created (Story 3.3).
        # The util's message is operator-readable and rendered verbatim.
        try:
            tag_util.parse_tag_list(form_data.get('tags'))
        except tag_util.InvalidTagError as e:
            errors['tags'] = str(e)

    # Story 5.1 (FR23/FR24). SHARED, not create-only, for the reason this
    # function exists: `quantity_on_hand` is rendered by BOTH product templates
    # and read by both routes, so a rule living in
    # `_validate_product_create_form` would let an edit POST write an unusable
    # value while the create form refused it.
    #
    # Judged by `_non_negative_int_string`, NOT by `_positive_int_string`: `0`
    # is a state this column means something by ("tracked, none on hand"), which
    # is exactly what separates this field from the create form's first-receipt
    # `quantity` two blocks down. A BLANK value is not an error and never
    # reaches the check — blank is how the operator says "not tracked", and the
    # service clears both columns for it.
    #
    # The recount checkbox is deliberately NOT validated: it is a checkbox, so
    # every value a browser can send means "checked" and its absence means
    # "not checked". There is no third thing for a rule to refuse.
    #
    # No `not in errors` guard: this is the only rule keyed on the name, so a
    # first-writer-wins test would be a condition that cannot be false. Same
    # shape and same reason as the `quantity` and `unit_price` rules in the
    # create-only validator.
    quantity_on_hand = (form_data.get('quantity_on_hand') or '').strip()
    if quantity_on_hand and _non_negative_int_string(quantity_on_hand) is None:
        errors['quantity_on_hand'] = (
            f'Quantity On Hand must be a whole number of zero or more and no '
            f'more than {_MAX_INT32}. Leave it blank to stop tracking the '
            f'quantity.')

    # Story 5.2 (FR26). SHARED for the same reason the rule above is, and judged
    # by the same `_non_negative_int_string`: `0` is a legal threshold ("low
    # only once the count reaches zero"), distinct from a blank, which means no
    # threshold at all and is therefore not an error. The message says what
    # blank means because that is the one thing about this field a reader cannot
    # guess — an unset threshold does not make a product low, it makes the
    # threshold branch of the signal simply not apply.
    reorder_threshold = (form_data.get('reorder_threshold') or '').strip()
    if reorder_threshold and _non_negative_int_string(reorder_threshold) is None:
        errors['reorder_threshold'] = (
            f'Reorder Threshold must be a whole number of zero or more and no '
            f'more than {_MAX_INT32}. Leave it blank for no threshold.')

    # Story 5.3 (FR28/FR29). SHARED for the reason the two rules above are: the
    # `<select>` renders on BOTH product templates and both routes read it, so a
    # rule living in `_validate_product_create_form` would let an edit POST
    # reach the service with a value the create form refused.
    #
    # Keyed on PRESENCE, and the shape differs from the two rules above in a way
    # worth stating: for them a blank is a legal value (it clears a nullable
    # column), so their check begins `if <stripped value>`. `stock_status`
    # cannot be NULL and has no blank state at all, so a present-but-empty key
    # is an ERROR here rather than a no-op — the browser's own control can never
    # send one, so a blank means a truncated or hand-built POST, and letting it
    # through would need the service to invent a destination for it. An ABSENT
    # key remains the untouched case (a non-browser client PATCHing one field),
    # which is why the rule is guarded on `in form_data` rather than on
    # truthiness.
    #
    # The message enumerates the four stored values, built from `StockStatus`
    # so it cannot drift from what the service will accept. It names the STORED
    # spellings rather than the operator-facing labels because those are what a
    # caller hand-building a POST has to send; an operator never sees this
    # message from the rendered form, whose select cannot produce a bad value.
    if 'stock_status' in form_data:
        submitted = form_data.get('stock_status')
        if submitted not in _STOCK_STATUS_VALUES:
            errors['stock_status'] = (
                f'Stock Status must be one of '
                f'{", ".join(_STOCK_STATUS_VALUES)}.')
    return errors


def _validate_product_create_form(form_data):
    """`_validate_product_form` plus the rules only the CREATE form can trigger.

    Everything below judges a field that exists on `add.html` alone — the
    optional first-receipt block and the scanned-identifier card — and that only
    `product_add` reads and writes. `product_add` is the sole caller by
    construction: the split is what keeps `product_edit` from refusing a POST
    over a field it has no input for and no message slot for.
    """
    errors = _validate_product_form(form_data)

    for field, (label, limit) in _RECEIPT_FIELD_LIMITS.items():
        value = (form_data.get(field) or '').strip()
        if value and len(value) > limit and field not in errors:
            errors[field] = f'{label} must be {limit} characters or fewer.'

    # A scanned `Q` arrives as the string the label carried (no coercion — see
    # the pre-fill mapping), so this is where it is finally judged, exactly as
    # a typed value would be.
    quantity = (form_data.get('quantity') or '').strip()
    if quantity and _positive_int_string(quantity) is None:
        errors['quantity'] = (
            f'Quantity must be a whole number greater than zero and no more '
            f'than {_MAX_INT32}.')

    # DW-22: the block's price, judged by `_purchase_unit_price` — the single
    # definition of what `Purchase.unit_price` accepts, which `purchase_add` and
    # `api_record_purchase` already share. This form deliberately restates none
    # of it and emits its messages verbatim, because a third hand-copied list is
    # exactly how the first two came to disagree about this column. It is judged
    # HERE, in front of `create_product`, for the reason the identifier rules
    # below are: the Purchase is written after the commit and non-fatally, so a
    # price the column cannot hold would otherwise cost the whole receipt. A
    # bare `Decimal(...)` would not do: SQLite (what the unit suite runs on)
    # hides both the eight-digit magnitude and the two-place scale, and
    # `Decimal('NaN')` parses, reports success and stores NULL.
    #
    # No `'unit_price' not in errors` guard, unlike the length loops above: this
    # is the only rule in the file that keys on the name, so a first-writer-wins
    # test here would be a condition that cannot be false, advertising a
    # collision no reader could find. The `quantity` rule directly above is
    # written the same way, for the same reason.
    unit_price = (form_data.get('unit_price') or '').strip()
    if unit_price:
        _, message = _purchase_unit_price(unit_price)
        if message:
            errors['unit_price'] = message

    # The identifier is judged HERE, before `create_product` commits, for the
    # reason the duplicate gate is: `_attach_scanned_identifier` runs after the
    # commit and is deliberately non-fatal, so anything it refuses there is a
    # product that exists with its identifier silently thrown away — and there
    # is no surface anywhere to add one afterwards. Every check that can be made
    # from the form alone therefore belongs in front of the write.
    identifier_value = (form_data.get('identifier_value') or '').strip()
    identifier_type = (form_data.get('identifier_type') or '').strip()
    # The type is what decides how the value is stored and normalized (a GTIN
    # gets its check digit folded to the canonical 14), so an unselected
    # `<select>` must not silently become whichever member the enum declares
    # first. Field-scoped, and only when there is a value to type.
    #
    # Every rule below is gated on a non-blank VALUE, and not only because a
    # blank one attaches nothing: `add.html` renders the whole Scanned
    # Identifier card — and therefore both `invalid-feedback` blocks — only when
    # `form_data.identifier_value` is set. An error raised beside a blank value
    # would render nowhere, and the operator would get a silent 200 that wrote
    # nothing with no message anywhere on the page.
    if identifier_value:
        if not identifier_type:
            errors['identifier_type'] = (
                'Choose the type of the scanned identifier, or clear its value.')
        elif identifier_type not in _identifier_type_choices():
            # A hand-edited `identifier_type=` (or `INTERNAL`, which
            # `add_identifier` refuses outright) would otherwise be rejected
            # only after the commit.
            errors['identifier_type'] = 'Choose a valid identifier type.'
    if identifier_value and len(identifier_value) > _IDENTIFIER_VALUE_LIMIT:
        errors['identifier_value'] = (
            f'Identifier must be {_IDENTIFIER_VALUE_LIMIT} characters or fewer.')

    # The fourth and last purely-checkable identifier fault, and the only one
    # `add_identifier` still judged after the commit — where a refusal costs a
    # product that exists with its identifier dropped behind an advisory flash.
    # No scan can land here (`classify()` types a value GTIN only once
    # `normalize_gtin` has ACCEPTED it — the whole of that acceptance, not the
    # check digit alone); it takes a value or a type entered by hand, either
    # in the form or in the query string that pre-fills it (`_scan_banner_args`
    # passes `scan_value` through to `identifier_value` unjudged).
    #
    # The judgement is a CALL into app/utils/gtin.py, never a re-derivation, so
    # the form refuses exactly the set `add_identifier` refuses and the two
    # cannot drift. `InvalidGtinError` is caught WHOLE: one raise covers a
    # non-digit, a wrong length, an all-zero run (the wedge no-read) and a
    # failed check digit, and narrowing to any one of them would mean re-listing
    # the other three here. The canonical key is
    # discarded — the service stays the sole normalizer on the write path
    # (AD-4).
    #
    # Fires on the exact, case-sensitive `GTIN`, the one branch the service
    # normalizes. The recovery CLAUSE is word-for-word the service's, so both
    # sides name the same remedy; only the verb differs, because here
    # `GTIN_UNVALIDATED` is still a `<select>` option to choose
    # (`_identifier_type_choices` offers it) and there the identifier would have
    # to be added again. Keep the clause in step when either side changes; each
    # side's wording is pinned by its own test. Skipped when `identifier_value`
    # already carries an error, following the file's first-writer-wins
    # convention.
    if identifier_value and identifier_type == IdentifierType.GTIN.value \
            and 'identifier_value' not in errors:
        try:
            gtin.normalize_gtin(identifier_value)
        except gtin.InvalidGtinError as e:
            errors['identifier_value'] = (
                f'{e} Choose the {IdentifierType.GTIN_UNVALIDATED.value} type '
                f'to keep the value exactly as entered, without check-digit '
                f'validation.')

    # DW-20: the identifier block's OWN vendor, the one thing a vendor-scoped
    # type cannot be stored correctly without. `add_identifier` reads it as the
    # row's `vendor_scope`, and a blank scope is not "unscoped" — '' is the
    # sentinel meaning GLOBAL (AD-9), so a second vendor's identical SKU
    # collides on `uq_product_identifiers_type_value_scope` instead of
    # coexisting beside the first. The form refuses the type without a scope
    # rather than storing one that quietly means something else.
    #
    # The types come from `_vendor_scoped_identifier_type_choices()`, which asks
    # app/models.py; nothing here re-lists them, so the rule and the help text
    # cannot drift from the scoping authority the service computes with.
    # Gated on a non-blank VALUE like every rule above it, for the same reason:
    # the card holding this field's `invalid-feedback` slot renders only when
    # there is a value.
    vendor_scoped_types = _vendor_scoped_identifier_type_choices()
    identifier_vendor = (form_data.get('identifier_vendor') or '').strip()
    if identifier_value and identifier_type in vendor_scoped_types \
            and not identifier_vendor:
        # Names the type the operator actually chose rather than reciting all
        # three: they have to act on THIS row, and a message that lists the set
        # makes them work out which member they are looking at. It also keeps
        # the rendered text independent of the enum's declaration order.
        errors['identifier_vendor'] = (
            f"{identifier_type} identifiers are unique per vendor, so Vendor "
            f"Scope is required. It is this identifier's own vendor, not the "
            f"First Receipt block's Vendor.")

    # Gated on the type as well, because that is the only case where the value
    # reaches the column at all: `add_identifier` discards `vendor` outright for
    # a globally-scoped type, and the field's help text promises exactly that
    # ("Ignored for every other type"). Refusing a length nothing would store
    # would be the form contradicting its own caption over a value it is about
    # to throw away. Skipped when the field already carries the message above,
    # following the file's first-writer-wins convention.
    if identifier_value and identifier_type in vendor_scoped_types \
            and len(identifier_vendor) > _IDENTIFIER_VENDOR_LIMIT \
            and 'identifier_vendor' not in errors:
        errors['identifier_vendor'] = (
            f'Vendor Scope must be {_IDENTIFIER_VENDOR_LIMIT} characters or '
            f'fewer.')

    return errors


def _form_tags(form_data):
    """The canonical tag list a VALIDATED product form carries.

    None when the POST omitted the `tags` key entirely — absent means "not
    provided", not "clear them" (the same partial-update rule product_edit
    applies to every other optional field). A present-but-empty field is an
    empty list, which clears.
    """
    if 'tags' not in form_data:
        return None
    return tag_util.parse_tag_list(form_data.get('tags'))


def _apply_product_tags(service, product_id, tags):
    """Write a just-saved product's tags; return an operator-facing message
    when the write failed, or None on success.

    The product and its tags are two transactions (create_product owns a retry
    loop over its own session), so a failure can land between them. Either way
    it is reported honestly — the product saved, the tags did not — but the two
    kinds need DIFFERENT advice:

    - A backend failure is transient, so writing the tags again fixes it (the
      replace is idempotent). So is the concurrent-writer race, which the
      service marks `retryable` — another save reached the same product first
      and rolled this one back, but nothing about the requested list is wrong.
    - A `ValidationError` on the tags field that is NOT marked retryable is a
      collision. `_validate_product_form` refuses everything a pure check can
      see, but the database's collation can still fold two tags Python keeps
      distinct (`café`/`cafe` under utf8mb4_unicode_ci), and re-submitting the
      identical list reproduces that refusal forever. The operator has to
      CHANGE a tag, so the message says so rather than telling them to retry a
      save that cannot succeed. Keying on the field ALONE would sweep the race
      into this arm and demand a change that fixes nothing.

    Every message asks the operator to ENTER tags again, never merely to save
    again: nothing kept what they typed. The edit form repopulates its tag field
    from the database, which by definition does not hold the tags this write
    just failed to store, so a bare re-save would write the OLD set (or none at
    all) and report success.
    """
    try:
        service.set_product_tags(product_id, tags)
        return None
    except ValidationError as e:
        # warning, not error: a refused retag is ordinary operator input, and
        # the service is careful to skip the audit record for exactly that
        # reason. Logging it as an operational failure here would undo the
        # distinction one layer up.
        current_app.logger.warning(
            f'Tag write refused for product {product_id}: {e}')
        if e.field == 'tags' and not getattr(e, 'retryable', False):
            return (f'The product was saved, but its tags were not: {e} '
                    f'Edit the product and enter different tags.')
        return (f'The product was saved, but its tags were not: {e} '
                f'Edit the product and enter its tags again.')
    except Exception as e:
        current_app.logger.error(
            f'Error writing tags for product {product_id}: {e}\n{traceback.format_exc()}')
        return ('The product was saved, but its tags were not. Edit the '
                'product and enter its tags again.')


def _product_form_data(product, tags=None):
    """Build the form_data mapping for rendering edit.html from a Product.

    `tags` comes from a dedicated service call (they live in their own table,
    and the Product is detached), and is rendered back into the single
    comma-separated field the form submits.

    Story 5.1's `quantity_recounted` checkbox is deliberately NOT seeded here.
    It is a per-submission intent ("I counted it again"), not a stored value, so
    a GET must always render it unticked; on a failed submit the POST body's own
    key survives through the `{**stored, **form_data}` merge at the re-render
    sites, which is exactly the round-trip the other controls get.
    """
    return {
        'description': product.description or '',
        'manufacturer': product.manufacturer or '',
        'mpn': product.mpn or '',
        'category_path': product.category_path or '',
        'tags': tag_util.format_tag_list(tags),
        'notes': product.notes or '',
        # Story 5.1. `is None` rather than `or ''`, which is not pedantry here:
        # a tracked quantity of 0 is falsy, and `product.quantity_on_hand or ''`
        # would render the "tracked, none on hand" state as an EMPTY field —
        # which this form reads as "stop tracking", so re-saving an untouched
        # edit page would silently untrack every product sitting at zero.
        'quantity_on_hand': ('' if product.quantity_on_hand is None
                             else str(product.quantity_on_hand)),
        # Story 5.2, `is None` for the same reason and with the same
        # consequence: a threshold of 0 is falsy, and `or ''` would render it as
        # an empty field — which this form reads as "no threshold", so re-saving
        # an untouched edit page would silently drop the one threshold shape
        # that says "tell me the moment this runs out".
        'reorder_threshold': ('' if product.reorder_threshold is None
                              else str(product.reorder_threshold)),
        # Story 5.3. The stored value, not a label: it is what a re-post has to
        # carry, and it is what `_selected_stock_status` reads as the SUBMITTED
        # half of its decision on the failure re-render. WHICH option carries
        # `selected` is not decided from this entry — the templates compare
        # `stock_status_selected`, which the route passes separately. The
        # `or` fallback is not the falsy-zero hazard the two fields above guard
        # against — this column is NOT NULL and its only falsy possibility is a
        # None that cannot come from the database — it is a guard for the
        # unsaved/hand-built Product some tests construct, where an empty string
        # would leave the select with nothing selected and the browser would
        # silently pick the first option.
        'stock_status': product.stock_status or StockStatus.UNKNOWN.value,
        'location': product.location or '',
        'sub_location': product.sub_location or '',
    }


# --- Scan pre-fill boundary (Story 4.5, FR39/FR40) --------------------------

# The ONLY `request.args` names `product_add`'s GET reads, and the set
# `product_search` forwards into its own "Create a new product" link. A fixed
# whitelist rather than `request.args` wholesale: the form round-trips whatever
# it is handed into `form_data`, so an unbounded read would let any query string
# put arbitrary keys in front of the operator.
#
# Story 5.3's `stock_status` is deliberately NOT here, and the omission is a
# decision rather than an oversight. This whitelist is read from `request.args`
# and `product_search` forwards it into its "Create a new product" link, so
# membership would let a query string put a stock ASSERTION in front of the
# operator — a claim about a product's stock that nobody made, pre-selected on a
# control that posts on every save. The duplicate-a-product flow gives the same
# answer from the other direction: a duplicated product has had no assertion
# made about it, so `unknown` is the only honest starting value. (DW-249 asks
# whether `reorder_threshold` — a per-product POLICY rather than an
# observation — should join this list; that question is untouched here.)
_PRODUCT_PREFILL_ARGS = (
    'description', 'manufacturer', 'mpn', 'category_path', 'tags', 'notes',
    'identifier_type', 'identifier_value', 'identifier_vendor',
    'quantity', 'order_number', 'vendor', 'vendor_sku',
    'duplicate_of',
)

# The create form's optional first-receipt block. Two tuples, and they are
# deliberately DIFFERENT sets: this one is everything a Purchase is WRITTEN
# from, and `_RECEIPT_TRIGGER_FIELDS` below is the subset whose SURVIVING ITS
# PARSE decides whether there is a Purchase at all. Non-blankness was the rule
# until DW-187: a `quantity` of `'abc'` is non-blank and stores nothing, so
# testing the typed string wrote receipts with no content in them.
#
# They were one set until DW-27, and being one set is exactly what broke.
# `_ecia_prefill` puts a distributor label's `P` record into `vendor_sku`, so
# scanning a part-number-only envelope, typing a description and saving recorded
# a Purchase nobody asked for — vendor, quantity, unit price and order number all
# NULL, a `vendor_sku` the operator never typed, and an `order_date` that
# `record_purchase` defaults to today — into the FR20/FR21 history. `vendor` is
# out for a reason of meaning rather than of exposure: no ECIA record carries a
# vendor, so no SCAN supplies one, but `_PRODUCT_PREFILL_ARGS` does carry it and
# `product_search` forwards that whitelist, so a query string can put one in
# front of the operator. It is excluded because naming WHO sells the part is not
# saying a shipment came, and a lone `unit_price` (DW-22) is likewise a fact
# about the PRODUCT. So the trigger is exactly the two fields a human plausibly
# types as part of a RECEIPT.
# `quantity` and `order_number` stay triggers even when a label pre-filled them:
# those are receipt content rather than identity, and the operator confirms them
# on the form before saving.
#
# All five names here are still read whenever a trigger fires, so DW-22's
# complaint stays fixed rather than reverted: a quantity plus a price records ONE
# priced Purchase, not a second one added afterwards. When no trigger fires,
# `vendor`, `vendor_sku` and `unit_price` are silently not written, and the
# block's help text — not a validation error — is what tells the operator so.
# Making the MISSING TRIGGER itself the error would recreate DW-27 in mirror
# image, handing a refusal to an operator over a field a scan filled in for them.
#
# What is NOT waived is validation of the values themselves. The rules in
# `_validate_product_create_form` never consult the trigger, so an unstorable
# `unit_price` or an over-long `vendor`/`vendor_sku` is still refused even when
# both triggers are blank and a storable value in that same position would have
# been dropped. The asymmetry is deliberate rather than an oversight: the
# operator is asked to fix what the column cannot hold, and is never asked to
# supply a receipt they did not have. `docs/user-manual.md` states it too, so
# the surprise is documented on the surface the operator actually reads.
#
# `unit_price` is NOT in `_RECEIPT_FIELD_LIMITS`, which is text columns only; its
# rule is numeric and lives in `_purchase_unit_price`.
#
# It is deliberately NOT in `_PRODUCT_PREFILL_ARGS` either, which is a THIRD set
# and not this one: that whitelist bounds what a query string may put in front of
# the operator, and nothing in the app emits a price into one. No distributor
# envelope carries one (`ECIA_FIELD_KEYS` has none), `_scan_banner_args` forwards
# only `mpn`/`quantity`/`order_number`/`vendor_sku`, and `product_search` forwards
# the whitelist itself. Adding it would widen that surface for no producer;
# `test_a_url_borne_price_does_not_prefill_the_block` pins the omission so it
# stays a decision rather than an oversight. A POST re-render round-trips the
# typed value through `form_data` regardless, which is the path that matters.
_RECEIPT_FIELDS = ('quantity', 'order_number', 'vendor', 'vendor_sku',
                   'unit_price')

# The subset of the above that a Purchase is TRIGGERED by (DW-27). A subset by
# construction and not merely by coincidence, and the guard below subscripts
# `parsed` deliberately: a trigger name that is not also read raises `KeyError`
# there, and `product_add` catches it into "An error occurred while creating the
# product" over a Product that has ALREADY committed — the save-looks-failed
# resubmit that `_record_first_receipt`'s docstring names FR41 to avoid. Failing
# that loudly beats `.get()` quietly never triggering. The containment and the
# exact contents are pinned in `TestFirstReceiptOnCreate`, so narrowing or
# widening this stays a decision someone makes rather than a line someone slips
# in, and the pin fails long before any operator meets that traceback.
#
# What the guard tests is the value as PARSED, not the typed string: a
# `quantity` of `'abc'` is not a trigger, because a receipt whose only trigger
# content is unusable is a row nobody can read. Not every name has a parse of
# its own — `order_number`'s stripped string IS its parsed form, and only
# `quantity` and `unit_price` are put through anything — so adding a trigger
# that DOES have one means adding it to the parse in `_record_first_receipt`
# too, or the guard silently reads its raw string again and DW-187 reopens for
# that field. `_record_first_receipt` states the rule where it is enforced; this
# note exists so a reader of the tuple knows the membership question ("which
# fields") and the survival question ("with what in them") are answered in two
# different places.
_RECEIPT_TRIGGER_FIELDS = ('quantity', 'order_number')


def _identifier_type_choices():
    """The identifier types the create form may attach (FR40).

    INTERNAL is excluded because `add_identifier` refuses it: that row is
    derived from `products.internal_id` by `create_product` in one transaction,
    and letting it be added by hand is how the index would come to disagree with
    the column it mirrors. Built here and passed to the template so the enum
    stays out of Jinja.
    """
    return [t.value for t in IdentifierType if t is not IdentifierType.INTERNAL]


def _vendor_scoped_identifier_type_choices():
    """The offered types whose uniqueness is per-vendor, not global (DW-20).

    `app/models.py:VENDOR_SCOPED_IDENTIFIER_TYPES` is the scoping authority
    (AD-9) — the same frozenset `add_identifier` computes `vendor_scope` from —
    so this asks it rather than re-listing the three types the form would then
    have to keep in step by hand. Passed to the template like the type choices
    above, so Jinja never imports the enum either.

    Iterated over the ENUM and filtered, not over the frozenset: a set has no
    order, so listing it directly would let the help text name the same three
    types in a different order from one process to the next.

    Intersected with the OFFERED types, so the name stays honest. Nothing
    vendor-scoped is withheld today, but `_identifier_type_choices` already
    withholds one member, and a second exclusion would otherwise put a type the
    `<select>` cannot produce into the help text and into a rule that could
    never fire for it.
    """
    offered = _identifier_type_choices()
    return [t.value for t in IdentifierType
            if t in VENDOR_SCOPED_IDENTIFIER_TYPES and t.value in offered]


def _duplicate_product_exists(product_id):
    """Whether a `duplicate_of` pre-fill names a product that actually exists.

    Shape is not existence. `_valid_duplicate_of` only proves the value COULD be
    an id; a stale bookmark or a hand-edited query string then renders the
    warning block asserting "this scan already matched an existing product",
    links it to a detail page that 404s, and makes the FR41 gate demand that the
    operator confirm duplicating nothing. Checked only here, on the pre-fill
    path where a `duplicate_of` arrives from outside — the arrival banner's own
    link always names the product the banner was rendered on.

    A lookup FAILURE leaves the claim standing rather than dropping it: the gate
    is the half that must fail closed, and dropping the field because the
    database blinked would remove it.
    """
    try:
        return _get_catalog_service().get_product(int(product_id)) is not None
    except Exception as e:
        current_app.logger.warning(
            f'Could not verify duplicate_of={product_id!r}: {e}')
        return True


def _prefill_form_data():
    """`product_add`'s GET `form_data`: a whitelist of `request.args`, verbatim.

    Every value is rendered into an ordinary editable input and is read on GET
    only (FR39). Nothing is trimmed or truncated here — length is judged by
    `_validate_product_create_form` on POST, so a too-long pre-fill earns a field
    message rather than being silently shortened behind the operator's back.
    """
    data = {}
    for name in _PRODUCT_PREFILL_ARGS:
        value = request.args.get(name)
        if not value:
            continue
        if name == 'duplicate_of':
            # The one pre-fill that is not free text: it feeds an `int` URL
            # converter, so anything that cannot name a product is dropped and
            # the duplicate block is simply not rendered.
            value = _valid_duplicate_of(value)
            if not value or not _duplicate_product_exists(value):
                continue
        data[name] = value
    return data


def _attach_scanned_identifier(service, product_id, form_data):
    """Attach the identifier a scanned create form carried (FR40).

    Returns an operator-facing message when the attach failed, or None.

    Non-fatal, for the reason `_apply_product_tags` is: `create_product` has
    already committed by the time this runs, so telling the operator the save
    failed while the Product demonstrably exists is the worse lie. The realistic
    failure is the uniqueness one — `uq_product_identifiers_type_value_scope`
    makes a GTIN globally unique, so "create a separate product anyway" (FR41)
    and "attach the scanned GTIN to it" are mutually exclusive at the schema
    level. The message names the conflict (the service's own text names the
    holding product) and the identifier stays where it is; moving it would
    rewrite the first product's identity from a form that never mentioned it.

    The `vendor` passed is the identifier block's OWN `identifier_vendor` input
    and never the receipt block's "Vendor" (DW-20). `add_identifier` stores it
    as this row's `vendor_scope` for a vendor-scoped type — the namespace its
    uniqueness is measured in — so borrowing the receipt's vendor would let two
    inputs the form presents as unrelated decide each other, while passing
    nothing at all made every vendor-scoped identifier global and collided the
    second vendor's identical SKU with the first's. A blank becomes None, which
    for a vendor-scoped type the service stores as `''` — the GLOBAL sentinel,
    i.e. the bug itself — so it is `_validate_product_create_form` that keeps one
    from reaching here, NOT any degradation in the service. For a
    globally-scoped type the argument is ignored outright and `vendor_scope`
    stays `''`, which is correct for it.
    """
    value = (form_data.get('identifier_value') or '').strip()
    if not value:
        return None
    identifier_type = (form_data.get('identifier_type') or '').strip()
    try:
        service.add_identifier(product_id, identifier_type=identifier_type,
                               value=value,
                               vendor=(form_data.get('identifier_vendor') or '').strip() or None)
        return None
    except ValidationError as e:
        current_app.logger.warning(
            f'Scanned identifier refused for product {product_id}: {e}')
        return (f'The product was saved, but the scanned identifier was not '
                f'attached: {e}')
    except Exception as e:
        current_app.logger.error(
            f'Error attaching identifier to product {product_id}: {e}\n'
            f'{traceback.format_exc()}')
        # Deliberately does NOT tell the operator to add it from the product
        # page: there is no identifier-management surface anywhere yet (see the
        # ledger), so naming one would be advice the UI cannot honour.
        return ('The product was saved, but the scanned identifier was not '
                'attached. Note the identifier — it must be added by hand once '
                'a product can be given one.')


def _record_first_receipt(service, product_id, form_data):
    """Record the optional first receipt a create form carried (FR39).

    One Purchase, only when a TRIGGER field SURVIVES PARSING — a Quantity that
    is a positive whole number, or a non-blank Order Number
    (`_RECEIPT_TRIGGER_FIELDS`, DW-27). All five `_RECEIPT_FIELDS` are then
    written onto that one Purchase; when no trigger fires, the other
    three are read and discarded rather than refused. Returns an
    operator-facing message on failure, or None. `record_purchase` never raises
    — it returns None — so this is non-fatal in the same way the identifier
    attach above is, and for the same reason.

    The blanket `except` is that reason made good: `record_purchase` PROMISES
    not to raise, but this runs after `create_product` has committed, so if it
    ever broke that promise the exception would reach `product_add`'s outer
    handler and re-render the form saying the save failed while the Product
    exists — and the operator's natural resubmit would create the second
    product FR41 exists to prevent. Both siblings above guard the same way.
    """
    values = {name: (form_data.get(name) or '').strip() for name in _RECEIPT_FIELDS}
    # Parsed BEFORE the trigger is tested, so what triggers a receipt is a value
    # that can be STORED rather than a string that can be typed. `order_number`
    # has no parse of its own — its stripped string is its parsed form — so
    # `quantity` is the only trigger the order changes, and it is the one that
    # needed it: tested on its raw string, a `quantity` of `'abc'` triggered and
    # then parsed to None, writing a Purchase whose only content was the
    # `order_date` `record_purchase` defaults to today, and reporting success.
    # Nothing downstream refuses that row, and no reader can tell it from a
    # receipt someone meant. It now declines instead — silently, exactly as a
    # blank form does, because refusing would hand the operator a message about
    # a field a scan may have filled in for them, which is DW-27 in mirror image.
    #
    # `unit_price` is parsed here too, but only because both parses may as well
    # happen in one place: it is not a trigger, so its position relative to the
    # guard changes nothing. It is now parsed on every create that carries a
    # price rather than only on the ones that record a receipt, which is safe
    # because both parse helpers are TOTAL — they return a value or a message
    # and raise nothing — and the early return that used to shield them is gone.
    # Its message is still discarded —
    # `_validate_product_create_form` has already proved the value parses on the
    # path an operator takes, and a caller that reached here another way is
    # better served by the real receipt its trigger asked for, missing a price,
    # than by no receipt at all. That is the one place this still fails open,
    # and it can only lose a price from a Purchase something else meant.
    parsed = dict(
        values,
        quantity=_positive_int_string(values['quantity']),
        unit_price=(_purchase_unit_price(values['unit_price'])[0]
                    if values['unit_price'] else None),
    )
    # "Survived" is spelled out rather than left to truthiness. It happens to be
    # the same test today — `_positive_int_string` never returns `0`, and a blank
    # `order_number` is the empty string — but a parsed value has falsy shapes a
    # string does not: an accepted `Decimal('0.00')` is falsy, so a trigger set
    # that ever grew `unit_price` would silently never fire. That is the failure
    # the `KeyError` note above cannot catch, because it is a no-op rather than a
    # traceback.
    if all(parsed[name] in (None, '') for name in _RECEIPT_TRIGGER_FIELDS):
        return None
    try:
        snapshot = service.record_purchase(
            product_id,
            vendor=parsed['vendor'] or None,
            vendor_sku=parsed['vendor_sku'] or None,
            quantity=parsed['quantity'],
            unit_price=parsed['unit_price'],
            order_number=parsed['order_number'] or None,
        )
    except Exception as e:
        current_app.logger.error(
            f'Error recording first receipt for product {product_id}: {e}\n'
            f'{traceback.format_exc()}')
        snapshot = None
    if snapshot is None:
        return ('The product was saved, but its first receipt was not recorded. '
                'Add the purchase from the product page.')
    return None


def _render_product_add(form_data, validation_errors):
    """The single render of the create form, so every path carries the same
    template context (including the identifier-type choices).

    The one value scrubbed on the way through is `duplicate_of`: the duplicate
    block renders it into `url_for('main.product_detail', product_id=…)`, so a
    value the `int` converter cannot take would be a 500 on a re-render. Done
    here rather than only in the GET pre-fill so a POST cannot reach it either.
    """
    if form_data.get('duplicate_of') and not _valid_duplicate_of(form_data.get('duplicate_of')):
        form_data = {k: v for k, v in form_data.items() if k != 'duplicate_of'}
    return render_template('product/add.html', title='Add Product',
                           validation_errors=validation_errors,
                           form_data=form_data,
                           # Story 5.3: the option list comes from here so the
                           # template never imports the enum and never spells
                           # the operator-facing labels itself (AD-5), and so
                           # does the CHOICE of which one is selected — no
                           # stored value exists on the create form, so an
                           # unrenderable submitted value falls all the way
                           # back to `unknown`.
                           stock_status_choices=_stock_status_choices(),
                           stock_status_selected=_selected_stock_status(
                               form_data),
                           identifier_type_choices=_identifier_type_choices(),
                           vendor_scoped_identifier_types=_vendor_scoped_identifier_type_choices())


@bp.route('/products/add', methods=['GET', 'POST'])
def product_add():
    """Create a Product from the catalog UI.

    GET additionally accepts the scan pre-fill (FR39/FR40): a routed scan hands
    this form the identifier it carried, a distributor label's MPN / quantity /
    order references, or the raw scan text as a description — always through
    `request.args`, always rendered editable.

    POST gains three effects after `create_product` succeeds, beside the
    existing tag handling and each non-fatal for the same reason it is: the
    scanned identifier is attached, an optional first receipt is recorded, and
    the operator is redirected to the new product. The `duplicate_of` /
    `confirm_duplicate` gate that guards this write lives in
    `_validate_product_form` — the SHARED half that
    `_validate_product_create_form` calls first — so it runs before any of it
    (FR41).
    """
    if request.method == 'GET':
        return _render_product_add(_prefill_form_data(), {})

    form_data = request.form.to_dict()
    log_audit_operation('product_add', 'input', form_data=form_data)

    validation_errors = _validate_product_create_form(form_data)
    if validation_errors:
        return _render_product_add(form_data, validation_errors)

    # Parsed BEFORE the write, not after: _validate_product_form has already
    # proved this cannot raise, and doing it inside the try below would let a
    # tag rejection surface as "An error occurred while creating the product".
    tags = _form_tags(form_data)

    try:
        service = _get_catalog_service()
        new_id = service.create_product(
            description=form_data.get('description'),
            manufacturer=form_data.get('manufacturer'),
            mpn=form_data.get('mpn'),
            category_path=form_data.get('category_path'),
            notes=form_data.get('notes'),
            # Story 5.1. An omitted or blank `quantity_on_hand` is the UNTRACKED
            # default, so `.get()` returning None is exactly right and no
            # present-key dance is needed here — there is no stored value for an
            # absent key to preserve on a create.
            #
            # `quantity_recounted` is deliberately NOT read: on a create there
            # is nothing stored to re-confirm, every non-blank quantity is a
            # first assertion and stamps regardless, and `add.html` renders no
            # such control. A POST that carries the key anyway is simply
            # ignored.
            quantity_on_hand=form_data.get('quantity_on_hand'),
            # Story 5.2. Same shape and same reasoning: an omitted or blank
            # threshold is the default (none), so there is no stored value for
            # an absent key to preserve on a create.
            reorder_threshold=form_data.get('reorder_threshold'),
            # Story 5.3. NOT the same `.get()` shape as the two above: for them
            # an absent key and a blank one both mean the default, so None is
            # exactly right. This column has no blank state, so an absent key
            # must arrive as None (not provided — the service leaves the column
            # at its `unknown` default) while a PRESENT key is passed through
            # verbatim, blank included, for the service to refuse. The
            # validator above has already rejected anything outside the four
            # values, so what reaches here from the form is always one of them.
            stock_status=(form_data['stock_status']
                          if 'stock_status' in form_data else None),
            location=form_data.get('location'),
            sub_location=form_data.get('sub_location'),
        )
        if not new_id:
            flash('Failed to create product. Please try again.', 'error')
            return _render_product_add(form_data, {})

        # Everything below is post-commit and therefore non-fatal: each step
        # reports its own failure and NONE of them sends the operator back to a
        # form claiming the save failed, because the product demonstrably
        # exists. Collected rather than returned early so a failure in one step
        # cannot silently skip the next.
        followup_errors = []
        if tags:
            # A brand-new product carries no tags, so an empty list is a no-op
            # and is not worth a transaction.
            tag_error = _apply_product_tags(service, new_id, tags)
            if tag_error:
                followup_errors.append(tag_error)
        identifier_error = _attach_scanned_identifier(service, new_id, form_data)
        if identifier_error:
            followup_errors.append(identifier_error)
        receipt_error = _record_first_receipt(service, new_id, form_data)
        if receipt_error:
            followup_errors.append(receipt_error)

        # The success is flashed UNCONDITIONALLY, before the follow-up failures.
        # The product exists either way, and suppressing it made the one outcome
        # FR41's confirmed-duplicate path can ever produce — a product created,
        # its scanned identifier necessarily refused because the identifier is
        # globally unique and still belongs to the product the scan matched —
        # look to the operator like a save that had failed outright.
        flash('Product created successfully!', 'success')
        for message in followup_errors:
            flash(message, 'error')
        return redirect(url_for('main.product_detail', product_id=new_id))
    except Exception as e:
        current_app.logger.error(f'Error creating product: {e}\n{traceback.format_exc()}')
        flash('An error occurred while creating the product. Please try again.', 'error')
        return _render_product_add(form_data, {})


def _scan_arrival_banner(product_id):
    """The arrival banner a scan that RESOLVED to this product carries (FR41).

    None unless the URL carries `scan_kind`, in which case the page is
    byte-identical to what it was before this story. When it is present the
    route builds both links with `url_for` and hands the template a dict of
    finished values — the template computes no URL and assembles no query
    string (AD-5).

    "Receiving context" is this banner rather than a mode: there is no receipt
    mode in this application, so a matched scan lands on the record and offers
    "Add a purchase" as the operator's next click. The alternative — creating a
    second Product for a scan that already matched — is offered too, and carries
    `duplicate_of` so `_validate_product_form` demands an explicit confirmation
    before anything is written.
    """
    # Both discriminators are validated against the enums that produced them,
    # and the banner is suppressed outright when either fails. The URL is
    # hand-editable, and an unvalidated pair would let any query string assert
    # that an arbitrary scan of an arbitrary type matched this product — and
    # would put that bogus type on the "create a separate product" link, where
    # it becomes the `identifier_type` a save then tries to attach.
    scan_kind = (request.args.get('scan_kind') or '').strip()
    if scan_kind not in {kind.value for kind in ScanKind}:
        return None
    scan_type = (request.args.get('scan_type') or '').strip()
    if scan_type and scan_type not in _identifier_type_choices():
        return None
    # An untyped value is not an identifier. Only the `gtin` arm emits the pair,
    # always together, so a value without a type came from a hand-edited URL —
    # and the banner would otherwise display it as "what was scanned" while the
    # create link below silently dropped it (an identifier cannot be attached
    # without the type that says how to store it).
    scan_value = (request.args.get('scan_value') or '').strip() if scan_type else ''

    # The purchase pre-fill a distributor label carries: quantity, the order
    # number and the distributor's own part number. No date is pre-filled —
    # `9D`/`10D` are YYWW, a week with no day in it, and a manufactured day
    # would look like scanned data while being a guess.
    purchase_args = {}
    for name in ('vendor_sku', 'quantity', 'order_number'):
        value = (request.args.get(name) or '').strip()
        if value:
            purchase_args[name] = value

    # The create link carries the MPN too — the field FR39 names first. It is
    # NOT on the purchase link, because `Purchase` has no such column; a
    # duplicate-create that dropped it would make the operator retype the part
    # number off the label they just scanned.
    # `mpn` and `description` ride the create link and NOT the purchase one:
    # `Purchase` has no such column, while a duplicate-create that dropped them
    # would make the operator retype the part number — or, for an `internal`
    # scan, the whole label — off the thing they just scanned (FR39/FR40).
    create_args = dict(purchase_args)
    for name in ('mpn', 'description'):
        value = (request.args.get(name) or '').strip()
        if value:
            create_args[name] = value
    create_args['duplicate_of'] = product_id
    if scan_type and scan_value:
        create_args['identifier_type'] = scan_type
        create_args['identifier_value'] = scan_value

    return {
        'kind': scan_kind,
        'scan_type': scan_type,
        'scan_value': scan_value,
        'purchase_url': url_for('main.purchase_add', product_id=product_id,
                                **purchase_args),
        'create_url': url_for('main.product_add', **create_args),
    }


# The three fixed strings the tri-state quantity renders as (Story 5.1,
# FR23/FR24). Three DISTINCT literals is the requirement, not an implementation
# detail: a reader must never be able to confuse "not tracked" with "none on
# hand", so the untracked state gets its own words rather than the `—` every
# other absent field on the detail page uses, and the zero state says `0` rather
# than falling back to that dash.
_QUANTITY_UNTRACKED_DISPLAY = 'Not tracked'


def _product_quantity_display(product):
    """The finished quantity string the product detail page renders (AD-5).

    Computed here rather than in Jinja because the template must not be the
    place a domain rule lives — and because the rule is genuinely easy to get
    wrong in a template: `{{ product.quantity_on_hand or 'Not tracked' }}` reads
    naturally and is exactly the bug, since a tracked 0 is falsy and would
    render as untracked.
    """
    if product.quantity_on_hand is None:
        return _QUANTITY_UNTRACKED_DISPLAY
    return f'In stock: {product.quantity_on_hand}'


def _product_reorder_threshold_display(product):
    """The finished threshold string the product detail page renders (AD-5).

    The em dash is the page's ordinary "nothing here" marker — unlike the
    quantity above, an unset threshold really is an absence rather than a third
    named state. What it is NOT is `product.reorder_threshold or '—'`: a stored
    `0` is a threshold the operator deliberately set, and that spelling would
    render it as no threshold at all, which is the opposite claim.
    """
    if product.reorder_threshold is None:
        return '—'
    return str(product.reorder_threshold)


def _product_stock_status_display(product):
    """The finished stock-status string the product detail page renders (AD-5).

    Read out of `_STOCK_STATUS_LABELS`, the same mapping the two forms' option
    labels come from, so the operator can never pick one name on the form and
    read a different one back on the page.

    The fallback is the raw stored value rather than a dash or a guess. This
    column is NOT NULL and the write path admits only the four known values, so
    an unmapped string can only come from a hand-run UPDATE, a restored backup
    or a later story that added a member to `StockStatus` and forgot the label
    — and in all three cases showing what is actually stored is more useful
    than hiding it, and is what makes the omission visible.

    `None` is the one unmapped value NOT shown raw, because showing it raw
    means rendering the literal word `None` into the page. The column cannot be
    NULL, so this is never a persisted row: it is an un-flushed or hand-built
    `Product`, whose `stock_status` is None until the Python-side default is
    applied — the state `test_the_getter_answers_for_an_unset_status_attribute`
    pins on the model side. `unknown` is the honest reading of it (no assertion
    has been made) and it is what `_product_form_data` already coerces the same
    case to, so the form and the page agree about one instance.
    """
    stored = product.stock_status or StockStatus.UNKNOWN.value
    return _STOCK_STATUS_LABELS.get(stored, stored)


@bp.route('/products/<int:product_id>')
def product_detail(product_id):
    """View a Product by its direct URL (FR6), with purchase history (FR20/FR21).

    Story 4.5: when the URL carries `scan_kind`, the page additionally shows the
    scan-arrival banner (FR41). Without it nothing changes.

    Story 5.1: the tri-state quantity and the AGE of its verification stamp are
    computed here and handed to the template as finished strings (AD-5). The age
    is None whenever there is no stamp — which is exactly when there is no
    tracked quantity either, since the two columns only ever move together — and
    the template renders nothing rather than an empty parenthesis. The age shown
    is the age of the last COUNT, not of the last edit: the write contract only
    re-stamps on a real assertion.

    Story 5.2 adds the threshold and the Effective-Low signal beside them. The
    signal is READ off the Product, not computed here: `Product.is_effective_low`
    is its single home (AD-6), so this route writes no comparison of its own and
    stores nothing — the read leaves the row exactly as it found it (FR30).

    Story 5.3 adds the stored stock status and the age of its assertion, built
    the same way. The Reorder signal row is unchanged HERE and changed in
    meaning: `is_effective_low` now answers to a manual flag as well, so a
    product with no count and no threshold can read `Low stock`. This page
    renders two ages from this story on, so `now` is computed ONCE and passed
    to both `describe_age` calls — which is the case that function's own
    docstring asks for an explicit `now` in, so the two phrases are measured
    from one instant rather than from two.
    """
    service = _get_catalog_service()
    product = service.get_product(product_id)
    if product is None:
        abort(404)
    now = datetime.now()
    # Load purchases with a dedicated query (never product.purchases — that
    # would lazy-load on the detached Product).
    purchases = service.get_purchases_for_product(product_id)
    last_paid = service.get_last_paid_price(product_id)
    attachments = service.get_attachments_for_product(product_id)
    tags = service.get_tags_for_product(product_id)
    return render_template('product/detail.html',
                           title=product.description or f'Product {product_id}',
                           product=product, purchases=purchases, last_paid=last_paid,
                           attachments=attachments, tags=tags,
                           quantity_display=_product_quantity_display(product),
                           # Gated on the quantity, not on the stamp alone. The
                           # write contract moves the two columns together, so
                           # a stamp without a count is a state this app cannot
                           # produce — but a restored backup or a hand-run
                           # UPDATE can, and the ungated version rendered
                           # `Not tracked (counted 3 months ago)`: an age for a
                           # count the same line says does not exist.
                           quantity_verified_age=(
                               describe_age(product.quantity_verified_at, now)
                               if product.quantity_on_hand is not None
                               else None),
                           reorder_threshold_display=(
                               _product_reorder_threshold_display(product)),
                           stock_status_display=(
                               _product_stock_status_display(product)),
                           # Story 5.3, gated on the STATUS rather than on the
                           # stamp, for the reason the quantity age above is
                           # gated on the count: the write contract moves the
                           # two columns together, so a stamp on an `unknown`
                           # status is a state this app cannot produce — but a
                           # restored backup or a hand-run UPDATE can, and the
                           # ungated version would render `Not set (set 3
                           # months ago)`, a date for an assertion the same line
                           # says was never made.
                           #
                           # `or StockStatus.UNKNOWN.value` for the reason
                           # `_product_stock_status_display` and
                           # `_product_form_data` both carry it: an un-flushed
                           # or hand-built Product reads None here, and a bare
                           # `!=` is TRUE for None — so the gate would open on
                           # the one instance whose row above says `Not set`.
                           # All three coerce identically so no two of them can
                           # describe the same instance differently.
                           stock_status_age=(
                               describe_age(product.stock_status_at, now)
                               if (product.stock_status
                                   or StockStatus.UNKNOWN.value)
                               != StockStatus.UNKNOWN.value
                               else None),
                           effective_low=product.is_effective_low,
                           scan_banner=_scan_arrival_banner(product_id))


@bp.route('/products/search')
def product_search():
    """Free-text product search results (Story 4.5, FR36, AD-17).

    Deliberately minimal, and deliberately at this URL. It is the landing an
    ambiguous scan needs — a query, a list, an empty state, and an escape hatch
    to the create form carrying the scan's own pre-fill — and nothing else: the
    only query it issues is `search_products(q)`, with no filters, no paging, no
    ranking and no result-count signal. AD-17 fixes that method as the sole
    free-text entrypoint and defers the search MECHANISM to Epic 8, whose search
    page then extends this route rather than orphaning a scan-only one.
    """
    query = request.args.get('q', '').strip()
    # A blank query renders the empty state without querying: `search_products`
    # would answer `[]` anyway, and not asking says so more plainly.
    #
    # The search itself is guarded because this page is a SCAN DESTINATION. An
    # unhandled exception here is an HTML 500 — precisely the dead end `api_scan`
    # maps its own resolver failure to a JSON envelope to avoid, reached by the
    # same broken database one step later, after the client has already
    # navigated and the scan text is gone from the field.
    products = []
    search_failed = False
    if query:
        try:
            products = _get_catalog_service().search_products(query)
        except Exception as e:
            current_app.logger.error(
                f'Error searching products for {query[:120]!r}: {e}\n'
                f'{traceback.format_exc()}')
            # Carried into the template as well as flashed. An empty `products`
            # renders "No products match X" — a POSITIVE claim about the
            # catalog, which is exactly what a failed search cannot make, and
            # the operator who reads it instead of the flash creates a duplicate
            # of something the catalog already holds.
            search_failed = True
            flash('Search is unavailable right now. The scan was not lost — '
                  'create the product, or try the search again.', 'error')
    create_args = {name: request.args.get(name)
                   for name in _PRODUCT_PREFILL_ARGS if request.args.get(name)}
    if query and not create_args:
        # A query typed into the page's own search box rather than routed here
        # by a scan: nothing carries the operator's text onto the create form,
        # so "Create a new product" would open with `description` — the one
        # REQUIRED field — blank, and they would retype what they just typed.
        # Only when the request carries NO scan pre-fill at all, so the scan
        # mapping (a `gtin` deliberately leaves `description` empty) is untouched.
        create_args['description'] = _scan_url_value('description', query)
    # The same pre-fill is handed to the page's OWN search form as hidden
    # inputs. Refining the query is the most natural next action on a results
    # page, and a form carrying only `q` would silently drop the scan's
    # identifier, MPN and receipt values — so the create escape hatch on the
    # refined page would open blank on exactly the scan that got here.
    return render_template('product/search.html', title='Search Products',
                           query=query, query_display=_without_control_characters(query),
                           products=products, search_failed=search_failed,
                           prefill_args=create_args,
                           create_url=url_for('main.product_add', **create_args))


# The eight Purchase columns the HTML form carries, in render order.
_PURCHASE_FORM_FIELDS = ('vendor', 'vendor_sku', 'order_date', 'received_date',
                         'quantity', 'unit_price', 'order_number', 'source_url')

# The text columns this form writes. The three the create form's first-receipt
# block also writes are taken FROM that mapping rather than restated beside it:
# they are the same `Purchase` columns with the same limits and the same
# messages, so a second copy would only give a future widening somewhere to be
# missed and let the two forms disagree about one column. `source_url` is this
# form's alone (app/database.py: Purchase.source_url is VARCHAR(1024)).
# Without these an over-long value reaches MariaDB and comes back as the generic
# "Failed to record the purchase", with nothing said about WHICH field.
_PURCHASE_FIELD_LIMITS = dict(_RECEIPT_FIELD_LIMITS,
                              source_url=('Source URL', 1024))

# `Purchase.unit_price` is `Numeric(10, 2)` (app/database.py): eight digits
# before the point and exactly two after it. Both bounds are the form's to
# enforce — MariaDB refuses the first and silently rounds the second, and SQLite
# (what the unit suite runs on) does neither.
_MAX_UNIT_PRICE = Decimal('100000000')
_UNIT_PRICE_STEP = Decimal('0.01')

# The one zero this helper returns. `Decimal('-0')` is not negative, so it is
# accepted, and `quantize` carries the sign through (`Decimal('-0.00')`) — a
# `str()` MariaDB stores as `0.00` but that no reader of the returned value
# would guess. Naming the value here rather than negating in place keeps the
# fact that there is exactly ONE spelling of a zero price visible beside the
# bounds it belongs with.
_ZERO_UNIT_PRICE = Decimal('0.00')


def _purchase_unit_price(raw):
    """`(price, None)` for a storable unit price, or `(None, message)`.

    The single definition of what `Purchase.unit_price` accepts, applied by both
    HTTP entry points that write the column — `_parse_purchase_form` and
    `api_record_purchase`. `record_purchase` validates nothing, so those two
    routes are the only gates in front of it, and two hand-copied lists are how
    they came to disagree. The rule lives here rather than in the service
    because that is where both callers are; a future service-layer writer
    (`record_amazon_purchase`) does NOT inherit it.

    Three things the bare `Decimal(str(...))` conversion does NOT refuse, and
    this does:

    - `Decimal('NaN')` and `Decimal('Infinity')` raise neither `InvalidOperation`
      nor `ValueError`, so an unchecked parse accepts them, reports success and
      stores NULL — a silently discarded price. A negative price is refused for
      the same reason: nothing downstream is looking.
    - A finite, non-negative price is still not necessarily a STORABLE one.
      `Numeric(10, 2)` is eight digits before the point, and MariaDB refuses a
      value past `99999999.99` outright: `record_purchase` returns None and the
      operator gets the generic "Failed to record the purchase" naming no field.
    - The column keeps exactly two decimal places and rounds a third away, so
      `0.005` reported success while `0.01` — or, for `0.001`, nothing — is what
      was stored.

    Neither of the last two is visible under SQLite (what the unit suite runs
    on), which widens the column silently, so both are checked here rather than
    left to the backend. The order is load-bearing: `is_finite()` must come
    before any comparison, and `quantize` can itself raise on a `Decimal` whose
    magnitude has not already been bounded.

    The two bounds also lean on each other, which matters if either is ever
    loosened: the magnitude check is `>= 100000000` on the value AS TYPED, so
    `99999999.995` passes it and quantizes to `100000000.00` — past the column.
    It is the SCALE rule that refuses that value, not the ceiling. Relaxing the
    scale rule to round instead of refuse would therefore reopen the overflow
    the ceiling exists to prevent, unless the ceiling is tightened to compare
    the quantized value.

    What this does NOT refuse is what `Decimal` itself is lenient about:
    PEP 515 underscores and non-ASCII numerals (`Decimal('1_0')` is 10 and
    `Decimal('٥')` is 5), so those are stored as the number they spell rather
    than refused — unlike `quantity`, whose `_positive_int_string` rule exists
    to reject exactly that. Both entry points have always behaved this way and
    still agree, so tightening it would be a new business rule, not the parity
    this helper was extracted for; it is recorded in the deferred-work ledger.

    That leniency is about the SPELLING, and the accepted spellings are wider
    than a price looks: `-0` is a zero rather than a negative, `1E+7` is ten
    million, and `0.00E-99999999999999999` is a zero carrying an exponent no
    column has room for. Each is accepted as the number it spells — and each is
    RETURNED as one two-place `Decimal`, because the number is all that should
    survive. That is what the `quantize` on the way out is for, and it is not
    tidiness: PyMySQL renders a `Decimal` parameter with `str()`, so the SQL
    literal is whatever spelling the object kept, and the spellings do not fare
    alike. MariaDB takes `'-0'` and `'1E+7'` — it reads the latter as an
    approximate-value literal and converts it — but it refuses
    `'0E-100000000000000001'` outright, which made `record_purchase` return None
    and left each caller to say so in its own words — "Failed to record the
    purchase" on the purchase form, a 500 on the JSON endpoint, "its first
    receipt was not recorded" on the create form — every one of them naming no
    field, over a price the form had just told them was fine. Normalizing
    here makes the stored value one number with one spelling rather than a
    spelling the server happens to tolerate: every caller gets
    `Decimal('10000000.00')` for every spelling of ten million, and
    `Decimal('0.00')` for every spelling of zero including the signed one.
    `tests/integration/test_purchase_unit_price_decimal.py` is where the real
    column is asked, because SQLite cannot be.

    A JSON *number* is judged by the same rules as the string that spells it,
    which is stricter than it may look: `Decimal(str(3.3000000000000003))` has
    seventeen significant digits, so a client that computes a price in binary
    floating point is refused rather than quietly rounded. That is the scale
    rule doing its job — the caller sends the two decimal places it means, as a
    string or as a number that has them.
    """
    # One string, two ways to reach it: an unparseable value and a parseable
    # non-finite one are the same refusal to the operator.
    not_a_number = 'Unit Price must be a decimal number.'
    try:
        price = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None, not_a_number
    if not price.is_finite():
        return None, not_a_number
    if price < 0:
        return None, 'Unit Price must not be negative.'
    if price >= _MAX_UNIT_PRICE:
        return None, f'Unit Price must be less than {_MAX_UNIT_PRICE}.'
    # One `quantize`, used twice: as the scale TEST (a value that survives the
    # round trip unchanged had at most two places to begin with) and as the
    # value returned. Reusing it is what makes the two agree by construction —
    # a second call could only be a second chance to disagree — and it cannot
    # raise here, because the three checks above have already bounded the
    # magnitude to `[0, 100000000)`. That is the ordering the paragraph above
    # calls load-bearing.
    quantized = price.quantize(_UNIT_PRICE_STEP)
    if price != quantized:
        return None, 'Unit Price must have at most two decimal places.'
    # `-0` reaches here — it is not negative — and `quantize` keeps its sign, so
    # the sign is dropped explicitly rather than left to the column to swallow.
    return (_ZERO_UNIT_PRICE if quantized == 0 else quantized), None


def _purchase_text_length_error(name, value):
    """The over-length message for one `_PURCHASE_FIELD_LIMITS` column, or
    `None` if the value fits — the single definition both entry points apply,
    for the reason given on that mapping.

    Measured on the STRIPPED value, because that is what is stored: the service
    puts every text field through `_clean` (mariadb_catalog_service.py), which
    trims before the write. Measuring the raw value would refuse a padded string
    the column can hold — and the HTML form, which strips during its own
    pre-fill, would then accept a value the JSON endpoint rejects.

    A non-string value is left alone: the rule counts characters, and the JSON
    endpoint may be handed anything.
    """
    label, limit = _PURCHASE_FIELD_LIMITS[name]
    if isinstance(value, str) and len(value.strip()) > limit:
        return f'{label} must be {limit} characters or fewer.'
    return None


# The two date columns this form and `api_record_purchase` write, mapped to the
# label their refusal wears. Keyed the way `_PURCHASE_FIELD_LIMITS` is keyed, and
# for the same reason: the loop that parses them and the mapping that labels them
# are then the same set of columns, so a third date column cannot be parsed
# without a label or labelled without being parsed.
_PURCHASE_DATE_LABELS = {'order_date': 'Order Date',
                         'received_date': 'Received Date'}


def _purchase_date(name, value):
    """`(date, None)` for a storable purchase date, `(None, message)` for a
    refusal, and `(None, None)` for no date at all.

    The single definition of what `Purchase.order_date` and
    `Purchase.received_date` accept, applied by both HTTP entry points that write
    them — `_parse_purchase_form` and `api_record_purchase`. Like the other three
    helpers beside it, it lives here rather than in the service because
    `record_purchase` validates nothing by design and those two routes are the
    only gates in front of it; `record_amazon_purchase` takes both dates and does
    NOT inherit this rule either.

    The grammar it enforces is exactly the one the message names: an ASCII,
    zero-padded, four-digit-year `YYYY-MM-DD` calendar date, and nothing else.
    That is narrower than `date.fromisoformat`, which since 3.11 parses most of
    ISO 8601 — and the gap was not cosmetic. `'2026-W01-1'` is a week date that
    parses to `2025-12-29`, so a purchase the operator spelled in 2026 was
    recorded in the previous year, by a string the refusal sentence says is not
    accepted (DW-88). `'20260101'` is the same surprise, quieter only because it
    lands on the day meant. Not every rejection is the round-trip's, though, and
    the difference matters to anyone tempted to simplify this: `'2026-1-1'`,
    `'٢٠٢٦-٠١-٠١'` and `'2026-01-01T00:00:00'` never parse at all and are refused
    by the `except` below, while the week and basic formats parse fine and are
    refused only by the comparison. Test a change to this function with a value
    from the SECOND group; the first group stays refused with the guard deleted.

    The round-trip comparison IS the grammar rule, and deliberately so: no regex
    (`re` is not imported in this module and should not start to be for one
    field) and no `strptime`, whose `%Y`/`%m`/`%d` match Unicode decimal digits
    and unpadded numbers — it would accept `'٢٠٢٦-٠١-٠١'` and `'2026-1-1'`, the
    two spellings this exists to refuse. `date.isoformat()` always prints exactly
    zero-padded `YYYY-MM-DD` for a year of four digits, so requiring the parse to
    print back what was given admits every canonical spelling and no other: the
    wider grammars parse to a date whose canonical form is a DIFFERENT string.
    Years below 1000 (`'0999-01-01'`, `'0001-01-01'`) round-trip and stay
    accepted, because they were already accepted and narrowing the range would be
    a new business rule rather than the parity this closes. That is deliberate
    and it costs nothing: MariaDB's `1000-01-01` floor is the range its `DATE`
    type is DOCUMENTED to support, not one it enforces — 11.8 under
    `STRICT_TRANS_TABLES` stores `'0999-01-01'` and `'0001-01-01'` and reads them
    back with no error and no warning. So unlike `_purchase_unit_price`'s
    `DECIMAL(10,2)` bound and the `quantity` ceiling, which guard real column
    limits, there is no production failure here for a year bound to prevent, and
    stating one would refuse a value the database stores.

    It strips because the form always did and the endpoint never did, which is
    the whole of DW-191: `' 2026-01-01 '` was a 302 and a stored row through the
    form and a 400 through the endpoint, for a value both agree means the same
    day. Stripping here — before the round-trip comparison, so the padding is
    gone by the time canonicity is judged — is what makes the two answers one
    answer, and it also lets a padded pair reach `_purchase_date_order_error` as
    dates rather than dying as a format error first.

    A non-`str` is refused rather than `str()`-coerced. The coercion is what let
    the JSON integer `20260101` be stored as a date the caller never spelled, and
    a JSON number is not a date in any spelling; `_purchase_text_length_error`
    makes the mirror-image choice for the same reason (it counts characters, so a
    non-string is not its business). Absence is decided BEFORE the type check, so
    `None` still means "no date given" rather than becoming a refusal.

    Absent stays absent, and three things spell it: `None`, `''` and a
    whitespace-only string. All three return `(None, None)` — every Purchase
    column is nullable (FR61) and a blank `order_date` is filled with today by
    the service (DW-192), so "no date" is a valid request, not a bad one.

    The human-labelled sentence is returned as-is and `api_record_purchase`
    renders it verbatim, exactly as it already does for `_purchase_unit_price`
    and `_purchase_text_length_error`: AD-13's `field` already carries the
    machine name a client keys on, and a second message string differing only in
    case is precisely the divergence sharing a helper removes (the endpoint's own
    sentence used to be `'order_date must be an ISO date (YYYY-MM-DD)'`, without
    the period).

    That message change is not the only break for JSON callers, and the smaller
    half of it. Three input classes flipped verdict too: `20260101` (the integer),
    `'20260101'` and `'2026-W01-1'` each used to answer 201 and store a row and
    now answer 400, while `'   '` used to answer 400 and now answers 201, storing
    a purchase dated today. `ApiClient.record_purchase` (app/api_client.py)
    forwards a caller's dict verbatim, so an integration spelling a date in
    compact form or as a number starts failing with no change on its side — which
    is the point: those rows were the defect, not the contract.
    """
    # The label lookup is unconditional, like `_purchase_text_length_error`'s:
    # an unmapped column name is a programming error and must fail the same way
    # whether or not a value happened to be supplied, rather than passing
    # silently on `None` and raising `KeyError` — a 500 outside the AD-13
    # envelope — the first time someone fills the field in.
    label = _PURCHASE_DATE_LABELS[name]
    # Before the type check: `None` is not a bad date, it is no date.
    if value is None:
        return None, None
    # One string for every way a value fails to be a `YYYY-MM-DD` date, on the
    # same reasoning as `_purchase_unit_price`'s single `not_a_number`: the
    # operator's fix is the same in all of them, and the message states the
    # requirement rather than the diagnosis.
    message = f'{label} must be an ISO date (YYYY-MM-DD).'
    if not isinstance(value, str):
        return None, message
    text = value.strip()
    if not text:
        return None, None
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None, message
    if parsed.isoformat() != text:
        return None, message
    return parsed, None


def _purchase_date_order_error(order_date, received_date):
    """The out-of-order message for a purchase's date pair, or `None` — the
    third rule both entry points share (DW-24).

    Unlike the other two helpers this is not a column bound; nothing in
    `purchases` can express "received on or after ordered", so both entry points
    validated each date's format independently and neither ever compared them.
    The rule lives beside them rather than in the service for the same reason
    they do: `record_purchase` validates nothing by design, so
    `_parse_purchase_form` and `api_record_purchase` are the two HTTP gates in
    front of it. They are not the only writers — `record_amazon_purchase` takes
    both dates and, exactly like the price rule, does NOT inherit this one; the
    day it gets a route, the rule has to be applied there too.

    The arguments are already-parsed `date` values, not the raw strings, which
    is what makes the interaction with the format rules resolve itself: an
    unparseable date is `None` on the form side and has already short-circuited
    the request on the JSON side, so this is never reached with a non-date and a
    malformed date reports only its own format message. Both entry points now
    reach this through the same parse, `_purchase_date`, which gave the FORMAT
    rule the single definition the other columns already had — so the padding
    divergence (DW-191) and the over-wide ISO grammar (DW-88) that used to sit
    under this rule are closed, and a padded pair is compared as the two dates it
    spells rather than refused by one side as a format error.

    Falsy on either side means the pair is accepted. A `received_date` with no
    `order_date` is left alone even though `record_purchase` then defaults
    `order_date` to `date.today()` (mariadb_catalog_service.py) and can store a
    row where received precedes order: refusing that — or replicating the
    default here to compare against — would be a broader rule than the one
    decided. The comparison is `<`, so equal dates are accepted: the rule is
    "must not precede", not "must follow".
    """
    if order_date and received_date and received_date < order_date:
        return 'Received Date must not be earlier than Order Date.'
    return None


def _parse_purchase_form(form_data):
    """Parse the HTML purchase form into the typed values the service takes.

    Returns `(values, errors)`. The bounds on `unit_price` and on the text
    columns live in `_purchase_unit_price` and `_purchase_text_length_error`,
    the dates' own FORMAT rule in `_purchase_date`, and the one cross-field
    rule — a `received_date` may not precede its `order_date` — in
    `_purchase_date_order_error`; `api_record_purchase` applies all four, so the
    two entry points cannot come to disagree about them; the only difference is
    the shape of the refusal (a field message on a re-render rather than the
    AD-13 JSON envelope).

    `quantity` is deliberately NOT shared, and the two entry points do still
    differ on it: the JSON endpoint's shipped contract takes a JSON integer,
    while this rule takes the string a form field carries. `int()` is not the
    "whole number" the message promises — `int('1_0')` is 10 and `int('٥')` is
    5 — so `_positive_int_string` is the rule as stated here, and it also bounds
    the value to the 32-bit column.
    """
    errors = {}
    # The text columns this form carries and the text columns it bounds are the
    # same columns, so both come from `_PURCHASE_FIELD_LIMITS` rather than from
    # a tuple restating its keys. A restated tuple could only drift: a column
    # added to `_RECEIPT_FIELD_LIMITS` would be bounded by `api_record_purchase`
    # (which reads the mapping) and silently neither parsed nor bounded here —
    # a divergence of exactly the kind sharing the helpers removes.
    values = {name: ((form_data.get(name) or '').strip() or None)
              for name in _PURCHASE_FIELD_LIMITS}
    for name in _PURCHASE_FIELD_LIMITS:
        message = _purchase_text_length_error(name, values[name])
        if message:
            errors[name] = message

    raw_price = (form_data.get('unit_price') or '').strip()
    values['unit_price'] = None
    if raw_price:
        parsed_price, message = _purchase_unit_price(raw_price)
        if message:
            errors['unit_price'] = message
        else:
            values['unit_price'] = parsed_price

    raw_quantity = (form_data.get('quantity') or '').strip()
    values['quantity'] = None
    if raw_quantity:
        parsed_quantity = _positive_int_string(raw_quantity)
        if parsed_quantity is None:
            errors['quantity'] = (
                f'Quantity must be a whole number greater than zero and no '
                f'more than {_MAX_INT32}.')
        else:
            values['quantity'] = parsed_quantity

    # Both date columns and their labels come from `_PURCHASE_DATE_LABELS`, for
    # the reason given on that mapping; the strip and the label wording this loop
    # used to carry itself now live inside the helper, so the endpoint gets both.
    for name in _PURCHASE_DATE_LABELS:
        values[name], message = _purchase_date(name, form_data.get(name))
        if message:
            errors[name] = message

    # After the loop, so a date that failed to parse is `None` here and gets its
    # own format message rather than also being called out of order — the two
    # would otherwise contend for this very key.
    message = _purchase_date_order_error(values['order_date'],
                                         values['received_date'])
    if message:
        errors['received_date'] = message

    return values, errors


@bp.route('/products/<int:product_id>/purchases/add', methods=['GET', 'POST'])
def purchase_add(product_id):
    """Record a Purchase against a Product from the UI (Story 4.5, FR41).

    The HTML counterpart of `api_record_purchase`, which is untouched and keeps
    its own JSON contract. This is where a matched scan's "Add a purchase"
    banner link lands: an ordinary CSRF-protected form, pre-filled on GET from
    the scan's `request.args` and every value editable.
    """
    service = _get_catalog_service()
    product = service.get_product(product_id)
    if product is None:
        abort(404)

    def _render(form_data, validation_errors):
        return render_template('product/purchase_add.html',
                               title=f'Add Purchase — {product.description or product_id}',
                               product=product, form_data=form_data,
                               validation_errors=validation_errors)

    if request.method == 'GET':
        return _render({name: (request.args.get(name) or '')
                        for name in _PURCHASE_FORM_FIELDS}, {})

    form_data = request.form.to_dict()
    log_audit_operation('purchase_add', 'input', item_id=str(product_id),
                        form_data=form_data)

    values, validation_errors = _parse_purchase_form(form_data)
    if validation_errors:
        return _render(form_data, validation_errors)

    try:
        snapshot = service.record_purchase(product_id, **values)
    except Exception as e:
        # `record_purchase` PROMISES not to raise — it returns None — and
        # `_record_first_receipt` guards the same call anyway, for the same
        # reason it applies here with more force: this page is where a matched
        # scan's banner lands, so an escaped exception is the HTML 500 that
        # `api_scan` and `product_search` both go out of their way to avoid,
        # reached one click after the scan text is gone from the field.
        current_app.logger.error(
            f'Error recording purchase for product {product_id}: {e}\n'
            f'{traceback.format_exc()}')
        snapshot = None
    if snapshot is None:
        flash('Failed to record the purchase. Please try again.', 'error')
        return _render(form_data, {})

    flash('Purchase recorded.', 'success')
    return redirect(url_for('main.product_detail', product_id=product_id))


@bp.route('/products/<int:product_id>/attachments', methods=['POST'])
def product_upload_attachment(product_id):
    """Upload a file attachment to a Product (browser multipart form, CSRF-protected)."""
    service = _get_catalog_service()
    if service.get_product(product_id) is None:
        abort(404)

    file = request.files.get('file')
    if file is None or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('main.product_detail', product_id=product_id))

    try:
        service.add_attachment(
            product_id=product_id,
            filename=file.filename,
            content=file.read(),
            content_type=file.content_type,
        )
        flash('Attachment uploaded.', 'success')
    except ValidationError as e:
        flash(str(e), 'error')
    except Exception as e:
        current_app.logger.error(f'Error uploading attachment for product {product_id}: {e}\n{traceback.format_exc()}')
        flash('An error occurred while uploading the attachment.', 'error')
    return redirect(url_for('main.product_detail', product_id=product_id))


@bp.route('/attachments/<int:attachment_id>')
def serve_attachment(attachment_id):
    """Serve an attachment's bytes (FR5). Inline-safe: the content-type
    whitelist admits only PDF/raster images (no HTML/SVG)."""
    import io
    service = _get_catalog_service()
    result = service.get_attachment_data(attachment_id)
    if result is None:
        abort(404)
    content, content_type, filename = result
    response = send_file(io.BytesIO(content), mimetype=content_type,
                         as_attachment=False, download_name=filename)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def _catalog_json_error(code, message, status, field=None):
    """Build the fixed catalog JSON error envelope (AD-13): an OBJECT error,
    unlike the legacy inventory routes' string `error`. Reused by all catalog
    JSON endpoints (Epic 7 onward)."""
    error = {'code': code, 'message': message}
    if field:
        error['field'] = field
    return jsonify({'success': False, 'error': error}), status


@bp.route('/api/products/<int:product_id>/purchases', methods=['POST'])
@csrf.exempt
def api_record_purchase(product_id):
    """Record a Purchase against an existing Product (FR22). JSON API."""
    service = _get_catalog_service()
    if service.get_product(product_id) is None:
        return _catalog_json_error('not_found', f'Product {product_id} not found', 404)

    # The decoded body must be a JSON OBJECT, and anything else is refused here
    # rather than coerced into one. `api_scan` does coerce (it turns a non-dict
    # body into `{}`), and that is right THERE because an absent `raw` is itself
    # a refusal one line later, so the coercion only picks the message. Here it
    # would decide whether a ROW IS WRITTEN: every field of a purchase is
    # optional, so `{}` is a valid request that records a Purchase — one with no
    # values of its own except the `order_date` `record_purchase` defaults to
    # today — and coercing `[1, 2]`, `"hello"`, `5`, `null`, bytes that are not
    # JSON, or no body at all would record a purchase the caller never
    # described. That is DW-90: the array/string/number cases reached
    # `body.get(...)` and came back as an `AttributeError` 500, outside the
    # AD-13 envelope this endpoint otherwise honors, and the rest answered 201.
    # The architecture spine's "API success" row still gives `request.get_json()
    # or {}` as the shorthand for reading a body; it predates an endpoint whose
    # fields are all optional, where that shorthand is what writes the row.
    #
    # The shipped `or {}` could not be kept in front of this check: `[] or {}`
    # and `0 or {}` are both `{}`, so two of the very bodies being refused would
    # have been rewritten into a valid one before `isinstance` ever saw them.
    #
    # ONE message for every way a body fails to arrive as an object, on the same
    # reasoning as `_purchase_unit_price`'s single `not_a_number` string: the
    # caller's fix is the same in all of them, and `silent=True` collapses them
    # into the same `None` anyway. So it states the requirement rather than the
    # diagnosis, and states the whole of it — a wrong or absent content type
    # lands here too, a perfectly good object sent as `text/plain` included
    # (before this it answered 201 with every field silently dropped). The one
    # arrival that surprises: a well-formed object carrying an integer literal
    # longer than `sys.get_int_max_str_digits()`, which CPython refuses to parse
    # at all, so `json` raises and this refusal answers for it rather than the
    # `quantity` one. That limit is 4300 by DEFAULT and is per-process settable
    # (`PYTHONINTMAXSTRDIGITS`, `-X int_max_str_digits`), so the digit count is
    # the interpreter's business and not a number this route promises. It is the
    # same cap `_positive_int_string` documents for the form — where the comment
    # misnames it `sys.int_info.str_digits_check_threshold`, which is 640: the
    # FLOOR `set_int_max_str_digits` accepts, not the parse limit.
    #
    # The decoded type is logged so an operator integrating a client has
    # something to go on, but it separates less than it looks like: only the
    # bodies `get_json` DID decode — a list, a string, a number — are told apart.
    # No body, a literal `null`, unparseable bytes, a non-JSON content type and
    # the over-long literal above all decode to `None` and emit the same line.
    # That is the price of `silent=True`, and the same conflation the single
    # message makes. What would discriminate them is `request.content_type` and
    # whether any body bytes arrived — both client-supplied and unbounded, on a
    # route that is `@csrf.exempt` and unthrottled, which is exactly why the log
    # carries a type name instead: bounded by construction, like the body is not.
    #
    # `field` is deliberately not passed: AD-13's `field` names a JSON key, and
    # a body that is not an object has no key to name.
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        current_app.logger.warning(
            'Purchase rejected: body decoded to %s, not a JSON object',
            type(body).__name__)
        return _catalog_json_error(
            'invalid_request',
            'Request body must be a JSON object sent as application/json.', 400)

    # Parse/validate typed fields at the boundary; the service takes typed values.
    # `unit_price` and the four text columns are bounded by the same two helpers
    # the HTML form applies (`_parse_purchase_form`), each date's FORMAT by a
    # third, `_purchase_date`, and the ORDER of the pair by a fourth,
    # `_purchase_date_order_error`, so the two entry points cannot disagree about
    # THOSE rules; only the shape of the refusal differs. `quantity` below is
    # deliberately not shared — see that function's docstring — and is now the
    # only column here that is not. The helpers' human-readable message is reused
    # verbatim: `error.field` already carries the machine name a client keys on,
    # and a second message string is exactly the divergence sharing them avoids.
    # That reuse is what changed the two date refusals from the lowercase
    # `'order_date must be an ISO date (YYYY-MM-DD)'` this endpoint used to spell
    # itself to the form's labelled sentence (DW-88/DW-191).
    #
    # First failure wins, and the text columns are judged first, so a body with
    # several bad fields names the earliest one in `_PURCHASE_FIELD_LIMITS`.
    # AD-13's envelope carries one `field`; the caller fixes and re-POSTs. The
    # cross-field date rule is judged last of all, because it needs both dates
    # parsed and must not pre-empt either one's own format message.
    for name in _PURCHASE_FIELD_LIMITS:
        message = _purchase_text_length_error(name, body.get(name))
        if message:
            return _catalog_json_error('invalid_field', message, 400, field=name)

    # Strings are stripped first so a whitespace-only price means "no price"
    # here as it does on the form, rather than reaching `Decimal` as garbage.
    raw_price = body.get('unit_price')
    if isinstance(raw_price, str):
        raw_price = raw_price.strip()
    unit_price = None
    if raw_price not in (None, ''):
        unit_price, message = _purchase_unit_price(raw_price)
        if message:
            return _catalog_json_error('invalid_field', message, 400, field='unit_price')

    # `OverflowError` is caught alongside the other two because it is neither of
    # them: `json.loads` decodes `1e400` to `float('inf')`, and `int(inf)` raises
    # `OverflowError`, which escaped this handler entirely and reached the
    # generic 500 below naming no field. A number the client can spell in JSON
    # but Python cannot make an int of is an unparseable quantity like any other.
    try:
        quantity = body.get('quantity')
        quantity = int(quantity) if quantity not in (None, '') else None
    except (TypeError, ValueError, OverflowError):
        return _catalog_json_error('invalid_field', 'quantity must be an integer', 400, field='quantity')

    # The bound is the COLUMN's, applied to the PARSED int. `Purchase.quantity`
    # is an INTEGER, which MariaDB stores in 32 bits, so `2147483648` and up
    # cannot be stored at all: the write failed and the caller got the generic
    # `server_error` 500 naming no field — the DW-25 symptom every other column
    # on this endpoint no longer has (DW-86). The unit suite cannot see any of
    # that, because it runs on SQLite, which widens INTEGER silently and stores
    # the value happily; a green suite therefore proves less than it appears to
    # for this column, which is exactly why the bound is stated here rather than
    # left to the backend. `0` and `-3` fail the same expression for a different
    # reason: they are not quantities of anything, and no backend was ever going
    # to object to them, so they were stored as typed.
    #
    # The parse above deliberately is NOT the form's `_positive_int_string`.
    # That helper takes the raw string a form field always is and admits ASCII
    # digits only; this endpoint's shipped contract accepts both the JSON int
    # `5` and the string `"5"`, so reusing it would break callers. Bounding the
    # parsed value is what lets the two entry points share the column's rule
    # without sharing a parser that cannot be shared.
    #
    # What this does NOT add is a "whole number" rule. `int()` still coerces
    # `3.7` to 3, `True` to 1 and `'٥'` to 5, and all three still answer 201 —
    # that is `int()`'s lenience, the counterpart of `Decimal`'s on the price
    # (DW-89), and narrowing it would be a new business rule rather than the
    # bound this closes. Keeping it does move two values across the line, since
    # the bound judges what `int()` returned: `False` and any fraction under 1
    # (`0.5`) truncate to 0 and are refused as the zero they became, where they
    # used to be stored as 0. So the message does NOT reuse the form's sentence
    # ("Quantity must be a whole number greater than zero and no more than
    # 2147483647"): that sentence promises a rule this endpoint does not apply,
    # and 0.5 is not in fact "not greater than 0" until `int()` has had it. It
    # says only what is enforced here, in the lowercase machine-facing wording
    # of the `'quantity must be an integer'` message just above it.
    if quantity is not None and not 0 < quantity <= _MAX_INT32:
        return _catalog_json_error(
            'invalid_field',
            f'quantity must be greater than 0 and no more than {_MAX_INT32}',
            400, field='quantity')

    # Over `_PURCHASE_DATE_LABELS` rather than two hand-written calls, for the
    # reason the text columns above are judged by a loop over
    # `_PURCHASE_FIELD_LIMITS`: the set of columns this route JUDGES is then the
    # same set the form judges, by construction, so neither entry point can come
    # to apply the format rule to a column the other skips.
    #
    # That is all it buys, and the limit is worth naming: the mapping is not an
    # extension point. A third date column added to it would be parsed here and
    # then dropped, because the `record_purchase` call below names `order_date`
    # and `received_date` individually — and it would not reach the form's
    # render or pre-fill either, which read `_PURCHASE_FORM_FIELDS`. Adding a
    # date column means touching all three; see the deferred-work ledger.
    #
    # Insertion order is the judging order, so `order_date` still answers first
    # when both dates are malformed (pinned by
    # `TestTheJsonEndpointJudgesTheDatesInMappingOrder`).
    dates = {}
    for name in _PURCHASE_DATE_LABELS:
        dates[name], message = _purchase_date(name, body.get(name))
        if message:
            return _catalog_json_error('invalid_field', message, 400,
                                       field=name)
    order_date = dates['order_date']
    received_date = dates['received_date']

    message = _purchase_date_order_error(order_date, received_date)
    if message:
        return _catalog_json_error('invalid_field', message, 400,
                                   field='received_date')

    try:
        snapshot = service.record_purchase(
            product_id,
            vendor=body.get('vendor'),
            vendor_sku=body.get('vendor_sku'),
            order_date=order_date,
            received_date=received_date,
            quantity=quantity,
            unit_price=unit_price,
            order_number=body.get('order_number'),
            source_url=body.get('source_url'),
        )
    except Exception as e:
        current_app.logger.error(f'Error recording purchase for product {product_id}: {e}\n{traceback.format_exc()}')
        return _catalog_json_error('server_error', 'Failed to record purchase', 500)

    if snapshot is None:
        return _catalog_json_error('server_error', 'Failed to record purchase', 500)

    return jsonify({
        'success': True,
        'purchase': snapshot,
        'product_url': url_for('main.product_detail', product_id=product_id),
    }), 201


# How much of a captured scan reaches the log. The endpoint is CSRF-exempt and
# unthrottled, and `repr` of a control-character-heavy payload is several times
# longer than the payload itself, so an unbounded log line is an amplification
# any client can drive. A real payload is well under this.
#
# This one stays here while `MAX_SCAN_LENGTH`/`clean_scan_input` moved to
# `app/utils/scan_input.py`: it bounds what THIS ROUTE writes to its log, it is
# used nowhere else, and it is a property of the logging done here rather than
# of the scan-text rule. Moving it would put a route's log policy in a pure
# util that has no logging.
_SCAN_LOG_CHARS = 512


def _ecia_prefill(classification):
    """The create-form values a distributor label pre-fills (Story 4.5, FR39).

    Every value is taken from a `.strip()`ed copy of `ecia_fields`. The parser
    keeps values exactly as the label printed them — which is right for a parser
    — but a padded part number saved into `products.mpn` would carry its padding
    into every later search, export and equivalence comparison, so the trim
    happens here, at the first boundary that has any business removing it --
    the label prints the padding and `ecia.parse_fields` preserves it, both
    correctly. Not the only trim: `_clean` strips again at the write path
    (DW-7), so a padded value that never came through this form still stores
    trimmed. What this boundary uniquely owns is that the form the operator is
    HANDED already shows the clean value, rather than one silently corrected
    on save.

    - `mpn` <- the first non-blank of `1P` (the supplier part number, which the
      ECIA spec makes the required field) then `P`. Which of the two a given
      distributor prints the manufacturer part number in is a property of that
      label, so neither is hard-coded as "the MPN".
    - `vendor_sku` <- `P`, but only when `P` was not the value used for `mpn`.
    - `quantity` <- `Q`, as the scanned string and ONLY when that string is a
      positive whole number the form will accept. `Q0` and a scaled quantity
      like `1.5K` are real on real labels, and pre-filling either would hand
      the operator a validation error on a field they never typed; leaving it
      blank asks them for the one value the label did not plainly state.
    - `order_number` <- the first non-blank of `K` then `1K`.

    Deliberately NOT pre-filled: `9D`/`10D`. They are `YYWW` — a week, with no
    day in it — so nothing is written into `order_date` or `received_date`.
    """
    fields = {key: (value or '').strip()
              for key, value in (classification.ecia_fields or {}).items()}
    values = {}
    supplier = fields.get('1P') or ''
    customer = fields.get('P') or ''
    mpn = supplier or customer
    if mpn:
        values['mpn'] = mpn
    if customer and customer != mpn:
        values['vendor_sku'] = customer
    if _positive_int_string(fields.get('Q')) is not None:
        values['quantity'] = fields['Q']
    order_number = (fields.get('K') or '') or (fields.get('1K') or '')
    if order_number:
        values['order_number'] = order_number
    return values


def _scan_prefill_args(classification):
    """The create-form pre-fill one classified scan implies (FR39/FR40).

    `identifier_type`/`identifier_value` are emitted for `gtin` and for nothing
    else: `INTERNAL` is refused by `add_identifier`, an ECIA part number belongs
    in the free `products.mpn` column rather than in a globally-unique `MPN`
    identifier row that two genuinely distinct products would collide on, and
    free text offers no type to infer. Where no type can be inferred the raw
    scan is preserved in `description`, so the scan is never lost.

    That last rule is why an ECIA envelope that names no PART falls back to the
    same `description`, keeping whatever else it carried. A label with only date
    identifiers (`9D`/`10D`, deliberately not coerced) pre-fills nothing at all,
    and one with only a `Q` or a `K` pre-fills a quantity or an order number and
    leaves `description` — the one REQUIRED field on the form — blank, with the
    scanned text nowhere on the page. Both lose the scan, which is what FR40
    forbids; the test for the first shape must not be read as covering the rule.
    """
    kind = classification.kind
    if kind is ScanKind.GTIN:
        return {'identifier_type': IdentifierType.GTIN.value,
                'identifier_value': classification.normalized_value}
    if kind is ScanKind.ECIA:
        prefill = _ecia_prefill(classification)
        if prefill.get('mpn'):
            return prefill
        # No part number — `_ecia_prefill` sets `mpn` from the first non-blank of
        # `1P`/`P` and `vendor_sku` only alongside it, so a missing `mpn` means
        # the envelope named no part at all. Whatever it DID carry (a quantity,
        # an order number, nothing) is kept, and the raw scan goes into
        # `description` as well: a create form opening with no trace of the label
        # loses the scan, which is what FR40 forbids, and `description` is the
        # one required field on it.
        prefill['description'] = scan_router.strip_aim_prefix(classification.raw)
        return prefill
    return {'description': scan_router.strip_aim_prefix(classification.raw)}


def _scan_banner_args(classification):
    """The `request.args` a matched scan carries onto the product page (FR41).

    `scan_kind` is the lower-case `ScanKind` wire value; `scan_type` is the
    upper-case `IdentifierType` value, because it feeds `identifier_type` on the
    "create a separate product instead" link.
    """
    args = {'scan_kind': classification.kind.value}
    if classification.kind is ScanKind.GTIN:
        args['scan_type'] = IdentifierType.GTIN.value
        args['scan_value'] = classification.normalized_value
    elif classification.kind is ScanKind.INTERNAL:
        # The scan itself, so the "create a separate product instead" link is
        # not the one create form that opens with NOTHING on it. `internal` is
        # the only matching kind that names no identifier and no MPN, and
        # `_scan_prefill_args` puts the same text in `description` when the very
        # same scan matches nothing — the two halves of "the scan is never lost"
        # (FR40) must not disagree on whether it happened to match.
        args['description'] = scan_router.strip_aim_prefix(classification.raw)
    elif classification.kind is ScanKind.ECIA:
        prefill = _ecia_prefill(classification)
        # `mpn` is carried as well as the receipt fields: the detail page puts
        # it on the "create a separate product instead" link, which FR39 names
        # first and which would otherwise open blank on the one field the
        # operator just scanned.
        for name in ('mpn', 'quantity', 'order_number', 'vendor_sku'):
            if prefill.get(name):
                args[name] = prefill[name]
    return args


# `q` is scan text rather than a column value, so its bound comes from the URL
# budget instead. It is set well past every VARCHAR the fallthrough search
# touches, so a scan long enough to be cut here could only have matched through
# `products.notes` (TEXT) — see `_scan_url_value` on why cutting `q` is not the
# harmless truncation it looks like.
#
# This is the CEILING, not the whole rule. A URL that still overruns the
# transport with `q` at 1024 is shrunk again by `_bounded_scan_url` — which
# sheds every pre-fill first and then stops `q` at `_SCAN_URL_Q_FLOOR`, itself
# past that same set of VARCHARs. So the sentence above stays literally true of
# a cut `q` as well, and in every alphabet rather than only in ASCII.
_SCAN_URL_Q_LIMIT = 1024

# Every value a scan-built URL can carry, bounded by the column it targets
# (app/database.py): Product.description/manufacturer/mpn and
# Purchase.vendor/vendor_sku/order_number are VARCHAR(255), Product.category_path
# is VARCHAR(512).
_SCAN_URL_ARG_LIMITS = {
    'description': 255,
    'manufacturer': 255,
    'mpn': 255,
    'category_path': 512,
    'vendor': 255,
    'vendor_sku': 255,
    'order_number': 255,
    'identifier_value': 255,
    'scan_value': 255,
    'quantity': 255,
    'q': _SCAN_URL_Q_LIMIT,
}
_SCAN_URL_DEFAULT_LIMIT = 255


def _without_control_characters(text):
    """C0 controls and DEL replaced by spaces, for anything a human must read.

    A wedge can deliver NUL or a stray RS/GS, and neither an `<input>` nor a
    `<code>` block can render one: the bytes are there, invisible, and the
    operator can neither see nor delete them. A space keeps the boundaries the
    separators marked and is what a human reads off the label.
    """
    return ''.join(' ' if (ord(ch) < 0x20 or ord(ch) == 0x7f) else ch
                   for ch in str(text))


def _scan_url_value(name, value):
    """One scan-derived value, made safe to hand to `url_for`.

    Two things a raw scan can do to a URL, and both of them here rather than at
    each call site:

    - **Lone surrogates.** A wedge can deliver one (Story 4.1's comments already
      name `'\\ud800ABC'` as a real vector), and werkzeug percent-encodes a
      query value with `errors='strict'`, so an unsanitized surrogate raises
      `UnicodeEncodeError` inside `url_for` — a 500 for a scan `resolve_scan`
      itself handled cleanly, and a dead end the endpoint's whole contract says
      cannot happen. Encoding through UTF-8 with `'replace'` substitutes it.
    - **Length.** `MAX_SCAN_LENGTH` is 4096 and the search arm puts scan text
      into the URL twice, which measured 10-12 KB — past gunicorn's 8190-byte
      request line and nginx's default 8 KB header buffer, so the browser lands
      on a 414 or a 400 instead of on the results page. Each value is capped at
      the column it targets, in characters (what the VARCHAR counts) AND in
      UTF-8 bytes (what the percent-encoding expands), so the whole generated
      URL is bounded regardless of the scanned alphabet.

    Truncation is safe here in a way it would not be on the create form itself:
    this is the pre-fill going OUT, still editable when it lands, and a value
    past the column limit could not have been saved anyway.

    The one place a cap can be more than cosmetic is `q`, and the cost is NOT
    the harmless direction an earlier reading of this claimed. A capped `q` is a
    PREFIX of what the resolver searched, and a substring search on a prefix
    does match a superset — but `search_products` then keeps only the first
    `SEARCH_RESULTS_DEFAULT_LIMIT` (50) rows in ascending `products.id`, so the
    superset's extra LOW-id members can evict the genuine matches entirely. The
    results page would then show 50 products, none of them the ones `hit_count`
    counted. `q` is therefore bounded by the URL budget rather than by a column
    (`_SCAN_URL_Q_LIMIT`), which puts the truncation point past every VARCHAR
    the search touches: a scan long enough to be cut can only have matched
    through `products.notes` (TEXT). That residue is real and is on the ledger;
    it is not claimed away here. `CatalogService.scan_search_text` itself is
    uncapped, so `TestSearchTextAgreesWithTheResolver` still pins the
    derivation rule.

    `_SCAN_URL_Q_LIMIT` is where that cut STARTS, not where it ends.
    `_bounded_scan_url` cuts `q` again when the assembled URL still overruns the
    transport, and on a multi-byte alphabet it always does — 1024 astral
    characters percent-encode to 12288, over budget however much else is
    dropped. That second cut is floored at `_SCAN_URL_Q_FLOOR`, chosen to sit
    past the very same VARCHARs, so the guarantee reads `_SCAN_URL_Q_LIMIT` down
    to `_SCAN_URL_Q_FLOOR` and never below: one interval, identical for ASCII
    and for astral, rather than a truncation point that slides with whatever
    alphabet happened to be on the label.

    Control characters become spaces — in a PRE-FILL, and never in `q`. A wedge
    can deliver NUL or a stray RS/GS, and an `<input>` cannot render one: the
    value would reach `description` (the one required field on the create form)
    carrying bytes the operator can neither see nor delete, and an ECIA envelope
    routed to the create form would run its records together. A space keeps the
    boundaries the separators marked and is what a human reads off the label.

    `q` is exempt because it is the SEARCH TERM: it must stay byte-for-byte the
    text `resolve_scan` searched, or the results page shows a different set from
    the one `hit_count` counted. It is not exempt from being seen — the results
    page echoes it and puts it back in its own search box — so `product_search`
    scrubs it for DISPLAY with `_without_control_characters` and keeps the raw
    value for the query itself. Nothing is lost by the exemption, though the
    reason is not the one an earlier reading gave. Unstorable text is no longer
    refused before the branch — `resolve_scan` guards each arm's own lookup
    binding now, so such a scan does reach `search_products`, which refuses it
    itself (`sql_text.is_storable_text`) and answers `[]` without building a
    pattern. Non-empty hits therefore MEAN the search accepted the text, and a
    `q` is only ever built on the `search` outcome, so a `q` is storable by
    construction. That conclusion is the whole of what the exemption needs, and
    it holds for control characters generally rather than for a particular
    cast of them: `q` is either an ECIA candidate part number, which by the
    format-06 grammar cannot contain a separator (the separators are what
    delimited the records it was read out of), or the AIM-stripped raw scan,
    which can carry ANY storable control character a scanner emits — a stray RS
    or GS included, since text that failed to parse as an envelope is searched
    exactly as it arrived. The conclusion does not rest on which controls turn
    up. What is excluded is exactly the two classes
    `is_storable_text` names — NUL and unpaired surrogates — and those are the
    only ones a scrub would have had to save the query from, since the rest
    reach a LIKE pattern intact and match what they literally say.

    Length is bounded in CHARACTERS only — what the VARCHAR counts. An earlier
    reading also cut each value to its limit in UTF-8 BYTES, which cost nothing
    on an ASCII label but quartered a CJK or emoji value that was comfortably
    inside both its column and the URL budget. Keeping the whole URL under the
    transport's request-line limit is `_bounded_scan_url`'s job, applied once to
    the assembled URL where it can actually be measured.
    """
    text = str(value).encode('utf-8', 'replace').decode('utf-8')
    if name != 'q':
        text = _without_control_characters(text)
    limit = _SCAN_URL_ARG_LIMITS.get(name, _SCAN_URL_DEFAULT_LIMIT)
    return text[:limit]


def _scan_url_args(args):
    """`_scan_url_value` over a whole arg mapping."""
    return {name: _scan_url_value(name, value) for name, value in args.items()}


# `url_for` returns an already-percent-encoded ASCII string, so its length IS
# the length of the request line the browser will send. Bounded below gunicorn's
# 8190-byte limit and nginx's default 8 KB header buffer, with room for the
# scheme, host and the `Cookie` header that rides alongside it.
_MAX_SCAN_URL_CHARS = 7000

# How far down `_bounded_scan_url` may cut `q`, and the one number that has to
# satisfy two unrelated constraints at once. They meet with room to spare rather
# than in conflict:
#
# - From below: 512 is past the largest VARCHAR the fallthrough search touches
#   (255 — `products.description`/`manufacturer`/`mpn` and
#   `product_identifiers.value`; `internal_id` is 32), so DW-17's "a cut `q` can
#   only over-match through `products.notes` (TEXT)" stays literally true of a
#   `q` sitting on the floor.
# - From above: twelve characters is the most one Python character can
#   percent-encode to (4 UTF-8 bytes, each written `%XX`), so a floored `q` is
#   at worst 512 * 12 = 6144 characters; plus `/products/search?q=` that is
#   ~6163, inside `_MAX_SCAN_URL_CHARS`. A `q` on the floor is therefore always
#   transportable on its own, whatever the alphabet.
#
# `_SCAN_URL_Q_LIMIT` itself cannot be the floor: 1024 * 12 is 12288, over
# budget however much else is dropped. One halving is thus the strongest floor
# the transport can actually guarantee, and it is already double the widest
# column — so nothing is bought by going lower.
_SCAN_URL_Q_FLOOR = 512

# The characters werkzeug leaves literal in a query string, so that ranking a
# shrink candidate by cost can measure the cost the URL will ACTUALLY carry.
# `werkzeug.urls._urlencode` is `urlencode(items, safe="!$'()*,/:;?@")`, and
# `urlencode` quotes with `quote_plus` — so a space costs ONE character (`+`)
# and each of those reserved characters costs one, where the obvious
# `quote(value, safe='')` charges three apiece. The gap is the same class of
# error as ranking by character count, not a rounding difference: 255
# characters of ordinary spaced English score 331 under `quote(safe='')` and
# really cost 255, so they outrank — and would be cut instead of — a
# 50-character Cyrillic value that really costs 300.
_URL_QUERY_SAFE = "!$'()*,/:;?@"


def _bounded_scan_url(endpoint, **args):
    """`url_for`, with the assembled URL bounded to what the transport accepts.

    `MAX_SCAN_LENGTH` is 4096 and a scan's text can reach the URL more than once
    (as `q` and again as a pre-fill), which measured 10-12 KB — past gunicorn's
    request line and nginx's header buffer, so the browser would land on a 414
    or a 400 instead of on the destination. That is a scan dead end, which the
    endpoint's whole contract says cannot happen.

    Measured on the finished URL rather than guessed per value: percent-encoding
    expands one character to between one and twelve bytes depending on the
    alphabet, so a per-value byte cap has to assume the worst case for every
    value at once and mangles ordinary non-Latin text to buy a bound it already
    had. Here values are halved until the URL fits, so an alphabet that encodes
    compactly is never charged for one that does not.

    WHICH value is halved is not "the longest", and that obvious rule was the
    bug. The arguments are not interchangeable: every one except `q` is a
    re-editable PRE-FILL, landing in a form field the operator can retype, while
    `q` is the search term the results page is built from — and cutting `q`
    widens the match into a superset that `search_products`'s first-50-by-
    `products.id` window can evict the counted hits out of (`_scan_url_value`
    spells that out). Halving the longest charged the two the same, and on a
    multi-byte alphabet `q` IS the longest, so `q` was cut first and its
    truncation point became a function of the scanned alphabet — ~256 characters
    for astral text — rather than the `_SCAN_URL_Q_LIMIT` the docstrings claim.

    So, two phases. Every non-`q` argument is exhausted first: the COSTLIEST is
    halved, and dropped outright once halving empties it, until either the URL
    fits or nothing is left to shed. Costliest by what the value costs the
    assembled URL (`_URL_QUERY_SAFE`) rather than by character count, because
    the same reason a per-value byte cap was wrong makes a character-count
    ranking wrong here too — and `_scan_url_args` caps every pre-fill at its
    column, so in the shape production actually emits the candidates are
    routinely TIED at 255 characters while costing anywhere from 255 to 3060
    characters of URL. Ranked by characters, `max` breaks that tie by dict order
    and can halve a compact ASCII value to nothing while the astral value that
    caused the overrun is never touched.

    Only then is `q` touched, and it is halved against a floor rather than to
    nothing — `max(len // 2, _SCAN_URL_Q_FLOOR)`, stopping AT the floor instead
    of passing it. A `q` on the floor fits the budget by itself in the worst
    alphabet there is, so the halving never has to choose between the floor and
    the transport, and the promise "`q` is cut to somewhere between
    `_SCAN_URL_Q_LIMIT` and `_SCAN_URL_Q_FLOOR`, never below" holds for every
    alphabet instead of only for ASCII.

    Both loops strictly decrease a non-negative integer each iteration
    (`n // 2 < n` for `n >= 1`; `max(n // 2, floor) < n` for `n > floor`), so
    both terminate on every input. Phase 1's `break` is neither an error path
    nor a rare one: it is the ordinary handoff to phase 2, taken by every
    over-budget search URL carrying nothing but `q` — which is the commonest
    over-budget shape there is. What cannot happen as the constants stand is
    RETURNING an over-budget URL: phase 1 can always shed the pre-fills down to
    the bare path, and phase 2 can always reach a floored `q`, which fits the
    budget on its own in the worst alphabet. Should an edit to those constants
    break that, the function still returns the shortest URL it managed rather
    than raising — an over-long URL is a transport dead end (a 414 or a 400,
    which is what the budget exists to avoid), but an exception inside `url_for`
    is the same dead end reached through a 500, and the shorter URL is at least
    the one with a chance of arriving.

    The `isinstance(value, str)` guard keeps path arguments (`product_detail`'s
    int `product_id`) out of the candidate set: slicing one would build a URL
    for a different product, or for none.
    """
    url = url_for(endpoint, **args)
    while len(url) > _MAX_SCAN_URL_CHARS:
        costliest = max((name for name, value in args.items()
                         if name != 'q' and isinstance(value, str) and value),
                        key=lambda name: len(quote_plus(args[name],
                                                        safe=_URL_QUERY_SAFE)),
                        default=None)
        if costliest is None:
            break
        shrunk = args[costliest][:len(args[costliest]) // 2]
        if shrunk:
            args[costliest] = shrunk
        else:
            del args[costliest]
        url = url_for(endpoint, **args)
    while (len(url) > _MAX_SCAN_URL_CHARS
           and isinstance(args.get('q'), str)
           and len(args['q']) > _SCAN_URL_Q_FLOOR):
        args['q'] = args['q'][:max(len(args['q']) // 2, _SCAN_URL_Q_FLOOR)]
        url = url_for(endpoint, **args)
    return url


def _scan_destination(resolution, service):
    """Map a `ScanResolution` to `(outcome, url)` — the whole routing rule.

    The ONE place the mapping lives (AD-2/AD-5): every URL is built server-side
    with `url_for`, so the URL namespace stays inside the blueprint, every
    routing decision is assertable without a browser, and the client is left
    with a single line of new behavior — follow the URL. If the client branched
    on `kind` to pick a destination, FR36's precedence would exist in two
    languages and Epic 9's handheld view would be a third.

    Three outcomes, decided solely from the resolution, and `url` is always a
    non-empty in-app path — so no scan dead-ends (FR36/FR40):

    - a matched product -> `'product'`, the detail page carrying the arrival
      banner's args,
    - no product but hits -> `'search'`, the results page for the text the
      resolver actually searched,
    - no product and no hits -> `'create'`, the pre-filled create form.

    Only `product.id` is read off the matched row: it is a DETACHED ORM row, so
    a relationship attribute would raise, and the detail page re-fetches through
    `get_product()` as it already does.

    Every value that reaches `url_for` goes through `_scan_url_value` first, so
    no scan can make URL BUILDING the thing that fails (a lone surrogate) or
    produce a URL the transport in front of Flask refuses (an over-long one).

    `service` is the same `CatalogService` that produced `resolution`, and it is
    a parameter rather than a fresh `_get_catalog_service()` so that the routing
    decision stays assertable against whatever service the caller resolved with.
    Only the `search` branch uses it, for `scan_search_text` — the text
    `resolve_scan` actually searched. That used to be re-derived here from the
    classification alone, and could be while the rule was pure; the `ecia` arm's
    per-candidate fallthrough made the winning candidate a function of the
    DATABASE, which no route can compute. So the rule lives in the service now
    and this is its only caller — the direction this repo has repeatedly chosen
    (one LIKE escaper, one format-06 grammar) rather than re-copying a
    service-internal rule with a service argument bolted on.
    """
    classification = resolution.classification
    if resolution.product is not None:
        return 'product', _bounded_scan_url(
            'main.product_detail', product_id=resolution.product.id,
            **_scan_url_args(_scan_banner_args(classification)))

    prefill = _scan_url_args(_scan_prefill_args(classification))
    if resolution.free_text_hits:
        return 'search', _bounded_scan_url(
            'main.product_search',
            q=_scan_url_value('q', service.scan_search_text(resolution)),
            **prefill)
    return 'create', _bounded_scan_url('main.product_add', **prefill)


@bp.route('/api/scan', methods=['POST'])
@csrf.exempt
def api_scan():
    """Receive one keyboard-wedge scan and answer with where it goes (FR36).

    Story 4.5 makes this the router: it validates the payload, applies the
    single whitespace rule above, resolves the cleaned text through
    `CatalogService.resolve_scan()` once, and answers with a six-key envelope
    whose `url` is a server-built in-app path the client simply follows.
    `outcome` is one of `product` / `search` / `create` and `url` is never
    empty, so no scan dead-ends and none reaches an HTML error page.

    `hit_count` is `len(free_text_hits)`, and `free_text_hits` is capped at
    `SEARCH_RESULTS_DEFAULT_LIMIT` (50) by `search_products`. So it is the size
    of the set `/products/search` will show — the page and the count always
    agree with each other — but NEITHER is a count of all matches, and a scan
    reporting 50 may match more. Signalling a truncated result set is
    deferred-work's, and Epic 8's, under AD-17.

    It stays READ-ONLY, deliberately. `resolve_scan` writes nothing: no
    Purchase, no Product, no identifier, no audit mutation. Every mutation this
    story adds sits behind an ordinary, CSRF-protected HTML form POST an
    operator submits — which is what keeps a rescan after the client's 10s
    timeout free rather than a double-apply.

    The `@csrf.exempt` above is inherited from Story 4.1 and is NOT closed by
    that read-only property, because read-only is not the same as cheap: an
    unauthenticated, unthrottled cross-site POST here costs several sessions and
    a leading-wildcard `LIKE` over six unindexed columns with a pattern of up to
    `MAX_SCAN_LENGTH` characters — a full table scan per request. "Several" is
    five in the worst case, which is a two-candidate ECIA envelope routed to
    `search`: `resolve_scan` may issue one lookup and one search per candidate
    (four), and `_scan_destination` then asks `scan_search_text` which candidate
    won, which costs ONE more search — it re-runs every candidate but the last,
    since with hits in hand a last candidate that is reached needs no asking
    (the price of the searched-text rule having ONE home — see that method).
    Every other kind still costs at most two. That is a denial-of-service
    shape, not a one-SELECT shape, and it got worse rather than better here.
    The exemption stays (removing it would break the wedge path this endpoint
    exists for). Do not read the ledger as holding this cost for someone: the
    two entries aimed at this endpoint — the CSRF exemption itself (DW-14) and
    rate limiting (DW-63) — were both CLOSED by human decision on 2026-07-26,
    and DW-14's summary still describes the two-session cost that this change
    raised to five. The larger number is written HERE and nowhere else.

    Errors use the AD-13 object-error envelope exclusively, including a failing
    resolution: a broken `GS1_INTERNAL_*` grammar or a database outage is a 500
    the client toasts, never an HTML error page and never a navigation.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        # A JSON array/scalar body, or no/invalid JSON at all — treated as an
        # absent `raw`, never a 500.
        body = {}

    raw = body.get('raw')
    if not isinstance(raw, str):
        # No coercion: an int, None, or a list is a malformed client, not a scan.
        current_app.logger.warning(
            'Scan rejected: `raw` absent or not a string (got %s)', type(raw).__name__)
        return _catalog_json_error('invalid_field', 'raw must be a string', 400, field='raw')

    # Bound the captured value, before trimming. Note what this does NOT do:
    # the body has already been read and parsed by get_json() above, and len()
    # counts code points rather than bytes, so this is a payload sanity bound,
    # not a transport/memory guard. The transport bound is now a separate,
    # active control: app/request_limits.py caps the request body at
    # MAX_REQUEST_BODY_BYTES (MAX_UPLOAD_BODY_BYTES on the two upload
    # endpoints) at the WSGI layer, so a body over that is a 413 before this
    # view runs at all. The two are additive — the cap stops a body that should
    # never have been buffered, this stops an in-bounds body carrying an
    # implausible `raw`.
    if len(raw) > MAX_SCAN_LENGTH:
        current_app.logger.warning(
            'Scan rejected: %d characters exceeds the %d limit, starts %r',
            len(raw), MAX_SCAN_LENGTH, raw[:_SCAN_LOG_CHARS])
        return _catalog_json_error(
            'invalid_field',
            f'raw must be {MAX_SCAN_LENGTH} characters or fewer',
            400, field='raw')

    cleaned = clean_scan_input(raw)
    if not cleaned:
        # `repr` of what arrived, not just "blank": a scanner that has started
        # emitting only its suffix is one of the two likeliest real faults, and
        # a message with no bytes in it cannot tell that from an empty POST.
        current_app.logger.warning(
            'Scan rejected: blank after trimming %r', raw[:_SCAN_LOG_CHARS])
        return _catalog_json_error('invalid_field', 'raw must not be empty', 400, field='raw')

    try:
        service = _get_catalog_service()
        resolution = service.resolve_scan(cleaned)
        # The same service instance, so the searched text `_scan_destination`
        # asks it for is derived against the database the resolution came from.
        outcome, url = _scan_destination(resolution, service)
    except Exception as e:
        # Every failure here is a deployment or backend fault, not a bad scan:
        # a malformed configured grammar, or the database. It must not reach the
        # operator as an HTML error page (the client is a fetch, not a form),
        # and it must not navigate — the AD-13 envelope makes the client toast
        # it and RETAIN the scanned text for retry.
        current_app.logger.error(
            'Error resolving scan %r: %s\n%s',
            cleaned[:_SCAN_LOG_CHARS], e, traceback.format_exc())
        return _catalog_json_error('server_error', 'Failed to resolve scan', 500)

    # The only server-side record that a scan arrived. Logged at debug because
    # a rapid-scanning operator generates one of these per item; it is the
    # entire diagnostic value of this endpoint when a scanner starts emitting
    # something unexpected. `repr` because the whole question a wedge
    # investigation asks is "which bytes actually arrived" — a bare character
    # count cannot answer it, and control characters would otherwise be
    # invisible in the log. Barcodes here carry no personal data. The length is
    # logged alongside, so a truncated line is recognisable as one.
    current_app.logger.debug(
        'Scan captured: %d characters %r, outcome=%s',
        len(cleaned), cleaned[:_SCAN_LOG_CHARS], outcome)

    return jsonify({
        'success': True,
        'raw': cleaned,
        # The serialization app/models.py predicted this story would add: the
        # lower-case ScanKind wire value, never persisted.
        'kind': resolution.classification.kind.value,
        'outcome': outcome,
        'url': url,
        'hit_count': len(resolution.free_text_hits),
    }), 200


@bp.route('/products/edit/<int:product_id>', methods=['GET', 'POST'])
def product_edit(product_id):
    """Edit a Product from the catalog UI."""
    service = _get_catalog_service()
    product = service.get_product(product_id)
    if product is None:
        abort(404)

    title = f'Edit {product.description or product_id}'

    if request.method == 'GET':
        # Named rather than inlined because the select's selected option is
        # decided from the same mapping (AD-5) and `_selected_stock_status`
        # needs it; building it twice would be two reads of the tag table.
        stored_data = _product_form_data(
            product, service.get_tags_for_product(product_id))
        return render_template(
            'product/edit.html', title=title, product=product,
            form_data=stored_data,
            stock_status_choices=_stock_status_choices(),
            stock_status_selected=_selected_stock_status(
                stored_data, product.stock_status),
            validation_errors={})

    form_data = request.form.to_dict()
    log_audit_operation('product_edit', 'input', item_id=str(product_id),
                        form_data=form_data)

    # What every failure re-render below hands the template: the SUBMITTED
    # values laid over the STORED ones. Submitted wins so in-flight edits
    # survive the error, and `request.form.to_dict()` holds a key for every
    # field the client actually sent — including ones sent empty — so an
    # explicit clear still renders empty while a key the client OMITTED falls
    # through to what a GET would have shown. Without the stored base, a
    # non-browser client that POSTs one field and re-posts the rendered form
    # silently wipes every optional field it never sent (DW-52), because the
    # template renders `value="{{ form_data.get('<field>', '') }}"`.
    #
    # ONLY the render mapping is merged. `update_product` and `_form_tags`
    # below keep reading the unmerged `form_data`, or the partial-update rule
    # this merge exists to protect would itself be broken: every stored value
    # would arrive as a present key and "absent means not provided" would stop
    # meaning anything.
    #
    # A function called at each re-render site rather than a value computed
    # once, because reading the stored baseline is the only service call this
    # POST path did not make before and the COMMON outcome — a save that
    # succeeds — throws the merge away unused. Eager, it spent that read on
    # every edit, and (once the degraded case below had to say so out loud) it
    # would have warned the operator about a re-render that never happened.
    def _render_data():
        # Guarded, because an unguarded failure here would escape as an HTML
        # 500 on a page whose every other failure mode is a flash and a
        # re-render, and it would do so in service of a DISPLAY concern.
        #
        # But the degraded render is not harmless and must not be silent: it
        # shows every omitted field blank, and this form's own rule is that a
        # present-but-empty field CLEARS — so a client that re-posts the page
        # it was handed turns a transient read failure into a wiped
        # manufacturer, mpn, category, notes, tag list, location and
        # sub_location. Story 5.1 added one field to that list that is worse
        # than the rest: a blank `quantity_on_hand` does not merely clear a
        # string, it UNTRACKS the product, nulling `quantity_verified_at` with
        # it — and unlike a retypeable category, the date somebody counted is
        # not recoverable by retyping. Story 5.2's `reorder_threshold` joined
        # the same list (it is in the present-key loop below on the same
        # terms), and it fails QUIETLY where the others fail visibly: the value
        # is retypeable, but nothing on the page afterwards says a threshold
        # used to be there, and the only symptom is a low-stock signal that
        # stops arriving. This list is the durable record of which fields carry
        # that hazard — a field added to the loop below belongs in it.
        # The operator is told so in the one place they are already looking.
        #
        # Story 5.3's `stock_status` is in the loop below and is the one field
        # there this hazard does NOT reach, which is worth stating because the
        # select's failure shape would otherwise be the worst on the form: it
        # has no empty state to degrade into, so a `Not set` it fell back to
        # would look filled rather than blank. It does not fall back. The
        # rendered selection comes from `_selected_stock_status(render_data,
        # product.stock_status)`, and that second argument is read off the
        # `product` this route loaded BEFORE the read that fails here — so the
        # degraded page still marks the STORED status selected, and re-posting
        # the page as handed re-posts the value already stored. That immunity is
        # structural rather than incidental, and it is the reason the fallback
        # must keep coming from `product` rather than from `stored`:
        # `test_an_unreadable_baseline_degrades_instead_of_500ing` asserts the
        # rendered selection, not merely the warning text.
        try:
            stored = _product_form_data(
                product, service.get_tags_for_product(product_id))
        except Exception as e:
            current_app.logger.warning(
                f'Could not read the stored values for product {product_id} to '
                f'seed a re-render: {e}\n{traceback.format_exc()}')
            # Worded for what is actually true of this page: the controls that
            # degrade are the ones seeded from the failed read, and they all
            # degrade to EMPTY. The Stock Status select is deliberately not
            # described here, because it does not degrade at all (see the
            # comment above) — warning about a menu that is in fact correct
            # would spend the operator's attention on the one control that
            # needs none.
            flash('Could not load this product\'s saved values, so a field '
                  'shown empty below may not actually be empty. Check every '
                  'field before saving.', 'warning')
            stored = {}
        return {**stored, **form_data}

    validation_errors = _validate_product_form(form_data)
    if validation_errors:
        # `_render_data()` is called ONCE and named, because the select's
        # selected option is decided from the same merged mapping and a second
        # call would be a second read of the stored row and the tag table.
        # `product.stock_status` is the STORED fallback: this is exactly the
        # re-render where a refused submit could otherwise hand the operator a
        # page whose select silently reads `Not set` over a stored `low`.
        render_data = _render_data()
        return render_template('product/edit.html', title=title, product=product,
                               form_data=render_data,
                               stock_status_choices=_stock_status_choices(),
                               stock_status_selected=_selected_stock_status(
                                   render_data, product.stock_status),
                               validation_errors=validation_errors)

    # Parsed before the write, for the reason product_add gives.
    tags = _form_tags(form_data)

    try:
        # Only update fields actually present in the POST body: an absent key
        # means "not provided", not "clear this" — a present-but-empty field
        # still clears (the service coerces blanks to NULL).
        update_fields = {'description': form_data.get('description')}
        # Story 5.1's three join the list unchanged, and the present-key rule is
        # what gives `quantity_on_hand` its tri-state write: an absent key
        # leaves the count and its verification stamp alone, while a key sent
        # EMPTY clears both (the service's `_apply_quantity_assertion`). A key
        # sent with a NUMBER re-stamps only if it is a real assertion — a
        # changed value, or an unchanged one the operator explicitly recounted.
        # Story 5.2's `reorder_threshold` joins them on the same terms: an
        # absent key leaves the stored threshold alone, a key sent EMPTY clears
        # it to NULL, and a key sent `0` sets a real threshold of zero.
        # Story 5.3's `stock_status` joins on the same terms with one meaning
        # of its own: an absent key leaves the assertion and its date alone,
        # and a PRESENT key is passed through as sent — including a blank,
        # which the service refuses rather than reading as a clear, because
        # this column has no blank state (`unknown` is how "no assertion" is
        # spelled and is a value the select can actually send). Whether the
        # date then moves is the service's assertion rule, not this loop's: the
        # select posts on every save, so presence is a property of the markup
        # rather than of intent.
        for field in ('manufacturer', 'mpn', 'category_path', 'notes',
                      'quantity_on_hand', 'reorder_threshold', 'stock_status',
                      'location', 'sub_location'):
            if field in form_data:
                update_fields[field] = form_data[field]

        # The recount checkbox (Story 5.1). NOT a field and never in
        # `update_fields`: it is not a column, is never persisted, and only
        # tells the service how to read the quantity that IS in there.
        # `product_add` reads no such key.
        #
        # Present AND non-blank, not merely present. A browser omits an unticked
        # box entirely and sends `on` for a ticked one, so for the form itself
        # the two rules agree — but a JS serializer that posts every control
        # sends `quantity_recounted=` for the unticked box, and reading that as
        # a recount would refresh the verification date of a count nobody took,
        # which is the one thing this whole control exists to prevent. It is
        # also the test `edit.html` itself applies when it decides whether to
        # re-render the box ticked (`{% if form_data.get(...) %}`), so route and
        # template now agree about what the same body means.
        recounted = bool((form_data.get('quantity_recounted') or '').strip())

        ok = service.update_product(product_id,
                                    quantity_recounted=recounted,
                                    **update_fields)
        if not ok:
            flash('Failed to update product. Please try again.', 'error')
            render_data = _render_data()
            return render_template('product/edit.html', title=title, product=product,
                                   form_data=render_data,
                                   stock_status_choices=_stock_status_choices(),
                                   stock_status_selected=_selected_stock_status(
                                       render_data, product.stock_status),
                                   validation_errors={})

        # Post-commit and therefore non-fatal, collected rather than returned
        # early — the same shape and the same reasoning as `product_add`. The
        # row was updated either way, so the success is flashed
        # UNCONDITIONALLY and the failures after it: suppressing it told the
        # operator the edit had failed outright when in fact only the follow-up
        # had, which is the opposite of what the create form said about the
        # identical outcome (DW-30).
        followup_errors = []
        if tags is not None:
            # Present-but-empty clears every tag; an ABSENT key leaves them
            # alone, the same partial-update rule as the fields above.
            tag_error = _apply_product_tags(service, product_id, tags)
            if tag_error:
                followup_errors.append(tag_error)

        flash('Product updated successfully!', 'success')
        for message in followup_errors:
            flash(message, 'error')
        return redirect(url_for('main.product_detail', product_id=product_id))
    except Exception as e:
        current_app.logger.error(f'Error updating product {product_id}: {e}\n{traceback.format_exc()}')
        flash('An error occurred while updating the product. Please try again.', 'error')
        render_data = _render_data()
        return render_template('product/edit.html', title=title, product=product,
                               form_data=render_data,
                               stock_status_choices=_stock_status_choices(),
                               stock_status_selected=_selected_stock_status(
                                   render_data, product.stock_status),
                               validation_errors={})


# ---------------------------------------------------------------------------
# Category management pages (Story 3.2, FR17). The category tree is the
# distinct set of assigned products.category_path values, so these pages are
# views over CatalogService — no ORM here, and every path comparison goes
# through app/utils/category.py rather than a bare startswith (AD-1/AD-2/AD-4).
# ---------------------------------------------------------------------------


def _is_canonical_path(path):
    """
    True when `path` is exactly what normalization would have stored.

    Story 3.1's backfill migration deliberately LEAVES a row it could not
    normalize (a SQLite-era value past 512 characters, or one whose canonical
    form is longer than the original) exactly as it found it, so a stored
    category_path is not guaranteed canonical — while every helper in
    `app/utils/category.py` assumes it is. This is the one guard that keeps
    such a row away from them, asked through the util so no canonicality rule
    is re-derived here (AD-4).
    """
    try:
        return category_util.normalize_category_path(path) == path
    except category_util.InvalidCategoryPathError:
        return False


def _category_tree(service):
    """
    Build the listing's rows: every node of the category tree, including the
    INTERIOR ones no product is filed at directly.

    `list_category_paths()` returns only paths products actually carry, so a
    catalog whose sole product sits at `electronics/power/dc-dc` yields exactly
    one row — and without this, `electronics/power` (the node FR17's own
    acceptance criterion renames) would have no row and therefore no Rename
    link. The interior nodes are recovered with `ancestor_paths`.

    Returns a list of (path, direct_count, subtree_count, is_canonical) sorted
    by SEGMENT, not by byte: plain string ordering sorts `electronics-old`
    between `electronics` and `electronics/power` (because `-` < `/`), tearing
    a parent away from its children on a page that presents itself as a tree.

    `is_canonical` is False only for a legacy row Story 3.1's backfill left in
    place. Such a row is still listed, but it carries no Rename link: the
    rename form normalizes whatever `?path=` it is given, so the link would
    resolve to a DIFFERENT path than the row it sits on — and where that
    normalized path also exists (a stored `Electronics/Power` beside the
    canonical `electronics/power`), submitting the form would rename a
    category the operator never selected.
    """
    assigned = service.list_category_paths()
    direct = {path: count for path, count in assigned}
    nodes = set(direct)
    for path in direct:
        # A non-canonical legacy row is still listed as its own node — this
        # page is where the operator would find it — but it contributes no
        # interior ones: `ancestor_paths('/a/b')` yields an EMPTY ancestor,
        # which `is_descendant_path` then refuses with an
        # InvalidCategoryPathError no handler catches, 500-ing the whole
        # listing. A doubled separator likewise invents a phantom `a/` node
        # beside the real `a`, with its own Rename link.
        if _is_canonical_path(path):
            nodes.update(category_util.ancestor_paths(path))
    rows = [
        (node, direct.get(node, 0),
         sum(count for path, count in assigned
             if category_util.is_descendant_path(path, node)),
         _is_canonical_path(node))
        for node in nodes
    ]
    rows.sort(key=lambda row: row[0].split(category_util.CATEGORY_PATH_SEPARATOR))
    return rows


def _category_rename_preview(service, raw_path):
    """
    Resolve a `?path=` (or posted `old_path`) into what a rename would move.

    Returns (source, affected, total) where `source` is the canonical source
    path or None when the value carries no path at all, `affected` is the list
    of (path, product_count) rows at or under it, and `total` is their product
    count. A zero `total` means the node holds nothing — there is nothing to
    rename.

    The source node itself is ALWAYS listed, even when no product is filed at
    it directly: it is the node being renamed, so a table headed "What Will
    Move" that omits it is silent about the very path the operator named —
    which is exactly the interior-node case FR17's own acceptance criterion
    uses.
    """
    try:
        source = category_util.normalize_category_path(raw_path)
    except category_util.InvalidCategoryPathError:
        # Unstorable, therefore matching no stored path: the same "no such
        # category" answer as any other miss.
        source = None
    if source is None:
        return None, [], 0
    affected = [(path, count) for path, count in service.list_category_paths()
                if category_util.is_descendant_path(path, source)]
    total = sum(count for _, count in affected)
    if total and not any(path == source for path, _ in affected):
        affected.insert(0, (source, 0))
    return source, affected, total


@bp.route('/products/categories')
def category_list():
    """List every category tree node with its product counts (FR17)."""
    service = _get_catalog_service()
    return render_template('product/categories.html', title='Categories',
                           categories=_category_tree(service))


@bp.route('/products/categories/rename', methods=['GET', 'POST'])
def category_rename():
    """Rename a category path, carrying its descendants (FR17).

    The GET previews exactly which paths move and how many products go with
    them — the preview IS the confirmation. The POST hands both values to
    CatalogService, which does the whole subtree in one transaction and
    explains any refusal as a ValidationError.
    """
    service = _get_catalog_service()

    if request.method == 'GET':
        raw_path = request.args.get('path', '')
        if not raw_path.strip():
            # Reached without picking a row (a bookmark, or a hand-typed URL);
            # "no products are filed under ''" would describe the wrong problem.
            flash('Pick a category to rename.', 'error')
            return redirect(url_for('main.category_list'))
        if not _is_canonical_path(raw_path):
            # The preview NORMALIZES whatever it is given and then matches
            # stored paths exactly, so a non-canonical value can only resolve
            # to a different path than the one named — either to nothing (a
            # redirect contradicting the counts the listing just showed) or,
            # where the canonical twin also exists, to a real category the
            # operator never selected, which the POST would then rename. The
            # listing already withholds the link; this refuses the URL.
            flash(f'Category "{raw_path}" is not stored in canonical form, so '
                  f'it cannot be renamed here — refile its products from the '
                  f'product form instead.', 'error')
            return redirect(url_for('main.category_list'))
        source, affected, total = _category_rename_preview(service, raw_path)
        if not total:
            flash(f'No products are filed under category "{raw_path}".', 'error')
            return redirect(url_for('main.category_list'))
        return render_template('product/category_rename.html',
                               title=f'Rename {source}', source=source,
                               affected=affected, total=total, new_path='',
                               error_field=None, error_message=None,
                               preview_failed=False)

    form_data = request.form.to_dict()
    log_audit_operation('category_rename', 'input', form_data=form_data)
    raw_old = form_data.get('old_path', '')
    new_path = form_data.get('new_path', '')

    def _rerender(message, error_field='new_path'):
        preview_failed = False
        try:
            source, affected, total = _category_rename_preview(service, raw_old)
        except Exception:
            # The preview is a second trip to the database, so on a backend
            # failure it fails too — and re-raising here would replace the
            # message the operator needs with a 500 page. The template is told
            # the preview is UNKNOWN rather than empty: rendering "no products
            # are filed under this category" next to a database error would
            # state, as fact, something never established — and read as if the
            # operator's category had vanished.
            source, affected, total = None, [], 0
            preview_failed = True
        return render_template('product/category_rename.html',
                               title=f'Rename {source or raw_old}',
                               source=source or raw_old, affected=affected,
                               total=total, new_path=new_path,
                               error_field=error_field, error_message=message,
                               preview_failed=preview_failed)

    try:
        updated = service.rename_category_path(raw_old, new_path)
    except ValidationError as e:
        # A refused rename re-renders the form with the reason and the typed
        # destination intact; nothing was written (the service is atomic). The
        # service says which value it refused, so the form marks that field
        # rather than always blaming the destination.
        return _rerender(str(e), error_field=e.field or 'new_path')
    except Exception as e:
        current_app.logger.error(f'Error renaming category {raw_old!r}: {e}\n{traceback.format_exc()}')
        return _rerender('An error occurred while renaming the category. '
                         'Please try again.', error_field=None)

    # Both values normalized cleanly (the rename succeeded), so the flash can
    # report the canonical forms actually stored.
    flash(f'Renamed category "{category_util.normalize_category_path(raw_old)}" '
          f'to "{category_util.normalize_category_path(new_path)}" — '
          f'{updated} product(s) updated.', 'success')
    return redirect(url_for('main.category_list'))


# ---------------------------------------------------------------------------
# Tag pages (Story 3.3, FR16). Tags cut ACROSS the category tree, so the filter
# page is the retrieval surface a hierarchy cannot express. There is no tag
# vocabulary table: the vocabulary is the distinct set of assigned tags, so
# these are views over CatalogService — no ORM here, and every tag string goes
# through app/utils/tag.py (AD-1/AD-2/AD-4).
# ---------------------------------------------------------------------------


@bp.route('/products/tags')
def tag_list():
    """List every assigned tag with the number of products carrying it (FR16)."""
    service = _get_catalog_service()
    return render_template('product/tags.html', title='Tags',
                           tags=service.list_tags())


def _tag_rename_preview(service, raw_tag):
    """
    Resolve a `?tag=` (or posted `old_tag`) into what a rename would move.

    Returns (source, total) where `source` is the canonical source tag or None
    when the value carries no usable tag at all, and `total` is how many
    products carry it. A zero `total` means nothing carries the tag — there is
    nothing to rename.

    An UNUSABLE value (over-length, or carrying the `,` separator) is folded
    into that same `(None, 0)` on purpose, but only because every caller has
    already answered it: the GET refuses it by name before reaching here, and
    the POST only gets here to REBUILD the preview beside a message the service
    already produced. Folding it in is what keeps this helper from raising
    InvalidTagError into `_rerender`'s backend-failure handler, where it would
    be reported as "the tag could not be read" — a database problem the
    operator does not have.

    Deliberately thinner than `_category_rename_preview`, and the asymmetry is
    the operation's own: a category rename can enumerate the whole subtree it
    will move because the destination is irrelevant to WHICH rows move, while a
    tag rename's outcome depends on a destination the operator has not typed
    yet. So this previews the source and its count, and the form states the
    merge rule up front rather than inventing a second confirmation step.
    """
    try:
        source = tag_util.normalize_tag(raw_tag)
    except tag_util.InvalidTagError:
        # See the note above: the callers have already distinguished this case,
        # so here it collapses into the same "nothing carries it" shape as any
        # other miss rather than escaping as an exception.
        source = None
    if source is None:
        return None, 0
    # Keyed on the canonical form against `list_tags`, which groups in Python —
    # so this reads the count for THIS tag rather than for whatever the
    # database's collation would have folded onto it.
    return source, dict(service.list_tags()).get(source, 0)


@bp.route('/products/tags/rename', methods=['GET', 'POST'])
def tag_rename():
    """Rename a tag across every product carrying it, merging on collision
    (FR16).

    The GET previews the tag and how many products carry it — the preview IS
    the confirmation. The POST hands both values to CatalogService, which does
    every affected row in one transaction and explains any refusal as a
    ValidationError.

    Unlike the category rename there is no canonicality guard on the way in:
    `product_tags` was created empty and EVERY writer of it normalizes before
    it writes — `set_product_tags`, and now this page's own `rename_tag`, which
    stores the canonical destination and nothing else. So a stored tag is
    canonical by construction and a normalized `?tag=` can only resolve to the
    row it came from. (The claim is about the normalizing, not about there
    being one writer: a second writer that normalizes cannot introduce a
    non-canonical row either.)
    """
    service = _get_catalog_service()

    if request.method == 'GET':
        raw_tag = request.args.get('tag', '')
        if not raw_tag.strip():
            # Reached without picking a row (a bookmark, or a hand-typed URL);
            # "no products carry ''" would describe the wrong problem.
            flash('Pick a tag to rename.', 'error')
            return redirect(url_for('main.tag_list'))
        try:
            tag_util.normalize_tag(raw_tag)
        except tag_util.InvalidTagError:
            # Over-length, or carrying the `,` separator: no stored tag can
            # ever equal it, so the preview below would answer "no products
            # carry it" — true, but a description of the wrong problem. Someone
            # who followed a truncated or hand-edited link would go looking for
            # a tag that vanished instead of for the link that mangled it. Same
            # answer, in the same words, as `tag_filter` gives the same input
            # class just below.
            flash('That is not a usable tag, so nothing could carry it. '
                  'Pick one from the list.', 'error')
            return redirect(url_for('main.tag_list'))
        source, total = _tag_rename_preview(service, raw_tag)
        if not total:
            flash(f'No products carry tag "{raw_tag}".', 'error')
            return redirect(url_for('main.tag_list'))
        return render_template('product/tag_rename.html',
                               title=f'Rename {source}', source=source,
                               total=total, new_tag='', error_field=None,
                               error_message=None, preview_failed=False)

    form_data = request.form.to_dict()
    log_audit_operation('tag_rename', 'input', form_data=form_data)
    raw_old = form_data.get('old_tag', '')
    new_tag = form_data.get('new_tag', '')

    def _rerender(message, error_field='new_tag'):
        preview_failed = False
        try:
            source, total = _tag_rename_preview(service, raw_old)
        except Exception:
            # The preview is a second trip to the database, so on a backend
            # failure it fails too — and re-raising here would replace the
            # message the operator needs with a 500 page. The template is told
            # the count is UNKNOWN rather than zero: rendering "no products
            # carry this tag" next to a database error would state, as fact,
            # something never established — and read as if the operator's tag
            # had vanished.
            source, total = None, 0
            preview_failed = True
        return render_template('product/tag_rename.html',
                               title=f'Rename {source or raw_old}',
                               source=source or raw_old, total=total,
                               new_tag=new_tag, error_field=error_field,
                               error_message=message,
                               preview_failed=preview_failed)

    try:
        renamed, merged = service.rename_tag(raw_old, new_tag)
    except ValidationError as e:
        # A refused rename never writes anything (the service is atomic), but
        # where the operator is sent depends on whether they can DO anything
        # about it, and that is what the refused field says.
        field = e.field or 'new_tag'
        if field == 'old_tag':
            # The source is a HIDDEN input, so re-rendering the form would hand
            # back a page with nothing to correct: resubmitting reproduces the
            # identical refusal forever and the only way out is Cancel. Blank,
            # unusable, or carried by no product — every one of them is a
            # property of a value the form does not let the operator touch, so
            # this goes back to the listing with the reason, exactly as the GET
            # guard already does for the same three inputs. (It also stops the
            # page stating the problem twice: the alert, and the card's "No
            # products carry this tag." underneath it.)
            flash(str(e), 'error')
            return redirect(url_for('main.tag_list'))
        if getattr(e, 'retryable', False):
            # The concurrent-writer race. Nothing about the destination is
            # wrong — the identical submission succeeds once the racing
            # transaction is done — so the input is NOT painted invalid; the
            # message above the form already explains it. Marking it would
            # render the race identically to a permanent collation collision
            # and tell the operator to change a value that was never the
            # problem, which is the same distinction `_apply_product_tags`
            # draws off this flag.
            return _rerender(str(e), error_field=None)
        # A destination refusal the operator CAN act on: re-render with the
        # reason and the typed value intact, marking the field the service
        # named rather than always blaming the destination.
        return _rerender(str(e), error_field=field)
    except Exception as e:
        current_app.logger.error(f'Error renaming tag {raw_old!r}: {e}\n{traceback.format_exc()}')
        return _rerender('An error occurred while renaming the tag. '
                         'Please try again.', error_field=None)

    # Both values normalized cleanly (the rename succeeded), so the flash can
    # report the canonical forms actually stored.
    old_canonical = tag_util.normalize_tag(raw_old)
    new_canonical = tag_util.normalize_tag(new_tag)
    if renamed:
        message = (f'Renamed tag "{old_canonical}" to "{new_canonical}" — '
                   f'{renamed} product(s) updated.')
        if merged:
            # Reported SEPARATELY from the rewrite count, because the two
            # outcomes differ in a way the operator can check: a merged product
            # ends up with ONE new-tag row where it previously carried two
            # tags, so a single "N product(s) updated" would overstate what the
            # tag listing will now show against the destination.
            message += (f' {merged} product(s) already carried '
                        f'"{new_canonical}", so their "{old_canonical}" was '
                        f'merged into it.')
    else:
        # NOTHING was rewritten: every carrying product already had the
        # destination, so the operation was a pure merge and the source tag
        # simply stopped existing. The renamed-count sentence is not merely
        # uninformative here, it is wrong twice over — it leads with "0
        # product(s) updated" and is then contradicted by the merge sentence
        # reporting products that plainly were changed. (A rename where BOTH
        # counts are zero never reaches this line: the service refuses a source
        # no product carries.)
        message = (f'Merged tag "{old_canonical}" into "{new_canonical}" — '
                   f'all {merged} product(s) carrying it already carried '
                   f'"{new_canonical}", so their "{old_canonical}" was dropped '
                   f'rather than rewritten.')
    flash(message, 'success')
    return redirect(url_for('main.tag_list'))


@bp.route('/products/tags/filter')
def tag_filter():
    """List exactly the products carrying one tag, whatever their categories
    (FR16).

    The tag is a QUERY parameter rather than a path segment because a canonical
    tag may contain spaces and `/`. Exactly one tag: multi-tag and combined
    category+tag faceting belong to Epic 8.
    """
    raw_tag = request.args.get('tag', '')
    try:
        tag = tag_util.normalize_tag(raw_tag)
    except tag_util.InvalidTagError:
        # Unstorable (over-length, or carrying the separator), therefore
        # matching no stored tag — but it is a malformed request rather than an
        # empty answer, so it goes back to the listing instead of rendering an
        # empty state under a tag nothing could ever carry. It is named as the
        # unusable tag it is: "pick a tag" would report the wrong problem to
        # someone who followed a truncated or hand-edited link.
        flash('That is not a usable tag, so nothing could carry it. '
              'Pick one from the list.', 'error')
        return redirect(url_for('main.tag_list'))
    if tag is None:
        flash('Pick a tag to filter by.', 'error')
        return redirect(url_for('main.tag_list'))

    products = _get_catalog_service().find_products_by_tag(tag)
    return render_template('product/tag_products.html', title=f'Tag: {tag}',
                           tag=tag, products=products)


@bp.route('/api/items/<ja_id>/duplicate', methods=['POST'])
@csrf.exempt
def duplicate_item(ja_id):
    """Duplicate an inventory item N times with sequential JA IDs"""
    try:
        # Get JSON request data
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        quantity = data.get('quantity', 1)
        save_changes = data.get('save_changes', False)
        updated_fields = data.get('updated_fields', {})

        # Validate quantity
        if not isinstance(quantity, int) or quantity < 1 or quantity > 100:
            return jsonify({'success': False, 'error': 'Quantity must be between 1 and 100'}), 400

        service = _get_inventory_service()

        # Get the source item
        source_item = service.get_item(ja_id)
        if not source_item:
            return jsonify({'success': False, 'error': f'Item {ja_id} not found'}), 404

        # If save_changes is True, update the source item first
        if save_changes and updated_fields:
            updated_fields = _normalize_duplicate_updated_fields(updated_fields)
            for field, value in updated_fields.items():
                if hasattr(source_item, field):
                    setattr(source_item, field, value)
            service.update_item(source_item)
            # Reload the item to get fresh data
            source_item = service.get_item(ja_id)

        # Get next available JA ID via a single SQL aggregate
        next_number = service.get_max_ja_id_number() + 1

        created_ja_ids = []
        photos_copied_per_item = 0  # Track photo count for success message

        # Create N duplicates with sequential JA IDs
        for i in range(quantity):
            new_ja_id = f"JA{next_number:06d}"
            next_number += 1

            # Create duplicate item (copy all fields except JA ID, photos, history)
            from app.database import InventoryItem
            from app.models import Dimensions
            duplicate = InventoryItem()

            # Copy all basic fields
            duplicate.ja_id = new_ja_id
            duplicate.item_type = source_item.item_type
            duplicate.shape = source_item.shape
            duplicate.material = source_item.material

            # Copy dimensions
            if source_item.dimensions:
                duplicate.dimensions = Dimensions(
                    length=source_item.dimensions.length,
                    width=source_item.dimensions.width,
                    thickness=source_item.dimensions.thickness,
                    wall_thickness=source_item.dimensions.wall_thickness,
                    weight=source_item.dimensions.weight
                )

            # Copy thread info
            if source_item.thread:
                # Get the string value from enum if it's an enum, otherwise use as-is
                duplicate.thread_series = source_item.thread.series.value if hasattr(source_item.thread.series, 'value') else source_item.thread.series
                duplicate.thread_handedness = source_item.thread.handedness.value if hasattr(source_item.thread.handedness, 'value') else source_item.thread.handedness
                duplicate.thread_size = source_item.thread.size

            # Copy location
            duplicate.location = source_item.location
            duplicate.sub_location = source_item.sub_location

            # Copy purchase info
            duplicate.purchase_date = source_item.purchase_date
            duplicate.purchase_price = source_item.purchase_price
            duplicate.purchase_location = source_item.purchase_location
            duplicate.vendor = source_item.vendor
            duplicate.vendor_part = source_item.vendor_part

            # Copy notes
            duplicate.notes = source_item.notes

            # Copy original material/thread
            duplicate.original_material = source_item.original_material
            duplicate.original_thread = source_item.original_thread

            # Set precision flag
            duplicate.precision = source_item.precision if hasattr(source_item, 'precision') else False

            # Set as active
            duplicate.active = True

            # Add the duplicate using helper
            duplicate_context = {
                'source_ja_id': ja_id,
                'duplicate_index': i+1,
                'duplicate_total': quantity
            }
            success, created_ja_id, error_msg = _add_item_with_logging(service, duplicate, 'duplicate_item', duplicate_context)

            if success:
                created_ja_ids.append(created_ja_id)

                # Copy photos from source item to duplicate
                try:
                    from app.photo_service import PhotoService
                    with PhotoService(_get_storage_backend()) as photo_service:
                        photo_count = photo_service.copy_photos(ja_id, created_ja_id)
                        if i == 0:  # Store count from first duplicate (all should be same)
                            photos_copied_per_item = photo_count
                        if photo_count > 0:
                            current_app.logger.info(f"Copied {photo_count} photos from {ja_id} to {created_ja_id}")
                            log_audit_operation('copy_photos', 'success',
                                              item_id=created_ja_id,
                                              form_data={'source_ja_id': ja_id, 'photos_copied': photo_count})
                except Exception as photo_error:
                    current_app.logger.warning(f"Failed to copy photos from {ja_id} to {created_ja_id}: {photo_error}")
                    # Don't fail the entire duplication if photo copying fails
            else:
                current_app.logger.error(f'Failed to duplicate item {i+1}/{quantity}: {new_ja_id} - {error_msg}')

        # Return results
        if len(created_ja_ids) == quantity:
            first_id = created_ja_ids[0]
            last_id = created_ja_ids[-1]
            photo_msg = f' {photos_copied_per_item} photos copied to each item.' if photos_copied_per_item > 0 else ''
            return jsonify({
                'success': True,
                'count': len(created_ja_ids),
                'ja_ids': created_ja_ids,
                'message': f'Successfully created {len(created_ja_ids)} duplicate(s): {first_id} - {last_id}.{photo_msg}'
            }), 200
        elif len(created_ja_ids) > 0:
            photo_msg = f' {photos_copied_per_item} photos copied to each successful item.' if photos_copied_per_item > 0 else ''
            return jsonify({
                'success': False,
                'count': len(created_ja_ids),
                'ja_ids': created_ja_ids,
                'error': f'Created {len(created_ja_ids)} of {quantity} duplicates. Some failed.{photo_msg}'
            }), 500
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to create any duplicates'
            }), 500

    except Exception as e:
        current_app.logger.error(f'Error duplicating item {ja_id}: {e}\n{traceback.format_exc()}')
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500

@bp.route('/inventory/view/<ja_id>')
def inventory_view(ja_id):
    """View inventory item details (JSON API for modal)"""
    try:
        service = _get_inventory_service()
        
        item = service.get_item(ja_id)
        if not item:
            return jsonify({'success': False, 'error': f'Item {ja_id} not found.'}), 404

        # Convert item to dictionary for JSON response
        item_dict = item.to_dict()

        # Add thread object for consistency with other API endpoints
        item_dict['thread'] = item.thread.to_dict() if item.thread else None

        # Format dimensions for display
        dimensions = item.dimensions
        formatted_dimensions = {}

        if dimensions.length:
            formatted_dimensions['length'] = f"{dimensions.length}\""
        if dimensions.width:
            formatted_dimensions['width'] = f"{dimensions.width}\""
        if dimensions.thickness:
            formatted_dimensions['thickness'] = f"{dimensions.thickness}\""
        if dimensions.wall_thickness:
            formatted_dimensions['wall_thickness'] = f"{dimensions.wall_thickness}\""
        if dimensions.weight:
            formatted_dimensions['weight'] = f"{dimensions.weight} lbs"

        item_dict['formatted_dimensions'] = formatted_dimensions
        item_dict['display_name'] = item.display_name
        
        return jsonify({'success': True, 'item': item_dict})
        
    except Exception as e:
        current_app.logger.error(f'Error viewing item {ja_id}: {e}\n{traceback.format_exc()}')
        return jsonify({'success': False, 'error': 'An error occurred while loading item details.'}), 500

@bp.route('/inventory/search')
def inventory_search():
    """Advanced search interface"""
    valid_materials = _get_valid_materials()
    return render_template('inventory/search.html', title='Search',
                         ItemType=ItemType, ItemShape=ItemShape, ThreadSeries=ThreadSeries,
                         valid_materials=valid_materials)

@bp.route('/inventory/move', methods=['GET', 'POST'])
def inventory_move():
    """Batch move items interface"""
    if request.method == 'GET':
        return render_template('inventory/move.html', title='Move Items')
    
    # Handle POST request would go here (currently handled by API)
    return redirect(url_for('main.inventory_move'))

@bp.route('/inventory/shorten', methods=['GET', 'POST'])
def inventory_shorten():
    """Shorten items interface"""
    if request.method == 'GET':
        return render_template('inventory/shorten.html', title='Shorten Items')
    
    # Handle POST request for shortening operation
    try:
        # Get form data
        form_data = request.form.to_dict()
        
        # AUDIT: Log shorten operation input
        log_audit_operation('shorten_item', 'input',
                          item_id=form_data.get('source_ja_id'),
                          form_data=form_data)
        
        # Validate required fields
        required_fields = ['source_ja_id', 'new_length', 'confirm_operation']
        missing_fields = [field for field in required_fields if not form_data.get(field)]
        
        if missing_fields:
            error_msg = f'Missing required fields: {", ".join(missing_fields)}'
            # AUDIT: Log validation error
            log_audit_operation('shorten_item', 'error',
                              item_id=form_data.get('source_ja_id'),
                              error_details=error_msg)
            flash(error_msg, 'error')
            return redirect(url_for('main.inventory_shorten'))
        
        if form_data.get('confirm_operation') != 'on':
            error_msg = 'You must confirm the shortening operation'
            # AUDIT: Log validation error
            log_audit_operation('shorten_item', 'error',
                              item_id=form_data.get('source_ja_id'),
                              error_details=error_msg)
            flash(error_msg, 'error')
            return redirect(url_for('main.inventory_shorten'))
        
        # Execute shortening operation
        result = _execute_shortening_operation(form_data)
        
        if result['success']:
            original_length = result.get('original_length')
            new_length = result.get('new_length')
            ja_id = result.get('ja_id')
            
            # AUDIT: Log successful shortening operation
            changes = {
                'length': {'before': original_length, 'after': new_length},
                'operation_type': 'shorten',
                'notes': form_data.get('shortening_notes', ''),
                'cut_date': form_data.get('cut_date', '')
            }
            log_audit_operation('shorten_item', 'success',
                              item_id=ja_id or form_data.get('source_ja_id'),
                              changes=changes)
            
            if original_length and new_length:
                flash(f"Item {ja_id} successfully shortened from {original_length}\" to {new_length}\"! History preserved.", 'success')
            else:
                flash(f"Item {ja_id} successfully shortened! History preserved.", 'success')
            return redirect(url_for('main.inventory_shorten'))
        else:
            # AUDIT: Log failed shortening operation
            log_audit_operation('shorten_item', 'error',
                              item_id=form_data.get('source_ja_id'),
                              error_details=f"Shortening operation failed: {result['error']}")
            flash(f"Shortening failed: {result['error']}", 'error')
            return redirect(url_for('main.inventory_shorten'))
            
    except Exception as e:
        # AUDIT: Log shortening operation exception
        log_audit_operation('shorten_item', 'error',
                          item_id=form_data.get('source_ja_id') if 'form_data' in locals() else None,
                          error_details=f'Exception during shortening: {str(e)}')
        current_app.logger.error(f'Error in shortening operation: {e}\n{traceback.format_exc()}')
        flash('An error occurred during the shortening operation. Please try again.', 'error')
        return redirect(url_for('main.inventory_shorten'))

# API Routes

@bp.route('/api/stats')
def api_stats():
    """API endpoint for dashboard statistics"""
    try:
        from app.mariadb_inventory_service import InventoryService
        
        # Get inventory service
        service = _get_inventory_service()
        
        # For MariaDB service, get counts directly from database to include inactive items
        if isinstance(service, InventoryService):
            from app.database import InventoryItem
            from sqlalchemy import func
            
            session = service.Session()
            try:
                # Get total count (active + inactive)
                total_items = session.query(func.count(InventoryItem.id)).scalar()
                
                # Get active count only
                active_items = session.query(func.count(InventoryItem.id)).filter(
                    InventoryItem.active == True
                ).scalar()
            finally:
                session.close()
        else:
            # Fallback for other service types (e.g., tests)
            items = service.get_all_items()
            total_items = len(items)
            active_items = len([item for item in items if item.active])
        
        return jsonify({
            'success': True,
            'data': {
                'total_items': total_items,
                'active_items': active_items,
                'last_updated': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        current_app.logger.error(f'Error getting dashboard stats: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to load dashboard statistics'
        }), 500

@bp.route('/api/items/<ja_id>/exists')
def check_ja_id_exists(ja_id):
    """Check if a JA ID already exists"""
    try:
        service = _get_inventory_service()
        
        item = service.get_item(ja_id)
        exists = item is not None
        
        return jsonify({
            'success': True,
            'exists': exists,
            'ja_id': ja_id
        })
        
    except Exception as e:
        current_app.logger.error(f'Error checking JA ID {ja_id}: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to check JA ID'
        }), 500

@bp.route('/api/materials/suggestions')
def material_suggestions():
    """Get material suggestions from MariaDB taxonomy"""
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', '10')
    
    try:
        limit = int(limit)
        limit = min(max(limit, 1), 20)  # Clamp between 1 and 20
    except (ValueError, TypeError):
        limit = 10
    
    try:
        # Get all valid materials using the appropriate storage backend
        all_materials = _get_valid_materials()
        
        if not query:
            # Return first N materials if no query
            return jsonify(all_materials[:limit])
        
        # Filter materials based on query (case insensitive)
        query_lower = query.lower()
        suggestions = []
        
        # Exact matches first
        for material in all_materials:
            if material.lower() == query_lower:
                suggestions.insert(0, material)
                break
        
        # Starts with matches
        for material in all_materials:
            if (material.lower().startswith(query_lower) and 
                material not in suggestions):
                suggestions.append(material)
        
        # Contains matches
        for material in all_materials:
            if (query_lower in material.lower() and 
                material not in suggestions):
                suggestions.append(material)
        
        # Return limited results
        return jsonify(suggestions[:limit])
        
    except Exception as e:
        current_app.logger.error(f'Error getting material suggestions for "{query}": {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to get material suggestions'
        }), 500


# The two fields whose vocabulary is drawn from BOTH tables (Story 5.1, FR27).
#
# Not a third dispatch whitelist: these names stay in
# `InventoryService.FIELD_SUGGESTION_COLUMNS` and are still ANSWERED by the item
# service exactly as before. Membership here only adds a second, product-sourced
# query whose ordered result is merged into the first. That is what makes the
# vocabulary bidirectional — a location typed on the product form is offered on
# the item form and vice versa — without either service reaching into the
# other's table, and without `location` appearing in the catalog dispatch map
# where it would REPLACE the item lookup instead of adding to it.
_MERGED_LOCATION_FIELDS = ('location', 'sub_location')


@bp.route('/api/inventory/field-suggestions/<field>')
def inventory_field_suggestions(field):
    """Return distinct existing values for a whitelisted field.

    Used by the Add/Edit Item forms to autocomplete free-form fields
    (Thread Size, Purchase Location, Vendor, Location, Sub-Location), by the
    product form's Category and Tags fields since Stories 3.1/3.3, and by the
    product form's own Location / Sub-Location since Story 5.1.

    ONE endpoint, two sources (AD-14): fields in the catalog whitelist are
    served by CatalogService (products), everything else by InventoryService
    (inventory_items) exactly as before. Catalog-sourced responses carry an
    extra `normalized` key — the canonical form of the query, which the
    autocomplete-with-create UI displays so the browser never reimplements
    normalization. The five pre-existing fields keep byte-identical request
    handling and response bodies, `normalized` included (i.e. absent).

    Story 5.1 adds a THIRD shape for `location` / `sub_location` alone: still
    item-dispatched, still no `normalized` key and still no create affordance,
    but the item answer is merged with a product-sourced one under the same
    ordering rule (`app/utils/suggestion_merge.py`). The response body is
    byte-identical to what those two fields have always returned — same three
    keys — so nothing about the existing consumers changes except that the list
    can now contain a value only a Product carries.
    """
    query = request.args.get('q', '').strip()
    limit_raw = request.args.get('limit', '10')
    location = request.args.get('location', '').strip() or None

    try:
        limit = int(limit_raw)
    except (ValueError, TypeError):
        limit = 10
    limit = min(max(limit, 1), 50)

    is_catalog_field = field in CATALOG_FIELD_SUGGESTION_COLUMNS
    normalized = None

    try:
        if is_catalog_field:
            service = _get_catalog_service()
            suggestions = service.get_field_value_suggestions(
                field,
                query=query or None,
                limit=limit,
            )
            normalized = service.normalize_suggestion_value(field, query)
        else:
            service = _get_inventory_service()
            suggestions = service.get_field_value_suggestions(
                field,
                query=query or None,
                limit=limit,
                location=location,
            )
            if field in _MERGED_LOCATION_FIELDS:
                # Story 5.1 (FR27). Two independent top-`limit` reads under one
                # total order, re-ranked into the top-`limit` of their union —
                # see `merge_suggestions` for why truncating each source first
                # loses nothing. Both are asked for `limit`, not for half of it:
                # either table alone may hold the whole answer.
                #
                # Deliberately inside the same `try`: a catalog failure here is
                # the same kind of failure an item failure is, and it must reach
                # the 500 below rather than be swallowed into a partial list
                # that silently claims the product vocabulary is empty.
                product_suggestions = _get_catalog_service() \
                    .get_product_location_suggestions(
                        field,
                        query=query or None,
                        limit=limit,
                        location=location,
                    )
                suggestions = merge_suggestions(
                    (suggestions, product_suggestions),
                    query=query or None,
                    limit=limit,
                )
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), 400
    except Exception as e:
        current_app.logger.error(
            f'Error getting field suggestions for "{field}": {e}'
        )
        return jsonify({
            'success': False,
            'error': 'Failed to get field suggestions',
        }), 500

    body = {
        'success': True,
        'field': field,
        'suggestions': suggestions,
    }
    if is_catalog_field:
        body['normalized'] = normalized
    return jsonify(body)


def _normalize_taxonomy_aliases(nodes: list[dict[str, Any]]) -> None:
    """Recursively convert each node's ``aliases`` into a list.

    ``get_taxonomy_overview`` passes the raw ``MaterialTaxonomy.aliases``
    column through, which is a comma-separated string (or an empty list
    when null). Mutates ``nodes`` in place so the public API returns
    consistently list-typed aliases.
    """
    for node in nodes:
        aliases = node.get('aliases')
        if isinstance(aliases, str):
            node['aliases'] = [a.strip() for a in aliases.split(',') if a.strip()]
        children = node.get('children')
        if isinstance(children, list):
            _normalize_taxonomy_aliases(children)


@bp.route('/api/taxonomy')
def api_taxonomy():
    """Return the full hierarchical materials taxonomy.

    Reuses the canonical tree builder
    (``MariaDBMaterialsAdminService.get_taxonomy_overview``) that powers
    the admin interface, so callers get the same nested structure:
    categories -> ``children`` (families) -> ``children`` (materials),
    each node carrying ``id``, ``name``, ``level``, ``active``,
    ``notes``, ``sort_order`` (plus ``parent`` on families/materials and
    ``aliases`` on materials).

    Query parameters:
      * ``include_inactive`` (``true``/``false``, default ``false``):
        when true, inactive taxonomy entries are included.
    """
    try:
        from app.mariadb_materials_admin_service import MariaDBMaterialsAdminService

        include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'

        admin_service = MariaDBMaterialsAdminService(_get_storage_backend())
        taxonomy = admin_service.get_taxonomy_overview(include_inactive=include_inactive)

        # Normalize `aliases` into a proper list. The admin service
        # passes the raw MaterialTaxonomy.aliases column through, which
        # is a comma-separated string (or an empty list when null); for
        # this public API we want consistent list-typed aliases.
        _normalize_taxonomy_aliases(taxonomy)

        return jsonify({
            'success': True,
            'taxonomy': taxonomy,
        })

    except Exception as e:
        current_app.logger.error(
            f'Error getting materials taxonomy: {e}\n{traceback.format_exc()}'
        )
        return jsonify({
            'success': False,
            'error': 'Failed to get materials taxonomy'
        }), 500


@bp.route('/api/materials/hierarchy')
def materials_hierarchy():
    """Get hierarchical materials taxonomy.

    Powers the material-selector autocomplete UI
    (``app/static/js/material-selector.js``); its response shape is
    tailored to that frontend. Programmatic clients should prefer the
    general-purpose ``GET /api/taxonomy`` endpoint instead.
    """
    try:
        from app.database import MaterialTaxonomy
        from sqlalchemy.orm import sessionmaker

        # Borrow the app-scoped engine (or the injected test storage's) rather
        # than building a per-request one; the session is closed in `finally`.
        engine = resolve_engine(_get_storage_backend())
        Session = sessionmaker(bind=engine)
        session = Session()

        try:
            # Get all active materials ordered by level and sort order
            all_materials = session.query(MaterialTaxonomy).filter(
                MaterialTaxonomy.active == True
            ).order_by(MaterialTaxonomy.level, MaterialTaxonomy.sort_order, MaterialTaxonomy.name).all()

            # Group materials by level
            categories = [m for m in all_materials if m.level == 1]
            families = [m for m in all_materials if m.level == 2]
            materials = [m for m in all_materials if m.level == 3]

            # Build hierarchical structure
            hierarchy = []

            for category in categories:
                category_families = [f for f in families if f.parent == category.name]
                category_data = {
                    'name': category.name,
                    'level': category.level,
                    'notes': category.notes,
                    'families': []
                }

                for family in category_families:
                    family_materials = [m for m in materials if m.parent == family.name]
                    family_data = {
                        'name': family.name,
                        'level': family.level,
                        'parent': family.parent,
                        'notes': family.notes,
                        'materials': [{'name': m.name, 'level': m.level, 'parent': m.parent, 'aliases': m.aliases, 'notes': m.notes} for m in family_materials]
                    }
                    category_data['families'].append(family_data)

                hierarchy.append(category_data)
        finally:
            session.close()

        return jsonify({
            'success': True,
            'hierarchy': hierarchy,
            'summary': {
                'categories': len(categories),
                'total_families': sum(len(cat['families']) for cat in hierarchy),
                'total_materials': sum(sum(len(fam['materials']) for fam in cat['families']) for cat in hierarchy)
            }
        })
        
    except Exception as e:
        current_app.logger.error(f'Error getting materials hierarchy: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to get materials hierarchy'
        }), 500


@bp.route('/api/validate/type-shape', methods=['POST'])
@csrf.exempt
def validate_type_shape():
    """Validate type-shape combination and return required dimensions"""
    try:
        data = request.get_json() or {}
        item_type_str = data.get('item_type', '').upper()
        shape_str = data.get('shape', '').upper()
        
        if not item_type_str or not shape_str:
            return jsonify({
                'success': False,
                'error': 'item_type and shape are required'
            }), 400
        
        try:
            item_type = ItemType[item_type_str]
            shape = ItemShape[shape_str]
        except KeyError:
            return jsonify({
                'success': False,
                'error': 'Invalid item_type or shape'
            }), 400
        
        is_valid, errors = type_shape_validator.validate_type_shape_combination(item_type, shape)
        
        if is_valid:
            required_dims = type_shape_validator.get_required_dimensions(item_type, shape)
            optional_dims = type_shape_validator.get_optional_dimensions(item_type, shape)
            
            return jsonify({
                'success': True,
                'valid': True,
                'required_dimensions': required_dims,
                'optional_dimensions': optional_dims
            })
        else:
            return jsonify({
                'success': True,
                'valid': False,
                'errors': errors
            })
            
    except Exception as e:
        current_app.logger.error(f'Error validating type-shape: {e}')
        return jsonify({
            'success': False,
            'error': 'Validation failed'
        }), 500

@bp.route('/api/items/<ja_id>')
def get_item_details(ja_id):
    """Get detailed information about an item"""
    try:
        service = _get_inventory_service()
        
        item = service.get_item(ja_id)
        
        if not item:
            return jsonify({
                'success': False,
                'error': 'Item not found'
            }), 404
        
        # Get photo information
        photo_info = _get_photo_info(ja_id)
        
        return jsonify({
            'success': True,
            'item': {
                'ja_id': item.ja_id,
                'display_name': item.display_name,
                'item_type': item.item_type,  # InventoryItem stores as string
                'shape': item.shape,  # InventoryItem stores as string
                'material': item.material,
                'location': item.location,
                'sub_location': item.sub_location,
                'active': item.active,
                'precision': item.precision,
                'dimensions': item.dimensions.to_dict() if item.dimensions else None,
                'photos': photo_info
            }
        })
        
    except Exception as e:
        current_app.logger.error(f'Error getting item details for {ja_id}: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to get item details'
        }), 500

@bp.route('/api/items/<ja_id>/history')
def get_item_history(ja_id):
    """Get historical versions of an item (for multi-row JA IDs)"""
    try:
        service = _get_inventory_service()
        
        # Check if MariaDB service to use history functionality
        if hasattr(service, 'get_item_history'):
            items = service.get_item_history(ja_id)
        else:
            # Fallback for non-MariaDB storage
            item = service.get_item(ja_id)
            items = [item] if item else []
        
        if not items:
            return jsonify({
                'success': False,
                'error': 'No items found for this JA ID'
            }), 404
        
        history_data = []
        for item in items:
            history_data.append({
                'ja_id': item.ja_id,
                'active': item.active,
                'display_name': item.display_name,
                'item_type': item.item_type if item.item_type else None,  # InventoryItem stores as string
                'shape': item.shape if item.shape else None,  # InventoryItem stores as string
                'material': item.material,
                'location': item.location or '',
                'sub_location': item.sub_location or '',
                'dimensions': item.dimensions.to_dict() if item.dimensions else None,
                'date_added': item.date_added.isoformat() if item.date_added else None,
                'last_modified': item.last_modified.isoformat() if item.last_modified else None,
                'notes': item.notes or ''
            })
        
        return jsonify({
            'success': True,
            'ja_id': ja_id,
            'total_items': len(items),
            'active_item_count': sum(1 for item in items if item.active),
            'history': history_data
        })
        
    except Exception as e:
        current_app.logger.error(f'Error getting item history for {ja_id}: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to get item history'
        }), 500

@bp.route('/api/inventory/batch-move', methods=['POST'])
@csrf.exempt
def batch_move_items():
    """Execute batch move of inventory items"""
    try:
        data = request.get_json()
        if not data or 'moves' not in data:
            error_msg = 'Invalid request data'
            # AUDIT: Log input validation error for batch move
            log_audit_batch_operation('batch_move_items', 'error', 
                                    error_details=error_msg)
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400
        
        moves = data['moves']
        if not moves or not isinstance(moves, list):
            error_msg = 'No moves provided'
            # AUDIT: Log input validation error for batch move
            log_audit_batch_operation('batch_move_items', 'error', 
                                    error_details=error_msg)
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400
        
        # AUDIT: Log batch move input phase
        log_audit_batch_operation('batch_move_items', 'input', 
                                batch_data={
                                    'move_count': len(moves),
                                    'moves': moves
                                })
        
        service = _get_inventory_service()
        
        successful_moves = 0
        failed_moves = []
        
        for move in moves:
            ja_id = move.get('ja_id')
            new_location = move.get('new_location')
            new_sub_location = move.get('new_sub_location')

            if not ja_id or not new_location:
                failed_moves.append({
                    'ja_id': ja_id,
                    'error': 'Missing JA ID or location'
                })
                continue

            try:
                # Get the current item
                item = service.get_item(ja_id)
                if not item:
                    failed_moves.append({
                        'ja_id': ja_id,
                        'error': 'Item not found'
                    })
                    continue

                # Store old values for audit logging
                old_location = item.location
                old_sub_location = item.sub_location

                # Update location
                item.location = new_location.strip()

                # Update sub-location with clearing logic:
                # - If new_sub_location is provided and non-empty, set it (stripped)
                # - If new_sub_location is not provided or empty, clear it (set to None)
                if new_sub_location and new_sub_location.strip():
                    item.sub_location = new_sub_location.strip()
                else:
                    item.sub_location = None

                # AUDIT: Log individual move operation input
                log_audit_operation('move_item', 'input',
                                  item_id=ja_id,
                                  form_data={
                                      'ja_id': ja_id,
                                      'new_location': new_location,
                                      'new_sub_location': new_sub_location,
                                      'old_location': old_location,
                                      'old_sub_location': old_sub_location
                                  },
                                  item_before=_item_to_audit_dict(item))

                # Save the updated item
                if service.update_item(item):
                    successful_moves += 1
                    # AUDIT: Log successful individual move with location and sub-location changes
                    changes = {
                        'location': {'before': old_location, 'after': new_location}
                    }
                    # Only log sub_location change if it actually changed
                    if old_sub_location != item.sub_location:
                        changes['sub_location'] = {'before': old_sub_location, 'after': item.sub_location}

                    log_audit_operation('move_item', 'success',
                                      item_id=ja_id,
                                      changes=changes)

                    # Build log message
                    log_msg = f'Moved {ja_id} from "{old_location}" to "{new_location}"'
                    if old_sub_location != item.sub_location:
                        log_msg += f' (sub-location: "{old_sub_location}" -> "{item.sub_location}")'
                    current_app.logger.info(log_msg)
                else:
                    # AUDIT: Log failed individual move
                    log_audit_operation('move_item', 'error',
                                      item_id=ja_id,
                                      error_details='Service update_item returned False')
                    failed_moves.append({
                        'ja_id': ja_id,
                        'error': 'Failed to update item'
                    })
                    
            except Exception as e:
                # AUDIT: Log individual move exception
                import traceback
                tb_str = traceback.format_exc()
                exc_info = traceback.extract_tb(e.__traceback__)[-1] if e.__traceback__ else None
                if exc_info:
                    error_details = f'Exception during move: {type(e).__name__}: {str(e)} at {exc_info.filename}:{exc_info.lineno} in {exc_info.name}(). Traceback: {tb_str}'
                else:
                    error_details = f'Exception during move: {type(e).__name__}: {str(e)}. Traceback: {tb_str}'
                log_audit_operation('move_item', 'error',
                                  item_id=ja_id,
                                  error_details=error_details)
                current_app.logger.error(f'Error moving item {ja_id}: {error_details}')
                failed_moves.append({
                    'ja_id': ja_id,
                    'error': str(e)
                })
        
        # Prepare response
        response_data = {
            'success': len(failed_moves) == 0,
            'moved_count': successful_moves,
            'total_count': len(moves),
            'failed_moves': failed_moves
        }
        
        if len(failed_moves) > 0:
            response_data['error'] = f'{len(failed_moves)} items failed to move'
        
        # AUDIT: Log batch move completion with results
        batch_results = {
            'successful_count': successful_moves,
            'failed_count': len(failed_moves),
            'total_count': len(moves),
            'failed_items': [fm['ja_id'] for fm in failed_moves],
            'overall_success': len(failed_moves) == 0
        }
        log_audit_batch_operation('batch_move_items', 'success', 
                                results=batch_results)
        
        return jsonify(response_data)
        
    except Exception as e:
        # AUDIT: Log batch move exception
        import traceback
        tb_str = traceback.format_exc()
        exc_info = traceback.extract_tb(e.__traceback__)[-1] if e.__traceback__ else None
        if exc_info:
            error_details = f'Exception during move: {type(e).__name__}: {str(e)} at {exc_info.filename}:{exc_info.lineno} in {exc_info.name}(). Traceback: {tb_str}'
        else:
            error_details = f'Exception during move: {type(e).__name__}: {str(e)}. Traceback: {tb_str}'
        current_app.logger.error(f'Error moving item {ja_id}: {error_details}')
        log_audit_batch_operation('batch_move_items', 'error',
                                error_details=f'Batch move exception: {error_details}')
        current_app.logger.error(f'Batch move error: {error_details}\n{traceback.format_exc()}')
        return jsonify({
            'success': False,
            'error': 'Batch move operation failed'
        }), 500

@bp.route('/api/inventory/next-ja-id')
def get_next_ja_id():
    """Get the next available JA ID"""
    try:
        service = _get_inventory_service()
        next_number = service.get_max_ja_id_number() + 1
        next_id = f"JA{next_number:06d}"

        return jsonify({
            'success': True,
            'next_ja_id': next_id
        })
        
    except Exception as e:
        current_app.logger.error(f'Error generating next JA ID: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to generate next JA ID'
        }), 500

@bp.route('/api/thread-series-lookup', methods=['GET'])
def thread_series_lookup():
    """Look up the thread series for a given thread size"""
    try:
        from app.models import lookup_thread_series

        thread_size = request.args.get('thread_size', '').strip()

        if not thread_size:
            return jsonify({
                'success': False,
                'error': 'thread_size parameter is required'
            }), 400

        # Look up the series
        series = lookup_thread_series(thread_size)

        if series:
            return jsonify({
                'success': True,
                'thread_size': thread_size,
                'series': series
            })
        else:
            return jsonify({
                'success': True,
                'thread_size': thread_size,
                'series': None
            })

    except Exception as e:
        current_app.logger.error(f'Error looking up thread series for "{thread_size}": {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to lookup thread series'
        }), 500

@bp.route('/api/labels/print', methods=['POST'])
@csrf.exempt
def print_label():
    """Print a barcode label for a JA ID"""
    try:
        from app.services.label_printer import print_label_for_ja_id, get_available_label_types
        
        data = request.get_json() or {}
        ja_id = data.get('ja_id', '').strip()
        label_type = data.get('label_type', '').strip()
        
        if not ja_id:
            return jsonify({
                'success': False,
                'error': 'ja_id is required'
            }), 400
            
        if not label_type:
            return jsonify({
                'success': False,
                'error': 'label_type is required'
            }), 400
        
        # Validate JA ID format
        if not (ja_id.startswith('JA') and len(ja_id) == 8 and ja_id[2:].isdigit()):
            return jsonify({
                'success': False,
                'error': 'Invalid JA ID format. Expected format: JA######'
            }), 400
        
        # Validate label type
        available_types = get_available_label_types()
        if label_type not in available_types:
            return jsonify({
                'success': False,
                'error': f'Invalid label type. Available types: {available_types}'
            }), 400
        
        # Print the label
        print_label_for_ja_id(ja_id, label_type)
        
        current_app.logger.info(f'Successfully printed {label_type} label for {ja_id}')
        
        return jsonify({
            'success': True,
            'message': f'Label printed successfully for {ja_id}',
            'ja_id': ja_id,
            'label_type': label_type
        })
        
    except ValueError as e:
        current_app.logger.warning(f'Validation error printing label: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
        
    except Exception as e:
        current_app.logger.error(f'Error printing label: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to print label'
        }), 500

@bp.route('/api/labels/types')
def get_label_types():
    """Get available label types for the UI"""
    try:
        from app.services.label_printer import get_available_label_types
        
        available_types = get_available_label_types()
        
        return jsonify({
            'success': True,
            'label_types': available_types
        })
        
    except Exception as e:
        current_app.logger.error(f'Error getting label types: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to get label types'
        }), 500

@bp.route('/api/inventory/list')
def api_inventory_list():
    """Get inventory list data for the frontend"""
    try:
        service = _get_inventory_service()

        # Get status filter from query parameter (default: all)
        # The frontend will handle filtering based on the dropdown selection
        status = request.args.get('status', 'all')

        # Build filter dict based on status
        filters = {}
        if status == 'active':
            filters['active'] = True
        elif status == 'inactive':
            filters['active'] = False
        elif status == 'all':
            filters['active'] = ''  # Empty string means show all items
        else:
            # Invalid status value, default to all items
            filters['active'] = ''

        # Get items using search_active_items which handles the active filter
        items = service.search_active_items(filters)
        
        # Get photo counts for all items efficiently
        from app.photo_service import PhotoService
        with PhotoService(_get_storage_backend()) as photo_service:
            ja_ids = [item.ja_id for item in items]
            photo_counts = photo_service.get_photo_counts_bulk(ja_ids)
        
        # Convert to JSON-serializable format
        items_data = []
        for item in items:
            item_data = {
                'ja_id': item.ja_id,
                'display_name': item.display_name,
                'item_type': item.item_type,  # InventoryItem stores as string
                'shape': item.shape,  # InventoryItem stores as string
                'material': item.material,
                'dimensions': item.dimensions.to_dict() if item.dimensions else None,
                'thread': item.thread.to_dict() if item.thread else None,
                'location': item.location,
                'sub_location': item.sub_location,
                'purchase_date': item.purchase_date.isoformat() if item.purchase_date else None,
                'purchase_price': str(item.purchase_price) if item.purchase_price else None,
                'purchase_location': item.purchase_location,
                'vendor': item.vendor,
                'vendor_part_number': item.vendor_part,  # InventoryItem field name
                'notes': item.notes,
                'active': item.active,
                'precision': item.precision,  # Add precision field to API response
                'parent_ja_id': None,  # InventoryItem doesn't have parent/child relationships
                'child_ja_ids': [],  # InventoryItem doesn't have parent/child relationships
                'date_added': item.date_added.isoformat() if item.date_added else None,
                'last_modified': item.last_modified.isoformat() if item.last_modified else None,
                'photo_count': photo_counts.get(item.ja_id, 0)
            }
            items_data.append(item_data)
        
        return jsonify({
            'success': True,
            'items': items_data,
            'total_count': len(items_data)
        })
        
    except Exception as e:
        current_app.logger.error(f'Error loading inventory list: {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to load inventory list',
            'items': []
        }), 500

@bp.route('/api/inventory/<ja_id>/status', methods=['PATCH'])
@csrf.exempt
def api_toggle_item_status(ja_id):
    """Toggle item active/inactive status"""
    try:
        data = request.get_json() or {}

        if 'active' not in data:
            return jsonify({
                'success': False,
                'message': 'Missing "active" field in request'
            }), 400

        active = data['active']
        if not isinstance(active, bool):
            return jsonify({
                'success': False,
                'message': '"active" must be a boolean'
            }), 400

        service = _get_inventory_service()

        # Get the canonical row for this JA ID: prefer the active row,
        # otherwise the latest inactive row with a deterministic tiebreak.
        item = service.get_canonical_item(ja_id)
        if not item:
            return jsonify({
                'success': False,
                'message': f'Item {ja_id} not found'
            }), 404

        # Update active status
        item.active = active

        # Save changes
        if service.update_item(item):

            action = 'activated' if active else 'deactivated'
            return jsonify({
                'success': True,
                'message': f'Item {ja_id} {action} successfully',
                'active': active
            })
        else:
            error_msg = f'Failed to update item {ja_id}'
            return jsonify({
                'success': False,
                'message': error_msg
            }), 500

    except Exception as e:
        current_app.logger.error(f'Error toggling item status for {ja_id}: {e}')
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500

@bp.route('/api/inventory/search', methods=['POST'])
@csrf.exempt
def api_advanced_search():
    """Advanced search API endpoint"""
    try:
        data = request.get_json() or {}
        
        service = _get_inventory_service()
        
        # Import SearchFilter here to avoid circular import
        from app.mariadb_inventory_service import SearchFilter
        
        # Build search filter from request data
        search_filter = SearchFilter()
        
        # Basic identification filters
        if data.get('ja_id'):
            search_filter.add_exact_match('ja_id', data['ja_id'].upper())
        
        if data.get('location'):
            search_filter.add_text_search('location', data['location'])
        
        if data.get('notes'):
            search_filter.add_text_search('notes', data['notes'])
        
        # Type and shape filters
        if data.get('item_type'):
            try:
                item_type = ItemType(data['item_type'])
                search_filter.add_exact_match('item_type', item_type)
            except KeyError:
                return jsonify({
                    'success': False,
                    'message': f'Invalid item type: {data["item_type"]}',
                    'items': [],
                    'total_count': 0
                }), 400
        
        if data.get('shape'):
            try:
                shape = ItemShape(data['shape'])
                search_filter.add_exact_match('shape', shape)
            except KeyError:
                return jsonify({
                    'success': False,
                    'message': f'Invalid shape: {data["shape"]}',
                    'items': [],
                    'total_count': 0
                }), 400
        
        # Active/inactive filter
        if 'active' in data:
            if data['active'] == '':
                # Empty string means show all items - add empty string to filters
                search_filter.add_exact_match('active', '')
            elif data['active'] is not None:
                if isinstance(data['active'], bool):
                    search_filter.add_exact_match('active', data['active'])
                elif isinstance(data['active'], str):
                    search_filter.add_exact_match('active', data['active'].lower() == 'true')
        # If active is not present at all, search_active_items will default to active items only
        
        # Precision filter
        if 'precision' in data and data['precision'] is not None:
            if isinstance(data['precision'], bool):
                search_filter.add_exact_match('precision', data['precision'])
            elif isinstance(data['precision'], str):
                search_filter.add_exact_match('precision', data['precision'].lower() == 'true')
        
        # Material filter with hierarchical support
        if data.get('material'):
            # Get all descendant materials in the hierarchy for hierarchical search
            material_descendants = service.get_material_descendants(data['material'])
            # Add the material list directly to the filter for hierarchical matching
            search_filter.add_exact_match('material', material_descendants)
        
        # Dimension range filters
        dimension_fields = ['length', 'width', 'thickness', 'wall_thickness']
        for field in dimension_fields:
            min_val = data.get(f'{field}_min')
            max_val = data.get(f'{field}_max')
            
            if min_val is not None or max_val is not None:
                try:
                    min_decimal = Decimal(str(min_val)) if min_val is not None else None
                    max_decimal = Decimal(str(max_val)) if max_val is not None else None
                    search_filter.add_range(field, min_decimal, max_decimal)
                except (ValueError, InvalidOperation):
                    return jsonify({
                        'success': False,
                        'message': f'Invalid {field} range values',
                        'items': [],
                        'total_count': 0
                    }), 400
        
        # Thread filters
        if data.get('thread_size'):
            search_filter.add_text_search('thread_size', data['thread_size'])
        
        if data.get('thread_series'):
            try:
                thread_series = ThreadSeries[data['thread_series'].upper()]
                search_filter.add_exact_match('thread_series', thread_series)
            except KeyError:
                return jsonify({
                    'success': False,
                    'message': f'Invalid thread series: {data["thread_series"]}',
                    'items': [],
                    'total_count': 0
                }), 400
        
        
        # Execute search
        items = service.search_items(search_filter)

        # Get photo counts for all items efficiently
        from app.photo_service import PhotoService
        with PhotoService(_get_storage_backend()) as photo_service:
            ja_ids = [item.ja_id for item in items]
            photo_counts = photo_service.get_photo_counts_bulk(ja_ids)

        # Convert to JSON-serializable format
        items_data = []
        for item in items:
            item_data = {
                'ja_id': item.ja_id,
                'display_name': item.display_name,
                'item_type': item.item_type,
                'shape': item.shape,
                'material': item.material,
                'dimensions': item.dimensions.to_dict() if item.dimensions else None,
                'thread': item.thread.to_dict() if item.thread else None,
                'location': item.location,
                'sub_location': item.sub_location,
                'purchase_date': item.purchase_date.isoformat() if item.purchase_date else None,
                'purchase_price': str(item.purchase_price) if item.purchase_price else None,
                'purchase_location': item.purchase_location,
                'vendor': item.vendor,
                'vendor_part_number': item.vendor_part,
                'notes': item.notes,
                'precision': item.precision,
                'active': item.active,
                'date_added': item.date_added.isoformat() if item.date_added else None,
                'last_modified': item.last_modified.isoformat() if item.last_modified else None,
                'photo_count': photo_counts.get(item.ja_id, 0)
            }
            items_data.append(item_data)
        
        return jsonify({
            'success': True,
            'items': items_data,
            'total_count': len(items_data),
            'search_criteria': data
        })

    except Exception as e:
        current_app.logger.error(f'Advanced search error: {e}\n{traceback.format_exc()}')
        return jsonify({
            'success': False,
            'message': 'Search operation failed',
            'error': str(e),
            'items': [],
            'total_count': 0
        }), 500

def _execute_shortening_operation(form_data):
    """Execute the shortening operation using keep-same-ID approach"""
    try:
        service = _get_inventory_service()
        
        source_ja_id = form_data['source_ja_id'].upper()
        
        # Parse new length
        try:
            new_length = _parse_dimension_value(form_data['new_length'])
            if not new_length or float(new_length) <= 0:
                return {'success': False, 'error': 'Invalid new length'}
        except Exception:
            return {'success': False, 'error': 'Invalid new length format'}
        
        # Check if this is MariaDB service with keep-same-ID shortening support  
        if hasattr(service, 'shorten_item') and hasattr(service, 'get_item_history'):
            # Use MariaDB-specific shortening method with keep-same-ID approach
            result = service.shorten_item(
                ja_id=source_ja_id,
                new_length=float(new_length),
                cut_date=form_data.get('cut_date'),
                notes=form_data.get('shortening_notes')
            )
            
            if result['success']:
                current_app.logger.info(f'Keep-same-ID shortening completed: {source_ja_id} shortened to {new_length}"')
            
            return result
            
        else:
            # For non-MariaDB storage (like tests), implement keep-same-ID shortening manually
            current_app.logger.info(f'Using manual keep-same-ID shortening for non-MariaDB storage')
            
            # Get current item
            current_item = service.get_item(source_ja_id)
            if not current_item:
                return {'success': False, 'error': f'Item {source_ja_id} not found'}
            
            # Validate new length
            if current_item.dimensions and current_item.dimensions.length:
                original_length = float(current_item.dimensions.length)
                if float(new_length) >= original_length:
                    return {'success': False, 'error': 'New length must be shorter than current length'}
            else:
                return {'success': False, 'error': 'Item has no current length to shorten'}
            
            # Create updated dimensions for shortening
            new_dimensions = Dimensions(
                length=Decimal(str(new_length)),
                width=current_item.dimensions.width,
                thickness=current_item.dimensions.thickness,
                wall_thickness=current_item.dimensions.wall_thickness,
                weight=None  # Weight would change after cutting
            )
            
            # Update the current item to the shortened version (keep-same-ID approach)
            current_item.dimensions = new_dimensions
            current_item.notes = f"Shortened to {new_length}\" - {form_data.get('shortening_notes', '').strip()}" if form_data.get('shortening_notes', '').strip() else f"Shortened to {new_length}\""
            current_item.active = True
            current_item.last_modified = datetime.now()
            
            if service.update_item(current_item):
                return {
                    'success': True,
                    'ja_id': source_ja_id,
                    'original_length': original_length,
                    'new_length': float(new_length),
                    'message': f'Item {source_ja_id} successfully shortened using keep-same-ID approach'
                }
            else:
                return {'success': False, 'error': 'Failed to add shortened item'}
        
    except Exception as e:
        current_app.logger.error(f'Error in shortening operation: {e}')
        return {'success': False, 'error': str(e)}


def _parse_item_from_form(form_data):
    """Parse form data into an InventoryItem object"""
    from datetime import datetime
    
    # Create InventoryItem directly with form data
    item = InventoryItem(
        ja_id=form_data['ja_id'].upper(),
        item_type=form_data['item_type'],  # Store as string
        shape=form_data['shape'],          # Store as string
        material=form_data['material'].strip(),
        active=form_data.get('active') == 'on',
        precision=form_data.get('precision') == 'on'
    )
    
    # Parse dimensions
    dimension_fields = ['length', 'width', 'thickness', 'wall_thickness', 'weight']
    for field in dimension_fields:
        value = form_data.get(field, '').strip()
        if value:
            try:
                # Handle fraction input and convert to float for database storage
                parsed_value = float(_parse_dimension_value(value))
                setattr(item, field, parsed_value)
            except (ValueError, InvalidOperation) as e:
                raise ValueError(f"Invalid {field}: {value}")
    
    # Parse threading if provided
    thread_series_str = form_data.get('thread_series', '').strip()
    if thread_series_str and thread_series_str != 'None':
        thread_handedness_str = form_data.get('thread_handedness', 'RH').strip() or 'RH'
        thread_size = form_data.get('thread_size', '').strip()
        
        try:
            # Store thread fields as strings in InventoryItem
            item.thread_series = thread_series_str.upper()
            item.thread_handedness = 'RH' if thread_handedness_str.upper() == 'RH' else 'LH'
            item.thread_size = thread_size or None
        except Exception:
            raise ValueError(f"Invalid thread series or handedness: {thread_series_str}, {thread_handedness_str}")

    # Set other fields
    item.location = form_data.get('location', '').strip() or None
    item.sub_location = form_data.get('sub_location', '').strip() or None
    item.purchase_date = _parse_date_from_form(form_data.get('purchase_date'))
    item.purchase_price = form_data.get('purchase_price', '').strip() or None
    item.purchase_location = form_data.get('purchase_location', '').strip() or None
    item.vendor = form_data.get('vendor', '').strip() or None
    item.vendor_part = form_data.get('vendor_part_number', '').strip() or None  # Note: vendor_part not vendor_part_number
    item.notes = form_data.get('notes', '').strip() or None
    
    # Set timestamps
    item.date_added = datetime.now()
    item.last_modified = datetime.now()
    
    return item

def _parse_dimension_value(value):
    """Parse dimension value that might include fractions"""
    value = value.strip()
    if not value:
        return None
    
    # Handle mixed numbers like "1 1/2"
    if ' ' in value and '/' in value:
        parts = value.split(' ', 1)
        try:
            whole = Decimal(parts[0])
            frac_parts = parts[1].split('/')
            if len(frac_parts) == 2:
                numerator = Decimal(frac_parts[0])
                denominator = Decimal(frac_parts[1])
                fraction = numerator / denominator
                return str(whole + fraction)
        except (ValueError, InvalidOperation, ZeroDivisionError):
            pass
    
    # Handle simple fractions like "1/2"
    elif '/' in value:
        try:
            frac_parts = value.split('/')
            if len(frac_parts) == 2:
                numerator = Decimal(frac_parts[0])
                denominator = Decimal(frac_parts[1])
                return str(numerator / denominator)
        except (ValueError, InvalidOperation, ZeroDivisionError):
            pass
    
    # Handle decimal numbers
    try:
        return str(Decimal(value))
    except (ValueError, InvalidOperation):
        raise ValueError(f"Cannot parse dimension value: {value}")

def _parse_date_from_form(date_str):
    """Parse date string from form into datetime object"""
    if not date_str or not date_str.strip():
        return None
    
    date_str = date_str.strip()
    
    try:
        # Try parsing common date formats
        from datetime import datetime
        
        # Try ISO format first (YYYY-MM-DD)
        if '-' in date_str and len(date_str.split('-')) == 3:
            return datetime.strptime(date_str, '%Y-%m-%d')
        
        # Try US format (MM/DD/YYYY)
        elif '/' in date_str and len(date_str.split('/')) == 3:
            return datetime.strptime(date_str, '%m/%d/%Y')
        
        # Try other common formats
        elif '.' in date_str and len(date_str.split('.')) == 3:
            return datetime.strptime(date_str, '%m.%d.%Y')
        
    except ValueError:
        pass
    
    # If all parsing attempts fail, return None
    return None


_DUPLICATE_BOOLEAN_FIELDS = frozenset({'active', 'precision'})


def _coerce_bool(value):
    """Coerce a JSON/form value to bool, accepting True/False, "on"/"off",
    "true"/"false", 1/0 etc. Treats any unrecognized non-empty string as
    truthy to match the lenient behavior callers historically assumed."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ('', 'off', 'false', '0', 'no')
    return bool(value)


def _normalize_duplicate_updated_fields(updated_fields):
    """Normalize the updated_fields payload from the duplicate-with-save flow.

    The edit-page form posts checkbox state as either an HTML form's "on"
    string (legacy) or, after the snapshot-based payload builder, as JSON
    booleans. Either way these need to land on the source item as actual
    Python booleans before setattr, so the in-memory ORM attribute matches
    what SQLAlchemy will persist - especially for unchecked checkboxes,
    which would otherwise either be missing entirely (silently dropping
    the change) or set to a stale string.
    """
    normalized = dict(updated_fields)
    for field in _DUPLICATE_BOOLEAN_FIELDS:
        if field in normalized:
            normalized[field] = _coerce_bool(normalized[field])
    return normalized


# Export Endpoints
# NOTE: /admin/export route moved to admin/routes.py

@bp.route('/api/admin/export', methods=['POST'])
@csrf.exempt
def api_admin_export():
    """API endpoint for triggering data exports"""
    try:
        data = request.get_json() or {}
        
        # Parse export options
        export_type = data.get('type', 'combined')  # 'inventory', 'materials', or 'combined'
        destination = data.get('destination', 'json')  # 'json' or 'sheets'
        options_data = data.get('options', {})
        
        # Validate export type
        if export_type not in ['inventory', 'materials', 'combined']:
            return jsonify({
                'success': False,
                'error': 'Invalid export type. Must be inventory, materials, or combined.'
            }), 400
        
        # Validate destination
        if destination not in ['json', 'sheets']:
            return jsonify({
                'success': False,
                'error': 'Invalid destination. Must be json or sheets.'
            }), 400
        
        # Import export services
        from app.export_service import InventoryExportService, MaterialsExportService, CombinedExportService
        from app.export_schemas import ExportOptions
        
        # Configure export options
        options = ExportOptions()
        options.batch_size = options_data.get('batch_size', 1000)
        options.enable_progress_logging = options_data.get('enable_progress_logging', True)
        
        # Inventory-specific options
        options.inventory_include_inactive = options_data.get('include_inactive', True)
        options.inventory_sort_order = options_data.get('inventory_sort_order', 'ja_id, active DESC, date_added')
        
        # Materials-specific options
        options.materials_active_only = options_data.get('materials_active_only', True)
        options.materials_sort_order = options_data.get('materials_sort_order', 'level, sort_order, name')
        
        # Export metadata
        options.export_generated_by = options_data.get('export_generated_by', 'Workshop Inventory MariaDB Export')
        
        current_app.logger.info(f'Starting {export_type} export to {destination}')
        
        # Execute export based on type
        if export_type == 'inventory':
            service = InventoryExportService(storage=_get_storage_backend())
            headers, rows, metadata = service.export_complete_dataset(options)
            
            result = {
                'type': 'inventory',
                'headers': headers,
                'rows': rows,
                'metadata': metadata.to_dict(),
                'summary': {
                    'total_records': metadata.records_exported,
                    'success': len(metadata.errors) == 0,
                    'errors': metadata.errors,
                    'warnings': metadata.warnings
                }
            }
            
        elif export_type == 'materials':
            service = MaterialsExportService(storage=_get_storage_backend())
            headers, rows, metadata = service.export_complete_dataset(options)
            
            result = {
                'type': 'materials',
                'headers': headers,
                'rows': rows,
                'metadata': metadata.to_dict(),
                'summary': {
                    'total_records': metadata.records_exported,
                    'success': len(metadata.errors) == 0,
                    'errors': metadata.errors,
                    'warnings': metadata.warnings
                }
            }
            
        else:  # combined
            service = CombinedExportService(storage=_get_storage_backend())
            result = service.export_all_data(options)
        
        # Handle destination
        if destination == 'json':
            # Calculate stats for UI display
            total_items = 0
            if export_type == 'combined':
                if 'inventory' in result and 'rows' in result['inventory']:
                    total_items += len(result['inventory']['rows'])
                if 'materials' in result and 'rows' in result['materials']:
                    total_items += len(result['materials']['rows'])
            else:
                total_items = len(result.get('rows', []))
            
            # Return JSON data directly
            return jsonify({
                'success': True,
                'export_data': result,
                'timestamp': result.get('timestamp'),
                'export_type': export_type,
                'stats': {
                    'total_items': total_items,
                    'processing_time': 'Complete'
                }
            })
            
        elif destination == 'sheets':
            # Upload to Google Sheets
            upload_result = _upload_to_google_sheets(result, export_type)
            
            # Debug logging to understand the upload_result structure
            current_app.logger.info(f'Upload result: {upload_result}')
            
            # Check if upload was successful
            upload_success = upload_result.get('success', False)
            
            if upload_success:
                # Calculate stats for UI display
                total_items = upload_result.get('rows_uploaded', 0)
                if export_type == 'combined' and 'results' in upload_result:
                    total_items = sum(r.get('affected_rows', 0) for r in upload_result['results'].values())
                
                return jsonify({
                    'success': True,
                    'message': f'Export to Google Sheets completed successfully',
                    'export_type': export_type,
                    'upload_details': upload_result,
                    'stats': {
                        'total_items': total_items,
                        'processing_time': 'Complete'
                    }
                })
            else:
                # For combined exports, check if individual uploads succeeded even if overall failed
                if export_type == 'combined' and 'results' in upload_result:
                    individual_successes = []
                    individual_errors = []
                    for sheet_name, sheet_result in upload_result['results'].items():
                        if sheet_result.get('success', False):
                            individual_successes.append(f"{sheet_name}: {sheet_result.get('affected_rows', 0)} rows")
                        else:
                            individual_errors.append(f"{sheet_name}: {sheet_result.get('error', 'Unknown error')}")
                    
                    if individual_successes and not individual_errors:
                        # All individual uploads succeeded, treat as success despite overall failure
                        current_app.logger.warning(f'Combined export marked as failed but all individual uploads succeeded: {individual_successes}')
                        
                        # Calculate total items for stats
                        total_items = sum(r.get('affected_rows', 0) for r in upload_result['results'].values())
                        
                        return jsonify({
                            'success': True,
                            'message': f'Export to Google Sheets completed successfully (partial success recovered)',
                            'export_type': export_type,
                            'upload_details': upload_result,
                            'individual_results': individual_successes,
                            'stats': {
                                'total_items': total_items,
                                'processing_time': 'Complete'
                            }
                        })
                
                # Handle failure case
                errors = upload_result.get('errors', [])
                error_msg = '; '.join(filter(None, errors)) if errors else upload_result.get('error', 'Unknown upload error')
                
                return jsonify({
                    'success': False,
                    'error': f'Export completed but Google Sheets upload failed: {error_msg}',
                    'upload_details': upload_result,
                    'export_data': result  # Include data for potential retry
                }), 500
        
    except Exception as e:
        current_app.logger.error(f'Export API error: {e}\n{traceback.format_exc()}')
        return jsonify({
            'success': False,
            'error': f'Export operation failed: {str(e)}'
        }), 500

@bp.route('/api/admin/export/validate', methods=['POST'])
@csrf.exempt
def api_export_validate():
    """Validate export data before uploading to Google Sheets"""
    try:
        data = request.get_json() or {}
        export_data = data.get('export_data')
        
        if not export_data:
            return jsonify({
                'success': False,
                'error': 'No export data provided'
            }), 400
        
        from app.export_service import CombinedExportService
        service = CombinedExportService(storage=_get_storage_backend())
        
        validation_result = service.validate_export_data(export_data)
        
        return jsonify({
            'success': True,
            'validation': validation_result
        })
        
    except Exception as e:
        current_app.logger.error(f'Export validation error: {e}')
        return jsonify({
            'success': False,
            'error': f'Validation failed: {str(e)}'
        }), 500

def _upload_to_google_sheets(export_data, export_type):
    """Upload export data to Google Sheets"""
    try:
        from app.google_sheets_export import GoogleSheetsExportService
        
        current_app.logger.info(f'Starting Google Sheets upload for {export_type} export')
        
        # Initialize export service
        export_service = GoogleSheetsExportService()
        
        # Test connection first
        connection_test = export_service.test_connection()
        if not connection_test.success:
            return {
                'success': False,
                'error': f'Google Sheets connection failed: {connection_test.error}'
            }
        
        # Upload data based on export type
        if export_type == 'combined':
            # Upload both inventory and materials data
            result = export_service.upload_combined_export(export_data)
            
            return {
                'success': result['success'],
                'message': f'Combined upload completed: {result["total_rows_uploaded"]} total rows',
                'upload_type': export_type,
                'rows_uploaded': result['total_rows_uploaded'],
                'sheets_updated': ['Metal_Export', 'Materials_Export'],
                'details': result['results'],
                'errors': result['errors']
            }
            
        elif export_type == 'inventory':
            # Upload inventory data only
            headers = export_data.get('headers', [])
            rows = export_data.get('rows', [])
            
            result = export_service.upload_inventory_export(headers, rows)
            
            return {
                'success': result.success,
                'message': f'Inventory upload completed: {result.affected_rows} rows' if result.success else f'Upload failed: {result.error}',
                'upload_type': export_type,
                'rows_uploaded': result.affected_rows or 0,
                'sheets_updated': ['Metal_Export'] if result.success else [],
                'details': result.data,
                'error': result.error if not result.success else None
            }
            
        elif export_type == 'materials':
            # Upload materials data only
            headers = export_data.get('headers', [])
            rows = export_data.get('rows', [])
            
            result = export_service.upload_materials_export(headers, rows)
            
            return {
                'success': result.success,
                'message': f'Materials upload completed: {result.affected_rows} rows' if result.success else f'Upload failed: {result.error}',
                'upload_type': export_type,
                'rows_uploaded': result.affected_rows or 0,
                'sheets_updated': ['Materials_Export'] if result.success else [],
                'details': result.data,
                'error': result.error if not result.success else None
            }
            
        else:
            return {
                'success': False,
                'error': f'Unknown export type: {export_type}'
            }
        
    except Exception as e:
        current_app.logger.error(f'Google Sheets upload error: {e}\n{traceback.format_exc()}')
        return {
            'success': False,
            'error': f'Upload failed: {str(e)}'
        }

# Photo API endpoints
@bp.route('/api/items/<ja_id>/photos', methods=['POST'])
@csrf.exempt
def upload_photo(ja_id):
    """Upload a photo for an inventory item"""
    try:
        from app.photo_service import PhotoService
        
        # Check if file was uploaded (accept both 'file' and 'photo' field names)
        file = request.files.get('file') or request.files.get('photo')
        if file is None:
            return jsonify({
                'success': False,
                'error': 'No file provided'
            }), 400
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        # Get file data
        file_data = file.read()
        filename = file.filename
        content_type = file.content_type
        
        # Validate content type
        with PhotoService(_get_storage_backend()) as photo_service:
            photo = photo_service.upload_photo(ja_id, file_data, filename, content_type)
            
            return jsonify({
                'success': True,
                'photo': photo.to_dict(),
                'message': f'Photo {filename} uploaded successfully'
            })
            
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except RuntimeError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
        
    except Exception as e:
        current_app.logger.error(f'Photo upload error: {e}')
        return jsonify({
            'success': False,
            'error': f'Photo upload failed: {str(e)}'
        }), 500

@bp.route('/api/items/<ja_id>/photos', methods=['GET'])
def get_item_photos(ja_id):
    """Get all photos for an inventory item"""
    try:
        from app.photo_service import PhotoService
        
        with PhotoService(_get_storage_backend()) as photo_service:
            photos = photo_service.get_photos(ja_id)
            
            return jsonify({
                'success': True,
                'photos': [photo.to_dict() for photo in photos],
                'count': len(photos)
            })
        
    except Exception as e:
        current_app.logger.error(f'Get photos error: {e}')
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve photos: {str(e)}'
        }), 500

@bp.route('/api/photos/<int:photo_id>', methods=['GET'])
def get_photo_data(photo_id):
    """Get photo data with specified size"""
    try:
        from app.photo_service import PhotoService
        import io
        
        size = request.args.get('size', 'original')  # thumbnail, medium, original
        if size not in ['thumbnail', 'medium', 'original']:
            return jsonify({
                'success': False,
                'error': 'Invalid size parameter. Use: thumbnail, medium, or original'
            }), 400
        
        with PhotoService(_get_storage_backend()) as photo_service:
            result = photo_service.get_photo_data(photo_id, size)
            
            if not result:
                return jsonify({
                    'success': False,
                    'error': 'Photo not found'
                }), 404
            
            data, content_type = result
        
        # Return the image data
        return send_file(
            io.BytesIO(data),
            mimetype=content_type,
            as_attachment=False
        )
        
    except Exception as e:
        current_app.logger.error(f'Get photo data error: {e}')
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve photo data: {str(e)}'
        }), 500

@bp.route('/api/photos/<int:photo_id>/download', methods=['GET'])
def download_photo(photo_id):
    """Download photo as attachment"""
    try:
        from app.photo_service import PhotoService
        import io
        
        with PhotoService(_get_storage_backend()) as photo_service:
            photo = photo_service.get_photo(photo_id)
            
            if not photo:
                return jsonify({
                    'success': False,
                    'error': 'Photo not found'
                }), 404
            
            result = photo_service.get_photo_data(photo_id, 'original')
            if not result:
                return jsonify({
                    'success': False,
                    'error': 'Photo data not found'
                }), 404
            
            data, content_type = result
        
        # Return the image data as attachment
        return send_file(
            io.BytesIO(data),
            mimetype=content_type,
            as_attachment=True,
            download_name=photo.filename
        )
        
    except Exception as e:
        current_app.logger.error(f'Download photo error: {e}')
        return jsonify({
            'success': False,
            'error': f'Failed to download photo: {str(e)}'
        }), 500

@bp.route('/api/photos/<int:photo_id>', methods=['DELETE'])
@csrf.exempt
def delete_photo(photo_id):
    """Delete a photo"""
    try:
        from app.photo_service import PhotoService
        
        with PhotoService(_get_storage_backend()) as photo_service:
            success = photo_service.delete_photo(photo_id)
            
            if success:
                return jsonify({
                    'success': True,
                    'message': 'Photo deleted successfully'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Photo not found'
                }), 404
        
    except Exception as e:
        current_app.logger.error(f'Delete photo error: {e}')
        return jsonify({
            'success': False,
            'error': f'Failed to delete photo: {str(e)}'
        }), 500

@bp.route('/api/admin/photos/cleanup', methods=['POST'])
@csrf.exempt
def cleanup_orphaned_photos():
    """Cleanup photos for items that no longer exist"""
    try:
        from app.photo_service import PhotoService
        
        with PhotoService(_get_storage_backend()) as photo_service:
            cleaned_count = photo_service.cleanup_orphaned_photos()
            
            return jsonify({
                'success': True,
                'message': f'Cleaned up {cleaned_count} orphaned photos',
                'photos_removed': cleaned_count
            })
        
    except Exception as e:
        current_app.logger.error(f'Photo cleanup error: {e}')
        return jsonify({
            'success': False,
            'error': f'Failed to cleanup photos: {str(e)}'
        }), 500

@bp.route('/api/admin/photos/regenerate-pdf-thumbnails', methods=['POST'])
@csrf.exempt
def regenerate_pdf_thumbnails():
    """Regenerate thumbnails for existing PDF photos"""
    try:
        from app.photo_service import PhotoService
        
        with PhotoService(_get_storage_backend()) as photo_service:
            updated_count = photo_service.regenerate_pdf_thumbnails()
            
            return jsonify({
                'success': True,
                'message': f'Regenerated thumbnails for {updated_count} PDF photos',
                'photos_updated': updated_count
            })
        
    except Exception as e:
        current_app.logger.error(f'PDF thumbnail regeneration error: {e}')
        return jsonify({
            'success': False,
            'error': f'Failed to regenerate PDF thumbnails: {str(e)}'
        }), 500


@bp.route('/api/photos/copy', methods=['POST'])
@csrf.exempt
def copy_photos():
    """
    Copy photos from one item to one or more target items.

    Request JSON:
        {
            "source_ja_id": "JA000123",
            "target_ja_ids": ["JA000456", "JA000789"]
        }

    Response JSON:
        {
            "success": true,
            "photos_copied": 3,
            "items_updated": 2,
            "details": [
                {"ja_id": "JA000456", "photos_copied": 3, "success": true},
                {"ja_id": "JA000789", "photos_copied": 3, "success": true}
            ]
        }
    """
    try:
        data = request.get_json()

        # Validate request data
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided'
            }), 400

        source_ja_id = data.get('source_ja_id')
        target_ja_ids = data.get('target_ja_ids', [])

        if not source_ja_id:
            return jsonify({
                'success': False,
                'error': 'source_ja_id is required'
            }), 400

        if not target_ja_ids or not isinstance(target_ja_ids, list):
            return jsonify({
                'success': False,
                'error': 'target_ja_ids must be a non-empty list'
            }), 400

        if len(target_ja_ids) == 0:
            return jsonify({
                'success': False,
                'error': 'At least one target JA ID is required'
            }), 400

        # Copy photos to each target item
        from app.photo_service import PhotoService

        with PhotoService(_get_storage_backend()) as photo_service:
            # Check if source item exists and has photos
            source_photos = photo_service.get_photos(source_ja_id)

            if not source_photos:
                return jsonify({
                    'success': False,
                    'error': f'Source item {source_ja_id} has no photos to copy'
                }), 400

            photos_per_item = len(source_photos)
            details = []
            successful_count = 0

            for target_ja_id in target_ja_ids:
                try:
                    copied_count = photo_service.copy_photos(source_ja_id, target_ja_id)
                    details.append({
                        'ja_id': target_ja_id,
                        'photos_copied': copied_count,
                        'success': True
                    })
                    successful_count += 1

                    # Log audit operation
                    log_audit_operation('copy_photos', 'success',
                                      item_id=target_ja_id,
                                      form_data={
                                          'source_ja_id': source_ja_id,
                                          'photos_copied': copied_count
                                      })

                except ValueError as e:
                    # Item not found or other validation error
                    current_app.logger.warning(f'Failed to copy photos to {target_ja_id}: {e}')
                    details.append({
                        'ja_id': target_ja_id,
                        'photos_copied': 0,
                        'success': False,
                        'error': str(e)
                    })
                except Exception as e:
                    # Unexpected error
                    current_app.logger.error(f'Error copying photos to {target_ja_id}: {e}')
                    details.append({
                        'ja_id': target_ja_id,
                        'photos_copied': 0,
                        'success': False,
                        'error': f'Unexpected error: {str(e)}'
                    })

            # Determine overall success
            all_succeeded = successful_count == len(target_ja_ids)

            response = {
                'success': all_succeeded,
                'photos_copied': photos_per_item,
                'items_updated': successful_count,
                'details': details
            }

            # If partial success, return 207 Multi-Status
            # If all failed, return 500
            # If all succeeded, return 200
            if successful_count == 0:
                response['error'] = 'Failed to copy photos to any target items'
                return jsonify(response), 500
            elif not all_succeeded:
                response['warning'] = f'Copied photos to {successful_count} of {len(target_ja_ids)} items'
                return jsonify(response), 207
            else:
                return jsonify(response), 200

    except Exception as e:
        current_app.logger.error(f'Photo copy API error: {e}')
        log_audit_operation('copy_photos', 'error',
                          error_details=str(e))
        return jsonify({
            'success': False,
            'error': f'Failed to copy photos: {str(e)}'
        }), 500


# Error handlers for the blueprint
@bp.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@bp.errorhandler(500)
def internal_error(error):
    current_app.logger.error(f'Server Error: {error}')
    return render_template('errors/500.html'), 500

