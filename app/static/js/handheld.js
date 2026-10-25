/**
 * Handheld screens (feature 068): scan-entry focus, the keyboard button and an
 * in-page confirm. Loaded only by handheld/base.html, after the base scripts.
 *
 * Markup it binds (contracts/controller-markup.md, "handheld.js"):
 * - [data-handheld-scan]: the screen's scan entry, focused on load and after
 *   actions so the next scan lands in it with no tap.
 * - [data-keyboard-for="<input id>"]: the keyboard button. The scan entry is
 *   rendered with inputmode="none" so focusing it never raises the soft
 *   keyboard; this button raises it for one typed entry.
 * - #handheld-confirm-modal with #handheld-confirm-message, -ok and -cancel:
 *   backs window.confirmAction, so no browser dialog appears on a handheld.
 *
 * Enter in any field but the scan entry is cancelled: a scan that lands in a
 * tapped field must not submit its form. Only the action bar's buttons do.
 */

(function () {
    'use strict';

    function scanEntry() {
        return document.querySelector('[data-handheld-scan]');
    }

    // Fields where a tap means "I am about to type here", so focus stays.
    // Checkboxes and radios are not among them: the full-width cards are
    // labels wrapping one, and a scan after ticking a card must still reach
    // the scan entry.
    const TEXT_ENTRY = 'input:not([type=checkbox]):not([type=radio]):not([type=file])'
        + ':not([type=button]):not([type=submit]):not([type=reset]), select, textarea';

    // Focus the scan entry with its contents selected, so the next scan
    // replaces what is there (a prefill, the last code) instead of appending.
    function focusScanEntry() {
        const input = scanEntry();
        if (input && !input.disabled && document.activeElement !== input) {
            input.focus({ preventScroll: true });
            input.select();
        }
    }

    // Blur then focus: Chrome re-reads inputmode only when focus arrives, so
    // this is what makes the keyboard rise or drop.
    function refocus(input) {
        input.blur();
        input.focus({ preventScroll: true });
        input.select();
    }

    function setManualEntry(checked) {
        // The Move page auto-processes its field 100 ms after each character
        // unless manual entry mode is on, which would submit a half-typed code.
        //
        // MoveManager's change handler also resets #scanner-status to "Ready",
        // which would misreport a move in progress (it would read "Ready" while
        // waiting for a location), so the badge is put back as it was.
        const manual = document.getElementById('manual-entry-mode');
        if (manual && manual.checked !== checked) {
            const status = document.getElementById('scanner-status');
            const before = status && { text: status.textContent, cls: status.className };
            manual.checked = checked;
            manual.dispatchEvent(new Event('change', { bubbles: true }));
            if (before) {
                status.textContent = before.text;
                status.className = before.cls;
            }
        }
    }

    function openKeyboard(input) {
        if (input._handheldKeyboardEnter) {
            input.removeEventListener('keydown', input._handheldKeyboardEnter);
        }
        input.setAttribute('inputmode', 'text');
        setManualEntry(true);
        refocus(input);

        // Registered now, long after the controllers bound their own keydown
        // handlers, so theirs run first and see manual entry still on. No
        // preventDefault: the Enter is theirs.
        const onEnter = (event) => {
            if (event.key !== 'Enter') {
                return;
            }
            input.removeEventListener('keydown', onEnter);
            input._handheldKeyboardEnter = null;
            input.setAttribute('inputmode', 'none');
            setManualEntry(false);
            refocus(input);
        };
        input._handheldKeyboardEnter = onEnter;
        input.addEventListener('keydown', onEnter);
    }

    // One question at a time: a second ask while one is open would add a
    // second OK listener, and one tap would answer both.
    let confirmPending = false;

    function confirmInPage(message) {
        if (confirmPending) {
            return Promise.resolve(false);
        }
        confirmPending = true;
        const modalEl = document.getElementById('handheld-confirm-modal');
        const okBtn = document.getElementById('handheld-confirm-ok');
        document.getElementById('handheld-confirm-message').textContent = message;
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

        return new Promise((resolve) => {
            let confirmed = false;
            const onOk = () => {
                confirmed = true;
                modal.hide();
            };
            okBtn.addEventListener('click', onOk);
            // Resolved once the modal is fully gone, so the caller's next step
            // (and the refocus below) never races the closing animation.
            modalEl.addEventListener('hidden.bs.modal', () => {
                okBtn.removeEventListener('click', onOk);
                confirmPending = false;
                resolve(confirmed);
            }, { once: true });
            modal.show();
        });
    }

    window.confirmAction = confirmInPage;

    document.addEventListener('DOMContentLoaded', () => {
        focusScanEntry();

        document.querySelectorAll('[data-keyboard-for]').forEach((button) => {
            button.addEventListener('click', (event) => {
                const input = document.getElementById(button.dataset.keyboardFor);
                if (input) {
                    event.preventDefault();
                    openKeyboard(input);
                }
            });
        });
    });

    // After any modal closes (label printing, the confirm), the next scan
    // goes to the scan entry.
    document.addEventListener('hidden.bs.modal', focusScanEntry);

    // After a tap on anything but a text field (or its label), return focus
    // to the scan entry: tapping +, Execute, Print or a card must not strand
    // the next scan. Taps inside an open modal are left alone; its close
    // refocuses. File inputs are left alone too: Attach opens the chooser.
    document.addEventListener('click', (event) => {
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }
        if (target.closest('.modal, [data-keyboard-for], input[type=file]')) {
            return;
        }
        const label = target.closest('label');
        const field = target.closest(TEXT_ENTRY) || (label && label.control);
        if (field && field.matches(TEXT_ENTRY)) {
            return;
        }
        queueMicrotask(focusScanEntry);
    });

    // A tap on a label moves focus to its checkbox after the label's click
    // has been handled, so the click above is too early for a card. The
    // change comes last; refocus there. (Only a real tap: handheld.js's own
    // manual-entry toggle dispatches a change too.)
    document.addEventListener('change', (event) => {
        if (event.isTrusted && event.target instanceof Element
                && event.target.matches('input[type=checkbox], input[type=radio]')) {
            focusScanEntry();
        }
    });

    // Enter in a form field submits its form (implicit submission), and every
    // scan ends with Enter. A scan that lands in a tapped field -- Quantity, a
    // ticked card -- must not receive or shorten anything, so on a handheld
    // only the action bar's buttons submit. The scan entry keeps its Enter
    // (its controller handles it), and is left selected for the next scan.
    // Registered on the document, so the field's own handlers run first.
    document.addEventListener('keydown', (event) => {
        const target = event.target;
        if (event.key !== 'Enter' || !(target instanceof Element)) {
            return;
        }
        if (target.matches('[data-handheld-scan]')) {
            target.select();
        } else if (target.matches('input, select')) {
            event.preventDefault();
        }
    });
})();
