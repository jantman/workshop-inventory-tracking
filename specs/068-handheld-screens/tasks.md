# Tasks: Handheld Screens

**Input**: Design documents from `specs/068-handheld-screens/`

**Prerequisites**: plan.md, spec.md, research.md (Phase 0 design decisions D1–D14), data-model.md,
contracts/ (`handheld-routes.md`, `scan-api.md`, `controller-markup.md`), quickstart.md

**Tests**: Required. The constitution requires behavior changes to land with tests, and FR-027
requires e2e coverage per story at a 360×512 touch viewport.

**Organization**: by user story, in priority order, so each phase leaves the app shippable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (disjoint files, no dependency on an incomplete task)
- **[Story]**: the user story the task serves (US1–US7)

## Rules every task follows

- **Commands.** Run everything through nox with venv binaries by path:
  `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` for unit tests.
  Never run `pytest` directly.
- **E2E runs.** Run e2e detached: `nohup ... venv/bin/nox -s e2e -- <files> > "$SCRATCH/<name>.log" 2>&1 &`,
  then poll the log tail. `$SCRATCH` is the session scratchpad. A single handheld file takes
  minutes. The full suite takes about 17 minutes warm and outlasts the 10-minute Bash cap.
- **E2E waiting** (repo `CLAUDE.md`, "Writing e2e tests"):
  - No `wait_for_timeout`, `time.sleep` or `wait_for_load_state("networkidle")`.
  - Wait with `expect(...)`, including `to_be_in_viewport()` and `to_have_url(...)`.
  - Establish a JS-rendered region with `expect()` before any `count()`, `text_content()`,
    `is_visible()`, `get_attribute()` or `is_checked()`.
  - For a click that fires a `fetch`, wait for what the response changes on the page.
  - Seed with `live_server.add_test_data`, `add_test_products`, `add_product_attachments` or
    `CatalogService(live_server.storage).record_purchase(...)`. Drive a form only when the
    form is under test.
  - Shared waits go in `tests/e2e/waits.py`, handheld helpers in `tests/e2e/handheld.py`, and
    assertions in the test.
- **Every handheld e2e test**:
  - uses the `handheld_page` fixture (360×512, `has_touch=True`, `is_mobile=True`)
  - delivers scans as `page.keyboard.type(code)` then `page.keyboard.press("Enter")`, with
    nothing tapped first
  - calls `assert_handheld_layout(page, scan_selector, primary_selector)` (FR-006, FR-007)
  - asserts `inputmode="none"` on the scan entry (FR-029)
  - checks results through the desktop pages or APIs (SC-005)
- **Desktop identity (FR-025).** A task marked **(desktop)** edits a file that desktop pages
  use. It must leave desktop HTML and behavior identical. The existing desktop unit and e2e
  tests must pass **unedited**.
- **Spelling.** `catalog`, never `catalogue`.
- **Lint.** Lint fails on `main` as a baseline, so check only files you touched.

---

## Phase 1: Setup

**Purpose**: capture the desktop baseline before any desktop template changes.

- [X] T001 Capture the desktop-identity baseline per quickstart.md §3. Seed a dev database with
  at least one item, one product (with a purchase, an attachment and a location) and one
  outstanding purchase. Run the dev server on :5000. curl `/`, `/inventory`,
  `/inventory/move`, `/inventory/shorten`, `/products`, `/products/<id>`, `/products/move` and
  `/inventory/edit/<JA>` with the CSRF token and `content=` attributes stripped and whitespace
  squeezed. Save into `$SCRATCH/identity-before/`. Keep the seeded database for T020 and T066.
  Writes no repo files.
  - *Done via the e2e `live_server` (allowed by the implement brief) instead of a dev server:
    a throwaway capture test, kept with its output in the session scratchpad `068-baseline/`
    (`identity-before/`). It also normalizes timestamps, the random WIT code and the footer
    version, and adds `/purchases/<id>/receive` and `/products/outstanding`.*

---

## Phase 2: Foundational (blocks every story)

**Purpose**: the handheld shell, the shared JS and CSS, the blueprint and the e2e helpers.

- [X] T002 **(desktop)** In `app/templates/base.html`, wrap the `<nav>` in
  `{% block navbar %}…{% endblock %}`, wrap the `<footer>` in `{% block footer %}…{% endblock %}`,
  and add an empty `{% block styles %}{% endblock %}` right after the `main.css` link (D3).
  Default block contents must render byte-identical markup.
- [X] T003 [P] **(desktop)** In `app/static/js/main.js`, define the default
  `window.confirmAction = (message) => Promise.resolve(window.confirm(message))` (D10).
  Nothing calls it yet.
- [X] T004 [P] Create `app/static/css/handheld.css`, with every rule scoped under
  `.handheld-main` or a `.handheld-*` class (D3, D12):
  - a sticky compact header (`position: sticky; top: 0`)
  - a fixed bottom action bar, with matching bottom padding on `.handheld-main`
  - 44 px minimum tap targets (FR-008)
  - `overflow-wrap: anywhere` on summary and card text (FR-006)
  - full-width selection-card styles, used by later stories for attachments and order lines
