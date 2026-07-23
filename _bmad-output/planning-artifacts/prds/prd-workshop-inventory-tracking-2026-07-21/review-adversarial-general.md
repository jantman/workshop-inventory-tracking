# Adversarial Review — Product Catalog & Purchase Tracking PRD

*Cynical/skeptical read of `prd.md` + `addendum.md`, 2026-07-21. Brownfield claims spot-checked against the actual codebase (`app/services/label_printer.py`, `app/main/routes.py`, `app/static/js/field-autocomplete.js`). Severity: CRITICAL (will produce wrong data or a broken core loop) / HIGH (a named use case fails, or a decision is unverified and load-bearing) / MEDIUM (ambiguity or gap that will cost a rework cycle) / LOW (polish, wording, undefined edge).*

Counts: **CRITICAL 3, HIGH 4, MEDIUM 7, LOW 6.**

---

## CRITICAL

### C1 — The single-group equivalence model forces transitivity, which "functionally interchangeable" does not have. (§4.5 FR62, Glossary "Equivalent Product Group", Q8, addendum §C)
`equivalent_group_id` as a nullable FK makes group membership a partition: every product is in exactly zero or one group, and membership is transitively closed. But "functionally interchangeable" is **not** a transitive relation. Concrete failure: group G1 = {38-pin ESP32-DevKitC boards A, B}; group G2 = {bare ESP32-WROOM modules C, D}. Product X (an ESP32 board that also happens to be pin-compatible with the bare modules for your use) is legitimately equivalent to A *and* to C. The single-group model cannot represent this without merging G1∪G2∪{X} into one group — which now falsely asserts A ≡ D (a dev board ≡ a bare module). The operator either records a lie or omits a real equivalence. The addendum (§C) names the join-table alternative and dismisses it as "heavier," but heaviness is not the deciding axis — **correctness of the relation is**, and the PRD never argues that equivalence-in-this-domain is actually transitive. It isn't.
**Failure scenario:** operator groups three brand-relabels of one module (fine), then later buys a fourth part that overlaps two existing clusters; is forced to over-merge; the reorder view (FR64) now shows non-interchangeable parts as substitutes and the operator buys the wrong one.
**Fix:** Either (a) resolve Q8 toward the `product_equivalences(product_id, equivalent_product_id)` join table before schema (accepts multi-membership and non-transitivity), or (b) explicitly narrow the PRD's definition of equivalence to "same manufacturer part, differently branded" (a genuine equivalence class) and state that the transitivity assumption is a deliberate scope limit the operator must respect. Do not ship the FK model while the prose says "functionally interchangeable."

### C2 — FR50 de-duplication silently depends on the ASIN being promoted to an Identifier, which FR11 makes optional — so repeat Amazon purchases create duplicate Products. (§4.10 FR50, §4.2 FR11, §7, UJ-1)
FR11: ASIN is stored on the **Purchase** as Vendor SKU, and "**may** additionally be indexed as a Product Identifier." FR50: capture attaches to an existing Product "where the submitted Vendor SKU matches an existing Product's **Identifier**." FR50's own testable consequence says the match is against an *identifier*, not against prior purchases' `vendor_sku`. So the de-dup only fires if the ASIN was promoted to a `product_identifiers` row — but FR11 says that promotion is optional and §7/FR48 never state that capture performs it. First bookmarklet capture of a product writes `purchases.vendor_sku = <ASIN>` and no identifier; the second capture of the **same** ASIN finds no matching *identifier* and creates a **second Product**. This breaks UJ-1 ("attaching to an existing one by identifier match"), FR41's spirit, and SM-2.
**Failure scenario:** you re-order the same Dorhea ESP32 board three months later; the bookmarklet creates Product #2; price history is now split across two records; "recognize repeat purchases" (JTBD, UJ-5) fails.
**Fix:** Make FR50 match against **both** existing Identifiers **and** prior `purchases.vendor_sku` (vendor-scoped), OR require capture to auto-create/index the ASIN as an Identifier on first sight — and then change FR11's "may additionally be indexed" to "is indexed," removing the contradiction. Pick one and state the double-storage authority (see M7).

