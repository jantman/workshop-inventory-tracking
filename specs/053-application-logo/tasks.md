# Tasks: Application Logo

**Input**: Design documents from `specs/053-application-logo/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/logo-assets.md

**Tests**: Included. The constitution (IV) requires that behavior changes land with tests.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Create the master logo `app/static/img/logo.svg`: a 16-unit viewBox, a rounded tile (`rx=3`, `#0a58ca`), and a white hex-nut path (`fill-rule="evenodd"`, flat sides at x = 3 and 13, hole r = 2.6). Put the regeneration commands in a header comment (research.md §2–3).

## Phase 2: Foundational

- [X] T002 Derive the rasters from the master with the commands in its header: `app/static/img/favicon.ico` (16/32/48), and `extension/icons/icon-16.png`, `icon-48.png`, `icon-128.png`. View the 16 px render magnified to confirm it is legible (SC-003).

## Phase 3: User Story 1 — the browser tab shows the logo (P1) 🎯 MVP

**Independent test**: any page declares an icon, and the icon is served with 200.

- [X] T003 [P] [US1] Write tests in `tests/unit/test_logo.py`: the home page `<head>` carries both `<link rel="icon">` from the contract, each `href` returns 200, and `GET /favicon.ico` returns the same bytes as `/static/img/favicon.ico`.
- [X] T004 [US1] Add the two `<link rel="icon">` lines to `<head>` in `app/templates/base.html`.
- [X] T005 [US1] Add the `GET /favicon.ico` route to `app/main/routes.py`. It sends `img/favicon.ico` from the static folder.

## Phase 4: User Story 2 — the extension icon is the logo (P2)

**Independent test**: every icon the manifest declares is a PNG of its declared size.

- [X] T006 [P] [US2] Add a test to `tests/unit/test_logo.py`: for every `size → path` in the manifest's `icons` and `action.default_icon`, Pillow reads a PNG of exactly `size × size`. (T002 supplies the files, and the manifest is unchanged.)

## Phase 5: User Story 3 — the navbar shows the logo (P3)

**Independent test**: the navbar brand holds `img.brand-logo` and no `bi-tools`, and it still links home.

- [X] T007 [P] [US3] Add tests to `tests/unit/test_logo.py`: the navbar brand contains `img.brand-logo` pointing at `logo.svg`, keeps its link to `/`, and has no `bi-tools`; the home banner `h1` contains `img.brand-logo` and has no `bi-tools`.
- [X] T008 [US3] In `app/templates/base.html`, replace `<i class="bi bi-tools">` in the navbar brand with `<img src="{{ url_for('static', filename='img/logo.svg') }}" class="brand-logo" alt="">`.
- [X] T009 [US3] In `app/templates/index.html`, replace the banner heading's `bi-tools` the same way.
- [X] T010 [US3] In `app/static/css/main.css`, add a `.brand-logo` rule (height 1.5em, width auto, vertical-align middle, margin-right 0.5rem). Remove the `.navbar-brand i` rule if nothing else uses it.

## Phase 6: Polish

- [X] T011 Run `nox -s tests` (the unit suite, including `test_logo.py`).
- [X] T012 Run `nox -s screenshots_headless`, then `nox -s screenshots_verify`. Compare each changed PNG against HEAD and keep only the ones whose navbar or banner actually changed. Revert churn that is only the footer or timestamps, including `metadata.json`, if its only change is timestamps (#77).
- [ ] T013 Run `nox -s e2e` detached (about 20 min) and confirm it passes.
- [X] T014 Confirm `grep -rn "bi-tools" app/templates` returns nothing, and that `docs/capture-extension.md` still tells the operator to reload on upgrade (FR-008, no text change).

## Dependencies

T001 → T002 → the stories. US1, US2 and US3 are independent of one another. T004 and T008 both edit `base.html`, so do them in sequence. The polish phase runs last, and T012 needs T008–T010.

## Parallel opportunities

T003, T006 and T007 are the three test groups. They can be written together, and are then merged into one file.

## Implementation strategy

MVP = Phases 1–3: the favicon alone closes the biggest gap. US2 and US3 are small and ship in the same PR, so the application and the extension never disagree for long.
