# Research: Browser Capture Extension

All of this feature's unknowns were mechanical questions about the extension platform. Every
one is now closed; there are no `NEEDS CLARIFICATION` items remaining.

The load-bearing result is §1 together with §3: the reader runs in an **isolated world**, which
is documented as exempt from the host page's content policy, and the submission moves **off the
vendor page entirely**, which removes the popup-blocker risk the specification flagged rather
than betting on it.

---

## 1. The isolated world is what defeats McMaster's policy — not the main world

**Decision**: The reader is injected with the default `ISOLATED` execution world. It is never
injected into the page's main world.

**Rationale**: Chrome's content-script documentation states that a content script running in an
isolated world carries *its own* policy — "Content scripts running in isolated worlds have the
following Content Security Policy (CSP): `script-src 'self' 'wasm-unsafe-eval'
'inline-speculation-rules' chrome-extension://…`" — and, in the same breath, that "when a
content script is injected into the main world, the CSP of the page applies."

That sentence is the whole fix. McMaster's `script-src` is what refuses the bookmarklet's
subresource today; an isolated-world injection is never measured against it. The isolated world
shares the page's DOM, which is all the readers need.

Choosing the main world would reintroduce exactly the bug this feature exists to close. Several
third-party write-ups describe main-world injection as a policy bypass; the official
documentation contradicts them, and where they disagree the documentation governs. There is no
reason to take the risk: nothing in the readers needs the page's JavaScript variables, only its
DOM.

**Alternatives considered**:

- **Main world (`world: "MAIN"`)**, so the reader sees page globals. Rejected: subject to the
  page's policy per the documentation, and no reader needs page globals.
- **A statically declared content script** that runs on every matching page load. Rejected: it
  would run the reader on every Amazon and McMaster page the operator visits, where today
  nothing runs until they ask for it. Injection on demand preserves the bookmarklet's
  semantics exactly.

## 2. The reader's own network reads keep working, unchanged

**Decision**: `canonicalDocument()` and `readListing()` keep their same-origin `fetch` calls
exactly as written. No host permissions are declared for the vendor domains, and no fetch is
relayed through the service worker.

**Rationale**: This was the one place an isolated world could have changed behavior, because
Chrome 85 removed content scripts' ability to bypass CORS. It does not bite here. Chromium's
own write-up of that change is explicit that a content script keeps the page's origin for
network purposes: cross-origin fetches from a content script "will have an `Origin` request
header with the page's origin", and host permissions do not lift CORS in that context.

Both of this feature's fetches are **same-origin** — `https://www.amazon.com/dp/<ASIN>` read
from a document already on `https://www.amazon.com/…`. A same-origin fetch from an
isolated-world content script behaves as the page's own would, cookies included, which is
precisely what today's bookmarklet-injected code does. The code is copied across untouched.

This is also covered by the existing tests rather than taken on trust: the end-to-end fixtures
serve the listing, the order page and the images from the application's own origin, so the
`/dp/<ASIN>` re-read is exercised on every run.

**Alternatives considered**:

- **Relay every fetch through the service worker** (the standard advice when CORS bites).
  Rejected: it is the remedy for a problem that does not occur here, it would add a message
  round trip per order line, and it would change the request's origin and credential handling —
  the one thing FR-003 says must not change.
- **Declare `host_permissions` for the vendor domains.** Rejected: does not help (host
  permissions do not lift CORS for content scripts), and it would grant the extension standing
  access to those sites where `activeTab` grants it only when the operator asks.

## 3. The submission moves off the vendor page, which retires the popup-blocker risk

**Decision**: The vendor page no longer builds or submits the form. The reader returns its
payload to the service worker; the worker stores it and opens a tab on a page belonging to the
extension; **that** page builds the form and submits it to the configured application address,
as an ordinary same-tab navigation.

**Rationale**: The specification flagged one known risk — a form submitted into a new tab needs
transient user activation to clear the popup blocker, and it is not established that a toolbar
or context-menu click confers activation on a script injected with `chrome.scripting`. Chromium
has carried a request to pass the user gesture through `executeScript` for years, which is
itself evidence that it does not happen today.

Rather than test that and depend on the answer, the design removes the question. An extension's
service worker may always open a tab; no activation is involved. The page it opens then submits
a form **in its own tab**, which is a plain top-level navigation and is not a popup at all.
Nothing in the path can be blocked.

Three things fall out of this, and all three are improvements:

- **`upgrade-insecure-requests` stops applying.** The document initiating the submission is now
  the extension's own page, not Amazon's, so the header that broke the transport in issue #54
  is no longer in play. This is not relied upon and the TLS requirement is retained regardless
  (§4), but it removes a class of vendor interference from the path.
- **The landing tab need not be opened up front.** Today the Amazon order path opens a blank
  tab before reading, purely to spend the click's activation before it expires. With no
  activation to spend, the tab is opened after reading completes, when its address is known.
  `showProgress`'s second job — writing status into that blank tab — disappears with it.