- [X] T005 [P] Create `app/static/js/handheld.js` (D10, D11, controller-markup.md
  "`handheld.js`"):
  - **Focus.** Focus `[data-handheld-scan]` on `DOMContentLoaded` with
    `{preventScroll: true}` (FR-002). Refocus it on `hidden.bs.modal`, and after a `click`
    whose target is not an `input`, `select`, `textarea` or `label`, on a microtask.
  - **Keyboard button** `[data-keyboard-for="<id>"]` (FR-029):
    1. Set `inputmode="text"`, then blur and refocus so the keyboard rises.
    2. If `#manual-entry-mode` exists, check it and dispatch `change`.
    3. On the next Enter keydown in that input (no `preventDefault`), restore
       `inputmode="none"`, uncheck manual-entry mode, and blur and refocus.
  - **Confirm.** Override `window.confirmAction` with a Bootstrap-modal confirm on
    `#handheld-confirm-modal`, `#handheld-confirm-message`, `#handheld-confirm-ok` and
    `#handheld-confirm-cancel`. It returns a Promise of a boolean (FR-026).
- [X] T006 Create `app/templates/handheld/base.html`, extending `base.html` (D3, D4):
  - **Overrides.** `navbar` becomes a header with a Home link to `/h/` (FR-005), a
    `{% block scan_entry %}` and a keyboard button. `footer` is empty. `styles` loads
    `handheld.css`. `main_container_class` is `handheld-main container-fluid px-2`.
  - **Default scan entry**: `<input id="handheld-scan-input" data-scan-capture="handheld"
    data-handheld-scan inputmode="none" autocomplete="off">` with
    `data-keyboard-for="handheld-scan-input"`.
  - **Blocks**: `screen`, and `action_bar` rendered in the fixed bar.
  - **Confirm modal**: `#handheld-confirm-modal` and its children.
  - **Script**: loads `handheld.js` after the base scripts.

  Depends on T002, T004 and T005.
- [X] T007 Create the blueprint. `app/handheld/__init__.py` defines
  `bp = Blueprint('handheld', __name__, url_prefix='/h')` and imports `routes`.
  `app/handheld/routes.py` starts empty apart from imports. Register the blueprint in
  `app/__init__.py` beside `main`, `admin` and `product` (D1). Author Jason Antman, 2026.
- [X] T008 [P] **(desktop)** In `app/static/js/scan-capture.js` `resolve()`, add
  `handheld: true` to the `/api/scan` body only when
  `this.input.dataset.scanCapture === 'handheld'` (scan-api.md "Client"). The body for the bare
  desktop attribute stays `{"scan": …}`.
- [X] T009 [P] Add the `handheld_page` fixture to `tests/e2e/conftest.py`. It opens a
  `browser.new_context(viewport={'width': 360, 'height': 512}, has_touch=True, is_mobile=True)`
  page, following `tests/e2e/test_touch_readiness.py:24`, and closes the context on teardown.
- [X] T010 [P] Create `tests/e2e/handheld.py` (D12, D14):
  - `scan(page, code)`: types the code and presses Enter
  - `assert_handheld_layout(page, scan_selector, primary_selector)`:
    1. `expect(...).to_be_visible()` and `to_be_in_viewport()` for both selectors
    2. scroll to the bottom with `evaluate('window.scrollTo(0, document.body.scrollHeight)')`
       and assert both are still `to_be_in_viewport()`
    3. evaluate `document.documentElement.scrollWidth - clientWidth <= 1`
  - `assert_scan_entry_no_keyboard(page, selector)`: `expect(...).to_have_attribute('inputmode', 'none')`
  - long-data seed builders: a 255-character description, a long location and sub-location,
    a long vendor name and realistic order numbers. FR-006 is tested against these.

**Checkpoint**: `/h/` has no routes yet. Desktop pages unchanged. `nox -s tests` passes.

---

## Phase 3: User Story 1 – Scan anything from the landing page (P1) 🎯 MVP

**Goal**: `/h/` takes a scan with no tap. JA IDs open `/h/item/…`, products open
`/h/product/…`, and create or search outcomes open the desktop page.

**Independent test**: seed an item and a product. At 360×512, type each code and Enter on `/h/`
and land on the right handheld screen.

**Scope note**: until US6 and US7 add their mappings, a receive outcome keeps its desktop URL.
FR-003 permits this fallback. US1 scenario 3 is tested in T049 (US6). Item and product screens
are summary-only here. US4 and US2 fill them in.

### Tests

- [X] T011 [P] [US1] In `tests/unit/test_scan_routes.py`, add handheld-flag cases.
  - With `handheld: true`: `item` returns `/h/item/<JA>` and `product` returns
    `/h/product/<id>`.
  - `create` and `search` return the same URL with and without the flag.
  - A falsy flag gives today's response.
  - Leave existing assertions untouched.
- [X] T012 [P] [US1] Create `tests/unit/test_handheld_routes.py`.
  - `GET /h/` returns 200 with `#handheld-scan-input` carrying `inputmode="none"` and links
    to the four task URLs.
  - `GET /h/item/<JA>` returns 200 with the JA ID.
  - `GET /h/product/<id>` returns 200 with the description. An unknown id returns 404.
  - *Unknown product id: the centralized `ItemNotFoundError` handler answers an HTML
    request with a flash and a 302, as it does for `/products/<id>` (contracts/handheld-routes.md
    "same handling as the desktop routes"). The test asserts equivalence with the desktop
    response rather than a literal 404.*
- [X] T013 [US1] Create `tests/e2e/test_handheld_landing.py`, covering US1 scenarios 1, 2, 4,
  5 and 6 plus FR-029:
  - **Scenario 1.** A JA ID goes to `/h/item/<JA>`.
  - **Scenario 2.** A `WIT…` code and a retail GTIN go to `/h/product/<id>`.
  - **Scenario 4.** An unknown GTIN goes to the desktop create form, and free text goes to
    `/products?q=…`.
  - **Scenario 5.** Layout via `assert_handheld_layout(page, '#handheld-scan-input',
    '<Move items button>')`, plus the four buttons in the viewport.
  - **Scenario 6.** A scan typed on `/h/product/<id>` resolves like one on the landing page.
  - **FR-029.** The keyboard button sets `inputmode` to `text` with the input focused. A
    typed code plus Enter navigates, and the destination's entry is back to `none`.

