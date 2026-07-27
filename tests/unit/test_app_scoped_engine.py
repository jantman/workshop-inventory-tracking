"""
Unit tests for the app-scoped SQLAlchemy engine (DW-32).

Covers every row of the spec's I/O & Edge-Case Matrix for
`spec-app-scoped-database-engine.md`:

* production apps memoize ONE connected storage (and one engine) per app,
* an injected `STORAGE_BACKEND` still wins and suppresses the singleton,
* two apps never share storage/engine,
* `app.config['SQLALCHEMY_DATABASE_URI']` -- not `config.Config` -- decides the
  engine's URL,
* a failed `connect()` raises `ConnectionError` and caches nothing,
* a borrowed engine survives `PhotoService.close()` while an owned one does not,
* duck-typed/mock storages are adopted unchanged.

Everything here runs against temp-file SQLite databases; the unit suite blocks
the network, so no MariaDB is involved.
"""

import os
import tempfile
import threading
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy import text

from app import create_app
from app.db import (STORAGE_EXTENSION_KEY, get_app_storage,
                    get_storage_backend, resolve_engine)
from app.database import Base
from app.mariadb_storage import MariaDBStorage
from app.storage import StorageResult
from config import Config
from tests.test_config import TestConfig


@pytest.fixture
def sqlite_uri():
    """A temp-file SQLite URI, torn down after the test."""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    uri = f'sqlite:///{temp_db.name}'

    yield uri

    try:
        os.unlink(temp_db.name)
    except OSError:
        pass


def _make_config(uri):
    """A production-shaped config class: real URI, no injected storage."""

    class _AppScopedConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = uri

    return _AppScopedConfig


@pytest.fixture
def prod_app(sqlite_uri):
    """A Flask app with NO injected STORAGE_BACKEND (the production shape)."""
    app = create_app(_make_config(sqlite_uri))
    assert 'STORAGE_BACKEND' not in app.config

    yield app

    storage = app.extensions.get(STORAGE_EXTENSION_KEY)
    if storage is not None:
        storage.close()


class _CountingStorage(MariaDBStorage):
    """MariaDBStorage that records how many times it has been constructed."""

    instances = 0
    # `instances += 1` is a non-atomic read-modify-write, and the test that
    # matters most drives eight threads through this constructor at once: a lost
    # update would report 1 and hide the double construction it is hunting for.
    _counter_lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        with type(self)._counter_lock:
            type(self).instances += 1
        super().__init__(*args, **kwargs)


class _FailingStorage:
    """Storage stand-in whose connect() fails until `fail_times` is exhausted."""

    # Declared so an instance is usable even if a test forgets to set it.
    fail_times = 0

    def __init__(self, database_url=None, engine_options=None):
        self.database_url = database_url
        self.engine_options = engine_options
        self.engine = None
        self.Session = None
        self._connected = False

    def connect(self) -> StorageResult:
        if type(self).fail_times > 0:
            type(self).fail_times -= 1
            return StorageResult(success=False, error='no route to host')
        self.engine = Mock(name='engine')
        self._connected = True
        return StorageResult(success=True, data='Connected')


class TestProductionSingleton:
    """Matrix row: production, repeated requests."""

    @pytest.mark.unit
    def test_repeated_calls_return_the_same_storage_and_engine(self, prod_app):
        with prod_app.app_context():
            first = get_storage_backend()
            second = get_storage_backend()
            third = get_app_storage(prod_app)

        assert first is second
        assert first is third
        assert first.engine is second.engine
        assert first._connected is True
        assert prod_app.extensions[STORAGE_EXTENSION_KEY] is first

    @pytest.mark.unit
    def test_only_one_storage_is_ever_constructed(self, prod_app):
        _CountingStorage.instances = 0
        with patch('app.db.MariaDBStorage', _CountingStorage):
            with prod_app.app_context():
                for _ in range(5):
                    get_storage_backend()

        assert _CountingStorage.instances == 1

    @pytest.mark.unit
    def test_services_across_requests_share_one_engine(self, prod_app):
        """Acceptance: N requests' InventoryService/CatalogService share an engine."""
        from app.mariadb_catalog_service import CatalogService
        from app.mariadb_inventory_service import InventoryService

        engines = []
        with prod_app.app_context():
            storage = get_storage_backend()
            Base.metadata.create_all(storage.engine)
            for _ in range(3):
                engines.append(InventoryService(get_storage_backend()).engine)
                engines.append(CatalogService(get_storage_backend()).engine)

        assert all(engine is engines[0] for engine in engines)
        assert engines[0] is prod_app.extensions[STORAGE_EXTENSION_KEY].engine


