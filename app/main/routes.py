from flask import render_template, current_app, jsonify, abort, request, flash, redirect, url_for
from app.main import bp
from app import csrf
from app.google_sheets_storage import GoogleSheetsStorage
from app.inventory_service import InventoryService
from app.taxonomy import taxonomy_manager
from app.models import Item, ItemType, ItemShape, Dimensions, Thread, ThreadSeries, ThreadHandedness
from decimal import Decimal, InvalidOperation
import traceback
from config import Config

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
        return render_template('inventory/add.html', title='Add Item')
    
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
        storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
        service = InventoryService(storage)
        
        result = service.add_item(item)
        
        if result:
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

@bp.route('/inventory/search')
def inventory_search():
    """Advanced search interface (placeholder)"""
    return render_template('inventory/search.html', title='Search')

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
        required_fields = ['source_ja_id', 'new_length', 'new_ja_id', 'confirm_operation']
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
            flash(f"Item successfully shortened! New item {result['new_ja_id']} created, original item {result['source_ja_id']} deactivated.", 'success')
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
        
        storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
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
    """API endpoint for dashboard statistics (placeholder)"""
    # This will be implemented in future milestones
    return jsonify({
        'success': True,
        'data': {
            'total_items': 0,
            'active_items': 0,
            'unique_locations': 0,
            'last_updated': None
        }
    })

