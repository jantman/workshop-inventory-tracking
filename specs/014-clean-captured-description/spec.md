# Feature Specification: Clean Captured Description

**Feature Branch**: `issues/91`

**Created**: 2026-08-16

**Status**: Draft

**Input**: GitHub issue #91 — "Captured description carries inline CSS and JavaScript, and loses every line break", a sub-issue of #80. It records that on the three A+ listings `B0DMNXC4CD`, `B09GM8FB3X` and `B0FX4PDW6M` the stored `Description` specification contains stylesheet and script source rendered as prose, that on `B09GM8FB3X` the `Customer Reviews` row is contaminated the same way, and that in every case the description arrives as one unbroken run of text with its paragraph and list structure gone. Issue #80's verification comment records the observed sizes: 21,415 and 28,767 characters.

## Overview

Capture reads a listing's own page in the browser that is displaying it and turns what it finds into catalog data (`specs/007-product-page-capture/`). One of the things it keeps is the description, stored as a specification row named `Description`, uncapped — storage was deliberately widened so that FR-006's "nothing is truncated" holds without an exception.

That promise is being kept on the wrong content. Two separate defects, one shared cause:

- **The description is not only prose.** A rich ("A+") description block routinely carries an inline stylesheet and inline script code. Reading the block's text reads those too, so a stylesheet and a function body end up stored and displayed as though they were the manufacturer's writing. This is a large part of why two of the sampled descriptions measure over 21,000 characters. The same reading is used for specification table cells, which is how a `Customer Reviews` row picked up the same junk.
- **The description has no shape.** Every run of whitespace is collapsed to a single space before the value is stored, so line breaks, paragraphs, list items and divisions leave no trace. A listing whose description is six paragraphs and two bullet lists is stored as one line.

The fix is not to archive markup and it is not to convert markup. It is to read the *prose* of the block — skipping the parts of it that were never prose — and to keep the line structure the page presents, so what is stored reads the way the listing reads.

The distinction that has to survive is **shorter without being lossier**. FR-006 of the capture feature says nothing is truncated, and the three plain-description listings (`B0CKXJLP4B`, `B01N4OSKWE`, `B099F4X4Q9`) capture their descriptions whole today. A change that makes the A+ descriptions smaller by also dropping prose has not fixed the bug, it has traded one data-loss defect for another.

## Terminology

- **Description block** — the region of a listing page that holds its description. Either the plain form or the rich "A+" form; capture reads whichever is present, never both.
- **Non-content node** — anything inside a captured region whose text was never prose: an inline stylesheet, inline script code, a scripting-disabled fallback, or an inert content template. Its text is markup or code that the page never shows the reader as words.
- **Block boundary** — a point in the page's structure where the reader sees a new line or a new paragraph: an explicit line break, or the end of a paragraph, list item, table row, division or heading.
- **Specification row** — a name and a value, as captured from the listing's product-information tables and bullets. The description is stored as one of these, named `Description`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The stored description is the listing's words, not its markup (Priority: P1)

A workshop user captures an Amazon listing whose description is a rich A+ block. The block carries an inline stylesheet and inline script code, as A+ blocks routinely do. The user opens the resulting product and reads the `Description` specification. It contains the manufacturer's copy about the part — and nothing else. No `.aplus-module { margin: 0; }`, no `function loadModule(...)`, no run of braces and semicolons.

**Why this priority**: This is the defect that makes the stored description unusable and the one that inflates it to five figures. A description a person cannot read is not a captured description, and once the listing is delisted there is no second chance to get it. Everything else in this feature is an improvement on top of a value that has to be readable first.

**Independent Test**: Capture from a listing whose description block contains an inline stylesheet and inline script code; confirm; and read the stored `Description` value. It contains the block's visible copy and none of the stylesheet or script text. Verifiable on its own without any change to line structure.

**Acceptance Scenarios**:

