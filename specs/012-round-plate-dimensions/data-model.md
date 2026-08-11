# Data Model: Round Plate Dimensions

**Feature**: `specs/012-round-plate-dimensions` | **Date**: 2026-08-10

Phase 1 output. Two parts: the rules table this feature makes authoritative, and an inventory
of every path that reads a dimension, with what each does when a round plate has no length.

**Nothing here is a schema change.** No column is added, removed, retyped or made nullable —
`length` is already `Column(Numeric(10, 4), nullable=True)` (`app/database.py:42`) and the
`CheckConstraint`s at `:85-89` already read `X IS NULL OR X > 0`. There is no Alembic revision
in this feature. See research D8.

---

## 1. Entities

### Inventory item — unchanged

`InventoryItem` (`app/database.py:32-93`) and the `Dimensions` dataclass
(`app/models.py:296-389`) are untouched by this feature. Recorded dimensions remain:

| Field | Column | Meaning | Note |
|---|---|---|---|
| `length` | `Numeric(10,4)` | inches | Becomes optional for round Plate and Sheet |
| `width` | `Numeric(10,4)` | inches | **This is the diameter for any round item.** `Dimensions.diameter` is a property alias for it (`app/models.py:323-331`), and both forms already relabel it "Diameter" when Shape is Round |
| `thickness` | `Numeric(10,4)` | inches | Becomes required for round Plate and Sheet |
| `wall_thickness` | `Numeric(10,4)` | inches | Tubes only; not applicable to a solid plate |
| `weight` | `Numeric(10,2)` | pounds | Optional for every type and shape, unchanged |

`item_type` (`String(50)`, not null) and `shape` (`String(50)`, nullable) also stay as they
are. They are orthogonal fields; `Plate` + `Round` has always been a legal pair.

### Requirement rule — the thing this feature actually changes

A rule is a set of **form field names** that must be present for one (Type, Shape) pair. Field
names, not dimensions specifically, because Threaded Rod's rule includes its thread fields —
that is how `inventory-add.js` models it today and the behaviour has to be preserved.

Today `app/taxonomy.py`'s `TypeShapeCompatibility` carries `required_dimensions: List[str]`
keyed on **type alone**; `get_required_dimensions(item_type, shape)` (`:93-101`) takes a shape
only to use it as a compatibility gate and then ignores it. That structure cannot express "a
round plate differs from a rectangular plate", which is the whole of issue #85 — and is why
the rule ended up restated in JavaScript in the first place. The dataclass therefore gains
per-shape requirements.

---

## 2. The authoritative table

Seeded to reproduce today's **effective** behaviour — that is, `inventory-add.js:18-46`,
because it is the only one of the three statements that runs (research D1, D3). Exactly two
rows change. Optional fields are `weight` for every row, plus anything not listed as required.

| Type | Shape | Required | Changed? |
|---|---|---|---|
| Bar | Rectangular | length, width, thickness | |
| Bar | Round | length, width | |
| Bar | Square | length, width | |
| Bar | Hex | length, width | |
| **Plate** | **Round** | **width, thickness** | **← was length, width, thickness** |
| Plate | Rectangular | length, width, thickness | |
| Plate | Square | length, width, thickness | |
| **Sheet** | **Round** | **width, thickness** | **← was length, width, thickness** |
| Sheet | Rectangular | length, width, thickness | |
| Sheet | Square | length, width, thickness | |
| Tube | Round | length, width, wall_thickness | |
| Tube | Square | length, width, wall_thickness | |
| Tube | Rectangular | length, width, wall_thickness | |
| Threaded Rod | Round | length, thread_series, thread_size | |
| Angle | Rectangular | length, width, thickness | |
| Channel | Rectangular | *(none)* | carried forward — see below |
| Channel | Square | *(none)* | carried forward — see below |

**Three rows deserve their justification restated here, because getting any of them wrong
turns green tests red:**

- **Threaded Rod does not require width.** `app/taxonomy.py:58` claims `['length', 'width']`.
  It is wrong: `test_add_threaded_rod_with_proper_validation`
  (`tests/e2e/test_add_item.py:361`) asserts Width is *not* required, and
  `tests/e2e/test_field_autocomplete.py:25-50` seeds three threaded rods through the JSON API
  with no width at all. The JS row is the one that matches reality.
- **Bar + Round requires length and width.** `app/taxonomy.py:34` claims only `['length']`. The
  form requires both, and FR-006 says the server must agree with the form.
- **Channel requires nothing.** `ItemType.CHANNEL` is absent from the JS table entirely. All
  four Channel e2e tests (`tests/e2e/test_add_item.py:600, 631, 658, 693`) supply a length and
  a width and **no thickness**, so adopting `app/taxonomy.py:70`'s
  `['length', 'width', 'thickness']` fails all four. The spec puts Channel's missing rule out
  of scope, so the empty rule is carried forward and the gap stays visible.

**The one behaviour change outside round Plate and Sheet**: the Add form filters its Shape
dropdown from the keys of this table (`inventory-add.js:324-354`). Channel, being absent
today, offers all four shapes including Hex. Giving Channel rows — even empty ones — narrows
it to Rectangular and Square. Called out in the spec's Out of Scope; both Channel tests use
one of those two, so nothing breaks.

---

## 3. Validation rules