@bp.route('/api/items/<ja_id>/exists')
def check_ja_id_exists(ja_id):
    """Check if a JA ID already exists"""
    try:
        storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
        service = InventoryService(storage)
        
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
    """Get material suggestions based on partial input"""
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', '10')
    
    try:
        limit = int(limit)
        limit = min(max(limit, 1), 20)  # Clamp between 1 and 20
    except (ValueError, TypeError):
        limit = 10
    
    if not query:
        return jsonify({
            'success': True,
            'suggestions': []
        })
    
    try:
        suggestions = taxonomy_manager.suggest_material_matches(query, limit)
        
        # Format suggestions for frontend
        formatted_suggestions = [
            {
                'name': name,
                'confidence': confidence,
                'category': taxonomy_manager.get_material_info(name).category if taxonomy_manager.get_material_info(name) else None
            }
            for name, confidence in suggestions
        ]
        
        return jsonify({
            'success': True,
            'suggestions': formatted_suggestions,
            'query': query
        })
        
    except Exception as e:
        current_app.logger.error(f'Error getting material suggestions for "{query}": {e}')
        return jsonify({
            'success': False,
            'error': 'Failed to get material suggestions'
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
        
        is_valid, errors = taxonomy_manager.validate_type_shape_combination(item_type, shape)
        
        if is_valid:
            required_dims = taxonomy_manager.get_required_dimensions(item_type, shape)
            optional_dims = taxonomy_manager.get_optional_dimensions(item_type, shape)
            
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
        storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
        service = InventoryService(storage)
        
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
        
        storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
        service = InventoryService(storage)
        
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
        storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
        service = InventoryService(storage)
        
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
        storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
        service = InventoryService(storage)
        
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
        
        storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
        service = InventoryService(storage)
        
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
    """Execute the shortening operation"""
    try:
        storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
        service = InventoryService(storage)
        
        source_ja_id = form_data['source_ja_id'].upper()
        new_ja_id = form_data['new_ja_id'].upper()
        
        # Get the source item
        source_item = service.get_item(source_ja_id)
        if not source_item:
            return {'success': False, 'error': f'Source item {source_ja_id} not found'}
        
        if not source_item.active:
            return {'success': False, 'error': f'Source item {source_ja_id} is not active'}
        
        # Check if new JA ID already exists
        if service.get_item(new_ja_id):
            return {'success': False, 'error': f'New JA ID {new_ja_id} already exists'}
        
        # Parse new length
        try:
            new_length = _parse_dimension_value(form_data['new_length'])
            if not new_length or float(new_length) <= 0:
                return {'success': False, 'error': 'Invalid new length'}
        except Exception:
            return {'success': False, 'error': 'Invalid new length format'}
        
        # Validate new length is shorter than original
        if source_item.dimensions and source_item.dimensions.length:
            original_length = float(source_item.dimensions.length)
            if float(new_length) >= original_length:
                return {'success': False, 'error': 'New length must be shorter than original length'}
        
        # Create new shortened item
        new_item = Item(
            ja_id=new_ja_id,
            item_type=source_item.item_type,
            shape=source_item.shape,
            material=source_item.material,
            dimensions=Dimensions(
                length=new_length,
                width=source_item.dimensions.width if source_item.dimensions else None,
                thickness=source_item.dimensions.thickness if source_item.dimensions else None,
                wall_thickness=source_item.dimensions.wall_thickness if source_item.dimensions else None,
                weight=source_item.dimensions.weight if source_item.dimensions else None
            ),
            thread=source_item.thread,
            quantity=1,  # Shortened items are always quantity 1
            location=form_data.get('new_location') or source_item.location,
            sub_location=form_data.get('new_sub_location') or source_item.sub_location,
            purchase_date=source_item.purchase_date,
            purchase_price=source_item.purchase_price,
            purchase_location=source_item.purchase_location,
            vendor=source_item.vendor,
            vendor_part_number=source_item.vendor_part_number,
            notes=_build_shortening_notes(source_item, form_data),
            active=True,
            parent_ja_id=source_ja_id  # Set parent relationship
        )
        
        # Add the new item
        if not service.add_item(new_item):
            return {'success': False, 'error': 'Failed to create new shortened item'}
        
        # Deactivate the original item and add child relationship
        source_item.active = False
        source_item.add_child(new_ja_id)
        
        # Update notes to indicate shortening
        original_notes = source_item.notes or ''
        shortening_note = f"Shortened on {form_data.get('cut_date', 'unknown date')} to create {new_ja_id}"
        if form_data.get('operator'):
            shortening_note += f" by {form_data['operator']}"
        
        if original_notes:
            source_item.notes = f"{original_notes}\n\n{shortening_note}"
        else:
            source_item.notes = shortening_note
        
        # Update the source item
        if not service.update_item(source_item):
            # Try to remove the new item if source update fails
            current_app.logger.warning(f'Failed to update source item {source_ja_id}, but new item {new_ja_id} was created')
        
        current_app.logger.info(f'Shortening operation completed: {source_ja_id} -> {new_ja_id}')
        
        return {
            'success': True,
            'source_ja_id': source_ja_id,
            'new_ja_id': new_ja_id,
            'operation': 'shortening'
        }
        
    except Exception as e:
        current_app.logger.error(f'Error in shortening operation: {e}')
        return {'success': False, 'error': str(e)}

def _build_shortening_notes(source_item, form_data):
    """Build notes for the new shortened item"""
    notes_parts = []
    
    # Add source information
    notes_parts.append(f"Shortened from {source_item.ja_id}")
    
    # Add original length info
    if source_item.dimensions and source_item.dimensions.length:
        notes_parts.append(f"Original length: {source_item.dimensions.length}\"")
    
    # Add cut information
    cut_date = form_data.get('cut_date')
    if cut_date:
        notes_parts.append(f"Cut date: {cut_date}")
    
    operator = form_data.get('operator')
    if operator:
        notes_parts.append(f"Operator: {operator}")
    
    # Add cut loss if specified
    cut_loss = form_data.get('cut_loss')
    if cut_loss:
        try:
            loss_value = _parse_dimension_value(cut_loss)
            notes_parts.append(f"Cut loss: {loss_value}\"")
        except:
            pass
    
    # Add user notes
    user_notes = form_data.get('shortening_notes')
    if user_notes:
        notes_parts.append(f"Notes: {user_notes}")
    
    # Add original item notes if any
    if source_item.notes:
        notes_parts.append(f"Original item notes: {source_item.notes}")
    
    return '\n'.join(notes_parts)

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
    
    # Normalize material
    material, _ = taxonomy_manager.normalize_material(form_data['material'])
    
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

# Error handlers for the blueprint
@bp.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@bp.errorhandler(500)
def internal_error(error):
    current_app.logger.error(f'Server Error: {error}')
    return render_template('errors/500.html'), 500

