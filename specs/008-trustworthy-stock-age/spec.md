# Feature Specification: Trustworthy Stock Age

**Feature Branch**: `issues/59`

**Created**: 2026-08-09

**Status**: Draft

**Input**: GitHub issue #59 — "Stock information should be trustworthy: age a manual low flag, and don't call a count verified when nobody counted", and the "Reordering and stock" section of `docs/product-functionality-gap.md`.

## Overview

The catalogue already knows that a bare number is not trustworthy. It never shows a count without saying how old it is — "12, counted 8 months ago" — precisely so the operator can decide whether to believe it. That display is the whole trust mechanism, and it has two holes in it.

The first is an absence. A hand-set "low" or "out" flag carries no age at all. A product flagged two years ago and a product flagged this morning look identical on the reorder list, which is the one screen where the operator is deciding what to buy. The manual flag is the mechanism for everything the count cannot express — an untracked consumable, a judgement about a part that is technically in stock but not enough of it — and it is the half of the reorder list with no evidence attached.

The second is worse, because it is not a gap but a false statement. Receiving a purchase adds the received quantity to a tracked count *and* stamps the count as freshly updated, so the screen can read "counted just now" when nobody counted anything — the number went up by what the packing slip claimed, sight unseen. That is the one place where the shipped behaviour actively contradicts the plan, which held that receiving must never touch a count because an inaccurate number is worse than no number. The increment itself is defensible and this feature keeps it. What is not defensible is that an arithmetic adjustment presents itself as a physical verification, because that undermines the age display the rest of the catalogue depends on.

So the feature is one idea in two places: **an assertion about stock displays the age of the evidence behind it, and nothing claims evidence it does not have.**

This is deliberately not a staleness policy. Nothing here decides how old is too old, flags anything as expired, or nags. The existing display renders an age in the words a person would use and lets the operator judge; this extends that treatment to the flag and stops the count's version of it from lying.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The reorder list stops claiming a count nobody made (Priority: P1)

The operator tracks a count of 4 M3 standoffs, counted properly in January. In August a box of 100 arrives and they receive the purchase. The catalogue now says 104 — and says it was counted in January, because it was. Nothing on the screen claims anyone has looked in the drawer since.

**Why this priority**: It is the only part of this feature where the application currently states something untrue, and the untruth attacks the mechanism the whole trust story rests on. Every other improvement here is worth less while the age display can be reset by a delivery.

**Independent Test**: Seed a product with a tracked count and a counted-age of several months, receive an outstanding purchase against it, and verify the count has risen by the received quantity while the displayed counted-age has not moved backwards.

**Acceptance Scenarios**:

1. **Given** a product with a tracked count last counted three months ago, **When** an outstanding purchase for it is received, **Then** the count rises by the received quantity and the screen still reports the count as three months old.
2. **Given** that same product, **When** the operator afterwards counts the drawer and enters the number they found, **Then** the screen reports the count as counted just now.
3. **Given** a product whose count is not tracked, **When** a purchase for it is received, **Then** no count appears and no age is claimed — receiving does not start tracking a count.
4. **Given** a purchase recorded with no quantity, **When** it is received against a product with a tracked count, **Then** the count is unchanged and its age is unchanged.
5. **Given** an already-received purchase, **When** it is received a second time, **Then** neither the count nor its age changes.
6. **Given** a product whose count has never been counted, **When** a purchase for it is received, **Then** the screen does not begin claiming a counted age.
7. **Given** a product whose count has risen by a receipt since it was last counted, **When** the operator views it, **Then** exactly one age is shown for the count, it is the age of the count, and no second date is offered claiming the number changed more recently.

---

### User Story 2 - A hand-set flag shows how old it is (Priority: P2)

The operator opens the reorder list. Two products are flagged low by hand. One says "flagged low yesterday" and one says "flagged low 2 years ago". They order the first and open the second to check whether it is still true.

**Why this priority**: It closes the gap that made the reorder list half-evidenced, and it is what makes the manual flag usable as something other than a permanent shout. It ranks below Story 1 because a missing age misleads less than a false one.

