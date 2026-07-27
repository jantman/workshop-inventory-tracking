---
title: 'App-scoped shared SQLAlchemy engine (DW-32)'
type: 'refactor'
created: '2026-07-27'
status: 'done'
baseline_revision: 'cfc7102'
final_revision: 'd376757'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** In production `_get_storage_backend()` returns a fresh *unconnected* `MariaDBStorage` (`engine is None`, `connect()` never called), so `InventoryService`, `CatalogService`, `MariaDBMaterialsAdminService`, `PhotoService` and the export services each fall through to building their own engine from the class-level `Config.SQLALCHEMY_DATABASE_URI` on **every request**. Those engines are never disposed, `storage.database_url` is ignored, and `SQLALCHEMY_ENGINE_OPTIONS` pool tuning is effectively inert.

**Approach:** Own one connected `MariaDBStorage` — and therefore one engine and one pool — per Flask app, memoized on `app.extensions`, built from `app.config` rather than the `Config` class. Every service resolves its engine from the storage it was handed instead of constructing its own, and services that borrow an engine must not dispose it.

## Boundaries & Constraints

**Always:**
- An injected `STORAGE_BACKEND` (tests, e2e) keeps priority; the app-scoped singleton is only the production fallback.
- The singleton is created lazily on first use, never during `create_app()` — `wsgi.py`/`app.py` import the factory and must not require a reachable database.
- `storage.database_url` is the source of truth for the engine's URL; `storage`-derived engine options come from `app.config`, falling back to `config.Config` when absent.
- Failure to connect raises `ConnectionError` and does **not** cache a connected-looking storage; the next call retries.
- A service may only `dispose()` an engine it created itself.
- Preserve the public attribute surface tests read: `storage.database_url`, `storage.engine`, `storage.Session`, `storage._connected`, `service.engine`, `service.Session`, `service.storage`.
- Match surrounding style: legacy `session.query(...)`, `sqlalchemy.text(...)` for raw SQL, type hints.

**Block If:**
- A change would require altering the `Storage` ABC contract in `app/storage.py`.
- Removing the per-request `sessionmaker` (out of scope — sessions stay per-service-instance).

**Never:**
- Do not introduce Flask-SQLAlchemy or any new dependency.
- Do not register a SQLite collation here — DW-72 is a separate item; this work only creates the seam.
- Do not change `manage.py`, `migrations/env.py`, or test fixtures' own engines.
- Do not mass-reformat touched files.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Production, repeated requests | No `STORAGE_BACKEND` in `app.config` | Every `_get_storage_backend()` call returns the *same* connected storage object; `storage.engine` is one identical `Engine` across calls | No error expected |
| Test injection | `STORAGE_BACKEND` present | That exact object is returned; singleton never built | No error expected |
| Two distinct apps | Two `create_app()` results | Each has its own storage/engine; no cross-app sharing | No error expected |
| URL source of truth | `app.config['SQLALCHEMY_DATABASE_URI']` set to a sqlite temp file | Engine URL matches `storage.database_url`, not `Config.SQLALCHEMY_DATABASE_URI` | No error expected |
| DB unreachable | `connect()` returns `success=False` | `ConnectionError` raised; nothing cached as connected; retry on next call | `ConnectionError` with the storage's error text |
| Borrowed engine closed | `PhotoService(shared_storage)` used as a context manager | On `__exit__` the session closes, the **shared engine is not disposed**, and the storage stays usable | No error expected |
| Owned engine closed | `PhotoService()` with no storage | On `close()` its own engine *is* disposed | No error expected |
| Duck-typed/mock storage | Object exposing a truthy `.engine` | That engine is adopted unchanged (existing mock-based tests keep passing) | No error expected |

</intent-contract>

## Code Map

