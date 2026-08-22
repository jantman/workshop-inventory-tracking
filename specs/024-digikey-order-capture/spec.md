# Feature Specification: DigiKey Order Capture and Receiving

**Feature Branch**: `issues/108`

**Created**: 2026-08-22

**Status**: Draft

**Input**: GitHub issue #108 — "Handle Digi-Key Orders": *"This application needs a process for capturing DigiKey Products and Orders and then receiving them. I know we have scanning enabled ... but we need a way to capture products and orders and receive them, similar to Amazon (but leveraging whatever DigiKey provides for this)."* The issue quotes a real bag label from a recent order as the worked example.

## Overview

Order capture exists because the vendor's listing is in front of the operator when the order is placed and gone by the time the box arrives. For Amazon that worked out to one listing, one click, one purchase — which is the shape the whole capture flow has today.

A DigiKey order is not that shape. It is thirty lines placed in one checkout, each a different part, and the operator is not going to run thirty captures. Worse, the parts arrive weeks later as thirty anonymous bags in one box, and the only thing that says which bag is which is the 2D label stuck to it. The catalog already reads those labels — it has read them since the first release — but it reads them in the only way available to it, which is to offer a blank product draft filled in from the label. The label knows it is line 14 of sales order 100882558; the catalog does not, because nothing ever told it that sales order 100882558 exists. So every bag gets typed up as though it were the first time anyone had seen the part, and what was ordered is never reconciled against what turned up.

DigiKey, unlike Amazon, publishes the data. An order can be read back by its sales order number: every line, with the DigiKey part number, the manufacturer part number, the quantity and what was paid. A part can be read back by its part number: manufacturer, description, datasheet, photograph, category and its full parametric detail. None of it has to be scraped off a page, and none of it goes stale when DigiKey redesigns their site.

This feature makes the order the unit of capture. One sales order number, entered once, becomes a confirmed set of outstanding purchases — one per line, each attached to a product the catalog either already holds or creates on the spot. Weeks later the box arrives, and receiving is a scan per bag: the label names its sales order and its part, which is exactly enough to find the one outstanding line it belongs to and receive it. What is left outstanding after the last bag is what DigiKey did not ship, and the operator can see that at a glance instead of inferring it.

Everything the existing capture flow decided is kept: nothing is written until the operator confirms it, the label description is authored while the data is on screen, and anything the system is unsure about is put in front of the operator as a choice rather than resolved behind their back.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Capture a whole order from its sales order number (Priority: P1)

The operator has just placed a 24-line order on DigiKey. Instead of running 24 captures, they enter the sales order number once. The catalog reads the order back, and shows every line: the DigiKey part number, the manufacturer and part number, how many were ordered, what each cost — and, for each line, whether this is something the catalog already holds. The operator writes the label description for the lines that are new, ticks off any line they do not want cataloged, and confirms. Twenty-four outstanding purchases exist, filed against the right products, and nothing had to be typed twice.

**Why this priority**: It is the entry point for everything else in this feature — receiving has nothing to match against until an order has been captured — and it is the part that removes the work the issue is actually complaining about. On its own it already delivers value: the outstanding orders are recorded, the reorder list stops suggesting things that are on the way, and the parts are cataloged before they arrive.

**Independent Test**: Capture a known sales order number, confirm the review page, and verify that every line of the order became an outstanding purchase against a product carrying the line's manufacturer part number and DigiKey part number, with the quantity and unit price DigiKey reported.

**Acceptance Scenarios**:

1. **Given** a sales order number for an order on the connected account, **When** the operator enters it, **Then** the catalog shows a review listing every line — DigiKey part number, manufacturer, manufacturer part number, DigiKey's description, quantity ordered and unit price — and nothing has been recorded yet.
2. **Given** that review, **When** the operator confirms it, **Then** one outstanding purchase is recorded per included line, each carrying the vendor `DigiKey`, the order's sales order number, the order date, the line's quantity and the line's unit price.
3. **Given** a line whose manufacturer part number already names a product in the catalog, **When** the review is shown, **Then** that line names the matched product, offers to attach the purchase to it, and does not offer to author a new description for it.
3a. **Given** any line of the order, **When** the review is shown, **Then** it also carries DigiKey's own detail for that part — the manufacturer, the category, the datasheet and the parametric detail — none of which the order line itself supplies (FR-040).
3b. **Given** a line whose part detail cannot be read, **When** the review is shown, **Then** the line is still offered, marked as having come back without that detail, and confirming captures it on what the order gave (FR-041).
4. **Given** a line whose part the catalog has never seen, **When** the review is shown, **Then** the line offers an editable description pre-filled from DigiKey's description of the part, and confirming creates a product carrying it.
5. **Given** a line the operator does not want in the catalog at all — a tool, a consumable, a shipping charge — **When** they exclude it on the review and confirm, **Then** no product and no purchase result from that line, and every other line is captured normally.
6. **Given** the review page, **When** the operator closes the tab without confirming, **Then** no product and no purchase exist as a result.
7. **Given** a captured order, **When** the operator opens it, **Then** they see every line with its state — outstanding or received — and how many of the order's lines are still outstanding.

