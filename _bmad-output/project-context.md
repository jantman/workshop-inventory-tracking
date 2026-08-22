---
project_name: 'workshop-inventory-tracking'
user_name: 'Jason'
date: '2026-07-18'
sections_completed: ['technology_stack', 'language_specific', 'framework_specific', 'testing', 'code_quality', 'workflow', 'critical_rules']
existing_patterns_found: 5
status: 'complete'
rule_count: 31
optimized_for_llm: true
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- **Language:** Python 3.13 (`nox` sessions pin `3.13`)
- **Web framework:** Flask 3.1.3 + Werkzeug 3.1.8; app-factory pattern (`create_app()` in `app/__init__.py`)
- **ORM:** SQLAlchemy **2.0.51** (migrated from 1.4 in July 2026). The codebase uses the **legacy `Query` API** (`session.query(...)`), which remains fully supported in 2.0 — match the surrounding file's style. Writing 2.0-style `select()` / `session.execute()` is allowed for new code but prefer consistency with the existing service. Raw SQL strings passed to `.execute()` **must** be wrapped in `sqlalchemy.text(...)`.
- **Migrations:** Alembic 1.18.5, driven through `manage.py db ...` (NOT Flask-Migrate)
- **Database:** MariaDB/MySQL via PyMySQL 1.2.0 (primary). Google Sheets API (google-api-python-client 2.198.0) is **export-only / legacy**, not primary storage.
- **Forms/CSRF:** Flask-WTF 1.3.0 (CSRF enabled in prod, disabled in tests)
- **Frontend:** Server-rendered Jinja2 + Bootstrap 5.3.2 (`app/templates`, `app/static`)
- **Testing:** nox + pytest 9.1.1, pytest-flask, pytest-playwright 0.8.0 + Playwright 1.61.0 (e2e), testcontainers[mysql] 4.14.2 (integration)
- **Other:** PyMuPDF 1.28.0 (PDF), Pillow 12.3.0 (images), pt-p710bt-label-maker (Brother label printing via git dependency)
- **Config:** python-dotenv 1.2.2 — settings loaded from `.env`; `SQLALCHEMY_DATABASE_URI` read directly
- **DigiKey API** (feature 024): `app/services/digikey.py`, `requests` + stdlib only. 2-legged OAuth (`client_credentials`) plus an `X-DIGIKEY-Account-ID` header — without that header every order endpoint answers `400 Account ID must not be 0`, which is *configuration*, not authorization. Settings: `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`, `DIGIKEY_ACCOUNT_ID`, `DIGIKEY_API_BASE`. Unset client id = not configured, which is an ordinary state.
- **Serving/packaging:** gunicorn 26.0.0 behind the `Dockerfile` (python:3.13-slim, `linux/amd64`, non-root, migrations NOT auto-run). Images publish to `ghcr.io/jantman/workshop-inventory-tracking`.
- **Versioning:** SemVer. `version` in `pyproject.toml` is the single source of truth; `app/version.py` reads it at runtime. `pyproject.toml` is metadata only — the app is never pip-installed as a package.

## Critical Implementation Rules

### Language-Specific (Python) Rules

- **Decimals, never floats, for measurements.** All dimensions/lengths use `decimal.Decimal` with `ROUND_HALF_UP` (see `app/models.py`). Never introduce `float` math for quantities or dimensions.
- **Domain models are `@dataclass`, not ORM rows.** `app/models.py` holds dataclass domain models + `Enum` types (`ItemType`, `ItemShape`, `Thread`, `ThreadSeries`, etc.). Keep validation logic there.
- **SQLAlchemy ORM lives separately** in `app/database.py` (`Base`, `InventoryItem`). Do not merge the dataclass layer and the ORM layer — conversions happen explicitly at the storage boundary.
- **Type hints expected** — code uses `typing` (`Optional`, `List`, `Dict`, `Union`) throughout; match it.
- **Defensive parsing** — helpers like `parse_date_value` / `safe_str` tolerate mixed input (strings, Excel serials, None) because data originated from Google Sheets. Preserve this tolerance when touching import/parse paths.

### Framework-Specific (Flask) Rules

