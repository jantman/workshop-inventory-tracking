# Specification Quality Checklist: Product Catalog Documentation Overhaul

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

**Clarifications resolved** (2026-08-10):

- **Q1 — where the catalog guidance lives**: Option A. Re-level inside `docs/user-manual.md`;
  catalog topics become top-level `##` sections and the contents page groups into an
  inventory half and a catalog half. No separate manual. Recorded as FR-001 through FR-003.
- **Q2 — how far the spelling fix reaches**: Option C. Documentation, user-visible
  application text, and code comments and docstrings. `specs/` and `migrations/` stay
  excluded as frozen historical records. Recorded as FR-008 through FR-014.

**Correction to the Q2 estimate presented at decision time.** The question described option C
as "~20 extra one-word edits". The measured figure is **156 occurrences** across `app/` and
`tests/`, of which roughly **85 are code identifiers** rather than prose — a pytest fixture
named `catalogue` in `tests/unit/test_product_search.py` accounts for 71 references on its
own, and several test *function* names embed the spelling. Renaming those is a mechanical
refactor of test code, not a comment sweep.

Because that is a materially larger change than the decision was made against, the identifier
rename is carved out as **FR-011**, explicitly marked separable, with **FR-012** requiring it
to be behavior-preserving and test counts to be unchanged. Dropping FR-011 at planning time
still satisfies the intent of option C everywhere a human reads prose, and leaves the
remaining spelling work at roughly 70 prose edits. Two edge cases exist specifically to guard
FR-011: a test renamed out of pytest collection passes silently, and a blind
`catalogue`→`catalog` substitution turns `uncatalogued` into `uncatalogd`.

**On file paths in the requirements.** `docs/user-manual.md`, `README.md`, `CLAUDE.md` and
`docs/images/screenshots/` are named throughout. That is not implementation detail leaking in
— those documents are the deliverable.

**Constitutional check.** FR-021 (screenshot tests excluded from the standard sessions) and
SC-010 (the working tree stays clean) restate Principle IV, which the plan phase must honor
when it adds catalog screenshot tests. Any new pytest marker would need registering in
`pytest.ini`; the existing `screenshot` marker should suffice.
