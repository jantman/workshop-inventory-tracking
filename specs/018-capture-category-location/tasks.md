---

description: "Task list for feature implementation"
---

# Tasks: Category and Location on the Capture Confirmation Page

**Input**: Design documents from `/specs/018-capture-category-location/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/capture-form.md](./contracts/capture-form.md), [contracts/capture-order.md](./contracts/capture-order.md), [quickstart.md](./quickstart.md)

**Tests**: Test tasks are **included and required**, not optional. Constitution Principle IV:
"Changes that alter behavior MUST land with tests covering that behavior." Unit tests exercise
the service and the route; E2E covers the operator-facing behavior. Everything runs under
`nox -s tests` and `nox -s e2e`.

**Organization**: Tasks are grouped by user story so each can be implemented, tested and shipped
on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths are in every task

## Path Conventions

Flask web application, server-rendered. This feature touches:

| File | Change |
|---|---|
| `app/templates/product/_classification_fields.html` | **New** — the three inputs, one definition |
| `app/templates/product/_form_fields.html` | Includes the partial in place of the block that moved |
| `app/templates/product/capture.html` | Includes the partial; two script tags |
| `app/catalog_service.py` | `capture_order` gains three parameters |
| `app/product/routes.py` | `product_capture` reads three form fields and passes them on |
| `tests/unit/test_capture.py`, `tests/unit/test_product_routes.py`, `tests/e2e/test_order_capture.py` | Tests |
| `docs/user-manual.md`, `docs/images/screenshots/user-manual/order_capture.png` | Docs |

**There is no Alembic revision in this feature, and there must not be one.** `products` already
has `category_path`, `location` and `sub_location`, all nullable. If a task has you editing
`app/database.py` or `migrations/`, stop and re-read [data-model.md](./data-model.md). Likewise
there is **no new endpoint**: `/api/categories` and `/api/inventory/field-suggestions/<field>`
already exist and already serve both halves of the app.

---

## Phase 1: Setup

**Purpose**: Confirm the ground the feature stands on before building on it. Both tasks are
reads; neither writes code.

- [X] T001 Confirm work is on feature branch `issues/99` (cut during `/speckit-specify`), not `main` — constitution: non-trivial code changes go through a branch and a PR
- [X] T002 [P] Confirm the surface this feature reuses is really there, so nothing below invents a substitute: `products.category_path`/`location`/`sub_location` are nullable columns in `app/database.py` (lines 842-847); `category_path`, `location` and `sub_location` are all already in `update_product`'s `editable` set in `app/catalog_service.py`; and `FIELD_SUGGESTION_COLUMNS` in `app/services/vocabulary.py` already reads `location`/`sub_location` from **both** `InventoryItem` and `Product`. That last one is why FR-007 and FR-008 need no backend code

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Put the three inputs on the capture page, defined once. Every story needs them —
US1 submits them, US2 suggests into them, US3 re-renders them.

**⚠️ No user story work can begin until this phase is complete.**

- [X] T003 Create `app/templates/product/_classification_fields.html` by moving lines **114-157** of `app/templates/product/_form_fields.html` — the two `<div class="row">` blocks holding Category, Storage Location and Sub-Location — **verbatim**, keeping every element id (`category_path`, `category-suggestions`, `location`, `location-suggestions`, `sub_location`, `sub_location-suggestions`), every `maxlength`, every `autocomplete="off"`, the `position-relative` wrappers and the existing `{# ... #}` comment about how the dropdown sibling is the whole integration with `field-autocomplete.js`. Do **not** move the card wrapper (109-113), the `show_threshold` block (159+) or the `show_tags` block — each page keeps its own card. Add a short header comment saying the partial reads `values` and is included by both the product form and the capture page, so the two cannot drift (FR-007, FR-008)
- [X] T004 Replace lines 114-157 of `app/templates/product/_form_fields.html` with `{% include "product/_classification_fields.html" %}`, leaving the surrounding card, the `show_threshold` block and the `show_tags` block untouched
- [X] T005 Prove the move was faithful before building on it: `venv/bin/nox -s tests` stays green, and the rendered `/products/add` markup is unchanged apart from whitespace. The partial's own indentation differs from its old position (8 spaces inside a 4-space card body vs. 16 inside capture's), which is cosmetic — **any change to an attribute, an id or an element is not**, and means T003 edited rather than moved
- [X] T006 Include the partial in `app/templates/product/capture.html`: a new `<div class="card mb-4">` with a `Classification & Location` header, inserted **between line 235** (the `</div>` closing the "Paste the listing URL" card) **and the `{% if listing %}` capture-summary block**, so filing reads after the order details and before the summary of what the listing yielded. Wrap the include in `{% with values = form_data %}` — the capture page names its context `form_data` and the partial reads `values`; Jinja includes inherit the current context, so the `with` binding reaches it. This alone satisfies FR-011 (all three re-render paths already pass `form_data=request.form`) and gets US2's location and sub-location suggestions working, because `field-autocomplete.js` is already loaded by `capture.html` and auto-binds both ids