- **App factory + storage injection.** Always build the app via `create_app(config_class, storage_backend=None)`. The storage backend is stashed in `app.config['STORAGE_BACKEND']` and read by routes — get storage from there, don't instantiate it inline.
- **Storage goes through the `Storage` ABC.** `app/storage.py` defines the `Storage` interface returning a `StorageResult(success, data, error, affected_rows)`. New persistence code implements/uses that contract; check `result.success` — do not raise across the boundary.
- **`MariaDBStorage` is the concrete backend** (`app/mariadb_storage.py`); the heavy business logic lives in the service layer (`mariadb_inventory_service.py`, `mariadb_materials_admin_service.py`). Put new domain logic in a service, not in routes.
- **Blueprints:** `main` (`app/main/`) and `admin` (`app/admin/`), registered in the factory. Add routes to the appropriate blueprint, not to a bare app.
- **CSRF is on** via Flask-WTF globally (`csrf.init_app(app)`). Non-GET endpoints need CSRF tokens; tests disable it via `WTF_CSRF_ENABLED = False`.
- **Centralized error handling & logging** — `create_error_handlers(app)` and `setup_logging(app)` run in the factory; use the project's custom exceptions (`app/exceptions.py`) rather than ad-hoc error responses.

### Testing Rules

- **Run tests via `nox`, never bare `pytest`.** Sessions: `nox -s tests` (unit), `nox -s e2e`, `nox -s coverage`, `nox -s lint`.
- **The `e2e` session needs a 15-minute timeout** on the tool/agent running it (it installs Playwright browsers and uses `--reruns=3`). This is a harness-level timeout, not a CLI flag. The suite itself runs in well under 10 minutes warm; the margin covers a cold start.
- **The `e2e` session excludes screenshot tests** (`-m "e2e and not screenshot"`). Screenshot generation belongs to `nox -s screenshots`/`screenshots_headless`; those tests write into `docs/images/screenshots/`, so running them in the e2e gate made the test suite dirty the working tree. An e2e run must leave the tree clean.
- **Markers gate scope** (`pytest.ini`): `unit`, `integration`, `e2e`, `slow`, `database`, `screenshot`. `--strict-markers` is on — register any new marker before using it. The `tests` session runs `-m "not e2e and not integration"`.
- **Unit tests block the network** via `--blockage` (pytest-blockage). Don't write unit tests that make real HTTP/API calls — mock them.
- **Unit tests use SQLite through `MariaDBStorage`.** The `test_storage` fixture points `MariaDBStorage(database_url=sqlite:///...)` at a temp SQLite file and creates schema via `Base.metadata.create_all`. Integration tests use a real MariaDB testcontainer (`mariadb_testcontainer`).
- **Shared fixtures live in `tests/conftest.py`:** `test_storage` → `app` (built with `TestConfig` + injected storage) → `client`. Reuse them; build the app through them, not manually.
- **Layout:** `tests/unit/` and `tests/e2e/`; files `test_*.py`, classes `Test*`, functions `test_*`. `migrations/` is excluded from collection.

#### E2E waiting rules (non-negotiable)

The e2e suite took 22m 27s until `specs/002-e2e-test-performance/`, over half of it spent blocking on a clock instead of on the application. These rules keep it fast; the full version with examples is the "Writing e2e tests" section of `CLAUDE.md`.

- **No `page.wait_for_timeout(...)` and no `time.sleep(...)`.** Use `expect(locator)`, which polls until the condition holds. Where nothing observable exists, the wait may stay only with a comment at the call site explaining why.
- **No `wait_for_load_state("networkidle")`.** It costs >=0.5s per call and says nothing about your content. `goto()` already waits for `load`.
- **Never read a JS-rendered region without waiting first.** `count()`, `text_content()` and `is_visible()` do not wait and return "empty" against a table that is still loading. This is worst for negative assertions, which then pass for the wrong reason.
- **A click that fires a `fetch` is not done when `click()` returns.** Wait for what the response changes; navigating away first aborts the request.
- **Seed via `live_server.add_test_data([...])`** (milliseconds), not by driving the Add Item form (~3s per item). Use the form only when the form is under test.
- **Waits live in page objects**; shared helpers are in `tests/e2e/waits.py`.
- **Every test must pass in isolation.** It may assume an empty inventory and the standard 21-row taxonomy, nothing more.

### Code Quality & Style Rules

