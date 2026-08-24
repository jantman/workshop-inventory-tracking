# Phase 0 — Research

The spec left no `NEEDS CLARIFICATION` markers: both open questions were answered in session
before it was finalized. What follows is the design research the plan rests on — six decisions,
each with what was rejected and why, and one finding in existing code that shaped the design.

---

## D1 — Where the agreed tree lives

**Decision**: a pure Python module, `app/utils/catalog_taxonomy.py`, exporting
`CATEGORY_PATHS: tuple[str, ...]` and `SPECIFICATION_KEYS: tuple[str, ...]`.

**Rationale**: FR-016 rules out the two obvious alternatives by name, and what is left has to
be read by the application at runtime. A module constant needs no file I/O, no parser, no
config key, no startup hook and no error path for "the file is missing or malformed". It is
importable by the unit suite with the network blocked. Per Principle I it is the smallest
thing that works.

**Alternatives considered**:

- **A categories table.** Explicitly forbidden by FR-016, and it would reverse a deliberate
  existing design decision (`app/utils/category.py` documents why there is no such table).
- **Placeholder products, one per branch.** Also forbidden by FR-016. It would put 142 fake
  rows in the catalog and leave every one of them as later cleanup.
- **A JSON or YAML data file read at startup.** Adds file I/O, a load-failure path and a
  question about what the application does when the file is absent — all to gain editability
  the operator does not need, because the record is a document they edit anyway.
- **Parsing `docs/category-taxonomy.md` at runtime.** Attractive because it would collapse the
  record and the reference data into one source and make FR-019's third-place drift
  impossible. Rejected: a markdown parser in the request path is machinery, and a malformed
  heading would take the category filter down. The same guarantee is bought far more cheaply
  by a *test* that compares the two (see D5).

---

## D2 — Where the merge happens

**Decision**: in `CatalogService.list_categories`, `CatalogService.category_tree` and
`CatalogService.list_specification_names`.

**Rationale**: FR-018 requires a branch on offer and the same branch in use to present as one
branch. Deduplicating on the canonical path inside the service means that holds for every
consumer at once — the product-form datalist, the search-page category filter and the browse
page all read these three methods. Merging in the route or the template would have to be
repeated per caller and would drift.

**Alternatives considered**:

- **Union in `/api/categories` only.** Satisfies FR-012 and leaves the browse page showing a
  different tree from the one the form offers. Rejected as an inconsistency the operator would
  hit on their first visit.
- **Union in the template.** Puts logic in the presentation layer, violating Principle II.

---

## D3 — Whether intermediate parents are included in `CATEGORY_PATHS`

**Decision**: yes. All 142 branches — roots, intermediate parents and leaves.

**Rationale**: two reasons. Filing at a parent is legitimate when the leaf is not yet known.
And `category_tree()` derives one entry per *distinct in-use path*, so a catalog whose only
product sits at `electronics/dev boards/arduino` renders a depth-3 row with no `electronics`
or `electronics/dev boards` row above it — the browse page indents against parents that are
not there. Including parents fills those holes as a side effect.

**Alternatives considered**:

- **Leaves only (116 paths).** Smaller, but leaves the browse tree with holes and refuses a
  legitimate filing target.
- **Synthesizing parents inside `category_tree`.** More code, and it would not help the
  datalist.

---

## D4 — The rename button on unoccupied branches

**Finding in existing code**: `CatalogService.rename_category` raises `ValidationError` when
no product carries the path — `app/catalog_service.py:2822`, *"There is no category … to
rename."* The check is deliberate and its refusal is covered by `tests/unit/
test_category_rename.py` and `tests/e2e/test_category_rename.py`.

**Decision**: render the Rename button only when the row's `count > 0`. No service change.

**Rationale**: once unoccupied branches appear on the browse page, every one of them would
otherwise offer a control that cannot succeed. An unoccupied branch has nothing in the database
to rewrite, so the correct way to rename it is to edit the record and the module — which is
also what FR-019 requires. Solving this presentationally leaves `rename_category`'s semantics
and its existing tests completely untouched.

**Alternatives considered**:

- **Make `rename_category` succeed on an empty category.** It would have to rewrite a Python
  constant, which is absurd, or do nothing and report success, which is a lie.
- **Leave the button and let it fail.** A control that always errors is worse than no control.

---

## D5 — Keeping the record and the module in agreement

**Decision**: a unit test parses `docs/category-taxonomy.md` and asserts that the branch paths
it names equal `CATEGORY_PATHS`, and that the registry's keys equal `SPECIFICATION_KEYS`.

**Rationale**: FR-019 says the record and the reference data must not be left disagreeing.
Runtime parsing (D1) would guarantee it at the cost of machinery in the request path. A test
gives the same guarantee at merge time, costs milliseconds, and turns drift into a red gate —
which is where the constitution puts this kind of obligation anyway. The record's tables have
a fixed shape (`| \`path\` | definition |` under a root heading), so the parse is a few lines
and fails loudly if that shape changes.

**Alternatives considered**:

- **Generating the module from the record in a build step.** A build step is a moving part the
  project does not otherwise have, and Principle I prohibits adding one speculatively.
- **Trusting review.** The whole feature exists because typed-by-hand vocabularies drift.

---

## D6 — Unioning the specification keys

**Decision**: union `SPECIFICATION_KEYS` into `list_specification_names`, feeding the existing
`specification-name-suggestions` datalist on the product form and the search page.

**Rationale**: this is the one vocabulary in the application with **no rename**.
`rename_category` and `rename_tag` both exist; there is no `rename_specification`, so `Thread`
beside `Thread Size` cannot be repaired in bulk. SC-010 asks for zero near-duplicate keys and
has no other mechanism. The union is the same pattern already being built for categories.

**Declared as a judgment call**: no functional requirement demands it — FR-023 through FR-025
constrain the *record*, not the application. It is included because the cost is one constant
and one union, and because leaving SC-010 to unaided discipline in the one place drift is
irreversible seemed the wrong trade. It is cleanly separable if it is not wanted.

**Alternatives considered**:

- **Scope the offered keys to the product's category.** Would need the branch-family mapping
  in code and a live lookup as the category field changes. Real machinery for a datalist that
  already filters as you type.
- **Do nothing.** Leaves SC-010 unmeasurable by construction.

---

## Non-decisions worth recording

- **No caching.** The union is a 142-element tuple against a `SELECT DISTINCT` that already
  runs. Principle I requires a measured problem before optimizing, and there is none.
- **No automatic vendor normalization.** FR-024 requires the record to state how a vendor's
  specification name maps onto a key. Making capture rewrite names automatically is a
  different feature with its own failure modes, and nothing has been observed going wrong yet.
- **No migration.** Nothing about the schema changes, so Principle V's Alembic requirement
  does not engage.
