# Phase 0 Research: Delete a Purchase

**Feature**: `specs/032-delete-purchase` | **Date**: 2026-08-31

No `NEEDS CLARIFICATION` markers survived `/speckit-specify` — the two open questions
(where the control lives, and what happens to a tracked count) were answered before the
spec was finalized. What follows is the design research the plan rests on: seven decisions,
each with what was chosen, why, and what was rejected.

---

## R1 — The confirmation is a server-rendered page, not a dialog

**Decision**: `GET /purchases/<int:purchase_id>/delete` renders a confirmation page
(`app/templates/product/purchase_delete.html`); `POST` to the same address performs the
deletion. Exactly the shape `purchase_receive` already has.

**Rationale**:

- **FR-004 needs the attachment count, and only the server knows it.** The product page
  already builds a `purchase_attachments` dict, but the order screen
  (`order_detail`, `routes.py:1428`) loads purchases with `selectinload(Purchase.product)`
  and nothing else. A dialog fed from the DOM would force *both* listing routes to grow an
  attachment-count query. A confirmation page reads it once, in one place, for both entry
  points — `PhotoService.get_purchase_attachments()` already exists and needs no new
  method.
- **FR-015 ("identical wherever it is offered") becomes free.** One template, one route.
  With a dialog it would be a rule to maintain across two pages.
- **No JavaScript at all.** The purchase-history table and the order table are pure Jinja
  today. A `<form>` with a `csrf_token()` hidden field keeps them that way.
- **It makes the E2E tests boring.** The flow is navigate → click → navigate, with no
  `fetch` boundary (CLAUDE.md pattern A) and no browser dialog to trap.

**Alternatives considered**:

- **`window.confirm()` + a `fetch('DELETE')`** — the precedent used by
  `product-attachments.js:174` (bulk attachment delete) and `components/item-actions.js:77`
  (item delete). Rejected: it needs the attachment count in the DOM of both listings, adds
  a JS file, and puts a dialog in the E2E path. Dialog handling *is* established in the
  suite (`test_admin_materials.py:115`, `test_bulk_label_printing_list.py:117`), so this
  was viable — it is simply more moving parts for the same outcome.
- **A Bootstrap modal populated from `data-` attributes**, following
  `_rename_modal.html` + `taxonomy-rename.js`. Rejected for the same reason plus one more:
  the modal would have to be rendered into two different templates.

---

## R2 — The whole deletion happens in one `CatalogService` session

**Decision**: `CatalogService.delete_purchase(purchase_id)` opens a single
`self._session()` and inside it: collects the `photo_id`s of the purchase's attachments,
builds the return summary, `session.delete(purchase)`, `session.flush()`, then deletes each
of those photos that no longer has a `ProductAttachment` or `ItemPhotoAssociation`
referencing it. One commit, or one rollback (FR-012).

**Rationale**:

- `Purchase.attachments` is declared `cascade='all, delete-orphan', passive_deletes=True`
  (`database.py:1123`) and `product_attachments.purchase_id` is `ON DELETE CASCADE`
  (`database.py:1371`), so the attachment **rows** already go on their own. What does not
  go is the **stored photo** behind each one — FR-006 says it must, when nothing else wants
  it.
- The orphan check must run *after* the attachment rows are gone, hence the `flush()`
  between. This is the same sequence `PhotoService.delete_attachment` uses
  (`photo_service.py:768-779`).

**Alternatives considered**:

- **Route calls `CatalogService.delete_purchase()` then `PhotoService` to clean up.**
  Rejected outright: `CatalogService` and `PhotoService` hold *separate* sessionmakers
  bound to the same engine (`catalog_service.py:119`, `photo_service.py:73`), so this is
  two transactions. A crash between them leaves photos that FR-006 says are gone. FR-012
  makes this non-negotiable.
- **Let `PhotoService.cleanup_orphaned_photos()` sweep them up later.** Rejected: it is a
  sweep with no caller on this path, it is not atomic, and FR-006 wants the file gone with
  the purchase, not eventually.
- **Extract the "is this photo still referenced?" predicate into a shared helper** so this
  becomes its second reuse rather than its third copy (it exists at
  `photo_service.py:768` and again, as a bulk `~exists()` form, at `photo_service.py:327`).
  Rejected *for now*: the helper would have to take a session, which means
  `catalog_service.py` importing from `photo_service.py` — a coupling that does not exist
  today (`catalog_service` imports no other service except `services.order_vendors`). Six
  lines of duplication is cheaper than a new inter-service dependency, and Principle I
  prefers the boring version. **The duplication must carry a comment naming the other two
  copies**, so that a future change to the rule finds all three.

---

## R3 — Where the operator lands is a flag, not a URL

**Decision**: the confirmation carries `return_to` with exactly two accepted values,
`product` (the default) and `order`. After deleting, the route redirects to
`product.product_detail` or to `product.order_detail`, and it builds the order address
from the **summary the deletion returned** — the purchase's own vendor and
`supplier_order_reference` — not from anything the caller supplied. An unrecognized value
falls back to `product`.

**Rationale**:

- The purchase already knows which order it belongs to, so passing an order number in the
  request would be passing back data the server is about to look up anyway.
