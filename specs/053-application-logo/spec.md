# Feature Specification: Application Logo

**Feature Branch**: `robot-army/issue-169-design-a-logo-for-the-application-and`

**Created**: 2026-09-27

**Status**: Draft

**Input**: GitHub issue #169, "Design a logo for the application, and use it for the UI,
favicon and extension icon" — the application has no mark of its own. The navbar borrows a
generic glyph, there is no favicon at all, and the capture extension ships a placeholder that
reads as "download". Design one logo and use it in all three places.

## Background

Three places currently improvise a mark:

- **The navbar** shows a generic toolbox glyph from the icon font (the same glyph also heads
  the home page's banner).
- **There is no favicon.** No page declares one and no image is served for it, so the browser
  tab shows a blank page icon, and a bookmark to the application is indistinguishable from
  any other.
- **The capture extension** (feature 048) ships a placeholder drawn for issue #133 — a
  download arrow into a tray, at 16/48/128 px. It is a generic inbox glyph; next to other
  extensions in the toolbar it reads as "download", not as this application.

The issue was raised while installing the extension for the first time, but the underlying gap
is that there is no logo to use anywhere.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The browser tab shows the application's logo (Priority: P1)

The operator has several tabs open. The application's tab shows its logo instead of a blank
page icon, so it can be found at a glance, and a bookmark to it carries the same logo.

**Why this priority**: The favicon is the one place that has nothing at all today, and the
16 px tab icon is the hardest size for the logo to work at — if it works there, it works
everywhere.

**Independent Test**: Load any page of the application. The page declares an icon, the icon
is served successfully, and it is the logo.

**Acceptance Scenarios**:

1. **Given** any page of the application, **When** it loads, **Then** the page declares an
   icon and the browser can fetch it successfully.
2. **Given** the tab icon rendered at 16 px, **When** the operator looks at it, **Then** the
   logo's shape is recognizable — it is not a smudge and not a generic glyph.

---

### User Story 2 - The extension's toolbar icon is the application's logo (Priority: P2)

The operator installs (or re-installs) the capture extension. Its toolbar icon and its entry
on the browser's extensions page show the same logo as the application's tab, so the
operator can tell at a glance which toolbar button captures into the inventory.

**Why this priority**: This is the case that prompted the issue. It is second only because
it needs a manual re-install to reach the operator, whereas the favicon arrives with the
application.

**Independent Test**: Load the extension from the repository. Its icons at 16, 48 and 128 px
are the logo, and each file is the size the extension declares.

**Acceptance Scenarios**:

1. **Given** the extension loaded from the repository, **When** the operator looks at the
   toolbar, **Then** the icon is the application's logo, not the download-arrow placeholder.
2. **Given** each extension icon, **When** its pixel size is checked, **Then** it matches the
   size it is declared at (16, 48, 128).

---

### User Story 3 - The navbar shows the logo (Priority: P3)

Every page's navbar shows the logo beside the application's name, in place of the borrowed
toolbox glyph, so the application's own pages carry the same mark as its tab and its
extension.

**Why this priority**: The navbar already has a serviceable mark; replacing it is about
consistency rather than a gap.

**Independent Test**: Load any page. The navbar brand shows the logo image and no longer
shows the toolbox glyph; the brand still links home.

**Acceptance Scenarios**:

1. **Given** any page, **When** it renders, **Then** the navbar brand shows the logo beside
   "Workshop Inventory" and still links to the home page.
2. **Given** a narrow (phone-width) window, **When** the navbar renders, **Then** the logo is
   still shown at a legible size beside the name and does not break the navbar layout.

---

### Edge Cases

- **The logo on the navbar's own blue.** The navbar is the application's primary blue; the
  logo must remain distinguishable on it, not vanish into it.
- **Light and dark browser chrome.** The tab strip may be light or dark; the favicon must be
  recognizable on both. The same applies to a light or dark browser toolbar for the extension.
- **The home page's banner** uses the same borrowed glyph in its heading. It is replaced by
  the logo too, so the application never shows two different marks on one page.
- **An extension installed before this change** keeps the placeholder until the operator
  reloads or re-installs it; the application cannot update it (048 FR-026). The logo is
  delivered in the same change as the application's, and the extension documentation tells
  the operator to reload.
- **A browser that requests the conventional root icon path** without reading the page's
  declaration still gets the logo rather than an error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST contain one master logo, as an editable vector asset
  checked in by hand — not generated at build time by a script. Every other logo image in
  the repository MUST be derived from it.
- **FR-002**: The logo MUST be recognizable at 16 × 16 px as well as at 128 px: a simple,
  bold shape with no fine detail or text that disappears at small sizes.
- **FR-003**: The logo MUST read as this application — workshop materials and their
  inventory — and MUST NOT be a stock glyph from the icon font the UI already uses.
- **FR-004**: Every application page MUST declare a favicon, and the application MUST serve
  it successfully. A request for the conventional root icon path MUST also return the logo.
- **FR-005**: The navbar brand MUST show the logo in place of the toolbox glyph, beside the
  existing name, and MUST keep linking to the home page. The home page banner's heading MUST
  show the logo in place of the same glyph.
- **FR-006**: The extension's icons at 16, 48 and 128 px MUST be replaced with the logo, each
  exactly the size it is declared at. The extension's declared icon paths need not change.
- **FR-007**: The logo MUST remain distinguishable on the navbar's primary blue, on a white
  background, and on a dark background.
- **FR-008**: The extension documentation MUST tell an operator who installed the extension
  earlier that the new icon arrives only when they reload the extension.
- **FR-009**: Documentation screenshots MUST be regenerated to show the new navbar, and only
  screenshots whose content actually changed are committed.

### Key Entities

- **Logo**: the one master vector image, and the fixed-size raster copies derived from it for
  the favicon and the extension.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of application pages show the logo in the browser tab (zero pages fall
  back to the blank page icon).
- **SC-002**: The logo appears in all four places — tab, navbar, home banner, extension
  toolbar — and no generic glyph or placeholder remains in any of them.
- **SC-003**: At 16 px the logo is identifiable by eye next to other tabs and extensions,
  confirmed by viewing the rendered 16 px image.
- **SC-004**: An operator who reloads the extension sees the new icon with no other steps.

## Assumptions

- The logo is designed as part of this work; the issue asks for one without prescribing its
  form. Its motif is chosen in planning, within FR-002/FR-003's constraints.
- The logo is used at the brand's existing size in the navbar; no other page layout changes.
- The raster copies are generated once from the master and committed. They are real files in
  the repository, not produced at build or run time.
- An extension that predates this change keeps working exactly as before; only its icon is
  stale until reloaded. No version bump is required for the icon to change on reload.
