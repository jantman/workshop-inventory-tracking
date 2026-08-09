# Contract: HTTP surface

**No new route.** Every change below is to an existing endpoint, and each keeps its current behaviour when the new field is absent.

---

## `POST /api/capture` — form representation

Unchanged in shape: it renders the pre-filled capture form and writes nothing. It now forwards one more field to the template.

| Field | Before | Now |
|---|---|---|
| `url` | read | read, unchanged |
| `listing_title` | read | read, unchanged |
| `listing` | — | passed through to `form_data` verbatim, not parsed here |

The route does not parse the payload. Parsing belongs at the point of use, and this representation is a render — nothing is written, so nothing needs validating yet. `from_bookmarklet=True` still drives the "nothing has been recorded yet" banner.

**Still `@csrf.exempt`, and still the only exemption this blueprint adds.** The count assertion in `tests/unit/test_product_csrf.py` is unaffected.

## `POST /api/capture` — JSON representation

Unchanged. It accepts no `listing` key and gains no capture behaviour. The rich payload arrives through the form representation because that is the one a vendor page can send; adding it here would be a second path to maintain for a caller that does not exist.

---

## `POST /products/capture` — the confirmation

The write. Its existing contract — validate, call `capture_order`, catch `CaptureDecisionRequired` and re-render, catch `ValidationError` and flash — is unchanged. Three additions:

1. **Parses `listing`** via `ListingCapture.from_json(request.form.get('listing'))`. `None` on anything absent or unusable; the capture then behaves exactly as it does today.
2. **Fills the blanks the operator left.** Where the form's `manufacturer` or `unit_price` is empty and the payload has one, the payload's value is used. The operator's typed value always wins — US1 scenario 3.
3. **After `capture_order` returns**, calls `store_listing_images(purchase.product_id, listing.images, ...)` and flashes the tally before redirecting to the receive screen.

**Ordering is the contract.** The redirect happens after the images are stored, so the receive screen the operator lands on shows a finished capture. This is what makes the POST take 8–15 seconds for a full gallery; see [research.md](../research.md#why-image-retrieval-is-synchronous).

**Failure semantics:**

| What fails | What the operator gets |
|---|---|
| `CaptureDecisionRequired` | The form again, with the question — and the `listing` field re-emitted, so answering costs nothing (FR-016). |
| `ValidationError` | The form again, flashed error, `listing` re-emitted. |
| Some images unretrievable | Capture succeeded. Flash names how many did not land (FR-020). |
| Attachment cap reached | Capture succeeded. Flash says it stopped at the limit (FR-022). |
| Every image unretrievable | Capture succeeded. The specifications and description are the point too (FR-020). |

There is no path where an image problem costs the operator the purchase.

---

## The bookmarklet

`_capture_bookmarklet()` stops being the extractor and becomes a loader. It carries two absolute URLs, both from `url_for(..., _external=True)`, and cache-busts the script so FR-024 holds:

```
javascript:(function(){var s=document.createElement('script');
s.src='{static}/js/capture-agent.js?v='+Date.now();
s.dataset.endpoint='{endpoint}';
document.body.appendChild(s);})();
```

The existing TLS caveat on `/products/capture` still applies and its warning panel stays: a bookmarklet dragged from the `http` page still bakes in an `http` address and still dies under `upgrade-insecure-requests`. What changes is that the payload it can carry is now the whole listing.

---

## `GET /products/<id>` — the attachments card

Renders a thumbnail grid instead of a filename list (FR-013), using the existing `GET /api/photos/<photo_id>?size=thumbnail`, which already accepts `thumbnail`, `medium` and `original` (`app/main/routes.py:2729`). No route changes; the template stops asking for the original in an `<a>` and starts asking for the thumbnail in an `<img>`, with the original still one click away.

PDFs already have rendered thumbnails — `_process_pdf` generates them — so a datasheet appears in the grid as its first page rather than as a broken image.

---

## `POST /api/products/<id>/attachments` — unchanged, one new caller

The paste handler (FR-023) posts to this endpoint with the same `FormData` shape the file picker uses, through `csrfFetch`. No route change, no new endpoint, and the CSRF token travels because this one is same-origin.

Clipboard content that holds no image uploads nothing and reports nothing — a paste is not a request to upload, and a rejection message on every ordinary text paste would be noise.
