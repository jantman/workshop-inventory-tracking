# Feature Specification: Fix Add & Continue With Quantity Greater Than One

**Feature Branch**: `010-fix-bulk-add-continue`

**Created**: 2026-08-10

**Status**: Draft

**Input**: GitHub issue #52 — "11. Error on Add & Continue with quantity": *Browser throws an error when using Add & Continue button if Quantity is greater than 1.*

## Problem Statement

On the Add Item form, the **Quantity to Create** field lets the user create several identical
items in one submission, each receiving its own sequential JA ID. The form offers two submit
actions: **Add** (create, then go to the inventory list) and **Add & Continue** (create, then
return to an empty Add form so the next item can be entered without navigating).

The two features do not work together. With **Quantity to Create** set to 1, **Add & Continue**
works. With **Quantity to Create** set to 2 or more, pressing **Add & Continue** reports an error
to the user, and the number of items actually recorded in the inventory does not reliably match
the quantity requested — the same submission is sent to the server twice, and the two attempts
race each other. Depending on which attempt lands first, the user sees either an error message
alongside a success dialog, or no error at all while twice the requested number of items is
created. Pressing **Add** with the same quantity does not produce the error.

The consequences, in order of severity:

1. **Inventory can silently gain items the user never asked for.** A request for 3 items can
   record 6. The user has no indication this happened, and physical stock will not match.
2. **An error is shown for an operation that partly succeeded.** The user cannot tell from the
   screen whether the items were created, so the safe response is to go check the inventory list
   by hand.
3. **The "continue" part of Add & Continue never happens.** Even when creation succeeds, the form
   is not reset for the next entry, so the button does not do what its label says.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bulk create without spurious errors or extra items (Priority: P1)

The user is entering a box of identical stock — say six lengths of the same steel bar. They fill
in the Add Item form once, set **Quantity to Create** to 6, and press **Add & Continue**. Six
items are created, each with its own JA ID, and no error is shown.

**Why this priority**: This is the reported defect, and it is the one that can corrupt the
inventory. Fixing it alone restores a trustworthy result even if nothing else changes.

**Independent Test**: Fill the Add form, set quantity above 1, press **Add & Continue**, and check
that the inventory contains exactly the requested number of new items and that no error message
was displayed. Fully testable on its own; delivers a correct inventory.

**Acceptance Scenarios**:

1. **Given** a valid, complete Add Item form with **Quantity to Create** set to 6, **When** the
   user presses **Add & Continue**, **Then** exactly 6 new items are recorded, each with a
   distinct sequential JA ID, and no error message is shown.
2. **Given** the same submission, **When** the user afterwards views the inventory list, **Then**
   it contains exactly 6 new items — not 12, and not a partial subset.
3. **Given** a valid form with **Quantity to Create** set to 6, **When** the user presses
   **Add & Continue**, **Then** the server receives exactly one creation request for that
   submission.
4. **Given** a valid form with **Quantity to Create** set to 1, **When** the user presses
   **Add & Continue**, **Then** the existing single-item behavior is unchanged: the item is
   created and the user is returned to an empty Add form.
5. **Given** a valid form with **Quantity to Create** set to 6, **When** the user presses **Add**
   (not **Add & Continue**), **Then** the existing bulk behavior is unchanged: 6 items are
   created and the bulk label-printing dialog is offered.

---

### User Story 2 - Continue into the next entry after a bulk create (Priority: P2)

Having created six identical bars, the user wants to enter the next batch straight away. After the
bulk creation completes and the label-printing dialog is dismissed, the Add form is ready for the
next entry, exactly as it would be after a single-item **Add & Continue**.

**Why this priority**: This is what the button's label promises. It is a usability gap rather than
a correctness one, so it ranks below Story 1 — but without it, **Add & Continue** and **Add**
behave identically for quantity above 1, which is its own kind of wrong.

**Independent Test**: Complete a bulk **Add & Continue**, dismiss the label dialog, and confirm the
form is in the same ready-for-next-entry state that a single-item **Add & Continue** leaves behind.

**Acceptance Scenarios**:

1. **Given** a bulk **Add & Continue** that created its items successfully, **When** the user
   dismisses the label-printing dialog, **Then** the Add form is presented ready for a new entry
   with the per-item fields cleared.
2. **Given** the form after a bulk **Add & Continue**, **When** the user presses **Carry Forward**,
   **Then** the values from the batch just created are restored, matching the behavior after a
   single-item **Add & Continue**.
3. **Given** a bulk **Add** (not **Add & Continue**), **When** the creation succeeds, **Then** the
   user is **not** returned to a cleared Add form — the two buttons remain distinguishable.

---

### User Story 3 - Honest reporting when a bulk create does not fully succeed (Priority: P3)

If some of the requested items genuinely cannot be created, the user is told how many were created
and how many were not, and the message is not confusable with the spurious error this feature
removes.

**Why this priority**: Partial-failure reporting already exists; this story only requires that it
survives the fix and is not masked. It has no value without Story 1 being correct first.

**Independent Test**: Force a bulk creation to fail partway and confirm the reported counts match
what was actually recorded.

**Acceptance Scenarios**:

1. **Given** a bulk creation in which some items cannot be created, **When** the submission
   completes, **Then** the user is told how many items were created and that the rest failed, and
   the count stated matches the inventory.
2. **Given** a bulk creation in which no items can be created, **When** the submission completes,
   **Then** the user is told the creation failed and the inventory is unchanged.

---

### Edge Cases

