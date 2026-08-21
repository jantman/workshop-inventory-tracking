# Feature Specification: Gallery Image Counts — Reconcile the Expectation with the Listing

**Feature Branch**: `issues/95`

**Created**: 2026-08-20

**Status**: Draft (amended 2026-08-20 after the Phase 0 live probe — see [research.md](research.md)
§0 for the finding and §1–§8 for the five items the observation corrected)

> **What the probe found, in one line.** Neither explanation was right. #80 §1b's numbers were never
> gallery counts — they are whole-document `hiRes` sweeps that include every sibling variant, and they
> reproduce exactly today. The extractor is defective, but in the opposite direction from the report:
> its JSON parse has never once matched real Amazon markup, so a fallback sweep has answered every
> capture ever made and it emits **two addresses per photograph**, the second a 500-pixel copy. Both
> headline listings publish **7** gallery images; the agent produces 14 and 12.

**Input**: GitHub issue #95 — "Gallery image counts fall short of the §1b expectations — reconcile the probe table with reality": *From the #80 verification pass, comment items 5 and 8. Two of the three plain-description listings captured fewer images than #80 §1b's table demands — `B0CKXJLP4B` expected 14 and captured 7, `B099F4X4Q9` expected 16 and captured 7 — and both landed exactly on the thumbnail-strip number, which §1b names as the signature of reading the gallery from the DOM instead of the page's inline data. But the verifier "also only see[s] 7 images on the page" for `B0CKXJLP4B`, which is the signature of a stale expectation instead. The issue states the working assumption — that the probe table has aged and the code is doing what it should — and states just as plainly that this is the assumption and not the conclusion. It requires the question be settled in the owner's own signed-in Chrome, together, before the extractor or the table is touched. It also carries a knock-on: #80 §1b's B4 check pins the FR-004 original-resolution test to `B0CKXJLP4B` at 1601×1601 / 358,055 bytes, and if the image set has moved that figure is no longer evidence of anything.*

## Terminology

- **Capture** — recording a purchase from a vendor listing by way of the bookmarklet, which reads the
  listing's page and hands the reading to this application. The reading arrives at the confirmation
  form and the write happens when the operator submits it.
- **Gallery image** — one of the product photographs the listing publishes for the item itself, as
  distinct from a picture inside the written description. This feature is entirely about these.
- **Page data** — the listing's own inline data describing its gallery: the machine-readable block
  the page carries so its own image viewer can work. It is the source 007 FR-003 requires the
  capture to read, precisely because it names images the page does not display until the viewer is
  used.
- **Thumbnail strip** — the row of small images the listing renders next to the main photograph. It
  shows a subset. #80 §1b names the thumbnail count as *the wrong answer*: a capture landing on it
  is the signature of reading the rendered page rather than the page data.
- **The probe table** — #80 §1b's six-ASIN table of expected counts, derived from issue #57's
  probing in early August 2026 and repeated in `specs/007-product-page-capture/quickstart.md` and
  its open manual task T052.
- **Variant** — one member of a family of listings the vendor publishes together (a size, a colour, a
  pack quantity). Each variant has its own identifier, and a listing's page data may name a
  different image set for each.
- **Description image** — a picture inside the written description. Out of scope here: which of
  those are captured is issue #94's feature (`specs/021-fix-aplus-image-selection/`), already done.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The question is settled by looking, before anything is changed (Priority: P1)

The owner and the agent open `B0CKXJLP4B` and `B099F4X4Q9` together in the owner's own signed-in
browser and read, from each listing as it stands today, how many product images its page data names.
Nothing about the extractor and nothing about the recorded expectations moves until that reading
exists.

**Why this priority**: This is the feature. Both explanations — an aged table, and a gallery read
from the rendered page — predict the exact number that was seen, so no amount of reasoning about the
code separates them; and each has a fix that is actively harmful if the other is true. "Correcting"
a table that was right hides a live defect in the one check that would have caught it. "Fixing" an
extractor that was right changes working capture behaviour on the strength of a number nobody
re-read. The issue's own framing is that the assumption gets checked rather than trusted.

**Independent Test**: Open each listing in the owner's browser, read the count out of its page data
by hand, and record it beside the thumbnail count and beside what the capture reports. That reading
alone decides the rest of the work, and is valuable even if nothing else in this feature ships.

**Acceptance Scenarios**:

