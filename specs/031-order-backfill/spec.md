# Feature Specification: Backfilling Past Orders

**Feature Branch**: `issues/125`

**Created**: 2026-08-28

**Status**: Draft

**Input**: GitHub issue #125 — "Order Backfill": *"New users of this application or its Product functionality will likely want to capture past/historical orders from the supported vendors (Amazon, DigiKey, McMaster). We need some way to do this. Note that the solution to this may not be a code change in this repo, it could just be documentation. DigiKey and McMaster could simply leverage something like Claude in Chrome to enumerate all orders and then trigger the bookmarklet for each one in order. Amazon is a different case, as many Amazon customers are likely to have orders (maybe the majority of their orders) unrelated to workshop items. One possible solution is to have the user utilize the Request Your Data tool to request their order history, download the resulting Zip file, and edit the `Your Amazon Orders/Order History.csv` file down to only the rows they care about. Then, a deterministic script or Claude in Chrome could extract the unique order numbers and load them in a browser for capture."*

## Overview

Every capture path in this application was built for an order that has just been placed. Feature 007 catches a listing while it is still on screen; 024, 028 and 029 catch a whole order at checkout time, so that the box arriving three weeks later has something to be received against. All three are written in the present tense, and all three assume the operator is standing at the beginning of the order's life.

Nobody starts there. Someone adopting the product catalog — or the person who wrote it, on the day they turned it on — already owns a workshop full of things, most of which came from these same three vendors, and none of which the catalog knows about. Their price history, their part numbers, their datasheets and their pack sizes are all still sitting in the vendors' own order histories, and the only thing standing between the two is that no one has walked the list.

**That walk is what this feature is.** It is not a new way to record an order — it is a written, followable procedure for feeding orders the operator already placed through the capture paths that already exist, plus whatever small amount of application change turns out to be needed to keep the result honest.

Three things make it more than "click the bookmarklet a lot".

**Enumeration.** Capture starts from a page or an order number the operator is already looking at. Backfill starts from nothing, and the first job is producing the list. DigiKey's order history is on DigiKey's site and each entry carries a sales order number the existing screen already accepts. McMaster's order history lists orders whose own pages the existing bookmarklet already reads. Amazon's *Your Orders* is paginated back through the years. Enumerating is mechanical in all three cases, which is exactly why it should not be a person's job — the only question is whether the machine doing it is a driven browser or the application itself.

**Selection, which is Amazon's problem alone.** DigiKey and McMaster sell nothing that is not a workshop item, so every order in those histories is wanted. An Amazon account is the household's, and the workshop orders are a minority buried in groceries, books, birthday presents and phone chargers. Opening four hundred order pages to find thirty is not a procedure, it is a punishment. Amazon's *Request Your Data* export exists precisely to make that filtering possible away from the browser — but it delivers one row per *item*, so an eleven-item order appears eleven times, and what comes out of the filtering has to be reduced to unique order identifiers before anything can be opened.

**Disposition, which is the part that is genuinely new.** A captured order is an outstanding one: the received date is blank, and that blank is the entire representation of "on its way". That is right for an order placed this morning and wrong for one placed in 2023. Backfilling fifty orders through the existing paths would leave fifty complete orders and several hundred lines reporting themselves as in transit, on the two screens — Captured Orders and the reorder list — that exist to answer *what is still coming*. Clearing that by hand is one receive screen per line, several hundred times, and it would still stamp a delivery date of today onto a delivery that happened two years ago. Backfill is not finished when the purchases exist; it is finished when the catalog's account of what is on its way is still true afterwards.

**Where the three land.** Enumeration for Amazon and McMaster stays in the browser, because that is already where their reading happens. DigiKey is the exception: it is the one vendor this application talks to directly, and asking that same connection *which* orders exist is a smaller thing than asking a person to copy thirty sales order numbers off a web page by hand — so the connection grows an order listing and the operator picks from it. Amazon's selection is done by the operator in the export file, and the mechanical part that follows — reducing a file of item rows to the distinct orders they belong to — is a command shipped with this project, because it is exactly the kind of fiddly, repeatable, easy-to-get-quietly-wrong step that should be written down once and tested rather than retyped. And disposition is settled at capture time: the review the operator is already looking at gains one statement — *these already arrived* — and confirming it records the lines delivered rather than outstanding.

