# Feature Specification: Delete a Purchase

**Feature Branch**: `032-delete-purchase`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "issue #130 on this repo — No way to delete a purchase, so a mis-captured one is permanent"

## User Scenarios & Testing *(mandatory)*

The operator is the only user. Everything below is one person correcting their own
records after a capture went wrong.

### User Story 1 - Delete a mis-captured purchase from the product page (Priority: P1)

The operator opens a product and sees two rows in its purchase history for what was
physically one purchase — the listing capture and the order capture of the same thing
(issue #129). They delete the wrong one from the purchase history table, confirm what
they are about to lose, and the row is gone. Spend, quantity-on-order and the reorder
view stop double-counting.

**Why this priority**: This is the whole issue. Without it every other capture defect is
unrecoverable without shell access to the database host, and the "report it and let the
operator decide" posture that spans all three vendors terminates in a decision the
operator cannot act on. On its own it is a complete, useful feature.

**Independent Test**: Record two purchases against one product, delete one from the
product page, reload, and confirm one row remains and the other is gone from every view
that reads purchases.

**Acceptance Scenarios**:

1. **Given** a product with two purchases in its history, **When** the operator deletes
   one and confirms, **Then** the product page reloads showing one purchase, and a
   message names what was removed.
2. **Given** the confirmation prompt is showing, **When** the operator cancels, **Then**
   nothing is deleted and the history is unchanged.
3. **Given** a product whose only purchase is deleted, **When** the page reloads,
   **Then** the purchase history shows its empty state and the product itself still
   exists with its identifiers, specifications, photos and product-level attachments
   intact.
4. **Given** an outstanding (never-received) purchase, **When** it is deleted, **Then**
   it no longer appears as on-order anywhere — the product page's outstanding banner,
   the reorder view, and the captured-orders list.
5. **Given** a purchase that carries attachments, **When** the operator opens the
   confirmation, **Then** the confirmation states how many attached files will be
   deleted with it, and after confirming those files are gone.
6. **Given** a received purchase against a product with a tracked count, **When** it is
   deleted, **Then** the confirmation states plainly that the product's counted quantity
   will not change, and after deleting the count, its age and any stock flag are
   unchanged.

---

### User Story 2 - Delete an orphaned purchase from the order it no longer belongs to (Priority: P2)

The operator re-captures an order that changed at the vendor. The review reports that a
purchase recorded against this order is for a line the order no longer contains, and
tells them to open the order to look at it. On the order screen they find that line and
delete it.

**Why this priority**: This is the path the existing text already promises — "reported
and never deleted … a purchase the operator can see and cancel". P1 makes the deletion
possible; this puts the control where the operator was already sent. Independently
valuable, but the operator can reach the same purchase via its product without it.

**Independent Test**: Record two purchases carrying the same order number, open the
order screen, delete one line, and confirm the order screen re-derives with one line and
the deleted purchase is gone from its product's history too.

**Acceptance Scenarios**:

1. **Given** an order screen showing several lines, **When** the operator deletes one
   line's purchase and confirms, **Then** the order re-derives without it and the
   remaining lines are untouched.
2. **Given** an order whose every line is deleted, **When** the operator opens that
   order number again, **Then** the page renders the existing "no purchase is recorded
   against this order" state rather than an error.
3. **Given** an order line deleted from the order screen, **When** the operator opens
   that line's product, **Then** the purchase is absent from its purchase history.

---

### Edge Cases

- **A purchase that is already gone.** The operator has the product page open in two
  tabs and deletes the same purchase twice. The second attempt reports that the purchase
  no longer exists rather than failing obscurely, and leaves the rest alone.
- **The last purchase of a product.** The product survives. Deleting a purchase is not a
  way to delete a product, and no product is ever removed as a side effect.
- **The last purchase of an order.** The order stops existing, because an order is only
  ever derived from its purchases. Nothing needs cleaning up and no stored order row is
  left behind.
- **A purchase whose attachment file is shared.** If the underlying file is also
  referenced by something else, deleting the purchase removes the purchase's claim on it
  but not the file.
- **Deleting a received purchase that was the product's most recent.** The product's
  "latest price" and provenance line re-derive from whatever purchases remain, or show
  nothing if none do.
- **Re-capture after deletion.** A deleted line is offered again the next time its order
  is captured, exactly as an excluded line is — there is no row left in which to remember
  the refusal, and this feature does not add one.
- **An outstanding purchase deleted while a receiving scan is mid-flight.** A scan that
  resolves to a purchase that has since been deleted reports it as not found rather than
  erroring.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The operator MUST be able to delete a single purchase from the product
  page's purchase history.
- **FR-002**: Deleting a purchase MUST require an explicit confirmation before anything
  is removed. Cancelling MUST leave the purchase and everything it touches unchanged.
- **FR-003**: The confirmation MUST identify the purchase the operator is about to lose
  — at minimum its vendor, its order date, its quantity and its price — so that the
  right one of two near-identical rows can be told from the wrong one.
- **FR-004**: The confirmation MUST state the two consequences the operator cannot see
  from the row: how many attached files go with it, and that the product's counted
  quantity will not change.
- **FR-005**: Deleting a purchase MUST remove exactly that purchase. The product, its
  identifiers, specifications, photos, tags, categories and product-level attachments
  MUST all survive, as MUST every other purchase of that product.
- **FR-006**: Deleting a purchase MUST delete the attachments that belong to it. The
  stored file behind an attachment MUST be removed only when nothing else references it
  — the same rule that already governs deleting a single attachment.
- **FR-007**: Deleting a purchase MUST NOT change the product's counted quantity, MUST
  NOT change the age of that count, and MUST NOT change a stock flag the operator set by
  hand. Receiving history and current stock are separate claims, and a correction to one
  is not a correction to the other. The operator adjusts the count with the controls
  already on the product page. This is a decision, not an oversight: nothing on a
  purchase records whether its receipt ever moved a count — one received through the
  receive screen did, one captured with an arrival date did not — so subtracting would
  invent a loss for half of them, and would move a number nobody has looked at, which is
  the thing the count's age display exists to prevent.
- **FR-008**: After a successful deletion the operator MUST be told what was removed, in
  the same way other actions on these screens report themselves.
- **FR-009**: The deleted purchase MUST disappear from every view derived from purchases:
  the product's purchase history and latest price, the product's outstanding-order
  banner, the reorder view's on-order figure, the order screen for its order number, and
  the captured-orders list.
- **FR-010**: Deleting the last purchase carrying an order number MUST leave that order
  rendering its existing "nothing captured against this order" state, not an error.
- **FR-011**: An attempt to delete a purchase that no longer exists MUST report that
  plainly and change nothing.
- **FR-012**: Deletion MUST be all-or-nothing: a failure part way through MUST leave the
  purchase and its attachments exactly as they were.
- **FR-013**: A purchase MUST be deletable whether or not it has been received, and
  whether or not it carries an order number, a line number or attachments. There is no
  state a mis-captured purchase can be in that the operator cannot correct.
- **FR-014**: The operator MUST be able to delete a purchase from the order screen as
  well as from the product page. This is the path the operator is already sent down when
  a re-capture reports a purchase the order no longer contains — that report currently
  ends in "open the order to look at them", with nothing there to act with.
- **FR-015**: Deletion MUST behave identically wherever it is offered — the same
  confirmation naming the same purchase and the same consequences, the same rules for
  attachments and the counted quantity. Only where the operator lands afterwards
  differs: the product page returns to the product, the order screen to the order.

### Key Entities *(include if data involved)*

- **Purchase**: One acquisition of one product from one vendor. Carries vendor, vendor
  item id, listing title and address, order date, received date (absent means still
  outstanding), quantity, unit price, the customer's and supplier's order numbers, the
  line number within the supplier's order, and notes. This is the row being deleted.
- **Product**: The catalog entry a purchase is recorded against. Owns the counted
  quantity, the count's age and the manual stock flag — none of which this feature
  touches. Survives the deletion of any or all of its purchases.
- **Purchase attachment**: A file belonging to a purchase — a saved listing, a receipt.
  Belongs to exactly one owner, a product or a purchase, never both. Deleted with its
  purchase.
- **Order**: Not a stored thing. An order is the set of purchases carrying its number,
  worked out afresh each time it is opened, so a deleted purchase simply leaves it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator who has recorded a purchase in error can remove it entirely
  through the application, with no access to the database host, in under one minute from
  opening the product.
- **SC-002**: Deleting one of two duplicate purchases leaves the product's spend history,
  quantity-on-order and reorder figure reading exactly what one purchase would have — a
  100% recovery from the duplicate in issue #129.
- **SC-003**: 100% of purchases are deletable regardless of state: outstanding or
  received, with or without an order number, with or without attachments.
- **SC-004**: No purchase is ever deleted without the operator confirming a prompt that
  names the purchase, so the accidental-deletion rate stays at zero across the
  verification pass.
- **SC-005**: Every one of the roughly twenty manual verification checks currently parked
  on this issue becomes runnable, because a mistake made during one of them can be undone.

## Assumptions

- **Attachments go with the purchase, and the file goes only if nothing else wants it.**
  The alternative — re-parenting a purchase's attachments onto its product — was not
  taken: a saved listing belongs to the purchase that captured it, and moving it to the
  product would file a receipt for a purchase that no longer exists.
- **Deletion is permanent.** No soft delete, no trash, no undo, no audit row. Simplicity
  First: this is a single-user LAN tool, the confirmation is the safeguard, and a
  tombstone table would be scale machinery for one person's typo. The retained-history
  invariant in the constitution governs inventory item shortening, not purchase records.
- **One purchase at a time.** No bulk selection. The observed need is a single duplicate
  row; a multi-select is speculative until a second case appears.
- **The count is corrected by hand when it needs correcting.** The product page already
  carries increment, decrement and set controls for the counted quantity, so FR-007
  leaves the operator with a way to fix a count that a deleted receipt really did move.
- **Only the order-capture path can write a received purchase without moving a count.**
  A purchase received through the receive screen did move a tracked count; one captured
  with an arrival date did not. FR-007 applies the same rule to both rather than trying
  to work out which happened, because nothing records it.
- **Issue #129 lands first or alongside.** This feature is how the operator recovers from
  the duplicate #129 produces; it is not a fix for the duplication itself and does not
  change any capture path.
- **The order screen shows the same control, not a different feature.** Deleting from
  the order screen and deleting from the product page are one action reached two ways
  (FR-015). A bulk "delete this whole order" was not taken — an order is only ever
  derived from its purchases, so there is no order to delete, and the observed need is a
  single wrong line.
- **No new database structure.** A purchase's attachments already cascade from the
  purchase at the storage layer; this feature is a way to ask for the deletion, not a new
  shape of data.
