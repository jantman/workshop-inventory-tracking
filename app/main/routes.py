from flask import render_template, current_app, jsonify, abort, request, flash, redirect, url_for
from datetime import datetime
from app.main import bp
from app import csrf
from app.google_sheets_storage import GoogleSheetsStorage
from app.mariadb_storage import MariaDBStorage
from app.inventory_service import InventoryService
from app.mariadb_inventory_service import MariaDBInventoryService
from app.performance import batch_manager
from app.taxonomy import type_shape_validator
from app.models import Item, ItemType, ItemShape, Dimensions, Thread, ThreadSeries, ThreadHandedness
from app.error_handlers import with_error_handling, ErrorHandler
from app.exceptions import ValidationError, StorageError, ItemNotFoundError
from decimal import Decimal, InvalidOperation
import traceback
from config import Config

def _get_storage_backend():
    """Get the appropriate storage backend for the current app context"""
    # Check if test storage is injected
    if 'STORAGE_BACKEND' in current_app.config:
        return current_app.config['STORAGE_BACKEND']
    
    # Use MariaDB storage (switched from Google Sheets in Milestone 2)
    return MariaDBStorage()

def _get_inventory_service():
    """Get the appropriate inventory service for the current storage backend"""
    storage = _get_storage_backend()
    
    # Use MariaDB-specific service for MariaDB storage
    if isinstance(storage, MariaDBStorage):
        return MariaDBInventoryService(storage)
    else:
        # Fallback to generic service for other storage types (e.g., tests)
        return InventoryService(storage)

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
    return render_template('inventory/list.html', title='Inventory')

@bp.route('/inventory/add', methods=['GET', 'POST'])
def inventory_add():
    """Add new inventory item"""
    if request.method == 'GET':
        return render_template('inventory/add.html', title='Add Item', 
                             ItemType=ItemType, ItemShape=ItemShape)
    
    # Handle POST request for adding item
    try:
        # Get form data
        form_data = request.form.to_dict()
        
        # Validate required fields
        required_fields = ['ja_id', 'item_type', 'shape', 'material']
        missing_fields = [field for field in required_fields if not form_data.get(field)]
        
        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        # Parse form data into models
        item = _parse_item_from_form(form_data)
        
        # Save to storage
        service = _get_inventory_service()
        storage = _get_storage_backend()
        
        result = service.add_item(item)
        
        if result:
            # Force flush pending add_items batch to ensure item is immediately available for E2E tests
            pending_items = batch_manager.get_batch('add_items')
            if pending_items:
                # Process any remaining items in the batch
                rows_to_add = [entry['row'] for entry in pending_items]
                batch_result = storage.write_rows('Metal', rows_to_add)
                if batch_result.success:
                    # Clear cache since we added items
                    service.get_all_items.cache_clear()
                    current_app.logger.info(f"Force-flushed batch of {len(pending_items)} items after form submission")
            
            flash('Item added successfully!', 'success')
            if request.form.get('submit_type') == 'continue':
                return redirect(url_for('main.inventory_add'))
            else:
                return redirect(url_for('main.inventory_list'))
        else:
            flash('Failed to add item. Please try again.', 'error')
            return redirect(url_for('main.inventory_add'))
            
    except ValueError as e:
        current_app.logger.error(f'Validation error adding item: {e}')
        flash(f'Validation error: {str(e)}', 'error')
        return redirect(url_for('main.inventory_add'))
    except Exception as e:
        current_app.logger.error(f'Error adding item: {e}\n{traceback.format_exc()}')
        flash('An error occurred while adding the item. Please try again.', 'error')
        return redirect(url_for('main.inventory_add'))

