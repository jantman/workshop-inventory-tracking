# Phase 0 Research: Stock Fit Search

**Feature**: [spec.md](./spec.md) | **Date**: 2026-08-24

Fourteen decisions. Each records what was observed in the code or the constitution that
settled it, because the alternatives here are not obviously wrong and a later reader will
want to know why they were not taken.

---

## D1 — The fit test is a pure module in `app/utils/`, not a service and not a query

**Decision**: The geometry lives in a new `app/utils/fit.py`: pure functions over `Decimal`,
importing only `app/models.py` enums. It knows nothing about Flask, SQLAlchemy or storage.

**Rationale**: `app/utils/` already holds exactly this kind of module — `scan_router.py` is
described in its own docstring as "the pure classifier", and `gtin.py`, `ecia.py` and
`gs1.py` are the same shape. Constitution Principle II puts business logic in services and
domain rules in domain modules; a containment test between two solids is neither a service
concern nor a persistence concern, and it is the only part of this feature that genuinely
needs exhaustive testing. Pure and import-free means those tests run in the sub-second unit
suite with no fixtures.

**Alternatives considered**:

- *Put it in `app/mariadb_inventory_service.py`.* The service is already 1,100+ lines and
  every test of the geometry would need a database session. Rejected.
- *Put it in `app/taxonomy.py`.* Tempting, since taxonomy owns type/shape knowledge — but
  taxonomy states *what a record must contain*, and this states *what solid the record
  describes*. Merging them would make one module answer two questions, which is how
  `specs/012-round-plate-dimensions/` got three disagreeing rule tables in the first place.
  D3 below keeps them honest without merging them.
- *Express the fit test in SQL.* See D5.

---

## D2 — Two envelope kinds are enough: a box and a cylinder

**Decision**: Every evaluable item reduces to one of two solids — `Box(a, b, c)` or
`Cylinder(diameter, height)`. The full per-(type, shape) mapping is in
[contracts/fit-rules.md](./contracts/fit-rules.md) and repeated with sources in
[data-model.md](./data-model.md).

**Rationale**: The seven `ItemType`s and four `ItemShape`s in `app/models.py:81-97` produce
far fewer distinct solids than the product suggests. A square bar is a box whose two
cross-section dimensions are equal. A hex bar, taken at the circle inscribed in its flats,
is a cylinder. A round plate — the disc that `specs/012-round-plate-dimensions/` established
records a `width` and a `thickness` and no `length` — is a cylinder standing on end. Two
kinds means four fit rules total (D4), which is a table a person can read and a test can
enumerate.

**Alternatives considered**:

- *One kind — the bounding box of everything.* Would report that a Ø2" round bar can yield a
  2"×2" square, which it cannot. FR-006 says an item must not be returned when the piece
  cannot be made from it; a bounding-box-only model breaks that in the most common case in
  the inventory. Rejected.
- *A kind per shape, including a hexagonal prism.* The extra fidelity buys the operator the
  corners of a hex bar. The inscribed circle is conservative — it can only fail to return an
  item, never return an unusable one — and the corners of a hex are not where parts come
  from. Rejected under Principle I.

---

## D3 — `fit.py` and `taxonomy.py` are kept in agreement by a test, not by a shared table

**Decision**: `app/utils/fit.py` carries its own (type, shape) → envelope table. A unit test
walks every combination `TypeShapeValidator` declares compatible and asserts that `fit.py`
either builds an envelope from exactly the fields taxonomy requires for that combination, or
declares the combination non-evaluable — never reads a field taxonomy does not require, and
never silently returns nothing for a combination taxonomy does describe.

**Rationale**: This is the lesson of feature 012, which spent most of its budget collapsing
three rule tables that had drifted apart. Two tables that must agree is one more than ideal;
the difference here is that they answer different questions and a mechanical test can check
the agreement, which is not true of the three tables 012 found. The test fails the moment
someone adds an `ItemType` or changes a requirement without teaching `fit.py` about it.

**Alternatives considered**:

