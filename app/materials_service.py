"""
Material Hierarchy Service

Provides access to the hierarchical material taxonomy stored in the Materials sheet.
Supports browsing by category/family/material levels and search functionality.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from .google_sheets_storage import GoogleSheetsStorage


def _parse_bool(value: Any) -> bool:
    """Parse boolean value from storage data, handling string representations."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on')
    if isinstance(value, (int, float)):
        return bool(value)
    return bool(value)


@dataclass
class MaterialTaxonomy:
    """Represents a single entry in the materials taxonomy."""
    name: str
    level: int  # 1=Category, 2=Family, 3=Material
    parent: str
    aliases: List[str]
    active: bool
    sort_order: int
    notes: str
    
    @classmethod
    def from_row(cls, row: List[Any]) -> 'MaterialTaxonomy':
        """Create MaterialTaxonomy from a sheet row."""
        return cls(
            name=str(row[0]) if row[0] else '',
            level=int(row[1]) if row[1] else 1,
            parent=str(row[2]) if row[2] else '',
            aliases=[alias.strip() for alias in str(row[3]).split(',') if alias.strip()] if row[3] else [],
            active=_parse_bool(row[4]) if len(row) > 4 else True,
            sort_order=int(row[5]) if len(row) > 5 and row[5] else 0,
            notes=str(row[7]) if len(row) > 7 and row[7] else ''
        )