@bp.route('/inventory/edit/<ja_id>', methods=['GET', 'POST'])
def inventory_edit(ja_id):
    """Edit inventory item"""
    try:
        service = _get_inventory_service()
        
        # Get the item
        item = service.get_item(ja_id)
        if not item:
            flash(f'Item {ja_id} not found.', 'error')
            return redirect(url_for('main.inventory_list'))
        
        if request.method == 'GET':
            # Populate form with existing item data
            return render_template('inventory/edit.html', title=f'Edit {ja_id}', 
                                 item=item, ItemType=ItemType, ItemShape=ItemShape)
        
        # Handle POST request for updating item
        form_data = request.form.to_dict()
        
        # Validate required fields
        required_fields = ['ja_id', 'item_type', 'shape', 'material']
        missing_fields = [field for field in required_fields if not form_data.get(field)]
        
        if missing_fields:
            flash(f'Missing required fields: {", ".join(missing_fields)}', 'error')
            return redirect(url_for('main.inventory_edit', ja_id=ja_id))
        
        # Parse form data into updated item
        updated_item = _parse_item_from_form(form_data)
        
        # Update the item (preserve dates from original)
        updated_item.date_added = item.date_added
        updated_item.last_modified = datetime.now()
        result = service.update_item(updated_item)
        
        if result:
            flash('Item updated successfully!', 'success')
            return redirect(url_for('main.inventory_list'))
        else:
            flash('Failed to update item. Please try again.', 'error')
            return redirect(url_for('main.inventory_edit', ja_id=ja_id))
            
    except ValueError as e:
        current_app.logger.error(f'Validation error updating item {ja_id}: {e}')
        flash(f'Validation error: {str(e)}', 'error')
        return redirect(url_for('main.inventory_edit', ja_id=ja_id))
    except Exception as e:
        current_app.logger.error(f'Error updating item {ja_id}: {e}\n{traceback.format_exc()}')
        flash('An error occurred while updating the item. Please try again.', 'error')
        return redirect(url_for('main.inventory_list'))

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
                         ItemType=ItemType, ItemShape=ItemShape)

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
        
        # Validate required fields
        required_fields = ['source_ja_id', 'new_length', 'confirm_operation']
        missing_fields = [field for field in required_fields if not form_data.get(field)]
        
        if missing_fields:
            flash(f'Missing required fields: {", ".join(missing_fields)}', 'error')
            return redirect(url_for('main.inventory_shorten'))
        
        if form_data.get('confirm_operation') != 'on':
            flash('You must confirm the shortening operation', 'error')
            return redirect(url_for('main.inventory_shorten'))
        
        # Execute shortening operation
        result = _execute_shortening_operation(form_data)
        
        if result['success']:
            original_length = result.get('original_length')
            new_length = result.get('new_length')
            ja_id = result.get('ja_id')
            
            if original_length and new_length:
                flash(f"Item {ja_id} successfully shortened from {original_length}\" to {new_length}\"! History preserved.", 'success')
            else:
                flash(f"Item {ja_id} successfully shortened! History preserved.", 'success')
            return redirect(url_for('main.inventory_shorten'))
        else:
            flash(f"Shortening failed: {result['error']}", 'error')
            return redirect(url_for('main.inventory_shorten'))
            
    except Exception as e:
        current_app.logger.error(f'Error in shortening operation: {e}\n{traceback.format_exc()}')
        flash('An error occurred during the shortening operation. Please try again.', 'error')
        return redirect(url_for('main.inventory_shorten'))

# API Routes
@bp.route('/api/connection-test')
def connection_test():
    """Test API endpoint for Google Sheets connection"""
    try:
        if not Config.GOOGLE_SHEET_ID:
            return jsonify({
                'success': False,
                'error': 'GOOGLE_SHEET_ID not configured'
            }), 500
        
        storage = _get_storage_backend()
        result = storage.connect()
        
        if result.success:
            return jsonify({
                'success': True,
                'message': 'Connected to Google Sheets successfully',
                'data': result.data
            })
        else:
            return jsonify({
                'success': False,
                'error': result.error
            }), 500
            
    except Exception as e:
        current_app.logger.error(f'Connection test failed: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/api/stats')
