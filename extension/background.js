/**
 * The service worker: the whole of the extension's control flow.
 *
 * A capture is four steps, and the order of them is the design (048 research.md
 * §1, §3, §6, §7):
 *
 * 1. Read the configured address. **Without one, stop and say so.** Doing
 *    nothing visible is the symptom of the bug this extension exists to fix, so
 *    there is no path through this file that ends in silence.
 * 2. Inject `capture-agent.js` into the active tab's **isolated world**, which
 *    is documented as carrying its own content policy rather than the host
 *    page's. That is what defeats McMaster's `script-src`, and it is why the
 *    world is never set to `MAIN`.
 * 3. Ask the reader what kind of page it is standing on, then ask it to read.
 *    Both go through `chrome.scripting.executeScript` against the same frame,
 *    which shares one isolated world, so the second and third calls find what
 *    the first defined.
 * 4. Hand the payload to a page of the extension's own, which submits it. The
 *    worker may always open a tab, so nothing here needs transient user
 *    activation and the popup blocker is not in the path at all.
 *
 * **The vendor tab is never navigated away from.** That is a property of step 4
 * and nothing else in the suite would notice it regressing, which is why
 * test_capture_extension.py asserts it directly.
 */

import { readAddress } from './storage.js';

// The sites the context-menu entry is offered on (FR-016). This is the one
// place a host list is unavoidable -- a menu item is scoped by URL patterns or
// it is offered everywhere -- and it is deliberately *not* what decides whether
// a page can be read. That question goes to the reader (see `capture`), because
// two copies of those rules would be two chances for them to disagree.
const MENU_SITES = [
    'https://*.amazon.com/*',
    'https://*.mcmaster.com/*',
];

const MENU_ID = 'workshop-capture';

/**
 * Say something to the operator, on the page they are looking at.
 *
 * A notification would need a permission, and a badge is too quiet for a
 * message that has to be read. This injects a banner into the tab in the same
 * isolated world everything else here uses, so it works on a page whose content
 * policy forbids inline script -- which is the population this extension is for.
 *
 * @param {number} tabId - the tab to say it in.
 * @param {string} text - what to say.
 */
async function tell(tabId, text) {
    try {
        await chrome.scripting.executeScript({
            target: { tabId },
            func: (message) => {
                const banner = document.createElement('div');
                banner.id = 'workshop-capture-message';
                banner.setAttribute('role', 'alert');
                banner.style.cssText =
                    'position:fixed;top:12px;right:12px;z-index:2147483647;'
                    + 'background:#842029;color:#fff;padding:10px 14px;'
                    + 'border-radius:6px;font:14px/1.4 system-ui,sans-serif;'
                    + 'box-shadow:0 2px 8px rgba(0,0,0,.35);max-width:26em';
                banner.textContent = message;
                document.body.appendChild(banner);
                setTimeout(() => banner.remove(), 8000);
            },
            args: [text],
        });
    } catch (error) {
        // A page the extension cannot touch at all -- chrome://, the Web Store,
        // a PDF viewer. There is nowhere to put a banner, so the console of the
        // worker is the only place left to say it.
        console.warn('[workshop-capture] could not report to the tab:', text, error);
    }
}

/**
 * Read `tab` and hand what was read to the submitting page.
 *
 * Shared by both entry points, which is the whole of what makes them identical
 * (contracts/extension-surface.md). Neither carries capture logic of its own.
 *
 * @param {chrome.tabs.Tab} tab - the tab the operator invoked capture on.
 */
async function capture(tab) {
    const address = await readAddress();
    if (!address) {
        // FR-011, and the single most important branch in this file: the bug
        // being fixed is *nothing happening*, so this never returns quietly.
        await tell(
            tab.id,
            'Workshop capture: no application address is configured yet. '
            + 'The options screen is opening — enter the address there.',
        );
        chrome.runtime.openOptionsPage();
        return;
    }

    let kind;
    try {
        await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: ['capture-agent.js'],
        });
        // FR-008. Asked of the reader rather than matched here: `pageKind`'s
        // rules live in one place and this is the second consumer of them, not
        // a second copy (data-model.md, "Supported page kind"). A second call
        // rather than the file's own completion value, so the contract is not
        // hidden in that file's last line (research.md §7).
        const [{ result }] = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => globalThis.workshopCapture.readableKind(),
        });
        kind = result;
    } catch (error) {
        // A page no extension may touch -- chrome://, the Web Store, a PDF
        // viewer -- or one where `activeTab` was never granted.
        await tell(tab.id, 'Workshop capture: this is not a page it can read.');
        console.error('[workshop-capture] could not inject the reader:', error);
        return;
    }
    if (!kind) {
        await tell(
            tab.id,
            'Workshop capture: this is not a page it can read. It reads Amazon '
            + 'listings and order pages, and McMaster-Carr products and orders.',
        );
        return;
    }

    let fields;
    try {
        const [{ result }] = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => globalThis.workshopCapture.capture(),
        });
        fields = result;
    } catch (error) {
        // A reader that cannot find one selector degrades and returns anyway
        // (FR-006). One that cannot run at all lands here, and a partial payload
        // is worse than none -- so nothing is submitted.
        await tell(
            tab.id,
            'Workshop capture: the page could not be read. Nothing was sent.',
        );
        console.error('[workshop-capture] the reader threw:', error);
        return;
    }

    // A single-use key, so two captures started in quick succession cannot
    // overwrite one another. Session rather than local storage: the value is
    // meaningless once submitted and captured vendor data should not outlive the
    // browser session on disk.
    //
    // **The address is deliberately not stored alongside it.** The submit page
    // reads the configured address itself, on every attempt, so that a retry
    // after the operator corrects a wrong address uses the corrected one. An
    // address frozen in here would look authoritative and be stale.
    const key = `capture-${crypto.randomUUID()}`;
    await chrome.storage.session.set({ [key]: { fields } });
    await chrome.tabs.create({
        url: chrome.runtime.getURL(`submit.html?key=${encodeURIComponent(key)}`),
    });
}

/**
 * Start a capture, and let nothing end in silence.
 *
 * `capture` reports every outcome it anticipates. This is the guard for the
 * ones it does not: an unhandled rejection in an event listener is invisible,
 * and invisible is the exact symptom of the bug this extension exists to fix.
 *
 * @param {chrome.tabs.Tab} tab - the tab the operator invoked capture on.
 */
function startCapture(tab) {
    capture(tab).catch(async (error) => {
        console.error('[workshop-capture] the capture failed:', error);
        await tell(
            tab.id,
            'Workshop capture: something went wrong and nothing was sent. The '
            + "extension's service worker console says what.",
        );
    });
}

chrome.action.onClicked.addListener(startCapture);

// FR-016. The registration is the whole of the context-menu entry; its handler
// calls the same routine the toolbar control does, so the two cannot diverge.
// `onInstalled` rather than top level because the worker is restarted often and
// `create` throws on a duplicate id.
chrome.runtime.onInstalled.addListener(() => {
    chrome.contextMenus.create({
        id: MENU_ID,
        title: 'Capture to Workshop',
        contexts: ['page'],
        documentUrlPatterns: MENU_SITES,
    });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
    if (info.menuItemId === MENU_ID && tab) {
        startCapture(tab);
    }
});
