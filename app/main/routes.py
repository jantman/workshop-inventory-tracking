from flask import render_template, current_app, jsonify
from app.main import bp
from app.google_sheets_storage import GoogleSheetsStorage
from config import Config

@bp.route('/')
@bp.route('/index')
def index():
    return render_template('index.html', title='Home')

@bp.route('/health')
def health():
    return {'status': 'healthy', 'service': 'workshop-inventory-tracking'}

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

