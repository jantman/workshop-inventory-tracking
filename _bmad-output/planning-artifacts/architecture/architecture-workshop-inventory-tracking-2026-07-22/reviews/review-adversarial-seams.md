---
title: Adversarial Seam Review — Architecture Spine
subject: ARCHITECTURE-SPINE.md (Product Catalog & Purchase Tracking)
reviewer: adversarial architecture reviewer
method: construct pairs of one-level-down units (epics/stories) that each obey EVERY AD yet build incompatibly
created: 2026-07-22
status: draft
---

# Adversarial Seam Review — Architecture Spine

**Verdict:** The spine is strong on layering and derived-state discipline, but it leaves the *scan seam* (classify-vs-resolve boundary + typed-classification shape), the *AI-96/`WIT` payload grammar* (encoder ↔ decoder), and the *equivalence-group stock semantics* under-constrained enough that two conforming epics build genuinely incompatible code or silently corrupt data. 2 CRITICAL, 3 HIGH, 5 MEDIUM.

Method: for each finding I name two concrete units one level down (epics or their stories per the addendum §D decomposition), show that **both** obey every relevant AD to the letter, show the incompatible outcome, and propose the new/tightened AD or convention that closes the hole. Severity = how badly the divergence corrupts data or breaks the build.

---

## CRITICAL

### C-1 — `scan_router` is required to be a pure classifier (AD-4) *and* to perform DB lookups with match-fallthrough (AD-5). The classify-vs-resolve boundary and the "typed classification" shape are both unfixed.

**The two units.**
- **Epic 4, story 4.2 "Routing by structure"** implements `app/utils/scan_router.py`. Per **AD-4** it is a *module-level pure function with no Flask/DB imports*, single source of truth, exhaustively unit-tested. So it can only return a **structural classification**: e.g. `Classification(kind="internal", token_payload="…")`, `kind="gtin", normalized="0001…"`, `kind="ecia", fields={…}`, `kind="free_text", raw="…"`. It cannot know whether a product matches, because that needs the DB.
- **Epic 4, story 4.6 "Unknown scan path" + Epic 7, story 4.7 "Duplicate prevention on receipt" + Epic 9, story 9.2 "self-sufficient scan-result view"** consume the router's output. **AD-5** literally says the router "implements the FR36 precedence … (1) … → internal-ID lookup … (3) … valid GTIN check digit → normalize + GTIN lookup, **falling through to free-text on no match**." A "lookup" and "fall through on no match" require the DB. So a conforming Epic 4 could just as legitimately build `scan_router.route(raw, service)` that **returns a resolved product-or-None**, because AD-5 tells it to.

**How both obey the ADs.** AD-4 says pure/no-DB; AD-5 says the router does the lookup and the no-match fallthrough. These two ADs point at the same module and contradict each other, so *each* reading is fully AD-compliant. Neither epic is wrong.

