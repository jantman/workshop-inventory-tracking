# Feature Specification: E2E Test Suite Performance

**Feature Branch**: `issues/47`

**Created**: 2026-08-05

**Status**: Draft

**Input**: GitHub issue #47 — "The current e2e test suite takes approximately 18 minutes to run. Perform a full assessment of the efficiency of this test suite (setup/teardown, dependencies, fixtures, and the tests themselves) and develop a plan to increase its performance without substantially sacrificing either test coverage or separation of tests (that would prevent localization of test failures). Include an estimate of the performance improvement. Pause for human review and approval of the plan. When approved, implement all changes and be sure to update all documentation (especially `CLAUDE.md` and documentation in `docs/` and `_bmad-output/`) to ensure that all future e2e test additions adhere to your performance improvements."

## Current Baseline *(originally estimated 2026-08-05; corrected by measurement the same day)*

Recorded so that "faster" is verifiable rather than felt. All figures describe the browser-driven end-to-end suite as it exists today.

> **Corrected against measurement.** The first version of this table was built by reading the code. The Phase 0 assessment ([research.md](./research.md)) then measured the suite and contradicted it in two places. The measured column is authoritative; the estimates are kept so the correction is visible.

| Property | First estimate | **Measured** |
|---|---|---|
| Wall-clock runtime of the full end-to-end suite | ~18 minutes | **1347.6s (22m 27s)**, retries disabled |
| End-to-end tests | 371 functions, 57 files | **377 collected** (376 passing, 1 skipped), 57 files |
| Execution mode | Fully serial; one test at a time | unchanged |
| Shared infrastructure | One application server and one database instance, started once per run | **45.9s one-time** (database container, server, browser launch) |
| Where the time goes | not estimated | **test bodies 1245.7s (92.5%)**, setup 90.8s (6.7%), teardown 6.4s (0.5%) |
| Per-test reset cost | Every table emptied and 21 reference rows re-inserted before each test — assumed a headline cost | **44.9s total, 0.120s per test — only 3.3% of the run.** Not worth optimizing; see C4 in [plan.md](./plan.md) |
| Fixed-duration waits | ~220 call sites totalling ~192s of literal arguments | **423.9s across 479 executions.** Call sites inside helpers run repeatedly, so counting sites understates by 2.2× |
| Navigation readiness waits | not estimated | **~302s** of `networkidle` waiting, ≥0.5s every navigation |
| Failure handling | Each failing test retried up to 3 more times with a 2-second delay, so one flaky test can cost up to 4× its own duration | unchanged; all measurements above were taken with retries disabled |
| Per-action timeouts | 60 seconds for page actions and navigation | unchanged |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fast full-suite feedback (Priority: P1)

The maintainer finishes a change and runs the complete end-to-end suite before opening a pull request. Today that means an ~18-minute block during which the change cannot be confirmed and the working session is interrupted. After this feature, the same complete run finishes fast enough to stay inside a single working session, so end-to-end verification becomes a routine step rather than something deferred to CI.

**Why this priority**: This is the entire point of the issue. Every other story exists to protect a property while this one delivers the value.

**Independent Test**: Time the full end-to-end suite before and after the change on the same machine with a warm environment. The runtime reduction is the deliverable; nothing else needs to be in place to observe it.

**Acceptance Scenarios**:

1. **Given** an unchanged working tree on the maintainer's machine, **When** the full end-to-end suite is run to completion, **Then** it finishes in materially less wall-clock time than the ~18-minute baseline and reports zero failures.
2. **Given** the continuous-integration environment, **When** the end-to-end job runs, **Then** it finishes faster than its pre-change baseline and remains green.
3. **Given** the suite has been sped up, **When** the maintainer runs a single end-to-end test file in isolation, **Then** the per-invocation startup cost is no worse than it is today.

---

### User Story 2 - Failures still point at one test (Priority: P1)

