# Phase 0 Research: API Routes Always Answer With JSON Errors

**Feature**: `specs/035-api-error-json` | **Date**: 2026-09-01

The spec left no `[NEEDS CLARIFICATION]` markers. This phase resolves the design questions the
implementation raises and records two facts found in the code that correct an assumption written
into the spec.

---

## D1. What decides the response format?

**Decision**: The request **path prefix**, in a single helper in `app/error_handlers.py`:

```
JSON_ROUTE_PREFIXES = ('/api/', '/admin/api/')
wants_json() -> request.path.startswith(JSON_ROUTE_PREFIXES) or request.is_json
```

**Rationale**: The route is what determines whether a response has a reader that parses it. The
caller's `Content-Type` is what `request.is_json` reports, and that is a property of the *request
body*, which a `DELETE` and a parameterless `GET` do not have. Keeping `or request.is_json` in the
predicate preserves the existing behaviour for JSON callers of page routes (FR-004) — the change
only ever *widens* the set of requests that receive JSON, so no working caller can regress.

**Alternatives considered**:

| Alternative | Rejected because |
|---|---|
| `request.accept_mimetypes.best == 'application/json'` | `fetch()` with no `Accept` header sends `*/*`; browsers send `text/html` first on navigations but `*/*` on `fetch`. The signal is present but noisy, and it makes the answer depend on a header the caller did not deliberately set. |
| `request.accept_mimetypes.accept_json and not accept_html` | Same problem, plus it is hard to read and hard to predict from a route's source. |
| Return 404 from `api_delete_attachment` directly instead of raising | Fixes one endpoint and leaves the trap for the next `/api/` route that raises. The issue says as much. |
| A `@json_errors` decorator applied per route | 49 decorations to keep in sync, and a route that forgets it is silently wrong. The bug is *omission*, so the fix must not be opt-in. |
| Register a second set of error handlers on the blueprints | Blueprint handlers cannot discriminate by path within a blueprint, and `main` and `product` each serve both page and `/api/` routes. |

---

## D2. `/admin/api/` — the spec's prefix assumption was too narrow

**Finding**: The spec's Assumptions state that "the `/api/` path prefix is a reliable
discriminator". That was established by reading the `@bp.route(...)` decorators, which is where it
is wrong: `app/admin/__init__.py` registers its blueprint with `url_prefix='/admin'`, so
`@bp.route('/api/materials/validate')` serves the path **`/admin/api/materials/validate`**.
A bare `startswith('/api/')` would leave the two admin API routes behind.

**Decision**: `JSON_ROUTE_PREFIXES` is a tuple of both prefixes — `str.startswith` accepts a tuple.

Rejected: `'/api/' in request.path`, which would also match a page path whose *variable segment*
happened to be `api` (`/products/orders/api/12345` matches `/products/orders/<vendor>/<order_number>`).
Unlikely, but a substring test that can be defeated by data is worse than two explicit prefixes.

**Route inventory** (verified by reading every `@bp.route` in `app/`):

| Blueprint | `url_prefix` | API paths | Page paths |
|---|---|---|---|
| `main` | none | 30 under `/api/` | 9 |
| `product` | none | 17 under `/api/` | 28 |
| `admin` | `/admin` | 2 under `/admin/api/` | 4 |

Every path under those two prefixes is machine-facing, and no path outside them is. The
discriminator holds once `/admin/api/` is included.

---

## D3. `main`'s blueprint-level 500 handler shadows the app-level one

**Finding**: `app/main/routes.py:3246-3253` registers `@bp.errorhandler(404)` and
`@bp.errorhandler(500)` that render `errors/404.html` / `errors/500.html`. Flask consults the
blueprint's handler before the app's, so an unexpected exception raised inside a `main` blueprint
`/api/` route is answered with an **HTML error page**, not the app-level handler's JSON.

This is less harmful than the redirect — the status really is 500, so a `fetch` caller's
`response.ok` is correctly `false` — but it still fails FR-001, and it is two lines to fix with
the same helper.

