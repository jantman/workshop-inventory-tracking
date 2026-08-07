# Feature Specification: Finish Removing Time-Based Waits from the E2E Suite

**Feature Branch**: `issues/65`

**Created**: 2026-08-06

**Status**: Draft

**Input**: GitHub issue #65 — "Finish removing time-based waits from the e2e suite (127 sites remain)". Follow-up to #47 / PR #64, which cut the e2e suite from 22m27s to ~9m45s but did not finish the job. SC-008 from `specs/002-e2e-test-performance/spec.md` is not met: measured `wait_for_timeout` execution time is 121.6s against a target of under 60s. Existing waits are grandfathered; new ones are not permitted. This issue is about clearing the grandfathered set.

## Current Baseline *(measured 2026-08-06)*

Carried forward from [feature 002](../002-e2e-test-performance/) so that "finished" is verifiable rather than felt. Feature 002 delivered the majority of the win; this feature closes the remainder.

| Property | After 002 (today) | Target |
|---|---|---|
| Wall-clock runtime of the e2e gate | **~585s (9m 45s)**, retries disabled | ≤ 8m 45s |
| Measured time spent in fixed-duration waits | **121.6s across 212 executions** | under 60s |
| Fixed-duration wait call sites in `tests/e2e/` | **127** (down from ~220) | 0 unjustified |
| — of those, running inside the e2e gate | **99** | 0 unjustified |
| — of those, in the excluded screenshot session | **28** | 0 unjustified |
| `wait_for_load_state("networkidle")` occurrences | **0** | stays 0 |
| E2E tests in the gate | 362 passing, 0 skipped | unchanged |

The 127 sites divide into three populations with genuinely different difficulty:

**Population A — the cheap half (42 sites, 17 files, in the gate).** Not known-hard; simply not reached before PR #64 landed. Each needs the same per-site judgement the finished files got.

| File | Sites |
|---|---|
| `test_shorten_items.py` | 5 |
| `test_material_field_validation.py` | 4 |
| `test_item_actions.py` | 4 |
| `test_duplicate_item.py` | 4 |
| `test_move_items_with_original_thread.py` | 3 |
| `test_label_print.py` | 3 |
| `test_bulk_creation.py` | 3 |
| `test_toggle_item_status.py` | 2 |
| `test_required_location.py` | 2 |
| `test_multi_row_ja_id.py` | 2 |
| `test_list_view_status_filter.py` | 2 |
| `test_inactive_item_pagination.py` | 2 |
| `test_add_item.py` | 2 |
| `test_product_search.py`, `test_move_items_basic.py`, `test_history_functionality.py`, `test_admin_materials.py` | 1 each |

**Population B — the hard half (57 sites, 4 files, in the gate).** Attempted during 002 and reverted.

- `test_move_items_sub_location.py` (42 sites). The move page's scan state machine finalises each queue entry through an awaited API call, and its queue UI only renders after the `>>DONE<<` code — so neither "barcode input cleared" nor "queue contains the item" is a valid readiness signal at the point the test needs one. Three successive candidate conditions each surfaced a further race, and the file was reverted.
- `test_copy_item_photos.py` (8), `test_photo_upload_bug.py` (4), `test_photo_upload.py` (3). Upload and clipboard flows complete asynchronously across several steps; replacing the waits broke 6 tests.

**Population C — outside the gate (28 sites, 1 file).** `test_screenshot_generation.py` no longer runs in `nox -s e2e` (excluded by `-m "e2e and not screenshot"`), so it does not affect the gate's runtime — but it still slows `nox -s screenshots` / `screenshots_headless`, and it is the largest single remaining offender in one file.

One further `time.sleep(0.1)` exists in `tests/e2e/test_server.py`, inside a server-startup polling loop. It waits on an observable condition (the server answering) and re-checks; it is a readiness poll, not a fixed delay, and is excluded from the 127.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The ordinary remaining files stop waiting on the clock (Priority: P1)

The maintainer opens any of the seventeen files in Population A and finds tests that assert on application state rather than counting seconds. Each of these files was skipped for reasons of time, not difficulty, so each is a self-contained piece of ordinary work: read the test, work out what it is actually waiting for, assert that.

**Why this priority**: This is the largest block of work that carries no research risk. It delivers a measurable share of the remaining time saving immediately, and it is the part most likely to be finished in full.

