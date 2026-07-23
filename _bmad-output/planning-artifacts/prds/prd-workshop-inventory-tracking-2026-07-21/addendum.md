# PRD Addendum — Product Catalog & Purchase Tracking

*Companion to `prd.md`. Preserves technical depth, rejected-alternative rationale, an indicative data model, reference notes, and a provisional epic/story decomposition — material that belongs to downstream workflows (architecture, epics/stories) or earned a place but does not fit the PRD's capability-level narrative. Nothing here overrides the PRD; where they touch, the PRD's FRs win. Revised alongside the finalize reviewer gate.*

---

## A. Internal Identifier Encoding — Rationale & Rejected Alternatives

**Chosen encoding** (PRD FR12–FR12d, Glossary "Internal Encoding"). GS1 DataMatrix (ECC 200, FNC1 in first position), a single element string carrying GS1 Application Identifier **96** (company internal information), data field = configured token `WIT` + internal identifier. Because AI 96 is variable-length and terminal, no FNC1 separator is required — a deliberate simplification that keeps both encoder and parser free of separator handling.

> **Rendering caveat (see §F, PRD H2/Q7).** The existing label subsystem renders **1D barcodes only**. Producing this GS1 DataMatrix is a *new* 2D-symbology rendering capability and almost certainly a new dependency — in scope per FR42, gated by the Q7 spike. The encoding decision below is sound; the rendering path is the open engineering question.

**Standards basis.** GS1 General Specifications §3.10.2 reserves AIs **91–99** for company internal information; the data field is alphanumeric and, following GSCN 16-000528, may extend to ~90 characters (raised from the original 30). Content and meaning are entirely at the defining company's discretion — the correct standards-based home for a private product identifier.

**Alternatives considered and rejected:**

- **AI 91.** Valid, but the lowest number in the range and the one an organization is most likely to reach for first. Using **96** reduces the already-small chance of colliding with a foreign label carrying the same AI. (This is why the PRD picks 96 over 91.)
- **AI 4311 (return-to contact name), GS1 GenSpecs §3.7.31.** Rejected (PRD FR12d). The 43xx series addresses parcel routing for logistics systems; none read these labels. Being variable-length, a second element string would force FNC1 separator handling and add ~17 characters — enlarging the symbol precisely on the 1×2 media where space is scarcest and thermal degradation is most consequential. Ownership/return info belongs in human-readable text, which is what a person recovering a stray part would actually read.
- **Product detail URL.** Self-routing and scannable by any phone camera without an app, but produces a larger symbol and **breaks every previously printed label if the hostname ever changes** — an unacceptable durability property for labels expected to outlive several infrastructure decisions.

**AIM symbology identifiers.** GS1 DataMatrix (ECC 200, FNC1 in first position) is denoted `]d1`. `]d2` denotes ECC 200 with FNC1 in fifth/sixth position — an industry-specific variant this system does not emit. Note `]d1` identifies only the *symbology*, not the payload semantics: both this system's internal AI-96 symbol and a manufacturer's AI-01 (GTIN) DataMatrix present as `]d1`, so the AI/token structural inspection (PRD FR36 rules 1 vs 3, FR37) still selects the handler. Scanner support for AIM-identifier transmission — and, more importantly, whether the deployed unit round-trips the 2D data characters intact — is configuration-dependent and must be verified on the deployed unit (PRD Q1, a blocking spike).

---

## B. Reference Notes

**ECIA / ANSI MH10.8.2.** ECIA publishes a 2D barcode guideline for electronics distribution; participating distributors include Avnet, Allied, Arrow, Digi-Key, Future, Mouser, Newark, Sager, TTI. Labels use DataMatrix or PDF417 carrying ANSI MH10.8.2 data identifiers encoded per ISO/IEC 15434:2006. Fields are delimited by group separators (0x1D) within a format-06 envelope. Relevant data identifiers: `P` customer part number, `1P` supplier part number (required per spec), `Q` quantity, `K` customer order number, `1K` supplier order number, `9D`/`10D` date in YYWW. (Drives PRD FR38.)