- A field named in a row's requirement set MUST be present and non-empty. "Present" means the
  same thing a blank form field and an omitted API key mean today: absent.
- Every missing field is reported, not the first (FR-018).
- Nothing else about a dimension is checked here. Positivity is already enforced by the
  database `CheckConstraint`s and by `validate()`'s existing loop; parseability is already
  enforced by `_parse_item_from_form` and the JSON coercion.
- The rule is applied at three call sites, all in `app/main/routes.py`, beside the
  `required_fields` checks already there (`:261`, `:660`): the Add POST, the Edit POST, and the
  JSON create path. **Not** in `InventoryService` — e2e fixtures seed through it
  (`tests/e2e/test_server.py:135-175`), and their default `item_type` is `'Rod'`, which is not
  even a member of `ItemType` (research D2).

State transitions: none. An item has no dimension-related lifecycle; this is a point-in-time
check at write.

---

## 4. Every path that reads a dimension

The question asked of each: **what does it do when a round plate has `length = NULL`?**

### Must be fixed

| Path | Behaviour | Why it matters |
|---|---|---|
| `app/database.py:248-265` `display_name` | **Renders no dimensions at all.** The whole block sits under `if self.length:` (`:257`). A round plate becomes `Steel Plate Round`. The ROUND branch (`:259`) is also `⌀{width}" × {length}"` with no thickness term, so even a round plate that *has* a length loses its thickness | Reaches five API payloads (`routes.py:39, 1435, 1478, 1858, 2079`) and every screen showing an item's name — list, search, history, shorten. Violates FR-013 |
| `app/static/js/components/item-formatters.js:61` | The `width && thickness` branch **never emits ⌀**. A round plate renders `6" × 0.25"`, identical to a rectangular one. The only branch that emits ⌀ is `:68`, reached when width is present *without* thickness | Violates FR-014. Already wrong today, independent of this feature |
| `app/database.py:210-236` `validate()` | Shape-keyed and type-blind. Requires length for every round item, and requires thickness for none | Delegates to the table instead (research D1) |
| `app/taxonomy.py:38-49` | `required_dimensions` cannot vary by shape | The structural blocker |
| `app/static/js/inventory-add.js:28, 33` | `Plate.Round` and `Sheet.Round` require length | Deleted along with the rest of the literal |
| `app/templates/inventory/edit.html:167, 179, 458, 461` | `Length *` and `Width *` are hard-coded label text; no dimension input carries `required`; Thickness is never marked. The form does gate on `checkValidity()` (`:756-769`) — there is simply nothing for it to catch | Violates FR-007 |

### Safe as they stand — verified, not assumed

| Path | Behaviour with NULL length |
|---|---|
| `app/database.py:577-600` `to_dict`, `app/models.py:366-379` `Dimensions.to_dict` | Each field `None`-guarded. Emit no `diameter` key — see the dead-read note below |
| `app/main/routes.py:914-929` `formatted_dimensions` | Each key added only `if dimensions.X` |
| `item-formatters.js:96-106` `formatDimensions` (the Length column) | Falls back to a muted `-` |
| `inventory-search.js:611-648`, `inventory-list.js:930-1003` (detail modals) | Every row guarded |
| `history-viewer.js:203-215` | Guarded; renders `W: 12", T: 0.25"`. Mislabels the diameter as `W:`, which is pre-existing and cosmetic |
| `inventory-shorten.js:192`, `app/main/routes.py:2153-2159` | Both **correctly refuse** to shorten an item with no length. A round plate cannot be shortened, which is right |
| `app/export_schemas.py:117` | `format_decimal(None)` → `""`; the Sheets export column is simply blank |
| `app/services/label_printer.py` | Renders no dimensions at all. Labels are unaffected |
| `app/main/routes.py:797-805`, `mariadb_inventory_service.py:825-998` (duplicate/copy) | All `float(x) if x else None` |
| `app/main/routes.py:2026-2035` (form parsing) | Sets a dimension only `if value:`; a blank Length is simply not set |
| `mariadb_inventory_service.py:360-364` (length-range search) | SQL comparison against NULL is UNKNOWN, so a round plate is **excluded from a length-range filter**. Correct, and stated as an edge case in the spec |
| `inventory-table.js:166-170` (client sort) | `|| 0` fallback; length-less rows sort as zero |

### Latent, listed in the plan's known gaps

`mariadb_inventory_service.py:500` — `if current_db_item.length and new_length >= ...`
short-circuits, so a length-less item passes the "must be shorter" check and is *assigned* a
length. Unreachable through the UI or the API because both guards above refuse first, but
round plates make NULL length ordinary rather than exotic.

### Dead reads — pre-existing, not created here

`inventory-search.js:647` and `history-viewer.js:210-212` render `dimensions.diameter`,
`inner_diameter` and `outer_diameter`. No serializer emits any of the three, so those branches
have never executed. Left alone: FR-014 is satisfied where the ⌀ is fixed, and rewiring these
modals is not what issue #85 asks for.

Its exact counterpart in the test suite is `AddItemPage.DIAMETER_INPUT = "#diameter"`
(`tests/e2e/pages/add_item_page.py:23`), which matches no element in any template and no-ops
silently through `_fill_if_on_this_form` (`:93-99`). That one **must** go, because this is the
first feature to care what a round item's diameter field is called, and a test that appears to
set a diameter while setting nothing is the same class of defect the feature exists to fix.
