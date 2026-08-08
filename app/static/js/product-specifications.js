/**
 * The repeating specification-row editor, and the suggestions behind it.
 *
 * Every row carries the *same* field names -- `spec_name` and `spec_value` --
 * so the server pairs them positionally with `request.form.getlist`. That is why
 * there is no index bookkeeping here and no renumbering when a row is removed:
 * the DOM order is the order, and `display_order` falls out of it on the server.
 *
 * Suggestions are plain <datalist> rather than field-autocomplete.js: that
 * component is constructed per DOM id, and these rows are cloned at runtime with
 * no stable ids to construct against. A datalist also cannot restrict what is
 * typed, so "suggestions never limit what can be entered" holds by construction
 * rather than by care.
 */

(function () {
    'use strict';

    /** Replace a datalist's options. Missing elements are not an error. */
    function fill(datalist, values) {
        if (!datalist) {
            return;
        }
        datalist.innerHTML = '';
        values.forEach((value) => {
            const option = document.createElement('option');
            option.value = value;
            datalist.appendChild(option);
        });
    }

    function load(url, key) {
        return fetch(url)
            .then((response) => response.json())
            .then((data) => (data.success ? data[key] : []))
            .catch((error) => {
                // Suggestions are a convenience; typing still works without them.
                console.warn('[product-specifications] could not load', url, error);
                return [];
            });
    }

    function loadNames() {
        return load('/api/specification-names', 'specification_names');
    }

    function loadValues(name) {
        if (!name.trim()) {
            return Promise.resolve([]);
        }
        return load(
            '/api/specification-values?name=' + encodeURIComponent(name),
            'specification_values'
        );
    }

    class SpecificationRows {
        constructor(container) {
            this.container = container;
            this.template = document.getElementById('specification-row-template');
            this.addButton = document.getElementById('add-specification-btn');
            // Unique ids for the per-row value datalists. The rows themselves
            // need no ids -- only a <datalist> does, because `list=` refers to
            // one by id and nothing else.
            this.nextDatalistId = 0;
        }

        get rows() {
            return Array.from(this.container.querySelectorAll('.specification-row'));
        }

        init() {
            if (!this.template || !this.addButton) {
                return;
            }

            this.addButton.addEventListener('click', () => this.addRow());
            this.container.addEventListener('click', (event) => {
                const remove = event.target.closest('.remove-specification-btn');
                if (remove) {
                    this.removeRow(remove.closest('.specification-row'));
                }
            });
            this.container.addEventListener('change', (event) => {
                if (event.target.classList.contains('specification-name')) {
                    this.refreshValues(event.target.closest('.specification-row'));
                }
            });

            this.rows.forEach((row) => this.wireRow(row));

            // A form that opens with nowhere to type is a form that looks broken.
            if (this.rows.length === 0) {
                this.addRow();
            }
        }

        /** Give a row's value input its own datalist and fill it if it has a name. */
        wireRow(row) {
            const value = row.querySelector('.specification-value');
            const datalist = row.querySelector('.specification-value-suggestions');
            if (!value || !datalist) {
                return;
            }
            this.nextDatalistId += 1;
            datalist.id = 'specification-values-' + this.nextDatalistId;
            value.setAttribute('list', datalist.id);
            this.refreshValues(row);
        }

        /** Reload one row's value suggestions from that row's current name. */
        refreshValues(row) {
            if (!row) {
                return;
            }
            const name = row.querySelector('.specification-name');
            const datalist = row.querySelector('.specification-value-suggestions');
            if (!name || !datalist) {
                return;
            }
            // Scoped per row on purpose: one shared list would offer
            // "barrel 5.5 mm" while the operator is typing a voltage.
            const asked = name.value;
            loadValues(asked).then((values) => {
                // A response for a name the row has since moved off is stale.
                // Two changes in quick succession can land out of order, and
                // the loser would otherwise overwrite the winner.
                if (name.value === asked) {
                    fill(datalist, values);
                }
            });
        }

        addRow() {
            const row = this.template.content.firstElementChild.cloneNode(true);
            this.container.appendChild(row);
            this.wireRow(row);
            return row;
        }

        removeRow(row) {
            if (!row) {
                return;
            }
            row.remove();
            // Removing the last row would leave the operator nothing to type in.
            if (this.rows.length === 0) {
                this.addRow();
            }
        }
    }

    /** The catalogue filter: one name input, one value input, same endpoints. */
    function initFilter() {
        const name = document.getElementById('filter-spec-name');
        const values = document.getElementById('specification-value-suggestions');
        if (!name || !values) {
            return;
        }

        const refresh = () => {
            const asked = name.value;
            return loadValues(asked).then((list) => {
                if (name.value === asked) {
                    fill(values, list);
                }
            });
        };
        name.addEventListener('change', refresh);
        refresh();
    }

    document.addEventListener('DOMContentLoaded', () => {
        // One shared list behind every name input, on the forms and the filter.
        const names = document.getElementById('specification-name-suggestions');
        if (names) {
            loadNames().then((values) => fill(names, values));
        }

        const container = document.getElementById('specification-rows');
        if (container) {
            new SpecificationRows(container).init();
        }

        initFilter();
    });
})();
