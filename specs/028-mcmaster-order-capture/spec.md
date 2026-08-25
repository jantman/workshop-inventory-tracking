# Feature Specification: McMaster-Carr Order and Product Capture

**Feature Branch**: `issues/119`

**Created**: 2026-08-24

**Status**: Draft

**Input**: GitHub issue #119 — "Handle McMaster-Carr Items / Orders": *"Ideally we should also be able to capture Products ordered from McMaster-Carr, as well as McMaster-Carr orders. Note that McMaster's API requires human review of applications, and we can consider it a certainty that they won't approve an individual hobbyist for API access, so we'll need to rely on the bookmarklet."*

## Overview

The catalog has two capture paths, and each was built to a different vendor's shape.

Amazon's is one listing, one click, one purchase, read out of the page by a bookmarklet — because Amazon publishes nothing and the page is the only place the data exists. DigiKey's is one sales order number, thirty lines, thirty purchases, read out of DigiKey's own published data — because DigiKey publishes everything and a page is a thing that goes stale.

McMaster-Carr is the third shape, and it is the awkward one. An order is DigiKey-shaped: a dozen lines placed in one checkout, arriving weeks later as a dozen bags in one box, each bag anonymous until someone reads its label. But the data is Amazon-shaped, which is to say there is none the workshop can have. McMaster does publish an interface; reaching it requires an application review, and the issue settles that question for us: a one-person hobby workshop is not going to pass it. So a McMaster order has to be read the one way that is left — off the page the operator is already looking at, by the bookmarklet the catalog already hands out.

That combination is what is new. Every capture the catalog performs today either reads *one* thing off a page or reads *many* things from a service. Nothing reads many things off a page, and the difference is not cosmetic:

- **The review cannot re-read.** DigiKey's confirmation step fetches the order again and treats the fetched order as the authority, so the form it submits carries only the operator's decisions. There is nothing for a McMaster confirmation to fetch. What the bookmarklet read has to travel with the review and has to be what gets written — which makes the review the only record of the read, and makes "nothing is written until the operator confirms" a promise about a page that can no longer reconstruct itself.
- **Extraction is per-line and every line is fallible.** A selector that stops matching costs one field on Amazon. On an order page it can cost one field on twelve lines, or cost the line count itself. What the operator is told when that happens is not a footnote; it is the difference between a capture they can trust and one they have to audit by hand.
- **A McMaster part number is usually the only name a part has.** McMaster sells to its own specification and mostly does not name a manufacturer. Where a DigiKey capture writes a manufacturer part number and a distributor part number, a McMaster capture will often have exactly one identifier to write, and it is McMaster's.

What this feature does *not* change is everything the two existing capture paths already decided, because those decisions were right and are not McMaster-specific: nothing is written until the operator confirms it; the label description is authored while the vendor's data is on screen; anything the system is unsure about is put in front of the operator as a choice rather than resolved behind their back; and a value the operator typed always beats a value a selector found.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Capture a whole McMaster order from its page (Priority: P1)

The operator has just placed a McMaster order — fourteen lines, mostly fasteners. With the order's page open in the browser, they click the capture bookmarklet. A tab opens on the catalog showing every line of that order: McMaster's part number, McMaster's description of it, how many were ordered, what each cost, and whether the catalog already holds the part. They write the label description for the lines that are new, untick the two lines they do not want cataloged, and confirm. Twelve outstanding purchases exist, filed against the right products, all carrying the McMaster order number — and the only thing typed was twelve short descriptions.

**Why this priority**: It is the whole of the issue's second half and the entry point for everything else in this feature — there is nothing to receive against until an order has been captured. On its own it already pays: the purchases are recorded, the reorder list stops suggesting things that are on the way, and the parts are in the catalog before the box is.

**Independent Test**: With a saved copy of a real McMaster order page, run the capture, confirm the review, and verify that every included line became exactly one outstanding purchase against a product carrying that line's McMaster part number, with the quantity and unit price the page stated.

