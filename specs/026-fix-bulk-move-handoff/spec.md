# Feature Specification: Fix the item hand-off into Move and Shorten

**Feature Branch**: `issues/106`

**Created**: 2026-08-24

**Status**: Draft

**Input**: GitHub issue #106 — "Select multiple items on /inventory and click Options → Bulk Move Selected. The resulting page has no items in the move queue; this is a bug." Scope extended during specification to the sibling defects listed under Assumptions.

## Context

Four places in the application let the user pick items and then send them to a working page:

| Entry point | Sends | Receiving page |
|---|---|---|
| Inventory list → Options → Bulk Move Selected | many items | Move |
| Search → Options → Bulk Move Selected | many items | Move |
| Item row → Move | one item | Move |
| Item row → Shorten | one item | Shorten |

**None of the four work.** Each one does carry the chosen items across, and both receiving pages discard what they were handed and open empty. The user's selection is silently lost, and because the page itself opens normally, the failure looks like the page merely forgot.

This was never built rather than broken later: no version of either receiving page has ever looked at what it was handed. The links were added as UI scaffolding alongside a sibling "bulk deactivate" button that at least announces itself as unimplemented.

A fifth defect (issue #107) is included because it is in the same workflow and the same state machine this feature must modify: after a long run of scanning, the user cannot reach validation at all.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Move a group of selected items to one place (Priority: P1)

The user has a batch of items that all need to go to the same place — a shelf being cleared, a bin being consolidated. They filter or browse the inventory list, tick the items, and choose Bulk Move Selected. The Move page opens already holding those items and asks a single question: where are these going? The user scans one location, and every selected item is queued for that destination. They validate and execute once.

**Why this priority**: It is the reported bug, it is the only one of the four hand-offs that saves the user a meaningful amount of work, and it is the entry point most likely to be used on a large selection.

**Independent Test**: Select three items on the inventory list, click Bulk Move Selected, scan one location, and confirm all three appear in the move queue bound for that location and execute successfully. Delivers the entire feature of issue #106 on its own.

**Acceptance Scenarios**:

1. **Given** three active items are selected on the inventory list, **When** the user chooses Bulk Move Selected, **Then** the Move page opens showing those three items as awaiting a destination, and states that a destination is needed for all three.
2. **Given** the Move page has opened with three preselected items, **When** the user scans or enters a valid location, **Then** all three items are queued to that location, each showing its own current location, and the queue count reads three.
3. **Given** all three items are queued to the scanned location, **When** the user supplies a sub-location before finishing, **Then** the sub-location applies to all three.
4. **Given** three preselected items have been queued to a destination, **When** the user then scans a further JA ID and location by hand, **Then** that item joins the same queue and all four execute together.
5. **Given** the same selection is made on the Search page instead of the inventory list, **When** the user chooses Bulk Move Selected, **Then** the behavior is identical to the inventory list in every respect.
6. **Given** the user has queued preselected items, **When** they execute the moves, **Then** every item's location is updated and the result is reflected on the inventory list.

---

### User Story 2 - Finish a long scanning session (Priority: P2)

The user works down a shelf scanning a JA ID and a location for each item, repeating many times in one sitting. When the shelf is done they need to review and commit the batch. Today, after a long run the Validate & Preview and Execute Moves buttons stay disabled and the end-of-scan barcode does not release them, stranding the whole session's work with no way to commit it and no way to recover it.

**Why this priority**: It is a reported defect (issue #107) against the primary documented workflow, and its consequence is total loss of a long manual session. It ranks below P1 only because P1 is the issue this feature was opened for.

**Independent Test**: Scan a long run of JA-ID/location pairs — at least as many as the fourteen in the report — then finish the session, and confirm validation and execution are reachable and the queue holds every pair. Testable with no reference to the preselection work.

**Acceptance Scenarios**:

1. **Given** the user has scanned a long run of JA-ID/location pairs with no sub-locations, **When** they scan the end-of-scan barcode, **Then** the last pair is added to the queue, the queue holds every pair scanned, and Validate & Preview becomes available.
2. **Given** the user has scanned a long run of pairs, **When** they scan the end-of-scan barcode, **Then** no spurious input warning is shown.
3. **Given** validation has succeeded on a long queue, **When** the user executes, **Then** every queued item is moved.
4. **Given** the user's scanner does not emit a trailing newline after a barcode, **When** they scan a full JA-ID/location sequence and finish, **Then** the outcome is the same as for a scanner that does emit one.
5. **Given** the user is midway through entering an item and has supplied a JA ID but not yet a location, **When** they look at the controls, **Then** it is evident why the batch cannot yet be validated.

---

### User Story 3 - Move one item straight from its row (Priority: P3)

The user is looking at an item in a list and wants to move just that one. They use the row's Move action. The Move page opens with that item already present and asks only for its destination.

**Why this priority**: Real but small — it saves one scan, and the user can reach the same outcome today by scanning the item on the Move page. It shares the receiving mechanism with P1, so it is largely free once P1 exists.

**Independent Test**: Use a row's Move action on a single item and confirm the Move page opens holding that item, needing only a destination.

**Acceptance Scenarios**:

1. **Given** the user is viewing an item in the inventory list or search results, **When** they choose Move from that row, **Then** the Move page opens with that one item awaiting a destination.
2. **Given** a single item arrived from a row action, **When** the user scans a location, **Then** that item is queued to it and can be validated and executed.

---

### User Story 4 - Shorten one item straight from its row (Priority: P4)

The user uses a row's Shorten action and the Shorten page opens already identifying that item, rather than requiring it to be entered again.

**Why this priority**: The lowest-value of the four hand-offs — it saves a single field entry on a page that handles one item at a time — but it is the same defect and leaving it is the same trap for the next reader.

**Independent Test**: Use a row's Shorten action and confirm the Shorten page opens identifying that item.

**Acceptance Scenarios**:

1. **Given** the user is viewing an item in a list, **When** they choose Shorten from that row, **Then** the Shorten page opens already identifying that item as the item to shorten.
2. **Given** the Shorten page was opened without any item specified, **When** it loads, **Then** it behaves exactly as it does today.

---

### Edge Cases

- **An item in the hand-off no longer exists or is no longer active.** It must be reported by name and excluded, and the remaining items must still proceed. Silently dropping it would recreate the present bug in miniature.
- **Every item in the hand-off is invalid.** The page must say so plainly rather than presenting an empty page indistinguishable from a normal arrival.
- **The hand-off names the same item twice.** The item appears once; a queue cannot move one item to two places.
- **The hand-off carries no items, or the page is opened directly.** Current behavior is unchanged — this is how the page is reached in normal scanning use and must not regress.
- **The user changes their mind about the destination after arriving.** Clearing the queue must return the page to a usable state rather than a dead one, since the preselected items cannot be re-fetched by scanning a location again.
- **An item is already in the location the user scans.** It is queued like any other; the existing validation reports what it reports today.
- **The user scans a sub-location as the first input after arrival.** A destination location is required first, and the page must say so rather than accepting it.
- **A very large selection is handed off.** The page must remain usable and must not appear to hang while it establishes each item's current location.
- **An item's current location cannot be determined.** It is still queued and its current location is shown as unknown, as it is today.
- **The user arrives with preselected items and then scans the end-of-scan barcode without giving a destination.** Nothing is queued, and the page says why.

## Requirements *(mandatory)*

### Functional Requirements

**The hand-off**

- **FR-001**: All four entry points MUST identify the chosen items to the receiving page using a single, consistent convention, so that the two bulk entry points and the two single-item entry points cannot drift apart again.
- **FR-002**: The Move page MUST read the items it was handed and present them as preselected and awaiting a destination.
- **FR-003**: The Shorten page MUST read the item it was handed and present it as the item to be shortened.
- **FR-004**: Both receiving pages MUST behave exactly as they do today when opened with no items specified.
- **FR-005**: The receiving pages MUST report by name any handed-off item that cannot be used, and MUST proceed with the remainder rather than failing wholesale.
- **FR-006**: A duplicate item in a hand-off MUST be reduced to a single occurrence.

**Assigning the destination**

- **FR-007**: When the Move page opens with preselected items, it MUST state how many items are awaiting a destination and that the next input is the destination for all of them.
- **FR-008**: The first location supplied after arrival MUST be applied as the destination of every preselected item, queueing them all.
- **FR-009**: A sub-location supplied for the preselected group MUST apply to every item in that group.
- **FR-010**: Each queued preselected item MUST show its own current location and sub-location, as scanned items do.
- **FR-011**: After the preselected group is queued, the page MUST return to its normal scanning behavior so further items can be added by hand to the same batch.
- **FR-012**: Input that is not a valid location MUST be rejected while the page is awaiting the group's destination, with an explanation.
- **FR-013**: Preselected items MUST be validated and executed by the same path as scanned items, with no separate execution route.

**The scanning session (issue #107)**

- **FR-014**: The user MUST be able to reach validation and execution after any number of scanned JA-ID/location pairs.
- **FR-015**: The end-of-scan barcode MUST finalize any pair in progress and release validation, on every path through the scanning workflow.
- **FR-016**: The end-of-scan barcode MUST NOT produce a spurious input warning.
- **FR-017**: A scan MUST be handled identically whether or not the scanner emits a trailing newline.
- **FR-018**: When validation is unavailable because an item is half-entered, the page MUST make the reason evident.

**Coverage** *(these exist because the absence of them is why all five defects shipped)*

- **FR-019**: Automated coverage MUST exercise each of the four hand-offs by operating the actual control the user operates, not by navigating directly to the receiving page.
- **FR-020**: Automated coverage of the scanning workflow MUST include a session long enough to represent real use, rather than the two items covered today.
- **FR-021**: Automated coverage MUST exercise scans that do not carry a trailing newline, so that the input path used by such scanners is not left untested.
- **FR-022**: Any test that asserts only that a hand-off link is present MUST either be extended to cover the link's effect or be recognized as insufficient, so that a dead link cannot again be held in place by a passing test.

### Key Entities

- **Preselected item set**: the items handed from a list to a working page, and the count and identity of those the receiving page could not use.
- **Pending move**: a preselected item that is present on the Move page but has no destination yet — the state this feature introduces, between arrival and queueing.
- **Queued move**: an item bound for a destination, with its current and new location and sub-location and its validation status. Unchanged by this feature except in how it comes to exist.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Selecting items and choosing Bulk Move Selected results in every selected item appearing on the Move page, from both the inventory list and search — the defect in issue #106 is gone from both.
- **SC-002**: Moving a group of items to a shared destination takes exactly one destination entry regardless of how many items were selected.
- **SC-003**: All four hand-off entry points carry the user's chosen items through to the receiving page; none discards them.
- **SC-004**: A scanning session of at least fourteen JA-ID/location pairs can be validated and executed, and every pair scanned is present in the batch — the defect in issue #107 is gone.
- **SC-005**: No item selected by the user is ever silently absent from the receiving page: any item that could not be carried over is named on screen.
- **SC-006**: Reaching either receiving page without a selection behaves as it does today, with no change to the existing scanning workflow.
- **SC-007**: Each of the four hand-offs and the long scanning session is covered by an automated test that fails against the current code and passes after the change.
- **SC-008**: The test suite continues to meet the project's existing timing and quality expectations, with no fixed-duration waits introduced.

## Assumptions

- **Destination model**: a bulk move sends every selected item to one destination, chosen once on arrival. Confirmed as a decision during specification. The record contains no prior intent — the receiving half was never built and never designed — so this originates the behavior rather than restoring it. Per-item destinations after arrival, and editing an individual queued row's destination, are deliberately out of scope; the existing scan workflow already covers moving items to differing destinations.
- **Scope extension**: issue #106 names only the inventory list. The Search page's bulk move, both single-item row actions, and issue #107 were added to scope during specification, on the grounds that the first three are the identical defect and the last shares the state machine this work must change.
- **Out of scope**: the row-level Duplicate action uses the same hand-off convention and appears to have the same defect. It was not included and is not addressed here.
- **Out of scope**: bulk deactivate remains unimplemented and openly says so. This feature does not change that.
- **Unresolved at specification time**: the precise cause of issue #107 is not established. A reading of the workflow suggests validation should become reachable after the end-of-scan barcode, so the reported behavior is not yet explained. Reproducing it at the reported scale is part of the work, and the acceptance scenarios above are written against the user's reported experience rather than against a presumed cause.
- Items handed off are identified by their JA ID, the identifier already used throughout the application and already present in the existing links.
- The application remains single-user on a private network; the hand-off is a convenience between the app's own pages and carries no requirement to defend against hostile input.
