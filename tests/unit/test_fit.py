"""
Unit Tests for the Stock Fit Geometry

Enumerates `specs/027-stock-fit-search/contracts/fit-rules.md`: the envelope
table of section 1, the four fit rules of section 3, the ordering of section 4
and the tolerance evaluation of section 5.

`app/utils/fit.py` is pure, so everything here runs without a fixture, a session
or a Flask app.
"""

from decimal import Decimal

import pytest

from app.database import InventoryItem
from app.models import ItemShape, ItemType
from app.taxonomy import type_shape_validator
from app.utils.fit import (
    Box,
    Cylinder,
    RequestedPiece,
    SkipReason,
    envelope_for,
    evaluate,
    sort_key,
)


def D(value) -> Decimal:
    """A Decimal, spelled short because this file is nothing but Decimals."""
    return Decimal(str(value))


def item(item_type: ItemType, shape: ItemShape, length=None, width=None,
         thickness=None, wall_thickness=None) -> InventoryItem:
    """An unsaved inventory row.

    Built rather than mocked so the test goes through the same `item_type_enum`
    and `shape_enum` properties production does. Nothing is persisted; no
    session is involved.
    """
    return InventoryItem(
        ja_id='JA000001',
        item_type=item_type.value,
        shape=shape.value,
        material='Steel',
        length=None if length is None else D(length),
        width=None if width is None else D(width),
        thickness=None if thickness is None else D(thickness),
        wall_thickness=None if wall_thickness is None else D(wall_thickness),
    )