**Independent Test**: Flag one product low, seed another as flagged at an older date, and verify the reorder list and the product page each show the two ages distinctly and in the same words used for a count's age.

**Acceptance Scenarios**:

1. **Given** a product with no manual flag, **When** the operator flags it low, **Then** the flag's age is recorded and shown as just set.
2. **Given** a product flagged low some time ago, **When** the operator views the reorder list, **Then** the row shows how long ago it was flagged.
3. **Given** a product flagged low some time ago, **When** the operator views the product page, **Then** the flag's age is shown next to the flag.
4. **Given** a product flagged low, **When** the operator changes the flag to out, **Then** the age resets to that moment, because "out" is a new assertion and not the old one.
5. **Given** a product flagged low, **When** the operator presses "low" again, **Then** the age resets to that moment, because re-asserting a flag means the operator has just looked.
6. **Given** a product flagged low, **When** the operator clears the flag, **Then** no flag and no flag age are shown.
7. **Given** a product flagged low, **When** an outstanding purchase for it is received and the flag is cleared as a result, **Then** no stale flag age survives to be shown if it is flagged again later.
8. **Given** a product that was already flagged before this feature existed, **When** it is shown, **Then** the flag is shown with its age stated as unknown, and no age is invented for it.

---

### User Story 3 - Adjusting a count at the shelf still counts as counting (Priority: P3)

The operator takes two standoffs out of the drawer and presses the minus button twice on their phone, standing at the shelf. The count drops by two and its age resets, because they were holding the things.

**Why this priority**: It is the boundary that makes Story 1 coherent rather than over-broad. Without it stated, "receiving must not refresh the age" could reasonably be read as "no arithmetic refreshes the age", which would break the quick adjust buttons that are the most common way a count is kept honest.

**Independent Test**: Adjust a tracked count from the product page using the increment and decrement controls and verify the displayed counted-age resets to just now.

**Acceptance Scenarios**:

1. **Given** a product with a tracked count last counted months ago, **When** the operator increments or decrements it from the product page, **Then** the count changes and its age resets to just now.
2. **Given** a product with a tracked count, **When** the operator stops tracking the count, **Then** neither a count nor a counted age is shown.
3. **Given** a product whose count tracking was stopped, **When** the operator starts counting it again with a number, **Then** the age is that moment and carries nothing over from before.

---

### Edge Cases

- **A count changed by a receipt, then never counted again.** The number is not the number anybody counted, and the age refers to the count that was. This is intended and is not further annotated: a count has exactly one age, meaning the last time a person counted, and the screen says so. That the number has moved since is recoverable from the product's purchases, which is where it belongs; a second date shown beside the first would buy one line of display at the cost of a rule every future write path has to get right.
- **A receipt against a product with no count tracked.** Nothing to increment; nothing changes. Receiving never begins tracking a count.
- **A flag set on a product that also has a tracked count.** Both ages are shown, independently, because they are evidence of two different acts.
- **A flagged product with no count at all.** The flag's age is the only evidence the reorder row has, which is exactly the case this feature exists for.
- **A flag that predates this feature.** No age exists and none is fabricated; the display says so.
- **A count that predates this feature and has no recorded age.** Already handled — it reads as never counted — and this feature does not change it.
- **Receiving a purchase whose received quantity was amended at receipt time.** The count moves by what actually arrived, not by what was ordered.
- **Clearing a flag that was never set.** A no-op; nothing to age.

## Requirements *(mandatory)*

### Functional Requirements

**The manual flag's age**

- **FR-001**: The system MUST record when the operator's manual low/out flag was last set.
- **FR-002**: Setting the flag to any value MUST record that moment as the flag's age, including when the value set is the value it already had.
- **FR-003**: Clearing the flag MUST discard its age, so that a later flag never inherits an older one's date.
- **FR-004**: Every screen that shows a manual flag MUST show how long ago it was set, in the same human terms already used for a count's age.
- **FR-005**: A flag whose age was never recorded MUST be shown with its age stated as unknown; the system MUST NOT substitute any other date for it.
- **FR-006**: Anything that clears the flag as a side effect — receiving an outstanding purchase does — MUST discard the flag's age with it.