### C3 — FR33 (receipt sets status → `ok`) directly contradicts FR30 (derive `low` from quantity ≤ threshold). Stock Status is simultaneously stored and derived with no precedence rule. (§4.7 FR28–FR33, addendum §C `stock_status` column)
`stock_status` is a stored column (FR28 default `unknown`, FR29 manual set, FR33 receipt writes `ok`) **and** a derived value (FR30 `low` when qty ≤ threshold). These collide. Receiving a purchase forces `ok` (FR33), but if the received quantity leaves the product still at/below its threshold, FR30 says it is `low`. The PRD gives no rule for which wins or when derivation re-runs. Worse, **no FR increments `quantity_on_hand` on receipt** — receipt only nulls out a date and (FR33) stamps `ok`. So for a tracked product: receive → FR33 writes `ok` → next FR30 evaluation sees qty unchanged and ≤ threshold → flips back to `low`. The reorder view (FR34) will show the item you just received as needing reorder, or not, depending entirely on evaluation timing.
**Failure scenario:** qty 1, threshold 3, status `low`. You order + receive one more but never manually update qty (quantity is manual-only, FR25). FR33 stamps `ok`; the reorder view derives `low` again; you re-order; repeat forever.
**Fix:** Declare a single source of truth. Recommended: `stock_status` stored holds only the manual override states (`unknown/ok/out` + manual `low`); "effective low" is computed as `stored == low OR (qty ≤ threshold)`; FR33 clears only the *manual* override, and never fights the derived signal. Specify when derivation runs (at read). And decide whether receipt increments `quantity_on_hand` — currently nothing does (see M4).

---

## HIGH

### H1 — Equivalence buys you nothing in the one place it exists for: on-order and receipt do not propagate across a group, so you double-order the exact interchangeable part. (§4.5 FR64, §4.7 FR32/FR33, UJ-5)
UJ-5's stated payoff is "in-flight (on-order) purchases visibly marked so he doesn't double-order" *and* "where equivalents exist, compare price history." But On Order (FR32) is derived per-Product from *that Product's* purchases, and receipt-clears-low (FR33) act on *that Product* only. Group members A and B are both `low`; you order A; A is On Order and (on receipt) `ok`; **B is still `low` with no on-order marker**. The reorder view (FR64) shows B as needing reorder even though its interchangeable twin is inbound/received. The feature's headline use case actively misfires.
**Fix:** FR64 must specify that the reorder view collapses a group to one line and that on-order / recent-receipt on *any* member suppresses (or annotates) the reorder signal for the whole group. Add a testable consequence: "A group with one member On Order shows the group as On Order, not as needing reorder."

### H2 — FR12/FR44 require a GS1 **DataMatrix (2D)** symbol, but the existing label subsystem is a 1D barcode generator with no 2D capability anywhere in its dependencies — so FR42/NFR9 ("no new print path… extended, not forked") are not free. (§4.2 FR12, §4.9 FR42/FR44, NFR9, Q7)
Verified in `app/services/label_printer.py`: printing goes through `pt_p710bt_label_maker` exposing `BarcodeLabelGenerator` and `FlagModeGenerator` (1D barcode generators) via `LpPrinter`. `LABEL_TYPES` already defines `Sato 1x2`, `Sato 2x4`, `Sato 4x6` — so the *media/lp* side of §6/FR43 checks out. **But there is no DataMatrix/QR/PDF417 code anywhere** (`grep` for datamatrix/qr/pdf417/treepoem/pystrich in `app/` and `requirements.txt`: nothing). Rendering a GS1 DataMatrix (FR12/FR44) requires a new 2D-symbology generator — a new rendering capability and almost certainly a new dependency — even though the `lp` submission path is reused. FR42's strong claim ("no new printing path, printer language, or driver") and NFR9's "extended/parameterized, not forked" gloss over this. Q7 flags "template mechanism?" but frames it as parameterization, materially understating that 2D symbology generation is *absent today*.
**Fix:** Downgrade FR42 to "reuses the existing `lp` **submission** path"; explicitly acknowledge a new 2D-barcode rendering dependency is in scope; move Q7 from "confirm before label work" to a blocking spike ("verify `pt-p710bt-label-maker` can emit a GS1 DataMatrix, or select a 2D generator") gating Epic 6. Also note FR43's consequence "no 4×6 template is added" is moot — the subsystem already ships `Sato 4x6`.

