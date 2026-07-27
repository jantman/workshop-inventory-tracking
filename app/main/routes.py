from flask import render_template, current_app, jsonify, abort, request, flash, redirect, url_for, send_file
from datetime import datetime, date
from typing import Any
from app.main import bp
from app import csrf
from app.mariadb_storage import MariaDBStorage
# Using unified InventoryService (MariaDB-based implementation)
from app.mariadb_inventory_service import InventoryService
from app.mariadb_catalog_service import (
    CatalogService,
    FIELD_SUGGESTION_COLUMNS as CATALOG_FIELD_SUGGESTION_COLUMNS,
)
# Performance optimizations removed - no longer needed with MariaDB
from app.taxonomy import type_shape_validator
from app.models import (ItemType, ItemShape, Dimensions, Thread, ThreadSeries,
                        ThreadHandedness, IdentifierType, ScanKind)
from app.database import InventoryItem
# Story 3.2: routes call the pure category util for segment-boundary logic —
# they never re-derive it (AD-4).
from app.utils import category as category_util
# Story 4.5: the route needs ONE pure-util call from the classifier module —
# `strip_aim_prefix`, to re-derive the text a fallthrough search ran on. That is
# a util call, not classification (AD-4/AD-5): the route never calls classify()
# and never decides a kind.
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
    """Get the appropriate storage backend for the current app context"""
    # Check if test storage is injected
    if 'STORAGE_BACKEND' in current_app.config:
        return current_app.config['STORAGE_BACKEND']
    
    # Use MariaDB storage (switched from Google Sheets in Milestone 2)
    from app.mariadb_storage import MariaDBStorage
    return MariaDBStorage()

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

