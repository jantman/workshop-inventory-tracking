# Quickstart: validating Trustworthy Stock Age

## Prerequisites

```bash
cd /home/jantman/scratch/rm_me/workshop-inventory-tracking
source venv/bin/activate
```

`nox` sessions pin Python 3.13; put pyenv's 3.13 ahead of the system Python on `PATH` if `nox` reports a missing interpreter.

## The suites

```bash
nox -s tests      # unit; sub-second, network blocked, SQLite via test_storage
nox -s e2e        # Playwright against MariaDB -- allow a 15-minute tool timeout
```

Both must pass. `nox -s e2e` selects `-m "e2e and not screenshot"` and must leave the working tree clean.

## What the unit suite proves

`tests/unit/test_stock_status.py`, extended. These carry the requirements that need a clock the UI cannot provide — a test backdates the field through `service.Session()` and then exercises the service (see `research.md`).

| Behaviour | Requirement |
|---|---|
| Setting a flag records the moment | FR-001 |
| Setting the flag to the value it already holds moves the date forward | FR-002 |
| Clearing the flag clears the date | FR-003 |
| `stock_status_age` is `None` with no flag, and `None` with a flag and no date | FR-005 |
| Receiving adds the received quantity to a tracked count | FR-007 |
| Receiving leaves a backdated `quantity_updated_at` **exactly** where it was | FR-008, SC-001 |
| Receiving against an untracked product writes no count and no date | FR-009 |
| Receiving clears the flag *and* its date | FR-006 |
| Receiving twice changes neither the count nor either date | FR-008 |
| Setting a count, and stepping it, stamp the date | FR-010 |
| Stopping tracking clears the date; starting again writes a fresh one | FR-011 |
| `relative_age(None)` still says `never counted`; `relative_age(None, 'at an unknown time')` says that instead | FR-012 |
| `to_dict()` carries `stock_status_updated_at` | contract |

The FR-008 test is the one that matters. Backdate `quantity_updated_at`, receive, and assert the stored value is **unchanged** — not "older than now", which passes against a bug that moves it by a second.

## What the E2E suite proves

`tests/e2e/test_stock_age.py` (new) and `tests/e2e/test_reorder_view.py` (extended). Seed through `CatalogService(live_server.storage)` and backdate through `sessionmaker(bind=live_server.engine)`; drive the browser only for the parts under test.

| Scenario | Requirement |
|---|---|
| Flag a product from the detail page → `#flag-age` reads *Flagged low just now* | FR-004 |
| Two products flagged at different seeded dates → the reorder rows show different ages | FR-004, SC-004 |
| A product with a flag and a `NULL` date → *at an unknown time* | FR-005, SC-006 |
| Clear the flag → `#flag-age` is absent | FR-003 |
| A backdated count, receive through the reorder list's **Receive** button → the count rises and `#quantity-age` still reads the old age | FR-007, FR-008, SC-001 |
| The received product's flag and flag age are both gone | FR-006 |

Waiting rules for the new assertions, per `CLAUDE.md`: every one is `expect(locator)` on server-rendered HTML. The existing `wait_for_stock_flag()` helper in `test_reorder_view.py` is the right wait after a flag button click — the button PATCHes and reloads, so the reloaded button's own styling is the proof the round trip finished. Reuse it rather than writing a second one.

## The migration

Neither suite runs migrations, so `b1a0c0d10010` is otherwise unexercised. Run it against a **disposable MariaDB container**, never against the database named in `.env`:

```bash
python manage.py db upgrade      # column appears, nullable, all NULL
python manage.py db downgrade    # column gone, flags and counts intact
python manage.py db upgrade      # back again
```

Check after the upgrade that no row has a non-`NULL` `stock_status_updated_at`: nothing is backfilled, by design.

## The four things to check by hand

A fresh database cannot produce the first of these, and the others are judgements about wording rather than assertions.

1. **The legacy row.** On a copy of the real database, upgrade and open the reorder list. Every product flagged before today reads **Flagged low at an unknown time**. This is correct and it is the thing most likely to be reported as a bug — confirm it reads as an honest gap rather than an error.
2. **The receive path, watched.** Find a product with a tracked count and an outstanding order. Note the age line. Receive. The number goes up, the age line does not move. This is the entire point of the feature and it takes ten seconds to see.
3. **Re-affirming a flag.** Open a product flagged some time ago and press **Low** again. The age resets to *just now*. Before this feature that button press did nothing at all.
4. **The two ages side by side.** A product with both a count and a flag shows two age lines in the same words. Read them together and confirm they cannot be confused for one another — that is FR-012 as a judgement, not as a test.

## Documentation

`docs/user-manual.md` has two sentences that this feature falsifies, around line 694 and line 708: the stock section describes the count's age without mentioning the flag's, and says receiving "clears both kinds of low" without saying what it now leaves alone. Both need updating in the same change, along with a note that flags set before the upgrade have no recorded age.