A test fails. The maintainer needs the failure report to name the one behavior that broke, reproduce it by running that test alone, and get the same result. If speed were bought by letting tests share state or run in ways that make one failure cascade into a dozen, the suite would be faster and less useful.

**Why this priority**: The issue names this as a hard constraint, not a nice-to-have. A fast suite whose failures cannot be localized is a regression, so this is co-equal with P1 speed.

**Independent Test**: Deliberately break one application behavior, run the full suite, and confirm that the failure set is attributable to that behavior and that each named failing test reproduces on its own.

**Acceptance Scenarios**:

1. **Given** a single deliberately introduced application defect, **When** the full end-to-end suite runs, **Then** the failures reported correspond to the affected behavior and do not include tests of unrelated behaviors.
2. **Given** any single end-to-end test that failed during a full-suite run, **When** that test is run by itself, **Then** it fails the same way — the failure is not an artifact of what ran before it.
3. **Given** any single end-to-end test, **When** it is run by itself against a clean environment, **Then** it passes without depending on data or state left behind by another test.
4. **Given** the full end-to-end suite, **When** it is run twice in succession on an unchanged tree, **Then** both runs pass and no test consumes a retry.

---

### User Story 3 - Coverage is preserved, not traded away (Priority: P1)

The maintainer needs confidence that the faster suite still checks everything the slow one did. Speed achieved by deleting tests, weakening assertions, or quietly skipping scenarios would be a loss disguised as a win.

**Why this priority**: The issue makes preserved coverage a constraint on the solution. Violating it invalidates the whole change, so it gates acceptance alongside speed.

**Independent Test**: Compare the set of behaviors exercised before and after. Every scenario asserted today must still be asserted after, whatever structural reorganization happened in between.

**Acceptance Scenarios**:

1. **Given** the pre-change suite's set of asserted behaviors, **When** the post-change suite is compared against it, **Then** every behavior is still asserted somewhere in the suite.
2. **Given** a test that was merged or restructured to save setup cost, **When** its assertions are reviewed, **Then** each original assertion is still present and still meaningful.
3. **Given** the post-change suite, **When** it is run, **Then** no test is newly skipped, and no end-to-end test has been deleted without its assertions being carried elsewhere.

---

### User Story 4 - Future tests inherit the improvement (Priority: P2)

Six months from now the maintainer (or an AI agent working in this repo) adds three new end-to-end tests. Without written guidance they will be modelled on whatever file is open, and the habits that made the suite slow — unconditional waits, redundant setup, one-file-per-bug sprawl — will creep straight back in. The performance work needs to be encoded as a convention, not just a one-time cleanup.

**Why this priority**: Protects the gain over time rather than delivering it. Real, but the speed-up has value even on day one without it.

**Independent Test**: Have someone unfamiliar with this work read the project documentation and write a new end-to-end test; confirm the documentation told them how to wait for readiness, what setup to reuse, and where the test belongs.

**Acceptance Scenarios**:

1. **Given** the updated project instructions and developer documentation, **When** a contributor looks for guidance on adding an end-to-end test, **Then** they find explicit, actionable rules covering waiting/synchronization, setup and fixture reuse, and test placement.
2. **Given** the updated documentation set, **When** `CLAUDE.md`, the developer/testing documentation under `docs/`, and the project context under `_bmad-output/` are reviewed, **Then** all three reflect the new conventions and none still describes the superseded approach.
3. **Given** a newly written end-to-end test that follows the documented conventions, **When** it is added to the suite, **Then** it does not measurably degrade total suite runtime.

---

### User Story 5 - An assessment and an approved plan precede the changes (Priority: P1)

Before any test file is touched, the maintainer wants a written assessment of where the ~18 minutes actually goes — setup and teardown, shared dependencies, fixtures, and the tests themselves — paired with a concrete change plan and a quantified estimate of the expected improvement. The maintainer reviews and approves that plan before implementation begins.

**Why this priority**: The issue requires this gate explicitly. Implementing first and justifying afterwards is not the requested deliverable.

