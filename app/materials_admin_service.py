"""
Materials Taxonomy Admin Service

Handles administrative operations for the hierarchical materials taxonomy.
Supports adding new entries, managing status, and validating relationships.
"""

from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass

from .storage import Storage
from .materials_service import MaterialHierarchyService, MaterialTaxonomy
from .exceptions import ValidationError


@dataclass
class TaxonomyAddRequest:
    """Request to add a new taxonomy entry"""
    name: str
    level: int  # 1=Category, 2=Family, 3=Material
    parent: str = ''  # Empty for categories
    aliases: List[str] = None
    notes: str = ''
    sort_order: int = 0


class MaterialsAdminService:
    """Service for managing materials taxonomy through admin interface"""
    
    def __init__(self, storage: Storage):
        self.storage = storage
        self.hierarchy_service = MaterialHierarchyService(storage)
    
    def get_taxonomy_overview(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        Get complete taxonomy overview for admin interface
        Returns hierarchical structure with usage statistics
        """
        all_materials = self.hierarchy_service.get_all_materials(active_only=not include_inactive)
        
        # Group by level for easier processing
        categories = [m for m in all_materials if m.level == 1]
        families = [m for m in all_materials if m.level == 2]  
        materials = [m for m in all_materials if m.level == 3]
        
        # Build hierarchical structure
        overview = []
        
        for category in sorted(categories, key=lambda x: (x.sort_order, x.name)):
            category_data = {
                'name': category.name,
                'level': category.level,
                'parent': category.parent,
                'aliases': category.aliases,
                'active': category.active,
                'sort_order': category.sort_order,
                'notes': category.notes,
                'children': []
            }
            
            # Add families under this category
            category_families = [f for f in families if f.parent == category.name]
            for family in sorted(category_families, key=lambda x: (x.sort_order, x.name)):
                family_data = {
                    'name': family.name,
                    'level': family.level,
                    'parent': family.parent,
                    'aliases': family.aliases,
                    'active': family.active,
                    'sort_order': family.sort_order,
                    'notes': family.notes,
                    'children': []
                }
                
                # Add materials under this family
                family_materials = [m for m in materials if m.parent == family.name]
                for material in sorted(family_materials, key=lambda x: (x.sort_order, x.name)):
                    material_data = {
                        'name': material.name,
                        'level': material.level,
                        'parent': material.parent,
                        'aliases': material.aliases,
                        'active': material.active,
                        'sort_order': material.sort_order,
                        'notes': material.notes,
                        'children': []
                    }
                    family_data['children'].append(material_data)
                
                category_data['children'].append(family_data)
            
            # Add materials directly under category (if any)
            direct_materials = [m for m in materials if m.parent == category.name]
            for material in sorted(direct_materials, key=lambda x: (x.sort_order, x.name)):
                material_data = {
                    'name': material.name,
                    'level': material.level,
                    'parent': material.parent,
                    'aliases': material.aliases,
                    'active': material.active,
                    'sort_order': material.sort_order,
                    'notes': material.notes,
                    'children': []
                }
                category_data['children'].append(material_data)
                
            overview.append(category_data)
        
        return overview
    
    def validate_add_request(self, request: TaxonomyAddRequest) -> Tuple[bool, List[str]]:
        """
        Validate a request to add a new taxonomy entry
        Returns (is_valid, error_messages)
        """
        errors = []
        
        # Basic validation
        if not request.name or not request.name.strip():
            errors.append("Name is required")
            
        if request.level not in [1, 2, 3]:
            errors.append("Level must be 1 (Category), 2 (Family), or 3 (Material)")
            
        # Level-specific validation
        if request.level > 1 and not request.parent:
            errors.append(f"Level {request.level} entries must have a parent")
            
        if request.level == 1 and request.parent:
            errors.append("Categories (Level 1) cannot have a parent")
        
        # Check for duplicates (case-insensitive)
        existing = self.hierarchy_service.get_by_name(request.name)
        if existing:
            errors.append(f"Material '{request.name}' already exists")
        
        # Check aliases for conflicts
        if request.aliases:
            for alias in request.aliases:
                if alias.strip():
                    existing_alias = self.hierarchy_service.get_by_name(alias.strip())
                    if existing_alias:
                        errors.append(f"Alias '{alias}' conflicts with existing material '{existing_alias.name}'")
        
        # Validate parent exists and is correct level
        if request.parent:
            parent_material = self.hierarchy_service.get_by_name(request.parent)
            if not parent_material:
                errors.append(f"Parent '{request.parent}' does not exist")
            else:
                expected_parent_level = request.level - 1
                if parent_material.level != expected_parent_level:
                    errors.append(f"Parent must be Level {expected_parent_level}, but '{request.parent}' is Level {parent_material.level}")
        
        return len(errors) == 0, errors
    
    def add_taxonomy_entry(self, request: TaxonomyAddRequest) -> Tuple[bool, str]:
        """
        Add a new taxonomy entry to the Materials sheet
        Returns (success, message)
        """
        # Validate request
        is_valid, errors = self.validate_add_request(request)
        if not is_valid:
            return False, "; ".join(errors)
        
        # Prepare row data for Materials sheet
        aliases_str = ', '.join([alias.strip() for alias in (request.aliases or []) if alias.strip()])
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        row_data = [
            request.name.strip(),           # name
            request.level,                  # level  
            request.parent,                 # parent
            aliases_str,                    # aliases
            True,                          # active
            request.sort_order,            # sort_order
            current_time,                  # created_date
            request.notes.strip()          # notes
        ]
        
        try:
            # Add to Materials sheet
            result = self.storage.write_row('Materials', row_data)
            if result.success:
                # Clear hierarchy service cache to pick up new entry
                self.hierarchy_service.refresh_cache()
                return True, f"Successfully added '{request.name}' to taxonomy"
            else:
                return False, f"Failed to add entry: {result.error}"
                
        except Exception as e:
            return False, f"Error adding taxonomy entry: {str(e)}"
    
    def set_material_status(self, name: str, active: bool) -> Tuple[bool, str]:
        """
        Set the active status of a taxonomy entry (enable/disable)
        Returns (success, message)
        """
        # Find the material
        material = self.hierarchy_service.get_by_name(name)
        if not material:
            return False, f"Material '{name}' not found"
        
        # Read all data to find the row to update
        result = self.storage.read_all('Materials')
        if not result.success:
            return False, f"Failed to read Materials sheet: {result.error}"
        
        data = result.data
        if not data or len(data) < 2:
            return False, "Materials sheet is empty or has no data rows"
        
        headers = data[0]
        rows = data[1:]
        
        # Find the row with this material name
        target_row_index = None
        for i, row in enumerate(rows):
            if len(row) > 0 and row[0] == name:  # name is first column
                target_row_index = i + 2  # +2 because: +1 for header, +1 for 1-indexed sheets
                break
        
        if target_row_index is None:
            return False, f"Could not find row for material '{name}'"
        
        try:
            # Get current row data
            current_row = rows[target_row_index - 2]  # Convert back to 0-indexed
            
            # Update only the active column (index 4)
            updated_row = current_row.copy()
            while len(updated_row) < 8:  # Ensure row has all columns
                updated_row.append('')
            updated_row[4] = active  # active column
            
            # Update the row in the sheet
            update_result = self.storage.update_row('Materials', target_row_index, updated_row)
            if update_result.success:
                # Clear cache to pick up changes
                self.hierarchy_service.refresh_cache()
                status_word = "activated" if active else "deactivated"
                return True, f"Successfully {status_word} '{name}'"
            else:
                return False, f"Failed to update status: {update_result.error}"
                
        except Exception as e:
            return False, f"Error updating material status: {str(e)}"
    
    def get_available_parents(self, level: int) -> List[MaterialTaxonomy]:
        """
        Get available parent options for a given level
        Level 2 (Families) can have Level 1 (Categories) as parents
        Level 3 (Materials) can have Level 2 (Families) as parents
        """
        if level <= 1:
            return []  # Categories have no parents
        
        parent_level = level - 1
        return self.hierarchy_service.get_by_level(parent_level, active_only=True)
    
    def get_usage_statistics(self) -> Dict[str, int]:
        """
        Get statistics about taxonomy usage
        This would require inventory service integration to count material usage
        For now, returns basic taxonomy stats
        """
        all_materials = self.hierarchy_service.get_all_materials(active_only=False)
        
        stats = {
            'total_entries': len(all_materials),
            'active_entries': len([m for m in all_materials if m.active]),
            'inactive_entries': len([m for m in all_materials if not m.active]),
            'categories': len([m for m in all_materials if m.level == 1]),
            'families': len([m for m in all_materials if m.level == 2]),
            'materials': len([m for m in all_materials if m.level == 3])
        }
        
        return stats