**Acceptance Scenarios**:

1. **Given** a McMaster order page open in the browser, **When** the operator clicks the capture bookmarklet, **Then** the catalog opens a review listing every line the page carried — McMaster part number, McMaster's description, quantity, unit price — together with the order's number and date, and nothing has been recorded yet.
2. **Given** that review, **When** the operator confirms it, **Then** one purchase is recorded per included line, each carrying the vendor `McMaster-Carr`, the order's number, the order's date, the line's quantity and the line's unit price.
3. **Given** a line whose McMaster part number already names a product in the catalog, **When** the review is shown, **Then** that line names the matched product, offers to attach the purchase to it, and does not offer to author a new description for it.
4. **Given** a line whose part the catalog has never seen, **When** the review is shown, **Then** the line offers an editable label description pre-filled from McMaster's description, and confirming creates a product carrying it.
5. **Given** a line the operator does not want cataloged — a tool, a consumable, a shipping or handling charge — **When** they exclude it and confirm, **Then** that line produces neither a product nor a purchase, and every other line is captured normally.
6. **Given** the review page, **When** the operator closes the tab without confirming, **Then** no product, no purchase and no stored file exists as a result.
7. **Given** an order captured a moment ago, **When** the operator clicks the bookmarklet on the same order page again, **Then** the review shows every already-captured line as already captured, offers only what is new, and confirming an unchanged order records nothing.
8. **Given** a captured order, **When** the operator opens it, **Then** they see every line with its product, quantity, unit price and state, and how many of the order's lines are still outstanding.

---

### User Story 2 - Capture one McMaster part from its product page (Priority: P2)

The operator is looking at a McMaster product page — a bearing they are about to order, or one they already have in a drawer unlabelled. They click the same bookmarklet they use on Amazon. The confirmation page comes up already carrying McMaster's part number, McMaster's description, the price and what a pack holds, the specification table off the page, and the product image. They write their own label description over McMaster's, say where it goes, and capture.

**Why this priority**: It is the issue's first half, and today it is the visibly broken case — clicking the bookmarklet on a McMaster page yields the vendor name and the address and nothing else, because every selector it knows is Amazon's. It ranks below Story 1 because a single part can be typed in by hand in a minute, whereas a fourteen-line order cannot.

**Independent Test**: With a saved copy of a real McMaster product page, run the capture and verify the confirmation page arrives carrying the part number, description, price, pack size, specifications and image without anything being typed, and that confirming creates the product with those values.

**Acceptance Scenarios**:

1. **Given** a McMaster product page, **When** the operator clicks the bookmarklet, **Then** the confirmation page carries McMaster's part number, McMaster's description of the part, its price, the specification rows the page shows and the product image — and nothing has been recorded yet.
2. **Given** that confirmation page, **When** the operator confirms it, **Then** a product is created carrying those values, with the McMaster part number recorded as a `DISTRIBUTOR` identifier scoped to McMaster-Carr, so that scanning or searching that number finds it.
3. **Given** a page that prices the part per pack, **When** the confirmation page is shown, **Then** the amount paid and the units in the pack are both filled in from the page, and the unit price is worked out from them exactly as it is for a multi-pack captured from any other vendor.
4. **Given** a part number the catalog already holds, **When** the operator captures it, **Then** the existing duplicate handling applies unchanged: the operator is shown the product it matched and must choose before anything is written.
5. **Given** the operator types their own label description over McMaster's, **When** they capture, **Then** the product carries theirs, and McMaster's is kept with the captured listing detail rather than discarded.
6. **Given** a McMaster product address pasted into the paste-a-URL form instead, **When** the operator captures it, **Then** the vendor is `McMaster-Carr` and the McMaster part number is read out of the address, exactly as an Amazon address yields an ASIN today.
7. **Given** an Amazon listing, **When** the operator clicks the bookmarklet, **Then** the capture behaves exactly as it does today, in every respect.

