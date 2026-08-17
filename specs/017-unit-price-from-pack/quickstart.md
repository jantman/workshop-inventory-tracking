# Quickstart: Unit Price From a Multi-Pack

How to run and validate this feature. Details of the rule live in
[contracts/README.md](contracts/README.md); this is the run guide.

## Prerequisites

The repository virtualenv, and `python3.13` on `PATH` for nox:

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
```

All commands run from the repository root. Use `venv/bin/nox` rather than activating the
virtualenv.

## Automated validation

```bash
venv/bin/nox -s tests                 # unchanged by this feature; must stay green
venv/bin/nox -s e2e                   # the feature's tests live here (allow 15 minutes)
venv/bin/nox -s screenshots_headless  # capture.html changed; regenerate order_capture.png
venv/bin/nox -s screenshots_verify
```

`nox -s e2e` needs a 15-minute timeout on whatever runs it, and it must leave the working tree
clean. The screenshot sessions are the ones that write into `docs/images/screenshots/`; the
regenerated `user-manual/order_capture.png` is committed with the change.

To run just this feature's tests while iterating:

```bash
venv/bin/nox -s e2e -- tests/e2e/test_order_capture.py
```

## Manual validation

Start the application and open `http://<host>:<port>/products/capture`.

### 1. The case from issue #97

1. Paste any listing URL.
2. **Paid for the pack**: `17.99`. **Units in the pack**: `3`.
3. **Unit Price** reads `6.00` without touching it, and the line beneath says the three units
   at `6.00` do not come back to `17.99`.
4. Change the pack size to `1`: Unit Price returns to `17.99` and the note disappears.

Expected: no calculator, and the rounding is visible rather than silent (SC-001, SC-003).

### 2. The even case

Paid `29.97`, pack of `3` → Unit Price `9.99`, **no** note (FR-009).

### 3. The override

With `9.99` derived, type `9.95` over it and press **Capture**. The receive screen shows
`9.95`: what the operator typed is what is recorded (FR-004).

### 4. Recompute comes from the inputs

Derive `9.99`, type `1.00` over it, then change the pack size to `6`. Unit Price becomes
`5.00` — `29.97 ÷ 6` is `4.995`, rounded up, with the note shown — and not anything derived
from the `1.00` that was sitting in the field (FR-005).

### 5. Nothing usable, nothing destroyed

Type a unit price of `4.00` by hand, then put `0` in the pack size. The pack size is called
out as unusable and `4.00` is still in the Unit Price field (FR-011).

### 6. Across a question

Capture the same listing twice. On the second, with a pack price and pack size filled in, the
duplicate warning comes back and both fields — and the derived unit price — are still on the
page (FR-012).

### 7. The single-unit capture is untouched

Capture a listing without touching either pack field. The price recorded is the extracted
price, exactly as before this feature (FR-015, SC-005). Worth doing with the bookmarklet as
well as the paste box, since the bookmarklet is the path that prefills.

### 8. Without JavaScript

Disable JavaScript and load the page. The form still renders, Unit Price is still prefilled
from the listing, and a capture still records it. The pack fields simply do nothing.

## What to check in the diff

- No Alembic revision, and no change under `app/database.py` or `app/models.py` — this feature
  stores nothing (FR-014).
- No `parseFloat`, `toFixed`, or arithmetic on a `Number` anywhere in
  `app/static/js/pack-unit-price.js` (Principle III).
- `product_capture` unchanged: neither `pack_price` nor `pack_size` is read there.
- No `wait_for_timeout` or `networkidle` in the new e2e tests (Principle IV). The recompute is
  synchronous, so `expect(locator).to_have_value(...)` is the whole wait.
