# Contract: the extension's surface

What the extension presents to the operator, and what its published package declares. The
transport is specified separately in [extension-transport.md](./extension-transport.md).

---

## Declared in the manifest

| Key | Value | Why |
|---|---|---|
| `manifest_version` | `3` | |
| `version` | equal to `pyproject.toml`'s `version` | FR-024; asserted by a test, not generated |
| `permissions` | `scripting`, `storage`, `contextMenus`, `activeTab` | research.md §8 — each load-bearing, nothing else |
| `host_permissions` | **none** | `activeTab` covers injection; host permissions would not help the reader's fetches and would grant standing access |
| `background.service_worker` | the worker | registers the menu, handles both entry points |
| `options_page` | the options screen | FR-009 |
| `action` | toolbar control | FR-015 |

**Not declared, deliberately**: `content_scripts` (nothing runs until the operator asks),
`web_accessible_resources` (nothing is injected from an extension address), `tabs` (opening a
tab does not require it), `unlimitedStorage`.

**The permission list is user-visible** on the install screen. Keeping it to four is not
tidiness — it is the difference between a list a person reads and one they click past.

---

## Entry points

Both do exactly the same thing. Neither carries any state the other does not.

| Entry point | Availability | Requirement |
|---|---|---|
| Toolbar action | Every page | FR-015 |
| Context-menu item | **Only on the sites the extension reads**, via the menu's own URL patterns | FR-016 (SHOULD) |

The context-menu item is the one part of this feature that may be dropped. It is registered by
the service worker and shares the worker's capture routine, so dropping it removes a
registration and nothing else — no capture logic lives behind it.

### What the operator sees when it cannot proceed

These are the contract's most important clauses, because the bug being fixed is *nothing
visibly happening*. Silence is not an acceptable outcome of any of them.

| Situation | Requirement | Behavior |
|---|---|---|
| Address not configured | FR-011 | Say so; open the options screen. |
| Page not recognized | FR-008 | Say so, naming that this is not a page it can read. |
| Reader failed | contract | Say the page could not be read. Do not submit. |
| Reading is slow (an order with many lines) | FR-007 | Show progress on the vendor page while it reads. |

---

## Options screen

One field, one action.

| Element | Behavior |
|---|---|
| Address field | Pre-filled with the stored value when there is one |
| Save | Normalizes, validates, stores — see [data-model.md](../data-model.md#configured-application-address) |
| Insecure-address warning | Shown when the saved address is not `https` (FR-012). Saved anyway; the operator is told, not blocked. |
| Version | The extension's own version is displayed (FR-014), so it can be compared with the application's footer |

Normalization and the accept/reject table live in the data model rather than here, because they
are properties of the stored value rather than of the screen.

---

## Published package

| Property | Value |
|---|---|
| Form | zip of the extension directory |
| Produced by | every ordinary build (FR-022) and every release (FR-023) |
| Install | unzip, then load unpacked |
| Update | replace the files, press reload |
| Signed `.crx` | **not produced** — research.md §10 |

**The install path is part of the contract, not an implementation note.** A signed package
would be refused by Chrome outside its store on two of three major platforms; an unpacked
directory loads everywhere with no key. The documentation page (FR-025) documents the unpacked
path and nothing else.

---

## What this feature removes

Stated here because removal is the larger half of the application-side work.

| Removed | Where |
|---|---|
| `_capture_bookmarklet()` | `app/product/routes.py` |
| `#capture-bookmarklet` control | `app/templates/product/capture.html` |
| `#bookmarklet-http-warning` alert | `app/templates/product/capture.html` |
| The served reader | `app/static/js/capture-agent.js` moves into the extension |
| Bookmarklet-address assertions | `tests/unit/test_proxy_headers.py`, `tests/e2e/test_order_capture.py` |

Replaced by a pointer to the extension on the capture page (FR-018). After this, exactly one
browser transport exists (FR-020).

**The template change requires regenerated screenshots** under the constitution's Development
Workflow section, and CI blocks merge on stale ones.
