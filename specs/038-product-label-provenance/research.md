# Phase 0 Research: Product label provenance

Five decisions. Each records what was chosen, why, and what was rejected. None required a
blocking question to the user; the issue text supplied enough to choose, and the choices it left
open are recorded in the spec's Assumptions section.

---

## Decision 1 — Two provenance lines, identity first

**Decision**: Provenance becomes up to two lines. Line 1 is identity — manufacturer and
manufacturer part number. Line 2 is the purchase — vendor, order date, unit price. Either line may
be absent independently; when both are absent there is no provenance band at all.

**Rationale**:

- The issue offers "a second provenance line, or a reflowed single one" and does not pick.
- Two short lines fit at a **larger** type size than one long line, because the fitted font is
  bounded by the widest line's width. `MEAN WELL  IRM-05-5  Amazon  2026-01-14  $6.50 ea` on a
  610px-wide Sato 1x2 would be fitted down toward the 10px floor; split in two, each half fits at
  roughly double that. On a direct-thermal label that will be read in five years, type size is
  durability.
- Grouping by question is what a reader actually does with the label: "what is this" (identity)
  and "where did it come from" (purchase). Interleaving them into one run of six two-space-separated
  fields makes `IRM-05-5  Amazon` read as one thought.
- Identity goes first because the issue's own argument puts it first: once the bag is open and the
  box is gone, the manufacturer and part number are what identify the thing, and the eye reaching
  down from the description finds them before the order details.

**Alternatives considered**:

- *One reflowed line.* Rejected: smaller type on the stock where legibility is already tightest,
  and it reads as one undifferentiated run.
- *Three lines (manufacturer, part number, purchase).* Rejected: costs a third of the description
  band to separate two fields that belong together and are short.
- *Dropping the order date to make room on one line.* Rejected: the issue muses that identity is
  "arguably more useful than the order date" but does not ask for the date's removal, and removing
  information already on a label is a different decision from adding some. Recorded as an
  assumption in the spec.

---

## Decision 2 — The second line is paid for out of the description, never the code

**Decision**: The space above the code band is a fixed budget of
`DESCRIPTION_BAND + PROVENANCE_BAND` (0.38 + 0.14 = 0.52 of the panel height) whenever any
provenance exists. Provenance takes `PROVENANCE_BAND` per line out of that budget and the
description gets the remainder. The code band gets whatever is left over, which is a constant
0.48 for one *or* two provenance lines.

| Case | Description | Provenance | Code |
|------|-------------|-----------|------|
| No provenance (today, and after) | 0.38 | 0.00 | 0.62 |
| One line (today, and after) | 0.38 | 0.14 | 0.48 |
| Two lines (after only) | 0.24 | 0.28 | 0.48 |

**Rationale**: This is FR-006, which restates the module's own FR-012 — the human-readable code is
what keeps a scuffed label usable and is never traded for space; the description truncates first.
The naive change (add 0.14 for the second line, let the code band absorb it) would take the code
from 0.48 to 0.34, which is exactly the regression the issue asks to be avoided.

The arithmetic was chosen so that the one-line and zero-line cases reduce to today's numbers
*identically*, not merely closely. That is what makes SC-006 ("byte-for-byte identical") a real
assertion: a product with no manufacturer, no part number and no purchase composes through
precisely the code path and precisely the pixel budget it does today.

**Alternatives considered**:

- *Give each provenance line half of `PROVENANCE_BAND`.* Rejected: it holds the code band constant
  but halves the type size of both lines, undoing the main benefit of Decision 1 and making a
  two-line label less legible than the one-line label it replaces.
- *Grow the label.* Rejected outright — the stock dimensions come from `LABEL_TYPES` and are
  physical.
- *Shrink the barcode but not its text.* Rejected: a narrower symbol is a less forgiving one after
  a year on a shelf, which the module's `_paste_code` comment already argues at length.

**Consequence to verify**: on the narrowest stock (`Sato 1x2`, 305px panel height) the two-line
case leaves the description 73px, about four lines at the 14px floor. That is a real reduction and
it is the intended trade — the modal's help text already tells the operator that the description is
what gets shortened on the narrowest stock.

---

## Decision 3 — `format_provenance` takes strings, not a `Product`, and returns a list

**Decision**:

```python
def format_provenance(purchase, manufacturer=None, part_number=None) -> List[str]
```