**Decision**: The `main` blueprint handlers gain the same `wants_json()` branch. The HTML
templates stay for page requests (FR-004); this is not a change to what a browser sees.

**Note on the `404` case**: a request to an unrouted path has no blueprint, so it reaches the
app-level handler. The blueprint 404 handler is only reachable from an explicit `abort(404)` or a
raised `NotFound`, and `grep -rn "abort(" app/` returns **nothing** — so that branch is dead today.
It is updated for consistency rather than because it is reachable; no test is written for it.

---

## D4. Which call sites change

Nine, all mechanical `request.is_json` → `wants_json()`:

| File | Line | Handler |
|---|---|---|
| `app/error_handlers.py` | 161 | `with_error_handling` decorator (unused today — `main/routes.py` imports it but no route applies it; updated for consistency) |
| `app/error_handlers.py` | 293 | `ValidationError` → 400 |
| `app/error_handlers.py` | 302 | `StorageError` → 500 |
| `app/error_handlers.py` | 311 | `ItemNotFoundError` → 404 |
| `app/error_handlers.py` | 320 | `AuthenticationError` → 401 |
| `app/error_handlers.py` | 329 | `ConfigurationError` → 500 |
| `app/error_handlers.py` | 338 | `500` |
| `app/error_handlers.py` | 346 | `404` |
| `app/main/routes.py` | 3246, 3251 | blueprint `404` / `500` |

No error handler is added, removed, or reordered, and the JSON payload built by
`ErrorHandler.handle_error` is untouched — which is what makes FR-005 hold by construction.

---

## D5. The client side is already written for this

**Finding**: `product-attachments.js:220` already reads
`if (response.ok || response.status === 404)`. FR-006's bulk-delete half needs **no JS change** —
the branch becomes live the moment the server returns 404 instead of a followed redirect.

**But** the per-tile trash handler at `product-attachments.js:98-105` checks `response.ok` alone.
Today a stale per-tile delete reloads the page (because the redirect yields a 200); after the
server fix it would get a 404 and show *"Could not remove that attachment"* — a **new** visible
error where there is none today, for an attachment that is in exactly the state the user asked for.

**Decision**: Align the per-tile handler with the bulk one — `response.ok || response.status === 404`.
Without it, this fix ships a user-visible regression on the same page it is fixing. This is FR-006
read as written ("the attachments grid"), not a scope widening.

---

## D6. What a failing `/api/` request costs today

`fetch` follows a 302 by default, so a failing `/api/` request always costs a second round trip.
What arrives back depends on the method, and **the two cases fail differently** — measured in the
browser during implementation, and *not* what issue #132 predicts:

| Caller | What `fetch` does with the 302 | Result |
|---|---|---|
| `GET` | re-issues as `GET /inventory` | `200` HTML. `response.ok` is **true** — the failure reads as success, which is the mode the issue describes. |
| `DELETE` | re-issues as **`DELETE /inventory`** | `405`. `response.ok` is **false** — the client reports a failure that did not happen. |

`fetch` only rewrites the method to `GET` for a `POST`; every other method is preserved across a
301/302. `/inventory` is a `GET`-only route, so the followed redirect cannot succeed. Confirmed from
the captured console of an e2e run against the unfixed handler: `HTTP 405: /inventory`.

So the attachments grid's stale-tile case was not silently succeeding — it was showing *"1
attachment could not be removed"* for an attachment that was already in the requested state, and
leaving the grid unreloaded. The issue's reasoning about `response.ok` holds for a `GET` caller and
inverts for this one. Both are wrong, both are fixed, and the fix is worth more than the issue
claimed: it removes a spurious user-visible error, not just a misleading mechanism.

After the fix the delete is one request. That is SC-003, assertable via `page.on("request")` — and
because all three new e2e tests fail against the unfixed handler, none of them passes by accident.

---

## D7. Testing approach

**Decision**: unit tests carry the whole change; one e2e test covers the browser path.

The change is a predicate plus nine call sites, so the tests that would have caught the bug are:

1. **The predicate itself** — `wants_json()` over the path matrix, using
   `app.test_request_context(path=...)`. Five cases: `/api/x`, `/admin/api/x`, `/products/1`,
   `/products/orders/api/9` (the substring trap from D2), and a page path with a JSON body.
2. **Through real routes, with no request body** — two endpoints that already raise
   `ItemNotFoundError` and need no contrivance to reach:
   - `GET /api/products/999999` → JSON 404 (`_product_or_404`, `routes.py:2233`)
   - `DELETE /api/attachments/999999` → JSON 404 (`api_delete_attachment`, `routes.py:2344`)
   - `DELETE /api/products/1/identifiers/999999` → JSON 404 (the second endpoint the issue names)
   Each asserts status **404**, `Content-Type: application/json`, `success: false`, and — the
   assertion that actually encodes the bug — that the response is **not** a redirect.
3. **An unrouted `/api/` path** → JSON 404 from the app-level `404` handler.
4. **The page-route regression** (FR-004) — `GET /products/999999` still answers 302 to the
   inventory list, and a JSON-bodied request to a page route still gets JSON.

**Not tested**: the `StorageError`, `AuthenticationError`, `ConfigurationError` and `500` handlers
through routes. No `/api/` route raises them without mocking a service into failure, and the branch
under test is character-identical in all seven handlers and covered by test 1. Manufacturing a
route per handler would be test machinery in service of a coverage number the constitution
explicitly does not chase.

**e2e**: one test for the two-tab case that issue #132's inherited checklist calls for — delete an
attachment, then delete a selection containing it, and assert the grid empties with no alert **and
that no request to `/inventory` was issued**. The second half is what distinguishes "passes for the
right reason" from today's accidental pass. `tests/e2e/test_product_attachments.py` already has a
`page.route` interception helper (`fail_deletes`) and a dialog recorder to build on.

---

## D8. Screenshots

`app/static/js/**` is touched, which trips `.github/workflows/screenshots.yml`. That workflow was
rewritten under issue #77 to post a **reminder comment** and nothing more — it regenerates nothing
and diffs nothing, and does not block merge. The JS change alters a status-code branch and no
rendered pixel, so no screenshot regeneration is warranted. The reminder comment is expected on the
PR and should be answered with that reasoning rather than by regenerating twelve files.

---

## D9. Measured baseline — the defect is wider than the issue records

Run against `main` at `2e6d63a` on 2026-09-01, with the script in
[quickstart.md](./quickstart.md) §1:

```
GET  /api/products/999999                  -> 302 /inventory
GET  /api/products/999999 +ct              -> 404 application/json
DEL  /api/attachments/999999               -> 302 /inventory
DEL  /api/products/1/identifiers/999999    -> 302 /inventory
GET  /api/no-such-route                    -> 302 /index
GET  /products/999999 (page)               -> 302 /inventory
```

Two findings beyond what issue #132 documents, both already covered by FR-001/FR-002 as written:

1. **It is not a `DELETE` problem.** `GET /api/products/<missing-id>` redirects for exactly the same
   reason — a `GET` with no query body has no content type either. `_product_or_404`
   (`app/product/routes.py:75`) is reached by seven routes, two of them under `/api/`, so the
   exposure is larger than the two `DELETE` endpoints the issue's Scope section names.
2. **An unrouted `/api/` path redirects to `/index`**, from the app-level `404` handler. A client
   requesting a misspelled or removed endpoint gets a `200` HTML home page after `fetch` follows it.

Lines 1 and 2 differ only by a `Content-Type: application/json` header on a request with **no body**.
That is the whole mechanism in one comparison, and it is the pair worth keeping as a regression test.

The page route on line 6 is the control: it must still read `302 /inventory` after the fix.

**Also confirmed**: `create_app(TestConfig)` with no `storage_backend` cannot reach these handlers —
the routes construct a `CatalogService` first and fail on engine creation. Any reproduction or test
must build storage the way `tests/conftest.py` does, which the constitution requires regardless.
