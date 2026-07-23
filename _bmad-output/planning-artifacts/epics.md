---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - '_bmad-output/specs/spec-product-catalog/SPEC.md'
  - '_bmad-output/planning-artifacts/prds/prd-workshop-inventory-tracking-2026-07-21/prd.md'
  - '_bmad-output/planning-artifacts/prds/prd-workshop-inventory-tracking-2026-07-21/addendum.md'
  - '_bmad-output/planning-artifacts/architecture/architecture-workshop-inventory-tracking-2026-07-22/ARCHITECTURE-SPINE.md'
  - '_bmad-output/project-context.md'
---

# Product Catalog & Purchase Tracking - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for the Product Catalog & Purchase Tracking enhancement (brownfield, inside the existing `workshop-inventory-tracking` Flask app), decomposing the PRD's 64 functional requirements and the Architecture spine's 17 decisions (AD-1…AD-17) into implementable stories. There is no separate UX design contract — the UI is the existing Bootstrap 5.3.2 codebase, and handheld/touch requirements are captured as FRs.

## Requirements Inventory

### Functional Requirements

**Product Catalog (CAP-1)**
- FR1: Product records are distinct from Purchase records; one Product has zero or more Purchases.
- FR2: A Product carries manufacturer, MPN, Label Description, notes, Specifications (`attributes`), and a Category.
- FR3: Manufacturer and MPN are both optional.
- FR4: A Product is creatable with no Purchase (supports opportunistic backfill).
- FR5: Files (datasheets, diagrams, photos) attach to a Product or a Purchase — exactly one owner.
- FR6: Products are editable at any time; Label Description edits don't invalidate prior prints but are reflected in later prints.

**Identifiers & Internal Encoding (CAP-2)**
- FR7: Multiple typed Identifiers per Product (`GTIN`, `GTIN_UNVALIDATED`, `ASIN`, `FNSKU`, `MPN`, `VENDOR_SKU`, `INTERNAL`); `internal_id` authoritative.
- FR8: `(type, value)` is unique per its scope.
- FR9: GTIN normalized to 14 digits (GTIN-8/UPC-A/EAN-13/GTIN-14 resolve identically).
- FR10: GTIN check-digit validated on entry; failures storable as `GTIN_UNVALIDATED` (unnormalized, outside GTIN namespace).
- FR11: ASIN recorded on the Purchase as Vendor SKU and indexed as an `ASIN` identifier for de-dup; product identity never depends on it.
- FR12: System-generated internal identifier encoded as a GS1 DataMatrix carrying AI 96.
- FR12a: AI-96 data field = token `WIT` + internal id (self-identifying; foreign AI-96 without `WIT` is rejected).
- FR12b: AI 96 is the sole element string; FNC1 first position; no separator; no second AI.
- FR12c: The AI number (`96`) and token (`WIT`) are configuration values, not literals.
- FR12d: Ownership/return info is human-readable label text only (no 43xx element strings).

**Taxonomy & Tagging (CAP-3)**
- FR13: Materialized-path Category tree of arbitrary depth (e.g. `electronics/power/dc-dc-converters`).
- FR14: Categories creatable inline via autocomplete-with-create.
- FR15: No pre-populated taxonomy; the tree accretes from use.
- FR16: Zero or more free-form Tags per Product, independent of Category.
- FR17: Category paths editable; descendants + assigned Products follow the rename; sibling collision rejected.

**Purchases (CAP-1)**
- FR18: A Purchase carries product ref, vendor, Vendor SKU, order date, nullable received date, quantity, unit price, order number, source URL.
- FR19: Null received date = order in flight (On Order).
- FR20: Full Purchase history per Product in chronological order (date/vendor/price).
- FR21: Most recent prior unit price surfaced in a labeled field ("Last paid").
- FR22: Purchases creatable via REST API (order-time capture).

**Optional Quantity & Location (CAP-5)**
- FR23: Tri-state Quantity On Hand (`NULL`=untracked / `0`=tracked-none / `N`); three distinct render strings.
- FR24: Quantity defaults to `NULL`; tracking is opt-in per Product.
- FR25: `quantity_verified_at` set on manual assertion; its age displayed; receipt never modifies quantity.
- FR26: Optional integer Reorder Threshold per Product.
- FR27: Optional location/sub-location reusing the existing location autocomplete vocabulary.

**Stock Status & Reorder Signals (CAP-5)**
- FR28: Stored Stock Status (`unknown`|`ok`|`low`|`out`, default `unknown`) holds only manual assertions.
- FR29: Manual status settable, including flagging untracked Products low/out.
- FR30: Effective Low derived when tracked quantity ≤ threshold (NULL threshold → false); never writes stored status.
- FR31: Timestamp recorded when manual status set; age displayed.
- FR32: On Order derived (unreceived Purchase on the Product or any group sibling); never stored.
- FR33: Receipt clears only a manual `low`/`out` → `ok` (product-scoped); never touches quantity; never fights derived Effective Low.
- FR34: Single reorder view: all Effective-Low Products, On-Order marked, Equivalent Product Groups collapsed to one line.

