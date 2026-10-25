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
 */

(function () {
    'use strict';

    function scanEntry() {
        return document.querySelector('[data-handheld-scan]');
    }

    function focusScanEntry() {
        const input = scanEntry();
        if (input && !input.disabled) {
            input.focus({ preventScroll: true });
        }
    }

    // Blur then focus: Chrome re-reads inputmode only when focus arrives, so
    // this is what makes the keyboard rise or drop.
    function refocus(input) {
        input.blur();
        input.focus({ preventScroll: true });
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

    function confirmInPage(message) {
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

    // After a tap on anything but a form field, return focus to the scan
    // entry: tapping +, Execute or Print must not strand the next scan.
    // Taps inside an open modal are left alone; its close refocuses.
    document.addEventListener('click', (event) => {
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }
        if (target.closest('input, select, textarea, label, .modal, [data-keyboard-for]')) {
            return;
        }
        queueMicrotask(focusScanEntry);
    });
})();
