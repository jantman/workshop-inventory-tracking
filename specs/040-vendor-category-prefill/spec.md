# Feature Specification: A Vendor's Category Is Not the Shop's Category

**Feature Branch**: `robot-army/issue-138-a-digikey-order-capture-pre-fills-the`

**Created**: 2026-09-06

**Status**: Draft

**Input**: GitHub issue #138 — "A DigiKey order capture pre-fills the vendor's category, which becomes a branch of the shop's taxonomy" (labels: bug, robot-army). Found during the #80 verification pass, capturing DigiKey order 100882558: the capture pre-filled the new product's category with DigiKey's own catalog name, "power supplies - board mount", where the shop's taxonomy for that part is `electronics/power/power supplies`. The issue offers three options and recommends the first — do not pre-fill from the vendor at all — on the grounds that the codebase already decided this question for the Amazon listing capture (018 FR-013) and wrote down why.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Capturing a DigiKey order leaves the category to the operator (Priority: P1)

The operator captures a DigiKey order. New products are created from its lines. None of them
arrives carrying DigiKey's catalog name in the shop's category field: each is uncategorized
until the operator files it, exactly as a product captured from an Amazon listing is.

**Why this priority**: This is the reported defect, and it is the path that does the damage.
The category field is free-form and the browsable category tree is built from the distinct
values actually in use, so a vendor category left unchanged even once becomes a permanent
branch of the shop's taxonomy. The cost is paid in the tree, not in the one record, and the
operator has no reason to look at the tree while capturing an order.

**Independent Test**: Capture a DigiKey order whose part detail carries a vendor category.
Inspect the created products: every one has an empty category. Inspect the category tree: it
gained no branch from the capture.

**Acceptance Scenarios**:

1. **Given** a DigiKey order line whose part detail states the category "Power Supplies - Board Mount", **When** the operator captures the order, **Then** the created product's category is empty.
2. **Given** the same capture, **When** the operator opens the browsable category tree afterwards, **Then** it contains no branch that came from the vendor's catalog name.
3. **Given** a DigiKey order line whose part detail is unavailable, **When** the operator captures the order, **Then** the created product's category is empty and nothing about the capture reports an error — a blank category is an ordinary state, not a failure.

---

### User Story 2 - Capturing a single DigiKey part leaves the category to the operator, and lets them set it (Priority: P2)

The operator looks a part up on the single-part DigiKey capture page and creates a product
from it. The vendor's category is shown as part of "what DigiKey says", where it is
information; it is not silently carried into the product. The page offers an empty Category
field alongside the Storage Location and Sub-Location fields it already offers, so an
operator who knows where the part belongs can file it while creating it.

**Why this priority**: Same defect, second door. This page carries the vendor category in a
hidden field, so today the operator cannot see the value being stored, cannot edit it, and
cannot decline it. Removing the hidden field without offering a visible one would leave a
capture page that can state a location but not a category, which is the inconsistency 018
FR-007 removed everywhere else.

**Independent Test**: Look up a part whose detail carries a vendor category, create the
product, and inspect it: the category is whatever the operator typed, empty if they typed
nothing, and never the vendor's value unless they typed that. The same test applies to the
Add Product form a scan opens (FR-010).

**Acceptance Scenarios**:

1. **Given** a looked-up DigiKey part whose category is "Power Supplies - Board Mount", **When** the operator creates the product without touching the Category field, **Then** the created product's category is empty.
2. **Given** the same looked-up part, **When** the operator types `electronics/power/power supplies` into the Category field and creates the product, **Then** that is the product's category.
3. **Given** the same looked-up part, **When** the operator views the page, **Then** DigiKey's category is still displayed among the part's stated detail, presented as the vendor's information rather than as a value about to be recorded.

---

### User Story 3 - Enriching an existing product does not file it (Priority: P3)

A product already in the catalog is enriched from DigiKey's part detail — during an order
capture, a backfill, or a re-capture. Enrichment fills the manufacturer and the
specifications it can. It does not fill the category, whether or not the category is blank.

**Why this priority**: The narrowest of the three doors and the least visible, but the one
most likely to be missed by a fix aimed only at the reported symptom. It writes the same
wrong value into the same field, and it does so to products the operator was not even
creating.

**Independent Test**: Enrich a product whose category is blank from a part detail that states
one. The category is still blank; the manufacturer and specifications were still filled.

**Acceptance Scenarios**:

1. **Given** a product with a blank category and a DigiKey part detail stating a category, **When** the product is enriched, **Then** the category is still blank and the manufacturer and specification rows were written as before.
2. **Given** a product the operator has already filed under `electronics/power/power supplies`, **When** the product is enriched from a part detail stating a different category, **Then** the operator's value is untouched.

---

### Edge Cases

