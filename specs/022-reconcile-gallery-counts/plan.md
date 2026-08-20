# Implementation Plan: Gallery Image Counts — Reconcile the Expectation with the Listing

**Branch**: `issues/95` | **Date**: 2026-08-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/022-reconcile-gallery-counts/spec.md`

## Summary

Issue #95 reports `B0CKXJLP4B` capturing 7 gallery images where #80 §1b expects 14, and
`B099F4X4Q9` capturing 7 where it expects 16. Both landed on the thumbnail-strip number, which §1b
names as the signature of reading the rendered page instead of the page data — but the verifier
could only find 7 images on `B0CKXJLP4B` at all, which is the signature of a stale expectation.

**The probe ran on 2026-08-20, and both explanations were wrong.** All six of #57's ASINs were read
in the owner's signed-in Chrome; [research.md](research.md) has the numbers. Two findings, one cause:

**1. `initialImageArray()` has never matched a real listing.** It searches for a bracket immediately
after `initial':`; every listing serves `'initial': A.$.parseJSON('[…]')`, with a function name and a
quote in between. The search returns `-1` on all six, so the JSON parse never runs and
`sweepImageAddresses()` — the fallback for a block "not shaped the way this expects" — has answered
**every capture ever made**. Silently: nothing distinguishes a parsed gallery from a swept one.

**2. The sweep matches `hiRes` *and* `large`, so every photograph arrives twice.** The two are
different asset ids, so they survive both `withoutTransform()` and the server's content dedupe as
distinct files. `B0CKXJLP4B` stores each picture at 1601×1601 **and** at 500×500. The reported
symptom was a shortfall; the actual behaviour is a doubling. Today: 14 and 12 addresses for two
listings that publish **7** gallery images each.

**And #80 §1b was never right.** Its expected column is the count of distinct `hiRes` addresses in
the *whole document* — every sibling variant included — which reproduces all six of #57's numbers
exactly on 2026-08-20 (14, 16, 3, 7, 11, 9). `B0CKXJLP4B`'s 14 is 7 gallery images plus 8 pack
variants. So the table did not age; it measured a different thing. Worse, §1b's B1 tells a verifier
that landing on the thumbnail number proves a DOM read — and on five of six listings the gallery and
the strip are the same number, so that check can only be failed by being correct.

The fix is two edits in `app/static/js/capture-agent.js`: find the array wherever the listing puts
it, and emit one address per gallery entry. No Python, no schema, no migration, no new dependency.
Every listing roughly halves — 14→7, 12→7, 6→3, 14→7, 14→8, 14→7 — and every image lost is a
duplicate of one that stays.

**The FR-004 knock-on turned out to be a no-op**: `81flPsAWG-L.jpg` still measures 1601×1601 /
358,055 bytes, unchanged since 2026-08-09. What B4 needs is not a new number but the *filename stem*,
because until the fix lands half the stored "originals" are 500×500 copies and measuring the wrong
one looks like the failure B4 hunts.

**The probe amended the spec in seven places** — two new requirements (FR-021, FR-022), one more for
the record (FR-023), three success criteria, and the falsified "the table has aged" assumption.
[research.md](research.md) records each against the observation that forced it.

## Technical Context

