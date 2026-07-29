---
title: 'Reorder threshold and derived Effective Low'
type: 'feature'
created: '2026-07-29'
status: 'done'
review_loop_iteration: 0
baseline_revision: 'fac9137'
final_revision: '4ff59ee'
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** Story 5.1 landed the tracked count (`products.quantity_on_hand`, `app/database.py:941`) but nothing to compare it against: `reorder_threshold` does not exist (the `Product` docstring still reserves it, `app/database.py:873`), so FR26 is unrealized and FR30's **Effective Low** signal has no home at all — `grep -ri "effective.low" app/ tests/` matches nothing but that reservation comment. AD-6 requires that signal to be derived at read and expressed **exactly once** as a predicate usable both in Python and in a SQL `WHERE`, because Story 5.6's reorder view and Epic 8's stock facet both consume it; there is no precedent for such a predicate in this codebase (the five `@hybrid_property` pairs on `InventoryItem`, `app/database.py:131-220`, are Python-only getters with no `@expression`).

**Approach:** Add one nullable integer column `reorder_threshold` to `products` via a single Alembic revision, accept it on the product create/edit forms through the existing shared validator and service write path, and add `Product.is_effective_low` — a `@hybrid_property` with a matching `@is_effective_low.expression` — as the single home of the FR30 predicate, currently carrying its threshold branch (`quantity_on_hand IS NOT NULL AND reorder_threshold IS NOT NULL AND quantity_on_hand <= reorder_threshold`) with a named, documented seam where Story 5.3 ORs in the stored-status branch. Surface the threshold and the derived signal as two new route-computed rows on the product detail page.

## Boundaries & Constraints

**Always:**
- **One expression of the predicate, and it is `Product.is_effective_low`.** The Python getter and the SQL `@expression` are the only two encodings permitted, they live adjacent in `app/database.py`, and they must agree row-for-row. Any route, template, service query or test that needs the signal reads that property or filters on that expression — a hand-written `quantity_on_hand <= reorder_threshold` anywhere else is a defect (AD-6).
- **The SQL expression must be false, never NULL, for rows that do not qualify**, so that `~Product.is_effective_low` returns exactly the complement. Lead with the two `IS NOT NULL` guards (`FALSE AND NULL` is `FALSE`; a bare `col <= col` on NULLs is `NULL`, and `NOT NULL` is `NULL`, which would silently drop untracked products from a future "not low" query).
- **The Python getter returns a real `bool`** and reads **only mapped scalar columns on `Product`** — never a relationship. `CatalogService.get_product` returns a **detached** instance (`app/mariadb_catalog_service.py:454-469`); touching `product.purchases` there raises `DetachedInstanceError`. This is also why On Order (a `purchases` existence test, Story 5.4) cannot join this property.
- **Evaluating the predicate writes nothing** — no column, no cache, no trigger, no `stock_status` back-write. Reading it must leave the session clean and `products.updated_at` unmoved (AD-6, FR30).
- **Story 5.3's seam is inside this one property.** Its docstring must state, in prose, that the stored-status branch (`stock_status IN ('low','out')`) is Story 5.3's to OR into **these two bodies** and nowhere else, and that until then the property expresses the threshold branch alone. The name is the domain name (`is_effective_low`), not `is_below_threshold` — 5.3 widens the body, never renames the property.
- `reorder_threshold` is a plain nullable `Integer` with no server default, accepted from the forms and from `create_product`/`update_product` like any other field. A blank submission clears it to `NULL`; `NULL` makes the threshold branch false however the quantity reads (FR30).
- **Zero is a legal threshold**, distinct from absent: `reorder_threshold = 0` means "low only when the count reaches 0". So the validator is the shared `_non_negative_int_string` (`app/main/routes.py:845`), and the detail page's threshold string is **route-computed**, never `product.reorder_threshold or '—'` — that would render a stored `0` as absent.
- **The stored bounds/type guard is shared with the quantity path, not copied.** `_apply_quantity_assertion` (`app/mariadb_catalog_service.py:200-289`) already owns "an int or a digit string, `bool` refused, leading zeros stripped, `0 <= n <= 2147483647`"; extract that parse into one module-level helper taking the field name and call it from both branches. `_apply_quantity_assertion`'s observable behaviour — including its two exception messages, which name `quantity_on_hand` — must be byte-identical after the extraction. Per the comment at `app/mariadb_catalog_service.py:193-196`, the service's guard stays deliberately distinct from the route's form grammar; do not merge those two.
- Partial-update rule, unchanged (`app/main/routes.py:3270-3278`): key absent = untouched, key present and blank = clear to `NULL`.
- Add/edit parity: `reorder_threshold` renders on **both** `product/add.html` and `product/edit.html` with the same name, id, `maxlength` and validation, and its rule lives in the shared `_validate_product_form`, not the create-only one. It goes in the existing `Stock & Location` card (`#stock-and-location`) without disturbing the existing ids, the two `*-suggestions` divs, or that anchor.
- Catalog rows are read/written by `CatalogService`; routes hold no ORM/SQL (AD-1/AD-2). Field validation stays in the route validators, coercion in the service (AD-4). Detail-page display strings are finished by the route (AD-5).
- `reorder_threshold` joins `Product.to_dict()` (`app/database.py:974-998`) — that dict is the audit snapshot, and a column missing from it is invisible to the audit log.

