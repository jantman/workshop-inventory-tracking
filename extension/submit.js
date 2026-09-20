/**
 * Build the form and POST it, in this tab.
 *
 * This page is the whole reason the extension defeats issue #133's second half.
 * The submission is made by a document the extension owns, not by the vendor's
 * page, so the vendor's `upgrade-insecure-requests` is not in the path, and a
 * plain top-level navigation is not a popup and cannot be blocked
 * (048 research.md §3).
 *
 * The payload arrives through `chrome.storage.session` rather than the address,
 * because an Amazon order with its per-line listings runs to tens of kilobytes.
 * The key is single-use and is deleted before the form is submitted, so a tab
 * restored later submits nothing rather than submitting again.
 */

const problem = document.getElementById('problem');
const sending = document.getElementById('status');

function fail(message) {
    sending.hidden = true;
    problem.hidden = false;
    problem.textContent = message;
}

async function send() {
    const key = new URLSearchParams(location.search).get('key');
    if (!key) {
        fail('This page was opened without a capture to send.');
        return;
    }

    const held = await chrome.storage.session.get(key);
    const pending = held[key];
    // Deleted before the form is built, not after: this page must not be able
    // to submit the same capture twice, and the only copy that matters from
    // here on is the one already in hand.
    await chrome.storage.session.remove(key);

    if (!pending) {
        fail(
            'That capture is no longer available — the browser session ended, or '
            + 'it has already been sent. Run the capture again from the vendor’s page.'
        );
        return;
    }

    const form = document.createElement('form');
    form.method = 'POST';
    // The stored address is a bare origin (storage.js normalizes it on write),
    // so the endpoint path is appended here and nowhere else.
    form.action = `${pending.address}/api/capture`;

    // Built from the payload's own keys. `order` and `vendor` are absent rather
    // than empty when they do not apply, and an absent key must produce no field
    // at all -- a plain Amazon listing sends no `vendor`, and FR-003 requires
    // that to stay byte-identical to what the bookmarklet sent.
    for (const [name, value] of Object.entries(pending.fields)) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = name;
        input.value = value;
        form.appendChild(input);
    }

    document.body.appendChild(form);
    form.submit();
}

// Nothing may end in silence: a page left saying "Sending the capture…" for ever
// is the symptom this whole feature exists to remove, one step further along.
send().catch((error) => {
    console.error('[workshop-capture] the submission failed:', error);
    fail(`The capture could not be sent: ${error.message}`);
});
