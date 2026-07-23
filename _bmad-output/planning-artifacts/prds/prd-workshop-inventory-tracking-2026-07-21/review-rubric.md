# PRD Quality Review — Product Catalog & Purchase Tracking

## Overall verdict

This is a strong, unusually disciplined PRD for its stakes: a clear identification-not-inventory thesis (§1) drives a bounded brownfield enhancement, every FR carries concrete testable consequences, and scope boundaries are stated rather than left to inference. It is correctly shaped as a capability spec with lean, justified UJs for a single-operator hobby tool, and it feeds downstream cleanly via a rich Glossary, a companion data model, and an FR-mapped epic decomposition. What's at risk is minor and localized: one broken Glossary cross-reference (§4.13 should be §4.5), an undefined but load-bearing "specifications" noun, and the one feature — Equivalent Products (§4.5) — that is both newly-in-scope and the least anchored to the central thesis, resting on an unconfirmed model (Q8). None of these blocks a green light.

## Decision-readiness — strong

A decision-maker can act on this. Choices are stated as decisions with what-was-given-up attached, not smoothed to neutral: ASIN is recorded on the Purchase, not as Product identity, with the reason stated inline ("ASINs are reused by Amazon," FR11); the AI-96 internal-encoding choice carries a rejected-alternatives trail (AI 91, AI 4311, product-URL) in the addendum, referenced rather than buried. Open Questions are genuinely open — Q1 is empirical scanner behavior, Q7 is an unverified assumption about the existing label subsystem, Q8 is an unresolved data-model shape — not rhetorical questions answered in the next sentence. The single `[NOTE FOR PM]` sits at a real tension (§4.5, the one feature flagged as "meaningful modeling complexity"), not at a safe checkpoint. Counter-metrics SM-C1/SM-C2 name what *not* to optimize, which is the tell of a PRD that has actually made trade-offs.

The one thing a reviewer pushing back would flag: Equivalent Products is marked in-scope while its model rests on an unconfirmed assumption (Q8, "Confirm before schema"). But this is surfaced honestly rather than dodged — tagged, indexed, and gated — so it counts as decision-ready, not evasive.

## Substance over theater — strong

The content is earned. There is no persona theater — a single named protagonist (Jason) across five lean scenes, with §2.3 explicitly justifying the lean shape for a single-operator tool. No innovation/differentiation section exists to pad. NFRs are product-specific with reasoning, not boilerplate: NFR7 demands pure, exhaustively-tested identifier logic *because* "errors there produce expensive-to-detect data corruption"; NFR11 requires deterministic raster rendering. The Vision is non-swappable — it names a specific insight ("this is not an inventory-control problem — it is an identification problem") and a specific waste being captured (the editorial label work "thrown away"). RISK-1 is a *rejected* option (LLM-generated label copy) with a concrete failure mode, not a hedge.

Minor furniture note, not theater: FR56 (touch equivalents for every shortcut) and FR58 (no keyboard dependency) overlap substantially; one could absorb the other.

## Strategic coherence — strong

There is a real thesis and the PRD bets on it: identification-at-point-of-pickup, offline, without recourse to a vanished vendor page (§1). Prioritization follows from it — the provisional sequencing (§10.3, addendum §D) deliberately front-loads the identification loop "create a Product → print a label → scan it back" and defers classification/stock until the loop is proven. Success Metrics validate the thesis (SM-1 continued use, SM-3 offline identifiability) rather than measuring activity, and the counter-metrics guard the thesis boundary (SM-C1 "do not chase backfill" is a direct defense of the identification-not-inventory framing). MVP scope kind is problem-solving and the scope logic matches.

The one coherence seam worth naming: Equivalent Products (§4.5, FR62–64) serves reorder/price-comparison convenience, which is adjacent to — not part of — the identification thesis. It is the one capability that reads as "wanted" rather than derived from the arc, and it is also the newest and least-confirmed. Coherent enough to keep, but it is the weakest-anchored scope decision in the document.

### Findings
- **low** Equivalent Products sits slightly outside the identification thesis (§4.5, FR62–64) — It is a reorder convenience, newly-in-scope, and modeled on an unconfirmed assumption (Q8), making it the one feature not derived from the central arc. *Fix:* no change needed to scope, but keep Q8 resolution gating its epic (already advised in §10.3) so it isn't built on a guessed model.

## Done-ness clarity — strong

This is the standout dimension. Every FR carries an explicit "Consequences (testable)" block, and many use literal, executable values: FR9 gives the three GTIN encodings that must resolve to one Product; FR30 gives "Quantity 2, threshold 3 → low"; FR57 gives "At 360 px…". Adjective-hedging ("handles gracefully," "reasonable performance," "user-friendly") is essentially absent from the FRs; where softness appears it is bounded honestly and framed as qualitative-by-choice (SM-4 "large majority of the time," NFR6 "consistent with the existing suite"), appropriate to hobby stakes.

The one real gap an engineer would hit: FR57 requires the scan-result view to show "specifications," and UJ-4 repeats "specs," but "specifications" is not a Glossary term and does not map cleanly to a named Product field (the Product carries manufacturer, MPN, Label Description, notes, category, tags, and `attributes` JSON — "specifications" presumably means `attributes`, but that is inference). Since FR57 is the self-sufficient scan-result view that story/UX creation will build directly, the undefined noun is load-bearing.

### Findings
- **medium** "specifications"/"specs" is undefined but load-bearing (FR57, UJ-4, §4.6 description) — Used in the scan-result view FR downstream UX/stories will build, with no Glossary definition and no clean mapping to a named Product field. *Fix:* add a Glossary entry (or point FR57 at `attributes`/named fields) so "shows specifications" has a concrete render target.

