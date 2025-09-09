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
            case 'display_name':
                return item.display_name;
            case 'item_type':
                return item.item_type;
            case 'material':
                return item.material;
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
                ${this.formatItemDisplay(item)}
            </td>
            <td>
                <span class="badge bg-secondary">${item.item_type}</span>
            </td>
            <td>${item.material}</td>
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
    
    formatItemDisplay(item) {
        const isThreadedRod = item.item_type === 'Threaded Rod';
        
        if (isThreadedRod && item.thread) {
            // For threaded rod: show "Material Threaded Rod Round 🔩M10x1.5 x 18""
            const threadDisplay = this.formatThread(item.thread, true); // true for display with symbol
            const length = item.dimensions?.length ? ` x ${item.dimensions.length}"` : '';
            return `<div class="fw-bold">${item.material} ${item.item_type} ${item.shape} ${threadDisplay}${length}</div>`;
        } else {
            // For other items: show traditional layout with shape on separate line
            const threadInfo = item.thread ? `<br><small class="text-info"><i class="bi bi-gear"></i> ${this.formatThread(item.thread, false)}</small>` : '';
            return `<div class="fw-bold">${item.display_name}</div><small class="text-muted">${item.shape}</small>${threadInfo}`;
        }
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
    alert(`Show details for ${jaId} - Feature coming soon!`);
};

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