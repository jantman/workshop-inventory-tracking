/**
 * The extension's entire configuration: where this operator's application is.
 *
 * `chrome.storage.sync` rather than `local` only for roaming -- the interface is
 * the same, and it degrades to local storage on a profile that is not signed in.
 *
 * Normalization happens **on write and nowhere else** (048 FR-013). The stored
 * value is a bare origin and `submit.js` appends the endpoint path to it, so a
 * value carrying a trailing slash would compose `https://host//api/capture`.
 * Trimming here rather than at each read is what makes a pasted address-bar
 * value work without every caller remembering to.
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
 * Normalize an address as it is typed: trim, then strip trailing slashes.
 *
 * Exported separately from `writeAddress` so the options screen can validate
 * what it is about to store rather than what the operator typed -- `https://x/`
 * and `https://x` must not be able to disagree about whether they parse.
 *
 * @param {string} entered - what the operator typed.
 * @returns {string}
 */
export function normalizeAddress(entered) {
    return (entered || '').trim().replace(/\/+$/, '');
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
