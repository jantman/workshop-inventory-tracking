---
title: 'ECIA per-candidate resolution and per-arm storability guard'
type: 'bugfix'
created: '2026-07-27'
status: 'done'
review_loop_iteration: 0
baseline_revision: '911dd61'
final_revision: '92cb843'
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/4-4-ecia-distributor-label-parsing.md'
warnings: ['multiple-goals', 'oversized']
---

<intent-contract>

## Intent

**Problem:** `resolve_scan`'s ECIA arm ORs both candidate part numbers into ONE query (`app/mariadb_catalog_service.py:2446-2513`) and searches only `candidates[0]` on a miss (`:2521`), producing three verified ways a distributor label resolves to LESS than it supports: a unique `1P` hit is discarded as a false ambiguity when `P` collides with a different product (DW-78); a product reachable only by `P` dead-ends entirely once a `1P` record is present, so adding an identifier subtracts an answer (DW-79, an FR36 dead end); and when `1P` matches nothing while `P` matches two products EXACTLY, both exact matches are thrown away AND the fallthrough searches the other candidate, returning no product and no hits (DW-82). Separately, `sql_text.is_storable_text(raw)` (`:2372`) judges the WHOLE envelope before the four-way branch, so an unstorable character in a record the arm never queries — a `K` order number, a `9D` date — suppresses a part-number lookup that would have resolved (DW-80).

**Approach:** Query per candidate in order and take the first unambiguous answer, at a cost of one extra query in the worst case; fall through by searching candidates in order and taking the first non-empty hit list. Move the storability guard off `raw` and onto the text each arm actually binds. This deliberately renegotiates Story 4.4's frozen "one query, one session" and "the fallthrough text is the first candidate", strictly in the tightening direction: every landing the old code reached is reached identically, no scan loses hits, and one FR36 dead end closes.

## Boundaries & Constraints

**Always:**
- **Per-candidate lookup.** Candidates stay `1P` then `P`, trimmed, non-blank, de-duplicated, in that order. Each candidate is queried on its own (`Product.mpn` OR an `EXISTS` `MPN` identifier row, both disjuncts of the existing `_matches` fold, `order_by(Product.id.asc()).limit(2)`). The FIRST candidate matching EXACTLY ONE product resolves to it; a candidate matching zero or more than one contributes no product and the walk continues. Zero or ≥2 on every candidate → no product. At most one query per candidate, and the walk stops at the first landing.
- **Per-candidate fallthrough.** On no product, search candidates in order through `search_products()` (AD-17, no second search path) and take the FIRST non-empty hit list; that candidate is the searched text. If no candidate yields hits, `free_text_hits=()` and the reported searched text is `candidates[0]`. No merging or de-duplicating across candidates — `free_text_hits` must stay exactly `search_products(<one text>)` so the search page can reproduce it from a single `q`.
- **One home for the searched text.** `ScanResolution` stays three fields (AD-15), so the route still needs the text. Replace the route's pure duplicate `_scan_search_text` (`app/main/routes.py:1979`) with a public `CatalogService.scan_search_text(resolution)` that is the SINGLE implementation of the per-arm rule, used by `resolve_scan` itself and called by `_scan_destination`. Cross-module duplication of a service-internal rule is removed, not re-copied.
- **Per-arm storability guard.** Delete the blanket `if not sql_text.is_storable_text(raw)` early return. Guard instead the text each arm binds to a LOOKUP: `internal` → `normalized_value`; `gtin` → `normalized_value`; `ecia` → each candidate individually, an unstorable candidate being dropped from the candidate list entirely so it can be neither looked up nor searched nor reported. `free_text` binds nothing. Every fallthrough search is already guarded inside `search_products` (`:2088`) — do not re-guard it in `resolve_scan`.
- **Preserved invariants.** No `str` scan raises (NFR8). No scan returns the whole catalog. NUL and unpaired-surrogate text still reaches no LIKE pattern and opens no session. `resolve_scan` stays read-only, and rows stay detached. `search_products`, `app/utils/ecia.py`, `app/utils/scan_router.py` and `app/models.py` are unchanged in behavior.
- **Docstrings are corrected in the same commit.** `resolve_scan`'s `ecia` bullet, its three numbered consequences (all closed here), its session-count paragraph and the storable-guard comment; the `_matches`/`limit(2)` comments; `_scan_url_value`'s claim that unstorable text "never reaches the search arm at all"; and every test docstring whose stated reason expires — notably `test_which_hostile_vectors_actually_reach_the_lookup`, whose prediction that relocating the guard reddens it is wrong (both its hostile characters sit IN the candidate).
- **Tests are inverted deliberately, not deleted.** The three pins named in the ledger keep their scenario, product fixtures and control cases, and assert the new outcome under a name that describes it.

