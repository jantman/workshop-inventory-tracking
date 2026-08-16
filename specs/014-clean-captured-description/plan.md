# Implementation Plan: Clean Captured Description

**Branch**: `issues/91` | **Date**: 2026-08-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/014-clean-captured-description/spec.md`

## Summary

Capture stores a listing's description and its product-information rows as text read straight off the page. The one helper that reads that text — `textOf()` in `app/static/js/capture-agent.js` — does two things wrong: it reads the text of inline stylesheets and script blocks along with the prose, and it collapses every run of whitespace to a single space, so the page's paragraphs, breaks and list items leave no trace.

The whole feature is one helper, split in two, in one file:

- **`proseOf(node)`** — a recursive walk of a *clone* of the node with non-content elements removed, emitting a single newline for an explicit line break and a paragraph break at each block boundary, then normalized so no more than one blank line survives. New.
- **`textOf(node)`** — `proseOf(node)` with all whitespace collapsed back to single spaces. Same contract as today, so the title, brand, price and specification names keep behaving exactly as they do now.

The description and specification *values* switch to `proseOf`; everything else stays on `textOf` and inherits only the stripping. No Python changes, no schema change, no migration, no new dependency.

Three findings shaped the plan and are worth stating up front:

1. **`innerText` is not available here.** `canonicalDocument()` reads the listing through `DOMParser`, producing a detached document with no layout. `innerText` returns `''` on such a node. The explicit walk is not a stylistic preference — it is the only thing that works on the document capture actually reads.
2. **The display half of the feature already exists.** `product/detail.html:106` carries `white-space: pre-wrap`, `product/_form_fields.html:59` already renders a textarea for any value containing a newline, and `tests/e2e/test_product_specifications.py` already tests both against a multi-line value. FR-011 and FR-012 need a test that ties them to a *captured* description, not new code.
3. **Re-capture will not overwrite the three contaminated products.** `CatalogService.merge_specifications` is "already present wins", so re-capturing `B0DMNXC4CD` onto its existing product keeps the contaminated `Description`. That is the correct rule and this feature does not change it — but it makes the verification procedure a two-step, and `quickstart.md` says so.

## Technical Context

**Language/Version**: JavaScript (ES5-compatible, no build step, no modules) for `app/static/js/capture-agent.js`. Python 3.13 / Flask 3.1.x for everything else — unchanged by this feature.

**Primary Dependencies**: None new. Browser DOM only (`cloneNode`, `querySelectorAll`, `Node.TEXT_NODE`, `nodeName`). Explicitly *not* an HTML sanitizer, a Markdown converter, or `innerText`.

**Storage**: MariaDB, existing `product_specifications` table. **No schema change and no Alembic revision** — the widening that made "kept in full" possible has already shipped, and this feature only reduces what is written into it. `_payload_string` and `_clean` both `.strip()` and nothing more, so newlines survive the Python path untouched.

**Testing**: `nox -s tests` (unit; nothing here touches Python, so this is a regression gate only) and `nox -s e2e` (Playwright, fixture-driven). The capture agent has no unit-test seam — it is a self-executing IIFE with no exports, driven only through the real capture flow — so every extraction requirement is proved by asserting on the `listing` payload JSON that lands in the confirmation form's hidden field, which is the technique `test_the_rich_description_is_kept_and_its_furniture_is_not` already uses.

**Target Platform**: Chromium, running the agent inside the vendor's page on the operator's desktop.

**Project Type**: Server-rendered Flask application with one standalone browser-side script. This feature is almost entirely inside that script.

**Performance Goals**: None. A description block is a few hundred nodes walked once per capture. Do not add memoization, batching, or an incremental walk — Principle I forbids optimization without a measurement, and there is none.

**Constraints**:
- The walk MUST work on a detached `DOMParser` document (no layout, no `innerText`, no `naturalWidth`).
- The walk MUST NOT mutate the live page — `canonicalDocument()` falls back to `document` itself, so stripping in place would edit the page the operator is looking at (FR-003).
- Nothing may throw (FR-015). The agent has no error boundary; a throw costs the entire capture.
- `descriptionImages()` MUST keep reading the **original** block, not the stripped clone: `knownEdges()` consults `img.naturalWidth`, which is 0 on a detached clone.

**Scale/Scope**: One JavaScript file, one e2e test file, one e2e fixture. Six sampled listings, three affected products, one affected specification row.

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1. Both passes below.*

| Principle | Verdict | Notes |
|---|---|---|
| **I. Simplicity First** | PASS | No new dependency; the issue's own constraint ("no HTML sanitizer dependency, no Markdown conversion") and Principle I agree. One walker of roughly 40 lines replaces a one-line regex in the file that already owns the problem. No configuration knob for which tags count as block boundaries — a single module-level list, read once. |
| **II. Layered Architecture Boundaries** | PASS | No Python layer is touched. The browser/server boundary already exists and is documented in `specs/007-product-page-capture/contracts/capture-payload.md`; the payload *schema* is unchanged, only the content of two string fields. |
| **III. Exact Numerics** | N/A → PASS | No measured quantity is computed. `priceFrom()` keeps returning a string and is untouched; `textOf()` keeps its single-line contract precisely so the price and brand parsers cannot see a newline. |
| **IV. Test Discipline Through Nox** | PASS (with obligations) | Run through `nox -s tests` and `nox -s e2e`, never bare `pytest`. New e2e tests wait on observable state only — no `wait_for_timeout`, no `networkidle`. The payload read is a snapshot (`input_value()`), so the landed page must be established with an `expect()` first; see the waiting notes in `quickstart.md`. No new pytest marker is needed. |
| **V. MariaDB Is the Source of Truth** | PASS | No schema change, no migration, no `create_all`. |
| **VI. Item Lifecycle and History Invariants** | N/A | Products and specifications, not inventory items. No JA ID, active-row, or history path is touched. |
| **Operating Context / Threat Model** | PASS | Removing scripts and stylesheets from *extracted text* is a correctness measure — that text is stored and displayed as prose. It is explicitly **not** a sanitization layer against hostile input, and no escaping, allow-listing, or CSP work is in scope. Jinja already escapes what it renders. |
| **Technology Constraints** | PASS | No frontend framework, no build step, no module system. The agent stays a plain script the loader appends. Type hints are a Python rule and no Python signature changes. |
| **Workflow / Quality Gates** | PASS (with obligation) | Feature branch `issues/91` + PR. The Screenshot Reminder workflow will fire because `app/static/js/**` is in its path filter — it is informational (issue #77) and the honest judgment is recorded in "Screenshots" below. |

**No entries in Complexity Tracking.** Nothing in this plan requires a justified exception.

### Screenshots

`.github/workflows/screenshots.yml` posts a reminder on any PR touching `app/static/js/**`, which this PR does. It does not block, and it explicitly leaves the judgment to the author. The judgment here: `capture-agent.js` runs inside the *vendor's* page and appears in no documentation screenshot, so regeneration is not warranted **provided no template changes**. If the implementation ends up touching `app/templates/product/detail.html` or `_form_fields.html` — the plan says it should not, because both already satisfy FR-011 and FR-012 — then `nox -s screenshots` must be run and the PNGs committed alongside. Remember that `nox -s e2e` must leave the working tree clean; if it does not, screenshots were rewritten and must be reverted.

## Project Structure

### Documentation (this feature)

```text
specs/014-clean-captured-description/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── text-extraction.md
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit-tasks output — NOT created here
```

### Source Code (repository root)

```text
app/
├── static/js/
│   └── capture-agent.js            # the whole implementation
└── templates/product/
    ├── detail.html                 # UNCHANGED — line 106 already has white-space: pre-wrap
    └── _form_fields.html           # UNCHANGED — line 59 already switches to a textarea

tests/e2e/
├── fixtures/
│   └── amazon_listing_aplus.html   # grows real-shaped A+ markup
├── test_product_page_capture.py    # new and extended assertions
└── test_product_specifications.py  # UNCHANGED — already covers FR-011 and FR-012
```

**Structure Decision**: No new files. The implementation is confined to `app/static/js/capture-agent.js`, the "Reading the page" section of it, and the fixture and test that already exercise the A+ description path. Adding a JavaScript test runner to unit-test the walker in isolation was considered and rejected — it is a build step and a dependency, both of which the Technology Constraints section makes a constitutional amendment rather than a design choice. `research.md` records what that costs.

## Phase 0 — Research

See [research.md](./research.md). Seven decisions, all resolved; no `NEEDS CLARIFICATION` remains.

Headline decisions:

- **Walk a clone, not the node.** `cloneNode(true)`, remove the non-content elements from the clone, walk the clone. Protects the live page (FR-003) and keeps `descriptionImages()` reading the original.
- **Explicit recursive walk, not `innerText`.** `innerText` needs layout; the document capture reads is detached. This is decisive, not preferential.
- **One walker, two wrappers.** `proseOf` for the description and specification values; `textOf` = `proseOf` collapsed, for title, brand, price and specification names. FR-001 reaches every caller through one implementation; FR-005 to FR-008 reach only the two that should have them (FR-009).
- **Normalize in a fixed four-step order** — collapse spaces and tabs but not newlines, trim each line, fold 3+ newlines to 2, trim the whole. Order matters and is specified in the contract.
- **Rewrite the detail-bullet value extraction to remove the bold node from the clone** instead of slicing by the name's character length. The existing arithmetic silently breaks the moment either side can contain a newline; removing the node is both shorter and correct.
- **`<li>` produces a paragraph break, not a single newline** — the issue prescribes it, and FR-006 names list items among the block boundaries. Recorded with the alternative, because it makes bullet lists read loose and is a one-line change if the owner dislikes it once they see it.
- **The optional live-markup review** (driving the owner's Chrome against `B0DMNXC4CD`) is a fixture-fidelity step, not a prerequisite. The prescription is already in the issue; looking at a real A+ block only tells us whether the fixture is shaped like the real thing.

## Phase 1 — Design & Contracts

- **[data-model.md](./data-model.md)** — no persisted-schema change; documents the three in-flight shapes (the extracted description, a specification row, the walker's intermediate parts list) and the exact invariants each must satisfy.
- **[contracts/text-extraction.md](./contracts/text-extraction.md)** — the contract for `proseOf`/`textOf`: inputs, guarantees, the boundary-tag set, the normalization order, and a worked input/output table that doubles as the test table.
- **[quickstart.md](./quickstart.md)** — how to run it, what the automated tests prove, and the manual verification against the six real listings, including the two-step needed because merge is "already present wins".

### Constitution re-check after design

Re-evaluated against the artifacts above: unchanged, all PASS. The design added no dependency, no layer, no schema object, no configuration surface, and no Python. The only thing it added beyond the minimum is the detail-bullet rewrite, which removes code rather than adding it.

## What is deliberately not in this plan

- No back-fill or cleanup migration for the three contaminated products (spec Assumptions; Principle I).
- No stripping of hidden-but-present A+ copy (spec Assumptions).
- No change to which images are captured, to the size filter, or to `withoutTransform`.
- No change to `merge_specifications`' "already present wins" rule.
- Nothing from the rest of the #80 verification pass — the "About this item" section, the manufacturer-part-number default, bulk image deletion, the UPC identifier, the per-pack price calculator, or the reverse-proxy warning. Each is listed under Out of Scope in the spec and belongs to its own issue.
