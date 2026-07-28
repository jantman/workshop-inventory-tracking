---
title: 'DW-34: pin an explicit charset and per-column collation on every table'
type: 'chore'
created: '2026-07-27'
status: 'done'
baseline_revision: '796be6f'
final_revision: '9210919'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** No table or column in the schema declares a charset or collation, so every string comparison the catalog depends on — `product_identifiers` uniqueness, `product_tags` uniqueness, `products.category_path` prefix matching, `products.internal_id` scan lookup — runs under whatever the deployed MariaDB server default happens to be. `set_product_tags`' collision handling, `list_tags`' Python-side grouping and `rename_category_path`'s non-canonical-overlap refusal are all written against `utf8mb4_unicode_ci` semantics specifically, and a deployment on `utf8mb4_bin` or a future server default silently invalidates them.

**Approach:** Add one Alembic migration that converts every existing table to an explicit `utf8mb4` / `utf8mb4_unicode_ci`, then pins `products.internal_id` to `utf8mb4_bin` because it is a case-stable generated identifier whose validator (`is_valid_internal_id`) is deliberately case-sensitive. Mirror both decisions in the ORM models so `create_all` and the migrated schema agree, and cover the pinning with integration tests that run against a database whose own default collation is deliberately something else.

## Boundaries & Constraints

**Always:**
- The migration is MariaDB/MySQL-only DDL. Guard on `op.get_bind().dialect.name` and no-op on any other dialect (SQLite already has binary semantics and nothing to pin).
- Pre-flight before any DDL: check every UNIQUE constraint that spans a string column for rows that are distinct today but would collide under `utf8mb4_unicode_ci`, and raise a `RuntimeError` naming the table, constraint and offending values. MySQL commits DDL implicitly, so a duplicate-key failure partway through would strand a half-converted schema; the check must run first and abort with nothing changed.
- Model-side collation must be dialect-scoped via `.with_variant(...)` — a bare `String(32, collation='utf8mb4_bin')` renders `COLLATE utf8mb4_bin` into SQLite DDL and breaks the entire unit suite.
- `product_identifiers.value`, `product_identifiers.identifier_type`, `product_identifiers.vendor_scope`, `product_tags.tag` and `products.category_path` stay folding (`utf8mb4_unicode_ci`) — that is the semantics the catalog service is written against and the integration tier already asserts.
- Comments/docstrings that currently describe the collation as "whatever the server default happens to be" must be corrected to state the pinned value.

**Block If:**
- The pre-flight collision check cannot be expressed without changing which rows a live deployment would consider duplicates (i.e. a target collation would require deleting or rewriting existing rows to apply).

