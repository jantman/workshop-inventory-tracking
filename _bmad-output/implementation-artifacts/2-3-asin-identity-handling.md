---
title: 'ASIN identity handling'
type: 'feature'
created: '2026-07-24'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
baseline_revision: '889ab16'
final_revision: '1df1460'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** An Amazon purchase can be recorded (Story 1.4 `record_purchase` writes the ASIN into the free-text `purchases.vendor_sku` column), but nothing indexes that ASIN as a `ProductIdentifier`. So a repeat Amazon buy of the same part has no identifier to resolve against and would create a duplicate Product, while `record_purchase` + `add_identifier` each commit their own transaction, so there is no atomic "record the purchase **and** index its ASIN" unit of work (FR11, AD-9).

**Approach:** Add one new service method `CatalogService.record_amazon_purchase` that, in a single transaction, inserts the Purchase (with `vendor_sku` = the ASIN) **and** indexes the ASIN as an `ASIN`-type `ProductIdentifier` on the same Product. It reuses Story 2.1's vendor-scoped uniqueness so an ASIN already indexed on a **different** Product is rejected and surfaced (never silently re-attached), is idempotent when the same Product already carries that ASIN (repeat buys), and never treats the ASIN as Product identity.

## Boundaries & Constraints

**Always:**
- The ASIN write and the ASIN index happen in **one session/transaction**: on any conflict nothing is committed (no orphan Purchase, no half-capture). Do NOT compose the existing public `record_purchase` + `add_identifier` — each commits independently and cannot be made atomic together.
- ASIN is **vendor-scoped** (already in `VENDOR_SCOPED_IDENTIFIER_TYPES`); the identifier's `vendor_scope` and the Purchase's `vendor` both come from the same `vendor` value (default `'Amazon'`). The ASIN is stored **as entered** (stripped only) as both `purchases.vendor_sku` and the identifier `value` — not normalized (consistent with Story 2.2 normalizing GTIN only).
- Idempotent ASIN index for the **same** Product: if the Product already carries `(ASIN, value, vendor_scope)`, do **not** insert a second identifier row and do **not** error — record the new Purchase and return success (repeat Amazon buys of the same Product must work).
- Conflict with a **different** Product: reject with a caught `ValidationError` whose message names the conflicting Product's id (mirror `add_identifier`'s wording), roll the whole transaction back, and record no Purchase — the ASIN is never silently attached/merged (FR11, AD-9). Catch the DB `IntegrityError` on the unique index and convert it, never let it leak.
- Preserve every Story 2.1/1.4 invariant on both writes: blank/`None` ASIN rejected as `ValidationError(field=...)`, value/scope bounded by `IDENTIFIER_MAX_LENGTH` (255), `order_date` defaults to `date.today()` when omitted, blank optional fields cleaned via `_clean`, audit-log the operation, close the session in `finally`, return a snapshot dict taken **before** commit.
- Product identity never depends on the ASIN: the ASIN lives only as a `ProductIdentifier` index + `purchases.vendor_sku`; it is never written as `internal_id` or any identity/FK. A rejected or reassigned ASIN leaves both Products' identities unchanged.

**Block If:**
- The intent is read to require the Epic 7 capture flow — the HTTP capture endpoint, `request_key` idempotency, the de-dup **lookup** (find Product by prior ASIN / `vendor_sku`), or **confirm-not-merge** operator prompting on manufacturer/MPN mismatch. Those are Story 7.2, not here; do not build them.

