---
baseline_commit: b28c9cdabcaa944a7105e6abe13aeb487f417f42
---

# Story 1.4: Purchase recording and history

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the workshop operator,
I want to record purchases against a Product and see their history,
so that I can tell what I paid and where, over time.

## Acceptance Criteria

1. **Given** a Product with three Purchases across two vendors, **When** I open the Product detail view (`/products/<id>`), **Then** all its Purchases list in chronological order showing date, vendor, and unit price (FR20).
2. **And** the most recent prior unit price is shown in a labeled "Last paid" field (FR21).
3. **Given** a JSON payload describing a purchase, **When** I POST it to `POST /api/products/<id>/purchases` (`@csrf.exempt`), **Then** a Purchase is created and attached to that Product and the response is `201` with `{success: true, purchase: {…}, product_url: …}` (FR18, FR22).
4. **And** the endpoint returns the **fixed catalog error envelope** `{success: false, error: {code, message, field?}}` on failure — `404` when the Product does not exist, `400` on an invalid field — never a raw `500`/`IntegrityError` for those cases (AD-13, Conventions).
5. **And** the endpoint has a matching `record_purchase(product_id, purchase)` method + a frozen `RecordPurchaseResult` dataclass in `app/api_client.py`, using only `requests` (AD-13, NFR10).
6. **And** all purchase logic (history retrieval, last-paid, recording) lives in `CatalogService`; routes contain no ORM/SQL (AD-2). Existing behavior is unchanged (NFR9) and the full test suite passes with new service, route, and api_client tests.

## Scope Boundary — READ FIRST

This story adds **purchase-history display + "Last paid" on the product detail page** and a **basic REST endpoint to record a purchase against an existing Product** (FR22), plus its api_client mirror. It establishes the **first catalog JSON endpoint** and therefore the AD-13 request/response/error conventions the rest of the API inherits. No schema change (the `purchases` table exists from Story 1.2).

| Concern | Owned by | In 1.4? |
| --- | --- | --- |
| Purchase-history table + "Last paid" on `/products/<id>` | **Story 1.4 (this)** | ✅ |
| `POST /api/products/<id>/purchases` (attach to a known Product) + api_client method/dataclass | **Story 1.4 (this)** | ✅ |
| **Manual browser "Add Purchase" form** | later (or Epic 7) | ❌ confirmed — recording in 1.4 is the REST/api_client path per the AC ("service/REST path"); no manual UI form this story |
| `request_key` idempotency (same key → same record) | Epic 7 (7.4) | ❌ — 1.4's endpoint does not accept `request_key`; idempotent capture is Epic 7 |
| De-dup / attach-to-existing by Vendor SKU or ASIN; ASIN confirm-not-merge; create-a-Product-if-no-match | Epic 7 (7.1, 7.2) | ❌ — 1.4 attaches only to the `<id>` in the URL |
| Derived **On Order** / Recently Received signals (group-aware) | Epic 5 (5.4) / Epic 10 | ❌ — 1.4 shows `received_date` as a plain column; it does NOT compute the On-Order signal |
| `order_date` "defaults to capture date when omitted" | convention seeded here | ✅ — `record_purchase` defaults a missing `order_date` to today (Epic 7 reuses it) |
| "Last paid" group-awareness across Equivalent Products | Epic 10 | ❌ — 1.4 is per-Product |
| Enrichment hook on the record path | Epic 7 (7.5) | ❌ |

## Tasks / Subtasks

