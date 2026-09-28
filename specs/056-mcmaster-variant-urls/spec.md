# Feature Specification: Capture McMaster Variant Product Pages

**Feature Branch**: `robot-army/issue-184-mcmaster-page-capturing-bug`

**Created**: 2026-09-28

**Status**: Draft

**Input**: GitHub issue #184, "McMaster page capturing bug"

## Background

Some McMaster-Carr products come in variants chosen on the product page — part `3408A521`
is a spring plunger offered with or without threadlocker. Until a variant is chosen the
page is incomplete: in the reported case it showed no 2-D drawing, so a capture of it
recorded none.

Choosing a variant changes the address from `/3408A521/` to `/3408A521-3408A523/` — two
part numbers joined by a hyphen. The capture extension recognizes a McMaster product page
only by an address naming exactly one part number, so on the variant page — the very page
the owner had to reach to see the drawing — it refuses with "this is not a page it can
read".

Observed on the live page on 2026-09-28: at `/3408A521-3408A523/` with "Threadlocker"
chosen, the page renders the product normally — title, price, specification table, the
2-D drawing picker — and names its part number as **3408A521**, the first of the two in
the address.

The paste-a-URL form on the application's own capture page reads a part number out of a
McMaster address with the same rule, and has the same gap.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Capture a McMaster product after choosing its variant (Priority: P1)

The owner is on a McMaster product page, chooses a variant, and captures the page with the
extension. The capture reads the page exactly as it reads any other McMaster product page:
title, price, photos, specification rows and the 2-D drawing, under the part number the
page names.

**Why this priority**: This is the reported defect, and choosing the variant is the only
way to get a complete page — including its drawing — for such a product.

**Independent Test**: Serve a McMaster product page fixture at a two-part-number address
and capture it; the confirmation page opens with the part number, title, price and
drawing filled in.

**Acceptance Scenarios**:

1. **Given** the owner is on `/3408A521-3408A523/`, **When** they capture the page,
   **Then** no "this is not a page it can read" message appears and the confirmation page
   opens with the listing read from the page.
2. **Given** that page names `3408A521` as its part number, **When** it is captured,
   **Then** the capture's part number is `3408A521`.
3. **Given** the page names neither of the address's part numbers (or names none the
   capture can read), **When** it is captured, **Then** the capture's part number is the
   first part number in the address.
4. **Given** the variant page shows a 2-D drawing, **When** it is captured, **Then** the
   drawing is attached as it is for a single-part-number page.

---

### User Story 2 - Paste a variant address into the capture form (Priority: P2)

The owner pastes a two-part-number McMaster address into the application's own capture
form, with no extension involved. The part number is prefilled from the address.

**Why this priority**: The same rule lives on both sides; fixing one leaves the owner with
a form that disagrees with the extension about the same address.

**Independent Test**: Submit the capture form with `https://www.mcmaster.com/3408A521-3408A523/`;
the vendor is McMaster-Carr and the part number is `3408A521`.

**Acceptance Scenarios**:

1. **Given** a pasted `/3408A521-3408A523/` address, **When** the form reads it, **Then**
   the part number prefilled is `3408A521`.

---

### Edge Cases

- A single-part-number address behaves exactly as before, for both the extension and the
  form.
- Addresses that are not a product page still are not: the family table
  (`/products/<part>/`), the order list, an order, the site root. A path with a hyphen that
  is not two part numbers (e.g. a trailing hyphen, three part numbers, lower-case) is not a
  product page.
- The page names a part number that is not one of the two in the address: the address's
  first part number is used, so the recorded part number is always one the address names.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The extension MUST recognize an address whose path is two McMaster part
  numbers joined by a single hyphen (`/<part>-<part>/`) as a McMaster product page, and
  read it with the McMaster product reader.
- **FR-002**: For such a page the captured part number MUST be the part number the page
  displays for the chosen product when that is one of the address's two part numbers, and
  otherwise the address's first part number.
- **FR-003**: A single-part-number address MUST keep today's behavior unchanged: its part
  number comes from the address.
- **FR-004**: The application's paste-a-URL form MUST read the first part number from a
  two-part-number McMaster address.
- **FR-005**: Every address that is not a product page today MUST remain not a product page.

### Key Entities

- **McMaster product address**: `/<part>/` or, after a variant is chosen,
  `/<part>-<part>/`. A part number is digits, an upper-case letter, then alphanumerics.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Capturing a McMaster product page reached by choosing a variant succeeds and
  records the part number the page shows, on the first attempt.
- **SC-002**: Every existing McMaster and Amazon capture test passes unchanged.

## Assumptions

- The first half of the issue — the drawing missing from `/3408A521/` before a variant was
  chosen — is the page not showing one, which the owner identified themselves. Being able to
  capture the variant page is the fix; no warning about an unchosen variant is added.
- McMaster's own convention for which of the two numbers is "the" product is not
  documented. The page's displayed part number is the authority where it can be read; the
  address's first part number (which matched it on the one live page observed) is the
  fallback.