**Independent Test**: Convert the sites in any one of the seventeen files, run that file alone and then the full gate, and confirm the file passes, its assertions are unchanged, and the measured wait time has dropped by that file's contribution. No other population needs to be touched.

**Acceptance Scenarios**:

1. **Given** a file in Population A, **When** its fixed-duration waits are replaced by state assertions, **Then** the file passes both alone and inside the full gate, with no assertion removed or weakened.
2. **Given** `test_shorten_items.py`, `test_toggle_item_status.py` or `test_history_functionality.py` — which cover the item lifecycle and history invariants protected by Constitution §VI — **When** their waits are converted, **Then** every behavior they asserted before is still asserted, and only the mechanism of waiting has changed.
3. **Given** all of Population A converted, **When** the blocking-call probe is run against the gate, **Then** the measured fixed-duration wait time has fallen by an amount attributable to those forty-two sites.
4. **Given** a converted file, **When** the gate is run three times in succession, **Then** it passes every time without consuming a retry.

---

### User Story 2 - The move page's scan flow becomes observable (Priority: P1)

`test_move_items_sub_location.py` alone holds 42 of the 99 in-gate sites — the single largest concentration in the suite. The tests wait on the clock because, at the moment they need to know a scan has been accepted, the page offers nothing to observe: the queue entry is still being finalised through an awaited API call, and the queue UI does not render until the `>>DONE<<` code is entered. Making these tests wait on state means first understanding that state machine, and — if it genuinely exposes no signal — giving it one.

**Why this priority**: It is the biggest single win available and the one that decides whether the under-60s target is reachable at all. It also carries the most risk, having already been attempted and reverted once, so it needs to start rather than be left until last.

**Independent Test**: Map the move page's scan state machine, document where each scan becomes observable, convert the file, and run it alone and in the full gate. Success is the file passing repeatedly without retries — the previous attempt's failure mode was intermittent, so a single green run is not evidence.

**Acceptance Scenarios**:

1. **Given** the move page's scan behavior, **When** it is analysed before any test is edited, **Then** a written description exists of what an observer can detect after each step of the scan sequence, and each replacement wait cites a condition from that description.
2. **Given** the analysis finds no observable signal at a point where a test needs one, **When** a signal is added to the application to expose it, **Then** the addition is additive and changes nothing a user of the application can perceive.
3. **Given** the converted file, **When** it is run ten times in succession, **Then** it passes every time with zero retries consumed — demonstrating the race that reverted the previous attempt is closed rather than narrowed.
4. **Given** the converted file, **When** its assertions are compared against the pre-change version, **Then** every scan, queue and sub-location behavior it verified before is still verified.

---

### User Story 3 - Photo upload and clipboard flows wait for completion (Priority: P2)

The three photo files hold 15 in-gate sites. Their flows complete asynchronously across several steps — a file is selected, uploaded, processed, and rendered; a clipboard copy fans out into several items — and the previous attempt to replace the waits broke six tests because a single condition did not cover the whole flow. Each site needs to be matched to the step it is actually waiting on.

**Why this priority**: Real time saving and real risk, but a third the size of the move file. It earns its place after the two P1 stories rather than alongside them.

**Independent Test**: Analyse the photo manager's completion behavior, convert the three files, and run each alone and in the gate repeatedly. The six tests that broke last time are the specific regression to watch.

**Acceptance Scenarios**:

1. **Given** the photo upload and copy flows, **When** they are analysed before any test is edited, **Then** each asynchronous step's completion has a documented observable signal, or is explicitly recorded as having none.
2. **Given** the three converted files, **When** they are run in the full gate three times, **Then** all their tests pass every time with zero retries consumed.
3. **Given** a site whose step genuinely exposes no observable completion, **When** the wait is retained, **Then** it carries a justification at the call site naming the step and why nothing distinguishes "not yet" from "never".

---

### User Story 4 - Screenshot generation stops waiting on the clock (Priority: P3)

`test_screenshot_generation.py` holds 28 sites — the largest single file outside the move tests. It is excluded from the e2e gate, so it costs the maintainer nothing on a pre-merge run, but it is paid in full every time documentation images are regenerated, and it is the last place in `tests/e2e/` where the prohibited pattern still lives in bulk.

**Why this priority**: It does not move the number the issue is measured against, and the session it slows is run rarely. It is worth doing, and worth doing last.

