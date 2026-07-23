---
title: Product Catalog & Purchase Tracking
status: final
created: 2026-07-21
updated: 2026-07-21
---

# PRD: Product Catalog & Purchase Tracking
*Working title — confirm.*

*Brownfield enhancement to the existing `workshop-inventory-tracking` Flask application. Source draft: `~/tmp/prd-product-catalog.md` (v0.3). Project context/rules: `_bmad-output/project-context.md`. This revision incorporates the finalize reviewer gate (see `review-rubric.md`, `review-adversarial-general.md`).*

## 0. Document Purpose

This PRD is for the single developer-operator of `workshop-inventory-tracking` (who is also the sole user) and for the downstream BMad workflows — architecture, UX, and epic/story generation — that build on it. It defines a **product catalog and purchase-history** capability for non-metal-stock workshop consumables and components, as a bounded enhancement to the existing Flask app. It is organized as a Glossary-anchored vocabulary (§3), features with globally-numbered Functional Requirements nested under them (§4), cross-cutting non-functional requirements (§5), hardware/environment constraints (§6), the order-time capture API surface (§7), risks (§8), and scope/metrics/questions (§9–§13). Assumptions I inferred without confirmation are tagged `[ASSUMPTION]` inline and indexed in §14. Technical depth that belongs to the architect — the rejected-alternative rationale for the internal identifier, the ECIA/MH10.8.2 reference notes, an indicative data model, and a provisional epic/story decomposition — lives in the companion `addendum.md`; this PRD references it rather than duplicating it.

## 1. Vision

The workshop already holds tens of thousands of items, the overwhelming majority of which will never be recorded. This is not an inventory-control problem — it is an **identification** problem. The goal is that any item acquired *from this point forward* can be identified — what it is, its key specifications, where it came from, and what it cost — at the moment it is picked up off a shelf, **without recourse to a vendor product page that may no longer exist**. The primary targets are unbranded electronic, electrical, and hardware items bought from Amazon, plus properly-labeled parts from industrial distributors (DigiKey, Mouser, McMaster-Carr).

Today, product metadata is manually re-derived from vendor pages at unboxing time and typed onto a printed physical label, with no retained copy. That label represents real editorial work — compressing a keyword-stuffed listing title down to the handful of facts that actually identify the item, and frequently *adding* knowledge not present in the listing (drill sizes, mounting-hole dimensions, unit conversions). Only the physical adhesive copy survives; the data is thrown away. This enhancement captures that editorial work as durable, searchable data at the moment it is composed, captures mechanical metadata (vendor part ID, order date, unit price) at *order* time rather than re-deriving it at *receipt* time, and makes every barcode in the shop — a manufacturer GTIN, a distributor 2D label, or a label this system prints — resolve to a catalog record via a single scan.

This is a single-user application serving one hobby workshop, receiving on the order of tens of parts per month. Every design decision favors simplicity, low maintenance burden, and data durability over throughput, concurrency, or performance. The enhancement is deliberately bounded to one additional entity cluster with a small surface area, delivered inside the existing app and reusing its infrastructure (MariaDB + Alembic, REST API, `requests`-only client, keyboard-wedge scanner integration, Bootstrap 5.3.2 UI, `lp`-based label submission, Docker deployment).

## 2. Target User

### 2.1 Jobs To Be Done

- **Identify a part in hand.** When I pick up any item acquired after this launch, tell me what it is, its key Specifications, where it came from, and what it cost — from its physical label alone, with no network and no live vendor page.
- **Stop re-transcribing.** Capture the listing title, Vendor SKU, order date, and unit price once, at order time, so I never re-navigate to a page that may have changed or vanished.
- **Preserve my editorial work.** The compressed, corrected, knowledge-added Label Description I compose is data worth keeping and reprinting — not a throwaway that exists only as adhesive.
- **Resolve any barcode with one scan.** A manufacturer GTIN, a DigiKey/Mouser 2D label, or a label this system printed should all route to the right record from a single scan.
- **Recognize repeat purchases.** When I buy the same thing again, show me the price and date history so I can see whether it's gotten more expensive and where I bought it last.
- **Track stock only where it earns its keep.** Let me track quantity and location for the handful of high-value or long-lead items where a stockout has real cost, and leave it entirely absent everywhere else — with an unambiguous distinction between "zero on hand" and "not tracked."
- **Classify without a taxonomy project.** Let me file and filter products well enough to browse, without designing a category tree up front.
- **Consolidate brand-relabels.** When the identical part is sold under three brand names, let me treat those listings as one thing for reorder and price comparison.

### 2.2 Non-Users (v1)

- **Any second user.** There is no multi-user, permissions, authentication-per-role, or concurrency requirement of any kind. The app's existing single-operator auth is inherited unchanged.
- **The pre-enhancement inventory at large.** The tens of thousands of already-owned items are explicitly *not* the audience. Only newly-acquired items (plus opportunistic, ad-hoc backfill of a handful of high-value or frequently-confused existing items) are in view. [ASSUMPTION: "label-worthy" ≈ the roughly half of received items that today get a hand-printed label; the distributor-labeled remainder are catalogued for search/reorder but need no printed label.]

### 2.3 Key User Journeys

*Single-operator tool, so these are captured as lean scenes with one named protagonist — Jason, at the workshop cart. FRs reference them by ID inline.*

- **UJ-1. Jason captures an order while the listing is still open.**
  Jason is on an Amazon product page in a browser, having *just placed an order*. He invokes the capture bookmarklet (**Amazon-only**), which extracts vendor, Vendor SKU (ASIN), listing title, and the price shown, and posts them to the capture endpoint — creating a new Product or attaching to an existing one by identifier match. The **order date defaults to today** (capture time) and the **captured price is taken as the price paid**; both remain editable. Because the full listing (including Specifications that may not survive to receipt) is in front of him, he *optionally authors the Label Description now* rather than deferring it. **Climax:** a confirmation with a link to the record. **Resolution:** an in-flight Purchase (null received date) exists, ready to be reconciled against the physical item on arrival. Realizes FR48–FR51, FR49a. [ASSUMPTION: capture happens at or near order time, so the listing price then ≈ the price paid — see §8 RISK-6.]

- **UJ-2. Jason receives an Amazon package and prints a label.**
  A box arrives. Jason scans or opens the pending Purchase at the cart. If he authored a description at capture time, he confirms or amends it against the item in hand; if not, he composes it from the pre-filled listing title. Specifications discoverable only from the physical part (measured dimensions, part markings, actual thread pitch) are added here. He marks the Purchase received and prints a 2×4 or 1×2 label. **Climax:** a durable label with description, Provenance Block, and a scannable internal-ID barcode is on the part. **Resolution:** the Product is identifiable offline, forever. Realizes FR6, FR33, FR42–FR47.

- **UJ-3. Jason receives a distributor package — no label needed.**
  A DigiKey bag arrives. Jason scans its 2D barcode; MPN, quantity, and order references parse automatically and pre-fill a product/purchase form. He confirms. **No label is printed** — the distributor's label is adequate. **Resolution:** the record exists for search and reorder history. Realizes FR36, FR38–FR41.