- **The operator keeps the vendor tab.** It is never navigated away from.

**Alternatives considered**:

- **Keep `submitCapture()` on the vendor page with `target="_blank"`**, as today. Rejected: it
  is the option that depends on the unresolved activation question, and a wrong answer is a
  silently blocked capture — the same symptom as the bug being fixed.
- **Submit in the vendor's own tab**, no target. Rejected: it works and needs no activation,
  but it navigates away from the page the operator is reading, and it aborts the Amazon order
  path's in-flight per-line reads.
- **Have the service worker POST and then render the result.** Rejected: the endpoint answers a
  form submission with a rendered page, so the worker would have to either re-issue the request
  from the tab or have the application store the capture first — a change to the endpoint's
  contract, which FR-003 forbids.

## 4. TLS is still required, and is still stated at the point of configuration

**Decision**: The application must be reachable over `https` for capture to work. The options
screen warns when the address entered is not secure. The requirement is unchanged from today
and is not something this feature tries to remove.

**Rationale**: This is a settled decision of the project owner, recorded in the specification's
Out of Scope. §3 notes that the mechanism which forced it may no longer apply now that the
submitting document is the extension's own page — but an extension page is itself a secure
context, so a submission from it to a plain-`http` address is a downgrade the browser may well
refuse anyway. The honest position is that the requirement is retained and untested against,
not quietly dropped on a theory.

Stating it where the address is typed (FR-012) is the whole of the mitigation, and it is a
strict improvement on today: the current warning appears on the application's capture page,
which is not where the mistake is made.

## 5. Where the address lives, and how it reaches the reader

**Decision**: `chrome.storage.sync`, one key holding the application's base address. The
service worker reads it when a capture is invoked. The reader never sees it.

**Rationale**: `sync` and `local` are the same interface; `sync` additionally carries the value
to the operator's other browsers, which for a single-operator tool is a free convenience and
costs nothing when the profile is not signed in — it degrades to local storage.

The reader not seeing the address is a simplification over today. The bookmarklet had to smuggle
the endpoint in on a `data-endpoint` attribute because the reader was also the submitter. Now
the reader only reads and the submitting page reads the address itself, so the attribute, its
absence check, and the "no endpoint" console error all go away.

**Normalization** (FR-013) happens once, on save: trim surrounding whitespace, strip trailing
slashes. The stored value is a bare origin, and the submitting page appends the known path.

**Alternatives considered**:

- **`chrome.storage.local`.** Equivalent; `sync` was preferred only for roaming.
- **Keep passing the address into the reader**, preserving today's shape. Rejected: it exists
  only because the reader used to submit, and it no longer does.

## 6. Handing the payload from the reader to the submitting page

**Decision**: `chrome.scripting.executeScript` returns the payload to the service worker; the
worker writes it to `chrome.storage.session` under a single-use key and opens the submitting
page with that key in its address. The page reads it, submits, and deletes the key.

**Rationale**: `executeScript` awaits a promise the injected function returns and delivers the
settled value in the injection result — documented behavior since Chrome 90. That is exactly
the shape the Amazon order path needs, since it reads each line's listing asynchronously before
the payload is complete.

The payload is far too large for an address fragment (an Amazon order with its per-line listings
runs to tens of kilobytes), so it travels through session storage, whose quota is an order of
magnitude larger than anything this produces. Session storage is the right tier: the value is
meaningless after the submission and should not outlive the browser session.

A single-use key rather than a fixed one so that two captures started in quick succession cannot
overwrite each other.

**Alternatives considered**:

- **Message the newly opened tab directly.** Rejected: requires waiting for the tab to be ready
  to receive, which is more moving parts than writing a value before opening it.
- **`chrome.storage.local`.** Rejected: outlives the session for no reason, and leaves captured
  vendor data on disk after it has been used.

## 7. Injecting the reader: two calls, not a clever one

**Decision**: The service worker injects `capture-agent.js` by file, then makes a second
`executeScript` call whose function invokes the entry point the first call defined. The second
call's result is the payload.

**Rationale**: Isolated-world state persists between injections into the same frame, so the
second call sees what the first defined. The alternative — relying on a file's last evaluated
statement being the completion value — works but hides the contract in the file's final line,
where an edit could silently break it.

This also fixes the reader's shape. `capture-agent.js` today ends in a self-executing dispatch
block that reads `document`, `location`, `window` and `document.currentScript`. That block is
replaced by an entry function taking no arguments and returning the payload, which reads
`document` and `location` itself. **Every reader above it is untouched** — they are already
parameterized over a document and a URL, which is what makes this a small change to a large
file.

## 8. Permissions: four, and no host permissions

**Decision**: `scripting`, `storage`, `contextMenus`, `activeTab`. No `host_permissions`, no
`tabs`, no `web_accessible_resources`.