# Length limits mirroring the Product column definitions (app/database.py).
_PRODUCT_FIELD_LIMITS = {
    'description': ('Label Description', 255),
    'manufacturer': ('Manufacturer', 255),
    'mpn': ('MPN', 255),
    'category_path': ('Category', 512),
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

# `Purchase.quantity` is an INTEGER, which MariaDB stores in 32 bits. A longer
# digit string parses fine in Python and then overflows the column, so the form
# refuses it here rather than letting the write fail with the generic message.
_MAX_INT32 = 2147483647


def _positive_int_string(value):
    """The value as a positive 32-bit int, or None if it is not one.

    Deliberately NOT `int()`. `int('1_0')` is 10 and `int('٥')` is 5, so a form
    that promises "a whole number" would silently store something the operator
    did not type. `.isascii() and .isdigit()` is the rule the message states:
    ASCII digits, nothing else — no sign, no separator, no exponent, no
    non-ASCII numeral.
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
    if parsed <= 0 or parsed > _MAX_INT32:
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


def _validate_product_form(form_data):
    """Validate product form input. Returns a dict of field -> error message.

    Story 4.5 adds three rules here rather than in `product_add`, so that every
    caller of this function inherits them and none can be bypassed by a POST
    aimed at a different route (FR41):

    - the optional first-receipt fields are bounded against their `Purchase`
      columns, and `quantity` — the one typed field on that block — must parse
      as a whole number greater than zero;
    - a form carrying `duplicate_of` (a scan that already matched an existing
      Product) is refused unless `confirm_duplicate` is exactly `'yes'`. The
      gate lives here, before any write, on the `inventory_shorten` precedent:
      the destructive-by-accident outcome FR41 names is creating a SECOND
      product for a scan that already resolved, and a validation error is the
      only way to guarantee nothing at all is written.
    """
    errors = {}
    if not (form_data.get('description') or '').strip():
        errors['description'] = 'Label Description is required.'
    for field, (label, limit) in _PRODUCT_FIELD_LIMITS.items():
        value = (form_data.get(field) or '').strip()
        if value and len(value) > limit and field not in errors:
            errors[field] = f'{label} must be {limit} characters or fewer.'
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
    """
    return {
        'description': product.description or '',
        'manufacturer': product.manufacturer or '',
        'mpn': product.mpn or '',
        'category_path': product.category_path or '',
        'tags': tag_util.format_tag_list(tags),
        'notes': product.notes or '',
    }


# --- Scan pre-fill boundary (Story 4.5, FR39/FR40) --------------------------

# The ONLY `request.args` names `product_add`'s GET reads, and the set
# `product_search` forwards into its own "Create a new product" link. A fixed
# whitelist rather than `request.args` wholesale: the form round-trips whatever
# it is handed into `form_data`, so an unbounded read would let any query string
# put arbitrary keys in front of the operator.
_PRODUCT_PREFILL_ARGS = (
    'description', 'manufacturer', 'mpn', 'category_path', 'tags', 'notes',
    'identifier_type', 'identifier_value',
    'quantity', 'order_number', 'vendor', 'vendor_sku',
    'duplicate_of',
)

# The create form's optional first-receipt block. Present-and-non-blank on any
# one of them is what makes `product_add` record a Purchase.
_RECEIPT_FIELDS = ('quantity', 'order_number', 'vendor', 'vendor_sku')


def _identifier_type_choices():
    """The identifier types the create form may attach (FR40).

    INTERNAL is excluded because `add_identifier` refuses it: that row is
    derived from `products.internal_id` by `create_product` in one transaction,
    and letting it be added by hand is how the index would come to disagree with
    the column it mirrors. Built here and passed to the template so the enum
    stays out of Jinja.
    """
    return [t.value for t in IdentifierType if t is not IdentifierType.INTERNAL]


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
    `_validate_product_form` on POST, so a too-long pre-fill earns a field
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

    No `vendor` is passed. `add_identifier` would take the receipt block's
    "Vendor" input as this identifier's `vendor_scope` for a vendor-scoped type,
    silently coupling two inputs the form presents as unrelated — the create
    form offers no vendor-scope control, so it supplies none.
    """
    value = (form_data.get('identifier_value') or '').strip()
    if not value:
        return None
    identifier_type = (form_data.get('identifier_type') or '').strip()
    try:
        service.add_identifier(product_id, identifier_type=identifier_type,
                               value=value)
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

    One Purchase, only when at least one receipt field is non-blank. Returns an
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
    if not any(values.values()):
        return None
    # `_validate_product_form` has already proved this parses; the fallback is
    # for a caller that reached here another way.
    quantity = _positive_int_string(values['quantity'])
    try:
        snapshot = service.record_purchase(
            product_id,
            vendor=values['vendor'] or None,
            vendor_sku=values['vendor_sku'] or None,
            quantity=quantity,
            order_number=values['order_number'] or None,
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
                           identifier_type_choices=_identifier_type_choices())


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
    `_validate_product_form`, so it runs before any of it (FR41).
    """
    if request.method == 'GET':
        return _render_product_add(_prefill_form_data(), {})

    form_data = request.form.to_dict()
    log_audit_operation('product_add', 'input', form_data=form_data)

    validation_errors = _validate_product_form(form_data)
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


@bp.route('/products/<int:product_id>')
def product_detail(product_id):
    """View a Product by its direct URL (FR6), with purchase history (FR20/FR21).

    Story 4.5: when the URL carries `scan_kind`, the page additionally shows the
    scan-arrival banner (FR41). Without it nothing changes.
    """
    service = _get_catalog_service()
    product = service.get_product(product_id)
    if product is None:
        abort(404)
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
    if price != price.quantize(_UNIT_PRICE_STEP):
        return None, 'Unit Price must have at most two decimal places.'
    return price, None


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


def _parse_purchase_form(form_data):
    """Parse the HTML purchase form into the typed values the service takes.

    Returns `(values, errors)`. The bounds on `unit_price` and on the text
    columns live in `_purchase_unit_price` and `_purchase_text_length_error`,
    which `api_record_purchase` applies to those same columns, so the two entry
    points cannot come to disagree about them; the only difference is the shape
    of the refusal (a field message on a re-render rather than the AD-13 JSON
    envelope).

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

    for name, label in (('order_date', 'Order Date'),
                        ('received_date', 'Received Date')):
        raw_date = (form_data.get(name) or '').strip()
        values[name] = None
        if raw_date:
            try:
                values[name] = date.fromisoformat(raw_date)
            except ValueError:
                errors[name] = f'{label} must be an ISO date (YYYY-MM-DD).'

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

    body = request.get_json(silent=True) or {}

    # Parse/validate typed fields at the boundary; the service takes typed values.
    # `unit_price` and the four text columns are bounded by the same two helpers
    # the HTML form applies (`_parse_purchase_form`), so the two entry points
    # cannot disagree about THOSE columns; only the shape of the refusal
    # differs. `quantity` below is deliberately not shared — see that
    # function's docstring. The helpers' human-readable message is reused
    # verbatim: `error.field` already carries the machine name a client keys on,
    # and a second message string is exactly the divergence sharing them avoids.
    #
    # First failure wins, and the text columns are judged first, so a body with
    # several bad fields names the earliest one in `_PURCHASE_FIELD_LIMITS`.
    # AD-13's envelope carries one `field`; the caller fixes and re-POSTs.
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

    try:
        quantity = body.get('quantity')
        quantity = int(quantity) if quantity not in (None, '') else None
    except (TypeError, ValueError):
        return _catalog_json_error('invalid_field', 'quantity must be an integer', 400, field='quantity')

    def _parse_date(value, field):
        if value in (None, ''):
            return None, None
        try:
            return date.fromisoformat(str(value)), None
        except ValueError:
            return None, _catalog_json_error('invalid_field', f'{field} must be an ISO date (YYYY-MM-DD)', 400, field=field)

    order_date, err = _parse_date(body.get('order_date'), 'order_date')
    if err:
        return err
    received_date, err = _parse_date(body.get('received_date'), 'received_date')
    if err:
        return err

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
    happens here, at the pre-fill boundary, and nowhere else.

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


def _scan_search_text(classification):
    """The text `resolve_scan`'s fallthrough search actually ran on.

    A second copy of a service-internal rule, and stated as one. AD-15 freezes
    `ScanResolution` to three fields, so the searched text is not returned and a
    fourth field must not be added — but it IS a pure function of the
    classification, so it is re-derived here, mirroring
    `mariadb_catalog_service.resolve_scan`'s per-arm `fallthrough_text` exactly:

    - `internal` -> `normalized_value` (the bare, token-stripped id, which is
      what the column stores; the `<ai><token>` prefix is in no column),
    - `gtin` and `free_text` -> the AIM-stripped raw scan,
    - `ecia` -> the first non-blank of the `.strip()`ed `1P` then `P`.

    Because this is a duplicate, `TestSearchTextAgreesWithTheResolver` asserts
    for every `ScanKind` that `search_products(_scan_search_text(c))` returns
    exactly `resolve_scan(raw).free_text_hits` — so the search page can never
    show a different set than `hit_count` promised, and a change to either rule
    turns a test red.
    """
    kind = classification.kind
    if kind is ScanKind.INTERNAL:
        return classification.normalized_value
    if kind is ScanKind.ECIA:
        fields = classification.ecia_fields or {}
        for key in ('1P', 'P'):
            value = (fields.get(key) or '').strip()
            if value:
                return value
        # An envelope carrying only quantity/order/date identifiers: the
        # resolver issues no query at all, and `search_products('')` is `[]`.
        return ''
    return scan_router.strip_aim_prefix(classification.raw)


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
    it is not claimed away here. `_scan_search_text` itself is uncapped, so
    `TestSearchTextAgreesWithTheResolver` still pins the derivation rule.

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
    value for the query itself. Nothing is lost by the exemption:
    `sql_text.is_storable_text` refuses NUL and unpaired surrogates outright,
    so a scan carrying either has no hits and never reaches the search arm at
    all.

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


def _scan_destination(resolution):
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
            q=_scan_url_value('q', _scan_search_text(classification)), **prefill)
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
    unauthenticated, unthrottled cross-site POST here costs up to two sessions
    and a leading-wildcard `LIKE` over six unindexed columns with a pattern of
    up to `MAX_SCAN_LENGTH` characters — a full table scan per request. That is
    a denial-of-service shape, not a one-SELECT shape. The exemption stays
    (removing it would break the wedge path this endpoint exists for), and the
    two ledger entries aimed at it — the CSRF exemption itself and rate
    limiting — stay open and now have the real cost written against them.

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
        resolution = _get_catalog_service().resolve_scan(cleaned)
        outcome, url = _scan_destination(resolution)
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
        return render_template(
            'product/edit.html', title=title, product=product,
            form_data=_product_form_data(
                product, service.get_tags_for_product(product_id)),
            validation_errors={})

    form_data = request.form.to_dict()
    log_audit_operation('product_edit', 'input', item_id=str(product_id),
                        form_data=form_data)

    validation_errors = _validate_product_form(form_data)
    if validation_errors:
        # Re-render with the SUBMITTED values so the user's in-flight edits
        # survive the validation error (mirrors add.html's form_data round-trip).
        return render_template('product/edit.html', title=title, product=product,
                               form_data=form_data,
                               validation_errors=validation_errors)

    # Parsed before the write, for the reason product_add gives.
    tags = _form_tags(form_data)

    try:
        # Only update fields actually present in the POST body: an absent key
        # means "not provided", not "clear this" — a present-but-empty field
        # still clears (the service coerces blanks to NULL).
        update_fields = {'description': form_data.get('description')}
        for field in ('manufacturer', 'mpn', 'category_path', 'notes'):
            if field in form_data:
                update_fields[field] = form_data[field]

        ok = service.update_product(product_id, **update_fields)
        if not ok:
            flash('Failed to update product. Please try again.', 'error')
            return render_template('product/edit.html', title=title, product=product,
                                   form_data=form_data, validation_errors={})
        if tags is not None:
            # Present-but-empty clears every tag; an ABSENT key leaves them
            # alone, the same partial-update rule as the fields above.
            tag_error = _apply_product_tags(service, product_id, tags)
            if tag_error:
                flash(tag_error, 'error')
                return redirect(url_for('main.product_detail', product_id=product_id))
        flash('Product updated successfully!', 'success')
        return redirect(url_for('main.product_detail', product_id=product_id))
    except Exception as e:
        current_app.logger.error(f'Error updating product {product_id}: {e}\n{traceback.format_exc()}')
        flash('An error occurred while updating the product. Please try again.', 'error')
        return render_template('product/edit.html', title=title, product=product,
                               form_data=form_data, validation_errors={})


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


@bp.route('/api/inventory/field-suggestions/<field>')
def inventory_field_suggestions(field):
    """Return distinct existing values for a whitelisted field.

    Used by the Add/Edit Item forms to autocomplete free-form fields
    (Thread Size, Purchase Location, Vendor, Location, Sub-Location), and
    since Story 3.1 by the product form's Category field.

    ONE endpoint, two sources (AD-14): fields in the catalog whitelist are
    served by CatalogService (products), everything else by InventoryService
    (inventory_items) exactly as before. Catalog-sourced responses carry an
    extra `normalized` key — the canonical form of the query, which the
    autocomplete-with-create UI displays so the browser never reimplements
    normalization. The five pre-existing fields keep byte-identical request
    handling and response bodies, `normalized` included (i.e. absent).
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
        from app.mariadb_storage import MariaDBStorage
        from sqlalchemy.orm import sessionmaker
        
        # Use injected storage backend if available (for testing), otherwise create new one
        if current_app.config.get('STORAGE_BACKEND'):
            storage = current_app.config['STORAGE_BACKEND']
            engine = storage.engine
        else:
            # Create MariaDB storage and session directly
            storage = MariaDBStorage()
            storage.connect()
            engine = storage.engine
            
        Session = sessionmaker(bind=engine)
        session = Session()
        
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
            service = InventoryExportService()
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
            service = MaterialsExportService()
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
            service = CombinedExportService()
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
        service = CombinedExportService()
        
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

