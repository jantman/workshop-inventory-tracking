# Contract: Envelope Derivation and Fit Rules

**Feature**: [../spec.md](../spec.md) | **Decisions**: [../research.md](../research.md) D2, D3, D4, D6, D7, D8

This is the normative statement of the geometry. `app/utils/fit.py` implements exactly this
table and nothing beyond it; `tests/unit/test_fit.py` enumerates it.

All quantities are `decimal.Decimal`. No `float` appears anywhere in this contract, and no
square root is taken (D4).

---

## 1. Envelope derivation

An inventory row becomes one of two solids, or becomes non-evaluable. The rules are applied
in order; the first that matches wins.

| # | Condition | Envelope | Reason |
|---|---|---|---|
| E1 | `wall_thickness` is recorded | *none* — **hollow** | The recorded outside dimensions describe a shell, not a solid (FR-010). |
| E2 | `shape` is `Round` **and** `item_type` is `Plate` or `Sheet` | `Cylinder(diameter = width, height = thickness)` | A disc. `width` is the diameter and `thickness` is how thick the disc is — the rule `specs/012-round-plate-dimensions/` established (`app/taxonomy.py:73-84`). A stale `length` on such a row is ignored, not used as the height. |
| E3 | `shape` is `Round` or `Hex` | `Cylinder(diameter = width, height = length)` | A bar. For `Hex`, `width` is the across-flats measurement, so the cylinder is the circle **inscribed** in the flats — conservative by design (D2). |
| E4 | `shape` is `Square` **and** `thickness` is not recorded | `Box(length, width, width)` | A square prism: `Bar`/`Square` requires only `length` and `width` (`app/taxonomy.py:63-67`), the second cross-section dimension being equal to the first. |
| E5 | otherwise | `Box(length, width, thickness)` | Rectangular and square plate and sheet; rectangular bar; and one leg of an `Angle` or one wall of a `Channel` — see note below. |
| E6 | any field the chosen rule needs is `NULL` | *none* — **incomplete** | FR-011. Counted and reported, never silently dropped. |

**Angle and Channel.** E5 gives an `Angle` the solid `Box(length, width, thickness)`, which
is one leg of the L — the material genuinely there as a solid rectangular strip. The second
leg is not counted. The same reading applies to a `Channel`, whose taxonomy entry requires
no fields at all (`app/taxonomy.py:110-116`), so most channel rows will fall to E6.

**Threaded rod.** `Threaded Rod`/`Round` requires `length`, `thread_series` and
`thread_size` and no `width` (`app/taxonomy.py:96-101`). A row that happens to record a
`width` evaluates under E3 — you can turn a part from a threaded rod. A row that does not
falls to E6. There is no type-specific exclusion; the field-driven rule is the whole rule.

### Envelope by declared type and shape

Every combination `TypeShapeValidator` declares compatible, with the rule that fires. The
test in D3 walks this table.

| Type | Shape | Required fields (taxonomy) | Rule | Envelope |
|---|---|---|---|---|
| Bar | Rectangular | length, width, thickness | E5 | `Box(length, width, thickness)` |
| Bar | Round | length, width | E3 | `Cylinder(width, length)` |
| Bar | Square | length, width | E4 | `Box(length, width, width)` |
| Bar | Hex | length, width | E3 | `Cylinder(width, length)` — inscribed |
| Plate | Rectangular | length, width, thickness | E5 | `Box(length, width, thickness)` |
| Plate | Square | length, width, thickness | E5 | `Box(length, width, thickness)` |
| Plate | Round | width, thickness | E2 | `Cylinder(width, thickness)` |
| Sheet | Rectangular | length, width, thickness | E5 | `Box(length, width, thickness)` |
| Sheet | Square | length, width, thickness | E5 | `Box(length, width, thickness)` |
| Sheet | Round | width, thickness | E2 | `Cylinder(width, thickness)` |
| Tube | Round, Square, Rectangular | length, width, wall_thickness | E1 | hollow — excluded |
| Threaded Rod | Round | length, thread_series, thread_size | E3 or E6 | `Cylinder(width, length)` if a width is recorded |
| Angle | Rectangular | length, width, thickness | E5 | `Box(length, width, thickness)` — one leg |
| Channel | Rectangular, Square | *(none)* | E5 or E6 | `Box(...)` only if all three are recorded |

---

## 2. The requested piece

| Shape | Dimensions | Solid |
|---|---|---|
| `Rectangular` | length, width, thickness | `Box(length, width, thickness)` |
| `Round` | diameter, length | `Cylinder(diameter, length)` |

Every dimension may carry a tolerance. The **effective** value of a dimension is
`nominal − tolerance`; with no tolerance the effective value is the nominal one (FR-015).

---

## 3. Fit rules

