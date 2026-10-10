# Feature Specification: Bulk Set Category

**Feature Branch**: `robot-army/issue-201-add-support-for-bulk-category-setting`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Issue #201: Add support for bulk category setting on products and order pages. The products page (`/products`) and captured order page (`/products/orders/<Vendor>/<order number>`) currently support selection of multiple orders for the purposes of printing labels (as well as on the order page, for receiving items). The new Outstanding Orders page (created from #200) also has this functionality. On all of these pages, add an option to select multiple items and then set a Category for them (same category for all selected items). The resulting modal for this should auto-complete product categories the way the Edit Product page does. Once submitted and the updates are complete, the current selection should be cleared."

## Background

Three pages already let the owner tick several rows and act on all of them at once:

- **Products** (`/products`): one row per product, with a Print Labels action.
- **An order's page** (`/products/orders/<vendor>/<order number>`): one row per purchase line,
  with Print Labels and Receive Selected actions.
- **Outstanding Products**: one row per purchase line that has not been received, from every
  order, with the same two actions as an order's page.

Today a category can only be set one product at a time, from Edit Product. A newly captured
order often brings in several products that belong in the same category, and each one has to
be opened, edited and saved separately.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Set one category on several products from the products list (Priority: P1)

The owner filters or browses **Products** and ticks several products. They choose **Set
Category**, and a dialog opens with a single category field. That field suggests existing
categories as they type, exactly as Edit Product's Category field does. They enter
`electronics/passives/resistors` and confirm. Every ticked product now has that category, the
list shows the new category in each of those rows, and nothing is ticked any more.

**Why this priority**: This is the most general page, since it reaches every product, and it
is the simplest form of the feature. It is useful on its own.

**Independent Test**: Seed three products with different categories (one with none). Tick two,
set the category `tools/hand`, and confirm. Those two products carry `tools/hand`, the third is
unchanged, the Category column shows the new value for the two, and no checkbox is ticked.

**Acceptance Scenarios**:

1. **Given** three products on the list, **When** the owner ticks two of them, chooses Set
   Category, enters `tools/hand` and confirms, **Then** both products carry `tools/hand`, the
   unticked product keeps its category, and a message says how many products were updated.
2. **Given** the dialog is open, **When** the owner types the start of an existing category,
   **Then** existing categories are offered as suggestions, the same ones Edit Product offers.
3. **Given** the owner enters a category that no product has yet, **When** they confirm,
   **Then** it is accepted and becomes a category, just as typing a new category on Edit
   Product does.
4. **Given** the owner enters `Tools / Hand ` with odd case and spacing, **When** they
   confirm, **Then** the products carry the same normalized category Edit Product would
   save for that input (`tools/hand`).
5. **Given** the update has completed, **When** the page is shown again, **Then** no product
   is ticked, the selection count reads zero, and the bulk actions are disabled.
6. **Given** no product is ticked, **When** the owner looks at the Set Category action,
   **Then** it is disabled.

---

### User Story 2 - Set a category on the products of an order's lines (Priority: P1)

After capturing an order, the owner opens its page, ticks the lines whose products belong
together, chooses **Set Category**, enters a category (with the same suggestions), and
confirms. The product on each ticked line gets that category, and the selection is cleared.

**Why this priority**: The issue names the order page explicitly. It is where new products
first appear, so it is where categorizing them in a batch saves the most time.

**Independent Test**: Seed an order with three lines for three different products. Tick two
lines and set the category `fasteners/screws`. The two lines' products carry it, the third
product does not, and no line is ticked afterwards.

**Acceptance Scenarios**:

1. **Given** an order with three lines, **When** the owner ticks two and sets a category,
   **Then** the products of those two lines carry it and the third line's product is unchanged.
2. **Given** two ticked lines that name the same product, **When** a category is set, **Then**
   that product is updated once, and the message counts it as one product.
3. **Given** ticked lines, some received and some not, **When** a category is set, **Then**
   every ticked line's product is updated, and no line's received state, quantity or date
   changes.
4. **Given** the update has completed, **When** the page is shown again, **Then** no line is
   ticked and the order's other actions (Print Labels, Receive Selected) are disabled until
   something is ticked again.

---

### User Story 3 - Set a category from Outstanding Products (Priority: P2)

On **Outstanding Products** the owner ticks lines from several orders and sets one category on
their products in the same way. The selection is cleared afterwards.

**Why this priority**: The behavior is the same as on an order's page, and that page's toolbar
is already shared with this one, so this story adds coverage rather than new behavior.

