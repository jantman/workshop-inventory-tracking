---
title: 'Make the suggestion ORDER BY tiebreak total on MariaDB (DW-96)'
type: 'bugfix'
created: '2026-07-28'
status: 'done'
baseline_revision: '0591021b672576452d7fb59441f12e812ae990db'
final_revision: '0a7f1fec6ced3aacf74c18ec3df4fd3ca87b6819'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** Both suggestion readers end their `ORDER BY` with a bare `column` tiebreak (`app/mariadb_inventory_service.py:956,958`, `app/mariadb_catalog_service.py:739,741`) so the query plan stops choosing which spelling of a duplicated value the operator is offered — but under MariaDB's pinned folding `utf8mb4_unicode_ci` that tiebreak column compares case- and accent-insensitively too, so `McMaster` and `mcmaster` tie on every sort key and the first-seen-casing dedup keeps whichever row the plan emitted first. The ordering is total only under SQLite's BINARY collation, which is the only place the suite runs it, and that is exactly what let the divergence ship green.

**Approach:** Add one shared, dialect-aware order-key helper in `app/db.py` that yields `column COLLATE utf8mb4_bin` on MySQL/MariaDB and the bare column everywhere else, route both services' tiebreak through it, and prove the resulting determinism in the MariaDB integration tier that now exists — not only under SQLite.

## Boundaries & Constraints

**Always:**
- The collation clause is emitted **only** when `engine.dialect.name` is in `{'mysql', 'mariadb'}` — both names, per `app/database.py:31-35`; a `mariadb+pymysql://` URL reports `'mariadb'`.
- Under any other dialect the helper returns the column expression **unchanged** (identity), so SQLite keeps working and no `COLLATE` reaches it.
- The change is `ORDER BY`-only. Row membership, filters, rank tiers, `limit` clamping, the absent `.distinct()`, the unbounded read, `yield_per(SUGGESTION_ROW_BATCH)`, and the Python first-seen-casing dedup all stay byte-for-byte as they are.
- Both services keep behaving identically to each other; the tiebreak rule gets exactly ONE home.
- The code comments in both files that currently record this as deferred must be rewritten to state what the code now does. Do not leave them claiming the limitation.

**Block If:**
- A whitelisted suggestion column turns out not to be a `utf8mb4` text column (a binary/BLOB column cannot take `COLLATE utf8mb4_bin`).
- Making the ordering total on MariaDB would require changing which rows are returned.

