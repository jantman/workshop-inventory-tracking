"""
WSGI entry point for Workshop Inventory Tracking application.

This module provides the WSGI application entry point for production
deployment with servers like Gunicorn, uWSGI, or mod_wsgi.
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)