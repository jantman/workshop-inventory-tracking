from typing import List, Dict, Any, Optional
from flask import current_app
from googleapiclient.errors import HttpError
import time
import json

from app.storage import Storage, StorageResult
from app.auth import GoogleAuth
from app.exceptions import GoogleSheetsError, RateLimitError, TemporaryError, AuthenticationError
from app.error_handlers import retry_with_backoff, google_sheets_circuit_breaker

class GoogleSheetsStorage(Storage):
    """Google Sheets implementation of the Storage interface"""
    
    def __init__(self, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        self.auth = GoogleAuth()
        self.service = None
        self._retry_count = 3
        self._retry_delay = 1  # seconds
    
    def _get_service(self):
        """Get the Google Sheets service, initializing if needed"""
        if not self.service:
            self.service = self.auth.get_service()
        return self.service
    
    def _handle_http_error(self, e: HttpError, operation: str) -> None:
        """Convert HttpError to appropriate custom exception"""
        status = e.resp.status
        
        try:
            error_details = json.loads(e.content.decode('utf-8'))
            message = error_details.get('error', {}).get('message', str(e))
        except (json.JSONDecodeError, KeyError, AttributeError):
            message = str(e)
        
        if status == 401:
            raise AuthenticationError(f"Authentication failed for {operation}: {message}")
        elif status == 403:
            raise GoogleSheetsError(f"Access denied for {operation}: {message}", operation, status, e)
        elif status == 429:
            raise RateLimitError(f"Rate limit exceeded for {operation}: {message}", 
                               retry_after=60, service="Google Sheets")
        elif status >= 500:
            raise TemporaryError(f"Server error during {operation}: {message}")
        else:
            raise GoogleSheetsError(f"HTTP {status} error during {operation}: {message}", operation, status, e)

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def _retry_request(self, func, operation: str, *args, **kwargs):
        """Execute request with circuit breaker and error handling"""
        try:
            return google_sheets_circuit_breaker.call(func, *args, **kwargs)
        except HttpError as e:
            self._handle_http_error(e, operation)
        except Exception as e:
            if "credentials" in str(e).lower() or "auth" in str(e).lower():
                raise AuthenticationError(f"Authentication error during {operation}: {e}")
            else:
                raise GoogleSheetsError(f"Unexpected error during {operation}: {e}", operation, original_error=e)
        
    def connect(self) -> StorageResult:
        """Test connection to Google Sheets"""
        try:
            service = self._get_service()
            sheet_metadata = self._retry_request(
                service.spreadsheets().get,
                "connect",
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            title = sheet_metadata.get("properties", {}).get("title", "Unknown")
            current_app.logger.info(f'Connected to spreadsheet: {title}')
            
            return StorageResult(
                success=True,
                data={
                    'title': title,
                    'sheets': [sheet['properties']['title'] for sheet in sheet_metadata.get('sheets', [])]
                }
            )
            
        except (GoogleSheetsError, AuthenticationError, RateLimitError, TemporaryError) as e:
            current_app.logger.error(f'Connection failed: {e}')
            return StorageResult(success=False, error=str(e))
        except Exception as e:
            error_msg = f'Unexpected error connecting to Google Sheets: {e}'
            current_app.logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
    
    def read_all(self, sheet_name: str) -> StorageResult:
        """Read all data from a sheet"""
        try:
            service = self._get_service()
            result = self._retry_request(
                service.spreadsheets().values().get,
                f"read_all from {sheet_name}",
                spreadsheetId=self.spreadsheet_id,
                range=sheet_name
            ).execute()
            
            values = result.get('values', [])
            current_app.logger.info(f'Read {len(values)} rows from {sheet_name}')
            
            return StorageResult(success=True, data=values)
            
        except (GoogleSheetsError, AuthenticationError, RateLimitError, TemporaryError) as e:
            current_app.logger.error(f'Failed to read from sheet {sheet_name}: {e}')
            return StorageResult(success=False, error=str(e))
        except Exception as e:
            error_msg = f'Unexpected error reading from sheet {sheet_name}: {e}'
            current_app.logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
    
    def read_range(self, sheet_name: str, range_spec: str) -> StorageResult:
        """Read data from a specific range"""
        try:
            service = self._get_service()
            full_range = f"{sheet_name}!{range_spec}"
            
            result = self._retry_request(
                service.spreadsheets().values().get,
                spreadsheetId=self.spreadsheet_id,
                range=full_range
            ).execute()
            
            values = result.get('values', [])
            return StorageResult(success=True, data=values)
            
        except HttpError as e:
            error_msg = f'Failed to read range {range_spec} from {sheet_name}: {e}'
            current_app.logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
    
    def write_row(self, sheet_name: str, data: List[Any]) -> StorageResult:
        """Append a single row to the sheet"""
        return self.write_rows(sheet_name, [data])
    
    def write_rows(self, sheet_name: str, data: List[List[Any]]) -> StorageResult:
        """Append multiple rows to the sheet"""
        try:
            service = self._get_service()
            
            body = {
                'values': data
            }
            
            result = self._retry_request(
                service.spreadsheets().values().append,
                f"write_rows to {sheet_name}",
                spreadsheetId=self.spreadsheet_id,
                range=sheet_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            updated_rows = result.get('updates', {}).get('updatedRows', 0)
            current_app.logger.info(f'Appended {updated_rows} rows to {sheet_name}')
            
            return StorageResult(success=True, affected_rows=updated_rows)
            
        except (GoogleSheetsError, AuthenticationError, RateLimitError, TemporaryError) as e:
            current_app.logger.error(f'Failed to write rows to {sheet_name}: {e}')
            return StorageResult(success=False, error=str(e))
        except Exception as e:
            error_msg = f'Unexpected error writing rows to {sheet_name}: {e}'
            current_app.logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
    
    def update_row(self, sheet_name: str, row_index: int, data: List[Any]) -> StorageResult:
        """Update a specific row (1-indexed)"""
        try:
            service = self._get_service()
            range_name = f"{sheet_name}!{row_index}:{row_index}"
            
            body = {
                'values': [data]
            }
            
            result = self._retry_request(
                service.spreadsheets().values().update,
                'update_row',
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            updated_cells = result.get('updatedCells', 0)
            current_app.logger.info(f'Updated row {row_index} in {sheet_name}, {updated_cells} cells changed')
            
            return StorageResult(success=True, affected_rows=1)
            
        except HttpError as e:
            error_msg = f'Failed to update row {row_index} in {sheet_name}: {e}'
            current_app.logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
    
    def delete_row(self, sheet_name: str, row_index: int) -> StorageResult:
        """Delete a specific row"""
        # Note: Google Sheets API doesn't have a direct delete row method
        # This would require getting sheet ID and using batchUpdate with DeleteDimensionRequest
        # For now, we'll mark as not implemented
        error_msg = "Delete row operation not yet implemented for Google Sheets"
        return StorageResult(success=False, error=error_msg)
    
    def create_sheet(self, sheet_name: str, headers: List[str]) -> StorageResult:
        """Create a new sheet with headers"""
        try:
            service = self._get_service()
            
            # First create the sheet
            body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': sheet_name
                        }
                    }
                }]
            }
            
            result = self._retry_request(
                service.spreadsheets().batchUpdate,
                f"create_sheet {sheet_name}",
                spreadsheetId=self.spreadsheet_id,
                body=body
            )
            
            # Then add headers if provided
            if headers:
                header_result = self.write_row(sheet_name, headers)
                if not header_result.success:
                    return header_result
            
            current_app.logger.info(f'Created sheet {sheet_name} with {len(headers)} headers')
            return StorageResult(success=True)
            
        except HttpError as e:
            error_msg = f'Failed to create sheet {sheet_name}: {e}'
            current_app.logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
    
    def rename_sheet(self, old_name: str, new_name: str) -> StorageResult:
        """Rename a sheet"""
        try:
            service = self._get_service()
            
            # First get the sheet ID
            sheet_metadata = service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            sheet_id = None
            for sheet in sheet_metadata.get('sheets', []):
                if sheet['properties']['title'] == old_name:
                    sheet_id = sheet['properties']['sheetId']
                    break
            
            if sheet_id is None:
                return StorageResult(success=False, error=f'Sheet {old_name} not found')
            
            # Rename the sheet
            body = {
                'requests': [{
                    'updateSheetProperties': {
                        'properties': {
                            'sheetId': sheet_id,
                            'title': new_name
                        },
                        'fields': 'title'
                    }
                }]
            }
            
            result = self._retry_request(
                service.spreadsheets().batchUpdate,
                f"rename_sheet {old_name} to {new_name}",
                spreadsheetId=self.spreadsheet_id,
                body=body
            )
            
            current_app.logger.info(f'Renamed sheet from {old_name} to {new_name}')
            return StorageResult(success=True)
            
        except HttpError as e:
            error_msg = f'Failed to rename sheet from {old_name} to {new_name}: {e}'
            current_app.logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
    
    def backup_sheet(self, sheet_name: str, backup_name: str) -> StorageResult:
        """Create a backup copy of a sheet"""
        try:
            # Read all data from source sheet
            data_result = self.read_all(sheet_name)
            if not data_result.success:
                return data_result
            
            # Create new sheet with backup name
            if data_result.data:
                headers = data_result.data[0] if data_result.data else []
                create_result = self.create_sheet(backup_name, headers)
                if not create_result.success:
                    return create_result
                
                # Copy remaining data if any
                if len(data_result.data) > 1:
                    copy_result = self.write_rows(backup_name, data_result.data[1:])
                    if not copy_result.success:
                        return copy_result
            else:
                # Empty sheet
                create_result = self.create_sheet(backup_name, [])
                if not create_result.success:
                    return create_result
            
            current_app.logger.info(f'Created backup of {sheet_name} as {backup_name}')
            return StorageResult(success=True)
            
        except Exception as e:
            error_msg = f'Failed to backup sheet {sheet_name}: {e}'
            current_app.logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
    
    def get_sheet_info(self, sheet_name: str) -> StorageResult:
        """Get information about a sheet"""
        try:
            service = self._get_service()
            sheet_metadata = service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            for sheet in sheet_metadata.get('sheets', []):
                if sheet['properties']['title'] == sheet_name:
                    properties = sheet['properties']
                    grid_properties = properties.get('gridProperties', {})
                    
                    info = {
                        'title': properties['title'],
                        'sheet_id': properties['sheetId'],
                        'rows': grid_properties.get('rowCount', 0),
                        'columns': grid_properties.get('columnCount', 0)
                    }
                    
                    return StorageResult(success=True, data=info)
            
            return StorageResult(success=False, error=f'Sheet {sheet_name} not found')
            
        except HttpError as e:
            error_msg = f'Failed to get info for sheet {sheet_name}: {e}'
            current_app.logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)
    
    def search(self, sheet_name: str, filters: Dict[str, Any]) -> StorageResult:
        """Basic search implementation - reads all data and filters in memory"""
        try:
            # Read all data
            data_result = self.read_all(sheet_name)
            if not data_result.success:
                return data_result
            
            data = data_result.data
            if not data:
                return StorageResult(success=True, data=[])
            
            headers = data[0]
            rows = data[1:]
            
            # Simple filtering - exact matches only for now
            filtered_rows = []
            for row in rows:
                match = True
                for column, value in filters.items():
                    if column in headers:
                        col_index = headers.index(column)
                        if col_index < len(row) and row[col_index] != value:
                            match = False
                            break
                    else:
                        match = False
                        break
                
                if match:
                    filtered_rows.append(row)
            
            result_data = [headers] + filtered_rows if filtered_rows else [headers]
            return StorageResult(success=True, data=result_data)
            
        except Exception as e:
            error_msg = f'Failed to search sheet {sheet_name}: {e}'
            current_app.logger.error(error_msg)
            return StorageResult(success=False, error=error_msg)