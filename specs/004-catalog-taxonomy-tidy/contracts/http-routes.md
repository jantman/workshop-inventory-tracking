# Contract: HTTP surface

New and changed routes. All new routes live on the `product` blueprint (`app/product/routes.py`) and stay thin: parse the form, call one service method, flash, redirect. No ORM query or raw SQL in a route (Principle II).

---

## New pages

### `GET /products/tags`

The tags in use, with product counts, and a rename control per row. Satisfies FR-013 — near-duplicate spellings cannot be corrected until they can be seen next to each other.

Renders `product/tags.html` from `CatalogService.tag_list_with_counts()`. Structured like `product/categories.html`: a `list-group` of rows, each carrying the tag name, a count badge, a link to the catalogue filtered by that tag, and a rename button. Tags carried by no product are shown with a count of 0.

Each row exposes its name and count as data attributes so the shared rename modal can read them without a round trip.

### `GET /products/categories` *(existing — changed)*

Gains a rename control per row. The rendered rows already carry path, depth, name and direct count; each row additionally exposes its path and count as data attributes for the modal.

---

## New form handlers

Both accept `application/x-www-form-urlencoded`, require the CSRF token (already wired for every product form), flash a result, and redirect back to the listing. Neither returns JSON — these pages are server-rendered and the rest of the blueprint's non-scan surface works this way.

### `POST /products/categories/rename`

| Field | Meaning |
|---|---|
| `csrf_token` | Standard. |
| `old_path` | The category being renamed. |
| `new_path` | What it becomes. |

**Success** → flash `success`, redirect to `GET /products/categories`. The message states the old name, the new name, and how many products moved.

**`ValidationError`** → flash `error` with the exception's message, redirect to the same page. Nothing changed; the operator sees the tree exactly as it was.

The service is authoritative here. The modal's client-side conflict check is a courtesy, and a page rendered before someone else's change is still refused correctly.

### `POST /products/tags/rename`

| Field | Meaning |
|---|---|
| `csrf_token` | Standard. |
| `old_name` | The tag being renamed. |
| `new_name` | What it becomes, or the tag to merge into. |

**Success** → flash `success`, redirect to `GET /products/tags`. The message distinguishes a rename from a merge and states how many products moved.

**`ValidationError`** → flash `error`, redirect. Nothing changed.

---

## Changed endpoint (behaviour only)

### `GET /api/inventory/field-suggestions/<field>`

**Path, query parameters, response shape and status codes are unchanged.** `field-autocomplete.js` and the metal stock forms need no edit.

```json
{"success": true, "field": "vendor", "suggestions": ["Amazon", "McMaster-Carr"]}
```

What changes: for `location`, `sub_location` and `vendor`, the values now come from the catalogue as well as from metal stock. `thread_size` and `purchase_location` are unaffected. The route body changes only in which service it constructs — `VocabularyService` instead of the inventory service — and keeps its existing `ValueError` → 400 and `Exception` → 500 handling.

The `inventory` segment in the path is historical. It is deliberately not renamed: doing so would touch a route, two templates, a JS file and its e2e tests for no user-visible gain. See decision D10 in `../research.md`.

---

## Changed forms

Four inputs gain the autocomplete dropdown element and the script that binds it. No JavaScript is written — `field-autocomplete.js:218-240` already binds these ids on DOM ready and skips any target whose dropdown is absent.

| Template | Input | Field | Notes |
|---|---|---|---|
| `product/_form_fields.html` | `#location` | `location` | |
| `product/_form_fields.html` | `#sub_location` | `sub_location` | New field; scoped by `#location`, which the component already does for this id pair |
| `product/purchase_add.html` | `#vendor` | `vendor` | |
| `product/capture.html` | `#vendor` | `vendor` | |

The markup is the pattern already used at `inventory/add.html:253-261`: a `position-relative` wrapper around the input plus a sibling `<div id="{id}-suggestions" class="dropdown-menu position-absolute w-100">`. `product/add.html` and `product/edit.html` add a `<script>` tag for `field-autocomplete.js` alongside the `catalog-suggestions.js` they already include.

`product/add.html`'s `#identifier_vendor` is a different field — the vendor an *identifier* belongs to, not a purchase vendor — and is out of scope.

---

## New static asset

### `app/static/js/taxonomy-rename.js`

Drives the shared rename modal on both the categories and tags pages. A plain IIFE matching `catalog-suggestions.js` — no framework, no build step.

Responsibilities:

1. On rename-button click, populate the modal from the row's data attributes and pre-fill the target with the current name.
2. As the target is typed, report the impact from data already on the page: for categories, the sum of the counts of the source path and its descendants; for tags, the source's count, and whether the target name matches an existing tag (a merge) or not (a rename).
3. Warn — before submit — when the target collides in the way the server will refuse.
4. Submit the form. The server re-validates and its answer is the one that counts.

It performs no fetch. Everything it needs is rendered on the page.

---

## Not built

- No preview or dry-run endpoint. See D7 in `../research.md`.
- No category *merge*. FR-004 requires refusal.
- No redirect or alias for a renamed category or tag; an old bookmark stops matching, which the spec accepts.
- No delete for a category or a tag. Categories cannot be empty by construction, and orphan tags are already documented as harmless.
