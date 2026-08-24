# Feature Specification: Stock Fit Search

**Feature Branch**: `issues/100`

**Created**: 2026-08-24

**Status**: Draft

**Input**: GitHub issue #100 — "Better dimension search": *"Right now we store dimensions for stock (specifically bar and plate) as length, width, and thickness. Searching currently (as far as I can tell) uses those dimensions literally, so a search for rectangular bar with a thickness of 0.5", length of 4" and width of 3" doesn't return stock that's marked with a thickness of 0.5", length of 3", and width of 4" even though the overall dimensions of those pieces of stock are identical. […] Re-think how stock search works to take into account the actual use of this functionality: someone needs a piece of stock of given dimensions and material to make a part from; they want to find the closest-sized piece of material that fits the requirements […] Tolerance should also be included somehow […] Provide a list of options for how we can improve the metal stock (inventory) search to return all items that can provide a specific dimension of material."*

## Overview

The operator has a part to make. They know the material and they know the smallest block of stock the part will fit inside. What they want from the inventory is the list of pieces on the shelf that can yield that block — and, among those, the one that wastes the least and is quickest to get onto the machine.

The search does not answer that question. It answers a narrower one: *which records carry a Length in this range, a Width in that range and a Thickness in the other?* Those three numbers are stored as three separate labelled fields and compared one against its own namesake. So a piece of stock is found only if the operator happens to name its dimensions in the same order the person who recorded it did. Ask for 0.5 × 3 × 4 and the shelf's 0.5 × 4 × 3 stays hidden, though it is the same bar and would be turned the same way in the vise. The record's labels are an artifact of how it was entered; the search treats them as facts about the metal.

The same mistake, one level up, hides whole categories of usable stock. A 2" length of 2" round can be made from a 2" round bar, and it can also be made from a 3" square bar, or sawn out of a block. None of those appear, because the search compares a request for a round to the records of squares and rectangles field by field and finds nothing in common. The operator's fallback today is to run the search several times with different guesses about how a usable piece might have been written down, and to remember, unaided, that a bigger piece of the right material is always an option.

Tolerance has the same shape of problem. The dimensions of a request are nominal: a part that wants 2" of length is usually still makeable from 1.98". The search offers min and max bounds per field, which can express that, but only if the operator does the arithmetic themselves for every dimension on every search, and only if they have already guessed which field the number will be in.

This feature replaces the literal, per-field, per-name comparison with a single question the operator can actually ask: **I need a piece of *this material* this big — what on the shelves can give me one?** It answers with every item that can, ordered so the closest fit is at the top, and it treats each requested dimension as nominal within a tolerance the operator sets for that dimension.

What it does not do is change how stock is recorded. Length, Width and Thickness keep their meanings and their places on the Add and Edit forms, and the rules in the type/shape taxonomy that say which of them a given kind of item requires are unchanged. This is a change to the question search asks, not to the data it asks it of.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Orientation stops hiding stock (Priority: P1)

The operator needs a rectangular blank half an inch thick, three inches by four. They enter the material and those three numbers. Every rectangular piece of that material large enough to yield the blank comes back — including the ones recorded as 0.5 × 4 × 3, and 4 × 0.5 × 3, and any other ordering of the same measurements.

**Why this priority**: It is the concrete failure the issue reports, and it is the one that makes the current search actively misleading rather than merely limited. An empty result reads as "there is none", and today it can mean "there is one, filed under a different word order". Nothing else in this feature matters if the operator cannot trust a negative answer.

**Independent Test**: Record the same physical bar twice with its measurements in two different field orders, search once for those measurements, and verify both records come back.

**Acceptance Scenarios**:

1. **Given** an item recorded with thickness 0.5", length 4" and width 3", **When** the operator searches for a piece 0.5" × 3" × 4" of that material, **Then** the item is returned.
2. **Given** the same item, **When** the operator searches for the same three measurements in any other order, **Then** the item is returned, and the result set is identical whichever order was typed.
3. **Given** an item measuring 0.5" × 3" × 4", **When** the operator searches for a piece 0.75" × 3" × 4", **Then** the item is not returned — no ordering of its measurements is large enough.
4. **Given** an item measuring 1" × 6" × 12", **When** the operator searches for a piece 0.5" × 3" × 4", **Then** the item is returned: a larger piece can yield a smaller one.
5. **Given** a search that returns several items, **When** the operator reads the results, **Then** each row states the item's dimensions as recorded, so the operator can see what they will be cutting from.

---

### User Story 2 - A bigger piece of any shape is still a piece of stock (Priority: P1)

