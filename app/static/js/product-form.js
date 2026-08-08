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

    // A field inside one of these is one of a repeating set: it shares its name
    // with the same field in every other row, and position is what tells them
    // apart.
    const REPEATING_ROW = '.specification-row';

    /** Everything a stored entry holds, whether it is one value or a row list. */
    function valuesOf(stored) {
        return (Array.isArray(stored) ? stored : [stored]).map((v) => v || '');
    }

    /**
     * Do a stored entry and a shown one say the same thing?
     *
     * Compared element by element rather than by joining with a separator:
     * any separator that can also appear in the text makes two different row
     * splits compare equal -- ['Foo Bar', 'Baz'] and ['Foo', 'Bar Baz'] join
     * to the same string -- and specification text is free-form, so multi-word
     * values are ordinary rather than exotic.
     */
    function sameValue(stored, shown) {
        const a = valuesOf(stored);
        const b = valuesOf(shown);
        return a.length === b.length && a.every((value, i) => value === b[i]);
    }

    class ProductFormDraft {
        constructor(form) {
            this.form = form;
            this.key = STORAGE_PREFIX + (form.dataset.draftKey || 'product');
        }

        /**
         * Queried on every use rather than snapshotted in the constructor: the
         * specification rows are added and removed after load, and a snapshot
         * taken on DOMContentLoaded would neither save what is typed into a new
         * row nor fill one when a draft is restored.
         */
        get fields() {
            return Array.from(
                this.form.querySelectorAll(
                    'input[type="text"], input[type="number"], textarea, select'
                )
            ).filter((field) => field.name && field.name !== 'csrf_token');
        }

        /**
         * The field names whose value is a default rather than something typed.
         *
         * A <select> always reports a value -- its first option. Judging "has
         * the operator already typed something here?" by that would mean the
         * answer is always yes and the draft is never offered.
         *
         * Returned as a name set rather than a list of elements because the
         * questions below are asked of a *stored draft*, which can name fields
         * the page has not rendered yet. Judging those questions by the elements
         * currently in the DOM meant a draft holding nothing but specification
         * rows looked empty: offerRestore() runs before product-specifications.js
         * has added the blank row, so there was no `spec_name` input to match
         * against and the draft was silently unrecoverable.
         */
        get untypedNames() {
            return new Set(
                this.fields
                    .filter((field) => field.tagName === 'SELECT')
                    .map((field) => field.name)
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

        /** One of a repeating set of rows, however many happen to exist now? */
        isRepeating(field) {
            return Boolean(field.closest(REPEATING_ROW));
        }

        collect() {
            const data = {};
            this.fields.forEach((field) => {
                if (this.isRepeating(field)) {
                    // Always a list, even when only one row is present. Deciding
                    // by how many rows exist *at save time* meant a one-row draft
                    // came back as a scalar, which apply() then wrote into every
                    // row on the page -- turning one edited row into two
                    // identical ones. Blanks are kept so a value still lines up
                    // with its own name.
                    data[field.name] = data[field.name] || [];
                    data[field.name].push(field.value);
                } else if (field.value) {
                    data[field.name] = field.value;
                }
            });
            return data;
        }

        /** Has the operator actually typed anything, ignoring select defaults? */
        hasTypedContent(fields) {
            const untyped = this.untypedNames;
            return Object.keys(fields).some(
                (name) => !untyped.has(name)
                    && valuesOf(fields[name]).some((value) => value)
            );
        }

        /** Does the stored draft say anything the form is not already showing? */
        differsFromForm(fields) {
            const current = this.collect();
            const untyped = this.untypedNames;
            // The union of both sides: a draft naming a field the page has not
            // rendered is a difference, and so is one the page shows and the
            // draft does not.
            const names = new Set(
                Object.keys(fields).concat(Object.keys(current))
            );
            return Array.from(names).some(
                (name) => !untyped.has(name)
                    && !sameValue(fields[name], current[name])
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

        /**
         * Add rows until the form can hold the draft.
         *
         * The row editor owns adding them, so this asks for clicks rather than
         * cloning markup itself. The loop is bounded by the number wanted rather
         * than by the count reaching it: a button that ever stopped adding a row
         * would otherwise spin forever.
         */
        growRepeatingRows(fields) {
            const addButton = document.getElementById('add-specification-btn');
            if (!addButton) {
                return;
            }
            const wanted = Math.max(
                0,
                ...Object.values(fields).filter(Array.isArray).map((list) => list.length)
            );
            const rows = () => this.form.querySelectorAll(REPEATING_ROW).length;
            for (let attempt = 0; attempt < wanted && rows() < wanted; attempt += 1) {
                addButton.click();
            }
        }

        apply(fields) {
            this.growRepeatingRows(fields);

            // Repeated names are assigned in DOM order, which is the order they
            // were collected in -- restoring only the last row would silently
            // lose every specification but one.
            const nextIndex = {};
            this.fields.forEach((field) => {
                if (!Object.prototype.hasOwnProperty.call(fields, field.name)) {
                    return;
                }
                if (!this.isRepeating(field)) {
                    field.value = fields[field.name];
                    return;
                }
                const stored = valuesOf(fields[field.name]);
                const index = nextIndex[field.name] || 0;
                nextIndex[field.name] = index + 1;
                // A row past the end of the draft is blanked rather than left
                // showing what the page rendered: the draft is the whole answer
                // for these rows, and a blank row is dropped on save (FR-009).
                field.value = index < stored.length ? stored[index] : '';
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
