---
description: "Task list for feature 035: API Routes Always Answer With JSON Errors"
---

# Tasks: API Routes Always Answer With JSON Errors

**Input**: Design documents from `/specs/035-api-error-json/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api-error-response.md](./contracts/api-error-response.md), [quickstart.md](./quickstart.md)

**Tests**: **Required.** FR-007 asks for them by name, and the constitution's Principle IV says a
change that alters behaviour lands with tests covering that behaviour. They are not optional here.

**Organization**: Grouped by user story. The predicate is foundational and blocks everything; after
it, US1 and US2 touch disjoint handlers and can proceed independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 / US2 / US3, mapping to the user stories in [spec.md](./spec.md)

## Path Conventions

Flask application at the repository root: `app/` for source, `tests/unit/` and `tests/e2e/` for
tests. Paths below are repository-relative and exact.

**Before running anything**: use the virtualenv by path (`venv/bin/...`, never `source
venv/bin/activate`), and prefix `nox` invocations with
`PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`.

---

## Phase 1: Setup (Baseline & Blast Radius)

**Purpose**: Record what the behaviour is now, so "changed" and "unchanged" are both provable, and
find anything in the test suite that encodes the current behaviour.

- [X] T001 Record the pre-fix baseline: run the reproduction script from [quickstart.md](./quickstart.md) §1 and save its six output lines to compare against after the change. Expect `302` on lines 1, 3, 4 and 5, `404 application/json` on line 2, and `302 /inventory` on line 6.
- [X] T002 [P] Find tests that encode the current redirect behaviour: `grep -rn "302\|assert_redirect\|follow_redirects" tests/ | grep -i "api"` and read each hit. Any test asserting a redirect from an `/api/` or `/admin/api/` path is asserting the bug and must be updated in the phase that changes that handler — list them in the PR description rather than silently rewriting them.

**Checkpoint**: The baseline is on record and the set of tests needing updates is known.

---

## Phase 2: Foundational (Blocking Prerequisite)

**Purpose**: The single predicate every handler will use. Nothing else can proceed without it.

**⚠️ CRITICAL**: T003 blocks every task in Phases 3, 4 and 5.

- [X] T003 Add `JSON_ROUTE_PREFIXES = ('/api/', '/admin/api/')` and `def wants_json() -> bool` to `app/error_handlers.py`, placed above `with_error_handling` so both it and `create_error_handlers` can use it. Body: `return request.path.startswith(JSON_ROUTE_PREFIXES) or request.is_json`. Type-hinted per the constitution's typing rule. Carry a comment naming the reason: `request.is_json` reports what the caller *sent*, and a bodyless request to a machine-facing route is not a page request — see [research.md](./research.md) D1. Both prefixes are required because the admin blueprint carries `url_prefix='/admin'` (D2); use a tuple with `startswith`, not `'/api/' in path`, which a variable path segment can satisfy.
- [X] T004 Create `tests/unit/test_api_error_format.py` with the predicate's path matrix, using `app.test_request_context(path=...)` over the `app` fixture from `tests/conftest.py`: `/api/products/1` → True; `/admin/api/materials/validate` → True; `/products/1` → False; `/products/orders/api/12345` → **False** (the substring trap from D2); `/products/1` with `content_type='application/json'` → True (the retained `or request.is_json` clause). This is the test that carries the whole change — the branch is character-identical at every call site.

**Checkpoint**: `venv/bin/nox -s tests` passes. `wants_json()` exists and is correct, and no handler uses it yet, so behaviour is unchanged.

---

## Phase 3: User Story 1 — A failed API operation is reported as a failure (Priority: P1) 🎯 MVP

**Goal**: The attachments grid stops reporting failures as successes. A delete of an
already-deleted attachment returns a real 404 that the client recognises, and a delete that fails
for any other reason is reported to the user instead of vanishing into a page reload.

**Independent Test**: Delete an attachment, then delete it again. The second request answers `404
application/json` with no `Location` header and fetches no page. In the browser, deleting a
selection containing a stale tile empties the grid with no alert and issues no request to
`/inventory`.

**Why this is the MVP**: It is the case issue #132 was found in and the only one with a
user-visible consequence. It needs exactly one of the seven handlers, so it ships without waiting
for US2.

### Implementation for User Story 1

- [X] T005 [US1] In `app/error_handlers.py`, change `handle_item_not_found` (the `ItemNotFoundError` handler, ~line 311) from `if request.is_json:` to `if wants_json():`. This is the handler both endpoints named in issue #132 reach, plus `_product_or_404`.
- [X] T006 [P] [US1] In `app/static/js/product-attachments.js`, the per-tile trash handler (~line 100) currently reads `if (response.ok)`. Change it to `if (response.ok || response.status === 404)`, matching `deleteSelection` ~120 lines below, and carry the same reasoning in a comment. **This is not optional polish**: without it, T005 introduces a *new* "Could not remove that attachment" error on a stale tile where today the page silently reloads — see [research.md](./research.md) D5. The bulk-delete path needs no change; it is already written for a real 404.

### Tests for User Story 1

- [X] T007 [US1] In `tests/unit/test_api_error_format.py`, add route-level tests for the three endpoints that reach `ItemNotFoundError` with **no request body**: `GET /api/products/999999`, `DELETE /api/attachments/999999`, `DELETE /api/products/1/identifiers/999999`. Each asserts status `404`, `Content-Type` is `application/json`, `success` is `false`, and — the assertion that actually encodes the bug — that the response carries **no `Location` header**. Use the `client` fixture from `tests/conftest.py`; note that `create_app(TestConfig)` with no `storage_backend` cannot reach these handlers at all (D9).
- [X] T008 [US1] Add an e2e test to `tests/e2e/test_product_attachments.py` for the stale-tile bulk delete — the two-tab case from issue #132's inherited checklist. Seed three attachments with the existing `open_with_attachments` helper; delete one out from under the grid with `page.evaluate` issuing a real `csrfFetch` DELETE (a genuine delete, not a `page.route` stub — stubbing would fake the very response under test); then tick all three and press Delete Selected. Use the file's `record_dialogs` helper for the confirm. Assert the grid empties (`expect(page.locator(CARDS)).to_have_count(0)`) and, **after** that establishes the reload landed, that no alert rendered (`expect(page.locator("#attachment-alert")).to_have_count(0)`) — a negative assertion made before the region settles would pass against an unloaded page.
- [X] T009 [US1] In the same e2e test, record requests with `page.on("request", ...)` and assert **no request to `/inventory`** was issued (SC-003). This is what separates "passes for the right reason" from today's accidental pass: a followed 302 is exactly what a `/inventory` request would mean. The successful reload navigates to `/products/<id>`, so `/inventory` cannot appear for any legitimate reason.
- [X] T010 [US1] Add an e2e test that the **per-tile** trash button on a stale tile reloads the grid rather than showing "Could not remove that attachment" — the regression T006 exists to prevent. Same seeding, delete one out from under the page, then click that tile's `.delete-attachment-btn`.

**Checkpoint**: `nox -s tests` and `tests/e2e/test_product_attachments.py` pass. The attachments grid is fixed and shippable. Lines 1, 3 and 4 of the T001 baseline now read `404 application/json`; lines 2, 5 and 6 are unchanged.

---

## Phase 4: User Story 2 — Every API route reports errors the same way (Priority: P2)

**Goal**: The remaining six handlers stop discriminating on the request body, so the next `/api/`
route to raise an error is correct without anyone remembering this issue.

**Independent Test**: An unrouted `/api/` path answers `404 application/json` instead of redirecting
to `/index`. The predicate matrix from T004 covers the branch in the handlers that cannot be reached
without mocking a service into failure.

### Implementation for User Story 2

- [X] T011 [US2] In `app/error_handlers.py`, change the remaining `request.is_json` occurrences to `wants_json()`: `handle_validation_error` (~293), `handle_storage_error` (~302), `handle_auth_error` (~320), `handle_config_error` (~329), `handle_internal_error` (~338), `handle_not_found` (~346), and the `with_error_handling` decorator (~161, where it reads `if return_json or request.is_json:`). Seven edits, all mechanical. Afterwards `grep -n "request.is_json" app/error_handlers.py` must return nothing.
- [X] T012 [P] [US2] In `app/main/routes.py`, give the blueprint's `@bp.errorhandler(404)` and `@bp.errorhandler(500)` (~3246-3253) a `wants_json()` branch returning the same JSON shape the app-level handlers return, keeping `render_template('errors/404.html')` / `errors/500.html` for page requests. Flask consults a blueprint's handler before the app's, so without this an unexpected error in a `main` `/api/` route renders an HTML error page — see [research.md](./research.md) D3. Note in a comment that the 404 branch is currently unreachable (`grep -rn "abort(" app/` returns nothing) and is changed for consistency, not because a caller hits it.

### Tests for User Story 2

- [X] T013 [US2] In `tests/unit/test_api_error_format.py`, assert `GET /api/no-such-route` returns `404` with `Content-Type: application/json` and no `Location` header. Baseline was `302 /index` (D9).
- [X] T014 [US2] In `tests/unit/test_api_error_format.py`, assert the payload shape is unchanged (FR-005): a JSON error from an `/api/` route carries `success`, `error_id`, `error_code`, `error_type`, `message`, `details` and `recovery_suggestions`, exactly as [data-model.md](./data-model.md) records. Compare a bodyless request against the same request with `content_type='application/json'` — the two bodies must agree on every field except `error_id`, which is a timestamp.

**Note on coverage**: the `StorageError`, `AuthenticationError`, `ConfigurationError` and `500`
handlers are deliberately **not** tested through routes. No `/api/` route raises them without
mocking a service into failure, `TESTING=True` sets `PROPAGATE_EXCEPTIONS` so the 500 handler never
runs under test anyway, and the branch is character-identical in all seven handlers and covered by
T004. Manufacturing a failing route per handler would be test machinery in service of a coverage
number the constitution explicitly declines to chase (D7).

**Checkpoint**: All five API lines of the T001 baseline read `404 application/json`. Line 6 is
still `302 /inventory`.

---

## Phase 5: User Story 3 — Browser pages keep their existing error behaviour (Priority: P3)

**Goal**: Prove the half of the contract that must **not** change. No source change belongs in this
phase — the predicate preserves page behaviour by construction, because it is a strict superset of
`request.is_json`. This phase turns "by construction" into "by test".

**Independent Test**: A page route failing a lookup still answers `302` to the inventory list with a
flash message.

- [X] T015 [US3] In `tests/unit/test_api_error_format.py`, assert `GET /products/999999` still returns `302` with `Location` ending in `/inventory` — the page-route control from the T001 baseline. A `404` here is a regression against FR-004.
- [X] T016 [US3] In `tests/unit/test_api_error_format.py`, assert a page route requested **with** a JSON content type still receives JSON, proving the `or request.is_json` clause survived and no existing JSON caller of a page route regressed.

**Checkpoint**: All three stories are covered. The full contract in [contracts/api-error-response.md](./contracts/api-error-response.md) is asserted in both directions.

---

## Phase 6: Polish & Verification

- [X] T017 Re-run the [quickstart.md](./quickstart.md) §1 script and diff against the T001 baseline. Expected: lines 1, 3, 4, 5 changed from `302` to `404 application/json`; lines 2 and 6 byte-identical.
- [X] T018 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests`. Must be green, and still sub-second.
- [X] T019 Run the full e2e suite **detached**: `nohup env PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &`, then poll. It takes ~13m 45s warm and does not fit inside a 10-minute foreground tool timeout — a foreground run reports a false timeout on a passing suite. Budget 20 minutes cold.
- [X] T020 Confirm `git status` is clean after the e2e run — a test session must not modify tracked files (constitution IV). In particular no screenshot under `docs/images/screenshots/` may have changed.
- [X] T021 Update any test found in T002 that asserted a redirect from an `/api/` path. **None existed** -- all 14 `== 302` assertions in the suite are page-route form posts (`/inventory/add`, `/inventory/edit`, `/purchases/<id>/delete`, `/products/<code>`), so no existing test encoded the bug and none needed changing.
- [ ] T022 Open the PR against `main` from `speckit/035-api-error-json`. `screenshots.yml` will post its reminder comment because `app/static/js/**` was touched; answer it in the PR rather than regenerating — that workflow blocks nothing and was reduced to a reminder under #77, and this change flips a status-code branch without altering a rendered pixel ([research.md](./research.md) D8).
- [ ] T023 Do the by-hand two-tab check from [quickstart.md](./quickstart.md) §3, which issue #132 carries as an inherited verification item from #80, and tick that checkbox on the issue. The automated tests cover it, but the issue asks for it by hand and the point is to see the `404` in the network panel rather than a `302` followed by `GET /inventory`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: needs nothing from Phase 1 to *start*, but T002's findings shape T021. **T003 blocks Phases 3, 4 and 5 entirely.**
- **US1 (Phase 3)**: after T003. Independent of US2 and US3.
- **US2 (Phase 4)**: after T003. Independent of US1 — disjoint handlers in the same file, so coordinate the edit rather than the design.
- **US3 (Phase 5)**: after T003. Pure verification; can run alongside either.
- **Polish (Phase 6)**: after every story phase intended for this change.

