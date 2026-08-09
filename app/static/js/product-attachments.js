/**
 * Attachments on a product or a purchase (FR-034).
 *
 * Two owners, one upload path. A datasheet belongs to the product; a saved
 * listing or a receipt belongs to the purchase that captured it, and the UI
 * offers exactly one owner at a time so "both" is never expressible -- which is
 * also what the database's check constraint says.
 */

(function () {
    'use strict';

    function upload(url, file, onDone, onError) {
        const body = new FormData();
        body.append('file', file);

        csrfFetch(url, { method: 'POST', body: body })
            .then((response) => response.json())
            .then((data) => {
                if (data.success) {
                    onDone(data.attachment);
                } else {
                    onError(data.error || 'Upload failed');
                }
            })
            .catch((error) => onError(String(error)));
    }

    function showAlert(message) {
        const alerts = document.getElementById('attachment-alerts');
        if (alerts) {
            alerts.innerHTML =
                `<div class="alert alert-danger" id="attachment-alert">${message}</div>`;
        }
    }

    function initProductAttachments() {
        const card = document.getElementById('attachments-card');
        if (!card) {
            return;
        }

        const productId = card.dataset.productId;
        const input = document.getElementById('product-attachment-input');
        const button = document.getElementById('upload-product-attachment-btn');

        button.addEventListener('click', () => {
            if (!input.files || input.files.length === 0) {
                showAlert('Choose a file first.');
                return;
            }
            button.disabled = true;
            upload(
                `/api/products/${productId}/attachments`,
                input.files[0],
                () => window.location.reload(),
                (message) => {
                    button.disabled = false;
                    showAlert(message);
                }
            );
        });

        // FR-023: an image on the clipboard becomes an attachment on the
        // product being viewed. No new endpoint and no route change -- the same
        // FormData shape the file picker already posts, through csrfFetch, and
        // same-origin so the token travels.
        //
        // Clipboard content holding no image uploads nothing **and reports
        // nothing**. A rejection message on every ordinary text paste would be
        // noise: a paste is not a request to upload.
        document.addEventListener('paste', (event) => {
            if (!event.clipboardData) {
                return;
            }

            const items = Array.from(event.clipboardData.items || []);
            const image = items.find((item) => item.type.startsWith('image/'));
            if (!image) {
                return;
            }

            const file = image.getAsFile();
            if (!file) {
                return;
            }

            upload(
                `/api/products/${productId}/attachments`,
                file,
                () => window.location.reload(),
                (message) => showAlert(message)
            );
        });

        card.querySelectorAll('.delete-attachment-btn').forEach((deleteButton) => {
            deleteButton.addEventListener('click', () => {
                csrfFetch(`/api/attachments/${deleteButton.dataset.attachmentId}`, {
                    method: 'DELETE'
                })
                    .then((response) => {
                        if (response.ok) {
                            window.location.reload();
                        } else {
                            showAlert('Could not remove that attachment');
                        }
                    })
                    .catch((error) => showAlert(String(error)));
            });
        });
    }

    function initPurchaseAttachments() {
        document.querySelectorAll('.purchase-attachments').forEach((cell) => {
            const purchaseId = cell.dataset.purchaseId;
            const input = cell.querySelector('.purchase-attachment-input');
            const button = cell.querySelector('.attach-to-purchase-btn');

            button.addEventListener('click', () => input.click());
            input.addEventListener('change', () => {
                if (!input.files || input.files.length === 0) {
                    return;
                }
                upload(
                    `/api/purchases/${purchaseId}/attachments`,
                    input.files[0],
                    () => window.location.reload(),
                    (message) => showAlert(message)
                );
            });
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        initProductAttachments();
        initPurchaseAttachments();
    });
})();
