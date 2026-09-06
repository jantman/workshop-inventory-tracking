"""
Unit tests for product label composition.

Composition is asserted directly: dimensions, that the description is present,
that the code is present in both forms, that a long description truncates rather
than overflowing, and that a product with no purchases composes without a
provenance band.

**No test here reaches LpPrinter.print_images()** -- it drives real hardware.
"""

from datetime import datetime
from decimal import Decimal
from io import BytesIO

import pytest
from PIL import Image

from app.services.label_printer import LABEL_TYPES
from app.services.product_label import (
    DESCRIPTION_BAND,
    PROVENANCE_BAND,
    _band_heights,
    compose_product_label,
    format_provenance,
)

CODE = 'WIT0123456789'


def compose_bytes(stock='Sato 2x4', **overrides):
    """Compose a label on a named stock and return the raw PNG bytes.

    The bytes rather than the image, so that two labels can be compared for
    being the *same* label and not merely for looking similar.
    """
    config = LABEL_TYPES[stock]
    kwargs = {
        'description': 'Blue widget, 10mm',
        'code': CODE,
        'provenance_lines': ['Amazon  2026-01-14  $12.34'],
        'lp_width_px': config['lp_width_px'],
        'fixed_len_px': config['fixed_len_px'],
        'maxlen_inches': config['maxlen_inches'],
        'lp_dpi': config['lp_dpi'],
        'flag_mode': config.get('flag_mode', False),
    }
    kwargs.update(overrides)
    return compose_product_label(**kwargs).read()


def compose(stock='Sato 2x4', **overrides):
    """Compose a label on a named stock and return the PIL image"""
    return Image.open(BytesIO(compose_bytes(stock, **overrides)))


def ink_columns(image):
    """Column indices that carry any dark pixel -- a crude 'is something here'"""
    flat = image.convert('L')
    alpha = image.convert('RGBA').split()[3]
    columns = set()
    for x in range(0, flat.width, 4):
        for y in range(0, flat.height, 4):
            if alpha.getpixel((x, y)) > 0 and flat.getpixel((x, y)) < 128:
                columns.add(x)
                break
    return columns