1. **Given** a listing whose description block contains an inline stylesheet, **When** the user captures the listing, **Then** the stored `Description` contains none of the stylesheet's text.
2. **Given** a listing whose description block contains inline script code, **When** the user captures the listing, **Then** the stored `Description` contains none of that source.
3. **Given** a listing whose description block contains a scripting-disabled fallback or an inert content template, **When** the user captures the listing, **Then** the text inside it is not part of the stored `Description`.
4. **Given** a listing whose description block is plain prose with no stylesheet or script, **When** the user captures the listing, **Then** the stored `Description` is exactly the copy the block shows — nothing is dropped and nothing is truncated.
5. **Given** a description block whose only text is a stylesheet and a script, **When** the user captures the listing, **Then** capture treats that block as carrying no description and continues to whichever other description block the page has, or reports that no description was found — it does not store an empty or whitespace-only description.
6. **Given** any listing, **When** the user captures it, **Then** every other field capture extracts — title, brand, price, images, the other specification rows — is unchanged by this feature.

---

### User Story 2 - The description keeps its paragraphs, and shows them (Priority: P2)

The same user reads the description they just captured. The listing presented it as an intro paragraph, three feature paragraphs and a bullet list. The stored description has those breaks, and the product page displays them as breaks — not as one continuous wall of text that has to be re-read to find where one point ends and the next begins.

**Why this priority**: It is the difference between a description that is *present* and one that is *usable*, but it only matters once Story 1 has made the value readable at all. Storing line structure and then flattening it at display would be no better than not storing it, so the storing and the showing are one slice.

**Independent Test**: Capture from a listing whose description contains explicit line breaks and multiple paragraphs or list items; open the product page; and confirm the displayed value breaks where the listing breaks. Verifiable independently of whether any stylesheet stripping happened.

**Acceptance Scenarios**:

1. **Given** a description containing an explicit line break, **When** the user captures the listing, **Then** the stored value has a single line break at that point.
2. **Given** a description whose copy is split into paragraphs, **When** the user captures the listing, **Then** the stored value separates those paragraphs from each other.
3. **Given** a description containing a list, **When** the user captures the listing, **Then** each list item begins on its own line in the stored value.
4. **Given** a description whose markup nests blocks several deep, **When** the user captures the listing, **Then** the stored value contains no run of more than one blank line — nesting does not produce a gap the listing does not show.
5. **Given** a stored description containing line breaks, **When** the user views the product page, **Then** the value is displayed with those breaks intact.
6. **Given** a stored description containing line breaks, **When** the user opens the product for editing and saves without touching that value, **Then** the line breaks survive the round trip unchanged.
7. **Given** a description that the listing presents as a single unbroken paragraph, **When** the user captures the listing, **Then** the stored value is a single line and gains no breaks — runs of spaces and tabs within a line are still collapsed to one space, and leading and trailing whitespace is still removed.

---

### User Story 3 - A specification row is prose too (Priority: P3)

The user captures a listing whose product-information table holds a `Customer Reviews` cell containing a rating widget with its own inline styling and script. The captured row reads as a rating and a review count. It does not carry a stylesheet.

**Why this priority**: It is the same defect reaching a second surface, and it affected one row on one of the sampled listings — real, but far smaller in blast radius than the description. It is listed separately because it is separately observable: a fix to the description alone would leave it standing.

**Independent Test**: Capture from a listing whose product-information table contains a cell with an inline stylesheet or script; confirm; and read that specification row on the product page. Its value is the cell's visible text only.

**Acceptance Scenarios**:

1. **Given** a product-information cell containing an inline stylesheet or script, **When** the user captures the listing, **Then** that row's stored value contains none of that text.
2. **Given** a product-information cell whose visible content spans more than one line, **When** the user captures the listing, **Then** the stored value keeps those lines, and the product page displays them as lines.
3. **Given** a specification name whose cell contains a line break, **When** the user captures the listing, **Then** the stored name is a single line — names are still matched, merged and de-duplicated exactly as they are today.
4. **Given** the six listings sampled in #80, **When** they are re-captured, **Then** the set of specification names captured for each is the same as before this feature; only the contaminated values change.

---

### Edge Cases

