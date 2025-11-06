"""
MariaDB Inventory Service

Provides inventory management functionality specifically designed for MariaDB backend.
Handles multi-row JA ID scenarios with proper active/inactive item logic.
"""

import logging
import warnings
# Suppress SQLAlchemy warnings about Decimal support in SQLite (used in tests)
warnings.filterwarnings("ignore", message=".*does.*not.*support Decimal objects natively.*")
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from decimal import Decimal
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, and_, desc, asc, func

from .mariadb_storage import MariaDBStorage
from .database import InventoryItem
from .models import ItemType, ItemShape
# Using enhanced InventoryItem directly instead of separate Item dataclass
from .storage import StorageResult
from config import Config

logger = logging.getLogger(__name__)


class SearchFilter:
    """Search filter specification"""
    
    def __init__(self):
        self.filters = {}
        self.ranges = {}
        self.text_searches = {}
    
    def add_exact_match(self, field: str, value: Any) -> 'SearchFilter':
        """Add exact match filter"""
        self.filters[field] = value
        return self
    
    def add_range(self, field: str, min_value: Optional[Decimal] = None, 
                  max_value: Optional[Decimal] = None) -> 'SearchFilter':
        """Add numeric range filter"""
        self.ranges[field] = {'min': min_value, 'max': max_value}
        return self
    
    def add_text_search(self, field: str, query: str, exact: bool = False) -> 'SearchFilter':
        """Add text search filter"""
        self.text_searches[field] = {'query': query, 'exact': exact}
        return self
    
    def active_only(self) -> 'SearchFilter':
        """Filter for active items only"""
        return self.add_exact_match('active', True)
    
    def material(self, material: str) -> 'SearchFilter':
        """Filter by material"""
        return self.add_exact_match('material', material)
    
    def item_type(self, item_type) -> 'SearchFilter':
        """Filter by item type"""
        if hasattr(item_type, 'value'):
            return self.add_exact_match('item_type', item_type.value)
        else:
            return self.add_exact_match('item_type', item_type)
    
    def notes_contain(self, text: str) -> 'SearchFilter':
        """Filter by notes containing text"""
        return self.add_text_search('notes', text)
    
    def length_range(self, min_length=None, max_length=None) -> 'SearchFilter':
        """Filter by length range"""
        return self.add_range('length', min_length, max_length)
    
    def to_dict(self) -> dict:
        """Convert SearchFilter to dictionary for compatibility"""
        result = {}
        
        # Copy filters, converting enum objects to their string values
        for key, value in self.filters.items():
            if hasattr(value, 'value'):
                # Convert enum to its string value
                result[key] = value.value
            else:
                result[key] = value
        
        # Handle range filters - convert to min/max format
        for field, range_vals in self.ranges.items():
            if range_vals['min'] is not None:
                result[f'min_{field}'] = range_vals['min']
            if range_vals['max'] is not None:
                result[f'max_{field}'] = range_vals['max']
        
        # Handle text searches - add the search text directly to the field for LIKE searches
        for field, search_vals in self.text_searches.items():
            result[field] = search_vals['query']
            
        return result
    
    
    def shape(self, shape: ItemShape) -> 'SearchFilter':
        """Filter by shape"""
        return self.add_exact_match('shape', shape.value)
    
    def location(self, location: str) -> 'SearchFilter':
        """Filter by location"""
        return self.add_exact_match('location', location)
    
    def length_range(self, min_length: Optional[Decimal] = None, 
                    max_length: Optional[Decimal] = None) -> 'SearchFilter':
        """Filter by length range"""
        return self.add_range('length', min_length, max_length)
    
    def width_range(self, min_width: Optional[Decimal] = None, 
                   max_width: Optional[Decimal] = None) -> 'SearchFilter':
        """Filter by width range"""
        return self.add_range('width', min_width, max_width)
    
    def notes_contain(self, text: str) -> 'SearchFilter':
        """Filter by notes containing text"""
        return self.add_text_search('notes', text, exact=False)


