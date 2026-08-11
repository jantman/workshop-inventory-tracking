# Contract: Dimension Requirement Rules

**Feature**: `specs/012-round-plate-dimensions` | **Date**: 2026-08-10

Three interfaces carry this feature. Two exist today and change; one is new and internal to
the page. The rules table itself is in [../data-model.md](../data-model.md) §2 and is not
repeated here.

---

## C1: `app/taxonomy.py` — the Python surface

The module already exposes `type_shape_validator`, a singleton `TypeShapeValidator`. Its
existing methods keep their names and their meanings:

| Method | Change |
|---|---|
| `is_shape_compatible_with_type(item_type, shape)` | Unchanged in behaviour. Its answer is now derived from the same per-shape table |
| `get_compatible_shapes(item_type)` | Unchanged in behaviour |
| `validate_type_shape_combination(item_type, shape)` | Unchanged |
| `get_required_dimensions(item_type, shape)` | **Behaviour change**: now varies by shape. Previously took `shape` only as a compatibility gate and returned the type-level list regardless (`app/taxonomy.py:93-101`) |
| `get_optional_dimensions(item_type, shape)` | Unchanged — `['weight']` throughout |

One method is added:

```python
def validate_required_fields(
    item_type: ItemType,
    shape: ItemShape,
    values: Mapping[str, Any],
) -> List[str]:
    """Return a human-readable message for every required field missing from `values`.

    Empty list means the item satisfies the rules for its type and shape.
    """
```

- `values` is keyed by form field name — `length`, `width`, `thickness`, `wall_thickness`,
  `thread_series`, `thread_size`. A key that is absent, `None`, or an empty/whitespace string
  counts as missing; they are indistinguishable today and stay so.
- **Every** missing field produces a message. Returning after the first would violate FR-018.
- Messages name the dimension as the operator sees it. For a round shape, `width` is reported
  as **Diameter**, matching the label on both forms and the wording
  `app/database.py:230` already uses.
- An incompatible (type, shape) pair is not this method's business — `validate_type_shape_combination`
  answers that, and the write paths do not call it (enforcing compatibility is out of scope).
- A pair with no rule — Channel, today — yields an empty list. Silence, not an error.

`InventoryItem.validate()` (`app/database.py:190-245`) keeps its signature and its contract
of returning a list of message strings. Its dimension branch (`:210-236`) is replaced by a call
to the above. Its JA-ID, material, item-type and positive-value checks are untouched.

---

## C2: The item write paths — what a refusal looks like

Applies to all three call sites in `app/main/routes.py`: the Add POST, the Edit POST, and the
JSON create path. The rule is applied **after** the existing `required_fields` check
(`:261`, `:660`) and after dimension parsing, so an unparseable dimension still reports as one.

### JSON API — `POST /api/inventory/items`

Refusal reuses the existing failure shape exactly. No new status code, no new envelope:

```
HTTP 400
{
  "success": false,
  "error": "Missing required field(s) for Plate/Round: Thickness"
}
```

Multiple missing fields are listed in one message, in the order the rule declares them:

```
{
  "success": false,
  "error": "Missing required field(s) for Plate/Round: Diameter, Thickness"
}
```

This matches how the existing required-field failure is asserted in the suite —
`tests/unit/test_routes.py:1408-1415` checks that the field name appears *within*
`data['error']`, not that the message equals anything. Bulk creation (`quantity_to_create`)
refuses the whole request, as it already does for a missing `location`: the payload describes
one item repeated, so it is either valid or it is not.

**Compatibility note.** This is a new refusal on a path that previously accepted anything. The
spec records it (FR-017, SC-008) and the operator accepted it. Verified against the payloads
the suite actually sends: `_minimum_payload` (`tests/unit/test_routes.py:1347`) is a Bar+Round
with length and width, and `tests/e2e/test_field_autocomplete.py:25-50` sends Threaded Rods
with length and thread fields. Both satisfy their rows.

### Add and Edit forms

Refusal uses whatever the surrounding handler already does for a missing `required_field` —
the same flash-and-re-render, with the item's entered values preserved. No new error mechanism
is introduced; the constitution's error-handling constraint bars building one.

In practice the operator rarely sees this: the browser refuses first, because the shared module
(C3) sets `required` on the same fields. The server check is the backstop that makes FR-017
true, and the thing that catches an edit submitted from a stale page.

---

## C3: The rules table as seen by the browser

The Add and Edit views pass the table to their templates, which render it into the page as a
JSON constant. No fetch — see research D4.

```html
<script id="type-shape-requirements" type="application/json">
  {"Bar": {"Rectangular": ["length","width","thickness"],
           "Round": ["length","width"], ...},
   "Plate": {"Rectangular": ["length","width","thickness"],
             "Square": ["length","width","thickness"],
             "Round": ["width","thickness"]}, ...}
</script>
```

`app/static/js/dimension-requirements.js` reads it and owns four behaviours on both forms:

1. **Requirement marks and enforcement.** Clear `required` and hide every `.dimension-required`
   indicator, then set and show them for the current (Type, Shape). This is what
   `updateDimensionRequirements()` (`inventory-add.js:280-322`) does today; it moves here
   unchanged in substance, and the Edit form gains it for the first time.
2. **Diameter labelling.** Width's label reads `Diameter` when Shape is Round and `Width`
   otherwise — today's `updateWidthLabel()` (`inventory-add.js:356-366`). The Edit form's
   variant bakes the asterisk into the string (`edit.html:458-461`); it must not, because the
   asterisk is now driven by the requirement mark.
3. **Shape filtering.** Hide Shape options the current Type has no row for, clearing the
   selection if it becomes invalid — today's `updateShapeOptions()` (`inventory-add.js:324-354`).
4. **Nothing else.** The module does not submit, does not fetch, and does not know about
   threading sections, carry-forward, barcode scanning or photos. Those stay where they are.

The Edit form's `#required-dimensions-info` / `#required-dimensions-text`
(`edit.html:160-162`) are dead — nothing in the repository writes to them. Either drive them
from this module or delete them; leaving a third state (present, empty, unexplained) is the
one option to avoid.

### What the front end must not do

Restate the table. The literal at `inventory-add.js:18-46` is deleted, not copied. If a rule
needs to change after this feature, `app/taxonomy.py` must be the only file that has to.