---

### User Story 2 - Receive the box one bag at a time, by scanning (Priority: P2)

Two weeks later the box arrives. The operator takes out a bag, scans the label in the header scan box, and lands directly on the receipt for that line of that order — the right product, the right purchase, the quantity the label says is in the bag. One confirmation and it is received, the count goes up, and the label prints. Next bag. When the box is empty, the order screen says whether anything is still outstanding.

**Why this priority**: It is the payoff — the moment the capture in Story 1 was performed for. It ranks second only because it is worthless without a captured order to receive against.

**Independent Test**: Capture an order, then scan a bag label carrying that order's sales order number and one of its DigiKey part numbers, and verify the scan lands on the receipt for that specific outstanding line rather than on a blank product draft.

**Acceptance Scenarios**:

1. **Given** a captured order with an outstanding line for a DigiKey part number, **When** a bag label carrying that sales order number and that part number is scanned, **Then** the catalog opens the receipt for that line, naming the product and the order.
2. **Given** that receipt, **When** the label states a quantity, **Then** the quantity offered is the label's, editable, rather than the quantity that was ordered.
3. **Given** that receipt, **When** the operator confirms it, **Then** the purchase is recorded as received, the product's counted quantity rises by the received quantity if it is being counted, and any manual low/out flag on the product is cleared — exactly as receiving does today.
4. **Given** a captured order part-way through unpacking, **When** the operator opens it, **Then** the lines already received are distinguished from those still outstanding, with a count of each.
5. **Given** a bag label that scans as the right part but names a sales order the catalog has not captured, **When** it is scanned, **Then** the existing behaviour is unchanged — the part's product opens if the catalog holds it, and a draft filled in from the label is offered if it does not.
6. **Given** a captured order with an outstanding line, **When** the bag's label is torn or will not read, **Then** the operator can mark that line received from the order screen and amend its quantity there, with the same result as scanning it.
7. **Given** a line that has already been received, **When** its bag is scanned a second time, **Then** the catalog says the line is already received, names it, and does not receive anything twice.
8. **Given** a bag whose label names a captured order and a part number that order does not contain, **When** it is scanned, **Then** the catalog says so plainly and falls back to the existing part-based behaviour rather than guessing at a line.

---

### User Story 3 - Catalog a single DigiKey part without an order (Priority: P3)

The operator is holding a part that came from somewhere else, or is looking at a DigiKey product page and wants it in the catalog before ordering. They give the catalog the DigiKey part number — typed, pasted as a product-page address, or scanned off a bag — and get a filled-in product: manufacturer, manufacturer part number, DigiKey part number, DigiKey's description, the datasheet, the photograph, the category and the part's parametric detail. They write their own label description over the top of DigiKey's and save.

**Why this priority**: It is real value and it is what makes today's scan-a-bag draft worth having, but the operator can already type a part in by hand — slowly. Stories 1 and 2 remove work that currently has no alternative at all.

**Independent Test**: Enter a DigiKey part number for a part not in the catalog, and verify the resulting draft carries the manufacturer, manufacturer part number, DigiKey part number and description without anything being typed, and that confirming it creates the product with those values.

**Acceptance Scenarios**:

1. **Given** a DigiKey part number for a part the catalog does not hold, **When** the operator captures it, **Then** a review is shown carrying the manufacturer, manufacturer part number, DigiKey part number, description, datasheet, product photograph, DigiKey's category and the part's parametric detail as specifications — and nothing has been recorded yet.
2. **Given** that review, **When** the operator confirms it, **Then** a product is created carrying those values, with the manufacturer part number recorded as an `MPN` identifier and the DigiKey part number as a `DISTRIBUTOR` identifier scoped to DigiKey.
3. **Given** that review, **When** the operator types their own description over DigiKey's, **Then** the product carries theirs, and DigiKey's is kept as part of the captured detail rather than discarded.
4. **Given** a DigiKey product-page address pasted in place of a part number, **When** the operator captures it, **Then** the part number is read out of the address and the capture proceeds identically.
5. **Given** a part number the catalog already holds, **When** the operator captures it, **Then** the review names the existing product and offers to fill in what that product is missing rather than creating a second one.
6. **Given** a bag label scanned for a part the catalog does not hold and an order it has not captured, **When** the draft is offered, **Then** it is filled in from DigiKey's data for that part number, not only from the four or five values the label itself carries.
7. **Given** a part number DigiKey does not recognize, **When** the operator captures it, **Then** they are told so and offered the ordinary hand-typed product form carrying what they entered.

---

### User Story 4 - Connect the account once, and be told plainly when it is not working (Priority: P4)

The operator sets up the DigiKey connection once, out of band, the same way the Google Sheets export was set up. From then on it is invisible. When it is not — not yet configured, authorization expired, DigiKey unreachable or refusing — the catalog says which of those it is, at the point the operator tried to use it, and every other workflow in the application carries on working.

**Why this priority**: Nothing here is a feature the operator wants; it is the difference between a five-minute diagnosis and an afternoon. It ranks last because a working connection makes all of it invisible, and because the connection itself ships as part of Story 1.

**Independent Test**: With no DigiKey configuration present, open each DigiKey entry point and verify each one states that the connection is not configured and points at how to configure it, while product search, scanning, manual purchases and the existing Amazon capture are all unaffected.

**Acceptance Scenarios**:

1. **Given** no DigiKey configuration, **When** the operator opens a DigiKey capture screen, **Then** they are told the connection is not configured and where to configure it, and nothing raises an error page.
2. **Given** no DigiKey configuration, **When** the operator uses product search, the scan box, manual purchase entry, receiving or the existing listing capture, **Then** all of them behave exactly as they do today.
3. **Given** a configured connection whose account authorization has expired or been revoked, **When** the operator captures an order, **Then** they are told the authorization needs renewing, distinctly from "DigiKey is down", and nothing is recorded.
4. **Given** a configured connection, **When** DigiKey cannot be reached or answers with an error, **Then** the operator is told the capture could not be read and nothing is partially recorded.
5. **Given** a configured connection, **When** part data is requested for a part number, **Then** it succeeds whether or not the account-level order authorization is present — the two are independent, and losing one does not disable the other.
6. **Given** a capture that failed for any of these reasons, **When** the operator retries it after the cause is fixed, **Then** it succeeds with no cleanup needed.

---

### Edge Cases

