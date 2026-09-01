# Feature Specification: Photo Download Actually Downloads

**Feature Branch**: `issues/131`

**Created**: 2026-09-01

**Status**: Draft

**Input**: User description: "issue #131 in this repo — GET /api/photos/<id>/download can never succeed: wrong id type, and filename read off the association"

## User Scenarios & Testing *(mandatory)*

The operator is the only user. Everything below is one person trying to get a copy of a
file they previously attached to an inventory item.

### User Story 1 - Download a photo from the item's gallery (Priority: P1)

The operator opens an inventory item that has photos attached, clicks the download button
on a photo's card, and the file is saved to their machine under its original filename with
its original content — the full-size image or PDF exactly as uploaded, not a thumbnail and
not a re-encoded copy.

**Why this priority**: This is the whole issue. The button has never worked — every click
either fails silently or produces an error — so the only way to retrieve an attached file
today is out-of-band access to the database. On its own it makes the feature real for the
first time.

**Independent Test**: Attach a file to an item, reload the item, click the download button
on its card, and confirm a file arrives with the uploaded name, the uploaded content type,
and byte-for-byte the uploaded content.

**Acceptance Scenarios**:

1. **Given** an item with an attached image, **When** the operator clicks the download
   button on its gallery card, **Then** the browser saves a file whose name is the
   filename the file was uploaded under and whose bytes are identical to what was
   uploaded.
2. **Given** an item with an attached PDF, **When** the operator downloads it, **Then**
   the saved file is the original PDF, not the generated preview image.
3. **Given** a photo that has not finished uploading, **When** the operator clicks
   download, **Then** nothing is requested and no error is shown.

---

### User Story 2 - Download from the full-size viewer (Priority: P2)

The operator opens a photo in the viewer to look at it full size, decides they want a
copy, and uses the download control in the viewer. The same file arrives as from the
gallery card.

**Why this priority**: It is the second of the two entry points to the same broken
endpoint, and the natural place to decide you want the file — but it is the same
underlying capability as P1, so it is only valuable once P1 works.

**Independent Test**: Open a photo in the viewer, use its download control, and confirm
the saved file matches the uploaded one.

**Acceptance Scenarios**:

1. **Given** the viewer is open on an uploaded image, **When** the operator uses the
   download control, **Then** the original file is saved under its original filename.
2. **Given** the viewer is open on an uploaded PDF, **When** the operator uses the
   download control shown in place of the inline viewer, **Then** the original PDF is
   saved.

---

### User Story 3 - Downloading a file that is not there (Priority: P3)

The operator (or a stale page left open after a deletion) asks to download a file that no
longer exists. They get a clear "not found" answer rather than a server error.

**Why this priority**: It is the correctness boundary around P1 rather than a capability
of its own, but it is what separates "the endpoint is fixed" from "the endpoint happens to
work for the row I tried". It also protects against the specific defect being re-created:
the current handler answers a missing file two different ways depending on which table the
id happens to hit.

**Independent Test**: Request a download for an identifier no file has, and confirm a
not-found response rather than a failure.

**Acceptance Scenarios**:

1. **Given** an identifier that matches no stored file, **When** a download is requested
   for it, **Then** the response is "not found" and no server error is recorded.
2. **Given** a file that was deleted after the page was loaded, **When** the operator
   clicks download on the stale card, **Then** the response is "not found".

---

### Edge Cases

- **The two identifier sequences have drifted.** Files attached to products and purchases
  are stored without an item association, so the stored-file identifiers and the
  item-attachment identifiers do not line up on any database that has had one. Download
  must be correct on such a database, not merely on a fresh one where the numbers happen
  to coincide. This is the condition that makes the current defect visible (association 53
  against file 43 on the deployed build).
- **A file attached to more than one item.** One stored file can be attached to several
  items. Downloading it from any of those items yields the same file and the same
  filename.