**FNSKU.** Amazon FBA items carry `X00…` barcodes that are per-seller-per-product, not global product identifiers. A reliable "same seller, same item" signal and nothing more. Stored as its own identifier type; never conflated with GTIN.

**GTIN forms and normalization.** GTIN-8 (8), UPC-A (12), EAN-13 (13), GTIN-14 (14) all normalize (zero-pad left) to a single 14-digit key — the canonical lookup/uniqueness value (PRD FR9). Check-digit-failing values are **not** GTINs: they are stored, if kept, as `GTIN_UNVALIDATED` (unnormalized, outside the GTIN uniqueness namespace, PRD FR10/H4) so a mis-keyed value can never squat a real product's normalized GTIN slot. If preserving the as-entered form (UPC-A vs EAN-13) matters for display/audit, keep it alongside the normalized key; the PRD treats that as an architect's choice.

**GS1 company prefix.** A valid GTIN embeds a company prefix identifying the brand owner, queryable via GEPIR — occasionally useful for determining the actual manufacturer of a white-labeled part. Not in scope; noted for future reference.

**Label format example** (current manual practice, to be preserved — basis for the Product/Purchase split, PRD FR1):

```
Dorhea ESP32-DevKitC ESP32-WROOM-32D 38-pin wide / Amazon 2025-11-16 B08MFBQ8LV $4.67ea
```

The description half describes the Product; the provenance half describes the Purchase.

---

## C. Indicative Data Model

*Context for the Architect. **Not prescriptive** — the Architect owns final schema design (per PRD NFR2/NFR3, MariaDB + Alembic). Extended from the source draft to include Equivalent Product Groups and the finalize-gate fixes.*

```
products
  id, internal_id,                -- AUTHORITATIVE Internal Identifier (PRD FR7/M7)
  manufacturer, mpn,
  description,                    -- label text, human-authored (Label Description)
  category_path, notes, attributes JSON,   -- attributes = Specifications
  quantity_on_hand NULL, quantity_verified_at,   -- manual-only; receipt never writes these
  reorder_threshold,
  stock_status, stock_status_at,  -- STORED = manual assertion only (unknown/ok/low/out)
                                  --   Effective Low & On Order are DERIVED, never stored
  location, sub_location,
  equivalent_group_id NULL,       -- FK -> equivalent_groups.id; at most one group per product
  created_at, updated_at

product_identifiers
  id, product_id, type, value       -- unique(type, value)
  -- types: GTIN, GTIN_UNVALIDATED, ASIN, FNSKU, MPN, VENDOR_SKU, INTERNAL
  -- GTIN values are normalized-14; GTIN_UNVALIDATED are as-entered, outside GTIN namespace
  -- INTERNAL row (if present) is a DERIVED read index of products.internal_id, not editable
  -- ASIN indexed here on capture so repeat Amazon buys de-dup (PRD FR11/FR50/C2)

product_tags
  product_id, tag                   -- unique(product_id, tag)

purchases
  id, product_id, vendor, vendor_sku,   -- vendor_sku also used (vendor-scoped) for de-dup, FR50
  order_date,                       -- defaults to capture date on capture (PRD FR48/RISK-6)
  received_date NULL,               -- null = On Order (derived)
  quantity, unit_price, order_number, source_url,
  request_key NULL,                 -- idempotency (FR51): same key returns original record
  created_at

attachments
  id, product_id NULL, purchase_id NULL,
  path, kind, filename, created_at
  -- INVARIANT (PRD FR5/M6): exactly one of (product_id, purchase_id) is non-null
  --   enforce via CHECK ((product_id IS NULL) <> (purchase_id IS NULL)) or app-level guard

equivalent_groups                   -- PRD §4.5, FR62-64
  id, created_at
  -- membership via products.equivalent_group_id (at most one group per product)
```

