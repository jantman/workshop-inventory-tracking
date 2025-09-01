"""
Inventory Service for Workshop Material Inventory Tracking

This service provides a high-level interface for inventory operations,
including CRUD operations, search, filtering, and batch operations.
It works with the Item model and abstracts the underlying storage.
"""

from typing import List, Dict, Any, Optional, Union, Tuple
from decimal import Decimal
from datetime import datetime
import time
from flask import current_app

from app.models import Item, ItemType, ItemShape, Thread, Dimensions
from app.storage import Storage, StorageResult
from app.google_sheets_storage import GoogleSheetsStorage
from app.performance import cached, timed, performance_monitor, batch_manager
from app.logging_config import log_operation, log_performance

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
    
    def item_type(self, item_type: ItemType) -> 'SearchFilter':
        """Filter by item type"""
        return self.add_exact_match('item_type', item_type.value)
    
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
    """High-level inventory management service"""
    
    # Standard sheet headers matching our migration script
    SHEET_HEADERS = [
        'Active', 'JA ID', 'Length', 'Width', 'Thickness', 'Wall Thickness',
        'Weight', 'Type', 'Shape', 'Material', 'Thread Series', 'Thread Handedness',
        'Thread Size', 'Quantity', 'Location', 'Sub-Location', 'Purchase Date',
        'Purchase Price', 'Purchase Location', 'Notes', 'Vendor', 'Vendor Part',
        'Original Material', 'Original Thread', 'Date Added', 'Last Modified'
    ]
    
    def __init__(self, storage: Storage):
        self.storage = storage
        self._cache = {}
        self._cache_timestamp = None
        self._cache_duration = 300  # 5 minutes
    
    @classmethod
    def create_default(cls, spreadsheet_id: str) -> 'InventoryService':
        """Create service with default Google Sheets storage"""
        storage = GoogleSheetsStorage(spreadsheet_id)
        return cls(storage)
    
    # Basic CRUD Operations
    
    @cached(ttl=300)  # Cache for 5 minutes
    @timed("get_item")
    def get_item(self, ja_id: str) -> Optional[Item]:
        """Get a single item by JA ID"""
        try:
            start_time = time.time()
            
            # First try to find in all items
            items = self.get_all_items()
            for item in items:
                if item.ja_id == ja_id:
                    log_operation("get_item", 
                                int((time.time() - start_time) * 1000), 
                                ja_id, 
                                {"found": True})
                    return item
            
            log_operation("get_item", 
                        int((time.time() - start_time) * 1000), 
                        ja_id, 
                        {"found": False})
            return None
        except Exception as e:
            current_app.logger.error(f"Failed to get item {ja_id}: {e}")
            return None
    
    @cached(ttl=180)  # Cache for 3 minutes (shorter than single item cache)
    @timed("get_all_items")
    def get_all_items(self, force_refresh: bool = False) -> List[Item]:
        """Get all inventory items with performance optimization"""
        try:
            start_time = time.time()
            
            result = self.storage.read_all('Metal')
            if not result.success:
                current_app.logger.error(f"Failed to read items: {result.error}")
                return []
            
            if not result.data or len(result.data) < 2:
                return []
            
            headers = result.data[0]
            rows = result.data[1:]
            
            items = []
            parse_errors = 0
            
            for row in rows:
                try:
                    item = Item.from_row(row, headers)
                    items.append(item)
                except Exception as e:
                    parse_errors += 1
                    current_app.logger.warning(f"Failed to parse item row: {e}")
                    continue
            
            # Log operation performance
            end_time = time.time()
            log_operation("get_all_items", 
                        int((end_time - start_time) * 1000), 
                        details={
                            "item_count": len(items),
                            "parse_errors": parse_errors,
                            "rows_processed": len(rows)
                        })
            
            return items
            
        except Exception as e:
            current_app.logger.error(f"Failed to get all items: {e}")
            return []
    
    @timed("add_item")
    def add_item(self, item: Item) -> bool:
        """Add a new item to inventory with performance optimization"""
        try:
            start_time = time.time()
            
            # Validate item doesn't already exist
            if self.get_item(item.ja_id):
                current_app.logger.error(f"Item {item.ja_id} already exists")
                return False
            
            # Convert to row format
            row = item.to_row(self.SHEET_HEADERS)
            
            # Add to batch or write immediately
            if batch_manager.add_to_batch('add_items', {'item': item, 'row': row}):
                # Batch is ready, process it
                batch = batch_manager.get_batch('add_items')
                rows_to_add = [entry['row'] for entry in batch]
                result = self.storage.write_rows('Metal', rows_to_add)
                
                if result.success:
                    # Clear cache since we added items
                    self.get_all_items.cache_clear()
                    
                    # Log batch operation
                    end_time = time.time()
                    log_operation("add_item_batch", 
                                int((end_time - start_time) * 1000), 
                                details={"batch_size": len(batch)})
                    
                    current_app.logger.info(f"Added batch of {len(batch)} items including {item.ja_id}")
                    return True
                else:
                    current_app.logger.error(f"Failed to add item batch: {result.error}")
                    return False
            else:
                # Add to batch for later processing
                log_operation("add_item", 
                            int((time.time() - start_time) * 1000), 
                            item.ja_id, 
                            {"batched": True})
                return True
                
        except Exception as e:
            current_app.logger.error(f"Failed to add item {item.ja_id}: {e}")
            return False
    
    def update_item(self, item: Item) -> bool:
        """Update an existing item"""
        try:
            # Find the item's row
            result = self.storage.read_all('Metal')
            if not result.success:
                return False
            
            headers = result.data[0]
            rows = result.data[1:]
            
            # Find row with matching JA ID
            for i, row in enumerate(rows):
                if len(row) > 1 and row[1] == item.ja_id:  # JA ID is column 1
                    # Update the row
                    updated_row = item.to_row(self.SHEET_HEADERS)
                    row_index = i + 2  # +1 for headers, +1 for 1-based indexing
                    
                    update_result = self.storage.update_row('Metal', row_index, updated_row)
                    if update_result.success:
                        self._invalidate_cache()
                        current_app.logger.info(f"Updated item {item.ja_id}")
                        return True
                    else:
                        current_app.logger.error(f"Failed to update item {item.ja_id}: {update_result.error}")
                        return False
            
            current_app.logger.error(f"Item {item.ja_id} not found for update")
            return False
            
        except Exception as e:
            current_app.logger.error(f"Failed to update item {item.ja_id}: {e}")
            return False
    
    def deactivate_item(self, ja_id: str) -> bool:
        """Deactivate an item (set active = False)"""
        item = self.get_item(ja_id)
        if not item:
            return False
        
        item.active = False
        item.last_modified = datetime.now()
        return self.update_item(item)
    
    def activate_item(self, ja_id: str) -> bool:
        """Activate an item (set active = True)"""
        item = self.get_item(ja_id)
        if not item:
            return False
        
        item.active = True
        item.last_modified = datetime.now()
        return self.update_item(item)
    
    # Search and Filtering
    
    def search_items(self, search_filter: SearchFilter) -> List[Item]:
        """Search items with complex filtering"""
        items = self.get_all_items()
        filtered_items = []
        
        for item in items:
            if self._matches_filter(item, search_filter):
                filtered_items.append(item)
        
        return filtered_items
    
    def _matches_filter(self, item: Item, search_filter: SearchFilter) -> bool:
        """Check if item matches search filter"""
        # Exact match filters
        for field, value in search_filter.filters.items():
            if not self._matches_exact(item, field, value):
                return False
        
        # Range filters
        for field, range_spec in search_filter.ranges.items():
            if not self._matches_range(item, field, range_spec):
                return False
        
        # Text search filters
        for field, search_spec in search_filter.text_searches.items():
            if not self._matches_text(item, field, search_spec):
                return False
        
        return True
    
    def _matches_exact(self, item: Item, field: str, value: Any) -> bool:
        """Check exact match for field"""
        if field == 'active':
            return item.active == value
        elif field == 'material':
            return item.material.lower() == str(value).lower()
        elif field == 'item_type':
            return item.item_type == value
        elif field == 'shape':
            return item.shape == value
        elif field == 'location':
            return (item.location or '').lower() == str(value).lower()
        elif field == 'ja_id':
            return item.ja_id == value
        elif field == 'thread_series':
            return item.thread and item.thread.series == value
        elif field == 'thread_form':
            return item.thread and item.thread.form == value
        
        return True
    
    def _matches_range(self, item: Item, field: str, range_spec: Dict[str, Optional[Decimal]]) -> bool:
        """Check range match for numeric field"""
        value = None
        
        if item.dimensions:
            if field == 'length':
                value = item.dimensions.length
            elif field == 'width':
                value = item.dimensions.width
            elif field == 'thickness':
                value = item.dimensions.thickness
            elif field == 'wall_thickness':
                value = item.dimensions.wall_thickness
            elif field == 'weight':
                value = item.dimensions.weight
        
        if value is None:
            return range_spec.get('min') is None and range_spec.get('max') is None
        
        min_val = range_spec.get('min')
        max_val = range_spec.get('max')
        
        if min_val is not None and value < min_val:
            return False
        if max_val is not None and value > max_val:
            return False
        
        return True
    
    def _matches_text(self, item: Item, field: str, search_spec: Dict[str, Any]) -> bool:
        """Check text search match"""
        query = search_spec['query'].lower()
        exact = search_spec.get('exact', False)
        
        text = ''
        if field == 'notes':
            text = item.notes or ''
        elif field == 'vendor':
            text = item.vendor or ''
        elif field == 'material':
            text = item.material or ''
        elif field == 'location':
            text = item.location or ''
        elif field == 'thread_size':
            text = item.thread.size if item.thread else ''
        
        text = text.lower()
        
        if exact:
            return text == query
        else:
            return query in text
    
    # Batch Operations
    
    def batch_move_items(self, ja_ids: List[str], new_location: str, 
                        new_sub_location: Optional[str] = None) -> Tuple[int, List[str]]:
        """Move multiple items to new location"""
        success_count = 0
        failed_ids = []
        
        for ja_id in ja_ids:
            item = self.get_item(ja_id)
            if not item:
                failed_ids.append(ja_id)
                continue
            
            item.location = new_location
            if new_sub_location is not None:
                item.sub_location = new_sub_location
            item.last_modified = datetime.now()
            
            if self.update_item(item):
                success_count += 1
            else:
                failed_ids.append(ja_id)
        
        return success_count, failed_ids
    
    def batch_deactivate_items(self, ja_ids: List[str]) -> Tuple[int, List[str]]:
        """Deactivate multiple items"""
        success_count = 0
        failed_ids = []
        
        for ja_id in ja_ids:
            if self.deactivate_item(ja_id):
                success_count += 1
            else:
                failed_ids.append(ja_id)
        
        return success_count, failed_ids
    
    # Special Operations
    
    def shorten_item(self, parent_ja_id: str, new_length: Decimal, 
                    new_ja_id: str) -> Optional[Item]:
        """Create a shortened version of an item"""
        parent = self.get_item(parent_ja_id)
        if not parent:
            return None
        
        if parent.dimensions.length is None or new_length >= parent.dimensions.length:
            return None
        
        # Deactivate parent
        parent.active = False
        parent.last_modified = datetime.now()
        parent.add_child(new_ja_id)
        
        # Create new shortened item
        new_item = Item(
            ja_id=new_ja_id,
            item_type=parent.item_type,
            shape=parent.shape,
            material=parent.material,
            dimensions=Dimensions(
                length=new_length,
                width=parent.dimensions.width,
                thickness=parent.dimensions.thickness,
                wall_thickness=parent.dimensions.wall_thickness,
                weight=None  # Weight will change
            ),
            thread=parent.thread,
            active=True,
            quantity=parent.quantity,
            location=parent.location,
            sub_location=parent.sub_location,
            purchase_date=parent.purchase_date,
            purchase_price=parent.purchase_price,
            purchase_location=parent.purchase_location,
            vendor=parent.vendor,
            vendor_part_number=parent.vendor_part_number,
            notes=f"Shortened from {parent_ja_id}",
            original_material=parent.original_material,
            original_thread=parent.original_thread,
            parent_ja_id=parent_ja_id
        )
        
        # Update parent and add new item
        if self.update_item(parent) and self.add_item(new_item):
            return new_item
        
        return None
    
    # Statistics and Reporting
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get inventory statistics"""
        items = self.get_all_items()
        
        stats = {
            'total_items': len(items),
            'active_items': len([i for i in items if i.active]),
            'inactive_items': len([i for i in items if not i.active]),
            'unique_materials': len(set(i.material for i in items)),
            'unique_locations': len(set(i.location for i in items if i.location)),
            'by_type': {},
            'by_shape': {},
            'by_material': {},
        }
        
        # Count by type
        for item in items:
            if item.active:
                type_name = item.item_type.value
                stats['by_type'][type_name] = stats['by_type'].get(type_name, 0) + 1
                
                shape_name = item.shape.value
                stats['by_shape'][shape_name] = stats['by_shape'].get(shape_name, 0) + 1
                
                material_name = item.material
                stats['by_material'][material_name] = stats['by_material'].get(material_name, 0) + 1
        
        return stats
    
    def get_low_stock_items(self, threshold: int = 1) -> List[Item]:
        """Get items with quantity at or below threshold"""
        items = self.get_all_items()
        return [item for item in items if item.active and item.quantity <= threshold]
    
    def get_items_without_location(self) -> List[Item]:
        """Get active items without location specified"""
        items = self.get_all_items()
        return [item for item in items if item.active and not item.location]
    
    # Cache Management
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid"""
        if not self._cache_timestamp:
            return False
        
        age = (datetime.now() - self._cache_timestamp).total_seconds()
        return age < self._cache_duration
    
    def _invalidate_cache(self):
        """Invalidate the cache"""
        self._cache.clear()
        self._cache_timestamp = None
    
    def refresh_cache(self):
        """Force refresh the cache"""
        self._invalidate_cache()
        self.get_all_items(force_refresh=True)