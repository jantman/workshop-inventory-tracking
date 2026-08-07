# Feature Specification: Keep the Catalogue Tidy

**Feature Branch**: `issues/61`

**Created**: 2026-08-07

**Status**: Draft

**Input**: GitHub issue #61 — "2. Keep the catalog tidy: rename categories and tags, share the location/vendor vocabulary", with background in `docs/product-functionality-gap.md`. The issue's third section, structured specifications, was split out to issue #71 and is not part of this feature.

## Overview

The product catalogue lets the operator invent its own vocabulary as they go: a category is created by typing it on a product, a tag by typing it in a list, and a location or vendor by typing it in a box. That was a deliberate choice — there is no setup step and no empty-category cleanup story — but it has a cost that has now been felt. Typed vocabulary accretes typos, second thoughts, and near-duplicate spellings, and today there is no way to correct one except to edit every affected product by hand.

Separately, the two halves of the application do not share what they know. Metal stock already records locations and vendors and offers them as you type; the catalogue's location and vendor boxes suggest nothing and contribute nothing back. Left alone, the same shelf and the same supplier will end up spelled two ways, one on each side.

This feature gives the operator a way to correct the vocabulary after the fact, and makes the two halves draw on one shared list of location and vendor names.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rename a category (Priority: P1)

The operator notices a category is misspelled, or decides a better name for it, and renames it in one action. Every product filed directly under it, and every product in every sub-category beneath it, follows the rename. Nothing has to be opened and edited by hand.

**Why this priority**: This is the problem the issue leads with and the one with the highest manual cost today — a category with thirty products under it currently takes thirty edits to correct. It is also independently valuable: shipping only this already stops the catalogue's category tree from degrading.

**Independent Test**: Create products under `elctronics/passives` and `elctronics/passives/resistors`, rename `elctronics` to `electronics`, and confirm every product now reads `electronics/...` with its sub-category structure intact.

**Acceptance Scenarios**:

1. **Given** products filed under a category, **When** the operator renames that category, **Then** every one of those products is filed under the new name and none is left behind.
2. **Given** a category with sub-categories beneath it, **When** the operator renames it, **Then** the sub-categories keep their own names and their relative position under the renamed parent, and their products move with them.
3. **Given** an existing category, **When** the operator attempts to rename another category to a name that already exists or that already has products beneath it, **Then** the rename is refused with an explanation naming the conflict, and nothing is changed.
4. **Given** a rename in progress, **When** the operator is shown the confirmation, **Then** they are told how many products will be affected before they commit.
5. **Given** a completed rename, **When** the operator views the categories list, **Then** the old name is gone and the new name carries the same product counts.

---

### User Story 2 - Rename or merge a tag (Priority: P1)

The operator renames a tag, correcting a spelling. If they rename it to a tag that already exists, the two are merged: every product that carried either one carries the survivor, and the duplicate is gone.

**Why this priority**: Same problem, same cost, and tags are the more likely of the two to accrete near-duplicates because they are typed as free comma-separated text. Merging matters more here than for categories — the common repair is exactly "these two spellings are the same tag."

**Independent Test**: Tag one product `surpluss` and another `surplus`, rename `surpluss` to `surplus`, and confirm one tag remains carrying both products.

**Acceptance Scenarios**:

1. **Given** a tag applied to several products, **When** the operator renames it to an unused name, **Then** every one of those products carries the new name and the old name no longer exists.
2. **Given** two tags, **When** the operator renames one to the other's name, **Then** they are merged into one tag carrying every product that had either.
3. **Given** a product carrying both tags being merged, **When** the merge completes, **Then** that product carries the survivor exactly once.
4. **Given** a rename that would merge, **When** the operator is shown the confirmation, **Then** they are told it is a merge and not a rename before they commit.
5. **Given** a completed rename or merge, **When** the operator filters the catalogue by the surviving tag, **Then** every affected product is returned.

---

### User Story 3 - One vocabulary for locations and vendors (Priority: P2)

The operator types a location on a product, or a vendor on a purchase, and the application offers the names it already knows — including the ones the metal stock inventory uses. A name first typed on one side is offered on the other side afterwards. The two halves stop drifting apart by spelling.

**Why this priority**: This prevents the divergence rather than repairing it, so it matters most on the entries that have not been made yet. It is lower priority than the renames because the damage it prevents is still small and because the renames repair damage that already exists.

**Independent Test**: With metal stock recording a vendor, start typing that vendor on a product purchase and confirm it is offered; then record a new vendor on a product purchase and confirm it is offered on the metal stock form afterwards.

**Acceptance Scenarios**:

1. **Given** locations recorded on metal stock items, **When** the operator types in a product's location field, **Then** matching existing locations are offered as suggestions.
2. **Given** vendors recorded on metal stock items, **When** the operator types in a purchase's vendor field, **Then** matching existing vendors are offered as suggestions.
3. **Given** a location or vendor recorded only on a product or purchase, **When** the operator types in the corresponding metal stock field, **Then** that name is offered there too.
4. **Given** a suggestion is offered, **When** the operator ignores it and types something new, **Then** the new value is accepted — suggestions never restrict what can be entered.
5. **Given** no matching value exists anywhere, **When** the operator types, **Then** no suggestions are shown and entry proceeds normally.

---

### User Story 4 - Record a product's sub-location (Priority: P3)

The operator records where a product is with the same precision as metal stock: a location and, within it, a sub-location. Both are suggested from what the application already knows.

**Why this priority**: A convenience that closes a gap between the two halves, but a product with only a location is still findable. Smallest of the four and dependent on Story 3 for its suggestions.

**Independent Test**: Record a product with a location and a sub-location, and confirm both are stored, displayed on the product, and offered as suggestions afterwards.

**Acceptance Scenarios**:

1. **Given** a product being created or edited, **When** the operator records a location and a sub-location, **Then** both are stored against the product.
2. **Given** a product with a location, **When** the operator types in its sub-location field, **Then** sub-locations already known for that location are offered first.
3. **Given** an existing product recorded before this feature, **When** it is viewed, **Then** its location is unchanged and its sub-location is simply empty.

---

### Edge Cases

- **A rename that changes only capitalization or surrounding whitespace.** Category and tag names are stored in a normalized form, so `Resistors` and `resistors` are the same category. Such a rename must be reported as a no-op rather than accepted and silently discarded.
- **A category renamed to a position beneath itself** (`power` → `power/supplies`). This would make the category its own ancestor; it must be refused.
- **A rename that pushes a descendant's path past the maximum length.** Renaming a short parent to a long name can overflow the deepest path beneath it. The rename must be refused as a whole, not applied to the products that fit.
- **A rename applied while nothing matches.** Renaming a category or tag that no longer exists — because the last product carrying it was edited or deleted meanwhile — must report that plainly, not create the new name from nothing.
- **A tag merge where the survivor is the tag being renamed away from.** Merging must be direction-independent in its result: one tag remains, carrying the union of products.
- **A link or bookmark to a renamed category.** Filtering by the old path returns nothing after the rename. This is accepted; the operator is not offered a redirect.
- **Suggestion vocabulary that does not fit the other side's conventions.** Metal stock locations follow a code convention (`M1-A`, `T-5`, `Other`) that a product location such as `Drawer 3` does not. Suggestions are offered from the shared pool without either side being constrained to the other's conventions.
- **A location or vendor recorded only on inactive metal stock history rows.** These are part of the vocabulary the application knows and are offered; a name is not withdrawn from suggestions because the item carrying it was deactivated.

## Requirements *(mandatory)*

### Functional Requirements

**Renaming categories**

- **FR-001**: The system MUST allow the operator to rename a category from the categories view, without opening the products filed under it.
- **FR-002**: A category rename MUST carry every product filed directly under that category to the new name.
- **FR-003**: A category rename MUST carry every sub-category beneath the renamed category, and every product filed under those sub-categories, preserving the structure beneath the renamed level.
- **FR-004**: The system MUST refuse a category rename whose target name already exists as a category or already has products beneath it, and MUST state the conflict rather than merging.
- **FR-005**: The system MUST refuse a category rename whose target would place the category beneath itself.
- **FR-006**: The system MUST show the operator how many products a category rename will affect, and require confirmation, before applying it.
- **FR-007**: A category rename MUST be applied in full or not at all: if any part of it cannot be applied, no product is changed.

**Renaming and merging tags**

- **FR-008**: The system MUST allow the operator to rename a tag without opening the products carrying it.
- **FR-009**: A tag rename to an unused name MUST carry every product to the new name and leave the old name no longer in existence.
- **FR-010**: A tag rename to a name already in use MUST merge the two, leaving one tag carrying every product that had either, and MUST NOT leave any product carrying the survivor more than once.
- **FR-011**: The system MUST tell the operator, before applying it, whether a tag rename will merge into an existing tag or simply rename, and how many products are affected.
- **FR-012**: A tag rename or merge MUST be applied in full or not at all.
- **FR-013**: The system MUST present a view of tags in use with their product counts, so that near-duplicate spellings can be seen and corrected.

**Shared location and vendor vocabulary**

- **FR-014**: The system MUST offer existing location names as suggestions while the operator types a product's location.
- **FR-015**: The system MUST offer existing vendor names as suggestions while the operator types a purchase's vendor, both when capturing an order and when adding a purchase by hand.
- **FR-016**: The vocabulary offered for locations and for vendors MUST draw on values recorded anywhere in the application, so the metal stock inventory and the product catalogue see the same list.
- **FR-017**: A location or vendor name newly recorded on either side MUST be available as a suggestion on both sides from that point on, with no separate publishing, import, or re-indexing step.
- **FR-018**: Suggestions MUST NOT restrict entry: any value the operator types MUST be accepted, whether or not it appears in the suggestions.
- **FR-019**: Suggestion matching MUST be case-insensitive, and MUST offer values recorded on inactive metal stock history rows as well as active ones.

