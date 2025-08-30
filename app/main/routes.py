from flask import render_template, current_app
from app.main import bp

@bp.route('/')
@bp.route('/index')
def index():
    return render_template('index.html', title='Home')

@bp.route('/health')
def health():
    return {'status': 'healthy', 'service': 'workshop-inventory-tracking'}

