"""
Database testing utilities and fixtures for MariaDB integration tests.

Provides MariaDB-specific test setup, fixtures, and utilities for testing
with the actual database backend instead of in-memory storage.
"""

import pytest
import os
import tempfile
import sqlalchemy as sa
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool

from config import TestConfig
from app.database import Base, InventoryItem, MaterialTaxonomy


@pytest.fixture(scope="session")
def mariadb_testcontainer():
    """Session-scoped MariaDB testcontainer for local e2e testing"""
    # Skip testcontainer in CI - use service container instead
    if os.environ.get('CI') == 'true':
        pytest.skip("Using MariaDB service container in CI")
    
    try:
        from testcontainers.mysql import MySqlContainer
    except ImportError:
        pytest.skip("testcontainers not installed - run: pip install testcontainers[mysql]")
    
    # Start MariaDB container with same config as CI
    container = MySqlContainer("mariadb:10.11")
    container = container.with_env("MYSQL_ROOT_PASSWORD", "test_root_password")
    container = container.with_env("MYSQL_DATABASE", "workshop_inventory_test") 
    container = container.with_env("MYSQL_USER", "inventory_test_user")
    container = container.with_env("MYSQL_PASSWORD", "test_password")
    container = container.with_env("MARIADB_CHARACTER_SET_SERVER", "utf8mb4")
    container = container.with_env("MARIADB_COLLATION_SERVER", "utf8mb4_unicode_ci")
    
    with container:
        # Set SQLALCHEMY_DATABASE_URI directly from testcontainer
        connection_url = container.get_connection_url()
        os.environ['SQLALCHEMY_DATABASE_URI'] = connection_url
        print(f"✅ MariaDB testcontainer ready: {connection_url}")
        
        yield container




@pytest.fixture(scope="session")
def mariadb_engine(mariadb_testcontainer):
    """Session-scoped MariaDB engine for e2e tests"""
    # testcontainer fixture sets SQLALCHEMY_DATABASE_URI environment variable
    
    config = TestConfig()  # Uses SQLALCHEMY_DATABASE_URI from environment
    engine = create_engine(
        config.SQLALCHEMY_DATABASE_URI,
        **config.SQLALCHEMY_ENGINE_OPTIONS
    )
    
    # Test connection
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
            print(f"✅ Connected to MariaDB: {config.SQLALCHEMY_DATABASE_URI}")
    except Exception as e:
        pytest.fail(f"Cannot connect to MariaDB database: {e}")
    
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def sqlite_engine():
    """Session-scoped SQLite engine for unit tests"""
    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool
    )
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine(request):
    """Fixture that returns appropriate engine based on test markers"""
    if request.node.get_closest_marker("integration"):
        # Integration tests use MariaDB
        return request.getfixturevalue("mariadb_engine")
    else:
        # Unit tests use SQLite
        return request.getfixturevalue("sqlite_engine")


@pytest.fixture
def db_session(db_engine):
    """Database session fixture with automatic rollback"""
    # Create all tables
    Base.metadata.create_all(db_engine)
    
    # Create session
    Session = scoped_session(sessionmaker(bind=db_engine))
    session = Session()
    
    # Start transaction
    transaction = session.begin()
    
    try:
        yield session
    finally:
        # Always rollback to keep tests isolated
        transaction.rollback()
        session.close()
        Session.remove()


@pytest.fixture
def clean_db(db_engine):
    """Clean database fixture - creates/drops all tables"""
    # Create all tables
    Base.metadata.create_all(db_engine)
    
    yield db_engine
    
    # Clean up by dropping all tables
    Base.metadata.drop_all(db_engine)


@pytest.fixture
def sample_inventory_item():
    """Sample inventory item for testing"""
    return InventoryItem(
        ja_id="JA000001",
        active=True,
        length=1000.0,
        width=25.0,
        item_type="Bar",
        shape="Round",
        material="Steel",
        quantity=1,
        location="Test Location",
        notes="Sample item for testing"
    )


@pytest.fixture
def sample_material_taxonomy():
    """Sample material taxonomy entries for testing"""
    return [
        MaterialTaxonomy(
            name="Metals",
            level=1,
            parent=None,
            aliases="Metal,Metallic",
            active=True,
            sort_order=1,
            notes="Category for all metals"
        ),
        MaterialTaxonomy(
            name="Ferrous",
            level=2,
            parent="Metals",
            aliases="Iron-based",
            active=True,
            sort_order=1,
            notes="Iron-based metals"
        ),
        MaterialTaxonomy(
            name="Steel",
            level=3,
            parent="Ferrous",
            aliases="Carbon Steel,Mild Steel",
            active=True,
            sort_order=1,
            notes="Standard carbon steel"
        )
    ]


@pytest.fixture
def populated_db(db_session, sample_inventory_item, sample_material_taxonomy):
    """Database session with sample data pre-populated"""
    # Add inventory item
    db_session.add(sample_inventory_item)
    
    # Add material taxonomy
    for material in sample_material_taxonomy:
        db_session.add(material)
    
    db_session.commit()
    
    return db_session


def wait_for_mariadb(max_retries=30, retry_delay=1):
    """Wait for MariaDB to be ready for connections"""
    import time
    from sqlalchemy.exc import OperationalError
    
    config = DatabaseTestConfig()
    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    
    for attempt in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            engine.dispose()
            return True
        except OperationalError:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            else:
                engine.dispose()
                return False
    
    return False


def create_test_data(session):
    """Create standard test data for E2E tests"""
    # Create material taxonomy
    materials = [
        MaterialTaxonomy(name="Metals", level=1, parent=None, active=True, sort_order=1),
        MaterialTaxonomy(name="Ferrous", level=2, parent="Metals", active=True, sort_order=1),
        MaterialTaxonomy(name="Steel", level=3, parent="Ferrous", active=True, sort_order=1),
        MaterialTaxonomy(name="Aluminum", level=3, parent="Non-Ferrous", active=True, sort_order=2),
        MaterialTaxonomy(name="Non-Ferrous", level=2, parent="Metals", active=True, sort_order=2),
    ]
    
    for material in materials:
        session.add(material)
    
    # Create sample inventory items
    items = [
        InventoryItem(
            ja_id="JA000001",
            active=True,
            length=1000.0,
            width=25.0,
            item_type="Bar",
            shape="Round", 
            material="Steel",
            quantity=1,
            location="Shop A",
            notes="Standard steel bar"
        ),
        InventoryItem(
            ja_id="JA000002", 
            active=True,
            length=500.0,
            width=50.0,
            thickness=10.0,
            item_type="Plate",
            shape="Rectangular",
            material="Aluminum",
            quantity=1,
            location="Rack B",
            notes="Aluminum plate"
        )
    ]
    
    for item in items:
        session.add(item)
    
    session.commit()
    return len(materials), len(items)