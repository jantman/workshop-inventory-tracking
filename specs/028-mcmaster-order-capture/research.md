# Research: McMaster-Carr Order and Product Capture

**Feature**: 028-mcmaster-order-capture | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

Phase 0. Every decision below is one the design depends on; each names what was chosen, why,
and what was rejected.

---

## 1. The transport: the bookmarklet, and nothing else

**Decision**: The order and the product are both read out of the page in the operator's own
browser, by `app/static/js/capture-agent.js`, loaded by the bookmarklet that already exists.
No McMaster credentials, no registration, no configuration held by the application.

**Rationale**: Issue #119 settles it: McMaster's API requires an application review, and a
one-person hobby workshop will not pass it. There is no second source. This is the opposite
premise from feature 024, where DigiKey publishes the data and the page was rejected as a
source precisely because it goes stale.

**Alternatives considered**:

| Alternative | Rejected because |
|---|---|
| Apply for McMaster API access | The issue rules it out as a certainty, and building against an interface we cannot obtain is building nothing. |
| Server-side scrape with stored McMaster credentials | Order pages are behind a login. It would put a vendor password in the application's configuration, add a login/session/2FA path the app has never had, and break the moment McMaster changes their sign-in. The bookmarklet already carries the operator's live session for free. |
| Import a downloaded order export | Whether McMaster offers a stable machine-readable export is unknown, and the issue names the bookmarklet. Adding a file-upload path to find out is speculative work. |

---

## 2. The bookmarklet's text must not change

**Decision**: `_capture_bookmarklet()` is not modified. The order payload rides the **existing**
`/api/capture` endpoint as one additional form field, and `product_capture()` branches on the
payload's shape.

**Rationale**: The bookmarklet is a `javascript:` URL saved in the operator's browser. Anything
that changes its text — a second `data-` attribute, a second endpoint, a second bookmarklet —
means re-dragging it, which FR-034 forbids and FR-021 contradicts. The *agent* is cache-busted
on every load (`?v=' + Date.now()`), so all the new behaviour can live there and deploy itself.

Routing on payload shape at one endpoint is consistent with what the endpoint already does: it
accepts a capture and renders a page for the operator to confirm. A payload it does not
recognize is already required to fall through to today's behaviour (007 FR-007), so the
fall-through is not new code, it is the existing contract.

**Alternatives considered**: a second `data-order-endpoint` attribute (forces a re-drag);
a separate order bookmarklet (two things to drag, FR-021 says one); deriving the order URL by
string surgery on the endpoint the loader supplies (fragile, and unnecessary once one endpoint
can serve both shapes).

---

## 3. Page dispatch happens in the agent, and keys on the path

**Decision**: The agent decides what kind of page it is on before it extracts anything. Three
outcomes: **McMaster order page**, **McMaster product page**, **everything else — today's
Amazon path, untouched**. Detection keys on the URL **path shape**, not on the hostname.

**Rationale**: Two reasons, and the second is the load-bearing one.

The first is that this is how the agent already works: Amazon is recognized by
`/(?:dp|gp/product|product)/([A-Z0-9]{10})` in the path, and `_asin_from_url` in
`app/product/routes.py:841` reads the same shape server-side. A path is a contract in a way
markup is not.

