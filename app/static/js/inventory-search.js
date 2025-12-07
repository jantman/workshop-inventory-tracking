/*!
 * Advanced Inventory Search JavaScript
 * Handles complex search queries with range filtering and CSV export
 */

import {
    formatFullDimensions,
    formatDimensions,
    formatThread,
    escapeHtml
} from './components/item-formatters.js';
import { InventoryTable } from './components/inventory-table.js';

class AdvancedInventorySearch {
    constructor() {
        this.form = document.getElementById('advanced-search-form');
        this.resultsSection = document.getElementById('search-results-section');
        this.loadingElement = document.getElementById('search-loading');
        this.noResultsElement = document.getElementById('no-results');
        this.tableContainer = document.getElementById('results-table-container');
        this.resultsCount = document.getElementById('results-count');

        this.currentResults = [];
        this.isSearching = false;
        this.selectedItems = [];

        this.initializeTable();
        this.init();
    }

    initializeTable() {
        this.table = new InventoryTable({
            tableBodyId: 'results-table-body',
            enableSelection: true,
            enableSorting: true,
            showSubLocation: true,
            itemsPerPage: 1000, // Show all results in search
            onSelectionChange: (selectedIds) => this.onSelectionChange(selectedIds),
            onActionClick: (action, jaId) => this.onActionClick(action, jaId)
        });
    }
    
    init() {
        this.attachEventListeners();
        this.loadSearchFromURL();
    }
    
