#!/usr/bin/env python3
"""
Development server entry point for Workshop Inventory Tracking application.

This script provides a convenient way to run the Flask development server
with debug mode enabled. It uses the centralized create_app factory from
the app module to ensure consistency between development, test, and production
environments.

For production deployment, use wsgi.py with a proper WSGI server like Gunicorn.

Usage:
    python app.py

The server will start on http://127.0.0.1:5000 with debug mode enabled.
"""

from app import create_app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='127.0.0.1', port=5000)