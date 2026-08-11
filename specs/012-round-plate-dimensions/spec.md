# Feature Specification: Round Plate Dimensions

**Feature Branch**: `issues/85`

**Created**: 2026-08-10

**Status**: Draft

**Input**: GitHub issue #85 — "Round Plate Dimensions": *"For metal stock / materials, if the Type is `Plate` and the Shape is `Round`, only Diameter and Thickness dimensions should be required. This needs updates in at least the front-end UI as well as database schema and backend models."*

## Overview

A round plate is a disc. Two numbers describe it completely: how far across it is, and how thick it is. The Add Item form asks for three, because a plate's required dimensions are decided by its type without consulting its shape — so a round plate inherits the rectangular plate's Length, Width, Thickness. Length has no meaning for a disc, and the form will not accept the item without it.

The operator's only way past that is to invent a number. Whatever they type lands in the inventory as though it were a measurement of the thing on the shelf. A field that must be filled and cannot be filled truthfully is worse than a field that is simply absent: it turns every round plate in the inventory into a record carrying one value nobody can trust, and there is nothing on the record to say which value that is.

The same applies to a round sheet, which is the same disc with a different thickness. The rules for Plate and Sheet are identical today and wrong in the same way, so both are in scope.

There is a second problem underneath. Three separate places in the system each state what dimensions a type and shape require, and they do not agree with each other. One is keyed on type alone and never looks at shape. One is keyed on shape alone and never looks at type — by that rule a round plate needs Length and Diameter and no Thickness at all. The third, the one the Add Item form actually applies, is keyed on both. On top of that, the Edit Item form marks Length and Width with an asterisk and enforces neither, and never marks Thickness at all. Changing one of these and not the others would leave the system still saying three different things about a round plate. This feature makes all of them say the same thing for round plates and round sheets.

This is not a general reconciliation of those rule sets. The disagreements they carry about *other* type and shape combinations are real but are not what issue #85 reports, and closing them is a separate piece of work.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Record a round plate by what it actually is (Priority: P1)

The operator has a disc of aluminum on the bench. They measure it: six inches across, quarter inch thick. They open Add Item, choose Plate and Round, type those two numbers, and the item is recorded. They are not asked for a length and they do not invent one.

**Why this priority**: It is the whole of the reported problem. Until this works, every round plate entered into the inventory carries a fabricated measurement, and each one entered is another record to distrust later.

**Independent Test**: Open the Add Item form, select Plate and Round, supply only diameter and thickness, submit, and verify the item is created with exactly those dimensions and no length.

**Acceptance Scenarios**:

1. **Given** the Add Item form with Type `Plate` and Shape `Round` selected, **When** the operator supplies a diameter and a thickness and submits, **Then** the item is created and no length is recorded for it.
2. **Given** the same selection, **When** the operator looks at the dimension fields, **Then** Diameter and Thickness are marked as required and Length is not.
3. **Given** the same selection, **When** the operator submits with the diameter blank, **Then** the item is not created and the form identifies Diameter as the missing dimension.
4. **Given** the same selection, **When** the operator submits with the thickness blank, **Then** the item is not created and the form identifies Thickness as the missing dimension.
5. **Given** the same selection, **When** the operator chooses to supply a length as well, **Then** it is accepted and recorded — the field remains available, it has merely stopped being demanded.
6. **Given** Type `Sheet` and Shape `Round`, **When** the operator supplies a diameter and a thickness and submits, **Then** the item is created, identically to the plate.
7. **Given** Type `Plate` and Shape `Round` with only a diameter and thickness entered, **When** the operator changes the Type to `Bar`, **Then** Length becomes required again and the form says so before the operator submits.
8. **Given** Type `Bar`, `Tube` or `Threaded Rod` with Shape `Round`, **When** the operator fills the form, **Then** Length is required exactly as it is today.
9. **Given** Type `Plate` with Shape `Rectangular` or `Square`, **When** the operator fills the form, **Then** Length, Width and Thickness are all required exactly as they are today.

---

### User Story 2 - The same rule everywhere the item is recorded (Priority: P2)

The operator opens a round plate they created earlier, corrects its location, and saves. Nothing on the form demands a dimension the item does not have, and nothing it demands is silently ignored.

**Why this priority**: An item that can be created but not saved again is only half recorded, and a form whose asterisks do not match what it enforces teaches the operator to ignore asterisks. This is worth less than Story 1 because the operator has a working substitute — the item exists and can be read — but it is what makes Story 1 durable.

**Independent Test**: Create a round plate with only diameter and thickness, open it in the Edit Item form, save it without changing anything, and verify it survives unchanged and no dimension was demanded.

**Acceptance Scenarios**:

1. **Given** a round plate recorded with a diameter and thickness and no length, **When** the operator opens it for editing and saves without changes, **Then** it is saved unchanged and no dimension was demanded of them.
2. **Given** the Edit Item form showing a round plate, **When** the operator reads the dimension labels, **Then** the ones marked required are Diameter and Thickness, and the marks match what the form actually enforces.
3. **Given** the Edit Item form showing a round plate, **When** the operator clears the diameter or the thickness and saves, **Then** the change is refused and the missing dimension is named.
4. **Given** an item recorded through the application's item interface rather than the form, **When** a round plate is submitted with a diameter and thickness and no length, **Then** it is accepted on the same terms as one entered on the form.
5. **Given** a round plate on the Edit Item form, **When** the operator changes the Shape from `Round` to `Rectangular`, **Then** Length becomes required before the change can be saved.
6. **Given** a rectangular plate carrying a length, **When** the operator changes its Shape to `Round` and saves, **Then** the recorded length is retained rather than silently discarded, and the item saves.

---

### User Story 3 - A round plate reads as a disc (Priority: P3)

The operator finds the round plate in the inventory list. Its dimensions read as a six-inch disc a quarter inch thick — not as a blank.

**Why this priority**: It is a consequence rather than the request, but it is the one that would make Story 1 look broken. Item dimensions are assembled from the recorded values, and at least one place today produces nothing at all when there is no length. A correctly recorded item that displays as having no dimensions is not obviously better than the invented number it replaced.

**Independent Test**: Record a round plate with only diameter and thickness, then view it on each screen that shows item dimensions, and verify each one shows the diameter and the thickness.

**Acceptance Scenarios**:

1. **Given** a round plate with a diameter and thickness and no length, **When** the operator views it in the inventory list, **Then** its dimensions are shown as a diameter and a thickness, and the diameter is identifiable as one.
2. **Given** the same item, **When** the operator views its detail, its search results row, or its history, **Then** each shows the same diameter and thickness.
3. **Given** the same item, **When** any screen assembles a name or summary for it, **Then** the summary includes its dimensions rather than omitting them for want of a length.
4. **Given** a round plate that does carry a length, **When** it is displayed, **Then** the length is shown as well — nothing recorded is hidden.
5. **Given** any item that is not a round plate or sheet, **When** it is displayed, **Then** its dimensions read exactly as they do today.

---

### Edge Cases

- **A round plate submitted with neither diameter nor thickness.** Refused, with both named. The operator is not made to discover the second missing dimension by fixing the first.
- **A dimension supplied as blank versus not supplied at all.** Treated identically. Clearing a field means the same thing as never filling it.
- **A zero or negative diameter or thickness.** Refused, on the same terms as any other dimension — this feature changes which dimensions are required, not what a valid measurement is.
- **A round plate already in the inventory carrying an invented length.** Left exactly as it is. Nothing is rewritten, nothing is cleared, and it continues to display and to edit. The operator may clear the length themselves if they want to; the system does not decide that for them.
- **A round plate already in the inventory with no thickness.** Possible today, because the rule keyed on shape alone never asked for one. It remains readable and listed. It is only when the operator next edits it that the thickness is asked for — a stored item is never made unopenable by a rule that arrived after it.
- **Switching Type from `Plate` to `Sheet`, or Shape from `Round` to `Round`, mid-entry.** No change in what is required; the two are the same rule.
- **Wall thickness on a round plate.** Not applicable and not required, as today. A plate is solid.
- **Weight on a round plate.** Optional, as it is for every type and shape today.
- **Filtering the inventory by a length range.** A round plate with no length is simply not among the matches. That is the correct answer to the question asked, not an error, and the item is still found by a diameter or thickness filter.
- **A round plate whose diameter is smaller than its thickness.** Recorded without comment. The system does not decide what geometry is plausible.

## Requirements *(mandatory)*

### Functional Requirements

**What a round plate or sheet requires**

- **FR-001**: For an item whose Type is `Plate` or `Sheet` and whose Shape is `Round`, the only dimensions the system requires are Diameter and Thickness.
- **FR-002**: Length MUST NOT be required for such an item. It MUST remain available to record and MUST be preserved when supplied.
- **FR-003**: An attempt to record or amend such an item without a diameter or without a thickness MUST be refused, and the refusal MUST name every dimension that is missing.
- **FR-004**: The measurement across the face of a round item MUST be presented to the operator as "Diameter", on every form where it is entered, as it is presented today.

**Consistency of the rule**

- **FR-005**: Every place in the system that states what dimensions a round plate or round sheet requires MUST state the rule in FR-001. No place may continue to require Length for them, and no place may fail to require Thickness for them.
- **FR-006**: The Add Item form, the Edit Item form, and the application's item interface MUST all apply the same rule. An item that one of them accepts MUST be accepted by the others.
- **FR-007**: The dimensions a form marks as required MUST be the dimensions that form actually enforces, for every type and shape it can display — a mark that enforces nothing, and an enforced requirement that is unmarked, are both defects.
- **FR-008**: This change MUST NOT introduce a new disagreement between those statements of the rule for any other type and shape combination.

**What does not change**

