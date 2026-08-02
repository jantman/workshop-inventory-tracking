/**
 * Stock controls on the product detail view.
 *
 * Every action here is a button (FR-036, SC-010): the workshop cart is one
 * thing, but a handheld with no keyboard is the other, and a control that needs
 * a keyboard is a control that does not exist on that device.
 *
 * The three quantity states are all reachable -- a count, zero, and "not
 * tracked" -- because a UI that can only express two of them makes SC-007
 * impossible no matter what the database stores.
 */

(function () {
    'use strict';

    class StockControls {
        constructor(card) {
            this.card = card;
            this.productId = card.dataset.productId;
            this.alerts = document.getElementById('stock-alerts');
        }

        init() {
            ['quantity-decrement', 'quantity-increment'].forEach((id) => {
                const button = document.getElementById(id);
                if (button) {
                    button.addEventListener('click', () => this.step(parseInt(button.dataset.step, 10)));
                }
            });

            const start = document.getElementById('start-tracking-btn');
            if (start) {
                start.addEventListener('click', () => this.setQuantity(0));
            }

            const stop = document.getElementById('stop-tracking-btn');
            if (stop) {
                // An explicit null, which is a different request from omitting
                // the field: it means "stop counting", not "leave it alone".
                stop.addEventListener('click', () => this.setQuantity(null));
            }

            this.card.querySelectorAll('.stock-status-btn').forEach((button) => {
                button.addEventListener('click', () => {
                    this.setStockStatus(button.dataset.status || null);
                });
            });
        }

        currentQuantity() {
            const text = document.getElementById('quantity-value').innerText.trim();
            const parsed = parseInt(text, 10);
            return Number.isNaN(parsed) ? 0 : parsed;
        }

        step(delta) {
            this.setQuantity(Math.max(0, this.currentQuantity() + delta));
        }

        setQuantity(quantity) {
            this.patch(`/api/products/${this.productId}/quantity`, { quantity: quantity });
        }

        setStockStatus(status) {
            this.patch(`/api/products/${this.productId}/stock-status`, { stock_status: status });
        }

        patch(url, body) {
            fetch(url, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            })
                .then((response) => response.json())
                .then((data) => {
                    if (data.success) {
                        // Re-render from the server rather than patching the DOM
                        // in two places: the age line and the badge both change.
                        window.location.reload();
                    } else {
                        this.showAlert(data.error || 'That did not work');
                    }
                })
                .catch((error) => this.showAlert(String(error)));
        }

        showAlert(message) {
            this.alerts.innerHTML =
                `<div class="alert alert-danger" id="stock-alert">${message}</div>`;
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const card = document.getElementById('stock-card');
        if (card) {
            new StockControls(card).init();
        }
    });
})();