class TestInjectedStorageWins:
    """Matrix row: test injection."""

    @pytest.mark.unit
    def test_injected_backend_is_returned_and_singleton_never_built(self, app, test_storage):
        assert get_storage_backend(app) is test_storage
        with app.app_context():
            assert get_storage_backend() is test_storage

        assert STORAGE_EXTENSION_KEY not in app.extensions


class TestPerAppIsolation:
    """Matrix row: two distinct apps."""

    @pytest.mark.unit
    def test_two_apps_do_not_share_storage_or_engine(self, sqlite_uri):
        second_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        second_db.close()

        app_one = create_app(_make_config(sqlite_uri))
        app_two = create_app(_make_config(f'sqlite:///{second_db.name}'))
        try:
            storage_one = get_app_storage(app_one)
            storage_two = get_app_storage(app_two)

            assert storage_one is not storage_two
            assert storage_one.engine is not storage_two.engine
            assert str(storage_one.engine.url) != str(storage_two.engine.url)
        finally:
            for app in (app_one, app_two):
                storage = app.extensions.get(STORAGE_EXTENSION_KEY)
                if storage is not None:
                    storage.close()
            try:
                os.unlink(second_db.name)
            except OSError:
                pass


class TestUrlSourceOfTruth:
    """Matrix row: URL source of truth."""

    @pytest.mark.unit
    def test_engine_url_comes_from_app_config_not_the_config_class(self, prod_app, sqlite_uri):
        from config import Config

        # Pin the class-level URI to something distinguishable, so this asserts
        # that app.config won rather than passing vacuously because the class
        # attribute happens to be None with no .env present.
        with patch.object(Config, 'SQLALCHEMY_DATABASE_URI',
                          'mysql+pymysql://u:p@class-level/inventory'):
            with prod_app.app_context():
                storage = get_storage_backend()

            assert storage.database_url == sqlite_uri
            assert str(storage.engine.url) == sqlite_uri
            assert storage.database_url != Config.SQLALCHEMY_DATABASE_URI

    @pytest.mark.unit
    def test_engine_options_come_from_app_config(self, sqlite_uri):
        """Non-SQLite URLs take their pool options from `app.config`."""
        captured = {}

        class _RecordingConfig(TestConfig):
            SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://u:p@db/inventory'
            SQLALCHEMY_ENGINE_OPTIONS = {'pool_size': 3, 'pool_pre_ping': False}

        def _fake_create_engine(url, **kwargs):
            captured['url'] = url
            captured['kwargs'] = kwargs
            return MagicMock(name='engine')

        app = create_app(_RecordingConfig)
        with patch('app.mariadb_storage.create_engine', _fake_create_engine):
            storage = MariaDBStorage(
                database_url=app.config['SQLALCHEMY_DATABASE_URI'],
                engine_options=app.config['SQLALCHEMY_ENGINE_OPTIONS'],
            )
            result = storage.connect()

        assert result.success is True
        assert captured['url'] == 'mysql+pymysql://u:p@db/inventory'
        assert captured['kwargs'] == {'pool_size': 3, 'pool_pre_ping': False}

    @pytest.mark.unit
    def test_engine_options_fall_back_to_config_class(self):
        """With no explicit options, `config.Config`'s pool tuning is used."""
        from config import Config

        captured = {}

        def _fake_create_engine(url, **kwargs):
            captured['kwargs'] = kwargs
            return MagicMock(name='engine')

        with patch('app.mariadb_storage.create_engine', _fake_create_engine):
            storage = MariaDBStorage(database_url='mysql+pymysql://u:p@db/inventory')
            storage.connect()

        assert captured['kwargs'] == Config.SQLALCHEMY_ENGINE_OPTIONS

    @pytest.mark.unit
    def test_app_storage_forwards_both_app_config_values(self):
        """`get_app_storage` builds the storage from `app.config`, end to end.

        Asserted against the storage constructor rather than only against the
        resulting engine, because a SQLite URL makes `connect()` ignore the pool
        options -- so dropping `engine_options=` here would otherwise go unseen.
        """

        class _RecordingConfig(TestConfig):
            SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://u:p@db/inventory'
            SQLALCHEMY_ENGINE_OPTIONS = {'pool_size': 7, 'pool_pre_ping': False}

        captured = {}

        def _fake_storage(database_url=None, engine_options=None):
            captured['database_url'] = database_url
            captured['engine_options'] = engine_options
            storage = Mock(name='storage')
            storage.connect.return_value = StorageResult(success=True, data='Connected')
            return storage

        app = create_app(_RecordingConfig)
        with patch('app.db.MariaDBStorage', _fake_storage):
            get_app_storage(app)

        assert captured['database_url'] == 'mysql+pymysql://u:p@db/inventory'
        assert captured['engine_options'] == {'pool_size': 7, 'pool_pre_ping': False}


