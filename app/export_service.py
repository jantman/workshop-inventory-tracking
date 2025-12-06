"""
Export Service Classes

Provides services for querying MariaDB data and formatting it for Google Sheets export.
Handles both inventory items and materials taxonomy with proper data formatting,
batch processing, and error handling.
"""

from typing import List, Dict, Any, Optional, Tuple, Iterator
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine, desc, asc
import logging
from datetime import datetime

from .database import InventoryItem, MaterialTaxonomy
from .export_schemas import (
    InventoryExportSchema, 
    MaterialsExportSchema, 
    ExportOptions, 
    ExportMetadata,
    ExportFormatter
)
from config import Config

logger = logging.getLogger(__name__)


class BaseExportService:
    """Base class for export services with common functionality"""
    
    def __init__(self, database_uri: Optional[str] = None):
        """
        Initialize export service with database connection
        
        Args:
            database_uri: Database connection string, uses Config if not provided
        """
        self.database_uri = database_uri or Config.SQLALCHEMY_DATABASE_URI
        if not self.database_uri:
            raise ValueError("Database URI is required. Set SQLALCHEMY_DATABASE_URI environment variable.")
        
        self.engine = create_engine(
            self.database_uri,
            **Config.SQLALCHEMY_ENGINE_OPTIONS
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()
    
    def close_session(self, session: Session):
        """Close a database session"""
        try:
            session.close()
        except Exception as e:
            logger.warning(f"Error closing session: {e}")


class InventoryExportService(BaseExportService):
    """Service for exporting inventory items data to Google Sheets format"""
    
    def __init__(self, database_uri: Optional[str] = None):
        super().__init__(database_uri)
        self.schema = InventoryExportSchema()
        self.formatter = ExportFormatter()
    
    def get_export_headers(self) -> List[str]:
        """Get the column headers for inventory export"""
        return self.schema.get_headers()
    
    def count_items(self, options: ExportOptions) -> Tuple[int, int]:
        """
        Count total and active items for export planning
        
        Args:
            options: Export configuration options
            
        Returns:
            Tuple of (total_items, active_items)
        """
        session = self.get_session()
        try:
            # Count total items
            total_query = session.query(InventoryItem)
            if not options.inventory_include_inactive:
                total_query = total_query.filter(InventoryItem.active == True)
            total_count = total_query.count()
            
            # Count active items
            active_count = session.query(InventoryItem).filter(InventoryItem.active == True).count()
            
            return total_count, active_count
            
        except Exception as e:
            logger.error(f"Error counting inventory items: {e}")
            raise
        finally:
            self.close_session(session)
    
    def export_items_batch(
        self, 
        options: ExportOptions, 
        offset: int = 0, 
        limit: Optional[int] = None
    ) -> List[List[str]]:
        """
        Export a batch of inventory items as formatted rows
        
        Args:
            options: Export configuration options
            offset: Number of records to skip
            limit: Maximum number of records to return (uses options.batch_size if None)
            
        Returns:
            List of formatted rows ready for Google Sheets
        """
        if limit is None:
            limit = options.batch_size
        
        session = self.get_session()
        try:
            # Build query
            query = session.query(InventoryItem)
            
            # Apply filters
            if not options.inventory_include_inactive:
                query = query.filter(InventoryItem.active == True)
            
            # Apply sorting
            sort_order = options.inventory_sort_order
            if "ja_id" in sort_order:
                query = query.order_by(asc(InventoryItem.ja_id))
            if "active DESC" in sort_order:
                query = query.order_by(desc(InventoryItem.active))
            if "date_added" in sort_order:
                query = query.order_by(asc(InventoryItem.date_added))
            
            # Apply pagination
            query = query.offset(offset).limit(limit)
            
            # Execute query
            items = query.all()
            
            if options.enable_progress_logging:
                logger.info(f"Retrieved {len(items)} inventory items (offset={offset}, limit={limit})")
            
            # Format items as rows
            formatted_rows = []
            for item in items:
                try:
                    row = self.schema.format_row(item)
                    formatted_rows.append(row)
                except Exception as e:
                    logger.error(f"Error formatting item {item.ja_id}: {e}")
                    # Continue with other items, don't fail entire batch
                    continue
            
            return formatted_rows
            
        except Exception as e:
            logger.error(f"Error exporting inventory items batch: {e}")
            raise
        finally:
            self.close_session(session)
    
    def export_all_items(self, options: ExportOptions) -> Iterator[List[List[str]]]:
        """
        Export all inventory items in batches
        
        Args:
            options: Export configuration options
            
        Yields:
            Batches of formatted rows ready for Google Sheets
        """
        total_count, active_count = self.count_items(options)
        
        if options.enable_progress_logging:
            logger.info(f"Starting inventory export: {total_count} total items, {active_count} active items")
        
        offset = 0
        exported_count = 0
        
        while offset < total_count:
            try:
                batch = self.export_items_batch(options, offset, options.batch_size)
                
                if not batch:
                    break
                
                exported_count += len(batch)
                offset += options.batch_size
                
                if options.enable_progress_logging:
                    logger.info(f"Exported batch: {len(batch)} items (total: {exported_count}/{total_count})")
                
                yield batch
                
            except Exception as e:
                logger.error(f"Error exporting batch at offset {offset}: {e}")
                # Skip this batch and continue
                offset += options.batch_size
                continue
        
        if options.enable_progress_logging:
            logger.info(f"Inventory export complete: {exported_count} items exported")
    
    def export_complete_dataset(self, options: ExportOptions) -> Tuple[List[str], List[List[str]], ExportMetadata]:
        """
        Export complete inventory dataset with headers and metadata
        
        Args:
            options: Export configuration options
            
        Returns:
            Tuple of (headers, all_rows, metadata)
        """
        metadata = ExportMetadata("inventory")
        metadata.options_used = {
            'include_inactive': options.inventory_include_inactive,
            'sort_order': options.inventory_sort_order,
            'batch_size': options.batch_size
        }
        
        try:
            headers = self.get_export_headers()
            all_rows = []
            
            # Export all data in batches
            for batch in self.export_all_items(options):
                all_rows.extend(batch)
                metadata.records_exported += len(batch)
            
            if options.enable_progress_logging:
                logger.info(f"Inventory export complete: {len(all_rows)} total rows")
            
            return headers, all_rows, metadata
            
        except Exception as e:
            metadata.add_error(f"Export failed: {str(e)}")
            logger.error(f"Complete inventory export failed: {e}")
            raise


class MaterialsExportService(BaseExportService):
    """Service for exporting materials taxonomy data to Google Sheets format"""
    
    def __init__(self, database_uri: Optional[str] = None):
        super().__init__(database_uri)
        self.schema = MaterialsExportSchema()
        self.formatter = ExportFormatter()
    
    def get_export_headers(self) -> List[str]:
        """Get the column headers for materials export"""
        return self.schema.get_headers()
    
    def count_materials(self, options: ExportOptions) -> Tuple[int, int]:
        """
        Count total and active materials for export planning
        
        Args:
            options: Export configuration options
            
        Returns:
            Tuple of (total_materials, active_materials)
        """
        session = self.get_session()
        try:
            # Count total materials
            total_query = session.query(MaterialTaxonomy)
            if options.materials_active_only:
                total_query = total_query.filter(MaterialTaxonomy.active == True)
            total_count = total_query.count()
            
            # Count active materials
            active_count = session.query(MaterialTaxonomy).filter(MaterialTaxonomy.active == True).count()
            
            return total_count, active_count
            
        except Exception as e:
            logger.error(f"Error counting materials: {e}")
            raise
        finally:
            self.close_session(session)
    
    def export_materials_batch(
        self, 
        options: ExportOptions, 
        offset: int = 0, 
        limit: Optional[int] = None
    ) -> List[List[str]]:
        """
        Export a batch of materials as formatted rows
        
        Args:
            options: Export configuration options
            offset: Number of records to skip
            limit: Maximum number of records to return (uses options.batch_size if None)
            
        Returns:
            List of formatted rows ready for Google Sheets
        """
        if limit is None:
            limit = options.batch_size
        
        session = self.get_session()
        try:
            # Build query
            query = session.query(MaterialTaxonomy)
            
            # Apply filters
            if options.materials_active_only:
                query = query.filter(MaterialTaxonomy.active == True)
            
            # Apply sorting - level, sort_order, name
            query = query.order_by(
                asc(MaterialTaxonomy.level),
                asc(MaterialTaxonomy.sort_order),
                asc(MaterialTaxonomy.name)
            )
            
            # Apply pagination
            query = query.offset(offset).limit(limit)
            
            # Execute query
            materials = query.all()
            
            if options.enable_progress_logging:
                logger.info(f"Retrieved {len(materials)} materials (offset={offset}, limit={limit})")
            
            # Format materials as rows
            formatted_rows = []
            for material in materials:
                try:
                    row = self.schema.format_row(material)
                    formatted_rows.append(row)
                except Exception as e:
                    logger.error(f"Error formatting material {material.name}: {e}")
                    # Continue with other materials, don't fail entire batch
                    continue
            
            return formatted_rows
            
        except Exception as e:
            logger.error(f"Error exporting materials batch: {e}")
            raise
        finally:
            self.close_session(session)
    
    def export_all_materials(self, options: ExportOptions) -> Iterator[List[List[str]]]:
        """
        Export all materials in batches
        
        Args:
            options: Export configuration options
            
        Yields:
            Batches of formatted rows ready for Google Sheets
        """
        total_count, active_count = self.count_materials(options)
        
        if options.enable_progress_logging:
            logger.info(f"Starting materials export: {total_count} total materials, {active_count} active materials")
        
        offset = 0
        exported_count = 0
        
        while offset < total_count:
            try:
                batch = self.export_materials_batch(options, offset, options.batch_size)
                
                if not batch:
                    break
                
                exported_count += len(batch)
                offset += options.batch_size
                
                if options.enable_progress_logging:
                    logger.info(f"Exported batch: {len(batch)} materials (total: {exported_count}/{total_count})")
                
                yield batch
                
            except Exception as e:
                logger.error(f"Error exporting batch at offset {offset}: {e}")
                # Skip this batch and continue
                offset += options.batch_size
                continue
        
        if options.enable_progress_logging:
            logger.info(f"Materials export complete: {exported_count} materials exported")
    
    def export_complete_dataset(self, options: ExportOptions) -> Tuple[List[str], List[List[str]], ExportMetadata]:
        """
        Export complete materials dataset with headers and metadata
        
        Args:
            options: Export configuration options
            
        Returns:
            Tuple of (headers, all_rows, metadata)
        """
        metadata = ExportMetadata("materials")
        metadata.options_used = {
            'active_only': options.materials_active_only,
            'sort_order': options.materials_sort_order,
            'batch_size': options.batch_size
        }
        
        try:
            headers = self.get_export_headers()
            all_rows = []
            
            # Export all data in batches
            for batch in self.export_all_materials(options):
                all_rows.extend(batch)
                metadata.records_exported += len(batch)
            
            if options.enable_progress_logging:
                logger.info(f"Materials export complete: {len(all_rows)} total rows")
            
            return headers, all_rows, metadata
            
        except Exception as e:
            metadata.add_error(f"Export failed: {str(e)}")
            logger.error(f"Complete materials export failed: {e}")
            raise


class CombinedExportService:
    """Service for managing combined exports of both inventory and materials data"""
    
    def __init__(self, database_uri: Optional[str] = None):
        self.inventory_service = InventoryExportService(database_uri)
        self.materials_service = MaterialsExportService(database_uri)
    
    def export_all_data(self, options: ExportOptions) -> Dict[str, Any]:
        """
        Export both inventory and materials data
        
        Args:
            options: Export configuration options
            
        Returns:
            Dictionary containing both datasets and metadata
        """
        logger.info("Starting combined export of inventory and materials data")
        
        # Export inventory data
        inv_headers, inv_rows, inv_metadata = self.inventory_service.export_complete_dataset(options)
        
        # Export materials data
        mat_headers, mat_rows, mat_metadata = self.materials_service.export_complete_dataset(options)
        
        # Create combined result
        result = {
            'timestamp': datetime.now().isoformat(),
            'export_generated_by': options.export_generated_by,
            'inventory': {
                'headers': inv_headers,
                'rows': inv_rows,
                'metadata': inv_metadata.to_dict()
            },
            'materials': {
                'headers': mat_headers,
                'rows': mat_rows,
                'metadata': mat_metadata.to_dict()
            },
            'summary': {
                'total_inventory_items': inv_metadata.records_exported,
                'total_materials': mat_metadata.records_exported,
                'success': len(inv_metadata.errors) == 0 and len(mat_metadata.errors) == 0,
                'errors': inv_metadata.errors + mat_metadata.errors,
                'warnings': inv_metadata.warnings + mat_metadata.warnings
            }
        }
        
        logger.info(f"Combined export complete: {inv_metadata.records_exported} inventory items, "
                   f"{mat_metadata.records_exported} materials")
        
        return result
    
    def validate_export_data(self, export_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate exported data for quality and completeness
        
        Args:
            export_data: Export data from export_all_data()
            
        Returns:
            Validation report with issues found
        """
        issues = []
        warnings = []
        
        # Validate inventory data
        inv_data = export_data.get('inventory', {})
        inv_headers = inv_data.get('headers', [])
        inv_rows = inv_data.get('rows', [])

        if len(inv_headers) != 27:
            issues.append(f"Inventory headers count mismatch: expected 27, got {len(inv_headers)}")
        
        for i, row in enumerate(inv_rows):
            if len(row) != len(inv_headers):
                issues.append(f"Inventory row {i+1} column count mismatch: expected {len(inv_headers)}, got {len(row)}")
            
            # Check for required fields
            if len(row) > 1 and not row[1]:  # JA ID
                issues.append(f"Inventory row {i+1} missing JA ID")
        
        # Validate materials data
        mat_data = export_data.get('materials', {})
        mat_headers = mat_data.get('headers', [])
        mat_rows = mat_data.get('rows', [])
        
        if len(mat_headers) != 3:
            issues.append(f"Materials headers count mismatch: expected 3, got {len(mat_headers)}")
        
        for i, row in enumerate(mat_rows):
            if len(row) != len(mat_headers):
                issues.append(f"Materials row {i+1} column count mismatch: expected {len(mat_headers)}, got {len(row)}")
            
            # Check for required fields
            if len(row) > 0 and not row[0]:  # Name
                issues.append(f"Materials row {i+1} missing name")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'summary': {
                'inventory_rows': len(inv_rows),
                'materials_rows': len(mat_rows),
                'total_issues': len(issues),
                'total_warnings': len(warnings)
            }
        }