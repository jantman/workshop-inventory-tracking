# Feature Specification: A+ Description Images — Keep the Product's, Drop the Vendor's

**Feature Branch**: `issues/94`

**Created**: 2026-08-19

**Status**: Draft (amended 2026-08-19 after the Phase 0 live-markup probe — see
[research.md](research.md) §7 for the three items the observation corrected)

**Input**: GitHub issue #94 — "A+ image selection is wrong in both directions: vendor cross-sells kept, the spec-table image dropped": *From the #80 verification pass, comment item 10. Capturing `B0FX4PDW6M` collected "a large number of images of the vendor's other products", which had to be deleted one at a time, and did **not** collect "one of the most important images — the image of the specification table embedded in the A+ product description — a 1464×600 JPEG". Both failures come out of the same block, so the 300-pixel edge rule (007 FR-019) is not the right discriminator on its own. The over-capture is the "From the brand" brand-story carousel, which the listing renders inside the A+ block and which is categorically not this product. The under-capture is an image large enough to pass the size rule, so it is very likely never being seen at all — a lazily-loaded address, a sibling A+ region that is never read, or a misleading layout attribute. The issue is explicit that the diagnosis happens in the owner's browser against the real signed-in listing, and that whatever it finds goes back into the test fixture as real markup rather than as markup somebody imagined.*

## Terminology

- **Capture** — recording a purchase from a vendor listing by way of the bookmarklet, which reads the
  listing's page and hands the reading to this application. The reading arrives at the confirmation
  form and the write happens when the operator submits it.
