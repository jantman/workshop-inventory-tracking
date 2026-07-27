"""
Database engine ownership for the Flask application.

Historically every service (`InventoryService`, `CatalogService`,
`MariaDBMaterialsAdminService`, `PhotoService`, the export services) built its
own SQLAlchemy `Engine` from the class-level ``Config.SQLALCHEMY_DATABASE_URI``
whenever the storage it was handed had no engine of its own. In production
``_get_storage_backend()`` returned a *fresh, unconnected* ``MariaDBStorage`` on
every request, so that fallback was the normal path: each request created a new
engine and a new connection pool that nobody ever disposed, and
``SQLALCHEMY_ENGINE_OPTIONS`` pool tuning never applied to anything.

This module makes engine lifetime have exactly one owner: a single connected
``MariaDBStorage`` per Flask app, memoized on ``app.extensions``. Services no
longer construct engines -- they resolve one from the storage they were handed
via :func:`resolve_engine`.

Notes on the design:

* The singleton lives on ``app.extensions`` rather than ``app.config`` so it is
  never serialized into a config dump and cannot collide with the injected
  ``STORAGE_BACKEND`` key that tests and the e2e server use.
* It is app-scoped (not module-scoped) so two ``create_app()`` results never
  share a pool, and it is built from ``app.config`` rather than from the
  ``Config`` class so a test/e2e app really does talk to its own database.
* Creation is lazy -- never during ``create_app()`` -- because ``wsgi.py`` and
  ``app.py`` import the factory and must not require a reachable database.
* A module-level lock guards first touch, so a threaded WSGI runner cannot build
  two storages for one app. (The e2e server injects ``STORAGE_BACKEND`` and so
  never reaches this path; production is what races here.)
* Flask offers no app-shutdown hook, so this engine is disposed only through
  ``MariaDBStorage.close()``. That is intentional -- the whole point is that it
  lives as long as the process. The per-request half of the lifetime, removing
  the shared ``scoped_session``, is a ``teardown_appcontext`` hook registered in
  ``app/__init__.py``.

DW-72 (a custom SQLite collation, so SQLite and MariaDB agree about case
folding) would *not* be registered in this module: the SQLite engines that
divergence shows up on are the ones built with a bare ``create_engine`` outside
any storage -- ``tests/conftest.py`` (schema creation) and
``tests/e2e/test_server.py`` (which also *queries* through its own engine) --
and those never pass through here. ``MariaDBStorage.connect()`` is the one seam
that covers every engine a *storage* builds, this one included, but it does not
reach those bare fixture engines, nor the ones ``PhotoService`` and
``BaseExportService`` still build from ``Config``. DW-72 therefore has to cover
each of those sites (or consolidate them first). Nothing of the sort is
registered yet -- DW-72 is a separate item.
"""

import threading
from typing import Any, Dict, Optional

from flask import current_app
from sqlalchemy.engine import Engine

from .mariadb_storage import MariaDBStorage

# Key under which the app-scoped storage is memoized on ``app.extensions``.
STORAGE_EXTENSION_KEY = 'workshop_inventory_storage'

# Guards first-touch creation of the app-scoped storage.
_storage_lock = threading.Lock()


def _unwrap(app: Any) -> Any:
    """Return the real Flask app behind a ``current_app``-style proxy."""
    return getattr(app, '_get_current_object', lambda: app)()


def _is_usable(storage: Any) -> bool:
    """True when ``storage`` is cached *and* actually connected.

    The memoized value must satisfy what :func:`get_app_storage` promises, so
    this checks ``_connected`` and not merely ``engine is not None``: during a
    reconnect there is a moment where an engine exists but has not yet been
    validated.
    """
    return (storage is not None
            and getattr(storage, '_connected', False)
            and getattr(storage, 'engine', None) is not None)


