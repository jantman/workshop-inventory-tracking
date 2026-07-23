---
id: SPEC-product-catalog
companions:
  - '../../planning-artifacts/prds/prd-workshop-inventory-tracking-2026-07-21/prd.md'
  - '../../planning-artifacts/prds/prd-workshop-inventory-tracking-2026-07-21/addendum.md'
  - '../../planning-artifacts/architecture/architecture-workshop-inventory-tracking-2026-07-22/ARCHITECTURE-SPINE.md'
  - '../../project-context.md'
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Consult a companion for the detail this kernel cites by ID: the **PRD** (`prd.md`) holds the 64 FRs with testable consequences, the named user journeys, and the glossary; the **addendum** holds the provisional epic/story decomposition, the ECIA/GS1 reference notes, the indicative data model, and brownfield verification; the **architecture spine** holds decisions **AD-1…AD-17**, the consistency conventions, the stack, and all diagrams; **project-context.md** holds the existing app's conventions. Capabilities cite `FR-n` (PRD) and `AD-n` (spine) so downstream stories trace to both.

# Product Catalog & Purchase Tracking

## Why

A **pain** and a **vision**, for the single operator of this hobby workshop. The shop holds tens of thousands of items; the problem was never inventory control — it is **identification**. Today, when a part is unboxed, its metadata is re-derived by hand from a vendor product page (which may have changed or vanished), typed onto a printed label, and the data is thrown away — only the adhesive copy survives. This work is deliberately being made durable: every item acquired *from now on* should be identifiable — what it is, its key Specifications, where it came from, what it cost — from its physical label alone, offline, with no live vendor page, and any barcode in the shop should resolve to its record in a single scan. This is a bounded, brownfield enhancement to the existing `workshop-inventory-tracking` Flask app, reusing its database, API, label printing, and scanner integration.

## Capabilities

- **CAP-1 — Product & Purchase catalog**
  - **intent:** The operator can record Products (distinct from Purchases) carrying a Label Description, Specifications, identifiers, and full purchase history, creatable from a Label Description alone.
  - **success:** A Product persists with zero Purchases and only a description; a Product with three Purchases across two vendors shows chronological history with the last-paid price distinguished. *(FR1–6, FR18–22; AD-1, AD-2, AD-3)*

- **CAP-2 — Identifier system & internal encoding**
  - **intent:** The operator can reach a Product by any identifier on it, its packaging, or its vendor's label, and every Product gets a collision-proof generated internal identifier.
  - **success:** GTIN-8/UPC-A/EAN-13/GTIN-14 forms of one product resolve identically; a bad check digit is quarantined as `GTIN_UNVALIDATED` and cannot block a real GTIN; each Product gets a GS1 AI-96 `WIT` DataMatrix that cannot collide with a GTIN or ECIA payload. *(FR7–12d; AD-4, AD-7, AD-8, AD-16)*

- **CAP-3 — Taxonomy & tagging**
  - **intent:** The operator can classify Products into an accreting materialized-path category tree plus cross-cutting tags, both created inline.
  - **success:** Typing a new path creates and assigns it; renaming a segment moves its descendants (a sibling-collision rename is rejected); a tag filter returns the correct subset independent of category. *(FR13–17; AD-4)*

- **CAP-4 — Scan routing & ECIA parsing**
  - **intent:** Any barcode in the shop resolves correctly from one keyboard-wedge scan.
  - **success:** Internal-ID, ECIA format-06, GTIN (8 or 12–14 digit), and free-text inputs each route to the right handler; a DigiKey DataMatrix yields `P,1P,Q,K,1K,9D`; a malformed envelope surfaces the raw scan and never errors; an unknown scan lands on a pre-filled create form. *(FR35–41; AD-5, AD-15, AD-16)*

- **CAP-5 — Optional stock tracking & reorder signals**
  - **intent:** The operator can track quantity and location only where worthwhile, with honest staleness, and see one unified reorder view.
  - **success:** Tri-state quantity renders three distinct strings; Effective Low derives from quantity ≤ threshold *without* writing stored status; receiving a Purchase clears a manual low without flip-flop and without touching quantity; the reorder view unifies manual and derived signals with on-order marked. *(FR23–34; AD-6)*

- **CAP-6 — Label generation & printing**
  - **intent:** The operator can generate durable 2×4/1×2 labels from records via the existing print path, reprintable and dual-encoded.
  - **success:** A label renders the Label Description, Provenance Block, a GS1 DataMatrix, and human-readable id through the existing `print_images` seam; rendering is deterministic; reprint needs no re-entry; the catalog feature never emits a 4×6 label. *(FR42–47; AD-8, AD-11, AD-16)*

- **CAP-7 — Order-time capture**
  - **intent:** The operator can capture vendor, SKU, title, and price at order time via an Amazon-only bookmarklet + REST endpoint, de-duping to existing Products, idempotently.
  - **success:** A capture creates a Product+Purchase or attaches to an existing Product on identifier / vendor-SKU match; a repeat ASIN does not create a duplicate; the same `request_key` returns the original record; the capture-time price is recorded as paid and order date defaults to the capture date. *(FR48–51, FR49a; AD-9, AD-13)*

- **CAP-8 — Equivalent products**
  - **intent:** The operator can declare same-part brand-relabels as one Equivalent Product Group for reorder and price comparison.
  - **success:** Adding Product B to Product A's group makes both symmetric members (a cross-group add is rejected); the group collapses to one reorder line; an inbound order or recent receipt on any member suppresses the whole group. *(FR62–64; AD-10)*

