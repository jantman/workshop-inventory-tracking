#!/usr/bin/env python3
"""
Data Migration Script for Workshop Material Inventory Tracking

This script migrates data from the original Metal sheet format to the new normalized format.
It includes data validation, normalization rules, and comprehensive error handling.
"""

import os
import sys
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
import argparse
import json

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from config import Config
from app.google_sheets_storage import GoogleSheetsStorage

class DataMigrator:
    """Handles data migration from original to normalized format"""
    
    # Updated headers for the new schema
    NEW_HEADERS = [
        'Active', 'JA ID', 'Length', 'Width', 'Thickness', 'Wall Thickness',
        'Weight', 'Type', 'Shape', 'Material', 'Thread Series', 'Thread Handedness',
        'Thread Form', 'Thread Size', 'Quantity', 'Location', 'Sub-Location', 'Purchase Date',
        'Purchase Price', 'Purchase Location', 'Notes', 'Vendor', 'Vendor Part',
        'Original Material', 'Original Thread', 'Date Added', 'Last Modified'
    ]
    
    # Material normalization mapping
    MATERIAL_ALIASES = {
        '4140 Pre-Hard': '4140 Pre-Hard',
        '304 / 304L': '304/304L Stainless',
        '304/304L': '304/304L Stainless',
        'Mystery': 'Unknown',
        'mystery': 'Unknown',
        'unknown': 'Unknown',
        '': 'Unknown'
    }
    
    def __init__(self, spreadsheet_id: str, dry_run: bool = True):
        self.spreadsheet_id = spreadsheet_id
        self.dry_run = dry_run
        self.storage = GoogleSheetsStorage(spreadsheet_id)
        self.migration_log = []
        self.errors = []
        self.warnings = []
        self.ja_ids_seen = set()
        self.stats = {
            'total_rows': 0,
            'valid_rows': 0,
            'skipped_rows': 0,
            'material_normalizations': 0,
            'thread_parsing': 0,
            'fraction_conversions': 0,
            'price_cleanings': 0
        }
        
    def log_info(self, message: str):
        """Log an info message"""
        print(f"INFO: {message}")
        self.migration_log.append(f"INFO: {message}")
    
    def log_warning(self, message: str):
        """Log a warning message"""
        print(f"WARNING: {message}")
        self.warnings.append(message)
        self.migration_log.append(f"WARNING: {message}")
    
    def log_error(self, message: str):
        """Log an error message"""
        print(f"ERROR: {message}")
        self.errors.append(message)
        self.migration_log.append(f"ERROR: {message}")
    
    def fraction_to_decimal(self, value: str) -> Optional[str]:
        """Convert fraction strings to decimal, preserving user precision"""
        if not value or value.strip() == '':
            return None
            
        value = value.strip()
        
        try:
            # Handle mixed numbers like "1 1/2" first
            if ' ' in value and '/' in value:
                parts = value.split(' ', 1)
                whole = int(parts[0])
                fraction = Fraction(parts[1])
                decimal_value = whole + float(fraction)
                result = f"{decimal_value:.4f}".rstrip('0').rstrip('.')
                self.stats['fraction_conversions'] += 1
                return result
            
            # Handle simple fractions like "1/2", "3/4", etc.
            elif '/' in value:
                fraction = Fraction(value)
                # Convert to decimal with appropriate precision
                decimal_value = float(fraction)
                
                # Determine precision based on denominator
                denominator = fraction.denominator
                if denominator <= 64:  # Common fractions
                    # Use 4 decimal places for common fractions
                    result = f"{decimal_value:.4f}".rstrip('0').rstrip('.')
                    self.stats['fraction_conversions'] += 1
                    return result
                else:
                    result = f"{decimal_value:.6f}".rstrip('0').rstrip('.')
                    self.stats['fraction_conversions'] += 1
                    return result
            
            # Handle regular decimals
            else:
                decimal_value = float(value)
                return f"{decimal_value:.4f}".rstrip('0').rstrip('.')
            
        except (ValueError, ZeroDivisionError) as e:
            self.log_warning(f"Could not convert '{value}' to decimal: {e}")
            return value  # Return original value
    
    def normalize_material(self, material: str) -> Tuple[str, str]:
        """Normalize material name and return (normalized, original)"""
        if not material:
            return 'Unknown', ''
        
        material = material.strip()
        original = material
        
        # Check aliases
        normalized = self.MATERIAL_ALIASES.get(material, material)
        
        if normalized != original:
            self.stats['material_normalizations'] += 1
        
        return normalized, original
    
    def parse_thread(self, thread: str) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
        """Parse thread into series, handedness, size, and original"""
        if not thread or thread.strip() == '':
            return None, None, None, ''
        
        thread = thread.strip()
        original = thread
        
        # Thread parsing patterns
        # Examples: "1/2-13 UNC", "M12x1.75", "1/4-20 UNC RH", etc.
        
        series = None
        handedness = None
        size = None
        
        # Extract handedness first
        if 'RH' in thread.upper() or 'RIGHT' in thread.upper():
            handedness = 'RH'
            thread = re.sub(r'\b(RH|RIGHT)\b', '', thread, flags=re.IGNORECASE).strip()
        elif 'LH' in thread.upper() or 'LEFT' in thread.upper():
            handedness = 'LH'
            thread = re.sub(r'\b(LH|LEFT)\b', '', thread, flags=re.IGNORECASE).strip()
        
        # Extract series
        if 'UNC' in thread.upper():
            series = 'UNC'
            thread = thread.upper().replace('UNC', '').strip()
        elif 'UNF' in thread.upper():
            series = 'UNF'
            thread = thread.upper().replace('UNF', '').strip()
        elif 'METRIC' in thread.upper() or 'M' in thread:
            series = 'Metric'
        
        # Extract size (what's left)
        if thread:
            # Clean up common separators
            size = re.sub(r'^[-\s]+', '', thread).strip()
            if size:
                size = size
        
        if any([series, handedness, size]):
            self.stats['thread_parsing'] += 1
            
        return series, handedness, size, original
    
    def clean_price(self, price: str) -> Optional[str]:
        """Clean price data by removing currency symbols and invalid characters"""
        if not price or price.strip() == '':
            return None
        
        price = price.strip()
        
        # Remove common currency symbols and whitespace
        price = price.replace('$', '').replace('€', '').replace('£', '').replace('¥', '')
        price = price.replace(',', '').strip()
        
        # Handle empty result after cleaning
        if not price:
            return None
        
        try:
            # Validate it's a valid decimal number
            decimal_value = self.fraction_to_decimal(price)
            if decimal_value and float(decimal_value) >= 0:
                self.stats['price_cleanings'] += 1
                return decimal_value
            else:
                return None
        except (ValueError, TypeError):
            self.log_warning(f"Could not parse price '{price}' - invalid format")
            return None
    
    def validate_ja_id(self, ja_id: str) -> bool:
        """Validate JA ID format"""
        if not ja_id:
            return False
        
        # Expected format: JA000001, JA000002, etc.
        pattern = r'^JA\d{6}$'
        return bool(re.match(pattern, ja_id.strip()))
    
    def normalize_active_status(self, active: str) -> str:
        """Normalize active status to Yes/No"""
        if not active or active.strip() == '':
            return 'Yes'  # Default to active
        
        active = active.strip().lower()
        if active in ['no', 'n', 'false', '0', 'inactive']:
            return 'No'
        else:
            return 'Yes'
    
    def validate_required_fields(self, row_data: Dict[str, Any], row_index: int) -> bool:
        """Validate required fields for different type/shape combinations"""
        required_issues = []
        
        # JA ID is always required
        if not row_data.get('JA ID') or not self.validate_ja_id(row_data['JA ID']):
            required_issues.append('Invalid or missing JA ID')
        
        # Type and Shape are required
        if not row_data.get('Type'):
            required_issues.append('Missing Type')
        if not row_data.get('Shape'):
            required_issues.append('Missing Shape')
        
        # Dimension requirements based on type/shape
        item_type = row_data.get('Type', '').strip()
        shape = row_data.get('Shape', '').lower().strip()
        
        if item_type == 'Threaded Rod':
            # Threaded rods only need length and thread specification
            if not row_data.get('Length'):
                required_issues.append('Length required for threaded rods')
            if not row_data.get('Thread Size') and not row_data.get('Original Thread'):
                required_issues.append('Thread specification required for threaded rods')
        elif shape == 'rectangular':
            if not row_data.get('Length'):
                required_issues.append('Length required for rectangular items')
            if not row_data.get('Width'):
                required_issues.append('Width required for rectangular items')
            if not row_data.get('Thickness'):
                required_issues.append('Thickness required for rectangular items')
        elif shape == 'round':
            if not row_data.get('Length'):
                required_issues.append('Length required for round items')
            if not row_data.get('Width'):  # Width = diameter for round
                required_issues.append('Diameter (Width) required for round items')
        
        if required_issues:
            for issue in required_issues:
                self.log_error(f"Row {row_index}: {issue}")
            return False
        
        return True
    
    def check_uniqueness(self, ja_id: str, row_index: int, is_active: bool) -> bool:
        """Check JA ID uniqueness among active rows"""
        if not is_active:
            return True  # Inactive rows don't need to be unique
        
        if ja_id in self.ja_ids_seen:
            self.log_error(f"Row {row_index}: Duplicate JA ID '{ja_id}' among active rows")
            return False
        
        self.ja_ids_seen.add(ja_id)
        return True
    
    def transform_row(self, original_row: List[str], original_headers: List[str], row_index: int) -> Optional[List[str]]:
        """Transform a single row from original to new format"""
        # FIXED: Handle missing trailing columns (Google Sheets API doesn't return trailing empty cells)
        if len(original_row) < len(original_headers):
            # Pad with empty strings for missing trailing columns
            padded_row = original_row + [''] * (len(original_headers) - len(original_row))
            self.log_info(f"Row {row_index}: Padded {len(original_headers) - len(original_row)} missing trailing columns")
        elif len(original_row) > len(original_headers):
            # This indicates actual corruption - extra columns
            self.log_error(f"Row {row_index}: Too many columns - expected {len(original_headers)}, got {len(original_row)}. This indicates data corruption.")
            self.log_error(f"Row {row_index}: Row data: {original_row}")
            return None
        else:
            padded_row = original_row
        
        # Create mapping from original headers to values
        row_dict = dict(zip(original_headers, padded_row))
        
        # Transform to new format
        new_row = [''] * len(self.NEW_HEADERS)
        
        try:
            # Active status
            new_row[0] = self.normalize_active_status(row_dict.get('Active?', ''))
            
            # JA ID
            ja_id = row_dict.get('Code128', '').strip()
            if not self.validate_ja_id(ja_id):
                self.log_error(f"Row {row_index}: Invalid JA ID format: '{ja_id}'")
                return None
            new_row[1] = ja_id
            
            # Dimensions - convert fractions to decimals
            new_row[2] = self.fraction_to_decimal(row_dict.get('Length (in)', '')) or ''
            new_row[3] = self.fraction_to_decimal(row_dict.get('Width (in)', '')) or ''
            new_row[4] = self.fraction_to_decimal(row_dict.get('Thickness (in)', '')) or ''
            new_row[5] = self.fraction_to_decimal(row_dict.get('Wall Thickness (in)', '')) or ''
            new_row[6] = self.fraction_to_decimal(row_dict.get('Weight (lbs total)', '')) or ''
            
            # Type and Shape
            new_row[7] = row_dict.get('Type', '').strip()
            new_row[8] = row_dict.get('Shape', '').strip()
            
            # Material normalization
            normalized_material, original_material = self.normalize_material(row_dict.get('Material', ''))
            new_row[9] = normalized_material
            new_row[23] = original_material  # Store original (shifted by 1)
            
            # Thread parsing
            thread_series, thread_handedness, thread_size, original_thread = self.parse_thread(row_dict.get('Thread', ''))
            new_row[10] = thread_series or ''
            new_row[11] = thread_handedness or ''
            new_row[12] = ''  # Thread Form (always empty)
            new_row[13] = thread_size or ''
            new_row[24] = original_thread  # Store original (shifted by 1)
            
            # Other fields (all shifted by 1 due to Thread Form insertion)
            new_row[14] = row_dict.get('Quantity (>1)', '').strip()
            new_row[15] = row_dict.get('Location', '').strip()
            new_row[16] = row_dict.get('Sub-Location', '').strip()
            new_row[17] = row_dict.get('Purch. Date', '').strip()
            new_row[18] = self.clean_price(row_dict.get('Purch. Price (line)', '')) or ''
            new_row[19] = row_dict.get('Purch. Loc.', '').strip()
            new_row[20] = row_dict.get('Notes', '').strip()
            new_row[21] = row_dict.get('Vendor', '').strip()
            new_row[22] = row_dict.get('Vendor Part #', '').strip()
            
            # FIXED: Use consistent timestamp and ensure we have exactly the right number of columns
            current_time = datetime.now().isoformat()
            new_row[25] = current_time  # Date Added (shifted by 1)
            new_row[26] = current_time  # Last Modified (shifted by 1)
            
            # FIXED: Strict validation that we have exactly the expected number of columns
            if len(new_row) != len(self.NEW_HEADERS):
                self.log_error(f"Row {row_index}: Output row has {len(new_row)} columns, expected {len(self.NEW_HEADERS)}")
                return None
            
            # Validate the transformed row
            row_data = dict(zip(self.NEW_HEADERS, new_row))
            if not self.validate_required_fields(row_data, row_index):
                return None
            
            # Check uniqueness for active rows
            is_active = new_row[0] == 'Yes'
            if not self.check_uniqueness(ja_id, row_index, is_active):
                return None
            
            # FINAL CHECK: Ensure output row has no extra columns that could cause alignment issues
            final_row = new_row[:len(self.NEW_HEADERS)]  # Truncate to exact length
            return final_row
            
        except Exception as e:
            self.log_error(f"Row {row_index}: Error transforming row: {e}")
            return None
    
    def backup_original_sheet(self) -> bool:
        """Create backup of original Metal sheet"""
        self.log_info("Creating backup of original Metal sheet...")
        
        if self.dry_run:
            self.log_info("DRY RUN: Would create backup Metal_backup_YYYYMMDD_HHMMSS")
            return True
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"Metal_backup_{timestamp}"
        
        result = self.storage.backup_sheet('Metal', backup_name)
        if result.success:
            self.log_info(f"Successfully created backup: {backup_name}")
            return True
        else:
            self.log_error(f"Failed to create backup: {result.error}")
            return False
    
    def rename_original_sheet(self) -> bool:
        """Rename Metal sheet to Metal_original"""
        self.log_info("Renaming Metal sheet to Metal_original...")
        
        if self.dry_run:
            self.log_info("DRY RUN: Would rename Metal → Metal_original")
            return True
        
        result = self.storage.rename_sheet('Metal', 'Metal_original')
        if result.success:
            self.log_info("Successfully renamed Metal sheet to Metal_original")
            return True
        else:
            self.log_error(f"Failed to rename sheet: {result.error}")
            return False
    
    def create_new_sheet(self) -> bool:
        """Create new Metal sheet with updated headers"""
        self.log_info("Creating new Metal sheet with updated schema...")
        
        if self.dry_run:
            self.log_info(f"DRY RUN: Would create new Metal sheet with {len(self.NEW_HEADERS)} headers")
            return True
        
        result = self.storage.create_sheet('Metal', self.NEW_HEADERS)
        if result.success:
            self.log_info(f"Successfully created new Metal sheet with {len(self.NEW_HEADERS)} columns")
            return True
        else:
            self.log_error(f"Failed to create new sheet: {result.error}")
            return False
    
    def backup_current_metal_sheet(self) -> bool:
        """Create backup of current Metal sheet before replacing it"""
        self.log_info("Creating backup of current Metal sheet...")
        
        if self.dry_run:
            self.log_info("DRY RUN: Would create backup Metal_replaced_YYYYMMDD_HHMMSS")
            return True
        
        timestamp = datetime.now().strftime("%m%d_%H%M")
        backup_name = f"Metal_backup_{timestamp}"
        
        result = self.storage.backup_sheet('Metal', backup_name)
        if result.success:
            self.log_info(f"Successfully created backup: {backup_name}")
            return True
        else:
            self.log_error(f"Failed to create backup: {result.error}")
            return False
    
    def replace_metal_sheet(self) -> bool:
        """Replace Metal sheet by clearing it and writing new headers"""
        self.log_info("Clearing Metal sheet and adding new headers...")
        
        if self.dry_run:
            self.log_info("DRY RUN: Would clear Metal sheet and add new headers")
            return True
        
        # Simply write the headers as the first row - this will effectively replace the sheet
        # The write_rows method will handle clearing and writing all data
        result = self.storage.write_row('Metal', self.NEW_HEADERS)
        if result.success:
            self.log_info(f"Successfully added new headers to Metal sheet ({len(self.NEW_HEADERS)} columns)")
            return True
        else:
            self.log_error(f"Failed to write headers: {result.error}")
            return False
    
    def _replace_sheet_content(self, sheet_name: str, data: List[List[str]]) -> bool:
        """Replace entire sheet content using Google Sheets API update method"""
        try:
            from googleapiclient.discovery import build
            from app.auth import GoogleAuth
            
            auth = GoogleAuth()
            credentials = auth.credentials
            service = build('sheets', 'v4', credentials=credentials)
            
            # Clear the entire sheet first
            clear_range = f"{sheet_name}!A:ZZ"  # Clear all columns
            clear_request = service.spreadsheets().values().clear(
                spreadsheetId=self.storage.spreadsheet_id,
                range=clear_range
            )
            clear_request.execute()
            self.log_info(f"Cleared existing content from {sheet_name}")
            
            # Update with new data (replaces content starting from A1)
            range_name = f"{sheet_name}!A1"
            body = {
                'values': data
            }
            
            update_request = service.spreadsheets().values().update(
                spreadsheetId=self.storage.spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            )
            result = update_request.execute()
            
            updated_cells = result.get('updatedCells', 0)
            self.log_info(f"Updated {updated_cells} cells in {sheet_name}")
            return True
            
        except Exception as e:
            self.log_error(f"Failed to replace sheet content: {e}")
            return False
    
    def migrate_data(self) -> bool:
        """Perform the complete data migration"""
        self.log_info("Starting data migration process...")
        
        # Step 1: Connect and validate
        self.log_info("Connecting to Google Sheets...")
        connect_result = self.storage.connect()
        if not connect_result.success:
            self.log_error(f"Failed to connect to Google Sheets: {connect_result.error}")
            return False
        
        self.log_info(f"Connected to spreadsheet: {connect_result.data.get('title', 'Unknown')}")
        
        # Step 2: Read original data
        self.log_info("Reading original Metal_original sheet...")
        data_result = self.storage.read_all('Metal_original')
        if not data_result.success:
            self.log_error(f"Failed to read Metal sheet: {data_result.error}")
            return False
        
        original_data = data_result.data
        if not original_data:
            self.log_error("Metal sheet is empty")
            return False
        
        original_headers = original_data[0]
        original_rows = original_data[1:]
        
        self.log_info(f"Found {len(original_rows)} data rows in original sheet")
        
        # FIXED: Better validation of source data structure
        self.log_info("Validating source data structure...")
        self.log_info(f"Original headers ({len(original_headers)}): {original_headers}")
        
        # Check for rows with mismatched column counts and report statistics
        short_rows = 0
        long_rows = 0
        perfect_rows = 0
        
        for i, row in enumerate(original_rows, start=2):
            if len(row) < len(original_headers):
                short_rows += 1
            elif len(row) > len(original_headers):
                long_rows += 1
            else:
                perfect_rows += 1
        
        self.log_info(f"Source data analysis: {perfect_rows} perfect rows, {short_rows} short rows (will be padded), {long_rows} long rows (errors)")
        
        if long_rows > 0:
            self.log_error(f"Found {long_rows} rows with too many columns. This indicates data corruption and cannot be auto-fixed.")
            return False
        
        # Step 3: Transform data
        self.log_info("Transforming data...")
        transformed_rows = []
        self.stats['total_rows'] = len(original_rows)
        
        for i, row in enumerate(original_rows, start=2):  # Start at 2 because headers are row 1
            # FIXED: Validate each output row has exactly the expected columns
            transformed_row = self.transform_row(row, original_headers, i)
            if transformed_row:
                # Final validation: ensure exact column count
                if len(transformed_row) != len(self.NEW_HEADERS):
                    self.log_error(f"Row {i}: Transformed row has {len(transformed_row)} columns, expected {len(self.NEW_HEADERS)}")
                    self.stats['skipped_rows'] += 1
                    continue
                    
                transformed_rows.append(transformed_row)
                self.stats['valid_rows'] += 1
            else:
                self.log_warning(f"Skipping row {i} due to validation errors")
                self.stats['skipped_rows'] += 1
        
        self.log_info(f"Successfully transformed {len(transformed_rows)} out of {len(original_rows)} rows")
        
        if not transformed_rows:
            self.log_error("No valid rows to migrate")
            return False
        
        # Stop here if dry run
        if self.dry_run:
            self.log_info("DRY RUN: Migration validation complete. Use --execute to perform actual migration.")
            self._print_migration_summary()
            return True
        
        # Step 4: Skip backup since we're replacing with corrected data
        self.log_info("Skipping backup - replacing corrupted Metal sheet with corrected data")
        
        # Step 5: Replace all content in Metal sheet
        self.log_info("Replacing all content in Metal sheet...")
        all_data = [self.NEW_HEADERS] + transformed_rows
        if not self._replace_sheet_content('Metal', all_data):
            return False
        
        self.log_info(f"Successfully replaced Metal sheet with {len(all_data)} rows")
        
        # Step 8: Final validation and integrity verification
        self.log_info("Performing final validation and data integrity verification...")
        if not self._verify_data_integrity():
            self.log_error("Data integrity verification failed")
            return False
        
        self.log_info("Data migration completed successfully!")
        self._print_migration_summary()
        return True
    
    def _verify_data_integrity(self) -> bool:
        """Verify data integrity after migration"""
        try:
            # Read the new sheet data
            final_check = self.storage.read_all('Metal')
            if not final_check.success:
                self.log_error(f"Failed to read new Metal sheet for verification: {final_check.error}")
                return False
            
            new_data = final_check.data
            if not new_data or len(new_data) < 2:  # Need at least headers + 1 row
                self.log_error("New Metal sheet is empty or has no data rows")
                return False
            
            new_headers = new_data[0]
            new_rows = new_data[1:]
            
            # FIXED: Strict header and column count validation
            if new_headers != self.NEW_HEADERS:
                self.log_error("New sheet headers do not match expected schema")
                self.log_error(f"Expected: {self.NEW_HEADERS}")
                self.log_error(f"Actual:   {new_headers}")
                return False
            
            if len(new_headers) != 27:
                self.log_error(f"Headers have {len(new_headers)} columns, expected exactly 27")
                return False
            
            self.log_info(f"✓ Headers verified: {len(new_headers)} columns (exactly 27 as expected)")
            
            # Verify row count
            expected_rows = self.stats['valid_rows']
            actual_rows = len(new_rows)
            
            if actual_rows != expected_rows:
                self.log_error(f"Row count mismatch: expected {expected_rows}, found {actual_rows}")
                return False
            
            self.log_info(f"✓ Row count verified: {actual_rows} rows")
            
            # Verify no duplicate JA IDs among active rows
            active_ja_ids = set()
            active_count = 0
            
            for i, row in enumerate(new_rows, start=2):
                if len(row) < 2:
                    continue
                
                active = row[0] == 'Yes'
                ja_id = row[1]
                
                if active:
                    active_count += 1
                    if ja_id in active_ja_ids:
                        self.log_error(f"Duplicate JA ID found in final data: {ja_id}")
                        return False
                    active_ja_ids.add(ja_id)
            
            self.log_info(f"✓ Uniqueness verified: {active_count} active items with unique JA IDs")
            
            # FIXED: Verify all rows have exactly 27 columns (no more, no less)
            validation_errors = 0
            for i, row in enumerate(new_rows, start=2):
                if len(row) != 27:
                    self.log_error(f"Row {i}: Has {len(row)} columns, expected exactly 27. This indicates column alignment corruption.")
                    validation_errors += 1
                    continue
                
                active = row[0] == 'Yes'
                if not active:
                    continue
                
                # Check required fields
                row_data = dict(zip(self.NEW_HEADERS, row))
                if not self.validate_required_fields(row_data, i):
                    validation_errors += 1
            
            if validation_errors > 0:
                self.log_error(f"Found {validation_errors} validation errors in final data")
                return False
            
            self.log_info(f"✓ Field validation passed for all {active_count} active items")
            self.log_info("✓ Data integrity verification completed successfully")
            
            return True
            
        except Exception as e:
            self.log_error(f"Data integrity verification failed with error: {e}")
            return False
    
    def _print_migration_summary(self):
        """Print migration summary"""
        print("\n" + "="*60)
        print("MIGRATION SUMMARY")
        print("="*60)
        print(f"Mode: {'DRY RUN' if self.dry_run else 'EXECUTED'}")
        print(f"Total rows processed: {self.stats['total_rows']}")
        print(f"Valid rows: {self.stats['valid_rows']}")
        print(f"Skipped rows: {self.stats['skipped_rows']}")
        print(f"Success rate: {(self.stats['valid_rows']/max(self.stats['total_rows'],1)*100):.1f}%")
        print()
        print("TRANSFORMATIONS:")
        print(f"  Material normalizations: {self.stats['material_normalizations']}")
        print(f"  Thread parsing operations: {self.stats['thread_parsing']}")
        print(f"  Fraction conversions: {self.stats['fraction_conversions']}")
        print(f"  Price cleanings: {self.stats['price_cleanings']}")
        print()
        print(f"Errors: {len(self.errors)}")
        print(f"Warnings: {len(self.warnings)}")
        
        if self.errors:
            print("\nERRORS:")
            for error in self.errors:
                print(f"  - {error}")
        
        if self.warnings:
            print("\nWARNINGS:")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        print("="*60)