---

### User Story 3 - See the order, and receive the box against it (Priority: P3)

Two weeks later the box arrives. The operator takes out a bag and scans the part number off its label; the catalog knows that number is line three of an order it captured a fortnight ago, and lands them on that line's receipt with the product and the order named. One confirmation, the count goes up, the label prints. Next bag. Where the label will not read, or where the same part is outstanding on two orders, they fall back to the order screen and work down it by hand. When the box is empty, what is still outstanding is what McMaster did not ship — visible at a glance instead of inferred.

**Why this priority**: It is the payoff Story 1 was performed for, and it is what turns a captured order from a record into a workflow. It ranks third because Stories 1 and 2 both deliver on their own and this one delivers nothing without Story 1.

**Independent Test**: Capture an order, scan the part number of one of its lines, and verify the scan lands on that line's receipt rather than on the product page; confirm it and verify the purchase is received, the product's counted quantity rose, and the order screen's outstanding count fell by one.

**Acceptance Scenarios**:

1. **Given** a captured McMaster order, **When** the operator opens it, **Then** every line shows its product, quantity, unit price and whether it is outstanding or received, with a count of each.
2. **Given** an outstanding line, **When** the operator marks it received from the order screen and amends the quantity, **Then** the purchase is recorded as received with the amended quantity, a counted product's quantity rises by it, and any manual low or out flag on the product is cleared — exactly as receiving a purchase does today.
3. **Given** a line that is already received, **When** the operator returns to the order screen, **Then** it is shown as received and cannot be received a second time.
4. **Given** an order with the same part on two lines, **When** the operator receives one of them, **Then** the other is unaffected and both remain individually identifiable.
5. **Given** a bag whose McMaster part number names exactly one outstanding line of a captured order, **When** the operator scans that part number, **Then** they land on the receipt for that line, naming the product and the order.
6. **Given** a part number naming outstanding lines on more than one captured order, **When** it is scanned, **Then** the candidates are shown and the operator chooses; the catalog MUST NOT pick one.
7. **Given** a part number that names no outstanding McMaster line — never captured, already received, or excluded at capture — **When** it is scanned, **Then** the scan behaves exactly as it does today.

---

### User Story 4 - Be told what the page did not give up (Priority: P4)

McMaster redesigns. The next order capture comes back with the lines intact but every price blank, or with three lines where the page shows fourteen. The operator is told which fields came back empty and how many lines were read, on the review, before they confirm anything — and the capture still works for everything that did read.

**Why this priority**: It is not a feature the operator wants, it is the difference between noticing a bad capture now and finding it in six months in the price history. It ranks last because a working extraction makes all of it invisible, and because none of it is worth building before there is something to extract.

**Independent Test**: Run a capture against a saved order page with the price markup removed, and verify the review states that prices could not be read, still offers every line, and captures them with the quantity and part number intact.

**Acceptance Scenarios**:

1. **Given** an order page whose lines read but whose prices do not, **When** the review is shown, **Then** it says prices could not be read, leaves those fields empty and editable, and confirming captures the lines without prices.
2. **Given** an order page nothing recognizable can be read from, **When** the operator clicks the bookmarklet, **Then** they are told plainly that the page yielded no order lines, and are offered the ordinary hand-entry path carrying the address they came from — never an error page and never an empty review that looks like an empty order.
3. **Given** any page that is not a McMaster order page or product page, **When** the operator clicks the bookmarklet, **Then** the existing behaviour for that page is unchanged.
4. **Given** a review stating that some lines came back incomplete, **When** the operator confirms it, **Then** the resulting flash names what was incomplete, so the record of it survives leaving the review page.

---

### Edge Cases