**Never:**
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md` — the orchestrator records resolution.
- Do not add `.distinct()` back, do not re-introduce a fetch-row ceiling, and do not change the Python dedup key (`v.lower()`).
- Do not apply a collation to the `func.lower(column)` primary key — accent-adjacent grouping there is intended.
- Do not register a custom SQLite collation (that is DW-72, a separate item).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| MySQL/MariaDB dialect | `binary_order_key(col, 'mysql')` / `'mariadb'` | Expression compiling to `<col> COLLATE utf8mb4_bin` | No error expected |
| Non-MySQL dialect | `binary_order_key(col, 'sqlite')` / `'postgresql'` / `''` / `None` | The bare `col`, unchanged; no `COLLATE` in compiled SQL | No error expected |
| Case variants, MariaDB | Rows `mcmaster`, `MCMASTER`, `McMaster` in `vendor`; `get_field_value_suggestions('vendor')` | Exactly `['MCMASTER']` — the binary-lowest spelling, stable across repeated calls | No error expected |
| Case variants under a query | Same rows, `query='mc'` | Exactly `['MCMASTER']`; rank tiers still applied ahead of the tiebreak | No error expected |
| Accent variants, MariaDB | Rows `Café`, `Cafe` | Both offered (distinct Python dedup keys), in the deterministic binary order `['Cafe', 'Café']` | No error expected |
| Catalog half, MariaDB | `category_path` and `tags` variants differing only in case | Binary-lowest spelling offered, stable across repeated calls | No error expected |
| SQLite (whole unit suite) | Any existing suggestion call | Unchanged results; emitted SQL contains no `COLLATE` | No error expected |

</intent-contract>

## Code Map

- `app/db.py` -- owns `resolve_engine`, imported by both services; the natural single home for the new dialect-aware order-key helper.
- `app/mariadb_inventory_service.py` -- `get_field_value_suggestions` at 790-1008; `order_by` at 956/958; `self.engine` at 150; deferred comment at 983-990.
- `app/mariadb_catalog_service.py` -- `get_field_value_suggestions` at 590-796; `order_by` at 739/741; `self.engine` at 317; deferred comment at 771-778; column may resolve to `Product` or `ProductTag` via `_FIELD_SUGGESTION_MODELS`.
- `app/database.py:31-35, 903-906` -- precedent for dialect-scoped `utf8mb4_bin` (`with_variant(..., 'mysql', 'mariadb')`) and for why both dialect names matter.
- `migrations/versions/a977ca7315df_pin_explicit_charset_and_collation.py:168,679` -- `MYSQL_DIALECTS` branch shape; confirms `utf8mb4_bin` is the deployment's binary collation.
- `tests/integration/conftest.py` -- `integration_schema`, `integration_catalog_service`, `BINARY_COLLATION`, `database_default`; structural `integration` marker.
- `tests/unit/test_database_schema.py:63-69` -- `SERVER_DIALECTS = (mysql.dialect(), MariaDBDialect())`, the way this repo proves dialect-specific SQL without a server.
- `tests/unit/test_inventory_service.py:429-820`, `tests/unit/test_catalog_service.py:1455-1560` -- existing SQLite-only suggestion coverage that must stay green.

## Tasks & Acceptance

**Execution:**
- [x] `app/db.py` -- add `MYSQL_DIALECTS = frozenset({'mysql', 'mariadb'})`, `BINARY_COLLATION = 'utf8mb4_bin'`, and `binary_order_key(column, dialect_name)` returning `sqlalchemy.collate(column, BINARY_COLLATION)` for MySQL dialects and `column` otherwise -- one home for the rule both services must agree on, next to `resolve_engine`. No `>>>` examples (doctests run only under `app/utils/`).
- [x] `app/mariadb_inventory_service.py` -- import the helper and replace the trailing `column` in both `order_by` calls with `binary_order_key(column, self.engine.dialect.name)`; rewrite the 983-990 comment to state that the ordering is now total on both backends and how.
- [x] `app/mariadb_catalog_service.py` -- same two `order_by` edits and the same comment rewrite at 771-778, keeping the two halves mirrored.
- [x] `tests/unit/test_suggestion_order_collation.py` -- new: helper branch semantics for `mysql`/`mariadb`/`sqlite`/`postgresql`/`None`; compile the helper's output against `mysql.dialect()` and `MariaDBDialect()` asserting `COLLATE utf8mb4_bin`; assert the SQLite-compiled form has none; and assert BOTH services route their tiebreak through the helper by monkeypatching `binary_order_key` in each service module with a recording delegator and calling `get_field_value_suggestions` on the SQLite `test_storage` fixture, checking it was invoked with the suggestion column and the engine's dialect name.
- [x] `tests/integration/conftest.py` -- add an `integration_inventory_service` fixture modeled on `integration_catalog_service` (storage built from `integration_db_url`, `connect()` asserted, `close()` in `finally`, depending on `integration_schema`).
- [x] `tests/integration/test_suggestion_order_collation.py` -- new: prove the premise (on MariaDB the seeded case/accent variants really do compare equal under the pinned folding collation), then the Matrix's MariaDB rows for the inventory service (`vendor`, plus `sub_location` under a `location` scope) and the catalog service (`category_path`, `tags`), each asserted over repeated calls so a plan-dependent survivor cannot pass.

**Acceptance Criteria:**
- Given the pinned `utf8mb4_unicode_ci` schema and rows differing only in case, when either service's `get_field_value_suggestions` runs on MariaDB, then the offered spelling is the binary-lowest one and is identical on every repetition.
- Given a non-MySQL dialect, when either service builds its suggestion query, then the emitted SQL contains no `COLLATE` clause and every pre-existing suggestion test still passes unchanged.
- Given the two services, when the tiebreak rule is read, then it exists in exactly one place in `app/` and neither service's comments still describe it as deferred.

## Review Triage Log

### 2026-07-28 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 0, low 9)
- defer: 1: (high 0, medium 0, low 1)
- reject: 10: (high 0, medium 0, low 10)
- addressed_findings:
  - `[low]` `[patch]` The accent-adjacency integration assertion was green whether or not the `LOWER()` primary key stayed folding — `Cafe` < `Café` under both. Added `Cafex` (`VENDOR_ACCENT_NEIGHBOR`), which sorts *between* the pair under a binary primary key and after both under the folding one, so the invariant is now observable.
  - `[low]` `[patch]` The integration premise test probed `tests/integration/conftest.BINARY_COLLATION`, not the constant production sorts by; it now imports `BINARY_COLLATION` from `app.db`.
  - `[low]` `[patch]` Nothing asserted the collated branch was actually taken on the integration tier; the premise test now asserts `engine.dialect.name in MYSQL_DIALECTS` first, so a dialect-name change fails as itself rather than as an ordering bug.
  - `[low]` `[patch]` The module docstring claimed `REPETITIONS` catches a plan-dependent survivor. It does not (five identical calls return five identical wrong answers just as readily); reworded to credit the binary-highest-first seed order, which is what actually fails the old behavior, and to state what repetition does cover.
  - `[low]` `[patch]` The unit tests proved `binary_order_key` was *called*, not that its result is what the query sorts by — `order_by(rank, lower(c), binary_order_key(c), c)` would have stayed green while reverting the fix on MariaDB. Added `_assert_sorts_on`, which asserts the emitted ORDER BY ends with the `LOWER(col), col` pair; verified by negative control (injecting that exact drift fails the inventory test, 1 failed / 1 passed).
  - `[low]` `[patch]` `test_no_collate_reaches_sqlite` asserted only the absence of `COLLATE`, which also holds for a query with no tiebreak at all; both halves now assert the sort shape too, and the catalog half gained `test_the_child_table_field_sorts_on_its_own_column` for the `ProductTag`-sourced field.
  - `[low]` `[patch]` `binary_order_key`'s docstring now states the migrated-schema precondition explicitly: `COLLATE utf8mb4_bin` is legal only against `utf8mb4`, so a server that never ran migration `a977ca7315df` would answer error 1253 where it previously answered (nondeterministically). No runtime guard added — an `information_schema` probe per keystroke is not a trade worth making, and every other statement in the app already assumes the migrated schema.
  - `[low]` `[patch]` Dropped the unused `app` fixture dependency in the inventory unit-test class (`resolve_engine` adopts the storage's engine and never reaches `current_app`), matching the catalog class.
  - `[low]` `[patch]` Two docstrings corrected: the `sub_location` scope note read as its own opposite ("binary-lower than nothing"), and the tag seeds now say, as the category-path seeds already did, why a non-canonical spelling is the legitimate subject.
  - `[low]` `[defer]` Recorded below under *Deferred findings* rather than in the ledger, per the invocation's instruction not to edit `deferred-work.md`.

### 2026-07-28 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 0, low 9)
- defer: 2: (high 0, medium 1, low 1)
- reject: 10: (high 0, medium 0, low 10)
- addressed_findings:
  - `[low]` `[patch]` `binary_order_key`'s docstring opened with a factual error it contradicted ten lines above: "every text column in this schema is `utf8mb4_unicode_ci`" is false — `products.internal_id` is pinned `utf8mb4_bin` (`app/database.py:903-906`), which is the very precedent this change was modeled on. Rescoped to the columns the helper is actually called with, naming the exception.
  - `[low]` `[patch]` The claim "the ordering is now TOTAL" was overstated in three places. `utf8mb4_bin` is PAD SPACE, not NO PAD (verified against the live server: `'Cafe' = 'Cafe ' COLLATE utf8mb4_bin` is 1), so values differing only in trailing whitespace still tie on every key. Corrected at `BINARY_COLLATION` and in both service comments, together with why the residue is unobservable — the readers `.strip()` before offering — and which collation (`utf8mb4_nopad_bin`) would not have it.
  - `[low]` `[patch]` The same comments claimed the binary-lowest spelling "is offered on every call" on both backends. Per-backend determinism is not cross-backend agreement: SQLite's `lower()` folds ASCII only, so for case variants carrying non-ASCII letters its `LOWER()` key does not tie and this tiebreak never runs there. Scoped the claim to each backend separately and pointed at DW-72 for the divergence itself, which is now also ledgered (DW-225).
  - `[low]` `[patch]` `app/db.py`'s module docstring is entirely about engine lifetime and did not admit its new second responsibility; a paragraph now states why a SQL-expression helper lives there rather than in `app/utils/sql_text.py`, which the repo otherwise treats as the home for cross-service SQL-text rules.
  - `[low]` `[patch]` Both PUBLIC method docstrings still documented ordering as only "alphabetized (case-insensitive)" — the new guarantee about WHICH spelling a caller gets lived exclusively in inline implementation comments no API consumer reads. Both now state it, including that it is the most-uppercase spelling over ASCII and that accented/unaccented values are separate and both offered.
  - `[low]` `[patch]` The integration module docstring claimed the behavior was proven "for every whitelisted field"; the inventory service whitelists five and two are exercised. Replaced with what is actually covered and why — by query SHAPE, not by field.
  - `[low]` `[patch]` The catalog service's RANKED branch was exercised only for `category_path`, never for the `ProductTag`-sourced `tags` — the field the file itself argues is a genuinely different query. Added `test_tag_case_variants_under_a_query`, so both ORDER BY branches now run against both services on a real server.
  - `[low]` `[patch]` `test_the_stored_column_itself_cannot_distinguish_the_spellings` hard-coded `rows == 5` against a seed built from two constant tuples, so adding a spelling would fail as "the seed did not land" — the wrong cause. Derived from `len()` instead, and the surviving literal `2` is commented as the number of folding GROUPS.
  - `[low]` `[patch]` `_order_by_clause` measured offsets on `statement.upper()` and sliced the ORIGINAL string, which is correct only while the SQL stays ASCII (case mapping is not length-preserving). Replaced with a case-insensitive regex over the statement itself.

## Design Notes

The helper takes a dialect **name**, not an engine, so it stays pure and unit-testable, and so a duck-typed/mock storage whose `engine.dialect.name` is not a real dialect simply falls through to the identity branch.

```python
# app/db.py
def binary_order_key(column, dialect_name):
    if dialect_name in MYSQL_DIALECTS:
        return collate(column, BINARY_COLLATION)
    return column
