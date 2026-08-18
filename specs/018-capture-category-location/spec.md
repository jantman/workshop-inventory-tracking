# Feature Specification: Category and Location on the Capture Confirmation Page

**Feature Branch**: `issues/99` (the feature directory is `specs/018-capture-category-location`)

**Created**: 2026-08-17

**Status**: Draft

**Input**: User description: "issue #99 on this repo" — The capture confirmation page can't set a category or a location (GitHub issue #99, from the #80 verification pass, comment item 3).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - File the product while capturing it (Priority: P1)

The operator captures an order. The listing has handed over specifications, a description,
a price and six images, and none of it says where the thing will live in the shop or what
kind of thing it is — only the operator knows that, and they know it now, with the listing
still on screen. On the capture confirmation page they state the category, the storage
location and the sub-location, and capture. The product is filed. There is no second visit.

**Why this priority**: This is the whole of issue #99. Today every captured product is
created uncategorized and unlocated, so filing it means finding it again afterwards, opening
it and editing it. That second visit is the entire cost of the defect, and one field on the
confirmation form removes it.

**Independent Test**: Capture an order with a category, a location and a sub-location filled
in, then open the resulting product and read all three back off it. Delivers the whole value
of the feature on its own.

**Acceptance Scenarios**:

1. **Given** the capture confirmation page, **When** the operator states a category, a
   location and a sub-location and captures, **Then** the created product carries all three.
2. **Given** the capture confirmation page, **When** the operator leaves all three blank and
   captures, **Then** the created product is uncategorized and unlocated, and the capture
   behaves exactly as it does today.
3. **Given** the capture confirmation page, **When** the operator states a category but no
   location, **Then** the product is categorized and unlocated — each field stands alone and
   neither requires the other.
4. **Given** a category path that no product yet uses, **When** the operator types it and
   captures, **Then** the product is filed under it and the path exists from that point on,
   with no separate step to create it.

---

### User Story 2 - Type against the vocabulary the rest of the app already knows (Priority: P2)

The operator does not remember whether last month's shelf was called `Shelf A` or `shelf a`,
or which of two similar category branches they settled on. As they type, the same suggestions
the product form offers appear here: the categories already in use, the locations already
recorded anywhere in the shop — metal stock included — and, once a location is chosen, the
sub-locations recorded under that location.

**Why this priority**: A filing field with no suggestions produces `Electronics` on Monday
and `electronic components` on Thursday, which is the problem issue #98 exists to fix, made
worse at the point of entry. It is a separate slice because US1 files the product without it;
this is what keeps the filing consistent.

**Independent Test**: Type a partial location that exists elsewhere in the shop and confirm
the suggestion appears, without submitting the form.

**Acceptance Scenarios**:

1. **Given** categories already in use in the catalog, **When** the operator focuses the
   category field on the capture page, **Then** those categories are offered as suggestions.
2. **Given** a location recorded on a metal stock item and on no product, **When** the
   operator types the start of it in the location field, **Then** it is offered.
3. **Given** a location has been stated, **When** the operator types in the sub-location
   field, **Then** the suggestions offered are the sub-locations recorded under that location.
4. **Given** a suggestion list is showing, **When** the operator types a value that is not in
   it, **Then** the value is accepted — the suggestions never restrict what can be entered.

---

### User Story 3 - The filing survives a question (Priority: P3)

Capturing can come back with a question — a suspected duplicate order, or a vendor item
number that already names a product. The page re-renders with the answer still to give. The
category, location and sub-location the operator typed are still there when it does.

**Why this priority**: The confirmation page already preserves every other typed field across
these re-renders. Three new fields that silently emptied themselves would send the operator
back to the second visit this feature exists to remove, and would do it invisibly. It is P3
because it only matters on the paths that ask a question.

**Independent Test**: Trigger the duplicate question with the three fields filled in, and read
them back off the re-rendered form.

**Acceptance Scenarios**:

1. **Given** a capture with a category, location and sub-location stated, **When** the capture
   comes back asking about a suspected duplicate, **Then** all three fields still hold what
   the operator typed.
2. **Given** the same, **When** the capture comes back reporting a validation failure,
   **Then** all three fields still hold what the operator typed.
3. **Given** a re-rendered form with the three fields preserved, **When** the operator answers
   the question and captures, **Then** the product is filed with those values.
4. **Given** an existing product already filed under one location, **When** the operator
   answers the recycled-identifier question by attaching to it and has stated a different
   location, **Then** the product is re-filed under the stated location.

---

### Edge Cases

- **A category path longer than the catalog allows.** Rejected, not truncated — the same
  answer the product form gives — and the capture comes back with the fields as typed so the
  operator can shorten it. A silently truncated path files the product somewhere that is not
  where the operator said.