**Block If:**
- Closing any entry appears to require a fourth field on `ScanResolution` or any change to `ScanClassification`/`ScanKind` — AD-15 freezes both for Epics 4/7/8/9 and widening them is a human decision.
- A schema migration appears necessary (AD-14), or the fix appears to require editing `app/utils/gs1.py`, `app/utils/gtin.py` or `app/utils/ecia.py`'s grammar.

**Never:**
- No merged/union hit list across candidates, and no re-bounding of a merged set — it cannot be reproduced from one `q` and would make `hit_count` disagree with the page.
- No change to which fields are candidates, to their order, to the `VENDOR_SKU` exclusion, or to the equality fold's two disjuncts. The backend collation divergence stays as ledgered.
- No UI, template, JS or screenshot change. No new search implementation. No edit to the deferred-work ledger — the orchestrator records resolution.

## I/O & Edge-Case Matrix

Vectors: `MPN='RC0805-10K'`, `CUSTOMER_MPN='296-1234-ND'`, `_envelope(*records)` as in `tests/unit/test_scan_resolution.py:80`.

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| DW-78 — unique `1P` hit survives a `P` collision | A `mpn=MPN`, B `mpn=CUSTOMER_MPN`; `_envelope(f'1P{MPN}', f'P{CUSTOMER_MPN}')` | `product` is A, `free_text_hits == ()`; one query, one session | No error expected |
| DW-79 — reachable only by `P` | Product described `reel of {CUSTOMER_MPN}`, no `mpn`; `_envelope('1PSUP-99999', f'P{CUSTOMER_MPN}')` | `product is None`, hits `== [that product]`; searches were `['SUP-99999', CUSTOMER_MPN]` | No error expected |
| DW-82 — two exact matches on `P` | Two products both `mpn=MPN`; `_envelope('1PSUP-99999', f'P{MPN}')` | `product is None`, hits `== [first, second]` (id-ascending), searches `== ['SUP-99999', MPN]` | No error expected |
| Ambiguous first candidate, unique second | Two products `mpn=MPN`, one `mpn=CUSTOMER_MPN`; `_envelope(f'1P{MPN}', f'P{CUSTOMER_MPN}')` | Resolves to the `CUSTOMER_MPN` product — first UNAMBIGUOUS answer wins | No error expected |
| Old landings unchanged | Any envelope whose union query matched exactly one product | The same product, `free_text_hits == ()` | No error expected |
| Single-candidate hit | Product `mpn=MPN`; `_envelope(f'1P{MPN}')` | `product` is it; exactly ONE session opened | No error expected |
| Two-candidate total miss | No product matches either; `_envelope(f'1P{MPN}', f'P{CUSTOMER_MPN}')` | `product is None`, hits `== ()`; two lookups and two searches; `scan_search_text` is `MPN` | No error expected |
| DW-80 — unstorable record the arm never queries | Product `mpn=MPN`; `resolve_scan('[)>\x1e06\x1d1PRC0805-10K\x1dK\ud800\x1e\x04')` and the `K\x00` twin | Resolves to the product — the lookup runs on the clean candidate | No error expected |
| Unstorable candidate is dropped | `_envelope('1P' + '\x00'*10)` / `_envelope('1P\ud800')` | `product is None`, hits `== ()`, ZERO sessions — no candidate remains | Never raises |
| Unstorable candidate beside a clean one | `_envelope('1P\ud800', f'P{MPN}')` with a product `mpn=MPN` | Resolves to that product | Never raises |
| NUL / surrogate free-text scan | `'\x00'*4096`, `'\ud800abc'` | `product is None`, hits `== ()`, ZERO sessions; `search_products` is called and refuses the text before building a pattern | Never raises |
| Bare wildcards as part numbers | `_envelope('P%', '1P_')` with the `RES 10K 0805 1%` fixture | `product is None`; hits contain only rows whose searched text literally contains the needle — never the whole catalog | Never raises |
| No part number at all | `_envelope('Q10', '9D2612')`, `_envelope('1P   ')` | `product is None`, hits `== ()`, zero sessions, zero searches; `scan_search_text` is `''` | No error expected |
| Route agreement, every kind | Any missing scan | `service.search_products(service.scan_search_text(resolution))` returns exactly `resolution.free_text_hits`, before and after `_scan_url_value('q', …)` | No error expected |

