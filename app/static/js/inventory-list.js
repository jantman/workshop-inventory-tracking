/**
 * Inventory List JavaScript - Inventory Listing Interface
 *
 * Handles inventory display, filtering, sorting, and pagination
 * with advanced search capabilities and bulk operations.
 */

import { InventoryTable } from './components/inventory-table.js';
import { toggleItemStatus } from './components/item-actions.js';

class InventoryListManager {
    constructor() {
        this.items = [];
        this.filteredItems = [];
        this.filters = {
            status: 'active',
            type: 'all',
            material: '',
            search: ''
        };

        // Photo clipboard state
        this.photoClipboard = this.loadPhotoClipboard();

        this.initializeElements();
        this.initializeTable();
        this.bindEvents();
        this.initializeBulkPrintModal();
        this.loadFiltersFromURL();  // Load filters from URL params if present
        this.loadInventory();
        this.updatePhotoClipboardUI();  // Update UI based on clipboard state

        console.log('InventoryListManager initialized');
    }

    initializeTable() {
        // Create InventoryTable instance
        this.table = new InventoryTable({
            tableBodyId: 'inventory-table-body',
            enableSelection: true,
            enableSorting: true,
            showSubLocation: true,
            itemsPerPage: 25,
            onSelectionChange: (selectedIds) => this.onSelectionChange(selectedIds),
            onActionClick: (action, jaId) => this.onActionClick(action, jaId)
        });
    }
    
    initializeElements() {
        // Filter elements
        this.statusFilter = document.getElementById('status-filter');
        this.typeFilter = document.getElementById('type-filter');
        this.materialFilter = document.getElementById('material-filter');
        this.searchFilter = document.getElementById('search-filter');
        this.clearFiltersBtn = document.getElementById('clear-filters-btn');
        this.clearAllFiltersBtn = document.getElementById('clear-all-filters');
        
        // Control elements
        this.refreshBtn = document.getElementById('refresh-btn');
        this.exportBtn = document.getElementById('export-btn');
        this.bookmarkBtn = document.getElementById('bookmark-btn');
        this.itemsPerPageSelect = document.getElementById('items-per-page');
        
        // Selection elements
        this.selectAllCheckbox = document.getElementById('select-all-checkbox');
        this.selectAllBtn = document.getElementById('select-all-btn');
        this.selectNoneBtn = document.getElementById('select-none-btn');
        this.bulkMoveBtn = document.getElementById('bulk-move-btn');
        this.bulkDeactivateBtn = document.getElementById('bulk-deactivate-btn');
        this.bulkPrintLabelsBtn = document.getElementById('bulk-print-labels-btn');

        // Photo clipboard elements
        this.copyPhotosBtn = document.getElementById('copy-photos-btn');
        this.pastePhotosBtn = document.getElementById('paste-photos-btn');
        this.clearPhotoClipboardBtn = document.getElementById('clear-photo-clipboard-btn');
        this.photoClipboardBanner = document.getElementById('photo-clipboard-banner');
        this.photoClipboardInfo = document.getElementById('photo-clipboard-info');

        // Display elements
        this.itemCount = document.getElementById('item-count');
        this.loadingState = document.getElementById('loading-state');
        this.emptyState = document.getElementById('empty-state');
        this.errorState = document.getElementById('error-state');
        this.inventoryTableContainer = document.getElementById('inventory-table-container');
        this.inventoryTableBody = document.getElementById('inventory-table-body');
        this.retryBtn = document.getElementById('retry-btn');
        
        // Pagination elements
        this.paginationContainer = document.getElementById('pagination-container');
        this.pagination = document.getElementById('pagination');
        this.itemsStart = document.getElementById('items-start');
        this.itemsEnd = document.getElementById('items-end');
        this.itemsTotal = document.getElementById('items-total');
        
        // Sortable headers
        this.sortableHeaders = document.querySelectorAll('.sortable');
    }
    