- **UJ-4. Jason finds an unknown item on a shelf.**
  He scans the label this system printed, or the manufacturer barcode on the packaging. **Climax:** the scan-result view shows what it is — identity, Specifications, location, Stock Status — self-sufficiently, at whatever screen width he's on. Realizes FR35–FR37, FR52, FR55, FR57. **Edge case:** a scan matching no record lands on a pre-filled product-creation form with the scanned identifier attached and typed — never an error page (FR40).

- **UJ-5. Jason checks what to reorder.**
  He opens a single reorder view listing everything effectively `low` or `out` — whether set manually or derived from a tracked quantity at/below threshold — with in-flight (On Order) purchases visibly marked so he doesn't double-order. Where brand-relabels exist as an Equivalent Product Group, the group appears as a single line with its members' price history comparable, and an inbound order on *any* member marks the whole group On Order. Realizes FR28–FR34, FR62–FR64.

## 3. Glossary

*Downstream workflows and readers must use these terms exactly. FRs, UJs, and metrics use them verbatim; no synonyms elsewhere.*

- **Product** — A catalog record for a distinct kind of item, independent of any Purchase. Carries manufacturer, MPN, Label Description, notes, Category, Tags, Identifiers, Specifications, optional quantity/location/stock fields, and a generated Internal Identifier. One Product has zero or more Purchases.
- **Purchase** — A record of acquiring a Product on a specific order: vendor, Vendor SKU, order date, nullable received date, quantity, unit price, order number, source URL. Belongs to exactly one Product.
- **Label Description** — The human-authored text printed on a Product's label. Editorial, often corrected/augmented beyond the source listing. Distinct from the listing title.
- **Specifications** — The Product's structured/semi-structured attributes (e.g. measured dimensions, thread pitch, voltage, drill sizes), stored in the Product's `attributes` JSON plus the named fields (manufacturer, MPN). This is the "specs" rendered on the Product detail and scan-result views (FR57). Not a separate entity.
- **Provenance Block** — The purchase-derived half of a label: vendor, order date, Vendor SKU, unit price. Always rendered last, in canonical field order.
- **Identifier** — A typed, valued external or internal code attached to a Product. Types (minimum): `GTIN`, `GTIN_UNVALIDATED`, `ASIN`, `FNSKU`, `MPN`, `VENDOR_SKU`, `INTERNAL`. The pair (type, value) is unique across the catalog.
- **Internal Identifier** — A system-generated identifier unique to each Product, held authoritatively in the Product's `internal_id` and encoded on printed labels as a GS1 DataMatrix (see Internal Encoding). Never depends on any external identifier. The `INTERNAL`-type Identifier row, if present, is a derived read index, not an independent source of truth.
- **GTIN** — Global Trade Item Number. Check-digit-valid values are normalized to 14 digits (left zero-padded) on write and lookup so GTIN-8, UPC-A (12), EAN-13 (13), and GTIN-14 forms of the same product resolve identically. Values that fail check-digit validation are not GTINs and are stored, if kept, as `GTIN_UNVALIDATED` (unnormalized), never in the GTIN namespace.
- **ASIN** — Amazon Standard Identification Number. Recorded as the **Purchase**'s Vendor SKU (not as Product identity, because Amazon reuses ASINs), and additionally indexed as an `ASIN`-type Product Identifier on capture so repeat purchases resolve to the same Product.
- **FNSKU** — Amazon FBA per-seller-per-product barcode (`X00…`). A "same seller, same item" signal only; its own Identifier type, never conflated with GTIN.
- **MPN** — Manufacturer Part Number. Optional (many unbranded imports have none).
- **Vendor SKU** — The seller's own identifier for an item on a Purchase (e.g. an ASIN, a distributor customer part number).
- **Category** — A node in a hierarchical tree of arbitrary depth, stored as a materialized path (e.g. `electronics/power/dc-dc-converters`). Created inline via autocomplete-with-create; the tree ships empty and accretes from use.
- **Tag** — A free-form label on a Product, independent of Category, for cross-cutting retrieval.
- **Internal Encoding** — The barcode payload for the Internal Identifier: a GS1 element string with FNC1 in first position, GS1 Application Identifier (AI) **96** (company internal information), and a data field of the configured token `WIT` followed by the internal identifier. AI 96 is the sole element string; no separator handling.
- **ECIA Barcode** — A distributor 2D barcode (DataMatrix or PDF417) carrying ANSI MH10.8.2 data identifiers per ISO/IEC 15434:2006 (format-06 envelope). Used by DigiKey, Mouser, and other ECIA distributors.
- **Quantity On Hand** — A nullable integer per Product. `NULL` = not tracked; `0` = tracked, none on hand; `N` = tracked, N on hand. The three states render as distinct literal text (see FR23). Modified only by manual assertion — never automatically on receipt.
- **Quantity Verified At** — Timestamp set whenever Quantity On Hand is manually asserted; its age is displayed alongside the quantity.
- **Reorder Threshold** — An optional integer per Product; when Quantity On Hand is at or below it, the Product is **Effective Low**.
- **Stock Status** — A stored value per Product, one of `unknown` (default), `ok`, `low`, `out`, holding only the operator's **manual** assertion. It is not written by derivation. See Effective Low.
- **Effective Low** — The computed reorder signal, evaluated at read: true when stored Stock Status is `low`/`out` **OR** (Quantity On Hand is tracked and ≤ Reorder Threshold). Never stored. Drives the reorder view (FR34).
- **On Order** — A derived indicator, true when a Product — or, for a member of an Equivalent Product Group, *any* member of its group — has a Purchase with a null received date. Never persisted.
- **Equivalent Product Group** — A set of Products that are the **same manufacturer part sold under different brand names/labels** (e.g. one ESP32-WROOM-32 module relabeled by three sellers). This is a genuine equivalence class, so membership is a partition: each Product belongs to at most one group, and the relation is symmetric and transitive by definition of "same part." It does **not** model looser "functionally substitutable" relationships (see §4.5 and §9 NG11).
- **Enrichment Interface** — A single internal interface taking a set of typed Identifiers and returning a partial Product record (manufacturer, MPN, category suggestion, attributes). This phase ships only a no-op implementation.
- **Attachment** — A file (datasheet, wiring diagram, saved product page, photograph) linked to **exactly one** of a Product or a Purchase (never both, never neither — see FR5).

## 4. Features

*Each subsection is a coherent feature. FR identifiers are preserved verbatim from the source draft (FR1–FR61, including lettered variants) so the provisional epic decomposition in `addendum.md` stays traceable; equivalent-products adds FR62–FR64. Consequences are testable.*

### 4.1 Product Catalog

**Description:** Product records exist as first-class entities alongside metal stock, distinct from purchases, editable at any time, and creatable with nothing but a Label Description. Realizes UJ-2, UJ-4.

**Functional Requirements:**

#### FR1: Products distinct from purchases
The system maintains Product records distinct from Purchase records, such that one Product has zero or more Purchases.
**Consequences (testable):**
- A Product persists with zero Purchases.
- Deleting/altering a Purchase never deletes its Product.

