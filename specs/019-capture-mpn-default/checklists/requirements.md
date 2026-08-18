# Specification Quality Checklist: The Captured Listing Fills In the Manufacturer Part Number

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-18
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

- **Iteration 1 finding, fixed.** FR-003's usability test originally read "non-empty"; the
  length ceiling was added after the review asked what happens to a candidate longer than the
  field accepts, which is why US3 carries it as an acceptance scenario rather than an
  edge-case note.
- **Corrected during Phase 0 planning (2026-08-18).** The rationale attached to that ceiling was
  wrong. It claimed an over-long rendered value would put the input into the `tooLong` state and
  block submission with an unexplained browser bubble. HTML's `tooLong` constraint applies only
  after the *user* edits a control, so a server-rendered over-long value submits normally -- and
  then fails on the `String(100)` column at the end of a fifteen-second capture, because nothing
  in the stack checks the length. The requirement did not change; US3's "Why this priority", US3
  scenario 2 and FR-003 were rewritten to state the real failure. See
  [research.md](../research.md) section 4.
- **Iteration 1 finding, fixed.** FR-007 originally read "both capture paths MUST behave the
  same". That is trivially true and untestable — the pasted-address path carries no product
  information rows at all. Restated as a single shared rule, with the reason recorded in the
  Assumptions.
- **Deliberate scope call for the planner's attention.** FR-006 requires a cleared field to stay
  cleared when the confirmation form comes back with a question. The adjacent Manufacturer and
  Unit Price fields do **not** behave this way today — they re-apply their derived default on
  re-render. The issue's wording ("the operator must still be able to clear or change it") is
  read as requiring the stronger behavior for this field, and the last Assumption records that
  aligning the other two is out of scope. If the owner would rather have three consistent fields
  than one correct one, this is the requirement to revisit.
- **Terminology exclusion.** The recognized names in FR-001 are quoted as vendors spell them, so
  `Mfr Part Number` and `Item model number` keep their source capitalization. These are data
  values being matched, not prose.
