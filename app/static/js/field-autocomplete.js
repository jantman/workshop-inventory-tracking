/**
 * Generic Field Autocomplete
 *
 * Attaches database-backed autocomplete to a free-form text input by
 * polling /api/inventory/field-suggestions/<field>. Used for the five
 * fields covered by the Autocomplete feature: thread_size,
 * purchase_location, vendor, location, sub_location — plus the product
 * form's category_path (Story 3.1), which opts into the create variant,
 * and its tags field (Story 3.3), which additionally opts into
 * multi-value mode via `multiValueSeparator`.
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
 * The component owns its own ARIA wiring. Every accessibility attribute
 * of the WAI-ARIA 1.2 combobox pattern — role="combobox" and friends on
 * the input, role="listbox" on the dropdown, role="option"/aria-selected
 * on each entry, aria-activedescendant, and a polite live region
 * announcing the result count — is written from here, never from the
 * templates. The templates supply only the input and an empty
 * `#<inputId>-suggestions` div, and this file refuses to attach unless
 * both exist, so it is the only place that knows an instance is really
 * live. Fourteen hand-written copies of the same attributes — one per
 * instance across the four forms — could drift; one implementation
 * cannot, and a field added later gets the semantics for free.
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
         * @param {string} [opts.multiValueSeparator]
         *                                        — when set, the input holds a
         *                                          LIST of values separated by
         *                                          this character (Story 3.3's
         *                                          tags field). Only the
         *                                          fragment after the last
         *                                          separator is queried, and
         *                                          selecting an entry replaces
         *                                          only that fragment. Unset by
         *                                          default, so every
         *                                          single-value instance is
         *                                          byte-for-byte unaffected.
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
            // Null unless the field opted into multi-value mode; every
            // branch below is guarded on it, so the single-value instances
            // take exactly the code path they always did.
            this.multiValueSeparator = opts.multiValueSeparator || null;
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

            this.dropdownId = opts.dropdownId || `${opts.inputId}-suggestions`;
            this.dropdown = document.getElementById(this.dropdownId);
            if (!this.dropdown) {
                console.warn(
                    `FieldAutocomplete: dropdown #${this.dropdownId} not found`
                );
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
            this.attachAria();

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

        /**
         * Turn the plain <input> + empty <div> pair into a WAI-ARIA 1.2
         * combobox. Called once, from attach().
         *
         * Everything here is static for the lifetime of the instance; the
         * parts that track state (aria-expanded, aria-selected,
         * aria-activedescendant, the announcement) are maintained by
         * render()/hide()/highlight().
         */
        attachAria() {
            this.input.setAttribute('role', 'combobox');
            // "list", not "both": nothing is ever inserted into the input
            // ahead of the caret — selecting is what writes a value.
            this.input.setAttribute('aria-autocomplete', 'list');
            this.input.setAttribute('aria-controls', this.dropdownId);
            this.input.setAttribute('aria-expanded', 'false');

            this.dropdown.setAttribute('role', 'listbox');
            this.dropdown.setAttribute('aria-label', this.listboxLabel());

            // The count announcement. It lives NEXT TO the dropdown rather
            // than inside it: a listbox may only contain options, and a
            // non-option child would also be counted by anything measuring
            // the dropdown's children.
            //
            // Reused if it is already there. The class is exported for
            // programmatic use, so an input can be attached twice; a second
            // region would leave the first one stale, still asserting a count
            // that no longer holds.
            const statusId = `${this.dropdownId}-status`;
            this.liveRegion = document.getElementById(statusId);
            if (!this.liveRegion) {
                this.liveRegion = document.createElement('div');
                this.liveRegion.id = statusId;
                this.liveRegion.className = 'visually-hidden';
                this.liveRegion.setAttribute('role', 'status');
                this.liveRegion.setAttribute('aria-live', 'polite');
                this.dropdown.insertAdjacentElement('afterend', this.liveRegion);
            }
        }

        /**
         * An accessible name for the listbox, derived at runtime so no
         * template has to carry an aria-label that could disagree with the
         * visible label beside it.
         *
         * `input.labels` covers the `<label for=…>` every one of these fields
         * already has. The trailing "*" some labels use to mark a required
         * field is dropped — a screen reader announcing "Location star
         * suggestions" is noise, and requiredness is already conveyed by the
         * input's own `required`. Falls back to the field name with its
         * underscores spaced out when there is no label at all.
         *
         * Runs of whitespace are collapsed first. `textContent` returns the
         * label's source formatting verbatim, so a label wrapped across lines
         * (or wrapping an icon element) would otherwise put newlines and
         * indentation into the accessible name.
         */
        listboxLabel() {
            const label = this.input.labels && this.input.labels[0];
            const text = label
                ? label.textContent
                      .replace(/\s+/g, ' ')
                      .replace(/\s*\*\s*$/, '')
                      .trim()
                : '';
            return `${text || String(this.field).replace(/_/g, ' ')} suggestions`;
        }

        /**
         * Say what is on offer, for a user who cannot see the dropdown
         * appear. `count` of 0 is the "nothing matched" case, which is worth
         * hearing rather than leaving as silence.
         *
         * The create entry is counted SEPARATELY, never folded into `count`.
         * It is not a stored value, and on a brand-new category path it is
         * the only row — reporting "1 suggestion available" would tell a
         * screen-reader user that something matched when nothing did, which
         * is the exact confusion the visible `+ Create "…"` wording exists to
         * prevent.
         *
         * Nothing is announced on the fetch-failure paths: they route through
         * hide(), which clears the region. That is the pre-existing silent
         * behaviour and this change deliberately does not alter it.
         *
         * @param {number} count      — stored suggestions being shown
         * @param {?string} createValue — the canonical value the create entry
         *                                offers, or null when there is none
         */
        announce(count, createValue) {
            if (!this.liveRegion) return;
            const listed = count
                ? `${count} suggestion${count === 1 ? '' : 's'} available`
                : 'No suggestions';
            this.liveRegion.textContent = createValue
                ? `${listed}, plus an option to create "${createValue}"`
                : listed;
        }

        /**
         * The part of the input the dropdown is about.
         *
         * For an ordinary field that is the whole value. In multi-value mode
         * it is only the fragment after the last separator — the value the
         * user is typing right now — so the server is asked about one value
         * and can echo its canonical form, exactly as for a single-value
         * field. Returns {prefix, fragment}: `prefix` is everything before
         * that fragment, separator included, and is carried across untouched.
         */
        currentFragment() {
            const value = this.input.value || '';
            if (!this.multiValueSeparator) {
                return { prefix: '', fragment: value, suffix: '' };
            }
            const sep = this.multiValueSeparator;
            // The fragment is the one the CARET sits in, not simply the last
            // one in the field. Keying off lastIndexOf alone means that
            // editing the first of `ssr, rectifier` queries `rectifier` and
            // then replaces it on selection — discarding the edit and
            // silently overwriting a tag the operator never touched.
            const caret = Number.isInteger(this.input.selectionStart)
                ? this.input.selectionStart
                : value.length;
            const start = caret === 0 ? 0 : value.lastIndexOf(sep, caret - 1) + 1;
            const nextSep = value.indexOf(sep, caret);
            const end = nextSep < 0 ? value.length : nextSep;
            return {
                prefix: value.slice(0, start),
                fragment: value.slice(start, end),
                suffix: value.slice(end),
            };
        }

        buildUrl() {
            const params = new URLSearchParams();
            const q = this.currentFragment().fragment.trim();
            if (q) params.append('q', q);
            // In multi-value mode render() drops every suggestion the field
            // already carries elsewhere, and that filtering happens AFTER the
            // server applied its limit — so a field already holding the top
            // matches would get a dropdown of one or two entries, or none at
            // all, hiding a stored value the operator was reaching for. Ask
            // for enough extra rows to cover what the filter removes; the
            // server clamps the limit, and render() trims back to `limit`.
            const overFetch = this.multiValueSeparator
                ? this.otherValues().length : 0;
            params.append('limit', String(this.limit + overFetch));
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
         *
         * The entry stays an <a class="dropdown-item"> — every existing
         * selector, and onKeyDown/highlight/selectValue, key off exactly
         * that — and gains the option semantics on top.
         */
        buildItem(index, value) {
            const a = document.createElement('a');
            a.className = 'dropdown-item';
            a.href = '#';
            a.dataset.index = String(index);
            a.dataset.value = value;
            a.textContent = value;
            // An id is required, not cosmetic: aria-activedescendant can only
            // point at an element that has one.
            a.id = `${this.dropdownId}-option-${index}`;
            a.setAttribute('role', 'option');
            a.setAttribute('aria-selected', 'false');
            // Focus never leaves the input in this pattern — the input is
            // what carries aria-activedescendant. Without this the anchors
            // are tab stops, so Tab out of the field walks INTO the
            // suggestion list instead of on to the next form control.
            a.setAttribute('tabindex', '-1');
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

        /**
         * The values the field already carries OTHER than the fragment being
         * edited. Empty for a single-value input.
         *
         * Offering one of these would produce a visible duplicate — the server
         * de-duplicates on save, so the field would show the operator
         * something that is not what gets stored. Comparison (in render()) is
         * case-insensitive on the trimmed text, because on the ADD form every
         * value here is what the operator typed, in whatever case they typed
         * it: `SSR, ss` would otherwise be completed to `SSR, ssr, `, the
         * exact duplicate this filter exists to prevent. Lowercasing is a
         * display-side comparison only — nothing here is stored, and the
         * canonical form still comes from the server's echo.
         */
        otherValues() {
            if (!this.multiValueSeparator) return [];
            const { prefix, suffix } = this.currentFragment();
            return `${prefix}${suffix}`
                .split(this.multiValueSeparator)
                .map((v) => v.trim())
                .filter(Boolean);
        }

        render(suggestions) {
            const taken = this.otherValues();
            if (taken.length) {
                const takenLower = taken.map((v) => v.toLowerCase());
                suggestions = suggestions.filter(
                    (s) => !takenLower.includes(String(s).toLowerCase())
                );
            }
            // buildUrl over-fetched to cover what the filter above removes;
            // the dropdown still shows at most `limit` entries.
            suggestions = suggestions.slice(0, this.limit);
            // A create entry is offered only when the field opted in, the
            // server gave us a canonical value, that value is not already
            // among the suggestions (comparison on the canonical form, which
            // the server also produced), and — in multi-value mode — the
            // field does not already carry it elsewhere.
            const candidate = this.allowCreate && this.createCandidate &&
                !taken.some(
                    (v) => v.toLowerCase() ===
                        String(this.createCandidate).toLowerCase()
                )
                ? this.createCandidate : null;
            const showCreate = Boolean(candidate) &&
                !suggestions.some(
                    (s) => s.toLowerCase() === String(candidate).toLowerCase()
                );

            if (!suggestions.length && !showCreate) {
                this.hide();
                // AFTER hide(), which clears the region: collapsing normally
                // means there is nothing to report, but "nothing matched" is
                // itself the report here.
                this.announce(0, null);
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
                // fw-semibold is the only thing that distinguished this entry
                // from a stored suggestion, and weight is invisible to a
                // screen reader. data-create marks it for anything scripting
                // the dropdown; the hidden note is what a user actually hears.
                a.dataset.create = 'true';
                const note = document.createElement('span');
                note.className = 'visually-hidden';
                // A hidden SUFFIX rather than an aria-label, so the accessible
                // name still CONTAINS the visible text (WCAG 2.5.3,
                // label-in-name) — a voice-control user can still say
                // "Create". Comma-separated, not dash-separated: how a screen
                // reader voices an em dash varies by engine and by the user's
                // punctuation verbosity, a comma reads as a pause everywhere.
                note.textContent = ', new entry, not yet in the list';
                a.appendChild(note);
            }
            this.dropdown.style.display = 'block';
            this.activeIndex = -1;
            this.input.setAttribute('aria-expanded', 'true');
            // These are freshly built options; whatever the input pointed at
            // before this render no longer exists.
            this.input.removeAttribute('aria-activedescendant');
            this.announce(suggestions.length, showCreate ? candidate : null);
        }

        selectValue(value) {
            if (this.multiValueSeparator) {
                // Replace only the fragment being edited; every other value in
                // the field survives untouched, whether it sits before or
                // after the caret. A trailing separator and space are appended
                // only when this fragment IS the last one, so the operator can
                // keep typing without reaching for the comma key — while
                // editing a middle value doesn't inject a stray empty one.
                // Read at SELECTION time, not captured when the dropdown was
                // rendered. A render can lag the caret — the immediate fetch a
                // focus starts resolves after the value has already changed —
                // so a captured range describes where the caret WAS, and
                // completing a middle tag from a lagging dropdown would
                // replace the last one instead. The live caret is the only
                // reading that is true at the moment the operator acts.
                const { prefix, suffix } = this.currentFragment();
                const tail = suffix || `${this.multiValueSeparator} `;
                const head = `${prefix}${prefix ? ' ' : ''}${value}`;
                this.input.value = `${head}${tail}`;
                // Assigning .value parks the caret at the END of the field in
                // every browser, which would undo the whole point of editing a
                // MIDDLE value: the next keystroke would land on the last tag
                // instead of after the one just completed. Put it back where
                // the operator was — past the appended separator when this
                // fragment really was the last one, so typing continues into
                // the next tag either way.
                const caret = suffix ? head.length : this.input.value.length;
                if (typeof this.input.setSelectionRange === 'function') {
                    this.input.setSelectionRange(caret, caret);
                }
            } else {
                this.input.value = value;
            }
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
            // The one place the combobox is reported collapsed, so every
            // route to a hidden dropdown — no matches, a failed fetch,
            // Escape, blur, an outside click, a selection — goes through it
            // and none can leave aria-expanded lying.
            this.input.setAttribute('aria-expanded', 'false');
            this.input.removeAttribute('aria-activedescendant');
            if (this.liveRegion) this.liveRegion.textContent = '';
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
                const isActive = i === this.activeIndex;
                if (isActive) {
                    el.classList.add('active');
                } else {
                    el.classList.remove('active');
                }
                // The 'active' class is the sighted channel and the CSS is
                // the only thing that renders it; aria-selected is the same
                // fact in the accessibility tree, which is the only channel a
                // screen reader has.
                el.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });
            // In this pattern focus stays in the input, so "which entry am I
            // on" has to be published BY the input. Nothing is active at
            // activeIndex === -1, and a dangling reference to a stale option
            // is worse than none.
            const active = items[this.activeIndex];
            if (active) {
                this.input.setAttribute('aria-activedescendant', active.id);
                // The dropdown caps at 200px and can hold ten entries, so
                // arrow-keying past the fifth moves the highlight below the
                // fold. Both channels have to keep up: aria-activedescendant
                // is required to reference a VISIBLE option, and the 'active'
                // class is no use to a sighted keyboard user off-screen.
                // 'nearest' scrolls the dropdown only as far as it must, and
                // leaves the page alone when the entry is already showing.
                if (typeof active.scrollIntoView === 'function') {
                    active.scrollIntoView({ block: 'nearest' });
                }
            } else {
                this.input.removeAttribute('aria-activedescendant');
            }
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
            // Product form Tags (Story 3.3): one input holding a
            // comma-separated LIST, so it opts into multi-value mode as well
            // as create — the tag vocabulary accretes purely from use, and a
            // novel tag must be assignable without leaving the form.
            {
                inputId: 'tags',
                field: 'tags',
                allowCreate: true,
                multiValueSeparator: ',',
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