### Implementation

- [X] T014 [US1] In `app/product/routes.py` `api_scan`, read
  `handheld = bool(data.get('handheld'))`. When it is set, return
  `url_for('handheld.item', ja_id=…)` for `item` and `url_for('handheld.product', product_id=…)`
  for `product` (scan-api.md). Leave `receive`, `create` and `search` URLs unchanged for now.
  Resolution is untouched.
- [X] T015 [US1] Add `handheld.landing` (`/h/`) to `app/handheld/routes.py` and create
  `app/templates/handheld/landing.html`. It has no data. The `screen` block shows four 44 px
  buttons: Move items, Move products, Shorten and Orders, linking to `/h/move?kind=items`,
  `/h/move?kind=products`, `/h/shorten` and `/h/orders` (FR-001, FR-004). Those targets come
  in later phases.
- [X] T016 [US1] Add minimal `handheld.item` (`/h/item/<ja_id>`) and `handheld.product`
  (`/h/product/<int:product_id>`) routes to `app/handheld/routes.py`.
  - item reads `InventoryService.get_canonical_item(ja_id)`; product reads
    `_product_or_404(service, product_id)` (data-model.md).
  - Create `app/templates/handheld/item.html` and `app/templates/handheld/product.html`,
    showing the JA ID or the product description and location only.
  - US4 and US2 complete them.

**Checkpoint**: from `/h/`, scanning reaches item and product screens with zero taps (SC-001).
T011–T013 pass.

---

## Phase 4: User Story 2 – Adjust a product at the shelf (P1)

**Goal**: the product screen shows name, location and stock controls above the fold, plus
label printing and attachments.

**Independent test**: seed a counted product with a location. At 360×512, tap +, set Low, and
see both on `/products/<id>`.

### Desktop refactor (do first, then verify identity)

- [X] T017 [US2] **(desktop)** Move the Stock card (D8; today `detail.html` lines 355–498)
  verbatim into `app/templates/product/_stock_card.html`. Move the product label modal
  (lines 592–633) into `app/templates/product/_label_modal.html`. `{% include %}` both at the
  same positions in `app/templates/product/detail.html`. Line numbers are as of `e5c2bd9`, so
  confirm the boundaries by element (`#stock-card`, `#product-label-modal`).
- [X] T018 [US2] **(desktop)** Extract `_received_total(purchases)` from `product_detail` in
  `app/product/routes.py`. `product_detail` calls it, with the same result.
- [X] T019 [US2] **(desktop)** In `app/templates/product/_label_modal.html`, add
  `d-none d-sm-block` to the two `.form-text` help lines (FR-016). This is the one intended
  desktop markup change.
- [X] T020 [US2] Desktop-identity check after T002, T017 and T019. Re-run T001's curl loop
  into `$SCRATCH/identity-after-us2/` and `diff -r` it against `identity-before/`. The only
  allowed differences are whitespace and the `d-none d-sm-block` classes. Any other
  difference must be fixed before continuing. Run the existing product e2e tests detached,
  unedited, and confirm they pass: `tests/e2e/test_product_*.py` and any test touching
  `#stock-card` or `#product-label-modal`.
  - *Done with the phase-1 capture test (`068-baseline/identity-after-us2/`): the only diff
    is `d-none d-sm-block` on the two help lines. Desktop e2e (`test_product_*`, `test_move_*`,
    `test_bulk_move_handoff`, `test_label_print`, `test_touch_readiness`, `test_typed_quantity`,
    `test_reorder_view`, `test_stock_age`) pass unedited: 249 + 8.*

### Tests

- [X] T021 [P] [US2] In `tests/unit/test_handheld_routes.py`, `GET /h/product/<id>` renders
  `#stock-card[data-product-id]`, `#product-label-modal`, `#attachments-card[data-product-id]`,
  and no `.delete-attachment-btn` (D9).
- [X] T022 [P] [US2] Create `tests/e2e/test_handheld_product.py`, covering US2 scenarios 1–7.
  Seed with `add_test_products` and `add_product_attachments`, including one long-data
  product from `tests/e2e/handheld.py`.
  - **Scenario 1.** Description, location and the −/+ controls are in the viewport.
    `assert_handheld_layout`, with Set as the primary action.
  - **Scenarios 2–3.** Tap −, + and Set; Low, Out and Clear (`waits.wait_for_stock_flag`).
    Verify each on `/products/<id>`.
  - **Scenario 4.** Start and Stop counting.
  - **Scenario 5.** Print label opens `#product-label-modal`
    (`waits.wait_for_modal_shown`), and `#product-label-print-confirm` is `to_be_in_viewport()`.
  - **Scenario 6.** Attach a file through `#product-attachment-input`
    (`set_input_files`), then wait for the new `.attachment-row`.
  - **Scenario 7.** Select a tile, Delete Selected, and accept the in-page
    `#handheld-confirm-modal`. Assert no native dialog fires by registering `page.on('dialog')`
    to fail. The tile count drops.
  - *Scenario 1 asserts Set `to_be_in_viewport()` and clear of the fixed action bar at load,
    then `assert_handheld_layout` with Label (`#print-product-label-btn`, action bar) as the
    primary: the helper re-checks after scrolling to the bottom, which an in-flow Set cannot
    pass by design (D12 puts Set above the fold, not in the bar). Scenarios 1 and 5 run with
    short and long data.*

### Implementation

