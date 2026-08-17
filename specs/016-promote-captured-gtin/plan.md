# Implementation Plan: A Captured Barcode Becomes a Scannable Identifier

**Branch**: `issues/93` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/016-promote-captured-gtin/spec.md`

## Summary

A capture that is handed a `UPC` row by the vendor's product-details table stores it as an ordinary
specification and nothing else, so the product stays unfindable by the barcode on its own box. This
adds one step to the capture write path: among the specification rows a capture **added**, any row
whose name is a recognized barcode name and whose value passes the existing GTIN validation becomes
a `GTIN` identifier on the product. The confirmation page then says what the barcode-named rows came
to.

The approach is deliberately thin: **no schema change, no migration, no new endpoint, no new
dependency, no template change.** Three edits to `app/catalog_service.py`, three lines in
`app/product/routes.py`, and tests. The check-digit arithmetic, the normalization, the uniqueness
constraint and the collision behavior all already exist and are reused as they are — see
[research.md](./research.md) §1.

**One spec amendment came out of Phase 0 and is already applied to `spec.md`:** the confirmation
page reports the barcode's *state* ("recorded on this product") rather than the *action* this
particular capture took. Distinguishing "recorded just now" from "was already there" would require
changing `capture_order`'s return type at ~80 call sites, which is far larger than the problem.
FR-009, FR-010 and SC-003 were reworded; the reasoning is [research.md](./research.md) §3.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x, SQLAlchemy 2.0.x, Jinja2 — all already present; this feature
adds none

**Storage**: MariaDB via SQLAlchemy. **No schema change and no Alembic revision** — the
`product_identifiers` table and its `uq_identifier_type_value_vendor` constraint already hold
everything this writes. See [data-model.md](./data-model.md)

**Testing**: `nox -s tests` (unit, SQLite through the same `Storage` interface) and `nox -s e2e`
(Playwright, ≥15-minute tool timeout). Both are required; the unit suite carries the classification
matrix and the E2E suite carries the one thing unit tests cannot prove — that a captured barcode is
scannable end to end

**Target Platform**: Server-rendered web UI on a home LAN, one user

**Project Type**: Flask web application, server-rendered

**Performance Goals**: None. A listing has at most one or two barcode-named rows; promotion adds one
`SELECT` and at most one `INSERT` each, and no external request (SC-006)

**Constraints**: The GTIN validation in `app/utils/gtin.py` MUST be reused rather than reimplemented
(FR-002, and the issue says so in as many words). No override path may be introduced (FR-004)

**Scale/Scope**: 2 application files, 1 E2E fixture, 3 test files. No migration, no template, no
JavaScript, no screenshots

## Constitution Check

*GATE: passed before Phase 0, re-checked after Phase 1 design — see the re-check at the end.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** (non-negotiable) | **Pass, and it decided the design twice.** No new module, no abstraction, no configuration knob, no new dependency; the recognized-name list is a module-level frozenset, not a settings key. It also decided §3 of research: the faithful-but-expensive reporting channel was rejected for being larger than the problem, and the spec was amended rather than the codebase churned. No retrofit sweep over existing products (spec Assumptions). |
| **II. Layered Architecture Boundaries** | **Pass.** All logic is in `CatalogService`; the route gains two lines (one service call, one `flash`) and no query. Nothing new touches `app/database.py` or the storage layer. The report is a plain dataclass in `app/models.py`, alongside `CaptureAssessment`, which is the established place for a display-only value object produced by a capture. |
| **III. Exact Numerics** | **Not applicable.** A GTIN is a digit string, never arithmetic. It is normalized by `str.zfill`, compared as text, and stored in a `String(128)` column. No `Decimal`, and emphatically no `float` — `int(barcode)` would drop leading zeros, which is why `app/utils/gtin.py` keys on the string and this feature does not touch that. |
| **IV. Test Discipline Through Nox** | **Pass, with obligations.** Unit tests for the classification matrix; E2E for capture → identifier → scan. Run through `nox`, never bare `pytest`. No new pytest marker. E2E waits on observable state only — the confirmation page's flash and the product detail's `#identifier-list` are both server-rendered, so `expect()` covers them; see [quickstart.md](./quickstart.md). The run must leave the working tree clean. |
| **V. MariaDB Is the Source of Truth** | **Pass.** No schema change, so no Alembic revision — the tell that the plan is right, not an omission. The "one product per barcode" rule stays a database constraint (`uq_identifier_type_value_vendor`); promotion relies on it rather than re-checking it in Python. |
| **VI. Item Lifecycle and History Invariants** | **Not applicable.** Nothing here touches JA IDs, active rows, shortening history or parent-child links. Products and their identifiers carry no such semantics. |
| **Operating Context / Threat Model** | **Pass.** Validation here serves correctness — a wrong barcode resolves a future scan to the wrong product — not defense. Nothing is sanitized against an attacker who does not exist. CSRF is unchanged; the write is the existing form POST. |
| **Development Workflow** | **Obligations.** Feature branch + PR (`issues/93`) — required, this is a non-trivial code change. **No screenshots**: `app/templates/**`, `app/static/css/**` and `app/static/js/**` are untouched, so the screenshot gate does not fire. If a task starts editing a template, stop and re-read this plan. |

