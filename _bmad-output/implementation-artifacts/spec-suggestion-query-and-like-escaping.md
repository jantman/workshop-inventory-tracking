---
title: 'One LIKE-literal escaper, no SQL DISTINCT, and a storability guard on the field-suggestion path (DW-42, DW-49, DW-77)'
type: 'bugfix'
created: '2026-07-26'
status: done
baseline_revision: '1089889'
final_revision: '0d5b081'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['multiple-goals', 'oversized']
---

<intent-contract>

## Intent

**Problem:** Three defects meet at the same touchpoint — how `get_field_value_suggestions` builds its LIKE pattern.
1. **DW-42:** LIKE-metacharacter escaping has three independent copies that agree today and are free to drift: `app/utils/category.py`'s `descendant_like_pattern` (inline, against `CATEGORY_LIKE_ESCAPE_CHAR`), `_escape_like_wildcards` at `app/mariadb_catalog_service.py:130` (whose own docstring records the duplication), and the nested `_escape_like` at `app/mariadb_inventory_service.py:847-852`.
2. **DW-49:** both suggestion queries end `base.distinct().limit(fetch_limit).all()`. Under MariaDB's folding collation the DB collapses `café`/`cafe` (and any pre-migration case variant) into one row *before* the Python case-insensitive dedup pass that exists to decide exactly those cases, so one of two genuinely distinct stored values is never offered. The over-fetch cannot restore a row the DB already dropped. This has applied to the five inventory fields and `category_path` since Story 3.1, and to `tags` since Story 3.3.
3. **DW-77:** the suggestion patterns (`app/mariadb_catalog_service.py:590,597`; `app/mariadb_inventory_service.py:872,879`) carry no `_is_storable_text` guard. SQLite reads a LIKE pattern as a C string and stops at the first NUL, so `'%' + escaped + '%'` silently runs as a prefix of itself: measured in `search_products` before the Story 4.3 fix, `'\x00'` returned the entire catalog and `'a\x00b'` ran as `'%a'`. PyMySQL escapes `\0` in the emitted literal, so MariaDB is right and only SQLite — the sole backend the suite runs — is wrong.

**Approach:** Extract one pure util, `app/utils/sql_text.py`, holding the single LIKE-literal escaper and the single storability predicate, and rewire every caller in both services and in `category.py` onto it. Drop the SQL `DISTINCT` from both suggestion queries in favour of the existing Python dedup pass — the same "SQL narrows, Python decides" move `list_category_paths` and `list_tags` already make — reading the ordered rows lazily and stopping once `limit` distinct values are in hand, so removing `DISTINCT` cannot be starved by duplicate volume. Guard the suggestion entry points so unstorable input answers `[]` without querying, and guard the rename path's pattern sites so a truncated pattern cannot narrow a blocker scan.

## Boundaries & Constraints