- [X] T023 [P] [US2] **(desktop)** In `app/static/js/product-attachments.js` (about line 178),
  make the Delete Selected handler `async` and replace `confirm(...)` with
  `await window.confirmAction(...)` (D10). Desktop still gets a native confirm through the
  T003 default.
- [X] T024 [US2] Complete `handheld.product` in `app/handheld/routes.py`:
  - add `purchases` (`get_purchase_history`), `received_total` (`_received_total`) and
    `attachments` (`PhotoService.get_product_attachments(...)` as `.to_dict()`), per
    data-model.md
  - load `product-stock.js`, `product-label-modal.js` and `product-attachments.js` from the
    template
- [X] T025 [US2] Complete `app/templates/handheld/product.html` (FR-014, FR-017, D8, D9,
  controller-markup.md):
  - description, location and sub-location first, then `{% include 'product/_stock_card.html' %}`
  - the label modal include and `#print-product-label-btn`
  - the attachments card with the IDs `product-attachments.js` binds; full-width `<label>`
    tiles around `.attachment-select`; no `.delete-attachment-btn`
  - Label and Attach in `action_bar`
  - *Attach in the action bar is a `<label for="product-attachment-input">`; the file input and
    `#upload-product-attachment-btn` are visually hidden, and a small inline script clicks the
    upload button on `change`, so choosing a file is the upload (one step on the handheld).*
- [X] T026 [P] [US2] In `app/static/css/handheld.css`, under `.handheld-main #stock-card`, hide
  the Stock card's own header and helper text so the controls sit as high as possible (D8).
  Style the attachment tiles as full-width cards.

**Checkpoint**: US2 scenarios 1–7 pass. Scenario 8 (Move) lands with US3.

---

## Phase 5: User Story 3 – Move items and products by scanning (P1)

**Goal**: `/h/move?kind=items|products` runs the desktop move loop. The queue is shown as a
list, and Validate and Execute are always in view.

**Independent test**: seed two items. Scan each with a location, Validate, Execute, and confirm
both locations changed.

### Tests

- [X] T027 [P] [US3] In `tests/unit/test_handheld_routes.py`:
  - `/h/move?kind=items` and `?kind=products` return 200 with `#barcode-input[data-handheld-scan]`,
    `#queue-items` as a `<tbody>`, `#batch-move-form` with `csrf_token`, `#validate-btn` and
    `#execute-moves-btn`
  - a missing or unknown `kind` returns 404
  - `?ja_id=<JA>` renders `#preselected-section` with the hand-off
  - *An unknown `kind` is `abort(404)`, which the app's global 404 handler turns into a flash
    and redirect for page requests; the test asserts the same response as any unknown URL.*
- [X] T028 [P] [US3] Create `tests/e2e/test_handheld_move.py`, covering US3 scenarios 1–5.
  Reuse `waits.scan_on_move_page` and `waits.wait_for_move_executed` unchanged.
  - **Scenarios 1–2.** Two items with a location each. Validate, then Execute through the
    in-page confirm with no native dialog. Locations are verified via `/api/items/<ja>`.
  - **Scenario 3.** `>>DONE<<` finalizes and enables Validate.
  - **Scenario 4.** An unknown ID is rejected, and `#barcode-input` stays in the viewport and
    focused (`to_be_focused`).
  - **Scenario 5.** The products variant.
  - **Long queue.** A 10-move queue with `assert_handheld_layout(page, '#barcode-input',
    '#execute-moves-btn')`, with no horizontal overflow.
  - **Keyboard button.** `#manual-entry-mode` is checked while typing and cleared after
    Enter.
  - *Fixed in `handheld.js`: unchecking `#manual-entry-mode` fires MoveManager's change
    handler, which resets `#scanner-status` to "Ready" mid-move; the badge is restored.*
- [X] T029 [US3] Extend `tests/e2e/test_handheld_product.py` with US2 scenario 8. Move opens
  `/h/move?kind=products&code=<code>` with the product pending in `#pending-moves`.

### Implementation

- [X] T030 [P] [US3] **(desktop)** In `app/static/js/move-manager.js` `executeMoves()` (about
  line 1125), replace `confirm(...)` with `await window.confirmAction(...)` (D10). The existing
  desktop move e2e tests must pass unedited.
- [X] T031 [US3] Add `handheld.move` to `app/handheld/routes.py`:
  - `kind` is `items` or `products`, otherwise `abort(404)`
  - the hand-off uses `resolve_handoff(request.args.get('ja_id'), …)` for items and
    `resolve_product_handoff(request.args.get('code'), …)` for products, as the desktop move
    routes do
  - pass `noun`, `nouns` and `id_label`, the same strings as the desktop wrappers
- [X] T032 [US3] Create `app/templates/handheld/move.html`, carrying every ID in
  controller-markup.md "`MoveManager`", with the handheld placement it describes:
  - `#barcode-input` (`data-handheld-scan`, `inputmode="none"`) and `#scanner-status` in the
    `scan_entry` block, with the keyboard button
  - `#form-alerts` directly below, then `#input-status`, then the queue
  - `#validate-btn` and `#execute-moves-btn` in `action_bar`
  - `#clear-all-btn` and `#manual-entry-mode` visually hidden
  - copy the preselected and rejected sections from `app/templates/move/_scan_move.html`
    (lines 61–127) with the same IDs and `data-` attributes
  - load `move-manager.js` plus `inventory-move.js` or `product-move.js` by `kind`
- [X] T033 [P] [US3] In `app/static/css/handheld.css`:
  - give `.handheld-main #form-alerts` a `max-height` and `overflow-y: auto` (FR-019)
  - under `.handheld-main #move-queue-list`, set `table`, `thead`, `tbody`, `tr` and `td` to
    `display: block` and hide `thead`
  - lay each `tr` out as a card: columns 2–3 as one muted line, the new location emphasized,
    status and remove floated right