    bindEvents() {
        // Filter events
        this.statusFilter.addEventListener('change', () => this.onFilterChange());
        this.typeFilter.addEventListener('change', () => this.onFilterChange());
        this.materialFilter.addEventListener('input', () => this.onFilterChange());
        this.searchFilter.addEventListener('input', () => this.onFilterChange());
        this.clearFiltersBtn.addEventListener('click', () => this.clearFilters());
        if (this.clearAllFiltersBtn) {
            this.clearAllFiltersBtn.addEventListener('click', () => this.clearAllFilters());
        }
        
        // Control events
        this.refreshBtn.addEventListener('click', () => this.loadInventory());
        this.exportBtn.addEventListener('click', () => this.exportToCSV());
        this.bookmarkBtn.addEventListener('click', () => this.copyBookmarkLink());
        this.itemsPerPageSelect.addEventListener('change', () => this.onItemsPerPageChange());
        this.retryBtn.addEventListener('click', () => this.loadInventory());
        
        // Selection events
        this.selectAllCheckbox.addEventListener('change', (e) => this.toggleSelectAll(e.target.checked));
        this.selectAllBtn.addEventListener('click', () => this.selectAll());
        this.selectNoneBtn.addEventListener('click', () => this.selectNone());
        this.bulkMoveBtn.addEventListener('click', () => this.bulkMoveSelected());
        this.bulkDeactivateBtn.addEventListener('click', () => this.bulkDeactivateSelected());
        this.bulkPrintLabelsBtn.addEventListener('click', () => this.printLabelsForSelected());

        // Photo clipboard events
        if (this.copyPhotosBtn) {
            this.copyPhotosBtn.addEventListener('click', () => this.copyPhotosFromSelected());
        }
        if (this.pastePhotosBtn) {
            this.pastePhotosBtn.addEventListener('click', () => this.pastePhotosToSelected());
        }
        if (this.clearPhotoClipboardBtn) {
            this.clearPhotoClipboardBtn.addEventListener('click', () => this.clearPhotoClipboard());
        }

        // Note: Sorting now handled by InventoryTable component
    }

    initializeBulkPrintModal() {
        // Set up event listener for label type selection
        const labelTypeSelect = document.getElementById('list-bulk-label-type');
        if (labelTypeSelect) {
            labelTypeSelect.addEventListener('change', () => {
                this.onLabelTypeChange();
            });
        }

        // Set up event listener for Print All Labels button
        const printAllBtn = document.getElementById('list-bulk-print-all-btn');
        if (printAllBtn) {
            printAllBtn.addEventListener('click', () => {
                this.printAllLabels();
            });
        }

        // Set up event listener for modal close to reset state
        const modalElement = document.getElementById('listBulkLabelPrintingModal');
        if (modalElement) {
            modalElement.addEventListener('hidden.bs.modal', () => {
                this.onBulkPrintModalClose();
            });
        }
    }

    onLabelTypeChange() {
        const labelTypeSelect = document.getElementById('list-bulk-label-type');
        const printAllBtn = document.getElementById('list-bulk-print-all-btn');

        // Enable the Print All button only if a label type is selected
        if (labelTypeSelect.value) {
            printAllBtn.disabled = false;
        } else {
            printAllBtn.disabled = true;
        }
    }

    onBulkPrintModalClose() {
        // Reset the modal state when it's closed
        // This ensures the modal is clean for the next use
        this.resetBulkPrintModal();
    }

    async printAllLabels() {
        const labelType = document.getElementById('list-bulk-label-type').value;
        const selectedJaIds = this.table.getSelectedItems();

        const progressDiv = document.getElementById('list-bulk-print-progress');
        const progressBar = document.getElementById('list-bulk-print-progress-bar');
        const statusSpan = document.getElementById('list-bulk-print-status');
        const errorsDiv = document.getElementById('list-bulk-print-errors');
        const printBtn = document.getElementById('list-bulk-print-all-btn');
        const doneBtn = document.getElementById('list-bulk-print-done-btn');
        const cancelBtn = document.getElementById('list-bulk-print-cancel');

        // Show progress section
        progressDiv.classList.remove('d-none');
        printBtn.classList.add('d-none');
        cancelBtn.classList.add('d-none');

        let successCount = 0;
        let failureCount = 0;
        const errors = [];

        // Iterate through all selected items and print labels
        for (let i = 0; i < selectedJaIds.length; i++) {
            const jaId = selectedJaIds[i];
            const progress = Math.round(((i + 1) / selectedJaIds.length) * 100);

            // Update progress display
            statusSpan.textContent = `Printing ${i + 1} of ${selectedJaIds.length}: ${jaId}`;
            progressBar.style.width = `${progress}%`;
            progressBar.textContent = `${progress}%`;

            try {
                const response = await fetch('/api/labels/print', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        ja_id: jaId,
                        label_type: labelType
                    })
                });