class InventoryService:
    """MariaDB inventory service with multi-row JA ID support"""
    
    def __init__(self, storage: MariaDBStorage = None):
        """Initialize with MariaDB storage backend"""
        if storage is None:
            storage = MariaDBStorage()
        
        self.storage = storage
        self._cache = {}  # For test compatibility
        self._cache_timestamp = None  # For test compatibility
        
        # Direct database access for complex queries
        self.engine = storage.engine or self._create_engine()
        self.Session = sessionmaker(bind=self.engine)
    
    def _create_engine(self):
        """Create database engine if not provided by storage"""
        return create_engine(
            Config.SQLALCHEMY_DATABASE_URI,
            **Config.SQLALCHEMY_ENGINE_OPTIONS
        )
    
    def get_active_item(self, ja_id: str) -> Optional[InventoryItem]:
        """
        Get the currently active item for a JA ID
        
        This is the primary method for retrieving items - it only returns
        the active row for a given JA ID, which represents the current state
        of the physical item.
        
        Args:
            ja_id: The JA ID to search for
            
        Returns:
            InventoryItem object if active item found, None otherwise
        """
        try:
            session = self.Session()
            
            # Query for active item with this JA ID
            db_item = session.query(InventoryItem).filter(
                and_(
                    InventoryItem.ja_id == ja_id,
                    InventoryItem.active == True
                )
            ).first()
            
            if not db_item:
                return None
            
            # Return enhanced InventoryItem directly (no conversion needed)
            logger.debug(f"Found active item {ja_id}: length={db_item.dimensions.length}")
            return db_item
            
        except Exception as e:
            logger.error(f"Error getting active item {ja_id}: {e}")
            return None
        finally:
            if 'session' in locals():
                session.close()
    
    def get_item_history(self, ja_id: str) -> List[InventoryItem]:
        """
        Get all historical versions of an item (active and inactive)
        
        Returns items ordered by date_added (oldest first), allowing
        you to see the complete history of shortening operations.
        
        Args:
            ja_id: The JA ID to get history for
            
        Returns:
            List of InventoryItem objects sorted by date_added
        """
        try:
            session = self.Session()
            
            # Query for all items with this JA ID, ordered by date_added
            db_items = session.query(InventoryItem).filter(
                InventoryItem.ja_id == ja_id
            ).order_by(asc(InventoryItem.date_added)).all()
            
            # Return enhanced InventoryItems directly (no conversion needed)
            logger.debug(f"Found {len(db_items)} historical items for {ja_id}")
            return db_items
            
        except Exception as e:
            logger.error(f"Error getting item history for {ja_id}: {e}")
            return []
        finally:
            if 'session' in locals():
                session.close()
    
    def get_all_active_items(self) -> List[InventoryItem]:
        """
        Get all currently active items (one per JA ID)
        
        This returns only the active items, which represent the current
        state of all inventory items.
        
        Returns:
            List of active InventoryItem objects
        """
        try:
            session = self.Session()
            
            # Query for all active items
            db_items = session.query(InventoryItem).filter(
                InventoryItem.active == True
            ).order_by(asc(InventoryItem.ja_id)).all()
            
            # Return enhanced InventoryItems directly (no conversion needed)
            logger.info(f"Retrieved {len(db_items)} active inventory items")
            return db_items
            
        except Exception as e:
            logger.error(f"Error getting all active items: {e}")
            return []
        finally:
            if 'session' in locals():
                session.close()
    
    def search_active_items(self, filters: Dict[str, Any]) -> List[InventoryItem]:
        """
        Search for active items using filters
        
        Only searches among active items to ensure results represent
        current inventory state. Now uses enhanced InventoryItem with enum properties
        for simplified filtering logic.
        
        Args:
            filters: Dictionary of search filters
            
        Returns:
            List of matching active InventoryItem objects
        """
        try:
            session = self.Session()
            
            # Start with active items only
            query = session.query(InventoryItem).filter(InventoryItem.active == True)
            
            # Apply filters using enum properties where applicable
            if 'ja_id' in filters and filters['ja_id']:
                query = query.filter(InventoryItem.ja_id.ilike(f"%{filters['ja_id']}%"))
            
            if 'material' in filters and filters['material']:
                query = query.filter(InventoryItem.material == filters['material'])
            
            if 'item_type' in filters and filters['item_type']:
                # Use enum property for better type matching
                query = query.filter(InventoryItem.item_type == filters['item_type'])
            
            if 'shape' in filters and filters['shape']:
                # Use enum property for better shape matching
                query = query.filter(InventoryItem.shape == filters['shape'])

            if 'precision' in filters and filters['precision'] is not None:
                query = query.filter(InventoryItem.precision == filters['precision'])

            if 'location' in filters and filters['location']:
                query = query.filter(InventoryItem.location.ilike(f"%{filters['location']}%"))
            
            # Length range filters
            if 'min_length' in filters and filters['min_length']:
                query = query.filter(InventoryItem.length >= filters['min_length'])
            
            if 'max_length' in filters and filters['max_length']:
                query = query.filter(InventoryItem.length <= filters['max_length'])
            
            # Width range filters
            if 'min_width' in filters and filters['min_width']:
                query = query.filter(InventoryItem.width >= filters['min_width'])

            if 'max_width' in filters and filters['max_width']:
                query = query.filter(InventoryItem.width <= filters['max_width'])

            # Thickness range filters
            if 'min_thickness' in filters and filters['min_thickness']:
                query = query.filter(InventoryItem.thickness >= filters['min_thickness'])

            if 'max_thickness' in filters and filters['max_thickness']:
                query = query.filter(InventoryItem.thickness <= filters['max_thickness'])

            # Notes filtering
            if 'notes' in filters and filters['notes']:
                query = query.filter(InventoryItem.notes.ilike(f"%{filters['notes']}%"))
            
            # Execute query
            db_items = query.order_by(asc(InventoryItem.ja_id)).all()
            
            # Return enhanced InventoryItems directly (no conversion needed)
            logger.debug(f"Search found {len(db_items)} active items")
            return db_items
            
        except Exception as e:
            logger.error(f"Error searching active items: {e}")
            return []
        finally:
            if 'session' in locals():
                session.close()
    
    def ja_id_exists(self, ja_id: str, only_active: bool = True) -> bool:
        """
        Check if a JA ID exists in the database
        
        Args:
            ja_id: JA ID to check
            only_active: If True, only check active items
            
        Returns:
            True if JA ID exists, False otherwise
        """
        try:
            session = self.Session()
            
            query = session.query(InventoryItem.id).filter(InventoryItem.ja_id == ja_id)
            
            if only_active:
                query = query.filter(InventoryItem.active == True)
            
            exists = query.first() is not None
            return exists
            
        except Exception as e:
            logger.error(f"Error checking if JA ID {ja_id} exists: {e}")
            return False
        finally:
            if 'session' in locals():
                session.close()
    
    def shorten_item(self, ja_id: str, new_length: float, cut_date: str = None, notes: str = None) -> dict:
        """
        Shorten an existing item by creating a new active row and deactivating the current one.
        Keeps the same JA ID throughout the item's lifecycle.
        
        Args:
            ja_id: JA ID of the item to shorten
            new_length: New length after shortening (in inches)
            cut_date: Date when shortening occurred (defaults to today)
            notes: Optional notes about the shortening operation
            
        Returns:
            Dictionary with success status and details
        """
        from datetime import datetime, timezone, date
        from .logging_config import log_audit_operation
        
        try:
            session = self.Session()
            
            # Get current active item
            current_db_item = session.query(InventoryItem).filter(
                and_(InventoryItem.ja_id == ja_id, InventoryItem.active == True)
            ).first()
            
            if not current_db_item:
                error_msg = f'Active item {ja_id} not found'
                log_audit_operation('shorten_item_service', 'error',
                                  item_id=ja_id,
                                  error_details=error_msg,
                                  logger_name='mariadb_inventory_service')
                return {'success': False, 'error': error_msg}
            
            # AUDIT: Log the before state with complete item data
            item_before = current_db_item.to_dict()
            operation_data = {
                'ja_id': ja_id,
                'new_length': new_length,
                'cut_date': cut_date,
                'notes': notes,
                'original_length': float(current_db_item.length) if current_db_item.length else None
            }
            
            log_audit_operation('shorten_item_service', 'input',
                              item_id=ja_id,
                              form_data=operation_data,
                              item_before=item_before,
                              logger_name='mariadb_inventory_service')
            
            # Validate new length
            if new_length <= 0:
                error_msg = 'New length must be greater than 0'
                log_audit_operation('shorten_item_service', 'error',
                                  item_id=ja_id,
                                  form_data=operation_data,
                                  error_details=error_msg,
                                  logger_name='mariadb_inventory_service')
                return {'success': False, 'error': error_msg}
            
            if current_db_item.length and new_length >= float(current_db_item.length):
                error_msg = 'New length must be shorter than current length'
                log_audit_operation('shorten_item_service', 'error',
                                  item_id=ja_id,
                                  form_data=operation_data,
                                  error_details=error_msg,
                                  logger_name='mariadb_inventory_service')
                return {'success': False, 'error': error_msg}
            
            # Set cut date
            if cut_date:
                try:
                    cut_date_obj = datetime.strptime(cut_date, '%Y-%m-%d').date()
                except ValueError:
                    cut_date_obj = date.today()
            else:
                cut_date_obj = date.today()
            
            # Deactivate current item
            current_db_item.active = False
            current_db_item.last_modified = datetime.now(timezone.utc)
            
            # Build shortening notes
            shortening_notes = f"Shortened from {current_db_item.length}\" to {new_length}\" on {cut_date_obj}"
            if notes:
                shortening_notes += f"\nNotes: {notes}"
            if current_db_item.notes:
                shortening_notes += f"\n\nPrevious notes: {current_db_item.notes}"
            
            # Create new active item with same JA ID and shortened length
            new_db_item = InventoryItem(
                ja_id=ja_id,  # Keep same JA ID
                item_type=current_db_item.item_type,
                shape=current_db_item.shape,
                material=current_db_item.material,
                length=new_length,
                width=current_db_item.width,
                thickness=current_db_item.thickness,
                wall_thickness=current_db_item.wall_thickness,
                weight=current_db_item.weight,
                thread_series=current_db_item.thread_series,
                thread_handedness=current_db_item.thread_handedness,
                thread_size=current_db_item.thread_size,
                quantity=1,  # Shortened items are always quantity 1
                location=current_db_item.location,
                sub_location=current_db_item.sub_location,
                purchase_date=current_db_item.purchase_date,
                purchase_price=current_db_item.purchase_price,
                purchase_location=current_db_item.purchase_location,
                vendor=current_db_item.vendor,
                vendor_part=current_db_item.vendor_part,
                notes=shortening_notes,
                original_material=current_db_item.original_material,
                original_thread=current_db_item.original_thread,
                active=True,
                date_added=datetime.now(timezone.utc),
                last_modified=datetime.now(timezone.utc)
            )
            
            # Add new item to session
            session.add(new_db_item)
            
            # Commit changes
            session.commit()
            
            # AUDIT: Log successful completion with before/after state
            item_after = new_db_item.to_dict()
            success_result = {
                'success': True,
                'ja_id': ja_id,
                'original_length': float(current_db_item.length) if current_db_item.length else None,
                'new_length': new_length,
                'cut_date': str(cut_date_obj),
                'operation': 'shortening',
                'deactivated_item_id': current_db_item.id,
                'new_item_id': new_db_item.id
            }
            
            log_audit_operation('shorten_item_service', 'success',
                              item_id=ja_id,
                              form_data=operation_data,
                              item_before=item_before,
                              item_after=item_after,
                              changes=success_result,
                              logger_name='mariadb_inventory_service')
            
            logger.info(f"Successfully shortened item {ja_id}: {current_db_item.length}\" -> {new_length}\"")
            
            return success_result
            
        except Exception as e:
            error_msg = str(e)
            log_audit_operation('shorten_item_service', 'error',
                              item_id=ja_id,
                              form_data=operation_data if 'operation_data' in locals() else {'ja_id': ja_id, 'new_length': new_length},
                              item_before=item_before if 'item_before' in locals() else None,
                              error_details=error_msg,
                              logger_name='mariadb_inventory_service')
            logger.error(f"Error shortening item {ja_id}: {e}")
            if 'session' in locals():
                session.rollback()
            return {'success': False, 'error': error_msg}
        finally:
            if 'session' in locals():
                session.close()
    
    # Override parent class methods to use active-only logic
    
    def get_item(self, ja_id: str) -> Optional[InventoryItem]:
        """Override to return active item only"""
        return self.get_active_item(ja_id)
    
    def get_all_items(self, force_refresh: bool = False) -> List[InventoryItem]:
        """Override to return active items only"""
        return self.get_all_active_items()
    
    def get_valid_materials(self) -> List[str]:
        """
        Get list of all valid material names from the materials taxonomy.
        Returns both primary names and aliases.
        
        Returns:
            List of valid material names sorted alphabetically
        """
        try:
            from .database import MaterialTaxonomy
            
            session = self.Session()
            
            # Get all active materials from taxonomy
            materials = session.query(MaterialTaxonomy).filter(
                MaterialTaxonomy.active == True
            ).all()
            
            # Collect all valid names (primary names + aliases)
            valid_names = set()
            
            for material in materials:
                if material.name:
                    valid_names.add(material.name.strip())
                
                # Add aliases if they exist
                if material.aliases:
                    # Handle both string and list formats for aliases
                    if isinstance(material.aliases, str):
                        aliases = [a.strip() for a in material.aliases.split(',') if a.strip()]
                    else:
                        aliases = material.aliases
                    
                    for alias in aliases:
                        if alias and alias.strip():
                            valid_names.add(alias.strip())
            
            # Convert to sorted list, removing empty strings
            result = sorted([name for name in valid_names if name])
            
            logger.info(f"Retrieved {len(result)} valid materials from taxonomy")
            return result
            
        except Exception as e:
            logger.error(f"Error getting valid materials from MariaDB: {e}")
            # Return fallback materials if database query fails
            return ['Steel', 'Carbon Steel', 'Stainless Steel', 'Aluminum', 'Brass', 'Copper']
        finally:
            if 'session' in locals():
                session.close()
    
    def update_item(self, item: 'InventoryItem') -> bool:
        """
        Update an existing item in MariaDB
        
        For multi-row JA ID scenarios, this updates only the currently active item.
        The update preserves the item's history by modifying the existing active row
        rather than creating a new row (which is what shortening does).
        
        Args:
            item: InventoryItem model object with updated data
            
        Returns:
            True if update was successful, False otherwise
        """
        from .logging_config import log_audit_operation
        
        try:
            session = self.Session()
            
            # Get the current active item for this JA ID
            current_db_item = session.query(InventoryItem).filter(
                and_(InventoryItem.ja_id == item.ja_id, InventoryItem.active == True)
            ).first()
            
            if not current_db_item:
                error_msg = f'Active item {item.ja_id} not found for update'
                log_audit_operation('update_item_service', 'error',
                                  item_id=item.ja_id,
                                  error_details=error_msg,
                                  logger_name='mariadb_inventory_service')
                logger.error(error_msg)
                return False
            
            # Log the before state for audit purposes
            before_state = {
                'ja_id': current_db_item.ja_id,
                'item_type': current_db_item.item_type,
                'shape': current_db_item.shape,
                'material': current_db_item.material,
                'length': float(current_db_item.length) if current_db_item.length else None,
                'width': float(current_db_item.width) if current_db_item.width else None,
                'thickness': float(current_db_item.thickness) if current_db_item.thickness else None,
                'wall_thickness': float(current_db_item.wall_thickness) if current_db_item.wall_thickness else None,
                'weight': float(current_db_item.weight) if current_db_item.weight else None,
                'quantity': current_db_item.quantity,
                'location': current_db_item.location,
                'sub_location': current_db_item.sub_location,
                'thread_series': current_db_item.thread_series,
                'thread_handedness': current_db_item.thread_handedness,
                'thread_size': current_db_item.thread_size,
                'notes': current_db_item.notes,
                'vendor': current_db_item.vendor,
                'vendor_part': current_db_item.vendor_part
            }
            
            # InventoryItem already stores values as strings, no conversion needed
            item_type_value = item.item_type if item.item_type else None
            shape_value = item.shape if item.shape else None
            thread_series_value = item.thread_series if item.thread_series else ''
            thread_handedness_value = item.thread_handedness if item.thread_handedness else ''
            thread_size_value = item.thread_size if item.thread_size else ''
            
            # Update the database fields
            current_db_item.item_type = item_type_value
            current_db_item.shape = shape_value
            current_db_item.material = item.material
            current_db_item.length = item.dimensions.length
            current_db_item.width = item.dimensions.width
            current_db_item.thickness = item.dimensions.thickness
            current_db_item.wall_thickness = item.dimensions.wall_thickness
            current_db_item.weight = item.dimensions.weight
            current_db_item.quantity = item.quantity
            current_db_item.location = item.location
            current_db_item.sub_location = item.sub_location
            current_db_item.thread_series = thread_series_value
            current_db_item.thread_handedness = thread_handedness_value
            current_db_item.thread_size = thread_size_value
            current_db_item.notes = item.notes
            current_db_item.vendor = item.vendor
            current_db_item.vendor_part = item.vendor_part
            current_db_item.purchase_date = item.purchase_date
            current_db_item.purchase_price = item.purchase_price
            current_db_item.purchase_location = item.purchase_location
            current_db_item.active = item.active
            current_db_item.precision = getattr(item, 'precision', False)
            # Update timestamp
            current_db_item.last_modified = func.now()
            
            # Commit the changes
            session.commit()
            
            # Log the after state for audit purposes
            after_state = {
                'ja_id': item.ja_id,
                'item_type': item_type_value,
                'shape': shape_value,
                'material': item.material,
                'length': float(item.dimensions.length) if item.dimensions.length else None,
                'width': float(item.dimensions.width) if item.dimensions.width else None,
                'thickness': float(item.dimensions.thickness) if item.dimensions.thickness else None,
                'wall_thickness': float(item.dimensions.wall_thickness) if item.dimensions.wall_thickness else None,
                'weight': float(item.dimensions.weight) if item.dimensions.weight else None,
                'quantity': item.quantity,
                'location': item.location,
                'sub_location': item.sub_location,
                'thread_series': thread_series_value,
                'thread_handedness': thread_handedness_value,
                'thread_size': thread_size_value,
                'notes': item.notes,
                'vendor': item.vendor,
                'vendor_part': item.vendor_part
            }
            
            # Log successful update with full audit trail
            log_audit_operation('update_item_service', 'success',
                              item_id=item.ja_id,
                              item_before=before_state,
                              item_after=after_state,
                              logger_name='mariadb_inventory_service')
            
            logger.info(f"Successfully updated item {item.ja_id}")
            return True
            
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            
            error_msg = f"Failed to update item {item.ja_id}: {e}"
            log_audit_operation('update_item_service', 'error',
                              item_id=item.ja_id,
                              error_details=error_msg,
                              logger_name='mariadb_inventory_service')
            logger.error(error_msg)
            return False
        finally:
            if 'session' in locals():
                session.close()

    def add_item(self, item: 'InventoryItem') -> bool:
        """Add a new item to MariaDB"""
        from .logging_config import log_audit_operation
        
        try:
            session = self.Session()
            
            # Check if an active item with this JA ID already exists
            existing_item = session.query(InventoryItem).filter(
                and_(InventoryItem.ja_id == item.ja_id, InventoryItem.active == True)
            ).first()
            
            if existing_item:
                error_msg = f'Active item {item.ja_id} already exists'
                log_audit_operation('add_item_service', 'error',
                                  item_id=item.ja_id,
                                  error_details=error_msg,
                                  logger_name='mariadb_inventory_service')
                logger.error(error_msg)
                return False
            
            # Convert Item model to database fields
            item_type_str = item.item_type if item.item_type else None
            shape_str = item.shape if item.shape else None
            
            # Extract dimensions directly from InventoryItem fields
            length = item.length
            width = item.width  
            thickness = item.thickness
            wall_thickness = item.wall_thickness
            weight = item.weight
            
            # Extract threading info directly from InventoryItem fields
            thread_series_str = item.thread_series
            thread_handedness_str = item.thread_handedness
            thread_size = item.thread_size
            
            # Create new database item
            new_db_item = InventoryItem(
                ja_id=item.ja_id,
                item_type=item_type_str,
                shape=shape_str,
                material=item.material,
                length=length,
                width=width,
                thickness=thickness,
                wall_thickness=wall_thickness,
                weight=weight,
                thread_series=thread_series_str,
                thread_handedness=thread_handedness_str,
                thread_size=thread_size,
                quantity=getattr(item, 'quantity', 1),
                location=getattr(item, 'location', None),
                sub_location=getattr(item, 'sub_location', None),
                purchase_date=getattr(item, 'purchase_date', None),
                purchase_price=float(getattr(item, 'purchase_price', 0)) if getattr(item, 'purchase_price', None) else None,
                purchase_location=getattr(item, 'purchase_location', None),
                notes=getattr(item, 'notes', None),
                vendor=getattr(item, 'vendor', None),
                vendor_part=getattr(item, 'vendor_part', None),
                precision=getattr(item, 'precision', False),
                active=True
            )
            
            session.add(new_db_item)
            session.commit()
            
            # Log successful operation
            log_audit_operation('add_item_service', 'success',
                              item_id=item.ja_id,
                              item_after={
                                  'ja_id': item.ja_id,
                                  'item_type': item_type_str,
                                  'shape': shape_str,
                                  'material': item.material,
                                  'length': length,
                                  'width': width,
                                  'thickness': thickness,
                                  'wall_thickness': wall_thickness,
                                  'weight': weight,
                                  'thread_series': thread_series_str,
                                  'thread_handedness': thread_handedness_str,
                                  'thread_size': thread_size,
                                  'quantity': getattr(item, 'quantity', 1),
                                  'location': getattr(item, 'location', None),
                                  'purchase_date': getattr(item, 'purchase_date', None).isoformat() if getattr(item, 'purchase_date', None) else None,
                                  'purchase_price': float(getattr(item, 'purchase_price', 0)) if getattr(item, 'purchase_price', None) else None,
                                  'notes': getattr(item, 'notes', None),
                                  'active': True
                              },
                              logger_name='mariadb_inventory_service')
            
            logger.info(f'Successfully added item {item.ja_id} to database')
            return True
            
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            
            error_msg = f'Failed to add item {item.ja_id}: {str(e)}'
            log_audit_operation('add_item_service', 'error',
                              item_id=item.ja_id,
                              error_details=error_msg,
                              logger_name='mariadb_inventory_service')
            logger.error(error_msg)
            return False
        finally:
            if 'session' in locals():
                session.close()
    
    def deactivate_item(self, ja_id: str) -> bool:
        """Deactivate an item (set active = False) - override to work with database directly"""
        try:
            session = self.Session()
            
            # Find the active item in the database
            db_item = session.query(InventoryItem).filter(
                and_(
                    InventoryItem.ja_id == ja_id,
                    InventoryItem.active == True
                )
            ).first()
            
            if not db_item:
                return False
            
            # Deactivate the item
            db_item.active = False
            db_item.last_modified = datetime.now(timezone.utc)
            
            session.commit()
            logger.info(f'Successfully deactivated item {ja_id}')
            return True
            
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            logger.error(f'Error deactivating item {ja_id}: {e}')
            return False
        finally:
            if 'session' in locals():
                session.close()
    
    def activate_item(self, ja_id: str) -> bool:
        """Activate an item (set active = True) - override to work with database directly"""
        try:
            session = self.Session()
            
            # Find the most recent inactive item in the database
            db_item = session.query(InventoryItem).filter(
                and_(
                    InventoryItem.ja_id == ja_id,
                    InventoryItem.active == False
                )
            ).order_by(InventoryItem.date_added.desc()).first()
            
            if not db_item:
                return False
            
            # Activate the item
            db_item.active = True
            db_item.last_modified = datetime.now(timezone.utc)
            
            session.commit()
            logger.info(f'Successfully activated item {ja_id}')
            return True
            
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            logger.error(f'Error activating item {ja_id}: {e}')
            return False
        finally:
            if 'session' in locals():
                session.close()
    
    def search_items(self, search_filter: 'SearchFilter') -> List['InventoryItem']:
        """
        Search for items using a SearchFilter object.
        This method provides compatibility with the original InventoryService API.
        """
        return self.search_active_items(search_filter.to_dict())
    
    def batch_move_items(self, item_ids: List[str], location_id: str, notes: str = None) -> tuple[int, List[str]]:
        """
        Move multiple items to a new location.
        Returns (count_moved, failed_ids)
        """
        moved_count = 0
        failed_ids = []
        
        for item_id in item_ids:
            try:
                # Get current item
                item = self.get_item(item_id)
                if not item:
                    failed_ids.append(item_id)
                    continue
                
                # Update location and optionally notes directly on InventoryItem
                item.location = location_id
                if notes:
                    item.notes = notes
                
                if self.update_item(item):
                    moved_count += 1
                else:
                    failed_ids.append(item_id)
                    
            except Exception:
                failed_ids.append(item_id)
                
        return moved_count, failed_ids
    
    def batch_deactivate_items(self, item_ids: List[str]) -> tuple[int, List[str]]:
        """
        Deactivate multiple items.
        Returns (count_deactivated, failed_ids)
        """
        deactivated_count = 0
        failed_ids = []
        
        for item_id in item_ids:
            try:
                if self.deactivate_item(item_id):
                    deactivated_count += 1
                else:
                    failed_ids.append(item_id)
            except Exception:
                failed_ids.append(item_id)
                
        return deactivated_count, failed_ids