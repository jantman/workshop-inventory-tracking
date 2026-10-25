# Feature Specification: Handheld Screens

**Feature Branch**: `speckit/068-handheld-screens`

**Created**: 2026-10-25

**Status**: Draft

**Input**: User description: "Handheld (Zebra TC52) screens: a small set of purpose-built, scan-first screens for a 360x512 CSS px portrait touch viewport, reached from a dedicated handheld landing page that the user bookmarks and sets as the handheld browser's home page. Scanning arrives as DataWedge keystroke input ending in Enter. Screens: landing (scan anything via /api/scan, routing results to handheld screens; buttons for the tasks), item (print item label, item photos via Android's chooser, links to shorten and move), product (quantity/counting, stock status, print product label, attachments upload, link to move), shorten, move (items and products; reuse move-manager.js), receive a purchase (including one line per scanned distributor bag), and captured order (bulk select and receive lines). Reuse existing JSON APIs, JS controllers and modals; no business logic duplicated; anything else falls back to desktop pages; desktop pages unchanged. Deliberately reverses spec 001's assumption that a separate mobile interface is out of scope. E2E coverage at a 360x512 touch viewport."

## Context

The operator now has a Zebra TC52 handheld: an Android device with a built-in barcode imager. Its browser shows a usable area of **360×512 CSS px** in portrait. The imager types each scan into the focused field and ends it with Enter. This works with the application today and was verified on the device (`research.md`, "Observed on the device").

The existing pages work at that size but are not usable for work at the shelf. A survey of the twelve handheld tasks at 360×512 (`research.md`, "Survey at 360×512") found these problems:
- The header scan box is hidden behind the menu toggle on every page.
- The controls for quantity, stock status and attachments sit 3.5–5 screens down the product page.
- The commit buttons for shorten, move and receive are 2–4 screens down.
- The page a JA ID scan lands on scrolls sideways.
- The captured-order table has rows about 400 px tall and checkboxes about 14 px wide.

This feature adds a small set of handheld screens, each built around one scan and one action, and reached from a handheld landing page.

**This deliberately reverses an assumption in spec 001**, which said "a separate mobile-specific interface is out of scope" (`specs/001-product-catalog/spec.md`, Assumptions). Spec 001 assumed the single responsive interface would serve handhelds. The measurements show it doesn't at this viewport, and reworking every desktop page to fit would cost more and still give a desktop-shaped result (`research.md`, "Recommendation").

The handheld screens are a second presentation of operations the application already performs. They introduce no new inventory or catalog rules.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scan anything from the handheld landing page (Priority: P1)

The operator picks up the handheld. Its browser opens on the handheld landing page, which is bookmarked on the home screen and set as the browser's home page. They scan any label without tapping anything first:
- A JA ID opens that item's handheld item screen.
- A product's own code or retail barcode opens its handheld product screen.
- A distributor bag label opens the handheld receive flow for that line.

Any scan the handheld screens don't cover opens the matching desktop page.

**Why this priority**: Every other handheld task starts from a scan. Without this screen the handheld has no entry point.

**Independent Test**: Seed an item and a product. Open the landing page at 360×512, deliver each code as keystrokes followed by Enter without tapping, and confirm each opens the right handheld screen.

**Acceptance Scenarios**:

1. **Given** the landing page has just opened, **When** the operator scans `JA200001` without tapping anything, **Then** the handheld item screen for `JA200001` opens.
2. **Given** the landing page, **When** the operator scans a product's internal code or a retail barcode known to the catalog, **Then** that product's handheld product screen opens.
3. **Given** the landing page, **When** the operator scans a distributor label that matches exactly one outstanding purchase line, **Then** the handheld receive screen for that line opens.
4. **Given** the landing page, **When** the operator scans something the handheld screens do not cover (an unknown product code that would start a new product, or free text that would search), **Then** the existing desktop page that the desktop scan box would open opens.
5. **Given** the landing page, **When** it is viewed at 360×512, **Then** the scan entry and the task buttons are visible without scrolling or opening a menu.
6. **Given** any handheld screen other than Move and Shorten, **When** the operator scans, **Then** the scan is handled the same way as on the landing page, without returning to it first. On Move and Shorten the scan entry is the task's own input. A scan there is a subject, a location or a JA ID to shorten, as on the desktop pages (`research.md`, D4).

---

### User Story 2 - Adjust a product at the shelf (Priority: P1)

The operator scans a product's label at the bin. The handheld product screen shows the product's name and location, and the stock controls without scrolling: quantity −/+ and set, start or stop counting, and stock status (Low, Out, clear). They make one change and scan the next product.

