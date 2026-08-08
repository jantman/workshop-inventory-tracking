# Feature Specification: Structured Specifications

**Feature Branch**: `issues/71`

**Created**: 2026-08-07

**Status**: Draft

**Input**: GitHub issue #71 — "Structured specifications: store product specifications as named values, not one block of text", split out of issue #61, with background in `docs/product-functionality-gap.md`. Issue #61's other three parts are specified in `specs/004-catalog-taxonomy-tidy/` and are not part of this feature.

## Overview

A product's specifications are today one block of free text. The operator types whatever they want to know later — voltage, thread pitch, tolerance — into a paragraph, and the catalogue stores it as a paragraph. It is searchable by word, and that is all it is: it cannot be filtered, it cannot be laid out as fields, and there is no way to ask a question of it.

The consequence is the one the gap document names. "Show me every 12 V converter I own" is not a question this catalogue can answer. The nearest thing is a word search for `12 V`, which also returns the product whose paragraph happens to mention a 12 V input on a 5 V regulator, and misses the one whose operator wrote `12VDC`.

This feature replaces the paragraph with a list of named values. A specification becomes a name and a value — `Voltage` / `12 V` — recorded, displayed, and filtered as a name and a value. Existing paragraphs are carried across whole and unaltered; nothing already written is parsed, split, or guessed at.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Record a product's specifications as named values (Priority: P1)

The operator adds or edits a product and records its specifications as a list of named values rather than a paragraph: a row for `Voltage` / `12 V`, a row for `Output current` / `3 A`, a row for `Connector` / `barrel 5.5 mm`. The product page shows them laid out as fields. Products recorded before this feature still show everything they showed before, unchanged.

**Why this priority**: Nothing else in the feature is possible without the data having a shape. This slice is also independently valuable on its own: a product page that lays specifications out as fields is legible in a way a paragraph is not, even before anything can be filtered.

**Independent Test**: Create a product with three named specifications, view it, and confirm each name and value is shown as its own field; then open a product created before this feature and confirm its original text is present in full.

**Acceptance Scenarios**:

1. **Given** a product being created, **When** the operator records several name/value specifications and saves, **Then** every one is stored against the product and shown on its page as a separate named field.
2. **Given** a product with specifications, **When** the operator edits it, **Then** each existing specification appears as an editable name and value, and can be changed, removed, or added to.
3. **Given** a product recorded before this feature with a free-text specifications paragraph, **When** it is viewed after this feature ships, **Then** that text is present in full, character for character, and is not split, reworded, or truncated.
4. **Given** a product with no specifications, **When** it is viewed, **Then** no specifications are shown and this is an ordinary state, not an error.
5. **Given** the operator enters a specification whose name duplicates another on the same product, **When** they save, **Then** the save is refused with a message naming the duplicate, and nothing is changed.
6. **Given** the operator leaves an unused entry row entirely blank, **When** they save, **Then** it is ignored rather than stored or reported as an error.

---

### User Story 2 - Find every product with a given specification (Priority: P2)

The operator asks the catalogue for every product that records `Voltage` as `12 V` and gets exactly those, without the products that merely mention 12 V somewhere else. They can also ask for every product that records a `Voltage` at all, whatever its value.

**Why this priority**: This is the reason the feature exists — the question the gap document leads with. It comes second only because it has nothing to operate on until Story 1 has shipped and specifications exist to filter.

**Independent Test**: Record one product with `Voltage` / `12 V`, one with `Voltage` / `5 V`, and one whose description mentions 12 V but which records no voltage specification; filter for `Voltage` = `12 V` and confirm exactly the first is returned.

**Acceptance Scenarios**:

1. **Given** products recording various specifications, **When** the operator filters by a specification name and value, **Then** exactly the products carrying that name with a matching value are returned.
2. **Given** products recording various specifications, **When** the operator filters by a specification name with no value, **Then** every product that records that name is returned, whatever its value.
3. **Given** a product whose description or notes contain the filter text but which records no such specification, **When** the specification filter is applied, **Then** that product is not returned.
4. **Given** a specification filter, **When** it is combined with the existing category, tag, stock, and text filters, **Then** all of them apply together and narrow the result.
5. **Given** a specification name that no product records, **When** it is filtered for, **Then** an empty result is shown and no error is raised.
6. **Given** a product page showing a specification, **When** the operator follows that specification, **Then** they are taken to the catalogue filtered by that name and value.
7. **Given** the existing free-text search box, **When** the operator searches for a word, **Then** specification names and values are searched as the old paragraph was, so nothing that used to be findable stops being findable.

---

### User Story 3 - Keep specification names consistent (Priority: P3)

While typing a specification name, the operator is offered the names already used elsewhere in the catalogue; while typing a value, the values already recorded under that name. Typing `Volt` offers `Voltage`, so the catalogue does not end up with `Voltage`, `voltage`, and `Volts` as three different questions.

**Why this priority**: A convenience that protects the value of Story 2 over time — a filter is only as good as the consistency of what it filters on. The feature works without it; it just degrades faster.

**Independent Test**: Record `Voltage` on one product, then start typing `Vol` in a second product's specification name and confirm `Voltage` is offered; accept it and confirm the values already recorded under `Voltage` are offered for the value.

**Acceptance Scenarios**:

1. **Given** specification names recorded on other products, **When** the operator types a specification name, **Then** matching existing names are offered as suggestions.
2. **Given** a specification name has been entered, **When** the operator types its value, **Then** values already recorded under that name are offered as suggestions.
3. **Given** a suggestion is offered, **When** the operator ignores it and types something new, **Then** the new name or value is accepted — suggestions never restrict what can be entered.
4. **Given** the specification filter on the catalogue list, **When** the operator types in its name or value box, **Then** the same suggestions are offered there.
5. **Given** no specification has ever been recorded, **When** the operator types, **Then** no suggestions are shown and entry proceeds normally.

---

### Edge Cases

- **An existing paragraph carried across.** It becomes exactly one specification, named `Specifications`, whose value is the paragraph verbatim — including its line breaks. It is not split at newlines, colons, or commas, because any such split would be a guess about text the operator wrote for themselves.
- **A carried-across paragraph longer than a new value would normally be.** The value must hold anything the old field held, so no existing text is refused or trimmed on the way in.
- **Rolling the change back.** The reverse of the migration must restore a single block of text per product with nothing lost, including for products whose specifications were entered as named values after the change.
- **A name that differs from another on the same product only in case or surrounding spaces.** `voltage` and `Voltage ` are the same name; recording both on one product is a duplicate and is refused.
- **Half a row.** A name with no value, or a value with no name, is refused with a message. Only an entirely blank row is ignored.
- **A value the operator spells differently from last time.** `12V` and `12 V` are different values and will not match each other. Suggestions exist to make this less likely; the system does not normalize units, spacing, or spelling, because guessing that `12 V`, `12VDC`, and `12 volts` are one value would be reinterpreting the operator's data.
- **Filtering by a value without a name.** Not offered. The existing free-text search already finds a value wherever it appears; the specification filter answers "which products record *this name* as *this value*", which requires the name.
- **A migrated legacy entry showing up in the name suggestions.** `Specifications` will be offered as a name until the operator has split the last carried-across paragraph. This is accepted: it is visible, it is honest about what it is, and it disappears as the paragraphs are converted.
- **Ordering.** Specifications are shown in the order the operator entered them. There is no alphabetical reordering and no drag-to-reorder.
- **A specification name recorded on many products with a typo.** Correcting it means editing those products. Renaming a specification name across the catalogue is not part of this feature.

## Requirements *(mandatory)*

### Functional Requirements

**The shape of a specification**

