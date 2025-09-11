#!/usr/bin/env python
"""
Google Sheets to MariaDB Migration Tool

Migrates inventory items and materials taxonomy from Google Sheets to MariaDB.
Handles data type conversions, validation, and multi-row JA ID scenarios.
"""

import sys
import os
from typing import Dict, List, Any, Optional, Tuple
import logging
from datetime import datetime
from decimal import Decimal
import traceback

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from app import create_app
from app.google_sheets_storage import GoogleSheetsStorage
from app.database import Base, InventoryItem, MaterialTaxonomy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import IntegrityError


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SheetsMigrationTool:
    """Tool for migrating data from Google Sheets to MariaDB"""
    
    def __init__(self):
        self.sheet_id = Config.GOOGLE_SHEET_ID
        if not self.sheet_id:
            raise ValueError("GOOGLE_SHEET_ID not configured")
        
        self.storage = GoogleSheetsStorage(self.sheet_id)
        
        # Use production Config for database
        self.database_url = Config.SQLALCHEMY_DATABASE_URI
        self.engine = None
        self.Session = None
        
        self.stats = {
            'inventory_items': {
                'total_read': 0,
                'successful_migrations': 0,
                'failed_migrations': 0,
                'skipped_empty_rows': 0,
                'errors': []
            },
            'materials': {
                'total_read': 0,
                'successful_migrations': 0,
                'failed_migrations': 0,
                'skipped_empty_rows': 0,
                'errors': []
            }
        }
    
    def _connect_database(self):
        """Initialize database connection and create tables"""
        self.engine = create_engine(
            self.database_url,
            **Config.SQLALCHEMY_ENGINE_OPTIONS
        )
        
        # Test connection
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        # Create session factory
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        
        # Create all tables
        Base.metadata.create_all(self.engine)
        logger.info("✅ Database connection established and tables ready")
    
    def migrate_all_data(self) -> Dict[str, Any]:
        """Migrate both inventory items and materials taxonomy"""
        logger.info("🚀 Starting complete migration from Google Sheets to MariaDB...")
        
        migration_result = {
            'migration_timestamp': datetime.now().isoformat(),
            'spreadsheet_id': self.sheet_id,
            'inventory_migration': None,
            'materials_migration': None,
            'overall_success': False
        }
        
        # Test Google Sheets connection
        connection_result = self.storage.connect()
        if not connection_result.success:
            raise RuntimeError(f"Cannot connect to Google Sheets: {connection_result.error}")
        
        logger.info(f"✅ Connected to spreadsheet: {connection_result.data.get('title', 'Unknown')}")
        
        # Initialize database connection
        self._connect_database()
        
        # Migrate materials taxonomy first (inventory items reference materials)
        logger.info("🌳 Starting materials taxonomy migration...")
        migration_result['materials_migration'] = self.migrate_materials_taxonomy()
        
        # Migrate inventory items
        logger.info("📦 Starting inventory items migration...")
        migration_result['inventory_migration'] = self.migrate_inventory_items()
        
        # Determine overall success
        materials_ok = migration_result['materials_migration']['success']
        inventory_ok = migration_result['inventory_migration']['success']
        migration_result['overall_success'] = materials_ok and inventory_ok
        
        return migration_result
    
    def migrate_inventory_items(self) -> Dict[str, Any]:
        """Migrate inventory items from Metal sheet"""
        result = self.storage.read_all("Metal")
        if not result.success:
            logger.error(f"Failed to read Metal sheet: {result.error}")
            return {"success": False, "error": result.error}
        
        data = result.data
        if not data or len(data) < 2:
            return {"success": False, "error": "Metal sheet is empty or has no data rows"}
        
        headers = data[0]
        rows = data[1:]
        
        logger.info(f"📊 Processing {len(rows)} inventory item rows...")
        
        # Clear existing inventory data
        session = self.Session()
        try:
            session.query(InventoryItem).delete()
            session.commit()
            logger.info("🗑️ Cleared existing inventory items")
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
        
        self.stats['inventory_items']['total_read'] = len(rows)
        
        session = self.Session()
        try:
            for i, row in enumerate(rows):
                try:
                    if self._is_empty_row(row):
                        self.stats['inventory_items']['skipped_empty_rows'] += 1
                        continue
                    
                    inventory_item = self._convert_inventory_row(row, headers, i + 2)
                    if inventory_item:
                        session.add(inventory_item)
                        self.stats['inventory_items']['successful_migrations'] += 1
                    else:
                        self.stats['inventory_items']['failed_migrations'] += 1
                        
                except Exception as e:
                    error_msg = f"Row {i + 2}: {str(e)}"
                    self.stats['inventory_items']['errors'].append(error_msg)
                    self.stats['inventory_items']['failed_migrations'] += 1
                    logger.warning(f"Failed to process inventory row {i + 2}: {e}")
                    continue
            
            session.commit()
            logger.info(f"✅ Committed {self.stats['inventory_items']['successful_migrations']} inventory items")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to commit inventory items: {e}")
            return {"success": False, "error": f"Database commit failed: {e}"}
        finally:
            session.close()
        
        return {
            "success": True,
            "stats": self.stats['inventory_items'].copy()
        }
    
    def migrate_materials_taxonomy(self) -> Dict[str, Any]:
        """Migrate materials taxonomy from Materials sheet"""
        result = self.storage.read_all("Materials")
        if not result.success:
            logger.error(f"Failed to read Materials sheet: {result.error}")
            return {"success": False, "error": result.error}
        
        data = result.data
        if not data or len(data) < 2:
            return {"success": False, "error": "Materials sheet is empty or has no data rows"}
        
        headers = data[0]
        rows = data[1:]
        
        logger.info(f"🌳 Processing {len(rows)} materials taxonomy rows...")
        
        # Clear existing materials data
        session = self.Session()
        try:
            session.query(MaterialTaxonomy).delete()
            session.commit()
            logger.info("🗑️ Cleared existing materials taxonomy")
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
        
        self.stats['materials']['total_read'] = len(rows)
        
        session = self.Session()
        try:
            for i, row in enumerate(rows):
                try:
                    if self._is_empty_row(row):
                        self.stats['materials']['skipped_empty_rows'] += 1
                        continue
                    
                    material = self._convert_material_row(row, headers, i + 2)
                    if material:
                        session.add(material)
                        self.stats['materials']['successful_migrations'] += 1
                    else:
                        self.stats['materials']['failed_migrations'] += 1
                        
                except Exception as e:
                    error_msg = f"Row {i + 2}: {str(e)}"
                    self.stats['materials']['errors'].append(error_msg)
                    self.stats['materials']['failed_migrations'] += 1
                    logger.warning(f"Failed to process material row {i + 2}: {e}")
                    continue
            
            session.commit()
            logger.info(f"✅ Committed {self.stats['materials']['successful_migrations']} materials")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to commit materials: {e}")
            return {"success": False, "error": f"Database commit failed: {e}"}
        finally:
            session.close()
        
        return {
            "success": True,
            "stats": self.stats['materials'].copy()
        }
    
    def _convert_inventory_row(self, row: List[Any], headers: List[str], row_num: int) -> Optional[InventoryItem]:
        """Convert a Google Sheets row to an InventoryItem"""
        if len(row) < 2:
            return None
        
        # Extract basic required fields
        active_str = self._safe_get_string(row, 0)
        ja_id = self._safe_get_string(row, 1)
        
        if not ja_id:
            logger.warning(f"Row {row_num}: Missing JA ID, skipping")
            return None
        
        # Parse active status
        active = active_str.lower() in ['1', 'true', 'yes', 'active']
        
        # Create inventory item with data mapping
        try:
            item = InventoryItem(
                ja_id=ja_id,
                active=active,
                length=self._safe_get_decimal(row, 2),
                width=self._safe_get_decimal(row, 3),
                thickness=self._safe_get_decimal(row, 4),
                wall_thickness=self._safe_get_decimal(row, 5),
                weight=self._safe_get_decimal(row, 6),
                item_type=self._safe_get_string(row, 7),
                shape=self._safe_get_string(row, 8),
                material=self._safe_get_string(row, 9),
                thread_series=self._safe_get_string(row, 10),
                thread_handedness=self._safe_get_string(row, 11),
                thread_size=self._safe_get_string(row, 13),
                quantity=self._safe_get_int(row, 14),
                location=self._safe_get_string(row, 15),
                sub_location=self._safe_get_string(row, 16),
                purchase_date=self._safe_get_date(row, 17),
                purchase_price=self._safe_get_decimal(row, 18),
                purchase_location=self._safe_get_string(row, 19),
                notes=self._safe_get_string(row, 20),
                vendor=self._safe_get_string(row, 21),
                vendor_part=self._safe_get_string(row, 22),
                original_material=self._safe_get_string(row, 23),
                original_thread=self._safe_get_string(row, 24),
                date_added=self._safe_get_datetime(row, 25),
                last_modified=self._safe_get_datetime(row, 26)
            )
            return item
        except Exception as e:
            logger.error(f"Failed to create InventoryItem for row {row_num}: {e}")
            return None
    
    def _convert_material_row(self, row: List[Any], headers: List[str], row_num: int) -> Optional[MaterialTaxonomy]:
        """Convert a Google Sheets row to a MaterialTaxonomy"""
        if len(row) < 3:
            return None
        
        name = self._safe_get_string(row, 0)
        level = self._safe_get_int(row, 1)
        parent_name = self._safe_get_string(row, 2)
        
        if not name:
            logger.warning(f"Row {row_num}: Missing material name, skipping")
            return None
        
        if level is None or level < 1 or level > 3:
            logger.warning(f"Row {row_num}: Invalid level {level} for material {name}, skipping")
            return None
        
        try:
            material = MaterialTaxonomy(
                name=name,
                level=level,
                parent=parent_name if parent_name else None
            )
            return material
        except Exception as e:
            logger.error(f"Failed to create MaterialTaxonomy for row {row_num}: {e}")
            return None
    
    def _is_empty_row(self, row: List[Any]) -> bool:
        """Check if a row is effectively empty"""
        return not any(str(cell).strip() for cell in row if cell is not None)
    
    # Data conversion helper methods
    def _safe_get_string(self, row: List[Any], index: int) -> str:
        """Safely get string value from row"""
        if index < len(row) and row[index] is not None:
            return str(row[index]).strip()
        return ""
    
    def _safe_get_int(self, row: List[Any], index: int) -> Optional[int]:
        """Safely get integer value from row"""
        if index < len(row) and row[index] is not None:
            try:
                value = str(row[index]).strip()
                if value:
                    return int(float(value))  # Handle "2.0" -> 2
            except (ValueError, TypeError):
                pass
        return None
    
    def _safe_get_decimal(self, row: List[Any], index: int) -> Optional[Decimal]:
        """Safely get decimal value from row"""
        if index < len(row) and row[index] is not None:
            try:
                value = str(row[index]).strip()
                if value:
                    decimal_value = Decimal(str(float(value)))
                    # Convert 0 to None for fields that should be positive
                    if decimal_value == 0:
                        return None
                    return decimal_value
            except (ValueError, TypeError, ArithmeticError):
                pass
        return None
    
    def _safe_get_date(self, row: List[Any], index: int) -> Optional[datetime]:
        """Safely get date value from row"""
        if index < len(row) and row[index] is not None:
            try:
                value = str(row[index]).strip()
                if value:
                    # Try common date formats
                    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                        try:
                            return datetime.strptime(value, fmt)
                        except ValueError:
                            continue
            except (ValueError, TypeError):
                pass
        return None
    
    def _safe_get_datetime(self, row: List[Any], index: int) -> Optional[datetime]:
        """Safely get datetime value from row"""
        if index < len(row) and row[index] is not None:
            try:
                value = str(row[index]).strip()
                if value:
                    # Try common datetime formats
                    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M:%S"]:
                        try:
                            return datetime.strptime(value, fmt)
                        except ValueError:
                            continue
                    # Try date-only formats
                    date_result = self._safe_get_date(row, index)
                    if date_result:
                        return date_result
            except (ValueError, TypeError):
                pass
        return None