The same screen also offers:
- print a product label
- add or delete an attachment, such as a photo taken with the handheld's camera
- move this product

**Why this priority**: Stock counting and status at the shelf is the most frequent handheld task. Today it is the furthest from reach: the controls are 4–5 screens down the product page.

**Independent Test**: Seed a counted product with a location. Open its handheld product screen at 360×512, change the quantity with a tap, set it to Low, and confirm both changes appear on the desktop product page.

**Acceptance Scenarios**:

1. **Given** a counted product, **When** its handheld product screen opens at 360×512, **Then** its name, location and the quantity controls are visible without scrolling.
2. **Given** the handheld product screen, **When** the operator taps + or −, or enters a number and taps Set, **Then** the product's quantity changes exactly as the same control on the desktop product page would change it.
3. **Given** the handheld product screen, **When** the operator taps Low, Out or clear, **Then** the product's stock status changes exactly as it would on the desktop product page.
4. **Given** a product that is not counted, **When** the operator taps start counting, **Then** counting starts as it would on the desktop product page. Stop counting works the same way.
5. **Given** the handheld product screen, **When** the operator taps Print label, **Then** the product label dialog opens and its Print button is visible without scrolling.
6. **Given** the handheld product screen, **When** the operator adds an attachment, **Then** the device's file chooser opens, offering the camera and files, and the chosen file is attached to the product.
7. **Given** a product with attachments, **When** the operator deletes one from the handheld product screen and confirms, **Then** it is removed.
8. **Given** the handheld product screen, **When** the operator taps Move, **Then** the handheld move screen opens with this product already queued.

---

### User Story 3 - Move items and products by scanning (Priority: P1)

The operator opens handheld Move from the landing page, or from an item or product screen. They scan an item or product, scan a location (and optionally a sub-location), repeat, and finish with the Execute button or the existing DONE barcode. The queue is shown as a list that fits the width. Execute is always reachable without scrolling.

**Why this priority**: Moving stock is a core shelf task. The scanning loop already works on the handheld, but finishing a move takes 2–3 screens of scrolling, and the queue table scrolls sideways.

**Independent Test**: Seed two items. Open handheld Move at 360×512, scan both with a location each, execute, and confirm both items' locations changed.

**Acceptance Scenarios**:

1. **Given** handheld Move at 360×512, **When** the operator scans an item and then a location, **Then** the move is queued and shown in the queue without horizontal scrolling.
2. **Given** a queue of one or more moves, **When** the operator taps Execute, **Then** every queued move is applied exactly as on the desktop move page. Execute is reachable without scrolling regardless of queue length.
3. **Given** a queue, **When** the operator scans the DONE barcode, **Then** the same validation and completion happen as on the desktop move page.
4. **Given** a scan the move rules reject, such as an unknown ID or an invalid location, **When** it is scanned, **Then** the operator sees the rejection, and the scan input stays visible and focused.
5. **Given** handheld Move, **When** the operator scans products instead of items, **Then** product moves behave exactly as on the desktop product move page.

---

### User Story 4 - Item screen: label, photos, and starting a shorten or move (Priority: P2)

The operator scans an item's JA ID. The handheld item screen shows a short summary of the item (type, shape, material, dimensions, length, location) and buttons for:
- print label
- photos
- shorten
- move

The screen does not scroll sideways.

**Why this priority**: The JA ID scan currently lands on the full desktop edit form, which overflows to 502 px wide and has photos 3 screens down. The item screen is the hub for tasks 12, 13, 16 and 17.

**Independent Test**: Seed an item with one photo. Open its handheld item screen at 360×512. Confirm there is no horizontal overflow, the label dialog opens with Print visible, a photo can be added and deleted, and Shorten opens with the item loaded.

**Acceptance Scenarios**:

1. **Given** an active item, **When** its handheld item screen opens at 360×512, **Then** its summary and the action buttons are visible without scrolling, and the page does not scroll sideways.
2. **Given** the handheld item screen, **When** the operator taps Print label, **Then** the existing item label dialog opens and prints exactly as it does from the desktop item page.
3. **Given** the handheld item screen, **When** the operator adds a photo, **Then** the device's file chooser opens, offering the camera and files, and the photo is attached to the item exactly as on the desktop item page.
4. **Given** an item with photos, **When** the operator views them on the handheld item screen, **Then** thumbnails are shown and any photo can be opened full size or deleted (after confirmation).
5. **Given** the handheld item screen, **When** the operator taps Shorten or Move, **Then** the matching handheld screen opens with this item already loaded or queued.
6. **Given** a scanned JA ID that does not exist, or names an inactive item, **When** the item screen opens, **Then** it says so plainly and offers to open the desktop item page.

