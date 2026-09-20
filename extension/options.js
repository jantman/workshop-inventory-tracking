/**
 * The options screen: one value, one action.
 *
 * The accept/reject table it applies is data-model.md's, not this file's:
 * empty is rejected, unparseable is rejected with the reason shown, anything
 * that is not `https` is **saved with a warning** (FR-012), and a valid one is
 * saved. Validation runs against the *normalized* value rather than what was
 * typed, so `https://host/` and `https://host` cannot disagree about whether
 * they parse.
 */

import { normalizeAddress, readAddress, writeAddress } from './storage.js';

const field = document.getElementById('address');
const saved = document.getElementById('saved');
const warning = document.getElementById('warning');
const error = document.getElementById('error');

function say(element, text) {
    element.textContent = text;
    element.hidden = !text;
}

function clear() {
    say(saved, '');
    say(warning, '');
    say(error, '');
}

document.getElementById('version').textContent =
    `Extension version ${chrome.runtime.getManifest().version}`;

readAddress().then((address) => {
    field.value = address;
}).catch((problem) => {
    say(error, `The stored address could not be read: ${problem.message}`);
});

document.getElementById('address-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    clear();

    const address = normalizeAddress(field.value);
    if (!address) {
        say(error, 'Enter the address of your Workshop application.');
        return;
    }

    let parsed;
    try {
        parsed = new URL(address);
    } catch (problem) {
        say(error, `That is not an address: ${problem.message}`);
        return;
    }
    if (!parsed.protocol.startsWith('http')) {
        say(error, `That is not a web address — it says ${parsed.protocol}`);
        return;
    }

    try {
        await writeAddress(address);
    } catch (problem) {
        say(error, `That could not be saved: ${problem.message}`);
        return;
    }
    // Rewritten with what was actually stored, so the operator sees the value
    // a capture will use rather than the one they typed.
    field.value = address;
    say(saved, `Saved. Captures will be sent to ${address}/api/capture`);

    if (parsed.protocol !== 'https:') {
        // Saved, and said. 048 research.md §4: this page is where the mistake
        // is made, which is why the warning belongs here rather than on the
        // application's capture page where it used to be.
        say(
            warning,
            'This address is not https. Capture will very likely fail against '
            + 'it — an extension page is a secure context, and a browser may '
            + 'refuse to submit from one to an insecure address. Serve the '
            + 'application over TLS.',
        );
    }
});
