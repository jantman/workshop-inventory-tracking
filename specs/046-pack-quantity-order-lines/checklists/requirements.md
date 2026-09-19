# Specification Quality Checklist: Packs Recorded as Units, and What a Pack Was Kept

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-19
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain — the three open questions were answered by the
      author and are recorded as *Decisions agreed before specifying* A, B and C
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded — FR-039 to FR-042 name what is deliberately untouched and why
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

### Shipping order

Five stories, each independently testable:

| Story | What it delivers | Depends on |
|-------|------------------|------------|
| US1 (P1) | The reported fix: a pack size on the Amazon order review | nothing |
| US2 (P2) | Which lines were converted, visibly | US1 |
| US4 (P2) | The same defect fixed on the single-listing page | nothing |
| US3 (P3) | Pack size suggested from the listing, marked as a guess | US2 — a guess is only safe on a review that shows conversions plainly |
| US5 (P3) | The pack is kept, so an order reconciles against its invoice | US1, US4; carries the migration |

US1 alone closes the issue. US5 is the only story requiring a schema change.

### Flags for planning

- **FR-030 changes McMaster.** Decision C says all three paths store the pack consistently, so
  McMaster's capture — which converts correctly today and discards the pack — gains retention.
  Its *conversion* is explicitly out of scope (FR-039). Do not treat the McMaster change as
  optional; it is what "consistently" means.
- **FR-033 has no page behind it yet.** It constrains hand-editing a captured purchase so stored
  pack values can never contradict the purchase's own numbers. Planning must decide between
  keeping them consistent and clearing them; the spec deliberately allows either.
- **Three code sites and one document assert the rule decision C reverses** — the McMaster review
  template, the capture confirmation template, the `ListingCapture` pack fields, and the user
  manual's *"When it is sold as a pack"*. All four say pack values are not stored. FR-035 to
  FR-038 cover the manual; the code comments need the same correction or they will mislead the
  next reader.
- **The reversal of `specs/029-whole-order-capture/research.md` §5** ("Amazon needs no pack
  arithmetic") is stated in Background so planning does not treat it as a contradiction to
  resolve. `specs/` is a frozen record and is not edited.
- **Constitution V** applies to US5: the schema change needs an Alembic migration, and the unit
  suite builds its schema with `create_all` rather than Alembic, so the model and the migration
  must match exactly or the drift passes `nox -s tests` and fails on the real database.
