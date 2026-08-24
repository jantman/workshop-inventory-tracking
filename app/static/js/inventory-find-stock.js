/*!
 * Find Stock for a Part
 *
 * Asks one question the advanced search cannot: given a piece the operator
 * needs, what on the shelves can it be cut out of? The results come back
 * already ordered by closeness of fit, and are handed to the same
 * InventoryTable component the inventory list and the advanced search use --
 * setItems() renders without sorting, which is what preserves the server's
 * order until the operator clicks a header (FR-029).
 */

import { InventoryTable } from './components/inventory-table.js';

// The form fields each requested shape reads, keyed by the name the API wants.
// The round shape's length lives under `round_length` because the rectangular
// shape already owns `length` and two inputs cannot share an id.
const SHAPE_FIELDS = {
    'Rectangular': { length: 'length', width: 'width', thickness: 'thickness' },
    'Round': { diameter: 'diameter', length: 'round_length' }
};

class FindStockSearch {
    constructor() {
        this.form = document.getElementById('find-stock-form');
        this.resultsSection = document.getElementById('find-stock-results-section');
        this.loadingElement = document.getElementById('find-stock-loading');
        this.errorElement = document.getElementById('find-stock-error');
        this.noResultsElement = document.getElementById('find-stock-no-results');
        this.tableContainer = document.getElementById('find-stock-table-container');
        this.countersElement = document.getElementById('find-stock-counters');
        this.shapeSelect = document.getElementById('piece_shape');
        this.rectangularFields = document.getElementById('rectangular-dimensions');
        this.roundFields = document.getElementById('round-dimensions');

        this.isSearching = false;
        this.selectedItems = [];

        this.table = new InventoryTable({
            tableBodyId: 'find-stock-table-body',
            enableSelection: true,
            enableSorting: true,
            showSubLocation: true,
            showFitColumn: true,
            itemsPerPage: 1000,
            onSelectionChange: (selectedIds) => { this.selectedItems = selectedIds; }
        });

        this.attachEventListeners();
        this.applyShape();
    }

    attachEventListeners() {
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.performSearch();
        });

        this.shapeSelect.addEventListener('change', () => this.applyShape());

        document.getElementById('clear-find-stock-btn').addEventListener('click', () => {
            this.form.reset();
            this.applyShape();
            this.resultsSection.classList.add('d-none');
        });
    }

    /** Show the dimension inputs the chosen shape needs, and hide the others. */
    applyShape() {
        const round = this.shapeSelect.value === 'Round';
        this.roundFields.classList.toggle('d-none', !round);
        this.rectangularFields.classList.toggle('d-none', round);
    }

    /**
     * Build the request payload.
     *
     * A blank tolerance means the dimension is exact, so it is left out of the
     * payload entirely rather than sent as a zero-ish string (FR-015).
     */
    collectRequest() {
        const shape = this.shapeSelect.value;
        const request = {
            material: document.getElementById('material').value.trim(),
            shape: shape
        };

        Object.entries(SHAPE_FIELDS[shape]).forEach(([key, fieldId]) => {
            const value = document.getElementById(fieldId).value.trim();
            if (value) {
                request[key] = value;
            }
            const tolerance = document.getElementById(`${fieldId}_tolerance`).value.trim();
            if (tolerance) {
                request[`${key}_tolerance`] = tolerance;
            }
        });

        return request;
    }

    async performSearch() {
        if (this.isSearching) return;

        this.isSearching = true;
        this.showLoading();

        try {
            const response = await fetch('/api/inventory/find-stock', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(this.collectRequest())
            });

            const data = await response.json();
            this.hideLoading();

            if (!data.success) {
                this.showRefusal(data.message || 'Search failed');
                return;
            }

            this.displayResults(data);
        } catch (error) {
            console.error('Find stock error:', error);
            this.hideLoading();
            this.showRefusal('Search failed. Please try again.');
        } finally {
            this.isSearching = false;
        }
    }

    displayResults(data) {
        this.errorElement.classList.add('d-none');
        this.renderCounters(data);

        const items = data.items || [];
        if (items.length === 0) {
            this.noResultsElement.classList.remove('d-none');
            this.tableContainer.classList.add('d-none');
            return;
        }

        this.noResultsElement.classList.add('d-none');
        this.tableContainer.classList.remove('d-none');
        this.table.setItems(items);
    }

    /**
     * Say what the search looked at, on every search.
     *
     * This is what makes an empty result trustworthy (FR-023, SC-006): with the
     * counts beside it, "nothing fits" is distinguishable from "you have none of
     * this material" and from "yours are recorded incompletely".
     */
    renderCounters(data) {
        const parts = [];
        const considered = data.considered || 0;
        const found = (data.items || []).length;

        parts.push(`${found} of ${considered} item${considered === 1 ? '' : 's'} considered can make it`);

        if (data.skipped_incomplete) {
            parts.push(`${data.skipped_incomplete} skipped for a missing dimension`);
        }
        if (data.skipped_hollow) {
            parts.push(`${data.skipped_hollow} skipped as hollow`);
        }

        this.countersElement.textContent = parts.join(' — ');
    }

    showLoading() {
        this.resultsSection.classList.remove('d-none');
        this.loadingElement.classList.remove('d-none');
        this.errorElement.classList.add('d-none');
        this.noResultsElement.classList.add('d-none');
        this.tableContainer.classList.add('d-none');
        this.countersElement.textContent = '';
    }

    hideLoading() {
        this.loadingElement.classList.add('d-none');
    }

    /** A request the search refused, with the message naming what was wrong. */
    showRefusal(message) {
        this.countersElement.textContent = '';
        this.noResultsElement.classList.add('d-none');
        this.tableContainer.classList.add('d-none');
        this.errorElement.textContent = message;
        this.errorElement.classList.remove('d-none');
    }

    getCSRFToken() {
        const token = document.querySelector('meta[name=csrf-token]');
        return token ? token.getAttribute('content') : '';
    }
}