---

### User Story 5 - Shorten an item at the saw (Priority: P2)

The operator opens handheld Shorten from the item screen or the landing page, or scans a JA ID into it. They see the item's current length, enter the new length, and tap Execute. Execute is reachable without scrolling.

**Why this priority**: Shortening happens at the saw, away from the desk. Today the Execute button is about four screens down.

**Independent Test**: Seed an item 1000 mm long. Shorten it to 600 mm on handheld Shorten at 360×512. Confirm the item now reads 600 mm and its shortening history is kept.

**Acceptance Scenarios**:

1. **Given** handheld Shorten, **When** the operator scans or loads a JA ID, **Then** the item's current length is shown and the new-length entry is visible without scrolling.
2. **Given** a loaded item and a valid new length, **When** the operator taps Execute and confirms, **Then** the item is shortened exactly as on the desktop shorten page, including its retained shortening history.
3. **Given** a new length that is not shorter than the current length, or is not a valid measurement, **When** the operator taps Execute, **Then** the same rejection the desktop page gives is shown and nothing changes.

---

### User Story 6 - Receive a purchase, one bag at a time (Priority: P2)

The operator opens a delivery and scans each bag's distributor label.
- **One outstanding line matches:** the handheld receive screen opens for that line, with any quantity the label carries pre-filled. The operator confirms the quantity, says whether they counted it, and taps Receive.
- **Several lines match:** the operator picks one from a short list.
- **No lines are outstanding:** the screen says so.

**Why this priority**: Receiving is done with the goods in hand. On the desktop receive page the form starts at y≈812 and Confirm sits at y≈1376.

**Independent Test**: Seed an outstanding purchase whose distributor label matches one line. Scan it on the handheld landing page at 360×512, receive it, and confirm the purchase reads received with the entered quantity.

**Acceptance Scenarios**:

1. **Given** a distributor label matching one outstanding line, **When** it is scanned, **Then** the handheld receive screen opens with the line's product, the ordered quantity and any label quantity pre-filled. Quantity, the counted choice and Receive are all visible without scrolling.
2. **Given** the handheld receive screen, **When** the operator taps Receive, **Then** the purchase is received exactly as on the desktop receive page, including how a counted receipt updates the product's count.
3. **Given** a label matching several outstanding lines, **When** it is scanned, **Then** the handheld screens list the candidates and let the operator choose one, instead of choosing for them.
4. **Given** a label matching only lines that are already received, **When** it is scanned, **Then** the operator is told nothing is outstanding, and nothing is received twice.
5. **Given** the operator opens a product's outstanding purchase from the handheld product screen, **When** they choose to receive it, **Then** the same handheld receive screen opens.

---

### User Story 7 - Receive several lines of a captured order (Priority: P3)

The operator opens a captured order on the handheld. They get there by scanning a label that names an order with several candidate lines, from a list of orders with outstanding lines linked from the landing page, or from an Order button on a product screen whose product has an outstanding line. The order's lines are shown as cards. Each card is selectable with a full-width tap target, and Receive Selected stays reachable without scrolling.

**Why this priority**: Bulk receiving works on the desktop today. On the handheld it is a convenience for unpacking a whole order at the bench with the device.

**Independent Test**: Seed a captured order with three outstanding lines. Open it on the handheld at 360×512, select two cards, receive them, and confirm exactly those two lines are received.

**Acceptance Scenarios**:

1. **Given** a captured order with outstanding lines, **When** it opens on the handheld at 360×512, **Then** each line is a card showing product, quantity and state, with no horizontal scrolling.
2. **Given** the order screen, **When** the operator taps cards to select them and taps Receive Selected, **Then** exactly the selected lines are received, as bulk receive does on the desktop order page.
3. **Given** lines that are already received, **When** the order screen opens, **Then** they are shown as received and cannot be selected.
4. **Given** captured orders with outstanding lines, **When** the operator opens the handheld order list from the landing page, **Then** each such order is listed (vendor, order number, outstanding line count), and tapping one opens its handheld order screen. Orders with nothing outstanding are not listed.
5. **Given** a product with an outstanding purchase line, **When** its handheld product screen opens, **Then** an Order button opens the handheld order screen for that line's order. With more than one such order, the operator chooses which.

---

### Edge Cases

