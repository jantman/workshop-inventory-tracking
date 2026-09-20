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
 *
 * **`form.submit()` is a navigation, and a navigation reports nothing.** It
 * returns no promise, and a browser that refuses to make it -- the documented
 * risk of an `http://` address, since this page is itself a secure context --
 * refuses silently. There is no event for "the navigation you asked for did not
 * happen". So the only signal available is that this page is still here after a
 * while, and that is what `SETTLE_MS` below watches for. A tab left reading
 * "Sending the capture…" for ever is exactly the silence this whole feature
 * exists to remove, one step further along than where it started.
 *
 * A `fetch()` would be observable, and is still wrong: the endpoint answers a
 * form submission with a *rendered page*, so fetching it would leave this tab
 * holding markup it cannot become. That is the same reason research.md §3 gave
 * for not having the service worker POST.
 */

/** How long to wait for the navigation before deciding it is not coming. */
const SETTLE_MS = 8000;

const problem = document.getElementById('problem');
const sending = document.getElementById('status');
const retry = document.getElementById('retry');

function fail(message) {
    sending.hidden = true;
    problem.hidden = false;
    problem.textContent = message;
}

async function send() {
    problem.hidden = true;
    retry.hidden = true;
    sending.hidden = false;

    const key = new URLSearchParams(location.search).get('key');
    if (!key) {
        fail('This page was opened without a capture to send.');
        return;
    }

    const held = await chrome.storage.session.get(key);
    const pending = held[key];

    if (!pending) {
        fail(
            'That capture is no longer available — the browser session ended, or '
            + 'it has already been sent. Run the capture again from the vendor’s page.'
        );
        return;
    }

    // The stored address is a bare origin (storage.js normalizes it on write),
    // so the endpoint path is appended here and nowhere else.
    const endpoint = `${pending.address}/api/capture`;

    // **Dropped when the navigation commits, not before.** Deleting it up front
    // would make a refused submission unrecoverable as well as invisible: this
    // page holds the only copy. Letting it survive costs nothing, because
    // sending the same capture twice is harmless — a form body to /api/capture
    // renders the confirmation form and writes nothing (app/product/routes.py).
    addEventListener('pagehide', () => chrome.storage.session.remove(key), { once: true });

    const form = document.createElement('form');
    form.method = 'POST';
    form.action = endpoint;

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

    // If the navigation happens this page is gone and the timer with it. If it
    // does not, this is the only thing that will ever say so.
    setTimeout(() => {
        fail(
            `The browser did not send the capture to ${endpoint}. That usually `
            + 'means the address is not reachable, or it is not served over '
            + 'https — a page belonging to an extension may be refused when it '
            + 'submits to an insecure address. Check the address on the '
            + 'extension’s options screen. The capture itself is still here.'
        );
        retry.hidden = false;
    }, SETTLE_MS);
}

retry.addEventListener('click', send);

// Nothing may end in silence: a page left saying "Sending the capture…" for ever
// is the symptom this whole feature exists to remove, one step further along.
send().catch((error) => {
    console.error('[workshop-capture] the submission failed:', error);
    fail(`The capture could not be sent: ${error.message}`);
});