### User Story Dependencies

- **US1 (P1)**: needs only `handle_item_not_found`. Shippable alone — this is the MVP.
- **US2 (P2)**: needs the other six handlers plus the `main` blueprint. Adds no user-visible behaviour on its own; it closes the trap for the next route.
- **US3 (P3)**: no source change. Verifies US1 and US2 did not overreach.

### File-Level Conflicts

`app/error_handlers.py` is touched by T003, T005 and T011, and `tests/unit/test_api_error_format.py`
by T004, T007, T013, T014, T015 and T016. Those are sequential within their file regardless of
phase — none is marked `[P]` against another task in the same file.

### Parallel Opportunities

- T002 alongside T003.
- T006 (JS) alongside T005 (Python) — different files.
- T012 (`app/main/routes.py`) alongside T011 (`app/error_handlers.py`).
- T015 and T016 are independent assertions but land in the same file as every other test task, so they carry no `[P]` — write them together.
- US1, US2 and US3 can be worked in parallel by different people once T003 lands, with the `error_handlers.py` edits coordinated.

---

## Parallel Example: User Story 1

```bash
# After T003 lands, these two touch different files:
Task: "T005 Change handle_item_not_found to wants_json() in app/error_handlers.py"
Task: "T006 Per-tile delete treats 404 as removed in app/static/js/product-attachments.js"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 — baseline recorded.
2. Phase 2 — `wants_json()` and its matrix test. **Blocks everything.**
3. Phase 3 — one handler, one JS line, four tests.
4. **STOP and VALIDATE**: the attachments grid reports failures as failures, and the stale-tile case
   passes because the `404` branch runs rather than because a redirect was followed.
5. Shippable here. The remaining phases close the trap for the rest of the API but change nothing a
   user can see today.

### Incremental Delivery

1. Setup + Foundational → the predicate exists, behaviour unchanged.
2. + US1 → the reported bug is fixed (MVP).
3. + US2 → the whole API honours the contract.
4. + US3 → the page-route half is proven, not assumed.
5. Polish → both suites green, working tree clean, issue #132's manual item ticked.

---

## Notes

- **Nine call sites, one predicate.** If a task tempts you toward a decorator, a config flag, or a
  per-route `jsonify`, re-read [research.md](./research.md) D1 — each was considered and rejected
  for being more machinery, and the constitution forbids adding error-handling machinery on top of
  the centralized handlers.
- **The payload never changes.** Any task that edits `ErrorHandler.handle_error` has gone wrong.
- **No Alembic revision, no model, no service.** This feature stores nothing.
- **e2e waits**: no `wait_for_timeout`, no `time.sleep`, no `networkidle`. Establish any
  JS-rendered region with `expect(...)` before a `count()`/`text_content()`/`is_visible()` read,
  and especially before a negative assertion.
- Commit after each task or logical group.
