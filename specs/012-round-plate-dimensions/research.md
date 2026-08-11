# Research: Round Plate Dimensions

**Feature**: `specs/012-round-plate-dimensions` | **Date**: 2026-08-10

Phase 0 output. Everything here is a decision that had to be settled before the design in
`plan.md` could be written, together with what was actually observed in the codebase to
settle it.

---

## D1: Where the dimension rules live

**Decision**: `app/taxonomy.py` becomes the single authoritative statement of which
dimensions each (Type, Shape) pair requires. The copies in `app/static/js/inventory-add.js`
and in `InventoryItem.validate()` are removed and both read from it.

**Rationale**: the system states these rules in three places today and they disagree.

| Statement | Keyed on | Says about Plate + Round | Reachable from |
|---|---|---|---|
| `app/taxonomy.py:32-75` | Type only — shape is a compatibility gate, never consulted for dimensions (`app/taxonomy.py:93-101`) | length, width, thickness | `/api/validate/type-shape` (`app/main/routes.py:1356`), which has **no callers** |
| `InventoryItem.validate()` `app/database.py:210-236` | Shape only, with one Threaded Rod special case | length, width — **no thickness at all** | `tests/unit/test_database.py` only, **never application code** |
| `inventory-add.js:18-46` | Type **and** Shape | length, width, thickness | The Add Item form. **The only one with runtime effect.** |

Fixing one and leaving the others would leave the system still saying three different things
about a round plate, which FR-005 forbids. Once D2 puts enforcement on the server, one table
stops being a tidiness argument and becomes a correctness requirement: FR-006 says the forms
and the write paths must apply the *same* rule, and two tables cannot be relied on to agree.

This is de-duplication, not a new abstraction layer — Constitution Principle I bars
speculative generality, and consolidating three existing copies into the module already named
for the job is the opposite of that.

**Alternatives considered**:

- *Fix all three copies in place, keep them separate.* Smaller diff, and the spec as written
  permits it (FR-005 says every place must state the rule, not that there must be one place).
  Rejected once D2 landed: three copies that must agree, enforced in two of three, is exactly
  the configuration that produced this bug.
- *Have the front end fetch the rules from `/api/validate/type-shape` on every Type/Shape
  change.* Removes the duplication too, but adds a network round-trip to a keystroke-speed
  interaction and gives every e2e test a new asynchronous boundary to wait on — the kind of
  awaited-fetch seam `CLAUDE.md` pattern A warns about. Rejected in favour of rendering the
  table into the page (D4).

---

## D2: What the server enforces

**Decision**: dimension requirements are enforced on every write path a user can reach — the
Add Item form POST, the Edit Item form POST, and the JSON item API. Validation lives in
`app/taxonomy.py` and is called from the route helpers beside the existing `required_fields`
check. It reports **all** missing dimensions at once.

**Rationale**: the operator chose this over leaving the forms as the sole enforcement point.
Today the server enforces no dimension rule of any kind — `_process_item_creation`
(`app/main/routes.py:261`) and the edit path (`:660`) require only `ja_id`, `item_type`,
`shape`, `material`, `location`, and `_create_single_item` never calls `validate()` or the
type/shape validator. Every dimension requirement in the application is an HTML5 `required`
attribute set by JavaScript. So the JSON API accepts a round plate with no thickness, and
always has.

This is a deliberate widening beyond what issue #85 describes, made with the risk stated. The
spec has been amended to match (FR-017, FR-018, and a qualification on SC-005) rather than
left contradicting the plan.

**Placement — routes, not `InventoryService`**: this matters more than it looks.
`tests/e2e/test_server.py:135-175`'s `add_test_data()` seeds fixtures by calling
`InventoryService.add_item()` directly. Validating inside the service would put every one of
the ~20 e2e fixtures that seed items through the new rules — and those fixtures are loose
(the default `item_type` is `'Rod'`, which is not even a member of `ItemType`). Validating at
the route helpers covers every path a user can actually reach while leaving direct-service
seeding alone. The existing `required_fields` check already sits there, so this matches the
surrounding code.

**Alternatives considered**:

- *Forms only, as today.* Smallest change, no blast radius. Rejected by the operator.
- *Enforce only for round Plate and Sheet.* No fixture could break, but the server would
  validate exactly one combination and ignore the rest. Rejected by the operator.
- *Enforce in `InventoryService`.* The constitutionally "correct" layer for business logic,
  but it breaks test seeding wholesale for no user-visible gain. The rule itself lives in the
  domain module (`app/taxonomy.py`); only the *call* is at the route. Routes stay thin.

---

## D3: Which rules the one table holds

**Decision**: the consolidated table reproduces today's **effective** behaviour — that is,
the `inventory-add.js` table, because it is the only one that runs — with exactly two rows
changed:

| Type + Shape | Before | After |
|---|---|---|
| Plate + Round | length, width, thickness | **width, thickness** |
| Sheet + Round | length, width, thickness | **width, thickness** |

Everything else keeps the requirement set it has today. This is what FR-009, FR-010 and
SC-005 demand, and with D2 in place it is also what keeps the existing suite green.

**Rationale, verified against the tests that would otherwise break**:

- **Threaded Rod must not require width.** `app/taxonomy.py:58` says `['length', 'width']`;
  the JS says `['length', 'thread_series', 'thread_size']`. `test_add_threaded_rod_with_proper_validation`
  (`tests/e2e/test_add_item.py:361`) asserts explicitly that Width is *not* required, and
  `tests/e2e/test_field_autocomplete.py:25-50` seeds three Threaded Rods through the JSON API
  with a length and thread fields and **no width**. Adopting the taxonomy row would 400 all
  three. The JS row is the correct one.
