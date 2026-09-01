# Quickstart: Delete a Purchase

**Feature**: `specs/032-delete-purchase` | **Date**: 2026-08-31

How to run and validate this feature. Implementation belongs in `tasks.md`; this is the
run guide.

## Prerequisites

- The repository virtualenv at `venv/`. Invoke its binaries by path — `venv/bin/nox`,
  `venv/bin/python` — rather than activating it.
- `nox` needs Python 3.13 on `PATH`:
  `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"` in front of every `nox` call.
- Docker, for the MariaDB container the E2E session brings up.
- A feature branch. This is a non-trivial code change, so it goes through a branch and a
  PR (`issues/130`), not straight to `main`.

## Automated validation

```bash
# Unit suite — sub-second, network blocked. Run this constantly.
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests

# E2E. ~13m45s warm, 15-minute constitutional allowance, so run it DETACHED and poll —
# most agent bash tools cap at 10 minutes regardless of the timeout requested.
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup venv/bin/nox -s e2e \
  > /tmp/e2e.log 2>&1 &

# Templates changed, so the screenshot gate applies. CI blocks on stale screenshots.
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify
```

Screenshots churn on every run from two generators. Look at what actually differs before
committing the diff rather than committing everything the run touched.

**A test session must leave the working tree clean.** `nox -s e2e` selects
`-m "e2e and not screenshot"` precisely so it does not write into
`docs/images/screenshots/`. If `git status` is dirty after an E2E run, that is a defect.

## Running the app by hand

```bash
venv/bin/python run.py        # then http://localhost:5000
```

## Manual validation scenarios

Each maps to a spec requirement. Seed a product with two purchases first — the fastest
route is the Add Item form once and the "Add a purchase to this product" button twice, or
`live_server.add_test_data` from a test.

### 1. The headline case — US1 / FR-001, FR-002, FR-003, FR-008

Open a product with two purchases. Press **Delete** on one row. The confirmation names
that purchase's vendor, order date, quantity and price — check it names the one you
pressed, not the other. Press **Cancel**: nothing changes. Press **Delete** again, confirm.
The product page returns with one row, and a flash saying what went.

### 2. Attachments — FR-004, FR-006

Attach a file to a purchase, then delete the purchase. The confirmation states the file
count before you commit. Afterwards the file is gone. A **product-level** attachment (a
datasheet) on the same product is still there.

### 3. The count does not move — FR-007

On a product with a tracked count and a received purchase: note the count, its age and any
Low flag. Delete the purchase. All three read exactly as before, and the confirmation said
so in advance. Adjust the count by hand with the +/− controls if it needed adjusting.

### 4. The order screen — US2 / FR-014, FR-015

Open **Products → Captured Orders**, then an order. Delete one line. You land back on the
order, which re-derives without it. The confirmation looked identical to the one on the
product page. Open that line's product: the purchase is absent there too.

### 5. Deleting an order's last line — FR-010

Delete every line of an order, then open that order number again. It renders "no purchase
is recorded against this order", not an error.

### 6. The derived views — FR-009

Delete an **outstanding** purchase. It disappears from the product's on-order banner, from
the reorder view's on-order figure, and from the captured-orders list.

### 7. Already gone — FR-011

Open the same product in two tabs. Delete the purchase in one. In the other, press Delete
on the row that no longer exists. You get a clear not-found, and nothing else changes.

### 8. The real reason this exists — SC-002

Reproduce #129 if it has not yet been fixed: capture an Amazon listing, then capture the
order containing it. Delete the duplicate purchase. Spend, quantity-on-order and the
reorder figure read what one purchase would have.

## References

- Requirements and acceptance scenarios: [spec.md](./spec.md)
- Design decisions and what was rejected: [research.md](./research.md)
- Tables, cascades and the transaction sequence: [data-model.md](./data-model.md)
- Routes, service signature and UI entry points:
  [contracts/purchase-delete.md](./contracts/purchase-delete.md)
