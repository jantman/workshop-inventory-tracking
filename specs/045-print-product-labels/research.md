# Phase 0 Research: Print labels for selected products

The spec left no `[NEEDS CLARIFICATION]` markers. What Phase 0 had to settle instead was *where the
reuse the issue asks for actually is*, because the codebase contains both genuinely shared label
machinery and a documented decision to duplicate small pieces of it. Getting that boundary wrong in
either direction is the main risk in this feature.

## What already exists

Surveyed before deciding anything:

| Piece | Location | State |
|---|---|---|
| Label stocks (six) | `app/services/label_printer.py` `LABEL_TYPES` | Single source of truth |
| `GET /api/labels/types` | `app/main/routes.py:1877` | Serves that list to every dialog |
| `POST /api/labels/print` | `app/main/routes.py:1790`, `@csrf.exempt` | Item labels, one JA ID, count 1–99 |
| `POST /api/products/<id>/label` | `app/product/routes.py:2560`, CSRF-protected | Product labels, count 1–99 |
| Product label composition | `app/services/product_label.py` | Description, provenance, Code128 |
| `window.readLabelCount` | `app/static/js/label-count.js` | Shared 1–99 reader and wording |
| `window.csrfFetch` | `app/static/js/csrf.js`, loaded from `base.html` | Global |
| Bulk dialog markup | Inline in `app/templates/inventory/list.html:199-266` | Not shared |
| Bulk dialog logic | Inside `app/static/js/inventory-list.js` | Not shared |
| Products list | `app/templates/product/search.html`, server-rendered Jinja | No selection of any kind |

There are **five** label dialogs in the app today: three bulk-ish ones inline in
`inventory/list.html`, `inventory/add.html` and `inventory/search.html`, the single-product one in
`product/detail.html`, and one generated in JS by `label-printing-modal.js`.

## Decision 1 — No new backend code

**Decision**: Print the selection with N client-side calls to the existing `POST
/api/products/<id>/label`. Add no route, no service function, no schema change.

**Rationale**: The endpoint already does everything one product needs, including the 1–99 count and
composing from the stored record at print time (which gives FR-008 and FR-009 for nothing). A bulk
run is that endpoint, N times. More importantly, the spec's own requirements *ask* for the
client-side loop: FR-010 wants progress naming which product of how many, and FR-011 wants one
failure not to abort the run. A single batch request would have to invent a streaming or
partial-success response shape to report either, and would still need the client to render progress.

**Alternatives considered**:

- *`POST /api/products/labels` taking a list of ids.* Rejected. It buys one round trip per run on a
  LAN where nobody is counting round trips, and costs a new endpoint, a new partial-success response
  contract, and new tests — to deliver strictly less than the loop does. Constitution I forbids
  exactly this trade.
- *Server-side Server-Sent Events for progress.* Rejected outright as scale machinery for a
  single-user LAN app.

**Consequence**: the backend diff for this feature is empty, and `nox -s tests` covers the endpoints
already.

## Decision 2 — Extract the bulk dialog rather than copy it

**Decision**: Move the bulk-print orchestration out of `inventory-list.js` into a shared
`BulkLabelPrintDialog` class in `app/static/js/bulk-label-print.js`, and have both the inventory list
and the new products list construct one.

**Rationale**: The block is about 230 lines — load stocks into the select, enable the print button
only once a stock is chosen, validate the count once *before* anything prints, loop with a progress
bar and a per-entity status line, tally, name every failure, report a total that never overstates
what emerged from the printer, reset on close. Every line of that is generic except four things:

| Varies | Inventory list | Products list |
|---|---|---|
| Element id prefix | `list-bulk` | `product-bulk` |
| Noun in the strings | item / items | product / products |
| What is printed | `POST /api/labels/print` with `{ja_id, label_type, label_count}` | `csrfFetch POST /api/products/<id>/label` with `{label_type, label_count}` |
| Entry display text | the JA ID | the product description |

Four parameters for two callers is an extraction, not an abstraction. It is also the reading of
"reuse as much existing code as possible" that actually reduces total code: after the move,
`inventory-list.js` is ~230 lines shorter and the products page needs ~90 lines rather than ~320.

**Why this is not contradicted by the codebase's own duplication precedent**: `app/product/routes.py:2583`
carries a written decision to duplicate the eight-line count validation rather than share it, because
sharing would have meant coupling two blueprints for eight lines. That reasoning is about *eight
lines across a module boundary*, and it does not extend to *230 lines within the same static/js
directory*. The same file also points at `label-count.js` as the thing that *is* shared, because the
bounds and the wording must agree. This plan sits on the same side of that line.

