# Feature Specification: Product Page Capture

**Feature Branch**: `issues/57`

**Created**: 2026-08-09

**Status**: Draft

**Input**: GitHub issue #57 — "Product Page Capture", and its comment of 2026-08-09 recording six probed Amazon listings, the options ruled out, and the decisions taken. Builds directly on #58 (capture is confirmed, not silent) and #71 (specifications are named values, not one block of text).

## Overview

Capture today takes a listing's address and its title. Everything else the listing shows — the price, the brand, the gallery, the description, the table of measurements and materials — stays on the vendor's page, where it is only useful for as long as that page exists and says the same thing. For offshore component vendors that is not long, and the loss is not cosmetic: they routinely put the spec sheet *in* the image gallery, so the document that says what the part actually is disappears with the listing.

The obvious answers to that are all wrong, and issue #57 establishes why. Printing the page to a PDF keeps one image. Whole-page archivers keep the thumbnails, because Amazon does not load the full-size gallery images until the gallery is interacted with. Re-fetching the listing from this application never worked and never will: the browser has the vendor session, a machine on the LAN gets a bot wall.

What the probing found instead is that the full-resolution address of *every* gallery image is already sitting in the page's own data when it loads — on two of six sampled listings, more than twice as many images as the thumbnail strip shows. So the answer is not to archive the page. It is to **read the page in the browser that is already displaying it, and extract it into the catalogue**: the images become attachments, the "Product information" rows become named specifications that can be filtered on, the description becomes text that is kept, and the price and brand fill themselves in.

That reframes the feature. The output is not an archived blob to re-read later. It is catalogue data — the same data the operator would otherwise type in by hand, at the one moment they will never have better access to it.

Two properties of the existing capture flow have to be preserved through all of this, and they are the hardest part. Nothing may be written until the operator confirms — an abandoned capture leaves no trace, which is what #58 was for. And when a capture raises a question ("you may already have captured this", "that item number already names something"), nothing is written *at all*, so a dozen images and twenty specification rows have to survive that round trip and land only after the question is answered.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The listing fills the form in (Priority: P1)

The operator is on an Amazon listing for a 12 V 3 A power supply. They click the capture control in their browser. The confirmation page opens with the vendor, the item identifier, the listing title, **the price** and **the brand** already filled in — none of which they typed. They write the label description they want, and confirm.

**Why this priority**: It is the smallest slice that stands alone, it is what makes every later slice possible (the extraction has to run and reach this application before it can carry images or specifications), and it closes issue #56 points 2 and 3, which are today's live complaint that the capture control does not pull the vendor, model number or price off Amazon pages.

**Independent Test**: Capture from a real Amazon listing and verify the confirmation page arrives with price and brand populated from the page, without the operator entering them; confirm and verify both are recorded on the purchase and the product.

**Acceptance Scenarios**:

1. **Given** an Amazon listing showing a price, **When** the operator captures from it, **Then** the confirmation page's unit price is pre-filled with the listing's price and the operator does not have to type it.
2. **Given** an Amazon listing whose byline names a brand, **When** the operator captures from it, **Then** the confirmation page's manufacturer is pre-filled with that brand.
3. **Given** a capture in progress, **When** the operator changes a pre-filled value before confirming, **Then** the operator's value is what gets recorded, not the extracted one.
4. **Given** a listing whose open tab has drifted to a variant of the item, **When** the operator captures from it, **Then** what is captured is the canonical listing for the item identifier, not the drifted variant.
5. **Given** a page the extraction cannot read as a listing, **When** the operator captures from it, **Then** the confirmation page arrives filled in from the address and title exactly as it does today, and the capture is not refused.
6. **Given** a capture from a vendor other than Amazon, **When** the confirmation page opens, **Then** it behaves exactly as it does today — vendor from the host, nothing else claimed — and no extracted fields are invented.

---

### User Story 2 - Every gallery image, at full resolution (Priority: P2)

The listing is for an offshore-made DC-DC converter. Its gallery holds seven thumbnails; two of the images behind them are the pin-out drawing and the specification sheet, and the page's data actually names fourteen images in total. The operator captures the order and all fourteen are stored against the catalogue at their original resolution. When the listing is delisted six months later, the spec sheet is still here.

**Why this priority**: This is the requirement that ruled out every other approach, and the one the operator cannot reproduce by hand later. It ranks below Story 1 only because it depends on the extraction path existing.

**Independent Test**: Capture from a listing whose page data names more images than its thumbnail strip displays; confirm; and verify the number of stored images matches the page data's count and each stored image is at least as large as the resolution the gallery serves.

