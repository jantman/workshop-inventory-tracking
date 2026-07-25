/**
 * Workshop Inventory Tracking - Wedge Scan Capture (FR35)
 *
 * Captures a keyboard-wedge barcode scan from the global #scan-input navbar
 * field and POSTs the typed characters verbatim to /api/scan.
 *
 * This file is deliberately dumb. It performs NO classification, NO
 * normalization, NO uppercasing and NO navigation — the server decides what a
 * scan means (Story 4.2's classifier, Story 4.3's resolver, Story 4.5's
 * routing all land behind the same POST). Keeping it out of main.js keeps the
 * epic-4 scan logic in one isolated file.
 *
 * Note there is no document-level key listener here: capture requires the
 * field to have focus, and main.js's global shortcut handler already
 * early-returns while focus is in an input, so a focused scan field is inert
 * to it. A second global listener would create the conflict that absence
 * avoids.
 */

const ScanCapture = {

    // Endpoint is @csrf.exempt, matching every other JSON route.
    config: {
        endpoint: '/api/scan',
        timeoutMs: 10000
    },

    // Guards against a fast double-scan producing two overlapping requests
    // against one keystroke burst.
    isSubmitting: false,

    init: function() {
        this.input = document.getElementById('scan-input');
        if (!this.input) return;

        this.bindEvents();
    },

    bindEvents: function() {
        // keydown on the field only — never on document.
        this.input.addEventListener('keydown', (e) => {
            if (e.key !== 'Enter') return;

            // A wedge terminates with Enter; nothing here should submit a form.
            e.preventDefault();

            // A scan arriving while the previous POST is still in flight is
            // ignored — but never SILENTLY. A silent drop is indistinguishable
            // from a captured scan, which is exactly how a scan gets lost.
            //
            // The dropped burst's CHARACTERS are already in the field, appended
            // to the text still in flight ("SCAN1SCAN2"). Leaving them there is
            // worse than dropping the scan: the operator's rescan would append
            // again and POST the concatenation as one valid scan. Selecting the
            // residue makes the next burst's first keystroke overwrite it.
            if (this.isSubmitting) {
                this.notify('Previous scan still in progress - rescan this item.', 'warning');
                this.selectIfActive();
                return;
            }

            // Blank Enter is a no-op: send nothing. The blank test must use the
            // SERVER's trim set, not JS trim() — trim() also strips \x0b, \x0c,
            // \u00a0 (NBSP) and \ufeff (BOM), which the server deliberately keeps. A
            // payload made only of those would be dropped here with no request and
            // no toast, while the server would have accepted it.
            if (!this.stripOuter(this.input.value)) return;

            this.submitScan(this.input.value);
        });
    },

    /**
     * POST the field's value verbatim. The value is NOT trimmed, cased or
     * otherwise touched here: control characters carried by an ISO/IEC 15434
     * envelope must reach the server byte-for-byte, and the server owns the
     * single narrow whitespace rule.
     */
    submitScan: function(rawText) {
        this.isSubmitting = true;

        // A request that never settles would otherwise leave isSubmitting
        // stuck true and every later scan refused for the rest of the session.
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.config.timeoutMs);

        // The rejection handler below covers the network stage ONLY. It must
        // not wrap the handlers, or a bug thrown inside handleSuccess would be
        // reported to the operator as an offline server for a scan the server
        // actually accepted.
        fetch(this.config.endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ raw: rawText }),
            signal: controller.signal
        })
        .then(
            response => response.json()
                .catch(() => null)
                .then(data => ({ ok: response.ok, data })),
            error => ({ networkError: true, aborted: !!error && error.name === 'AbortError' })
        )
        .then(result => {
            if (result.networkError) {
                // An abort is NOT the same as an unreachable server: the
                // request may have been received and processed, and only the
                // response was too slow. Saying "could not reach the server"
                // would invite a rescan of something already accepted — which
                // matters once Stories 4.3/4.5 give this endpoint side effects.
                this.handleFailure(rawText, result.aborted
                    ? 'Scan timed out - the server may or may not have received it.'
                    : 'Scan failed: could not reach the server.');
            } else if (result.ok && result.data && result.data.success) {
                this.handleSuccess(rawText);
            } else {
                this.handleFailure(rawText, this.errorMessage(result.data));
            }
        })
        .catch(error => {
            // Only reachable if a handler above threw. Do not claim a network
            // failure and do not touch the field: the server's verdict is
            // unknown and the operator's field state is whatever it left.
            console.error('Scan handler error:', error);
        })
        .finally(() => {
            clearTimeout(timer);
            this.isSubmitting = false;
        });
    },

    /**
     * Only a successful response clears the field.
     *
     * The clear is conditional on the field still holding exactly what was
     * submitted. The response is asynchronous, so by the time it lands the
     * operator (or the next wedge burst) may already have typed into the
     * field; blanking it unconditionally would erase those keystrokes and
     * still show the cleared-field "accepted" signal — a lost scan.
     */
    handleSuccess: function(rawText) {
        if (this.input.value !== rawText) {
            // Newer keystrokes win — but they sit on top of the accepted text
            // ("SCAN1SCAN2"). Select the residue so the next burst overwrites
            // it instead of concatenating onto it.
            this.selectIfActive();
            return;
        }

        this.input.value = '';
        this.refocus();
    },

    /**
     * A scan is never lost: the raw text stays in the field and is selected,
     * so the operator can retry it or read it off. The toast is not optional —
     * retained text is otherwise indistinguishable from a scan that never
     * fired.
     *
     * Restoring is likewise conditional: if the operator has already started
     * a fresh scan, overwriting it would trade one lost scan for another. On
     * that branch the failed text is put in the TOAST instead — otherwise it
     * exists nowhere on either side (the server logs it only at debug) while
     * the message still claims it was kept.
     */
    handleFailure: function(rawText, message) {
        if (this.input.value === '' || this.input.value === rawText) {
            this.input.value = rawText;
            // select() focuses the element as a side effect, so it must run
            // ONLY when refocus() decided focusing was allowed. Calling it
            // unconditionally would yank focus back from whatever field the
            // operator moved to — exactly what refocus() exists to prevent.
            if (this.refocus()) {
                this.input.select();
            }
        } else {
            message = `${message} Unrestored scan: ${this.escapeHtml(rawText)}`;
        }

        this.notify(message, 'danger');
    },

    // Never yank focus back from wherever the operator has moved in the
    // meantime — a late response must not steal keystrokes from another field.
    // Returns whether focus was (or already was) on the scan field.
    refocus: function() {
        const active = document.activeElement;
        if (active === this.input || active === document.body || active === null) {
            this.input.focus();
            return true;
        }
        return false;
    },

    // Select the field's contents, but only when it already has focus —
    // select() focuses as a side effect and must never steal focus.
    selectIfActive: function() {
        if (document.activeElement === this.input) {
            this.input.select();
        }
    },

    // The server's trim rule, mirrored EXACTLY (routes.py `_SCAN_TRIM`).
    // Used only to decide "is this blank"; the value posted is never trimmed.
    stripOuter: function(value) {
        return value.replace(/^[ \t\r\n]+/, '').replace(/[ \t\r\n]+$/, '');
    },

    notify: function(message, level) {
        if (window.WorkshopInventory && window.WorkshopInventory.utils) {
            window.WorkshopInventory.utils.showToast(message, level);
        } else {
            console.error(message);
        }
    },

    // AD-13 object-error envelope: {success: false, error: {code, message, field?}}
    // The message is server-supplied and showToast renders via innerHTML, so it
    // is escaped here. Stories 4.2/4.3 will echo the scanned payload into these
    // messages, and a barcode label is attacker-suppliable physical input.
    errorMessage: function(data) {
        if (data && data.error && data.error.message) {
            return `Scan failed: ${this.escapeHtml(data.error.message)}`;
        }
        return 'Scan failed. The scanned text has been kept for retry.';
    },

    // TEXT-NODE CONTEXT ONLY. This escapes &, < and > — which is what
    // showToast's `<div class="toast-body">${message}</div>` needs — but NOT
    // quotes. Stories 4.2/4.3 must not reuse it for an attribute position.
    escapeHtml: function(text) {
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    ScanCapture.init();
});

// Make available globally
window.ScanCapture = ScanCapture;