What backfill explicitly does not change is the shape of a capture. Nothing is written until the operator confirms; the label description is authored while the vendor's data is on screen; a line the operator does not want cataloged is excluded and leaves no trace; and re-capturing an order records nothing new. Those four properties are what make a backfill safe to run, safe to interrupt, and safe to resume — they are the reason this feature can be mostly a procedure rather than mostly code.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Walk a vendor's order history and capture what is in it (Priority: P1)

The operator has been buying from DigiKey for three years and the catalog knows about none of it. They follow a written procedure: get their order history in front of them — from the application for DigiKey, from the vendor's own site for McMaster and Amazon — work back through it, and for each order use the review that vendor already has. Each capture presents the same review it always does, they write the descriptions that matter and untick what they do not want, and confirm. When they get to the bottom of the history, every order they kept is in the catalog, with its lines, its parts, its prices and its dates.

**Why this priority**: It is the whole point of the issue and it is the only story that delivers value alone. The products and the price history are what the operator actually wants; everything else here makes getting them cheaper or keeps the result honest.

**Independent Test**: Take a vendor account holding several historical orders, follow the written procedure end to end, and verify that each captured order's lines exist as purchases against products carrying the right vendor identifiers, quantities, unit prices and order dates — and that a second pass over the same history records nothing new.

**Acceptance Scenarios**:

1. **Given** a vendor order history containing several past orders, **When** the operator follows the documented procedure, **Then** each order they chose to capture is reviewed and recorded through that vendor's existing review-and-confirm path, with nothing new introduced between the review and the record.
2. **Given** a backfill that was interrupted partway through the history, **When** the operator resumes it from the beginning, **Then** orders already captured record nothing new and orders not yet reached capture normally.
3. **Given** a historical order containing a line the operator no longer wants cataloged, **When** they exclude it in the review and confirm, **Then** that line produces no product and no purchase, and every other line captures.
4. **Given** a historical order whose page or order data yields fewer lines or thinner lines than it did when new, **When** it is captured, **Then** the review reports what came back thin before anything is written, exactly as a present-day capture does.
5. **Given** an order that was already captured normally at the time it was placed, **When** the backfill reaches it, **Then** it is recognized as already captured and no duplicate product or purchase results.
6. **Given** the written procedure, **When** it is read by someone who has not done a backfill before, **Then** it states for each of the three vendors where the order history lives, how an order is fed into capture, and how far back that vendor's history can be relied on.

---

### User Story 2 - Pick the workshop orders out of an Amazon history that is mostly not workshop (Priority: P2)

The operator's Amazon account holds several hundred orders and perhaps thirty of them are workshop purchases. Rather than paging through *Your Orders*, they request their order history from Amazon's data tool, wait for the export, and open the order-history file. Working in that file — where every order is one line of text with a title and a date — they keep only the rows they recognize as workshop purchases and discard the rest. They then run the project's own command over what is left, and it hands back the distinct order numbers those rows belong to, each one once, as addresses that open the order pages the existing Amazon capture already reads.

**Why this priority**: Amazon is the vendor the operator buys from most, and without this step Amazon backfill is not merely tedious but unreasonable. It ranks second only because it is a way of producing the list that Story 1 consumes — Story 1 works without it for the two vendors whose histories need no filtering at all.

**Independent Test**: Take an Amazon order-history export containing a mix of workshop and non-workshop orders, edit it down, run the command over it, and verify the result is the set of distinct order numbers for the kept rows only — no order number repeated, no discarded order present, and every address opening a real order page.

**Acceptance Scenarios**:

1. **Given** an edited Amazon order-history export, **When** the operator runs the project's reduction command over it, **Then** they get back the order identifiers of exactly the rows they kept, and nothing else.
2. **Given** an export in which one order contributed eleven item rows, **When** the command is run, **Then** that order appears exactly once in the result.
3. **Given** the command's output, **When** the operator opens one of its addresses, **Then** it resolves to an Amazon order page that the existing Amazon order capture accepts.
4. **Given** an export file whose columns are not the ones the command expects — Amazon changed the format, or the wrong file was passed — **When** the command is run, **Then** it says plainly what it could not find and produces nothing, rather than emitting a short or empty list that looks like a successful run.
5. **Given** any run, **When** it finishes, **Then** it states how many rows it read and how many distinct orders came out, so a file edited down to four rows that yields one order is visibly that.
6. **Given** an order containing both workshop and non-workshop items, **When** it is captured, **Then** the unwanted lines are excluded in the existing review and only the wanted ones are recorded.
7. **Given** the written procedure, **When** it is read before the export has been requested, **Then** it states that the export is not immediate, roughly how long Amazon takes to deliver it, and which file inside it to use.
8. **Given** an Amazon order that the export names but whose order page no longer renders as an order, **When** the operator reaches it, **Then** the procedure says what that means and what to do instead, rather than leaving them at a capture that silently yields nothing.

---

### User Story 3 - A backfilled order is recorded as having already arrived (Priority: P3)

The operator is reviewing a historical order they have just read out of a vendor's history. Everything in it was delivered eighteen months ago. Alongside the lines they are about to confirm, the review lets them say so — *these already arrived*, on this date — and confirming records every kept line as delivered rather than outstanding. Afterwards, **Captured Orders** shows the order as complete, the reorder list does not claim its products are on the way, and each purchase carries a delivery date in the past rather than the date the backfill was run.

**Why this priority**: It is worthless without captured orders to settle, which is why it ranks last — but it is not optional. Leaving it out means backfill actively breaks the two screens whose entire job is to say what is still coming, and stamps today's date on deliveries that happened years ago. It ships with this feature or the feature makes the catalog less trustworthy than it was before.

**Independent Test**: Capture an order dated in the past, mark it as already arrived in the review, confirm, and verify every kept line is recorded delivered with the date given, the order is reported complete on the captured-orders list, and none of its products is marked as on the way on the reorder list.

**Acceptance Scenarios**:

1. **Given** a review of a captured order, **When** the operator marks it as already arrived and confirms, **Then** every included line is recorded delivered in that one confirmation rather than one receipt screen per line.
2. **Given** that mark, **When** the operator supplies the date it arrived, **Then** that date is what is recorded against every line.
3. **Given** that mark with no date supplied, **When** it is confirmed, **Then** the recorded delivery date is derived from the order's own date and is never silently today's date.
4. **Given** a review that has *not* been marked as already arrived, **When** it is confirmed, **Then** the lines are recorded outstanding exactly as they are today — a present-day capture is unchanged in every respect.
5. **Given** a confirmed already-arrived order, **When** the captured-orders list is opened, **Then** the order is shown as complete with nothing outstanding.
6. **Given** a confirmed already-arrived order, **When** the reorder list is opened, **Then** none of that order's products is marked as being on the way on account of it.
7. **Given** a line against a product whose stock is counted, **When** the order is confirmed as already arrived, **Then** the operator can do so without raising that product's on-hand count, because a delivery from two years ago has already been used.
8. **Given** an order in which most lines arrived and one never did, **When** it is reviewed, **Then** the operator can hold that one line back from the arrival mark and it is recorded outstanding while the rest are recorded delivered.
9. **Given** a re-capture of an order whose lines were already recorded delivered, **When** it is confirmed, **Then** those lines are not received a second time and their delivery dates are not rewritten.

---

### Edge Cases

