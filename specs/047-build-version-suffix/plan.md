# Implementation Plan: Build Version Suffix

**Branch**: `robot-army/issue-164-build-version-exposed-in-ui` | **Date**: 2026-09-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/047-build-version-suffix/spec.md`

## Summary

Two images built a month apart from different commits both say `0.1.1`, so the footer
answers "which release is this descended from?" when the question being asked is "which
build am I looking at?". This makes the version carry its provenance.

The whole feature is one file plus two workflow lines plus two Dockerfile lines. Its
shape follows from one fact established in research: **the runtime image has no `git`
binary and no `.git` directory**, so the container's answer has to be baked in at build
time and the working copy's answer has to be derived at run time, and those are the only
two mechanisms needed.

- **Container**: a `BUILD_SHA` build argument, persisted as `ENV APP_BUILD_SHA`. The
  `docker-build` job in `test.yml` passes it; the `release` job does not. That asymmetry
  *is* the release/non-release distinction — no second flag, no build-kind branch in the
  application (research R2).
- **Working copy**: three `git` invocations through `subprocess.run`, each returning
  `None` on any failure, folded into a suffix. Roughly thirty lines and no new
  dependency, which is why the issue's conditional second story is in scope rather than
  deferred (research R4).
- **One string, two surfaces**: `app/version.py:__version__` keeps its name and keeps
  being the thing the footer and `/health` read. Neither `app/__init__.py` nor
  `app/main/routes.py` nor `base.html` is touched, so FR-001 ("the two can never
  disagree") holds by construction rather than by discipline.

The existing `__version__` name now carries a suffix, so the one test that parsed it as
bare SemVer needs the bare number. `RELEASE_VERSION` is added for that — a name for the
number `pyproject.toml` declares, with exactly one caller.

Two details are load-bearing and easy to get wrong:

1. The CI job must stamp `steps.image.outputs.sha`, **not** `github.sha`. On a
   `pull_request` event `github.sha` is GitHub's synthetic merge commit, which is not in
   the repository — a suffix naming it would fail SC-002 ("locate the commit in one
   lookup"). `test.yml` already computes the right value and says why in a comment.
2. `git status --porcelain` must be given `--untracked-files=no`. Development in this
   repository leaves untracked files constantly (`test-debug-output/`, `.pytest_cache/`),
   and without the flag every developer run reports `-dirty`, turning the marker into
   noise.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: none added. `subprocess`, `os`, `tomllib`, `pathlib` — all
standard library. The `versionfinder` package named in the issue was evaluated and
rejected (research R3).

**Storage**: none. Nothing is persisted; no Alembic revision.

**Testing**: `nox -s tests` (unit, network-blocked, sub-second). No new E2E test — the
change alters a string's contents, not any page behaviour; `nox -s e2e` must still pass.

**Target Platform**: single-user Flask app on a home LAN, run either from a container
image built by GitHub Actions or directly from a working copy.

**Project Type**: server-rendered web application.

**Performance Goals**: none new. Version resolution is module-level, so it happens once
per worker process, not once per request (FR-009, SC-006). The container path is a single
`os.environ.get`; the working-copy path is three subprocess calls at start, each bounded
by `timeout=5`.

**Constraints**: version resolution must never raise into a page render or `/health`
(FR-008). Every failure mode — no repository, no `git`, `git` errors, `git` hangs —
degrades to the bare release number.

**Scale/Scope**: one application module rewritten (~70 lines), one new test module, two
lines in `Dockerfile`, one line in `.github/workflows/test.yml`, a comment in
`.github/workflows/release.yml`, one documentation section.

## Constitution Check

*Constitution v1.3.0. Checked before Phase 0 and re-checked after Phase 1 design; both
passes below, with the post-design pass in the right-hand column.*

| Principle | Assessment | Post-design |
|---|---|---|
| **I. Simplicity First (NON-NEGOTIABLE)** | No new dependency: `subprocess` over `versionfinder`, which is unmaintained, pre-3.13 and answers a far larger question (R3). No new configuration knob: the release/non-release distinction is the *absence* of a build argument, not a second flag (R2). No abstraction: one module, private helpers, no injection seam beyond what the tests actually monkeypatch. No caching machinery: module-level evaluation is the cache. | **PASS.** The design got smaller during Phase 0, not larger — FR-005 was rewritten to drop a positive release marker that had no consumer. |
| **II. Layered Architecture Boundaries** | Not engaged. `app/version.py` is neither a model, a storage path, nor a service; it is a constant the app factory injects. No route, no SQL, no ORM. | **PASS.** No layer is crossed or collapsed. |
| **III. Exact Numerics** | Not engaged. No measured quantity anywhere near this feature. | **PASS.** |
| **IV. Test Discipline Through Nox** | Behaviour change lands with tests (`tests/unit/test_version.py`), run via `nox -s tests`. No new pytest marker. Unit tests build on `tests/conftest.py` fixtures where they touch the app. Network stays blocked — `git` is a local subprocess, not a network call. Monkeypatching one `_git` helper covers all eight situations SC-005 names, including the two (`git` absent, `git` hanging) that a fixture repository cannot represent (R5). | **PASS.** No E2E test added and none needed; `nox -s e2e` must still be green before merge. |
| **V. MariaDB Is the Source of Truth** | Not engaged. No schema change, no migration, nothing written. | **PASS.** |
| **VI. Item Lifecycle and History Invariants** | Not engaged. No add/move/shorten/edit/search path is touched. | **PASS.** |
| **Operating Context and Threat Model** | Nothing added to the attack surface and nothing hardened against an imagined one. A commit SHA in the footer of a LAN-only application is a diagnostic, not a disclosure; the repository is public and its history is already public. No secret is read, written, or committed. | **PASS.** |
| **Technology Constraints** | Type hints on every function (`-> str`, `-> str \| None`). No new error-handling machinery — the failure path returns a value rather than raising, so the centralized handlers are not involved. Module placement unchanged. | **PASS.** |
| **Development Workflow and Quality Gates** | Feature branch plus pull request. `test.yml` green before merge. **Screenshot gate not triggered**: `app/templates/**`, `app/static/css/**` and `app/static/js/**` are all untouched — the footer template is unchanged, only the value flowing into it. | **PASS.** Confirmed against the final file list below; no file under those three trees appears. |

**Gate result: PASS, no violations.** The Complexity Tracking table is therefore omitted,
per its own instruction.

One deliberate deviation from the spec-as-first-written is recorded rather than hidden:
FR-005 originally asked the release workflow to positively stamp "this is a release".
Phase 0 found that flag's only consumer would produce output identical to the
no-flag path, making it a knob Principle I forbids. FR-005 was revised in `spec.md` and
the reasoning is in research R2.

## Project Structure

### Documentation (this feature)

```text
specs/047-build-version-suffix/
├── plan.md                        # This file
├── spec.md                        # /speckit-specify output (FR-005 revised in planning)
├── research.md                    # Phase 0: R1-R5
├── data-model.md                  # Phase 1: values, grammar, resolution order, worked cases
├── quickstart.md                  # Phase 1: how to prove it, cheapest first
├── contracts/
│   └── version-surfaces.md        # Phase 1: module surface, /health, build argument
├── checklists/
│   └── requirements.md            # spec quality checklist
└── tasks.md                       # /speckit-tasks output -- NOT created here
```

### Source Code (repository root)

```text
app/
└── version.py                     # REWRITTEN. RELEASE_VERSION + suffix resolution.
                                   # __version__ keeps its name and its role.

app/__init__.py                    # UNCHANGED (imports __version__, injects app_version)
app/main/routes.py                 # UNCHANGED (/health reads __version__)
app/templates/base.html            # UNCHANGED (renders v{{ app_version }})

Dockerfile                         # ARG BUILD_SHA / ENV APP_BUILD_SHA, runtime stage,
                                   # below every COPY so the cache is not spoiled

.github/workflows/test.yml         # docker-build job: build-args: BUILD_SHA=<head sha>
.github/workflows/release.yml      # comment only -- passing no build arg is the point,
                                   # and a bare absence needs a note saying it is intended

tests/unit/
├── test_version.py                # NEW. Every row of the resolution table.
└── test_basic.py                  # AMENDED. SemVer assertion moves to RELEASE_VERSION;
                                   # footer and /health asserted to agree.

docs/deployment-guide.md           # "Versioning and Releases" gains what the suffix means
```

**Structure Decision**: no new directories and no new package. The feature is a rewrite
of one existing module plus build-time plumbing. `app/version.py` already exists for
exactly this purpose and already owns reading `pyproject.toml`; giving it one more thing
to determine is the smallest change that can satisfy FR-001, because a single module
attribute cannot disagree with itself.

## Phase Outputs

- **Phase 0** — [research.md](./research.md). Five questions: how a built image learns its
  commit (R1), how a release image reports bare (R2), where the working-copy answer comes
  from (R3), whether Story 2 is too complicated to include (R4 — it is not), and what
  module shape keeps it testable without fixture repositories (R5).
- **Phase 1** — [data-model.md](./data-model.md) (values, grammar, resolution order, an
  eleven-row worked-case table), [contracts/version-surfaces.md](./contracts/version-surfaces.md)
  (module surface, `/health` response, Docker build argument, and what is deliberately
  *not* a contract), [quickstart.md](./quickstart.md) (validation in four rising tiers).

No NEEDS CLARIFICATION markers remain.
