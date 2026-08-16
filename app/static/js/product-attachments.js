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

        initSelection(card);
    }

    /**
     * Selecting several attachments and removing them in one press (#96).
     *
     * The selection is the checked boxes, read from the DOM when it is needed.
     * There is no client-side model of the tiles to hang a flag on -- they are
     * server-rendered -- and inventing one would be a second place for the
     * truth about a checkbox to live.
     */
    function initSelection(card) {
        const deleteSelected = document.getElementById('delete-selected-attachments');
        if (!deleteSelected) {
            // No attachments, so no toolbar was rendered.
            return;
        }

        const label = document.getElementById('delete-selected-attachments-label');

        // Read live rather than captured: the partial-failure path removes tiles
        // from the grid, and a list captured at load would go on counting them.
        function selected() {
            return Array.from(card.querySelectorAll('.attachment-select'))
                .filter((box) => box.checked);
        }

        const selectAll = document.getElementById('select-all-attachments');

        function refresh() {
            const boxes = Array.from(card.querySelectorAll('.attachment-select'));
            const count = selected().length;

            deleteSelected.disabled = count === 0;
            label.textContent = count === 0
                ? 'Delete Selected'
                : `Delete Selected (${count})`;

            // Kept honest against the tiles: "all" must not stay lit while one
            // of them is unticked.
            selectAll.checked = boxes.length > 0 && count === boxes.length;
            selectAll.indeterminate = count > 0 && count < boxes.length;
        }

        card.querySelectorAll('.attachment-select').forEach((box) => {
            box.addEventListener('change', refresh);
        });

        selectAll.addEventListener('change', () => {
            card.querySelectorAll('.attachment-select').forEach((box) => {
                box.checked = selectAll.checked;
            });
            refresh();
        });

        deleteSelected.addEventListener('click', () => {
            const chosen = selected();
            if (chosen.length === 0) {
                return;
            }

            const noun = chosen.length === 1 ? 'attachment' : 'attachments';
            if (!window.confirm(`Delete ${chosen.length} ${noun}?`)) {
                return;
            }

            deleteSelected.disabled = true;
            deleteSelection(chosen).finally(refresh);
        });

        refresh();
    }

    /**
     * Delete each chosen attachment, **one at a time**.
     *
     * Sequential on purpose, and not because of any user-facing race: two
     * attachments can reference the same photo row, and delete_attachment drops
     * the photo bytes once nothing else references them. Two of those in flight
     * together can both find the photo unreferenced and both try to delete it,
     * so one reports a failure for a delete that actually happened. Awaiting
     * each request makes that unreachable, and at this scale costs nothing
     * anyone can perceive.
     */
    async function deleteSelection(chosen) {
        const removed = [];
        let failures = 0;

        for (const box of chosen) {
            try {
                const response = await csrfFetch(
                    `/api/attachments/${box.dataset.attachmentId}`,
                    { method: 'DELETE' }
                );
                // 404 is the attachment already being gone -- which is the state
                // that was asked for. A second tab is the realistic cause.
                if (response.ok || response.status === 404) {
                    removed.push(box);
                } else {
                    failures += 1;
                }
            } catch (error) {
                failures += 1;
            }
        }

        if (failures === 0) {
            window.location.reload();
            return;
        }

        // Not a reload: it would wipe the message. The grid is brought back to
        // the truth instead -- what was deleted goes, what refused to stays.
        removed.forEach((box) => {
            const row = box.closest('.attachment-row');
            if (row) {
                row.remove();
            }
        });

        const noun = failures === 1 ? 'attachment' : 'attachments';
        showAlert(
            `${failures} ${noun} could not be removed. The rest were deleted.`
        );
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
