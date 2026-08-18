# Phase 0 Research: Category and Location on the Capture Confirmation Page

Everything below was resolved by reading the code. No `NEEDS CLARIFICATION` remains; the
spec's single marker (FR-009) was answered by the operator before planning started.

---

## 1. How much of this already exists

**Decision**: Add no column, no migration, no endpoint and no service method.

**Rationale**: The three things this feature stores are already stored, and the two
vocabularies it needs are already served.

| What FR-002/FR-005/FR-008 need | Where it already is |
|---|---|
| A place to put a category path | `Product.category_path`, `String(512)`, nullable, indexed — `app/database.py:842` |
| A place to put a location and sub-location | `Product.location` / `Product.sub_location`, `String(100)`, nullable — `app/database.py:844,847` |
| Creating a product with all three | `CatalogService.create_product(category_path=…, location=…, sub_location=…)` |
| Updating all three on an existing product | `CatalogService.update_product` — all three are in its `editable` set |
| Category normalization and the length limit | `_validate_category_path` → `category_utils.canonical`, raising `ValidationError` on over-length ("over-length is a rejection, not a truncation") |
| Category suggestions | `GET /api/categories` (`app/product/routes.py:960`), consumed by `catalog-suggestions.js` into the `#category-suggestions` datalist |
| Location / sub-location suggestions, scoped | `GET /api/inventory/field-suggestions/<field>` (`app/main/routes.py:1198`) → `VocabularyService` |

**FR-007 is already true and needs no code.** `VocabularyService.FIELD_SUGGESTION_COLUMNS`
reads `location` and `sub_location` from **both** `InventoryItem` and `Product`
(`app/services/vocabulary.py:52-58`). Both columns are `String(100)` on both tables. The two
sides cannot diverge in what they hold because they are the same width, and cannot diverge in
what they suggest because they are the same query.

**Alternatives considered**: a capture-specific suggestion endpoint (rejected — Principle I,
and it would create the drift FR-007 forbids); widening `sub_location` (rejected — nothing
asked for it, and it would break the symmetry FR-007 depends on).

---

## 2. Sharing the markup instead of copying it

**Decision**: Extract the three field rows from the "Classification & Location" card in
`app/templates/product/_form_fields.html` into a new partial
`app/templates/product/_classification_fields.html`, and include it from both
`_form_fields.html` and `capture.html`.

**Rationale**: The issue's requirement is "the same inputs the product form already uses so
the suggestion vocabularies are shared". Two copies of forty-five lines of markup satisfy
that on the day they are written and stop satisfying it the first time one is edited. A
shared partial makes FR-008 a structural property rather than a thing to remember.

It is also a small extraction. `_form_fields.html` lines 109-158 are a card whose body holds
two `<div class="row">` blocks (category + location, then sub-location) followed by the
`show_threshold` and `show_tags` conditionals. Only the two rows move; each page keeps its
own card wrapper, so the capture page can title its card as it likes.

**The context variable.** `_form_fields.html` reads `values.get(…)`; `capture.html` reads
`form_data.get(…)`. The partial reads `values`, and `capture.html` includes it inside
`{% with values = form_data %}` — Jinja includes inherit the current context, so the `with`
binding is visible. `request.form` and `request.args` are both MultiDicts with `.get`, so the
GET and POST renders behave identically.

**Element ids do not collide.** `#category_path`, `#location` and `#sub_location` move with
the markup and must keep those exact ids: `field-autocomplete.js` auto-binds `location` and
`sub_location` by id on `DOMContentLoaded` and skips any target whose sibling dropdown div is
absent (`app/static/js/field-autocomplete.js:218-239`), and `catalog-suggestions.js` fills
`#category-suggestions` by id. `_form_fields.html` and `capture.html` are never rendered on
the same page.