**Never:**
- No Alembic migration (`purchases.vendor_sku`, `product_identifiers`, and the `ASIN` enum member all already exist). No `float`. No route/template/UI/bookmarklet. No new `IdentifierType` member. No ASIN normalization/uppercasing (leave the SQLite↔MariaDB case-parity item in the deferred-work ledger). Do not modify the existing `record_purchase` or `add_identifier` signatures/behavior.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| New ASIN, first sight | Product A; `record_amazon_purchase(A, asin='B01ABC2DEF', unit_price=Decimal('9.99'))` | one `purchases` row (`vendor_sku=='B01ABC2DEF'`, `vendor=='Amazon'`) **and** one `ASIN` identifier (`value=='B01ABC2DEF'`, `vendor_scope=='Amazon'`) both persist | No error |
| Repeat buy, same Product | A already has ASIN `'B01ABC2DEF'`; call again for A | a **second** `purchases` row persists; ASIN identifier count for A stays 1 (idempotent index) | No error |
| ASIN on a different Product | Product B holds ASIN `'B01ABC2DEF'` (Amazon); call for Product A | rejected — nothing written for A (no Purchase, no identifier) | caught `ValidationError` naming B's product id |
| Unknown Product | `product_id` not in `products` | rejected, nothing written | caught `ValidationError` (`field='product_id'`) |
| Blank / None ASIN | `asin=''` or `asin=None` | rejected before any write | caught `ValidationError` (`field='asin'`) |
| Overlong ASIN | `asin` longer than 255 chars | rejected | caught `ValidationError` (`field='value'`) |
| Identity independence | A has ASIN `X`; B given the same ASIN `X` | B is rejected; A keeps its ASIN and identity; B's identity unchanged (ASIN reassignment cannot move identity) | caught `ValidationError` |

</intent-contract>

## Code Map

- `app/mariadb_catalog_service.py` — **add** `record_amazon_purchase(self, product_id, *, asin, vendor='Amazon', order_date=None, received_date=None, quantity=None, unit_price=None, order_number=None, source_url=None) -> Optional[dict]`. New single-session method: load Product (missing → `ValidationError` `field='product_id'`); validate/strip `asin` (blank → `field='asin'`; len>255 → `field='value'`); scope = `vendor.strip()`; query existing `ProductIdentifier(identifier_type='ASIN', value=asin, vendor_scope=scope)` — different product → `ValidationError` naming it, same product → skip insert, none → add a new `ProductIdentifier`; add the `Purchase` (`vendor_sku=asin`, `vendor`, `order_date` default `date.today()`, other fields via `_clean`); `flush` (catch `IntegrityError` → rollback → re-query → surface conflict as `ValidationError`); snapshot, `commit`, audit-log, return the Purchase snapshot (with the ASIN identifier reflected). Reuse `_clean`, `IDENTIFIER_MAX_LENGTH`, `VENDOR_SCOPED_IDENTIFIER_TYPES`, the `log_audit_operation` pattern, and the `Purchase`/`ProductIdentifier` ORM. Do not touch `record_purchase`/`add_identifier`.
- `app/models.py` — no change (`ASIN` already in `IdentifierType` and `VENDOR_SCOPED_IDENTIFIER_TYPES`).
- `tests/unit/test_catalog_service.py` — **add** `record_amazon_purchase` service tests covering every I/O-matrix row (see Tasks).

## Tasks & Acceptance

