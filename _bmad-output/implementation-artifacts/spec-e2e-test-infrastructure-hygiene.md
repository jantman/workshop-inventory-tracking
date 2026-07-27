---
title: 'E2E test infrastructure hygiene: truncate catalog tables, decouple scan helpers'
type: 'chore'
created: '2026-07-26'
status: 'done'
baseline_revision: 'b435515d7cb969e3688fb79d201871b475f1d944'
final_revision: 'b5d76a1c2aeb6d2b1dda383143c2ef5d69dcf49f'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** Two shared test-infrastructure defects force every future test to work around them. (1) `E2ETestServer.clear_test_data()` deletes only photos, inventory items and the material taxonomy, so every product, purchase, attachment, identifier and tag an e2e test creates survives into every later test and every later run against the same container — Story 3.1's and 4.5's tests had to defend themselves with per-invocation UUID/GTIN minting and positive-only assertions. (2) `tests/e2e/test_scan_routing.py` imports `SCAN_INPUT`, `simulate_wedge_scan` and `unstored_gtin` from the sibling test module `tests/e2e/test_wedge_scan.py`, coupling two test modules through collection order.

**Approach:** Add an FK-ordered delete of the catalog tables to `clear_test_data()`. Move the three shared scan helpers into a new `tests/e2e/conftest.py` so both e2e modules depend on shared infrastructure rather than on each other. Replace the Story 4.5 unit assertions that reason about autoincrement arithmetic (`get_product(existing + 1) is None`, `get_product(1) is None`) with assertions over the actual product set, exposed as a new `product_ids` fixture in `tests/conftest.py`.

## Boundaries & Constraints

**Always:**
- Delete catalog rows in FK-safe order. `attachments` references both `products` and `purchases`; `product_tags`, `product_identifiers` and `purchases` reference `products`. Order: `Attachment` → `ProductTag` → `ProductIdentifier` → `Purchase` → `Product`, before the existing `MaterialTaxonomy` delete.
- Include `product_tags` even though the ledger entry names only four tables — `ProductTag.product_id` is a non-nullable FK to `products`, so omitting it makes the `Product` delete fail under MariaDB.
- Preserve the existing `clear_test_data()` error handling shape (try/rollback/print/finally-close, then `setup_materials_taxonomy()`).
- Both `tests/e2e/test_wedge_scan.py` and `tests/e2e/test_scan_routing.py` import the moved helpers from `tests.e2e.conftest`; neither imports from the other afterwards.
- Where a docstring or comment asserts that `clear_test_data()` does NOT truncate the catalog tables, update it — after this change the statement is false.
- Behavior of the helpers themselves is unchanged; this is a move, not a rewrite.

**Block If:**
- Truncating the catalog tables makes an existing e2e test fail for a reason other than its own stale "the catalog accumulates" assumption — that would mean a test depends on cross-test catalog state and the fix needs a human call.

**Never:**
- Do not remove the per-invocation UUID / random-GTIN minting from `test_scan_routing.py`, `test_category_autocomplete.py` or `test_product_tags.py`. Those defenses remain correct and removing them is out of scope.
- Do not move `routed_body`, `FRAGMENT_URL`, `JA_ID_INPUT` or `record_scan_requests` — they have a single consumer.
- Do not change production code under `app/`.
- Do not edit `{implementation_artifacts}/deferred-work.md`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Catalog cleared between tests | A prior test created a product with a purchase, attachment, identifier and tag | The next `live_server` fixture leaves `products`, `purchases`, `attachments`, `product_identifiers`, `product_tags` empty | No error expected |
| Empty catalog | `clear_test_data()` on a database with no catalog rows | Deletes zero rows, commits, taxonomy re-seeded | No error expected |
| FK-ordered delete | Products with dependent purchases/attachments/tags/identifiers | All rows removed, no `IntegrityError` | On any exception: rollback + warning print, as today |
| "Nothing was written" assertion, empty start | POST rejected by validation, no product created | `product_ids() == set()` | No error expected |
| "Nothing was written" assertion, one pre-existing product | A product `existing` was created, then a POST is rejected | `product_ids() == {existing}` | No error expected |
| Helper import | `tests/e2e/test_scan_routing.py` collected alone (`-k scan_routing`) | Imports resolve from `tests.e2e.conftest`; test_wedge_scan.py need not be collected | Collection error if the move is incomplete |

