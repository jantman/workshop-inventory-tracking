/**
 * Line selection, bulk label printing and the bulk receive button on an order
 * page (feature 060, issue #194).
 *
 * Receiving needs no script: the checkboxes belong to the receive form through
 * their `form` attribute, so it is a plain POST. What is here is the selection
 * state -- the select-all box, the count, and arming both buttons -- and the
 * label dialog, which is the shared one (bulk-label-print.js) posting to the
 * same per-product endpoint the products list uses.
 */

(function () {
    'use strict';

    class OrderLineSelection {
        constructor() {
            this.table = document.getElementById('order-lines');
            this.selectAll = document.getElementById('order-select-all');
            this.printBtn = document.getElementById('order-print-labels-btn');
            this.receiveBtn = document.getElementById('order-receive-btn');
            this.countBadge = document.getElementById('order-selected-count');
            this.categoryBtn = document.getElementById('bulk-category-btn');

            // Set Category (063) gives each ticked line's product the
            // category -- each product once, as for labels.
            this.categoryDialog = new BulkSetCategoryDialog({
                clearSelection: () => {
                    this.checkboxes().forEach(cb => { cb.checked = false; });
                    this.onSelectionChange();
                }
            });

            this.dialog = new BulkLabelPrintDialog({
                modalId: 'orderBulkLabelPrintingModal',
                prefix: 'order-bulk',
                noun: 'product',
                nounPlural: 'products',
                closeOnSuccess: true,
                printOne: (entry, labelType, labelCount) =>
                    csrfFetch(`/api/products/${entry.id}/label`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            label_type: labelType,
                            label_count: labelCount
                        })
                    })
            });
        }

        init() {
            this.dialog.init();
            this.categoryDialog.init();

            this.checkboxes().forEach(cb => {
                cb.addEventListener('change', () => this.onSelectionChange());
            });

            this.selectAll.addEventListener('change', () => {
                const checked = this.selectAll.checked;
                this.checkboxes().forEach(cb => { cb.checked = checked; });
                this.onSelectionChange();
            });

            this.printBtn.addEventListener('click', () => {
                this.dialog.open(this.selectedProducts());
            });

            this.categoryBtn.addEventListener('click', () => {
                this.categoryDialog.open(this.selectedProducts().map(e => e.id));
            });

            this.onSelectionChange();
        }

        checkboxes() {
            return Array.from(this.table.querySelectorAll('input.order-line-checkbox'));
        }

        /**
         * The ticked lines' products, each once.
         *
         * Two lines of one order can name the same product, and it wants one
         * label, not two. Read from the page when wanted, like the products
         * list does, rather than tracked.
         */
        selectedProducts() {
            const seen = new Set();
            const entries = [];
            this.checkboxes().filter(cb => cb.checked).forEach(cb => {
                const id = cb.dataset.productId;
                if (!seen.has(id)) {
                    seen.add(id);
                    entries.push({ id: id, label: cb.dataset.productLabel });
                }
            });
            return entries;
        }

        onSelectionChange() {
            const boxes = this.checkboxes();
            const selected = boxes.filter(cb => cb.checked).length;

            this.countBadge.textContent = String(selected);
            this.printBtn.disabled = selected === 0;
            this.receiveBtn.disabled = selected === 0;
            this.categoryBtn.disabled = selected === 0;
            // `indeterminate` is a property, not an attribute.
            this.selectAll.checked = boxes.length > 0 && selected === boxes.length;
            this.selectAll.indeterminate = selected > 0 && selected < boxes.length;
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (document.getElementById('order-lines') &&
                document.getElementById('orderBulkLabelPrintingModal')) {
            new OrderLineSelection().init();
        }
    });
})();
