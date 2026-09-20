---

description: "Task list for 047-build-version-suffix"
---

# Tasks: Build Version Suffix

**Input**: Design documents from `/specs/047-build-version-suffix/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/version-surfaces.md](./contracts/version-surfaces.md)

**Tests**: REQUIRED, not optional. Constitution IV: "Changes that alter behavior MUST land
with tests covering that behavior." This change alters what the footer and `/health`
report, so it lands with tests.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 = container provenance (P1), US2 = working-copy provenance (P2)

## Path Conventions

Single Flask application at the repository root: `app/`, `tests/unit/`, `docs/`,
`.github/workflows/`. Paths below are repository-relative.

---

## Phase 1: Setup

**Purpose**: none required.

No dependency to install, no directory to create, no tooling to configure — the feature
adds no package and no new tree. The existing `venv/` and `nox` sessions are the whole
environment. This phase is intentionally empty; skip to Phase 2.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: split the one thing `app/version.py` reports today into the two things it
must distinguish — the declared release number and the version to report. Both user
stories build on this split, and neither can be observed until the resolution skeleton
exists.

**⚠️ CRITICAL**: T001–T003 block both US1 and US2.

- [ ] T001 Restructure `app/version.py` so the release number is read into a
      `RELEASE_VERSION: str` module constant by a helper rather than assigned inline, and
      `__version__: str` becomes the result of a `_compute_version()` call evaluated at
      module level. At this task `_compute_version()` may simply return `RELEASE_VERSION`
      — the behaviour is unchanged and the module still imports cleanly. Keep the existing
      module docstring's point (pyproject is the single source of truth) and extend it to
      say what the suffix means.
- [ ] T002 Update `tests/unit/test_basic.py`: change `test_version_is_semver` to assert
      against `RELEASE_VERSION` instead of `__version__`, importing it from
      `app.version`. `__version__` may now carry a suffix, so splitting it on `.` and
      requiring three digit parts is no longer a true statement about it. Leave
      `test_health_reports_version` and `test_templates_render_version` asserting against
      `__version__` — they are checking that the *reported* version reaches both
      surfaces, which is exactly what must stay true.
- [ ] T003 Add `tests/unit/test_version.py` with a test asserting `RELEASE_VERSION`
      equals the `[project].version` value parsed independently from `pyproject.toml`, so
      the single-source-of-truth claim (FR-010) has a test and not just a comment.

**Checkpoint**: `venv/bin/nox -s tests` is green, `__version__` still reports the bare
release number, and nothing user-visible has changed yet.

---

## Phase 3: User Story 1 - Identify which build a container is running (Priority: P1) 🎯 MVP

**Goal**: an image built by the `docker-build` job reports `0.1.1-6d15bde`; an image
built by the `release` job reports `0.1.1`.

**Independent test**: `docker build --build-arg BUILD_SHA="$(git rev-parse HEAD)" .` then
run `python -c "from app.version import __version__; print(__version__)"` in the
container — expect the seven-character suffix. Build again with no `--build-arg` — expect
the bare number. Both are spelled out in [quickstart.md](./quickstart.md) §3.

### Tests for User Story 1

- [ ] T004 [P] [US1] In `tests/unit/test_version.py`, cover the build-stamp branch by
      monkeypatching the environment: `APP_BUILD_SHA` set to a full forty-character SHA
      yields `RELEASE_VERSION + "-" + first seven characters`; set to exactly seven
      characters yields the same shape; set to empty string and to whitespace-only are
      both treated as absent and fall through to the git path.
- [ ] T005 [P] [US1] In `tests/unit/test_version.py`, assert the stamp takes precedence:
      with `APP_BUILD_SHA` set *and* `app.version._git` monkeypatched to return
      working-copy answers, the result is the stamped version and `_git` is never called.
      This is the spec edge case "a container started inside a working copy must report
      what it was built from".

### Implementation for User Story 1

- [ ] T006 [US1] In `app/version.py`, implement the build-stamp branch of
      `_compute_version()`: read `APP_BUILD_SHA` from `os.environ`, strip it, and if
      non-empty return `f"{RELEASE_VERSION}-{sha[:7]}"` without consulting anything else.
      Per [data-model.md](./data-model.md) resolution step 1.
- [ ] T007 [US1] In `Dockerfile`, add `ARG BUILD_SHA=""` and `ENV APP_BUILD_SHA=$BUILD_SHA`
      to the **runtime** stage (`ARG` is stage-scoped, and it is the runtime stage that
      must carry the `ENV`). Place them after the last `COPY` and before `HEALTHCHECK`, so
      a value that changes every commit does not invalidate the expensive layers above it.
      Add a short comment saying the CI build passes it and the release build does not.
- [ ] T008 [US1] In `.github/workflows/test.yml`, add
      `build-args: BUILD_SHA=${{ steps.image.outputs.sha }}` to the `docker-build` job's
      `docker/build-push-action` step. **Use `steps.image.outputs.sha`, not `github.sha`**
      — on a `pull_request` event `github.sha` is GitHub's synthetic merge commit, which
      is not in the repository, and the job already computes the right value for exactly
      this reason (see its existing comment).
- [ ] T009 [US1] In `.github/workflows/release.yml`, add a comment to the release job's
      build step recording that it deliberately passes no `BUILD_SHA`, and that this
      absence is what makes a release image report a bare version. Both files already
      carry "keep these two in sync" notices; an unexplained asymmetry between them would
      read as an oversight and get "fixed".

**Checkpoint**: US1 is complete and shippable on its own. The mandatory requirement of
the issue is satisfied. `nox -s tests` green.

---

## Phase 4: User Story 2 - Identify what a working copy is running (Priority: P2)

**Goal**: run from a checkout and the footer tells you the commit, and whether the code
has been edited since.

**Independent test**: `venv/bin/python -c "from app.version import __version__; print(__version__)"`
on a normal feature branch shows `0.1.1-<short sha>`; touch a tracked file and it gains
`-dirty`. [quickstart.md](./quickstart.md) §2.

**Scope decision**: in scope. Research R4 measured the cost — one ~30-line helper, no new
dependency, no configuration, no caller change — against the issue's condition ("only if
it is not a significant additional complication") and found the condition unmet.

### Tests for User Story 2

- [ ] T010 [P] [US2] In `tests/unit/test_version.py`, add a helper that monkeypatches
      `app.version._git` with a stub driven by a dict keyed on the git subcommand, so
      each case states only the three answers it cares about (`rev-parse`,
      `tag --points-at`, `status`). Research R5 — this stub is what lets all eight
      situations be covered without a fixture repository.
- [ ] T011 [P] [US2] Cover the four working-copy rows of the
      [data-model.md](./data-model.md) worked-case table: on the release tag + clean →
      bare; on the release tag + dirty → `-dirty`; untagged + clean → `-<sha>`; untagged +
      dirty → `-<sha>-dirty`.
- [ ] T012 [P] [US2] Cover tag matching precisely: `v0.1.1` matches, bare `0.1.1` matches,
      an unrelated tag such as `nightly` does not, and a near-miss such as
      `v0.1.1-rc1` does not. Cover a HEAD carrying several tags where one of them is the
      release tag.
- [ ] T013 [P] [US2] Cover every `git`-unavailable path collapsing to the bare release
      number with no exception escaping: `_git` returns `None` for `rev-parse` (not a
      repository / `git` not installed / non-zero exit / timeout). Assert the bare number
      is returned even when the dirty check would have said dirty — if the commit is not
      knowable, neither is anything else (data-model step 2a).
- [ ] T014 [P] [US2] Cover `_git` itself against real failure modes rather than a stub:
      a non-existent subcommand returns `None`, and a `FileNotFoundError` (simulating no
      `git` binary) and a `subprocess.TimeoutExpired` both return `None` rather than
      propagating. This is the test for FR-008, and it is the one test that must not use
      the T010 stub, since the stub replaces the code under test.

### Implementation for User Story 2

- [ ] T015 [US2] In `app/version.py`, add `_git(*args: str) -> str | None`: run
      `["git", *args]` with `subprocess.run`, `cwd` set to the repository root (the same
      directory `pyproject.toml` is read from), `capture_output=True`, `text=True`,
      `timeout=5`. Return stripped stdout on returncode 0; return `None` on a non-zero
      exit, `OSError`/`FileNotFoundError`, or `subprocess.TimeoutExpired`. It must never
      raise. Comment why the timeout is there: a hung `git` would otherwise take
      application startup with it.
- [ ] T016 [US2] In `app/version.py`, add `_version_suffix(release_version: str) -> str`
      implementing resolution step 2 from [data-model.md](./data-model.md): `rev-parse
      --short=7 HEAD` for the commit (`None` → return `""`), `tag --points-at HEAD` split
      on newlines for the tags, and `status --porcelain --untracked-files=no` for
      dirtiness. Return `""`, `"-dirty"`, `"-<sha>"`, or `"-<sha>-dirty"`.
      **`--untracked-files=no` is load-bearing** — without it the untracked files a
      working copy always has (`test-debug-output/`, `.pytest_cache/`) make every
      developer run report dirty, and the marker stops meaning anything. Say so in a
      comment at the call site.
- [ ] T017 [US2] Wire `_version_suffix()` into `_compute_version()` as the fallback after
      the build-stamp branch returns nothing, completing the resolution order.

**Checkpoint**: both stories complete. Every row of the worked-case table is covered by a
test.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T018 [P] Update the "Versioning and Releases" section of `docs/deployment-guide.md`:
      say what the three forms mean (`0.1.1` is a release, `0.1.1-6d15bde` is a CI build
      of that commit, a trailing `-dirty` means a working copy with edits), and that the
      version in the footer and the one from `/health` are the same string. The section
      currently states pyproject is the single source of truth for *the* version — keep
      that true by describing the suffix as added to it, not as replacing it.
- [ ] T019 [P] Update the sample `/health` response near line 819 of
      `docs/deployment-guide.md`, which currently shows `"version":"0.1.0"` — stale
      against the current `0.1.1` and now also unrepresentative of a CI build. Show a
      suffixed example.
- [ ] T020 Run `venv/bin/nox -s tests` and confirm green.
- [ ] T021 Run `venv/bin/nox -s e2e` detached with a 20+ minute budget and confirm green.
      It gains no new test, but Constitution IV requires it to pass before merge, and the
      footer appears on every page every E2E test loads. Per `CLAUDE.md`, run it with
      `nohup`/background and poll — it does not fit inside a 10-minute tool timeout.
- [ ] T022 Confirm `git status` is clean after the test runs (Constitution IV: a test
      session must leave the working tree clean), and confirm no file under
      `app/templates/`, `app/static/css/` or `app/static/js/` was touched, so the
      screenshot-regeneration gate is genuinely not triggered rather than merely assumed.
- [ ] T023 Build both container variants per [quickstart.md](./quickstart.md) §3 and
      confirm the stamped image reports the suffix and the unstamped one reports the bare
      number. This is the only check that exercises the real Dockerfile and the real
      "no git in the image" fallback; the unit tests cannot reach either.

---

## Dependencies

```text
Phase 2 (T001-T003)  ── blocks everything
      │
      ├── Phase 3 / US1 (T004-T009)  ── shippable alone; the issue's mandatory scope
      │
      └── Phase 4 / US2 (T010-T017)  ── needs T001-T003 only, NOT US1
                  │
                  └── T017 touches _compute_version(), which T006 also touches.
                      If US1 and US2 are worked separately, do T006 first.
      │
      └── Phase 5 (T018-T023) ── after both
