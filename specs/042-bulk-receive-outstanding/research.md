# Research: Bulk-Receiving Outstanding Purchases from a Backfill

**Feature**: 042-bulk-receive-outstanding | **Date**: 2026-09-06

The spec left no `[NEEDS CLARIFICATION]` markers. What follows is the reading of the existing
code that the spec's assumptions rest on, plus the decisions the plan needs settled before any
of it is written.

---

## 1. Is the capture-time path really already built?

**Finding**: Yes, and it is the thing this feature has to imitate rather than extend.

The issue asks that the capture-time path be built first and this be reconsidered afterwards.
Feature 031 shipped it. `app/templates/product/order_review.html` carries the order-level
**"This order has already arrived"** control and a per-line `arrived` box, and
`CatalogService.capture_order_lines` (`app/catalog_service.py:2042`) takes `arrived_date` and
resolves it through `_resolve_arrival_date` (`:1852`).

What is *not* built is any retroactive equivalent. `capture_order_lines` reaches an
already-recorded purchase only through the re-capture path, and there it fills an empty
`received_date` (`:2312`) — so re-capturing a whole order would in principle mark its lines
arrived. That is not a route worth taking: it requires the vendor's order page for an order from
2023, it re-reads DigiKey's part API for every line, and it rewrites product fields as a side
effect of what was meant to be a date correction. The residue the issue names is real.

**Decision**: Build the command. The capture-time path stays untouched.

---

## 2. Which date to record — the issue's one open question

**Decision**: the purchase's own `order_date`, and skip purchases that have none.

**Rationale**: 031 FR-026 already decided this for the capture-time path — blank arrival date
falls back to the order's own date, explicitly so that "a delivery from 2023 recorded as
arriving today would be wrong in exactly the way backfilling exists to avoid"
(`_resolve_arrival_date` docstring). The issue itself suggests reusing it, and one rule is worth
more here than any refinement.

The one place this feature does *not* follow 031 is the second fallback.
`_resolve_arrival_date` falls back to `now` where the vendor stated no order date at all,
calling it "the least wrong answer available rather than a good one" — it exists so a *capture*
can still complete rather than dying on a missing date. There is no capture to complete here.
An undated purchase also has nothing to compare against `--before`, so it cannot be selected by
the stated filters in the first place. Skipping it and reporting the count (FR-006) is both the
honest answer and the one that falls out of the query.

**Alternatives considered**:

- *Today's date* — rejected outright; it is the failure mode the whole backfill design exists to
  prevent.
- *An operator-supplied date applied to the whole sweep* — rejected. A sweep spans years by
  construction, so one date is wrong for all but one order in it. If the operator knows a
  specific date for a specific order, they know it for one order, and the per-purchase receive
  screen takes it.
- *Order date plus a nominal shipping delay* — rejected as invented precision. The stored value
  would look like knowledge nobody has.

**Validation**: `received_date = order_date` passes `_validate_receipt_order` (`:1843`, "nothing
arrives before it is ordered") by equality, exactly as an 031 capture with a blank arrival date
does.

---

## 3. Can `receive_purchase` be reused?

**Decision**: No. Write `received_date` directly, as `capture_order_lines` does.

**Rationale**: this is the load-bearing decision of the feature (spec US3, FR-009 through
FR-011). `receive_purchase` (`:1571`) deliberately does four things beyond setting the date:

| What it does | Why it must not happen here |
|---|---|
| `product.quantity += purchase.quantity` | Goods delivered in 2023 were consumed in 2023. Adding them now inflates every counted quantity in the catalog by years of consumption. |
| Clears `product.stock_status` and its date | A low flag set last month is a statement about today's shelf, not about a 2023 delivery. |
| Optionally moves `quantity_updated_at` (041 `counted`) | Nobody counted anything; the operator is at a terminal, not at the shelf. |
| Amends quantity, price, notes, description | Not asked for and not knowable in bulk. |

031 states the same conclusion twice in comments (`:2312`, `:2338`) and notes it is *satisfied
by construction* — "a purchase born with a `received_date` never passes through
`receive_purchase`" — with `tests/unit/test_order_backfill.py` as "the only thing that will
notice if that ever changes". This feature introduces the first path that receives an
*already-existing* purchase without going through `receive_purchase`, so it needs its own tests
making the same assertion; construction no longer covers it.

**Alternatives considered**: adding a `backfill=True` flag to `receive_purchase` that suppresses
all four behaviours. Rejected — a method whose central paragraph of behaviour is switched off by
a boolean is two methods sharing a name, and the constitution's "prefer boring, obvious code"
points the other way. Writing one column is three lines.

---

## 4. Where the logic lives

**Decision**: two methods on `CatalogService` returning a dataclass from `app/models.py`;
`manage.py` stays a thin adapter.

**Rationale**: Constitution II keeps business logic in services and out of the layers that call
them, and `manage.py` already follows the shape — `orders amazon-urls` parses arguments, calls
`app.services.amazon_order_export.summarize`, and prints `summary.render()`. Purchases are
`CatalogService`'s territory (`find_captured_orders`, `receive_purchase`, `delete_purchase` all
live there), so the sweep belongs there too and not in a new module.

**Shape**: a read and a write, not one call with a mode flag.

```
plan_outstanding_receipts(vendor=None, before=...) -> OutstandingReceiptPlan   # reads, writes nothing
apply_outstanding_receipts(plan) -> int                                        # writes, returns count
```

The split is what makes `--dry-run` (FR-015) and the confirmation (FR-016) trivial rather than
conditional: dry-run is "call the first one and stop", and confirming is "call the second one
with what you were just shown". It also makes the write explicit about *which rows* — the second
call takes the ids the operator saw, so what was listed is what gets written, and the sweep is
one `UPDATE`-per-row inside one session (FR-020).