The second is testability. `tests/e2e/test_product_page_capture.py` drives the *real*
bookmarklet against a fixture served from the **application's own origin** at `/dp/<ASIN>` —
because Chrome's Private Network Access rules make a convincing `www.amazon.com` origin
impossible to serve locally (that test's module docstring explains it at length). A
host-gated dispatch would be undriveable by that harness, and the McMaster extraction would
have no end-to-end coverage at all. A path-shaped one reuses the harness as-is.

**Consequence**: a McMaster product page is recognized by a path of the form
`/91290A115/` — digits, a letter, then alphanumerics. The order-page path shape is one of the
fixture-derived unknowns in §5.

**Structuring**: the agent grows a small dispatch at its entry point and a McMaster reader
alongside the Amazon one. Nothing on the Amazon path is edited, which is what makes SC-010
checkable by running the existing suite.

---

## 4. The vendor name travels in the payload

**Decision**: When the agent recognizes a McMaster page it puts `vendor: "McMaster-Carr"` on the
payload. The server uses it rather than deriving the vendor from the host.

**Rationale**: `_vendor_from_url` maps `mcmaster.com` → `McMaster-Carr` and is right in
production, but under the e2e harness the fixture is served from `127.0.0.1:<port>` and the
vendor comes out as the loopback host — a cost `test_product_page_capture.py` already
documents and tolerates, because for Amazon the vendor is cosmetic.

For McMaster it is not cosmetic. `vendor` is half of every query that finds a captured order
and every query that finds a receivable line, and it scopes the `DISTRIBUTOR` identifier
(US2 scenario 2). If the vendor is wrong under test, none of receiving can be tested at all.

The agent is the thing that actually knows which vendor's markup it just read, so it is the
honest place for the value to come from. `product_capture()` already prefers a submitted
`vendor` over the derived one (`app/product/routes.py:468`), so the product path needs no
change beyond the agent sending the field. The order route validates that the declared vendor
is the known McMaster name before treating a payload as a McMaster order.

**Not a security decision**: the app is LAN-only with no login (Constitution, Operating
Context). This is about testability and about which component holds the knowledge.

---

## 5. The unknown: McMaster's actual markup — and how it is resolved

**This is the one open input, and it is an input rather than a spec gap.** No selector in this
plan can be written until two saved pages exist:

1. `tests/e2e/fixtures/mcmaster_order.html` — one order, saved complete from McMaster's
   **order history** (the page FR-001 names), with lines showing part numbers, descriptions,
   quantities and prices.
2. `tests/e2e/fixtures/mcmaster_product.html` — one product page, saved complete, ideally for
   a pack-priced item so FR-020's arithmetic has something real to run against.

**Before either is committed, scrub it.** An order-history page carries the ship-to address,
and possibly a name, phone number or the last digits of a card. None of that is read by this
feature and none of it belongs in the repository. Part numbers, descriptions, quantities and
prices are the fixture; everything else comes out. The Amazon fixtures set the precedent for
what a saved vendor page looks like in `tests/e2e/fixtures/`.

**Why nothing was fetched to resolve this during planning**: an order page is behind the
operator's login and cannot be reached from here at all. A product page is public, but
McMaster renders client-side, so a server-side fetch returns a shell that says nothing about
the DOM the agent will actually see. The bookmarklet runs against the live, rendered document
(§6), so the live document is the only thing worth reading, and only the operator can save it.

**What is designed without it**: everything except the selectors. The payload schema
(`contracts/capture-payload.md`), the routes, the service methods, the data model and the
migration are all fixed by the spec and are unaffected by which CSS class McMaster hangs a
price on. The selectors are the last thing written and the only thing the fixtures gate.

**The risk that is not mitigated** — stated here as feature 007 stated its own: nothing in
this design fails when McMaster changes their markup. A test against a saved page proves the
reader reads *that* page. FR-036 (a lost field costs that field alone) and FR-004/FR-037 (say
how many lines were read, and what came back thin) are the whole of the mitigation, and they
are containment, not prevention.

---

## 6. The live document, not a canonical re-fetch

**Decision**: The McMaster readers run against `document` as it stands on screen. No change to
`canonicalDocument()`.

**Rationale**: It already does the right thing without being touched. It is gated on an ASIN
(`capture-agent.js:932`): with none, it resolves immediately to `{doc: document, url:
location.href}`. A McMaster page has no ASIN, so it takes that path today.

It is also right on the merits. Amazon's re-fetch exists because a tab drifts to a variant
(`?th=1`) and the canonical address is the authority. McMaster's pages are client-rendered, so
a re-fetch would return an unrendered shell — strictly worse than the document the operator is
looking at, which by definition shows the lines they can see.

---

## 7. McMaster gets its own service methods; the DigiKey path is not refactored

**Decision**: `review_mcmaster_order` / `capture_mcmaster_order` are written as their own
methods alongside `review_digikey_order` / `capture_digikey_order`. Shared: the leaf helpers
(`price_to_cents`, `MAX_DESCRIPTION_LENGTH`, `_add_identifier`, `create_product`,
`record_purchase`, `receive_purchase`) and the display value objects (`OrderLineState`,
`ReviewedLine`). Not shared: the orchestration.

**Rationale**: The two flows differ in four places that sit right in the middle of the
orchestration — where the order comes from (a client fetch that can be repeated, versus a
payload that was read once and must be carried), whether lines are enriched (a part lookup per
line, versus the page being the detail), which identifiers are written (`MPN` +
`DISTRIBUTOR`, versus `DISTRIBUTOR` and `MPN` only if stated), and pack-to-unit conversion
(McMaster only). A single parameterized routine would be four branches wearing a trench coat.

The deciding factor is risk, not elegance. `capture_digikey_order` is the most intricate write
path in the application, its edge cases were bought with a data-corruption bug (PR #116
review), and SC-010 requires that every existing workflow behave identically after this
feature. Refactoring it to serve a second vendor puts that at risk for a saving of perhaps
150 lines. The project has done this before and it was right: the Amazon capture and the
DigiKey capture are separate paths that share leaves.

Constitution I is satisfied rather than strained: no new abstraction is introduced for a
single implementation, and none is introduced for two either.

**Alternatives considered**: a vendor-neutral `OrderCapture` protocol with per-vendor readers
(the abstraction the constitution warns about, and it would have to be built by editing the
DigiKey path); reusing `capture_digikey_order` with a vendor argument (same risk, plus every
DigiKey-specific branch becomes conditional).

---

## 8. Line identity: rename the column rather than add a second one

**Decision**: `purchases.digikey_line_number` becomes `purchases.order_line_number` in one
reversible Alembic revision. Both vendors write it.

**Rationale**: The column exists because pairing an order's lines to purchases by *position*
corrupted data the first time a part appeared twice on one order — the comment at
`app/database.py:1102` records the incident and the reasoning. FR-014 needs exactly the same
thing for McMaster, and reading a page rather than a service makes the case stronger, not
weaker: a page's line ordering is not a contract at all.

The name is the only problem, and it is cheap to fix: eleven references across three editable
files (`app/database.py`, `app/catalog_service.py`, `tests/unit/test_digikey_capture.py`) plus
the original migration, which is frozen and stays as it shipped. The rename is mechanical and
covered by the existing DigiKey unit tests.

Both halves of the migration must be exercised (Constitution V), and the ORM column
definition must match the revision exactly — the unit suite builds its schema with
`create_all` and never runs Alembic, so drift passes `nox -s tests` and fails on the real
database. `app/database.py:1085` already carries that warning for the sibling column.

**Alternatives considered**: a parallel `mcmaster_line_number` (two nullable columns meaning
one thing — the duplication the constitution's "boring, obvious code" rule exists to prevent);
writing McMaster's line number into `digikey_line_number` unrenamed (the name would be a lie,
and the next reader pays for it).

---

## 9. Packs become units at the review, and the arithmetic is shown

**Decision**: A pack-priced line records `quantity = packs × pack_size` and
`unit_price = price_to_cents(pack_price / pack_size)`. All three inputs and both outputs are
rendered on the review, both outputs are editable, and inexact division is stated.

**Rationale**: The user chose units over packs: what gets consumed, and what the low-stock flag
has to mean, is individual screws. The arithmetic itself is not new — feature 017 already does
`amount paid ÷ pack size` on the capture confirmation page, already renders the result as an
ordinary editable field, and already tells the operator when the division does not come out
even. This reuses that decision one level up, per line.

`price_to_cents` (`app/models.py:852`) is the existing `Decimal`/`ROUND_HALF_UP` quantizer and
is what keeps Constitution III true. `Purchase.quantity` is an `Integer` with a
`> 0` check constraint, and packs × pack size is an integer, so nothing about the column
changes.

**Note on the boundary**: 017's pack fields are UI-only and recorded nowhere
(`app/templates/product/capture.html:212`). This feature keeps that: the pack figures are
shown so the operator can check the arithmetic, and what is stored is units and a unit price.

---

## 10. Receiving: where the scan branch goes, and why the precedence matters

**Decision**: In `resolve_scan`'s **FREE_TEXT** branch, look for outstanding McMaster purchases
whose `vendor_item_id` equals the scanned value **before** the existing vendor-scoped
identifier lookup. Any match yields the `receive` outcome; no match falls through to today's
behaviour, byte for byte.

**Rationale**: This mirrors the ECIA branch, whose comment
(`app/catalog_service.py:2333`) states the trap: capturing an order creates products carrying
these part numbers, so the identifier lookup would match happily, and a bag for a part you have
bought before would open the product page instead of its receipt — satisfying the requirement
only for parts you have never bought, which is exactly backwards.

**Why it cannot affect anything else**: the lookup is `vendor == 'McMaster-Carr'` AND
`received_date IS NULL` AND `vendor_item_id == <scanned>`. An ASIN scan cannot match a McMaster
purchase's `vendor_item_id`; a GTIN or internal code never reaches this branch; a McMaster part
number with no outstanding line finds nothing and falls straight through (FR-032b). Both
columns in the predicate are already indexed (`app/database.py:1049`, `:1086`).

**`_receive_url` must stop reading ECIA fields.** It currently takes the order number from
`resolution.classification.ecia_fields['1K']` (`app/product/routes.py:1515`), which is empty
for a FREE_TEXT scan. It reads the order number and the vendor off the matched purchases
instead — information the purchases carry either way, and a strictly better source for the
DigiKey case too.

---

## 11. Several candidates land on a chooser, not on an order screen

**Decision**: A new small page listing each candidate outstanding purchase — order number,
order date, quantity, unit price, product — each linking to its own receipt.

**Rationale**: DigiKey's multi-candidate case is *within one order* (the same part on two lines
of one sales order), so its answer — the order screen with the candidates highlighted — has a
screen to land on. McMaster's is not: the same part can be outstanding on two different orders
placed weeks apart, and there is no single order screen that shows both. FR-032a forbids
picking one.

