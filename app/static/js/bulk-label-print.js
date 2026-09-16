/**
 * Bulk label printing dialog, shared by the pages that offer one.
 *
 * This is the inventory list's dialog, lifted out of inventory-list.js so the
 * products list can use it too. Nothing about the behaviour changed in the move:
 * the strings, the element ids and the order of operations are the ones that
 * page has always emitted, and tests/e2e/test_bulk_label_printing_list.py is
 * what says so.
 *
 * Only four things differ between the two callers -- the element id prefix, the
 * noun in the user-visible strings, the display text of an entry, and what
 * actually performs the request -- so those are the parameters and there are no
 * others. The markup comes from the `bulk_label_modal` macro in
 * app/templates/_bulk_label_modal.html, which emits the ids read here.
 *
 * A plain global rather than an ES module, for the reason label-count.js gives
 * for itself: inventory-list.js is loaded with type="module" and
 * product-list-labels.js is not, and a global is readable from both.
 */

class BulkLabelPrintDialog {
    /**
     * @param {object} config
     * @param {string} config.modalId - id of the modal element
     * @param {string} config.prefix - every other element is `${prefix}-...`
     * @param {string} config.noun - singular, for the user-visible strings
     * @param {string} config.nounPlural - plural, likewise
     * @param {Function} config.printOne - (entry, labelType, labelCount) =>
     *     Promise<Response>. The one thing that genuinely differs. It must not
     *     catch its own errors: a rejected promise is reported as that entry's
     *     failure and the run carries on.
     * @param {Function} [config.onFinished] - optional, called with
     *     {successCount, failureCount, labelsPrinted} once a run completes. It
     *     exists so the inventory list can raise the toast it has always raised
     *     without this file growing a toast of its own.
     */
    constructor(config) {
        this.modalId = config.modalId;
        this.prefix = config.prefix;
        this.noun = config.noun;
        this.nounPlural = config.nounPlural;
        this.printOne = config.printOne;
        this.onFinished = config.onFinished || (() => {});
        this.entries = [];
    }

    /** The dialog's own elements, addressed by the shared prefix. */
    el(suffix) {
        return document.getElementById(`${this.prefix}-${suffix}`);
    }

    init() {
        const labelTypeSelect = this.el('label-type');
        if (labelTypeSelect) {
            labelTypeSelect.addEventListener('change', () => this.onLabelTypeChange());
        }

        const printAllBtn = this.el('print-all-btn');
        if (printAllBtn) {
            printAllBtn.addEventListener('click', () => this.printAll());
        }

        // Reset on close so the dialog is clean for the next use.
        const modalElement = document.getElementById(this.modalId);
        if (modalElement) {
            modalElement.addEventListener('hidden.bs.modal', () => this.reset());
        }
    }

    onLabelTypeChange() {
        // Print is available only once a stock is chosen.
        this.el('print-all-btn').disabled = !this.el('label-type').value;
    }

    /**
     * Show the dialog for a selection.
     *
     * @param {Array<{id: string, label: string}>} entries - built fresh from
     *     what the page currently shows. Never cached between opens: that is
     *     what stops a row the page no longer lists from being printed.
     */
    async open(entries) {
        this.entries = entries;

        this.el('print-summary').textContent =
            `You have selected ${entries.length} ${this.noun}(s) to print labels for.`;

        const itemsList = this.el('label-items-list');
        itemsList.innerHTML = '';
        entries.forEach(entry => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.textContent = entry.label;
            itemsList.appendChild(li);
        });

        await this.loadLabelTypes();
        this.reset();