**Alternatives considered**: copying the markup into `capture.html` (rejected — guaranteed
drift, and FR-007/FR-008 are precisely about not drifting); making `capture.html` include the
whole of `_form_fields.html` behind flags (rejected — it carries description, manufacturer,
specifications, quantity and tags that the capture page either already has its own copy of or
deliberately does not offer, so it would need four new flags to suppress them, which is the
configuration knob Principle I prohibits).

---

## 3. FR-010: blank must not clear, and `None` means clear

**Decision**: On the attach-to-existing path, add each of the three keys to the
`update_product` call **only when the operator stated a value**. Do not pass the key at all
when the field came back blank.

**Rationale**: This is the one place the obvious implementation is wrong.

- `_clean('')` returns `None` (`app/catalog_service.py`, "turning blank into None").
- `category_utils.canonical('')` returns `None`, and so does `canonical('///')` — a path of
  nothing but separators is "no category", not an error.
- `update_product` writes every key it is given: `product.category_path =
  self._validate_category_path(fields['category_path'])`. Passing `None` *sets the column to
  NULL*.

So `update_product(pid, category_path=form.get('category_path'))` would erase an existing
product's filing every time the operator left the field alone — the exact opposite of FR-010.
`update_product`'s own docstring names the protection: "Only the fields present in `fields`
are touched, so a caller that knows about three fields cannot blank the other ten." Presence
is the mechanism; this feature has to use it.

**The test for "stated" differs by field**, because the two normalizers differ:

| Field | Stated when |
|---|---|
| `category_path` | `category_utils.canonical(value) is not None` |
| `location`, `sub_location` | `_clean(value) is not None` |

Using `_clean` for the category would treat `"///"` as stated and then write `NULL`, which is
FR-010's failure mode arriving by a side door.

**On the create path there is no such problem.** `create_product` is called with all three
unconditionally; `None` there means "uncategorized", which FR-003 says is an ordinary state.

**Alternatives considered**: a sentinel object for "not stated" (rejected — presence already
means that, and a sentinel is machinery for a problem the existing API has already solved);
reading the product first and only writing on a difference (rejected — an extra query and an
extra race for no behavioural gain, since a same-value write is harmless).

---

## 4. Where the category path gets validated

**Decision**: Call `self._validate_category_path(category_path)` near the top of
`capture_order`, beside the existing `self._validate_price(...)` and
`self._validate_purchase_quantity(...)` calls, and pass the canonical result downstream.

**Rationale**: `capture_order` has an explicit contract that a refused capture writes nothing
— "Both questions are worked out before either is raised… Nothing below writes", and
`CaptureDecisionRequired` is documented as leaving "a database this call has not touched". An
over-length path validated only inside `create_product` would be refused *after* the operator
had already answered a duplicate question, which is a worse sequence for the same outcome.
Validating up top puts it with the other input validation and refuses before anything else
happens.

Re-validation downstream is harmless: `canonical(canonical(x)) == canonical(x)`, and the
length check on an already-canonical path is a no-op.

The route already handles the resulting exception. `product_capture` catches `ValidationError`,
flashes `e.message` and re-renders with `form_data=request.form` — so FR-005's rejection and
FR-011's preservation fall out of the existing code once the fields are in the template.

**Alternatives considered**: validating in the route (rejected — Principle II, validation is
service work); letting `create_product` be the only validator (rejected for the sequencing
reason above).

---

## 5. FR-011: surviving the three re-renders

**Decision**: Nothing to build. Verify it.

**Rationale**: All three re-render paths in `product_capture` already pass
`form_data=request.form`:

- `except CaptureDecisionRequired` → duplicate question and recycled-identifier question
- `except ValidationError` → validation failure
- the GET branch passes `form_data=request.args` for the bookmarklet landing

The partial renders `values.get('…') or ''` for each field, so a value the operator typed
comes back. This is a test-only obligation (US3), not an implementation one — which is why
US3 is P3.

---

## 6. FR-013: nothing from a listing may fill these

**Decision**: Add no fallback. Do not touch the `ListingCapture` merge.

