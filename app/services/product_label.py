"""
Product label composition.

The existing ``BarcodeLabelGenerator`` draws a barcode plus, as text, the
barcode's own value -- there is no parameter for a caption or a second line. So
FR-011 (description **and** provenance **and** a scannable code on one label)
cannot be met by calling it, and this module composes the image instead.

What it does *not* change is the printing path. The output is a PNG ``BytesIO``
of exactly the dimensions the existing generator produces for the chosen stock,
handed to the same ``LpPrinter.print_images()`` with the same ``lp_options``.
No new printer control language, no new driver -- which is precisely what the
spec's constraint protects.

FR-012 is a durability requirement, not a formatting preference: direct-thermal
labels degrade in a workshop, and the human-readable code is what keeps a label
with a scuffed barcode usable. It is therefore never dropped to gain space. The
description truncates first.
"""

import logging
from io import BytesIO
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont
from pt_p710bt_label_maker.barcode_label import BarcodeLabelGenerator

logger = logging.getLogger(__name__)

FONT_FILENAME = 'DejaVuSans.ttf'

# Below this the description is no longer worth reading, so it is truncated
# rather than shrunk any further.
MIN_DESCRIPTION_FONT_PX = 14
MIN_PROVENANCE_FONT_PX = 10

# Fractions of the label height, top to bottom.
DESCRIPTION_BAND = 0.38
PROVENANCE_BAND = 0.14

MARGIN_FRACTION = 0.03
ELLIPSIS = '…'


def compose_product_label(
    description: str,
    code: str,
    provenance_lines: Optional[Sequence[str]] = None,
    lp_width_px: int = 610,
    fixed_len_px: int = 1220,
    maxlen_inches: float = 4.0,
    lp_dpi: int = 305,
    flag_mode: bool = False,
    **_ignored: Any,
) -> BytesIO:
    """Compose a product label as a PNG.

    Args:
        description: The product's description; the largest thing on the label.
        code: The internal product code, rendered as a Code128 symbol *and* as
            text. Both, always.
        provenance_lines: The provenance lines from ``format_provenance``:
            identity (manufacturer, part number) then purchase (vendor, order
            date, per-unit price). Either may be absent; when the list is empty
            the band is omitted entirely rather than left blank -- a
            hand-entered product with nothing to say is still labelable
            (FR-001).

            A *sequence*, not a string, and named so. ``str`` satisfies
            ``Sequence[str]``, so a parameter that accepted both would draw one
            line per character for a caller that had not been updated.
        lp_width_px: The stock's pixel height, from LABEL_TYPES.
        fixed_len_px: The stock's pixel length, from LABEL_TYPES.
        maxlen_inches: The stock's length in inches, from LABEL_TYPES.
        lp_dpi: The stock's DPI, from LABEL_TYPES.
        flag_mode: Whether this stock folds back on itself, in which case the
            content is repeated at both ends so it reads either way round.
        **_ignored: Other LABEL_TYPES keys (``lp_options``) are accepted so a
            config entry can be splatted in whole.

    Returns:
        A PNG BytesIO sized (fixed_len_px x lp_width_px), ready for
        LpPrinter.print_images().
    """
    if flag_mode:
        # Each half carries the whole message, so the label reads the same
        # whichever way the fold ends up facing.
        half = _compose_panel(
            description, code, provenance_lines,
            width_px=fixed_len_px // 2,
            height_px=lp_width_px,
            maxlen_inches=maxlen_inches / 2,
            lp_dpi=lp_dpi,
        )
        canvas = Image.new('RGBA', (fixed_len_px, lp_width_px), (255, 255, 255, 0))
        canvas.paste(half, (0, 0))
        canvas.paste(half.rotate(180), (fixed_len_px - half.width, 0))
    else:
        canvas = _compose_panel(
            description, code, provenance_lines,
            width_px=fixed_len_px,
            height_px=lp_width_px,
            maxlen_inches=maxlen_inches,
            lp_dpi=lp_dpi,
        )

    out = BytesIO()
    canvas.save(out, format='PNG')
    out.seek(0)
    return out