- [X] T034 [US3] Add a Move button (`/h/move?kind=products&code=<internal_code>`) to the
  `action_bar` of `app/templates/handheld/product.html` (FR-020).

**Checkpoint**: all P1 stories are done. This is a usable shelf tool: scan, adjust stock, move.

---

## Phase 6: User Story 4 – Item screen (P2)

**Goal**: the JA ID screen shows a summary with Label, Photos, Shorten and Move, and does not
scroll sideways.

**Independent test**: seed an item with one photo. At 360×512 there is no overflow, the label
dialog opens with Print visible, a photo can be added and deleted, and Shorten opens loaded.

### Tests

- [X] T035 [P] [US4] In `tests/unit/test_handheld_routes.py`, `/h/item/<missing>` and
  `/h/item/<inactive>` return 200 with their stated messages and a link to
  `/inventory/edit/<ja>` (handheld-routes.md, "Error behavior"). An active item renders type,
  shape, material, dimensions, length and location.
- [X] T036 [P] [US4] Create `tests/e2e/test_handheld_item.py`, covering US4 scenarios 1–6.
  Seed with `live_server.add_test_data`, including a long-data item.
  - **Scenario 1.** `assert_handheld_layout(page, '#handheld-scan-input', <Label button>)`
    and the summary fields.
  - **Scenario 2.** Label opens the item label modal (`waits.wait_for_modal_shown`), with
    Print in the viewport.
  - **Scenarios 3–4.** Add a photo with `set_input_files`, then wait with
    `expect(cards).to_have_count(n)` (pattern C). Open one full size
    (`waits.wait_for_photo_viewer_open`). Delete it through the in-page confirm with no native
    dialog.
  - **Scenario 5.** Shorten goes to `/h/shorten?ja_id=<ja>`, and Move goes to
    `/h/move?kind=items&ja_id=<ja>` with the item pending.
  - **Scenario 6.** Missing and inactive JA IDs.
  - *Note (implementation):* missing/inactive screens have no action bar, so scenario 6 checks
    the desktop link is in view and there is no sideways scroll instead of `assert_handheld_layout`.

### Implementation

- [X] T037 [P] [US4] **(desktop)** In `app/static/js/photo-manager.js` (about lines 640 and
  657), replace `confirm(...)` with `await window.confirmAction(...)` (D10). The existing
  desktop photo e2e tests must pass unedited.
- [X] T038 [US4] Complete `handheld.item` in `app/handheld/routes.py`. Compute `state`
  (`missing`, `inactive` or `active`) per data-model.md.
- [X] T039 [US4] Complete `app/templates/handheld/item.html` (FR-010–FR-012):
  - **Summary.** JA ID, type, shape, material, the non-empty dimensions, length, location and
    sub-location.
  - **Missing or inactive.** A plain message and an "Open desktop page" link to
    `/inventory/edit/<ja>`.
  - **Photos.** `#photo-manager-container`, initialized with
    `PhotoManager.init('#photo-manager-container', {itemId, readOnly: false})`.
  - **Scripts.** Load `label-printing-modal.js` and `label-count.js`. Label calls
    `showLabelPrintingModal(jaId, false)`.
  - **Action bar.** Label, Photos (scrolls to the container), Shorten
    (`/h/shorten?ja_id=`) and Move (`/h/move?kind=items&ja_id=`).

---

## Phase 7: User Story 5 – Shorten an item at the saw (P2)

**Goal**: `/h/shorten` loads an item, takes the new length, and Execute is always in view.
It uses the same handler as the desktop.

**Independent test**: shorten a 1000 mm item to 600 mm. It reads 600 mm and its history is
retained.

### Desktop refactor

- [X] T040 [US5] **(desktop)** In `app/main/routes.py`, extract the POST body of
  `inventory_shorten` (about lines 1045–1119) into
  `handle_shorten_post(form_data, return_endpoint)`, with the same validation, audit log
  entries, flashes and `_execute_shortening_operation` call. Every redirect goes to
  `return_endpoint`. `inventory_shorten` calls it with `'main.inventory_shorten'`. The existing
  `tests/unit/test_routes.py` and `tests/unit/test_audit_logging.py` shorten cases must pass
  unedited.

### Tests

- [X] T041 [P] [US5] In `tests/unit/test_handheld_routes.py`:
  - `GET /h/shorten?ja_id=<JA>` prefills `#source-ja-id`
  - `POST /h/shorten` with a valid shorter length shortens the item, keeps the inactive
    history row and redirects to `/h/shorten`
  - an invalid or longer length changes nothing
- [X] T042 [P] [US5] Create `tests/e2e/test_handheld_shorten.py`, covering US5 scenarios 1–3.
  - **Scenario 1.** Scan a JA ID into `#source-ja-id`, then wait for `#current-length` to show
    the length. `assert_handheld_layout(page, '#source-ja-id', '#execute-shortening-btn')`.
  - **Scenario 2.** Shorten 1000 mm to 600 mm through `#confirm-operation` and Execute. Verify
    with `/api/items/<ja>`, and verify `/api/items/<ja>/history` shows the inactive row.
  - **Scenario 3.** A longer-than-current length gives the desktop's refusal, and nothing
    changes.

### Implementation

- [X] T043 [US5] Add `handheld.shorten`, GET and POST, to `app/handheld/routes.py`.
  - GET uses `resolve_handoff(...)` for `preselected_ja_id` and `rejected_items`.
  - POST calls `handle_shorten_post(request.form, 'handheld.shorten')`.
