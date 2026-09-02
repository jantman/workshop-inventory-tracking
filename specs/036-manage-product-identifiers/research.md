# Phase 0 Research: Manage Product Identifiers After Creation

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-09-02

No `NEEDS CLARIFICATION` markers survived the spec, so this phase is not resolving unknowns
about *what* to build. It settles the six open questions about *how*, each against what the
codebase already does. Every one was answered by reading a neighbouring file rather than by
choosing a technology.

---

## D1 — What happens on the page after a successful add or remove

**Decision**: Reload the page (`window.location.reload()`) after a success. Render failures
into an alerts region inside the card, without reloading.

**Rationale**: The two sibling controls on this exact page already work this way —
`product-stock.js:79` reloads after a quantity or flag change, and `product-attachments.js:107`
reloads after an attachment delete. Reloading also discharges FR-012 and SC-004 ("the shown
list matches what is stored") by construction: there is no second copy of the list to disagree
with the database. And FR-011 (a refusal leaves the operator's typing in place) falls out for
free, because the failure path is the path that does not reload.

The spec's wording is "without the operator reloading the page" (FR-012, FR-016), not "without
a page load". The operator presses one button and the list is correct — which is what the
requirement is protecting.

**Alternatives considered**:
- *Append/remove the row in the DOM from the JSON response.* Rejected: it is more code, it
  introduces a client-side model of a server-rendered list, and it can silently drift from the
  database — exactly the failure SC-004 names. The normalization case makes this concrete: what
  you type is not what is stored (`687117723741` is stored as `00687117723741`), so a naive
  append would show the wrong text until the next load.
- *Re-fetch just the card's HTML.* Rejected: no such partial-render endpoint exists, and adding
  one for a single caller is the speculative generality Principle I prohibits.

---

## D2 — Where the add form lives in the card

**Decision**: A Bootstrap `collapse` block inside the existing Identifiers card, toggled by an
"Add identifier" button using `data-bs-toggle="collapse"` — markup only, no JavaScript of its
own. The form holds a type `<select>`, a value input, a vendor input, and the override
checkbox, mirroring `add.html:38-80`.

**Rationale**: The card sits in the narrow right-hand column of the detail page, and
`test_touch_readiness.py:145` asserts the page does not scroll sideways at 390px. A permanently
expanded four-field form in that column makes the card the tallest thing on a phone for a
control used rarely. Bootstrap's collapse is already loaded and costs nothing in JS.

**Alternatives considered**:
- *Always-visible form.* Simpler markup, but it dominates the card and pushes the identifier
  list — the thing the card is for — below the fold on a handheld.
- *A modal, like the label printer.* More markup than a collapse and no benefit; the label modal
  exists because it needs to fetch its options list first, which this does not.

---

## D3 — Keeping the type list identical in both places (FR-003)

**Decision**: Add `OPERATOR_IDENTIFIER_TYPES` to `app/models.py` beside `IdentifierType`,
derived from the enum with `INTERNAL` excluded, and pass it explicitly to the three
`render_template` calls that need it (`app/product/routes.py:253`, `:325` for `add.html`,
`:349` for `detail.html`).

**Rationale**: `add.html:50` hardcodes `['MPN', 'GTIN', 'VENDOR', 'DISTRIBUTOR']`. FR-003 makes
the two lists agreeing a *requirement*, and a second hardcoded copy is a requirement that holds
only until someone adds a fifth type. Deriving from `IdentifierType` also means the exclusion of
`INTERNAL` is stated once, in the place that knows why ("generated, never typed" —
`models.py:411`).

This is deduplication of an existing literal, not a new abstraction: a module-level tuple with
no behavior, no configuration and no extension point.

**Alternatives considered**:
- *Leave `add.html` alone and hardcode the same four in `detail.html`.* Fewer files touched,
  but it makes FR-003 an assertion about human discipline instead of about code.
- *A context processor or Jinja global.* Rejected: three explicit call sites are clearer than an
  invisible injection, and `app/__init__.py:157` currently injects exactly one thing (the app
  version) — a good bar to keep high.
- *A shared Jinja partial for the whole field group.* Rejected: the two forms differ in kind —
  `add.html` posts form fields by `name`, the card posts JSON read by element `id` — so the
  partial would need parameterizing on both, which costs more than it saves.

---

## D4 — The two response shapes the JS must read

**Decision**: Read the message from `data.error` when present and fall back to `data.message`.

**Rationale**: There are genuinely two shapes, and assuming one shows the operator `undefined`
in the other case:

| Case | Produced by | Shape |
|---|---|---|
| Validation refusal (400) | the route itself, `routes.py:2407` | `{success: false, error: "..."}` |
| Owned by another product (409) | the route itself, `routes.py:2411` | `{success: false, error: "...", owning_product_id: N}` |
| Product does not exist (404) | the central handler, `error_handlers.py:344` | `{success: false, message: "...", error_code, recovery_suggestions, ...}` |

FR-019 is the requirement that lands in the third row, and it is served by the *global* handler
rather than by the route, so its key is `message`, not `error`. This is the single most likely
thing to get silently wrong in this feature.

**Alternatives considered**: normalizing the shapes server-side. Rejected — that is a change to
the central error machinery, which the Technology Constraints section of the constitution
explicitly says not to build on top of, and it would affect every other caller for the benefit
of one.

---

## D5 — Treating an already-removed identifier as success (FR-018)

**Decision**: `if (response.ok || response.status === 404)` — the same test, and the same
reasoning, as `product-attachments.js:106`.

**Rationale**: The requested state is "this identifier is not on this product". A 404 means that
state holds. What makes this worth stating is the history: before #132 (closed 2026-09-02) this
endpoint answered a bodyless `fetch` with a **302 to `/inventory`**, `fetch` followed it, and
`response.ok` was true — so the attachment equivalent of this branch was dead code and the
behavior was right by accident. `wants_json()` in `error_handlers.py:148` now settles the format
by route rather than by whether the caller sent a body, so the 404 is real and the branch is
live. The e2e "remove it in one tab, then the other" case is what proves it.

**Alternatives considered**: reporting the 404 as an error. Rejected by FR-018 and by the spec's
own edge case — it would show the operator a failure for the thing they asked for having already
happened.

---

## D6 — Test shape and placement

**Decision**: Two new files, no page object.

- `tests/unit/test_product_identifiers.py` — the HTTP contract the card depends on: 201 and the
  stored normalized value, 400 for a bad check digit, 201-with-override, 400 for the all-zero
  no-read, 409 carrying `owning_product_id`, 400 for a vendor-scoped type with no vendor, the
  idempotent re-add leaving one row, 204 then 404 on a repeated delete, and 404 for a product
  that does not exist. Plus one test that `OPERATOR_IDENTIFIER_TYPES` excludes `INTERNAL` and
  covers every other `IdentifierType` member.
- `tests/e2e/test_product_identifiers.py` — the operator flows, including the scan-back that
  closes SC-002.

**Rationale**: `tests/e2e/pages/` holds page objects for the inventory pages only; every
product-detail e2e file (`test_product_attachments.py`, `test_product_specifications.py`,
`test_touch_readiness.py`) drives element ids directly. Matching the neighbours beats
introducing a `ProductDetailPage` for one feature.

For the scan-back, `tests/e2e/test_wedge_scan.py:33` already has the `scan()` helper shape —
type into `#global-scan-input`, press Enter — which is the honest way to prove SC-002 rather
than asserting against `find_product_by_identifier` directly.

**Waiting**: every wait is an `expect()` on an element. The add and remove paths both end in a
reload, so pattern **C** from `CLAUDE.md` applies — the rendered list is on the far side of the
completed request, so `expect(rows).to_have_count(n)` is the whole wait. The error paths do not
reload, so the wait there is `expect(alert).to_contain_text(...)`. Negative assertions ("the row
is gone") must follow a positive `expect` that establishes the list first.

**Alternatives considered**: asserting the outcome through the service in-process. Rejected —
the defect in #136 is precisely that the service works and nothing calls it, so a test that
calls the service would have passed on the broken build.

---

## Open questions

None. Nothing in this phase needs the operator's input before implementation.
