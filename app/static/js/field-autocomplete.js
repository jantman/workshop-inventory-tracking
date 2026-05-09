/**
 * Generic Field Autocomplete
 *
 * Attaches database-backed autocomplete to a free-form text input by
 * polling /api/inventory/field-suggestions/<field>. Used for the five
 * fields covered by the Autocomplete feature: thread_size,
 * purchase_location, vendor, location, sub_location.
 *
 * Sub-location autocomplete optionally scopes its query by the value
 * of a related Location input (`locationFieldId`), so a user already
 * inside "Shelf A" only sees sub-locations recorded under "Shelf A".
 *
 * The component is intentionally narrow:
 *   - No client-side validation (these fields are free-form).
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
        return function (...args) {
            if (timer) clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), ms);
        };
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
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
         */
        constructor(opts) {
            this.input = document.getElementById(opts.inputId);
            if (!this.input) {
                console.warn(`FieldAutocomplete: input #${opts.inputId} not found`);
                return;
            }

            this.field = opts.field;
            this.limit = opts.limit || DEFAULT_LIMIT;
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

            this.input.addEventListener('input', () => this.debouncedFetch());
            this.input.addEventListener('focus', () => this.fetchAndRender());
            this.input.addEventListener('keydown', (e) => this.onKeyDown(e));
            this.input.addEventListener('blur', () => {
                // Delay so a click on the dropdown registers before we hide.
                setTimeout(() => this.hide(), 150);
            });

            // Hide on outside click.
            document.addEventListener('click', (e) => {
                if (e.target !== this.input && !this.dropdown.contains(e.target)) {
                    this.hide();
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
            try {
                const response = await fetch(this.buildUrl());
                if (!response.ok) {
                    this.hide();
                    return;
                }
                const body = await response.json();
                if (!body || !body.success) {
                    this.hide();
                    return;
                }
                this.render(body.suggestions || []);
            } catch (err) {
                console.warn(
                    `FieldAutocomplete[${this.field}]: fetch failed`,
                    err
                );
                this.hide();
            }
        }

        render(suggestions) {
            if (!suggestions.length) {
                this.hide();
                return;
            }
            const html = suggestions
                .map(
                    (v, i) =>
                        `<a class="dropdown-item" href="#" data-index="${i}" ` +
                        `data-value="${escapeHtml(v)}">${escapeHtml(v)}</a>`
                )
                .join('');
            this.dropdown.innerHTML = html;
            this.dropdown.style.display = 'block';
            this.activeIndex = -1;

            this.dropdown.querySelectorAll('.dropdown-item').forEach((el) => {
                el.addEventListener('mousedown', (e) => {
                    // mousedown so we beat the input's blur->hide.
                    e.preventDefault();
                    this.selectValue(el.dataset.value);
                });
            });
        }

        selectValue(value) {
            this.input.value = value;
            this.hide();
            this.input.dispatchEvent(new Event('input', { bubbles: true }));
            this.input.dispatchEvent(new Event('change', { bubbles: true }));
        }

        hide() {
            this.dropdown.style.display = 'none';
            this.activeIndex = -1;
        }

        onKeyDown(e) {
            const items = Array.from(this.dropdown.querySelectorAll('.dropdown-item'));
            const visible = this.dropdown.style.display === 'block' && items.length > 0;
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
            } else if (e.key === 'Escape') {
                this.hide();
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
