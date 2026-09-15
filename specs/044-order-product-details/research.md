# Research: Capture Product Details for Products an Order Created

Findings from reading the code, and the decisions they led to. Paths are relative to the
repository root.

## §1. Why the defect exists

`CatalogService.capture_order` (`app/catalog_service.py:1064`) is the only write path behind a
single-listing capture, and it ends unconditionally in `record_purchase` (`:1304`). The listing's
details are applied by `_apply_listing` (`:1301`), which runs only after both questions are
settled. Pictures are stored by the route after that (`app/product/routes.py:612`).

After an order capture the two questions cannot be answered in a way that avoids a purchase:

- **Duplicate.** `_find_captured_purchase` finds the order-captured row through spec 033's
  cross-path arm. The only answers are to open that row, or to tick "separate order", which
  records a second purchase.
- **Identifier.** An order-created product has no manufacturer (`_create_amazon_product`, `:3058`),
  so `_corroborates` can never pass. Either answer, attach or new, still records a purchase.

The order review's note (`app/templates/product/order_review.html:103-110`) promises the
opposite. So does `_create_amazon_product`'s docstring.

**Decision:** add a third outcome to a listing capture, *details only*. It writes the listing onto
the matched product and never reaches `record_purchase`. Neither existing question is removed.

## §2. What "details captured" means: derived, not stored

FR-014 needs every product to read as captured or missing. There are two options:

- **A stored marker**, such as a nullable `products.listing_details_at` column. This needs an
  Alembic revision with a backfill guess for every existing row, a write on every capture path, and
  a column that can disagree with what the product visibly holds.
- **Derived from what the product holds.** A product reads as *captured* when it has at least one
  specification row.

**Decision: derived.** Every listing capture writes rows: the listing's product-information rows,
"About this item" (spec 020) and "Description" (from `description_text`). An order-line product has
none. The existing data therefore classifies correctly with no backfill (FR-015):

- yesterday's thin products read as missing
- listing-captured products read as captured

Two edge behaviors are accepted deliberately:

- **A listing that yields no rows at all leaves the product reading as missing.** That is
  truthful. The capture got nothing, and the operator should look.
- **A thin product the operator has typed rows onto by hand reads as captured.** That is also
  truthful, because it has details. The checklist asks "does this need attention?", not "which code
  path ran?".

Where it is used:

- The order page, in one grouped query: `products_missing_details(product_ids)`.
- The product page, from rows the page already loads.

This is the fourth consecutive order feature with no schema change.

## §3. Where the choice is offered: the bookmarklet landing, with no extra round trip

Today questions appear only after the operator submits (`CaptureDecisionRequired` → re-render).
A corroborated repeat buy asks nothing and records the purchase silently, which would leave nowhere
to offer details-only (FR-001).

**Decision:** the bookmarklet's landing (`api_capture`, form branch, `routes.py:823`) already
knows the vendor, the item id and the listing. It gains one read-only service call,
`find_listing_match(...)`. When that finds a product, the page renders a **"What should this
capture do?"** block before the operator has submitted anything. The same call feeds every
re-render of the form (a decision or validation error), so the block survives a round trip.

- **Match with no order-captured purchase:** the radio defaults to *Record a purchase* (FR-012).
  Submitting takes exactly today's path, including today's questions.
- **Match whose product also holds an order-captured purchase within the spec 033 window:** the
  page shows **one** message naming the order, with *details only* selected (FR-009, FR-010). The
  alternative, *a separate purchase of this same product*, carries its answers as hidden fields:
  `acknowledged_duplicate_of=<that purchase>` and `attach_to=<that product>`.
  - The details path ignores both fields.
  - The purchase path receives exactly the two answers the operator has just given, so
    `capture_order` asks nothing further and the page needs no JavaScript.
  - "File as a different product" is not offered in this mode. It would mean Amazon recycled an
    ASIN within ninety days of an order that recorded it, and that operator can still reach it
    through the paste form.

**Paste-a-URL path:** the form does not know the item until it is submitted. It reaches the
details-only choice only through a question's re-render. That path carries no listing payload, so
there is almost nothing it could add. This is accepted and recorded in the contract.

The two existing warning blocks are kept verbatim for every case the collapsed message does not
cover. The identifier block gains the FR-013 consequence sentence on its "different product"
option.

**Alternatives rejected:**

- **A second bookmarklet, or a "details mode" flag.** The operator would have to choose before
  seeing what matched, and a bookmarklet change means re-dragging it (spec 029 FR-034).
- **Always raising a question when a product matches.** This adds a round trip to every repeat buy
  and breaks the silent-attach path that `tests/e2e/test_repeat_purchase.py` pins.

## §4. One service method writes a listing onto an existing product

`apply_listing_details(product_id, listing, proposed, replace)` does the following:

- **Scalars** (description, manufacturer, part number, category, location, sub-location): a
  proposed value fills a blank. It replaces a held value only when the field is named in `replace`.
  A blank proposal changes nothing.
