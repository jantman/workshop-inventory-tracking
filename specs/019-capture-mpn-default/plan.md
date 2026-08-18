# Implementation Plan: The Captured Listing Fills In the Manufacturer Part Number

**Branch**: `issues/90` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/019-capture-mpn-default/spec.md`

## Summary

A capture reads the vendor's product-information rows, displays them, and then leaves the
Manufacturer Part Number field blank even when one of those rows is the part number. This feature
derives a default for that field from the rows themselves.

The whole of it is one method on `ListingCapture`, one constant tuple of five recognized names in
priority order, one shared name-folding helper lifted out of the existing barcode-row matcher, one
Jinja expression changed from a truthiness test to a presence test, and three lines in the capture
route joining the field to the absent-versus-empty fallback that `manufacturer` and `unit_price`
already use.

No migration. No new endpoint. No payload version bump. No new dependency. No JavaScript.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x, Jinja2, SQLAlchemy 2.0.x — all already present. **Nothing is
added.**

**Storage**: MariaDB via the existing `Storage` ABC. **No schema change**; see
[data-model.md](./data-model.md).

**Testing**: `nox -s tests` (unit, network blocked, sub-second), `nox -s e2e` (Playwright, 15-minute
timeout required), `nox -s screenshots_headless` + `screenshots_verify`. The capture page **is**
screenshotted — `tests/e2e/test_screenshot_generation.py::test_screenshot_order_capture` writes
`docs/images/screenshots/user-manual/order_capture.png`, which 018 regenerated for the same reason.
It is not in `screenshot_config.yaml`; that file drives a different set.

**Target Platform**: Flask app on a home LAN, single trusted operator, server-rendered Bootstrap 5 UI.

**Project Type**: Web application, server-rendered. No frontend build step and none introduced.

**Performance Goals**: Unchanged. The derivation is five passes over roughly twenty-five in-memory
dict entries, on a request that already spends eight to fifteen seconds retrieving a gallery. SC-007
asks that capture time not move, and nothing here can move it.

**Constraints**: The derived value must never exceed what
`Product.manufacturer_part_number` can store (`String(100)`, `app/database.py:838`), and must never
be truncated to fit — see [research.md](./research.md) §4.

**Scale/Scope**: Four source files, one template, three test files, one test fixture, one
screenshot, one documentation paragraph. Roughly 60 lines of application code including docstrings.

## Constitution Check

*GATE: passed before Phase 0. Re-checked after Phase 1 — see below.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** (NON-NEGOTIABLE) | **Pass.** One method, two constants, one moved helper. No new module, no new class, no interface, no configuration knob. The two rejected designs — a payload field emitted by the capture agent, and a computed value threaded to four render sites — were both rejected on this principle and the reasoning is recorded in [research.md](./research.md) §1 and §5. The one thing that *looks* like generality, extracting `normalized_row_name`, is required by FR-001 and has two real callers on day one. |
| **II. Layered Architecture Boundaries** | **Pass.** The derivation is domain logic and lives in `app/models.py`. The route stays thin: it reads a form field and picks a fallback, exactly as it already does for two other fields. No ORM query and no SQL is added anywhere. `app/catalog_service.py` already imports from `.models`, so the new helper creates no new dependency edge and no inversion. |
| **III. Exact Numerics** | **Not engaged.** A part number is an opaque string. No measurement, no arithmetic, no `float`. |
| **IV. Test Discipline Through Nox** | **Pass.** Unit tests through `tests/conftest.py`'s fixtures, network blocked, nothing mocked because nothing makes a request. E2E waits are `expect(...).to_have_value(...)` on a server-rendered form — `CLAUDE.md` Pattern C, render-implies-completion — with no fixed wait anywhere. No new pytest marker. Both suites must be green before merge. |
| **V. MariaDB Is the Source of Truth** | **Pass, vacuously.** No schema change and therefore no Alembic revision. If a revision appears in the diff, the plan has been misread. |
| **VI. Item Lifecycle and History Invariants** | **Not engaged.** This touches the product catalog, not inventory items. No JA ID, no active-row filtering, no shortening history. |
| **Operating Context / Threat Model** | **Not engaged.** No auth, no new input surface, no sanitization. The field already exists and is already operator-editable; this changes only what it arrives holding. Validation here serves correctness — a value the database cannot store — not defense. |
| **Technology Constraints** | **Pass.** No new dependency. Type hints on both new public callables. No new error machinery: an unusable row returns `None`, which is the ordinary case. Server-rendered Jinja, no framework. |
| **Development Workflow** | **Pass.** Feature branch `issues/90`, merged by PR. `app/templates/product/capture.html` is edited, so the screenshot gate applies and regeneration is a planned task, not an afterthought. |

**Violations requiring justification**: none. The Complexity Tracking table below is empty and should
stay that way.

### Post-Phase-1 re-check

Re-evaluated after `data-model.md`, `contracts/` and `quickstart.md` were written. The design did not
grow: still one method, two constants, one moved function, one template expression, three route
lines. Two things were *removed* from the initial sketch during Phase 0 and are worth recording as
simplicity wins:

- A route-level helper computing the field's value and passing it to the template at four render
  sites. The presence test in the template does the same job with no route change
  ([research.md](./research.md) §5).
- Conditioning the default on whether the merge kept the row, by analogy with 016. It would require
  running a write path from a render path to answer a question the operator can see the answer to
  ([research.md](./research.md) §6).

**Still no violations.**

## Project Structure

### Documentation (this feature)

```text
specs/019-capture-mpn-default/
├── spec.md               # /speckit-specify output (amended in Phase 0 — see research.md §4)
├── plan.md               # This file
├── research.md           # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── README.md         # Phase 1 output — internal surface, no HTTP change
├── checklists/
│   └── requirements.md   # /speckit-specify output
└── tasks.md              # NOT created by /speckit-plan
```

### Source Code (repository root)

Five files. Nothing else should appear in the diff.

```text
app/
├── models.py                        # + normalized_row_name, + PART_NUMBER_ROW_NAMES,
│                                    #   + MANUFACTURER_PART_NUMBER_MAX_LENGTH,
│                                    #   + ListingCapture.manufacturer_part_number
├── catalog_service.py               # ~ _is_barcode_row_name calls the moved helper. Nothing else.
├── product/routes.py                # ~ product_capture: the absent-versus-empty fallback
└── templates/product/capture.html   # ~ one input's value expression: presence, not truthiness

