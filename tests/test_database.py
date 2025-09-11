"""
Database testing utilities and fixtures for MariaDB integration tests.

Provides MariaDB-specific test setup, fixtures, and utilities for testing
with the actual database backend instead of in-memory storage.
"""

import pytest
import os
import tempfile
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool

from config import TestConfig
from app.database import Base, InventoryItem, MaterialTaxonomy


class DatabaseTestConfig(TestConfig):
    """Test configuration specifically for database integration tests"""
    
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        """Override for test database URI"""
        if os.environ.get('USE_TEST_MARIADB') == '1':
            # Use MariaDB test container
            return super().SQLALCHEMY_DATABASE_URI
        else:
            # Fall back to SQLite for unit tests
            db_path = os.environ.get('TEST_DATABASE_PATH', ':memory:')
            return f'sqlite:///{db_path}?check_same_thread=false'


@pytest.fixture(scope="session")
def mariadb_engine():
    """Session-scoped MariaDB engine for integration tests"""
    if os.environ.get('USE_TEST_MARIADB') != '1':
        pytest.skip("MariaDB integration tests require USE_TEST_MARIADB=1")
    
    config = DatabaseTestConfig()
    engine = create_engine(
        config.SQLALCHEMY_DATABASE_URI,
        **config.SQLALCHEMY_ENGINE_OPTIONS
    )
    
    # Test connection
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"Cannot connect to MariaDB test database: {e}")
    
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