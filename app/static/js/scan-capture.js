/**
 * Workshop Inventory Tracking - Wedge Scan Capture (FR35)
 *
 * Captures a keyboard-wedge barcode scan from the global #scan-input navbar
 * field and POSTs the typed characters verbatim to /api/scan.
 *
 * This file is deliberately dumb. It performs NO classification, NO
 * normalization and NO uppercasing — the server decides what a scan means
 * (Story 4.2's classifier, Story 4.3's resolver, Story 4.5's routing all land
 * behind the same POST). Keeping it out of main.js keeps the epic-4 scan logic
 * in one isolated file.
 *
 * Story 4.5 adds exactly ONE behavior: an accepted scan's response carries a
 * server-built `url`, and the client follows it. It does NOT build that URL, and
 * it does not read `kind` or `outcome` to decide where to go — if it branched on
 * either, FR36's precedence would exist in two languages (AD-5).
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

    // Text the CLIENT itself put back in the field after a failure. Submitting
    // it again is a legitimate retry; submitting something that EXTENDS it is a
    // later burst's characters sitting on top of it.
    retainedText: null,

    // The field value already announced as a dropped burst, so a CR+LF wedge's
    // second Return does not warn about the same drop twice.
    warnedText: null,

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

                // The same CR+LF suffix sends its second Return after a burst
                // that WAS dropped, and the field is unchanged since the drop
                // was announced. One dropped burst, one warning.
                if (this.input.value === this.warnedText) return;

                // The field has GROWN, so this is a second burst and its scan
                // is genuinely dropped — announced, never silently, because a
                // silent drop is indistinguishable from a captured scan.
                this.warnedText = this.input.value;
                if (this.inFlightText && this.input.value.startsWith(this.inFlightText)) {
                    // The dropped burst's CHARACTERS sit on top of the text
                    // still in flight ("SCAN1SCAN2"). This burst is complete —
                    // its Enter is what brought us here — so selecting is safe.
                    this.flagMergedResidue();
                } else {
                    // The operator cleared the field first, so what is there is
                    // a clean scan — dropped, but not contaminated.
                    this.selectIfActive();
                }
                this.notify('Previous scan still in progress - rescan this item.', 'warning');
                return;
            }

            // Two scans run together ("SCAN1SCAN2") must never be submitted.
            // Selecting the residue only protects the path where the next burst
            // TYPES over it; a bare Enter — the obvious response to "rescan this
            // item", and what a repeat-trigger scanner emits — would otherwise
            // POST the concatenation as one valid 200 scan. A silently WRONG
            // scan is worse than the lost scan the guard exists to prevent.
            if (this.isContaminated(this.input.value)) {
                const refused = this.input.value;
                this.input.value = '';
                this.forgetFieldText();
                this.notify(
                    'That text was two scans run together and was not sent - scan again. ' +
                        `Discarded: ${this.printable(refused)}`,
                    'danger');
                this.refocus();
                return;
            }
            this.forgetFieldText();

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
     *
     * Only safe from the keydown path, where the burst that produced the value
     * has finished (its Enter is what got us here). From an asynchronous
     * response handler the burst may still be typing, and selecting mid-burst
     * would make its remaining keystrokes REPLACE the field — leaving a
     * truncated payload that no longer matches the residue and would submit.
     * Those paths use markMergedResidue instead.
     */
    flagMergedResidue: function() {
        this.markMergedResidue();
        this.selectIfActive();
    },

    // Record a concatenation without touching the selection. The value may
    // still be growing, which the startsWith match in isContaminated absorbs.
    markMergedResidue: function() {
        this.mergedResidue = this.input.value;
    },

    /**
     * Is this value known to be more than one scan?
     *
     * Two records, because the two cases differ on equality:
     * - `mergedResidue` is already a concatenation, so submitting it unchanged
     *   is exactly the silently-wrong scan to refuse. startsWith, not equality:
     *   if focus had left the field the residue could not be selected, so a
     *   later burst appends to it rather than replacing it.
     * - `retainedText` is a single failed scan the client put back for retry,
     *   so submitting it unchanged is legitimate. Only a value that STRICTLY
     *   extends it carries a later burst's characters on top.
     */
    isContaminated: function(value) {
        if (this.mergedResidue && value.startsWith(this.mergedResidue)) return true;

        return !!this.retainedText &&
            value.length > this.retainedText.length &&
            value.startsWith(this.retainedText);
    },

    // Forget what the client knows about the field's current contents, because
    // the operator has replaced it with something unrelated.
    forgetFieldText: function() {
        this.mergedResidue = null;
        this.retainedText = null;
        this.warnedText = null;
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
                this.handleSuccess(rawText, result.data);
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
            // unknown and the operator's field state is whatever it left. Say
            // so anyway — silence here is indistinguishable from a scan that
            // never fired, which is the reason the failure toast is mandatory.
            console.error('Scan handler error:', error);
            this.notify('Scan status unknown - check before rescanning.', 'danger');
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
    handleSuccess: function(rawText, data) {
        if (this.input.value !== rawText) {
            // Newer keystrokes win. If they sit ON TOP of the text the server
            // just accepted ("SCAN1SCAN2") the field is contaminated, so record
            // it as unsubmittable. If the operator cleared the field first,
            // what is there is a clean scan — leave it alone.
            if (this.input.value.startsWith(rawText)) {
                this.markMergedResidue();
                // The field cannot be cleared, so THIS scan has no success
                // signal at all — and the refusal the operator's next Enter
                // earns talks about the field, not about the item already
                // captured. Silence here reads as "never fired" and invites a
                // rescan of something the server has taken.
                this.notify(
                    'Scan accepted. The field now holds two scans run together' +
                        ' - scan the next item again.',
                    'warning');
            }
            return;
        }

        this.input.value = '';
        this.forgetFieldText();
        const stillOurs = this.refocus();

        // Story 4.5: follow the destination the SERVER chose. The URL is taken
        // as given — no parsing, no branching on `kind` or `outcome`, no
        // construction (AD-5).
        //
        // The one thing checked is that it resolves to THIS origin. `url_for`
        // cannot emit an external URL today, so this is defence in depth — but
        // the endpoint producing it is CSRF-exempt, so the check has to actually
        // hold: a character test does not. "/\evil.example" passes any
        // "starts with / but not //" rule and is then normalized by the browser
        // to "//evil.example", i.e. scheme-relative and off-site. Resolving the
        // URL the way the browser will and comparing origins is the same one
        // line and has no such gap.
        const url = (data && typeof data.url === 'string') ? data.url : '';
        let sameOrigin = false;
        if (url) {
            try {
                sameOrigin = new URL(url, window.location.href).origin ===
                    window.location.origin;
            } catch (e) {
                sameOrigin = false;
            }
        }

        // Gated on refocus()'s verdict for the same reason the clear above is
        // gated on the field still holding what was submitted: a response is
        // asynchronous, and if the operator has already moved to another field
        // (the JA ID lookup, say) then navigating would destroy what they are
        // typing there. Refusing to navigate is the conservative half of that
        // choice — the scan WAS accepted, the field is cleared to say so, and
        // the operator simply stays where they put themselves.
        if (stillOurs) {
            if (sameOrigin) {
                window.location.href = url;
            } else {
                // Accepted, cleared, and going nowhere: `url` was missing, empty
                // or not ours. The endpoint's contract says that cannot happen,
                // which is exactly why it must not be silent if it ever does —
                // a cleared field with no landing reads as "never fired" and
                // invites a rescan, the same reasoning as the two branches
                // either side of this one.
                this.notify(
                    `Scan accepted: ${this.printable(rawText)}. It had no usable` +
                        ' destination - find the product from the menu.',
                    'warning');
            }
            return;
        }

        // ...and the OTHER half is saying so. The field cleared silently while
        // the operator was looking somewhere else, and the destination was
        // dropped; silence there reads as "never fired" and invites a rescan of
        // something the server has already taken — the same reasoning as the
        // contaminated-field branch above. Focus is still not stolen.
        this.notify(
            `Scan accepted: ${this.printable(rawText)}. You had moved to another` +
                ' field, so it was not followed.',
            'warning');
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
            this.warnedText = null;
            // Remember what the client itself left in the field. The selection
            // below is gone the moment the operator clicks anywhere, and a burst
            // arriving after that APPENDS — so the retry text needs the same
            // concatenation guard the dropped-burst residue has.
            this.retainedText = rawText;
            // select() focuses the element as a side effect, so it must run
            // ONLY when refocus() decided focusing was allowed. Calling it
            // unconditionally would yank focus back from whatever field the
            // operator moved to — exactly what refocus() exists to prevent.
            if (this.refocus()) {
                this.input.select();
            }
        } else {
            // A burst is typing into the field right now, and its characters
            // sit on top of the failed text. The Enter it is about to send must
            // not POST that concatenation, so record it before the Enter
            // arrives — without selecting, which would truncate the burst.
            if (this.input.value.startsWith(rawText)) {
                this.markMergedResidue();
            }
            message = `${message} Unrestored scan: ${this.printable(rawText)}`;
        }

        this.notify(message, 'danger');
    },

    // Never yank focus back from wherever the operator has moved in the
    // meantime — a late response must not steal keystrokes from another field.
    // Returns whether focus was (or already was) on the scan field.
    refocus: function() {
        const active = document.activeElement;
        // documentElement and a DETACHED node are both "nothing is focused"
        // states a browser really reports — the latter after the element the
        // operator was on is removed, which a dismissed toast's own close
        // button does. Treating them as another field would leave the scan
        // field unfocused and the next burst going nowhere.
        if (!active || active === this.input || active === document.body ||
                active === document.documentElement || !document.contains(active)) {
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
     * which a printed label makes attacker-suppliable physical input. Escaping
     * per call site would leave nothing at the call site to distinguish an
     * already-escaped string from a raw one.
     *
     * `showToast` needs the Bootstrap bundle, which is loaded from a CDN. If it
     * throws, the operator loses the toast — but a scan-state mutation must
     * never be skipped because the notification failed, so nothing here
     * propagates. Callers still mutate state BEFORE notifying.
     */
    notify: function(message, level) {
        try {
            if (window.WorkshopInventory && window.WorkshopInventory.utils) {
                window.WorkshopInventory.utils.showToast(this.escapeHtml(message), level);
                return;
            }
        } catch (error) {
            console.error('Scan toast failed:', error);
        }
        console.error(message);
    },

    // AD-13 object-error envelope: {success: false, error: {code, message, field?}}
    // Returns PLAIN TEXT; `notify` escapes it. The message is server-supplied,
    // so its type is checked and its length bounded rather than trusted — an
    // object would render as "[object Object]" and a long one would push the
    // toast off the screen.
    errorMessage: function(data) {
        const message = data && data.error && data.error.message;
        if (typeof message === 'string' && message) {
            return `Scan failed: ${message.slice(0, 200)}`;
        }
        return 'Scan failed. The scanned text has been kept for retry.';
    },

    /**
     * Render control characters visibly, the way the server logs `repr`.
     *
     * A toast that tells the operator to read the text off must not put an
     * ISO/IEC 15434 envelope's GS/RS/EOT into the DOM, where they render as
     * nothing and the message becomes a claim about text that is not there.
     */
    printable: function(text) {
        return String(text).replace(
            /[\x00-\x1f\x7f]/g,
            (c) => `\\x${c.charCodeAt(0).toString(16).padStart(2, '0')}`);
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