- **Specification rows:** absent names are appended, which is `merge_specifications`' add-only rule
  (`:707`). A held name is overwritten only when `spec:<name>` is in `replace`.
- **Barcodes:** the rows this call added or replaced are passed to `_promote_barcode_rows`, the
  existing rule (spec 016 FR-003, "rows this capture added").
- **Never touched:** purchases, quantity, stock status and reorder threshold (FR-002).
  `update_product` already excludes the last three by construction.
- **Returns** `ListingDetailsResult`: the fields filled, the fields replaced, and the rows added and
  replaced, which is enough for the flash.

It has **two callers**:

1. **Details-only capture.** `proposed` comes from the confirmation form, and `replace` from the
   operator's ticks.
2. **The order path (§6).** `proposed` holds `{manufacturer: brand, manufacturer_part_number:
   listing.manufacturer_part_number()}`, and `replace` is empty. That is FR-027's "fill what it
   lacks, overwrite nothing", expressed through the same method rather than a second rule.

**The purchase path (`capture_order`) is not changed** (FR-008). It already overwrites nothing
listing-derived. Routing it through the new method was considered and rejected: that would change
how operator-typed values are handled on a repeat buy, which is outside this issue and pinned by
`tests/unit/test_capture.py`.

The new method needs the show-and-choose inputs **before** the operator submits. The same
`find_listing_match` result carries the product's current values and its current specification
rows. The template compares them with the listing's rows at render time:

- same value: nothing is shown
- new name: counted as "will be added"
- different value: one row with a *Replace* tick, unticked by default (FR-004)

Scalar fields show *Currently: X* under the input, with a *Replace it* tick, whenever the product
holds a value. The input stays the operator's to edit, so the proposed value is whatever it holds on
submit.

## §5. The auto-fetch lives in the capture agent

`canonicalDocument(asin)` (`app/static/js/capture-agent.js:1584`) already fetches
`location.origin + '/dp/' + asin` same-origin, with the operator's session, and parses it with
`DOMParser`. `extract(doc, url, asin)` (`:677`) turns that into the listing payload. Reading
every line of an order is those two in a loop.

**Decision:** in the `amazon-order` branch (`:1677`), before `submitCapture`, read each distinct
ASIN once, **sequentially**, and attach the result to every line naming it:

- `line.listing = <extract(...)>` when the listing was read
- `line.listing_problem = "<short reason>"` when it was not

A listing counts as read only when all three of these hold:

1. **The fetch succeeded**, with `response.ok`.
2. **The final address, `response.url`, still names the same ASIN.** A redirect to a variant or a
   replacement is recorded as a problem rather than silently applied (spec edge case).
3. **`titleFrom(doc)` is non-empty.** A sign-in page or a robot check has no `#productTitle`.
   This is the check that catches Amazon throttling without the agent having to recognize
   Amazon's captcha markup.

Unlike `canonicalDocument`, there is **no fallback to the open tab**. The open tab is the order
page, and reading it as a listing would be wrong.

**Progress (FR-023)** is a fixed-position element the agent appends to the Amazon page, reading
"Workshop capture: reading listing 3 of 5…". It is updated after each fetch and removed when the
form submits. It is inline-styled, because the agent cannot rely on any stylesheet on Amazon's page.

**Sequential, not concurrent.** Five parallel fetches from one session are the likeliest way to be
handed a robot check. At roughly 1–2 s per listing, sequential reading is within SC-007, and per
Constitution I there is no concurrency without a measured need. There is no delay between fetches
either. Adding one would be a fixed wait with nothing to justify it.

**Payload.** The two keys are additive inside the existing version-1 order payload.
`AmazonOrderLine.from_payload` ignores keys it does not know, so a stale server renders the order
exactly as before. The version is not bumped. A bump would make a new agent against an old server
fall through to "unreadable", which is worse than extra keys being ignored.

**Why not fetch server-side?** The application would then contact Amazon without the operator's
session. It would be refused far more often, and it would make a LAN app a scraper. The agent runs
in the operator's browser, on the page they are already signed in to, which is the property every
Amazon capture already relies on.

## §6. Order-line details are written after the order commits

`capture_order_lines` (`:2042`) writes the whole order in one session. The existing listing helpers
(`merge_specifications`, `add_identifier`, `update_product`) each open **their own** session, and
`_session()` (`:151`) does not nest. Doing this inside the order's transaction would mean extracting
in-session twins of three methods.

**Decision:** leave `capture_order_lines` as it is, apart from reporting which product each line
landed on. It gains `OrderCaptureResult.line_products`, a tuple of `(form_key, product_id)`, for:

- every line that created or attached a purchase
- every line adopted under spec 033
- every line already captured (FR-030)

The confirm route then calls `apply_listing_details` for each line that carries a listing, followed
by `store_listing_images`.

