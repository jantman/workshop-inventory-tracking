# Phase 1: Test State Ownership Model

**Feature**: `specs/002-e2e-test-performance` | **Date**: 2026-08-05

This feature adds no application entities and no schema change. What it does have is a state model
— who owns which piece of the shared test environment, how long it lives, and what a test is
allowed to assume about it. Getting this wrong is how a fast suite becomes an unreliable one, so it
is written down here.

The model below is **unchanged by this feature**. It is recorded because C1 and C2 remove the
incidental waits that were masking violations of it, and because C4 rejects changing it.

## Lifetimes

| Entity | Scope | Created by | Cost (measured) |
|---|---|---|---|
| MariaDB instance | session | `mariadb_testcontainer` (local) / CI service container | part of 45.9s one-time |
| Flask application server | session | `e2e_server` → `E2ETestServer.start()` | part of 45.9s one-time |
| Chromium browser process | session | pytest-playwright | part of 45.9s one-time |
| Browser context + page | **function** | pytest-playwright `page` fixture, wrapped in `tests/conftest.py` | within 0.120s setup mean |
| Database contents | **function** | `live_server` → `clear_test_data()` | 0.120s mean, 44.9s total |
| Material taxonomy (21 rows) | **function** | `setup_materials_taxonomy()`, called by `clear_test_data()` | included above |

The split matters: **process-level things are shared and expensive; data-level things are per-test
and cheap.** That is why C4 rejects optimizing the reset — the per-test half is already the cheap
half.

## Invariants a test may rely on

1. **A test starts with an empty inventory.** All ten tables are emptied before it runs.
2. **A test starts with the standard 21-row material taxonomy.** Categories (level 1), families
   (level 2), and specific materials (level 3) as seeded by
   `E2ETestServer.setup_materials_taxonomy()`.
3. **A test starts with a fresh browser context** — no cookies, no local storage, no session from
   any previous test.
4. **A test may mutate anything.** Nothing it does can leak into the next test, because the reset
   runs before every test rather than after.

Invariant 4 is what makes FR-012 (each test passes in isolation) achievable and FR-013 (no
cascading failures) true today. **No change in this feature may weaken invariants 1–4.**

## What a test must NOT assume

- **That the page is ready because it navigated.** This is the defect C1 exposes. Server-rendered
  HTML arrives with the document; anything JavaScript renders — the inventory table, modals,
  autocomplete results, validation messages, button enable/disable state — arrives later. A test
  must wait on the specific element, not on the navigation.
- **That another test created data it needs.** Invariant 1 forbids it.
- **That a fixed delay is long enough.** It is either unnecessary (the condition was already met)
  or unreliable (a slower machine misses it). Both are defects; the first is the one costing 423.9s.

## State transitions relevant to Principle VI

Constitution Principle VI governs item lifecycle and history, and the tests covering it are in
scope for C2 edits. The transitions their assertions verify:

```
add       → exactly one active row for the JA ID
shorten   → prior row retained inactive, new row active; exactly one active row
move      → location changes, active row identity preserved
deactivate→ row becomes inactive; no active row remains for that JA ID
duplicate → new JA ID, new active row, history NOT copied
```

`test_history_functionality.py`, `test_shorten_items.py`, `test_shorten_items_basic.py`, and
`test_toggle_item_status.py` assert these. FR-011 forbids weakening any of them; C2's edits there
may change *how the test waits*, never *what it asserts*.

## Seeding paths and their cost

Two ways to get an item into the database. The choice is a performance decision:

| Path | Used at | Cost | When correct |
|---|---|---|---|
| `live_server.add_test_data([...])` | 64 call sites | milliseconds — direct service-layer insert | The item is a **precondition**. The test is about something else. |
| Driving the Add Item form | 22 files | ~3s per item — form fill + submit + waits | The test is **about the add form itself**. |

Roughly half the suite already uses the fast path. The rule for C2 and for all future tests: **if
the item is scenery, seed it directly; drive the UI only when the UI is the thing under test.**
This is captured normatively in [`contracts/e2e-test-authoring.md`](./contracts/e2e-test-authoring.md).