class TestEnvelopeTable:
    """Every row of the envelope table in fit-rules section 1."""

    def test_bar_rectangular_is_a_box_of_its_three_dimensions(self):
        """E5."""
        assert envelope_for(
            item(ItemType.BAR, ItemShape.RECTANGULAR, length=12, width=3, thickness=0.5)
        ) == Box(D(12), D(3), D('0.5'))

    def test_bar_round_is_a_cylinder_of_width_by_length(self):
        """E3 -- `width` is the diameter of a round item."""
        assert envelope_for(
            item(ItemType.BAR, ItemShape.ROUND, length=12, width=2)
        ) == Cylinder(D(2), D(12))

    def test_bar_square_is_a_prism_whose_cross_section_is_square(self):
        """E4 -- Bar/Square requires only length and width."""
        assert envelope_for(
            item(ItemType.BAR, ItemShape.SQUARE, length=12, width=3)
        ) == Box(D(12), D(3), D(3))

    def test_bar_hex_is_the_cylinder_inscribed_in_its_flats(self):
        """E3 -- the across-flats measurement is the diameter, conservatively."""
        assert envelope_for(
            item(ItemType.BAR, ItemShape.HEX, length=12, width=1)
        ) == Cylinder(D(1), D(12))

    def test_plate_rectangular_is_a_box(self):
        """E5."""
        assert envelope_for(
            item(ItemType.PLATE, ItemShape.RECTANGULAR, length=12, width=6, thickness=0.25)
        ) == Box(D(12), D(6), D('0.25'))

    def test_plate_square_is_a_box_and_not_a_prism(self):
        """E5, not E4: a square plate records a thickness, so E4 does not fire."""
        assert envelope_for(
            item(ItemType.PLATE, ItemShape.SQUARE, length=6, width=6, thickness=0.25)
        ) == Box(D(6), D(6), D('0.25'))

    def test_plate_round_is_a_disc_of_width_by_thickness(self):
        """E2."""
        assert envelope_for(
            item(ItemType.PLATE, ItemShape.ROUND, width=6, thickness=0.25)
        ) == Cylinder(D(6), D('0.25'))

    def test_sheet_rectangular_is_a_box(self):
        """E5."""
        assert envelope_for(
            item(ItemType.SHEET, ItemShape.RECTANGULAR, length=48, width=24, thickness=0.0625)
        ) == Box(D(48), D(24), D('0.0625'))

    def test_sheet_square_is_a_box(self):
        """E5."""
        assert envelope_for(
            item(ItemType.SHEET, ItemShape.SQUARE, length=24, width=24, thickness=0.0625)
        ) == Box(D(24), D(24), D('0.0625'))

    def test_sheet_round_is_a_disc(self):
        """E2."""
        assert envelope_for(
            item(ItemType.SHEET, ItemShape.ROUND, width=12, thickness=0.0625)
        ) == Cylinder(D(12), D('0.0625'))

    @pytest.mark.parametrize('shape', [
        ItemShape.ROUND, ItemShape.SQUARE, ItemShape.RECTANGULAR,
    ])
    def test_a_tube_of_any_shape_is_hollow(self, shape):
        """E1 -- the outside dimensions describe a shell, not a solid."""
        assert envelope_for(
            item(ItemType.TUBE, shape, length=12, width=3, wall_thickness=0.065)
        ) == SkipReason.HOLLOW

    def test_threaded_rod_with_a_width_is_a_cylinder(self):
        """E3 -- you can turn a part from a threaded rod, if its size is recorded."""
        assert envelope_for(
            item(ItemType.THREADED_ROD, ItemShape.ROUND, length=36, width=0.25)
        ) == Cylinder(D('0.25'), D(36))

    def test_threaded_rod_without_a_width_is_incomplete(self):
        """E6 -- the field-driven rule is the whole rule; no type-specific case."""
        assert envelope_for(
            item(ItemType.THREADED_ROD, ItemShape.ROUND, length=36)
        ) == SkipReason.INCOMPLETE

    def test_angle_is_one_leg_of_the_l(self):
        """E5 -- the material genuinely there as a solid strip."""
        assert envelope_for(
            item(ItemType.ANGLE, ItemShape.RECTANGULAR, length=36, width=2, thickness=0.25)
        ) == Box(D(36), D(2), D('0.25'))

    def test_channel_with_all_three_recorded_is_a_box(self):
        """E5 -- channel's taxonomy entry requires nothing, so this is optional."""
        assert envelope_for(
            item(ItemType.CHANNEL, ItemShape.RECTANGULAR, length=36, width=3, thickness=0.25)
        ) == Box(D(36), D(3), D('0.25'))

    def test_channel_recording_nothing_is_incomplete(self):
        """E6 -- most channel rows fall here."""
        assert envelope_for(
            item(ItemType.CHANNEL, ItemShape.RECTANGULAR)
        ) == SkipReason.INCOMPLETE

    def test_a_round_plate_carrying_a_stale_length_is_still_a_disc(self):
        """E2 must precede E3, or this row becomes a bar that is not there."""
        assert envelope_for(
            item(ItemType.PLATE, ItemShape.ROUND, length=99, width=6, thickness=0.25)
        ) == Cylinder(D(6), D('0.25'))

    def test_hollow_wins_over_every_other_rule(self):
        """E1 is applied first, so a wall thickness excludes the row outright."""
        assert envelope_for(
            item(ItemType.BAR, ItemShape.RECTANGULAR,
                 length=12, width=3, thickness=0.5, wall_thickness=0.065)
        ) == SkipReason.HOLLOW


class TestEnvelopeIncompleteness:
    """Rule E6, once for each of the rules that can reach it."""

    def test_e2_without_a_thickness_is_incomplete(self):
        assert envelope_for(
            item(ItemType.PLATE, ItemShape.ROUND, width=6)
        ) == SkipReason.INCOMPLETE

    def test_e3_without_a_length_is_incomplete(self):
        assert envelope_for(
            item(ItemType.BAR, ItemShape.ROUND, width=2)
        ) == SkipReason.INCOMPLETE

    def test_e4_without_a_width_is_incomplete(self):
        assert envelope_for(
            item(ItemType.BAR, ItemShape.SQUARE, length=12)
        ) == SkipReason.INCOMPLETE

    def test_e5_without_a_thickness_is_incomplete(self):
        assert envelope_for(
            item(ItemType.BAR, ItemShape.RECTANGULAR, length=12, width=3)
        ) == SkipReason.INCOMPLETE


