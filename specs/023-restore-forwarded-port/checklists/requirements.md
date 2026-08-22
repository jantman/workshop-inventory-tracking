# Specification Quality Checklist: Restore the Browser's Port Behind a Reverse Proxy

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-21
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

Two questions were open when the spec was drafted and both were answered on 2026-08-21 before it was
finalized, so no `[NEEDS CLARIFICATION]` marker survives into the spec:

1. **Which of the issue's candidate remedies the spec requires.** Answered: the application trusts a
   forwarded port declaration from the one hop it already trusts, and the deployment guide states
   that the proxy must send it. Recorded in Assumptions with the two alternatives and why each was
   rejected. This is what makes FR-002 and FR-011 a pair rather than two independent choices.
2. **Whether #113's blocked write-path check belongs here.** Answered: no. This feature unblocks it;
   #113 performs it. Recorded in Out of Scope, which is also what keeps SC-001 a form-submission
   check rather than a stored-file measurement.

Two things about the spec worth carrying into planning:

- **FR-008 and FR-009 are falsifiable by construction.** Both are required to fail against the code
  as it stands, and SC-004 is the assertion that they do. A test written after the fix that has
  never been seen to fail does not satisfy them.
- **SC-001, SC-002 and SC-003 can only be checked by hand** against the real deployment, because the
  defect exists only behind a real proxy on a real non-default port. The Assumptions section says so
  explicitly; planning should expect a manual verification task rather than treating these as
  automatable.

The one implementation term remaining in the spec is inside the **Input** block, which quotes the
issue's own title verbatim. That block is the record of what was specified from, and is not
rewritten, for the same reason `specs/` is excluded from the repository's spelling sweep.
