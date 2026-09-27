# Research: Capture Product PDFs

## §1 Where each vendor's PDFs are, and who can fetch them

Measured 2026-09-27 in the owner's Chrome and from the development host.

**McMaster-Carr (`91074A329`).** The page renders client-side. The CAD files sit behind a
combobox, `button[role=combobox][aria-label="Select CAD file type"]`, inside
`[class*="_productDetailCADControl_"]`. Beside it is `a[class*="_downloadAnchor_"]`, whose
`href` is the *currently selected* format — on this browser `3-D PDF`, remembered from an
earlier visit. The list of formats exists in the DOM **only while the picker is open**, as
`li[role=option]` elements whose `id` is `dropdown-<label><path>`:

```
dropdown-3-D PDF/mvC/Library/CAD2/20260219/B6B6040F/91074A329_3D_Zinc-...Washer.PDF
dropdown-2-D PDF/mvC/Library/CAD2/20260219/B6B6040F/91074A329_Zinc-...Washer.PDF
dropdown-2-D DWG/... dropdown-2-D DXF/... dropdown-3-D STEP/... (and others)
```

The button's `aria-activedescendant` carries the same `dropdown-<label><path>` for the
selected entry, so when 2-D PDF is already selected no opening is needed.

Fetching the 2-D PDF address:

| Client | Result |
|---|---|
| page `fetch`, `credentials: 'include'`, `cache: 'no-store'` | 200 `application/pdf`, 105,558 bytes |
| page `fetch`, `credentials: 'omit'`, `cache: 'no-store'` | **403** |
| `curl` / `requests` from the dev host, with or without browser headers and Referer | **403** (ASP.NET origin, via Akamai) |

Product images under `/mvC/Contents/gfx/ImageCache/` and the drawing GIF under
`/mvC/Library/CAD2/` return 200 to `curl` — which is why images work today — but the CAD
downloads are session-gated. **Decision:** the agent must fetch the drawing itself.

**Amazon.** Sampled eight Fluke-multimeter listings via `/dp/<ASIN>`; four carried PDFs.
They appear as `<a href="https://m.media-amazon.com/images/I/<id>.pdf">User Manual (PDF)</a>`
under `#productDocuments_feature_div` ("Product guides and documents"), repeated inside the
quick-view popover `#pqv-documents`, and occasionally as a warranty link inside
`#productDetails_feature_div`. `curl` and `requests` fetch them: 200 `application/pdf`.
**Decision:** addresses are enough; the server fetches them as it fetches gallery images.

## §2 How the McMaster bytes reach the server

- **Decision:** a `data:application/pdf;base64,<…>` string in the listing's existing
  `images` array.
- **Rationale:** the payload travels as a form field into the confirmation page's hidden
  `listing` input and back, so a string is the only shape that survives without new
  plumbing. Putting it in `images` means every consumer — the details-only path (044/049),
  the purchase path, the Amazon order line path — stores it without being touched, and the
  size/type/dedup/cap rules apply for free (FR-005). An old server drops non-http entries
  in `_payload_images`, so the change is additive and `LISTING_CAPTURE_VERSION` stays 1.
- **Alternatives considered:** a separate `documents` field (a second parser, a second
  loop at three call sites, and a second counter, for no behavioural difference);
  forwarding the owner's McMaster cookies to the server (credentials leaving the browser —
  the constitution keeps secrets out of scope for a reason); deriving the 2-D address from
  the 3-D one by dropping `_3D_` (a guess about McMaster's naming that the picker states
  outright).

## §3 Opening the picker without changing it

- **Decision:** if `aria-activedescendant` already names `2-D PDF`, read it. Otherwise
  `click()` the combobox, poll briefly (≤ 1 s, 50 ms steps) for `li[id^="dropdown-"]`, read
  the `2-D PDF` entry, and `click()` again **only if the picker was closed before** —
  `aria-expanded` says which. No option is clicked, so the selected format and McMaster's
  remembered preference do not change (FR-003).
- **Rationale:** the content script runs in the isolated world but shares the DOM; a
  dispatched click reaches React's root listener exactly as a user's does. The poll is a
  wait for the list to render, bounded so a picker that never opens costs one second and
  the drawing, never the capture.
- **Alternatives considered:** reading React's props off the element (not visible from the
  isolated world); selecting 2-D PDF and reading the anchor (changes the owner's page and
  their remembered format).

## §4 What counts as a PDF on Amazon

- **Decision:** every `a[href]` whose resolved address is http(s) and whose path ends in
  `.pdf` (case-insensitive), excluding anchors inside the brand-story cross-sell container
  that images already exclude, de-duplicated by address, appended after the gallery and
  description images.
- **Rationale:** Amazon has no other PDFs on a listing page; the ones present are the
  product's own documentation. The quick-view repeat collapses under de-duplication, and
  content-hash de-duplication on the server catches anything the address check misses.

## §5 Telling the owner

- **Decision:** `ImageCaptureResult` gains `pdfs`, the number of *stored* files that were
  PDFs (`stored` stays the total, so the DigiKey "Attached N file(s)" message and every
  existing tally are unchanged). `_image_tally` says "Stored 4 images and 1 PDF" when
  `pdfs` is non-zero and exactly today's sentence otherwise.
- **Rationale:** FR-007 — the drawing is the thing the owner will check for.
