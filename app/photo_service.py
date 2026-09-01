"""
Photo Service for Workshop Inventory Tracking

Handles photo upload, processing, storage, and retrieval for inventory items.
Supports JPEG, PNG, WebP, and PDF formats with automatic image compression.
"""

import hashlib
import io
import logging
from typing import List, Optional, Dict, Any, Tuple
from PIL import Image, ImageOps
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, and_
from datetime import datetime

from .database import Photo, ItemPhotoAssociation, InventoryItem, Product, ProductAttachment, Purchase
from config import Config

logger = logging.getLogger(__name__)

# PDF processing support
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
    # A separate cap from MAX_PHOTOS_PER_ITEM rather than a reuse of it: a
    # product accumulates datasheets and wiring diagrams over years, an
    # inventory item accumulates photographs of one physical thing, and the
    # two limits should be able to move without surprising each other.
    # FR-012: raised from 25 because one listing capture can contribute more
    # than a dozen gallery images on its own.
    MAX_ATTACHMENTS_PER_PRODUCT = 100
    
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
    
    def upload_photo(self, ja_id: str, file_data: bytes, filename: str, content_type: str) -> ItemPhotoAssociation:
        """
        Upload and process a photo for an inventory item

        Args:
            ja_id: JA ID of the inventory item
            file_data: Raw file data
            filename: Original filename
            content_type: MIME type of the file

        Returns:
            ItemPhotoAssociation: Created association record (with photo relationship)

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

            # Create photo record (stores BLOB data once)
            photo = Photo(
                filename=filename,
                content_type=content_type,
                file_size=len(file_data),
                thumbnail_data=thumbnail_data,
                medium_data=medium_data,
                original_data=original_data,
                sha256_hash=None,  # Optional: can add hash calculation later
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            self.session.add(photo)
            self.session.flush()  # Get photo.id

            # Calculate display_order (position in this item's photo list)
            display_order = self.get_photo_count(ja_id)

            # Create association linking item to photo
            association = ItemPhotoAssociation(
                ja_id=ja_id,
                photo_id=photo.id,
                display_order=display_order,
                created_at=datetime.utcnow()
            )

            self.session.add(association)
            self.session.commit()

            # Refresh to load the photo relationship
            self.session.refresh(association)

            logger.info(f"Photo uploaded for item {ja_id}: {filename} ({len(file_data)} bytes)")
            return association

        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to upload photo for {ja_id}: {str(e)}")
            raise RuntimeError(f"Photo upload failed: {str(e)}")
    
    def get_photos(self, ja_id: str) -> List[ItemPhotoAssociation]:
        """Get all photo associations for an inventory item (includes photo data via relationship)"""
        try:
            associations = self.session.query(ItemPhotoAssociation).filter(
                ItemPhotoAssociation.ja_id == ja_id
            ).order_by(ItemPhotoAssociation.display_order.asc()).all()

            return associations

        except Exception as e:
            logger.error(f"Failed to get photos for {ja_id}: {str(e)}")
            raise RuntimeError(f"Failed to retrieve photos: {str(e)}")
    
    def get_photo(self, photo_id: int) -> Optional[ItemPhotoAssociation]:
        """Get a specific photo association by ID (association ID, not photo ID)"""
        try:
            return self.session.query(ItemPhotoAssociation).filter(
                ItemPhotoAssociation.id == photo_id
            ).first()

        except Exception as e:
            logger.error(f"Failed to get photo association {photo_id}: {str(e)}")
            raise RuntimeError(f"Failed to retrieve photo: {str(e)}")
    
    def get_photo_data(self, photo_id: int, size: str = 'original') -> Optional[Tuple[bytes, str]]:
        """
        Get photo data in specified size

        Args:
            photo_id: Photo ID (photos.id) - NOT association ID
            size: 'thumbnail', 'medium', or 'original'

        Returns:
            Tuple of (data, content_type) or None if not found
        """
        # Query by Photo.id directly (not association ID)
        try:
            photo = self.session.query(Photo).filter(Photo.id == photo_id).first()
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
        except Exception as e:
            logger.error(f"Failed to get photo data for photo ID {photo_id}: {str(e)}")
            raise RuntimeError(f"Failed to retrieve photo data: {str(e)}")

    def get_photo_file(self, photo_id: int) -> Optional[Tuple[bytes, str, str]]:
        """
        Get the original file for download

        Everything a download needs off one row, so the caller resolves the id
        once. Returns plain values rather than the Photo, because the route
        reads them after the session has closed.

        Args:
            photo_id: Photo ID (photos.id) - NOT association ID

        Returns:
            Tuple of (original_data, content_type, filename), or None if there
            is no such photo
        """
        try:
            photo = self.session.query(Photo).filter(Photo.id == photo_id).first()
            if not photo:
                return None

            return photo.original_data, photo.content_type, photo.filename
        except Exception as e:
            logger.error(f"Failed to get photo file for photo ID {photo_id}: {str(e)}")
            raise RuntimeError(f"Failed to retrieve photo file: {str(e)}")

    def delete_photo(self, photo_id: int) -> bool:
        """
        Delete a photo association and the photo itself if no other associations exist

        Args:
            photo_id: Association ID to delete (item_photo_associations.id)

        Returns:
            bool: True if deleted, False if not found
        """
        try:
            association = self.get_photo(photo_id)
            if not association:
                return False

            photo = association.photo
            ja_id = association.ja_id
            filename = photo.filename if photo else "unknown"

            # Delete the association
            self.session.delete(association)
            self.session.flush()

            # Check if this photo has any other associations
            if photo:
                remaining_associations = self.session.query(ItemPhotoAssociation).filter(
                    ItemPhotoAssociation.photo_id == photo.id
                ).count()

                # If no other associations exist, delete the photo data
                if remaining_associations == 0:
                    logger.info(f"No other associations for photo {photo.id}, deleting photo data")
                    self.session.delete(photo)

            self.session.commit()

            logger.info(f"Photo association deleted: {filename} (ID: {photo_id}) for item {ja_id}")
            return True

        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to delete photo association {photo_id}: {str(e)}")
            raise RuntimeError(f"Failed to delete photo: {str(e)}")
    
    def get_photo_count(self, ja_id: str) -> int:
        """Get count of photo associations for an item"""
        try:
            return self.session.query(ItemPhotoAssociation).filter(
                ItemPhotoAssociation.ja_id == ja_id
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
                    ItemPhotoAssociation.ja_id,
                    func.count(ItemPhotoAssociation.id).label('photo_count')
                ).filter(
                    ItemPhotoAssociation.ja_id.in_(ja_ids)
                ).group_by(ItemPhotoAssociation.ja_id).all()

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
        Clean up photos and associations for items that no longer exist,
        and photos that have no associations

        Returns:
            int: Number of items cleaned up (associations + photos)
        """
        session = self.Session()
        try:
            from sqlalchemy import exists

            # Step 1: Find and delete associations for JA IDs that don't exist in inventory_items
            orphaned_associations = session.query(ItemPhotoAssociation).filter(
                ~ItemPhotoAssociation.ja_id.in_(
                    session.query(InventoryItem.ja_id).distinct()
                )
            ).all()

            assoc_count = len(orphaned_associations)
            if assoc_count > 0:
                logger.info(f"Found {assoc_count} orphaned photo associations to clean up")
                for assoc in orphaned_associations:
                    session.delete(assoc)
                session.flush()

            # Step 2: Find and delete photos that nothing references.
            #
            # Both tables have to be checked. Product and purchase attachments
            # reference photos through product_attachments and never create an
            # ItemPhotoAssociation, so a filter that only knows about the latter
            # treats every attachment as orphaned the moment it is uploaded --
            # and product_attachments.photo_id is ON DELETE CASCADE, so the sweep
            # would take the attachment rows with it. delete_attachment() already
            # checks both; so must this.
            orphaned_photos = session.query(Photo).filter(
                ~exists().where(ItemPhotoAssociation.photo_id == Photo.id),
                ~exists().where(ProductAttachment.photo_id == Photo.id),
            ).all()

            photo_count = len(orphaned_photos)
            if photo_count > 0:
                logger.info(f"Found {photo_count} orphaned photos (no associations) to clean up")
                for photo in orphaned_photos:
                    session.delete(photo)

            session.commit()

            total_cleaned = assoc_count + photo_count
            if total_cleaned > 0:
                logger.info(f"Cleaned up {assoc_count} associations and {photo_count} photos")

            return total_cleaned

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to cleanup orphaned photos: {str(e)}")
            return 0
        finally:
            session.close()

    def copy_photos(self, source_ja_id: str, target_ja_id: str) -> int:
        """
        Copy all photos from source item to target item by creating new associations

        This creates new ItemPhotoAssociation records that reference the same Photo records,
        so no BLOB data is duplicated - only association metadata.

        Args:
            source_ja_id: JA ID of source item (to copy photos from)
            target_ja_id: JA ID of target item (to copy photos to)

        Returns:
            int: Number of photo associations created

        Raises:
            ValueError: If source or target item doesn't exist
            RuntimeError: If copy operation fails
        """
        try:
            # Verify both items exist
            if not self._item_exists(source_ja_id):
                raise ValueError(f"Source item {source_ja_id} not found")

            if not self._item_exists(target_ja_id):
                raise ValueError(f"Target item {target_ja_id} not found")

            # Get all photo associations for source item
            source_associations = self.session.query(ItemPhotoAssociation).filter(
                ItemPhotoAssociation.ja_id == source_ja_id
            ).order_by(ItemPhotoAssociation.display_order.asc()).all()

            if not source_associations:
                logger.info(f"No photos to copy from {source_ja_id} to {target_ja_id}")
                return 0

            # Calculate starting display_order for target item (append to existing photos)
            target_photo_count = self.get_photo_count(target_ja_id)

            # Create new associations for target item
            created_count = 0
            for idx, source_assoc in enumerate(source_associations):
                new_association = ItemPhotoAssociation(
                    ja_id=target_ja_id,
                    photo_id=source_assoc.photo_id,  # Reference same photo (no BLOB duplication!)
                    display_order=target_photo_count + idx,
                    created_at=datetime.utcnow()
                )
                self.session.add(new_association)
                created_count += 1

            self.session.commit()

            logger.info(f"Copied {created_count} photos from {source_ja_id} to {target_ja_id} (no BLOB duplication)")
            return created_count

        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to copy photos from {source_ja_id} to {target_ja_id}: {str(e)}")
            raise RuntimeError(f"Failed to copy photos: {str(e)}")

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
    
    # -----------------------------------------------------------------
    # Product catalog attachments (FR-034)
    #
    # Datasheets, wiring diagrams, saved listings and photographs, stored the
    # same way item photos already are. Datasheets are PDFs, and PDFs already
    # work here -- building a second blob store beside a working one would be
    # the opposite of simple.
    # -----------------------------------------------------------------

    def upload_product_attachment(
        self, product_id: int, file_data: bytes, filename: str, content_type: str
    ) -> ProductAttachment:
        """Attach a file to a product.

        Args:
            product_id: The product it belongs to.
            file_data: Raw file bytes.
            filename: Original filename.
            content_type: MIME type; must be in SUPPORTED_TYPES.

        Returns:
            The created ProductAttachment.

        Raises:
            ValueError: If validation fails or the product does not exist.
            RuntimeError: If processing fails.
        """
        return self._upload_attachment(
            file_data, filename, content_type,
            owner_column='product_id', owner_id=product_id,
            owner_model=Product, owner_name='Product',
        )

    def upload_product_attachment_if_new(
        self, product_id: int, file_data: bytes, filename: str, content_type: str
    ) -> Optional[ProductAttachment]:
        """Attach unless this product already holds these exact bytes (FR-018).

        Judged by content, never by address. A vendor serves the same source
        file under several transform tokens, so two addresses routinely name
        identical bytes -- an address-keyed check would store the same picture
        twice and believe it had deduped. It also means the within-a-capture and
        across-captures halves of FR-018 need one mechanism, because by the time
        the second copy is considered the first is already stored.

        Scoped to this product. A different product holding the same bytes gets
        its own row pointing at its own Photo; cross-product blob sharing is a
        storage optimization nothing has asked for.

        Args:
            product_id: The product it belongs to.
            file_data: Raw file bytes.
            filename: Original filename.
            content_type: MIME type; must be in SUPPORTED_TYPES.

        Returns:
            The created ProductAttachment, or None when the content is already
            on this product.

        Raises:
            ValueError: For the cap, a refused type or size, or a missing
                product -- the same contract upload_product_attachment has,
                because it is the same method underneath.
        """
        digest = hashlib.sha256(file_data).hexdigest()

        existing = self.session.query(ProductAttachment).join(
            Photo, ProductAttachment.photo_id == Photo.id
        ).filter(
            ProductAttachment.product_id == product_id,
            Photo.sha256_hash == digest,
        ).first()
        if existing is not None:
            logger.info(
                f"Product {product_id} already holds these bytes ({digest[:12]}); "
                f"not attaching {filename} a second time"
            )
            return None

        # Delegated rather than reimplemented, so validation, processing, the
        # cap and the error contract cannot drift apart from the ordinary path.
        return self.upload_product_attachment(
            product_id, file_data, filename, content_type
        )

    def upload_purchase_attachment(
        self, purchase_id: int, file_data: bytes, filename: str, content_type: str
    ) -> ProductAttachment:
        """Attach a file to a purchase.

        A datasheet belongs to the product; a saved listing belongs to the
        purchase that captured it, which is why both owners exist.

        Args:
            purchase_id: The purchase it belongs to.
            file_data: Raw file bytes.
            filename: Original filename.
            content_type: MIME type; must be in SUPPORTED_TYPES.

        Returns:
            The created ProductAttachment.

        Raises:
            ValueError: If validation fails or the purchase does not exist.
            RuntimeError: If processing fails.
        """
        return self._upload_attachment(
            file_data, filename, content_type,
            owner_column='purchase_id', owner_id=purchase_id,
            owner_model=Purchase, owner_name='Purchase',
        )

    def _upload_attachment(
        self, file_data, filename, content_type, owner_column, owner_id,
        owner_model, owner_name,
    ) -> ProductAttachment:
        """Store the bytes once and link them to exactly one owner."""
        self._validate_attachment_upload(file_data, filename, content_type)

        if self.session.query(owner_model).filter(owner_model.id == owner_id).first() is None:
            raise ValueError(f"{owner_name} {owner_id} not found")

        existing = self.session.query(ProductAttachment).filter(
            getattr(ProductAttachment, owner_column) == owner_id
        ).count()
        if existing >= self.MAX_ATTACHMENTS_PER_PRODUCT:
            raise ValueError(
                f"Maximum {self.MAX_ATTACHMENTS_PER_PRODUCT} attachments allowed"
            )

        try:
            thumbnail_data, medium_data, original_data = self._process_photo(
                file_data, content_type
            )

            photo = Photo(
                filename=filename,
                content_type=content_type,
                file_size=len(file_data),
                thumbnail_data=thumbnail_data,
                medium_data=medium_data,
                original_data=original_data,
                # Over the bytes as received, which is exactly what
                # _process_photo returns unchanged as original_data. Hashing a
                # Pillow output instead would not be stable across Pillow
                # versions, and a dedupe key that moves under you is worse than
                # none. Closes the note this column has carried since
                # 8213852b0b94: "will be populated on future uploads".
                sha256_hash=hashlib.sha256(file_data).hexdigest(),
            )
            self.session.add(photo)
            self.session.flush()

            attachment = ProductAttachment(
                photo_id=photo.id,
                display_order=existing,
                **{owner_column: owner_id}
            )
            self.session.add(attachment)
            self.session.commit()
            self.session.refresh(attachment)

            logger.info(
                f"Attachment uploaded for {owner_name.lower()} {owner_id}: "
                f"{filename} ({len(file_data)} bytes)"
            )
            return attachment

        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to attach {filename} to {owner_name.lower()} {owner_id}: {e}")
            raise RuntimeError(f"Attachment upload failed: {str(e)}")

    def get_product_attachments(self, product_id: int) -> List[ProductAttachment]:
        """Every attachment on a product, in display order."""
        return self.session.query(ProductAttachment).filter(
            ProductAttachment.product_id == product_id
        ).order_by(ProductAttachment.display_order).all()

    def get_purchase_attachments(self, purchase_id: int) -> List[ProductAttachment]:
        """Every attachment on a purchase, in display order."""
        return self.session.query(ProductAttachment).filter(
            ProductAttachment.purchase_id == purchase_id
        ).order_by(ProductAttachment.display_order).all()

    def delete_attachment(self, attachment_id: int) -> bool:
        """Remove an attachment and the bytes it referenced.

        Args:
            attachment_id: The attachment row.

        Returns:
            True when a row was removed, False when there was nothing to remove.
        """
        attachment = self.session.query(ProductAttachment).filter(
            ProductAttachment.id == attachment_id
        ).first()
        if attachment is None:
            return False

        photo_id = attachment.photo_id
        try:
            self.session.delete(attachment)
            self.session.flush()

            still_referenced = self.session.query(ProductAttachment).filter(
                ProductAttachment.photo_id == photo_id
            ).count() or self.session.query(ItemPhotoAssociation).filter(
                ItemPhotoAssociation.photo_id == photo_id
            ).count()

            if not still_referenced:
                photo = self.session.query(Photo).filter(Photo.id == photo_id).first()
                if photo is not None:
                    self.session.delete(photo)

            self.session.commit()
            return True

        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to delete attachment {attachment_id}: {e}")
            raise RuntimeError(f"Attachment deletion failed: {str(e)}")

    def _validate_attachment_upload(self, file_data, filename, content_type):
        """Validate an attachment upload -- same rules as a photo, no JA ID."""
        if not file_data:
            raise ValueError("File data is required")

        if len(file_data) > self.MAX_FILE_SIZE:
            raise ValueError(
                f"File size {len(file_data)} exceeds maximum {self.MAX_FILE_SIZE} bytes"
            )

        if not filename or not filename.strip():
            raise ValueError("Filename is required")

        if content_type not in self.SUPPORTED_TYPES:
            supported_list = ', '.join(sorted(self.SUPPORTED_TYPES))
            raise ValueError(
                f"Unsupported content type: {content_type}. Supported: {supported_list}"
            )

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