</intent-contract>

## Code Map

- `tests/e2e/test_server.py` -- `E2ETestServer.clear_test_data()` at lines 311-332; imports the ORM classes at line 18. Needs the catalog deletes and the new imports.
- `app/database.py` -- ORM classes `Product` (819), `Purchase` (889), `Attachment` (956), `ProductIdentifier` (1011), `ProductTag` (1069) and their FK columns.
- `tests/e2e/conftest.py` -- **new file**. Destination for `SCAN_INPUT`, `_gtin13`, `unstored_gtin`, `simulate_wedge_scan`.
- `tests/e2e/test_wedge_scan.py` -- defines the helpers today at lines 32 (`SCAN_INPUT`), 55 (`_gtin13`), 62 (`unstored_gtin`), 94 (`simulate_wedge_scan`); ~30 in-file usages of `SCAN_INPUT`.
- `tests/e2e/test_scan_routing.py` -- line 32 is the offending cross-module import; module docstring lines 20-26 describe the pre-fix accumulation behavior.
- `tests/conftest.py` -- holds `test_storage`, `live_server`, `page`, `pytest_configure`.
- `tests/unit/conftest.py` -- **new file**. Destination for the new `product_ids` fixture. (Originally planned for the root `tests/conftest.py`; moved during review because a fixture there is offered to e2e tests too, where it reads the wrong database. See Design Notes.)
- `tests/e2e/test_clear_test_data.py` -- **new file**. Executable coverage for AC1, added during review.
- `tests/unit/test_product_routes.py` -- arithmetic assertions at lines 1317, 1327, 1346, 1374, 1645.
- `tests/unit/test_scan_routes.py` -- arithmetic assertion at line 407.
- `app/mariadb_catalog_service.py` -- `CatalogService.Session` (line 153) is the session factory the `product_ids` fixture uses.

## Tasks & Acceptance