**Alternatives considered**:

- *Copy the loop into a new products file.* Rejected. It would make a sixth near-duplicate dialog
  and two places to fix the next bug in progress reporting — and the issue explicitly asked for the
  opposite.
- *Convert all five dialogs to the shared class.* Rejected. Three of them are out of scope, FR-014
  requires their behaviour unchanged, and the constitution's review question ("is this larger than
  the problem?") answers itself. They can adopt it later if a reason arises.

**Risk and its mitigation**: the refactor touches a working path. `tests/e2e/test_bulk_label_printing_list.py`
asserts that path in detail — button visibility, the empty-selection alert, stocks loaded,
enable-on-choice, batch print, progress text, modal reset, select-all, API error handling, and the
whole label-count story including that a refused count prints nothing. The shared class must keep the
inventory list's element ids **and its exact user-visible strings**, and that suite is what proves it.

## Decision 3 — Share the markup through a Jinja macro

**Decision**: `app/templates/_bulk_label_modal.html` defines a macro taking `modal_id`, `prefix`,
`noun`, `noun_plural`. `inventory/list.html` calls it with `listBulkLabelPrintingModal` / `list-bulk`
and `product/search.html` with `productBulkLabelPrintingModal` / `product-bulk`.

**Rationale**: The shared JS addresses elements by `<prefix>-...` id. If the two templates hold
hand-written copies of the markup, nothing stops one from drifting — a renamed id produces a dialog
that silently does nothing, with no test failing unless someone wrote a test for that exact id. The
macro makes the ids the JS reads and the ids the template writes the same fact. The existing markup
is already identical in structure between the two pages' needs, including the list of what was
selected, so the macro has no conditional content.

**Alternatives considered**: keeping the markup inline in both templates (rejected: the drift above);
a Jinja `include` with context variables (rejected: a macro's explicit parameter list documents the
contract, an include's implicit context does not).

## Decision 4 — Plain checkboxes, not the InventoryTable component

**Decision**: Add `<input type="checkbox" class="product-checkbox" data-product-id="...">` to the
server-rendered rows and manage selection in `product-list-labels.js` by reading the DOM.

**Rationale**: `app/static/js/components/inventory-table.js` does own selection, and reusing it was
the first thing considered. It cannot be reused: it renders its own `<tbody>` client-side from
`/api/inventory/list`, keys every row on `ja_id`, and carries item-specific formatters and row
actions. The products table is a Jinja `for` loop over rows the server already rendered. Adopting the
component would mean building a products list API and rewriting the page — a far larger change than
the feature, to avoid about thirty lines of checkbox handling.

Reading selection from the DOM also delivers FR-015 without any code: when the server re-renders the
list for a new filter, the checkboxes that exist are exactly the products that are listed, so no
unlisted product can remain selected. A `Set` held in JS would have to be explicitly cleared to
achieve the same thing.

**Alternatives considered**: generalizing `InventoryTable` to a table-agnostic selection mixin —
rejected as speculative generality touching a component used by three pages.

## Decision 5 — Checkbox column first, and the three selectors that costs

**Decision**: The checkbox is the first column, matching the inventory table. Update the three
existing E2E selectors that depend on the description being `td:first-child`.

**Rationale**: A selection checkbox at the right-hand end of a row is not a pattern anyone expects,
and the app already establishes the left-hand convention one page over. The cost is exactly three
selectors — `tests/e2e/test_product_search.py:46`, `:144` and
`tests/e2e/test_product_specifications.py:57` — each changing `td:first-child a` to `td a`. That is
not a workaround: the row has one anchor, and `td a` is the form the twenty-odd other `#product-table`
selectors in the suite already use, so the change makes them consistent with their neighbours rather
than position-dependent.

`#no-products` also goes from `colspan="5"` to `colspan="6"`.

**Alternatives considered**: putting the column last to avoid touching any test — rejected; hiding a
test-shaped decision in the UI is the wrong way round.

## Decision 6 — Screenshots must be regenerated

Not a choice, a consequence. The constitution requires regenerating documentation screenshots when
`app/templates/**` or `app/static/js/**` change, and `tests/e2e/test_screenshot_generation.py:951`
captures the products list, which gains a column and a toolbar button. `nox -s screenshots_headless`
runs and its output is committed; `nox -s screenshots_verify` must pass. Screenshot generation is
excluded from `nox -s e2e`, so an E2E run must still leave the working tree clean.

## Open questions

None. Nothing in Phase 0 required a decision the spec or the constitution did not already determine.
