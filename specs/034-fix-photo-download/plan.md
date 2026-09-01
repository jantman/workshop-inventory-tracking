# Implementation Plan: Photo Download Actually Downloads

**Branch**: `issues/131` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/034-fix-photo-download/spec.md`

## Summary

`GET /api/photos/<id>/download` has never returned a file. The handler
(`app/main/routes.py:2990`) resolves the id twice against two different tables — once
through `PhotoService.get_photo()`, which takes an **association** id, and once through
`get_photo_data()`, which takes a **Photo** id — and then reads `filename` off the
association, which has no such attribute. The first fault makes it wrong on any database
where the two id sequences have drifted; the second makes it fatal even where they have
not.

The fix is to stop resolving the id twice. Add one `PhotoService` method that takes a
Photo id and returns everything the download needs — original bytes, content type,
filename — read from the single `Photo` row, and reduce the handler to one service call
plus `send_file`. The `get_photo()` call disappears from the download path entirely, which
removes both faults at once. Nothing else changes: no schema change, no migration, and no
JavaScript change, because both callers already send the Photo id.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x (`send_file`), SQLAlchemy 2.0.x (legacy `Query`
API, matching `app/photo_service.py`). No new dependency.

**Storage**: MariaDB via PyMySQL in production, SQLite through the same `Storage`
interface in unit tests. **No schema change and no Alembic revision** — every field the
download needs (`photos.filename`, `photos.content_type`, `photos.original_data`) already
exists and is `NOT NULL`.

**Testing**: `nox -s tests` and `nox -s e2e`. New coverage lands in
`tests/unit/test_photo_download.py` (real SQLite through the `test_storage` fixture, not
mocks) and `tests/e2e/test_photo_download.py`.

**Target Platform**: Linux, single Flask process on the home LAN.

**Project Type**: Server-rendered Flask web application (blueprints + Jinja2 + Bootstrap).

**Performance Goals**: None new. The download reads one `photos` row, exactly as the
existing full-size view does.

**Constraints**: The e2e suite is at ~13m 45s against a 15-minute ceiling, so new e2e
coverage must be seeded directly rather than driven through the upload widget. Waits must
be on observable state (Constitution IV).

**Scale/Scope**: One route handler rewritten, one service method added, two test files
added. No UI files touched — which, per the workflow gate, means **no screenshot
regeneration is required**.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Assessment | Verdict |
|-----------|------------|---------|
| **I. Simplicity First** | One new service method and a shorter handler. No new abstraction, no configuration, no compatibility shim for the old id. The alternative designs in `research.md` were rejected for being larger, not smaller. | PASS |
| **II. Layered Architecture Boundaries** | The filename lookup goes into `PhotoService`, not the route. The handler keeps no ORM query and no raw SQL, and gets shorter than it is today. | PASS |
| **III. Exact Numerics** | No measured quantity involved. | N/A |
| **IV. Test Discipline Through Nox** | Run through `nox`. The unit test uses the `test_storage` fixture against a real SQLite database — mocked-session tests cannot express the drifted-id condition FR-008 requires. The e2e test seeds via `PhotoService` and waits on `expect()` and `page.expect_download()`, with no fixed delays. Markers `unit` and `e2e` are already registered. | PASS |
| **V. MariaDB Is the Source of Truth** | No schema change, so no migration. Nothing is hand-edited. | PASS |
| **VI. Item Lifecycle and History Invariants** | Untouched — no add, move, shorten, edit or search path is involved. | PASS |
| **Operating Context / Threat Model** | No authentication or authorization is added. Keying on the Photo id makes product and purchase attachments downloadable; those same rows are already served inline by `GET /api/photos/<id>` and linked from `product/detail.html`, so this exposes nothing new on a LAN-only single-user app. Adding a gate would be hardening against an attacker the threat model excludes. | PASS |
| **Technology Constraints** | New service method matches the file's existing `session.query(...)` style and carries type hints. Errors continue through the handler's existing pattern. | PASS |
| **Development Workflow** | Non-trivial code change → feature branch `issues/131` + PR. No `app/templates/**`, `app/static/css/**` or `app/static/js/**` file changes, so the screenshot gate does not apply. | PASS |

**Result**: No violations. The Complexity Tracking section is therefore omitted.

## Project Structure

### Documentation (this feature)

```text
specs/034-fix-photo-download/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── photo-download.md
├── checklists/
│   └── requirements.md  # From /speckit-specify
├── spec.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
├── photo_service.py          # ADD get_photo_file(photo_id) -> (bytes, content_type, filename)
├── main/
│   └── routes.py             # REWRITE download_photo (line ~2990): one service call
├── database.py               # UNCHANGED — Photo and ItemPhotoAssociation as they are
└── static/js/
    └── photo-manager.js      # UNCHANGED — :587 and :896 already send the Photo id

tests/
├── unit/
│   └── test_photo_download.py    # NEW — real SQLite, drifted id sequences
└── e2e/
    └── test_photo_download.py    # NEW — gallery button and viewer control
```

**Structure Decision**: The existing Flask blueprint layout is kept exactly as it is. The
change is confined to the service layer (`app/photo_service.py`) and one handler in the
`main` blueprint (`app/main/routes.py`), which is where Principle II says each half
belongs. No new module is created — a new file for one function would be the kind of
structure Principle I prohibits.

## Phase 0: Research

See [research.md](./research.md). Six decisions were resolved:

1. **Which id the endpoint takes** — the Photo id. Both callers already send it; the
   alternative changes both callers and excludes attachments by construction.
2. **Where the filename lookup lives** — a new `PhotoService.get_photo_file()`, returning
   plain values rather than an ORM object.
3. **Why not reuse `get_photo_data()` plus a filename lookup** — two queries and two
   failure modes for one read.
4. **Filename encoding in the download header** — Werkzeug already handles non-ASCII;
   nothing to write.
5. **How to prove the drifted-id condition in a test** — a product attachment creates a
   `Photo` row with no association, which is the existing technique in
   `tests/e2e/test_photo_bulk_delete.py`.
6. **What the e2e test can and cannot assert** — the anchor's `download` attribute wins
   over `Content-Disposition` in the browser, so the server-sent filename must be asserted
   at the API level, not in the e2e test.

## Phase 1: Design

- [data-model.md](./data-model.md) — no schema change; documents the two id kinds, why
  they drift, and the `NOT NULL` guarantees the handler may rely on.
- [contracts/photo-download.md](./contracts/photo-download.md) — the HTTP contract for
  `GET /api/photos/<photo_id>/download` and the internal `PhotoService.get_photo_file()`
  signature.
- [quickstart.md](./quickstart.md) — how to reproduce the defect, and how to validate the
  fix by test run and by hand.

### Post-Design Constitution Re-check

Re-evaluated after the design above: **still PASS on every gate**. The design added one
method to an existing service and removed a call from a handler; it introduced no new
module, no new dependency, no migration, and no UI change. The one judgment call worth
restating is the deliberate omission of a "this Photo has no item association" check —
recorded in `research.md` as a decision, and justified by the threat model rather than
overlooked.
