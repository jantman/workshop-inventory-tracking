---
baseline_commit: 3de56609a6223da14bdb3a5ee8f2253a2484f85f
---

# Story 1.3: Product create/edit/detail

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the workshop operator,
I want to create, edit, and view a Product from the UI,
so that I can catalog an item with as little or as much detail as I have.

## Acceptance Criteria

1. **Given** the product create form, **When** I create a Product with only a Label Description and no other fields, **Then** it saves successfully with `manufacturer`, `mpn`, `category_path`, `notes`, and all other optional fields empty (FR3, FR4).
2. **And** creation requires no field that would be unavailable for a pre-existing item with no order — the only required field is the Label Description, which is always typeable (FR61).
3. **Given** an existing Product, **When** I edit its Label Description and save, **Then** the change persists.
4. **And** the Product's detail view is reachable by a direct URL (`/products/<id>`), rendering its stored fields (FR6).
5. **And** all catalog business logic (create, read, update) lives in a new `app/mariadb_catalog_service.py` service — routes contain no ORM/SQL and delegate to it; mutations call `log_audit_operation` (AD-2).
6. **And** existing metal-stock UI, routes, and behavior are unchanged (NFR9); the full test suite passes; new unit tests cover the service and new route/integration tests cover the create/edit/detail flows.

## Scope Boundary — READ FIRST

This story delivers **browser-based create / edit / detail for Products only**, on the existing Bootstrap UI, backed by a new catalog service. It is the first story to add routes, a service, and templates for the catalog — so it establishes patterns Epics 2–10 build on. **No schema change** (the `products` table already exists from Story 1.1).

| Concern | Owned by | In 1.3? |
| --- | --- | --- |
| `CatalogService` create/get/update + product create/edit/detail pages | **Story 1.3 (this)** | ✅ |
| Product **list / browse / search / facets** | Epic 8 (8.1–8.3) | ❌ — 1.3 adds only a nav link to "Add Product"; existing products are reached by direct URL |
| `internal_id` generation + `internal_id`-keyed detail URL | Epic 2 (2.4) + Epic 8 (8.3) | ❌ — 1.3 keys the detail URL on the integer PK `id` |
| **Specifications (`attributes`) editing UI** | later | ❌ — 1.3 does not add a JSON/spec editor to the form; the detail page *displays* `attributes` read-only if present |
| Category **autocomplete-with-create + `normalize_category_path`** | Epic 3 (3.1) | ❌ — 1.3 uses a plain free-text `category_path` field, stored as entered (trimmed) |
| Purchase history + "Last paid" on the product view | Story 1.4 | ❌ |
| Attachments on the product view | Story 1.5 | ❌ |
| Enrichment hook on the create path | Story 7.5 | ❌ — the create-service established here is the seam 7.5 and 2.4 later extend |
| REST/JSON create endpoint (`@csrf.exempt`, fixed envelope) | Epic 7 (7.1) | ❌ — 1.3 is browser HTML forms only (CSRF-protected, flash+redirect) |
| Tags | Epic 3 (3.3) | ❌ |

Ship exactly: the service, three routes (+ nav link), three templates, and their tests. Nothing else.

## Tasks / Subtasks