**Acceptance Scenarios**:

1. **Given** a listing whose data names fourteen gallery images while seven thumbnails are on screen, **When** the operator confirms the capture, **Then** fourteen images are stored.
2. **Given** a captured gallery image, **When** it is compared with the image the gallery displays, **Then** the stored copy is the original file, at a resolution no smaller than the displayed one.
3. **Given** a capture in progress, **When** the confirmation page is shown, **Then** it states how many images will be stored, before anything is written.
4. **Given** a capture where one image cannot be retrieved, **When** the operator confirms, **Then** the remaining images are stored, the capture succeeds, and the operator is told how many were not.
5. **Given** a listing naming more images than a product is allowed to hold, **When** the operator confirms, **Then** the capture succeeds up to the limit and says plainly that it stopped there.
6. **Given** an image that is not a supported file type or exceeds the size limit, **When** the capture runs, **Then** that image is skipped and reported, and the rest of the capture is unaffected.

---

### User Story 3 - "Product information" becomes something you can filter on (Priority: P3)

The listing's Product information section says the item is 6061 aluminium, 300 mm long, M8 thread, 2 mm pitch. Those land as named specifications on the product. Months later "every M8 × 2 mm thing I own" is a filter, not a memory exercise.

**Why this priority**: It is what makes a capture worth more than an archive — the difference between data that can be searched and text that has to be re-read. It sits below the images because a missing specification can be typed in from a stored image, whereas a missing image cannot be recovered at all.

**Independent Test**: Capture from a listing carrying a Product information section, confirm, and verify each name/value row is a specification on the resulting product and appears in a specification filter.

**Acceptance Scenarios**:

1. **Given** a listing with a Product information section, **When** the operator confirms the capture, **Then** each row is recorded as a named specification on the product.
2. **Given** a listing that presents its product information across more than one section, **When** the capture runs, **Then** the rows from all of them are gathered into one set.
3. **Given** two rows in the gathered set whose names differ only by case or surrounding whitespace, **When** the capture runs, **Then** they are treated as one name and the capture is not refused.
4. **Given** a capture attaching to a product that already carries a specification named `Material`, **When** the captured rows also carry `Material` with a different value, **Then** the existing value is kept and is not overwritten.
5. **Given** that same capture, **When** it carries a specification name the product does not have, **Then** that one is added.
6. **Given** a capture attaching to an existing product, **When** it completes, **Then** no specification the operator entered by hand has been removed.
7. **Given** a listing whose product information includes marketplace bookkeeping rows such as Best Sellers Rank or Date First Available, **When** the capture runs, **Then** those rows are recorded too — nothing is dropped by name.
8. **Given** a captured row whose name is longer than a specification name may be, **When** the capture runs, **Then** that row is refused and every other row still lands.

---

### User Story 4 - Keep the description the listing was sold on (Priority: P4)

The listing's description is the paragraph that explains what the thing is for, and on about half of listings it is a rich block carrying its own diagrams. The operator captures the order and that text is kept with the product, along with the images that are part of it.

**Why this priority**: It is the least structured part of the capture and the least likely to be needed, but it is free once the extraction is running and it is gone forever once the listing is.

**Independent Test**: Capture from a listing carrying a plain description and from one carrying a rich description block, and verify in each case that the description text is stored with the product and is readable there.

**Acceptance Scenarios**:

1. **Given** a listing with a plain description block, **When** the operator confirms the capture, **Then** the description text is stored with the product and is readable on the product page.
2. **Given** a listing with a rich description block instead, **When** the operator confirms the capture, **Then** its text is stored the same way.
3. **Given** a listing carrying both no description of either kind, **When** the capture runs, **Then** nothing about the description is recorded and the capture is not refused.
4. **Given** a captured description longer than a product's own description field allows, **When** it is stored, **Then** it is kept in full and the product's label description is left as the operator's own wording.
5. **Given** a rich description carrying images, **When** the capture runs, **Then** every image measuring at least 300 pixels on both edges is stored and anything smaller on either edge is left behind.
6. **Given** a rich description containing layout furniture — a 1×1 spacer, a 970×20 rule, a 16×16 bullet, a 150 px brand mark — **When** the capture runs, **Then** none of them is stored.
7. **Given** a rich description whose images cannot be measured before retrieval, **When** the capture runs, **Then** they are stored rather than discarded.

---

### User Story 5 - A question in the middle does not lose the capture (Priority: P5)

