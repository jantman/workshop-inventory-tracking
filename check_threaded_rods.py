#!/usr/bin/env python3
"""
Check the Type values for rows that are failing diameter validation
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from config import Config
from app.google_sheets_storage import GoogleSheetsStorage

def check_threaded_rods():
    """Check the Type values for problematic rows"""
    
    # Get sheet ID from environment
    sheet_id = os.getenv('GOOGLE_SHEET_ID')
    if not sheet_id:
        print("ERROR: GOOGLE_SHEET_ID not set in environment")
        return
    
    app = Flask(__name__)
    app.config.from_object(Config)
    
    with app.app_context():
        storage = GoogleSheetsStorage(sheet_id)
        result = storage.read_all('Metal_original')
        
        if not result.success:
            print(f"Failed to read Metal sheet: {result.error}")
            return
        
        data = result.data
        headers = data[0]
        
        # Get column indices
        type_col = headers.index('Type')
        shape_col = headers.index('Shape') 
        width_col = headers.index('Width (in)')
        code_col = headers.index('Code128')
        thread_col = headers.index('Thread')
        
        # Check problematic rows (381, 440-506 are 1-indexed, data is 0-indexed)
        problematic_rows = [381] + list(range(440, 507))  # Convert to 1-indexed
        
        print("Checking problematic rows for Type values:")
        print("=" * 60)
        
        type_counts = {}
        
        for row_num in problematic_rows:
            if row_num < len(data):  # Convert to 0-indexed for data access
                row_data = data[row_num - 1]  # -1 because headers are at index 0
                if row_num <= len(data):  # Make sure we don't go out of bounds
                    actual_row = data[row_num]  # This is the actual data row
                    
                    type_val = actual_row[type_col] if type_col < len(actual_row) else ""
                    shape_val = actual_row[shape_col] if shape_col < len(actual_row) else ""
                    width_val = actual_row[width_col] if width_col < len(actual_row) else ""
                    code_val = actual_row[code_col] if code_col < len(actual_row) else ""
                    thread_val = actual_row[thread_col] if thread_col < len(actual_row) else ""
                    
                    # Count types
                    if type_val not in type_counts:
                        type_counts[type_val] = 0
                    type_counts[type_val] += 1
                    
                    if row_num <= 385 or row_num >= 500:  # Show first few and last few
                        print(f"Row {row_num:3d}: Type='{type_val:15s}' Shape='{shape_val:12s}' Width='{width_val:8s}' Thread='{thread_val:20s}' Code='{code_val}'")
        
        print("\nType distribution in problematic rows:")
        print("=" * 40)
        for type_val, count in sorted(type_counts.items()):
            print(f"'{type_val}': {count} rows")

if __name__ == "__main__":
    check_threaded_rods()