**Block If:**
- The single-expression rule cannot be honoured — i.e. a `@hybrid_property`/`@expression` pair cannot serve both `product.is_effective_low` on a detached instance and `session.query(Product).filter(Product.is_effective_low)` without a second hand-written copy of the comparison.
- The migration proves to need anything beyond one `op.add_column` on `products` (a backfill, a constraint, an index, or a change to any other table).

**Never:**
- Do not add `stock_status` or `stock_status_at` (Story 5.3), and do not add any manual-status control, enum, timestamp or display. Do not compute or render On Order or Recently Received (Story 5.4). Do not build a reorder list, view, route or service query method that returns low products (Story 5.6) — this story adds the predicate and its single-product read surface, not the list.
- Do not persist the derived flag: no column, no `to_dict()` key, no cached attribute, no index, no trigger.
- Do not put the signal in `app/templates/product/search.html` or `tag_products.html`, and do not touch `search_products` or its reserved `filters` argument (`app/mariadb_catalog_service.py:2937-2944`, Epic 8's).
- Do not add a JSON endpoint, and therefore no `app/api_client.py` change. Do not add `reorder_threshold` to `_RECEIPT_TRIGGER_FIELDS` (`app/main/routes.py:1364`) or to any receipt path — nothing on the purchase path may write it.
- Do not alter what `quantity_recounted` means or which form carries it; the recount checkbox stays edit-only and has nothing to do with the threshold.
- No `float` anywhere; no `>>>` prompts outside `app/utils/`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Below threshold | `quantity_on_hand=2`, `reorder_threshold=3` | `is_effective_low` is `True` in Python **and** the row is returned by `filter(Product.is_effective_low)`; no column written | No error expected |
| At threshold | `quantity_on_hand=3`, `reorder_threshold=3` | `True` (comparison is `<=`) | No error expected |
| Above threshold | `quantity_on_hand=4`, `reorder_threshold=3` | `False`, and the row is returned by `filter(~Product.is_effective_low)` | No error expected |
| Zero threshold, zero count | `quantity_on_hand=0`, `reorder_threshold=0` | `True` — a stored `0` threshold is a threshold | No error expected |
| Zero threshold, stock on hand | `quantity_on_hand=1`, `reorder_threshold=0` | `False` | No error expected |
| No threshold | `quantity_on_hand=0`, `reorder_threshold IS NULL` | `False` — the threshold branch is false, not "low because empty" (FR30) | No error expected |
| Untracked with a threshold | `quantity_on_hand IS NULL`, `reorder_threshold=3` | `False`; the row appears in `filter(~Product.is_effective_low)`, not lost to a NULL | No error expected |
| Neither set | both `NULL` (a freshly created Product) | `False` | No error expected |
| Evaluation is read-only | Any Product, property read then session inspected | `session.dirty` empty, `updated_at` unchanged, no `UPDATE` issued | No error expected |
| Create with a threshold | `POST /products/add` with `reorder_threshold=3` | Column = `3`; detail shows `3` | No error expected |
| Set on edit | Edit posts `reorder_threshold=3` | Column = `3` | No error expected |
| Clear on edit | Edit posts `reorder_threshold=''` | Column = `NULL`; detail row shows `—`; quantity columns untouched | No error expected |
| Key absent | Edit body has no `reorder_threshold` key | Column untouched | No error expected |
| Leading zeros | Form posts `reorder_threshold=007` | Column = `7` (magnitude, not digit count) | No error expected |
| Bad threshold | `reorder_threshold` = `-1`, `2.5`, `1_0`, `٥`, `abc`, `0`×5000, or > 2147483647 | Form re-renders 200 with a keyed error; nothing written | Keyed `validation_errors['reorder_threshold']` |
| Bad caller value | `update_product(id, reorder_threshold=2.9)` or `=True` | Refused with `TypeError`/`ValueError`; `update_product` returns `False` and logs; nothing written | Service-level raise, caught by the existing except-log handler |
| Detail rendering, low | Tracked `2`, threshold `3` | `Reorder threshold` row reads `3`; `Reorder signal` row reads `Low stock` | No error expected |
| Detail rendering, not low | Tracked `4`, threshold `3` | `Reorder threshold` reads `3`; `Reorder signal` reads `—` | No error expected |
| Detail rendering, zero threshold | Threshold `0` | `Reorder threshold` row reads `0`, not `—` | No error expected |
| Receipt untouched | Recording/receiving a Purchase for a Product with a threshold | `reorder_threshold`, `quantity_on_hand` and `quantity_verified_at` all unchanged | No error expected |

</intent-contract>

## Code Map

- `app/database.py:862-998` -- `Product`: add `reorder_threshold` beside the Story 5.1 stock columns (`:941-942`), extend `to_dict()` (`:974-998`), amend the docstring reservation at `:870-874` (drop `reorder_threshold`, keep `stock_status`/`stock_status_at` for Story 5.3). `:12` already imports `hybrid_property`; `:131-220` are the existing (Python-only) hybrid pairs to match stylistically — this story adds the first `@expression` in the repo. `:960-968` `__table_args__` — no index is added.
- `migrations/versions/2c837402a89a_add_product_stock_and_location.py` -- current HEAD and the style reference (prose docstring naming the story/FRs, typed revision identifiers, bare `op.add_column`, mirrored `op.drop_column`, explicit "metal stock untouched" note). New revision chains `down_revision = '2c837402a89a'`.
- `app/mariadb_catalog_service.py:42-62` `_PRODUCT_FIELDS` and its per-exclusion comment; `:193-197` the bound constant and its "deliberately duplicated in `routes._MAX_INT32`" rationale; `:200-289` `_apply_quantity_assertion` (the parse to extract is `:270-283`); `:495-499` `create_product` (keyword-only, one parameter per field, constructor call `:540-556`); `:628-693` `update_product` and its `**fields` loop — note `:691-692` `else: cleaned = _clean(value)` passes strings through unparsed, which is why the threshold needs its own branch; `:157-193` `_clean`.
- `app/main/routes.py:799-813` `_PRODUCT_FIELD_LIMITS` (string lengths only — the threshold does not belong there); `:842` `_MAX_INT32`; `:845-880` `_non_negative_int_string`; `:917-1013` `_validate_product_form` with Story 5.1's quantity rule at `:986-1012` as the pattern to follow; `:1240-1268` `_product_form_data`; `:1601-1655` `product_add` (service call `:1636-1655`); `:3183-3298` `product_edit` (present-keys loop `:3270-3278`, re-render closure `:3225-3255`); `:1774-1788` `_QUANTITY_UNTRACKED_DISPLAY` / `_product_quantity_display`; `:1791-1832` `product_detail` (the two Story 5.1 precomputed values at `:1826-1832`).
- `app/templates/product/add.html:128-186` and `app/templates/product/edit.html:117-190` -- the `Stock & Location` card; `edit.html:25` `keyed_error_fields`; `edit.html:121-126` is the input markup style reference.
- `app/templates/product/detail.html:63-92` -- the `<dl class="row">` tail: the quantity row (`id="product-quantity"`, whose scraped text tests pin — do not add anything inside it), the location row, then Notes.
- `tests/unit/test_product_model.py:15-35` -- `_make_session` plus the literal `cols == {…}` set assertion that must gain the new column; the natural home for the SQL-expression tests.
- `tests/unit/test_catalog_service.py:3842-4188+` -- `_stored_stamp`/`_backdate_stamp` helpers and `TestProductQuantityWriteContract`; `catalog_service` fixture at `:17`.
- `tests/unit/test_product_routes.py:105-128` -- `_rendered_edit_form`'s hard-coded field tuple (`:109-118`) which every new edit input must join; `:6001-6011` `_detail_field`; classes at `:6035`, `:6260`, `:6469`.
- `tests/e2e/test_product_stock.py` -- Story 5.1's e2e (helpers `_add_product` `:73`, `_set_quantity` `:85`); this story extends it.
- `docs/user-manual.md:694-698` (what a Product is), `:737-738` (add walkthrough step 5), `:771-835` `#### Stock and Location`, `:1509-1545` `### Editing a Product`, `:1554-1556` troubleshooting table.

## Tasks & Acceptance

**Execution:**
- [x] `app/database.py` -- add `reorder_threshold = Column(Integer, nullable=True)` to `Product` next to the Story 5.1 stock columns; add it to `to_dict()`; update the class docstring so it reserves only `stock_status`/`stock_status_at` (Story 5.3) and `equivalent_group_id` (Epic 10) -- the audit log is blind to columns missing from `to_dict()`.
- [x] `app/database.py` -- add `Product.is_effective_low` as a `@hybrid_property` plus `@is_effective_low.expression` pair: the FR30 predicate's single home. Getter returns a plain `bool` from mapped scalars only; expression returns `and_(cls.quantity_on_hand.isnot(None), cls.reorder_threshold.isnot(None), cls.quantity_on_hand <= cls.reorder_threshold)` so non-qualifying rows are FALSE rather than NULL and `~` is a true complement. The docstring carries AD-6 (derived at read, never stored), why both encodings exist (Story 5.6 and Epic 8's facet filter in SQL; the detail page reads it in Python off a detached instance), why no relationship may be touched here, and that Story 5.3's stored-status branch is ORed into **these two bodies** and nowhere else.
- [x] `migrations/versions/<rev>_add_product_reorder_threshold.py` -- one `op.add_column('products', sa.Column('reorder_threshold', sa.Integer(), nullable=True))` and its `op.drop_column`, `down_revision = '2c837402a89a'`; docstring states the story, FR26/FR30, that the signal it feeds is derived and gets no column, and that metal-stock tables are untouched.
- [x] `app/mariadb_catalog_service.py` -- extract the type/bounds/leading-zero parse from `_apply_quantity_assertion` into one module-level helper parameterised by field name (rename the bound constant so it no longer reads as quantity-only, updating its comment to name both columns); `_apply_quantity_assertion` keeps its exact current behaviour and messages. Add `'reorder_threshold'` to `_PRODUCT_FIELDS`, a `reorder_threshold` keyword-only parameter to `create_product`, and a branch in `update_product`'s field loop that maps blank/None to `NULL` and anything else through the shared parse -- the `else: _clean(value)` fallthrough would store the raw string `'3'` in an `Integer` column (SQLite keeps it as text, so a later comparison would be wrong).
- [x] `app/main/routes.py` -- validation: add a `reorder_threshold` rule to the **shared** `_validate_product_form`, modelled on the quantity rule at `:986-1012` (blank is not an error -- blank means no threshold), message naming the bound and what blank means.
- [x] `app/main/routes.py` -- write path: seed `reorder_threshold` in `_product_form_data` (`'' if None else str(...)`, never `or ''` -- a stored `0` is falsy), pass it from `product_add`, and add it to `product_edit`'s present-keys tuple so absent-vs-blank semantics hold.
- [x] `app/main/routes.py` -- read path: `product_detail` computes and passes the finished threshold string (`—` when NULL, the number otherwise -- including `0`) and `effective_low=product.is_effective_low`; no comparison is written in the route.
- [x] `app/templates/product/add.html`, `app/templates/product/edit.html` -- add a `Reorder Threshold` control to the `Stock & Location` card on both forms (same name/id/`maxlength`/`is-invalid`+`invalid-feedback` pattern as `quantity_on_hand`), regridding the card so four fields lay out cleanly at 360 px upward without changing the `#stock-and-location` anchor, the existing ids or the two suggestion divs; extend the shared card help text with what blank means and that a threshold only signals for a tracked quantity; add `reorder_threshold` to `edit.html`'s `keyed_error_fields`.
- [x] `app/templates/product/detail.html` -- add two rows after the quantity row: `Reorder threshold` (`id="product-reorder-threshold"`, route string) and `Reorder signal` (`id="product-effective-low"`, a `Low stock` badge when `effective_low` else `—`). Do not add anything inside `#product-quantity` -- its rendered text is pinned by Story 5.1 tests. Comment states the template neither computes nor compares.
- [x] `tests/unit/test_product_model.py` -- extend the exact-column-set assertion; cover `reorder_threshold` NULL by default, persisting `0` distinctly from `None`, and its presence in `to_dict()`; cover the predicate on both sides: every Python row of the I/O matrix, the same rows through `session.query(Product).filter(Product.is_effective_low)`, the complement through `filter(~Product.is_effective_low)` (untracked and NULL-threshold rows must be present there, not dropped), and that reading the property leaves the session clean and `updated_at` unmoved.
- [x] `tests/unit/test_catalog_service.py` -- cover the write contract: create with and without a threshold, set/clear/absent-key on update, `0` stored as `0`, leading zeros, a float/bool/oversize caller value refused with `update_product` returning `False` and nothing written, the threshold present in the audit snapshot, and that writing a threshold touches neither quantity column nor its stamp. Add a tripwire that the shared parse extraction did not change `_apply_quantity_assertion`: its refusals still name `quantity_on_hand`.
- [x] `tests/unit/test_product_routes.py` -- add `reorder_threshold` to `_rendered_edit_form`'s field tuple; cover add/edit parity of the control, round-trip of a typed value, every bad-input row of the matrix re-rendering 200 with a keyed error and no write, blank clearing to NULL, and the three detail-row cases (low, not low, zero threshold) via `_detail_field`. Include the re-post regression: take the rendered edit form verbatim, change only `description`, re-post, and assert the threshold is unchanged.
- [x] `tests/e2e/test_product_stock.py` -- extend: set a threshold above the tracked count and see `Low stock` on the detail page, raise the count above the threshold and see it clear, clear the threshold and see it clear, and confirm an untracked product with a threshold never shows the signal.
- [x] `docs/user-manual.md` -- document Reorder Threshold in `#### Stock and Location` (what blank means, that `0` is a real threshold, that it only signals when a quantity is tracked, and that the signal is computed when the page is drawn and never stored), name the two new detail-page rows where the page is described, cross-reference it from `### Editing a Product`, and add a troubleshooting row quoting the new validator message verbatim.