# What `envelope_for` must make of a row carrying exactly the dimension fields
# taxonomy requires for the combination, and nothing else. `Box` and `Cylinder`
# mean "an envelope of that kind"; a `SkipReason` means the combination is
# declared non-evaluable rather than silently unhandled.
#
# This table is the other half of D3: two (type, shape) tables are kept in
# agreement by a test rather than by being merged, because they answer different
# questions. Adding an ItemType or changing a requirement in `app/taxonomy.py`
# without teaching `app/utils/fit.py` about it fails here.
ENVELOPE_AGREEMENT = {
    (ItemType.BAR, ItemShape.RECTANGULAR): Box,
    (ItemType.BAR, ItemShape.ROUND): Cylinder,
    (ItemType.BAR, ItemShape.SQUARE): Box,
    (ItemType.BAR, ItemShape.HEX): Cylinder,
    (ItemType.PLATE, ItemShape.RECTANGULAR): Box,
    (ItemType.PLATE, ItemShape.SQUARE): Box,
    (ItemType.PLATE, ItemShape.ROUND): Cylinder,
    (ItemType.SHEET, ItemShape.RECTANGULAR): Box,
    (ItemType.SHEET, ItemShape.SQUARE): Box,
    (ItemType.SHEET, ItemShape.ROUND): Cylinder,
    (ItemType.TUBE, ItemShape.ROUND): SkipReason.HOLLOW,
    (ItemType.TUBE, ItemShape.SQUARE): SkipReason.HOLLOW,
    (ItemType.TUBE, ItemShape.RECTANGULAR): SkipReason.HOLLOW,
    # No width is required of a threaded rod, so a row recording only what
    # taxonomy asks for cannot be measured for fit.
    (ItemType.THREADED_ROD, ItemShape.ROUND): SkipReason.INCOMPLETE,
    (ItemType.ANGLE, ItemShape.RECTANGULAR): Box,
    # Channel requires no fields at all.
    (ItemType.CHANNEL, ItemShape.RECTANGULAR): SkipReason.INCOMPLETE,
    (ItemType.CHANNEL, ItemShape.SQUARE): SkipReason.INCOMPLETE,
}

DIMENSION_FIELDS = ('length', 'width', 'thickness', 'wall_thickness')

# Distinct values, so a rule reading the wrong field produces a wrong envelope
# rather than a coincidentally right one.
SAMPLE_DIMENSIONS = {
    'length': 12,
    'width': 3,
    'thickness': 0.5,
    'wall_thickness': 0.065,
}


def _declared_combinations():
    """Every (type, shape) `TypeShapeValidator` declares compatible."""
    for item_type in ItemType:
        for shape in type_shape_validator.get_compatible_shapes(item_type):
            yield item_type, shape


class TestAgreementWithTaxonomy:
    """D3: `fit.py` and `taxonomy.py` are kept in agreement by this test.

    Do not weaken it. It is the whole mitigation for carrying a second
    (type, shape) table, and feature 012 is the record of what happens when
    rule tables drift apart unwatched.
    """

    def test_every_declared_combination_is_accounted_for(self):
        """Adding a type or shape to taxonomy must not go unnoticed here."""
        declared = set(_declared_combinations())
        assert declared == set(ENVELOPE_AGREEMENT), (
            'taxonomy and the fit agreement table disagree about which '
            '(type, shape) combinations exist'
        )

    @pytest.mark.parametrize(
        'item_type,shape',
        list(_declared_combinations()),
        ids=lambda value: getattr(value, 'name', str(value)),
    )
    def test_the_envelope_reads_only_the_fields_taxonomy_requires(self, item_type, shape):
        """A row carrying exactly the required dimensions, and nothing else.

        Every other dimension column is NULL, so a rule that reached for a field
        taxonomy never asked for would return INCOMPLETE. An envelope coming
        back therefore proves the rule read only required fields; a SkipReason
        must be the one this combination is declared to produce.
        """
        required = type_shape_validator.get_required_dimensions(item_type, shape)
        recorded = {
            name: SAMPLE_DIMENSIONS[name]
            for name in DIMENSION_FIELDS
            if name in required
        }

        result = envelope_for(item(item_type, shape, **recorded))
        expected = ENVELOPE_AGREEMENT[(item_type, shape)]

        if isinstance(expected, SkipReason):
            assert result == expected
        else:
            assert isinstance(result, expected), (
                f'{item_type.value}/{shape.value} requires {sorted(required)} '
                f'but envelope_for produced {result!r}'
            )