### H3 — The Amazon bookmarklet's premise is likely infeasible as written: a product page does not carry *your* order date or the price you *paid*. (UJ-1, §7, §4.10 FR48)
UJ-1 and §7 say the bookmarklet, run "on an Amazon product page," extracts "order date, and unit price." An Amazon **product/listing** page shows the *current* list price and no order date — those live on the order-confirmation / "Your Orders" page, and the price you paid can differ from today's list price. NG4 forbids automated scraping, so you're reading the live DOM of whatever page you're on. As specified, the captured `unit_price` is the current listing price, not what was paid, and `order_date` is unavailable — directly undermining §1's core promise ("what it cost") and the "stop re-transcribing" JTBD.
**Failure scenario:** you capture from the product page a week after ordering; the listing has repriced; your catalog records a price you never paid; the price-history feature (FR20/FR21) is now built on fiction.
**Fix:** Re-scope the bookmarklet source to the **order-details page** (where date, quantity, and price-paid actually appear), or mark order date + unit price as operator-confirmed fields the bookmarklet pre-fills best-effort and the human corrects at capture. Update UJ-1, §7, and FR48 to name the correct page.

### H4 — Normalization + "store unvalidated" GTIN + (type,value) uniqueness can let a garbage identifier squat on a real product's GTIN slot. (§4.2 FR8, FR9, FR10)
FR9 normalizes every GTIN to 14 digits (zero-pad) on write; FR8 makes `(type, value)` unique catalog-wide; FR10 lets a **check-digit-failing** value be stored anyway as a "non-validated identifier." If an unvalidated 12-digit value (not actually a GTIN) is normalized and stored under type `GTIN`, it occupies a normalized 14-digit slot. Later a *different* product's legitimate, check-digit-valid GTIN that normalizes to the same 14 digits is **rejected** by FR8 as a duplicate — a real part blocked by earlier garbage. Conversely two genuinely different mis-keyed unvalidated values could collide by accident.
**Fix:** Store unvalidated values under a distinct type (e.g. `GTIN_UNVALIDATED`) that is *not* GTIN-normalized, or exclude unvalidated identifiers from the normalized-GTIN uniqueness namespace. State explicitly whether normalization applies to unvalidated values (it should not).

---

## MEDIUM