- **Gallery image** — one of the product photographs the listing's own image strip names. Gallery
  images are captured under their own rules and are **out of scope here**: nothing in this feature
  changes which gallery images are captured or how (that is issue #95).
- **Description block** — the region of the listing that carries the vendor's written description of
  the product. It takes a plain form and a rich ("A+") form; the A+ form is a stack of laid-out
  modules containing prose, tables rendered as pictures, and photographs.
- **Description image** — a picture that lives inside the description block. This feature is
  entirely about which of these are captured.
- **Content image** — a description image that depicts, describes or specifies **this** product: the
  spec-table picture, a labeled diagram, a photograph of the item in use.
- **Furniture** — a description image that carries no product information: a spacer, a rule, a
  bullet glyph, a badge. The existing 300-pixel rule (007 FR-019) exists to drop these and does so
  correctly; it is not being changed.
- **Cross-sell region** — a part of the description block that advertises the vendor's **other**
  products. On `B0FX4PDW6M` this is the "From the brand" brand-story carousel, rendered inside the
  A+ block. Its images are large, well-produced photographs — indistinguishable from content by
  size, and distinguishable by where they sit.
- **The 300-pixel rule** — 007 FR-019: a description image measuring under 300 pixels on either
  edge that can be established before retrieval is not stored; one whose dimensions cannot be
  established is stored. It stays exactly as it is.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The specification picture survives the capture (Priority: P1)

The operator captures a listing whose real specifications are published as a picture of a table
inside the A+ description — an extremely common shape for tooling and hardware. The saved product
carries that picture.

**Why this priority**: This is the half of the bug that loses information permanently. A deleted
cross-sell costs a click; a specification table that was never captured is gone the day the listing
changes, and the operator has no way to know it was ever there. `B0FX4PDW6M`'s spec table is a
1464×600 JPEG — it clears the 300-pixel rule on both edges by a wide margin, so it is not being
rejected, it is not being *seen*.

**Independent Test**: Capture a listing whose A+ description contains a large specification-table
image. Confirm the stored images include it, at the resolution the listing publishes.

**Acceptance Scenarios**:

1. **Given** a listing whose A+ description contains a specification-table image measuring well over
   300 pixels on both edges, **When** the operator completes a capture, **Then** that image is among
   the product's stored attachments.
2. **Given** a description image whose address the listing supplies somewhere other than a plain
   `src` — a deferred-loading attribute, a candidate set, a placeholder that is replaced on scroll —
   **When** the capture completes, **Then** the image is captured all the same.
3. **Given** a listing that carries more than one A+ region, **When** the capture completes, **Then**
   content images from every one of those regions are captured, not only from the first.
4. **Given** a large description image whose markup declares a small display size, **When** the
   capture completes, **Then** it is captured rather than dropped as furniture.
5. **Given** a description image the listing also shows in the gallery, **When** the capture
   completes, **Then** it is stored once, not twice.

---

### User Story 2 - The vendor's other products stay out of the catalog (Priority: P1)

The operator captures a listing whose A+ description ends in a "From the brand" carousel showing a
dozen of the vendor's other products. None of those pictures reach the product.

**Why this priority**: Equal to US1 because it is the same defect seen from the other side, and
because the cost is real and repeated: on `B0FX4PDW6M` the operator deleted these by hand, one at a
time. It is also the failure that makes the captured gallery unusable — a product page whose
attachments are mostly pictures of *other* products cannot be looked through, which was the whole
point of capturing images.

**Independent Test**: Capture a listing whose A+ description carries a brand-story carousel of other
products. Confirm none of the carousel's images are stored, and that every content image from the
same description block still is.

**Acceptance Scenarios**:

1. **Given** an A+ description containing a cross-sell region, **When** the capture completes,
   **Then** no image from that region is stored.
2. **Given** the same capture, **When** it completes, **Then** the content images from the rest of
   that description block are stored — the exclusion removes a region, not the block.
3. **Given** a listing whose A+ description carries no cross-sell region, **When** the capture
   completes, **Then** the images captured are exactly what they would have been without this
   feature.
4. **Given** a cross-sell image that is also a legitimate gallery image of this product, **When** the
   capture completes, **Then** it is still captured — by way of the gallery, which this feature does
   not touch.

---

### User Story 3 - Neither correction is bought at the other's expense (Priority: P1)

The change is proven on the listings that motivated it and on the listings that already worked,
before it is called done.

**Why this priority**: P1 because the two corrections pull in opposite directions and a plausible
fix for either one breaks the other. Widening what is read to find the spec table is exactly what
lets 57 furniture images back in; excluding harder to keep cross-sells out is exactly what silently
drops a content image on the next listing. There is no version of this feature that is finished
without the counter-check.

**Independent Test**: Re-capture the three A+ listings from #80 §1b and compare against the recorded
figures: `B0FX4PDW6M` gains the spec table and loses the cross-sells; `B09GM8FB3X` and `B0DMNXC4CD`
lose nothing.

**Acceptance Scenarios**:

1. **Given** `B0FX4PDW6M`, **When** it is re-captured, **Then** the confirmation page reports more
   images than it did before the change and nowhere near the 57 unique addresses the page carries.
2. **Given** `B09GM8FB3X`, **When** it is re-captured, **Then** it reports at least the 11 images
   #80 §1b records as its floor, and no image it captured before is missing.
3. **Given** `B0DMNXC4CD`, **When** it is re-captured, **Then** it reports at least the 7 images
   #80 §1b records as its floor, and no image it captured before is missing.
4. **Given** any of the three, **When** it is re-captured, **Then** the description text, the
   product-information rows and the gallery images are unchanged by this feature.

---

### User Story 4 - The automated test is anchored to a real listing (Priority: P2)

The markup the suite tests against is markup a real listing actually served, not an approximation
written from memory of it.

**Why this priority**: P2 because it protects the fix rather than being the fix — but it is the
reason this bug reached the operator at all. The suite already covers A+ image selection and passed
throughout; it passed because the fixture was hand-written and contained neither a cross-sell
carousel nor a deferred-loading image. A fixture that cannot exhibit the defect cannot catch it, and
a second hand-written fixture would repeat the mistake at greater length.

**Independent Test**: Read the fixture the suite uses for A+ image selection and confirm the
cross-sell region and the awkward image addresses in it are shaped as the real listing serves them.

**Acceptance Scenarios**:

1. **Given** the test fixture for A+ description capture, **When** it is inspected, **Then** it
   contains a cross-sell region whose markup matches the real listing's structure and naming.
2. **Given** the same fixture, **When** it is inspected, **Then** it contains a large content image
   expressed the way the real listing expresses it, including whatever defeats capture today.
3. **Given** the change, **When** the suite runs, **Then** a build that re-introduces either half of
   this defect fails a test.

---

### Edge Cases

- **A description block that is nothing but a cross-sell region.** No description images are
  captured. The capture still succeeds, still stores the gallery, and still stores the description
  text — an empty image list is a correct answer, not a failure.
- **A cross-sell image that cannot be distinguished from a content image by anything except its
  position.** This is the normal case, not the exception: both are large, well-produced product
  photographs. Position is the discriminator; size is not, and raising the 300-pixel rule to
  compensate is prohibited by FR-005.
- **An image whose dimensions cannot be established at all.** Kept, exactly as 007 FR-019 already
  says. Widening where images are read from must not turn "unknown" into "discard".
- **The same image reachable from two A+ regions, or from a candidate set and a deferred attribute
  at once.** Stored once. 007 FR-018 already judges duplicates by content, but the reading must not
  submit the same picture under several addresses and consume the attachment budget with them.
- **A candidate set offering the same picture at several widths.** The largest available is what is
  captured; a captured image is never smaller than what the listing displays.
- **A listing with a plain description rather than an A+ one.** Untouched by this feature in every
  respect.
- **A cross-sell region the vendor renames.** The capture must degrade to today's behavior — some
  unwanted images to delete — and must never fail the capture or drop content images because a
  region it expected was absent.
- **The attachment ceiling.** If a listing's genuine content images plus its gallery exceed the
  per-product limit, the existing clean stop (007 FR-022) applies unchanged; this feature must not
  make the limit easier to hit by re-admitting furniture.

## Requirements *(mandatory)*

### Functional Requirements

**What is captured**

- **FR-001**: A capture MUST store the content images of a listing's A+ description — the pictures
  that depict, describe or specify the product being captured — including images published only as
  a picture of a table.
- **FR-002**: A capture MUST find a description image regardless of how the listing expresses its
  address. An address the listing supplies only through a deferred-loading attribute, a candidate set,
  or any means other than a directly resolved address MUST NOT cause the image to be skipped. This matters
  because the reading is taken from the canonical listing document, which is never displayed or
  scrolled, so nothing deferred has resolved by itself.
- **FR-003**: A capture MUST read every description region the listing carries, not only the first
  one that has text. An image MUST NOT be missed because it sits in a sibling region.
- **FR-004**: A capture MUST NOT store a description image that belongs to a cross-sell region — a
  part of the description advertising the vendor's other products, such as the "From the brand"
  brand-story carousel.
- **FR-005**: The exclusion required by FR-004 MUST be made by identifying the region, not by
  raising the size threshold. The 300-pixel rule (007 FR-019) MUST remain in force with its
  threshold unchanged, and no listing may lose an image it captures today because that number moved.
- **FR-006**: Excluding a cross-sell region MUST NOT exclude the description block that contains it.
  Content images that sit alongside a cross-sell region MUST still be captured.
- **FR-007**: Where a description image is offered at more than one resolution, the capture MUST
  store the largest the listing offers, and never one smaller than the listing displays.
- **FR-008**: Reading an image from more than one place — two regions, or two attributes of one
  element — MUST yield one stored image, and MUST NOT consume more than one of the product's
  attachment slots.
- **FR-009**: Where the expected structure of a description or a cross-sell region is absent or has
  been renamed by the vendor, the capture MUST still complete and MUST still store whatever content
  images it can identify. A structural surprise MUST NOT refuse a capture and MUST NOT be resolved
  by discarding images.

**What must not change**

- **FR-010**: This feature MUST NOT change which gallery images are captured, or how.
- **FR-011**: The captured description text MUST be read from the same block this feature corrects.
  A cross-sell region's prose MUST NOT be captured as the product's description. This feature MUST
  NOT change the captured product-information rows, or any other captured field.
  *(Amended after the Phase 0 probe: the original wording forbade changing the description text at
  all, which the observed cause makes impossible to honor — the wrong block is being read, and its
  text is the vendor's company bio. See [research.md](research.md) §5 and §7.)*
- **FR-012**: An image whose dimensions cannot be established before retrieval MUST continue to be
  stored rather than discarded (007 FR-019), including under the wider reading FR-002 and FR-003
  introduce.
- **FR-013**: The three A+ listings recorded in #80 §1b MUST NOT lose any *real* image they capture
  today. Two categories may be lost and only these two: the cross-sell images FR-004 removes, and
  placeholder images that are not pictures of anything — a capture MUST NOT store a deferred-loading
  placeholder in place of the image it stands for.
  *(Amended after the Phase 0 probe: every A+ listing with deferred-loading images stores a 1×1 grey
  placeholder as an attachment today, so a blanket "loses nothing" would forbid fixing it. See
  [research.md](research.md) §2 and §6.)*

**Proving it**

- **FR-014**: The behavior required by FR-001 through FR-009 MUST be settled against the real
  listing as it renders today, signed in, before it is implemented — not inferred from markup
  written from memory.
- **FR-015**: The automated test fixture for A+ description capture MUST reproduce the real
  listing's markup for both halves of this defect: a cross-sell region, and a large content image
  expressed the way the listing expresses it. A test that passes against a fixture that cannot
  exhibit the defect does not satisfy this requirement.
- **FR-016**: The suite MUST fail if either half of this defect returns — a cross-sell image stored,
  or a large content image dropped.

### Key Entities

- **Description block**: The listing's written description of the product, in its rich (A+) form: a
  stack of modules that may include prose, pictures of tables, photographs, layout furniture, and a
  cross-sell region. A listing may carry more than one such region.
- **Description image**: A picture inside a description block. Classified by this feature into
  content (captured), furniture (dropped by size, unchanged) and cross-sell (dropped by position,
  new).
- **Captured listing**: The reading handed to the confirmation form. Unchanged by this feature
  except in the membership of its image list.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Re-capturing `B0FX4PDW6M` stores the specification-table picture from its A+
  description, at the resolution the listing publishes.
- **SC-002**: Re-capturing `B0FX4PDW6M` stores zero pictures of the vendor's other products. The
  operator deletes no images by hand after the capture.
- **SC-003**: Re-capturing `B0FX4PDW6M` reports at least 7 images and fewer than 20 — above the 6
  gallery images plus the spec table, and nowhere near the 57 unique addresses the page carries.
  A count approaching 57 means the size rule has stopped working.
- **SC-004**: Re-capturing `B09GM8FB3X` reports at least 11 images and `B0DMNXC4CD` at least 7, the
  floors recorded in #80 §1b, with no *real* image either captured before now missing. Each drops
  exactly one placeholder image and nothing else.
- **SC-005**: For each of the three listings, the product-information rows and the gallery are
  unchanged from what the same capture produced before this change. The description text is
  unchanged on the two listings whose block selection was already correct, and on `B0FX4PDW6M` it
  becomes the product's own description in place of the vendor's company bio.
- **SC-006**: Reverting the fix, with the new tests in place, fails the suite — for both the
  over-capture and the under-capture.
- **SC-007**: The operator, looking at the captured product page for `B0FX4PDW6M`, can find the
  product's specifications in the images without scrolling past a single picture of something they
  did not buy.

## Assumptions

- **~~The cause is diagnosed before it is fixed~~ — done. The probe ran on 2026-08-19** and its
  findings are in [research.md](research.md); none of issue #94's three candidates was the cause.
  The original text is kept below because the requirements it justifies still stand.
  Issue #94 names three candidate causes for the under-capture — a deferred-loading address, an unread sibling
  region, a misleading layout attribute — with three different fixes, and states plainly that
  choosing between them from inferred markup is guessing. This specification therefore requires the
  *outcome* (FR-001) and permits any of the three to be the answer, or more than one. FR-002,
  FR-003 and the "misleading declared size" scenario in US1 each cover one candidate; whichever
  turn out not to apply to this listing still describe correct behavior and cost nothing to hold.
- **Position, not size, separates a cross-sell from content.** Both are large product photographs.
  Any approach that tries to separate them by dimensions will fail on one listing or the other, and
  FR-005 forbids it.
- **The exact markup naming the cross-sell region is not fixed here.** The issue offers
  `.aplus-brand-story-card` and `#aplusBrandStory` explicitly "from memory of the markup, not from
  this page"; neither exists. The observed container is `#aplusBrandStory_feature_div`, recorded in
  [research.md](research.md) §5. It belongs in the plan, not in this specification.
- **~~Description *text* is out of scope.~~ Falsified by the Phase 0 probe; text is in scope.**
  This assumption held that the defect was about images and that touching text risked regressing
  #91. The probe showed the defect is the *choice of block*, from which text and images are both
  read — `B0FX4PDW6M`'s captured description is the vendor's company bio, and the specification
  table that issue #94 wants as an image is also missing from the description text for the same
  reason. #91 changed how text is stripped, not which block it comes from, and is untouched. See
  [research.md](research.md) §5 and §7.
- **The gallery is somebody else's feature.** #95 covers gallery counts falling short of the #80
  §1b table. Nothing here touches gallery selection, and the counts in SC-003 and SC-004 assume the
  gallery behaves exactly as it does today.
- **Verification is manual and in-browser, by design.** The three ASINs are live listings; no
  automated suite can assert against them, which is precisely why FR-015 requires the fixture to
  carry the real markup instead.
- **The bookmarklet does not need reinstalling.** 007 FR-024 already requires changes to what
  extraction reads to take effect without the operator reconfiguring their browser; this change
  inherits that and adds nothing to it.
