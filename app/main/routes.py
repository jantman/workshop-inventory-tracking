from flask import render_template, current_app, jsonify, abort, request, flash, redirect, url_for, send_file
from datetime import datetime
from app.main import bp
from app import csrf
from app.mariadb_storage import MariaDBStorage
# Using unified InventoryService (MariaDB-based implementation)
from app.mariadb_inventory_service import InventoryService
# Performance optimizations removed - no longer needed with MariaDB
from app.taxonomy import type_shape_validator
from app.models import ItemType, ItemShape, Dimensions, Thread, ThreadSeries, ThreadHandedness
from app.database import InventoryItem
from app.error_handlers import with_error_handling, ErrorHandler
from app.exceptions import ValidationError, StorageError, ItemNotFoundError
from app.logging_config import log_audit_operation, log_audit_batch_operation
from decimal import Decimal, InvalidOperation
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


def _create_single_item(service, form_data, bulk_context=None):
    """
    Helper function to create a single item from form data and log the operation.

    Args:
        service: InventoryService instance
        form_data: Dictionary of form data for the item
        bulk_context: Optional dict with 'index' and 'total' for bulk creation logging

    Returns:
        Tuple of (success: bool, ja_id: str, error_message: str or None)
    """
    try:
        item = _parse_item_from_form(form_data)

        # Build context for logging
        context = None
        if bulk_context:
            context = {
                'bulk_creation': True,
                'bulk_index': bulk_context['index'],
                'bulk_total': bulk_context['total']
            }

        return _add_item_with_logging(service, item, 'add_item', context)

    except Exception as e:
        error_msg = str(e)
        current_app.logger.error(f'Error creating item: {error_msg}')
        return (False, form_data.get('ja_id'), error_msg)


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
        # Get form data
        form_data = request.form.to_dict()

        # AUDIT: Log input phase with complete form data
        log_audit_operation('add_item', 'input',
                          item_id=form_data.get('ja_id'),
                          form_data=form_data)
        
        # Validate required fields
        required_fields = ['ja_id', 'item_type', 'shape', 'material', 'location']
        missing_fields = [field for field in required_fields if not form_data.get(field)]
        
        if missing_fields:
            error_msg = f'Missing required fields: {", ".join(missing_fields)}'
            # AUDIT: Log validation error
            log_audit_operation('add_item', 'error', 
                              item_id=form_data.get('ja_id'), 
                              error_details=error_msg)
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400
        
        # Validate material is in taxonomy
        material = form_data.get('material', '').strip()
        valid_materials = _get_valid_materials()
        # Defensive: handle case where valid_materials might be None or contain None values
        valid_materials_lower = [m.lower() for m in (valid_materials or []) if m]

        if material and valid_materials_lower and material.lower() not in valid_materials_lower:
            error_msg = f'Material "{material}" is not valid. Please select from materials taxonomy.'
            # AUDIT: Log validation error
            log_audit_operation('add_item', 'error', 
                              item_id=form_data.get('ja_id'), 
                              error_details=error_msg)
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400
        
        # Check for bulk creation (quantity_to_create > 1)
        quantity_to_create = int(form_data.get('quantity_to_create', '1'))
        current_app.logger.info(f'Add item: quantity_to_create={quantity_to_create} from form_data')

        # Validate quantity range
        if quantity_to_create < 1 or quantity_to_create > 100:
            error_msg = 'Quantity to create must be between 1 and 100'
            log_audit_operation('add_item', 'error',
                              item_id=form_data.get('ja_id'),
                              error_details=error_msg)
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400

        service = _get_inventory_service()
        storage = _get_storage_backend()

        if quantity_to_create == 1:
            # Single item creation
            success, ja_id, error_msg = _create_single_item(service, form_data)

            if success:
                flash('Item added successfully!', 'success')

                # Check submission type
                submit_type = request.form.get('submit_type')
                current_app.logger.info(f'Add item workflow: submit_type="{submit_type}" for item {ja_id}')

                if submit_type == 'continue':
                    current_app.logger.info(f'Add & Continue: Redirecting to add form after successfully adding item {ja_id}')
                    log_audit_operation('add_item', 'continue_workflow',
                                      item_id=ja_id)
                    return redirect(url_for('main.inventory_add'))
                else:
                    current_app.logger.info(f'Normal Add: Redirecting to inventory list after adding item {ja_id}')
                    return redirect(url_for('main.inventory_list'))
            else:
                flash('Failed to add item. Please try again.', 'error')
                return redirect(url_for('main.inventory_add'))
        else:
            # Bulk creation (quantity_to_create > 1)
            current_app.logger.info(f'Bulk creation: Creating {quantity_to_create} items starting from {form_data.get("ja_id")}')

            # Get next available JA IDs
            all_items = service.get_all_items()
            if all_items:
                max_number = 0
                for existing_item in all_items:
                    ja_id = existing_item.ja_id
                    if ja_id.startswith('JA') and len(ja_id) == 8:
                        try:
                            number = int(ja_id[2:])
                            max_number = max(max_number, number)
                        except ValueError:
                            continue
                next_number = max_number + 1
            else:
                next_number = 1

            # Get the starting JA ID from form (user may have entered a specific one)
            starting_ja_id = form_data.get('ja_id', '').strip()
            if starting_ja_id and starting_ja_id.startswith('JA'):
                try:
                    starting_number = int(starting_ja_id[2:])
                    # Use whichever is higher: user's choice or next available
                    next_number = max(next_number, starting_number)
                except ValueError:
                    pass  # Use calculated next_number

            created_ja_ids = []

            # Create N items with sequential JA IDs
            for i in range(quantity_to_create):
                ja_id = f"JA{next_number:06d}"
                next_number += 1

                # Create a copy of form_data with the new JA ID
                item_form_data = form_data.copy()
                item_form_data['ja_id'] = ja_id

                # Create the item using helper function
                bulk_context = {'index': i+1, 'total': quantity_to_create}
                success, created_ja_id, error_msg = _create_single_item(service, item_form_data, bulk_context)

                if success:
                    created_ja_ids.append(created_ja_id)
                else:
                    current_app.logger.error(f'Failed to create item {i+1}/{quantity_to_create}: {ja_id} - {error_msg}')

            if len(created_ja_ids) == quantity_to_create:
                # All items created successfully
                first_ja_id = created_ja_ids[0]
                last_ja_id = created_ja_ids[-1]

                current_app.logger.info(f'Bulk creation complete: Created {len(created_ja_ids)} items ({first_ja_id} - {last_ja_id})')

                # Return JSON response for bulk creation
                return jsonify({
                    'success': True,
                    'count': len(created_ja_ids),
                    'ja_ids': created_ja_ids,
                    'message': f'Successfully created {len(created_ja_ids)} items: {first_ja_id} - {last_ja_id}'
                }), 200
            elif len(created_ja_ids) > 0:
                # Partial success
                error_msg = f'Created {len(created_ja_ids)} of {quantity_to_create} items. Some items failed.'
                log_audit_operation('add_item', 'error',
                                  error_details=error_msg,
                                  form_data={
                                      'bulk_creation': True,
                                      'bulk_total': quantity_to_create,
                                      'bulk_succeeded': len(created_ja_ids)
                                  })
                return jsonify({
                    'success': False,
                    'count': len(created_ja_ids),
                    'ja_ids': created_ja_ids,
                    'error': error_msg
                }), 500
            else:
                # Complete failure
                error_msg = 'Failed to create any items'
                log_audit_operation('add_item', 'error',
                                  error_details=error_msg,
                                  form_data={
                                      'bulk_creation': True,
                                      'bulk_total': quantity_to_create
                                  })
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), 500
            
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
        item = service.get_item_any_status(ja_id)
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

