# Feature Specification: Capture Product PDFs

**Feature Branch**: `robot-army/issue-173-mcmaster-not-capturing-all-media`

**Created**: 2026-09-27

**Status**: Draft

**Input**: GitHub issue #173, "McMaster not capturing all media" — capturing a product should
capture the PDFs on its product page as well as its images, for McMaster-Carr and Amazon
alike. Validate with McMaster part `91074A329`, whose page offers a single-page 2-D PDF
drawing of the washer.

## Background

Capturing a product page from the browser extension today brings across the listing's
photographs and line-drawing images and nothing else. Product pages carry documents too:

- **McMaster-Carr** offers each part's CAD files from a "CAD file type" picker. One of the
  choices is a **2-D PDF** — a dimensioned, single-page drawing of the part, which is the
  most useful reference a machinist can keep beside the stock. The others are 3-D models
  and 2-D formats for CAD programs (STEP, SolidWorks, DWG, DXF, a 3-D PDF, …).
  **McMaster serves these files only to a browser holding a McMaster session**: the same
  address that returns the PDF inside the owner's browser is refused when the application
  asks for it directly. (Checked on 2026-09-27 against `91074A329`: 200 with the session,
  403 without.)
- **Amazon** lists manuals, user guides and warranty statements as PDF links under
  "Product guides and documents" and in the product-details tables. These are public
  addresses the application can already retrieve.

The application already stores PDFs as product attachments — a DigiKey datasheet arrives
that way — with a preview of the first page. What is missing is the capture reading them
off the page.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A McMaster capture keeps the part's 2-D drawing (Priority: P1)

The owner captures a McMaster-Carr product page. Alongside the part's photographs, the
product in the inventory now holds the part's 2-D PDF drawing, so the dimensions are to
hand without going back to mcmaster.com.

**Why this priority**: This is the reported defect, and McMaster's drawing cannot be
fetched any other way once the page is closed — the application cannot retrieve it on its
own.

**Independent Test**: Capture McMaster part `91074A329` and confirm. The product's
attachments include a one-page PDF drawing of the washer, next to its images.

**Acceptance Scenarios**:

1. **Given** the owner is on a McMaster product page that offers a 2-D PDF drawing,
   **When** they capture it and confirm, **Then** the product gains that drawing as a PDF
   attachment in addition to the images it gained before this feature.
2. **Given** the same capture, **When** the owner confirms "add the listing's details, record
   no purchase" onto an existing product (features 044/049), **Then** the drawing is attached
   there too.
3. **Given** a McMaster product page that offers no CAD files at all, **When** the owner
   captures it, **Then** the capture behaves exactly as it does today.
4. **Given** the page's CAD picker currently shows some other format (for example a 3-D
   PDF, remembered from an earlier visit), **When** the owner captures it, **Then** the
   2-D PDF is still the one captured, and the picker is left showing what it showed before.

---

### User Story 2 - An Amazon capture keeps the listing's documents (Priority: P2)

The owner captures an Amazon listing that offers a user manual as a PDF. The product gains
the manual as an attachment beside its gallery images.

**Why this priority**: The issue asks for it explicitly, and a tool's manual is exactly the
document that goes missing when it's needed. Lower than P1 only because an Amazon manual
stays retrievable from its public address, while McMaster's drawing does not.

**Independent Test**: Capture an Amazon listing with a "Product guides and documents" PDF.
The product's attachments include that PDF.

**Acceptance Scenarios**:

1. **Given** an Amazon listing that links one or more PDFs, **When** the owner captures and
   confirms it, **Then** each distinct PDF is attached to the product once.
2. **Given** an Amazon *order* capture whose lines' listings are read (feature 044), **When**
   a line's listing links a PDF, **Then** that PDF is attached to the line's product the same
   way its images are.
3. **Given** a listing whose only PDF links sit inside a "customers also viewed" style
   carousel, **When** it is captured, **Then** those PDFs are not attached — they describe
   other products.

---

### Edge Cases

- The McMaster drawing cannot be read (the picker changed shape, the download was refused,
  the session lapsed): the rest of the capture proceeds and the images still arrive — a
  missing drawing never costs the capture.
- A PDF over the existing attachment size limit, or one the vendor answers with something
  that is not a PDF, is skipped and reported the way an oversized or unsupported image is
  reported today.
- The same PDF linked twice on one page (Amazon repeats its documents in a quick-view
  overlay) is attached once.
- Capturing the same product page again does not attach the drawing a second time — the
  existing "already stored" check applies to PDFs as it does to images.
- The product's attachment cap still applies; a PDF counts toward it like an image.
- McMaster's other CAD formats (3-D PDF, STEP, DWG, DXF, SolidWorks, …) are not captured.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Capturing a McMaster-Carr product page MUST bring across the part's 2-D PDF
  drawing when the page offers one, regardless of which CAD format the page's picker is
  currently showing.
- **FR-002**: The McMaster drawing MUST be read using the owner's own browser session, since
  McMaster refuses the file to anything else; the application MUST NOT need a McMaster
  account or credentials of its own.
- **FR-003**: Reading the drawing MUST leave the McMaster page as the owner had it — any
  control the capture opens to find the drawing is closed again, and no CAD format is
  selected on the owner's behalf.
- **FR-004**: Capturing an Amazon listing MUST bring across every distinct PDF the listing
  links to, other than those inside cross-sell regions that already exclude images.
- **FR-005**: Captured PDFs MUST be stored as product attachments through the same path as
  captured images, and so inherit its size limit, type check, duplicate detection,
  per-product cap and per-file failure reporting.
- **FR-006**: A PDF that cannot be read or stored MUST cost that PDF alone; the capture,
  its purchase, its specifications and its images proceed.
- **FR-007**: The message shown after a capture MUST say how many PDFs were stored,
  separately from the images, so the owner can tell whether the drawing arrived.
- **FR-008**: Only 2-D PDF drawings are captured from McMaster; other CAD formats are not.
- **FR-009**: Pages with no PDFs MUST capture exactly as they did before this feature.

### Key Entities

- **Captured document**: a PDF read off a vendor's product page, carried with the listing's
  images and stored as a product attachment. It has no record of its own beyond the
  attachment.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Capturing McMaster part `91074A329` leaves its product with exactly one PDF
  attachment, a single-page drawing of the washer.
- **SC-002**: Capturing an Amazon listing that links N distinct product PDFs leaves its
  product with N PDF attachments.
- **SC-003**: Capturing the same page twice attaches no additional copies.
- **SC-004**: A capture whose PDF cannot be retrieved still records the purchase and stores
  every image it stored before this feature.

## Assumptions

- "PDFs from the product page" on McMaster means the 2-D PDF drawing. The 3-D PDF is an
  interactive model most viewers cannot render and whose first page previews poorly, and
  the issue's validation case names a single-page drawing.
- On Amazon, every PDF link on the listing outside cross-sell regions is product
  documentation (manual, user guide, warranty); no finer choice is needed.
- McMaster drawings are small (the validation drawing is about 100 KB), well inside the
  existing attachment size limit and form size limit.
- The confirmation page's summary count may count PDFs among the files to be stored; only
  the post-capture tally distinguishes them (FR-007). Changing the confirmation page's
  wording is not needed to meet the issue.