- [X] T044 [US5] Create `app/templates/handheld/shorten.html`, carrying every ID in
  controller-markup.md "`InventoryShortenManager`":
  - `#shorten-form` with `method="POST"`, no `action`, and `csrf_token`
  - `#source-ja-id` (`data-handheld-scan`, `inputmode="none"`) in `scan_entry`
  - compact `#item-details`, then `#new-length`
  - `#confirm-operation` and `#execute-shortening-btn` in `action_bar`
  - notes, summary and history below
  - load `inventory-shorten.js`
  - *Note (implementation):* the action bar sits outside `#shorten-form`, so `#source-ja-id`,
    `#confirm-operation` and `#execute-shortening-btn` carry `form="shorten-form"`. `#clear-form-btn`
    is also in the action bar (Clear, Confirm, Execute), so a second item can be scanned after one
    is loaded: the controller moves focus to `#new-length` on load.

---

## Phase 8: User Story 6 – Receive a purchase, one bag at a time (P2)

**Goal**: a distributor-label scan opens a one-line handheld receive screen, or a choice list,
with the same effects as the desktop.

**Independent test**: seed an outstanding purchase whose label matches one line. Scan it on
`/h/` and receive it. The purchase reads received with the entered quantity.

### Desktop refactor

- [ ] T045 [US6] **(desktop)** In `app/product/routes.py`:
  - extract `_receive_purchase_from_form(service, purchase_id, form)` from `purchase_receive`
    (about lines 1106–1118), with the same field mapping including `counted == 'on'`
  - extract `_receive_choice(scan)` from `purchase_receive_choice` (about lines 2266–2296)
  - both desktop routes call the helpers
  - the existing `tests/unit/test_product_routes.py`, `tests/unit/test_mcmaster_routes.py`,
    `tests/unit/test_mcmaster_receive.py` and `tests/unit/test_order_receive.py` pass unedited
- [ ] T046 [US6] In `app/product/routes.py`, give `_receive_url` a `handheld: bool = False`
  parameter and pass the flag from `api_scan`. With the flag, the one-outstanding-line target
  becomes `handheld.receive` (keeping `quantity`) and the `LANDING_CHOICE_PAGE` target becomes
  `handheld.receive_choose`. The branching is unchanged. The order-screen branch stays on
  desktop until T055.

### Tests

- [ ] T047 [P] [US6] In `tests/unit/test_scan_routes.py`, add receive cases.
  - One outstanding line with the flag returns `/h/receive/<pid>?quantity=Q`.
  - A McMaster or Amazon multi-candidate scan with the flag returns
    `/h/receive/choose?scan=…`.
  - Without the flag, both return today's URLs.
- [ ] T048 [P] [US6] In `tests/unit/test_handheld_routes.py`:
  - `GET /h/receive/<id>?quantity=3` prefills 3, and an unknown id returns 404
  - `POST /h/receive/<id>` receives the purchase and redirects to `/h/product/<pid>` with
    `Received.`
  - a `ValidationError` re-renders the handheld template
  - an already-received purchase shows no Receive button
  - `GET /h/receive/choose?scan=…` lists the candidates
- [ ] T049 [P] [US6] Create `tests/e2e/test_handheld_receive.py`, covering US6 scenarios 1–5
  and US1 scenario 3. Seed as `tests/e2e/test_mcmaster_receive.py` and
  `tests/e2e/test_digikey_receive.py` do, and with `record_purchase`.
  - **Scenario 1 (and US1 scenario 3).** A single-line label scanned on `/h/` goes to
    `/h/receive/<pid>` with the label's Q prefilled.
    `assert_handheld_layout(page, '#handheld-scan-input', <Receive button>)`.
  - **Scenario 2.** Receive with "counted" updates the count as on desktop. Verify on
    `/products/<id>`.
  - **Scenario 3.** Multiple candidates go to `/h/receive/choose` and nothing is received.
  - **Scenario 4.** Nothing outstanding shows the message, and nothing is received twice.
  - **Scenario 5.** Receive from the product screen's outstanding list.

### Implementation

- [ ] T050 [US6] Add `handheld.receive` (GET and POST) and `handheld.receive_choose` to
  `app/handheld/routes.py`, per handheld-routes.md and data-model.md.
  - POST calls `_receive_purchase_from_form`. Success redirects to `handheld.product` with the
    same flash. A `ValidationError` re-renders.
  - `receive_choose` calls `_receive_choice(scan)`.
- [ ] T051 [US6] Create `app/templates/handheld/receive.html` (D7):
  - **Visible.** Product description, ordered quantity, pack note, `quantity`, and `counted`
    only when `product.quantity is not None`.
  - **Hidden.** `description`, `unit_price`, `notes`, a blank `received_date`, and
    `csrf_token`.
  - **Action bar.** Receive.
  - **Already received.** The message and no Receive button.
- [ ] T052 [P] [US6] Create `app/templates/handheld/receive_choose.html`. Candidates are
  full-width links to `/h/receive/<id>`, and nothing is preselected (FR-022).
- [ ] T053 [US6] In `handheld.product` (`app/handheld/routes.py`) and
  `app/templates/handheld/product.html`, add `outstanding` (data-model.md) and a Receive link
  for each outstanding purchase, to `/h/receive/<id>` (US6 scenario 5).

---

## Phase 9: User Story 7 – Receive several lines of a captured order (P3)

**Goal**: the order list and order screens show lines as full-width selectable cards, with
Receive Selected in view.

**Independent test**: seed a captured order with three outstanding lines. Select two and
receive them. Exactly those two are received.

### Tests

