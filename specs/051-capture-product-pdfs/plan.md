# Implementation Plan: Capture Product PDFs

**Branch**: `robot-army/issue-173-mcmaster-not-capturing-all-media` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/051-capture-product-pdfs/spec.md`

## Summary

A product-page capture brings across images and nothing else. Make it bring PDFs too:
McMaster's 2-D PDF drawing and Amazon's linked manuals/guides.

The two vendors differ in the one way that decides the design (research.md §1): Amazon's
PDFs are public addresses the server already fetches, McMaster's CAD files are served only
to a browser holding a McMaster session. So:

- **Amazon** — the agent adds each PDF link's address to the listing's existing `images`
  list. The server's fetcher already accepts `application/pdf` and already stores PDFs
  (DigiKey datasheets take that path). No server change is needed for Amazon beyond the
  tally.
- **McMaster** — the agent opens the page's CAD picker, reads the 2-D PDF's address, closes
  it, fetches the file *in the page* (with the session) and puts it in `images` as a
  `data:application/pdf;base64,…` address. The server accepts that one kind of `data:`
  address and decodes it instead of making a request.

Everything downstream — size limit, type check, content-hash de-duplication, the per-product
cap, per-file failure counting — is the existing image path, untouched. The post-capture
tally learns to say how many of the stored files were PDFs (FR-007).

## Technical Context

**Language/Version**: Python 3.13 (Flask 3.1); JavaScript (MV3 extension content script, no build step)

**Primary Dependencies**: `requests` (already the fetcher), `base64` (stdlib), PyMuPDF (already renders PDF previews)

**Storage**: Unchanged — PDFs become `ProductAttachment` rows via `PhotoService`, as images do. No schema change, no migration.

**Testing**: `nox -s tests` (unit: payload parsing, `data:` decoding, tally); `nox -s e2e` (agent against the McMaster and Amazon fixtures, confirming stores the PDF)

**Target Platform**: The owner's Chrome with the capture extension; the LAN Flask app

**Project Type**: Web application (server-rendered) plus browser extension

**Performance Goals**: None new. One extra same-origin request on a McMaster capture (~100 KB).

**Constraints**: `MAX_FORM_MEMORY_SIZE` is 16 MB and a PDF attachment is capped at 20 MB by
`PhotoService`; a drawing is ~100 KB, so a base64 copy (~140 KB) in the form is well inside
both. The agent skips a McMaster PDF over the attachment limit rather than inflating the form.

**Scale/Scope**: One agent file, one service module, one model helper, one route helper, fixtures, docs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Simplicity First | **Pass.** No new payload field, entity, endpoint or setting: PDFs ride the existing `images` list and storage path. The only new server concept is decoding one `data:` address kind, which is forced by McMaster refusing the server (research.md §1). No new dependency. |
| II. Layered Architecture | **Pass.** Parsing stays in `app/models.py` (`_payload_images`), retrieval in `app/services/listing_images.py`, routes only format the tally. |
| III. Exact Numerics | **N/A.** No measured quantity is touched. |
| IV. Test Discipline | **Pass.** Unit tests mock nothing new on the network (a `data:` address needs no request; Amazon PDFs go through the already-patched `requests.get`). E2E waits on the agent's own promise and on the landed page (patterns C/A); the fixture's CAD picker is scripted so the test exercises the open/read/close path. No fixed waits. |
| V. MariaDB Source of Truth | **Pass.** No schema change. |
| VI. Item Lifecycle | **N/A.** Products and attachments only; no item paths. |
| Threat model | **Pass.** No allow-list or sanitization added for the `data:` address; it is validated only as far as bad data would break the inventory (must decode, must be a PDF the existing type check accepts). |
| Screenshots gate | **Pass.** No template, CSS or static JS changes — `extension/` is outside `app/static/`, and the tally is a flash string built in Python. |

Post-design re-check: unchanged — the design artifacts introduce nothing beyond the above.

## Project Structure

### Documentation (this feature)

```text
specs/051-capture-product-pdfs/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── listing-images.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
extension/capture-agent.js            # McMaster drawing reader; Amazon PDF links; capture() awaits the drawing
app/models.py                          # _payload_images accepts data:application/pdf;base64; ImageCaptureResult.pdfs
app/services/listing_images.py         # decode a data: address instead of requesting it; count PDFs; short log labels
app/product/routes.py                  # _image_tally names PDFs; order-listing sum carries pdfs
tests/unit/test_listing_images.py      # data: address stored / undecodable / duplicate; pdf counting
tests/unit/test_capture.py (or model tests) # payload parsing keeps data:application/pdf, drops other data:
tests/e2e/fixtures/mcmaster_product.html   # scripted CAD picker (3-D PDF showing, 2-D PDF in the list)
tests/e2e/fixtures/amazon_listing.html     # Product guides and documents + quick-view duplicate + brand-story PDF
tests/e2e/fixtures/images/*.pdf            # a one-page PDF the image host serves
tests/e2e/test_mcmaster_product.py         # drawing captured, picker restored, confirming stores it
tests/e2e/test_product_page_capture.py     # Amazon PDFs captured once, cross-sell excluded, stored
docs/user-manual.md, docs/capture-extension.md, README.md  # "images" → "images and PDFs" where capture is described
```

**Structure Decision**: Existing layout; no new modules.

## Complexity Tracking

No violations to justify.
