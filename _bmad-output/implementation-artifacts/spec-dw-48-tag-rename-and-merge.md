---
title: 'DW-48: tag rename and merge on /products/tags'
type: 'feature'
created: '2026-07-28'
status: 'done'
baseline_revision: 'afc31fe'
final_revision: 'cb5bd00'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** `/products/tags` lists every assigned tag with a product count next to an Actions column offering nothing but "View products", so a typo'd tag can only be corrected by editing every carrying product one form at a time — while the sibling `/products/categories` page in the same navbar dropdown has offered rename-with-descendants since Story 3.2.

**Approach:** Add `CatalogService.rename_tag()` mirroring `rename_category_path` (pure argument checks first, one narrowing SELECT, Python decides, one commit, same audit logging), plus a `/products/tags/rename` GET-previews-then-POST page mirroring `/products/categories/rename` and a per-row Rename link on the tag listing. Renaming onto a tag that already exists **merges** the two (a tag set is a set, so the union is well defined) — unlike the category rename, which refuses a branch merge because a Product carries at most one category.

## Boundaries & Constraints

**Always:**
- Every tag string is normalized by `app/utils/tag.py` alone (AD-4). Routes and templates never split, trim or lowercase a tag.
- SQL narrows, Python decides. `product_tags.tag` is `utf8mb4_unicode_ci` (`app/database.py:50-55`), which folds case **and accents**, so an equality filter also matches folded near-misses. Membership in `moving` / `occupied` is decided by exact Python string equality, never by what the SQL matched.
- Atomic: either every affected row changes or none does. Every rejection is decided before any row is mutated; the write is one commit.
- Refusals are **raised** as `ValidationError` with the field the operator can act on (`old_tag` / `new_tag`), never swallowed into a False — same contract as `rename_category_path` and `set_product_tags`.
- No ORM or SQL in routes; all mutation goes through `CatalogService` (AD-1/AD-2).
- Audit-log success **outside** the try/commit so it cannot raise over a completed rename; log failures as a `logger.warning`. A refused rename writes no audit-error record.

**Block If:**
- The work would require an Alembic migration (it must not — no schema change).

**Never:**
- No tag **delete**. Removing a tag from every product is a destructive bulk operation that wants its own confirmation; out of scope by explicit decision.
- No new datastore, no tag vocabulary table, no change to `set_product_tags` / `list_tags` / `find_products_by_tag` semantics.
- No autocomplete on the new-tag input. Unlike the category destination (which must not exist), an existing destination is legal here — but offering the existing vocabulary would invite an accidental merge, so the field stays plain.
- No multi-tag or combined faceting (Epic 8).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Plain rename | 3 products carry `ssr`; nothing carries `relay` | 3 rows rewritten to `relay`; returns `(3, 0)` | No error expected |
| Merge | P1,P2 carry `ssr`; P2,P3 carry `relay` | P1's row rewritten; P2's `ssr` row **deleted** (already carries `relay`); returns `(1, 1)`. P2 ends with one `relay` | No error expected |
| As-typed input | `'  SSR '` → `' Relay '` | Normalized to `ssr` → `relay` before anything else | No error expected |
| Folded near-miss not dragged | P1 carries `café`, P2 carries `cafe`; rename `cafe` → `x` | Only P2's row moves; P1 keeps `café` | No error expected |
| Folded destination conflict | P1 carries `ssr` **and** `café`; rename `ssr` → `cafe` (MariaDB) | Refused, nothing written; message names the conflicting product ids | `ValidationError(field='new_tag')` |
| Blank source / destination | `''` or whitespace | Refused | `ValidationError(field='old_tag'/'new_tag')` |
| Unusable value | over-length, or containing `,` | Refused, nothing written | `ValidationError` (`InvalidTagError` never leaks) |
| Unstorable value | canonical value carrying NUL or an unpaired surrogate | Refused before the session opens | `ValidationError` |
| No-op rename | `ssr` → `SSR` (same canonical form) | Refused on the arguments alone | `ValidationError(field='new_tag')` |
| Source carries nothing | no product carries `ssr` | Refused | `ValidationError(field='old_tag')` |
| Concurrent duplicate insert | racing writer commits the destination tag first | Rolled back; refused as retryable | `ValidationError` with `retryable = True` |
| Non-duplicate `IntegrityError` | FK broken by a concurrently deleted product | Re-raised with its own identity, audited as an error | Re-raise |

