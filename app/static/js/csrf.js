/**
 * CSRF token plumbing for fetch().
 *
 * Flask-WTF protects every POST, PUT, PATCH and DELETE, and a fetch() carries no
 * form field to put the token in. It does accept the token in an `X-CSRFToken`
 * header, so this reads the token out of the meta tag in base.html and adds that
 * header to any state-changing request.
 *
 * This exists so the catalog's AJAX endpoints do not have to be exempted from
 * CSRF one by one. The one endpoint that genuinely cannot carry a token -- the
 * bookmarklet's POST /api/capture, which arrives from a vendor's origin -- stays
 * exempt and says why at the endpoint.
 */

(function () {
    'use strict';

    const UNSAFE_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE'];

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : null;
    }

    /**
     * fetch(), with the CSRF token attached when the method needs one.
     *
     * @param {string} url
     * @param {object} options - the usual fetch options.
     * @returns {Promise<Response>}
     */
    function csrfFetch(url, options) {
        const settings = Object.assign({}, options);
        const method = (settings.method || 'GET').toUpperCase();

        if (UNSAFE_METHODS.indexOf(method) !== -1) {
            const token = csrfToken();
            if (token) {
                settings.headers = Object.assign({}, settings.headers, {
                    'X-CSRFToken': token
                });
            } else {
                // Without this the request comes back 400 and the failure looks
                // like a server problem rather than a missing meta tag.
                console.warn('[csrf] no csrf-token meta tag found; ' + method +
                             ' ' + url + ' will probably be rejected');
            }
        }

        return fetch(url, settings);
    }

    window.csrfFetch = csrfFetch;
    window.csrfToken = csrfToken;
})();