**Language/Version**: ES5-compatible browser JavaScript (`app/static/js/capture-agent.js` runs
unbundled and untranspiled on a vendor's page). Python 3.13 for the test suite only. No Python is
edited under either outcome.

**Primary Dependencies**: None added. The probe uses Chrome driven against amazon.com; the tests use
Playwright, already present.

**Storage**: MariaDB, **untouched**. No schema change, no Alembic revision, no data migration — see
[data-model.md](data-model.md). Images already captured short are corrected by re-capturing, never
by editing rows (spec Assumptions).

**Testing**: `nox -s tests` and `nox -s e2e`. Gallery reading is covered today by
`tests/e2e/test_product_page_capture.py` against `tests/e2e/fixtures/amazon_listing.html`, whose
`colorImages.initial` array carries six entries. Under the no-defect outcome the suite is not
touched at all. The e2e session needs a ≥15-minute bash timeout and must be run detached — it
outruns the 10-minute cap.

**Target Platform**: Chrome on the operator's Linux workstation reading amazon.com, signed in;
Flask app on the same LAN over HTTPS.

**Project Type**: Server-rendered Flask web application with a single injected client-side script.

**Performance Goals**: None. Nothing here is measured for speed and Principle I's measurement rule is
not engaged.

**Constraints**:

* The reading the agent performs is not the tab the operator is looking at. `canonicalDocument()`
  re-fetches `/dp/<ASIN>` same-origin and parses it with `DOMParser`, falling back to the live
  `document` with a console warning if that fetch fails. **Every probe measurement must be taken
  from the fetched document**, the way feature 021's probe was, or it measures the wrong artifact.
* That document is detached and unstyled — no layout, no `naturalWidth`, no `getComputedStyle`. Any
  fix must be structural.
* The reader must not be able to throw. A page-data shape that stops matching must cost images,
  never the capture.
* The live listings are third-party and may change between the probe and the fix. Anything the probe
  establishes is recorded with its date, and anything the suite must keep true is carried into the
  fixture rather than left pointed at amazon.com.

**Scale/Scope**: Six listings probed. Two functions edited (`initialImageArray()`,
`sweepImageAddresses()`), one console line added, one fixture block replaced with the real markup
shape, a handful of e2e assertions, and six corrected figures across #80 §1b and 007's quickstart,
research and open manual task. Single user, LAN-only.

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design. Both passes recorded below.*

| Principle | Verdict | Note |
|-----------|---------|------|
| **I. Simplicity First** | **PASS** | Two named edits — find the array wherever it is, emit one address per entry — plus one `console.warn`. No abstraction, no configuration, no "image classifier". *Post-probe*: the FR-009 watch item is no longer conditional (the fallback is the **only** thing that has ever answered, so the silence is the reason this ran a whole release undetected) and it is still one line. Declined explicitly: a JavaScript evaluator for the payload, which is plain JSON once located; deduping by asset id or fetched byte size, which treats the symptom the entry already answers; deleting `sweepImageAddresses()` now that the parse works, because this feature is the direct result of not noticing when a reading silently degraded; and any column recording which rendition a `Photo` came from ([data-model.md](data-model.md)). |
| **II. Layered Architecture Boundaries** | **PASS (N/A)** | No route, service, storage or model file is touched under either outcome. Any change sits on the vendor side of the payload boundary, whose contract is unchanged — the server receives a list of addresses and does not learn where they came from. |
| **III. Exact Numerics** | **PASS (N/A)** | No measured physical quantity. Image counts and pixel dimensions are integers; byte sizes are integers. No `Decimal`, and no `float` either. |
| **IV. Test Discipline Through Nox** | **PASS, with obligations** | Under the defect outcome: coverage lands in `nox -s e2e` against a fixture carrying the real page-data structure, run detached with a ≥15-minute timeout, no new pytest marker, and every wait on observable state. The capture assertions read a server-rendered region, so no `count()` may precede the `expect()` that establishes it. Under the no-defect outcome the suite is untouched and must still be run once, green, to show that. |
| **V. MariaDB Is the Source of Truth** | **PASS** | No schema change, so no migration. Recorded explicitly in [data-model.md](data-model.md) so "where would the extra images live" cannot be answered by inventing a column. Nothing is hand-edited in the database. |
| **VI. Item Lifecycle and History Invariants** | **PASS (N/A)** | Inventory items are untouched. This is the product catalog. |
| **Operating Context / Threat Model** | **PASS (N/A)** | No authentication, validation or hardening surface is involved. The listing is read with the operator's own signed-in session, as it already is. |
| **Workflow: branch and PR** | **PASS** | `issues/95`, merged by pull request. The record corrections are documentation, but they ship with any code change rather than ahead of it, so #80 §1b never disagrees with `main`. |
| **Workflow: screenshots** | **Triggered under the defect outcome, expected no-op** | `app/static/js/**` is touched only if `galleryFrom()` changes. `capture-agent.js` is never loaded by an application template, so no screenshot can depend on it. Run `nox -s screenshots_verify` to establish that rather than assert it, and measure any diff before committing an image — regeneration is not reproducible (#80 §6). |
| **Governance: `specs/` is a frozen record** | **PASS by design** | FR-016 requires dated amendments beside the original figures rather than overwrites. Feature 021's spec is the precedent: it struck through what the probe falsified and left it legible. |

## Project Structure

### Documentation (this feature)

```text
specs/022-reconcile-gallery-counts/
├── plan.md              # This file
├── research.md          # Phase 0 — the browser probe and what it settled
├── data-model.md        # Phase 1 — the entities, and the explicit "no schema change"
├── quickstart.md        # Phase 1 — how to re-derive every number in this feature
├── contracts/
│   └── gallery-reading.md   # Phase 1 — what a gallery reading must contain
├── checklists/
│   └── requirements.md  # Written by /speckit-specify
└── tasks.md             # Phase 2 — /speckit-tasks, not this command
```

### Source code (repository root)

Only these paths are in play, and the list did not grow when the probe confirmed a defect:

```text
app/static/js/capture-agent.js          # initialImageArray()   — find the array inside parseJSON('…')
                                        # sweepImageAddresses() — one address per entry, not two
                                        # galleryFrom()         — say when the fallback answered

tests/e2e/fixtures/amazon_listing.html  # the colorImages block, rewritten in the A.$.parseJSON('…')
                                        #   form the vendor actually serves
tests/e2e/test_product_page_capture.py  # gallery-count assertions

specs/007-product-page-capture/         # quickstart.md §B, tasks.md T052, research.md — the
                                        #   expected counts and the FR-004 baseline, amended
                                        #   with dates rather than overwritten
```

Corrections outside the repository: **#80 §1b's table and its B1/B4 checklist items**, which is
where the verification pass actually reads from.

**Structure Decision**: No new files in `app/` or `tests/`. The gallery reading is three small
functions in one client-side file and there is nothing to extract, move or introduce. The feature's
centre of gravity is the probe and the record; the code change is the smaller half.

## Phase 0 — the probe: **done, 2026-08-20**

Ran in the owner's signed-in Chrome with the owner present, against the **fetched** `/dp/<ASIN>`
document rather than the rendered tab. Scope widened from the issue's two listings to all six of
#57's once the first two showed the cause was structural — the condition the spec's own assumption
named for widening. Full findings in [research.md](research.md); the headline table is §0.

| ASIN | Gallery entries | Agent today | Thumbnails | Whole document | #80 §1b said |
|---|---|---|---|---|---|
| `B0CKXJLP4B` | **7** | 14 | 7 | 14 | 14 |
| `B099F4X4Q9` | **7** (2 × `hiRes` null) | 12 | 7 | 16 | 16 |
| `B01N4OSKWE` | **3** | 6 | 3 | 3 | 3 |
| `B0DMNXC4CD` | **7** | 14 | 7 | 7 | ≥ 7 |
| `B09GM8FB3X` | **8** (2 × `hiRes` null) | 14 | 7 | 11 | ≥ 11 |
| `B0FX4PDW6M` | **7** | 14 | 6 | 9 | ≥ 9 |

FR-004's anchor was re-measured and is unchanged (research §5). The variant question is answered and
needs no code (research §4). **One thing the probe did not settle** and which is recorded as open
rather than explained away: issue #95's "Captured 7" is not reproducible on either listing today —
both paths return 14 and 12, and the panel renders the raw payload count. Research §8 lists the
candidates; the first implementation task settles it as a by-product by running one real capture.

## Phase 1 — design artifacts: **done**

Written after the probe, because what they say depends on what it found:

* **[data-model.md](data-model.md)** — the reading, the recorded expectation, and the explicit
  statement that no schema, no migration and no stored data is involved.
* **[contracts/gallery-reading.md](contracts/gallery-reading.md)** — what a gallery reading must
  contain and what it must never contain, stated so it can be checked against a listing rather than
  against the code that produces it.
* **[quickstart.md](quickstart.md)** — how to re-derive every number this feature records, so the
  next verification pass can tell an aged figure from a fresh one without a second archaeology
  session. This is the artifact FR-015 and SC-007 are really about. It also says how to recognise the
  low-resolution twins already sitting on captured products, since the fix stops them recurring but
  removes none of them.

## Constitution re-check after Phase 1

Re-evaluated against the designed change rather than the anticipated one. **No verdict moved**, and
the two that could have:

* **Principle I** was the one at risk, because a doubling defect invites a dedupe mechanism. The
  design has none: the listing's own entry already says which addresses are one photograph, so the
  fix is to read the entry instead of pattern-matching around it. Fewer moving parts than today's
  code, not more.
* **Principle V** was at risk from the same instinct one layer down — a column recording which
  rendition a `Photo` came from, so duplicates could be found later. Refused in
  [data-model.md](data-model.md), with the reasoning, so the question is answered before it is asked.

One obligation is added by the design: the e2e fixture's gallery block must be replaced with the
`A.$.parseJSON('…')` form the vendor actually serves. Under Principle IV that is not optional
tidying — the current fixture is *why* the suite passed for a whole release against a parse path that
never ran.

## Risks

| Risk | Handling |
|------|----------|
| The probe reads a document Amazon served to a robot check rather than the listing | FR-004 makes such a reading inadmissible. The probe records the title and identifier out of the fetched document and confirms they are the listing's before any count is taken. |
| ~~The two listings give different answers~~ | Did not occur — one cause, six listings. |
| "Correcting" a table that was right, hiding a live defect | The reason FR-002 requires all three numbers. A page-data count equal to the thumbnail count is only believed when the page data was read directly, not inferred from the capture agreeing with the strip. |
| The listing changes again next month | Unavoidable and the point of FR-015: every surviving figure carries the date it was read. The suite's protection is the fixture, not the listing. |
| Screenshot churn confuses the CI gate | `capture-agent.js` is not loadable from a template. Measure the diff before committing any image; do not regenerate reflexively. |
| The fix over-collects | This is the defect *as found*, so the risk is not hypothetical — it is what is being removed. The contract states both bounds precisely because a count-based check looking only for shortfalls missed a doubling for a whole release. |
| The counts drop and it reads as a regression | Every listing roughly halves. Anyone comparing against #80 §1b's old numbers will see a "loss" of exactly the duplicates. The corrected §1b must say so in the same edit, or the next pass files this feature as the bug. |
| Products already captured keep their duplicates | Nothing migrates them and nothing should ([data-model.md](data-model.md)). Recognising and removing them is the operator's, with #96's bulk deletion; quickstart §F says how. |
