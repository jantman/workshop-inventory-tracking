# Tasks: Bulk-Receiving Outstanding Purchases from a Backfill

**Feature**: `specs/042-bulk-receive-outstanding` | **Branch**: `robot-army/issue-140-no-way-to-bulk-receive-already-captured`

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/cli-receive-outstanding.md](./contracts/cli-receive-outstanding.md), [contracts/service-receipts.md](./contracts/service-receipts.md), [quickstart.md](./quickstart.md)

**Tests**: Included, and not optional. Constitution IV requires that "changes that alter
behavior MUST land with tests covering that behavior". More specifically: feature 031's
equivalent guarantee — that a backfill receipt moves no count, no count age and no stock flag —
holds today *by construction*, because a purchase born with a `received_date` never reaches
`receive_purchase`. This feature writes the first code that receives an **already-existing**
purchase without going through it, so construction stops covering it here. Phase 6 is where that
is nailed down, and it is not skippable.

## Format

`- [ ] [ID] [P?] [Story?] Description with file path`

`[P]` marks tasks that touch different files and depend on nothing incomplete.

---

## Phase 1: Setup

Nothing to set up. No new dependency, no new directory, no migration, no new pytest marker, no
schema change. The feature branch already exists and the work happens on it.

- [X] T001 Confirm the working tree is clean and on `robot-army/issue-140-no-way-to-bulk-receive-already-captured`, and that `venv/bin/nox -s tests` is green before any change, so a later failure is attributable

---

## Phase 2: Foundational (blocking prerequisites)

The two records every story passes around. Nothing else can be written until they exist: the
service has nothing to return, the command has nothing to print, and the tests have nothing to
assert against.

- [X] T002 Add the frozen dataclass `OutstandingReceipt` to `app/models.py`, beside `PurchaseDeletion` (~line 2221), with fields `purchase_id: int`, `vendor: str`, `order_date: datetime`, `order_number: Optional[str] = None`, `product_description: Optional[str] = None`, `quantity: Optional[int] = None`. Its docstring must say why `order_date` is **not** optional here: an undated purchase is not a candidate, and that invariant is what makes "the receipt date is the order date" total rather than conditional at the write
- [X] T003 Add the frozen dataclass `OutstandingReceiptPlan` to `app/models.py`, directly after `OutstandingReceipt`, with `receipts: Tuple[OutstandingReceipt, ...] = ()` and `undated_count: int = 0`, plus `purchase_ids` and `is_empty` properties. Its docstring must record why this is a flattened record rather than a list of ORM rows — the same reason `PurchaseDeletion`'s docstring already gives: the caller reads it after the session has closed, and relying on `expire_on_commit=False` for that works by luck rather than by design. State that `undated_count` is a count and not a list on purpose: the operator can do nothing about those rows from this command
- [X] T004 Add `render(self) -> str` to `OutstandingReceiptPlan` in `app/models.py`, producing the operator-facing listing exactly as [contracts/cli-receive-outstanding.md](./contracts/cli-receive-outstanding.md) specifies — one aligned line per receipt (`#id`, vendor, order number or `-`, order date as `YYYY-MM-DD`, quantity, product description), preceded by a heading line whose verb the caller supplies, and followed by the undated-skip line when `undated_count` is non-zero. Rendering lives with the result, following `app/services/amazon_order_export.py`'s summary, which `manage.py` prints the same way

**Checkpoint**: `venv/bin/nox -s tests` green. Nothing calls this yet.

---

## Phase 3: User Story 1 — Closing out a backfill captured as outstanding (P1)

**Goal**: Every outstanding purchase matching the filters is marked received, each dated from its
own order date.

**Independent test**: Seed several outstanding purchases with order dates spread over past years,
run the two service methods against them, and verify each becomes received with a receipt date
equal to its own order date.

