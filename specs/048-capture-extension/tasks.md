---
description: "Task list for the Browser Capture Extension"
---

# Tasks: Browser Capture Extension

**Input**: Design documents from `/specs/048-capture-extension/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: **Required, not optional.** Constitution Principle IV: "Changes that alter behavior
MUST land with tests covering that behavior, and `nox -s tests` and `nox -s e2e` MUST pass
before a change is merged." Test tasks below are therefore part of the work, not an add-on.

**Organization**: Tasks are grouped by user story. Phase 2 is unusually large for this feature
and that is deliberate — see the note at its head.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Every task names its file path

## Path Conventions

Per [plan.md](./plan.md#source-code-repository-root): the extension is a top-level `extension/`
directory, loadable unpacked exactly as it sits in the repository. Application code is under
`app/`, tests under `tests/`, documentation under `docs/`.

**Run everything through the project virtualenv and `nox`**, never bare `pytest`. `nox -s e2e`
takes ~20 minutes warm and outlasts most tool timeouts — run it detached and poll.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: The extension directory exists and loads unpacked, doing nothing yet.

- [ ] T001 Create `extension/manifest.json`: manifest_version 3, name, description, `version` matching `pyproject.toml`'s `2.0.0`, `permissions` of exactly `scripting`/`storage`/`contextMenus`/`activeTab`, no `host_permissions`, `background.service_worker`, `options_page`, `action` — per [contracts/extension-surface.md](./contracts/extension-surface.md#declared-in-the-manifest)
- [ ] T002 [P] Add `extension/icons/` with the sizes the manifest declares (16, 48, 128)
- [ ] T003 [P] Add `capture-extension.zip` to `.gitignore` so a local package build never gets committed
- [ ] T004 Confirm the directory loads via `chrome://extensions` → Load unpacked with no manifest errors

**Checkpoint**: the extension installs and shows its icon. It captures nothing.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story can be verified until this phase completes.

**Why this phase is large.** Moving the reader out of `app/static/js/` breaks
`_capture_bookmarklet()`, the template that renders it, six test assertions about its address,
and the driver that ~158 e2e tests reach the readers through. Those are one change, not five —
landing them separately leaves the suite red in between. The milestone is: the reader lives in
the extension, the bookmarklet is gone, and the whole suite is green again.

### The reader moves and changes shape