def main():
    parser = argparse.ArgumentParser(description='Migrate workshop inventory data')
    parser.add_argument('--execute', action='store_true', 
                       help='Execute the migration (default is dry-run)')
    parser.add_argument('--spreadsheet-id', 
                       help='Google Sheets spreadsheet ID (overrides config)')
    parser.add_argument('--log-file', 
                       help='Save migration log to file')
    
    args = parser.parse_args()
    
    # Create Flask app context for configuration
    app = Flask(__name__)
    app.config.from_object(Config)
    
    with app.app_context():
        # Get spreadsheet ID
        spreadsheet_id = args.spreadsheet_id or Config.GOOGLE_SHEET_ID
        if not spreadsheet_id:
            print("ERROR: No Google Sheets ID provided. Set GOOGLE_SHEET_ID environment variable or use --spreadsheet-id")
            return 1
        
        # Initialize migrator
        dry_run = not args.execute
        migrator = DataMigrator(spreadsheet_id, dry_run=dry_run)
        
        try:
            # Perform migration
            success = migrator.migrate_data()
            
            # Save log if requested
            if args.log_file:
                with open(args.log_file, 'w') as f:
                    f.write('\n'.join(migrator.migration_log))
                print(f"Migration log saved to: {args.log_file}")
            
            return 0 if success else 1
            
        except KeyboardInterrupt:
            print("\nMigration interrupted by user")
            return 1
        except Exception as e:
            print(f"Migration failed with unexpected error: {e}")
            return 1

if __name__ == '__main__':
    exit(main())