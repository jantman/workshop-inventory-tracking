/**
 * Product label printing.
 *
 * Follows the pattern the JA-ID label modal already established: fetch the
 * stocks from the existing GET /api/labels/types endpoint, remember the last
 * chosen stock in localStorage, and post the choice.
 *
 * All six stocks are offered (FR-037). Nothing is composed here -- the server
 * composes from the stored record every time, so a reprint after an edited
 * description reflects the edit (FR-013).
 */

(function () {
    'use strict';

    const STORAGE_KEY = 'labelPrintingModal.selectedLabelType';

    class ProductLabelModal {
        constructor(button) {
            this.button = button;
            this.productId = button.dataset.productId;
            this.select = document.getElementById('product-label-type-select');
            this.count = document.getElementById('product-label-count');
            this.confirm = document.getElementById('product-label-print-confirm');
            this.alerts = document.getElementById('product-label-alerts');
            this.modalEl = document.getElementById('product-label-modal');
        }

        init() {
            this.button.addEventListener('click', () => this.open());
            this.confirm.addEventListener('click', () => this.print());
        }

        open() {
            this.alerts.innerHTML = '';
            // The stock is remembered across opens; the count deliberately is
            // not. The modal is one static node reused every time it is shown,
            // so the markup's value="1" only ever applies on the first open --
            // without this line a job of 20 would still read 20 the next time
            // the dialog opened, and print 20. The three sibling print dialogs
            // reset theirs for the same reason.
            this.count.value = '1';
            this.loadLabelTypes().then(() => {
                new bootstrap.Modal(this.modalEl).show();
            });
        }

        loadLabelTypes() {
            if (this.select.options.length > 1) {
                return Promise.resolve();
            }

            return fetch('/api/labels/types')
                .then((response) => response.json())
                .then((data) => {
                    if (!data.success) {
                        throw new Error(data.error || 'Could not load label types');
                    }
                    const remembered = localStorage.getItem(STORAGE_KEY);
                    data.label_types.forEach((name) => {
                        const option = document.createElement('option');
                        option.value = name;
                        option.textContent = name;
                        if (name === remembered) {
                            option.selected = true;
                        }
                        this.select.appendChild(option);
                    });
                })
                .catch((error) => {
                    this.showAlert('danger', error.message);
                });
        }

        print() {
            const labelType = this.select.value;
            if (!labelType) {
                this.showAlert('warning', 'Choose a label stock first.');
                return;
            }

            // The shared reader, not a fourth hand-rolled one: the bounds and
            // the wording when a count is refused have to agree across the
            // print dialogs, which is why label-count.js exists. Its own
            // docstring already counted this dialog as the fourth.
            //
            // The gate is here rather than in the browser's constraint
            // validation because the print button is type="button", for which
            // constraint validation never fires. The route validates again --
            // min/max on the input bounds the spinner, not what can be typed.
            const countResult = window.readLabelCount('product-label-count');
            if (!countResult.ok) {
                this.showAlert('warning', countResult.error);
                return;
            }

            try {
                localStorage.setItem(STORAGE_KEY, labelType);
            } catch (e) {
                /* remembering the choice is a convenience, not a requirement */
            }

            this.confirm.disabled = true;
            csrfFetch(`/api/products/${this.productId}/label`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    label_type: labelType,
                    label_count: countResult.value
                })
            })
                .then((response) => response.json())
                .then((data) => {
                    this.confirm.disabled = false;
                    if (data.success) {
                        this.showAlert('success', data.message);
                    } else {
                        this.showAlert('danger', data.error || 'Printing failed');
                    }
                })
                .catch((error) => {
                    this.confirm.disabled = false;
                    this.showAlert('danger', String(error));
                });
        }

        showAlert(kind, message) {
            this.alerts.innerHTML =
                `<div class="alert alert-${kind}" id="product-label-alert">${message}</div>`;
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const button = document.getElementById('print-product-label-btn');
        if (button) {
            new ProductLabelModal(button).init();
        }
    });
})();
