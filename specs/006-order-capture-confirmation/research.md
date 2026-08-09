# Phase 0 Research: Order Capture Confirmation

Six questions had to be settled before the design could be written. None of them came from a `NEEDS CLARIFICATION` marker — the spec carried none — but each had a plausible wrong answer that would have cost more than it saved.

## Where an unconfirmed capture lives

**Decision**: nowhere. An unconfirmed capture is a rendered HTML form and has no existence beyond it.

`POST /api/capture` with a form body — the bookmarklet's request, arriving from the vendor's origin — stops writing and starts rendering `product/capture.html` with the fields it derived from `url` and `document.title`. The operator types a description into that form and submits it to `POST /products/capture`, which is where the write happens. Closing the tab discards a page, which is FR-009 satisfied by construction rather than by cleanup.

**Rationale**: every alternative asks "where does the draft go?", and the answer only matters if a draft has to survive something. Nothing here has to survive anything: the operator is on one machine, the listing is open in the next tab, and the entire lifetime of a draft is the seconds between clicking a bookmark and pressing a button. A form field already survives exactly that long.

**Alternatives considered**:

- **A `capture_drafts` table.** Would need creation, expiry, cleanup, and a decision about what to do with week-old rows. Principle I forbids the machinery, and Principle V would demand a migration for it. It also makes FR-009 a thing to implement — "abandoning must leave no trace" becomes a garbage collector — rather than a thing that is already true.
- **Flask session storage.** No table, but it introduces a second place capture state can live, is invisible in the database, and breaks the moment two bookmarklet tabs are open at once — which is precisely the double-click scenario User Story 3 is about. Two tabs holding two independent forms is the correct behaviour and comes free.
- **Keep writing on click, and let the operator edit afterwards.** This is today's behaviour, and it is what the issue rejects. "Author the description while the listing is in front of you" is not achievable when the write has already happened before the operator has typed anything.

## Why the listing URL becomes a column

**Decision**: add `purchases.listing_url`, and stop putting the URL in `purchases.notes`.

**Rationale**: FR-013 requires the duplicate check to fall back to the listing address when the URL yields no vendor item number. That means querying on the address, and today the address is only present as the entire content of a free-text field — `capture_order` passes `notes=url` to `record_purchase` (`app/catalog_service.py:948`). The receive screen renders that field as an editable textarea (`app/templates/product/receive.html:92`) and invites the operator to write in it. A duplicate check that reads `notes` is therefore a check that stops working the first time somebody uses the notes field for notes.

Two facts were sharing one column. Splitting them is the smaller change, not the larger one: it removes a coincidence rather than adding a feature.

**Alternatives considered**:

- **Match on `notes LIKE 'http%'` or on exact `notes == url`.** Works until the operator types anything. Also means the duplicate check silently depends on the *order* in which the operator did things, which is the kind of behaviour that cannot be explained to the person hitting it.
- **Match on `vendor + listing_title + order_date` when there is no item number.** No migration, which is genuinely attractive. Rejected because the paste-a-URL form allows a blank listing title, and the fallback would then match every untitled capture of that day against every other — turning a missing warning into a wrong one. The bookmarklet always supplies a title, but the path that always works is the paste path, and the fallback has to hold there too.
- **Drop FR-013.** It is half of the duplicate story the issue tells, and it is the half the issue leads with: "When the page address yields no item number there is nothing to recognize, so a second click files a second purchase."

## Why the URL is compared exactly

**Decision**: store the URL as the bookmarklet or the operator supplied it, compare it with `==` after stripping whitespace, and build no normalization.

**Rationale**: the case FR-013 has to catch is the one the issue names — the same page, captured twice, in one sitting. `location.href` on an open tab is byte-identical between two clicks of the same bookmark, so exact comparison catches it completely.

The case exact comparison misses is the operator navigating back to a listing days later and capturing it again, where the URL has picked up different tracking junk. Normalization would have to know which parts of a URL are junk, and that is vendor-specific: Amazon puts `/ref=sr_1_3` in the *path*, not the query string, so "drop the query string" does not even handle the one vendor the code knows best. A normalizer that is right for Amazon and wrong for the next vendor produces false duplicate warnings on genuinely different listings, which is worse than a missed one — a missed warning costs a purchase the operator can delete, a wrong one invites them to discard a real order.

Exact comparison is also the honest boundary to document: it recognizes a repeat click, and it does not claim to recognize a repeat visit.

**Alternatives considered**:

- **Normalize to scheme + host + path.** Wrong for Amazon, as above.
- **Normalize per known vendor.** A table of per-vendor URL rules is a maintenance surface with one user and no measurement behind it. Speculative generality, prohibited by Principle I.
- **Match on the derived item number only, and skip the URL entirely.** That is today's behaviour and is exactly the gap FR-013 closes.