**Product sub-location**

- **FR-020**: The system MUST allow an optional sub-location to be recorded against a product, alongside its existing optional location.
- **FR-021**: The system MUST display a product's sub-location wherever its location is displayed.
- **FR-022**: The system MUST offer existing sub-location names as suggestions while the operator types a product's sub-location, preferring those already recorded under the location currently entered.
- **FR-023**: Products recorded before this feature MUST remain valid with no sub-location, which is an ordinary state and not an error.

### Key Entities

- **Category**: A position in a hierarchy classifying products, expressed as a path of names. It exists because a product is filed under it. This feature adds renaming as an operation on it.
- **Tag**: A free-form label applied to products across categories. This feature adds renaming and merging as operations on it.
- **Location vocabulary**: The set of location names — and, separately, sub-location names — that the application knows about, drawn from both metal stock items and products. Not a managed list: it is whatever has been recorded.
- **Vendor vocabulary**: The set of vendor names the application knows about, drawn from both metal stock items and product purchases. Not a managed list.
- **Product**: Gains an optional sub-location alongside its existing optional location.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Correcting a category name that N products are filed under takes one operation regardless of N, where today it takes N product edits.
- **SC-002**: After a category rename, every product that was under the old name — at any depth beneath it — is under the new name, and none is under the old one.
- **SC-003**: No rename can produce two categories with the same name, and no rename silently absorbs one category into another: a conflicting rename is refused and reported.
- **SC-004**: Merging two spellings of a tag leaves exactly one tag, carrying every product that had either spelling, each exactly once.
- **SC-005**: A rename that is refused leaves the catalogue exactly as it was — no product is partially renamed.
- **SC-006**: A location or vendor name recorded on either half of the application is offered as a suggestion on the other half the next time that field is typed in, with no intervening step by the operator.
- **SC-007**: The operator can record and later read back both a location and a sub-location on a product.
- **SC-008**: Suggestions never block entry: every value that could be recorded in these fields before this feature can still be recorded after it.

## Assumptions

### Scope boundaries

- **Renaming is a repair, not routine data entry.** Categories and tags continue to be created by typing them on a product; this feature adds no setup step, no create/delete management screen, and no empty-category concept. There is still no categories table to maintain and no orphan cleanup on a schedule.
- **Category renames refuse collisions; tag renames merge.** This follows the issue directly: it describes the plan as refusing a colliding category rename, and describes tags as wanting rename *and merge*. Category merging is not built. If the operator wants two categories combined, they rename one to a free name and re-file its products, or the need is revisited later as its own change.
- **A category rename operates on a whole level, not a single path.** Renaming `elctronics` renames it wherever it sits in the tree at that position, taking its subtree with it. Renaming a leaf affects only that leaf.
- **Suggestion vocabulary is derived, not curated.** There is no locations table or vendors table to maintain, no way to add a name without recording it on something, and no way to remove one except by removing the last thing that carries it. Suggestions are the distinct values already in the data. This mirrors how categories work today and how the existing metal stock field suggestions already work.
- **Neither half's naming conventions are imposed on the other.** Metal stock locations follow a code convention that product locations do not; sharing the suggestion pool does not make either side validate against the other. No new location validation is added by this feature.
- **Old links are not redirected.** A saved filter or bookmark pointing at a renamed category or tag stops matching. Building redirect or alias machinery for a single-user application is not warranted.
- **Structured specifications are out of scope.** Issue #61's body also describes replacing the free-text specifications field with named values so products can be filtered by specification. That is a data model change with a migration path of its own, roughly the size of the other three parts combined, and it has been split out to issue #71. The free-text specifications field is untouched by this feature.

### Environmental and data assumptions

- The catalogue currently holds a small number of products, so a rename touching every product under a category is a small operation. No progress reporting, batching, or background processing is assumed to be needed.
- This is a single-user application: no other operator can be editing a product while a rename is in progress, so no locking or conflict resolution is required.
- Category and tag names are already stored in a normalized (lowercased, trimmed) form, and this feature does not change that normalization. A "rename" that differs only in case or whitespace therefore has no effect and is reported as such.
- The metal stock inventory already exposes suggestions for its own location, sub-location, and vendor fields; this feature widens what those suggestions draw on rather than introducing a suggestion mechanism.
- Existing products carry a location but no sub-location. No migration of existing location text into a location/sub-location pair is attempted — a value that today reads as a whole location stays a whole location.
