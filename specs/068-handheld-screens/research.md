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

## Phase 0 design decisions (2026-10-25)

Written during `/speckit-plan`. Code references are to `main` at `e5c2bd9`.

### D1. Where handheld routes live

- **Decision**: a new `handheld` blueprint, `app/handheld/`, with `url_prefix='/h'`. It is registered in `app/__init__.py` beside `main`, `admin` and `product` (`app/__init__.py:152-158`).
- **Rationale**: the `/h/` prefix comes from one place, and the desktop route modules stay as they are apart from extracted helpers. The constitution allows routes in a blueprint package.
- **Alternatives**:
  - Spread handheld routes across `main` (item, shorten, move items) and `product` (product, move products, receive, orders). Rejected: the prefix would be repeated in nine decorators, and the handheld would have no single place to read.
  - A separate app. Rejected as scale machinery.

### D2. Mapping scan outcomes to handheld screens

- **Decision**: `POST /api/scan` accepts an optional `"handheld": true` (contracts/scan-api.md).
  - Resolution is untouched. `service.scan(scan)` runs exactly as today.
  - Only the URL chosen in `api_scan` (`app/product/routes.py:2652`) changes: `item` goes to `handheld.item`, `product` to `handheld.product`, and `receive` to `_receive_url(resolution, handheld=True)`.
  - `create` and `search` keep their desktop URLs (FR-003).
  - `scan-capture.js` sends the flag when its input has `data-scan-capture="handheld"`. The desktop's bare `data-scan-capture` sends the same body as today.
- **Rationale**: `_receive_url` (`app/product/routes.py:2723`) holds the three-way receive rule:
  - one outstanding line goes to its receipt, with `quantity` from the label's `Q` field;
  - several lines go to the choice page for vendors with `LANDING_CHOICE_PAGE` (McMaster, Amazon), and otherwise to the order screen with `highlight`;
  - none outstanding flashes "already received" and goes to the order screen.

  Keeping that rule on the server and swapping only the endpoint names keeps one resolution rule. `scan-capture.js:193` already navigates to whatever `url` comes back.
- **Alternatives**:
  - Map client-side from `payload.outcome` and `payload.purchases`. Rejected: the receive branching would be re-implemented in JS, giving two copies of 029 FR-038 to FR-040.
  - A separate `/api/h/scan`. Rejected: it is a second endpoint for one flag.
  - Rewrite URLs client-side (`/inventory/edit/X` to `/h/item/X`). Rejected: string surgery on URLs, and it cannot handle `receive`.

### D3. The handheld base template

- **Decision**: `handheld/base.html` extends `base.html`. `base.html` gains three blocks:
  - `{% block navbar %}` around the existing `<nav>`
  - `{% block footer %}` around the `<footer>`
  - an empty `{% block styles %}` after `main.css`

  The handheld base overrides `navbar` with a sticky compact header (Home, scan input, keyboard button), `footer` with nothing, `styles` with `handheld.css`, and `main_container_class` with `handheld-main container-fluid px-2`. It defines `screen` and `action_bar` blocks. The action bar is `position: fixed; bottom: 0`, and the main area gets matching bottom padding.
- **Rationale**: the handheld still needs everything else `base.html` carries:
  - the `csrf-token` meta and `csrf.js`
  - Bootstrap CSS and JS
  - icons
  - PhotoSwipe, browser-image-compression and pdf.js
  - `main.js` (`showToast`, which `photo-manager.js:9` uses instead of `alert`)
  - `photo-manager.js`, `scan-capture.js`
  - flash messages

  Extending the base means none of that is copied and none of it can drift. Default block contents render the same HTML for desktop pages.
- **Alternatives**: a standalone handheld base. Rejected: it would copy about 40 lines of CDN tags and script includes that would drift. `main.js` is null-safe without the navbar (`main.js:36`), so it can load as-is.

### D4. Which input is the "scan entry" on each screen

- **Decision**:
  - Landing, item, product, receive, receive-choice, order list and order screens: the scan entry is the header input `#handheld-scan-input` with `data-scan-capture="handheld"`, resolved per D2.
  - Move: the scan entry is move-manager's `#barcode-input`, placed in the header slot. No header scan input is rendered.
  - Shorten: the scan entry is `#source-ja-id`, placed the same way.