**Alternatives considered**: a single `receive_outstanding(..., dry_run=False)`. Rejected — the
caller still needs the listing before it can prompt, so a single method means either two calls
that re-query (the listing and the write could disagree) or a callback, and a callback into a
service for a confirmation prompt is worse than either.

---

## 5. The write itself

**Decision**: a plain loop over the selected rows inside one `self._session()` block, each
setting `purchase.received_date = purchase.order_date`.

**Rationale**: `_session()` (`:149`) already commits on success and rolls back on any exception,
which is FR-020 in full — no savepoint or explicit transaction handling to add. A loop over a
few hundred rows is the boring, obvious code the constitution asks for, and it lets each
iteration re-check that the row is still outstanding and still dated rather than trusting the
ids it was handed.

**Alternatives considered**: `query.update({Purchase.received_date: Purchase.order_date})`, one
statement, correlated column-to-column. It works on both backends and is genuinely faster.
Rejected under Constitution I: there is no measurement, the row count is a backfill's worth, and
the loop is easier to read and to test.

---

## 6. Selecting rows

**Decision**:

```sql
received_date IS NULL
AND order_date IS NOT NULL
AND order_date < :before
AND (LOWER(vendor) = LOWER(:vendor))?      -- only when --vendor given
```

ordered by `order_date`, then `id`, with the product eager-loaded (`selectinload`) so rendering
the listing does not fire a query per row.

**Notes**:

- `received_date IS NULL` *is* outstanding — there is no status column to keep in step
  (`app/database.py:1038`), and the column is already indexed.
- **Case-insensitive vendor** (FR-003): `Purchase.vendor` is a free-form `String(200)` holding
  whatever recorded the row — the fixed constants `DIGIKEY_VENDOR`/`MCMASTER_VENDOR`/
  `AMAZON_VENDOR` for captures, and typed text for hand-recorded purchases. The operator typing
  `digikey` is recalling a name, not reading one, and `LOWER()` on a few thousand rows needs no
  index. Whitespace is stripped before comparison.
- **The cutoff is exclusive** (FR-004): `--before 2026-01-01` excludes anything ordered on
  2026-01-01. "Before" means before.
- **Undated rows are excluded by the comparison anyway** — `NULL < x` is unknown in SQL, so they
  drop out. Counting them takes a second small query, which is what FR-006's report needs.
- **Provenance is not part of the filter** (FR-007). A hand-recorded outstanding purchase from
  2023 is the same wrong state as a captured one, and adding
  `supplier_order_reference IS NOT NULL` would be a rule with nothing behind it.

---

## 7. Arguments, and what is deliberately not offered

**`--before` is required; `--vendor` is not.**

The cutoff is the safety rail — an order placed before it and still outstanding is almost
certainly one that arrived and was never marked — and an unbounded sweep of every outstanding
purchase in the database has no legitimate use. The vendor filter only narrows further, so
making it optional is a strictly smaller rule than requiring it.

**No `--order`, no id list, no interactive per-line selection.** The issue is explicit that
per-line handling is what the existing screens are for; the whole point of this command is not
going line by line. A mixed order is handled by narrowing the cutoff, and failing that by the
per-purchase receive screen. Adding a third selection axis is the speculative generality
Constitution I prohibits.

**`--dry-run` and a confirmation prompt, both.** The issue asks for the dry run specifically.
The prompt is not redundant with it: an operator who runs the command without `--dry-run` first
still gets to see the listing before anything is written, which is the case the dry run does not
cover.

**Date parsing**: `click.DateTime(formats=['%Y-%m-%d'])` refuses an unusable value before the
command body runs and names the offending value in its message, which is FR-019 without writing
an argument validator.

---

## 8. The issue's premise about irreversibility

The issue says "#130 means a wrong receipt cannot be undone by deleting the purchase". **That is
no longer true**: feature 032 shipped `CatalogService.delete_purchase` (`:1718`) and the route
at `app/product/routes.py:1043`. A wrongly-received purchase can be deleted.

It is still heavy — deleting loses the purchase, so recovering means re-capturing the order —
and there is no un-receive. So the dry run and the prompt stay as requirements; they simply are
not the last line of defence the issue took them for.

---

## 9. Testing

**Decision**: unit tests only, in a new `tests/unit/test_bulk_receive.py`, plus a small CLI test
using `click.testing.CliRunner`.

- **Service tests** drive `CatalogService(test_storage)` directly, the way
  `tests/unit/test_order_backfill.py` does. They cover selection (FR-002 through FR-007), the
  date rule (FR-008), and — most importantly — the three "does not happen" assertions
  (FR-009/010/011), which are the ones nothing else in the suite will catch.
- **CLI tests** use `CliRunner` against the `orders receive-outstanding` command with the
  service patched, covering dry-run, confirm, decline and the empty selection. `manage.py`
  imports `CatalogService` inside the command body (the file's established style), so a test can
  substitute it without importing a database.
- **No E2E test.** There is no page. `nox -s e2e` must still pass, and will, untouched.
- **No screenshots.** Nothing under `app/templates/**`, `app/static/css/**` or
  `app/static/js/**` changes, so the constitution's screenshot gate does not apply.

---

## 10. Documentation

`docs/user-manual.md` has a **Backfilling Past Orders** chapter ending in **Saying it already
arrived** (`:1861`), which describes the capture-time tick and states the two things it
deliberately does not do. This command is the same rule applied afterwards, so it belongs there
as a following subsection rather than anywhere else — including the two "does not do" points
restated, because an operator reaching for this command is exactly the one who will wonder why
their counts did not move.
