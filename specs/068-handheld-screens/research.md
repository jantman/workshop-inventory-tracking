# Zebra TC52 handheld: research findings

**Date:** 2026-10-18 · **Status:** research input for a future spec · **Device:** ordered, not yet received

## Question

Should the Zebra TC52 use (a) a custom native Android app, (b) dedicated handheld-optimized pages in the existing web app, or (c) the existing pages made to work well on a small screen?

## Recommendation (revised 2026-10-25)

**No native app.** DataWedge keystroke output with an Enter suffix delivers scans into Chrome, and this was verified on the device.

**Purpose-built handheld screens, decided after measuring at 360×512.** The original recommendation was to make the existing pages responsive. Measuring them at the real viewport changed that: every task's controls sit 2–5 screens down, and the Scan box is hidden behind the navbar toggler. The handheld gets its own small set of screens. They reuse the existing JS controllers, JSON APIs and modals, so no business logic is duplicated, only presentation. Anything else falls back to the desktop pages. This deliberately reverses spec 001's assumption that "a separate mobile-specific interface is out of scope".

## Observed on the device (2026-10-23)

- Upgraded to Android 14 with current Chrome.
- The usable Chrome viewport is **360×512 CSS px** in portrait.
- Default DataWedge Profile0 sends no Enter suffix, so the Scan box never submitted. Turning on **Keystroke output > Basic data formatting > Send ENTER key** fixed it. JA ID and WIT product scans both work through the header Scan box.
- The 120 ms no-Enter fallback in `scan-capture.js` does not fire on Android. Chrome reports characters from the input method with `key === "Unidentified"`, so they never enter the buffer (`scan-capture.js:144`). This is inferred from Chrome's input-method behavior and not traced on the device. The Enter suffix makes it moot, but the dependency should be documented.

## Decisions so far

- **Entry point (2026-10-23):** a dedicated handheld landing page. Jason will bookmark it on the handheld's home screen and set it as the browser's home page.
- **Handheld task scope (2026-10-23):** the handheld handles only these tasks (numbers from the app task inventory):
  - 1: scan
  - 12: shorten an item
  - 13: move items
  - 16: print item label
  - 17: item photos
  - 22: product quantity and counting
  - 23: product stock status
  - 24: move products
  - 25: print product label
  - 26: product attachments
  - 32: receive a purchase
  - 33: receive from a captured order
- **Purpose-built screens (2026-10-25):** yes, as described in the plan below. They fall back to the desktop pages for anything else.
- **Task 33 (2026-10-25):** both receiving one line per scanned bag, and selecting lines in bulk from the order on the handheld. So the order needs its own handheld screen.
- **Photos (2026-10-25):** keep Android's chooser (camera or files), as today. No `capture` attribute.
- **Orders on the handheld (2026-10-25):** an order is opened by scanning, from a list of orders with outstanding lines linked from the landing page, or from an Order button on the product screen.
- **Soft keyboard (2026-10-25):** it rises when the header Scan box is tapped (observed). Handheld scan entries suppress it, and a keyboard button lets you type a code by hand.
- **Tests (2026-10-25):** the handheld screens get e2e coverage at a 360×512 touch viewport.

## Proposed handheld screens

All share a compact header with an always-focused scan input, no navbar, and the primary action fixed at the bottom of the screen.

| Screen | Tasks | Reuses |
|---|---|---|
| Landing | 1, plus buttons for the tasks | `/api/scan`; outcomes map to handheld URLs |
| Item | 16, 17, and links to 12 and 13 | item label modal (fits as-is); photo upload API and compression |
| Product | 22, 23, 25, 26, and a link to 24 | Stock card controls (good touch sizes; extract into a shared partial); product label modal, with the help text hidden at small widths; attachment API |
| Shorten | 12 | shorten endpoint |
| Move | 13, 24 | `move-manager.js`; the queue shown as a list rather than a table |
| Receive | 32, and 33 one line per scanned bag | receive endpoint; the `receive` scan outcome |
| Order | 33, bulk | order receive endpoint; lines shown as cards with large select targets |

## Survey at 360×512 (2026-10-23)