**Scanning & Scan Routing (CAP-4)**
- FR35: Keyboard-wedge scanner input, no scanner-specific driver.
- FR36: Structural routing precedence: (1) AI-96+token → internal; (2) ISO/IEC 15434 format-06 → ECIA; (3) 8 or 12–14 digits w/ valid check digit → GTIN (fall through to free-text on no match); (4) else → free-text.
- FR37: AIM symbology identifiers narrow the symbology class only; structural inspection selects the handler (AIM not emitted by the deployed scanner — optional path).
- FR37a: FNC1 transmission tolerance (GS 0x1D / substitute / stripped); deployed scanner strips FNC1 → recognize by `96WIT` prefix.
- FR38: Parse ECIA MH10.8.2 (format-06) barcodes; extract `P`, `1P`, `Q`, `K`, `1K`, `9D`/`10D`.
- FR39: Parsed ECIA fields pre-populate a create form; all values editable.
- FR40: A scan matching no record opens a pre-filled create form with the identifier attached/typed — never an error page.
- FR41: A scan resolving to an existing Product in a receiving context offers to add a Purchase; duplicate creation requires explicit confirmation.

**Label Generation & Printing (CAP-6)**
- FR42: Reuse the existing `lp` submission path; add GS1 DataMatrix (2D) rendering (pyStrich); no new print/submission path.
- FR43: 2×4 and 1×2 templates only; never emit a 4×6 catalog label.
- FR44: Label content = Label Description + Provenance Block (vendor, order date, Vendor SKU, unit price) + GS1 DataMatrix.
- FR45: Internal Identifier appears in both barcode and human-readable form.
- FR46: Any label reprintable on demand from its Product record with no re-entry.
- FR47: Canonical field order; Provenance Block last, structurally consistent.

**Order-Time Capture (CAP-7)**
- FR48: Capture payload = vendor, Vendor SKU, listing title, unit price, quantity, source URL, optional order date (defaults to capture date).
- FR49: Listing title populates the Label Description as an editable draft.
- FR49a: Optional authored Label Description in the payload replaces the title draft; editable at receipt.
- FR50: De-dup — attach to an existing Product when Vendor SKU matches an existing Identifier OR a prior `purchases.vendor_sku` (vendor-scoped); index ASIN on first sight.
- FR51: Idempotent creation on a client `request_key` (same key returns the original record).

**Search & Retrieval (CAP-9)**
- FR52: Full-text search across Label Descriptions, notes, manufacturer, MPN, all Identifier values.
- FR53: Filter by Category path prefix, Tag, and Effective-Low/Stock Status.
- FR54: URL-bookmarkable search state.
- FR55: Product detail reachable by direct URL keyed on `internal_id`.

**Handheld & Touch Readiness (CAP-11)**
- FR56: Every keyboard-shortcut action has a touch-reachable equivalent.
- FR57: Self-sufficient scan-result view at handheld width (identity, Specifications, location, status; inline quantity + status changes).
- FR58: No interaction depends on hover or a physical keyboard.
- FR59: In-progress form state persists client-side across network drops.

**Extensibility Hooks (CAP-12)**
- FR60: Enrichment behind a single internal interface (typed Identifiers in, partial Product out); no-op implementation only this phase.
- FR61: REST creation requires no field unavailable during manual/backfill entry.

**Equivalent Products (CAP-8)**
- FR62: Declare a Product into an Equivalent Product Group (same manufacturer part, differently branded); symmetric membership; cross-group add rejected.
- FR63: A Product's detail view lists its equivalents with manufacturer/MPN and latest price.
- FR64: Reorder view collapses a group to one line; On Order/recent receipt on any member suppresses the whole group.

### NonFunctional Requirements

- NFR1: Delivered inside the existing Flask app; no new services or containers.
- NFR2: Schemaless Specifications use a MariaDB JSON column; no new datastore.
- NFR3: All schema changes are Alembic migrations (via `manage.py db`), not `create_all`.
- NFR4: Single responsive Bootstrap 5.3.2 codebase, 360 px → 21.5″.
- NFR5: Fully usable for identification with quantity tracking entirely unused.
- NFR6: Unit coverage consistent with the existing suite + E2E for scan-routing and label paths.
- NFR7: Identifier normalization/encoding/routing are pure functions with exhaustive unit tests.
- NFR8: ECIA parser degrades gracefully on malformed input (surface raw scan, never raise).
- NFR9: Metal-stock functionality unaffected; shared schema not restructured; label subsystem extended, not forked.
- NFR10: REST API remains consumable by the `requests`-only standalone client with no added deps.
- NFR11: Label rendering deterministic — same record → identical raster.

### Additional Requirements

*From the Architecture spine (AD-1…AD-17), stack, and resolved spikes. These shape story structure and acceptance criteria; each cites the governing AD.*