**Gate result: PASS.** No violations, so [Complexity Tracking](#complexity-tracking) is empty.

## Project Structure

### Documentation (this feature)

```text
specs/016-promote-captured-gtin/
├── plan.md              # This file
├── spec.md              # Feature specification (amended in Phase 0 — see Summary)
├── research.md          # Phase 0: decisions, with what was rejected and why
├── data-model.md        # Phase 1: no schema change; the rows written; the report object
├── quickstart.md        # Phase 1: how to validate, automated and by hand
├── contracts/
│   └── README.md        # Phase 1: service surface, message shapes, reused contracts
├── checklists/
│   └── requirements.md  # Spec quality checklist (all pass)
└── tasks.md             # Phase 2 — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
app/
├── catalog_service.py                 # MODIFIED, three edits:
│                                      #   1. merge_specifications returns the rows it added
│                                      #      instead of a count
│                                      #   2. _apply_listing promotes the barcode-named ones
│                                      #      (new private _promote_barcode_rows)
│                                      #   3. new public describe_captured_barcodes() — read-only,
│                                      #      builds the confirmation report
├── models.py                          # MODIFIED: CapturedBarcode dataclass, beside
│                                      #   CaptureAssessment
└── product/routes.py                  # MODIFIED: product_capture flashes the tally
                                       #   (+ _barcode_tally helper, beside _image_tally)

tests/
├── unit/test_capture.py               # MODIFIED: promotion + report classes; two existing
│                                      #   merge_specifications assertions adjust to a list
└── e2e/
    ├── fixtures/amazon_listing.html   # MODIFIED: a UPC row in the tech-spec table
    └── test_product_page_capture.py   # MODIFIED: capture → identifier → scan; bad check digit
```

**Not touched, and deliberately so**: `app/utils/gtin.py` (reused verbatim — FR-002), `app/database.py`,
`migrations/`, every template, every JavaScript file, and the `/api/scan` route. The JSON
`/api/capture` endpoint is also untouched: it never passes a `listing`, so no capture through it can
have a barcode-named row to promote.

**Structure Decision**: The existing Flask layout, unchanged. The feature is business logic, so it
lives in `CatalogService`; the only presentation-layer change is a flash message.

## Implementation Notes

The detail that is easy to get wrong, gathered so `/speckit-tasks` can turn it into steps.

### The classifier (`app/catalog_service.py`, module level)

```python
BARCODE_ROW_NAMES = frozenset({'UPC', 'EAN', 'GTIN', 'ISBN', 'GTIN-13', 'UPC-A'})

def _is_barcode_row_name(name: str) -> bool:
    """FR-001: fold case and whitespace, then compare whole."""
    return ' '.join((name or '').split()).upper() in BARCODE_ROW_NAMES
```

Whole-name comparison, not a substring: `Manufacturer UPC` is not a `UPC` row, and treating it as
one is how a feature that promised six names quietly promotes anything.

### Promotion (`_apply_listing` → `_promote_barcode_rows`)

- `merge_specifications` returns **the validated entries it added** (`List[Dict[str, str]]`) instead
  of a count. `len(added)` is the old value, so `if added:` and the log line still read the same.
  Two assertions in `tests/unit/test_capture.py` move from `added == 2` to `len(added) == 2`.
- Promotion iterates that returned list, not `listing.specifications`. **That is the whole of
  FR-003** — a row the merge dropped is not in the list, so it cannot be promoted, and no separate
  "was it dropped?" check is needed anywhere.
- Per row: `key = gtin_utils.normalize_and_validate(value)`. `None` ⇒ log and move on (FR-004 — there
  is no override branch to write, because there is no override).
- Otherwise `self.add_identifier(product_id, IdentifierType.GTIN.value, key)`, catching
  `DuplicateItemError` (another product holds it — FR-006) and `ValidationError` (belt and braces)
  and logging each. **Neither propagates**: FR-011 says a refused promotion never fails the capture,
  and the purchase has already been resolved by this point.
- `add_identifier` already returns the existing row when *this* product holds the value, so FR-007
  needs no code — do not add a pre-check for it.
- Call `add_identifier` (the public method), not `_add_identifier`. `_apply_listing` runs outside any
  open session; the public method opens its own, which is the pattern the rest of `capture_order`
  follows.

### The report (`describe_captured_barcodes`, read-only)

Called by the route *after* `capture_order` returns, and derives every outcome from final state — it
writes nothing. For each barcode-named row in the listing, in order, deduplicated by normalized key:

| Condition on the row's value | Outcome | What the operator is told |
|---|---|---|
| Not a valid GTIN | `unusable` | not recorded, the value is not a valid barcode; it is a specification |
| This product holds the key | `recorded` | the barcode is recorded on this product |
| Another product holds the key | `taken` | not recorded, and which product holds it |
| Nobody holds the key | `not_examined` | the row was not examined, because the product already listed a row of that name |

The four are mutually exclusive and exhaustive, which is what makes them testable. The last one is
an inference rather than a flag: a valid value that no product holds can only mean the merge dropped
the row, because every added row was either promoted or collided. Say that in a comment — a later
reader will otherwise "fix" it by threading a flag through.

Deduplicate by normalized key: a listing carrying both `UPC` (12 digits) and `EAN` (the same code
with a leading zero) is one barcode, and reporting it twice reads like two.

### The route (`product_capture`)

```python
if listing is not None:
    notes = service.describe_captured_barcodes(purchase.product_id, listing)
    if notes:
        flash(_barcode_tally(notes), 'success' if all recorded else 'warning')
```

Placed immediately after `flash('Captured. ...')` and **before** the image block, so the identity
message sits above the image tally on the confirmation page. `_barcode_tally` goes next to
`_image_tally` and follows it: one string, everything that did not land is named.

### Tests

- The unit tests are where the matrix lives, one test per outcome, plus: an `EAN`/`GTIN`/`ISBN`/
  `GTIN-13`/`UPC-A` row promotes like `UPC`; ISBN-10 does not; a two-codes-in-one-value row does
  not; `upc` and ` UPC ` do; `Manufacturer UPC` does not; a dropped row does not; the equivalent
  UPC/EAN pair yields one identifier and one report line.
- E2E proves the two things unit tests cannot: the operator sees the message on the confirmation
  page, and the barcode then resolves through the find-by-code path (`tests/e2e/test_wedge_scan.py`
  has the scan pattern to copy).
- The fixture change is one `<tr>` in `amazon_listing.html`'s tech-spec table. Existing assertions
  there use `to_contain_text` and filtered counts rather than exact row lists, so they are not
  disturbed — but re-run the whole file, not just the new tests.
- Waits: the confirmation page and the product detail page are both server-rendered, so `expect()`
  on the flash text and on `#identifier-list` is the whole wait. No `wait_for_timeout`, no
  `networkidle`. Before any negative assertion (`no identifier was created`), establish the region
  with a positive `expect` first, or it passes against a page that has not loaded (`CLAUDE.md`).

## Complexity Tracking

No constitution violations, so nothing to justify.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *(none)* | | |

## Post-Design Constitution Re-check

Re-evaluated after Phase 1. **PASS, unchanged.**

The design produced no migration, no endpoint, no module, no dependency and no abstraction. It
reuses `app/utils/gtin.py` whole, leans on an existing database constraint instead of a Python
check, and leaves the presentation layer alone apart from one flash message. The one place it was
tempted into complexity — an exactly-accurate "recorded just now" report — was resolved by making
the requirement simpler rather than the code cleverer, which is Principle I working as intended.

Two obligations carry out of the gate: a PR from `issues/93`, and both `nox -s tests` and
`nox -s e2e` green before merge.