- **FR-009**: Round Bar, Round Tube and Round Threaded Rod MUST continue to require exactly the dimensions they require today, including Length.
- **FR-010**: Rectangular and Square Plate and Sheet MUST continue to require Length, Width and Thickness.
- **FR-011**: No item already in the inventory may be modified, invalidated or made unreadable by this change. A round plate carrying a length keeps it; a round plate lacking a thickness remains readable and listed.
- **FR-012**: No dimension is added to or removed from what an item can record. The diameter of a round plate is the same recorded measurement as the diameter of a round bar.

**Display**

- **FR-013**: Wherever item dimensions are shown — the inventory list, the item detail, search results, and item history — a round plate or sheet with no length MUST show its diameter and its thickness, and MUST NOT show nothing.
- **FR-014**: A displayed diameter MUST be identifiable as a diameter rather than as an unlabeled measurement.
- **FR-015**: Any item that carries a length MUST continue to show it. Nothing recorded is withheld from display.
- **FR-016**: Items other than round plates and round sheets MUST display exactly as they do today.

### Key Entities

- **Inventory item**: A piece of stock on the shelf. Already carries a Type, a Shape, and its dimensions. This feature adds nothing to it and removes nothing from it; it changes which of the dimensions it already has must be filled in for one Type and Shape pairing.
- **Dimension**: A recorded physical measurement of an item — length, width (shown as diameter for round items), thickness, wall thickness, weight. The set is unchanged by this feature.
- **Dimension requirement rule**: The statement of which dimensions a given Type and Shape must have before an item can be recorded. This feature corrects that statement for round plates and round sheets, and makes the places that hold it agree.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A round plate is recorded from exactly the two measurements the operator can take from it — how far across and how thick — with no third number invented to satisfy the form.
- **SC-002**: No round plate or round sheet entered after this change carries a length the operator made up, because none is asked for.
- **SC-003**: A round plate created on the Add Item form can be opened in the Edit Item form and saved back unchanged, without supplying anything further.
- **SC-004**: On every screen that shows an item's dimensions, a round plate with no length is shown as a disc of a stated diameter and thickness — never as an item with no dimensions.
- **SC-005**: Every type and shape combination other than round Plate and round Sheet records exactly the dimensions it recorded before, required and optional alike.
- **SC-006**: Every item already in the inventory still displays and still edits, including round plates that carry a length and round plates that lack a thickness.
- **SC-007**: Asking the system what a round plate requires gives the same answer from every part of it that has an answer.

## Assumptions

- **Diameter is the measurement the inventory already records, not a new one.** Confirmed with the operator: a round item's diameter is the same recorded dimension that a round bar's and a round tube's diameter is, and it is already labeled "Diameter" on the forms whenever the Shape is Round. Issue #85 names "database schema" among the things to update; on inspection nothing in the schema stands in the way — the dimension exists, it is already optional at the storage level, and the requirement is imposed entirely by the rules layered over it. This feature therefore introduces no new stored dimension and needs no data migration.
- **Length stays on the form, it just stops being required.** Confirmed with the operator. The field remains visible and accepted for a round plate; the change is to the demand, not to the availability. This also means an operator who has a reason to record something there is not blocked, and existing round plates that carry a length have somewhere to display it.
- **Sheet is in scope alongside Plate.** Confirmed with the operator. Issue #85 names only Plate, but round Sheet carries the identical rule today and is wrong in the identical way; fixing one and leaving the other is leaving a known defect behind for the sake of the issue title.
- **Thickness is required, not merely allowed.** A disc with no thickness is not described. This matches what the Add Item form already demands of a round plate; it tightens only the rule keyed on shape alone, which asks for no thickness for any round item.
- **Wall thickness and weight are unaffected.** Wall thickness does not apply to a solid plate and is not required for one today. Weight is optional for every type and shape and stays optional.
- **"The application's item interface" means the existing programmatic route for creating and amending items.** No new entry point is introduced, and no existing one is retired.
- **The operator is the only user.** Per the project's operating context there are no roles, permissions or approval steps to consider in any of this.

## Out of Scope

- Introducing a separately stored diameter dimension, or any change to how dimensions are stored. Diameter remains the measurement the inventory already records for round items.
- Reconciling the pre-existing disagreements between the system's several statements of the dimension rules for type and shape combinations *other than* round Plate and round Sheet. Those disagreements are real and predate this issue; FR-008 requires only that this change not add to them.
- Supplying the dimension rule for `Channel`, which the Add Item form's rule set omits entirely today.
- Enforcing type-and-shape compatibility when an item is recorded. Which shapes a type may take is filtered on the Add Item form and enforced nowhere; that is a separate gap.
- Estimated volume. It is calculated from length and is not shown anywhere in the application.
- Any change to the inventory's search filters, including adding a filter named for diameter. The existing filters continue to work on the dimensions they already work on.
- Rewriting, clearing or flagging the invented lengths already recorded against existing round plates. They are the operator's data to correct or keep.
- Changing what dimensions round Bar, round Tube or round Threaded Rod require.
