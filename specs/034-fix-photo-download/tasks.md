---
description: "Task list for 034-fix-photo-download"
---

# Tasks: Photo Download Actually Downloads

**Input**: Design documents from `/specs/034-fix-photo-download/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/photo-download.md)

**Tests**: **Included, and not optional.** Constitution IV requires a behavior change to land with
tests covering that behavior, and `nox -s tests` and `nox -s e2e` must both be green before merge.
More pointedly: this endpoint already *has* unit tests around it
(`tests/unit/test_photo_service.py`) and they did not catch a handler that has never once returned
a file, because they mock the session and a mock answers to both id kinds. FR-008 exists to stop
that repeating, and it is a statement about how the test is *seeded*, not about how much is
covered.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: Which user story the task serves (US1, US2, US3)
- Every task names the exact file it touches

## Path Conventions

Server-rendered Flask application; existing layout kept exactly (plan.md → Structure Decision).
`app/photo_service.py` for the service half, `app/main/routes.py` for the handler,
`tests/unit/` and `tests/e2e/` for tests, `docs/` for the manual. **No new module, no migration,
and nothing under `app/static/` or `app/templates/`.**

## A note on the phase order

**There is no Setup phase.** No dependency, directory, migration or configuration changes, so the
template's Phase 1 would be make-work.

**Phase 1 is the two test fixtures, and it is the load-bearing phase.** Not the production code —
that is nine lines. The thing that is actually hard to get right here is *seeding a database whose
`photos.id` and `item_photo_associations.id` sequences have come apart*, because a fixture that
does not do that produces tests which pass against the bug. Both fixtures assert the drift they
created, so they fail loudly rather than quietly stop testing anything.

**US1 (Phase 2) carries all the production code.** US2 and US3 add no application code at all —
they are the second entry point and the error boundary of the same endpoint. Their phases are
tests, and that is not a gap in the plan: after Phase 2 the feature works, and Phases 3 and 4 pin
the parts of the spec that Phase 2 does not prove.

**MVP is Phases 1 + 2.** That is issue #131 closed: the gallery's download button produces a file.

---

## Phase 1: Foundational — seeding a drifted database (blocking prerequisite)

**Purpose**: Two fixtures that build the only database shape worth testing against — one where the
Photo id and the association id of the same photo are different numbers.

**⚠️ Blocks everything.** Every test below is worthless without it (research.md R5).

- [X] T001 [P] Create `tests/unit/test_photo_download.py` with a module docstring explaining why the product attachment is load-bearing (borrow the reasoning from `tests/e2e/test_photo_bulk_delete.py`'s fixture docstring), and a `@pytest.fixture` on `test_storage` that: uploads a product attachment via `PhotoService.upload_product_attachment` to create a `Photo` row with no association; inserts an `InventoryItem` row for `JA000900` directly through `test_storage._get_session()` (`PhotoService.upload_photo` refuses an item that does not exist); uploads one JPEG to that item via `upload_photo`; and **asserts `association.photo_id != association.id`** before yielding, so the fixture fails rather than silently stopping producing drift (FR-006, FR-008). Return the ids, the uploaded bytes and the filename. Mark the tests `@pytest.mark.unit`
- [X] T002 [P] Create `tests/e2e/test_photo_download.py` with an `item_with_photo` fixture modeled on `tests/e2e/test_photo_bulk_delete.py:52` — `live_server.add_test_products([...])` then `live_server.add_product_attachments(product.id, 3)` to push the sequences apart, then `live_server.add_test_data([...])` for `JA000901`, then one `PhotoService.upload_photo` against `live_server.storage`. Carry the same "these attachments are not scenery" note. Return the JA ID, the Photo id and the uploaded bytes so the tests can assert on both. Mark the tests `@pytest.mark.e2e`

**Checkpoint**: A test can now ask the question the bug is about.

---

## Phase 2: User Story 1 — Download a photo from the item's gallery (Priority: P1) 🎯 MVP

**Goal**: The download button on a gallery card saves the original file under its original name.

**Independent Test**: Attach a file to an item, click the download button on its card, confirm a
file arrives with the uploaded name, the uploaded content type and byte-for-byte the uploaded
content.

### Tests for User Story 1

> Write these first and **watch them fail**. Today T003 gets a 404 and T004 gets a 404; neither is
> the assertion failing for the right reason yet, which is exactly why running them first matters.

- [X] T003 [US1] Add the image success test to `tests/unit/test_photo_download.py`: `GET /api/photos/{photo_id}/download` through the `client` fixture returns 200; `response.data` equals the uploaded bytes byte-for-byte; `Content-Type` is the uploaded content type; `Content-Disposition` starts with `attachment` and carries the uploaded filename (FR-001, FR-002, FR-003). **This is the only place the server-sent filename can be asserted** — the e2e tests cannot see it (research.md R6), so do not move it
- [X] T004 [US1] Add the PDF test to `tests/unit/test_photo_download.py`: seed a PDF through `upload_photo` (the PDF bytes fixture in `tests/unit/test_photo_service.py:70` is the pattern), download it, and assert the response body is the original PDF and the content type is `application/pdf` — **not** the `image/jpeg` the thumbnail path substitutes for PDFs (`app/photo_service.py:191`). A download that returns the generated preview passes a naive "did I get bytes" check, so assert on the bytes (FR-003)
- [X] T005 [US1] Run `tests/unit/test_photo_download.py` and confirm T003 and T004 fail against the current code before writing T006, recording which failure each one gives. If either *passes* now, the fixture is not producing drift and T001 is wrong

### Implementation for User Story 1

- [X] T006 [US1] Add `get_photo_file(self, photo_id: int) -> Optional[Tuple[bytes, str, str]]` to `app/photo_service.py`, beside `get_photo_data`: query `Photo` by primary key in the file's existing `session.query(...)` style, return `(photo.original_data, photo.content_type, photo.filename)` or `None` when there is no such row, and raise `RuntimeError` on a query failure to match the surrounding methods. Docstring must say **"Photo ID (photos.id) - NOT association ID"**, as `get_photo_data` already does. Return plain values, never the ORM instance — the caller reads them after the session closes (research.md R2)
- [X] T007 [US1] Rewrite `download_photo` in `app/main/routes.py:2990` to make exactly one service call: `result = photo_service.get_photo_file(photo_id)` inside the `with PhotoService(...)` block, 404 with the existing `{'success': False, 'error': 'Photo not found'}` shape when it is `None`, unpack to locals, then `send_file(io.BytesIO(data), mimetype=content_type, as_attachment=True, download_name=filename)`. **Delete the `photo_service.get_photo(photo_id)` call and the second `get_photo_data` call** — both faults leave with them. Do not add a check for a photo with no item association; that omission is a decision (research.md R1, plan.md threat-model row), not an oversight
- [X] T008 [US1] Add a comment above `download_photo` in `app/main/routes.py` naming which id the route takes and why: the Photo id, matching `GET /api/photos/<id>` directly above it, while `DELETE /api/photos/<id>` takes the association id. Cross-reference `PhotoService.get_photo` (association) against `get_photo_file`/`get_photo_data` (Photo) so the next reader of this file cannot repeat the substitution
- [X] T009 [US1] Add the gallery e2e test to `tests/e2e/test_photo_download.py`: `page.goto(f"{live_server.url}/inventory/edit/{ja_id}")`, settle the gallery with `expect(page.locator("#photo-manager-container .photo-card")).to_have_count(1)`, then wrap the click of `.photo-download-btn` in `with page.expect_download() as info:` — that context manager **is** the wait, so no `wait_for_timeout` is needed or permitted (Constitution IV). Assert the downloaded file's bytes equal the seeded bytes, and assert `download.url` ends with `/api/photos/{photo_id}/download` using the **Photo** id, which is what pins FR-004 and FR-007 at the UI level. Do **not** assert `download.suggested_filename` — the page's own `link.download` sets it and it would pass against a server that sent no filename (research.md R6)
- [X] T010 [US1] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and confirm green

**Checkpoint**: Issue #131 is closed. The gallery button produces the original file, on a database
with drifted ids.

---

## Phase 3: User Story 2 — Download from the full-size viewer (Priority: P2)

**Goal**: The download control inside the photo viewer produces the same file as the gallery card.

**Independent Test**: Open a photo in the viewer, use its download control, confirm the saved file
matches the uploaded one.

**No application code.** The viewer's control already points at the same endpoint
(`app/static/js/photo-manager.js:896`), so US1's fix serves it. This phase is the test that says so.

- [X] T011 [US2] Add the viewer e2e test to `tests/e2e/test_photo_download.py`: open the edit page, settle the gallery, click `.photo-view-btn` to open the modal, and settle it with `expect(page.locator("#fallback-image-modal .modal-footer .modal-download-btn")).to_be_visible()` before clicking. Scope the locator to `.modal-footer` — the same class also appears in the PDF-unavailable notice, and an unscoped locator is ambiguous. Wrap the click in `page.expect_download()` and assert the bytes. Add a comment recording *why* the fallback modal is the one under test in e2e: `app/templates/base.html:20,157` skip the PhotoSwipe CDN loads on `localhost`/`127.0.0.1`, so `viewPhoto()` always takes its `showFallbackImageModal()` branch here (research.md R7)

**Checkpoint**: Both entry points to the endpoint are covered.

---

## Phase 4: User Story 3 — Downloading a file that is not there (Priority: P3)

**Goal**: A request for a file that does not exist answers "not found" rather than failing.

**Independent Test**: Request a download for an identifier no file has, and confirm a not-found
response rather than a failure.

**API-level only, deliberately.** The failure this story is about is a 500 from the server; the
page does nothing with the response either way, so an e2e test would spend fifteen seconds of suite
time to observe a status code a `client` fixture reads in milliseconds. Constitution I.

- [X] T012 [US3] Add the not-found tests to `tests/unit/test_photo_download.py`: an id no `photos` row has returns 404 with the `{'success': False, 'error': 'Photo not found'}` body; and — the one that matters — **requesting the association id of the seeded photo does not return 500** (FR-005). On the drifted fixture that id is either a different photo or nothing at all, and today it is the id that produces `'ItemPhotoAssociation' object has no attribute 'filename'`
- [X] T013 [US3] Add a test to `tests/unit/test_photo_download.py` asserting no request in this file logs a handler exception — assert the 404 path is reached through the `None` return, not through the `except` block, e.g. by asserting the response body is exactly the not-found shape rather than the `Failed to download photo: ...` shape (FR-005, second sentence)

**Checkpoint**: All three stories covered; the endpoint has no path left that fails on an id it
should serve.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T014 Add a **Downloading Photos** subsection to `docs/user-manual.md` under *Photo Management*, after *Viewing Photos* (line ~452): the download button on each gallery card and the Download control in the full-size viewer both save the original file under the name it was uploaded with, full size rather than the preview, for images and PDFs alike. The manual has never documented this because it has never worked. **No screenshot** — no UI changed, and `nox -s screenshots` must not run for this feature
- [X] T015 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` **detached** (`nohup` + poll). Budget 15 minutes warm, 20 cold — most agent shells cap a foreground command at 10 minutes and will report a false timeout on a passing run
- [X] T016 Run `git status --short` after the e2e session and confirm the working tree is clean — anything under `docs/images/screenshots/` means screenshot tests were selected and the run is wrong (Constitution IV)
- [X] T017 Confirm the diff touches no file under `app/static/` or `app/templates/`. If it does, the change has outgrown its plan and the screenshot gate now applies (plan.md → Development Workflow row)
- [ ] T018 (not done — no deployed instance available to this session; the e2e tests in
      `tests/e2e/test_photo_download.py` drive both controls in a real browser against a real
      database, and the unit tests cover the 404, so every step below is covered by automation
      except the human eyeball) Walk `quickstart.md` §3 by hand against a database that has product attachments on it: gallery download, viewer download, a PDF, and `curl -si .../api/photos/999999/download`

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Foundational)**: no dependencies — start here. Blocks every other phase.
- **Phase 2 (US1)**: depends on T001 and T002. Contains all production code.
- **Phase 3 (US2)**: depends on Phase 2 — the control it tests is served by US1's fix. Its test
  would fail before T007 for the same reason US1's does.
