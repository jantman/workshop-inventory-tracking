"""
Taxonomy Management for Workshop Material Inventory Tracking

This module manages the taxonomy of materials, types, shapes, and their relationships.
It provides normalization, validation, and extensibility for the inventory system.
"""

from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import re
import json
from flask import current_app

from app.models import ItemType, ItemShape, ThreadSeries

@dataclass
class MaterialInfo:
    """Information about a material type"""
    name: str
    aliases: List[str] = field(default_factory=list)
    category: Optional[str] = None
    density: Optional[float] = None  # kg/m³
    properties: Dict[str, Any] = field(default_factory=dict)
    common_forms: List[str] = field(default_factory=list)

@dataclass
class TypeShapeCompatibility:
    """Defines which shapes are valid for which item types"""
    item_type: ItemType
    compatible_shapes: List[ItemShape]
    required_dimensions: List[str]  # Which dimensions are required
    optional_dimensions: List[str] = field(default_factory=list)

class TaxonomyManager:
    """Manages the taxonomy of materials, types, shapes, and their relationships"""
    
    def __init__(self):
        self._materials = {}
        self._aliases = {}
        self._type_shape_compatibility = []
        self._custom_materials = set()
        self._initialize_default_taxonomy()
    
    def _initialize_default_taxonomy(self):
        """Initialize with default taxonomy data"""
        
        # Material definitions
        materials = [
            MaterialInfo(
                name="4140 Pre-Hard",
                aliases=["4140", "4140 Pre-hardened", "4140 PHB"],
                category="Alloy Steel",
                density=7850,
                properties={"hardness": "28-32 HRC", "yield_strength": "795 MPa"},
                common_forms=["Bar", "Plate", "Sheet"]
            ),
            MaterialInfo(
                name="304/304L Stainless",
                aliases=["304", "304L", "304 / 304L", "304 Stainless", "SS304"],
                category="Stainless Steel",
                density=8000,
                properties={"corrosion_resistance": "excellent", "magnetic": False},
                common_forms=["Bar", "Plate", "Sheet", "Tube", "Pipe"]
            ),
            MaterialInfo(
                name="316/316L Stainless",
                aliases=["316", "316L", "316 / 316L", "316 Stainless", "SS316"],
                category="Stainless Steel",
                density=8000,
                properties={"corrosion_resistance": "superior", "magnetic": False},
                common_forms=["Bar", "Plate", "Sheet", "Tube", "Pipe"]
            ),
            MaterialInfo(
                name="Aluminum 6061",
                aliases=["6061", "6061-T6", "Al 6061", "Aluminum 6061-T6"],
                category="Aluminum",
                density=2700,
                properties={"corrosion_resistance": "good", "weldability": "excellent"},
                common_forms=["Bar", "Plate", "Sheet", "Angle", "Channel"]
            ),
            MaterialInfo(
                name="Aluminum 7075",
                aliases=["7075", "7075-T6", "Al 7075", "Aluminum 7075-T6"],
                category="Aluminum",
                density=2810,
                properties={"strength": "high", "machinability": "good"},
                common_forms=["Bar", "Plate", "Sheet"]
            ),
            MaterialInfo(
                name="Brass",
                aliases=["Brass 360", "Free Machining Brass", "C360"],
                category="Brass",
                density=8500,
                properties={"machinability": "excellent", "corrosion_resistance": "good"},
                common_forms=["Bar", "Plate", "Sheet", "Tube"]
            ),
            MaterialInfo(
                name="Copper",
                aliases=["C101", "C110", "Pure Copper", "ETP Copper"],
                category="Copper",
                density=8960,
                properties={"conductivity": "excellent", "corrosion_resistance": "excellent"},
                common_forms=["Bar", "Plate", "Sheet", "Tube", "Wire"]
            ),
            MaterialInfo(
                name="Carbon Steel",
                aliases=["A36", "1018", "1020", "Cold Roll", "Hot Roll", "CRS", "HRS"],
                category="Carbon Steel",
                density=7850,
                properties={"weldability": "excellent", "machinability": "good"},
                common_forms=["Bar", "Plate", "Sheet", "Angle", "Channel", "Beam"]
            ),
            MaterialInfo(
                name="Tool Steel",
                aliases=["O1", "A2", "D2", "S7", "Tool Steel"],
                category="Tool Steel",
                density=7800,
                properties={"hardness": "high", "wear_resistance": "excellent"},
                common_forms=["Bar", "Plate"]
            ),
            MaterialInfo(
                name="Unknown",
                aliases=["Mystery", "Unidentified", "TBD", "N/A", ""],
                category="Unknown",
                common_forms=[]
            )
        ]
        
        # Register materials
        for material in materials:
            self.register_material(material)
        
        # Type-Shape compatibility definitions
        compatibilities = [
            TypeShapeCompatibility(
                item_type=ItemType.BAR,
                compatible_shapes=[ItemShape.RECTANGULAR, ItemShape.ROUND, ItemShape.SQUARE, ItemShape.HEXAGONAL],
                required_dimensions=['length'],
                optional_dimensions=['weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.PLATE,
                compatible_shapes=[ItemShape.RECTANGULAR, ItemShape.SQUARE, ItemShape.ROUND, ItemShape.IRREGULAR],
                required_dimensions=['length', 'width', 'thickness'],
                optional_dimensions=['weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.SHEET,
                compatible_shapes=[ItemShape.RECTANGULAR, ItemShape.SQUARE, ItemShape.ROUND],
                required_dimensions=['length', 'width', 'thickness'],
                optional_dimensions=['weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.TUBE,
                compatible_shapes=[ItemShape.ROUND, ItemShape.SQUARE, ItemShape.RECTANGULAR],
                required_dimensions=['length', 'width', 'wall_thickness'],
                optional_dimensions=['weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.PIPE,
                compatible_shapes=[ItemShape.ROUND],
                required_dimensions=['length', 'width', 'wall_thickness'],
                optional_dimensions=['weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.ROD,
                compatible_shapes=[ItemShape.ROUND],
                required_dimensions=['length', 'width'],
                optional_dimensions=['weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.ANGLE,
                compatible_shapes=[ItemShape.L_SHAPED],
                required_dimensions=['length', 'width', 'thickness'],
                optional_dimensions=['weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.CHANNEL,
                compatible_shapes=[ItemShape.C_CHANNEL, ItemShape.U_SHAPED],
                required_dimensions=['length', 'width', 'thickness'],
                optional_dimensions=['weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.BEAM,
                compatible_shapes=[ItemShape.I_BEAM],
                required_dimensions=['length', 'width', 'thickness'],
                optional_dimensions=['weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.WIRE,
                compatible_shapes=[ItemShape.ROUND],
                required_dimensions=['length', 'width'],
                optional_dimensions=['weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.FASTENER,
                compatible_shapes=[ItemShape.ROUND, ItemShape.HEXAGONAL],
                required_dimensions=['width'],  # diameter or hex size
                optional_dimensions=['length', 'weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.OTHER,
                compatible_shapes=list(ItemShape),  # All shapes allowed
                required_dimensions=[],  # No required dimensions
                optional_dimensions=['length', 'width', 'thickness', 'wall_thickness', 'weight']
            )
        ]
        
        self._type_shape_compatibility = compatibilities
    
    def register_material(self, material: MaterialInfo):
        """Register a new material in the taxonomy"""
        self._materials[material.name] = material
        
        # Register aliases
        for alias in material.aliases:
            if alias:  # Skip empty aliases
                self._aliases[alias.lower()] = material.name
    
    def normalize_material(self, material: str) -> Tuple[str, bool]:
        """
        Normalize a material name using aliases
        Returns (normalized_name, is_custom)
        """
        if not material or not material.strip():
            return "Unknown", False
        
        material = material.strip()
        
        # Check exact match first
        if material in self._materials:
            return material, material in self._custom_materials
        
        # Check aliases (case-insensitive)
        alias_key = material.lower()
        if alias_key in self._aliases:
            normalized = self._aliases[alias_key]
            return normalized, normalized in self._custom_materials
        
        # Not found - could be a new material
        current_app.logger.info(f"Unknown material: {material}")
        return material, True
    
    def get_material_info(self, material: str) -> Optional[MaterialInfo]:
        """Get information about a material"""
        normalized, _ = self.normalize_material(material)
        return self._materials.get(normalized)
    
    def add_custom_material(self, name: str, aliases: List[str] = None, 
                          category: str = None, properties: Dict[str, Any] = None) -> bool:
        """Add a custom material to the taxonomy"""
        if not name or name in self._materials:
            return False
        
        material = MaterialInfo(
            name=name,
            aliases=aliases or [],
            category=category,
            properties=properties or {}
        )
        
        self.register_material(material)
        self._custom_materials.add(name)
        return True
    
    def get_all_materials(self) -> List[str]:
        """Get list of all known materials"""
        return list(self._materials.keys())
    
    def get_materials_by_category(self, category: str) -> List[str]:
        """Get materials in a specific category"""
        return [name for name, info in self._materials.items() 
                if info.category == category]
    
    def get_material_categories(self) -> List[str]:
        """Get list of all material categories"""
        categories = set()
        for info in self._materials.values():
            if info.category:
                categories.add(info.category)
        return sorted(list(categories))
    
    def is_shape_compatible_with_type(self, item_type: ItemType, shape: ItemShape) -> bool:
        """Check if a shape is compatible with an item type"""
        for compatibility in self._type_shape_compatibility:
            if compatibility.item_type == item_type:
                return shape in compatibility.compatible_shapes
        return False
    
    def get_compatible_shapes(self, item_type: ItemType) -> List[ItemShape]:
        """Get list of shapes compatible with an item type"""
        for compatibility in self._type_shape_compatibility:
            if compatibility.item_type == item_type:
                return compatibility.compatible_shapes.copy()
        return []
    
    def get_required_dimensions(self, item_type: ItemType, shape: ItemShape) -> List[str]:
        """Get required dimensions for a type/shape combination"""
        if not self.is_shape_compatible_with_type(item_type, shape):
            return []
        
        for compatibility in self._type_shape_compatibility:
            if compatibility.item_type == item_type:
                return compatibility.required_dimensions.copy()
        return []
    
    def get_optional_dimensions(self, item_type: ItemType, shape: ItemShape) -> List[str]:
        """Get optional dimensions for a type/shape combination"""
        if not self.is_shape_compatible_with_type(item_type, shape):
            return []
        
        for compatibility in self._type_shape_compatibility:
            if compatibility.item_type == item_type:
                return compatibility.optional_dimensions.copy()
        return []
    
    def validate_type_shape_combination(self, item_type: ItemType, shape: ItemShape) -> Tuple[bool, List[str]]:
        """
        Validate a type/shape combination
        Returns (is_valid, error_messages)
        """
        errors = []
        
        if not self.is_shape_compatible_with_type(item_type, shape):
            errors.append(f"Shape '{shape.value}' is not compatible with type '{item_type.value}'")
            compatible = self.get_compatible_shapes(item_type)
            if compatible:
                compatible_names = [s.value for s in compatible]
                errors.append(f"Compatible shapes: {', '.join(compatible_names)}")
        
        return len(errors) == 0, errors
    
    def suggest_material_matches(self, partial: str, limit: int = 5) -> List[Tuple[str, float]]:
        """
        Suggest material matches for partial input
        Returns list of (material_name, confidence_score) tuples
        """
        if not partial:
            return []
        
        partial = partial.lower().strip()
        suggestions = []
        
        # Check exact prefix matches
        for material in self._materials.keys():
            if material.lower().startswith(partial):
                suggestions.append((material, 1.0))
        
        # Check alias matches
        for alias, material in self._aliases.items():
            if alias.startswith(partial):
                suggestions.append((material, 0.9))
        
        # Check substring matches
        for material in self._materials.keys():
            if partial in material.lower():
                suggestions.append((material, 0.7))
        
        # Remove duplicates and sort by confidence
        seen = set()
        unique_suggestions = []
        for material, confidence in sorted(suggestions, key=lambda x: x[1], reverse=True):
            if material not in seen:
                seen.add(material)
                unique_suggestions.append((material, confidence))
        
        return unique_suggestions[:limit]
    
    def get_taxonomy_stats(self) -> Dict[str, Any]:
        """Get statistics about the taxonomy"""
        return {
            'total_materials': len(self._materials),
            'custom_materials': len(self._custom_materials),
            'total_aliases': len(self._aliases),
            'categories': len(self.get_material_categories()),
            'type_shape_combinations': len(self._type_shape_compatibility),
            'materials_by_category': {
                category: len(self.get_materials_by_category(category))
                for category in self.get_material_categories()
            }
        }
    
    def export_taxonomy(self) -> Dict[str, Any]:
        """Export taxonomy data for backup/transfer"""
        return {
            'materials': {
                name: {
                    'aliases': info.aliases,
                    'category': info.category,
                    'density': info.density,
                    'properties': info.properties,
                    'common_forms': info.common_forms,
                    'is_custom': name in self._custom_materials
                }
                for name, info in self._materials.items()
            },
            'type_shape_compatibility': [
                {
                    'item_type': comp.item_type.value,
                    'compatible_shapes': [s.value for s in comp.compatible_shapes],
                    'required_dimensions': comp.required_dimensions,
                    'optional_dimensions': comp.optional_dimensions
                }
                for comp in self._type_shape_compatibility
            ]
        }
    
    def import_taxonomy(self, data: Dict[str, Any]) -> bool:
        """Import taxonomy data from backup/transfer"""
        try:
            # Clear existing custom materials
            self._custom_materials.clear()
            
            # Import materials
            for name, info in data.get('materials', {}).items():
                material = MaterialInfo(
                    name=name,
                    aliases=info.get('aliases', []),
                    category=info.get('category'),
                    density=info.get('density'),
                    properties=info.get('properties', {}),
                    common_forms=info.get('common_forms', [])
                )
                self.register_material(material)
                
                if info.get('is_custom', False):
                    self._custom_materials.add(name)
            
            # Import type-shape compatibility (if provided)
            if 'type_shape_compatibility' in data:
                compatibilities = []
                for comp_data in data['type_shape_compatibility']:
                    compatibility = TypeShapeCompatibility(
                        item_type=ItemType(comp_data['item_type']),
                        compatible_shapes=[ItemShape(s) for s in comp_data['compatible_shapes']],
                        required_dimensions=comp_data['required_dimensions'],
                        optional_dimensions=comp_data.get('optional_dimensions', [])
                    )
                    compatibilities.append(compatibility)
                self._type_shape_compatibility = compatibilities
            
            return True
            
        except Exception as e:
            current_app.logger.error(f"Failed to import taxonomy: {e}")
            return False

# Global taxonomy manager instance
taxonomy_manager = TaxonomyManager()