- **The vendor's history does not go back far enough.** Every vendor prunes eventually. What the procedure must not do is leave the operator believing they backfilled everything when the history stopped at four years.
- **An Amazon order page for a very old order renders differently, or not at all.** Archived, digital-only, or a shape the reader was never written against. This must produce the existing "no lines could be read" statement, not an empty review.
- **Amazon notices the browser opening thirty order pages in a minute.** A re-login or a challenge partway through a run. The run must be resumable from where it stopped, which follows from re-capture recording nothing new.
- **The export's order-history file names orders that were cancelled or fully returned.** Nothing should record a purchase for goods that were sent back; the operator excludes them at selection or at review.
- **A historical order contains an item the operator no longer owns.** Consumed, given away, thrown out. Cataloging it anyway gives a real price history for something they may buy again — but they may also not want it. Excluding a line already does this; the procedure has to say which choice it is recommending and why.
- **A historical purchase is the *only* purchase for a product that already exists in the catalog with a newer price.** The product page calls out the most recent price; a backfilled older purchase must slot into the history by date, not become the headline.
- **A backfilled order and a present-day order carry the same identifier at different vendors.** Order identity is per-vendor already; backfill must not weaken that.
- **The same physical delivery is backfilled twice** — once from the vendor's history and once because it was captured at the time. Handled by the existing per-vendor re-capture behaviour, and the procedure must say to expect it rather than treat it as a fault.
- **An order is re-captured after some of its lines were already recorded delivered.** The already-delivered lines must not be received a second time or have their dates rewritten, which is the existing re-capture rule applied to a state that did not exist before.
- **DigiKey's order listing does not reach back as far as the operator's history does.** A listing that quietly stops at eighteen months looks identical to an account with eighteen months of orders. What it covers has to be stated, and capture-by-number has to remain available for anything older.
- **The reduction command is run over an unedited export.** It will faithfully produce every order in the household's history, which is not a fault — the count it reports is what tells the operator they skipped the editing step.
- **An order is marked as already arrived by mistake on a present-day capture.** The mark is never the default and the review states what confirming will do; beyond that, the existing receive record is where the correction is made.
- **The operator's Amazon export contains someone else's household orders.** Nothing technical to do, but the procedure should note that selection is happening over the whole account's history.

## Requirements *(mandatory)*

### The procedure

- **FR-001**: The project MUST provide a written procedure for backfilling historical orders, covering all three supported vendors, discoverable from the user documentation rather than living only in an issue or a specification.
- **FR-002**: Backfill MUST reuse each vendor's existing review-and-confirm path. It MUST NOT introduce a second way of reviewing or recording an order for any vendor; new ways of *finding* an order to capture are permitted, and are the only new surfaces this feature adds.
- **FR-003**: The procedure MUST state, per vendor, where the order history is found, how an individual order is fed into that vendor's capture path, and what identifies an order to that vendor.
- **FR-004**: The procedure MUST state, per vendor, how far back the order history can be relied on and what to do about orders older than that.
- **FR-005**: A backfill MUST be interruptible and resumable: re-running it over an order that was already captured MUST record no new product and no new purchase, per each vendor's existing re-capture behaviour.
- **FR-006**: Backfill MUST NOT require the operator to give the application any vendor credentials beyond the existing optional DigiKey connection. Amazon and McMaster reading MUST continue to happen in the operator's own signed-in browser.
- **FR-007**: The procedure MUST describe how the Amazon and McMaster page-opening steps can be driven mechanically rather than by hand, without the application itself driving a browser.
- **FR-008**: The procedure MUST state what a backfilled record does and does not contain per vendor — in particular that an Amazon order capture yields title, quantity and price but no images, specifications or barcodes — and how to fill a record in later by capturing its listing page.

### Selecting Amazon orders