**Independent Test**: Convert the file and run `nox -s screenshots_headless`, confirming it is faster and that the images it produces are equivalent to the ones committed today.

**Acceptance Scenarios**:

1. **Given** the converted file, **When** the screenshot session runs, **Then** it completes faster than before and every image it generates is substantively equivalent to the committed version.
2. **Given** the converted file, **When** the e2e gate runs, **Then** the working tree is still left clean — no file under `docs/images/screenshots/` is modified.

---

### User Story 5 - The rule stops being conditional (Priority: P3)

Today the project's guidance says the waiting rule binds new tests while existing waits are grandfathered. That caveat is a standing invitation to leave the last few in place. Once the set is cleared, the guidance should state the rule without exception, and the record of feature 002 should stop describing its own success criterion as unmet.

**Why this priority**: It is bookkeeping, and it can only be done truthfully once the preceding stories land. But leaving it undone means the next contributor reads a rule that says the old pattern is tolerated.

**Independent Test**: Read the project instructions and the constitution as a contributor would — plus the authoring contract if it still exists at that point — and confirm nothing describes existing time-based waits as tolerated. Read feature 002's spec and quickstart and confirm they no longer report SC-008 as outstanding.

**Acceptance Scenarios**:

1. **Given** every document that states the waiting rule, **When** they are reviewed after the conversion work, **Then** none of them grandfathers pre-existing time-based waits, and the exception for genuinely unobservable conditions is the only exception described.
2. **Given** feature 002's specification and quickstart, **When** they are reviewed, **Then** their record of SC-008 reflects the achieved measurement rather than the unmet one.
3. **Given** any wait that survives the conversion, **When** the documentation is reviewed, **Then** the surviving set is small enough and justified enough that a contributor reading the rule understands each survivor as an application of the stated exception, not as a leftover.

---

### User Story 6 - The next contributor inherits what this work learned (Priority: P3, final)

Converting the move page's scan flow and the photo upload paths will produce knowledge that exists nowhere today: which kinds of asynchronous behavior offer an obvious readiness signal, which need one added, and what a test should wait on when a flow completes across several steps rather than one. Today's guidance says what *not* to do and offers a table of simple conditions; it has nothing to say about the cases that took two attempts to solve. Worse, it lives in a completed feature's spec directory, so a contributor is sent rummaging through project history to find out how to write a test.

Once every population is converted and proven stable, that knowledge — the existing rules plus what this work learned — moves into the two places a contributor actually reads: the constitution for the rule, the project instructions for how to satisfy it. The next e2e test, written by the maintainer or by an agent working in this repo six months from now, should be fast by default rather than fast after a cleanup.

**Why this priority**: It cannot be written honestly before the work is done. Guidance invented ahead of the conversion would be speculation, and the two reverted attempts are proof that the hard cases do not yield to reasoning from first principles. This story is also the only thing standing between this feature and a third repetition of it.

**Independent Test**: After the conversion work is complete and stable, have someone unfamiliar with it write a new e2e test against a multi-step asynchronous flow using only the project instructions and the constitution — with the old contract path unavailable to them. Confirm the guidance told them what to wait on without their needing to read the converted tests, or project history, to find out.

**Acceptance Scenarios**:

1. **Given** all preceding stories are complete and their stability demonstrated, **When** the project instructions and the constitution are reviewed, **Then** they describe the authoring practices that keep the suite fast — including the multi-step and deferred-render cases this work solved — rather than only prohibiting fixed delays.
2. **Given** the patterns discovered while converting the previously-reverted files, **When** the guidance is written, **Then** each pattern names the situation it applies to and the observable condition it resolves to, so a contributor can match a new flow against it rather than reasoning from scratch.
3. **Given** the guidance has moved, **When** the repository is searched for pointers to the old contract, **Then** every one of the five live references has been repointed — including the one in the shared waits module's own documentation — and none resolves to a file that no longer holds the rules.
4. **Given** the constitution and the project instructions after the move, **When** they are read together, **Then** the constitution states the rule and its exception, the instructions state how to comply, and neither restates the other's material.
5. **Given** a new e2e test written by following only that guidance, **When** it is added to the suite, **Then** it contains no fixed-duration wait and adds no measurable time to the suite total.
6. **Given** the guidance, **When** its authorship is traced, **Then** it was written after the conversion was complete and stable — recording what was learned, not what was expected.

---