- **Repeated presses.** If the user presses **Add & Continue** twice in quick succession, or
  presses **Add** and **Add & Continue** in quick succession, only one batch is created. The
  submit controls are unavailable while a submission is in flight and are restored when it
  settles, whether it succeeded or failed.
- **Keyboard submission.** Pressing Enter to submit the form produces the same single, correct
  submission as clicking a button, for both quantity 1 and quantity above 1.
- **Invalid form with quantity above 1.** If a required field is missing, pressing
  **Add & Continue** reports the validation problem and creates nothing — no partial batch, no
  request sent.
- **Quantity at the boundaries.** Quantity 1 takes the single-item path. Quantity 2 takes the bulk
  path. Quantity at the maximum allowed (100) behaves as any other bulk value. A quantity outside
  the permitted range is rejected with a message and creates nothing.
- **Server failure mid-batch.** If the request fails outright (server error, connection dropped),
  the submit controls are restored and the user is told the creation did not complete, so they can
  check the list rather than blindly retrying.
- **Bulk creation with photos attached.** Photos attached on the Add form behave the same for a
  bulk **Add & Continue** as for a bulk **Add**.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Pressing **Add & Continue** on the Add Item form MUST result in exactly one creation
  request being sent to the server, for every value of **Quantity to Create**.
- **FR-002**: A bulk creation initiated with **Add & Continue** MUST create exactly the requested
  number of items — never more.
- **FR-003**: A bulk creation initiated with **Add & Continue** that succeeds MUST NOT display any
  error message.
- **FR-004**: Each item created in a bulk submission MUST receive a distinct JA ID, and no JA ID
  MUST collide with an item that already exists.
- **FR-005**: While a creation request is in flight, both submit controls MUST be unavailable, and
  they MUST be restored to their normal labels and enabled state when the request settles —
  success, failure, or error.
- **FR-006**: After a successful bulk creation initiated with **Add & Continue**, once the
  label-printing dialog is dismissed, the system MUST present the Add form ready for the next
  entry, with per-item fields cleared, matching the state left by a single-item
  **Add & Continue**.
- **FR-007**: After a successful bulk creation initiated with **Add** (not **Add & Continue**), the
  system MUST NOT clear the form for a further entry — the two controls MUST remain behaviorally
  distinct.
- **FR-008**: The values of the just-submitted batch MUST remain available to **Carry Forward**
  after a bulk **Add & Continue**, as they are after a single-item **Add & Continue**.
- **FR-009**: When a bulk creation partly succeeds, the message shown MUST state how many items
  were created, and that number MUST match what was recorded.
- **FR-010**: When a submission fails validation before anything is created, the system MUST report
  the validation problem and MUST NOT create any items.
- **FR-011**: Existing behavior for **Add** with quantity 1, **Add & Continue** with quantity 1,
  and **Add** with quantity above 1 MUST be unchanged by this work.
- **FR-012**: Automated end-to-end coverage MUST exercise **Add & Continue** with a quantity above
  1 through the Add Item form, asserting both the count of items created and the absence of an
  error — the combination has no such coverage today, which is why the defect reached the user.

### Key Entities

- **Inventory item**: an individual piece of stock identified by its JA ID. A bulk submission
  creates several of these from one set of form values, differing only in JA ID.
- **Add submission**: one user action on the Add Item form, carrying the form values, a quantity,
  and which of the two submit controls was used. One user action must correspond to exactly one
  submission.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every quantity from 1 to 10, pressing **Add & Continue** creates exactly that
  number of items — 100% agreement between requested and recorded counts, with no over-creation.
- **SC-002**: A successful bulk **Add & Continue** displays zero error messages.
- **SC-003**: A user entering three consecutive batches of identical stock can do so without
  leaving the Add form and without manually verifying the inventory list between batches.
- **SC-004**: Pressing a submit control repeatedly during a submission produces no more items than
  a single press.
- **SC-005**: The automated test suite catches the defect if it is reintroduced — verified by
  confirming the new coverage fails against today's behavior and passes after the fix.
- **SC-006**: All existing automated checks continue to pass, and total end-to-end suite runtime
  grows by no more than the cost of the one new scenario (under 30 seconds).

## Assumptions

- The reported "error" is the user-visible failure message produced by the duplicated submission;
  no separate, unrelated fault is being reported in issue #52. The issue text gives no error
  string, so this specification treats any error surfaced by a successful bulk **Add & Continue**
  as in scope.
- The existing bulk label-printing dialog remains part of the bulk flow; this work changes when the
  form is reset relative to that dialog, not whether the dialog appears.
- The permitted quantity range (1–100) is unchanged.
- The **Carry Forward** feature and its persistence across page loads are unchanged in behavior;
  they need only continue to work after a bulk **Add & Continue**.
- No change to the item data model, the database schema, or the JA-ID format is required.
- The standalone API client's bulk-creation path is out of scope: it does not use the form's submit
  controls and does not exhibit the defect.
- Per the project constitution, the fix is sized to the defect — no new submission framework,
  queueing, or request-deduplication infrastructure beyond what removing the duplicate submission
  requires.

## Out of Scope

- Redesigning the Add Item form or the bulk-creation user experience.
- Changing how JA IDs are allocated for bulk creation, beyond what is needed to guarantee
  FR-004 for a single submission.
- Concurrency between two different browser sessions submitting at the same time. This is a
  single-user application on a LAN; the duplication addressed here originates from one user action
  in one page.
- The bulk *duplication* feature on the item view (a separate path with its own quantity field).