**Never:**
- Do not change `product_identifiers.value` to a binary collation, do not add per-type Python case folding to `add_identifier`, and do not alter `set_product_tags` / `list_tags` / `rename_category_path` behavior — this pins the semantics they already assume, it does not change them.
- Do not attempt to make SQLite agree with MariaDB (that is DW-72, a separate app-level engine change).
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`.
- Do not add a collation to BLOB/`MEDIUMBLOB`, JSON, numeric or datetime columns.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fresh upgrade | Blank MariaDB whose database default is `utf8mb4_bin` | `upgrade head` succeeds; every table's default is `utf8mb4`/`utf8mb4_unicode_ci`; every string column reports `utf8mb4_unicode_ci` except `products.internal_id` | No error expected |
| Folding preserved | Migrated schema | `product_identifiers.value` and `product_tags.tag` fold both case and accents (`'A'='a'`, `'É'='e'`) | No error expected |
| internal_id is binary | Migrated schema | `products.internal_id` does NOT fold: `'ABC1234567' = 'abc1234567'` is false, and both values insert without violating `uq_products_internal_id` | No error expected |
| Pre-existing collision | `product_tags` holds `(1,'cafe')` and `(1,'café')` before the upgrade | Migration aborts before issuing any DDL; schema unchanged | `RuntimeError` naming `product_tags`, `uq_product_tags_product_tag` and the colliding values |
| Non-MySQL dialect | Alembic run against SQLite | Both `upgrade` and `downgrade` are no-ops and succeed | No error expected |
| Downgrade | Migrated MariaDB schema | Every table and `products.internal_id` return to the *database* default charset/collation (`@@character_set_database` / `@@collation_database`) | No error expected |
| Model/migration parity | `Base.metadata.create_all` on MariaDB | Produces the same charset/collation per table and per column as the migration does | No error expected |

</intent-contract>

## Code Map

- `app/database.py` -- all 9 ORM tables. Add `mysql_charset`/`mysql_collate` to each `__table_args__`; give `Product.internal_id` a `.with_variant()` binary collation (line ~842); correct the `ProductTag` docstring's collation claim (~line 1084).
- `migrations/versions/68707d1f48bf_add_product_tags_table.py` -- current HEAD; the new migration's `down_revision`.
- `tests/integration/conftest.py` -- `integration_db_url` forces the DB default to `utf8mb4_unicode_ci` and its docstring says the schema pins nothing (DW-51); that caveat is now stale.
- `tests/integration/test_migrations.py` -- `FOLDING_COLUMNS` behavioral check on the migrated schema; extend here.
- `tests/integration/test_identifier_collation.py` -- same check against the `create_all` schema.
- `app/mariadb_catalog_service.py` -- `resolve_scan`/`_matches` (~2350-2380) describe `products.internal_id` equality as backend-dependent (DW-73); with `utf8mb4_bin` MariaDB now agrees with SQLite. Comment correction only.
- `app/utils/internal_id.py` -- `is_valid_internal_id` is explicitly case-sensitive; the rationale for the binary choice.
- `noxfile.py` -- `integration` session (`-m integration tests/integration`, requires Docker).

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/` -- generate a revision with `venv/bin/python manage.py db migrate -m "pin explicit charset and collation" --no-autogenerate`, then hand-author it: dialect guard, pre-flight collision check, `ALTER TABLE <t> CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci` for all 9 tables, then `ALTER TABLE products MODIFY internal_id VARCHAR(32) NOT NULL COLLATE utf8mb4_bin`. Downgrade converts back to the live database default. Docstring must state that `CONVERT TO CHARACTER SET` rebuilds each table and leaves BLOB columns untouched. -- the deployed behavior must stop depending on the server default.
- [x] `app/database.py` -- add `{'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}` as the trailing dict of every `__table_args__` (all 9 tables); change `internal_id` to `Column(String(32).with_variant(String(32, collation='utf8mb4_bin'), 'mysql'), nullable=False)` with a comment giving the reason. -- so `create_all` and the migration describe one schema.
- [x] `app/database.py`, `app/mariadb_catalog_service.py` -- correct the comments that describe the collation as the server default or `products.internal_id` equality as backend-dependent, stating the pinned collations instead. -- stale rationale is worse than none.
- [x] `tests/integration/test_migrations.py` -- assert the migrated schema's per-table default charset/collation and per-column collation (including the `utf8mb4_bin` exception), assert `internal_id` does not fold while the folding columns do, and add a test that runs the chain against a database whose default collation is deliberately NOT the target and still gets the pinned values (restore the default in a `finally`). -- pinning is only proven when the inherited value would have differed.
- [x] `tests/integration/test_migrations.py` -- add a pre-flight test: seed two rows into `product_tags` that differ only by accent at the revision before this one, then assert `command.upgrade` raises naming the constraint and that no table gained the new collation. -- the abort-before-DDL guarantee.
- [x] `tests/integration/test_identifier_collation.py` -- extend the `create_all`-schema guard to the same per-column collation expectations. -- the two schemas are maintained independently.
- [x] `tests/unit/test_database_schema.py` (new or existing equivalent) -- assert `Product.__table__.c.internal_id.type` compiles to `VARCHAR(32) COLLATE utf8mb4_bin` under the MySQL dialect and to plain `VARCHAR(32)` under SQLite, and that every table carries the `mysql_charset`/`mysql_collate` kwargs. -- catches a missing `with_variant` without needing a database.
- [x] `tests/unit/test_database_schema.py` -- add a dialect-guard test: stamp a temp SQLite database at the preceding revision, then `upgrade`/`downgrade` across the new one and assert both complete. -- the guard is one `if` per direction and nothing else in the suite runs Alembic off MariaDB.
- [x] `tests/integration/conftest.py` -- update the `integration_db_url` docstring: the DB-level force is now a contrast baseline, not the only thing setting the collation. -- the DW-51 caveat it records is resolved.