```

**Story independence**: US1 and US2 share only the Phase 2 skeleton. US1 is the container
path and reads an environment variable; US2 is the working-copy path and shells out to
`git`. They meet at one `if` in `_compute_version()`. Either can ship without the other,
and US1 alone satisfies the issue's stated mandatory requirement.

## Parallel Execution

Within US1: T004 and T005 are both in `tests/unit/test_version.py` and touch different
test functions — parallel in principle, though the file is small enough that writing them
together is simpler. T007 (`Dockerfile`), T008 (`test.yml`) and T009 (`release.yml`) are
three different files with no ordering between them; genuinely parallel.

Within US2: T011–T014 are independent test cases and all depend on T010's stub.

Phase 5: T018 and T019 are the same file and must be sequential despite both being
documentation. T020, T021 and T023 are three different runners and can overlap, though
T021 is the long pole and should be started first.

## Implementation Strategy

**MVP = Phase 2 + Phase 3.** That is the issue's only mandatory requirement, and it is
four small tasks of implementation behind three of scaffolding.

**Then Phase 4**, which research found cheap enough to include. If it turns out during
implementation to be more than research R4 estimated — if it needs a dependency, a
configuration knob, or a change to a caller — stop and ship the MVP, and record why in
the pull request. The issue set that condition explicitly and the plan agreed to honour it.

**Then Phase 5**, where T023 matters more than its position suggests: everything before it
is tested against a monkeypatched view of the world, and T023 is the only step that finds
out whether the real image behaves the way the design says it does.