```

Only the third sort key changes. `rank` and `func.lower(column)` are untouched: pure case variants already tie on both under every collation, so the tiebreak is the only key that can decide them, and leaving `LOWER()` folding is what keeps `cafe`/`café` adjacent in the offered list.

Precondition: the suggestion columns are `utf8mb4` because migration `a977ca7315df` pins them (DW-34). `COLLATE utf8mb4_bin` is valid for that charset family and invalid only for binary/BLOB columns, none of which are whitelisted (`thread_size`, `purchase_location`, `vendor`, `location`, `sub_location`, `category_path`, `tag`). No index-plan concern: this read is already a full ordered scan by design.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all unit tests pass, including the new `tests/unit/test_suggestion_order_collation.py`.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s integration` -- expected: the whole integration tier passes, including the new MariaDB determinism tests (requires Docker).
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: pass, unaffected.

## Auto Run Result

Status: done — DW-96 resolved; follow-up review pass complete.

**Implemented change.** Both `get_field_value_suggestions` readers ended their sort with a bare `column`, which is a tiebreak only under a collation that folds nothing. Under the deployed `utf8mb4_unicode_ci` it folded case and accents exactly like the `LOWER()` key ahead of it, so `McMaster` and `mcmaster` tied on every key and the plan — not the query — chose which spelling the operator was offered. A single dialect-aware helper, `app/db.py::binary_order_key`, now collates that one key to `utf8mb4_bin` on MySQL/MariaDB and returns the column unchanged everywhere else; both services route their tiebreak through it, and the determinism is proven against a real MariaDB rather than only under SQLite's BINARY collation.