**Acceptance Criteria:**
- Given a MariaDB database whose own default collation is `utf8mb4_bin`, when `alembic upgrade head` runs, then `information_schema.columns` reports `utf8mb4_unicode_ci` for every string column except `products.internal_id`, which reports `utf8mb4_bin`.
- Given the migrated schema, when two products are inserted whose `internal_id` values differ only in case, then both rows persist and `uq_products_internal_id` is not violated.
- Given the migrated schema, when two `product_identifiers` rows are inserted whose `value` differs only in case or accent, then the second is rejected by `uq_product_identifiers_type_value_scope`.
- Given `product_tags` already holds two rows that fold together under the target collation, when the migration runs, then it raises before issuing DDL and the tables retain their prior collation.
- Given a SQLite database stamped at the preceding revision, when this revision is applied and then reversed, then both directions complete as no-ops and the unit suite is unaffected. (Narrower than "the whole chain applies to SQLite", which is false and predates this work: `dce1254cd381` issues `ALTER TABLE ... MODIFY COLUMN ... MEDIUMBLOB`, which SQLite rejects.)
- Given the full chain, when `alembic downgrade base` runs, then it completes and leaves only `alembic_version`.

## Spec Change Log

## Review Triage Log

### 2026-07-28 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 17: (high 0, medium 5, low 12)
- defer: 1: (high 0, medium 0, low 1)
- reject: 3
- addressed_findings:
  - `[medium]` `[patch]` The model-side pin was inert under a `mariadb+pymysql://` URL — SQLAlchemy resolves dialect kwargs and `with_variant()` on `dialect.name`, which is `mariadb`, not `mysql`, for that scheme; verified that `create_all` then emitted a bare `CREATE TABLE`. Added the `mariadb_charset`/`mariadb_collate` pair and `with_variant(..., 'mysql', 'mariadb')`, and made every unit assertion run against both server dialects.
  - `[medium]` `[patch]` `downgrade()` had no pre-flight, though it moves `internal_id` from binary to a folding default (tightening uniqueness) with `products` fifth in the list — the same stranded half-converted schema the upgrade guards against. Added the same check against the collation being restored.
  - `[medium]` `[patch]` `downgrade()` would `CONVERT TO` a narrower database default, silently replacing unrepresentable characters with `?`. Now refuses unless the default is utf8mb4.
  - `[medium]` `[patch]` `COLLISION_CHECKS` was hard-coded from the models, but the pre-flight exists to protect a deployed schema that need not match them (this repo documents surviving `uq_ja_id_active` indexes). Replaced with discovery from `information_schema.statistics`, including prefix-index and functional-index handling.
  - `[medium]` `[patch]` Nothing covered the NULL-key exclusion, whose regression would abort the upgrade on essentially every real deployment (`purchases.request_key` is NULL until Epic 7). Added `test_rows_with_a_null_unique_key_are_not_a_collision`.
  - `[low]` `[patch]` The reported collision count was capped by `LIMIT` while the comment promised a real total; now counted separately from the sample.
  - `[low]` `[patch]` `GROUP_CONCAT` truncated the offending values at 1024 bytes with only a warning; `group_concat_max_len` is raised for the session.
  - `[low]` `[patch]` `products.attributes` (JSON) IS converted by `CONVERT TO CHARACTER SET` on MariaDB, contradicting the docstring and diverging from `create_all`. Restored in both directions and asserted.
  - `[low]` `[patch]` Alembic offline/`--sql` mode got past the dialect guard and died with a `TypeError` after emitting a script whose safety check had not run; now refused explicitly in both directions.
  - `[low]` `[patch]` The migrated-charset assertion was keyed on `table_name`, collapsing ~100 per-column rows onto 9 entries; re-keyed on `(table, column)`.
  - `[low]` `[patch]` That same assertion included `alembic_version`, contradicting the tier's own stated policy; excluded by name.
  - `[low]` `[patch]` `CONTRAST_COLLATION` equalled `BINARY_COLLATION`, so the one behaviorally load-bearing pin was the one the contrast tests could not prove. Split into `CONTRAST_COLLATION` (`utf8mb4_general_ci`, differs from both pins) and `NON_FOLDING_COLLATION` (`utf8mb4_bin`, for tests that must seed a foldable collision).
  - `[low]` `[patch]` `database_default()` accepted a `charset` argument its restore ignored; parameter removed.
  - `[low]` `[patch]` `assert_schema_is_pinned` pre-filtered to model tables, so extra tables/columns could never fail it; both set comparisons are now two-directional.
  - `[low]` `[patch]` The unit dialect-guard test copied the revision-pair constants but not the chain guard its integration counterpart has; added.
  - `[low]` `[patch]` The migration docstring named the wrong widest index (the composite identifier UNIQUE at 2168 bytes, not `category_path`), cited only InnoDB's 3072-byte DYNAMIC limit while raising the latin1 case that would be on a 767-byte row format, and understated the BLOB-proportional rebuild cost. Corrected.
  - `[low]` `[patch]` Fixed a mangled line-wrap left by a comment edit in `app/mariadb_catalog_service.py`.