def _band_heights(height_px: int, line_count: int) -> Tuple[int, int, int]:
    """Split the panel into description, provenance and code bands.

    The code band is the one that must not shrink (FR-006, and FR-012 before
    it): the human-readable code is what keeps a scuffed label usable, so more
    provenance is paid for by the description and never by the code.

    The first provenance line takes ``PROVENANCE_BAND`` from the panel, exactly
    as it always has. **Every line after the first is subtracted from the
    description**, which is what holds the code band constant no matter how many
    provenance lines there are. Written as a subtraction from the existing
    constants rather than as a fresh fraction of the panel, so that the
    zero-line and one-line cases are not merely close to their old values but
    identical to the pixel -- a label that gained nothing from this feature
    prints exactly what it printed before.

    Returns:
        ``(description_height, provenance_height, code_height)``, summing to
        ``height_px``.
    """
    line_height = int(height_px * PROVENANCE_BAND)
    provenance_height = line_height * line_count

    description_height = int(height_px * DESCRIPTION_BAND)
    if line_count > 1:
        description_height -= line_height * (line_count - 1)

    code_height = height_px - description_height - provenance_height
    return description_height, provenance_height, code_height


def _compose_panel(
    description: str,
    code: str,
    provenance_lines: Optional[Sequence[str]],
    width_px: int,
    height_px: int,
    maxlen_inches: float,
    lp_dpi: int,
) -> Image.Image:
    """Compose one panel: description band, provenance lines, then the code.

    Empty lines are dropped before anything is measured, so a provenance line
    with nothing in it neither reserves a band nor moves the code.
    ``_band_heights`` divides what is left; see its docstring for why the code
    band comes out the same whether there is one provenance line or two.
    """
    canvas = Image.new('RGBA', (width_px, height_px), (255, 255, 255, 0))
    draw = ImageDraw.Draw(canvas)

    margin = max(2, int(width_px * MARGIN_FRACTION))
    usable_width = width_px - 2 * margin

    lines = [line for line in (provenance_lines or []) if line]
    description_height, provenance_height, code_height = _band_heights(
        height_px, len(lines)
    )
    # Divided back out rather than recomputed, so the row a line is drawn on
    # cannot drift from the band that was reserved for it.
    line_height = provenance_height // len(lines) if lines else 0

    cursor = _draw_description(
        draw, description or '', margin, description_height, usable_width
    )

    if lines:
        cursor = _draw_provenance(
            draw, lines, margin, cursor, line_height, usable_width
        )

    _paste_code(canvas, code, margin, cursor, code_height, usable_width,
                maxlen_inches, lp_dpi)

    return canvas


