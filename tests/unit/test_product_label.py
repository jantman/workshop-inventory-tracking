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
from app.services.product_label import compose_product_label, format_provenance

CODE = 'WIT0123456789'


def compose(stock='Sato 2x4', **overrides):
    """Compose a label on a named stock and return the PIL image"""
    config = LABEL_TYPES[stock]
    kwargs = {
        'description': 'Blue widget, 10mm',
        'code': CODE,
        'provenance': 'Amazon  2026-01-14  $12.34',
        'lp_width_px': config['lp_width_px'],
        'fixed_len_px': config['fixed_len_px'],
        'maxlen_inches': config['maxlen_inches'],
        'lp_dpi': config['lp_dpi'],
        'flag_mode': config.get('flag_mode', False),
    }
    kwargs.update(overrides)
    return Image.open(compose_product_label(**kwargs))


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
        blank = compose(description='', provenance=None)
        with_text = compose(description='Blue widget, 10mm', provenance=None)

        band = with_text.height // 3
        assert len(ink_columns(with_text.crop((0, 0, with_text.width, band)))) > \
            len(ink_columns(blank.crop((0, 0, blank.width, band))))

    def test_the_provenance_band_pushes_the_code_down_and_is_omitted_without_one(self):
        """The band is present or absent, not present-and-blank.

        The barcode is the only dense block on the label, so where it starts says
        exactly how much room the bands above it took.
        """
        with_provenance = first_dense_row(compose(provenance='Amazon  2026-01-14  $12.34'))
        without = first_dense_row(compose(provenance=None))

        assert with_provenance is not None and without is not None
        assert with_provenance > without

    def test_an_over_long_provenance_line_does_not_overflow(self):
        image = compose(provenance='A vendor with an implausibly long name ' * 10)
        assert image.size == (1220, 610)

    def test_a_product_with_no_purchases_composes_without_a_provenance_band(self):
        """FR-001: a hand-entered product is still labelable"""
        image = compose(provenance=None)
        assert image.size == (1220, 610)
        assert len(ink_columns(image)) > 0

    def test_the_code_band_carries_ink_even_with_no_description(self):
        """The code is never dropped to gain space -- FR-012"""
        image = compose(description='', provenance=None)
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

    def test_the_narrowest_stock_still_composes(self):
        """Sato 1x2 truncates often -- that is the expected trade-off"""
        image = compose('Sato 1x2', description='A description far too long for a 1x2 label ' * 5)
        assert image.size == (610, 305)


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
        assert format_provenance(purchase) == 'Amazon  2026-01-14  $12.34'

    def test_no_purchase_means_no_line(self):
        assert format_provenance(None) is None

    def test_a_purchase_with_no_date_or_price_is_still_a_line(self):
        assert format_provenance(_FakePurchase('Amazon', None, None)) == 'Amazon'

    def test_the_price_never_passes_through_a_float(self):
        purchase = _FakePurchase('Amazon', None, Decimal('0.10'))
        assert format_provenance(purchase) == 'Amazon  $0.10'


class _FakePurchase:
    """The three fields the provenance line reads, without a database"""

    def __init__(self, vendor, order_date, unit_price):
        self.vendor = vendor
        self.order_date = order_date
        self.unit_price = unit_price
