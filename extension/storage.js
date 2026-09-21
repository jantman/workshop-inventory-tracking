/**
 * The extension's entire configuration: where this operator's application is.
 *
 * `chrome.storage.sync` rather than `local` only for roaming -- the interface is
 * the same, and it degrades to local storage on a profile that is not signed in.
 *
 * Normalization happens **on write and nowhere else** (048 FR-013). The stored
 * value is a bare origin and `submit.js` appends the endpoint path to it, so
 * anything the operator's address bar carried past the origin -- a trailing
 * slash, but also the path of whatever page they copied it from -- has to come
 * off here or the POST goes somewhere that does not exist. Doing it here rather
 * than at each read is what makes a pasted address work without every caller
 * remembering to.
 */

const ADDRESS_KEY = 'applicationAddress';

/**
 * The configured address, or '' when none has been stored.
 *
 * @returns {Promise<string>}
 */
export async function readAddress() {
    const stored = await chrome.storage.sync.get(ADDRESS_KEY);
    return stored[ADDRESS_KEY] || '';
}

/**
 * Reduce an address to the bare origin the data model says is stored.
 *
 * Trimming and stripping a trailing slash is not enough. The documentation
 * tells the operator to paste straight from the address bar, and an address bar
 * showing this application is showing a *page* of it -- so
 * `https://host:15603/products/capture` is the realistic paste, and appending
 * `/api/capture` to it composes an address that 404s on every capture with
 * nothing to say the stored value was the problem. `URL.origin` is what
 * actually implements "scheme, host, optional port; no path".
 *
 * **Only an http(s) address is reduced.** `URL.origin` answers the string
 * `'null'` for a scheme it does not recognize -- `httpx://host` parses -- and
 * storing `'null'` would turn a mistyped scheme into an unreadable parse error
 * two steps later. Anything else falls through to the trim, and `options.js`
 * reports the scheme or the parse failure itself.
 *
 * Exported separately from `writeAddress` so the options screen can validate
 * what it is about to store rather than what the operator typed -- `https://x/`
 * and `https://x` must not be able to disagree about whether they parse.
 *
 * @param {string} entered - what the operator typed.
 * @returns {string}
 */
export function normalizeAddress(entered) {
    const trimmed = (entered || '').trim();
    try {
        const parsed = new URL(trimmed);
        if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
            return parsed.origin;
        }
    } catch (problem) {
        // Not an address at all. `options.js` says so, with the reason.
    }
    return trimmed.replace(/\/+$/, '');
}

/**
 * Store an address, normalized.
 *
 * @param {string} entered - what the operator typed.
 * @returns {Promise<string>} what was actually stored.
 */
export async function writeAddress(entered) {
    const address = normalizeAddress(entered);
    await chrome.storage.sync.set({ [ADDRESS_KEY]: address });
    return address;
}
