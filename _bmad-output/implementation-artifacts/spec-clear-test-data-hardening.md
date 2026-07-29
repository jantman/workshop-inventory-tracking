---
title: 'Make the e2e catalog clear self-maintaining and its silent paths loud'
type: 'refactor'
created: '2026-07-29'
status: 'done'
baseline_revision: 'c9fa92ac972dbdd1ac7e22ae79d0d302cf408d91'
final_revision: 'c3248bfe12d8f466d681e9417460ff1efda061a9'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `E2ETestServer.clear_test_data()` (`tests/e2e/test_server.py:312`) names nine ORM classes in a hand-maintained FK order that the next catalog table will silently invalidate, and its whole body sits under `if self.storage and hasattr(self, 'engine'):` — a guard that returns normally having cleared nothing; separately `setup_materials_taxonomy()` (:239) swallows a failed taxonomy re-seed, leaving every material-facing e2e test green on an empty vocabulary.

**Approach:** Derive the delete order from `Base.metadata.sorted_tables` instead of restating it, invert the guard into an early `RuntimeError`, and add the missing `raise` to the taxonomy seeder's exception handler so both remaining silent paths fail loudly.

## Boundaries & Constraints

**Always:**
- The delete order must come from `reversed(Base.metadata.sorted_tables)` — no hand-written table or model list remains in `clear_test_data`.
- `self.setup_materials_taxonomy()` still runs after a successful clear.
- The existing `except Exception` handler in `clear_test_data` keeps its rollback / print / `raise` shape and its explanatory comment (updated where the comment now describes removed code).
- `alembic_version` must remain untouched — it is not in `Base.metadata` and no code may add it there.
- Module-level imports in `tests/e2e/test_server.py` are trimmed to only names still used; `Base` stays (it is also used by `start()`).
- New tests must not require a running server or a network connection.

**Block If:**
- `Base.metadata.sorted_tables` turns out not to cover every table the hand-written list deleted (i.e. a model is registered on a different metadata).