The operator captures a listing they ordered from before. Capture stops and asks whether this is a repeat of the purchase it already has, or whether the item number that already names a product really means the same product. They answer. The dozen images, the specification rows and the description are still there and land intact.

**Why this priority**: Without it the feature is unreliable exactly when the operator is buying something they have bought before, which is the common case for consumables. It is last because it only bites when a question is raised.

**Independent Test**: Capture a listing twice on the same day so the duplicate question is raised, answer it, and verify the second capture writes the same images and specification rows the first one would have.

**Acceptance Scenarios**:

1. **Given** a capture carrying images and specifications that raises the duplicate question, **When** the operator answers it, **Then** the resulting purchase and product carry the full captured set.
2. **Given** a capture that raises a question, **When** the operator closes the page instead of answering, **Then** no product, no purchase, no specification and no stored image exists as a result.
3. **Given** a capture that raises a question, **When** the question is on screen, **Then** nothing has been written yet, as it is today.
4. **Given** a capture that raises both the duplicate question and the item-number question, **When** the operator answers both, **Then** the captured set lands once, not twice.
5. **Given** a completed capture, **When** the same listing is captured again later and attached to the same product, **Then** only images whose content the product does not already hold are stored, and the operator is not left with two copies of anything.
6. **Given** a re-capture of a listing that has gained an image since the first capture, **When** it completes, **Then** that new image is stored alongside the ones already held.
7. **Given** an image the product already holds, **When** the vendor now serves it under a different address, **Then** it is still recognized as the same image and is not stored twice.

---

### User Story 6 - Paste an image straight onto a product (Priority: P6)

The operator finds a wiring diagram on a forum, or a photo in an email, that is not part of any listing. They copy the image, open the product, and paste. It is attached.

**Why this priority**: It is a small, independent convenience that composes with everything else and cannot break the capture path. It is genuinely useful for the material no listing carries, but it is manual and one image at a time, so it can never be the main path.

**Independent Test**: With an image on the clipboard, paste onto a product page and verify it is stored as an attachment on that product.

**Acceptance Scenarios**:

1. **Given** an image on the clipboard, **When** the operator pastes it on a product page, **Then** it is stored as an attachment on that product and appears without a page reload.
2. **Given** clipboard content that is not an image, **When** the operator pastes it on a product page, **Then** nothing is uploaded and no error is raised.
3. **Given** a pasted image that is not a supported file type or is too large, **When** the paste happens, **Then** the operator is told why it was refused and nothing is stored.

---

### Edge Cases

- **The tab is not on a listing at all.** The operator clicks the capture control on an Amazon order-details page or a search results page. Extraction yields no listing, and the capture must fall back to today's behaviour rather than inventing product facts from page furniture. (Issue #56 point 4 records that today's capture creates a product called "Order Details" from such a page; this feature must not make that worse, and does not claim to fix it.)
- **The listing has no price shown**, because it is out of stock or sold only through a variant selector. The price field arrives blank and the operator fills it in, as today.
- **The application cannot reach the image host.** No network, or the vendor's image service refuses. The text half of the capture is still valuable and must complete; the operator is told the images did not.
- **The vendor changes their page structure.** Extraction stops finding some or all of the listing's facts. The capture must degrade to the fields it can still read, never fail outright, because the address and title path is the one that cannot break.
- **A listing carries no Product information section.** Nothing is recorded, and the capture is not refused.
- **A captured specification name is longer than a specification name may be.** That row is refused; the rest of the capture is not.
- **A capture attaches to a product with an existing captured set** — see Story 5, scenario 5.
- **The same image appears more than once in the listing's data**, e.g. a gallery image reused in the description block, or the same source file served under two different addresses. It is stored once.
- **The vendor re-encodes an image between captures**, so the same picture arrives as different content. It is stored a second time. This is accepted: a duplicate the operator can delete beats a genuinely new image that never lands.
- **A description image whose dimensions are not knowable before it is retrieved.** It is kept rather than filtered out, on the same reasoning — an unwanted image can be deleted, a lost one cannot be recovered.
- **A listing carrying an enormous number of images.** The per-product attachment limit stops the capture cleanly rather than silently truncating.

## Requirements *(mandatory)*

### Functional Requirements

**Extraction**

