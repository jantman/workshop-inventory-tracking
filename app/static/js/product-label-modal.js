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

            try {
                localStorage.setItem(STORAGE_KEY, labelType);
            } catch (e) {
                /* remembering the choice is a convenience, not a requirement */
            }

            this.confirm.disabled = true;
            fetch(`/api/products/${this.productId}/label`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label_type: labelType })
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
