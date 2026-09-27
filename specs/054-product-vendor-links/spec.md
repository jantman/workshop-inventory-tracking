# Feature Specification: Vendor Links on the Product Page

**Feature Branch**: `robot-army/issue-180-clickable-links-for-products`

**Created**: 2026-09-27

**Status**: Draft

**Input**: GitHub issue #180, "Clickable links for products" — product pages should have
clickable links to the vendor's website, shown in the Details panel near the top of the
product view. Amazon: `https://www.amazon.com/dp/<VENDOR identifier>`. McMaster-Carr:
`https://www.mcmaster.com/<DISTRIBUTOR identifier>/`. DigiKey (unless the URL is already
captured): `https://www.digikey.com/en/products/result?keywords=<DISTRIBUTOR identifier>`,
which redirects to the product page.

## Background

A product already records its vendor item ids as vendor-scoped identifiers — an Amazon ASIN,
a McMaster-Carr part number, a DigiKey part number — each filed under the vendor it belongs
to. What the product page does not do is turn them into a way back to the vendor. To reorder,
check a datasheet or compare a listing, the operator copies the identifier out of the
Identifiers card and types it into the vendor's site by hand.

The one link the page offers today is the "Open listing" notice, which appears only for an
Amazon product that has no details yet, and disappears once it has them.

Two facts about the existing data shape this feature:

- **The identifier type is not uniform per vendor.** McMaster-Carr part numbers were recorded
  as `VENDOR` identifiers before feature 049 and as `DISTRIBUTOR` since; a DigiKey part
  captured from its product page is recorded as `VENDOR`, while one from an order or a bag
  label is `DISTRIBUTOR`. A link keyed on only the type the issue names would silently miss
  real products.
- **DigiKey's product page address is not stored.** The DigiKey lookup returns one, but
  nothing keeps it, so the keyword-search address the issue gives is what is available.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Open a product's vendor page from its Details panel (Priority: P1)

The operator is looking at a product that was bought from Amazon, McMaster-Carr or DigiKey.
In the Details panel they see a link naming the vendor, click it, and the vendor's page for
that item opens in a new tab, leaving the inventory page where it was.

**Why this priority**: This is the whole of the issue. Each of the three vendors is a slice
of it, but they share one place on the page and one behaviour, so they ship together.

**Independent Test**: Seed one product per vendor, each with its vendor identifier, open each
product page, and confirm the Details panel shows one link to the address the issue gives,
opening in a new tab.

**Acceptance Scenarios**:

1. **Given** a product with an Amazon identifier `B0EXAMPLE1`, **When** the operator opens
   its page, **Then** the Details panel shows a link labelled for Amazon to
   `https://www.amazon.com/dp/B0EXAMPLE1`.
2. **Given** a product with a McMaster-Carr identifier `91251A540`, **When** the operator opens
   its page, **Then** the Details panel shows a link labelled for McMaster-Carr to
   `https://www.mcmaster.com/91251A540/`.
3. **Given** a product with a DigiKey identifier `296-1395-5-ND`, **When** the operator opens
   its page, **Then** the Details panel shows a link labelled for DigiKey to
   `https://www.digikey.com/en/products/result?keywords=296-1395-5-ND`.
4. **Given** any of the above, **When** the operator clicks the link, **Then** the vendor's
   page opens in a new tab and the product page stays open.

---

### User Story 2 - A product from several vendors links to each (Priority: P2)

A part the operator has bought from both DigiKey and McMaster-Carr shows a link to each, so
they can compare or reorder from either without looking anything up.

**Why this priority**: Less common than a single vendor, but the natural consequence of a
product carrying identifiers from more than one vendor; showing only one would be arbitrary.

**Independent Test**: Seed a product carrying identifiers for two supported vendors and
confirm both links appear.

**Acceptance Scenarios**:

1. **Given** a product with a DigiKey and a McMaster-Carr identifier, **When** the operator
   opens its page, **Then** both links appear, each labelled with its vendor.

---

### Edge Cases

- **No supported vendor identifier** — a product with only an MPN, a barcode, or an
  identifier from a vendor with no known address pattern (Mouser, eBay, a hand-typed vendor):
  no vendor-link row is shown at all, rather than an empty one.
- **Either vendor-scoped type** — a McMaster-Carr or DigiKey part number recorded as a
  `VENDOR` identifier links exactly as one recorded as `DISTRIBUTOR` does, and likewise an
  Amazon ASIN recorded under either type.
- **The same vendor and value under both types** — produces one link, not two.
- **Two different identifiers for the same vendor** — each gets its own link, distinguished
  by the identifier shown with it.
- **Characters that are not address-safe** — an identifier containing a space, `/`, `#` or
  similar is encoded, so the link reaches the vendor with the identifier intact rather than
  a truncated or re-routed address.
- **Vendor name spelling** — only the vendor names the application itself files purchases
  and identifiers under are recognized. A legacy spelling such as `Digi-Key` is not linked;
  this feature does not rewrite existing rows.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The product page's Details panel MUST show a link to the vendor's page for each
  vendor-scoped identifier the product carries under Amazon, McMaster-Carr or DigiKey.
- **FR-002**: The link addresses MUST be, with `<id>` the identifier's value:
  Amazon `https://www.amazon.com/dp/<id>`; McMaster-Carr `https://www.mcmaster.com/<id>/`;
  DigiKey `https://www.digikey.com/en/products/result?keywords=<id>`.
- **FR-003**: Both vendor-scoped identifier types (`VENDOR` and `DISTRIBUTOR`) MUST produce a
  link for a supported vendor; the same vendor and value recorded under both types MUST
  produce a single link.
- **FR-004**: Each link MUST name its vendor and show the identifier it was built from, so
  two links for one vendor can be told apart.
- **FR-005**: Each link MUST open in a new browser tab without giving the opened page a handle
  on the inventory page.
- **FR-006**: The identifier MUST be encoded for its position in the address, so any value
  arrives at the vendor unchanged.
- **FR-007**: A product with no identifier for a supported vendor MUST show no vendor-link row.
- **FR-008**: Links MUST be derived from the identifiers at display time; nothing new is
  stored, and editing or removing an identifier changes the links on the next page load.
- **FR-009**: The existing "Open listing" notice for Amazon products without details MUST
  continue to behave as it does today.

### Key Entities

- **Product identifier** (existing): a coded name for a product, with a type and, for the two
  vendor-scoped types, the vendor it belongs to. The only input to this feature.
- **Vendor link** (derived, not stored): a vendor name, the identifier value, and the address
  built from them.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a product page, the operator reaches the vendor's page for that item in one
  click, with no copying or typing, for every product carrying an Amazon, McMaster-Carr or
  DigiKey identifier.
- **SC-002**: 100% of products carrying a supported vendor identifier — whichever of the two
  vendor-scoped types it was recorded as — show a link; 0% of products without one show an
  empty link row.
- **SC-003**: No stored data changes: the feature adds no migration and alters no existing
  record.

## Assumptions

- The three address patterns in the issue are correct and stable; if a vendor changes its
  addressing, the pattern is updated in one place.
- DigiKey's keyword-search address is used for every DigiKey identifier. Storing DigiKey's
  own product page address would need a new column and back-filling, which the issue does not
  ask for and which the search address makes unnecessary.
- Other vendors (Mouser, eBay, AliExpress, hand-typed vendors) are out of scope; adding one
  later is adding one address pattern.
- Links go on the product detail page only, not the product list, search results or order
  screens.
- A link is offered whether or not the listing still exists at the vendor; the application
  does not check.