**Independent Test**: Confirm that a written assessment and plan exist, that the plan attributes runtime to specific causes with evidence, that it states an estimated post-change runtime, and that it was approved before implementation commits landed.

**Acceptance Scenarios**:

1. **Given** the assessment, **When** it is reviewed, **Then** it accounts for the current runtime across setup/teardown, dependencies, fixtures, and test bodies, with measured evidence rather than assertion.
2. **Given** the plan, **When** it is reviewed, **Then** each proposed change states its expected time saving and its risk to failure localization or coverage.
3. **Given** the plan, **When** it is presented, **Then** work stops for maintainer review and no implementation change is made until the plan is approved.
4. **Given** the assessment's measurements, **When** the plan addresses concurrent execution, **Then** it either shows that serial-only changes reach the target and recommends staying serial, or shows that they fall short and makes an explicit, separately-approvable case for concurrency.

---

### Edge Cases

- **A wait that was doing real work.** Some fixed-duration waits are unknowingly masking a genuine readiness gap. Replacing them with condition-based waiting must surface that gap as a deterministic wait on the real condition — not as a new intermittent failure.
- **A test that silently depended on leftover state.** If per-test reset is reduced or reorganized, a test that passed only because a previous test left data behind must be found and made self-sufficient, not left to fail intermittently based on ordering.
- **Retries hiding a regression.** The existing retry-on-failure behavior can absorb newly introduced flakiness and make it look like a pass. Acceptance must distinguish "passed" from "passed on the first attempt".
- **Reference data required by nearly every test.** The fixed reference-data set is re-inserted before all 371 tests. Any scheme that seeds it less often must guarantee that a test which modifies it cannot corrupt the tests that follow.
- **Local and CI environments differ.** One environment provisions its own database, the other consumes a pre-provisioned one. An improvement that only helps one of the two environments only solves half the problem.
- **The screenshot-generation flow shares this infrastructure.** Documentation screenshots are produced through the same end-to-end machinery and must continue to work unchanged.
- **A test that is genuinely slow.** Some behaviors — bulk creation, photo upload, label printing — are inherently expensive. The suite must not get faster by making these shallower.
- **Serial-only changes land close to the target but short of it.** If the assessment shows serial work recovering, say, 45% against a 50% target, the plan must say so plainly and let the maintainer choose between accepting the smaller win and authorizing concurrency — not quietly reach for concurrency to close the gap.
- **Existing time budgets.** Project governance currently mandates a 20-minute allowance for the end-to-end run. If the run gets substantially faster, that documented allowance should be revisited so it still describes reality.

## Requirements *(mandatory)*

### Functional Requirements

**Assessment and approval**

- **FR-001**: The work MUST begin with a written assessment attributing the current end-to-end runtime to specific causes across setup/teardown, shared dependencies, fixtures, and test bodies, supported by measurement rather than inspection alone.
- **FR-002**: The assessment MUST be accompanied by a change plan in which each proposed change carries an estimated time saving and a stated risk to coverage or failure localization.
- **FR-003**: The plan MUST state an estimated post-change suite runtime.
- **FR-004**: Implementation MUST NOT begin until the maintainer has reviewed and approved the plan.

**Performance**

- **FR-005**: The full end-to-end suite MUST complete in materially less wall-clock time than the ~18-minute baseline, measured on the same machine under comparable conditions.
- **FR-006**: The improvement MUST hold in both the local development environment and the continuous-integration environment.
- **FR-007**: Waiting for the application to reach an expected state MUST be based on observing that state, not on elapsed time, except where no observable condition exists — and each such exception MUST be justified in a comment at the call site.
- **FR-008**: Per-test setup and teardown MUST NOT repeat work whose result is already valid for the test about to run.
- **FR-009**: Whether end-to-end tests run concurrently rather than one at a time MUST be decided by the assessment, not assumed up front. The assessment MUST measure how much of the runtime the serial-only changes (FR-007, FR-008) can recover, and the plan MUST recommend concurrency only if those changes alone fall short of the target.
- **FR-010**: If the plan recommends concurrency, it MUST state how each concurrent worker gets isolated application state, what a failure report looks like under concurrency, and what the added infrastructure costs — and the maintainer MUST approve that recommendation separately from the rest of the plan before any concurrency work begins.
- **FR-011**: If the plan does not recommend concurrency, the suite MUST remain strictly serial; concurrency MUST NOT be introduced incidentally.