- `app/db.py` -- **new**: `get_app_storage(app)` (lazy, thread-safe, `app.extensions`-memoized singleton), `get_storage_backend()` (config-injection-aware helper used by both blueprints), `resolve_engine(storage)` (connect-if-needed engine accessor). The DW-72 collation seam.
- `app/mariadb_storage.py:27-73` -- `__init__`/`connect()`/`close()`: accept optional `engine_options`, dispose a prior/failed engine instead of orphaning it, reset `engine`/`Session` on close.
- `app/main/routes.py:48-56, 101-116, 3255-3270` -- `_get_storage_backend()` delegates to `app/db.py`; the `/api/materials/hierarchy` inline engine/session block uses the shared storage and closes its session.
- `app/admin/routes.py:13-21` -- same delegation (duplicate helper).
- `app/mariadb_inventory_service.py:139-156`, `app/mariadb_catalog_service.py:143-160`, `app/mariadb_materials_admin_service.py:34-50` -- replace `storage.engine or self._create_engine()` + `_create_engine()` with `resolve_engine(storage)`.
- `app/photo_service.py:54-66, 546-553` -- track engine ownership; `close()` only disposes an owned engine.
- `app/export_service.py:31-46` -- accept an optional `storage`, adopt its engine when given.
- `app/main/routes.py:4371, 4388, 4405, 4521` -- pass the shared storage to export services. (`:4545` `GoogleSheetsExportService` is *not* a `BaseExportService`, owns no engine, and is correctly left alone.)
- `config.py:84-95, 173-195` -- `SQLALCHEMY_DATABASE_URI` / `SQLALCHEMY_ENGINE_OPTIONS` definitions (read-only reference).
- `tests/conftest.py:35-73` -- `test_storage` (connected SQLite) + `app` fixtures; the injection path that must keep working.
- `tests/unit/test_photo_service.py:35-135, 545-560` -- mock-storage and no-storage constructor expectations that must not regress.

## Tasks & Acceptance

**Execution:**
- [x] `app/db.py` -- create the module with `get_app_storage`, `get_storage_backend`, `resolve_engine`; document why the engine is app-scoped and that this is where a SQLite collation would be registered (DW-72) -- single owner for engine lifetime.
- [x] `app/mariadb_storage.py` -- add optional `engine_options` to `__init__`; in `connect()` dispose any pre-existing engine and dispose+null the partially built engine on failure; in `close()` null `engine`/`Session` -- so repeated connect/close cannot orphan pools.
- [x] `app/main/routes.py` + `app/admin/routes.py` -- `_get_storage_backend()` delegates to `app.db.get_storage_backend()` -- one implementation, production path now returns a connected shared storage.
- [x] `app/main/routes.py` -- rewrite the `/api/materials/hierarchy` inline storage/engine block to use `_get_storage_backend()` + `resolve_engine`, closing the session in a `finally` -- removes the last per-request engine construction in routes.
- [x] `app/mariadb_inventory_service.py`, `app/mariadb_catalog_service.py`, `app/mariadb_materials_admin_service.py` -- use `resolve_engine(storage)`; delete `_create_engine` and now-unused `create_engine`/`Config` imports -- services can no longer silently point at a different database than their storage.
- [x] `app/photo_service.py` -- resolve the borrowed engine via `resolve_engine`, record ownership, and dispose in `close()` only when owned -- a shared engine must survive a `with PhotoService(...)` block.
- [x] `app/export_service.py` + export construction sites in `app/main/routes.py` -- accept and use an optional `storage` -- exports stop building a fresh pool per download.
- [x] `tests/unit/test_app_scoped_engine.py` -- **new**: cover every row of the I/O & Edge-Case Matrix -- proves singleton identity, config-driven URL, connect-failure behavior, and borrowed-vs-owned disposal.

