"""
Unit tests for Photo API endpoints.

Tests photo upload, retrieval, and deletion API endpoints.
"""

import pytest
import json
import io
from unittest.mock import Mock, patch, MagicMock
from PIL import Image

from app.database import ItemPhoto


class TestPhotoAPI:
    """Test the photo API endpoints"""
    
    @pytest.fixture
    def sample_image_data(self):
        """Generate sample JPEG image data"""
        image = Image.new('RGB', (100, 100), color='red')
        img_buffer = io.BytesIO()
        image.save(img_buffer, format='JPEG', quality=90)
        img_buffer.seek(0)
        return img_buffer.getvalue()
    
    @pytest.fixture
    def sample_pdf_data(self):
        """Generate sample PDF data"""
        return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj
xref
0 4
0000000000 65535 f 
0000000010 00000 n 
0000000053 00000 n 
0000000100 00000 n 
trailer<</Size 4/Root 1 0 R>>
startxref
149
%%EOF"""
    
    @pytest.mark.unit
    def test_upload_photo_success(self, client, sample_image_data):
        """Test POST /api/items/{id}/photos with valid image"""
        with patch('app.photo_service.PhotoService') as mock_service_class:
            # Mock PhotoService instance
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            # Mock successful upload
            mock_photo = ItemPhoto(
                id=1,
                ja_id="JA000123",
                filename="test.jpg",
                content_type="image/jpeg",
                file_size=len(sample_image_data)
            )
            mock_service.upload_photo.return_value = mock_photo
            
            # Create form data
            data = {
                'photo': (io.BytesIO(sample_image_data), 'test.jpg', 'image/jpeg')
            }
            
            response = client.post('/api/items/JA000123/photos',
                                 data=data,
                                 content_type='multipart/form-data')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['photo_id'] == 1
            assert data['filename'] == 'test.jpg'
            assert 'message' in data
            
            # Verify service was called correctly
            mock_service.upload_photo.assert_called_once()
            args = mock_service.upload_photo.call_args[1]
            assert args['ja_id'] == 'JA000123'
            assert args['filename'] == 'test.jpg'
            assert args['content_type'] == 'image/jpeg'
    
    @pytest.mark.unit
    def test_upload_photo_no_file(self, client):
        """Test POST /api/items/{id}/photos without file"""
        response = client.post('/api/items/JA000123/photos',
                             data={},
                             content_type='multipart/form-data')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'No file provided' in data['message']
    
    @pytest.mark.unit
    def test_upload_photo_empty_file(self, client):
        """Test POST /api/items/{id}/photos with empty file"""
        data = {
            'photo': (io.BytesIO(b''), 'empty.jpg', 'image/jpeg')
        }
        
        response = client.post('/api/items/JA000123/photos',
                             data=data,
                             content_type='multipart/form-data')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'No file selected' in data['message']
    
    @pytest.mark.unit
    def test_upload_photo_service_error(self, client, sample_image_data):
        """Test POST /api/items/{id}/photos when service throws error"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            # Mock service error
            mock_service.upload_photo.side_effect = ValueError("Invalid file type")
            
            data = {
                'photo': (io.BytesIO(sample_image_data), 'test.jpg', 'image/jpeg')
            }
            
            response = client.post('/api/items/JA000123/photos',
                                 data=data,
                                 content_type='multipart/form-data')
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'Invalid file type' in data['message']
    
    @pytest.mark.unit
    def test_get_photos_for_item_success(self, client):
        """Test GET /api/items/{id}/photos with existing photos"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            # Mock photos
            mock_photos = [
                ItemPhoto(id=1, ja_id="JA000123", filename="photo1.jpg", 
                         content_type="image/jpeg", file_size=1000),
                ItemPhoto(id=2, ja_id="JA000123", filename="photo2.png", 
                         content_type="image/png", file_size=2000)
            ]
            mock_service.get_photos_for_item.return_value = mock_photos
            
            response = client.get('/api/items/JA000123/photos')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert len(data['photos']) == 2
            assert data['photos'][0]['id'] == 1
            assert data['photos'][0]['filename'] == 'photo1.jpg'
            assert data['photos'][1]['id'] == 2
            assert data['photos'][1]['filename'] == 'photo2.png'
            
            mock_service.get_photos_for_item.assert_called_once_with('JA000123')
    
    @pytest.mark.unit
    def test_get_photos_for_item_empty(self, client):
        """Test GET /api/items/{id}/photos with no photos"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            mock_service.get_photos_for_item.return_value = []
            
            response = client.get('/api/items/JA000123/photos')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert len(data['photos']) == 0
    
    @pytest.mark.unit
    def test_get_photo_data_thumbnail(self, client, sample_image_data):
        """Test GET /api/photos/{id}?size=thumbnail"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            # Mock photo and data retrieval
            mock_photo = ItemPhoto(
                id=1, ja_id="JA000123", filename="test.jpg",
                content_type="image/jpeg", file_size=1000
            )
            mock_service.get_photo_by_id.return_value = mock_photo
            mock_service.get_photo_data.return_value = sample_image_data
            
            response = client.get('/api/photos/1?size=thumbnail')
            
            assert response.status_code == 200
            assert response.content_type == 'image/jpeg'
            assert response.data == sample_image_data
            assert 'Cache-Control' in response.headers
            
            mock_service.get_photo_by_id.assert_called_once_with(1)
            mock_service.get_photo_data.assert_called_once_with(1, 'thumbnail')
    
    @pytest.mark.unit
    def test_get_photo_data_not_found(self, client):
        """Test GET /api/photos/{id} for non-existent photo"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            mock_service.get_photo_by_id.return_value = None
            
            response = client.get('/api/photos/999?size=thumbnail')
            
            assert response.status_code == 404
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'Photo not found' in data['message']
    
    @pytest.mark.unit
    def test_get_photo_data_invalid_size(self, client):
        """Test GET /api/photos/{id} with invalid size parameter"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            mock_photo = ItemPhoto(id=1, filename="test.jpg")
            mock_service.get_photo_by_id.return_value = mock_photo
            mock_service.get_photo_data.side_effect = ValueError("Invalid size")
            
            response = client.get('/api/photos/1?size=invalid')
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'Invalid size' in data['message']
    
    @pytest.mark.unit
    def test_download_photo_success(self, client, sample_image_data):
        """Test GET /api/photos/{id}/download"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            # Mock photo and data retrieval
            mock_photo = ItemPhoto(
                id=1, ja_id="JA000123", filename="test.jpg",
                content_type="image/jpeg", file_size=1000
            )
            mock_service.get_photo_by_id.return_value = mock_photo
            mock_service.get_photo_data.return_value = sample_image_data
            
            response = client.get('/api/photos/1/download')
            
            assert response.status_code == 200
            assert response.content_type == 'image/jpeg'
            assert response.data == sample_image_data
            assert 'attachment; filename=test.jpg' in response.headers['Content-Disposition']
            
            mock_service.get_photo_data.assert_called_once_with(1, 'original')
    
    @pytest.mark.unit
    def test_download_photo_not_found(self, client):
        """Test GET /api/photos/{id}/download for non-existent photo"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            mock_service.get_photo_by_id.return_value = None
            
            response = client.get('/api/photos/999/download')
            
            assert response.status_code == 404
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'Photo not found' in data['message']
    
    @pytest.mark.unit
    def test_delete_photo_success(self, client):
        """Test DELETE /api/photos/{id}"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            mock_service.delete_photo.return_value = True
            
            response = client.delete('/api/photos/1')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'deleted successfully' in data['message']
            
            mock_service.delete_photo.assert_called_once_with(1)
    
    @pytest.mark.unit
    def test_delete_photo_not_found(self, client):
        """Test DELETE /api/photos/{id} for non-existent photo"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            mock_service.delete_photo.return_value = False
            
            response = client.delete('/api/photos/999')
            
            assert response.status_code == 404
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'Photo not found' in data['message']
    
    @pytest.mark.unit
    def test_cleanup_orphaned_photos_success(self, client):
        """Test POST /api/admin/photos/cleanup"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            mock_service.cleanup_orphaned_photos.return_value = 5
            
            response = client.post('/api/admin/photos/cleanup')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['deleted_count'] == 5
            assert 'cleanup completed' in data['message']
            
            mock_service.cleanup_orphaned_photos.assert_called_once()
    
    @pytest.mark.unit
    def test_cleanup_orphaned_photos_error(self, client):
        """Test POST /api/admin/photos/cleanup with service error"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            mock_service.cleanup_orphaned_photos.side_effect = Exception("Database error")
            
            response = client.post('/api/admin/photos/cleanup')
            
            assert response.status_code == 500
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'Database error' in data['message']
    
    @pytest.mark.unit
    def test_photo_api_invalid_ja_id_format(self, client, sample_image_data):
        """Test photo APIs with invalid JA ID format"""
        data = {
            'photo': (io.BytesIO(sample_image_data), 'test.jpg', 'image/jpeg')
        }
        
        response = client.post('/api/items/INVALID_ID/photos',
                             data=data,
                             content_type='multipart/form-data')
        
        # Should validate JA ID format at route level
        assert response.status_code == 400
    
    @pytest.mark.unit
    def test_photo_api_with_pdf(self, client, sample_pdf_data):
        """Test photo upload with PDF file"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            mock_photo = ItemPhoto(
                id=1,
                ja_id="JA000123",
                filename="document.pdf",
                content_type="application/pdf",
                file_size=len(sample_pdf_data)
            )
            mock_service.upload_photo.return_value = mock_photo
            
            data = {
                'photo': (io.BytesIO(sample_pdf_data), 'document.pdf', 'application/pdf')
            }
            
            response = client.post('/api/items/JA000123/photos',
                                 data=data,
                                 content_type='multipart/form-data')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['filename'] == 'document.pdf'
    
    @pytest.mark.unit
    def test_get_photo_data_all_sizes(self, client, sample_image_data):
        """Test GET /api/photos/{id} with all valid size parameters"""
        sizes = ['thumbnail', 'medium', 'original']
        
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            mock_photo = ItemPhoto(
                id=1, filename="test.jpg", content_type="image/jpeg"
            )
            mock_service.get_photo_by_id.return_value = mock_photo
            mock_service.get_photo_data.return_value = sample_image_data
            
            for size in sizes:
                response = client.get(f'/api/photos/1?size={size}')
                
                assert response.status_code == 200
                assert response.content_type == 'image/jpeg'
                assert response.data == sample_image_data
                
                mock_service.get_photo_data.assert_called_with(1, size)
    
    @pytest.mark.unit
    def test_photo_api_error_handling(self, client, sample_image_data):
        """Test photo API error handling for various service exceptions"""
        with patch('app.main.routes.PhotoService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            # Test different service errors
            error_cases = [
                (ValueError("File too large"), 400),
                (RuntimeError("Processing failed"), 500),
                (Exception("Unexpected error"), 500)
            ]
            
            for error, expected_status in error_cases:
                mock_service.upload_photo.side_effect = error
                
                data = {
                    'photo': (io.BytesIO(sample_image_data), 'test.jpg', 'image/jpeg')
                }
                
                response = client.post('/api/items/JA000123/photos',
                                     data=data,
                                     content_type='multipart/form-data')
                
                assert response.status_code == expected_status
                data = json.loads(response.data)
                assert data['success'] is False
                assert 'message' in data