---

description: "Task list for feature 046 — packs recorded as units, and what a pack was kept"
---

# Tasks: Packs Recorded as Units, and What a Pack Was Kept

**Input**: Design documents from `/specs/046-pack-quantity-order-lines/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: **Required, not optional.** Constitution IV: *"Changes that alter behavior MUST land
with tests covering that behavior, and `nox -s tests` and `nox -s e2e` MUST pass before a change
is merged."* Test coverage is not a target — write the test that would have caught the bug.

**Organization**: grouped by user story. Each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: which user story the task serves

## Path Conventions

Server-rendered Flask app, four layers (Constitution II): domain dataclasses in `app/models.py`,
ORM in `app/database.py`, services in `app/*_service.py`, thin routes in `app/product/routes.py`,
Jinja templates in `app/templates/product/`, plain-global scripts in `app/static/js/`.

Commands run through the main checkout's virtualenv with Python 3.13 on `PATH`:

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
NOX=/home/jantman/GIT/workshop-inventory-tracking/venv/bin/nox
```

---

## Phase 1: Setup

**Purpose**: establish the baseline this feature is measured against.

- [ ] T001 Confirm the baseline is green before touching anything: run `$NOX -s tests` and record the pass, and confirm `git status` is clean apart from `specs/046-pack-quantity-order-lines/`
- [ ] T002 Confirm the Alembic head is still `d0817b3ea45c` with `venv/bin/python manage.py db heads`; if it has moved, update `down_revision` in T051 and note it in [research.md](./research.md) R9
- [ ] T003 [P] Create `tests/unit/test_pack_conversion.py` with the module docstring naming this feature and the two contracts it exercises

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the shared pack shape. Behavior-preserving — this phase lands green against the
existing suite, with no observable change anywhere.

**⚠️ CRITICAL**: US1, US2 and US3 cannot begin until this phase is complete. US4 and US5 do not
depend on it.

- [ ] T004 Add the `PackLine` mixin to `app/models.py` per [data-model.md](./data-model.md): `units_per_pack`, `quantity`, `exact_unit_price`, `unit_price`, `price_rounds`, lifted verbatim from `McMasterOrderLine`. Document that it requires `packs`, `pack_size` and `pack_price` of its host, and why the abstraction is warranted here (two shipped implementations — the standard `app/services/order_vendors.py` sets)
- [ ] T005 Make `McMasterOrderLine` in `app/models.py` use `PackLine` and delete its four now-duplicated property bodies. Keep its field declarations and its docstring's *"Packs, not units"* explanation, which is still the clearest statement of the rule
- [ ] T006 Reshape `AmazonOrderLine` in `app/models.py`: replace the `quantity` and `unit_price` **fields** with `packs`, `pack_size` and `pack_price`, and inherit `PackLine`. Replace the class docstring's *"No pack arithmetic … The spec assumed otherwise and was wrong"* paragraph with why that finding was true of the page and false of the purchase
- [ ] T007 Update `AmazonOrderLine.from_payload` in `app/models.py` to read the payload's `quantity` into `packs` and `unit_price` into `pack_price`. **The payload format does not change** — an existing bookmarklet keeps working. Preserve both existing behaviours: an absent quantity is 1 rather than None, and `missing_fields` never reports a missing quantity
- [ ] T008 [P] Unit-test the mixin in `tests/unit/test_pack_conversion.py` against the worked table in [contracts/pack-conversion.md](./contracts/pack-conversion.md) §1 — all eight rows, including `packs=None → quantity=None`, `pack_price=None → unit_price=None`, and `pack_size=1` as the identity
- [ ] T009 [P] Unit-test in `tests/unit/test_amazon_capture.py` that a payload captured before this feature reads identically through `from_payload`, and that `AmazonOrderLine` still hashes and compares with `listing` excluded
- [ ] T010 Run `$NOX -s tests`. `tests/unit/test_mcmaster_capture.py`, `test_amazon_capture.py` and `test_order_vendors.py` must pass **unedited** — if any needed changing, the refactor was not behavior-preserving

**Checkpoint**: the pack shape exists and nothing behaves differently. US1 can begin.

---

## Phase 3: User Story 1 — A pack size on the Amazon order review (Priority: P1) 🎯 MVP

**Goal**: the operator states how many items are in one of what Amazon sold, and the purchase is
recorded in items at a per-item price.

**Independent test**: capture an order with one pack line, set its pack size, confirm, and read
the resulting purchase. Closes the reported issue on its own — no schema change, no other page.

### Red first

- [ ] T011 [US1] Write the failing test in `tests/unit/test_pack_conversion.py`: an `AmazonOrder` payload with one line — ASIN `B0PACK100`, title `Widget Screws (Pack of 100)`, quantity `1`, unit price `13.23` — run through `capture_order_lines` with a decision carrying `pack_size` of `100`, asserting the purchase holds **quantity 100 at 0.13**. Today it records **1 at 13.23**. Record the failure in the PR

### Implementation

- [ ] T012 [US1] Add `suggested_pack_size(line)` to `app/catalog_service.py` returning `1` for every line, with a docstring stating it is the seam US3 fills and that it MUST stay pure — no clock, no request state, no database read — because override detection reconstructs what the server rendered from it ([contracts/pack-conversion.md](./contracts/pack-conversion.md) §2, preconditions)
- [ ] T013 [US1] Add `'pack_size': form.get(f'pack_size[{key}]') or ''` to `_order_decisions` in `app/product/routes.py:1536`, keyed by `form_key` and never the item id (FR-004), following the docstring's existing rule that a vendor not offering the field simply ignores it
- [ ] T014 [US1] Add `_pack_size_for_line(self, line, decision)` to `app/catalog_service.py`: the operator's entry if present, else `suggested_pack_size(line)`. Refuse a value that is not a whole number of at least 1 with a `ValidationError` naming the line via `field=f'pack_size[{line.form_key}]'` — **never coerce to 1** (FR-011)
- [ ] T015 [US1] Add override detection to `app/catalog_service.py` per [contracts/pack-conversion.md](./contracts/pack-conversion.md) §2: compute `rendered_pack`, `rendered_quantity` and `rendered_price`, and return the submitted value when it differs, else recompute from the submitted pack size. Extend `_mcmaster_quantity` and `_mcmaster_unit_price`, or wrap them — whichever keeps McMaster's behaviour byte-identical (FR-039)
- [ ] T016 [US1] Rewrite `_amazon_line_fields` in `app/catalog_service.py:5163` to apply the pack size with `dataclasses.replace(line, pack_size=n)` before computing quantity and unit price, so every reader of `line.quantity` sees the converted value
- [ ] T017 [US1] Add `'pack_entry'` to `AMAZON_ORDER_VENDOR.review_columns` in `app/catalog_service.py`, and replace the *"Neither shipped/backorder counts nor pack arithmetic"* comment with what is now true
- [ ] T018 [US1] Add the pack-size column to `app/templates/product/order_review.html`, gated on `'pack_entry' in vendor.review_columns` so McMaster and DigiKey are untouched. Label it so it cannot be read as how many were ordered (FR-003), default it to the line's pack size, and round-trip `form_data` on a re-render (FR-012)
- [ ] T019 [US1] Show the inexact-division note for a converted Amazon line in `app/templates/product/order_review.html` — the existing `price_rounds` branch is gated on `packs`; widen it to any line whose pack exceeds 1 (FR-008)
- [ ] T020 [US1] Create `app/static/js/order-line-pack.js`: on each review row, recompute the quantity and unit-price inputs when the pack size changes, reusing `window.unitPriceFromPack` unchanged. Carry over both rules from `pack-unit-price.js` verbatim and say so at the top of the file — **write a derived field only once the operator has typed in a pack field, never on load**, and **nothing listens on the derived fields themselves**. Inert on any page without the hooks
- [ ] T021 [US1] Load `order-line-pack.js` from `app/templates/product/order_review.html`, after `pack-unit-price.js` is available or by loading that file too — `window.unitPriceFromPack` must exist before it runs

### Tests

- [ ] T022 [P] [US1] Unit-test override detection in `tests/unit/test_pack_conversion.py`: an untouched quantity follows the pack size; a changed one wins; a JS-converted submission and a no-JS submission reach the same number (the table in [contracts/pack-conversion.md](./contracts/pack-conversion.md) §2)
- [ ] T023 [P] [US1] Unit-test refusals in `tests/unit/test_pack_conversion.py`: `0`, blank-with-a-changed-sibling, negative and fractional pack sizes each raise naming the line, and **nothing is written for any line of that order** (FR-013)
- [ ] T024 [P] [US1] Unit-test in `tests/unit/test_amazon_capture.py` that `ReviewedLine.has_change` compares **converted** values — a pack line matching an already-recorded pack purchase reports no change (FR-010)
- [ ] T025 [P] [US1] Unit-test in `tests/unit/test_digikey_capture.py` and `tests/unit/test_mcmaster_capture.py` that neither vendor's `line_fields` output moved (FR-039, FR-040)
- [ ] T026 [US1] E2E in `tests/e2e/test_amazon_order.py`: seed an order with one pack line, set the pack size to 100, and assert with `expect(quantity_input).to_have_value("100")` and `expect(price_input).to_have_value("0.13")` before confirming — never `input_value()`, which does not poll (`CLAUDE.md` pattern E). Then confirm and assert the purchase reads 100 at 0.13
- [ ] T027 [US1] E2E in `tests/e2e/test_amazon_order.py`: a line whose pack size is left alone confirms to exactly what the order stated (FR-002, SC-005); and a refused pack size comes back with **every** other entry on the page intact (FR-012)

**Checkpoint**: the reported issue is closed. US1 is shippable on its own.

---

## Phase 4: User Story 2 — See which lines were treated as packs (Priority: P2)

**Goal**: a converted line cannot be mistaken for one that needed no change.

**Independent test**: capture a mixed order, convert some lines, and read off which are which
without opening Amazon.

**Depends on**: US1.

- [ ] T028 [US2] Mark converted lines in `app/templates/product/order_review.html` — a visible marker on any line whose pack exceeds 1, and nothing on a line at 1 (FR-014)
- [ ] T029 [US2] State the arithmetic on a converted line in `app/templates/product/order_review.html`: `packs × pack_size` and `pack_price ÷ pack_size` (FR-015), keeping the vendor's own numbers visible beside the catalog's (FR-016)
- [ ] T030 [US2] Correct the review banner in `app/templates/product/order_review.html` so *"Quantities and prices are as {{ vendor.name }} stated them"* is no longer asserted of a converted line (FR-017)
- [ ] T031 [US2] E2E in `tests/e2e/test_amazon_order.py`: a four-line order with two converted shows the converted marking on exactly those two. Assert the **positive** marker on a converted line, never the absence of one on an unconverted line — the absent form also passes against a row that has not rendered (`CLAUDE.md` pattern F)

**Checkpoint**: a multi-line pack order is reviewable, which is what makes US3's guess safe.

---

## Phase 5: User Story 4 — The single-listing capture page (Priority: P2)

**Goal**: capturing one pack of 100 from a listing records 100 items at the per-item price.

**Independent test**: capture a pack listing with no order involved; read the purchase back.

**Depends on**: nothing. Can run in parallel with US1 and US2 — different files throughout.

### Red first

- [ ] T032 [US4] Write the failing test in `tests/unit/test_capture.py`: POST to `/products/capture` with `pack_price=13.23`, `pack_size=100`, `packs=1` and no typed quantity, asserting the purchase records **100 at 0.13**. Today the route drops all three fields and records a NULL quantity

### Implementation

- [ ] T033 [US4] Add `quantity_from_pack` to `ListingCapture` in `app/models.py` — the pack size as a string, or None — mirroring `unit_price_from_pack`, so the first render carries the right number without JavaScript ([research.md](./research.md) R8)
- [ ] T034 [US4] Add a **Packs** input to `app/templates/product/capture.html` beside the existing pack fields, defaulting to 1, labelled as how many packs were bought (FR-024)
- [ ] T035 [US4] Derive the Quantity field's initial value in `app/templates/product/capture.html` from `packs × pack_size`, falling back to today's empty field when there is no pack (FR-023, FR-026), and round-trip `form_data` on a re-render (FR-012)
- [ ] T036 [US4] Correct the help text in `app/templates/product/capture.html` so Quantity and the pack fields say what they now do (FR-027), and replace the comment block asserting *"Neither pack field is recorded anywhere … there is no pack size in the schema and this is not the beginning of one"* ([research.md](./research.md) R10)
- [ ] T037 [US4] Extend `app/static/js/pack-unit-price.js` to also write `#quantity` from `#packs × #pack_size`, under the same `editing` guard that governs the price — never on load — and with nothing listening on `#quantity` itself. Reuse the existing `BigInt` discipline; the quantity derivation is integer multiplication and needs no new helper
- [ ] T038 [US4] Add `packs`, `pack_size` and `pack_price` parameters to `capture_order` in `app/catalog_service.py:1317`, deriving the quantity when the operator typed none and honouring a typed one (FR-025)
- [ ] T039 [US4] Forward the three fields from `product_capture` in `app/product/routes.py:525` to `capture_order`. **They follow the pack rule, not the listing-fallback rule** — the confirmation form always submits all three, so an empty value is one the operator cleared

### Tests

- [ ] T040 [P] [US4] Unit-test in `tests/unit/test_capture.py`: a pack of 100 bought once records 100 at 0.13; bought twice records 200 at 0.13; a typed quantity wins; a pack size of 1 or no pack behaves exactly as before (FR-026)
- [ ] T041 [US4] E2E in `tests/e2e/test_product_page_capture.py`: drive the confirmation form for a pack listing and assert `expect(quantity_field).to_have_value("100")`, then type over it and confirm the typed value is what is recorded

**Checkpoint**: both operator-facing pack paths record items.

---

## Phase 6: User Story 3 — A suggested pack size, marked as a guess (Priority: P3)

**Goal**: the typing disappears from the common case without a guess ever being invisible.

**Independent test**: capture an order whose titles name pack counts; the field arrives filled,
marked, and overrulable.

**Depends on**: US1 (the field) and US2 (the marking that makes a guess safe).

- [ ] T042 [US3] Add `pack_size_from_title(text)` to `app/models.py` per [data-model.md](./data-model.md): a pure `str -> Optional[int]` recognising `Pack(s) of N`, `N Pack` / `N-Pack` / `N Pk`, `N Pcs` / `N pieces` / `N pc` / `N ct` / `N count`, `Set of N` / `Box of N` / `Bag of N`. Fire only on a digit run **adjacent to a pack word**; return None for a bare number, for a count of 0 or 1, and when two different counts appear
- [ ] T043 [US3] Add `suggested_pack_size` and `pack_size_is_suggested` to `AmazonOrderLine` in `app/models.py`, with the precedence in [contracts/pack-conversion.md](./contracts/pack-conversion.md) §3: operator → the listing's structured `pack_size` → the title parse → 1
- [ ] T044 [US3] Fill in `suggested_pack_size(line)` in `app/catalog_service.py` (the T012 seam) to return the line's suggestion. **It must stay pure** — override detection reconstructs `rendered_pack` from it, so a suggestion that varied between render and submit would misclassify an override
- [ ] T045 [US3] Mark a suggested pack size in `app/templates/product/order_review.html` as read from the listing, distinguishably from one the operator entered, from first render until confirmation (FR-020)
- [ ] T046 [US3] Ensure an operator-set value is never replaced by the suggestion on a re-render (FR-021) — this falls out of the precedence in T043, so the task is the test that pins it
- [ ] T047 [P] [US3] Unit-test `pack_size_from_title` in `tests/unit/test_pack_conversion.py`: every recognised form returns its count, and `M3 x 12mm`, `12V`, `1/4-20`, a bare number, a count of 0 or 1, and a title naming two different counts all return None (FR-022)
- [ ] T048 [P] [US3] Unit-test the precedence chain in `tests/unit/test_amazon_capture.py`, including that a listing's structured `pack_size` beats a contradicting title
- [ ] T049 [US3] E2E in `tests/e2e/test_amazon_order.py`: a line titled `… (Pack of 100)` arrives pre-filled and marked as a guess; clearing it survives a re-render caused by a question about another line

**Checkpoint**: a pack order captures with no arithmetic and no typing, and every guess is visible.

---

## Phase 7: User Story 5 — The pack is kept (Priority: P3)

**Goal**: a captured order reconciles against the vendor's invoice from the catalog alone.

**Independent test**: capture a pack line through each of the three paths, then restate the
vendor's own line from what was stored.

**Depends on**: US1 and US4 (the two paths that produce a pack size). **Carries the migration.**

- [ ] T050 [US5] Add `pack_size = Column(Integer, nullable=True)` and `pack_price = Column(Numeric(10, 2), nullable=True)` to `Purchase` in `app/database.py`, with a comment stating what [contracts/purchase-pack-fields.md](./contracts/purchase-pack-fields.md) §1 states — they record what the vendor charged and are never a derivation of the row — and the `create_all`-vs-Alembic drift warning the neighbouring columns already carry
- [ ] T051 [US5] Create the Alembic revision `migrations/versions/<rev>_add_purchases_pack_size_and_pack_price.py` with `down_revision = 'd0817b3ea45c'`, adding both columns nullable and dropping both on downgrade. No data migration (FR-032). Match `app/database.py` exactly — `Integer`, `Numeric(10, 2)`, both nullable, neither indexed
- [ ] T052 [US5] Exercise the migration both ways against MariaDB per [quickstart.md](./quickstart.md) §2: `upgrade head`, `downgrade -1`, `upgrade head`, then confirm every pre-existing row holds NULL in both columns
- [ ] T053 [US5] Write the pack fields from `_amazon_line_fields` in `app/catalog_service.py`, **only when the pack size exceeds 1** — a pack of one stores NULL for both (FR-031, invariant P2)
- [ ] T054 [US5] Write `line.pack_size` and `line.pack_price` from `_mcmaster_line_fields` in `app/catalog_service.py`, which today discards them. NULL for "Each" and for **"Pairs"**, where McMaster states no count — inventing 2 there would be inventing data
- [ ] T055 [US5] Store the pack from `capture_order` in `app/catalog_service.py`, from the parameters T038 added, under the same both-or-neither and never-1 rules
- [ ] T056 [US5] Write the pack fields in `_apply_order_change` in `app/catalog_service.py:3069` alongside quantity and price — a re-capture that updates the quantity and leaves a stale pack size is exactly the contradiction FR-033 forbids
- [ ] T057 [US5] Show both views per line on the captured order's page `app/templates/product/order.html` (FR-034): the vendor's *N packs of S at $P* beside the catalog's *Q items at $U*. Derive packs as `quantity / pack_size` and **omit it when it does not divide evenly** — the operator overrode the quantity and no packs figure would be honest. Label the pack as the vendor's line, never as the arithmetic behind the row
- [ ] T058 [US5] Show the pack as context on `app/templates/product/receive.html` where the purchase carries one, and confirm `receive_purchase` leaves both columns untouched — what arrived is allowed to differ from what was ordered ([research.md](./research.md) R7)
- [ ] T059 [P] [US5] Unit-test the invariants from [contracts/purchase-pack-fields.md](./contracts/purchase-pack-fields.md) §2 in `tests/unit/test_pack_conversion.py`: both-or-neither, never 1, `pack_price` through `_validate_price`, and a hand-recorded purchase holding NULL for both
- [ ] T060 [P] [US5] Unit-test the writers in `tests/unit/test_mcmaster_capture.py`, `test_amazon_capture.py`, `test_capture.py` and `tests/unit/test_order_receive.py`: each path stores the pack, DigiKey stores neither, and `receive_purchase` amending a quantity leaves both columns alone
- [ ] T061 [US5] E2E in `tests/e2e/test_amazon_order.py`: capture a pack order, open it, and assert the vendor's line and the catalog's are both shown. Establish the region with an `expect(...)` before reading it — a captured order's lines are JS-rendered and a snapshot read against them returns empty (`CLAUDE.md`)

**Checkpoint**: every promise in the spec is met.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T062 [P] Correct `docs/user-manual.md:1228` *"When it is sold as a pack"*: remove *"Neither pack field is stored — they exist to work the unit price out and are forgotten the moment you capture"* (FR-035), and make the Quantity description match the page (FR-037). **Check rather than rewrite** the sentence *"Units in the Pack is not Quantity … Quantity is how many units the order brings in"* — it becomes true with US4 and needs no edit
- [ ] T063 [P] Add a `docs/user-manual.md` passage covering the Amazon review's pack size, stating that a suggested one is a guess the operator is answerable for (FR-036)
- [ ] T064 [P] Update `docs/user-manual.md:1643` and `:1808` to say McMaster's pack is now kept rather than discarded (FR-038)
- [ ] T065 [P] Correct the `ListingCapture.pack_price` / `pack_size` comment in `app/models.py` asserting *"Neither is recorded anywhere … There is no pack size in the schema and this is not the beginning of one"*, and the McMaster packs-column comment in `app/templates/product/order_review.html` asserting *"not stored"* ([research.md](./research.md) R10)
- [ ] T066 Verify the documentation gates: `grep -n "Neither pack field is stored" docs/user-manual.md` returns nothing, and `grep -ric "catalogue" README.md docs/ app/ tests/` returns nothing. Confirm `specs/` is untouched, including `specs/029-whole-order-capture/research.md` §5 whose finding this reverses — it is a frozen record
- [ ] T067 Regenerate documentation screenshots with `$NOX -s screenshots_headless` and verify with `$NOX -s screenshots_verify`. `app/templates/**` and `app/static/js/**` both changed, so CI blocks merge on stale ones. **Measure the churn before committing** — screenshots come from two sources and churn every run; commit only the ones this change actually altered
- [ ] T068 Run the full unit suite with `$NOX -s tests` and confirm it still completes in under a second. Nothing this feature adds does I/O
- [ ] T069 Run the E2E suite detached — `nohup $NOX -s e2e > /tmp/claude-e2e.log 2>&1 &` — and poll the log. It takes about 17 minutes warm and outlasts the Bash tool's 10-minute cap; a foreground run reports a false timeout on a passing suite
- [ ] T070 Confirm zero fixed waits were added: `grep -rn "wait_for_timeout\|time.sleep\|networkidle" tests/e2e/` returns only the one justified call in `waits.dismiss_material_suggestions`
- [ ] T071 Confirm the E2E run left the working tree clean (`git status`) — a test session that modifies tracked files fails Constitution IV
- [ ] T072 Do the by-hand check in [quickstart.md](./quickstart.md) §7 against order `111-1533738-5610601`, the four-line pack order from the issue, including the no-pack regression that proves SC-005
- [ ] T073 Open the PR against `main` per the branching rule, linking issue #137 and quoting the comment this feature answers

---

## Dependencies

```text
Phase 1 Setup
     |
     +---------------------------+
     |                           |
Phase 2 Foundational         Phase 5 US4 (P2)  [independent]
     |                           |
Phase 3 US1 (P1) MVP             |
     |                           |
Phase 4 US2 (P2)                 |
     |                           |
Phase 6 US3 (P3)                 |
     |                           |
     +-----------+---------------+
                 |
        Phase 7 US5 (P3)  [needs US1 and US4; carries the migration]
                 |
        Phase 8 Polish
```

| Story | Depends on | Why |
|-------|-----------|-----|
| US1 | Foundational | Needs the pack shape on `AmazonOrderLine` |
| US2 | US1 | Marks a conversion US1 introduces |
| US4 | — | Different page, different files throughout |
| US3 | US2 | A pre-filled guess is only safe on a review that shows conversions plainly (spec, *Why this priority*) |
| US5 | US1, US4 | Stores what those two produce |

**The one cross-phase seam to watch**: T012 creates `suggested_pack_size(line)` returning `1`, and
T044 fills it in. Override detection reads it for `rendered_pack`, so it must stay pure in both
states — a suggestion that varied between render and submit would misclassify an override as an
untouched field.

---

## Parallel Execution

**Across stories**: Phase 5 (US4) touches `capture.html`, `pack-unit-price.js`, `capture_order`
and `test_capture.py` — none of which US1, US2 or US3 touch. It can run start to finish alongside
the US1 → US2 → US3 chain.

**Within phases**, the `[P]`-marked tasks:

| Phase | Parallel set | Files |
|-------|-------------|-------|
| 2 | T008, T009 | `test_pack_conversion.py`, `test_amazon_capture.py` |
| 3 | T022, T023, T024, T025 | four separate test modules |
| 5 | T040 | `test_capture.py` |
| 6 | T047, T048 | two test modules |
| 7 | T059, T060 | test modules only, after the writers land |
| 8 | T062, T063, T064, T065 | manual sections and code comments in distinct files |

Everything else is sequential because it edits a file an earlier task in the same phase edits —
`app/catalog_service.py` and `app/templates/product/order_review.html` are each touched by several
tasks per phase.

---

## Implementation Strategy

**MVP is Phase 1 → 2 → 3.** That is T001–T027, closes issue #137, needs no schema change, and
touches no page but the Amazon order review. Ship it and stop if nothing else fits.

**Then the second increment, in this order:**

1. **US4** (T032–T041) — the same defect on the page the operator reaches most often, and one the
   manual already documents as working the way it does not. No dependency on anything above.
2. **US2** (T028–T031) — small, and the precondition for US3 being safe.
3. **US3** (T042–T049) — removes the typing.
4. **US5** (T050–T061) — the migration. Last deliberately: it is the only irreversible step, and
   by then the two paths that feed it are proven.

**Before US5, re-read [research.md](./research.md) R7.** It interprets FR-033 to mean the stored
pack records what the vendor charged and is left alone when a purchase is amended later. That
reading is what makes a short delivery a legitimate row rather than a contradiction to repair. If
the author wants the stricter reading, R7 is the single place to change it and the change must
happen before T050.
