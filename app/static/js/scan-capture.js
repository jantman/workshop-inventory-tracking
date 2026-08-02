/**
 * Keyboard-wedge scan capture.
 *
 * The scanner types its payload and terminates with Enter. This buffers the
 * rapid keystrokes and flushes on Enter or an inter-key timeout, following the
 * pattern already in inventory-add.js.
 *
 * The property this adds, and the single most breakable link in the scan path:
 * **control characters must survive**. GS (0x1d), RS (0x1e) and EOT (0x04) carry
 * the field structure of a distributor's 2D label, and a capture that quietly
 * drops non-printing characters passes every other test in the suite and fails
 * only when a real DigiKey label is scanned. A wedge emits those as Ctrl-key
 * events, so they are reconstructed here rather than discarded.
 */

(function () {
    'use strict';

    // Milliseconds of silence that ends a scan when no Enter arrives.
    const INTER_KEY_TIMEOUT_MS = 120;

    /**
     * Map a Ctrl+<key> event onto the control character a wedge means by it.
     * Returns null when the combination is not a control character.
     */
    function controlCharacterFor(event) {
        if (!event.ctrlKey || event.altKey || event.metaKey) {
            return null;
        }

        const key = event.key;
        if (key.length !== 1) {
            return null;
        }

        // Ctrl+A..Ctrl+Z -> 0x01..0x1a (EOT is Ctrl+D).
        const upper = key.toUpperCase();
        if (upper >= 'A' && upper <= 'Z') {
            return String.fromCharCode(upper.charCodeAt(0) - 64);
        }

        // The separators, in the forms browsers report them.
        const punctuation = {
            '[': '\x1b',   // ESC
            '\\': '\x1c',  // FS
            ']': '\x1d',   // GS
            '^': '\x1e',   // RS
            '6': '\x1e',   // RS, as Ctrl+6 on layouts without a bare caret
            '_': '\x1f',   // US
            '-': '\x1f'
        };
        return Object.prototype.hasOwnProperty.call(punctuation, key)
            ? punctuation[key]
            : null;
    }

    class ScanCapture {
        constructor(input) {
            this.input = input;
            this.buffer = '';
            this.timer = null;
        }

        init() {
            this.input.addEventListener('keydown', (event) => this.onKeyDown(event));
            // A paste is a legitimate manual path; take it verbatim.
            this.input.addEventListener('paste', (event) => {
                const text = (event.clipboardData || window.clipboardData).getData('text');
                if (text) {
                    event.preventDefault();
                    this.buffer = text;
                    this.flush();
                }
            });
        }

        onKeyDown(event) {
            if (this.timer) {
                clearTimeout(this.timer);
                this.timer = null;
            }

            if (event.key === 'Enter') {
                event.preventDefault();
                this.flush();
                return;
            }

            const control = controlCharacterFor(event);
            if (control !== null) {
                // Without this the field structure of a distributor label is
                // gone before anything downstream can see it.
                event.preventDefault();
                this.buffer += control;
                this.scheduleFlush();
                return;
            }

            if (event.key.length === 1) {
                event.preventDefault();
                this.buffer += event.key;
                this.scheduleFlush();
            }
        }

        scheduleFlush() {
            this.timer = setTimeout(() => {
                this.timer = null;
                this.flush();
            }, INTER_KEY_TIMEOUT_MS);
        }

        flush() {
            const scan = this.buffer;
            this.buffer = '';
            if (!scan) {
                return;
            }
            this.resolve(scan);
        }

        /**
         * Ask the server what the scan is. Every well-formed scan gets an
         * answer -- a product, an offer to create one, or a search -- so there
         * is no not-found branch to handle here.
         */
        resolve(scan) {
            this.setBusy(true);

            fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scan: scan })
            })
                .then((response) => response.json())
                .then((data) => {
                    if (data && data.url) {
                        window.location.href = data.url;
                    } else {
                        this.setBusy(false);
                        console.error('[scan-capture] no destination in response', data);
                    }
                })
                .catch((error) => {
                    this.setBusy(false);
                    console.error('[scan-capture] scan failed', error);
                });
        }

        setBusy(busy) {
            this.input.classList.toggle('is-scanning', busy);
            this.input.disabled = busy;
            if (!busy) {
                this.input.value = '';
                this.input.focus();
            }
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('[data-scan-capture]').forEach((input) => {
            new ScanCapture(input).init();
        });
    });

    // Exported for the tests that assert control characters survive.
    window.WorkshopScanCapture = { controlCharacterFor: controlCharacterFor };
})();
