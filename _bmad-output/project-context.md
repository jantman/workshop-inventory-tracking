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
- **Web framework:** Flask 3.0.0 + Werkzeug 3.0.1; app-factory pattern (`create_app()` in `app/__init__.py`)
- **ORM:** SQLAlchemy **1.4.53** — NOT 2.x. Use 1.4 idioms (legacy `Query` API, `db.session.query(...)`). Do not write 2.0-style `select()` / `session.execute()` unless matching existing code.
- **Migrations:** Alembic 1.13.1, driven through `manage.py db ...` (NOT Flask-Migrate)
- **Database:** MariaDB/MySQL via PyMySQL 1.1.0 (primary). Google Sheets API (google-api-python-client 2.110.0) is **export-only / legacy**, not primary storage.
- **Forms/CSRF:** Flask-WTF 1.2.1 (CSRF enabled in prod, disabled in tests)
- **Frontend:** Server-rendered Jinja2 + Bootstrap 5.3.2 (`app/templates`, `app/static`)
- **Testing:** nox + pytest 8.4.2, pytest-flask, Playwright 1.55.0 (e2e), testcontainers[mysql] 4.8.2 (integration), factory-boy/faker
- **Other:** PyMuPDF (PDF), Pillow (images), pt-p710bt-label-maker (Brother label printing via git dependency)
- **Config:** python-dotenv 1.0.0 — settings loaded from `.env`; `SQLALCHEMY_DATABASE_URI` read directly

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
- **The `e2e` session needs a 20-minute timeout** on the tool/agent running it (it installs Playwright browsers and uses `--reruns=3`). This is a harness-level timeout, not a CLI flag.
- **Markers gate scope** (`pytest.ini`): `unit`, `integration`, `e2e`, `slow`, `database`, `screenshot`. `--strict-markers` is on — register any new marker before using it. The `tests` session runs `-m "not e2e and not integration"`.
- **Unit tests block the network** via `--blockage` (pytest-blockage). Don't write unit tests that make real HTTP/API calls — mock them.
- **Unit tests use SQLite through `MariaDBStorage`.** The `test_storage` fixture points `MariaDBStorage(database_url=sqlite:///...)` at a temp SQLite file and creates schema via `Base.metadata.create_all`. Integration tests use a real MariaDB testcontainer (`mariadb_testcontainer`).
- **Shared fixtures live in `tests/conftest.py`:** `test_storage` → `app` (built with `TestConfig` + injected storage) → `client`. Reuse them; build the app through them, not manually.
- **Layout:** `tests/unit/` and `tests/e2e/`; files `test_*.py`, classes `Test*`, functions `test_*`. `migrations/` is excluded from collection.

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
- **CI (GitHub Actions):** `test.yml` (nox tests) and `security.yml` gate the repo; Claude Code review workflows also run. Keep `nox -s tests` green.

### Critical Don't-Miss Rules

- **Don't write SQLAlchemy 2.0 style** — this is 1.4.53. Use `session.query(...)`, not `session.execute(select(...))`, unless the file already does.
- **Don't bypass the `Storage`/service layers** by putting raw SQL or ORM queries in routes — go through `MariaDBStorage` + the `*_service.py` layer.
- **Don't use `float` for measurements** — `Decimal` only (see item dimensions / `ROUND_HALF_UP`).
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

Last Updated: 2026-07-18