1. **Given** `B0CKXJLP4B` open in the owner's signed-in browser today, **When** its page data is read
   by hand, **Then** the number of product images it names is recorded, along with the date, the
   variant on screen, and how it was read.
2. **Given** the same listing, **When** the thumbnail strip is counted and a capture is run against
   it, **Then** all three numbers — thumbnails, page data, capture — are recorded separately, so a
   coincidence between any two of them cannot be mistaken for agreement.
3. **Given** `B099F4X4Q9`, **When** the same reading is taken, **Then** the same three numbers are
   recorded for it.
4. **Given** either listing offers variants, **When** the reading is taken, **Then** whether its page
   data names a different image set per variant is established and recorded.
5. **Given** the readings, **When** the page data names the same number the capture reported,
   **Then** the expectation is what was wrong and no extraction behaviour changes.
6. **Given** the readings, **When** the page data names more images than the capture reported,
   **Then** that is a defect against 007 FR-003 and it is fixed in this feature.

---

### User Story 2 - A capture collects every gallery image the listing names (Priority: P1)

The operator captures a listing and gets the product photographs the listing itself holds — not only
the handful it happens to render in the strip.

**Why this priority**: This is the requirement the count is evidence *for*, and it is the whole
reason 007 reads the page data at all. An image not captured on the day is gone when the listing
changes, and the operator has no way to learn it existed. It is P1 alongside US1 because if US1 finds
a defect, this is the defect.

*(Amended after the Phase 0 probe: US1 found a defect, and it is the mirror image of the one reported.
Nothing is being missed — every gallery entry is captured, and then captured a second time as a
500-pixel copy under a different filename. The requirement below is unchanged and still correct; what
the probe added is scenarios 5 and 6, which are the half of "every gallery image, once" that nobody
had written down because nobody suspected it. See [research.md](research.md) §1 and §2.)*

**Independent Test**: For each listing read in US1, compare the number of images the capture reports
against the number read by hand from that same listing's page data in the same session. They match.

**Acceptance Scenarios**:

1. **Given** a listing whose page data names more product images than its thumbnail strip displays,
   **When** the operator captures it, **Then** the capture reports and stores the page-data set, not
   the strip's subset.
2. **Given** a listing whose page data names exactly as many images as the strip displays, **When**
   the operator captures it, **Then** the capture reports that number — a count equal to the
   thumbnail count is the correct answer here, not a failure.
3. **Given** a listing that publishes a different image set for each of its variants, **When** the
   operator captures one variant, **Then** the images stored are that variant's, neither another
   variant's set nor a merge of all of them.
4. **Given** any listing already captured correctly today, **When** it is captured after this
   feature, **Then** it stores the same images it stored before.
5. **Given** a gallery entry naming both a full-resolution address and a smaller rendition of the
   same photograph, **When** the capture completes, **Then** exactly one image is stored for that
   entry — the largest the entry names — and never both.
6. **Given** a gallery entry naming no full-resolution address at all, **When** the capture completes,
   **Then** the best address that entry does name is stored and the entry is not skipped.

---

### User Story 3 - The verification record states what is true, and when it was read (Priority: P1)

The next person to walk #80 §1b — or 007's still-open manual task — is measuring against numbers
somebody actually saw, and can tell at a glance how old each one is.

**Why this priority**: P1, not housekeeping. A checklist item that fails for a reason other than the
one it is testing for costs a verification pass its credibility: this one produced two "failures",
consumed a browser session and an issue, and may turn out to describe nothing. Left uncorrected it
will do so again on every future pass, and the third time it cries wolf the real gallery defect goes
through. An expected count read from a live vendor listing has a shelf life, and the record has to
say so on its face.

**Independent Test**: Read the corrected record cold, without a browser. It states, per listing, the
page-data count, the thumbnail count, the date each was read, and how to re-derive it.

**Acceptance Scenarios**:

1. **Given** the readings from US1, **When** the record is corrected, **Then** every expected image
   count for these listings agrees with what was observed.
2. **Given** a corrected figure, **When** the record is read, **Then** it carries the date it was
   observed and the means used, so a later reader can tell an aged number from a fresh one.
3. **Given** a figure that a frozen artifact recorded earlier, **When** it is corrected, **Then** the
   correction is a dated amendment beside the original rather than an overwrite of it.
4. **Given** the corrected record, **When** a future verifier finds a count that disagrees, **Then**
   the record tells them which of the three numbers they should be comparing and how to read it.

---