- **FR-001**: A product MUST be able to carry any number of specifications, including none.
- **FR-002**: Each specification MUST consist of a name and a value, both required and both non-empty once stored.
- **FR-003**: A specification value MUST accommodate any text the previous free-text specifications field could hold, including multiple lines.
- **FR-004**: A product MUST NOT carry two specifications with the same name, compared without regard to case or surrounding whitespace.
- **FR-005**: A specification name and value MUST be stored as the operator typed them, apart from trimming surrounding whitespace; the system MUST NOT reword, re-case, or normalize units or spelling.
- **FR-006**: Specifications MUST retain the order in which the operator entered them, and MUST be displayed in that order.

**Recording and editing**

- **FR-007**: The add and edit product forms MUST allow the operator to add, change, and remove individual named specifications.
- **FR-008**: A save MUST be refused, with the offending entry identified and nothing changed, when a specification has a name but no value, a value but no name, or a name duplicating another on the same product.
- **FR-009**: An entry row left entirely blank MUST be ignored rather than stored or reported.
- **FR-010**: The product page MUST display specifications as named fields rather than as a paragraph.
- **FR-011**: The product's machine-readable representation MUST carry its specifications as named values, so anything reading a product through the interface sees the same structure the page does.

**Filtering and search**

- **FR-012**: The catalogue list MUST allow filtering by a specification name, returning every product that records that name whatever its value.
- **FR-013**: The catalogue list MUST allow filtering by a specification name together with a value, returning every product that records that name with a matching value.
- **FR-014**: Specification value matching MUST be case-insensitive and MUST match a value that contains the entered text, so a partially remembered value still finds the product.
- **FR-015**: Specification name matching MUST be case-insensitive and MUST match the whole name, so filtering `Voltage` does not also return products recording `Input voltage adjustment`.
- **FR-016**: A specification filter MUST combine with the existing text, category, tag, and stock filters, all narrowing the result together.
- **FR-017**: The existing free-text search MUST match specification names and values, so that everything findable through the old paragraph remains findable.
- **FR-018**: A specification shown on the product page MUST offer a one-action route to the catalogue filtered by that name and value.

**Suggestions**

- **FR-019**: The system MUST offer specification names already recorded anywhere in the catalogue as suggestions while the operator types a specification name, both on the product forms and on the catalogue filter.
- **FR-020**: The system MUST offer the values already recorded under the entered name as suggestions while the operator types a specification value.
- **FR-021**: Suggestions MUST NOT restrict entry: any name or value the operator types MUST be accepted whether or not it appears in the suggestions.

**Carrying the existing data across**

- **FR-022**: Every existing non-empty specifications paragraph MUST be carried across as exactly one specification whose value is that paragraph verbatim, with no text lost, added, split, or reinterpreted.
- **FR-023**: A product with no specifications text MUST end up with no specifications, not with an empty one.
- **FR-024**: The change MUST be reversible: reversing it MUST restore a single block of specifications text per product with no content lost, for products whose specifications were entered as named values as well as for those carried across.

### Key Entities

- **Product Specification**: One named fact about a product — a name (`Voltage`) and a value (`12 V`), belonging to exactly one product and ordered among that product's other specifications. Removed with the product. Replaces the product's free-text specifications field.
- **Specification vocabulary**: The set of specification names, and the values recorded under each, that the catalogue knows about. Derived from what has been recorded, not curated: there is no list to maintain, no way to add a name without recording it on a product, and no way to remove one except by removing the last product carrying it. This mirrors how categories, tags, locations, and vendors already work.
- **Product**: Loses its free-text specifications field and gains its list of specifications. Nothing else about it changes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: "Every 12 V converter I own" is answerable in one filter operation, and its result contains no product that merely mentions 12 V without recording it as a specification.
- **SC-002**: Every product that carried specifications text before the change carries the identical text after it, character for character, including line breaks.
- **SC-003**: No product's specification content is lost by applying the change or by reversing it.
- **SC-004**: A specification recorded on a product can be read back individually by name, rather than only as part of a block of text.
- **SC-005**: Every text search that returned a product through its specifications paragraph before the change still returns it after.
- **SC-006**: A specification name typed once is offered as a suggestion the next time the operator types in a specification name field, with no intervening step.
- **SC-007**: Suggestions never block entry: any name or value the operator wants to record can be recorded, whether or not it has been used before.
- **SC-008**: A product page shows each specification as its own labelled field, and following one lands on the catalogue filtered to the products sharing it.