- **A line's part detail cannot be read.** The order was read but DigiKey will not answer for one of its parts. The capture is not refused and the other lines are unaffected: that line loses its manufacturer, category, datasheet, photograph and parameters, keeps everything the order gave, and the review says so. A failed *order* read is the opposite — it refuses the capture, because there is nothing to capture.
- **The order is captured twice.** A sales order number is an exact key, not the same-day guess an Amazon listing forces. A re-capture recognizes every line it already recorded, shows them as already captured, and offers only what is new — so recapturing an unchanged order records nothing and recapturing a changed one is how the operator picks up the change.
- **The order changed after it was captured.** DigiKey splits a backorder, cancels a line, or adjusts a quantity. Re-capturing reconciles: a new line is offered for capture, a changed quantity or price is shown against the recorded one and applied only if the operator says so, and a line that has vanished from the order is reported rather than deleted — a purchase the operator can see and cancel is better than one that disappears.
- **A line arrives in two shipments.** A purchase is received or it is not; there is no half-received state and this feature does not add one. The operator receives the line when the last of it arrives, or receives it with the quantity that actually turned up and records the rest as its own purchase. Both are visible; neither is silent.
- **The quantity in the bag differs from the quantity ordered.** The label's quantity is what is offered at receipt, because the label describes what is in the bag. The ordered quantity stays on the purchase's record until the operator confirms otherwise.
- **A line has no manufacturer part number** — DigiKey-branded goods, a shipping or handling line, a cut-tape service charge. The line is still shown; it can be captured on the DigiKey part number alone, or excluded. Nothing is refused for a missing manufacturer part number.
- **A DigiKey part number already names a different product.** Treated exactly as a recycled Amazon item number is today: the review names the existing product, shows its description and manufacturer part number, and requires a choice before anything is written.
- **Two lines of one order are the same part.** Both are shown and both can be captured; they become two purchases against one product, which is what they are. Receiving one does not receive the other, and a scan that could mean either says so and asks.
- **The order was placed minutes ago and DigiKey does not have it yet.** Reported as "not found yet" with the suggestion to try again shortly, not as a bad order number.
- **The sales order number belongs to a different DigiKey account.** Reported as not found for this account. Nothing about another account's order is displayed.
- **A bag label carrying a quantity that is a length** — cut tape, a partial reel. The value is taken exactly as printed and stays editable, as every value read off a distributor label already does.
- **A bag label that will not parse at all.** Falls through to the existing free-text search behaviour with the raw scan shown. Nothing dead-ends.
- **A line was excluded at capture and its bag is scanned later.** There is no outstanding line to receive, so the scan behaves as it does for any uncaptured part: the product opens if it exists, and a DigiKey-filled draft is offered if it does not.
- **The product a captured line attached to is deleted before the box arrives.** The purchase goes with the product, as it does today. Scanning the bag then finds no outstanding line and falls back to the part-based behaviour.
- **DigiKey's description is longer than a label description may be.** The review refuses an over-long description at the point of entry with the limit stated, and pre-fills with a value that fits, rather than silently truncating — a truncated description is a wrong label.
- **Prices in a currency other than the account's.** Recorded exactly as DigiKey reports them, to the cent, with no conversion. The catalog has never converted currency and this feature does not start.
- **DigiKey rate-limits or throttles the request.** Reported as a temporary failure to be retried, distinct from a bad order number and from an authorization problem.

## Requirements *(mandatory)*

### Capturing an order

- **FR-001**: The operator MUST be able to capture a DigiKey order by giving the catalog its sales order number, entered by hand, pasted, or scanned from a label carrying it.
- **FR-002**: A capture MUST read the order's lines from DigiKey rather than from a page the operator is looking at, so that capture does not depend on DigiKey's site markup.
- **FR-003**: A capture MUST present every line of the order for review — DigiKey part number, manufacturer, manufacturer part number, DigiKey's description, quantity ordered and unit price — before anything is recorded.
- **FR-004**: Nothing MUST be recorded until the operator confirms the review. An abandoned review MUST leave no product, no purchase and no stored file.
- **FR-005**: The review MUST state, for each line, whether the catalog already holds a product for it, and MUST name that product.
- **FR-006**: The review MUST let the operator author the label description for each line that would create a new product, pre-filled with DigiKey's description of the part.
- **FR-007**: The review MUST let the operator exclude any line, and an excluded line MUST produce neither a product nor a purchase while every other line is captured normally.
- **FR-008**: Confirming a review MUST record one purchase per included line, against the matched or newly created product, carrying the vendor `DigiKey`, the line's quantity, the line's unit price, the order's date, and the order's sales order number.
- **FR-009**: A purchase recorded by this capture MUST be outstanding — not received — regardless of whether the order has already shipped.
- **FR-010**: A product created by this capture MUST carry the line's manufacturer part number as an `MPN` identifier and its DigiKey part number as a `DISTRIBUTOR` identifier scoped to DigiKey, so that both scan back to it.
- **FR-011**: The catalog MUST record the sales order number against each captured purchase in a field of its own, such that all of an order's purchases can be found from it. It MUST NOT be kept only as free text in a note.
- **FR-012**: A capture MUST NOT record a second purchase for a line it has already captured from the same sales order.
- **FR-013**: Re-capturing an order MUST show which of its lines are already captured, offer any line that is not, and report any previously captured line that the order no longer contains without deleting it.
- **FR-014**: Where a re-capture finds a changed quantity or unit price on an already-captured line, it MUST show the change against what is recorded and apply it only if the operator confirms it.
- **FR-015**: Where a line's DigiKey part number already names a product whose manufacturer part number contradicts the line's, the capture MUST name that product and require a choice — attach to it, or create a separate product — before writing anything.
- **FR-016**: A line with no manufacturer part number MUST be capturable on its DigiKey part number alone.
- **FR-040**: A capture MUST enrich every line with DigiKey's own detail for that part — the manufacturer, the category, the datasheet, the product photograph and the parametric detail — because an order line by itself carries none of them.
- **FR-041**: Where that enrichment fails for a line, the line MUST still be capturable on what the order gave, and the review MUST say which lines came back without it. A part that cannot be looked up costs that line's extra detail and nothing else.