def _fit_font(text: str, max_width: int, max_height: int, min_size: int) -> ImageFont.FreeTypeFont:
    """Largest font at which `text` fits the box, never below `min_size`.

    Height is measured as ``box[3]`` rather than ``box[3] - box[1]``: text is
    drawn from the ascender origin, so the descender's extent below that origin
    is what actually has to fit, and measuring the tight glyph box instead leaves
    the tail of a 'g' hanging off the label.
    """
    chosen = ImageFont.truetype(FONT_FILENAME, size=min_size)
    for size in range(min_size, 200, 2):
        try:
            candidate = ImageFont.truetype(FONT_FILENAME, size=size)
        except OSError:
            break
        box = candidate.getbbox(text)
        if (box[2] - box[0]) <= max_width and box[3] <= max_height:
            chosen = candidate
        else:
            break
    return chosen


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    """Greedy word wrap at the given font and width."""
    lines = []
    current = ''
    for word in text.split():
        candidate = f"{current} {word}".strip()
        box = font.getbbox(candidate)
        if (box[2] - box[0]) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _truncate(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """Shorten a single line to fit, marking that it was shortened."""
    if (font.getbbox(text)[2] - font.getbbox(text)[0]) <= max_width:
        return text

    shortened = text
    while shortened:
        shortened = shortened[:-1]
        candidate = shortened.rstrip() + ELLIPSIS
        box = font.getbbox(candidate)
        if (box[2] - box[0]) <= max_width:
            return candidate
    return ELLIPSIS


def _draw_description(draw, description: str, margin: int, band_height: int,
                      usable_width: int) -> int:
    """Draw the description band and return the y coordinate below it."""
    if not description.strip():
        return band_height

    # Try progressively smaller fonts until the wrapped text fits the band; the
    # description is what gives up space, never the code.
    for size in range(60, MIN_DESCRIPTION_FONT_PX - 1, -2):
        try:
            font = ImageFont.truetype(FONT_FILENAME, size=size)
        except OSError:
            continue
        lines = _wrap(description, font, usable_width)
        line_height = int(size * 1.2)
        if len(lines) * line_height <= band_height:
            break
    else:
        font = ImageFont.truetype(FONT_FILENAME, size=MIN_DESCRIPTION_FONT_PX)
        lines = _wrap(description, font, usable_width)
        line_height = int(MIN_DESCRIPTION_FONT_PX * 1.2)

    max_lines = max(1, band_height // line_height)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _truncate(lines[-1] + ELLIPSIS, font, usable_width)

    y = 0
    for line in lines:
        draw.text((margin, y), line, fill=(0, 0, 0, 255), font=font)
        y += line_height

    return band_height


def _draw_provenance(draw, lines: Sequence[str], margin: int, top: int,
                     line_height: int, usable_width: int) -> int:
    """Draw the provenance lines and return the y coordinate below them.

    One font for all of them, fitted to whichever line needs the smallest. Two
    lines set at different sizes read as a mistake, and the smallest of the
    fitted sizes is the only one that is guaranteed to fit every line. With a
    single line this reduces to fitting that line, which is what it did when a
    single line was all there could be.
    """
    max_height = int(line_height * 0.8)
    font = min(
        (_fit_font(line, usable_width, max_height, MIN_PROVENANCE_FONT_PX)
         for line in lines),
        key=lambda candidate: candidate.size,
    )

    for index, line in enumerate(lines):
        draw.text(
            (margin, top + index * line_height),
            _truncate(line, font, usable_width),
            fill=(0, 0, 0, 255),
            font=font,
        )

    return top + line_height * len(lines)


def _paste_code(canvas, code: str, margin: int, top: int, band_height: int,
                usable_width: int, maxlen_inches: float, lp_dpi: int) -> None:
    """Paste the Code128 symbol with the code beneath it, as text.

    Both forms, always. This is FR-012, not a display option: the text is what
    makes a label with a degraded barcode still usable, so it is drawn here
    rather than left to the generator's own rendering, whose size cannot be
    controlled independently of the bars.
    """
    text_height = max(MIN_DESCRIPTION_FONT_PX, int(band_height * 0.34))
    bar_height = max(1, band_height - text_height)
    maxlen_px = max(1, int(maxlen_inches * lp_dpi))

    generator = BarcodeLabelGenerator(
        value=code,
        height_px=bar_height,
        maxlen_px=min(maxlen_px, usable_width),
        show_text=False,
    )
    bars = Image.open(generator.file_obj).convert('RGBA')

    # The generator adds its own quiet zone, so what comes back is taller than
    # what was asked for. Trim it to the band or the human-readable code below
    # gets pushed off the label -- and that code is the one thing that must not
    # be sacrificed for space (FR-012).
    if bars.height > bar_height:
        bars = bars.resize((bars.width, bar_height), Image.NEAREST)

    if bars.width > usable_width:
        scale = usable_width / bars.width
        bars = bars.resize(
            (usable_width, max(1, int(bars.height * scale))), Image.LANCZOS
        )
    else:
        # Widen the symbol to fill the label. A wider module is a more forgiving
        # one once the label has spent a year on a shelf, and an integer factor
        # with NEAREST keeps the bar edges hard -- interpolating a barcode is how
        # you get a symbol that looks fine and scans badly.
        factor = usable_width // bars.width
        if factor > 1:
            bars = bars.resize((bars.width * factor, bars.height), Image.NEAREST)

    canvas.paste(bars, (margin + max(0, (usable_width - bars.width) // 2), top), bars)

    font = _fit_font(code, usable_width, text_height, MIN_DESCRIPTION_FONT_PX)
    text_box = font.getbbox(code)
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (margin + max(0, (usable_width - (text_box[2] - text_box[0])) // 2),
         top + bars.height),
        code,
        fill=(0, 0, 0, 255),
        font=font,
    )


def format_provenance(
    purchase,
    manufacturer: Optional[str] = None,
    part_number: Optional[str] = None,
) -> List[str]:
    """Build the provenance lines: identity first, then the purchase.

    Identity goes first because it answers the question asked more often. Once
    the bag is open and the box is gone, the manufacturer and part number are
    what identify the thing and what you re-order it by; the vendor and the date
    are what you consult afterwards, if at all.

    Two lines rather than one long one. The font is fitted to the widest line, so
    splitting the fields in two sets them at roughly double the size a single
    run of six fields would get on the narrow stocks -- and on a direct-thermal
    label that will be read in five years, size is durability.

    The two are built independently: a product that has never been bought still
    has a manufacturer, and it now gets a label that says so (FR-004).

    Args:
        purchase: A Purchase, or None when the product has never been bought.
        manufacturer: The product's manufacturer, if it has one.
        part_number: The manufacturer's part number, if it has one.

    Returns:
        The lines to print, in order. Empty when there is nothing to say -- in
        which case the band is omitted rather than left blank.
    """
    candidates = [
        _join([manufacturer, part_number]),
        _join(_purchase_fields(purchase)),
    ]

    return [line for line in candidates if line]


def _purchase_fields(purchase) -> List[Any]:
    """Vendor, order date and price of the most recent purchase."""
    if purchase is None:
        return []

    parts = [purchase.vendor]
    if purchase.order_date is not None:
        parts.append(purchase.order_date.strftime('%Y-%m-%d'))
    if purchase.unit_price is not None:
        # str() on the Decimal: a price never passes through a float, not even
        # on its way to a label. The suffix is concatenated onto that string, so
        # nothing here is ever an arithmetic operand.
        #
        # "ea" is three characters standing between a reader and a wrong answer.
        # This is a *unit* price going onto a bag that may hold five, and a label
        # in a drawer is read precisely because nobody wants to go and look the
        # order up -- possibly years later, by someone who never saw it.
        parts.append(f"${purchase.unit_price} ea")

    return parts


def _join(parts: Sequence[Any]) -> str:
    """Join the fields of one provenance line, dropping the ones with nothing.

    A field that is absent, empty, or nothing but whitespace takes its separator
    with it, so no label carries a blank field, a doubled separator, or a
    separator with nothing after it (FR-003).
    """
    return '  '.join(
        str(part).strip() for part in parts if part is not None and str(part).strip()
    )


def print_product_label(
    description: str,
    code: str,
    provenance_lines: Optional[Sequence[str]],
    label_config: Dict[str, Any],
    num_copies: int = 1,
) -> None:
    """Compose a product label and send it to the printer.

    Keeps the existing test seam: when TESTING or DISABLE_LABEL_PRINTING is set
    this logs what it would have printed and returns. **No test ever reaches
    LpPrinter.print_images()** -- it drives real hardware.

    Args:
        description: The product's description.
        code: The internal product code.
        provenance_lines: The provenance lines, possibly empty.
        label_config: One LABEL_TYPES entry.
        num_copies: How many to print.
    """
    from flask import current_app
    from pt_p710bt_label_maker.lp_printer import LpPrinter

    if current_app and (
        current_app.config.get('TESTING', False)
        or current_app.config.get('DISABLE_LABEL_PRINTING', False)
    ):
        logger.info(
            f"Test mode detected - short-circuiting product label print. "
            f"Would have printed: description='{description}', code='{code}', "
            f"provenance={list(provenance_lines or [])}, "
            f"lp_options='{label_config.get('lp_options')}', "
            f"num_copies={num_copies}"
        )
        return

    image = compose_product_label(
        description=description,
        code=code,
        provenance_lines=provenance_lines,
        lp_width_px=label_config['lp_width_px'],
        fixed_len_px=label_config['fixed_len_px'],
        maxlen_inches=label_config['maxlen_inches'],
        lp_dpi=label_config.get('lp_dpi', 305),
        flag_mode=label_config.get('flag_mode', False),
    )

    printer = LpPrinter(label_config['lp_options'])
    printer.print_images([image] * num_copies)
    logger.info(f"Printed {num_copies} product label(s) for {code}")