def main():
    """Main migration function"""
    try:
        # Initialize Flask app for application context
        app = create_app(Config)
        
        with app.app_context():
            migrator = SheetsMigrationTool()
            results = migrator.migrate_all_data()
            
            # Print summary
            print("\n" + "="*80)
            print("🚀 GOOGLE SHEETS TO MARIADB MIGRATION SUMMARY")
            print("="*80)
            
            if results['overall_success']:
                print("✅ MIGRATION SUCCESSFUL")
            else:
                print("❌ MIGRATION FAILED")
            
            # Inventory items summary
            if results['inventory_migration']:
                inv = results['inventory_migration']
                print(f"\n📦 INVENTORY ITEMS MIGRATION:")
                if inv['success']:
                    stats = inv['stats']
                    print(f"   ✅ Success: {stats['successful_migrations']}/{stats['total_read']} rows")
                    if stats['failed_migrations'] > 0:
                        print(f"   ⚠️  Failed: {stats['failed_migrations']} rows")
                    if stats['skipped_empty_rows'] > 0:
                        print(f"   ℹ️  Skipped empty: {stats['skipped_empty_rows']} rows")
                    if stats['errors']:
                        print(f"   📄 Errors sample: {stats['errors'][:3]}")
                else:
                    print(f"   ❌ Failed: {inv['error']}")
            
            # Materials taxonomy summary
            if results['materials_migration']:
                mat = results['materials_migration']
                print(f"\n🌳 MATERIALS TAXONOMY MIGRATION:")
                if mat['success']:
                    stats = mat['stats']
                    print(f"   ✅ Success: {stats['successful_migrations']}/{stats['total_read']} rows")
                    if stats['failed_migrations'] > 0:
                        print(f"   ⚠️  Failed: {stats['failed_migrations']} rows")
                    if stats['skipped_empty_rows'] > 0:
                        print(f"   ℹ️  Skipped empty: {stats['skipped_empty_rows']} rows")
                    if stats['errors']:
                        print(f"   📄 Errors sample: {stats['errors'][:3]}")
                else:
                    print(f"   ❌ Failed: {mat['error']}")
            
            # Save detailed results
            import json
            output_file = 'migration_results.json'
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            
            print(f"\n💾 Detailed migration results saved to: {output_file}")
            print(f"📅 Migration completed at: {results['migration_timestamp']}")
            
            return results
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        traceback.print_exc()
        return None


if __name__ == "__main__":
    main()