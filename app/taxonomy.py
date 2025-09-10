"""
Type-Shape Validation for Workshop Material Inventory Tracking

This module manages the validation of item type and shape combinations.
Material taxonomy is now handled by the MaterialHierarchyService.
"""

from typing import List, Tuple
from dataclasses import dataclass, field
from app.models import ItemType, ItemShape


@dataclass
class TypeShapeCompatibility:
    """Defines which shapes are valid for which item types"""
    item_type: ItemType
    compatible_shapes: List[ItemShape]
    required_dimensions: List[str]  # Which dimensions are required
    optional_dimensions: List[str] = field(default_factory=list)


class TypeShapeValidator:
    """Validates item type and shape combinations"""
    
    def __init__(self):
        self._type_shape_compatibility = []
        self._initialize_compatibility_rules()
    
    def _initialize_compatibility_rules(self):
        """Initialize type-shape compatibility rules"""
        
        compatibilities = [
            TypeShapeCompatibility(
                item_type=ItemType.BAR,
                compatible_shapes=[ItemShape.RECTANGULAR, ItemShape.ROUND, ItemShape.SQUARE, ItemShape.HEX],
                required_dimensions=['length'],
                optional_dimensions=['weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.PLATE,
                compatible_shapes=[ItemShape.RECTANGULAR, ItemShape.SQUARE, ItemShape.ROUND],
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
                item_type=ItemType.THREADED_ROD,
                compatible_shapes=[ItemShape.ROUND],
                required_dimensions=['length', 'width'],
                optional_dimensions=['weight']
            ),
            TypeShapeCompatibility(
                item_type=ItemType.ANGLE,
                compatible_shapes=[ItemShape.RECTANGULAR],
                required_dimensions=['length', 'width', 'thickness'],
                optional_dimensions=['weight']
            )
        ]
        
        self._type_shape_compatibility = compatibilities
    
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


# Global validator instance
type_shape_validator = TypeShapeValidator()