# Project Context

This is a single-user application for tracking materials and supplies in a hobby workshop. It runs on a home network and is reachable only from the LAN. Size every decision to that.

* **Simplicity is the first principle.** Build for the requirement in front of you. No abstraction for a single implementation, no configuration knob for a future that hasn't arrived.
* **Don't optimize without a measurement.** Caching, batching, async, and background jobs require an observed problem. The 1% coverage gate and the sub-second unit suite are deliberate — don't "fix" them.
* **Don't add scale machinery.** No multi-tenancy, user accounts, roles, rate limiting, or queues. The app has no login and doesn't need one.
* **Don't harden against the Internet.** No anonymous attackers, no hostile input, no sanitization layers, no CVE triage as a merge gate. Security effort goes to not losing data and not committing secrets (`.env`, `credentials.json`, `token.json` stay untracked). Validate input because bad data breaks the inventory, not because it might be malicious.
* **The exception:** simplicity never justifies risking data integrity — `Decimal` (never `float`) for measurements, MariaDB as the source of truth with Alembic migrations, and the item history invariants (one active row per JA ID, retained shortening history) are non-negotiable.

Full governance: `.specify/memory/constitution.md`. Stack details and code patterns: `_bmad-output/project-context.md`.

# General

* You must source the virtualenv (`venv/`) before running any commands that rely on project dependencies.

## Spelling: "catalog", never "catalogue"

American spelling throughout: `catalog`, `cataloged`, `cataloging`, `uncataloged`. This covers
prose, user-visible strings, comments, docstrings and code identifiers alike. The repository
was swept to one spelling; the point is that it stays that way.

**Two trees are deliberately excluded and must not be swept:**

* **`specs/`** — the frozen record of what was specified at the time. Rewriting it falsifies
  the record.
* **`migrations/versions/*.py`** — Alembic revision docstrings describe migrations as they
  shipped, for the same reason.

So `grep -ri catalogue specs/ migrations/` returning matches is correct, not a bug to fix. The
check that matters is that the rest is clean:

```bash
grep -ric "catalogue" README.md CLAUDE.md docs/ app/ tests/   # must return nothing
```

**A blind `catalogue` → `catalog` substitution is wrong.** It turns `catalogued` into
`catalogd` and `cataloguing` into `catalogng`. Replace the longer inflections first —
`catalogues`→`catalogs`, `catalogued`→`cataloged`, `cataloguing`→`cataloging` — and only then
the bare word. Verify with `grep -rn "catalogd\|catalogng\|uncatalogd" app/ tests/`.

# Testing

* Run tests via the `nox` test runner, not by running `pytest` directly
* The `e2e` test session must have a timeout of 15 minutes set on your bash tool. This timeout is set on your bash tool, not on the command line. (The suite runs in about 8m 15s on a warm environment; the margin is for a cold start that has to pull the MariaDB image and install Playwright browsers.)

## Writing e2e tests

This section is the normative source for how to wait in an e2e test. The constitution states the rule; this states the practice.

The suite used to take 22 minutes, over half of it blocked on a clock rather than on the application. Two features were spent getting the fixed waits out — the second one because the first left 127 of them behind. It now runs in 8m 13s with **zero** `wait_for_timeout` executions. Adding one puts that back.

### The rules

* **Wait for state, never for a duration.** No `page.wait_for_timeout(...)`, no `time.sleep(...)`. Use `expect(locator)` — it polls until the condition holds. If there is genuinely nothing observable to wait for, the wait stays but MUST carry a comment at the call site naming the condition that cannot be observed. There is exactly one such wait in the suite today (`waits.dismiss_material_suggestions`), and it is justified there.
* **Never `wait_for_load_state("networkidle")`.** It costs at least half a second every time and tells you nothing about whether your content rendered. `goto()` already waits for `load`; wait for the element you care about.
* **Never snapshot a JavaScript-rendered region.** `locator.count()`, `text_content()`, `is_visible()`, `get_attribute()` and `is_checked()` do not wait, so against a JS-rendered table they read "empty". Establish the region with `expect(...)` first. This matters most for *negative* assertions — "the item is absent" passes trivially against a table that has not loaded.
* **A click that fires a `fetch` has not finished when `click()` returns.** Wait for whatever the response changes on the page. Navigating away sooner aborts the request.
* **Seed data directly.** `live_server.add_test_data([...])` takes milliseconds; creating the same item through the Add Item form takes about three seconds. Drive the form only when the form is what is under test.
* **Put the waiting in the page object, the assertions in the test.** Shared waits live in `tests/e2e/waits.py`.
* **Screenshot tests are not e2e tests.** `nox -s e2e` selects `-m "e2e and not screenshot"`; screenshot generation belongs to `nox -s screenshots`/`screenshots_headless`. Running an e2e session must leave the working tree clean.