- **Formatters/linters exist but are NOT enforced in default CI.** `nox -s lint` runs flake8 + `black --check` + `isort --check`, but it's not in `nox.options.sessions` (default = `tests`, `coverage`) and `lint` is labeled a future enhancement. Match surrounding style; don't mass-reformat existing files.
- **Screenshots track the UI.** When you change `app/templates/**`, `app/static/css/**`, or `app/static/js/**`, docs screenshots may be stale. Regenerate with `nox -s screenshots` (or `screenshots_headless`); a repo `pre-commit` hook (`hooks/`) reminds about this.
- **Screenshot quality gate:** PNGs must be < 500KB and RGB/RGBA — `nox -s screenshots_verify` enforces it.
- **Module organization:** routes in blueprint packages (`app/main`, `app/admin`); services as `*_service.py`; utilities in `app/utils/`; reusable services in `app/services/`. Keep this separation.
- **Naming:** modules/functions `snake_case`; classes `PascalCase`; test files `test_*.py`.

### Development Workflow Rules

- **Always source the venv** (`source venv/bin/activate`) before running any project command.
- **Database schema changes go through Alembic** via `python manage.py db ...` (revision/upgrade). Never hand-edit the DB or use `create_all` outside tests. `manage.py` is a click CLI with additional admin/audit commands.
- **Secrets stay in `.env`** (gitignored): `SECRET_KEY`, `SQLALCHEMY_DATABASE_URI`, `GOOGLE_*`. `.flaskenv` holds non-secret Flask run settings. Never hardcode credentials or commit `.env`, `credentials.json`, or `token.json`.
- **CI (GitHub Actions):** `test.yml` (nox tests + Docker build/push of `ci-<sha>`) and `security.yml` gate the repo; Claude Code review workflows also run. Keep `nox -s tests` green.
- **Releasing:** bump `version` in `pyproject.toml` and merge to `main`; `release.yml` then pushes the versioned + `latest` images and creates the `v<version>` GitHub release. Merges without a version bump are a no-op. The Docker build config is duplicated in `test.yml` and `release.yml` — change both together.

### Critical Don't-Miss Rules

- **Prefer the legacy `Query` API for consistency** — the codebase runs on SQLAlchemy 2.0.51 but overwhelmingly uses `session.query(...)`. Match the surrounding file; don't refactor working `query()` code to `select()` gratuitously. Always wrap raw SQL strings in `sqlalchemy.text(...)`.
- **Don't bypass the `Storage`/service layers** by putting raw SQL or ORM queries in routes — go through `MariaDBStorage` + the `*_service.py` layer.
- **Don't use `float` for measurements** — `Decimal` only (see item dimensions / `ROUND_HALF_UP`).
- **Never call `response.json()` in `app/services/digikey.py`** — it returns `float` prices. Parse with `json.loads(body, parse_float=Decimal)`. `tests/unit/test_digikey_client.py::TestNoResponseJson` walks the module's AST to enforce this; a text search would fire on the docstring explaining the ban.
- **`app/services/digikey.py` imports nothing from the app but `models` and `exceptions`** — no Flask, no ORM, no config. The client is built in `create_app()` and stashed as `app.config['DIGIKEY_CLIENT']`, mirroring `STORAGE_BACKEND`; tests inject a fake there.
- **A captured DigiKey order is derived, not stored.** It *is* the purchases carrying its `supplier_order_reference` (ECIA `1K`), the way the reorder list is derived. Do not add a `digikey_orders` table.
- **`ScanResolution.outcome` has four members**, not three: `product`, `receive`, `create`, `search`. In the ECIA branch of `resolve_scan`, the order-line lookup **must run before** the `1P` → MPN lookup, or a bag for a part you already own opens the product page instead of its receipt.
- **Don't treat Google Sheets as live storage** — it's export/legacy only; MariaDB is the source of truth.
- **Items have history/lifecycle semantics** — JA-ID identifiers, parent-child relationships, and active/inactive shortening history (multi-row). Preserve active-status and history invariants when editing/moving/shortening items; there are dedicated e2e tests for these.
- **Don't run `pytest` directly or skip the 20-min e2e timeout** — both break the intended test flow.

---

## Usage Guidelines

**For AI Agents:**

- Read this file before implementing any code in this project.
- Follow ALL rules exactly as documented; when in doubt, prefer the more restrictive option.
- Update this file if new patterns emerge.

**For Humans:**

- Keep this file lean and focused on agent needs.
- Update when the technology stack or storage/service patterns change.
- Review periodically and remove rules that become obvious over time.

Last Updated: 2026-07-19