- **A line's price is stated per pack, not per unit.** The review shows what the page stated and what the pack holds, and the recorded unit price is worked out from the two — the same arithmetic the confirmation page already performs for a multi-pack, and never a silently rounded price. Where the division does not come out even, the operator is told, as they are today.
- **The order page is behind a login that has expired.** The bookmarklet runs in the operator's own browser session, so this shows up as a page with no order on it. Handled by US4 scenario 2: nothing recognizable read, said plainly, no empty review.
- **The order is captured twice.** A McMaster order number is an exact key. A re-capture recognizes the lines it already recorded, shows them as already captured, and offers only what is new — so recapturing an unchanged order records nothing.
- **The order changed after it was captured** — a line cancelled, a quantity adjusted, a backorder split. Re-capturing reconciles: a new line is offered, a changed quantity or price is shown against what is recorded and applied only if the operator says so, and a line that has vanished from the page is reported rather than deleted. A purchase the operator can see and cancel beats one that disappears.
- **Two lines of one order are the same part.** Both are shown and both can be captured; they become two purchases against one product, which is what they are. Receiving one does not receive the other. Because the page is read once and cannot be re-read, each line's identity within the order must be recorded at capture — pairing lines to purchases by position at a later re-capture is what corrupted data the last time it was tried.
- **A line has no part number** — a shipping charge, a handling fee, a cut-to-length service. It is shown, it can be excluded, and it can be captured on its description alone. Nothing is refused for a missing part number.
- **A McMaster part number already names a different product.** Treated exactly as a recycled Amazon item number is today: the review names the existing product, shows its description, and requires a choice before anything is written.
- **McMaster's description is longer than a label description may be.** The review refuses an over-long description at the point of entry, with the limit stated, and pre-fills with a value that fits. A silently truncated description is a wrong label.
- **A line arrives in two shipments.** A purchase is received or it is not; this feature adds no partial state. The operator receives the line when the last of it arrives, or receives it with what actually turned up and records the rest as its own purchase. Both are visible; neither is silent.
- **The catalog is served over plain HTTP on the LAN and McMaster's page is HTTPS.** The same constraint the Amazon bookmarklet already lives with, and the same answer: the capture leaves the vendor's page as a form submission into a new tab, not as a background request.
- **The order page renders its lines after the page loads.** The bookmarklet is clicked by a human who can see the lines, so what it reads is what is on screen. A page still loading yields fewer lines than it shows, which is why the review states how many lines it read.
- **A price in a currency other than the account's.** Recorded exactly as stated, to the cent, with no conversion. The catalog has never converted currency and this feature does not start.
- **The same part is outstanding on two different captured orders.** The scan names both and the operator chooses. The catalog does not guess, and it does not prefer the older order or the larger quantity — either preference would be wrong often enough to be worse than asking.
- **A bag's label will not scan, or the part number on it is worn off.** The order screen is the fallback and always works: find the line, receive it there, amend the quantity there. Nothing about receiving depends on a label being readable.
- **A bag is scanned for a line that was already received.** There is no outstanding line left to match, so the scan behaves as it does for any known product — which says plainly that this part is in the catalog and offers what today's scan offers. Nothing is received twice.
- **The operator confirms a review much later, from a stale tab.** The review carries what was read; confirming it writes what was read. Nothing is silently refreshed underneath them, and re-capturing from the live page is how they pick up a change.

## Requirements *(mandatory)*

### Capturing an order

