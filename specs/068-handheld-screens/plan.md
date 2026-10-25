# Implementation Plan: Handheld Screens

**Branch**: `speckit/068-handheld-screens` | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/068-handheld-screens/spec.md`

## Summary

Add a small `handheld` blueprint at `/h/` with nine server-rendered screens for a 360×512 touch
viewport: landing, item, product, shorten, move, receive, receive-choice, order list and order.
Each screen is a new template over operations the application already performs.

- **Same JSON APIs and JS controllers.** `scan-capture.js`, `move-manager.js` with its two
  subclasses, `inventory-shorten.js`, `photo-manager.js`, `product-stock.js`,
  `product-attachments.js`, `label-printing-modal.js` and `product-label-modal.js` are mounted
  on new markup that carries the element IDs each controller binds.
- **Same scan rule.** `POST /api/scan` resolves exactly as it does today. A `handheld: true`
  flag in the request changes only which URL is returned for `item`, `product` and `receive`.
- **Same receive and shorten handlers.** The two form POSTs are factored into helpers so the
  handheld routes call the same code. Only the redirect target differs.
- **Desktop changes.** All of them render identical HTML or behave identically:
  - three empty-by-default blocks in `base.html`
  - the Stock card and product label modal extracted into partials
  - an overridable confirm hook in three controllers, defaulting to `window.confirm`
  - the product label modal's help text hidden below 576 px (FR-016)

## Technical Context

**Language/Version**: Python 3.13. Vanilla JS in `app/static/js/`.

**Primary Dependencies**: Flask 3.1, Jinja2 and Bootstrap 5.3.2 from the CDN, as today. No new
dependencies.

**Storage**: MariaDB, unchanged. No schema change, no migration, no new table. One read-only
grouping over `find_outstanding_purchases()` for the order list (data-model.md).

**Testing**: `nox -s tests` for unit tests (routes, scan flag) and `nox -s e2e` for Playwright
at a 360×512 touch context with keystroke scans.

**Target Platform**: Zebra TC52, Android 14, current Chrome, 360×512 CSS px portrait, served
over plain HTTP on the LAN.

**Project Type**: Server-rendered Flask web application.

**Performance Goals**: None beyond today's pages. No measured problem, so nothing to optimize.

**Constraints**:
- No horizontal scroll at 360 px (FR-006).
- The scan entry and the primary action stay in the viewport (FR-007).
- Desktop pages render identically (FR-025).
- No browser dialogs on handheld screens (FR-026).
- Scan entries do not raise the soft keyboard (FR-029).

**Scale/Scope**:
- 1 new blueprint, 9 new templates, 2 extracted partials, 1 new JS file and 1 new CSS file.
- About 10 existing files modified.
- 7 new e2e files, 2 unit test files new or extended, and a user manual section.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Simplicity First | PASS, justified | New screens are new surface. The measurements justify them: research.md "Survey at 360×512" puts every task's controls 2–5 screens down and the scan box behind the toggler. Reworking every desktop page was the rejected alternative (research.md, "Recommendation"). No framework, no SPA, no service worker or PWA, no device detection, no new dependency, no new table. Each screen reuses an existing controller rather than adding a second one. The one new indirection, `window.confirmAction`, has two real implementations: the native confirm on desktop and the in-page confirm on the handheld. |
| II. Layered Architecture | PASS | Handheld routes are thin and call the same `CatalogService` / `InventoryService` methods the desktop routes call. The shared route-level glue (receive form → `receive_purchase`, shorten POST, the receive-choice lookup) is factored into helpers rather than copied. There is no ORM in the routes. The order-list grouping is plain Python over a service result, the same shape as `outstanding_products()` (`app/product/routes.py:1929`). |
| III. Exact Numerics | PASS | Shorten goes through the existing POST handler and `_execute_shortening_operation`. The handheld adds no arithmetic on lengths. |
| IV. Test Discipline | PASS | Every story gets e2e coverage at 360×512 touch (FR-027). Tests wait on state, following CLAUDE.md: `expect(...)`, `to_be_in_viewport()`, URL waits, `waits.scan_on_move_page` reused as-is. Seeding goes through `live_server.add_test_data`, `add_test_products`, `add_product_attachments` and `CatalogService.record_purchase`. No new marker; the tests use `e2e`. Run through nox. |
| V. MariaDB Source of Truth | N/A | No schema change. |
| VI. Item History Invariants | PASS | Handheld Shorten posts the same form fields to the same handler (`handle_shorten_post`, extracted from `inventory_shorten`). Handheld Move posts to the same `/api/inventory/batch-move`. The existing active-status and history e2e tests keep covering those paths, and `test_handheld_shorten.py` adds a check that history is retained. |
| Threat model / CSRF | PASS | CSRF stays on. Handheld pages extend `base.html`, so the `csrf-token` meta tag and `csrf.js` come with them. Form POSTs carry `csrf_token`. No endpoint is newly exempted. |
| Workflow: screenshots | Action | Templates, CSS and JS change, so regenerate screenshots. Commit only those that actually changed (they churn per run; see memory). Desktop screenshots should not change. Any that do is an FR-025 regression to investigate. |

**Spec 001 reversal.** Spec 001 said a separate mobile interface is out of scope. This feature
reverses that for the twelve handheld tasks only, because the measurement in research.md shows
the single responsive interface fails at the real viewport. The decision is the user's
(research.md, "Decisions so far", 2026-10-25). Spec 001's FR-036 and SC-010 still bind the
desktop pages, and `test_touch_readiness.py` stays as it is.

**Post-design re-check**: PASS. The Phase 1 design below adds no violations. See
"Complexity Tracking".

## Project Structure

### Documentation (this feature)

`spec.md`, `research.md` (with the Phase 0 design decisions appended), `plan.md`,
`data-model.md`, `contracts/handheld-routes.md`, `contracts/scan-api.md`,
`contracts/controller-markup.md`, `quickstart.md`, and later `tasks.md`.

### Source Code

**New**
- `app/handheld/__init__.py`: `bp = Blueprint('handheld', __name__, url_prefix='/h')`
- `app/handheld/routes.py`: the routes in `contracts/handheld-routes.md`
- `app/templates/handheld/base.html`: extends `base.html`. It overrides the navbar with a
  compact sticky header (Home, scan entry, keyboard button) and the footer with nothing. It
  provides `screen` and `action_bar` blocks, the action bar being fixed to the bottom, and the
  in-page confirm modal.
- `app/templates/handheld/landing.html`, `item.html`, `product.html`, `shorten.html`,
  `move.html`, `receive.html`, `receive_choose.html`, `orders.html`, `order.html`
- `app/templates/product/_stock_card.html`: the Stock card, moved out of `detail.html`
  verbatim
- `app/templates/product/_label_modal.html`: the product label modal, moved out of
  `detail.html`
- `app/static/js/handheld.js`: scan-entry focus (FR-002), the keyboard button (FR-029) and
  `window.confirmAction` as an in-page modal (FR-026)
- `app/static/css/handheld.css`: all rules scoped under `.handheld-main` or `.handheld-*`
  classes. Covers the header, the fixed action bar, 44 px targets, the move queue reflowed as
  a list, and full-width selection cards.
- `tests/e2e/handheld.py`: the layout assertions (FR-006, FR-007), `scan()` and seeding helpers
- `tests/e2e/test_handheld_landing.py`, `test_handheld_product.py`, `test_handheld_move.py`,
  `test_handheld_item.py`, `test_handheld_shorten.py`, `test_handheld_receive.py`,
  `test_handheld_orders.py`
- `tests/unit/test_handheld_routes.py`

**Modified**
- `app/__init__.py`: register `handheld` bp
- `app/templates/base.html`: wrap the `<nav>` in `{% block navbar %}`, the `<footer>` in
  `{% block footer %}`, and add an empty `{% block styles %}` after `main.css`. Desktop output
  is unchanged.
- `app/templates/product/detail.html`: `{% include %}` the two partials in their current
  positions
- `app/templates/product/_label_modal.html`: the two `.form-text` help lines get
  `d-none d-sm-block` (FR-016). They are visible at ≥576 px as today.
- `app/static/js/scan-capture.js`: `data-scan-capture="handheld"` adds `handheld: true` to the
  `/api/scan` body
- `app/static/js/main.js`: default `window.confirmAction = (m) => Promise.resolve(window.confirm(m))`
- `app/static/js/move-manager.js` (`executeMoves`, line 1125), `photo-manager.js` (lines 640
  and 657), `product-attachments.js` (line 178): `confirm(...)` becomes
  `await window.confirmAction(...)`
- `app/product/routes.py`:
  - `api_scan`: the handheld flag
  - `_receive_url(resolution, handheld=False)`
  - extract `_receive_purchase_from_form()`, `_receive_choice()` and `_received_total()`, used
    by both the desktop and handheld routes
- `app/main/routes.py`: extract the POST body of `inventory_shorten` into
  `handle_shorten_post(form_data, return_endpoint)`
- `tests/unit/test_scan_routes.py`: the handheld flag cases
- `docs/user-manual.md`: a new section, "Using a Handheld Scanner" (FR-028), and a TOC entry

**Structure Decision**: the existing single Flask project. `app/handheld/` is a blueprint
package beside `app/main`, `app/admin` and `app/product`, as the constitution's module
placement allows. A separate blueprint gives every handheld URL its `/h/` prefix in one
place and keeps the desktop route modules unchanged apart from the extracted helpers.

## Phased approach

The phases follow the user stories. P1 comes first, and each phase leaves the app shippable.

**Phase A: foundation (blocks everything).**
- `base.html` blocks, `handheld/base.html`, `handheld.css`, `handheld.js` (focus, keyboard
  button, `confirmAction`), the `main.js` default, the blueprint and its registration.
- The `scan-capture.js` flag and the `api_scan` / `_receive_url` handheld mapping.
- `tests/e2e/handheld.py` with the `handheld_page` fixture (360×512, `has_touch`,
  `is_mobile`) and `assert_handheld_layout()`.

**Phase B, US1 (P1): landing and scan routing.**
- `/h/`, plus minimal item and product screens (summary only). US1 needs both screens to
  exist as scan destinations, and later phases fill in their actions.
- Unit tests for the flag. `test_handheld_landing.py`.

**Phase C, US2 (P1): product.**
- Extract `_stock_card.html` and `_label_modal.html`, with an HTML-identity check
  (quickstart §3).
- `/h/product/<id>` with the Stock card, label modal (FR-016), attachments, Move, and Order
  buttons (FR-023b).
- The confirm hook in `product-attachments.js`.
- `test_handheld_product.py`.

**Phase D, US3 (P1): move.**
- `/h/move?kind=items|products` with handheld markup carrying move-manager's IDs, the queue
  reflowed as a list by CSS, and Validate/Execute in the action bar.
- The confirm hook in `move-manager.js`.
- `test_handheld_move.py`, reusing `waits.scan_on_move_page`.

**Phase E, US4 (P2): item.**
- Summary, the item label modal (`showLabelPrintingModal`), `PhotoManager.init` on
  `#photo-manager-container`, and the not-found and inactive states.
