# Implementation Plan: Browser Capture Extension

**Branch**: `robot-army/issue-133-mcmaster-s-csp-blocks-the-capture-agent` | **Date**: 2026-09-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/048-capture-extension/spec.md`

## Summary

McMaster's `script-src` refuses the bookmarklet's subresource, so no McMaster page can be
captured by any route. The fix is the MV3 extension that feature 007 retained as its fallback
for exactly this case.

The approach is smaller than "a second codebase" suggests, because the readers are already
parameterized over a document and a URL. `capture-agent.js` moves into the extension and loses
only its trailing dispatch block, which is replaced by an entry point that **returns** the
payload instead of submitting it. The extension's service worker injects that file into an
**isolated world** — documented as exempt from the host page's content policy, which is the
whole fix — awaits the payload, and hands it to a page of the extension's own that builds the
form and POSTs it. The application's capture endpoint is untouched.

Moving the submission off the vendor page also removes the one risk the specification flagged:
nothing needs transient user activation, so the popup blocker is not in the path at all.

The bookmarklet is removed, so the project maintains one transport afterwards rather than two.

## Technical Context

**Language/Version**: JavaScript (browser, no build step, no transpilation) for the extension;
Python 3.13 / Flask 3.1.x for the application-side removals and the version assertion.

**Primary Dependencies**: None added. The extension uses only browser-provided APIs
(`chrome.scripting`, `chrome.storage`, `chrome.contextMenus`, `chrome.tabs`). No bundler, no
package manager, no `node_modules`.

**Storage**: `chrome.storage.sync` for the configured address; `chrome.storage.session` for a
payload in transit. **No database change — no table, no column, no migration.**

**Testing**: `nox -s tests` (unit) and `nox -s e2e` (Playwright). The extension-loading tests
use `launch_persistent_context` with `channel="chromium"`; every other capture test keeps the
existing shared `page` fixture.

**Target Platform**: Chrome and Chromium-derived browsers, manifest version 3. The application
continues to target Linux/containers, unchanged.

**Project Type**: Server-rendered Flask web application, plus — new with this feature — a
browser extension published as a build artifact.

**Performance Goals**: None. Capture is an interactive, occasional, single-operator action.
Reading an Amazon order takes seconds because it reads each line's listing; that is pre-existing
and is covered by showing progress (FR-007), not by making it faster.

**Constraints**: The application must be served over TLS (FR-012, retained not introduced). The
payload must stay byte-identical to the bookmarklet's (FR-003). The e2e suite must leave the
working tree clean.

**Scale/Scope**: One operator, one installation. Four recognized page kinds. One configuration
value. Roughly 158 existing e2e tests change entry point; a handful of new ones are added.

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design. Both recorded below.*

### I. Simplicity First (NON-NEGOTIABLE) — **passes, with a justification**

This is the principle the feature has to answer to, and it is answered rather than skirted.

**The problem is observed, not speculative.** A McMaster order cannot be captured by any route
that exists. The bookmarklet is refused outright by the vendor's policy, and the paste-an-address
path cannot express an order. That is a measured failure of shipped functionality — the standard
this principle sets for work of this size — and it was found by running the #80 verification
pass, not predicted.

**The alternatives were weighed by the project owner and rejected** (pasting rendered markup;
entering McMaster orders by hand). This plan does not reopen that.

**The cost is bounded, and the plan makes it binding:**

| Cost the principle polices | How it is bounded |
|---|---|
| A second codebase | The readers keep exactly one home. What is new is a manifest, an options screen, a service worker and a submit page — plumbing around an existing file, not a second copy of the part that does the work. |
| Two transports to maintain | There are not two. FR-017/FR-020 remove the bookmarklet; the count goes one → one. |
| A build step | None. No bundler, no transpiler, no `node_modules`. CI zips a directory. |
| A configuration knob | One value, and it is not speculative generality — the extension cannot work without knowing where the application is. |
| A new dependency | None added, to either side. |

**What is genuinely given up is recorded rather than hidden**: editing the reader used to require
no re-install and now requires one (FR-026), and the documentation is required to say so.

Net, the feature deletes a meaningful amount of application code (`_capture_bookmarklet()`, the
bookmarklet control, the insecure-address alert, and six assertions that existed only to test
the bookmarklet's address).

### II. Layered Architecture Boundaries — **passes, not engaged**

No service, storage or model changes. The only application-side change is removal from a route
module and a template. No ORM query moves into a route; no layer is added.

### III. Exact Numerics — **passes, not engaged**

No measurement is parsed, formatted or compared. Prices in the payload travel as they already
do, and the application's existing `price_to_cents` handling is untouched.

### IV. Test Discipline Through Nox — **passes, with one thing to watch**

Tests run through `nox`. The new e2e tests must wait on observable state, never on elapsed time
— `wait_for_timeout`, `time.sleep` and `networkidle` are prohibited, and the suite currently
executes zero fixed waits. This matters more than usual here because an extension's service
worker starts asynchronously, and "wait a moment for the worker" is exactly the wrong reflex.
Playwright exposes the worker (`context.service_workers`, and an event for it), so the condition
is observable and must be waited on that way.

New markers: none. The existing `e2e` marker covers the new tests.

**Screenshots**: `app/templates/product/capture.html` changes, so documentation screenshots must
be regenerated and committed. CI blocks merge on stale ones.

### V. MariaDB Is the Source of Truth — **passes, not engaged**

No schema change, therefore no Alembic revision. Nothing in this feature writes to the database
that was not already written by the unchanged capture endpoint.

### VI. Item Lifecycle and History Invariants — **passes, not engaged**

No add, move, shorten, edit or search path is touched. The feature changes how a capture reaches
the application, not what the application does with it.

### Operating Context and Threat Model — **passes**

Single operator, LAN, no hostile party. The extension holds one configuration value and no
credentials. The endpoint's existing CSRF exemption is retained and its justification is
unchanged — it is, if anything, narrower in spirit now, since the submitting document is the
extension's own page rather than a vendor's.

The four requested permissions are the minimum that works (research.md §8). Note that
**tightening McMaster's CSP is not the project's business** — the constitution puts CSP tuning
out of scope, and this feature works *with* the vendor's policy rather than trying to influence
it.

### Post-design re-evaluation (after Phase 1)

No gate changed. Two things the design settled are worth recording:

- Choosing the **isolated world** (research.md §1) rather than the main world keeps the fix on
  documented behavior instead of on third-party bypass reports — the conservative reading, and
  the one that does not risk reintroducing the bug.
- Moving the submission to the extension's own page (research.md §3) **removed** the feature's
  only flagged risk rather than mitigating it. That is a simplification, not an addition: the
  blank landing tab opened up front and half of `showProgress` both disappear.

One consequence is recorded honestly rather than glossed: the ~158 injected-reader e2e tests no
longer exercise the form submission, because it has moved somewhere only the extension can run
it. That divergence is one small function wide and is covered by the extension-loading tests.
The alternative — running the whole suite under a persistent context — was rejected as a larger
risk for no gain (research.md §9).

**No entries in Complexity Tracking.** The one cost that needed justifying is Principle I's, and
it is argued above rather than deferred to a table.

## Project Structure

### Documentation (this feature)

```text
specs/048-capture-extension/
├── plan.md                        # This file
├── spec.md                        # /speckit-specify output
├── research.md                    # Phase 0 — ten decisions, all unknowns closed
├── data-model.md                  # Phase 1 — browser-side entities; no DB change
├── quickstart.md                  # Phase 1 — validation, incl. the manual McMaster checks
├── contracts/
│   ├── extension-transport.md     # How a capture reaches the application
│   └── extension-surface.md       # Manifest, entry points, options, package, removals
├── checklists/
│   └── requirements.md            # Spec quality checklist
└── tasks.md                       # /speckit-tasks output — NOT created here
```

### Source Code (repository root)

```text
extension/                         # NEW — the published package, loadable unpacked as-is
├── manifest.json                  # MV3; version tracks pyproject.toml
├── background.js                  # service worker: menu registration, both entry points,
│                                  #   injection, payload hand-off
├── capture-agent.js               # MOVED from app/static/js/ — readers unchanged;
│                                  #   trailing dispatch IIFE replaced by an entry point
├── submit.html / submit.js        # builds the form and POSTs, in its own tab
├── options.html / options.js      # the one configuration value
└── icons/