- **Rationale**: on Move, a scan is a subject, a location, a sub-location or `>>DONE<<`. If it were resolved by `/api/scan`, a location scan would land on product search. On Shorten, a JA ID scan means "shorten this", not "open its item screen". Two scan inputs on one screen would compete for focus.
- **Spec impact**: US1 scenario 6 and FR-002/FR-003 say "any handheld screen" handles a scan "the same way as on the landing page". That holds for the seven screens above. On Move and Shorten, scans are the task's own input, and Home is one tap away (FR-005). This is reported back to the user as an interpretation.

### D5. Reusing the move controller

- **Decision**: a new `handheld/move.html` carries every element ID that `MoveManager` binds (`move-manager.js:89-186`; list in contracts/controller-markup.md). It loads `move-manager.js` plus `inventory-move.js` or `product-move.js`, chosen by `?kind=items|products`. Hand-off uses the same helpers as desktop: `resolve_handoff(ja_id)` and `resolve_product_handoff(code)`. The layout:
  - `#barcode-input` in the sticky header
  - `#form-alerts` directly under it, height-capped so warnings scroll inside it instead of pushing the input away (FR-019)
  - the queue (`#queue-items` stays a `<tbody>`, because `renderQueueItems()` at `move-manager.js:843` appends `<tr>`s with seven `<td>`s) reflowed into stacked rows by CSS scoped to `.handheld-main`
  - `#validate-btn` and `#execute-moves-btn` in the fixed action bar
- **Rationale**: no change to move logic. `>>DONE<<` handling (`move-manager.js:307`, `:722`) and `#scanner-status` come along unchanged. `waits.scan_on_move_page` keys on `#barcode-input`, `#scanner-status` and `#queue-count`, so it works on the handheld page as-is.
- **Alternatives**: restyle the desktop `move/_scan_move.html` macro with CSS. Rejected (plan.md, Complexity Tracking).
- **Note**: `>>DONE<<` does not execute anything. It finalizes the half-entered move and enables Validate (`move-manager.js:722-770`). Execute stays a tap on the action bar, as on desktop.

### D6. Reusing the shorten controller and handler

- **Decision**:
  - `handheld/shorten.html` carries the IDs that `InventoryShortenManager` binds (`inventory-shorten.js:25-64`, plus `#shorten-form`), in a compact layout:
    - `#source-ja-id` in the header
    - current length and `#new-length` first
    - the confirm checkbox and `#execute-shortening-btn` in the action bar
    - notes, summary and history below
  - The POST body of `inventory_shorten` (`app/main/routes.py:1045-1119`) is extracted into `handle_shorten_post(form_data, return_endpoint)`. The desktop calls it with `'main.inventory_shorten'`, and `/h/shorten` POST with `'handheld.shorten'`. The form keeps `method="POST"` with no `action`, so it posts to its own page.
- **Rationale**: the desktop form posts to itself and every branch redirects to `main.inventory_shorten`. Without the extraction, the handheld would land on the desktop page after a shorten. With it, validation, audit logging and `_execute_shortening_operation` stay one copy (constitution VI).
- **Alternatives**: a hidden `return_to=handheld` field on the desktop route. It works, but it adds a branch to five redirects. The extraction is the same size and reads more plainly.

### D7. Reusing the receive handler

- **Decision**:
  - Extract `_receive_purchase_from_form(service, purchase_id, form)` from `purchase_receive` (`app/product/routes.py:1106-1118`). It maps the form fields onto `service.receive_purchase(...)`, including `counted == 'on'`, and both routes call it.
  - The handheld form posts the same fields the desktop form posts when nothing is amended: `description` = product description, `unit_price` and `notes` = stored values, `received_date` blank, plus the visible `quantity` and `counted`. The service sees the same call an unamended desktop receive makes (SC-005).
  - Success redirects to `handheld.product` with the same `Received.` flash. A `ValidationError` re-renders `handheld/receive.html`.
  - Extract `_receive_choice(scan)` from `purchase_receive_choice` (`:2266-2296`: `find_mcmaster_receivable`, then the vendor-scoped product fallback) for `/h/receive/choose`.
- **Rationale**: the desktop redirects to the desktop product page and re-renders the desktop template on refusal. The handheld needs its own landing, with no new rules.
- **Already received**: the handheld receive screen says so and offers no Receive button. A repeat receive is a service no-op anyway, so this is presentation only.

### D8. Reusing the product Stock card and label modal

- **Decision**:
  - Move `detail.html` lines 355–498 (the Stock card) verbatim into `product/_stock_card.html`, and lines 592–633 (the label modal) into `product/_label_modal.html`. `detail.html` includes them at the same positions. `{% include %}` shares the context, so `product`, `received_total` and the `relative_age` filter keep working.
  - The handheld product screen includes both. `received_total` comes from a new `_received_total(purchases)` helper that `product_detail` also uses.
  - `product-stock.js` reloads the page after every PATCH (`product-stock.js:151`), so the handheld re-renders from the server exactly as the desktop does.