- [X] T005 [US1] Add `plan_outstanding_receipts(self, before: datetime, vendor: Optional[str] = None) -> OutstandingReceiptPlan` to `app/catalog_service.py`, beside `find_captured_orders` (~line 3121). Select purchases where `received_date IS NULL`, `order_date IS NOT NULL` and `order_date < before`, adding a case-insensitive whitespace-stripped vendor equality only when `vendor` is given. Order by `order_date` then `id`, eager-load the product with `selectinload` so rendering does not fire a query per row, and build one `OutstandingReceipt` per row inside the session. Reads only. Leave `undated_count` to T022, which fills it
- [X] T006 [US1] Add `apply_outstanding_receipts(self, plan: OutstandingReceiptPlan) -> int` to `app/catalog_service.py`, directly after T005's method. Inside one `self._session()` block, loop over `plan.purchase_ids`, load each purchase, skip it if it is missing, already received, or has no order date, and otherwise set `received_date = order_date`. Return how many were written. A plain loop, not a bulk `UPDATE` — see [research.md](./research.md) §5
- [X] T007 [US1] Write the docstrings for both methods in `app/catalog_service.py`, following the file's house style. `apply_outstanding_receipts`'s must state the four things it deliberately does **not** do and why (031 FR-028), name `capture_order_lines` as the path it is imitating, and say that this is the first code to receive an already-existing purchase without going through `receive_purchase` — so the guarantee is no longer satisfied by construction and `tests/unit/test_bulk_receive.py` is what will notice
- [X] T008 [P] [US1] Create `tests/unit/test_bulk_receive.py` with `pytestmark = pytest.mark.unit`, a `catalog` fixture built as `CatalogService(test_storage)` (matching `tests/unit/test_order_backfill.py`), and a helper that seeds a product plus an outstanding purchase with a given vendor and order date
- [X] T009 [US1] Add tests to `tests/unit/test_bulk_receive.py` for the sweep itself: outstanding purchases before the cutoff are planned and then received (FR-001); each one's `received_date` equals its own `order_date` and is **not** today (FR-008); `apply_outstanding_receipts` returns the number written
- [X] T010 [US1] Add tests to `tests/unit/test_bulk_receive.py` for the downstream reads the spec names: after a sweep, `find_captured_orders` reports the swept order with `outstanding_count == 0` / `is_complete` (FR-013, SC-005), and the reorder read no longer reports the product as on the way on account of that purchase
- [X] T011 [US1] Add selection tests to `tests/unit/test_bulk_receive.py`: an already-received purchase is not planned and its receipt date is not overwritten (FR-002); a purchase ordered *on* the cutoff date is excluded and one ordered the day before is included (FR-004); `--vendor`-style filtering excludes other vendors and matches case-insensitively with surrounding whitespace stripped (FR-003); omitting the vendor includes every vendor (FR-005); a hand-recorded purchase carrying no `supplier_order_reference` is eligible (FR-007)

**Checkpoint**: the sweep works end to end from Python. `venv/bin/nox -s tests` green.

---

## Phase 4: User Story 2 — Seeing exactly what would happen first (P1)

**Goal**: The operator sees every purchase a run would touch, before anything is written, and can
stop.

**Independent test**: Run the command with `--dry-run` against seeded outstanding purchases and
verify each one is named in the output and that every purchase is still outstanding afterwards.

- [X] T012 [US2] Add the `receive-outstanding` command to the existing `orders` group in `manage.py`, beside `amazon_urls`. Options per [contracts/cli-receive-outstanding.md](./contracts/cli-receive-outstanding.md): `--before` required as `click.DateTime(formats=['%Y-%m-%d'])`, `--vendor` optional text, `--dry-run` a flag. Import `CatalogService` inside the command body, matching the file's style. Body: plan, print `plan.render(...)`, and stop
- [X] T013 [US2] In `manage.py`, add the empty-selection branch: when `plan.is_empty`, print that nothing matches, write nothing, prompt for nothing, and return with status 0 (FR-017)
- [X] T014 [US2] In `manage.py`, add the confirmation branch: when not `--dry-run` and the plan is non-empty, `click.confirm` after printing the listing; declining prints that nothing was written and returns 0, confirming calls `apply_outstanding_receipts` and prints how many were received (FR-016, FR-018)
- [X] T015 [US2] Write the command's docstring in `manage.py`, following the `amazon-urls` precedent: what it is for, that the receipt date is each purchase's own order date and never today, that it moves no count and clears no flag, and that there is no un-receive
- [X] T016 [P] [US2] Add CLI tests to `tests/unit/test_bulk_receive.py` using `click.testing.CliRunner` against the `orders` group, substituting the `CatalogService` the command imports with a stub plan/apply pair: `--dry-run` prints every selected purchase and never calls apply (FR-014, FR-015); without it, confirming calls apply and declining does not (FR-016); an empty plan prints the nothing-to-do line and never prompts (FR-017); a malformed `--before` exits non-zero without the command body running (FR-019)

**Checkpoint**: the command is usable at a terminal. `venv/bin/nox -s tests` green.

---

## Phase 5: User Story 3 — A backfill receipt is not a receiving-desk receipt (P1)

**Goal**: Sweeping moves the receipt date and nothing else.

**Independent test**: Seed a product with a tracked count, an age, and a manually set low-stock
flag; sweep an outstanding purchase for it; verify the count, its age and the flag are all
unchanged and only the receipt date moved.

No production code is expected here — T006 already writes one column — but if any of these
tests fail, T006 is what is wrong.