- [x] **Task 1 — Create `app/mariadb_catalog_service.py` (`CatalogService`) (AC: #1, #3, #5)**
  - [x] Modeled on `MariaDBMaterialsAdminService`/`InventoryService`: `__init__(storage=None)` → `getattr(storage,'engine',None) or self._create_engine()` → `sessionmaker`; `_create_engine()` from `Config`.
  - [x] Per-method `session = self.Session()` / `try` / `except`(rollback on mutations) / `finally` close.
  - [x] `get_product(id) -> Optional[Product]` (read-only query, returns detached ORM object or None; no relationship access).
  - [x] `create_product(*, ...) -> Optional[int]` (add+commit+audit, returns new id captured pre-close; None on failure).
  - [x] `update_product(id, **fields) -> bool` (load-or-False, set recognized fields, commit; `updated_at` auto-bumps via `onupdate`).
  - [x] `_clean()` trims strings and coerces blanks to `None`; only `_PRODUCT_FIELDS` applied on update; `app/models.py` untouched.

- [x] **Task 2 — Add routes to `app/main/routes.py` (main blueprint) (AC: #1, #3, #4, #5)**
  - [x] `_get_catalog_service()` helper added beside `_get_inventory_service()`; imported `CatalogService` + `Product` (`abort` already imported).
  - [x] `product_add` (`/products/add`, GET/POST, CSRF-protected) — requires non-empty `description`, re-renders with `validation_errors` + `form_data` on blank, else creates and redirects to detail.
  - [x] `product_detail` (`/products/<int:product_id>`) — `abort(404)` if missing, else renders `detail.html`.
  - [x] `product_edit` (`/products/edit/<int:product_id>`, GET/POST) — `abort(404)` if missing; requires `description`; updates and redirects to detail.
  - [x] All three are server-rendered HTML (render/flash/redirect); no JSON envelope, no `@csrf.exempt`.

- [x] **Task 3 — Templates under `app/templates/product/` (AC: #1, #3, #4)**
  - [x] `add.html` — extends base, `<form method="POST" novalidate>` + hidden `csrf_token()`, Bootstrap card, fields (description required, manufacturer, mpn, category_path, notes), `is-invalid`/`d-block` validation display, preserves `form_data`.
  - [x] `edit.html` — same form pre-filled from `product.*`; Cancel → detail.
  - [x] `detail.html` — read-only `<dl>` of all fields, Specifications rendered only if `product.attributes`, timestamps, Edit button.
  - [x] Added a "Products" navbar dropdown in `base.html` with "Add Product" → `main.product_add`.
  - [x] No autocomplete wired (not needed for 1.3's fields).

- [x] **Task 4 — Tests (AC: #1, #3, #4, #6)**
  - [x] `tests/unit/test_catalog_service.py` — 7 tests (create-minimal/full/blank-coercion, get-missing, update-persist/missing/blank-coerce).
  - [x] `tests/unit/test_product_routes.py` — 9 tests (add form; create→302→detail; blank re-render; detail 404 + fields; edit prefilled/404/persist/blank).
  - [x] `venv/bin/nox -s tests` → **383 passed** (367 baseline + 16 new), 0 failures, no regressions. No MariaDB container needed (no schema change).
  - [x] E2E not added (optional for 1.3; NFR6 prioritizes scan/label E2E, delivered later). Route tests exercise the full render/flow via the Flask test client.
  - [x] Screenshots: product pages were **not** added to `tests/e2e/screenshot_config.yaml`, so no screenshot regen is required for this story (noted in Completion Notes).

### Review Findings

- [x] [Review][Patch] Edit POST non-success paths discard typed input (blank-description re-render fills from `product.*` not `form_data`; `not ok`/exception branches redirect and wipe input; error-branch title also differs from GET) [app/main/routes.py:815-838, app/templates/product/edit.html]
- [x] [Review][Patch] DB errors masquerade as 404 — `get_product` swallows all exceptions to `None`, routes `abort(404)` for products that exist [app/mariadb_catalog_service.py:61-79]
- [x] [Review][Patch] No length validation: >255-char description/manufacturer/mpn (>512 category) fails generically on strict MariaDB, succeeds on SQLite tests; templates lack `maxlength` [app/main/routes.py:747-838, app/templates/product/*.html]
- [x] [Review][Patch] Partial POST nulls omitted fields — `update_product` receives `None` for absent form keys and wipes stored values; pass only keys present in the form [app/main/routes.py:820-828]
- [x] [Review][Patch] `detail.html` 500s when `attributes` JSON is a non-dict (list/scalar passes the `{% if %}` guard, `.items()` raises) [app/templates/product/detail.html:35-44]
- [x] [Review][Patch] `create_product` can report failure after a successful commit (post-commit `id`/`to_dict()` refresh may fail → retry duplicates); flush + capture before commit [app/mariadb_catalog_service.py:100-116]
- [x] [Review][Patch] `mariadb_catalog_service` logger not registered in `setup_logging` — catalog audit records bypass the audit-enrichment handler config; route-level input audits also tagged with the service logger name [app/logging_config.py:127-145, app/main/routes.py:754,811]
- [x] [Review][Patch] Weak test assertions — `updated_at >= before` is tautological at second resolution; blank-create route test doesn't assert the error message rendered [tests/unit/test_catalog_service.py, tests/unit/test_product_routes.py]
- [x] [Review][Patch] Unused `Product` import in routes [app/main/routes.py:13]
- [x] [Review][Defer] Per-request SQLAlchemy engine/pool creation — unconnected `MariaDBStorage()` in production makes `CatalogService` (and the pre-existing `InventoryService`) build an undisposed engine from `Config` per request, ignoring `storage.database_url` [app/mariadb_catalog_service.py:51-58] — deferred, pre-existing systemic pattern shared with InventoryService; needs an app-level engine-sharing fix covering both services

## Dev Notes

### Previous story intelligence — carried from Stories 1.1 & 1.2 (merged)
- **`created_at`/`updated_at`** is the confirmed catalog timestamp convention; `Product`/`Purchase` already use it. `updated_at` auto-bumps via the model's `onupdate=func.now()` — don't set it manually in `update_product`.
- **Detached-instance pitfall (hit in 1.2 tests):** after `session.commit()`, attributes expire; after the session closes, the instance is detached and lazy access raises `DetachedInstanceError`. That's why `create_product` returns the **int id** (captured pre-close), and why `get_product` (a read-only query with no commit) can safely return the ORM object for the route to render its scalar columns. In tests, use `session.expire_all()` (keeps objects bound) rather than `expunge_all()` when re-reading.
- Baseline: full unit suite is **367 passed** on `main`. Keep it green.
- **This story has NO migration** — `products` already exists (`c10caa1431c6`). AD-14/MariaDB-container verification does not apply here.

### Service layer (AD-2) — mirror `MariaDBMaterialsAdminService` / `InventoryService`
- Class + wiring (grounded references): `InventoryService.__init__` (`mariadb_inventory_service.py:130-148`) — `self.engine = storage.engine or self._create_engine()`, `self.Session = sessionmaker(bind=self.engine)`. Use the **safer** `getattr(storage, 'engine', None)` form from the admin service (`mariadb_materials_admin_service.py:42`), because a freshly-built `MariaDBStorage()` has `engine=None` until `connect()`.
- Method shapes to copy: read → `get_active_item` (`mariadb_inventory_service.py:150-187`, returns object or `None`); create → `add_item` (`:1058-1167`, `session.add` + `commit` + audit); update → `update_item` (`:930-1056`, load-mutate-commit-audit, returns `bool`).
- `log_audit_operation(operation_name, phase, *, item_id=None, item_after=None, error_details=None, logger_name='mariadb_catalog_service')` — defined `app/logging_config.py:250`; import lazily inside methods (`from .logging_config import log_audit_operation`); phases `'input'|'success'|'error'`; call on every mutation. Use a `product_id`/id string for `item_id`.
- Services return domain objects / `bool` / `None` / int id — **never** a `StorageResult` (that dataclass is the storage-backend contract, `app/storage.py:5-11`). The route picks the HTTP status and renders.
- Exceptions available in `app/exceptions.py`: `ValidationError`, `ItemNotFoundError`, `DuplicateItemError`, … (all subclass `WorkshopInventoryError(message, code, details)`).

### Routes (AD-2) — mirror `inventory_add` / `inventory_edit`
- Blueprint: `main` (`app/main/__init__.py`, root-mounted). Products are first-class inventory, so they belong in `main` alongside `/inventory/...`, not the `/admin`-prefixed blueprint. Attach routes by adding functions to `app/main/routes.py` decorated with `@bp.route`.
- Per-request service construction: `service = _get_catalog_service()` at the top of each handler (no `g`-caching), exactly like `service = _get_inventory_service()` (`routes.py:498` etc.). The `_get_storage_backend()` indirection (`routes.py:20-28`) is what lets tests inject SQLite via `current_app.config['STORAGE_BACKEND']` — always go through it.
- CSRF: browser HTML form POSTs are **CSRF-protected** (Flask-WTF `csrf.init_app` is global) — the template must include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>` (as `inventory/add.html:31` does). Do **not** add `@csrf.exempt` (that is only for JSON APIs, e.g. `routes.py:460`). Tests disable CSRF via `TestConfig.WTF_CSRF_ENABLED=False`, so `client.post` works without a token.
- Error/flash idiom: wrap bodies in `try/except Exception as e:` → `current_app.logger.error(f'...: {e}')` + `flash(msg, 'error')` + redirect (HTML routes). Missing product on a GET resource URL → `abort(404)` (renders `templates/errors/` via the registered `create_error_handlers`).

### Templates (Bootstrap 5.3.2) — mirror `inventory/add.html` & `inventory/edit.html`
- `base.html` exposes only two blocks: `content` and `scripts`; title is the `title` context var (not a block). Child templates `{% extends "base.html" %}`.
- Form scaffold: `<form method="POST" novalidate>` with **no `action`** (posts to the rendering URL, since routes are `methods=['GET','POST']`); hidden `csrf_token()` input first; `.card`>`.card-header`/`.card-body`; fields as `.row`>`.col-md-* mb-3`>`<label class="form-label">`+`<input class="form-control">`; `<textarea class="form-control">` for notes.
- Server-side validation display (copy `inventory/edit.html:113-121`): add `{% if validation_errors and validation_errors.description %} is-invalid{% endif %}` to the input class and a sibling `<div class="invalid-feedback{% if ... %} d-block{% endif %}">{{ validation_errors.description }}</div>`. Preserve typed values on re-render (`value="{{ form_data.get('manufacturer', '') }}"` for add; `value="{{ product.manufacturer or '' }}"` for edit).
- Flash messages render globally in `base.html:92-103` (category `error`→`alert-danger`); you don't need to re-render them in the product templates.
- Detail page is a **new pattern** — the existing app shows item details in a JS modal, but FR6 requires a direct-URL page, so build a proper read-only `detail.html`. The closest reference for read-only field display is the details-modal HTML table built in `static/js/inventory-list.js` (~lines 970-1000); render it server-side in Jinja instead.

### Data / field notes
- Product columns (from Story 1.1, `app/database.py`): `manufacturer`, `mpn`, `description` (Label Description), `notes`, `category_path`, `attributes` (JSON), `created_at`, `updated_at`, all nullable except PK/timestamps. `internal_id` does **not** exist yet — do not reference it (Epic 2). Detail URL keys on `id`.
- Required field: only **`description`** (Label Description) — the one field always available even for backfill (FR61). Everything else optional (FR3/FR4). Coerce blank optional fields to `None`.
- `category_path`: plain free-text in 1.3 (trim only). Epic 3 adds canonicalization + inline autocomplete-create; do not anticipate it.
- `attributes`: not editable in 1.3; the create/edit form omits it (stays `NULL`). Detail displays it read-only if some later path set it.

### What this story must NOT break (NFR9)
- Additive only: a NEW service file, NEW routes/functions in `routes.py`, NEW `product/` templates, and ONE nav edit in `base.html`. Do not modify `InventoryService`, inventory routes, inventory templates, or `app/database.py`/`app/models.py`.
- No dependency changes (`requirements.txt` untouched).

### Testing standards (project-context.md + spine)
- `venv/bin/nox -s tests` — never bare `pytest`; env needs Python 3.13 (`PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`). Unit tests use SQLite through `MariaDBStorage`, network blocked; the `client` fixture builds the app via `create_app(TestConfig, storage_backend=test_storage)` (`tests/conftest.py:67-79`).
- Route tests use `client` (see `tests/unit/test_routes.py` `TestAPIConsistency` for the pattern); service tests construct `CatalogService(test_storage)` directly.
- `nox -s e2e` requires a **20-minute** tool timeout if used.

### Project Structure Notes
- New: `app/mariadb_catalog_service.py`, `app/templates/product/add.html`, `app/templates/product/edit.html`, `app/templates/product/detail.html`, `tests/unit/test_catalog_service.py`, `tests/unit/test_product_routes.py`. Modified: `app/main/routes.py` (routes + `_get_catalog_service` + imports), `app/templates/base.html` (nav). Matches the spine Structural Seed (`mariadb_catalog_service.py` NEW; `main/routes.py` + catalog endpoints; `templates/`).

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.3: Product create/edit/detail] (AC, FR3/FR4/FR6/FR61)
- [Source: …/ARCHITECTURE-SPINE.md#AD-2] (business logic in `mariadb_catalog_service.py`; routes build response, no ORM/SQL in routes; per-method session lifecycle; `log_audit_operation` on mutations)
- [Source: …/ARCHITECTURE-SPINE.md#AD-1] (enhanced-ORM `Product` already exists) · [#AD-3] (`internal_id` is the future URL key — Epic 2/8; 1.3 uses the surrogate id)
- [Source: …/ARCHITECTURE-SPINE.md#Consistency Conventions] (JSON envelope + `@csrf.exempt` apply to JSON APIs — Epic 7, not 1.3; service `mariadb_catalog_service.py`; sessions `try/except-log/finally-close`)
- [Source: _bmad-output/implementation-artifacts/1-1-product-entity-and-migration.md, 1-2-purchase-entity-and-migration.md] (timestamp convention, DetachedInstance lesson, 367-test baseline)
- [Existing code: app/mariadb_inventory_service.py:130-187 (service ctor + read), :930-1056 (update), :1058-1167 (create); app/mariadb_materials_admin_service.py:40-197 (single-file service template + ValidationError use)]
- [Existing code: app/main/routes.py:20-28 (`_get_storage_backend`), :73-78 (`_get_inventory_service`), :546-625 (`inventory_add`), :627-733 (`inventory_edit`), :460 (`@csrf.exempt` — JSON only)]
- [Existing code: app/templates/base.html:26-103 (nav + flash blocks), app/templates/inventory/add.html:30-31 (form+CSRF), edit.html:113-121 (server-side validation display)]
- [Existing code: app/storage.py:5-11 (`StorageResult` — the storage contract, NOT a service return), app/exceptions.py (ValidationError et al.), app/logging_config.py:250 (`log_audit_operation`)]
- [Existing code: tests/conftest.py:35-79 (`test_storage`/`app`/`client` fixtures), tests/unit/test_routes.py (client-based route tests), tests/e2e/test_add_item.py (e2e add pattern)]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Opus 4.8, 1M context) — bmad-dev-story workflow.

### Debug Log References

- No migration/schema change in this story — pure app-layer (service + routes + templates). No MariaDB container run.
- Route/integration tests drive the create→detail→edit flow end-to-end through the real Jinja templates via the Flask `client` fixture (SQLite backend), which also exercises the new `base.html` "Products" nav on every rendered page — a broken `url_for('main.product_add')` would 500 those renders; all pass.

### Completion Notes List

- Delivered browser create/edit/detail for Products backed by a new `CatalogService`. No schema change (the `products` table already exists from Story 1.1).
- `CatalogService` mirrors `MariaDBMaterialsAdminService`/`InventoryService` exactly (ctor, session lifecycle, `log_audit_operation(..., logger_name='mariadb_catalog_service')`, returns id/object/bool — not `StorageResult`).
- Detail page is keyed on the **integer PK** (`/products/<int:id>`); `internal_id`-keyed URLs are Epic 2/8. Create/edit redirect to the detail page (demonstrates FR6 direct-URL reachability).
- Only **Label Description** (`description`) is required; all other fields optional, blanks coerced to `NULL` (AC #1, FR3/FR4/FR61). Category is plain free-text (Epic 3 adds normalization/autocomplete-create). Specifications (`attributes`) editing deferred; the detail page displays them read-only if present.
- Browser forms are CSRF-protected with `{{ csrf_token() }}` (not `@csrf.exempt`); the JSON/REST create path is Epic 7.
- Scope deferred by design: product list/browse/search (Epic 8), enrichment hook on create (Story 7.5), purchase history/attachments (Stories 1.4/1.5), tags (Epic 3).
- Screenshots: the new `product/*` pages are **not** in `tests/e2e/screenshot_config.yaml`, so no screenshot regeneration was required.
- All 6 ACs satisfied; full unit suite green (**383 passed**); metal-stock/inventory UI, routes, and templates unchanged (NFR9).

### File List

- `app/mariadb_catalog_service.py` (new) — `CatalogService` (create/get/update Products).
- `app/main/routes.py` (modified) — `_get_catalog_service()` helper; `product_add`/`product_detail`/`product_edit` routes; `CatalogService`/`Product` imports.
- `app/templates/product/add.html` (new), `app/templates/product/edit.html` (new), `app/templates/product/detail.html` (new).
- `app/templates/base.html` (modified) — "Products" navbar dropdown with "Add Product".
- `tests/unit/test_catalog_service.py` (new) — 7 service tests.
- `tests/unit/test_product_routes.py` (new) — 9 route/integration tests.
- `_bmad-output/implementation-artifacts/1-3-product-create-edit-detail.md` (modified) — story tracking.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — status transitions.

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-23 | Story 1.3 implemented: `CatalogService` (create/get/update) + product create/edit/detail routes + 3 templates + "Products" nav + 16 tests (7 service, 9 route). No schema change. Full suite green (383 passed). Status → review. |