class TestConnectFailure:
    """Matrix row: DB unreachable."""

    @pytest.mark.unit
    def test_failure_raises_and_caches_nothing_then_retries(self, sqlite_uri):
        app = create_app(_make_config(sqlite_uri))
        _FailingStorage.fail_times = 1

        with patch('app.db.MariaDBStorage', _FailingStorage):
            with pytest.raises(ConnectionError) as excinfo:
                get_app_storage(app)

            # Nothing cached: a storage that never connected must not look like
            # the app's storage.
            assert STORAGE_EXTENSION_KEY not in app.extensions
            assert 'no route to host' in str(excinfo.value)

            # The next call retries and succeeds.
            storage = get_app_storage(app)

        assert storage._connected is True
        assert app.extensions[STORAGE_EXTENSION_KEY] is storage

    @pytest.mark.unit
    def test_resolve_engine_raises_when_storage_cannot_connect(self):
        storage = Mock()
        storage.engine = None
        storage.connect.return_value = StorageResult(success=False, error='boom')

        with pytest.raises(ConnectionError) as excinfo:
            resolve_engine(storage)

        assert 'boom' in str(excinfo.value)

    @pytest.mark.unit
    def test_failed_connect_disposes_the_partial_engine(self):
        """A connect() that blows up must not leave a live engine behind."""
        engine = Mock(name='engine')
        engine.connect.side_effect = RuntimeError('handshake failed')

        with patch('app.mariadb_storage.create_engine', return_value=engine):
            storage = MariaDBStorage(database_url='mysql+pymysql://u:p@db/inventory')
            result = storage.connect()

        assert result.success is False
        assert storage.engine is None
        assert storage._connected is False
        engine.dispose.assert_called_once()


class TestBorrowedVsOwnedEngine:
    """Matrix rows: borrowed engine closed / owned engine closed."""

    @pytest.mark.unit
    def test_context_manager_exit_leaves_the_shared_engine_usable(self, prod_app):
        from app.photo_service import PhotoService

        with prod_app.app_context():
            storage = get_storage_backend()
            Base.metadata.create_all(storage.engine)
            shared_engine = storage.engine

            with patch.object(shared_engine, 'dispose') as dispose:
                with PhotoService(storage) as photo_service:
                    assert photo_service.engine is shared_engine
                    assert photo_service._owns_engine is False
                assert photo_service.session is None
                dispose.assert_not_called()

            # The storage is still usable through the very same engine.
            assert storage.engine is shared_engine
            with storage.engine.connect() as conn:
                assert conn.execute(text('SELECT 1')).scalar() == 1

    @pytest.mark.unit
    def test_owned_engine_is_disposed_on_close(self):
        from app.photo_service import PhotoService

        owned_engine = Mock(name='engine')
        with patch('app.photo_service.create_engine', return_value=owned_engine), \
             patch('app.photo_service.sessionmaker') as mock_sessionmaker:
            mock_sessionmaker.return_value = Mock(return_value=Mock())

            service = PhotoService()
            assert service._owns_engine is True
            service.close()

        owned_engine.dispose.assert_called_once()
        assert service.engine is None


