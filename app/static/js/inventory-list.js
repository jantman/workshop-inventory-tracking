/**
 * Inventory List JavaScript - Inventory Listing Interface
 * 
 * Handles inventory display, filtering, sorting, and pagination
 * with advanced search capabilities and bulk operations.
 */

class InventoryListManager {
    constructor() {
        this.items = [];
        this.filteredItems = [];
        this.currentPage = 1;
        this.itemsPerPage = 25;
        this.sortField = 'ja_id';
        this.sortDirection = 'asc';
        this.filters = {
            status: 'active',
            type: 'all',
            material: '',
            search: ''
        };
        this.selectedItems = new Set();
        
        this.initializeElements();
        this.bindEvents();
        this.loadInventory();
        
        console.log('InventoryListManager initialized');
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
        this.itemsPerPageSelect = document.getElementById('items-per-page');
        
        // Selection elements
        this.selectAllCheckbox = document.getElementById('select-all-checkbox');
        this.selectAllBtn = document.getElementById('select-all-btn');
        this.selectNoneBtn = document.getElementById('select-none-btn');
        this.bulkMoveBtn = document.getElementById('bulk-move-btn');
        this.bulkDeactivateBtn = document.getElementById('bulk-deactivate-btn');
        this.bulkPrintLabelsBtn = document.getElementById('bulk-print-labels-btn');
        
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
        this.itemsPerPageSelect.addEventListener('change', () => this.onItemsPerPageChange());
        this.retryBtn.addEventListener('click', () => this.loadInventory());
        
        // Selection events
        this.selectAllCheckbox.addEventListener('change', (e) => this.toggleSelectAll(e.target.checked));
        this.selectAllBtn.addEventListener('click', () => this.selectAll());
        this.selectNoneBtn.addEventListener('click', () => this.selectNone());
        this.bulkMoveBtn.addEventListener('click', () => this.bulkMoveSelected());
        this.bulkDeactivateBtn.addEventListener('click', () => this.bulkDeactivateSelected());
        this.bulkPrintLabelsBtn.addEventListener('click', () => this.printLabelsForSelected());
        
        // Sorting events
        this.sortableHeaders.forEach(header => {
            header.addEventListener('click', () => this.onSort(header.dataset.sort));
        });
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
            this.applyFiltersAndSort();
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
        
        // Reset to first page when filters change
        this.currentPage = 1;
        
        // Apply filters and update display
        this.applyFiltersAndSort();
        this.renderTable();
        this.renderPagination();
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
    
    onItemsPerPageChange() {
        this.itemsPerPage = parseInt(this.itemsPerPageSelect.value);
        this.currentPage = 1;
        this.renderTable();
        this.renderPagination();
    }
    
    onSort(field) {
        if (this.sortField === field) {
            // Toggle direction if same field
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            // New field, default to ascending
            this.sortField = field;
            this.sortDirection = 'asc';
        }
        
        this.applyFiltersAndSort();
        this.renderTable();
        this.renderPagination();
        this.updateSortIcons();
    }
    
    applyFiltersAndSort() {
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
        
        // Apply sorting
        this.filteredItems.sort((a, b) => {
            let aVal = this.getSortValue(a, this.sortField);
            let bVal = this.getSortValue(b, this.sortField);
            
            // Handle null/undefined values
            if (aVal == null && bVal == null) return 0;
            if (aVal == null) return 1;
            if (bVal == null) return -1;
            
            // String comparison
            if (typeof aVal === 'string' && typeof bVal === 'string') {
                aVal = aVal.toLowerCase();
                bVal = bVal.toLowerCase();
            }
            
            // Numeric comparison
            if (typeof aVal === 'number' && typeof bVal === 'number') {
                return this.sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
            }
            
            // String comparison
            if (aVal < bVal) return this.sortDirection === 'asc' ? -1 : 1;
            if (aVal > bVal) return this.sortDirection === 'asc' ? 1 : -1;
            return 0;
        });
    }
    
    getSortValue(item, field) {
        switch (field) {
            case 'ja_id':
                return item.ja_id;
            case 'item_type':
                return item.item_type;
            case 'shape':
                return item.shape;
            case 'material':
                return item.material;
            case 'dimensions':
                // Sort by primary dimension (length if available, otherwise width)
                if (item.dimensions && item.dimensions.length) {
                    return parseFloat(item.dimensions.length);
                } else if (item.dimensions && item.dimensions.width) {
                    return parseFloat(item.dimensions.width);
                }
                return null;
            case 'length':
                return item.dimensions && item.dimensions.length ? parseFloat(item.dimensions.length) : null;
            case 'location':
                return item.location || '';
            case 'active':
                return item.active;
            default:
                return item[field] || '';
        }
    }
    
    renderTable() {
        const startIndex = (this.currentPage - 1) * this.itemsPerPage;
        const endIndex = startIndex + this.itemsPerPage;
        const pageItems = this.filteredItems.slice(startIndex, endIndex);
        
        this.inventoryTableBody.innerHTML = '';
        
        pageItems.forEach(item => {
            const row = this.createTableRow(item);
            this.inventoryTableBody.appendChild(row);
        });
        
        // Update selection state
        this.updateSelectAllCheckbox();
    }
    
    createTableRow(item) {
        const row = document.createElement('tr');
        const isSelected = this.selectedItems.has(item.ja_id);
        
        if (isSelected) {
            row.classList.add('table-active');
        }
        
        row.innerHTML = `
            <td class="border-end">
                <input type="checkbox" class="form-check-input item-checkbox" 
                       data-ja-id="${item.ja_id}" ${isSelected ? 'checked' : ''}>
            </td>
            <td class="border-end">
                <strong>${item.ja_id}</strong>
                ${item.parent_ja_id ? `<br><small class="text-muted">Child of ${item.parent_ja_id}</small>` : ''}
                ${item.child_ja_ids && item.child_ja_ids.length > 0 ? `<br><small class="text-info">Has ${item.child_ja_ids.length} child(ren)</small>` : ''}
            </td>
            <td>
                <span class="badge bg-secondary">${item.item_type}</span>
            </td>
            <td>${item.shape}</td>
            <td>${item.material}</td>
            <td>${this.formatFullDimensions(item.dimensions, item.item_type, item.thread)}</td>
            <td class="text-end">
                ${this.formatDimensions(item.dimensions, item.item_type)}
            </td>
            <td>
                <div>${item.location || '<span class="text-muted">Not specified</span>'}</div>
                ${item.sub_location ? `<small class="text-muted">${item.sub_location}</small>` : ''}
            </td>
            <td class="text-center">
                <span class="badge ${item.active ? 'bg-success' : 'bg-secondary'}">
                    ${item.active ? 'Active' : 'Inactive'}
                </span>
            </td>
            <td class="text-center">
                <div class="btn-group btn-group-sm">
                    <a href="/inventory/edit/${item.ja_id}" class="btn btn-outline-primary btn-sm" title="Edit">
                        <i class="bi bi-pencil"></i>
                    </a>
                    <button type="button" class="btn btn-outline-info btn-sm" onclick="showItemDetails('${item.ja_id}')" title="View Details">
                        <i class="bi bi-eye"></i>
                    </button>
                    <button type="button" class="btn btn-outline-warning btn-sm" onclick="showItemHistory('${item.ja_id}')" title="View History">
                        <i class="bi bi-clock-history"></i>
                    </button>
                    <div class="btn-group btn-group-sm">
                        <button type="button" class="btn btn-outline-secondary btn-sm dropdown-toggle dropdown-toggle-split" 
                                data-bs-toggle="dropdown"></button>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="/inventory/move?ja_id=${item.ja_id}">
                                <i class="bi bi-arrow-left-right"></i> Move
                            </a></li>
                            <li><a class="dropdown-item" href="/inventory/shorten?ja_id=${item.ja_id}">
                                <i class="bi bi-scissors"></i> Shorten
                            </a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item" href="#" onclick="duplicateItem('${item.ja_id}')">
                                <i class="bi bi-copy"></i> Duplicate
                            </a></li>
                            <li><a class="dropdown-item text-warning" href="#" onclick="toggleItemStatus('${item.ja_id}', ${!item.active})">
                                <i class="bi bi-${item.active ? 'eye-slash' : 'eye'}"></i> ${item.active ? 'Deactivate' : 'Activate'}
                            </a></li>
                        </ul>
                    </div>
                </div>
            </td>
        `;
        
        // Add click event for row selection
        const checkbox = row.querySelector('.item-checkbox');
        checkbox.addEventListener('change', (e) => {
            if (e.target.checked) {
                this.selectedItems.add(item.ja_id);
                row.classList.add('table-active');
            } else {
                this.selectedItems.delete(item.ja_id);
                row.classList.remove('table-active');
            }
            this.updateSelectAllCheckbox();
            this.updateBulkActions();
        });
        
        return row;
    }
    
    formatFullDimensions(dimensions, itemType, thread) {
        if (!dimensions) return '<span class="text-muted">-</span>';
        
        const parts = [];
        
        // For threaded items, show thread info first
        if (thread) {
            const threadDisplay = this.formatThread(thread, true); // true for display with symbol
            parts.push(threadDisplay);
        }
        
        // Then show physical dimensions
        if (dimensions.length) {
            if (dimensions.width && dimensions.thickness) {
                // Rectangular: width × thickness × length
                parts.push(`${dimensions.width}" × ${dimensions.thickness}" × ${dimensions.length}"`);
            } else if (dimensions.width) {
                // Round or Square: diameter/width × length
                const symbol = dimensions.width.toString().includes('⌀') ? '' : '⌀';
                parts.push(`${symbol}${dimensions.width}" × ${dimensions.length}"`);
            } else {
                // Just length
                parts.push(`${dimensions.length}"`);
            }
        }
        
        return parts.length > 0 ? parts.join(' ') : '<span class="text-muted">-</span>';
    }
    
    formatThread(thread, includeSymbol = false) {
        if (!thread) return '';
        const parts = [];
        if (thread.size) parts.push(thread.size);
        if (thread.series) parts.push(thread.series);
        if (thread.handedness && thread.handedness !== 'RH') parts.push(thread.handedness);
        
        const threadText = parts.join(' ');
        return includeSymbol && threadText ? `🔩${threadText}` : threadText;
    }
    
    formatDimensions(dimensions, itemType = null) {
        if (!dimensions) return '<span class="text-muted">-</span>';
        
        // The Length column should only show the length dimension
        if (dimensions.length) {
            return `${dimensions.length}"`;
        }
        
        return '<span class="text-muted">-</span>';
    }
    
    renderPagination() {
        const totalPages = Math.ceil(this.filteredItems.length / this.itemsPerPage);
        const startItem = Math.min((this.currentPage - 1) * this.itemsPerPage + 1, this.filteredItems.length);
        const endItem = Math.min(this.currentPage * this.itemsPerPage, this.filteredItems.length);
        
        // Update pagination info
        this.itemsStart.textContent = startItem;
        this.itemsEnd.textContent = endItem;
        this.itemsTotal.textContent = this.filteredItems.length;
        
        // Show/hide pagination
        if (this.filteredItems.length > 0) {
            this.paginationContainer.classList.remove('d-none');
        } else {
            this.paginationContainer.classList.add('d-none');
            return;
        }
        
        // Build pagination buttons
        this.pagination.innerHTML = '';
        
        // Previous button
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${this.currentPage === 1 ? 'disabled' : ''}`;
        prevLi.innerHTML = `<a class="page-link" href="#" onclick="window.listManager.goToPage(${this.currentPage - 1})">Previous</a>`;
        this.pagination.appendChild(prevLi);
        
        // Page numbers
        const maxVisiblePages = 5;
        let startPage = Math.max(1, this.currentPage - Math.floor(maxVisiblePages / 2));
        let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
        
        // Adjust start page if we're near the end
        if (endPage - startPage < maxVisiblePages - 1) {
            startPage = Math.max(1, endPage - maxVisiblePages + 1);
        }
        
        // Add first page and ellipsis if needed
        if (startPage > 1) {
            const firstLi = document.createElement('li');
            firstLi.className = 'page-item';
            firstLi.innerHTML = `<a class="page-link" href="#" onclick="window.listManager.goToPage(1)">1</a>`;
            this.pagination.appendChild(firstLi);
            
            if (startPage > 2) {
                const ellipsisLi = document.createElement('li');
                ellipsisLi.className = 'page-item disabled';
                ellipsisLi.innerHTML = '<span class="page-link">...</span>';
                this.pagination.appendChild(ellipsisLi);
            }
        }
        
        // Add visible page numbers
        for (let i = startPage; i <= endPage; i++) {
            const pageLi = document.createElement('li');
            pageLi.className = `page-item ${i === this.currentPage ? 'active' : ''}`;
            pageLi.innerHTML = `<a class="page-link" href="#" onclick="window.listManager.goToPage(${i})">${i}</a>`;
            this.pagination.appendChild(pageLi);
        }
        
        // Add last page and ellipsis if needed
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                const ellipsisLi = document.createElement('li');
                ellipsisLi.className = 'page-item disabled';
                ellipsisLi.innerHTML = '<span class="page-link">...</span>';
                this.pagination.appendChild(ellipsisLi);
            }
            
            const lastLi = document.createElement('li');
            lastLi.className = 'page-item';
            lastLi.innerHTML = `<a class="page-link" href="#" onclick="window.listManager.goToPage(${totalPages})">${totalPages}</a>`;
            this.pagination.appendChild(lastLi);
        }
        
        // Next button
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${this.currentPage === totalPages ? 'disabled' : ''}`;
        nextLi.innerHTML = `<a class="page-link" href="#" onclick="window.listManager.goToPage(${this.currentPage + 1})">Next</a>`;
        this.pagination.appendChild(nextLi);
    }
    
    goToPage(page) {
        const totalPages = Math.ceil(this.filteredItems.length / this.itemsPerPage);
        if (page >= 1 && page <= totalPages) {
            this.currentPage = page;
            this.renderTable();
            this.renderPagination();
        }
    }
    
    updateSortIcons() {
        this.sortableHeaders.forEach(header => {
            const icon = header.querySelector('.sort-icon');
            if (header.dataset.sort === this.sortField) {
                icon.className = `bi bi-chevron-${this.sortDirection === 'asc' ? 'up' : 'down'} sort-icon`;
                header.classList.add('text-primary');
            } else {
                icon.className = 'bi bi-chevron-expand sort-icon';
                header.classList.remove('text-primary');
            }
        });
    }
    
    toggleSelectAll(checked) {
        const pageItems = this.getVisibleItems();
        
        if (checked) {
            pageItems.forEach(item => this.selectedItems.add(item.ja_id));
        } else {
            pageItems.forEach(item => this.selectedItems.delete(item.ja_id));
        }
        
        this.renderTable();
        this.updateBulkActions();
    }
    
    selectAll() {
        this.filteredItems.forEach(item => this.selectedItems.add(item.ja_id));
        this.renderTable();
        this.updateSelectAllCheckbox();
        this.updateBulkActions();
    }
    
    selectNone() {
        this.selectedItems.clear();
        this.renderTable();
        this.updateSelectAllCheckbox();
        this.updateBulkActions();
    }
    
    getVisibleItems() {
        const startIndex = (this.currentPage - 1) * this.itemsPerPage;
        const endIndex = startIndex + this.itemsPerPage;
        return this.filteredItems.slice(startIndex, endIndex);
    }
    
    updateSelectAllCheckbox() {
        const visibleItems = this.getVisibleItems();
        const selectedVisibleItems = visibleItems.filter(item => this.selectedItems.has(item.ja_id));
        
        if (selectedVisibleItems.length === 0) {
            this.selectAllCheckbox.checked = false;
            this.selectAllCheckbox.indeterminate = false;
        } else if (selectedVisibleItems.length === visibleItems.length) {
            this.selectAllCheckbox.checked = true;
            this.selectAllCheckbox.indeterminate = false;
        } else {
            this.selectAllCheckbox.checked = false;
            this.selectAllCheckbox.indeterminate = true;
        }
    }
    
    updateBulkActions() {
        const hasSelection = this.selectedItems.size > 0;
        this.bulkMoveBtn.classList.toggle('disabled', !hasSelection);
        this.bulkDeactivateBtn.classList.toggle('disabled', !hasSelection);
    }
    
    bulkMoveSelected() {
        if (this.selectedItems.size === 0) return;
        
        const selectedIds = Array.from(this.selectedItems);
        const url = new URL('/inventory/move', window.location.origin);
        url.searchParams.set('items', selectedIds.join(','));
        window.location.href = url.toString();
    }
    
    bulkDeactivateSelected() {
        if (this.selectedItems.size === 0) return;

        const count = this.selectedItems.size;
        if (!confirm(`Are you sure you want to deactivate ${count} selected item(s)?`)) {
            return;
        }

        // Implementation would go here
        alert(`Bulk deactivate feature coming soon! Would deactivate ${count} items.`);
    }

    printLabelsForSelected() {
        if (this.selectedItems.size === 0) {
            alert('Please select at least one item to print labels.');
            return;
        }

        // Show the bulk label printing modal with selected items
        this.showBulkLabelPrintingModal();
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
            this.renderTable();
            this.renderPagination();
            this.updateSortIcons();
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

window.toggleItemStatus = function(jaId, activate) {
    const action = activate ? 'activate' : 'deactivate';
    if (confirm(`Are you sure you want to ${action} item ${jaId}?`)) {
        alert(`Toggle status feature coming soon for ${jaId}!`);
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.listManager = new InventoryListManager();
});