- [ ] T005 `git mv app/static/js/capture-agent.js extension/capture-agent.js` — preserve history; the readers themselves are not edited
- [ ] T006 In `extension/capture-agent.js`, replace the trailing dispatch IIFE (from `const script = document.currentScript;` to end of file) with an entry point that takes no arguments, dispatches on `location` exactly as before, and **returns a promise for the payload** `{url, listing_title, listing, order?, vendor?}` — per [contracts/extension-transport.md](./contracts/extension-transport.md#the-readers-own-interface-after-this-feature). `order` and `vendor` MUST be absent, not null or empty, when they do not apply
- [ ] T007 In `extension/capture-agent.js`, delete `submitCapture()` and the `data-endpoint` read plus its "no endpoint" console error — the reader no longer submits and no longer needs the address
- [ ] T008 In `extension/capture-agent.js`, reduce `showProgress()` to the vendor-page banner only, dropping the half that wrote into a pre-opened landing tab — research.md §3 removed that tab
- [ ] T009 Update the module docstring at the top of `extension/capture-agent.js`: it currently describes a bookmarklet loader, a form submission and a mixed-content rationale that no longer apply. State instead that it is injected into an isolated world and returns its payload

### The bookmarklet is removed

- [ ] T010 Remove `_capture_bookmarklet()` from `app/product/routes.py` and the `bookmarklet=` argument passed to the template from `_capture_page()`
- [ ] T011 In `app/templates/product/capture.html`, remove the `#bookmarklet-http-warning` alert and the `#capture-bookmarklet` control, and replace the surrounding "The faster way" card body with a pointer to the extension and where to get it (FR-018). Keep the card; the paste box beside it is untouched (FR-019)
- [ ] T012 [P] Remove the four bookmarklet-address assertions from `tests/unit/test_proxy_headers.py` (~lines 117, 127, 143, 163). Keep every other proxy-header assertion — `X-Forwarded-Proto`/`-Port` still matter to the rest of the app
- [ ] T013 [P] Remove the two bookmarklet-href assertions from `tests/e2e/test_order_capture.py` (~lines 290, 317)
- [ ] T014 [P] Update the stale references to `app/static/js/capture-agent.js` in the comments of `app/services/amazon_order_export.py` and `app/models.py` to the new path

### The e2e driver is converted

- [ ] T015 In `tests/e2e/test_product_page_capture.py`, replace `run_bookmarklet()` with a driver that injects `extension/capture-agent.js` from disk into the fixture page, calls the entry point, and posts the returned payload to `/api/capture` the way the extension's submit page will. Keep the function's signature and its `landing` parameter so the three importing modules need no change. Document in its docstring what it no longer covers (the submission) and where that is covered instead — research.md §9
- [ ] T016 Update the module docstring of `tests/e2e/test_product_page_capture.py`, which currently explains the bookmarklet-as-loader design in its opening paragraphs
- [ ] T017 Run `nox -s tests` and `nox -s e2e` (detached, ~20 min) and confirm green, with a clean working tree afterwards

**Checkpoint**: exactly one transport exists in the repository, the reader lives in the
extension, and the suite passes. The extension still captures nothing.

---

## Phase 3: User Story 1 - Capture a McMaster order (Priority: P1) 🎯 MVP

**Goal**: The thing that is impossible today. Invoke capture on a McMaster order page and land
on the application's order review.

**Independent test**: With the extension installed and its stored address seeded, invoke capture
on a McMaster order fixture; the order review opens listing the order's lines.

### Implementation

- [ ] T018 [US1] Create `extension/storage.js`: read and write the configured address in `chrome.storage.sync`, with the normalization from [data-model.md](./data-model.md#configured-application-address) (trim whitespace, strip trailing slashes) applied on write
- [ ] T019 [US1] Create `extension/background.js` — the service worker. On the action being clicked: read the address; if unset, open the options page and stop (FR-011, and **never** fail silently); otherwise inject `capture-agent.js` into the active tab with the default isolated world, then a second `executeScript` invoking the entry point, awaiting its payload — research.md §1, §7
- [ ] T020 [US1] In `extension/background.js`, write the payload plus the resolved address to `chrome.storage.session` under a single-use key and open a tab on `submit.html` carrying that key — research.md §6
- [ ] T021 [US1] Create `extension/submit.html` and `extension/submit.js`: read the keyed value, delete it, build a form with exactly the fields in [contracts/extension-transport.md](./contracts/extension-transport.md#what-the-extension-sends), and submit it to `<address>/api/capture` **in its own tab**. Omit `order` and `vendor` entirely when absent. If the key holds nothing, say so rather than submitting an empty form
- [ ] T022 [US1] In `extension/background.js`, report a reader that threw as "the page could not be read" without submitting a partial payload — per the preconditions table in [contracts/extension-transport.md](./contracts/extension-transport.md#preconditions-the-extension-enforces-before-submitting)

### Tests

- [ ] T023 [US1] Create `tests/e2e/test_capture_extension.py` with a fixture launching `launch_persistent_context` with `channel="chromium"` and `--load-extension`, recovering the extension id from `context.service_workers[0].url`. Wait on the worker as observable state — **no fixed waits** (Constitution IV); Playwright exposes a service-worker event for exactly this
- [ ] T024 [US1] In `tests/e2e/test_capture_extension.py`, add the McMaster order path end to end: seed the address into `chrome.storage.sync`, open the McMaster order fixture, invoke the action, assert the order review renders with its lines
- [ ] T025 [US1] In `tests/e2e/test_capture_extension.py`, assert the vendor tab is still open and has not navigated after a capture — the property research.md §3 buys, which nothing else would notice regressing

**Checkpoint**: US1 is independently deliverable. A McMaster order can be captured — the issue's
core defect is closed.

---

## Phase 4: User Story 2 - Keep capturing everything that already worked (Priority: P2)

**Goal**: The three page kinds that work today arrive through the extension with nothing lost.

**Independent test**: Invoke capture on an Amazon order, an Amazon listing and a McMaster
product fixture; each produces what the bookmarklet produced.

- [ ] T026 [US2] Verify `extension/background.js` needs no per-vendor branching — the entry point already dispatches on `location`. Add none; if a branch appears here the dispatch has been duplicated, which [data-model.md](./data-model.md#supported-page-kind) warns against
- [ ] T027 [US2] In `extension/background.js`, handle the unrecognized-page case: tell the operator this is not a page it can read (FR-008), asking the reader rather than reimplementing the path patterns
- [ ] T028 [US2] Confirm the progress banner (FR-007) still appears on the vendor page during a multi-line Amazon order read, now that it no longer writes into a pre-opened tab
- [ ] T029 [P] [US2] In `tests/e2e/test_capture_extension.py`, add the Amazon order path through the real extension, asserting per-line listing details survive — this is the path whose same-origin `/dp/<ASIN>` fetches research.md §2 says are unchanged
- [ ] T030 [P] [US2] In `tests/e2e/test_capture_extension.py`, add the McMaster product and Amazon listing paths through the real extension
- [ ] T031 [P] [US2] In `tests/e2e/test_capture_extension.py`, assert an unsupported page reports that it cannot be read and submits nothing
- [ ] T032 [US2] Assert the plain Amazon listing capture sends **no `vendor` field at all** — not an empty one (FR-003). This is the one field whose absence is load-bearing

**Checkpoint**: all four page kinds capture through the extension.

---

## Phase 5: User Story 3 - Point the extension at my own installation (Priority: P2)

**Goal**: The address is configurable, validated, and persistent.

**Independent test**: Install, open options, enter an address, save; restart the browser and
confirm a capture still works.

- [ ] T033 [US3] Create `extension/options.html` and `extension/options.js`: one address field pre-filled from storage, a save action, and the extension's own version displayed (FR-014)
- [ ] T034 [US3] In `extension/options.js`, apply the accept/reject table from [data-model.md](./data-model.md#configured-application-address): reject empty, reject unparseable with the reason shown, **save but warn** when not `https` (FR-012), save when valid
- [ ] T035 [P] [US3] In `tests/e2e/test_capture_extension.py`, assert the options page saves an address and a subsequent capture uses it
- [ ] T036 [P] [US3] In `tests/e2e/test_capture_extension.py`, assert an address entered with a trailing slash and surrounding whitespace is normalized and still reaches the endpoint (FR-013)
- [ ] T037 [P] [US3] In `tests/e2e/test_capture_extension.py`, assert an `http://` address saves and shows the warning (FR-012)
- [ ] T038 [US3] In `tests/e2e/test_capture_extension.py`, assert that with **no** address configured, invoking capture opens the options page and submits nothing (FR-011). This is the regression test for the bug's own symptom — silence — and is the most important test in the file

**Checkpoint**: the extension works for any self-hoster, not just this one.

---

## Phase 6: User Story 4 - Install and update from a published build (Priority: P2)

**Goal**: CI publishes the package; documentation explains install, configure, use and update.

**Independent test**: From a completed build, download the package, follow the documentation,
reach a first capture without editing a file.

- [ ] T039 [US4] Create `tests/unit/test_extension_manifest.py` asserting `extension/manifest.json`'s `version` equals `pyproject.toml`'s `version` (FR-024). Read both files; do not hardcode the number
- [ ] T040 [US4] Add an `extension-package` job to `.github/workflows/test.yml` that zips `extension/` and uploads it with `actions/upload-artifact@v7`, mirroring the `docker-build` job's shape (FR-022)
- [ ] T041 [US4] In `.github/workflows/release.yml`, build the same zip and attach it via the existing `softprops/action-gh-release@v2` step's `files:` input, and mention it in that step's release `body:` beside the Docker pull instructions (FR-023)
- [ ] T042 [US4] Add the "keep in sync" comment to both workflow additions, matching the convention the Docker jobs already carry at `test.yml:271` and in `release.yml`
- [ ] T043 [US4] Create `docs/capture-extension.md` covering: what it is and why it replaced the bookmarklet, install by Load unpacked, configuring the address, the TLS requirement, the supported pages, updating by replace-and-reload, and — explicitly — that changing the readers now requires a new extension version installed by hand (FR-025, FR-026)
- [ ] T044 [P] [US4] Cross-reference `docs/capture-extension.md` from `docs/user-manual.md` and `docs/deployment-guide.md` wherever the bookmarklet is described today

**Checkpoint**: the extension is reachable by someone who did not build it.

---

## Phase 7: User Story 5 - Start a capture from the right-click menu (Priority: P3)

**Goal**: A context-menu entry on the supported sites only.

**This is the droppable story.** FR-016 is the specification's only SHOULD. It shares the
worker's capture routine, so abandoning it removes a registration and nothing else.

**Independent test**: Right-click a supported page and capture from the menu; right-click an
unrelated page and find no entry.

- [ ] T045 [US5] In `extension/background.js`, register a context-menu item on install, scoped with `documentUrlPatterns` to the supported vendor sites, whose handler calls the same capture routine the action does — no capture logic of its own
- [ ] T046 [P] [US5] In `tests/e2e/test_capture_extension.py`, assert the menu-invoked capture produces the same result as the action-invoked one
- [ ] T047 [P] [US5] Document the context-menu entry in `docs/capture-extension.md`

**Checkpoint**: both entry points work identically.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T048 Regenerate documentation screenshots (`nox -s screenshots_headless`) and commit them — `app/templates/product/capture.html` changed and CI blocks merge on stale screenshots (Constitution, Development Workflow)
- [ ] T049 Run `nox -s screenshots_verify` and confirm valid PNG, RGB/RGBA, under 500KB
- [ ] T050 [P] Grep the repository for surviving references to the bookmarklet in prose and comments (`grep -ril bookmarklet app/ tests/ docs/ README.md`) and update each, leaving `specs/` untouched — it is the frozen record
- [ ] T051 [P] Confirm no `wait_for_timeout`, `time.sleep` or `networkidle` was introduced in `tests/e2e/test_capture_extension.py` (Constitution IV — the suite executes zero fixed waits and must continue to)
- [ ] T052 Run the full gate: `nox -s tests` and `nox -s e2e` (detached), and confirm the working tree is clean afterwards
- [ ] T053 Walk [quickstart.md](./quickstart.md) §3 against the real sites — the manual checks CI cannot do. **§3a and §3b are the feature**; no local fixture carries McMaster's content policy, so nothing but a real McMaster page proves the bug is fixed
- [ ] T054 Record the quickstart results in this file, as feature 047 did in its `tasks.md`

---

## Dependencies & Execution Order

### Phase dependencies

```
Phase 1 (Setup)
   └─▶ Phase 2 (Foundational)  ◀── BLOCKS EVERYTHING
          └─▶ Phase 3 (US1, P1) ── MVP
                 ├─▶ Phase 4 (US2, P2)
                 ├─▶ Phase 5 (US3, P2)
                 ├─▶ Phase 6 (US4, P2)
                 └─▶ Phase 7 (US5, P3)  ── droppable
                        └─▶ Phase 8 (Polish)
```

### User story dependencies

- **US1** depends on Phase 2 only. It is the MVP and closes the issue.
- **US2**, **US3**, **US4** each depend on US1's worker and submit page, and are independent of
  one another — they touch different files and can proceed in parallel.
- **US5** depends on US1's capture routine. Nothing depends on US5.

**One honest caveat**: US1's tests seed the address directly into storage because the options
screen is US3's work. US1 is independently *testable* that way, but not independently *usable* —
a person installing only US1 would have no way to set the address. US3 is what makes it usable,
which is why both are needed before anything ships.

### Within each story

Implementation before its tests within a phase, because the tests drive the real extension and
have nothing to load until it exists. Across phases, the ordering above holds.

### Parallel opportunities

- Phase 1: T002, T003 together
- Phase 2: T012, T013, T014 together (three separate files, all pure deletion)
- Phase 4: T029, T030, T031 together
- Phase 5: T035, T036, T037 together
- Phase 8: T050, T051 together
- **Phases 4, 5 and 6 as whole units**, once Phase 3 lands

---

## Parallel Example: Phase 2's deletions

```bash
# Three independent files, no shared state:
#   T012  tests/unit/test_proxy_headers.py      — drop 4 assertions
#   T013  tests/e2e/test_order_capture.py       — drop 2 assertions
#   T014  app/services/amazon_order_export.py,
#         app/models.py                          — fix stale path comments
```

## Parallel Example: Phase 4's page kinds

```bash
#   T029  Amazon order        through the real extension
#   T030  McMaster product + Amazon listing
#   T031  unsupported page reports and submits nothing
# All three add independent test functions to the same new file — coordinate the
# file, not the work.
```

---

## Implementation Strategy

### MVP (Phases 1–3 + Phase 5)

Phase 3 alone closes issue #133 mechanically, but Phase 5 is what makes it installable by a
person rather than a test. Treat **Phases 1, 2, 3 and 5** as the smallest shippable slice.

### Incremental delivery

1. **Phases 1–2** — the swap. One transport, suite green. Nothing user-visible yet, and this is
   the riskiest phase: it touches ~158 tests' driver.
2. **Phase 3** — McMaster orders capture. The defect is closed.
3. **Phase 5** — anyone can configure it.
4. **Phase 4** — the other three page kinds confirmed, no regression.
5. **Phase 6** — published and documented.
6. **Phase 7** — the context menu, if it is cheap. Drop it if it is not.
7. **Phase 8** — screenshots, the full gate, and the manual checks against real vendor pages.

### What to do if Phase 2 goes badly

Phase 2 is the one place this feature can get expensive, because the e2e driver conversion
(T015) touches the entry point of the suite's largest file. If the converted driver cannot
reproduce what the bookmarklet-clicking one did, **stop and reconsider the split** rather than
weakening assertions to make it pass — research.md §9 chose this split over running the whole
suite under a persistent context, and that choice is reversible.

---

## Notes

- **Tests are mandatory here**, per Constitution Principle IV. They are listed inside each
  story's phase rather than gathered at the end.
- **`nox`, never bare `pytest`.** `nox -s e2e` needs ≥20 minutes and outlasts most tool timeouts
  — run it detached.
- **A test run must leave the working tree clean.** Screenshot generation is a separate session
  (T048) and is not part of the e2e gate.
- **No database work anywhere in this list** — no table, no column, no Alembic revision. If a
  migration appears, something has gone wrong.
- **`specs/` is never swept** for terminology or stale references; it is the frozen record.