**Acceptance Criteria:**
- Given a Product with tracked quantity 2, threshold 3, when Effective Low is evaluated through the single predicate in Python or in a SQL `WHERE`, then both say low and no stored column changes (FR26, FR30, AD-6).
- Given a Product with a `NULL` reorder threshold, when Effective Low is evaluated, then the threshold branch is false however the quantity reads (FR30).
- Given the finished implementation, when the codebase is searched for a `quantity_on_hand`/`reorder_threshold` comparison, then it appears only inside `Product.is_effective_low`'s two bodies (AD-6 single-sourcing).
- Given a threshold entered on either the add or the edit form, when the Product is saved and re-opened, then the value round-trips into the form and onto the detail page, and a blank submission clears it.
- Given `nox -s tests` and `nox -s doctests`, when they run, then they pass with no new warnings and no marker or doctest-scope violations.

## Spec Change Log

## Review Triage Log

### 2026-07-29 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 0, low 6)
- defer: 1: (high 0, medium 0, low 1)
- reject: 10: (high 0, medium 0, low 10)
- addressed_findings:
  - `[low]` `[patch]` `_parse_stored_count`'s new docstring claimed every refusal names the field the caller passed; two did not. `int()` is not total over strings — a non-numeric one and an all-digit one still past CPython's 4300-digit ceiling both escaped as CPython's own wording, naming neither the field nor the fact that an argument was wrong, into a handler whose only other output is a generic failure. Both now raise the field-named refusal, with the offending value truncated so a 5000-character submission does not land in the audit log. The two messages the story pins byte-identical are untouched. Pinned by `test_a_string_int_itself_gives_up_on_is_refused_by_field_name`, `test_a_refusal_does_not_quote_the_whole_submission_back` and `test_zero_padding_is_still_the_magnitude_it_names`.
  - `[low]` `[patch]` `create_product`'s new comment claimed the threshold parse "keeps a bad caller value out of the retry loop entirely"; the call is *inside* the internal-id retry loop and is re-evaluated on every attempt. The behaviour is right for a reason the comment did not give — it raises on the first pass, before any flush — and a comment asserting a structure the code does not have is one that survives a refactor and then lies. Reworded to state the actual guarantee.
  - `[low]` `[patch]` `is_effective_low`'s docstring forbade reading a relationship and read as exhaustive. A column left unloaded fails identically on the detached instance `get_product` returns, and the likeliest place someone reaches for `load_only()`/`defer()` is exactly the anticipated consumer, Story 5.6's catalog-wide reorder list. Rule restated as "loaded scalar columns", naming the projection case.
  - `[low]` `[patch]` The 5.3 seam was marked prominently in code and nowhere in prose, while `docs/user-manual.md` now states today's rule to the operator exhaustively ("a product with no threshold never reads low") — a sentence Story 5.3 makes false. The seam docstring now names the manual section that has to widen with it.
  - `[low]` `[patch]` Both templates' regrid comments claimed a pairing that only `add.html` actually gets: on `edit.html` the recount checkbox and its help text sit inside the quantity column, so the threshold beside it is followed by whitespace down to the locations. The comments also justified only 360 px and `md`+, silently skipping the one band the change costs something in — 576–767 px, where the two location inputs go from full width to half. Both now state the lopsided pair, the narrowed band, and why a fourth `md` column was rejected.
  - `[low]` `[patch]` One concept wears four names (`is_effective_low`, `product-effective-low`, "Reorder signal", "Low stock") and every assertion located by id, so swapping the two `<dt>` labels would have left the suite green while the page contradicted the user manual. Pinned by `test_each_row_carries_the_label_the_manual_promises`, which asserts each label immediately precedes its own `<dd>`.
  - `[low]` `[patch]` The SQL half of the single-sourced predicate was exercised only on SQLite, while its stated consumers (Story 5.6, Epic 8) filter in MariaDB — and the hazard justifying the `reorder_threshold` write branch is SQLite-specific, so the engine proving the branch necessary was not the engine running the comparison. Added `tests/integration/test_effective_low_predicate.py`: the same matrix through `filter(...)`, through `~filter(...)`, as a partition, and row-for-row against the Python getter, on the live MariaDB container.