- **FR-001**: The system MUST extract from an Amazon listing the operator is viewing: the listing title, the vendor item identifier, the unit price, the brand, the description text, the Product information name/value rows, and the identity of every gallery image — without the operator copying any of it by hand.
- **FR-002**: The system MUST extract from the canonical listing for the item identifier rather than from whatever variant state the operator's open tab has drifted into.
- **FR-003**: The system MUST capture every gallery image the listing's own page data names, not only those shown in the on-screen thumbnail strip.
- **FR-004**: Each captured gallery image MUST be stored at the listing's original resolution — never smaller than the resolution the gallery displays.
- **FR-005**: The system MUST capture the listing's description text whichever of the two forms it takes, and MUST NOT require both to be present.
- **FR-006**: A captured description MUST be kept in full even when it exceeds the length of the product's own label description, and MUST NOT displace the operator's label wording.
- **FR-007**: Where extraction yields nothing for a page, the capture MUST behave exactly as it does today — vendor and item identifier derived from the address, title from the page — and MUST NOT be refused.

**Landing it in the catalogue**

- **FR-008**: Every captured Product information row MUST be recorded as a named specification on the product, so that they are filterable rather than free text. Rows MUST NOT be filtered by name, including marketplace bookkeeping rows such as Best Sellers Rank, Customer Reviews or Date First Available: losing a physical fact to a filter rule is unrecoverable once the listing is gone, whereas an unwanted row can be deleted afterwards.
- **FR-009**: Where a listing presents its product information in more than one section, the system MUST gather the rows into a single set, treating names that differ only by case or surrounding whitespace as one name.
- **FR-010**: When a capture lands on a product that already has specifications, the captured rows MUST be merged, not replace the existing set. A captured value MUST NOT overwrite an existing value for the same name; only names the product does not already carry are added.
- **FR-011**: A capture MUST NOT remove any specification, attachment or field the operator entered by hand.
- **FR-012**: The system MUST allow a product to hold up to 100 attachments, raised from the current 25, because a single listing capture can contribute more than a dozen.
- **FR-013**: The system MUST present a product's images as a thumbnail grid rather than as a list of filenames, so that a captured gallery can be looked through.

**Confirmation and integrity**

- **FR-014**: Nothing MUST be written — no product, no purchase, no specification, no stored image — until the operator confirms the capture.
- **FR-015**: An abandoned capture MUST leave no trace of any kind, including no stored image bytes.
- **FR-016**: The complete captured payload MUST survive a capture that stops to ask the operator a question, and MUST be written intact once the question is answered.
- **FR-017**: The confirmation page MUST show the operator what will be written before it is written, including how many images and which specification rows.
- **FR-018**: An image MUST be stored at most once against a given owner, judged by the content of the image itself rather than by the address it came from. This holds both within one capture — a gallery image reused in the description block — and across captures, where a vendor may serve the same image under a different address.
- **FR-019**: A capture MUST NOT store a description image measuring under 300 pixels on either edge. Gallery images are not subject to this rule. Where an image's dimensions cannot be established before retrieval, it MUST be stored rather than discarded.

**Partial results and limits**

- **FR-020**: Failure to retrieve any individual image MUST NOT abort the capture. The rest MUST be stored and the operator MUST be told how many were not.
- **FR-021**: An image that is not a supported file type, or that exceeds the per-file size limit, MUST be skipped and reported rather than failing the capture.
- **FR-022**: Reaching the per-product attachment limit MUST stop the capture cleanly and say so, rather than truncating silently.

**Supplementary**

- **FR-023**: The operator MUST be able to paste an image from the clipboard onto a product page and have it stored as an attachment on that product.
- **FR-024**: Changes to what the extraction reads MUST take effect without the operator reinstalling or reconfiguring anything in their browser.

### Key Entities

