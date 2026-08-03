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

            // A <select> always reports a value -- its first option. Judging
            // "has the operator already typed something here?" by that would
            // mean the answer is always yes and the draft is never offered.
            this.typedFields = this.fields.filter(
                (field) => field.tagName !== 'SELECT'
            );
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

        /** Has the operator actually typed anything, ignoring select defaults? */
        hasTypedContent(fields) {
            return this.typedFields.some((field) => fields[field.name]);
        }

        /** Does the stored draft say anything the form is not already showing? */
        differsFromForm(fields) {
            return this.typedFields.some(
                (field) => (fields[field.name] || '') !== (field.value || '')
            );
        }

        save() {
            const data = this.collect();
            try {
                if (!this.hasTypedContent(data)) {
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
            if (!draft || !draft.fields || !this.hasTypedContent(draft.fields)) {
                return;
            }
            if (!this.differsFromForm(draft.fields)) {
                // The draft says nothing the form is not already showing, so
                // there is nothing to offer.
                //
                // This is a comparison rather than a "does the form have any
                // values?" check, which is what it used to be: an edit form is
                // always pre-populated -- `description` is required and can
                // never be blank -- so that check was unconditionally true
                // there and the restore banner could never appear on the one
                // form where losing an edit costs the most.
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
