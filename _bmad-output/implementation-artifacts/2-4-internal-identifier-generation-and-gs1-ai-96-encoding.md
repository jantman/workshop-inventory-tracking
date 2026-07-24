---
title: 'Internal identifier generation and GS1 AI-96 encoding'
type: 'feature'
created: '2026-07-24'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
baseline_revision: 'be3c9f6'
final_revision: 'c2cc4d4'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** `products` has no `internal_id` column at all (Story 1.1 deliberately deferred it to Epic 2), so no Product carries the authoritative, system-generated business key that labels, scan routing and direct URLs depend on, and nothing can produce the GS1 element string a printed DataMatrix must carry (FR12, FR12a–c, AD-3, AD-8, AD-16).

**Approach:** Add two pure `app/utils/` modules — `internal_id.py` (collision-resistant candidate generator) and `gs1.py` (AI-96 `encode`/`decode`, the single owner of the FNC1/AI/token grammar) — plus the `products.internal_id` column (Alembic, `UNIQUE`, no DB default) and its config pair. `CatalogService.create_product` becomes the **sole writer**: it generates a candidate, inserts the Product **and** its derived `INTERNAL` `ProductIdentifier` row in one transaction, and retries on a `UNIQUE` collision.

## Boundaries & Constraints

**Always:**
- `app/utils/internal_id.py` and `app/utils/gs1.py` are **pure** — stdlib only, no Flask/SQLAlchemy/`app.*` imports (AD-4). Their only failure signal is a module-local `ValueError` subclass; the service translates to `ValidationError`. Each ships a purity-guard test mirroring `tests/unit/test_gtin.py`.
- `internal_id.py` yields a **candidate only** — it never touches the DB. The create-service performs the insert and owns retry-on-`UNIQUE`-collision; `products.internal_id` carries **no** `default`/`server_default` (AD-8).
- The `INTERNAL`-type `ProductIdentifier` row is written in the **same transactional step** from the **same value** as `products.internal_id`, with global scope (`vendor_scope=''`, `INTERNAL` is not in `VENDOR_SCOPED_IDENTIFIER_TYPES`). It is a derived read index: `add_identifier` must reject `identifier_type=INTERNAL` so the row can never be edited to diverge (PRD FR7: "the row cannot be edited to diverge"), and `internal_id` stays out of `_PRODUCT_FIELDS` so `update_product` can never change it.
- On collision the whole attempt rolls back and retries with a fresh candidate; a non-collision `IntegrityError` is re-raised, never mislabelled (mirror `add_identifier`'s rollback → re-query → classify pattern). A partial write is never committed: either Product + `INTERNAL` row both land, or neither does. Exhausting the retry budget follows `create_product`'s established failure contract (audit-log `error`, return `None`).
- `gs1.encode(internal_id, *, ai, token)` returns exactly one element string: FNC1 first, then `ai`, then the data field `token + internal_id` — no separator, no second AI, nothing appended (FR12b). `ai`/`token` are **keyword-only with no defaults** (FR12c); the service reads the single config pair `GS1_INTERNAL_AI` / `GS1_INTERNAL_TOKEN` and passes them in explicitly (AD-16).
- `gs1.decode(raw, *, ai, token, fnc1_substitute=None)` **never raises on `raw`** (NFR8) — it returns `InternalPayload` or `None`. It absorbs all three FNC1 transmissions: GS `0x1D`, a caller-supplied substitute character, or stripped entirely (the deployed Tera HW0009 case, so the bare `96WITxxxxxxxxxx` must decode). A payload whose data field does not begin with the configured token, or that carries an empty id, returns `None` (FR12a).
- Existing behaviour is preserved: `create_product`'s signature and `Optional[int]` return, snapshot-before-commit, `finally`-close, and audit logging all stay; `record_purchase`/`record_amazon_purchase`/GTIN paths are untouched.
- The Alembic migration chains from HEAD `3beb9dff5e41`, backfills every pre-existing Product with a unique id **and** its `INTERNAL` row before applying `NOT NULL` + `UNIQUE`, and leaves metal-stock tables untouched (AD-14, NFR9).

**Block If:**
- The intent is read to require label rendering / DataMatrix rasterization (Epic 6), scan classification or `scan_router.py` (Epic 4), `internal_id`-keyed URLs or lookup-by-internal-id (Epic 8), or the `ScanClassification`/`ScanResolution` shapes (AD-15). None of those are built here.

**Never:** No route/template/UI/JS change. No `float`. No pyStrich/DataMatrix dependency. No `InternalPayload` in `app/models.py` (that would break `gs1.py`'s purity guard — it is defined in `gs1.py`). No AIM-symbology-identifier (`]d1`) stripping in `decode()` — FR37 makes that the Story 4.2 classifier's job. No third config key. No 43xx/ownership element strings (FR12d). No changes to `IdentifierType`. No exhaustive foreign-payload matrix or label ownership-text work — that is Story 2.5.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Generate candidate | `generate_internal_id()` | 10 chars, all from the Crockford-32 alphabet (no `I`/`L`/`O`/`U`); 1000 draws are distinct | No error |
| Invalid length | `generate_internal_id(length=0)` | rejected | `InvalidInternalIdError` |
| Validate | `is_valid_internal_id(x)` for `'ABC'` / lowercase / `'IIIIIIIIII'` / `None` / a good id | `False, False, False, False, True` | Never raises |
| New Product | `create_product(description='LM317')` | `products.internal_id` set to a valid id; exactly one `INTERNAL` identifier row with the same value and `vendor_scope=''`; `to_dict()` carries `internal_id` | No error |
| Collision retry | generator patched to yield `dup, dup, fresh` where `dup` is already stored | Product persists with `fresh`; still exactly one Product holding `dup`; no orphan identifier rows | No error |
| Retry exhausted | generator always yields a taken value | returns `None`; no Product and no identifier row written | audit-logged `error` |
| Foreign `IntegrityError` | flush fails for a reason other than the internal-id/`INTERNAL` uniqueness | re-raised, not retried or mislabelled | surfaces via `create_product`'s `except` → `None` + audit `error` |
| Manual INTERNAL add | `add_identifier(pid, identifier_type='INTERNAL', value='X')` | rejected, nothing written | `ValidationError(field='identifier_type')` |
| Immutability | `update_product(pid, internal_id='HACKED')` | ignored; stored value unchanged; returns `True` | No error |
| Encode | `encode('ABC1234567', ai='96', token='WIT')` | `'\x1d96WITABC1234567'` — one element string, FNC1 first | No error |
| Encode bad input | blank/non-str `internal_id`, blank `ai`, blank `token`, or an id containing FNC1/whitespace/control chars | rejected | `InvalidGs1PayloadError` |
| Decode, all FNC1 forms | `'\x1d96WITABC1234567'`, `'~96WITABC1234567'` (with `fnc1_substitute='~'`), `'96WITABC1234567'`, and the last with a trailing `\r\n` | each → `InternalPayload(internal_id='ABC1234567', ai='96', token='WIT', raw=<input>)` | No error |
| Decode foreign / junk | `'9612345'` (AI 96, no token), `'0109506000134352'`, `'96WIT'` (empty id), `''`, `None`, `'96wit...'` (wrong case) | `None` in every case | Never raises |
| Config-driven grammar | `encode`/`decode` with `ai='97', token='ZZZ'` | round-trips on `'\x1d97ZZZ...'`; the same input fails to decode under `ai='96', token='WIT'` | No error |
| Service seam | `encode_internal_payload('ABC1234567')` with `Config.GS1_INTERNAL_TOKEN` patched to `'ZZZ'` | output token changes with no code edit (FR12c) | No error |

</intent-contract>

## Code Map

- `app/utils/internal_id.py` — **new, pure.** `ALPHABET` (Crockford base32, `0-9A-Z` minus `I`/`L`/`O`/`U`), `INTERNAL_ID_LENGTH = 10`, `InvalidInternalIdError(ValueError)`, `generate_internal_id(*, length=INTERNAL_ID_LENGTH) -> str` (uses `secrets.choice`; rejects a non-positive length), `is_valid_internal_id(value) -> bool` (never raises). Docstring style per `app/utils/gtin.py`.
- `app/utils/gs1.py` — **new, pure.** `FNC1 = '\x1d'`, `InvalidGs1PayloadError(ValueError)`, frozen `@dataclass InternalPayload(internal_id, ai, token, raw)`, `encode(internal_id, *, ai, token) -> str`, `decode(raw, *, ai, token, fnc1_substitute=None) -> Optional[InternalPayload]`. `encode`/`decode` validate `ai`/`token` (blank → `InvalidGs1PayloadError`; a blank token would defeat FR12a); only `encode` validates the id. `decode` accepts non-`str` by returning `None`, strips surrounding whitespace, strips one leading FNC1 (GS or the substitute), then requires the exact `ai + token` prefix and a non-empty remainder.
- `config.py` — add `GS1_INTERNAL_AI = os.environ.get('GS1_INTERNAL_AI', '96')` and `GS1_INTERNAL_TOKEN = os.environ.get('GS1_INTERNAL_TOKEN', 'WIT')` to `Config` (both `TestConfig`s subclass it, so tests inherit them).
- `app/database.py` — `Product`: add `internal_id = Column(String(32), nullable=False)` (no default of any kind) plus `__table_args__ = (UniqueConstraint('internal_id', name='uq_products_internal_id'),)`; add `'internal_id'` to `to_dict()`; refresh the "later stories extend this table" comment.
- `migrations/versions/<rev>_add_products_internal_id.py` — **new**, `down_revision = '3beb9dff5e41'`. Add the column nullable → backfill each existing row via `from app.utils.internal_id import generate_internal_id` (env.py puts the project root on `sys.path`), inserting a matching `INTERNAL` `product_identifiers` row (`vendor_scope=''`, `created_at=sa.func.now()`) and tracking issued ids to avoid in-batch duplicates → `alter_column` to `nullable=False` → `create_unique_constraint('uq_products_internal_id', ...)`. Downgrade drops the constraint, deletes the derived `INTERNAL` rows, drops the column.
- `app/mariadb_catalog_service.py` — `from .utils import gtin, internal_id as internal_id_util` and `from .utils import gs1`; add `INTERNAL_ID_MAX_ATTEMPTS = 5`. **`create_product`**: inside the existing `try`, loop up to `INTERNAL_ID_MAX_ATTEMPTS` — build `Product(internal_id=candidate, ...)` and its `ProductIdentifier(product=product, identifier_type=IdentifierType.INTERNAL.value, value=candidate, vendor_scope='')`, `session.add` both, `session.flush()`; on `IntegrityError` roll back, re-query for the candidate (a `Product.internal_id` **or** an `INTERNAL` identifier row) and retry only if it is genuinely taken, otherwise re-raise; exhausting attempts raises so the existing `except` audit-logs and returns `None`. Snapshot/commit/audit/`finally` unchanged. **`add_identifier`**: reject `IdentifierType.INTERNAL` up front with `ValidationError(..., field='identifier_type')`. **New** `encode_internal_payload(self, internal_id: str) -> str` — reads `Config.GS1_INTERNAL_AI`/`Config.GS1_INTERNAL_TOKEN` and delegates to `gs1.encode` (the AD-16 config seam).
- `tests/unit/test_internal_id.py`, `tests/unit/test_gs1.py` — **new**, one class per public function + a purity-guard class, `@pytest.mark.unit` on every test (mirror `tests/unit/test_gtin.py`).
- `tests/unit/test_catalog_service.py` — add service-level tests; **update** the existing `add_identifier` parametrize case `('INTERNAL', 'ABC123', 'ABC123')` (line ~321), which now must be rejected.

## Tasks & Acceptance

**Execution:**
- [x] `app/utils/internal_id.py` — implement the pure candidate generator per the Code Map, so the id is collision-resistant and free of scanner/human-ambiguous characters (AD-4, AD-8).
- [x] `app/utils/gs1.py` — implement the single-source AI-96 grammar (`encode` + `decode` + `InternalPayload` + `FNC1`) with no literal `ai`/`token` defaults, so encoder and router can never drift (FR12–FR12c, AD-16).
- [x] `config.py` — add the `GS1_INTERNAL_AI` / `GS1_INTERNAL_TOKEN` pair to `Config` (FR12c).
- [x] `app/database.py` + `migrations/versions/<rev>_add_products_internal_id.py` — add the `UNIQUE`, no-DB-default `internal_id` column and its backfilling migration chained from `3beb9dff5e41` (AD-3, AD-8, AD-14).
- [x] `app/mariadb_catalog_service.py` — make `create_product` the sole writer (atomic Product + derived `INTERNAL` row, retry-on-collision, re-raise foreign `IntegrityError`), reject manual `INTERNAL` adds in `add_identifier`, and add the `encode_internal_payload` config seam (AD-8, AD-16).
- [x] `tests/unit/test_internal_id.py`, `tests/unit/test_gs1.py` — cover every pure-module row of the I/O matrix (alphabet/length/uniqueness/validation; encode grammar and rejections; decode round-trip under all three FNC1 transmissions, foreign/junk → `None`, config-driven grammar) plus the purity guards.
- [x] `tests/unit/test_catalog_service.py` — cover the service rows of the I/O matrix (id + derived row written together, collision retry, retry exhaustion, foreign `IntegrityError`, manual-`INTERNAL` rejection, `update_product` immutability, `encode_internal_payload` config-drive) and update the stale `INTERNAL` parametrize case.

**Acceptance Criteria:**
- Given a new Product is saved, when `create_product` returns, then `products.internal_id` holds a unique generated value with no DB default involved, and exactly one derived `INTERNAL` identifier row carries the identical value — both committed in a single transaction (FR12, AD-8).
- Given the generated candidate is already taken, when `create_product` inserts, then it retries with a fresh candidate and still commits exactly one Product; when the budget is exhausted it writes nothing and returns `None` (AD-8).
- Given `app/utils/gs1.py` and `app/utils/internal_id.py`, when the purity-guard tests run, then neither module imports Flask, SQLAlchemy, or `app.*` (AD-4, NFR7).
- Given only a config change to `GS1_INTERNAL_AI`/`GS1_INTERNAL_TOKEN`, when a payload is encoded and decoded, then both sides follow the new grammar with no code edit, and a payload built under the old token no longer decodes (FR12c, AD-16).
- Given `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests`, when the suite runs, then all new tests pass and every pre-existing test stays green.

## Spec Change Log

## Review Triage Log

### 2026-07-24 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 0, medium 2, low 6)
- defer: 1
- reject: 18
- addressed_findings:
  - `[medium]` `[patch]` The migration backfill wrote a **second** `INTERNAL` identifier row for a Product that already had one (pre-2.4 `add_identifier` allowed manual `INTERNAL` adds), creating exactly the column↔index disagreement the new guard exists to prevent. It now adopts an existing row's value as `internal_id` (when it fits the 32-char column) instead of issuing a new one, and inserts a derived row only for products that lack one.
  - `[medium]` `[patch]` `gs1.decode()` returned any non-empty data field after the token, so a garbled/crafted scan such as `96WITABC1234567\r\n… ERROR …` yielded an `internal_id` carrying interior control characters — audit-log forging material, and un-encodable by `encode()`, leaving the pair open. `decode()` now applies the same printable-ASCII rule `encode()` enforces and returns `None` otherwise, closing the round trip.
  - `[low]` `[patch]` `downgrade()` deleted **all** `INTERNAL` identifier rows, destroying operator rows that predated the revision. It now deletes only rows whose value matches `products.internal_id` (the ones `upgrade()` derived).
  - `[low]` `[patch]` The backfill's collision `while` loop was unbounded, contradicting the bounded retry policy the same story establishes in the service. Now capped at 5 attempts, raising rather than spinning mid-DDL.
  - `[low]` `[patch]` `_require_grammar_part` checked blankness with `.strip()` but returned the value unchanged, so `GS1_INTERNAL_AI=96 ` (invisible trailing space in `.env`) was concatenated into every element string and still round-tripped locally. Padded `ai`/`token` are now rejected.
  - `[low]` `[patch]` `encode()` accepted non-ASCII ids (e.g. `'ABC123456é'`), which no GS1 symbology encodes; the character rule is now printable-ASCII, shared with `decode()`.
  - `[low]` `[patch]` `_internal_id_is_taken` matched `(identifier_type, value)` while the unique constraint is `(identifier_type, value, vendor_scope)`, so a scoped legacy `INTERNAL` row could make a non-collision `IntegrityError` look like a collision and hide the real cause behind an exhausted-retry `RuntimeError`. The query now matches the constraint exactly.
  - `[low]` `[patch]` `config.py` used `os.environ.get(key, default)`, so a key present-but-empty in `.env` overrode the default with `''` and made every encode raise; switched to the repo's `... or 'default'` idiom. Also corrected `encode_internal_payload`'s docstring, which claimed a reconfigured value "takes effect immediately" when `Config` reads the environment once at import.
  - `[low]` `[patch]` Filtering the derived `INTERNAL` row out of the pre-existing identifier-count assertions removed all total-count coverage, so a spurious extra row would go undetected; restored one unfiltered total assertion.
  - Deferred (1): no test in the repo executes an Alembic migration, so `upgrade()`/`downgrade()` are verified by inspection only — logged to the deferred-work ledger now that migrations carry data logic.
  - Rejected (18, by-design / out-of-scope / spec-`Never` / pre-existing): `decode('96WITNESS42')` returning a payload for a foreign AI-96 code (spec-mandated grammar-only recognition; it cannot resolve to a Product, since issued ids are 10 alphabet chars, and Story 2.5 owns the foreign-payload matrix); `gs1` not consulting `is_valid_internal_id` (deliberate module separation — the grammar owner must not own the id shape); no `fnc1_substitute` config key and no `decode_internal_payload` service method (spec `Never: no third config key`; Epic 4 adds both with its consumer); `encode_internal_payload` having no caller yet (Epic 6 is its consumer); literal `0x1D` vs a symbology FNC1 codeword (Epic 6 rendering, explicitly out of scope); no `CHECK`/format constraint on `internal_id` (sole-writer is the AD-8 design, and a DB-level format rule would freeze the format); migration not restartable / DDL auto-commit and the live-insert race (a property of every migration in this repo; single-operator deployment); no `ondelete`/cascade on the derived row (purchases and attachments already FK-block product deletion; no `delete_product` exists); `except Exception → None` hiding the re-raise from callers and `update_product` silently ignoring unknown fields (both spec-required existing contracts); TOCTOU between rollback and the collision re-check (single-writer, mirrors `add_identifier`); the purity guard being a text scan rather than an AST walk (verbatim copy of the established `test_gtin.py` pattern); `_product_counter`'s `:02d` width in a test helper; unbounded `length`/id-length arguments on `generate_internal_id`/`encode` (caller-controlled keyword knobs).

### 2026-07-24 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 12: (high 0, medium 2, low 10)
- defer: 1
- reject: 12
- addressed_findings:
  - `[medium]` `[patch]` The migration's adopt path (added last pass) validated only that a pre-existing `INTERNAL` value fit the 32-char column, not that it was a *canonical* id. An operator row holding `Bin 4A` or `my-shelf-tag` would have been promoted to that Product's authoritative business key — one that `gs1.encode` rejects outright, so the product's label could never be printed, discovered only at the label printer. Adoption is now gated on `is_valid_internal_id` (which until now had no production caller at all); a non-canonical row aborts the migration with an actionable message instead of being promoted.
  - `[medium]` `[patch]` `adopted` was a dict comprehension over all `INTERNAL` rows, so a Product carrying two of them silently kept only the last — leaving the other permanently disagreeing with `products.internal_id`, which is the exact column↔index divergence the story exists to prevent and which `add_identifier`'s new guard can no longer catch for pre-existing rows. The backfill now detects the case and refuses rather than guessing.
  - `[low]` `[patch]` The backfill's `INTERNAL` query filtered on `identifier_type` alone while `_internal_id_is_taken` was deliberately tightened last pass to match the constraint `(type, value, vendor_scope)`. A vendor-scoped `INTERNAL` row was therefore adoptable by the migration yet invisible to the runtime collision check. The query now filters `vendor_scope = ''`, so both sides agree on what the derived index is.
  - `[low]` `[patch]` `downgrade()` matched rows by value alone, so an `INTERNAL` row belonging to a *different* Product that happened to hold the same string was deleted — a row this revision never created. It now matches ownership (`product_id`) and global scope via a correlated `EXISTS`. The comment claiming adopted rows are spared was also wrong (adoption makes them indistinguishable from inserted ones) and now states the real contract.
  - `[low]` `[patch]` Neither `GS1_INTERNAL_AI` nor `GS1_INTERNAL_TOKEN` appeared in `.env.example`, which documents every other config key — so the FR12c "one config change, no code edit" seam was only discoverable by reading `config.py`. Both are now documented there with their defaults and the label-invalidation warning.
  - `[low]` `[patch]` `decode`'s `fnc1_substitute` was the one grammar knob with no validation: a non-string made `candidate.startswith()` raise a bare `TypeError` out of a function contracted never to raise on scan data, and a multi-character value (`'96'`) silently ate the AI so every scan returned `None`. It is now required to be a single character or `None` — checked inline rather than via `_require_grammar_part`, which forbids whitespace and would have rejected GS itself.
  - `[low]` `[patch]` `_is_encodable_id_char` contradicted its own docstring (it excludes the space; the docstring called the accepted set "printable ASCII", which includes it) and carried an unreachable `not char.isspace()` clause — no character in 0x21-0x7E is whitespace. Docstring corrected to state the real 0x21-0x7E rule and why the space is excluded; the dead clause removed.
  - `[low]` `[patch]` The comment beside `decode`'s FNC1-stripping loop implied both arms do work, but `raw.strip()` already removes GS (Python counts 0x1C-0x1F as whitespace, verified), so the `FNC1` arm can never fire. The comment now says the arm is redundant-but-explicit documentation of the grammar and that only the substitute arm can actually fire.
  - `[low]` `[patch]` `InternalPayload.raw` was documented as "kept verbatim for audit" while being the one field that is *not* character-filtered — so the trailing CR/LF the interior-control-character rule was added to block last pass survives intact in the field most likely to be logged, re-opening the same log-forging vector. The attribute doc now marks it UNTRUSTED and requires escaping before logging.
  - `[low]` `[patch]` The retry loop wraps `session.flush()` only, so a UNIQUE violation surfaced at `COMMIT` would bypass it entirely — true on neither deployed backend, but recorded nowhere. Documented at the `commit()` call that the guarantee rests on statement-time constraint evaluation.
  - `[low]` `[patch]` Last pass restored exactly one unfiltered identifier-count assertion, leaving the other converted call sites blind to a duplicated or orphaned derived row. Added unfiltered totals to `test_add_each_type_persists` and `test_get_identifiers_empty_and_ordered` (including the "a new Product has exactly one row" case).
  - `[low]` `[patch]` Several test fixtures used values the generator can never produce — `'SQUATTED1'` (9 chars, contains the excluded `U`), `'FOREIGN001'` and `'PROD00000n'`/`'HOSTPROD'` (excluded `O`/`I`) — so the collision path was never exercised against a realistically-shaped id. All are now canonical.
  - Deferred (1): `create_product`'s constraint-arbitration/retry mechanism is exercised only against SQLite, never the MariaDB backend it runs on — logged to the deferred-work ledger as a new entry.
  - Rejected (12, by-design / spec-mandated / matching established repo patterns / pre-existing): the duplicated attempt budgets `_MAX_CANDIDATE_ATTEMPTS`/`INTERNAL_ID_MAX_ATTEMPTS` (a migration must stay self-contained; importing the service constant is the coupling to avoid); the migration importing `app.utils.internal_id` (explicitly mandated by the Code Map); no fail-fast validation of `GS1_*` at config load and no `.strip()` coercion (fail-loud on a padded value is last pass's deliberate choice; coercing would silently restore the bug); `encode_internal_payload` reading base `Config` so subclass overrides are ignored (the file's pre-existing engine setup and `config.py` itself do the same); MariaDB's case-insensitive default collation on `internal_id` (the generator emits upper-case only, and the identifier-level version of this is already on the ledger from Story 2.1); `session.rollback()` rolling back the transaction rather than a savepoint (`create_product` owns its session, mirroring `add_identifier`); no length cap on the id returned by `decode` and no AI 90-99 30-character data-field cap in `encode` (both re-couple the grammar owner to the id shape, rejected last pass for the same reason); the migration being executed by no test (already on the ledger — not duplicated or re-opened); the unused `attempt` loop variable, `_require_grammar_part`'s discarded return value, and the un-executed doctest `Examples:` blocks; a config fault surfacing as `ValidationError(field='internal_id')` rather than `field='config'`.

### 2026-07-24 — Review pass (follow-up 2)
- intent_gap: 0
- bad_spec: 0
- patch: 7: (high 0, medium 1, low 6)
- defer: 0
- reject: 14
- addressed_findings:
  - `[medium]` `[patch]` The two `RuntimeError` abort paths added last pass ran **after** `op.add_column`. MySQL/MariaDB commits DDL implicitly, so an abort left `products.internal_id` applied while `alembic_version` still pointed at the old revision — and the re-run the error message explicitly instructs the operator to perform would then die on `Duplicate column name 'internal_id'`. The migration's own comment ("failing loudly costs nothing and destroys nothing … the operator resolves the row by hand and re-runs") was therefore false for both paths it described. The read + adoption validation now runs before any DDL is issued, making every data-dependent abort a genuine no-op on the schema; the one remaining post-DDL abort (generator exhaustion) is now documented as depending on a broken generator rather than on any state of the data.
  - `[low]` `[patch]` `_require_grammar_part` validated `ai`/`token` for blankness and padding but never for character shape, while `encode` held `internal_id` to printable-ASCII. `GS1_INTERNAL_AI='9 6'` (or a value carrying a control character, or FNC1 itself, which would split the data field) was concatenated into every element string and still round-tripped through this module's own decode under the same config — the exact invisible-failure mode the padding check was added for last pass, one character further in. Both grammar parts are now held to the same rule as the id.
  - `[low]` `[patch]` The purity guard scanned for five absolute-import literals, none of which match a relative import — and every intra-package import in this app is relative, so the realistic violation `from ..database import Product` sailed through, leaving AC 3 ("neither module imports Flask, SQLAlchemy, or `app.*`") unenforced against the likeliest breach. A per-line statement-start check now catches it; verified by injecting that exact import and watching the test fail, then reverting. Applied to `test_gtin.py` as well, since the Code Map requires the new guards to mirror it and the hole was identical. A substring check was deliberately not used: `gtin.py` contains the prose "a bare AttributeError from .strip()", which would false-positive.
  - `[low]` `[patch]` `test_bad_id_surfaces_as_validationerror_not_the_pure_error` asserted `not isinstance(exc_info.value, InvalidGs1PayloadError)` on a caught `ValidationError` — unrelated classes, so the assertion could never fail and the test verified nothing about translation. It would have passed identically against a service that rejected the id itself and never called `gs1.encode`. It now first pins that the pure module genuinely rejects the input, then asserts the pure error's message is carried through and the field is set.
  - `[low]` `[patch]` A genuine internal-id collision — a ~1-in-1.1e15 event the story itself argues is unreachable — was retried with no log line of any kind, so a degenerate generator (truncated `ALPHABET`, a monkeypatch left in place, a shortened length) surfaced only as the eventual exhausted-retry failure, with the audit log showing plain `success` on the attempt that landed. The retry path now emits a `warning` naming the attempt and candidate. (This also puts the previously-unused `attempt` loop variable to work.)
  - `[low]` `[patch]` `.env.example` stated "Both must be non-blank and carry no surrounding whitespace", describing two opposite behaviors as one rule: a blank value is silently replaced by the default (`config.py`'s `or` idiom, no error), while a padded one is accepted by config and rejected far downstream in `gs1.encode`. The comment now states the real contract. The file also lacked a trailing newline — the same defect this diff repairs three lines earlier on `LOG_LEVEL`.
  - `[low]` `[patch]` Three `_added_identifiers(...) == []` assertions on rejected `record_amazon_purchase` paths checked only the filtered list, so a spurious or duplicated derived `INTERNAL` row written on the way out would go undetected — the same gap the previous two passes closed elsewhere, left partially applied. Unfiltered totals added to all three.
  - Deferred (0): nothing new. The migration's lack of test execution and the SQLite-only collision-retry coverage are already on the ledger from earlier passes and were not re-opened or duplicated.
  - Rejected (14, previously-rejected / by-design / out-of-scope): `decode` not bounding the id's length or alphabet (re-raised by both reviewers; rejected twice before — `gs1.py` owns the grammar, not the id shape, and Story 2.5 owns the foreign-payload matrix); a config fault surfacing as `ValidationError(field='internal_id')`; `encode_internal_payload` reading base `Config` rather than `app.config`; no `fnc1_substitute` config key and no `decode_internal_payload` (spec `Never`: no third config key; Epic 4 adds both with its consumer); `is_valid_internal_id` having no service caller (the service generates from the same module — validating its own output is redundant); no cap tying `generate_internal_id(length=…)`/`decode` output to `String(32)` (caller-controlled keyword knob, rejected last pass); the backfill's per-row round-trips not being batched; `fnc1_substitute` colliding with the first character of `ai`, and a scanner emitting both a substitute and GS (pathological, caller-supplied, no production caller); `.strip()` coercion in `config.py` (fail-loud is the deliberate prior choice); the live-insert race between backfill and `NOT NULL`; `downgrade()` raising on a missing constraint after an aborted upgrade (subsumed — aborts now precede all DDL); the migration being executed by no test (already on the ledger).

## Design Notes

**Why random Crockford-32 rather than a sequence.** A pure generator cannot see the DB, so a sequence would need a DB default or a read-modify-write — both barred by AD-8 (single writer, no DB default). Ten characters from a 32-symbol alphabet (~1.1e15 space) makes collision effectively unreachable, while the retry loop keeps correctness independent of that estimate. Dropping `I`/`L`/`O`/`U` avoids OCR/human transcription ambiguity for the human-readable label region (Epic 6) and typed URLs (Epic 8).

**Why the `INTERNAL` row is written here, not by `add_identifier`.** `add_identifier` opens and commits its own session, so calling it from `create_product` could not be atomic — the same reasoning Story 2.3 applied to `record_amazon_purchase`. Both rows are therefore built on one session and flushed together; the retry loop covers both unique constraints because both derive from the same candidate. Linking via `ProductIdentifier(product=product, ...)` lets one flush assign the FK.

**Why `decode()` lives here.** `encode()` is only meaningfully verifiable by round-trip, and AD-16 makes `gs1.py` the single owner of the grammar — splitting encode and decode across stories is exactly the drift AD-16 exists to prevent. Story 2.5 still owns the exhaustive foreign-payload matrix and the FR12d ownership-text rule; Story 4.2 owns AIM-prefix handling and routing precedence.

**FNC1 shape.** `encode` emits the GS character `\x1d` as FNC1-in-first-position and exports it as `gs1.FNC1`; `decode` tolerates GS, a caller-supplied substitute, or nothing at all, so a symbol printed by Epic 6 round-trips through the deployed scanner that strips FNC1 (Q1 spike). Consumers never re-derive the grammar — a renderer that needs the bare data field gets a parameter added to `encode` in this module.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` — expected: all pass (new `test_internal_id.py`, `test_gs1.py`, and catalog-service cases included); no pre-existing test regresses.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests -- -k "InternalId or Gs1 or Encode or Decode"` — expected: the new pure-module classes run and pass.
- `venv/bin/python -m py_compile migrations/versions/*_add_products_internal_id.py` — expected: clean compile.

**Manual checks (if no CLI):**
- The new migration's `down_revision` is `'3beb9dff5e41'` and `venv/bin/python -c "import app.database"` reflects the same column type/length and constraint name (`uq_products_internal_id`) that the migration creates — the unit suite builds its schema with `create_all`, so model↔migration parity is inspected, not tested.

## Auto Run Result

Status: `done` — third review pass over the already-implemented story. No intent gaps and no spec deviations; 7 findings patched, 0 newly deferred, 14 rejected.

**Implemented change (cumulative).** `products.internal_id` is a `UNIQUE`, `NOT NULL`, no-DB-default business key written solely by `CatalogService.create_product`, which generates a Crockford-32 candidate, writes the Product and its derived global `INTERNAL` identifier row in one transaction, and retries on a UNIQUE collision while re-raising any other `IntegrityError`. Two pure stdlib-only modules own the primitives: `internal_id.py` (shape) and `gs1.py` (the AI-96 element-string grammar, `encode`/`decode`). This pass fixed the backfill migration's abort ordering, closed the last unvalidated part of the grammar, and strengthened three tests that could not fail.

**Files changed in this pass:**
- `migrations/versions/5aeb89e22451_add_products_internal_id.py` — the pre-existing-row read and adoption validation now run before `op.add_column`, so a data-dependent abort leaves the schema completely untouched and the re-run its message asks for actually works on MariaDB (DDL there commits implicitly).
- `app/utils/gs1.py` — `_require_grammar_part` now holds `ai`/`token` to the same printable-ASCII rule as `internal_id`, closing the interior-whitespace/control-character hole left by last pass's padding fix; three docstrings updated to match.
- `app/mariadb_catalog_service.py` — module logger added; a real internal-id collision is now logged as a warning instead of being retried silently.
- `.env.example` — the `GS1_*` comment now states the real contract (blank falls back to the default; malformed raises at first encode, it is never repaired); trailing newline restored.
- `tests/unit/test_gs1.py` — new parametrized coverage for unencodable `ai`/`token`; purity guard now detects relative imports.
- `tests/unit/test_internal_id.py`, `tests/unit/test_gtin.py` — same purity-guard strengthening, keeping the three guards mirrored as the Code Map requires.
- `tests/unit/test_catalog_service.py` — the translation test now proves translation actually happens; unfiltered identifier totals added to the three remaining rejected-path assertions.

**Review findings breakdown:** 7 patches applied (1 medium, 6 low), 0 newly deferred (both standing coverage gaps were already on the ledger and were not re-opened), 14 rejected — the majority of them findings both reviewers re-raised after earlier passes had already rejected them for stated design reasons.

**Verification performed:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` — **650 passed**, 305 deselected, 0 failures (645 before this pass; +5 from the new `ai`/`token` parametrization).
- `venv/bin/python -m py_compile migrations/versions/5aeb89e22451_add_products_internal_id.py` — clean.
- The reordered `upgrade()` executed against scratch SQLite databases with a recording `op` stub, 5/5 as intended: both abort cases (two global `INTERNAL` rows on one product; a non-canonical value) raised with **zero** DDL calls and the schema unmodified; clean backfill, single-row adoption, and vendor-scoped-row-not-adopted all produced a column and derived-row set that agree exactly and hold distinct values.
- The purity-guard fix proved by injecting `from ..database import Product` into `app/utils/gs1.py` and confirming the test fails on it (it passed before the fix), then reverting — `git diff` confirms the module is unchanged.

**Residual risks:**
- The migration is still executed by no test (on the deferred ledger). This pass's simulation exercises its data logic and abort ordering against SQLite with a stubbed `op`, which is materially stronger than inspection but is still not a real Alembic run; `alter_column(nullable=False)` and `create_unique_constraint` are not executable on SQLite without `batch_alter_table`, so the DDL half remains inspection-only.
- The collision-retry mechanism remains SQLite-only in test (on the deferred ledger).
- `encode_internal_payload` and `gs1.decode` still have no production caller; their consumers arrive in Epics 4 and 6.
- `tests/unit/test_gtin.py` was touched outside this story's scope to keep the three purity guards mirrored, as the Code Map requires. It is a comment plus one assertion, and the full suite is green.