**Acceptance Criteria:**
- Given a production-shaped app (no injected `STORAGE_BACKEND`), when N requests hit routes that build `InventoryService` and `CatalogService`, then all resolved engines are the same object and no engine is created after the first.
- Given the existing unit suite, when `nox -s tests` runs, then it passes with no changes to `tests/conftest.py` fixtures.
- Given `grep -n "create_engine" app/mariadb_inventory_service.py app/mariadb_catalog_service.py app/mariadb_materials_admin_service.py`, when run after the change, then it returns no matches.
- Given a route that borrows the shared engine through `PhotoService`, when the context manager exits, then a subsequent query through the shared storage still succeeds.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 11: (high 0, medium 4, low 7)
- defer: 4: (high 0, medium 3, low 1)
- reject: 11
- addressed_findings:
  - `[medium]` `[patch]` `MariaDBStorage.connect()` disposed a live engine with no serialization, so a second thread could tear down an engine the first had just bound a `sessionmaker` to — added a per-storage `_connect_lock` and made `connect()` idempotent (returns the existing connection instead of rebuilding).
  - `[medium]` `[patch]` A `None`/empty `database_url` surfaced as `AttributeError: 'NoneType' object has no attribute 'startswith'` wrapped in a `ConnectionError` — now returns a `StorageResult` naming `SQLALCHEMY_DATABASE_URI`.
  - `[medium]` `[patch]` `get_app_storage` returned a cached-but-closed storage with `engine=None`, violating its documented "connected" contract — it now reconnects the cached object.
  - `[medium]` `[patch]` The app-scoped `scoped_session` now lives for the process, retaining a session per worker thread where the old per-request storage was discarded — added a `teardown_appcontext` hook in `app/__init__.py` that removes it (injected test backends untouched).
  - `[low]` `[patch]` `BaseExportService.database_uri` was set to `str(engine.url)`, which SQLAlchemy renders with the password masked as `***` — now takes the storage's own `database_url`.
  - `[low]` `[patch]` `_dispose_engine()` ran outside `connect()`'s `try`, so a teardown error made `connect()` raise instead of returning a `StorageResult` — teardown failures are now logged and the attributes cleared regardless.
  - `[low]` `[patch]` `PhotoService.close()` used `getattr(self, '_owns_engine', True)`, defaulting to *disposing* a possibly-borrowed engine — added a class-level `_owns_engine = False`.
  - `[low]` `[patch]` `app/db.py`'s docstring justified its lock with an e2e-server race that cannot happen (e2e injects `STORAGE_BACKEND`) and claimed to be the DW-72 collation seam, which it is not — the seam is `MariaDBStorage.connect()`, the only place any storage builds an engine. Both corrected.
  - `[low]` `[patch]` `resolve_engine`'s docstring said "truthy" where the code tests `is not None`.
  - `[low]` `[patch]` Dead `from config import Config` left in `app/admin/routes.py` while the same commit removed the equivalent dead imports from four sibling files.
  - `[low]` `[patch]` Test gaps and hygiene: nothing exercised the double-checked lock (added a `threading.Barrier` concurrency test), `_FailingStorage` had no `fail_times` default, and `test_engine_url_comes_from_app_config_not_the_config_class` passed vacuously when `Config.SQLALCHEMY_DATABASE_URI` was `None`. Stale `_create_engine` rationale in `tests/unit/conftest.py` refreshed.

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 7: (high 0, medium 4, low 3)
- defer: 3: (high 0, medium 2, low 1)
- reject: 10
- addressed_findings:
  - `[medium]` `[patch]` `_dispose_engine()` cleared `_connected` *last*, so a thread in `_get_session()` could pass the `if not self._connected` check and then call `self.Session()` after another thread had already nulled it — `TypeError: 'NoneType' object is not callable` on an ordinary read path. `_connected` is now cleared first (so the racing thread takes the locked `connect()` path instead), and `close()` takes `_connect_lock` so it cannot interleave with a concurrent connect.
  - `[medium]` `[patch]` `_connect_locked()` assigned `self.engine = create_engine(...)` *before* the `SELECT 1` validation, and `self.engine` is read without the lock (`app.db`'s memoization fast path, `resolve_engine`). A reader could therefore adopt an unvalidated engine that the `except` branch was about to dispose. The engine is now built into a local and published onto `self` only after it connects.
  - `[medium]` `[patch]` The new `teardown_appcontext` hook called `storage.Session.remove()` unguarded. It runs from `AppContext.pop()` inside Flask's `finally`, *after* the response has been sent, so a failing `remove()` (a dropped pooled connection resurfaces as `OperationalError`) escapes past the error handlers as an unhandled traceback on a successful request — while the identical call in `_dispose_engine` was already wrapped for exactly that reason. Now reads the registry once (a concurrent `close()` nulls it) and logs failures.
  - `[medium]` `[patch]` Nothing exercised the production wiring: every route test injects `STORAGE_BACKEND`, which short-circuits before `get_app_storage`, so reverting either blueprint's `_get_storage_backend()` to `MariaDBStorage()` left the whole 571-line suite green — the acceptance criterion says "N *requests* hit routes" and no test issued one. Added `TestRoutesUseTheAppScopedStorage`: real requests against a production-shaped app through both blueprints, asserting they resolve the singleton's engine and construct no second storage.
  - `[low]` `[patch]` `get_app_storage` passed `app.config.get('SQLALCHEMY_DATABASE_URI')` straight into `MariaDBStorage`, whose own `database_url or Config.SQLALCHEMY_DATABASE_URI` fallback then silently fired for an app that deliberately configured none — pointing it at whatever `.env` holds, and defeating the module's stated "built from `app.config`, not the `Config` class" invariant. Now raises `ConnectionError` naming the key.
  - `[low]` `[patch]` The `app.extensions` memoization tested `engine is not None` while the docstring promised a *connected* storage; during a reconnect those differ. Both the fast path and the under-lock re-check now go through `_is_usable()`, which requires `_connected`.
  - `[low]` `[patch]` `app/db.py`'s DW-72 paragraph claimed `MariaDBStorage.connect()` is "the seam that covers both those engines and this one" — false for the two files it names: `tests/conftest.py` and `tests/e2e/test_server.py` build engines with a bare `create_engine`, and the latter runs queries through its own. Corrected, and it now names the other uncovered sites (`PhotoService`, `BaseExportService`).
  - Three further findings were confirmed but are already on the ledger from the previous pass — `BaseExportService` having no way to dispose an owned engine (DW-147), builtin `ConnectionError` sitting outside the project's exception hierarchy (DW-148), and the now load-bearing `pool_size` never being sized (DW-149) — so they were dropped here rather than re-recorded.

### 2026-07-27 — Review pass (follow-up 2)
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 1, low 2)
- defer: 3: (high 0, medium 1, low 2)
- reject: 21
- addressed_findings:
  - `[medium]` `[patch]` The `_get_session()` race the previous pass claimed to close is still open. Clearing `_connected` before teardown only redirects a thread that has *not yet* made the check; one already past it still evaluates `self.Session()` after a concurrent `close()` nulled it and dies on `TypeError: 'NoneType' object is not callable`. `_get_session()` now snapshots the factory into a local and treats a `None` snapshot exactly like "not connected", and `connect()`'s idempotent fast path now also requires `Session is not None` so that recovery actually rebuilds instead of short-circuiting. The overstated `_dispose_engine` comment was corrected, and `test_get_session_survives_a_torn_down_session_factory` pins the behavior.
  - `[low]` `[patch]` `get_app_storage`'s docstring promised "nothing is cached" on failure, which is true only on first touch — a *cached* storage whose reconnect fails stays in `app.extensions`. Rewritten to state the real invariant: nothing that looks connected is ever handed out, and the failed-reconnect object fails `_is_usable()` so the next call reconnects it.
  - `[low]` `[patch]` The concurrency test could pass while the bug it hunts was live: `_CountingStorage.instances += 1` is a non-atomic read-modify-write driven by eight racing threads, so a double construction could lose an increment and report `1`. The counter is now lock-guarded. The same test's `threading.Barrier` had no timeout (a worker dying before `wait()` hangs the suite) and its `finally` indexed `results[0]`, turning an all-workers-failed run into an `IndexError` that masked the real failure — both fixed.
  - Confirmed but not re-recorded, already on the ledger: `_get_storage_backend()` now raising where it only constructed an object before, and the builtin `ConnectionError` used for a pure configuration error (both DW-148); the e2e server's injected storage retaining per-thread sessions (DW-151); `PhotoService()`'s no-storage branch (DW-153); pool sizing (DW-149).