- **Bar + Round requires length and width.** The JS says so; `app/taxonomy.py:34` says only
  `['length']`. The unit suite's `_minimum_payload` (`tests/unit/test_routes.py:1347`) is a
  Bar + Round carrying both, so 21 API tests are unaffected either way — but the form
  requires both, and FR-006 says the server must agree with the form.
- **Channel requires nothing.** `ItemType.CHANNEL` is absent from the JS table entirely, so
  the form asks for no dimensions for a channel today. All four Channel e2e tests
  (`tests/e2e/test_add_item.py:600, 631, 658, 693`) supply a length and a width and **no
  thickness** — their `diameter=` argument is a no-op (see D6). Adopting `app/taxonomy.py:70`'s
  `['length', 'width', 'thickness']` would fail all four. The spec lists "supplying the
  dimension rule for Channel" under Out of Scope, so the empty rule is carried forward
  unchanged and the gap stays recorded rather than silently closed.

**Consequence that must be accepted**: the Add Item form filters its Shape dropdown by the
keys of the requirements table (`inventory-add.js:324-354`). Because Channel is absent, a
channel currently offers all four shapes, Hex included. Once there is one table, Channel gets
the shapes `app/taxonomy.py:70` already claims for it — Rectangular and Square. That is a
behaviour change outside the feature's stated scope. It is small, it is a correction rather
than a regression, and both existing Channel tests use Rectangular or Square so nothing
breaks — but it is a change, and it is recorded here rather than slipped in.

---

## D4: How the front end gets the rules

**Decision**: the server renders the table into the Add and Edit pages as a JSON constant;
the shared front-end module (D5) reads it. No fetch.

**Rationale**: keeps one source of truth without putting a network round-trip inside a
`change` handler. Nothing about the table is per-item or per-request, so there is nothing to
gain from fetching it. It also keeps the e2e suite free of a new awaited-fetch boundary,
which per `CLAUDE.md` is the single most common source of flake in this suite.

**Alternatives considered**: fetching from `/api/validate/type-shape` (see D1); duplicating
the literal in a `.js` file kept in sync by hand (that is the bug being fixed).

---

## D5: The Edit form

**Decision**: extract the requirement logic into one front-end module used by both the Add
and the Edit form. The Edit form's hand-rolled inline script loses its label swapping to it.

**Rationale**: FR-007 requires that the dimensions a form *marks* required are the ones it
*enforces*. The Edit form fails this today in both directions at once —
`app/templates/inventory/edit.html:167` and `:180` label Length and Width with an asterisk,
neither input carries a `required` attribute, the form is `novalidate`, and Thickness
(`:192`) is never marked at all despite being required for most types. Its inline script
(`:430-475`) only toggles the threading section and swaps the width label.

So the Edit form needs real requirement logic regardless. Writing a second copy of it there
would recreate, in JavaScript, precisely the duplication D1 removes from Python. Two genuine
call sites is not speculative generality.

**Alternatives considered**: correcting the Edit form's labels to match its (nonexistent)
enforcement — i.e. removing all asterisks. Technically satisfies FR-007 and is one line, but
it makes the Edit form worse, and D2's server-side enforcement would then reject edits the
form gave no warning about.

---

## D6: A dead selector the e2e suite has been carrying

**Observation, not a decision**: `AddItemPage.DIAMETER_INPUT = "#diameter"`
(`tests/e2e/pages/add_item_page.py:23`) points at an element that exists in no template.
`_fill_if_on_this_form()` (`:93-99`) returns silently when `count() == 0`, so every
`fill_dimensions(..., diameter="0.125")` call in the suite has always been a no-op. That is
why the Channel tests appear to supply a thickness and do not.

This matters here because this feature is the first thing to care what a round item's
diameter field is called. The page object must drive the real field, and the dead selector
must go — otherwise a test that "sets the diameter" will keep passing while setting nothing,
which is exactly the failure this feature exists to prevent in the application.

---

## D7: Displaying a round item with no length

**Decision**: fix the display paths that assume a length is present. No display path may
render a round plate as having no dimensions.

**Rationale**: `InventoryItem.display_name` (`app/database.py:247-265`) puts every dimension
behind `if self.length:`, so a length-less round plate contributes no dimensions to its own
name. `formatFullDimensions` (`app/static/js/components/item-formatters.js:43-83`) emits the
⌀ prefix only when `width` is present *without* `thickness`, so a round plate carrying both
renders as `6" × 0.25"` with nothing to say the first number is a diameter — FR-014 forbids
that. The full inventory of affected paths is enumerated in `data-model.md`.

**Alternatives considered**: none — this is a straight defect against FR-013 through FR-016.

---

## D8: No schema change, no migration

**Decision**: confirmed. Nothing in this feature touches the database schema.

**Rationale**: issue #85 asks for a schema update. `length` is already
`Column(Numeric(10, 4), nullable=True)` (`app/database.py:42`), so storing a round plate
without one requires nothing new, and diameter is already the `width` column by convention
throughout (`app/models.py:300`, `app/models.py:323-331`, `app/database.py:230`). The
operator confirmed that diameter stays the measurement the inventory already records. The
`CheckConstraint`s at `app/database.py:85-89` already require every dimension to be positive,
which is what the spec's zero-or-negative edge case asks for.

Per the project's memory note, Alembic is exercised by neither suite — so the best outcome
here is the one where there is no revision to exercise.