- [X] T017 [US3] Add a test to `tests/unit/test_bulk_receive.py` that a product with a tracked on-hand count still has exactly that count after one of its purchases is swept, including when the purchase carries a quantity (FR-009)
- [X] T018 [US3] Add a test to `tests/unit/test_bulk_receive.py` that `product.quantity_updated_at` is unchanged by a sweep (FR-010), and that a product with no tracked count still has `quantity is None` afterwards (US3 scenario 4)
- [X] T019 [US3] Add a test to `tests/unit/test_bulk_receive.py` that a manually set `stock_status` and its `stock_status_updated_at` both survive a sweep unchanged (FR-011)
- [X] T020 [US3] Add a test to `tests/unit/test_bulk_receive.py` that a sweep leaves the purchase's `quantity`, `unit_price` and `notes` and the product's `description` unchanged (FR-012)
- [X] T021 [US3] Add a test to `tests/unit/test_bulk_receive.py` that the sweep is applied as one unit: with the session's commit made to fail, no purchase in the plan is received (FR-020)

**Checkpoint**: the invariant that outlives this feature is pinned. `venv/bin/nox -s tests` green.

---

## Phase 6: User Story 4 — Leaving alone what it cannot honestly date (P2)

**Goal**: Undated outstanding purchases are left outstanding, and the operator is told how many.

**Independent test**: Seed an outstanding purchase with no order date alongside dated ones, run
the command, and verify the dated ones are received, the undated one is not, and the output
accounts for it.

- [X] T022 [US4] In `plan_outstanding_receipts` in `app/catalog_service.py`, count the outstanding purchases with no `order_date` that match the vendor filter, and set `undated_count` on the returned plan. A second small query in the same read; the cutoff cannot apply to a row with no date to compare
- [X] T023 [US4] Add tests to `tests/unit/test_bulk_receive.py`: an outstanding purchase with no order date is not planned and is still outstanding after a sweep (FR-006); the plan's `undated_count` reports it; `render()` names the skip when the count is non-zero and omits the line entirely when it is zero (FR-018)

**Checkpoint**: `venv/bin/nox -s tests` green.

---

## Phase 7: Polish & cross-cutting

- [X] T024 [P] Add a subsection to `docs/user-manual.md` immediately after **Saying it already arrived** (~line 1861), covering the command for an operator who captured orders as outstanding or forgot the tick: what to run, that `--dry-run` shows the list first, that the receipt date is each order's own date, and — restated rather than cross-referenced, because this is exactly the operator who will wonder — that a counted quantity does not go up and a hand-set low flag is not cleared. Say plainly that there is no un-receive and that a mistake means deleting the purchase and re-capturing it
- [X] T025 [P] Check the wording added in T024 and every new docstring for the project's American spelling rule (`catalog`, never `catalogue`) per `CLAUDE.md`
- [ ] T026 Run `venv/bin/nox -s tests` and confirm green, then run `venv/bin/nox -s e2e` detached (it exceeds the 10-minute Bash cap; see `CLAUDE.md`) and confirm it is unaffected — no page changed, so nothing there should move
- [ ] T027 Confirm the working tree is clean after the test runs (Constitution IV) and that no file under `app/templates/**`, `app/static/css/**` or `app/static/js/**` was touched, so the screenshot gate correctly does not apply
- [ ] T028 Mark this task list complete and commit, push the branch, and open the PR

---

## Dependencies

```text
Phase 1 (T001)
   └─▶ Phase 2 (T002–T004)          the two records; blocks everything
          ├─▶ Phase 3 US1 (T005–T011)      the sweep
          │      ├─▶ Phase 4 US2 (T012–T016)   the command, needs both service methods
          │      ├─▶ Phase 5 US3 (T017–T021)   asserts against T006
          │      └─▶ Phase 6 US4 (T022–T023)   extends T005
          └─▶ Phase 7 (T024–T028)
```

- **US1 is the MVP.** With Phases 1–3 done the sweep is real and reachable from a Python shell;
  everything after makes it usable and pins what it must not do.
- **US2, US3 and US4 are independent of each other** and can be done in any order once US1 lands.
- **US3 adds no production code.** It is the phase that exists so that a later refactor toward
  `receive_purchase` fails loudly instead of silently inflating every counted quantity in the
  catalog.

## Parallel opportunities

- T002 and the reading of the contracts can proceed together; T003 depends on T002.
- T008 (the new test file's scaffolding) is `[P]` against T005–T007 — different file, no
  dependency on the service being finished.
- T016 is `[P]` against T012–T015 only in the sense that it lands in a different file; write it
  after the command exists or it has nothing to invoke.
- T024 and T025 are `[P]` against each other's neighbours and against all test work.

There is little genuine parallelism here and that is fine: the feature is five files.

## Implementation strategy

Land Phase 2 and Phase 3 first and stop to run the suite — at that point the feature exists and
is wrong only in being unreachable. Then Phase 4 makes it reachable, Phase 5 makes it safe to
leave alone for a year, and Phase 6 closes the honest-skip gap. Phase 7 is documentation and the
gates.
