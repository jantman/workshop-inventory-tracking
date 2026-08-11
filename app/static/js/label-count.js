/**
 * Shared label count reader for the print dialogs.
 *
 * Four dialogs offer a label count and they must agree on the bounds and on the
 * wording when a value is refused, so both live here rather than in each dialog.
 *
 * A plain global rather than an ES module: inventory-list.js is loaded with
 * type="module" while inventory-add.js and label-printing-modal.js are plain
 * scripts, and a global is readable from all three.
 */

const LABEL_COUNT_MIN = 1;
const LABEL_COUNT_MAX = 99;
const LABEL_COUNT_ERROR =
    `Label count must be a whole number between ${LABEL_COUNT_MIN} and ${LABEL_COUNT_MAX}`;

/**
 * Read and validate the label count from a number input.
 *
 * The gate is here rather than in browser constraint validation, because every
 * print button is type="button" and constraint validation never fires for them.
 *
 * @param {string} inputId - id of the <input type="number"> holding the count
 * @returns {{ok: true, value: number}|{ok: false, error: string}}
 */
window.readLabelCount = function(inputId) {
    const input = document.getElementById(inputId);

    // A dialog with no count input yet still prints one label.
    if (!input) {
        return { ok: true, value: 1 };
    }

    const raw = input.value.trim();
    if (!/^\d+$/.test(raw)) {
        return { ok: false, error: LABEL_COUNT_ERROR };
    }

    const value = parseInt(raw, 10);
    if (value < LABEL_COUNT_MIN || value > LABEL_COUNT_MAX) {
        return { ok: false, error: LABEL_COUNT_ERROR };
    }

    return { ok: true, value: value };
};