**Files changed.**
- `app/db.py` — `MYSQL_DIALECTS`, `BINARY_COLLATION`, and `binary_order_key(column, dialect_name)`; the one home for the rule, next to `resolve_engine`.
- `app/mariadb_inventory_service.py` — both `order_by` calls route through the helper; the deferred-tiebreak comment rewritten to state what the code now does, and the public docstring now states which spelling a caller gets.
- `app/mariadb_catalog_service.py` — the mirrored edits.
- `tests/unit/test_suggestion_order_collation.py` (new) — helper branch semantics, per-dialect rendered SQL without a server, and proof that each service sorts by the helper's result.
- `tests/integration/conftest.py` — new `integration_inventory_service` fixture, the inventory counterpart of `integration_catalog_service`.
- `tests/integration/test_suggestion_order_collation.py` (new) — the premise (the deployed collation really does tie what the binary one separates) plus the behavior, for both services and both ORDER BY branches.

**Review findings breakdown (this follow-up pass).** 9 patches applied (all low severity, itemized in the Review Triage Log), 2 deferred (DW-224 medium, DW-225 low), 10 rejected. No intent gaps and no spec defects, across two passes.

What this pass actually found: no defect in the shipped behavior, but a set of claims the code made about itself that do not survive checking. The load-bearing one is that `utf8mb4_bin` is PAD SPACE rather than NO PAD, so "the ordering is now TOTAL" was false as written — harmless only because the readers `.strip()`, which nothing said. The rest were an outright factual error in the helper's docstring (it asserted a schema-wide collation the constant ten lines above it contradicts), a determinism claim that quietly generalized from MariaDB to SQLite, two public API docstrings that never learned the guarantee, and an integration docstring claiming coverage of five fields it exercises two of. No production code path changed in this pass; the executable additions are one integration test (the catalog ranked branch on the child table, the one query shape no test reached) and two test-helper corrections.