Deferred finding (NOT written to `deferred-work.md` — the invocation reserves every ledger write to the orchestrator; carry it forward from here):
- `[low]` The Alembic chain as a whole is incompatible with offline/`--sql` mode. `8213852b0b94`, `56dc95692b79`, `f8e66632ee42` and `5aeb89e22451` all read or write rows through `op.get_bind()`, so "generate the SQL, hand it to a DBA" has never worked for this project. Pre-existing; `a977ca7315df` now refuses that mode explicitly rather than adding a fifth silent failure.

Rejected: a `LOCK TABLES` window between the pre-flight and the first `ALTER` (heavier than the race it addresses, for a single-operator application whose migrations run against a quiesced database); `database_default()`'s restore masking an in-block failure if the restore itself raises; and the observation that DW-51/DW-73 remain open in the ledger while the new comments describe them as closed (ledger writes belong to the orchestrator).

### 2026-07-28 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 14: (high 0, medium 3, low 11)
- defer: 2: (high 0, medium 1, low 1)
- reject: 3
- addressed_findings:
  - `[medium]` `[patch]` `upgrade()` had no source-charset guard while `downgrade()` did, so a non-utf8mb4 deployment was converted rather than refused — and that conversion is a WIDENING with three consequences nothing here could see. Confirmed empirically against a latin1 database: it silently promotes `TEXT` to `MEDIUMTEXT` on `inventory_items.notes`, `material_taxonomy.aliases`, `material_taxonomy.notes` and `products.notes`, permanently breaking the model/migration parity this revision exists to establish (every check compares collations and charsets, never column types); it leaves `downgrade()` refusing forever, since it will not convert back to a narrower default; and it grows index keys past the 767-byte limit of the `COMPACT`/`REDUNDANT` row formats, which the docstring named as a precondition and nothing enforced — that failure would have landed mid-loop, stranding exactly the half-converted schema the pre-flight exists to prevent. Added `_abort_on_wide_charset`, checking both table defaults and per-column charsets, plus `test_upgrade_refuses_a_schema_that_is_not_already_utf8mb4`.
  - `[medium]` `[patch]` `_collisions` appended `COLLATE` to every key term, including the non-character ones `_unique_indexes` had deliberately left bare. On a deployed unique index mixing a VARCHAR with a VARBINARY column that is `ERROR 1253`, not a no-op — the pre-flight would crash instead of passing or aborting cleanly, on exactly the divergent deployed schema whose existence justifies discovering indexes from `information_schema`. Key terms now carry a `collatable` flag, and `binary` is treated as "not a character column" alongside NULL.
  - `[medium]` `[patch]` The downgrade's conversion path had never executed against MariaDB with a default that differs from the target — `test_downgrade_to_base_removes_every_application_table` runs at `utf8mb4_unicode_ci`, so its `CONVERT TO` is a no-op. Added `test_downgrade_restores_the_database_default`, which also proves `products.internal_id` gives up its per-column binary pin.
  - `[low]` `[patch]` `TABLES` is a fixed list against a deployed schema, so a dropped table surfaced as `ERROR 1146` from whichever `ALTER` reached it, with every earlier table already converted and committed. Added `_abort_on_missing_tables` in both directions, plus a test.
  - `[low]` `[patch]` Expression-based unique indexes were named only inside the failure message, so the one outcome where it matters — the migration proceeding having not checked one — was the silent one. Now logged unconditionally through Alembic's runtime logger.
  - `[low]` `[patch]` `not_null_columns` held the NULLable columns and its own docstring said so, inverting the name in the one function with no way to fail loudly. Renamed to `nullable_columns`.
  - `[low]` `[patch]` The sample query had `LIMIT` with no `ORDER BY`, so an operator fixing the ten reported groups and re-running could be shown a different arbitrary ten — contradicting the workflow `MAX_REPORTED_GROUPS`' comment commits to. Ordered by the grouping.
  - `[low]` `[patch]` `group_concat_max_len` was raised 1024x on Alembic's own connection and never restored, leaking to every later revision in the same `upgrade head` run. Now saved and restored in a `finally`.
  - `[low]` `[patch]` `GROUP_CONCAT` truncation past the raised 1 MiB cap was still silent. Samples at or over the cap are now marked truncated.
  - `[low]` `[patch]` `_is_online(bind)` ignored its only parameter — the same class of defect the previous pass fixed in `database_default()`. Parameter removed.
  - `[low]` `[patch]` The `sub_part` prefix-index branch — the only reason `_unique_indexes` emits `LEFT(...)`, and the one that stops the check UNDER-reporting — was dead code under test. Added `test_preflight_compares_only_a_prefix_indexs_prefix`, whose two values collide only in their first five characters.
  - `[low]` `[patch]` The `uq_products_internal_id` transient the docstring devotes a paragraph to (folding `CONVERT TO` runs before the binary `MODIFY`) was argued but never asserted. Added `test_preflight_catches_an_internal_id_collision`.
  - `[low]` `[patch]` `test_folding_columns_use_the_expected_collation`'s rewritten docstring claimed "a rename or a new collation that preserved the folding should not fail here", which both of its assertions falsify — the first is a hard name comparison and the second interrogates string literals, never the columns. Corrected to state what each assertion can and cannot see.
  - `[low]` `[patch]` `BINARY_COLUMNS` was duplicated across the unit and integration tiers with no rationale, in a file that explicitly justifies its other duplications. Documented, including why the duplication is safe (both tiers fail loudly, naming the same column).