### Edge Cases

- **A wait that was doing real work.** Some of these delays are the only thing keeping a test from racing the application. Replacing one must surface that gap as a deterministic wait on the real condition — never as a test that passes nine times in ten. This is precisely how the move and photo files failed the first time.
- **The move page offers no signal at the point the test needs one.** Three candidate conditions have already been tried and each surfaced a further race. If the state machine genuinely exposes nothing observable at that point, the choice is between adding an observable signal to the application and retaining a justified wait — and that choice must be made deliberately, not by exhausting attempts.
- **Constitution §VI files.** `test_shorten_items.py`, `test_toggle_item_status.py` and `test_history_functionality.py` protect the item lifecycle and history invariants. Converting a wait there may change *how* the test waits and must never change *what* it asserts.
- **A second failed attempt.** Two file groups have already been attempted and reverted. Repeating an open-ended trial-and-error loop wastes the effort again; each of these needs its underlying behavior mapped before test edits begin, and a bounded outcome — converted, or retained with a written reason.
- **Retries hiding new flakiness.** The suite retries failures up to three times. A conversion that introduces a race can still report green. Acceptance must distinguish "passed" from "passed on the first attempt", and repeated runs are the only evidence that counts.
- **Measurement by counting rather than timing.** Summing the literal arguments in the source understates the real cost by about 2.2×, because sites inside page-object helpers execute repeatedly. The target is measured against execution time, and a conversion that removes many cheap sites while leaving one expensive helper site can look like progress and deliver none.
- **A conversion that is fast but shallow.** Replacing a delay with an assertion that is trivially true — waiting for an element that was already on the page — removes the time cost and the safety at once. The replacement must be the condition the next line actually depends on.
- **Leverage in page objects.** Some of these sites sit in shared helpers. One conversion there changes the behavior of every test that calls it, including tests in files nobody intended to touch. The blast radius of a helper change is the whole suite.
- **Screenshot output drift.** Converting the screenshot file changes when each image is captured. An image taken a moment earlier may catch an animation mid-flight, producing a technically-passing test and a worse-looking document.
- **The last few sites may be legitimately unconvertible.** Asserting that something does *not* happen within a debounce window has no observable condition by construction. These are expected to survive, and the target is set with room for them.
- **A pointer left behind after the move.** Five live documents send a contributor to the contract inside feature 002's spec directory to learn the rules, and one of them is a source file — the shared waits module's own documentation — which is easy to miss when sweeping Markdown. A single missed pointer is worse than not having moved at all: it sends the reader to a file that no longer holds the rules.
- **A superseded copy that outlives its supersession.** If the old contract keeps its body after the guidance moves, the repository holds two statements of the same rules, and an agent grepping for "wait_for_timeout" finds both. Feature 002's own FR-020 named this failure — new guidance placed *beside* stale guidance rather than replacing it — and the move must not recreate it.
- **History cited as if it were law.** Some references to feature 002 are historical attribution: the suite took 22m 27s until that work. Those are true and worth keeping. Stripping them along with the normative pointers would erase why the rules exist, which is the part that makes contributors follow them.
- **Guidance split into two homes that drift.** Splitting the rule from the practice across the constitution and the project instructions is only an improvement while they stay in sync. If the practical guidance later acquires a stricter rule than the governing one, the constitution stops describing what the project actually does.
- **Guidance written too early.** The final documentation story draws its content from the two file groups that were reverted once already. If it is written from the plan rather than from the finished conversion, it records an expectation — and an expectation that has already been wrong twice is worse than no guidance at all.
- **Guidance that restates the prohibition.** The existing rule already says "no fixed delays". Documentation that adds emphasis without adding a pattern a contributor can apply to a *new* flow leaves them exactly where they started, and it is the likeliest failure mode of a documentation task written at the end of a long change.

## Requirements *(mandatory)*

### Functional Requirements

**Scope of the conversion**

- **FR-001**: Every fixed-duration wait in `tests/e2e/` MUST either be removed, or be retained with a written justification at its call site naming the condition that cannot be observed.
- **FR-002**: A removed wait MUST be replaced by an assertion on the application state the following code depends on — not by a shorter delay, and not by an assertion that would hold before the awaited work completed.
- **FR-003**: All three populations MUST be addressed: the forty-two ordinary in-gate sites, the fifty-seven previously-reverted in-gate sites, and the twenty-eight sites in the excluded screenshot file.
- **FR-004**: The readiness-poll loop in `tests/e2e/test_server.py` — which re-checks an observable condition rather than waiting a fixed period — is out of scope and MUST be left as it is.

