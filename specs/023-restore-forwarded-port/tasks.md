---

description: "Task list for feature 023 — restore the browser's port behind a reverse proxy"
---

# Tasks: Restore the Browser's Port Behind a Reverse Proxy

**Input**: Design documents from `/specs/023-restore-forwarded-port/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/proxy-headers.md](contracts/proxy-headers.md),
[quickstart.md](quickstart.md)

**Tests**: Required, not optional. FR-008, FR-009 and FR-010 mandate them and SC-004 makes their
failing first the acceptance criterion. This is not a TDD preference — it is the feature.

**Organization**: Tasks are grouped by user story, with one deliberate deviation described below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths are given in every task

## Path Conventions

Single Flask project at the repository root: `app/`, `tests/unit/`, `docs/`. No `src/` directory.

---

## Read this before starting: two things that will otherwise be got wrong

**1. Every new test is written before the fix, and all of them live in Phase 2.**

The template would put each story's tests inside that story's phase. That does not work here.
FR-008, FR-009 and SC-004 require the new coverage to be **seen failing** against the code as it
stands — and the moment `app/__init__.py` changes, that observation is gone and can only be recovered
by reverting. US1's phase is where the fix lands, so any test written in US2's phase afterwards could
never be seen red. The red observation is therefore a blocking prerequisite shared by both stories,
which is exactly what Phase 2 is for. Each test task names the requirement and the story it serves,
so traceability survives the move.

**2. Not all four new tests are red-first, and expecting them to be will waste an hour.**

They have three distinct signatures. Confusing them will read as a broken test rather than as the
design:

| Test | Today | With `x_port=1`, no guard | Finished |
|---|---|---|---|
| T005 bookmarklet addresses carry the port (FR-008) | **FAIL** | pass | pass |
| T006 believed host and same-origin (FR-009) | **FAIL** | pass | pass |
| T007 default port is omitted, no-proxy unchanged (FR-003/FR-010) | pass | pass | pass |
| T008 malformed port does not corrupt the host (FR-007) | pass | **FAIL** | pass |

T007 is a no-regression test and is *supposed* to be green throughout — it is what proves the fix did
not move the paths the end-to-end suite cannot see. T008 goes red only in the middle, which is the
entire evidence that the guard is a regression control and not speculative hardening; T011 exists
solely to make that observation.

---

## Phase 1: Setup

**Purpose**: Get onto a branch and establish that the starting point is green

- [X] T001 Create and switch to branch `issues/114` from `main` (code change → branch + PR per this repository's workflow; the spec directory rides along on the same PR)
- [X] T002 Establish the baseline: run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and confirm it passes before anything is touched, so a later failure is attributable to this work

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Write all new coverage and observe how it behaves *before* the fix. See "Read this
before starting" above for why this is not inside the story phases.

**⚠️ CRITICAL**: `app/__init__.py` MUST NOT be edited until T009 is complete. Editing it earlier
destroys the evidence SC-004 requires and cannot be undone without a revert.

- [X] T003 Add a helper to `tests/unit/test_proxy_headers.py` that captures `flask.request.host`, `request.scheme` and `request.is_secure` from inside a request via an `after_request` hook on the `app` fixture, and returns them alongside the response — the values `ProxyFix` produces are not visible on `response.request`, which reports the pre-middleware environ and will silently report `localhost` for every case
- [X] T004 Extend the module docstring of `tests/unit/test_proxy_headers.py` to record the second gap this file now covers: the port, issue #114, and the fact that no test here used a non-default port until now, which is why a defect disabling every write shipped unnoticed
- [X] T005 Add a test class to `tests/unit/test_proxy_headers.py` asserting that with `X-Forwarded-Proto: https`, `X-Forwarded-Host: titan.example.com` and `X-Forwarded-Port: 15603`, **both** bookmarklet addresses read `https://titan.example.com:15603/...` — the agent script and the `/api/capture` endpoint (FR-008, FR-005; serves US2). Reuse the existing `bookmarklet_of` helper
- [X] T006 Add a test to `tests/unit/test_proxy_headers.py` asserting that for the same headers the believed host (via T003's helper) is `titan.example.com:15603`, and that `flask_wtf.csrf.same_origin('https://titan.example.com:15603/products/capture', f'https://{host}/')` is true — that second expression is built exactly as `flask_wtf.csrf.CSRFProtect.protect` builds it, which is what makes this a test of the refused POST rather than a test near it (FR-009, FR-004; serves US1)
- [X] T007 Add tests to `tests/unit/test_proxy_headers.py` covering the paths that must not move: `X-Forwarded-Port: 443` over `https` and `X-Forwarded-Port: 80` over `http` both yield addresses with **no** port and a believed host with no port; and the no-proxy case is byte-for-byte what it is today (FR-003, FR-006, FR-010; SC-006). Expect these to pass immediately — see the signature table above
- [X] T008 Add a test to `tests/unit/test_proxy_headers.py` asserting that with `X-Forwarded-Port: not-a-port` the believed host is still `titan.example.com` and neither bookmarklet address contains `https:///` (FR-007). Expect this to pass today and to fail after T009 — that is the point of it
- [X] T009 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests -- -k proxy_headers` and record the outcome against the signature table: T005 and T006 MUST fail, T007 and T008 MUST pass, and every pre-existing test in the file MUST still pass. This recorded observation is SC-004's evidence — if T005 or T006 passes here, it is not exercising the defect and must be corrected before proceeding

**Checkpoint**: The defect is now pinned by two failing tests. The fix can begin.

---

## Phase 3: User Story 1 - The deployment can save data again (Priority: P1) 🎯 MVP

**Goal**: A form submitted over HTTPS on a non-default port is accepted and written, instead of being
refused with `400 Bad Request — The referrer does not match the host`.

**Independent Test**: T006 turns green — the application's believed origin now matches the browser's,
which is the exact comparison the referrer check performs. Confirmed live by T023 once a build is
deployed.

### Implementation for User Story 1

- [X] T010 [US1] Add `x_port=1` to the `ProxyFix` call at `app/__init__.py:32`, and extend the comment block above it to say what the port is for — that without it the believed host loses the port, every secure form submission is refused by the referrer check, and the bookmarklet points at a port nothing listens on (issue #114). The existing comment explains the scheme and host for issue #89; this is the same explanation for the third header
- [X] T011 [US1] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests -- -k proxy_headers` and record that T005 and T006 now pass **and that T008 now fails**. Do not skip this intermediate run: the T008 failure is the only direct evidence that the guard in T012 prevents a regression this change introduces, rather than defending against a hypothetical. It is what justifies that row of the plan's Complexity Tracking table
- [X] T012 [US1] In `app/__init__.py`, before the `ProxyFix` wrapping, discard `HTTP_X_FORWARDED_PORT` from the WSGI environ when its value is not a plain decimal number, so the arriving host stands. Keep it to a few lines and comment why: `ProxyFix` composes `host:not-a-port`, and `werkzeug.sansio.utils.get_host` returns the **empty string** for a host containing invalid characters, so every address the app builds becomes `https:///...` with no error and no log line. Do not add a range check on the number — a well-formed but wrong port produces a visibly wrong address the operator can read
- [X] T013 [US1] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` in full and confirm every test passes, including the pre-existing `TestPlainHttpIsUnchanged` and default-host cases in `tests/unit/test_proxy_headers.py` (SC-005, SC-006)

**Checkpoint**: The write path is fixed and covered. This is the MVP — everything after it is the
bookmarklet, the documentation, and getting the fix onto the deployment.

---

## Phase 4: User Story 2 - A bookmarklet dragged from the deployment works (Priority: P2)

**Goal**: Both addresses baked into the capture bookmarklet carry the browser-visible port, so
clicking it on a vendor listing loads the agent instead of hanging on a port nothing listens on.

**Independent Test**: T005 turns green. Confirmed live by T024 once a build is deployed.

**No application code changes in this phase.** US2 is delivered entirely by T010, which is what the
spec says: the bookmarklet is the visible symptom of the same missing port. What is left here is the
comment that stops the next reader re-deriving it.

- [X] T014 [US2] Confirm T005 passes and record both address values it asserts (SC-003 at the unit level)
- [X] T015 [US2] Extend the `_capture_bookmarklet` docstring in `app/product/routes.py` (around line 577) so its existing paragraph about `request.scheme` and the TLS caveat also names the port: these addresses carry whatever port the proxy declares, and a deployment on a non-default port that does not declare one hands out a bookmarklet that cannot load (issue #114). This is the one place a reader meets `_external=True` in this codebase

**Checkpoint**: Both stories' automated evidence is green. Nothing is deployed yet.

---

## Phase 5: User Story 3 - The gap that hid this closes behind it (Priority: P3)

**Goal**: The next person to change how the application resolves its own address is told immediately
if they break a non-default-port deployment, and the person deploying it finds the port requirement
in the configuration they are copying rather than in prose they may skim.

**Independent Test**: An operator can follow the deployment guide's reverse-proxy section end to end
on a non-default port and get a working deployment without reading this spec or the source (SC-007).

- [X] T016 [P] [US3] In `docs/deployment-guide.md`, "Serving Behind a TLS Reverse Proxy": add `proxy_set_header X-Forwarded-Port $server_port;` to the nginx block, and extend the prose to state that the port travels in its own header and what breaks without it — refused form submissions and a dead bookmarklet, not just a cosmetic address. Note that `$host` deliberately excludes the port. Use [contracts/proxy-headers.md](contracts/proxy-headers.md) as the source (FR-011)
- [X] T017 [P] [US3] In `docs/troubleshooting-guide.md`, "Common Nginx Issues": add a sixth entry for a missing `X-Forwarded-Port` beside the existing fifth entry for a missing `X-Forwarded-Proto`, naming both symptoms — `400 Bad Request — The referrer does not match the host` on any form, and a bookmarklet that does nothing when clicked — and linking to the deployment guide section (FR-012)
- [X] T018 [US3] Confirm this feature adds **no new** lint violations to `app/__init__.py`, `app/product/routes.py` and `tests/unit/test_proxy_headers.py`, by counting flake8 output against each file's pre-feature content
  - **Revised during implementation, and the original wording was not achievable.** `nox -s lint` does not pass on `main` and never has: it reports **7,269** violations across `app/` and `tests/` (3,726 E501, 2,610 W293, …), of which **121** are in the three files this feature touches. The noxfile itself calls the session a "future enhancement". Fixing "anything reported" in those files would mean reformatting 107 unrelated lines of `app/product/routes.py` inside a port fix — a large unrelated diff, and outside this feature's stated scope. Measured result: `app/__init__.py` 8 → **7** (a blank line fixed a pre-existing E302), `app/product/routes.py` 107 → **107**, `tests/unit/test_proxy_headers.py` 6 → **6**. **Delta: −1.** Repository-wide lint remains red for reasons that predate this branch
- [X] T019 [US3] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` **detached with polling** — it runs about 8m 15s warm, longer than a 10-minute foreground command allows, and needs at least a 15-minute allowance. Expect it to be entirely unaffected: it runs over plain HTTP on a default-port origin, so `request.is_secure` is false and the referrer check is never reached. Afterwards confirm `git status` is clean — a test run must not modify tracked files
- [X] T020 [US3] Confirm `grep -ric "catalogue" README.md docs/ app/ tests/` still returns nothing after the documentation edits

**Checkpoint**: Everything that can be verified without a deployment is verified.

---

## Phase 6: Release & Live Verification

**Purpose**: Get the fix onto the deployment and settle the three success criteria that no test can
reach. Nothing in this phase can be done from the working tree alone.

**⚠️ T021 is a delivery blocker, not bookkeeping.** The release workflow builds and pushes a
container image only when the version exceeds the latest GitHub release; on an unchanged version an
ordinary merge deliberately does nothing. Without the bump the fix is merged, no image is published,
the deployment stays broken, and SC-001, SC-002, SC-003 and SC-007 cannot be checked at all.

- [X] T021 Bump `version` in `pyproject.toml` from `0.1.0` to `0.1.1` — PATCH, per the deployment guide's own rule for a bug fix plus documentation. No other file needs touching: `app/version.py` reads `pyproject.toml` as the single source of truth
- [X] T022 Opened as PR #115; merged 2026-08-22, which closed #114. Original text: open a pull request from `issues/114` referencing issue #114, and note in the description that it also unblocks #113's remaining write-path task
- [~] T023 **Superseded during execution** — the deployment runs PR #115's CI image
  (`:ci-1534b60e…`), which `test.yml`'s `docker-build` job pushes on every PR. That made
  verification possible *before* merge instead of after, which is the better order: a
  problem gets fixed on the branch rather than in a follow-up release. Still to do after
  merge — confirm the `Release` workflow published `v0.1.1` and the `:0.1.1` / `:latest` images.
  **Deploying that image is deliberately deferred**: the owner is keeping the deployment on the
  verified CI build while other work is in flight. The release exists to be pinned later
- [X] T024 Apply the `X-Forwarded-Port` line from [contracts/proxy-headers.md](contracts/proxy-headers.md) to the deployment's proxy configuration and reload it
- [X] T025 Verify SC-003 and the contract: `curl -s https://titan.jasonantman.com:15603/products/capture | grep -o 'id="capture-bookmarklet"[^>]*'` — both addresses must read `https://titan.jasonantman.com:15603/...`. If the port is still absent here, the proxy is not sending the header and no further application change will help
- [X] T026 Verify SC-001 (User Story 1, the criterion that matters most): in a browser over `https` on `:15603`, edit an item and save. The change must be written, and specifically must **not** return `400 Bad Request — The referrer does not match the host`
- [X] T027 **Done.** The agent script at the bookmarklet's address answers 200
  (`text/javascript`, 45,950 bytes), and the owner confirmed the end-to-end journey by hand on
  2026-08-22 against `B0G43FCHFX` — the listing the defect was found on. SC-002 satisfied.
  Original text: verify SC-002 (User Story 2): drag the bookmarklet **fresh** from `/products/capture` — not a previously dragged one, and with no hand-correction of its address, which is how #113's verification worked around this — and click it on an Amazon listing. A tab must open on the confirmation page. This is #80 §1a check A1, which passed before 2026-08-19 and fails today
- [X] T028 Results recorded in `specs/023-restore-forwarded-port/verification.md`; #114 closes via
  the PR's `Fixes` line. Original text: and comment them on issue #114, then close it
- [X] T029 Commented on #113 on 2026-08-22, explicitly *not* closing it. Original text: comment on #113 that its blocked step — confirming a capture and measuring a stored file to show every gallery image is a full-resolution original (022 SC-010 / #80 §1b B4) — is now unblocked. **Do not close it**: T026 proves the write path works, it does not perform that measurement, and the spec puts it explicitly out of scope

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no dependencies
- **Phase 2 (Foundational)**: depends on Phase 1. **Blocks everything.** Its purpose is an
  observation that a single edit in Phase 3 destroys permanently
- **Phase 3 (US1)**: depends on Phase 2 completing through T009
- **Phase 4 (US2)**: depends on T010. Contains no code change of its own
- **Phase 5 (US3)**: T016, T017 and T020 depend on nothing but the branch and could be done at any
  point; T018 and T019 must follow all code edits
- **Phase 6**: depends on everything, and on a merge and a published image

### The one hard ordering rule

```text
T003 … T008  (write every new test)
      ↓
T009         (observe: T005 ✗ T006 ✗ T007 ✓ T008 ✓)   ← SC-004's evidence
      ↓
T010         (x_port=1)          ← the first edit to app/__init__.py
      ↓
T011         (observe: T005 ✓ T006 ✓ T008 ✗)          ← the guard's justification
      ↓
T012         (the guard)
      ↓
T013         (all green)
```

Nothing may edit `app/__init__.py` before T009, and T011 must not be folded into T013. Both
observations are deliverables, not diagnostics.

### User Story Dependencies

- **US1 (P1)**: independent. It is the whole fix
- **US2 (P2)**: **not independent of US1** — it is delivered by T010. The spec says so directly: the
  bookmarklet is the visible symptom of the same missing port. Its test, its docstring and its live
  check are separable; its implementation is not. Do not manufacture a second code change for it
- **US3 (P3)**: independent of both. The documentation could be written first

### Parallel Opportunities

Limited, and honestly so. This is a one-line fix with a guard — most of the work is a chain of
observations that must happen in order.

- T016 and T017 are different files with no shared dependency and can be written in parallel, at any
  time after T001
- T003 through T008 all edit `tests/unit/test_proxy_headers.py` and therefore **cannot** run in
  parallel with each other
- T010 and T012 both edit `app/__init__.py` and are sequential by design — T011 sits between them
- Nothing in Phase 6 is parallelizable; each step depends on the one before

---

## Parallel Example: Phase 5

```bash
# The only genuine parallelism in this feature — two documentation files, no shared state:
Task: "T016 Add X-Forwarded-Port to the nginx block in docs/deployment-guide.md"
Task: "T017 Add the missing-port symptom to docs/troubleshooting-guide.md"
```

---

## Implementation Strategy

### MVP (User Story 1 only)

1. Phase 1 — branch and baseline
2. Phase 2 — all tests written, T009's observation recorded
3. Phase 3 — `x_port=1`, T011's observation recorded, the guard, green
4. **STOP and VALIDATE**: `nox -s tests` green, T006 covering the refused POST

At that point the defect is fixed and covered. It is not yet *delivered* — that needs Phase 6, and
Phase 6 needs T021.

### Incremental Delivery

1. Phases 1–3 → the write path works and is covered (MVP)
2. Phase 4 → the bookmarklet is covered and the reason is written down where the code is
3. Phase 5 → the deployment guide stops producing broken deployments; suite and lint green
4. Phase 6 → the fix reaches the deployment and SC-001, SC-002, SC-003 and SC-007 are settled

### Not in this feature

Confirming a capture and measuring a stored file to show every gallery image is a full-resolution
original — 022 SC-010 / #80 §1b B4. T026 unblocks it; #113 performs it. See T029.

---

## Notes

- Commit after each logical group; T009 and T011 are worth their own commits so the observations are
  in the history rather than only in a task list
- `venv/` is used by path (`venv/bin/nox`), never via `source venv/bin/activate`
- Every nox invocation needs `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"` prefixed or environment
  creation fails
- No new pytest marker is introduced, so `--strict-markers` needs nothing registered in `pytest.ini`
- No migration, no schema change, no `Decimal` arithmetic — principles III, V and VI are untouched