## Design Notes

`app.extensions` (not `app.config`) holds the singleton so it is not serialized into config dumps and cannot collide with `STORAGE_BACKEND`. A module-level `threading.Lock` guards creation against a threaded WSGI runner; a second, per-storage lock inside `MariaDBStorage.connect()` makes connection itself idempotent, since `resolve_engine`/`_get_session` can also reach `connect()` concurrently.

```python
def get_storage_backend(app=None):
    app = app or current_app
    injected = app.config.get('STORAGE_BACKEND')
    if injected is not None:
        return injected
    return get_app_storage(app)
```

`resolve_engine` keeps `getattr(storage, 'engine', None)` semantics first so `Mock()` storages in existing tests are adopted unchanged; only a `None` engine triggers `connect()`. Flask offers no app-shutdown hook, so the app-scoped engine is disposed only via `MariaDBStorage.close()` (e2e teardown) — acceptable, since the whole point is that it lives as long as the process. The per-request half of that lifetime is a `teardown_appcontext` hook that drops the shared `scoped_session`.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all unit tests pass, including the new `tests/unit/test_app_scoped_engine.py`
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: pass (no `app/utils/` change intended)
- `grep -rn "create_engine" app/mariadb_inventory_service.py app/mariadb_catalog_service.py app/mariadb_materials_admin_service.py` -- expected: no output
- `venv/bin/python -c "import app, wsgi"` -- expected: imports cleanly with no database reachable