### User Story 4 - The original-resolution check has evidence behind it again (Priority: P2)

The FR-004 check — that a stored image is the listing's original and not a resized rendition — is
pinned to a specific file at a specific size. Whoever runs it next is comparing against a
measurement of an image that is still on the listing.

**Why this priority**: P2 because it is a knock-on rather than the reported defect, but it is not
optional: if `B0CKXJLP4B`'s image set has moved, 1601×1601 / 358,055 bytes may name a file the
listing no longer serves, and a check whose expected value is unreachable cannot pass or fail — it
can only be skipped. FR-004 is the one capture requirement with no fallback and therefore no silent
failure mode, and that property is worth keeping testable. The browser session is already open, so
re-establishing it costs minutes.

**Independent Test**: Follow the FR-004 check as written against a captured product and reach a
verdict — pass or fail — without having to decide whether the expected numbers still apply.

*(Amended after the Phase 0 probe: **the baseline is intact.** `81flPsAWG-L.jpg` measured 1601×1601 /
358,055 bytes on 2026-08-20, identical to #57's 2026-08-09 figure, with the tokened rendition still
1446×1500 / 345,670. Scenario 2 below is therefore expected to be a no-op. What the probe did find is
that B4's wording — "check a stored original" — is unsafe while half the stored images are 500×500
copies, because the wrong one measures 500×500 / 62,467 and that is indistinguishable from a
verifier's error. Scenario 3 gains the naming requirement. See [research.md](research.md) §5.)*

**Acceptance Scenarios**:

1. **Given** the browser session of US1, **When** `B0CKXJLP4B`'s current gallery is read, **Then**
   whether the image the 1601×1601 / 358,055-byte figure describes is still published is established.
2. **Given** that image is no longer published, **When** the record is corrected, **Then** the check
   is re-anchored to an image the listing carries now, with its original dimensions and byte size
   measured this session and both the tokened and untokened figures recorded.
3. **Given** the re-anchored check, **When** a capture is run and a stored original is measured,
   **Then** it matches the recorded original, and the tokened rendition's figure is recorded beside
   it so the failure remains recognisable rather than merely "wrong".
4. **Given** any figure repeated elsewhere as justification for stripping the transform token,
   **When** the baseline changes, **Then** that repetition is corrected too rather than left to
   contradict the record.

---

### User Story 5 - A degraded reading is visible rather than silent (Priority: P2)

If the capture cannot read the page data in the form it expects and falls back to a cruder reading,
the operator can tell.

**Why this priority**: **P2, raised from P3 by the probe** — US1 showed the fallback is not merely
what has been answering, it is the *only* thing that has ever answered, on all six listings, for the
entire life of the feature. A silent degradation that ran for a whole release and was found only
because an unrelated checklist item disagreed is not a nice-to-have. It is still kept small: one
console line on the path that already has one beside it. It is here because it is the mechanism that would let this defect exist at all: a
reading that quietly degrades produces a plausible smaller number and no complaint, and the only
evidence is a count that looks a bit low on a page nobody counted. It earns its place under the
simplicity principle as a line the operator can see, not as machinery.

**Independent Test**: Against a listing whose page data does not parse in the expected form, run a
capture and observe that something says so.

**Acceptance Scenarios**:

1. **Given** a listing whose page-data block cannot be read in the expected form, **When** a capture
   runs, **Then** the operator can tell that the count came from a lesser reading.
2. **Given** a listing that reads normally, **When** a capture runs, **Then** nothing new is said.

---

### Edge Cases

- **The listing changed between August 3rd and today.** The expected case, and the reason the issue
  exists. A listing that names fewer images than it did is not a defect and must not be recorded as
  one.
- **A listing whose page data names exactly what its thumbnail strip shows.** Correct and, by count
  alone, indistinguishable from the failure this table was written to catch. This is why the three
  numbers are recorded separately rather than compared as a pair.
- **A listing offering variants.** Its page data may name a different set per variant, and the set
  read depends on which variant the reading resolves to. A count that moves between readings of
  "the same" listing is explained by this before it is explained by anything else.
- **More than one place in the page naming gallery data.** A reading that takes the first one it
  finds can answer from a block belonging to something other than the product being captured.
- **A page-data entry that is not a photograph** — a video, a 360° spin, a swatch. It may or may not
  count towards "images"; whichever it is, the record must say, because a discrepancy of one or two
  is otherwise unresolvable.
- **A reading taken while signed out, or refused and answered from the rendered page instead.** The
  counts can differ from what the owner sees signed in. The session's reading is only evidence if it
  was taken the way the operator's own capture takes it.
- **An image address the listing names that cannot be retrieved once the transform token is
  stripped.** 007 FR-004 deliberately has no fallback: it is reported as a failed image. That stays.
- **A listing that has been withdrawn.** Neither the count nor the FR-004 baseline can be
  re-established from it, and the expectation must be re-anchored to a listing that exists rather
  than kept as an untestable figure.
- **The two listings disagree** — one stale expectation, one real shortfall. Both conclusions are
  recorded and both are acted on; a single verdict for the pair is not assumed.

## Requirements *(mandatory)*

### Functional Requirements

**Establishing what is true**

- **FR-001**: The number of product images `B0CKXJLP4B` and `B099F4X4Q9` name in their own page data
  MUST be read from the live listings, in the owner's signed-in browser, with the owner present,
  **before** any extraction behaviour or any recorded expectation is changed.
- **FR-002**: For each listing, three numbers MUST be recorded separately: the count the page data
  names, the count the thumbnail strip displays, and the count a capture reports. A conclusion MUST
  NOT be drawn from any two of them alone.
- **FR-003**: The reading MUST establish whether either listing offers variants and, if so, whether
  its page data names a different image set per variant, and which variant the reading was taken
  from.
- **FR-004**: The reading MUST be taken under the same conditions a real capture runs under —
  signed in, from the listing as the operator reaches it. A reading that was refused, redirected, or
  answered from the rendered page rather than the page data MUST be recorded as such and MUST NOT be
  used as evidence.
- **FR-005**: The observation MUST be recorded in this feature's artifacts with its date and the
  means used, in enough detail that a later reader can repeat it.

**What a capture must do**

- **FR-006**: A capture MUST report and store every product image the listing's page data names for
  the item being captured. It MUST NOT report a set limited to what the thumbnail strip displays.
  *(This restates 007 FR-003; it is repeated here because it is what the observation tests.)*
- **FR-007**: Where a listing publishes a different image set per variant, a capture MUST store the
  set belonging to the variant being captured — not another variant's set, and not a merge across
  variants.
- **FR-008**: Where more than one candidate block of page data is present, a capture MUST take the
  one describing the product being captured rather than the first one encountered.
- **FR-009**: Where the page data cannot be read in the expected form and a lesser reading answers
  instead, the capture MUST NOT present that reading as though it were the full one. The degradation
  MUST be observable to the operator at capture time.
- **FR-010**: If the observation shows FR-006 through FR-008 already hold on these listings, no
  extraction behaviour may be changed. A reported count that matches the page data is the correct
  answer even where it is lower than a previously recorded expectation, and lowering the recorded
  expectation is then the whole of the change.
  *(Not triggered. The probe found a defect — see FR-021 — so the extractor changes as well as the
  record. The clause is kept because its second sentence is now load-bearing in its own right: 7 is
  the correct answer for both listings even though it equals the thumbnail count that #80 §1b calls
  "the wrong answer".)*
- **FR-021**: A capture MUST store **one** image per gallery entry. Where an entry names the same
  photograph at more than one resolution, the largest the entry names MUST be stored and the smaller
  renditions MUST NOT be. Where an entry names no full-resolution address, the best address it does
  name MUST be stored rather than the entry skipped.
  *(Added after the Phase 0 probe. This is the observed defect: 7 gallery entries are being stored as
  14 attachments, alternating a 1601×1601 original with a 500×500 copy of the same picture under a
  different filename. See [research.md](research.md) §2.)*
- **FR-022**: The reading MUST locate the listing's gallery array wherever the listing places it,
  including as the argument of a function call inside a quoted string. Failing to locate it MUST NOT
  be indistinguishable from succeeding.
  *(Added after the Phase 0 probe. `initialImageArray()` searches for a bracket immediately after
  `initial':`; every real listing serves `'initial': A.$.parseJSON('[…]')`, so the search has never
  matched and the fallback has answered every capture ever made. See [research.md](research.md) §1.)*

**What must not change**

- **FR-011**: This feature MUST NOT change which description images are captured, or how. Issue #94's
  correction (`specs/021-fix-aplus-image-selection/`) stands untouched.
- **FR-012**: This feature MUST NOT change the captured description text, product-information rows,
  identifiers, price, brand, or any other captured field. On a listing whose gallery reading does not
  change, a capture after this feature MUST produce exactly what it produced before.
  *(Amended after the Phase 0 probe: there is no listing in the probe set whose gallery reading does
  not change — all six roughly halve. The requirement now binds only the non-gallery fields, which is
  what it was always for. Description images are covered separately by FR-011.)*
- **FR-013**: 007 FR-004 MUST remain in force unchanged: a stored gallery image is the listing's
  original, the transform token is stripped, and there is no fallback to the tokened address. What
  may be re-established is the *expected measurement*, never the requirement.

**The record**

- **FR-014**: Every place recording an expected gallery image count for these listings MUST agree
  with what was observed, and MUST distinguish the page-data count from the thumbnail count rather
  than presenting a single unlabelled number.
- **FR-015**: Each corrected expectation MUST carry the date it was observed, so a later reader can
  judge its age. A vendor listing is not a fixed target and the record MUST NOT read as though it is.
- **FR-016**: Where the earlier figure sits in a frozen artifact — a delivered feature's
  specification, quickstart or task list — the correction MUST be a dated amendment recorded beside
  the original, never an overwrite that erases what was specified at the time.
- **FR-017**: The FR-004 original-resolution check MUST end this feature testable: an expected
  dimension and byte size for an image the anchor listing publishes today, measured this session,
  with the tokened rendition's figure recorded alongside so the failure it detects stays
  recognisable. If it cannot be anchored to `B0CKXJLP4B`, it MUST be re-anchored to a listing that
  can carry it.
  *(Amended after the Phase 0 probe: satisfied without changing a number. 1601×1601 / 358,055 was
  re-measured on 2026-08-20 and is unchanged from #57's figure; `B0CKXJLP4B` still publishes that
  image as its first gallery entry. What the check does need is to name the image by its filename
  stem rather than saying "a stored original", because until FR-021 lands half the stored originals
  are 500×500 copies and measuring the wrong one looks like a failure. See
  [research.md](research.md) §5.)*
- **FR-018**: Any figure repeated outside the record as justification — including in the extractor's
  own commentary — MUST agree with the re-established baseline.

**Proving it**

- **FR-019**: If the observation finds a defect, the automated suite MUST fail if that defect
  returns, against a fixture whose gallery page data is shaped the way the real listing serves it —
  including whatever structure defeated the reading. A fixture that cannot exhibit the defect does
  not satisfy this requirement.
- **FR-020**: If the observation finds no defect, this feature MUST change no extraction code and no
  test. The deliverable is then the corrected record and nothing else.
  *(Not triggered — see FR-021 and FR-022.)*
- **FR-023**: The correction to #80 §1b MUST fix its **inference** as well as its numbers. B1 tells a
  verifier that a count equal to the thumbnail count means the gallery is being read from the DOM;
  on both headline listings the gallery and the strip are both 7, so that check can only be failed by
  being right. A verifier MUST be told which number is the gallery and how to read it.
  *(Added after the Phase 0 probe. See [research.md](research.md) §3.)*

### Key Entities

- **Listing**: A vendor product page, identified by its item identifier. Carries page data naming its
  gallery, a thumbnail strip showing a subset of it, a written description, and product-information
  rows. It is a live third-party artifact and may change at any time.
- **Gallery reading**: The set of product image addresses a capture derives from a listing's page
  data. Its size is the number under dispute.
- **Recorded expectation**: A figure held in the verification record against which a manual check is
  judged — an image count, or an original's dimensions and byte size. Has a provenance and a date,
  and ages.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For `B0CKXJLP4B` and `B099F4X4Q9`, the image count the confirmation page reports equals
  the count read by hand from that same listing's page data in the same session.
- **SC-002**: For both listings, the page-data count, the thumbnail count and the captured count are
  recorded as three separate figures, each dated 2026-08-20 or later.
- **SC-003**: No expected gallery image count for these listings survives this feature unless it was
  read from the live listing during it, and every surviving figure states the date it was read.
- **SC-004**: A verifier can carry out the FR-004 original-resolution check and reach a pass or fail
  on measured evidence — an expected dimension and byte size for an image the listing publishes
  today — without having to judge whether the expectation still applies. *(Measured 2026-08-20:
  1601×1601 / 358,055 bytes, unchanged. The remaining work is naming the image, not re-measuring
  it.)*
- **SC-005**: Capturing a listing whose gallery reading did not change produces a byte-identical set
  of description images, description text, product-information rows and identifier fields to what the
  same listing produced before this feature.
- **SC-006**: Exactly one of two end states holds, and the record says which: extraction was found
  correct and no extraction code changed; or a defect was found, fixed, and reverting the fix fails
  the suite.
- **SC-007**: A future verifier reading the corrected record without opening a browser can tell, per
  listing, which number they should be comparing against, when it was last confirmed, and how to
  re-derive it themselves.
- **SC-008**: The next verification pass over these listings raises no finding that turns out to be
  an aged expectation rather than a defect.
- **SC-009**: After the change, a capture reports these counts, and they equal the gallery entries
  each listing publishes: `B0CKXJLP4B` **7** (from 14), `B099F4X4Q9` **7** (from 12), `B01N4OSKWE`
  **3** (from 6), `B0DMNXC4CD` **7** (from 14), `B09GM8FB3X` **8** (from 14), `B0FX4PDW6M` **7**
  (from 14). Every image lost is a duplicate of one that remains; no photograph the listing publishes
  is missing.
- **SC-010**: Every stored gallery image is an original. Measuring any of them returns the dimensions
  the listing's own data names for that entry, and none returns the 500-pixel rendition.
- **SC-011**: A capture that could not read the listing's gallery data in the expected form says so
  where the operator can see it. Establishing this requires making the reading fail deliberately —
  it is not observable on a listing that works.

## Assumptions

- **~~The probe table has aged~~ — falsified, and not in the way either side expected.** The table
  did not age: its numbers reproduce exactly on 2026-08-20. They were never gallery counts. #57's
  column headed "hi-res URLs in page data" is the count of distinct `hiRes` addresses in the whole
  document, which on a variation family includes every sibling variant's lead image — 7 gallery
  images plus 8 pack variants makes `B0CKXJLP4B`'s 14. The original text is kept below because the
  requirements it justifies still stand. *Issue #95 states this explicitly and requires it be checked
  rather than trusted. This specification therefore requires the reading (FR-001 through FR-005) and
  permits either outcome: FR-010 covers the stale table, FR-006 through FR-009 and FR-019 cover the
  defect. Nothing here presumes which.* See [research.md](research.md) §3.
- **The two listings may not give the same answer.** They are treated as two independent questions
  throughout; a finding on one is not evidence about the other. *(As it turned out they give the same
  answer, as do the other four: one cause, six listings.)*
- **~~Only the two listings named in the issue are in scope for the reading.~~ Superseded.** The
  first two showed the cause was structural rather than listing-specific, which is the condition this
  assumption named for widening, so all six of #57's ASINs were probed in the same session. The
  numbers for all six are in [research.md](research.md) §0 and all six are corrected.
- **The A+ listings' floors are somebody else's numbers.** #80 §1b's counts for `B0DMNXC4CD`,
  `B09GM8FB3X` and `B0FX4PDW6M` are floors covering gallery *plus* description images, and issue #94's
  feature has since moved what the description contributes. This feature neither relies on them nor
  corrects them. *(Amended: their **gallery** halves are corrected, because the same defect is on all
  three and the probe measured them — 7, 8 and 7 entries. What is left alone is the description
  contribution, which is #94's.)*
- **Verification is manual and in-browser, by design.** These are live third-party listings; no
  automated suite can assert against them, which is exactly why FR-019 puts the real structure into a
  fixture instead.
- **The reading happens in the owner's own browser, not a headless one.** The issue requires it: the
  session is the owner and the agent looking at the same page, signed in, at the same time. An agent
  reading the page alone from a different browser is not what was asked for and would reproduce the
  original mistake of concluding from something other than what the operator sees.
- **The bookmarklet does not need reinstalling.** 007 FR-024 already requires changes to what
  extraction reads to take effect without the operator reconfiguring their browser; this feature
  inherits that and adds nothing to it.
- **Nothing is corrected by hand in the database.** If images were missed on an earlier capture, the
  remedy is a re-capture once the reading is right, not an edit to stored rows. *(Amended after the
  probe: the problem is the opposite — every product captured since 007 shipped carries roughly twice
  the images it should, half of them 500-pixel copies. Nothing is lost and nothing is corrupt. The
  remedy is the operator's, using bulk photo deletion (#96); this feature stops it recurring and says
  how to recognise the copies. See [research.md](research.md) §9.)*