### Seeing and receiving an order

- **FR-017**: The operator MUST be able to open a captured order and see all of its lines, each showing its product, its quantity, its unit price, and whether it is outstanding or received.
- **FR-018**: A captured order MUST show how many of its lines are still outstanding.
- **FR-019**: Scanning a distributor label whose sales order number matches a captured order and whose part matches one of that order's outstanding lines MUST take the operator to the receipt for that line.
- **FR-020**: That receipt MUST offer the quantity stated on the scanned label, editable, rather than the quantity that was ordered.
- **FR-021**: Confirming that receipt MUST have the same effect as receiving a purchase does today — the purchase is recorded as received, a counted product's quantity rises by the received quantity, and a manual low or out flag is cleared.
- **FR-022**: The operator MUST be able to mark any line of a captured order received from the order screen, amending its quantity there, with the same effect as scanning it.
- **FR-023**: Scanning a label for a line that is already received MUST say so, name the line, and receive nothing.
- **FR-024**: Scanning a label whose sales order number matches a captured order but whose part is not among its lines MUST say so and fall back to the existing part-based scan behaviour.
- **FR-025**: Scanning a label whose sales order number matches no captured order MUST behave exactly as scanning it does today.
- **FR-026**: Where a scanned label could refer to more than one outstanding line of an order — the same part ordered twice — the catalog MUST show the candidates and let the operator choose, and MUST NOT pick one.

### Capturing a part

- **FR-027**: The operator MUST be able to capture a single DigiKey part by its part number, by a DigiKey product-page address, or from a scanned bag label.
- **FR-028**: A part capture MUST present for review the manufacturer, manufacturer part number, DigiKey part number, DigiKey's description, the datasheet, the product photograph, DigiKey's category for the part and its parametric detail — before anything is recorded.
- **FR-029**: A part capture MUST let the operator author their own label description over DigiKey's, and MUST keep DigiKey's description as part of the captured detail either way.
- **FR-030**: The part's parametric detail MUST be recorded as the product's specifications, and MUST NOT overwrite a specification of the same name that the operator has already edited by hand.
- **FR-031**: Where the catalog already holds a product for the part, the review MUST name it and offer to fill in what it is missing rather than creating a second product.
- **FR-032**: A part number DigiKey does not recognize MUST produce a plain statement to that effect and the ordinary hand-typed product form carrying what the operator entered — never an error page and never a silent empty draft.
- **FR-033**: Where a scanned distributor label yields a DigiKey part number for a part the catalog does not hold, the draft offered MUST be filled in from DigiKey's data for that part number in addition to the values the label itself carries.

### The connection

- **FR-034**: The DigiKey connection MUST be configured out of band — outside the application's own screens — following the pattern the existing Google Sheets integration uses, and its secrets MUST NOT be committed to the repository.
- **FR-035**: Part data MUST be obtainable with the connection alone; order data MAY additionally require an account-level authorization. Losing or lacking the latter MUST NOT disable the former.
- **FR-036**: When the connection is not configured, every DigiKey entry point MUST say so and say where to configure it, and MUST NOT raise an error page.
- **FR-037**: When the connection is not configured, every other workflow in the application — search, scanning, manual purchases, receiving, and the existing listing capture — MUST behave exactly as it does today.
- **FR-038**: The catalog MUST distinguish, in what it tells the operator, between: not configured; authorization expired or refused; order or part not found; and DigiKey unreachable, erroring or throttling.
- **FR-039**: A capture that fails for any reason MUST leave nothing partially recorded, and MUST be safe to retry once the cause is fixed.

### Key Entities