- **A file with no item attachment at all** — a product or purchase attachment. Asking to
  download one must either succeed or answer "not found"; it must not fail.
- **A filename that is awkward in a download header** — non-ASCII characters, quotes,
  spaces, or a very long name. The download still succeeds and the saved name is
  recognizably the uploaded one.
- **A stored file whose original content is missing** while its record exists. The
  response is "not found", not a failure.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let the operator download the original, unmodified content
  of any file attached to an inventory item, in the form it was uploaded.
- **FR-002**: A download MUST be delivered as an attachment (saved to disk) rather than
  displayed in place, and MUST carry the filename the file was uploaded under.
- **FR-003**: A download MUST return the original content, never a generated thumbnail or
  preview rendition, and MUST report the original content type.
- **FR-004**: The download request MUST identify the file by the same identifier used to
  view that file full size, so that a caller holding one identifier can do both without
  translating between identifier kinds.
- **FR-005**: A download request for an identifier that matches no stored file MUST be
  answered "not found". A download request that matches a stored file MUST NOT fail.
- **FR-006**: Download MUST behave identically whether the stored-file identifiers and the
  item-attachment identifiers coincide or have drifted apart.
- **FR-007**: Both places the operator can ask for a download — the gallery card and the
  full-size viewer — MUST request it in the way FR-004 requires.
- **FR-008**: The system MUST have automated coverage proving that a download returns the
  original bytes and original filename on a database where the two identifier sequences do
  **not** coincide. Coverage that only exercises a database where they happen to match
  does not satisfy this requirement, because that is exactly the condition under which the
  present defect hides.

### Key Entities *(include if data involved)*

- **Stored file**: The uploaded content itself — original bytes, filename, content type,
  size, and generated preview renditions. Identified independently of what it is attached
  to. Created by item photo uploads and by product and purchase attachments alike, which
  is why its identifiers drift from the item-attachment ones.
- **Item attachment**: The link that puts a stored file on an inventory item, with its own
  identifier and its own display ordering. One stored file may have several; a stored file
  created as a product or purchase attachment has none.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The operator can save a copy of any file attached to an item, from either
  the gallery card or the full-size viewer, in a single click.
- **SC-002**: 100% of downloads of an existing attached file succeed. The current success
  rate is 0% — every identifier produces either a not-found answer or a failure.
- **SC-003**: The saved file is byte-for-byte identical to what was uploaded, and its name
  is the name it was uploaded under, for images and PDFs alike.
- **SC-004**: Requests for a file that does not exist are answered "not found" in 100% of
  cases, with no server error recorded.
- **SC-005**: SC-002 through SC-004 hold on a database where the stored-file and
  item-attachment identifier sequences have drifted apart — the condition that exists in
  production today.

## Assumptions

- **The download identifies the file by its stored-file identifier**, matching the
  existing full-size view request and the natural reading of the download address. The
  issue reaches the same conclusion, and the gallery and viewer already hold that
  identifier and already send it — so no caller has to change to satisfy FR-004. The
  alternative, keying on the item-attachment identifier, would require both call sites to
  switch and would leave product and purchase attachments undownloadable by construction.
- **Downloading a file that is attached to no item is acceptable** and needs no separate
  gate. Nothing in the interface offers such a download today; permitting it is a
  consequence of the identifier choice above, not a new capability, and adding a check to
  forbid it would be machinery for no observed problem.
- **No change to what is stored.** The original bytes, filename and content type are
  already recorded on the stored file; this is about reading the right ones, not capturing
  anything new. No migration is expected.
- **No change to the user interface.** Both download controls already exist and are
  already wired up; the fix is that pressing them now produces a file.
- **Existing upload, viewing and deletion behavior is unchanged.** Full-size views and
  thumbnails already work correctly and are out of scope. Deletion's identifier confusion
  was fixed separately (issue #102) and is not revisited here.
- **The operator is the only user** and the application is reachable only on the home LAN,
  so no access control applies to downloads beyond what already applies to viewing.
