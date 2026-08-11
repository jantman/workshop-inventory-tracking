"""
Unit tests for the type/shape dimension requirement rules.

`app/taxonomy.py` is the single authoritative statement of which fields each
(Type, Shape) pair requires. The rules used to be restated in
`InventoryItem.validate()` and in `inventory-add.js`, and the three disagreed;
these tests pin the one table that replaced them.
"""

import pytest

from app.models import ItemShape, ItemType
from app.taxonomy import type_shape_validator


class TestRequiredDimensionsByShape:
    """Requirements vary by shape, not by type alone."""

    @pytest.mark.unit
    def test_round_plate_requires_diameter_and_thickness_only(self):
        """A round plate is a disc: diameter and thickness, no length."""
        required = type_shape_validator.get_required_dimensions(
            ItemType.PLATE, ItemShape.ROUND)

        assert set(required) == {'width', 'thickness'}
        assert 'length' not in required

    @pytest.mark.unit
    def test_round_sheet_requires_diameter_and_thickness_only(self):
        """A round sheet carries the identical rule to a round plate."""
        required = type_shape_validator.get_required_dimensions(
            ItemType.SHEET, ItemShape.ROUND)

        assert set(required) == {'width', 'thickness'}
        assert 'length' not in required

    @pytest.mark.unit
    @pytest.mark.parametrize('item_type,shape', [
        (ItemType.PLATE, ItemShape.RECTANGULAR),
        (ItemType.PLATE, ItemShape.SQUARE),
        (ItemType.SHEET, ItemShape.RECTANGULAR),
        (ItemType.SHEET, ItemShape.SQUARE),
    ])
    def test_flat_stock_that_is_not_round_still_requires_all_three(self, item_type, shape):
        """FR-010: rectangular and square plate and sheet are unchanged."""
        required = type_shape_validator.get_required_dimensions(item_type, shape)

        assert set(required) == {'length', 'width', 'thickness'}

    @pytest.mark.unit
    def test_threaded_rod_does_not_require_width(self):
        """The taxonomy used to claim width; the form has never asked for one.

        `test_add_threaded_rod_with_proper_validation` asserts Width is not
        required, and `test_field_autocomplete` seeds threaded rods through the
        JSON API with no width at all. Requiring it here would fail both at a
        distance.
        """
        required = type_shape_validator.get_required_dimensions(
            ItemType.THREADED_ROD, ItemShape.ROUND)

        assert set(required) == {'length', 'thread_series', 'thread_size'}
        assert 'width' not in required

    @pytest.mark.unit
    def test_round_bar_requires_length_and_width(self):
        """FR-009: round bar is unchanged, and the server agrees with the form."""
        required = type_shape_validator.get_required_dimensions(
            ItemType.BAR, ItemShape.ROUND)

        assert set(required) == {'length', 'width'}

    @pytest.mark.unit
    @pytest.mark.parametrize('shape', [ItemShape.RECTANGULAR, ItemShape.SQUARE])
    def test_channel_requires_nothing(self, shape):
        """Carried forward deliberately — the spec puts Channel's rule out of scope.

        Pinned so the gap stays a decision rather than becoming an accident.
        """
        assert type_shape_validator.get_required_dimensions(ItemType.CHANNEL, shape) == []

    @pytest.mark.unit
    def test_incompatible_combination_has_no_requirements(self):
        """A pair with no rule yields silence, not an error."""
        assert type_shape_validator.get_required_dimensions(
            ItemType.PLATE, ItemShape.HEX) == []