def api_stats():
    """API endpoint for dashboard statistics"""
    try:
        from app.inventory_service import InventoryService
        
        # Get inventory service
        service = _get_inventory_service()
        
        # Get all items
        items = service.get_all_items()
        
        # Calculate statistics
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
    """Get material suggestions from hierarchical taxonomy"""
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', '10')
    level = request.args.get('level')  # Filter by hierarchy level (1=Category, 2=Family, 3=Material)
    parent = request.args.get('parent')  # Filter by parent name
    
    try:
        limit = int(limit)
        limit = min(max(limit, 1), 20)  # Clamp between 1 and 20
    except (ValueError, TypeError):
        limit = 10
    
    try:
        level_int = int(level) if level else None
        if level_int and level_int not in [1, 2, 3]:
            level_int = None
    except (ValueError, TypeError):
        level_int = None
    
    try:
        from app.materials_service import MaterialHierarchyService
        
        # Get storage backend
        storage_backend = current_app.config.get('STORAGE_BACKEND')
        if storage_backend:
            # Use injected storage backend (for testing)
            storage = storage_backend
        else:
            # Use default Google Sheets storage for production
            from app.google_sheets_storage import GoogleSheetsStorage
            from config import Config
            storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
        
        # Initialize material hierarchy service
        materials_service = MaterialHierarchyService(storage)
        
        # Get suggestions using the new service
        suggestions = materials_service.get_suggestions(
            query=query,
            level=level_int,
            parent=parent,
            limit=limit
        )
        
        # Return just the material names for backward compatibility with existing autocomplete
        material_names = [suggestion['name'] for suggestion in suggestions]
        return jsonify(material_names)
        
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
        from app.materials_service import MaterialHierarchyService
        
        # Get storage backend
        storage_backend = current_app.config.get('STORAGE_BACKEND')
        if storage_backend:
            storage = storage_backend
        else:
            from app.google_sheets_storage import GoogleSheetsStorage
            from config import Config
            storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
        
        materials_service = MaterialHierarchyService(storage)
        
        # Get categories and their children
        categories = materials_service.get_categories()
        hierarchy = []
        
        for category in categories:
            families = materials_service.get_children(category.name)
            category_data = {
                'name': category.name,
                'level': category.level,
                'notes': category.notes,
                'families': []
            }
            
            for family in families:
                materials = materials_service.get_children(family.name)
                family_data = {
                    'name': family.name,
                    'level': family.level,
                    'parent': family.parent,
                    'notes': family.notes,
                    'materials': [{'name': m.name, 'level': m.level, 'parent': m.parent, 'aliases': m.aliases, 'notes': m.notes} for m in materials]
                }
                category_data['families'].append(family_data)
            
            hierarchy.append(category_data)
        
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
        
        return jsonify({
            'success': True,
            'item': {
                'ja_id': item.ja_id,
                'display_name': item.display_name,
                'item_type': item.item_type.value,
                'shape': item.shape.value,
                'material': item.material,
                'location': item.location,
                'sub_location': item.sub_location,
                'active': item.active,
                'dimensions': item.dimensions.to_dict() if item.dimensions else None
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
                'item_type': item.item_type.value if item.item_type else None,
                'shape': item.shape.value if item.shape else None,
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
            return jsonify({
                'success': False,
                'error': 'Invalid request data'
            }), 400
        
        moves = data['moves']
        if not moves or not isinstance(moves, list):
            return jsonify({
                'success': False,
                'error': 'No moves provided'
            }), 400
        
        service = _get_inventory_service()
        
        successful_moves = 0
        failed_moves = []
        
        for move in moves:
            ja_id = move.get('ja_id')
            new_location = move.get('new_location')
            
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
                
                # Update location
                old_location = item.location
                item.location = new_location.strip()
                
                # Save the updated item
                if service.update_item(item):
                    successful_moves += 1
                    current_app.logger.info(f'Moved {ja_id} from "{old_location}" to "{new_location}"')
                else:
                    failed_moves.append({
                        'ja_id': ja_id,
                        'error': 'Failed to update item'
                    })
                    
            except Exception as e:
                current_app.logger.error(f'Error moving item {ja_id}: {e}')
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
        
        return jsonify(response_data)
        
    except Exception as e:
        current_app.logger.error(f'Batch move error: {e}\n{traceback.format_exc()}')
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

@bp.route('/api/inventory/list')
def api_inventory_list():
    """Get inventory list data for the frontend"""
    try:
        service = _get_inventory_service()
        
        # Get all items
        items = service.get_all_items()
        
        # Convert to JSON-serializable format
        items_data = []
        for item in items:
            item_data = {
                'ja_id': item.ja_id,
                'display_name': item.display_name,
                'item_type': item.item_type.value,
                'shape': item.shape.value,
                'material': item.material,
                'dimensions': item.dimensions.to_dict() if item.dimensions else None,
                'thread': item.thread.to_dict() if item.thread else None,
                'quantity': item.quantity,
                'location': item.location,
                'sub_location': item.sub_location,
                'purchase_date': item.purchase_date.isoformat() if item.purchase_date else None,
                'purchase_price': str(item.purchase_price) if item.purchase_price else None,
                'purchase_location': item.purchase_location,
                'vendor': item.vendor,
                'vendor_part_number': item.vendor_part_number,
                'notes': item.notes,
                'active': item.active,
                'parent_ja_id': item.parent_ja_id,
                'child_ja_ids': list(item.child_ja_ids) if item.child_ja_ids else [],
                'date_added': item.date_added.isoformat() if item.date_added else None,
                'last_modified': item.last_modified.isoformat() if item.last_modified else None
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
        from app.inventory_service import SearchFilter
        
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
                item_type = ItemType[data['item_type'].upper()]
                search_filter.add_exact_match('item_type', item_type)
            except KeyError:
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid item type: {data["item_type"]}'
                }), 400
        
        if data.get('shape'):
            try:
                shape = ItemShape[data['shape'].upper()]
                search_filter.add_exact_match('shape', shape)
            except KeyError:
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid shape: {data["shape"]}'
                }), 400
        
        # Active/inactive filter
        if 'active' in data and data['active'] is not None:
            if isinstance(data['active'], bool):
                search_filter.add_exact_match('active', data['active'])
            elif isinstance(data['active'], str):
                search_filter.add_exact_match('active', data['active'].lower() == 'true')
        
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
                        'status': 'error',
                        'message': f'Invalid {field} range values'
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
                    'status': 'error',
                    'message': f'Invalid thread series: {data["thread_series"]}'
                }), 400
        
        if data.get('thread_form'):
            # Import ThreadForm here
            from app.models import ThreadForm
            try:
                thread_form = ThreadForm[data['thread_form'].upper()]
                search_filter.add_exact_match('thread_form', thread_form)
            except KeyError:
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid thread form: {data["thread_form"]}'
                }), 400
        
        # Execute search
        items = service.search_items(search_filter)
        
        # Convert to JSON-serializable format
        items_data = []
        for item in items:
            item_data = {
                'ja_id': item.ja_id,
                'display_name': item.display_name,
                'item_type': item.item_type.value,
                'shape': item.shape.value,
                'material': item.material,
                'dimensions': item.dimensions.to_dict() if item.dimensions else None,
                'thread': item.thread.to_dict() if item.thread else None,
                'quantity': item.quantity,
                'location': item.location,
                'sub_location': item.sub_location,
                'purchase_date': item.purchase_date.isoformat() if item.purchase_date else None,
                'purchase_price': str(item.purchase_price) if item.purchase_price else None,
                'purchase_location': item.purchase_location,
                'vendor': item.vendor,
                'vendor_part_number': item.vendor_part_number,
                'notes': item.notes,
                'active': item.active,
                'parent_ja_id': item.parent_ja_id,
                'child_ja_ids': list(item.child_ja_ids) if item.child_ja_ids else [],
                'date_added': item.date_added.isoformat() if item.date_added else None,
                'last_modified': item.last_modified.isoformat() if item.last_modified else None
            }
            items_data.append(item_data)
        
        return jsonify({
            'status': 'success',
            'items': items_data,
            'total_count': len(items_data),
            'search_criteria': data
        })
        
    except Exception as e:
        current_app.logger.error(f'Advanced search error: {e}\n{traceback.format_exc()}')
        return jsonify({
            'status': 'error',
            'message': 'Search operation failed',
            'error': str(e)
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
    """Parse form data into an Item object"""
    # Parse enums
    item_type = ItemType[form_data['item_type'].upper()]
    shape = ItemShape[form_data['shape'].upper()]
    
    # Parse dimensions
    dimensions_data = {}
    dimension_fields = ['length', 'width', 'thickness', 'wall_thickness', 'weight']
    
    for field in dimension_fields:
        value = form_data.get(field, '').strip()
        if value:
            try:
                # Handle fraction input
                dimensions_data[field] = _parse_dimension_value(value)
            except (ValueError, InvalidOperation) as e:
                raise ValueError(f"Invalid {field}: {value}")
    
    dimensions = Dimensions.from_dict(dimensions_data) if dimensions_data else None
    
    # Parse threading if provided
    thread = None
    thread_series_str = form_data.get('thread_series', '').strip()
    if thread_series_str and thread_series_str != 'None':
        thread_handedness_str = form_data.get('thread_handedness', 'RH').strip() or 'RH'
        thread_size = form_data.get('thread_size', '').strip()
        
        try:
            thread_series = ThreadSeries[thread_series_str.upper()]
            thread_handedness = ThreadHandedness.RIGHT if thread_handedness_str.upper() == 'RH' else ThreadHandedness.LEFT
            
            thread = Thread(
                series=thread_series,
                handedness=thread_handedness,
                size=thread_size or None
            )
        except KeyError:
            raise ValueError(f"Invalid thread series or handedness: {thread_series_str}, {thread_handedness_str}")
    
    # Parse other fields
    quantity = form_data.get('quantity', '1')
    try:
        quantity = int(quantity) if quantity else 1
    except ValueError:
        quantity = 1
    
    active = form_data.get('active') == 'on'
    
    # Material is now handled by hierarchical taxonomy - use as provided
    material = form_data['material'].strip()
    
    # Create item
    item = Item(
        ja_id=form_data['ja_id'].upper(),
        item_type=item_type,
        shape=shape,
        material=material,
        dimensions=dimensions,
        thread=thread,
        quantity=quantity,
        location=form_data.get('location', '').strip() or None,
        sub_location=form_data.get('sub_location', '').strip() or None,
        purchase_date=form_data.get('purchase_date') or None,
        purchase_price=form_data.get('purchase_price', '').strip() or None,
        purchase_location=form_data.get('purchase_location', '').strip() or None,
        vendor=form_data.get('vendor', '').strip() or None,
        vendor_part_number=form_data.get('vendor_part_number', '').strip() or None,
        notes=form_data.get('notes', '').strip() or None,
        active=active
    )
    
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

# Export Endpoints
@bp.route('/admin/export')
def admin_export():
    """Admin page for data export functionality"""
    return render_template('admin/export.html', title='Data Export')

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
            # Return JSON data directly
            return jsonify({
                'success': True,
                'export_data': result,
                'timestamp': result.get('timestamp'),
                'export_type': export_type
            })
            
        elif destination == 'sheets':
            # Upload to Google Sheets
            upload_result = _upload_to_google_sheets(result, export_type)
            
            if upload_result['success']:
                return jsonify({
                    'success': True,
                    'message': f'Export to Google Sheets completed successfully',
                    'export_type': export_type,
                    'upload_details': upload_result
                })
            else:
                return jsonify({
                    'success': False,
                    'error': f'Export completed but Google Sheets upload failed: {upload_result["error"]}',
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

# Error handlers for the blueprint
@bp.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@bp.errorhandler(500)
def internal_error(error):
    current_app.logger.error(f'Server Error: {error}')
    return render_template('errors/500.html'), 500