### 2026-07-29 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 0, low 5)
- defer: 1: (high 0, medium 0, low 1)
- reject: 4: (high 0, medium 0, low 4)
- addressed_findings:
  - `[low]` `[patch]` The previous pass truncated the value quoted back by one of `_parse_stored_count`'s refusals and left its sibling untouched, so the guarded path was the one no operator can reach while the unguarded one took whatever a service caller passed. Both remaining inlets were live: a digit string *under* CPython's 4300-digit ceiling parses cleanly and fails only the bounds check, producing a 4056-character exception that `create_product`/`update_product` hand to `log_audit_operation` as `error_details` verbatim; and an `int` argument has no ceiling at all, so rendering one past 4300 digits raised CPython's `Exceeds the limit` from *inside* the f-string building the refusal — the field-named message was never constructed, which is the exact escape the docstring claimed to have closed. Both cuts now go through one `_truncated_for_refusal` helper, the huge-int render is guarded, and the docstring says three rather than two. The two messages the story pins byte-identical are unchanged (re-verified). Pinned by `test_the_bounds_refusal_is_bounded_too`.
  - `[low]` `[patch]` `product_edit`'s `_render_data()` carries the only durable record of which fields a degraded re-render can wipe, and it enumerates them by name. `reorder_threshold` joined the present-key clearing loop in this story and was never added to that list — and it is the member that fails most quietly: the value is retypeable, but nothing on the page afterwards says a threshold used to be there, and the only symptom is a low-stock signal that stops arriving. Enumerated, with the rule that a field added to the loop belongs in the list.
  - `[low]` `[patch]` The extraction tripwire pinned the two refusals the story required to stay byte-identical — and not the third, the one the extraction actually *added*, which was asserted only for `reorder_threshold`. A field-name crossover confined to that branch would have made every quantity refusal blame the wrong column while the whole suite stayed green, which is precisely the failure the tripwire's own docstring describes. Now pinned for `quantity_on_hand` too.
  - `[low]` `[patch]` The story's third acceptance criterion is a grep-shaped structural invariant — the comparison appears only inside `is_effective_low`'s two bodies — and every docstring around the predicate repeats it, while nothing enforced it. Both moments a second copy becomes tempting are still ahead (Story 5.3 widens the bodies, Story 5.6 adds the first query consumer). Added `TestTheComparisonHasExactlyOneHome`: an AST walk over `app/**/*.py` for any comparison naming both columns, asserting the only two sites are `Product.is_effective_low`, plus a Jinja-delimiter scan of the templates. Verified to trip on a synthetic duplicate rather than passing vacuously; its docstring states what a structural test cannot catch.
  - `[low]` `[patch]` The integration matrix's comment claimed the duplicated rows were an "INDEPENDENT statement of the expected answers", but they are a transcription — a wrong answer copied in is wrong in both tiers, and one author touching both files in a sitting defeats the separation. Reworded to claim only what it buys (drift protection), and to stop implying the encodings' agreement rests on it: `test_the_expression_agrees_with_the_getter_row_for_row` compares the implementations directly and never reads the table.