The operator needs a 2" length of 2" round steel. Along with the 2" round bar, the search offers the 3" square bar and the 6" cube — pieces that are not round, are wasteful, and will absolutely work if the round bar is not on the shelf.

**Why this priority**: This is the half of the issue that the operator cannot work around by re-typing the search. Orientation is a matter of guessing a word order; cross-shape yield is a body of knowledge the search never had. It carries the issue's own example — a 2" round turned out of a 6" cube — and it is what turns the search from a record lookup into an answer to "can I make this today".

**Independent Test**: Record only a square bar and a rectangular block of a material, search for a round piece of that material that both can yield, and verify both are returned.

**Acceptance Scenarios**:

1. **Given** a 3" square bar 12" long, **When** the operator searches for a 2" diameter round 2" long of that material, **Then** the bar is returned.
2. **Given** a 6" × 6" × 6" block, **When** the operator searches for a 2" diameter round 2" long of that material, **Then** the block is returned.
3. **Given** a 1.5" round bar, **When** the operator searches for a 2" diameter round of that material, **Then** it is not returned — nothing can be added to it.
4. **Given** a 4" diameter round bar 12" long, **When** the operator searches for a rectangular piece 1" × 2" × 3", **Then** the bar is returned: the requested cross-section fits within the circle.
5. **Given** a 2" diameter round bar, **When** the operator searches for a rectangular piece 2" × 2" in cross-section, **Then** it is not returned — that square does not fit inside that circle.
6. **Given** a round plate recorded as a diameter and a thickness with no length, **When** the operator searches for a piece it can yield, **Then** it is returned, its thickness being treated as the third dimension of the disc.
7. **Given** any item whose record is missing a dimension the fit test needs, **When** a search is run, **Then** the item is not returned as a match and the operator is told how many items were skipped for want of a recorded dimension.

---

### User Story 3 - The closest fit is at the top (Priority: P2)

The search returns eleven items. The 2" round bar is first; the 6" cube is last. The operator takes the first one and does not read the rest.

**Why this priority**: With Stories 1 and 2 in place the search returns *more* than it used to — sometimes much more, since every oversized piece of the right material now qualifies. Without an order that puts the sensible choice first, the operator has traded a search that hid the answer for one that buries it. It is P2 rather than P1 because an unordered correct answer is still an answer, where an incorrect one is not.

**Independent Test**: Record several items of one material that can all yield the same requested piece, run one search, and verify the result order runs from least excess material to most.

**Acceptance Scenarios**:

1. **Given** several items that can all yield the requested piece, **When** the operator runs the search, **Then** they are ordered with the least excess material first.
2. **Given** the same search, **When** the operator reads a result row, **Then** it shows how that item compares to the request, so the choice between the top few is visible without opening each one.
3. **Given** two items that fit the request equally closely, **When** the search is run twice, **Then** they appear in the same order both times.
4. **Given** a search where one item matches the request exactly, **When** the results are shown, **Then** that item is first.

---

### User Story 4 - Nominal, within a tolerance set per dimension (Priority: P2)

The part wants 2" of length and 1.98" would do — but its 0.5" thickness is a finished face with nothing to give. The operator allows a couple of thou on the length, leaves the thickness alone, and the search stops discarding pieces that are a hair under where being a hair under does not matter.

**Why this priority**: The issue names tolerance explicitly, and without it the operator has to shade every number downward by hand before typing it — tedious, and a place to make a mistake that silently drops stock. Per dimension rather than one number for the whole request because the dimensions are not alike: length is nearly always the forgiving one and a thickness often is not, and a single global tolerance buys the slack on the length at the price of returning stock that is too thin. It follows Stories 1 and 2 because a tolerance on the wrong question does not help.

**Independent Test**: Record an item slightly short on one dimension and correct on the others, search with a tolerance on that dimension alone, and verify it is returned; search with that tolerance removed and verify it is not.

**Acceptance Scenarios**:

1. **Given** an item 1.98" long and a request for 2" of length carrying a 0.02" tolerance on length, **When** the search is run, **Then** the item is returned.
2. **Given** the same item and the same request with no tolerance on length, **When** the search is run, **Then** the item is not returned.
3. **Given** an item 1.98" long and 0.48" thick and a request for 2" long by 0.5" thick with a 0.02" tolerance on length only, **When** the search is run, **Then** the item is not returned — the thickness falls short and nothing allows for it.
4. **Given** a request being composed, **When** the operator reads the form, **Then** each tolerance is shown beside the dimension it applies to, and a dimension left without one is visibly exact.
5. **Given** a result that qualifies only because of a tolerance, **When** the operator reads its row, **Then** it is distinguishable from one that fits outright and the dimension that used its tolerance is named.
6. **Given** a negative tolerance on any dimension, **When** the operator submits, **Then** the search is refused with a message naming that dimension.

