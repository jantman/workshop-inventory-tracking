# Contract: `listing.images` entries

The capture agent (`extension/capture-agent.js`) → server (`ListingCapture.from_data`,
`store_listing_images`). `LISTING_CAPTURE_VERSION` remains **1**: the change is additive.

## Agent obligations

1. Entries are strings, in the order gallery → description images → documents.
2. An Amazon PDF is sent as its absolute `https://` address, once per distinct address.
3. A McMaster 2-D drawing is sent as `data:application/pdf;base64,<standard base64>`,
   at most one per capture, only when the in-page fetch returned 200 with a
   `application/pdf` body no larger than 20 MB.
4. Failing to find or fetch a drawing omits it silently from `images`; it never rejects
   `capture()`.
5. The McMaster CAD picker is left as found: open state and selected format unchanged.

## Server obligations

1. `_payload_images` keeps http(s) entries and entries beginning exactly
   `data:application/pdf;base64,`; it drops everything else.
2. `store_listing_images` decodes a `data:` entry instead of requesting it; the decoded
   bytes are subject to the same type, size, dedup and cap rules as a fetched body, with
   the type taken from the `data:` header.
3. An undecodable `data:` entry is one `failed`, never an exception.
4. A `data:` entry is never written to the log in full.
5. `ImageCaptureResult.pdfs` counts stored PDFs; the tally names them when non-zero and is
   unchanged otherwise.
