#!/usr/bin/env python3
"""
Test Google Sheets connection
"""

import os
import sys
from flask import Flask

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from app.google_sheets_storage import GoogleSheetsStorage

def test_connection():
    """Test connection to Google Sheets"""
    
    print("Testing Google Sheets Connection")
    print("=" * 40)
    
    # Validate configuration first
    print("1. Validating configuration...")
    config_errors = Config.validate_config()
    
    if config_errors:
        print("❌ Configuration errors:")
        for error in config_errors:
            print(f"  - {error}")
        print("\nPlease run 'python setup_config.py' to configure the application.")
        return False
    
    print("✓ Configuration is valid")
    
    # Create Flask app context for logging
    app = Flask(__name__)
    app.config.from_object(Config)
    
    with app.app_context():
        from app.logging_config import setup_logging
        setup_logging(app)
        
        print(f"2. Connecting to spreadsheet: {Config.GOOGLE_SHEET_ID}")
        
        try:
            # Initialize storage
            storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
            
            # Test connection
            result = storage.connect()
            
            if result.success:
                print("✓ Successfully connected to Google Sheets!")
                print(f"  - Spreadsheet: {result.data.get('title', 'Unknown')}")
                print(f"  - Available sheets: {', '.join(result.data.get('sheets', []))}")
                
                # Test reading from Metal sheet if it exists
                sheets = result.data.get('sheets', [])
                if 'Metal' in sheets:
                    print("\n3. Testing read from Metal sheet...")
                    read_result = storage.read_range('Metal', 'A1:E5')
                    if read_result.success:
                        print("✓ Successfully read sample data from Metal sheet")
                        if read_result.data:
                            print("  Sample data:")
                            for i, row in enumerate(read_result.data[:3]):
                                print(f"    Row {i+1}: {row}")
                    else:
                        print(f"❌ Failed to read from Metal sheet: {read_result.error}")
                else:
                    print("\n3. Metal sheet not found - this is expected for initial setup")
                
                return True
                
            else:
                print(f"❌ Failed to connect: {result.error}")
                return False
                
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return False

def main():
    """Main test function"""
    try:
        success = test_connection()
        if success:
            print("\n🎉 Google Sheets integration is working!")
            return 0
        else:
            print("\n❌ Connection test failed")
            return 1
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        return 1

if __name__ == '__main__':
    exit(main())