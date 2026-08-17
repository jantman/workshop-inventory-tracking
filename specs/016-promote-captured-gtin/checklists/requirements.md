# Specification Quality Checklist: A Captured Barcode Becomes a Scannable Identifier

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-17
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

Two questions were open on the first pass and were settled by the owner on 2026-08-17:

1. **Which rows promotion reads** — only the rows the capture actually added to the specification
   list, not every row it read. Recorded in FR-003 and the "A row the merge dropped" edge case.
   **Consequence worth carrying into planning:** a product that already lists a barcode-named row
   never gains the identifier by re-capture, and that includes `B01N4OSKWE`. The issue's verification
   step has to be run against a product without that row, or after deleting it. Stated in SC-001 and
   in the "Nothing is retrofitted" assumption.
2. **What the confirmation page reports** — everything: what was recorded, and every barcode-named
   row that was not, with the reason. FR-009. FR-010 extends that to a row the merge dropped, so the
   rule in (1) is never silently surprising.

**Amended during `/speckit-plan` (2026-08-17).** Planning found that reporting the *action* this
capture took — as opposed to the barcode's resulting *state* — would require changing
`capture_order`'s return type at roughly 55 call sites, for the sake of staying silent on a repeat
capture instead of repeating one true sentence. FR-009 was reworded to be state-shaped, FR-009a was
added to say so explicitly, FR-010's silent-case exception collapsed into it, and SC-003 and two
acceptance scenarios follow. The pricing is in [research.md](../research.md) §3. Nothing about what
gets *written* changed.

Two judgments were taken as defaults rather than asked, and are recorded in the Assumptions: a
value holding several space-separated barcodes is not promoted, and no retrofit sweep over
already-captured products is in scope.

`FR-009a` from the first draft was renumbered to `FR-010`; the requirements now run FR-001..FR-013
with no gaps.