**Verification.** `nox -s tests`: 3409 passed, 2 skipped, 466 deselected. `nox -s doctests`: 22 passed. `nox -s integration`: 53 passed in 457s (real MariaDB testcontainer), including all 11 integration tests in the new file. Independently during review the fix was re-confirmed by negative control — forcing `binary_order_key` to its identity branch in both service modules fails 7 of the 9 behavioral integration tests (`['relay'] != ['RELAY']`, `['electronics/power'] != ['ELECTRONICS/POWER']`) while both premise tests still pass — and the PAD SPACE finding was established by probing the live server directly (`SELECT 'Cafe' = 'Cafe ' COLLATE utf8mb4_bin` → 1; under `utf8mb4_nopad_bin` → 0). `nox -s e2e` was not run: no template, CSS, or JS changed.

**Residual risks.**
- On a MySQL-family server whose migrations were never applied (columns still `latin1`/`utf8mb3`), `COLLATE utf8mb4_bin` is illegal and autocomplete would return HTTP 500 where it previously returned nondeterministic-but-valid suggestions. Documented in the helper's docstring; deliberately not guarded at runtime, because a per-request `information_schema` probe is not worth its cost and every other statement in the application already assumes the migrated schema. A `CAST(column AS BINARY)` key would avoid the precondition and be NO PAD besides, but it is a different expression than the intent contract froze, so it was not substituted under review.
- Integration coverage exercises `vendor` and `sub_location` of the five whitelisted inventory fields, plus both catalog fields. The remaining three share the identical code path and differ only in which column attribute is resolved.
- The `'mariadb'` half of `MYSQL_DIALECTS` cannot be exercised end-to-end: `tests/integration/conftest.py::_assert_safe_target` refuses any URL whose backend name does not start with `mysql`, so the testcontainer always reports `'mysql'`. That name is covered by the compile-only unit assertions, which is the technique this repo already uses for dialect-specific SQL.
- `utf8mb4_bin` is PAD SPACE, so values differing only in trailing whitespace still tie on every sort key. The Python `value.strip()` makes the winner unobservable at the output boundary, so the determinism claim holds where it is asserted — now stated in the code rather than only here.
- Which spelling wins is now contract, and it is the most-uppercase one. Recorded as DW-224 for a product decision, not a code one.