### M1 — FR36 routing rule 3 misroutes coincidental numerics and drops 8-digit GTINs. (§4.8 FR36, FR9)
Rule 3 = "12–14 digits passing GTIN check-digit validation → GTIN lookup." (a) A distributor part number or order number that happens to be 12–14 digits and coincidentally satisfies the mod-10 check digit is misrouted to GTIN lookup instead of free-text (rule 4); ~1-in-10 random numerics pass the check. (b) **GTIN-8 / EAN-8 is 8 digits** and is a valid GTIN; it fails the "12–14 digits" gate and falls to free-text, never normalized/looked-up — a gap versus §1's "any manufacturer GTIN." Note FR9's own examples also silently omit GTIN-8.
**Fix:** Add 8-digit handling to rule 3 (or state EAN-8 is out of scope and why). Accept that check-digit-passing non-GTINs will occasionally misroute and give the GTIN-lookup miss a graceful fall-through to free-text within the same scan (don't dead-end on "no GTIN match").

### M2 — FR37 symbology routing is not actually deterministic; `]d1` names a symbology, not a handler. (§4.8 FR37, addendum §A)
FR37's consequence claims "a `]d1`-prefixed scan routes by symbology." But `]d1` = *any* GS1 DataMatrix (FNC1 first position) — that includes both this system's internal AI-96 symbol **and** a manufacturer's product DataMatrix carrying AI 01 (GTIN). The AIM identifier alone cannot choose between the internal-ID handler and the GTIN handler; you still must inspect the AI. FR37 overstates "deterministic routing."
**Fix:** Reword: AIM identifiers narrow the *symbology class*; the AI/token structural inspection (FR36 rules 1 vs 3) still selects the handler. Fix the testable consequence accordingly.

### M3 — Q1 (FNC1 transmission / AIM support) is a go/no-go blocker dressed as a routing simplification. (§4.8 FR37a, Q1)
The PRD says confirming Q1 "simplifies FR36 routing" and that FR37/FR37a "degrade gracefully either way." But if the deployed Tera HW0009 mangles or reorders the 2D payload (not just strips FNC1), the *entire* internal-ID scan path (the core identification loop, SM-3/SM-4) is at risk — this is not a simplification, it's a feasibility gate for Epic 4/6. The graceful-degradation story leans entirely on the `WIT` token surviving as a literal prefix after FNC1 stripping; if the scanner also transforms the data characters, there is no fallback.
**Fix:** Elevate Q1 to a blocking hardware spike with a pass/fail criterion ("the deployed scanner round-trips a GS1 DataMatrix carrying AI 96 `WIT…` recognizably under its actual config") before committing the internal-encoding design, not just "before the scan-routing work."

### M4 — Nothing increments `quantity_on_hand`; tracked quantity is stale the instant any purchase is received. (§4.6 FR23–FR25, §4.7 FR33)
Quantity is manual-only (FR25 "manually asserted"). Receiving a purchase (FR33) does not touch quantity. So for a tracked item, every receipt immediately desynchronizes the count from reality until the operator manually re-asserts — and FR33 simultaneously stamps `ok`, hiding the fact that the count is now wrong. This may be intentional ("honest staleness," RISK-2 / FR25 age display), but the PRD never says receipt-does-not-affect-quantity, and it interacts badly with C3.
**Fix:** State explicitly that receipt does not modify `quantity_on_hand` (and rely on the staleness display), or add an optional "increment on receipt" for tracked items. Either way, resolve against C3.

### M5 — Untestable adjectives inside "Consequences (testable)". (Glossary "Quantity On Hand"; FR23; FR21)
- FR23 / Glossary: "the three states **render distinguishably**" / "render distinguishably" — no observable is defined; a reviewer cannot fail this without inventing a criterion.
- FR21: "the most recent unit price is **visibly distinguished**" — same weasel.
These smuggle subjective UI judgments into requirements labeled testable.
**Fix:** Pin an observable: e.g. "`NULL` renders as the literal text '—/untracked', `0` as 'In stock: 0', `N` as 'In stock: N'"; "prior price appears in a labeled field named 'Last paid'." UX can refine styling; the *distinction* must be assertable.

### M6 — Attachment model permits orphans and ambiguity; FR5's "either/or" has no XOR constraint. (§4.1 FR5, addendum §C `attachments`)
`attachments(product_id NULL, purchase_id NULL, …)` with both nullable allows a row with **both** null (orphan) or **both** set (ambiguous ownership). FR5 says "either a Product or a specific Purchase" — an exclusive-or the schema doesn't enforce.
**Fix:** Add a CHECK / application invariant that exactly one of the two FKs is non-null, and state it in FR5's consequences.

### M7 — Internal Identifier is double-stored (`products.internal_id` column **and** a `product_identifiers` row of type `INTERNAL`) with no stated authority. (§4.2 FR7, FR55, addendum §C)
FR7 stores identifiers including type `INTERNAL`; the addendum data model also carries `products.internal_id`. FR55 keys direct URLs on "the Internal Identifier" without saying which store is canonical. Two sources of truth can diverge (e.g. an identifier-table edit not reflected on the column). Same double-storage smell as C2's ASIN.
**Fix:** Declare one canonical store. Recommended: `products.internal_id` is authoritative and generated; the `INTERNAL` identifier-type row, if present at all, is a derived/denormalized read index, not independently editable.

---

## LOW

### L1 — FR62 "creating the group if none exists" is undefined when *both* products already belong to (different) groups. (§4.5 FR62)
Adding B to A's group when B is already in a group: merge the groups? reject? move B (breaking B's other equivalences)? Unspecified. With the FK model (C1) a move silently drops B's prior equivalences.
**Fix:** Define the collision behavior explicitly; add a testable consequence.