- **FR-016**: the modal measured 538 px. The two `.form-text` help lines get `d-none d-sm-block`, which hides them below 576 px and leaves them visible at desktop widths, so the desktop look is unchanged. The e2e test measures that `#product-label-print-confirm` is in the viewport at 360×512.
- **Desktop identity check**: render `/products/<id>` before and after the extraction and diff the HTML with whitespace normalized (quickstart §3). The existing product e2e tests and screenshots must also pass unchanged.
- **Compaction**: the Stock card's own header and helper text are hidden only under `.handheld-main`, so the −/+, Set, counting and Low/Out/Clear controls sit as high as possible. US2 acceptance 1 requires name, location and the quantity controls above the fold, and that is the measured gate. Low/Out/Clear above the fold is the aim, measured in e2e but not a gate.

### D9. Attachments and photos

- **Item photos**: `PhotoManager.init('#photo-manager-container', {itemId, readOnly: false})` (`photo-manager.js:43`) mounts on any page as-is. `edit.html:735` already does exactly this. Its file input has no `capture` attribute, so Android offers its chooser, as decided.
- **Product attachments**: the handheld product screen renders the markup `product-attachments.js` binds:
  - `#attachments-card[data-product-id]`
  - `#attachment-alerts`
  - `#product-attachment-input` and `#upload-product-attachment-btn`
  - `.attachment-select` and the selection toolbar

  It renders no per-tile `.delete-attachment-btn`. On the desktop that button deletes **without any confirmation** (`product-attachments.js:96-112`), and FR-017 requires a confirmation. On the handheld, deletion is select, then Delete Selected, which confirms (`:178`). Each tile is a full-width label around its checkbox (FR-008).

### D10. In-page confirmation (FR-026)

- **Decision**: `main.js` defines a default `window.confirmAction = (message) => Promise.resolve(window.confirm(message))`. `handheld.js` replaces it with a Bootstrap-modal confirm that resolves true or false. Three call sites change from `confirm(...)` to `await window.confirmAction(...)`:
  - `move-manager.js:1125`, in `executeMoves`, which is already async
  - `photo-manager.js:640` and `:657`, which are already async
  - `product-attachments.js:178`, whose click handler becomes async
- **Rationale**: these are the only browser dialogs in the controllers the handheld reuses. A grep of `alert(`, `confirm(` and `prompt(` over `app/static/js` finds none in `inventory-shorten.js`, `product-stock.js`, `label-printing-modal.js` or `product-label-modal.js`. `photo-manager.js:23` alerts only when `WorkshopInventory.utils.showToast` is missing, and `main.js` provides it. On desktop, `window.confirm` is still called synchronously from the same handler, so desktop behavior and the dialog-accepting desktop e2e tests are unchanged.
- **Alternatives**: copy the controllers, which duplicates logic, or replace desktop confirms everywhere, which violates FR-025.

### D11. Soft keyboard (FR-029) and focus (FR-002)

