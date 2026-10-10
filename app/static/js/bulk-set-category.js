/**
 * The Set Category dialog (063, issue #201).
 *
 * Shared by the Products list, the order page and Outstanding Products. Like
 * BulkLabelPrintDialog, it owns the dialog and nothing else: each page's own
 * selection script arms the button and calls open() with the product ids
 * behind its ticked rows.
 *
 * A success reloads the page, which shows the flashed message and the fresh
 * values. The boxes are unticked first because some browsers restore checkbox
 * state across a reload -- unticking first is what makes the restored state
 * an empty selection. A failure leaves the dialog open and the selection
 * alone, so the owner can correct the category and try again.
 */

class BulkSetCategoryDialog {
    /**
     * @param {Object} options
     * @param {Function} options.clearSelection untick every row on the page
     */
    constructor(options) {
        this.clearSelection = options.clearSelection;
        this.productIds = [];
        this.modalElement = document.getElementById('bulkCategoryModal');
        this.input = document.getElementById('bulk-category-input');
        this.summary = document.getElementById('bulk-category-summary');
        this.error = document.getElementById('bulk-category-error');
        this.submitBtn = document.getElementById('bulk-category-submit');
    }

    init() {
        this.submitBtn.addEventListener('click', () => this.submit());
        this.input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                this.submit();
            }
        });
        // Focus once shown; focusing a hidden input does nothing.
        this.modalElement.addEventListener('shown.bs.modal', () => this.input.focus());
    }

    /** @param {Array<string|number>} productIds distinct product ids */
    open(productIds) {
        this.productIds = productIds.map(id => Number(id));
        const n = this.productIds.length;
        this.summary.textContent =
            `${n} product${n === 1 ? '' : 's'} will be given this category.`;
        this.input.value = '';
        this.hideError();
        this.submitBtn.disabled = false;
        bootstrap.Modal.getOrCreateInstance(this.modalElement).show();
    }

    showError(message) {
        this.error.textContent = message;
        this.error.classList.remove('d-none');
    }

    hideError() {
        this.error.textContent = '';
        this.error.classList.add('d-none');
    }

    async submit() {
        const category = this.input.value.trim();
        if (!category) {
            this.showError('Enter a category. Blank does not set one.');
            return;
        }

        this.hideError();
        this.submitBtn.disabled = true;
        try {
            const response = await csrfFetch('/api/products/category', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    product_ids: this.productIds,
                    category_path: category
                })
            });
            const data = await response.json().catch(() => ({}));
            if (response.ok && data.success) {
                this.clearSelection();
                window.location.reload();
                return;
            }
            this.showError(data.error || `Could not set the category (HTTP ${response.status}).`);
        } catch (error) {
            this.showError(`Could not set the category: ${error.message}`);
        }
        this.submitBtn.disabled = false;
    }
}