**What counts as a verified count**

- **FR-007**: Receiving a purchase MUST continue to add the received quantity to a product's tracked count.
- **FR-008**: Receiving a purchase MUST NOT cause the product's count to present itself as more recently counted than it was.
- **FR-009**: Receiving a purchase against a product with no tracked count MUST NOT begin tracking one, and MUST NOT record a counted age.
- **FR-010**: An operator setting or adjusting a count directly — entering a number, or using the increment and decrement controls — MUST record that moment as the count's age.
- **FR-011**: Stopping count tracking MUST discard the counted age, and starting it again MUST record a fresh one.
- **FR-012**: The words used to express an age MUST be the same for a flag and for a count, so that two pieces of evidence on one screen can be compared at a glance.

**Boundaries**

- **FR-013**: The system MUST NOT classify any age as stale, expired or overdue, and MUST NOT withhold, warn about or re-sort an entry on account of its age. The judgement is the operator's.
- **FR-014**: An entry's membership of the reorder list MUST be unchanged by this feature: a flagged product appears however old its flag is.
- **FR-015**: A count MUST carry exactly one age, meaning the last time an operator counted. The system MUST NOT record or display a separate "last changed" date beside it; a change the operator did not make is evidenced by the purchase that made it, not by a second date on the count.

### Key Entities

- **Product**: Gains the date its manual flag was last set, alongside the date its count was last taken. Both are evidence of an operator's act, both are absent when there is nothing to be evidence of, and neither is written by machinery acting on the operator's behalf.
- **Purchase**: Unchanged in what it stores. What changes is what receiving one is allowed to assert about the product it belongs to.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Receiving a purchase never reduces the reported age of a count. Measured by comparing the displayed age immediately before and after a receipt on a product with a tracked count.
- **SC-002**: 100% of manual flags displayed anywhere in the application are accompanied by their age or by an explicit statement that the age is unknown.
- **SC-003**: The only actions that reset a count's age are an operator entering a count and an operator adjusting one at the shelf. Every other path that can change stored stock data leaves the age alone.
- **SC-004**: On the reorder list, an operator can tell which of two flagged products was flagged more recently without opening either one.
- **SC-005**: No product that was previously reachable through the reorder list becomes unreachable, and no product joins or leaves it as a result of this feature.
- **SC-006**: Products carrying flags set before this feature shipped continue to display and behave correctly, with no invented dates.
- **SC-007**: A stock assertion shown to the operator carries at most one date: a count shows when it was counted, a flag shows when it was set. No screen presents two competing ages for the same assertion.

## Assumptions

- The age of a flag is rendered in the same relative, human phrasing already used for a count's age ("yesterday", "3 months ago") rather than an absolute date. Absolute timestamps were rejected for counts for the same reason they are rejected here: the operator's question is "should I trust this?", not "what was the date?".
- Existing flagged products are not backfilled with a date derived from any other field. A record's last-modified date is not evidence that anybody looked at a shelf, and inventing one would repeat in the flag the exact error this feature removes from the count.
- Receiving continues to clear the manual flag, as it does today. That behaviour is not in question here; only the age travelling with it.
- Receiving continues to increment a tracked count, as it does today. Issue #59 offered stopping that as well — the original plan's position — and it was not taken: a count that ignores a delivery is knowingly wrong until the operator counts, which is a worse trade than a correct number whose age is honest about who last verified it.
- No new screen is introduced. The two ages appear on the screens that already show a count and a flag: the product page and the reorder list.
- The reorder list's ordering is unchanged. Sorting by evidence age is a plausible follow-on and is not part of this feature.
- The counted age remains absent — rendered as never counted — for a tracked count that has never been set by an operator, which is the behaviour today.