- *Derive the envelope from the required-fields list alone.* It nearly works — but `PLATE`
  and `SHEET` with `ItemShape.SQUARE` require `length, width, thickness`
  (`app/taxonomy.py:73-84`), the same three fields as `RECTANGULAR`, while `BAR` with
  `SQUARE` requires only `length, width` and means a square prism. The field list does not
  determine the solid. Rejected on the facts.

---

## D4 — Four fit rules, all comparing squares; no square root, no `float`

**Decision**: The rules are box-in-box, box-in-cylinder, cylinder-in-box and
cylinder-in-cylinder. Where a diagonal is involved, the comparison is made between squared
quantities — a rectangle `y × z` fits a circle of diameter `d` when `y² + z² ≤ d²` — so no
square root is ever taken.

**Rationale**: Constitution Principle III prohibits `float` for any measured quantity,
including "in parsing, display formatting, comparison, and search filters". `Decimal` has no
exact square root, and `math.sqrt` would introduce exactly the binary floating point the
principle exists to keep out of a machinist's inventory. Squaring a `Decimal` is exact, and
the inequality is equivalent for non-negative values. This costs nothing and removes the
question entirely.

**Alternatives considered**:

- *`Decimal.sqrt()` with a context precision.* Correct to the set precision and still a
  rounding step in the middle of a comparison that does not need one. Rejected.
- *Compare in `float` "just for the search".* Directly prohibited by Principle III, and the
  prohibition names search filters specifically. Rejected.

---

## D5 — Narrow in SQL by material and active; decide fit in Python

**Decision**: The service issues one query — active rows whose material is in the
hierarchical descendant list — and evaluates every candidate in Python. No dimension
predicate goes into SQL.

**Rationale**: The fit test is orientation-agnostic across two solid kinds; there is no
column-to-column comparison that expresses it, and the four rules would become a wall of
`OR`ed `CASE` expressions that no one could verify. Meanwhile Principle I forbids optimizing
without a measurement: this is one workshop's inventory, the existing search already loads
every matching row into Python (`app/mariadb_inventory_service.py:399`), and the material
filter alone cuts the candidate set to a fraction. If it is ever slow, that is a measurement
and a reason to revisit — and the plain version is the one to measure against.

**Alternatives considered**:

- *Push a cheap pre-filter into SQL* — e.g. `greatest(length, width, thickness) >= smallest
  requested dimension`. It is a correct narrowing, but it adds a second place where the fit
  rules are stated, and the two would drift exactly as D3 warns. Rejected until measured.
- *Reuse `search_active_items` with new filter keys.* That method's contract is per-field
  ranges (`:359-385`); adding orientation-free matching to it would change the meaning of
  existing keys and put FR-026 at risk. A separate service method instead — D9.

---

## D6 — "Closest fit" is measured as material removed, not as the item's leftover volume

**Decision**: Results are ordered by the cross-sectional area the operator must machine away
in the orientation that fits, ascending. The item's excess *length* is not counted as waste.
The full ordering key is in [contracts/fit-rules.md](./contracts/fit-rules.md).

