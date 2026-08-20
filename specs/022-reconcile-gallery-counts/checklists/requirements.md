# Specification Quality Checklist: Gallery Image Counts — Reconcile the Expectation with the Listing

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-20
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

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.
- **The specification is deliberately outcome-neutral, and that is not vagueness.** Issue #95's whole
  point is that the reported symptom has two explanations which predict the same number, and that the
  choice between them is made by looking rather than by reasoning. FR-006 through FR-009 describe
  correct capture behaviour and are testable on their own terms; FR-010 and FR-020 make "no code
  changed" an explicit, checkable end state rather than an absence of one. SC-006 requires the record
  to name which of the two ended up true, so the feature cannot finish ambiguous.
- **FR-001 through FR-005 and FR-019 constrain how the work is done, not only what it produces.**
  Unusual for a specification, and kept for the same reason the equivalent requirements were kept in
  feature 021: the failure mode being guarded against is concluding from inferred markup. Issue #95
  requires the live signed-in reading in as many words, and a specification that described only the
  outcome would permit the guess it was written to prevent.
- **Three references to concrete artifacts survive review** — `specs/021-fix-aplus-image-selection/`
  in the Terminology and FR-011, and the 1601×1601 / 358,055-byte figure throughout US4. These are
  provenance and scope boundaries, not design: the first says which neighbouring feature must not be
  disturbed, the second is the measurement whose staleness is the knock-on the issue raises. Neither
  prescribes an implementation.
- **FR-018's "the extractor's own commentary" is as close as this gets to naming code.** It is a
  consistency requirement about a figure, not a design instruction — the same measurement is quoted
  as justification in more than one place, and a correction that leaves one of them contradicting the
  record has not finished. Where those places are belongs in the plan.
- **No [NEEDS CLARIFICATION] markers were raised.** The one genuinely open question — whether the
  table aged or the extractor is short — is answered in the browser session with the owner, not by
  the owner in advance, and the specification is built to accept either answer. Two smaller
  judgement calls were resolved as documented assumptions rather than as questions: the scope of the
  reading is the two ASINs the issue names (the other four are a possible follow-up), and the A+
  listings' floors are left alone because issue #94's feature has already moved what feeds them.

## Re-validation after the Phase 0 probe (2026-08-20)

The probe ran during `/speckit-plan` and **falsified two items in this specification and confirmed a
third from an unexpected direction**. All amendments are in `spec.md`, each traced to the observation
that forced it in [research.md](../research.md).

| Amended | What changed | Observation |
|---|---|---|
| The "probe table has aged" assumption | Falsified. It did not age — it was never a gallery count. #57's column is a whole-document `hiRes` sweep, family-wide, and reproduces exactly today | research §3 |
| US2, FR-021 (new) | The defect is a doubling, not a shortfall: one photograph stored twice, the second at 500 px | research §2 |
| FR-022 (new) | The JSON parse has never matched real markup on any listing | research §1 |
| FR-023 (new) | §1b's *inference* is wrong too, not only its numbers | research §3 |
| US4, FR-017, SC-004 | The FR-004 re-anchoring is a no-op; what B4 needs is a filename stem | research §5 |
| US5 | Raised P3 → P2. The silent fallback is not a hypothetical | research §1 |
| FR-010, FR-020 | Marked not-triggered rather than deleted | research §6 |

The checklist re-runs clean against the amended text. Three notes on why the amendments do not
weaken it:

- **"Requirements are testable and unambiguous" is strengthened.** FR-021 and FR-022 name observable
  conditions — one stored image per gallery entry, and the array located in the form the vendor
  serves — where the original set could only say "matches the page data", which was true of the
  broken behaviour on `B0CKXJLP4B` by coincidence (14 = 14, from two unrelated causes).
- **"Scope is clearly bounded" survives the widening from two listings to six.** The spec's own
  assumption named the condition for widening — evidence the table is systematically rather than
  individually wrong — and the probe met it in its first two measurements. The assumption is marked
  superseded rather than quietly ignored.
- **The outcome-neutral construction did its job and is now spent.** FR-010 and FR-020 (the
  "no defect found" branch) are marked not-triggered rather than deleted, because deleting them would
  hide that the specification was written before the answer was known — which is the property that
  made it safe to write at all.

One item is deliberately left open rather than resolved: issue #95's "Captured 7" is not reproducible
on either listing today (research §8). It is recorded as an open observation with candidates, not
explained away, and it does not gate the work — the defect is present on all six listings regardless
of which number the verifier read, and the first implementation task settles it by running one real
capture.