## Assumptions

### The five questions the issue asked to settle

- **The shape of a named value is a name and a value, both required.** Nothing constrains what either says: no unit list, no type system, no numeric parsing, no per-name value rules. A hobby workshop catalogue that made the operator declare `Voltage` a numeric field in volts before they could write `12 V` would cost more than the paragraph does. The only constraint is that a name may not appear twice on one product, because a product recording `Voltage` twice makes "filter by voltage" ambiguous for no gain.
- **Filtering is by exact name and contained value, with suggestions doing the consistency work.** The issue is right that values will not be uniformly spelled, and there are three ways to respond: normalize them, restrict them to a picklist, or offer what has been typed before and accept whatever is typed. This takes the third. It is the same choice the catalogue already makes for categories, tags, locations, and vendors, and it is the only one of the three that cannot silently change or reject what the operator meant. The cost is that `12V` and `12 V` remain two values; the suggestion list is what keeps that from happening, and the free-text search remains the fallback when it does.
- **Existing paragraphs are carried across whole, as a single specification named `Specifications`.** Not parsed at newlines, not split at colons, not dropped, and not left behind in a second field that would have to be maintained forever alongside the new one. The operator converts a paragraph into named values by editing that product, at whatever pace they care to, and the carried-across entry is visibly a carried-across entry until they do.
- **Distributor-label scans do not populate specifications.** What a distributor's 2D label yields — distributor part number, quantity, order reference, supplier order reference, date code — are facts about a *purchase*, not specifications of the product, and the create form already keeps them verbatim in a note block for exactly that reason. Turning them into named specifications would file purchase provenance under the wrong heading. Scanning behaviour is unchanged by this feature, and the question of values with no obvious name does not arise, because no scanned value is being routed here.
- **The printed label is unchanged.** Space on the label is already the binding constraint — the description truncates before the human-readable code is dropped — and a name/value list is longer than the paragraph it replaces, not shorter. Specifications were not on the label before this feature and are not added to it by this feature.

### Scope boundaries

- **No specification-name rename or merge.** The vocabulary will accrete typos exactly as categories and tags did, and the repair is the same shape as the one just built for those. It is not built here: this feature is already a data model change with a migration, and correcting a name today means editing the products carrying it, as it did for categories until recently. If the need is felt, it is a separate change.
- **No per-name configuration.** No declared unit, no expected type, no ordering preference, no "required for products in this category". Names come into existence by being typed, as categories do.
- **No filtering by value alone, and no numeric comparison.** "Every product whose voltage is above 9 V" is not answerable and is not attempted; values are text the operator wrote.
- **One specification filter at a time.** Filtering by two specifications simultaneously is not offered. The catalogue is small enough that one specification plus the existing category, tag, and text filters narrows it sufficiently.
- **Notes and description are untouched.** This feature changes the specifications field and nothing else on the product.

### Environmental and data assumptions

- The catalogue holds a small number of products, so carrying every existing paragraph across is a small operation with no need for batching, progress reporting, or background processing.
- This is a single-user application with no external consumers of the product interface, so the specifications field changing shape breaks nothing outside this repository.
- The existing free-text specifications field is operator-authored and never machine-generated, so there is no producer that has to be updated in step with the change.
- The catalogue already offers derived suggestions for categories, tags, locations, and vendors; this feature adds another vocabulary to that existing mechanism rather than introducing suggestions.