This is the same split the single-listing capture already makes. `capture_order` itself runs
`create_product`, `merge_specifications`, `add_identifier` and `record_purchase` as separate
sessions, and pictures follow outside all of them. The integrity-critical write, the order's
purchases, is still all-or-nothing. Details that fall short degrade to "missing" on the checklist
(FR-031), which is exactly the fallback the spec asks for.

**Already-captured lines (FR-030)** come for free from this. The loop's `existing is not None`
branch (`:2188`) records the line's product id in `line_products`, and the route fills it like any
other. Re-running the order bookmarklet on yesterday's order is therefore a one-click repair for
the reported products.

`OrderCaptureResult.wrote_anything` and `_order_capture_summary` gain `products_detailed`. It is
counted in the "wrote something" block above the fallback, so a re-capture that only filled details
does not lead with "Nothing new to capture". That is the PR #116 / #123 rule the function's
docstring records.

## §7. Werkzeug's 500 KB form-field limit

Flask 3.1.3 / Werkzeug 3.1.8 cap each non-file form field at `MAX_FORM_MEMORY_SIZE` = 500 000
bytes by default (checked: `Flask.default_config['MAX_FORM_MEMORY_SIZE']`). The `order` field now
carries a listing per line. A listing payload is dominated by `description_text` and `images`, and
the agent sends the description uncapped (`capture-agent.js:715`). A twenty-line order of listings
at 25 KB each is already at the limit. Exceeding it is a 413 with nothing captured, and the review
page posts the same field back on confirmation.

**Decision:** set `MAX_FORM_MEMORY_SIZE = 16 * 1024 * 1024` on the base config. The value is
measured rather than guessed: the tasks include recording the fixture listing's serialized size.
It does not count as a new configuration knob. It is Flask's own setting, raised because this
feature makes a payload that did not exist before. `MAX_CONTENT_LENGTH` stays unset, as today.

## §8. Gunicorn's 30-second worker timeout

The container runs `gunicorn --workers 2 wsgi:app` (`Dockerfile:69`) with no `--timeout`, which
means gunicorn's default of 30 s. A single listing capture already takes 8–15 s to store a full
gallery. That figure is documented at `app/product/routes.py:610` and in spec 007's research.md
("Why image retrieval is synchronous"). An order confirmation that now stores a gallery for each of
five lines is 40–75 s: past the timeout, so the worker is killed mid-request. The purchases and
details are already committed by then, but the operator sees an error page and the pictures stop
part-way.

**Decision:** add `--timeout 600` to the gunicorn command, and state in
`docs/deployment-guide.md` that a reverse proxy in front of the app needs a read timeout at least
that long. The alternative is moving image retrieval to a background job, and the constitution
prohibits background machinery without a measured problem. The measured problem here is the
request's length, not throughput, and a longer timeout fixes that with one flag. One operator
waiting a minute, with a single-listing-sized progress story, is acceptable. The confirm button's
existing behavior is unchanged.

## §9. Returning to the order after a details-only capture

FR-020 needs to know which order to return to. The landing page knows it from
`find_listing_match`, which found the order-captured purchase, so the form carries it in a hidden
`return_order` field. The route redirects to `_order_url(vendor, return_order,
highlight=item_id)`, the helper the order capture already uses, and otherwise to the product page.
Nothing is stored between requests.

## §10. The checklist's "open listing" link

For an Amazon line the link is `https://www.amazon.com/dp/<ASIN>`, opened in a new tab. It is
built from the purchase's `vendor_item_id`, not from `listing_url`: an order-captured purchase's
`listing_url` is the order page (`_amazon_line_fields`), not the listing.

The product page shows the missing-details notice only for a product carrying an Amazon VENDOR
identifier (FR-018, "when its item's listing address is known"). A product with nothing to link to
gets no nagging.

## §11. Existing tests that change on purpose

- `tests/unit/test_cross_path_duplicates.py::TestCapturingAListingAfterItsOrder` (`:631-742`)
  asserts that both warnings render when a listing is captured after its order. FR-009 replaces them
  with one message, so these assertions are updated. The cases asserting that acknowledging records
  a separate purchase still hold through the collapsed block's "separate purchase" option.
- `tests/e2e/test_amazon_order.py` and `tests/e2e/test_amazon_receive.py` drive the order agent
  against a fixture on the live server's origin. From now on the agent also fetches `/dp/<ASIN>`
  for each line. Unrouted, those requests reach the app, return 404, and every line reads "details
  not read". Each such test either routes the listings (with `LISTING_ROUTE`, the pattern
  `tests/e2e/test_product_page_capture.py:60` already uses) or asserts the not-read state. The
  thin-note test (`test_the_review_says_the_products_will_be_thin`) is rewritten against the new
  note.
- Everything else, including `test_repeat_purchase.py` and `test_capture.py`, is expected to pass
  unedited. That is the check that §3's default-to-purchase and §4's untouched purchase path are
  true.

## §12. Schema

No schema change and no Alembic revision. Every value written already has a column. The details
status is derived (§2).
