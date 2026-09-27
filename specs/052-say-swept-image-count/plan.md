# Implementation Plan: Say When the Image Count Was Swept

**Branch**: `robot-army/issue-172-say-on-the-capture-page-when-the-image` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/052-say-swept-image-count/spec.md`

## Summary

The Amazon listing reader in the browser extension already knows when it fell back to
sweeping page text for gallery addresses — it `console.warn`s. Carry that fact as one
optional boolean on the capture payload (`images_swept: true`), one boolean field on
`ListingCapture`, and one conditional clause in each of the two templates that show a
listing's image count: `#summary-images` on the capture confirmation page and
`.line-listing-summary` on the Amazon order review. The warning stays. No payload version
bump, no persistence, no migration.

## Technical Context

**Language/Version**: Python 3.13 (server), plain browser JavaScript (extension content script)

**Primary Dependencies**: Flask 3.1, Jinja2, Bootstrap 5.3 — nothing new

**Storage**: N/A — the flag is informational and never persisted (FR-007)

**Testing**: pytest via nox (`tests` for unit, `e2e` for Playwright with the real extension agent)

**Target Platform**: Linux server on a home LAN; Chrome with the capture extension

**Project Type**: Server-rendered web application plus a browser extension

**Performance Goals**: N/A

**Constraints**: An extension that predates this change must keep working with no reload (FR-003)

**Scale/Scope**: One JS function and its caller, one dataclass field, two template clauses,
one user-manual sentence, a handful of tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| I. Simplicity First | ✅ One boolean carried along an existing path. No new abstraction, setting, or channel; the console warning is kept rather than replaced by machinery. |
| II. Layered Architecture | ✅ Parsing stays in `ListingCapture.from_data` (domain model, `app/models.py`); templates only read the field. No route or service changes. |
| III. Exact Numerics | ✅ Not touched — no measurement or price is involved. |
| IV. Test Discipline | ✅ Unit tests for parsing and both rendered summaries; e2e extends the existing unreadable-gallery test and adds an order case, all waiting on `expect(...)`, no fixed waits. Run through `nox`. |
| V. MariaDB Source of Truth | ✅ No schema change; nothing persisted. |
| VI. Item History Invariants | ✅ Not touched. |
| Screenshots gate | ✅ Templates change, but no documentation screenshot shows the capture confirmation page or the Amazon order review (`docs/images/screenshots/metadata.json`), and the caveat renders only on a swept capture. No regeneration needed. |

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/052-say-swept-image-count/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── listing-payload-images-swept.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
extension/capture-agent.js                  # galleryFrom() reports the sweep; extract() sets images_swept
app/models.py                               # ListingCapture.images_swept, read in from_data
app/templates/product/capture.html          # #summary-images caveat
app/templates/product/order_review.html     # .line-listing-summary caveat
docs/user-manual.md                         # one sentence on the caveat
tests/unit/test_capture.py                  # confirmation page renders / omits the caveat
tests/unit/test_order_product_details.py    # from_data parsing; order review per-line caveat
tests/e2e/test_product_page_capture.py      # unreadable-gallery capture shows the caveat
tests/e2e/test_order_product_details.py     # an order line with an unreadable gallery shows it
```

**Structure Decision**: Existing layout; every change lands in a file that already owns the
behavior it extends.

## Complexity Tracking

None.