class MaterialHierarchyService:
    """Service for accessing hierarchical material taxonomy."""
    
    def __init__(self, storage: GoogleSheetsStorage):
        self.storage = storage
        self._taxonomy_cache: Optional[List[MaterialTaxonomy]] = None
        self._name_to_taxonomy: Optional[Dict[str, MaterialTaxonomy]] = None
    
    def _load_taxonomy(self) -> List[MaterialTaxonomy]:
        """Load taxonomy data from Materials sheet."""
        if self._taxonomy_cache is not None:
            return self._taxonomy_cache
        
        # Read all data from Materials sheet
        result = self.storage.read_all('Materials')
        
        if not result.success or not result.data:
            return []
        
        # Skip header row and convert to MaterialTaxonomy objects
        taxonomy_data = []
        for row in result.data[1:]:  # Skip header row
            if row and len(row) >= 3:  # Ensure minimum required fields
                try:
                    taxonomy_data.append(MaterialTaxonomy.from_row(row))
                except (ValueError, IndexError) as e:
                    # Skip malformed rows
                    continue
        
        self._taxonomy_cache = taxonomy_data
        
        # Build name lookup cache
        self._name_to_taxonomy = {item.name: item for item in taxonomy_data}
        for item in taxonomy_data:
            for alias in item.aliases:
                if alias not in self._name_to_taxonomy:
                    self._name_to_taxonomy[alias] = item
        
        return taxonomy_data
    
    def get_all_materials(self, active_only: bool = True) -> List[MaterialTaxonomy]:
        """Get all materials in the taxonomy."""
        taxonomy = self._load_taxonomy()
        
        if active_only:
            return [item for item in taxonomy if item.active]
        return taxonomy
    
    def get_by_level(self, level: int, active_only: bool = True) -> List[MaterialTaxonomy]:
        """Get all materials at a specific hierarchy level."""
        taxonomy = self._load_taxonomy()
        
        items = [item for item in taxonomy if item.level == level]
        if active_only:
            items = [item for item in items if item.active]
        
        # Sort by sort_order, then by name
        return sorted(items, key=lambda x: (x.sort_order, x.name.lower()))
    
    def get_categories(self, active_only: bool = True) -> List[MaterialTaxonomy]:
        """Get all categories (level 1)."""
        return self.get_by_level(1, active_only)
    
    def get_families(self, active_only: bool = True) -> List[MaterialTaxonomy]:
        """Get all families (level 2)."""
        return self.get_by_level(2, active_only)
    
    def get_materials(self, active_only: bool = True) -> List[MaterialTaxonomy]:
        """Get all materials (level 3)."""
        return self.get_by_level(3, active_only)
    
    def get_children(self, parent_name: str, active_only: bool = True) -> List[MaterialTaxonomy]:
        """Get all children of a given parent material."""
        taxonomy = self._load_taxonomy()
        
        children = [item for item in taxonomy if item.parent == parent_name]
        if active_only:
            children = [item for item in children if item.active]
        
        # Sort by sort_order, then by name
        return sorted(children, key=lambda x: (x.sort_order, x.name.lower()))
    
    def get_by_name(self, name: str) -> Optional[MaterialTaxonomy]:
        """Get material by exact name or alias."""
        taxonomy = self._load_taxonomy()
        
        if not self._name_to_taxonomy:
            return None
        
        return self._name_to_taxonomy.get(name)
    
    def search(self, query: str, active_only: bool = True, max_results: int = 20) -> List[MaterialTaxonomy]:
        """
        Search materials by name, aliases, or notes.
        Returns results ranked by relevance.
        """
        taxonomy = self._load_taxonomy()
        
        if not query.strip():
            return []
        
        query_lower = query.lower().strip()
        results = []
        
        for item in taxonomy:
            if active_only and not item.active:
                continue
            
            # Calculate relevance score
            score = 0
            
            # Exact name match gets highest score
            if item.name.lower() == query_lower:
                score = 100
            # Name starts with query
            elif item.name.lower().startswith(query_lower):
                score = 90
            # Name contains query
            elif query_lower in item.name.lower():
                score = 70
            # Alias exact match
            elif any(alias.lower() == query_lower for alias in item.aliases):
                score = 85
            # Alias starts with query
            elif any(alias.lower().startswith(query_lower) for alias in item.aliases):
                score = 75
            # Alias contains query
            elif any(query_lower in alias.lower() for alias in item.aliases):
                score = 60
            # Notes contain query
            elif query_lower in item.notes.lower():
                score = 30
            
            if score > 0:
                results.append((score, item))
        
        # Sort by score (descending), then by level (ascending), then by name
        results.sort(key=lambda x: (-x[0], x[1].level, x[1].name.lower()))
        
        return [item for score, item in results[:max_results]]
    
    def get_suggestions(self, query: str = '', level: Optional[int] = None, parent: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get material suggestions for autocomplete.
        
        Args:
            query: Search query (optional)
            level: Filter by hierarchy level (optional)
            parent: Filter by parent name (optional)  
            limit: Maximum results to return
            
        Returns:
            List of suggestion dictionaries with name, level, parent, and notes
        """
        if query:
            # Search-based suggestions
            results = self.search(query, active_only=True, max_results=limit)
        elif parent:
            # Get children of specific parent
            results = self.get_children(parent, active_only=True)[:limit]
        elif level:
            # Get items at specific level
            results = self.get_by_level(level, active_only=True)[:limit]
        else:
            # Get all materials, prioritize categories
            categories = self.get_categories(active_only=True)[:limit//2]
            materials = self.get_materials(active_only=True)[:limit-len(categories)]
            results = categories + materials
        
        return [
            {
                'name': item.name,
                'level': item.level,
                'parent': item.parent,
                'notes': item.notes,
                'aliases': item.aliases
            }
            for item in results
        ]
    
    def get_hierarchy_path(self, name: str) -> List[MaterialTaxonomy]:
        """Get the full hierarchy path for a material (e.g., Category -> Family -> Material)."""
        item = self.get_by_name(name)
        if not item:
            return []
        
        path = [item]
        current = item
        
        # Walk up the hierarchy
        while current.parent:
            current = self.get_by_name(current.parent)
            if current:
                path.insert(0, current)
            else:
                break
        
        return path
    
    def validate_material(self, name: str) -> bool:
        """Check if a material name is valid in the taxonomy."""
        return self.get_by_name(name) is not None
    
    def refresh_cache(self):
        """Clear the taxonomy cache to force reload from sheet."""
        self._taxonomy_cache = None
        self._name_to_taxonomy = None