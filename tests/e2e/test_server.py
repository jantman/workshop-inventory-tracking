"""
Test Server Management for E2E Tests

Handles Flask application server startup/shutdown for browser testing.
"""

import threading
import time
import requests
import socket
import tempfile
import os
from contextlib import closing
from werkzeug.serving import make_server
from app import create_app
from app.mariadb_storage import MariaDBStorage
from tests.test_config import TestConfig
from tests.test_database import DatabaseTestConfig
from app.database import Base, InventoryItem, MaterialTaxonomy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class E2ETestServer:
    """Manages Flask test server for E2E testing"""
    
    def __init__(self, host='127.0.0.1', port=None):
        self.host = host
        self.port = port or self._find_free_port()
        self.server = None
        self.thread = None
        self.storage = None
        self.app = None
        
    def _find_free_port(self):
        """Find a free port for the test server"""
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    def start(self):
        """Start the test server in a separate thread"""
        if self.thread and self.thread.is_alive():
            return  # Already running
            
        # Create temporary SQLite database for E2E tests
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()  # Close the file handle, keep the path
        
        # Set up test database URI
        test_db_uri = f'sqlite:///{self.temp_db.name}?check_same_thread=false'
        
        # Create test engine and initialize database
        self.engine = create_engine(test_db_uri)
        Base.metadata.create_all(self.engine)
        
        # Create MariaDB storage instance with test database
        self.storage = MariaDBStorage(database_url=test_db_uri)
        self.storage.connect()
        
        print(f"✅ E2E test database initialized at: {test_db_uri}")
        
        # Create Flask app with test storage
        self.app = create_app(TestConfig, storage_backend=self.storage)
        
        # Set up Materials taxonomy for hierarchical system (after app creation)
        self.setup_materials_taxonomy()
        
        # Create server
        self.server = make_server(
            self.host, 
            self.port, 
            self.app,
            threaded=True
        )
        
        # Start server in background thread
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True
        )
        self.thread.start()
        
        # Wait for server to be ready
        self._wait_for_server()
    
    def stop(self):
        """Stop the test server"""
        if self.server:
            self.server.shutdown()
            self.server = None
            
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)
            self.thread = None
            
        if self.storage:
            self.storage.close()
            self.storage = None
            
        # Clean up temporary database file
        if hasattr(self, 'temp_db') and self.temp_db and os.path.exists(self.temp_db.name):
            try:
                os.unlink(self.temp_db.name)
                print(f"🧹 Cleaned up test database: {self.temp_db.name}")
            except OSError as e:
                print(f"⚠️ Failed to clean up test database {self.temp_db.name}: {e}")
            self.temp_db = None
    
    def _wait_for_server(self, timeout=10):
        """Wait for the server to be ready to accept requests"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f'http://{self.host}:{self.port}/health', timeout=1)
                if response.status_code == 200:
                    return True
            except (requests.RequestException, ConnectionError):
                time.sleep(0.1)
        
        raise TimeoutError(f"Test server failed to start within {timeout} seconds")
    
    @property 
    def url(self):
        """Get the base URL of the test server"""
        return f'http://{self.host}:{self.port}'
    
    def add_test_data(self, items_data):
        """Add test data to the storage backend"""
        if not self.storage:
            raise RuntimeError("Server not started")
            
        # Use the InventoryService to add items directly to database
        from app.mariadb_inventory_service import InventoryService
        service = InventoryService(self.storage)
        
        # Convert items to Item objects and add via service
        for item_data in items_data:
            # If item_data is already an Item object, add it directly
            if hasattr(item_data, 'ja_id'):
                service.add_item(item_data)
            else:
                # Convert dict to Item object if needed
                from app.models import Item, ItemType, ItemShape, Dimensions
                from decimal import Decimal
                
                # Create dimensions from available data
                dimensions_data = {}
                if 'length' in item_data:
                    dimensions_data['length'] = Decimal(str(item_data['length']))
                if 'width' in item_data:
                    dimensions_data['width'] = Decimal(str(item_data['width']))
                if 'thickness' in item_data:
                    dimensions_data['thickness'] = Decimal(str(item_data['thickness']))
                if 'wall_thickness' in item_data:
                    dimensions_data['wall_thickness'] = Decimal(str(item_data['wall_thickness']))
                if 'weight' in item_data:
                    dimensions_data['weight'] = Decimal(str(item_data['weight']))
                
                dimensions = Dimensions(**dimensions_data) if dimensions_data else None
                
                item = Item(
                    ja_id=item_data.get('ja_id', 'JA000000'),
                    item_type=ItemType(item_data.get('item_type', 'Rod')),
                    shape=ItemShape(item_data.get('shape', 'Round')),
                    material=item_data.get('material', 'Steel'),
                    dimensions=dimensions,
                    location=item_data.get('location'),
                    notes=item_data.get('notes'),
                    active=item_data.get('active', True)
                )
                service.add_item(item)
        
        # InventoryService writes directly to database - no batching or flushing needed
        print(f"Added {len(items_data)} test items directly to database")
    
    def setup_materials_taxonomy(self):
        """Setup Materials sheet with hierarchical taxonomy for testing"""
        if not self.storage:
            raise RuntimeError("Server not started")
        
        # Materials sheet already exists in MariaDBStorage, just populate it
        
        # Add basic taxonomy data for testing
        taxonomy_data = [
            # Categories (Level 1)
            ['Carbon Steel', 1, '', 'Steel', True, 1, '2025-01-01', 'Structural and general purpose steel'],
            ['Stainless Steel', 1, '', 'Stainless', True, 2, '2025-01-01', 'Corrosion resistant steel alloys'],
            ['Aluminum', 1, '', 'Al', True, 3, '2025-01-01', 'Lightweight aluminum alloys'],
            ['Brass', 1, '', '', True, 4, '2025-01-01', 'Copper-zinc alloys'],
            ['Copper', 1, '', 'Cu', True, 5, '2025-01-01', 'Pure copper and copper alloys'],
            ['Tool Steel', 1, '', '', True, 6, '2025-01-01', 'High carbon steel for tools'],
            
            # Families (Level 2) 
            ['Medium Carbon Steel', 2, 'Carbon Steel', '4140 Series', True, 1, '2025-01-01', '0.3-0.6% carbon content'],
            ['Free Machining Steel', 2, 'Carbon Steel', 'Leaded Steel', True, 2, '2025-01-01', 'Enhanced machinability'],
            ['Austenitic Stainless', 2, 'Stainless Steel', '300 Series', True, 1, '2025-01-01', 'Non-magnetic stainless'],
            ['6000 Series', 2, 'Aluminum', 'Al-Mg-Si', True, 1, '2025-01-01', 'Heat treatable aluminum'],
            
            # Specific Materials (Level 3)
            ['4140', 3, 'Medium Carbon Steel', '4140 Steel', True, 1, '2025-01-01', 'Chromium-molybdenum alloy steel'],
            ['4140 Pre-Hard', 3, 'Medium Carbon Steel', '4140 PHB', True, 2, '2025-01-01', 'Pre-hardened 4140 steel'],
            ['12L14', 3, 'Free Machining Steel', '', True, 1, '2025-01-01', 'Leaded free-machining steel'],
            ['304', 3, 'Austenitic Stainless', '304 Stainless,SS304', True, 1, '2025-01-01', 'General purpose stainless'],
            ['304L', 3, 'Austenitic Stainless', '304L Stainless', True, 2, '2025-01-01', 'Low carbon 304'],
            ['316', 3, 'Austenitic Stainless', '316 Stainless,SS316', True, 3, '2025-01-01', 'Molybdenum-enhanced stainless'],
            ['316L', 3, 'Austenitic Stainless', '316L Stainless', True, 4, '2025-01-01', 'Low carbon 316'],
            ['321', 3, 'Austenitic Stainless', '321 Stainless', True, 5, '2025-01-01', 'Titanium stabilized'],
            ['6061-T6', 3, '6000 Series', '6061,6061 T6', True, 1, '2025-01-01', 'Heat treated aluminum'],
            ['360 Brass', 3, 'Brass', 'Brass 360', True, 1, '2025-01-01', 'Free machining brass'],
            ['C10100', 3, 'Copper', 'Pure Copper', True, 1, '2025-01-01', 'Oxygen-free copper']
        ]
        
        # Add taxonomy data to Materials sheet using database directly
        from app.database import MaterialTaxonomy
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=self.engine)
        session = Session()
        
        try:
            # Clear existing materials first
            session.query(MaterialTaxonomy).delete()
            
            # Add taxonomy data
            for row_data in taxonomy_data:
                name, level, parent, aliases, active, sort_order, created_date, notes = row_data
                material = MaterialTaxonomy(
                    name=name,
                    level=level, 
                    parent=parent if parent else None,
                    aliases=aliases if aliases else None,
                    active=active,
                    sort_order=sort_order,
                    notes=notes
                    # date_added and last_modified will be set automatically by default/func.now()
                )
                session.add(material)
            
            session.commit()
            print(f"✅ Materials taxonomy initialized with {len(taxonomy_data)} entries")
            
        except Exception as e:
            session.rollback()
            print(f"Error initializing materials taxonomy: {e}")
            import traceback
            traceback.print_exc()
        finally:
            session.close()

    def clear_test_data(self):
        """Clear all test data from database"""
        if self.storage and hasattr(self, 'engine'):
            # Clear all data from database tables
            Session = sessionmaker(bind=self.engine)
            session = Session()
            try:
                # Delete all inventory items and materials taxonomy
                session.query(InventoryItem).delete()
                session.query(MaterialTaxonomy).delete()
                session.commit()
                print("🧹 Cleared all test data from database")
            except Exception as e:
                session.rollback()
                print(f"⚠️ Error clearing test data: {e}")
            finally:
                session.close()
            
            # Re-setup materials taxonomy for tests
            self.setup_materials_taxonomy()
    
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()


# Global test server instance for sharing across tests
_test_server = None

def get_test_server():
    """Get the global test server instance"""
    global _test_server
    if _test_server is None:
        _test_server = E2ETestServer()
    return _test_server