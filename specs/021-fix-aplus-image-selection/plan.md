# Implementation Plan: A+ Description Images — Keep the Product's, Drop the Vendor's

**Branch**: `issues/94` | **Date**: 2026-08-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/021-fix-aplus-image-selection/spec.md`

## Summary

`B0FX4PDW6M` carries **two elements with `id="aplus"`**. The first in document order is inside
`#aplusBrandStory_feature_div` — the vendor's "From the brand" carousel, 126 images of other
products. `descriptionBlock()` calls `doc.querySelector('#aplus')`, gets that one, returns, and
never reaches `#aplus_feature_div`, where the product's real description and its 1464×600
specification JPEG live.

That single line is both halves of issue #94. The cross-sells are not slipping past the 300-pixel
filter — they *are* the block being read. The spec table is not being rejected — its container is
never opened. Simulated against the real fetched document: **61 description images today, 7 after**,
with no real image lost on any of the three probed listings.

None of the issue's three candidate causes is load-bearing. Lazy loading is present but every lazy
image has a `<noscript>` twin carrying a plain `src`; no A+ image has `width`/`height` attributes at
all. See [research.md](research.md) for all of it.

The fix is in `descriptionImages()` and `descriptionBlock()` in `app/static/js/capture-agent.js`:
gather every description container instead of the first, exclude the brand-story subtree, and
prefer `data-src` over a placeholder address. No Python change, no schema change, no migration, no
new dependency, and `knownEdges()` / `MIN_DESCRIPTION_EDGE` / `withoutTransform()` are not touched.

**The probe amended the spec in three places** (FR-011, FR-013/SC-004/SC-005, and the
description-text assumption). The short version: description **text** is in scope after all,
because it is read from the same block, and `B0FX4PDW6M`'s captured description today is the
vendor's company bio rather than the product's description. [research.md](research.md) §7 records
each correction against the observation that forced it.

## Technical Context

