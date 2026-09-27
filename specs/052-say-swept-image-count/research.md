# Research: Say When the Image Count Was Swept

## 1. How `galleryFrom()` reports that it swept

- **Decision**: `galleryFrom(doc)` returns `{ addresses, swept }` instead of a bare array.
  `swept` is true only on the branch that already emits the console warning — the parse
  yielded nothing and `sweepImageAddresses()` found at least one address. `extract()` is its
  only caller and destructures it.
- **Rationale**: The fact is local to one branch of one function; returning it is the
  plainest way to hand it to the one caller. Tying it to the branch that warns keeps the two
  channels in lockstep — the page says it exactly when the console says it (spec SC-004).
- **Alternatives considered**: A module-level "last read swept" variable — rejected, it is
  state shared across reads, and an order capture runs `extract()` once per line. Counting
  warnings — rejected, indirect.

## 2. Payload shape and compatibility

- **Decision**: `extract()` sets `listing.images_swept = true` only when swept; the key is
  omitted otherwise, matching the existing rule that a key the page yielded nothing for is
  omitted. `LISTING_CAPTURE_VERSION` stays 1.
- **Rationale**: `ListingCapture.from_data` reads named keys and ignores the rest, so an
  older extension's payload (no key) parses unchanged and reads as not swept (FR-003). A
  version bump would make every pre-upgrade extension degrade to no payload at all — the
  cost 048 FR-026 records — for a purely informational flag.
- **Alternatives considered**: `images_swept: false` on every payload — harmless, but breaks
  the omit-when-empty convention for no gain.

## 3. Parsing on the server

- **Decision**: `images_swept = data.get('images_swept') is True`.
- **Rationale**: Mirrors `_payload_string` refusing a JSON number for `price`: only the exact
  shape the agent produces counts. A string `"true"` or `1` reads as not swept, which errs
  toward today's behavior (no caveat) rather than a false alarm.

## 4. Where the caveat renders

- **Decision**: Inside `#summary-images` on `product/capture.html`, after the count, with the
  issue's wording; inside `.line-listing-summary` on `product/order_review.html`, directly
  after the picture count, in a shorter form ("picture count is a guess — gallery data could
  not be read"). Each carries its own class (`images-swept`) so tests can target it.
- **Rationale**: The issue asks for it "next to the count it qualifies". The per-line
  summary is a single dot-separated line, so the long sentence would dominate it.
- **Alternatives considered**: A warning badge — rejected; the confirmation page's summary is
  plain text by design, and the caveat is information rather than an error.

## 5. The console warning

- **Decision**: Unchanged (`console.warn`, same text).
- **Rationale**: The issue explicitly rejects lowering it to `console.info`: that gives up the
  signal #95 exists to preserve. The `chrome://extensions` badge is accepted.

## 6. Test harness for the order case

- **Decision**: e2e: route the order's listing reads so one ASIN gets
  `amazon_listing_unreadable_gallery.html` and the rest get `amazon_listing.html`, modeled on
  `serve_listings_except()` in `tests/e2e/test_order_product_details.py`; assert the caveat
  appears on that line only. Unit: post an order payload whose line listing carries
  `images_swept: true`.
- **Rationale**: Exercises the real agent end to end on the path the issue observed (#133),
  with fixtures that already exist.