@bp.route('/api/items/<ja_id>/duplicate', methods=['POST'])
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
            # Update source item with changed fields
            for field, value in updated_fields.items():
                if hasattr(source_item, field):
                    setattr(source_item, field, value)
            service.update_item(source_item)
            # Reload the item to get fresh data
            source_item = service.get_item(ja_id)

        # Get next available JA IDs
        all_items = service.get_all_items()
        if all_items:
            max_number = 0
            for existing_item in all_items:
                existing_ja_id = existing_item.ja_id
                if existing_ja_id.startswith('JA') and len(existing_ja_id) == 8:
                    try:
                        number = int(existing_ja_id[2:])
                        max_number = max(max_number, number)
                    except ValueError:
                        continue
            next_number = max_number + 1
        else:
            next_number = 1

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
    return render_template('inventory/search.html', title='Search',
                         ItemType=ItemType, ItemShape=ItemShape, ThreadSeries=ThreadSeries)

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


@bp.route('/api/materials/hierarchy')
def materials_hierarchy():
    """Get hierarchical materials taxonomy (for testing)"""
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
        
        # Get all items to find the highest JA ID
        all_items = service.get_all_items()
        
        if not all_items:
            # No items exist, start with JA000001
            next_id = "JA000001"
        else:
            # Find the highest numeric part
            max_number = 0
            for item in all_items:
                ja_id = item.ja_id
                if ja_id.startswith('JA') and len(ja_id) == 8:
                    try:
                        number = int(ja_id[2:])
                        max_number = max(max_number, number)
                    except ValueError:
                        continue
            
            # Generate next ID
            next_number = max_number + 1
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
        
        # Material filter
        if data.get('material'):
            exact_match = data.get('material_exact', False)
            if isinstance(exact_match, str):
                exact_match = exact_match.lower() == 'true'
            search_filter.add_text_search('material', data['material'], exact=exact_match)
        
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

