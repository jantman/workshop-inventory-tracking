"""
Test Storage Implementation

SQLite in-memory storage backend for testing purposes.
Implements the Storage interface for fast, isolated tests.
"""

import sqlite3
import tempfile
import os
from typing import List, Dict, Any, Optional, Union
from app.storage import Storage, StorageResult
import json
import logging

logger = logging.getLogger(__name__)

class InMemoryStorage(Storage):
    """SQLite in-memory storage implementation for testing"""
    
    def __init__(self, database_path: str = None):
        """Initialize test storage with SQLite database"""
        if database_path is None:
            # Create a temporary file for multi-connection access
            self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
            self.database_path = self.temp_file.name
            self.temp_file.close()
        else:
            self.database_path = database_path
            self.temp_file = None
        self.connection: Optional[sqlite3.Connection] = None
        self.sheets: Dict[str, List[str]] = {}  # sheet_name -> headers
        
    def connect(self) -> StorageResult:
        """Establish connection to SQLite database"""
        try:
            self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
            self.connection.row_factory = sqlite3.Row  # Enable column access by name
            return StorageResult(success=True, data="Connected to test storage")
        except Exception as e:
            logger.error(f"Failed to connect to test storage: {e}")
            return StorageResult(success=False, error=str(e))
    
    def _ensure_connection(self):
        """Ensure database connection exists"""
        if not self.connection:
            result = self.connect()
            if not result.success:
                raise RuntimeError(f"Cannot connect to database: {result.error}")
    
    def _sanitize_sheet_name(self, sheet_name: str) -> str:
        """Sanitize sheet name for use as SQLite table name"""
        # Replace spaces and special chars with underscores
        return "".join(c if c.isalnum() else "_" for c in sheet_name.lower())
    
    def create_sheet(self, sheet_name: str, headers: List[str]) -> StorageResult:
        """Create a new sheet/table with headers"""
        try:
            self._ensure_connection()
            table_name = self._sanitize_sheet_name(sheet_name)
            
            # Store headers for later reference
            self.sheets[sheet_name] = headers.copy()
            
            # Create table with dynamic columns
            columns_sql = ", ".join([f'"{header}" TEXT' for header in headers])
            create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" (id INTEGER PRIMARY KEY AUTOINCREMENT, {columns_sql})'
            
            cursor = self.connection.cursor()
            cursor.execute(create_sql)
            self.connection.commit()
            
            logger.info(f"Created test sheet: {sheet_name} with headers: {headers}")
            return StorageResult(success=True, data=f"Sheet {sheet_name} created")
            
        except Exception as e:
            logger.error(f"Failed to create sheet {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
    
    def read_all(self, sheet_name: str) -> StorageResult:
        """Read all data from a sheet/table"""
        try:
            self._ensure_connection()
            table_name = self._sanitize_sheet_name(sheet_name)
            
            cursor = self.connection.cursor()
            cursor.execute(f'SELECT * FROM "{table_name}" ORDER BY id')
            rows = cursor.fetchall()
            
            # Convert to list of lists (excluding id column)
            headers = self.sheets.get(sheet_name, [])
            data = []
            
            # Add headers as first row (to match Google Sheets format)
            if headers:
                data.append(headers)
            
            # Add data rows
            for row in rows:
                row_data = [row[header] for header in headers]
                data.append(row_data)
            
            return StorageResult(success=True, data=data)
            
        except Exception as e:
            logger.error(f"Failed to read all from {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
    
    def read_range(self, sheet_name: str, range_spec: str) -> StorageResult:
        """Read data from a specific range (simplified for testing)"""
        # For testing, just return all data (could be enhanced later)
        return self.read_all(sheet_name)
    
    def write_row(self, sheet_name: str, data: List[Any]) -> StorageResult:
        """Write a single row to the sheet"""
        try:
            self._ensure_connection()
            table_name = self._sanitize_sheet_name(sheet_name)
            headers = self.sheets.get(sheet_name, [])
            
            if len(data) > len(headers):
                return StorageResult(success=False, error=f"Data length {len(data)} exceeds headers {len(headers)}")
            
            # Pad data if shorter than headers
            padded_data = data + [None] * (len(headers) - len(data))
            
            # Insert row
            placeholders = ", ".join(["?" for _ in headers])
            columns_sql = ", ".join([f'"{header}"' for header in headers])
            insert_sql = f'INSERT INTO "{table_name}" ({columns_sql}) VALUES ({placeholders})'
            
            cursor = self.connection.cursor()
            cursor.execute(insert_sql, padded_data)
            self.connection.commit()
            
            return StorageResult(success=True, affected_rows=1, data=cursor.lastrowid)
            
        except Exception as e:
            logger.error(f"Failed to write row to {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
    
    def write_rows(self, sheet_name: str, data: List[List[Any]]) -> StorageResult:
        """Write multiple rows to the sheet"""
        try:
            affected_count = 0
            for row in data:
                result = self.write_row(sheet_name, row)
                if result.success:
                    affected_count += 1
                else:
                    return StorageResult(success=False, error=f"Failed to write row: {result.error}")
            
            return StorageResult(success=True, affected_rows=affected_count)
            
        except Exception as e:
            logger.error(f"Failed to write rows to {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
    
    def update_row(self, sheet_name: str, row_index: int, data: List[Any]) -> StorageResult:
        """Update a specific row (1-based indexing to match Google Sheets)"""
        try:
            self._ensure_connection()
            table_name = self._sanitize_sheet_name(sheet_name)
            headers = self.sheets.get(sheet_name, [])
            
            if len(data) > len(headers):
                return StorageResult(success=False, error=f"Data length {len(data)} exceeds headers {len(headers)}")
            
            # Pad data if shorter than headers
            padded_data = data + [None] * (len(headers) - len(data))
            
            # For Google Sheets compatibility: row_index includes header row
            # Row 1 = headers, Row 2 = first data (id=1), Row 3 = second data (id=2)
            # So SQLite id = row_index - 1
            sqlite_id = row_index - 1
            
            set_clauses = ", ".join([f'"{header}" = ?' for header in headers])
            update_sql = f'UPDATE "{table_name}" SET {set_clauses} WHERE id = ?'
            
            cursor = self.connection.cursor()
            cursor.execute(update_sql, padded_data + [sqlite_id])
            self.connection.commit()
            
            return StorageResult(success=True, affected_rows=cursor.rowcount)
            
        except Exception as e:
            logger.error(f"Failed to update row {row_index} in {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
    
    def delete_row(self, sheet_name: str, row_index: int) -> StorageResult:
        """Delete a specific row"""
        try:
            self._ensure_connection()
            table_name = self._sanitize_sheet_name(sheet_name)
            
            # For Google Sheets compatibility: row_index includes header row
            # Row 1 = headers, Row 2 = first data (id=1), Row 3 = second data (id=2)
            # So SQLite id = row_index - 1
            sqlite_id = row_index - 1
            
            cursor = self.connection.cursor()
            cursor.execute(f'DELETE FROM "{table_name}" WHERE id = ?', (sqlite_id,))
            self.connection.commit()
            
            return StorageResult(success=True, affected_rows=cursor.rowcount)
            
        except Exception as e:
            logger.error(f"Failed to delete row {row_index} from {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
    
    def rename_sheet(self, old_name: str, new_name: str) -> StorageResult:
        """Rename a sheet/table"""
        try:
            self._ensure_connection()
            old_table = self._sanitize_sheet_name(old_name)
            new_table = self._sanitize_sheet_name(new_name)
            
            cursor = self.connection.cursor()
            cursor.execute(f'ALTER TABLE "{old_table}" RENAME TO "{new_table}"')
            self.connection.commit()
            
            # Update headers mapping
            if old_name in self.sheets:
                self.sheets[new_name] = self.sheets.pop(old_name)
            
            return StorageResult(success=True, data=f"Sheet renamed from {old_name} to {new_name}")
            
        except Exception as e:
            logger.error(f"Failed to rename sheet {old_name} to {new_name}: {e}")
            return StorageResult(success=False, error=str(e))
    
    def backup_sheet(self, sheet_name: str, backup_name: str) -> StorageResult:
        """Create a backup copy of a sheet"""
        try:
            self._ensure_connection()
            source_table = self._sanitize_sheet_name(sheet_name)
            backup_table = self._sanitize_sheet_name(backup_name)
            
            cursor = self.connection.cursor()
            cursor.execute(f'CREATE TABLE "{backup_table}" AS SELECT * FROM "{source_table}"')
            self.connection.commit()
            
            # Copy headers mapping
            if sheet_name in self.sheets:
                self.sheets[backup_name] = self.sheets[sheet_name].copy()
            
            return StorageResult(success=True, data=f"Sheet {sheet_name} backed up to {backup_name}")
            
        except Exception as e:
            logger.error(f"Failed to backup sheet {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
    
    def get_sheet_info(self, sheet_name: str) -> StorageResult:
        """Get information about a sheet"""
        try:
            self._ensure_connection()
            table_name = self._sanitize_sheet_name(sheet_name)
            
            cursor = self.connection.cursor()
            cursor.execute(f'SELECT COUNT(*) as row_count FROM "{table_name}"')
            row_count = cursor.fetchone()[0]
            
            headers = self.sheets.get(sheet_name, [])
            info = {
                "row_count": row_count,
                "column_count": len(headers),
                "headers": headers
            }
            
            return StorageResult(success=True, data=info)
            
        except Exception as e:
            logger.error(f"Failed to get sheet info for {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
    
    def search(self, sheet_name: str, filters: Dict[str, Any]) -> StorageResult:
        """Search for rows matching given filters"""
        try:
            self._ensure_connection()
            table_name = self._sanitize_sheet_name(sheet_name)
            headers = self.sheets.get(sheet_name, [])
            
            # Build WHERE clause from filters
            where_clauses = []
            params = []
            
            for column, value in filters.items():
                if column in headers:
                    where_clauses.append(f'"{column}" = ?')
                    params.append(value)
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            query_sql = f'SELECT * FROM "{table_name}" WHERE {where_sql} ORDER BY id'
            
            cursor = self.connection.cursor()
            cursor.execute(query_sql, params)
            rows = cursor.fetchall()
            
            # Convert to list of lists (excluding id column)
            data = []
            for row in rows:
                row_data = [row[header] for header in headers]
                data.append(row_data)
            
            return StorageResult(success=True, data=data)
            
        except Exception as e:
            logger.error(f"Failed to search {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
    
    def close(self):
        """Close database connection and cleanup temporary file"""
        if self.connection:
            self.connection.close()
            self.connection = None
        
        # Clean up temporary file if we created one
        if self.temp_file and os.path.exists(self.database_path):
            try:
                os.unlink(self.database_path)
            except OSError:
                pass  # Ignore cleanup errors
    
    def clear_all_data(self):
        """Clear all data from all sheets (useful for test cleanup)"""
        try:
            self._ensure_connection()
            cursor = self.connection.cursor()
            
            # Get all table names (exclude sqlite system tables)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = cursor.fetchall()
            
            # Drop all non-system tables
            for table in tables:
                table_name = table[0]
                cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            
            self.connection.commit()
            self.sheets.clear()
            
        except Exception as e:
            logger.error(f"Failed to clear all data: {e}")
    
    def __del__(self):
        """Cleanup on destruction"""
        self.close()