- **No starter template** — brownfield. Epic 1 Story 1 is the entity migration + foundation, not a greenfield scaffold.
- **Layered structure (AD-1, AD-2):** route → `mariadb_catalog_service.py` (new) → enhanced-ORM models on shared `Base`; no ORM/SQL in routes; routes build the `{success,…}` envelope. Entities follow the single-enhanced-ORM-class + value-object-dataclass pattern (`@hybrid_property`/`@property`).
- **Keys (AD-3):** integer surrogate PKs; `products.internal_id` is a unique business key (URLs/labels/scan), never a join FK target.
- **Pure utils (AD-4, NFR7):** `app/utils/gtin.py`, `internal_id.py`, `gs1.py`, `scan_router.py`, `category.py` — no Flask/DB imports, exhaustive unit tests.
- **Scan seam (AD-5, AD-15):** pure `scan_router.classify()` → frozen `ScanClassification`; `mariadb_catalog_service.resolve_scan()` → frozen `ScanResolution` (DB lookup + free-text fallthrough); shapes in `app/models.py`.
- **Derived stock (AD-6):** stored status = manual only; Effective Low / On Order / Recently Received computed at read; Effective-Low predicate single-sourced (one hybrid/service method Epic 8's facet reuses); NULL-threshold rule explicit.
- **GTIN namespace (AD-7):** normalized-14 validated GTINs are the uniqueness namespace; `GTIN_UNVALIDATED` quarantined.
- **Internal id + grammar (AD-8, AD-16):** `internal_id.py` yields a candidate; the create-service is the sole writer with UNIQUE-collision retry; GS1 grammar single-sourced in `gs1.py` (`encode` + `decode`); one config pair `GS1_INTERNAL_AI`/`GS1_INTERNAL_TOKEN` passed to both; no literal defaults.
- **Capture de-dup (AD-9):** per-type scope (GTIN/INTERNAL global; VENDOR_SKU/ASIN/FNSKU vendor-scoped); ASIN match is confirm-not-merge when manufacturer/MPN differ; `request_key` UNIQUE; idempotent unit = whole capture transaction; UNIQUE violations caught as domain errors.
- **Equivalence (AD-10):** nullable `equivalent_group_id` FK partition (≤1 group/product); cross-group add rejected; group reorder-line = all members Effective-Low AND none On Order AND none Recently Received.
- **Labels (AD-11):** new `LABEL_TYPES` entries (2×4, 1×2) + new generator branch compositing the pyStrich DataMatrix + description + provenance into one raster, submitted via the unchanged `LpPrinter.print_images()`; deterministic.
- **Attachments (AD-12):** BLOB-in-DB; `CHECK ((product_id IS NULL) <> (purchase_id IS NULL))`.
- **API client parity (AD-13, NFR10):** each new programmatic endpoint gets a matching method + frozen result dataclass in `app/api_client.py`; JSON routes `@csrf.exempt`; fixed error envelope `{success:false, error:{code, message, field?}}`.
- **Migrations (AD-14):** Alembic chained from HEAD `8213852b0b94`; metal stock untouched; extend the `field-suggestions` source query/whitelist (don't fork).
- **Single search entrypoint (AD-17):** `mariadb_catalog_service.search_products()` is the sole free-text search; both the scan fallthrough and Epic-8 search call it. Search *mechanism* (LIKE vs FULLTEXT) decided in Epic 8.
- **Category convention:** canonical `category_path` = lowercase, `/`-separated, no leading/trailing slash; segment-boundary prefix match via a shared `normalize_category_path()`.
- **Enrichment (FR60):** `app/services/product_enrichment.py`, no-op, called on the create path.
- **New dependency:** add `pyStrich[png]` (0.19, pure-Python GS1 DataMatrix) to `requirements.txt` in the label epic. **Both spikes resolved** — no spike stories: pyStrich confirmed; scanner strips FNC1 / no AIM, so scan routing keys on the `96WIT` prefix.

### UX Design Requirements

None — no separate UX design contract. The UI is the existing Bootstrap 5.3.2 codebase; handheld/touch needs are covered by FR56–FR59 (governed by NFR4 + AD-15) and realized in templates/static during the relevant epics.

### FR Coverage Map

- FR1–FR6: Epic 1 — product/purchase entities, optional fields, attachments, editability
- FR7–FR12d: Epic 2 — typed identifiers, GTIN normalize/validate, internal id + GS1 AI-96 encoding
- FR13–FR17: Epic 3 — materialized-path categories, inline create, tags, rename
- FR18–FR22: Epic 1 — purchase entity, in-flight orders, history, last-paid, REST create
- FR23–FR27: Epic 5 — tri-state quantity, staleness, threshold, location
- FR28–FR34: Epic 5 — stored-vs-derived stock, Effective Low, On Order, reorder view
- FR35–FR41 (incl. FR37a): Epic 4 — wedge input, structural routing, ECIA parse, unknown/duplicate handling
- FR42–FR47: Epic 6 — label rendering via existing lp path + pyStrich DataMatrix, dual encoding, reprint
- FR48–FR51 (incl. FR49a): Epic 7 — capture payload, draft/authored description, de-dup, idempotency
- FR52–FR55: Epic 8 — full-text search, faceted filter, bookmarkable state, direct-URL views
- FR56–FR59: Epic 9 — touch equivalents, self-sufficient scan-result view, form-state persistence
- FR60: Epic 7 — enrichment interface (no-op) on the create path
- FR61: Epic 1 — creation requires no backfill-hostile field
- FR62–FR64: Epic 10 — equivalence group, equivalents display, reorder collapse

## Epic List

### Epic 1: Product & Purchase Foundation
Establish Products and Purchases as first-class entities alongside metal stock, with CRUD, detail views, file attachments, and purchase history — a usable catalog on its own. Realizes the backfill-forward creation shape (FR61) and the BLOB attachment model (AD-12).
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR18, FR19, FR20, FR21, FR22, FR61

### Epic 2: Identifiers & Internal Encoding
Make a Product reachable by any identifier on it, its packaging, or its vendor's label, and give every Product a collision-proof generated internal identifier encoded as a GS1 DataMatrix (AI 96 + `WIT`). Pure, exhaustively-tested normalization/encoding (AD-4/7/8/16).
**FRs covered:** FR7, FR8, FR9, FR10, FR11, FR12, FR12a, FR12b, FR12c, FR12d

### Epic 3: Taxonomy & Tagging
Let the operator classify Products into an accreting materialized-path category tree and cross-cutting tags, all created inline — no taxonomy designed up front.
**FRs covered:** FR13, FR14, FR15, FR16, FR17

### Epic 4: Scan Routing & ECIA
Any barcode in the shop resolves correctly from a single keyboard-wedge scan, via a pure classifier + service resolution (AD-5/15), with ECIA distributor-label parsing and graceful degradation.
**FRs covered:** FR35, FR36, FR37, FR37a, FR38, FR39, FR40, FR41

### Epic 5: Stock Tracking & Reorder Signals
Track quantity and location only where worthwhile, with honest staleness; derive Effective Low / On Order / Recently Received at read (never stored), and surface one unified reorder view.
**FRs covered:** FR23, FR24, FR25, FR26, FR27, FR28, FR29, FR30, FR31, FR32, FR33, FR34

### Epic 6: Label Generation & Printing
Generate durable 2×4/1×2 labels from records via the existing `lp` submission path plus a new pyStrich GS1 DataMatrix render step, dual-encoded and reprintable (AD-11).
**FRs covered:** FR42, FR43, FR44, FR45, FR46, FR47

### Epic 7: Order-Time Capture
Capture vendor, SKU, title, and price at order time via an Amazon bookmarklet + REST endpoint, de-duping to existing Products and idempotent on a request key; enrichment behind a no-op hook (AD-9/13).
**FRs covered:** FR48, FR49, FR49a, FR50, FR51, FR60

### Epic 8: Search & Retrieval
Full-text search across catalog text and identifiers, faceted by category/tag/stock-status with bookmarkable URLs, and direct-URL product views — via the single shared search entrypoint (AD-17).
**FRs covered:** FR52, FR53, FR54, FR55

### Epic 9: Handheld & Touch Readiness
Make every action touch-reachable, the scan-result view self-sufficient at handheld width, and in-progress form state resilient to network drops (NFR4, AD-15).
**FRs covered:** FR56, FR57, FR58, FR59

### Epic 10: Equivalent Products
Declare same-part brand-relabels into one Equivalent Product Group (partition, cross-group add rejected) and surface it in the product view and the reorder collapse (AD-10).
**FRs covered:** FR62, FR63, FR64

---

## Epic 1: Product & Purchase Foundation

Establish Products and Purchases as first-class entities alongside metal stock, with CRUD, detail views, file attachments, and purchase history — a usable catalog on its own.

### Story 1.1: Product entity and migration

As the workshop operator,
I want a Product table and domain model created alongside metal stock,
So that the catalog has a place to store products without disturbing existing inventory.

**Acceptance Criteria:**

**Given** the app running against the existing database at Alembic HEAD `8213852b0b94`
**When** the new migration is applied
**Then** a `products` table exists with an integer surrogate PK and columns for manufacturer, mpn, description (Label Description), notes, category_path, attributes (JSON), and timestamps (FR2)
**And** the Product ORM class lives on the shared `Base` in `app/database.py` following the enhanced-ORM pattern (AD-1), with any value objects/enums in `app/models.py`
**And** existing metal-stock tables and behavior are unchanged (NFR9), and `manage.py db downgrade` cleanly reverses the migration

### Story 1.2: Purchase entity and migration

As the workshop operator,
I want a Purchase table linked to Products,
So that I can record acquisitions, including orders still in flight.

**Acceptance Criteria:**

**Given** the Product table exists
**When** the Purchase migration is applied
**Then** a `purchases` table exists with an integer PK, a `product_id` FK to `products.id` such that one Product has zero or more Purchases (FR1, AD-3), and vendor, vendor_sku, order_date, nullable received_date, quantity, unit_price, order_number, source_url, and a `request_key` column with a UNIQUE constraint (AD-9)
**And** a Purchase can be created with a null `received_date` (FR19)

### Story 1.3: Product create/edit/detail

As the workshop operator,
I want to create, edit, and view a Product from the cart UI,
So that I can catalog an item with as little or as much detail as I have.

**Acceptance Criteria:**

**Given** the product form
**When** I create a Product with only a Label Description and no other fields
**Then** it saves successfully with manufacturer, mpn, category, and all optional fields empty (FR3, FR4)
**And** the creation requires no field that would be unavailable for a pre-existing item with no order (FR61)

**Given** an existing Product
**When** I edit its Label Description and save
**Then** the change persists and its detail view is reachable by direct URL (FR6)

### Story 1.4: Purchase recording and history

As the workshop operator,
I want to record purchases against a Product and see their history,
So that I can tell what I paid and where, over time.

**Acceptance Criteria:**

**Given** a Product with three Purchases across two vendors
**When** I open the Product detail view
**Then** all Purchases list in chronological order with date, vendor, and unit price (FR20)
**And** the most recent prior unit price is shown in a labeled "Last paid" field (FR21)

**Given** I am recording a new Purchase via the service/REST path
**When** I submit it
**Then** a Purchase is created and attached to the Product (FR18, FR22)

### Story 1.5: Attachments on product or purchase

As the workshop operator,
I want to attach datasheets, diagrams, or photos to a Product or a Purchase,
So that reference material lives with the record and survives with my backups.

**Acceptance Criteria:**

**Given** a Product detail view
**When** I upload a PDF datasheet
**Then** the file is stored as a BLOB in the database (AD-12) and is retrievable from the Product view (FR5)

**Given** the attachments table
**When** a row is written
**Then** exactly one of `product_id` / `purchase_id` is non-null, enforced by a CHECK/application invariant (both-null or both-set is rejected)

---

## Epic 2: Identifiers & Internal Encoding

Make a Product reachable by any identifier, and give every Product a collision-proof generated internal identifier encoded as a GS1 DataMatrix.

### Story 2.1: Typed identifier entity and uniqueness

As the workshop operator,
I want to store multiple typed identifiers per Product,
So that I can look a product up by whatever code is printed on it.

**Acceptance Criteria:**

**Given** a Product
**When** I add identifiers of type GTIN, ASIN, FNSKU, MPN, VENDOR_SKU, or INTERNAL
**Then** each persists in `product_identifiers` with its type (FR7)

**Given** an identifier `(type, value)` already exists on another Product
**When** I try to add the same pair
**Then** it is rejected as a caught domain error naming the conflicting Product (FR8), not a raw IntegrityError

### Story 2.2: GTIN normalization and check-digit validation

As the workshop operator,
I want GTINs normalized and validated,
So that the same product resolves identically however its barcode was encoded, and bad values can't corrupt the namespace.

**Acceptance Criteria:**

**Given** the pure `app/utils/gtin.py` module (no Flask/DB imports, exhaustive unit tests — AD-4, NFR7)
**When** I store or look up GTIN-8, UPC-A (12), EAN-13 (13), or GTIN-14 forms of one product
**Then** all normalize to the same 14-digit key and resolve to the same Product (FR9)

**Given** a value whose GTIN check digit is invalid
**When** I submit it
**Then** it is rejected as a GTIN with a clear message and an option to store it as `GTIN_UNVALIDATED` (unnormalized, outside the GTIN namespace), so it cannot block a later valid GTIN (FR10, AD-7)

### Story 2.3: ASIN identity handling

As the workshop operator,
I want ASINs recorded on purchases and indexed for lookup,
So that repeat Amazon buys find the same product without ASIN reuse corrupting identity.

**Acceptance Criteria:**

**Given** a captured Amazon purchase
**When** it is stored
**Then** the ASIN is recorded on the Purchase as `vendor_sku` and additionally indexed as an `ASIN` identifier (FR11)
**And** the Product's identity does not depend on the ASIN (a reassigned ASIN does not change which product is which)

### Story 2.4: Internal identifier generation and GS1 AI-96 encoding

As the workshop operator,
I want each Product to get a unique internal identifier encoded as a GS1 DataMatrix,
So that my own labels scan back to the right product and can never collide with a vendor barcode.

**Acceptance Criteria:**

**Given** a new Product
**When** it is saved
**Then** `internal_id.py` yields a candidate and the create-service is the sole writer, inserting it with retry-on-UNIQUE-collision and no DB default (AD-8); the column is UNIQUE
**And** `app/utils/gs1.py` `encode()` produces a single GS1 element string: FNC1 first, AI `96`, data field `WIT` + internal_id, no separator (FR12, FR12a, FR12b)
**And** the AI number and token come from one config pair (`GS1_INTERNAL_AI`, `GS1_INTERNAL_TOKEN`), not literals (FR12c, AD-16)

### Story 2.5: Foreign-payload rejection and ownership text

As the workshop operator,
I want foreign AI-96 payloads rejected and ownership info kept human-readable,
So that a coincidental barcode never resolves to one of my products.

**Acceptance Criteria:**

**Given** `gs1.decode()`
**When** it receives an AI-96 element string whose data field does not begin with the configured `WIT` token
**Then** it does not treat it as an internal identifier (FR12a)

**Given** a generated label
**When** it is rendered
**Then** no 43xx element string is encoded; any ownership/return text appears only in the human-readable region (FR12d)

---

## Epic 3: Taxonomy & Tagging

Classify Products into an accreting materialized-path category tree and cross-cutting tags, created inline.

### Story 3.1: Materialized-path categories with inline create

As the workshop operator,
I want to file a Product under a category path I type on the spot,
So that I can organize without designing a taxonomy first.

**Acceptance Criteria:**

**Given** no categories exist
**When** I type `electronics/power/dc-dc-converters` into the category field
**Then** it is normalized (lowercase, `/`-separated, no leading/trailing slash) via `normalize_category_path()` (AD-4), stored on the Product, and offered via autocomplete-with-create afterward (FR13, FR14, FR15)

### Story 3.2: Category rename with descendants

As the workshop operator,
I want renaming a category segment to carry its descendants,
So that reorganizing doesn't strand products.

**Acceptance Criteria:**

**Given** Products assigned under `electronics/power/`
**When** I rename that segment
**Then** all descendant paths and assigned Products follow the rename (FR17)

**Given** a rename that would collide with an existing sibling path
**When** I submit it
**Then** it is rejected with a message rather than silently merged

### Story 3.3: Free-form tags

As the workshop operator,
I want to tag Products independently of their category,
So that I can retrieve cross-cutting sets.

**Acceptance Criteria:**

**Given** three heat sinks under `thermal/heat-sinks`, two tagged `ssr` and one `rectifier` (stored in a `product_tags` table)
**When** I filter by the `ssr` tag
**Then** exactly the two tagged products are returned, independent of category (FR16)

---

## Epic 4: Scan Routing & ECIA

Any barcode resolves correctly from a single keyboard-wedge scan, via a pure classifier plus service resolution.

### Story 4.1: Wedge scan capture

As the workshop operator,
I want the scan field to capture a wedge scan on any page,
So that scanning just works without special drivers.

**Acceptance Criteria:**

**Given** the scan field has focus
**When** the Tera HW0009 emits a scan as keystrokes terminated by Enter
**Then** the raw text is captured and posted for routing with no scanner-specific driver or config (FR35)

### Story 4.2: Pure scan classifier

As the workshop operator,
I want scans classified by structure in a fixed precedence,
So that each kind of barcode is understood correctly and deterministically.

**Acceptance Criteria:**

**Given** the pure `app/utils/scan_router.py` classifier (no DB — AD-4/AD-5) returning a frozen `ScanClassification`
**When** it receives input
**Then** it applies FR36 precedence: (1) a `96WIT`-prefixed payload → `internal` (delegating recognition to `gs1.decode()`, tolerating stripped FNC1 — AD-16, FR37a); (2) an ISO/IEC 15434 format-06 envelope → `ecia`; (3) an all-digit value of length 8 or 12–14 with a valid GTIN check digit → `gtin` (normalized); (4) anything else → `free_text`
**And** an AIM `]d1` prefix, if ever present, only narrows the symbology class; the AI/token still selects the handler (FR37)

### Story 4.3: Service scan resolution

As the workshop operator,
I want a scan resolved to a product (or a search) in one step,
So that a scan lands me on the right screen.

**Acceptance Criteria:**

**Given** `mariadb_catalog_service.resolve_scan(raw)` returning a frozen `ScanResolution` (AD-15)
**When** a classification does not match a record
**Then** it falls through to a new shared `search_products()` service method — the single free-text search entrypoint (AD-17), covering identifiers, descriptions, notes, manufacturer, and MPN — introduced here and reused by Epic 8; never dead-ending
**And** a `gtin`/`internal` classification that matches resolves directly to that Product

### Story 4.4: ECIA distributor-label parsing

As the workshop operator,
I want DigiKey/Mouser 2D labels parsed,
So that receiving a distributor package pre-fills the record.

**Acceptance Criteria:**

**Given** a DigiKey format-06 DataMatrix
**When** it is parsed
**Then** `P`, `1P`, `Q`, `K`, `1K`, and `9D`/`10D` are extracted into named fields (FR38)

**Given** a malformed or unrecognized envelope
**When** parsing is attempted
**Then** the raw scan is surfaced for manual handling and no exception is raised (NFR8)

### Story 4.5: Scan outcome routing in the UI

As the workshop operator,
I want scans to land me on the right action,
So that I never hit an error page and never create accidental duplicates.

**Acceptance Criteria:**

**Given** a scan matching no record
**When** routing completes
**Then** a Product-creation form opens with the scanned identifier attached and its type inferred — never an error page (FR40)

**Given** a parsed distributor scan with no matching product
**When** the create form opens
**Then** MPN, quantity, and order references are pre-filled and every value remains editable (FR39)

**Given** a scan resolving to an existing Product in a receiving context
**When** routing completes
**Then** the system offers to add a Purchase to that Product, and creating a duplicate requires explicit confirmation (FR41)

---

## Epic 5: Stock Tracking & Reorder Signals

Track quantity and location only where worthwhile; derive reorder signals at read; surface one unified reorder view.

### Story 5.1: Tri-state quantity and location

As the workshop operator,
I want quantity tracking to be opt-in with an honest "untracked" state,
So that I track only what matters and never confuse "none" with "not tracked."

**Acceptance Criteria:**

**Given** a newly created Product
**Then** `quantity_on_hand` is `NULL` and renders as an untracked marker (e.g. "Not tracked"), distinct from `0` ("In stock: 0") and `N` ("In stock: N") — three distinct strings (FR23, FR24)

**Given** I manually assert a quantity
**When** I save
**Then** `quantity_verified_at` is set and its age is displayed alongside the quantity (FR25)

**Given** the location field
**When** I enter a location
**Then** it draws from the existing location autocomplete vocabulary (FR27)

### Story 5.2: Reorder threshold and derived Effective Low

As the workshop operator,
I want low stock derived from a threshold,
So that I don't have to flag it by hand where I'm tracking counts.

**Acceptance Criteria:**

**Given** a Product with tracked quantity 2, threshold 3, and stored status `ok`
**When** Effective Low is evaluated at read (single-sourced predicate — AD-6)
**Then** it is Effective Low, with no write to the stored `stock_status` (FR26, FR30)

**Given** a Product with a `NULL` reorder_threshold
**When** Effective Low is evaluated
**Then** the threshold branch is false (FR30)

### Story 5.3: Manual stock status

As the workshop operator,
I want to flag stock status by hand, even for untracked items,
So that I can mark something low without committing to counting it.

**Acceptance Criteria:**

**Given** a Product with no tracked quantity
**When** I flag it `low`
**Then** the stored `stock_status` records only that manual assertion, a timestamp is recorded, its age is displayed, and the Product is Effective Low (FR28, FR29, FR31)

### Story 5.4: Derived On Order and Recently Received

As the workshop operator,
I want in-flight and just-received state derived from purchases,
So that reorder decisions reflect reality without extra bookkeeping.

**Acceptance Criteria:**

**Given** a Product with an unreceived Purchase
**When** any status view is rendered
**Then** it is marked On Order, with no On-Order value persisted (FR32, AD-6)

**Given** a Purchase received within the last N days (N a config value)
**When** signals are evaluated
**Then** the Product is Recently Received (derived, not stored)

**Note:** the derived-signal definitions (AD-6) are group-aware, but no Equivalent Product Groups exist until Epic 10; this story ships the per-Product signals, and Epic 10 (Story 10.3) extends On Order / Recently Received to propagate across group siblings.

### Story 5.5: Receipt clears manual low

As the workshop operator,
I want receiving an order to clear a manual low,
So that I don't keep seeing it after it arrives — without corrupting my counts.

**Acceptance Criteria:**

**Given** a manually-`low` Product with an unreceived Purchase
**When** I set the Purchase's received_date
**Then** the stored status returns to `ok` for that product only, `quantity_on_hand` is not modified, and the derived Effective-Low signal is not overridden (FR33, AD-6)

### Story 5.6: Unified reorder view

As the workshop operator,
I want one list of everything to reorder,
So that I can restock in a single pass.

**Acceptance Criteria:**

**Given** Products that are manually low and others derived low from threshold
**When** I open the reorder view
**Then** all Effective-Low Products appear in one list and On-Order ones are marked (FR34, AD-6)
**And** the Equivalent Product Group collapse into a single line is added in Epic 10 (Story 10.3), building on this view — it is not required for this story to deliver

---

## Epic 6: Label Generation & Printing

Generate durable 2×4/1×2 labels via the existing lp path plus a new pyStrich DataMatrix render step, dual-encoded and reprintable.

### Story 6.1: DataMatrix rendering dependency and encoder

As the workshop operator,
I want the internal-id GS1 DataMatrix rendered into a label image,
So that my labels carry a scannable code.

**Acceptance Criteria:**

**Given** `pyStrich[png]` added to `requirements.txt`
**When** the label generator renders a Product's internal id via `gs1.encode()` + pyStrich
**Then** a GS1 DataMatrix raster (FNC1-first, AI 96, `WIT`+id) is produced as a `BytesIO` (FR42, FR44, AD-11/AD-16)

### Story 6.2: 2×4 and 1×2 label templates

As the workshop operator,
I want catalog labels on my 2×4 and 1×2 media,
So that I can label bins, boxes, and bags.

**Acceptance Criteria:**

**Given** new `LABEL_TYPES` entries for 2×4 and 1×2
**When** a label is generated
**Then** the generator composites the DataMatrix together with the Label Description and the Provenance Block (vendor, order date, Vendor SKU, unit price) into one raster and submits it through the unchanged `LpPrinter.print_images()` seam (AD-11)
**And** the Provenance Block appears last in canonical field order (FR47), and no 4×6 catalog label is emitted (FR43)

### Story 6.3: Dual encoding and reprint

As the workshop operator,
I want the id in both barcode and text and reprint on demand,
So that a faded label is still readable and easily replaced.

**Acceptance Criteria:**

**Given** any generated label
**Then** the internal identifier appears both as the DataMatrix and as human-readable text (FR45)

**Given** a Product whose label was damaged
**When** I select reprint from its record
**Then** the label is regenerated and sent with no re-entry, and repeated rendering of an unchanged record produces an identical raster (FR46, NFR11)

---

## Epic 7: Order-Time Capture

Capture vendor/SKU/title/price at order time via an Amazon bookmarklet + REST endpoint, de-duped and idempotent.

### Story 7.1: Capture endpoint

As the workshop operator,
I want a REST endpoint that records an order from a JSON payload,
So that a bookmarklet can file a purchase in one action.

**Acceptance Criteria:**

**Given** a JSON payload (vendor, vendor_sku, listing title, unit_price, quantity, source_url, optional order_date)
**When** it is POSTed to the capture endpoint (`@csrf.exempt`)
**Then** a Purchase is created (with a Product if no match), `order_date` defaults to the capture date when omitted, and the response includes the resulting Product URL (FR48, FR22)
**And** the endpoint has a matching method + frozen result dataclass in `app/api_client.py` and uses the fixed error envelope (AD-13)

### Story 7.2: De-dup and ASIN confirm-not-merge

As the workshop operator,
I want a repeat purchase to attach to the existing product,
So that price history stays on one record — without merging genuinely different items.

**Acceptance Criteria:**

**Given** a submitted Vendor SKU that matches an existing Identifier or a prior `purchases.vendor_sku` (vendor-scoped per type — AD-9)
**When** capture runs
**Then** the Purchase attaches to that Product and no duplicate is created (FR50)

**Given** an ASIN match where manufacturer/MPN differ
**When** capture runs
**Then** the match requires explicit operator confirmation rather than a silent merge; a first-sight ASIN is indexed as an identifier (FR11, AD-9)

### Story 7.3: Title draft and authored description

As the workshop operator,
I want the listing title pre-filled and overridable,
So that I can compose the label text at order time or defer it.

**Acceptance Criteria:**

**Given** a capture with no supplied description
**When** the Product is opened for editing
**Then** the listing title appears in the Label Description field as an editable draft (FR49)

**Given** a capture payload that includes an authored Label Description
**Then** that description replaces the title draft and remains editable at receipt (FR49a)

### Story 7.4: Idempotent capture

As the workshop operator,
I want a retried capture to not double-record,
So that a dropped connection doesn't create duplicates.

**Acceptance Criteria:**

**Given** a capture request carrying a client `request_key` (UNIQUE constraint — AD-9)
**When** the same key is submitted twice
**Then** exactly one Purchase exists, both responses reference it, and the idempotent unit is the whole Product+Purchase transaction (FR51)

### Story 7.5: Enrichment no-op hook

As a future maintainer,
I want product creation to call an enrichment interface,
So that a later lookup implementation drops in without restructuring creation.

**Acceptance Criteria:**

**Given** `app/services/product_enrichment.py` with a no-op implementation
**When** a Product is created
**Then** the create path invokes the interface with the available identifiers, the no-op returns an empty partial record, and creation proceeds unchanged (FR60)

### Story 7.6: Amazon bookmarklet

As the workshop operator,
I want a bookmarklet on an Amazon page to capture the order,
So that I record metadata while the listing is in front of me.

**Acceptance Criteria:**

**Given** I am on an Amazon product page having just ordered
**When** I invoke the bookmarklet
**Then** vendor SKU (ASIN), title, and the shown price are extracted and POSTed to the capture endpoint, and I see a confirmation linking to the record (FR48; capture-time price treated as paid, order date defaults to today)

---

## Epic 8: Search & Retrieval

Full-text search across catalog text and identifiers, faceted and bookmarkable, with direct-URL product views.

### Story 8.1: Full-text search entrypoint

As the workshop operator,
I want to search across everything about a product,
So that I can find it by any remembered detail.

**Acceptance Criteria:**

**Given** the shared `search_products()` service method introduced for the scan fallthrough in Epic 4 (AD-17)
**When** I build the search page/experience on it and search a term appearing in a Label Description, notes, manufacturer, MPN, or any identifier value
**Then** the matching Products are returned, with the method confirmed to cover all those fields (FR52)

### Story 8.2: Faceted filtering and bookmarkable state

As the workshop operator,
I want to narrow results by facets and bookmark the view,
So that I can return to a saved filter.

**Acceptance Criteria:**

**Given** search results
**When** I filter by category path prefix (segment-boundary match), tag, or Effective-Low/stock status
**Then** results narrow accordingly and the filter state is reflected in a bookmarkable URL that reproduces them (FR53, FR54)

### Story 8.3: Direct-URL product view

As the workshop operator,
I want a stable URL per product keyed on its internal id,
So that a scanned or linked id opens the right product.

**Acceptance Criteria:**

**Given** a Product with an internal identifier
**When** I visit its `internal_id`-keyed URL
**Then** the correct Product detail view opens (FR55)

---

## Epic 9: Handheld & Touch Readiness

Make every action touch-reachable, the scan-result view self-sufficient at handheld width, and form state resilient to network drops.

### Story 9.1: Touch equivalents for shortcuts

As the workshop operator on a tablet or handheld,
I want a touch control for every keyboard shortcut,
So that I can work without a keyboard.

**Acceptance Criteria:**

**Given** the UI at handheld width
**When** it renders
**Then** every action available via keyboard shortcut has a touch-reachable equivalent, and no interaction depends on hover or a physical keyboard (FR56, FR58)

### Story 9.2: Self-sufficient scan-result view

As the workshop operator holding a handheld,
I want the scan result to show everything and let me act inline,
So that I don't have to navigate to identify or adjust an item.

**Acceptance Criteria:**

**Given** a 360 px viewport
**When** a scan resolves to a Product (rendered from the `ScanResolution` — AD-15)
**Then** identity, Specifications, location, and stock status are visible, and quantity adjustment and status flagging are available without navigation (FR57)

### Story 9.3: Form-state persistence

As the workshop operator on wireless,
I want in-progress form text to survive a dropped connection,
So that a roam or outage doesn't lose my work.

**Acceptance Criteria:**

**Given** a partially composed Label Description
**When** the connection drops and is restored
**Then** the composed text is still present (FR59)

---

## Epic 10: Equivalent Products

Declare same-part brand-relabels into one Equivalent Product Group and surface it in the product view and the reorder collapse.

### Story 10.1: Declare and undeclare equivalence

As the workshop operator,
I want to group products that are the same part under different brands,
So that I treat them as one for reordering.

**Acceptance Criteria:**

**Given** Products A and B (a `products.equivalent_group_id` FK to a new `equivalent_groups` table — AD-10)
**When** I add B to A's group
**Then** both are symmetric members of one group (A lists B and B lists A), and a member can be removed leaving the rest grouped (FR62)

**Given** a Product already in a different group
**When** I try to add it to another group
**Then** it is rejected rather than silently moved (FR62, AD-10)

### Story 10.2: Equivalents on the product view

As the workshop operator,
I want to see a product's equivalents and their latest prices,
So that I can choose the cheapest source.

**Acceptance Criteria:**

**Given** a Product in an Equivalent Product Group
**When** I open its detail view
**Then** the other members are listed with their manufacturer/MPN and most-recent unit price (FR63)

### Story 10.3: Equivalence in the reorder view

As the workshop operator,
I want a group to appear as one reorder line, suppressed when any member is inbound,
So that I don't double-order interchangeable parts.

**Acceptance Criteria:**

**Given** two Effective-Low Products in the same group
**When** the reorder view renders
**Then** they appear as one collapsed line with their latest prices comparable (FR64)

**Given** one member is On Order or Recently Received
**When** the reorder view renders
**Then** the whole group is suppressed from needing reorder, achieved via the derived signals and never by writing a sibling's stored status (FR64, AD-6, AD-10)
