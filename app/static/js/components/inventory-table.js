/**
 * Inventory Table Component
 *
 * Shared table component for displaying, sorting, paginating, and selecting
 * inventory items. Used by both inventory list and advanced search pages.
 */

import {
    formatFullDimensions,
    formatDimensions,
    escapeHtml
} from './item-formatters.js';

/**
 * InventoryTable - Configurable table component for inventory items
 */
export class InventoryTable {
    /**
     * Create an InventoryTable instance
     *
     * @param {Object} config - Configuration options
     * @param {string} config.tableBodyId - ID of the tbody element to populate
     * @param {boolean} config.enableSelection - Show checkboxes for item selection
     * @param {boolean} config.enableSorting - Enable column sorting
     * @param {boolean} config.showSubLocation - Show sub-location column
     * @param {number} config.itemsPerPage - Number of items per page (default: 25)
     * @param {Function} config.onSelectionChange - Callback when selection changes
     * @param {Function} config.onActionClick - Callback when action button clicked
     * @param {Array<string>} config.actions - Available actions for items
     */
    constructor(config) {
        this.config = {
            tableBodyId: config.tableBodyId,
            enableSelection: config.enableSelection || false,
            enableSorting: config.enableSorting || false,
            showSubLocation: config.showSubLocation !== undefined ? config.showSubLocation : true,
            itemsPerPage: config.itemsPerPage || 25,
            onSelectionChange: config.onSelectionChange || (() => {}),
            onActionClick: config.onActionClick || (() => {}),
            actions: config.actions || ['view-history', 'edit', 'shorten', 'move', 'duplicate', 'print-label']
        };

        this.items = [];
        this.currentPage = 1;
        this.sortField = 'ja_id';
        this.sortDirection = 'asc';
        this.selectedItems = new Set();

        this.tableBody = document.getElementById(this.config.tableBodyId);
        if (!this.tableBody) {
            throw new Error(`Table body element #${this.config.tableBodyId} not found`);
        }

        this.initializeEventListeners();
    }

    /**
     * Initialize event listeners for sorting
     */
    initializeEventListeners() {
        if (this.config.enableSorting) {
            const table = this.tableBody.closest('table');
            if (table) {
                const sortableHeaders = table.querySelectorAll('.sortable');
                sortableHeaders.forEach(header => {
                    header.style.cursor = 'pointer';
                    header.addEventListener('click', () => {
                        const field = header.dataset.sort;
                        if (field) {
                            this.sortBy(field);
                        }
                    });
                });
            }
        }
    }

    /**
     * Set items to display in the table
     *
     * @param {Array<Object>} items - Array of inventory item objects
     */
    setItems(items) {
        this.items = items || [];
        this.currentPage = 1;
        this.selectedItems.clear();
        this.render();
    }

    /**
     * Render the current page
     *
     * @param {number} pageNumber - Page number to render (optional, defaults to current page)
     */
    renderPage(pageNumber) {
        if (pageNumber !== undefined) {
            this.currentPage = pageNumber;
        }
        this.render();
    }

    /**
     * Sort table by field
     *
     * @param {string} field - Field name to sort by
     * @param {string} direction - Sort direction ('asc' or 'desc'), optional
     */
    sortBy(field, direction) {
        if (field === this.sortField && direction === undefined) {
            // Toggle direction if sorting by same field
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortField = field;
            this.sortDirection = direction || 'asc';
        }

        // Sort items array
        this.items.sort((a, b) => {
            let aVal = this.getSortValue(a, this.sortField);
            let bVal = this.getSortValue(b, this.sortField);

            // Handle null/undefined values
            if (aVal === null || aVal === undefined) aVal = '';
            if (bVal === null || bVal === undefined) bVal = '';

            // Numeric comparison for numbers
            if (typeof aVal === 'number' && typeof bVal === 'number') {
                return this.sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
            }

            // String comparison
            aVal = String(aVal).toLowerCase();
            bVal = String(bVal).toLowerCase();
            if (aVal < bVal) return this.sortDirection === 'asc' ? -1 : 1;
            if (aVal > bVal) return this.sortDirection === 'asc' ? 1 : -1;
            return 0;
        });

        this.updateSortIndicators();
        this.render();
    }