- It sidesteps the redirect-target question entirely. Per the constitution's threat model,
  an open-redirect defense would be inflating a threat model that explicitly excludes
  anonymous attackers — but the right way to not need that defense is to never accept a
  URL, not to write a validator.
- `return_to=order` must degrade to the product page when the purchase carries no
  `supplier_order_reference` (a hand-recorded or listing-captured purchase). That is not an
  error; there is no order to go back to.

**Alternatives considered**: a `next` parameter carrying a full URL (rejected, above); a
separate route per entry point (rejected — two routes to keep identical, contradicting
FR-015).

---

## R4 — The service returns a summary value object

**Decision**: add `PurchaseDeletion` to `app/models.py` — a frozen dataclass carrying
`purchase_id`, `product_id`, `vendor`, `order_date`, `quantity`, `unit_price`,
`supplier_order_reference` and `attachments_deleted`. `delete_purchase` returns it;
`get_purchase` returning `None` is what a missing purchase looks like, and the route
raises `ItemNotFoundError` from that (FR-011).

**Rationale**: FR-008 requires the flash to say *what* was removed, and the route needs
`product_id` and the order reference to redirect (R3) — all of it read from a row that no
longer exists by the time the route is told. Reading the purchase in the route before
calling the service would be a second session and a race. Returning a detached ORM object
is worse: it is a deleted instance, and touching an unloaded attribute on it is undefined.

**Precedent**: `OrderCaptureResult`, `OrderCaptureReview`, `ScanResolution` and
`LabelOutcome` all exist in `app/models.py` for exactly this purpose. This is not a new
pattern.

**Alternatives considered**: returning `bool` and having the route pre-read the purchase
(rejected: race, two sessions); returning a `dict` (rejected: the file's peers are all
dataclasses).

---

## R5 — No migration, and the check that proves it

**Decision**: no Alembic revision. Nothing about the schema changes.

**Rationale**: the only foreign keys in play — `product_attachments.purchase_id →
purchases.id ON DELETE CASCADE` and `product_attachments.photo_id → photos.id ON DELETE
CASCADE` — shipped with `b1a0c0d10005_add_product_attachments_table.py`. A grep for
`purchases.id` across `app/database.py` and `migrations/versions/` returns those two rows
and nothing else, so `product_attachments` is the **only** table referencing a purchase.
Deleting a purchase can therefore not strand a row anywhere else.

This matters beyond "no work to do": it is the evidence for FR-005 (the product and
everything else about it survives) and for the edge case "the last purchase of a product"
— nothing cascades upward from a purchase to anything.

---

## R6 — The count is left alone, and the confirmation says so out loud

**Decision**: FR-007. `delete_purchase` does not touch `products.quantity`,
`products.quantity_updated_at`, `products.stock_status` or
`products.stock_status_updated_at`. The confirmation page states this in words before the
operator commits (FR-004).

**Rationale** (the evidence the spec's answer rests on): receiving through
`receive_purchase` **does** move a tracked count — `catalog_service.py:1598` adds
`purchase.quantity` to `product.quantity`, and `:1608` clears a manual stock flag.
Capturing an order line already marked arrived does **not** (031 FR-028). Nothing on the
`purchases` row distinguishes the two afterwards. So a subtraction would be right for some
received purchases and would invent a loss for the rest, and it would move a number nobody
has looked at — which is precisely what `quantity_updated_at` ("the last time somebody
counted") exists to prevent.

The operator is not left stuck: `detail.html:324-330` already carries increment and
decrement controls for the counted quantity.

**Alternatives considered**: subtract the received quantity (rejected, above); ask on the
confirmation (rejected — a decision on every deletion, almost always irrelevant, and the
operator can already adjust the count directly).

---

## R7 — Testing, and the two gates this change trips

**Unit** (`tests/unit/test_purchase_delete.py`, fixtures via `tests/conftest.py`):
the service method — outstanding and received purchases, with and without attachments, a
shared photo that must survive, a missing purchase, the product and its sibling purchases
surviving, `inventory_items` untouched (Principle VI), and the count/age/flag left alone.
The route — GET renders the details and the attachment count, POST deletes and redirects
per `return_to`, a second POST reports not-found.

**E2E** (`tests/e2e/test_purchase_delete.py`): seed through
`live_server.add_test_data([...])`, never through the Add Item form. Both entry points, the
cancel path, and the derived views (reorder, captured orders) losing the row. Every wait is
a navigation or an `expect()` on a locator — this feature has no `fetch`, no dialog and no
JS-rendered region, so none of CLAUDE.md's six trap patterns apply. Negative assertions
("the row is gone") must `expect()` the table into existence first, or they pass against a
page that has not loaded.

**Gate 1 — screenshots.** `detail.html`, `order.html` and a new template mean
`app/templates/**` changed, so `nox -s screenshots` (or `screenshots_headless`) must be
regenerated and committed, and must pass `screenshots_verify`. CI blocks on stale
screenshots. Screenshots churn on every run; check what actually differs before committing
the diff.

**Gate 2 — the E2E clock.** The suite is ~13m 45s warm and the constitution allows 15
minutes, which is under 90 seconds of margin. This feature adds tests to it. Run it
detached and poll — most agent bash tools cap at 10 minutes regardless of the timeout
requested — and budget 20 minutes cold.