---

## Phase 3: User Story 1 - File the product while capturing it (Priority: P1) 🎯 MVP

**Goal**: What the operator types in the three fields is written to the product, on both the
create path and the attach-to-existing path.

**Independent test**: Capture an order with a category, a location and a sub-location filled in,
then open the resulting product and read all three back off it.

### Tests for User Story 1 ⚠️

- [X] T007 [P] [US1] Add a `TestFilingAtCapture` class to `tests/unit/test_capture.py`, beside `TestAttachVsCreate` (which is where the create-vs-attach distinction already lives). Cover: all three stored on a created product; all three omitted leaves them `None` and the capture otherwise identical (FR-003, FR-004); each field independently (FR-003); a category path normalized to canonical form; **a canonical path over 512 characters raises `ValidationError` and writes nothing at all** — no product, no purchase (FR-005); a stated value overwriting an existing product's value on the attach path (FR-009); **a blank field leaving an existing product's value alone** (FR-010); and `category_path='///'` on the attach path leaving the existing category alone, not clearing it. That last one is the side-door version of FR-010 and is the test most likely to be missing
- [X] T008 [P] [US1] Add a route test to `tests/unit/test_capture.py` (**not** `tests/unit/test_product_routes.py` as first written: the route-level capture harness — a `client.post('/products/capture', ...)` helper — already lives in `test_capture.py`, while `test_product_routes.py` is exclusively about product-code routing): a POST to `/products/capture` carrying `category_path`, `location` and `sub_location` files the product; and a POST carrying a `listing` payload but none of the three leaves all three `None` — nothing in a listing may populate them (FR-013)
- [X] T009 [US1] Add E2E tests to `tests/e2e/test_order_capture.py` under a new "Filing at capture (issue #99)" section. The existing module-level `capture(page, base_url, **fields)` helper fills `#{field}` per keyword argument, so `capture(page, url, category_path='electronics/passives/resistors', location='Shelf A', sub_location='Bin 3')` needs no new plumbing. Assert the product detail page shows the category via `expect(page.locator("#product-category")).to_have_text(...)` — that element is rendered **only** when `category_path` is set, so its presence is the assertion; never snapshot it with `text_content()`. Also cover the FR-009/FR-010 pair through the recycled-identifier question: attach with a new location and see it re-filed, then attach again with the field blank and see it unchanged

### Implementation for User Story 1