- **Phase 4 (US3)**: depends on T007. Independent of Phases 2 and 3 otherwise.
- **Phase 5 (Polish)**: depends on Phases 2–4.

### Story independence

The three stories are independently *testable* but not independently *deliverable*: US2 and US3
are additional surfaces of the single endpoint US1 fixes, and neither adds code. This is a bug fix
with one defect in one handler — the honest dependency graph is a chain, and pretending otherwise
would invent three implementations of a nine-line change.

### Within Phase 2

T003 → T004 → T005 (same file, and T005 is the "watch it fail" gate) → T006 → T007 → T008 → T009 → T010.
T006 before T007: the handler calls the method.

### Parallel opportunities

- **T001 and T002** — different files, no shared state. The only genuine parallelism here.
- T003/T004 both edit `tests/unit/test_photo_download.py`, so they are **not** parallel despite
  being independent assertions.
- T009 and T011 both edit `tests/e2e/test_photo_download.py` — not parallel, and T011 depends on
  Phase 2 anyway.

```bash
# Phase 1, both fixtures at once:
Task: "Create tests/unit/test_photo_download.py with the drifted-id fixture"
Task: "Create tests/e2e/test_photo_download.py with the drifted-id fixture"
```

---

## Implementation Strategy

### MVP (Phases 1 + 2)

1. Both fixtures (T001, T002).
2. The failing API tests (T003–T005) — do not skip T005.
3. The service method and the handler (T006–T008).
4. The gallery e2e test (T009) and `nox -s tests` (T010).
5. **Stop and validate**: the download button produces the original file.

That is issue #131 closed. Phases 3–5 add the second entry point's test, the error boundary and
the manual.

### Incremental delivery

Phase 2 → the feature works. Phase 3 → the viewer is covered. Phase 4 → the error boundary is
pinned. Phase 5 → the run is verified end to end and documented. Every phase after 2 is additive
and cannot break the one before it, because none of them changes application code.

---

## Notes

- **The one thing not to get wrong**: if a test passes before T006, the fixture is not producing
  drifted ids. Fix the fixture, not the test.
- Both branches of `download_photo` must be reachable through `get_photo_file` returning a value
  or `None`. If a request that matches a row can still reach the `except`, the fix is incomplete.
- Commit after each task or logical group; feature branch `issues/131`, merged by PR
  (Constitution → Development Workflow).
- Renaming `PhotoService.get_photo` to something that stops inviting this bug is **out of scope**
  and recorded in `research.md` R2. Do not fold it in here.