- **DigiKey Order**: One sales order placed with DigiKey, identified by its sales order number. Carries the order date and the customer's own purchase order reference where there is one. Its lines are the purchases captured from it; it is not a separate stock record.
- **Order Line**: One line of a DigiKey order — a DigiKey part number, a manufacturer part number, a quantity and a unit price. Captured, it becomes one Purchase against one Product. Excluded, it becomes nothing.
- **Purchase**: The existing record of one acquisition of one product. Gains a first-class home for the sales order number, which is what ties a scanned bag to the line it came from. Outstanding until received; there is no third state.
- **Product**: The existing record of a distinct kind of thing the workshop holds. Its identity is its own record and never a vendor's part number, so a DigiKey part number DigiKey later reuses cannot merge two products.
- **Product Identifier**: The existing coded names a product carries. This feature writes `MPN` for the manufacturer part number and `DISTRIBUTOR`, scoped to DigiKey, for the DigiKey part number.
- **DigiKey Connection**: The credentials and account authorization that let the catalog read DigiKey's data. Configured out of band, held outside the repository, and independently reportable as working or not.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A 24-line order is captured — reviewed, described and confirmed — in under five minutes, with the sales order number the only thing typed that DigiKey could have supplied.
- **SC-002**: Every line of a captured order becomes exactly one outstanding purchase or one deliberately excluded line. No line is silently dropped and no line produces two purchases.
- **SC-003**: Capturing the same unchanged order a second time records nothing new.
- **SC-004**: Receiving a bag from a captured order takes one scan and one confirmation, with no typing and no searching, in under ten seconds per bag.
- **SC-005**: Every line whose part the catalog already holds attaches to that existing product; none creates a duplicate.
- **SC-006**: A part captured from DigiKey arrives with its manufacturer, manufacturer part number, DigiKey part number and description filled in without the operator typing any of them.
- **SC-007**: At any point during unpacking, the operator can see from one screen how many of an order's lines are still outstanding and which they are.
- **SC-008**: With the DigiKey connection absent, broken or unreachable, every workflow the application had before this feature still works, and each DigiKey entry point states which of the four failure states it is in.
- **SC-009**: No failed or abandoned capture leaves a partial record behind — measured as: after any failure, the number of products and purchases is unchanged.

## Assumptions

- **DigiKey's published data services are the source.** The user chose this over scraping DigiKey's pages or importing a downloaded order file. It requires registering an application with DigiKey and holding credentials locally; the constitution's rule about secrets (`.env`, `credentials.json`, `token.json` stay untracked) covers them, and the existing Google Sheets integration is the pattern to follow.
- **One connection covers both orders and parts.** Verified: the same credentials read both, and both carry the same account header. The earlier assumption that order access and part access might be separately authorized turned out not to apply — FR-035's two-tier behaviour is therefore vacuous rather than unmet, and what actually distinguishes the failure states is whether the account has been named at all.
- **The account is named in configuration.** DigiKey's credentials identify the *application*, not the customer, so every request carries the account number separately. It is configuration rather than a credential, and it is one value that does not change.
- **The operator enters the sales order number.** Browsing a list of recent orders to pick from would be nicer and may be possible; it is not specified here, because one number typed once a fortnight is not a problem worth solving before the workflow exists. Nothing in this spec forbids adding it later.
- **Capture happens when the order is placed, not when it arrives.** That is the whole point of capture, and it is what makes the reorder list's "on the way" marking correct. Capturing an order that has already arrived is allowed and works; the lines are simply received immediately afterwards.
- **Receiving stays all-or-nothing per line.** The existing model represents outstanding as "no received date", with no partial state, and adding one would touch every screen that reads a purchase. Split shipments are handled by the operator, visibly, per the edge case above.
- **The vendor is recorded as `DigiKey`**, matching what the catalog already derives from a `digikey.com` address. Existing records spelled `Digi-Key` are not rewritten by this feature.
- **Currency is recorded as reported.** No conversion, no assumed currency, prices recorded to the cent as exact decimal amounts, never binary floating point — Constitution III.
- **The existing distributor-label parsing is reused as-is.** The catalog already reads the manufacturer part number, DigiKey part number, quantity and both order references off a format-06 label. This feature gives those values somewhere to go; it does not change how they are read.
- **The existing Amazon listing capture is untouched.** Its bookmarklet, its confirmation page and its duplicate handling all keep working exactly as they do; this is a second capture path, not a replacement.
- **Capture reads one part detail per line.** An order line carries no manufacturer name and no datasheet, category or parametric detail, so each line is looked up separately. A 24-line order is therefore around 25 reads, well inside DigiKey's published allowance, and takes roughly ten to fifteen seconds — the same order as the gallery fetch an Amazon capture already performs.
- **Single operator, LAN-only, as ever.** No accounts, no roles, no queues, no background jobs. A capture is a thing the operator waits a couple of seconds for.