                if (response.ok) {
                    successCount++;
                } else {
                    const data = await response.json();
                    failureCount++;
                    errors.push(`${jaId}: ${data.error || response.statusText}`);
                }
            } catch (error) {
                failureCount++;
                errors.push(`${jaId}: ${error.message}`);
            }
        }

        // Display error messages if any failures occurred
        if (failureCount > 0) {
            errorsDiv.classList.remove('d-none');
            errorsDiv.innerHTML = `
                <strong>Warning:</strong> ${failureCount} label(s) failed to print:<br>
                ${errors.map(e => `• ${e}`).join('<br>')}
            `;
        }

        // Update final status
        statusSpan.textContent = `Complete: ${successCount} printed, ${failureCount} failed`;
        progressBar.classList.remove('progress-bar-animated');

        // Show done button
        doneBtn.classList.remove('d-none');

        // Show success toast notification
        if (successCount > 0) {
            this.showToast(`Printed ${successCount} label(s) successfully`, 'success');
        }
    }

    showToast(message, type = 'info') {
        // Simple toast notification - can be enhanced later
        const alertClass = type === 'success' ? 'alert-success' :
                          type === 'error' ? 'alert-danger' :
                          type === 'warning' ? 'alert-warning' :
                          'alert-info';
        const toast = document.createElement('div');
        toast.className = `alert ${alertClass} position-fixed top-0 start-50 translate-middle-x mt-3`;
        toast.style.zIndex = '9999';
        toast.textContent = message;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    async loadInventory() {
        this.showLoading();
        
        try {
            const response = await fetch('/api/inventory/list');
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.error || 'Failed to load inventory');
            }
            
            this.items = data.items || [];
            this.applyFilters();
            this.table.setItems(this.filteredItems);
            this.updateItemCount();
            this.showInventoryTable();
            
        } catch (error) {
            console.error('Error loading inventory:', error);
            this.showError();
        }
    }
    
    onFilterChange() {
        // Update filter state
        this.filters.status = this.statusFilter.value;
        this.filters.type = this.typeFilter.value;
        this.filters.material = this.materialFilter.value.toLowerCase();
        this.filters.search = this.searchFilter.value.toLowerCase();

        // Apply filters and update table
        this.applyFilters();
        this.table.setItems(this.filteredItems);
    }
    
    clearFilters() {
        this.materialFilter.value = '';
        this.searchFilter.value = '';
        this.onFilterChange();
    }
    
    clearAllFilters() {
        this.statusFilter.value = 'active';
        this.typeFilter.value = 'all';
        this.materialFilter.value = '';
        this.searchFilter.value = '';
        this.onFilterChange();
    }

    loadFiltersFromURL() {
        const params = new URLSearchParams(window.location.search);
        if (params.has('status')) this.statusFilter.value = params.get('status');
        if (params.has('type')) this.typeFilter.value = params.get('type');
        if (params.has('material')) this.materialFilter.value = params.get('material');
        if (params.has('search')) this.searchFilter.value = params.get('search');
    }

    copyBookmarkLink() {
        const url = new URL(window.location.href);
        url.searchParams.set('status', this.filters.status);
        url.searchParams.set('type', this.filters.type);
        if (this.filters.material) {
            url.searchParams.set('material', this.filters.material);
        } else {
            url.searchParams.delete('material');
        }
        if (this.filters.search) {
            url.searchParams.set('search', this.filters.search);
        } else {
            url.searchParams.delete('search');
        }

        navigator.clipboard.writeText(url.toString())
            .then(() => {
                // Show success feedback
                const originalText = this.bookmarkBtn.innerHTML;
                this.bookmarkBtn.innerHTML = '<i class="bi bi-check"></i> Copied!';
                this.bookmarkBtn.classList.add('btn-success');
                this.bookmarkBtn.classList.remove('btn-outline-secondary');

                setTimeout(() => {
                    this.bookmarkBtn.innerHTML = originalText;
                    this.bookmarkBtn.classList.remove('btn-success');
                    this.bookmarkBtn.classList.add('btn-outline-secondary');
                }, 2000);
            })
            .catch(err => {
                console.error('Failed to copy bookmark link:', err);
                alert('Failed to copy bookmark link. Please try again.');
            });
    }

    onItemsPerPageChange() {
        const newItemsPerPage = parseInt(this.itemsPerPageSelect.value);
        this.table.config.itemsPerPage = newItemsPerPage;
        this.table.currentPage = 1;
        this.table.refresh();
    }

    applyFilters() {
        // Apply filters
        this.filteredItems = this.items.filter(item => {
            // Status filter
            if (this.filters.status === 'active' && !item.active) return false;
            if (this.filters.status === 'inactive' && item.active) return false;
            
            // Type filter
            if (this.filters.type !== 'all' && item.item_type !== this.filters.type) return false;
            
            // Material filter
            if (this.filters.material && !item.material.toLowerCase().includes(this.filters.material)) return false;
            
            // Search filter (searches JA ID, location, notes)
            if (this.filters.search) {
                const searchText = this.filters.search;
                const searchFields = [
                    item.ja_id.toLowerCase(),
                    (item.location || '').toLowerCase(),
                    (item.sub_location || '').toLowerCase(),
                    (item.notes || '').toLowerCase(),
                    item.display_name.toLowerCase()
                ];
                
                if (!searchFields.some(field => field.includes(searchText))) {
                    return false;
                }
            }
            
            return true;
        });

        // Note: Sorting is now handled by InventoryTable component
    }

    onSelectionChange(selectedIds) {
        // Update bulk action buttons
        this.updateBulkActions();
        // Update photo clipboard button states
        this.updatePhotoClipboardUI();
    }

    onActionClick(action, jaId) {
        // Handle action clicks (currently handled by onclick handlers in HTML)
        console.log(`Action ${action} clicked for ${jaId}`);
    }

    // Note: updateDisplay and createTableRow methods removed - now handled by InventoryTable component

    selectAll() {
        this.table.selectAll();
    }

    selectNone() {
        this.table.selectNone();
    }

    toggleSelectAll(checked) {
        if (checked) {
            this.selectAll();
        } else {
            this.selectNone();
        }
    }

    // Methods removed (now in InventoryTable): renderTable, createTableRow

    // Old createTableRow removed - functionality now in InventoryTable component

    updateSelectAllCheckbox() {
        const selectedCount = this.table.getSelectedItems().length;
        const totalCount = this.filteredItems.length;
        if (this.selectAllCheckbox) {
            this.selectAllCheckbox.checked = selectedCount > 0 && selectedCount === totalCount;
            this.selectAllCheckbox.indeterminate = selectedCount > 0 && selectedCount < totalCount;
        }
    }

    // Old methods removed - now handled by InventoryTable component:
    // renderPagination, goToPage, updateSortIcons, toggleSelectAll (old version)
    // selectAll/selectNone (old versions), getVisibleItems, updateSelectAllCheckbox (old version)

    updateBulkActions() {
        const selectedCount = this.table.getSelectedItems().length;
        const hasSelection = selectedCount > 0;
        this.bulkMoveBtn.classList.toggle('disabled', !hasSelection);
        this.bulkDeactivateBtn.classList.toggle('disabled', !hasSelection);
        this.bulkPrintLabelsBtn.classList.toggle('disabled', !hasSelection);
    }
    
    bulkMoveSelected() {
        const selectedIds = this.table.getSelectedItems();
        if (selectedIds.length === 0) return;

        const url = new URL('/inventory/move', window.location.origin);
        url.searchParams.set('items', selectedIds.join(','));
        window.location.href = url.toString();
    }

    bulkDeactivateSelected() {
        const selectedIds = this.table.getSelectedItems();
        if (selectedIds.length === 0) return;

        const count = selectedIds.length;
        if (!confirm(`Are you sure you want to deactivate ${count} selected item(s)?`)) {
            return;
        }

        // Implementation would go here
        alert(`Bulk deactivate feature coming soon! Would deactivate ${count} items.`);
    }

    printLabelsForSelected() {
        const selectedIds = this.table.getSelectedItems();
        if (selectedIds.length === 0) {
            alert('Please select at least one item to print labels.');
            return;
        }

        // Show the bulk label printing modal with selected items
        this.showBulkLabelPrintingModal();
    }

    async showBulkLabelPrintingModal() {
        const selectedJaIds = this.table.getSelectedItems();

        // Update summary
        const summaryElement = document.getElementById('list-bulk-print-summary');
        summaryElement.textContent = `You have selected ${selectedJaIds.length} item(s) to print labels for.`;

        // Populate the items list
        const itemsList = document.getElementById('list-bulk-label-items-list');
        itemsList.innerHTML = '';
        selectedJaIds.forEach(jaId => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.textContent = jaId;
            itemsList.appendChild(li);
        });

        // Load and populate label types
        await this.loadLabelTypes();

        // Reset modal state
        this.resetBulkPrintModal();

        // Show the modal
        const modalElement = document.getElementById('listBulkLabelPrintingModal');
        const modal = new bootstrap.Modal(modalElement);
        modal.show();
    }

    async loadLabelTypes() {
        try {
            const response = await fetch('/api/labels/types');
            if (!response.ok) {
                throw new Error('Failed to load label types');
            }

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Failed to load label types');
            }

            const labelTypeSelect = document.getElementById('list-bulk-label-type');
            // Clear existing options except the first placeholder
            while (labelTypeSelect.children.length > 1) {
                labelTypeSelect.removeChild(labelTypeSelect.lastChild);
            }

            // Add label type options
            data.label_types.forEach(labelType => {
                const option = document.createElement('option');
                option.value = labelType;
                option.textContent = labelType;
                labelTypeSelect.appendChild(option);
            });
        } catch (error) {
            console.error('Error loading label types:', error);
            alert('Failed to load label types. Please try again.');
        }
    }

    resetBulkPrintModal() {
        // Reset label type selection
        const labelTypeSelect = document.getElementById('list-bulk-label-type');
        labelTypeSelect.value = '';

        // Hide progress section
        const progressDiv = document.getElementById('list-bulk-print-progress');
        progressDiv.classList.add('d-none');

        // Reset progress bar
        const progressBar = document.getElementById('list-bulk-print-progress-bar');
        progressBar.style.width = '0%';
        progressBar.textContent = '';

        // Clear error messages
        const errorsDiv = document.getElementById('list-bulk-print-errors');
        errorsDiv.classList.add('d-none');
        errorsDiv.innerHTML = '';

        // Show/hide appropriate buttons
        document.getElementById('list-bulk-print-all-btn').classList.remove('d-none');
        document.getElementById('list-bulk-print-all-btn').disabled = true;
        document.getElementById('list-bulk-print-done-btn').classList.add('d-none');
        document.getElementById('list-bulk-print-cancel').classList.remove('d-none');
    }

    exportToCSV() {
        // Implementation would generate and download CSV
        alert('CSV export feature coming soon!');
    }
    
    showLoading() {
        this.loadingState.classList.remove('d-none');
        this.emptyState.classList.add('d-none');
        this.errorState.classList.add('d-none');
        this.inventoryTableContainer.classList.add('d-none');
        this.paginationContainer.classList.add('d-none');
        this.itemCount.textContent = 'Loading...';
    }
    
    showError() {
        this.loadingState.classList.add('d-none');
        this.emptyState.classList.add('d-none');
        this.errorState.classList.remove('d-none');
        this.inventoryTableContainer.classList.add('d-none');
        this.paginationContainer.classList.add('d-none');
        this.itemCount.textContent = 'Error loading items';
    }
    
    showInventoryTable() {
        this.loadingState.classList.add('d-none');
        this.errorState.classList.add('d-none');
        
        if (this.filteredItems.length === 0) {
            this.emptyState.classList.remove('d-none');
            this.inventoryTableContainer.classList.add('d-none');
            this.paginationContainer.classList.add('d-none');
        } else {
            this.emptyState.classList.add('d-none');
            this.inventoryTableContainer.classList.remove('d-none');
            // Table rendering now handled by InventoryTable component via setItems()
        }
    }
    
    updateItemCount() {
        const total = this.items.length;
        const filtered = this.filteredItems.length;
        const active = this.items.filter(item => item.active).length;

        if (filtered !== total) {
            this.itemCount.innerHTML = `${filtered} of ${total} items shown (${active} active)`;
        } else {
            this.itemCount.innerHTML = `${total} items (${active} active)`;
        }
    }

    // ========== Photo Clipboard Methods ==========

    loadPhotoClipboard() {
        try {
            const data = sessionStorage.getItem('photoClipboard');
            return data ? JSON.parse(data) : null;
        } catch (e) {
            console.error('Error loading photo clipboard:', e);
            return null;
        }
    }

    savePhotoClipboard(clipboard) {
        try {
            if (clipboard) {
                sessionStorage.setItem('photoClipboard', JSON.stringify(clipboard));
            } else {
                sessionStorage.removeItem('photoClipboard');
            }
        } catch (e) {
            console.error('Error saving photo clipboard:', e);
        }
    }

    copyPhotosFromSelected() {
        const selectedIds = this.table.getSelectedItems();

        if (selectedIds.length === 0) {
            this.showToast('Please select an item to copy photos from', 'warning');
            return;
        }

        if (selectedIds.length > 1) {
            this.showToast('Please select exactly one item to copy photos from', 'warning');
            return;
        }

        const sourceJaId = selectedIds[0];
        const sourceItem = this.items.find(item => item.ja_id === sourceJaId);

        if (!sourceItem) {
            this.showToast('Source item not found', 'error');
            return;
        }

        // Check if item has photos
        if (!sourceItem.photo_count || sourceItem.photo_count === 0) {
            this.showToast(`Item ${sourceJaId} has no photos to copy`, 'error');
            return;
        }

        // Save to clipboard
        this.photoClipboard = {
            source_ja_id: sourceJaId,
            photo_count: sourceItem.photo_count,
            timestamp: new Date().toISOString()
        };
        this.savePhotoClipboard(this.photoClipboard);

        // Clear selection and update UI
        this.table.selectNone();
        this.updatePhotoClipboardUI();

        this.showToast(`Ready to paste ${sourceItem.photo_count} photo(s) from ${sourceJaId}`, 'success');
    }

    async pastePhotosToSelected() {
        if (!this.photoClipboard) {
            this.showToast('No photos in clipboard. Please copy photos from an item first.', 'warning');
            return;
        }

        const selectedIds = this.table.getSelectedItems();

        if (selectedIds.length === 0) {
            this.showToast('Please select target items to paste photos to', 'warning');
            return;
        }

        const sourceJaId = this.photoClipboard.source_ja_id;
        const photoCount = this.photoClipboard.photo_count;

        // Show confirmation
        const confirmed = confirm(
            `Paste ${photoCount} photo(s) from ${sourceJaId} to ${selectedIds.length} selected item(s)?`
        );

        if (!confirmed) {
            return;
        }

        try {
            const response = await fetch('/api/photos/copy', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    source_ja_id: sourceJaId,
                    target_ja_ids: selectedIds
                })
            });

            const data = await response.json();

            if (data.success) {
                const message = `Copied ${data.photos_copied} photo(s) to ${data.items_updated} item(s)`;
                this.showToast(message, 'success');

                // Clear clipboard and selection (suppress toast since we already showed success)
                this.clearPhotoClipboard(false);
                this.table.selectNone();

                // Reload inventory to show updated photo counts
                await this.loadInventory();
            } else if (response.status === 207) {
                // Partial success
                const successCount = data.details.filter(d => d.success).length;
                const failCount = data.details.filter(d => !d.success).length;
                const message = `Partially successful: ${successCount} succeeded, ${failCount} failed`;
                this.showToast(message, 'warning');

                // Still clear clipboard and reload (suppress toast since we already showed result)
                this.clearPhotoClipboard(false);
                this.table.selectNone();
                await this.loadInventory();
            } else {
                this.showToast(data.error || 'Failed to paste photos', 'error');
            }
        } catch (error) {
            console.error('Error pasting photos:', error);
            this.showToast('Error pasting photos. Please try again.', 'error');
        }
    }

    clearPhotoClipboard(showToast = true) {
        this.photoClipboard = null;
        this.savePhotoClipboard(null);
        this.updatePhotoClipboardUI();
        if (showToast) {
            this.showToast('Photo clipboard cleared', 'info');
        }
    }

    updatePhotoClipboardUI() {
        const hasClipboard = this.photoClipboard !== null;
        const selectedIds = this.table ? this.table.getSelectedItems() : [];

        // Update banner visibility and content
        if (this.photoClipboardBanner) {
            if (hasClipboard) {
                this.photoClipboardBanner.classList.remove('d-none');
                if (this.photoClipboardInfo) {
                    const { source_ja_id, photo_count } = this.photoClipboard;
                    this.photoClipboardInfo.textContent =
                        `${photo_count} photo(s) from ${source_ja_id} ready to paste. Select target items and click 'Paste Photos'.`;
                }
            } else {
                this.photoClipboardBanner.classList.add('d-none');
            }
        }

        // Update button states
        if (this.copyPhotosBtn) {
            // Enable copy button only if exactly 1 item selected AND it has photos
            let canCopy = false;
            if (selectedIds.length === 1) {
                const selectedItem = this.items.find(item => item.ja_id === selectedIds[0]);
                canCopy = selectedItem && selectedItem.photo_count > 0;
            }
            // For <a> elements, we need to add/remove the disabled attribute, not just set the property
            if (canCopy) {
                this.copyPhotosBtn.removeAttribute('disabled');
            } else {
                this.copyPhotosBtn.setAttribute('disabled', '');
            }
        }

        if (this.pastePhotosBtn) {
            // For <a> elements, we need to add/remove the disabled attribute, not just set the property
            if (!hasClipboard || selectedIds.length === 0) {
                this.pastePhotosBtn.setAttribute('disabled', '');
            } else {
                this.pastePhotosBtn.removeAttribute('disabled');
            }
        }

        if (this.clearPhotoClipboardBtn) {
            // For <a> elements, we need to add/remove the disabled attribute, not just set the property
            if (!hasClipboard) {
                this.clearPhotoClipboardBtn.setAttribute('disabled', '');
            } else {
                this.clearPhotoClipboardBtn.removeAttribute('disabled');
            }
        }
    }
}