## Design Notes

**Why the property lives on the ORM class rather than in the service.** AD-6 asks for "a single SQLAlchemy hybrid expression / service method usable in both Python and SQL `WHERE`". A service method can be one or the other, not both; a hybrid is both by construction, and it is the only shape that lets Story 5.6 and Epic 8's facet filter in the database instead of loading the catalog and filtering in Python. Queries still live in the service (AD-1/AD-2) — this story adds none; `product_detail` reads the property off the instance the service already returned, which is an attribute read, not a query.

**Why the `IS NOT NULL` guards are load-bearing in SQL and not merely parallel to Python.**

```python
@is_effective_low.expression
def is_effective_low(cls):
    return and_(cls.quantity_on_hand.isnot(None),
                cls.reorder_threshold.isnot(None),
                cls.quantity_on_hand <= cls.reorder_threshold)
```

Without them a NULL column makes the comparison NULL; `WHERE NULL` filters the row out, so `filter(...)` looks right, but `filter(~...)` is `WHERE NOT NULL` — also NULL — and the untracked products silently vanish from "everything that is not low". With the guards leading, `and_` short-circuits to FALSE and negation is a true complement.

**Why the parse is extracted rather than copied.** `_apply_quantity_assertion` already owns the rule that a stored count is an int or digit string, is not a `bool`, has its leading zeros stripped before `int()` (CPython refuses digit strings longer than 4300), and fits `0 <= n <= 2147483647`. The threshold column has exactly those properties. Copying the rule is how the two columns come to disagree; the extraction keeps one home, and the field name is a parameter only so the refusal message names the field the caller actually passed.

**Story 5.3's seam.** The stored-status branch is `stock_status IN ('low','out')` per AD-6. It is one `or_` term in each body plus one `or` in the getter, added when the column exists. Naming the property for the signal now — not for the threshold comparison it currently is — is what makes that a widening rather than a rename with call sites to chase.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all pass (~3640 selected today), including the new model/service/route tests.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: unchanged (25 passed); this story adds no `app/utils/` module.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` -- expected: pass (needs a 20-minute tool timeout; revert any screenshots the session rewrites).
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s integration` -- expected: pass; `test_migrated_schema_matches_the_orm_metadata` and the downgrade test cover the new revision automatically. Requires Docker — if unavailable, say the migration round-trip was not executed rather than claiming it passed.

**Manual checks (if no CLI):**
- `venv/bin/python manage.py db upgrade` then `db downgrade -1` against a scratch database -- the column appears and disappears.


## Auto Run Result

Status: `done` — follow-up review pass over the committed story. Two independent adversarial passes, five low-severity patches applied, one item deferred (DW-250), four rejected. No intent gap and no spec defect: the implementation still matches the contract, and nothing was re-derived.

**Implemented change (unchanged from the prior pass):** `products.reorder_threshold` (nullable `Integer`, one Alembic revision chained on `2c837402a89a`) plus `Product.is_effective_low` — a `@hybrid_property` with a matching `@expression`, the repo's first — as the single home of FR30's Effective-Low predicate, derived at read and never stored (AD-6). The threshold is accepted on both product forms through the shared validator and the service write path, and the detail page carries two route-computed rows.

**Files changed in this pass:**
- `app/mariadb_catalog_service.py` — the bounds refusal in `_parse_stored_count` now renders its value through the new shared `_truncated_for_refusal` helper and guards the int-too-large-to-render case; docstring corrected from two escaping refusals to three. The two messages the story pins byte-identical are untouched.
- `app/main/routes.py` — comment only: `reorder_threshold` added to `product_edit`'s degraded-render hazard enumeration.
- `tests/unit/test_product_model.py` — new `TestTheComparisonHasExactlyOneHome`, the AST + template tripwire enforcing the story's third acceptance criterion.
- `tests/unit/test_catalog_service.py` — `test_the_bounds_refusal_is_bounded_too` (both inlets), and the extraction tripwire extended to pin the added branch under `quantity_on_hand`.
- `tests/integration/test_effective_low_predicate.py` — comment only: the matrix-duplication rationale reworded to claim only drift protection.
- `_bmad-output/implementation-artifacts/deferred-work.md` — DW-250 appended.

**Review findings breakdown:** 5 patches applied (all low: one real code defect with two live escape routes, two test-coverage gaps, two comment/docstring accuracy corrections). 1 deferred (DW-250: the SQL expression is advertised to Story 5.6 and Epic 8 as a database-side filter, but an inter-column comparison under a `NOT` is not indexable as written and neither column carries an index — correctly out of scope here, previously unrecorded). 4 rejected: the service parse accepting `'+3'`/`'1_0'`/`'٥'` where the form rule refuses them (deliberate and settled in Story 5.1 — the service owns type and bounds, the route owns the typed grammar; the wording predates this story and one of the two messages is pinned byte-identical by the story's own `Always` clause), the missing user-manual note that duplicating a product drops the threshold (DW-249 already defers the underlying product decision, and either resolution falsifies text written now), the legacy same-name `@expression` spelling in place of SQLAlchemy 2.0's `hybrid_property.inplace` (works, raises no deprecation warning, and the repo runs no type checker — a cosmetic rewrite of covered working code), and the `Reorder signal: —` row conflating "no threshold set" with "comfortably above threshold" (spec-prescribed: the I/O matrix pins `—` for the not-low case and the Tasks prescribe two rows, so changing it is a design decision, not a defect).

**Verification performed:**
- `nox -s tests` — **3713 passed, 2 skipped, 487 deselected, 3 warnings** (41s). Up 4 from the prior pass's 3709: two tripwire tests and two parametrized bounds tests. Warning count is the unchanged pre-existing baseline.
- `nox -s doctests` — **25 passed**; this pass adds no `app/utils/` module.
- `nox -s integration` — **57 passed (8:00)** against the MariaDB testcontainer, including the four predicate tests and the migration round-trip.
- The two fixed escape routes were reproduced before the change (a 4056-character exception, and CPython's `Exceeds the limit` in place of the field-named refusal) and re-checked after, alongside a byte-identical re-verification of the two pinned `quantity_on_hand` messages.
- The new tripwire was verified to trip on a synthetic duplicate comparison rather than passing vacuously.
- `nox -s e2e` was **not re-run** this pass, and no e2e result is claimed for it. The prior pass ran it green (429 passed, 1 skipped); this pass changed no template, no rendered markup and no reachable route behaviour — the `routes.py` diff is comment-only (verified: no non-comment line changed), and the service change affects only refusal text on inputs the form's 10-digit cap makes unreachable.

**Residual risks:**
- Carried forward unchanged from the prior pass: the intent contract's I/O matrix lists `'0' × 5000` among the "Bad threshold" inputs, contradicting its own `Always` rule and Design Notes; `is_effective_low` ships as the domain name for a predicate currently expressing one of its two branches; the user manual states the signal's rule exhaustively and Story 5.3 falsifies two of its sentences; screenshots were not regenerated despite the earlier template changes.
- `_apply_quantity_assertion`'s behaviour is not in fact byte-identical to its pre-extraction state, as the story's `Always` clause requires: a non-numeric string now raises a field-named refusal where CPython's `invalid literal for int()` used to escape. That deviation was a deliberate patch in the prior pass and is recorded there; it is restated here because the contract text still says byte-identical and was never amended, so a future reader comparing the two will find a real discrepancy rather than a documented one.
- The new comparison tripwire asserts structure, not meaning. A duplicate that assigns the columns to locals first, or reaches them through `getattr`, passes it. Its docstring says so.