Deferred (appended to `deferred-work.md` as NEW entries, per the invocation):
- `[medium]` DW-196 — `photos.medium_data`, `photos.original_data` and `attachments.content` use `.with_variant(MEDIUMBLOB, 'mysql')` without `'mariadb'`, so `create_all` under a `mariadb+pymysql://` URL builds 64 KB `BLOB`s. Pre-existing; confirmed by compiling the DDL against both dialects. Production is unaffected (the chain issues an explicit `MODIFY ... MEDIUMBLOB`); the `create_all` path is not.
- `[low]` DW-197 — the Alembic chain as a whole is incompatible with offline/`--sql` mode. Carried forward from the previous pass, which was barred from writing to the ledger.

Rejected: the concurrent-write race between the pre-flight and the first `ALTER` (already rejected last pass — `LOCK TABLES` is heavier than the race it addresses for a single-operator application whose migrations run against a quiesced database); the claim that the change's motivation does not survive checking, on the grounds that MariaDB 11.8's `utf8mb4_uca1400_ai_ci` default folds case, accents and trailing spaces exactly as `utf8mb4_unicode_ci` does (true, and not a contradiction — every statement in the comments is factually accurate, and "correct only by accident" means "correct without guarantee", which is precisely the condition being fixed); and the untested `total != len(samples)` reporting path (a cosmetic count in an abort message, with no behavioral consequence).