def first_dense_row(image, threshold=0.3, run=20):
    """Where the barcode starts.

    Bars are the only thing on the label that is both wide and *tall*: a run of
    consecutive rows each covering a third of the width. Text has the occasional
    dense row but never a run of them, which is what separates the two.
    """
    flat = image.convert('L')
    alpha = image.convert('RGBA').split()[3]
    sampled = max(1, image.width // 2)

    fractions = []
    for y in range(image.height):
        dark = sum(
            1 for x in range(0, image.width, 2)
            if alpha.getpixel((x, y)) > 0 and flat.getpixel((x, y)) < 128
        )
        fractions.append(dark / sampled)

    for y in range(len(fractions) - run):
        if all(fraction > threshold for fraction in fractions[y:y + run]):
            return y
    return None


class TestOutputShape:
    """The printer must receive what it already expects"""

    @pytest.mark.parametrize('stock', list(LABEL_TYPES))
    def test_dimensions_match_the_stock(self, stock):
        config = LABEL_TYPES[stock]
        image = compose(stock)
        assert image.size == (config['fixed_len_px'], config['lp_width_px'])

    def test_output_is_a_png_bytesio(self):
        config = LABEL_TYPES['Sato 2x4']
        result = compose_product_label(
            description='Blue widget', code=CODE,
            lp_width_px=config['lp_width_px'], fixed_len_px=config['fixed_len_px'],
            maxlen_inches=config['maxlen_inches'], lp_dpi=config['lp_dpi'],
        )
        assert isinstance(result, BytesIO)
        assert Image.open(result).format == 'PNG'

    def test_a_whole_label_types_entry_can_be_splatted_in(self):
        """lp_options rides along in the config and must not be a TypeError"""
        image = Image.open(compose_product_label(
            description='Blue widget', code=CODE, **LABEL_TYPES['Sato 2x4']
        ))
        assert image.size == (1220, 610)


class TestContent:
    """FR-011: description, provenance and a scannable code, all on one label"""

    def test_something_is_drawn_in_the_description_band(self):
        blank = compose(description='', provenance_lines=None)
        with_text = compose(description='Blue widget, 10mm', provenance_lines=None)

        band = with_text.height // 3
        assert len(ink_columns(with_text.crop((0, 0, with_text.width, band)))) > \
            len(ink_columns(blank.crop((0, 0, blank.width, band))))

    def test_the_provenance_band_pushes_the_code_down_and_is_omitted_without_one(self):
        """The band is present or absent, not present-and-blank.

        The barcode is the only dense block on the label, so where it starts says
        exactly how much room the bands above it took.
        """
        with_provenance = first_dense_row(compose(provenance_lines=['Amazon  2026-01-14  $12.34']))
        without = first_dense_row(compose(provenance_lines=None))

        assert with_provenance is not None and without is not None
        assert with_provenance > without

    def test_an_over_long_provenance_line_does_not_overflow(self):
        image = compose(provenance_lines=['A vendor with an implausibly long name ' * 10])
        assert image.size == (1220, 610)

    def test_a_product_with_no_purchases_composes_without_a_provenance_band(self):
        """FR-001: a hand-entered product is still labelable"""
        image = compose(provenance_lines=None)
        assert image.size == (1220, 610)
        assert len(ink_columns(image)) > 0

    def test_the_code_band_carries_ink_even_with_no_description(self):
        """The code is never dropped to gain space -- FR-012"""
        image = compose(description='', provenance_lines=None)
        bottom = image.crop((0, image.height // 2, image.width, image.height))
        assert len(ink_columns(bottom)) > 0


class TestTruncation:
    """The description gives up space. The code never does."""

    def test_a_very_long_description_does_not_overflow_the_label(self):
        long_description = 'Blue widget with an extremely long description ' * 20
        image = compose(description=long_description)
        assert image.size == (1220, 610)

    def test_the_code_band_survives_a_very_long_description(self):
        long_description = 'Blue widget with an extremely long description ' * 20
        image = compose(description=long_description)

        # The bottom third still carries the symbol and its text.
        bottom = image.crop((0, int(image.height * 0.66), image.width, image.height))
        assert len(ink_columns(bottom)) > 0

    def test_an_over_long_identity_line_truncates_rather_than_overflowing(self):
        """FR-007: a long part number shortens; it does not push the code off"""
        image = compose(provenance_lines=[
            'A MANUFACTURER WITH AN IMPLAUSIBLY LONG NAME ' * 5,
            'DigiKey  2026-01-14  $6.50 ea',
        ])

        assert image.size == (1220, 610)
        bottom = image.crop((0, int(image.height * 0.66), image.width, image.height))
        assert len(ink_columns(bottom)) > 0

    def test_the_narrowest_stock_still_composes(self):
        """Sato 1x2 truncates often -- that is the expected trade-off"""
        image = compose('Sato 1x2', description='A description far too long for a 1x2 label ' * 5)
        assert image.size == (610, 305)


class TestBandBudget:
    """More provenance comes out of the description. The code never pays.

    FR-006, and the module's own FR-012 before it: the human-readable code is
    what keeps a scuffed label usable, so it is never traded for space.

    The band split is asserted on ``_band_heights`` directly rather than by
    measuring the composed image. The obvious pixel measure -- find where the
    barcode starts -- does not survive contact with the full stock set: the
    heuristic that separates bars from text needs a tall run of dense rows and
    finds none on the 1x2, and a flag label carries two copies of the panel, one
    rotated, so the first dense row belongs to whichever copy happens to be
    upside down. Asserting the arithmetic is exact where the pixel measure is
    approximate, and it is the arithmetic that FR-006 constrains.
    ``test_the_arithmetic_reaches_the_canvas`` below keeps one end-to-end check
    on the stock where the heuristic does work.
    """

    @pytest.mark.parametrize('stock', list(LABEL_TYPES))
    def test_a_second_provenance_line_does_not_shrink_the_code_band(self, stock):
        height = LABEL_TYPES[stock]['lp_width_px']
        _, _, one = _band_heights(height, 1)
        _, _, two = _band_heights(height, 2)

        assert two == one

    @pytest.mark.parametrize('stock', list(LABEL_TYPES))
    def test_the_second_line_is_paid_for_by_the_description(self, stock):
        height = LABEL_TYPES[stock]['lp_width_px']
        one_description, one_provenance, _ = _band_heights(height, 1)
        two_description, two_provenance, _ = _band_heights(height, 2)

        assert two_provenance - one_provenance == one_description - two_description
        assert two_description > 0

    @pytest.mark.parametrize('stock', list(LABEL_TYPES))
    @pytest.mark.parametrize('line_count', [0, 1, 2])
    def test_the_bands_account_for_the_whole_panel(self, stock, line_count):
        height = LABEL_TYPES[stock]['lp_width_px']
        assert sum(_band_heights(height, line_count)) == height

    @pytest.mark.parametrize('stock', list(LABEL_TYPES))
    def test_the_old_cases_are_unchanged_to_the_pixel(self, stock):
        """SC-006: nothing moved for a label this feature does not concern.

        These are the two splits the module used before provenance could be more
        than one line, spelled out rather than derived, so that a change to the
        arithmetic that happens to preserve the invariant above but shifts a
        label by a pixel still fails.
        """
        height = LABEL_TYPES[stock]['lp_width_px']
        description = int(height * DESCRIPTION_BAND)
        line = int(height * PROVENANCE_BAND)

        assert _band_heights(height, 0) == (description, 0, height - description)
        assert _band_heights(height, 1) == (
            description, line, height - description - line
        )

    def test_the_arithmetic_reaches_the_canvas(self):
        """The one end-to-end check, on the stock the heuristic can measure."""
        one = first_dense_row(compose(provenance_lines=['MEAN WELL  IRM-05-5']))
        two = first_dense_row(compose(provenance_lines=[
            'MEAN WELL  IRM-05-5', 'DigiKey  2026-01-14  $6.50 ea',
        ]))

        assert one is not None and two is not None
        assert two == one

    @pytest.mark.parametrize('stock', list(LABEL_TYPES))
    def test_no_provenance_composes_identically_whether_none_or_empty(self, stock):
        """``None`` is the default; ``[]`` is what format_provenance returns."""
        assert compose_bytes(stock, provenance_lines=None) == \
            compose_bytes(stock, provenance_lines=[])

    @pytest.mark.parametrize('stock', list(LABEL_TYPES))
    def test_an_empty_line_is_not_a_line(self, stock):
        """An empty string must not reserve a band or displace the code."""
        assert compose_bytes(stock, provenance_lines=['']) == \
            compose_bytes(stock, provenance_lines=[])


class TestFlagMode:
    """A flag label reads the same whichever way the fold ends up facing"""

    def test_flag_mode_composes_to_the_stock_size(self):
        image = compose('Sato 2x4 Flag')
        assert image.size == (1220, 610)

    def test_both_halves_carry_content(self):
        image = compose('Sato 2x4 Flag')
        half = image.width // 2
        left = ink_columns(image.crop((0, 0, half, image.height)))
        right = ink_columns(image.crop((half, 0, image.width, image.height)))
        assert len(left) > 0
        assert len(right) > 0


class TestProvenanceLine:
    def test_builds_from_the_most_recent_purchase(self):
        purchase = _FakePurchase('Amazon', datetime(2026, 1, 14), Decimal('12.34'))
        assert format_provenance(purchase) == ['Amazon  2026-01-14  $12.34 ea']

    def test_no_purchase_means_no_lines(self):
        assert format_provenance(None) == []

    def test_a_purchase_with_no_date_or_price_is_still_a_line(self):
        assert format_provenance(_FakePurchase('Amazon', None, None)) == ['Amazon']

    def test_the_price_never_passes_through_a_float(self):
        purchase = _FakePurchase('Amazon', None, Decimal('0.10'))
        assert format_provenance(purchase) == ['Amazon  $0.10 ea']

    def test_the_price_says_it_is_per_unit(self):
        """The whole of US1: $6.50 on a bag of five is a wrong answer."""
        purchase = _FakePurchase('DigiKey', datetime(2026, 1, 14), Decimal('6.50'))
        assert format_provenance(purchase) == ['DigiKey  2026-01-14  $6.50 ea']

    def test_a_zero_price_is_a_price(self):
        """Zero is recorded, not missing, and is marked per-unit like any other"""
        assert format_provenance(_FakePurchase('Amazon', None, Decimal('0.00'))) == [
            'Amazon  $0.00 ea'
        ]

    def test_no_price_means_no_marker(self):
        """No stray 'ea' hanging off a line that never named a price"""
        line = format_provenance(_FakePurchase('Amazon', datetime(2026, 1, 14), None))
        assert line == ['Amazon  2026-01-14']
        assert 'ea' not in line[0]


class TestIdentityLine:
    """US2: the two fields you re-order the thing by reach the label"""

    PURCHASE = ('DigiKey', datetime(2026, 1, 14), Decimal('6.50'))
    PURCHASE_LINE = 'DigiKey  2026-01-14  $6.50 ea'

    def test_manufacturer_and_part_number_lead(self):
        assert format_provenance(
            _FakePurchase(*self.PURCHASE),
            manufacturer='MEAN WELL',
            part_number='IRM-05-5',
        ) == ['MEAN WELL  IRM-05-5', self.PURCHASE_LINE]

    @pytest.mark.parametrize('manufacturer,part_number,purchase,expected', [
        # SC-003: all eight combinations of present and absent. No line is ever
        # blank, and no line carries a doubled or trailing separator.
        (None, None, False, []),
        (None, None, True, ['DigiKey  2026-01-14  $6.50 ea']),
        ('MEAN WELL', None, False, ['MEAN WELL']),
        (None, 'IRM-05-5', False, ['IRM-05-5']),
        ('MEAN WELL', 'IRM-05-5', False, ['MEAN WELL  IRM-05-5']),
        ('MEAN WELL', None, True, ['MEAN WELL', 'DigiKey  2026-01-14  $6.50 ea']),
        (None, 'IRM-05-5', True, ['IRM-05-5', 'DigiKey  2026-01-14  $6.50 ea']),
        ('MEAN WELL', 'IRM-05-5', True,
         ['MEAN WELL  IRM-05-5', 'DigiKey  2026-01-14  $6.50 ea']),
    ])
    def test_every_combination_degrades_gracefully(
        self, manufacturer, part_number, purchase, expected
    ):
        result = format_provenance(
            _FakePurchase(*self.PURCHASE) if purchase else None,
            manufacturer=manufacturer,
            part_number=part_number,
        )

        assert result == expected
        assert all(line == line.strip() for line in result)
        assert not any('   ' in line for line in result)

    def test_a_product_never_bought_still_gets_its_identity(self):
        """FR-004: provenance is no longer conditional on a purchase existing"""
        assert format_provenance(
            None, manufacturer='MEAN WELL', part_number='IRM-05-5'
        ) == ['MEAN WELL  IRM-05-5']

    @pytest.mark.parametrize('empty', ['', '   ', '\t', None])
    def test_an_empty_field_is_an_absent_field(self, empty):
        """FR-003: no blank field, no doubled separator, no trailing separator"""
        assert format_provenance(
            None, manufacturer='MEAN WELL', part_number=empty
        ) == ['MEAN WELL']
        assert format_provenance(
            None, manufacturer=empty, part_number='IRM-05-5'
        ) == ['IRM-05-5']
        assert format_provenance(None, manufacturer=empty, part_number=empty) == []

    def test_surrounding_whitespace_is_trimmed_not_printed(self):
        assert format_provenance(
            None, manufacturer='  MEAN WELL  ', part_number=' IRM-05-5 '
        ) == ['MEAN WELL  IRM-05-5']


class _FakePurchase:
    """The three fields the provenance line reads, without a database"""

    def __init__(self, vendor, order_date, unit_price):
        self.vendor = vendor
        self.order_date = order_date
        self.unit_price = unit_price
