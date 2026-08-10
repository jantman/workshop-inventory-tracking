# Feature Specification: Product Catalog Documentation Overhaul

**Feature Branch**: `011-catalog-docs-overhaul`

**Created**: 2026-08-10

**Status**: Draft

**Input**: User description: "issue #53 on this repo" — GitHub issue #53, *11b. Product Catalog Documentation Overhaul*:

> 1. Right now there is a dedicated "Product Catalogue" section in `docs/user-manual.md`. This makes the Product Catalog feel like a bolted-on addition, with all of its documentation jammed into one section in the user manual. Rework the user manual so the Product Catalog feels like more of a top-tier functionality on par with inventory tracking.
> 2. Prefer the American spelling "Catalog" not the British "Catalogue". Fix this everywhere it appears in documentation and also add a reminder about this to CLAUDE.md.
> 3. Update the README to ensure that it mentions the Catalog as well.
> 4. Include relevant screenshots for the Catalog, auto-generating them in the same fashion as the existing ones.

## Context

The application has grown two halves. **Inventory** tracks physical metal stock by JA ID —
adding, moving, shortening, photographing, searching. **The product catalog** answers a
different question: what a part is, what it cost, and where it came from — products,
identifiers, scanning, purchases, order capture, reorder lists, categories and tags,
attachments.

The documentation has not caught up. All catalog material sits inside a single section,
`## Product Catalogue`, roughly one fifth of the way through a manual whose other twelve
top-level sections are all about inventory. Its subsections carry the weight of top-level
topics — *Scanning*, *Recording Purchases*, *Labels*, *Finding Things* — but are nested one
level deeper than the equivalent inventory topics, and the table of contents shows the
catalog as one line among thirteen. The README's feature list and its documentation links
do not mention the catalog at all. The eleven user-manual screenshots are all of inventory
screens; not one catalog screen is pictured.

The result is that a reader who wants to use the catalog cannot see from the contents page
that it exists as a peer capability, and a reader who arrives via the README does not learn
it exists at all.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The catalog reads as a peer of inventory (Priority: P1)

A reader opens the user manual, looks at the table of contents, and can see at a glance
that this application does two things: it tracks metal stock, and it catalogs the products
you buy. Catalog topics — adding a product, scanning, purchases and orders, stock levels
and reordering, organizing by category and tag — are presented at the same structural level
as the equivalent inventory topics, so finding "how do I record a purchase" takes the same
kind of scan down the contents as finding "how do I move an item".

**Why this priority**: This is the substance of the issue. The spelling fix, the README
line and the screenshots are all worth having on their own, but the structural problem is
the one the reader actually trips over, and it is the one the other three points support.

**Independent Test**: Read the reworked manual's table of contents cold and, without
scrolling into the body, name the catalog's major capabilities and the section each is
documented in. Confirm every heading link in the contents resolves to a heading that
exists.

**Acceptance Scenarios**:

1. **Given** the reworked user manual, **When** a reader looks only at the table of
   contents, **Then** the catalog's major capabilities are visible as top-level entries
   rather than as sub-entries of a single catalog section.
2. **Given** the reworked user manual, **When** a reader follows any link in the table of
   contents, **Then** it resolves to a heading that exists in the document.
3. **Given** the pre-existing catalog guidance (identifiers, barcode normalization, the
   2D-label and bookmarklet caveats, three-state quantity, count and flag ages, rename
   rules, the shared vocabulary), **When** the reworked manual is compared against the
   current one, **Then** every one of those facts is still documented somewhere — the
   rework moves and re-levels prose, it does not drop guidance.
4. **Given** an existing external link or bookmark into a renamed catalog heading anchor,
   **When** the rework changes that anchor, **Then** the change is deliberate and every
   in-repository reference to the old anchor has been updated to match.

---

### User Story 2 - The README says the application has a catalog (Priority: P2)

Someone landing on the repository for the first time reads the README and learns that this
application catalogs the products you buy, not only the metal stock you cut. The feature
list names the catalog's capabilities alongside the inventory ones, and the documentation
links point at the catalog guidance.

**Why this priority**: The README is the front door and currently gives no hint the catalog
exists. It is a small change with outsized reach, and it depends on nothing else in this
feature except the eventual heading names.

**Independent Test**: Read the README alone, with no other file open, and answer "does this
application track what I purchased and what it cost?" and "where do I read more about it?"

