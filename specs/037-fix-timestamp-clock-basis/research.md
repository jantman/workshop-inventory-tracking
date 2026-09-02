# Phase 0 Research: One Clock for Recorded Timestamps

**Feature**: `specs/037-fix-timestamp-clock-basis/` | **Spec**: [spec.md](./spec.md) | **Issue**: #134

The issue names one symptom on one table. The first job of this phase was to find out how far
the symptom actually reaches, because the fix is a sweep and a sweep needs a complete list.

---

## R1 — Which timestamps are on which clock today?

**Finding**: There are three writers, not two, and the split does not follow table boundaries.

| Writer | Basis produced | Where |
|---|---|---|
| `default=func.now()` / `onupdate=func.now()` column defaults | database server (UTC in this deployment) | `app/database.py` — 10 columns across `InventoryItem`, `MaterialTaxonomy`, `Photo`, `ItemPhotoAssociation`, `Product`, `Purchase`, `ProductIdentifier`, `ProductAttachment` |
| `datetime.now(timezone.utc)` | UTC, tz-aware | `app/mariadb_inventory_service.py:603,637,638,1133,1166`; `app/mariadb_storage.py:430,442` |
| `datetime.utcnow()` | UTC, naive, deprecated API | `app/photo_service.py:118,119,133,423,873` |
| `datetime.now()` | **application-local** | `app/catalog_service.py:223,445,499`; `app/mariadb_materials_admin_service.py:180,181,250,354`; `app/main/routes.py:742,2403,2472,2473`; `app/database.py:967,983` (read side) |

**Two tables are actually wrong**, not one:

1. **`products`** — the reported case. `quantity_updated_at` and `stock_status_updated_at` are
   written local by `catalog_service`; `date_added` and `last_modified` come from the column
   defaults, in UTC. `set_quantity` writes the local value and fires the UTC `onupdate` **in the
   same UPDATE statement**, so a single write produces two columns four hours apart.