Four rules, one per (request kind, envelope kind). Each returns whether the piece fits and,
when it does, the orientation that fits best — the one with the smallest cross-section, which
is the one that removes the least material (D6).

Write `PI = Decimal('3.14159265359')`, the constant `Dimensions.volume()` already uses in
`app/models.py`. It appears **only** in the sort key (§4), never in a displayed measurement.

### F1 — Box into Box

Sort the request `p ≥ q ≥ r` and the envelope `a ≥ b ≥ c`.

> **Fits** iff `p ≤ a` and `q ≤ b` and `r ≤ c`.

Orientation: the part's axis lies along `a`. Envelope cross-section `b × c`; requested
cross-section `q × r`. Sorted assignment leaves the two smallest envelope dimensions as the
cross-section, so it is the minimising orientation — no search over permutations is needed.

### F2 — Box into Cylinder(d, h)

For each of the three choices of which request dimension `x` is axial, leaving `y` and `z`:

> **Fits** iff `x ≤ h` and `y² + z² ≤ d²`.

The rectangle `y × z` is inscribed in the circle of diameter `d`; comparing squares avoids
the square root (D4). Envelope cross-section is the circle; requested cross-section is
`y × z`. Where more than one choice fits, take the one with the largest `y · z`.

This one rule covers the disc-yields-a-strip case: a Ø6" × 0.25" plate yields a
0.2" × 1" × 5" bar with `x = 0.2` axial, because `1² + 5² = 26 ≤ 36`.

### F3 — Cylinder(D, L) into Box(a, b, c)

For each of the three axes `i`:

> **Fits** iff `dim_i ≥ L` and both remaining dimensions `≥ D`.

Envelope cross-section is the product of the two remaining dimensions; requested
cross-section is the circle of diameter `D`. Where more than one axis fits, take the one
with the smallest remaining product.

### F4 — Cylinder(D, L) into Cylinder(d, h)

Two orientations:

> **Upright** — fits iff `D ≤ d` and `L ≤ h`. Cross-section: the circle of diameter `d`.
>
> **Crosswise** — fits iff `D ≤ h` and `D² + L² ≤ d²`. Cross-section: `h × d`.

Crosswise is the rod sawn out of a disc, its axis lying in the disc's plane: it must fit
within the thickness (`D ≤ h`), and the `L × D` rectangle it occupies in plan must fit the
circle of diameter `d`. Centring on a diameter is optimal for a rectangle in a circle, so
the condition is exact, not merely sufficient.

Using `h × d` rather than a chord for the crosswise cross-section deliberately overstates
the material removed, which ranks crosswise fits below upright ones. Sawing a rod out of a
plate *is* more work than parting one off a bar, so the overstatement points the right way.

Where both orientations fit, take the smaller cross-section.

---

## 4. Ordering (D6, D7)

Every returned item carries a sort key, ascending on each term in turn:

| # | Term | Why |
|---|---|---|
| 1 | `0` if the item fits at nominal, `1` if it fits only within tolerance | A tolerance-only match is stock **under** nominal, so it has the smaller cross-section and would otherwise sort first. The operator asked for nominal (FR-018 makes the distinction visible; this makes it matter). |
| 2 | envelope cross-section area − requested cross-section area, in the winning orientation | The material that becomes chips (D6). Zero for an exact match, so an exact match is always first (Story 3, scenario 4). |
| 3 | the envelope's extent along the part's axis | Use up a drop before cutting into a full-length bar. |
| 4 | `ja_id` ascending | FR-020: the same search over unchanged inventory produces the same order. The three terms above can all tie. |

Term 2 is the only place `PI` is used. It is a comparison figure, not a measurement.

---

## 5. Tolerance evaluation and attribution (D8)

1. Run the fit rules with every dimension at its **nominal** value. If it fits, the result is
   an exact fit; stop.
2. Run them again with every dimension at its **effective** value. If it does not fit, the
   item is not returned.
3. It fits within tolerance. For each dimension carrying a non-zero tolerance, run the rules
   once more with **that one** dimension restored to nominal and the others effective. If the
   fit fails, that dimension is load-bearing and is named in the result (FR-018).

At most five evaluations of a function that performs a dozen `Decimal` comparisons.

---

## 6. What each result reports (FR-021, FR-022)

| Field | Content | Exactness |
|---|---|---|
| the item's own dimensions | as recorded, unchanged | exact — this is the existing Dimensions column |
| envelope cross-section | the two figures (or the diameter) in the winning orientation | exact |
| requested cross-section | the same, for the request | exact |
| excess per cross-section dimension | envelope figure − requested figure | exact `Decimal` subtraction |
| within-tolerance marker | absent, or the names of the load-bearing dimensions from §5.3 | — |

No area figure is shown. The area exists to order the list, and showing an approximation of
it would put a `PI`-derived number in front of a machinist for no gain.
