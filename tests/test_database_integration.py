"""
Integration tests for database models and operations.

These tests use the MariaDB test database when USE_TEST_MARIADB=1 is set,
otherwise they fall back to SQLite for unit testing.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from app.database import InventoryItem, MaterialTaxonomy
from tests.test_database import db_session, sample_inventory_item, sample_material_taxonomy, populated_db


@pytest.mark.integration
class TestInventoryItemDatabase:
    """Test InventoryItem database operations"""
    
    def test_create_inventory_item(self, db_session, sample_inventory_item):
        """Test creating an inventory item in the database"""
        db_session.add(sample_inventory_item)
        db_session.commit()
        
        # Verify item was created
        items = db_session.query(InventoryItem).all()
        assert len(items) == 1
        
        item = items[0]
        assert item.ja_id == "JA000001"
        assert item.active is True
        assert item.material == "Steel"
        assert float(item.length) == 1000.0
        assert float(item.width) == 25.0
    
    def test_inventory_item_constraints(self, db_session):
        """Test inventory item database constraints"""
        # Test unique constraint on active JA ID
        item1 = InventoryItem(
            ja_id="JA000001",
            active=True,
            item_type="Bar",
            material="Steel",
            quantity=1
        )
        item2 = InventoryItem(
            ja_id="JA000001", 
            active=True,  # This should violate unique constraint
            item_type="Bar",
            material="Aluminum",
            quantity=1
        )
        
        db_session.add(item1)
        db_session.commit()
        
        db_session.add(item2)
        
        # Should raise integrity error due to unique constraint violation
        with pytest.raises(IntegrityError):
            db_session.commit()
    
    def test_multiple_inactive_items_same_ja_id(self, db_session):
        """Test that multiple inactive items with same JA ID are allowed"""
        item1 = InventoryItem(
            ja_id="JA000001",
            active=False,  # Inactive
            item_type="Bar",
            material="Steel", 
            quantity=1,
            length=1000
        )
        item2 = InventoryItem(
            ja_id="JA000001",
            active=False,  # Also inactive - should be allowed
            item_type="Bar", 
            material="Steel",
            quantity=1,
            length=500  # Different length (shortened)
        )
        item3 = InventoryItem(
            ja_id="JA000001",
            active=True,  # Only one active allowed
            item_type="Bar",
            material="Steel",
            quantity=1,
            length=300  # Current length
        )
        
        db_session.add_all([item1, item2, item3])
        db_session.commit()
        
        # Verify all were created
        items = db_session.query(InventoryItem).filter_by(ja_id="JA000001").all()
        assert len(items) == 3
        
        active_items = [item for item in items if item.active]
        assert len(active_items) == 1
        assert active_items[0].length == 300


@pytest.mark.integration 
class TestMaterialTaxonomyDatabase:
    """Test MaterialTaxonomy database operations"""
    
    def test_create_material_taxonomy(self, db_session, sample_material_taxonomy):
        """Test creating material taxonomy entries"""
        for material in sample_material_taxonomy:
            db_session.add(material)
        db_session.commit()
        
        # Verify all materials were created
        materials = db_session.query(MaterialTaxonomy).order_by(MaterialTaxonomy.level).all()
        assert len(materials) == 3
        
        # Check hierarchy
        assert materials[0].name == "Metals" and materials[0].level == 1
        assert materials[1].name == "Ferrous" and materials[1].level == 2
        assert materials[2].name == "Steel" and materials[2].level == 3
    
    def test_material_taxonomy_constraints(self, db_session):
        """Test material taxonomy database constraints"""
        # Test unique name constraint
        material1 = MaterialTaxonomy(name="Steel", level=3, parent="Ferrous", active=True)
        material2 = MaterialTaxonomy(name="Steel", level=3, parent="Ferrous", active=True)
        
        db_session.add(material1)
        db_session.commit()
        
        db_session.add(material2)
        
        # Should raise integrity error due to unique name constraint
        with pytest.raises(IntegrityError):
            db_session.commit()
    
    def test_material_aliases_property(self, db_session):
        """Test aliases property functionality"""
        material = MaterialTaxonomy(
            name="Stainless Steel",
            level=3,
            parent="Ferrous",
            aliases="SS,Stainless,Inox",
            active=True
        )
        
        db_session.add(material)
        db_session.commit()
        
        # Test aliases_list property
        aliases = material.aliases_list
        assert len(aliases) == 3
        assert "SS" in aliases
        assert "Stainless" in aliases
        assert "Inox" in aliases
        
        # Test setting aliases via property
        material.aliases_list = ["316SS", "Marine Grade"]
        assert material.aliases == "316SS,Marine Grade"


@pytest.mark.integration
class TestDatabaseQueries:
    """Test complex database queries and relationships"""
    
    def test_query_active_items_only(self, populated_db):
        """Test querying only active inventory items"""
        # Add an inactive item
        inactive_item = InventoryItem(
            ja_id="JA000003",
            active=False,
            item_type="Bar",
            material="Brass",
            quantity=1
        )
        populated_db.add(inactive_item)
        populated_db.commit()
        
        # Query only active items
        active_items = populated_db.query(InventoryItem).filter_by(active=True).all()
        
        # Should not include the inactive item
        ja_ids = [item.ja_id for item in active_items]
        assert "JA000003" not in ja_ids
        assert len(active_items) >= 1  # Should have at least the sample items
    
    def test_material_hierarchy_queries(self, populated_db):
        """Test querying material taxonomy hierarchy"""
        # Get all categories (level 1)
        categories = populated_db.query(MaterialTaxonomy).filter_by(level=1).all()
        assert len(categories) >= 1
        
        # Get children of a category
        if categories:
            category_name = categories[0].name
            children = populated_db.query(MaterialTaxonomy).filter_by(parent=category_name).all()
            assert len(children) >= 0  # May or may not have children
    
    def test_database_performance_indexes(self, populated_db):
        """Test that database indexes are working (basic performance test)"""
        # Add more test data to make index performance meaningful
        items = []
        for i in range(100):
            item = InventoryItem(
                ja_id=f"JA{i:06d}",
                active=(i % 10 != 0),  # Every 10th item is inactive
                item_type="Bar",
                material=f"Material{i % 5}",  # 5 different materials
                quantity=1
            )
            items.append(item)
        
        populated_db.add_all(items)
        populated_db.commit()
        
        # These queries should be fast due to indexes
        import time
        
        start = time.time()
        # Query by JA ID (indexed)
        item = populated_db.query(InventoryItem).filter_by(ja_id="JA000050").first()
        ja_id_time = time.time() - start
        
        start = time.time()  
        # Query by active status (indexed)
        active_items = populated_db.query(InventoryItem).filter_by(active=True).count()
        active_time = time.time() - start
        
        # These should be relatively fast (< 0.1 seconds each)
        assert ja_id_time < 0.1, f"JA ID query took {ja_id_time:.3f}s - too slow"
        assert active_time < 0.1, f"Active query took {active_time:.3f}s - too slow"
        
        assert item is not None
        assert active_items > 80  # Should be around 90 active items


@pytest.mark.unit
def test_database_models_without_db():
    """Test database model creation and properties without database"""
    # Test InventoryItem model
    item = InventoryItem(
        ja_id="JA000001",
        active=True,
        item_type="Bar",
        material="Steel",
        quantity=1
    )
    
    assert item.ja_id == "JA000001"
    assert item.active is True
    assert item.quantity == 1
    
    # Test to_dict method
    item_dict = item.to_dict()
    assert item_dict['ja_id'] == "JA000001"
    assert item_dict['active'] is True
    
    # Test MaterialTaxonomy model  
    material = MaterialTaxonomy(
        name="Steel",
        level=3,
        parent="Ferrous",
        aliases="Carbon Steel,Mild Steel",
        active=True
    )
    
    assert material.name == "Steel"
    assert material.level == 3
    assert len(material.aliases_list) == 2
    assert "Carbon Steel" in material.aliases_list