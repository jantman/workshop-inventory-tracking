# Quickstart: Stock Fit Search

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

How to run this feature and how to prove it works. Implementation belongs in `tasks.md`, not
here.

---

## Prerequisites

The repository virtualenv, and Python 3.13 on `PATH` for nox to build its environments:

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
```

Invoke the venv's binaries by path — `venv/bin/nox`, `venv/bin/python`. Do not activate.

---

## Run the application

```bash
venv/bin/python app.py
```

Then open `http://localhost:5000/inventory/find-stock`, or reach it from the **Inventory**
menu, entry "Find Stock for a Part", beside "Search Items".

---

## Prove it by hand

Seed four items of the same material — the set is chosen so that each one exercises a
different rule in [contracts/fit-rules.md](./contracts/fit-rules.md):

| JA ID | Type / Shape | Dimensions | Envelope rule |
|---|---|---|---|
| JA000101 | Bar / Rectangular | 4 × 3 × 0.5 | E5 — `Box` |
| JA000102 | Bar / Square | 12 long, 3 across | E4 — `Box(12, 3, 3)` |
| JA000103 | Bar / Round | 12 long, Ø2 | E3 — `Cylinder(2, 12)` |
| JA000104 | Tube / Round | 12 long, Ø3, 0.065 wall | E1 — hollow, excluded |

Then:

1. **Orientation** (Story 1). Ask for a rectangular piece **0.5 × 3 × 4**. JA000101 comes
   back. Ask again as **4 × 0.5 × 3**, and as **3 × 4 × 0.5**. The same set comes back every
   time, and JA000102 comes back too — a 3" square bar contains a 3 × 0.5 cross-section.
2. **Cross-shape** (Story 2). Ask for a **Ø2 round, 2 long**. JA000103 (upright, rule F4) and
   JA000102 (rule F3 — 3 × 3 cross-section contains a Ø2 circle) both come back. JA000101
   does not: its 0.5 thickness cannot contain a Ø2 circle in any orientation.
3. **Ordering** (Story 3). In that same result, JA000103 is first — its cross-section is the
   circle of Ø2 against the request's Ø2, so nothing is removed.
4. **Tolerance** (Story 4). Ask for a **Ø2 round, 12.5 long** — nothing fits. Put `0.5` in
   the tolerance beside the length and JA000103 returns, marked as fitting within tolerance
   with **Length** named. Clear the tolerance and it disappears again.
5. **Counters** (SC-006). Every one of these searches reports what it looked at: `considered`
   counts all four, and JA000104 appears in `skipped_hollow` and never in the results.
6. **The existing search is untouched** (FR-026). Open `/inventory/search`, run a
   length-range query, and confirm it behaves exactly as before.

---

## Run the tests

Unit — sub-second, network blocked, and where nearly all of this feature's coverage lives:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
```

End-to-end — **give this a 15-minute tool timeout and run it detached.** The suite is around
13m 45s warm, which does not fit inside the 10-minute cap most agent shells impose:

```bash
nohup env PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" \
  venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
# then poll /tmp/e2e.log
```

Screenshots, required by the Development Workflow gate because this change touches
`app/templates/**` and `app/static/js/**`:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify
```

Screenshot output churns on every run. Inspect `git diff --stat docs/images/screenshots/`
and commit only the images this change actually alters.

---

## What each test level is responsible for

| Level | Covers | Why there |
|---|---|---|
| `tests/unit/test_fit.py` | Every row of fit-rules §1 and every rule in §3, including the cases that must **not** fit: Ø2 bar refusing a 2 × 2 square, Ø1.5 bar refusing a Ø2 request, a 0.5-thick bar refusing a Ø2 round. Plus the D3 agreement test against `TypeShapeValidator`. | Pure functions, no fixtures, runs in milliseconds. This is where exhaustiveness is affordable. |
| `tests/unit/test_mariadb_inventory_service.py` | Ordering (all four sort terms, including a deliberate tie broken by `ja_id`), the three counters, hierarchical material, active-only. | Through SQLite via the same `Storage` ABC production uses. |
| `tests/unit/test_routes.py` | The six 400 cases from [find-stock-api.md](./contracts/find-stock-api.md), and that a success payload carries every key the shared table reads. | Request parsing is route work. |
| `tests/e2e/test_find_stock.py` | One pass per user story, and the FR-028 check that `/inventory/list` and `/inventory/search` still render without a Fit column. | The browser is the only place the shared-table reuse can actually be observed. |

---

## The waits the e2e test uses

Constitution Principle IV: wait on observable state, never on elapsed time. Nothing in this
feature needs an unobservable wait, so `tests/e2e/test_find_stock.py` must contain no
`wait_for_timeout` and no `time.sleep`.

| Action | Wait on | Which CLAUDE.md pattern |
|---|---|---|
| Submitting the form | `expect(rows).to_have_count(n)` on the results tbody | **C — render-implies-completion.** The handler appends rows only after awaiting the `fetch`, so a rendered row cannot predate a completed search. |
| Asserting an item is **absent** | `expect(rows).to_have_count(n)` **first**, then assert on the row set | A count/text snapshot against a JS-rendered table reads "empty" before it loads, so a negative assertion would pass trivially. |
| The counters line | `expect(counters).to_contain_text(...)` | Written in the same handler pass as the rows; either is a valid signal, and `expect` polls. |
| Seeding | `live_server.add_test_data([...])` | Milliseconds, versus roughly three seconds per item through the Add Item form. The form is not what is under test. |
