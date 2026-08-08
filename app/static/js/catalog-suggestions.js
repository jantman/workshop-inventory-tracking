/**
 * Category and tag suggestions.
 *
 * Fills the datalists behind the category and tag inputs from what is already in
 * use. Suggestions only -- typing something new is how a category or a tag gets
 * created (FR-030, FR-031), so the input is never restricted to the list.
 *
 * The fetch-and-fill plumbing is shared with product-specifications.js and lives
 * in datalist.js.
 */

(function () {
    'use strict';

    const datalists = window.WorkshopDatalist;

    function load(url, key, datalistId) {
        const datalist = document.getElementById(datalistId);
        if (!datalist) {
            return;
        }
        datalists.load(url, key).then((values) => datalists.fill(datalist, values));
    }

    document.addEventListener('DOMContentLoaded', () => {
        load('/api/categories', 'categories', 'category-suggestions');
        load('/api/tags', 'tags', 'tag-suggestions');
    });
})();