### 2026-07-28 — Review pass (follow-up 2)
- intent_gap: 0
- bad_spec: 0
- patch: 15: (high 0, medium 1, low 14)
- defer: 0
- reject: 7
- addressed_findings:
  - `[medium]` `[patch]` Nothing checked the two columns the post-conversion `MODIFY`s name, and those are the only DDL in the revision with nine implicitly-committed `ALTER`s in front of them. A deployment missing `products.internal_id` or `products.attributes` reached `ERROR 1054` with the whole schema already converted; worse, because MySQL's `MODIFY` REPLACES a definition rather than patching it, a deployment whose `internal_id` was wider than `VARCHAR(32)` would have been silently truncated by the statement whose only intended effect is a collation. Added `_abort_on_missing_columns`, which pins presence, `data_type`, nullability and length in both directions.
  - `[low]` `[patch]` `_unique_indexes` applied a prefix index's `sub_part` only to collatable members, so a UNIQUE index mixing a VARCHAR with a BLOB prefix grouped on the WHOLE blob and UNDER-reported — letting the conversion through to the duplicate-key failure the pre-flight exists to prevent. The prefix is now applied to every member. Proven non-vacuous: with the fix reverted, the new test below fails.
  - `[low]` `[patch]` A key term over a binary column makes `CONCAT_WS`/`GROUP_CONCAT` return binary, so the sample came back as `bytes` and `len(sample.encode(...))` raised `AttributeError` — replacing the actionable abort with a traceback from the code that formats it. Samples are now decoded with `errors='replace'`, and the truncation length is measured on the original bytes. Also proven non-vacuous (reverting it turns the abort into a `TypeError`).
  - `[low]` `[patch]` `GROUP_CONCAT` is bounded by `max_allowed_packet` as well as by `group_concat_max_len`, so on a server configured below 1 MiB the raise did not prevent silent truncation and the length check could not see it. The session value and the truncation threshold now both come from `_group_concat_cap`, the minimum of the two.
  - `[low]` `[patch]` `_abort_on_missing_tables` queried `information_schema.tables` without filtering `table_type`, so a VIEW carrying one of the nine names satisfied the presence check and then failed its `ALTER` with `ERROR 1347` mid-loop. Restricted to `BASE TABLE`.
  - `[low]` `[patch]` No check covered FOREIGN KEYs over character columns, which `CONVERT TO CHARACTER SET` breaks by moving one side of the pair before the other (`ERROR 3780`), again mid-loop. The docstring's "all foreign keys here are over INTEGER columns" is true of the MODELS, and the pre-flight exists precisely because a deployed schema need not match them. Added `_abort_on_string_foreign_keys`.
  - `[low]` `[patch]` `downgrade()` omitted `_abort_on_wide_charset` although it also converts to utf8mb4, so a narrower column added by a later revision would be widened there without the refusal the upgrade applies. Added, along with the other two structural checks, for symmetry.
  - `[low]` `[patch]` The conversion loop emitted nothing while rebuilding nine tables under a metadata lock at a cost proportional to stored MEDIUMBLOB bytes — an operator could not distinguish a slow table from a hung one, and killing it to find out produces the stranded schema. Extracted `_convert`, which logs each table through the already-wired Alembic runtime logger.
  - `[low]` `[patch]` The docstring said three earlier revisions read rows through `op.get_bind()`; there are four, as DW-197 (added in the same commit) already recorded. Corrected and the revisions named.
  - `[low]` `[patch]` `test_upgrade_refuses_when_a_table_is_missing` ran at the tier's normal default, where the surviving tables are already on the target collation — so a check that ran AFTER the conversion loop instead of before it would have passed identically. Moved inside `CONTRAST_COLLATION` and given the unconverted-schema and unchanged-version assertions its sibling tests carry.
  - `[low]` `[patch]` Nothing asserted the shape the `MODIFY` restates: `_structural_diffs` discards `modify_type` and `modify_nullable` by design, and `assert_schema_is_pinned` compares collations only, so narrowing `internal_id` or dropping its `NOT NULL` passed the entire tier. Added the `varchar(32)`/`NOT NULL` assertion.
  - `[low]` `[patch]` The `collatable=False` branch and the prefix-on-binary branch were dead code under test — the same standard the previous pass applied when it added the prefix-index test. Added `test_preflight_handles_an_index_mixing_a_string_and_a_binary_column`, over `photos (filename, thumbnail_data(16))`, which exercises both branches and the bytes-sample path at once.
  - `[low]` `[patch]` The downgrade's narrower-charset refusal — the one branch keyed on the database CHARSET rather than a collation — was unreachable by any test, because `database_default()` had had its charset parameter removed. Reinstated it (documenting why the restore is absolute rather than a delta) and added `test_downgrade_refuses_a_narrower_database_default`.
  - `[low]` `[patch]` `test_pinning_beats_a_contrary_database_default` is the tier's only guard on tables added by FUTURE revisions — `--autogenerate` never decorates `op.create_table()` with the charset kwargs — and it only works because it upgrades to `head` inside a contrary default. Stated in its docstring rather than left as an accident.
  - `[low]` `[patch]` Lint/prose: `E302` before `class InventoryItem`, `from pathlib import Path` grouped with third-party imports in the new unit module, and a `MYSQL_TABLE_OPTIONS` comment whose second and third bullets stated the same conclusion twice. (The migration's own import order is left alone: all 16 revision files share Alembic's scaffold ordering.)

Rejected: the concurrent-write race between the pre-flight and the first `ALTER` (rejected twice before, for the same reason — `LOCK TABLES` is heavier than the race it addresses for a single-operator application whose migrations run against a quiesced database); that `_abort_on_wide_charset` permanently blocks a latin1 deployment with no remedy documented outside the migration (deliberate, already recorded as a residual risk, and the refusal message states the remedy); that the abort message cannot identify rows without a primary key (every key column IS in the message, and the unique key is the identifying tuple); that DW-196 should have been fixed here rather than deferred (it is a column-TYPE defect, pre-existing, already on the ledger, and ledger entries belong to the orchestrator); that `test_the_shared_options_dict_is_not_mutated_by_declarative` cannot fail (it is redundant with the test above it, not wrong); that `database_default()`'s restore could strand the tier if the restore itself raises (rejected in pass 1); and that the `finally` restoring `group_concat_max_len` could mask the original error (Python chains it as `__context__`, so both appear).

