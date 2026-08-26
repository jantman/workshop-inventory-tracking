# Quickstart: Whole-Order Capture for Every Vendor

**Feature**: `specs/029-whole-order-capture/` | **Date**: 2026-08-26

How to run and validate this feature. Prerequisites, the gates in the order they matter, and the
manual walks that automation cannot cover.

---

## Prerequisites

```bash
# nox needs python3.13 on PATH
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
```

Use the repository virtualenv binaries by path — `venv/bin/nox`, `venv/bin/python` — rather than
activating it.

Docker must be running for the e2e session (MariaDB), and Playwright browsers install on first
run.

---

## The gates, in order

### 1. The regression gate — run this first and often

This is the one that matters most, and it is the whole safety argument for Phase A. The existing
DigiKey and McMaster suites are the **specification of the behaviour being consolidated**.

```bash
venv/bin/nox -s tests -- tests/unit/test_digikey_capture.py \
                        tests/unit/test_digikey_receive.py \
                        tests/unit/test_digikey_failures.py \
                        tests/unit/test_digikey_client.py \
                        tests/unit/test_mcmaster_capture.py \
                        tests/unit/test_mcmaster_receive.py \
                        tests/unit/test_mcmaster_routes.py \
                        tests/unit/test_mcmaster_payload.py
```

**These files must not be edited.** If a shared implementation cannot satisfy them as written,
the seam is in the wrong place — re-cut it rather than adjusting the tests. That rule is
research.md §14 and it is what SC-011 measures.

### 2. Unit suite

```bash
venv/bin/nox -s tests
```

Sub-second, network blocked. New: `tests/unit/test_amazon_capture.py`,
`tests/unit/test_order_vendors.py`.

### 3. E2E — **run it detached**

```bash
nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
# then poll /tmp/e2e.log
```

**The suite takes about 13m 45s warm and most agent bash tools cap at 10 minutes**, so a
foreground run reports a false timeout on a passing suite. Budget 20 minutes cold.

Running an e2e session must leave the working tree clean — screenshot tests are excluded by the
session's own marker expression (`-m "e2e and not screenshot"`).

### 4. Screenshots — required, because templates change

```bash
venv/bin/nox -s screenshots_headless
venv/bin/nox -s screenshots_verify
```

This feature replaces `digikey_order_review.html`, `mcmaster_order_review.html`,
`digikey_order.html` and `mcmaster_order.html` with one pair, and adds `orders.html`. CI blocks
merge on stale screenshots. Screenshots churn every run — check what actually changed before
committing the lot.

### 5. Style (advisory)

```bash
venv/bin/nox -s lint
```

New code should satisfy it. Do not mass-reformat existing files.

---

## Validating Phase A (consolidate) — no user-visible change

The point is that **nothing changed**. Gate 1 is the test. Beyond it:

1. Capture a DigiKey order by sales order number; confirm the review renders as before and the
   purchases land identically.
2. Open a captured McMaster order; confirm the pack figures still show.
3. Scan a DigiKey bag label for an order with two outstanding lines of the same part; confirm it
   still lands where it did.

---

## Validating Phase B (Amazon capture)

**Automated**: `tests/e2e/test_amazon_order.py` against the committed fixture. The fixture is
served from the application's own origin, which is why dispatch keys on the path rather than the
hostname.

**The fixture must retain realistic recommendation markup.** A stripped-down fixture stops
catching the trap that matters — a 4-line order page carries ~26 `/dp/` links across ~9 ASINs,
and only row-scoped extraction gets 4 (research.md §4). Assert the **line count**, not just that
some lines were read.

**Manual walk** (needs a real signed-in browser — automation cannot cover it):

1. Open a real multi-line Amazon order at `/your-orders/order-details?orderID=…`.
2. Click the capture bookmarklet.
3. Confirm the review lists **exactly** the ordered items — no recommendations — with the right
   quantities and unit prices, and states how many lines it read.
4. Exclude a line, edit a description, confirm.
5. Verify one outstanding purchase per included line, each carrying the order number, the line
   number and the ASIN.
6. Re-run the capture on the same order: every line reads as already captured and nothing new is
   written.

### The one open task

**Confirm how a quantity greater than 1 renders.** Ten consecutive orders in the operator's
history contained no such line, so `[data-component="quantity"]`'s non-empty rendering is
unverified (research.md §6).

To close it: open any order containing a line with quantity ≥ 2 and read that component.

```js
[...document.querySelectorAll('[data-component="purchasedItemsRightGrid"]')]
  .map(r => JSON.stringify((r.querySelector('[data-component="quantity"]')||{}).innerText))
```

Until it is closed the reader takes any digits it finds and falls back to 1. That is correct for
the confirmed case and safe for the other — the quantity is on the review and editable before
anything is written.

---

## Validating Phase C (receiving and the list)

1. Capture an order from each of the three vendors.
2. Open `/products/orders`: all three appear with vendor, number, date and outstanding count,
   most recent first.
3. Receive two lines of the Amazon order from its order screen, one with an amended quantity.
   Confirm the counted products' quantities rose by the **received** amount and any manual
   low/out flag cleared.
4. Confirm a received line cannot be received twice.
5. Confirm an order number that names nothing renders "not captured" rather than a 404.
6. Confirm the pre-existing DigiKey and McMaster order URLs still open (FR-044).

---

## Reference

* The seam: [contracts/order-vendor.md](./contracts/order-vendor.md)
* The payload and its selectors: [contracts/capture-payload.md](./contracts/capture-payload.md)
* Routes: [contracts/routes.md](./contracts/routes.md)
* Types and what a captured line writes: [data-model.md](./data-model.md)
* The Amazon investigation and the duplication measurement: [research.md](./research.md)