- [x] **Task 1 — Extend `CatalogService` with purchase methods (AC: #1, #2, #3, #6)**
  - [x] Added `List`/`date`/`Decimal` imports and `Purchase` to the `.database` import.
  - [x] `get_purchases_for_product` — dedicated query ordered `order_date.asc(), id.asc()`; returns `[]` for unknown product; never touches `product.purchases`.
  - [x] `get_last_paid_price` — most recent priced purchase (`unit_price.isnot(None)`, `order_date.desc(), id.desc()`), else `None`.
  - [x] `record_purchase(...) -> Optional[dict]` — verifies product exists (`None` if not), defaults `order_date` to today, cleans text fields, flush→snapshot→commit, returns the `to_dict()` snapshot; audit on success/error; no `request_key`.
  - [x] Established session lifecycle + flush-before-commit snapshot pattern reused.

- [x] **Task 2 — Purchase history + "Last paid" on the product detail page (AC: #1, #2)**
  - [x] `product_detail` now fetches `purchases` + `last_paid` (dedicated queries) and passes them; 404 guard preserved.
  - [x] `detail.html` "Purchases" card: "Last paid" (null-safe currency), chronological table (Order Date / Vendor / Unit Price / plain Received), empty-state "No purchases recorded.". Received shows the stored date only — no derived On-Order label.
  - [x] All currency/date cells null-safe.

- [x] **Task 3 — REST endpoint `POST /api/products/<int:product_id>/purchases` (AC: #3, #4, #6)**
  - [x] `@bp.route(...)` + `@csrf.exempt`; body via `request.get_json(silent=True) or {}`.
  - [x] Added `_catalog_json_error(code, message, status, field=None)` — the AD-13 **object** envelope helper (reused by future catalog routes).
  - [x] 404 (`not_found`) when product missing; boundary parsing → 400 with `error.field` for bad `unit_price`/`quantity`/`order_date`/`received_date`; typed values passed to `record_purchase`.
  - [x] Success → 201 `{success, purchase: <snapshot>, product_url}`; `None`/exception → 500 `server_error`. No template/flash/redirect.

- [x] **Task 4 — `api_client.py` mirror (AC: #5)**
  - [x] Added frozen `RecordPurchaseResult` (`purchase: dict|None` + trailing trio + `message` property that reads the object envelope) and registered it in `__all__`.
  - [x] Added `record_purchase(product_id, purchase)` mirroring `upload_photo` (path-param POST, `timeout`, HTTP≥400 → not success).
  - [x] Error extraction handles the object envelope (`error.message`/`code`/`field`) and falls back to `_safe_json`'s string form; `requests`-only, no new imports.

- [x] **Task 5 — Tests (AC: #1–#6)**
  - [x] `test_catalog_service.py` — +7 (record/attach, order-date default, missing→None, chronological order, empty, last-paid most-recent-priced/skip-null, none-when-unpriced).
  - [x] `test_product_routes.py` — +5 (detail history+last-paid, empty-state, POST 201+persist, 404 object envelope, 400 field).
  - [x] `test_api_client.py` — +3 (success URL/json/timeout, object-error message surfaced, non-JSON error).
  - [x] `venv/bin/nox -s tests` → **400 passed** (385 baseline + 15 new), 0 failures, no regressions. No MariaDB container needed.

## Dev Notes

### The live "detached relationship" hazard (flagged in 1.3, now real)
`get_product` returns a **detached** `Product` (session closed, no commit). Its docstring explicitly warns: *do not access `.purchases`* — a relationship lazy-load on a detached instance raises `DetachedInstanceError`. Story 1.4 therefore loads purchases with a **dedicated query** (`get_purchases_for_product`), never via `product.purchases`. This is the whole reason the method exists. (Story 1.2 wired the `Product.purchases` ↔ `Purchase.product` relationship, but it's for in-session use, not detached template rendering.)

### The AD-13 error envelope — this story sets the precedent
This is the **first catalog JSON endpoint**. Two things diverge from the legacy inventory JSON routes, and every future catalog route (Epic 7 especially) inherits what you establish here:
- **Success:** `{success: true, …}` + explicit HTTP status; body read via `request.get_json(silent=True) or {}`.
- **Errors:** the **object** envelope `{success: false, error: {code: str, message: str, field?: str}}`. Legacy routes (`api_create_items`, etc.) return `error` as a **plain string** — do NOT copy that. `WorkshopInventoryError.code` (`app/exceptions.py`) maps into `error.code`; `ValidationError.field` into the optional `field`. Build it once via the `_catalog_json_error` helper so 7.1's capture endpoint reuses it verbatim.
- Because the client sees `error` as a dict, `api_client.record_purchase` must read `body.get('error', {}).get('message')`, unlike `create_item`/`upload_photo` which read the legacy string `body.get('error')`. This is the single conscious mismatch with the existing client methods.

### api_client (AD-13 / NFR10) — mirror `UploadPhotoResult` + `upload_photo`
- `app/api_client.py` is **`requests`-only** (module docstring asserts it; only third-party import is `requests`). Add no dependencies. Register `RecordPurchaseResult` in `__all__`.
- Result dataclasses are `@dataclass(frozen=True)` with the trailing trio `errors: list[dict]`, `http_status: int`, `raw: dict` + a leading `success: bool`, plus a `message` property. `UploadPhotoResult` (single created object + `photo: dict|None`) is the exact template — model `purchase: dict|None` on it.
- `upload_photo` is the path-param POST template (`f'{base_url}/api/items/{ja_id}/photos'`, `json=…`, `timeout=self.timeout`; HTTP≥400 forces `success=False`). `_safe_json` is a shared static method — reuse as-is. `WorkshopInventoryClient.__init__(base_url, *, timeout=30.0, session=None)` — there is **no `auth` param**.

### Service layer (AD-2) — extend the established `CatalogService`
- Reuse the merged patterns: ctor/`sessionmaker`, per-method `try/except-rollback/finally-close`, flush-before-commit snapshot (`create_product`/`update_product`), `log_audit_operation(..., logger_name='mariadb_catalog_service')` (the logger is registered in `setup_logging` since the 1.3 review). Services return dict/list/`Optional[...]`/`bool` — never `StorageResult`.
- Money is `Decimal` (`unit_price` is `Numeric(10,2)`); never `float`. `Purchase.to_dict()` (from 1.2) already serializes `unit_price` via `float()` at the JSON boundary and ISO-formats the dates — reuse it for the snapshot/response.
- `order_date` default-to-today lives in `record_purchase` (the Dates convention). Do not add a DB default.

### Routes (AD-2) — extend `product_detail`, add the JSON endpoint
- `product_detail` currently: `get_product` → `abort(404)` → render. Add the two service reads and pass `purchases`/`last_paid`; keep the 404 guard. No ORM in the route.
- The JSON endpoint is `@csrf.exempt` (JSON APIs only; browser forms stay CSRF-protected — the 1.3 product forms are unchanged). Reuse the existing `_get_catalog_service()` helper.
- Parse/validate request types at the boundary (Decimal/int/date) and return 400 with `error.field`; keep parsing out of the service (the service takes typed values), mirroring how 1.3 validated in the route.

### Previous story intelligence (Stories 1.1–1.3, all merged)
- `created_at`/`updated_at` timestamp convention; flush-before-commit to avoid false-failure on post-commit refresh; `_clean()` blank→NULL; `session.expire_all()` (not `expunge_all`) when re-reading in a test; 1.3 code-review lessons already applied (input preservation, length validation, object-vs-string errors). Baseline suite: **385 passed** on `main`.
- 1.3's review **deferred** the per-request engine/pool creation (systemic, shared with `InventoryService`) to `deferred-work.md` — do not try to fix it here; just don't make it worse (reuse `_get_catalog_service()`).

### What this story must NOT break (NFR9)
- Additive: new `CatalogService` methods, a modified `product_detail` + one new JSON route in `routes.py`, an extended `detail.html`, and new `api_client` symbols. Do not touch inventory routes/templates, `app/database.py`, `app/models.py`, or existing api_client methods.
- No schema change, no migration, no dependency change.

### Testing standards
- `venv/bin/nox -s tests` (never bare pytest; `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`). SQLite via `test_storage`, network blocked. Route tests: `create_app(TestConfig, storage_backend=test_storage)` + `client` (CSRF disabled in tests). api_client tests: `MagicMock(spec=requests.Session)`, assert `session.post.call_args` (URL/json/timeout) — never a live server. No MariaDB container needed (no schema/migration).

### Project Structure Notes
- Modified: `app/mariadb_catalog_service.py`, `app/main/routes.py`, `app/templates/product/detail.html`, `app/api_client.py`. New tests appended to `tests/unit/test_catalog_service.py`, `tests/unit/test_product_routes.py`, `tests/unit/test_api_client.py`. `app/database.py`/`app/models.py` unchanged. Matches the spine Structural Seed (`api_client.py + capture/product methods + frozen result dataclasses`; `main/routes.py + catalog JSON endpoints`).

### References
- [Source: epics.md#Story 1.4: Purchase recording and history] (AC, FR18/FR20/FR21/FR22)
- [Source: ARCHITECTURE-SPINE.md#AD-13] (endpoint ↔ api_client method + frozen dataclass; `@csrf.exempt`; fixed error envelope) · [#AD-2] (service owns logic; per-method session lifecycle; audit) · [#AD-3] (`purchases.product_id` FK)
- [Source: ARCHITECTURE-SPINE.md#Consistency Conventions] ("API success" and "API errors" rows — the exact success/`{code,message,field?}` envelopes; Money = Decimal; Dates = tolerant parse + `order_date` server-default)
- [Source: 1-2-purchase-entity-and-migration.md] (`Purchase` columns, `to_dict()`, `Product.purchases`↔`Purchase.product`) · [1-3-product-create-edit-detail.md] (CatalogService/route/detail patterns; deferred engine item)
- [Existing code: app/mariadb_catalog_service.py:60-161 (merged service — ctor, get_product detached-warning, flush-before-commit); app/api_client.py:46-58,84-96 (result dataclasses), :426-537 (`upload_photo` path-param POST), :538-561 (`_safe_json`), :108-117 (ctor, no auth); app/main/routes.py:464-548 (legacy `@csrf.exempt` JSON route — note its STRING error, to diverge from); app/exceptions.py:8-15 (`WorkshopInventoryError(message, code, details)`), :17-28 (`ValidationError.field`)]
- [Existing code: app/templates/product/detail.html (extend), tests/unit/test_api_client.py:62-109 (session-mock idiom), tests/unit/test_routes.py:142-287 (client JSON-route idiom)]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Opus 4.8, 1M context) — bmad-dev-story workflow.

### Debug Log References

- No migration/schema change (pure app-layer). No MariaDB container run.
- Route + api_client tests exercise the full JSON contract end-to-end (Flask `client` and mocked `requests.Session` respectively).

### Completion Notes List

- Added purchase history + "Last paid" to the product detail page, and the first catalog JSON endpoint (`POST /api/products/<id>/purchases`) with its `api_client` mirror.
- **Detached-relationship hazard handled:** purchases are loaded with dedicated `CatalogService` queries (`get_purchases_for_product`, `get_last_paid_price`), never via `product.purchases` on the detached `Product` — the pitfall `get_product`'s docstring warned about since 1.2/1.3.
- **AD-13 precedent set:** introduced `_catalog_json_error(code, message, status, field=None)` producing the OBJECT error envelope `{success:false, error:{code, message, field?}}` — distinct from the legacy inventory routes' string `error`. Epic 7's capture endpoint reuses this helper.
- **api_client divergence handled:** `RecordPurchaseResult.message` and `record_purchase` read the object envelope (`error.message`) rather than the legacy string `body.get('error')`, while still degrading gracefully to `_safe_json`'s string fallback. `requests`-only (NFR10).
- `order_date` defaults to today in `record_purchase` (server-side capture-date convention seeded here; Epic 7 reuses).
- Scope honored: no manual browser add-purchase form (per Jason), no `request_key`/idempotency/de-dup/ASIN (Epic 7), no derived On-Order signal (Epic 5).
- All 6 ACs satisfied; full suite **400 passed**; inventory UI/routes, `app/database.py`, `app/models.py`, and existing api_client methods unchanged (NFR9).

### File List

- `app/mariadb_catalog_service.py` (modified) — `get_purchases_for_product`, `get_last_paid_price`, `record_purchase`; `Purchase`/`List`/`date`/`Decimal` imports.
- `app/main/routes.py` (modified) — `product_detail` fetches purchases/last_paid; new `api_record_purchase` JSON route; `_catalog_json_error` helper; `date` import.
- `app/templates/product/detail.html` (modified) — Purchases card (history table + "Last paid" + empty-state).
- `app/api_client.py` (modified) — `RecordPurchaseResult` dataclass + `record_purchase` method + `__all__` entry.
- `tests/unit/test_catalog_service.py` (modified) — +7 purchase tests.
- `tests/unit/test_product_routes.py` (modified) — +5 purchase/endpoint tests.
- `tests/unit/test_api_client.py` (modified) — +3 `record_purchase` tests.
- `_bmad-output/implementation-artifacts/1-4-purchase-recording-and-history.md`, `sprint-status.yaml` (modified) — tracking.

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-24 | Story 1.4 implemented: purchase history + "Last paid" on the product detail page; `POST /api/products/<id>/purchases` (first catalog JSON endpoint, AD-13 object error envelope); `api_client.record_purchase` + `RecordPurchaseResult`; +15 tests. No schema change. Full suite green (400 passed). Status → review. |