**Acceptance Scenarios**:

1. **Given** the README, **When** a first-time reader reads the Features list, **Then** the
   product catalog's capabilities appear there.
2. **Given** the README, **When** a reader follows the documentation links, **Then** at
   least one of them leads to the catalog guidance.
3. **Given** the README, **When** a reader looks at its screenshots, **Then** the catalog is
   pictured as well as the inventory list.

---

### User Story 3 - The catalog is pictured, and the pictures regenerate themselves (Priority: P2)

The catalog guidance carries screenshots of the actual screens, produced by the same
automated generation the inventory screenshots use — so a later UI change is one
regeneration command away from correct documentation, not a manual re-capture.

**Why this priority**: Screenshots make the catalog feel like a first-class feature in a way
prose cannot, and the generation infrastructure already exists. It is P2 rather than P1
because the manual is usable, if plainer, without them.

**Independent Test**: Delete the new catalog screenshot files, run the screenshot generation
session, and confirm the identical files reappear and pass the quality verification.

**Acceptance Scenarios**:

1. **Given** the screenshot generation session, **When** it is run from a clean checkout,
   **Then** it produces the new catalog screenshots alongside the existing ones without
   manual steps.
2. **Given** the generated catalog screenshots, **When** the quality verification session is
   run, **Then** every one of them passes the project's existing size, format and color-mode
   checks.
3. **Given** the reworked manual, **When** a reader reaches a documented catalog screen,
   **Then** a screenshot of that screen is embedded near the prose describing it, with a
   caption.
4. **Given** the standard test session, **When** it is run, **Then** it does not execute the
   new screenshot tests and leaves the working tree clean.
5. **Given** the screenshot inventory documents that list what is generated, **When** the new
   screenshots are added, **Then** those documents list them too and their counts are
   correct.

---

### User Story 4 - One spelling, and it stays that way (Priority: P3)

The repository says "catalog", never "catalogue" — in the documentation, on the screens the
application renders, and in the comments and docstrings a contributor reads. A note in the
project's contributor instructions keeps it that way for work that comes later. The frozen
records under `specs/` and `migrations/` keep their original wording.

**Why this priority**: It is a real inconsistency and individually cheap to fix, but nothing
in the manual is unusable because of it. It is last because doing it before the restructuring
would mean touching the same prose twice.

**Independent Test**: Search the in-scope tree for the British spelling and get no hits;
search `specs/` and still get hits; read the contributor instructions and find the rule and
its exclusions stated.

**Acceptance Scenarios**:

1. **Given** the in-scope tree, **When** it is searched case-insensitively for "catalogue",
   **Then** there are no matches.
2. **Given** `specs/` and `migrations/`, **When** they are searched the same way, **Then**
   matches remain — the historical record was not rewritten.
3. **Given** the contributor instructions file, **When** a contributor reads it, **Then** the
   American-spelling rule and its exclusions are stated plainly enough to follow without
   further explanation.
4. **Given** a spelling change inside a documented heading, **When** the heading's anchor
   changes as a result, **Then** every reference to that anchor is updated in the same
   change.
5. **Given** the identifier renames, **When** both test suites are run, **Then** they pass and
   collect the same number of tests as before.

---

### Edge Cases

- **Frozen historical artifacts.** Files under `specs/` are the record of what was specified
  at the time and are not live documentation; rewriting them would falsify that record. They
  are out of scope for the spelling fix, and so are Alembic revision docstrings, which
  describe a migration as it shipped.
- **Anchors that break silently.** A markdown heading link that no longer resolves renders as
  ordinary text and fails no build. Renaming or re-leveling headings requires every reference
  to be re-checked, including references from other documents.
- **Screenshots of screens that need data.** A product page with no purchases, a reorder list
  with nothing to reorder, and a category tree with one entry all picture the feature
  badly. Catalog screenshots need seeded data representative enough to show what the screen
  is for.
- **Screenshot tests are not e2e tests.** Adding catalog screenshot tests must not lengthen
  or dirty the standard e2e run; that run excludes screenshot tests and must keep leaving the
  working tree clean.
- **A screenshot over the size limit.** The project enforces a per-image size ceiling. A
  full-page capture of a long product page may exceed it and must be framed or captured
  differently rather than having the limit raised.
