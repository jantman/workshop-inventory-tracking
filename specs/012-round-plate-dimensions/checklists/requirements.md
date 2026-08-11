# Specification Quality Checklist: Round Plate Dimensions

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-10
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

- Three questions that would have been `[NEEDS CLARIFICATION]` markers were put to the
  operator before the spec was written, and their answers are recorded in **Assumptions**:
  diameter stays the measurement the inventory already records (no new stored dimension,
  no migration); Length remains on the form but stops being required; and Sheet is in
  scope alongside Plate. No marker survives in the spec.
- The spec names one behavior that is a *tightening* rather than a relaxation — FR-001
  requires Thickness for a round plate. The Add Item form already demands it; the rule
  keyed on shape alone does not. This is called out in Assumptions so it is not mistaken
  for scope creep during planning.
- FR-005 through FR-008 exist because the system holds several statements of the dimension
  rules that disagree with one another. The spec deliberately bounds the fix to round Plate
  and round Sheet and lists the wider reconciliation under **Out of Scope**; FR-008 holds
  the line by forbidding *new* disagreements.
- Issue #85 asks for a database schema change. The spec does not require one, and says why
  in Assumptions: the dimension already exists and is already optional in storage, so the
  requirement is imposed entirely above it. **Confirmed during planning** — `length` is
  already a nullable column and its check constraint already reads `IS NULL OR > 0`, so
  there is no Alembic revision in this feature. See `research.md` D8.

## Amendment — 2026-08-10, during `/speckit-plan`

Planning put one further question to the operator, because the spec could be read two ways
and the readings differed in size: should the dimension rules be *enforced* on the write
paths, or only stated consistently and marked on the forms? Today nothing enforces them
anywhere except as browser-side marks on the Add Item form, so the item API has always
accepted a round plate with no thickness.

The operator chose enforcement on every write path, over both narrower options, with the
blast-radius risk stated. The spec was amended rather than left contradicting the plan:

- **Added** FR-017 (enforce on every path), FR-018 (report every missing dimension, not the
  first), FR-019 (enforcement introduces no new requirement for any other combination).
- **Qualified** SC-005 and **added** SC-008 to separate *which* dimensions are required —
  unchanged for every other type and shape — from *where* the requirement is applied, which
  is what actually changes for them.
- **Added** two assumptions recording the decision and its bound: enforcement covers the
  paths a person can reach, not internal test seeding.
- **Extended** the Channel entry under Out of Scope with the one visible side effect that
  consolidating the rules forces — Channel's Shape dropdown narrowing to the shapes it is
  recorded as taking.

All checklist items above were re-run against the amended spec and still pass.
