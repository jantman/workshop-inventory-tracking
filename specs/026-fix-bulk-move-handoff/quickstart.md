# Quickstart: Validating the item hand-off

**Feature**: `specs/026-fix-bulk-move-handoff` | **Date**: 2026-08-24

How to prove this feature works. Details live in [contracts/handoff.md](./contracts/handoff.md)
and [data-model.md](./data-model.md); this is the run guide.

## Prerequisites

Per `CLAUDE.md`: use the virtualenv binaries by path, and put pyenv's 3.13 on `PATH` for nox.

```bash
cd /home/jantman/GIT/workshop-inventory-tracking
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
```

Docker must be available for the e2e session's MariaDB container.

## Commands

```bash
venv/bin/nox -s tests            # unit; sub-second, network blocked
venv/bin/nox -s e2e              # ~13m45s warm — see the timeout note below
venv/bin/nox -s screenshots_verify
```

**The e2e session will not fit in an agent's Bash timeout.** Most cap at 10 minutes and the suite
no longer fits. Run it detached and poll:

```bash
nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

Budget 20 minutes on a cold environment (image pull + Playwright browsers).

## Step 0 — Reproduce before fixing

Do this first. It is not ceremony: three code paths produce issue #107's report and
[research.md](./research.md) R3 does not settle which. A fix written against the wrong one passes
its own test and leaves the user stuck.

1. Open `/inventory/move`. Scan 14 JA-ID/location pairs, no sub-locations.
2. Scan `>>DONE<<`.
3. Record: the queue badge count throughout, the alert text at each step, whether
   Validate & Preview is enabled, and `moveQueue.length` / `currentExpectedInput` from the
   console.

The queue badge reading `0 items` partway through points at Candidate A/B; input arriving as
fragments points at Candidate C. Capture this before changing behavior.

## Step 1 — Bulk move from the inventory list (US1, the reported bug)

1. Seed three active items in different locations via `live_server.add_test_data`.
2. On `/inventory`, tick all three; Options → **Bulk Move Selected**.
3. The Move page opens naming all three as awaiting a destination, and says a destination is
   needed for all three.
4. Scan one location.
5. **Expect**: all three queued to it, each showing its own current location, badge reads
   `3 items`.
6. Validate, execute. **Expect**: all three moved, reflected on `/inventory`.

**This is the acceptance test for issue #106.** It must fail against `main` — if it passes before
the fix, it is navigating directly instead of clicking the control.

## Step 2 — The same from Search (US1)

Repeat Step 1 from `/inventory/search`. Behavior must be identical in every respect. This is the
step that catches a re-split of the parameter convention.

## Step 3 — Mixing, and sub-locations (US1)

- After Step 1's group is queued, scan a further JA ID and location by hand. **Expect**: it joins
  the same queue; all four execute together.
- Repeat Step 1 but supply a sub-location before finishing. **Expect**: it applies to **all three**
  items, not just the last.

## Step 4 — Long scanning session (US2, issue #107)

1. `/inventory/move`, no hand-off. Scan 14 JA-ID/location pairs.
2. Scan `>>DONE<<`.
3. **Expect**: the 14th pair is queued, the badge reads `14 items`, Validate & Preview is
   enabled, and no spurious input warning appears.
4. Validate and execute. **Expect**: all 14 moved.

Then the wedge, directly: from the state where a JA ID has been scanned but no location yet,
scan another JA ID. **Expect**: the machine resolves rather than bouncing — no state from which
no valid input makes progress.

## Step 5 — Scanner without a trailing newline (US2)

Drive a full sequence typing characters **without** a trailing Enter. **Expect**: the same
outcome as with Enter.

This path has never been executed by a test — every existing scan does `.type()` then
`.press("Enter")`, which cancels the 100 ms fallback timer. It is Candidate C in R3.

## Step 6 — Single-item row actions (US3, US4)

- A row's **Move** action → Move page holds that one item, needs only a destination; queue,
  validate, execute.
- A row's **Shorten** action → Shorten page opens with `source_ja_id` already identifying it.

## Step 7 — Rejections and edge cases

| Case | Expect |
|---|---|
| Hand-off names a nonexistent JA ID | Named on screen; the rest proceed |
| Hand-off names an inactive (historical) row | Rejected and named — never queued |
| Every item rejected | Says so plainly; not an apparently-normal empty page |
| Same item twice | Appears once |
| Open `/inventory/move` and `/inventory/shorten` with no parameter | Today's behavior exactly |
| Sub-location scanned first after a hand-off | Refused, with an explanation |
| `>>DONE<<` after a hand-off with no destination given | Nothing queued; the page says why |
| Clear the queue after a hand-off | Page still usable, not dead |

## Step 8 — Regression and gates

```bash
venv/bin/nox -s tests
nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

- The active-status and item-history e2e tests must pass — this touches move and shorten, so
  Principle VI is engaged.
- **Working tree must be clean after an e2e run.** If it is not, screenshot tests leaked into the
  session.
- `app/templates/**` and `app/static/js/**` changed, so regenerate screenshots
  (`venv/bin/nox -s screenshots_headless`) and commit them with the change. Measure the churn
  first — screenshots come from two sources and churn every run.
- Confirm no `wait_for_timeout`, `time.sleep`, or `networkidle` was added:

```bash
grep -rn "wait_for_timeout\|time.sleep\|networkidle" tests/e2e/
```

The suite executes zero fixed waits today and must still execute zero.
