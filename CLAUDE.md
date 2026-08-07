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

# Testing

* Run tests via the `nox` test runner, not by running `pytest` directly
* The `e2e` test session must have a timeout of 15 minutes set on your bash tool. This timeout is set on your bash tool, not on the command line. (The suite runs in well under 10 minutes; the margin is for a cold start that has to pull the MariaDB image and install Playwright browsers.)

## Writing e2e tests

The e2e suite used to take 22 minutes, over half of it spent blocking on a clock rather than on the application. Adding a `wait_for_timeout` puts that back. The rules, in full, are in `specs/002-e2e-test-performance/contracts/e2e-test-authoring.md`; the short version:

* **Wait for state, never for a duration.** No `page.wait_for_timeout(...)`, no `time.sleep(...)`. Use `expect(locator)` — it polls until the condition holds. If there is genuinely nothing observable to wait for, the wait stays but MUST carry a comment at the call site saying why.
* **Never `wait_for_load_state("networkidle")`.** It costs at least half a second every time and tells you nothing about whether your content rendered. `goto()` already waits for `load`; wait for the element you care about.
* **Never snapshot a JavaScript-rendered region.** `locator.count()`, `text_content()` and `is_visible()` do not wait, so against a JS-rendered table they read "empty". Establish the region with `expect(...)` first. This matters most for *negative* assertions — "the item is absent" passes trivially against a table that has not loaded.
* **A click that fires a `fetch` has not finished when `click()` returns.** Wait for whatever the response changes on the page. Navigating away sooner aborts the request.
* **Seed data directly.** `live_server.add_test_data([...])` takes milliseconds; creating the same item through the Add Item form takes about three seconds. Drive the form only when the form is what is under test.
* **Put the waiting in the page object, the assertions in the test.** Shared waits live in `tests/e2e/waits.py`.
* **Screenshot tests are not e2e tests.** `nox -s e2e` selects `-m "e2e and not screenshot"`; screenshot generation belongs to `nox -s screenshots`/`screenshots_headless`. Running an e2e session must leave the working tree clean.