class TestDuckTypedStorage:
    """Matrix row: duck-typed/mock storage."""

    @pytest.mark.unit
    def test_truthy_engine_is_adopted_unchanged(self):
        storage = Mock()
        storage.engine = Mock(name='engine')

        assert resolve_engine(storage) is storage.engine
        storage.connect.assert_not_called()

    @pytest.mark.unit
    def test_none_engine_triggers_connect(self, sqlite_uri):
        storage = MariaDBStorage(database_url=sqlite_uri)
        assert storage.engine is None
        try:
            engine = resolve_engine(storage)

            assert engine is storage.engine
            assert storage._connected is True
        finally:
            storage.close()


class TestStorageLifecycle:
    """`connect()`/`close()` must never orphan a pool."""

    @pytest.mark.unit
    def test_close_resets_engine_and_session(self, sqlite_uri):
        storage = MariaDBStorage(database_url=sqlite_uri)
        storage.connect()
        assert storage.engine is not None

        storage.close()

        assert storage.engine is None
        assert storage.Session is None
        assert storage._connected is False

    @pytest.mark.unit
    def test_connect_is_idempotent(self, sqlite_uri):
        """A second connect() on a live storage must not swap the engine out.

        Services bind a sessionmaker to whatever engine they were given, so
        rebuilding on every call would leave them bound to a disposed one.
        """
        storage = MariaDBStorage(database_url=sqlite_uri)
        storage.connect()
        first_engine = storage.engine

        try:
            with patch.object(first_engine, 'dispose') as dispose:
                result = storage.connect()
                dispose.assert_not_called()

            assert result.success is True
            assert storage.engine is first_engine
        finally:
            storage.close()

    @pytest.mark.unit
    def test_reconnect_after_close_builds_a_fresh_engine(self, sqlite_uri):
        storage = MariaDBStorage(database_url=sqlite_uri)
        storage.connect()
        first_engine = storage.engine
        storage.close()

        storage.connect()
        try:
            assert storage.engine is not None
            assert storage.engine is not first_engine
            assert storage._connected is True
        finally:
            storage.close()

    @pytest.mark.unit
    def test_missing_database_url_reports_the_real_problem(self):
        """A `None` URL must not surface as `NoneType has no attribute startswith`."""
        with patch.object(Config, 'SQLALCHEMY_DATABASE_URI', None):
            storage = MariaDBStorage()
            result = storage.connect()

        assert result.success is False
        assert 'SQLALCHEMY_DATABASE_URI' in result.error
        assert storage.engine is None

    @pytest.mark.unit
    def test_get_session_survives_a_torn_down_session_factory(self, sqlite_uri):
        """`_get_session()` must never call a `Session` a racing close() nulled.

        A thread that passed the `_connected` check before `_dispose_engine()`
        cleared it is already committed to reading the factory, so it can find
        `Session is None` with `_connected` still True from its point of view.
        That state must reconnect, not raise `'NoneType' object is not callable`.
        """
        storage = MariaDBStorage(database_url=sqlite_uri)
        storage.connect()

        try:
            storage.Session = None  # what the racing close() left behind

            session = storage._get_session()
            try:
                assert storage.Session is not None
                assert session.execute(text('SELECT 1')).scalar() == 1
            finally:
                session.close()
        finally:
            storage.close()

    @pytest.mark.unit
    def test_dispose_errors_do_not_escape_connect(self, sqlite_uri):
        """connect() must return a StorageResult even if teardown misbehaves."""
        storage = MariaDBStorage(database_url=sqlite_uri)
        storage.connect()
        storage._connected = False  # force the dispose-then-rebuild path

        with patch.object(storage.engine, 'dispose', side_effect=RuntimeError('boom')):
            result = storage.connect()

        try:
            assert result.success is True
            assert storage.engine is not None
        finally:
            storage.close()

    @pytest.mark.unit
    def test_concurrent_first_touch_builds_exactly_one_storage(self, sqlite_uri):
        """The double-checked lock in `get_app_storage` under real contention."""
        app = create_app(_make_config(sqlite_uri))
        _CountingStorage.instances = 0
        # Timed out rather than bare: a worker that dies before reaching wait()
        # would otherwise hang the whole suite instead of failing this test.
        barrier = threading.Barrier(8)
        results = []
        errors = []

        def _worker():
            try:
                barrier.wait(timeout=30)
                results.append(get_app_storage(app))
            except Exception as exc:
                # Recorded, not swallowed: letting it kill the thread would
                # leave `results` empty and turn the assertions below into an
                # IndexError that hides the real concurrency failure.
                errors.append(exc)

        with patch('app.db.MariaDBStorage', _CountingStorage):
            threads = [threading.Thread(target=_worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        try:
            assert errors == []
            assert _CountingStorage.instances == 1
            assert len(results) == 8
            assert all(storage is results[0] for storage in results)
            assert all(storage.engine is results[0].engine for storage in results)
        finally:
            if results:
                results[0].close()

    @pytest.mark.unit
    def test_closed_singleton_is_reconnected_not_handed_back_dead(self, prod_app):
        """`get_app_storage` promises a *connected* storage, even after close()."""
        with prod_app.app_context():
            storage = get_app_storage(prod_app)
            storage.close()
            assert storage.engine is None

            revived = get_app_storage(prod_app)

        assert revived is storage
        assert revived.engine is not None
        assert revived._connected is True

    @pytest.mark.unit
    def test_app_context_teardown_removes_the_shared_session(self, prod_app):
        """The process-lifetime scoped_session must not accumulate per thread."""
        with prod_app.app_context():
            storage = get_app_storage(prod_app)

        with patch.object(storage.Session, 'remove') as remove:
            with prod_app.app_context():
                pass

            remove.assert_called_once()

    @pytest.mark.unit
    def test_teardown_leaves_injected_test_storage_alone(self, test_storage):
        """An injected backend's lifetime belongs to the fixture, not the app."""
        app = create_app(TestConfig, storage_backend=test_storage)

        with patch.object(test_storage.Session, 'remove') as remove:
            with app.app_context():
                pass

            remove.assert_not_called()


class TestExportServiceStorage:
    """Export services borrow the shared engine when handed a storage."""

    @pytest.mark.unit
    def test_export_service_adopts_storage_engine(self, prod_app):
        from app.export_service import (CombinedExportService,
                                        InventoryExportService,
                                        MaterialsExportService)

        with prod_app.app_context():
            storage = get_storage_backend()
            Base.metadata.create_all(storage.engine)

            inventory = InventoryExportService(storage=storage)
            materials = MaterialsExportService(storage=storage)
            combined = CombinedExportService(storage=storage)

        assert inventory.engine is storage.engine
        assert materials.engine is storage.engine
        assert combined.inventory_service.engine is storage.engine
        assert combined.materials_service.engine is storage.engine

    @pytest.mark.unit
    def test_database_uri_argument_still_builds_its_own_engine(self, sqlite_uri):
        from app.export_service import InventoryExportService

        service = InventoryExportService(database_uri=sqlite_uri)
        try:
            assert str(service.engine.url) == sqlite_uri
        finally:
            service.engine.dispose()


class TestRoutesUseTheAppScopedStorage:
    """Acceptance: N *requests* against a production-shaped app share one engine.

    The rest of this file drives `app.db` directly, which cannot tell whether
    the blueprints actually delegate to it -- every other route test in the
    suite uses the `app` fixture, whose injected `STORAGE_BACKEND` short-circuits
    `get_storage_backend` before the singleton is reached. These tests go through
    the real request path on an app with no injected backend, so reverting either
    blueprint's `_get_storage_backend()` to `MariaDBStorage()` fails here.
    """

    @staticmethod
    def _prepare(prod_app):
        with prod_app.app_context():
            storage = get_app_storage(prod_app)
            Base.metadata.create_all(storage.engine)
        return storage

    @pytest.mark.unit
    def test_main_blueprint_requests_resolve_the_shared_engine(self, prod_app):
        import app.main.routes as main_routes

        shared = self._prepare(prod_app)
        real_resolve = main_routes.resolve_engine
        seen = []

        def _spy(storage):
            engine = real_resolve(storage)
            seen.append((storage, engine))
            return engine

        client = prod_app.test_client()
        with patch.object(main_routes, 'resolve_engine', _spy):
            for _ in range(3):
                response = client.get('/api/materials/hierarchy')
                assert response.status_code == 200
                assert response.get_json()['success'] is True

        assert len(seen) == 3
        assert all(storage is shared for storage, _ in seen)
        assert all(engine is shared.engine for _, engine in seen)

    @pytest.mark.unit
    def test_admin_blueprint_requests_use_the_shared_storage(self, prod_app):
        import app.admin.routes as admin_routes

        shared = self._prepare(prod_app)
        real_service = admin_routes._get_admin_service
        seen = []

        def _spy(storage):
            seen.append(storage)
            return real_service(storage)

        client = prod_app.test_client()
        with patch.object(admin_routes, '_get_admin_service', _spy):
            for _ in range(3):
                response = client.get('/admin/materials')
                assert response.status_code == 200

        assert len(seen) == 3
        assert all(storage is shared for storage in seen)

    @pytest.mark.unit
    def test_requests_never_build_a_second_storage(self, prod_app):
        """No engine is created after the first, across N requests."""
        self._prepare(prod_app)
        _CountingStorage.instances = 0

        client = prod_app.test_client()
        with patch('app.db.MariaDBStorage', _CountingStorage):
            for _ in range(3):
                assert client.get('/api/materials/hierarchy').status_code == 200

        assert _CountingStorage.instances == 0


class TestConfigurationGuards:
    """`app.config` really is the source of truth, and teardown never escapes."""

    @pytest.mark.unit
    def test_unset_app_config_uri_raises_instead_of_using_the_config_class(self):
        """An app that configures no database must not inherit `.env`'s."""

        class _NoUriConfig(TestConfig):
            SQLALCHEMY_DATABASE_URI = None

        app = create_app(_NoUriConfig)

        with patch.object(Config, 'SQLALCHEMY_DATABASE_URI',
                          'mysql+pymysql://u:p@class-level/inventory'):
            with pytest.raises(ConnectionError) as excinfo:
                get_app_storage(app)

        assert 'SQLALCHEMY_DATABASE_URI' in str(excinfo.value)
        assert STORAGE_EXTENSION_KEY not in app.extensions

    @pytest.mark.unit
    def test_teardown_swallows_session_removal_errors(self, prod_app):
        """A failing `Session.remove()` must not escape `AppContext.pop()`."""
        with prod_app.app_context():
            storage = get_app_storage(prod_app)

        with patch.object(storage.Session, 'remove', side_effect=RuntimeError('boom')):
            with prod_app.app_context():
                pass  # popping the context must not raise

    @pytest.mark.unit
    def test_half_built_engine_is_not_published_on_the_storage(self):
        """`self.engine` is only set once the engine has passed SELECT 1.

        A lock-free reader (`app.db`'s fast path, `resolve_engine`) must never
        see an engine that connect() is about to dispose.
        """
        engine = Mock(name='engine')
        engine.connect.side_effect = RuntimeError('handshake failed')
        observed = []

        storage = MariaDBStorage(database_url='mysql+pymysql://u:p@db/inventory')

        def _fake_create_engine(*args, **kwargs):
            observed.append(storage.engine)
            return engine

        with patch('app.mariadb_storage.create_engine', _fake_create_engine):
            result = storage.connect()

        assert result.success is False
        assert observed == [None]
        assert storage.engine is None

    @pytest.mark.unit
    def test_cached_but_unconnected_storage_is_not_handed_back(self, prod_app):
        """Memoization honors `_connected`, not just a non-None engine."""
        with prod_app.app_context():
            storage = get_app_storage(prod_app)

        # The shape a reconnect passes through: an engine exists but has not
        # been validated yet.
        storage._connected = False
        try:
            with prod_app.app_context():
                revived = get_app_storage(prod_app)

            assert revived is storage
            assert revived._connected is True
        finally:
            storage.close()
