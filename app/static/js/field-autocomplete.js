/**
 * Generic Field Autocomplete
 *
 * Attaches database-backed autocomplete to a free-form text input by
 * polling /api/inventory/field-suggestions/<field>. Used for the five
 * fields covered by the Autocomplete feature: thread_size,
 * purchase_location, vendor, location, sub_location — plus the product
 * form's category_path (Story 3.1), which opts into the create variant.
 *
 * Sub-location autocomplete optionally scopes its query by the value
 * of a related Location input (`locationFieldId`), so a user already
 * inside "Shelf A" only sees sub-locations recorded under "Shelf A".
 *
 * With `allowCreate`, the dropdown also offers a `+ Create "<value>"`
 * entry for a typed value that does not exist yet. The value shown is
 * the server's own `normalized` echo — the exact string that will be
 * stored — so nothing here re-derives it: normalization has a single
 * source of truth on the server and cannot silently drift.
 *
 * The component is intentionally narrow:
 *   - No client-side validation or normalization (these fields are
 *     free-form; the server owns canonical form).
 *   - No taxonomy navigation (that's MaterialSelector's job).
 *   - Replaces nothing other than the dropdown UI; carry-forward and
 *     form-submission code see only the underlying <input>.
 */

(function () {
    'use strict';

    const DEFAULT_DEBOUNCE_MS = 200;
    const DEFAULT_LIMIT = 10;

    function debounce(fn, ms) {
        let timer = null;
        const wrapped = function (...args) {
            if (timer) clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), ms);
        };
        // Callers that end the interaction (selecting a value) must be able to
        // drop a fetch that was already scheduled by an earlier keystroke —
        // otherwise it fires afterwards and re-opens the dropdown we closed.
        wrapped.cancel = function () {
            if (timer) clearTimeout(timer);
            timer = null;
        };
        return wrapped;
    }

    class FieldAutocomplete {
        /**
         * @param {Object} opts
         * @param {string} opts.inputId           — DOM id of the target <input>
         * @param {string} opts.field             — backend field name (whitelisted)
         * @param {string} [opts.dropdownId]      — DOM id of the dropdown <div>;
         *                                          defaults to `${inputId}-suggestions`
         * @param {string} [opts.locationFieldId] — DOM id of the related Location
         *                                          input. When set and non-empty,
         *                                          its value is sent as
         *                                          `?location=`. Intended only for
         *                                          sub-location fields.
         * @param {number} [opts.limit]           — max suggestions; default 10
         * @param {number} [opts.debounceMs]      — input debounce; default 200
         * @param {boolean} [opts.allowCreate]    — when true, offer a
         *                                          `+ Create "<value>"` entry
         *                                          for a value the server did
         *                                          not return. Requires the
         *                                          field's source to echo
         *                                          `normalized`. Default false,
         *                                          so existing instances are
         *                                          unaffected.
         */
        constructor(opts) {
            this.input = document.getElementById(opts.inputId);
            if (!this.input) {
                console.warn(`FieldAutocomplete: input #${opts.inputId} not found`);
                return;
            }

            this.field = opts.field;
            this.limit = opts.limit || DEFAULT_LIMIT;
            this.allowCreate = opts.allowCreate === true;
            // The server-supplied canonical form of the current query, or
            // null. Never computed here.
            this.createCandidate = null;
            // Monotonic id of the newest in-flight request; stale responses
            // are dropped rather than rendered.
            this.requestSeq = 0;
            // Pending blur->dismiss handle, cleared when focus comes back
            // before it fires.
            this.blurTimer = null;
            // Set by selectValue so the 'input' event it dispatches does not
            // re-open the dropdown we just closed.
            this.suppressNextFetch = false;
            this.locationField = opts.locationFieldId
                ? document.getElementById(opts.locationFieldId)
                : null;

            const dropdownId = opts.dropdownId || `${opts.inputId}-suggestions`;
            this.dropdown = document.getElementById(dropdownId);
            if (!this.dropdown) {
                console.warn(`FieldAutocomplete: dropdown #${dropdownId} not found`);
                return;
            }

            this.activeIndex = -1;
            this.debouncedFetch = debounce(
                () => this.fetchAndRender(),
                opts.debounceMs || DEFAULT_DEBOUNCE_MS
            );

            this.attach();
        }

        attach() {
            this.input.setAttribute('autocomplete', 'off');

            this.input.addEventListener('input', () => {
                if (this.suppressNextFetch) {
                    // This 'input' event is our own, dispatched by
                    // selectValue after the user picked an entry. Re-querying
                    // would reopen the dropdown ~200ms later — and for a
                    // create entry it would re-offer creating the value the
                    // user just accepted, on top of the Save button.
                    this.suppressNextFetch = false;
                    return;
                }
                this.debouncedFetch();
            });
            this.input.addEventListener('focus', () => {
                // A blur moments ago scheduled a dismiss(); letting it land
                // now would cancel the very fetch this focus is starting and
                // leave the field silently dropdown-less.
                if (this.blurTimer) {
                    clearTimeout(this.blurTimer);
                    this.blurTimer = null;
                }
                this.fetchAndRender();
            });
            this.input.addEventListener('keydown', (e) => this.onKeyDown(e));
            this.input.addEventListener('blur', () => {
                // Delay so a click on the dropdown registers before we hide.
                this.blurTimer = setTimeout(() => {
                    this.blurTimer = null;
                    this.dismiss();
                }, 150);
            });

            // Hide on outside click.
            document.addEventListener('click', (e) => {
                if (e.target !== this.input && !this.dropdown.contains(e.target)) {
                    this.dismiss();
                }
            });
        }

        buildUrl() {
            const params = new URLSearchParams();
            const q = (this.input.value || '').trim();
            if (q) params.append('q', q);
            params.append('limit', String(this.limit));
            if (this.locationField) {
                const loc = (this.locationField.value || '').trim();
                if (loc) params.append('location', loc);
            }
            const qs = params.toString();
            const base = `/api/inventory/field-suggestions/${encodeURIComponent(this.field)}`;
            return qs ? `${base}?${qs}` : base;
        }

        async fetchAndRender() {
            // 'focus' fetches immediately while a debounced keystroke fetch
            // may still be in flight, so responses can arrive out of order.
            // Only the newest one is allowed to touch the dropdown; otherwise
            // an older query's suggestions (and, worse, its `normalized`
            // create candidate) could overwrite what the user is typing now.
            const seq = ++this.requestSeq;
            try {
                const response = await fetch(this.buildUrl());
                if (seq !== this.requestSeq) return;
                if (!response.ok) {
                    this.hide();
                    return;
                }
                const body = await response.json();
                if (seq !== this.requestSeq) return;
                if (!body || !body.success) {
                    this.hide();
                    return;
                }
                // Catalog-sourced fields echo the canonical form of the
                // query; item fields never send this key, so the create
                // entry can only ever appear where the server supports it.
                this.createCandidate = this.allowCreate
                    ? (body.normalized || null)
                    : null;
                this.render(body.suggestions || []);
            } catch (err) {
                console.warn(
                    `FieldAutocomplete[${this.field}]: fetch failed`,
                    err
                );
                this.hide();
            }
        }

        /**
         * Build one dropdown entry, append it, and return it.
         *
         * Items are built via DOM APIs rather than innerHTML.
         * textContent escapes safely; dataset.value carries the raw
         * string so selectValue writes the original (un-encoded) text
         * back into the input — even if a suggestion contains
         * characters like '&', '<', or quotes.
         */
        buildItem(index, value) {
            const a = document.createElement('a');
            a.className = 'dropdown-item';
            a.href = '#';
            a.dataset.index = String(index);
            a.dataset.value = value;
            a.textContent = value;
            a.addEventListener('mousedown', (e) => {
                // mousedown so we beat the input's blur->hide.
                e.preventDefault();
                this.selectValue(a.dataset.value);
            });
            // Belt-and-suspenders: even when mousedown ran, a click
            // event still fires on the anchor afterward and would
            // otherwise navigate to "#" (jumping the page to top).
            a.addEventListener('click', (e) => {
                e.preventDefault();
            });
            this.dropdown.appendChild(a);
            return a;
        }

        render(suggestions) {
            // A create entry is offered only when the field opted in, the
            // server gave us a canonical value, and that value is not
            // already among the suggestions (comparison on the canonical
            // form, which the server also produced).
            const candidate = this.allowCreate ? this.createCandidate : null;
            const showCreate = Boolean(candidate) &&
                !suggestions.some(
                    (s) => s.toLowerCase() === String(candidate).toLowerCase()
                );

            if (!suggestions.length && !showCreate) {
                this.hide();
                return;
            }
            this.dropdown.replaceChildren();
            suggestions.forEach((v, i) => {
                this.buildItem(i, v);
            });
            if (showCreate) {
                // Just another .dropdown-item carrying data-value, so
                // onKeyDown/highlight/selectValue need no changes and
                // ArrowDown/Enter/Escape/click all work on it for free.
                const a = this.buildItem(suggestions.length, candidate);
                a.textContent = `+ Create "${candidate}"`;
                a.classList.add('fw-semibold');
            }
            this.dropdown.style.display = 'block';
            this.activeIndex = -1;
        }

        selectValue(value) {
            this.input.value = value;
            // Selecting ends the interaction, so nothing may re-open the
            // dropdown behind the user's back — which, for a create entry
            // sitting over the Save button, could swallow the submit click.
            // Three things can re-open it, so all three are closed here:
            //   1. a fetch already scheduled by an earlier keystroke, and
            //   2. a fetch already in flight (its response is now stale) —
            //      both handled by dismiss(),
            this.dismiss();
            //   3. the 'input' event this method itself dispatches below.
            this.suppressNextFetch = true;
            this.input.dispatchEvent(new Event('input', { bubbles: true }));
            this.input.dispatchEvent(new Event('change', { bubbles: true }));
        }

        hide() {
            this.dropdown.style.display = 'none';
            this.activeIndex = -1;
        }

        /**
         * Close the dropdown for good — the user is done with it (Escape,
         * blur, outside click), as opposed to hide()'s "there is nothing to
         * show right now".
         *
         * Plain hide() is not enough: a keystroke moments earlier may have
         * scheduled a debounced fetch, or left one in flight, and either
         * re-renders the dropdown up to ~200ms AFTER it was dismissed. It
         * then sits over the Save button with no focus in the field, where a
         * click meant for Save lands on a dropdown item's mousedown instead.
         * With allowCreate that stray dropdown appears even when the server
         * matched nothing, which is the ordinary case for a brand-new
         * category path — so the window is widest on exactly the flow the
         * create affordance exists for. Same two closures selectValue makes.
         */
        dismiss() {
            this.debouncedFetch.cancel();
            this.requestSeq++;
            this.hide();
        }

        onKeyDown(e) {
            const items = Array.from(this.dropdown.querySelectorAll('.dropdown-item'));
            const visible = this.dropdown.style.display === 'block' && items.length > 0;

            if (e.key === 'Escape') {
                // Handled BEFORE the visibility guard below. Escape's job is
                // to cancel what is coming, not only to close what is already
                // up: the keystroke just before it scheduled a debounced fetch
                // that opens the dropdown ~200ms later. In that window the
                // dropdown is still hidden, so a visibility-gated Escape would
                // be a no-op on exactly the case dismiss() exists for.
                this.dismiss();
                return;
            }
            if (!visible) return;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                this.activeIndex = (this.activeIndex + 1) % items.length;
                this.highlight(items);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                this.activeIndex =
                    this.activeIndex <= 0 ? items.length - 1 : this.activeIndex - 1;
                this.highlight(items);
            } else if (e.key === 'Enter') {
                if (this.activeIndex >= 0 && this.activeIndex < items.length) {
                    e.preventDefault();
                    this.selectValue(items[this.activeIndex].dataset.value);
                }
            }
        }

        highlight(items) {
            items.forEach((el, i) => {
                if (i === this.activeIndex) {
                    el.classList.add('active');
                } else {
                    el.classList.remove('active');
                }
            });
        }
    }

    // Auto-initialize the standard field set on DOM ready. Each
    // attachment is independent — missing inputs are skipped silently
    // (their console warnings make this debuggable).
    document.addEventListener('DOMContentLoaded', function () {
        const targets = [
            { inputId: 'thread_size', field: 'thread_size' },
            { inputId: 'purchase_location', field: 'purchase_location' },
            { inputId: 'vendor', field: 'vendor' },
            { inputId: 'location', field: 'location' },
            {
                inputId: 'sub_location',
                field: 'sub_location',
                locationFieldId: 'location',
            },
            // Product form Category (Story 3.1): the only create-enabled
            // field. The category tree accretes purely from use, so a novel
            // path must be creatable inline without leaving the form.
            {
                inputId: 'category_path',
                field: 'category_path',
                allowCreate: true,
            },
        ];

        const instances = {};
        targets.forEach((cfg) => {
            const input = document.getElementById(cfg.inputId);
            const dropdown = document.getElementById(`${cfg.inputId}-suggestions`);
            if (input && dropdown) {
                instances[cfg.inputId] = new FieldAutocomplete(cfg);
            }
        });
        window.fieldAutocompleteInstances = instances;
    });

    // Export for tests / programmatic use.
    window.FieldAutocomplete = FieldAutocomplete;
})();