- **FR-009**: The procedure MUST give the operator a way to identify which of their Amazon orders are workshop-related without opening every order page.
- **FR-010**: That selection MUST work from Amazon's own order-history export, and the procedure MUST state how to request it, roughly how long it takes to arrive, and which file within it to use.
- **FR-011**: The project MUST ship a command that takes the operator's edited order-history export and returns the distinct orders its rows belong to, so that the reduction is written down and tested once rather than retyped per backfill.
- **FR-012**: That command MUST yield each order exactly once regardless of how many item rows it contributed, and MUST yield only orders the kept rows name.
- **FR-013**: That command MUST report how many rows it read and how many distinct orders it produced, so a truncated or wrongly-edited file is visible as such rather than passing as a short history.
- **FR-014**: That command MUST refuse plainly, naming what it could not find, when handed a file whose shape it does not recognize. It MUST NOT produce a partial or empty list that is indistinguishable from a successful run.
- **FR-015**: The command's output MUST be directly usable to reach Amazon order pages that the existing Amazon order capture accepts.
- **FR-016**: The command MUST read the operator's file and write nothing to the catalog. Selection is a step before capture, and no product or purchase may result from running it.
- **FR-017**: An order containing both wanted and unwanted items MUST be capturable with the unwanted lines excluded through the existing per-line exclusion, with no new exclusion mechanism.

### Finding DigiKey and McMaster orders

- **FR-018**: The application MUST be able to list the operator's past DigiKey orders through the existing DigiKey connection, so that backfilling DigiKey does not require reading sales order numbers off DigiKey's website and typing them back in.
- **FR-019**: From that listing, the operator MUST be able to start the capture of any order without typing its sales order number.
- **FR-020**: The listing MUST show enough of each order — at least its sales order number and its date — for the operator to tell which orders they have already dealt with.
- **FR-021**: The listing MUST behave like the rest of the DigiKey integration when the connection is not configured: it opens, says it is not configured, and changes nothing else. It MUST NOT become a second thing that has to be configured separately.
- **FR-022**: Where DigiKey cannot supply the listing — the connection is down, or the account returns nothing — the screen MUST say so plainly and leave the existing capture-by-number path available.
- **FR-023**: The procedure MUST let the operator enumerate their McMaster-Carr order history and reach each order's own page, where the existing bookmarklet reads it. This stays browser-side; no McMaster connection is introduced.

### Recording that a backfilled order already arrived

- **FR-024**: The review shown before an order is recorded MUST let the operator state that the order has already arrived, and confirming such a review MUST record every included line as delivered rather than outstanding, in that one confirmation.
- **FR-025**: A review that has not been marked as already arrived MUST record its lines outstanding exactly as it does today. Present-day capture MUST be unchanged, and the arrival mark MUST NOT be the default.
- **FR-026**: The delivery date recorded MUST be one the operator supplied, or one derived from the order's own date. It MUST NOT silently be today's date.
- **FR-027**: After such a confirmation, the captured-orders list MUST report the order as complete and the reorder list MUST NOT mark any of its products as being on the way on account of it.
- **FR-028**: The operator MUST be able to record a line as already arrived without raising the on-hand count of a product whose stock is counted.
- **FR-029**: The operator MUST be able to hold an individual line back from the arrival mark, so that a line that never arrived is recorded outstanding while the rest of the order is recorded delivered.
- **FR-030**: Re-capturing an order whose lines were already recorded delivered MUST leave those lines untouched — not received a second time, and not re-dated.
- **FR-031**: Nothing MUST be written until the operator confirms, at every step of a backfill, exactly as the existing capture paths behave.

### Key Entities

