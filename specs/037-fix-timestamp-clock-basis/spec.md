# Feature Specification: One Clock for Recorded Timestamps

**Feature Branch**: `speckit/037-fix-timestamp-clock-basis`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "issue #134 on this repo — timestamps on one table use two different clocks: func.now() (UTC) and datetime.now() (local)"

## User Scenarios & Testing *(mandatory)*

The operator is the only user. There is no second person and no second machine; every scenario
below is one person, or one program reading the app's JSON, trying to answer "when did this
happen?" from data the app recorded for itself.

The distinction that runs through all of it: some times are **recorded by the app** as a side
effect of an action (when a row was created, when a count was taken, when a record last
changed), and some are **stated by the operator** as a calendar day (the day an order was
placed, the day a box arrived). These are different kinds of value and this feature treats
them differently.

### User Story 1 - Two recorded times on one record agree (Priority: P1)

The operator creates a product and counts it a few minutes later. Reading that product back —
through the JSON API, or through any future screen — every time the app recorded for that
product sits within minutes of every other, because they were minutes apart in reality.

Today they do not. A product created and counted within a quarter of an hour reports a
creation time of `19:03:45` and a count time of `15:18:40` — four hours apart, in the wrong
direction, because the two values were taken from two different clocks. Nothing in the app
compares them yet, so nothing looks broken; the data is simply wrong where it sits.

**Why this priority**: This is the whole issue. It is stored data that does not mean what it
says, it cannot be reconstructed for rows already written, and it fails silently. Everything
else in this feature is protecting behavior that already works from the fix itself.

**Independent Test**: Create a product and set a count on it within the same minute. Read
every recorded timestamp on that product back. Confirm they fall within a minute of each
other and that none is in the future.

**Acceptance Scenarios**:

1. **Given** a product created and then counted within the same minute, **When** its recorded
   times are read back, **Then** the creation time and the count time differ by less than a
   minute.
2. **Given** two records created a known interval apart, **When** they are ordered by any
   recorded timestamp, **Then** the ordering matches the order the events actually happened,
   whichever timestamp is chosen.
3. **Given** any record the app has just written, **When** its recorded times are compared
   against the current time, **Then** none of them is in the future.
4. **Given** the same action performed twice — once where the app writes the time and once
   where the database writes it — **Then** both produce a value on the same basis.

---

### User Story 2 - Stock ages keep telling the truth (Priority: P2)

The operator opens a product page and reads "counted 3 hours ago" and "flagged low 2 days
ago". Those lines are right today, because the two halves of the subtraction happen to share a
basis. Changing what is stored without changing what it is compared against would break them —
and break them quietly, because a count that appears to be in the future renders as "just now"
rather than as an error.

**Why this priority**: These are the only timestamps the operator actually sees. They work now.
The fix must not be the thing that breaks them, and "just now" on every product is exactly what
a half-done fix looks like.

**Independent Test**: Set a count at a known moment, then read the product page at a known
later moment, and confirm the rendered age matches the elapsed interval rather than reading
"just now".

**Acceptance Scenarios**:

1. **Given** a count taken a known number of hours ago, **When** the product page is rendered,
   **Then** the age line reports that number of hours, not "just now".
2. **Given** a count taken 51 minutes ago and a purchase received since, **When** the product
   page is rendered, **Then** the count age still reports the count, not the receipt — the
   behavior feature 008 established is unchanged.
3. **Given** a product with a count but no recorded count time, **When** the product page is
   rendered, **Then** the age reads as unknown, as it does today.

---

### User Story 3 - Dates the operator states keep the operator's day (Priority: P3)

The operator captures an order at nine in the evening. The order records the day it is, on the
operator's calendar — not tomorrow, which is what the same instant is called elsewhere in the
world. The same holds for the day a shipment is marked received.

**Why this priority**: These dates are displayed, are compared against packing slips, and are
the operator's own statement about a day rather than the app's record of an instant. Sweeping
them along with the recorded timestamps would shift evening entries onto the following day —
a new, visible bug introduced by a fix for an invisible one.

**Independent Test**: Capture an order late in the local evening with no order date supplied
and confirm the stored order date is the local calendar day, then read it back on the order
listing and confirm the same day is displayed.

**Acceptance Scenarios**:

1. **Given** an order captured in the local evening with no order date typed, **When** the
   order date is displayed, **Then** it shows the operator's current calendar day.
2. **Given** a shipment marked received in the local evening with no date typed, **When** the
   received date is displayed, **Then** it shows the operator's current calendar day.
3. **Given** an order date typed by the operator, **When** it is stored and read back,
   **Then** it is the day that was typed, unshifted.

---

### Edge Cases

- **Rows written before the fix.** Existing rows are already on mixed bases and the offset in
  force when each was written was never recorded, so it cannot be reversed. Those rows stay as
  they are. The system must read them without erroring, and an age computed from one that now
  appears to be in the future must render the way an unknown or zero age renders today rather
  than as a negative interval or a crash.
- **A daylight-saving boundary.** Because the offset at write time is not stored, a row written
  near a transition cannot even be corrected in principle. This is a further reason not to
  attempt a migration, not a case to handle.
- **The database server's timezone changes.** What the app records must not depend on how the
  database server is configured. Reconfiguring the server's timezone must not change the basis
  of a newly written row.
- **Import and export.** Records exported and re-imported carry their times as text. A time
  written out and read back in must denote the same instant, and must not be re-interpreted on
  a different basis on the way in.
