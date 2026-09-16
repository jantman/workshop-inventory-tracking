/**
 * Row selection and bulk label printing on the products list.
 *
 * The dialog itself is shared with the inventory list -- see
 * bulk-label-print.js. What is here is the selection, and the one thing that
 * differs about printing a product: it posts to the per-product label endpoint
 * that the product detail page already uses, so a label printed from this list
 * is the same label, composed by the same code from the same record.
 */

(function () {
    'use strict';

    class ProductListSelection {
        constructor() {
            this.table = document.getElementById('product-table');
            this.selectAll = document.getElementById('product-select-all');
            this.printBtn = document.getElementById('product-print-labels-btn');
            this.countBadge = document.getElementById('product-selected-count');

            this.dialog = new BulkLabelPrintDialog({
                modalId: 'productBulkLabelPrintingModal',
                prefix: 'product-bulk',
                noun: 'product',
                nounPlural: 'products',
                printOne: (entry, labelType, labelCount) =>
                    // csrfFetch, not fetch: unlike the item label endpoint this
                    // one is not @csrf.exempt. base.html loads csrf.js on every
                    // page, so nothing else is needed for it.
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

            this.checkboxes().forEach(cb => {
                cb.addEventListener('change', () => this.onSelectionChange());
            });

            if (this.selectAll) {
                this.selectAll.addEventListener('change', () => {
                    const checked = this.selectAll.checked;
                    this.checkboxes().forEach(cb => { cb.checked = checked; });
                    this.onSelectionChange();
                });
            }

            if (this.printBtn) {
                this.printBtn.addEventListener('click', () => {
                    this.dialog.open(this.selectedEntries());
                });
            }

            this.onSelectionChange();
        }

        checkboxes() {
            return Array.from(this.table.querySelectorAll('input.product-checkbox'));
        }

        /**
         * The selection, read from the page at the moment it is wanted rather
         * than tracked in a Set.
         *
         * This is what keeps the selection scoped to what the list shows. The
         * table is server-rendered, so a product filtered out of the results
         * has no checkbox on the page at all and therefore cannot be selected,
         * counted, or printed. A Set held here would have to be explicitly
         * cleared to get the same guarantee, and would be wrong until it was.
         */
        selectedEntries() {
            return this.checkboxes()
                .filter(cb => cb.checked)
                .map(cb => ({
                    id: cb.dataset.productId,
                    label: cb.dataset.productLabel
                }));
        }

        onSelectionChange() {
            const boxes = this.checkboxes();
            const selected = boxes.filter(cb => cb.checked).length;

            if (this.countBadge) {
                this.countBadge.textContent = String(selected);
            }
            if (this.printBtn) {
                this.printBtn.disabled = selected === 0;
            }
            if (this.selectAll) {
                // Three states, not two. `indeterminate` is a property rather
                // than an attribute, so it has to be set rather than toggled in
                // the markup.
                this.selectAll.checked = boxes.length > 0 && selected === boxes.length;
                this.selectAll.indeterminate = selected > 0 && selected < boxes.length;
            }
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        // The catalog has other tables; only the list page carries this one
        // together with the dialog.
        if (document.getElementById('product-table') &&
                document.getElementById('productBulkLabelPrintingModal')) {
            new ProductListSelection().init();
        }
    });
})();