**Never:**
- Do not change `add_material_taxonomy()` (:190) — it already re-raises.
- Do not relax `clear_test_data`'s re-raise back into a swallow.
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`.
- Do not restructure `start()`, `stop()`, or the `live_server` / `e2e_server` fixtures.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Started server, populated DB | `storage` and `engine` set; catalog + inventory rows present | Every table in `Base.metadata` emptied, taxonomy re-seeded, success message printed | No error expected |
| Started server, already-empty DB | `storage` and `engine` set; no rows | Same, no-op deletes succeed, taxonomy re-seeded | No error expected |
| Never started | fresh `E2ETestServer()`; `storage is None`, no `engine` attribute | `RuntimeError('clear_test_data: server not started, catalog NOT cleared')` | Raised before any session is opened |
| Stopped server | `storage` and `engine` both `None` (post-`stop()`) | Same `RuntimeError` — `hasattr(self, 'engine')` is True but the value is falsy | Raised before any session is opened |
| Delete fails mid-clear | e.g. a new table with an FK into one deleted below it | Rollback, `⚠️` message, exception re-raised | Re-raised (unchanged) |
| Taxonomy re-seed fails | `engine` bound to a schema without `material_taxonomy` | Rollback, error message + traceback printed, exception re-raised | Re-raised (new) |

</intent-contract>

## Code Map

- `tests/e2e/test_server.py` -- `E2ETestServer`; holds all three defects: `setup_materials_taxonomy` (:239, swallowing handler at :304-308), `clear_test_data` (:312, guard at :314, hand-written deletes at :320-331, re-seed at :348). Module imports at :18-21.
- `app/database.py` -- the single `declarative_base()` (:23) and all nine mapped classes; `Base.metadata.sorted_tables` is exactly those nine tables. `Product`'s docstring names further Epic 5 / Epic 10 tables — the reason to stop hand-maintaining the list.
- `tests/e2e/test_clear_test_data.py` -- pins clear behavior (catalog emptied, inventory emptied + taxonomy re-seeded, safe on empty DB). Asserts outcomes only, no call counts or ordering, so it survives the rewrite unchanged. Its module docstring describes the hand-written FK ordering and goes stale.
- `tests/conftest.py:163-176` -- `e2e_server` (session, start/stop) and `live_server` (function, calls `clear_test_data()` before yield). The only production caller; always called on a started server, never in teardown.

## Tasks & Acceptance

**Execution:**
- [x] `tests/e2e/test_server.py` -- in `setup_materials_taxonomy`, add `raise` as the last statement of the `except Exception` handler (after `traceback.print_exc()`), matching `add_material_taxonomy`'s handler five methods above -- a swallowed re-seed leaves the vocabulary empty and the suite green.
- [x] `tests/e2e/test_server.py` -- in `clear_test_data`, replace `if self.storage and hasattr(self, 'engine'):` with an early `if not (self.storage and getattr(self, 'engine', None)): raise RuntimeError('clear_test_data: server not started, catalog NOT cleared')` and dedent the body -- `stop()` sets both attributes to `None`, so the old guard admitted a half-stopped server and silently no-opped on a fully stopped one.
- [x] `tests/e2e/test_server.py` -- replace the nine `session.query(X).delete()` calls and their FK-ordering comment with `for table in reversed(Base.metadata.sorted_tables): session.execute(table.delete())`, keeping the trailing `session.commit()`, the print, the re-raising handler and the `setup_materials_taxonomy()` call -- the metadata already knows the FK order and stays correct as tables are added.
- [x] `tests/e2e/test_server.py` -- trim the `app.database` import at :18-19 to the names still used at module level, and update the `except` comment in `clear_test_data` so it no longer refers to "deleted below it" ordering that is now derived.
- [x] `tests/e2e/test_clear_test_data.py` -- add tests for the two newly-loud paths: `clear_test_data()` on a never-started and on a stopped `E2ETestServer` raises `RuntimeError`, and `setup_materials_taxonomy()` raises when its engine has no `material_taxonomy` table (bind an in-memory SQLite engine and a truthy dummy `storage`). Update the module docstring's FK-ordering prose to describe the metadata-driven clear.

**Acceptance Criteria:**
- Given a running e2e server with catalog and inventory rows, when `clear_test_data()` runs, then every table in `Base.metadata` is empty and `MaterialTaxonomy` is non-empty again.
- Given a new table is added to `Base.metadata` with an FK into an existing catalog table, when `clear_test_data()` runs, then it is cleared without any edit to `tests/e2e/test_server.py`.
- Given the alembic version table, when `clear_test_data()` runs, then it is not deleted from (it is absent from `Base.metadata`).
- Given `nox -s e2e`, when the full suite runs, then it passes with no new failures.

## Spec Change Log

_No bad_spec loopback occurred._

## Review Triage Log

### 2026-07-29 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 7: (high 0, medium 3, low 4)
- defer: 2: (high 0, medium 0, low 2)
- reject: 13: (high 0, medium 2, low 11)
- addressed_findings:
  - `[medium]` `[patch]` The clear became generic but its proof did not: `CATALOG_MODELS`/`INVENTORY_MODELS` are still hand-maintained, so a tenth model would be cleared with nothing asserting it — the same hand-maintenance this story removed, moved somewhere harder to notice. Added `test_every_metadata_table_is_covered_by_this_module`, which fails naming the uncovered table.
  - `[medium]` `[patch]` `test_setup_materials_taxonomy_raises_...` never reached the re-seed: the method opens with `session.query(MaterialTaxonomy).delete()`, so an engine with no tables failed there and the seeding loop never ran — a regression swallowing only the INSERT would have stayed green. Reworked to create a stub `material_taxonomy` table with just an `id` column, which accepts the bare DELETE and rejects the INSERT; the assertion now pins `StatementError.statement` to an INSERT.
  - `[medium]` `[patch]` `clear_test_data()`'s `rollback`/`raise` branch — the story's other loud path — had no direct test. Added `test_clear_test_data_rolls_back_and_re_raises_when_a_delete_fails` using an empty SQLite schema.
  - `[low]` `[patch]` The stopped-server test built the half-stopped state (`storage` truthy, `engine` None) while its docstring described `stop()`'s actual both-`None` state, and the `storage=None, engine=truthy` mirror was untested. Replaced the two guard tests with one parametrized test covering all four not-running states.
  - `[low]` `[patch]` The in-memory SQLite engines were never disposed. Added the `_detached_server` context manager, which disposes whatever engine it was handed.
  - `[low]` `[patch]` Module docstring inaccuracies: "the last two tests" for three tests; "no server and no network" while `E2ETestServer.__init__` binds a local socket; and an overclaim that the module "proves the metadata's answer survives those constraints" when `start()` builds the schema via `create_all` from the same metadata the sort reads. Reworded to state what the assertions actually catch.
  - `[low]` `[patch]` `tests/e2e/test_server.py:317` exceeded flake8's default 79 and black's 88. Wrapped the `RuntimeError` message, plus the four over-length lines the new tests introduced. `flake8 --select=F` on both files is now clean; the baseline had three `F401`s.

### 2026-07-29 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 0, low 6)
- defer: 3: (high 0, medium 0, low 3)
- reject: 15: (high 0, medium 2, low 13)
- addressed_findings:
  - `[low]` `[patch]` `test_clear_test_data_rolls_back_and_re_raises_when_a_delete_fails` asserted only the re-raise, so its name overclaimed. Verified the rollback is in fact unpinnable here: the failure is on the *first* DELETE, so nothing is pending to undo, and the `finally: session.close()` below the handler discards uncommitted work regardless — removing `session.rollback()` cannot turn any test red. Renamed to `test_clear_test_data_re_raises_when_a_delete_fails` and stated in the docstring what is verified and why the rollback is not.
  - `[low]` `[patch]` The same test's `assert 'DELETE' in ...` carried no failure message while its sibling carried a two-line one, so a regression printed a bare `assert False`. Added a message naming what the statement had to be and showing what it was.
  - `[low]` `[patch]` `test_setup_materials_taxonomy_raises_when_the_seeding_insert_fails` rested silently on a pooling default: a `sqlite://` database lives inside its connection, so the hand-created stub table is visible to the later session only because in-memory SQLite happens to default to a single-connection pool. Pinned with `poolclass=StaticPool` and a comment; without it the test would not have failed honestly, it would have failed on the DELETE with the message written to rule that out.
  - `[low]` `[patch]` The coverage tripwire's failure message ended `(or add it to the re-seeded set)`, naming nothing that exists in the code, and assumed the only way to trip it was adding a table — a *removed* table fails the same set equality and got told to go seed one. Rewritten to name the actual edit sites and cover both directions.
  - `[low]` `[patch]` The `INVENTORY_MODELS` comment ("the tables `clear_test_data()` handled before the catalog deletes were added") preserved a distinction the method can no longer make now that it names no tables at all. Reworded to say the split exists only for the assertions below it.
  - `[low]` `[patch]` `tests/e2e/test_server.py:324` — one comment line introduced by this story was 80 chars, one over flake8's default. Wrapped, so every line this story added to either file is clean.

