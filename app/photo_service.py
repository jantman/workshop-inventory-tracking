"""
Photo Service for Workshop Inventory Tracking

Handles photo upload, processing, storage, and retrieval for inventory items.
Supports JPEG, PNG, WebP, and PDF formats with automatic image compression.
"""

import io
import logging
from typing import List, Optional, Dict, Any, Tuple
from PIL import Image, ImageOps
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, and_
from datetime import datetime

from .database import Photo, ItemPhotoAssociation, InventoryItem
from config import Config

logger = logging.getLogger(__name__)

# PDF processing support - disabled on Python 3.13+ due to SWIG compatibility issues
import sys
if sys.version_info >= (3, 13):
    PDF_SUPPORT = False
    logger.warning("PyMuPDF disabled on Python 3.13+ - PDF thumbnail generation will use fallback")
else:
    try:
        import fitz  # PyMuPDF
        PDF_SUPPORT = True
    except ImportError:
        PDF_SUPPORT = False
        logger.warning("PyMuPDF not available - PDF thumbnail generation will use fallback")

class PhotoService:
    """Service for managing inventory item photos
    
    Supports context manager usage for proper resource cleanup:
        with PhotoService() as photo_service:
            photo_service.upload_photo(...)
    
    Or use explicit cleanup:
        photo_service = PhotoService()
        try:
            photo_service.upload_photo(...)
        finally:
            photo_service.close()
    """
    
    # Supported MIME types
    SUPPORTED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
    SUPPORTED_TYPES = SUPPORTED_IMAGE_TYPES | {'application/pdf'}
    
    # Image processing settings
    THUMBNAIL_SIZE = (150, 150)
    MEDIUM_SIZE = (800, 800)
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
    MAX_PHOTOS_PER_ITEM = 10
    
    def __init__(self, storage_backend=None):
        """Initialize photo service with database connection"""
        if storage_backend and hasattr(storage_backend, 'engine'):
            # Ensure the storage backend is connected
            if not storage_backend._connected:
                storage_backend.connect()
            self.engine = storage_backend.engine
        else:
            # Create MariaDB connection using the same config as the app
            self.engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
        
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
    
    def upload_photo(self, ja_id: str, file_data: bytes, filename: str, content_type: str) -> ItemPhoto:
        """
        Upload and process a photo for an inventory item
        
        Args:
            ja_id: JA ID of the inventory item
            file_data: Raw file data
            filename: Original filename
            content_type: MIME type of the file
            
        Returns:
            ItemPhoto: Created photo record
            
        Raises:
            ValueError: If validation fails
            RuntimeError: If processing fails
        """
        # Validate inputs
        self._validate_upload(ja_id, file_data, filename, content_type)
        
        # Check photo count limit
        existing_count = self.get_photo_count(ja_id)
        if existing_count >= self.MAX_PHOTOS_PER_ITEM:
            raise ValueError(f"Maximum {self.MAX_PHOTOS_PER_ITEM} photos allowed per item")
        
        # Verify item exists
        if not self._item_exists(ja_id):
            raise ValueError(f"Item with JA ID {ja_id} not found")
        
        try:
            # Process the photo
            thumbnail_data, medium_data, original_data = self._process_photo(file_data, content_type)
            
            # Create photo record
            photo = ItemPhoto(
                ja_id=ja_id,
                filename=filename,
                content_type=content_type,
                file_size=len(file_data),
                thumbnail_data=thumbnail_data,
                medium_data=medium_data,
                original_data=original_data,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            self.session.add(photo)
            self.session.commit()
            
            logger.info(f"Photo uploaded for item {ja_id}: {filename} ({len(file_data)} bytes)")
            return photo
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to upload photo for {ja_id}: {str(e)}")
            raise RuntimeError(f"Photo upload failed: {str(e)}")
    
    def get_photos(self, ja_id: str) -> List[ItemPhoto]:
        """Get all photos for an inventory item"""
        try:
            photos = self.session.query(ItemPhoto).filter(
                ItemPhoto.ja_id == ja_id
            ).order_by(ItemPhoto.created_at.asc()).all()
            
            return photos
            
        except Exception as e:
            logger.error(f"Failed to get photos for {ja_id}: {str(e)}")
            raise RuntimeError(f"Failed to retrieve photos: {str(e)}")
    
    def get_photo(self, photo_id: int) -> Optional[ItemPhoto]:
        """Get a specific photo by ID"""
        try:
            return self.session.query(ItemPhoto).filter(
                ItemPhoto.id == photo_id
            ).first()
            
        except Exception as e:
            logger.error(f"Failed to get photo {photo_id}: {str(e)}")
            raise RuntimeError(f"Failed to retrieve photo: {str(e)}")
    
    def get_photo_data(self, photo_id: int, size: str = 'original') -> Optional[Tuple[bytes, str]]:
        """
        Get photo data in specified size
        
        Args:
            photo_id: Photo ID
            size: 'thumbnail', 'medium', or 'original'
            
        Returns:
            Tuple of (data, content_type) or None if not found
        """
        photo = self.get_photo(photo_id)
        if not photo:
            return None
        
        if size == 'thumbnail':
            # For PDF thumbnails, return as JPEG since we converted them
            content_type = 'image/jpeg' if photo.content_type == 'application/pdf' else photo.content_type
            return photo.thumbnail_data, content_type
        elif size == 'medium':
            # For PDF medium size, return as JPEG since we converted them  
            content_type = 'image/jpeg' if photo.content_type == 'application/pdf' else photo.content_type
            return photo.medium_data, content_type
        else:  # original
            return photo.original_data, photo.content_type
    
    def delete_photo(self, photo_id: int) -> bool:
        """
        Delete a photo
        
        Args:
            photo_id: Photo ID to delete
            
        Returns:
            bool: True if deleted, False if not found
        """
        try:
            photo = self.session.query(ItemPhoto).filter(
                ItemPhoto.id == photo_id
            ).first()
            
            if not photo:
                return False
            
            ja_id = photo.ja_id
            filename = photo.filename
            
            self.session.delete(photo)
            self.session.commit()
            
            logger.info(f"Photo deleted: {filename} (ID: {photo_id}) for item {ja_id}")
            return True
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to delete photo {photo_id}: {str(e)}")
            raise RuntimeError(f"Failed to delete photo: {str(e)}")
    
    def get_photo_count(self, ja_id: str) -> int:
        """Get count of photos for an item"""
        try:
            return self.session.query(ItemPhoto).filter(
                ItemPhoto.ja_id == ja_id
            ).count()
            
        except Exception as e:
            logger.error(f"Failed to get photo count for {ja_id}: {str(e)}")
            return 0
    
    def get_photo_counts_bulk(self, ja_ids: List[str]) -> Dict[str, int]:
        """Get photo counts for multiple items efficiently"""
        if not ja_ids:
            return {}
            
        try:
            from sqlalchemy import func
            
            # Use a fresh session for this query
            session = self.Session()
            try:
                # Query photo counts grouped by ja_id
                results = session.query(
                    ItemPhoto.ja_id,
                    func.count(ItemPhoto.id).label('photo_count')
                ).filter(
                    ItemPhoto.ja_id.in_(ja_ids)
                ).group_by(ItemPhoto.ja_id).all()
                
                # Create mapping with default 0 for items with no photos
                counts = {ja_id: 0 for ja_id in ja_ids}
                for ja_id, count in results:
                    counts[ja_id] = count
                
                return counts
            finally:
                session.close()
            
        except Exception as e:
            logger.error(f"Failed to get bulk photo counts: {str(e)}")
            return {ja_id: 0 for ja_id in ja_ids}
    
    def cleanup_orphaned_photos(self) -> int:
        """
        Remove photos for ja_ids that no longer exist in the inventory
        
        Returns:
            int: Number of photos cleaned up
        """
        session = self.Session()
        try:
            # Find photos whose ja_id is not in the inventory_items table
            orphaned_photos = session.query(ItemPhoto).filter(
                ~ItemPhoto.ja_id.in_(
                    session.query(InventoryItem.ja_id).distinct()
                )
            ).all()
            
            count = len(orphaned_photos)
            if count > 0:
                for photo in orphaned_photos:
                    session.delete(photo)
                session.commit()
                logger.info(f"Cleaned up {count} orphaned photos")
            
            return count
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to cleanup orphaned photos: {str(e)}")
            return 0
        finally:
            session.close()
    
    def _validate_upload(self, ja_id: str, file_data: bytes, filename: str, content_type: str):
        """Validate photo upload parameters"""
        if not ja_id or not ja_id.strip():
            raise ValueError("JA ID is required")
        
        if not file_data:
            raise ValueError("File data is required")
        
        if len(file_data) > self.MAX_FILE_SIZE:
            raise ValueError(f"File size {len(file_data)} exceeds maximum {self.MAX_FILE_SIZE} bytes")
        
        if not filename or not filename.strip():
            raise ValueError("Filename is required")
        
        if content_type not in self.SUPPORTED_TYPES:
            supported_list = ', '.join(sorted(self.SUPPORTED_TYPES))
            raise ValueError(f"Unsupported content type: {content_type}. Supported: {supported_list}")
    
    def _item_exists(self, ja_id: str) -> bool:
        """Check if an inventory item exists"""
        session = self.Session()
        try:
            return session.query(InventoryItem).filter(
                and_(InventoryItem.ja_id == ja_id, InventoryItem.active == True)
            ).first() is not None
            
        except Exception as e:
            logger.error(f"Failed to check if item exists {ja_id}: {str(e)}")
            return False
        finally:
            session.close()
    
    def _process_photo(self, file_data: bytes, content_type: str) -> Tuple[bytes, bytes, bytes]:
        """
        Process photo into three sizes: thumbnail, medium, and original
        
        Returns:
            Tuple of (thumbnail_data, medium_data, original_data)
        """
        if content_type == 'application/pdf':
            return self._process_pdf(file_data)
        
        if content_type not in self.SUPPORTED_IMAGE_TYPES:
            raise ValueError(f"Unsupported image type: {content_type}")
        
        try:
            # Open image
            with Image.open(io.BytesIO(file_data)) as img:
                # Convert to RGB if necessary (handles RGBA, CMYK, etc.)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Create white background for transparency
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = rgb_img
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Auto-orient based on EXIF data
                img = ImageOps.exif_transpose(img)
                
                # Generate thumbnail
                thumbnail = img.copy()
                thumbnail.thumbnail(self.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                thumbnail_bytes = self._image_to_bytes(thumbnail, 'JPEG', quality=85)
                
                # Generate medium size
                medium = img.copy()
                medium.thumbnail(self.MEDIUM_SIZE, Image.Resampling.LANCZOS)
                medium_bytes = self._image_to_bytes(medium, 'JPEG', quality=90)
                
                # Original data (keep as-is)
                original_bytes = file_data
                
                return thumbnail_bytes, medium_bytes, original_bytes
                
        except Exception as e:
            logger.error(f"Failed to process image: {str(e)}")
            raise RuntimeError(f"Image processing failed: {str(e)}")
    
    def _process_pdf(self, file_data: bytes) -> Tuple[bytes, bytes, bytes]:
        """
        Process PDF to generate thumbnail and medium size previews from first page
        
        Returns:
            Tuple of (thumbnail_data, medium_data, original_data)
        """
        if not PDF_SUPPORT:
            logger.warning("PDF thumbnail generation not available - using original data for all sizes")
            return file_data, file_data, file_data
        
        try:
            # Open PDF document
            pdf_doc = fitz.open(stream=file_data, filetype="pdf")
            
            if pdf_doc.page_count == 0:
                logger.warning("PDF has no pages - using original data for all sizes")
                pdf_doc.close()
                return file_data, file_data, file_data
            
            # Get first page
            page = pdf_doc[0]
            
            # Generate thumbnail (150x150 max)
            thumbnail_matrix = fitz.Matrix(1.0, 1.0)  # Start with 1:1 scale
            thumbnail_pixmap = page.get_pixmap(matrix=thumbnail_matrix)
            
            # Convert pixmap to PIL Image
            thumbnail_img_data = thumbnail_pixmap.tobytes("ppm")
            thumbnail_img = Image.open(io.BytesIO(thumbnail_img_data))
            
            # Resize to thumbnail size
            thumbnail_img.thumbnail(self.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            thumbnail_bytes = self._image_to_bytes(thumbnail_img, 'JPEG', quality=85)
            
            # Generate medium size (800x800 max)
            medium_matrix = fitz.Matrix(2.0, 2.0)  # Higher resolution for medium
            medium_pixmap = page.get_pixmap(matrix=medium_matrix)
            
            # Convert pixmap to PIL Image
            medium_img_data = medium_pixmap.tobytes("ppm")
            medium_img = Image.open(io.BytesIO(medium_img_data))
            
            # Resize to medium size
            medium_img.thumbnail(self.MEDIUM_SIZE, Image.Resampling.LANCZOS)
            medium_bytes = self._image_to_bytes(medium_img, 'JPEG', quality=90)
            
            # Clean up PyMuPDF resources
            thumbnail_pixmap = None
            medium_pixmap = None
            pdf_doc.close()
            
            logger.info("Generated PDF thumbnails successfully")
            return thumbnail_bytes, medium_bytes, file_data
            
        except Exception as e:
            logger.error(f"Failed to process PDF: {str(e)}")
            # Fallback to original data for all sizes if PDF processing fails
            return file_data, file_data, file_data
    
    def _image_to_bytes(self, img: Image.Image, format: str, **kwargs) -> bytes:
        """Convert PIL Image to bytes"""
        buffer = io.BytesIO()
        img.save(buffer, format=format, **kwargs)
        return buffer.getvalue()
    
    def close(self):
        """Explicitly close database session and dispose engine"""
        if hasattr(self, 'session') and self.session:
            self.session.close()
            self.session = None
        if hasattr(self, 'engine') and self.engine:
            self.engine.dispose()
            self.engine = None
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def regenerate_pdf_thumbnails(self) -> int:
        """
        Regenerate thumbnails for existing PDF photos that only have original PDF data
        
        Returns:
            int: Number of PDFs that were processed
        """
        if not PDF_SUPPORT:
            logger.warning("PyMuPDF not available - cannot regenerate PDF thumbnails")
            return 0
            
        try:
            # Find PDFs where thumbnail_data is still PDF data (starts with %PDF)
            pdf_photos = self.session.query(ItemPhoto).filter(
                ItemPhoto.content_type == 'application/pdf'
            ).all()
            
            updated_count = 0
            
            for photo in pdf_photos:
                # Check if thumbnail_data is still PDF data (not JPEG)
                if photo.thumbnail_data and photo.thumbnail_data.startswith(b'%PDF'):
                    try:
                        # Regenerate thumbnails using original PDF data
                        thumbnail_data, medium_data, original_data = self._process_pdf(photo.original_data)
                        
                        # Update the photo record with new thumbnail data
                        photo.thumbnail_data = thumbnail_data
                        photo.medium_data = medium_data
                        photo.updated_at = datetime.utcnow()
                        
                        updated_count += 1
                        logger.info(f"Regenerated thumbnails for PDF {photo.filename} (ID: {photo.id})")
                        
                    except Exception as e:
                        logger.error(f"Failed to regenerate thumbnails for PDF {photo.filename} (ID: {photo.id}): {str(e)}")
                        continue
            
            if updated_count > 0:
                self.session.commit()
                logger.info(f"Successfully regenerated thumbnails for {updated_count} PDF photos")
            else:
                logger.info("No PDF photos needed thumbnail regeneration")
                
            return updated_count
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to regenerate PDF thumbnails: {str(e)}")
            raise RuntimeError(f"PDF thumbnail regeneration failed: {str(e)}")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup"""
        self.close()