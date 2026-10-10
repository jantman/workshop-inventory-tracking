# UI Contract: Product Label Dialog Auto-Close

| Dialog | Element | Closes itself when | Stays open when |
|---|---|---|---|
| Product detail | `#product-label-modal` | POST `/api/products/<id>/label` returns `success: true`, 2 s after `#product-label-alert` shows the success text | the POST fails or the count/stock is refused |
| Products list | `#productBulkLabelPrintingModal` | a run ends with 0 failures, 2 s after `Complete: …` and Done are shown | any entry failed, or the count was refused |
| Order page / Outstanding Products | `#orderBulkLabelPrintingModal` | likewise | likewise |
| Inventory list (unchanged) | `#listBulkLabelPrintingModal` | never (closed with Done) | always |

`BulkLabelPrintDialog` constructor gains `closeOnSuccess` (boolean, default `false`).

Any pending close is cancelled when the dialog is reopened or hidden. A dialog closed
automatically reopens in the same state as one closed by hand.
