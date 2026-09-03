# Quickstart: Validating the One-Clock Fix

**Feature**: `specs/037-fix-timestamp-clock-basis/` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

The defect is invisible on every screen, so "does it look right?" proves nothing here. Everything
below reads the stored values directly.

## Prerequisites

- The repository virtualenv at `venv/`. Invoke its binaries by path — `venv/bin/python`,
  `venv/bin/nox` — rather than activating it.
- `nox` needs Python 3.13 on `PATH`: prefix nox invocations with
  `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`.
- **A non-UTC `TZ` for the manual steps.** On a machine already set to UTC the bug does not
  reproduce and the fix is unobservable. Every command below forces `TZ=America/New_York`, which
  is what this deployment runs.

## 1. Reproduce the defect (before the fix)

Two columns of one row, written by one call, on two clocks. SQLite's `CURRENT_TIMESTAMP` is UTC,
so this reproduces the MariaDB behavior exactly.

```bash
TZ=America/New_York venv/bin/python - <<'PY'
import tempfile
from sqlalchemy import create_engine
from app.database import Base
from app.mariadb_storage import MariaDBStorage
from app.catalog_service import CatalogService

db = tempfile.NamedTemporaryFile(suffix='.db', delete=False).name
uri = f'sqlite:///{db}?check_same_thread=false'
Base.metadata.create_all(create_engine(uri))
storage = MariaDBStorage(database_url=uri); storage.connect()

service = CatalogService(storage)
p = service.create_product(description='clock probe', quantity=1)
p = service.get_product(p.id)
print('date_added         ', p.date_added)
print('quantity_updated_at', p.quantity_updated_at)
print('gap                ', abs(p.date_added - p.quantity_updated_at))
PY
```

**Before the fix**: the gap is four hours (five in winter), for two values written within the
same millisecond.

**After the fix**: the gap is under a second, and stays under a second whatever `TZ` is set to.

## 2. Run the automated checks

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
```

The new `tests/unit/test_clock_basis.py` carries the two tests from
[research.md](./research.md) R9 — a forced-timezone basis test that fails on today's code, and a
patched-clock test asserting every recorded column on a new row equals the sentinel (INV-1). Both
are sub-second; the unit suite stays sub-second.

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

**Run e2e detached and poll.** It takes about 13m 45s warm, which does not fit inside a 10-minute
agent tool timeout; a foreground run reports a false timeout on a passing suite.

Two things in that run matter more than the rest:

- The **active-status and history** tests. `inventory_items.date_added` selects the current
  history row (R8), so this feature is under Principle VI whether or not it looks like it.
- `tests/e2e/test_stock_age.py` and `tests/e2e/test_reorder_view.py`, whose backdating seeds move
  onto the application clock. The ages under test are 9, 100, 400 and 800 days — none within four
  hours of a rendering boundary — so a green run here means the seeds were retargeted correctly,
  not that the margin hid a mistake.

The run must leave the working tree clean. If `docs/images/screenshots/` is dirty afterwards, a
screenshot test leaked into the session.

## 3. Validate by hand

Against a running instance, with a product that has a count:

```bash
curl -s localhost:5000/api/products/<id> | venv/bin/python -m json.tool \
  | grep -E 'date_added|last_modified|quantity_updated_at|stock_status_updated_at'
```

For a product **created after the fix**, all four values sit within seconds of each other. This is
the check from the issue, and it is the one that was four hours out.

Then confirm the two things that must *not* have moved:

- **Ages still read correctly.** Open the product page. A count set a few minutes ago reads
  "just now"; one set this morning reads the right number of hours. If every product on the site
  reads "just now", the read side did not move with the write side.
- **Order days did not shift.** Capture an order **after 20:00 local** with no order date typed,
  then look at it on the order listing. It must show today's date, not tomorrow's. This is the
  single most likely way to get this feature wrong, and it is only observable in the evening.

## What changes on the first deploy — expected, not a bug

**Stock ages on products counted before the deploy will jump by about four hours, once.**

Those rows hold a local-clock value and are now read against a UTC clock, so they report as older
than they are, by the UTC offset. "Counted 1 hour ago" becomes "counted 5 hours ago"; a count
near midnight may cross into "yesterday". Rows written after the deploy are unaffected, and the
discrepancy on the old rows becomes noise as soon as the real age exceeds a day.

This is accepted, not overlooked — see [research.md](./research.md) R6. The offset in force when
each row was written was never recorded, so it cannot be reversed, and a row written inside a
daylight-saving transition is ambiguous even in principle. No rows are migrated.

## What "done" looks like

- The gap in step 1 is under a second, with `TZ` forced to a non-UTC zone.
- `nox -s tests` and `nox -s e2e` pass, and the working tree is clean afterwards.
- `grep -rn "datetime\.now()\|datetime\.utcnow()" app/` returns only the log and report sites R7
  puts out of scope, and `local_now()` accounts for every calendar-day default.
- No file under `migrations/versions/` was added or changed.

## What this feature does not touch

- Existing rows. Nothing is rewritten, converted or migrated.
- The schema. No column, no type, no Alembic revision.
- The JSON format. Same field names, same naive ISO-8601 text, no `Z` added
  ([contracts/clock.md](./contracts/clock.md)).
- Which action updates which timestamp. Receiving a purchase still leaves the count age alone —
  that is feature 008's FR-008 and `test_receiving_does_not_reset_a_counted_age` still guards it.
- Log lines, export report headers, and the `last_updated` label in a response body. They stay
  local (R7).
