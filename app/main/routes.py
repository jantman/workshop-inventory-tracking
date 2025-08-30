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
    """Inventory list view (placeholder)"""
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

@bp.route('/inventory/move')
def inventory_move():
    """Batch move items interface (placeholder)"""
    return render_template('inventory/move.html', title='Move Items')

@bp.route('/inventory/shorten')
def inventory_shorten():
    """Shorten items interface (placeholder)"""
    return render_template('inventory/shorten.html', title='Shorten Items')

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