- [X] T010 [US1] Add `category_path`, `location` and `sub_location` keyword parameters (all defaulting to `None`) to `CatalogService.capture_order` in `app/catalog_service.py`, per [contracts/capture-order.md](./contracts/capture-order.md). Document all three in the docstring, and state there that they are never populated from `listing` (FR-013)
- [X] T011 [US1] In `capture_order` in `app/catalog_service.py`, normalize and validate the category path **up front**, in the block that already calls `self._validate_price(...)` and `self._validate_purchase_quantity(...)`: `category_path = self._validate_category_path(category_path)`. This is what makes FR-005 refuse an over-length path *before* the duplicate and recycled-identifier questions are raised, preserving the method's documented contract that a refused capture leaves "a database this call has not touched"
- [X] T012 [US1] In `capture_order` in `app/catalog_service.py`, pass all three through to `create_product` on the branch where `product is None`, unconditionally. `None` stores `NULL`, which is "uncategorized/unlocated" and is an ordinary state, not an error (FR-003)
- [X] T013 [US1] In `capture_order` in `app/catalog_service.py`, rewrite the `elif wording is not None and wording != product.description:` branch as a `changes` dict built by **presence**, exactly as [data-model.md](./data-model.md#path-b--the-capture-attaches-to-a-product-that-already-exists) sets out: keep the existing description condition, then add `category_path` only when `category_utils.canonical(category_path) is not None`, and `location`/`sub_location` only when `_clean(value) is not None`; call `update_product(product.id, **changes)` once, and only if `changes` is non-empty. **This is the task that goes wrong if written the obvious way.** `_clean('')` and `canonical('')` both return `None`, and `update_product` writes every key it is given — so passing the keys unconditionally sets the columns to `NULL` and erases an existing product's filing on every capture that left the field blank, which is the exact inverse of FR-010. Note also that the two "was it stated?" tests are different functions on purpose: `_clean('///')` returns `'///'` and reads as stated, while `canonical('///')` is `None`, so using `_clean` for the category writes `NULL` by a side door
- [X] T014 [US1] In `product_capture` in `app/product/routes.py`, read `category_path`, `location` and `sub_location` off `request.form` and pass them to `capture_order`. Straight through: **no `or` fallback, no default, and no consultation of `listing`** — unlike `manufacturer` and `unit_price` directly above, which deliberately do fall back to the listing. Add a one-line comment saying why these three do not (FR-013). Leave `/api/capture` alone; it passes none of the three and keeps today's behavior exactly

**Checkpoint**: US1 is complete and shippable. Issue #99 is closed at this point — a captured product can be filed without a second visit.

---

## Phase 4: User Story 2 - Type against the vocabulary the rest of the app already knows (Priority: P2)

**Goal**: The three fields suggest from what the shop already records, so filing stays
consistent instead of drifting by spelling.

**Independent test**: Type a partial location that exists only on a metal stock item and confirm
the suggestion appears, without submitting the form.

**Note**: T006 already delivered the location and sub-location halves — `field-autocomplete.js`
is loaded by `capture.html` today and auto-binds `#location` and `#sub_location` on
`DOMContentLoaded`. Only the category datalist needs a change, which is why this phase is two
tasks.

### Tests for User Story 2 ⚠️

- [X] T015 [US2] Add E2E tests to `tests/e2e/test_order_capture.py`: seed a metal stock item through `live_server.add_test_data([...])` (milliseconds, versus three seconds through the Add Item form) with a location no product uses, type its opening letters into `#location` on the capture page, and `expect` an option inside `#location-suggestions` — `expect` polls, which is what absorbs the 200 ms debounce and the fetch; a fixed wait in front of `count()` is the load-bearing-cushion mistake. Also assert the `#category-suggestions` datalist is populated from an existing category, and that `#sub_location-suggestions` is scoped by the value in `#location`. Establish each dropdown with `expect(...)` before any negative assertion about it

### Implementation for User Story 2

- [X] T016 [US2] Add two script tags to the `{% block scripts %}` in `app/templates/product/capture.html`, **before** the existing `field-autocomplete.js` tag: `js/datalist.js` then `js/catalog-suggestions.js`. Copy the ordering comment from `app/templates/product/add.html:117-118` — `catalog-suggestions.js` reads `window.WorkshopDatalist` as it loads, not on `DOMContentLoaded`, so the order is load-bearing rather than tidy. `catalog-suggestions.js` also fetches `/api/tags` into a `#tag-suggestions` datalist that the capture page does not have; its `load()` returns early when the datalist is missing, so no guard is needed and none should be added

**Checkpoint**: US1 and US2 both work independently.

---

## Phase 5: User Story 3 - The filing survives a question (Priority: P3)

**Goal**: A capture that comes back asking something does not throw away what the operator typed.

**Independent test**: Trigger the duplicate question with the three fields filled in, and read
them back off the re-rendered form.

**Note**: **This phase has no implementation task, and that is correct.** All three re-render
paths in `product_capture` already pass `form_data=request.form`, and the partial renders
`values.get('...') or ''`. T006 satisfied FR-011 the moment it landed. What is left is proving
it, and keeping it proven — which is the whole reason US3 is a story rather than a footnote.

### Tests for User Story 3 ⚠️

- [X] T017 [US3] Add E2E tests to `tests/e2e/test_order_capture.py` covering all three re-render paths with the three fields filled in: the duplicate question (capture the same listing twice), the recycled-identifier question (same vendor item id, uncorroborated manufacturer), and a `ValidationError` (a category path over 512 characters). In each case `expect(page.locator("#category_path")).to_have_value(...)` for all three fields, then answer the question and assert the product is filed with those values. For the validation case, assert the value came back **as typed and not truncated** — FR-005 is a rejection, and a test that only checks for an error message would pass against a page that silently shortened the path

**Checkpoint**: all three stories independently verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T018 [P] Document the three fields in `docs/user-manual.md`, in "Capturing an Order When You Place It" (around line 900): that filing now happens at capture instead of on a second visit, that all three are optional and uncategorized is an ordinary state, and — the one non-obvious rule — that on a capture attaching to a product you already own, a value you type **replaces** the one it had, while leaving the field blank changes nothing
- [X] T019 Regenerate screenshots: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless`. `capture.html` changed, so `docs/images/screenshots/user-manual/order_capture.png` is stale and the constitution makes regenerating it part of this change rather than a follow-up. **`docs/images/screenshots/user-manual/product_add_form.png` must come back unchanged** — it renders `add.html` through `_form_fields.html`, so a diff there means T003/T004 altered the markup and is a bug to fix, not a screenshot to accept. The catalog shots come from the `test_screenshot_*` methods in `tests/e2e/test_screenshot_generation.py`, not from `screenshot_config.yaml`; reading only the YAML is how this gets missed
- [X] T020 `venv/bin/nox -s screenshots_verify` — valid PNG, RGB/RGBA, under 500KB
- [X] T021 `venv/bin/nox -s tests` — the full unit suite green
- [X] T022 `venv/bin/nox -s e2e` with a **15-minute** tool timeout (constitution Principle IV; run it detached and poll, since it outlasts a 10-minute cap). Then confirm `git status --short` is clean apart from intended edits — a test session that rewrites tracked files is a failed session
- [X] T023 Review the diff against [quickstart.md](./quickstart.md): no Alembic revision and no edit to `app/database.py`; no new route; no change to `/api/capture`; the three fields never read from `listing`; the attach path passes keys by presence, not by value; and no `wait_for_timeout`, `time.sleep` or `networkidle` anywhere in the new tests
- [ ] T024 **Left for the operator** — it writes captures into the live inventory database, which is not mine to write to. Its most important step (attach with the field blank, confirm the filing is unchanged) is covered by `test_attaching_with_the_fields_blank_leaves_the_filing_alone` and by two unit tests. Walk the manual checks in [quickstart.md](./quickstart.md#2-manual-walkthrough), especially step 4 of the FR-009/FR-010 sequence — capture a third time with the location blank and confirm the product is still filed where it was. That is the single check that catches T013 written the obvious way
- [X] T025 Open the pull request for `issues/99` referencing issue #99, stating the FR-009 decision (a typed value replaces what an existing product held) in the description so the choice is reviewable where the code is

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: needs nothing from Phase 1 beyond T001; blocks all three stories. T005 gates T006 — do not build on an extraction that has not been shown faithful
- **US1 (Phase 3)**: needs Phase 2 (the fields must be on the page and submitting). Independent of US2 and US3
- **US2 (Phase 4)**: needs Phase 2 only. Does **not** need US1 — suggestions are a page behavior and work whether or not the values are stored yet
- **US3 (Phase 5)**: needs Phase 2 only for the re-render itself; its "and then it is filed" assertions need US1
- **Polish (Phase 6)**: after every story that is going in. T019/T020 need the final templates; T025 needs everything

### Within Each User Story

Tests first, and failing, before the implementation that makes them pass. Within a story the
implementation tasks are sequential — T010 through T013 all edit `app/catalog_service.py`.

### Parallel Opportunities

- T002 is `[P]` with T001: one is a read, the other a branch check
- T007 and T008 are `[P]` with each other: different test files
- T018 is `[P]` with the test tasks: `docs/user-manual.md` is touched by nothing else
- Everything else is sequential by file. `app/templates/product/capture.html`,
  `app/catalog_service.py` and `tests/e2e/test_order_capture.py` each take one editor at a time

## Implementation Strategy

### MVP (User Story 1 only)

Phases 1 → 2 → 3, then stop and validate. That is issue #99 closed: a captured product is filed
at capture time and the second visit is gone. US2 keeps the filing *consistent* and US3 keeps it
from being *lost to a question*, but neither is what the issue asked for.

### Incremental delivery

1. Setup + Foundational → the three inputs are on the capture page, defined once
2. US1 → what is typed is stored (MVP — ship-able)
3. US2 → the category datalist fills, so filing stops drifting by spelling
4. US3 → proof the filing survives a question
5. Polish → docs, screenshot, full suites, manual walk, PR

## Notes

- Every task names its file. Nothing in this feature touches a model, a migration or a new endpoint
- Commit per phase, or per logical group within a phase
- The one thing to be careful about is **T013**. Everything else in this feature is threading
  values through functions that already know what to do with them; T013 is the one place where the
  obvious implementation is silently wrong, and its failure mode — erasing a product's filing on a
  capture where the operator touched nothing — is invisible until someone goes looking for
  something that is no longer where they put it
