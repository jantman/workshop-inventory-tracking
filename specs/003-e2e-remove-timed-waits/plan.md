# Implementation Plan: Finish Removing Time-Based Waits from the E2E Suite

**Branch**: `issues/65` | **Date**: 2026-08-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-e2e-remove-timed-waits/spec.md`

## Summary

127 fixed-duration waits remain in `tests/e2e/`, costing a measured 121.6s against SC-001's 60s
target. The work is to convert each one to an assertion on observable state, then move the authoring
guidance out of feature 002's spec directory into the constitution and `CLAUDE.md`.

Phase 0 changed the shape of the job in three ways.

**The time is not where the site count says it is.** The move file holds 42 of the 99 in-gate sites
but only ~10.2s of the 121.6s, because every one of its sites is inline and runs once. Population A
— the seventeen "ordinary" files — holds ~87.5s. Converting Population A alone meets **both** SC-001
and SC-002. The previously-reverted files are therefore compliance work, not performance work, and
the feature's headline numbers no longer depend on the risky part succeeding.

**No application change is required.** FR-007 anticipated needing an additive readiness affordance
for the move page. Every signal needed already exists in the DOM. What defeated the previous attempt
was not a missing signal but using one signal where the page has two independent completions.

**One defect was found and is not being fixed silently.** `handleDoneCode()` tests
`moveQueue.length` before the finalise it just started has landed, producing a spurious "No items in
move queue" warning and leaving the scanner badge short of `Done - Ready to Validate`. It
self-corrects, so the flow works and today's tests pass. It is raised for decision rather than
folded into a test-cleanup commit, because fixing it changes user-visible behavior.

Full evidence: [research.md](./research.md). Signals: [contracts/readiness-signals.md](./contracts/readiness-signals.md).

## Technical Context

**Language/Version**: Python 3.13 (nox-pinned; system Python is 3.14)

**Primary Dependencies**: pytest, pytest-playwright, Playwright (Chromium), testcontainers (MariaDB)

**Storage**: MariaDB via testcontainer — unchanged by this feature; no schema or migration work

**Testing**: `nox -s e2e` (`-m "e2e and not screenshot"`), `nox -s tests`, `nox -s screenshots_headless`, `nox -s screenshots_verify`

**Target Platform**: Linux, home LAN, single user

**Project Type**: Flask web application with server-rendered templates and vanilla-JS page modules

**Performance Goals**: measured fixed-wait time under 60s (from 121.6s); e2e gate at or under 8m 45s (from ~585s)

**Constraints**: strictly serial suite; zero retries consumed; every test passes in isolation; no assertion weakened; working tree clean after a run

**Scale/Scope**: 127 wait sites across 22 test files; 362 gate tests; 5 documentation locations to repoint

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | **PASS.** Removes code and consolidates four documentation locations into one normative source. No new dependency, abstraction or configuration. The probe (C0) is a temporary, uncommitted measurement tool, deleted after each use. |
| **II. Layered Architecture Boundaries** | **PASS.** No application layer is touched. The one candidate change (D3) is confined to a single JS event handler and is gated on maintainer approval. |
| **III. Exact Numerics** | **N/A.** No measurement or `Decimal` value is involved. |
| **IV. Test Discipline Through Nox** | **PASS — this feature is the principle.** All runs via nox. No new marker. §IV's own grandfathering clause is retired by C6, and §IV's pointer into feature 002 is replaced by C7. |
| **V. MariaDB Is the Source of Truth** | **N/A.** No schema change, no migration. |
| **VI. Item Lifecycle and History Invariants** | **PASS, with a guard.** `test_shorten_items.py`, `test_toggle_item_status.py` and `test_history_functionality.py` protect these invariants. FR-010 confines changes there to the waiting mechanism; SC-005's assertion diff is the check. |

**Post-Phase-1 re-evaluation**: unchanged. The design added no dependency, no abstraction and no
application code. D3 remains the only proposed behavior change and remains gated.

**Gate result: PASS.** No entry in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/003-e2e-remove-timed-waits/
├── plan.md                       # This file
├── spec.md                       # Feature specification
├── research.md                   # Phase 0: where the time is, and what is observable
├── data-model.md                 # Phase 1: wait sites, signals, documentation locations
├── quickstart.md                 # Phase 1: how to verify each success criterion
├── contracts/
│   └── readiness-signals.md      # Phase 1: the signals a test may depend on
├── checklists/
│   └── requirements.md           # Spec quality checklist
└── tasks.md                      # Phase 2 — created by /speckit-tasks, not here
```

### Source Code (repository root)

```text
tests/e2e/
├── test_move_items_sub_location.py     # C2 — 42 sites, the state-machine file
├── test_copy_item_photos.py            # C3 — 8 sites, helper-resident, Rule 3 pass
├── test_photo_upload.py                # C4 — 3 sites
├── test_photo_upload_bug.py            # C4 — 4 sites
├── test_screenshot_generation.py       # C5 — 28 sites, outside the gate
├── test_shorten_items.py               # C1 — §VI guarded
├── test_toggle_item_status.py          # C1 — §VI guarded
├── test_history_functionality.py       # C1 — §VI guarded
├── ... 14 further C1 files             # C1 — see research.md §A
├── waits.py                            # C7 — docstring repointed
└── pages/                              # shared page objects; no wait sites

app/static/js/
├── inventory-move.js                   # read-only, except D3 if approved
└── photo-manager.js                    # read-only

CLAUDE.md                               # C7 — becomes the normative source
.specify/memory/constitution.md         # C6, C7 — rule and exception only
docs/development-testing-guide.md       # C7 — repointed
_bmad-output/project-context.md         # C7 — repointed
specs/002-e2e-test-performance/         # C6 — record corrected; C7 — contract superseded
```

**Structure Decision**: no structural change. This is a test-suite and documentation feature; the
only files created are under the feature's own spec directory.

## Change Sets

Ordered by the Phase 0 finding that Population A carries the time and the least risk.

| # | Change | Sites | Est. saving | Risk |
|---|---|---:|---:|---|
| **C0** | Rebuild the blocking-call probe; re-confirm the 121.6s baseline | — | — | none — uncommitted tool |
| **C1** | Population A: 42 sites across 17 files | 42 | **~87.5s** | low, per-site judgement |
| **C2** | `test_move_items_sub_location.py` against the state-machine map | 42 | ~10.2s | **high** — reverted once |
| **C3** | `test_copy_item_photos.py`: waits + Rule 3 snapshot reads | 8 | ~13.9s | medium |
| **C4** | `test_photo_upload.py`, `test_photo_upload_bug.py` | 7 | ~10.0s | medium |
| **C5** | `test_screenshot_generation.py` | 28 | out of gate | low; verify images |
| **C6** | Retire grandfathering; correct 002's record of SC-008 | — | — | none |
| **C7** | Relocate guidance; repoint all five references | — | — | none |
| **D3** | *Optional, needs approval*: fix `handleDoneCode()`'s ordering | — | — | user-visible |

**C0 is genuinely first.** The instrument SC-001 is measured with is not in the tree — feature 002
kept `_probe.py` in a session scratchpad and only a stale `.pyc` survives. Until it is rebuilt the
headline number cannot be measured at all, and the 121.6s baseline cannot be re-confirmed against
the current tree.

**Measure after C1 and stop to look.** If the projection holds, SC-001 and SC-002 are both met at
that point and everything after is compliance work at whatever pace correctness needs.

### C2 — how the move file is approached

The mapping is in [contracts/readiness-signals.md](./contracts/readiness-signals.md) §1. Each of the
42 sites resolves to one of five transitions; the fourth — a JA ID scanned while in
`ja_id_or_sub_location` — is the one that needs **two** conditions awaited, and is why single-condition
attempts kept surfacing "a further race".

Order within C2: convert one test, run it ten times, and only then convert the rest. A single green
run is not evidence here.

### C7 — the relocation

Five live references treat `specs/002-e2e-test-performance/contracts/e2e-test-authoring.md` as
normative: `CLAUDE.md:24`, `docs/development-testing-guide.md:359`,
`.specify/memory/constitution.md:134`, `_bmad-output/project-context.md:65`, and
**`tests/e2e/waits.py:6`** — a source file a Markdown-only sweep would miss.

Split by altitude per FR-022: the constitution keeps the rule, its exception, and the
justify-in-writing requirement; `CLAUDE.md` takes the condition table, the worked cases, the review
checklist, and the patterns from `contracts/readiness-signals.md` §4. The other three point at
`CLAUDE.md`.

Two historical citations stay (FR-025): `docs/development-testing-guide.md:74` and
`.specify/memory/constitution.md:14`, both attributing the 22m 27s baseline to feature 002.

C7 runs after C1–C5 are proven stable (FR-020) — its content is what those conversions taught.

## Risks

| Risk | Mitigation |
|---|---|
| C2 races again and is reverted a second time | The map is written first (FR-005) and every wait cites it (FR-006). Ten-run bar per file. C2 no longer gates SC-001/SC-002, so a revert costs compliance, not the feature. |
| A conversion is fast but shallow — waits for something already true | The signal must be `post-await` where the work is async; `contracts/readiness-signals.md` marks which are which. |
| Rule 3 snapshot reads left behind a removed cushion | C3 converts reads and waits together. Pattern E names this as the general case. |
| Retries mask new flakiness | Every acceptance run uses `--reruns=0`. |
| §VI assertions altered while changing how they wait | SC-005's assertion diff, reviewed specifically for the three guarded files. |
| Screenshots capture a fade mid-transition | `nox -s screenshots_verify`. |
| D3 declined, leaving a wait that wants `Done - Ready to Validate` | Default path waits on `#queue-count`, which works either way. D3 is an improvement, not a dependency. |

## Open Decision for the Maintainer

**D3 — fix `handleDoneCode()`'s ordering?** It calls `finalizeCurrentMove(null)` without awaiting it,
then immediately tests `moveQueue.length === 0`. On a first move that test is wrongly true: the user
gets a spurious "No items in move queue. Add some items before finishing." warning, and the scanner
badge never reaches `Done - Ready to Validate`. `updateUI()` re-enables Validate a moment later, so
nothing is broken for long.

Recommend fixing it — `await` the finalise, then test the queue — as a separate commit from the test
conversion. It is a real if minor bug, and it makes the obvious readiness signal usable. But it
changes user-visible behavior, which FR-007 does not cover, so it is not being folded in silently.

The conversion does not depend on the answer.

## Complexity Tracking

No constitutional violations. Table intentionally empty.