- **"Catalogue" as part of a sentence about something else.** Occurrences inside prose that
  is not about the product catalog (if any) still get the American spelling; the rule is
  about spelling, not about the noun's referent.
- **A rename that silently drops a test.** A pytest function renamed wrongly, or a fixture
  renamed at its definition but not at one of its 71 call sites, fails loudly. But a test
  renamed into a name that no longer starts with `test_` is simply not collected, and the
  suite still passes — with less in it. Test *counts* before and after are the check that
  catches this, not a green run.
- **`uncatalogued` is not a plain substitution.** At least one identifier embeds the word as
  a prefix (`test_an_uncatalogued_barcode_...`). A blind `catalogue`→`catalog` replacement
  yields `uncatalogd`; the American form is `uncataloged`.

## Requirements *(mandatory)*

### Functional Requirements

**Manual restructuring**

- **FR-001**: The catalog guidance MUST remain in `docs/user-manual.md`. It MUST NOT be split
  into a separate manual.
- **FR-002**: The user manual MUST present the product catalog's major capabilities as
  top-level sections, at the same heading level as the equivalent inventory capabilities,
  rather than nested beneath a single `## Product Catalogue` section.
- **FR-003**: The user manual's table of contents MUST reflect that structure and MUST group
  its entries so a reader can see the application's two halves — inventory and catalog — and
  identify each half's capabilities without reading the body.
- **FR-004**: The rework MUST preserve every substantive fact in the existing catalog
  guidance. Prose MAY be re-levelled, re-ordered, re-titled and re-worded; guidance MUST NOT
  be dropped.
- **FR-005**: The manual MUST make plain, near its top, that the application has two halves —
  inventory of physical stock and a catalog of products purchased — and what distinguishes
  them.
- **FR-006**: Every table-of-contents entry and every intra-document heading link in the
  reworked manual MUST resolve to a heading that exists.
- **FR-007**: Every reference from another in-repository document to a catalog heading anchor
  MUST be updated to match any anchor this rework changes.

**Spelling**

- **FR-008**: Documentation MUST use the American spelling "catalog" (and its inflections:
  catalogs, cataloged, cataloging) and MUST NOT contain the British "catalogue" form. This
  covers `README.md`, `CLAUDE.md`, and the files under `docs/`.
- **FR-009**: User-visible application text MUST use the American spelling. Two page
  templates currently render "catalogue" to the screen.
- **FR-010**: Code comments and docstrings under `app/` and `tests/` MUST use the American
  spelling.
- **FR-011**: Code identifiers under `app/` and `tests/` that embed the British spelling —
  test function names, fixture names, and the references to them — MUST be renamed to the
  American spelling. This requirement is separable from FR-008 through FR-010: it is the
  larger part of the diff by volume and the smallest part by reader-visible value, and
  dropping it leaves the repository consistent everywhere a human reads prose.
- **FR-012**: Renaming under FR-011 MUST be behavior-preserving. The unit and e2e suites MUST
  pass afterwards with the same set of tests, none skipped and none silently renamed out of
  collection.
- **FR-013**: The scope of FR-008 through FR-012 MUST exclude files under `specs/`, which are
  the frozen record of past specifications, and Alembic revision docstrings under
  `migrations/`, which describe migrations as they shipped. Rewriting either would falsify a
  historical record.
- **FR-014**: `CLAUDE.md` MUST state the American-spelling rule as standing guidance for
  future work, and MUST name the exclusions in FR-013 so a later contributor does not "fix"
  the frozen records.

**README**

- **FR-015**: The README's feature list MUST name the product catalog and its principal
  capabilities.
- **FR-016**: The README MUST link a reader to the catalog guidance in the user manual.
- **FR-017**: The README MUST include at least one screenshot of a catalog screen.

**Screenshots**

- **FR-018**: Screenshots of the catalog's principal screens MUST be produced by the
  project's existing automated screenshot generation, not captured by hand.
- **FR-019**: The generated catalog screenshots MUST be embedded in the reworked manual next
  to the prose describing each screen, each with a caption, following the convention the
  existing screenshots use.
- **FR-020**: Screenshot generation MUST seed data representative enough that each captured
  screen shows what the feature is for — a product with purchases and identifiers, a reorder
  list with entries, a category tree with depth.