- **FR-001**: The operator MUST be able to capture a whole McMaster-Carr order by clicking the existing capture bookmarklet while a McMaster order page is open, with no order number typed and no per-line action. The page read is the order's own page in McMaster's order history, which is re-openable and is therefore what makes re-capture possible.
- **FR-002**: The capture MUST read the order from the page in the operator's own browser session, because McMaster's published interface is not available to this workshop. It MUST NOT require credentials, an account registration, or any configuration held by the application.
- **FR-003**: The capture MUST present every line the page yielded for review — McMaster part number, McMaster's description, quantity and unit price — together with the order's number and its date, before anything is recorded.
- **FR-004**: The review MUST state how many lines it read, so that a page that yielded three of fourteen is visibly that rather than a short order.
- **FR-005**: Nothing MUST be recorded until the operator confirms the review. An abandoned review MUST leave no product, no purchase and no stored file.
- **FR-006**: Because the vendor cannot be re-read at confirmation time, what the review displays MUST be what confirming it writes, carried through the confirmation without a second read of any page.
- **FR-007**: The review MUST state, for each line, whether the catalog already holds a product for it, and MUST name that product.
- **FR-008**: The review MUST let the operator author the label description for each line that would create a new product, pre-filled with McMaster's description.
- **FR-009**: The review MUST let the operator exclude any line, and an excluded line MUST produce neither a product nor a purchase while every other line is captured normally.
- **FR-010**: Confirming a review MUST record one purchase per included line, against the matched or newly created product, carrying the vendor `McMaster-Carr`, the line's quantity, the line's unit price, the order's date and the order's number.
- **FR-011**: A purchase recorded by this capture MUST be outstanding — not received — regardless of whether the order has already shipped.
- **FR-012**: A product created by this capture MUST carry the line's McMaster part number as a `DISTRIBUTOR` identifier scoped to McMaster-Carr, and MUST carry a manufacturer part number as an `MPN` identifier only where the page actually stated one.
- **FR-013**: The catalog MUST record the McMaster order number against each captured purchase in a field of its own, such that all of an order's purchases can be found from it. It MUST NOT be kept only as free text in a note.
- **FR-014**: The catalog MUST record, against each captured purchase, which line of that order it came from, and MUST NOT rely on position or part number to re-establish that pairing later. An order can carry the same part twice.
- **FR-015**: A capture MUST NOT record a second purchase for a line it has already captured from the same order number.
- **FR-016**: Re-capturing an order MUST show which of its lines are already captured, offer any line that is not, and report any previously captured line the page no longer carries without deleting it.
- **FR-017**: Where a re-capture finds a changed quantity or unit price on an already-captured line, it MUST show the change against what is recorded and apply it only if the operator confirms it.
- **FR-018**: Where a line's McMaster part number already names a product whose identity contradicts the line's, the capture MUST name that product and require a choice — attach to it, or create a separate product — before writing anything.
- **FR-019**: A line with no part number MUST be capturable on its description alone, or excludable, and MUST NOT cause the capture to be refused.
- **FR-020**: Where a line's price is stated for a pack rather than for a unit, the recorded quantity MUST be the number of *units* the line brings in — packs ordered multiplied by the pack size — and the recorded unit price MUST be the price of one unit, worked out from the pack price and the pack size as a decimal amount to the cent.
- **FR-020a**: The review MUST show the packs, the pack size, the pack price and the resulting unit quantity and unit price together, and MUST let the operator overrule either computed value before confirming. Where the division does not come out even, it MUST say so rather than round silently.

### Capturing a single product

- **FR-021**: The operator MUST be able to capture a single McMaster part by clicking the same bookmarklet on a McMaster product page, and MUST NOT have to choose between two bookmarklets or two entry points.
- **FR-022**: A product-page capture MUST present for confirmation the McMaster part number, McMaster's description, the price, the pack size where the page states one, the page's specification rows and the product image — before anything is recorded.
- **FR-023**: A product-page capture MUST let the operator author their own label description over McMaster's, and MUST keep McMaster's with the captured listing detail either way.
- **FR-024**: The page's specification rows MUST be recorded as the product's specifications, and MUST NOT overwrite a specification of the same name the operator has already edited by hand.
- **FR-025**: A McMaster part number MUST be readable from a McMaster product address alone, so that the paste-a-URL form yields it without the bookmarklet, exactly as an Amazon address yields an ASIN today.
- **FR-026**: Where the catalog already holds a product for the part, the existing duplicate handling MUST apply unchanged — the operator is shown the match and chooses.

### Seeing and receiving an order

