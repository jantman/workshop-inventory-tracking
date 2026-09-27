# Feature Specification: Say When the Image Count Was Swept

**Feature Branch**: `robot-army/issue-172-say-on-the-capture-page-when-the-image`

**Created**: 2026-09-27

**Status**: Draft

**Input**: GitHub issue #172, "Say on the capture page when the image count was swept rather
than read" — when the capture reader cannot parse an Amazon listing's own gallery data it
falls back to sweeping the page text for image addresses, and today says so only in the
browser console. Say it on the capture confirmation page, beside the image count it
qualifies, and on the Amazon order review's per-line summary.

## Background

An Amazon listing publishes its gallery as a block of inline data. The capture reader parses
that block to learn exactly which images the listing has. When the block is shaped in a way
the reader does not recognize, it falls back to a **sweep**: it scans the text for anything
that looks like a gallery image address. The sweep usually produces a plausible number, but
it is a guess, not a reading.

Feature 022 (FR-009) made the sweep announce itself, because of issue #95: for an entire
release the parse matched no real listing and the sweep silently answered every capture,
plausibly and wrongly. **A guess that says nothing is indistinguishable from a reading.**

The announcement is a browser-console warning. That is the wrong place for the operator:

- The operator is looking at the capture confirmation page, which exists precisely to say
  what was found before anything is written — and it shows the image count with no caveat.
- Since feature 048 the reader runs inside the browser extension, and Chrome collects an
  extension's console warnings as **Errors** on `chrome://extensions`. An ordinary capture
  therefore raises a red error badge for something benign, which trains the operator to
  ignore the one list where a real extension error would appear.

Observed during issue #133's manual verification: capturing a real Amazon order produced two
such warnings (7 and 6 addresses), one from each line's listing read.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The confirmation page says the image count is a guess (Priority: P1)

The operator captures an Amazon listing whose gallery data the reader cannot parse. On the
capture confirmation page, the image line of "What the listing yielded" reads, in effect,
"7 images — the listing's own gallery data could not be read, so this count is a guess." The
operator can decide, before capturing, whether to trust the count or check the listing.

**Why this priority**: This is the reported defect. The confirmation page is where the
operator is standing when the information matters.

**Independent Test**: Capture the existing unreadable-gallery test listing. The confirmation
page's image summary states that the count is a guess.

**Acceptance Scenarios**:

1. **Given** a listing whose gallery data cannot be parsed but whose sweep finds image
   addresses, **When** the operator captures it, **Then** the confirmation page's image
   summary shows the count followed by a statement that the listing's gallery data could
   not be read and the count is a guess.
2. **Given** a listing whose gallery data parses normally, **When** the operator captures
   it, **Then** the image summary shows the count exactly as today, with no caveat.
3. **Given** the unreadable-gallery listing, **When** the operator captures it, **Then** the
   browser console still carries the existing diagnostic warning.

---

### User Story 2 - The order review says which lines' counts are guesses (Priority: P2)

The operator captures an Amazon order. Each line whose listing was read shows a per-line
summary on the order review, including a picture count. For a line whose listing gallery
was swept, that summary also says the picture count is a guess; other lines are unchanged.

**Why this priority**: The same guess reaches the order review through the same listing
data, and the issue's observed case was an order. It is secondary only because the
single-listing page is the primary place the count is reviewed.

**Independent Test**: Capture an order in which one line's listing has an unreadable gallery.
That line's summary carries the caveat; a line with a readable gallery does not.

**Acceptance Scenarios**:

1. **Given** an order line whose listing gallery was swept, **When** the order review
   renders, **Then** that line's listing summary states that its picture count is a guess.
2. **Given** an order line whose listing gallery was read normally, **When** the order
   review renders, **Then** that line's summary is unchanged.

---

### User Story 3 - An older extension keeps working unchanged (Priority: P3)

The operator has not yet reloaded the browser extension after upgrading the application. Its
captures do not report whether the sweep was used. Captures go through exactly as before and
show no caveat; the operator is not forced to re-install anything.

**Why this priority**: Compatibility guard. No new behavior, but breaking it would block
every capture until the extension is reloaded.

**Independent Test**: Submit a capture payload with no sweep indication. It is accepted and
the summary shows no caveat.

**Acceptance Scenarios**:

1. **Given** a capture payload that carries no sweep indication, **When** it is submitted,
   **Then** it is accepted and read as "not swept".

---

### Edge Cases

- **The sweep ran but found nothing.** No gallery images were guessed, so there is nothing
  to qualify: no caveat, and (as today) no console warning.
- **Swept gallery plus description images or documents.** The image count covers all of
  them; the caveat still appears, because part of the count is a guess.
- **The indication arrives in an unexpected form** (a string, a number). Only an explicit
  "true" means swept; anything else reads as not swept, the same leniency the payload's
  other fields get.
- **A payload that fails to parse for other reasons** is handled exactly as today; this
  feature adds nothing to that path.
- **Non-Amazon vendors** (McMaster-Carr, DigiKey) never sweep, so never show the caveat.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The capture reader MUST record, for each listing it reads, whether its gallery
  images came from the sweep fallback rather than from parsing the listing's gallery data,
  and MUST include that indication in the capture payload when — and only when — the sweep
  supplied at least one gallery image.
- **FR-002**: The application MUST carry the indication through from the payload to the
  capture confirmation page and to each order line's listing summary.
- **FR-003**: A payload that omits the indication, or carries it in any form other than an
  explicit true, MUST be accepted and read as "not swept". The payload version MUST NOT
  change, so an extension that predates this feature needs no reload or re-install.
- **FR-004**: When the indication is set, the confirmation page's image summary MUST show,
  next to the image count, that the listing's own gallery data could not be read and so the
  count is a guess. When it is not set, the image summary MUST read exactly as it does today.
- **FR-005**: When an order line's listing carries the indication, that line's listing
  summary on the order review MUST say its picture count is a guess. Lines without it MUST
  read exactly as they do today.
- **FR-006**: The existing console warning MUST be kept, unchanged in severity. It remains
  the diagnostic channel; this feature adds a channel, it does not replace one.
- **FR-007**: Nothing is written differently because of the indication: the same images are
  captured and stored whether or not the count was swept. The indication is informational
  and is not persisted.

### Key Entities

- **Listing capture**: what the reader extracted from one vendor listing — title, price,
  images, specifications, description — gaining one new fact: whether its gallery image
  count was swept rather than read.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every capture whose gallery was swept, the confirmation page states the
  count is a guess — 100% of the time, on the page the operator is already reading.
- **SC-002**: For every capture whose gallery was read normally, the confirmation page and
  order review show no caveat (zero false alarms).
- **SC-003**: Captures from an extension that predates this feature complete with no
  operator action beyond what they required before.
- **SC-004**: The console warning continues to be emitted for every swept capture.

## Assumptions

- Silencing the red **Errors** badge on `chrome://extensions` is **not** a goal. The issue
  considered lowering the warning's severity and rejected it, because that gives up the
  signal issue #95 exists to preserve. The badge becomes less important once the page says
  the same thing, not quieter.
- The caveat wording follows the issue: "the listing's own gallery data could not be read,
  so this count is a guess." The order review's compact per-line summary may use a shorter
  form carrying the same meaning.
- Only Amazon listings have a sweep fallback today; other vendors' readers never set the
  indication.
- The existing unreadable-gallery test listing already exercises the sweep path and is
  sufficient for the single-listing test; the order case can route one line's listing to
  the same test listing.