2. **`material_taxonomy`** — unreported and identical in shape. `mariadb_materials_admin_service` passes
   `date_added=datetime.now()` and `last_modified=datetime.now()` explicitly, overriding the
   UTC column defaults, so a material created through the admin service is on a different clock
   from one created through any other path into the same columns (`mariadb_storage.py:442` writes the same row's `last_modified` in UTC).

**Four `datetime.now()` writes in `app/main/routes.py` are dead.** `_parse_item_from_form`
(`:2472-2473`) sets `date_added`/`last_modified` on the domain object, but `add_item`
(`app/mariadb_inventory_service.py:1004`) never copies them onto the row — the column defaults
win. Likewise `:742` and `:2403` set `last_modified` before calling `update_item`, which
overwrites it at `:953`. They record nothing. They are still worth removing: they are exactly
the shape a reader would copy when adding the next write.

**`inventory_items` is therefore already consistent** — everything that reaches the column is
UTC, by two different routes. It is consistent by luck, not by design, and the two dead writes
above are the near miss.

**Decision**: the sweep covers every row in the table above. `inventory_items` is included even
though it is not currently wrong, because leaving three writers in place is what produced the
bug on `products`.

---

## R2 — What is the common basis: naive UTC, aware UTC, or a timezone-aware column?

**Decision: naive UTC.**

**Rationale**: MariaDB's `DATETIME` stores no offset, and SQLAlchemy's `DateTime(timezone=True)`
is a no-op on MySQL/MariaDB — an "aware" column is a fiction the database will not keep. Every
value read back from these columns is naive today and will stay naive. Choosing naive UTC means
the value that comes back is the value that went in, and that a subtraction against it cannot
raise.

It also matches what is already there. `func.now()` on a UTC server produces naive UTC, so the
majority of rows already stored are naive UTC and need no reinterpretation.

**The mixing hazard this avoids is not theoretical in this codebase.** `app/models.py:1263`
(`_naive`) exists because an operator typing an arrival date sent a naive datetime into a
comparison against an aware one, and `TypeError: can't compare offset-naive and offset-aware
datetimes` escaped as a 500 that lost a whole order capture (PR #128). The existing
`datetime.now(timezone.utc)` writes are aware values landing in naive columns; adopting aware
datetimes as the standard would spread that hazard rather than close it.

**Alternatives considered**:

- *Aware UTC everywhere.* Rejected: the column cannot hold the offset, so every read boundary
  would have to re-attach one, and every place that forgets is the PR #128 crash again.
- *Migrate the columns to a timezone-aware type.* Rejected: MariaDB has no such type for this
  purpose. `TIMESTAMP` would convert on read according to the session timezone, which is the
  server-dependence FR-003 exists to remove.

---

## R3 — Where does "now" come from: keep the `func.now()` defaults, or move them into Python?

**Decision: move them into Python.** `default=func.now()` becomes `default=utc_now`, and
`onupdate=func.now()` becomes `onupdate=utc_now`, in `app/database.py`.

**Rationale**: FR-003 requires that the basis not depend on the database server's timezone
configuration. As long as any timestamp is produced by the server, that requirement is satisfied
only by a coincidence of deployment. Moving the defaults into the application makes the
requirement structurally true, gives FR-012 its single place, and — as a side effect worth
having — makes the defaults exercisable in a unit test without a database.

**This is not a schema change.** `default=` in SQLAlchemy is client-side: it is evaluated when
the INSERT is built, not declared in DDL. Swapping a SQL expression for a Python callable
changes what value the INSERT carries and nothing about the table. No Alembic revision is
required, which keeps this feature clear of Principle V's migration machinery entirely.

---

## R4 — The migrations declare `server_default=sa.func.now()`. Does that need dropping?

**Finding**: four tables carry a real DDL default — `products`, `purchases`,
`product_identifiers`, `product_attachments` (`migrations/versions/b1a0c0d1000*.py`). It renders
as `DEFAULT current_timestamp()` and is evaluated by the server, in server time.

(The `server_onupdate=sa.func.now()` arguments alongside them emit no DDL at all. SQLAlchemy
treats `server_onupdate` as a hint that something outside the ORM maintains the column; it does
not generate MariaDB's `ON UPDATE CURRENT_TIMESTAMP`. They are documentation, and inaccurate
documentation at that.)

**Decision: leave the DDL defaults in place; do not write a migration.**

**Rationale**: after R3 the ORM always supplies a value on INSERT, so the server default is
never reached. Every write path in this application goes through the ORM — there is no raw
`INSERT` anywhere in `app/`. Dropping the defaults would mean an Alembic revision, a `downgrade`
that has to be exercised on MariaDB (Principle V), and a schema change, all to remove a code
path that cannot execute. Principle I says do not.

**What guards it instead**: a unit test asserting that a row inserted through the ORM carries
the value the application clock returned. If a future change ever stopped supplying it, that
test fails rather than the value silently reverting to server time.

---

## R5 — Which timestamps are calendar dates that must not move?

**Finding**: five call sites default a value that is a *day*, not an instant:

| Site | Value | Why it is a day |
|---|---|---|
| `app/catalog_service.py:1151` | `order_date` default | already `.replace(hour=0, minute=0, second=0, microsecond=0)` — explicitly a midnight-anchored day |
| `app/catalog_service.py:1620` | `received_date` default | rendered `%Y-%m-%d` everywhere it appears |
| `app/catalog_service.py:2072` | arrival-date fallback | feeds `_resolve_arrival_date`, compared against an operator-stated order date |
| `app/models.py:1438` | year for a bare "14 Mar" order date | the year *the operator is in* when reading a vendor page |
| `app/main/routes.py` purchase-date form parsing | `purchase_date` | typed by the operator as a day |

**Decision: these stay on local time and are marked as deliberate at the call site by calling
`local_now()` rather than `datetime.now()`.**

**Rationale**: converting them would shift every evening entry onto the following day. An order
captured at 21:00 EDT would record as the 3rd when the operator placed it on the 2nd, and the
order listing would show the wrong day — trading an invisible defect for a visible one. These
values are the operator's assertion about their own calendar; UTC is not a more correct way to
express that, it is a wrong one.

The reason to route them through a named helper rather than leave `datetime.now()` in place is
that after this feature a bare `datetime.now()` in a service is a bug by default. Making the
five deliberate ones say `local_now()` is what keeps the next sweep from converting them.

---

## R6 — What happens to rows written before the fix?

**Finding, and this is the one genuinely unpleasant consequence of the fix**: the stock-age
lines are correct today. They are correct because both halves of the subtraction are local —
`datetime.now() - self.quantity_updated_at` at `app/database.py:967`. Moving the read side to
UTC while the stored value stays local makes those rows read as **older than they are, by the
UTC offset** — four or five hours, depending on the season.

Direction matters: local time here is *behind* UTC, so a pre-fix count reads too old rather
than as a future date. It does not hit the `days < 0 → 'just now'` guard.

**Decision: accept it. No migration.**

**Rationale**: the offset in force when each row was written was never recorded, so the
correction is not derivable for the general case, and a row written inside a daylight-saving
transition is ambiguous even in principle. The error is bounded by one offset and it decays into
irrelevance immediately: these ages are rendered as "N hours ago", "yesterday", "N days ago",
"N months ago" for the purpose of judging whether a count is stale. Four hours can move a
render across the "yesterday" boundary on the day of deployment and is noise thereafter. Buying
that back would cost an Alembic revision, an exercised `downgrade`, and a decision about DST
that has no right answer.

**What must be said out loud**: the operator should expect ages on already-counted products to
jump by roughly the UTC offset once, on deploy. That belongs in the quickstart, not in a
surprise.

**Alternative considered**: a one-time `UPDATE products SET quantity_updated_at = CONVERT_TZ(...)`
for rows written before the deploy. Rejected on the ambiguity above, and because the spec
already fixed the no-migration decision.

---

## R7 — Are the log and report timestamps in scope?

**Finding**: seven `datetime.now()` sites are neither persisted to a table nor compared against
one — `app/logging_config.py:274,336` (audit log lines), `app/export_service.py:457`,
`app/export_schemas.py:211,220,225` (report headers and message prefixes),
`app/main/routes.py:1128` (a `last_updated` label in a JSON response body).

**Decision: out of scope. They stay local and keep using `datetime.now()`.**

**Rationale**: FR-001 enumerates recorded columns. These are labels a person reads — "this
report was generated at", "this log line happened at" — and they are self-consistent with each
other. They are never subtracted from a stored value and never sorted against one. Converting
them would hand the operator UTC in their own log files to fix a defect nobody has, which is the
scope creep Principle I names. This is a line worth writing down rather than leaving to the
next reader's judgment, because a sweep is exactly the kind of change that eats these by
accident.

---

## R8 — `date_added` orders item history. Is history currently mis-ordered?

**Finding**: `date_added` is not a decorative column. It selects rows under Principle VI:

- `app/mariadb_inventory_service.py:226` — history for a JA ID, oldest first
- `:267`, `:889` — "the current row" via `desc(date_added), desc(id)`
- `:1159` — "the most recent inactive row" for `activate_item`

**Is it wrong today?** No — and only by geography. Every value that actually reaches
`inventory_items.date_added` is UTC (R1), and even if the dead local write at
`app/main/routes.py:2472` were live, local time here is behind UTC, so a row created on the
local clock and a later row created on the UTC clock would still sort in the right order. **East
of Greenwich the same code inverts history**: the first row would carry a timestamp ahead of the
second, `desc(date_added)` would return the superseded row as current, and one JA ID would
present the wrong active item.

**Decision**: this is the strongest reason the sweep covers `inventory_items` even though
nothing there is observably broken, and the reason the existing active-status and history e2e
tests are a required gate for this feature rather than an optional one.

---

## R9 — How does a test catch this deterministically?

**The obvious test does not work.** Unit tests run against SQLite, whose `CURRENT_TIMESTAMP` is
UTC, so "create a product, count it, assert the two timestamps agree" does reproduce the bug —
but only on a machine whose local time is not UTC. On a CI runner set to UTC it passes against
the unfixed code. A regression test that passes on the bug is worse than none.

**Decision: two tests, one for each half of the requirement.**

1. **Basis test** — force the process timezone to a non-UTC zone for the duration of the test
   (`os.environ['TZ'] = 'America/New_York'; time.tzset()`, restored by the fixture), then create
   a product and set a count on it. Assert every recorded timestamp on the row falls within a
   minute of every other. This fails on today's code *because* the timezone is forced, and
   passes after the fix regardless of what the runner is set to. It is the test that would have
   caught the reported bug.
2. **Single-source test** — patch the application clock to a fixed sentinel instant and assert
   that every recorded column on a newly written row equals the sentinel. This is deterministic
   with no timezone manipulation, it proves FR-002 and FR-012 directly (nothing bypasses the
   helper, including the column defaults), and it is the test that fails when someone adds an
   new recorded timestamp on the wrong clock.

The calendar-date requirement (FR-008) gets the same treatment as (2): patch `local_now()` to a
fixed evening instant and assert the stored `order_date` is that day. Asserting against a real
evening would be a test that only fails after 20:00.

---

## R10 — What has to change in the existing test suite?

**Finding**: `tests/e2e/test_stock_age.py:26` (`days_ago`) and `tests/e2e/test_reorder_view.py:236,239`
seed backdated ages from `datetime.now()`. After the fix the read side is UTC, so these seeds
are off by the offset.

**Decision**: retarget the helpers onto the application clock. The assertions themselves need no
change — the ages under test are 9, 100, 400 and 800 days, and none is within four hours of a
rendering boundary — but a seed on the wrong clock is the same defect this feature exists to
remove, and leaving it in the suite would be writing the bug down as the expected shape.

**No new e2e test is warranted.** SC-004 is already covered end-to-end by
`test_receiving_does_not_reset_a_counted_age`, and Principle IV's cost argument applies: the
suite is at 13m 45s for 602 tests, and everything this feature needs to assert is assertable in
the sub-second unit suite. The e2e gate here is *the existing tests still passing*, particularly
the active-status and history tests R8 puts in the path.

---

## Summary of decisions

| # | Decision |
|---|---|
| D1 | Common basis is **naive UTC**, produced in Python, for every persisted recorded timestamp. |
| D2 | One module, `app/utils/clock.py`, exposing `utc_now()` (recorded instants) and `local_now()` (stated calendar days). |
| D3 | Column defaults move from `func.now()` to the Python callable. No DDL change, no Alembic revision. |
| D4 | The existing `server_default` DDL stays; it becomes unreachable and a test proves it. |
| D5 | Calendar-date defaults stay local, and say so by calling `local_now()`. |
| D6 | Pre-fix rows are not migrated; their ages shift by the UTC offset once, which is documented rather than fixed. |
| D7 | Log, report and response-label timestamps are out of scope and stay local. |
| D8 | Dead `datetime.now()` writes in `app/main/routes.py` are removed rather than converted. |
| D9 | Regression coverage is two unit tests — a forced-timezone basis test and a patched-clock single-source test — plus retargeted seeds in the two e2e files that backdate ages. |