- **CAP-9 — Search & retrieval**
  - **intent:** The operator can full-text search across catalog text and identifiers, filter by facet with a bookmarkable URL, and open a Product by direct URL.
  - **success:** A term appearing in description/notes/MPN/identifier returns the Product; faceting by category-prefix / tag / stock-status narrows results in a bookmarkable URL; the internal-id URL opens the Product. *(FR52–55; AD-17)*

- **CAP-10 — Attachments**
  - **intent:** The operator can attach datasheets, wiring diagrams, or photos to a Product or a Purchase.
  - **success:** A PDF attached to a Product is retrievable from the Product view; every Attachment references exactly one owner (Product XOR Purchase). *(FR5; AD-12)*

- **CAP-11 — Handheld & touch readiness**
  - **intent:** Every action is reachable by touch, the scan-result view is self-sufficient at handheld width, and in-progress form state survives network drops.
  - **success:** At 360 px a resolved scan shows identity, Specifications, location, and status and allows quantity + status changes inline; a partially composed description survives a dropped-and-restored connection; nothing depends on hover or a physical keyboard. *(FR56–59; AD-15)*

- **CAP-12 — Extensibility hooks**
  - **intent:** Product enrichment sits behind one internal interface (no-op this phase), and creation requires no field unavailable during manual/backfill entry.
  - **success:** Creation invokes the Enrichment Interface (the no-op returns an empty partial record and creation is unchanged); every required creation field is obtainable for a pre-existing item with no order. *(FR60–61; AD-2, AD-13)*

## Constraints

- Delivered **inside the existing Flask app** — no new services or containers; ships in the existing Docker image on the Raspberry Pi 5, sharing MariaDB, auth, and backups. *(NFR1)*
- **Existing metal-stock functionality is unaffected**: shared schema is not restructured; shared vocabularies (location, vendor) are reused by extending the `field-suggestions` source, never forked. All schema changes are Alembic migrations chained from HEAD `8213852b0b94`; no `create_all`. *(NFR3, NFR9; AD-14)*
- Schemaless Specifications use a **MariaDB JSON** column; no new datastore. *(NFR2)*
- Identifier normalization, encoding/decoding, and scan classification are **pure, exhaustively-tested functions** — a single source of truth per concern, no Flask/DB imports. *(NFR7; AD-4)*
- Labels print on **direct-thermal 2×4 and 1×2 only** (4×6 reserved for shipping), with dual barcode + human-readable encoding for durability and deterministic rendering. *(NFR11)*
- The **GS1 DataMatrix is rendered by pyStrich** (pure-Python, no system dependency on the Pi); `treepoem`+Ghostscript is the documented fallback.
- The REST API stays **consumable by the requests-only standalone client** with no added dependencies. *(NFR10)*
- A **single responsive Bootstrap 5.3.2 codebase** renders acceptably from 360 px to the 21.5″ cart display. *(NFR4)*
- **No LLM generation** of label descriptions or Specifications — model use is confined to the read/search path. *(RISK-1)*
- Architecture decisions **AD-1…AD-17** (see the spine companion) are binding; downstream stories cite them by their stable IDs.

## Non-goals

- No bulk-backfill tooling — no importer, CSV ingest, or bulk-entry UI (ad-hoc manual entry of existing items still works). *(NG1)*
- No mandatory quantity tracking or consumption-event logging. *(NG2)*
- Not replacing Trello for shipment tracking; no carrier-tracking integration. *(NG3)*
- No automated or unattended scraping of Amazon product pages. *(NG4)*
- No LLM-generated label descriptions or specifications. *(NG5)*
- No document store / NoSQL — schemaless data uses MariaDB JSON. *(NG6)*
- No vendor-API integration (DigiKey/Mouser/McMaster) for enrichment — the interface ships a no-op only. *(NG7)*
- No separate mobile UI codebase. *(NG8)*
- No offline operation with local persistence and sync. *(NG9)*
- No user-defined internal part-numbering scheme. *(NG10)*
- No substitutability graph — only the same-part "differently branded" equivalence class. *(NG11)*
- The **4×6 label template** and a **multi-vendor bookmarklet** are out of scope for this phase (Amazon-only capture; distributor labels captured by physical scan).

## Success signal

I keep using the catalog weekly and don't abandon it after a month; every label-worthy item I acquire after launch gets a durable Product record before it is shelved — rather than being hand-transcribed from a vendor page — and is identifiable from its physical label alone, offline and with no live vendor page, via a single scan that resolves to the right record. Counter-signals to respect, not optimize: do **not** chase catalog completeness of the pre-existing inventory, and do **not** grow quantity-tracking coverage broadly (inaccurate counts are worse than none).

## Assumptions

- "Label-worthy" ≈ the roughly half of received items that today get a hand-printed label; distributor-labeled items are catalogued for search/reorder but need no printed label.
- Order-time capture happens at or near ordering, so the capture-time listing price ≈ the price paid and order date defaults to the capture date (both remain editable).
- The existing `field-suggestions` autocomplete source is extended to include Product locations, making the location/vendor vocabulary bidirectional (today it draws from metal-stock rows only).

## Open Questions

- **Q1 (blocking spike, gates CAP-4):** Does the Tera HW0009 scanner round-trip a GS1 DataMatrix `WIT…` payload recognizably — data characters intact, whether it transmits FNC1 as GS (0x1D), a substitute character, or stripped, and whether it emits the AIM `]d1` identifier? Resolve before building the internal-ID scan path.
- **Q7 (blocking spike, gates CAP-6):** Does pyStrich's ~6-week-old GS1 output scan and verify as a valid GS1 DataMatrix on a real printed sample? If not, fall back to `treepoem`+Ghostscript. Resolve before label work.