## Auto Run Result

Status: done (second follow-up review pass, no code re-derivation)

**Summary.** A third independent review of the DW-32 change. No intent gaps and no spec defects, so the implementation stands as specified. The pass closed the one real defect left in the concurrency work — the `_get_session()` race the previous pass believed it had fixed by reordering — and corrected a docstring and a test that could pass while the bug it hunts was live. Everything else the reviewers raised was either already on the ledger, spec-mandated behavior, or noise.

**Files changed in this pass:**
- `app/mariadb_storage.py` -- `_get_session()` snapshots the session factory instead of re-reading it, `connect()`'s idempotent fast path requires a live `Session`, and `_dispose_engine`'s comment no longer overstates what the `_connected`-first ordering buys.
- `app/db.py` -- `get_app_storage`'s `Raises:` docstring now describes the failed-*reconnect* branch truthfully.
- `tests/unit/test_app_scoped_engine.py` -- new `test_get_session_survives_a_torn_down_session_factory`; the concurrency test's construction counter is lock-guarded, its barrier has a timeout, and worker exceptions are collected instead of surfacing as an `IndexError`.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- DW-154, DW-155, DW-156 appended.

**Findings breakdown:** 3 patches applied (1 medium, 2 low), 3 deferred (DW-154, DW-155, DW-156), 21 rejected — of which 5 were confirmed but already on the ledger as DW-148/149/151/153 and so were not re-recorded.

**Verification:**
- `nox -s tests` -- 2722 passed, 427 deselected (2721 before this pass; +1 new test).
- `nox -s doctests` -- 21 passed.
- `grep -rn "create_engine" app/mariadb_inventory_service.py app/mariadb_catalog_service.py app/mariadb_materials_admin_service.py` -- no matches.
- `venv/bin/python -c "import app, wsgi"` -- clean, no database reachable.
- DW-155 confirmed by exhaustive grep, not inspection: no call site anywhere in the repository (`venv/` excluded) for any `Storage` data method outside `app/mariadb_storage.py` calling itself at `:236`.

**Residual risks:**
- The module-level `_storage_lock` held across a blocking `connect()` remains, now recorded as DW-154 rather than living only in this section.
- `MariaDBStorage.close()` is still not fully serialized against readers of `storage.engine` — `resolve_engine` can adopt an engine in the window between `_dispose_engine` clearing `_connected` and disposing the engine. No production path calls `close()` (only e2e teardown does), and the guard that would close it would have to reject the duck-typed/mock storages the spec's matrix requires, so it was left alone.
- Pool sizing (DW-149) and the absence of any MariaDB-tier test for the production storage path (DW-150) remain open from the first pass.