**Rationale**: `product_capture` has a deliberate fallback pattern for `manufacturer` and
`unit_price` — `if listing is not None and manufacturer is None: manufacturer = listing.brand`
— and a deliberately absent one for everything else. The three new fields join the second
group. `ListingCapture` carries no category or location field and no selector could produce
one, so the risk is not that a value arrives wrongly but that someone later invents a
heuristic (a category guessed from the vendor's breadcrumb trail). FR-013 exists to say no in
advance.

`_apply_listing` merges specification rows and the description onto the product and is not
touched.

---

## 7. Script loading on the capture page

**Decision**: Add `datalist.js` and `catalog-suggestions.js` to `capture.html`'s
`{% block scripts %}`, before the `field-autocomplete.js` tag that is already there.

**Rationale**: `capture.html:338` already loads `field-autocomplete.js`, which auto-binds
`#location` and `#sub_location` the moment their dropdown divs exist — so US2 scenarios 2 and
3 need no JS change at all. The category datalist is the gap: it is filled by
`catalog-suggestions.js`, which reads `window.WorkshopDatalist` **as it loads**, not on
`DOMContentLoaded`. `add.html:117-119` records the ordering constraint in a comment;
`capture.html` must repeat it.

`catalog-suggestions.js` also loads `/api/tags` into `#tag-suggestions`, which the capture
page does not have. Its `load()` returns early when the datalist is missing, so the extra
call is skipped rather than erroring — no guard needed.

**Alternatives considered**: a capture-specific script (rejected — one `fetch` and two lines,
already written); inlining the category options server-side (rejected — it would diverge from
how the product form gets them, and add a query to a page render).

---

## 8. Testing and the screenshot gate

**Decision**: Unit tests in `tests/unit/test_capture.py` (service) and
`tests/unit/test_product_routes.py` (route), E2E in `tests/e2e/test_order_capture.py`. Run
`nox -s tests`, `nox -s e2e`, and the screenshot verification.

**Rationale**: `test_capture.py` already groups service behaviour by concern
(`TestDescriptionAtCapture`, `TestAttachVsCreate`), and the attach-vs-create distinction is
exactly where FR-009 and FR-010 live — a new `TestFilingAtCapture` class belongs beside them.
`test_order_capture.py` already has a `capture(page, base_url, **fields)` helper that fills
`#{field}` for each keyword argument, so `capture(page, url, category_path='…', location='…')`
works unmodified.

**Screenshots**: the constitution requires regenerating documentation screenshots for any
change under `app/templates/**`, and **this feature does make one stale**.

Screenshots come from two places, and reading only the first is how this gets missed:
`tests/e2e/screenshot_config.yaml` (twenty metal-stock shots, none of them a catalog page)
*and* the `test_screenshot_*` methods in `tests/e2e/test_screenshot_generation.py`, which is
where every product-catalog shot lives. The relevant ones:

| Shot | Source template | Expected |
|---|---|---|
| `user-manual/order_capture.png` | `capture.html` | **Changes** — the page gains a card. Must be regenerated and committed with the change. |
| `user-manual/product_add_form.png` | `add.html` → `_form_fields.html` | **Must not change.** It is the check that the §2 extraction was a faithful move. A diff here means the partial altered the rendered markup. |
| `user-manual/edit_item_form.png` | metal stock `edit.html` | Untouched — the product edit form has no screenshot. |

Regenerate with `nox -s screenshots_headless` and verify with `nox -s screenshots_verify`
(valid PNG, RGB/RGBA, under 500KB). Per Principle IV a test run must leave the working tree
clean, so `nox -s e2e` — which selects `-m "e2e and not screenshot"` — must not be the thing
that rewrites them.

**Alternatives considered**: driving the new fields through a page object (rejected — there is
no capture page object, `test_order_capture.py`'s module-level helpers are the established
pattern in that file, and one feature is not the moment to introduce a fifth page class).
