"""
Admin Routes for Materials Taxonomy Management

Provides web interface for adding new taxonomy entries and managing status.
"""

from flask import render_template, request, jsonify, flash, redirect, url_for, current_app
from app.admin import bp
from app.mariadb_materials_admin_service import MariaDBMaterialsAdminService, TaxonomyAddRequest
from config import Config


def _get_storage_backend():
    """Get the appropriate storage backend for the current app context"""
    # Check if test storage is injected
    if 'STORAGE_BACKEND' in current_app.config:
        return current_app.config['STORAGE_BACKEND']
    
    # Use MariaDB storage for consistency with autocomplete
    from app.mariadb_storage import MariaDBStorage
    return MariaDBStorage()


def _get_admin_service(storage):
    """Get the appropriate admin service for the storage backend"""
    # All storage now uses MariaDB backend
    return MariaDBMaterialsAdminService(storage)


@bp.route('/materials')
def materials_overview():
    """Main materials taxonomy management page"""
    storage = _get_storage_backend()
    admin_service = _get_admin_service(storage)
    
    # Get taxonomy overview
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    overview = admin_service.get_taxonomy_overview(include_inactive=include_inactive)
    
    # Get statistics
    stats = admin_service.get_usage_statistics()
    
    return render_template('admin/materials_overview.html', 
                         taxonomy=overview, 
                         stats=stats,
                         include_inactive=include_inactive)


@bp.route('/materials/add', methods=['GET', 'POST'])
def add_material():
    """Add new taxonomy entry form and handler"""
    storage = _get_storage_backend()
    admin_service = _get_admin_service(storage)
    
    if request.method == 'GET':
        # Get level from query param, default to 3 (Material)
        level = int(request.args.get('level', 3))
        
        # Get available parents for this level
        available_parents = admin_service.get_available_parents(level)
        
        # Get parent from query param if provided (for "Add child" links)
        suggested_parent = request.args.get('parent', '')
        
        return render_template('admin/add_material.html',
                             level=level,
                             available_parents=available_parents,
                             suggested_parent=suggested_parent)
    
    else:  # POST
        # Parse form data
        try:
            level = int(request.form.get('level', 3))
            aliases_str = request.form.get('aliases', '').strip()
            aliases = [alias.strip() for alias in aliases_str.split(',') if alias.strip()] if aliases_str else []
            sort_order = int(request.form.get('sort_order', 0) or 0)
            
            add_request = TaxonomyAddRequest(
                name=request.form.get('name', '').strip(),
                level=level,
                parent=request.form.get('parent', '').strip(),
                aliases=aliases,
                notes=request.form.get('notes', '').strip(),
                sort_order=sort_order
            )
            
            # Add the entry
            success, message = admin_service.add_taxonomy_entry(add_request)
            
            if success:
                flash(message, 'success')
                return redirect(url_for('admin.materials_overview'))
            else:
                flash(message, 'error')
                
        except ValueError as e:
            flash(f"Invalid form data: {e}", 'error')
        except Exception as e:
            flash(f"Error processing request: {e}", 'error')
        
        # If we get here, there was an error - redisplay form
        level = int(request.form.get('level', 3))
        available_parents = admin_service.get_available_parents(level)
        
        return render_template('admin/add_material.html',
                             level=level,
                             available_parents=available_parents,
                             form_data=request.form)


@bp.route('/materials/status', methods=['POST'])
def update_material_status():
    """Update the active status of a material (AJAX endpoint)"""
    storage = _get_storage_backend()
    admin_service = _get_admin_service(storage)
    
    try:
        data = request.get_json()
        material_name = data.get('name')
        active = data.get('active', True)
        
        if not material_name:
            return jsonify({'success': False, 'error': 'Material name required'}), 400
        
        success, message = admin_service.set_material_status(material_name, active)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/api/materials/parents/<int:level>')
def get_available_parents(level):
    """Get available parent materials for a given level (AJAX endpoint)"""
    storage = _get_storage_backend()
    admin_service = _get_admin_service(storage)
    
    try:
        parents = admin_service.get_available_parents(level)
        return jsonify({
            'success': True,
            'parents': [
                {
                    'name': parent.name,
                    'level': parent.level,
                    'notes': parent.notes
                }
                for parent in parents
            ]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/api/materials/validate', methods=['POST'])
def validate_material():
    """Validate a taxonomy add request (AJAX endpoint)"""
    storage = _get_storage_backend()
    admin_service = _get_admin_service(storage)
    
    try:
        data = request.get_json()
        
        aliases_list = []
        if 'aliases' in data and data['aliases']:
            aliases_str = data['aliases']
            aliases_list = [alias.strip() for alias in aliases_str.split(',') if alias.strip()]
        
        add_request = TaxonomyAddRequest(
            name=data.get('name', '').strip(),
            level=int(data.get('level', 3)),
            parent=data.get('parent', '').strip(),
            aliases=aliases_list,
            notes=data.get('notes', '').strip(),
            sort_order=int(data.get('sort_order', 0) or 0)
        )
        
        is_valid, errors = admin_service.validate_add_request(add_request)
        
        return jsonify({
            'success': True,
            'valid': is_valid,
            'errors': errors
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/export')
def export():
    """Admin page for data export functionality"""
    return render_template('admin/export.html', title='Data Export')