- **Scanning while a screen is busy:** a scan arrives while a screen is still saving a previous action. The earlier action must complete; the new scan must not be lost or applied to the wrong record.
- **Scans with no handheld screen:** a scan whose outcome has no handheld screen (a new product, a search) opens the desktop page. The operator gets back to the handheld screens with the browser's home button, which is set to the landing page.
- **Soft keyboard over the screen:** the Android on-screen keyboard covers about half of a 512 px screen. Tapping the header Scan box on the device raises it (observed 2026-10-25). Handheld scan entries therefore never raise it on their own; a keyboard button raises it for typing a code by hand (FR-029).
- **Device rotated to landscape:** the screens must remain usable, with no horizontal overflow and the primary action reachable, but landscape is not a design target.
- **Desktop browser at a handheld URL:** the handheld screens work but are not designed for it; nothing redirects between the two sets of screens.
- **Dialogs:** a blocking browser dialog during scanning can stall keystroke delivery on the device (`research.md`, DataWedge). Confirmations on handheld screens must use in-page dialogs, not browser alert or confirm boxes.

## Requirements *(mandatory)*

### Functional Requirements

**Handheld landing page and scanning**

- **FR-001**: The system MUST provide a handheld landing page at a stable address that can be bookmarked and set as the device browser's home page.
- **FR-002**: Every handheld screen MUST have a scan entry that holds keyboard focus when the screen loads and after each action completes, so that a scan works without a tap.
- **FR-003**: A scan on a handheld screen (other than Move and Shorten, whose scan entry is the task input; see US1 scenario 6) MUST be resolved by the same rules as the desktop header scan box. The result MUST open:
  - **JA ID:** the handheld item screen.
  - **Known product:** the handheld product screen.
  - **Receive result:** the handheld receive flow (a single line, a choice among candidates, the handheld order screen, or "nothing outstanding").
  - **Any other result:** the page the desktop scan box would open.
- **FR-004**: The landing page MUST offer buttons for handheld Move (items), Move (products), Shorten and Orders. These and the scan entry MUST be visible at 360×512 without scrolling.
- **FR-005**: Every handheld screen MUST provide a one-tap way back to the landing page.

**Layout**

- **FR-006**: No handheld screen may scroll horizontally at 360×512, at any data length the survey seeded (`research.md`).
- **FR-007**: On every handheld screen, the scan entry and the primary action (Execute, Receive, Receive Selected, Set) MUST be reachable at 360×512 without scrolling, however long the page's content is.
- **FR-008**: Tappable controls on handheld screens MUST be at least 44 CSS px in their smaller dimension. Selection targets (checkbox rows, cards) MUST span the row, not just a 14–16 px box.
- **FR-009**: Handheld screens MUST NOT show the desktop navigation bar.

**Item and shorten**