**How the hard files are approached**

- **FR-005**: Before any test in `test_move_items_sub_location.py` or the three photo files is edited, the asynchronous completion behavior of the underlying page MUST be mapped in writing, identifying what an observer can detect after each step.
- **FR-006**: Each replacement wait in those files MUST cite a condition from that mapping, so that a failure points at a wrong understanding of the state machine rather than at an untested guess.
- **FR-007**: Where the mapping shows no observable signal exists at a point a test requires one, an additive readiness signal MAY be introduced into the application, provided it changes nothing a user can perceive and is called out explicitly in the plan.
- **FR-008**: Where neither a condition nor an affordance is available, the wait MUST be retained under FR-001 with its reason recorded — an unconvertible site is an acceptable outcome; an unexplained one is not.

**Preserved correctness**

- **FR-009**: Every behavior asserted by the suite before this work MUST still be asserted after it. No test may be deleted, skipped, or have an assertion weakened.
- **FR-010**: In the files covering item lifecycle and history invariants, changes MUST be confined to the waiting mechanism; the assertions themselves MUST be untouched in substance.
- **FR-011**: Every e2e test MUST continue to pass when run in isolation against a clean environment.
- **FR-012**: The suite MUST pass consecutive full runs on an unchanged tree without any test consuming a retry, so that a conversion which merely narrows a race is not mistaken for one that closes it.
- **FR-013**: The prohibited navigation-readiness wait MUST remain absent from `tests/e2e/`; conversions MUST NOT reintroduce it as a substitute for a state assertion.
- **FR-014**: The documentation-screenshot flow MUST continue to produce images equivalent to those committed today, and running the e2e gate MUST continue to leave the working tree clean.

**Closing the record**

- **FR-015**: Wherever the waiting rule is stated at the time this work lands, it MUST be restated without the grandfathering caveat, retaining only the exception for genuinely unobservable conditions. If the relocation required by FR-021 has already happened, that means the project instructions and the constitution; if it has not, the authoring contract is included too.
- **FR-016**: Feature 002's specification and quickstart MUST be updated so their record of the wait-time success criterion reflects the achieved measurement rather than the outstanding one.
- **FR-017**: The final measurement MUST be taken with the execution-time probe rather than by counting call sites in the source, and the resulting figure MUST be recorded alongside the count of surviving justified waits.

**Encoding what the work learned**

- **FR-018**: `CLAUDE.md` and the constitution MUST be updated to describe the practices that keep future e2e tests fast, not only the prohibition on fixed delays. Guidance that states what to avoid without stating what to do instead does not satisfy this requirement.
- **FR-019**: That guidance MUST cover the cases the conversion actually had to solve — at minimum, waiting on a flow that completes across several asynchronous steps, and waiting on a state machine whose result is not rendered until a later stage. Each pattern MUST name the situation it applies to and the observable condition it resolves to.
- **FR-020**: The guidance MUST be written only after the conversion work is complete and its stability demonstrated under FR-012 and SC-007, so that it records what was learned rather than what was anticipated.
**Where the guidance lives** *(settled by the maintainer on 2026-08-06; see Assumptions)*

- **FR-021**: The e2e authoring guidance MUST be moved out of `specs/002-e2e-test-performance/contracts/e2e-test-authoring.md` and into the project instructions and the constitution. No live document may direct a contributor to a completed feature's spec directory to learn how to write a test.
- **FR-022**: The two destinations MUST divide by altitude, not by duplication: the constitution carries the governing rule — the prohibition, its one exception, and the requirement that an exception be justified in writing — and the project instructions carry the practical guidance for complying with it, including the patterns from FR-019. Neither may restate the other's material.
- **FR-023**: The project instructions MUST be the single normative source for e2e authoring practice, and every other location that summarises these rules — the developer testing guide, the project context under `_bmad-output/`, and the shared waits module's own documentation — MUST point there rather than at the superseded contract. All five live references identified today MUST be updated; a dead or stale pointer left behind is a failure of this requirement.
- **FR-024**: The superseded contract MUST NOT survive as a second copy of the rules that can drift from the first. Its content moves; what remains at that path, if anything, may only redirect.
- **FR-025**: References to feature 002 that cite it as *history* — that the suite took 22m 27s until that work, that it removed the navigation-readiness wait — are legitimate and MUST be left intact. Only references that treat it as the live source of authoring rules are in scope for removal.