- **A category path written with stray separators or casing** (`/Electronics//Passives/`).
  Normalized to the catalog's canonical form before storage, identically to the product form,
  so the same typing produces the same path on both pages.
- **A location cleared to blank on a capture that attaches to an existing product.** Blank is
  "I am not saying", not "erase what is there". A blank field never clears a value the product
  already holds.
- **A sub-location stated with no location.** Accepted. It is a free-form field on both sides
  and the catalog stores one without the other today; the capture page does not invent a
  constraint the rest of the app does not have.
- **A capture that attaches to an existing, already-filed product.** A stated value re-files
  it. The operator is holding the thing and saying where it goes now, which outranks where an
  earlier order said it went.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The capture confirmation page MUST let the operator state a category for the
  product being captured.
- **FR-002**: The capture confirmation page MUST let the operator state a storage location and
  a sub-location for the product being captured.
- **FR-003**: All three fields MUST be optional. A capture that leaves them blank MUST create
  an uncategorized, unlocated product without warning or error — uncategorized is an ordinary
  state, not a deficiency.
- **FR-004**: A capture in which the operator touches none of the three fields MUST record
  exactly what it records today.
- **FR-005**: A stated category MUST be normalized and validated by the same rules the product
  form applies, including the path length limit, and an over-length path MUST be rejected
  rather than truncated.
- **FR-006**: A category path that does not yet exist MUST be created by being typed, with no
  separate setup step — the same rule that holds on the product form.
- **FR-007**: A sub-location value that the metal stock records accept MUST be storable here,
  and one storable here MUST remain storable there. The two vocabularies are deliberately the
  same one and MUST NOT diverge in what they will hold.
- **FR-008**: The three fields MUST offer the same suggestions the product form offers for
  them: categories already in use, locations recorded anywhere in the shop including metal
  stock, and sub-locations scoped to the location currently stated. Suggestions MUST NOT
  restrict what can be entered.
- **FR-009**: When a capture attaches to a product that already exists, a stated category,
  location or sub-location MUST be written onto that product, replacing whatever it held. The
  operator is stating where the thing goes while holding it; that is more current than a value
  recorded on an earlier order. This is the rule the description already follows, and it is
  deliberately not the rule manufacturer and part number follow — those two are the evidence
  the recycled-identifier question depends on, and filing is not.
- **FR-010**: A blank field MUST NOT clear a value an existing product already holds. Blank is
  "I am not saying", not "erase it"; there is no way to unfile a product from this page.
- **FR-011**: The three values MUST survive every re-render of the confirmation form —
  the duplicate question, the recycled-identifier question, and a validation failure — holding
  what the operator typed, alongside the fields that already survive those re-renders.
- **FR-012**: The three values MUST be recorded on the product, not on the purchase. Filing is
  a property of the thing, not of the order that brought it.
- **FR-013**: Nothing in a captured listing may populate any of the three fields. Neither a
  category nor a location can be read off a vendor page, and a guessed value that looks stated
  is worse than a blank one.

### Key Entities

- **Product**: Already carries a category path, a location and a sub-location, all nullable.
  This feature adds no attribute; it adds a second place where the existing three are set.
- **Purchase**: Unchanged. It records nothing about filing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator who knows where a captured product goes can file it during capture,
  with zero follow-up visits to the product page — down from one for every capture today.
- **SC-002**: Every category path, location and sub-location value the product form accepts is
  accepted by the capture page, and produces an identically stored value.
- **SC-003**: A capture that leaves all three fields untouched produces a product and purchase
  indistinguishable from what the same capture produces today.
- **SC-004**: All three values are still present on the form after each of the three paths that
  re-render it.
- **SC-005**: The operator is never asked to name a category or location that does not already
  exist in a suggestion list before it can be used.
- **SC-006**: A capture that attaches to an existing product and states a location leaves that
  product's location equal to the stated one, with no follow-up edit.

## Assumptions

- The suggestion sources are the ones already serving the product form and the metal stock
  forms; this feature reuses them and introduces no new vocabulary or endpoint of its own.
- "The same inputs the product form already uses" means the same field semantics, validation
  and suggestion behavior — not necessarily a shared template fragment. How the sharing is
  achieved is a planning decision.
- The capture page is the only place changed. The receive step, the bookmarklet payload and
  the capture API's request shape are untouched; the bookmarklet lands on this form and the
  operator fills the fields there like any other.
- Issue #98 (an initial category taxonomy) is not a dependency. This feature is worth less
  against an empty category list and works the same way against a populated one.
- Product quantity, reorder threshold and tags remain out of scope. Only the three fields the
  issue names are added.