- **A timestamp the operator supplies for a recorded field.** Where an operator-supplied value
  fills a field the app would otherwise record itself, it must be interpreted on the operator's
  local calendar and stored on the common basis, so it remains comparable to the values the app
  writes.
- **A count and a flag set in the same action.** Both times must land on the same basis, so the
  two age lines on the product page cannot disagree about which evidence is fresher.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every timestamp the system records for itself — record creation, last change,
  count time, stock-flag time, photo and attachment times — MUST be recorded on a single,
  consistent basis across every table and every code path.
- **FR-002**: The basis of a recorded timestamp MUST NOT depend on which component wrote it.
  The same event recorded through the application and through a database-supplied default MUST
  produce a value on the same basis.
- **FR-003**: The basis of a recorded timestamp MUST NOT depend on the database server's
  timezone configuration or on the machine's local timezone setting.
- **FR-004**: Two timestamps recorded on the same record for events less than a minute apart
  MUST differ by less than a minute.
- **FR-005**: Ordering or comparing records by any recorded timestamp MUST agree with the order
  the events actually occurred, regardless of which recorded timestamp is used.
- **FR-006**: A recorded timestamp MUST NOT be in the future relative to the moment it is read.
- **FR-007**: Elapsed-time displays (count age, stock-flag age) MUST compute the interval
  against the same basis the timestamp was recorded on, and MUST report the same values after
  this change as before it for any record written after this change.
- **FR-008**: A date the operator states, or that is defaulted to "today" on the operator's
  behalf — order date, received date, item purchase date — MUST denote the operator's local
  calendar day and MUST NOT be shifted by this change.
- **FR-009**: Records written before this change MUST remain readable and MUST NOT cause errors,
  blank screens, or negative elapsed times. They are not migrated.
- **FR-010**: The names, presence and textual shape of timestamp fields in the JSON API MUST NOT
  change. Only the values become mutually consistent.
- **FR-011**: A timestamp exported and later re-imported MUST denote the same instant it did
  before the round trip.
- **FR-012**: The system MUST have exactly one place that answers "what time is it, for the
  purpose of recording an event", so a new recorded timestamp cannot be introduced on the wrong
  basis by accident.

### Key Entities *(include if data involved)*

- **Recorded event time**: A moment the system observed and wrote down without being told —
  when a record was created, last changed, counted, or flagged; when a photo or attachment was
  stored. Its only purpose is comparison: against other recorded times, and against now. It has
  no meaning to the operator as a wall-clock reading.
- **Stated calendar date**: A day the operator asserts, or accepts as "today" — the day an
  order was placed, the day a shipment arrived, the day an item was purchased. It is displayed
  as a day, compared against paper, and belongs to the operator's local calendar.
- **Elapsed age**: The interval between a recorded event time and now, rendered as a phrase
  ("3 hours ago", "yesterday", "8 months ago"). It is correct only when both ends of the
  subtraction share a basis.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a product created and counted within five minutes, every recorded time read
  back falls within five minutes of every other. Today the gap is four hours.
- **SC-002**: Sorting the same set of records by each of its recorded timestamps in turn
  produces the same order every time.
- **SC-003**: Zero recorded timestamps read back from newly written records are in the future,
  measured across every table that records one.
- **SC-004**: Every elapsed-age phrase shown on the product page reports the same value after
  the change as it did before it, for records written after the change — including the case
  where a purchase has been received since the count was taken.
- **SC-005**: An order or receipt entered at any hour of the local day records the operator's
  calendar day for that entry, verified at both ends of the day.
- **SC-006**: Changing the database server's configured timezone changes nothing about what a
  newly written record reports.
- **SC-007**: Records written before the change continue to load on every screen and endpoint
  that reads them, with no error and no negative elapsed time.

## Assumptions

- **The common basis is UTC.** This is the conventional choice, it is the basis the
  database-supplied defaults already produce in this deployment, and it makes the columns
  comparable without a policy. Displays that need a wall-clock reading can localize; none does
  today.
- **Existing rows are left alone.** The offset in force when each was written was not recorded,
  and a daylight-saving boundary makes it ambiguous, so no correction is possible in principle
  for the general case. The error is bounded and affects only rows written before the fix.
- **The JSON API keeps emitting times in the shape it emits them in now.** The single consumer
  is this application; changing the text format to carry an explicit offset would be a
  consumer-visible change made for no observed need.
- **No new absolute timestamp is put on screen.** No screen renders a recorded event time today.
  Making one visible is a separate decision with its own display and localization questions.
- **"The operator's local calendar" means the timezone the application host is configured for.**
  There is one host, one operator, and no timezone setting to configure; introducing one would
  be scale machinery for a problem that does not exist.
- **This is a data-integrity fix, not a feature.** It falls under the constitution's carve-out
  — stored data that does not mean what it says — rather than under speculative hardening, and
  should not grow a configuration surface, an abstraction layer, or a clock-injection framework
  beyond the one place FR-012 asks for.

## Out of Scope

- Migrating or correcting timestamps on rows written before this change.
- Displaying any absolute recorded timestamp in the user interface.
- Any operator-facing timezone preference, setting, or picker.
- Changing the textual format of timestamps in the JSON API or in exports.
- Changing which action updates which timestamp. In particular, receiving a purchase still
  leaves the count age alone (feature 008, FR-008).