</intent-contract>

## Code Map

- `app/mariadb_catalog_service.py` -- add `rename_tag()` in the Story 3.3 tag block (after `list_tags`, ~:1440). Mirror `rename_category_path` (:847-1099) for structure/audit and `set_product_tags` (:1197-1405) for the folding/`IntegrityError` handling. Reuse `_is_duplicate_key_violation` (:1103), `sql_text.is_storable_text`, `tag_util.normalize_tag`, `MAX_TAGS_NAMED_IN_ERROR` (:96).
- `app/main/routes.py` -- add `_tag_rename_preview()` and the `tag_rename` route beside `tag_list` (:3067). Mirror `category_rename` (:2971-3055) including the `log_audit_operation(..., 'input', form_data=...)` call and the `_rerender` / `preview_failed` handling. All needed imports already exist.
- `app/templates/product/tag_rename.html` -- NEW. Mirror `product/category_rename.html`.
- `app/templates/product/tags.html` -- add a Rename link to the Actions cell (:35-40).
- `app/utils/tag.py` -- docstring only: the "Future extensibility" note (:57-61) says a rename "would belong in the service"; update it to record that it now does.
- `tests/unit/test_csrf_protection.py` -- `FORM_TEMPLATE_ENDPOINTS` (:123-133) is parity-checked against every POST form under `app/templates/**`; a new form template that is not listed **fails the suite**.
- `docs/user-manual.md` -- add `#### Renaming a Tag` under `### Tags` (:1023), mirroring `#### Renaming a Category` (:963).

## Tasks & Acceptance

**Execution:**
- [x] `app/mariadb_catalog_service.py` -- add `rename_tag(old_tag, new_tag) -> Tuple[int, int]` returning `(renamed, merged)` -- the whole feature's behavior lives here; the route is a view over it.
- [x] `app/main/routes.py` -- add `_tag_rename_preview` + `GET/POST /products/tags/rename` (`main.tag_rename`) -- GET previews the source tag and its count; POST calls the service and reports the outcome.
- [x] `app/templates/product/tag_rename.html` -- new confirm-and-submit form -- the preview is the confirmation.
- [x] `app/templates/product/tags.html` -- per-row Rename link -- the page that knows the counts is where the action belongs.
- [x] `app/utils/tag.py` -- correct the stale "nothing further is planned" docstring note.
- [x] `tests/unit/test_catalog_service.py` -- new `TestRenameTag` class covering every I/O Matrix row -- use the established monkeypatched-`Session`/`flush`-raises-`IntegrityError` harness (:2552, :2613, :2701) for the MariaDB-only cases, since the unit suite runs on SQLite.
- [x] `tests/unit/test_product_routes.py` -- new `TestTagRenamePage` class beside `TestTagPages` (:1244) -- GET preview, guard redirects, POST success flash, POST refusal re-render with `is-invalid` on the right field.
- [x] `tests/unit/test_csrf_protection.py` -- register `('product/tag_rename.html', 'main.tag_rename', {})`.
- [x] `tests/integration/test_identifier_collation.py` -- add `TestTagRenameUnderFoldingCollation` using `integration_catalog_service` -- the folded-destination-conflict and accent-fixing renames only take their real path against MariaDB.
- [x] `tests/e2e/test_tag_rename.py` -- NEW, mirroring `tests/e2e/test_category_rename.py` -- one rename-through-the-form test and one merge test, using `_unique_prefix` isolation.
- [x] `docs/user-manual.md` -- document the page and quote every refusal message verbatim, as the category section does.
- [x] `tests/e2e/test_product_tags.py` -- (added during implementation) scope `test_the_tag_listing_links_to_the_filter`'s click to `a[href*="/products/tags/filter"]` -- the new Rename link made the row's bare `a` locator a Playwright strict-mode violation. Caught by the full e2e run, not by the unit suite.