        new bootstrap.Modal(document.getElementById(this.modalId)).show();
    }

    async loadLabelTypes() {
        try {
            const response = await fetch('/api/labels/types');
            if (!response.ok) {
                throw new Error('Failed to load label types');
            }

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Failed to load label types');
            }

            const labelTypeSelect = this.el('label-type');
            // Clear existing options except the first placeholder
            while (labelTypeSelect.children.length > 1) {
                labelTypeSelect.removeChild(labelTypeSelect.lastChild);
            }

            data.label_types.forEach(labelType => {
                const option = document.createElement('option');
                option.value = labelType;
                option.textContent = labelType;
                labelTypeSelect.appendChild(option);
            });
        } catch (error) {
            console.error('Error loading label types:', error);
            alert('Failed to load label types. Please try again.');
        }
    }

    reset() {
        this.el('label-type').value = '';

        // Reset the label count. The modal is reused rather than recreated, so
        // the markup's value="1" only covers the first open.
        const labelCountInput = this.el('label-count');
        if (labelCountInput) {
            labelCountInput.value = '1';
        }

        this.el('print-progress').classList.add('d-none');

        const progressBar = this.el('print-progress-bar');
        progressBar.style.width = '0%';
        progressBar.textContent = '';
        // printAll() stops the animation when a run ends; without putting it
        // back, a dialog reopened after a run shows a dead bar.
        progressBar.classList.add('progress-bar-animated');

        const errorsDiv = this.el('print-errors');
        errorsDiv.classList.add('d-none');
        errorsDiv.innerHTML = '';

        this.el('print-all-btn').classList.remove('d-none');
        this.el('print-all-btn').disabled = true;
        this.el('print-done-btn').classList.add('d-none');
        this.el('print-cancel').classList.remove('d-none');
    }

    async printAll() {
        const labelType = this.el('label-type').value;
        const entries = this.entries;

        const progressDiv = this.el('print-progress');
        const progressBar = this.el('print-progress-bar');
        const statusSpan = this.el('print-status');
        const errorsDiv = this.el('print-errors');
        const printBtn = this.el('print-all-btn');
        const doneBtn = this.el('print-done-btn');
        const cancelBtn = this.el('print-cancel');

        // Clear anything a previous attempt left behind. The reset only runs
        // when the dialog opens and closes, so without this a refused count's
        // warning would still be sitting there after the user corrects it and
        // prints -- visible directly above a successful completion line.
        errorsDiv.classList.add('d-none');
        errorsDiv.innerHTML = '';

        // Read the count before anything is printed -- a refused count must
        // leave the dialog untouched and print nothing at all.
        const countResult = window.readLabelCount(`${this.prefix}-label-count`);
        if (!countResult.ok) {
            errorsDiv.classList.remove('d-none');
            errorsDiv.innerHTML = `<strong>Warning:</strong> ${countResult.error}`;
            return;
        }
        const labelCount = countResult.value;

        progressDiv.classList.remove('d-none');
        printBtn.classList.add('d-none');
        cancelBtn.classList.add('d-none');

        let successCount = 0;
        let failureCount = 0;
        const errors = [];

        for (let i = 0; i < entries.length; i++) {
            const entry = entries[i];
            const progress = Math.round(((i + 1) / entries.length) * 100);

            // The count suffix appears only above 1, so a run at the default
            // reads exactly as it did before there was a count at all.
            const countSuffix = labelCount > 1 ? ` (${labelCount} labels)` : '';
            statusSpan.textContent =
                `Printing ${i + 1} of ${entries.length}: ${entry.label}${countSuffix}`;
            progressBar.style.width = `${progress}%`;
            progressBar.textContent = `${progress}%`;

            try {
                const response = await this.printOne(entry, labelType, labelCount);

                if (response.ok) {
                    successCount++;
                } else {
                    const data = await response.json();
                    failureCount++;
                    errors.push(`${entry.label}: ${data.error || response.statusText}`);
                }
            } catch (error) {
                // One failure never takes the rest of the run with it.
                failureCount++;
                errors.push(`${entry.label}: ${error.message}`);
            }
        }

        if (failureCount > 0) {
            errorsDiv.classList.remove('d-none');
            // Built from nodes rather than an innerHTML template, because
            // `errors` carries entry.label and that is now a free-text product
            // description. An ordinary one -- `Shim stock <brass> 1/32"` --
            // is otherwise parsed as markup, and the name vanishes from the
            // very line that exists to say which product failed. The
            // selected-things list above has always built itself this way.
            errorsDiv.innerHTML = '';

            const warning = document.createElement('strong');
            warning.textContent = 'Warning:';
            errorsDiv.appendChild(warning);
            errorsDiv.appendChild(document.createTextNode(
                ` ${failureCount} label(s) failed to print:`));

            errors.forEach(message => {
                errorsDiv.appendChild(document.createElement('br'));
                errorsDiv.appendChild(document.createTextNode(`• ${message}`));
            });
        }

        // A failed entry contributes 0 labels rather than a partial figure --
        // one entry's copies are one lp job with one exit code, so the total
        // must never claim more labels than actually emerged.
        const labelsPrinted = successCount * labelCount;
        const attempted = successCount + failureCount;
        statusSpan.textContent =
            `Complete: ${labelsPrinted} ${labelsPrinted === 1 ? 'label' : 'labels'} ` +
            `for ${attempted} ${attempted === 1 ? this.noun : this.nounPlural}, ` +
            `${failureCount} failed`;
        progressBar.classList.remove('progress-bar-animated');

        doneBtn.classList.remove('d-none');

        this.onFinished({ successCount, failureCount, labelsPrinted });
    }
}

window.BulkLabelPrintDialog = BulkLabelPrintDialog;