#### FR2: Product core fields
A Product carries: manufacturer, MPN, Label Description, free-text notes, Specifications (`attributes`), and a Category assignment.
**Consequences (testable):**
- All fields round-trip through create/edit/detail.

#### FR3: Manufacturer and MPN optional
Manufacturer and MPN are both optional (a substantial fraction of catalogued items are unbranded imports with no meaningful MPN).
**Consequences (testable):**
- A Product saves with both blank; no validation error.

#### FR4: Product creatable without a purchase
A Product is creatable with no Purchase record, to support items acquired outside the order workflow (opportunistic backfill).
**Consequences (testable):**
- Creating a Product with only a Label Description succeeds; all other fields empty.

#### FR5: Attachments on product or purchase
The system supports attaching arbitrary files (datasheets, wiring diagrams, saved product pages, photographs) to either a Product or a specific Purchase.
**Consequences (testable):**
- A PDF uploaded to a Product is retrievable from the Product view.
- A file attached to a Purchase is retrievable from that Purchase.
- Every Attachment references exactly one of (Product, Purchase); a row with both set or both null is rejected by an enforced invariant.

#### FR6: Editable; edits don't invalidate prior prints
Products are editable at any time; Label Description edits do not invalidate previously printed labels but are reflected in subsequent prints. Realizes UJ-2.
**Consequences (testable):**
- Editing a description and reprinting yields the new text; the old physical label is not tracked as invalid.

### 4.2 Identifiers & Internal Encoding

**Description:** One Product is reachable by any identifier printed on it, its packaging, or its vendor's label. Each Product also gets a system-generated Internal Identifier encoded so it can never collide with an external code. Realizes UJ-4. Full rejected-alternative rationale for the encoding choice is in `addendum.md`.

**Functional Requirements:**

#### FR7: Typed multi-identifier storage
The system stores multiple Identifiers per Product, each with a declared type; minimum types: `GTIN`, `GTIN_UNVALIDATED`, `ASIN`, `FNSKU`, `MPN`, `VENDOR_SKU`, `INTERNAL`. The Product's `internal_id` is the authoritative Internal Identifier; any `INTERNAL`-type Identifier row is a derived read index, not independently editable.
**Consequences (testable):**
- Adding one identifier of each external type to a Product persists all with their types.
- The `internal_id` and any `INTERNAL` Identifier row always agree; the row cannot be edited to diverge.

#### FR8: (type, value) uniqueness
The combination of identifier type and value is unique across the catalog.
**Consequences (testable):**
- Adding a (type, value) that already exists on another Product is rejected with a message naming the conflicting Product.

