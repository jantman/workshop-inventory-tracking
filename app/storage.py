from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class StorageResult:
    """Result wrapper for storage operations"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    affected_rows: int = 0

class Storage(ABC):
    """Abstract base class for storage implementations"""
    
    @abstractmethod
    def connect(self) -> StorageResult:
        """Establish connection to the storage backend"""
        pass
    
    @abstractmethod
    def read_all(self, sheet_name: str) -> StorageResult:
        """Read all data from a sheet/table"""
        pass
    
    @abstractmethod
    def read_range(self, sheet_name: str, range_spec: str) -> StorageResult:
        """Read data from a specific range"""
        pass
    
    @abstractmethod
    def write_row(self, sheet_name: str, data: List[Any]) -> StorageResult:
        """Write a single row to the sheet"""
        pass
    
    @abstractmethod
    def write_rows(self, sheet_name: str, data: List[List[Any]]) -> StorageResult:
        """Write multiple rows to the sheet"""
        pass
    
    @abstractmethod
    def update_row(self, sheet_name: str, row_index: int, data: List[Any]) -> StorageResult:
        """Update a specific row"""
        pass
    
    @abstractmethod
    def delete_row(self, sheet_name: str, row_index: int) -> StorageResult:
        """Delete a specific row"""
        pass
    
    @abstractmethod
    def create_sheet(self, sheet_name: str, headers: List[str]) -> StorageResult:
        """Create a new sheet with headers"""
        pass
    
    @abstractmethod
    def rename_sheet(self, old_name: str, new_name: str) -> StorageResult:
        """Rename a sheet"""
        pass
    
    @abstractmethod
    def backup_sheet(self, sheet_name: str, backup_name: str) -> StorageResult:
        """Create a backup copy of a sheet"""
        pass
    
    @abstractmethod
    def get_sheet_info(self, sheet_name: str) -> StorageResult:
        """Get information about a sheet (dimensions, etc.)"""
        pass
    
    @abstractmethod
    def search(self, sheet_name: str, filters: Dict[str, Any]) -> StorageResult:
        """Search for rows matching given filters"""
        pass