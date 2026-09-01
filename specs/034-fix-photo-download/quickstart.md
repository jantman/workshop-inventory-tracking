# Quickstart: Validating the Photo Download Fix

**Feature**: `034-fix-photo-download` | **Date**: 2026-09-01

How to see the defect, and how to confirm it is gone. Implementation belongs in
`tasks.md`; this file is the run guide.

## Prerequisites

- The repository virtualenv at `venv/` (Constitution: local commands run against it).
- `python3.13` reachable on `PATH` for nox — e.g.
  `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`.
- Nothing else. There is no migration to apply and no data to seed for the test runs.

## 1. Reproduce the defect (before the fix)

Against a database that has had at least one product or purchase attachment — which is
any real one:

```bash
# An id that is a Photo but not an association  -> 404
curl -si http://<host>/api/photos/43/download | head -1

# An id that is an association                  -> 500
curl -si http://<host>/api/photos/53/download | head -1
```

Both are failures, and there is no third case. For contrast, the inline view of the same
file works:

```bash
curl -si 'http://<host>/api/photos/43?size=original' | head -1   # 200
```

Issue #131 records this exact pair against `JA000182` on build `ci-7b359bc`.

## 2. Run the automated checks

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
```

Fast (well under a minute). Covers the API-level contract: the download of an existing
photo returns 200 with the original bytes, the original content type and the original
filename in `Content-Disposition`; an unknown id returns 404; and all of it holds on a
database where the Photo and association id sequences have been pushed apart.

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e
```

Slow — **budget 15 minutes warm, 20 cold, and run it detached.** Most agent shells cap a
foreground command at 10 minutes, which is less than the suite takes; use `nohup` and poll
rather than reading a false timeout as a failure. Covers the two UI entry points: the
gallery card button and the viewer modal's download control.

The e2e session must leave the working tree clean. Confirm with `git status --short`
afterwards; anything under `docs/images/screenshots/` means a screenshot test was picked
up and the selection is wrong.

## 3. Validate by hand

Only worthwhile for the whole-loop check; the automated runs above are the gate.

1. Start the app against a database with at least one product attachment on it, so the id
   sequences are genuinely apart.
2. Open an item that has photos: `/inventory/edit/JA######`.
3. **Gallery card** — press the download button on a card. Expected: the browser saves a
   file named as it was uploaded, and opening it shows the full-size image (not the
   thumbnail).
4. **Viewer** — click the thumbnail to open the photo, then press *Download* in the modal
   footer. Expected: the same file.
5. **PDF** — repeat 3 and 4 on an item carrying a PDF. Expected: the original PDF, not the
   generated preview image.
6. **Stale id** — `curl -si http://<host>/api/photos/999999/download | head -1`. Expected:
   `404`, and no traceback in the application log.

## What "done" looks like

| Spec item | Proven by |
|-----------|-----------|
| FR-001, FR-003 | Unit test: response bytes equal the uploaded bytes; content type is the uploaded one. |
| FR-002 | Unit test: `Content-Disposition` is `attachment` and carries the uploaded filename. Not assertable in e2e — see `research.md` R6. |
| FR-004, FR-006 | Unit test: seeded so `photo.id != association.id`, asserted in the test itself. |
| FR-005 | Unit test: unknown id → 404; existing id → 200, never 500. |
| FR-007 | E2E: gallery button and viewer control each produce a download. |
| FR-008 | The drifted-id seeding above, present in the unit test rather than assumed. |

## What this feature does not touch

No migration, no template, no CSS, no JavaScript — so **no screenshot regeneration** and
no `nox -s screenshots` run is required. If a diff in `app/static/js/` or
`app/templates/` appears, the change has grown beyond its plan and the screenshot gate
now applies.
