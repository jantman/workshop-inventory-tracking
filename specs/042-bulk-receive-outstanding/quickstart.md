# Quickstart: Bulk-Receiving Outstanding Purchases from a Backfill

**Feature**: 042-bulk-receive-outstanding

How to run this feature's tests, and how to see the command actually do the thing against a real
database.

## Prerequisites

Commands run from the repository root against the project virtualenv. In a worktree without its
own `venv/`, use the main checkout's.

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
```

## 1. Run the tests

```bash
venv/bin/nox -s tests
```

Everything this feature adds is unit-tested; the suite runs in about a second and the network is
blocked, which is fine because nothing external is touched.

To run just this feature's tests while iterating:

```bash
venv/bin/nox -s tests -- tests/unit/test_bulk_receive.py
```

The E2E suite is untouched — there is no page — but it still has to be green to merge:

```bash
venv/bin/nox -s e2e     # ~14 minutes; run it detached, see CLAUDE.md
```

No screenshot regeneration: nothing under `app/templates/**`, `app/static/css/**` or
`app/static/js/**` changes.

## 2. What the tests must prove

Grouped by what would go wrong if they were missing.

**The sweep does the job** (spec US1)

- Outstanding purchases before the cutoff become received.
- Each one's `received_date` equals its own `order_date` — not today's date.
- Afterwards the order reports no outstanding lines and the reorder list no longer calls the
  product on the way.

**The sweep is not a receiving-desk receipt** (spec US3 — the tests that matter most)

- A product with a tracked on-hand count still has the same count.
- Its `quantity_updated_at` is unchanged.
- A manually set `stock_status` is still set, with its original date.
- A product with no tracked count still has none.

Nothing in the existing suite covers this: 031's equivalent assertions hold "by construction"
because a purchase born with a receipt date never reaches `receive_purchase`. This feature
introduces the first code that receives an already-existing purchase without going through it,
so construction no longer covers it.

**Selection is exactly what was asked for**

- An already-received purchase is not selected and is not re-dated.
- A purchase ordered *on* the cutoff date is not selected — "before" means before.
- A different vendor's purchase is not selected; `digikey` matches `DigiKey`.
- With no `--vendor`, every vendor is eligible.
- A hand-recorded outstanding purchase is eligible.
- An undated outstanding purchase is left alone and counted in `undated_count`.

**The command behaves at the terminal** (via `click.testing.CliRunner`)

- `--dry-run` lists and writes nothing.
- Without it, confirming writes; declining writes nothing and says so.
- An empty selection says so and prompts for nothing.
- A malformed `--before` is refused before anything is read.

## 3. Try it against a real database

```bash
# See what a sweep would touch. Writes nothing.
python manage.py orders receive-outstanding --before 2026-01-01 --dry-run

# Narrow it to one vendor.
python manage.py orders receive-outstanding --vendor DigiKey --before 2026-01-01 --dry-run

# Do it. It lists what it found and asks before writing.
python manage.py orders receive-outstanding --vendor DigiKey --before 2026-01-01
```

Then check the result in the app:

- **Products → Captured Orders** — the swept orders now show as complete.
- **Stock Levels / reorder list** — nothing from those orders is marked *on the way*.
- **Any swept product's page** — the on-hand count, its age, and any low flag are exactly as they
  were. If any of those moved, the feature is wrong.

Run the same command a second time: it should find nothing and say so.

## 4. Reference

- Command surface: [contracts/cli-receive-outstanding.md](./contracts/cli-receive-outstanding.md)
- Service methods: [contracts/service-receipts.md](./contracts/service-receipts.md)
- Records and the columns touched: [data-model.md](./data-model.md)
- Why the date rule and the non-reuse of `receive_purchase`: [research.md](./research.md) §2, §3
