#!/usr/bin/env python3
"""
Production entry point for Workshop Inventory Tracking application.

This script uses the centralized create_app factory from the app module
to ensure consistency between test and production environments.
"""

from app import create_app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='127.0.0.1', port=5000)