**Execution:**
- [x] `app/mariadb_catalog_service.py` — implement `record_amazon_purchase` per the Code Map: atomic Purchase-insert + ASIN-index in one transaction; vendor-scoped ASIN reusing 2.1 uniqueness; idempotent for the same Product; different-Product conflict caught from `IntegrityError` and surfaced as a `ValidationError` naming the conflict; all 2.1/1.4 guards (blank/length/`_clean`/`date.today()` default/audit/`finally`-close) preserved; ASIN stored as-entered and never as identity (FR11, AD-9).
- [x] `tests/unit/test_catalog_service.py` — add a test class for `record_amazon_purchase` asserting: new-ASIN persists both the Purchase (`vendor_sku`==ASIN, `vendor`=='Amazon') and one `ASIN` identifier; repeat buy on the same Product adds a Purchase but not a second identifier; same ASIN on a different Product is rejected (naming it) with **no** Purchase or identifier written for the caller; unknown Product / blank ASIN / overlong ASIN each raise `ValidationError` with the expected `field`; and identity independence (a rejected ASIN leaves both Products' identities intact). Use the existing `catalog_service`/`create_product` fixtures.

**Acceptance Criteria:**
- Given a Product and a never-seen Amazon ASIN, when `record_amazon_purchase` runs, then exactly one Purchase (ASIN in `vendor_sku`) and one `ASIN`-type `ProductIdentifier` for that Product are persisted together, and no raw `IntegrityError`/DB error reaches the caller (FR11).
- Given a Product that already carries that ASIN, when `record_amazon_purchase` is called again for it, then a new Purchase is recorded and the ASIN identifier is not duplicated (repeat Amazon buys resolve to the same Product — FR11).
- Given the same ASIN already indexed on a **different** Product, when `record_amazon_purchase` targets this Product, then it is rejected with a caught `ValidationError` naming the conflicting Product and nothing is written for the caller — the ASIN is never silently attached and neither Product's identity changes (FR11, AD-9).
- Given `nox -s tests`, when the suite runs, then the new `record_amazon_purchase` tests pass and every pre-existing test stays green.

## Spec Change Log

_No bad_spec loopbacks — the intent contract and spec sections held through review._

## Review Triage Log

### 2026-07-24 — Follow-up review pass
- intent_gap: 0
- bad_spec: 0
- patch: 0
- defer: 0
- reject: 16
- addressed_findings:
  - none
- notes: Fresh independent adversarial + edge-case pass on the committed diff (baseline `889ab16`). All 16 deduplicated findings rejected as noise/by-design: ASIN & vendor case/whitespace normalization and no-ASIN-shape-validation (spec `Never: no normalization/uppercasing`; SQLite↔MariaDB case-parity already in the deferred-work ledger); blank vendor → global scope (by-design, mirrors 2.1 `add_identifier`); `field='asin'` vs `'value'` split (mandated by this spec's I/O matrix, asserted by tests); `Optional[dict]`/"mirrors record_purchase"/raises-vs-returns-None (harmless supertype; raising a caught `ValidationError` on conflict is the spec-required behavior); no route/UI/integration coverage and no quantity/price/date validation (spec `Never: no route/template/UI`; parsing is the route's job, record_purchase parity); concurrent-race branch untested / TOCTOU product-delete / Purchase-flush IntegrityError / rejected-conflict not audited (negligible single-writer-SQLite-untestable concurrency edges routed through the generic handler and never mislabeled, mirroring existing `add_identifier`/`record_purchase` patterns); over-grown docstring/comments (cosmetic). No new deferred-work entries (case-parity and per-request-engine items already logged). Verified `nox -s tests` green (496 passed).

### 2026-07-24 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 1, low 2)
- defer: 0
- reject: 8
- addressed_findings:
  - `[medium]` `[patch]` The `except IntegrityError` handler treated *any* found `(ASIN, value, scope)` row as a cross-product conflict, so (a) an unrelated integrity failure on the idempotent-skip path would have been mislabeled as "ASIN already exists on {this same product}", and (b) a same-product insert race dropped a valid Purchase with a self-contradictory error. Restructured to flush the identifier **on its own** (so a unique-index `IntegrityError` is unambiguously the ASIN), raise the conflict `ValidationError` only when the row is owned by a **different** product, fall through to record the Purchase idempotently when the same product won the race, and re-raise any non-ASIN integrity error rather than mislabel it.
  - `[low]` `[patch]` The Purchase stored `vendor` raw while the ASIN identifier stored a stripped `vendor_scope`, so a padded vendor diverged between the two rows and an all-whitespace overlong vendor evaded the length guard into a raw `DataError`. Now stores the stripped vendor (`scope or None`) on the Purchase so both rows agree.
  - `[low]` `[patch]` Added a field-pass-through test (order/received dates, quantity, `Decimal` price, order number, source URL) with a non-default vendor asserting Purchase↔identifier vendor consistency, and annotated `product_id: int` to document the route-parses-caller contract.
  - Rejected (by-design / out-of-scope / non-consequential): blank vendor → global scope (consistent with 2.1 `add_identifier` vendor-scoping); ASIN not uppercase-normalized (explicit spec `Never`; the SQLite↔MariaDB case-parity item is already in the deferred-work ledger); `field='asin'` vs `'value'` split (matches this spec's I/O matrix and is asserted by tests); `Optional[dict]` return annotation (harmless supertype — the method returns a dict or raises); audit `item_id=f'product:{id}'` (matches `add_identifier`; the codebase already mixes both styles); no ASIN shape validation (Epic 7 capture-time concern; mirrors `add_identifier`); triplicated conflict-message wording (extracting a shared helper would touch the tested `add_identifier`); the "claimed tests not in diff" note (an artifact of the abbreviated review diff — the real diff contains every test).

## Design Notes

**Why a new method rather than composing the two public ones.** `record_purchase` and `add_identifier` each open, commit, and close their own session, so calling them in sequence cannot be atomic — a mid-sequence ASIN conflict would leave a committed Purchase pointing at the wrong Product. `record_amazon_purchase` therefore does both inserts on one `session` and commits once. The ASIN identifier is resolved and flushed **on its own first**, guarded by the `uq_product_identifiers_type_value_scope` unique constraint 2.1 established: a unique-index `IntegrityError` at that point is unambiguously the ASIN, so the handler names a **different**-product conflict as a `ValidationError`, treats a same-product race as idempotent (falls through and records the Purchase), and re-raises anything else. The Purchase then flushes separately, so a Purchase-level integrity error is never mislabeled as an ASIN duplicate. Keeping `add_identifier` untouched avoids regressing the 2.1/2.2 tests.

**Idempotency and identity.** The pre-insert query distinguishes "same Product already has this ASIN" (skip the identifier insert, still record the Purchase — repeat buy) from "different Product owns it" (reject). Because the ASIN is only ever a `ProductIdentifier` row plus `purchases.vendor_sku` — never `internal_id` or a FK — a reassigned or rejected ASIN cannot move Product identity; the internal id (Story 2.4) is the identity authority.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` — expected: all pass, including the new `record_amazon_purchase` tests; no pre-existing test regresses.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests -- -k record_amazon_purchase` — expected: the new atomic/idempotent/conflict cases pass. **Note:** this `-k` filter selects nothing (the test class is `TestRecordAmazonPurchase`, no underscores); use the unfiltered `nox -s tests` or `-k RecordAmazonPurchase` to target them.

## Auto Run Result

Status: done

### Summary
Follow-up (second) review pass over the previously-completed Story 2.3 change: `CatalogService.record_amazon_purchase`, which atomically records an Amazon Purchase (`vendor_sku` = ASIN) and indexes that ASIN as a vendor-scoped `ASIN`-type `ProductIdentifier` in a single transaction — idempotent for repeat buys on the same Product, rejecting an ASIN already owned by a different Product with a caught `ValidationError`, and never treating the ASIN as Product identity (FR11, AD-9). No code changes were made in this pass.

### Files changed (this pass)
- `_bmad-output/implementation-artifacts/2-3-asin-identity-handling.md` — appended follow-up review-triage entry, corrected the `-k` verification note, set `followup_review_recommended: false`, added this result.

(Implementation files `app/mariadb_catalog_service.py` and `tests/unit/test_catalog_service.py` were unchanged from `d31f811`.)

### Review findings breakdown
- Patches applied: 0
- Deferred: 0 new (case-parity and per-request-engine items already in the ledger)
- Rejected: 16 (all noise / by-design / spec-`Never` / sibling-method parity — see the follow-up triage-log entry)

### Verification
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` → **496 passed, 305 deselected** (green; no regressions).

### Follow-up review recommendation
`false` — this pass produced no review-driven changes; the implementation held unchanged under an independent adversarial + edge-case review.

### Residual risks
- SQLite (unit tests) vs MariaDB (prod) case-sensitivity parity for identifier uniqueness — already tracked in the deferred-work ledger, not regressed here.
- The concurrent-insert race-recovery branch and TOCTOU-on-product-deletion are defensive paths not exercisable by single-writer SQLite unit tests; logic was reviewed and mirrors established `add_identifier`/`record_purchase` patterns.

