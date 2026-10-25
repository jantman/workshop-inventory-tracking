# Contract: markup the reused JS controllers bind

The handheld templates reuse these controllers unchanged, except for the
`window.confirmAction` call sites. Each controller looks its elements up by ID or class and
does not null-check most of them, so **every listed element must exist** in the handheld
template, even when it is hidden (`d-none`). The handheld e2e tests pin this contract: a
missing element throws in the controller's constructor and fails the story's test.

## `MoveManager` (`move-manager.js`) with `InventoryMoveManager` / `ProductMoveManager`

IDs bound in `move-manager.js:89-186`:

`preselected-section` (with `data-ids`, its JSON hand-off list), `pending-moves` (table with
`tr[data-id]` rows, each holding `.pending-label`, `.pending-current-location` and
`.pending-current-sub-location`, rendered only when `preselected_items`), `barcode-input`,
`manual-entry-mode`, `scanner-status`, `input-status`, `status-text`, `queue-count`,
`move-queue-empty`, `move-queue-list`, `queue-items` (**a `<tbody>`**: `renderQueueItems()`
appends `<tr>` rows of seven `<td>`), `clear-all-btn`, `clear-queue-btn`, `validate-btn`,
`execute-moves-btn`, `validate-hint`, `form-alerts`, `validation-section`,
`validation-results`.

Also required: `#batch-move-form` holding `input[name="csrf_token"]`, which
`executeMoves()` reads (`move-manager.js:1137`), and `#rejected-items` when `rejected_items`
is non-empty.

The preselected section and the rejected list are copied from `move/_scan_move.html:61-127`,
reworded where needed but with the same IDs and `data-` attributes.

Handheld placement:
- `#barcode-input`, `#scanner-status` and a keyboard button go in the sticky header.
- `#form-alerts` goes directly below, with `max-height` and `overflow-y: auto`.
- `#input-status` comes next, then the queue.
- `#validate-btn` and `#execute-moves-btn` go in the fixed action bar.
- `#clear-all-btn` and `#manual-entry-mode` are present but visually hidden. `handheld.js`
  drives `#manual-entry-mode` from the keyboard button.

Queue as a list: under `.handheld-main #move-queue-list`, set `table`, `thead`, `tbody`, `tr`
and `td` to `display: block`, hide `thead`, and lay each `tr` out as a card. Columns 2 and 3
(current location and current sub-location) collapse to one muted line. The new-location
column is emphasized, and the status and remove columns are floated right. This is CSS only.

## `InventoryShortenManager` (`inventory-shorten.js`)

IDs bound in `inventory-shorten.js:25-64`, plus `#shorten-form` (`:448`):

`source-ja-id` (`name="source_ja_id"`, prefilled from `preselected_ja_id`), `new-length`
(`name="new_length"`), `cut-date` (`name="cut_date"`), `shortening-notes`
(`name="shortening_notes"`), `confirm-operation` (`name="confirm_operation"`, a checkbox),
`scan-ja-id-btn`, `load-item-btn`, `clear-form-btn`, `execute-shortening-btn`,
`scanner-status`, `item-details`, `item-not-found`, `shortening-section`, `notes-section`,
`summary-section`, `history-section`, `length-validation`, `length-validation-alert`,
`item-display-name`, `item-material`, `item-type`, `item-shape`, `current-length`,
`item-location`, `item-status`, `summary-ja-id`, `summary-current-length`,
`summary-new-length`, `summary-removed-length`, `form-alerts`.

`#shorten-form` uses `method="POST"`, has no `action`, and contains `csrf_token`.

Handheld placement:
- `#source-ja-id` goes in the header.
- `#item-details` (compact) and `#new-length` come first in the content.
- `#confirm-operation` and `#execute-shortening-btn` go in the fixed action bar. The checkbox
  is the in-page confirmation (US5 scenario 2), as it is on desktop.

## `PhotoManager` (`photo-manager.js`)

`PhotoManager.init('#photo-manager-container', {itemId: '<JA>', readOnly: false})`. It builds
its own markup inside the container. No IDs are needed beyond the container. Confirmations
go through `window.confirmAction` (`:640`, `:657`).

## Item label modal (`label-printing-modal.js` + `label-count.js`)

`showLabelPrintingModal(jaId, false)` (`label-printing-modal.js:331`) injects its own modal
into `document.body`. Both scripts must be loaded. The modal measured 373 px tall, so it fits
as-is.

## `product-stock.js`

`#stock-card[data-product-id]` and everything inside it, provided by including
`product/_stock_card.html` unchanged.

## `product-label-modal.js`

The trigger button `#print-product-label-btn` and the modal from `product/_label_modal.html`:
`#product-label-modal`, `#product-label-type-select`, `#product-label-count`,
`#product-label-print-confirm` and `#product-label-alerts`.

## `product-attachments.js`

- `#attachments-card[data-product-id]`
- `#attachment-alerts`
- `#product-attachment-input`
- `#upload-product-attachment-btn`
- when attachments exist: `#attachment-selection-toolbar`, `#select-all-attachments`,
  `#delete-selected-attachments`, `#delete-selected-attachments-label`, `#attachment-list`
  with `.attachment-row` tiles each holding `.attachment-select[data-attachment-id]`
- otherwise: `#no-attachments`

The handheld does **not** render `.delete-attachment-btn`, the desktop's unconfirmed
single-tile delete (research.md D9). The document-level `paste` handler is harmless on the
handheld.

## `scan-capture.js`

`<input id="handheld-scan-input" data-scan-capture="handheld" inputmode="none" autocomplete="off">`.
The `handheld` attribute value is the only new contract (see [scan-api.md](scan-api.md)).

## `handheld.js` (new)

- `[data-handheld-scan]` marks the screen's scan entry: the one input focused on load and
  after actions. It is set on `#handheld-scan-input`, `#barcode-input` or `#source-ja-id`.
- `[data-keyboard-for="<input id>"]` is the keyboard button (FR-029).
- `#handheld-confirm-modal` (in `handheld/base.html`), with `#handheld-confirm-message`,
  `#handheld-confirm-ok` and `#handheld-confirm-cancel`, backs `window.confirmAction`.
