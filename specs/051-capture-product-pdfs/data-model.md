# Data Model: Capture Product PDFs

No persisted entity changes. No migration.

## `ListingCapture.images` (payload, not persisted)

An ordered list of strings. Each entry is now one of:

| Form | Produced by | Server action |
|---|---|---|
| `http(s)://…` image address | Amazon gallery/description, McMaster images (unchanged) | fetched |
| `http(s)://….pdf` address | Amazon PDF links (new) | fetched |
| `data:application/pdf;base64,<data>` | McMaster 2-D drawing (new) | decoded, no request |

Validation (`_payload_images`): http(s) as before, plus the exact prefix
`data:application/pdf;base64,`. Any other `data:` entry is dropped, as any non-http entry
always was. Order is preserved: gallery, description images, then PDFs.

## `ImageCaptureResult` (not persisted)

| Field | Change |
|---|---|
| `stored` | unchanged: total files stored, images and PDFs |
| `pdfs` | **new**, `int = 0`: how many of `stored` were `application/pdf` |
| `duplicates`, `skipped`, `failed`, `cap_reached` | unchanged; PDFs count in them like images |

A `data:` address that does not decode as base64 counts as `failed` (the owner's next action
is the same as for an unreachable address). A decoded body is then subject to the existing
size and type checks.

## Stored attachment

A captured PDF becomes a `ProductAttachment` through
`PhotoService.upload_product_attachment_if_new`, named `<vendor item id>-<index>.pdf`, with a
first-page preview rendered as for any uploaded PDF. De-duplication is by content hash, so
a re-capture adds nothing (SC-003).
