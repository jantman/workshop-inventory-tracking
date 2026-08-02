/**
 * Product form draft persistence (FR-035).
 *
 * Keeps in-progress entry from being lost when the connection drops mid-compose:
 * every input is mirrored to localStorage, and a draft found on load is offered
 * for restore rather than applied silently.
 *
 * This is deliberately not offline sync and not a service worker. The spec's
 * environmental assumptions put full offline operation out of scope; the only
 * resilience required is that a momentary interruption not discard typing.
 * It follows the precedent already in the codebase, where the label-printing
 * modal persists the selected label type the same way.
 */

(function () {
    'use strict';

    const STORAGE_PREFIX = 'workshop-product-draft:';

    class ProductFormDraft {
        constructor(form) {
            this.form = form;
            this.key = STORAGE_PREFIX + (form.dataset.draftKey || 'product');
            this.fields = Array.from(
                form.querySelectorAll('input[type="text"], input[type="number"], textarea, select')
            ).filter((field) => field.name && field.name !== 'csrf_token');
        }

        init() {
            this.offerRestore();

            this.form.addEventListener('input', () => this.save());
            this.form.addEventListener('change', () => this.save());
            // A draft that survived its own successful submit would be offered
            // back on the next blank form, which is worse than losing it.
            this.form.addEventListener('submit', () => this.clear());
        }

        collect() {
            const data = {};
            this.fields.forEach((field) => {
                if (field.value) {
                    data[field.name] = field.value;
                }
            });
            return data;
        }

        save() {
            const data = this.collect();
            try {
                if (Object.keys(data).length === 0) {
                    localStorage.removeItem(this.key);
                } else {
                    localStorage.setItem(this.key, JSON.stringify({
                        savedAt: new Date().toISOString(),
                        fields: data
                    }));
                }
            } catch (e) {
                // A full or disabled localStorage costs the draft, not the form.
                console.warn('[product-form] could not save draft:', e);
            }
        }

        read() {
            try {
                const raw = localStorage.getItem(this.key);
                return raw ? JSON.parse(raw) : null;
            } catch (e) {
                return null;
            }
        }

        clear() {
            try {
                localStorage.removeItem(this.key);
            } catch (e) {
                /* nothing to do */
            }
        }

        apply(fields) {
            this.fields.forEach((field) => {
                if (Object.prototype.hasOwnProperty.call(fields, field.name)) {
                    field.value = fields[field.name];
                }
            });
        }

        /**
         * Offer the draft rather than applying it: the operator may have walked
         * away and come back to start something else.
         */
        offerRestore() {
            const draft = this.read();
            if (!draft || !draft.fields || Object.keys(draft.fields).length === 0) {
                return;
            }
            if (this.fields.some((field) => field.value)) {
                // The form already carries values (an edit form, or a rejected
                // submit); overwriting them would be the surprise.
                return;
            }

            const banner = document.createElement('div');
            banner.className = 'alert alert-info d-flex flex-wrap align-items-center gap-2';
            banner.id = 'draft-restore-banner';
            banner.innerHTML =
                '<span class="me-auto"><i class="bi bi-clock-history"></i> ' +
                'You have unsaved entry from a previous visit.</span>';

            const restore = document.createElement('button');
            restore.type = 'button';
            restore.className = 'btn btn-sm btn-primary';
            restore.id = 'draft-restore-btn';
            restore.textContent = 'Restore it';
            restore.addEventListener('click', () => {
                this.apply(draft.fields);
                banner.remove();
            });

            const discard = document.createElement('button');
            discard.type = 'button';
            discard.className = 'btn btn-sm btn-outline-secondary';
            discard.id = 'draft-discard-btn';
            discard.textContent = 'Discard';
            discard.addEventListener('click', () => {
                this.clear();
                banner.remove();
            });

            banner.appendChild(restore);
            banner.appendChild(discard);
            this.form.parentNode.insertBefore(banner, this.form);
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const form = document.getElementById('product-form');
        if (form) {
            new ProductFormDraft(form).init();
        }
    });
})();
