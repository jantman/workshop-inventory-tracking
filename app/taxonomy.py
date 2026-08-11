"""
Type-Shape Validation for Workshop Material Inventory Tracking

This module manages the validation of item type and shape combinations, and is
the single authoritative statement of which fields each combination requires.
Material taxonomy is now handled by the MaterialHierarchyService.
"""

from typing import Any, Dict, List, Mapping, Tuple
from dataclasses import dataclass, field
from app.models import ItemType, ItemShape


# How a field is named to the operator. `width` is the diameter of a round
# item, and is labelled that way on both forms.
FIELD_LABELS = {
    'length': 'Length',
    'width': 'Width',
    'thickness': 'Thickness',
    'wall_thickness': 'Wall Thickness',
    'thread_series': 'Thread Series',
    'thread_size': 'Thread Size',
}


def field_label(field_name: str, shape: ItemShape) -> str:
    """Name a field as the operator sees it on the form."""
    if field_name == 'width' and shape == ItemShape.ROUND:
        return 'Diameter'
    return FIELD_LABELS.get(field_name, field_name.replace('_', ' ').title())


@dataclass
class TypeShapeCompatibility:
    """Which shapes an item type may take, and what each of them requires.

    Requirements are keyed on shape as well as type: a round plate is a disc
    and needs no length, where a rectangular one does. A shape present with an
    empty requirement list is compatible with the type but requires nothing.
    """
    item_type: ItemType
    required_fields: Dict[ItemShape, List[str]]
    optional_dimensions: List[str] = field(default_factory=lambda: ['weight'])

    @property
    def compatible_shapes(self) -> List[ItemShape]:
        return list(self.required_fields.keys())


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
                required_fields={
                    ItemShape.RECTANGULAR: ['length', 'width', 'thickness'],
                    ItemShape.ROUND: ['length', 'width'],
                    ItemShape.SQUARE: ['length', 'width'],
                    ItemShape.HEX: ['length', 'width'],
                },
            ),
            TypeShapeCompatibility(
                item_type=ItemType.PLATE,
                required_fields={
                    ItemShape.RECTANGULAR: ['length', 'width', 'thickness'],
                    ItemShape.SQUARE: ['length', 'width', 'thickness'],
                    # A disc: how far across, and how thick.
                    ItemShape.ROUND: ['width', 'thickness'],
                },
            ),
            TypeShapeCompatibility(
                item_type=ItemType.SHEET,
                required_fields={
                    ItemShape.RECTANGULAR: ['length', 'width', 'thickness'],
                    ItemShape.SQUARE: ['length', 'width', 'thickness'],
                    ItemShape.ROUND: ['width', 'thickness'],
                },
            ),
            TypeShapeCompatibility(
                item_type=ItemType.TUBE,
                required_fields={
                    ItemShape.ROUND: ['length', 'width', 'wall_thickness'],
                    ItemShape.SQUARE: ['length', 'width', 'wall_thickness'],
                    ItemShape.RECTANGULAR: ['length', 'width', 'wall_thickness'],
                },
            ),
            TypeShapeCompatibility(
                item_type=ItemType.THREADED_ROD,
                # No width: a threaded rod is described by its thread, and the
                # form has never asked for one.
                required_fields={
                    ItemShape.ROUND: ['length', 'thread_series', 'thread_size'],
                },
            ),
            TypeShapeCompatibility(
                item_type=ItemType.ANGLE,
                required_fields={
                    ItemShape.RECTANGULAR: ['length', 'width', 'thickness'],
                },
            ),
            TypeShapeCompatibility(
                item_type=ItemType.CHANNEL,
                # Channel has never had a rule; carried forward unchanged
                # rather than invented here (spec, Out of Scope).
                required_fields={
                    ItemShape.RECTANGULAR: [],
                    ItemShape.SQUARE: [],
                },
            ),
        ]

        self._type_shape_compatibility = compatibilities

    def _compatibility_for(self, item_type: ItemType):
        """The rules for an item type, or None if it has none."""
        for compatibility in self._type_shape_compatibility:
            if compatibility.item_type == item_type:
                return compatibility
        return None

    def is_shape_compatible_with_type(self, item_type: ItemType, shape: ItemShape) -> bool:
        """Check if a shape is compatible with an item type"""
        compatibility = self._compatibility_for(item_type)
        return bool(compatibility) and shape in compatibility.required_fields

    def get_compatible_shapes(self, item_type: ItemType) -> List[ItemShape]:
        """Get list of shapes compatible with an item type"""
        compatibility = self._compatibility_for(item_type)
        return compatibility.compatible_shapes if compatibility else []

    def get_required_dimensions(self, item_type: ItemType, shape: ItemShape) -> List[str]:
        """Get required fields for a type/shape combination"""
        compatibility = self._compatibility_for(item_type)
        if not compatibility:
            return []
        return list(compatibility.required_fields.get(shape, []))

    def get_optional_dimensions(self, item_type: ItemType, shape: ItemShape) -> List[str]:
        """Get optional dimensions for a type/shape combination"""
        if not self.is_shape_compatible_with_type(item_type, shape):
            return []

        compatibility = self._compatibility_for(item_type)
        return compatibility.optional_dimensions.copy()

    def get_missing_required_fields(
        self,
        item_type: ItemType,
        shape: ItemShape,
        values: Mapping[str, Any],
    ) -> List[str]:
        """Name every required field missing from `values`, as the operator sees it.

        A key that is absent, None, or an empty/whitespace string counts as
        missing; they mean the same thing on a form and in a payload. An empty
        list means the item satisfies the rules for its type and shape.
        """
        missing = []
        for field_name in self.get_required_dimensions(item_type, shape):
            value = values.get(field_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field_label(field_name, shape))
        return missing

    def validate_required_fields(
        self,
        item_type: ItemType,
        shape: ItemShape,
        values: Mapping[str, Any],
    ) -> List[str]:
        """Return a human-readable message for every required field missing from `values`.

        Empty list means the item satisfies the rules for its type and shape.
        """
        type_and_shape = f"{item_type.value}/{shape.value}" if shape else item_type.value
        return [
            f"{name} is required for {type_and_shape}"
            for name in self.get_missing_required_fields(item_type, shape, values)
        ]

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

    def requirements_by_name(self) -> Dict[str, Dict[str, List[str]]]:
        """The whole table keyed by the type and shape names the forms use.

        Rendered into the Add and Edit pages so the browser applies the same
        rules the server enforces, without restating them.
        """
        return {
            compatibility.item_type.value: {
                shape.value: list(fields)
                for shape, fields in compatibility.required_fields.items()
            }
            for compatibility in self._type_shape_compatibility
        }


# Global validator instance
type_shape_validator = TypeShapeValidator()
