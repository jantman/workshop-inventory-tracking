# Deferred Work Ledger

### DW-1: Follow-up review still recommended for 3-1-materialized-path-categories-with-inline-create after the damping cap was spent
origin: review-budget-followup
source_spec: `3-1-materialized-path-categories-with-inline-create.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260724-153649-49e6; this entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-2: Follow-up review still recommended for 3-2-category-rename-with-descendants after the damping cap was spent
origin: review-budget-followup
source_spec: `3-2-category-rename-with-descendants.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260724-153649-49e6; this entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-3: Follow-up review still recommended for 3-3-free-form-tags after the damping cap was spent
origin: review-budget-followup
source_spec: `3-3-free-form-tags.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260724-153649-49e6; this entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-4: Follow-up review still recommended for 4-1-wedge-scan-capture after manual convergence
origin: review-budget-followup
source_spec: `4-1-wedge-scan-capture.md`
severity: low
reason: Four review passes (one inline, three follow-ups) each finalized the story (status: done, tests green) while still recommending an independent follow-up. Converged manually rather than by the orchestrator's damping cap (limits.max_followup_reviews = 1), because the story was completed outside bmad-loop run 20260724-153649-49e6 after its dev session hit the session timeout. Severity fell across the passes (high 1 -> 0, medium 2 -> 1) while patched-finding volume did not, and app/static/js/scan-capture.js grew 189 -> 430 lines, with each pass largely correcting the previous pass's fix to the same defect class. The open design question is whether the in-flight/contamination guard belongs in 4.1 at all: it defends against double-apply, but POST /api/scan has no side effects to double-apply until Stories 4.3/4.5. This entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-5: Follow-up review still recommended for 4-2-pure-scan-classifier after the damping cap was spent
origin: review-budget-followup
source_spec: `4-2-pure-scan-classifier.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260724-153649-49e6; this entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-6: The padded-ECIA-value pre-fill decision is taken — Story 4.4's open entry is closed
origin: story-4-5
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: Story 4.4's ledger entry "the ECIA arm trims the value it looks a product up by while `ecia_fields` keeps the value verbatim, so a padded label hands Story 4.5 a create form pre-filled with the padding" explicitly left the choice to this story. It is taken: the pre-fill is built from a `.strip()`ed copy.
evidence: `_ecia_prefill` in `app/main/routes.py` copies `classification.ecia_fields` through `(value or '').strip()` before deriving `mpn`, `vendor_sku`, `quantity` and `order_number`, so the create form shows — and therefore saves — the same value the resolver looked the product up by. Pinned by `test_ecia_label_with_no_product_prefills_mpn_quantity_and_order` in `tests/unit/test_scan_routes.py`, which scans `1P  RC0805-10K  ` / `Q 25 ` and asserts the URL carries the trimmed values. The DURABLE half of that entry is deliberately NOT closed here and stays open below (DW-7): the fix at the write path — `create_product` stripping identifier-ish columns the way `add_identifier` already does — is a Story 1.3 question, and a hand-typed padded `mpn` still reaches the column by every other route.
status: closed

### DW-7: `create_product` still stores `mpn`/`manufacturer` exactly as submitted, so padding typed (or pasted) into the form survives into the column
origin: story-4-5
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: DW-6 closes the SCAN path's half of Story 4.4's padded-value entry by trimming at the pre-fill boundary, but the write path is unchanged: any caller that submits `mpn=' RC0805-10K '` still stores the padding, and `resolve_scan`'s ECIA arm — which trims its candidate — would then miss it on the exact lookup while `search_products` (which strips its own query) silently succeeds.
evidence: `CatalogService.create_product` and `update_product` pass `mpn`, `manufacturer` and `category_path` through `_clean`, which coerces blanks to NULL but does not strip; `add_identifier` DOES strip its value (`value = ('' if value is None else str(value)).strip()`), so the two write paths disagree about what a stored identifier-ish string is. Reachable today from the create form by hand and from any JSON client. Not closed here because `app/mariadb_catalog_service.py` is read-only in this story and because "which columns are identifier-ish enough to strip" is a Story 1.3/2.1 data decision, not a routing one.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-decision-dw-7
decision: 2026-07-26 Strip identifier-ish columns at the write path — Make `create_product` and `update_product` strip `mpn` and `manufacturer` before storing, matching `add_identifier`'s rule, so every write path agrees about what a stored identifier value is. Leave `description` and `notes` alone - they are prose, not identifiers - and decide `category_path` explicitly (it is already normalized by `normalize_category_path`, so no change is needed there). Add tests pinning that a padded `mpn` submitted by hand and by JSON both store the trimmed value, and that `resolve_scan`'s exact lookup then finds it.

### DW-8: `/products/search` is a placeholder that Epic 8 Story 8.1 must replace, not extend blindly
origin: story-4-5
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: medium
summary: The new `main.product_search` route exists to give the FR36 fallthrough a landing and nothing more: one `search_products(q)` call, no filters, no paging, no ranking, no facets, no result count and no truncation signal. Every limitation the ledger already records about the search MECHANISM is now visible to the operator on a real page.
evidence: `app/main/routes.py`'s `product_search` calls `search_products(query)` positionally with no `filters` and no `limit`, and `app/templates/product/search.html` renders every returned row with no paging control. So the open entries "`search_products` silently truncates to the 50 OLDEST matches with no total and no truncation flag", "matching is a CONTIGUOUS substring of a single column, not tokenized" and "the case fold is ASCII-only and backend-dependent" are all now user-facing: a scan of a distributor's human-readable line lands on an empty results page, a one-character scan lands on 50 arbitrary products, and neither page can say which. AD-17 assigns the mechanism to Epic 8 and Story 8.2 owns faceted, bookmarkable state, so the URL namespace (`/products/search?q=`) was chosen to be the one Epic 8 extends rather than orphans — but the page as shipped should be treated as a stub, and `TestProductSearchPage::test_the_page_issues_only_search_products` pins the single-entrypoint call shape so Epic 8's change is a deliberate one.
status: open

### DW-9: The scanned-identifier block on the create form carries exactly one identifier and offers no edit path afterwards
origin: story-4-5
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: A scan can only ever contribute ONE identifier to a new product, the form renders that one pair, and once the product is created there is no UI anywhere to add, change or remove an identifier — including the one whose attach just failed on a uniqueness collision, whose flashed message tells the operator nothing they can act on.
evidence: `_attach_scanned_identifier` reads a single `identifier_value`/`identifier_type` pair, and `app/templates/product/add.html` renders a single pair, shown only when the pre-fill supplied a value; `app/templates/product/edit.html` was deliberately left untouched and has no identifier fields at all, and `grep -n "add_identifier\|get_identifiers_for_product" app/main/routes.py` shows the service's identifier methods have exactly one route caller between them (the create path). So: an ASIN plus a GTIN on one product needs a second route that does not exist; a mistyped identifier can only be corrected in the database; and the collision message ("… already exists on product 7") names a product the operator cannot reach from the form they are on. A product-identifiers management surface is Epic 2's unfinished UI half rather than this story's — 4.5 is a consumer that adds no service method — but the create form is now the FIRST place identifiers are writable from the UI, which is what makes the missing counterpart visible.
status: done 2026-07-26
resolution: closed by human decision: Accept that identifiers are write-once from the UI and correctable only in the database until a later epic needs more. The scan path only ever emits one identifier type (`gtin`), so the multi-identifier case is currently hypothetical.
decision: 2026-07-26 Close - the create path is enough for now — Accept that identifiers are write-once from the UI and correctable only in the database until a later epic needs more. The scan path only ever emits one identifier type (`gtin`), so the multi-identifier case is currently hypothetical.

### DW-10: An accepted scan deliberately does NOT navigate when the operator has moved to another field, and nothing tells them where it would have gone
origin: story-4-5
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: `scan-capture.js` follows `data.url` only when `refocus()` reports that the scan field still owns focus. That is the right conservative half of the choice — navigating would destroy whatever the operator is typing in the JA ID lookup — but the destination is then discarded silently: the field clears (the accepted signal), and the routed landing is simply never reached.
evidence: `handleSuccess` in `app/static/js/scan-capture.js` gates `window.location.href = data.url` on the same `refocus()` verdict that already prevents a late response from stealing focus, and `tests/e2e/test_wedge_scan.py::TestLateResponseDoesNotClobberTheOperator::test_late_response_does_not_steal_focus_from_another_field` pins it (the URL is not followed, the field is cleared). The intent contract states the client rule as "navigate when `data.url` is a non-empty string" and separately requires that test class to stay green with a routed stub; the focus gate is how both hold at once, and it is a deviation worth recording rather than burying. The gap it leaves is a UX one: a toast offering the destination as a link, or a queued navigation the operator can accept, would close it — but "what should an accepted scan do when the operator has already moved on" is a product decision, and Epic 9's self-sufficient scan-result view is where it naturally belongs.
status: open

### DW-11: Three hardware questions and the trim-rule relocation are re-aimed past Epic 4 — Story 4.4's DW note is answered
origin: story-4-5
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: Story 4.4's entry "three earlier ledger entries now cite symbols this story deleted and describe Story 4.4's parser as future work; they need re-aiming at Story 4.5" is answered here. 4.5 is the last story in Epic 4, so the entries it names cannot be re-aimed at a later Epic 4 story: they are re-aimed at the first work with the PHYSICAL Tera HW0009 and a real distributor label in hand.
evidence: Re-affirmed and re-aimed, none closed: (a) "a keyboard wedge cannot type ASCII control characters into an HTML text input" and (b) "the classifier's ECIA rule requires the literal `[)>` RS `06` header, but it is an open hardware question whether a wedge can deliver RS/GS at all" — both now cite `app/utils/ecia.py`'s `is_envelope`/`_HEADER` rather than the deleted `scan_router._is_ecia_envelope`, and this story's e2e coverage confirms the shape of the gap rather than closing it: `tests/e2e/test_scan_routing.py::test_an_ecia_envelope_prefills_mpn_quantity_and_order_references` has to place the envelope in the field with `page.evaluate` because a keypress cannot type GS. (c) "an extra LEADING separator before an ECIA header misroutes the envelope to free_text" — unchanged, and `app/main/routes.py` is no longer off-limits in principle but absorbing separators in `_clean_scan_input` would still be a fourth copy of the trim rule, which this story's Never list forbids. (d) "`ecia.is_envelope` recognizes format 06 only when it is FIRST in the message". (e) The `_SCAN_TRIM` relocation entry stands unchanged — the rule still lives as a private symbol in `app/main/routes.py` with a second copy in `ScanCapture.stripOuter`, and its "Story 4.4's parser is correct only if the trim set never widened" line should now read as a statement about shipped code rather than future work. Of the five, (a)-(d) need a decision nobody can take without the hardware; (e) needs a home for a pure util, which every Epic 4 story's Never list has so far forbidden it.
status: done 2026-07-26
resolution: already resolved: Commit 23aecd3 carried out the re-aiming this entry records. Its five items are now individually ledgered with corrected locations and explicit back-references: deferred-work.md:447 (item a -> DW-57), :464 (item e -> DW-59), :513 (item b -> DW-65), :530 (item c -> DW-67), :669 (item d -> DW-84). Each of those entries cites `app/utils/ecia.py` (`is_envelope`, `_HEADER`) rather than the deleted `scan_router._is_ecia_envelope`, so the re-aiming this entry exists to record has been performed and the entry itself carries no residual work.

### DW-12: `api_record_purchase` accepts `NaN`/`Infinity` for `unit_price` and reports success while storing NULL
origin: story-4-5-review
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: medium
summary: The JSON purchase endpoint parses `unit_price` with `Decimal(str(...))` inside a `try` that catches only `InvalidOperation`/`ValueError`. `Decimal('NaN')` and `Decimal('Infinity')` raise neither, so the request answers 201 with a `purchase` object whose price is `None` — the operator (or client) is told the price was recorded when it was silently dropped.
evidence: Found by adversarial review of Story 4.5 and reproduced against the real app: `POST /api/products/<id>/purchases` with `unit_price: "NaN"` returns 201 and stores `NULL`. Not caused by this story — the parsing predates it (Story 1.4) and `POST /api/products/<int:product_id>/purchases` is explicitly on 4.5's Never list. The review surfaced it because 4.5's new HTML purchase form was written to mirror that parsing exactly; the form's copy WAS fixed (it now rejects non-finite and negative values with a field-scoped message), so the two entry points writing the same column now disagree, and the JSON one is the lenient half. Closing it is a one-line `is_finite()` guard in `api_record_purchase`, ideally taken together with the length rules the JSON endpoint also does not enforce.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-json-purchase-bounds-parity

### DW-13: `_validate_product_form`'s receipt and duplicate rules are reachable through `product_edit`, which renders no such fields and no feedback for them
origin: story-4-5-review
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: `product_edit` shares `_validate_product_form` with `product_add`, so a crafted `POST /products/edit/<id>` carrying `quantity=0` (or `duplicate_of`) fails validation and re-renders — but `app/templates/product/edit.html` has no `quantity`/`vendor`/`vendor_sku`/`order_number` input and no `invalid-feedback` block for any of them, so the message renders nowhere and the operator sees a silent 200 no-op instead of a 302.
evidence: Reproduced: `POST /products/edit/<id>` with a valid description plus `quantity=0` returns 200 rather than 302 and writes nothing, with no visible error. Unreachable from the real edit form, which submits none of those names — only a hand-crafted POST hits it. The shared validator is what the intent contract asked for ("`_validate_product_form` owns the check so every caller of it inherits the rule"), and that is the right call for the duplicate gate specifically, since a bypass there would be an FR41 hole. The residue is that inheriting the RECEIPT rules buys nothing on the edit form and costs a silent failure mode. Closing it means either scoping the receipt rules to the add form or giving `edit.html` the feedback blocks; both are cosmetic relative to the writes they guard, which is why it was not patched under time.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-product-form-add-edit-parity

### DW-14: `POST /api/scan` is CSRF-exempt, unauthenticated and unthrottled, and now drives a leading-wildcard `LIKE` over six unindexed columns per request
origin: story-4-5-review
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: medium
summary: Story 4.1 deferred the CSRF-exemption and rate-limiting questions on the stated grounds that they matter "once the endpoint has an effect". 4.5 kept the endpoint read-only, so those entries stay correctly open — but "read-only" is not "cheap": every unmatched scan now opens up to two sessions and runs `search_products`, whose `LIKE '%…%'` over `internal_id`/`description`/`notes`/`manufacturer`/`mpn` plus an EXISTS on `product_identifiers` is a full table scan, with an attacker-chosen pattern of up to `MAX_SCAN_LENGTH` (4096) characters, driveable cross-site from any page.
evidence: Found by adversarial review of Story 4.5. The endpoint's docstring originally justified the exemption with "a cross-site POST here costs one SELECT"; that sentence was corrected in this story to state the real cost and to point at the two open ledger entries, but the exposure itself is unchanged and was deliberately not narrowed — the exemption is what makes the wedge work without a token, and adding throttling or a token is exactly the decision the existing `:144` and `:148` entries reserve. Story 4.1 bounded the log-amplification vector with `_SCAN_LOG_CHARS`; the database vector is larger and is now bounded only by `MAX_SCAN_LENGTH`. The cheapest partial mitigations, if this is ever taken up, are capping the text that reaches the fallthrough search (independently of what reaches the classifier) and per-IP throttling at the reverse proxy rather than in Flask.
status: done 2026-07-26
resolution: closed by human decision: The app is unauthenticated on a workshop LAN by design; every other route shares the exposure, so a per-endpoint hardening is the wrong shape and the honest answer is that this is accepted rather than deferred.
decision: 2026-07-26 Close - accept the LAN posture — The app is unauthenticated on a workshop LAN by design; every other route shares the exposure, so a per-endpoint hardening is the wrong shape and the honest answer is that this is accepted rather than deferred.

### DW-15: After a routed scan navigates, `#scan-input` is no longer focused, so a consecutive scan needs a click
origin: story-4-5-review
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: medium
summary: Every successful scan now loads a new page, and nothing focuses the scan field on load — `base.html` has no `autofocus` and `ScanCapture.init()` only binds handlers. The operator therefore clicks (or tabs) before each scan after the first, which is in tension with FR35's premise that wedge scanning needs no pointing device.
evidence: Found by adversarial review of Story 4.5, which noticed that Story 4.1's `test_successful_scan_clears_field_and_keeps_focus` — the test that pinned post-scan focus — necessarily changed meaning once a successful scan navigates. Before 4.5 a scan did nothing, so retained focus was free; the regression is a real cost of making scans useful, not a defect in the routing. It was NOT patched because there is no single right answer: focusing `#scan-input` on every page load is correct on the product-detail and search landings and actively wrong on the create form, where the operator's next action is typing a description into a different field. Deciding per-destination — or giving the scan field a touch-reachable arming affordance — is Epic 9's charter (Story 9.1 touch equivalents, 9.2 the self-sufficient scan-result view, 9.3 form-state persistence), and it should be taken there rather than guessed here. Related to DW-10, which is the same question for the case where the operator moved away deliberately.
status: open

### DW-16: `tests/e2e/test_scan_routing.py` imports fixtures and helpers from `tests/e2e/test_wedge_scan.py`, coupling two modules through collection order
origin: story-4-5-review
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: The new e2e module reuses `simulate_wedge_scan`, the scan-input selector and related helpers by importing them from a sibling test module rather than from a conftest. Renaming or reorganizing anything in `test_wedge_scan.py` now breaks a file that does not appear in its diff.
evidence: Found by adversarial review of Story 4.5. The helpers are genuinely shared and the import works, so nothing is red — but shared e2e machinery belongs in `tests/e2e/conftest.py` (where `live_server` and `page` already live) rather than in a test module that pytest may collect in either order. A related, smaller instance in the new unit tests: several assertions reason about autoincrement arithmetic (`get_product(existing + 1) is None`) instead of the actual set of products, which is correct today only because the SQLite fixture starts empty. Both are test-hygiene items with no user-visible consequence, which is why they were deferred rather than patched.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-e2e-test-infrastructure-hygiene

### DW-17: A scan longer than the `q` bound can still land on a results page that excludes the hits it counted
origin: story-4-5-review-2
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: medium
summary: `q` is now bounded by the URL budget (1024 characters) rather than by a column, which puts the truncation point past every VARCHAR the fallthrough search touches — but a scan longer than that which matched through `products.notes` (TEXT) still reaches the search page as a PREFIX, and a prefix matches a superset that `search_products`' 50-row ascending-id cap can fill with other products entirely.
evidence: Found by the second adversarial review of Story 4.5, which reproduced the original 255-character form against the real app: one 1000-character scan, 60 products matching only the prefix and 3 matching the full text answered `outcome=search, hit_count=3` and routed to a page listing 50 products, none of them the 3. The bound was raised and `test_a_truncatable_q_does_not_evict_the_hits_it_counted` pins the fixed case (it fails at the old bound, verified). What remains is the same mechanism past 1024 characters, and it cannot be closed by bounding alone: the acceptance criterion "the products listed are exactly the `free_text_hits` the endpoint counted" is only reachable if the page can be told WHICH rows to show, or if `search_products` can order by relevance rather than by id, or if the resolver's searched text is carried rather than re-derived — and AD-15 freezes `ScanResolution` to three fields, while the search mechanism and its 50-row cap are Epic 8's under AD-17. Bounded honestly rather than claimed away: `_scan_url_value`'s docstring now states the eviction rather than the earlier, wrong "returns a SUPERSET, so never fewer".
status: open

### DW-18: FR41's duplicate gate is enforced on a client-supplied hidden field, so the server has no independent knowledge that a scan matched
origin: story-4-5-review-2
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: medium
summary: `_validate_product_form` demands `confirm_duplicate=yes` only when the POST carries `duplicate_of`, and `duplicate_of` reaches the server only because the rendered form put it in a hidden input. A POST that simply omits the field creates the second product with no confirmation and no trace that the scan had already resolved.
evidence: Found by the second adversarial review of Story 4.5. The mechanism is exactly what the intent contract specified ("the create form carries a hidden `duplicate_of` field; when it is non-blank and the submitted `confirm_duplicate` is not `'yes'`, the POST re-renders"), and it is implemented faithfully — the gate is in the shared validator, before any write, so no rendered path can reach the write unconfirmed. What overstates it is the acceptance criterion "it is never possible to reach that write without one": that is true of the UI flow and of nothing else. Closing it needs server-side state the gate can trust — a signed token minted by the scan endpoint, or a session note — which is a design decision about how much a scan's resolution should bind a later form POST, and is adjacent to the at-least-once/idempotency questions Epic 7 owns. No unattended fix: narrowing the AC and adding a token are different answers.
status: done 2026-07-26
resolution: closed by human decision: Restate the AC to what is true and what FR41 actually needs: the rendered create flow cannot reach the write without a confirmation. A client that hand-crafts a POST omitting `duplicate_of` is not the operator FR41 protects, and the app is unauthenticated anyway, so a forged POST is not the weakest link.
decision: 2026-07-26 Narrow the acceptance criterion — Restate the AC to what is true and what FR41 actually needs: the rendered create flow cannot reach the write without a confirmation. A client that hand-crafts a POST omitting `duplicate_of` is not the operator FR41 protects, and the app is unauthenticated anyway, so a forged POST is not the weakest link.

### DW-19: The scan-arrival banner is a bookmarkable re-invitation to record the same receipt again
origin: story-4-5-review-2
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: medium
summary: `_scan_arrival_banner` renders from `request.args` on every GET, so `/products/<id>?scan_kind=ecia&quantity=100&order_number=PO-9` re-offers the same pre-filled purchase every time it is revisited — by Back, by history, by a copied link — and nothing downstream deduplicates.
evidence: Found by the second adversarial review of Story 4.5. `POST /api/scan` was deliberately kept read-only so a duplicated scan burst costs only a lookup, and the existing at-least-once/CSRF/rate-limiting entries are aimed at that endpoint. The mutation the banner leads to is not free and is not covered by them: `record_purchase` takes no request key (`app/mariadb_catalog_service.py:1352` defers idempotent capture to Epic 7), `purchase_add` is an ordinary POST with no post-submit guard, and there is no uniqueness rule over `(product_id, order_number)`. So the receipt half of FR41 can be double-recorded by ordinary browser navigation, which then double-counts in the FR20/FR21 history and in "Last paid". Closing it means either an idempotency key on `record_purchase` (Epic 7's, and a service change this story is forbidden) or a one-shot token on the banner link; both are decisions rather than patches.
status: open

### DW-20: The create form offers vendor-scoped identifier types with no vendor-scope input, so such a row stores an empty scope
origin: story-4-5-review-2
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: medium
summary: `_identifier_type_choices()` offers every `IdentifierType` except `INTERNAL`, which includes the vendor-scoped ones (`VENDOR_SKU`, `ASIN`, `FNSKU`, `app/models.py:174`). The form has no vendor-scope control and deliberately passes no `vendor`, so choosing one of those types stores `vendor_scope=''` — the sentinel that means "global" — and a second vendor's identical SKU then collides with it instead of coexisting.
evidence: Found by the second adversarial review of Story 4.5, and reproduced: a create POST with `identifier_type=VENDOR_SKU` writes a row whose `vendor_scope` is empty. The choice list is what the intent contract specified verbatim ("the `IdentifierType` values minus `INTERNAL`"), and the omission of `vendor` was itself a review fix this story applied for a good reason — passing the receipt block's Vendor input would silently make an unrelated field the identifier's uniqueness scope. So the two halves are each defensible and the pair is not: either the list should be narrowed to the globally-scoped types, or the block needs its own vendor-scope input. Both deviate from an explicit contract instruction, which is why neither was taken unattended. Unreachable from a scan — only `gtin` emits a type — so it needs an operator to pick one by hand.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-decision-dw-20
decision: 2026-07-26 Add a vendor-scope input to the identifier block — Give the Scanned Identifier block its own vendor-scope input, shown (or required) when the chosen type is vendor-scoped, and pass it to `add_identifier` as `vendor`. Keep it distinct from the First Receipt block's Vendor field so the two cannot be conflated, and default it to blank rather than to the receipt vendor.

### DW-21: A routed scan navigates away from a partly-filled form without warning
origin: story-4-5-review-2
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: medium
summary: The scan field lives in `base.html` and is therefore present on the create and purchase forms themselves. A scan submitted while the operator has typed into one of those forms now navigates, discarding everything unsaved, with no prompt.
evidence: Found by the second adversarial review of Story 4.5. Before this story a successful scan did nothing, so the field was harmless on a form page; making scans useful is what created the hazard. `handleSuccess` navigates whenever the response belongs to the in-flight scan and the scan field still holds focus — which is precisely the state after a wedge fires — and there is no dirty-form check anywhere in `scan-capture.js`. The conservative half of the focus gate (DW-10) covers the operator having moved to another FIELD, not their having filled the form around the scan input. Closing it well is Epic 9's: Story 9.3 owns form-state persistence, and the alternatives (a `beforeunload` prompt, a queued navigation the operator accepts, or persisting the form and restoring it) are the same decision as DW-15's "what should an accepted scan do when the operator is in the middle of something".
status: open

### DW-22: A scanned first receipt cannot be given a price without creating a second Purchase
origin: story-4-5-review-2
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: The create form's First Receipt block carries `quantity`, `order_number`, `vendor` and `vendor_sku` and no `unit_price`, and there is no purchase edit or delete route anywhere — so the only way to price the receipt captured on create is to record a SECOND Purchase, which then duplicates the row in the FR20/FR21 history and skews "Last paid".
evidence: Found by the second adversarial review of Story 4.5. `_RECEIPT_FIELDS` is exactly the four field names the intent contract listed for that fieldset, so adding `unit_price` would deviate from it; `grep -n "@bp.route.*purchase" app/main/routes.py` shows only `purchases/add` and the untouched JSON endpoint, so nothing can amend a Purchase after the fact. A distributor label carries no price either (nothing in `ECIA_FIELD_KEYS` is one), so the pre-fill loses nothing — the gap is only for the operator who knows the price while creating the product. Either the block gains the field or the story's scope should say plainly that first-receipt capture is price-less; a purchase edit path would close it more generally and belongs with whatever story gives Purchases a management surface.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-decision-dw-22
decision: 2026-07-26 Add `unit_price` to the First Receipt block — Add `unit_price` to `_RECEIPT_FIELDS` and to the create form's First Receipt fieldset, validated with the same `Numeric(10, 2)` magnitude/scale/non-finite rules `_parse_purchase_form` applies, so the receipt captured at create time can be priced without a second Purchase. Update the fieldset's help text and the tests that pin the four-field set.

### DW-23: A GTIN check-digit failure is still judged after the commit, and the recovery its message names does not exist
origin: story-4-5-review-2
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: Three of the four purely-checkable identifier faults were moved in front of the write by this review pass (a blank type, an unknown type, an over-long value). The fourth — a value typed `GTIN` whose check digit does not validate — is still first judged inside `add_identifier`, after `create_product` has committed, and the service's message tells the operator to "store it as GTIN_UNVALIDATED", which no surface lets them do.
evidence: Found by the second adversarial review of Story 4.5 and confirmed: the POST returns 200 with the product created and only an advisory flash. It was not moved with its three siblings because the check is not makeable from the form alone — it means re-deriving GS1 check-digit validation and the 14-digit normalization that `add_identifier` applies (`app/mariadb_catalog_service.py:1680-1687`), from `app/utils/gtin.py`, which is read-only in this story. That would be a third copy of a normalization rule, which every Epic 4 story's Never list has resisted for the same reason. Reachable only by hand-editing the type or the value — the classifier emits `GTIN` only for a value whose check digit already validated — and the honest fix is either a service-side pure validator the route may call, or the identifier-management surface DW-9 wants, at which point the message becomes actionable.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-pre-commit-gtin-check-digit

### DW-24: The purchase form accepts a `received_date` earlier than its `order_date`
origin: story-4-5-review-2
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: `_parse_purchase_form` validates each date's format independently and never compares them, so a Purchase can record having been received before it was ordered — and nothing downstream refuses it either.
evidence: Found by the second adversarial review of Story 4.5. `record_purchase` validates nothing (`app/mariadb_catalog_service.py:1339`), and `api_record_purchase` has had the same gap since Story 1.4, so the HTML form inherits it rather than introducing it. Not patched because it is a new business rule rather than a column constraint: the pair may be legitimately partial (either date may be NULL), a receipt logged against a back-dated order is real, and FR19's on-order/received signals are the consumer that would define what "impossible" means. Should be taken with the same rule applied to both entry points at once, as DW-25 says of the other bounds they now disagree about.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-decision-dw-24
decision: 2026-07-26 Refuse received-before-ordered on both entry points — Add one cross-field rule - when both `order_date` and `received_date` are present, `received_date` must not precede `order_date` - implemented once and applied by both `_parse_purchase_form` and `api_record_purchase`, with a field-scoped message on the HTML side and a 400 with `field='received_date'` on the JSON side. Leave the partial cases (either date NULL) untouched. Take it in the same change as the json-purchase-bounds-parity bundle so the two entry points are written from one list.

### DW-25: `api_record_purchase` still lacks the magnitude, scale and length bounds the HTML form now enforces on the same columns
origin: story-4-5-review-2
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: medium
summary: This pass gave the HTML purchase form `Numeric(10, 2)`-shaped bounds on `unit_price` (a value past `99999999.99` is refused rather than failing opaquely on MariaDB; a third decimal place is refused rather than silently rounded). The JSON endpoint writing the same column enforces neither, and — per the still-open DW-12 — not the non-finite check nor the length limits either.
evidence: Found by the second adversarial review of Story 4.5 and reproduced through the form before the fix: `1E+30` stored `1000000000000000019884624838656.00` under SQLite and cannot be stored at all under MariaDB; `0.005` reported success while storing `0.01`. `POST /api/products/<int:product_id>/purchases` is on 4.5's Never list and was not touched, so the two entry points to one column now disagree in four ways rather than DW-12's one. Closing it is a handful of guards in `api_record_purchase` mirroring `_parse_purchase_form`, ideally taken as one change together with DW-12 and DW-24 so the JSON and HTML rules are written from the same list rather than converging by accident.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-json-purchase-bounds-parity

### DW-26: An `internal` scan that matched no product pre-fills `description` with the raw label rather than the id it contains
origin: story-4-5-review-2
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: `_scan_prefill_args` sends `internal` scans down the same AIM-stripped-raw path as free text, so a scan of `96WITABC123` whose product no longer exists opens the create form with `96WITABC123` in Description — the field that becomes the product's label — while `_scan_search_text` uses the bare `normalized_value` (`ABC123`) for the very same scan.
evidence: Found by the second adversarial review of Story 4.5. The two derivations of "what this scan says" disagree inside one function pair, and the operator has to hand-edit the AI and the ownership token out of the description before saving. The behavior is what the intent contract's pre-fill table specified (`internal`, `free_text` -> `description` <- "the AIM-stripped raw scan"), which is why it was not changed here. It is also a narrow case: an internal label exists because this system minted it, so a scan of one that matches nothing means the product was deleted or the label predates the database. The better pre-fill is probably `normalized_value` in `description` (or in a `notes` line recording that the label matched nothing), and choosing needs the story that decides what a re-adopted orphan label should mean — Epic 2's identifier-management half, alongside DW-9.
status: open

### DW-27: A distributor scan records a Purchase the operator never asked for, dated today
origin: story-4-5-review-3
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: medium
summary: `_ecia_prefill` puts the ECIA `P` record into `vendor_sku`, and `vendor_sku` is one of `_RECEIPT_FIELDS`, so the "any non-blank receipt field records one Purchase" trigger fires on a value the SCAN filled in rather than the operator. Scanning a `1P`+`P` label, typing only a description and saving writes a Purchase whose only real content is the distributor's part number — with `order_date` defaulted to today by `record_purchase`, a receipt date nobody entered.
evidence: Found by the third adversarial review of Story 4.5 and reproduced: `[)>␞06␝1PABC-123␝PXYZ-999␝␞␄` routes to `/products/add?mpn=ABC-123&vendor_sku=XYZ-999`, and a save with only a description produces `Purchase(vendor=NULL, vendor_sku='XYZ-999', quantity=NULL, unit_price=NULL, order_number=NULL, order_date=<today>)` in the FR20/FR21 history. The fieldset's own help text — "Leave blank to create the product without a purchase record" — is misleading in exactly this case, because it was not the operator who filled it in. Both halves are explicit intent-contract instructions (`vendor_sku` <- `P` in the pre-fill table; the four `_RECEIPT_FIELDS` names in the trigger), so neither could be changed unattended. The candidate fixes are all decisions: trigger only on the fields a human plausibly typed (`quantity`/`order_number`), require an explicit "record a first receipt" checkbox, or leave `order_date` NULL when the receipt was scan-derived rather than typed. Not visible to the suite because no test submits an ECIA-prefilled create form. Adjacent to DW-22, which is the same fieldset's other half.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-decision-dw-27
decision: 2026-07-26 Trigger only on fields a human plausibly typed — Narrow the Purchase trigger to `quantity` and `order_number` - the two receipt fields a scan does not pre-fill from a part-number record - so a scan-derived `vendor_sku` alone never creates a Purchase, while a real receipt (a quantity or an order number, both of which ECIA labels do carry and the operator does confirm) still does. Add the e2e/unit coverage that submits an ECIA-prefilled create form, which nothing currently does.

### DW-28: `_bounded_scan_url`'s halving can cut `q` far below the bound DW-17 records as the safe one
origin: story-4-5-review-3
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: medium
summary: DW-17 records the residual eviction risk as beginning past `_SCAN_URL_Q_LIMIT` (1024 characters), "past every VARCHAR the fallthrough search touches". `_bounded_scan_url` then halves the longest argument repeatedly until the assembled URL fits 7000 characters, which for a multi-byte alphabet drives `q` well back inside that range — a 4096-character CJK or emoji scan percent-encodes to roughly twelve bytes per character, so `q` is halved from 1024 to 256 while `hit_count` was computed from the full scan.
evidence: Found by the third adversarial review of Story 4.5, reading the two bounds against each other. Each is individually correct — the transport bound genuinely can only be measured on the assembled URL, and truncating the longest value is the least-bad way to hit it — but their composition means the truncation point is a function of the scanned alphabet rather than the fixed 1024 the ledger and the docstring both state. The consequence is DW-17's exactly: a prefix matches a superset that `search_products`' 50-row ascending-id cap can fill with other products. DW-17 is deliberately not edited (the orchestrator owns it); this entry records the composition. The cheap partial fix is to floor the halving so `q` is never cut below a stated minimum and to drop OTHER arguments first, since every one of them is a re-editable pre-fill while `q` is the only value the results depend on.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-scan-url-q-floor

### DW-29: The identifier rules are inherited by `product_edit`, which renders neither field nor feedback
origin: story-4-5-review-3
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: DW-13's shape, on the field set this review pass touched. `_validate_product_form`'s identifier rules (a value with no type, an unknown or `INTERNAL` type, a value over 255 characters) are shared with `product_edit`, whose `edit.html` has no `identifier_value` input and no `invalid-feedback` block for either name — so a POST carrying one gets a silent 200 that writes nothing and says nothing.
evidence: Found by the third adversarial review of Story 4.5. This pass fixed the half that was reachable on the ADD form (an unknown type beside a BLANK value raised an error the add template also hides, because the whole Scanned Identifier card is conditional on `identifier_value`; every identifier rule is now gated on a non-blank value, and `TestNoErrorRendersNowhere` pins it). What remains is the edit form, which renders none of these fields at all, so only a hand-crafted POST reaches it — unreachable from the real UI, exactly as DW-13 describes for the receipt fields. Closing it is the same choice DW-13 names: scope the add-only rules to `product_add`, or give `edit.html` the feedback blocks. Should be taken together with DW-13 rather than separately.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-product-form-add-edit-parity

### DW-30: `product_add` and `product_edit` now tell the operator two different stories about the same failure
origin: story-4-5-review-3
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
summary: The previous review pass made `product_add` flash "Product created successfully!" unconditionally and append any post-commit follow-up failures beside it, for a good reason (FR41's confirmed-duplicate path can only ever produce a refused identifier, and suppressing the success made a working save look like a failed one). `product_edit`'s tag-apply failure still returns early and never flashes "Product updated successfully!", so the identical failure mode — row committed, follow-up failed — reads as a partial success on one form and as an outright failure on the other.
evidence: Found by the third adversarial review of Story 4.5. `product_add`'s change was deliberate and its test was inverted to match; `product_edit` was not touched because it is outside this story's scope (4.5 adds scan destinations, and the edit form is neither). The add form's behavior is the correct one of the two — the product exists either way, and the operator's natural response to "the save failed" is a resubmit, which on the create path is how a second product gets made. Closing it means applying the same collect-then-flash shape to `product_edit`, ideally alongside DW-13/DW-29, since all three are about the two forms sharing machinery they do not share surfaces for.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-product-form-add-edit-parity

### DW-31: Follow-up review still recommended for 4-5-scan-outcome-routing-in-the-ui after the damping cap was spent
origin: review-budget-followup
source_spec: `4-5-scan-outcome-routing-in-the-ui.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260724-153649-49e6; this entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-32: Per-request SQLAlchemy engine/pool creation (systemic)
origin: migrated from legacy ledger ("Deferred from: code review of 1-3-product-create-edit-detail (2026-07-23)"), 2026-07-26
location: `app/mariadb_catalog_service.py:51-58`, `app/mariadb_inventory_service.py:140`, `app/main/routes.py:20-28`
reason: In production, `_get_storage_backend()` returns a fresh unconnected `MariaDBStorage()` (`engine=None` until `connect()`, which routes never call), so both `CatalogService` and the pre-existing `InventoryService` fall back to `_create_engine()` — building a new pooled engine from class-level `Config.SQLALCHEMY_DATABASE_URI` on every request, never disposed, and ignoring `storage.database_url`. Fix belongs at the app level (shared/app-scoped engine or connected storage singleton) and should cover both services at once.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-app-scoped-database-engine

### DW-33: No test in the repo ever executes an Alembic migration, so `upgrade()`/`downgrade()` correctness is verified only by inspection
origin: migrated from legacy ledger ("Deferred from: code review of 1-3-product-create-edit-detail (2026-07-23)"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/2-4-internal-identifier-generation-and-gs1-ai-96-encoding.md`
location: `tests/conftest.py`, `migrations/versions/5aeb89e22451_add_products_internal_id.py`
reason: No test executes a migration, so `upgrade()`/`downgrade()` correctness is verified only by inspection — now that migrations carry data logic, not just DDL.
evidence: `tests/conftest.py` builds the unit-test schema with `Base.metadata.create_all`, and no test imports alembic or runs `manage.py db upgrade`; the integration (MariaDB testcontainer) session does not run migrations either. Story 2.4's `5aeb89e22451_add_products_internal_id.py` is the first migration with a *data* backfill (generating ids, adopting pre-existing INTERNAL rows, inserting derived identifier rows) and a non-trivial downgrade — a typo in a table stub or a column added by a later story would surface only against real operator data. A migration-runner test (fresh DB → `upgrade head` → assert schema + backfill → `downgrade` → assert reversal) would cover this migration and every future one.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-mariadb-integration-test-session

### DW-34: `product_identifiers` uniqueness is case-sensitive under SQLite but case-insensitive under MariaDB, so identifier case-semantics differ between test and prod
origin: migrated from legacy ledger ("Deferred from: code review of 1-3-product-create-edit-detail (2026-07-23)"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/2-1-typed-identifier-entity-and-uniqueness.md`
location: `uq_product_identifiers_type_value_scope` on `product_identifiers`
reason: `product_identifiers` uniqueness is case-sensitive under SQLite (unit tests) but case-insensitive under MariaDB's default collation, so identifier case-semantics differ between test and prod.
evidence: SQLite's default `BINARY` collation is case-sensitive; MariaDB's default `utf8mb4_*_ci` is case-insensitive. The `uq_product_identifiers_type_value_scope` index therefore enforces different uniqueness for case-differing values (e.g. `B01abc` vs `B01ABC`) in prod vs the passing unit tests. No live caller yet; resolving well needs a per-type case-semantics decision (numeric GTIN / uppercase INTERNAL & ASIN are case-stable; MPN / VENDOR_SKU may not be) — e.g. pin a binary collation on the key columns or fold case explicitly.
status: done 2026-07-28
resolution: resolved by sweep bundle dw-decision-dw-34
decision: 2026-07-26 Pin a per-column collation in a migration — Decide the case semantics per column - a binary collation on the case-stable identifier columns (`products.internal_id`, and `product_identifiers.value` for the types that are case-stable) and an explicit `_ci` collation where folding is wanted - then pin it in a migration covering every existing table, together with an explicit charset, so the deployed behavior stops depending on the server default. Reconcile with the code paths written against folding semantics (`set_product_tags`' collision handling, `list_tags`' Python grouping, `rename_category_path`'s equivalents) and decide whether deployed data needs migrating. This also unblocks DW-51 and DW-73.

### DW-35: `create_product`'s let-the-UNIQUE-constraint-arbitrate retry design is exercised only against SQLite, never against the MariaDB backend it runs on
origin: migrated from legacy ledger ("Deferred from: code review of 1-3-product-create-edit-detail (2026-07-23)"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/2-4-internal-identifier-generation-and-gs1-ai-96-encoding.md`
location: `app/mariadb_catalog_service.py` (`create_product`, `_internal_id_is_taken`), `tests/unit/test_catalog_service.py::TestInternalIdGeneration`
reason: `create_product`'s let-the-UNIQUE-constraint-arbitrate design (flush → catch `IntegrityError` → classify as collision-or-foreign → retry) is exercised only against SQLite, never against the MariaDB backend it actually runs on.
evidence: Every test covering the mechanism (`TestInternalIdGeneration` in `tests/unit/test_catalog_service.py`) is `@pytest.mark.unit`, and the `test_storage` fixture in `tests/conftest.py` points `MariaDBStorage` at a temp SQLite file. Where and how a UNIQUE violation surfaces is backend-specific: the retry loop wraps `session.flush()` only, so it depends on constraints being evaluated per statement rather than at COMMIT, and `_internal_id_is_taken`'s re-query classification depends on the post-rollback session state. Both hold for InnoDB today, but nothing verifies it — a backend that deferred either would silently convert every collision into `create_product` returning `None`. An `@pytest.mark.integration` case against the existing `mariadb_testcontainer` fixture (force a duplicate candidate, assert the retry commits) would close it, and would cover the same mechanism for any future sole-writer column.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-mariadb-integration-test-session

### DW-36: A `fnc1_substitute` whose character is also the marker's first character silently breaks every decode of a genuine label
origin: migrated from legacy ledger ("Deferred from: code review of 1-3-product-create-edit-detail (2026-07-23)"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/2-5-foreign-payload-rejection-and-ownership-text.md`
location: `app/utils/gs1.py` (`decode`, `_require_grammar`)
reason: A `fnc1_substitute` whose character is also the marker's first character silently breaks every decode of a genuine label — the same total two-way outage the token-room rule fails loudly on, but with no guard.
evidence: `decode` in `app/utils/gs1.py` strips one leading `FNC1`-or-`fnc1_substitute` prefix before matching the marker, so with `ai='96', token='WIT', fnc1_substitute='9'` the bare scan `'96WITABC1234567'` has its leading `9` consumed, leaves `'6WITABC1234567'`, fails `startswith('96WIT')` and returns `None` — verified by execution. Every internal label becomes unscannable with no error anywhere, which is exactly the failure mode Story 2.5 chose to reject loudly for a too-long token (`_require_grammar`'s token-room rule). The stripping logic is Story 2.4's and predates this change; `fnc1_substitute` has no config key yet (Epic 4 adds one with its consumer), so today it is only reachable from a direct caller — but the guard belongs beside the other grammar checks in `_require_grammar` before that key exists.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-gs1-grammar-configurability

### DW-37: The category field measures its 512-character limit twice with different rules, so a Unicode case that lengthens on lowercasing turns an accepted form into a generic save failure
origin: migrated from legacy ledger ("Deferred from: code review of 1-3-product-create-edit-detail (2026-07-23)"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-1-materialized-path-categories-with-inline-create.md`
location: `app/main/routes.py:757-766` (`_validate_product_form`), `app/utils/category.py:113` (`normalize_category_path`)
reason: The category field measures its 512-character limit twice with different rules — raw in the route, normalized in the util — and the rare Unicode case where lowercasing *lengthens* a string turns a form the route accepted into a generic "please try again" save failure with no field-level message.
evidence: `_validate_product_form` (`app/main/routes.py:757-766`) measures `len(form_data['category_path'])` on the submitted string, while `normalize_category_path` raises `InvalidCategoryPathError` on the normalized result (`app/utils/category.py:113`), which `create_product`/`update_product` swallow into their `None`/`False` failure returns. Normalization usually shortens, but `'İ'.lower()` is two characters (`i` + U+0307), so `'İ' * 300` is 300 raw characters (accepted by the route) and 600 normalized (rejected by the util) — the operator sees a generic failure. Symmetrically, a 520-character path of slashes and spaces that would normalize to 300 characters is rejected up front with "Category must be 512 characters or fewer". Resolving it well needs a decision the story deliberately constrained (Story 3.1 forbade changing the route's existing message or normalizing outside the service): either move the length check onto the normalized value, or have the service surface a `ValidationError` the form can render on the field.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-category-length-rule-single-measure

### DW-38: The E2E server's `clear_test_data()` never truncates `products`, `purchases`, `attachments` or `product_identifiers`, so catalog rows accumulate across the session and across runs
origin: migrated from legacy ledger ("Deferred from: code review of 1-3-product-create-edit-detail (2026-07-23)"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-1-materialized-path-categories-with-inline-create.md`
location: `tests/e2e/test_server.py:311-332` (`clear_test_data`)
reason: `clear_test_data()` never truncates `products` (nor `purchases`, `attachments`, `product_identifiers`), so catalog rows — and therefore the category vocabulary that autocomplete draws from — accumulate for the whole session and across runs.
evidence: `tests/e2e/test_server.py:311-332` deletes `ItemPhotoAssociation`, `Photo`, `InventoryItem` and `MaterialTaxonomy` only; every product an e2e test creates survives into every later test and every later run against the same container. Story 3.1's new `tests/e2e/test_category_autocomplete.py` had to work around it with per-invocation UUID path prefixes and positive-only assertions, and any future product-facing e2e test will need the same workaround (or will be flaky under `--reruns=3`, which replays a test whose product already landed). The fix is a FK-ordered delete of the four catalog tables in `clear_test_data`, which is a change to shared e2e infrastructure and so was left out of a story that only consumed it.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-e2e-test-infrastructure-hygiene

### DW-39: `encode_internal_payload` reports a configured-grammar fault as `ValidationError(field='internal_id', ...)`, blaming user data for an operator's config error
origin: migrated from legacy ledger ("Deferred from: code review of 1-3-product-create-edit-detail (2026-07-23)"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/2-5-foreign-payload-rejection-and-ownership-text.md`
location: `app/mariadb_catalog_service.py:738-743` (`encode_internal_payload`)
reason: `encode_internal_payload` reports a *configured-grammar* fault as `ValidationError(field='internal_id', value=<the perfectly valid id>)`, so structured error fields blame user data for an operator's config error.
evidence: `app/mariadb_catalog_service.py:738-743` catches every `gs1.InvalidGs1PayloadError` and re-raises it with `field='internal_id', value=str(internal_id)`. Verified: with `GS1_INTERNAL_AI='4311'`, `encode_internal_payload('ABC1234567')` raises `ValidationError(field='internal_id', value='ABC1234567')`. The message text is accurate, but `field`/`value` exist precisely so UI and logs can key on them, and they point at valid data. The wrapper is Story 2.4's and the mis-attribution already applied to a blank or padded `GS1_INTERNAL_AI`; Story 2.5 adds two further grammar faults (the 43xx refusal, the token-room rule) that flow through the same path, which is how it surfaced. Fix is to classify the pure error's source and attribute grammar faults to the config key.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-gs1-grammar-configurability

### DW-40: The database-backed autocomplete dropdown carries no ARIA semantics on any of its six fields
origin: migrated from legacy ledger ("Deferred from: code review of 1-3-product-create-edit-detail (2026-07-23)"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-1-materialized-path-categories-with-inline-create.md`
location: `app/static/js/field-autocomplete.js`, `app/templates/inventory/add.html`
reason: The database-backed autocomplete dropdown — now on six fields, including the create affordance — carries no ARIA semantics, so a screen-reader user gets no announcement that suggestions appeared, no way to tell a real suggestion from the `+ Create` entry, and no exposure of the arrow-key selection.
evidence: `app/static/js/field-autocomplete.js` renders the dropdown as a plain `<div>` of `<a class="dropdown-item">` elements with no `role="listbox"`/`role="option"`, no `aria-expanded`/`aria-controls`/`aria-activedescendant` on the input, and no live region; `highlight()` conveys the active entry with a CSS class alone. Story 3.1's create entry is distinguished only by the literal text `+ Create "…"` and a `fw-semibold` class, neither of which is a semantic. The gap is identical for the five pre-existing item fields (`thread_size`, `purchase_location`, `vendor`, `location`, `sub_location`) — Story 3.1 copied the established markup from `app/templates/inventory/add.html` rather than introducing it — so a fix is a change to shared autocomplete markup and behavior affecting every form that uses it, plus the four `style="max-height: 200px; …"` inline duplicates that would be better as one class. Out of scope for a story constrained to extend the component in place without altering the five existing instances (NFR9).
status: done 2026-07-27
resolution: resolved by sweep bundle dw-autocomplete-aria-semantics

### DW-41: `docs/user-manual.md` has no Products/Catalog chapter, so operator-facing catalog behavior is documented only inside the REST API reference
origin: migrated from legacy ledger ("Deferred from: code review of 1-3-product-create-edit-detail (2026-07-23)"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-1-materialized-path-categories-with-inline-create.md`
location: `docs/user-manual.md`
reason: `docs/user-manual.md` has no Products/Catalog chapter at all, so every operator-facing catalog behavior — including Story 3.1's silent canonicalization of a typed category — is documented only inside the REST API reference.
evidence: The manual's chapters run Getting Started, Adding New Inventory, Label Printing, Managing Existing Inventory, Advanced Search, Batch Operations, Data Export — none covers products, which Story 1.3 shipped with add/edit/detail pages. Story 3.1 therefore had nowhere operator-facing to say that typing `Electronics/Power/` stores and redisplays `electronics/power`, or that `+ Create "…"` files a product under a new path rather than creating anything; it documented the `normalized` response key under `GET /api/inventory/field-suggestions/<field>` instead, and the "Form Features" bullet at line 89 still lists only the five item fields because it sits in the Add Item chapter. The gap predates this story (it is Epic 1's), and closing it means authoring a Products chapter — a documentation unit larger than any one story in Epic 3 should bolt on.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-products-user-manual-chapter

### DW-42: LIKE-wildcard escaping has two independent implementations in `app/mariadb_catalog_service.py` that agree today and are free to drift
origin: migrated from legacy ledger ("3-2-category-rename-with-descendants.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-2-category-rename-with-descendants.md`
location: `app/utils/category.py` (`descendant_like_pattern`), `app/mariadb_catalog_service.py:446-451` (`_escape_like` inside `get_field_value_suggestions`)
reason: LIKE-wildcard escaping now has two independent implementations in `app/mariadb_catalog_service.py` — the util's `descendant_like_pattern` and the nested `_escape_like` inside `get_field_value_suggestions` — which agree today and are free to drift.
evidence: `app/utils/category.py`'s `descendant_like_pattern` escapes `\`, `%` and `_` against `CATEGORY_LIKE_ESCAPE_CHAR`, while `get_field_value_suggestions`' local `_escape_like` (`app/mariadb_catalog_service.py:446-451`) performs the identical three replacements against a hardcoded `'\\'`, and both feed `.like(..., escape=...)` in the same class. Story 3.2's stated goal was exactly one implementation of path/prefix logic; the escaping half stayed duplicated only because the story's own "Never" list forbids changing `get_field_value_suggestions` (a Story 3.1 surface with a byte-identical-response contract). Closing it means exporting the literal-escaper from the pure util and rewiring the Story 3.1 caller onto it, re-verifying that the five inventory suggestion fields' responses are unchanged.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-suggestion-query-and-like-escaping

### DW-43: Form routes audit-log `request.form.to_dict()` verbatim, so every POST's CSRF token is written into the audit log
origin: migrated from legacy ledger ("3-2-category-rename-with-descendants.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-2-category-rename-with-descendants.md`
location: `app/main/routes.py:792` (`product_add`) and `category_rename`, `app/logging_config.py:255-289` (`log_audit_operation`)
reason: Form routes audit-log `request.form.to_dict()` verbatim, so the CSRF token of every POST is written into the audit log; `log_audit_operation` performs no redaction.
evidence: `app/main/routes.py`'s `product_add` (:792) and the new `category_rename` both call `log_audit_operation(..., 'input', form_data=request.form.to_dict())`, and the form templates carry `<input type="hidden" name="csrf_token" ...>`, so the token lands in `form_data`. `log_audit_operation` (`app/logging_config.py:255-289`) writes `form_data` straight through with no field filtering. Story 3.2 propagated the existing pattern rather than diverging from it in one route; the fix belongs at the logging helper (a redaction list covering `csrf_token` and any future secret-ish field) so every current and future caller is covered at once.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-csrf-token-handling

### DW-44: No test at any level exercises a form's CSRF token, so a deleted or misspelled `csrf_token` input leaves the suite green while every real POST 400s
origin: migrated from legacy ledger ("3-2-category-rename-with-descendants.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-2-category-rename-with-descendants.md`
location: `config.py` (`TestConfig.WTF_CSRF_ENABLED`), `tests/test_config.py:18`, `tests/unit/test_product_routes.py::TestCategoryPages`
reason: No test at any level exercises a form's CSRF token, so deleting or misspelling a `csrf_token` hidden input leaves the whole suite green while every real POST 400s.
evidence: `config.py`'s `TestConfig` sets `WTF_CSRF_ENABLED = False` (asserted by `tests/test_config.py:18`), and the e2e session runs against the same config, so unit POSTs and Playwright submissions alike succeed with the token present, absent or wrong. Every assertion in `tests/unit/test_product_routes.py::TestCategoryPages` about the rename POST passes identically whether `app/templates/product/category_rename.html`'s `<input type="hidden" name="csrf_token" ...>` exists or not — and the same holds for `product/add.html`, `product/edit.html`, `admin/add_material.html` and every other form template. Story 3.2 surfaced it by adding the project's newest POST form; closing it means a small CSRF-enabled app fixture (a second `create_app` config) plus one test per form template asserting a tokenless POST is refused, which is shared test-infrastructure work rather than one story's.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-csrf-token-handling

### DW-45: The `Examples:` blocks in `app/utils/category.py`'s docstrings are never executed
origin: migrated from legacy ledger ("3-2-category-rename-with-descendants.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-2-category-rename-with-descendants.md`
location: `app/utils/category.py`, `pytest.ini` (`addopts`)
reason: The `Examples:` blocks in `app/utils/category.py`'s docstrings are never executed, so the module positioned as the single source of truth for category-path logic documents behavior nothing verifies.
evidence: `pytest.ini`'s `addopts` does not include `--doctest-modules` and no nox session enables it, so the `>>>` examples in `normalize_category_path` (Story 3.1) and in Story 3.2's `is_descendant_path`, `descendant_like_pattern`, `rewrite_category_path` and `ancestor_paths` are prose. Only one is pinned by hand (`test_the_matrix_pattern_is_22_characters`); changing `CATEGORY_LIKE_ESCAPE_CHAR` or `CATEGORY_PATH_SEPARATOR` would leave the rest asserting behavior the module no longer has — and AD-4 makes these docstrings the contract Epic 8's faceting is meant to build on. The gap predates Story 3.2 (Story 3.1 established the convention) and closing it is a repo-wide test-configuration decision: enabling `--doctest-modules` collects every module in the tree, so it needs a scoped session or a per-module opt-in rather than one story's addopts change.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-pure-util-doctest-session

### DW-46: Catalog vocabulary listings and the tag filter result page fetch and render without any bound
origin: migrated from legacy ledger ("3-3-free-form-tags.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-3-free-form-tags.md`
location: `app/mariadb_catalog_service.py` (`list_tags`, `find_products_by_tag`, `list_category_paths`), `app/templates/product/tag_products.html`
reason: Both catalog vocabulary listings and the tag filter result page fetch and render without any bound — `list_tags()` pulls every `product_tags` row into Python, `list_category_paths()` every non-blank `products.category_path`, and `find_products_by_tag()` every match.
evidence: `CatalogService.list_tags` and `find_products_by_tag` (Story 3.3) carry no `.limit()`, and `app/templates/product/tag_products.html` renders every returned product with no paging; `list_category_paths` (Story 3.2) has the identical shape. The Python-side grouping is well justified — MariaDB's case-insensitive PAD SPACE collation would fold distinct stored values into one row — but the *unbounded fetch* is a separate choice, and `product_tags` can hold up to `MAX_TAGS_PER_PRODUCT` (50) rows per product, so it may grow far larger than `products`. `/products/tags` and `/products/categories` are both reachable from the navbar on every page. Fixing it well means one decision about paging across all three surfaces (and Epic 8's faceted views will want the same mechanism), which is why Story 3.3 followed the shipped Story 3.2 precedent rather than diverging on its own.
status: open

### DW-47: The app configures no `MAX_CONTENT_LENGTH`, so every form POST is bounded only by the WSGI server default and per-field guards
origin: migrated from legacy ledger ("3-3-free-form-tags.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-3-free-form-tags.md`
location: `config.py`
reason: The app configures no `MAX_CONTENT_LENGTH`, so every form POST is bounded only by the WSGI server's own default and each handler's per-field guards.
evidence: `grep -rn "MAX_CONTENT_LENGTH" config.py app/` returns nothing. Story 3.3 surfaced it because the tag field deliberately carries no `maxlength` (it holds a list, not a value) and so needed its own pre-split ceiling in `parse_tag_list` — a guard that exists per-field precisely because no request-level one does. The same gap applies to `notes` (a `Text` column with no length check in `_validate_product_form`) and to the attachment upload path, whose `ATTACHMENT_MAX_SIZE` check runs only after Werkzeug has already buffered the whole body. One `MAX_CONTENT_LENGTH` in `config.py` covers every current and future handler at once, which is app-scope work rather than one story's.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-request-body-size-limit

### DW-48: `/products/tags` shows counts next to an Actions column offering nothing but "View products", so a typo'd tag can only be corrected product by product
origin: migrated from legacy ledger ("3-3-free-form-tags.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-3-free-form-tags.md`
location: `app/templates/product/tags.html`
reason: `/products/tags` shows each tag with a product count next to an Actions column offering nothing but "View products", so a typo'd tag can only be corrected by editing every carrying product one form at a time.
evidence: Story 3.3's Never list explicitly excludes tag rename, merge and delete, so `app/templates/product/tags.html` ships the count and the link and no mutation. The asymmetry with the category half of the same epic is the point: Story 3.2 gave `/products/categories` a rename that carries descendants atomically, and the tag page now sits beside it in the same navbar dropdown showing a count it cannot act on. A tag rename/merge is materially simpler than the category one (no descendants, no path rewriting — an `UPDATE product_tags SET tag=` plus the same collision decision `rename_category_path` already makes), and the page that knows the counts is where it belongs.
status: done 2026-07-28
resolution: resolved by sweep bundle dw-decision-dw-48
decision: 2026-07-26 Build tag rename and merge — Add rename (and merge-on-collision, following `rename_category_path`'s existing collision decision) to `/products/tags`, with a service method on `CatalogService` mirroring the category one, the same audit logging, and coverage for the folding-collation cases `set_product_tags` already handles. Leave delete out unless it falls out for free - removing a tag from every product is a destructive bulk operation that wants its own confirmation.

### DW-49: `get_field_value_suggestions` applies `DISTINCT` in SQL, so under MariaDB's folding collation one of two distinct stored values is never offered
origin: migrated from legacy ledger ("3-3-free-form-tags.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-3-free-form-tags.md`
location: `app/mariadb_catalog_service.py` (`get_field_value_suggestions` query)
reason: `get_field_value_suggestions` applies `DISTINCT` in SQL, so under MariaDB's folding collation two distinct stored values (`café`/`cafe`, and any case variant predating Story 3.1's data migration) collapse to one row and one spelling is never offered — the exact hazard the Python-side dedup pass below it was written to survive.
evidence: `app/mariadb_catalog_service.py`'s suggestion query ends `base.distinct().limit(fetch_limit).all()`, and its own comment states "the DB DISTINCT depends on the column's collation, so two values differing only in case may both reach Python" — which is the harmless direction. The harmful one is not handled: when the collation *does* fold them, the row is gone before Python sees it, and the over-fetch cannot restore it. This predates Story 3.3 (it has applied to all five inventory fields and to `category_path` since Story 3.1) and Story 3.3 only registered one more field against it. The fix is the same "SQL narrows, Python decides" move `list_category_paths` and `list_tags` already make — drop `.distinct()` and let the existing dedup pass do the work — but it changes suggestion behavior for six shipped fields at once, so it is a deliberate cross-field change rather than one story's.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-suggestion-query-and-like-escaping

### DW-50: No test at any level runs `CatalogService` against MariaDB, so every collation-dependent mechanism is verified only by staging the failure under SQLite
origin: migrated from legacy ledger ("3-3-free-form-tags.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-3-free-form-tags.md`
location: `tests/` (no `tests/integration/`), `pytest.ini` (`integration` marker), `mariadb_testcontainer` fixture
reason: No test at any level runs `CatalogService` against MariaDB, so every collation-dependent mechanism in the catalog service is verified only by staging the failure under SQLite — if the deployed collation does not behave as assumed, the mechanisms are elaborate no-ops and nothing would notice.
evidence: `pytest.ini` registers an `integration` marker "using MariaDB test database" and `testcontainers[mysql]` is a declared dependency, but there is no `tests/integration/` directory and `grep -rn "mariadb_testcontainer" tests/` finds only the fixture definition — nothing consumes it. Meanwhile `set_product_tags`' delete-before-insert flush ordering, its `IntegrityError` classification and both collision messages, `list_tags`' Python grouping, `find_products_by_tag`'s exact-equality re-check and `rename_category_path`'s equivalents (Story 3.2) all exist solely because `utf8mb4_unicode_ci` folds case and accents. Each is unit-tested by monkeypatching a flush to raise, which proves the handling and never the trigger. Closing this means standing up the integration session the marker already promises — shared test infrastructure spanning Stories 3.1-3.3, not one story's work.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-mariadb-integration-test-session

### DW-51: No migration pins a charset or collation on any table or column
origin: migrated from legacy ledger ("3-3-free-form-tags.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-3-free-form-tags.md`
location: `migrations/versions/`
reason: No migration pins a charset or collation on any table or column, so the behavior several catalog code paths are written against is whatever the server default happens to be at deploy time.
evidence: `grep -rln "mysql_charset\|COLLATE" migrations/versions/` matches only a comment in `f8e66632ee42`. `product_tags.tag` (Story 3.3), `products.category_path` (3.1) and the identifier columns therefore inherit the server/database default, while `set_product_tags`' collision handling and `list_tags`' Python grouping assume `utf8mb4_unicode_ci` semantics specifically. A deployment on `utf8mb4_bin` makes those paths dead code; one on `utf8mb4_0900_ai_ci` or a future default changes which values fold. Pinning it is a schema-wide decision (every existing table would want the same treatment, plus a decision about whether to migrate deployed data), which is why Story 3.3 followed the existing no-charset convention.
status: done 2026-07-28
resolution: already resolved: Closed by migration `migrations/versions/a977ca7315df_pin_explicit_charset_and_collation.py`: `:652` issues `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci` for all nine tables (list at `:186-196`) and `:679` pins `products.internal_id` to `utf8mb4_bin`. Mirrored in the ORM at `app/database.py:51-54` (`MYSQL_TABLE_OPTIONS` with `mysql_charset`/`mysql_collate` + `mariadb_*`), appended to every `__table_args__`. The entry's own reproducer no longer holds: `grep -rn 'mysql_charset|COLLATE' migrations/versions/` now matches a977ca7315df's real DDL, not just f8e66632ee42's comment. `product_tags.tag` (`app/database.py:1183`) and `products.category_path` (`:916`) are pinned via the table default the CONVERT rewrote, which is exactly the schema-wide treatment the entry asked for.

### DW-52: The product edit form's validation-error re-render collapses "field absent from the POST" into "field submitted empty"
origin: migrated from legacy ledger ("3-3-free-form-tags.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/3-3-free-form-tags.md`
location: `app/main/routes.py` (`product_edit`, `product_add`), `app/templates/product/edit.html`
reason: The product edit form's validation-error re-render collapses "field absent from the POST" into "field submitted empty", so a non-browser client that re-posts the rendered form clears every optional field it never sent.
evidence: `product_edit` enforces the partial-update rule on the POST (`app/main/routes.py`: only keys present in `form_data` reach `update_product`, and `_form_tags` returns None for an absent `tags` key), but on a validation failure it re-renders `edit.html` with the raw submitted `form_data`, and the template renders `value="{{ form_data.get('<field>', '') }}"`. A client POSTing `description=''` plus nothing else gets back a form whose manufacturer, mpn, category_path, notes and tags inputs are all empty though the product carries values; fixing the description and re-posting that form now sends every key as blank, and each is dutifully cleared with a success flash. The browser never sees it (its inputs are always submitted), which is why no test catches it. This predates Story 3.3 — it has applied to every optional product field since Story 1.3 — and Story 3.3 only added one more field to the same re-render. Closing it means merging the stored values under the submitted ones when re-rendering (in both `product_add`/`product_edit` and the equivalent admin forms), which is a change to the shared form round-trip rather than one field's.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-product-form-add-edit-parity

### DW-53: No endpoint sets a request-body size limit, so an oversized JSON body is buffered and parsed in full before any application-level length check
origin: migrated from legacy ledger ("4-1-wedge-scan-capture.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-1-wedge-scan-capture.md`
location: `config.py`, `app/main/routes.py` (every JSON handler, including `api_scan`)
reason: No endpoint in the app sets a request-body size limit, so an oversized JSON body is buffered and parsed in full before any application-level length check can reject it.
evidence: `grep -rn "MAX_CONTENT_LENGTH" app/ config.py` returns nothing. `POST /api/scan` bounds `raw` at 4096 characters, but only after `request.get_json(silent=True)` has already read and parsed the entire body — the same is true of every other JSON handler in `app/main/routes.py`. The app is unauthenticated and every JSON route is `@csrf.exempt`, so any script on the LAN can force an arbitrarily large parse. Setting `MAX_CONTENT_LENGTH` is an app-wide config decision that must be reconciled with the photo-upload endpoints (which legitimately accept multi-megabyte bodies), so it is not one story's change.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-request-body-size-limit

### DW-54: `showToast` interpolates its message into an HTML string and inserts it with `insertAdjacentHTML`, making every toast an unescaped HTML sink
origin: migrated from legacy ledger ("4-1-wedge-scan-capture.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-1-wedge-scan-capture.md`
location: `app/static/js/main.js:395-403` (`WorkshopInventory.utils.showToast`)
reason: `WorkshopInventory.utils.showToast` interpolates its message into an HTML string and inserts it with `insertAdjacentHTML`, making every toast in the app an unescaped HTML sink.
evidence: `app/static/js/main.js:395-403` builds `<div class="toast-body">${message}</div>` and calls `toastContainer.insertAdjacentHTML('beforeend', toastHTML)`. Every caller across `main.js`, `inventory-search.js`, `inventory-move.js`, `photo-manager.js` and the component scripts passes text straight through, and several pass server-derived or user-derived strings. Story 4.1 escapes at its own call site because NFR9 forbids touching `main.js`, but that is one caller of many; the sink itself should escape (or take a text node) so callers cannot get it wrong. Fixing it means auditing every existing caller that intentionally passes markup, which spans the whole front end.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-toast-html-escaping

### DW-55: Both navbar scan/lookup inputs sit inside `.navbar-collapse`, so below the `lg` breakpoint they are hidden behind the hamburger toggler
origin: migrated from legacy ledger ("4-1-wedge-scan-capture.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-1-wedge-scan-capture.md`
location: `app/templates/base.html` (`#ja-id-lookup`, `#scan-input`)
reason: Both navbar scan/lookup inputs sit inside `.navbar-collapse`, so below Bootstrap's `lg` breakpoint they are hidden behind the hamburger toggler and cannot receive focus without an extra tap.
evidence: `app/templates/base.html` places the `#ja-id-lookup` block and the new `#scan-input` block inside `<div class="collapse navbar-collapse">` under `navbar-expand-lg`. FR35 requires the scan field on any page; on a phone or a narrow tablet with a Bluetooth wedge it is present in the DOM but not visible or focusable until the operator opens the menu. The e2e suite pins a 1280x720 viewport (`tests/conftest.py`) and the screenshot suite runs at 1920, so no test exercises the collapsed state. This is the pre-existing treatment of `#ja-id-lookup` that Story 4.1 matched deliberately; moving either field outside the collapse is a navbar layout decision affecting both.
status: open

### DW-56: `inventory-add.js`'s scan-mode handler is bound to `document` and swallows printable keystrokes for every field on `/inventory/add`
origin: migrated from legacy ledger ("4-1-wedge-scan-capture.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-1-wedge-scan-capture.md`
location: `app/static/js/inventory-add.js:128-146`
reason: `inventory-add.js`'s scan-mode handler is bound to `document` and swallows printable keystrokes for every field on `/inventory/add` while scan mode is active, including the global navbar scan field.
evidence: `app/static/js/inventory-add.js:128-146` registers `document.addEventListener('keydown', ...)`; once `this.scanModeActive` is true it appends any single-character key to its own buffer and calls `e.preventDefault()` regardless of which element has focus. Typing into any input on that page — the new `#scan-input` included — is therefore captured by the add-item barcode buffer instead. This predates Story 4.1 (it already applies to every field on the add form) and correcting it means adding a focus guard to that handler, which is metal-stock scan-path code NFR9 places off limits to this story.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-keydown-handler-focus-guards

### DW-57: A keyboard wedge cannot type ASCII control characters into an HTML text input, so the server's byte-exact GS/RS/EOT preservation path may be unreachable from a real scanner
origin: migrated from legacy ledger ("4-1-wedge-scan-capture.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-1-wedge-scan-capture.md`
location: `app/static/js/scan-capture.js`, `app/main/routes.py` (`api_scan`), `app/utils/ecia.py` (`is_envelope`, `_HEADER`)
see-also: DW-11 item (a) — re-aimed at the first work with the physical Tera HW0009 in hand
reason: A keyboard wedge cannot type ASCII control characters into an HTML text input, so the server's byte-exact GS/RS/EOT preservation path may be unreachable from a real scanner even though Story 4.4's parser depends on it.
evidence: `POST /api/scan` preserves `\x1d`, `\x1e` and `\x04` and is unit-tested for it, and the e2e suite exercises the transport with printable payloads only — browsers do not insert non-printable characters into an `<input type="text">` from keystrokes. If the deployed Tera HW0009 emits an ISO/IEC 15434 format-06 envelope as raw control keystrokes, `#scan-input` will hold the envelope with its separators missing and the server will faithfully echo a payload Story 4.4 cannot parse. Establishing whether this is real requires the physical scanner, and any fix (a `keydown`-level capture buffer, or a scanner-side change) is excluded by Story 4.1's stated boundaries. Story 4.5's e2e coverage confirms the shape of the gap rather than closing it: `tests/e2e/test_scan_routing.py::test_an_ecia_envelope_prefills_mpn_quantity_and_order_references` has to place the envelope in the field with `page.evaluate` because a keypress cannot type GS.
status: open

### DW-58: `docs/images/screenshots/metadata.json` records only one of the twelve screenshots the generator writes
origin: migrated from legacy ledger ("4-1-wedge-scan-capture.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-1-wedge-scan-capture.md`
location: `docs/images/screenshots/metadata.json`, `tests/e2e/screenshot_config.yaml`
reason: `docs/images/screenshots/metadata.json` records only one of the twelve screenshots the generator writes, so the manifest cannot be used to tell a complete regeneration from a partial one.
evidence: The file lists a single entry (`user-manual/batch_operations_menu.png`) both at baseline `80d5212` and after Story 4.1's regeneration, while `tests/e2e/screenshot_config.yaml` defines 20 capture definitions and `docs/images/screenshots/` holds 12 PNGs — all 12 of which that story's run updated. The manifest is therefore silently truncated by the generator, and `nox -s screenshots_verify` has no complete inventory to check against. This is a pre-existing defect in the screenshot tooling, not in that story's regeneration.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-screenshot-manifest-completeness

### DW-59: The exact set of characters trimmed off a scan lives as a private symbol inside `app/main/routes.py`, with a second copy in the client
origin: migrated from legacy ledger ("4-1-wedge-scan-capture.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-1-wedge-scan-capture.md`
location: `app/main/routes.py` (`_SCAN_TRIM`, `_clean_scan_input`, `MAX_SCAN_LENGTH`), `app/static/js/scan-capture.js` (`ScanCapture.stripOuter`)
see-also: DW-11 item (e) — the rule still needs a home as a pure util
reason: The epic's single most load-bearing invariant — the exact set of characters trimmed off a scan — lives as a private symbol inside a 3,700-line route module, so downstream consumers must either import an underscore-prefixed name from `app/main/routes.py` or restate the rule.
evidence: `_SCAN_TRIM`, `_clean_scan_input` and `MAX_SCAN_LENGTH` are defined in `app/main/routes.py` beside the `/api/scan` handler, and `tests/unit/test_scan_routes.py` already imports the private helper directly. Story 4.4's ISO/IEC 15434 parser is correct only if the trim set never widened, and Story 4.1's own code comments and tests treat that boundary as a contract; a second copy of it in `app/utils/scan_router.py` would be free to drift with nothing comparing the two. Story 4.1's Never list forbids creating or changing anything under `app/utils/**`, so the placement is spec-driven rather than an implementation error — but the natural home is a pure util the route imports. Story 4.1's client carries a third copy: `ScanCapture.stripOuter` mirrors the same four characters in JavaScript, which no test compares against the Python set. Per DW-11, the "Story 4.4's parser is correct only if the trim set never widened" line should now read as a statement about shipped code rather than future work.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-scan-trim-rule-single-home

### DW-60: The scan transport has at-least-once semantics on a client timeout, which is a double-apply risk now that `/api/scan` drives resolution
origin: migrated from legacy ledger ("4-1-wedge-scan-capture.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-1-wedge-scan-capture.md`
location: `app/static/js/scan-capture.js`, `app/main/routes.py` (`api_scan`)
reason: The scan transport has at-least-once semantics on a client timeout — the operator is told the outcome is unknown and invited to rescan — which was harmless against Story 4.1's echo endpoint but becomes a double-apply risk once `/api/scan` has side effects.
evidence: `app/static/js/scan-capture.js` aborts the request after 10s and reports "the server may or may not have received it", because an abort genuinely cannot distinguish a dropped request from a slow response to one the server processed. `POST /api/scan` was idempotent at Story 4.1 (it echoed and touched no database), so a rescan was free. Once resolution lands, a rescan after a timeout can repeat whatever the resolver did. Closing it needs a decision Story 4.1 could not make on its own — a client-generated scan id the endpoint deduplicates on, or an explicit statement that scan resolution is idempotent by construction — and belongs with the story that first gives the endpoint an effect.
status: open

### DW-61: With no field focused, a wedge burst reaches `main.js`'s global shortcut handler, so a payload containing `/` or `?` fires app shortcuts
origin: migrated from legacy ledger ("4-1-wedge-scan-capture.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-1-wedge-scan-capture.md`
location: `app/static/js/main.js:115-148`
reason: With no field focused, a wedge burst is processed by `main.js`'s global shortcut handler, so a payload containing `/` or `?` silently fires app shortcuts instead of being captured — on every page, not just the add form.
evidence: `app/static/js/main.js:115-148` tracks `inInputField` via document-level `focusin`/`focusout` and early-returns only while an input has focus. Nothing focuses `#scan-input` on page load (FR35's Given is that the field has focus, and Story 4.1's intent contract forbids a document-level key handler), so in the default state a burst reaches the shortcut table: `Slash` matches `Focus Search` and moves focus mid-burst, and `Shift+Slash` matches `Help` and opens the keyboard-shortcuts modal. GS1 Digital Link payloads are URLs and contain `/` by construction. This is distinct from the `inventory-add.js` entry, which is one page's scan-mode buffer; this one is the app-wide shortcut handler and applies everywhere. Any fix — auto-focusing the scan field on load, or adding a guard to the shortcut handler — is excluded by Story 4.1's boundaries (`main.js` is off limits under NFR9, and focus-required capture is stated in the intent contract), so it belongs with the story that decides how an operator arms a scan.
status: open

### DW-62: `POST /api/scan` is `@csrf.exempt` on the explicit understanding that it has no side effects
origin: migrated from legacy ledger ("4-1-wedge-scan-capture.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-1-wedge-scan-capture.md`
location: `app/main/routes.py` (`api_scan`)
reason: `POST /api/scan` is `@csrf.exempt` on the explicit understanding that it has no side effects, and later Epic 4 stories were designed to give it side effects behind the same request shape.
evidence: The exemption matches every other JSON route in `app/main/routes.py` and is required by Story 4.1's intent contract, and it was behaviorally correct at that story: the endpoint constructed no service, touched no database and echoed its input (asserted by `test_csrf_exemption_holds_with_protection_actually_enabled` and `test_endpoint_constructs_no_catalog_service`). The seam exists precisely so later stories can add resolution without renegotiating the transport — at which point a cross-site POST would drive whatever the resolver does. Revisiting it means either a token on the scan request (which Story 4.1's Never list ruled out) or a deliberate decision that scan resolution stays safe to trigger cross-site; it belongs with the story that first gives the endpoint an effect, alongside the at-least-once entry.
status: open

### DW-63: No route in the app is rate limited, so `POST /api/scan` can be driven at whatever rate a client chooses
origin: migrated from legacy ledger ("4-1-wedge-scan-capture.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-1-wedge-scan-capture.md`
location: `app/main/routes.py` (`api_scan`), `create_app()`
reason: No route in the app is rate limited, so `POST /api/scan` — unauthenticated, CSRF-exempt and writing a log line per request — can be driven at whatever rate a client chooses.
evidence: `app/main/routes.py`'s `api_scan` logs a `warning` on every rejection and a `debug` on every capture, and no blueprint, extension or WSGI middleware in `create_app()` applies any throttle. Story 4.1 bounded the per-request cost (`_SCAN_LOG_CHARS = 512`, so a `repr` of a control-character-heavy payload can no longer be amplified to several times an already 4096-character body), but not the request *rate*: log volume is still linear in requests, as is the JSON parse the `MAX_CONTENT_LENGTH` entry covers. This is app-wide — the app has no authentication anywhere and every other route shares the exposure — so a per-endpoint fix would be the wrong shape. It matters more for this endpoint than for the rest once the endpoint has side effects behind a CSRF-exempt POST.
status: done 2026-07-26
resolution: closed by human decision: The app is unauthenticated by design on a private workshop network with one operator; a rate limit protects against a threat model the deployment does not have, and the per-request bounds (`_SCAN_LOG_CHARS`, `MAX_SCAN_LENGTH`, and the pending `MAX_CONTENT_LENGTH`) are the proportionate answer.
decision: 2026-07-26 Close - single-user workshop LAN — The app is unauthenticated by design on a private workshop network with one operator; a rate limit protects against a threat model the deployment does not have, and the per-request bounds (`_SCAN_LOG_CHARS`, `MAX_SCAN_LENGTH`, and the pending `MAX_CONTENT_LENGTH`) are the proportionate answer.

### DW-64: `main.js`'s shortcut handler skips its "user is typing" early-return whenever Ctrl/Meta/Alt is held, so a wedge transmitting control chords fires shortcuts with the scan field focused
origin: migrated from legacy ledger ("4-1-wedge-scan-capture.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-1-wedge-scan-capture.md`
location: `app/static/js/main.js:133-136`, `app/static/js/main.js:180-184`
reason: `main.js`'s global shortcut handler skips its own "user is typing in an input" early-return whenever Ctrl, Meta or Alt is held, so a keyboard wedge that transmits control characters as modifier chords can fire app shortcuts while `#scan-input` has focus.
evidence: `app/static/js/main.js:133-136` reads `if (inInputField && !e.ctrlKey && !e.metaKey && !e.altKey) return;`, so any chord passes through to the shortcut table even with focus in a field. `Ctrl`+`Slash` matches `Focus Search` — its own action is guarded by `!inInputField` and does nothing, but the handler then calls `showToast(name)` unconditionally (`main.js:180-184`), putting a spurious "Focus Search" toast on screen mid-burst. `Ctrl`+`Shift`+`Slash` matches `Help`, which is *not* guarded, so `showKeyboardHelp()` opens the modal and takes focus out of the scan field. Keyboard-wedge scanners commonly emit ASCII control characters as Ctrl chords (GS as `Ctrl`+`]`, RS as `Ctrl`+`^`), which is the same transmission question the "a wedge cannot type ASCII control characters into a text input" entry raises from the other side. Distinct from the no-field-focused entry: that one is the default unfocused state, this one bites with the scan field properly focused. Unfixable inside Story 4.1 — the guard belongs in `main.js`, which that story's intent contract held read-only under NFR9 — and pre-existing: it applies to every input in the app, not just the scan field.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-keydown-handler-focus-guards

### DW-65: The classifier's ECIA rule requires the literal `[)>` RS `06` header, but whether a keyboard wedge can deliver RS/GS at all is an open hardware question
origin: migrated from legacy ledger ("4-2-pure-scan-classifier.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-2-pure-scan-classifier.md`
location: `app/utils/ecia.py` (`is_envelope`, `_HEADER`; the symbols moved from `app/utils/scan_router.py`'s `_is_ecia_envelope`/`_ECIA_HEADER` in Story 4.4)
see-also: DW-11 item (b) — re-aimed at the first work with the physical Tera HW0009 and a real distributor label in hand
reason: The classifier's ECIA rule requires the literal `[)>` RS `06` header, but it is an open hardware question whether a keyboard wedge can deliver RS/GS at all — if it cannot, every real DigiKey/Mouser label classifies as `free_text` and the ECIA parser is never reached.
evidence: The recognizer matches `_ECIA_HEADER = '[)>\x1e06'` and then requires GS, RS or end-of-string, which is exactly what ISO/IEC 15434 specifies and what all three of the repo's canonical vectors carry (`tests/unit/test_gs1.py:320`, `tests/unit/test_scan_routes.py:39`). The companion entry — "a keyboard wedge cannot type ASCII control characters into an HTML text input" — says browsers do not insert non-printable characters into `<input type="text">` from keystrokes, so the deployed Tera HW0009 may transmit the envelope as `[)>06P123` with every separator missing. Under this classifier that is `free_text`: the scan still lands somewhere (FR36 rule 4, no dead end), but receiving a distributor package would never pre-fill anything, which is the entire point of Story 4.4. Relaxing the header to tolerate missing separators cannot be decided without the hardware — it would invent tolerance for a transmission form nobody has observed, and would also promote genuinely damaged scans to `ecia`.
status: open

### DW-66: The pure `app/utils/` modules carry doctests that no test session ever executes
origin: migrated from legacy ledger ("4-2-pure-scan-classifier.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-2-pure-scan-classifier.md`
location: `app/utils/scan_router.py`, `app/utils/gs1.py`, `app/utils/gtin.py`, `noxfile.py`
reason: The pure `app/utils/` modules carry doctests that no test session ever executes, so their examples are documentation that can rot silently.
evidence: `app/utils/scan_router.py`, `app/utils/gs1.py` and `app/utils/gtin.py` all carry `>>>` examples in their public docstrings, and no `--doctest-modules` setting exists in `noxfile.py`, `pytest.ini`, `setup.cfg` or `pyproject.toml` (verified). `python -m doctest app/utils/scan_router.py` passes today and is the only statement of the deliberately-illustrative grammar used in `classify`'s examples, but nothing re-runs it. This is pre-existing across the pure-util family rather than introduced by Story 4.2 — which is the argument for closing it once, in the noxfile, rather than per module.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-pure-util-doctest-session

### DW-67: `gs1.decode` absorbs a transmitted GS/RS while `_clean_scan_input` preserves it, so a wedge that prefixes a separator misroutes every distributor envelope to `free_text`
origin: migrated from legacy ledger ("4-2-pure-scan-classifier.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-2-pure-scan-classifier.md`
location: `app/utils/gs1.py` (`decode`), `app/main/routes.py` (`_clean_scan_input`), `app/utils/ecia.py` (`is_envelope`, formerly `scan_router._is_ecia_envelope`)
see-also: DW-11 item (c) — unchanged; absorbing separators in `_clean_scan_input` would be a fourth copy of the trim rule
reason: `gs1.decode` absorbs a transmitted GS/RS while `_clean_scan_input` deliberately preserves it, so a wedge that prefixes a separator routes internal labels correctly and silently misroutes every distributor envelope to `free_text` — and neither the cleaner nor the classifier can close the gap alone.
evidence: Verified on this checkout: `classify('\x1d' + '96WITABC1234567')` is `INTERNAL` while `classify('\x1d[)>\x1e06\x1dP123')` is `FREE_TEXT`. The cause is that `gs1.decode` opens with `raw.strip()` (its FNC1/CR-LF tolerance) and Python counts `\x1c`-`\x1f` as whitespace, whereas `_clean_scan_input` (`app/main/routes.py`) trims exactly `' \t\r\n'` because stripping GS/RS would destroy the envelope it exists to protect. The ECIA recognizer anchors on `startswith(_HEADER)` and judges the scan as it arrived, per Story 4.2's "classify() performs no whitespace handling of its own" boundary. Both possible fixes were barred there: absorbing separators in `classify()` would be a third copy of the trim rule the module refuses to own, and `app/main/routes.py` was on that story's Never list. The review pinned the behavior (`TestWhitespaceAsymmetryBetweenRules.test_the_asymmetry_extends_to_the_separators_the_cleaner_preserves`) and documented it in the module contract, so it is visible rather than silent — but deciding whether a leading separator must be absorbed, and by whom, needs the physical wedge. Distinct from the entry about *missing* separators inside the header: this one is about an *extra* leading one, and about the rule-1/rule-2 asymmetry that makes it invisible in testing.
status: open

### DW-68: `strip_aim_prefix` recognizes only `']' + letter + digit`, so a scan behind an alphanumeric-modifier AIM prefix classifies as `free_text`
origin: migrated from legacy ledger ("4-2-pure-scan-classifier.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-2-pure-scan-classifier.md`
location: `app/utils/scan_router.py` (`_AIM_PREFIX_RE`, `strip_aim_prefix`)
reason: `strip_aim_prefix` recognizes only `']' + letter + digit`, but ISO/IEC 15424 allows alphanumeric modifier characters for some symbologies (Aztec Code uses `]zA`-`]zC`), so a scan behind such a prefix classifies as `free_text`.
evidence: Verified: `classify(']zA96WITABC1234567', ai='96', token='WIT')` returns `FREE_TEXT`. `_AIM_PREFIX_RE = re.compile(r'\][A-Za-z][0-9]')` in `app/utils/scan_router.py` matches Story 4.2's intent contract verbatim — "an AIM symbology identifier (`]` + one ASCII letter + one digit)" — so this is a defect in the frozen contract, not a deviation from it, and widening the shape would silently diverge from the spec the downstream stories are written against. It also cuts both ways: widening the modifier class to alphanumeric makes the prefix greedier, so a payload legitimately opening `']Ab'` would lose three characters. Low consequence today — the deployed Tera HW0009 emits no AIM identifier at all, so this path is tolerance rather than grammar — but `strip_aim_prefix` is the exported single implementation Stories 4.3 and 4.4 call, so the shape decision propagates. Changing the contract line is a human decision.
status: done 2026-07-26
resolution: closed by human decision: The narrow shape is the safer of the two: it can only fail to strip a prefix nobody's hardware emits, whereas the wide shape can eat three characters of a real payload. The behavior is spec-conformant and now documented; close it rather than widening a frozen contract line for a symbology this shop does not use.
decision: 2026-07-26 Keep the contract, record the limit — The narrow shape is the safer of the two: it can only fail to strip a prefix nobody's hardware emits, whereas the wide shape can eat three characters of a real payload. The behavior is spec-conformant and now documented; close it rather than widening a frozen contract line for a symbology this shop does not use.

### DW-69: An all-zero digit run — the classic wedge no-read output — passes the mod-10 check and classifies as a `gtin`
origin: migrated from legacy ledger ("4-2-pure-scan-classifier.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-2-pure-scan-classifier.md`
location: `app/utils/gtin.py` (`is_valid_gtin`, `normalize_gtin`), `app/utils/scan_router.py` (rule 3)
reason: An all-zero digit run — the classic keyboard-wedge no-read output — passes the mod-10 check and classifies as a `gtin` with normalized key `00000000000000`, indistinguishable from a real scan.
evidence: Verified: `classify('00000000')` and `classify('00000000000000')` both return `kind=GTIN, normalized_value='00000000000000'`, because zero is a valid check digit over all zeros. `'00000000'` is one of the more plausible real faults on this hardware, and under Story 4.3 it drives a product lookup, misses, and lands the operator on a create form pre-filled with a meaningless GTIN. The fix does not belong in `app/utils/scan_router.py`: rule 3 delegates validity entirely to `gtin.is_valid_gtin`/`normalize_gtin` under AD-16, and adding a zero-run check there would be a second copy of GTIN validity the rule exists to prevent. `app/utils/gtin.py` is the right home and is a frozen Epic 2 contract Story 4.2 held read-only ("Satisfying FR36 would require changing `app/utils/gtin.py` ... that is a human decision"). Neither the I/O matrix nor any test covers it in either direction, so the current behavior is accidental rather than chosen.
status: done 2026-07-28
resolution: resolved by sweep bundle dw-decision-dw-69
decision: 2026-07-26 Refuse all-zero runs in `gtin.py` — Make `is_valid_gtin` refuse an all-zero digit run (and have `normalize_gtin` follow it), so a wedge no-read classifies as `free_text` rather than as a trade item number. Note that this also affects the write path - an all-zero GTIN can no longer be stored as a validated identifier - which is the intended consequence. Pin it in the classifier I/O matrix in both directions: `'00000000'` must not be `gtin`, and a genuine GTIN with a zero check digit must still be.

### DW-70: A GS1 element string carrying AI `01` classifies as `free_text`, because FR36 rule 3 recognizes only a bare all-digit trade item number
origin: migrated from legacy ledger ("4-2-pure-scan-classifier.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-2-pure-scan-classifier.md`
location: `app/utils/scan_router.py` (`classify`), `app/utils/gs1.py` (`decode`)
reason: A GS1 element string carrying AI `01` — the standard machine-readable encoding of a GTIN on manufacturer packaging — classifies as `free_text`, because FR36 rule 3 recognizes only a *bare* all-digit trade item number.
evidence: Verified on this checkout: `classify('0109506000134352')`, `classify(']d20109506000134352')` and `classify('\x1d0109506000134352')` all return `kind=free_text, normalized_value=None`, while the bare `'9506000134352'` inside them is a valid EAN-13 that classifies `gtin` with key `'09506000134352'`. This is spec-conformant, not a deviation: FR36's four rules are internal / ECIA envelope / bare GTIN / free text, rule 1 is delegated to `gs1.decode` which returns `None` for any AI but the configured internal one, and Story 4.2's I/O matrix pins `'0109506000134352'` as `free_text` deliberately (`tests/unit/test_scan_router.py` carries it as "an AI-01 element string, not a GTIN"). But FR36's stated purpose is that any barcode in the shop resolves from one wedge scan, and AI-01 in a GS1-128 or GS1 DataMatrix is the most common way a manufacturer encodes a GTIN on a box — so a whole class of real barcode degrades to a text search with no record that it was considered. The fix did not belong in that story: adding a rule between 2 and 3 changes FR36's frozen precedence, which Stories 4.3/4.4/4.5/7/9 are written against, and parsing an AI-01 element string means either extending `gs1.decode`'s foreign-payload handling or re-deriving GS1 element-string parsing in `scan_router` — both barred there. Whether FR36 needs a fifth rule is a requirements decision.
status: done 2026-07-28
resolution: resolved by sweep bundle dw-decision-dw-70
decision: 2026-07-26 Add an AI-01 rule to FR36 — Add a rule between the ECIA envelope and the bare-GTIN rule that recognizes a GS1 element string opening with AI `01`, extracts the 14-digit trade item number, and hands it to the existing `gtin` arm so it resolves exactly as a bare GTIN does. Amend FR36 and the frozen precedence in the affected specs, extend `gs1.decode`'s foreign-payload handling (rather than re-deriving element-string parsing in `scan_router`), and extend the I/O matrix with the AI-01 forms in all three transmission shapes - bare, AIM-prefixed and FNC1-prefixed. Verify no existing rule-1 or rule-3 vector changes classification.

### DW-71: `search_products` silently truncates to the 50 oldest matches with no total and no truncation flag
origin: migrated from legacy ledger ("4-3-service-scan-resolution.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-3-service-scan-resolution.md`
location: `app/mariadb_catalog_service.py` (`search_products`, `SEARCH_RESULTS_DEFAULT_LIMIT`, `resolve_scan`)
reason: `search_products` silently truncates to the 50 *oldest* matches with no total and no truncation flag, so a scan fallthrough cannot tell the operator "showing 50 of 61" and the row cut first is the most recently created product.
evidence: Verified on this checkout: with 61 products matching `'BULK'`, `search_products('BULK')` returns 50 rows and the newest (`'BULK newest arrival'`) is not among them; `resolve_scan` calls it with no `limit`, so the scan path is pinned to `SEARCH_RESULTS_DEFAULT_LIMIT = 50`. Ordering plus a cap is a selection rule, not just a display order, and ascending id selects the least likely rows to be wanted — an operator scanning something they just added is exactly who loses. The bound itself is deliberate and was specced (the sibling listing methods fetch unbounded, which is its own open entry), and the review documented the consequence in the `search_products` docstring rather than leaving it implicit. But a signal cannot be added at that layer: it would have to reach `ScanResolution`, whose three fields — `classification`, `product`, `free_text_hits` — AD-15 freezes for Stories 4.4/4.5 and Epics 7/8/9. Adding a fourth field, or a `SearchResult` wrapper, is an architecture decision, and it should be taken together with Epic 8's paging (AD-17 defers the search mechanism there), not piecemeal in the scan path.
status: open

### DW-72: `search_products`' case-folding is ASCII-only under SQLite, so the two backends disagree about what a search matches
origin: migrated from legacy ledger ("4-3-service-scan-resolution.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-3-service-scan-resolution.md`
location: `app/mariadb_catalog_service.py` (`search_products`)
reason: `search_products`' case-folding is ASCII-only under SQLite, so any product whose text carries an uppercase non-ASCII letter is unreachable by search in the entire unit suite, and SQLite and MariaDB disagree about what a search matches.
evidence: Verified against the real `test_storage` backend: with `description='WÜRTH ELEKTRONIK'` stored, `search_products('ELEKTRONIK')` finds it but `search_products('WÜRTH')`, `'würth'` and `'WÜRTH ELEKTRONIK'` all return `[]`. The cause is that Python's `str.lower()` is full-Unicode while SQLite's built-in `LOWER()` folds ASCII only, so `%würth%` never matches `lower('WÜRTH ELEKTRONIK')` = `'wÜrth elektronik'`. On MariaDB the same query does match, because `LOWER()` there is collation-aware — and `LOWER()` does not change the comparison collation, so `utf8mb4_unicode_ci` additionally makes `cafe` match `café`, which SQLite never will. The review corrected the docstring (which claimed the two backends agree) and pinned the behavior in both directions with `test_non_ascii_folding_is_ascii_only_and_backend_dependent`, so it is visible rather than silent. Fixing it is out of a story's reach: it needs either a custom SQLite collation registered on the engine (an app-level change, and the same engine the per-request-engine entry already concerns) or the Epic 8 mechanism decision AD-17 defers. It compounds the entry that no test at any level runs `CatalogService` against MariaDB — that gap is why this divergence could ship green.
status: open

### DW-73: `resolve_scan`'s internal-id lookup is an exact `==` on `products.internal_id`, whose case semantics differ between SQLite and MariaDB
origin: migrated from legacy ledger ("4-3-service-scan-resolution.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-3-service-scan-resolution.md`
location: `app/mariadb_catalog_service.py` (`resolve_scan`, `find_product_id_by_gtin`), `products.internal_id`
reason: `resolve_scan`'s internal-id lookup is an exact `==` on `products.internal_id`, whose case semantics differ between SQLite (binary) and MariaDB (`_ci`), so the same scan yields a different resolution shape on the two backends.
evidence: Verified: with a generated id `1K8PPAPR8S`, scanning it exactly resolves to the product, while scanning the lowercased form returns `kind=INTERNAL, product=None` and falls through to a free-text search that finds it anyway. Under MariaDB's folding collation the `==` would match and `product` would be set. Both are legal FR36 terminal states, so nothing dead-ends either way, but Story 4.5 renders them differently (a product view versus a search-results list). Reachability is low — internal ids are generated uppercase Crockford base-32 and a wedge does not change case — and the obvious "fix" is worse than the gap: folding the filter with `func.upper()` here would make this lookup disagree with `find_product_id_by_gtin` and with the uniqueness constraint that admitted the row, so it needs a per-column case-semantics decision taken once. That decision is the entry about `product_identifiers` uniqueness being case-sensitive under SQLite and case-insensitive under MariaDB; this is the same defect on `products.internal_id`, and Story 4.3 is its first live consumer rather than its cause.
status: done 2026-07-28
resolution: already resolved: Closed by DW-34's per-column pin rather than by folding the filter, which is the resolution the entry itself named as the only safe one. `app/database.py:903-906`: `internal_id = Column(String(32).with_variant(String(32, collation='utf8mb4_bin'), 'mysql', 'mariadb'), nullable=False)` with the rationale at `:886-902`. `app/mariadb_catalog_service.py:3184-3186` keeps the bare `Product.internal_id == classification.normalized_value`, and the docstring at `:2940-2947` states that the pin makes MariaDB's semantics binary like SQLite's -- 'the divergence DW-73 recorded, closed by pinning rather than by folding the filter.' Guarded by `tests/unit/test_database_schema.py:187::test_internal_id_is_the_only_column_that_overrides_the_table_collation`.

### DW-74: Four pre-existing Story 2.4/2.5 tests hardcode the deployed GS1 grammar, so reconfiguring `GS1_INTERNAL_AI`/`GS1_INTERNAL_TOKEN` is already a red build
origin: migrated from legacy ledger ("4-3-service-scan-resolution.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-3-service-scan-resolution.md`
location: `tests/unit/test_catalog_service.py` (`TestEncodeInternalPayload`, `TestOwnershipLabelText`)
reason: Four pre-existing Story 2.4/2.5 tests hardcode the deployed GS1 grammar, so reconfiguring `GS1_INTERNAL_AI`/`GS1_INTERNAL_TOKEN` — the supported change AD-16 exists to make mechanical — is already a red build, independently of Story 4.3.
evidence: Reproduced by stashing all of Story 4.3's files and re-running at baseline `dd06934` with `GS1_INTERNAL_AI=91 GS1_INTERNAL_TOKEN=ZZ`: the same four tests fail with and without that story's changes. They are `TestEncodeInternalPayload::test_encodes_with_the_configured_grammar`, `::test_token_change_flips_the_payload`, `::test_ai_change_flips_the_payload` and `TestOwnershipLabelText::test_the_two_label_regions_are_disjoint` in `tests/unit/test_catalog_service.py`, all asserting the literal `'\x1d96WITABC1234567'`. AD-16's whole claim is that "one config change flips both encoder and router" mechanically; a suite that goes red on that change contradicts it from the test side, which is precisely the drift `4-2-pure-scan-classifier`'s review pass caught in the classifier's own guard and fixed there. Story 4.3's code and tests are clean under reconfiguration — verified green across AI/token pairs `91/ZZ`, `95/QQ`, `17/AB`, `40/XY`, `01/WT`, and by an exhaustive sweep of all 100 two-digit AIs against every executed string literal in both files. Fixing the four is a change to `tests/unit/test_catalog_service.py`, which was outside that story's four-file scope; the fix is to build the expected element string from `Config` the way `_internal_scan()` in `tests/unit/test_scan_resolution.py` now does.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-gs1-grammar-configurability

### DW-75: `search_products` matches only a contiguous substring of a single column, so the FR36 fallthrough finds nothing for multi-word scans and 50 arbitrary rows for a one-character one
origin: migrated from legacy ledger ("4-3-service-scan-resolution.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-3-service-scan-resolution.md`
location: `app/mariadb_catalog_service.py` (`search_products`)
reason: `search_products` matches only a CONTIGUOUS substring of a single column, so the FR36 fallthrough finds nothing for the multi-word scans it exists to serve, and returns the 50 oldest products for a one- or two-character one.
evidence: Verified against the real `test_storage` backend with a product `description='RES 10K 0805 1%'`, `manufacturer='Yageo'`, `mpn='RC0805FR-0710KL'`: `search_products('RES 10K')` finds it, while `'RES 0805'` (present, in order, not adjacent), `'10K RES'` (reordered) and `'Yageo 10K'` (spread across two columns) all return `[]`. In the other direction `search_products('e')` returns 50 unrelated products, which Story 4.5 renders as scan "hits". The realistic `free_text` scan is a distributor's human-readable line, which is almost never a contiguous substring of any stored field — so FR36's "a miss becomes a search rather than a dead end" holds in type and is usually empty or noise in practice. The mechanism was specced deliberately ("the simplest thing that satisfies the fallthrough") and AD-17 assigns the search mechanism to Epic 8, so this is not a deviation; but nothing recorded what the current mechanism can and cannot reach, and the suite's every positive vector was a contiguous prefix, so the limit was invisible. The review pinned both directions in `test_matching_is_contiguous_substring_only_not_tokenized` and stated it in the `search_products` docstring. Closing it is Epic 8's mechanism decision (tokenization, FULLTEXT, or a minimum query length), not a patch: whitespace-tokenizing the query would change what a search MEANS across the one entrypoint AD-17 froze, and a minimum-length rule is a product decision about what a one-character scan should do.
status: open

### DW-76: A `GTIN_UNVALIDATED` row is reachable by the FR36 fallthrough in only one encoding direction, so the zero-padded form of a short-stored GTIN is a real dead end
origin: migrated from legacy ledger ("4-3-service-scan-resolution.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-3-service-scan-resolution.md`
location: `app/mariadb_catalog_service.py` (`resolve_scan` GTIN miss arm, `search_products`)
reason: A `GTIN_UNVALIDATED` row is reachable by the FR36 fallthrough in only one encoding direction, so scanning the zero-padded form of a GTIN stored in its shorter form is a real dead end — no product AND no hits.
evidence: Verified against the real `test_storage` backend: with `GTIN_UNVALIDATED = '4006381333931'` stored on a product, `resolve_scan('04006381333931')` (the ITF-14 encoding of the same trade item) returns `kind=GTIN, product=None, free_text_hits=()`. The exact arm misses by design (AD-7 puts `GTIN_UNVALIDATED` outside the normalized-14 namespace) and the fallthrough misses because the search is a contiguous substring one and the scanned `'04006381333931'` is not a substring of the stored `'4006381333931'` — the added leading zero is at the front. The reverse direction works, which is why it went unnoticed: the existing `test_gtin_unvalidated_is_outside_the_namespace_but_inside_the_search` scans the short form of a short-stored row, where containment happens to hold. The review pinned both directions in `test_the_unvalidated_fallthrough_bridges_encodings_one_way_only` and corrected two docstrings that claimed unqualified reachability, so the gap is now visible and asserted rather than assumed away. It could not be closed inside Story 4.3: the intent contract fixes the GTIN miss arm's search text as `strip_aim_prefix(raw)`, and the two real fixes are both outside it — normalizing `GTIN_UNVALIDATED` values to the 14-digit form at write time (a Story 2.1/2.2 data decision that changes what the column stores and needs a migration, and which AD-7 arguably forbids since the whole point of the type is "stored as typed, unvalidated"), or Epic 8's search mechanism. It compounds the substring-only entry; that one is about which *text* the mechanism can reach, this one is about a specific identifier type being unreachable in a specific encoding.
status: open

### DW-77: `get_field_value_suggestions` has the same NUL-in-a-LIKE-pattern defect that was fixed in `search_products`
origin: migrated from legacy ledger ("4-3-service-scan-resolution.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-3-service-scan-resolution.md`
location: `app/mariadb_catalog_service.py:475-600` (`get_field_value_suggestions`; pattern built at `:590` and `:597`), `_escape_like_wildcards`, `_is_storable_text`
reason: `get_field_value_suggestions` has the same NUL-in-a-LIKE-pattern defect the Story 4.3 review fixed in `search_products`, and it predates that story — a suggestion query containing `\x00` returns rows that do not match it.
evidence: SQLite reads a LIKE pattern as a C string and stops at the first NUL, so a pattern built as `'%' + escaped + '%'` silently becomes a prefix of itself: measured in `search_products` before the fix, `'\x00'` returned the entire catalog and `'a\x00b'` ran as `'%a'` and returned the rows ending in `a`. `get_field_value_suggestions` (`app/mariadb_catalog_service.py:475-600`, pattern built at `:590` and `:597`) builds its pattern the same way, through the same `_escape_like_wildcards` helper Story 4.3 extracted, and applies no `_is_storable_text` guard — the guard was written for the scan path and only the scan path calls it. Story 4.3 did not cause this (the nested `_escape_like` and the suggestion query both predate `dd06934`; the extraction was behavior-preserving) and did not widen it, which is why it is deferred rather than patched: the suggestion endpoint is a different consumer with a different blank/no-match contract, fixing it means deciding whether unstorable text there should answer `[]` or be rejected, and that decision belongs with whoever owns that endpoint's callers. Reachability is lower than the scan path's — the input is a typed admin form field rather than a wedge — but it is not zero, and the same one-line guard closes it. Note the direction of the divergence, which is what makes this class of defect expensive to find: PyMySQL escapes `\0` in the emitted literal, so MariaDB answers correctly and only SQLite — the sole backend any test here runs — is wrong.
status: done 2026-07-26
resolution: resolved by sweep bundle dw-suggestion-query-and-like-escaping

### DW-78: `resolve_scan`'s ECIA arm counts matches over the union of both candidate part numbers, so a unique `1P` hit is discarded as a false ambiguity
origin: migrated from legacy ledger ("4-4-ecia-distributor-label-parsing.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-4-ecia-distributor-label-parsing.md`
location: `app/mariadb_catalog_service.py` (`resolve_scan`, ECIA arm)
reason: `resolve_scan`'s ECIA arm counts matches over the UNION of the two candidate part numbers, so a unique `1P` hit is discarded as a false ambiguity whenever `P` happens to match a different product.
evidence: Verified against the real SQLite `catalog_service`: with product A `mpn='RC0805-10K'` and product B `mpn='296-1234-ND'`, `resolve_scan` of an envelope carrying `1PRC0805-10K` and `P296-1234-ND` returns `product=None` and `free_text_hits=[A]`. The supplier part number — the field the ECIA spec makes required — matched exactly one product and nothing about that match was ambiguous; the arm sees two rows because both candidates are ORed into one query, and `1P` leading the candidate list gives it no precedence there. The operator still reaches A, as a hit rather than a landing, so this is a degradation and not a wrong answer. It could not be closed inside Story 4.4: the frozen intent contract specifies "one query, one session" over "any candidate" and the fallthrough text as "the first candidate", and the fix is to query per candidate in order and take the first unambiguous answer — two queries in the worst case, and a different contract. Pinned by `test_a_unique_supplier_hit_is_lost_when_the_customer_number_collides` so the behavior cannot change unnoticed, and stated in the `resolve_scan` docstring, but it is one of the two places where an ECIA scan currently resolves to less than the label supports.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-ecia-per-candidate-resolution

### DW-79: Only the first candidate part number is searched on a miss, so a label whose `P` value is the catalog-reachable one dead-ends entirely
origin: migrated from legacy ledger ("4-4-ecia-distributor-label-parsing.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-4-ecia-distributor-label-parsing.md`
location: `app/mariadb_catalog_service.py` (`resolve_scan`, ECIA arm fallthrough)
reason: Only the FIRST candidate part number is searched on a miss, so a distributor label whose `P` value is the catalog-reachable one dead-ends entirely — no product and no hits — while the same label carrying `P` alone resolves.
evidence: Verified: a product described `'reel of 296-1234-ND'` (no `mpn`) is found by `resolve_scan` of an envelope carrying only `P296-1234-ND`, and is NOT found by the same envelope once `1PSUP-99999` is added — `fallthrough_text = candidates[0]` searches `'SUP-99999'`, which matches nothing, and the `P` value is never queried at all. The presence of an extra identifier therefore makes the label resolve to LESS, which is the opposite of FR36's "no scan dead-ends" and is a genuine dead end rather than a thin answer. Same root as the union-ambiguity entry and the same frozen contract line, so the same deferral: closing it means searching every candidate and merging the hit lists (de-duplicated, and with the result bound applied to the merge rather than per query), which changes what `free_text_hits` means for this arm. Pinned in both directions by `test_a_product_reachable_only_by_the_customer_number_dead_ends`.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-ecia-per-candidate-resolution

### DW-80: `_is_storable_text(raw)` judges the whole envelope, so an unstorable character in a record the ECIA arm never queries suppresses a part-number lookup
origin: migrated from legacy ledger ("4-4-ecia-distributor-label-parsing.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-4-ecia-distributor-label-parsing.md`
location: `app/mariadb_catalog_service.py` (`_is_storable_text`, `resolve_scan`)
reason: `_is_storable_text(raw)` judges the WHOLE envelope, so an unstorable character in a record the ECIA arm never queries — a date, an order number — suppresses a part-number lookup that would have resolved.
evidence: Verified: with a product `mpn='RC0805-10K'` stored, `resolve_scan('[)>\x1e06\x1d1PRC0805-10K\x1dK\ud800\x1e\x04')` returns `product=None, free_text_hits=()`, and the same envelope without the lone surrogate in `K` resolves to the product; `K\x00` behaves identically. The guard is Story 4.3's and its reasoning is sound for the arms it was written for ("checking `raw` covers every arm ... any other arm's text is derived from `raw`"), but the ECIA arm is the first whose bound text is a SUBSTRING of `raw` rather than derived from the whole of it, so a hostile character anywhere in the envelope now suppresses a clean lookup. It became reachable only with Story 4.4, since the arm previously issued no query at all. Not patched there because the fix is to move the guard from `raw` to the text each arm actually binds — a change to 4.3's stated contract and to a function three other arms depend on — and because the failure is safe (no wrong answer, no exception, just a miss) and the trigger is a wedge misread that would corrupt the rest of the scan anyway.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-ecia-per-candidate-resolution

### DW-81: Earlier ledger entries cite symbols Story 4.4 deleted and describe 4.4's parser as future work
origin: migrated from legacy ledger ("4-4-ecia-distributor-label-parsing.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-4-ecia-distributor-label-parsing.md`
location: n/a (ledger bookkeeping)
see-also: DW-11, which answers this note and re-aims the named entries past Epic 4
reason: Three earlier ledger entries cite symbols Story 4.4 deleted and describe Story 4.4's parser as future work; they need re-aiming, and the dev-path append-only rule forbade editing them in place.
evidence: The entry about a wedge possibly delivering no RS/GS cited `app/utils/scan_router.py`'s `_is_ecia_envelope` and `_ECIA_HEADER = '[)>\x1e06'` as its evidence, and the entry about an extra LEADING separator cited `_is_ecia_envelope` likewise — both symbols moved to `app/utils/ecia.py` (`is_envelope`, `_HEADER`) in Story 4.4, so both entries pointed at code that no longer exists. The `_SCAN_TRIM` relocation entry still said "Story 4.4's ISO/IEC 15434 parser is correct only if the trim set never widened", written when 4.4 was unbuilt. All three remain substantively OPEN and correct — the hardware questions need the physical Tera HW0009 and a real DigiKey label, and the trim rule still lives beside the route — and all three belong to whoever owns the caller seam. This entry exists so the stale references are recorded rather than silently carried; DW-11 records the re-aiming that answers it.
status: done 2026-07-26
resolution: already resolved: Commit 23aecd3. No ledger entry still cites `app/utils/scan_router.py`'s deleted `_is_ecia_envelope`/`_ECIA_HEADER`, and none still describes Story 4.4's parser as future work: `grep -n see-also deferred-work.md` returns :447, :464, :513, :530, :643, :660, :669, and DW-57/DW-59/DW-65/DW-67/DW-84 all point their `location:` at `app/utils/ecia.py` and carry `see-also: DW-11 item (...)`. The bookkeeping this entry asked for is done; the substantive hardware/trim questions it named remain open as those five entries.

### DW-82: When `1P` matches nothing and `P` matches two products exactly, the ECIA arm discards both exact matches and searches `1P`
origin: migrated from legacy ledger ("4-4-ecia-distributor-label-parsing.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-4-ecia-distributor-label-parsing.md`
location: `app/mariadb_catalog_service.py` (`resolve_scan`, ECIA arm)
reason: When `1P` matches nothing and `P` matches two products EXACTLY, the ECIA arm discards both exact matches as a false ambiguity AND searches `1P`, so the label answers with no product and no hits while the same label carrying `P` alone returns both as hits.
evidence: Verified against the real SQLite `catalog_service`: with two products both `mpn='RC0805-10K'`, `resolve_scan` of an envelope carrying `1PSUP-99999` and `PRC0805-10K` returns `product=None, free_text_hits=()`, and the spy shows the fallthrough searched `'SUP-99999'`; dropping the `1P` record from the same envelope returns both products as hits. This is the composition of the two entries above it and is strictly worse than either: the query FOUND two exact matches on the customer part number and threw them away (the union is ambiguous), and then the fallthrough searched the other candidate, so the arm held the answer in hand and returned nothing. Entry one is a unique hit demoted to a hit-list; entry two is a product reachable only by a substring search of `P`; this is exact matches discarded and never searched. Same frozen contract lines as both — "one query, one session" over "any candidate", "Zero or more than one → no product", "The fallthrough text is the first candidate" — and the same fix closes all three: query per candidate in order and take the first unambiguous answer, at a cost of one more query in the worst case. Pinned by `test_two_exact_matches_are_discarded_while_the_other_candidate_is_searched`, which asserts the control case too, and stated as numbered consequence 3 in the `resolve_scan` docstring.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-ecia-per-candidate-resolution

### DW-83: The ECIA arm trims the value it looks a product up by while `ecia_fields` keeps the value verbatim
origin: migrated from legacy ledger ("4-4-ecia-distributor-label-parsing.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-4-ecia-distributor-label-parsing.md`
location: `app/utils/ecia.py` (`parse_fields`), `app/mariadb_catalog_service.py` (`resolve_scan` ECIA arm, `create_product`, `add_identifier`)
see-also: DW-6 takes the pre-fill half of this decision (trimmed copy); DW-7 carries the durable write-path half
reason: The ECIA arm trims the value it looks a product up by while `ecia_fields` keeps the value verbatim, so a padded label that misses the lookup hands the create form a pre-fill carrying the padding — writing a padded `mpn` into the catalog.
evidence: Both halves are deliberate and correct in isolation. `parse_fields` keeps values exactly as printed because the pre-fill must show what the label carries, and the arm trims because an untrimmed candidate could only ever miss the exact lookup while `search_products` silently strips its own query (both pinned, by `test_the_value_is_kept_verbatim` and `test_a_padded_part_number_still_matches_exactly`). The gap is what happens when the trimmed lookup MISSES: `resolve_scan` matched on `'RC0805-22K'` while `classification.ecia_fields['1P']` is `' RC0805-22K '`, and FR39 says the create form is pre-filled from those fields. An operator who accepts that form creates a product whose `mpn` carries the padding; the next scan of the same label then resolves, but every other path — `search_products`, admin lookups, exports, Epic 10's equivalence matching — carries it. Not closable in Story 4.4: whether the pre-fill shows the printed value or the queried one was Story 4.5's decision about its own form, and normalizing at write time is a Story 1.3 `create_product` question. The one-line version was for 4.5 to pre-fill from a trimmed copy; the durable version is for the write path to strip identifier values the way `add_identifier` already does.
status: done 2026-07-26
resolution: already resolved: `_ecia_prefill` at `app/main/routes.py:1750-1751` builds `fields = {key: (value or '').strip() for key, value in (classification.ecia_fields or {}).items()}` and derives `mpn`/`vendor_sku`/`quantity`/`order_number` from that stripped copy, so a padded label no longer hands the create form a padded pre-fill. Pinned by `tests/unit/test_scan_routes.py:514` (`test_ecia_label_with_no_product_prefills_mpn_quantity_and_order`). The write-path half of the original entry is carried separately and stays open as DW-7 (recorded at deferred-work.md:660).

### DW-84: `ecia.is_envelope` recognizes format 06 only when it is the first format in the message
origin: migrated from legacy ledger ("4-4-ecia-distributor-label-parsing.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-4-ecia-distributor-label-parsing.md`
location: `app/utils/ecia.py` (`is_envelope`, `parse_fields`)
see-also: DW-11 item (d) — re-aimed at the first work with the physical Tera HW0009 and a real distributor label in hand
reason: `ecia.is_envelope` recognizes format 06 only when it is the FIRST format in the message, so a legal multi-format ISO/IEC 15434 label carrying format 06 second degrades to `free_text` and its part numbers are never parsed.
evidence: Verified: `is_envelope('[)>\x1e05\x1dXYZ\x1e06\x1d1PABC\x1e\x04')` is `False`, so `classify()` falls through to rule 4 and the whole label is answered with a raw substring search that contains control characters and matches nothing. ISO/IEC 15434 explicitly allows one message to carry several format sections, and `parse_fields`' own docstring relies on that fact — it truncates at the first RS on the stated grounds that "what follows is a different format" — so the module already anticipates the shape its recognizer rejects. The behavior is not a regression: `is_envelope` was moved verbatim from Story 4.2's `_is_ecia_envelope` and the intent contract froze it as "unchanged in behavior", so this predates 4.4's parser and only became consequential once there was something to parse. Deliberately not patched: the Never list forbids inventing tolerance for transmission forms nobody has observed, and whether any distributor DigiKey/Mouser/Avnet actually emits a multi-format label is exactly the kind of question the open hardware entries need the physical Tera HW0009 and a real label to answer. If it is ever closed, the change is to locate the format-06 section rather than require it at offset zero, and to parse from there — not to relax the header.
status: open

### DW-85: The `product_identifiers` uniqueness constraint's collation lets the unit suite build a data shape production rejects, and the ECIA arm then reports a false ambiguity
origin: migrated from legacy ledger ("4-4-ecia-distributor-label-parsing.md"), 2026-07-26
source_spec: `_bmad-output/implementation-artifacts/4-4-ecia-distributor-label-parsing.md`
location: `uq_product_identifiers_type_value_scope`, `app/mariadb_catalog_service.py` (`add_identifier`, `resolve_scan` ECIA arm)
reason: The `product_identifiers` uniqueness constraint is byte-comparison under SQLite and case/accent-insensitive under MariaDB's `utf8mb4_unicode_ci`, so the unit suite can construct two products holding MPN identifier rows that differ only by case — a data shape production rejects — and the ECIA arm then reports a false ambiguity that cannot occur on the real backend.
evidence: Verified against the real SQLite `catalog_service`: `add_identifier(A, MPN, 'SHARED-1')` followed by `add_identifier(B, MPN, 'shared-1')` is ACCEPTED, and `resolve_scan('[)>\x1e06\x1d1PSHARED-1\x1e\x04')` then returns `product=None` with both products as hits, because the lookup folds case while the unique index did not. Under MariaDB the second `add_identifier` would raise, `uq_product_identifiers_type_value_scope` being over `(identifier_type, value, vendor_scope)` on `utf8mb4_unicode_ci` columns, so that ambiguity is unreachable there. Not caused by Story 4.4 — the divergence lives in the constraint's collation and predates Epic 4, and is the same family as the `search_products` fold divergence already ledgered — but it is newly consequential here, because this is the first seam where a false ambiguity costs a LANDING rather than an extra hit, and because it runs in the direction that makes the test environment stricter than production rather than looser, so a suite that is green proves less than it appears to. It also means `add_identifier`'s own duplicate-rejection contract is backend-dependent and no test at any level runs it against MariaDB. Closing it needs either an integration-level identifier test on the real engine or an explicit collation on the comparison, both of which are Epic 8's mechanism decision rather than one story's.
status: done 2026-07-27
resolution: resolved by sweep bundle dw-mariadb-integration-test-session

### DW-86: The JSON purchase endpoint still coerces `quantity` unbounded, so the DW-25 symptom it was raised for survives on that one column
origin: spec-json-purchase-bounds-parity-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-json-purchase-bounds-parity.md`
location: `app/main/routes.py` (`api_record_purchase`, the `int(quantity)` block)
severity: medium
summary: `POST /api/products/<id>/purchases` parses `quantity` as a bare `int(...)` with no bound, so an over-32-bit value reaches the `INTEGER` column and comes back as the generic 500 naming no field — precisely the failure DW-25 named — while `3.7` is silently stored as `3`, `true` as `1`, and `0`/negative are accepted. The HTML form refuses all of them with a field message.
evidence: Reproduced against the real app by the follow-up review of the json-purchase-bounds-parity bundle: `{"quantity": 100000000000000000000}` answers HTTP 500 `{"code": "server_error", "message": "Failed to record purchase"}` with nothing stored and no field named; `{"quantity": 1099511627776}` answers 201 under SQLite (which widens the column) and cannot be stored under MariaDB, so the unit suite structurally cannot see it — the same backend-invisibility argument `_purchase_unit_price`'s docstring makes for the price column, one screen below it. `{"quantity": 3.7}` -> 201 storing `3`; `{"quantity": true}` -> 201 storing `1`; `{"quantity": "٥"}` -> 201 storing `5`. Deliberately out of that bundle's scope: its intent contract's Never list forbids touching `quantity` on the JSON side because `_positive_int_string` takes a string while the shipped JSON contract takes an int, and mirroring the form's parser would break that contract. That argument rules out reusing the PARSER, not bounding the already-parsed int: `0 < quantity <= _MAX_INT32` on the parsed value breaks no contract and closes the 500. Any change here must keep `{'quantity': 5}` working (`test_record_purchase_endpoint_creates_201`).
status: done 2026-07-28
resolution: resolved by sweep bundle dw-json-purchase-endpoint-hardening

### DW-87: A non-string value for a purchase text column bypasses the length rule and reaches the write path, where a long one is a generic 500 and a boolean becomes the string "1"
origin: spec-json-purchase-bounds-parity-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-json-purchase-bounds-parity.md`
location: `app/main/routes.py` (`_purchase_text_length_error`), `app/mariadb_catalog_service.py` (`_clean`)
severity: medium
summary: `_purchase_text_length_error` applies only to `str` values, so a JSON list, dict or huge int in `vendor`/`vendor_sku`/`order_number`/`source_url` passes the boundary check untouched and fails at the column as the generic 500 naming no field — the DW-25 symptom, on the non-string path. A JSON `true` is accepted and stored as the text `'1'`.
evidence: Reproduced by the follow-up review: `{"vendor": ["a"*300]}`, `{"vendor": {"a": 1}}` and `{"vendor": 10**400}` each answer HTTP 500 `server_error` with nothing stored and no field named; `{"vendor": true}` answers 201 and stores `'1'` in a `String(255)` column. `_clean` (`app/mariadb_catalog_service.py`) also passes non-strings through untouched, so nothing between the boundary and the column looks. Pre-existing and explicitly in scope for NO change in the json-purchase-bounds-parity bundle — its I/O matrix's last row states "Non-string text value `{"vendor": 5}` -> unchanged from today; the length rule does not apply to a non-string" — and the `{"vendor": 5}` case is pinned by `test_a_non_string_value_is_not_the_length_rules_business`. Only that one case was examined; the over-long and boolean cases are uncovered. Closing it means deciding what a non-string means at this boundary (refuse with `invalid_field`, or coerce with `str()` and then bound) — a JSON contract widening/narrowing decision, not a parity one.
status: open

### DW-88: Both purchase entry points promise `YYYY-MM-DD` for the date columns and accept the whole ISO 8601 grammar, so a week-date string records a purchase in the wrong year
origin: spec-json-purchase-bounds-parity-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-json-purchase-bounds-parity.md`
location: `app/main/routes.py` (`_parse_purchase_form` date branch, `api_record_purchase._parse_date`)
severity: medium
summary: Both entry points parse `order_date`/`received_date` with `date.fromisoformat(str(value))`, whose grammar on Python 3.11+ is all of ISO 8601 — not the `YYYY-MM-DD` both refusal messages promise. `"2026-W01-1"` is accepted and stored as `2025-12-29`: a purchase recorded in the wrong year from a string the message says is not accepted. The two messages also still diverge in wording between the entry points.
evidence: Reproduced by the follow-up review on the JSON endpoint: `{"order_date": "2026-W01-1"}` -> 201, stored `2025-12-29`; `{"order_date": "20260101"}` -> 201, stored `2026-01-01`; the JSON *integer* `{"order_date": 20260101}` -> 201, stored `2026-01-01` (via the `str(value)` coercion). Confirmed directly: `date.fromisoformat('2026-W01-1')` is `datetime.date(2025, 12, 29)`. This is the same "the message is not the rule" defect that `_positive_int_string`'s docstring exists to argue against, on the one pair of columns the json-purchase-bounds-parity bundle left with no shared rule — its Never list scoped dates out (DW-24 owns the `received_date >= order_date` question) and its intent contract covers only `unit_price` and the four text columns. The messages themselves diverge today: `'Order Date must be an ISO date (YYYY-MM-DD).'` on the HTML side versus `'order_date must be an ISO date (YYYY-MM-DD)'` on the JSON side — a second message string of exactly the kind the shared helpers removed for the other columns. Closing it means one shared date helper stating the rule it enforces, ideally taken together with DW-24 since both touch the same two fields in the same two functions, and since the shared-helper seam is now built and sitting unused for the dates.
status: done 2026-07-28
resolution: resolved by sweep bundle dw-purchase-date-parse-single-home

### DW-89: `unit_price` accepts PEP 515 underscores and non-ASCII numerals on both entry points, the exact lenience `quantity` refuses one screen away
origin: spec-json-purchase-bounds-parity-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-json-purchase-bounds-parity.md`
location: `app/main/routes.py` (`_purchase_unit_price`)
severity: low
summary: `Decimal(str(raw))` is not the "decimal number" the refusal message promises: `'1_0'` is stored as `10.00` and `'٥'` (Arabic-Indic five) as `5.00`, on both the HTML form and the JSON endpoint. `_positive_int_string`, in the same module, exists solely to refuse those two spellings for `quantity` on the stated grounds that a form promising "a whole number" must not store something the operator did not type.
evidence: Reproduced end-to-end by the follow-up review: `POST /api/products/<id>/purchases {"unit_price": "1_0"}` -> 201 storing `Decimal('10.00')`, and the HTML form (an `<input type="text">`, so the browser imposes nothing) -> 302 storing the same; `'٥'` behaves likewise on both. Confirmed directly: `Decimal('1_0')` is `10`, `Decimal('٥')` is `5`. Pre-existing on both entry points and unchanged by the json-purchase-bounds-parity bundle, whose Always list forbids adding a bound that does not already ship on the HTML side; the two entry points do still AGREE, which is all that bundle claimed. Recorded because extracting `_purchase_unit_price` made the lenience a single shared definition, so both routes are now guaranteed wrong the same way, and because the note now in that helper's docstring points here. Closing it means an explicit spelling rule for the price (ASCII digits, one optional sign, one optional point) applied to BOTH entry points at once, with the HTML messages held unchanged.
status: open

### DW-90: A JSON body that is not an object answers a generic 500 rather than the AD-13 envelope
origin: spec-json-purchase-bounds-parity-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-json-purchase-bounds-parity.md`
location: `app/main/routes.py` (`api_record_purchase`, `request.get_json(silent=True) or {}`)
severity: low
summary: `request.get_json(silent=True) or {}` keeps a JSON array, string or number as-is, and the first `body.get(...)` then raises `AttributeError`, which escapes as the generic 500 shape rather than AD-13's `{success: false, error: {code, message, field}}` with a 400.
evidence: Reproduced by the follow-up review: `client.post('/api/products/<id>/purchases', json=[1, 2])` raises `AttributeError: 'list' object has no attribute 'get'`; in production `app/error_handlers.py` answers it as a generic 500 whose body is not the AD-13 envelope this endpoint otherwise honors. Pre-existing and unchanged in kind — before the json-purchase-bounds-parity bundle the first dereference was `body.get('unit_price')` inside a `try` catching only `(InvalidOperation, ValueError)`, so an `AttributeError` escaped there too; only the line number moved. Closing it is a two-line `isinstance(body, dict)` guard returning `invalid_request` with 400, and the same guard is likely wanted on every AD-13 endpoint that reads a JSON body rather than on this one alone.
status: done 2026-07-28
resolution: resolved by sweep bundle dw-json-purchase-endpoint-hardening

### DW-91: The JSON log formatter emits `request.url` and `user_agent` unbounded on the very record whose message the 413 handler carefully truncates
origin: spec-request-body-size-limit-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-request-body-size-limit.md`
location: `app/logging_config.py` (the JSON formatter's `request` block), consumed by `app/error_handlers.py` `handle_request_too_large`
severity: medium
summary: `handle_request_too_large` bounds `request.path` to 128 chars and CR/LF-escapes it with a visible truncation marker, then the formatter attaches the full untruncated `request.url` and `user_agent` to the same record, so an attacker still turns ~7 KB of chosen text into ~15 KB of log per rejected request.
evidence: Measured on the follow-up review with a 4000-char path and a 3000-char User-Agent against `POST /api/scan`: `message` length 178 (correctly bounded), `request.url` length 4025, `user_agent` length 3000, whole JSON record ~7.6 KB. Pre-existing and app-wide -- the formatter emits those fields for every record on every route, so this is not caused by the 413 handler; the handler merely made the asymmetry visible by bounding its own half. CR/LF forging is genuinely prevented (JSON encoding escapes the structured fields), so only the volume half of the claim fails. A related note about `AuditLogFilter` emitting the full `request.url` was recorded in the pass-7 spec notes; this entry is the ledger record. Closing it means bounding the caller-controlled fields in the formatter itself, which fixes every log line in the app at once rather than one handler's.

### DW-92: Every log record is emitted twice
origin: spec-request-body-size-limit-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-request-body-size-limit.md`
location: `app/logging_config.py` `setup_logging`
severity: low
summary: A single `app.logger.warning(...)` call produces two identical JSON records on the configured stream, doubling log volume for every message the application emits.
evidence: Reproduced directly and minimally: `create_app(TestConfig); app.logger.warning('PLAIN MARKER')` in a fresh interpreter emits the marker record twice. Entirely pre-existing and unrelated to the body-limit work -- it reproduces with no request in flight and with a bare logger call, and the same doubling was visible on the 413 rejection records only because those go through the same logger. The usual cause is a handler installed on both `app.logger` and the root logger with propagation left on. Closing it is a one-line propagation or handler-ownership fix in `setup_logging`, plus a test asserting one record per call.

### DW-93: The forced `parse_form_data=True` promotes Flask's form limits into hard transport limits on routes that never read the form
origin: spec-request-body-size-limit-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-request-body-size-limit.md`
location: `app/request_limits.py` (`enforce_request_body_limit`, `request.get_data(cache=True, parse_form_data=True)`)
severity: low
summary: Because the hook parses form data on every routed request, Flask's untouched 500 KB `MAX_FORM_MEMORY_SIZE` and 1000 `MAX_FORM_PARTS` defaults now reject urlencoded and multipart bodies on routes that never touch `request.form`, so raising `MAX_REQUEST_BODY_BYTES` does not raise the effective limit for those bodies.
evidence: Measured on the follow-up review with `MAX_REQUEST_BODY_BYTES` at 4 MiB and a route that ignores its body: a 600 KB `application/x-www-form-urlencoded` POST is a **413**, while the same 600 KB sent as `application/octet-stream` is a **200**. The forced parse is deliberate and load-bearing -- it is what moves the lazily-raised form-limit 413 out of the views whose `except Exception` used to downgrade it to a 500, and it is pinned in the spec's Boundaries -- so this is a recorded consequence of an accepted design decision, not a defect in its implementation. Both `.env` templates already name `MAX_FORM_MEMORY_SIZE` as the limit governing form bodies, but neither says the reach now extends to routes that never read the form. Closing it means either scoping `parse_form_data` to endpoints that actually consume forms (which reintroduces the per-endpoint bookkeeping the hook exists to avoid) or documenting the widened reach explicitly.

### DW-94: Follow-up review still recommended for dw-request-body-size-limit after the damping cap was spent
origin: review-budget-followup
source_spec: `spec-request-body-size-limit.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260726-064033-76c4; this entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-95: The five inventory suggestion fields bound storability but not length, so an arbitrarily long `q` becomes an arbitrarily long LIKE pattern
origin: spec-suggestion-query-and-like-escaping-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-suggestion-query-and-like-escaping.md`
location: `app/mariadb_inventory_service.py` (`get_field_value_suggestions`), `app/main/routes.py` (`inventory_field_suggestions`, the `q` read)
severity: low
summary: `search_products` treats storability and length as one pair of guards (`SEARCH_QUERY_MAX_LENGTH`, on the stated reasoning that no LIKE pattern can safely carry unbounded text), but the suggestions endpoint received only the storability half, so the five item fields accept a `q` of any size and build a `%…%` pattern from it.
evidence: The route applies only `.strip()` to `q` and passes it through; `get_field_value_suggestions` clamps `limit` and now refuses unstorable text, but never checks length. `escape_like_literal` then doubles every metacharacter, so a multi-KB `q` of `%` becomes a multi-KB pattern matched against every row. The two catalog fields are incidentally covered because `normalize_category_path`/`normalize_tag` reject over-length input and the method answers `[]`, so only the five inventory fields are unbounded. Entirely pre-existing -- the endpoint never had a length bound on either half -- and surfaced by this change only because it made the storability half total and removed the SQL row ceiling (see the unbounded-suggestion-read entry from the same spec), which amplifies the cost. Closing it means one length guard at the same entry point as the storability guard, ideally the same constant the search path already uses.
status: done 2026-07-28
resolution: resolved by sweep bundle dw-suggestion-query-length-bound

### DW-96: The suggestion `ORDER BY` tiebreak is total only under SQLite's binary collation, so which spelling of a case variant is offered stays plan-dependent on MariaDB
origin: spec-suggestion-query-and-like-escaping-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-suggestion-query-and-like-escaping.md`
location: `app/mariadb_catalog_service.py` and `app/mariadb_inventory_service.py` (`get_field_value_suggestions`, `order_by(rank, func.lower(column), column)`)
severity: low
summary: The `column` tiebreak added alongside the DISTINCT removal is meant to stop the query plan from deciding which spelling of a duplicated value the operator is offered, but under MariaDB's folding `_ci` collation the tiebreak column compares case- and accent-insensitively too, so `McMaster` and `mcmaster` tie on both sort keys and the first-seen-casing dedup still keeps whichever the plan emitted first.
evidence: The same collation folding that this change cites as the reason to drop the SQL `DISTINCT` (`utf8mb4_unicode_ci`, reasoned about elsewhere in `mariadb_catalog_service.py` for `set_product_tags` and `rename_category_path`) applies to `ORDER BY` as well. SQLite's BINARY collation makes the tiebreak effective, so the whole unit suite agrees with the code comment and production does not -- the same SQLite-only-correct blind spot the DISTINCT tests' own docstrings identify. The nondeterminism is pre-existing in effect: before this change the folding `DISTINCT` collapsed the variants into one row and the database chose the survivor. The code comments in both services now state the limitation rather than claiming totality. Closing it needs a `COLLATE utf8mb4_bin` tiebreak behind a dialect branch, which the SQLite-only unit suite cannot verify -- the same dialect-branch decision as the collation-safe-dedup option recorded for the unbounded suggestion read.
status: open

### DW-97: The audit redaction choke point covers two of the five logging helpers; `log_operation` and `log_performance` still merge caller dicts unfiltered
origin: spec-csrf-token-handling-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-csrf-token-handling.md`
location: `app/logging_config.py` (`log_operation`, `log_performance`)
severity: low
summary: `_redact_sensitive` is applied to every payload of `log_audit_operation` and `log_audit_batch_operation`, but the sibling helpers `log_operation(details=…)` and `log_performance(context=…)` merge caller-supplied dicts straight into the log record with no field filtering.
evidence: `log_operation` does `extra_data.update(details)` and `log_performance` does `extra_data.update(context)`, both reachable from route code with request-derived dicts. No current caller passes form data, so nothing leaks today, and the code comment at the audit choke point explicitly scopes the guarantee to the audit trail. The asymmetry is the risk: the audit helpers now carry a "no caller has to remember to strip a secret" property that these two do not, which is exactly the shape of the omission that produced DW-43. Closing it means routing both through the same `_redact_sensitive` helper.
status: open

### DW-98: `SECRET_KEY` falls back to a literal committed default, so every CSRF token and signed session is forgeable unless an operator sets the env var
origin: spec-csrf-token-handling-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-csrf-token-handling.md`
location: `config.py:85`
severity: low
summary: `SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'` means a deployment that forgets the env var runs on a key published in this repository, and nothing fails to announce it.
evidence: Entirely pre-existing; surfaced by this story only because it added the tests that prove CSRF enforcement works — enforcement whose whole value rests on the signing key being secret. The same key signs Flask sessions. No test, startup check, or log line distinguishes the fallback from a real key, so the failure is silent in exactly the deployment where it matters. Closing it means refusing to start (or at minimum logging at ERROR) when a non-debug config resolves to the fallback value, which is a config/startup change outside this story's redaction-and-tests scope.
status: open

### DW-99: Redaction is key-based, so a secret embedded in a value — notably `error_details` strings built from `traceback.format_exc()` — passes through untouched
origin: spec-csrf-token-handling-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-csrf-token-handling.md`
location: `app/logging_config.py` (`_redact_sensitive`, `AuditLogFilter`), `app/main/routes.py:3486` and `:3528`
severity: low
summary: `_redact_sensitive` matches field *names*, so a secret that arrives as a value under a benign key is not detectable; the batch-move error paths build `error_details` as an f-string embedding a full `traceback.format_exc()`, which can quote request-derived data.
evidence: `app/main/routes.py:3486` and `:3528` construct `error_details = f'Exception during move: … Traceback: {tb_str}'` and pass it to `log_audit_operation` / `log_audit_batch_operation`; the helper correctly leaves strings alone, and no key in that payload names a secret. `AuditLogFilter` separately attaches `request.url` to every record, the same value channel. Pre-existing and explicitly out of the story's scope (the spec scopes redaction to field names, and the helper's docstring now states the boundary rather than implying totality). Closing it means a value-pattern scan on log strings, which is a different and considerably more failure-prone control than the name denylist and deserves its own decision.
status: open

### DW-100: The denylist collision guard scans DB columns and static template fields, neither of which is what the redaction walk actually receives
origin: spec-csrf-token-handling-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-csrf-token-handling.md`
location: `tests/unit/test_audit_redaction.py` (`TestDenylistDoesNotSwallowRealFields`)
severity: low
summary: The guard enforcing the spec's "Block If" (a denylist substring colliding with a real field name would silently delete audit data) checks `app/database.py` column names and static `<input name=...>` attributes, but the payloads `_redact_sensitive` actually walks are hand-built dicts — `_item_to_audit_dict`, the `changes` map, and `batch_results` — whose keys are neither columns nor form fields.
evidence: `_item_to_audit_dict` (`app/main/routes.py:46-71`) returns literal keys (`dimensions`, `thread`, `original_material`, `precision`, …) and `log_audit_batch_operation` receives `results` dicts assembled in route code; none of those key sets is covered by either scan. Verified there is no collision today — every `_item_to_audit_dict` key is benign against the current denylist — so this is a coverage gap in the guard, not a live defect. A second, narrower gap: the form-field scan captures Jinja-computed names literally (`app/templates/product/search.html:30` yields the string `{{ name }}`), so a dynamically named field is invisible to the collision check by construction. Closing it means enumerating the audit payload key sets — either by importing and exercising the builders or by scanning the dict literals in `app/**/*.py` — which is a fuzzier scan than the two already in place and deserves its own decision about how much fidelity is worth the fragility.
status: open

### DW-101: Follow-up review still recommended for dw-csrf-token-handling after the damping cap was spent
origin: review-budget-followup
source_spec: `spec-csrf-token-handling.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260726-064033-76c4; this entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-102: `pytest.ini` declares `[tool:pytest]`, a `setup.cfg` section name, so pytest reads nothing from it and every setting in the file is inert
origin: spec-pure-util-doctest-session
source_spec: `_bmad-output/implementation-artifacts/spec-pure-util-doctest-session.md`
location: `pytest.ini`, `_bmad-output/project-context.md` (Testing Rules), `noxfile.py`
severity: medium
summary: `pytest.ini` must use a `[pytest]` section; `[tool:pytest]` is only honored inside `setup.cfg`. pytest still reports `configfile: pytest.ini` in its header, so the file looks loaded while `testpaths`, `addopts`, `markers`, `norecursedirs` and `minversion` all do nothing.
evidence: Verified by A/B test in a scratch directory with the project's own pytest 9.1.1: with `[tool:pytest]` the header shows no `testpaths:` line, `--verbose` from `addopts` is not applied, and an unregistered marker produces a `PytestUnknownMarkWarning` instead of the error `--strict-markers` promises; renaming the section to `[pytest]` makes all four take effect immediately. Corroborated in-repo — the new `doctests` session's output was compact dots despite `addopts` declaring `--verbose`. Consequences: `--strict-markers` is not enforced (a typo'd marker in `nox -s tests`'s `-m "not e2e and not integration"` would silently deselect rather than error), `norecursedirs` is not applied (only pytest's built-in defaults keep `venv/` and `migrations/` out), `--disable-warnings`/`--color=yes`/`minversion` are inert, and `testpaths` does not confine a bare `pytest` invocation. `_bmad-output/project-context.md` states `--strict-markers` is on, which is why this went unnoticed. Not caused by this story and deliberately out of its scope: renaming the section activates roughly five settings at once and needs its own verification pass (expect fallout from `--strict-markers` in particular), and every nox session already passes its flags explicitly, so nothing is currently broken by it. Closing it means the rename plus a full `nox -s tests` / `nox -s coverage` / `nox -s e2e` re-run and a `project-context.md` correction.
status: open

### DW-103: Nothing prevents a `>>>` example added outside `app/utils/` from going unexecuted, which is the same class of gap DW-45/DW-66 closed
origin: spec-pure-util-doctest-session
source_spec: `_bmad-output/implementation-artifacts/spec-pure-util-doctest-session.md`
location: `noxfile.py` (`doctests` session), `app/**` outside `app/utils/`
severity: low
summary: The new `doctests` session executes docstring examples under `app/utils/` only. A future `>>>` example in a route, service, or model docstring is unexecuted documentation, exactly as the `app/utils/` examples were before this story, and nothing fails or warns to say so.
evidence: `grep -rn '^\s*>>> ' --include='*.py' app/ manage.py config.py` returns zero matches outside `app/utils/` today, so this is a latent gap rather than a live defect — which is why it is deferred rather than patched. The scoping is deliberate (running `--doctest-modules` tree-wide imports every module, including the Flask/ORM layers, which the story's intent explicitly rules out), so closing this is not "widen the path": it means either a cheap tripwire test that greps for `>>>` outside `app/utils/` and fails with a pointer to this session, or a documented convention that examples belong in the pure-utils layer. `_bmad-output/project-context.md` now states the boundary, which is the minimum mitigation; the tripwire is the open decision.
status: open

### DW-104: `app/utils/sql_text.py` states its LIKE-escaping contract entirely in prose, so the module with the subtlest semantics contributes nothing to the new doctests session
origin: spec-pure-util-doctest-session
source_spec: `_bmad-output/implementation-artifacts/spec-pure-util-doctest-session.md`
location: `app/utils/sql_text.py`
severity: low
summary: The `doctests` session added by this story executes every `>>>` example under `app/utils/`, but `sql_text.py` has zero of them despite documenting exact `%`/`_`/`\` replacement semantics, replacement *ordering*, and non-idempotency in narrative docstrings — the class of contract doctests exist to pin.
evidence: `grep -c '>>>' app/utils/*.py` returns `0` for `sql_text.py` and `__init__.py`; the other eight modules supply all 20 collected items. `escape_like_literal` is a dependency of `app/utils/category.py`'s `descendant_like_pattern` (imported at `category.py:59`) and was last touched by the DW-42/DW-49/DW-77 sweep, so its behavior is both load-bearing and actively changing. Not caused by this story — the module had no examples before it either, and the story's scope was "run the examples that exist", not "write new ones" (its Never list forbids adding directives or deleting examples but says nothing about authoring). Closing it means writing `>>>` examples for `escape_like_literal` covering each metacharacter, the escape character itself, and the documented ordering guarantee; they would then be collected automatically with no `noxfile.py` change.
status: open

### DW-105: `pytest.ini` declares `database` and `screenshot` markers that nothing registers, so fixing DW-102 would turn `nox -s screenshots` red
origin: spec-pure-util-doctest-session
source_spec: `_bmad-output/implementation-artifacts/spec-pure-util-doctest-session.md`
location: `pytest.ini` (`markers`), `tests/conftest.py` (`pytest_configure`), `noxfile.py` (`screenshots`, `screenshots_headless`)
severity: low
summary: Marker registration actually happens in `tests/conftest.py::pytest_configure`, which registers only `unit`, `e2e`, `slow` and `integration`. The `database` and `screenshot` markers listed in `pytest.ini` are registered nowhere, and `pytest.ini` is inert (DW-102), so `--strict-markers` does not currently catch it.
evidence: `tests/conftest.py:203-216` calls `config.addinivalue_line("markers", ...)` exactly four times — `unit`, `e2e`, `slow`, `integration`. `pytest.ini`'s `markers` block lists six, adding `database` and `screenshot`. `noxfile.py:175` and `:213` both run `-m "screenshot"` against `tests/e2e/test_screenshot_generation.py`. Today this is harmless: `pytest.ini` is not read, so `--strict-markers` is not in force and an unregistered marker only warns. It becomes a live failure the moment DW-102 is closed — the section rename simultaneously activates `--strict-markers` and the six-marker list, at which point either the two extra markers must be added to `pytest_configure` or dropped from the ini. Deferred rather than patched because it is a pre-existing inconsistency whose only consequence is coupled to DW-102, and should be resolved in the same pass as that rename.
status: open

### DW-106: README's headline test counts are stale by two orders of magnitude, under a "100% success rates" claim
origin: spec-pure-util-doctest-session
source_spec: `_bmad-output/implementation-artifacts/spec-pure-util-doctest-session.md`
location: `README.md:70-75`
severity: low
summary: The README advertises "Unit Tests: 66/66 passing" and "E2E Tests: 20/20 passing". Actual collection is 2571 non-e2e tests and 367 e2e tests, so both figures are wrong by roughly 40x and 18x, and the surrounding "100% success rates" framing is unverifiable prose.
evidence: `pytest tests/ --collect-only -q` → `2938 tests collected`; `pytest tests/ -m e2e --collect-only -q` → `367/2938 tests collected (2571 deselected)`. Both numbers predate this story and were not introduced by it — the story only appended a `Doctests` bullet to the same list, deliberately without a count, since a hardcoded figure is exactly what rots (the same reasoning that rejected asserting a doctest-count floor in the session). Closing it means either refreshing the three counts and accepting they will rot again, or deleting the counts and the "100% success rates" claim and pointing at the CI badge/summary instead. The second is the better fix and is why this is a decision rather than a one-line patch.
status: done 2026-07-28
resolution: already resolved: `README.md` no longer carries either stale count. `grep -n '66/66\|20/20' README.md` returns nothing; the list now reads `README.md:74` `- **Unit Tests**: SQLite-backed, network-blocked - \`nox -s tests\`` and `README.md:77` `- **E2E Tests**: Playwright against a live server and MariaDB - \`nox -s e2e\``. The counts and the surrounding unverifiable '100% success rates' framing were replaced by the command that produces the real number, which is the second of the two options the entry recommended.

### DW-107: `clear_test_data()` hardcodes its table list, so the next table with an FK into the catalog silently breaks e2e isolation
origin: spec-e2e-test-infrastructure-hygiene
source_spec: `_bmad-output/implementation-artifacts/spec-e2e-test-infrastructure-hygiene.md`
location: `tests/e2e/test_server.py` (`clear_test_data`)
severity: medium
summary: The clear now names nine ORM classes in hand-maintained FK order. `for table in reversed(Base.metadata.sorted_tables): session.execute(table.delete())` derives the same order from the metadata that already knows it, is self-maintaining, and subsumes the hand-written list plus its ordering comment.
evidence: `app/database.py`'s `Product` docstring announces further catalog tables/columns for Epic 5 (stock/quantity/location) and Epic 10 (`equivalent_group_id`). Any new table with a non-nullable FK into one deleted below it makes the `Product` delete raise. This sweep patched the failure mode to be loud (the handler now re-raises rather than swallowing) and added `tests/e2e/test_clear_test_data.py` to pin the current order, so the consequence today is a clear red failure rather than silent staleness — which is why this is deferred rather than patched. Closing it means replacing the nine explicit `session.query(X).delete()` calls with the metadata-driven loop, keeping the `setup_materials_taxonomy()` re-seed afterwards, and confirming `alembic_version` (not in `Base.metadata`) is unaffected.
status: open

### DW-108: Unit tests named "writes nothing" assert only over `products`, so an orphan child row satisfies them
origin: spec-e2e-test-infrastructure-hygiene
source_spec: `_bmad-output/implementation-artifacts/spec-e2e-test-infrastructure-hygiene.md`
location: `tests/unit/test_product_routes.py` (`TestFirstReceiptOnCreate`, `TestDuplicateConfirmation`, `TestPrefillCannotBreakTheForm`, `TestScannedIdentifierTyping`), `tests/unit/conftest.py` (`product_ids`)
severity: low
summary: The `product_ids` fixture this sweep introduced covers `products` only, so a stray `Purchase`, `ProductIdentifier`, `ProductTag` or `Attachment` row still satisfies a test asserting that a rejected POST wrote nothing.
evidence: The assertions these replaced (`get_product(1) is None`, `get_product(existing + 1) is None`) had exactly the same one-table scope, so this is not a regression — the sweep preserved the existing coverage boundary while removing the autoincrement arithmetic, which was its stated intent. It is real rather than theoretical because `tests/unit/test_purchase_model.py:6` records that SQLite runs with `foreign_keys` OFF in this suite, so an orphan child row can genuinely exist. `tests/unit/test_scan_routes.py::test_the_endpoint_writes_nothing` is the one test that already checks purchases and identifiers alongside products, and is the model to follow. Closing it means a `catalog_rows` fixture returning table-name → id-set for all five catalog tables and widening the assertions to it.
status: open

### DW-109: The e2e isolation note is copy-pasted into five modules and has already drifted
origin: spec-e2e-test-infrastructure-hygiene
source_spec: `_bmad-output/implementation-artifacts/spec-e2e-test-infrastructure-hygiene.md`
location: `tests/e2e/test_scan_routing.py`, `test_product_tags.py`, `test_category_autocomplete.py`, `test_category_rename.py` (module docstrings), `tests/e2e/conftest.py` (`unstored_gtin` docstring)
severity: low
summary: The same paragraph explaining e2e catalog isolation exists in five places. Changing what `clear_test_data()` does therefore means editing five files, and this sweep is the bill for that: two of the four rewritten copies contradicted themselves and had to be patched during review.
evidence: The duplication predates this sweep — the pre-fix "clears photos, inventory items and the material taxonomy but NOT `products`" paragraph was already copy-pasted into four modules — and the sweep paid it by copy-pasting again, because rewriting five near-identical paragraphs was in scope while consolidating them was not. The drift is documented: `test_category_autocomplete.py` and `test_category_rename.py` shipped a rationale ("whatever else the shared e2e database holds") that contradicted their own preceding sentence and were corrected in the review pass. Closing it means one canonical note — most naturally in `tests/e2e/conftest.py`, which every e2e module already loads — with one-line pointers replacing the four copies.
status: open

### DW-110: `unstored_gtin`'s 20-attempt loop is now a 200-second stall that names neither the server nor the cause
origin: spec-e2e-test-infrastructure-hygiene
source_spec: `_bmad-output/implementation-artifacts/spec-e2e-test-infrastructure-hygiene.md`
location: `tests/e2e/conftest.py` (`unstored_gtin`)
severity: low
summary: The helper retries up to 20 times with a 10s urllib timeout each, unguarded against `HTTPError`/`URLError` or a non-JSON body. With the catalog now truncated per test it essentially always succeeds on the first iteration, so what the budget buys is a ~200s hang ending in `AssertionError('no unclaimed GTIN found in 20 attempts')` whenever `POST /api/scan` is unhealthy.
evidence: The loop, its timeout and its error handling moved verbatim from `tests/e2e/test_wedge_scan.py` in this sweep — the spec's Always clause required "a move, not a rewrite", so tightening it was explicitly out of scope. It is worth closing because the diagnostic is actively misleading: a 500 from the scan endpoint surfaces as "no unclaimed GTIN found", pointing at the vector rather than at the server. Closing it means a wall-clock deadline instead of an attempt count, an `except urllib.error.URLError` that re-raises as an assertion naming `/api/scan`, and a check that the decoded body is a dict before `.get('outcome')`.
status: open

### DW-111: Story 3.1's implementation artifact still instructs future e2e authors that the catalog accumulates
origin: spec-e2e-test-infrastructure-hygiene
source_spec: `_bmad-output/implementation-artifacts/spec-e2e-test-infrastructure-hygiene.md`
location: `_bmad-output/implementation-artifacts/3-1-materialized-path-categories-with-inline-create.md:201`
severity: low
summary: That line reads "clears photos, inventory items, and the material taxonomy but not `products`, so product rows accumulate across the session. New e2e tests must therefore use a distinctive path prefix and assert containment, never absence." The first sentence is false as of this sweep, and the second is a standing instruction to future authors.
evidence: This sweep's Always clause scoped the documentation fix to docstrings and comments, so the code was updated (`tests/e2e/test_server.py`, four e2e module docstrings, `tests/e2e/conftest.py`) while the prose with the widest blast radius was not. Deferred rather than patched because a completed story's implementation artifact is a historical record of what was true when the story shipped, and silently rewriting one is a different decision from fixing a stale code comment — it needs a call on whether these artifacts are amended in place or annotated. The containment-over-absence guidance itself remains good practice (see DW-109's canonical note) even though its stated justification no longer holds.
status: open

### DW-112: `clear_test_data()` returns silently when its guard is false, so "the clear cannot fail quietly" is only half true
origin: spec-e2e-test-infrastructure-hygiene-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-e2e-test-infrastructure-hygiene.md`
location: `tests/e2e/test_server.py:313` (`clear_test_data`)
severity: low
summary: The whole body sits under `if self.storage and hasattr(self, 'engine'):`. When that guard is false the method deletes nothing, skips the `setup_materials_taxonomy()` re-seed, prints nothing and returns normally — the exact silent-staleness outcome the newly added `raise` was written to rule out, reachable on a path the `raise` never sees.
evidence: The guard predates this sweep, which is why it was deferred rather than patched: the sweep hardened the failure path it touched (`except: rollback; print; raise`) and did not restructure the method. It is real rather than theoretical because `E2ETestServer.stop()` sets `self.storage = None` and `self.engine = None`, and `hasattr(self, 'engine')` stays `True` after an attribute is set to `None` — so the guard admits a half-stopped server straight through to `sessionmaker(bind=None)` while rejecting one whose `storage` was cleared. In practice `live_server` depends on `e2e_server`, which has started the server, so no test reaches it today. Closing it means replacing the guard with `if not (self.storage and getattr(self, 'engine', None)): raise RuntimeError('clear_test_data: server not started, catalog NOT cleared')`, so the no-op is as loud as the failure.
status: open

### DW-113: `setup_materials_data()` swallows a failed taxonomy re-seed, leaving every material-facing e2e test green on an empty vocabulary
origin: spec-e2e-test-infrastructure-hygiene-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-e2e-test-infrastructure-hygiene.md`
location: `tests/e2e/test_server.py:302-309` (`setup_materials_data`, reached via `setup_materials_taxonomy`)
severity: medium
summary: The method ends in `except Exception as e: session.rollback(); print(...); traceback.print_exc()` with no re-raise — the identical defect this sweep classified as medium and patched in its sibling `clear_test_data()`, five lines away and untouched.
evidence: `clear_test_data()` calls `setup_materials_taxonomy()` on every invocation, i.e. before every e2e test, so this is the second half of the same isolation guarantee. The consequence matches the patched case exactly: a failed re-seed rolls back, prints to captured stdout and returns, leaving the taxonomy empty for every subsequent test; the material and category modules assert positively (containment), so nothing goes red and the suite passes green on a missing vocabulary. Deferred rather than patched because the swallow predates this sweep and this diff does not touch the method — the sweep's Always clause scoped it to `clear_test_data()`'s error-handling shape. `tests/e2e/test_clear_test_data.py::test_clear_test_data_still_clears_the_inventory_side_and_reseeds_materials` now asserts `MaterialTaxonomy.count() > 0` after a clear, so one test would notice; the other ~370 would not. Closing it means adding `raise` after the rollback/print, matching `clear_test_data()`.
status: open

### DW-114: Four more implementation artifacts carry the same falsified "the catalog accumulates" instruction that DW-111 tracks in one
origin: spec-e2e-test-infrastructure-hygiene-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-e2e-test-infrastructure-hygiene.md`
location: `_bmad-output/implementation-artifacts/3-2-category-rename-with-descendants.md:33,92`, `_bmad-output/implementation-artifacts/3-3-free-form-tags.md:35,105`
severity: low
summary: DW-111 names only `3-1-materialized-path-categories-with-inline-create.md:201`, but the same standing instruction to future e2e authors appears in two further artifacts — `3-3:35` reads "`clear_test_data()` never truncates `products` and will not truncate `product_tags`", which this sweep falsified on both counts. All four lines additionally cite `tests/e2e/test_server.py:311-332` as the location of `clear_test_data`, a range this sweep's added deletes invalidated.
evidence: Found by adversarial review of this sweep, which read DW-111 and checked whether its scope was complete; `grep -rn "never truncates\|not truncate\|accumulate" _bmad-output/implementation-artifacts/` returns all five lines. Logged as a separate entry rather than folded into DW-111 because the ledger's existing entries are owned by the orchestrator and are not rewritten by a review pass. It carries the same open question DW-111 does — whether a completed story's artifact is amended in place or annotated — and should be closed in the same motion, not before it.
status: open

### DW-115: A `GS1_INTERNAL_TOKEN` of 21-29 characters still surfaces as `ValidationError(field='internal_id', value=<the valid id>)` — DW-39's defect in the data-field-overflow corner
origin: spec-gs1-grammar-configurability-review
source_spec: `_bmad-output/implementation-artifacts/spec-gs1-grammar-configurability.md`
location: `app/utils/gs1.py` (`encode`, the data-field bound) and `app/mariadb_catalog_service.py` (`encode_internal_payload`)
severity: low
summary: DW-39's fix classifies faults at the raise site, and `encode`'s `len(token) + len(internal_id) > MAX_DATA_FIELD_LENGTH` rule is classified `PAYLOAD` — correctly for an overlong id, but the same rule fires when a *configured token* is what consumed the field, and then a perfectly valid service-generated id is reported as the fault.
evidence: Verified: with `GS1_INTERNAL_TOKEN = 'W' * 21`, `encode_internal_payload('ABC1234567')` raises `ValidationError(field='internal_id', value='ABC1234567')`. The flip points are exact — a token of 19-20 characters encodes, 21-29 blames the id, and 30+ is caught by the token-room rule as `ConfigurationError(config_key='GS1_INTERNAL_TOKEN')`. Deferred rather than patched because closing it needs a design call this spec's `Never` list forecloses: the overflow is genuinely joint (a 21-character token encodes a 9-character id and refuses a 10-character one), so attributing it correctly means either widening the token-room rule to reserve room for an id — which requires `gs1.py` to know how long a generated internal id is, a coupling AD-4 deliberately avoids — or splitting the bound into a grammar half and a payload half. Mitigating: internal ids are a fixed 10 characters, so any token past 20 fails every id, and the error message itself names the token; only the structured `field`/`value` mis-point.
status: open

### DW-116: `resolve_scan` still lets a raw `gs1.InvalidGs1PayloadError` reach the request as an anonymous 500, for the identical config fault `encode_internal_payload` now attributes
origin: spec-gs1-grammar-configurability-review
source_spec: `_bmad-output/implementation-artifacts/spec-gs1-grammar-configurability.md`
location: `app/mariadb_catalog_service.py` (`resolve_scan`), `app/error_handlers.py` (`create_error_handlers`)
severity: low
summary: After DW-39, a malformed `GS1_INTERNAL_AI`/`GS1_INTERNAL_TOKEN` produces a `ConfigurationError` carrying `config_key` on the encode path and a bare `ValueError` subclass with no registered error handler on the scan path — and the scan path is the one with a production caller today.
evidence: `resolve_scan` deliberately propagates the pure error unchanged (`4-3-service-scan-resolution.md:76,103`), which is why this was left alone; `app/error_handlers.py` registers handlers for `ValidationError`, `StorageError`, `ItemNotFoundError`, `AuthenticationError` and both `ConfigurationError` classes, but nothing for `gs1.InvalidGs1PayloadError`, so it falls through to the generic 500 with no `error_code`, no `config_key` and no operator-facing hint — while the same misconfiguration reached through `encode_internal_payload` now names the key to change. `encode_internal_payload` has no production consumer until Epic 6's label renderer; `resolve_scan` is reached from the scan endpoint (`app/main/routes.py`). Closing it means deciding where the boundary translation belongs — a `gs1.InvalidGs1PayloadError` handler in `create_error_handlers`, or a translation in `resolve_scan` that Story 4.3 explicitly rejected — which is a call about the scan path's contract, not a patch to this diff.
status: open

### DW-117: The tag and category folding mechanisms DW-50 was opened for still have no MariaDB coverage — only the identifier half was closed
origin: spec-mariadb-integration-test-session-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-mariadb-integration-test-session.md`
location: `tests/integration/` (no tag/category test), `app/mariadb_catalog_service.py` (`set_product_tags`, `list_tags`, `find_products_by_tag`, `rename_category_path`)
severity: medium
summary: The new integration tier exercises `add_identifier` and `create_product` plus a collation guard; every tag- and category-side mechanism DW-50's evidence enumerated as existing "solely because `utf8mb4_unicode_ci` folds case and accents" remains verified only by monkeypatching a flush under SQLite.
evidence: DW-50's evidence names `set_product_tags`' delete-before-insert flush ordering, its `IntegrityError` classification and both collision messages, `list_tags`' Python grouping, `find_products_by_tag`'s exact-equality re-check and `rename_category_path`'s unclaimed-row handling (Story 3.2). `tests/integration/test_identifier_collation.py`'s own module docstring lists three of those as the things that "quietly become elaborate no-ops" if folding stops, and then asserts a collation *guard* rather than any of their behavior — no integration test constructs a tag pair differing only by case, or a category rename whose target already exists under a different casing. The spec that closed DW-50 scoped itself to "the identifier half of DW-50" deliberately (`Tasks & Acceptance`), so this is the remainder rather than a defect in that work: the guard proves the collation folds, but nothing proves these five call sites behave correctly when it does. Closing it is a second file in the existing tier consuming `integration_catalog_service` — no new infrastructure.
status: open

### DW-118: The migration runner never puts rows in front of `f8e66632ee42`, the tree's other data migration, so its folding-collation reasoning is unexercised
origin: spec-mariadb-integration-test-session-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-mariadb-integration-test-session.md`
location: `migrations/versions/f8e66632ee42_normalize_existing_category_paths.py`, `tests/integration/test_migrations.py`
severity: medium
summary: `upgrade head` runs the category-path normalization migration on every integration test, but always against an empty `products` table, so the one data migration whose correctness depends on MariaDB's folding collation is executed and never actually tested.
evidence: `f8e66632ee42` is labelled "DATA ONLY" in its own docstring and issues chunked `UPDATE`s to rewrite non-canonical `category_path` values through `app.utils.category.normalize_category_path`. Its comments reason explicitly about the backend: the value set comes from a `SELECT DISTINCT`, which under a case/accent-folding collation collapses `Electronics/Power` and `electronics/power` into one row — precisely the class of backend-dependent behavior this tier was built to catch, and precisely what SQLite cannot stage. `tests/integration/test_migrations.py` seeds products only at `3beb9dff5e41` for the Story 2.4 backfill (`TestInternalIdBackfill.backfilled`); the two whole-chain tests start from `blank_database` with no rows, so every assertion about this migration is vacuous. The fixture pattern to close it already exists — seed at `5aeb89e22451`, upgrade one revision, assert the collapse — so this is one more class in the file rather than new infrastructure.
status: open

### DW-119: `5aeb89e22451`'s two abort branches, and its claim that aborts are no-ops on the schema, are untested
origin: spec-mariadb-integration-test-session-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-mariadb-integration-test-session.md`
location: `migrations/versions/5aeb89e22451_add_products_internal_id.py` (the validation prologue), `tests/integration/test_migrations.py::TestInternalIdBackfill`
severity: low
summary: The internal-id migration refuses to run when a product carries more than one global `INTERNAL` row, or one whose value fails `is_valid_internal_id`; neither refusal is exercised, and neither is its ordering argument that a refusal leaves the schema untouched.
evidence: The migration hoists both `RuntimeError` checks ahead of all DDL and argues in a comment that this "keeps every reachable abort path a genuine no-op on the schema" — a claim about MySQL's implicit DDL commit that only a real backend can settle, and one an operator with dirty pre-2.4 data depends on to be able to fix the data and retry. `tests/integration/test_migrations.py` names one of the two cases in the `ADOPTED_INTERNAL_ID` comment and dismisses it as "a different test than this one" without adding it, so the tier covers the happy path of the same migration in five tests and its failure path in none. Both are cheap given `TestInternalIdBackfill.backfilled`: seed the offending row at `3beb9dff5e41`, assert `pytest.raises(RuntimeError)` on the upgrade, then assert `internal_id` is still absent from `products`.
status: open

### DW-120: The `e2e-tests` job's wait-for-MariaDB loop still cannot fail, the identical bug fixed in the new `integration-tests` job
origin: spec-mariadb-integration-test-session-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-mariadb-integration-test-session.md`
location: `.github/workflows/test.yml` (`e2e-tests`, the `Wait for MariaDB to be ready` step)
severity: low
summary: The e2e job's retry loop `break`s out on exhaustion with no `exit 1`, so a MariaDB that never comes up produces a green wait step and a confusing downstream failure — the exact defect the new integration job's copy of the same loop was patched to avoid.
evidence: The two steps are otherwise byte-identical `for i in {1..30}` loops around `mysqladmin ping`. The integration job's version, added by this change, ends with an `exit 1` and a comment explaining that without it "the step passes and the failure surfaces later as something unrelated". The e2e version falls through to the `mysql ... SELECT 1` step instead. Not caused by this change — the loop predates it — but it is now the only copy carrying the bug, and the fix is one line plus the same comment. Left alone here because the spec's `Never` list forbids changing e2e behavior.
status: open

### DW-121: `MARIADB_CHARACTER_SET_SERVER` / `MARIADB_COLLATION_SERVER` remain set in two places that this change proved inert, and the e2e tier still runs under an unpinned collation
origin: spec-mariadb-integration-test-session-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-mariadb-integration-test-session.md`
location: `.github/workflows/test.yml:189-190` (`e2e-tests` service container), `tests/test_database.py:48-49` (`mariadb_testcontainer`)
severity: low
summary: The official `mariadb` entrypoint does not interpret those variables, so both settings are decoration a reader trusts; the practical consequence is that the e2e tier runs under MariaDB 11.8's built-in default (`utf8mb4_uca1400_ai_ci`) while believing it runs under `utf8mb4_unicode_ci`.
evidence: Measured during this work on `mariadb:11.8.8`: with both variables set, `collation_server` reports `utf8mb4_uca1400_ai_ci` and the schema inherits it — which is why `tests/integration/conftest.py::integration_db_url` has to issue `ALTER DATABASE ... COLLATE utf8mb4_unicode_ci` itself, and why the new CI job deliberately omits the pair with a comment saying so. The two remaining copies were left in place because the spec forbids changing e2e behavior and `tests/test_database.py`'s fixture is shared with the e2e session. Both collations happen to fold case and accents, so nothing is currently wrong — but the e2e tier's collation is an accident of the image's defaults rather than a property anything asserts, and the misleading config invites the same wrong conclusion again. Related to DW-51 (nothing in the application pins a collation either).
status: open

### DW-122: The Material field's autocomplete dropdown still carries no ARIA semantics, on a required field
origin: spec-autocomplete-aria-semantics
source_spec: `_bmad-output/implementation-artifacts/spec-autocomplete-aria-semantics.md`
location: `app/static/js/material-selector.js`, `app/static/js/inventory-add.js`, `app/templates/inventory/add.html:107`, `app/templates/inventory/edit.html:116`
severity: medium
summary: DW-40 gave the seven `FieldAutocomplete` fields the combobox pattern, but `#material` — a *required* field on both item forms, with its own suggestion dropdown — was explicitly out of scope and remains an anonymous `<div>` of links to a screen reader.
evidence: `#material-suggestions` is driven by `MaterialSelector` (`material-selector.js`, `.suggestion-item` markup with breadcrumb navigation) and by the legacy `inventory-add.js` fallback, not by `field-autocomplete.js`. Neither writes any `role`, `aria-expanded`, `aria-activedescendant`, or live region; `tests/e2e/test_autocomplete_aria.py::test_the_material_dropdown_is_left_alone` now asserts the container has no `role`, which pins the boundary but is not approval of the gap. The fix is not a copy of DW-40's: MaterialSelector's dropdown is a *navigable tree* (breadcrumbs, a back button, a "navigate" affordance per row), so it needs its own pattern rather than a flat listbox. Out of scope for a change constrained to `field-autocomplete.js` and forbidden from touching MaterialSelector.
status: open

### DW-123: Declaring the autocomplete input a `combobox` creates a reopen expectation the keyboard handler does not meet
origin: spec-autocomplete-aria-semantics
source_spec: `_bmad-output/implementation-artifacts/spec-autocomplete-aria-semantics.md`
location: `app/static/js/field-autocomplete.js` (`onKeyDown`)
severity: low
summary: The WAI-ARIA combobox pattern expects ArrowDown (and Alt+ArrowDown) to reopen a dismissed list; `onKeyDown` returns early whenever the dropdown is not visible, so after Escape the only way back is to blur and refocus the field.
evidence: `onKeyDown` handles Escape first and then `if (!visible) return;`, which predates this change — but before it the input made no promise, and it now advertises `role="combobox"` with `aria-expanded`, which is exactly the promise. The fix is not a one-liner: `dismiss()` deliberately cancels the debounced fetch and bumps `requestSeq` so a dropdown cannot reappear over the Save button (the reason `test_escape_dismisses_the_dropdown_for_good` exists), so an ArrowDown reopen has to distinguish an operator asking for the list from a stale fetch delivering it. Out of scope here: the spec forbids changing keyboard behavior.
status: open

### DW-124: `test_batch_move_mixed_sub_locations` is flaky in a full e2e session, and its wedge-scan flow is paced by fixed `wait_for_timeout` sleeps
origin: spec-autocomplete-aria-semantics
source_spec: `_bmad-output/implementation-artifacts/spec-autocomplete-aria-semantics.md`
location: `tests/e2e/test_move_items_sub_location.py` (`TestMoveItemsSubLocation::test_batch_move_mixed_sub_locations`, and the fixed sleeps throughout the file)
severity: low
summary: The batch-move test failed all four attempts (`--reruns=3`) inside a full `nox -s e2e` run with `assert 'M2-B' == 'M11-Y'` — the second queued move silently not applied — yet passes in isolation and passes with its own file run end to end.
evidence: Observed 2026-07-27 in a full session (`1 failed, 384 passed, 1 skipped, 3 rerun`); re-run alone → 1 passed in 42.85s; whole file → 9 passed in 74.18s. Unrelated to the change that surfaced it: `app/templates/inventory/move.html` loads no autocomplete script and has no `-suggestions` container, so nothing in `field-autocomplete.js` executes on that page. The flow drives the wedge-scan input with `barcode_input.press('Enter')` followed by a bare `page.wait_for_timeout(200)` after each of ~10 scans, then asserts on a queue built asynchronously — under a loaded machine one queued entry can be dropped or mis-associated before `#queue-count` is read, and the count assertion (`3 items`) passes anyway because the third scan lands. A retry does not help because `--reruns` replays the same racing sequence. Wants the fixed sleeps replaced with waits on the queue's own state (a per-row locator reaching the expected count/content) rather than elapsed time.
status: open

### DW-125: Five toast call sites pass `type: 'error'`, which is not a Bootstrap variant — the app's error toasts render unstyled with an invisible close button
origin: spec-toast-html-escaping
source_spec: `_bmad-output/implementation-artifacts/spec-toast-html-escaping.md`
location: `app/static/js/main.js` (`WorkshopInventory.utils.showToast`, the `text-bg-${type}` class), callers `app/static/js/inventory-add.js:207,731,735` and `app/templates/inventory/edit.html:957,961`
severity: medium
summary: `showToast` interpolates its `type` argument into `text-bg-${type}`, and Bootstrap 5.3 defines `text-bg-*` only for `primary|secondary|success|danger|warning|info|light|dark` — so the five call sites passing `'error'` produce `text-bg-error`, a class nothing defines, on the toasts that report failures.
evidence: `grep -rn "text-bg-" app/static/css/*.css` returns nothing, so no project rule supplies the missing variant either. The toast therefore renders on the default light background while the close button keeps the unconditional `btn-close-white`, i.e. a white X on a white toast — the dismiss control is effectively invisible on exactly the toasts an operator most wants to dismiss. Pre-existing: the removed HTML-string version interpolated the same value into the same class. DW-54's rewrite touched both lines and deliberately kept `type` interpolated (a class token is not an HTML-parsing context, so it is not an injection question), which is why this is filed rather than fixed: the fix is a caller-side vocabulary decision — map `'error'` to `'danger'` at the five call sites, or normalize inside the sink and drop `btn-close-white` for light variants — and it changes the appearance of live error toasts, which is outside a change scoped to escaping.
status: open

### DW-126: The hand-built toast has no accessible name on its close button and no `aria-live`/`aria-atomic`
origin: spec-toast-html-escaping
source_spec: `_bmad-output/implementation-artifacts/spec-toast-html-escaping.md`
location: `app/static/js/main.js` (`WorkshopInventory.utils.showToast`)
severity: low
summary: The toast's `.btn-close` carries no `aria-label`, so a screen reader announces an unnamed "button", and the toast declares `role="alert"` without the `aria-live="assertive"`/`aria-atomic="true"` pair Bootstrap documents, so a message updated in place can be announced partially.
evidence: The same file gives the keyboard-shortcut modal's close button `aria-label="Close"` (`app/static/js/main.js:71`), so the omission is inconsistent within one file rather than a project-wide stance, and DW-40 (autocomplete ARIA semantics, landed at `e4929dd`) shows the project treats these as real defects. Pre-existing — the removed HTML string had neither attribute — but DW-54 rebuilt this element node by node, which is when it would have been cheapest to add. Left out because the spec's contract was to keep the rendered DOM shape byte-identical so no existing selector or screenshot moved; adding attributes is a deliberate, separately-verifiable a11y change.
status: open

### DW-127: `WorkshopInventory.utils` still holds three unescaped `innerHTML` interpolation sinks — the same defect DW-54 just removed from `showToast`, one object over
origin: spec-toast-html-escaping
source_spec: `_bmad-output/implementation-artifacts/spec-toast-html-escaping.md`
location: `app/static/js/main.js:302` (`utils.showLoading`), `app/static/js/main.js:321` (`utils.showLoadingOverlay`), `app/static/js/main.js:645` (`utils.createRecentItemsDropdown`)
severity: low
summary: Three sibling helpers in the very `utils` object DW-54 hardened still build markup by interpolating a caller-supplied argument or stored item data into `innerHTML` — `showLoading(element, text)`, `showLoadingOverlay(message)`, and the recent-items dropdown, which splices `item.ja_id`, `item.type`, `item.shape` and `item.material` from `localStorage` into `link.innerHTML`.
evidence: `grep -n "innerHTML" app/static/js/main.js` shows `:302` and `:321` interpolating `${text}` / `${message}` and `:645` interpolating four item fields. Severity is low only because all three are currently unreachable: `grep -rn "showLoading(\|showLoadingOverlay(\|createRecentItemsDropdown(" app/` finds no caller of the `utils` versions (`inventory-list.js:280` and `inventory-search.js:172` call their own objects' methods), and `createRecentItemsDropdown` returns early because nothing calls `addToRecentItems`, so `localStorage.recentItems` is never populated. That is exactly what makes it a ledger item rather than a live bug — and exactly what makes it a trap: the recent-items feature is written and waiting to be wired up, and the day someone calls `addToRecentItems(item)` with a server-derived item, `main.js` gets a fresh HTML sink fed by inventory data. Not caused by DW-54 and deliberately out of its scope (the spec's `Never` clause confines the change to the toast sink and leaves the other inline-alert sinks to their own entries); surfaced because reviewing the toast rewrite meant reading the rest of the file. Fix is the same shape that worked for the toast: build the nodes and set text with `textContent`, or delete the dead helpers outright if the recent-items feature is not coming back.
status: open

### DW-128: The Add Item chapter's "Auto-complete" bullet lists five fields, but `field-autocomplete.js` registers seven
origin: spec-products-user-manual-chapter
source_spec: `_bmad-output/implementation-artifacts/spec-products-user-manual-chapter.md`
location: `docs/user-manual.md` line 98-102 (`### Form Features` → `- **Auto-complete**`)
severity: medium
summary: The bullet enumerates Thread Size, Purchase Location, Vendor, Location and Sub-Location as the fields with database-backed suggestions; `app/static/js/field-autocomplete.js` also registers `category_path` and `tags`, so the list is now contradicted by the manual's own Products and Catalog chapter and by its REST API section.
evidence: `app/static/js/field-autocomplete.js:676-700` registers seven inputs — the five named plus `{ inputId: 'category_path', field: 'category_path' }` (689) and `{ inputId: 'tags', field: 'tags' }` (698), the latter with the caret-scoped fragment behavior the new chapter documents at "Entering Tags". The bullet sits inside the **Adding New Inventory** (item) chapter and describes the item form, so correcting it is an Add-Item-chapter pass rather than a product one; DW-41's own evidence flagged this staleness at line 89 before the Products chapter existed, and adding that chapter made the contradiction visible rather than causing it. The spec for DW-41 explicitly forbade editing unrelated chapters.
status: open

### DW-129: The user manual's Table of Contents omits `## Quick Reference Card`
origin: spec-products-user-manual-chapter
source_spec: `_bmad-output/implementation-artifacts/spec-products-user-manual-chapter.md`
location: `docs/user-manual.md` lines 3-16 (Table of Contents) and line 1958+ (`## Quick Reference Card`)
severity: low
summary: `## Quick Reference Card` is a top-level chapter with no Table of Contents entry, so the TOC runs 1-13 and stops at Troubleshooting while a fourteenth chapter follows it in the file.
evidence: `grep -n '^## ' docs/user-manual.md` lists `## Quick Reference Card` after `## Troubleshooting`; the TOC's last item is `13. [Troubleshooting](#troubleshooting)`. Pre-existing — the chapter was unlisted before the Products chapter was added, and the DW-41 change only renumbered entries 8-13, which is why the omission surfaced during that review without being caused by it. Fixing it is a one-line TOC addition, but it changes a chapter list the DW-41 spec scoped to "the TOC entry + renumbering" only.
status: open

### DW-130: The manual's "Main Navigation" list omits the Admin menu and the JA ID Quick Lookup field
origin: spec-products-user-manual-chapter
source_spec: `_bmad-output/implementation-artifacts/spec-products-user-manual-chapter.md`
location: `docs/user-manual.md` lines 31-44 (`### Main Navigation`)
severity: low
summary: The list now names Home, Add Item, Search, Inventory List, Move Items, Shorten Items, Products and Scan barcode, but `app/templates/base.html` also renders an **Admin** dropdown and a **JA ID Quick Lookup** field in the same navbar, neither of which appears anywhere in the manual's navigation list.
evidence: `app/templates/base.html:69` renders the `Admin` entry and `:74` the `<!-- JA ID Quick Lookup -->` block, both siblings of the Products dropdown and the scan field that DW-41 added to this list. Pre-existing gap: the two omissions predate the Products chapter, and DW-41's spec restricted edits outside the new chapter to adding the Products menu and the scan field, so completing the list was out of scope for it.
status: open

### DW-131: The pre-existing `Barcode Scanner Support` section and its troubleshooting entry predate the scan router and now compete with the Products chapter's Scanning section
origin: spec-products-user-manual-chapter
source_spec: `_bmad-output/implementation-artifacts/spec-products-user-manual-chapter.md`
location: `docs/user-manual.md` line 1852 (`### Barcode Scanner Support`) and line 1917 (`#### "Barcode scanner not working"`)
severity: low
summary: An operator whose scan misbehaves reaches the older Barcode Scanner Support / "Barcode scanner not working" advice, which is about wedge configuration and item JA IDs and carries no pointer to the Products chapter's `#### Scan Messages` table — the only place the ten client messages and their meanings are documented.
evidence: Both headings exist untouched at `docs/user-manual.md:1852` and `:1917`; `grep -n '#scanning' docs/user-manual.md` shows the only cross-references to the new Scanning section come from the Main Navigation list and from within the Products chapter. The navbar scan field is a global, every-page feature whose behavior is now documented as a `###` inside a product chapter, so the two treatments of scanning need reconciling — either a cross-reference from the troubleshooting section or a promotion of the scan documentation. DW-41's spec forbade rewriting unrelated chapters, which is why the duplication was left standing.
status: open

### DW-132: The Quick Reference Card's "Most Common Operations" list predates products, catalog and scanning entirely
origin: spec-products-user-manual-chapter
source_spec: `_bmad-output/implementation-artifacts/spec-products-user-manual-chapter.md`
location: `docs/user-manual.md` line 2059 (`### Most Common Operations`, inside `## Quick Reference Card`)
severity: low
summary: The four numbered operations are Add Item, Find Item, Move Items and List All — all inventory-item workflows. Nothing in the card mentions adding a product, finding one, the navbar scan field, or the `Products` menu, so the manual's own at-a-glance page still describes a system without a catalog.
evidence: `sed -n '2057,2062p' docs/user-manual.md` shows the list unchanged: `1. **Add Item**`, `2. **Find Item**`, `3. **Move Items**`, `4. **List All**`. The Products and Catalog chapter added by DW-41 documents nine product workflows and the every-page scan field, none of which reached this card. Distinct from DW-129, which is about the Table of Contents omitting the `## Quick Reference Card` heading, not about the card's contents. Pre-existing in the sense that the card was already stale for Epics 3 and 4 before the chapter existed; adding the chapter made the staleness legible rather than causing it, and the DW-41 spec's `Never` clause confined edits outside the new chapter to the TOC entry, the Main Navigation list and one REST cross-reference.
status: open

### DW-133: Follow-up review still recommended for dw-products-user-manual-chapter after the damping cap was spent
origin: review-budget-followup
source_spec: `spec-products-user-manual-chapter.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260726-064033-76c4; this entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-134: `Help`'s entry-level `shift: true` makes the advertised bare `F1` shortcut unreachable
origin: spec-keydown-handler-focus-guards
source_spec: `_bmad-output/implementation-artifacts/spec-keydown-handler-focus-guards.md`
location: `app/static/js/main.js:148-158`, `app/static/js/main.js:168`
severity: low
summary: The `Help` entry lists `keys: ['F1', 'Slash']` but declares `shift: true` for the whole entry, so `matchesShift = !shortcut.shift || e.shiftKey` fails for a bare `F1` and the key never matches — while `docs/user-manual.md:1947`, `docs/user-manual.md:2034` and the modal's own footer (`main.js:93`) all tell the operator to press it.
evidence: `main.js:168` computes `matchesShift` from the entry's flag, and only `Help` sets one; with `e.code === 'F1'` and `e.shiftKey === false` the entry cannot match, so the action's own `e.code === 'F1'` branch (`:153`) is dead code. The shortcut-table `preventDefault()` at `:172` is keyed on `e.code === 'F1'` and is unreachable for the same reason — and, unlike the toast, it is not covered by the new "only when the action acted" rule, so it would fire ahead of the action's decision if the entry were ever fixed. Pre-existing; DW-64's spec held the shortcut table's matching semantics out of scope so that its fix stayed to the focus guard.
status: open

### DW-135: One `Shift`+`/` press runs two shortcut actions, because the match loop has no early exit
origin: spec-keydown-handler-focus-guards
source_spec: `_bmad-output/implementation-artifacts/spec-keydown-handler-focus-guards.md`
location: `app/static/js/main.js:164-186`
severity: low
summary: `Focus Search` declares no `shift` requirement, so `Shift`+`/` matches it as well as `Help`; `Object.entries(shortcuts).forEach(...)` visits every entry with no `break`, so both actions run for a single keypress.
evidence: `matchesShift = !shortcut.shift || e.shiftKey` is `true` for `Focus Search` on any `Slash` press regardless of Shift, so `Shift`+`/` would focus a search box and then open the help modal over it. Harmless only because `Focus Search`'s selector matches nothing (DW-137) — the ordering hazard is intact and would surface the moment a search field exists. `tests/e2e/test_keydown_focus_guards.py::test_shift_slash_still_opens_the_help_modal_and_toasts_once` pins today's single-toast outcome, so a fix has a guard to check itself against. Pre-existing; out of scope for DW-64, which was confined to the focus guard.
status: open

### DW-136: A modifier-less shortcut entry matches any Ctrl/Meta/Alt chord
origin: spec-keydown-handler-focus-guards
source_spec: `_bmad-output/implementation-artifacts/spec-keydown-handler-focus-guards.md`
location: `app/static/js/main.js:166-167`
severity: medium
summary: `matchesCtrl = !shortcut.ctrl || e.ctrlKey || e.metaKey` (and `matchesAlt` likewise) tests only whether a *required* modifier is present, never whether an *unrequested* one is absent, so `Ctrl`+`/` still matches `Focus Search` and `Ctrl`+`Shift`+`/` still matches `Help` whenever no form field has focus.
evidence: The focus guard added for DW-64 closes this only while a field owns focus. With focus on `body` — the default state of every page, and the state an add-page wedge burst arrives in once the scanner is armed — a wedge's control chords (GS as `Ctrl`+`]`, RS as `Ctrl`+`^`) still reach the table, and a barcode carrying `Shift`+`/` opens the keyboard-help modal mid-burst. This is the no-field-focused sibling that DW-64's own evidence names as a distinct entry; a fix is a strict equality per modifier (`!!shortcut.ctrl === (e.ctrlKey || e.metaKey)`), which changes matching semantics for every entry and so needs its own story.
status: open

### DW-137: `Focus Search` has no target in any template, so `/` is now silently inert while the manual still documents it
origin: spec-keydown-handler-focus-guards
source_spec: `_bmad-output/implementation-artifacts/spec-keydown-handler-focus-guards.md`
location: `app/static/js/main.js:135-146`, `app/static/js/main.js:194-200`, `docs/user-manual.md:1943`
severity: medium
summary: The selector `input[type="search"], input[name*="search"], #search` matches no element in any template, so the shortcut has never focused anything; gating its confirmation toast on the action (DW-64's fix) removed the only feedback it produced, leaving `/` with no effect and no response at all.
evidence: No template contains `type="search"`, a `name` containing `search`, or `id="search"` — `app/templates/inventory/list.html:60`'s `id="search-filter"` is the near miss, and `app/templates/base.html:91` records that `#scan-input` is deliberately *not* a search input. Meanwhile `docs/user-manual.md:1943` states "`/` - Focus search field from anywhere in the application" and `main.js:196` still feeds `'/': 'Focus search input'` into the in-app help modal, so both the manual and the app advertise a shortcut that provably does nothing. Not caused by the focus-guard work — the shortcut was already inert, merely noisy about it — but that change is what made the failure silent, and the resolution (wire it to a real field, or drop the shortcut and its documentation) is a product decision the spec's `Never` list held out of scope.
status: open

### DW-138: Focus is stranded on `#scan-ja-id-btn` after a capture ends, so Enter re-arms the scanner instead of moving on
origin: spec-keydown-handler-focus-guards
source_spec: `_bmad-output/implementation-artifacts/spec-keydown-handler-focus-guards.md`
location: `app/static/js/inventory-add.js:195` (`startBarcodeCapture`), `app/static/js/inventory-add.js:208-217` (`cancelBarcodeCapture`)
severity: low
summary: `startBarcodeCapture()` moves focus onto the scan button and nothing ever moves it off again — not `processBarcodeInput`, not `cancelBarcodeCapture`, not the 10 s auto-cancel — so after every scan the operator's caret sits on a `type="button"` element where Enter and Space re-arm the capture they just finished.
evidence: `cancelBarcodeCapture()` resets `scanModeActive`, the buffer and the button's classes, and touches focus nowhere; `processBarcodeInput()` writes `#ja_id` and calls it. `clearFormForContinue()` focuses `#ja_id` after every Save & Continue, so bulk entry runs field → scan button → *button*, and the operator has to click or tab back into the form each cycle. Restoring focus is a two-line change (stash `document.activeElement` at arm time, or focus `this.scanTargetField` on completion) but it is a behavior change to the capture lifecycle, which the DW-56/DW-64 spec's `Never` clause held out of scope ("do not cancel or auto-exit add-page scan mode... do not change the scan buffer's parsing, timeouts, or toasts"). Pre-existing on Chromium, which focuses a clicked button natively; the `button.focus()` added for DW-56 makes it deterministic on every browser rather than causing it.
status: open

### DW-139: A burst interrupted mid-flight is flushed as though it were complete
origin: spec-keydown-handler-focus-guards
source_spec: `_bmad-output/implementation-artifacts/spec-keydown-handler-focus-guards.md`
location: `app/static/js/inventory-add.js:143-165` (`setupBarcodeScanning`)
severity: low
summary: The DW-56 focus guard returns before the `clearTimeout`, so if anything takes focus part-way through a burst the already-buffered prefix and its pending 100 ms flush both survive: the timer fires on a truncated buffer and `processBarcodeInput` reports `Invalid JA ID format: JA0` and disarms the scanner, while the rest of the burst types into whatever took focus.
evidence: The guard is `if (WorkshopInventory.utils.isFieldFocused()) return;` placed above `if (this.scanTimeout) clearTimeout(this.scanTimeout)`. That placement is deliberate and correct for its own purpose — clearing the timer on ignored keystrokes would postpone the flush for as long as an operator keeps typing — but it means the guard cannot distinguish "the operator started typing" from "focus moved mid-burst". Candidates for the focus move exist: `main.js:518` focuses the first invalid field during validation, and a stray click lands anywhere. Before the guard the whole burst went to the buffer, so this failure mode is new; the window is one burst wide (~50 ms) and `processBarcodeInput`'s `^JA\d{6}$` check means a truncated prefix error-toasts rather than writing a wrong JA ID, which is why it is low rather than a data defect. The fix — clearing `scanBuffer` and the pending timeout inside the guard — is exactly the buffer-behavior change that spec's `Never` clause excluded.
status: open

### DW-140: `startBarcodeCapture`'s 10 s auto-cancel timer is never cleared, so re-arming within 10 s kills the second capture
origin: spec-keydown-handler-focus-guards
source_spec: `_bmad-output/implementation-artifacts/spec-keydown-handler-focus-guards.md`
location: `app/static/js/inventory-add.js:200-205` (`startBarcodeCapture`)
severity: low
summary: The auto-cancel `setTimeout(..., 10000)` result is never stored and never cleared, and its callback tests only the live `this.scanModeActive` flag — so a timer left over from a completed capture cancels the *next* one if the operator re-arms inside the original 10 s window.
evidence: `startBarcodeCapture()` ends with a bare `setTimeout(() => { if (this.scanModeActive) this.cancelBarcodeCapture(); }, 10000)`; no handle is kept and `cancelBarcodeCapture()` has nothing to clear. Arm at t=0, scan successfully at t=2 (`processBarcodeInput` → `cancelBarcodeCapture`), arm again at t=5: the first timer fires at t=10, finds `scanModeActive` true again and disarms a capture that is only 5 s old, with no toast and only the button's colour changing back. Bulk entry through Save & Continue re-arms well inside 10 s. Pre-existing and untouched by the DW-56/DW-64 change, which added no timer and altered none; surfaced while reviewing the arm path. The fix is to stash the handle and `clearTimeout` it in `cancelBarcodeCapture()`.
status: open

### DW-141: Follow-up review still recommended for dw-scan-trim-rule-single-home after the damping cap was spent
origin: review-budget-followup
source_spec: `spec-scan-trim-rule-single-home.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260726-064033-76c4; this entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-142: Phase 1 sheds every pre-fill before phase 2 discovers how much budget flooring `q` frees
origin: spec-scan-url-q-floor-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-scan-url-q-floor.md`
location: `app/main/routes.py:2200-2222` (`_bounded_scan_url`), `app/main/routes.py:1412-1431` (`product_search`'s create link)
severity: medium
summary: The two phases run greedily in sequence rather than solving against the final `q`, so a multi-byte search scan deletes 100% of its pre-fills to buy budget that flooring `q` was about to free anyway — and the create escape hatch on the results page loses the label's receipt data with 837-2373 characters of headroom left unused.
evidence: Measured against the live app. `_bounded_scan_url('main.product_search', q='漢'*1024, mpn='ABC-123', quantity='5', order_number='PO-1234', vendor_sku='XYZ-9')` returns a 4627-character URL with all four pre-fills deleted and 2373 characters spare; building the same URL with `q` floored to 512 FIRST gives 4688 characters with all four intact. The astral equivalent finishes at 6163 with 837 spare, where the four pre-fills cost ~60. Cyrillic (2-byte) never enters phase 1 at all, so identical scans keep or lose their whole pre-fill set on alphabet alone. The consequence is not confined to the URL: `product_search` builds `create_url` from exactly those forwarded `_PRODUCT_PREFILL_ARGS`, and its `if query and not create_args` fallback then dumps the floored `q` into `description` — the untyped, blank-`mpn` create outcome `_scan_banner_args` says FR39 forbids, and no `_RECEIPT_FIELDS` survive to record a Purchase. NOT a deviation: the intent contract's Always list mandates this order ("Every non-`q` argument is exhausted (halved to nothing and dropped) before `q` is touched at all"), and the code implements it exactly. What is deferred is the mandated order itself — a single budget-aware pass that floors `q` and then re-adds pre-fills while they fit would honour the same priority (`q` outranks every pre-fill) without paying for it. Shares a root cause with DW-143.
status: open

### DW-143: Phase 2 is a one-shot cut to exactly the floor, so the stated truncation interval has no interior
origin: spec-scan-url-q-floor-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-scan-url-q-floor.md`
location: `app/main/routes.py:2218-2222` (`_bounded_scan_url`'s second loop)
severity: low
summary: `q` reaches `_bounded_scan_url` already capped at `_SCAN_URL_Q_LIMIT` (1024), so a single halving always lands at or below 512 and `max(..., _SCAN_URL_Q_FLOOR)` pins it exactly there — `q` is shortened further than the transport requires, and a shorter prefix is a WIDER prefix match, so the eviction window the floor exists to narrow is wider than it needs to be.
evidence: Measured: `q = '漢' * 1024` is cut to 512 for a 4627-character URL, 2373 characters under budget, while a 775-character `q` builds a 6994-character URL that fits — 263 characters of the operator's search term discarded for nothing. The interval the docstrings now promise (`_SCAN_URL_Q_LIMIT` down to `_SCAN_URL_Q_FLOOR`) therefore has exactly two reachable values, 1024 and 512, and no input lands strictly inside it. The fix is to cut `q` to the largest length that fits, floored at `_SCAN_URL_Q_FLOOR`, for the same number of `url_for` rebuilds. Out of scope here because the intent contract specifies the halving rule literally (`max(len // 2, _SCAN_URL_Q_FLOOR)`) and the Design Notes derive the floor from it.
status: open

### DW-144: The shrink candidate set is a type test, not an allow-list of query arguments
origin: spec-scan-url-q-floor-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-scan-url-q-floor.md`
location: `app/main/routes.py:2203-2204` (`isinstance(value, str)` in `_bounded_scan_url`)
severity: low
summary: Path arguments are kept out of the shrink loop by testing their TYPE rather than by naming the query arguments, so an endpoint with a `<string:...>` or `<path:...>` converter would have its path segment halved and then deleted outright — first silently building a URL for the wrong resource, then raising `BuildError` out of `url_for` as an uncaught 500 inside the scan API, the dead end FR36/FR40 forbid.
evidence: The guard works today only because the one path argument in play — `product_detail`'s `product_id` — is an int, and `_bounded_scan_url` is called with just three endpoints. But `app/main/routes.py` does define string-converter routes (`<ja_id>`, `<field>`), so nothing structural stops a fourth call site from being added, and the docstring at `_bounded_scan_url` invites the reader to believe the guard is about path arguments in general rather than about ints. The new `del args[costliest]` branch sharpens the failure from "wrong resource" to "BuildError": the pre-change code halved to `''` and the `and value` filter then left the key in place. An explicit allow-list of query-argument names, or reading the endpoint's `arguments` off the url map, would make the guard say what the docstring claims.
status: open

### DW-145: Phase 1 halves control and coupled values instead of dropping them as a unit
origin: spec-scan-url-q-floor-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-scan-url-q-floor.md`
location: `app/main/routes.py:2203-2216` (`_bounded_scan_url`'s phase 1), `app/main/routes.py:1880-1882` (`_scan_prefill_args`)
severity: low
summary: The loop treats every string argument as independently truncatable text, but several are not: `identifier_type`/`identifier_value` are emitted as a pair and the new `del` can remove the value while keeping the 4-character type; wire values like `scan_kind` and `identifier_type` halve to `'GT'`; and `quantity` `1000` -> `10` or a shortened `order_number` renders on the create form as a perfectly plausible value the operator may save as if it were what the label said.
evidence: `_scan_prefill_args` emits the identifier pair together and `_SCAN_URL_ARG_LIMITS` sizes `identifier_value` at 255, so nothing in `_bounded_scan_url` knows the two travel together or that a normalized GTIN is at most 14 digits. Reachability is narrow — `max` picks the costliest candidate, so a short numeric or enum value is only reached once everything else is already shorter, by which point the URL usually fits — but the loop's own contract offers no bound on it, and phase 1 now runs to exhaustion on every over-budget search scan (DW-142) rather than stopping early as the pre-change halving did. Dropping these fields outright rather than halving them would close it, but must not empty the ECIA create arm entirely, whose `mpn`/`vendor_sku`/`quantity`/`order_number` pre-fill carries no `description` to fall back on (FR40) — which is why it is a design decision rather than a patch.
status: open

### DW-146: A transport-shrunk pre-fill reaches the create form with nothing marking it as shortened
origin: spec-scan-url-q-floor-review-3
source_spec: `_bmad-output/implementation-artifacts/spec-scan-url-q-floor.md`
location: `app/main/routes.py:2200-2216` (`_bounded_scan_url`'s phase 1), `app/main/routes.py:1073-1080` (`_prefill_form_data`)
severity: low
summary: `_prefill_form_data`'s docstring states the module's rule for pre-fill length — "a too-long pre-fill earns a field message rather than being silently shortened behind the operator's back" — but `_bounded_scan_url` shortens pre-fills upstream of it for transport reasons, and the halved value arrives inside its column limit, so it renders as an ordinary valid entry and nothing on the page says it is a prefix of what the label carried.
evidence: Measured against the live app: an ECIA create URL whose five pre-fills sit at their real `_SCAN_URL_ARG_LIMITS` caps in astral text is 15371 characters unbounded, and `_bounded_scan_url` returns it at 6923 with `description` cut to 63 and `mpn`/`vendor_sku`/`order_number` to 127 — every one of them comfortably inside `products.mpn`'s VARCHAR(255), so `_validate_product_form` accepts them on POST without a field message and a half-MPN saves cleanly. `_scan_url_value` justifies ITS truncation with "a value past the column limit could not have been saved anyway", which does not cover a value cut from inside the limit; and `_scan_banner_args` emits no marker a template could render. Pre-existing rather than caused by this story — the pre-change "halve the longest" loop truncated the same values — and distinct from DW-142 (which is about the search arm's create link losing its pre-fills entirely) and DW-145 (which is about values a prefix of which is a different value, not a shorter one). What is missing is a signal: either a `scan_truncated` marker the create page can turn into a banner, or a rule that transport shrinking drops a pre-fill outright rather than emitting a plausible prefix.
status: open

### DW-147: `BaseExportService` builds a pool it has no API to dispose
origin: spec-app-scoped-database-engine-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-app-scoped-database-engine.md`
location: `app/export_service.py:32-60` (`BaseExportService.__init__`, `get_session`, `close_session`)
severity: low
summary: On the `database_uri=` path `BaseExportService` calls `create_engine` and the class exposes no `close()`/`dispose()`/context manager, so any caller that constructs one by URI leaks a connection pool for the life of the process.
evidence: The class has `get_session`/`close_session` for sessions but nothing for the engine; `grep -n "dispose" app/export_service.py` returns no hits. DW-32 removed the per-request leak only by threading the app-scoped `storage` through the four route call sites (`app/main/routes.py:4362, 4379, 4396, 4512`), which sidesteps the constructor rather than fixing it — the URI path is unchanged and still leaks. The new test has to reach in and call `service.engine.dispose()` by hand (`tests/unit/test_app_scoped_engine.py`, `test_database_uri_argument_still_builds_its_own_engine`), which is the class reporting the missing API. Pre-existing: `BaseExportService` never had a lifecycle method. Fixing it means deciding whether an owned engine should be disposed by a context manager, an explicit `close()`, or by removing the URI path altogether now that every in-app caller passes a storage.
status: open

### DW-148: The storage layer raises builtin `ConnectionError`, which the project's error handling does not know about
origin: spec-app-scoped-database-engine-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-app-scoped-database-engine.md`
location: `app/mariadb_storage.py` (`_get_session`), `app/db.py` (`get_app_storage`, `resolve_engine`), `app/exceptions.py`, `app/error_handlers.py:382`
severity: medium
summary: Database-unreachable failures raise the builtin `ConnectionError` rather than the project's `StorageError`/`WorkshopInventoryError` hierarchy, so they miss the registered storage-specific handler and land on the generic 500 — and the same builtin already means "the client socket died" elsewhere in the app.
evidence: `app/error_handlers.py:382` registers a handler for the `app/exceptions.py` hierarchy; a builtin `ConnectionError` is an `OSError` subclass and matches none of it, so an outage renders the generic 500 page with no storage-specific message. Separately `app/request_limits.py:636` catches `ConnectionError` to mean a reset/broken client socket (see the comment at `:649`), so one exception type now carries two unrelated meanings and any broad `except ConnectionError` conflates them. Pre-existing: `_get_session` raised `ConnectionError` before DW-32, which is why DW-32 mirrored it rather than diverging mid-refactor. DW-32 did widen the blast radius — `_get_storage_backend()` can now raise where it previously only constructed an object — so the fix is worth doing as its own change: introduce a `StorageError` subclass, raise it from these three sites, and confirm the handler renders something an operator can act on.
status: open

### DW-149: One process-wide pool of `pool_size=10` was never sized against a worker count
origin: spec-app-scoped-database-engine-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-app-scoped-database-engine.md`
location: `config.py:90-95` (`Config.SQLALCHEMY_ENGINE_OPTIONS`), `app/db.py` (`get_app_storage`)
severity: medium
summary: DW-32 collapsed N per-request pools into one process-lifetime pool, which makes `pool_size: 10` / `pool_timeout: 20` load-bearing for the first time — but neither value was revisited, `max_overflow` is unset, and nothing handles pool exhaustion.
evidence: `Config.SQLALCHEMY_ENGINE_OPTIONS` sets `pool_size: 10, pool_timeout: 20, pool_recycle: -1, pool_pre_ping: True` and no `max_overflow`, so SQLAlchemy's default of 10 applies for an effective ceiling of 20 concurrent connections for the whole process. Before DW-32 those numbers were inert (every request built its own pool and used one connection from it); now they cap real concurrency. The failure mode moved from "unbounded connections" to "requests block for `pool_timeout` seconds and then 500 with a `QueuePool` timeout", and no route catches `sqlalchemy.exc.TimeoutError`. Choosing the numbers needs the deployment's worker/thread count and MariaDB's `max_connections`, which is an operator decision rather than something a story can infer — hence deferred rather than guessed.
status: open

### DW-150: No test at any tier exercises the production storage path against MariaDB
origin: spec-app-scoped-database-engine-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-app-scoped-database-engine.md`
location: `tests/unit/test_app_scoped_engine.py`, `tests/e2e/test_server.py:67`, `tests/integration/conftest.py`
severity: medium
summary: `app/db.get_app_storage` — the path every production request now takes — is covered only by SQLite unit tests, and `MariaDBStorage.connect()` routes SQLite down a branch that ignores `engine_options` entirely, so the deployed combination of app-scoped storage plus real pool options is verified nowhere.
evidence: `tests/unit/test_app_scoped_engine.py` drives `get_app_storage` against temp-file SQLite; `connect()`'s first branch (`self.database_url.startswith('sqlite://')`) discards the caller's engine options for those URLs, so the pool tuning the singleton forwards is only ever asserted against a patched `create_engine`, never against a live pool. The e2e server injects `STORAGE_BACKEND` (`tests/e2e/test_server.py:67`) and so never constructs the singleton at all, and the integration fixtures build their own storage. Compounds DW-72's note that no test at any level runs `CatalogService` against MariaDB. The natural home is the integration tier that DW-33/35/50/85 established — a test that builds a production-shaped app against the MariaDB testcontainer and asserts one engine with the configured pool options.
status: open

### DW-151: The e2e server's injected storage accumulates a `scoped_session` per worker thread, which is exactly what the new teardown hook exists to prevent
origin: spec-app-scoped-database-engine-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-app-scoped-database-engine.md`
location: `app/__init__.py` (`_remove_app_scoped_session`), `tests/e2e/test_server.py:62-79` (`MariaDBStorage` injected into a `threaded=True` `make_server`)
severity: medium
summary: DW-32's `teardown_appcontext` hook removes the shared `scoped_session` only for the app-scoped singleton and deliberately skips injected backends, but the e2e server injects one long-lived `MariaDBStorage` into a multi-threaded werkzeug server — the one configuration in this repo that actually runs threaded — so its registry keeps a never-removed session per worker thread for the whole e2e run.
evidence: `tests/e2e/test_server.py` builds `MariaDBStorage(database_url=test_db_uri)`, connects it, passes it as `create_app(TestConfig, storage_backend=self.storage)` and serves it via `make_server(..., threaded=True)` for the session. `MariaDBStorage.connect()` binds `scoped_session(sessionmaker(...))`, which is thread-local, and the teardown hook reads `app.extensions[STORAGE_EXTENSION_KEY]` — never populated when a backend is injected — so nothing calls `remove()` on that registry. `TestConfig` inherits `pool_size: 5, pool_timeout: 10` from `config.py`, so enough distinct worker threads exhaust the pool and surface as `QueuePool limit ... timed out`, which reads as e2e flake. Pre-existing in the sense that nothing removed those sessions before DW-32 either; what is new is that the codebase now has a hook for precisely this leak and the injected path is carved out of it. "Lifetime belongs to the fixture" is a reason not to `close()` the storage, not a reason to leak per-thread sessions — the hook could remove the session for whichever storage the request actually used.
status: open

### DW-152: `/admin/api/materials/parents/<level>` returns 500 whenever a parent exists
origin: spec-app-scoped-database-engine-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-app-scoped-database-engine.md`
location: `app/admin/routes.py:132-153` (`get_available_parents` route), `app/mariadb_materials_admin_service.py:306-330` (`MariaDBMaterialsAdminService.get_available_parents`)
severity: medium
summary: The service returns a list of plain dicts; the route builds its JSON with `parent.name` / `parent.level` / `parent.notes` attribute access, so the endpoint 500s with `'dict' object has no attribute 'name'` for every level that has at least one active parent.
evidence: Confirmed by running it: against a production-shaped app with one active level-1 `MaterialTaxonomy` row, `GET /admin/api/materials/parents/2` returns `500 {'success': False, 'error': "'dict' object has no attribute 'name'"}`; with an empty table it returns `200 {'parents': []}` because the comprehension never executes, which is why no existing test catches it. `get_available_parents` returns `[{'name': ..., 'level': ..., 'notes': ...}]` while the route iterates `for parent in parents` and reads attributes. This is the AJAX endpoint the add-material form uses to populate its parent dropdown, so the dropdown is empty in the browser at level 2 and 3. Entirely pre-existing and unrelated to DW-32 — surfaced only because this review drove admin routes through a real request for the first time. Fix is one line either way (return objects, or index the dicts), plus a test with a row present.
status: open

### DW-153: `PhotoService()` with no storage still builds its own engine from `Config`, outside the app-scoped pool
origin: spec-app-scoped-database-engine-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-app-scoped-database-engine.md`
location: `app/photo_service.py:63-72` (`__init__`'s else branch), `manage.py:134`
severity: low
summary: DW-32 gave `PhotoService` a borrowed-engine path and ownership tracking, but left the no-storage branch calling `create_engine(Config.SQLALCHEMY_DATABASE_URI)` — a second pool outside the app's, built from the class-level config rather than `app.config`, and an opaque `ArgumentError` when that value is unset.
evidence: `manage.py:134` (`with PhotoService() as photo_service:`) is a live caller, and the class docstring's own usage example at `app/photo_service.py:34-38` shows the no-argument form. That branch bypasses `app/db.py` entirely, so a CLI run against a differently-configured app talks to whatever `.env` holds rather than to the app's database, and `create_engine(None)` raises `ArgumentError: Expected string or URL object` rather than naming the missing setting the way `MariaDBStorage._connect_locked` now does. Not fixed in DW-32 because a CLI invocation has no Flask app to scope an engine to, so the fix is a decision about whether `manage.py` should build an app context (and use `get_app_storage`) or whether `PhotoService` should take an explicit URL. Distinct from DW-147, which is the same shape in `BaseExportService`.
status: open

### DW-154: `app/db.py`'s creation lock is module-global and is held across a blocking `connect()`
origin: spec-app-scoped-database-engine-review-3
source_spec: `_bmad-output/implementation-artifacts/spec-app-scoped-database-engine.md`
location: `app/db.py:62` (`_storage_lock`), `app/db.py:106-140` (`get_app_storage`)
severity: medium
summary: One module-level `threading.Lock` guards first-touch creation for every app in the process and is held for the whole of `storage.connect()`, so during a database outage every worker thread queues behind one another's full connect timeout instead of failing fast.
evidence: `get_app_storage` takes `_storage_lock` and only releases it after `storage.connect()` returns. Nothing is cached on failure (by design — see the comment at `app/db.py:135-137`), so each request re-enters the lock and pays another connect attempt; `Config.SQLALCHEMY_ENGINE_OPTIONS` sets no `connect_args={'connect_timeout': ...}`, so that attempt is bounded only by the driver's TCP default. The effect is serialized thread-pool occupancy during an outage rather than N parallel fast failures. The lock being module-scoped rather than app-scoped also means one app's first touch blocks an unrelated app's in the same process (relevant to test runs and to `manage.py`-style multi-app processes, not to production). Recorded as a residual risk by the previous review pass and deliberately not fixed there: the obvious repair (per-app lock in `app.extensions`, or caching the unconnected storage so callers share its per-storage `_connect_lock`) rewrites the "caches nothing on failure" contract and the test that pins it, which is more churn than a review pass should take on. Fixing it properly means deciding the outage behavior first — fail fast with a negative-cache window, or set an explicit `connect_timeout` — which is a deployment call.
status: open

### DW-155: The `Storage` interface's data methods have no callers, so the app-scoped `scoped_session` the teardown hook releases is never populated
origin: spec-app-scoped-database-engine-review-3
source_spec: `_bmad-output/implementation-artifacts/spec-app-scoped-database-engine.md`
location: `app/storage.py` (the `Storage` ABC), `app/mariadb_storage.py:163-182` (`_get_session` and its callers), `app/__init__.py:52-77` (`_remove_app_scoped_session`)
severity: low
summary: `MariaDBStorage.Session` is bound by `connect()` but only ever used by the `Storage` ABC's data methods (`read_all`, `write_row`, `search`, …), and nothing anywhere in the repository calls those — every service builds its own `sessionmaker` from the engine — so the `teardown_appcontext` hook added for DW-32 releases a registry that holds no session.
evidence: `grep -rn "\.read_all(\|\.read_row(\|\.write_row(\|\.update_row(\|\.delete_row(\|\.search(" --include=*.py .` (excluding `venv/`) returns exactly one hit outside `app/storage.py`: `app/mariadb_storage.py:236`, the class calling itself. `_get_session()` is likewise reached only from within `app/mariadb_storage.py`. The sessions that *are* created per request — `InventoryService.Session()`, `CatalogService.Session()`, the `sessionmaker` at `app/main/routes.py:3262`, `PhotoService.session` — are bound to the shared engine directly and are not touched by the hook. `test_app_context_teardown_removes_the_shared_session` asserts only that `remove()` is called, i.e. that the mechanism fires, not that a session existed to release. The hook is harmless and correct-if-ever-used, so this is not a bug; the deferred decision is which way to resolve the contradiction with the project rule "don't bypass the `Storage`/service layers" (`_bmad-output/project-context.md`) — either route service reads through the `Storage` API (making the hook load-bearing) or retire the unused half of the ABC. Related: DW-151, which is the same registry on the injected e2e storage.
status: open

### DW-156: The three services' `storage=None` fallback now connects eagerly and leaks a storage, engine and session registry
origin: spec-app-scoped-database-engine-review-3
source_spec: `_bmad-output/implementation-artifacts/spec-app-scoped-database-engine.md`
location: `app/mariadb_inventory_service.py:139-150`, `app/mariadb_catalog_service.py:145-156`, `app/mariadb_materials_admin_service.py:34-44`
severity: low
summary: All three services still do `if storage is None: storage = MariaDBStorage()`, and DW-32 changed what that costs: `resolve_engine` now calls `connect()` on it, so constructing one of these services without a storage performs blocking network I/O, can raise `ConnectionError` where it previously could not, and abandons a connected storage (engine, pool and `scoped_session`) that nobody disposes.
evidence: Each constructor's fallback builds a bare `MariaDBStorage()`, which takes its URL from the class-level `Config` rather than `app.config` — the exact indirection DW-32 set out to remove — and `resolve_engine(storage)` then connects it because its `engine` is `None`. Before DW-32 the same branch produced a lazy `create_engine` that touched no socket at construction time. No production path reaches it: `app/main/routes.py` and `app/admin/routes.py` always pass `_get_storage_backend()`, and the unit suite always injects, which is why nothing caught the change in cost. Recorded as a residual risk by the previous review pass rather than fixed, because removing the fallback means deciding whether these services should require a storage (a signature change with call sites in tests) or fetch the app-scoped one themselves. Same shape as DW-153 (`PhotoService`) and DW-147 (`BaseExportService`), but in three more classes and, unlike those two, currently unreachable.
status: open

### DW-157: `product_edit` refuses a POST that omits `description` entirely, contradicting the partial-update rule every other field follows
origin: spec-product-form-add-edit-parity-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-product-form-add-edit-parity.md`
location: `app/main/routes.py:882-884` (`_validate_product_form`'s description rule), `app/main/routes.py:2494-2500` (`product_edit`'s `update_fields` loop)
severity: low
summary: `_validate_product_form` requires a non-blank `description` whether or not the key is present, while `product_edit`'s write path treats an absent key as "leave alone" for every other field, so a partial POST that simply omits `description` is refused rather than left unchanged.
evidence: The rule is `if not (form_data.get('description') or '').strip()`, which cannot distinguish an absent key from a blank one; the write loop immediately below is explicitly keyed on `field in form_data` for `manufacturer`, `mpn`, `category_path` and `notes`, and `_form_tags` returns None for an absent `tags` key. `update_fields` also hardcodes `'description': form_data.get('description')`, so `description` is the one field with no partial-update semantics on either side. Pre-existing — the validator has required description unconditionally since the route was written, and this pass did not touch that rule. The DW-52 merge made the mismatch visible rather than causing it: the re-render now shows the STORED description populated beside a "Label Description is required." message, because an absent key falls through to the stored value by design. Deciding it means choosing whether `description` is required-on-every-POST (in which case the message should say the key is missing, and the merge should not backfill it) or partial-update like its neighbours (in which case an omitted key means "leave the description alone"). That is a product call about what a partial POST to this route means, not a code cleanup.
status: open

### DW-158: `add.html` has no unkeyed validation-error fallback, so a future shared rule keyed on `notes` would be a silent 200 on the create form
origin: spec-product-form-add-edit-parity-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-product-form-add-edit-parity.md`
location: `app/templates/product/add.html` (no fallback block), `app/templates/product/edit.html:13-30` (the block that exists)
severity: low
summary: The unkeyed error fallback added for DW-13/DW-29 was scoped to `edit.html`, so the create form still has no home for an error key it renders no `invalid-feedback` block for — `notes` being the one such control today.
evidence: `edit.html` now renders every `validation_errors` entry outside `keyed_error_fields` in an alert above the card, which makes "an error renders nowhere" unreachable on that form for any present or future shared rule. `add.html` got no equivalent: it renders an `invalid-feedback` for `description`, `manufacturer`, `mpn`, `category_path`, `tags` and both identifier fields, but its `notes` textarea has none, so a rule `_validate_product_form` gains later keyed on `notes` would write nothing and say nothing there — the exact defect class `TestNoErrorRendersNowhere` exists to prevent, left standing on the side that actually creates products. Not currently reachable: no rule in either validator keys on `notes`. Pre-existing (the create form has never had a fallback) and deliberately out of scope for this story, whose task list named `edit.html` only. The fix is the same six-line block plus its own `keyed_error_fields` list, but adding a second hand-copied list to a second template is arguably the wrong shape — the two forms sharing one macro is the alternative worth weighing first, and that is a refactor rather than a patch.
status: open

### DW-159: `GET /products/edit/<id>` reads the stored values unguarded, so it 500s on the exact failure the POST path now degrades for
origin: spec-product-form-add-edit-parity-review-3
source_spec: `_bmad-output/implementation-artifacts/spec-product-form-add-edit-parity.md`
location: `app/main/routes.py:2422-2427` (the GET branch of `product_edit`), `app/main/routes.py:2456-2478` (`_render_data`, the guarded twin)
severity: low
summary: The DW-52 merge wrapped the stored-baseline read in a try/except on the POST re-render path, arguing that a display-only read must not turn this page into an error page — but the GET branch four lines above makes the identical `_product_form_data(product, service.get_tags_for_product(product_id))` call with no guard, so the more common way of reaching the form still answers 500 where the POST answers 200 plus a warning.
evidence: Confirmed by both reviewers of this pass with `get_tags_for_product` monkeypatched to raise: `GET /products/edit/<id>` propagates `RuntimeError` out of the view, while `POST` to the same route with the same failure returns 200, renders the form from the submitted values alone, and flashes "a field shown empty below may not actually be empty" (`test_an_unreadable_baseline_degrades_instead_of_500ing`). Pre-existing — the GET branch has read the tags unguarded since the edit form was written, and this story did not touch it; what the change introduced is the asymmetry, plus the reasoning in `_render_data`'s comment that argues against exactly this behaviour without extending to it. Not obviously a bug in either direction, which is why it is deferred rather than patched: on POST there is submitted data worth preserving, so degrading beats erroring, whereas a GET with no readable stored values has nothing to render and arguably should refuse rather than hand the operator a blank form whose every field is this route's own spelling of "clear this". Closing it means deciding which of those two the form owes the operator, and applying it to both branches so the comment and the code agree.
status: open

### DW-160: The two writers of `products.category_path` disagree about unstorable text, so the product forms can file a product where no search or suggestion will ever find it
origin: spec-category-length-rule-single-measure-review
source_spec: `_bmad-output/implementation-artifacts/spec-category-length-rule-single-measure.md`
location: `app/mariadb_catalog_service.py:234` (`create_product`), `:333` (`update_product`), `:773-779` (`rename_category_path`, the guarded twin), `app/main/routes.py` (`_validate_product_form`'s category check)
severity: medium
summary: `rename_category_path` refuses a canonical path that fails `sql_text.is_storable_text`, but `create_product`/`update_product` — and the form check in front of them — ask only `normalize_category_path`, which judges type and length and nothing else.
evidence: `rename_category_path` explicitly guards `not sql_text.is_storable_text(canonical)` before opening a session; the other two writers of the same column do not, and the pre-write check the product forms gained for DW-37 mirrors them rather than the rename. `normalize_suggestion_value`'s own docstring states the consequence: "the column would in fact accept it: a path carrying a NUL can be written, but no suggestion or search could ever match it back", which is why the suggestions endpoint refuses such a query. So a category path carrying a NUL or a lone surrogate is storable, unreachable by every lookup surface, and refused only on the rename path. Pre-existing — neither writer has ever checked it — and deliberately out of scope for DW-37, whose spec forbade adding an unstorable-text rule. Closing it means deciding where the check belongs: a fourth caller of `is_storable_text` in the route, or one guard inside the service that both writers share.
status: open

### DW-161: The category input now states its 512-character bound nowhere in the UI, and the suggestion dropdown goes quiet past it with no explanation
origin: spec-category-length-rule-single-measure-review
source_spec: `_bmad-output/implementation-artifacts/spec-category-length-rule-single-measure.md`
location: `app/templates/product/add.html`, `app/templates/product/edit.html`, `app/templates/product/category_rename.html` (the category inputs), `app/mariadb_catalog_service.py:358-407` (`normalize_suggestion_value`)
severity: low
summary: Removing `maxlength` for DW-37 was right — the limit is on the stored path, so a cap on typing truncates legal values in silence — but it also removed the only in-browser signal that a limit exists, and the category input carries no help text to replace it.
evidence: `maxlength="512"` was the sole statement of the bound on all three category inputs; `description`/`manufacturer`/`mpn` still carry theirs, and the Tags input compensates for having none with a `form-text` hint. Past the limit `normalize_suggestion_value` returns `None`, so `get_field_value_suggestions` matches nothing and the `+ Create "<path>"` affordance disappears — the dropdown simply empties, with no statement that the path is too long, until the form comes back carrying a character count the operator never typed. Not a defect in the change (the alternative silently truncates), and the fix is a one-line `form-text` under each input — but it is a visible UI addition, which is why it was deferred rather than patched into a change whose templates were otherwise attribute-only.
status: open

### DW-162: `field-autocomplete.js` sends the whole field value as `?q=` with no bound, so a pasted multi-kilobyte value kills the dropdown silently
origin: spec-category-length-rule-single-measure-review
source_spec: `_bmad-output/implementation-artifacts/spec-category-length-rule-single-measure.md`
location: `app/static/js/field-autocomplete.js` (`buildUrl`, `fetchAndRender`), `app/main/routes.py` (`inventory_field_suggestions`)
severity: low
summary: The suggestion request carries the entire current fragment with no length cap on either side, so a value long enough to overrun the request line makes autocomplete fail with nothing but a console warning.
evidence: `buildUrl` appends the fragment verbatim and the endpoint applies no bound to `q`; `fetchAndRender` treats a non-OK response as `hide()` plus `console.warn`, so the visible symptom is a dropdown that stops appearing. The codebase treats the request-line bound as real elsewhere — `_SCAN_URL_Q_LIMIT` (1024) and `_MAX_SCAN_URL_CHARS` (7000) exist for exactly this transport. Pre-existing rather than introduced: the Tags input has never carried a `maxlength` either, and a paste with no separator sends the whole value as one fragment. DW-37 makes it reachable from a second field by removing the category cap. Closing it means one bound, client-side in `buildUrl` or server-side on `q`, applied to every field the component serves.
status: done 2026-07-28
resolution: resolved by sweep bundle dw-suggestion-query-length-bound

### DW-163: `maxlength` counts UTF-16 code units, so the three raw-length inputs truncate astral text well below the limit they state
origin: spec-category-length-rule-single-measure-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-category-length-rule-single-measure.md`
location: `app/templates/product/add.html:57,67,73`, `app/templates/product/edit.html:40,50,56` (`description`, `manufacturer`, `mpn`), and the same attribute on the Purchase inputs in `add.html:192-208` / `purchase_add.html:28-85`
severity: low
summary: HTML `maxlength` bounds the value's *code-unit* length, while `_PRODUCT_FIELD_LIMITS` and the `utf8mb4 VARCHAR(255)` column both count code points — so a paste made of astral characters is silently shortened to as few as 127 of them, which is the exact harm DW-37 removed the category cap to avoid.
evidence: Per the HTML standard the `maxlength` constraint is applied to the "code-unit length" of the value; every non-BMP character (emoji, CJK Extension B+, most historic scripts) is two code units, so 200 such characters read as 400 and the browser stops the operator at 127. The server rule these inputs mirror is `len(value) > limit` on a Python `str`, which counts code points, and the column stores 255 of them. BMP text — including ordinary Chinese, Japanese and Korean — is unaffected, which is why this has never surfaced. Pre-existing and deliberately untouched: DW-37's spec forbids changing the other `_PRODUCT_FIELD_LIMITS` entries or their inputs, and `test_neither_form_caps_the_category_input` now pins `maxlength="255"` on all three. Closing it means deciding whether the argument that removed the category cap generalises — drop these three too and let the server be the only enforcer — or whether a cap that is correct for ASCII is worth keeping with the discrepancy documented.
status: open

### DW-164: The manual explains the 255-character server messages as coming from a scan pre-fill, which cannot produce them
origin: spec-category-length-rule-single-measure-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-category-length-rule-single-measure.md`
location: `docs/user-manual.md:746-749` (the "Long values are cut off" paragraph) and `:1249` (the same claim in the message table), against `app/main/routes.py:2029-2042` (`_SCAN_URL_ARG_LIMITS`) and `:2130-2134` (`_scan_url_value`)
severity: low
summary: Both passages tell the operator that `MPN must be 255 characters or fewer.` and its siblings arrive "from a scan pre-fill rather than from anything you typed", but `_scan_url_value` truncates every pre-filled value to the same 255 characters the validator compares against, so a pre-fill is never over the limit.
evidence: `_SCAN_URL_ARG_LIMITS` bounds `description`, `manufacturer` and `mpn` at 255 and `_scan_url_value` applies it as `text[:limit]`; `_validate_product_form` then tests `len(value) > 255`, which 255 does not satisfy. With the input's `maxlength` stopping typing and the pre-fill capped at exactly the boundary, the only remaining route to these three messages is a request that did not come from the rendered form — a hand-built POST or a client ignoring `maxlength`. Pre-existing: the sentence predates this change, which rewrote the surrounding paragraph to carve **Category** out of it and carried the explanation through unexamined. Closing it means either stating the real reachability or dropping the explanatory clause; it does not affect what the software does.
status: open

### DW-165: `nox -s screenshots_verify` is not run by any CI workflow, so the manifest gate only fires when a human types the command
origin: spec-screenshot-manifest-completeness-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-screenshot-manifest-completeness.md`
location: `.github/workflows/screenshots.yml`, `.github/workflows/test.yml`, `noxfile.py` (`screenshots_verify`)
severity: medium
summary: The 526-line verifier and its 60 unit tests exist to make a partial screenshot regeneration detectable, but nothing automated ever runs the session, so the detection only happens if someone chooses to look.
evidence: `grep -rn "screenshots_verify" .github/` returns nothing. `test.yml` runs `tests`, `doctests`, `coverage`, `e2e` and `integration`; `screenshots.yml` runs `screenshots_headless` and then a `git diff` check. A developer can run `nox -s screenshots -- -k add_item`, commit the truncated `metadata.json`, and open a PR with nothing failing — the exact scenario `GENERATION_GUIDE.md` claims is "no longer indistinguishable from a complete one". Deliberately out of scope for the spec, which forbade wiring the session into `nox.options.sessions`; CI wiring is a separate decision (which workflow, and whether it should gate or only warn) and see DW-168, which must be resolved first or the added step will be permanently noisy.
status: open

### DW-166: `conditional` captures are exempt from staleness detection in both directions, so three doc-embedded screenshots can rot behind a green verify
origin: spec-screenshot-manifest-completeness-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-screenshot-manifest-completeness.md`
location: `tests/e2e/screenshot_verifier.py` (`_verify_cross_references`, the `conditional_outputs` exemption and the `elif status == 'planned'` arm), `tests/e2e/screenshot_config.yaml` (the 5 `conditional` definitions)
severity: medium
summary: A `conditional` output is exempted from the orphan check and never subject to the required check, so its committed PNG is validated against nothing at all — permanently, and silently.
evidence: Reproduced directly: with config `[{name: a, output: readme/a.png, capture_status: conditional}]` and an empty manifest, `verify()` returns `[]` while `readme/a.png` sits on disk. Three `conditional` outputs are embedded in shipped documentation — `user-manual/bulk_creation_preview.png` (`docs/user-manual.md:113`), `user-manual/history_view.png` (`:452`), `user-manual/batch_operations_menu.png` (`:560`) — and all three guards are `if locator.count() > 0` / `try/except` blocks that cannot fail their test. Rename the button `test_screenshot_history_view` looks for and the capture stops firing forever while verification stays green. This is the deliberate cost of the high-severity fix in the first review pass (before it, a skipped conditional hard-failed as an orphan, which broke ordinary runs), and it is recorded as a residual risk in that pass — but it leaves 5 of 21 definitions outside the completeness guarantee the work exists to provide. Closing it needs a third state the verifier can check, most plausibly a content binding (hash or mtime-vs-source) rather than a presence check.
status: open

### DW-167: A screenshot session that captures nothing leaves the previous manifest untouched, so a filtered run whose guards all miss verifies clean against a stale file
origin: spec-screenshot-manifest-completeness-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-screenshot-manifest-completeness.md`
location: `tests/e2e/test_screenshot_generation.py` (`setup_screenshot_generator` teardown, `if self.screenshot.get_screenshot_count() > 0`)
severity: low
summary: The teardown only writes `metadata.json` when the session has captured something, so a run that captures nothing at all silently preserves the last good manifest and the tree still verifies as complete.
evidence: `get_screenshot_count()` returns `len(self.metadata['screenshots'])`, and `self.metadata` is now the session-shared manifest, so the guard is cumulative: it is false only until the first capture in the session, and a whole session that captures nothing never writes. `nox -s screenshots -- -k label_printing` (whose guard needs `#options-dropdown-btn` and `#bulk-print-labels-btn` to both be present) is a concrete way to reach it. The pre-existing consequence — stale manifest survives — was the same before the shared manifest; what changed is that the guard's per-test meaning became session-wide, so the comment above it ("Rewrite the full accumulated manifest after each test") no longer describes the condition beneath it. Not patched because the fix is a design choice the spec did not make: writing unconditionally is faithful to "the manifest is what this run wrote" but clobbers a good manifest with an empty one whenever a session captures nothing, which is arguably the worse of the two failure modes. Related to the filtered-run truncation hazard already documented in `GENERATION_GUIDE.md`.
status: open

### DW-168: `metadata.json`'s per-run timestamps make the CI screenshot-diff check unconditionally dirty, so every triggering PR gets an "outdated screenshots" comment
origin: spec-screenshot-manifest-completeness-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-screenshot-manifest-completeness.md`
location: `.github/workflows/screenshots.yml` (the "Check for screenshot differences" step, `git diff --quiet docs/images/screenshots/`), `tests/e2e/screenshot_generator.py` (`new_manifest`'s `generated_at`, `_record_screenshot`'s `timestamp`)
severity: low
summary: The workflow decides whether screenshots need regenerating by asking whether `docs/images/screenshots/` changed, but `metadata.json` lives in that directory and its timestamps are rewritten on every run, so the answer is always yes.
evidence: Any PR touching `app/templates/**`, `app/static/css/**`, `app/static/js/**` or the screenshot tests triggers the workflow; it regenerates and then runs `git diff --quiet docs/images/screenshots/`, which can never pass. Every such PR therefore gets an artifact upload and an automated "📸 Screenshot Update Reminder" comment even when all 12 PNGs are byte-identical. `GENERATION_GUIDE.md` documents the cause ("`generated_at` and every entry's `timestamp` are rewritten on each run, so the file always shows a diff") without touching the workflow that it defeats. Pre-existing — the one-entry manifest had a changing timestamp too — but this work turned one changing timestamp into thirteen and made committing the file standard practice. Closing it means either scoping the diff check to `'*.png'` or making the manifest's timestamps stable, and it gates DW-165: adding a verify step to a workflow whose signal is already always-red buys nothing.
status: open

### DW-169: Two tests writing the same output filename now silently replace each other's manifest entry, and nothing can detect the collision
origin: spec-screenshot-manifest-completeness-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-screenshot-manifest-completeness.md`
location: `tests/e2e/screenshot_generator.py` (`_record_screenshot`'s replace-by-filename loop), `tests/e2e/screenshot_verifier.py` (`_verify_entries`'s duplicate check)
severity: low
summary: Replace-by-filename means a copy-paste error pointing two tests at one output produces a manifest that looks complete while one screenshot is quietly missing from the docs.
evidence: `_record_screenshot` scans for an existing `filename` and does `screenshots[index] = entry; return`. Both tests run, the second overwrites the first's PNG and replaces its manifest entry; the config declares one `output`, so the manifest, the disk and the config all agree and `verify()` returns `[]`. The verifier's `duplicate manifest entry` check can now only fire on a hand-edited file, which `GENERATION_GUIDE.md` forbids ("**Never hand-edit it**"), and the config-side duplicate-`output` check does not help because the collision is between two tests, not two definitions. The replace-by-filename behaviour is required by the spec ("a re-capture replaces, never duplicates") and is right for a genuine re-capture, so this is not a defect in the change — it is a detection gap the change's own design creates. Closing it means the manifest recording which test wrote each entry, so a filename claimed by two different tests is visible.
status: open

### DW-170: Seven `wait_for` selectors in `screenshot_config.yaml` name elements the capture tests never wait on
origin: spec-screenshot-manifest-completeness-review-3
source_spec: `_bmad-output/implementation-artifacts/spec-screenshot-manifest-completeness.md`
location: `tests/e2e/screenshot_config.yaml` (`wait_for` on `search_form`, `search_results`, `move_items_form`, `shorten_items_form`, `photo_gallery`, `history_view`, `bulk_creation_preview`, `batch_selection_options`), `tests/e2e/test_screenshot_generation.py`
severity: low
summary: The config's `wait_for` field disagrees with the selector the corresponding test actually waits on for eight of the fourteen required/conditional definitions, so the file that is now the declared contract still misdescribes how each capture is taken.
evidence: Compared field-by-field against `page.wait_for_selector(...)` / `wait_for_selector=` in `tests/e2e/test_screenshot_generation.py`: config `#search-form` vs actual `#advanced-search-form` (:167,:180); `table.search-results` vs `#results-table-container .table` (:204); `#move-items-form` vs `#batch-move-form` (:496); `#shorten-items-form` vs `#shorten-form` (:528); `.photo-gallery-grid` vs `#photo-manager-container` (:427); `#history-timeline` vs `#item-history-modal.show` (:626); `#quantity-preview` vs the `#quantity_to_create` fallback branch; and `batch_selection_options` declares `#options-dropdown` while its test passes no `wait_for_selector` at all. This work corrected the five wrong `test:` values in these same entries and left the `wait_for` values untouched; neither the verifier nor the new unit tests check them, and the I/O matrix does not ask them to — which is why this is a follow-up rather than a defect in the change. Closing it means either correcting the values and adding a check that binds them to the test source, or deleting the field as non-load-bearing.
status: open

### DW-171: `config.metadata_filename` and `config.generate_metadata` are honoured by the verifier but ignored by the generator
origin: spec-screenshot-manifest-completeness-review-3
source_spec: `_bmad-output/implementation-artifacts/spec-screenshot-manifest-completeness.md`
location: `tests/e2e/screenshot_generator.py` (`save_metadata(self, filename: str = 'metadata.json')`), `tests/e2e/test_screenshot_generation.py` (`setup_screenshot_generator` teardown), `tests/e2e/screenshot_verifier.py` (`_collect`'s `_metadata_filename(config)`)
severity: low
summary: Changing `metadata_filename` in the config moves only where verification looks, not where generation writes, so the two halves of the manifest contract silently disagree.
evidence: The verifier reads `config.get_metadata_filename()` to locate the manifest, but the teardown calls `self.screenshot.save_metadata()` with no argument and the generator's default is the literal `'metadata.json'`; no caller ever passes the configured value. Set `metadata_filename: manifest.json` and a successful full regeneration is followed by `manifest.json: manifest not found`, every PNG reported as an orphan and every required capture reported missing. `generate_metadata: true` is likewise read by neither side — the manifest is always written and always demanded. Pre-existing dead config that this work made load-bearing on one side only; closing it means feeding the configured name into `save_metadata()` (and deciding whether `generate_metadata: false` should make the verifier skip the manifest checks) or deleting the two keys.
status: open

### DW-172: `add_item_form_readme` is tagged `capture_status: planned` while its `test:` names a test that already exists and runs
origin: spec-screenshot-manifest-completeness-review-3
source_spec: `_bmad-output/implementation-artifacts/spec-screenshot-manifest-completeness.md`
location: `tests/e2e/screenshot_config.yaml:34-41`, `tests/unit/test_screenshot_infrastructure.py` (`test_capturing_definitions_name_real_test_methods`)
severity: low
summary: A `planned` definition documented as having no capture code points at `test_screenshot_add_item_form`, which exists and captures unconditionally — just to a different output — so the new `capture_status` field is self-contradictory for this entry and nothing can catch it.
evidence: `GENERATION_GUIDE.md` defines `planned` as "no capture code exists yet; `test:` names the future test", but `test_screenshot_add_item_form` is a real method (`tests/e2e/test_screenshot_generation.py:224`) writing `user-manual/add_item_form.png`, while this definition's output is `readme/add_item_form.png`. `test_capturing_definitions_name_real_test_methods` deliberately skips `planned` entries and there is no inverse check that a `planned` entry's `test:` does *not* already exist, so `nox -s tests` and `nox -s screenshots_verify` are both blind to it. Harmless today — the README capture genuinely does not exist — but it is the one place where the newly introduced status vocabulary is untrue. Closing it means either renaming the field's meaning for reuse cases (one test, two outputs) or extending the existing definition to capture both.
status: open

### DW-173: `scan_search_text` re-derives the winning candidate with a query it already computed and threw away, costing `POST /api/scan` a fifth session and opening a staleness window
origin: spec-ecia-per-candidate-resolution-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-ecia-per-candidate-resolution.md`
location: `app/mariadb_catalog_service.py` (`_ecia_fallthrough`, `scan_search_text`), `app/main/routes.py` (`_scan_destination`, `api_scan`)
severity: medium
summary: `_ecia_fallthrough` returns the candidate whose search produced the hits and `resolve_scan` discards it (`_, hits = ...`), so `scan_search_text` has to re-establish the same answer with another `search_products` call — a fifth full-table-scan session on an unauthenticated, CSRF-exempt, unthrottled endpoint, run against a catalog that may have moved since.
evidence: Verified by reading the seam and pinned by the suite: `resolve_scan`'s ECIA arm binds only `hits` from `_ecia_fallthrough`'s `(searched_text, hits)` tuple, and nothing in `app/` or `tests/` consumes the first element. `scan_search_text` then re-runs `search_products` for every candidate but the last (one search for the two candidates this arm has), which `test_the_endpoint_opens_no_more_sessions_than_api_scan_claims` pins at exactly five sessions per request and `api_scan`'s own docstring concedes "got worse rather than better here". The same re-derivation is a TOCTOU window the `scan_search_text` docstring already describes: a catalog write landing between `resolve_scan` and `scan_search_text` can make a different candidate win, so `q` can name a candidate other than the one `hit_count` was counted from. Both halves close the same way and neither could be closed in this work: the winning text has to be carried out of `resolve_scan`, and AD-15 plus this spec's intent contract prescribe `ScanResolution` as exactly three fields. A companion method returning `(resolution, searched_text)` would not touch the frozen dataclass, but choosing that shape is a contract decision this run had no mandate for. Note the route already holds the SAME `CatalogService` instance that resolved the scan (`_scan_destination(resolution, service)`), so the coupling that would make memoization possible has already been paid for.
status: open

### DW-174: `_ecia_prefill` is a fourth, divergent copy of the `1P`-then-`P` rule, so an unstorable part number reaches the create form as `mpn='?'` while the usable one is filed under `vendor_sku`
origin: spec-ecia-per-candidate-resolution-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-ecia-per-candidate-resolution.md`
location: `app/main/routes.py` (`_ecia_prefill`, `_scan_prefill_args`, `_scan_banner_args`), `app/mariadb_catalog_service.py` (`_ecia_candidates`)
severity: low
summary: `_ecia_candidates` is documented as "the ONE home for the candidate rule", but `_ecia_prefill` selects `mpn` from the same two records with different filters — it trims and applies neither the storability filter nor the ASCII case-fold dedupe — so the resolver and the create form disagree about which value is the part number whenever a candidate is unstorable or the two differ only by case.
evidence: Two verified shapes. (1) `1P='\ud800'` with `P='296-1234-ND'`: the resolver drops the unstorable candidate and lands on the `P` product, while `_ecia_prefill` still maps `1P` to `mpn`, so `_scan_banner_args` puts `mpn='\ud800'` on the "create a separate product instead" link, `_scan_url_value` scrubs it to `'?'`, and the actual matched part number goes to `vendor_sku`. (2) An envelope whose ONLY part number is unstorable: `_scan_prefill_args` returns early on the truthy `mpn`, so no `description` is added and the create form opens with `mpn='?'` and no trace of the scan — the loss FR40 forbids, which `_scan_prefill_args`' own docstring already warns about for the no-part-number case. Shape (2) is fully pre-existing (the blanket `is_storable_text(raw)` guard never reached this route helper, which works from the classification rather than the resolution); shape (1) is pre-existing code newly REACHABLE on the `product` outcome, because such an envelope could not land on a product before. Not patched in this work: `_ecia_prefill`'s field mapping is Story 4.5's contract, and filtering unstorable values there changes the no-match create form as well as the banner, which is scope this spec's boundaries do not grant. Closing it means either giving `_ecia_prefill` the same filters as `_ecia_candidates` (and deciding what a wholly unstorable envelope pre-fills instead) or exporting the candidate rule so both callers consume one implementation.
status: open

### DW-175: A whitespace-only identifier value passes all four pre-write identifier rules and is then silently dropped by the attach helper
origin: spec-pre-commit-gtin-check-digit-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-pre-commit-gtin-check-digit.md`
location: `app/main/routes.py` (`_validate_product_create_form`, `_attach_scanned_identifier`), `app/templates/product/add.html`
severity: low
summary: `identifier_value` is `.strip()`ped before every one of the four create-form identifier rules is gated on it, so a value of `'   '` fails none of them; `_attach_scanned_identifier` strips again, finds nothing, and returns `None` — the product is created, the identifier is gone and no message says so, on a form that rendered the Scanned Identifier card because the *unstripped* value was truthy.
evidence: Verified by reading the seam. `_validate_product_create_form` binds `identifier_value = (form_data.get('identifier_value') or '').strip()` and gates the blank-type, unknown-type, over-long and (new) GTIN check-digit rules on it, so all four skip. `_attach_scanned_identifier` opens with the same strip and returns `None` on the empty result, which `product_add` reads as "nothing to attach" rather than "attach failed", so no flash is emitted. Meanwhile `add.html` tests `form_data.identifier_value` unstripped when deciding to render the card, so the operator saw a filled-in Value field and gets a 302 with a plain success flash. Fully pre-existing and shared by all four rules — DW-23's change added the fourth rule to an existing gate and did not introduce or widen this. Reachable only by typing or pasting whitespace into the Value field, or via a `scan_value=%20` query string. Closing it means deciding what a whitespace-only value *means* — refuse it as an unusable identifier beside the field, or treat it as cleared and stop rendering the card for it — which is a form-contract choice, not a patch.
status: open

### DW-176: An `mpn`/`manufacturer` carrying a NUL or unpaired surrogate is form-reachable and stores successfully, leaving the product unreachable by every scan and search surface
origin: spec-dw-7-write-path-identifier-trim-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-7-write-path-identifier-trim.md`
location: `app/mariadb_catalog_service.py` (`_clean`, `create_product`, `update_product`), `app/main/routes.py` (`_validate_product_form`)
severity: medium
summary: The product write path applies `sql_text.is_storable_text` to `category_path` only (indirectly, via `normalize_category_path`), so a `mpn` or `manufacturer` containing a NUL or a lone surrogate is accepted by the create/edit forms and written to the column, after which `_ecia_candidates` drops such a value as a candidate and `search_products` refuses it as a query — the row can never be matched by the identifier it holds.
evidence: Verified by reading the seam. `_validate_product_form` (`app/main/routes.py`) gates only requiredness, the 255-char `_PRODUCT_FIELD_LIMITS` and `category_util.normalize_category_path`; no storability check touches `mpn`/`manufacturer`. `_clean` (`app/mariadb_catalog_service.py:123`) strips and NULLs blanks and asks nothing about storability, and `create_product`/`update_product` add no check of their own. On the read side, `_ecia_candidates` refuses the value at `:244` (`if not value or not sql_text.is_storable_text(value)`) and `search_products` refuses the query at `:2266`, so both of the two surfaces that could find the product decline. Fully pre-existing: `app/utils/sql_text.py:92` already records that nothing on the write path asks this question, and this run touched no behaviour. It is the same defect class as DW-160 (open) on a different column of the same table — that entry covers `category_path`, this one the two identifier-ish columns — so the two should be decided together. Closing it means choosing where the guard belongs: a `ValidationError` in the service (matching `add_identifier`'s treatment of an unusable identifier) or a form-level rule beside the field, and whether existing rows are swept.
status: open

### DW-177: `str.strip()` does not remove zero-width whitespace, so a part number pasted from a datasheet stores looking clean and misses the exact ECIA lookup forever
origin: spec-dw-7-write-path-identifier-trim-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-7-write-path-identifier-trim.md`
location: `app/mariadb_catalog_service.py` (`_clean`, `_ecia_candidates`, `add_identifier`), `app/main/routes.py` (`_ecia_prefill`)
severity: low
summary: Every trim on the part-number path is `str.strip()`, which removes U+00A0 but not U+200B, U+200C, U+200D or U+FEFF — all routine in text copied out of a datasheet PDF or a distributor page, which is exactly the input the write path's own comments name as the motivating case — so a zero-width-padded `mpn` stores intact, renders indistinguishably from a clean one, and can never equal the trimmed candidate a scan produces.
evidence: Verified against the four trim sites, which are `str.strip()` with no argument: `_clean` (`app/mariadb_catalog_service.py:123`), `_ecia_candidates` (`:244`), `add_identifier` (`:1845`) and `_ecia_prefill` (`app/main/routes.py`). Python's `str.strip()` strips `str.isspace()` characters; U+200B/U+FEFF are not among them (U+FEFF is `Cf`, U+200B is `Cf` since Unicode 4.0). The write and query sides therefore still AGREE — both leave the zero-width character in place — but agreement is not the property that matters: `_ecia_match` compares a column holding `'​RC0805-10K'` against a scanned candidate of `'RC0805-10K'` and finds nothing, and `search_products`' substring fallthrough misses too when the zero-width character sits inside the matched span. Pre-existing and not introduced or widened by this run, which changed no behaviour. Closing it means deciding the normalization vocabulary for stored identifiers (an explicit strip set, or NFKC, applied identically at all four sites) rather than adding a fifth ad-hoc strip.
status: open

### DW-178: `mpn`/`manufacturer` length is bounded only on the form path, so a direct service call stores an overlong value on SQLite and fails opaquely on MariaDB
origin: spec-dw-7-write-path-identifier-trim-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-7-write-path-identifier-trim.md`
location: `app/mariadb_catalog_service.py` (`create_product`, `update_product`), `app/main/routes.py` (`_PRODUCT_FIELD_LIMITS`, `_validate_product_form`)
severity: low
summary: The 255-character limit on `description`, `manufacturer` and `mpn` lives in `_PRODUCT_FIELD_LIMITS` at the route, not in the service, so `create_product`/`update_product` called programmatically accept any length — stored intact under the unit suite's SQLite, and on MariaDB caught by `create_product`'s blanket `except`, which logs an audit error and returns `None` that the caller can only report as a generic failure.
evidence: Verified by reading both halves. `_PRODUCT_FIELD_LIMITS` (`app/main/routes.py:789`) is consulted only by `_validate_product_form`; `create_product` and `update_product` contain no `len()` check, no `MAX_LENGTH` constant and no `ValidationError` for length. The contrast is inside the same class: `add_identifier` raises a clean `ValidationError` at `IDENTIFIER_MAX_LENGTH` (`app/mariadb_catalog_service.py:1849`), so the two write paths DW-7 asked to agree still disagree about what an over-long value is. Pre-existing and explicitly declared out of scope by `spec-dw-7-write-path-identifier-trim.md`'s Block If ("bounding `mpn` length the way `add_identifier` bounds identifier values ... out of scope"), which is why it is filed rather than fixed. Closing it means deciding whether the service or the route owns the limit — and if the service, whether `description` moves with the other two, since one dict currently holds all three.
status: open

### DW-179: `vendor_scope` is unnormalized free text, so a capitalization difference silently creates a second vendor namespace
origin: spec-dw-20-identifier-vendor-scope-input-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-20-identifier-vendor-scope-input.md`
location: `app/mariadb_catalog_service.py` (`add_identifier` scope computation), `app/main/routes.py` (`_validate_product_create_form`, `_attach_scanned_identifier`), `app/templates/product/add.html` (the Vendor Scope input)
severity: medium
summary: `add_identifier` stores `vendor_scope` exactly as typed apart from `.strip()`, so `DigiKey`, `digikey` and `DIGIKEY` are three distinct uniqueness namespaces under SQLite and one namespace under MariaDB's `utf8mb4_unicode_ci` — the two backends disagree about whether the same SKU may be added twice, and on either one a typo silently defeats the uniqueness the scope exists to establish.
evidence: Found by the adversarial review of DW-20 and reproduced: three products each accepted `VENDOR_SKU` `296-1234-ND` under scopes `DigiKey`, `digikey`, `DIGIKEY` on the unit suite's SQLite. `uq_product_identifiers_type_value_scope` (`app/database.py:1044`) covers `(identifier_type, value, vendor_scope)` and the column is a plain `String(255)`, so the fold is whatever the connection's collation says — `tests/integration/test_identifier_collation.py` already demonstrates that MariaDB folds case and accents on `value`, and `vendor_scope` sits in the same key. Not introduced by DW-20 — the scope computation at `app/mariadb_catalog_service.py:1887` predates it and was already reachable through `add_identifier`'s `vendor=` argument — but DW-20 is what first makes the UI populate it, so the exposure is new. There is no canonical vendor list and no suggestion dropdown, though the machinery exists (`FIELD_SUGGESTION_COLUMNS`, `app/mariadb_catalog_service.py:80`, and `field-autocomplete.js`, which the create form already loads). Closing it means deciding the vendor-scope vocabulary — case-fold at the service, a canonical vendor table, or an autocomplete that steers without constraining — and whether existing rows are swept.
status: open

### DW-180: the "a vendor-scoped type must carry a scope" rule lives only in the create form, inverting the service's own stated form-is-a-courtesy precedent
origin: spec-dw-20-identifier-vendor-scope-input-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-20-identifier-vendor-scope-input.md`
location: `app/mariadb_catalog_service.py` (`add_identifier`), `app/main/routes.py` (`_validate_product_create_form`)
severity: medium
summary: `add_identifier` still stores `vendor_scope=''` — the GLOBAL sentinel — for a `VENDOR_SKU`/`ASIN`/`FNSKU` called with no `vendor`, so DW-20's fix holds only for callers that go through the create form; the second caller the codebase keeps anticipating (an identifier-management surface on the product page) re-opens DW-20 by default and silently.
evidence: Found by the adversarial review of DW-20. `add_identifier`'s scope computation (`app/mariadb_catalog_service.py:1887`) coerces a missing `vendor` to `''` with no refusal, while the GTIN check twenty lines above it (`:1866-1870`) states the house rule the other way round — the form's check is a courtesy and the service's is the guarantee. DW-20's own spec put `no change to add_identifier's signature or its scope computation` under **Never**, and the human decision it implements is scoped to the create form, which is why this is filed rather than fixed. Closing it means deciding whether a vendor-scoped type without a vendor is a `ValidationError` at the service — which would change the contract for every caller and require auditing `tests/unit/test_catalog_service.py::TestCatalogServiceIdentifiers`, where `test_add_each_type_persists` adds vendor-scoped types with no vendor today.
status: open

### DW-181: the 255-character identifier limit is hand-copied into three places instead of read from `IDENTIFIER_MAX_LENGTH`
origin: spec-dw-20-identifier-vendor-scope-input-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-20-identifier-vendor-scope-input.md`
location: `app/main/routes.py` (`_IDENTIFIER_VALUE_LIMIT`, `_IDENTIFIER_VENDOR_LIMIT`), `app/templates/product/add.html` (`maxlength="255"` on `identifier_value` and `identifier_vendor`), `app/mariadb_catalog_service.py:69` (`IDENTIFIER_MAX_LENGTH`)
severity: low
summary: `IDENTIFIER_MAX_LENGTH = 255` already exists in the service, annotated as matching both the `value` and `vendor_scope` column lengths, and `app/main/routes.py` already imports from that module — yet the route declares two separate literal-255 constants and the template hardcodes the number twice more, so widening the column takes edits in three files and a missed one refuses input the column would hold.
evidence: Found by the adversarial review of DW-20. `_IDENTIFIER_VALUE_LIMIT` (`app/main/routes.py:809`) predates this run; `_IDENTIFIER_VENDOR_LIMIT` was added by it, following the neighbouring precedent rather than the authority. Patching only the newer of the two would have left the pair inconsistent, which is why this is filed as one entry over both. No behaviour is wrong today — all four numbers agree. Closing it means importing `IDENTIFIER_MAX_LENGTH` for both route constants and deciding how the template gets the number (a template global, or the existing render context) rather than leaving the two `maxlength` attributes as the last copies.
status: open

### DW-182: `product/add.html` associates no help text with its inputs and marks no invalid field for assistive technology
origin: spec-dw-20-identifier-vendor-scope-input-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-20-identifier-vendor-scope-input.md`
location: `app/templates/product/add.html` (every `form-text` and `invalid-feedback` block)
severity: low
summary: The create form carries no `aria-describedby` on any input and sets no `aria-invalid` on the error branch, so a screen-reader user hears none of the `form-text` guidance and gets no announcement that a field was refused — including the new Vendor Scope input, whose conditional requirement is stated *only* in help text and is therefore inaudible.
evidence: Found by the adversarial review of DW-20 and confirmed: `grep aria- app/templates/product/add.html` returned nothing before this run, and the DW-20 field was added in the surrounding style rather than as the template's lone exception. Wholly pre-existing and template-wide — the same is true of `description`, `manufacturer`, `mpn`, `category_path`, `tags`, `quantity`, `order_number`, `vendor` and `vendor_sku`. The project treats ARIA as a live concern elsewhere (`tests/e2e/test_autocomplete_aria.py`, and `spec-autocomplete-aria-semantics.md`), but that work is scoped to the autocomplete comboboxes, which is why the plain inputs were never covered. Closing it means deciding the association convention once and applying it to the whole form (and probably to `product/edit.html` and the inventory forms with it) rather than to one field.
status: open

### DW-183: vendor-scoped identifiers written before DW-20 still carry `vendor_scope=''`, and there is no way to repair them
origin: spec-dw-20-identifier-vendor-scope-input-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-dw-20-identifier-vendor-scope-input.md`
location: `product_identifiers` rows predating DW-20; `migrations/` (no backfill), `app/mariadb_catalog_service.py` (`add_identifier` — the only identifier write a route can reach)
severity: medium
summary: Every `VENDOR_SKU`/`ASIN`/`FNSKU` created through the product form before DW-20 landed was stored at `vendor_scope=''`, the GLOBAL sentinel, because the form passed no `vendor` at all — so the catalog now holds two populations under one constraint: legacy rows claiming the global namespace and new rows in a vendor's, and a legacy row can neither be re-scoped nor deleted through any UI.
evidence: Found by the adversarial and edge-case reviews of DW-20 and reproduced: a pre-existing `VENDOR_SKU` `296-1234-ND` at scope `''` and a new one at scope `'DigiKey'` persist on two different products with no collision and no warning, so the same vendor's SKU is now reachable under two keys. `_attach_scanned_identifier` is the only caller of `add_identifier` from a route (`app/main/routes.py`), and its own comment states there is no identifier-management surface anywhere yet, so nothing in the app can rewrite or remove the legacy row. Not fixable inside DW-20: its intent contract puts `No schema change, no migration` under **Never**, and the correct backfill is not mechanical — a legacy row's true vendor is knowable only from the product's purchase history, which may name several vendors or none. Closing it means deciding whether legacy rows are swept by an Alembic data migration (and by what rule), left as global and documented, or deferred until the identifier-management surface DW-180 also waits on exists.
status: open

### DW-184: the ECIA scan path knows the distributor but does not pre-fill the new Vendor Scope, so the operator retypes what the label already carried
origin: spec-dw-20-identifier-vendor-scope-input-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-dw-20-identifier-vendor-scope-input.md`
location: `app/main/routes.py` (`_ecia_prefill`, `_scan_prefill_args`, `_scan_banner_args`)
severity: low
summary: `identifier_vendor` joined `_PRODUCT_PREFILL_ARGS`, but nothing in the app ever emits it — a distributor-label scan pre-fills `vendor_sku`, `quantity` and `order_number` and no vendor at all, so an operator who then selects `VENDOR_SKU` must hand-type a scope the scanned envelope identified.
evidence: Found by the adversarial review of DW-20. `_scan_prefill_args` emits `identifier_type`/`identifier_value` only for `ScanKind.GTIN`; `_ecia_prefill` emits `mpn`, `vendor_sku`, `quantity` and `order_number`; `_scan_banner_args`' create link copies the same set — so the only producer of `identifier_vendor` is a hand-crafted URL, which is why the whitelist entry and its tests exercise nothing the product emits. Correct as shipped: DW-20's scope was the form, and the whitelist entry is what makes the field round-trip a failed submit. Closing it means deciding which ECIA data identifier names the distributor reliably enough to become a uniqueness namespace, and whether a pre-filled scope should be distinguishable from one the operator typed — a wrong scope is silent and, per DW-183, unrepairable.
status: open

### DW-185: DW-181's `location` and `summary` describe a `maxlength` on `identifier_value` that the template does not have
origin: spec-dw-20-identifier-vendor-scope-input-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-dw-20-identifier-vendor-scope-input.md`
location: this ledger, `DW-181`; `app/templates/product/add.html` (`identifier_value`, `identifier_vendor`)
severity: low
summary: DW-181 says the template hardcodes 255 "twice more" and names `maxlength="255"` on both `identifier_value` and `identifier_vendor`; `identifier_value` carries no `maxlength` at all, so whoever closes DW-181 will hunt a copy that does not exist — and will miss the live question, which is that `identifier_value` is the outlier among the form's text inputs rather than `identifier_vendor` being a duplication.
evidence: Found by the adversarial review of DW-20 and confirmed: `grep -n maxlength app/templates/product/add.html` returns `description`, `manufacturer`, `mpn`, `identifier_vendor`, `quantity`, `order_number`, `vendor` and `vendor_sku` — and no `identifier_value`. `category_path` and `tags` omit it with an explanatory comment each; `identifier_value` omits it with none, though its 255 limit is enforced server-side by `_IDENTIFIER_VALUE_LIMIT`. Filed as a new entry rather than an edit to DW-181 because the orchestrator owns existing entries' status and resolution. Closing it means correcting DW-181's location/summary and deciding whether `identifier_value` should gain the attribute its siblings have or gain the comment its two deliberate-omission neighbours have.
status: open

### DW-186: Quantity and Unit Price sit side by side on one card and disagree about what a number is
origin: spec-dw-22-first-receipt-unit-price-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-22-first-receipt-unit-price.md`
location: `app/main/routes.py` (`_positive_int_string` vs `_purchase_unit_price`), `app/templates/product/add.html` (the `#first-receipt` card)
severity: low
summary: `Quantity` is judged by `_positive_int_string`, whose `.isascii() and .isdigit()` rule refuses `1_0` and `٥` on purpose; `Unit Price`, one box away in the same card, is judged by `_purchase_unit_price`, which is `Decimal(str(...))` and therefore stores `1_0` as 10 and `٥` as 5 without a word — so two adjacent inputs on one block apply two different definitions of "a number", and the card's help text calls the price "a plain decimal number", which `1_0` is not.
evidence: Found by the adversarial review of DW-22 and verified in the interpreter: `Decimal('1_0') == 10` and `Decimal('٥') == 5`. Pre-existing and deliberate at the helper — `_purchase_unit_price`'s docstring records the leniency, notes that both of its entry points have always behaved this way, and says tightening it would be a new business rule rather than the parity the helper was extracted for. DW-22 did not change that, but it is what puts the two rules on the same card for the first time: before it, the strict field and the lenient one were on different pages. `tests/unit/test_product_routes.py::TestTheFirstReceiptPriceMatchesThePurchaseForm::test_both_forms_accept_and_store_the_same_price` now pins the leniency as intended behaviour, so closing this means deciding the rule deliberately, not discovering it. Closing it means choosing one definition for the whole application — most likely tightening `_purchase_unit_price` for all three of its entry points at once (HTML purchase form, JSON endpoint, create form), which is a contract change for `api_record_purchase` and so cannot be scoped to the create form.
status: open

### DW-187: `_record_first_receipt`'s defensive re-parse can write a Purchase with every column NULL
origin: spec-dw-22-first-receipt-unit-price-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-22-first-receipt-unit-price.md`
location: `app/main/routes.py` (`_record_first_receipt`)
severity: low
summary: The trigger test (`if not any(values.values())`) runs on the RAW strings while the parse that follows discards anything unusable, so a caller reaching this function with a single unusable receipt value — `quantity='abc'`, or now `unit_price='abc'` — records a Purchase whose every column is NULL but the server-defaulted order date, and reports success.
evidence: Found by the edge-case review of DW-22 and reproduced by calling `_record_first_receipt(svc, pid, {'unit_price': 'abc'})` directly: `any(values.values())` is true on the string, both parsed fields come back None, and `record_purchase` writes the empty row. The shape is pre-existing — `{'quantity': 'abc'}` alone has done the same since Story 4.5 — and DW-22 widens it by one field rather than introducing it. Unreachable through the UI: `product_add` is the only caller and `_validate_product_create_form` refuses every one of these before the write, which is why the fallback is documented as being for "a caller that reached here another way". Closing it means deciding what the trigger rule actually is — non-blank raw text, or a value that survived parsing — which is the same question DW-27 opens from the other side, so the two should be settled together.
status: done 2026-07-28
resolution: resolved by sweep bundle dw-purchase-parse-residuals

### DW-188: the user manual quotes the create form's help text verbatim and nothing pins the quotation
origin: spec-dw-22-first-receipt-unit-price-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-22-first-receipt-unit-price.md`
location: `docs/user-manual.md` (the First Receipt Block section), `app/templates/product/add.html` (the `#first-receipt` `form-text`)
severity: low
summary: The manual reproduces the card's help text word for word — a quotation DW-22 grew from one sentence to three clauses — and no test compares the two, so an edit to the template silently falsifies the manual, exactly as DW-20's review found for the identifier card's refusal message.
evidence: Found by the adversarial review of DW-22 and confirmed: `grep -rn "Leave blank to create the product" tests/` returns nothing, and the same run's DW-20 follow-up had already had to correct one stale verbatim quotation in this file. Quoting rendered strings is a deliberate convention of the manual rather than an accident, so the fix is not to stop quoting; it is to make the convention checkable. Closing it means deciding how — a test that asserts the manual's quoted strings appear in the templates and messages they claim to come from, or a generated section — and applying it to the whole manual rather than to this one paragraph, since the same exposure exists for every message table in it.
status: open

### DW-189: `_purchase_unit_price` accepts `-0` and zeros with extreme exponents
origin: spec-dw-22-first-receipt-unit-price-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-22-first-receipt-unit-price.md`
location: `app/main/routes.py` (`_purchase_unit_price`)
severity: low
summary: `-0` passes the "must not be negative" rule (`Decimal('-0') < 0` is False) and `0.00E-99999999999999999` passes the scale rule (it equals its own quantize), so both are accepted and handed to the driver as `Decimal` values whose `str()` is not a shape a MySQL DECIMAL literal takes — unlike the underscore/non-ASCII leniency, neither is among the exceptions the helper's docstring records as deliberate.
evidence: Found by the edge-case review of DW-22 and reproduced through `POST /products/add`: `-0` is accepted, and `0.00E-99999999999999999` is accepted and returned as `Decimal('0E-100000000000000001')`. Both store as `0.00` under SQLite, which is what the unit suite runs on, so nothing here fails today; the MariaDB behaviour is untested. Wholly pre-existing and reachable from all three entry points that write the column — the HTML purchase form and `api_record_purchase` have accepted these since DW-12, and DW-22 only adds a third door to the same room. Closing it means normalizing in the helper (quantize the accepted value before returning it, and decide whether `-0` is a refusal or a zero) so that every caller stores the same number, and covering it in the integration suite where a real DECIMAL column can answer.
status: done 2026-07-28
resolution: resolved by sweep bundle dw-purchase-parse-residuals

### DW-190: the forms' numeric inputs offer no numeric affordance — no `inputmode`, no placeholder, on either receipt surface
origin: spec-dw-22-first-receipt-unit-price-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-dw-22-first-receipt-unit-price.md`
location: `app/templates/product/add.html` (the `#first-receipt` card's `quantity` and `unit_price`), `app/templates/product/purchase_add.html` (`quantity`, `unit_price`)
severity: low
summary: All four numeric inputs on the two purchase-capture surfaces are bare `type="text"` with no `inputmode`, no `placeholder` and no `step`, so a tablet — the plausible device for cataloguing a parcel at the bench — opens an alphabetic keyboard for a digits-only field, and the operator is told the price's format only by help text two fields below the box.
evidence: Found by the adversarial review of DW-22 and confirmed: `grep -rn "inputmode" app/templates/` returns nothing at all, and `grep -rn 'placeholder=' app/templates/product/*.html` shows the convention is already established elsewhere in these very files — `order_date`/`received_date` carry `placeholder="YYYY-MM-DD"` and `category_path`/`tags` carry worked examples — just never on a numeric field. Wholly pre-existing and symmetrical across both surfaces: DW-22 mirrored `purchase_add.html`'s markup exactly as its spec directed, so it added a fourth instance rather than the first. `type="number"` is NOT the fix — it would hand the browser a second, silent opinion about what a price is, on top of the two the application already disagrees about (see DW-186), and would let a browser discard a value the server means to refuse with a message. Closing it means adding `inputmode="numeric"`/`inputmode="decimal"` and a format placeholder to all four inputs in one pass, and deciding whether the price's format guidance belongs in a per-field `form-text` under the control (as `order_date`'s "Defaults to today when left blank." already is) rather than appended to the card-level help text.
status: open

### DW-191: the two purchase entry points disagree about whitespace around a date, so a padded value the form accepts the JSON endpoint refuses
origin: spec-dw-24-received-date-not-before-order-date-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-24-received-date-not-before-order-date.md`
location: `app/main/routes.py` (`_parse_purchase_form` date branch, `api_record_purchase._parse_date`)
severity: medium
summary: `_parse_purchase_form` strips `order_date`/`received_date` before `date.fromisoformat`; `api_record_purchase._parse_date` does not. `{'order_date': ' 2026-01-01 '}` is a 302 and a stored row through the HTML form and a 400 `order_date must be an ISO date` through the JSON endpoint — the same value, opposite verdicts, on the one pair of columns whose parse the two entry points still do not share.
evidence: Found by the adversarial review of DW-24 and reproduced both ways. Wholly pre-existing: neither line changed in this story, which adds only the shared ORDERING rule on top of the two unshared parses. It is a third symptom of DW-88, whose evidence names the ISO-grammar hole and the divergent message wording but not this, and it is the symptom most likely to be missed when DW-88 is closed by fixing the grammar alone. The rest of the purchase surface already settled this question the other way: `api_record_purchase` strips a string `unit_price` before parsing it precisely so padding does not diverge (`_UNIT_PRICE_VERDICTS` pins `('  2.34  ', None)`), and `_purchase_text_length_error` measures the stripped value with a docstring paragraph explaining that measuring the raw one would let the form accept what the endpoint rejects. Closing it belongs with DW-88 — one shared date helper that strips, states the grammar it actually enforces, and carries one message — after which `_DATE_ORDER_VERDICTS` can gain the padded row its comment currently explains the absence of.
status: done 2026-07-28
resolution: resolved by sweep bundle dw-purchase-date-parse-single-home

### DW-192: the purchase form advertises the very blank that defeats DW-24's new ordering rule, so "leave Order Date blank" stores the row the rule just refused
origin: spec-dw-24-received-date-not-before-order-date-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-dw-24-received-date-not-before-order-date.md`
location: `app/templates/product/purchase_add.html` (the `order_date` control's `form-text`), `app/main/routes.py` (`_purchase_date_order_error` and both its call sites), `app/mariadb_catalog_service.py` (`record_purchase`'s `order_date` default)
severity: medium
summary: DW-24 refuses `order_date='2026-07-27'` with `received_date='2020-01-01'`, but the same submission with `order_date` left blank is accepted and `record_purchase` then defaults `order_date` to today — storing byte-for-byte the row the rule just refused, and the form's own help text under the control ("Defaults to today when left blank.") is what tells the operator to do it.
evidence: Found by both reviewers of DW-24 independently and reproduced on both entry points: `POST /api/products/<id>/purchases {"received_date": "2020-01-01"}` returns 201 and stores `order_date=<today>, received_date=2020-01-01`; the HTML form does the same with a 302. The rule is therefore defeated by following the form's printed instructions, and the operator gets no hint that the blank changes the verdict. NOT a deviation: leaving the partial cases untouched is the human's explicit 2026-07-26 decision on DW-24, and `_purchase_date_order_error`'s docstring argues the case for it (refusing a lone past `received_date`, or replicating the service's today-default in the route to compare against, is a wider rule than the one decided). What the decision did not weigh is that `purchase_add.html` markets the bypass: the two halves were decided in different places and only meet at the operator's screen. Closing it is a decision, not a patch — resolve the default's location (leave `order_date` NULL when it was never typed, so the pair is genuinely partial rather than silently completed; or apply the rule against the effective `order_date` the service is about to substitute; or say in the help text that a blank Order Date means today and will be compared as such). It shares the substituted-`order_date` root cause with DW-27, and the "help text describes something other than what happens" shape with the `_RECEIPT_FIELDS` note in DW-27's evidence, so the three are worth settling in one pass.
status: open

### DW-193: a scanned Order Number still books a purchase dated today, so DW-27's fix covers `P` but not `K`
origin: spec-dw-27-purchase-trigger-narrowing-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-27-purchase-trigger-narrowing.md`
location: `app/main/routes.py` (`_RECEIPT_TRIGGER_FIELDS`, `_ecia_prefill`'s `order_number` <- `K`/`1K`), `tests/e2e/test_scan_routing.py` (`TestSavingAScanPrefilledCreateForm`)
severity: medium
summary: DW-27 narrowed the trigger to `quantity`/`order_number`, but `_ecia_prefill` fills `order_number` from the label's `K`/`1K` record, so scanning a distributor bag that carries an order reference, typing a description and saving still writes `Purchase(quantity=NULL, unit_price=NULL, vendor=NULL, order_number='<label K>', order_date=today)` — the DW-27 shape with `K` in place of `P`.
evidence: Found by the adversarial review of DW-27. NOT a deviation: the human's 2026-07-26 decision names this case and accepts it verbatim — "a real receipt (a quantity or an order number, both of which ECIA labels do carry and the operator does confirm) still does" record a Purchase — and `docs/user-manual.md`'s Scanning section now warns about it in as many words. What the decision could not weigh is frequency: real DigiKey/Mouser bag labels carry `1K` considerably more often than they carry nothing but `1P`+`P`, so if the scan-to-catalogue flow is common the narrowing may close the rarer door and leave the commoner one open. The new e2e (`test_a_part_number_only_envelope_saved_records_no_purchase`) deliberately constructs the part-number-only envelope and nothing in any suite submits the `K`-bearing shape, so the residual is unmeasured as well as unfixed. Closing it is a decision, not a patch — either gate the `order_number` pre-fill the way `Q` is already gated, or distinguish scan-supplied from typed values at the trigger, or accept it and measure how often real labels carry `K` without `Q`. Shares the substituted-`order_date` root cause with DW-192.
status: open

### DW-194: the create form drops typed receipt values with no message, while the route already has a mechanism for saying so
origin: spec-dw-27-purchase-trigger-narrowing-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-27-purchase-trigger-narrowing.md`
location: `app/main/routes.py` (`_record_first_receipt`'s early return, `product_add`'s `followup_errors` loop)
severity: medium
summary: Since DW-27, a create form carrying Vendor, Unit Price and Vendor SKU but neither trigger returns `None` before `record_purchase` and the operator sees only "Product created successfully!" — three values they typed are gone, with no flash, no field message and no log line, though `product_add` already collects and flashes non-fatal `followup_errors` for exactly this class of partial outcome.
evidence: Found by both reviewers of DW-27 independently. The silence is the spec's deliberate choice and its Design Notes argue it: making the shape a validation ERROR would recreate DW-27 in mirror image, because `vendor_sku` is the field a scan fills and the operator never typed it. What neither the spec nor the decision weighed is the third option — an advisory flash after a successful save, which is not a refusal and costs the operator nothing. The reason it is not a patch: on a POST the route cannot tell a scan-supplied `vendor_sku` from a typed one (both arrive as ordinary form fields), so an advisory would fire on every scan-and-catalogue save — the dominant flow this change exists to serve — and the noise may cost more than the rare forgotten quantity. Closing it means deciding between accepting the silence, flashing unconditionally, or plumbing "what the query string pre-filled" through the POST so the advisory can fire only on values a human typed. Reachable by typing Vendor=`DigiKey`, Unit Price=`12.50`, Vendor SKU=`296-1234-ND` and forgetting the quantity.
status: open

### DW-195: DW-187's recorded reproducer no longer reproduces — DW-27 closed the price half of the all-NULL Purchase and left the quantity half open
origin: spec-dw-27-purchase-trigger-narrowing-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-dw-27-purchase-trigger-narrowing.md`
location: `app/main/routes.py` (`_record_first_receipt`'s fail-open parse fallback), `_bmad-output/implementation-artifacts/deferred-work.md` (DW-187's evidence)
severity: medium
summary: DW-187 records the fail-open parse hazard — a non-blank receipt field that triggers on its raw string and then parses to `None`, writing a Purchase whose only content is today's date — and its evidence pins the repro as `_record_first_receipt(svc, pid, {'unit_price': 'abc'})`. Since DW-27 that exact call returns `None` before any write, because `unit_price` is no longer a trigger. The hazard is still real but now reaches through `quantity` alone (`{'quantity': 'abc'}`), so whoever picks DW-187 up will run a reproducer that passes and may conclude the entry is stale when half of it is live.
evidence: Found by the second review of DW-27 and confirmed against the code: the guard is now `any(values[name] for name in _RECEIPT_TRIGGER_FIELDS)` with `_RECEIPT_TRIGGER_FIELDS = ('quantity', 'order_number')`, so a form_data carrying only `unit_price` short-circuits at the guard and never reaches `_purchase_unit_price`. DW-187 also states that it "is the same question DW-27 opens from the other side, so the two should be settled together"; DW-27 shipped without narrowing or annotating it. Filed as a NEW entry rather than an edit because the orchestrator owns DW-187's status and resolution. The rewritten comment in `_record_first_receipt` now states the post-DW-27 split accurately (price closed, quantity open) and is the current source of truth; DW-187's own evidence is what is out of date. Closing this means re-scoping DW-187 to the `quantity` path and correcting its reproducer — an edit to an existing entry, which is a decision for whoever owns the ledger.
status: done 2026-07-28
resolution: resolved by sweep bundle dw-purchase-parse-residuals

### DW-196: three MEDIUMBLOB columns lose their variant under a `mariadb+pymysql://` URL, so `create_all` builds them as 64 KB BLOBs
origin: spec-dw-34-pinned-column-collations-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-dw-34-pinned-column-collations.md`
location: `app/database.py:743-744` (`Photo.medium_data`, `Photo.original_data`), `app/database.py:1050` (`Attachment.content`)
severity: medium
summary: All three columns are `LargeBinary().with_variant(MEDIUMBLOB, 'mysql')`, naming only the `mysql` dialect. SQLAlchemy resolves `with_variant()` on `dialect.name`, which is `mariadb` for a `mariadb+pymysql://` URL, so under that perfectly valid scheme `Base.metadata.create_all` emits plain `BLOB` (65,535 bytes) instead of `MEDIUMBLOB` (16 MB) — silently capping photo and attachment storage at 64 KB.
evidence: Found by the follow-up review of DW-34 and confirmed empirically by compiling `CreateTable(Photo.__table__)` against both dialects: `mysql` renders `medium_data MEDIUMBLOB NOT NULL`, `mariadb` renders `medium_data BLOB NOT NULL`. Pre-existing (the lines are untouched by DW-34's diff) and surfaced only because DW-34 documents this exact single-dialect failure mode five times over and fixes it for `Product.internal_id` alone, via `with_variant(..., 'mysql', 'mariadb')`. Production is NOT currently affected: the deployed schema is built by the Alembic chain, and `dce1254cd381` issues an explicit `MODIFY COLUMN ... MEDIUMBLOB`. The exposure is the `create_all` path — the integration tier's `integration_schema` fixture and any deployment bootstrapped without migrations. The one-line fix is to add `'mariadb'` to each of the three variants; it is filed rather than patched because it is outside DW-34's intent contract ("do not add a collation to BLOB/`MEDIUMBLOB` ... columns") and because `tests/unit/test_database_schema.py::test_internal_id_is_the_only_column_that_overrides_the_table_collation` already walks every column under both server dialects, so the guard that would prove the fix wants extending to column TYPE rather than just to `COLLATE`.
status: open

### DW-197: the Alembic chain as a whole cannot run in offline/`--sql` mode, so "generate the SQL and hand it to a DBA" has never worked
origin: spec-dw-34-pinned-column-collations-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-34-pinned-column-collations.md`
location: `migrations/versions/8213852b0b94_*.py`, `56dc95692b79_*.py`, `f8e66632ee42_*.py`, `5aeb89e22451_*.py`
severity: low
summary: Four revisions read or write rows through `op.get_bind()`, which has no live connection under `alembic upgrade --sql`. The chain therefore cannot be rendered to a script for out-of-band review or execution, and the failures are incidental (a `TypeError` or an empty result set) rather than an explicit refusal.
evidence: Deferred by the first review pass of DW-34 and carried forward per that pass's note. Pre-existing and independent of DW-34, which only made its own revision (`a977ca7315df`) refuse offline mode explicitly rather than adding a fifth silent failure — verified: `command.upgrade(cfg, '68707d1f48bf:a977ca7315df', sql=True)` now raises a `RuntimeError` naming the reason. Closing this means either giving the four data-migration revisions an explicit offline refusal of their own (cheap, honest, and consistent with `a977ca7315df`) or deciding that offline mode is unsupported for this project and saying so once, in `migrations/env.py`, instead of four times.
status: open

### DW-198: Follow-up review still recommended for dw-decision-dw-34 after the damping cap was spent
origin: review-budget-followup
source_spec: `spec-dw-34-pinned-column-collations.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260726-064033-76c4; this entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-199: the audit log files every catalog operation's `input` phase under a different name than its `success`/`error`, so no operation's lifecycle can be grepped as one
origin: spec-dw-48-tag-rename-and-merge-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-dw-48-tag-rename-and-merge.md`
location: `app/main/routes.py` (route-side `log_audit_operation(..., 'input', ...)` calls), `app/mariadb_catalog_service.py` (service-side `'success'`/`'error'` calls)
severity: low
summary: Every catalog route logs the `input` phase under the ROUTE's name while the service logs `success` and `error` under the SERVICE METHOD's name, so the two halves of one operation never share an `audit_operation` value. Grepping the audit log for either name returns half the lifecycle, and the `item_id` cannot rejoin them because the input record carries no `item_id` at all.
evidence: Surfaced by the DW-48 follow-up review, which found `tag_rename`/`rename_tag` and then confirmed the split is systemic rather than a slip in the new code: `product_add`/`create_product`, `product_edit`/`update_product`, `purchase_add`/`record_purchase` and `category_rename`/`rename_category_path` all pair the same way (verified by enumerating the `log_audit_operation` call sites in both files). It is pre-existing and was propagated, not introduced, by DW-48 — the new page mirrors `category_rename` exactly, which is why the review did not patch it here: fixing one pair alone would make the tag page the only member of the family that joins, which is worse than a consistent split. `app/logging_config.py:415` states the point of the audit trail is "to enable data reconstruction", which is precisely what the split defeats. Closing this means picking one naming side for the whole surface (the service method's name is the better anchor, since it is what the `success`/`error` records and the `item_id` already key on) and moving every route-side `input` call onto it in one pass.
status: open

### DW-200: an all-zero GTIN identifier already stored in a deployed database becomes unreachable by lookup and unrecreatable
origin: spec-dw-69-gtin-all-zero-refusal-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-69-gtin-all-zero-refusal.md`
location: `app/mariadb_catalog_service.py` (`find_product_id_by_gtin`), `product_identifiers` table
severity: medium
summary: Before DW-69, `add_identifier` accepted `'00000000'` and stored it as the validated `GTIN` value `'00000000000000'`. Such a row survives the change but can no longer be resolved: `find_product_id_by_gtin` now returns `None` for every all-zero input, and the value can never be re-entered as a `GTIN`. The row is findable only by the `product_identifiers.value` substring arm of `search_products` — an accident, not a designed fallback — and it still occupies the identifier uniqueness index.
evidence: Found by the DW-69 review. The DW-69 spec's Block If named "any existing product identifier row in a fixture, migration, or seed"; fixtures, migrations and seeds are clean (verified), but the population actually at risk is the deployed database, which the Block If never named. Confirmed by reading `find_product_id_by_gtin` (`normalize_gtin` inside a `try`, `InvalidGtinError` → `None`) — the new refusal reaches it with no code change. The human decision behind DW-69 accepted the write-path consequence explicitly ("an all-zero GTIN can no longer be stored as a validated identifier - which is the intended consequence") but did not address pre-existing rows. Closing this means running a detection query — `SELECT id, product_id FROM product_identifiers WHERE identifier_type = 'GTIN' AND value = '00000000000000'` — and deciding per row between deletion and re-typing as `GTIN_UNVALIDATED` (which still accepts the value verbatim, pinned by `test_the_quarantine_type_also_takes_the_wedge_no_read`). Not patched under DW-69 because a data migration is outside its intent contract and the right disposition is a human call.
status: open

### DW-201: the free-text search for an all-zero no-read substring-matches real GTIN keys
origin: spec-dw-69-gtin-all-zero-refusal-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-69-gtin-all-zero-refusal.md`
location: `app/mariadb_catalog_service.py` (`search_products`, the `product_identifiers.value` LIKE arm), `app/utils/scan_router.py` (rule 4)
severity: medium
summary: DW-69 routes the wedge no-read to `free_text`, which is the intended outcome, but `search_products` then runs `LIKE '%00000000%'` against identifier values. Every GTIN-8 stored in the catalog normalizes to a 14-digit key with six leading zeros, so a no-read can return a list of unrelated products as apparent scan hits — presented to the operator as if the failed scan matched something.
evidence: Found by the DW-69 edge-case review. The zero-padding to 14 is `gtin.py`'s documented invariant, so the collision is structural rather than incidental: `'00000000'` is a substring of `'00000000012348'`, the canonical key for the GTIN-8 `'00012348'` already used as a test vector. Not patched under DW-69, whose intent contract forbids zero-run logic in the service and router ("Do not add zero-run logic to `app/utils/scan_router.py`, `app/mariadb_catalog_service.py`, or `app/main/routes.py`"). Closing this means deciding whether a no-read should short-circuit to an empty hit set before the search runs, or whether misleading hits are acceptable given the operator can see the query. Related to [DW-202].
status: open

### DW-202: a failed scan pre-fills the create form's required `description` with the no-read text
origin: spec-dw-69-gtin-all-zero-refusal-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-69-gtin-all-zero-refusal.md`
location: `app/main/routes.py` (the `free_text` create pre-fill)
severity: low
summary: Post-DW-69 a wedge no-read routes to `free_text` and, matching nothing, lands on `/products/add?description=00000000`. That is a strict improvement over the pre-DW-69 outcome (a create form carrying `identifier_type=GTIN, identifier_value=00000000000000`), but the operator can still save a product whose description is a failed scan, in the one field the form requires.
evidence: Found by the DW-69 edge-case review and pinned as current behavior by `test_the_wedge_no_read_is_not_routed_as_a_trade_item_number` in `tests/unit/test_scan_routes.py`, which asserts `_query(url) == {'description': '00000000'}`. The pre-fill is Story 4.5's general free-text rule and is correct for genuine free text; the question is whether a recognizable no-read deserves an exception. Not patched under DW-69 (routes are out of its intent contract). Related to [DW-201].
status: open

### DW-203: the `GTIN_UNVALIDATED` advisory says "without check-digit validation" for refusals that are not check-digit failures
origin: spec-dw-69-gtin-all-zero-refusal-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-69-gtin-all-zero-refusal.md`
location: `app/mariadb_catalog_service.py` (`add_identifier`'s `ValidationError` message), `app/main/routes.py` (`_validate_product_create_form`)
severity: low
summary: Every GTIN refusal is shown to the operator as the util's message plus a fixed clause: "Choose the GTIN_UNVALIDATED type to keep the value exactly as entered, without check-digit validation." Four of the five refusal reasons are not check-digit failures, and the all-zero one actively contradicts the clause — `'00000000'` passes mod-10 and is refused for a different reason, so the operator is told to bypass a check that did not fire.
evidence: Pre-existing (the clause was already loose for the non-digit, wrong-length and non-`str` reasons) and surfaced by DW-69, which adds a fifth reason where the mismatch is not merely loose but false. The exact concatenation is asserted byte-for-byte by nine rows of `tests/unit/test_product_routes.py::TestGtinCheckDigitRefusedBeforeTheWrite::test_every_way_the_util_refuses_a_gtin_is_refused_here`, so rewording is a coordinated change across the service, the route and that table — too broad to patch inside DW-69's contract. Closing this means restating the clause in terms of what `GTIN_UNVALIDATED` actually does (holds the value verbatim, unvalidated) rather than naming one of the five checks it skips.
status: open

### DW-204: an all-zero part number inside an ECIA envelope pre-fills `mpn` and can be stored as an identifier, which the GTIN rule cannot reach
origin: spec-dw-69-gtin-all-zero-refusal-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-dw-69-gtin-all-zero-refusal.md`
location: `app/main/routes.py` (`_ecia_prefill` / `_scan_create_prefill`), `app/utils/ecia.py`
severity: medium
summary: DW-69 keeps a wedge no-read out of the GTIN namespace, but the same no-read arriving as the `1P`/`P` part-number field of an ECIA envelope still pre-fills `mpn` on the create form and can be saved as an `MPN` identifier. The rule that a failed scan must not become a trade identifier holds for one scan path and not the other.
evidence: Found by the DW-69 adversarial and edge-case review passes. `_scan_create_prefill` returns `_ecia_prefill(classification)` whenever it yields a non-blank `mpn`, and `mpn` is set from the first non-blank of `1P`/`P` with no value-level judgement — MPNs are deliberately not check-digit or format validated (`test_a_non_gtin_type_is_not_check_digit_judged` pins that only the `GTIN` branch is normalized). So `[)>{RS}06{GS}1P00000000{GS}{RS}{EOT}` pre-fills `mpn=00000000` and a save stores it. Not patched under DW-69, whose intent contract confines the rule to `app/utils/gtin.py` ("Do not add zero-run logic to `app/utils/scan_router.py`, `app/mariadb_catalog_service.py`, or `app/main/routes.py`") and forbids broadening it beyond GTINs. Closing this means deciding whether "is this field a scanner no-read" is a question the ECIA prefill should ask at all, and if so where it lives given AD-16 keeps per-namespace validity behind its own util. Related to [DW-202].
status: open

### DW-205: the GTIN fallthrough searches the raw scan, so an AI-01 miss searches an element string no column can hold
origin: spec-dw-70-ai-01-element-string-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-70-ai-01-element-string.md`
location: `app/mariadb_catalog_service.py` (`_fallthrough_text`), `app/utils/scan_router.py` (FR36 rules 3-4)
severity: medium
summary: `_fallthrough_text` returns the AIM-stripped RAW scan for a `gtin` classification. Since DW-70 that raw scan may be a whole GS1 element string — `'0109506000134352\x1d10LOT42'`, separators included — so an AI-01 scan whose GTIN misses the catalog issues a `LIKE` on a string no column holds and is guaranteed to return nothing, where the bare form of the same number could still substring-match a `GTIN_UNVALIDATED` row.
evidence: Found by the DW-70 review passes and confirmed by reading `_fallthrough_text` (`app/mariadb_catalog_service.py:259-306`), whose docstring justifies searching the scanned form because "the scanned form can substring-match a `GTIN_UNVALIDATED` row stored exactly as it was typed" — a rationale that holds for a typed number and not for an element string. Not a regression: an AI-01 scan classified `free_text` before DW-70 and reached the same text through the same helper, so the searched string is byte-identical to `28bff4a`. What DW-70 changes is that the spec now claims an AI-01 scan "is handled by the code path a bare GTIN already used", which is true of the lookup arm and NOT of the fallthrough. Not patched under DW-70, whose intent contract holds `app/mariadb_catalog_service.py` read-only and whose whole design claim is that no service change is needed. Closing this means deciding whether the `gtin` fallthrough should search the value the classifier extracted (available as `normalized_value`, or as a re-run of `gs1.decode_trade_item_number`) instead of the raw scan — which touches every `gtin` miss, not only the AI-01 ones. Related to [DW-70].
status: open

### DW-206: the separator asymmetry now splits a single scan kind, not only two different kinds
origin: spec-dw-70-ai-01-element-string-review-1
source_spec: `_bmad-output/implementation-artifacts/spec-dw-70-ai-01-element-string.md`
location: `app/utils/scan_router.py` (module docstring, `classify`), `app/utils/gs1.py`, `app/utils/scan_input.py` (`clean_scan_input`)
severity: low
summary: `gs1`'s recognizers open with `raw.strip()`, which eats `\x1c`-`\x1f`, while `clean_scan_input` deliberately preserves separators. Before DW-70 that split `internal` (tolerant) from `ecia`/`gtin` (strict). Now it splits the `gtin` kind against itself: `classify('\x1d0109506000134352')` is `GTIN` while `classify('\x1d9506000134352')` is `FREE_TEXT`, for the same product on the same box.
evidence: Verified on this checkout, and pinned in both directions by `TestWhitespaceAsymmetryBetweenRules` in `tests/unit/test_scan_router.py`. The underlying asymmetry is already an open concern aimed at the story that owns the caller seam; DW-70 widened rather than narrowed it, and the module docstring now presents the widening as a benefit ("a GS-framed manufacturer barcode routes correctly where a GS-framed envelope does not") without recording that one kind became internally inconsistent. Not patched under DW-70: absorbing separators in `scan_router` would be the third copy of the trim rule it refuses to own, and stripping them in `clean_scan_input` would destroy the envelope structure that cleaner exists to protect — the same two blocked fixes the original entry names. Closing this means deciding the caller-seam transmission contract once, for all four kinds. Has never been observed on the deployed Tera HW0009, which emits no separator prefix.
status: open

### DW-207: the `gs1`-delegated rules tolerate only Python's whitespace set, so a wedge programmed with a non-whitespace suffix refuses every element-string scan
origin: spec-dw-70-ai-01-element-string-review-3
source_spec: `_bmad-output/implementation-artifacts/spec-dw-70-ai-01-element-string.md`
location: `app/utils/gs1.py` (`decode`, `decode_trade_item_number`), `app/utils/scan_input.py` (`clean_scan_input`)
severity: low
summary: Both `gs1` recognizers open with `raw.strip()`, so their transmission tolerance is exactly `str.isspace()`'s character set and nothing else. A scanner programmed with a suffix outside that set — EOT (`\x04`), `#`, `*`, `$`, DEL — turns every internal label and every manufacturer AI-01 barcode into a free-text search, while the same unit programmed with VT (`\x0b`) or CR/LF works.
evidence: Verified on this checkout: `classify('0109506000134352\x0b')` returns `gtin 09506000134352` and `classify('0109506000134352\x04')` returns `free_text`, the difference being solely that Python counts VT as whitespace and EOT not. Pre-existing rather than caused by DW-70 — `decode` has carried the same `raw.strip()` preamble since Story 2.4, so rule 1 has always had this cliff and DW-70 gave rule 3 the same one by mirroring it deliberately. What makes it worth recording is that `app/utils/scan_input.py`'s docstring names EOT and VT together as bytes that survive `clean_scan_input` and explicitly anticipates "a scanner programmed with VT as its suffix", so the codebase already knows programmed suffixes arrive — and the two recognizers then split those two bytes apart with no statement anywhere that the dividing line is Python's whitespace table rather than a decision about wedges. Not patched under DW-70, whose contract fixes rule 3's tolerance as "mirrors `gs1.decode` exactly" and forbids widening it on one rule alone. Closing this means deciding the caller-seam suffix contract once — most likely by having `clean_scan_input` strip a configured/known suffix set before `classify` sees it, rather than by widening `strip()` inside the grammar module. Related to [DW-206], which is the same seam seen from the prefix side.
status: open

### DW-208: Follow-up review still recommended for dw-decision-dw-70 after the damping cap was spent
origin: review-budget-followup
source_spec: `spec-dw-70-ai-01-element-string.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260726-064033-76c4; this entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-209: the legacy JSON routes still answer a non-object body with a generic 500, the DW-90 shape outside AD-13
origin: spec-json-purchase-endpoint-hardening-review
source_spec: `_bmad-output/implementation-artifacts/spec-json-purchase-endpoint-hardening.md`
location: `app/main/routes.py` (`validate_type_shape` :4014, `print_label` :4394, `api_admin_export` :5008, and the other `request.get_json() or {}` readers at :3389, :4157, :4550, :4607, :5193, :5553; `app/admin/routes.py` :114, :163)
severity: low
summary: DW-90 closed the non-object-body hole on `api_record_purchase` and ended by saying the same guard "is likely wanted on every AD-13 endpoint that reads a JSON body rather than on this one alone". Every AD-13 endpoint is now covered, but roughly a dozen legacy inventory/admin JSON routes still read `request.get_json() or {}` and then `data.get(...)`, so a JSON array or non-empty scalar body raises `AttributeError` into the surrounding `except Exception` and comes back as a generic 500 rather than a 400 naming what was wrong.
evidence: Verified on this checkout while closing DW-90. The three AD-13 readers are all guarded: `api_record_purchase` now refuses a non-dict (this spec), `api_scan` coerces to `{}` because an absent `raw` is a refusal one line later (`app/main/routes.py:2748`), and `/api/inventory/items` refuses inside `_normalize_json_item_payload` (`app/main/routes.py:471`, `raise ValueError('Request body must be a JSON object')`) — so DW-90's own recommendation is satisfied for the family it named. The legacy routes are a different family with the same defect: `data = request.get_json() or {}` followed by `data.get(...)`, where `[1, 2] or {}` is `[1, 2]`. They are outside AD-13 (string `error`, not the object envelope), which is why this is a separate entry rather than part of DW-90 — closing it means deciding whether those routes get a shared body-shape guard and what envelope its refusal uses, which is a question about the legacy surface, not about purchases.
status: open

### DW-210: the architecture spine still prescribes `request.get_json() or {}`, which the purchase endpoint no longer does
origin: spec-json-purchase-endpoint-hardening-review
source_spec: `_bmad-output/implementation-artifacts/spec-json-purchase-endpoint-hardening.md`
location: `_bmad-output/planning-artifacts/architecture/architecture-workshop-inventory-tracking-2026-07-22/ARCHITECTURE-SPINE.md` ("API success" row, line 152)
severity: low
summary: The spine's Consistency Conventions table gives the body-reading convention for JSON routes as "body via `request.get_json() or {}`". DW-90 required exactly that expression to be replaced on `api_record_purchase`, so the spine now describes something one shipped endpoint deliberately does not do, and a future endpoint written from the spine inherits the hole DW-90 closed.
evidence: Read on this checkout at ARCHITECTURE-SPINE.md line 152, alongside the "API errors" row (153) the same endpoint does honor. The conflict is real but narrow: `or {}` is a safe shorthand wherever an empty body is already a refusal (`api_scan`), and unsafe only where every field is optional so `{}` is itself a valid write — which is the case the spine does not distinguish. Not amended under this spec, whose scope is one route: the spine governs every future JSON endpoint, so restating the convention is an architecture decision (probably "decode, then refuse a non-object; `or {}` only where an empty body cannot write") rather than a side effect of a bugfix. The reason for the departure is recorded in the code at `app/main/routes.py:2079` so a reader of either artifact can find the other. Related to [DW-209].
status: open

### DW-211: a whitespace-only `quantity` is refused on the JSON endpoint while a whitespace-only `unit_price` means "no price"
origin: spec-json-purchase-endpoint-hardening-review
source_spec: `_bmad-output/implementation-artifacts/spec-json-purchase-endpoint-hardening.md`
location: `app/main/routes.py` (`api_record_purchase`, the `quantity` parse against the `unit_price` strip six lines above it)
severity: low
summary: `api_record_purchase` strips a string `unit_price` before its `None`/`''` gate, so `{"unit_price": "  "}` records a purchase with no price. The `quantity` parse has no such strip and tests `quantity not in (None, '')` against the raw value, so `{"quantity": "  "}` reaches `int('  ')` and answers 400 "quantity must be an integer" — while the HTML form strips both and treats a blank quantity as no quantity.
evidence: Verified on this checkout: `{"quantity": "  "}` -> 400, `{"unit_price": "  "}` -> 201 with a NULL price. Pre-existing and unchanged in kind by this spec — `int('  ')` raised `ValueError` into the same refusal before the bound was added; only the neighbouring code moved. The `unit_price` strip was added deliberately by the json-purchase-bounds-parity follow-up review ("a whitespace-only price means 'no price' as it does on the form"), and the same argument applies verbatim to `quantity`; it was not applied because that bundle's contract put `quantity` on its Never list, and this bundle's contract scopes the `quantity` work to bounding the parsed int. Closing it is a one-line strip of a string `quantity` before the emptiness gate, and it is worth doing with DW-88's shared date parse, since the dates have the same untrimmed gate. Related to [DW-86], [DW-89].
status: open

### DW-212: a deeply nested JSON body raises RecursionError straight past `get_json(silent=True)` into a generic 500, on every JSON route
origin: spec-json-purchase-endpoint-hardening-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-json-purchase-endpoint-hardening.md`
location: `app/main/routes.py` (every `request.get_json(...)` reader, including `api_record_purchase` :2117, `api_scan` :2760, `_normalize_json_item_payload`'s callers, and the legacy readers DW-209 lists); `app/admin/routes.py` :114, :163
severity: medium
summary: `silent=True` suppresses only the decoder's `ValueError`/`BadRequest`. CPython's JSON scanner recurses per nesting level, so a body of a few hundred KB of nested brackets raises `RecursionError` out of `get_json` itself — before any route code runs — and escapes as the generic 500 shape rather than the AD-13 envelope, on routes that are `@csrf.exempt` and unthrottled.
evidence: Reproduced on this checkout against a live app built like `tests/conftest.py`: `POST /api/products/1/purchases` with `'{"a":' * 100000 + '1' + '}' * 100000` (600,001 bytes, i.e. under the 1 MiB `MAX_REQUEST_BODY_BYTES` cap that `app/request_limits.py` enforces at the WSGI layer) raises `RecursionError` out of `request.get_json(silent=True)`; the same body at depth 20000 answers 201. Pre-existing and unchanged in kind by this spec — the shipped `request.get_json(silent=True) or {}` raised in exactly the same place, and the new `isinstance` guard sits one line later, so it never sees the body. Not this route's problem to solve alone: the fix is either a nesting-depth or a smaller body bound applied where `get_json` is called across the app, or catching `RecursionError` alongside the decode, and choosing between them is a question about the whole JSON surface. Related to [DW-209], [DW-90].
status: open

### DW-213: `_positive_int_string`'s comment names `sys.int_info.str_digits_check_threshold` for a limit that constant does not hold
origin: spec-json-purchase-endpoint-hardening-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-json-purchase-endpoint-hardening.md`
location: `app/main/routes.py:841-844` (the comment inside `_positive_int_string`)
severity: low
summary: The comment says "CPython refuses to parse one longer than `sys.int_info.str_digits_check_threshold` (4300)". That constant is 640 — the floor `sys.set_int_max_str_digits()` will accept, not the parse limit. The limit the code is actually describing is `sys.get_int_max_str_digits()` / `sys.int_info.default_max_str_digits`, which is 4300 only by default and is settable per process.
evidence: Measured on this checkout: `sys.int_info.str_digits_check_threshold` is 640, `sys.int_info.default_max_str_digits` and `sys.get_int_max_str_digits()` are both 4300. The guard the comment defends is correct — `len(digits) > len(str(_MAX_INT32))` returns None long before any parse limit matters — so this is a wrong citation, not a wrong bound, which is why it is low. Not fixed under this spec: its intent contract's Never list forbids touching `_positive_int_string`. The two copies this spec's own change introduced were corrected in place (`app/main/routes.py`'s body-shape comment and the test docstring both now cite `sys.get_int_max_str_digits()`), and both note the form helper's misnaming so the surviving copy is discoverable from either. Related to [DW-86].
status: open

### DW-214: a purchase date before 1000-01-01 is accepted by both entry points and cannot be stored by MariaDB, and the SQLite unit suite pins it green
origin: spec-purchase-date-parse-single-home-review
source_spec: `_bmad-output/implementation-artifacts/spec-purchase-date-parse-single-home.md`
location: `app/main/routes.py` (`_purchase_date`, the round-trip comparison); `tests/unit/test_product_routes.py` (`_DATE_FORMAT_VERDICTS`, the `('0999-01-01', 'stored')` row)
severity: medium
summary: `_purchase_date` states the `YYYY-MM-DD` grammar but not the column's RANGE. MariaDB's supported `DATE` range begins at `1000-01-01`, so `{"order_date": "0999-01-01"}` — and `'0001-01-01'` — answers 201 under the SQLite unit suite and is a generic `server_error` 500 naming no field against a real backend: the DW-25 symptom DW-86 claims every other column on this endpoint no longer has.
evidence: `date.fromisoformat('0999-01-01').isoformat()` is `'0999-01-01'`, so the round-trip rule admits it, and the value was admitted before this change too — the defect is pre-existing and the shared parse neither caused nor widened it. What this story DID do is pin it: `_DATE_FORMAT_VERDICTS` now carries `('0999-01-01', 'stored')` for both columns and both entry points, turning an unverified deferral into a green guarantee, which is why it is recorded rather than left implicit (the row now carries a comment saying the same). Deliberately not fixed here: the intent contract scopes this story to the FORMAT parity between the two entry points, and `_purchase_date`'s docstring argues that narrowing the range would be a new business rule — the identical argument `_purchase_unit_price` makes for `Decimal`'s lenience (DW-89). It is the same class as the two column bounds that WERE stated for exactly this reason (`_MAX_UNIT_PRICE` and the `quantity` 32-bit ceiling, DW-86), both added because "the unit suite runs on SQLite, which widens silently, so a green suite proves less than it appears to". Closing it is a `1000 <= parsed.year <= 9999` check inside `_purchase_date` plus a row in the table, and it should be decided together with whether either purchase entry point gets any integration coverage against a real MariaDB — today neither does. Related to [DW-86], [DW-89], [DW-25].
status: open

### DW-215: the JSON purchase endpoint has no reference documentation, so a breaking change to its shipped contract had nothing to update
origin: spec-purchase-date-parse-single-home-review
source_spec: `_bmad-output/implementation-artifacts/spec-purchase-date-parse-single-home.md`
location: `docs/` (no file documents `POST /api/products/<id>/purchases`); `app/main/routes.py` (`api_record_purchase` docstring, the only record)
severity: low
summary: `docs/user-manual.md` documents the HTML purchase form's messages and needed no edit for this change, but `grep -rn 'api/products' docs/` finds nothing: the JSON endpoint is undocumented outside its route docstring. This story changed its shipped date refusal from `'order_date must be an ISO date (YYYY-MM-DD)'` to `'Order Date must be an ISO date (YYYY-MM-DD).'` and flipped the verdict on four input classes, with no document to carry the change to a caller.
evidence: Verified on this checkout: the two date refusal strings changed, `{"order_date": 20260101}`, `{"order_date": "20260101"}` and `{"order_date": "2026-W01-1"}` went 201 -> 400, and `{"order_date": "   "}` went 400 -> 201 (recording a purchase dated today). `app/api_client.py` (`ApiClient.record_purchase`) forwards a caller's dict verbatim, so an integration is affected without changing a line. All four flips are the defect being closed rather than a contract regression — DW-88 and DW-191 argue exactly that — which is why this is filed against the DOCUMENTATION gap and not against the change. Not this story's to fix: writing the endpoint's first reference doc is wider than a parity bugfix and belongs with the other AD-13 JSON routes (`api_scan`, the legacy readers DW-209 lists), which are undocumented in the same way. Related to [DW-88], [DW-191], [DW-209].
status: open

### DW-216: DW-214's premise is false — MariaDB does not enforce the `1000-01-01` floor its `DATE` documentation names, so there is no 500 to guard
origin: spec-purchase-date-parse-single-home-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-purchase-date-parse-single-home.md`
location: `_bmad-output/implementation-artifacts/deferred-work.md` (DW-214); previously `app/main/routes.py` (`_purchase_date` docstring) and `tests/unit/test_product_routes.py` (the `('0999-01-01', 'stored')` comment), both corrected in this pass
severity: medium
summary: DW-214 says a purchase date before `1000-01-01` "cannot be stored by MariaDB" and is "a generic `server_error` 500 naming no field against a real backend", and proposes a `1000 <= parsed.year <= 9999` check. That is wrong. MariaDB's `1000-01-01` floor is the range its `DATE` type is DOCUMENTED to support, not one it enforces, so the proposed fix would refuse values the database stores and turn a working input into a refusal.
evidence: Measured directly against `mariadb:11.8` with the default `sql_mode` (`STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION`): `CREATE TABLE d (x DATE); INSERT INTO d VALUES ('0999-01-01'),('0001-01-01'),('1000-01-01')` succeeds with no error and `SHOW WARNINGS` empty, and all three round-trip unchanged on `SELECT`. This matches the upstream wording, which says the range is what is supported rather than what is validated. The two copies of the false claim that this story's own change introduced were corrected in place in this pass — `_purchase_date`'s docstring and the `_DATE_FORMAT_VERDICTS` row comment now say the floor is documented and not enforced, and cite the measurement — so the surviving copy is DW-214 itself, which this entry exists to flag rather than rewrite. What remains genuinely open from DW-214 is only its last clause and it is worth keeping: neither purchase entry point has any integration coverage against a real MariaDB, which is why a claim about backend behaviour could sit unfalsified in three files at once. Related to [DW-214], [DW-86], [DW-25].
status: open

### DW-217: `_PURCHASE_DATE_LABELS` reads as an extension point but a third date column would drift across three places, silently on one path
origin: spec-purchase-date-parse-single-home-followup-review
source_spec: `_bmad-output/implementation-artifacts/spec-purchase-date-parse-single-home.md`
location: `app/main/routes.py` — `_PURCHASE_DATE_LABELS` (:1843), `_PURCHASE_FORM_FIELDS` (:1723), the `record_purchase` call in `api_record_purchase` and the `**values` call in `purchase_add`
severity: low
summary: Both entry points now loop `_PURCHASE_DATE_LABELS` to PARSE, but neither uses it to WRITE or RENDER. Adding a third date column to the mapping gets it parsed by both routes and then dropped by the JSON route, whose `record_purchase` call names `order_date` and `received_date` individually; on the form path the same addition puts an unexpected key into `values`, and `service.record_purchase(product_id, **values)` raises `TypeError` into `purchase_add`'s blanket `except Exception`, which becomes a generic "Failed to record the purchase" flash naming nothing. Pre-fill and render read `_PURCHASE_FORM_FIELDS`, a third independent list of the same names.
evidence: Confirmed by reading the two call sites on this checkout: `api_record_purchase` destructures the loop's result into `order_date`/`received_date` and passes them as explicit kwargs, and `record_purchase`'s signature accepts only those two, so `**values` with a third key is a `TypeError`. The mapping's own comment used to claim the loop prevented exactly this divergence; it was corrected in this pass to say what the loop actually buys (the same set of columns judged by the same rule on both sides) and to name all three places an addition must touch, so the code no longer overstates itself. Filed rather than fixed because the fix is a choice, not a correction: either forward `**dates` and let both paths fail loudly, or derive `_PURCHASE_FORM_FIELDS` from the mapping, or accept three lists and keep the comment honest — and no third date column is planned, which is why this is low. Related to [DW-88], [DW-191].
status: open

### DW-218: `order_number` is a receipt trigger with no storability rule of its own, so an over-long one triggers a Purchase MariaDB then refuses whole
origin: spec-purchase-parse-residuals-review
source_spec: `_bmad-output/implementation-artifacts/spec-purchase-parse-residuals.md`
location: `app/main/routes.py` (`_record_first_receipt`'s guard and its `order_number=parsed['order_number'] or None`)
severity: medium
summary: DW-187 was closed by making the trigger test the value AS PARSED rather than as typed, but only `quantity` has a parse — `order_number`'s stripped string IS its parsed form, and its one storability rule (the 255-character column) lives solely in `_validate_product_create_form`. A caller reaching `_record_first_receipt` with a 256-character `order_number` therefore still triggers on a value that cannot be stored: `record_purchase` swallows the `DataError` into `None` and the operator is told "The product was saved, but its first receipt was not recorded", losing the vendor, quantity and price that were on the same receipt.
evidence: Found by the edge-case review of this story and confirmed against the code: the guard is `all(parsed[name] in (None, '') for name in _RECEIPT_TRIGGER_FIELDS)` over a `parsed` dict that puts only `quantity` and `unit_price` through a helper, so a long `order_number` is truthy, fires the guard and reaches the write unchecked. Invisible to the unit tier by construction — SQLite does not enforce `String(255)`, so the value is simply stored and no test can see it — and the new integration file does not cover it. Reachability is the same class DW-187 had: `product_add` is the only caller today and `_validate_product_create_form` refuses the length first, which is exactly why the new test class exists ("`product_add` is not the only caller it could ever have"). Deliberately not fixed here: the intent contract for this story states that `order_number` has no parse and that its stripped string is its parsed form, so giving it one is a scope decision rather than a correction. Closing it means either putting the length rule where the trigger is judged or accepting that the trigger set's storability guarantee covers only the fields that have a parse — and saying which in the comment that now claims the guard tests parsed values. Related to [DW-187], [DW-27], [DW-193].
status: open

### DW-219: `Purchase.to_dict` renders `unit_price` with `float()`, discarding the one-number-one-spelling discipline the write path just gained
origin: spec-purchase-parse-residuals-review
source_spec: `_bmad-output/implementation-artifacts/spec-purchase-parse-residuals.md`
location: `app/database.py:1019` (`Purchase.to_dict`); consumed by `api_record_purchase`'s 201 body and every other reader of the snapshot
severity: low
summary: The write path now guarantees a two-place `Decimal` reaches the column, but the READ path hands it back as a binary float — `float(self.unit_price)`, on a column whose own comment says "Decimal money, never float". Every JSON consumer of a purchase therefore receives a value that is not the stored number but the nearest double to it, which is the exact conversion `app/models.py`'s Decimal rule exists to prevent.
evidence: Wholly pre-existing and not caused by this change — `to_dict` has rendered the column this way since Story 1.2 — but surfaced by it, because this story's whole subject is which spelling of a number survives to the other side, and this is where the answer stops being controlled. Harmless for the values the column can hold (two decimal places under `99999999.99` are exactly representable as doubles, so no value round-trips wrong today), which is why it is low rather than a data defect. The one behaviour this story DID change through it is pinned: `float(Decimal('-0.00'))` is `-0.0`, so the 201 body used to echo a negative zero for `unit_price: "-0"` and now echoes `0.0` (`TestANegativeZeroPriceIsEchoedAsAZero`). Closing it means deciding what the JSON contract for money is — a string, or a number — which is a contract decision for the AD-13 endpoints as a set and belongs with DW-215's undocumented-endpoint problem rather than with a parse bugfix. Related to [DW-215], [DW-89].
status: open

### DW-220: one price rule, two hand-maintained refusal tables — the create form's and the other two entry points'
origin: spec-purchase-parse-residuals-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-purchase-parse-residuals.md`
location: `tests/unit/test_product_routes.py` (`_UNSTORABLE_PRICES` and the refused half of `_UNIT_PRICE_VERDICTS`)
severity: low
summary: All three entry points share `_purchase_unit_price`, but the tests that pin what it REFUSES are two independent literal lists — `_UNSTORABLE_PRICES` for the create form, `_UNIT_PRICE_VERDICTS` for the purchase form and the JSON endpoint — so a refusal covered on one surface may be covered on neither of the others. The accepted half was solved in this story (`_STORABLE_PRICES` is derived from `_UNIT_PRICE_VERDICTS`, with a comment saying that deriving is what stops it falling behind); the refused half was left as two hand-copied lists, and this very change had to add `-0.001` to both by hand.
evidence: Compared programmatically on this checkout: the two tables share 14 raw values; `'$1.25'`, `'1,25'` and `'abc'` are pinned only for the create form, and `'not-a-number'` only for the other two. Nothing fails as a result — the rule is one helper, so the coverage gap is in what the suite would CATCH, not in what the code does — which is why this is low rather than a defect. The `_UNIT_PRICE_VERDICTS` header comment already argues the general case against exactly this shape ("two hand-copied per-route lists could not catch [drift]"), so the entry is about finishing an argument the file makes rather than making a new one. Closing it means deriving the create form's refusal cases from the same table the way `_STORABLE_PRICES` is derived, and deciding what to do with the three spellings only it covers — either they belong to every entry point or they belong to none. Related to [DW-12], [DW-25], [DW-22].
status: open

### DW-221: `_record_first_receipt` drops an unstorable price with no log line, so the one fail-open corner left is also the invisible one
origin: spec-purchase-parse-residuals-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-purchase-parse-residuals.md`
location: `app/main/routes.py:1466` (`_record_first_receipt`'s `parsed` dict)
severity: low
summary: The helper calls `_purchase_unit_price` and keeps only its value, discarding the message: a caller that reaches here with a surviving trigger and an unstorable price gets a real Purchase with a NULL `unit_price` and a `None` (success) return, and nothing anywhere records that a price was thrown away. The function's own comment names this as "the one place this still fails open", but the code has no diagnostic for it — the sole `logger` call in the function is inside the `except` around `record_purchase`.
evidence: Confirmed against the code on this checkout: `unit_price=(_purchase_unit_price(values['unit_price'])[0] if values['unit_price'] else None)` subscripts the tuple and lets the message go, and the guard below it can only see the trigger fields. Pre-existing in substance — the message has been discarded since the fallback was written, and DW-27 is what made this the only field it can still happen to — but newly the sole survivor of its class, since this story closed the quantity half. Not reachable through `POST /products/add` (`_validate_product_create_form` refuses an unstorable price before the Product commits), which is why it is low and why no test can observe it over HTTP; the exposure is the same "not the only caller it could ever have" one the new `TestTheFirstReceiptTriggersOnWhatSurvivesTheParse` class was written for. Deliberately not fixed here: adding a `logger.warning` is a behaviour change outside this story's contract, and the real question is whether a silently priceless receipt should be logged, refused, or left alone — the same question DW-218 asks about an unstorable `order_number`. Related to [DW-218], [DW-187], [DW-27].
status: open

### DW-222: The 7000-character URL ceiling is justified by gunicorn's MAXIMUM permitted request line, not its default, and no server config in this repo sets either
origin: spec-suggestion-query-length-bound-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-suggestion-query-length-bound.md`
location: `app/main/routes.py:2732` (`_MAX_SCAN_URL_CHARS`, and its rationale at :2641 and :2730), `app/static/js/field-autocomplete.js` (`MAX_URL_CHARS`)
severity: low
summary: Both constants are 7000 and both are justified in prose by "gunicorn's 8190-byte request line". 8190 is gunicorn's maximum ALLOWED `limit_request_line`; the default is 4094. If the deployment runs that default, a 7000-character URL is a 414 and neither bound prevents the failure it was written for.
evidence: Verified on this checkout: `_MAX_SCAN_URL_CHARS = 7000` predates this story (introduced by commit cfc7102, `sweep dw-scan-url-q-floor: DW-28`, before this spec's baseline 133e3e8), so the premise is pre-existing rather than introduced here; this change copied the number and its reasoning into `app/static/js/field-autocomplete.js` and pinned the two together with `tests/unit/test_autocomplete_markup.py::TestQueryLengthBoundTripwire::test_the_transport_bound_equals_the_scan_redirect_bound`. `grep -rn gunicorn requirements*.txt setup.py pyproject.toml` finds nothing — gunicorn is not a declared dependency, and the repo carries no gunicorn or nginx configuration, so the real request-line ceiling of the deployment is unknown to the code that claims to sit under it. Nothing fails today: the tripwire only asserts the two numbers agree, and they do. Closing it means measuring the deployed server's actual `limit_request_line` (and nginx's `large_client_header_buffers`), then moving BOTH constants together — the tripwire is what makes that one edit rather than two — or, if the server is not knowable, restating the comment as a self-imposed budget rather than as a fact about gunicorn. Related to [DW-162].
status: open

### DW-223: The browser half of the suggestion length bound has no executable coverage — only source-text regexes
origin: spec-suggestion-query-length-bound-review-2
source_spec: `_bmad-output/implementation-artifacts/spec-suggestion-query-length-bound.md`
location: `app/static/js/field-autocomplete.js` (`buildUrl`, `fetchAndRender`), `tests/unit/test_autocomplete_markup.py::TestQueryLengthBoundTripwire`, `tests/e2e/test_field_autocomplete.py`
severity: low
summary: Everything the component now does about an over-long value — refusing to build the URL, hiding, announcing "No suggestions", and not warning — is asserted only by regexes over the file's own source. A refactor that preserves those literals while breaking the logic passes, and one that preserves the logic while reformatting fails.
evidence: The tripwire slices the source on exact strings including their eight-space indentation (`_js_slice(source, '        buildUrl() {', ...)`) and matches `REFUSAL_BLOCK` against the text; no test executes the code. The spec's intent contract froze a no-e2e decision on the stated ground that "the pre-fix and post-fix symptoms are both 'no dropdown'", which is not the property that actually changed: the new behaviour is that NO REQUEST IS ISSUED, which Playwright observes directly through `page.route` / `page.on('request')`, as it would the companion regressions this pass could not cover either — that a legal 4096-character query is still sent, that two in-bounds values summing past `MAX_URL_CHARS` are not, and that a refusal does not wedge the component for the next keystroke. `tests/e2e/test_field_autocomplete.py`, `test_category_autocomplete.py` and `test_autocomplete_aria.py` already exist, so the harness cost is only the test. Deliberately not resolved in this story: the contract's "Never" list forbids the e2e test, so changing it is a spec decision rather than a review patch. Related to [DW-162], [DW-95].
status: open