class TestRequestedPieceValidation:
    """The four rules from data-model section 1, refused and accepted."""

    def test_a_rectangular_request_needs_all_three_dimensions(self):
        with pytest.raises(ValueError, match='Thickness'):
            RequestedPiece(ItemShape.RECTANGULAR,
                           {'length': D(4), 'width': D(3)})

    def test_a_round_request_needs_a_diameter_and_a_length(self):
        with pytest.raises(ValueError, match='Diameter'):
            RequestedPiece(ItemShape.ROUND, {'length': D(2)})

    def test_a_dimension_that_does_not_apply_is_refused(self):
        with pytest.raises(ValueError, match='Thickness'):
            RequestedPiece(ItemShape.ROUND,
                           {'diameter': D(2), 'length': D(2), 'thickness': D(1)})

    @pytest.mark.parametrize('value', [0, -1])
    def test_a_dimension_must_be_greater_than_zero(self, value):
        with pytest.raises(ValueError, match='Width'):
            RequestedPiece(ItemShape.RECTANGULAR,
                           {'length': D(4), 'width': D(value), 'thickness': D('0.5')})

    def test_a_negative_tolerance_is_refused_naming_the_dimension(self):
        with pytest.raises(ValueError, match='Length'):
            RequestedPiece(ItemShape.ROUND,
                           {'diameter': D(2), 'length': D(2)},
                           {'length': D('-0.01')})

    def test_a_tolerance_as_large_as_its_dimension_is_refused(self):
        """It would make the dimension meaningless."""
        with pytest.raises(ValueError, match='Length'):
            RequestedPiece(ItemShape.ROUND,
                           {'diameter': D(2), 'length': D(2)},
                           {'length': D(2)})

    def test_a_shape_that_is_not_rectangular_or_round_is_refused(self):
        with pytest.raises(ValueError, match='Rectangular or Round'):
            RequestedPiece(ItemShape.HEX, {'length': D(4), 'width': D(3)})

    def test_a_complete_rectangular_request_is_accepted(self):
        piece = RequestedPiece(ItemShape.RECTANGULAR,
                               {'length': D(4), 'width': D(3), 'thickness': D('0.5')})
        assert piece.dimensions['length'] == D(4)
        assert piece.tolerances == {}

    def test_a_complete_round_request_with_a_tolerance_is_accepted(self):
        piece = RequestedPiece(ItemShape.ROUND,
                               {'diameter': D(2), 'length': D(2)},
                               {'length': D('0.02')})
        assert piece.tolerances['length'] == D('0.02')

    def test_a_zero_tolerance_is_accepted_and_changes_nothing(self):
        """Zero is not negative; it simply means exact, as a blank does."""
        piece = RequestedPiece(ItemShape.ROUND,
                               {'diameter': D(2), 'length': D(2)},
                               {'length': D(0)})
        assert piece.effective('length') == D(2)

    def test_effective_subtracts_the_tolerance_only_where_one_is_stated(self):
        piece = RequestedPiece(ItemShape.RECTANGULAR,
                               {'length': D(4), 'width': D(3), 'thickness': D('0.5')},
                               {'length': D('0.02')})
        assert piece.effective('length') == D('3.98')
        assert piece.effective('width') == D(3)
        assert piece.effective('thickness') == D('0.5')


def rectangular(length, width, thickness, tolerances=None):
    """A rectangular request. `tolerances` is keyed by dimension name."""
    return RequestedPiece(
        ItemShape.RECTANGULAR,
        {'length': D(length), 'width': D(width), 'thickness': D(thickness)},
        {name: D(value) for name, value in (tolerances or {}).items()},
    )


def round_piece(diameter, length, tolerances=None):
    """A round request."""
    return RequestedPiece(
        ItemShape.ROUND,
        {'diameter': D(diameter), 'length': D(length)},
        {name: D(value) for name, value in (tolerances or {}).items()},
    )


