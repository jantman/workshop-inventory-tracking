"""
MariaDB Storage Backend

Implements the Storage interface using MariaDB database with SQLAlchemy ORM.
Provides compatibility with existing Google Sheets-style data access patterns
while using the new database schema.
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone

from .storage import Storage, StorageResult
from .database import Base, InventoryItem, MaterialTaxonomy
from config import Config


logger = logging.getLogger(__name__)


class MariaDBStorage(Storage):
    """MariaDB implementation of the Storage interface"""
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize MariaDB storage with database URL"""
        self.database_url = database_url or Config.SQLALCHEMY_DATABASE_URI
        self.engine = None
        self.Session = None
        self._connected = False
        
    def connect(self) -> StorageResult:
        """Establish connection to MariaDB database"""
        try:
            # Use different engine options for SQLite vs MariaDB
            if self.database_url.startswith('sqlite://'):
                # SQLite-specific options
                engine_options = {
                    'connect_args': {'check_same_thread': False}
                }
            else:
                # MariaDB-specific options from config
                engine_options = Config.SQLALCHEMY_ENGINE_OPTIONS
                
            self.engine = create_engine(
                self.database_url,
                **engine_options
            )
            
            # Test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            # Create session factory
            self.Session = scoped_session(sessionmaker(bind=self.engine))
            self._connected = True
            
            logger.info("Connected to MariaDB database successfully")
            return StorageResult(success=True, data="Connected")
            
        except Exception as e:
            logger.error(f"Failed to connect to MariaDB: {e}")
            return StorageResult(success=False, error=str(e))
    
    def close(self):
        """Close database connections"""
        if self.Session:
            self.Session.remove()
        if self.engine:
            self.engine.dispose()
        self._connected = False
    
    def _get_session(self):
        """Get database session, ensuring connection exists"""
        if not self._connected:
            result = self.connect()
            if not result.success:
                raise ConnectionError(f"Cannot connect to database: {result.error}")
        return self.Session()
    
    def read_all(self, sheet_name: str) -> StorageResult:
        """Read all data from a table (sheet equivalent)"""
        try:
            session = self._get_session()
            
            if sheet_name == "Metal":
                # Read inventory items
                items = session.query(InventoryItem).order_by(InventoryItem.date_added).all()
                
                # Convert to Google Sheets compatible format
                headers = self._get_inventory_headers()
                data = [headers]
                
                for item in items:
                    row = self._inventory_item_to_row(item)
                    data.append(row)
                
                return StorageResult(success=True, data=data, affected_rows=len(items))
                
            elif sheet_name == "Materials":
                # Read materials taxonomy
                materials = session.query(MaterialTaxonomy).order_by(
                    MaterialTaxonomy.level, MaterialTaxonomy.sort_order, MaterialTaxonomy.name
                ).all()
                
                # Convert to Google Sheets compatible format
                headers = self._get_materials_headers()
                data = [headers]
                
                for material in materials:
                    row = self._material_taxonomy_to_row(material)
                    data.append(row)
                
                return StorageResult(success=True, data=data, affected_rows=len(materials))
            
            else:
                return StorageResult(success=False, error=f"Unknown sheet: {sheet_name}")
                
        except Exception as e:
            logger.error(f"Error reading from {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
        finally:
            if 'session' in locals():
                session.close()
    
    def read_range(self, sheet_name: str, range_spec: str) -> StorageResult:
        """Read data from a specific range (simplified for database)"""
        # For database backend, we'll read all and then slice if needed
        # Range specification parsing would need more complex implementation
        return self.read_all(sheet_name)
    
    def write_row(self, sheet_name: str, data: List[Any]) -> StorageResult:
        """Write a single row to the table"""
        try:
            session = self._get_session()
            
            if sheet_name == "Metal":
                # Convert row data to InventoryItem
                item = self._row_to_inventory_item(data)
                session.add(item)
                session.commit()
                
                return StorageResult(success=True, data=item.id, affected_rows=1)
                
            elif sheet_name == "Materials": 
                # Convert row data to MaterialTaxonomy
                material = self._row_to_material_taxonomy(data)
                session.add(material)
                session.commit()
                
                return StorageResult(success=True, data=material.id, affected_rows=1)
            
            else:
                return StorageResult(success=False, error=f"Unknown sheet: {sheet_name}")
                
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            logger.error(f"Error writing to {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
        finally:
            if 'session' in locals():
                session.close()
    
    def write_rows(self, sheet_name: str, data: List[List[Any]]) -> StorageResult:
        """Write multiple rows to the table"""
        try:
            session = self._get_session()
            affected_rows = 0
            
            if sheet_name == "Metal":
                for row_data in data:
                    if row_data:  # Skip empty rows
                        item = self._row_to_inventory_item(row_data)
                        session.add(item)
                        affected_rows += 1
                        
            elif sheet_name == "Materials":
                for row_data in data:
                    if row_data:  # Skip empty rows
                        material = self._row_to_material_taxonomy(row_data)
                        session.add(material)
                        affected_rows += 1
            else:
                return StorageResult(success=False, error=f"Unknown sheet: {sheet_name}")
            
            session.commit()
            return StorageResult(success=True, affected_rows=affected_rows)
            
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            logger.error(f"Error writing rows to {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
        finally:
            if 'session' in locals():
                session.close()
    
    def update_row(self, sheet_name: str, row_index: int, data: List[Any]) -> StorageResult:
        """Update a specific row (by database ID for MariaDB)"""
        try:
            session = self._get_session()
            
            if sheet_name == "Metal":
                # For database, row_index is actually the database ID
                item = session.query(InventoryItem).filter_by(id=row_index).first()
                if not item:
                    return StorageResult(success=False, error=f"Item with ID {row_index} not found")
                
                # Update item with new data
                self._update_inventory_item_from_row(item, data)
                session.commit()
                
                return StorageResult(success=True, affected_rows=1)
                
            elif sheet_name == "Materials":
                material = session.query(MaterialTaxonomy).filter_by(id=row_index).first() 
                if not material:
                    return StorageResult(success=False, error=f"Material with ID {row_index} not found")
                
                self._update_material_taxonomy_from_row(material, data)
                session.commit()
                
                return StorageResult(success=True, affected_rows=1)
            
            else:
                return StorageResult(success=False, error=f"Unknown sheet: {sheet_name}")
                
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            logger.error(f"Error updating row in {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
        finally:
            if 'session' in locals():
                session.close()
    
    def delete_row(self, sheet_name: str, row_index: int) -> StorageResult:
        """Delete a specific row (by database ID)"""
        try:
            session = self._get_session()
            
            if sheet_name == "Metal":
                item = session.query(InventoryItem).filter_by(id=row_index).first()
                if not item:
                    return StorageResult(success=False, error=f"Item with ID {row_index} not found")
                
                session.delete(item)
                session.commit()
                return StorageResult(success=True, affected_rows=1)
                
            elif sheet_name == "Materials":
                material = session.query(MaterialTaxonomy).filter_by(id=row_index).first()
                if not material:
                    return StorageResult(success=False, error=f"Material with ID {row_index} not found")
                
                session.delete(material)
                session.commit()
                return StorageResult(success=True, affected_rows=1)
            
            else:
                return StorageResult(success=False, error=f"Unknown sheet: {sheet_name}")
                
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            logger.error(f"Error deleting row from {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
        finally:
            if 'session' in locals():
                session.close()
    
    def create_sheet(self, sheet_name: str, headers: List[str]) -> StorageResult:
        """Create a new sheet (table) - for database this is mostly a no-op"""
        # Tables are created via migrations, not dynamically
        return StorageResult(success=True, data=f"Table {sheet_name} exists")
    
    def rename_sheet(self, old_name: str, new_name: str) -> StorageResult:
        """Rename a sheet - not typically supported for database tables"""
        return StorageResult(success=False, error="Renaming tables not supported")
    
    def backup_sheet(self, sheet_name: str, backup_name: str) -> StorageResult:
        """Create a backup copy - would need custom implementation"""
        return StorageResult(success=False, error="Table backup not implemented")
    
    def get_sheet_info(self, sheet_name: str) -> StorageResult:
        """Get information about a table"""
        try:
            session = self._get_session()
            
            if sheet_name == "Metal":
                count = session.query(InventoryItem).count()
                return StorageResult(success=True, data={"rows": count + 1})  # +1 for headers
            elif sheet_name == "Materials":
                count = session.query(MaterialTaxonomy).count()
                return StorageResult(success=True, data={"rows": count + 1})
            else:
                return StorageResult(success=False, error=f"Unknown sheet: {sheet_name}")
                
        except Exception as e:
            logger.error(f"Error getting sheet info for {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
        finally:
            if 'session' in locals():
                session.close()
    
    def search(self, sheet_name: str, filters: Dict[str, Any]) -> StorageResult:
        """Search for rows matching given filters"""
        try:
            session = self._get_session()
            
            if sheet_name == "Metal":
                query = session.query(InventoryItem)
                
                # Apply filters
                for key, value in filters.items():
                    if hasattr(InventoryItem, key) and value is not None:
                        query = query.filter(getattr(InventoryItem, key) == value)
                
                items = query.all()
                
                # Convert to sheet format
                headers = self._get_inventory_headers()
                data = [headers]
                for item in items:
                    data.append(self._inventory_item_to_row(item))
                
                return StorageResult(success=True, data=data, affected_rows=len(items))
                
            elif sheet_name == "Materials":
                query = session.query(MaterialTaxonomy)
                
                # Apply filters
                for key, value in filters.items():
                    if hasattr(MaterialTaxonomy, key) and value is not None:
                        query = query.filter(getattr(MaterialTaxonomy, key) == value)
                
                materials = query.all()
                
                # Convert to sheet format
                headers = self._get_materials_headers()
                data = [headers]
                for material in materials:
                    data.append(self._material_taxonomy_to_row(material))
                
                return StorageResult(success=True, data=data, affected_rows=len(materials))
            
            else:
                return StorageResult(success=False, error=f"Unknown sheet: {sheet_name}")
                
        except Exception as e:
            logger.error(f"Error searching {sheet_name}: {e}")
            return StorageResult(success=False, error=str(e))
        finally:
            if 'session' in locals():
                session.close()
    
    # Helper methods for data conversion
    
    def _get_inventory_headers(self) -> List[str]:
        """Get inventory sheet headers compatible with Google Sheets format"""
        return [
            'JA ID', 'Type', 'Shape', 'Material', 'Length', 'Width', 'Thickness',
            'Wall Thickness', 'Weight', 'Thread Series', 'Thread Handedness',
            'Thread Size', 'Quantity', 'Location', 'Sub Location', 'Purchase Date',
            'Purchase Price', 'Purchase Location', 'Notes', 'Vendor', 'Vendor Part',
            'Original Material', 'Original Thread', 'Active', 'Date Added', 'Last Modified'
        ]
    
    def _get_materials_headers(self) -> List[str]:
        """Get materials taxonomy headers compatible with Google Sheets format"""
        return ['Name', 'Level', 'Parent', 'Aliases', 'Active', 'Sort Order', 'Reserved', 'Notes']
    
    def _inventory_item_to_row(self, item: InventoryItem) -> List[Any]:
        """Convert InventoryItem to row format compatible with Google Sheets"""
        return [
            item.ja_id,
            item.item_type,
            item.shape or '',
            item.material,
            float(item.length) if item.length else '',
            float(item.width) if item.width else '',
            float(item.thickness) if item.thickness else '',
            float(item.wall_thickness) if item.wall_thickness else '',
            float(item.weight) if item.weight else '',
            item.thread_series or '',
            item.thread_handedness or '',
            item.thread_size or '',
            item.quantity,
            item.location or '',
            item.sub_location or '',
            item.purchase_date.strftime('%Y-%m-%d') if item.purchase_date else '',
            float(item.purchase_price) if item.purchase_price else '',
            item.purchase_location or '',
            item.notes or '',
            item.vendor or '',
            item.vendor_part or '',
            item.original_material or '',
            item.original_thread or '',
            '1' if item.active else '0',  # Google Sheets compatible boolean
            item.date_added.strftime('%Y-%m-%d %H:%M:%S') if item.date_added else '',
            item.last_modified.strftime('%Y-%m-%d %H:%M:%S') if item.last_modified else ''
        ]
    
    def _material_taxonomy_to_row(self, material: MaterialTaxonomy) -> List[Any]:
        """Convert MaterialTaxonomy to row format compatible with Google Sheets"""
        return [
            material.name,
            material.level,
            material.parent or '',
            material.aliases or '',
            '1' if material.active else '0',  # Google Sheets compatible boolean
            material.sort_order,
            '',  # Reserved field
            material.notes or ''
        ]
    
    def _row_to_inventory_item(self, row: List[Any]) -> InventoryItem:
        """Convert row data to InventoryItem (basic implementation)"""
        # This is a simplified conversion - would need more robust parsing
        return InventoryItem(
            ja_id=str(row[0]) if len(row) > 0 else '',
            item_type=str(row[1]) if len(row) > 1 else '',
            shape=str(row[2]) if len(row) > 2 and row[2] else None,
            material=str(row[3]) if len(row) > 3 else '',
            length=float(row[4]) if len(row) > 4 and row[4] else None,
            width=float(row[5]) if len(row) > 5 and row[5] else None,
            thickness=float(row[6]) if len(row) > 6 and row[6] else None,
            wall_thickness=float(row[7]) if len(row) > 7 and row[7] else None,
            weight=float(row[8]) if len(row) > 8 and row[8] else None,
            thread_series=str(row[9]) if len(row) > 9 and row[9] else None,
            thread_handedness=str(row[10]) if len(row) > 10 and row[10] else None,
            thread_size=str(row[11]) if len(row) > 11 and row[11] else None,
            quantity=int(row[12]) if len(row) > 12 and row[12] else 1,
            location=str(row[13]) if len(row) > 13 and row[13] else None,
            sub_location=str(row[14]) if len(row) > 14 and row[14] else None,
            notes=str(row[18]) if len(row) > 18 and row[18] else None,
            vendor=str(row[19]) if len(row) > 19 and row[19] else None,
            vendor_part=str(row[20]) if len(row) > 20 and row[20] else None,
            active=str(row[23]).lower() in ('1', 'true', 'yes') if len(row) > 23 else True
        )
    
    def _row_to_material_taxonomy(self, row: List[Any]) -> MaterialTaxonomy:
        """Convert row data to MaterialTaxonomy"""
        return MaterialTaxonomy(
            name=str(row[0]) if len(row) > 0 else '',
            level=int(row[1]) if len(row) > 1 and row[1] else 1,
            parent=str(row[2]) if len(row) > 2 and row[2] else None,
            aliases=str(row[3]) if len(row) > 3 and row[3] else None,
            active=str(row[4]).lower() in ('1', 'true', 'yes') if len(row) > 4 else True,
            sort_order=int(row[5]) if len(row) > 5 and row[5] else 0,
            notes=str(row[7]) if len(row) > 7 and row[7] else None
        )
    
    def _update_inventory_item_from_row(self, item: InventoryItem, row: List[Any]):
        """Update InventoryItem from row data"""
        # Update fields from row data - simplified implementation
        if len(row) > 1:
            item.item_type = str(row[1])
        if len(row) > 2:
            item.shape = str(row[2]) if row[2] else None
        if len(row) > 3:
            item.material = str(row[3])
        # ... additional field updates as needed
        item.last_modified = datetime.now(timezone.utc)
    
    def _update_material_taxonomy_from_row(self, material: MaterialTaxonomy, row: List[Any]):
        """Update MaterialTaxonomy from row data"""
        # Update fields from row data
        if len(row) > 1:
            material.level = int(row[1])
        if len(row) > 2:
            material.parent = str(row[2]) if row[2] else None
        if len(row) > 3:
            material.aliases = str(row[3]) if row[3] else None
        # ... additional field updates as needed
        material.last_modified = datetime.now(timezone.utc)