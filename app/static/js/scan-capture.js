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

    // What the in-flight POST carries. Used to tell a duplicate TERMINATOR
    // (same burst, field unchanged) apart from a genuine second burst.
    inFlightText: null,

    // Text known to be two scans run together. Never submittable.
    mergedResidue: null,

    init: function() {
        this.input = document.getElementById('scan-input');
        if (!this.input) return;

        this.bindEvents();
    },

    bindEvents: function() {
        // keydown on the field only — never on document.
        this.input.addEventListener('keydown', (e) => {
            if (e.key !== 'Enter') return;

            // An IME commit fires Enter as well (`isComposing`, or keyCode 229
            // in browsers that predate it). That Enter ends the composition; it
            // does not terminate a scan, and acting on it would post a partial
            // string.
            if (e.isComposing || e.keyCode === 229) return;

            // A wedge terminates with Enter; nothing here should submit a form.
            e.preventDefault();

            if (this.isSubmitting) {
                // ONE scan can produce TWO Enter presses: HID has no separate
                // LF key, so a wedge programmed with a CR+LF suffix emits
                // Return twice in the same burst, and the second always lands
                // inside the first one's in-flight window. The field still
                // holds exactly what is in flight, which is how that case is
                // recognised. Warning here would fire on every single scan and
                // tell the operator to rescan an item that WAS captured —
                // double-processing it once Stories 4.3/4.5 add side effects.
                if (this.input.value === this.inFlightText) return;

                // The field has GROWN, so this is a second burst and its scan
                // is genuinely dropped — announced, never silently, because a
                // silent drop is indistinguishable from a captured scan.
                this.notify('Previous scan still in progress - rescan this item.', 'warning');
                if (this.inFlightText && this.input.value.startsWith(this.inFlightText)) {
                    // The dropped burst's CHARACTERS sit on top of the text
                    // still in flight ("SCAN1SCAN2").
                    this.flagMergedResidue();
                } else {
                    // The operator cleared the field first, so what is there is
                    // a clean scan — dropped, but not contaminated.
                    this.selectIfActive();
                }
                return;
            }

            // The residue of a dropped burst ("SCAN1SCAN2") must never be
            // submitted. Selecting it only protects the path where the next
            // burst TYPES over it; a bare Enter — the obvious response to
            // "rescan this item", and what a repeat-trigger scanner emits —
            // would otherwise POST the concatenation as one valid 200 scan. A
            // silently WRONG scan is worse than the lost scan the guard exists
            // to prevent.
            if (this.isMergedResidue(this.input.value)) {
                this.input.value = '';
                this.mergedResidue = null;
                this.notify(
                    'That text was two scans run together and was not sent - scan again.',
                    'danger');
                this.refocus();
                return;
            }
            this.mergedResidue = null;

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
     * Remember a concatenation so a later bare Enter cannot submit it, and
     * select it so the next burst's first keystroke overwrites it.
     */
    flagMergedResidue: function() {
        this.mergedResidue = this.input.value;
        this.selectIfActive();
    },

    // startsWith, not equality: if focus had already left the field,
    // selectIfActive could not select it, so a later burst appends to the
    // residue rather than replacing it.
    isMergedResidue: function(value) {
        return !!this.mergedResidue && value.startsWith(this.mergedResidue);
    },

    /**
     * POST the field's value verbatim. The value is NOT trimmed, cased or
     * otherwise touched here: control characters carried by an ISO/IEC 15434
     * envelope must reach the server byte-for-byte, and the server owns the
     * single narrow whitespace rule.
     */
    submitScan: function(rawText) {
        this.isSubmitting = true;
        this.inFlightText = rawText;

        // A request that never settles would otherwise leave isSubmitting
        // stuck true and every later scan refused for the rest of the session.
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.config.timeoutMs);

        // An abort means the outcome is UNKNOWN — the server may have taken the
        // scan and only the response was too slow. Saying "could not reach the
        // server" would invite a rescan of something already accepted, which
        // matters once Stories 4.3/4.5 give this endpoint side effects.
        const timedOut = 'Scan timed out - the server may or may not have received it.';

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
                this.handleFailure(rawText, result.aborted
                    ? timedOut
                    : 'Scan failed: could not reach the server.');
            } else if (result.ok && result.data && result.data.success) {
                this.handleSuccess(rawText);
            } else if (controller.signal.aborted) {
                // The abort landed while the response BODY was being read, so
                // it surfaced as a null `data` above rather than as a rejected
                // fetch. Same unknown outcome, so it must carry the same
                // warning instead of a generic failure.
                this.handleFailure(rawText, timedOut);
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
            this.inFlightText = null;
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
            // Newer keystrokes win. If they sit ON TOP of the text the server
            // just accepted ("SCAN1SCAN2") the field is contaminated, so flag
            // it as unsubmittable and select it. If the operator cleared the
            // field first, what is there is a clean scan — leave it alone.
            if (this.input.value.startsWith(rawText)) {
                this.flagMergedResidue();
            }
            return;
        }

        this.input.value = '';
        this.mergedResidue = null;
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
            this.mergedResidue = null;
            // select() focuses the element as a side effect, so it must run
            // ONLY when refocus() decided focusing was allowed. Calling it
            // unconditionally would yank focus back from whatever field the
            // operator moved to — exactly what refocus() exists to prevent.
            if (this.refocus()) {
                this.input.select();
            }
        } else {
            message = `${message} Unrestored scan: ${rawText}`;
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

    /**
     * The SINGLE escaping boundary. `showToast` interpolates its argument into
     * innerHTML, so every message is escaped here and every caller passes plain
     * text — including server-supplied strings and the scanned payload itself,
     * which a printed label makes attacker-suppliable physical input.
     *
     * Escaping at each call site instead (as this file did) leaves nothing at
     * the call site to distinguish an already-escaped string from a raw one,
     * which is exactly how Stories 4.2/4.3 would reintroduce the injection.
     */
    notify: function(message, level) {
        if (window.WorkshopInventory && window.WorkshopInventory.utils) {
            window.WorkshopInventory.utils.showToast(this.escapeHtml(message), level);
        } else {
            console.error(message);
        }
    },

    // AD-13 object-error envelope: {success: false, error: {code, message, field?}}
    // Returns PLAIN TEXT; `notify` escapes it.
    errorMessage: function(data) {
        if (data && data.error && data.error.message) {
            return `Scan failed: ${data.error.message}`;
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