**Execution:**
- [x] `tests/e2e/test_server.py` -- import `Product`, `Purchase`, `Attachment`, `ProductIdentifier`, `ProductTag` from `app.database` and add FK-ordered deletes for them to `clear_test_data()` before the `MaterialTaxonomy` delete -- catalog rows must not survive a test.
- [x] `tests/e2e/conftest.py` -- create; move `SCAN_INPUT`, `_gtin13`, `unstored_gtin`, `simulate_wedge_scan` here verbatim (with `unstored_gtin`'s docstring corrected to describe post-fix behavior) plus the `json`/`random`/`urllib.request` imports they need -- shared e2e machinery belongs beside the other shared fixtures, not in a test module.
- [x] `tests/e2e/test_wedge_scan.py` -- delete the four moved definitions, import them from `tests.e2e.conftest`, drop imports that become unused -- single definition site.
- [x] `tests/e2e/test_scan_routing.py` -- repoint line 32's import to `tests.e2e.conftest` and correct the module docstring's isolation note -- removes the sibling-module coupling.
- [x] `tests/unit/conftest.py` -- add a `product_ids` fixture: depends on `test_storage`, returns a zero-arg callable yielding `set[int]` of every `products.id`, bound directly to `test_storage.engine` -- lets tests assert over the product set. (Planned for the root `tests/conftest.py` and bound via `CatalogService`; both were corrected during review -- see Design Notes.)
- [x] `tests/e2e/test_clear_test_data.py` -- create; seed every table `clear_test_data()` is responsible for, clear, and assert nothing survived -- makes AC1 executable rather than assumed.
- [x] `tests/e2e/test_category_autocomplete.py`, `test_category_rename.py`, `test_product_tags.py` -- rewrite the isolation notes that assert the catalog accumulates -- the Always clause requires correcting any comment the truncation falsifies.
- [x] `tests/unit/test_product_routes.py` -- replace the five arithmetic assertions with `product_ids()` set comparisons, adding the fixture to each test signature -- assertions stop depending on autoincrement values.
- [x] `tests/unit/test_scan_routes.py` -- same replacement at line 407 -- ditto.

**Acceptance Criteria:**
- Given an e2e test that created a product with a purchase, attachment, identifier and tag, when the next test acquires `live_server`, then `products`, `purchases`, `attachments`, `product_identifiers` and `product_tags` are all empty and no `IntegrityError` was raised.
- Given `tests/e2e/test_scan_routing.py`, when its imports are inspected, then it imports nothing from `tests/e2e/test_wedge_scan.py`.
- Given `tests/e2e/test_wedge_scan.py`, when its module body is inspected, then `SCAN_INPUT`, `_gtin13`, `unstored_gtin` and `simulate_wedge_scan` are no longer defined there, and the names it still uses are imported from `tests.e2e.conftest`.
- Given the unit suite, when it runs, then no test asserts product absence via an id computed as `<some id> + 1` or a hardcoded `1`.
- Given `nox -s tests`, when it runs, then it passes with no new failures.

## Spec Change Log

_No bad_spec loopback occurred._

## Review Triage Log

### 2026-07-26 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 2, low 7)
- defer: 5: (high 0, medium 1, low 4)
- reject: 6: (high 0, medium 0, low 6)
- addressed_findings:
  - `[medium]` `[patch]` `clear_test_data()` swallowed every exception, so a wrong FK order would roll back the whole clear (photos and items included), print to captured stdout and let the entire suite pass green on stale data — the catalog e2e tests assert only positively, so nothing would notice. Now re-raises after rollback + print.
  - `[medium]` `[patch]` No executable assertion covered AC1: the new truncation was verified only by "the suite still passes", which per the finding above it would do either way. Added `tests/e2e/test_clear_test_data.py` — three tests seeding one row in every catalog table, pinning the FK delete order against real MariaDB, checking the inventory side and taxonomy re-seed still work, and covering the already-empty case.
  - `[low]` `[patch]` `product_ids` sat in the root `tests/conftest.py`, so it was offered to e2e tests, where a `CatalogService` bound to the per-test SQLite temp file would report an empty catalog forever. Moved to a new `tests/unit/conftest.py`.
  - `[low]` `[patch]` `product_ids` reached its engine through `CatalogService`, whose `getattr(storage, 'engine', None) or self._create_engine()` fallback would silently query `Config.SQLALCHEMY_DATABASE_URI` — making all six `== set()` assertions pass vacuously. Now binds `test_storage.engine` directly, with an assert if it is absent.
  - `[low]` `[patch]` The fixture docstring claimed the callable shape existed "so a test can sample before and after", which no call site does. Reworded to the actual reason (it must be sampled after the request under test runs).
  - `[low]` `[patch]` `test_an_unusable_quantity_rerenders_and_writes_nothing` and `test_an_overlong_receipt_field_rerenders_with_its_own_message` still requested `test_storage` after it stopped being referenced. Removed.
  - `[low]` `[patch]` `tests/e2e/conftest.py`'s docstring justified the move with "a test module that imports from a sibling test module is coupled to collection order" — false, since Python's import machinery is independent of pytest collection order. Replaced with the real reason (dependency direction; a helper must not be hostage to a test module's lifetime).
  - `[low]` `[patch]` `unstored_gtin`'s docstring reasoned from "the server is session-scoped", which is irrelevant because `live_server` is function-scoped and clears per test. Right conclusion, wrong premise; rewritten to cite the calling test's own earlier writes.
  - `[low]` `[patch]` The rewritten isolation notes in `test_category_autocomplete.py` and `test_category_rename.py` contradicted themselves — asserting "starts from an empty catalog" and then justifying positive-only assertions with "whatever else the shared e2e database holds". Aligned with the correct "'empty at setup' is not 'empty here'" rationale used in the other two modules.

### 2026-07-26 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 2, low 3)
- defer: 3: (high 0, medium 1, low 2)
- reject: 12: (high 0, medium 0, low 12)
- addressed_findings:
  - `[medium]` `[patch]` `test_clear_test_data.py`'s probe attachment could not exercise the FK edge its own comment claimed. `Attachment` carries `CheckConstraint('(product_id IS NULL) <> (purchase_id IS NULL)')`, so a single row can hold only one of the two FKs — the seeded row was purchase-owned, leaving `attachments → products` (one of the two edges the module docstring advertises pinning) untested, and the inline comment "it must go before purchases AND before products" false for that row. Now seeds two attachments, one per owner, with the comment corrected to say why it takes two.
  - `[medium]` `[patch]` `test_clear_test_data_still_clears_the_inventory_side_and_reseeds_materials` was half vacuous: it never seeded an `InventoryItem`, and `live_server` clears on the way in, so `assert InventoryItem.count() == 0` would have passed with the `session.query(InventoryItem).delete()` line deleted outright — the exact "green on stale data" failure the module exists to rule out, inside the module itself. It now seeds an `InventoryItem`, a `Photo` and an `ItemPhotoAssociation` (which also pins the `item_photo_associations → photos` order), asserts they landed, then asserts all three are empty. Every table is now seeded before the clear that is supposed to empty it.
  - `[low]` `[patch]` `test_clear_test_data_is_safe_on_an_already_empty_catalog` contradicted itself — the docstring said "`live_server` has just cleared, so this is the empty-input case" and then cleared twice anyway, with neither call distinguishable from the other. One call, docstring aligned, and the assertion widened to the inventory tables as well.
  - `[low]` `[patch]` The four rewritten isolation notes said `clear_test_data()` "truncates ``products`` along with photos, inventory items and the material taxonomy". The taxonomy is deleted and immediately re-seeded inside the same method — `test_clear_test_data.py` asserts it is NON-empty afterwards — so a reader writing a material-facing e2e test from those notes was being told the opposite of the truth. Reworded to "(and re-seeds the material taxonomy rather than leaving it empty)".
  - `[low]` `[patch]` The Code Map and Task 5 still placed `product_ids` in the root `tests/conftest.py` and routed it through `CatalogService`, both of which the previous review pass corrected in code; Task 5 was checked `[x]` against a location the fixture is not in, and neither `tests/unit/conftest.py` nor `tests/e2e/test_clear_test_data.py` nor the three docstring rewrites appeared in Tasks at all. Code Map and Tasks now record what shipped, with the review-time corrections noted inline.

## Design Notes

The `product_ids` fixture, a callable because it must be sampled after the request under test runs. It lives in `tests/unit/conftest.py` (created by this change) rather than the root `tests/conftest.py`: it reads the per-test SQLite database behind `test_storage`, which is not the database the e2e Flask server writes to, so offering it to e2e tests would hand them a fixture that reports an empty catalog forever. It binds `test_storage.engine` directly rather than going through `CatalogService`, whose `getattr(storage, 'engine', None) or self._create_engine()` fallback would silently point at `Config.SQLALCHEMY_DATABASE_URI` and make every `== set()` assertion vacuous.

```python
@pytest.fixture
def product_ids(test_storage):
    engine = getattr(test_storage, 'engine', None)
    assert engine is not None, '...'
    Session = sessionmaker(bind=engine)

    def _ids():
        session = Session()
        try:
            return {row[0] for row in session.query(Product.id).all()}
        finally:
            session.close()

    return _ids
```

Assertion translation: `get_product(1) is None` → `product_ids() == set()`; `get_product(existing + 1) is None` → `product_ids() == {existing}`; `get_product(pid + 1) is None` → `product_ids() == {pid}`.

`tests/e2e/conftest.py` holding plain functions (not fixtures) is deliberate: `SCAN_INPUT` has ~30 usages and converting `simulate_wedge_scan` to a fixture would churn every call site for no isolation gain. `tests/e2e/__init__.py` exists, so `from tests.e2e.conftest import ...` resolves to the same module object pytest itself loads.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: pass, no new failures.
- `venv/bin/python -c "import tests.e2e.test_scan_routing"` -- expected: imports cleanly, proving the helper move is complete (import check, not a test run — do not invoke `pytest` directly).
- `grep -n "test_wedge_scan" tests/e2e/test_scan_routing.py` -- expected: no import line.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` -- expected: pass. Needs a 20-minute harness timeout; run detached (nohup + poll) because it outlasts the Bash cap. Revert any screenshots the session rewrites.


## Auto Run Result

Status: done

**Summary.** Follow-up review pass over the already-implemented `e2e-test-infrastructure-hygiene` bundle (DW-38, DW-16). No intent gap and no spec defect: the shipped code does what the intent contract asks — `clear_test_data()` truncates the five catalog tables in FK-safe order, the three scan helpers live in `tests/e2e/conftest.py` with neither test module importing the other, and the autoincrement-arithmetic assertions are gone. What this pass found was that the test module the *previous* pass added to make AC1 executable did not fully execute it. Two of its three tests were partly vacuous, and both are now fixed and verified against real MariaDB.

**Files changed in this pass:**
- `tests/e2e/test_clear_test_data.py` — the probe now seeds two attachments (one product-owned, one purchase-owned) because `ck_attachment_one_owner` is an XOR and a single row can only exercise one of the two FK edges; the inventory-side test now seeds an `InventoryItem`, a `Photo` and an `ItemPhotoAssociation` before clearing instead of asserting emptiness on a database it never wrote to; the empty-catalog test clears once and says so. Shared `_counts()` helper; every table is seeded before the clear that is supposed to empty it.
- `tests/e2e/test_category_autocomplete.py`, `test_category_rename.py`, `test_product_tags.py`, `test_scan_routing.py` — the isolation notes said `clear_test_data()` "truncates ... the material taxonomy"; it deletes and immediately re-seeds it, which is the opposite of what a reader would infer.
- `_bmad-output/implementation-artifacts/spec-e2e-test-infrastructure-hygiene.md` — Code Map and Tasks now record where `product_ids` actually shipped (`tests/unit/conftest.py`, bound to `test_storage.engine`) and the two files the previous pass added that no task mentioned.
- `_bmad-output/implementation-artifacts/deferred-work.md` — three new entries (DW-112, DW-113, DW-114). Existing entries untouched, per the invocation.

**Review findings breakdown:** 5 patched (2 medium, 3 low), 3 deferred, 12 rejected. The medium patches are both "a test that would pass with the code it tests deleted": the attachment probe could not reach the `attachments → products` edge its own comment claimed to pin, and the inventory-side assertion ran against a database `live_server` had already cleared and the test never wrote to. DW-113 is the one deferral worth flagging — `setup_materials_data()` still swallows a failed taxonomy re-seed with no re-raise, the identical defect the previous pass patched as medium in `clear_test_data()` five lines away; it is deferred rather than patched because this sweep does not touch that method. Notable rejections: the spec's Never clause ("do not edit `deferred-work.md`", with the `{implementation_artifacts}` placeholder unrendered) reads as a contradiction with the workflow's own defer mechanism, but the invocation resolves it explicitly — append new entries, never modify existing ones; `review_loop_iteration: 0` alongside a populated triage log is the documented reset for a follow-up pass, not an inconsistency; the `unstored_gtin` error-handling and single-table `product_ids` findings restate DW-110 and DW-108; the hand-maintained `CATALOG_MODELS` list restates DW-107; and the "conftest.py is not an import target" objection was already weighed and rejected once, the intent contract naming that destination.

**Verification performed:**
- `nox -s tests` — 2571 passed, 370 deselected, 0 failed (27s).
- `nox -s e2e` — full run, detached: **369 passed, 1 skipped, 0 failed** (19:45). All three `test_clear_test_data.py` tests passed with the strengthened seeding, which is the only evidence that matters here: the new product-owned attachment, the `InventoryItem`/`Photo`/`ItemPhotoAssociation` seeds and the FK delete order they pin are only meaningful against MariaDB's real constraints. Screenshots rewritten by the run were reverted; the tree carries no `docs/images/screenshots/` change.
- `python -c "import tests.e2e.test_clear_test_data, tests.e2e.test_scan_routing, tests.e2e.test_wedge_scan, tests.e2e.conftest"` — clean.

**Residual risks:**
- DW-113: a failed taxonomy re-seed is still silent. One test (`test_clear_test_data_still_clears_the_inventory_side_and_reseeds_materials`) now asserts the taxonomy is non-empty after a clear, so it would go red — the other ~370 would not.
- DW-112: `clear_test_data()` still returns silently when `self.storage` is falsy. No test reaches that path today, since `live_server` depends on a started `e2e_server`.
- The delete list and `CATALOG_MODELS` remain two hand-maintained lists of the same tables (DW-107). The new module pins the current order but cannot discover a table absent from both.
