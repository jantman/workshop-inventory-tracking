# Quickstart: Backfilling Past Orders

**Feature**: 031-order-backfill | **Plan**: [plan.md](./plan.md)

How to prove each slice works. Scenarios map to the spec's user stories; commands are the ones this
project actually uses.

## Prerequisites

```bash
# nox needs python3.13 on PATH
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
```

Run tests through `nox`, never `pytest` directly (Constitution IV). Use the venv binaries by path
rather than activating it.

```bash
venv/bin/nox -s tests     # unit; network blocked; well under a second
venv/bin/nox -s lint
```

`nox -s e2e` **needs a 15-minute timeout and does not fit inside a 10-minute agent Bash cap** — run
it detached and poll:

```bash
nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

Budget 20 minutes cold. A test session must leave the working tree clean; screenshot generation is
a separate session.

---

## Slice A — arrival at capture (US3)

### A1. A backfilled order is delivered, not outstanding

1. Capture any vendor's order through its normal path.
2. On the review, tick **This order has already arrived** and give a date at or after the order
   date.
3. Confirm.

**Expect**: the flash names how many lines were recorded as already arrived. The order screen shows
every line received with that date and **nothing outstanding**. `Products → Captured Orders` shows
the order as complete. `Products → Reorder List` does not mark any of its products *on the way*.

### A2. Blank date falls back, and never to today

Same, leaving the date blank.

**Expect**: every line carries the **order's** date as its received date. Not today's.
(FR-026 — the failure this guards against is a two-year-old delivery recorded as arriving today.)

### A3. A date before the order date is refused whole

Same, with a date earlier than the order date.

**Expect**: the review re-renders with the message, and **no product and no purchase exists**. The
validation runs before the session opens, so there is nothing half-written to find.

### A4. One line held back

Tick the order-level box, then untick one line's own box. Confirm.

**Expect**: that line is outstanding; every other line is delivered; the captured-orders list shows
one outstanding.

### A5. The count and the flag do not move — the point of FR-028

Before capturing, take a product whose stock is **counted** and whose **Low** flag is set by hand.
Capture an order whose line matches it, marked already arrived.

**Expect**: the purchase is delivered, and the product's on-hand quantity is **unchanged** and its
**Low flag is still set, with its original age**. This is the one place capture-time arrival
deliberately disagrees with the receive screen (research.md §2) — if the count moved, the
implementation went through `receive_purchase` and should not have.

### A6. Present-day capture is untouched

Capture an order **without** ticking anything.

**Expect**: outstanding purchases, exactly as before this feature. The gate for this slice is the
existing DigiKey, McMaster and Amazon unit suites passing **unedited**:

```bash
venv/bin/nox -s tests
```

---

## Slice B — the Amazon reduction command (US2)

### B1. Eleven rows, one order

Build a small CSV with `Order ID`, `Website` and a few other columns, where one order id repeats
across several rows.

```bash
venv/bin/python manage.py orders amazon-urls /path/to/edited.csv
```

**Expect**: that order emitted **once**; addresses of the form
`https://www.amazon.com/gp/css/order-details?orderID=...`; a summary naming rows read and distinct
orders.

### B2. A missing column is refused by name

Delete the `Order ID` column and run again.

**Expect**: a message naming `Order ID` and listing the columns it did find, a non-zero exit, and
**no addresses on stdout**. A short list is worse than none because it looks like success.

### B3. A mixed-marketplace export

Include a row whose `Website` is `www.amazon.co.uk`.

**Expect**: that order's address is built against `amazon.co.uk`, not `amazon.com`.

### B4. Digital orders drop out for free

Include a row whose order id begins `D01-`.

**Expect**: not emitted, and counted in the "could not use" line of the summary.

### B5. The addresses actually work

Paste one emitted address into the browser, land on the order, click the capture bookmarklet.

**Expect**: the existing Amazon order review, with the order's lines. This is the end-to-end proof
that FR-015 holds and that the legacy `/gp/css/` path still redirects to the one the agent runs on.

---

## Slice C — the DigiKey listing (US1's enumeration half)

### C0. Do this first — it decides whether the slice exists

One live call to `GET /orderstatus/v4/orders` with the configured credentials, recording the exact
parameter names, the response shape, and **whether a 2-legged token is accepted at all**. Write the
result into `verification.md` (research.md §5).

**If it is refused on a 2-legged token**: stop. FR-018 – FR-022 are dropped, the fallback in
research.md §5 applies, and this slice becomes a paragraph in Slice D. **Do not build a 3-legged
OAuth flow.**

### C1. The listing renders and captures

Open `Products → Capture a DigiKey Order`.

**Expect**: recent orders above the form, each with its sales order number and date. Clicking one
reaches the review that already exists — no number typed.

### C2. Not configured says so and changes nothing else

Unset the DigiKey credentials and reload.

**Expect**: the existing not-configured message, no listing, and the sales-order-number form still
present.

### C3. A failed listing leaves the form working

Point `DIGIKEY_API_BASE` at something that errors.

**Expect**: a message about the listing, and a form that **still captures by number** (FR-022).

---

## Slice D — the documentation (US1's procedure half)

### D1. Someone who has never done this can follow it

Read the new **Backfilling Past Orders** chapter cold and check it answers, for each of the three
vendors: where the order history is, how one order reaches capture, what identifies an order, how
far back the history goes, and what a backfilled record does and does not contain (FR-003, FR-004,
FR-008).

### D2. Spelling

```bash
grep -ric "catalogue" README.md docs/ app/ tests/   # must return nothing
grep -rn "catalogd\|catalogng\|uncatalogd" app/ tests/   # must return nothing
```

`specs/` and `migrations/versions/*.py` are deliberately excluded from that sweep.

---

## Full gate before merge

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
venv/bin/nox -s lint
venv/bin/nox -s tests
nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &   # poll; ~14 min warm
git status --porcelain                             # must be empty
```
