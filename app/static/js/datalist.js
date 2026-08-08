/**
 * Filling a <datalist> from a suggestion endpoint.
 *
 * Two files needed the same three steps -- fetch JSON, hand back the list, warn
 * and carry on if it fails -- so they live here rather than in whichever one
 * happened to be written first. Suggestions are a convenience: every caller must
 * stay usable when the fetch fails, which is why a failure resolves to an empty
 * list rather than rejecting.
 *
 * Loaded before catalog-suggestions.js and product-specifications.js, both of
 * which do their work on DOMContentLoaded.
 */

window.WorkshopDatalist = (function () {
    'use strict';

    /** Replace a datalist's options. A missing element is not an error. */
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

    /**
     * Fetch a suggestion endpoint and resolve to its list.
     *
     * @param {string} url    the endpoint
     * @param {string} key    the response property holding the array
     * @returns {Promise<string[]>} the values, or [] if anything went wrong
     */
    function load(url, key) {
        return fetch(url)
            .then((response) => response.json())
            .then((data) => (data.success ? data[key] : []))
            .catch((error) => {
                console.warn('[datalist] could not load', url, error);
                return [];
            });
    }

    return { fill: fill, load: load };
})();
