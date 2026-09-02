/**
 * Adding and removing a product's identifiers, from the detail page's card.
 *
 * Both endpoints this drives already existed and already enforced every rule --
 * check digits, the all-zero no-read, the vendor requirement, cross-product
 * duplicates. What was missing was a caller (#136), so nothing here re-states a
 * rule: it sends what was typed and renders what came back. A second copy of
 * those rules in the browser is a second place for them to be wrong.
 *
 * On success the page reloads, as the stock and attachment controls next door
 * do. That is not laziness -- the stored value is not always the typed one (a
 * UPC-A is stored as its 14-digit key), so re-rendering from the server is the
 * only version of "what you see is what is stored" that cannot drift.
 */

(function () {
    'use strict';

    /**
     * The message out of an error body, whichever shape it arrived in.
     *
     * There are two, and reading only one shows the operator "undefined" for the
     * other. A refusal the route itself produced carries `error`; one raised past
     * the route -- a product that does not exist -- is rendered by the central
     * handler in app/error_handlers.py, which calls the field `message`.
     */
    function messageFrom(data, fallback) {
        if (!data) {
            return fallback;
        }
        return data.error || data.message || fallback;
    }

    /**
     * Show a refusal. `message` is set as text rather than markup, because it
     * quotes back what the operator typed and a value containing "<" would
     * otherwise render as broken HTML instead of as itself.
     */
    function showAlert(message, ownerProductId) {
        const alerts = document.getElementById('identifier-alerts');
        if (!alerts) {
            return;
        }

        const box = document.createElement('div');
        box.className = 'alert alert-danger';
        box.id = 'identifier-alert';
        box.textContent = message;

        if (ownerProductId) {
            // FR-009: the operator is the one who resolves this, so give them
            // the way there rather than just the product's number.
            box.appendChild(document.createTextNode(' '));
            const link = document.createElement('a');
            link.href = `/products/${ownerProductId}`;
            link.textContent = 'Open that product';
            box.appendChild(link);
        }

        alerts.replaceChildren(box);
    }

    function clearAlert() {
        const alerts = document.getElementById('identifier-alerts');
        if (alerts) {
            alerts.replaceChildren();
        }
    }

    function saveIdentifier(productId) {
        const vendor = document.getElementById('new-identifier-vendor').value.trim();

        clearAlert();
        csrfFetch(`/api/products/${productId}/identifiers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id_type: document.getElementById('new-identifier-type').value,
                value: document.getElementById('new-identifier-value').value,
                vendor: vendor || null,
                override: document.getElementById('new-identifier-override').checked
            })
        })
            .then((response) => response.json().then((data) => ({ response, data })))
            .then(({ response, data }) => {
                if (response.ok) {
                    window.location.reload();
                    return;
                }
                // Deliberately no reload and no clearing of the inputs: a refusal
                // that discards what was typed makes the operator type it twice
                // (FR-011).
                showAlert(
                    messageFrom(data, 'Could not add that identifier'),
                    data && data.owning_product_id
                );
            })
            .catch((error) => showAlert(String(error)));
    }

    function removeIdentifier(productId, identifierId) {
        clearAlert();
        csrfFetch(`/api/products/${productId}/identifiers/${identifierId}`, {
            method: 'DELETE'
        })
            .then((response) => {
                // 404 is the identifier already being gone -- which is the state
                // that was asked for. A second tab is the realistic cause. Same
                // reasoning as product-attachments.js, and it is a live branch
                // rather than a lucky one only since #132 stopped this answering
                // a bodyless DELETE with a redirect to an HTML page.
                if (response.ok || response.status === 404) {
                    window.location.reload();
                    return null;
                }
                // Anything else is a real failure, and since #132 every /api/
                // failure says why in JSON. Flattening a rejected CSRF token and
                // a storage error into one generic line throws away the only
                // thing that tells them apart. The catch is for the case that
                // body is not JSON after all -- a proxy's error page, say.
                return response.json()
                    .catch(() => null)
                    .then((data) => showAlert(
                        messageFrom(data, 'Could not remove that identifier')
                    ));
            })
            .catch((error) => showAlert(String(error)));
    }

    function initProductIdentifiers() {
        const card = document.getElementById('identifiers-card');
        if (!card) {
            return;
        }

        const productId = card.dataset.productId;

        const save = document.getElementById('save-identifier-btn');
        if (save) {
            save.addEventListener('click', () => saveIdentifier(productId));
        }

        card.querySelectorAll('.remove-identifier-btn').forEach((button) => {
            button.addEventListener('click', () => {
                if (!window.confirm('Remove this identifier?')) {
                    return;
                }
                removeIdentifier(productId, button.dataset.identifierId);
            });
        });
    }

    document.addEventListener('DOMContentLoaded', initProductIdentifiers);
})();