- **FR-021**: The new screenshot tests MUST be excluded from the standard test sessions, so
  that running those sessions leaves the working tree clean.
- **FR-022**: Every new screenshot MUST satisfy the project's existing screenshot quality
  checks (size ceiling, valid image, color mode).
- **FR-023**: The documents that inventory which screenshots exist MUST list the new ones,
  with correct totals.

### Key Entities

- **User Manual** (`docs/user-manual.md`): the reader-facing guide. Has a table of contents,
  top-level sections, and embedded screenshots with captions.
- **README** (`README.md`): the repository front door. Has a feature list, screenshots, and a
  documentation index.
- **Contributor Instructions** (`CLAUDE.md`): standing rules for future work on this
  repository.
- **Screenshot Set** (`docs/images/screenshots/`): generated PNGs, split into a `readme/`
  and a `user-manual/` group, plus the guide, verification report and metadata that inventory
  them.
- **Screenshot Generation Suite**: the automated tests that seed data, drive the application
  and capture each image.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reader who has never used the application can, from the manual's table of
  contents alone and in under 30 seconds, name at least four things the product catalog does
  and say which section documents each.
- **SC-002**: The catalog's capabilities appear as top-level manual sections, at the same
  heading level as the inventory capabilities they are peers of — not as subsections of one
  catalog section.
- **SC-003**: Every substantive claim present in today's catalog guidance is locatable in the
  reworked manual; a point-by-point comparison finds zero dropped facts.
- **SC-004**: Every table-of-contents link and every cross-document link to a catalog heading
  resolves; a link check reports zero broken anchors.
- **SC-005**: A case-insensitive search for "catalogue" across `README.md`, `CLAUDE.md`,
  `docs/`, `app/` and `tests/` returns zero matches. Searching `specs/` and `migrations/`
  still returns matches, deliberately.
- **SC-006**: After the identifier renames, both test suites pass and collect the same
  number of tests as before the change.
- **SC-007**: A first-time reader of the README alone can say that the application catalogs
  purchased products and can name where to read more.
- **SC-008**: Deleting every catalog screenshot and running the generation command restores
  all of them with no manual step, and the verification command reports all screenshots
  valid.
- **SC-009**: Each of the catalog's principal screens documented in the manual is pictured at
  least once.
- **SC-010**: Running the standard test sessions leaves the working tree clean — no
  regenerated or modified screenshot files.

## Assumptions

- **The catalog's screens worth picturing** are: the product list / all-products search, a
  product detail page, the add-product form, the order-capture confirmation, the reorder
  list, and the categories browser. Adding or dropping one is a planning decision, not a
  change of intent.
- **The catalog's guidance stays in `docs/user-manual.md`** (decided) rather than moving to
  a separate document, so that a reader has one manual to search and the existing "two halves
  of one application" framing survives. Material that straddles both halves — the shared
  location/vendor vocabulary, scanning, label printing — therefore needs no home decision and
  no duplication.
- **No application behavior changes.** This feature touches documentation, the screenshot
  suite and the fixtures it needs. Product screens, routes and data are read, driven and
  photographed, not modified.
- **The spelling rule reaches past documentation** (decided): it covers user-visible
  application text and code comments and docstrings, in addition to the documentation the
  issue names. The repository ends up spelling the word one way everywhere it is written by
  hand.
- **The measured size of that sweep** is 156 occurrences across `app/` and `tests/`, of which
  roughly 85 are code identifiers rather than prose — `tests/unit/test_product_search.py`
  alone has a pytest fixture named `catalogue` referenced 71 times. FR-010 covers the prose;
  FR-011 covers the identifiers and is separable if the diff proves not worth it.
- **No test asserts on the two user-visible strings** being corrected
  (`app/templates/product/reorder.html`, `app/templates/product/detail.html`), so changing
  them breaks nothing that exists today.
- **Screenshots are generated against seeded test data**, never against real inventory, and
  the seeded data contains nothing that would be embarrassing in a public repository.
- **The existing screenshot infrastructure is sufficient** — the capture helper, the quality
  verification and the nox sessions need extending with new tests and fixtures, not
  redesigning.
- **The issue's four points are the whole scope.** Rewriting inventory guidance for its own
  sake, or restructuring sections unrelated to the catalog, is out of scope except where the
  re-levelling unavoidably touches them (the contents list, the overview).