</intent-contract>

## Code Map

- `app/mariadb_catalog_service.py` -- `resolve_scan` `:2134`, the `raw` guard `:2372`, `internal` arm `:2376`, `gtin` arm `:2387`, `ecia` arm `:2409-2521` (candidates `:2434`, `_matches` `:2446`, `identifier_match` `:2490`, the union query `:2508`, `fallthrough_text` `:2521`), shared tail `:2529-2541`. `search_products` `:1900` — AD-17 entrypoint, guards its own query `:2088`, returns `[]` before opening a session. `sql_text.is_storable_text` imported already.
- `app/main/routes.py` -- `_scan_search_text` `:1979` (the duplicate to delete), `_scan_url_value` `:2015` (its "never reaches the search arm" claim expires), `_scan_destination` `:2272` (needs the service), `api_scan` `:2394-2395` (has `_get_catalog_service()`).
- `app/models.py`, `app/utils/ecia.py`, `app/utils/scan_router.py`, `app/utils/sql_text.py` -- **read-only.** No shape, grammar or guard-implementation change.
- `tests/unit/test_scan_resolution.py` -- `_envelope` `:80`, `_spy_on_search` `:208`, `_count_sessions` `:636`, `TestEciaResolution` `:654`. To invert: `:920`, `:945`, `:1008`. To update: `:891` (miss now searches both), `:1035` (docstring), `:1107` (per-vector hits), `:1142` (docstring + a DW-80 row), `:1593` and `:1630` (assert zero SESSIONS, not zero search calls).
- `tests/unit/test_scan_routes.py` -- `TestSearchTextAgreesWithTheResolver` `:565` and its `_agree` `:578` (call the service method), `:626`, `:635`. `TestEciaPrefillEdgeCases` `:1135` and `:465`/`:484` are expected to stay green.
- `tests/integration/test_identifier_collation.py:177`, `tests/e2e/test_scan_routing.py:156` -- single-candidate / no-match paths, expected green.

## Tasks & Acceptance