### Finding the condition to wait on

Read the handler that the action triggers, and ask where its `await` is. That one question answers most cases.

**A — the awaited-fetch boundary.** When a handler is `async` and awaits a request before mutating what you can see, everything it sets *before* the await is useless as a completion signal and everything after it is valid. `inventory-move.js`'s `finalizeCurrentMove()` awaits `GET /api/items/{ja_id}` and only then pushes to the queue: `#queue-count` is a valid signal for that move, and the barcode input clearing — which happens first — is not. Signals on the near side of the await lie.

**B — one action, two completions.** When a handler starts new work synchronously and finishes old work asynchronously, no single condition covers the action. Wait for both, one `expect()` each. Scanning a JA ID on the move page while a move is open calls `handleJaIdInput()` synchronously — which sets `#scanner-status` to `Waiting for Location` for the *new* item — and then calls `finalizeCurrentMove()` **without awaiting it**, to queue the *previous* one. Waiting on the badge alone passes on a fast machine and fails on a slow one. `waits.scan_on_move_page` waits on both.

**C — render-implies-completion.** When the code appends a DOM node *after* awaiting the work, the node's existence is a complete signal and nothing further is needed. `photo-manager.js:303` awaits the upload POST before appending the card, so `expect(cards).to_have_count(n)` is the whole wait — a rendered card cannot predate a completed upload. This is the cheapest correct wait there is; look for it first.

**D — a state badge is per-transition, not per-action.** A single element reporting "what the page is waiting for next" is a valid signal for the transitions that set it synchronously and a trap for those that do not. `#scanner-status` is right for two of the move page's five transitions and wrong for the rest. Map the states before trusting it.

**E — a cushion in front of a snapshot read is load-bearing.** If a fixed wait sits before `count()`, `text_content()`, `is_visible()`, `get_attribute()` or a boolean helper wrapping one, the wait is holding the *read* up, not the application. Converting the wait without converting the read moves the failure, it does not fix it. `test_copy_item_photos.py` is the worked case: its delays were never about the flow, they were propping up `assert not is_copy_photos_button_enabled()`. The fix is `expect(item).to_have_attribute('disabled', '')`, which polls.

**F — a positive class, not the absence of a negative one.** `expect(field).not_to_have_class('is-invalid')` is satisfied by a field the validator has never looked at, and by one something has since cleared. `MaterialValidator` adds `is-valid` on accept, so that is the condition that actually means "accepted". Prefer the assertion that cannot be true before the work happened.

**G — the page may be writing to the field you are filling.** Pattern A cuts both ways. `autoPopulateJaId()` checks "only if `#ja_id` is empty" *before* awaiting `GET /api/inventory/next-ja-id` and writes the result *after*, so a `fill()` issued in that gap has its selection collapsed by the page's write and appends instead of replacing — leaving `JA000123JA000123`, which fails the field's `pattern`. Where the page populates a field for you, let its write land first (`expect(field).not_to_have_value("")`) and confirm yours stuck (`expect(field).to_have_value(...)`).

**Submissions that never happen are silent.** A form refused by constraint validation leaves nothing in the DOM — just a browser bubble. `AddItemPage.submit_and_wait()` settles on the `invalid` event for that case and returns `False`; a caller that ignores the result carries on as though its item exists and fails much later, somewhere unrelated. It also logs the offending field, its message and its value to the browser console — both races found in this suite were diagnosed from that one line, so leave it in.

### Reviewing a new e2e test

- Does every wait name an element, not a number?
- For each `count()` / `text_content()` / `is_visible()` / `get_attribute()`: what established that region first?
- For each negative assertion: would it also pass against a page that has not loaded?
- For each click that starts a request: what on the page changes when the response lands, and is the test waiting for that?
- Does it seed through `live_server.add_test_data` unless the form is the subject?