## Design Notes

The clear becomes:

```python
if not (self.storage and getattr(self, 'engine', None)):
    raise RuntimeError('clear_test_data: server not started, catalog NOT cleared')
Session = sessionmaker(bind=self.engine)
session = Session()
try:
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
```

`sorted_tables` is topologically sorted parents-first, so `reversed()` is children-first — the same order the hand-written list encoded. This is one of the sanctioned SQLAlchemy-2.0-style `session.execute()` sites rather than a gratuitous rewrite of legacy `Query` code: `Table.delete()` has no `Query` equivalent, and the point of the change is to not name the mapped classes at all.

The `raise` added to `setup_materials_taxonomy` also makes `start()` (:71) fail loudly on a bad seed — intended, and the same trade-off already accepted for `add_material_taxonomy`.

Implementation note: the import-trim task also removed two pre-existing dead imports in the same file (`tempfile` at module level, `ItemType`/`ItemShape` from the function-local `app.models` import in `add_test_data`) so the file is F401-clean. No behavior change — `item_type` and `shape` are stored as strings.

The three new tests were confirmed to fail against `HEAD` before the change: pre-change `setup_materials_taxonomy()` returned `None` (swallowed), and pre-change `clear_test_data()` returned `None` on a never-started server and raised `UnboundExecutionError` (not `RuntimeError`) on a stopped one.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, unaffected by this change.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` -- expected: green, including all of `tests/e2e/test_clear_test_data.py`. Needs a 20-minute harness timeout; run detached and poll. Revert any screenshot files the session rewrites.
- `venv/bin/python -m flake8 tests/e2e/test_server.py` -- expected: no unused-import (F401) findings. Note: flake8 is not installed in `venv/`; it lives in the `lint` nox env, so the runnable form is `.nox/lint/bin/flake8`.

## Auto Run Result

Status: done
Blocking condition: none

**Implemented change.** `E2ETestServer.clear_test_data()` no longer names any table: it walks `reversed(Base.metadata.sorted_tables)`, so the FK-safe delete order is derived from the metadata that already knows it and a new catalog table is cleared without editing the method (DW-107). Its guard is inverted into an early `RuntimeError('clear_test_data: server not started, catalog NOT cleared')`, so the not-running case is as loud as the failing case instead of returning normally having cleared nothing (DW-112). `setup_materials_taxonomy()`'s `except` handler gained the missing `raise`, so a failed re-seed can no longer leave every material-facing e2e test green on an empty vocabulary (DW-113).

This follow-up review pass found no intent gaps and no spec defects; it changed no production behavior. Its six patches all landed in the proof around the change -- one test renamed to stop overclaiming, one hidden dependency on a SQLAlchemy pooling default made explicit, and four message/comment corrections.

**Files changed.**
- `tests/e2e/test_server.py` -- metadata-driven clear, inverted guard, `raise` added to the taxonomy seeder, module import reduced to `Base` (plus two pre-existing dead imports removed so the file is F401-clean).
- `tests/e2e/test_clear_test_data.py` -- 3 tests -> 10. Added a metadata-coverage tripwire, a 4-case parametrized guard test, a re-raise test, and a seeding-INSERT-failure test; docstring rewritten for the derived order and the corrected claims.

**Review findings (cumulative over both passes).** 13 patches applied (3 medium, 10 low), 5 deferred, 28 rejected, 0 intent gaps, 0 spec defects. The follow-up pass contributed 6 patches (all low), 3 deferrals (all low) and 15 rejections. See the Review Triage Log.

**Deferred findings.** The three from this pass are appended to `deferred-work.md` as DW-244 (`self.engine` is never initialized in `__init__`, so the class carries three inconsistent defenses and two sibling methods raise `AttributeError` instead of the `RuntimeError` they promise -- this subsumes the two findings the first pass could only record here), DW-245 (`start()` calls the now-raising `setup_materials_taxonomy()` outside any `try`, leaking the engine and storage connection), and DW-246 (the metadata-coverage tripwire needs no e2e infrastructure but is gated behind the ~20-minute e2e session). Note that this contradicts the `Never` clause "Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`": the orchestrator's invocation for this pass explicitly instructed that new findings be appended to the ledger as new entries. Only new entries were added; no existing entry was read for duplicates, modified, re-opened or rewritten.