- **A description block that is entirely non-content.** After the non-content nodes are skipped there is nothing left. Capture must treat this as "this block has no description" rather than storing an empty or whitespace-only value, and must go on to consider the page's other description blocks.
- **A description with no block structure at all.** The plain description form is often a single run of text. It must come through exactly as it does today: one line, no added breaks, nothing lost.
- **Deeply nested markup.** A+ blocks nest divisions inside divisions. Each nesting level must not contribute its own blank line; the result must never show more than one blank line between paragraphs.
- **A line break inside a list item.** The item's own line and the break inside it are different things and both are visible to the reader; both are kept.
- **Whitespace-only lines.** A block whose only content is spacing markup contributes no visible line and must not leave a blank line behind.
- **A specification value that gains line breaks.** Such a value must remain editable and saveable without silently losing its breaks, and must still be usable as a search value.
- **A listing page whose structure has changed.** Capture's existing rule holds: a region that can no longer be found costs that one field and nothing else. Nothing in this feature may cause a capture to fail, and a description that cannot be read leaves the rest of the capture intact.
- **Content the page hides.** A+ blocks carry alternative-layout copy that is present but not shown. It is prose, so it is kept — the cost of keeping it is one edit, and the cost of dropping it on a guess is content that cannot be recovered once the listing is gone.

## Requirements *(mandatory)*

### Functional Requirements

**Reading only prose**

- **FR-001**: When capture reads text from a listing region, it MUST exclude the text of non-content nodes within that region — at minimum inline stylesheets, inline script code, scripting-disabled fallbacks, and inert content templates.
- **FR-002**: FR-001 MUST apply to every region capture reads text from, including the description block, specification names and specification values.
- **FR-003**: Excluding non-content nodes MUST NOT alter the page the user is looking at. Capture runs inside the listing page the user has open; the page must be left exactly as it was found.
- **FR-004**: A description block whose remaining text is empty or whitespace-only after FR-001 MUST be treated as carrying no description, and capture MUST continue to the page's other description blocks as it does when a block is absent.

**Keeping line structure**

- **FR-005**: Capture MUST record an explicit line break in the source as exactly one line break in the stored value.
- **FR-006**: Capture MUST record a block boundary — the end of a paragraph, list item, table row, division or heading — as a paragraph separation in the stored value.
- **FR-007**: Capture MUST collapse any run of blank lines in the stored value so that no more than one blank line ever appears between two lines of text.
- **FR-008**: Within a single line, capture MUST continue to collapse runs of spaces and tabs to one space, and MUST remove leading and trailing whitespace from the stored value as a whole.
- **FR-009**: FR-005 through FR-008 MUST apply to the description and to specification values. Values that are single-line by nature — the listing title, the brand, the price, and specification names — MUST remain single-line, so that the existing matching, merging and de-duplication of specification names behaves exactly as it does today.
- **FR-010**: The stored description MUST NOT be truncated, capped, or otherwise shortened by any rule other than the removal of non-content nodes and the whitespace rules above.

**Showing it as written**

- **FR-011**: Wherever a specification value is displayed, a value containing line breaks MUST be displayed with those breaks.
- **FR-012**: Wherever a specification value can be edited, a value containing line breaks MUST be editable and saveable without losing them.

**Not breaking what works**

- **FR-013**: This feature MUST NOT change which description block capture selects on a page that has a readable description in more than one form, beyond the consequence of FR-004.
- **FR-014**: This feature MUST NOT change any other extracted field — the title, brand, price, image set, or the set of specification names captured from a page.
- **FR-015**: No part of this feature may cause a capture to fail. A region that cannot be read costs that region's field and nothing else, as capture already guarantees.

### Key Entities

