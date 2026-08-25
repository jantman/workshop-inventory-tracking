# Verification: McMaster-Carr Order and Product Capture

**Feature**: `specs/028-mcmaster-order-capture/` | **Implementation run**: 2026-08-25

Two halves. **Part A is done and recorded below** — the automated gates, and the
markup investigation that closed the plan's one TBD. **Part B is the manual walk
(T064)**, which needs a real order, a real box and a real HTTPS McMaster page,
and is left for the operator to fill in.

---

## Part A — what was verified automatically

### A1. The markup investigation (T001–T004)

Read off the live site on 2026-08-25 in the operator's own signed-in browser.
The findings are written up in [research.md §5 and §14](./research.md); the ones
that changed the design:

| Question | Answer |
|---|---|
| Order-page path shape (the plan's one TBD) | `/order-history/order/<24 lowercase hex>` |
| Product path | `/<part-number>/` — confirmed |
| Is there an order number? | **No.** Only the customer's *Purchase Order* string, in an editable input's `value` |
| Can the pages be fetched server-side? | **No.** Every order URL returns the same 152,129-byte client-rendered shell with no order data in it |

Two consequences the plan did not anticipate:

1. **The two page types use opposite class-name conventions.** The order card
   view has plain unhashed names (`dtl-row`, `dtl-row-specs`); product pages are
   CSS-module hashed (`_price_1y02s_5`), where the trailing hash is a build
   artifact. The two readers key on different things because the two pages
   differ.
2. **A second schema change**, resolved with the operator: the Purchase Order
   string is editable on McMaster's side and auto-generates as MMDD+SURNAME, so
   `purchases.vendor_order_id` records the stable id from the order's URL and
   re-capture pairs on it first. Without it, renaming a PO would make a
   re-capture write a duplicate purchase for every line.

### A2. Migrations, exercised both ways (Constitution V)

Against **MariaDB 11.8** in a throwaway container, with a seeded purchase
carrying values in the affected columns:

| Revision | Direction | Result |
|---|---|---|
| `c9e2a4d70318` rename `digikey_line_number` → `order_line_number` | upgrade → downgrade → upgrade | Column renamed in place each time; the seeded value (`order_line_number = 7`) intact at every step |
| `d0817b3ea45c` add `vendor_order_id` | upgrade → downgrade → upgrade | Added as `varchar(64) NULL`, dropped, re-added. The dropped column's value is gone after the round trip, which is what dropping a column means and what the revision's docstring says |

**ORM/Alembic drift check**, both times: `Base.metadata.create_all` against a
second database, then the two `purchases` tables diffed column by column —
no ORM-only columns, no Alembic-only columns, no type or nullability
differences. This matters because the unit suite builds its schema with
`create_all` and never runs Alembic, so drift passes `nox -s tests` and fails on
the real database.

### A3. The gates

| Gate | Result |
|---|---|
| `nox -s tests` | **1979 passed** |
| `nox -s e2e` | _(recorded on completion of the full run)_ |
| `nox -s lint` | Fails at baseline with ~7,565 findings, overwhelmingly `E501` at 79 columns against a codebase written to ~80. **Not a gate that passes in this repository today.** What was checked instead: `flake8 --select=E9,F` over every file this feature touched reports **nothing**. Every remaining finding is pre-existing elsewhere |
| `grep -ric "catalogue" README.md docs/ app/ tests/` | Clean (two of my own were caught and fixed) |
| `.env`, `credentials.json`, `token.json` untracked | Confirmed |

### A4. New test coverage

| Suite | Count |
|---|---|
| `tests/unit/test_mcmaster_payload.py` | 43 |
| `tests/unit/test_mcmaster_capture.py` | 40 |
| `tests/unit/test_mcmaster_routes.py` | 39 |
| `tests/unit/test_mcmaster_receive.py` | 22 |
| **unit total** | **144** |
| `tests/e2e/test_mcmaster_order.py` | 16 |
| `tests/e2e/test_mcmaster_product.py` | 10 |
| `tests/e2e/test_mcmaster_receive.py` | 6 |
| `tests/e2e/test_mcmaster_degraded.py` | 9 |
| **e2e total** | **41** |

No new pytest markers, and no `wait_for_timeout` or `time.sleep` added — the
suite still executes zero.

### A5. A defect the fixtures caught

The product page states the price and the pack in one string,
`"$13.23 per pack of 100"`. The first price parser stripped every non-digit and
kept what was left, yielding **`13.23100`** — a price a hundred thousand times
too large that still parses as a `Decimal` and would have been recorded without
complaint. It now takes the first monetary token. Pinned by
`test_the_pack_price_and_pack_size_fill_the_017_fields`.

### A6. One deliberate deviation from the spec

**US2 scenario 2** asks that a product-page capture record the part number as a
`DISTRIBUTOR` identifier scoped to McMaster-Carr. It records a **`VENDOR`**
identifier, scoped the same way, because that path goes through `capture_order`,
which has written `VENDOR` for every vendor since feature 007.

The scenario's stated purpose — "so that scanning or searching that number finds
it" — holds either way: both types are vendor-scoped and both are in
`VENDOR_SCOPED_TYPES`, so a scan finds either. Editing that shared write path to
emit a different type for one vendor was rejected because SC-010 requires it to
behave identically after this feature, and it is the path every Amazon capture
takes.

What *was* fixed is the consequence that mattered: the order review now looks up
**both** types, so an order capture recognizes a part already cataloged from its
product page instead of creating a second product for it. Guarded by
`test_an_order_capture_finds_a_part_cataloged_from_its_product_page`.

---

## Part B — the manual walk (T064) — NOT YET RUN

These are the checks only reality can make. Fill in each result and the date.

**Run date**: _______  **Against**: _______________ (deployment URL)

### B1. A real order, captured and reconciled line by line

Per [quickstart.md](./quickstart.md) §US1.

- [ ] Every line visible on McMaster's page appears on the review
- [ ] The line tally matches, or states the shortfall
- [ ] A pack-priced line shows packs, pack size and pack price, and computes
      units and a unit price from them
- [ ] Descriptions authored; one line unticked; confirmed
- [ ] One outstanding purchase per included line, carrying `McMaster-Carr`, the
      Purchase Order name, the line number, units and unit price
- [ ] **Abandon test**: bookmarklet again, close the tab without confirming —
      nothing written
- [ ] **Re-capture test**: every line reads as already captured; confirming
      records nothing

Notes:

### B2. A re-capture of an order that changed

- [ ] A changed quantity or price is shown against what is recorded
- [ ] It is applied only on the operator's say-so
- [ ] A purchase no line claims is reported and not deleted
- [ ] **Rename test** (the reason `vendor_order_id` exists): rename the Purchase
      Order on McMaster, re-capture, and confirm the order is still recognized
      rather than duplicated

Notes:

### B3. A real bag, scanned and received

Per [quickstart.md](./quickstart.md) §US3.

- [ ] Scanning a part number lands on **its receipt**, not the product page
- [ ] Amending the quantity and confirming receives it; the counted quantity
      rose; any low-stock flag cleared
- [ ] Scanning it again falls through to ordinary behaviour
- [ ] Two-candidate case offers the chooser and receives nothing by arriving

Notes:

### B4. A single real part

- [ ] The confirmation form arrives carrying part number, description, price,
      pack size, specifications and image, with nothing typed
- [ ] **Images**: whether McMaster's image host serves bytes to a plain
      server-side GET from the LAN is **unknown and unmeasured**. research.md
      §12 says an image host that refuses costs the pictures and nothing else.
      Record what actually happened here — this is the first real measurement:

      Images offered: ____  stored: ____  refused: ____

- [ ] The paste-a-URL path yields vendor and part number from the address alone

Notes:

### B5. The cross-origin transport — the half no local test can reach

**This is the single most important manual check.** The e2e harness serves every
fixture from the application's own origin, so the real path — a McMaster page
over HTTPS submitting a form to this app over plain HTTP on the LAN — is
exercised nowhere but here.

- [ ] The bookmarklet, clicked on a real McMaster **order** page, opens a tab on
      this app carrying the order
- [ ] The bookmarklet, clicked on a real McMaster **product** page, does the same

If it does nothing, check the scheme and port in the bookmarklet's own address
first: a proxy that does not send `X-Forwarded-Proto` / `X-Forwarded-Port` hands
out a bookmarklet pointing at nothing (issues #89, #114).

Notes:

### B6. SC-010 by hand

- [ ] Scanning an Amazon ASIN still opens its product page and nothing new

Notes:
