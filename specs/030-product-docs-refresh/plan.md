# Implementation Plan: Product Documentation Refresh

**Branch**: `030-product-docs-refresh` | **Date**: 2026-08-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/030-product-docs-refresh/spec.md`

## Summary

Three documentation problems, fixed in three commits against verified ground truth rather than against the documents that currently exist.

The **configuration reference** in the deployment guide is checked in both directions against what the application actually reads. Phase 0 established that set: seventeen variables that change a deployed or locally-run application, plus five that belong to the test suite. Nine names currently in the guide are read by nothing. The DigiKey four are absent entirely, which is what makes a guide-following deployment silently lack DigiKey capture.

The **vendor capability matrix** is established from the code — three registered order vendors, two page readers, one API-backed part lookup and backfill, one host-name table — and written once in the user manual, summarized in the README, and used to correct the troubleshooting guide.

The **removals** are `docs/product-functionality-gap.md`, `docs/spec-product-catalog.md`, and all of `docs/features/` (28 files). Phase 0's link audit confirms nothing outside `specs/` and the removal set itself references any of them, so the removal is a `git rm` and nothing else.

No application code changes. The whole feature is Markdown.

## Technical Context

**Language/Version**: Markdown (GitHub-flavored). Python 3.13 is read during verification, never written.

**Primary Dependencies**: None added. Verification uses `grep`, `git`, and the existing `nox` sessions.

**Storage**: N/A

**Testing**: `nox -s tests` and `nox -s e2e` must still pass, unchanged and unmodified — they are a regression check that this feature touched no behavior, not a test of it. No new test, marker, or nox session is added; a documentation link check is a one-time `grep`, not standing machinery (Principle I).

**Target Platform**: The repository's documentation set — `README.md` and `docs/**`.

**Project Type**: Documentation-only change to an existing Flask web application.

**Performance Goals**: N/A

**Constraints**:
- `specs/**` is frozen and MUST NOT be edited outside this feature's own directory, including where it links to a removed file (spec FR-006).
- American spelling — `catalog`, never `catalogue` — in everything written (`CLAUDE.md`).
- No screenshot regeneration: `nox -s screenshots` churns unrelated images, and no template, CSS or JS changes here, so the constitution's screenshot gate is not triggered.
- Verified in Phase 0: `tests/e2e/screenshot_config.yaml` names only surviving documents in its `used_in` entries, so removals leave it accurate.

**Scale/Scope**: 30 files deleted -- 28 under `docs/features/` plus the two standalone documents. Four files edited (`README.md`, `docs/deployment-guide.md`, `docs/user-manual.md`, `docs/development-testing-guide.md`) plus `.env.example`. `docs/troubleshooting-guide.md` was expected to need an edit and did not: it makes no vendor claim, so FR-017 is discharged by verification (tasks.md T021). Roughly 5,700 lines of documentation reviewed, of which about 900 change.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Assessment |
|-----------|----------|------------|
| **I. Simplicity First** | Yes | PASS. No new machinery: the two-directional configuration check and the link check are `grep` commands recorded in `quickstart.md`, not a CI job, a nox session, or a linter. A standing gate for a one-time cleanup is exactly the speculative knob this principle forbids. The removals reduce surface rather than adding it. |
| **II. Layered Architecture Boundaries** | No | No code changes. |
| **III. Exact Numerics** | No | No code changes. |
| **IV. Test Discipline Through Nox** | Yes | PASS. Nothing behavioral changes, so no test is added — "write the test that would have caught the bug, and stop" cuts the other way here: there is no bug in the application. `nox -s tests` and `nox -s e2e` are run once as a regression check. No new marker, no new session, no test edits. |
| **V. MariaDB Is the Source of Truth** | No | No schema or migration changes. |
| **VI. Item Lifecycle and History Invariants** | No | No changes to add/move/shorten/edit/search. |
| **Operating Context and Threat Model** | Yes | PASS. The deployment guide gains credential *setup* instructions (where to obtain DigiKey keys, which subscriptions to enable) and no credential values. `.env` stays untracked; `.env.example` continues to carry placeholders only. Documenting how to configure a secret is not committing one. |
| **Technology Constraints** | No | Nothing installed, imported, or upgraded. |
| **Development Workflow — branching** | Yes | PASS, deliberately stricter than required. The constitution permits documentation-only changes to go directly to `main`; issue #124 asks for a branch and a PR, so spec FR-027 takes the stricter path. A stricter choice needs no justification entry. |
| **Development Workflow — screenshots** | Yes | PASS. The gate binds changes to `app/templates/**`, `app/static/css/**` and `app/static/js/**`. None are touched, so no regeneration is required and none is done. |
| **Development Workflow — style** | No | `nox -s lint` covers Python, and no Python changes. |

**Result: PASS, no violations.** Complexity Tracking is therefore empty.

**Re-check after Phase 1 design: PASS.** Phase 1 produced two content contracts and a data model that are records of verified facts, not new abstractions — nothing in them survives into the application or into CI. `quickstart.md`'s checks are commands a reviewer runs by hand.

## Project Structure

### Documentation (this feature)

```text
specs/030-product-docs-refresh/
├── plan.md                              # This file
├── spec.md                              # Feature specification
├── research.md                          # Phase 0: the verified ground truth
├── data-model.md                        # Phase 1: the three entities and their rules
├── quickstart.md                        # Phase 1: how to verify the result
├── checklists/
│   └── requirements.md                  # Spec quality checklist (passing)
├── contracts/
│   ├── configuration-reference.md       # What the deployment guide MUST say, exactly
│   └── vendor-capability-matrix.md      # What the manual and README MUST say, exactly
└── tasks.md                             # Phase 2 (/speckit-tasks — not created here)
```

### Documentation set (repository root) — before and after

```text
README.md                                # EDIT — vendor names in the catalog bullet (FR-015)
.env.example                             # EDIT — align with the guide (FR-024)
docs/
├── category-taxonomy.md                 # keep, unchanged
├── deployment-guide.md                  # EDIT — the configuration reference (FR-018..FR-026)
├── development-testing-guide.md         # EDIT — stale env block, test-database settings
├── materials-taxonomy-design.md         # keep, unchanged (still-implemented design)
├── troubleshooting-guide.md             # keep, unchanged — no vendor claim (FR-017 verified)
├── user-manual.md                       # EDIT — the vendor summary (FR-009..FR-014)
├── images/                              # untouched; no screenshot regeneration
├── product-functionality-gap.md         # DELETE (FR-001)
├── spec-product-catalog.md              # DELETE (FR-003)
└── features/                            # DELETE, all 28 files (FR-004)
    ├── README.md
    ├── TEMPLATE.md
    └── complete/                        # 26 completed feature documents
```

**Structure Decision**: No source tree is involved. The documentation set above is the whole surface; `app/`, `tests/` and `migrations/` are not touched, which is checkable as spec SC-008.

## Implementation Approach

Three commits, in this order, on branch `030-product-docs-refresh` — spec priority order, which `tasks.md` follows phase for phase:

1. **Configuration** (FR-018..FR-026, User Story 1, P1). Rewrite the deployment guide's configuration section against `contracts/configuration-reference.md`, reconcile the Docker and from-source examples, move the `TEST_DB_*` family to the development guide, and align `.env.example`.
2. **Vendors** (FR-009..FR-017, User Story 2, P2). Add the summary to the user manual against `contracts/vendor-capability-matrix.md`, update the README bullet, and verify the troubleshooting guide.
3. **Removals** (FR-001, FR-003, FR-004, FR-007, FR-008, User Story 3, P3). Carry the one surviving piece of reasoning into the manual, then `git rm` the three targets. Nothing else in the commit, so it reverts cleanly on its own.

Then `nox -s tests` and `nox -s e2e` (detached, ≥15-minute budget), push, and open the PR (FR-027).

**Ordering rationale**: configuration first because it is the only story whose absence produces a broken deployment, and because the vendor summary links into the DigiKey configuration section it creates (FR-014) — a link is better written to a section that already exists. Removals last is a review convenience rather than a dependency: they touch no file the other two edit, they are the cheapest step to revert, and holding them back keeps two prose rewrites out of a diff full of deletions. The one ordering that *is* required is FR-007 before the deletion it protects — the label reasoning lands in the manual in the same commit that removes the document carrying it.

## Deviations from the Spec

One addition, stated rather than made silently:

**`docs/development-testing-guide.md:423-424`** tells a developer to `export FLASK_APP=app.py` and `export FLASK_ENV=development`. Both are wrong in the same way the deployment guide's block is: `.flaskenv` already sets `FLASK_APP=wsgi.py` (so the guide's value contradicts the repository's own), and `FLASK_ENV` has had no effect since Flask 2.3 — this project runs Flask 3.1.3. The spec's configuration requirements (FR-018..FR-026) name only the deployment guide, so fixing this is outside a literal reading. It is two lines, it is the same falsehood, and leaving it means shipping a feature whose stated purpose is "the configuration documentation is true" while a surviving document says otherwise. It is fixed, and called out here so the scope change is visible in review.

Nothing else is added. In particular, the several *behavioral* oddities Phase 0 turned up — `Config.validate_config()` is defined on `TestConfig` yet reads `Config`, and `DISABLE_LABEL_PRINTING` is honored but reachable from no environment variable — are recorded in `research.md` §5 and **not fixed**. This feature does not touch `app/`, and a code fix smuggled into a documentation PR is worse than the oddity.

## Complexity Tracking

No constitution violations. Table intentionally empty.
