# Epic 4 Context: Scan Routing & ECIA

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

This epic makes every barcode in the shop resolve correctly from a single keyboard-wedge scan — a label this system printed, a manufacturer GTIN, or a DigiKey/Mouser distributor 2D label — with no scanner-specific driver, no dead ends, and no error pages. It closes the identification loop opened by Epics 1 and 2: raw scan text is classified by structure in a fixed precedence by a pure classifier, resolved against the catalog by the service, and routed in the UI to the right next action (product view, pre-filled create form, or add-a-purchase). It also introduces the single shared free-text search entrypoint that the no-match fallthrough uses and that Epic 8's search later reuses, and adds ECIA/MH10.8.2 distributor-label parsing that degrades gracefully instead of raising.

## Stories

- Story 4.1: Wedge scan capture
- Story 4.2: Pure scan classifier
- Story 4.3: Service scan resolution
- Story 4.4: ECIA distributor-label parsing
- Story 4.5: Scan outcome routing in the UI

## Requirements & Constraints

- Scanner input arrives as plain keyboard-wedge keystrokes terminated by Enter and is captured wherever the scan field has focus. No scanner-specific driver, API, or device configuration may be required — both the deployed Tera HW0009 and future DataWedge-style Android terminals must work unchanged.
- Routing is decided by structural inspection in a fixed precedence: (1) internal GS1 AI-96 + configured token payload; (2) ISO/IEC 15434 format-06 envelope → ECIA parse; (3) all-digit value of length 8 or 12–14 with a valid GTIN check digit → normalized GTIN lookup; (4) anything else → free-text search.
- No scan ever dead-ends. A structurally valid GTIN that matches no Product falls through to free-text search within the same scan; a scan matching nothing at all opens a Product-creation form with the scanned identifier pre-attached and its type inferred — never an error page.
- A parsed distributor scan with no matching product opens the create form with MPN, quantity, and order references pre-filled, and every pre-filled value stays editable.
- A scan resolving to an existing Product in a receiving context offers to add a Purchase to that Product; creating a duplicate Product instead requires an explicit confirmation.
- ECIA parsing extracts at minimum the customer part number, supplier part number, quantity, customer order number, supplier order number, and date data identifiers (`P`, `1P`, `Q`, `K`, `1K`, `9D`/`10D`). A malformed or unrecognized envelope surfaces the raw scan for manual handling and never raises.
- If an AIM symbology identifier is ever present, it only narrows the symbology class — the payload's AI/token still selects the handler, since the same symbology denotes both internal and manufacturer GTIN symbols. The deployed scanner emits no AIM identifier, so this path is optional and must not be required for correct routing.
- Classification logic is a pure function with exhaustive unit tests. Scan routing additionally carries E2E coverage. Existing metal-stock scanning (JA-ID / location codes) must remain unaffected — scanner-level settings are global and must not be changed.

## Technical Decisions

- **Classifier/resolver split (AD-4, AD-5, AD-15).** `app/utils/scan_router.py` is the sole classifier and is pure — no Flask, no DB imports. It owns the precedence order and never performs lookup. DB lookup and the no-match fallthrough live in `mariadb_catalog_service.resolve_scan(raw)`. Client JS never classifies; it posts raw text and acts on the routed outcome.
- **Two frozen shapes (AD-15).** Both live in `app/models.py` and are the only contract every scan consumer (this epic, Epic 7, Epic 9) depends on: `ScanClassification{ kind ∈ internal|ecia|gtin|free_text; normalized_value (14-digit for gtin, token-stripped id for internal, else None); ecia_fields: dict|None keyed exactly P,1P,Q,K,1K,9D,10D; raw }` and `ScanResolution{ classification, product|None, free_text_hits }`.
- **Internal recognition is delegated, not reimplemented (AD-16).** Rule-1 recognition calls `gs1.decode()`; the classifier must not pattern-match the AI or token itself. The AI number and token come from the single named config pair read in the service and passed explicitly into the pure function — no literal defaults anywhere, so one config change flips both encoder and router. `decode()` already absorbs FNC1 transmission variance; the deployed scanner strips FNC1 and emits the bare `<ai><token><id>` string, recognized structurally by its prefix.
- **Single search entrypoint (AD-17).** `mariadb_catalog_service.search_products(query, filters)` is introduced in this epic as the sole free-text search implementation, covering identifier values, descriptions, notes, manufacturer, and MPN. Both the scan fallthrough here and Epic 8's search page call it — no second search path. The search *mechanism* (LIKE vs FULLTEXT vs ranking) is deliberately deferred to Epic 8; pick the simplest thing that satisfies the fallthrough now, behind this fixed entrypoint.
- **GTIN handling reuses Epic 2.** Check-digit validation and normalization to 14 digits come from the existing pure `gtin.py`; the classifier and resolver never re-derive them. Lookup is against the normalized-14 namespace.
- **Graceful ECIA degradation (NFR8).** A malformed format-06 envelope classifies as `free_text` carrying the raw scan. The parser raises nothing on any input.
- **Layering (AD-1, AD-2).** No ORM or SQL in routes; routes call the service and build the standard `{success, …}` envelope, with the fixed error shape `{success:false, error:{code, message, field?}}` for JSON endpoints. JSON routes are `@csrf.exempt`.
- **No new schema is implied by this epic.** If any migration proves necessary it is an Alembic migration chained from the current HEAD via `manage.py db`; metal-stock tables stay untouched.

## UX & Interaction Patterns

- There is no separate UX design contract; the UI is the existing responsive Bootstrap 5.3.2 codebase and must stay usable from 360 px up.
- The scan field is the single input for all scan kinds — the operator never selects a mode or tells the system what kind of barcode is coming.
- Every scan outcome is a landing, not an error: a match lands on the record, a miss lands on a pre-filled create form, an ambiguous scan lands on search results. Pre-filled values are always editable.
- Destructive-by-accident outcomes require explicit confirmation — specifically, creating a second Product when a scan already matched an existing one during receiving.

## Cross-Story Dependencies

- Depends on Epic 2: `gs1.decode()` for internal-payload recognition and foreign-payload rejection, `gtin.py` for check-digit validation and 14-digit normalization, and the typed-identifier model for lookup and for attaching a scanned identifier to a new Product.
- Depends on Epic 1 for the Product/Purchase entities and the create forms this epic pre-fills.
- Story 4.2 (classifier) is a prerequisite for 4.3 (resolution), which is a prerequisite for 4.5 (UI routing). Story 4.4's parser feeds the `ecia_fields` consumed by 4.5's pre-filled create form.
- Story 4.3 introduces `search_products()`, which Epic 8 consumes directly for full-text search and faceted filtering; design it as a shared method, not a scan-specific helper.
- Epic 7 (order-time capture) and Epic 9 (self-sufficient scan-result view at handheld width) depend on the `ScanClassification`/`ScanResolution` shapes fixed here.
