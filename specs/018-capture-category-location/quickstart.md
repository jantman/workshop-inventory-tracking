# Quickstart: validating Category and Location on the Capture Page

Prerequisites: the repository virtualenv at `venv/`, Docker running (the E2E session brings up
MariaDB), and `python3.13` reachable on `PATH`.

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
```

Invoke the venv binaries by path; do not activate.

---

## 1. Automated checks

```bash
venv/bin/nox -s tests            # unit suite, seconds
venv/bin/nox -s e2e              # Playwright; allow a 15-minute tool timeout
venv/bin/nox -s screenshots_verify
git status --short                # MUST be clean after any test session
```

`nox -s e2e` runs well past the ten-minute Bash cap in this environment — run it detached and
poll, rather than in the foreground.

**Screenshots**: this feature edits `app/templates/**`, which the constitution ties to
screenshot regeneration — and one shot really does go stale.

```bash
venv/bin/nox -s screenshots_headless   # regenerates; do NOT skip
venv/bin/nox -s screenshots_verify
git diff --stat docs/images/screenshots/
```

Expect exactly one changed file: `user-manual/order_capture.png`, because the capture page
gains a card. Commit it with the change. **`user-manual/product_add_form.png` must come back
unchanged** — it is generated from `add.html` through `_form_fields.html`, so a diff there
means the partial extraction altered the rendered markup and is a bug, not a screenshot to
accept. (The catalog shots are produced by the `test_screenshot_*` methods in
`tests/e2e/test_screenshot_generation.py`, not by `screenshot_config.yaml`.)

---

## 2. Manual walkthrough

```bash
venv/bin/flask run --debug        # then open http://localhost:5000/products/capture
```

### US1 — file a product while capturing it

1. Paste any listing URL, e.g. `https://www.amazon.com/dp/B0ABCDEFGH`.
2. Fill **Category** `electronics/passives/resistors`, **Storage Location** `Shelf A`,
   **Sub-Location** `Bin 3`.
3. Capture. You land on the receive screen.
4. Open the product. All three read back. **No second visit was needed** — that is SC-001.

Then repeat leaving all three blank: the product is created uncategorized and unlocated, with
no warning (FR-003), and the capture is indistinguishable from today's (SC-003).

### US2 — the shared vocabularies

1. Focus **Category**: the paths already in use appear (they come from `/api/categories`).
2. Type into **Storage Location** the first letters of a location recorded on a *metal stock*
   item and on no product. It is offered — `VocabularyService` reads both tables (SC-002).
3. With a location set, type into **Sub-Location**: only the sub-locations recorded under that
   location are offered.
4. Type something in none of the lists. It is accepted — suggestions never restrict (SC-005).

### US3 — the filing survives a question

1. Capture a listing once.
2. Capture the *same* listing again, this time with all three fields filled in.
3. The duplicate question comes back. **All three fields still hold what you typed** (FR-011).
4. Acknowledge and capture. The product is filed with those values.

Repeat with a category path longer than 512 characters: the page comes back with the error
flashed and the three fields as typed — rejected, not truncated (FR-005).

### FR-009 / FR-010 — attaching to an existing product

1. Capture vendor item `B0ABCDEFGH` with location `Shelf B`. A product is created and filed
   there.
2. Capture the same item id again with a *different* manufacturer, so the recycled-identifier
   question is raised. Set location `Shelf A`, answer "attach to the existing product".
3. The product's location is now `Shelf A` — the operator is holding the thing (FR-009).
4. Capture it a third time with the location field **blank** and attach again. The location is
   still `Shelf A`: blank is "I am not saying", not "erase it" (FR-010).

Step 4 is the one that fails if the three keys are passed to `update_product` unconditionally.
It is the single most important manual check in this document.

---

## 3. Waiting, for the E2E tests

`tests/e2e/test_order_capture.py`'s `capture(page, base_url, **fields)` helper fills `#{field}`
for each keyword argument, so `capture(page, url, category_path='...', location='...')` needs
no new plumbing.

Conditions to wait on, per `CLAUDE.md`:

- **The capture POST** — `capture()` already settles on `domcontentloaded`; assert on an element
  of the page you landed on (`#receive-vendor` for success, `#duplicate-warning` or
  `#identifier-warning` for a question). Never assert on the absence of something before the
  page that would contain it has been established.
- **Reading a filed product back** — `expect(page.locator("#product-category")).to_have_text(...)`
  on the detail page. `product-category` is rendered only when `product.category_path` is set,
  so its presence *is* the assertion; do not snapshot it with `text_content()`.
- **Suggestions** — `field-autocomplete.js` debounces 200 ms and then fetches. Wait for an
  option inside `#location-suggestions` with `expect(...)`, which polls; a fixed wait in front
  of `count()` is the load-bearing-cushion mistake (`CLAUDE.md` pattern E).
- **Seeding** — use `live_server.add_test_data([...])` to plant the metal-stock item whose
  location US2 scenario 2 expects to be suggested. Driving the Add Item form for that costs
  three seconds and tests nothing this feature changed.

## 4. What is not exercised here

No migration to apply (`data-model.md`: no schema change), no new endpoint to smoke-test, and
`/api/capture`'s JSON request shape is unchanged — the three fields exist only on the
confirmation form.
