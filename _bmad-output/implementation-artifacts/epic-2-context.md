# Epic 2 Context: Identifiers & Internal Encoding

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

This epic makes a Product reachable by any code printed on it, its packaging, or its vendor's label, and gives every Product a collision-proof, system-generated internal identifier encoded as a GS1 DataMatrix (AI 96 + a `WIT` token). It builds on the Epic 1 Product/Purchase foundation by adding typed identifiers with scoped uniqueness, GTIN normalization and check-digit validation, ASIN handling that never lets a reused marketplace code corrupt product identity, and a self-identifying internal-ID grammar that a scanner can distinguish from any foreign barcode. The normalization, encoding, and decoding logic here is pure and exhaustively tested, and it is the shared substrate that the scan-routing (Epic 4) and label (Epic 6) epics later depend on.

## Stories

- Story 2.1: Typed identifier entity and uniqueness
- Story 2.2: GTIN normalization and check-digit validation
- Story 2.3: ASIN identity handling
- Story 2.4: Internal identifier generation and GS1 AI-96 encoding
- Story 2.5: Foreign-payload rejection and ownership text

## Requirements & Constraints

- A Product may carry multiple typed identifiers: `GTIN`, `GTIN_UNVALIDATED`, `ASIN`, `FNSKU`, `MPN`, `VENDOR_SKU`, `INTERNAL`. Manufacturer and MPN remain optional; product identity must never depend on an ASIN (a reassigned ASIN must not change which product is which).
- `(type, value)` is unique within its scope. Attempting to add a duplicate must surface a caught domain error that names the conflicting Product — never a raw integrity error leaking to the caller.
- GTIN values are check-digit validated and stored normalized to 14 digits; GTIN-8, UPC-A (12), EAN-13 (13), and GTIN-14 forms of one product all resolve to the same 14-digit key and the same Product.
- A value that fails GTIN check-digit validation is rejected as a GTIN with a clear message, and may optionally be kept as `GTIN_UNVALIDATED` — stored unnormalized and outside the GTIN namespace so it can never block a later valid GTIN.
- On a captured Amazon purchase, the ASIN is recorded on the Purchase as its `vendor_sku` and additionally indexed as an `ASIN` identifier for de-dup. Indexing an ASIN that already exists on a different product is rejected and surfaced, not silently attached.
- Every Product receives a unique `internal_id`. The internal identifier appears (in later epics) in both machine-readable and human-readable label regions. Ownership/return information is human-readable label text only — no 43xx element strings are ever encoded.
- Normalization, encoding, decoding, and check-digit logic are pure functions with exhaustive unit tests (no Flask/DB imports).

## Technical Decisions

- **Pure utils (AD-4, AD-7, AD-8, AD-16).** Domain logic lives in module-level pure functions under `app/utils/`: `gtin.py` (normalize + check-digit), `internal_id.py` (candidate generator), and `gs1.py` (AI-96 encode + decode, FNC1 grammar). No Flask or DB imports; each module is its own single source of truth; the service calls them and routes/templates never re-derive.
- **Entity pattern (AD-1, AD-3).** `ProductIdentifier` is one ORM class on the shared `Base` in `app/database.py`; enums/value objects live in `app/models.py`. All mutation/query goes through `mariadb_catalog_service.py`. Every table has an integer surrogate PK. `products.internal_id` is a separate `UNIQUE` business key used for URLs/labels/scan lookup — never a foreign-key join target.
- **Uniqueness scoping (AD-9).** `GTIN` and `INTERNAL` are globally unique (unscoped). `VENDOR_SKU`, `ASIN`, and `FNSKU` are vendor-scoped. Uniqueness is enforced by DB `UNIQUE` constraints; the service catches violations and converts them to domain errors rather than propagating `IntegrityError`.
- **GTIN namespace (AD-7).** Normalized-14, check-digit-valid GTINs form the global uniqueness namespace. Check-digit failures, if retained, are quarantined as `GTIN_UNVALIDATED` — unnormalized, outside that namespace.
- **ASIN confirm-not-merge (AD-9).** An ASIN match attaches automatically only when manufacturer/MPN agree (or are absent on both); when they differ it requires explicit operator confirmation — never a silent merge — guarding against documented ASIN reuse.
- **Internal-ID authority (AD-8).** `internal_id.py` yields a *candidate* (pure). The create-service is the *sole writer*: it performs the insert and owns retry-on-`UNIQUE`-collision; the column carries no generating DB default. Any `INTERNAL`-type `ProductIdentifier` row is written in the same transactional step from the same value and is a derived read index, not independently editable.
- **GS1 grammar, one config source (AD-16).** `gs1.py` exposes `encode(internal_id, *, ai, token)` and `decode(raw, *, ai, token) -> InternalPayload|None`. The element string is FNC1-first, AI `96`, single data field = token `WIT` + `internal_id`, no separator, no second AI. The AI number and token come from one named config pair (`GS1_INTERNAL_AI`, `GS1_INTERNAL_TOKEN`) read in the service and passed explicitly into both functions — no literal defaults, so one config change flips both encoder and router.
- **Self-identifying decode / FNC1 tolerance (AD-16, FR37a).** `decode()` absorbs FNC1 transmission variance (GS `0x1D`, a configured substitute, or stripped). Per the resolved hardware spike, the deployed scanner strips FNC1 and emits no AIM identifier, so an internal symbol arrives as the bare string `<ai><token><id>` (e.g. `96WITTEST0001`); `decode()` recognizes it structurally by the `96WIT` (AI+token) prefix. A payload whose data field does not begin with the configured token is not treated as an internal identifier — a coincidental foreign AI-96 barcode must never resolve to one of these products.
- **Money/measures convention.** Use `decimal.Decimal` with `ROUND_HALF_UP` for prices, never `float`.
- **Migrations (AD-14).** Schema changes are Alembic migrations chained from the current HEAD; existing metal-stock tables and behavior stay untouched.

## Cross-Story Dependencies

- Builds on Epic 1 (Products, Purchases, and the create-service that is the sole `internal_id` writer).
- Story 2.4 (internal-ID generation) and the `gs1.py` grammar are prerequisites consumed downstream: Epic 4 scan routing delegates internal-symbol recognition to `gs1.decode()`, and Epic 6 label rendering calls `gs1.encode()`. Story 2.5's foreign-payload rejection is the safety property those consumers rely on.
- Identifier uniqueness scoping (AD-9) established here is reused by Epic 7 order-time capture de-dup.
- ASIN indexing (Story 2.3) is exercised end-to-end by Epic 7 capture.