### Key Entities

- **Fixed-duration wait site**: A single call that blocks for a set period rather than until a condition holds. 127 exist today; the unit this feature counts down.
- **Readiness signal**: An observable property of the running application — an element appearing, a value settling, a control becoming usable — that tells a test the work it triggered has finished. The thing each removed wait must be replaced by.
- **The e2e gate**: The set of tests run before merge, currently 362 passing in ~585s. 99 of the 127 sites run inside it; the other 28 do not.
- **The grandfathered set**: The pre-existing waits that current guidance tolerates while forbidding new ones. Clearing it is the point of this feature; retiring the concept is its last step.
- **The blocking-call probe**: The instrument that attributes execution time to blocking calls. Authoritative for the target, because counting call sites understates the real cost by about 2.2×.
- **Move-page scan state machine**: The sequence by which a scanned code becomes a finalised queue entry. Its observability is the open question behind the single largest concentration of sites.
- **Authoring guidance**: The standing instructions a contributor reads before writing an e2e test. Today it is prohibitive, scattered across four documents, and normatively rooted in a completed feature's spec directory. This feature makes it prescriptive and gives it one home. Its new content is an *output* of the conversion work, not an input to it.
- **The superseded contract**: `specs/002-e2e-test-performance/contracts/e2e-test-authoring.md`, the current normative source, cited by five live references. After this feature it is no longer a source of rules.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Measured time the e2e gate spends in fixed-duration waits falls from **121.6s across 212 executions** to **under 60s**, measured with the execution-time probe rather than by summing source literals.
- **SC-002**: The full e2e gate completes in **8 minutes 45 seconds or less**, down from ~9m 45s. The figure is derived, not chosen: removing at least 62s of measured wait time from a 585s run leaves 523s, and the target adds a small allowance for judgement calls that go the other way.
- **SC-003**: Every fixed-duration wait remaining anywhere in `tests/e2e/` carries a written justification at its call site. The count of unjustified sites is **zero**, down from 127.
- **SC-004**: The number of surviving justified waits is recorded, and each names the condition that cannot be observed — a reviewer can read the list and agree with every entry without consulting the author.
- **SC-005**: The gate still collects and passes **362 tests with zero skipped**, and a review of the change finds no assertion removed without an equivalent taking its place.
- **SC-006**: Three consecutive full gate runs on an unchanged tree pass with **zero retries consumed**.
- **SC-007**: `test_move_items_sub_location.py` and the three photo files each pass **ten consecutive runs** with zero retries — a higher bar than the rest of the suite, because these are the files a previous attempt left intermittently failing.
- **SC-008**: Every e2e test passes when run individually against a clean environment.
- **SC-009**: The documentation-screenshot session runs faster than before, produces images substantively equivalent to those committed today, and the e2e gate leaves `docs/images/screenshots/` unmodified.
- **SC-010**: The prohibited navigation-readiness wait appears **zero** times in `tests/e2e/`, unchanged from today.
- **SC-011**: A contributor reading every document that states the waiting rule finds it stated without a grandfathering caveat, and finds feature 002's record reporting its wait-time criterion as met.
- **SC-012**: `CLAUDE.md` and the constitution each describe **at least the two cases this work had to solve** — the multi-step asynchronous flow and the state machine whose result renders late — and every documented pattern can be traced to a specific call site converted by this feature. A pattern with no such call site behind it was invented rather than learned.
- **SC-013**: A new e2e test written against a multi-step asynchronous flow by following only the updated guidance contains **zero** fixed-duration waits, passes, and adds no measurable time to the suite total — written without reference to the converted test files themselves.
- **SC-014**: **Zero** live documents direct a contributor to `specs/002-e2e-test-performance/` to learn how to write an e2e test. All five references identified today — the project instructions, the developer testing guide, the constitution, the project context, and the shared waits module — resolve to the new home instead.
- **SC-015**: The repository holds **one** statement of each authoring rule. A reviewer comparing the constitution against the project instructions finds no sentence carried in both, and no rule stated in one place that contradicts the other.
- **SC-016**: References to feature 002 as *history* — the 22m 27s baseline, the work that removed the navigation-readiness wait — are still present. The move removed pointers to a source of rules, not the record of why the rules exist.

