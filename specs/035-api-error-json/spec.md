# Feature Specification: API Routes Always Answer With JSON Errors

**Feature Branch**: `speckit/035-api-error-json`

**Created**: 2026-09-01

**Status**: Draft

**Input**: GitHub issue #132 — "An /api/ DELETE answers a JSON client with an HTML redirect, making the client's 404 handling dead code"

## Context

The application's browser pages talk to the application's own `/api/` routes with background
requests. When one of those requests fails, the error is currently rendered based on what the
*caller sent* rather than on what the caller *asked for*: a request that carries a JSON body
gets a JSON error with the right status code, and an otherwise identical request that carries
no body at all (every `DELETE`, and any `GET` without parameters) gets an HTML redirect to a
page instead.

The observable consequence today is on the product attachments grid. Deleting an attachment
that another browser tab already deleted returns a redirect to the inventory list, and the
browser follows it — which cannot succeed, because the inventory list does not accept a
delete. The user is told the attachment could not be removed, for an attachment that is
already in exactly the state they asked for, and the grid is left unrefreshed. The front-end
code written to recognise "already gone" never runs.

The same defect reads the opposite way for a caller that is fetching rather than deleting:
there the redirect *is* followed successfully, an unrelated page comes back as a success, and
a real failure is reported as though it worked. One mechanism, two ways to be wrong, and in
both of them the caller cannot tell what actually happened.

This feature makes the response format depend on the route, so that every `/api/` route
reports failures as failures, and the page routes keep the flash-message-and-redirect
behaviour that a browser form submission needs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A failed API operation is reported as a failure (Priority: P1)

The workshop owner has a product open in two browser tabs. In the first tab they delete an
attachment. The second tab still shows the stale grid, including the attachment that is now
gone. They tick that attachment along with two others and use **Delete Selected**.

The two attachments that still exist are deleted. The one that was already gone is treated as
"already in the state you asked for" and does not raise an error. The page reports success and
refreshes, and the grid shows the three attachments removed.

**Why this priority**: This is the case the issue was found in, and it is the one where the
current behaviour actively hides information. A delete that fails for any reason other than
"already gone" is currently reported as a success and the failure disappears with no message —
which is exactly what the partial-failure handling exists to prevent.

**Independent Test**: Delete an attachment, then issue a second delete for the same attachment
and confirm the caller receives a "not found" answer it can distinguish from success, and that
no page fetch happens as a side effect.

**Acceptance Scenarios**:

1. **Given** an attachment that has already been deleted, **When** a delete is requested for
   it, **Then** the caller receives a machine-readable "not found" answer with a 404 status
   and no redirect is issued.
2. **Given** a selection of three attachments of which one is already deleted, **When**
   **Delete Selected** is used, **Then** all three are reported as removed, the grid refreshes,
   and no error is shown.
3. **Given** a delete that fails for a reason other than the attachment being absent, **When**
   the selection is submitted, **Then** the page reports the failure and does not silently
   reload as though it had succeeded.
4. **Given** any failing `/api/` request, **When** it completes, **Then** no HTML page is
   fetched as a side effect of the failure.

---

### User Story 2 - Every API route reports errors the same way (Priority: P2)

Any caller of an `/api/` route — the application's own pages, a command-line request, a
future integration — receives a machine-readable error with an accurate status code for every
class of failure the application raises, whether or not the request carried a body.

**Why this priority**: The attachments grid is the case with a visible symptom, but the same
trap is one raised error away on any of the other `/api/` routes. Fixing it once, at the point
where errors are rendered, means the next `/api/` route to raise an error is correct without
anyone remembering this issue.

**Independent Test**: For each error class the application raises, request an `/api/` route
that raises it, without sending a body, and confirm a machine-readable error with the expected
status code comes back.

**Acceptance Scenarios**:

1. **Given** an `/api/` route that raises "item not found", **When** it is requested without a
   body, **Then** the response is a machine-readable error with status 404.
2. **Given** an `/api/` route that raises a validation failure, **When** it is requested
   without a body, **Then** the response is a machine-readable error with status 400.
3. **Given** an `/api/` route that raises a storage, configuration, or authentication failure,
   **When** it is requested without a body, **Then** the response is a machine-readable error
   with the status matching that failure class (500, 500, 401 respectively).
4. **Given** a request for an `/api/` path that does not exist, **When** it is made without a
   body, **Then** the response is a machine-readable 404 rather than a redirect.
5. **Given** an `/api/` request that *does* carry a JSON body and fails, **When** it completes,
   **Then** its response is unchanged from today's behaviour.

---

### User Story 3 - Browser pages keep their existing error behaviour (Priority: P3)

Submitting a form on a page — adding an item, editing a product, receiving a purchase — that
fails validation continues to land the user on a page with a readable message explaining what
went wrong, exactly as it does today.

**Why this priority**: This is the behaviour that must *not* change. It is stated as a story so
that it is covered by a test rather than assumed.