DigiKey's path is left exactly as it is (FR-033); this is an additional landing, not a
replacement.

---

## 12. Images degrade, and that is already handled

**Decision**: McMaster product images go through `store_listing_images` unchanged.

**Rationale**: Whether McMaster's image host serves bytes to a plain server-side GET from the
LAN is unknown and not worth guessing at. It does not need to be known: the existing path
already fetches server-side, already tallies what landed and what did not, and already flashes
the shortfall to the operator (`_image_tally`). An image host that refuses costs the pictures
and nothing else — the same containment FR-036 states for fields. If it turns out McMaster
serves line drawings as SVG, that is a fact to record after the first real capture, not a
branch to write now.

---

## 13. Testing

**Unit** (`nox -s tests`, network blocked, sub-second): payload parsing — a well-formed order,
a payload with a line missing a price, a line with no part number, a non-object, a wrong
version, an empty line list; the pack-to-unit arithmetic including inexact division; the
service's review states (new / matched / captured / recycled identifier) and its capture
writes; the scan branch, including the three FR-032 cases; and the renamed column, via the
existing DigiKey tests.

**E2E** (`nox -s e2e`, 15-minute timeout, run detached — see `CLAUDE.md`): the real bookmarklet
clicked against `mcmaster_order.html` and `mcmaster_product.html` served from the app's own
origin, reusing `run_bookmarklet` from `tests/e2e/test_product_page_capture.py`; the review;
the confirm; the order screen; a scan that receives; a scan with two candidates. Waits follow
`CLAUDE.md` — the landing is a full navigation, so the review form's presence is the
completion signal (pattern C), and no `wait_for_timeout` is added.

**Not tested, and stated rather than hidden**: the genuinely cross-origin half of the transport
— a real McMaster page over TLS submitting a form to this app over plain HTTP on the LAN. It
cannot be exercised locally for the reasons `test_product_page_capture.py` documents, so it is
a manual check in `quickstart.md`, as it is for Amazon.

**No new pytest markers** are needed, so nothing is added to `pytest.ini` (`--strict-markers`).