This used the e2e infrastructure: headless Chromium with a touch context at DPR 2 and seeded data. y-positions are in CSS px; the fold is at 512.

- **Navbar:** 56 px tall. The header Scan box is hidden behind the toggler on every page, and it captures input only while focused.
- **JA scan landing page:** `/inventory/edit/<ja>` overflows to 502 px wide because of its header button group. Photos are at y≈1396.
- **Product detail:** the Stock card is at y≈2192 and the status buttons at y≈2599. Attachments upload is at y≈1990. The controls themselves are touch-sized (−/+ 149×49).
- **Shorten:** the JA field is at y=284 (fine). Execute is at y=2192 after the item loads.
- **Move:** the barcode input is at y=284. Execute is at y≈1065–1367. The queue table scrolls sideways (440 px wide in a 296 px box). Warnings stack above the input.
- **Receive purchase:** the form starts at y≈812. Confirm is at y=1376.
- **Captured order:** rows are about 400 px tall, checkboxes 14 px, and the table scrolls sideways (506 px in 330 px). Receive Selected is at y=609.
- **Label modals:** the item modal is 373 px tall and fits. The product modal is 538 px tall, so Print is partly below the fold.
- **Recurring small targets:** default buttons 35 px, inputs 38 px, checkboxes 14–16 px.

## Device facts