**Rationale**: Each is load-bearing and nothing else is. `activeTab` grants the host access
`executeScript` needs, and it is granted precisely by the gestures this feature uses — an action
click, a context-menu click, or a keyboard shortcut — which means the extension has no standing
access to any site. `chrome.tabs.create` does not require the `tabs` permission; that permission
governs reading a tab's address and title, which nothing here does. Nothing is injected into the
page from an extension address, so no resource needs to be web-accessible.

This is a smaller permission set than the bookmarklet's replacement is likely to be assumed to
need, and it is worth keeping small: the install screen lists them, and a short list is one a
person can actually read.

## 9. Driving a real extension in the test suite

**Decision**: Extensions require `launch_persistent_context`; the few tests that load the packed
extension use it with `channel="chromium"` so they still run headless. Every other capture test
keeps the existing `page` fixture and injects the reader from the file on disk.

**Rationale**: Playwright is explicit that "extensions only work in Chromium when launched with
a persistent context", and that the `chromium` channel "allows to run extensions in headless
mode". The extension's identifier is recovered from its service worker
(`context.service_workers[0].url`), which is what makes its options page addressable from a
test.

The split is the specification's stated assumption and the reason for it stands: about 158
existing tests reach the readers through the bookmarklet today, and putting all of them behind a
different browser launch mode would risk the suite's largest file to gain nothing — those tests
are about what the readers extract and what the application does with it, neither of which the
extension changes.

**What the injected-reader tests give up, stated plainly**: they no longer exercise the form
submission, because the submission has moved to the extension's own page (§3). They drive the
reader, take its payload, and post it the way the extension's page will. That divergence is
real, it is one small function wide, and it is covered by the extension-loading tests instead —
which is the honest place for it, since that page only exists inside the extension.

**Alternatives considered**:

- **Run the whole suite under a persistent context with the extension loaded.** Rejected:
  changes the launch mode for ~158 tests to cover plumbing that a handful can cover, and a
  persistent context per test is markedly slower than the shared browser the suite uses now.
- **Keep the bookmarklet solely as a test driver.** Rejected: FR-020 requires exactly one
  transport, and a transport that exists only for tests is one nothing verifies in production.

## 10. Packaging, publishing, and keeping the versions together

**Decision**: CI zips the `extension/` directory. `test.yml` gains a job that uploads it with
`actions/upload-artifact`, mirroring `docker-build`. `release.yml` attaches the same zip to the
release through the `softprops/action-gh-release` step it already runs. A unit test asserts
`manifest.json`'s version equals `pyproject.toml`'s.

**Rationale**: This is the shape the project already uses for the container image, which is what
the owner asked for, and it reuses both workflows' existing machinery rather than adding any.

No signed `.crx` is produced. Signing would mean managing a key in order to make an artifact
Chrome refuses to install outside its store on Windows and macOS, whereas an unpacked directory
loads on every platform with no key and no listing. The documented install is therefore
"download, unzip, load unpacked", and the documented update is "replace the files, press
reload".

**Version agreement is a test, not a build step** (FR-024). A test fails loudly in CI on the
pull request that introduced the mismatch; a build step that stamps the manifest would make the
working tree's manifest permanently wrong and would have to run before anyone could load the
extension unpacked during development. The manifest's version format — one to four
dot-separated integers — accepts the project's current `2.0.0` directly, so no translation is
needed. A release that changes the readers therefore ships a new extension version by the same
act that ships a new application version, which is what FR-026 describes.

**Alternatives considered**:

- **Generate `manifest.json` at build time** from `pyproject.toml`. Rejected as above: the
  checked-in directory must be loadable unpacked without running a build.
- **A separate workflow for the extension.** Rejected: two more places for the packaging to
  drift from the image's, when both existing workflows already have the step shapes needed.

---

## Sources

- [Content scripts — Chrome for Developers](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts) (isolated-world CSP; main-world CSP)
- [chrome.scripting — Chrome for Developers](https://developer.chrome.com/docs/extensions/reference/api/scripting) (promise awaiting; `world`; permissions)
- [Changes to Cross-Origin Requests in Chrome Extension Content Scripts — Chromium](https://www.chromium.org/Home/chromium-security/extension-content-script-fetches/) (content-script fetches carry the page's origin)
- [Cross-origin network requests — Chrome for Developers](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests)
- [User gesture should be passed through executeScript — Chromium issue 340816](https://bugs.chromium.org/p/chromium/issues/detail?id=340816) (the activation gap §3 designs around)
- [Making user activation consistent across APIs — Chrome for Developers](https://developer.chrome.com/blog/user-activation) (transient activation and popups)
- [Chrome extensions — Playwright Python](https://playwright.dev/python/docs/chrome-extensions) (persistent context; `channel="chromium"` for headless; extension id from the service worker)