- **Captured listing**: The complete set of facts read from a vendor's listing in one action — title, item identifier, price, brand, description text, product-information rows, and image references. It exists only between extraction and confirmation, and is never a stored record.
- **Product**: The catalogue entry a capture creates or attaches to. Gains the extracted brand, description text and specifications.
- **Product specification**: An existing name/value pair on a product. Product information rows and the description text land here.
- **Purchase**: The unreceived order a capture records, carrying the vendor, item identifier, listing address, listing title, price and quantity.
- **Attachment**: An image or document stored against the catalogue, with a thumbnail. Gallery images and description images land here.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a listing carrying price and brand, the operator types neither, and the capture is complete in one click plus one confirmation.
- **SC-002**: Across the six listings sampled in issue #57, 100% of the gallery images named in each listing's page data are stored — including the listings where the page data names twice what the thumbnail strip shows.
- **SC-003**: Every stored gallery image is at a resolution no smaller than the one the vendor's gallery displays.
- **SC-004**: For a listing carrying a Product information section, every one of its rows is recorded as a filterable specification on the product — the only exceptions being a row the existing specification rules already refuse — and a specification filter returns that product when queried on one of them.
- **SC-005**: A capture that is started and abandoned — at the confirmation step or at a question — leaves zero products, zero purchases, zero specifications and zero stored bytes.
- **SC-006**: A capture landing on a product that already carries specifications changes none of the values already there.
- **SC-007**: A capture that stops to ask a question and is then answered stores exactly the same set of images and specifications as the same capture that asks nothing.
- **SC-008**: A capture whose vendor page cannot be read still yields a usable confirmation page, with no fewer fields filled in than today's capture yields.
- **SC-009**: The operator can look through a captured gallery from the product page without opening the files one at a time.
- **SC-010**: A change to what is extracted reaches the operator without any action on their part beyond reloading.
- **SC-011**: Capturing the same listing twice onto the same product stores zero additional copies of any image already held.
- **SC-012**: On the sampled listing carrying 57 unique description images, no layout furniture is stored, and the resulting attachment count for the product stays within its limit.

## Assumptions

- **Amazon is the only vendor whose page is read.** Every piece of evidence in issue #57 is from Amazon, and the issue's requirement names it. Other vendors keep today's behaviour: vendor from the host, item identifier only where the address yields one. Extending extraction to another vendor is a separate feature, not a configuration knob.
- **The application is served over TLS.** Issue #54 is closed and the capture control is confirmed working against a real Amazon listing over https. Without TLS, Amazon's `upgrade-insecure-requests` breaks the path this feature builds on.
- **The operator's browser holds the vendor session.** The application cannot fetch a listing page itself — a LAN host gets a bot wall — so extraction happens where the page is already displayed.
- **Image bytes can be retrieved by the application from the vendor's image host without a session.** Issue #57 verified this against the image CDN from a different host with no cookies. If it stops holding, the browser can read the bytes and send them instead; that is a change of transport, not of what this specification requires.
- **A capture carries roughly a dozen images and a few megabytes.** The sampled listings ranged from 3 to 16 images at around 350 KB each.
- **Where the extraction code runs — a script the browser loads from this application, or a browser extension — is a planning decision**, not a requirement. Issue #57 recommends the former and records the evidence; either satisfies this specification.
- **Which record owns the captured images — the product or the purchase — is deferred to planning**, per issue #57's decisions. Specifications and description text go on the product either way, because a specification has no other owner.
- **The captured description is stored as a named specification** rather than in the product's own description field, which is limited to 255 characters and holds the operator's label wording.
- **Existing attachment handling is reused.** Supported file types, the per-file size limit and thumbnail generation are already in place and this feature does not change them.
- **Capture errs toward taking too much.** Where a rule could either discard something useful or keep something unwanted, it keeps it. The listing is available exactly once and an unwanted specification row or image can be deleted at leisure, so every judgement call in this specification — taking all product-information rows, keeping unmeasurable images, storing a re-encoded duplicate — resolves the same way. Tightening any of these later is a cleanup; loosening them later recovers nothing.
- **The 300-pixel description-image threshold is a filter on layout furniture, not on size.** Requiring it on *both* edges is what does the work: spacers, rules, bullets and brand marks are tiny or extreme in aspect ratio, while a genuine content image in a rich description module is roughly rectangular and at least 300 px square. A long-edge threshold would keep dividers and discard real 300×300 module photographs.

## Out of Scope

- **Archiving the page as a document** — printing to PDF, whole-page archivers, or saved HTML. Ruled out by issue #57: they capture thumbnails, not the gallery.
- **Re-fetching a listing from this application.** Never viable; the bot wall is on the HTML origin.
- **Refreshing a capture later**, on a schedule or on demand, to see what the listing now says.
- **Extraction for vendors other than Amazon.**
- **Issue #56 points 1, 4, 5 and 6** — editing a purchase date, the order-details page creating a junk product, the internal code format, and deleting products. Points 2 and 3 are closed by this feature as a consequence of Story 1.

## Dependencies

- **#71 — structured specifications** (merged). Provides the name/value specification rows that captured product information lands in.
- **#58 — order capture confirmation** (merged). Provides the confirmation step, the decision questions, and the guarantee that an abandoned capture writes nothing — all of which this feature must carry a larger payload through.
- **#54 — TLS** (closed). Without it the browser-side capture control cannot reach this application from an Amazon page.
- **Existing attachment storage**, including thumbnails and supported file types.