---

### Edge Cases

- **A dimension the request needs is not recorded on the item.** A threaded rod records no width; a channel records nothing dimensional at all. These cannot be tested for fit. They are excluded from results, and the operator is told how many were excluded so that "no results" is never confused with "nothing on the shelf".
- **Hollow stock.** A tube's recorded outside dimensions describe a shell, not a solid: a 3" square tube cannot yield a 2" solid round. Items carrying a wall thickness are excluded from solid-yield matching, and the requested piece is always solid — an operator who wants a length of tube finds it by its recorded dimensions in the existing advanced search, as they do today.
- **Nothing fits.** The operator is told plainly that no item can yield the requested piece, and how many items of the requested material were considered — distinguishing "you have none of this material" from "you have some, all too small".
- **The requested piece is under-specified.** A request with no material, or with fewer dimensions than the requested shape needs, is refused with a message naming what is missing, rather than silently matching everything.
- **Zero or negative dimensions.** Refused, naming the offending dimension.
- **Inactive items.** Excluded by default, exactly as the existing search excludes them, since they are not on the shelf.
- **A tolerance as large as the dimension it applies to.** Refused, naming that dimension: it would make the dimension meaningless.
- **An item is exactly the requested size.** It fits — the comparison is inclusive at the boundary, before any tolerance is applied.

## Requirements *(mandatory)*

### Functional Requirements

**The request**

- **FR-001**: The operator MUST be able to describe a piece of stock they need by material, by the shape of the piece, and by its dimensions, as a single search.
- **FR-002**: The search MUST accept a requested piece that is rectangular (three dimensions) or round (a diameter and a length), these being the shapes the operator makes parts from.
- **FR-003**: The material of the request MUST match items hierarchically, as material matching already works elsewhere in search — asking for Steel MUST return items recorded under its descendants.
- **FR-004**: The search MUST refuse a request that is missing its material or any dimension its requested shape needs, and MUST name what is missing.
- **FR-005**: The search MUST refuse a dimension that is zero or negative, and MUST name the offending dimension.

**The fit test**

- **FR-006**: An item MUST be returned when the requested piece can be cut or machined out of it, and MUST NOT be returned otherwise.
- **FR-007**: The fit test MUST be independent of the order in which an item's or a request's dimensions were entered: any assignment of the request's dimensions to the item's axes that fits counts as a fit.
- **FR-008**: The fit test MUST compare a request to an item across shapes — a round request against rectangular, square and hex stock, and a rectangular request against round stock — using the largest solid piece of the requested shape that the item's recorded dimensions can contain.
- **FR-009**: An item MUST be treated as the solid body its type and shape describe. A round plate recorded as a diameter and a thickness and no length MUST be treated as a disc of that diameter and that thickness, not as an item missing a dimension.
- **FR-010**: An item that carries a wall thickness MUST be excluded from solid-yield matching, its recorded outside dimensions describing a shell rather than a solid.
- **FR-011**: An item whose record lacks a dimension the fit test requires MUST be excluded from results, and the count of items excluded on that ground MUST be reported with the results.
- **FR-012**: An item exactly the size of the requested piece MUST be returned; the comparison is inclusive at the boundary.
- **FR-013**: The fit test MUST NOT depend on the item's own recorded shape matching the requested shape.

**Tolerance**

- **FR-014**: The operator MUST be able to state a tolerance for each requested dimension independently, by which an item may fall short of that dimension and still be returned.
- **FR-015**: A requested dimension left without a tolerance MUST be held to its stated value exactly; tolerance is opt-in, per dimension, and never applied by default.
- **FR-016**: Each tolerance in force MUST be shown beside the dimension it applies to on the search form, and MUST NOT be applied invisibly.
- **FR-017**: A negative tolerance, or one at least as large as the dimension it applies to, MUST be refused with a message naming that dimension.
- **FR-018**: A result that qualifies only by tolerance MUST be distinguishable in the results from one that fits outright, and each dimension that used its tolerance MUST be named.

**The results**

- **FR-019**: Results MUST be ordered with the closest fit first, closeness being how little material is left over once the requested piece is taken from the item.
- **FR-020**: The ordering MUST be stable: the same search over unchanged inventory MUST produce the same order.
- **FR-021**: Each result MUST show the item's dimensions as recorded, so the operator can see what they will be working from.
- **FR-022**: Each result MUST show how the item compares to the request, so the choice between the leading candidates does not require opening each item.
- **FR-023**: A search matching nothing MUST say so plainly and MUST report how many items of the requested material were considered.
- **FR-024**: Results MUST be limited to active items by default, consistently with the existing search.