**Independent Test**: Submit a page form with input that fails validation and confirm the user
still sees the page with a flash message rather than a raw error document.

**Acceptance Scenarios**:

1. **Given** a page form submission that fails validation, **When** it is submitted, **Then**
   the user is redirected to a page and shown the error message as a flash notice.
2. **Given** a request for a page path that does not exist, **When** it is made from a browser,
   **Then** the user is redirected to the home page with a "page not found" notice.

---

### Edge Cases

- **An `/api/` request that fails and also declares a JSON body.** Both signals agree; the
  answer is JSON, as it is today.
- **A page route requested by a background fetch.** No such caller exists in the application
  today; page routes continue to redirect. This is deliberate — the discriminator is the route,
  not the caller.
- **A delete for an item that never existed** (as opposed to one that was deleted a moment
  ago). Indistinguishable to the application, and answered identically: a 404. The front-end
  treats both as "the state you asked for", because they are.
- **An unexpected internal error on an `/api/` route.** Answered as a machine-readable error
  with status 500, not a redirect — the caller must be able to tell it apart from a success.
- **The redirect target is itself unavailable.** No longer reachable from an `/api/` route,
  because no redirect is issued.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every route under the `/api/` path MUST answer a failed request with a
  machine-readable error document and the status code appropriate to the failure, regardless of
  whether the request carried a body or declared a content type.
- **FR-002**: The status code MUST match the failure class: 400 for validation failures, 401
  for authentication failures, 404 for a missing item or a missing `/api/` path, and 500 for
  storage failures, configuration failures, and unexpected internal errors.
- **FR-003**: A failed `/api/` request MUST NOT be answered with a redirect, and MUST NOT cause
  any page to be fetched as a side effect of the failure.
- **FR-004**: Routes outside the `/api/` path MUST retain their current behaviour on failure —
  a flash message and a redirect to a sensible page for a browser caller, and a machine-readable
  error for a caller that declares a JSON body.
- **FR-005**: The error document returned by an `/api/` route MUST carry the same fields as the
  one returned today to a caller that declares a JSON body, so that no existing caller needs to
  change to keep working.
- **FR-006**: The attachments grid MUST treat a "not found" answer from a delete as a
  successful removal, and MUST treat every other failure as a failure — reporting it to the user
  and not refreshing the grid as though the operation had succeeded.
- **FR-007**: The behaviour MUST be covered by automated tests for both halves of the rule: an
  `/api/` route failing without a body returns a machine-readable error, and a page route
  failing from a browser still redirects with a flash message.

### Key Entities

None. This feature changes how failures are reported; it stores nothing and changes no data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of failing requests to `/api/` routes are answered with a machine-readable
  error and no redirect, whether or not the request carried a body.
- **SC-002**: All five failure classes the application raises (validation, authentication,
  item-not-found, storage, configuration) plus unhandled internal errors and unknown `/api/`
  paths return the correct status code, verified by test.
- **SC-003**: Deleting an already-deleted attachment issues exactly one request — the delete
  itself — where it currently issues two, the delete and a wasted follow-up to the inventory
  list that cannot succeed.
- **SC-004**: A delete that fails for a reason other than "already gone" produces a visible
  message to the user in 100% of cases, where today it produces none.
- **SC-005**: Page form submissions that fail validation continue to show a flash message on a
  page, with zero regressions in the existing test suite.

## Assumptions

- **The API path prefixes are a reliable discriminator.** Every route under `/api/` or
  `/admin/api/` is a machine-facing endpoint, and every route outside them renders or redirects to
  a page. Both prefixes are needed: the admin blueprint is registered with `url_prefix='/admin'`,
  so its `/api/...` routes are served at `/admin/api/...`. Verified against the full route table —
  51 machine-facing routes under the two prefixes, 39 page routes outside them, no exceptions.
  (An earlier draft of this assumption named only `/api/`; planning caught the admin prefix.)
- **All error classes get the same treatment, not just item-not-found.** The issue reports the
  problem against "item not found" and notes that authentication has the same shape. Fixing the
  handlers one at a time leaves the trap in place for the rest, so all of them are in scope.
  This is the point of the change, not a widening of it: the requirement is one rule about
  `/api/` routes, applied everywhere failures are rendered.
- **The error document format does not change.** Callers that already receive JSON errors today
  keep receiving exactly what they receive now; only the set of requests that get JSON widens.
- **No new configuration.** The rule is unconditional; there is no setting to turn it off.
- **The two endpoints named in the issue are examples, not the scope.**
  `DELETE /api/attachments/<id>` is the one with a UI caller and
  `DELETE /api/products/<id>/identifiers/<id>` has none today, but the fix is at the point where
  errors are rendered and therefore covers every `/api/` route.

## Out of Scope

- Changing which errors the application raises, or where it raises them.
- Adding new `/api/` routes, or changing the success responses of existing ones.
- Reworking the attachments grid beyond making its existing "already gone" and partial-failure
  handling function as written.
- Any change to how errors are logged.
