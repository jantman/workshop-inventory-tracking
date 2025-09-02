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
        
        # Set up test inventory sheet
        headers = [
            'JA_ID', 'Item_Type', 'Shape', 'Material', 'Length_mm', 'Width_mm', 
            'Height_mm', 'Diameter_mm', 'Thread_Series', 'Thread_Handedness', 
            'Thread_Length_mm', 'Location', 'Notes', 'Parent_JA_ID', 'Active'
        ]
        self.storage.create_sheet('Inventory', headers)
        
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
            
        # Convert items to storage format and add to database
        for item_data in items_data:
            row = [
                item_data.get('ja_id', ''),
                item_data.get('item_type', ''),
                item_data.get('shape', ''),
                item_data.get('material', ''),
                str(item_data.get('length_mm', '')),
                str(item_data.get('width_mm', '')),
                str(item_data.get('height_mm', '')),
                str(item_data.get('diameter_mm', '')),
                item_data.get('thread_series', ''),
                item_data.get('thread_handedness', ''),
                str(item_data.get('thread_length_mm', '')),
                item_data.get('location', ''),
                item_data.get('notes', ''),
                item_data.get('parent_ja_id', ''),
                str(item_data.get('active', True))
            ]
            self.storage.write_row('Inventory', row)
    
    def clear_test_data(self):
        """Clear all test data from storage"""
        if self.storage:
            self.storage.clear_all_data()
            # Recreate the inventory sheet
            headers = [
                'JA_ID', 'Item_Type', 'Shape', 'Material', 'Length_mm', 'Width_mm', 
                'Height_mm', 'Diameter_mm', 'Thread_Series', 'Thread_Handedness', 
                'Thread_Length_mm', 'Location', 'Notes', 'Parent_JA_ID', 'Active'
            ]
            self.storage.create_sheet('Inventory', headers)
    
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