- **FR-010**: The handheld item screen MUST show the item's JA ID, type, shape, material, dimensions, length and location. It MUST offer Print label, Photos, Shorten and Move.
- **FR-011**: Printing an item label from the handheld MUST use the existing item label dialog and printing behavior unchanged.
- **FR-012**: The handheld item screen MUST let the operator add photos (through the device's standard file chooser, which offers the camera), view them full size, and delete them after confirmation. The behavior MUST match the desktop item page.
- **FR-013**: Handheld Shorten MUST perform the existing shorten operation, preserving the item lifecycle and shortening history invariants exactly as the desktop shorten page does.

**Product**

- **FR-014**: The handheld product screen MUST show the product's name, location and sub-location, quantity and stock status first. It MUST offer quantity −/+ and set, start or stop counting, Low/Out/clear, Print label, attachments and Move.
- **FR-015**: Quantity, counting and stock-status changes from the handheld MUST have exactly the effect the same controls have on the desktop product page.
- **FR-016**: The product label dialog MUST fit within 512 px of height on the handheld, with its Print button visible without scrolling. Printing behavior MUST be unchanged.
- **FR-017**: The handheld product screen MUST let the operator add an attachment through the device's standard file chooser, and delete one after confirmation.

**Move**

- **FR-018**: Handheld Move MUST support moving items and moving products with the same scanning sequence, validation, DONE barcode and results as the desktop move pages.
- **FR-019**: The handheld move queue MUST be presented as a list that fits 360 px. Validation messages MUST NOT push the scan entry out of view.
- **FR-020**: Move started from an item or product screen MUST open with that item or product already queued.

**Receiving**

- **FR-021**: The handheld receive screen MUST receive a purchase line with the same effects as the desktop receive page. That includes pre-filling a label's quantity and how a counted receipt updates the product's count.
- **FR-022**: When a scan matches several outstanding lines, the handheld MUST list them and let the operator choose. It MUST NOT choose for them.
- **FR-023**: The handheld order screen MUST show a captured order's lines as selectable cards and receive exactly the selected lines, with the same effects as bulk receive on the desktop order page. Already-received lines MUST NOT be selectable.
- **FR-023a**: The handheld MUST provide a list of captured orders that have outstanding lines, reached from the landing page. Each entry opens that order's handheld order screen.
- **FR-023b**: The handheld product screen MUST offer an Order button when the product has an outstanding purchase line. It opens the handheld order screen for that order, or, with several such orders, a choice among them.

**Boundaries**

- **FR-024**: Handheld screens MUST perform every change through the application's existing operations. They MUST NOT introduce new inventory, catalog or receiving rules, and MUST NOT write data any other way.
- **FR-025**: Existing desktop pages MUST behave and look the same as before this feature. The one exception is the product label dialog's small-screen fit (FR-016), which MUST NOT change its appearance at desktop widths.
- **FR-026**: Handheld screens MUST use in-page confirmations, never browser alert, confirm or prompt dialogs.

**Testing**

- **FR-027**: Each user story MUST have end-to-end tests run at a 360×512 touch viewport. The tests deliver scans as keystrokes ending in Enter and assert FR-006 (no horizontal scroll) and FR-007 (primary action reachable).

**Documentation**

- **FR-028**: The user manual MUST describe how to set up the handheld scanner and the handheld screens:
  - the scanner setting that appends Enter
  - which barcode types to enable
  - how to bookmark the landing page and set it as the browser's home page

**Keyboard**

- **FR-029**: Handheld scan entries MUST NOT raise the device's on-screen keyboard when they take focus, whether on load, after an action or on a tap. Scanned keystrokes MUST still be received. Each scan entry MUST have a visible keyboard button. Tapping it raises the on-screen keyboard so a code can be typed by hand and submitted with Enter. After that submission, the entry returns to not raising the keyboard.

### Key Entities

No new data. The handheld screens present existing entities:

- **Inventory item**: identified by JA ID, with dimensions, location, photos and shortening history.
- **Product**: identified by its own code or identifiers. Has location, quantity, counting state, stock status and attachments.
- **Purchase / order line**: an outstanding or received line of a captured order.
- **Captured order**: a vendor's order with its lines.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From the handheld landing page, the operator can scan a label and reach the right item or product screen with zero taps.
- **SC-002**: Each of the twelve handheld tasks (1, 12, 13, 16, 17, 22, 23, 24, 25, 26, 32, 33 in `research.md`) can be completed at 360×512 with no horizontal scrolling. For each task, the controls it needs are visible without vertical scrolling once its screen is open.
- **SC-003**: Changing a product's quantity or stock status after a scan takes at most two taps, down from opening the menu, tapping the scan box, then scrolling about four screens.
- **SC-004**: Shortening, moving and receiving each reach their commit action without scrolling, down from 2–4 screens.
- **SC-005**: Every handheld change produces a record identical to the one the same action on the desktop page produces. The tests verify this by checking results through the desktop pages.
- **SC-006**: No desktop page's behavior changes, as shown by the existing end-to-end suite passing unchanged.

## Assumptions

- **Device and setup:** the device is a Zebra TC52 on Android 14 with current Chrome. Its scanner is configured to type each scan and append Enter (`research.md`, "Observed on the device"). Device setup is documented in the user manual as part of this feature; it is not automated.
- **Viewport:** the design target is 360×512 CSS px, portrait, touch. Other phones of similar size benefit, but are not tested separately.
- **Connection:** plain HTTP on the LAN, as today. Nothing here needs a secure connection: no camera access from the page, no offline mode, no installable app. Photos and attachments use the device's standard file chooser.
- **No device detection:** the operator reaches the handheld screens through the landing-page bookmark. Nothing redirects between handheld and desktop screens based on the device.
- **After an action:** the operator stays on the current handheld screen, which shows a confirmation and refocuses the scan entry so the next scan can follow immediately.
- **Scope:** the handheld covers only tasks 1, 12, 13, 16, 17, 22, 23, 24, 25, 26, 32 and 33 from the task inventory (`research.md`). Adding or editing items or products, search, lists, reorder, capture, taxonomy and admin stay desktop-only and fall back to the desktop pages.
- **Labels:** printing goes to the same label printers through the same path as the desktop pages.
- **Spec 001 reversal:** this feature supersedes spec 001's assumption that a separate mobile interface is out of scope, for the handheld tasks listed above only. Spec 001's other touch requirements (FR-036, SC-010) still apply to the desktop pages.