## Assumptions

- **The count is 127, not 128.** A raw search of `tests/e2e/` returns 128 matches. The extra one is a 0.1-second re-check inside `test_server.py`'s startup polling loop, which waits on an observable condition and is therefore not the pattern this feature removes.
- **The target is "no unjustified waits", not "no waits".** The authoring contract already permits a wait where no observable condition exists — asserting that something does *not* happen within a debounce window, for example. SC-001's 60-second allowance exists to accommodate that residue. A conversion effort that ends with a handful of well-explained survivors satisfies this feature; one that ends with bare delays does not.
- **Additive application changes are in scope; behavioral ones are not.** This follows the precedent set by feature 002: if the cheapest way to make a flow observable is a non-behavioral readiness affordance in the application, that is permitted and must be called out in the plan. Changing what the application does for a user is not.
- **The guidance's home was decided by the maintainer on 2026-08-06, not left to the plan.** The authoring rules move out of feature 002's spec directory into the constitution and the project instructions. What was FR-022's open question is now FR-021 through FR-025. The reasoning: guidance a contributor must find by reading project history is guidance that will be skipped, and it gets worse as more features accumulate spec directories.
- **The split is by altitude: the constitution governs, the instructions instruct.** The constitution already carries the prohibition, its exception, and the requirement to justify an exception in writing — that is governance and it stays there. Everything about *how* to comply — the condition table, the worked cases, the patterns from FR-019 — goes to the project instructions, which become the single normative source for practice. This is the only split that avoids the two documents restating each other.
- **The developer testing guide and the project context keep their summaries and change only their pointer.** The maintainer named two destinations, but four documents carry e2e guidance today. Emptying the other two would scatter the reader differently rather than less; leaving them pointing at a superseded contract would strand them. So they keep their short summaries and point at the project instructions. The fifth reference, in `tests/e2e/waits.py`, is a source-file docstring and is repointed the same way.
- **What remains at the old contract path is a plan-level detail, within a stated bound.** FR-024 requires only that no maintainable second copy of the rules survives. Whether that means a redirect stub, a supersession banner over a preserved body, or removal is left to the plan — with the constraint that git history already preserves the original text, so nothing is lost by choosing the smallest option. Feature 002's internal references to its own contract are part of that feature's record and are not live pointers.
- **The final documentation story is gated on proof, not on completion.** US6 begins only once US1–US4 are converted *and* the stability evidence in SC-006 and SC-007 is in hand. "The tests pass" is not the gate; "the tests pass ten times without a retry" is. This is deliberate: the guidance's whole value is that it describes solutions that held, and both hard file groups previously produced solutions that looked correct and were not.
- **US5 and US6 are separate stories because they do opposite things.** US5 removes guidance that has become false — the grandfathering caveat, feature 002's unmet-criterion record. US6 adds guidance that has become true. US5 could be done as soon as the sites are cleared; US6 cannot be done until they are proven.
- **Automated enforcement is out of scope.** The rule is stated in the constitution, and the review checklist that accompanies it moves to the project instructions along with the rest of the practical guidance. Adding a lint rule or merge gate to police it would be scale machinery the project's simplicity principle specifically resists, and the maintainer is the only contributor. If the maintainer wants a mechanical check, it is a separate decision rather than an implied part of this work.
- **Test consolidation is out of scope.** The one-file-per-feature-area rule constrains new tests and is not licence to merge existing files. It survives the relocation unchanged, and the move tests remain spread across several files after this work.
- **Runtime is measured warm** — dependencies installed, browser binaries present, container image pulled — on the maintainer's machine, consistent with feature 002's baseline. Cold-start provisioning is environment noise and is excluded from both the baseline and the target.
- **The suite stays serial.** Feature 002 considered and rejected concurrent execution on the evidence, and nothing in this feature reopens that question.
- **Retries stay in place** as a safety net for genuine environmental flakiness, but every measurement and acceptance run here is taken with them disabled, because a retried pass is indistinguishable from a real one otherwise.
- **The screenshot file's exclusion from the gate is settled.** Converting its waits speeds the screenshot sessions; it does not change which session runs it.
- **Scope is `tests/e2e/` only.** The unit and integration suites, the deliberately low coverage gate, and the sub-second unit suite are untouched.