tests/
├── unit/test_capture.py             # + the derivation, the prefill, the re-render, the fallback.
│                                    #   This is where every capture unit test already lives; see
│                                    #   TestTheListingPayload, TestTheListingFillsTheForm,
│                                    #   TestThePayloadSurvivesAQuestion, TestWhichRowNamesMeanABarcode
├── e2e/test_product_page_capture.py # + end to end through the bookmarklet
└── e2e/fixtures/amazon_listing.html # + a part-number row (it has a UPC row today, and no MPN row)

docs/
├── user-manual.md                   # ~ the "what the bookmarklet reads" list gains the part number
└── images/screenshots/user-manual/order_capture.png   # regenerated
```

**Structure Decision**: no new modules and no new packages. The feature is placed by asking where
each part of it belongs under Principle II, and every answer was an existing file. The derivation is
a fact about a `ListingCapture`, so it goes on `ListingCapture` in the domain layer; the fallback is
a route concern and joins two identical fallbacks already written three lines above it; the
redisplay rule is a display concern and is one Jinja expression.

## Approach

### Phase A — the shared fold (foundational, no behavior change)

Move the body of `_is_barcode_row_name` into `normalized_row_name` in `app/models.py` and have
`_is_barcode_row_name` call it. `tests/unit/test_capture.py` must stay green **untouched**; that is
the check that the move was verbatim. Nothing observable changes.

### Phase B — the derivation (US1, US3)

`PART_NUMBER_ROW_NAMES`, `MANUFACTURER_PART_NUMBER_MAX_LENGTH` and
`ListingCapture.manufacturer_part_number` in `app/models.py`, with unit tests in
`tests/unit/test_capture.py` beside `TestTheListingPayload`, which is where `ListingCapture`'s
existing tests live. Still nothing observable — no caller yet. At the end of this phase the whole of
FR-001 through FR-004 is proven, in under a second, with no app and no browser.

### Phase C — the render (US1)

The presence test in `app/templates/product/capture.html`. This is the point at which the feature
becomes visible, and it delivers US1 and US3 on its own: the field arrives filled on both first-render
paths. Route tests cover each render path.

### Phase D — the write (US2)

The absent-versus-empty fallback in `product_capture`. This closes FR-005 for a POST that carries the
payload and no field. Note that US2's *user-facing* half — a typed or cleared value winning — is
already true after Phase C, because the form submits what it displays; Phase D covers the submission
that omits the field entirely.

### Phase E — end to end, screenshots, docs

The user-manual sentence, the full suites, the screenshot regeneration, a diff review against the
file list above, and a by-hand pass against `B0CZ72JRHP` and `B0FX4PDW6M`.

The E2E fixture row and the E2E tests are **not** here — task generation moved them into the story
phases they prove, so each story is independently demonstrable end to end rather than only at the
end. See [tasks.md](./tasks.md).

Phases A→B→C are strictly ordered. D depends only on B. E depends on C and D.

## Risks and how they are bounded

| Risk | Bound |
|---|---|
| The moved fold silently changes barcode-row matching | `tests/unit/test_capture.py` is not edited. If it goes red, the move was not verbatim. |
| `manufacturer` or the unit price get "fixed" in passing | Explicitly out of scope by a spec assumption, called out in [contracts/README.md](./contracts/README.md), and a reviewable diff rule: those two hunks must not appear. |
| A too-clever unification of `normalized_row_name` and `_fold` | They answer different questions; `_fold` deliberately does not collapse internal whitespace. [research.md](./research.md) §2. |
| Screenshot churn swamping the diff | Regenerate, then inspect what actually differs and commit only the images whose content moved. |
| Scope creep into a one-off sweep over already-captured products | Out of scope by a spec assumption. This feature writes nothing on its own; it fills a form field. |

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified.

**No violations.** Table intentionally empty.