- [ ] T054 [P] [US7] In `tests/unit/test_handheld_routes.py`:
  - `group_outstanding_orders(...)` groups by `(vendor, reference)`, skips blank references,
    counts correctly and keeps oldest-first order
  - `/h/orders` lists only orders with outstanding lines
  - `/h/orders/<v>/<o>` renders checkboxes only for outstanding lines; an unknown order
    returns 200 with "not captured"
  - `POST …/receive` receives exactly the posted `purchase_id`s and redirects back
  - `/h/product/<id>` shows one Order link per distinct outstanding order
- [ ] T055 [P] [US7] In `tests/unit/test_scan_routes.py`, add the non-choice-vendor (DigiKey)
  multi- or zero-outstanding case. With the flag it returns
  `/h/orders/<vendor>/<order>?highlight=<P>`, and the "already received" flash is unchanged.
  Without the flag it returns today's URL.
- [ ] T056 [P] [US7] Create `tests/e2e/test_handheld_orders.py`, covering US7 scenarios 1–5.
  - **Scenarios 1–2.** An order with 3 outstanding lines, using a long vendor name.
    `assert_handheld_layout(page, '#handheld-scan-input', <Receive Selected>)`. Tap 2 cards
    (anywhere on the card, FR-008) and Receive Selected. Exactly those 2 are received,
    verified on the desktop order page.
  - **Scenario 3.** Received lines have no checkbox.
  - **Scenario 4.** `/h/orders` lists only orders with outstanding lines, with counts, and
    tapping one opens it.
  - **Scenario 5.** The product screen's Order button, and two buttons when there are two
    orders.
  - **Scan entry.** A DigiKey multi-line scan on `/h/` lands on the handheld order screen
    with the line highlighted and nothing selected.

### Implementation

- [ ] T057 [US7] In `app/product/routes.py` `_receive_url`, switch the `_order_url(...)` target
  to `url_for('handheld.order', vendor=…, order_number=…, highlight=…)` when `handheld` is set
  (scan-api.md).
- [ ] T058 [US7] In `app/handheld/routes.py`, add:
  - the `OrderSummary` dataclass and `group_outstanding_orders(purchases)` (data-model.md)
  - `handheld.orders`
  - `handheld.order`, reading `find_order_lines_for` and `highlight`
  - `handheld.order_receive` (POST), which calls `_flash_bulk_receipt(lambda:
    service.receive_order_lines(vendor, order_number, form.getlist('purchase_id'),
    received_date=form.get('received_date')))` and redirects to `handheld.order`
- [ ] T059 [P] [US7] Create `app/templates/handheld/orders.html`, with one full-width link
  card per order showing vendor, order number and outstanding count. An empty list says so.
- [ ] T060 [P] [US7] Create `app/templates/handheld/order.html` (D13):
  - each outstanding line is a full-width `<label>` card wrapping a
    `name="purchase_id"` checkbox
  - received lines show their received date and have no checkbox
  - `highlight` marks cards but selects none
  - an empty `lines` list gives "No order <n> from <vendor> was captured" and a Home link
  - Receive Selected in `action_bar`, with `csrf_token`
- [ ] T061 [US7] In `handheld.product` and `app/templates/handheld/product.html`, add
  `outstanding_orders` (data-model.md) and one Order button per distinct order, linking to
  `/h/orders/<vendor>/<order>` (FR-023b).

---

## Phase 10: Polish & cross-cutting

- [ ] T062 [P] Write the "Using a Handheld Scanner" section in `docs/user-manual.md`, with a
  TOC entry under **Across both halves** (FR-028, plan Phase I). Describe the current state
  only, no history. Cover:
  - DataWedge Profile0 (or a profile bound to `com.android.chrome`): Keystroke output →
    Basic data formatting → **Send ENTER key**
  - symbologies: Code128, DataMatrix and QR
  - "Send Control Characters as Events" for DigiKey labels; leave a placeholder for T069's
    finding
  - bookmarking `http://<host>:5000/h/` and setting it as Chrome's home page
  - what each screen does, the keyboard button, and that anything else opens the desktop page
- [ ] T063 [P] Check FR-026. Grep `app/templates/handheld/` and `app/static/js/handheld.js` for
  `alert(`, `confirm(` and `prompt(`; only the `window.confirmAction` override may match.
  Re-grep `app/static/js` to confirm the three converted call sites are the only `confirm(`
  changes.
- [ ] T064 [P] Check spelling and lint on touched files.
  - `grep -ric "catalogue" README.md docs/ app/ tests/` must return nothing.
  - Run flake8 on the Python files this feature touched only.
