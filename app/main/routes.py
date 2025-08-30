from flask import render_template, current_app, jsonify, abort
from app.main import bp
from app.google_sheets_storage import GoogleSheetsStorage
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

@bp.route('/inventory/add')
def inventory_add():
    """Add new inventory item (placeholder)"""
    return render_template('inventory/add.html', title='Add Item')

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

# Error handlers for the blueprint
@bp.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@bp.errorhandler(500)
def internal_error(error):
    current_app.logger.error(f'Server Error: {error}')
    return render_template('errors/500.html'), 500