class TestF1BoxIntoBox:
    """Rule F1, and User Story 1: orientation stops hiding stock."""

    ITEM = Box(D('0.5'), D(4), D(3))

    @pytest.mark.parametrize('order', [
        ('0.5', 3, 4), (3, 4, '0.5'), (4, '0.5', 3),
        ('0.5', 4, 3), (3, '0.5', 4), (4, 3, '0.5'),
    ])
    def test_every_ordering_of_a_request_gives_the_identical_verdict(self, order):
        """SC-001: the same set comes back whichever order was typed.

        The item is recorded 0.5 x 4 x 3 and the request is typed six ways.
        Sorting both triples is what makes the six indistinguishable.
        """
        fit = evaluate(self.ITEM, rectangular(*order))

        assert fit is not None
        assert fit.item_cross_section == (D(3), D('0.5'))
        assert fit.requested_cross_section == (D(3), D('0.5'))
        assert fit.removed_area == D(0)

    def test_an_item_too_small_in_every_ordering_does_not_fit(self):
        """Story 1 scenario 3: no ordering of 0.5 x 3 x 4 holds 0.75 x 3 x 4."""
        assert evaluate(Box(D('0.5'), D(3), D(4)),
                        rectangular('0.75', 3, 4)) is None

    def test_a_larger_piece_yields_a_smaller_one(self):
        """Story 1 scenario 4."""
        fit = evaluate(Box(D(1), D(6), D(12)), rectangular('0.5', 3, 4))

        assert fit is not None
        assert fit.item_cross_section == (D(6), D(1))
        assert fit.requested_cross_section == (D(3), D('0.5'))
        assert fit.excess == (D(3), D('0.5'))
        assert fit.axial_extent == D(12)

    def test_an_exactly_equal_item_fits(self):
        """FR-012: the comparison is inclusive at the boundary."""
        fit = evaluate(Box(D(4), D(3), D('0.5')), rectangular(4, 3, '0.5'))

        assert fit is not None
        assert fit.removed_area == D(0)
        assert fit.excess == (D(0), D(0))
        assert fit.within_tolerance is False
        assert fit.tolerance_dimensions == ()

    def test_the_minimising_orientation_is_the_sorted_one(self):
        """The part's axis lies along the longest envelope dimension."""
        fit = evaluate(Box(D(12), D(3), D(3)), rectangular('0.5', 3, 4))

        assert fit.item_cross_section == (D(3), D(3))
        assert fit.axial_extent == D(12)
        assert fit.removed_area == D(9) - D('1.5')


class TestF2BoxIntoCylinder:
    """Rule F2 -- a rectangular piece turned out of round stock."""

    def test_a_round_bar_yields_a_rectangular_piece_inside_its_circle(self):
        """Story 2 scenario 4: a 4" round bar yields 1 x 2 x 3."""
        fit = evaluate(Cylinder(D(4), D(12)), rectangular(3, 2, 1))

        assert fit is not None
        assert fit.item_cross_section == (D(4),)
        # The choice that fits with the largest cross-section: the 1" dimension
        # axial, leaving 3 x 2 inscribed in the circle.
        assert fit.requested_cross_section == (D(3), D(2))
        assert fit.axial_extent == D(12)

    def test_a_round_bar_refuses_a_square_that_does_not_fit_its_circle(self):
        """Story 2 scenario 5: 2 x 2 does not fit inside a 2" circle."""
        assert evaluate(Cylinder(D(2), D(12)), rectangular(6, 2, 2)) is None

    def test_a_disc_yields_a_strip_across_its_face(self):
        """fit-rules F2: a 6" x 0.25" disc yields a 0.2 x 1 x 5 bar."""
        fit = evaluate(Cylinder(D(6), D('0.25')), rectangular(5, 1, '0.2'))

        assert fit is not None
        assert fit.requested_cross_section == (D(5), D(1))
        assert fit.axial_extent == D('0.25')

    def test_a_strip_too_long_for_the_disc_does_not_fit(self):
        """1**2 + 6**2 = 37 > 36: the diagonal is what refuses it."""
        assert evaluate(Cylinder(D(6), D('0.25')), rectangular(6, 1, '0.2')) is None

    def test_a_piece_thicker_than_the_disc_does_not_fit(self):
        """Every choice of axial dimension exceeds the 0.25" height."""
        assert evaluate(Cylinder(D(6), D('0.25')), rectangular(1, 1, 1)) is None


