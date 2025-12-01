"""
Export Data Structure Schemas

Defines the data structures and formatting rules for exporting MariaDB data
back to Google Sheets format for backup and data access purposes.
"""

from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class ExportFormatter:
    """Utility class for formatting data for Google Sheets export"""
    
    @staticmethod
    def format_boolean(value: Optional[bool]) -> str:
        """Convert boolean to Yes/No string"""
        if value is None:
            return ""
        return "Yes" if value else "No"
    
    @staticmethod
    def format_decimal(value: Optional[Decimal], precision: int = 4) -> str:
        """Format decimal with specified precision, removing trailing zeros"""
        if value is None:
            return ""
        if value == 0:
            return "0" if precision == 0 else "0." + "0" * min(precision, 2)
        
        # Format with specified precision and remove trailing zeros
        formatted = f"{value:.{precision}f}".rstrip('0').rstrip('.')
        return formatted if formatted else "0"
    
    @staticmethod
    def format_integer(value: Optional[int]) -> str:
        """Format integer, handling None"""
        if value is None:
            return ""
        return str(value)
    
    @staticmethod
    def format_string(value: Optional[str]) -> str:
        """Format string, handling None and cleaning up"""
        if value is None:
            return ""
        return str(value).strip()
    
    @staticmethod
    def format_date(value: Optional[datetime]) -> str:
        """Format date as YYYY-MM-DD"""
        if value is None:
            return ""
        return value.strftime("%Y-%m-%d")
    
    @staticmethod
    def format_datetime(value: Optional[datetime]) -> str:
        """Format datetime as YYYY-MM-DD HH:MM:SS"""
        if value is None:
            return ""
        return value.strftime("%Y-%m-%d %H:%M:%S")


class InventoryExportSchema:
    """Schema definition for inventory items export to Google Sheets"""
    
    # Google Sheets column headers in correct order
    HEADERS = [
        "Active",           # 1
        "JA ID",           # 2
        "Length",          # 3
        "Width",           # 4
        "Thickness",       # 5
        "Wall Thickness",  # 6
        "Weight",          # 7
        "Type",            # 8
        "Shape",           # 9
        "Material",        # 10
        "Thread Series",   # 11
        "Thread Handedness", # 12
        "Thread Form",     # 13 (skip - not in database)
        "Thread Size",     # 14
        "Location",        # 15
        "Sub-Location",    # 16
        "Purchase Date",   # 17
        "Purchase Price",  # 18
        "Purchase Location", # 19
        "Notes",           # 20
        "Vendor",          # 21
        "Vendor Part",     # 22
        "Original Material", # 24
        "Original Thread", # 25
        "Precision",       # 26  
        "Date Added",      # 27
        "Last Modified"    # 28
    ]
    
    @staticmethod
    def format_row(item: Any) -> List[str]:
        """
        Convert a database InventoryItem to a Google Sheets row
        
        Args:
            item: InventoryItem database object or dict-like object
            
        Returns:
            List of formatted strings for Google Sheets export
        """
        formatter = ExportFormatter()
        
        return [
            formatter.format_boolean(item.active),                    # 1. Active
            formatter.format_string(item.ja_id),                     # 2. JA ID  
            formatter.format_decimal(item.length, 4),                # 3. Length
            formatter.format_decimal(item.width, 4),                 # 4. Width
            formatter.format_decimal(item.thickness, 4),             # 5. Thickness
            formatter.format_decimal(item.wall_thickness, 4),        # 6. Wall Thickness
            formatter.format_decimal(item.weight, 2),                # 7. Weight
            formatter.format_string(item.item_type),                 # 8. Type
            formatter.format_string(item.shape),                     # 9. Shape
            formatter.format_string(item.material),                  # 10. Material
            formatter.format_string(item.thread_series),             # 11. Thread Series
            formatter.format_string(item.thread_handedness),         # 12. Thread Handedness
            "",                                                       # 13. Thread Form (not in DB)
            formatter.format_string(item.thread_size),               # 14. Thread Size
            formatter.format_string(item.location),                  # 15. Location
            formatter.format_string(item.sub_location),              # 16. Sub-Location
            formatter.format_date(item.purchase_date),               # 17. Purchase Date
            formatter.format_decimal(item.purchase_price, 2),        # 18. Purchase Price
            formatter.format_string(item.purchase_location),         # 19. Purchase Location
            formatter.format_string(item.notes),                     # 20. Notes
            formatter.format_string(item.vendor),                    # 21. Vendor
            formatter.format_string(item.vendor_part),               # 22. Vendor Part
            formatter.format_string(item.original_material),         # 24. Original Material
            formatter.format_string(item.original_thread),           # 25. Original Thread
            formatter.format_boolean(item.precision),                # 26. Precision
            formatter.format_datetime(item.date_added),              # 27. Date Added
            formatter.format_datetime(item.last_modified)            # 28. Last Modified
        ]
    
    @staticmethod
    def get_headers() -> List[str]:
        """Get the column headers for the export"""
        return InventoryExportSchema.HEADERS.copy()


class MaterialsExportSchema:
    """Schema definition for materials taxonomy export to Google Sheets"""
    
    # Google Sheets column headers
    HEADERS = [
        "Name",     # 1
        "Level",    # 2  
        "Parent"    # 3
    ]
    
    @staticmethod
    def format_row(material: Any) -> List[str]:
        """
        Convert a database MaterialTaxonomy to a Google Sheets row
        
        Args:
            material: MaterialTaxonomy database object or dict-like object
            
        Returns:
            List of formatted strings for Google Sheets export
        """
        formatter = ExportFormatter()
        
        return [
            formatter.format_string(material.name),     # 1. Name
            formatter.format_integer(material.level),   # 2. Level
            formatter.format_string(material.parent)    # 3. Parent
        ]
    
    @staticmethod
    def get_headers() -> List[str]:
        """Get the column headers for the export"""
        return MaterialsExportSchema.HEADERS.copy()


class ExportOptions:
    """Configuration options for exports"""
    
    def __init__(self):
        # Inventory export options
        self.inventory_include_inactive = True  # Include inactive/historical records
        self.inventory_sort_order = "ja_id, active DESC, date_added"
        
        # Materials export options  
        self.materials_active_only = True  # Only export active materials
        self.materials_sort_order = "level, sort_order, name"
        
        # Performance options
        self.batch_size = 1000
        self.enable_progress_logging = True
        
        # Export metadata
        self.include_export_timestamp = True
        self.export_generated_by = "Workshop Inventory MariaDB Export"


class ExportMetadata:
    """Metadata about an export operation"""
    
    def __init__(self, export_type: str):
        self.export_type = export_type  # "inventory" or "materials" 
        self.timestamp = datetime.now()
        self.records_exported = 0
        self.records_skipped = 0
        self.errors = []
        self.warnings = []
        self.options_used = {}
    
    def add_error(self, message: str):
        """Add an error message"""
        self.errors.append(f"{datetime.now().strftime('%H:%M:%S')}: {message}")
        logger.error(f"Export error: {message}")
    
    def add_warning(self, message: str):
        """Add a warning message"""
        self.warnings.append(f"{datetime.now().strftime('%H:%M:%S')}: {message}")
        logger.warning(f"Export warning: {message}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary for JSON serialization"""
        return {
            'export_type': self.export_type,
            'timestamp': self.timestamp.isoformat(),
            'records_exported': self.records_exported,
            'records_skipped': self.records_skipped,
            'success': len(self.errors) == 0,
            'errors': self.errors,
            'warnings': self.warnings,
            'options_used': self.options_used
        }