- [ ] T065 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests`. All
  pass.
- [ ] T066 Final desktop-identity diff (quickstart §3). Re-run T001's curl loop into
  `$SCRATCH/identity-final/` and `diff -r` against `identity-before/`. The only allowed
  differences are whitespace and the `d-none d-sm-block` classes. Record the result in the PR
  description.
- [ ] T067 Run the full e2e suite detached:
  `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup venv/bin/nox -s e2e > "$SCRATCH/e2e-full.log" 2>&1 &`.
  Budget 20–25 minutes and poll the log tail. Every desktop test must pass with no desktop
  test file edited (SC-006). Confirm the working tree is clean afterwards.
- [ ] T068 Run `nox -s screenshots_headless` detached and inspect `git status`.
  - Desktop screenshots should not change materially. Screenshots churn on every run, so
    commit only images whose content genuinely changed.
  - Any real desktop change is an FR-025 regression: fix it rather than commit it.
  - Revert the rest with `git checkout -- <paths>`.
- [ ] T069 **Manual, for Jason on the TC52, not an agent task.** Work through the
  device-verification checklist (quickstart.md §5):
  1. Configure DataWedge Send ENTER and the symbologies. Bookmark `/h/` and set it as the
     home page.
  2. **`inputmode="none"` delivery.** Scan a JA ID on `/h/`. The item screen opens with no
     soft keyboard. If scans do not arrive, switch to the DataWedge keyboard option (D11).
  3. Scan a WIT label and tap +. The keyboard stays down and focus returns.
  4. The keyboard button raises the keyboard. Type, Enter, and the keyboard drops.
  5. Move: a JA ID, a location, a printed `>>DONE<<`, then Validate and Execute.
  6. **DigiKey control-character path.** A DigiKey 2D bag label on `/h/` reaches
     `/h/receive/…` or the order screen, not a mangled search (D11 item 2).
  7. **Android chooser.** Item photo Add opens it, with the camera offered.

  Record the findings in `specs/068-handheld-screens/research.md`, and the DigiKey setting in
  `docs/user-manual.md` (T062's placeholder).

---

## Dependencies & execution order

- **Setup (T001)** runs before T002 and T017. It is the "before" side of the identity diff.
- **Foundational (T002–T010)** blocks every story. Within it, T006 depends on T002, T004 and
  T005. T007 comes before any route. T003, T004, T005, T008, T009 and T010 are parallel.
- **US1 (T011–T016)** needs only Foundational. It is the MVP.
- **US2 (T017–T026)** needs US1's T016 (the minimal product route and template). Do T017–T020
  in order before the rest.
- **US3 (T027–T034)** needs Foundational. T029 and T034 also need US2's product screen. The
  landing buttons from T015 link here.
- **US4 (T035–T039)** needs US1's T016. The Shorten hand-off it tests (T036 scenario 5)
  needs US5's route. Either do US5 first or assert the link `href` only until US5 lands.
- **US5 (T040–T044)** needs Foundational only.
- **US6 (T045–T053)** needs US1 (the `api_scan` flag) and US2 (the product screen for T053).
  Do T045 before T046 and T050.
- **US7 (T054–T061)** needs US6's T046 (the `_receive_url` handheld parameter) and US2's
  product screen.
- **Polish (T062–T069)** comes after the desired stories. T066 and T067 come after every code
  change. T069 is Jason's, and gates calling the feature done.

Story completion order: US1 → US2 → US3 → (US5 → US4) → US6 → US7. US4 and US5 can swap
if T036's Shorten assertion is limited to the `href`.

## Parallel opportunities

- **Foundational**: T003 (`main.js`), T004 (`handheld.css`), T005 (`handheld.js`), T008
  (`scan-capture.js`), T009 (`conftest.py`) and T010 (`handheld.py`) touch disjoint files.
- **US1**: T011 (`test_scan_routes.py`) ∥ T012 (`test_handheld_routes.py`).
- **US2**: after T017–T020, T021 ∥ T022 ∥ T023 (`product-attachments.js`) ∥ T026
  (`handheld.css`). T024 and T025 then run in sequence.
- **US3**: T027 ∥ T028 ∥ T030 (`move-manager.js`) ∥ T033 (`handheld.css`).
- **US4**: T035 ∥ T036 ∥ T037 (`photo-manager.js`).
- **US6**: T047 ∥ T048 ∥ T049. T052 ∥ T051.
- **US7**: T054 ∥ T055 ∥ T056. T059 ∥ T060.
- **Polish**: T062 ∥ T063 ∥ T064.
- **Across stories** (after Foundational and US1): US3 and US5 touch disjoint files, apart
  from `test_handheld_routes.py` and `handheld.css`. Serialize edits to those two shared files.

## Implementation strategy

- **MVP = Phase 1, Phase 2 and US1.** That gives a bookmarked `/h/` that turns any scan into
  the right screen. The item and product screens are summaries, and every other outcome falls
  back to the desktop page.
- **First useful release = all P1 stories** (US1–US3): stock changes at the shelf and moves.
  Run the full e2e suite (T067) and the identity diff (T066) before merging any increment.
- **Then P2** (US4, US5, US6), then **P3** (US7), then the polish phase. The on-device
  checklist (T069) gates release, since FR-029's `inputmode="none"` delivery is unverified
  until it runs on the TC52.

## Desktop risk surface (FR-025)

These tasks edit files that desktop pages load. Each must leave desktop output and behavior
identical, and the desktop tests must pass unedited:

| Task | File | Change |
|---|---|---|
| T002 | `app/templates/base.html` | three blocks, with identical default output |
| T003 | `app/static/js/main.js` | `window.confirmAction` default (native confirm) |
| T008 | `app/static/js/scan-capture.js` | handheld flag, only for `data-scan-capture="handheld"` |
| T014, T046, T057 | `app/product/routes.py` (`api_scan`, `_receive_url`) | URL choice only with the flag |
| T017 | `app/templates/product/detail.html` → `_stock_card.html`, `_label_modal.html` | verbatim extraction |
| T018, T045 | `app/product/routes.py` | `_received_total`, `_receive_purchase_from_form`, `_receive_choice` extracted |
| T019 | `app/templates/product/_label_modal.html` | `d-none d-sm-block` on the help text; the one intended markup change |
| T023 | `app/static/js/product-attachments.js` | `confirm` → `await confirmAction` |
| T030 | `app/static/js/move-manager.js` | `confirm` → `await confirmAction` |
| T037 | `app/static/js/photo-manager.js` | `confirm` → `await confirmAction` |
| T040 | `app/main/routes.py` | `handle_shorten_post` extracted |

They are verified by T020 and T066 (the HTML diff), T065 and T067 (the unedited unit and e2e
suites) and T068 (screenshots).
