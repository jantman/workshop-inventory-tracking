/**
 * Photo Manager - Handles photo upload, display, and management
 * Part of Workshop Inventory Tracking system
 */

const PhotoManager = {

    // Safe toast notification helper
    showToast: function(message, type = 'info') {
        // Try to use WorkshopInventory.utils.showToast if available
        if (typeof WorkshopInventory !== 'undefined' &&
            WorkshopInventory.utils &&
            typeof WorkshopInventory.utils.showToast === 'function') {
            WorkshopInventory.utils.showToast(message, type);
        } else {
            // Fallback to console logging and alert for important messages
            const logMethod = type === 'danger' || type === 'error' ? 'error' :
                             type === 'warning' ? 'warn' : 'log';
            console[logMethod](`[PhotoManager] ${message}`);

            // Show alert for critical errors
            if (type === 'danger' || type === 'error') {
                alert(`Error: ${message}`);
            }
        }
    },

    // Configuration
    config: {
        maxFiles: 10,
        maxFileSize: 20 * 1024 * 1024, // 20MB in bytes
        allowedTypes: ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'],
        compressionOptions: {
            maxSizeMB: 20,
            maxWidthOrHeight: 4000,
            useWebWorker: true,
            fileType: 'image/jpeg',
            initialQuality: 0.8
        }
    },
    
    // Initialize photo manager for a form
    init: function(containerSelector, options = {}) {
        const container = document.querySelector(containerSelector);
        if (!container) {
            console.error('PhotoManager: Container not found:', containerSelector);
            return null;
        }
        
        // Merge options with defaults
        const config = Object.assign({}, this.config, options);
        
        // Create photo manager instance
        const instance = {
            container: container,
            config: config,
            photos: [],
            currentItemId: options.itemId || null,
            isReadOnly: options.readOnly || false,
            
            // Initialize the instance
            initialize: function() {
                this.createHTML();
                this.bindEvents();
                if (this.currentItemId) {
                    this.loadExistingPhotos();
                }
            },
            
            // Create HTML structure
            createHTML: function() {
                const uploadSection = this.isReadOnly ? '' : `
                    <div class="photo-upload-section mb-4">
                        <h6 class="fw-bold text-primary mb-3">
                            <i class="bi bi-camera"></i> Upload Photos
                        </h6>
                        
                        <!-- File Drop Zone -->
                        <div class="photo-drop-zone border-2 border-dashed border-primary rounded p-4 text-center" 
                             style="min-height: 120px; cursor: pointer; transition: all 0.3s ease;">
                            <div class="drop-zone-content">
                                <i class="bi bi-cloud-upload display-6 text-primary mb-2"></i>
                                <div class="fw-semibold mb-1">Drop photos here or click to browse</div>
                                <small class="text-muted">
                                    Supports JPEG, PNG, WebP, PDF • Max ${config.maxFiles} files • Up to 20MB each
                                </small>
                            </div>
                            <input type="file" class="photo-file-input d-none" 
                                   multiple accept="image/jpeg,image/png,image/webp,application/pdf">
                        </div>
                        
                        <!-- Upload Progress -->
                        <div class="photo-upload-progress mt-3 d-none">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <span class="fw-semibold">Uploading photos...</span>
                                <span class="upload-count">0 / 0</span>
                            </div>
                            <div class="progress">
                                <div class="progress-bar" role="progressbar" style="width: 0%"></div>
                            </div>
                        </div>
                        
                        <!-- File Preview -->
                        <div class="photo-preview-list mt-3"></div>
                    </div>
                `;
                
                this.container.innerHTML = `
                    ${uploadSection}
                    
                    <!-- Photo Gallery -->
                    <div class="photo-gallery-section">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h6 class="fw-bold text-primary mb-0">
                                <i class="bi bi-images"></i> Photos (<span class="photo-count">0</span>)
                            </h6>
                            ${this.isReadOnly ? '' : `
                                <div class="gallery-actions">
                                    <button type="button" class="btn btn-outline-danger btn-sm delete-selected-btn" 
                                            style="display: none;">
                                        <i class="bi bi-trash"></i> Delete Selected
                                    </button>
                                </div>
                            `}
                        </div>
                        
                        <!-- Gallery Grid -->
                        <div class="photo-gallery-grid row g-2">
                            <!-- Photos will be inserted here -->
                        </div>
                        
                        <!-- Empty State -->
                        <div class="photo-gallery-empty text-center text-muted py-4" style="display: none;">
                            <i class="bi bi-camera display-1 opacity-25"></i>
                            <div class="mt-2">No photos uploaded yet</div>
                            ${this.isReadOnly ? '' : '<small>Use the upload area above to add photos</small>'}
                        </div>
                    </div>
                `;
                
                this.updateGalleryDisplay();
            },
            
            // Bind event listeners
            bindEvents: function() {
                if (this.isReadOnly) return;
                
                const dropZone = this.container.querySelector('.photo-drop-zone');
                const fileInput = this.container.querySelector('.photo-file-input');
                const deleteSelectedBtn = this.container.querySelector('.delete-selected-btn');
                
                // File input change
                fileInput.addEventListener('change', (e) => {
                    this.handleFileSelection(e.target.files);
                });
                
                // Drop zone click
                dropZone.addEventListener('click', () => {
                    fileInput.click();
                });
                
                // Drag and drop
                dropZone.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    dropZone.classList.add('border-success', 'bg-light');
                });
                
                dropZone.addEventListener('dragleave', (e) => {
                    e.preventDefault();
                    dropZone.classList.remove('border-success', 'bg-light');
                });
                
                dropZone.addEventListener('drop', (e) => {
                    e.preventDefault();
                    dropZone.classList.remove('border-success', 'bg-light');
                    this.handleFileSelection(e.dataTransfer.files);
                });
                
                // Delete selected photos
                if (deleteSelectedBtn) {
                    deleteSelectedBtn.addEventListener('click', () => {
                        this.deleteSelectedPhotos();
                    });
                }
            },
            
            // Handle file selection
            handleFileSelection: function(files) {
                const fileArray = Array.from(files);
                
                // Validate file count
                if (this.photos.length + fileArray.length > this.config.maxFiles) {
                    PhotoManager.showToast(
                        `Maximum ${this.config.maxFiles} photos allowed`, 'warning'
                    );
                    return;
                }
                
                // Validate and process each file
                const validFiles = [];
                for (const file of fileArray) {
                    if (this.validateFile(file)) {
                        validFiles.push(file);
                    }
                }
                
                if (validFiles.length > 0) {
                    this.processFiles(validFiles);
                }
            },
            
            // Validate individual file
            validateFile: function(file) {
                // Check file type
                if (!this.config.allowedTypes.includes(file.type)) {
                    PhotoManager.showToast(
                        `${file.name}: Unsupported file type`, 'danger'
                    );
                    return false;
                }

                // Check file size
                if (file.size > this.config.maxFileSize) {
                    PhotoManager.showToast(
                        `${file.name}: File too large (max 20MB)`, 'danger'
                    );
                    return false;
                }
                
                return true;
            },
            
            // Process valid files
            processFiles: async function(files) {
                this.showUploadProgress(files.length);
                
                for (let i = 0; i < files.length; i++) {
                    try {
                        await this.processSingleFile(files[i], i + 1, files.length);
                    } catch (error) {
                        console.error('Error processing file:', error);
                        PhotoManager.showToast(
                            `Error processing ${files[i].name}: ${error.message}`, 'danger'
                        );
                    }
                }
                
                this.hideUploadProgress();
                this.updateGalleryDisplay();
            },
            
            // Process single file
            processSingleFile: async function(file, current, total) {
                this.updateUploadProgress(current, total, `Processing ${file.name}...`);
                
                let processedFile = file;
                
                // Compress image files if library is available
                if (file.type.startsWith('image/') && file.type !== 'image/svg+xml') {
                    if (typeof imageCompression !== 'undefined') {
                        try {
                            processedFile = await imageCompression(file, this.config.compressionOptions);
                            console.log(`Compressed ${file.name}: ${file.size} → ${processedFile.size} bytes`);
                        } catch (error) {
                            console.warn('Compression failed, using original file:', error);
                            this.showCompressionWarning(file.name, 'Compression failed. Using original file.');
                        }
                    } else {
                        console.warn('Image compression library not available, using original file');
                        this.showCompressionWarning(file.name, 'Compression unavailable. Uploading uncompressed file.');
                    }
                }
                
                // Create photo object
                const photo = {
                    id: 'temp_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9),
                    file: processedFile,
                    originalFile: file,
                    name: file.name,
                    size: processedFile.size,
                    type: processedFile.type,
                    preview: null,
                    uploaded: false,
                    selected: false
                };
                
                // Generate preview
                if (processedFile.type.startsWith('image/')) {
                    photo.preview = await this.generateImagePreview(processedFile);
                } else if (processedFile.type === 'application/pdf') {
                    // Use a placeholder initially - we'll get the real thumbnail after upload
                    photo.preview = this.getPDFPreview();
                }
                
                // Upload if we have an item ID
                if (this.currentItemId) {
                    this.updateUploadProgress(current, total, `Uploading ${file.name}...`);
                    await this.uploadPhoto(photo);
                }
                
                this.photos.push(photo);
                this.addPhotoToGallery(photo);
            },
            
            // Generate image preview
            generateImagePreview: function(file) {
                return new Promise((resolve) => {
                    const reader = new FileReader();
                    reader.onload = (e) => resolve(e.target.result);
                    reader.onerror = () => resolve(null);
                    reader.readAsDataURL(file);
                });
            },
            
            // Get PDF preview placeholder
            getPDFPreview: function() {
                return `data:image/svg+xml,${encodeURIComponent(`
                    <svg xmlns="http://www.w3.org/2000/svg" width="150" height="150" viewBox="0 0 150 150">
                        <rect width="150" height="150" fill="#dc3545"/>
                        <text x="75" y="85" text-anchor="middle" fill="white" font-family="Arial" font-size="48" font-weight="bold">PDF</text>
                    </svg>
                `)}`;
            },
            
            // Upload photo to server
            uploadPhoto: async function(photo) {
                const formData = new FormData();
                formData.append('photo', photo.file);
                
                try {
                    const response = await fetch(`/api/items/${this.currentItemId}/photos`, {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (!response.ok) {
                        const errorData = await response.json();
                        throw new Error(errorData.message || 'Upload failed');
                    }
                    
                    const result = await response.json();
                    photo.id = result.photo_id;
                    photo.uploaded = true;
                    
                    // For PDFs, update preview to use server-generated thumbnail
                    if (photo.type === 'application/pdf') {
                        photo.preview = `/api/photos/${photo.id}?size=thumbnail`;
                        // Update the preview in gallery
                        this.updatePhotoInGallery(photo);
                    }
                    
                } catch (error) {
                    console.error('Upload error:', error);
                    throw error;
                }
            },
            
            // Load existing photos for item
            loadExistingPhotos: async function() {
                if (!this.currentItemId) return;
                
                try {
                    const response = await fetch(`/api/items/${this.currentItemId}/photos`);
                    if (!response.ok) return;
                    
                    const data = await response.json();
                    
                    for (const photoData of data.photos) {
                        const photo = {
                            id: photoData.id,
                            name: photoData.filename,
                            size: photoData.file_size,
                            type: photoData.content_type,
                            content_type: photoData.content_type, // Also set content_type for consistency
                            preview: `/api/photos/${photoData.id}?size=thumbnail`,
                            uploaded: true,
                            selected: false,
                            created_at: photoData.created_at // Include creation date
                        };
                        
                        this.photos.push(photo);
                        this.addPhotoToGallery(photo);
                    }
                    
                    this.updateGalleryDisplay();
                    
                } catch (error) {
                    console.error('Error loading photos:', error);
                }
            },
            
            // Add photo to gallery display
            addPhotoToGallery: function(photo) {
                const gallery = this.container.querySelector('.photo-gallery-grid');
                
                const photoCard = document.createElement('div');
                photoCard.className = 'col-6 col-md-4 col-lg-3';
                photoCard.setAttribute('data-photo-id', photo.id);
                
                const selectionCheckbox = this.isReadOnly ? '' : `
                    <div class="photo-selection">
                        <input type="checkbox" class="form-check-input photo-select" 
                               id="photo-select-${photo.id}">
                    </div>
                `;
                
                const deleteButton = this.isReadOnly ? '' : `
                    <button type="button" class="btn btn-outline-danger btn-sm photo-delete-btn" 
                            title="Delete photo">
                        <i class="bi bi-trash"></i>
                    </button>
                `;
                
                photoCard.innerHTML = `
                    <div class="photo-card border rounded overflow-hidden position-relative">
                        ${selectionCheckbox}
                        
                        <div class="photo-thumbnail" style="aspect-ratio: 1; cursor: pointer;">
                            <img src="${photo.preview}" alt="${photo.name}" 
                                 class="w-100 h-100 object-fit-cover" loading="lazy">
                        </div>
                        
                        <div class="photo-info p-2 bg-light">
                            <div class="photo-name small fw-semibold text-truncate" title="${photo.name}">
                                ${photo.name}
                            </div>
                            <div class="photo-meta small text-muted">
                                ${this.formatFileSize(photo.size)}
                                ${!photo.uploaded ? ' • Uploading...' : ''}
                            </div>
                        </div>
                        
                        <div class="photo-actions position-absolute top-0 end-0 p-2">
                            <div class="btn-group-vertical btn-group-sm">
                                <button type="button" class="btn btn-outline-primary btn-sm photo-view-btn" 
                                        title="View full size">
                                    <i class="bi bi-eye"></i>
                                </button>
                                <button type="button" class="btn btn-outline-secondary btn-sm photo-download-btn" 
                                        title="Download">
                                    <i class="bi bi-download"></i>
                                </button>
                                ${deleteButton}
                            </div>
                        </div>
                    </div>
                `;
                
                // Bind photo-specific events
                this.bindPhotoEvents(photoCard, photo);
                
                gallery.appendChild(photoCard);
            },
            
            // Update existing photo in gallery (for preview changes after upload)
            updatePhotoInGallery: function(photo) {
                const gallery = this.container.querySelector('.photo-gallery-grid');
                const existingCard = gallery.querySelector(`[data-photo-id="${photo.id}"]`);
                
                if (existingCard) {
                    const img = existingCard.querySelector('.photo-thumbnail img');
                    const meta = existingCard.querySelector('.photo-meta');
                    
                    if (img) img.src = photo.preview;
                    if (meta) {
                        meta.innerHTML = `${this.formatFileSize(photo.size)}${!photo.uploaded ? ' • Uploading...' : ''}`;
                    }
                }
            },
            
            // Bind events for individual photo
            bindPhotoEvents: function(photoCard, photo) {
                const thumbnail = photoCard.querySelector('.photo-thumbnail');
                const viewBtn = photoCard.querySelector('.photo-view-btn');
                const downloadBtn = photoCard.querySelector('.photo-download-btn');
                const deleteBtn = photoCard.querySelector('.photo-delete-btn');
                const selectCheckbox = photoCard.querySelector('.photo-select');
                
                // View photo (thumbnail click or view button)
                const viewPhoto = () => this.viewPhoto(photo);
                if (thumbnail) thumbnail.addEventListener('click', viewPhoto);
                if (viewBtn) viewBtn.addEventListener('click', viewPhoto);
                
                // Download photo
                if (downloadBtn) {
                    downloadBtn.addEventListener('click', () => this.downloadPhoto(photo));
                }
                
                // Delete photo
                if (deleteBtn) {
                    deleteBtn.addEventListener('click', () => this.deletePhoto(photo));
                }
                
                // Selection checkbox
                if (selectCheckbox) {
                    selectCheckbox.addEventListener('change', (e) => {
                        photo.selected = e.target.checked;
                        this.updateSelectionActions();
                    });
                }
            },
            
            // View photo in lightbox
            viewPhoto: function(photo) {
                if (!photo.uploaded && !photo.preview) return;
                
                // Check if PhotoSwipe is available
                if (typeof PhotoSwipe === 'undefined') {
                    console.warn('PhotoSwipe not available, using fallback modal viewer');
                    this.showFallbackImageModal(photo);
                    return;
                }
                
                // Prepare items for PhotoSwipe v5
                const items = this.photos
                    .filter(p => p.uploaded || p.preview)
                    .map(p => ({
                        src: p.uploaded ? `/api/photos/${p.id}?size=original` : p.preview,
                        width: 1200, // Default width
                        height: 800,  // Default height
                        alt: p.name
                    }));
                
                const currentIndex = this.photos.indexOf(photo);
                
                try {
                    // Initialize PhotoSwipe v5
                    const lightbox = new PhotoSwipe({
                        dataSource: items,
                        index: currentIndex,
                        bgOpacity: 0.8,
                        showHideOpacity: true,
                        initialZoomLevel: 'fit',
                        secondaryZoomLevel: 1.5,
                        maxZoomLevel: 3
                    });
                    
                    lightbox.init();
                } catch (error) {
                    console.warn('PhotoSwipe initialization failed:', error);
                    // Fallback: use modal viewer
                    this.showFallbackImageModal(photo);
                }
            },
            
            // Download photo
            downloadPhoto: function(photo) {
                if (!photo.uploaded) return;
                
                const downloadUrl = `/api/photos/${photo.id}/download`;
                const link = document.createElement('a');
                link.href = downloadUrl;
                link.download = photo.name;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            },
            
            // Delete single photo
            deletePhoto: async function(photo) {
                if (!confirm(`Delete photo "${photo.name}"?`)) return;
                
                try {
                    if (photo.uploaded) {
                        const response = await fetch(`/api/photos/${photo.id}`, {
                            method: 'DELETE'
                        });
                        
                        if (!response.ok) {
                            throw new Error('Failed to delete photo');
                        }
                    }
                    
                    // Remove from photos array
                    const index = this.photos.indexOf(photo);
                    if (index > -1) {
                        this.photos.splice(index, 1);
                    }
                    
                    // Remove from DOM
                    const photoCard = this.container.querySelector(`[data-photo-id="${photo.id}"]`);
                    if (photoCard) {
                        photoCard.remove();
                    }
                    
                    this.updateGalleryDisplay();
                    PhotoManager.showToast('Photo deleted', 'success');

                } catch (error) {
                    console.error('Error deleting photo:', error);
                    PhotoManager.showToast('Failed to delete photo', 'danger');
                }
            },
            
            // Delete selected photos
            deleteSelectedPhotos: async function() {
                const selectedPhotos = this.photos.filter(p => p.selected);
                if (selectedPhotos.length === 0) return;
                
                if (!confirm(`Delete ${selectedPhotos.length} selected photo(s)?`)) return;
                
                for (const photo of selectedPhotos) {
                    await this.deletePhoto(photo);
                }
            },
            
            // Update selection actions visibility
            updateSelectionActions: function() {
                const selectedCount = this.photos.filter(p => p.selected).length;
                const deleteSelectedBtn = this.container.querySelector('.delete-selected-btn');
                
                if (deleteSelectedBtn) {
                    deleteSelectedBtn.style.display = selectedCount > 0 ? 'inline-block' : 'none';
                    deleteSelectedBtn.textContent = `Delete Selected (${selectedCount})`;
                }
            },
            
            // Update gallery display state
            updateGalleryDisplay: function() {
                const gallery = this.container.querySelector('.photo-gallery-grid');
                const emptyState = this.container.querySelector('.photo-gallery-empty');
                const photoCount = this.container.querySelector('.photo-count');
                
                const hasPhotos = this.photos.length > 0;
                
                if (gallery) gallery.style.display = hasPhotos ? 'block' : 'none';
                if (emptyState) emptyState.style.display = hasPhotos ? 'none' : 'block';
                if (photoCount) photoCount.textContent = this.photos.length;
            },
            
            // Show upload progress
            showUploadProgress: function(totalFiles) {
                const progressContainer = this.container.querySelector('.photo-upload-progress');
                if (progressContainer) {
                    progressContainer.classList.remove('d-none');
                    this.updateUploadProgress(0, totalFiles, 'Preparing...');
                }
            },
            
            // Update upload progress
            updateUploadProgress: function(current, total, message = '') {
                const progressContainer = this.container.querySelector('.photo-upload-progress');
                if (!progressContainer) return;
                
                const progressBar = progressContainer.querySelector('.progress-bar');
                const uploadCount = progressContainer.querySelector('.upload-count');
                const progressLabel = progressContainer.querySelector('.fw-semibold');
                
                const percentage = total > 0 ? (current / total) * 100 : 0;
                
                if (progressBar) progressBar.style.width = `${percentage}%`;
                if (uploadCount) uploadCount.textContent = `${current} / ${total}`;
                if (progressLabel && message) progressLabel.textContent = message;
            },
            
            // Hide upload progress
            hideUploadProgress: function() {
                const progressContainer = this.container.querySelector('.photo-upload-progress');
                if (progressContainer) {
                    progressContainer.classList.add('d-none');
                }
            },
            
            // Show compression warning to user
            showCompressionWarning: function(filename, message) {
                // Create or update warning banner
                let warningBanner = this.container.querySelector('.compression-warning');
                if (!warningBanner) {
                    warningBanner = document.createElement('div');
                    warningBanner.className = 'compression-warning alert alert-warning alert-dismissible fade show mt-2';
                    warningBanner.innerHTML = `
                        <i class="bi bi-exclamation-triangle"></i>
                        <strong>Compression Notice:</strong>
                        <span class="warning-message"></span>
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    `;
                    
                    const uploadSection = this.container.querySelector('.photo-upload-section');
                    if (uploadSection) {
                        uploadSection.appendChild(warningBanner);
                    }
                }
                
                const messageSpan = warningBanner.querySelector('.warning-message');
                messageSpan.textContent = `${filename}: ${message}`;
                
                // Auto-dismiss after 8 seconds
                setTimeout(() => {
                    if (warningBanner && warningBanner.parentNode) {
                        warningBanner.remove();
                    }
                }, 8000);
            },
            
            // Show fallback image modal when PhotoSwipe is unavailable
            showFallbackImageModal: function(photo) {
                // Create modal if it doesn't exist
                let modal = document.getElementById('fallback-image-modal');
                if (!modal) {
                    modal = document.createElement('div');
                    modal.id = 'fallback-image-modal';
                    modal.className = 'modal fade';
                    modal.setAttribute('tabindex', '-1');
                    modal.innerHTML = `
                        <div class="modal-dialog modal-lg modal-dialog-centered">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h5 class="modal-title">
                                        <i class="bi bi-image"></i>
                                        <span class="modal-filename"></span>
                                    </h5>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                                </div>
                                <div class="modal-body text-center p-0">
                                    <img class="modal-image img-fluid" style="max-height: 70vh;" alt="Photo preview">
                                    <div class="modal-pdf-viewer d-none" style="height: 70vh; display: flex; flex-direction: column;">
                                        <div class="pdf-canvas-container" style="flex: 1; display: flex; justify-content: center; align-items: center; overflow: auto; background: #f8f9fa;">
                                            <canvas class="pdf-canvas" style="max-width: 100%; max-height: 100%; border: 1px solid #dee2e6;"></canvas>
                                        </div>
                                        <div class="pdf-controls bg-dark text-white d-flex justify-content-between align-items-center p-2">
                                            <div>
                                                <button class="btn btn-sm btn-outline-light pdf-prev-btn">
                                                    <i class="bi bi-chevron-left"></i> Previous
                                                </button>
                                                <span class="mx-2 pdf-page-info">Page 1 of 1</span>
                                                <button class="btn btn-sm btn-outline-light pdf-next-btn">
                                                    Next <i class="bi bi-chevron-right"></i>
                                                </button>
                                            </div>
                                            <div>
                                                <button class="btn btn-sm btn-outline-light pdf-zoom-out-btn">
                                                    <i class="bi bi-zoom-out"></i>
                                                </button>
                                                <span class="mx-2 pdf-zoom-level">100%</span>
                                                <button class="btn btn-sm btn-outline-light pdf-zoom-in-btn">
                                                    <i class="bi bi-zoom-in"></i>
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="modal-pdf-notice d-none p-4">
                                        <i class="bi bi-file-earmark-pdf display-1 text-danger"></i>
                                        <p class="mt-3">PDF viewer is not available. Please download to view.</p>
                                        <a href="#" class="btn btn-outline-primary modal-download-btn">
                                            <i class="bi bi-download"></i> Download PDF
                                        </a>
                                    </div>
                                </div>
                                <div class="modal-footer justify-content-between">
                                    <small class="text-muted modal-info"></small>
                                    <div>
                                        <a href="#" class="btn btn-outline-secondary modal-download-btn">
                                            <i class="bi bi-download"></i> Download
                                        </a>
                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                    document.body.appendChild(modal);
                }
                
                // Update modal content
                const modalTitle = modal.querySelector('.modal-filename');
                const modalImage = modal.querySelector('.modal-image');
                const modalPdfViewer = modal.querySelector('.modal-pdf-viewer');
                const modalPdfNotice = modal.querySelector('.modal-pdf-notice');
                const modalInfo = modal.querySelector('.modal-info');
                const downloadBtns = modal.querySelectorAll('.modal-download-btn');
                
                modalTitle.textContent = photo.name || 'Photo';
                
                if ((photo.type && photo.type.includes('pdf')) || (photo.content_type && photo.content_type.includes('pdf'))) {
                    modalImage.classList.add('d-none');
                    
                    // Try to load PDF with PDF.js
                    if (typeof pdfjsLib !== 'undefined' && photo.uploaded) {
                        modalPdfViewer.classList.remove('d-none');
                        modalPdfNotice.classList.add('d-none');
                        this.loadPDFInViewer(photo, modalPdfViewer);
                    } else {
                        // Fallback to notice if PDF.js not available or photo not uploaded
                        modalPdfViewer.classList.add('d-none');
                        modalPdfNotice.classList.remove('d-none');
                    }
                } else {
                    modalImage.classList.remove('d-none');
                    modalPdfViewer.classList.add('d-none');
                    modalPdfNotice.classList.add('d-none');
                    
                    const imageUrl = photo.uploaded ? `/api/photos/${photo.id}?size=original` : photo.preview;
                    modalImage.src = imageUrl;
                    modalImage.alt = photo.name || 'Photo';
                }
                
                // Update info and download links
                const fileSize = photo.size ? this.formatFileSize(photo.size) : '';
                const uploadDate = photo.created_at ? new Date(photo.created_at).toLocaleDateString() : '';
                modalInfo.textContent = [fileSize, uploadDate].filter(Boolean).join(' • ');
                
                const downloadUrl = photo.uploaded ? `/api/photos/${photo.id}/download` : photo.preview;
                downloadBtns.forEach(btn => {
                    btn.href = downloadUrl;
                    btn.download = photo.name || 'photo';
                });
                
                // Show modal
                const bootstrapModal = new bootstrap.Modal(modal);
                bootstrapModal.show();
            },
            
            // Load PDF in viewer using PDF.js
            loadPDFInViewer: function(photo, viewerElement) {
                const canvas = viewerElement.querySelector('.pdf-canvas');
                const pageInfo = viewerElement.querySelector('.pdf-page-info');
                const prevBtn = viewerElement.querySelector('.pdf-prev-btn');
                const nextBtn = viewerElement.querySelector('.pdf-next-btn');
                const zoomInBtn = viewerElement.querySelector('.pdf-zoom-in-btn');
                const zoomOutBtn = viewerElement.querySelector('.pdf-zoom-out-btn');
                const zoomLevel = viewerElement.querySelector('.pdf-zoom-level');
                
                let pdfDoc = null;
                let currentPage = 1;
                let currentZoom = 1.0;
                
                const pdfUrl = `/api/photos/${photo.id}?size=original`;
                
                // Configure PDF.js worker
                if (typeof pdfjsLib !== 'undefined') {
                    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js';
                    
                    // Load PDF
                    pdfjsLib.getDocument(pdfUrl).promise.then(pdf => {
                        pdfDoc = pdf;
                        pageInfo.textContent = `Page ${currentPage} of ${pdf.numPages}`;
                        
                        // Update navigation buttons
                        prevBtn.disabled = currentPage <= 1;
                        nextBtn.disabled = currentPage >= pdf.numPages;
                        
                        // Render first page
                        renderPage(currentPage);
                        
                        // Set up event listeners
                        prevBtn.onclick = () => {
                            if (currentPage > 1) {
                                currentPage--;
                                renderPage(currentPage);
                                pageInfo.textContent = `Page ${currentPage} of ${pdf.numPages}`;
                                prevBtn.disabled = currentPage <= 1;
                                nextBtn.disabled = false;
                            }
                        };
                        
                        nextBtn.onclick = () => {
                            if (currentPage < pdf.numPages) {
                                currentPage++;
                                renderPage(currentPage);
                                pageInfo.textContent = `Page ${currentPage} of ${pdf.numPages}`;
                                nextBtn.disabled = currentPage >= pdf.numPages;
                                prevBtn.disabled = false;
                            }
                        };
                        
                        zoomInBtn.onclick = () => {
                            currentZoom = Math.min(currentZoom * 1.2, 3.0);
                            zoomLevel.textContent = Math.round(currentZoom * 100) + '%';
                            renderPage(currentPage);
                        };
                        
                        zoomOutBtn.onclick = () => {
                            currentZoom = Math.max(currentZoom / 1.2, 0.5);
                            zoomLevel.textContent = Math.round(currentZoom * 100) + '%';
                            renderPage(currentPage);
                        };
                        
                    }).catch(error => {
                        console.error('Error loading PDF:', error);
                        // Fall back to notice
                        viewerElement.classList.add('d-none');
                        viewerElement.parentElement.querySelector('.modal-pdf-notice').classList.remove('d-none');
                    });
                }
                
                function renderPage(pageNumber) {
                    if (!pdfDoc) return;
                    
                    pdfDoc.getPage(pageNumber).then(page => {
                        const container = viewerElement.querySelector('.pdf-canvas-container');
                        const containerWidth = container.clientWidth - 20; // Account for padding
                        const containerHeight = container.clientHeight - 20;
                        
                        // Calculate scale to fit within container while maintaining aspect ratio
                        let scale = currentZoom;
                        const viewport = page.getViewport({ scale: 1.0 });
                        const scaleX = containerWidth / viewport.width;
                        const scaleY = containerHeight / viewport.height;
                        const containerScale = Math.min(scaleX, scaleY, 2.0); // Max 2x for readability
                        
                        // Apply both container scale and user zoom
                        const finalScale = containerScale * currentZoom;
                        const finalViewport = page.getViewport({ scale: finalScale });
                        
                        const context = canvas.getContext('2d');
                        
                        // Set canvas size to match scaled viewport
                        canvas.width = finalViewport.width;
                        canvas.height = finalViewport.height;
                        
                        // Remove explicit CSS sizing to let the container handle it
                        canvas.style.width = '';
                        canvas.style.height = '';
                        canvas.style.maxWidth = '100%';
                        canvas.style.maxHeight = '100%';
                        
                        const renderContext = {
                            canvasContext: context,
                            viewport: finalViewport
                        };
                        
                        page.render(renderContext);
                    });
                }
            },
            
            // Format file size
            formatFileSize: function(bytes) {
                if (bytes === 0) return '0 B';
                const k = 1024;
                const sizes = ['B', 'KB', 'MB', 'GB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
            },
            
            // Get current photos data for form submission
            getPhotosData: function() {
                return {
                    photoIds: this.photos.filter(p => p.uploaded).map(p => p.id),
                    photoCount: this.photos.length
                };
            },
            
            // Clear all photos (for form reset)
            clearAll: function() {
                this.photos = [];
                const gallery = this.container.querySelector('.photo-gallery-grid');
                if (gallery) gallery.innerHTML = '';
                this.updateGalleryDisplay();
            }
        };
        
        // Initialize and return the instance
        instance.initialize();
        return instance;
    }
};

// Make PhotoManager available globally
window.PhotoManager = PhotoManager;