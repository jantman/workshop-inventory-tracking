# Specification Quality Checklist: Finish Removing Time-Based Waits from the E2E Suite

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-06
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

**On "no implementation details".** This feature's subject matter *is* the test suite, so test
file names and the `tests/e2e/` path appear throughout — they are how the scope is bounded, not
leaked implementation. The spec deliberately does not name the browser automation library, its API
methods, or the application's JavaScript modules: it says "fixed-duration wait", "readiness
signal", "the prohibited navigation-readiness wait", and "the move page's scan state machine"
rather than the concrete symbols. The one exception is the `>>DONE<<` scan code, which is domain
behavior a user types, not a code detail.

**Validation pass**: 3 iterations, no failures found in any. The second followed the addition of
US6 (encode the authoring practices this work learns); the third followed the maintainer's
2026-08-06 decision to move the guidance out of feature 002's spec directory into the constitution
and the project instructions, which converted FR-022's open question into FR-021 through FR-025.
Every functional requirement traces to at least one success criterion, and every user story to at
least one measurable outcome:

| Story | Requirements | Success criteria |
|---|---|---|
| US1 — ordinary in-gate files | FR-001–004, FR-009–012 | SC-001, SC-002, SC-005, SC-006 |
| US2 — move page scan flow | FR-005–008 | SC-001, SC-002, SC-007 |
| US3 — photo upload and clipboard | FR-005–008 | SC-001, SC-007 |
| US4 — screenshot generation | FR-003, FR-014 | SC-009 |
| US5 — retire the grandfather clause | FR-015–017 | SC-003, SC-004, SC-011 |
| US6 — encode what was learned, and move it | FR-018–025 | SC-012–SC-016 |

**On the relocation's verifiability.** "Move the docs" is the kind of requirement that passes by
assertion. It is pinned instead to a count taken from the tree: five live references cite the
contract as normative today — `CLAUDE.md:24`, `docs/development-testing-guide.md:359`,
`.specify/memory/constitution.md:134`, `_bmad-output/project-context.md:65`, and
`tests/e2e/waits.py:6`. SC-014 requires all five repointed, and names the source-file one because
a Markdown-only sweep would miss it. SC-016 guards the opposite error: feature 002's *historical*
citations are true and must survive, so the check is not simply "no mention of 002".

**On US6's testability.** A documentation story risks being unfalsifiable — "the docs are better"
cannot fail. Three things keep it testable: SC-012 requires every documented pattern to trace to a
call site this feature actually converted, which fails if a pattern was invented rather than
observed; SC-013 is an execution test, not a reading test; and FR-020 makes the *ordering* a
requirement, so guidance written from the plan rather than from the finished work is a defect
regardless of how it reads.

**Traceability to the prior feature.** SC-001 restates
`specs/002-e2e-test-performance/spec.md` SC-008, which is measured at 121.6s against a 60s target
and remains unmet. SC-010 restates 002's SC-011 as a non-regression. FR-016 requires 002's own
record to be corrected once this feature closes it.

**No clarifications were needed.** Two scope questions were resolved by informed default rather
than by asking, and both are recorded in the spec's Assumptions section so the maintainer can
overturn either at planning time: (1) automated enforcement of the waiting rule is out of scope,
per the project's simplicity principle and the fact that the constitution already states the rule;
(2) additive, non-user-visible readiness affordances in the application are in scope, following
the precedent set by feature 002.

Items marked incomplete would require spec updates before `/speckit-clarify` or `/speckit-plan`.
None are.
