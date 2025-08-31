#!/usr/bin/env python3
"""
Simple script to inspect the actual structure of the Google Sheet
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from config import Config
from app.google_sheets_storage import GoogleSheetsStorage

def inspect_sheet():
    """Inspect the actual sheet structure"""
    
    # Get sheet ID from environment
    sheet_id = os.getenv('GOOGLE_SHEET_ID')
    if not sheet_id:
        print("ERROR: GOOGLE_SHEET_ID not set in environment")
        return
    
    print(f"Inspecting sheet: {sheet_id}")
    print("=" * 50)
    
    # Initialize Flask app context for logging
    app = Flask(__name__)
    app.config.from_object(Config)
    
    with app.app_context():
        storage = GoogleSheetsStorage(sheet_id)
        
        print("✓ Attempting to connect to Google Sheets")
        
        # Read all data from Metal sheet
        result = storage.read_all('Metal')
        if not result.success:
            print(f"Failed to read Metal sheet: {result.error}")
            return
        
        data = result.data
        if not data:
            print("No data found in Metal sheet")
            return
        
        print(f"Total rows found: {len(data)}")
        
        # Show headers
        headers = data[0]
        print(f"\nHeaders ({len(headers)} columns):")
        for i, header in enumerate(headers):
            print(f"  {i+1:2d}: '{header}'")
        
        # Show first few data rows
        print(f"\nFirst 5 data rows:")
        for i, row in enumerate(data[1:6], 1):
            print(f"\nRow {i} ({len(row)} columns):")
            for j, cell in enumerate(row):
                if j < len(headers):
                    print(f"  {headers[j]:20s}: '{cell}'")
                else:
                    print(f"  Extra column {j+1:2d}: '{cell}'")
        
        # Show column count variations
        print(f"\nColumn count analysis:")
        column_counts = {}
        for i, row in enumerate(data):
            count = len(row)
            if count not in column_counts:
                column_counts[count] = []
            column_counts[count].append(i)
        
        for count, rows in sorted(column_counts.items()):
            print(f"  {count:2d} columns: {len(rows):3d} rows (first 10 row numbers: {rows[:10]})")

if __name__ == "__main__":
    inspect_sheet()