### L2 — FR17 category rename has no collision/merge semantics. (§4.3 FR17)
Renaming a path segment so it collides with an existing sibling path (e.g. `power`→`electronics` where `electronics` exists) has undefined merge behavior over the materialized paths.
**Fix:** Specify reject-on-collision (simplest) and add a consequence.

### L3 — SM-4 "the large majority of the time" is an unquantified success threshold. (§11 SM-4)
Not falsifiable as written.
**Fix:** Either give a rough number ("≥ ~90% of scans, subjectively") or explicitly mark it qualitative like SM-1/SM-2 rather than implying a rate.

### L4 — FR51 idempotency: same `request_key` with a *different* payload is undefined. (§4.10 FR51, addendum §C)
Return the original, reject, or overwrite? Unspecified.
**Fix:** State "same key returns the originally created record; payload differences are ignored" (typical idempotency-key contract).

### L5 — FR43's "no 4×6 template is added" is already contradicted by the existing subsystem, which ships `Sato 4x6`. (§4.9 FR43, verified in `label_printer.py`)
Harmless (the intent is "the catalog feature targets 1×2/2×4"), but the wording asserts a false fact about the environment.
**Fix:** Reword to "the catalog feature emits only to 1×2 and 2×4; 4×6 remains reserved for shipping" without claiming the template doesn't exist.

### L6 — FR9 stores the normalized 14-digit value, discarding the original entry form. (§4.2 FR9, Glossary GTIN)
UPC-A vs EAN-13 vs GTIN-14 of the same product all collapse to one stored string; the as-scanned/as-printed form is not preserved for display or audit. Intended for lookup, but the PRD never says the original is discarded.
**Fix:** If the source form matters for display, keep it alongside the normalized key; otherwise state the discard is intentional.

---

## Brownfield claims — verification results

- **FR27 (reuse existing location/vendor vocabulary): VERIFIED ACCURATE.** `GET /api/inventory/field-suggestions/<field>` exists (`app/main/routes.py:1154`) and serves `location`, `sub_location`, `vendor`, `purchase_location`, `thread_size` via `app/static/js/field-autocomplete.js`, including sub-location scoping by parent location. FR27's reuse is realistic. *Minor caveat:* suggestions are drawn from existing (metal-stock) rows; Products' own new locations won't feed back into autocomplete unless the endpoint's source query is extended to union Product rows — so "draws from the same source" holds at read, but the vocabulary is one-directional until extended.
- **FR42/§6 (SATO 1×2 / 2×4 / 4×6 via `lp`): PARTIALLY VERIFIED.** `LABEL_TYPES` in `app/services/label_printer.py` already defines all three SATO sizes and submits via `LpPrinter`. The media/`lp` claim is sound.
- **FR12/FR44 (GS1 DataMatrix 2D): NOT SUPPORTED TODAY — see H2.** The existing generators are 1D (`BarcodeLabelGenerator`, `FlagModeGenerator`); no 2D-symbology library is present in `app/` or `requirements.txt`. This is the load-bearing unverified assumption behind FR42/NFR9/Q7.
