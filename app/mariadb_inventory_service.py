"""
MariaDB Inventory Service

Provides inventory management functionality specifically designed for MariaDB backend.
Handles multi-row JA ID scenarios with proper active/inactive item logic.
"""

import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, and_, desc, asc

from .inventory_service import InventoryService
from .mariadb_storage import MariaDBStorage
from .database import InventoryItem
from .models import Item
from .storage import StorageResult
from config import Config

logger = logging.getLogger(__name__)


class MariaDBInventoryService(InventoryService):
    """MariaDB-specific inventory service with multi-row JA ID support"""
    
    def __init__(self, storage: MariaDBStorage = None):
        """Initialize with MariaDB storage backend"""
        if storage is None:
            storage = MariaDBStorage()
        
        super().__init__(storage)
        
        # Direct database access for complex queries
        self.engine = storage.engine or self._create_engine()
        self.Session = sessionmaker(bind=self.engine)
    
    def _create_engine(self):
        """Create database engine if not provided by storage"""
        return create_engine(
            Config.SQLALCHEMY_DATABASE_URI,
            **Config.SQLALCHEMY_ENGINE_OPTIONS
        )
    
    def get_active_item(self, ja_id: str) -> Optional[Item]:
        """
        Get the currently active item for a JA ID
        
        This is the primary method for retrieving items - it only returns
        the active row for a given JA ID, which represents the current state
        of the physical item.
        
        Args:
            ja_id: The JA ID to search for
            
        Returns:
            Item object if active item found, None otherwise
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
            
            # Convert to Item model
            item = self._db_item_to_model(db_item)
            logger.debug(f"Found active item {ja_id}: length={item.dimensions.length}")
            return item
            
        except Exception as e:
            logger.error(f"Error getting active item {ja_id}: {e}")
            return None
        finally:
            if 'session' in locals():
                session.close()
    
    def get_item_history(self, ja_id: str) -> List[Item]:
        """
        Get all historical versions of an item (active and inactive)
        
        Returns items ordered by date_added (oldest first), allowing
        you to see the complete history of shortening operations.
        
        Args:
            ja_id: The JA ID to get history for
            
        Returns:
            List of Item objects sorted by date_added
        """
        try:
            session = self.Session()
            
            # Query for all items with this JA ID, ordered by date_added
            db_items = session.query(InventoryItem).filter(
                InventoryItem.ja_id == ja_id
            ).order_by(asc(InventoryItem.date_added)).all()
            
            items = []
            for db_item in db_items:
                item = self._db_item_to_model(db_item)
                items.append(item)
            
            logger.debug(f"Found {len(items)} historical items for {ja_id}")
            return items
            
        except Exception as e:
            logger.error(f"Error getting item history for {ja_id}: {e}")
            return []
        finally:
            if 'session' in locals():
                session.close()
    
    def get_all_active_items(self) -> List[Item]:
        """
        Get all currently active items (one per JA ID)
        
        This returns only the active items, which represent the current
        state of all inventory items.
        
        Returns:
            List of active Item objects
        """
        try:
            session = self.Session()
            
            # Query for all active items
            db_items = session.query(InventoryItem).filter(
                InventoryItem.active == True
            ).order_by(asc(InventoryItem.ja_id)).all()
            
            items = []
            for db_item in db_items:
                item = self._db_item_to_model(db_item)
                items.append(item)
            
            logger.info(f"Retrieved {len(items)} active inventory items")
            return items
            
        except Exception as e:
            logger.error(f"Error getting all active items: {e}")
            return []
        finally:
            if 'session' in locals():
                session.close()
    
    def search_active_items(self, filters: Dict[str, Any]) -> List[Item]:
        """
        Search for active items using filters
        
        Only searches among active items to ensure results represent
        current inventory state.
        
        Args:
            filters: Dictionary of search filters
            
        Returns:
            List of matching active Item objects
        """
        try:
            session = self.Session()
            
            # Start with active items only
            query = session.query(InventoryItem).filter(InventoryItem.active == True)
            
            # Apply filters
            if 'ja_id' in filters and filters['ja_id']:
                query = query.filter(InventoryItem.ja_id.ilike(f"%{filters['ja_id']}%"))
            
            if 'material' in filters and filters['material']:
                query = query.filter(InventoryItem.material.ilike(f"%{filters['material']}%"))
            
            if 'item_type' in filters and filters['item_type']:
                query = query.filter(InventoryItem.item_type == filters['item_type'])
            
            if 'shape' in filters and filters['shape']:
                query = query.filter(InventoryItem.shape == filters['shape'])
            
            if 'location' in filters and filters['location']:
                query = query.filter(InventoryItem.location.ilike(f"%{filters['location']}%"))
            
            # Length range filters
            if 'min_length' in filters and filters['min_length']:
                query = query.filter(InventoryItem.length >= filters['min_length'])
            
            if 'max_length' in filters and filters['max_length']:
                query = query.filter(InventoryItem.length <= filters['max_length'])
            
            # Execute query
            db_items = query.order_by(asc(InventoryItem.ja_id)).all()
            
            items = []
            for db_item in db_items:
                item = self._db_item_to_model(db_item)
                items.append(item)
            
            logger.debug(f"Search found {len(items)} active items")
            return items
            
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
    
    def _db_item_to_model(self, db_item: InventoryItem) -> Item:
        """
        Convert database InventoryItem to Item model
        
        Args:
            db_item: SQLAlchemy InventoryItem object
            
        Returns:
            Item model object
        """
        from .models import Item, Dimensions, Thread
        from .database import ThreadSeries, ThreadHandedness, ItemType, ItemShape
        
        # Helper function to find enum by value
        def find_enum_by_value(enum_class, value):
            if not value:
                return None
            for enum_item in enum_class:
                if enum_item.value == value:
                    return enum_item
            return None
        
        # Map thread series
        thread_series = find_enum_by_value(ThreadSeries, db_item.thread_series)
        
        # Map thread handedness  
        thread_handedness = find_enum_by_value(ThreadHandedness, db_item.thread_handedness)
        
        # Create thread object - only if we have meaningful thread data
        thread = None
        if thread_series or thread_handedness or (db_item.thread_size and db_item.thread_size.strip()):
            try:
                thread = Thread(
                    series=thread_series,
                    handedness=thread_handedness,
                    size=db_item.thread_size.strip() if db_item.thread_size else None
                )
            except ValueError:
                # Skip thread creation if validation fails - thread data is malformed
                thread = None
        
        # Create dimensions
        dimensions = Dimensions(
            length=float(db_item.length) if db_item.length else None,
            width=float(db_item.width) if db_item.width else None,
            thickness=float(db_item.thickness) if db_item.thickness else None,
            wall_thickness=float(db_item.wall_thickness) if db_item.wall_thickness else None,
            weight=float(db_item.weight) if db_item.weight else None
        )
        
        # Map item type and shape
        item_type = find_enum_by_value(ItemType, db_item.item_type)
        shape = find_enum_by_value(ItemShape, db_item.shape)
        
        # Create Item
        item = Item(
            ja_id=db_item.ja_id,
            item_type=item_type,
            shape=shape,
            material=db_item.material,
            dimensions=dimensions,
            thread=thread,
            quantity=db_item.quantity,
            location=db_item.location,
            sub_location=db_item.sub_location,
            purchase_date=db_item.purchase_date,
            purchase_price=db_item.purchase_price,
            purchase_location=db_item.purchase_location,
            notes=db_item.notes,
            vendor=db_item.vendor,
            vendor_part_number=db_item.vendor_part,
            original_material=db_item.original_material,
            original_thread=db_item.original_thread,
            active=db_item.active,
            date_added=db_item.date_added,
            last_modified=db_item.last_modified
        )
        
        return item
    
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
        from datetime import datetime, date
        
        try:
            session = self.Session()
            
            # Get current active item
            current_db_item = session.query(InventoryItem).filter(
                and_(InventoryItem.ja_id == ja_id, InventoryItem.active == True)
            ).first()
            
            if not current_db_item:
                return {'success': False, 'error': f'Active item {ja_id} not found'}
            
            # Validate new length
            if new_length <= 0:
                return {'success': False, 'error': 'New length must be greater than 0'}
            
            if current_db_item.length and new_length >= float(current_db_item.length):
                return {'success': False, 'error': 'New length must be shorter than current length'}
            
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
            current_db_item.last_modified = datetime.utcnow()
            
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
                thread_form=current_db_item.thread_form,
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
                date_added=datetime.utcnow(),
                last_modified=datetime.utcnow()
            )
            
            # Add new item to session
            session.add(new_db_item)
            
            # Commit changes
            session.commit()
            
            logger.info(f"Successfully shortened item {ja_id}: {current_db_item.length}\" -> {new_length}\"")
            
            return {
                'success': True,
                'ja_id': ja_id,
                'original_length': float(current_db_item.length) if current_db_item.length else None,
                'new_length': new_length,
                'cut_date': str(cut_date_obj),
                'operation': 'shortening'
            }
            
        except Exception as e:
            logger.error(f"Error shortening item {ja_id}: {e}")
            if 'session' in locals():
                session.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            if 'session' in locals():
                session.close()
    
    # Override parent class methods to use active-only logic
    
    def get_item(self, ja_id: str) -> Optional[Item]:
        """Override to return active item only"""
        return self.get_active_item(ja_id)
    
    def get_all_items(self, force_refresh: bool = False) -> List[Item]:
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