# Implementation Plan: API Routes Always Answer With JSON Errors

**Branch**: `speckit/035-api-error-json` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/035-api-error-json/spec.md`

## Summary

`request.is_json` reports what a caller **sent**, not what it **accepts**. Every centralized error
handler branches on it, so a request with no body — every `DELETE`, and any parameterless `GET` —
is answered with a flash message and a 302 redirect even when the route is under `/api/`. `fetch`
follows that redirect, and the client code written to handle the failure never runs (issue #132).
Which way it then goes wrong depends on the method: a `GET` is followed successfully and its `200`
reads as success, while a `DELETE` is re-issued as `DELETE /inventory` and answered `405`, so a
delete that did exactly what was asked is reported as a failure. See [research.md](./research.md) D6
— the second case was measured during implementation and is not the one the issue predicts.

The fix replaces that predicate with one that asks about the **route** instead of the request body.
A single helper, `wants_json()`, returns true for paths under `/api/` or `/admin/api/`, *or* when
the caller sent JSON — so the set of requests receiving JSON only ever widens and no working caller
regresses. Nine call sites adopt it. The error payload itself is untouched.

On the client, the bulk-delete path in `product-attachments.js` already reads
`response.ok || response.status === 404` and becomes correct the moment the server does; the
per-tile trash handler checks `response.ok` alone and is aligned with it, so the fix does not ship
a new "Could not remove that attachment" error for an attachment that is already gone.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x (app-factory), SQLAlchemy 2.0.x — no new dependency

**Storage**: N/A — this feature reads and writes nothing

**Testing**: pytest via `nox -s tests` (unit) and `nox -s e2e` (Playwright)

**Target Platform**: Linux, home LAN, single user

**Project Type**: Server-rendered Flask web application with a JSON API consumed by its own pages

**Performance Goals**: None beyond removing one wasted follow-up request per failed `/api/` request
(SC-003)

**Constraints**: No change to the error payload shape (FR-005); no change to page-route behaviour
(FR-004); no new configuration

**Scale/Scope**: 9 changed lines in 2 source files, 1 changed line in 1 JS file, plus tests.
49 `/api/` routes and 2 `/admin/api/` routes are covered by the change; 39 page routes are
deliberately unaffected.

## Constitution Check

*GATE: passes before Phase 0, re-checked after Phase 1 — see [Post-Design Re-Check](#post-design-constitution-re-check).*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | **Pass, and the principle drove the design.** One module-level tuple and one four-line predicate, replacing an existing expression at nine sites. No decorator, no config knob, no new module, no dependency. The rejected alternatives in [research.md D1](./research.md) were rejected for being *more* machinery, not less. |
| **II. Layered Architecture Boundaries** | **Pass.** The change is confined to the error-rendering layer (`app/error_handlers.py`) and one blueprint's error handlers. No route gains logic, no service is touched, no storage call is added, and no ORM query moves. |
| **III. Exact Numerics** | **N/A.** No measurement is read, written, compared, or formatted. |
| **IV. Test Discipline Through Nox** | **Pass.** Tests run through `nox -s tests` / `nox -s e2e`. Behaviour changes land with tests (FR-007). The one new e2e test waits on observable state — attachment card counts and a recorded request list — with no fixed delays, and uses `live_server.add_test_data`-equivalent seeding via the file's existing `product` fixture rather than driving forms. No new pytest marker is needed. |
| **V. MariaDB Is the Source of Truth** | **N/A.** No schema change, so no Alembic revision. |
| **VI. Item Lifecycle and History Invariants** | **N/A.** No add/move/shorten/edit/search path is touched; JA IDs and item history are not involved. |
| **Technology Constraints — error handling** | **Pass, and this is the point.** The constitution says to use "the centralized handlers installed by `create_error_handlers(app)` rather than ad-hoc error responses. Do not add new error-handling machinery on top of them." The fix corrects those handlers in place. The rejected per-route `abort`/`jsonify` alternative would have been exactly the ad-hoc response the constitution forbids. |
| **Operating Context / Threat Model** | **Pass.** Nothing here is hardening. The change is about a client being able to tell failure from success — correctness, not defense. No auth, sanitization, or rate limiting is added. |
| **Workflow — branching** | **Pass.** Code change on `speckit/035-api-error-json`, merged by PR. |
| **Workflow — screenshots** | **Pass with a stated judgment.** `app/static/js/**` is touched, which triggers `screenshots.yml`. That workflow posts a reminder and blocks nothing (rewritten under #77 because CI font rasterization made the diff meaningless). The JS change flips a status-code branch and renders no differently, so screenshots are not regenerated. See [research.md D8](./research.md). |

**Result: no violations. The Complexity Tracking table is omitted because there is nothing to justify.**

## Design

### The predicate

Added to `app/error_handlers.py`, above `create_error_handlers`:

```
JSON_ROUTE_PREFIXES = ('/api/', '/admin/api/')

def wants_json() -> bool:
    """True when the caller parses the response rather than rendering it."""
```

Two prefixes rather than one because `app/admin/__init__.py` registers its blueprint with
`url_prefix='/admin'`, so `@bp.route('/api/materials/validate')` actually serves
`/admin/api/materials/validate` — the spec's assumption that `/api/` alone suffices was drawn from
the route decorators and is corrected in [research.md D2](./research.md). A tuple passed to
`str.startswith` rather than a substring test, because `'/api/' in path` can be satisfied by a
*variable* path segment (`/products/orders/api/12345`).

The `or request.is_json` clause is retained. The predicate is therefore a strict superset of the
current one, which is what makes "no existing caller changes" (FR-005) a property of the change
rather than a hope.

### The call sites

| File | Change |
|---|---|
| `app/error_handlers.py` | `request.is_json` → `wants_json()` at 8 sites: the `with_error_handling` decorator and the 7 handlers registered by `create_error_handlers` |
| `app/main/routes.py` | The blueprint's `404` and `500` handlers gain a `wants_json()` branch returning the same JSON shape; the HTML templates stay for page requests |
| `app/static/js/product-attachments.js` | Per-tile trash handler: `response.ok` → `response.ok || response.status === 404`, matching the bulk path 120 lines below it |

`app/main/routes.py` is in scope because Flask consults a blueprint's `500` handler before the
app's, so an unexpected error in a `main` `/api/` route currently renders `errors/500.html`
([research.md D3](./research.md)).

### What is deliberately not changed

- The payload built by `ErrorHandler.handle_error` — same fields, same values.
- Which exceptions routes raise, and where.
- Any page route's failure behaviour.
- The bulk-delete JS, which is already written correctly for a real 404.

## Project Structure

### Documentation (this feature)

```text
specs/035-api-error-json/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — design decisions D1-D8
├── data-model.md        # Phase 1 output — no entities; the error payload contract
├── quickstart.md        # Phase 1 output — how to reproduce and verify
├── contracts/
│   └── api-error-response.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
├── error_handlers.py            # CHANGED: JSON_ROUTE_PREFIXES + wants_json(); 8 call sites
├── main/
│   └── routes.py                # CHANGED: blueprint 404/500 handlers gain the JSON branch
├── product/
│   └── routes.py                # unchanged — the raise sites are already correct
├── admin/
│   └── routes.py                # unchanged — covered via the /admin/api/ prefix
└── static/js/
    └── product-attachments.js   # CHANGED: per-tile delete treats 404 as already-removed

tests/
├── unit/
│   ├── test_api_error_format.py # NEW: the predicate, and JSON errors through real routes
│   └── test_product_routes.py   # existing — checked for redirect assertions to update
└── e2e/
    └── test_product_attachments.py  # CHANGED: the stale-tile two-tab case
```

**Structure Decision**: No new module and no new package. `wants_json` lives beside the handlers
that use it, in `app/error_handlers.py`, which is already the single home for error rendering.
Putting it in `app/utils/` would separate a four-line predicate from its only callers.

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1. **Still no violations.** The design added exactly one thing not
foreseen at the gate — the `main` blueprint's `404`/`500` handlers — and it reuses the same
predicate rather than introducing a second mechanism, so the Simplicity and error-handling
assessments above are unchanged. The scope shrank in one place: [research.md D5](./research.md)
found the bulk-delete client code already written for a real 404, so FR-006 costs one line rather
than a rework.

## Risks

| Risk | Assessment |
|---|---|
| A page route relied on by a JSON caller starts returning JSON | Impossible: the predicate is a superset. A request that got JSON before still gets JSON. |
| An `/api/` route relied on the redirect | No such caller exists. Every `/api/` caller in `app/static/js/**` either parses JSON or checks the status; none reads a redirect's body. |
| A test asserts the current redirect behaviour for an `/api/` route | Checked during implementation, not assumed — `tests/` is grepped for 302 assertions against `/api/` paths and any hit is a spec-conformance fix, listed in the PR. |
| The `main` blueprint 500 handler is hard to test | Real, and accepted: `TESTING=True` sets `PROPAGATE_EXCEPTIONS`, so unhandled exceptions never reach it. It is covered by the predicate test rather than by a manufactured failing route ([research.md D7](./research.md)). |