**Independent Test**: Seed two orders with outstanding lines. Tick one line from each and set a
category. Both products carry it, both lines are still listed as outstanding, and nothing is
ticked.

**Acceptance Scenarios**:

1. **Given** outstanding lines from two orders, **When** the owner ticks one from each and
   sets a category, **Then** both lines' products carry it and both lines remain outstanding.
2. **Given** the update has completed, **When** the page is shown again, **Then** no line is
   ticked.

---

### Edge Cases

- **Blank category**: confirming with an empty or whitespace-only category is refused with a
  message, and nothing changes. This action sets a category; it does not clear one (see
  Assumptions).
- **Over-long category**: a category longer than the limit Edit Product enforces is refused
  with the same message Edit Product gives, and no product is changed.
- **A ticked product no longer exists** (deleted in another tab between page load and
  confirm): the whole update is refused with a message naming the problem, and no product
  is changed. The owner reloads and tries again.
- **Cancelling the dialog**: nothing changes, and the selection is kept so the owner can pick
  another action.
- **Failure of any kind**: nothing is changed (all or nothing), an error is shown, and the
  selection is kept so the owner can retry without ticking everything again.
- **Products list filtered by category**: once a product's category changes, it may no longer
  match the filter. Showing the page again with the same filter drops it from the list, which
  is correct, because the list shows what matches.
- **Lines with no product**: they already have no checkbox, so they cannot be selected.
- **The product already has that category**: it is still counted as updated and stays as it
  is. This is harmless.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Products list, every order page and Outstanding Products MUST each offer a
  **Set Category** action alongside their existing bulk actions. It acts on the rows currently
  ticked.
- **FR-002**: Set Category MUST be disabled while nothing is ticked and enabled whenever at
  least one row is ticked, in step with the existing bulk actions on that page.
- **FR-003**: Choosing Set Category MUST open a dialog that says how many products will be
  changed and contains a single category input.
- **FR-004**: The dialog's category input MUST suggest existing categories as the owner types,
  using the same source and behavior as Edit Product's Category field, and MUST accept a
  category that does not exist yet.
- **FR-005**: On confirmation, every distinct product behind the ticked rows MUST be given the
  entered category. On order and outstanding pages, the product is the one each ticked line
  names, and a product named by several ticked lines is updated once.
- **FR-006**: The entered category MUST be normalized and validated exactly as Edit Product
  does it. Input that Edit Product would store as "no category" (blank) MUST be refused
  instead of clearing the category.
- **FR-007**: The update MUST be all or nothing. If any selected product cannot be updated,
  no product is changed and the owner is told why.
- **FR-008**: Setting a category MUST change only the product's category. Nothing else about
  the products, their purchases, or receipt state may change.
- **FR-009**: After a successful update, the owner MUST see a confirmation stating how many
  products were updated, and the page MUST show no rows ticked, a selection count of zero,
  and all bulk actions disabled.
- **FR-010**: After a successful update on the Products list, the Category column MUST show
  the new category for the updated products, and the list MUST keep the filters it had.
- **FR-011**: After a failed or cancelled update, the selection MUST be preserved.

### Key Entities

- **Product**: the catalog record whose category is set. Its category is a slash-separated
  path, normalized in one place shared with Edit Product.
- **Purchase line**: a row on an order or Outstanding Products. It names at most one product.
  Ticking it selects that product. The line itself is not changed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The owner can give one category to any number of products shown on one of the
  three pages with a single dialog and one confirmation. Before this feature, that took one
  edit-and-save round trip per product.
- **SC-002**: A category set in bulk is indistinguishable from the same text saved through
  Edit Product, so the two produce the same stored value for every input.
- **SC-003**: After 100% of successful updates the selection is empty. After 100% of failed or
  cancelled updates it is unchanged.
- **SC-004**: An update that fails part-way leaves zero products changed.

## Assumptions

- **Clearing categories is out of scope.** The issue asks to *set* a category, and a blank
  entry is more likely a slip than an intent to wipe the category from many products at once.
  Clearing stays a per-product action on Edit Product.
- "Select multiple items" on the order and outstanding pages means ticking purchase lines,
  which is the selection those pages already have. The category belongs to the product, so
  the product on each ticked line is what changes.
- The existing checkboxes and select-all box on each page are reused. There is no separate
  selection for this action.
- The order page and Outstanding Products do not display category, so on those pages the
  confirmation message and cleared selection are the visible result.
- Reaching the result by showing the page again (which clears the selection and shows fresh
  values) satisfies "the current selection should be cleared".
