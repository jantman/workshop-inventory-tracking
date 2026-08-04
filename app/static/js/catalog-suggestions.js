/**
 * Category and tag suggestions.
 *
 * Fills the datalists behind the category and tag inputs from what is already in
 * use. Suggestions only -- typing something new is how a category or a tag gets
 * created (FR-030, FR-031), so the input is never restricted to the list.
 */

(function () {
    'use strict';

    function fill(datalistId, values) {
        const datalist = document.getElementById(datalistId);
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

    function load(url, key, datalistId) {
        if (!document.getElementById(datalistId)) {
            return;
        }
        fetch(url)
            .then((response) => response.json())
            .then((data) => {
                if (data.success) {
                    fill(datalistId, data[key]);
                }
            })
            .catch((error) => {
                // Suggestions are a convenience; typing still works without them.
                console.warn('[catalog-suggestions] could not load', url, error);
            });
    }

    document.addEventListener('DOMContentLoaded', () => {
        load('/api/categories', 'categories', 'category-suggestions');
        load('/api/tags', 'tags', 'tag-suggestions');
    });
})();