## Design Notes

**Why `product_identifiers.value` cannot be per-type.** A single column carries every identifier type, so a per-type collation is not expressible in DDL. Folding is the right column-level default: GTIN (digits), INTERNAL (uppercase Crockford base-32) and ASIN have no case variation to lose, so folding is a no-op for them, while for MPN/VENDOR_SKU folding is the semantics `add_identifier`'s duplicate rejection and `tests/integration/test_identifier_collation.py` already assert. The per-type distinction lives in Python normalization, not in the collation.

**Why `products.internal_id` is the one binary column.** `is_valid_internal_id` is deliberately case-sensitive ("silently upper-casing input would let two different scanned strings map to one identifier"). `utf8mb4_bin` makes MariaDB agree with both that validator and SQLite, so `resolve_scan`'s `Product.internal_id == value` yields the same outcome on both backends — a lowercased scan does not resolve and falls through to free-text search.

**Cross-column consistency note to document.** `product_identifiers.value` folds while `products.internal_id` does not, so in principle two internal ids differing only in case could pass `uq_products_internal_id` but collide on the derived `INTERNAL` identifier row. Unreachable in practice — generated ids are always uppercase and `create_product` retries on any UNIQUE violation — but state it in the migration docstring rather than leaving it to be rediscovered.

**Deployed data does not need rewriting.** The conversion changes comparison semantics, not stored bytes (the deployment is already utf8mb4 in every environment the repo configures). The only failure mode is pre-existing rows that fold together under the target, which the pre-flight check turns into an actionable abort.

**`uq_products_internal_id` is in the pre-flight list after all.** Planning assumed it needed no check because `utf8mb4_bin` only loosens uniqueness, but that ignores the transient: the table-wide `CONVERT TO CHARACTER SET` puts `internal_id` under `utf8mb4_unicode_ci` first and the `MODIFY` that pins it binary runs after, so two ids differing only in case would fail the conversion mid-chain — exactly the stranded-schema failure the pre-flight exists to prevent.

**`products.attributes` (JSON) is converted after all, and is restored.** MariaDB implements JSON as a LONGTEXT alias, so `CONVERT TO CHARACTER SET` rewrites it like any other text column — planning assumed it was untouched. Left alone it would have made the migrated schema differ from the `create_all` one on the single column this change exists to keep them agreeing about. The migration re-issues the column type in both directions to restore JSON's fixed `utf8mb4_bin`, and `expected_column_collations()` asserts it.

**Both server dialect names must be named.** SQLAlchemy resolves dialect kwargs and `with_variant()` on `dialect.name`, which is `mysql` for a `mysql+pymysql://` URL and `mariadb` for a `mariadb+pymysql://` one. A pin declared only for `mysql` renders nothing under the second scheme — the models emit a bare `CREATE TABLE` and every column silently goes back to the server default, reintroducing the exact defect. Hence the `mariadb_charset`/`mariadb_collate` pair and `with_variant(..., 'mysql', 'mariadb')`, both asserted per dialect in the unit tier.