**Derived signals — do not store (PRD FR30/FR32, C3).**
- **Effective Low** = `stored_status IN ('low','out')` OR `(quantity_on_hand IS NOT NULL AND quantity_on_hand <= reorder_threshold)`, evaluated at read.
- **On Order** = EXISTS a purchase with `received_date IS NULL` for the product **or any product sharing its `equivalent_group_id`** (PRD FR64/H1).
- Receipt (`received_date` set) clears only a *manual* `low`/`out` back to `ok`; it never touches `quantity_on_hand` and never fights the derived Effective-Low signal (PRD FR33/M4).

**Equivalence modeling note (PRD Q8 — RESOLVED).** The PRD narrowed Equivalent Products to the **"same manufacturer part, differently branded" equivalence class** (PRD §4.5, NG11). Because "same part" is genuinely reflexive/symmetric/**transitive**, membership is a partition and the nullable-FK model is *correct* — the transitivity objection that would defeat a "functionally interchangeable" reading does not apply here. Two alternatives were considered and rejected for this scope: (1) a `product_equivalences(product_id, equivalent_product_id)` join table — needed only if non-transitive/overlapping substitutability were in scope, which NG11 excludes; (2) directional `preferred`/`substitute` semantics — heavier and unused by the reorder use case. FR62 rejects adding a Product that already belongs to a different group (rather than silently moving it), so the FK model loses no existing equivalence.

---

## D. Provisional Epic & Story Decomposition

*Carried from the source draft (`~/tmp/prd-product-catalog.md` §7–§8) and extended. **Advisory** — `bmad-create-epics-and-stories` owns the final breakdown. FR references map to `prd.md`. Note the two blocking spikes (Q1, Q7) and the new Epic 10.*

### Epic dependency & order

| # | Epic | Depends on |
|---|------|-----------|
| 1 | Product and Purchase Data Model Foundation | — |
| 2 | Identifier System and Normalization | 1 |
| 3 | Taxonomy and Tagging | 1 |
| 4 | Scan Routing and ECIA Parsing | 2, **Q1 spike** |
| 5 | Optional Stock Tracking and Reorder Signals | 1 |
| 6 | Label Generation and Printing | 2, **Q7 spike** |
| 7 | Order-Time Capture API and Bookmarklet | 1, 2 |
| 8 | Search, Retrieval, and Attachments | 1, 3 |
| 9 | Handheld and Touch Readiness | 4, 5 |
| 10 | Equivalent Products | 1 (complements 5) |

**Recommended delivery order:** 1 → 2 → 4 → 6 → 7 → 3 → 5 → 10 → 8 → 9. This front-loads the identification loop (create a product, print a label, scan it back) — the core value — and defers classification and stock features until the loop is proven in daily use. **Clear the Q1 spike before Epic 4 and the Q7 spike before Epic 6** (both are feasibility gates for the 2D-barcode core, not mere simplifications).

### Epic 1 — Product and Purchase Data Model Foundation
**Goal:** Products and Purchases as first-class entities alongside metal stock, with CRUD and detail views. **Covers:** FR1–FR6, FR18–FR22, FR61, NFR1, NFR3, NFR9.
- **1.1 Product entity and migration** — migration creates a products table (manufacturer, MPN, label description, notes, category path, location, sub-location, attributes JSON, internal_id, stock/quantity fields, equivalent_group_id); existing metal-stock tables/behavior unchanged.
- **1.2 Purchase entity and migration** — purchases table referencing products (vendor, vendor_sku, order_date, nullable received_date, quantity, unit_price, order_number, source_url, request_key); a purchase may be created with a null received date.
- **1.3 Product CRUD UI** — creating a Product with only a label description saves with all other fields empty; detail view reachable by direct URL keyed on internal_id.
- **1.4 Purchase history display** — three purchases across two vendors list chronologically with date/vendor/price; most recent prior price shown in a "Last paid" field.
- **1.5 Attachments** — uploading a PDF datasheet stores and links it to the Product; retrievable from Product and (where applicable) the Purchase; the exactly-one-owner invariant (FR5/M6) is enforced.

### Epic 2 — Identifier System and Normalization
**Goal:** One Product reachable by any identifier printed on it, its packaging, or its vendor's label. **Covers:** FR7–FR12, FR12a–FR12d, NFR7.
- **2.1 Identifier entity** — types incl. GTIN, GTIN_UNVALIDATED, ASIN, FNSKU, MPN, VENDOR_SKU, INTERNAL stored with type; duplicate (type,value) on another Product rejected naming the conflict; internal_id authoritative, INTERNAL row a derived index.
- **2.2 GTIN normalization** — GTIN-8/UPC-A/EAN-13/GTIN-14 of the same product resolve to one normalized key; GTIN_UNVALIDATED stored as-entered outside the namespace.
- **2.3 GTIN check-digit validation** — bad check digit rejected as GTIN, offered as GTIN_UNVALIDATED; an unvalidated value does not block a later valid GTIN normalizing to the same digits (H4).
- **2.4 Internal identifier and GS1 AI 96 encoding** — on save, internal_id generated; payload is a GS1 element string, FNC1 first position, AI 96, data field `WIT`+internal id, sole element string, cannot collide with any valid GTIN or ECIA format-06 envelope.
- **2.5 Foreign AI 96 rejection** — a scanned AI-96 element string whose data field doesn't begin with `WIT` is not treated as internal; falls through to free-text search.

### Epic 3 — Taxonomy and Tagging
**Goal:** Classify and cross-reference without designing a taxonomy in advance. **Covers:** FR13–FR17, FR53.
- **3.1 Materialized-path categories** — typing `electronics/power/dc-dc-converters` creates and assigns it; later offered via autocomplete.
- **3.2 Category rename with descendants** — renaming a segment updates all descendant paths and assigned Products; a rename colliding with an existing sibling path is rejected (L2).
- **3.3 Free-form tags** — three heat sinks under `thermal/heat-sinks`, two tagged `ssr` / one `rectifier`; filtering by tag returns the correct subset independent of category.

### Epic 4 — Scan Routing and ECIA Parsing  *(gated by Q1 spike)*
**Goal:** Any barcode in the shop resolves correctly from a single scan. **Covers:** FR35–FR41, NFR8.
- **4.0 Q1 hardware spike** — verify the Tera HW0009 round-trips a GS1 DataMatrix carrying AI 96 `WIT…` recognizably (data chars intact; FNC1 as GS/substitute/stripped; AIM `]d1` support). Pass/fail gate before building the internal-ID scan path.
- **4.1 Scan input capture** — scan as keystrokes terminated by Enter captured and routed with no scanner-specific config.
- **4.2 Routing by structure** — internal AI-96+token → internal ID; format-06 header → ECIA; 8 or 12–14 digits w/ valid check digit → normalized GTIN lookup (GTIN-miss falls through to free-text); else → free-text search (FR36/M1).
- **4.3 AIM symbology narrowing** — `]d1` confirms GS1 DataMatrix class; AI/token still selects internal-vs-GTIN handler; unchanged when absent (FR37/M2).
- **4.3a FNC1 transmission tolerance** — GS (0x1D) / substitute char / stripped all parse, given data chars intact.
- **4.4 ECIA data identifier parsing** — DigiKey DataMatrix yields `P`, `1P`, `Q`, `K`, `1K`, `9D`/`10D`; malformed envelope surfaces the raw scan rather than raising.
- **4.5 Pre-populated creation from ECIA scan** — parsed distributor scan with no match opens a creation form with MPN/quantity/order refs pre-filled and editable.
- **4.6 Unknown scan path** — a scan matching no record opens a creation form with the scanned identifier attached and its type inferred; no error page.
- **4.7 Duplicate prevention on receipt** — a scan resolving to an existing Product in a receiving context offers to add a purchase; duplicate creation requires explicit confirmation.

### Epic 5 — Optional Stock Tracking and Reorder Signals
**Goal:** Track quantity/location only where worthwhile, with honest staleness and no stored/derived contradiction. **Covers:** FR23–FR34, NFR5.
- **5.1 Tri-state quantity** — new Product quantity null → rendered "Not tracked"; setting to 0 → "In stock: 0"; N → "In stock: N" (three distinct strings, M5).
- **5.2 Verification timestamp** — quantity set eight months ago shown with the age of its last verification; receipt does not change quantity or its timestamp (M4).
- **5.3 Manual stock status flag** — flagging an untracked Product `low` sets stored status, records a timestamp, and makes it Effective Low.
- **5.4 Derived Effective Low** — quantity 2, threshold 3, stored `ok` → Effective Low at read, no stored-status write (C3).
- **5.5 Derived on-order indicator** — a Product (or any group sibling) with an unreceived purchase is marked On Order in any status view; nothing persisted.
- **5.6 Receipt clears manual override without flip-flop** — receiving a manually-`low` untracked Product → `ok`; receiving a tracked Product still ≤ threshold leaves it Effective Low and does not touch quantity (C3/M4).
- **5.7 Unified reorder view** — manually-low and threshold-derived-low Products in one list; On-Order marked; groups collapsed to one line.

### Epic 6 — Label Generation and Printing  *(gated by Q7 spike)*
**Goal:** Labels generated from records; reprinting trivial; 2D rendering added to the existing subsystem. **Covers:** FR42–FR47, NFR9, NFR11.
- **6.0 Q7 rendering spike** — verify `pt-p710bt-label-maker` can emit a GS1 DataMatrix or select a 2D-symbology generator/dependency; confirm the template mechanism parameterizes (not forks). Gate before label work (H2).
- **6.1 Label rendering via existing lp path** — 2×4 template renders a raster submitted through the existing `lp` path (no new submission path); repeated rendering of an unchanged record is byte-identical; a GS1 DataMatrix is rendered into the raster.
- **6.2 Template variants** — 1×2 template fits content with a GS1 DataMatrix encoding AI 96 per FR12–FR12b; catalog feature never emits a 4×6 catalog label (L5).
- **6.3 Canonical field order** — provenance block last, consistent structure across all labels.
- **6.4 Dual encoding** — internal identifier as both 2D barcode and human-readable text.
- **6.5 Reprint** — reprint from the Product view regenerates and sends with no re-entry.

### Epic 7 — Order-Time Capture API and Bookmarklet
**Goal:** Metadata captured while the vendor page is open. **Covers:** FR48–FR51, FR49a, FR60, NFR10.
- **7.1 Capture endpoint** — JSON payload (vendor, vendor_sku, title, unit_price, quantity, url, optional order_date) → creates a Purchase (order_date defaults to capture date), and a Product if no identifier/vendor_sku match; response includes the Product URL.
- **7.2 Match to existing product for de-dup** — vendor_sku matching an existing Identifier or prior purchase attaches the purchase; first-sight ASIN indexed as an Identifier; no duplicate Product (C2).
- **7.3 Title as editable draft, or authored description** — title becomes an editable draft; a supplied authored description replaces it and stays editable at receipt.
- **7.4 Idempotent creation** — same request key twice → exactly one Purchase; both responses reference it; differing payload on a repeat key ignored (L4).
- **7.5 Enrichment hook** — no-op returns an empty partial record; creation proceeds unchanged; a future implementation needs no change to the creation path.
- **7.6 Bookmarklet (Amazon-only)** — on an Amazon product page, extracts vendor_sku/title/price, posts to the capture endpoint, shows a confirmation with a link to the record. Captured price treated as paid; order date defaults to today (RISK-6).

### Epic 8 — Search, Retrieval, and Attachments
**Covers:** FR52–FR55.
- **8.1 Full-text search** — a term in description/notes/MPN/identifier returns the matching Products.
- **8.2 Faceted filtering** — filter by category path prefix, tag, or Effective-Low/stock status; filter state in a bookmarkable URL.

### Epic 9 — Handheld and Touch Readiness
**Covers:** FR56–FR59, NFR4.
- **9.1 Touch equivalents for shortcuts** — every keyboard shortcut has a reachable touch control at handheld width.
- **9.2 Self-sufficient scan-result view** — at 360 px, a resolved scan shows identity/Specifications/location/status (with Effective-Low/On-Order) and allows quantity + status changes without navigation.
- **9.3 Form-state persistence** — a partially composed label description survives a dropped-and-restored connection.

### Epic 10 — Equivalent Products
**Goal:** Declare same-part brand-relabels as one group and surface it in reorder/price comparison. **Covers:** FR62–FR64. **Depends on:** Epic 1 (complements Epic 5's reorder view).
- **10.1 Declare/undeclare equivalence** — adding Product B to Product A's group makes both symmetric members of one group; a member can be removed leaving the rest grouped; adding a Product already in a *different* group is rejected rather than moved (FR62/L1).
- **10.2 Equivalents on product detail** — a member's detail view lists the other members with manufacturer/MPN and latest unit price.
- **10.3 Equivalence in reorder view** — a group collapses to one line; two Effective-Low members appear as one reorder line with latest prices comparable; On Order / recent receipt on any member marks the whole group (FR64/H1).

---

## E. Brownfield Verification Notes (from the finalize gate)

Spot-checked against the actual codebase during review; recorded so the architect starts from facts, not assumptions.

- **Location/vendor autocomplete reuse (FR27): accurate but one-directional today.** `GET /api/inventory/field-suggestions/<field>` exists (`app/main/routes.py`) and serves `location`, `sub_location`, `vendor`, `purchase_location`, `thread_size` via `app/static/js/field-autocomplete.js`, with sub-location scoped by parent location. Suggestions are drawn from existing metal-stock rows, so Products' own new locations won't feed back into autocomplete unless the endpoint's source query is extended to union Product rows (PRD FR27 assumption).
- **SATO media (FR43/§6): present.** `LABEL_TYPES` in `app/services/label_printer.py` already defines `Sato 1x2`, `Sato 2x4`, `Sato 4x6`, submitted via `LpPrinter`. The media/`lp` submission claim holds; FR43's job is to *not emit* 4×6 catalog labels, not to add the media.
- **2D barcode rendering (FR12/FR44): NOT present — the real gap.** The existing generators (`BarcodeLabelGenerator`, `FlagModeGenerator` via `pt_p710bt_label_maker`) are 1D only; no DataMatrix/QR/PDF417 library appears in `app/` or `requirements.txt`. Rendering the GS1 DataMatrix is a new capability + likely a new dependency (PRD FR42, Q7 spike). This is the load-bearing brownfield fact behind FR42/NFR9.

---

## F. Finalize Reviewer Gate — disposition summary

Both reviews are retained in full at `review-rubric.md` and `review-adversarial-general.md`. Rubric verdict: **strong on all seven dimensions, 0 critical/high**. Adversarial verdict: **3 critical / 4 high / 7 medium / 6 low**, several codebase-verified. Disposition:

- **Applied as spec fixes** (intent-aligned, non-discretionary): C2 (ASIN de-dup), C3+M4 (stored-vs-derived stock status), H1 (group on-order propagation), H2+L5 (1D→2D label reality, Q7 spike), H4 (GTIN_UNVALIDATED), M1/M2/M3/M5/M6/M7, L2/L3/L4/L6, and the rubric nits (Specifications glossary term, §4.5 cross-ref, assumptions-index alignment).
- **Resolved by user decision:** C1 (equivalence narrowed to same-part class → NG11, Q8 closed); H3 (accept capture-time price as paid, order date defaults to capture date → RISK-6).
- **Carried as open questions / spikes:** Q1 (scanner 2D round-trip), Q2 (attachment storage + XOR invariant), Q7 (2D rendering) — all in PRD §12.