class TestValidateRequiredFields:
    """The reporting contract: every missing field, named as the operator sees it."""

    @pytest.mark.unit
    def test_round_plate_with_diameter_and_thickness_is_accepted(self):
        missing = type_shape_validator.get_missing_required_fields(
            ItemType.PLATE, ItemShape.ROUND,
            {'width': '6', 'thickness': '0.25'})

        assert missing == []

    @pytest.mark.unit
    def test_round_plate_without_length_is_accepted(self):
        """FR-001: length is not asked for, and its absence is not an error."""
        errors = type_shape_validator.validate_required_fields(
            ItemType.PLATE, ItemShape.ROUND,
            {'width': '6', 'thickness': '0.25', 'length': None})

        assert errors == []

    @pytest.mark.unit
    def test_both_missing_dimensions_are_reported(self):
        """FR-018: correcting one omission must not reveal the next."""
        missing = type_shape_validator.get_missing_required_fields(
            ItemType.PLATE, ItemShape.ROUND, {})

        assert missing == ['Diameter', 'Thickness']

    @pytest.mark.unit
    def test_round_shape_reports_width_as_diameter(self):
        missing = type_shape_validator.get_missing_required_fields(
            ItemType.PLATE, ItemShape.ROUND, {'thickness': '0.25'})

        assert missing == ['Diameter']

    @pytest.mark.unit
    def test_rectangular_shape_reports_width_as_width(self):
        missing = type_shape_validator.get_missing_required_fields(
            ItemType.PLATE, ItemShape.RECTANGULAR,
            {'length': '12', 'thickness': '0.25'})

        assert missing == ['Width']

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [None, '', '   '])
    def test_blank_counts_as_missing(self, value):
        """Clearing a field means the same thing as never filling it."""
        missing = type_shape_validator.get_missing_required_fields(
            ItemType.PLATE, ItemShape.ROUND,
            {'width': '6', 'thickness': value})

        assert missing == ['Thickness']

    @pytest.mark.unit
    def test_zero_is_present(self):
        """Positivity is the CheckConstraints' business, not this method's."""
        missing = type_shape_validator.get_missing_required_fields(
            ItemType.PLATE, ItemShape.ROUND,
            {'width': 0, 'thickness': 0})

        assert missing == []

    @pytest.mark.unit
    def test_messages_name_the_type_and_shape(self):
        errors = type_shape_validator.validate_required_fields(
            ItemType.PLATE, ItemShape.ROUND, {})

        assert errors == [
            'Diameter is required for Plate/Round',
            'Thickness is required for Plate/Round',
        ]

    @pytest.mark.unit
    def test_channel_yields_silence(self):
        assert type_shape_validator.validate_required_fields(
            ItemType.CHANNEL, ItemShape.RECTANGULAR, {}) == []

    @pytest.mark.unit
    def test_threaded_rod_thread_fields_are_reported_by_their_labels(self):
        missing = type_shape_validator.get_missing_required_fields(
            ItemType.THREADED_ROD, ItemShape.ROUND, {'length': '36'})

        assert missing == ['Thread Series', 'Thread Size']


class TestCompatibilityDerivedFromTheSameTable:
    """No method may answer from a stale second copy."""

    @pytest.mark.unit
    def test_compatible_shapes_are_the_shapes_with_a_rule(self):
        assert type_shape_validator.get_compatible_shapes(ItemType.PLATE) == [
            ItemShape.RECTANGULAR, ItemShape.SQUARE, ItemShape.ROUND]

    @pytest.mark.unit
    def test_channel_offers_only_the_shapes_it_is_recorded_as_taking(self):
        assert type_shape_validator.get_compatible_shapes(ItemType.CHANNEL) == [
            ItemShape.RECTANGULAR, ItemShape.SQUARE]

    @pytest.mark.unit
    def test_round_is_compatible_with_plate(self):
        assert type_shape_validator.is_shape_compatible_with_type(
            ItemType.PLATE, ItemShape.ROUND) is True

    @pytest.mark.unit
    def test_hex_is_not_compatible_with_plate(self):
        assert type_shape_validator.is_shape_compatible_with_type(
            ItemType.PLATE, ItemShape.HEX) is False

    @pytest.mark.unit
    def test_optional_dimensions_are_weight_throughout(self):
        assert type_shape_validator.get_optional_dimensions(
            ItemType.PLATE, ItemShape.ROUND) == ['weight']

    @pytest.mark.unit
    def test_validate_type_shape_combination_rejects_an_incompatible_pair(self):
        is_valid, errors = type_shape_validator.validate_type_shape_combination(
            ItemType.PLATE, ItemShape.HEX)

        assert is_valid is False
        assert any('not compatible' in error for error in errors)