**Acceptance Criteria:**
- Given a tag with products and a destination nothing carries, when the operator submits the rename form, then every carrying product ends up with the new tag, none with the old, and the flash names both canonical forms and the counts.
- Given a destination tag that already exists, when the rename is submitted, then the two tags are merged — no product ends up carrying a duplicate row, and no product loses an unrelated tag.
- Given any refusal, when the POST returns, then not one `product_tags` row has changed and the form re-renders with the message and the typed destination intact.
- Given the tag listing, when it renders, then each row offers both "View products" and "Rename", and the existing count/link behavior is unchanged.
- Given a successful rename, when the audit log is inspected, then one `rename_tag` success record carries `old_tag`, `new_tag` and the counts; given a refusal, then no audit record is written.

> Note (review pass 1, P5): the third criterion was refined during review. A refusal still changes nothing, but only a **destination** refusal re-renders the form; a **source** refusal now returns to the listing with the reason, because `old_tag` is a hidden input and the re-rendered form offered nothing to correct.

## Spec Change Log

None. No `bad_spec` finding was raised; the spec was not amended and no implementation loopback occurred.

## Review Triage Log

### 2026-07-28 — Review pass 1
- intent_gap: 0
- bad_spec: 0
- patch: 11: (high 0, medium 2, low 9)
- defer: 0
- reject: 8
- addressed_findings:
  - `[medium]` `[patch]` P8 — `_fold_the_select` stubbed `or_` with `sqlalchemy.true()`, widening the SELECT to every row, so any unrelated tag on a moving product became a "conflict" and the collation-conflict tests could pass against a partition unrelated to folding. Made the stub name the fold-equivalent spellings it simulates, and added `test_an_unrelated_tag_on_a_moving_product_is_not_a_conflict` (fails against the old stub).
  - `[medium]` `[patch]` P7 — a pure merge (`renamed == 0`) flashed `… — 0 product(s) updated.` and then contradicted itself. Success flash now branches: a pure merge gets its own sentence, the mixed case still reports both counts separately.
  - `[low]` `[patch]` P1 — the service set `retryable = True` on the concurrent-writer refusal and the route ignored it, rendering the race identically to a permanent collision. Route now re-renders with `error_field=None` for retryable refusals, matching the `_apply_product_tags` precedent.
  - `[low]` `[patch]` P5 — an `old_tag` refusal re-rendered a form whose only correctable field is hidden, a dead end escapable only by Cancel. Source refusals now flash and redirect to the listing, as the GET guard already did; this also removed the double statement of the problem.
  - `[low]` `[patch]` P4 — `?tag=a,b` flashed "No products carry tag …", diagnosing the wrong problem. Now uses `tag_filter`'s existing wording for an unusable tag.
  - `[low]` `[patch]` P2 — the conflict message's spellings list was silently truncated while the comment above claimed both lists state their cap. It now appends `, ... (N in total)` like the product-id list.
  - `[low]` `[patch]` P3 — `rename_tag` is a second writer of `product_tags.tag`, but five places asserted `set_product_tags` is the sole writer. Reworded to "every writer normalizes" (the canonicality argument the claims support is unchanged), including the pre-existing `app/database.py` docstring.
  - `[low]` `[patch]` P6 — the docstring's atomicity claim outran the implementation. Added the check-then-write caveat in `rename_category_path`'s voice: the guarantee covers rows the SELECT saw, not a concurrent writer adding the source tag mid-transaction.
  - `[low]` `[patch]` P9 — `test_the_conflict_list_states_that_it_was_truncated` asserted only `len(named) <= MAX + 1` with substring matching (id `1` matched inside `11 in total`). Rewritten to parse both lists out of the message and assert exact counts and the true total.
  - `[low]` `[patch]` P10 — the merge was justified as lossless without noting it is not undoable. Added one sentence to the form's confirmation note and the user manual.
  - `[low]` `[patch]` P11 — e2e pinned only the two happy paths while the sibling category-rename e2e pins a refusal. Added `test_a_refused_rename_comes_back_on_the_form_and_changes_nothing`.