class TestF3CylinderIntoBox:
    """Rule F3 -- a round piece turned out of rectangular or square stock."""

    def test_a_square_bar_yields_a_round(self):
        """Story 2 scenario 1: a 3" square bar 12" long yields a 2" round."""
        fit = evaluate(Box(D(12), D(3), D(3)), round_piece(2, 2))

        assert fit is not None
        assert fit.item_cross_section == (D(3), D(3))
        assert fit.requested_cross_section == (D(2),)
        assert fit.excess == (D(1), D(1))
        assert fit.axial_extent == D(12)

    def test_a_cube_yields_a_round(self):
        """Story 2 scenario 2: the issue's own example, a round out of a cube."""
        fit = evaluate(Box(D(6), D(6), D(6)), round_piece(2, 2))

        assert fit is not None
        assert fit.item_cross_section == (D(6), D(6))

    def test_a_thin_bar_refuses_a_round_thicker_than_it(self):
        """A 0.5"-thick bar cannot contain a 2" circle in any orientation."""
        assert evaluate(Box(D(4), D(3), D('0.5')), round_piece(2, 2)) is None

    def test_the_smallest_remaining_product_wins(self):
        """Where two axes fit, the one removing least material is chosen."""
        fit = evaluate(Box(D(12), D(6), D(3)), round_piece(2, 2))

        assert fit.item_cross_section == (D(6), D(3))
        assert fit.axial_extent == D(12)


class TestF4CylinderIntoCylinder:
    """Rule F4 -- both orientations."""

    def test_a_round_bar_yields_a_shorter_round_of_the_same_diameter(self):
        fit = evaluate(Cylinder(D(2), D(12)), round_piece(2, 2))

        assert fit is not None
        assert fit.orientation == 'round from round, upright'
        assert fit.item_cross_section == (D(2),)
        assert fit.removed_area == D(0)

    def test_a_smaller_bar_refuses_a_larger_round(self):
        """Story 2 scenario 3: nothing can be added to a 1.5" bar."""
        assert evaluate(Cylinder(D('1.5'), D(12)), round_piece(2, 2)) is None

    def test_a_disc_yields_a_rod_sawn_across_its_face(self):
        """Crosswise: 1 <= 1 within the thickness, and 1 + 16 <= 36 in plan."""
        fit = evaluate(Cylinder(D(6), D(1)), round_piece(1, 4))

        assert fit is not None
        assert fit.orientation == 'round from round, crosswise'
        assert fit.item_cross_section == (D(1), D(6))
        assert fit.axial_extent == D(6)

    def test_a_rod_too_long_for_the_disc_does_not_fit_crosswise(self):
        """1 + 36 > 36."""
        assert evaluate(Cylinder(D(6), D(1)), round_piece(1, 6)) is None

    def test_upright_is_preferred_where_both_orientations_fit(self):
        """Crosswise overstates its cross-section deliberately, so it loses."""
        fit = evaluate(Cylinder(D(6), D(6)), round_piece(1, 2))

        assert fit.orientation == 'round from round, upright'


class TestNoFloatEscapes:
    """Principle III, checked mechanically rather than trusted."""

    @pytest.mark.parametrize('envelope,piece', [
        (Box(D(12), D(6), D(1)), rectangular('0.5', 3, 4)),
        (Cylinder(D(4), D(12)), rectangular(3, 2, 1)),
        (Box(D(12), D(3), D(3)), round_piece(2, 2)),
        (Cylinder(D(2), D(12)), round_piece(2, 2)),
    ])
    def test_every_figure_a_fit_reports_is_a_decimal(self, envelope, piece):
        fit = evaluate(envelope, piece)

        figures = (fit.item_cross_section + fit.requested_cross_section
                   + fit.excess + (fit.removed_area, fit.axial_extent))
        assert all(isinstance(value, Decimal) for value in figures)


