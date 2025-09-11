"""
Google Sheets Export Service

Handles uploading export data to Google Sheets, including clearing existing data
and replacing it with fresh export data from MariaDB.
"""

from typing import List, Dict, Any, Optional, Tuple
from flask import current_app
from googleapiclient.errors import HttpError
import logging
import time

from .google_sheets_storage import GoogleSheetsStorage
from .storage import StorageResult
from .auth import GoogleAuth
from .exceptions import GoogleSheetsError, RateLimitError, TemporaryError, AuthenticationError
from .error_handlers import retry_with_backoff

logger = logging.getLogger(__name__)


class GoogleSheetsExportService:
    """Service for uploading export data to Google Sheets"""
    
    def __init__(self, spreadsheet_id: Optional[str] = None):
        """
        Initialize Google Sheets export service
        
        Args:
            spreadsheet_id: Google Sheets spreadsheet ID, uses config if not provided
        """
        from config import Config
        
        self.spreadsheet_id = spreadsheet_id or Config.GOOGLE_SHEET_ID
        if not self.spreadsheet_id:
            raise ValueError("Google Sheets spreadsheet ID is required. Set GOOGLE_SHEET_ID environment variable.")
        
        self.auth = GoogleAuth()
        self.service = None
        self.storage = GoogleSheetsStorage(self.spreadsheet_id)
    
    def _get_service(self):
        """Get the Google Sheets service, initializing if needed"""
        if not self.service:
            self.service = self.auth.get_service()
        return self.service
    
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def clear_sheet_contents(self, sheet_name: str) -> StorageResult:
        """
        Clear all contents from a sheet (except the sheet itself)
        
        Args:
            sheet_name: Name of the sheet to clear
            
        Returns:
            StorageResult indicating success or failure
        """
        try:
            service = self._get_service()
            
            # Get sheet info to determine range to clear
            sheet_info = self.storage.get_sheet_info(sheet_name)
            if not sheet_info.success:
                return sheet_info
            
            rows = sheet_info.data.get('rows', 1000)  # Default to reasonable range
            columns = sheet_info.data.get('columns', 30)
            
            # Convert column count to letter (A, B, C, ..., Z, AA, AB, etc.)
            def num_to_col_letter(n):
                result = ""
                while n > 0:
                    n -= 1  # Adjust for 0-indexing
                    result = chr(ord('A') + (n % 26)) + result
                    n //= 26
                return result
            
            end_col = num_to_col_letter(columns)
            range_name = f"{sheet_name}!A1:{end_col}{rows}"
            
            logger.info(f"Clearing range {range_name} in sheet {sheet_name}")
            
            # Clear the range
            result = service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            
            cleared_cells = result.get('clearedRange', '')
            logger.info(f'Cleared contents from {cleared_cells}')
            
            return StorageResult(success=True, data={'cleared_range': cleared_cells})
            
        except HttpError as e:
            error_msg = f'Failed to clear sheet {sheet_name}: {e}'
            logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
        except Exception as e:
            error_msg = f'Unexpected error clearing sheet {sheet_name}: {e}'
            logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
    
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def upload_data_to_sheet(
        self, 
        sheet_name: str, 
        headers: List[str], 
        rows: List[List[str]], 
        clear_existing: bool = True
    ) -> StorageResult:
        """
        Upload data to a Google Sheet, optionally clearing existing content
        
        Args:
            sheet_name: Name of the sheet to upload to
            headers: Column headers
            rows: Data rows
            clear_existing: Whether to clear existing content first
            
        Returns:
            StorageResult with upload details
        """
        try:
            logger.info(f"Starting upload to sheet {sheet_name}: {len(headers)} columns, {len(rows)} rows")
            
            # Clear existing content if requested
            if clear_existing:
                clear_result = self.clear_sheet_contents(sheet_name)
                if not clear_result.success:
                    return clear_result
            
            # Prepare data with headers
            all_data = [headers] + rows
            
            # Upload data in batches to avoid API limits
            batch_size = 5000  # Google Sheets API limit
            total_rows = len(all_data)
            uploaded_rows = 0
            
            service = self._get_service()
            
            for i in range(0, total_rows, batch_size):
                batch = all_data[i:i + batch_size]
                start_row = i + 1  # 1-indexed for Google Sheets
                end_row = start_row + len(batch) - 1
                
                range_name = f"{sheet_name}!A{start_row}:{self._get_end_column(len(headers))}{end_row}"
                
                logger.info(f"Uploading batch {i//batch_size + 1}: rows {start_row}-{end_row} ({len(batch)} rows)")
                
                body = {
                    'values': batch
                }
                
                result = service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                    valueInputOption='USER_ENTERED',
                    body=body
                ).execute()
                
                batch_updated = result.get('updatedRows', 0)
                uploaded_rows += batch_updated
                
                logger.info(f"Uploaded batch: {batch_updated} rows")
                
                # Small delay between batches to avoid rate limits
                if i + batch_size < total_rows:
                    time.sleep(0.1)
            
            logger.info(f'Successfully uploaded {uploaded_rows} rows to {sheet_name}')
            
            return StorageResult(
                success=True, 
                affected_rows=uploaded_rows,
                data={
                    'sheet_name': sheet_name,
                    'total_rows': uploaded_rows,
                    'headers_count': len(headers),
                    'data_rows': len(rows)
                }
            )
            
        except HttpError as e:
            error_msg = f'Failed to upload data to sheet {sheet_name}: {e}'
            logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
        except Exception as e:
            error_msg = f'Unexpected error uploading to sheet {sheet_name}: {e}'
            logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
    
    def _get_end_column(self, column_count: int) -> str:
        """Convert column count to end column letter (A, B, ..., Z, AA, AB, etc.)"""
        if column_count <= 0:
            return 'A'
        
        result = ""
        n = column_count
        while n > 0:
            n -= 1  # Adjust for 0-indexing
            result = chr(ord('A') + (n % 26)) + result
            n //= 26
        return result
    
    def upload_inventory_export(
        self, 
        headers: List[str], 
        rows: List[List[str]], 
        sheet_name: str = "Metal_Export"
    ) -> StorageResult:
        """
        Upload inventory export data to Google Sheets
        
        Args:
            headers: Inventory column headers (should be 27 columns)
            rows: Inventory data rows
            sheet_name: Target sheet name (defaults to Metal_Export)
            
        Returns:
            StorageResult with upload details
        """
        logger.info(f"Uploading inventory export: {len(headers)} headers, {len(rows)} items")
        
        # Validate headers count
        if len(headers) != 27:
            return StorageResult(
                success=False,
                error=f"Invalid inventory headers count: expected 27, got {len(headers)}"
            )
        
        return self.upload_data_to_sheet(sheet_name, headers, rows, clear_existing=True)
    
    def upload_materials_export(
        self, 
        headers: List[str], 
        rows: List[List[str]], 
        sheet_name: str = "Materials_Export"
    ) -> StorageResult:
        """
        Upload materials taxonomy export data to Google Sheets
        
        Args:
            headers: Materials column headers (should be 3 columns)
            rows: Materials data rows
            sheet_name: Target sheet name (defaults to Materials_Export)
            
        Returns:
            StorageResult with upload details
        """
        logger.info(f"Uploading materials export: {len(headers)} headers, {len(rows)} materials")
        
        # Validate headers count
        if len(headers) != 3:
            return StorageResult(
                success=False,
                error=f"Invalid materials headers count: expected 3, got {len(headers)}"
            )
        
        return self.upload_data_to_sheet(sheet_name, headers, rows, clear_existing=True)
    
    def upload_combined_export(self, export_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upload combined inventory and materials export data
        
        Args:
            export_data: Combined export data with inventory and materials sections
            
        Returns:
            Dictionary with upload results for both datasets
        """
        results = {}
        
        # Upload inventory data
        if 'inventory' in export_data:
            inv_data = export_data['inventory']
            inv_headers = inv_data.get('headers', [])
            inv_rows = inv_data.get('rows', [])
            
            logger.info(f"Uploading inventory data: {len(inv_headers)} headers, {len(inv_rows)} rows")
            inv_result = self.upload_inventory_export(inv_headers, inv_rows)
            results['inventory'] = {
                'success': inv_result.success,
                'error': inv_result.error,
                'affected_rows': inv_result.affected_rows,
                'data': inv_result.data
            }
        
        # Upload materials data
        if 'materials' in export_data:
            mat_data = export_data['materials']
            mat_headers = mat_data.get('headers', [])
            mat_rows = mat_data.get('rows', [])
            
            logger.info(f"Uploading materials data: {len(mat_headers)} headers, {len(mat_rows)} rows")
            mat_result = self.upload_materials_export(mat_headers, mat_rows)
            results['materials'] = {
                'success': mat_result.success,
                'error': mat_result.error,
                'affected_rows': mat_result.affected_rows,
                'data': mat_result.data
            }
        
        # Calculate overall success
        overall_success = all(
            result.get('success', False) 
            for result in results.values()
        )
        
        total_rows = sum(
            result.get('affected_rows', 0) 
            for result in results.values()
        )
        
        errors = [
            result.get('error')
            for result in results.values()
            if result.get('error')
        ]
        
        return {
            'success': overall_success,
            'total_rows_uploaded': total_rows,
            'results': results,
            'errors': errors,
            'sheets_updated': list(results.keys())
        }
    
    def test_connection(self) -> StorageResult:
        """Test connection to Google Sheets"""
        return self.storage.connect()