**Fit within the existing search**

- **FR-025**: The fit search MUST be a search of its own, distinct from the existing advanced search rather than a mode inside it.
- **FR-026**: The existing advanced search MUST be left as it is: its per-dimension range filters MUST continue to work exactly as they do today for the browsing they support. This feature adds a way to ask a different question rather than replacing the current one.
- **FR-027**: The fit search MUST present its results through the same shared results table the inventory list and the advanced search already use, carrying the same columns, row content, selection and bulk actions those pages already provide. That table MUST NOT be forked or reimplemented for this search.
- **FR-028**: The fit-specific information required by FR-018 and FR-022 MUST be carried within that shared table rather than in a substitute of its own, and MUST NOT change how the table renders on the pages that already use it.
- **FR-029**: Results MUST be shown ordered by closeness of fit when they first arrive; where the shared table offers sorting by column, that MUST remain available to the operator afterwards.
- **FR-030**: How stock is recorded MUST NOT change: the meanings of Length, Width and Thickness, the type/shape rules governing which are required, and the Add and Edit forms are all out of scope.

### Key Entities

- **Requested piece**: what the operator needs — a material, a shape (rectangular or round), the dimensions that shape requires, and a tolerance. It is not stored; it exists for the duration of a search.
- **Item envelope**: the solid body an inventory item's recorded type, shape and dimensions describe. It is derived from the record at search time, not recorded on it, and is what the fit test compares against. A round bar's envelope is a cylinder; a round plate's is a disc; a rectangular bar's is a box.
- **Fit result**: an item that can yield the requested piece, together with how closely it fits — the basis for the ordering and for what each row tells the operator.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A search for a piece of given dimensions returns the same set of items regardless of the order in which the operator types those dimensions — for every ordering, in every case.
- **SC-002**: An operator looking for stock to make a given part runs one search, not several: no re-ordering of dimensions and no re-running against other shapes produces an item the first search missed.
- **SC-003**: Every item in the inventory that can physically yield the requested piece appears in the results, and no item that cannot appears in them.
- **SC-004**: When a usable piece exists, the item the operator would choose by hand — the smallest usable piece of the right material — is the first result.
- **SC-005**: Results appear within two seconds of submitting a search over the full inventory.
- **SC-006**: An empty result is trustworthy: it is accompanied by the count of items of that material considered and the count excluded for want of a recorded dimension, so the operator can tell "you have none" from "yours are all too small" from "yours are recorded incompletely".
- **SC-007**: The inventory list and the existing advanced search behave and read exactly as they do today once this feature ships — the shared results table has been extended, not copied.

## Assumptions

- **The requested piece is a rectangular block or a round.** These are what parts get made from in this workshop. Requests shaped like a hex, an angle or a channel are not offered; the existing dimension filters remain available for finding such stock by its recorded numbers.
- **Cross-sections are compared axis-aligned.** A rectangle is tested against a round cross-section by its diagonal, and against a rectangular one edge-to-edge. Rotating a rectangular request inside a rectangular cross-section to squeeze out a fractionally larger piece is not modelled — it is not how stock gets cut here.
- **A hex bar is treated by the circle inscribed in its flats.** The recorded width of a hex is its across-flats measurement, and the largest round that can be turned from it is that measurement.
- **A dimension with no tolerance is exact.** Tolerances are opt-in and per dimension; a blank tolerance means that number is held as stated, which is the safe reading when the operator has not thought about it.
- **Kerf, facing and clean-up allowance are the operator's business.** The tolerance the operator sets is the only allowance the search applies; it does not add a saw's width or a skim cut of its own.
- **Material removal is assumed possible.** The search reports what geometry permits; whether the operator wants to bandsaw a cube to get a round is their decision, which is what the ordering by excess material is there to inform.
- **Precision stock is not treated specially.** A precision-ground piece is as eligible as any other; the operator can see the flag on the result and decide.
- **The inventory is small enough to compare item by item.** This is a single-user workshop database; no new indexing or caching machinery is assumed, and none should be added without a measurement.
- **Existing search behaviours carry over.** Active-only by default, hierarchical material matching, and the existing result-row content are the baseline this builds on.

## Out of Scope

- Changing how items are recorded — field meanings, required-dimension rules, or the Add and Edit forms.
- Reserving, allocating or deducting stock against a planned part; this feature finds material, it does not lay claim to it.
- Suggesting how to make the part — cut lists, machining sequence, or nesting several parts into one piece of stock.
- Matching hollow stock to hollow requests. A requested piece is always solid, and tube-to-tube searching stays with the existing dimension filters.
- Cost, weight or availability as ranking inputs.