Sourced from Zebra spec sheets, release notes and techdocs. Full citations are in [Sources](#sources).

| | TC52 / TC52 HC | TC52x | TC52ax |
|---|---|---|---|
| Part-number prefix | `TC520K-1P` / `-1H` | `TC520K-1X` | `TC520L-1Y` |
| Display | 5" 1280×720 | 5" 1920×1080 | 5" 1920×1080 |
| Scan engine | SE4710 1D/2D | SE4720 | SE4720 or SE55 long range |
| Wi-Fi security | WPA2 (WPA3 unconfirmed) | WPA3 | WPA3, Wi-Fi 6 |
| Last sale / support end | 2024-10-31 / 2028-12-31 | 2025-10-31 / 2029-12-31 | same as TC52x |

- **OS ceiling:** all variants are covered by Zebra's Android 14 GMS LifeGuard builds. Upgrading from Android 11 or earlier to 13 or 14 forces a data reset because of the change from FDE to FBE encryption. That doesn't matter for this use. Downloading LifeGuard packages may need a Zebra support entitlement (unverified).
- **Chrome:** current Chrome requires Android 10 or later. Chrome 138 was the last version for Android 8 and 9. A unit still on Oreo or Pie is stuck on old Chrome until it is upgraded. `-CN` SKUs are AOSP and have no Chrome. A used ex-enterprise unit may also arrive in GMS Restricted mode or with leftover MDM policy; a factory reset should clear this.
- **Viewport:** about 360 CSS px wide in portrait on the 720p TC52, and about 411 px on the 1080p models. This is inferred and must be measured on the device.
- **Other hardware:** 13 MP rear camera, NFC, glove touch mode, warm-swap battery, and programmable keys through Zebra Key Programmer.
- **Plain HTTP on the LAN:** Chrome's HTTPS-by-default change (Chrome 154, Oct 2026) exempts private IPs and single-label hostnames. `.local` mDNS names should resolve on Android 13 and 14, but this is unverified on Zebra builds. Use the IP address or a router DNS entry as a fallback.

## How scanning reaches the web page (DataWedge)

- **Keystroke Output** types the data into the focused field. You can configure:
  - a prefix and a suffix
  - Send ENTER and Send TAB
  - inter-character delay and key event delay. These fix dropped or reordered characters; increase them in steps of 100 ms.
  - "Send Control Characters as Events"
  - the "DataWedge keyboard" option, which stops the soft keyboard flashing on Android 10 and later during continuous scanning
- **Profiles:** create one bound to `com.android.chrome` in the on-device DataWedge app. No MDM is needed. A profile can be exported as `dwprofile_<name>.db` and re-imported, so it can be kept alongside the app's docs.
- **Key-event mode:** with "Send Characters as Events", a page can capture scans from `keypress` on `document` without any input having focus. This isn't needed today but is an option if focus management turns out to be fragile.
- **Not usable from a web page:** Intent Output, which needs a native app; IP Output, which is unsupported for third-party listeners; and Zebra Enterprise Browser, which is paid and adds proprietary JS APIs.
- **Avoid** `alert()` and other blocking dialogs in scan handlers. They have been reported to stall keystroke input in Chrome.

## What the app has today

- **Stack:** server-rendered Jinja templates, Bootstrap 5.3 and vanilla JavaScript. The viewport meta tag is present. There are 576/768/992px breakpoints in `app/static/css/main.css`. There is no PWA manifest or service worker. Bootstrap and the other JS libraries load from CDNs, so the device needs internet access as well as the LAN.
- **Scanning is keyboard-wedge only, and Enter-terminated:**
  - **Global scan input:** `#global-scan-input` uses `app/static/js/scan-capture.js`. It flushes on Enter, or after 120 ms of silence following a machine-speed burst. It rebuilds Ctrl-key events into GS, RS and EOT control characters for DigiKey 2D labels. It posts to `POST /api/scan`, which is routed by `app/utils/scan_router.py`.
  - **Move pages:** Move (inventory and product) shares `app/static/js/move-manager.js` and `app/templates/move/_scan_move.html`. The flow is: scan an item, then scan a location, then optionally a sub-location. Scanning `>>DONE<<` ends the session.
  - **Shorten page:** `app/static/js/inventory-shorten.js` reads a JA ID terminated by Enter.
  - **Navbar lookup:** the `#ja-id-lookup` input goes to the item edit page.
- **Labels:** JA ID labels are Code128 by the library default; the default is not overridden. Product labels are Code128 `WIT` + 10 characters. Location codes like `M1-A` are plain strings.
- **Photos:** the file input has no `capture` attribute. On Android a file input normally offers the camera, and this works over plain HTTP.
- **API:** JSON endpoints under `/api/*` have no auth. CSRF exemption is per route (`@csrf.exempt` on some routes in `app/main/routes.py`), not blanket, despite what `docs/deployment-guide.md` says. This only matters if a native client is ever built.
- **Serving:** gunicorn on plain HTTP port 5000. Camera access via `getUserMedia`, service workers and PWA installation all need HTTPS. None of them is needed for the recommended approach. The deployment guide already documents a TLS reverse proxy for when one is needed.

## Gaps for handheld use

These are the candidate requirements for the spec, most valuable first.

1. **Scan entry points are hidden on a phone-width screen.** The navbar collapses below 992px, so both `#global-scan-input` and `#ja-id-lookup` are behind the toggler. A handheld user should be able to scan without opening a menu. For example, a persistent scan bar or a scan-first home page at small widths.
2. ~~**The global scan doesn't recognize JA IDs.**~~ Done in feature 067 (v2.6.0): the header Scan box routes JA IDs to the item, and the separate JA ID Quick Lookup was removed.
3. **Mobile e2e coverage stops at the product pages.** Extend the touch/viewport e2e coverage to the inventory pages that matter at a shelf: Move, Shorten, item edit/view, product Move and Receive. Test at 360 px, not only 390 px, and assert no horizontal overflow or clipped controls.
4. **Wide tables are unusable at 360 px.** These are `inventory/_item_table.html` (about 12 columns) and `product/search.html` (8 or more). Options:
   - a stacked card layout below 576 px
   - hiding low-priority columns at small widths
   - accepting horizontal scroll
   
   This is a design decision for the spec. Lists are less important on the handheld than the scan flows.
5. **The soft keyboard pops up over scan-only fields.** When Move or Shorten autofocuses the scan input, Android raises the soft keyboard and covers half the screen. Options:
   - the DataWedge keyboard option, a device setting with no code change
   - `inputmode="none"` with a tap-to-type toggle
   
   Decide after testing on the device. Prefer the device setting if it is enough.
6. **Long forms on a small screen.** Add Item and Edit Item are long. Make sure they are usable, not optimized: one column, large tap targets, the submit button reachable. Adding items is mostly a bench task.
7. **DataWedge setup is not documented.** Add a short section to `docs/user-manual.md` covering:
   - the Chrome-bound profile
   - Enter suffix
   - enabled symbologies (Code128, plus DataMatrix and QR for distributor labels)
   - control characters as events, for DigiKey GS/RS
   - the delay values that proved reliable
   - where the exported `.db` profile is kept
8. **Done barcode.** The `>>DONE<<` code must be printed somewhere reachable, such as a laminated card or a label on the device. Alternatively, a hardware key could be mapped to it through Key Programmer, or the page could offer a large Done button. Confirm a Done button exists and is reachable at 360 px.

**Out of scope, per project principles:** a native app, PWA/offline mode, camera barcode scanning in the browser (redundant with the hardware imager and would need TLS), Enterprise Browser, MDM/kiosk lockdown, and auth on the API.

## To verify when the device arrives

Run these before writing the spec. Several of the gaps above depend on the answers.

1. Model and part number. Check it isn't a `-CN` (AOSP) unit.
2. OS build (Settings > About). The prefix `14-…-UG` means Android 14 and `11-…-RG` means Android 11. Plan the LifeGuard upgrade if it is below Android 10.
3. Chrome is present and enabled, with no leftover MDM or Enterprise Home Screen lockdown.
4. `window.innerWidth` and `devicePixelRatio` in Chrome, portrait.
5. With default Profile0, scan a JA ID label into the navbar lookup and into the Move page. Check that characters arrive complete and that Enter is sent. Then the same for a DigiKey 2D label into the global Scan box, which tests GS/RS handling via Ctrl-key events.
6. Whether Move and Shorten work at full scan speed with 0 ms delays, or need inter-character or key event delay.
7. Soft keyboard behavior on autofocused scan inputs, with and without the DataWedge keyboard option.
8. Whether `http://<host>.local:5000` resolves, or only the IP.
9. Whether the photo file input offers the camera.
10. Battery health.

## Sources

- TC52/TC57 spec sheet: https://www.zebra.com/us/en/products/spec-sheets/mobile-computers/handheld/tc52-tc57.html
- TC52x/TC57x spec sheet: https://www.zebra.com/us/en/products/spec-sheets/mobile-computers/handheld/tc52x-tc57x.html
- Android 14 release notes (14-26-08.00-UG-U00): https://www.zebra.com/content/dam/support-dam/en/documentation/unrestricted/release-notes/HE_FULL_UPDATE_14-26-08.00-UG-U00-STD-HEL-04.pdf
- LifeGuard A13 / A14 upgrade paths: https://techdocs.zebra.com/lifeguard/a13/ and https://techdocs.zebra.com/lifeguard/a14/
- Support lifecycle:
  - https://www.zebra.com/us/en/support-downloads/mobile-computers/handheld/tc52.html
  - https://www.zebra.com/us/en/support-downloads/mobile-computers/handheld/tc52x.html
- Chrome Android requirements: https://support.google.com/chrome/a/answer/7100626
- GMS Restricted mode: https://techdocs.zebra.com/mx/gmsmgr/
- DataWedge:
  - Keystroke Output: https://techdocs.zebra.com/datawedge/latest/guide/output/keystroke/
  - Basic data formatting: https://techdocs.zebra.com/datawedge/latest/guide/process/bdf/
  - Profiles: https://techdocs.zebra.com/datawedge/latest/guide/profiles/
  - Settings import/export: https://techdocs.zebra.com/datawedge/latest/guide/settings/
  - IP Output: https://techdocs.zebra.com/datawedge/latest/guide/output/ip/
- DataWedge key events in a browser: https://developer.zebra.com/blog/listening-keypress-events-datawedge
- EMDK vs. DataWedge: https://developer.zebra.com/blog/moving-emdk-data-capture-profile-datawedge
- Enterprise Browser: https://techdocs.zebra.com/enterprise-browser/latest/guide/about/
- Enterprise Home Screen: https://techdocs.zebra.com/ehs/latest/guide/about/
- Chrome HTTPS-by-default: https://blog.google/security/https-by-defau/
- Android mDNS resolver: https://source.android.com/docs/core/architecture/modular-system/dns-resolver