    attachEventListeners() {
        // Form submission
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.performSearch();
        });
        
        // Clear form button
        document.getElementById('clear-form-btn').addEventListener('click', () => {
            this.clearForm();
        });
        
        // Reset search button
        document.getElementById('reset-search-btn').addEventListener('click', () => {
            this.resetSearch();
        });
        
        // Export CSV button
        document.getElementById('export-csv-btn').addEventListener('click', () => {
            this.exportCSV();
        });
        
        // Bookmark search button
        document.getElementById('bookmark-search-btn').addEventListener('click', () => {
            this.bookmarkSearch();
        });

        // Bulk operation buttons
        document.getElementById('search-select-all-btn').addEventListener('click', (e) => {
            e.preventDefault();
            this.table.selectAll();
        });

        document.getElementById('search-select-none-btn').addEventListener('click', (e) => {
            e.preventDefault();
            this.table.selectNone();
        });

        document.getElementById('search-bulk-move-btn').addEventListener('click', (e) => {
            e.preventDefault();
            this.handleBulkMove();
        });

        document.getElementById('search-bulk-deactivate-btn').addEventListener('click', (e) => {
            e.preventDefault();
            this.handleBulkDeactivate();
        });

        document.getElementById('search-bulk-print-labels-btn').addEventListener('click', (e) => {
            e.preventDefault();
            this.handleBulkPrintLabels();
        });

        // Real-time validation for JA ID pattern
        const jaIdInput = document.getElementById('ja_id');
        jaIdInput.addEventListener('input', (e) => {
            this.validateJAID(e.target);
        });
        
        // Range validation for dimensions
        this.attachRangeValidation();
        
        // Auto-search on Enter in text fields
        const textInputs = this.form.querySelectorAll('input[type="text"], input[type="number"]');
        textInputs.forEach(input => {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.performSearch();
                }
            });
        });
    }
    
    attachRangeValidation() {
        // Pairs of min/max range inputs
        const rangePairs = [
            ['length_min', 'length_max'],
            ['width_min', 'width_max'],
            ['thickness_min', 'thickness_max'],
            ['wall_thickness_min', 'wall_thickness_max']
        ];
        
        rangePairs.forEach(([minId, maxId]) => {
            const minInput = document.getElementById(minId);
            const maxInput = document.getElementById(maxId);
            
            const validateRange = () => {
                const min = parseFloat(minInput.value) || 0;
                const max = parseFloat(maxInput.value) || Infinity;
                
                if (min > max && maxInput.value) {
                    maxInput.setCustomValidity('Maximum must be greater than minimum');
                } else {
                    maxInput.setCustomValidity('');
                }
                
                if (max < min && minInput.value) {
                    minInput.setCustomValidity('Minimum must be less than maximum');
                } else {
                    minInput.setCustomValidity('');
                }
            };
            
            minInput.addEventListener('input', validateRange);
            maxInput.addEventListener('input', validateRange);
        });
    }
    
    validateJAID(input) {
        const value = input.value;
        const pattern = /^JA\d{6}$/;
        
        if (value && !pattern.test(value)) {
            input.setCustomValidity('JA ID must be in format JA123456 (JA followed by 6 digits)');
        } else {
            input.setCustomValidity('');
        }
    }
    
    async performSearch() {
        if (this.isSearching) return;
        
        this.isSearching = true;
        this.showLoading();
        
        try {
            const searchData = this.collectSearchData();
            const results = await this.executeSearch(searchData);
            
            this.currentResults = results;
            this.displayResults(results);
            this.updateURL(searchData);
            
        } catch (error) {
            console.error('Search error:', error);
            this.showError('Search failed. Please try again.');
        } finally {
            this.isSearching = false;
        }
    }
    
    collectSearchData() {
        const formData = new FormData(this.form);
        const searchData = {};

        // Collect all form values
        for (let [key, value] of formData.entries()) {
            // Special handling for active field - include empty string to mean "all items"
            if (key === 'active') {
                searchData[key] = value.trim();
            } else if (value.trim()) {
                searchData[key] = value.trim();
            }
        }

        // Convert boolean strings for active field
        if (searchData.active && searchData.active !== '') {
            searchData.active = searchData.active === 'true';
        }
        // If active is empty string, leave it as empty string to mean "show all items"
        if (searchData.precision) {
            searchData.precision = searchData.precision === 'true';
        }
        if (searchData.material_exact) {
            searchData.material_exact = searchData.material_exact === 'true';
        }
        
        // Convert numeric values
        const numericFields = ['length_min', 'length_max', 'width_min', 'width_max', 
                              'thickness_min', 'thickness_max', 'wall_thickness_min', 'wall_thickness_max'];
        
        numericFields.forEach(field => {
            if (searchData[field]) {
                searchData[field] = parseFloat(searchData[field]);
            }
        });
        
        return searchData;
    }
    
    async executeSearch(searchData) {
        const response = await fetch('/api/inventory/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(searchData)
        });
        
        if (!response.ok) {
            throw new Error(`Search failed: ${response.statusText}`);
        }
        
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.message || 'Search failed');
        }

        return data.items || [];
    }
    
    displayResults(results) {
        this.hideLoading();

        if (results.length === 0) {
            this.showNoResults();
            return;
        }

        this.showResultsTable();
        this.table.setItems(results);
        this.updateResultsCount(results.length);
    }


    showLoading() {
        this.resultsSection.classList.remove('d-none');
        this.loadingElement.classList.remove('d-none');
        this.noResultsElement.classList.add('d-none');
        this.tableContainer.classList.add('d-none');
    }
    
    hideLoading() {
        this.loadingElement.classList.add('d-none');
    }
    
    showNoResults() {
        this.noResultsElement.classList.remove('d-none');
        this.tableContainer.classList.add('d-none');
    }
    
    showResultsTable() {
        this.noResultsElement.classList.add('d-none');
        this.tableContainer.classList.remove('d-none');
    }
    
    showError(message) {
        this.hideLoading();
        alert(`Error: ${message}`);
    }
    
    updateResultsCount(count) {
        const text = count === 1 ? '1 item found' : `${count} items found`;
        this.resultsCount.textContent = text;
    }

    onSelectionChange(selectedIds) {
        this.selectedItems = selectedIds;
    }

    onActionClick(action, jaId) {
        // Handle action clicks if needed
        console.log('Action clicked:', action, jaId);
    }

    handleBulkMove() {
        if (this.selectedItems.length === 0) {
            alert('Please select items to move');
            return;
        }

        const jaIds = this.selectedItems.join(',');
        window.location.href = `/inventory/move?ja_id=${jaIds}`;
    }

    handleBulkDeactivate() {
        if (this.selectedItems.length === 0) {
            alert('Please select items to deactivate');
            return;
        }

        if (!confirm(`Are you sure you want to deactivate ${this.selectedItems.length} item(s)?`)) {
            return;
        }

        // TODO: Implement bulk deactivate API call
        alert('Bulk deactivate functionality will be implemented');
    }

    handleBulkPrintLabels() {
        if (this.selectedItems.length === 0) {
            alert('Please select items to print labels for');
            return;
        }

        // Show the bulk label printing modal
        const modal = new bootstrap.Modal(document.getElementById('searchBulkLabelPrintingModal'));
        this.initializeBulkLabelPrinting();
        modal.show();
    }

    initializeBulkLabelPrinting() {
        // Populate the items list in the modal
        const itemsList = document.getElementById('search-bulk-label-items-list');
        itemsList.innerHTML = '';

        this.selectedItems.forEach(jaId => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.textContent = jaId;
            itemsList.appendChild(li);
        });

        // Update summary
        const summary = document.getElementById('search-bulk-print-summary');
        summary.textContent = `${this.selectedItems.length} item(s) selected for label printing`;

        // TODO: Load label types from API
        // TODO: Implement bulk print functionality
    }
    
    clearForm() {
        this.form.reset();
        
        // Clear custom validity messages
        const inputs = this.form.querySelectorAll('input, select');
        inputs.forEach(input => input.setCustomValidity(''));
        
        // Reset to defaults
        document.getElementById('active').value = 'true';
        document.getElementById('material_exact').value = 'false';
        
        // Clear results
        this.resultsSection.classList.add('d-none');
        this.currentResults = [];
        
        // Clear URL
        window.history.replaceState({}, '', window.location.pathname);
    }
    
    resetSearch() {
        this.clearForm();
    }
    
    exportCSV() {
        if (this.currentResults.length === 0) {
            alert('No results to export');
            return;
        }
        
        const csvData = this.generateCSV(this.currentResults);
        const blob = new Blob([csvData], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', `inventory-search-${new Date().toISOString().slice(0, 10)}.csv`);
        link.style.visibility = 'hidden';
        
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        // Show success message
        const exportBtn = document.getElementById('export-csv-btn');
        const originalContent = exportBtn.innerHTML;
        exportBtn.innerHTML = '<i class="bi bi-check"></i> Exported';
        exportBtn.disabled = true;
        
        setTimeout(() => {
            exportBtn.innerHTML = originalContent;
            exportBtn.disabled = false;
        }, 2000);
    }
    
    generateCSV(items) {
        // CSV headers
        const headers = [
            'JA ID', 'Item Type', 'Shape', 'Material', 'Length', 'Width', 
            'Thickness', 'Wall Thickness', 'Weight', 'Thread Size', 
            'Thread Series', 'Thread Form', 'Location', 'Notes', 'Status', 'Date Added'
        ];
        
        // Convert items to CSV rows
        const csvRows = [headers.join(',')];
        
        items.forEach(item => {
            const row = [
                this.csvEscape(item.ja_id),
                this.csvEscape(item.item_type),
                this.csvEscape(item.shape),
                this.csvEscape(item.material),
                item.dimensions?.length || '',
                item.dimensions?.width || '',
                item.dimensions?.thickness || '',
                item.dimensions?.wall_thickness || '',
                item.dimensions?.weight || '',
                this.csvEscape(item.thread?.size),
                this.csvEscape(item.thread?.series),
                this.csvEscape(item.thread?.form),
                this.csvEscape(item.location),
                this.csvEscape(item.notes),
                item.active ? 'Active' : 'Inactive',
                item.date_added || ''
            ];
            csvRows.push(row.join(','));
        });
        
        return csvRows.join('\n');
    }
    
    csvEscape(value) {
        if (!value) return '';
        
        const stringValue = String(value);
        if (stringValue.includes(',') || stringValue.includes('"') || stringValue.includes('\n')) {
            return `"${stringValue.replace(/"/g, '""')}"`;
        }
        return stringValue;
    }
    
    bookmarkSearch() {
        const url = window.location.href;
        
        // Copy URL to clipboard
        navigator.clipboard.writeText(url).then(() => {
            const bookmarkBtn = document.getElementById('bookmark-search-btn');
            const originalContent = bookmarkBtn.innerHTML;
            
            bookmarkBtn.innerHTML = '<i class="bi bi-check"></i> Copied';
            bookmarkBtn.disabled = true;
            
            setTimeout(() => {
                bookmarkBtn.innerHTML = originalContent;
                bookmarkBtn.disabled = false;
            }, 2000);
        }).catch(() => {
            // Fallback for browsers that don't support clipboard API
            prompt('Copy this URL to bookmark your search:', url);
        });
    }
    
    updateURL(searchData) {
        const url = new URL(window.location);
        url.search = '';
        
        // Add search parameters to URL
        Object.keys(searchData).forEach(key => {
            if (searchData[key] !== undefined && searchData[key] !== '') {
                url.searchParams.set(key, searchData[key]);
            }
        });
        
        window.history.replaceState({}, '', url);
    }
    
    loadSearchFromURL() {
        const urlParams = new URLSearchParams(window.location.search);
        let hasParams = false;
        
        // Load search parameters from URL
        urlParams.forEach((value, key) => {
            const input = document.getElementById(key) || document.querySelector(`[name="${key}"]`);
            if (input) {
                if (input.type === 'checkbox') {
                    input.checked = value === 'true';
                } else {
                    input.value = value;
                }
                hasParams = true;
            }
        });
        
        // Auto-execute search if parameters are present
        if (hasParams) {
            setTimeout(() => this.performSearch(), 100);
        }
    }
    
    getCSRFToken() {
        const token = document.querySelector('meta[name=csrf-token]');
        return token ? token.getAttribute('content') : '';
    }
}