## Scope honesty — strong

Omissions are explicit and do real work. Non-Goals NG1–NG10 are concrete and defended (NG5 no-LLM ties to RISK-1; NG7 no-vendor-API ties to the no-op Enrichment Interface). §10.2 restates the de-scoped items (4×6 template, multi-vendor bookmarklet) with the resolving question cited (Q3, Q5). Assumptions are tagged inline and indexed (§13); the newly-in-scope feature is flagged as such in plain language ("This feature is **newly in scope** for this phase"). De-scoping is done openly, never silently.

Open-items density is low and proportionate — four open questions and three assumptions against a bounded hobby enhancement — nowhere near the level that would block a green light. The single genuine scope risk (building §4.5 on an unconfirmed model) is itself declared, gated, and cross-referenced to the addendum's modeling note.

## Downstream usability — strong

This PRD is built to be source-extracted. The Glossary is rich and terms are used near-verbatim across FRs, UJs, and metrics. FR/UJ/SM/NFR IDs are contiguous and unique; UJs each carry the named protagonist inline. The addendum deliberately carries the indicative data model (§C) and an FR-mapped 10-epic decomposition (§D) *for* the downstream workflows, and every FR appears in an epic's "Covers" list — architecture, UX, and epic/story creation can all pull cleanly.

Two mechanical snags will trip a literal extractor. First, the Glossary's "Equivalent Product Group" entry points to "**§4.13**" for the feature, but Equivalent Products is **§4.5** (§4.13 is Extensibility Hooks) — a reader or tool following that ref lands on the wrong section. Second, FR62–64 live in §4.5, which sits physically before §4.6 (FR23), so a tool reading in document order encounters FR62 before FR23; this is documented in the §4 preamble but still non-monotonic.

### Findings
- **medium** Broken Glossary cross-reference (§3, "Equivalent Product Group") — Says "see §4.13 and addendum"; the feature is §4.5, and §4.13 is Extensibility Hooks. A source-extractor or reader is routed to the wrong section. *Fix:* change "§4.13" to "§4.5".
- **low** FR62–64 out of document order (§4.5) — They precede FR23 (§4.6) in reading order; documented in the §4 preamble but a naive extractor going top-to-bottom sees a non-monotonic ID sequence. *Fix:* acceptable as-is given the preamble note; optionally add a one-line pointer at the §4.4→§4.5 boundary.

## Shape fit — strong

The PRD is shaped exactly as the rubric's §7 guidance prescribes for this product: a single-operator, brownfield, hobby capability spec with lean UJs. §2.3 states the choice explicitly ("Single-operator tool, so these are captured as lean scenes with one named protagonist"), and the UJs earn their place by pinning FR-to-scenario traceability rather than performing multi-stakeholder ceremony. SMs are appropriately operational/qualitative rather than user-funnel metrics. Brownfield references read as accurate and specific — the existing `lp` label subsystem, Bootstrap 5.3.2, MariaDB + Alembic (via `manage.py db`, not Flask-Migrate), the `requests`-only client, and the existing thread-size/vendor/location autocomplete pattern — and new-vs-existing surfaces are distinguished (NFR9 metal-stock unaffected; FR14/FR27 reuse existing vocabularies). It is neither over-formalized (no gratuitous UJ density) nor under-formalized. No finding.

## Mechanical notes

- **Broken cross-ref (see Downstream usability):** §3 Glossary "Equivalent Product Group" → "see §4.13" should be "§4.5". This is the one cross-reference that does not resolve to the intended target; all other §/FR/UJ/NFR/RISK/NG cross-refs checked resolve correctly (e.g., FR64→FR34, §9 NG5/NG7, §8 RISK-3, UJ "Realizes FR…" lists).
- **ID continuity:** FR1–FR64 all present, including lettered variants (FR12a–d, FR37a, FR49a). No duplicates or true gaps; FR62–64 are appended out of section order by design (documented, §4 preamble). UJ-1–5, SM-1–4 + SM-C1–C2, NFR1–11, RISK-1–5, NG1–10 all contiguous. Open Questions renumber-by-survival (remaining Q1, Q2, Q7, Q8; Q3–Q6 marked resolved) — intentional and readable.
- **Assumptions Index roundtrip:** Three inline `[ASSUMPTION]` tags (§2.2, §3 Glossary, §4.5) all appear in the §13 index. Minor drift: the index's third entry ("§4.5 (FR62–64) — Equivalence scope is intentionally minimal…") describes content that appears inline as a `[NOTE FOR PM]` in §4.5's Notes, not as an `[ASSUMPTION]` tag — so that index line has no matching inline `[ASSUMPTION]`. Low impact; either retag inline or footnote the index entry as a scope-boundary note.
- **Glossary drift:** "Vendor SKU" (Glossary canonical) appears lowercased in narrative and in the addendum data model ("vendor SKU", "vendor_sku") — expected in a code block, minor in prose. "specifications"/"specs" is used (FR57, UJ-4, §4.6) without a Glossary entry — noted above as a done-ness finding, not just cosmetic. Otherwise domain nouns (Product, Purchase, Stock Status, Quantity On Hand, Internal Identifier, Provenance Block) are used identically throughout.
- **UJ protagonist naming:** All five UJs name Jason and carry context inline; no floating UJs.
- **Required sections:** All present and proportionate for the agreed stakes — Vision, Target User + JTBD + Non-Users + UJs, Glossary, Features/FRs, NFRs, constraints, API surface, risks, non-goals, MVP scope, metrics, open questions, assumptions index, plus a companion addendum carrying architect-owned depth.