- The confirm hook in `photo-manager.js`.
- `test_handheld_item.py`.

**Phase F, US5 (P2): shorten.**
- Extract `handle_shorten_post`. Add `/h/shorten`, GET and POST, with the IDs that
  `inventory-shorten.js` binds.
- `test_handheld_shorten.py`.

**Phase G, US6 (P2): receive.**
- Extract `_receive_purchase_from_form` and `_receive_choice`. Add `/h/receive/<id>` (GET and
  POST) and `/h/receive/choose`.
- `test_handheld_receive.py`.

**Phase H, US7 (P3): orders.**
- `/h/orders`, `/h/orders/<vendor>/<order>` and its `/receive` POST.
- `test_handheld_orders.py`.

**Phase I: docs and finish.**
- The user manual section (FR-028), "Using a Handheld Scanner", under "Across both halves" in
  the TOC. It covers:
  - DataWedge Profile0 (or a profile bound to `com.android.chrome`): Keystroke output →
    Basic data formatting → **Send ENTER key**. This is required because Chrome's IME
    keystrokes defeat the no-Enter fallback.
  - Symbologies: Code128 (JA ID, product and location labels) and DataMatrix and QR
    (distributor labels).
  - "Send Control Characters as Events" for DigiKey GS/RS. Record whatever the device check
    (quickstart §5.7) shows.
  - Bookmarking `http://<host>:5000/h/` and setting it as Chrome's home page.
  - What each handheld screen does, the keyboard button, and that anything else opens the
    desktop page.
- Screenshots.
- The full `nox -s tests` and `nox -s e2e`, run detached.
- The on-device checklist (quickstart §5).

## Complexity Tracking

No constitution violations. Two design costs are recorded so a reviewer can weigh them.

| Cost | Why needed | Simpler alternative rejected because |
|---|---|---|
| `handheld/move.html` and `handheld/shorten.html` repeat the element IDs that `move-manager.js` and `inventory-shorten.js` bind (contracts/controller-markup.md). | The desktop markup puts warnings above the input, the queue in a 7-column table and the commit buttons in the last card. FR-007 and FR-019 need a different order. | Restyling the desktop macro with handheld CSS (flex `order`, `position: fixed` on buttons inside a `display:none` section) is fragile and couples the two layouts. Changing the macro risks FR-025. The repeated IDs are pinned by the handheld e2e tests, which fail if a controller starts binding an ID the handheld markup lacks. |
| `window.confirmAction` indirection in three shared controllers. | FR-026 forbids browser dialogs on the handheld. The controllers that confirm are the ones FR-024 says to reuse. | Leaving `confirm()` breaks FR-026 and risks the keystroke stall noted in research.md. Copying the controllers duplicates business flow. Replacing the desktop confirm with the in-page one changes desktop behavior (FR-025). |
