# Contract: Photo Download

**Feature**: `034-fix-photo-download` | **Date**: 2026-09-01

## HTTP: `GET /api/photos/<int:photo_id>/download`

Returns the original uploaded file as an attachment.

**Handler**: `download_photo` in `app/main/routes.py` (currently at line 2990).

### Parameters

| Name | In | Type | Meaning |
|------|----|------|---------|
| `photo_id` | path | integer | **`photos.id`** — the stored-file id, the same one `GET /api/photos/<id>` takes. **Not** the `item_photo_associations.id`. |

No query parameters. There is no `size` parameter and must not be: download returns the
original, always (FR-003).

### Responses

| Status | Body | When |
|--------|------|------|
| `200` | The original file bytes | A `photos` row with that id exists. |
| `404` | `{"success": false, "error": "Photo not found"}` | No `photos` row has that id. |
| `500` | `{"success": false, "error": "Failed to download photo: ..."}` | Unexpected failure only. **A request that matches an existing row must never reach this branch** (FR-005) — that it does today is the bug. |

### 200 response headers

| Header | Value |
|--------|-------|
| `Content-Type` | `photos.content_type` verbatim — `image/jpeg`, `image/png`, `image/webp` or `application/pdf`. Never re-mapped to `image/jpeg` the way the thumbnail path does for PDFs. |
| `Content-Disposition` | `attachment; filename=...`, the filename being `photos.filename`. Non-ASCII names are additionally emitted as RFC 2231 `filename*=` by Werkzeug (R4). |

The body is byte-for-byte `photos.original_data`.

### Contract notes

- **Attachment, not inline.** `as_attachment=True`. This is the only difference in intent
  from `GET /api/photos/<id>?size=original`, which serves the same bytes inline.
- **Rows with no item association are served.** Product and purchase attachments are
  `Photo` rows and download like any other. This is deliberate (R1) and consistent with
  `GET /api/photos/<id>`, which already serves them — `product/detail.html:169,242` links
  straight to it.
- **No authentication.** As with every route in this application (Constitution, Operating
  Context).

## Internal: `PhotoService.get_photo_file`

**Module**: `app/photo_service.py`

```python
def get_photo_file(self, photo_id: int) -> Optional[Tuple[bytes, str, str]]:
    """
    Get the original file for download.

    Args:
        photo_id: Photo ID (photos.id) - NOT association ID

    Returns:
        Tuple of (original_data, content_type, filename), or None if no such photo
    """
```

- Queries `Photo` by primary key in the file's existing `session.query(...)` style.
- Returns **plain values**, never the ORM instance — the caller reads them after the
  session closes (R2).
- Returns `None` for a missing row; raises `RuntimeError` on a genuine query failure,
  matching the surrounding methods' convention.

### Contract boundaries with existing methods

| Method | Takes | Returns | Unchanged by this feature |
|--------|-------|---------|---------------------------|
| `get_photo(photo_id)` | **association** id | `ItemPhotoAssociation` | yes — still used by `delete_photo`. The download path stops calling it. |
| `get_photo_data(photo_id, size)` | **Photo** id | `(bytes, content_type)` | yes — still serves the inline view route. |
| `get_photo_file(photo_id)` | **Photo** id | `(bytes, content_type, filename)` | **new** |

## UI contract (unchanged)

`app/static/js/photo-manager.js` is **not modified**. Both call sites already send the
Photo id and remain correct:

- `:587` — gallery card download button, `downloadPhoto(photo)`.
- `:896` — viewer modal download links, `.modal-download-btn`.

Note for testers: `downloadPhoto()` sets `link.download = photo.name`, which overrides
`Content-Disposition` in the browser. The server-sent filename must therefore be asserted
against the HTTP response, not against the browser's saved name (R6).
