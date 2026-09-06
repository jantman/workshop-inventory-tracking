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

            const set = document.getElementById('quantity-set-btn');
            if (set) {
                set.addEventListener('click', () => this.setTypedQuantity());
            }

            const start = document.getElementById('start-tracking-btn');
            if (start) {
                start.addEventListener('click', () => this.startCountingAtTypedQuantity());
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

        /**
         * Read the typed count, or say why it cannot be read.
         *
         * Returns one of {value: <int>}, {empty: true}, or {error: <message>}.
         * It never yields '' as a value to send, and that is the point: the
         * service reads an empty quantity as "stop counting", because the
         * product form posts '' for a field the operator left blank and there
         * that is exactly right. An empty box here is saying nothing yet, which
         * is a different thing, and this is the only place the two are
         * distinguishable.
         */
        readEntry() {
            const input = document.getElementById('quantity-input');
            const raw = input ? input.value.trim() : '';

            if (raw === '') {
                return { empty: true };
            }
            if (/^-\d+$/.test(raw)) {
                return { error: 'A count cannot be negative' };
            }
            if (!/^\d+$/.test(raw)) {
                return { error: 'The count must be a whole number' };
            }
            return { value: parseInt(raw, 10) };
        }

        /**
         * Commit the typed count on a product already being counted.
         *
         * Committing an unchanged number is not a no-op: it re-stamps the
         * count's date, which is the operator saying they have just looked
         * again. That is what an age on a count means (FR-003).
         */
        setTypedQuantity() {
            const entry = this.readEntry();

            if (entry.error) {
                this.showAlert(entry.error);
            } else if (entry.empty) {
                this.showAlert(
                    'Type a count to set. To stop counting this, use "Stop counting this".'
                );
            } else {
                this.setQuantity(entry.value);
            }
        }

        /**
         * Begin counting, at the typed number if there is one.
         *
         * An untouched field is the absence of an entry rather than an entry of
         * nothing, so it starts the count at zero exactly as this button did
         * before there was a field to type in (FR-004). The Set button refuses
         * that same emptiness, because its label promises a count -- the button
         * the operator pressed is what says which one this is.
         */
        startCountingAtTypedQuantity() {
            const entry = this.readEntry();

            if (entry.error) {
                this.showAlert(entry.error);
            } else {
                this.setQuantity(entry.empty ? 0 : entry.value);
            }
        }

        setQuantity(quantity) {
            this.patch(`/api/products/${this.productId}/quantity`, { quantity: quantity });
        }

        setStockStatus(status) {
            this.patch(`/api/products/${this.productId}/stock-status`, { stock_status: status });
        }

        patch(url, body) {
            csrfFetch(url, {
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
