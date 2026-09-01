# Phase 0 Research: Photo Download Actually Downloads

**Feature**: `034-fix-photo-download` | **Date**: 2026-09-01

All questions below were resolved against the code in the repository. Nothing is left
marked NEEDS CLARIFICATION.

---

## R1 — Which identifier should the download endpoint take?

**Decision**: The **Photo id** (`photos.id`), the same identifier `GET /api/photos/<id>`
already takes.

**Rationale**:

- Both call sites already send it. `photo-manager.js:587` and `:896` build
  `/api/photos/${photo.id}/download`, and `photo.id` is assigned from
  `result.photo.photo.id` on upload (`:364`) and `photoInfo.id` on load (`:398`) — the
  Photo row in both cases. Choosing the Photo id means FR-007 is satisfied with **no
  JavaScript change**, which in turn means no screenshot regeneration and a smaller diff.
- It matches the sibling route. `GET /api/photos/<id>` and
  `GET /api/photos/<id>/download` reading the same id is the only reading of that URL
  shape that does not surprise.
- It keeps product and purchase attachments downloadable. Those create `Photo` rows with
  no association at all, so an association-keyed download could never serve them.

**Alternatives considered**:

- *Take the association id.* Rejected: both callers would have to switch to
  `photo.associationId` (which they carry, from #102), and attachments become
  undownloadable by construction. It is the larger change and the worse contract.
- *Accept either id, disambiguating by which table hits.* Rejected outright — this is
  precisely the ambiguity that produced the bug, made permanent and given a fallback path
  that hides the next mistake. Principle I.

---

## R2 — Where does the filename lookup belong?

**Decision**: A new method on `PhotoService`:

```python
def get_photo_file(self, photo_id: int) -> Optional[Tuple[bytes, str, str]]:
    """Return (original_data, content_type, filename) for a Photo id, or None."""
```

The handler makes exactly one service call, and receives plain values.

**Rationale**:

- Principle II puts the query in the service, not the route.
- Returning **plain values rather than an ORM object** matters more than it looks.
  Today's handler reads `photo.filename` *after* the `with PhotoService(...)` block has
  closed the session (`routes.py:3020` against the block ending at `:3012`) — a detached
  instance access that survives only by luck of attribute expiry settings. A tuple of
  primitives cannot have that problem.
- One method, one query, one failure mode. `None` means "no such photo" and there is no
  second way to fail.

**Alternatives considered**:

- *Add `get_photo_record(photo_id) -> Optional[Photo]` and keep calling `get_photo_data`.*
  Rejected: two queries for one read, and it re-creates the detached-instance hazard
  above.
- *Widen `get_photo_data()` to also return the filename.* Rejected: it has another caller
  (`get_photo_data` route, `routes.py:2965`) that does not want the filename, and
  changing a shared return shape to serve one caller is churn.
- *Rename `get_photo()` to `get_association()` so the name stops inviting the bug.*
  Tempting, and genuinely the root of the confusion — but it is a rename touching
  `delete_photo` and two existing tests for no behavior change, in a feature whose job is
  to fix a broken endpoint. Out of scope; noted here so the next person can weigh it on
  its own.

---

## R3 — Do we need a guard for a `Photo` row with no original content?

**Decision**: No. `photos.original_data`, `photos.content_type` and `photos.filename` are
all `nullable=False` (`app/database.py:700-708`). A row that exists has all three.

**Rationale**: Principle I — a check for a state the schema forbids is machinery for an
unobserved problem. `None` from `get_photo_file()` means the row does not exist, which is
the only real not-found case. The spec's edge case ("a stored file whose original content
is missing") is therefore satisfied by the schema rather than by code, and that is the
correct place for it.

---

## R4 — Does the download filename need special handling for non-ASCII or awkward names?

**Decision**: No custom code. Pass `download_name=` to `send_file` and let Werkzeug build
the header.

**Rationale**: Werkzeug's `send_file` emits both a plain `filename=` and an RFC 2231
`filename*=` parameter when the name is not ASCII-safe, and quotes what needs quoting.
Writing that by hand would be re-implementing a dependency the project already has
(Principle I, "dependencies MUST earn their place" — this one already has).

---

## R5 — How does a test create the drifted-id condition FR-008 requires?

**Decision**: Upload a **product attachment first**, then the item photo. The attachment
creates a `Photo` row with no `ItemPhotoAssociation`, so the next item photo gets Photo id
*N+1* while its association gets id 1. Assert in the test that the two ids differ, so the
test fails loudly if the seeding stops producing drift.

**Rationale**: This is not a new technique — it is exactly what
`tests/e2e/test_photo_bulk_delete.py`'s `item_with_photos` fixture already does, and its
docstring explains why ("Without this, every test below passes against a gallery that
deletes by the wrong id"). The same reasoning applies verbatim here. `live_server` exposes
`add_test_products()` and `add_product_attachments()` for the e2e side; the unit side uses
`PhotoService.upload_product_attachment()` against the `test_storage` fixture, as
`tests/unit/test_product_attachments.py` does.

**Alternatives considered**:

- *Insert rows with hand-chosen ids.* Rejected: it proves the handler works against a
  database shape, not against the shape this application actually produces.
- *Mock the session, as `tests/unit/test_photo_service.py` does.* Rejected: a mocked
  session returns whatever the test tells it to for both id kinds, so it cannot express
  the condition at all. This is the reason the existing photo tests did not catch the bug.

---

## R6 — What can the e2e test actually assert, and what can it not?

**Decision**: The e2e test asserts that a download **happens** and that its **bytes** are
the uploaded bytes. It must **not** be relied on to prove the server sent the right
filename — that assertion belongs to the unit test, against `Content-Disposition`.

**Rationale**: `downloadPhoto()` sets `link.download = photo.name` before clicking
(`photo-manager.js:590`), and for a same-origin response the anchor's `download` attribute
overrides `Content-Disposition`. So `download.suggested_filename` in Playwright would read
back the name the *page* chose, and would be correct even against a server that sent no
filename at all. An e2e filename assertion would therefore pass against the bug — the
exact failure mode CLAUDE.md warns about for negative assertions, in a different disguise.

**Consequence for the tasks**: FR-002's filename requirement is verified by an API-level
assertion on the response header. The e2e tests verify FR-001 and FR-007 — that pressing
each control produces the file.

---

## R7 — Are the e2e mechanics available?

**Decision**: Yes, both controls are reachable and downloads are capturable.

**Rationale**:

- Playwright 1.61 / pytest-playwright 0.8.0 (`requirements-test.txt:11-12`); contexts
  accept downloads by default, and `page.expect_download()` is the observable wait — no
  fixed delay needed, satisfying Principle IV.
- The **gallery** control is `.photo-download-btn` on each card.
- The **viewer** control is reachable in e2e. `base.html:20,157` skip the PhotoSwipe CDN
  loads on `localhost`/`127.0.0.1`, so `viewPhoto()` takes its
  `showFallbackImageModal()` branch — which is the modal that carries
  `.modal-download-btn`. Scope the locator to the modal footer: the same class also
  appears in the PDF-unavailable notice.