Rejected (8): GET has no `preview_failed` handling (matches the `category_rename` GET precedent); `_tag_rename_preview` reads via `list_tags()` (the suggested scalar `COUNT` is *wrong* under the folding collation — Python-side grouping is what makes the count correct); the route re-normalizes for the flash (same as `category_rename`); the audit key is the old tag (same as `rename_category_path`; `changes` carries both); `preview_failed` still offers Submit (same as `category_rename.html`); `MAX_TAGS_NAMED_IN_ERROR` reused for product ids (naming nit); unbounded transaction on a very popular tag (same shape as `rename_category_path`; single-operator app); signed `expected_total` to close the GET→POST window (over-engineering, and covered by P6's caveat).

### 2026-07-28 — Review pass 2 (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 1, low 4)
- defer: 1: (high 0, medium 0, low 1)
- reject: 17
- addressed_findings:
  - `[medium]` `[patch]` F1 — the success audit record counted merged products without naming them. The merge is the one part of the rename that renaming back does not undo (it would drag the destination's original members along, which the form and the manual now say), so a count left it unreconstructible from the only record the operation writes. `changes` now carries `merged_product_ids`, captured before the deletes because a deleted row cannot answer for its `product_id` after the commit. Two tests pin it, including the empty-list case so a reader never has to tell "nothing merged" from "an older record that did not say".
  - `[low]` `[patch]` F2 — `MAX_TAGS_NAMED_IN_ERROR`'s comment said it caps *tags* and cited `MAX_TAGS_PER_PRODUCT` (50) as the ceiling it guards against; `rename_tag` also applies it to product ids, whose count has no ceiling at all. Comment now covers both callers and states the stronger reason.
  - `[low]` `[patch]` F3 — the conflict message calls every folded row on a moving product "the same tag" as the *destination*, which is true only because `uq_product_tags_product_tag` folds too (one product cannot hold both `ssr` and a spelling the index reads as `ssr`, so a folded row on a moving product can never be folding onto the source). The code relied on that invariant without stating it anywhere; it is now recorded where the partition depends on it, naming what starts lying if the constraint ever stops folding.
  - `[low]` `[patch]` F4 — the a11y affordance failed the users it exists for: `aria-describedby` pointed only at a feedback slot reading "This tag was rejected — see the message at the top of the page", so a screen reader on the invalid input announced where to look instead of what was wrong. The alert carrying the reason is now named first (`aria-describedby="rename-error new_tag-error"`), keeping the deliberate no-duplicate-sentence choice for sighted users. Pinned by `test_a_refused_destination_marks_that_field`.
  - `[low]` `[patch]` F5 — `tests/e2e/test_tag_rename.py`'s isolation note described `clear_test_data()` as truncating `products` "and, by cascade, `product_tags`"; it does neither — it issues per-table `.delete()` calls in FK order, `ProductTag` explicitly among them. It also claimed the file "asserts only positively, never absence" two functions above three absence assertions. An isolation argument resting on a false account of the mechanism is worth nothing when the mechanism changes; both claims corrected to what the code does.

Rejected (17), the ones worth naming: the ledger's `decision:` was read as mandating refusal (it says "merge-on-collision" in those words; the Design Notes resolve its self-contradictory parenthetical); the spec/ledger status metadata disagreeing (workflow bookkeeping the orchestrator owns); the GET preview's `list_tags()` full scan (the listing that reaches this page already scans the same table — the narrower `WHERE tag = :source` the reviewer proposed is correct, but the cost is not one this application can feel); the GET's missing `preview_failed` guard (`tag_list` and `category_rename`'s GET are unguarded identically — a backend that would 500 here already 500'd on the page you came from); an unstorable-but-normalizable `?tag=` (NUL) reaching "No products carry tag …" (the statement is *true*, no query is issued with the value, and `tag_filter` answers the same input the same way); the raw `str(e)` flashed on a source refusal (`old_tag` is hidden and arrived from a validated GET, so the library-worded cases are unreachable from the UI); the GET flashing the as-typed tag where the service flashes the canonical one (showing what the link contained is the better diagnosis for a mangled link); the truncation comment's claimed parity with `set_product_tags` (both cap and say so — only the wording differs, which is what the comment claims); the merge rationale restated in seven places and the GET normalizing twice (prose density is this file's house style; the second normalize is free); `_fold_the_select` monkeypatching a module-global `or_` (no defect today, and pass 1 already tightened the stub); no service-level assertion of a pure-merge `(0, N)` tuple (`test_a_pure_merge_does_not_report_zero_updated` exercises exactly that through the real service, end to end); the folded-conflict path being "signed off unrun" (`nox -s integration` did run — 38 passed against a real MariaDB testcontainer); a concurrent writer inserting a *folded* near-miss being reported as retryable, and a signed `expected_total` closing the GET→POST window (both are the check-then-write limitation the docstring already documents and pass 1 already weighed); the unguarded `log_audit_operation(..., 'input', ...)` (every route in the blueprint calls it the same way — see DW-199).

## Design Notes

**Why merge here but rejection there.** The intent's parenthetical ("merge-on-collision, following `rename_category_path`'s existing collision decision") reads as a contradiction only until the two collision *kinds* are separated, and both are implemented:

- **Exact collision** — the destination tag already exists as a distinct canonical string. **Merge.** A Product carries many tags, so the union is lossless; a Product carries one category, which is why the category rename refuses.
- **Folded collision** — the destination is Python-distinct from a tag the product already carries but equal under `utf8mb4_unicode_ci` (`cafe` vs `café`). **Refuse**, naming the products. This is precisely the decision `rename_category_path` makes about its `unclaimed` rows and `set_product_tags` makes about its collisions: Python must not guess the database's folding rules, and silently discarding one of two tags the operator deliberately typed differently is the one outcome neither method allows.

**Partitioning (the load-bearing detail).** One query, `WHERE tag = old OR tag = new`, then partition in Python by exact equality:

```python
moving   = [r for r in rows if r.tag == old_canonical]
occupied = {r.product_id for r in rows if r.tag == new_canonical}
folded   = [r for r in rows if r.tag not in (old_canonical, new_canonical)]
```

`folded` is empty on SQLite and non-empty only under MariaDB's collation. A `folded` row whose `product_id` is in `moving` is the refusal above — **detected before any write**, so the `IntegrityError` catch is left as a backstop for a concurrent writer only. Then each moving row is **deleted** if its product is in `occupied` (that is the merge) and otherwise rewritten. Flush the deletes before the rewrites, for the reason `set_product_tags` documents at :1264-1270: SQLAlchemy's unit of work emits inserts/updates before deletes, and a row on its way out must not collide with a rewritten one under the folding unique index.

**Preview honesty.** The GET cannot know the destination (it is typed on the form), so — unlike the category preview, which can enumerate the whole subtree — the tag preview shows the source and its count and states the merge rule up front. The POST flash then reports what actually happened, distinguishing rewritten from merged products. That keeps "the preview IS the confirmation" true without inventing a second confirmation step, which the intent reserves for the deliberately-excluded delete.

**No canonicality guard.** The categories page withholds its Rename link from non-canonical rows because Story 3.1's backfill left some in place. `product_tags` has no such legacy: it was created empty by `68707d1f48bf` and `set_product_tags` is its only writer, normalizing every value. So the tag route simply normalizes `?tag=` and matches — do not port `_is_canonical_path` or the "Not canonical" badge.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all pass, including the CSRF template-parity check.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: pass (`app/utils/tag.py` docstring edit must not break its examples).
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` -- expected: pass. **Requires a 20-minute tool timeout**; run detached and poll. Revert any screenshot files it rewrites.
- `git diff --stat migrations/` -- expected: empty. No schema change.

**Manual checks (if no CLI):**
- The integration session needs Docker (MariaDB testcontainer). If it cannot run in this environment, state that plainly rather than reporting it as passed.

## Auto Run Result

Status: done

**Change.** `/products/tags` gains rename-and-merge, closing the asymmetry with `/products/categories`. `CatalogService.rename_tag(old_tag, new_tag) -> (renamed, merged)` rewrites every row carrying the source tag onto the destination in one transaction, and where a product already carries the destination it deletes the source row instead — the merge. The two collision kinds are handled differently and deliberately: an **exact** destination collision merges (a tag set is a set, so the union is lossless), while a **folded** collision under `utf8mb4_unicode_ci` (`cafe` vs `café`) is refused before anything is written, naming the products, because Python must not guess the database's folding rules. That resolves the apparent contradiction in the intent's "merge-on-collision, following `rename_category_path`'s existing collision decision" — both readings are correct, for different collisions.

**Files changed**
- `app/mariadb_catalog_service.py` — new `rename_tag()`: pure argument checks, one narrowing SELECT, Python-exact partition into moving/occupied/folded, deletes flushed before rewrites, one commit, `IntegrityError` backstop, audit logging outside the commit. Pass 2 added `merged_product_ids` to the success record and recorded the unique-index invariant the conflict message rests on.
- `app/main/routes.py` — `_tag_rename_preview()` and `GET/POST /products/tags/rename`.
- `app/templates/product/tag_rename.html` — NEW confirm-and-submit form; the preview is the confirmation. Pass 2 pointed `aria-describedby` at the alert carrying the reason.
- `app/templates/product/tags.html` — per-row Rename link.
- `app/utils/tag.py`, `app/database.py` — docstrings corrected (the rename landed where the note said it would; `set_product_tags` is no longer the sole writer).
- `tests/unit/test_catalog_service.py` — `TestRenameTag` (36 tests) with a collation-folding stub.
- `tests/unit/test_product_routes.py` — `TestTagRenamePage` (17 tests).
- `tests/unit/test_csrf_protection.py` — registered the new form template (the parity check fails without it).
- `tests/integration/test_identifier_collation.py` — `TestTagRenameUnderFoldingCollation` (4 tests, real MariaDB).
- `tests/e2e/test_tag_rename.py` — NEW (3 tests). `tests/e2e/test_product_tags.py` — one existing locator scoped, see residual risks.
- `docs/user-manual.md` — `#### Renaming a Tag`, every refusal quoted verbatim.

**Review findings.** Pass 1: 11 patches applied (2 medium, 9 low), 0 deferred, 8 rejected. Pass 2 (follow-up): 5 patches applied (1 medium, 4 low), 1 deferred (DW-199), 17 rejected. Both passes: 0 intent gaps, 0 spec defects, no implementation loopback. See the Review Triage Log.

**Verification** (all run by the orchestrating session, not only reported by a subagent)
- `nox -s tests` — 3025 passed, 451 deselected.
- `nox -s doctests` — 21 passed. (First attempt aborted while building the `pt-p710bt-label-maker` git dependency into a fresh nox venv — a transient fetch failure, not a test failure; the retry installed and passed.)
- `nox -s integration` — 38 passed against a real MariaDB testcontainer, including the 4 folding tests.
- `nox -s e2e` — **full suite against the final tree**: 412 passed, 1 skipped, 0 failed, in 20m29s.
- `git diff --stat migrations/` — empty. No schema change.
- Screenshots rewritten by the e2e run were reverted and are not part of this commit.

**Residual risks**
- The rename is check-then-write with no row locking. A concurrent writer adding the source tag between the SELECT and the COMMIT leaves that product behind, and the operator still sees a success flash. Documented in the docstring; the same limitation `rename_category_path` accepts for the same single-operator reason.
- A merge is lossless per product but not undoable: renaming back would carry the destination's original members along. The form and the manual say so, and the audit record now names the merged products, but nothing in the UI reverses it.
- The folded-destination conflict is exercised against a real folding collation only in the integration tier; the unit tier reaches it through a monkeypatched `or_` that simulates what MariaDB would have matched.
- Adding the Rename link made an existing e2e test's bare `a` locator a Playwright strict-mode violation. Fixed by scoping the locator; other bare-`a` row locators elsewhere in the e2e suite were not audited.

