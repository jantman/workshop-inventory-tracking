"""
Test Server Management for E2E Tests

Handles Flask application server startup/shutdown for browser testing.
"""

import threading
import time
import requests
import socket
from contextlib import closing
from werkzeug.serving import make_server
from app import create_app
from app.test_storage import TestStorage
from tests.test_config import TestConfig


class TestServer:
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
            
        # Create test storage
        self.storage = TestStorage()
        self.storage.connect()
        
        # Set up test inventory sheet (using 'Metal' to match inventory service)
        # Import headers from InventoryService to ensure consistency
        from app.inventory_service import InventoryService
        headers = InventoryService.SHEET_HEADERS
        result = self.storage.create_sheet('Metal', headers)
        print(f"DEBUG: Created Metal sheet with result: {result}")
        
        # Verify the sheet was created
        info_result = self.storage.get_sheet_info('Metal')
        print(f"DEBUG: Sheet info after creation: {info_result}")
        
        # Create Flask app with test storage
        self.app = create_app(TestConfig, storage_backend=self.storage)
        
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
            
        # Use the InventoryService to add items properly
        from app.inventory_service import InventoryService
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
                
                item = Item(
                    ja_id=item_data.get('ja_id', 'JA000000'),
                    item_type=ItemType(item_data.get('item_type', 'Rod')),
                    shape=ItemShape(item_data.get('shape', 'Round')),
                    material=item_data.get('material', 'Steel'),
                    dimensions=Dimensions(
                        length=Decimal(str(item_data.get('length', '100'))),
                        width=Decimal(str(item_data.get('width', '10')))
                    )
                )
                service.add_item(item)
    
    def clear_test_data(self):
        """Clear all test data from storage"""
        if self.storage:
            self.storage.clear_all_data()
            # Recreate the inventory sheet with current headers
            from app.inventory_service import InventoryService
            headers = InventoryService.SHEET_HEADERS
            self.storage.create_sheet('Metal', headers)
    
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
        _test_server = TestServer()
    return _test_server