app/
├── product/routes.py              # REMOVE _capture_bookmarklet()
├── templates/product/capture.html # REMOVE bookmarklet control + insecure-address alert;
│                                  #   ADD pointer to the extension
└── static/js/capture-agent.js     # DELETED (moved to extension/)

docs/
└── capture-extension.md           # NEW — install, configure, use, update (FR-025)

tests/
├── unit/
│   ├── test_proxy_headers.py      # REMOVE 4 bookmarklet-address assertions
│   └── test_extension_manifest.py # NEW — manifest version == pyproject version
└── e2e/
    ├── test_product_page_capture.py  # run_bookmarklet() -> injected-reader driver
    ├── test_order_capture.py         # REMOVE 2 bookmarklet-href assertions
    └── test_capture_extension.py     # NEW — loads the packed extension for real

.github/workflows/
├── test.yml                       # ADD extension-package job (mirrors docker-build)
└── release.yml                    # ADD the zip to the existing release step
```

**Structure Decision**: the extension is a **sibling top-level directory**, not a subdirectory of
`app/`, because it is not served by Flask and is not part of the Python package. It is loadable
unpacked exactly as it sits in the repository — no build, no copy, no generated file — which is
what keeps `capture-agent.js` to one home and makes the development loop "edit, press reload".

`app/static/js/capture-agent.js` is deleted rather than kept in both places. Nothing loads it
over HTTP once the bookmarklet is gone, and two copies of the readers is the specific cost
Principle I is being asked to accept — so it is not paid.

## Complexity Tracking

> No entries. The single cost requiring justification is Principle I's, argued in the
> Constitution Check above. Nothing else in this design exceeds the problem.