// The shared table's rows carry a Details button. The list and search pages
// each build that modal for themselves; this page asks the list page's endpoint
// for the same record and shows it in a modal of its own.
window.showItemDetails = function(jaId) {
    if (typeof bootstrap === 'undefined') {
        console.error('Bootstrap is not loaded');
        return;
    }

    let element = document.getElementById('find-stock-details-modal');
    if (!element) {
        element = document.createElement('div');
        element.className = 'modal fade';
        element.id = 'find-stock-details-modal';
        element.tabIndex = -1;
        element.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="bi bi-eye"></i> Item Details</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body"></div>
                </div>
            </div>
        `;
        document.body.appendChild(element);
    }

    const body = element.querySelector('.modal-body');
    body.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div></div>';
    new bootstrap.Modal(element).show();

    fetch(`/inventory/view/${jaId}`)
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                body.innerHTML = `<div class="alert alert-danger">${data.error || 'Unable to load item details'}</div>`;
                return;
            }
            const item = data.item;
            const dimensions = item.formatted_dimensions || {};
            const rows = [
                ['JA ID', item.ja_id],
                ['Type', item.item_type],
                ['Shape', item.shape],
                ['Material', item.material],
                ['Length', dimensions.length],
                ['Width', dimensions.width],
                ['Thickness', dimensions.thickness],
                ['Diameter', dimensions.diameter],
                ['Location', item.location],
                ['Sub-location', item.sub_location],
                ['Notes', item.notes]
            ].filter(([, value]) => value);

            body.innerHTML = `<table class="table table-sm">${rows.map(
                ([label, value]) => `<tr><td><strong>${label}</strong></td><td>${value}</td></tr>`
            ).join('')}</table>
            <a href="/inventory/edit/${item.ja_id}" class="btn btn-primary btn-sm">
                <i class="bi bi-pencil"></i> Edit Item
            </a>`;
        })
        .catch(error => {
            console.error('Error fetching item details:', error);
            body.innerHTML = '<div class="alert alert-danger">Error loading item details.</div>';
        });
};

document.addEventListener('DOMContentLoaded', () => {
    new FindStockSearch();
});