// Global functions for row actions - Modal Implementation
window.showItemDetails = function(jaId) {
    // Check if modal element exists
    const modalElement = document.getElementById('item-details-modal');
    if (!modalElement) {
        console.error('Item details modal not found');
        return;
    }
    
    // Check if bootstrap is available
    if (typeof bootstrap === 'undefined') {
        console.error('Bootstrap is not loaded');
        return;
    }
    
    // Show loading state
    const modal = new bootstrap.Modal(modalElement);
    const modalBody = document.querySelector('#item-details-modal .modal-body');
    const editLink = document.getElementById('edit-item-link');
    
    modalBody.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-3">Loading item details...</p>
        </div>
    `;
    
    // Update edit link
    editLink.href = `/inventory/edit/${jaId}`;
    
    // Update history button
    const historyBtn = document.getElementById('view-history-from-details-btn');
    if (historyBtn) {
        historyBtn.onclick = () => {
            console.log('History button clicked for item:', jaId);
            console.log('showItemHistory function available:', typeof window.showItemHistory);
            
            // Close the details modal first
            modal.hide();
            
            // Show history modal
            if (typeof window.showItemHistory === 'function') {
                window.showItemHistory(jaId);
            } else {
                console.error('showItemHistory function not available');
            }
        };
    } else {
        console.warn('History button not found in search modal footer');
    }
    
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
}

function createItemDetailsHTML(item) {
    const dimensions = item.formatted_dimensions || {};
    const thread = item.thread || {};
    
    return `
        <div class="row">
            <div class="col-md-6">
                <h6 class="text-muted border-bottom pb-2">Basic Information</h6>
                <table class="table table-sm">
                    <tr><td><strong>JA ID:</strong></td><td>${item.ja_id}</td></tr>
                    <tr><td><strong>Type:</strong></td><td>${item.item_type || 'N/A'}</td></tr>
                    <tr><td><strong>Shape:</strong></td><td>${item.shape || 'N/A'}</td></tr>
                    <tr><td><strong>Material:</strong></td><td>${item.material || 'N/A'}</td></tr>
                    <tr><td><strong>Status:</strong></td><td>
                        ${item.active ? '<span class="badge bg-success">Active</span>' : '<span class="badge bg-secondary">Inactive</span>'}
                    </td></tr>
                    <tr><td><strong>Precision:</strong></td><td>
                        ${item.precision === true ? 'Yes' : ''}
                    </td></tr>
                </table>
            </div>
            <div class="col-md-6">
                <h6 class="text-muted border-bottom pb-2">Dimensions</h6>
                <table class="table table-sm">
                    ${(() => {
                        // Format thread info inline (similar to formatThread method)
                        if (!thread) return '';
                        const parts = [];
                        if (thread.size) parts.push(thread.size);
                        if (thread.series) parts.push(thread.series);
                        if (thread.handedness && thread.handedness !== 'RH') parts.push(thread.handedness);
                        const threadInfo = parts.join(' ');
                        return threadInfo ? `<tr><td><strong><i class="bi bi-nut"></i> Thread:</strong></td><td>${threadInfo}</td></tr>` : '';
                    })()}
                    ${dimensions.length ? `<tr><td><strong>Length:</strong></td><td>${dimensions.length}"</td></tr>` : ''}
                    ${dimensions.width ? `<tr><td><strong>Width:</strong></td><td>${dimensions.width}"</td></tr>` : ''}
                    ${dimensions.thickness ? `<tr><td><strong>Thickness:</strong></td><td>${dimensions.thickness}"</td></tr>` : ''}
                    ${dimensions.diameter ? `<tr><td><strong>Diameter:</strong></td><td>${dimensions.diameter}"</td></tr>` : ''}
                    ${dimensions.wall_thickness ? `<tr><td><strong>Wall Thickness:</strong></td><td>${dimensions.wall_thickness}"</td></tr>` : ''}
                    ${item.weight ? `<tr><td><strong>Weight:</strong></td><td>${item.weight} lbs</td></tr>` : ''}
                </table>
            </div>
        </div>
        <div class="row mt-3">
            <div class="col-md-6">
                <h6 class="text-muted border-bottom pb-2">Location</h6>
                <table class="table table-sm">
                    <tr><td><strong>Location:</strong></td><td>${item.location || 'N/A'}</td></tr>
                    <tr><td><strong>Sub-location:</strong></td><td>${item.sub_location || 'N/A'}</td></tr>
                </table>
            </div>
            <div class="col-md-6">
                <h6 class="text-muted border-bottom pb-2">Purchase Info</h6>
                <table class="table table-sm">
                    <tr><td><strong>Price:</strong></td><td>${item.purchase_price ? '$' + item.purchase_price : 'N/A'}</td></tr>
                    <tr><td><strong>Vendor:</strong></td><td>${item.vendor || 'N/A'}</td></tr>
                    <tr><td><strong>Date Added:</strong></td><td>${item.date_added ? new Date(item.date_added).toLocaleDateString() : 'N/A'}</td></tr>
                </table>
            </div>
        </div>
        ${item.notes ? `
            <div class="row mt-3">
                <div class="col-12">
                    <h6 class="text-muted border-bottom pb-2">Notes</h6>
                    <p class="text-muted">${item.notes}</p>
                </div>
            </div>
        ` : ''}
        ${thread.size ? `
            <div class="row mt-3">
                <div class="col-12">
                    <h6 class="text-muted border-bottom pb-2">Thread Information</h6>
                    <table class="table table-sm">
                        <tr><td><strong>Thread Size:</strong></td><td>${thread.size}</td></tr>
                        ${thread.series ? `<tr><td><strong>Series:</strong></td><td>${thread.series}</td></tr>` : ''}
                        ${thread.handedness ? `<tr><td><strong>Handedness:</strong></td><td>${thread.handedness}</td></tr>` : ''}
                        ${thread.form ? `<tr><td><strong>Form:</strong></td><td>${thread.form}</td></tr>` : ''}
                    </table>
                </div>
            </div>
        ` : ''}
        <div class="row mt-3">
            <div class="col-12">
                <h6 class="text-muted border-bottom pb-2">Photos</h6>
                <div id="item-details-photos">
                    <!-- Photos will be loaded here -->
                </div>
            </div>
        </div>
    `;
}

// Initialize photo manager for item details modal (read-only)
function initializeItemDetailsPhotoManager(jaId) {
    window.itemDetailsPhotoManager = window.initializeReadOnlyPhotoManager('#item-details-photos', jaId);
}

// Keep legacy function name for compatibility, but redirect to modal
window.viewItemDetails = function(jaId) {
    window.showItemDetails(jaId);
};

function editItem(jaId) {
    window.location.href = `/inventory/edit/${jaId}`;
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new AdvancedInventorySearch();
});