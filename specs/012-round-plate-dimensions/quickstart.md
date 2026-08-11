# Quickstart: Round Plate Dimensions

**Feature**: `specs/012-round-plate-dimensions` | **Date**: 2026-08-10

How to run this feature and prove it works. Design detail lives in
[plan.md](./plan.md), [data-model.md](./data-model.md) and
[contracts/dimension-rules.md](./contracts/dimension-rules.md).

## Prerequisites

```bash
cd /home/jantman/scratch/rm_me/workshop-inventory-tracking
source venv/bin/activate
```

`nox` sessions pin Python 3.13. The system Python is 3.14, so pyenv's 3.13 must come first on
`PATH` or every session fails at creation. `nox -s lint` is red at baseline on pre-existing
flake8 E501s — it is advisory and not a gate, so do not read its failures as yours.

## Running the suites

```bash
nox -s tests                    # unit; sub-second, network blocked
nox -s e2e                      # Playwright; ~8m15s warm
nox -s screenshots_headless     # regenerates docs/images/screenshots/
nox -s screenshots_verify       # PNG validity, RGB/RGBA, <500KB
```

`nox -s e2e` outlasts the Bash tool's 10-minute clamp — **run it in the background** and
collect the result, rather than watching it time out. It selects `-m "e2e and not screenshot"`,
so it must leave the working tree clean; if `git status` is dirty afterwards, a screenshot test
leaked into the run.

Screenshots are not optional here. This feature touches `app/templates/**` and
`app/static/js/**`, which per the constitution obliges regenerating and committing them in the
same change. CI blocks merge on stale ones. The captures that will actually move are
`user-manual/add_item_form.png` and `user-manual/edit_item_form.png`, both of which show
requirement asterisks.

## Manual walkthrough

```bash
python app.py     # or however the dev server is normally started on this box
```

1. **Add Item → Type `Plate`, Shape `Round`.** Length must lose its `*`; Diameter and
   Thickness must carry one. The Width field must be labelled **Diameter**.
2. **Fill only Diameter and Thickness, submit.** The item is created. This is FR-001, and the
   whole of issue #85.
3. **Find it in the inventory list.** Its Dimensions cell must read as a disc — `⌀6" × 0.25"`
   — not `6" × 0.25"`, and not blank. The Length column shows `-`.
4. **Edit it and save unchanged.** Nothing is demanded. Clear the Thickness and save: refused,
   naming Thickness.
5. **Switch Type to `Bar` on the Add form** with only diameter and thickness entered. Length
   regains its `*` before you submit.
6. **Post a round plate with no thickness to the item API.** Refused with 400, the message
   naming Thickness. Before this feature it was accepted.

```bash
curl -sS -X POST http://localhost:5000/api/inventory/items \
  -H 'Content-Type: application/json' \
  -d '{"item_type":"Plate","shape":"Round","material":"Aluminum",
       "location":"Shelf A","width":"6"}'
# expect: 400, {"success": false, "error": "... Thickness"}
```

## What the new tests must cover

### Unit — `tests/unit/test_taxonomy.py` (new)

`app/taxonomy.py` has never had a test. Cover the two changed rows, the three rows whose
justification is load-bearing, and the reporting contract:

- Plate + Round and Sheet + Round require width and thickness, and **not** length.
- Plate + Rectangular, Plate + Square and Sheet + Rectangular still require all three.
- Threaded Rod + Round does **not** require width. Guarding this stops a future tidy-up from
  reintroducing `app/taxonomy.py:58`'s wrong row and breaking two e2e tests at a distance.
- Bar + Round requires length and width.
- Channel yields no requirements — the carried-forward gap, pinned so it is a decision rather
  than an accident.
- `validate_required_fields` returns **both** names when diameter and thickness are both
  missing, not just the first (FR-018).
- A round shape reports `width` as "Diameter"; a rectangular one reports it as "Width".

### Unit — `tests/unit/test_database.py` (changed)

- `validate()` accepts a Plate + Round with width and thickness and no length, and rejects one
  missing either. There is **no existing test for round-shape validation at all** —
  `test_validate_rectangular_item_requirements` (`:174`) is the closest, and it uses
  Plate + Rectangular.
- `display_name` for a length-less round plate includes its diameter and thickness. The
  existing `test_display_name_with_dimensions_round` (`:217`) covers a Bar and must keep
  passing.

### Unit — `tests/unit/test_routes.py` (changed)

- The JSON create path refuses a round plate with no thickness, 400, message naming it.
- It accepts one with diameter and thickness and no length.
- The existing 21 tests built on `_minimum_payload` (`:1347`, a Bar + Round with length and
  width) must stay green — they are the check that enforcement did not overreach.

### E2E — `tests/e2e/test_round_plate.py` (new)

**Wait conditions, named per the rule that they must be state and not duration:**

| Step | Wait on |
|---|---|
| Type and Shape selected | `expect(length_input).not_to_have_attribute('required', '')` and `expect(thickness_input).to_have_attribute('required', '')` — polls, unlike `get_attribute()` |
| Width relabelled | `expect(width_label).to_have_text('Diameter')` |
| Item submitted | `AddItemPage.submit_and_wait()`'s existing return value. **Check it** — it returns `False` when constraint validation refuses, and a caller that ignores it carries on as though the item exists and fails somewhere unrelated much later |
| Item appears in list | `expect(row).to_be_visible()` before any `count()` or `text_content()` on the table |
| Dimensions rendered | `expect(dimensions_cell).to_have_text('⌀6" × 0.25"')` — never `text_content()` against a JS-rendered table, which reads empty before it loads |

The negative assertions need the most care. "Length is not required" and "the item is absent"
both pass trivially against a form or a table that has not rendered. Establish the region with
an `expect()` first. Prefer a positive condition where one exists.

### E2E — `tests/e2e/test_dimensions_display.py` (changed)

Add a Plate + Round case to `DIMENSION_ITEMS` (`:25-107`) with **no length**, and its expected
rendering to `EXPECTED_DIMENSIONS` (`:110`) and `EXPECTED_LENGTH` (`:121`). There is no
Plate + Round item anywhere in the suite today, and no item with a missing length — which is
why `formatFullDimensions`'s missing ⌀ has gone unnoticed.

### E2E — `tests/e2e/pages/add_item_page.py` (changed)

- `fill_dimensions()` (`:101-110`) needs a `thickness=` parameter.
- **Delete `DIAMETER_INPUT = "#diameter"` (`:23`)** or point it at `#width`. It matches no
  element in any template, and `_fill_if_on_this_form` (`:93-99`) returns silently on
  `count() == 0` — so every `diameter=` argument in the suite has always set nothing. The four
  Channel tests (`test_add_item.py:600, 631, 658, 693`) look like they supply a thickness and
  do not. Seed items directly via `live_server.add_test_data([...])` unless the form is what is
  under test.

## Done when

- `nox -s tests` and `nox -s e2e` are green, and `git status` is clean after the e2e run.
- `nox -s screenshots_headless` has been run and the changed PNGs committed;
  `nox -s screenshots_verify` passes.
- A round plate can be added, edited, listed, searched and displayed with no length anywhere in
  the flow.
- The JSON item API refuses a round plate missing a diameter or a thickness, and names both
  when both are missing.
- `grep -rn "typeShapeRequirements" app/` returns nothing — the JavaScript copy of the rules
  is gone, not merely corrected. That is the check that this feature fixed the cause and not
  only the symptom.