class TestTolerance:
    """Section 5: two-pass evaluation, and attribution of what was load-bearing."""

    SHORT_BAR = Cylinder(D(2), D('1.98'))

    def test_an_item_a_hair_short_fits_when_that_dimension_has_a_tolerance(self):
        """Story 4 scenario 1."""
        fit = evaluate(self.SHORT_BAR, round_piece(2, 2, {'length': '0.02'}))

        assert fit is not None
        assert fit.within_tolerance is True
        assert fit.tolerance_dimensions == ('Length',)

    def test_the_same_item_does_not_fit_without_that_tolerance(self):
        """Story 4 scenario 2: a blank tolerance holds the dimension exactly."""
        assert evaluate(self.SHORT_BAR, round_piece(2, 2)) is None

    def test_a_zero_tolerance_is_the_same_as_none(self):
        assert evaluate(self.SHORT_BAR, round_piece(2, 2, {'length': 0})) is None

    def test_a_tolerance_on_one_dimension_does_not_excuse_another(self):
        """Story 4 scenario 3: 1.98 long and 0.48 thick, tolerance on length only."""
        item = Box(D('1.98'), D(1), D('0.48'))

        assert evaluate(item, rectangular(2, 1, '0.5', {'length': '0.02'})) is None

    def test_an_item_that_fits_at_nominal_is_not_marked_within_tolerance(self):
        """Pass 1 wins outright, so the tolerance is never reached."""
        fit = evaluate(Cylinder(D(2), D(12)), round_piece(2, 2, {'length': '0.02'}))

        assert fit.within_tolerance is False
        assert fit.tolerance_dimensions == ()

    def test_only_the_load_bearing_dimension_is_named(self):
        """Section 5.3: a tolerance the fit did not need is not reported.

        The bar is short but full diameter, so restoring the diameter's
        tolerance changes nothing and restoring the length's breaks the fit.
        """
        fit = evaluate(self.SHORT_BAR,
                       round_piece(2, 2, {'length': '0.02', 'diameter': '0.01'}))

        assert fit.within_tolerance is True
        assert fit.tolerance_dimensions == ('Length',)

    def test_two_load_bearing_dimensions_are_both_named(self):
        item = Box(D('1.98'), D(1), D('0.48'))
        fit = evaluate(item, rectangular(2, 1, '0.5',
                                         {'length': '0.02', 'thickness': '0.02'}))

        assert fit.within_tolerance is True
        assert set(fit.tolerance_dimensions) == {'Length', 'Thickness'}

    def test_a_round_request_names_its_across_measurement_diameter(self):
        """FR-018: the operator sees Diameter, not width."""
        fit = evaluate(Cylinder(D('1.98'), D(12)),
                       round_piece(2, 2, {'diameter': '0.02'}))

        assert fit.tolerance_dimensions == ('Diameter',)


class TestSortKey:
    """Section 4, term by term."""

    def test_an_exact_fit_sorts_before_everything(self):
        """Story 3 scenario 4: zero removed area cannot be beaten."""
        exact = evaluate(Cylinder(D(2), D(12)), round_piece(2, 2))
        loose = evaluate(Box(D(12), D(3), D(3)), round_piece(2, 2))

        assert sort_key('JA000002', exact) < sort_key('JA000001', loose)

    def test_a_shorter_piece_breaks_a_tie_on_removed_area(self):
        """Use up a drop before cutting into a full-length bar."""
        short = evaluate(Cylinder(D(2), D(4)), round_piece(2, 2))
        long = evaluate(Cylinder(D(2), D(12)), round_piece(2, 2))

        assert sort_key('JA000002', short) < sort_key('JA000001', long)

    def test_ja_id_breaks_a_complete_tie(self):
        """FR-020: the three preceding terms can all tie."""
        first = evaluate(Cylinder(D(2), D(12)), round_piece(2, 2))
        second = evaluate(Cylinder(D(2), D(12)), round_piece(2, 2))

        assert sort_key('JA000001', first) < sort_key('JA000002', second)

    def test_an_exact_fit_outranks_a_tolerance_only_fit_that_removes_less(self):
        """D7: stock under nominal has the smaller cross-section, so term 1
        exists to stop it sorting to the top."""
        exact = evaluate(Box(D(12), D(3), D(3)), round_piece(2, 2, {'diameter': '0.1'}))
        tolerance_only = evaluate(Cylinder(D('1.95'), D(12)),
                                  round_piece(2, 2, {'diameter': '0.1'}))

        assert exact.within_tolerance is False
        assert tolerance_only.within_tolerance is True
        assert tolerance_only.removed_area < exact.removed_area
        assert sort_key('JA000002', exact) < sort_key('JA000001', tolerance_only)