**Preserved correctness**

- **FR-012**: Every behavior asserted by the pre-change suite MUST still be asserted by the post-change suite.
- **FR-013**: No end-to-end test may be deleted, skipped, or have assertions weakened as a means of reducing runtime.
- **FR-014**: Each end-to-end test MUST pass when run in isolation against a clean environment, without depending on state left by another test.
- **FR-015**: A failure in one end-to-end test MUST NOT cause unrelated tests to fail, so that a failure report identifies the broken behavior.
- **FR-016**: The post-change suite MUST pass consecutive full runs on an unchanged tree without any test consuming a retry.
- **FR-017**: The documentation-screenshot generation flow MUST continue to function.

**Durability of the improvement**

- **FR-018**: The project instructions (`CLAUDE.md`), the developer/testing documentation under `docs/`, and the project context under `_bmad-output/` MUST be updated to describe the conventions that future end-to-end tests are expected to follow.
- **FR-019**: That documentation MUST cover, at minimum: how to wait for application state, which setup and fixtures to reuse rather than recreate, and where a new test belongs relative to existing files.
- **FR-020**: Documentation that describes the superseded slower approach MUST be corrected or removed rather than left alongside the new guidance.
- **FR-021**: Any project-governance statement about end-to-end runtime allowances MUST be updated to match the new measured runtime.

### Key Entities