**Language/Version**: ES5-compatible browser JavaScript (`capture-agent.js` runs unbundled and
untranspiled on a vendor's page). Python 3.13 for the test suite only — no Python is edited.

**Primary Dependencies**: None added. The agent depends on nothing but the DOM; tests use
Playwright, already present.

**Storage**: MariaDB. **No schema change and no Alembic revision** — see
[data-model.md](data-model.md).

**Testing**: `nox -s tests` (no new coverage expected — this is browser-side code) and `nox -s e2e`,
where all of this feature's coverage lands, against `tests/e2e/fixtures/amazon_listing_aplus.html`.
The e2e session needs a ≥15-minute bash timeout and must be run detached (it outruns the 10-minute
cap).

**Target Platform**: Chrome on the operator's LAN workstation reading amazon.com; Flask app on the
same LAN.

**Project Type**: Server-rendered Flask web application with a single injected client-side script.

**Performance Goals**: None, and one incidental improvement worth naming: `B0FX4PDW6M` drops from
61 description images to 7, so the capture stops fetching and storing ~54 images the operator then
deletes. That is a correctness fix that happens to be faster; it is not an optimization and
Principle I's measurement rule is not engaged.

**Constraints**: The reader runs against a detached `DOMParser` document with no layout and no
stylesheets (`canonicalDocument()`), so `offsetHeight`, `getComputedStyle` and `naturalWidth` are
all unavailable or zero. Every decision must be structural. The reader must not be able to throw — a
selector that stops matching must cost images, never the capture.

**Scale/Scope**: Two functions edited, one added, one fixture extended, roughly five new e2e
assertions. Single user, LAN-only.

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design. Both passes below.*

| Principle | Verdict | Note |
|-----------|---------|------|
| **I. Simplicity First** | **PASS** | Three named things: gather all containers, skip one subtree, prefer `data-src`. No abstraction, no configuration, no "image classifier". Declined explicitly: extending `knownEdges()` to parse the double-underscore token (research §4 — it would establish 1464×600, which changes no outcome); a general visibility test (not implementable on a detached document, and 020 already killed it once); a server-side second implementation of the filter. |
| **II. Layered Architecture Boundaries** | **PASS** | Nothing crosses a layer. No route, service, storage or model file is touched. The change sits entirely on the vendor side of the payload boundary, whose contract is unchanged. |
| **III. Exact Numerics** | **PASS (N/A)** | No measured quantity is parsed or computed. Pixel edges are integers compared against an integer, as they already were. |
| **IV. Test Discipline Through Nox** | **PASS, with obligations** | All coverage through `nox -s e2e`, ≥15-minute timeout, run detached. No new pytest marker. Every new wait on observable state: the existing `capture_from_listing` helper establishes the landing page, and the payload assertions read a server-rendered region — no `count()` may precede the `expect()` that establishes it. The attachment-count assertion is pattern C (render-implies-completion): `expect(cards).to_have_count(n)`. |
| **V. MariaDB Is the Source of Truth** | **PASS** | No schema change, so no migration. Stated in data-model.md so "where do the images live" cannot be answered by inventing a column. |
| **VI. Item Lifecycle and History Invariants** | **PASS (N/A)** | Inventory items untouched. This is the product catalog. |
| **Operating Context** | **PASS** | No sanitization layer. The brand story is excluded because it is the wrong product, not because a vendor is hostile. The placeholder is rejected because it is not a picture, not because it is dangerous. |
| **Workflow: branch and PR** | **Required** | Non-trivial code change → feature branch `issues/94`, merged via PR. |
| **Workflow: screenshots** | **Triggered, expected no-op** | `app/static/js/**` is touched. `capture-agent.js` is never loaded by an application template, so no screenshot can depend on it; run `nox -s screenshots_verify` to establish that rather than assert it, and measure any diff before committing an image. |

**Post-Phase-1 re-check**: unchanged, with one addition to record. Phase 1 moved the brand-story
exclusion from `descriptionImages()` into a shared `isCrossSell()` predicate applied at both the
block-selection and the per-image step. That is one small function used twice rather than the same
condition written twice, and it is what makes FR-006 ("excluding the region must not exclude the
block") checkable in one place. No entity, interface or dependency was added.

**Complexity Tracking**: not applicable. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/021-fix-aplus-image-selection/
├── spec.md                      # /speckit-specify output, amended after the probe
├── plan.md                      # This file
├── research.md                  # Phase 0 — the live probe; the cause, and three corrections
├── data-model.md                # Phase 1 — no schema change, and why that is the point
├── quickstart.md                # Phase 1 — how to validate, including the real-listing check
├── contracts/
│   ├── listing-payload.md       # The payload boundary; version stays 1
│   └── description-reader.md    # The reader's obligations after this change
├── checklists/
│   └── requirements.md          # Spec quality checklist
└── tasks.md                     # /speckit-tasks output — NOT created by /speckit-plan
```

### Source code (repository root)

```text
app/
└── static/js/
    └── capture-agent.js         # THE ONLY PRODUCTION FILE THIS FEATURE CHANGES
                                 #   + CROSS_SELL_CONTAINER / isCrossSell()
                                 #   + PLACEHOLDER_ADDRESS / addressOf()
                                 #   ~ descriptionBlock()  -> descriptionBlocks(), returns all
                                 #   ~ descriptionImages()  reads a list, skips cross-sells
                                 #   ~ the call site in the extractor: text from the first
                                 #     non-cross-sell block, images from all of them

tests/e2e/
├── fixtures/
│   └── amazon_listing_aplus.html  # + a brand-story region with its own duplicate id="aplus",
│                                  #   placed FIRST; the real block wrapped in #aplus_feature_div;
│                                  #   a lazy image + its <noscript> twin; a real transform token
└── test_product_page_capture.py   # ~ the A+ image test; + the cross-sell and placeholder cases
```

**Structure Decision**: no new module, package or directory. Everything stays in
`capture-agent.js` beside the functions it changes, because "which block is the description" is one
question and splitting it across files would make the answer harder to find, not easier.

## Approach

### 1. `descriptionBlocks(doc)` replaces `descriptionBlock(doc)`

Returns an **array** of every container in `DESCRIPTION_CONTAINERS` that has text and is not a
cross-sell region, in document order, `querySelectorAll` rather than `querySelector` so the second
`#aplus` is reachable. `DESCRIPTION_CONTAINERS` itself is unchanged — `#aplus_feature_div` was
always in it; it was simply unreachable.

Duplicate work is expected and harmless: on `B09GM8FB3X` and `B0DMNXC4CD` the `#aplus` match is a
descendant of the `#aplus_feature_div` match, so the same images are seen twice. The existing
`seen` map in the extractor already deduplicates by address, and FR-018's content-level
deduplication catches the rest on the server.

### 2. `isCrossSell(node)` — one predicate, two call sites

`node.closest('#aplusBrandStory_feature_div')`. Applied when selecting blocks (so the brand story's
prose never becomes `description_text`) **and** per image inside `descriptionImages()` (so a future
listing that nests the carousel inside the real description block is still handled). Two call sites
is not duplication — they answer different questions, and FR-006 requires the second one to be
narrower than the first.

`closest()` is available on the detached document's elements; it is already used elsewhere in the
file's neighbourhood of DOM work.

### 3. `addressOf(img)` — the real address, or nothing

`data-src` if present, else `src`; then reject anything matching the known placeholder addresses
(`grey-pixel`, `transparent-pixel` under `images/G/01/x-locale/common/`). Everything downstream —
the `/^https?:/` test, `knownEdges()`, `withoutTransform()` — runs on that one address instead of
on `getAttribute('src')`.

This is what stops the 1×1 grey GIF that every A+ listing with lazy images is storing today
(research §2). It is a bug the issue did not report and the probe found.

### 4. The call site

Text from the **first** non-cross-sell block (preserving 007 FR-005's "whichever form it takes, do
not require both"); images from **all** of them (FR-003). The two differ deliberately: merging
description prose across nested containers would duplicate it, whereas merging images is what the
`seen` map is for.

### 5. The fixture

Extended as research §8 sets out — a `#aplusBrandStory_feature_div` holding its own `<div
id="aplus">` **placed before** the real block, the real block wrapped in `#aplus_feature_div`, a
lazy image with its `<noscript>` twin, and a real double-underscore transform token. The existing
furniture images stay untouched: they are the proof that the 300-pixel rule still works after the
block selection changes.

The ordering matters more than anything else in the fixture. A brand story placed *after* the real
block cannot reproduce the defect, and a fixture that cannot fail is what shipped this bug.

## What is not built

- No change to `knownEdges()`, `MIN_DESCRIPTION_EDGE` or `withoutTransform()` (research §4).
- No image classifier, heuristic or scoring. Position decides; size already decides the rest.
- No server-side filtering. 007 put this in the browser deliberately and the reasoning still holds.
- No handling of `data-a-hires` or `srcset`: **neither appears on any probed A+ image.** Adding
  them would be speculative generality under Principle I. Recorded here so the omission reads as a
  decision rather than an oversight.
- No `aplus3p_feature_div` handling — the issue guessed at it; it is not present.
- No gallery change of any kind (#95 owns that).

## Risks

| Risk | Bound |
|------|-------|
| Amazon renames `#aplusBrandStory_feature_div` | Degrades to today's behavior on the over-capture side only — some cross-sells to delete. The under-capture fix does not depend on the name. Stated rather than mitigated, as 007 and 020 did for the same class of risk. |
| Amazon stops emitting `<noscript>` twins | Already covered: `addressOf()` prefers `data-src`, so the real address survives the twins going away. This is the reason to implement it despite the twins making it redundant today. |
| Merging containers double-counts on some other nesting | Bounded by the `seen` map and by FR-018's content-level deduplication. Worst case is wasted fetches, not wrong data. |
| A listing whose *only* A+ content is a brand story captures no description | Correct per spec Edge Cases. The gallery and product-information rows are unaffected; the capture still succeeds. |
| The three pre-#91 assertions get loosened rather than updated | Called out in quickstart §2. They are #91's "nothing else moved" guard; the specification-name list and the title/brand/price values must not change in this feature. |
| Screenshot churn confuses the gate | `capture-agent.js` is not loadable from a template. Measure the diff before committing any image; do not regenerate reflexively. |
