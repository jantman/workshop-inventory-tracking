# Contract: Writing E2E Tests

**Feature**: `specs/002-e2e-test-performance` | **Date**: 2026-08-05 | **Satisfies**: FR-016, FR-017

The e2e suite's interface is not an API — it is the set of rules a test must follow to be fast and
reliable. This document is that contract, and the normative source for the documentation updates in
C6 (`CLAUDE.md`, `docs/development-testing-guide.md`, `_bmad-output/project-context.md`).

Every rule here traces to a measurement in [research.md](../research.md).

---

## Rule 1 — Wait for state, never for a duration

**Do not use `page.wait_for_timeout(...)` or `time.sleep(...)`.**

Measured cost of ignoring this: **423.9s across 479 executions**, 47.7% of test-body time.

A fixed delay is always one of two things: unnecessary, because the condition was already met — or
unreliable, because a slower machine will miss it. Both are defects.

Use Playwright's auto-waiting assertions, which poll until the condition holds or the timeout
expires:

```python
# WRONG — costs 1s every time, and still races on a slow machine
page.click("#submit-btn")
page.wait_for_timeout(1000)
assert page.locator("#result").is_visible()

# RIGHT — returns the moment the condition is true
page.click("#submit-btn")
expect(page.locator("#result")).to_be_visible()
```

Common conditions and how to wait for them:

| Waiting for | Use |
|---|---|
| An element to appear | `expect(locator).to_be_visible()` |
| An element to go away | `expect(locator).not_to_be_visible()` |
| A table row for a known item | `expect(page.locator(f"{ROWS}:has-text('{ja_id}')").first).to_be_visible()` |
| Text to settle after an update | `expect(locator).to_have_text(...)` / `to_contain_text(...)` |
| A button to become usable | `expect(locator).to_be_enabled()` / `to_be_disabled()` |
| A row count | `expect(page.locator(ROWS)).to_have_count(n)` |
| A field's value after JS fills it | `expect(locator).to_have_value(...)` |
| A URL change | `expect(page).to_have_url(...)` |

**The one exception**: if there is genuinely no observable condition — you are asserting that
something does *not* happen within a debounce window, for instance — keep the wait and justify it
in a comment at the call site. FR-007 requires the comment; a bare `wait_for_timeout` will not pass
review.

```python
# The autocomplete debounces at 250ms; wait past it to prove no request fires
# for a two-character input. No observable state distinguishes "not yet" from "never".
page.wait_for_timeout(400)
expect(page.locator(".autocomplete-menu")).not_to_be_visible()
```

## Rule 2 — Never `networkidle`

**Do not use `wait_for_load_state("networkidle")`.**

Measured cost: ~302s suite-wide before removal; it also slowed `goto` itself, whose mean dropped
from 0.564s to 0.239s once it was gone.

`networkidle` waits for a 500ms window of network silence, so it costs at least half a second every
time even when the page was ready instantly. Playwright's own documentation discourages it for
testing. `page.goto()` already waits for the `load` event; anything beyond that is content
readiness, which belongs to Rule 1.

```python
# WRONG
page.goto(url)
page.wait_for_load_state("networkidle")

# RIGHT — goto already awaited 'load'; assert on what you actually need
page.goto(url)
expect(page.locator("#inventory-table-body tr").first).to_be_visible()
```

## Rule 3 — Never snapshot a JavaScript-rendered region

A non-waiting read — `locator.count()`, `text_content()`, `is_visible()` — returns whatever is in
the DOM at that instant. For anything JavaScript renders, that instant is usually "empty".

This single anti-pattern in `InventoryTableMixin.assert_item_visible()` broke 6 tests at once when
its incidental `networkidle` cover was removed.

```python
# WRONG — reads an empty table and reports a confusing failure
items = self.get_table_items()
assert ja_id in [i["ja_id"] for i in items]

# RIGHT — wait for the row, then read only if you need detail for the message
row = self.page.locator(f"{self.TABLE_ROWS_SELECTOR}:has-text('{ja_id}')")
expect(row.first).to_be_visible()
```

Snapshot reads are fine **after** an `expect()` has established the region is populated — that is
how you get a useful failure message without racing.

## Rule 4 — Seed data directly unless the UI is what you are testing

Creating an item through the Add Item form costs about **3 seconds**. Inserting it directly costs
milliseconds.

```python
# WRONG when the test is about search, move, history, labels, ...
add_page = AddItemPage(page, live_server.url)
add_page.navigate()
add_page.add_minimal_item("JA000001", "Carbon Steel")

# RIGHT — the item is scenery, so put it there directly
live_server.add_test_data([
    {"ja_id": "JA000001", "material": "Carbon Steel", "location": "Storage A"},
])
```

Drive the form only when the form is the subject: `test_add_item.py`,
`test_material_field_validation.py`, `test_required_location.py`, and similar.

For a non-standard taxonomy, use `live_server.add_material_taxonomy([...])` rather than clicking
through the admin UI.

## Rule 5 — Put waits in the page object, assertions in the test

If a page object method navigates or triggers an async update, it is that method's job to leave the
page in a usable state. Tests should not need to know that clicking "Search" needs a wait.

```python
# In the page object
def search(self, query: str):
    self.page.fill(self.SEARCH_INPUT, query)
    self.page.click(self.SEARCH_BUTTON)
    expect(self.page.locator(self.RESULTS_TABLE)).to_be_visible()

# In the test — no waiting knowledge required
search_page.search("4140")
search_page.assert_item_in_results("JA000001")
```

This is also where the leverage is: one fix in a page object removes a wait from every test that
calls it.

## Rule 6 — One file per feature area, not per bug

The suite has 57 files, several of which exist because a bug once had a test written for it:
`test_move_items.py` alongside `test_move_items_basic.py`,
`test_move_items_sub_location.py`, `test_move_items_with_original_thread.py`, and
`test_move_current_location_bug.py`.

Every file pays fixed cost and makes the suite harder to navigate. A regression test for a bug in
move behaviour belongs in the move test file, named for the behaviour it protects — not the issue
number.

**This rule constrains new tests. It is not licence to merge existing files** — FR-011 forbids
losing assertions, and consolidation is not part of this feature.

## Rule 7 — A test must pass alone

```bash
nox -s e2e -- tests/e2e/test_your_file.py::test_your_test
```

If it only passes as part of a full run, it depends on state another test left behind. The reset
guarantees an empty inventory and the standard 21-row taxonomy before every test — nothing more.
See [data-model.md](../data-model.md) for the full list of what you may assume.

## Rule 8 — Screenshot tests are not e2e tests

Tests marked `@pytest.mark.screenshot` generate documentation images and write files into
`docs/images/screenshots/`. They belong to the `screenshots` / `screenshots_headless` nox sessions.

They must **not** be part of the `e2e` gate: they duplicate work, and they make the test suite
modify tracked files. The `e2e` session selects `-m "e2e and not screenshot"`.

---

## Review checklist

A new or modified e2e test should satisfy all of these:

- [ ] No `wait_for_timeout` / `time.sleep` — or each one carries a justification comment
- [ ] No `networkidle`
- [ ] No non-waiting read of a JS-rendered region before an `expect()` establishes it
- [ ] Precondition data seeded via `add_test_data`, not through the UI
- [ ] Waiting logic lives in the page object; the test reads as assertions
- [ ] Lives in the feature-area file, not a new bug-specific file
- [ ] Passes when run on its own
- [ ] Not marked `@pytest.mark.screenshot` unless it is genuinely a documentation screenshot