- **End-to-end suite**: The full set of browser-driven tests exercising the running application; 371 test functions across 57 files today. The unit of measurement for this feature.
- **Shared test infrastructure**: The application server and database instance provisioned once per run and shared by every test. The primary determinant of both fixed startup cost and per-test reset cost.
- **Per-test reset**: The work performed between tests to return the shared environment to a known state. Repeated 371 times per run.
- **Reference data set**: The fixed catalog data that nearly every test requires to be present. Currently re-created as part of every per-test reset.
- **Assessment and plan**: The written analysis and proposed change set that must be approved before implementation.
- **Test-authoring conventions**: The documented rules that keep future tests from reintroducing the removed costs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The full end-to-end suite completes in **10 minutes or less** on the maintainer's machine, down from the measured 1347.6s (22m 27s) baseline — a reduction of at least 55%. The plan projects ~8m 38s optimistic and ~10m 24s conservative; the target is set at the conservative figure so that meeting it does not depend on every judgement call going the best way.
- **SC-002**: The continuous-integration end-to-end job's wall-clock duration is reduced by at least 40% relative to its pre-change average over the last five runs.
- **SC-003**: All end-to-end tests pass — **377 collected today (376 passing, 1 skipped)**, or 361 after C3 removes the 16 screenshot-generation tests from this session — and the count of asserted behaviors is unchanged or higher.
- **SC-004**: Zero end-to-end tests are skipped, and zero are deleted without their assertions being carried into another test.
- **SC-005**: Three consecutive full end-to-end runs on an unchanged tree pass with zero retries consumed.
  **Met.** This feature never got past two consecutive clean runs, and left two failures unexplained (recorded in [plan.md](./plan.md) and raised as #66). Both turned out to be the same thing — a submit the browser refused, leaving no trace in the DOM, so an item that was never created only surfaced steps later somewhere unrelated. `specs/003-e2e-remove-timed-waits/` found and fixed both causes; the `TypeError: Failed to fetch` that preceded them was a byproduct of navigating away from the list mid-request, not the cause. Three consecutive clean `--reruns=0` runs on `afafd0a`, 2026-08-07: **362 passed at 8m 05s, 8m 05s and 8m 09s**.
- **SC-006**: Every end-to-end test passes when run individually against a clean environment.
  **Met.** Spot-checked only during this feature; `specs/003-e2e-remove-timed-waits/` ran the full one-at-a-time sweep on 2026-08-06 — **362 of 362 pass alone**, zero failures.
- **SC-007**: With one application behavior deliberately broken, 100% of the resulting failures are attributable to that behavior, and each failing test reproduces its failure in isolation.
- **SC-008**: Measured `wait_for_timeout` execution time falls from **423.9 seconds across 479 executions** to **under 60 seconds**, with every surviving instance carrying a written justification at its call site. Measured with the blocking-call probe described in [quickstart.md](./quickstart.md) — *not* by summing the literal arguments in the source, which understates the real cost by 2.2×.
  **Met.** This feature took it to 121.6s across 212 executions, short of the target; `specs/003-e2e-remove-timed-waits/` finished the job on 2026-08-06 and took it to **0 seconds across 0 executions** — `wait_for_timeout` no longer appears in the probe output at all, and there are no surviving instances to justify.
- **SC-011**: `wait_for_load_state("networkidle")` does not appear anywhere in `tests/e2e/`.
- **SC-012**: Running the end-to-end session leaves the working tree clean — in particular, no file under `docs/images/screenshots/` is modified.
- **SC-009**: `CLAUDE.md`, the `docs/` testing guidance, and `_bmad-output/` project context each describe the new conventions, and a review finds no remaining description of the superseded approach.
- **SC-010**: A new end-to-end test written by following only the updated documentation runs without adding measurable time to the suite total.

## Assumptions

- **SC-001's target is now derived from measurement, not chosen.** It began as a working 50% guess. The Phase 0 assessment measured the baseline at 1347.6s and the achievable reduction at 55–62%, so SC-001 was restated to ≤10 minutes at plan-approval time on 2026-08-06. The earlier ≤9-minute figure is reachable on the optimistic path but left under a minute of slack, which is not a target worth committing to.
- **Concurrency was considered and rejected on the evidence.** The serial changes reach the target on their own; see C5 in [plan.md](./plan.md). FR-011 therefore binds: the suite stays serial.
- **"Materially less" in FR-005 is quantified by SC-001.** The two are the same requirement stated at different altitudes.
- **The assessment/plan/approval gate (FR-001 through FR-004) is satisfied by this specification workflow's planning phase** — the plan document plus explicit maintainer approval before implementation. No separate process is needed.
- **Runtime is measured on a warm environment**: dependencies already installed, browser binaries already downloaded, container images already pulled. Cold-start provisioning is environment noise, not suite performance, and is excluded from the baseline and the target alike.
- **Test count may change if tests are consolidated.** SC-003 tracks asserted behaviors, not test-function count; merging two tests that assert three things each into one test asserting six is acceptable, provided FR-014 and FR-015 still hold for the merged test.
- **The existing retry-on-failure behavior stays.** It is a safety net for genuine environmental flakiness, not a target of this work — but SC-005 requires that the improved suite not actually need it.
- **Concurrency is deferred, not excluded.** Per the maintainer's decision on 2026-08-05, whether to run tests concurrently is settled by the assessment's measurements at the plan-approval gate rather than committed to now. The default is serial: concurrency has to earn its way in by demonstrating that FR-007 and FR-008 alone cannot reach the target. This follows the project's don't-optimize-without-a-measurement principle.
- **No new test infrastructure is introduced for its own sake.** Per project principles, optimizations require an observed cost; every change must trace to a measurement in the assessment.
- **Scope is the end-to-end suite only.** The unit and integration suites, the deliberately low coverage gate, and the sub-second unit suite are explicitly out of scope and must not be altered.
- **Application behavior does not change.** This is a test-suite change. If the assessment finds that an application-side change (for example, an observable readiness signal that tests could wait on) is the cheapest fix, that is in scope only as an additive, non-behavioral affordance and must be called out in the plan.