def get_app_storage(app: Optional[Any] = None) -> MariaDBStorage:
    """
    Return the app-scoped connected ``MariaDBStorage``, creating it on first use.

    The storage -- and therefore its engine and connection pool -- is memoized on
    ``app.extensions`` and reused for the life of the process.

    Args:
        app: Flask application; defaults to ``current_app``.

    Returns:
        The connected ``MariaDBStorage`` owned by this app.

    Raises:
        ConnectionError: If the database cannot be reached. Nothing that looks
            connected is ever cached or handed out, so the next call retries: on
            first touch the storage is only memoized after a successful
            ``connect()``, and a *cached* storage whose reconnect failed stays in
            ``app.extensions`` but fails :func:`_is_usable`, so the next call
            reconnects it rather than returning it.
    """
    app = _unwrap(app if app is not None else current_app)

    storage = app.extensions.get(STORAGE_EXTENSION_KEY)
    if _is_usable(storage):
        return storage

    with _storage_lock:
        # Re-check under the lock: another thread may have won the race.
        storage = app.extensions.get(STORAGE_EXTENSION_KEY)
        if _is_usable(storage):
            return storage

        if storage is None:
            database_url: Optional[str] = app.config.get('SQLALCHEMY_DATABASE_URI')
            if not database_url:
                # Raised rather than letting MariaDBStorage's own
                # `database_url or Config.SQLALCHEMY_DATABASE_URI` fallback fire:
                # this app's config is the source of truth, and that fallback
                # would silently point an app that deliberately configured no
                # database at whatever the process-wide `.env` happens to hold.
                raise ConnectionError(
                    'Cannot connect to database: no SQLALCHEMY_DATABASE_URI '
                    'configured for this app')

            engine_options: Optional[Dict[str, Any]] = app.config.get('SQLALCHEMY_ENGINE_OPTIONS')
            storage = MariaDBStorage(
                database_url=database_url,
                engine_options=engine_options,
            )

        # Reached either on first touch or after someone called close() on the
        # cached storage: this function promises a *connected* storage, so a
        # closed one is reconnected rather than handed back with engine=None.
        result = storage.connect()
        if not result.success:
            # Do NOT cache a storage that only looks connected -- the next
            # request should get a fresh attempt.
            raise ConnectionError(f"Cannot connect to database: {result.error}")

        app.extensions[STORAGE_EXTENSION_KEY] = storage
        return storage


def get_storage_backend(app: Optional[Any] = None) -> Any:
    """
    Return the storage backend the current app should use.

    An injected ``STORAGE_BACKEND`` (unit tests, the e2e server) always wins; the
    app-scoped singleton is only the production fallback.

    Args:
        app: Flask application; defaults to ``current_app``.

    Returns:
        The injected storage backend, or the app-scoped ``MariaDBStorage``.
    """
    app = _unwrap(app if app is not None else current_app)

    injected = app.config.get('STORAGE_BACKEND')
    if injected is not None:
        return injected

    return get_app_storage(app)


def resolve_engine(storage: Any) -> Engine:
    """
    Return the SQLAlchemy engine belonging to ``storage``, connecting if needed.

    Services call this instead of building an engine of their own, so a service
    can never silently point at a different database than its storage does. The
    engine is *borrowed*: the caller must not dispose it.

    A non-``None`` ``engine`` attribute is adopted unchanged -- that keeps
    duck-typed/mock storages working -- and only a missing/``None`` engine
    triggers ``connect()``, which is itself idempotent and locked.

    Args:
        storage: A ``MariaDBStorage`` or any object exposing ``engine`` (and,
            when that engine is absent, ``connect()``).

    Returns:
        The storage's engine.

    Raises:
        ConnectionError: If the storage has no engine and cannot produce one.
    """
    engine = getattr(storage, 'engine', None)
    if engine is not None:
        return engine

    connect = getattr(storage, 'connect', None)
    if connect is None:
        raise ConnectionError(
            'Storage backend has no engine and no connect() to build one')

    result = connect()
    if not getattr(result, 'success', False):
        raise ConnectionError(
            f"Cannot connect to database: {getattr(result, 'error', None)}")

    engine = getattr(storage, 'engine', None)
    if engine is None:
        raise ConnectionError('Storage backend connected but exposes no engine')

    return engine