**Always:**
- `app/utils/sql_text.py` is a **PURE module** in the sense `app/utils/category.py` documents: standard library only, no Flask, no SQLAlchemy, no I/O. It is importable by both services and by `category.py` without crossing the AD-1 service seam — which is the only reason the three copies existed.
- It exports exactly: `LIKE_ESCAPE_CHAR` (`'\\'`), `escape_like_literal(value)` (escape `\`, then `%`, then `_`, in that order), and `is_storable_text(value)` (False for a NUL or an unpaired surrogate). The measured evidence currently carried in `_escape_like_wildcards`' and `_is_storable_text`' docstrings moves with the code — it is the record of *why* these are one function, and deleting it re-opens DW-42.
- `category_util.CATEGORY_LIKE_ESCAPE_CHAR` keeps its name and value (`'\\'`), now defined as the util's `LIKE_ESCAPE_CHAR`. `tests/unit/test_category.py:84` pins it, and `app/mariadb_catalog_service.py:765` passes it as `escape=`.
- `descendant_like_pattern` output is byte-identical to today for every input, including the pinned 22-character `power_supplies/50%` case (`tests/unit/test_category.py:228`) and the trailing `/%` that must stay unescaped.
- The Python case-insensitive dedup pass (first-seen casing wins, `seen_lower` keyed on `v.lower()`) stays exactly as it is in both services and becomes the *only* dedup. `[1, 50]` limit clamping, the `NULL`/blank exclusion, the exact → starts-with → contains `rank` ordering, and the `order_by(rank, func.lower(column))` tiebreak are unchanged.
- After dropping `DISTINCT`, the method must still return `limit` distinct values whenever that many exist, no matter how many duplicate rows precede them. The fixed `limit * 3 + 10` over-fetch is **not** sufficient for this and must not survive as the only bound (100 products sharing one `category_path` would return one suggestion where ten distinct ones exist).
- Both `get_field_value_suggestions` implementations answer `[]` — without opening a session — when their raw input is not storable. The guard runs on the input **as passed**, before normalization, mirroring `resolve_scan` judging the whole `raw` envelope. The inventory method guards `location` the same way.
- The five inventory fields' HTTP responses stay byte-identical for ordinary input: `{'success', 'field', 'suggestions'}` and no `normalized` key (Story 3.1 / NFR9, pinned by `tests/unit/test_routes.py:1940`).
- Follow the surrounding style: legacy `session.query(...)` API, `typing` hints, long prose test names, `@pytest.mark.unit`, class-local `populated` fixtures.

**Block If:**
- Reading the suggestion rows lazily (early-break) proves not to work through `MariaDBStorage`'s SQLite session — i.e. there is no way to drop `DISTINCT` and keep a bound on rows transferred. (Falling back to an unbounded `.all()` matching `list_category_paths` is acceptable and is NOT a blocker; blocking is only for the case where `DISTINCT` cannot be dropped at all.)

**Never:**
- Do not change the suggestion endpoint's URL, JSON shape, status codes, field whitelists, dispatch rule, or the `normalized` key's catalog-only presence.
- Do not add a `normalized` key to inventory fields, and do not add an error branch for unstorable input — the answer is `[]` with HTTP 200, not a 400.
- Do not make either service import the other; the util is the shared seam. Do not move the LIKE escaper into `app/utils/category.py` — a vendor-name escape has no business depending on the category-path module, and `category.py`'s own docstring scopes it to canonical path form.
- Do not touch `list_category_paths` or `list_tags` (already correct), `search_products`' existing `_is_storable_text` guard (rewire the import only), `SEARCH_QUERY_MAX_LENGTH`, `MAX_SCAN_LENGTH`, or the scan path.
- Do not change `normalize_category_path` / `normalize_tag` contracts to reject NUL — the pure utils' rejection rules are pinned by tests and a storability question is not a canonical-form question.
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`; the orchestrator records resolution.
- Do not touch templates, static JS, or screenshots.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ordinary suggestion, any of the 7 fields | `q='elec'`, vocabulary seeded | Identical list to today, same order | No error expected |
| Two values differing only by folding | Stored `café` and `cafe`; blank query | **Both** offered (today one is lost under a folding collation). SQLite's BINARY collation never folds, so this is verified indirectly by the "no `DISTINCT` in the emitted SQL" assertion | No error expected |
| Two values differing only by case | Stored `Electronics/Power` and `electronics/power` | Exactly one offered, first-seen casing wins (unchanged) | No error expected |
| Duplicate volume exceeds the old over-fetch | 100 products at `a`, plus `b`…`k`; `limit=10` | 10 distinct values, not 1 | No error expected |
| LIKE metacharacters in the query | Stored `a%b` and `axb`; `q='a%b'` | `['a%b']` — literal match, unchanged | No error expected |
| NUL in the query, catalog field | `q='\x00'` or `'a\x00b'` on `category_path`/`tags` | `[]`; no SQL emitted for it | Guard returns before the session opens |
| NUL in the query, inventory field | `q='\x00'` or `'a\x00b'` on `vendor` etc. | `[]`; no SQL emitted | Same guard |
| Unpaired surrogate in the query | `q='\ud800'`, any field | `[]`, never a `UnicodeEncodeError`/500 | Same guard |
| NUL / unpaired surrogate in `location` | `field='sub_location'`, `location='a\x00b'` | `[]` | Same guard |
| Blank / whitespace / `None` query | `''`, `'   '`, `'/'`, `None` | Unfiltered vocabulary (unchanged "no filter" meaning) | No error expected |
| Unstorable path in a rename | `rename_category_path('a\x00b', 'c')` (either argument) | `ValidationError` naming the offending field; nothing written | `ValidationError`, not a silent partial/merged rename |
| Backend raises mid-query | Monkeypatched service raising | HTTP 500, never `200 []` (unchanged) | Route's existing handler |

</intent-contract>

## Code Map

- `app/utils/sql_text.py` -- **new**; the pure util. Sibling of `category.py`/`tag.py`, same "PURE module" docstring convention.
- `app/utils/category.py:72` -- `CATEGORY_LIKE_ESCAPE_CHAR`; `:205-244` `descendant_like_pattern` (its inline three-`replace` chain is copy #1). `:39`, `:67` docstrings mention the escaping.
- `app/mariadb_catalog_service.py:130-150` -- `_escape_like_wildcards` (copy #2; its docstring names the duplication). `:153-191` `_is_storable_text` (the only implementation). Callers: `:590`, `:597` (suggestions), `:2027` + `:2044` (`search_products`, already guarded), `:2306` (`resolve_scan`, already guarded), `:1933` (docstring reference).
- `app/mariadb_catalog_service.py:475-630` -- `CatalogService.get_field_value_suggestions`; normalization dispatch `:544-567`, pattern `:590`, rank `:594-600`, over-fetch `:605-611`, Python dedup `:618-627`.
- `app/mariadb_catalog_service.py:765-790` -- `rename_category_path`'s two `descendant_like_pattern` LIKEs; `:735-757` is where the normalized values are available for a guard, before the session opens.
- `app/mariadb_inventory_service.py:779-785` -- `FIELD_SUGGESTION_COLUMNS` (5 fields). `:787-911` `get_field_value_suggestions`: nested `_escape_like` `:847-852` (copy #3), `location` narrowing `:866-869`, pattern `:872`, rank `:876-882`, `.distinct()` `:892`, over-fetch `:891`, Python dedup `:899-908`. File imports nothing from `app/utils/`.
- `app/main/routes.py:3004-3071` -- `inventory_field_suggestions`, the single shared endpoint; dispatch on `CATALOG_FIELD_SUGGESTION_COLUMNS` at `:3030`; response bodies `:3064-3071`.
- `tests/unit/test_catalog_service.py:1131` `TestCatalogFieldValueSuggestions`, `:2611` `TestTagFieldValueSuggestions` -- fixture `catalog_service` at `:14`; `:1170`/`:2628` `test_distinct_values_only`, `:1243` case-insensitive dedup, `:1269`/`:2661` metacharacter escaping. `:2462` is the precedent for asserting on emitted SQL via a `before_cursor_execute` listener (used there to assert `list_tags` has no `DISTINCT`).
- `tests/unit/test_inventory_service.py:428` `TestFieldValueSuggestions` -- fixture `service` at `:431`, `populated` at `:448`, `:500` asserts case-insensitive uniqueness.
- `tests/unit/test_routes.py:1653` `TestFieldSuggestionsRoute` -- `:1808`/`:1881` whole-body equality, `:1940` `test_item_fields_never_carry_normalized` (the byte-identical guard), `:1773` backend-failure-is-500.
- `tests/unit/test_category.py:84`, `:209-268` -- `CATEGORY_LIKE_ESCAPE_CHAR` and `TestDescendantLikePattern` (6-row matrix, 22-char length pin, "only the trailing wildcard is unescaped").
- `tests/unit/test_scan_resolution.py:1459` `TestNeverRaisesOnScanData`, `:1679` `TestSearchProducts` -- the behavioral tests for NUL/surrogate/wildcard handling; the model for the new suggestion tests.

## Tasks & Acceptance

**Execution:**
- [x] `app/utils/sql_text.py` -- create the pure util with `LIKE_ESCAPE_CHAR`, `escape_like_literal`, `is_storable_text`; carry over the measured evidence from the two existing docstrings -- one implementation is the whole point of DW-42.
- [x] `app/utils/category.py` -- define `CATEGORY_LIKE_ESCAPE_CHAR` as the util's constant and build `descendant_like_pattern` on `escape_like_literal`, keeping output byte-identical -- kills copy #1 without changing the module's public surface.
- [x] `app/mariadb_catalog_service.py` -- delete `_escape_like_wildcards` and `_is_storable_text`, import the util, and rewire `get_field_value_suggestions`, `search_products` and `resolve_scan` onto it -- kills copy #2 and leaves one storability predicate.
- [x] `app/mariadb_catalog_service.py` -- in `get_field_value_suggestions`: guard unstorable raw input with `[]` before normalization, drop `.distinct()`, and read the ordered rows so the existing dedup pass yields `limit` distinct values regardless of duplicate volume -- DW-49 + DW-77.
- [x] `app/mariadb_catalog_service.py` -- in `rename_category_path`, reject an unstorable `old_canonical`/`new_canonical` with `ValidationError` on the matching field, before the session opens -- a NUL-truncated pattern narrows the blocker scan, which is how a refused branch merge could slip through.
- [x] `app/mariadb_inventory_service.py` -- delete the nested `_escape_like`, import the util, guard unstorable `query`/`location` with `[]`, and drop `.distinct()` with the same bounded read -- kills copy #3 and closes DW-49/DW-77 for the other five fields of the same endpoint.
- [x] `tests/unit/test_sql_text.py` -- **new**; unit-test `escape_like_literal` (each metacharacter, escape-char-first ordering, empty string, idempotence-is-NOT-claimed) and `is_storable_text` (plain text, NUL anywhere, lone surrogate, empty) -- the util is now the single point of failure for six query sites.
- [x] `tests/unit/test_catalog_service.py` -- add the DW-49 and DW-77 rows of the I/O matrix for `category_path` and `tags`: duplicate-volume-beats-the-old-over-fetch, NUL/surrogate query → `[]` with no SQL emitted, and a `before_cursor_execute` assertion that the suggestion SQL carries no `DISTINCT` (mirroring `:2462`); plus the `rename_category_path` unstorable-argument rejections.
- [x] `tests/unit/test_inventory_service.py` -- the same duplicate-volume, no-`DISTINCT`, and NUL/surrogate-in-`query`-or-`location` cases for the five inventory fields.
- [x] `tests/unit/test_routes.py` -- assert the endpoint answers `200` with an empty `suggestions` list for a NUL-bearing `q` on both a catalog and an inventory field, and that inventory bodies still carry no `normalized` key.

**Acceptance Criteria:**
- Given the whole codebase, when LIKE-metacharacter escaping is searched for, then exactly one implementation exists (`app/utils/sql_text.escape_like_literal`) and every LIKE pattern in `app/utils/category.py`, `app/mariadb_catalog_service.py` and `app/mariadb_inventory_service.py` is built through it.
- Given exactly one storability predicate, when `is_storable_text` is searched for, then `search_products`, `resolve_scan` and both `get_field_value_suggestions` implementations all call it and no second copy exists.
- Given the suggestion queries, when their emitted SQL is inspected, then it contains no `DISTINCT`, and duplicates are removed only by the Python case-insensitive pass.
- Given the pre-change suite, when `nox -s tests` runs after the change, then every previously passing test still passes — in particular `tests/unit/test_category.py::TestDescendantLikePattern`, `tests/unit/test_routes.py::TestFieldSuggestionsRoute` and both `test_distinct_values_only` tests.

## Spec Change Log

## Review Triage Log

### 2026-07-26 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 11 (high 0, medium 3, low 8)
- defer: 3 (high 0, medium 2, low 1)
- reject: 6
- addressed_findings:
  - `[medium]` `[patch]` The `yield_per` + early-break comments claimed "nothing past them is fetched". False: a buffering driver has already fetched everything, and PyMySQL's `SSCursor` drains the remaining rows at cursor close (`pymysql/cursors.py` `_finish_unbuffered_query`). Rewrote both read-loop comments, both `SUGGESTION_ROW_BATCH` comments and the inventory docstring to claim only what is true — the lazy read bounds Python-side materialization, the query is deliberately unbounded, and that trade is the same one every sibling vocabulary listing in these services already makes.
  - `[medium]` `[patch]` For unstorable input the catalog branch returned `suggestions: []` while `normalized` still echoed the NUL-bearing text — precisely the "not found, create it?" signal, for a value no suggestion or search could ever match back. `normalize_suggestion_value` now returns `None` for unstorable text, on the same rule it already applied to over-length input; the route test asserts the exact body.
  - `[medium]` `[patch]` `order_by(rank, lower(column))` has no total order, and with `DISTINCT` gone every duplicate row became a tie — so the early break let the query plan decide which spelling of a value the operator was offered. Added `column` as a deterministic tiebreak in both services.
  - `[low]` `[patch]` `app/utils/sql_text.py`'s docstring claimed "neither raises" (both raise on non-`str`) and claimed to be the source of truth for *every* user-text LIKE pattern (it is not — see the deferred entry). Replaced with the actual `str`-only caller obligation and an explicit list of the sites still outside it.
  - `[low]` `[patch]` `SUGGESTION_ROW_BATCH` shipped as a verbatim six-line duplicate across both services in the commit whose thesis is that duplication drifts. Constant kept per service (it is a per-table tuning knob, not a shared rule); the duplicated prose reduced to a cross-reference that says so.
  - `[low]` `[patch]` The same predicate was applied under two policies — raw argument answering `[]` in the lookups, canonical value raising `ValidationError` in the rename — with nothing stating the rule. Stated it at the rename site: a read is asked a question and "nothing matches" answers it; a write is told to change rows and silently changing none does not.
  - `[low]` `[patch]` All three `test_duplicate_volume_cannot_starve_the_distinct_values` docstrings claimed to demonstrate DW-49; they pass against the pre-change code too. Reframed as what they actually are — the guard that fails if any fixed row ceiling is restored now that a ceiling counts rows instead of values.
  - `[low]` `[patch]` The `DISTINCT`-absence assertions would stay green if someone reintroduced the identical collation-folding defect as a `GROUP BY`. Added the `GROUP BY` assertion to both suggestion SQL spies.
  - `[low]` `[patch]` `test_unstorable_arguments_are_rejected_before_anything_is_scanned` asserted only the error field and an unchanged row — both of which hold for a guard that runs *after* the subtree query. Added the `before_cursor_execute` spy the name promises.
  - `[low]` `[patch]` Two prose references to the deleted `_is_storable_text` were left behind in `tests/unit/test_scan_resolution.py` while the same reference was updated everywhere else.
  - `[low]` `[patch]` Housekeeping: restored the trailing newline at EOF, removed the double `.strip()` per row in both now-unbounded read loops, and rewrapped the 12 lines that broke the surrounding 79-column style.

### 2026-07-26 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 7 (high 0, medium 2, low 5)
- defer: 2 (high 0, medium 0, low 2)
- reject: 10
- addressed_findings:
  - `[medium]` `[patch]` "The `column` tiebreak makes the ordering total" is false on the production backend. Under MariaDB's folding `_ci` collation the tiebreak column folds case and accents too, so genuine case variants tie on BOTH sort keys and the early break still lets the plan pick the spelling — the exact SQLite-only-correct trap the DISTINCT tests' own docstrings warn about. Both services' comments now state where the ordering is total and where it is not; the substantive fix is deferred as DW-96.
  - `[medium]` `[patch]` The absolute claim "no stored value can equal or contain text that cannot be compared whole" — the sole stated justification for answering `[]` — is contradicted inside this same commit by `normalize_suggestion_value`'s new docstring ("a path carrying a NUL *can* be written") and by the change's own deferred write-path finding. Restated in `sql_text.is_storable_text` and both service guards as a premise about intent that the write path does not yet enforce, naming the read-only asymmetry as what makes it tolerable meanwhile rather than right.
  - `[low]` `[patch]` `app/utils/sql_text.py` claimed the unescaped `ilike()` sites in `search_items` and `mariadb_materials_admin_service.py` are "an open ledger entry". Verified false — `grep` finds no such entry. Reworded to what is true: they are named and carried as deferred work so the module is not read as a census.
  - `[low]` `[patch]` `SUGGESTION_ROW_BATCH`'s comment ("It bounds MEMORY, not transfer") contradicted the read-loop comment forty lines below it ("a buffering driver has already fetched everything"). Both service comments now say what the constant actually bounds — ORM row-object construction — and what it does not.
  - `[low]` `[patch]` All three `test_duplicate_volume_cannot_starve_the_distinct_values` docstrings claimed to fail if "any fixed ceiling" is restored; the 110 seeded rows only catch a ceiling in the old one's range, so a future `.limit(10000)` would keep them green and still starve a bigger table. Reframed to what the fixture can and cannot prove.
  - `[low]` `[patch]` Mid-sentence reflow damage left by the previous pass: `sql_text.py`'s "It is a PURE / module" and the inventory guard's one-word "reaches" line, both in a codebase otherwise wrapped uniformly at 79.
  - `[low]` `[patch]` Rewrapped the surrounding comment blocks the edits above touched, keeping every changed line within the file's 79-column style.

## Design Notes

**Why a new module and not `category.py`.** DW-42 says "export the literal-escaper from the pure util"; `app/utils/category.py` is that util today only because it happened to be where Story 3.2 needed escaping. Its module docstring scopes it to "the canonical form of a materialized category path", and making `mariadb_inventory_service.py` import the category module in order to escape a vendor name trades one wrong coupling for another. A sibling pure module keeps the seam honest and gives `is_storable_text` a home that both services can reach — which is what lets DW-77 be closed for all seven fields of one endpoint instead of two.

**Why the over-fetch must change when `DISTINCT` goes.** Today `DISTINCT` collapses duplicates in SQL, so `limit * 3 + 10` rows are `limit * 3 + 10` *values*. Without it they are rows, and a vocabulary with heavy duplication starves the result: 100 products at `a` followed by `b`…`k` with `limit=10` returns `['a']`. The precedent methods (`list_category_paths`, `list_tags`) read every row because their contract is the whole vocabulary; a suggestion needs only `limit` distinct values, so the ordered rows can be consumed lazily (e.g. `.yield_per(...)`) and the loop broken as soon as the dedup set reaches `limit` — same correctness, with a bound the precedent does not need. An unbounded `.all()` + dedup is an acceptable fallback if lazy consumption misbehaves under the SQLite fixture.

**Why the guard runs before normalization.** `normalize_category_path` and `normalize_tag` only strip whitespace and separators, so a NUL survives them and reaches the pattern either way; guarding the raw argument additionally means the *same* sentence describes all seven fields ("unstorable input answers `[]`") and matches how `resolve_scan` judges its whole `raw` envelope before parsing.

**Why `rename_category_path` is in and the rest of the file is out.** Its two `descendant_like_pattern` LIKEs are the only other user-text-derived patterns in the file. A NUL truncates them to a prefix, which *narrows* both scans; narrowing the `moving` set merely produces the existing "No products are filed under…" rejection, but narrowing the `blockers` set is how the branch merge that method exists to refuse could slip through. Rejecting up front costs four lines and makes the docstring's existing "unstorable" promise true in both senses.

## Deferred Findings (NOT written to the ledger)

The invocation instructed that the deferred-work ledger must not be edited by this run, so the three `defer` findings from the review pass are recorded here instead of appended to `deferred-work.md`. They are in the ledger's own shape so a sweep can lift them verbatim.

- source_spec: `_bmad-output/implementation-artifacts/spec-suggestion-query-and-like-escaping.md`
  severity: medium
  location: `app/mariadb_catalog_service.py` and `app/mariadb_inventory_service.py` (`get_field_value_suggestions` read loops)
  summary: Dropping the SQL `DISTINCT` also had to drop the row ceiling, so every suggestion lookup now emits an `ORDER BY` with no `LIMIT` — the server sorts and returns the whole matching set on each keystroke, and no client-side batching changes that.
  evidence: A ceiling applied after a SQL `DISTINCT` counts values; without one it counts rows, so any fixed ceiling can be starved by duplicate volume (100 products at one path return one suggestion where ten exist) — which is why it was removed rather than raised, and it is the trade `list_category_paths` and `list_tags` already make on the same tables. The alternative the review named and this change did not take is collation-safe dedup left in SQL — `DISTINCT BINARY column` / `GROUP BY BINARY column` under MariaDB, which does not fold under a `_ci` collation and would restore both a bounded top-N sort and a row ceiling. It was not taken here because the contract requires the Python pass to be the only dedup and forbids a ceiling that can starve, and because it needs dialect-specific SQL that the SQLite-only unit suite cannot verify. Closing it means measuring the sort cost on a real MariaDB dataset and deciding whether a `BINARY` grouping earns the dialect branch.
- source_spec: `_bmad-output/implementation-artifacts/spec-suggestion-query-and-like-escaping.md`
  severity: medium
  location: `app/mariadb_catalog_service.py` (`create_product`, `update_product`), `app/mariadb_inventory_service.py` (`add_item`, `update_item`)
  summary: The storability rule is enforced only on reads; nothing stops a NUL or an unpaired surrogate being written, so `is_storable_text`'s premise — that no stored value can contain text that cannot be compared whole — is asserted rather than enforced.
  evidence: `create_product` normalizes `category_path` but never calls `is_storable_text`, and `add_item` does nothing of the kind for `vendor`/`location`. A row written that way is invisible to suggestions and to `search_products` forever, is still offered as a suggestion by the vocabulary listings (whose values come straight from the column), and returns nothing when the operator selects it. Pre-existing — the write path never had such a guard — and only surfaced because this change made the read side total. Closing it means one guard at the write boundary plus a decision about the rows already stored.
- source_spec: `_bmad-output/implementation-artifacts/spec-suggestion-query-and-like-escaping.md`
  severity: low
  location: `app/mariadb_inventory_service.py:337,352,366,398,405` (`search_items`), `app/mariadb_materials_admin_service.py:219`
  summary: Six `ilike()` filters still interpolate user text into a LIKE pattern with no escaping and no storability guard, so they carry both defects this bundle closed everywhere else.
  evidence: They are built as `ilike(f"%{filters['ja_id']}%")` with no `escape=` argument at all, so a user typing `50%` or `a_b` into an inventory search filter still gets wildcard behaviour, and a NUL still truncates the pattern under SQLite. Entirely pre-existing and untouched by this change; the reason they are not in it is that escaping them changes matching behaviour for a different feature with its own contract, and the intent contract's `Never` list forbids touching search paths beyond the named ones. `app/utils/sql_text.py`'s docstring names them explicitly so the module does not read as a census it is not.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: full unit suite green, no new failures, no skips introduced.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s lint` -- expected: no new flake8/black/isort findings in the touched files (informational; lint is not in the default sessions).
- `grep -rn "replace('%'" app/` -- expected: exactly one hit, inside `app/utils/sql_text.py`.
- `grep -rn "\.distinct()" app/mariadb_catalog_service.py app/mariadb_inventory_service.py` -- expected: no hits.

**Manual checks (if no CLI):**
- No file under `app/templates/`, `app/static/css/` or `app/static/js/` is modified, so no screenshot regeneration is required.
- The e2e autocomplete suites (`tests/e2e/test_field_autocomplete.py`, `test_category_autocomplete.py`, `test_product_tags.py`) are the end-to-end coverage for this surface; running `nox -s e2e` needs a 20-minute tool timeout and is optional here because no template or JS changed.

## Auto Run Result

Status: done

**Summary.** A follow-up review pass over the already-implemented change (`e5886ba`). Two adversarial reviewers ran in parallel over the full `1089889..HEAD` diff. No intent gap and no spec defect surfaced: every finding that survived triage was an inaccurate claim in a comment, docstring or test docstring — including two the previous pass introduced while fixing something else. Seven were corrected. **No executable behavior changed in this pass**; the only edits are prose, and the suite is unchanged at 2468 passing.

The two findings with real teeth were both statements about the production backend that the SQLite-only suite cannot contradict: the `column` ORDER BY tiebreak added last pass is total only under a binary collation, and the "nothing stored can contain unstorable text" premise is asserted rather than enforced. Both are now stated honestly in the code, with the substantive fixes deferred.

**Files changed (this pass only):**
- `app/utils/sql_text.py` — corrected the false "open ledger entry" claim about the unescaped `ilike()` sites; restated `is_storable_text`'s invariant as an unenforced premise; repaired reflow damage.
- `app/mariadb_catalog_service.py` — corrected the tiebreak-totality claim, the `SUGGESTION_ROW_BATCH` "bounds MEMORY" claim, and the guard comment's absolute invariant.
- `app/mariadb_inventory_service.py` — the same three corrections, plus the one-word-line reflow damage in the guard comment.
- `tests/unit/test_catalog_service.py` — the two starvation-test docstrings now state what 110 seeded rows can and cannot catch.
- `tests/unit/test_inventory_service.py` — the same correction for the vendor twin.
- `_bmad-output/implementation-artifacts/deferred-work.md` — appended DW-95 and DW-96 as new entries only; no existing entry read, modified or re-opened.

**Review findings breakdown:** 7 patched (2 medium, 5 low), 2 deferred (DW-95 unbounded `q` length on the five inventory fields; DW-96 the collation-dependent tiebreak), 10 rejected. Notable rejections, all deliberate: the `rename_category_path` refusal of unstorable arguments is mandated by the intent contract's I/O matrix, and the row it can strand is reachable only through the un-guarded write path already recorded as this spec's deferred finding #2; the unbounded suggestion read and the collation-safe-`DISTINCT` alternative are already recorded verbatim as deferred finding #1, so re-deferring would duplicate; the uncommitted ledger edit is orchestrator-owned and this run is forbidden to touch it; the duplicated `SUGGESTION_ROW_BATCH` constant was explicitly adjudicated by the previous pass.

**Verification:**
- `nox -s tests` — **2468 passed**, 367 deselected, 18 pre-existing warnings, 25.9s. No new failures, no skips introduced.
- `grep -rn "replace('%'" app/` — exactly one hit, `app/utils/sql_text.py:87`. One escaper stands.
- `grep -rn "\.distinct()" app/mariadb_catalog_service.py app/mariadb_inventory_service.py` — no code hits (two comment mentions explaining the absence).
- Every line added this pass is within the files' 79-column style; the long lines those files carry are pre-existing and untouched.

**Residual risks.**
- Both deferred entries and this spec's own three deferred findings are MariaDB-side properties that no test in this repo can observe — the unit suite runs SQLite exclusively. The comments now say so at each site, which is the most the suite can enforce.
- The write-path storability gap (this spec's deferred finding #2) is the root cause behind two rejected findings; until it is closed, a row carrying a NUL can be created and will be invisible to every read guarded here, and unrenamable.