## The collation question

**Decision**: the corroboration test that FR-019 turns on is computed in Python on loaded values. The duplicate lookup's `vendor` and `listing_url` comparisons stay in SQL and their folding is accepted and written down.

The deployment runs `utf8mb4_unicode_ci`, which resolves to `utf8mb4_uca1400_ai_ci` on MariaDB 11 and folds case **and accents**; SQLite collates `BINARY`. A comparison written in SQL therefore means two different things depending on which suite is looking at it, and the unit suite is the one that cannot see the difference.

The rule applied here is: **ask which backend disagrees, then ask what the disagreement costs.**

| Comparison | Where | Folds on MariaDB? | What a wrong answer costs |
|---|---|---|---|
| `manufacturer` and `manufacturer_part_number` against the matched product (FR-019) | **Python**, `.strip().casefold()` | n/a — same on both | Decides whether the operator is asked at all. A false match attaches a purchase to the wrong product silently, which is the exact failure this feature exists to prevent. |
| `vendor_item_id` in the duplicate lookup | SQL | yes | A warning shown for a near-miss identifier. The operator overrules it in one click. Also the existing behaviour, unchanged by this feature. |
| `vendor` in the duplicate lookup | SQL | yes | Same. In practice both sides come from `_vendor_from_url` (`app/product/routes.py:479`) and are byte-identical. |
| `listing_url` in the duplicate lookup | SQL | yes | A warning for two URLs differing only in case. Overruled in one click. |

Every SQL-side comparison feeds a warning the operator can dismiss; the only comparison that acts without asking is Python-side. That asymmetry is the whole argument, and it is why FR-019 is not implemented as a `WHERE` clause even though it would read better as one.

**Alternatives considered**:

- **Do the corroboration in SQL with `func.lower()`.** Handles case but not accents, so it still means two things on two backends — just less obviously. Loading the matched product and comparing two short strings in Python costs nothing; the product is already loaded to render the warning panel.
- **Fold accents in Python too, to match MariaDB.** Would make the Python comparison agree with the deployment's collation — and disagree with the operator's intent, because `Würth` and `Wurth` are plausibly two spellings of one manufacturer but not reliably so. Case folding alone is the conservative choice: it never merges two things that differ by more than capitalization.

## Why corroboration requires both manufacturer and part number

**Decision**: `attach without asking` requires that the capture supplies a manufacturer **and** a manufacturer part number, and that both fold-equal the matched product's. Any missing value means the question gets asked.

**Rationale**: a manufacturer name matches across a vendor's entire catalogue — `Mean Well` corroborates nothing, because Mean Well makes hundreds of things. A part number without a manufacturer is not unique either; short numeric part numbers collide across manufacturers routinely. Only the pair is evidence.

The failure mode being guarded against is asymmetric, which is what settles it. Asking when the answer was obvious costs one click. Not asking when the identifier was recycled corrupts a product's price history invisibly, and the operator has no way to discover it later. When the evidence is incomplete, ask.

A consequence worth stating: an operator who never fills in manufacturer and part number is asked every time a captured item number matches an existing product — that is, on every repeat buy of a catalogued item. That is a real cost, and it is the price of the guarantee in SC-006. It is also self-limiting: filling in the two fields once, on the product, makes every later capture of that item silent.

**Alternatives considered**:

- **Part number alone.** Tempting because it is the more specific of the two. Rejected: collisions across manufacturers are common enough that this would auto-attach on evidence that does not distinguish.
- **Compare the listing title against the recorded one.** Vendor titles churn — the same listing is retitled for SEO without the product changing. This would ask constantly and corroborate almost never, which trains the operator to click through the question without reading it.
- **Ask always, and drop FR-019.** Simpler, and defensible. Rejected because it makes the fast path slower on the common case (a genuine repeat buy) with no gain in safety, and the spec asks for the corroborated shortcut explicitly.

## Why `listing_url` is not indexed

**Decision**: no index.

**Rationale**: the catalogue holds tens of purchases. The duplicate lookup already narrows to one vendor and one calendar day before the URL is compared at all, so the URL comparison runs against a handful of rows. Principle I requires a measured problem before an index; there isn't one.

There is also a structural reason not to reach for one later without thinking: at `VARCHAR(1000)` with `utf8mb4`, the column is 4000 bytes, which exceeds InnoDB's 3072-byte index key limit. Indexing it would mean a prefix index, and a prefix index on a URL indexes the part that is identical across every listing from one vendor. If the lookup ever does need help, the answer is a composite on `(vendor, order_date)`, not anything involving the URL.

**Alternatives considered**: a plain index (impossible at this width), a prefix index (indexes the wrong end of the string), and a stored hash column (a second representation of one fact, to solve a problem nobody has measured).