    /**
     * Get value from item for sorting
     *
     * @param {Object} item - Item object
     * @param {string} field - Field name
     * @returns {*} Value for sorting
     */
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
            case 'location':
                return item.location;
            case 'sub_location':
                return item.sub_location;
            case 'active':
                return item.active ? 1 : 0;
            case 'length':
                return item.dimensions?.length || 0;
            case 'dimensions':
                // Sort by length for dimensions column
                return item.dimensions?.length || 0;
            default:
                return item[field];
        }
    }

    /**
     * Update sort indicator icons
     */
    updateSortIndicators() {
        if (!this.config.enableSorting) return;

        const table = this.tableBody.closest('table');
        if (!table) return;

        const sortableHeaders = table.querySelectorAll('.sortable');
        sortableHeaders.forEach(header => {
            const icon = header.querySelector('.sort-icon');
            if (!icon) return;

            if (header.dataset.sort === this.sortField) {
                icon.className = `bi bi-chevron-${this.sortDirection === 'asc' ? 'up' : 'down'} sort-icon`;
            } else {
                icon.className = 'bi bi-chevron-expand sort-icon';
            }
        });
    }

    /**
     * Get array of selected item JA IDs
     *
     * @returns {Array<string>} Array of selected JA IDs
     */
    getSelectedItems() {
        return Array.from(this.selectedItems);
    }

    /**
     * Select all items on current page
     */
    selectAll() {
        const startIdx = (this.currentPage - 1) * this.config.itemsPerPage;
        const endIdx = Math.min(startIdx + this.config.itemsPerPage, this.items.length);
        const pageItems = this.items.slice(startIdx, endIdx);

        pageItems.forEach(item => {
            this.selectedItems.add(item.ja_id);
        });

        this.render();
        this.config.onSelectionChange(this.getSelectedItems());
    }

    /**
     * Deselect all items
     */
    selectNone() {
        this.selectedItems.clear();
        this.render();
        this.config.onSelectionChange(this.getSelectedItems());
    }

    /**
     * Refresh/re-render the current page
     */
    refresh() {
        this.render();
    }

    /**
     * Internal render method
     */
    render() {
        // Clear table body
        this.tableBody.innerHTML = '';

        // Calculate pagination
        const startIdx = (this.currentPage - 1) * this.config.itemsPerPage;
        const endIdx = Math.min(startIdx + this.config.itemsPerPage, this.items.length);
        const pageItems = this.items.slice(startIdx, endIdx);

        // Render rows
        pageItems.forEach(item => {
            const row = this.createRow(item);
            this.tableBody.appendChild(row);
        });

        // Update sort indicators
        this.updateSortIndicators();

        // Update pagination controls
        this.updatePaginationControls();
    }

    /**
     * Update pagination controls visibility and state
     */
    updatePaginationControls() {
        const paginationContainer = document.getElementById('pagination-container');
        if (!paginationContainer) return;

        const totalPages = Math.ceil(this.items.length / this.config.itemsPerPage);

        // Show pagination if more than one page
        if (totalPages > 1) {
            paginationContainer.classList.remove('d-none');
            this.renderPaginationButtons(totalPages);
        } else {
            paginationContainer.classList.add('d-none');
        }

        // Update item count display
        this.updateItemCountDisplay();
    }

    /**
     * Render pagination buttons
     *
     * @param {number} totalPages - Total number of pages
     */
    renderPaginationButtons(totalPages) {
        const pagination = document.getElementById('pagination');
        if (!pagination) return;

        let html = '';

        // Previous button
        const prevDisabled = this.currentPage === 1 ? 'disabled' : '';
        html += `<li class="page-item ${prevDisabled}">
            <a class="page-link" href="#" data-page="${this.currentPage - 1}">Previous</a>
        </li>`;

        // Page numbers (show max 5 pages)
        const startPage = Math.max(1, this.currentPage - 2);
        const endPage = Math.min(totalPages, startPage + 4);

        for (let i = startPage; i <= endPage; i++) {
            const active = i === this.currentPage ? 'active' : '';
            html += `<li class="page-item ${active}">
                <a class="page-link" href="#" data-page="${i}">${i}</a>
            </li>`;
        }

        // Next button
        const nextDisabled = this.currentPage === totalPages ? 'disabled' : '';
        html += `<li class="page-item ${nextDisabled}">
            <a class="page-link" href="#" data-page="${this.currentPage + 1}">Next</a>
        </li>`;

        pagination.innerHTML = html;

        // Attach click handlers
        pagination.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                if (!link.parentElement.classList.contains('disabled') &&
                    !link.parentElement.classList.contains('active')) {
                    const page = parseInt(link.dataset.page);
                    this.renderPage(page);
                }
            });
        });
    }

    /**
     * Update item count display
     */
    updateItemCountDisplay() {
        const itemsStart = document.getElementById('items-start');
        const itemsEnd = document.getElementById('items-end');
        const itemsTotal = document.getElementById('items-total');

        if (!itemsStart || !itemsEnd || !itemsTotal) return;

        const startIdx = (this.currentPage - 1) * this.config.itemsPerPage + 1;
        const endIdx = Math.min(this.currentPage * this.config.itemsPerPage, this.items.length);

        itemsStart.textContent = startIdx;
        itemsEnd.textContent = endIdx;
        itemsTotal.textContent = this.items.length;
    }

    /**
     * Create table row for an item
     *
     * @param {Object} item - Item object
     * @returns {HTMLElement} Table row element
     */
    createRow(item) {
        const row = document.createElement('tr');
        const isSelected = this.selectedItems.has(item.ja_id);

        if (isSelected) {
            row.classList.add('table-active');
        }

        // Build row HTML
        let html = '';

        // Selection checkbox column
        if (this.config.enableSelection) {
            html += `
                <td class="border-end">
                    <input type="checkbox" class="form-check-input item-checkbox"
                           data-ja-id="${item.ja_id}" ${isSelected ? 'checked' : ''}>
                </td>
            `;
        }

        // JA ID column
        html += `
            <td class="border-end">
                <strong>${item.ja_id}</strong>
                ${item.parent_ja_id ? `<br><small class="text-muted">Child of ${item.parent_ja_id}</small>` : ''}
                ${item.child_ja_ids && item.child_ja_ids.length > 0 ? `<br><small class="text-info">Has ${item.child_ja_ids.length} child(ren)</small>` : ''}
            </td>
        `;

        // Type, Shape, Material columns
        html += `
            <td><span class="badge bg-secondary">${item.item_type}</span></td>
            <td>${item.shape}</td>
            <td>${item.material}</td>
        `;

        // Dimensions column
        html += `<td>${formatFullDimensions(item.dimensions, item.item_type, item.thread)}</td>`;

        // Length column
        html += `<td class="text-end">${formatDimensions(item.dimensions, item.item_type)}</td>`;

        // Location column
        html += `<td>${item.location || '<span class="text-muted">Not specified</span>'}</td>`;

        // Sub-location column (separate column when enabled)
        if (this.config.showSubLocation) {
            html += `<td>${item.sub_location || ''}</td>`;
        }

        // Status column
        html += `
            <td class="text-center">
                <span class="badge ${item.active ? 'bg-success' : 'bg-secondary'}">
                    ${item.active ? 'Active' : 'Inactive'}
                </span>
            </td>
        `;

        // Actions column
        html += this.renderActions(item);

        row.innerHTML = html;

        // Attach selection event listener
        if (this.config.enableSelection) {
            const checkbox = row.querySelector('.item-checkbox');
            if (checkbox) {
                checkbox.addEventListener('change', (e) => {
                    if (e.target.checked) {
                        this.selectedItems.add(item.ja_id);
                        row.classList.add('table-active');
                    } else {
                        this.selectedItems.delete(item.ja_id);
                        row.classList.remove('table-active');
                    }
                    this.config.onSelectionChange(this.getSelectedItems());
                });
            }
        }

        return row;
    }

    /**
     * Render actions column HTML
     *
     * @param {Object} item - Item object
     * @returns {string} HTML for actions column
     */
    renderActions(item) {
        return `
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
    }
}