#### FR9: GTIN normalization to 14 digits
Check-digit-valid GTIN values are normalized to 14 digits, zero-padded on the left, on both write and lookup. GTIN-8, UPC-A, EAN-13, and GTIN-14 forms all normalize to the same 14-digit key, which is the canonical lookup/uniqueness value. (Whether to also retain the as-entered form for display is an architect's choice — see addendum.)
**Consequences (testable):**
- GTIN-8 `00012345`, UPC-A `012345678905`, EAN-13, and GTIN-14 forms of the same product each resolve to the correct normalized key.
- Normalization is applied only to `GTIN`; `GTIN_UNVALIDATED` values are stored as-entered.

#### FR10: GTIN check-digit validation
GTIN check digits are validated on entry; failing values are rejected with a clear message and an option to store the value as a `GTIN_UNVALIDATED` Identifier instead. `GTIN_UNVALIDATED` values are neither normalized nor placed in the `GTIN` uniqueness namespace, so a garbage value can never squat a real GTIN slot.
**Consequences (testable):**
- A 12-digit value with a bad check digit is rejected as a GTIN with an explanation and a "store as unvalidated" option.
- A stored `GTIN_UNVALIDATED` value does not block a later check-digit-valid GTIN that would normalize to the same digits.

#### FR11: ASIN on the purchase, and indexed for de-dup
ASIN is recorded on the **Purchase** as the Vendor SKU (Product identity does not depend on it, because Amazon reuses ASINs), and is **additionally indexed as an `ASIN`-type Product Identifier on capture** so a later purchase of the same ASIN resolves to the same Product (see FR50).
**Consequences (testable):**
- Capturing a never-seen ASIN creates the Product and an `ASIN` Identifier for it.
- The Product's identity is unaffected if the ASIN is later reassigned by Amazon; the indexed identifier is what resolves lookups.

#### FR12: Internal identifier via GS1 DataMatrix / AI 96
The system generates an Internal Identifier per Product, encoded on labels as a GS1 DataMatrix carrying GS1 AI 96 (company internal information), so internally-generated codes never collide with external GTINs or distributor payloads. *(Rendering this 2D symbol is a new capability — see FR42/Q7.)*
**Consequences (testable):**
- Every new Product gets a unique Internal Identifier and a renderable GS1 DataMatrix payload.

#### FR12a: Self-identifying `WIT` token
The AI 96 data field is the fixed token `WIT` followed by the Product's Internal Identifier, so a foreign AI-96 element string fails format validation rather than resolving to a coincidental product.
**Consequences (testable):**
- An AI-96 payload whose data field does not begin with `WIT` is not treated as an Internal Identifier.

#### FR12b: Single element string, no separator
AI 96 is the **only** element string in the symbol; FNC1 occupies first position; the variable-length terminal AI-96 field needs no separator, and no second AI is encoded.
**Consequences (testable):**
- The generated symbol contains exactly one element string; encoder/parser handle no group separators.

#### FR12c: AI number and token are configuration
The AI number (`96`) and payload token (`WIT`) are configuration values, not literals in code or templates.
**Consequences (testable):**
- Changing config changes both the encoder output and the router's recognition, with no code edit.

#### FR12d: Ownership/return info is human-readable only
Ownership and return information appears as human-readable label text, not as encoded element strings (AI 4311 and 43xx logistics identifiers were considered and rejected — see addendum).
**Consequences (testable):**
- No 43xx element string is ever encoded; return/ownership text appears only in the human-readable region.

### 4.3 Taxonomy & Tagging

**Description:** Products are classified and cross-referenced without designing a taxonomy in advance. Categories are a materialized-path tree that accretes from use; Tags cut across it. Realizes UJ-4, UJ-5.

**Functional Requirements:**

#### FR13: Materialized-path categories
Products are classified into a hierarchical Category tree of arbitrary depth, stored as a materialized path (e.g. `electronics/power/dc-dc-converters`).
**Consequences (testable):**
- Typing a new path creates it and assigns it.

#### FR14: Inline create via autocomplete
Categories are creatable inline during product entry via autocomplete-with-create, following the existing thread-size/vendor/location pattern.
**Consequences (testable):**
- A never-before-seen path typed at entry is created without leaving the form; subsequent products offer it via autocomplete.

#### FR15: No pre-populated taxonomy
The system ships no pre-populated taxonomy; the tree accretes from use.
**Consequences (testable):**
- A fresh install offers no categories until the operator creates one.

#### FR16: Free-form tags
Products support zero or more free-form Tags, independent of Category.
**Consequences (testable):**
- Filtering by a tag returns the correct subset regardless of category (e.g. three heat sinks under `thermal/heat-sinks`, two tagged `ssr` → filter `ssr` returns those two).

#### FR17: Category rename with descendants
Category paths are editable, with descendants and assigned Products following the rename. A rename that would collide with an existing sibling path is rejected rather than silently merged.
**Consequences (testable):**
- Renaming a path segment updates all descendant paths and all assigned Products.
- Renaming a segment onto an existing sibling path is rejected with a message.

### 4.4 Purchases

**Description:** Purchases record acquisition events against a Product, including in-flight orders, and expose price/date history. Realizes UJ-1, UJ-5.

**Functional Requirements:**

#### FR18: Purchase fields
A Purchase carries: Product reference, vendor, Vendor SKU, order date, received date, quantity purchased, unit price, order number, source URL.
**Consequences (testable):**
- All fields round-trip through create/detail.

#### FR19: Nullable received date = in flight
Received date is nullable; a null received date represents an order in flight (On Order). Realizes UJ-1.
**Consequences (testable):**
- A Purchase saves with a null received date and is reported On Order.

#### FR20: Purchase history display
For any Product, the system displays the full Purchase history with dates, vendors, and unit prices in chronological order. Realizes UJ-5.
**Consequences (testable):**
- Three purchases across two vendors list chronologically with date/vendor/price.

#### FR21: Surface most recent prior price
When recording a Purchase against a Product with prior Purchases, the system surfaces the most recent prior unit price in a labeled field (e.g. "Last paid").
**Consequences (testable):**
- The most recent prior unit price appears in the named field at entry and on the history.

#### FR22: Purchases via REST API
Purchases are creatable via the REST API with sufficient fields to support order-time capture from a browser bookmarklet. (See §7.)
**Consequences (testable):**
- A REST call creates a Purchase with the capture fields set.

### 4.5 Equivalent Products

**Description:** The operator can declare that several distinct Products are the **same manufacturer part sold under different brand names** — one ESP32-WROOM-32 module relabeled by three sellers — and have that equivalence surface in reorder and price comparison. This is deliberately a genuine equivalence class ("same part"), **not** looser "functionally substitutable" grouping (e.g. a dev board that happens to be pin-compatible with a bare module) — that broader notion is a Non-Goal (§9 NG11) because it is non-transitive and would require a heavier model. Because "same part" is transitive, a Product belongs to at most one Equivalent Product Group. This feature is **newly in scope** for this phase (the source draft had it deferred as Open Question Q4; the equivalence model was resolved during the finalize gate — Q8, now closed). Realizes UJ-5.

**Functional Requirements:**

#### FR62: Declare equivalence
The operator can add a Product to an Equivalent Product Group, creating the group if none exists, from the Product detail view. Adding a Product that already belongs to a *different* group is rejected (the operator must first remove it), so no existing equivalence is silently dropped.
**Consequences (testable):**
- Adding Product B to Product A's group makes both members of one group; the relation is symmetric (A lists B and B lists A).
- A Product can be removed from its group, leaving remaining members grouped.
- Adding B (already in group G2) to A's group G1 is rejected with a message rather than moving B out of G2.

#### FR63: Equivalents visible on the product
A Product's detail view lists its equivalents with their manufacturer/MPN and most-recent unit price.
**Consequences (testable):**
- Opening any member shows the other members and each one's latest price.

#### FR64: Equivalence in reorder & price comparison
In the reorder view (FR34), an Equivalent Product Group is collapsed to a single line so one reorder decision covers all brand-relabels, with the cheapest recent price visible. On Order or a recent receipt on **any** member marks the whole group, so an inbound order on one relabel suppresses the reorder signal for the others. Realizes UJ-5.
**Consequences (testable):**
- Two Effective-Low Products in the same group appear as one reorder line with their latest prices comparable.
- A group with one member On Order shows the group as On Order, not as needing reorder.

**Notes:** `[NOTE FOR PM]` — Scope is deliberately minimal: group membership + display + reorder grouping over a genuine "same-part" equivalence class. No cross-group merge, no substitutability graph, no equivalence-implied identifier sharing, no automatic equivalence detection.

### 4.6 Optional Quantity & Location

**Description:** Quantity and location tracking are opt-in per Product and absent by default, with honest staleness. Realizes UJ-5. The system remains fully usable for identification with quantity tracking entirely unused (NFR5).

**Functional Requirements:**

#### FR23: Tri-state quantity on hand
Quantity On Hand is a nullable integer: `NULL` = not tracked, `0` = tracked/none, `N` = tracked/N. The three states render as distinct literal text so the reader can never confuse "untracked" with "none on hand."
**Consequences (testable):**
- `NULL` renders as an untracked marker (e.g. "—" / "Not tracked"), `0` as "In stock: 0", `N` as "In stock: N" — three visibly distinct strings.
- Setting a Product from `NULL` to `0` changes its rendering from the untracked marker to "In stock: 0".

#### FR24: Default NULL / opt-in
Quantity defaults to `NULL` on creation; tracking is opt-in per Product.
**Consequences (testable):**
- A newly created Product renders as untracked.

#### FR25: Quantity verification staleness
The system records Quantity Verified At whenever quantity is manually asserted, and displays its age alongside any tracked quantity. Receipt of a Purchase does **not** modify Quantity On Hand (see FR33) — the count is operator-asserted only, and its staleness is surfaced rather than silently corrected.
**Consequences (testable):**
- A quantity set eight months ago shows its verification age on display.
- Receiving a Purchase leaves Quantity On Hand and Quantity Verified At unchanged.

#### FR26: Optional reorder threshold
A Product supports an optional integer Reorder Threshold.
**Consequences (testable):**
- A threshold persists and drives Effective Low (FR30).

#### FR27: Optional location reusing existing vocabulary
Location and sub-location are optional on Products, reusing the existing location autocomplete endpoints and vocabulary rather than introducing parallel fields. [ASSUMPTION: the existing `field-suggestions` endpoint's source query is extended to include Product locations so the vocabulary is bidirectional; today it draws from metal-stock rows only — see addendum brownfield note.]
**Consequences (testable):**
- Location autocomplete on a Product draws from the existing suggestion source.

### 4.7 Stock Status & Reorder Signals

**Description:** A Product carries a stored Stock Status that holds only the operator's manual assertion; the reorder signal (Effective Low) and On Order are **derived, never stored**, so the two can never contradict each other. A single reorder view unifies manual and derived signals. Realizes UJ-2, UJ-5.

**Functional Requirements:**

#### FR28: Stored status holds manual assertions only
Each Product carries a stored Stock Status `unknown` | `ok` | `low` | `out`; default `unknown`. This value records only the operator's manual assertion. Derivation never writes it.
**Consequences (testable):**
- A new Product is `unknown`.
- No automatic process mutates the stored Stock Status.

#### FR29: Manual status, including untracked products
The operator can set Stock Status manually, including flagging `low` or `out` on Products with no tracked quantity.
**Consequences (testable):**
- Flagging an untracked Product `low` sets its stored status and records a timestamp (FR31), and the Product is Effective Low.

#### FR30: Effective Low derived from threshold
For Products with a tracked Quantity On Hand and a Reorder Threshold, the Product is **Effective Low** when quantity ≤ threshold. Effective Low is computed at read from stored status OR the quantity/threshold comparison; it is never written back to the stored Stock Status.
**Consequences (testable):**
- Quantity 2, threshold 3, stored status `ok` → Effective Low is true on evaluation, with no change to the stored status.
- Raising quantity above threshold makes Effective Low false again with no stored-status write.

#### FR31: Status timestamp & age
The system records a timestamp when the stored Stock Status is manually set and displays its age.
**Consequences (testable):**
- A manually-set status shows its age.

#### FR32: On Order derived, not stored
On Order is not a stored status; it is derived from the existence of any Purchase with a null received date — for the Product, or for any member of its Equivalent Product Group (FR64) — and shown as a distinct indicator.
**Consequences (testable):**
- No On-Order value persists on the Product; the indicator appears while an unreceived Purchase exists on the Product or a group sibling.

#### FR33: Receipt clears a manual low/out
Setting a received date on a Purchase clears the associated Product's **manual** Stock Status from `low` or `out` to `ok`. It does not modify Quantity On Hand and does not override the derived Effective-Low signal — so if the tracked quantity is still ≤ threshold, the Product remains Effective Low and continues to surface in the reorder view. Realizes UJ-2.
**Consequences (testable):**
- Receiving a Purchase on a manually-`low` untracked Product returns its stored status to `ok` and drops the On-Order indicator.
- Receiving a Purchase on a tracked Product whose quantity is still ≤ threshold leaves it Effective Low (no flip-flop), and does not change Quantity On Hand.

#### FR34: Unified reorder view
The system provides a single reorder view listing all Effective-Low Products (manual or derived), with On-Order Products/groups visibly marked and Equivalent Product Groups collapsed to one line (FR64). Realizes UJ-5.
**Consequences (testable):**
- Manually-low and derived-low Products both appear; On-Order ones are marked; group members appear as a single line.

### 4.8 Scanning & Scan Routing

**Description:** Scanner input arrives as keyboard-wedge keystrokes and is routed to the correct interpretation by structural inspection, degrading gracefully. Realizes UJ-3, UJ-4. Empirical scanner behavior (FNC1 transmission, AIM identifier support) is a **blocking hardware spike** — Open Question Q1 — because the internal-ID scan path depends on the 2D payload round-tripping recognizably.

**Functional Requirements:**

#### FR35: Keyboard-wedge input, no driver
The system accepts scanner input as keyboard-wedge keystrokes, requiring no scanner-specific driver or API, so both the Tera HW0009 and Zebra DataWedge devices work without code changes. Realizes UJ-4.
**Consequences (testable):**
- A scan terminated by Enter is captured on any page with the scan field focused.

#### FR36: Structural routing precedence
The system routes scanned input by inspecting structure, in order: (1) GS1 element string with AI 96 + configured token → direct Internal-Identifier lookup; (2) ISO/IEC 15434 format-06 envelope header `[)>`RS`06` → ECIA parse; (3) an all-digit value of length 8 or 12–14 passing GTIN check-digit validation → GTIN lookup after normalization; (4) anything else → free-text search across identifiers, descriptions, MPNs. A rule-3 value that passes the check digit but matches no Product GTIN falls through to free-text search within the same scan rather than dead-ending. Realizes UJ-3, UJ-4.
**Consequences (testable):**
- Each of the four input classes routes to its stated handler; a value matching none falls to free-text search.
- A GTIN-8 (8-digit, valid check digit) is normalized and looked up, not dropped to free-text.
- A 13-digit number with a valid check digit but no GTIN match still returns free-text results, not an error.

#### FR37: AIM symbology identifiers narrow, not decide
If the scanner emits AIM symbology identifiers, the system uses them to narrow the symbology class; the AI/token structural inspection of FR36 (rules 1 vs 3) still selects the handler, because `]d1` denotes *any* GS1 DataMatrix (an internal AI-96 symbol and a manufacturer's AI-01 GTIN symbol alike). Routing falls back to pure structural inspection when the identifier is absent. (`]d2` is not what this system emits.)
**Consequences (testable):**
- A `]d1`-prefixed scan is confirmed a GS1 DataMatrix, then routed by its AI/token (internal vs GTIN); routing is unchanged when the prefix is absent.

#### FR37a: FNC1 transmission tolerance
The system assumes no particular FNC1 transmission; parsing tolerates GS (0x1D), a configurable substitute character, or stripped FNC1. The graceful-degradation path depends on the `WIT` token surviving as a recognizable literal prefix; deployed-scanner behavior is confirmed by the Q1 spike.
**Consequences (testable):**
- A GS1 DataMatrix carrying AI 96 parses correctly under all three FNC1 transmissions, provided the data characters are transmitted intact.

#### FR38: ECIA data-identifier parsing
The system parses ECIA-format 2D barcodes (DataMatrix/PDF417, ANSI MH10.8.2 per ISO/IEC 15434:2006) as used by DigiKey, Mouser, and other ECIA distributors. At minimum it extracts `P`, `1P`, `Q`, `K`, `1K`, and `9D`/`10D`. Realizes UJ-3.
**Consequences (testable):**
- A DigiKey DataMatrix yields the six named fields.

#### FR39: ECIA pre-populates a form
Parsed ECIA fields pre-populate a Product or Purchase creation form; the operator retains final control over all values. Realizes UJ-3.
**Consequences (testable):**
- Every pre-filled value is editable before save.

#### FR40: Unknown scan → creation form, never error
A scan resolving to no known record lands on a Product-creation form with the scanned identifier pre-attached and typed — never an error page. Realizes UJ-4.
**Consequences (testable):**
- An unmatched scan opens a creation form with the identifier attached and its type inferred; no error page.

#### FR41: Duplicate prevention on receipt
A scan resolving to an existing Product during receipt offers to add a Purchase to that Product rather than creating a duplicate; creating a duplicate requires explicit confirmation.
**Consequences (testable):**
- Scanning an existing Product in a receiving context offers "add purchase"; duplicate creation requires an explicit confirm.

### 4.9 Label Generation & Printing

**Description:** Labels are generated from records and submitted through the existing `lp` path, deterministic and reprintable, with dual barcode + human-readable encoding for direct-thermal durability. Realizes UJ-2. **Scope: 2×4 and 1×2 templates only; the 4×6 SATO is reserved for shipping** (Q3 resolved). **The existing subsystem renders 1D barcodes only** — the GS1 DataMatrix that FR12/FR44 require is a new 2D-rendering capability (Open Question Q7, a blocking spike gating this feature).

**Functional Requirements:**

#### FR42: Reuse existing `lp` submission path; add 2D rendering
Label printing reuses the app's existing label **submission** path (raster images submitted via `lp`); no new printer language, driver, or `lp` submission path is introduced. Because the existing generators render 1D barcodes only, a new 2D-symbology (GS1 DataMatrix) rendering capability — and likely a new rendering dependency — **is in scope**. Rendering and submission are server-side, so printing works identically from cart, tablet, or handheld. Realizes UJ-2.
**Consequences (testable):**
- A label is rendered and submitted through the existing `lp` path; no new submission path is added.
- A GS1 DataMatrix is rendered into the label raster (a capability not present in the existing 1D subsystem).

#### FR43: 2×4 and 1×2 templates
Catalog Label templates exist for the 2×4 and 1×2 media sizes. The catalog feature emits only to 1×2 and 2×4; the 4×6 media (already defined in the existing subsystem) remains reserved for shipping (Q3).
**Consequences (testable):**
- Both templates render valid labels; the catalog feature never emits a 4×6 catalog label.

#### FR44: Label content
Labels include the Product's Label Description, the Provenance Block (vendor, order date, Vendor SKU, unit price), and a GS1 DataMatrix encoding the namespaced Internal Identifier.
**Consequences (testable):**
- A rendered label contains all three regions.

#### FR45: Dual encoding
The Internal Identifier appears on the label in **both** barcode and human-readable form (direct-thermal media degrades; faded text remains readable when the barcode fails).
**Consequences (testable):**
- Both a scannable symbol and readable text of the Internal Identifier are present.

#### FR46: Reprint on demand
Any label is reprintable on demand from its Product record without re-entry. Realizes UJ-2.
**Consequences (testable):**
- Selecting reprint regenerates and sends the label with no data re-entry.

#### FR47: Canonical field order
Label content follows a canonical field order, with the Provenance Block last and structurally consistent across all labels.
**Consequences (testable):**
- Every generated label places the Provenance Block last in the same structure.

### 4.10 Order-Time Capture

**Description:** Metadata is captured while the vendor page is open, via a REST endpoint driven by an **Amazon-only** bookmarklet (Q5 resolved), idempotent against a client key, matching to existing Products by identifier. The capture-time listing price is taken as the price paid and the order date defaults to the capture date (H3-accepted simplification; both editable). Realizes UJ-1. API contract detailed in §7.

**Functional Requirements:**

#### FR48: Capture payload
The REST API accepts a product-and-purchase creation payload sufficient for a browser bookmarklet: vendor, Vendor SKU, listing title, unit price, quantity, source URL, and optional order date (defaulting server-side to the capture date if omitted). Realizes UJ-1.
**Consequences (testable):**
- Posting the payload creates a Purchase (and a Product if no identifier match) and returns the resulting Product URL.
- Omitting order date yields a Purchase dated the capture date.

#### FR49: Listing title as editable draft
The listing title populates the Label Description as an editable draft, expected to be edited down, not used verbatim.
**Consequences (testable):**
- After capture with no supplied description, the title appears in the Label Description field as editable draft text.

#### FR49a: Optional authored description at capture
The capture payload optionally accepts a user-authored Label Description; when supplied it replaces the listing-title draft rather than appending. Realizes UJ-1.
**Consequences (testable):**
- A payload with a description uses it instead of the title, still editable at receipt.

#### FR50: Match to existing product for de-dup
Where the submitted Vendor SKU matches an existing Product's Identifier **or** a prior Purchase's Vendor SKU (vendor-scoped), the API attaches the new Purchase to that Product rather than creating a new one. On first sight of an Amazon ASIN it also indexes the ASIN as an `ASIN` Identifier (FR11), so subsequent captures match by Identifier.
**Consequences (testable):**
- A second capture of the same ASIN attaches to the first Product; no duplicate Product is created and price history stays on one record.

#### FR51: Idempotent creation
Creation endpoints are idempotent with respect to a client-supplied request key: the same key returns the originally created record, and payload differences on a repeat key are ignored. This prevents a retry after a dropped connection from duplicating records.
**Consequences (testable):**
- The same request key submitted twice creates exactly one Purchase and both responses reference it.

### 4.11 Search & Retrieval

**Description:** Full-text search across catalog text and identifiers, faceted and bookmarkable, with direct-URL product views. Realizes UJ-4.

**Functional Requirements:**

#### FR52: Full-text search
The system provides full-text search across Label Descriptions, notes, manufacturer, MPN, and all Identifier values. Realizes UJ-4.
**Consequences (testable):**
- A term appearing in any of those fields returns the matching Product.

#### FR53: Faceted filtering
Search results are filterable by Category path prefix, by Tag, and by Effective-Low/Stock Status.
**Consequences (testable):**
- Each facet narrows results correctly.

#### FR54: Bookmarkable search state
Search state is URL-bookmarkable, consistent with existing app behavior.
**Consequences (testable):**
- Filter state is reflected in a shareable URL that reproduces the results.

#### FR55: Direct-URL product view
Product detail views are reachable by direct URL keyed on the authoritative Internal Identifier (`internal_id`). Realizes UJ-4.
**Consequences (testable):**
- The Internal-Identifier URL opens the correct Product.

### 4.12 Handheld & Touch Readiness

**Description:** Every action is reachable by touch; the scan-result view is self-sufficient at handheld widths; in-progress form state survives network interruptions. Realizes UJ-4. Supports the future Android tablet / Zebra TC access surfaces without foreclosing them.

**Functional Requirements:**

#### FR56: Touch equivalents for shortcuts
Every action available via keyboard shortcut has an equivalent control reachable by touch.
**Consequences (testable):**
- Each keyboard shortcut has a touch-reachable control at handheld width.

#### FR57: Self-sufficient scan-result view
The scan-result view is self-sufficient at handheld widths: it shows Product identity, Specifications, location, and Stock Status (with Effective-Low/On-Order indicators), and offers quantity adjustment and status flagging without navigation. Realizes UJ-4.
**Consequences (testable):**
- At 360 px, a resolved scan shows identity/Specifications/location/status and allows quantity + status changes inline.

#### FR58: No hover / no keyboard dependency
No interaction depends on hover state or on the presence of a physical keyboard.
**Consequences (testable):**
- All functions are reachable by touch alone.

#### FR59: Client-side form-state persistence
In-progress form state persists client-side, so a network interruption or wireless roam does not discard user-composed text.
**Consequences (testable):**
- A partially composed Label Description survives a dropped-and-restored connection.

### 4.13 Extensibility Hooks

**Description:** Product enrichment is structured behind one internal interface (no-op only in this phase), and REST creation requires no field unavailable during manual/bulk entry — so future enrichment and a future backfill importer become possible without restructuring or schema change. No such implementation is in scope.

**Functional Requirements:**

#### FR60: Enrichment interface (no-op)
Product enrichment is structured behind a single internal Enrichment Interface with defined input (typed Identifiers) and output (partial Product record). The only implementation this phase is a no-op.
**Consequences (testable):**
- Creation invokes the interface; the no-op returns an empty partial record and creation proceeds unchanged.
- Adding a future implementation requires no change to the creation path.

#### FR61: Creation requires no backfill-hostile field
Product and Purchase creation via the REST API requires no field unavailable during manual or bulk entry of pre-existing inventory, so a future backfill importer is possible without schema change.
**Consequences (testable):**
- Every required creation field is one obtainable for a pre-existing item with no order.

## 5. Cross-Cutting Non-Functional Requirements

*System-wide, not tied to one feature. Preserved from the source draft (NFR1–NFR11). No throughput/latency/scalability requirements apply; expected working set is hundreds to low-thousands of Products, one user. Optimization is out of scope unless a specific interaction becomes noticeably slow in practice.*

- **NFR1 — No new services.** Delivered within the existing Flask app, sharing its auth, deployment, database, and backup arrangements.
- **NFR2 — MariaDB JSON, no new datastore.** Schemaless/sparse Product Specifications use MariaDB JSON columns.
- **NFR3 — Alembic migrations.** All schema changes are Alembic migrations, per existing practice (via `manage.py db …`, not Flask-Migrate).
- **NFR4 — Single responsive codebase.** UI remains one Bootstrap 5.3.2 codebase, rendering acceptably from 360 px handheld through the 21.5" cart display.
- **NFR5 — Usable without quantity tracking.** The system remains fully usable for identification with quantity tracking entirely unused.
- **NFR6 — Test coverage.** New code carries unit coverage consistent with the existing suite, plus E2E coverage for scan-routing and label-generation paths specifically.
- **NFR7 — Pure, exhaustively-tested identifier logic.** Identifier normalization and check-digit logic are pure functions with exhaustive unit tests (errors there produce expensive-to-detect data corruption).
- **NFR8 — Graceful ECIA degradation.** The ECIA parser degrades gracefully on malformed/unrecognized input, surfacing the raw scan for manual handling rather than failing.
- **NFR9 — Metal stock unaffected; label subsystem extended.** Existing metal-stock functionality is unaffected; shared vocabularies (location, vendor) may be reused; shared schema is not restructured. The existing label subsystem is extended (notably with 2D-symbology rendering, FR42) and parameterized for new templates, not forked.
- **NFR10 — `requests`-only client compatibility.** The REST API remains consumable by the existing `requests`-only standalone client with no added dependencies.
- **NFR11 — Deterministic label rendering.** The same Product record produces an identical raster image.

## 6. Hardware & Environment Constraints

*The physical deployment shapes several requirements; captured here so downstream UX/architecture honor it.*

- **Primary access surface.** A rolling medical-style cart in the workshop: Raspberry Pi 5 (Linux), 21.5" ASUS 10-point touch monitor, keyboard, trackball, and a **Tera HW0009** barcode scanner (1D/2D, USB HID keyboard-wedge).
- **Future access surfaces (must not be foreclosed).** An Android tablet, or a Zebra TC-class Android data terminal with integrated imager via DataWedge keyboard-wedge emulation. Drives FR35, FR56–FR59.
- **Label printers.** Three SATO units — 4×6 (shipping), 2×4 (bin/box/bag), 1×2 (bin/box/bag). The **2×4 and 1×2 are direct-thermal only** (no thermal transfer). Catalog labels target the 2×4 and 1×2 only (Q3); the 4×6 is reserved for shipping. (The existing subsystem already defines all three SATO media sizes; the gap is 2D-symbology rendering, not media — see FR42/Q7.)
- **Direct-thermal durability.** Direct-thermal media degrades under multi-year shop exposure (solvent, UV). Mitigated by dual encoding (FR45), reprint (FR46), and evaluation of topcoated synthetic direct-thermal media (see §8 RISK-3).
- **Scale/throughput.** Tens of parts/month, single-digit orders/week, one operator, no concurrency. See §5.

## 7. Order-Time Capture API Surface

*The one externally-driven contract in this enhancement (bookmarklet + `requests`-only client). Capability-level here; wire-format detail is the architect's, in `addendum.md`.*

- **Contract.** A capture endpoint accepting the FR48 payload (vendor, Vendor SKU, listing title, unit price, quantity, source URL, optional order date) plus optional authored Label Description (FR49a) and a client request key (FR51).
- **Price & date semantics.** The submitted unit price is recorded as the price paid, and order date defaults to the capture date when omitted — both editable afterward (H3-accepted simplification; see §8 RISK-6).
- **Behavior.** Creates a Purchase; attaches to an existing Product when the Vendor SKU matches an existing Identifier or a prior Purchase's Vendor SKU, else creates a Product and indexes the ASIN as an Identifier (FR50/FR11); returns the resulting Product URL; idempotent on the request key (FR51).
- **Consumers.** An **Amazon-only** browser bookmarklet (UJ-1, Q5) and the existing `requests`-only standalone client (NFR10). DigiKey/Mouser are captured via 2D physical-label scan at receipt (§4.8), not the bookmarklet.
- **Backfill-forward.** No required field is unavailable during manual/bulk entry of pre-existing inventory (FR61); this leaves the door open for a future importer with no schema change, but no importer is in scope.

## 8. Risks & Mitigations

*Preserved from the source draft (RISK-1…RISK-5); RISK-6 added from the finalize gate.*

- **RISK-1 — LLM-generated label copy. Rejected.** Label descriptions frequently contain knowledge not in the source listing (drill sizes, mounting-hole dimensions, unit conversions). A plausible-but-wrong generated spec, printed on adhesive and trusted for years, is a silent, durable failure. Model use is acceptable only in the read/search path, where errors are visible and recoverable. (See §9 NG5.)
- **RISK-2 — Quantity-tracking scope creep.** Optional tracking is only viable while confined to the small set of items where a stockout has real cost; broad tracking drifts out of accuracy, and inaccurate counts are worse than absent ones. Mitigations: the Quantity Verified At staleness display (FR25), and receipt deliberately not touching the count (FR25/FR33).
- **RISK-3 — Direct-thermal media degradation.** The 2×4/1×2 SATO printers can't do thermal transfer; multi-year legibility in a solvent/UV shop environment is a known limitation. Mitigations: dual encoding (FR45), reprint (FR46), topcoated synthetic media evaluation.
- **RISK-4 — External GTIN databases.** Coverage for industrial/electronic components is poor and many unbranded imports carry no registered GTIN; any external lookup is opportunistic pre-fill only, never a dependency. Not in scope. (See §9 NG7.)
- **RISK-5 — Codebase provenance.** The existing app is, per its own README, vibe-coded and minimally reviewed; scope growth compounds differently in code that is not closely read. This enhancement is deliberately bounded to one entity cluster with a small surface area.
- **RISK-6 — Capture-time price ≠ price paid.** An Amazon product page shows the current listing price, which can drift from what was actually paid, and carries no order date. This PRD accepts the capture-time price as the recorded price and defaults order date to capture date (both operator-editable), on the assumption that capture happens at or near order time (UJ-1). If capture is habitually deferred, recorded prices will be approximate; the mitigation is that both fields remain editable at receipt.

## 9. Non-Goals (Explicit)

*Preserved from the source draft (NG1–NG10); NG11 added from the equivalence-scoping decision. Implementing agents must not introduce these.*

- **NG1 — No bulk-backfill tooling.** Ad-hoc manual entry of existing items must work (FR4) and the API must not preclude a future importer (FR61), but no importer, CSV ingest, or bulk-entry UI is in scope.
- **NG2 — No mandatory quantity tracking** or consumption-event logging workflow.
- **NG3 — Not replacing Trello** for shipment tracking, and no carrier-tracking integration.
- **NG4 — No automated/unattended scraping** of Amazon product pages.
- **NG5 — No LLM generation** of label descriptions or Specifications (RISK-1).
- **NG6 — No document store / NoSQL.** Schemaless data uses MariaDB JSON columns (NFR2).
- **NG7 — No vendor API integration** (DigiKey, Mouser, McMaster) for catalog enrichment; the Enrichment Interface (FR60) leaves the door open but ships a no-op only.
- **NG8 — No separate mobile UI codebase** (NFR4).
- **NG9 — No offline operation** with local persistence and sync.
- **NG10 — No user-defined internal part-numbering scheme.** Existing external identifiers are used wherever they exist; the generated Internal Identifier is not a user-facing part number.
- **NG11 — No substitutability graph.** Equivalent Products models only the "same manufacturer part, differently branded" equivalence class (§4.5). Looser "functionally substitutable / interchangeable-for-my-use" relationships (which are non-transitive and would need a pairwise graph) are out of scope.

## 10. MVP Scope

### 10.1 In Scope

- Product and Purchase entities distinct from metal stock, with CRUD and detail views (§4.1, §4.4).
- Typed multi-identifier system with GTIN normalization/validation (incl. GTIN-8 and the `GTIN_UNVALIDATED` type) and the GS1 AI-96 Internal Identifier encoding (§4.2).
- Materialized-path categories + free-form tags (§4.3).
- **Equivalent Product Groups** over the same-part equivalence class (§4.5) — newly in scope this phase.
- Optional quantity/location and manual Stock Status with derived Effective Low and a unified reorder view (§4.6, §4.7).
- Scan capture and structural routing incl. ECIA parsing (§4.8).
- Label generation on **2×4 and 1×2** templates via the existing `lp` submission path, **including new GS1 DataMatrix 2D rendering** (§4.9).
- Order-time capture API + **Amazon-only** bookmarklet (§4.10, §7).
- Full-text search, faceted filtering, direct-URL views, attachments (§4.11, FR5).
- Handheld/touch readiness (§4.12).
- Enrichment interface (no-op) and backfill-forward API shape (§4.13).

### 10.2 Out of Scope for MVP

- **4×6 label template** — reserved for shipping (Q3).
- **Multi-vendor bookmarklet** — DigiKey/Mouser via physical-label scan instead; manual entry acceptable for other web orders (Q5).
- **Substitutability grouping** beyond same-part equivalence (NG11).
- Everything in §9 Non-Goals (bulk backfill, LLM label copy, vendor API enrichment, Trello replacement, offline/sync, etc.).
- Any throughput/latency/scalability optimization (§5).

### 10.3 Provisional Delivery Sequencing

A provisional 10-epic decomposition with story-level acceptance criteria exists in `addendum.md` (carried from the source draft and extended for Equivalent Products). Recommended order front-loads the identification loop — *create a Product → print a label → scan it back* — and defers classification/stock features until the loop is proven in daily use. **Two blocking spikes must clear before their epics:** Q1 (scanner 2D round-trip) before scan-routing, and Q7 (2D-symbology rendering in the label subsystem) before label generation. This sequencing is advisory; `bmad-create-epics-and-stories` owns the final breakdown.

## 11. Success Metrics

*Hobby-scale, qualitative and usage-based (confirmed). The point is durable identification, not dashboards.*

**Primary**
- **SM-1** — *I keep using it.* I use the catalog weekly and don't abandon it after a month. Validates the whole enhancement.
- **SM-2** — *Every label-worthy new item is captured.* Items acquired after launch that would today get a hand-printed label instead get a durable Product record before shelving, rather than being hand-transcribed from a vendor page. Validates FR1–FR6, FR42–FR47, FR48–FR51.
- **SM-3** — *Offline identifiability.* Any such item is identifiable from its physical label alone, with no network and no live vendor page. Validates FR44–FR46, FR12–FR12d.

**Secondary**
- **SM-4** — *One scan resolves* (qualitative — no hard rate target). A GTIN, a distributor 2D label, or a system-printed label routes to the right record on the first scan, reliably enough that mis-scans are a rare annoyance rather than a routine one. Validates FR35–FR41.

**Counter-metrics (do not optimize)**
- **SM-C1** — *Do not chase backfill completeness.* Catalog coverage of the pre-existing inventory is explicitly not a success measure; driving it up would violate the identification-not-inventory framing (§1) and NG1. Counterbalances SM-2.
- **SM-C2** — *Do not maximize quantity-tracking coverage.* The share of Products with tracked quantity should stay small; broad tracking produces inaccurate counts that are worse than none (RISK-2). Counterbalances any temptation to "complete" stock data.

## 12. Open Questions

*Resolved during this PRD pass: Q3 (4×6 out of scope), Q4 (equivalent products in scope → §4.5), Q5 (Amazon-only bookmarklet), Q6 (internal-ID encoding — GS1 AI 96, see addendum), Q8 (equivalence model — narrowed to same-part class, §4.5). Remaining:*

1. **Q1 — Scanner 2D round-trip (BLOCKING SPIKE, gates scan-routing / Epic 4).** Does the Tera HW0009 support AIM symbology-identifier emission, and how does it transmit FNC1 (GS 0x1D / substitute char / stripped)? Critically, does it round-trip a GS1 DataMatrix carrying AI 96 `WIT…` recognizably under its actual config (data characters intact, not just FNC1 handling)? Pass/fail criterion; resolve before committing the internal-encoding design.
2. **Q2 — Attachment storage.** Filesystem-with-paths (assumed) vs. DB blobs? Confirm against existing backup arrangements. Also confirm the enforced exactly-one-owner invariant (FR5). *Architect decision.*
3. **Q7 — 2D rendering in the existing label subsystem (BLOCKING SPIKE, gates label generation / Epic 6).** The existing subsystem renders 1D only. Verify whether `pt-p710bt-label-maker` can emit a GS1 DataMatrix, or select a 2D-symbology generator/dependency, and confirm the template mechanism can be parameterized rather than forked (NFR9). Resolve before label work.

## 13. Assumptions Index

*Every `[ASSUMPTION]` in this document, for explicit confirmation:*

- **§2.2** — "Label-worthy" ≈ the ~half of received items that today get a hand-printed label; distributor-labeled items are catalogued for search/reorder but need no printed label.
- **§2.3 / §7 (RISK-6)** — Order-time capture happens at or near the moment of ordering, so the captured listing price ≈ the price paid; order date defaults to the capture date. Both remain editable.
- **§4.6 (FR27)** — The existing `field-suggestions` autocomplete source is extended to include Product locations so the location/vendor vocabulary is bidirectional; today it draws from metal-stock rows only.