- **The vendor states no category.** Indistinguishable from the vendor stating one, now: the product is uncategorized either way. No error, no warning, no difference in the flow.
- **A product created by an order capture is later re-captured or backfilled.** The second pass must not file it either; there is no path by which a vendor category reaches the field.
- **An existing product already carries a vendor-shaped category from a capture made before this change.** Nothing about it changes. Cleaning up values already recorded is the operator's business, through the ordinary category rename the taxonomy admin already offers, and is out of scope here.
- **The operator types the vendor's category by hand.** It is stored, exactly as any other typed value is. The rule is about what the system asserts unprompted, not about what the operator may say.
- **A scanned bag opens the Add Product form.** The scan path pre-loads the visible Category input from the vendor's part detail, where the operator can see and edit it. Visible is better than hidden, but a pre-loaded value that is simply accepted is still the vendor's value becoming a branch — the reported defect with one more chance to catch it. It is covered by the same rule (FR-010).
- **Copy that promises a category.** The order review page warns that lines with no part detail "arrive without a manufacturer, category or specifications", which implies lines *with* detail arrive with a category. That sentence stops being true and must be corrected, or the page states something the capture no longer does.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A product created by capturing a vendor order MUST NOT have its category set from the vendor's part detail. The category of such a product is empty unless the operator stated one.
- **FR-002**: Enriching a product from a vendor's part detail MUST NOT write the category, whether the product's category is blank or already set. Enrichment continues to fill the manufacturer and specifications under its existing gap-filling rule.
- **FR-003**: The single-part DigiKey capture page MUST NOT submit the vendor's category as the value to be recorded. No hidden field may carry it into the created product.
- **FR-004**: The single-part DigiKey capture page MUST offer an empty, editable Category field alongside its existing Storage Location and Sub-Location fields, using the same vocabulary and suggestions the add and edit forms use, so that filing at capture time remains possible without the vendor supplying the value.
- **FR-005**: The vendor's own category MAY still be displayed as part of what the vendor states about the part, where it is labelled as the vendor's information. It MUST NOT be presented as, or pre-loaded into, a field that will be recorded.
- **FR-006**: An empty category MUST remain an ordinary, non-error state throughout capture. No validation, warning, or blocking prompt may be introduced because a captured product is uncategorized.
- **FR-007**: On-page copy that tells the operator what a captured line records MUST agree with FR-001 — no page may promise that a captured product arrives with a category.
- **FR-008**: The change MUST NOT alter any category value already recorded on an existing product. No data migration, backfill, or cleanup of previously captured vendor categories is performed.
- **FR-009**: The rule MUST hold for every vendor whose capture path can read a category from the vendor, not only for the one path where it was reported, so that the two capture families do not diverge again.
- **FR-010**: Scanning a part the catalog does not hold, which opens the ordinary Add Product form pre-loaded with what the vendor knows about it, MUST NOT pre-load the category. The other pre-loaded values are unaffected — the rule is about the one field whose values become the shop's taxonomy, not about pre-loading in general.

### Key Entities

- **Product**: Carries a category path, free-form and nullable. This feature adds no attribute and removes none; it removes a source that wrote to one.
- **Vendor part detail**: What a vendor states about a part — manufacturer, description, datasheet, photo, parameters, and the vendor's own catalog category. The category remains readable and displayable; it stops being a source for the product's field.
- **Category tree**: The browsable hierarchy, built from the distinct category values in use. It has no rows of its own, which is precisely why a single stored vendor value becomes a permanent branch.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Capturing a DigiKey order of any size adds zero branches to the category tree. Before and after the capture, the set of categories in use is identical.
- **SC-002**: Of the products created by a vendor capture, 100% are uncategorized unless the operator typed a category during that capture.
- **SC-003**: Every category present in the tree can be traced to a value a person typed; none is traceable to a vendor's catalog.
- **SC-004**: An operator who knows where a single captured part belongs can file it during the capture, without a second visit to the product's edit page.
- **SC-005**: Capture succeeds at the same rate as before for orders and single parts alike; no capture fails, warns, or asks an extra question because a category is absent.

## Assumptions

- **The issue's Option 1 is adopted, and Options 2 and 3 are not.** No "DigiKey calls this X, accept it?" control is added, and no vendor-category-to-taxonomy mapping table is introduced. The issue names Option 2 as the follow-up if the suggestion turns out to be missed; that is a later decision made on evidence, not now.
- **The visible Category field on the single-part capture page (FR-004) is a deliberate, small addition beyond a strict reading of "stop pre-filling".** Without it that page would be the only capture page that can state a location but not a category. It costs one existing, already-shared field.
- **DigiKey is the only vendor whose capture reads a category today.** FR-009 is stated as a rule rather than a list so that a vendor added later inherits it; it is not a licence to build vendor-neutral machinery for one implementation.
- **Existing recorded categories are left exactly as they are** (FR-008). The taxonomy admin's rename already handles a value the operator wants to change, and a migration that guessed which recorded values came from a vendor would be guessing.
- **Four paths carry a vendor category toward a product today**: the order capture, the single-part capture page, enrichment of an already-matched product, and the Add Product form opened by a scan. All four are in scope; the fourth was found while planning and is FR-010.
- **The category field stays free-form.** Constraining it to a controlled vocabulary is a different feature and is not implied by this one.