// Global functions for row actions
window.showItemDetails = function(jaId) {
    // Check if bootstrap is available
    if (typeof bootstrap === 'undefined') {
        console.error('Bootstrap is not loaded');
        return;
    }
    
    // Get or create modal element
    let modalElement = document.getElementById('item-details-modal');
    if (!modalElement) {
        modalElement = createItemDetailsModal();
    }
    
    // Show loading state
    const modal = new bootstrap.Modal(modalElement);
    const modalBody = document.querySelector('#item-details-modal .modal-body');
    
    modalBody.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-3">Loading item details...</p>
        </div>
    `;
    
    modal.show();
    
    // Fetch item details
    fetch(`/inventory/view/${jaId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                modalBody.innerHTML = createItemDetailsHTML(data.item);
                
                // Initialize photo manager for the modal
                initializeItemDetailsPhotoManager(data.item.ja_id);
            } else {
                modalBody.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle"></i>
                        Error: ${data.error || 'Unable to load item details'}
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error fetching item details:', error);
            modalBody.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i>
                    Error loading item details. Please try again.
                </div>
            `;
        });
};

function createItemDetailsModal() {
    const modalHTML = `
        <div class="modal fade" id="item-details-modal" tabindex="-1" aria-labelledby="item-details-modal-label" aria-hidden="true">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title" id="item-details-modal-label">
                            <i class="bi bi-eye"></i> Item Details
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <!-- Content will be populated by JavaScript -->
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        <button type="button" class="btn btn-outline-warning" id="view-history-from-details-btn">
                            <i class="bi bi-clock-history"></i> View History
                        </button>
                        <a href="#" class="btn btn-primary" id="edit-item-link">
                            <i class="bi bi-pencil"></i> Edit Item
                        </a>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    return document.getElementById('item-details-modal');
}

function createItemDetailsHTML(item) {
    const dimensions = item.formatted_dimensions || {};
    const thread = item.thread || {};
    
    // Update modal title
    document.getElementById('item-details-modal-label').innerHTML = `
        <i class="bi bi-eye"></i> ${item.ja_id} Details
    `;
    
    // Update edit link
    document.getElementById('edit-item-link').href = `/inventory/edit/${item.ja_id}`;
    
    // Update history button
    const historyBtn = document.getElementById('view-history-from-details-btn');
    if (historyBtn) {
        historyBtn.onclick = () => {
            console.log('History button clicked for item:', item.ja_id);
            console.log('showItemHistory function available:', typeof window.showItemHistory);
            
            // Close the details modal first
            const detailsModal = bootstrap.Modal.getInstance(document.getElementById('item-details-modal'));
            if (detailsModal) {
                detailsModal.hide();
            }
            
            // Show history modal
            if (typeof window.showItemHistory === 'function') {
                window.showItemHistory(item.ja_id);
            } else {
                console.error('showItemHistory function not available');
            }
        };
    } else {
        console.warn('History button not found in modal footer');
    }
    
    return `
        <div class="row">
            <div class="col-md-6">
                <h6 class="text-muted mb-3">Basic Information</h6>
                <table class="table table-sm">
                    <tr>
                        <td><strong>JA ID:</strong></td>
                        <td>${item.ja_id}</td>
                    </tr>
                    <tr>
                        <td><strong>Type:</strong></td>
                        <td><span class="badge bg-secondary">${item.item_type}</span></td>
                    </tr>
                    <tr>
                        <td><strong>Shape:</strong></td>
                        <td>${item.shape}</td>
                    </tr>
                    <tr>
                        <td><strong>Material:</strong></td>
                        <td>${item.material}</td>
                    </tr>
                    <tr>
                        <td><strong>Status:</strong></td>
                        <td><span class="badge ${item.active ? 'bg-success' : 'bg-secondary'}">${item.active ? 'Active' : 'Inactive'}</span></td>
                    </tr>
                    <tr>
                        <td><strong>Precision:</strong></td>
                        <td><span class="badge ${item.precision ? 'bg-primary' : 'bg-secondary'}">${item.precision ? 'Yes' : 'No'}</span></td>
                    </tr>
                </table>
                
                ${Object.keys(dimensions).length > 0 ? `
                <h6 class="text-muted mb-3 mt-4">Dimensions</h6>
                <table class="table table-sm">
                    ${dimensions.length ? `<tr><td><strong>Length:</strong></td><td>${dimensions.length}</td></tr>` : ''}
                    ${dimensions.width ? `<tr><td><strong>Width/Diameter:</strong></td><td>${dimensions.width}</td></tr>` : ''}
                    ${dimensions.thickness ? `<tr><td><strong>Thickness:</strong></td><td>${dimensions.thickness}</td></tr>` : ''}
                    ${dimensions.wall_thickness ? `<tr><td><strong>Wall Thickness:</strong></td><td>${dimensions.wall_thickness}</td></tr>` : ''}
                    ${dimensions.weight ? `<tr><td><strong>Weight:</strong></td><td>${dimensions.weight}</td></tr>` : ''}
                </table>
                ` : ''}
                
                ${thread.size || thread.series || thread.handedness ? `
                <h6 class="text-muted mb-3 mt-4">Threading</h6>
                <table class="table table-sm">
                    ${thread.size ? `<tr><td><strong>Size:</strong></td><td>${thread.size}</td></tr>` : ''}
                    ${thread.series ? `<tr><td><strong>Series:</strong></td><td>${thread.series}</td></tr>` : ''}
                    ${thread.handedness ? `<tr><td><strong>Handedness:</strong></td><td>${thread.handedness}</td></tr>` : ''}
                </table>
                ` : ''}
            </div>
            <div class="col-md-6">
                <!-- Photos Section -->
                <h6 class="text-muted mb-3">Photos</h6>
                <div id="item-details-photos" class="mb-4">
                    <!-- Photos will be loaded here -->
                </div>
                <h6 class="text-muted mb-3">Location & Purchase</h6>
                <table class="table table-sm">
                    <tr>
                        <td><strong>Location:</strong></td>
                        <td>${item.location || '<span class="text-muted">Not specified</span>'}</td>
                    </tr>
                    <tr>
                        <td><strong>Sub-location:</strong></td>
                        <td>${item.sub_location || '<span class="text-muted">Not specified</span>'}</td>
                    </tr>
                    <tr>
                        <td><strong>Purchase Date:</strong></td>
                        <td>${item.purchase_date ? new Date(item.purchase_date).toLocaleDateString() : '<span class="text-muted">Not specified</span>'}</td>
                    </tr>
                    <tr>
                        <td><strong>Purchase Price:</strong></td>
                        <td>${item.purchase_price ? '$' + item.purchase_price : '<span class="text-muted">Not specified</span>'}</td>
                    </tr>
                    <tr>
                        <td><strong>Purchase Location:</strong></td>
                        <td>${item.purchase_location || '<span class="text-muted">Not specified</span>'}</td>
                    </tr>
                    <tr>
                        <td><strong>Vendor:</strong></td>
                        <td>${item.vendor || '<span class="text-muted">Not specified</span>'}</td>
                    </tr>
                    <tr>
                        <td><strong>Vendor Part #:</strong></td>
                        <td>${item.vendor_part_number || '<span class="text-muted">Not specified</span>'}</td>
                    </tr>
                </table>
                
                ${item.notes ? `
                <h6 class="text-muted mb-3 mt-4">Notes</h6>
                <div class="border p-3 bg-light rounded">
                    ${item.notes}
                </div>
                ` : ''}
                
                <h6 class="text-muted mb-3 mt-4">System Information</h6>
                <table class="table table-sm">
                    <tr>
                        <td><strong>Date Added:</strong></td>
                        <td>${new Date(item.date_added).toLocaleDateString()}</td>
                    </tr>
                    <tr>
                        <td><strong>Last Modified:</strong></td>
                        <td>${new Date(item.last_modified).toLocaleDateString()}</td>
                    </tr>
                    ${item.parent_ja_id ? `<tr><td><strong>Parent Item:</strong></td><td>${item.parent_ja_id}</td></tr>` : ''}
                    ${item.child_ja_ids && item.child_ja_ids.length > 0 ? `<tr><td><strong>Child Items:</strong></td><td>${item.child_ja_ids.join(', ')}</td></tr>` : ''}
                </table>
            </div>
        </div>
    `;
}

// Initialize photo manager for item details modal (read-only)
function initializeItemDetailsPhotoManager(jaId) {
    window.itemDetailsPhotoManager = window.initializeReadOnlyPhotoManager('#item-details-photos', jaId);
}

window.duplicateItem = function(jaId) {
    if (confirm(`Create a duplicate of item ${jaId}?`)) {
        alert(`Duplicate feature coming soon for ${jaId}!`);
    }
};

// Expose toggleItemStatus to global scope for onclick handlers
window.toggleItemStatus = toggleItemStatus;

// Backwards compatibility alias
window.viewItemDetails = function(jaId) {
    window.showItemDetails(jaId);
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.listManager = new InventoryListManager();
});