- **Historical order**: An order the operator placed in the past and has already received. Identified the way its vendor identifies it — a DigiKey sales order number, a McMaster purchase-order name, an Amazon order number — and distinguished from a present-day order only by the fact that it has already arrived.
- **Amazon order-history export**: The file Amazon delivers in response to a data request, listing one row per ordered item, each row naming its order. The raw material of Amazon selection; not something the catalog holds.
- **Selected order list**: The de-duplicated set of order identifiers the operator decided to capture — produced by the reduction command for Amazon, and by the DigiKey order listing or McMaster's order history for the other two. A working artifact of the backfill, not a record the catalog keeps.
- **Backfilled purchase**: A purchase created by a backfill. Identical in every respect to one created by a present-day capture, except that its delivery date is in the past rather than blank.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator who has never backfilled before can complete a backfill of one vendor's history by following the written procedure alone, without reading source code and without asking a question the procedure does not answer.
- **SC-002**: Backfilling one historical order costs the operator no more attention than capturing a present-day one — the arrival mark is part of the review they are already reading, not a second visit to the order.
- **SC-003**: For an Amazon account in which fewer than one order in ten is workshop-related, the operator opens only the orders they selected — the count of order pages opened is within one of the count of orders they chose.
- **SC-004**: Reducing an edited Amazon export to its distinct orders is one command and takes seconds, and its result is identical every time it is run over the same file.
- **SC-005**: Backfilling a DigiKey history requires no sales order number to be read off DigiKey's website and typed back in.
- **SC-006**: After a completed backfill, the captured-orders list reports no backfilled order as having outstanding lines, and the reorder list marks no product as on the way on account of a backfilled order.
- **SC-007**: No backfilled purchase carries a delivery date later than the day the goods actually arrived; in particular, none carries the date the backfill was performed unless that is genuinely when it arrived.
- **SC-008**: A backfill interrupted at any point and restarted from the beginning produces no duplicate product and no duplicate purchase.
- **SC-009**: Every capture, receive, order-screen and scanning behaviour that existed before this feature behaves exactly as it did for a present-day order, demonstrated by the existing tests passing unchanged.

## Assumptions

- **Backfill is a catch-up, not a routine.** It is run once when the catalog is adopted, and perhaps occasionally afterwards. The volume is tens of orders and hundreds of lines, not thousands, and nothing here needs to be optimized for scale beyond that.
- **The operator is signed in to each vendor in their own browser.** This is what the Amazon and McMaster bookmarklet paths already assume, and backfill assumes no more.
- **Driving the browser is the operator's business.** The issue names Claude in Chrome; anything that can open a list of addresses in turn and click a bookmarklet will do. This is how Amazon and McMaster orders get opened. The application does not drive a browser and gains no capability to.
- **DigiKey's connection can be asked which orders exist.** The application talks to DigiKey today only by sales order number, so listing an account's orders is new ground for this project. If that turns out not to be available on the connection the application already holds, FR-018 through FR-022 fall back to McMaster's shape — enumerate in the browser, capture by number — and the plan must say so rather than inventing a second integration.
- **The reduction command reads a file and nothing else.** It needs no database, no configuration and no network, which is what makes it safe to run before anything has been decided.
- **Historical pages read the way present-day ones do.** Where a vendor renders an old order differently, the existing thin-capture reporting is what tells the operator, and no new detection is introduced.
- **Selection is the operator's judgement.** No attempt is made to classify an Amazon order as workshop-related automatically. A person reading a list of titles is both more accurate and less dangerous than a rule.
- **Prices are recorded as the vendor stated them at the time.** A backfilled purchase is historical fact; it takes its place in a product's price history by date and does not become the headline price.
- **Excluded lines leave no trace.** This is the existing behaviour and backfill does not add a record of what was skipped — a decision that makes a second pass over the same history offer those lines again, which is correct.
- **The existing per-vendor re-capture behaviour is what makes a backfill resumable.** Nothing new is built to track backfill progress; the catalog's own contents are the progress.

## Out of Scope

- Vendors other than Amazon, DigiKey and McMaster-Carr. An order from anywhere else is cataloged the way it always was — from its address, one item at a time.
- Reconstructing purchases from bank statements, credit-card exports or receipts. The vendors' own order histories are the only source.
- Matching backfilled products to physical inventory items that already carry JA IDs. That is a separate reconciliation and is not attempted here.
- Retroactively fetching images, specifications or barcodes for orders captured from an order page. The documented answer is to capture the listing page for the handful of items where it matters.
- Any automatic or scheduled re-scan of a vendor's order history. Backfill is something the operator starts.