- **Description block** — the region of a listing page holding its description, in either its plain or its rich form. Contributes one stored value.
- **Specification row** — a captured name and value. The description is stored as one, named `Description`. Names are single-line and are matched case- and whitespace-insensitively; values may span lines.
- **Non-content node** — an element within a captured region whose text is markup or code rather than prose, and is therefore excluded from what capture reads.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Re-capturing `B0DMNXC4CD`, `B09GM8FB3X` and `B0FX4PDW6M`, the stored `Description` value for each contains no stylesheet source — no run of a `{`, declarations and a `}` — and no script source — no `function` or `var` declaration.
- **SC-002**: For each of those three listings, the stored `Description` is shorter than the character count the same listing produced before this feature (21,415 and 28,767 for two of them, per #80 §1b), and the copy the listing visibly shows is still present in full.
- **SC-003**: Re-capturing `B0CKXJLP4B`, `B01N4OSKWE` and `B099F4X4Q9`, each stored `Description` is character-for-character identical to the value the same listing produces today, apart from line breaks introduced by FR-005 and FR-006. No description becomes empty and none becomes shorter by losing prose.
- **SC-004**: For a listing whose description the page shows as multiple paragraphs or a list, the product page displays the stored description with the same number of visible paragraph or item breaks the listing shows, and with no run of more than one blank line.
- **SC-005**: Re-capturing `B09GM8FB3X`, the `Customer Reviews` specification value reads as a rating and a review count and contains no stylesheet or script text.
- **SC-006**: Across all six listings, the set of specification names captured is unchanged from the pre-feature capture, and every other pre-filled field on the confirmation page — vendor, item identifier, title, brand, price, image count — is unchanged.
- **SC-007**: A stored description containing line breaks survives an edit-and-save of the product with its breaks intact.

## Assumptions

- **No back-fill of already-captured products.** The three affected products are fixed by re-capturing them, which is the verification step the issue already calls for. A one-time cleanup pass over stored values would be scale machinery for a three-row problem in a single-user application (Principle I).
- **No new dependency.** The line-structure and node-exclusion rules are a plain walk of the page's own structure. No HTML sanitizer, no Markdown conversion, no library — this is the issue's own constraint and it is what Principle I requires.
- **Hidden-but-present prose is kept.** Where an A+ block carries copy the page does not currently show, it is treated as prose and captured. This matches the rule capture already applies to description images: discarding on a guess loses content that cannot be recovered; keeping on a guess costs one deletion.
- **Line breaks are a storage concern, not a formatting one.** The stored value is plain text with line breaks in it. Nothing in this feature stores markup, styling, or a markup-derived format.
- **The character counts in SC-002 come from #80 §1b** and are the values observed before this feature. They are a comparison baseline, not a target.
- **Verification against the real listings is manual and owner-driven.** This application cannot re-fetch an Amazon listing from the LAN — that path was ruled out in `specs/007-product-page-capture/` because a machine on the LAN meets a bot wall. Confirming SC-001 through SC-006 means the owner capturing the six listings from their own browser.
- **The e2e fixture will need to grow real-shaped markup.** The A+ fixture used by the existing capture tests is hand-written and does not currently contain the inline stylesheet, script, or paragraph and list structure this feature turns on. Anything learned from looking at a live listing belongs back in the fixture as markup shaped like the real thing.

## Dependencies

- Builds directly on `specs/007-product-page-capture/`, whose FR-005 (whichever description block is present, never both), FR-006 (nothing is truncated), FR-007 (an unreadable region costs one field and no more) and FR-008/FR-009 (specification rows are merged by name) all continue to hold.
- Depends on the description storage widening already shipped, which is what makes "kept in full" possible; this feature reduces what is stored without reducing what is kept.

## Out of Scope

The following were raised in the same #80 verification pass and are separate issues. None is addressed here:

- Capturing the "About this item" bullet section (#80 items 7 and 10).
- Defaulting the manufacturer part number from a `Model Number` or `Mfr Part Number` specification row (#80 items 2 and 10).
- Bulk deletion of captured images from the product page (#80 item 10).
- Which images are captured, including the A+ specification-table image that was missed (#80 items 5, 8 and 10).
- Promoting a `UPC` specification to an identifier (#80 item 7).
- The unit-price-per-pack calculation on the confirmation page (#80 item 4).
- The "Not from this page" warning behind a reverse proxy (#80 item 1).