**The pre-flight discovers unique indexes rather than listing them.** The schema it protects is a *deployed* one and is not required to match the models — this repo documents one such divergence itself (`3b7d76c3fb8d` is a no-op "kept for consistency with existing database instances that may have the constraint", so some databases still carry `uq_ja_id_active`). Reading `information_schema.statistics` also covers future tables without anyone remembering to extend a list.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green; SQLite DDL unaffected by the model changes.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s integration` -- expected: green, including the new collation and pre-flight tests. Requires Docker.
- `venv/bin/python -c "from app.database import Product; from sqlalchemy.dialects import mysql, sqlite; print(Product.__table__.c.internal_id.type.compile(mysql.dialect()), '|', Product.__table__.c.internal_id.type.compile(sqlite.dialect()))"` -- expected: the MySQL rendering contains `COLLATE` and `utf8mb4_bin`; the SQLite rendering is bare `VARCHAR(32)`.

## Auto Run Result

Status: done

**Implemented change.** The schema states its own charset and collation instead of inheriting the server default. One Alembic revision (`a977ca7315df`) converts all nine tables to `utf8mb4`/`utf8mb4_unicode_ci` and pins `products.internal_id` to `utf8mb4_bin`; the models declare the same two decisions for both the `mysql` and `mariadb` dialects, so `create_all` and a migrated database agree. This second follow-up pass finished the pre-flight's structural half: the revision now refuses, before any DDL, a schema missing or redefining either of the two columns its post-conversion `MODIFY`s name, and one carrying a FOREIGN KEY over a character column — the two remaining ways to strand a half-converted schema. It also fixed two defects in the collision check itself (a prefix over a binary column was compared whole, and a binary sample crashed the formatter instead of aborting) and gave the conversion loop per-table progress output.

**Files changed:**
- `migrations/versions/a977ca7315df_pin_explicit_charset_and_collation.py` (new) -- the conversion, five pre-flight refusals (`_abort_on_missing_tables`, `_abort_on_missing_columns`, `_abort_on_string_foreign_keys`, `_abort_on_wide_charset`, `_abort_on_collisions`), the dialect/offline guards, a logged conversion loop, and a downgrade that restores the database default, runs the same structural checks, and refuses to narrow the charset.
- `app/database.py` -- `MYSQL_TABLE_OPTIONS` on all nine `__table_args__`; `internal_id` gets a dialect-scoped `utf8mb4_bin` variant; corrected the `ProductTag` docstring's collation claim.
- `app/mariadb_catalog_service.py` -- comments only: `search_products`, `_ecia_match._matches` and `resolve_scan` now describe the collation as pinned, and record that DW-73's backend divergence is closed by the binary pin.
- `tests/unit/test_database_schema.py` (new) -- database-free guards on both dialects' rendered DDL, plus the migration's non-MySQL no-op.
- `tests/integration/conftest.py` -- shared collation constants, `database_default()` (collation and charset), and `assert_schema_is_pinned()`; rewrote the stale DW-51 caveat.
- `tests/integration/test_migrations.py` -- `TestPinnedCollations`: pinned collations and `internal_id`'s shape on the migrated schema, the chain run inside a contrary-default database, `internal_id` vs. tag folding, the collision / prefix-index / mixed string-binary index / internal-id / wide-charset / missing-table refusals, the NULL-key non-collision, and both downgrade paths (restore, and refusal into a narrower default).
- `tests/integration/test_identifier_collation.py` -- the same pinning guard against the independently-maintained `create_all` schema.

**Review findings (this pass):** 15 patches applied (1 medium, 14 low), 0 deferred, 7 rejected. See the Review Triage Log.

**Verification:**
- `nox -s tests` -- 2965 passed, 444 deselected.
- `nox -s integration` -- 34 passed against a real `mariadb:11.8` testcontainer (5m31s), up from 32. Every refusal is proven to fire and to leave the schema unconverted.
- The new mixed string/binary index test was proven non-vacuous by reverting each of the two fixes it covers and re-running it alone: without the prefix fix the pre-flight misses the collision entirely, and without the bytes decode the abort becomes a `TypeError`.
- `nox -s lint` fails repo-wide as it did before this work (it is not in the default sessions). The files touched here are clean apart from pre-existing `app/database.py` hits (`F401 enum`, `E128`, `F821 Decimal`) and the Alembic scaffold import order, which all 16 revision files share.

**Residual risks:**
- `CONVERT TO CHARACTER SET` rebuilds every table under a metadata lock; on a photo-heavy deployment the cost is proportional to stored BLOB bytes, not row count. The loop now names each table as it starts, but offers no estimate and no `ALGORITHM`/`LOCK` guidance, because InnoDB does not support an in-place charset conversion.
- A pre-utf8mb4 deployment can no longer run this revision at all. That is deliberate -- the alternative was a silent `TEXT`/`MEDIUMTEXT` divergence and an unreachable downgrade -- but such a deployment needs a human-run conversion first, and no migration in this repo performs it. The remedy is stated only in the refusal message and the revision docstring, not in `docs/` or `manage.py`.
- `_abort_on_string_foreign_keys` and the `_abort_on_missing_columns` shape check have no integration coverage: both fire only on a deployed schema that diverges from the models, and constructing one costs more than the branches are worth. They fail closed (a refusal with nothing changed), which is the safe direction.
- Expression-based unique indexes are reported and skipped rather than checked. Unreachable on MariaDB, which has no functional indexes, but a MySQL 8 deployment would need them verified by hand.
- SQLite remains binary while MariaDB folds, so the unit tier stays looser than production for the folding columns. That is DW-72's subject; only the `products.internal_id` half of the divergence is closed here.