- **FR-027**: The operator MUST be able to open a captured McMaster order and see all of its lines, each showing its product, quantity, unit price and whether it is outstanding or received.
- **FR-028**: A captured order MUST show how many of its lines are still outstanding.
- **FR-029**: The operator MUST be able to mark any outstanding line received from the order screen, amending its quantity there, with the same effect receiving a purchase has today — the purchase is received, a counted product's quantity rises by the received quantity, and a manual low or out flag is cleared.
- **FR-030**: A line that is already received MUST be shown as received and MUST NOT be receivable a second time.
- **FR-031**: A McMaster order number that names no captured order MUST render as "not captured", with a way forward, rather than as an error or a 404.
- **FR-032**: Scanning a McMaster part number that names exactly one outstanding line of a captured McMaster order MUST take the operator to the receipt for that line, with the ordered quantity offered and editable.
- **FR-032a**: Where such a scan names outstanding lines on more than one captured order, the catalog MUST show the candidates and let the operator choose, and MUST NOT pick one.
- **FR-032b**: Where such a scan names no outstanding McMaster line, the scan MUST behave exactly as it does today — the product opens if the catalog holds it, and the create-a-product path is offered if it does not.

### Not breaking what exists

- **FR-033**: Every existing capture path MUST behave exactly as it does today: the Amazon bookmarklet capture, the paste-a-URL capture, the DigiKey order and part captures, scanning, manual purchase entry and receiving.
- **FR-034**: The operator MUST continue to use one bookmarklet for all vendors, and MUST NOT have to re-drag it to get McMaster support.
- **FR-035**: Where the bookmarklet is clicked on a page it does not recognize as a McMaster order or product page, the capture MUST behave exactly as it does today for that page.
- **FR-036**: A field that cannot be read MUST cost that field alone. No unreadable field may cost another field, another line, or the capture.
- **FR-037**: The review MUST name which fields or lines came back incomplete, and confirming MUST carry that statement forward, so the operator knows which records to look over after leaving the page.
- **FR-038**: A page from which no order line can be read MUST produce a plain statement to that effect and a way forward, and MUST NOT produce an empty review that is indistinguishable from an order with no lines.
- **FR-039**: A capture that fails for any reason MUST leave nothing partially recorded, and MUST be safe to retry.

### Key Entities

- **McMaster Order**: One order placed with McMaster-Carr, identified by its order number, carrying an order date. Its lines are the purchases captured from it; like a DigiKey order it is derived from those purchases rather than stored as a record of its own.
- **Order Line**: One line of that order — a McMaster part number, a description, a quantity and a price. Captured, it becomes one Purchase against one Product; excluded, it becomes nothing. Its position within the order is part of its identity, because two lines can name the same part.
- **Purchase**: The existing record of one acquisition of one product. Gains a McMaster order number in the same first-class field a DigiKey sales order number already occupies, and a record of which line of that order it came from.
- **Product**: The existing record of a distinct kind of thing the workshop holds. Its identity is its own record and never a vendor's part number.
- **Product Identifier**: The existing coded names a product carries. This feature writes `DISTRIBUTOR`, scoped to McMaster-Carr, for the McMaster part number, and `MPN` only where a manufacturer part number was actually stated.
- **Captured Listing**: The existing carrier for what was read off a vendor's page — title, price, brand, description, specifications and images. This feature gives it a second vendor's markup to read and a many-line variant to carry, without changing what it means.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A fourteen-line McMaster order is captured — read, reviewed, described and confirmed — in under five minutes, with nothing typed that the order page already stated.
- **SC-002**: Every line of a captured order becomes exactly one outstanding purchase or one deliberately excluded line. No line is silently dropped and no line produces two purchases.
- **SC-003**: Capturing the same unchanged order a second time records nothing new.
- **SC-004**: Every line whose part the catalog already holds attaches to that existing product; none creates a duplicate.
- **SC-005**: A McMaster product captured from its page arrives with its part number, description, price and specifications filled in without the operator typing any of them.
- **SC-006**: Receiving a bag whose part is outstanding on exactly one captured order takes one scan and one confirmation, with no typing and no searching.
- **SC-007**: At any point during unpacking, the operator can see from one screen how many of an order's lines are still outstanding and which they are.
- **SC-008**: With McMaster's markup changed so that a given field no longer reads, every other field on every line still captures, and the operator is told which field was lost before they confirm.
- **SC-009**: No failed or abandoned capture leaves a partial record behind — measured as: after any failure or abandonment, the number of products and purchases is unchanged.
- **SC-010**: Every capture, scan and receiving workflow that worked before this feature works identically after it, demonstrated by the existing test suite passing unchanged.

