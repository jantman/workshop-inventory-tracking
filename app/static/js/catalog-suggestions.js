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
        // The Set Category dialog (063) has its own list, because the Products
        // page already carries #category-suggestions behind its filter. One
        // fetch fills both.
        const categoryLists = ['category-suggestions', 'bulk-category-suggestions']
            .map((id) => document.getElementById(id))
            .filter(Boolean);
        if (categoryLists.length) {
            datalists.load('/api/categories', 'categories').then((values) => {
                categoryLists.forEach((datalist) => datalists.fill(datalist, values));
            });
        }
        load('/api/tags', 'tags', 'tag-suggestions');
    });
})();