**Execution:**
- [x] `app/mariadb_catalog_service.py` -- add a module-level `_ecia_candidates(classification)` returning the trimmed, non-blank, storable, de-duplicated `1P`-then-`P` list, so the candidate rule has one home; rewrite the `ecia` arm to walk it with one query per candidate taking the first exactly-one match; add `_ecia_fallthrough(candidates) -> (text, hits)` implementing first-non-empty; add public `scan_search_text(resolution)` covering all four arms and short-circuiting on `resolution.free_text_hits` being empty or one candidate remaining; have `resolve_scan` use the same helpers for its own tail. Rationale: the per-candidate rule and the searched-text rule each exist exactly once.
- [x] `app/mariadb_catalog_service.py` -- delete the blanket `raw` guard and guard each arm's lookup binding instead. Rationale: DW-80 — an unstorable character in a record the arm never queries must not suppress a clean lookup.
- [x] `app/mariadb_catalog_service.py` -- rewrite the `resolve_scan` docstring: the `ecia` bullet, the three numbered consequences (replaced by what the arm now does and by the first-unambiguous-answer rule, including the ambiguous-then-unique case), the session/query-count paragraph (per candidate; at most two lookups and two searches), and the guard comment.
- [x] `app/main/routes.py` -- delete `_scan_search_text`, pass the service into `_scan_destination`, and build `q` from `service.scan_search_text(resolution)`; correct `_scan_url_value`'s reasoning about unstorable text while keeping its conclusion (a `search` outcome implies storable `q`). Rationale: one home for the rule, and the route can no longer derive it purely.
- [x] `tests/unit/test_scan_resolution.py` -- invert the three ledger pins under names describing the new outcome, keeping their fixtures and control cases; update the miss/session/hostile tests per the Code Map; add the matrix rows not yet covered (ambiguous-then-unique, unstorable candidate beside a clean one, DW-80's `K\ud800` and `K\x00` envelopes, two-candidate total miss, `scan_search_text` per arm).
- [x] `tests/unit/test_scan_routes.py` -- point `_agree` and the two ECIA cases at `service.scan_search_text(resolution)`; keep the end-to-end `hit_count`-equals-the-page assertion.

**Acceptance Criteria:**
- Given the pre-change catalog and any envelope that resolved to a product, when this ships, then it resolves to the SAME product, and no scan of any kind loses an ANSWER: hits are only ever added, except where a hit list is superseded by a landing on a product it contained. (That exception is the matrix's first row and is the intended rule, not a regression — DW-78 previously returned `free_text_hits=[A]` and now returns `product=A, free_text_hits=()`, which is strictly more of an answer, not less.)
- Given `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests`, when it runs, then it is green with no test failing for a reason this spec does not name.
- Given `git status --short`, when this ships, then nothing under `app/templates/`, `app/static/`, `migrations/` or `docs/images/` changed, so no screenshot goes stale and `nox -s e2e` is not required.
- Given `grep -n '_scan_search_text' app/`, when this ships, then there is no match — the duplicate is gone rather than re-copied.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass

- intent_gap: 0
- bad_spec: 0
- patch: 13: (high 0, medium 3, low 10)
- defer: 2: (high 0, medium 1, low 1)
- reject: 2
- addressed_findings:
  - `[medium]` `[patch]` The route re-derived the searched text by re-running the fallthrough, costing up to two extra bounded `LIKE` searches on an unauthenticated `@csrf.exempt` endpoint whose docstring already calls it a denial-of-service shape — `POST /api/scan`'s worst case had gone from two sessions to six. One query always settles it, because the hits are known non-empty: if a candidate's search finds anything it is the winner by the first-non-empty rule, and if every candidate but the last finds nothing the winner can only be the last. `scan_search_text` now loops `candidates[:-1]`, so the two-candidate case costs exactly one query and the route ceiling is five, pinned by a new test. The residual the reviewers also named — a catalog write landing between `resolve_scan` and this call can flip which candidate wins, so `q` could name a candidate other than the one `hit_count` came from — is now stated in the method rather than left implicit; it is a narrower flavour of the staleness that already exists between `hit_count` and the page the browser later renders, and removing it means carrying the value instead of re-deriving it, which changes the shape `<intent-contract>` prescribes. Deferred, below.
  - `[medium]` `[patch]` A newly flaky assertion. `test_a_miss_falls_through_searching_the_candidates_in_order` asserted `calls == ['ABC', '12345']` over `ECIA_FULL`, which holds only while `search_products('ABC')` finds nothing — but the `product` fixture's generated ten-character Crockford base-32 `internal_id` can contain `ABC`, and is mirrored into an INTERNAL identifier row the search also scans, so the walk would stop at the first candidate roughly once in four thousand runs. The old assertion (`calls == ['ABC']`) was insensitive to the collision, and the module's own vector-choice comment states exactly this standard. Demonstrated by pinning a colliding id, then re-pointed at the deliberately hyphenated `MPN`/`CUSTOMER_MPN` constants, which are immune under the same pin.
  - `[medium]` `[patch]` The second-candidate win — the entire reason the searched-text rule moved into the service — had no coverage at the route level. `TestSearchTextAgreesWithTheResolver`'s only ECIA vector was a first-candidate win, the one ECIA shape the deleted pure duplicate could already compute, so nothing walked the new behavior through the shipped `_scan_url_value('q', …)` transform or through `POST /api/scan`. Added both: an `_agree` vector where only the second candidate finds anything, and an end-to-end case asserting the rendered `/products/search` page shows exactly the `hit_count` the endpoint reported. Mutation-tested — making `scan_search_text` always answer `candidates[0]` reddens both.
  - `[low]` `[patch]` The candidate de-duplication was case-SENSITIVE while both its consumers fold ASCII case, so the case it exists to eliminate survived it: `1PABC-9` beside `Pabc-9` produced two candidates, two lookups and two searches for an answer the first could only repeat. The dedupe key is now `value.lower() if value.isascii() else value`. The `isascii()` guard is load-bearing rather than defensive: Python's `str.lower()` is full-Unicode while SQLite's `LOWER()` is ASCII-only, so merging two candidates differing only in NON-ASCII case would drop a lookup the byte-identical `column = value` disjunct can still satisfy. Both halves are now pinned and mutation-tested — an exact dedupe reddens the folded-repeat session count, an unconditional fold reddens the `WüRTH-1`/`WÜRTH-1` case, and each mutation reddens exactly one test.
  - `[low]` `[patch]` `scan_search_text` claimed to be "the SINGLE implementation of the per-arm rule" while `resolve_scan` independently derived the identical text for `internal`, `gtin` and `free_text` — the duplicate had moved from cross-module to intra-module rather than being removed, which is not what the Always clause asks for. A module-level `_fallthrough_text(classification)` now covers those three arms and both callers delegate to it; the ECIA arm is excluded by construction, its text being per candidate.
  - `[low]` `[patch]` Both new per-arm storability guards are unreachable: `gs1.decode` returns None unless every data-field character is printable ASCII, so an `internal` scan's `normalized_value` is storable by construction, as a `gtin` key's fourteen digits already were. The `gtin` comment said so; the `internal` one implied its guard could fire. Both guards kept — the spec prescribes them and they make "every arm guards what it binds" checkable by reading the branch rather than by reasoning about the classifier — but neither now claims to be load-bearing.
  - `[low]` `[patch]` The two relocated-guard tests were re-pinned from `calls == []` to `sessions == []`, which the PRE-change blanket `raw` guard also satisfied, so they passed identically against both implementations and pinned nothing this change did — while their docstrings explained at length that `search_products` is now called, the one fact that distinguishes them. Both now assert the search was called with the text the arm binds AND that no session opened, so the guard relocation is pinned on the `free_text` arm and not only on the two ECIA rows.
  - `[low]` `[patch]` No test covered two candidates where the FIRST search wins, so a regression to searching every candidate, or to last-one-wins, would have left the suite green. Added, asserting one search on each side.
  - `[low]` `[patch]` The route-level session ceiling the `api_scan` docstring states was unpinned — the resolver-side four is asserted, but the route number is the one that grew. Pinned at five.
  - `[low]` `[patch]` `scan_search_text`'s opening line and `TestScanSearchText`'s class docstring stated the round trip (`search_products(text)` reproduces `free_text_hits`) as a universal. It is false for a resolution that LANDED, whose hits are `()` while the text still finds the product — which is why one test in that class quietly exempts itself from the class's own property. Both statements scoped to a resolution that produced no product, with what a landing returns and why the route never asks it stated.
  - `[low]` `[patch]` `_scan_url_value`'s rewritten control-character rationale was wrong on both halves: for an `ecia` outcome `q` is a candidate part number, which by the format-06 grammar cannot contain a separator, and for a `free_text` outcome it is the AIM-stripped raw scan, which can carry any storable control character and none of them an ECIA separator. The conclusion it defends is correct and verified — non-empty hits mean `search_products` accepted the text, so a `search` outcome implies a storable `q` — so the conclusion stayed and the reasoning was replaced.
  - `[low]` `[patch]` `_ecia_fallthrough`'s cost paragraph reasoned about inputs its only supported caller cannot produce: `_ecia_candidates` has already removed blank and unstorable values, so only the over-long short-circuit survives. Tightened.
  - `[low]` `[patch]` Acceptance Criterion 1 ("no scan of any kind loses hits it previously returned") contradicted the I/O matrix's own first row, where the DW-78 scenario stops returning `free_text_hits=[A]` and starts returning `product=A`. The matrix is the intended rule and the code follows it; the AC now says no scan loses an ANSWER, and names the landing-supersedes-hits case as the exception.
  - `[medium]` `[defer]` Carry the searched text from `resolve_scan` to the router instead of re-deriving it. AD-15 freezes the `ScanResolution` dataclass, not `CatalogService`'s method set, so a companion method returning `(resolution, text)` would remove the last extra query and the staleness window above without a fourth field and without a second copy of the rule. Not taken here because `<intent-contract>` prescribes `scan_search_text(resolution)` called by `_scan_destination`, and changing that shape is a contract decision. Recorded for the orchestrator; this spec does not edit the ledger.
  - `[low]` `[defer]` `_ecia_prefill` maps `1P` to `mpn` unconditionally, so an envelope whose `1P` is unstorable and whose `P` is the usable part number pre-fills `mpn` with a replacement character while offering the real number as `vendor_sku`. Pre-existing — Story 4.5 owns that mapping and the blanket guard used to make the whole envelope answer nothing — but this change makes it reachable on the `product` outcome as well as `create`. Recorded for the orchestrator.
  - Rejected, two: that the arm's per-query sessions let the unambiguity verdict and the hit list come from different database snapshots (the lookup and the fallthrough have never shared a session, and the module documents scan resolution as read-only and un-transacted — the change adds queries, not a new class of skew); and the meta-finding that the added prose outruns what is verified (its concrete instances are the four docstring patches above and are fixed individually, and the same finding was rejected in all three of Story 4.4's review passes).

### 2026-07-27 — Review pass

- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 1, low 4)
- defer: 2: (high 0, medium 1, low 1)
- reject: 9
- addressed_findings:
  - `[medium]` `[patch]` `api_scan`'s docstring told a maintainer the wrong thing about live security debt: it said the two ledger entries aimed at this endpoint — the CSRF exemption and rate limiting — "stay open and now have the real cost written against them", while DW-14 and DW-63 are both `status: done 2026-07-26`, closed by human decision. Nothing is holding the new five-session ceiling for anyone, and DW-14's own summary still describes the two-session cost this change raised. Corrected to name both entries by number, state that they are closed, and say plainly that the larger number is written in this docstring and nowhere else. The 111-character line spliced into that paragraph was reflowed in the same edit.
  - `[low]` `[patch]` `scan_search_text` claimed the text it returns for a resolution that LANDED "will typically still FIND that product". False for the shape this change created: a landing on the SECOND candidate still reports `candidates[0]`, whose search can be empty — verified for `1PSUP-99999` + `PRC0805-10K` against a product stored `mpn='RC0805-10K'`. No functional impact (the route only builds a `q` on the `search` outcome, which has no product), so the scope paragraph now states both outcomes instead of predicting the friendly one.
  - `[low]` `[patch]` `_scan_url_value`'s control-character rationale, itself rewritten by the previous pass, still carried a false clause: the AIM-stripped raw scan is said to carry "any storable control character a scanner emits and none of which is an ECIA separator", but text that failed to parse as an envelope is searched verbatim, so a free-text scan carrying a GS puts that GS straight into `q`. The conclusion the paragraph defends is unaffected — only NUL and unpaired surrogates are excluded, and a `q` exists only on a `search` outcome, so a `q` is storable by construction — so the conclusion stayed and the clause was replaced with one that does not depend on which controls turn up.
  - `[low]` `[patch]` The `scan_router` import comment still justified itself by a use this change deleted ("`strip_aim_prefix`, to re-derive the text a fallthrough search ran on"). Its three surviving call sites feed the `description` pre-fill and the `internal` banner. Re-stated, with the pointer to `scan_search_text` as the new home of the fallthrough-text rule.
  - `[low]` `[patch]` `_fallthrough_text` documented ECIA as "not a legal argument" and then handled it anyway: with no guard, an ECIA classification falls to `strip_aim_prefix(raw)` and returns the whole envelope, separators included — the one text this arm must never search, and indistinguishable at the call site from a legitimate free-text fallthrough. Both callers branch on `kind` first so nothing reaches it today; the documented contract is now enforced with a `ValueError`, matching how every comparable seam in this module (`search_products`' type guards, `ScanClassification.__post_init__`) treats an illegal argument. Pinned by a new test.
  - `[medium]` `[defer]` DW-173 — `_ecia_fallthrough` computes the winning candidate and `resolve_scan` discards it, so `scan_search_text` re-establishes it with another search: a fifth session on `POST /api/scan` plus a TOCTOU window in which a concurrent write flips which candidate `q` names. Closing it means carrying the text out of `resolve_scan`, which is the shape `<intent-contract>` and AD-15 prescribe. The route already holds the same service instance, so the coupling that would make it possible is paid for.
  - `[low]` `[defer]` DW-174 — `_ecia_prefill` is a fourth copy of the `1P`-then-`P` rule that diverges from `_ecia_candidates` (no storability filter, no ASCII case-fold dedupe): an unstorable `1P` pre-fills `mpn` with a replacement character while the matched part number is filed under `vendor_sku`, and an envelope whose only part number is unstorable opens the create form with `mpn='?'` and no `description` at all, which is the loss FR40 forbids. The second shape is fully pre-existing; the first is pre-existing code newly reachable on the `product` outcome. Fixing the mapping is Story 4.5 scope this spec's boundaries do not grant.
  - Rejected, nine. Four are the spec's own decisions restated as defects: that a `1P` naming product A beside a `P` naming a different product B now lands silently on A (the intent contract says first-unambiguous-wins and the `resolve_scan` docstring names this exact case one sentence before the tightening proof); that the `internal` and `gtin` guards are permanently-dead branches (prescribed by the Always clause and already reasoned about last pass); that the `free_text` arm now leans on `search_products`' internal guard (the Always clause forbids re-guarding it); and that the endpoint's cost grew to five sessions (acknowledged in the spec, patched into the docstring above, and deferred as DW-173). Five are not defects: `_ecia_match`'s documented caller-responsibility precondition (private, one caller, and unlike `_fallthrough_text` its silent answer is a query on a blank string rather than a search of the raw envelope); the claim that reporting `candidates[0]` when NO candidate finds anything sends the operator to an empty results page while `hit_count` promised results (`hit_count` is zero on that path, and the route builds no `q` at all); that pinning the session ceiling at exactly five "defends the regression" (the exact number is deliberately coupled to the docstring claim, so the two must move together); and two test-style preferences — a three-vector `for` loop instead of `parametrize`, which this file uses both of, and `_round_trips` degenerating to `[] == []` where hits are empty.

## Design Notes

**Why first-non-empty and not a merged hit list.** DW-79 proposes "searching every candidate and merging the hit lists". A merge cannot be reproduced from a single `q`, and `ScanResolution` may not grow a fourth field (AD-15), so `/products/search?q=…` would show a different set than `hit_count` promised — the exact failure `TestSearchTextAgreesWithTheResolver` exists to prevent. First-non-empty closes DW-79 and DW-82 while keeping `free_text_hits == search_products(one text)`.

**Why the walk is monotone.** Under the union query the arm landed only when exactly one product matched EITHER candidate; then each candidate matched that product or nothing, so the per-candidate walk lands on the same product. New landings occur only where the union previously answered none. Likewise the fallthrough returns candidate 0's hits whenever they are non-empty, so hits are only ever added.

**Why the route calls the service.** The winning candidate is a function of the database, so the route's pure copy cannot compute it. Rather than re-copying the rule with a service argument, the rule moves into the service and the route calls it — the direction this repo has repeatedly chosen (one LIKE escaper, one format-06 grammar). Cost: for a multi-candidate ECIA envelope routed to `search`, up to two extra bounded `LIKE` searches. `api_scan`'s cost note must be updated to say so.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green; record the count against the pre-change baseline and account for every delta.
- `git status --short` -- expected: `app/mariadb_catalog_service.py`, `app/main/routes.py`, `tests/unit/test_scan_resolution.py`, `tests/unit/test_scan_routes.py`, this spec. Anything under `app/templates/`, `app/static/`, `migrations/` or `docs/images/` means a boundary was crossed.
- `grep -rn '_scan_search_text' app/ tests/` -- expected: no output.
- `grep -rl "down_revision = '68707d1f48bf'" migrations/versions/` -- expected: no output (AD-14, no schema change).
- Mutation check -- reverting the per-candidate walk to the union query must redden the three inverted pins; restoring the blanket `raw` guard must redden the DW-80 rows.

**Manual checks (if no CLI):**
- `nox -s e2e` is not required if `git status --short` shows no route-visible template/JS change; the JSON contract of `POST /api/scan` is unchanged in shape.



## Auto Run Result

Status: done

**Summary.** Closes DW-78, DW-79, DW-80 and DW-82. `resolve_scan`'s ECIA arm no longer ORs both candidate part numbers into one query and counts rows over the union: it asks each candidate on its own, in `1P`-then-`P` order, and takes the first UNAMBIGUOUS answer; on no product it searches the candidates in order and takes the first non-empty hit list. The storability guard moved off the whole envelope and onto the text each arm actually binds. This deliberately renegotiates Story 4.4's frozen "one query, one session" and "the fallthrough text is the first candidate", strictly in the tightening direction — every scan that resolved to a product before resolves to the same product now, no scan loses hits, and one FR36 dead end closes.

This run is a follow-up review pass on an already-complete implementation (the prior pass recommended one). It found no intent gap and no spec defect, so nothing was re-derived; five patches were applied and two findings deferred.

**Files changed since `911dd61` (four code files):**
- `app/mariadb_catalog_service.py` — `_ecia_candidates` (the one home for the candidate rule: trimmed, non-blank, storable, ASCII-case-folded-deduplicated), `_ecia_match` (one candidate, one query, one session), `_ecia_fallthrough` (first non-empty hit list), `_fallthrough_text` (the three pure arms), and public `scan_search_text(resolution)`. The blanket `is_storable_text(raw)` early return is gone, per-arm guards replace it, and the ECIA arm is a walk.
- `app/main/routes.py` — the pure duplicate `_scan_search_text` deleted; `_scan_destination(resolution, service)` builds `q` from `service.scan_search_text(resolution)`.
- `tests/unit/test_scan_resolution.py` — the three ledger pins inverted under names describing the new outcome, keeping their fixtures and control cases; new `TestScanSearchText`; new coverage for the DW-80 envelopes, an unstorable candidate beside a clean one, ambiguous-then-unique, a two-candidate total miss, first-search-wins, and both halves of the ASCII-only dedupe fold.
- `tests/unit/test_scan_routes.py` — `TestSearchTextAgreesWithTheResolver` points at the service method and gains a second-candidate-win vector; end-to-end and session-ceiling cases.

**This pass's changes** (all documentation or defensive, no behavior change on any reachable path):
- `app/main/routes.py` — `api_scan`'s claim that the two endpoint-security ledger entries "stay open" corrected (DW-14 and DW-63 are both closed by human decision); `_scan_url_value`'s false clause about ECIA separators replaced; the `scan_router` import comment re-stated after the use it cited was deleted.
- `app/mariadb_catalog_service.py` — `scan_search_text`'s overstated round-trip claim scoped to what actually happens on a second-candidate landing; `_fallthrough_text` now raises `ValueError` on the ECIA classification its docstring already called illegal, instead of silently returning the raw envelope; the deferred-work reference given its DW number.
- `tests/unit/test_scan_resolution.py` — one new test pinning that guard.

**Review findings this pass:** 5 patches applied (0 high, 1 medium, 4 low), 2 deferred (DW-173, DW-174), 9 rejected, 0 intent gaps, 0 spec defects. Two reviewers ran in parallel over the same diff and agreed independently on the `_fallthrough_text` guard, the `_ecia_prefill` divergence and the re-derivation cost.

**Verification performed:**
- `PATH=… venv/bin/nox -s tests` — green: `2841 passed, 427 deselected`, against `2840` before this pass, accounting for the one added test.
- Every patched claim was checked against the code or the ledger before rewriting it, not argued from reading the prose: `_fallthrough_text`'s ECIA path traced to `strip_aim_prefix(raw)`; `scan_search_text`'s ECIA branch traced to `candidates[0]` whenever `free_text_hits` is empty; DW-14 and DW-63 read out of the ledger as `status: done 2026-07-26`; the `scan_router` call sites enumerated (`description` pre-fill and `internal` banner only).
- `git status --short` — the four code/test files plus the spec and the ledger. Nothing under `app/templates/`, `app/static/`, `migrations/` or `docs/images/`, so no screenshot goes stale and `nox -s e2e` was not required.

**Follow-up review recommendation: false.** This pass changed no reachable behavior: four of the five patches are docstring or comment corrections, and the fifth is a guard on a path both callers already exclude. The volume, breadth and consequence that justified the previous pass's recommendation are not present here.

**Residual risks (unchanged by this pass).** The lookup remains verified on SQLite alone; no test at any level runs `CatalogService` against MariaDB, where `utf8mb4_unicode_ci` makes the equality accent-insensitive and PAD SPACE, so this arm can pick a landing in production the unit suite cannot reproduce. `POST /api/scan`'s worst case is five sessions on an unauthenticated, `@csrf.exempt`, unthrottled endpoint whose two ledger entries were closed by human decision at the two-session cost — the larger number now lives only in the endpoint's docstring and in DW-173. A `1P` and a `P` that name two different real products resolve silently to the `1P` product, which is the intended rule but is a coin flip the operator is not shown. And whether a keyboard wedge can deliver RS/GS at all is still unanswered, so the whole ECIA path remains unverified against real hardware.