**Rationale**: This is an interpretation of FR-019 ("how little material is left over once
the requested piece is taken from the item") and it deserves to be stated rather than
assumed. Read as *the item's whole volume minus the piece*, a 12" length of Ø2" bar scores
terribly for a 2" job and a Ø2.5" two-inch stub scores well — so the search would recommend
consuming a stub and turning 0.5" off it rather than cutting 2" off a bar of the right
diameter. That is backwards: cutting to length is a bandsaw operation and the remainder goes
back on the shelf, unconsumed. What is actually lost is what becomes chips, which is the
cross-section. Ordering by cross-section makes the piece of the right diameter win whatever
its length, which is what SC-004 describes as the choice the operator would make by hand.

**Alternatives considered**:

- *Whole-envelope volume minus requested volume.* The literal reading; rejected above.
- *Cross-section, then prefer the longer piece.* Would keep offcuts on the shelf forever.
  The tie-break goes the other way — see D7.

---

## D7 — Ties break toward exact fits, then short pieces, then JA ID

**Decision**: The sort key is `(0 if the item fits at nominal else 1, area removed, the
item's extent along the part's axis, ja_id)`.

**Rationale**: Each term earns its place. *Exact before tolerance* because a tolerance-only
match is stock that is slightly **under** nominal, so it has the smaller cross-section and
would otherwise sort to the top — the operator asked for nominal and the shortfall is a
fallback, not a preference. *Shorter piece next* because using up a drop before cutting into
a full-length bar is what a person does at the rack. *`ja_id` last* because FR-020 requires
the same search over unchanged inventory to produce the same order, and the three preceding
terms can all tie.

**Alternatives considered**:

- *Leave ties in database order.* `search_active_items` orders by `ja_id` already
  (`:399`), so it would be stable by accident. Relying on an accident for a stated
  requirement is not worth the two words it costs to make it explicit. Rejected.

---

## D8 — Tolerance is applied by running the fit test twice, and attributed by running it again per dimension

**Decision**: Each requested dimension carries an optional tolerance. The test runs once at
nominal and, if that fails, once at `nominal − tolerance` per dimension. A result that
passes only the second is marked as fitting within tolerance. To name *which* dimensions
were load-bearing (FR-018), the test is re-run with each single tolerance removed; a
dimension whose removal makes the fit fail is named.

**Rationale**: It is three or four evaluations of a function that does at most a dozen
`Decimal` comparisons, on a candidate set already narrowed by material. That is cheaper than
threading "which constraint was binding" through the geometry, and it cannot disagree with
the fit test because it *is* the fit test. Boring and obvious, as Principle I asks.

**Alternatives considered**:

- *Return the binding constraint from the fit function.* Makes every rule return a structure
  instead of a boolean, for information used only on rows that needed tolerance. Rejected.
- *Apply tolerance to the item's dimensions instead of the request's.* Same arithmetic,
  wrong story: it would read as though the recorded measurement were in doubt. The tolerance
  is a property of the part being made. Rejected.

---

## D9 — A new service method, a new page, a new endpoint; the existing search untouched

**Decision**: `InventoryService.find_stock(request)` in
`app/mariadb_inventory_service.py`; `GET /inventory/find-stock` renders the form;
`POST /api/inventory/find-stock` runs the search. `app/templates/inventory/search.html`,
`app/static/js/inventory-search.js` and `search_active_items` are not modified.

**Rationale**: FR-025 and FR-026 require it, and the existing search has four dedicated e2e
files (`test_search.py`, `test_search_active_status.py`,
`test_search_hierarchical_materials.py`, `test_search_length.py`) whose behaviour must not
move. Naming follows the existing pair — `/inventory/search` and `/api/inventory/search`
(`app/main/routes.py:979`, `:2021`). The route stays thin, calling the service and
jsonifying, per Principle II.

**Alternatives considered**:

- *A mode toggle inside advanced search.* Offered to the operator as option C during
  specification and not chosen; it also puts the existing search's tests at risk for no gain.

---

## D10 — The shared results table gains one optional column, and nothing else changes

**Decision**: `app/templates/inventory/_item_table.html` gains `config.show_fit_column`
(absent ⇒ false) and `app/static/js/components/inventory-table.js` gains a matching
`config.showFitColumn`, one `<td>` in `createRow()`, and one `case 'fit'` in
`getSortValue()`. The inventory list and advanced search pass neither and render exactly as
they do today.

**Rationale**: FR-027 and FR-028. The macro is already parameterized this way — it takes
`show_selection_column`, `enable_sorting` and `show_sub_location` and is imported by both
`list.html` and `search.html` — so an optional column is the pattern the file already
teaches, not a new mechanism. The `getSortValue` case is what keeps FR-029 whole: the
column sorts like its neighbours instead of being the one dead header in the row.

**Rationale for the initial order surviving**: `InventoryTable.setItems()` assigns
`this.items` and calls `render()` directly — it does **not** call `sortBy()`
(`app/static/js/components/inventory-table.js:83-88`). The server's order is what renders
until the operator clicks a header. FR-029 therefore needs no new code, but it does need a
test, because a future `setItems` that sorted on entry would break it silently.

**Alternatives considered**:

- *A separate table for fit results.* Explicitly rejected by FR-027.
- *Overload the existing Dimensions column with the fit note.* Changes rendering on pages
  that already use it, which FR-028 forbids. Rejected.

---

## D11 — Three counters come back with every search

**Decision**: The response carries `considered`, `skipped_incomplete` and `skipped_hollow`
alongside the items.

**Rationale**: SC-006 requires an empty result to distinguish "you have none of this
material" from "yours are all too small" from "yours are recorded incompletely", and FR-011
requires the incomplete count specifically. `skipped_hollow` is not demanded by the spec but
falls out of D2 for free, and without it a tube-heavy inventory would report items as
"considered" that were never eligible — which is the same untrustworthy silence the counters
exist to prevent.

---

## D12 — Nothing is persisted, so there is no migration

**Decision**: No schema change, no Alembic revision. The request exists for the duration of
one HTTP call and the envelope is derived at read time.

**Rationale**: Every column the fit test reads already exists and is already nullable:
`length`, `width`, `thickness`, `wall_thickness` are `Numeric(10, 4), nullable=True`
(`app/database.py:37-41`). Principle V's migration requirements do not engage because
nothing about the stored shape of the data changes. Constitution Principle I: no stored
"envelope" column, no derived-dimension table, no index added without a measurement.

---

## D13 — Test placement, and the one wait the e2e test needs

**Decision**: `tests/unit/test_fit.py` (new, the bulk of the coverage),
`tests/unit/test_mariadb_inventory_service.py` (extended, ordering and counters through
SQLite), `tests/unit/test_routes.py` (extended, request validation and error shapes),
`tests/e2e/test_find_stock.py` (new) with a page object at
`tests/e2e/pages/find_stock_page.py` reusing `InventoryTableMixin`. No new pytest marker.

**The wait**: submitting the form fires a `fetch` and the handler appends result rows only
after awaiting the response, so this is CLAUDE.md's pattern C — render-implies-completion.
`expect(rows).to_have_count(n)` is the whole wait, and a rendered row cannot predate a
completed search. No `wait_for_timeout`, and nothing here needs one.

**Rationale**: Constitution Principle IV. Seeding goes through `live_server.add_test_data`
(`tests/e2e/test_server.py:135`), which takes milliseconds, because the Add Item form is not
what is under test here.

---

## D14 — Template and JS changes oblige screenshots and a manual section

**Decision**: The change regenerates documentation screenshots, adds a `find_stock_form`
entry to `tests/e2e/screenshot_config.yaml` beside the existing `search_form` entry
(`:166`), and adds a section to `docs/user-manual.md`.

**Rationale**: The Development Workflow section of the constitution makes screenshot
regeneration a merge gate for any change to `app/templates/**` or `app/static/js/**`, and
this change touches both. `docs/user-manual.md` is the only place that documents the
advanced search; a second search that is not in it will not be found. Screenshots come from
`nox -s screenshots_headless` and must pass `nox -s screenshots_verify` — and per the
project memory on this repo, screenshot output churns on every run, so the diff is inspected
before anything is committed.

---

## D15 — Active-only, with no toggle

**Decision**: The fit search returns active rows only, and the request carries no
`active` / `include_inactive` parameter.

**Rationale**: FR-024 says "limited to active items by default", and this design reads
"default" as "always" for this search. An inactive row is a superseded shortening-history
row or a piece that has left the shelf (Constitution Principle VI); neither can be cut into
a part today, which is the only question this search asks. Principle I is explicit that a
configuration knob for a future that has not arrived is prohibited, and the advanced search
keeps its own inactive toggle for the browsing case that wants one
(`app/main/routes.py:2073-2081`).

**Flagged for the operator**: this is a narrowing of "by default", stated here rather than
made silently. If finding an inactive row through this search turns out to matter, the
parameter is a small addition — but it should be added when that need appears, not before.

**Alternatives considered**:

- *Mirror the advanced search's three-state active filter.* Copies a control whose value here
  is speculative, and adds a state to every e2e test of the page. Rejected under Principle I.
