"""
Unit tests for TestStorage class.

Tests the SQLite in-memory storage implementation.
"""

import pytest
from app.test_storage import TestStorage
from app.storage import StorageResult


class TestTestStorage:
    """Tests for TestStorage class"""
    
    @pytest.fixture
    def storage(self):
        """Create a fresh TestStorage instance for each test"""
        storage = TestStorage()
        result = storage.connect()
        assert result.success
        yield storage
        storage.close()
    
    @pytest.mark.unit
    def test_connection(self, storage):
        """Test storage connection"""
        assert storage.connection is not None
    
    @pytest.mark.unit
    def test_create_sheet(self, storage):
        """Test sheet creation"""
        headers = ['Column1', 'Column2', 'Column3']
        result = storage.create_sheet('TestSheet', headers)
        
        assert result.success
        assert 'TestSheet' in storage.sheets
        assert storage.sheets['TestSheet'] == headers
    
    @pytest.mark.unit
    def test_write_single_row(self, storage):
        """Test writing a single row"""
        headers = ['Name', 'Age', 'City']
        storage.create_sheet('People', headers)
        
        data = ['John', '30', 'New York']
        result = storage.write_row('People', data)
        
        assert result.success
        assert result.affected_rows == 1
    
    @pytest.mark.unit
    def test_write_multiple_rows(self, storage):
        """Test writing multiple rows"""
        headers = ['Name', 'Age', 'City']
        storage.create_sheet('People', headers)
        
        data = [
            ['John', '30', 'New York'],
            ['Jane', '25', 'Boston'],
            ['Bob', '35', 'Chicago']
        ]
        result = storage.write_rows('People', data)
        
        assert result.success
        assert result.affected_rows == 3
    
    @pytest.mark.unit
    def test_read_all_data(self, storage):
        """Test reading all data from sheet"""
        headers = ['Name', 'Age', 'City']
        storage.create_sheet('People', headers)
        
        data = [
            ['John', '30', 'New York'],
            ['Jane', '25', 'Boston']
        ]
        storage.write_rows('People', data)
        
        result = storage.read_all('People')
        
        assert result.success
        assert len(result.data) == 2
        assert result.data[0] == ['John', '30', 'New York']
        assert result.data[1] == ['Jane', '25', 'Boston']
    
    @pytest.mark.unit
    def test_update_row(self, storage):
        """Test updating a row"""
        headers = ['Name', 'Age', 'City']
        storage.create_sheet('People', headers)
        
        # Write initial data
        storage.write_row('People', ['John', '30', 'New York'])
        
        # Update the row (row_index 1 is the first data row)
        result = storage.update_row('People', 1, ['John', '31', 'New York'])
        
        assert result.success
        assert result.affected_rows == 1
        
        # Verify the update
        read_result = storage.read_all('People')
        assert read_result.data[0][1] == '31'  # Age should be updated
    
    @pytest.mark.unit
    def test_delete_row(self, storage):
        """Test deleting a row"""
        headers = ['Name', 'Age', 'City']
        storage.create_sheet('People', headers)
        
        # Write initial data
        storage.write_rows('People', [
            ['John', '30', 'New York'],
            ['Jane', '25', 'Boston']
        ])
        
        # Delete first row
        result = storage.delete_row('People', 1)
        
        assert result.success
        assert result.affected_rows == 1
        
        # Verify deletion
        read_result = storage.read_all('People')
        assert len(read_result.data) == 1
        assert read_result.data[0][0] == 'Jane'
    
    @pytest.mark.unit
    def test_search_with_filters(self, storage):
        """Test searching with filters"""
        headers = ['Name', 'Age', 'City']
        storage.create_sheet('People', headers)
        
        data = [
            ['John', '30', 'New York'],
            ['Jane', '25', 'Boston'],
            ['Bob', '30', 'Chicago']
        ]
        storage.write_rows('People', data)
        
        # Search by age
        result = storage.search('People', {'Age': '30'})
        
        assert result.success
        assert len(result.data) == 2
        # Should return John and Bob (both age 30)
        names = [row[0] for row in result.data]
        assert 'John' in names
        assert 'Bob' in names
        assert 'Jane' not in names
    
    @pytest.mark.unit
    def test_get_sheet_info(self, storage):
        """Test getting sheet information"""
        headers = ['Name', 'Age', 'City']
        storage.create_sheet('People', headers)
        
        # Add some data
        storage.write_rows('People', [
            ['John', '30', 'New York'],
            ['Jane', '25', 'Boston']
        ])
        
        result = storage.get_sheet_info('People')
        
        assert result.success
        assert result.data['row_count'] == 2
        assert result.data['column_count'] == 3
        assert result.data['headers'] == headers
    
    @pytest.mark.unit
    def test_backup_sheet(self, storage):
        """Test creating a sheet backup"""
        headers = ['Name', 'Age']
        storage.create_sheet('Original', headers)
        storage.write_row('Original', ['John', '30'])
        
        result = storage.backup_sheet('Original', 'Backup')
        
        assert result.success
        
        # Verify backup exists and has same data
        read_result = storage.read_all('Backup')
        assert read_result.success
        assert len(read_result.data) == 1
        assert read_result.data[0] == ['John', '30']
    
    @pytest.mark.unit
    def test_rename_sheet(self, storage):
        """Test renaming a sheet"""
        headers = ['Name', 'Age']
        storage.create_sheet('OldName', headers)
        storage.write_row('OldName', ['John', '30'])
        
        result = storage.rename_sheet('OldName', 'NewName')
        
        assert result.success
        
        # Verify old sheet is gone and new sheet exists
        assert 'NewName' in storage.sheets
        assert 'OldName' not in storage.sheets
        
        # Verify data is preserved
        read_result = storage.read_all('NewName')
        assert read_result.success
        assert read_result.data[0] == ['John', '30']
    
    @pytest.mark.unit
    def test_write_row_with_padding(self, storage):
        """Test writing row with fewer values than headers (should pad with None)"""
        headers = ['Name', 'Age', 'City', 'Country']
        storage.create_sheet('People', headers)
        
        # Write row with only 2 values for 4 headers
        result = storage.write_row('People', ['John', '30'])
        
        assert result.success
        
        # Read back and verify padding
        read_result = storage.read_all('People')
        assert len(read_result.data[0]) == 4
        assert read_result.data[0] == ['John', '30', None, None]
    
    @pytest.mark.unit
    def test_write_row_too_many_values(self, storage):
        """Test writing row with more values than headers (should fail)"""
        headers = ['Name', 'Age']
        storage.create_sheet('People', headers)
        
        # Try to write row with 3 values for 2 headers
        result = storage.write_row('People', ['John', '30', 'ExtraValue'])
        
        assert not result.success
        assert 'exceeds headers' in result.error
    
    @pytest.mark.unit
    def test_clear_all_data(self, storage):
        """Test clearing all data"""
        # Create multiple sheets with data
        storage.create_sheet('Sheet1', ['A', 'B'])
        storage.create_sheet('Sheet2', ['X', 'Y'])
        storage.write_row('Sheet1', ['data1', 'data2'])
        storage.write_row('Sheet2', ['dataX', 'dataY'])
        
        # Clear all data
        storage.clear_all_data()
        
        # Verify sheets are cleared
        assert len(storage.sheets) == 0
        
        # Verify tables are dropped (reading should fail)
        result1 = storage.read_all('Sheet1')
        result2 = storage.read_all('Sheet2')
        
        assert not result1.success
        assert not result2.success
    
    @pytest.mark.unit
    def test_sanitize_sheet_name(self, storage):
        """Test sheet name sanitization"""
        # Test various problematic sheet names
        assert storage._sanitize_sheet_name('Normal Name') == 'normal_name'
        assert storage._sanitize_sheet_name('With-Dashes') == 'with_dashes'
        assert storage._sanitize_sheet_name('Special!@#$%Chars') == 'special_____chars'
        assert storage._sanitize_sheet_name('Numbers123') == 'numbers123'
    
    @pytest.mark.unit
    def test_error_handling_nonexistent_sheet(self, storage):
        """Test error handling for operations on non-existent sheet"""
        result = storage.read_all('NonExistentSheet')
        assert not result.success
        assert 'no such table' in result.error.lower()
    
    @pytest.mark.unit
    def test_connection_error_handling(self):
        """Test error handling for connection issues"""
        # Try to create storage with invalid path
        storage = TestStorage('/invalid/path/database.db')
        result = storage.connect()
        
        # Should fail to connect to invalid path
        assert not result.success