returning `[]`, `[identity]`, `[purchase]`, or `[identity, purchase]`. `compose_product_label` and
`print_product_label` rename their `provenance: Optional[str]` parameter to
`provenance_lines: Optional[Sequence[str]]`.

**Rationale**:

- **Strings, not the ORM object**, because Constitution II keeps ORM types out of the service
  composition layer, and because the route already passes `description` and `code` as plain values
  for the same reason. Passing `product` would be the only ORM object crossing that boundary.
- **`purchase` stays first and positional** so the existing unit tests' positional call style keeps
  working, and because a purchase is still the source of most of the content.
- **A rename, not a widened type**, on the composition parameters. `provenance: Optional[str]`
  quietly accepting a list — or worse, `provenance: Optional[Sequence[str]]` quietly accepting a
  `str` and drawing one line per character, since `str` is a `Sequence[str]` — is a trap. Renaming
  to `provenance_lines` makes every call site fail loudly at review time rather than silently at
  print time.
- **A list rather than an embedded `\n`**, because the drawing code must fit a font per line and
  measure each line's width; a string carrying newlines would just be split back apart at the top
  of `_draw_provenance`.

**Alternatives considered**:

- *A new `format_identity()` alongside the existing `format_provenance()`, with the caller
  assembling the list.* Rejected: it pushes the "which lines exist" decision up into the route,
  which is exactly the business logic the route is supposed to stay thin of.
- *A small `ProvenanceLines` dataclass.* Rejected under Constitution I — a two-element list needs
  no type.
- *Keeping the single-string signature and joining the two lines with a wide separator.* Rejected:
  that is Decision 1's rejected alternative wearing a different hat.

---

## Decision 4 — `ea` as the per-unit marker

**Decision**: `f"${purchase.unit_price} ea"`. Applied at string-formatting time, appended to the
existing `str(Decimal)` rendering.

**Rationale**: The issue proposes it, it is three characters, and `ea` is already the convention on
the purchase screens so the label agrees with the app. Critically, it is applied **after** `str()`
on the `Decimal` — the price is never the operand of an arithmetic operation anywhere in this path,
so Constitution III is satisfied by construction rather than by care. The existing test
`test_the_price_never_passes_through_a_float` is extended rather than replaced, so that property
stays asserted.

A zero price prints as `$0.00 ea` — zero is a recorded price, not a missing one, and the existing
code already distinguishes `None` from `Decimal('0')` by testing `is not None`.

**Alternatives considered**:

- *`$6.50/ea`, `$6.50 each`, `@ $6.50`.* Rejected: longer for no gain, and `/` invites reading the
  figure as a rate over something.
- *Printing the extended price (`$32.50 for 5`) instead.* Rejected: the label is printed once and
  the bag's contents change as parts are used, so an extended total goes stale in a way a unit price
  does not. The issue asks for the ambiguity removed, not for a different number.

---

## Decision 5 — `label_count` validation is duplicated, not extracted

**Decision**: `api_print_product_label` validates `label_count` inline, with the same rules and the
same messages as `app/main/routes.py` uses for item labels: a whole number (explicitly rejecting
`bool`, which is an `int` in Python), between 1 and 99 inclusive, defaulting to 1 when absent.
The JSON field is named `label_count` to match the item endpoint; it is passed to
`print_product_label`'s existing `num_copies` parameter.

**Rationale**: Extracting a shared validator would mean editing a second blueprint that this issue
does not concern, to deduplicate eight lines. Constitution I's test is "is this the simplest thing
that works", and the smaller blast radius wins: the item label path keeps working exactly as it
does today, and a reviewer reading the product route sees the rule rather than a jump to a helper.
This is recorded here so that the duplication reads as a decision rather than an oversight.

The `bool` exclusion is not pedantry inherited by copying — `json.loads` yields real `bool`s, and
`isinstance(True, int)` is `True`, so without the check `{"label_count": true}` prints one label
while claiming to be validated.

**Alternatives considered**:

- *`validate_label_count()` in `app/services/label_printer.py`.* Both routes already import from
  that module, so it would be a natural home. Rejected for scope, not for shape — if a third caller
  ever appears, that is where it should go.
- *Reusing the item endpoint.* Rejected: it prints a JA-ID barcode label, which is a different
  label from a different record.
- *No validation, clamping instead.* Rejected: silently printing 99 labels because someone typed
  999 wastes a roll, and the item path already refuses rather than clamps.
