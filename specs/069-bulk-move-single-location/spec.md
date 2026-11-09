# Feature Specification: Bulk Move to a Single Location by Scanning

**Feature Branch**: `robot-army/issue-223-bulk-move-to-single-location`

**Created**: 2026-11-08

**Status**: Draft

**Input**: User description: "Bulk Move to Single Location. User Story: I have 10 labeled product bags and they're all going to the same location. Right now, to move them (or set their initial location) I need to scan a product, and then its location (and optional sub-location) and repeat 9 times even though they're all going to the same place. As a user, I would like a method to move multiple products to the same location. (GitHub issue #223)"

## Background

The Move Items and Move Products pages (and their handheld counterpart) share one
scan-driven flow: scan an ID, scan a location, optionally a sub-location, repeat. Each
subject needs its own location scan.

Two things already exist that this feature builds on:

- A group handed over from a list page's *Bulk Move Selected* (specs 026 / 057) waits for
  one location that is then applied to every subject in the group, and a sub-location
  scanned straight afterwards applies to the whole group too. That only works when the
  owner starts from a list page and ticks checkboxes — not when they are standing at a
  shelf with a scanner and ten labelled bags.
- On the scan path, scanning a second ID while the page waits for the first one's location
  currently *abandons* the first ID with a warning ("No location was scanned for X, so it
  was not queued"). That rule was introduced by 026 to stop the page wedging (#107).

This feature replaces the abandon rule with accumulation: IDs scanned back to back form a
group that waits for a destination, and the next location (and optional sub-location) is
applied to all of them. One-at-a-time scanning (ID, location, ID, location…) is unchanged,
because a single ID followed by a location is simply a group of one.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scan many, then one location (Priority: P1)

The owner has ten labelled product bags going to the same shelf. On the Move Products page
they scan all ten labels one after another, then scan the shelf's location label once, then
optionally a sub-location. All ten join the move queue with that destination. They validate
and execute as usual.

**Why this priority**: This is the issue. It turns 20–30 scans into 11–12.

**Independent Test**: Seed three products in different places. On the Move Products page
scan the three codes, then `Shelf 2`, then `Bin 4`, then `>>DONE<<`. The queue holds three
rows, each showing its own current location and the new `Shelf 2` / `Bin 4`; validate and
execute, and all three products are at `Shelf 2` / `Bin 4`.

**Acceptance Scenarios**:

1. **Given** the page is waiting for an ID, **When** the owner scans product A then product
   B, **Then** both are shown as awaiting a destination, the page says two products are
   waiting, and nothing has been added to the move queue yet.
2. **Given** products A, B and C are awaiting a destination, **When** the owner scans a
   location, **Then** all three are added to the queue with that location and no
   sub-location, each showing its own current location and sub-location.
3. **Given** a group has just been queued for a location, **When** the owner scans a
   sub-location, **Then** it is applied to every product in that group, and to no
   product queued earlier.
4. **Given** a group has just been queued for a location, **When** the owner scans another
   product code instead, **Then** the group keeps no sub-location and the new product
   starts a new group.
5. **Given** the same flow on the Move Items page with JA IDs and an `M`/`T`/`Other`
   location, **Then** it behaves the same way.

---

### User Story 2 - One-at-a-time scanning still works (Priority: P1)

The owner who scans ID, location, sub-location, ID, location… sees exactly the behaviour
they see today: each scanned ID is queued with the location scanned after it.

**Why this priority**: The existing flow is the one used most. Breaking it to add bulk
scanning would be a regression.

**Independent Test**: Run an existing alternating session (ID, location, sub-location, ID,
location, `>>DONE<<`) and confirm the queue is identical to today's.

**Acceptance Scenarios**:

1. **Given** the page is waiting for an ID, **When** the owner scans ID A, location L1, ID B,
   location L2, **Then** A is queued for L1 and B for L2.
2. **Given** ID A and location L1 have been scanned, **When** the owner scans sub-location
   S, **Then** A is queued for L1 / S.

---

### User Story 3 - Mistakes in a group can be corrected before the location (Priority: P2)

While building a group the owner double-scans a bag, scans a bag that is already queued,
or decides a bag doesn't belong. The page refuses duplicates with a message, and the owner
can remove a subject from the waiting group before scanning the location.

**Why this priority**: A wrong scan inside a group of ten would otherwise send the wrong
bag to the shelf, and the only recovery today would be Clear All.

**Independent Test**: Scan A, A, B; the second A is refused with a message and two
subjects are waiting. Remove B from the waiting group; scan a location; only A is queued.

**Acceptance Scenarios**:

1. **Given** A is awaiting a destination, **When** A is scanned again, **Then** it is
   refused with a message saying it is already waiting, and the group is unchanged.
2. **Given** A is already in the move queue, **When** A is scanned, **Then** it is refused
   with the existing "already in the move queue" message.
3. **Given** A and B are awaiting a destination, **When** the owner removes B from the
   waiting group, **Then** only A is waiting; and if the last waiting subject is removed,
   the page goes back to waiting for an ID.
4. **Given** subjects are awaiting a destination, **When** the owner scans `>>DONE<<`,
   **Then** nothing in the group is queued, the page says how many still need a
   destination, and anything already in the queue can still be validated.
5. **Given** subjects are awaiting a destination, **When** the owner presses Clear All,
   **Then** the group is discarded along with the queue.

---

### User Story 4 - Same on the handheld (Priority: P3)

The handheld Move screen uses the same controller, so the same accumulation works there,
with the waiting group visible on the small screen.

**Why this priority**: The handheld is where bags are most likely to be scanned in bulk,
but it inherits the behaviour from the shared controller; the only work is showing the
waiting group in its layout.

**Independent Test**: On the handheld Move screen, scan two product codes then a location;
both are queued for that location.

**Acceptance Scenarios**:

1. **Given** the handheld Move screen, **When** two codes and then a location are scanned,
   **Then** both are queued for that location and the screen showed the waiting count
   before the location was scanned.

### Edge Cases

- **Group handed over from a list page, then more IDs scanned.** While a handed-over group is
  waiting for its destination, an ID scan is still refused as today (026 FR-012): the
  handed-over group is a deliberate selection, and adding to it by scanning is not asked for.
- **A subject scanned into a group whose lookup fails or is unknown.** It joins the group
  and the queue like any other ("Unknown" current location) and is caught at validation, as
  today.
- **The location scan arrives before every group member's current location has been
  looked up.** The group is queued at once; a row whose lookup is still outstanding shows
  "Unknown" until it returns and is then corrected, so no row is left showing "Unknown" for
  a subject whose location is known.
- **Products' free-text locations.** On the Move Products page any input that is not a
  product code or a JA ID, while a group is waiting, is the destination. This is the rule
  the page already applies after a single code.
- **A foreign ID (a JA ID on the products page, or vice versa) while a group waits.** Refused
  with the existing message; the group is unchanged.
- **Validate & Preview while a group waits.** Unavailable, with the hint saying how many
  subjects still need a destination, as for a half-entered move today.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: On the scan-driven move pages (items, products, handheld), scanning an ID while
  one or more scanned IDs are waiting for a location MUST add it to the waiting group
  rather than abandoning the earlier ones.
- **FR-002**: The page MUST show which subjects are waiting for a destination and how many,
  before the location is scanned.
- **FR-003**: The first location scanned while a scanned group is waiting MUST be applied as
  the destination of every subject in the group, queueing them all as ordinary moves.
- **FR-004**: A sub-location scanned immediately after a group is queued MUST apply to every
  subject in that group and to nothing queued before it.
- **FR-005**: An ID scanned immediately after a group is queued MUST start a new group and
  leave the previous group without a sub-location.
- **FR-006**: A single ID followed by a location (and optional sub-location) MUST produce the
  same queue as today.
- **FR-007**: Scanning an ID that is already waiting, already queued, or on its way to the
  queue MUST be refused with a message, leaving the group unchanged.
- **FR-008**: The owner MUST be able to remove an individual subject from the waiting group
  before its location is scanned. Removing the last one MUST return the page to waiting
  for an ID.
- **FR-009**: `>>DONE<<` while a scanned group is waiting MUST NOT queue the group, MUST say
  how many subjects still need a destination, and MUST leave anything already queued
  available for validation.
- **FR-010**: Clear All MUST discard a waiting group.
- **FR-011**: While a group is waiting, Validate & Preview MUST be unavailable and the hint
  MUST say how many subjects still need a destination.
- **FR-012**: Each queued subject MUST show its own current location and sub-location, as
  today.
- **FR-013**: Validation, execution and the server-side batch-move endpoints MUST NOT change:
  a bulk-scanned group becomes the same queued moves that one-at-a-time scanning produces.
- **FR-014**: The on-page instructions MUST tell the owner that several IDs can be scanned
  before one location.
- **FR-015**: A group handed over from a list page MUST behave as it does today.

### Key Entities

- **Waiting group**: the subjects scanned since the last location, each with its ID, label
  and current location / sub-location once looked up. Exists only in the page; never saved.
- **Queued move**: unchanged — one subject, its current location / sub-location and its new
  location / sub-location.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Moving N subjects to one location and sub-location takes N + 2 scans (plus
  `>>DONE<<`), down from 3N.
- **SC-002**: A ten-product scan session (ten codes, one location, one sub-location) queues
  exactly ten moves, each with the shared destination, and executes them in one batch.
- **SC-003**: Every existing move-page e2e test that does not assert the abandon rule passes
  unchanged.
- **SC-004**: No scanned subject is ever silently dropped: every scanned ID ends up queued,
  still visibly waiting, refused with a message, or removed by the owner.

## Assumptions

- Accumulation replaces the 026 "abandon on a second ID" rule rather than being a separate
  mode or toggle. The abandon rule existed to keep the page from wedging, and accumulation
  keeps that guarantee: an ID scan always moves the machine forward. A forgotten location
  scan now shows up as a visibly waiting subject that will share the next location, instead
  of a warning and a dropped subject. Tests that asserted the abandon rule are updated to
  assert accumulation.
- The waiting group lives only in the page, as the queue does today. Leaving the page loses
  it, as it loses the queue.
- No server-side change is needed: the existing batch-move endpoints already accept many
  moves sharing one destination.
- Applies to both the item and product move pages and the handheld Move screen, since they
  share one controller.