- **Decision**: `handheld.js` does all of it.
  - Every handheld scan entry is rendered with `inputmode="none"` and `autocomplete="off"`, and is focused on `DOMContentLoaded` with `{preventScroll: true}`.
  - **Keyboard button** (`[data-keyboard-for="<input id>"]`):
    1. Set `inputmode="text"`, then `blur()` and `focus()` so Chrome raises the IME.
    2. On the Move screen, also check `#manual-entry-mode` and dispatch `change`. Otherwise `move-manager.js:319` auto-processes the field 100 ms after each typed character and would submit a half-typed code.
    3. On the next Enter keydown in that input (listened for without `preventDefault`, so the controller's own handler still runs), restore `inputmode="none"`, uncheck manual-entry mode, and blur and refocus so the keyboard drops.
  - **Refocus after actions**:
    - on `hidden.bs.modal`, which covers the label modals and the in-page confirm
    - after a `click` whose target is not a form field (`input`, `select`, `textarea`, `label`), on a microtask, so tapping +, Execute or Print returns focus to the scan entry
    - pages that reload after an action (product stock, attachments, form POSTs) get focus from the load handler
- **Rationale**: research.md records that tapping the header Scan box raises the keyboard (observed 2026-10-25), and that scan-capture's no-Enter fallback cannot fire on Android (`scan-capture.js:144`, key `"Unidentified"`). The Enter suffix is therefore required and is documented in FR-028. `scan-capture.js` is reused unchanged apart from the flag. That keeps the Ctrl-key to GS/RS/EOT reconstruction for DigiKey labels (`scan-capture.js:36`), and its Enter path already falls back to `input.value` when no keydown characters were buffered (`:115-121`), which is the Android IME path.
- **Unverified on the device, and a gate before release**:
  1. That DataWedge keystrokes reach an `inputmode="none"` field in Chrome. If they do not, the fallback is DataWedge's own "DataWedge keyboard" option (research.md, "How scanning reaches the web page") with `inputmode` left default.
  2. That a DigiKey 2D label still works on Android. If DataWedge sends the control characters as Ctrl key events while the printable characters arrive through the IME, `scan-capture.js` buffers only the control characters. Its `input.value` fallback is then skipped because the buffer is not empty, and the scan is lost. This is unchanged desktop code and the same risk exists for the header box today. It is listed for the device check, not fixed speculatively.

### D12. Primary-action reachability (FR-007) and overflow (FR-006)

- **Decision**:
  - The scan entry sits in a `position: sticky; top: 0` header.
  - Each screen's primary action sits in a `position: fixed; bottom: 0` action bar:
    - Move: Validate and Execute
    - Shorten: Confirm and Execute
    - Receive: Receive
    - Order: Receive Selected
    - Item: Label, Photos, Shorten, Move
    - Product: Label, Attach, Move, Order
  - On the product screen, Set is inside the Stock card, which is the first block under the header, so it is above the fold at load.
  - Long text wraps (`overflow-wrap: anywhere` on the summary and card text under `.handheld-main`).
- **Test helper** (`tests/e2e/handheld.py`):
  - `assert_handheld_layout(page, scan_selector, primary_selector)` runs `expect(locator).to_be_visible()` and then `expect(locator).to_be_in_viewport()` for both. That polls, following CLAUDE.md.
  - It then scrolls to the bottom with `page.mouse.wheel` (or `evaluate('window.scrollTo(0, document.body.scrollHeight)')`) and asserts `to_be_in_viewport()` again.
  - Finally it evaluates `scrollWidth - clientWidth <= 1`, after the content region has been established with `expect()`.

### D13. Orders on the handheld (FR-023, FR-023a, FR-023b)

- **Order list**: group `service.find_outstanding_purchases()` (`app/catalog_service.py:4284`) by `(vendor, supplier_order_reference)`, skipping purchases with no order reference. They have no order screen and are reachable from their product's screen instead. The service's order is kept: oldest order first. See data-model.md.
- **Order screen**:
  - `service.find_order_lines_for(vendor, order)` (`:4456`), shown as cards. Each outstanding line is a full-width `<label>` wrapping a `name="purchase_id"` checkbox. Received lines show their received date and have no checkbox (FR-023).
  - `highlight` marks matching cards (`vendor_item_id`) but selects nothing (FR-022).
  - The POST goes to `/h/orders/<vendor>/<order>/receive`, which calls `service.receive_order_lines(...)` through the existing `_flash_bulk_receipt` (`app/product/routes.py:1907`) and redirects back to the handheld order screen.
- **Product screen**: list the product's outstanding purchases, from `get_purchase_history` filtered on `is_outstanding`. Each gets a Receive link to `/h/receive/<id>`, which satisfies US6 scenario 5. Each distinct order gets an Order link (FR-023b). Several orders appear as several buttons, which is the choice FR-023b asks for.
- **One handheld order URL for every vendor**: `/h/orders/<vendor>/<order>`. The DigiKey-specific desktop address (`_order_url`) exists only for history compatibility, which does not apply to new URLs.

### D14. Survey seeding file

The throwaway survey test named in the planning brief (`…/scratchpad/handheld-screens/test_zz_handheld_survey.py.txt`) was **not present** when this plan was written. The e2e seeding is therefore planned from existing helpers:
- `live_server.add_test_data` for items
- `add_test_products` and `add_product_attachments` (`tests/e2e/test_server.py:193`, `:217`)
- `CatalogService(live_server.storage).record_purchase(...)`, as in `tests/e2e/test_outstanding_products.py:36`
- the McMaster and DigiKey receive seeding in `test_mcmaster_receive.py` and `test_digikey_receive.py`

FR-006's "data lengths the survey seeded" becomes an explicit long-data fixture: a 255-character description, a long location and sub-location, a long vendor name, and order numbers of realistic length.
