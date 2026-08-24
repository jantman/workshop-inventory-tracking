"""
Stock fit -- can the piece the operator needs be cut out of the piece on the shelf?

Two invariants govern this module.

* **Pure functions only.** No Flask, no SQLAlchemy, no storage, no config. It is
  handed an inventory row's recorded type, shape and dimensions and a
  description of the piece wanted, and answers with geometry. That is what lets
  the whole of it be tested exhaustively in the sub-second unit suite with no
  fixtures (`tests/unit/test_fit.py`).
* **`Decimal` only, never `float`** -- in arithmetic, in comparison, and in
  everything handed back. Constitution Principle III. Where a diagonal is
  involved the comparison is made between *squared* quantities, so no square
  root is ever taken: a rectangle `y x z` fits a circle of diameter `d` when
  `y**2 + z**2 <= d**2`.

The normative statement of the table below is
`specs/027-stock-fit-search/contracts/fit-rules.md`. This module implements
exactly that and nothing beyond it.

This module carries its own (type, shape) -> solid table, deliberately separate
from `app/taxonomy.py`'s (type, shape) -> required-fields table: taxonomy states
what a record must *contain*, this states what solid those contents *describe*,
and the field list does not determine the solid. `tests/unit/test_fit.py` walks
every combination taxonomy declares and asserts the two agree, which is what
keeps them from drifting apart.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, Mapping, Optional, Tuple, Union

from app.models import ItemShape, ItemType
from app.taxonomy import field_label

# The same constant `Dimensions.volume()` uses in `app/models.py`. It appears
# only in the sort key -- `Fit.removed_area`, term 2 of `sort_key()` -- and never
# in a figure shown to the operator, who is given exact subtraction instead
# (fit-rules section 6).
PI = Decimal('3.14159265359')

ZERO = Decimal('0')


# --------------------------------------------------------------------------
# The envelope: what solid an inventory row describes
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Box:
    """A solid rectangular prism.

    The field names imply no ordering -- `a` is not necessarily the largest.
    Every rule that cares sorts first.
    """
    a: Decimal
    b: Decimal
    c: Decimal


@dataclass(frozen=True)
class Cylinder:
    """A solid cylinder: a bar seen end-on, or a disc standing on end."""
    diameter: Decimal
    height: Decimal


class SkipReason(Enum):
    """Why a row could not be reduced to a solid, and so was not evaluated."""

    HOLLOW = 'hollow'
    INCOMPLETE = 'incomplete'


Envelope = Union[Box, Cylinder]

# The requested dimensions each request shape needs, in the order they are read.
REQUIRED_DIMENSIONS: Dict[ItemShape, Tuple[str, ...]] = {
    ItemShape.RECTANGULAR: ('length', 'width', 'thickness'),
    ItemShape.ROUND: ('diameter', 'length'),
}


def _box(*values: Optional[Decimal]) -> Union[Box, SkipReason]:
    """Rule E6 for a box: any field the chosen rule needs being NULL is fatal."""
    if any(value is None for value in values):
        return SkipReason.INCOMPLETE
    return Box(*values)


def _cylinder(diameter: Optional[Decimal],
              height: Optional[Decimal]) -> Union[Cylinder, SkipReason]:
    """Rule E6 for a cylinder."""
    if diameter is None or height is None:
        return SkipReason.INCOMPLETE
    return Cylinder(diameter, height)


def envelope_for(item) -> Union[Envelope, SkipReason]:
    """The solid an inventory row describes, or why it describes none.

    Rules E1-E6 of fit-rules section 1, applied in order; the first that matches
    wins. `item` is anything carrying the four dimension columns and the two
    enum properties `InventoryItem` exposes -- no ORM behaviour is used.
    """
    # E1 -- a wall thickness means the recorded outside dimensions describe a
    # shell, not a solid. Presence only; the magnitude is never read (FR-010).
    if item.wall_thickness is not None:
        return SkipReason.HOLLOW

    shape = item.shape_enum
    item_type = item.item_type_enum

    # E2 -- a disc: how far across, and how thick. This MUST precede E3, so that
    # a round plate carrying a stale `length` is still read as a disc rather
    # than as a bar of that length; the length on such a row describes nothing.
    if shape == ItemShape.ROUND and item_type in (ItemType.PLATE, ItemType.SHEET):
        return _cylinder(item.width, item.thickness)

    # E3 -- a bar. For a hex, `width` is the across-flats measurement, so the
    # cylinder is the circle inscribed in the flats: conservative by design.
    if shape in (ItemShape.ROUND, ItemShape.HEX):
        return _cylinder(item.width, item.length)

    # E4 -- a square prism: `Bar`/`Square` requires only length and width, the
    # second cross-section dimension being equal to the first.
    if shape == ItemShape.SQUARE and item.thickness is None:
        return _box(item.length, item.width, item.width)

    # E5 -- everything else: rectangular and square plate and sheet, rectangular
    # bar, and one leg of an angle or one wall of a channel.
    return _box(item.length, item.width, item.thickness)


# --------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------

def dimension_label(name: str) -> str:
    """Name a requested dimension as the operator sees it on the form.

    Routed through taxonomy so `Wall Thickness`-style labelling stays in one
    place. `RECTANGULAR` is passed because a rectangular request's `width` is a
    width; a round request names its across-measurement `diameter` outright and
    so never reaches the round/width substitution.
    """
    return field_label(name, ItemShape.RECTANGULAR)


@dataclass(frozen=True)
class RequestedPiece:
    """What the operator needs. Not stored; it lives for one search.

    Validated on construction, so nothing downstream has to re-check it. Every
    failure raises `ValueError` naming the offending dimension as the operator
    sees it, which is what the route turns into a 400 (FR-004, FR-005, FR-017).
    """

    shape: ItemShape
    dimensions: Mapping[str, Decimal]
    tolerances: Mapping[str, Decimal] = field(default_factory=dict)

    def __post_init__(self):
        required = REQUIRED_DIMENSIONS.get(self.shape)
        if required is None:
            raise ValueError(
                f'A requested piece must be Rectangular or Round, not '
                f'{getattr(self.shape, "value", self.shape)}'
            )

        for name in required:
            if self.dimensions.get(name) is None:
                raise ValueError(f'{dimension_label(name)} is required for a '
                                 f'{self.shape.value} piece')

        for name in self.dimensions:
            if name not in required:
                raise ValueError(f'{dimension_label(name)} does not apply to a '
                                 f'{self.shape.value} piece')
            if self.dimensions[name] <= ZERO:
                raise ValueError(f'{dimension_label(name)} must be greater than zero')

        for name, tolerance in self.tolerances.items():
            if name not in required:
                raise ValueError(f'{dimension_label(name)} does not apply to a '
                                 f'{self.shape.value} piece')
            if tolerance < ZERO:
                raise ValueError(f'The tolerance on {dimension_label(name)} '
                                 f'cannot be negative')
            if tolerance >= self.dimensions[name]:
                raise ValueError(
                    f'The tolerance on {dimension_label(name)} must be smaller than '
                    f'{dimension_label(name)} itself'
                )

    def effective(self, name: str) -> Decimal:
        """The dimension an item may fall to and still be returned.

        `nominal - tolerance`; with no tolerance stated, the nominal value
        itself, because a blank tolerance means exact (FR-015).
        """
        return self.dimensions[name] - self.tolerances.get(name, ZERO)


# --------------------------------------------------------------------------
# The fit test
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class _Match:
    """One orientation that fits, before tolerance is accounted for.

    `removed_area` and `axial_extent` exist for the sort key and are never
    shown; the two cross-sections and the excess derived from them are what the
    operator reads (fit-rules section 6).
    """

    orientation: str
    item_cross_section: Tuple[Decimal, ...]
    requested_cross_section: Tuple[Decimal, ...]
    removed_area: Decimal
    axial_extent: Decimal


@dataclass(frozen=True)
class Fit:
    """The outcome for one candidate. Only produced when the piece fits."""

    within_tolerance: bool
    tolerance_dimensions: Tuple[str, ...]
    orientation: str
    item_cross_section: Tuple[Decimal, ...]
    requested_cross_section: Tuple[Decimal, ...]
    excess: Tuple[Decimal, ...]
    removed_area: Decimal
    axial_extent: Decimal


def _circle_area(diameter: Decimal) -> Decimal:
    """The area of a circle, for the sort key alone. The one use of `PI`."""
    return PI * diameter * diameter / 4


def _excess(item_cross_section: Tuple[Decimal, ...],
            requested_cross_section: Tuple[Decimal, ...]) -> Tuple[Decimal, ...]:
    """Envelope figure minus requested figure, per cross-section dimension.

    Exact `Decimal` subtraction; no area and no `PI` reach the operator.

    Where the two cross-sections carry the same number of figures they pair up.
    A circular *requested* cross-section is one figure against a rectangular
    envelope's two, and there the diameter is what each envelope figure has to
    clear, so it is subtracted from both. A circular *envelope* against a
    rectangular request has no per-dimension comparison to make -- the request's
    two figures are constrained jointly, by the diagonal -- so nothing is
    reported for it and the two cross-sections stand on their own.
    """
    if len(item_cross_section) == len(requested_cross_section):
        return tuple(i - r for i, r
                     in zip(item_cross_section, requested_cross_section))
    if len(requested_cross_section) == 1:
        return tuple(i - requested_cross_section[0] for i in item_cross_section)
    return ()


def _requested_solid(piece: RequestedPiece,
                     exact: Optional[frozenset]) -> Envelope:
    """The solid the request describes.

    `exact is None` holds every dimension at nominal. Otherwise every dimension
    falls to its effective value except those named in `exact`, which is how
    section 5's attribution pass restores one tolerance at a time.
    """
    def value(name: str) -> Decimal:
        if exact is None or name in exact:
            return piece.dimensions[name]
        return piece.effective(name)

    if piece.shape == ItemShape.RECTANGULAR:
        return Box(value('length'), value('width'), value('thickness'))
    return Cylinder(value('diameter'), value('length'))


def _f1(requested: Box, envelope: Box) -> Optional[_Match]:
    """F1 -- a box out of a box.

    Sort both triples descending and compare componentwise. The sorted
    assignment is also the minimising orientation -- it leaves the two smallest
    envelope dimensions as the cross-section -- so no search over the six
    permutations is needed.

    The comparison is inclusive: an item exactly the requested size fits
    (FR-012).
    """
    p, q, r = sorted((requested.a, requested.b, requested.c), reverse=True)
    a, b, c = sorted((envelope.a, envelope.b, envelope.c), reverse=True)

    if p <= a and q <= b and r <= c:
        return _Match('box from box', (b, c), (q, r), b * c - q * r, a)
    return None


def _f2(requested: Box, envelope: Cylinder) -> Optional[_Match]:
    """F2 -- a box out of a cylinder.

    For each of the three choices of which request dimension is axial, the
    remaining two form a rectangle that must be inscribed in the circle:
    `y**2 + z**2 <= d**2`. Squares are compared so no square root is taken (D4).

    This one rule covers the disc-yields-a-strip case: a 6" x 0.25" plate yields
    a 0.2" x 1" x 5" bar with the 0.2 axial, because 1 + 25 <= 36.
    """
    dimensions = (requested.a, requested.b, requested.c)
    diameter_squared = envelope.diameter * envelope.diameter

    best = None
    for i in range(3):
        axial = dimensions[i]
        y, z = dimensions[:i] + dimensions[i + 1:]
        if axial <= envelope.height and y * y + z * z <= diameter_squared:
            # Where more than one choice fits, the largest cross-section is the
            # one that removes the least.
            if best is None or y * z > best[0]:
                best = (y * z, y, z)

    if best is None:
        return None

    area, y, z = best
    return _Match('box from round', (envelope.diameter,), (y, z),
                  _circle_area(envelope.diameter) - area, envelope.height)


def _f3(requested: Cylinder, envelope: Box) -> Optional[_Match]:
    """F3 -- a cylinder out of a box.

    For each axis of the box: that dimension must be at least the part's length,
    and both remaining dimensions at least its diameter. Where more than one
    axis fits, the smallest remaining product removes the least material.
    """
    dimensions = (envelope.a, envelope.b, envelope.c)

    best = None
    for i in range(3):
        axial = dimensions[i]
        rest = dimensions[:i] + dimensions[i + 1:]
        if axial >= requested.height and all(m >= requested.diameter for m in rest):
            product = rest[0] * rest[1]
            if best is None or product < best[0]:
                best = (product, rest, axial)

    if best is None:
        return None

    product, rest, axial = best
    return _Match('round from box', rest, (requested.diameter,),
                  product - _circle_area(requested.diameter), axial)


def _f4(requested: Cylinder, envelope: Cylinder) -> Optional[_Match]:
    """F4 -- a cylinder out of a cylinder, in either of two orientations.

    Upright is a length parted off a bar. Crosswise is a rod sawn out of a disc,
    its axis lying in the disc's plane: it must fit within the thickness, and
    the L x D rectangle it occupies in plan must fit the circle. Centring on a
    diameter is optimal for a rectangle in a circle, so that condition is exact
    rather than merely sufficient.

    Crosswise takes `h x d` as its cross-section rather than a chord, which
    deliberately overstates the material removed and so ranks crosswise fits
    below upright ones. Sawing a rod out of a plate *is* more work than parting
    one off a bar, so the overstatement points the right way.
    """
    candidates = []

    if requested.diameter <= envelope.diameter and requested.height <= envelope.height:
        candidates.append((
            'round from round, upright',
            (envelope.diameter,),
            _circle_area(envelope.diameter),
            envelope.height,
        ))

    if (requested.diameter <= envelope.height
            and requested.diameter * requested.diameter
            + requested.height * requested.height
            <= envelope.diameter * envelope.diameter):
        candidates.append((
            'round from round, crosswise',
            (envelope.height, envelope.diameter),
            envelope.height * envelope.diameter,
            envelope.diameter,
        ))

    if not candidates:
        return None

    orientation, cross_section, area, axial = min(candidates, key=lambda c: c[2])
    return _Match(orientation, cross_section, (requested.diameter,),
                  area - _circle_area(requested.diameter), axial)


def _match(envelope: Envelope, requested: Envelope) -> Optional[_Match]:
    """Dispatch to the rule for this (request kind, envelope kind) pair.

    One rule per pair, four in all; each returns the orientation that removes
    the least material, or None if the piece does not fit in any orientation.
    """
    if isinstance(requested, Box):
        if isinstance(envelope, Box):
            return _f1(requested, envelope)
        return _f2(requested, envelope)

    if isinstance(envelope, Box):
        return _f3(requested, envelope)
    return _f4(requested, envelope)


def evaluate(envelope: Envelope, piece: RequestedPiece) -> Optional[Fit]:
    """Whether `piece` can be cut from `envelope`, and how closely it fits.

    Section 5, in order: nominal first, and an item that passes there is an
    exact fit. Only if that fails is the effective (tolerance-relaxed) request
    tried, and an item failing that too is not returned at all.
    """
    nominal = _match(envelope, _requested_solid(piece, None))
    if nominal is not None:
        return _fit(nominal, within_tolerance=False, tolerance_dimensions=())

    if not any(tolerance > ZERO for tolerance in piece.tolerances.values()):
        return None

    effective = _match(envelope, _requested_solid(piece, frozenset()))
    if effective is None:
        return None

    return _fit(effective, within_tolerance=True,
                tolerance_dimensions=_load_bearing(envelope, piece))


def _load_bearing(envelope: Envelope, piece: RequestedPiece) -> Tuple[str, ...]:
    """The dimensions whose tolerance the fit actually depended on (FR-018).

    Section 5.3: restore one tolerance to nominal, leave the rest relaxed, and
    see whether the fit survives. Where it does not, that dimension was
    load-bearing. Named as the operator sees it, so a round request reports
    `Diameter` rather than `width`.
    """
    named = []
    for name, tolerance in piece.tolerances.items():
        if tolerance <= ZERO:
            continue
        if _match(envelope, _requested_solid(piece, frozenset({name}))) is None:
            named.append(dimension_label(name))
    return tuple(named)


def _fit(match: _Match, within_tolerance: bool,
         tolerance_dimensions: Tuple[str, ...]) -> Fit:
    """Build the result the service and the route hand on."""
    return Fit(
        within_tolerance=within_tolerance,
        tolerance_dimensions=tolerance_dimensions,
        orientation=match.orientation,
        item_cross_section=match.item_cross_section,
        requested_cross_section=match.requested_cross_section,
        excess=_excess(match.item_cross_section, match.requested_cross_section),
        removed_area=match.removed_area,
        axial_extent=match.axial_extent,
    )


def sort_key(ja_id: str, fit: Fit):
    """The order results arrive in (fit-rules section 4), ascending on each term.

    1. Exact fits before tolerance-only ones. A tolerance-only match is stock
       *under* nominal, so it has the smaller cross-section and would otherwise
       sort straight to the top; the operator asked for nominal (D7).
    2. The cross-sectional area that becomes chips. Zero for an exact match, so
       an exact match is always first. Excess *length* is not counted as waste:
       cutting to length is a bandsaw operation and the remainder goes back on
       the shelf (D6).
    3. The envelope's extent along the part's axis -- use up a drop before
       cutting into a full-length bar.
    4. `ja_id`, because the three terms above can all tie and the same search
       over unchanged inventory must produce the same order (FR-020).
    """
    return (
        1 if fit.within_tolerance else 0,
        fit.removed_area,
        fit.axial_extent,
        ja_id,
    )
