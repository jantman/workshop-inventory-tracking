# Contract: the listing payload

**Feature**: [spec.md](spec.md) | **Phase**: 1

## The boundary does not move

The payload the capture agent posts is **unchanged in shape**. No field is added, removed, renamed
or retyped, and the payload version stays **1**. This document exists to record that the boundary
was considered and deliberately not touched.

| Field | Type | Change |
|---|---|---|
| `images` | array of strings | **Membership only.** Fewer entries on a listing with a brand story; no placeholder entry on a listing with deferred-loading images. Still one flat list, still gallery-then-description, still no marker distinguishing the two. |
| `description_text` | string or null | **Value only, on affected listings.** Read from the corrected block. |
| `listing_title`, `brand`, `price`, `specifications`, `vendor`, `vendor_item_id` | unchanged | Not read, not written, not reordered by this feature. |

## Why the flat list stays flat

007 made `images` one undifferentiated list on purpose: the server never learns which address came
from the gallery and which from the description, so FR-019's "gallery images are exempt" carve-out
is true by construction rather than by the server honoring a distinction it cannot verify.

This feature adds two more browser-side rules — cross-sell and placeholder — and the same reasoning
applies to both. Neither needs the server's cooperation, and neither may acquire a second
implementation there. If a future change needs the server to know an image's origin, that is a
payload version bump and a separate decision, not a side effect of this one.

## What the server keeps doing

Unchanged, and relied upon:

- Deduplicating by image content, not address (007 FR-018).
- Fetching each address and skipping unsupported types or oversized files, reporting rather than
  failing (007 FR-020, FR-021).
- Stopping cleanly at the per-product attachment ceiling (007 FR-022).

Note for anyone reading this alongside research §2: `.gif` is in `_KNOWN_EXTENSIONS`
(`app/services/listing_images.py:45`), which is why the 1×1 placeholder is currently stored rather
than rejected downstream. **That list is not the fix and must not be edited here.** A GIF is a
legitimate product image; the placeholder is wrong because it is a placeholder, and that is knowable
only in the browser.