**The incompatible outcome.**
- If 4.2 builds the **pure classifier** (honoring AD-4), then the "fall through to free-text on no match" of AD-5/FR36 lives in the *service*, and the returned type is `Classification` (structure only). Story 4.6/4.7/9.2 must each re-implement resolution.
- If 4.2 builds the **resolving router** (honoring AD-5's "lookup"), it must import the service/session — violating AD-4 — and returns a `ScanResult` (structure **plus** matched product **plus** the free-text fallback rows). 
- The two return types are structurally different objects. Whichever epic ships first freezes a shape; the other's consumers (the scan endpoint, the receipt duplicate-prevention flow, the handheld view, and — see C-2 — the capture path) break against it. The "typed classification" is named but never defined, so even two *classifier* implementations disagree on fields (does `ecia` carry a dict keyed by `P/1P/Q/K/1K/9D`? does `gtin` carry the *normalized* or *as-scanned* value? is there a `product` field or not?).

**Proposed AD (new AD-15 — "Scan seam contract").**
> Split the seam explicitly. `app/utils/scan_router.py` is **pure and classification-only** (AD-4 wins): it returns a single frozen `ScanClassification` value object (defined in `app/models.py`) with fields `kind ∈ {internal, ecia, gtin, free_text}`, `normalized_value` (14-digit for `gtin`, `WIT…`-stripped id for `internal`, else `None`), `ecia_fields: dict|None` (keys exactly `P,1P,Q,K,1K,9D,10D`), and `raw`. **Resolution and the FR36 no-match free-text fallthrough happen in `mariadb_catalog_service.resolve_scan()`**, which calls the router then the DB and returns a frozen `ScanResolution(classification, product|None, free_text_hits)`. Reword AD-5 to say the router *owns precedence/classification*, the *service owns lookup + fallthrough*. All scan consumers (Epics 4, 7, 9) depend only on these two named shapes.

**Severity: CRITICAL** — directly contradictory ADs over one module; whichever way it resolves, the un-chosen consumers are built against the wrong shape and must be reworked. It is the highest-traffic seam in the feature (every scan surface).

---

### C-2 — Capture de-dup (AD-9) indexes a reused Amazon ASIN as a globally-UNIQUE identifier and matches on it — silently over-merging two genuinely different products, the exact scenario the glossary says ASIN-as-identity must prevent.

**The two units.**
- **Epic 2, story 2.1 "Identifier entity"** enforces **AD-7 / FR8**: `ProductIdentifier(type, value)` is *globally UNIQUE*. An `ASIN` value can exist on **at most one** product.
- **Epic 7, story 7.2 "Match to existing product"** implements **AD-9 / FR50**: on capture it "attaches to an existing Product when the submitted Vendor SKU matches an existing `ProductIdentifier` … on first sight of an Amazon ASIN it indexes the ASIN as an `ASIN` identifier so later captures match."

**How both obey the ADs.** 2.1 stores `(ASIN, "B08MFBQ8LV")` UNIQUE. 7.2 later sees the same ASIN string, finds the existing `ASIN` identifier, and attaches the new Purchase to that product. Both are textbook AD-compliant.

**The incompatible outcome.** The Glossary is explicit: **"ASIN … Amazon reuses ASINs"** — that is the stated reason ASIN is *not* product identity. But AD-9 turns the ASIN into an identity key anyway (indexes it + matches on it). When Amazon reuses `B08MFBQ8LV` for a *different physical part*, capture-2 matches capture-1's product and **silently files a purchase of Part-B under Part-A**, merging two products' price/label history — a durable, invisible data-corruption exactly of the class NFR7 exists to prevent. Conversely, if the operator has manually created Part-B and *already* attached the (now-reused) ASIN, the UNIQUE constraint (2.1) makes capture-2's indexing raise an IntegrityError instead — so the same scenario either corrupts or hard-fails depending on order of operations. The spine never says which, so Epic 2 and Epic 7 can each be "right" and still collide.

**Proposed AD (tighten AD-9).**
> State the de-dup match precedence and scope precisely, and cap ASIN trust: capture matches **(a)** an existing `ProductIdentifier` of a *non-reusable* type, then **(b)** a prior `purchases.vendor_sku` **scoped to the same vendor**. `ASIN` is indexed for *convenience lookup* but an ASIN match must be **vendor-scoped and treated as a suggestion, not an automatic merge** past a confidence check (e.g. manufacturer/MPN agreement), or must require explicit operator confirmation when it would merge products with differing manufacturer/MPN. Define the behavior when indexing an ASIN that already exists on another product (reject-and-surface, never silently attach). Add `UNIQUE(type,value)` handling as a caught domain error, not an uncaught IntegrityError.

**Severity: CRITICAL** — silent cross-product data corruption of the price/label history that is the feature's whole point (SM-2/SM-3), triggered by a documented Amazon behavior.

---

## HIGH

### H-1 — The AI-96 + `WIT` payload grammar has two owners (`gs1.py` encoder, `scan_router.py` decoder), both are "single source of truth per module" (AD-4), and neither AD says how the config token/AI reaches two *pure* modules identically. FR12c demands one config change flip both.

**The two units.**
- **Epic 6, story 2.4/6.x** uses `app/utils/gs1.py` to **encode** the label payload: `FNC1 + AI 96 + "WIT" + internal_id` (**AD-8**).
- **Epic 4, story 4.2/2.5** uses `app/utils/scan_router.py` to **recognize** rule-1 scans: "GS1 AI 96 + *configured token* → internal-ID lookup" (**AD-5**), i.e. it must parse `WIT`-prefixed AI-96 payloads.

**How both obey the ADs.** AD-4 declares `gs1.py` *and* `scan_router.py` as **separate** pure modules, each "its own single source of truth." AD-8 says the AI number and token are "configuration values, not literals." So Epic 6 legitimately reads config → passes `ai="96", token="WIT"` into `gs1.encode()`; Epic 4 legitimately implements AI-96/`WIT` recognition *inside `scan_router.py`* (it's the classifier — AD-5), reading its own copy of the config. Both obey AD-4's single-source rule *for their own module* and AD-8's no-literals rule.

**The incompatible outcome.** Two modules now independently know the AI-96/`WIT`/FNC1 grammar. **FR12c** requires: "Changing config changes **both** the encoder output and the router's recognition, with no code edit." But (a) pure functions per AD-4 *cannot read `app.config`*, so the config must be threaded in as arguments — and the spine never says a single well-known config key feeds both; Epic 6 could read `LABEL_INTERNAL_TOKEN` while Epic 4 reads `SCAN_INTERNAL_TOKEN`, or Epic 4 defaults the token as a function parameter default `token="WIT"` (a literal, quietly violating FR12c while looking AD-compliant). (b) FNC1-transmission tolerance (FR37a: GS `0x1D` / substitute / stripped) is a *decode-side* grammar detail with no encode-side counterpart, so the two modules' notion of "the payload" can drift (encoder emits real FNC1; decoder only tolerates stripped). Result: a label Epic 6 prints does not round-trip through Epic 4's router after a config change — silently, and only the Q1 spike would catch it, hardware-side.

**Proposed AD (new AD-16 — "One payload grammar, one config source").**
> The AI-96/`WIT`/FNC1 element-string grammar is single-sourced in `app/utils/gs1.py`, exposing both `encode(internal_id, *, ai, token)` **and** `decode(raw) -> InternalPayload|None` (the latter absorbing FR37a FNC1 tolerance). `scan_router.py` **delegates** rule-1 recognition to `gs1.decode()` rather than re-implementing it. The AI number and token are read from **one** named config pair (e.g. `config["GS1_INTERNAL_AI"]`, `config["GS1_INTERNAL_TOKEN"]`) **in the service layer** and passed explicitly into both `gs1.encode` and the router; pure functions take them as required arguments with **no literal defaults**. State this so FR12c is mechanically guaranteed.

**Severity: HIGH** — breaks the core identification loop (print → scan) after any config change or any drift between two hand-rolled grammars; failure is invisible until a physical scan fails.

---

### H-2 — FR64's "recent receipt on any group member suppresses the others" is a *third* derived signal the spine never sanctions (AD-6 defines only Effective Low and On Order), and it collides with FR33, which clears only the *purchased* product's manual status.

**The two units.**
- **Epic 7/5, story 5.6 "Receipt clears manual override"** implements **AD-6 / FR33**: setting a received date "clears **the associated Product's** manual `low`/`out` to `ok`." Scope: the one product on the purchase.
- **Epic 10, story 10.3 "Equivalence in reorder view"** implements **AD-10 / FR64**: "On Order **or a recent receipt on any member** marks the whole group, so an inbound order on one relabel **suppresses the reorder signal for the others**."

**How both obey the ADs.** AD-6 says receipt writes only the purchased product's stored status and forbids writing derived state. AD-10 says On-Order and reorder-collapse "operate across all group members." Epic 7 clears product A's manual `low`; Epic 10 collapses the group and wants A's receipt to satisfy B. Both are literal to their ADs.

**The incompatible outcome.** Group member B still holds a stored manual `low` (FR33 never touched it — it's not the purchased product). At read, B is Effective Low (AD-6 formula: `stored ∈ {low,out}` → true), so the collapsed group line is Effective Low — **contradicting FR64's promise that a recent receipt on A suppresses B's reorder signal.** To honor FR64, Epic 10 would have to either (a) write B's stored status (violating AD-6's "receipt clears only the purchased product" and "never writes derived state"), or (b) compute a **"recent receipt"** group signal that AD-6 does not define, does not bound ("recent" = ?), and does not locate. Epic 5 (which owns derived signals) and Epic 10 (which owns the group) will each fill this gap differently — one shows the group as still-needing-reorder, the other as satisfied.

**Proposed AD (tighten AD-6 + AD-10).**
> Enumerate the derived signals exhaustively and make them group-aware in one place. Add a third read-time derived signal **"Recently Received"** = EXISTS a purchase on the product *or any group sibling* with `received_date ≥ today − N days` (N a named config value), computed in the service. Define the **group reorder line** as: Effective-Low iff *every* member is Effective-Low **and** no member is On Order **and** no member is Recently Received (i.e., a receipt/inbound on any member suppresses the whole group). State that FR33's manual-status clear remains scoped to the purchased product only, and that group suppression is achieved by the derived signal, **never** by writing sibling stored status. Bind Epics 5, 7, 10 to this single definition.

**Severity: HIGH** — the reorder view (the feature's stated UJ-5 payoff) either double-orders or hides real shortages; two epics own overlapping, unspecified logic.

---

### H-3 — Two dedup match paths in AD-9 use *different uniqueness scopes* (global identifier vs vendor-scoped SKU), so the same submitted SKU string attaches to different products depending on which path an epic implements first.

**The two units.**
- **Epic 7, story 7.2** path (a): match the submitted Vendor SKU against an existing **`ProductIdentifier`** — which per AD-7 is **globally** unique/unscoped.
- **Epic 7, story 7.2** path (b): match against a prior **`purchases.vendor_sku`** — which AD-9 explicitly qualifies as **"(vendor-scoped)."**

**How both obey the ADs.** AD-9 lists both paths with an `OR`. AD-7 makes the identifier path global. Both are honored simultaneously — and that's the problem: the *same value* ("603-1234", a distributor customer part number used by two different vendors) matches globally via path (a) but is correctly partitioned by vendor via path (b). The `OR` means path (a) can fire across vendors and attach the purchase to the wrong vendor's product, even though path (b) was designed to prevent exactly that.

**The incompatible outcome.** Capture of a DigiKey SKU that collides with a Mouser `VENDOR_SKU` identifier attaches DigiKey's purchase to the Mouser product. Whether it does depends purely on whether that string happened to be promoted to a `ProductIdentifier` — a non-obvious, order-dependent divergence between how Epic 2 (identifiers) and Epic 7 (capture) treat the same value.

**Proposed AD (tighten AD-9).**
> Make both dedup paths **vendor-scoped for vendor-namespaced identifier types** (`VENDOR_SKU`, `ASIN`, `FNSKU`), and reserve global-unscoped matching for globally-unique types (`GTIN`, `INTERNAL`). State the match precedence order explicitly and the scope per type.

**Severity: HIGH** — cross-vendor mis-attribution of purchases; latent and order-dependent.

---

## MEDIUM

### M-1 — `internal_id` has two candidate writers: Epic 1 (the column/its server default) and Epic 2 (`internal_id.py`). No AD says who writes it or who owns collision-retry against the `UNIQUE` key.

- **Epic 1, story 1.1** creates `products.internal_id` (UK). It could give it a DB/server default or generate it in the create-service.
- **Epic 2, story 2.4** builds `app/utils/internal_id.py` (pure, AD-4) and says "on save, internal_id generated."

Both obey their ADs. But `internal_id.py` is *pure* (AD-4) — it cannot guarantee uniqueness against the DB, and AD-8 only says the value is "generated and authoritative," not *by whom* or *retried how*. If Epic 1 sets a default and Epic 2 also generates, there are two sources for one authoritative business key; if neither owns collision-retry, a rare generator collision surfaces as an uncaught IntegrityError.

**Proposed:** Tighten AD-8: `internal_id.py` produces a *candidate*; **the create-service is the sole writer**, performs the insert, and owns retry-on-`UNIQUE`-collision; Epic 1's column carries **no** generating default. State that the `INTERNAL`-type identifier row is written by the same service step, transactionally, from the same value. **Severity: MEDIUM.**

### M-2 — The JSON error envelope is fixed only as `{success: bool, …}`; the error-detail shape is unspecified, so AD-13's *frozen* result dataclasses in `api_client.py` are built against divergent bodies.

The convention says JSON routes use `{success: bool, …}` and errors are "the dominant route style" (loose). Epic 7's capture endpoint and any other new REST surface (AD-13) can each pick `{success:false, error:"msg"}` vs `{success:false, message:…, code:…}` vs `{success:false, errors:{field:…}}`. AD-13 requires a **frozen result dataclass** per endpoint in the `requests`-only client — but a frozen dataclass cannot absorb two different error shapes. Two conforming epics ship incompatible envelopes; the client's frozen dataclasses can only match one.

**Proposed:** Add to Consistency Conventions a **fixed error envelope**: `{success: false, error: {code: str, message: str, field?: str}}` (or equivalent), applied to every new JSON route, so AD-13's dataclasses are stable across epics. **Severity: MEDIUM.**

### M-3 — `category_path` canonical form (case, separators, leading/trailing slash, prefix-boundary) is unfixed between Epic 3 (create/rename/collision-detect) and Epic 8 (prefix-filter facet).

Category is a materialized-path *string* on `products` (convention), with no `categories` table (Deferred). **Epic 3, story 3.2** must detect a rename that "would collide with an existing sibling" and rewrite all descendants — both require a canonical comparison form. **Epic 8, story 8.2** filters "by Category path prefix." If Epic 3 stores `Electronics/Power/` and Epic 8 prefix-matches `electronics/power` (case, trailing slash, and the `power` vs `power-supplies` boundary problem where a naive `LIKE 'electronics/power%'` also matches `electronics/power-tools`), the facet silently under/over-matches and rename-collision detection disagrees with the filter. Both obey the (silent) convention.

**Proposed:** Convention addendum: define the canonical `category_path` form — lowercase, `/`-separated, no leading/trailing slash — and require prefix matching on a **segment boundary** (`path = X OR path LIKE 'X/%'`). Single-source a `normalize_category_path()` util (AD-4 style) used by Epics 3 and 8. **Severity: MEDIUM.**

### M-4 — The Effective-Low predicate is duplicated: service-side Python (Epic 5) vs SQL WHERE for the faceted filter (Epic 8), with a NULL-threshold edge that the two implementations resolve differently.

**AD-6** gives the formula and says it's "computed at read **in the service**." **Epic 5, story 5.4** implements it in Python. **Epic 8, story 8.2** filters search results "by Effective-Low/Stock Status" — practically a SQL `WHERE` for facet performance. Two encodings of one predicate. The edge: AD-6 says `quantity_on_hand ≤ reorder_threshold`; when `reorder_threshold IS NULL`, Python `qty <= None` raises/ is falsey by guard, while SQL `qty <= NULL` yields NULL(→ excluded) — and a hand-written Python guard may include or exclude the row differently from the SQL. The two views disagree on which products are "low."

**Proposed:** Tighten AD-6: the Effective-Low (and On-Order) predicate is expressed **once** — either a single service method that Epic 8 also calls, or a single SQLAlchemy hybrid expression usable in both `WHERE` and Python — and the `reorder_threshold IS NULL` case is stated explicitly (NULL threshold ⇒ threshold branch is false). Forbid a second hand-written copy. **Severity: MEDIUM.**

### M-5 — `request_key` idempotency: the UNIQUE-constraint owner (Epic 1 schema vs Epic 7 logic) and the *scope* of "the original record" (Purchase only, or the Product it created too) are unspecified.

**AD-9/FR51** requires idempotency on `request_key` but the ER shows it as a plain nullable string with **no `UNIQUE`** stated. **Epic 1, story 1.2** creates the column; **Epic 7, story 7.4** implements idempotency. If Epic 1 omits `UNIQUE(request_key)` and Epic 7 does a check-then-insert, a double-submit (bookmarklet retry) can create two purchases. Worse, capture creates **both** a Product and a Purchase; AD-9 says "the same key returns the original record" (singular) but never says whether a retry after a partial failure (product committed, purchase not) is covered by the same key. Two epics fill this in differently.

**Proposed:** Tighten AD-9: `purchases.request_key` carries a `UNIQUE` constraint (Epic 1 owns it); idempotency is enforced by that constraint + caught IntegrityError (not app-level check-then-insert); and the idempotent unit is the **whole capture transaction** (Product+Purchase created atomically), so a retry returns the same Product URL regardless of where the first attempt failed. **Severity: MEDIUM.**

---

## Severity summary

| Severity | Count | Findings |
| --- | --- | --- |
| CRITICAL | 2 | C-1 (scan classify-vs-resolve + shape), C-2 (ASIN over-merge) |
| HIGH | 3 | H-1 (AI-96/`WIT` grammar + config plumbing), H-2 (group receipt-suppress vs FR33), H-3 (dedup scope mismatch) |
| MEDIUM | 5 | M-1 (internal_id writer), M-2 (error envelope), M-3 (category_path canonical form), M-4 (Effective-Low duplication), M-5 (idempotency constraint/scope) |

## Proposed spine changes (rollup)

- **New AD-15** — Scan seam contract: pure `ScanClassification` from the router; resolution + FR36 fallthrough in the service returning `ScanResolution`; both shapes named in `app/models.py`.
- **New AD-16** — One AI-96/`WIT`/FNC1 grammar in `gs1.py` (encode+decode); `scan_router` delegates; one config-key pair read in the service and passed to both pure functions; no literal defaults.
- **Tighten AD-9** — de-dup match precedence + per-type scope (vendor-scope `VENDOR_SKU`/`ASIN`/`FNSKU`; global only `GTIN`/`INTERNAL`); ASIN match is confirm-not-merge; `UNIQUE(type,value)` and `UNIQUE(request_key)` as caught domain errors; idempotent unit = whole capture transaction.
- **Tighten AD-6 + AD-10** — exhaustive derived-signal list incl. group-aware "Recently Received"; group reorder-line definition; Effective-Low predicate single-sourced incl. NULL-threshold rule; FR33 clear stays product-scoped.
- **Tighten AD-8** — service is sole `internal_id` writer with collision-retry; `internal_id.py` yields a candidate only; no DB default.
- **Conventions** — fixed error-detail envelope; canonical `category_path` form + segment-boundary prefix match via a shared normalizer.

*File: `_bmad-output/planning-artifacts/architecture/architecture-workshop-inventory-tracking-2026-07-22/reviews/review-adversarial-seams.md`*