## Assumptions

- **The bookmarklet is the only source, by the issue's own instruction.** No McMaster credentials, no application registration, no configuration. This is a deliberate departure from the DigiKey feature's premise and it is what forces the read-once, carry-the-payload design.
- **Reading a vendor's markup is accepted as fragile.** The Amazon capture already made this trade and bounded it the same way: an independent, optional extraction per field, so a selector that stops matching costs one field. This feature extends that bound to lines and adds the requirement that the loss be *stated*, because a missing field on one of fourteen lines is not something the operator will notice.
- **The order is captured from its page in McMaster's order history**, not from the confirmation shown at checkout. The user chose this: the history page can be re-opened, and re-opening it is the whole mechanism by which a re-capture reconciles a cancelled line or a changed quantity. A confirmation page is a one-shot read that would have needed the history page for re-capture anyway.
- **Pack-priced goods are counted in units, not packs.** The user chose this: what gets used, and what the low-stock flag has to mean, is individual screws. A line ordered as two packs of fifty is recorded as a quantity of one hundred at the per-unit price. The pack figures are shown on the review so the arithmetic is checkable, but the pack is not what the catalog counts.
- **Receiving is scanned by part number, not by order.** The user chose this: a McMaster bag's label names the part, and that is enough to find the outstanding line as long as the catalog is willing to say when it is not sure. The rule is the one the DigiKey feature already set — one match goes straight to the receipt, several are shown as candidates for the operator to choose between, and none falls back to today's behaviour. This is why FR-014's stored line identity matters even for receiving: two lines of one order naming the same part are two candidates, not one.
- **A McMaster part number is usually the only identifier a part has.** McMaster sells to its own specification and mostly does not name a manufacturer, so the part number is recorded as a distributor identifier scoped to McMaster-Carr and a manufacturer part number is written only when the page states one. This is the opposite of the DigiKey case, where the manufacturer part number is the primary name.
- **Capture happens when the order is placed, not when it arrives** — that is the point of capture, and it is what makes the reorder list's "on the way" marking correct. Capturing an order that has already arrived is allowed and works; its lines are simply received immediately afterwards.
- **Receiving stays all-or-nothing per line.** The existing model represents outstanding as "no received date", with no partial state, and adding one would touch every screen that reads a purchase. Split shipments are handled by the operator, visibly, per the edge case above.
- **The vendor is recorded as `McMaster-Carr`**, matching what the catalog already derives from a `mcmaster.com` address. No existing records are rewritten by this feature.
- **Pack pricing reuses the arithmetic already on the confirmation page.** The amount paid and the units in the pack yield a unit price to the cent, exact and never binary floating point (Constitution III), with the inexact-division statement shown as it is today.
- **The order's line identity is stored, not re-derived.** The DigiKey capture learned this the expensive way: pairing lines to purchases by position corrupted data the first time a part appeared on two lines. Reading a page rather than a service makes it worse, not better, because a page's line ordering is not a contract.
- **Single operator, LAN-only, as ever.** No accounts, no roles, no queues, no background jobs, no scheduled re-scraping. A capture is a thing the operator clicks and waits a couple of seconds for.
- **Saved copies of real McMaster pages are the test fixtures**, the way saved Amazon listings already are. There is no live vendor call in any test.
