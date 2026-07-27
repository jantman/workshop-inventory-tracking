---
title: 'MariaDB integration test session (DW-33, DW-35, DW-50, DW-85)'
type: 'chore'
created: '2026-07-27'
baseline_revision: '1689ef32399df5a4dbe7c44ccb305d7f2cc8bf6e'
final_revision: '4371bc6e7ba0757737859ffa28c746f139c98e1d'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** The repo promises an integration tier — `pytest.ini` names an `integration` marker, `testcontainers[mysql]==4.14.2` is a declared dependency, and `tests/test_database.py::mariadb_testcontainer` exists — but there is no `tests/integration/`, no test carries the marker, and no test at any level runs `CatalogService` or Alembic against MariaDB. Three mechanisms are therefore verified only by staging their failure under SQLite: the Alembic `upgrade`/`downgrade` pair (including Story 2.4's data backfill), `create_product`'s let-the-UNIQUE-constraint-arbitrate retry, and `add_identifier`'s duplicate rejection under `utf8mb4_unicode_ci` — the last of which the SQLite suite is actively *looser* about than production, so a green unit suite proves less than it appears to.

**Approach:** Stand up a real integration session — `tests/integration/` consuming the existing `mariadb_testcontainer`, a `nox -s integration` session, and a CI job — then write real-trigger tests for those three mechanisms plus a collation guard that fails loudly if the backend does not actually fold case/accents.

## Boundaries & Constraints

**Always:**
- Reuse the existing `mariadb_testcontainer` fixture; do not start a second container.
- Resolve the DB URL as `os.environ.get('SQLALCHEMY_DATABASE_URI') or config.TestConfig().SQLALCHEMY_DATABASE_URI`. Locally the container fixture sets the env var; under `CI=true` it yields `None` and the `TEST_DB_*`-derived `TestConfig` URL applies. Do **not** use `tests/test_database.py::mariadb_engine` — `TestConfig` overrides `SQLALCHEMY_DATABASE_URI` from `TEST_DB_*`, so that fixture ignores the container's random port and only works in CI.
- Every integration test carries `@pytest.mark.integration`.
- Trigger real backend behavior. No monkeypatching of `flush`/`Session` to fake an `IntegrityError`; monkeypatching `app.utils.internal_id.generate_internal_id` to force a *candidate* collision is allowed and required (the DB still arbitrates).
- Tests must be order-independent: reset schema per test rather than relying on file ordering.
- Drive Alembic with `alembic.config.Config()` built in-process, `script_location` set to an absolute path, and `os.environ['SQLALCHEMY_DATABASE_URI']` set for the call. Passing a config *file* would trigger `fileConfig()` in `migrations/env.py` and clobber pytest logging.

**Block If:**
- Docker is unavailable / the container cannot start (the fixture already `pytest.skip`s on missing `testcontainers`; a hard docker failure is a blocker, not a skip to paper over).
- `upgrade head` on a clean MariaDB database fails for a reason that is a genuine pre-existing migration defect rather than a test-harness mistake — report it, do not "fix" a migration to make a new test pass.

**Never:**
- Do not modify `app/` production code, `migrations/versions/*`, or the `deferred-work.md` ledger.
- Do not change `tests/unit/**` or `tests/e2e/**` behavior.
- Do not add integration tests to `nox -s tests` (it must stay SQLite-only and fast).
- Do not pin an explicit collation on ORM columns — that is a separate ledger item (DW-51); this work only *observes* the deployed collation.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Migration round trip | Empty MariaDB database | `upgrade head` succeeds; resulting schema shows no added/removed table or column vs `Base.metadata` | No error expected |
| 2.4 backfill | At rev `3beb9dff5e41`: product P1 (no identifier rows), P2 with a canonical global `INTERNAL` row, P3 with a vendor-scoped `INTERNAL` row | `upgrade 5aeb89e22451`: all products get distinct canonical 10-char `internal_id`; P2 adopts its value and gains **no** second row; P1/P3 each gain exactly one global `INTERNAL` row equal to their `internal_id`; P3's vendor-scoped row survives | No error expected |
| 2.4 downgrade | The state above | `downgrade 3beb9dff5e41`: `internal_id` column and `uq_products_internal_id` gone; derived + adopted global `INTERNAL` rows gone; P3's vendor-scoped row survives | No error expected |
| Full downgrade | At `head` | `downgrade base` succeeds; no application tables remain | No error expected |
| internal_id collision | Existing product holds id `X`; generator yields `X, X, FRESH` | `create_product` returns an int id; committed product carries `FRESH` with exactly one derived global `INTERNAL` row; generator called 3× | No error expected |
| Derived-row-only collision | A bare `product_identifiers` row `('INTERNAL', Y, '')` exists with no product carrying `Y`; generator yields `Y, FRESH` | Retry commits with `FRESH` | No error expected |
| Non-collision IntegrityError | A temporary `UNIQUE` index on `products.mpn`; creating a second product with a duplicate MPN | `create_product` returns `None`; generator called exactly once (no retry); product count unchanged | Original `IntegrityError` is re-raised internally, converted to `None` by the outer handler |
| Case-differing MPN | `add_identifier(A, MPN, 'SHARED-1')` then `add_identifier(B, MPN, 'shared-1')` | Second call raises `ValidationError`, `field == 'value'`, message names product A | ValidationError (SQLite accepts this today — the divergence) |
| Accent-differing MPN | `add_identifier(A, MPN, 'REF-1')` then `add_identifier(B, MPN, 'RÉF-1')` | Second call raises `ValidationError` | ValidationError |
| ECIA no-false-ambiguity | Only product A holds MPN `SHARED-1`; scan `[)>␞06␝1Pshared-1␞␄` | `resolve_scan` returns `product == A` with empty `free_text_hits` — a LANDING, not the ambiguity SQLite can stage | No error expected |
| Collation guard | Integration database | `product_identifiers.value`, `product_tags.tag` report collation `utf8mb4_unicode_ci` | Fail with a message stating the observed collation, since every folding assumption downstream depends on it |

</intent-contract>

## Code Map

- `tests/test_database.py:21` -- `mariadb_testcontainer` (session-scoped, `mariadb:11.8`, `MARIADB_COLLATION_SERVER=utf8mb4_unicode_ci`); sets `os.environ['SQLALCHEMY_DATABASE_URI']`. Consume as-is.
- `tests/conftest.py:203` -- `pytest_configure` is where markers are really registered (`pytest.ini` is inert, `[tool:pytest]` header). `integration` is already registered.
- `config.py:174` -- `TestConfig`; note it *overrides* `SQLALCHEMY_DATABASE_URI` from `TEST_DB_*` (default port 3307).
- `app/mariadb_catalog_service.py:203` `create_product` (retry loop, `INTERNAL_ID_MAX_ATTEMPTS = 5` at :62), `:180` `_internal_id_is_taken`, `:1651` `add_identifier`, `:2412` `resolve_scan` ECIA arm.
- `app/utils/internal_id.py` -- `generate_internal_id` / `is_valid_internal_id`; monkeypatch target is `'app.utils.internal_id.generate_internal_id'` (called as a module attribute).
- `app/database.py:819` `Product`, `:1011` `ProductIdentifier` + `uq_product_identifiers_type_value_scope` (:1044), `:1069` `ProductTag`.
- `migrations/env.py:26` -- URL from `os.environ['SQLALCHEMY_DATABASE_URI']` first; `:31` `fileConfig` guard; `target_metadata = Base.metadata`.
- `migrations/versions/5aeb89e22451_add_products_internal_id.py` -- validate → add nullable column → backfill/adopt → `NOT NULL` + unique constraint; downgrade drops constraint, correlated-deletes derived rows, drops column. Prior rev is `3beb9dff5e41`; head is `68707d1f48bf`.
- `noxfile.py` -- `tests` already excludes `integration`; `coverage` runs `-m "not e2e"` and must be tightened.
- `.github/workflows/test.yml:178` -- `e2e-tests` job with the `mariadb:11.8` service container; the new job mirrors it.
- `tests/unit/test_catalog_service.py:794` `TestInternalIdGeneration` -- the SQLite originals these tests mirror against the real backend.

_Added by the implementation:_
- `tests/integration/conftest.py` -- `REQUIRED_COLLATION`, `alembic_config()`, `integration_db_url` (session; resolves the URL **and** forces the database collation — see Design Notes), `integration_engine` (session), `_drop_all_tables`, `blank_database`, `integration_schema`, `integration_catalog_service`.
- `tests/integration/test_migrations.py` -- `alembic_env` fixture, `STRUCTURAL_DIFF_KINDS` (the diff kinds the drift check ignores, with the reasons), `TestMigrationRunner`, `TestInternalIdBackfill` (its `backfilled` fixture seeds the matrix's P1/P2/P3 at `3beb9dff5e41`).
- `tests/integration/test_catalog_service_internal_id.py` -- `_fake_generator` (the one sanctioned monkeypatch), `TestNonCollisionIntegrityError.unique_mpn_index` (temporary `UNIQUE` index, dropped in teardown).
- `tests/integration/test_identifier_collation.py` -- collation guard, `TestDuplicateIdentifierRejection`, `TestEciaScanUnderFoldingCollation`.

## Tasks & Acceptance

**Execution:**
- [x] `tests/integration/__init__.py` -- create empty package file -- matches `tests/unit` and `tests/e2e` layout.
- [x] `tests/integration/conftest.py` -- add `integration_db_url` (session), `blank_database` (function; drops every table incl. `alembic_version` with `FOREIGN_KEY_CHECKS=0`), `integration_schema` (function; `blank_database` + `Base.metadata.create_all`), `integration_catalog_service` (function; `MariaDBStorage` on the integration URL + `CatalogService`), and `alembic_config()` helper -- one place that owns URL resolution, isolation and Alembic wiring.
- [x] `tests/integration/test_migrations.py` -- migration-runner tests: `upgrade head` on a blank DB, schema-vs-`Base.metadata` drift check via `alembic.autogenerate.compare_metadata` (assert no `add_table`/`remove_table`/`add_column`/`remove_column` diffs; ignore type/default/index noise and record the ignored diff kinds in a comment), the 2.4 backfill/adopt/vendor-scope cases, the `downgrade 3beb9dff5e41` reversal, and a full `downgrade base` -- closes DW-33 and makes every future migration covered by the same runner.
- [x] `tests/integration/test_catalog_service_internal_id.py` -- the three `create_product` retry cases against InnoDB -- closes DW-35; proves the UNIQUE violation surfaces at `flush()` (not COMMIT) and that `_internal_id_is_taken`'s post-rollback re-query classifies correctly on the real backend.
- [x] `tests/integration/test_identifier_collation.py` -- collation guard (`information_schema.columns`) plus `add_identifier` case- and accent-differing rejection, exact-duplicate rejection, and the `resolve_scan` ECIA no-false-ambiguity case -- closes DW-85 and the identifier half of DW-50.
- [x] `noxfile.py` -- add an `integration` session (installs both requirements files, `pip freeze`, runs `python -m pytest -v -m integration --tb=short *posargs`, no `--blockage`); change `coverage`'s filter to `-m "not e2e and not integration"` -- integration tests need real sockets and must not leak into the coverage run.
- [x] `.github/workflows/test.yml` -- add an `integration-tests` job mirroring `e2e-tests` (same `mariadb:11.8` service, wait-for-ready step, `nox -s integration`, `TEST_DB_*` env, no Playwright/bluez steps) -- the marker's promise becomes an enforced one.

**Acceptance Criteria:**
- Given a clean checkout with Docker available, when `nox -s integration` runs, then every test in `tests/integration/` executes against a real MariaDB container and passes, and no test is skipped for a missing fixture.
- Given `nox -s tests` and `nox -s coverage`, when they run, then no integration test is collected and both remain green and SQLite-only.
- Given the integration suite, when any single test file is run alone or the files run in any order, then results are identical (no shared-state coupling).
- Given the case-differing MPN pair that `tests/unit/test_catalog_service.py` accepts under SQLite, when the same pair is submitted in the integration suite, then the second `add_identifier` is rejected — the divergence is now asserted rather than assumed.

## Spec Change Log

_No bad_spec loopback occurred; this section is empty by design._

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 13: (high 1, medium 4, low 8)
- defer: 1: (high 0, medium 1, low 0)
- reject: 8
- addressed_findings:
  - `[high]` `[patch]` `_drop_all_tables` would drop every table in whatever `SQLALCHEMY_DATABASE_URI` resolved to, and `config.py`'s `load_dotenv()` puts a developer's real URI there before the fixtures run (the container only displaces it when `CI` is unset). Added `_assert_safe_target`: the target must be a MySQL/MariaDB URL, must name a database, and that name must contain `test`. Verified by pointing the tier at `workshop_inventory_prod` — it fails before any DDL.
  - `[medium]` `[patch]` The new CI job omitted the `bluetooth libbluetooth-dev` step every other job has; `nox -s integration` installs `requirements.txt`, which builds PyBluez from source. Added the step (would have failed on cold pip cache and passed on warm).
  - `[medium]` `[patch]` Nothing asserted that the *migrated* schema carries `uq_products_internal_id` / `uq_product_identifiers_type_value_scope` / `uq_product_tags_product_tag` — the drift check ignores constraints and every other test runs on the `create_all` schema. Added `test_migrated_schema_carries_the_load_bearing_unique_constraints`.
  - `[medium]` `[patch]` The `integration` marker was applied by hand-written decorators with nothing enforcing it; a missed one both vanishes from `nox -s integration` and gets collected by `nox -s tests` under `--blockage`. Added `pytest_collection_modifyitems` in `tests/integration/conftest.py` to apply it structurally.
  - `[medium]` `[patch]` The collation guard was tautological — the fixture forces the collation, the test asserted the name it had just set. Added a direct folding probe (`'SHARED-1' = 'shared-1'`, `'REF-1' = 'RÉF-1'` under the column's own collation) to both the guard and a new migrated-schema test, and corrected the docstrings that claimed independent observation.
  - `[low]` `[patch]` CI wait-for-MariaDB loop could not fail (no `exit 1` on exhaustion) — fixed, plus a `Verify test database is reachable` smoke step and `timeout-minutes: 20`.
  - `[low]` `[patch]` The new CI job copied `MARIADB_CHARACTER_SET_SERVER` / `MARIADB_COLLATION_SERVER` from `e2e-tests` while the conftest documents them as inert; removed, with a comment saying why.
  - `[low]` `[patch]` `_fake_generator` let `StopIteration` escape into `create_product`'s `except Exception`, turning "supplied too few candidates" into an opaque `None`. Now `pytest.fail`s naming the cause.
  - `[low]` `[patch]` No InnoDB-level coverage of retry-budget exhaustion; added `test_retry_budget_exhausted_writes_nothing` (the case where a deferred UNIQUE check would leave a partial write).
  - `[low]` `[patch]` `BEFORE_INTERNAL_ID` / `INTERNAL_ID_REVISION` were bare hashes with no chain assertion; the `backfilled` fixture now asserts their adjacency and names the constants to update.
  - `[low]` `[patch]` `integration_db_url`'s docstring claimed `TestConfig` "rebuilds" its URL; it is a class attribute computed once at import. Corrected, including the consequence for anything setting `TEST_DB_*` late.
  - `[low]` `[patch]` `blank_database` shares one database with `e2e_server`; documented that only the two sessions' marker expressions keep them apart, and that `_drop_all_tables`' transaction is for connection handling, not atomicity.
  - `[low]` `[patch]` A new nox session documented nowhere; added an Integration Tests section to `docs/development-testing-guide.md` (incl. the collation note and the "not run by a bare `nox`" warning) and a line to `README.md`.
  - `[medium]` `[defer]` The tier runs under a collation only the harness creates: `MARIADB_COLLATION_SERVER` is inert, MariaDB 11.8 defaults to `utf8mb4_uca1400_ai_ci`, and no migration or model pins a collation — so a real deployment's folding behavior is still unenforced. This is DW-51's subject; recorded here rather than appended to the ledger, per the invocation instruction not to edit it.
  - Rejected as noise: concurrency/race coverage (outside the bundle's scope), the `unique_mpn_index` fixture as "fabricated schema" (it is the only way to get a *backend-raised* non-collision `IntegrityError`, which the spec sanctioned over a session double), duplication of `_envelope` and of the CI service block, `.pytest_cache` artifact usefulness, the `<=` table-subset assertion, `_rows` using `begin()` for SELECTs, and the all-tests-skipped-if-`testcontainers`-missing path (unreachable — the session installs `testcontainers[mysql]`).

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 2, low 7)
- defer: 5: (high 0, medium 2, low 3)
- reject: 13
- addressed_findings:
  - `[medium]` `[patch]` `TestInternalIdBackfill`'s docstring claimed the 2.4 backfill is "the only migration in the tree that reads and writes rows rather than only issuing DDL". `migrations/versions/f8e66632ee42_normalize_existing_category_paths.py` is labelled DATA ONLY in its own docstring and rewrites `category_path` rows. Corrected, naming the other migration and stating that the runner only ever applies it to an empty `products` table (the coverage gap is deferred as DW-118).
  - `[medium]` `[patch]` `nox -s integration` scoped by marker alone, so every module under `tests/e2e/` was imported on each run just to be deselected (19 selected, 2980 deselected) — an import-time error anywhere in that tree would fail the integration session for an unrelated reason. Added the `tests/integration` path argument; the marker stays as the second net. Collection is now 19 items.
  - `[low]` `[patch]` `pytest_collection_modifyitems` compared an unresolved `Path(__file__).parent` against item paths and used the deprecated `item.fspath`. A checkout reached through a symlink would have matched nothing and silently voided the "a forgotten decorator cannot drop a test" guarantee. Now resolves both sides and uses `item.path`; verified empirically with a decorator-less probe file, which `-m integration` selects.
  - `[low]` `[patch]` `_assert_safe_target` accepted any database name *containing* `test`, which also admits `latest_inventory` and `contest_results`. Tightened to a `_test` suffix or the exact name `test`; verified that `workshop_inventory_prod`, `latest`, `contest_results` and a SQLite URL are all refused while `workshop_inventory_test` passes.
  - `[low]` `[patch]` `test_downgrade_to_base_...` asserted only that the tables were gone, so a downgrade that dropped them but left `alembic_version` stamped would pass and make the next `upgrade head` skip every revision below the stamp. Added the assertion that no version row survives.
  - `[low]` `[patch]` `STRUCTURAL_DIFF_KINDS`' comment claimed add/remove of tables and columns is "the only class of difference that means the migrations and the models describe different data", while the ignore-list discards `modify_type` and `modify_nullable`. Comment corrected to state what the check cannot see and why the ignore is still the right trade.
  - `[low]` `[patch]` Setup calls treated `create_product`'s `Optional[int]` as an id, so a setup failure surfaced as `AttributeError` on `None` (or an FK error) rather than as itself. Added naming assertions in `two_products` and the three `test_catalog_service_internal_id.py` setups.
  - `[low]` `[patch]` `docs/development-testing-guide.md` promised the session "fails rather than skips" without a database; `mariadb_testcontainer` calls `pytest.skip` when the `testcontainers` package is missing, which would skip the tier and exit 0. Documented the actual behavior and why `requirements-test.txt` keeps the nox session off that path. Also corrected the stated runtime (~2.5 → ~3 minutes; measured 179s).
  - `[low]` `[patch]` The new README line had been inserted into a block claiming "100% success rates" with "Unit Tests: 66/66" and "E2E Tests: 20/20" — the unit suite is 2,610 tests. Replaced the stale counts with what each tier is and requires, plus a pointer to the testing guide and the note that a bare `nox` runs neither `integration` nor `e2e`.
  - `[medium]` `[defer]` DW-117: the tag/category folding mechanisms DW-50 was opened for (`set_product_tags`, `list_tags`, `find_products_by_tag`, `rename_category_path`) still have no MariaDB coverage — the spec scoped itself to the identifier half deliberately, so this is the remainder.
  - `[medium]` `[defer]` DW-118: `f8e66632ee42` runs on every integration test but always against an empty table, so the tree's other data migration — the one whose `SELECT DISTINCT` reasoning depends on the folding collation — is executed and never tested.
  - `[low]` `[defer]` DW-119: `5aeb89e22451`'s two `RuntimeError` abort branches, and its ordering claim that an abort is a no-op on the schema, are untested.
  - `[low]` `[defer]` DW-120: the `e2e-tests` job's wait-for-MariaDB loop still cannot fail — the identical bug fixed in the new job's copy, left alone because the spec forbids changing e2e behavior.
  - `[low]` `[defer]` DW-121: `MARIADB_CHARACTER_SET_SERVER`/`MARIADB_COLLATION_SERVER` remain set on the e2e service container and in `mariadb_testcontainer` despite being proven inert, so the e2e tier runs under whatever collation the image defaults to.
  - Rejected as noise: `base → head → base → head` re-appliability, a multiple-heads assertion, a non-`utf8mb4` collation guard, the `unique_mpn_index` fixture as "fabricated schema" (re-raised; rejected in the prior pass for the same reason), `FOLDING_COLUMNS`/`_envelope` duplication (deliberate and commented), richer CI failure artifacts (`docker logs`, junit), `integration-tests` lacking `needs:` (`e2e-tests` has none either — it matches the file's convention), the `test-summary` job labelling skipped/cancelled as FAILED (pre-existing pattern applied identically to all four jobs), bindparams-vs-f-string style within one test, the unrestored `ALTER DATABASE` (the target must be a test database by the guard above), the Bluetooth build-dep install cost, and enforcing the documented e2e/integration schema-collision hazard in code (hook-ordering-fragile, and the worst case is a broken test run on a test database, not data loss).

## Design Notes

Isolation without root: the container's app user owns only `workshop_inventory_test`, so tests cannot `CREATE DATABASE`. `blank_database` instead reflects and drops every table (including `alembic_version`) with `FOREIGN_KEY_CHECKS=0`, which needs no extra privilege and works identically against the CI service container.

Alembic wiring — build the config in-process so no cwd or `alembic.ini` dependency and no logging clobber:

```python
cfg = alembic.config.Config()
cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", integration_db_url)  # env.py reads this first
alembic.command.upgrade(cfg, "head")
```

Forcing a *non*-collision `IntegrityError` on the real backend (no fakes): create a product with `mpn='DUP-MPN'`, `CREATE UNIQUE INDEX` on `products.mpn` for the duration of the test, then call `create_product` with the same MPN. `_internal_id_is_taken` returns `False`, the error is re-raised inside the loop, and `create_product` returns `None` after exactly one candidate generation. Drop the index in teardown.

The collation guard is the load-bearing assertion of DW-50: if the deployed collation ever stops folding case/accents, `set_product_tags`' flush ordering, `find_products_by_tag`'s re-check and `rename_category_path`'s unclaimed-row handling all become elaborate no-ops. Assert the observed collation explicitly so that change fails a test rather than passing silently.

### Empirical findings from implementation (2026-07-27)

**The collation had to be forced.** `MARIADB_COLLATION_SERVER` / `MARIADB_CHARACTER_SET_SERVER` — set by `tests/test_database.py::mariadb_testcontainer` and by the CI service container — are **not** variables the official `mariadb` docker entrypoint interprets (it consumes `MARIADB_*` for credentials/database/init only; server variables must be passed as command-line args or a config file). Measured on `mariadb:11.8.8`: `collation_server = utf8mb4_uca1400_ai_ci`, the schema's default collation `utf8mb4_uca1400_ai_ci`, and therefore `product_identifiers.value` / `product_tags.tag` both created as `utf8mb4_uca1400_ai_ci` — *not* `utf8mb4_unicode_ci`. Both collations happen to be case- and accent-insensitive, so the folding assertions would have passed either way; the guard would not have. `integration_db_url` therefore issues `ALTER DATABASE ... CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci` once per session, before any `create_all`/`upgrade`, which needs only the `ALTER` privilege the app user already holds on its own database. The guard assertion remains and now observes the forced value independently. Note the consequence for DW-51: a real deployment created on MariaDB ≥ 11.6 without an explicit `COLLATE` gets `utf8mb4_uca1400_ai_ci`, so "the deployed collation is `utf8mb4_unicode_ci`" is an assumption the *application* still does not enforce anywhere.

**`upgrade head` and `downgrade base` both succeed on a blank MariaDB database** — no pre-existing migration defect surfaced. `alembic_version` ends up stamped at `68707d1f48bf`; `downgrade base` leaves only `alembic_version` behind.

**`create_all` raises no InnoDB index-size error.** `uq_product_identifiers_type_value_scope` is (32 + 255 + 255) × 4 = 2168 bytes, under the 3072-byte DYNAMIC-row-format limit, and `innodb_default_row_format = dynamic` on 11.8 (every created table reports `Dynamic`). The temporary `UNIQUE` index on `products.mpn` (1020 bytes) is likewise fine.

**`compare_metadata` reports zero diffs of any kind** between the migrated schema and `Base.metadata` on MariaDB — the ignore-list in `test_migrations.py` is defensive, not currently load-bearing.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s integration` -- expected: all integration tests pass against a live MariaDB container.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, unchanged count, zero integration tests collected.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s coverage` -- expected: green; no attempt to reach MariaDB.
- `venv/bin/python -m pytest tests/integration/test_migrations.py -m integration -p no:cacheprovider` (inside the nox env, for isolation checks) -- expected: passes standalone.


## Auto Run Result

Status: done

### Summary

Follow-up review pass over the MariaDB integration tier (no implementation loopback — no intent gaps, no bad spec). Two adversarial reviewers ran over the full diff since `1689ef3`; 9 findings were patched, 5 deferred as new ledger entries, 13 rejected. The two substantive patches were scope-of-collection and a factual error: `nox -s integration` was importing the entire `tests/e2e/` tree on every run in order to deselect it, and `TestInternalIdBackfill` documented the 2.4 backfill as the tree's only data migration when `f8e66632ee42_normalize_existing_category_paths` is one too. The rest were correctness-of-documentation and failure-diagnostics fixes, plus two small hardening changes to the tier's own guarantees (the structural marker hook and the destructive-target guard), each verified by direct probe rather than by assertion.

### Files changed (this pass)

- `tests/integration/conftest.py` — resolved-path + `item.path` in the marker hook; `_assert_safe_target` tightened from a `test` substring to a `_test` suffix / exact `test`.
- `tests/integration/test_migrations.py` — corrected the "only data migration" docstring and the `STRUCTURAL_DIFF_KINDS` comment; added the `alembic_version`-unstamped assertion to the `downgrade base` test.
- `tests/integration/test_catalog_service_internal_id.py`, `tests/integration/test_identifier_collation.py` — setup assertions so a `create_product` returning `None` names itself.
- `noxfile.py` — `integration` session now passes `tests/integration` alongside `-m integration`.
- `docs/development-testing-guide.md` — corrected the "fails rather than skips" claim and the stated runtime.
- `README.md` — replaced the stale "100% success rates / 66/66 / 20/20" testing block with an accurate description and a pointer to the testing guide.
- `_bmad-output/implementation-artifacts/deferred-work.md` — five new entries, DW-117 through DW-121 (appended only; no existing entry touched).

### Review findings

9 patches applied (0 high, 2 medium, 7 low), 5 deferred (2 medium, 3 low), 13 rejected. No intent gaps, no spec loopbacks. The itemized breakdown is in the Review Triage Log entry for this pass.

### Verification

- `nox -s integration` — **19 passed**, 179s. Collection is now 19 items rather than 19 selected out of 2,999.
- `nox -s tests` — **2610 passed**, 389 deselected (unchanged).
- `nox -s coverage` — **2610 passed**, 389 deselected, 63.79%; no MariaDB contact.
- Marker hook: a decorator-less probe file dropped into `tests/integration/` is selected by `-m integration` (probe removed afterwards).
- Safety guard: `workshop_inventory_prod`, `latest`, `contest_results` and a SQLite URL are all refused; `workshop_inventory_test` and `test` pass.

### Residual risks

- The tier's collation is a property of the harness, not of any deployment: `integration_db_url` forces `utf8mb4_unicode_ci` because nothing in the application pins one (DW-51, and now DW-121 for the e2e side). The guard proves the collation folds, not that a production database has it.
- DW-50 is marked resolved in the ledger, but only its identifier half is covered — DW-117 records the tag/category remainder.
- Two data migrations exist and one of them (`f8e66632ee42`) is applied on every run without ever seeing a row (DW-118).