**Verification performed.**
- `nox -s e2e` (full suite, ~30 min): `1 failed, 418 passed, 1 skipped, 3599 deselected, 3 rerun in 1832.77s`. All 10 tests in `tests/e2e/test_clear_test_data.py` passed. The 1 skip is the pre-existing `test_screenshot_metadata_summary`.
- The 1 failure is `test_move_items_sub_location.py::TestMoveItemsSubLocation::test_batch_move_mixed_sub_locations`, which is **pre-existing and already tracked as DW-124** -- the signature matches that entry exactly (`assert 'M2-B' == 'M11-Y'`, failed all four attempts under `--reruns=3`, passes in isolation). Confirmed here by re-running it alone: `1 passed in 49.50s`. It is a fixed-`wait_for_timeout` race in a wedge-scan flow, unreachable from this change, which touches only `clear_test_data()` and its own test module.
- Targeted run of the changed module after patching: `8 passed, 2 deselected in 29.35s`, including the real-MariaDB `live_server` path.
- `nox -s tests`: `3544 passed, 2 skipped, 473 deselected in 37.04s`.
- `.nox/lint/bin/flake8 --select=F,E9,E501` on both changed files: every line this story added is clean. The `E501`s that remain in `test_server.py` are pre-existing (the file has ~50), as are the four in `test_clear_test_data.py` above line 185 and its `F841 dimensions` / `E302`.
- Screenshot PNGs and `metadata.json` rewritten by the e2e run were reverted.

**Residual risks.**
- The order-pinning value of this module is weaker than its prose used to claim: `start()` builds the schema with `create_all` from the same metadata the sort reads, so the sort cannot contradict constraints it derived from. The docstring says so.
- An FK cycle added later would make `sorted_tables` emit a `SAWarning` (suppressed by `--disable-warnings`) and return an arbitrary order. Judged acceptable rather than guarded: the resulting wrong order fails the delete under MariaDB's constraints and the handler re-raises, so the outcome is a red suite rather than silent staleness.
- `clear_test_data()`'s `session.rollback()` cannot be pinned by any test, as this pass's patch documents in place: the `finally: session.close()` beneath it already discards uncommitted work, so the line is a statement of intent rather than load-bearing behavior.
- The e2e session's `--reruns=3` retries setup errors, so an *intermittent* clear failure is replayed rather than reported. A deterministic one still goes red on all four attempts (DW-124 is the proof of that). Considered and not acted on -- masking flakes is what the flag is for.

