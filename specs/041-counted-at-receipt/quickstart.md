# Quickstart: Validating "I Counted the Shelf" at Receipt

**Feature**: `specs/041-counted-at-receipt` | **Date**: 2026-09-06

How to run this feature and see, by hand and in the suite, that both paths through the receive
screen do what they claim. For the parameter and rendering contracts these scenarios check, see
[contracts/receive-purchase.md](./contracts/receive-purchase.md).

## Prerequisites

* The repository virtualenv, and `python3.13` reachable for nox:
  ```bash
  export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
  ```
* Nothing else. No migration to apply — this feature changes no schema — and no new dependency
  to install.

## Automated validation

```bash
# Unit: the service rule, both paths, and the corners (contract tests C1-C8)
venv/bin/nox -s tests

# E2E: the operator ticking the real control on the real screen
venv/bin/nox -s e2e
```

**The E2E session needs a 15-minute tool timeout and takes roughly 14 minutes warm, which is
longer than most agent shells allow.** Run it detached and poll:

```bash
nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
# then poll /tmp/e2e.log
```

Because `app/templates/**` changed, the screenshot gate applies:

```bash
venv/bin/nox -s screenshots_headless
venv/bin/nox -s screenshots_verify
git status --short docs/images/screenshots/
```

No documentation screenshot shows the receive screen, so the expected result is that no PNG
differs. `metadata.json` churns on every run regardless — leave it alone unless an image
actually changed.

The tests that matter most:

| Where | Asserts |
|---|---|
| `tests/unit/test_stock_status.py` | The ticked and unticked service paths, the untracked product, the quantity-less receipt, the second receipt, the zero count, the flag, and the refusal |
| `tests/unit/test_stock_status.py` (existing, unedited) | That the default path is unchanged — roughly two dozen existing `receive_purchase` call sites across the unit suite pass no `counted` and must keep passing |
| `tests/e2e/test_stock_age.py::test_receiving_does_not_reset_a_counted_age` (existing) | The unticked screen path, unchanged |
| `tests/e2e/test_stock_age.py` (new) | The ticked screen path end to end |

## Manual validation

```bash
venv/bin/python app.py    # then browse to the LAN address it prints
```

### Scenario 1 — the assertion made (spec Story 1)

1. Create a product, set a tracked count of `4`, and note the age reads *counted just now*.
2. Record a purchase against it for a quantity of `100`, leaving the received date blank so it
   stays outstanding.
3. From the product page (or the reorder list, or a scanned bag) open **Receive**.
4. Confirm the checkbox is present, unticked, and worded as a claim about the shelf.
5. Tick it and press **Mark Received**.
6. **Expected**: the product page shows `104`, and the age reads *counted just now*.

To see the age actually move rather than start from now, backdate it first — the age display is
what makes this visible:

```bash
venv/bin/python - <<'PY'
from datetime import timedelta
from app import create_app
from app.database import Product
from app.utils.clock import utc_now
# ... open a session against your dev database and set
#     product.quantity_updated_at = utc_now() - timedelta(days=100)
PY
```

The E2E suite does this through `live_server.backdate_product(product_id,
quantity_updated_at=...)` (`tests/e2e/test_server.py:259`), which exists precisely because a
months-old age is unreachable through the UI.

### Scenario 2 — the assertion not made (spec Story 2)

1. Backdate a tracked product's count age as above, so the product page reads e.g. *counted 3
   months ago*.
2. Receive an outstanding purchase for it **without** touching the checkbox.
3. **Expected**: the count rises by what arrived, and the age still reads *counted 3 months
   ago*. This is feature 008's behaviour and it must be bit-for-bit unchanged.
4. Open **Receive** for another purchase. **Expected**: the checkbox is unticked. The choice is
   never remembered.

### Scenario 3 — the control is not offered where it would do nothing (spec Story 3)

1. Receive a purchase against a product whose count is **not tracked**.
2. **Expected**: no checkbox on the screen, no count created, no age recorded.
3. Now set that product's count to `0` and open Receive again. **Expected**: the checkbox *is*
   shown — zero is a counted number, not an absence.

### Scenario 4 — a refusal keeps the tick (spec FR-009)

1. On a tracked product's receive screen, tick the checkbox and type something invalid into
   **Unit Price**.
2. Press **Mark Received**.
3. **Expected**: the page comes back with the error, the checkbox still ticked, and — on the
   product page — no change to the count or its age.

### Scenario 5 — a second submission (spec FR-010)

1. Receive a purchase, then open its receive screen again. The green banner says it was already
   received.
2. Tick the checkbox and submit.
3. **Expected**: the received date is unchanged, the count is unchanged, and the age reads
   *counted just now* — the operator said they looked, and they did.

## What should not have changed

* The manual **Low**/**Out** flag is still cleared by a first receipt, with its date, ticked or
  not.
* The reorder list's membership and ordering.
* The wording of any age, anywhere.
* Any count reached through the product page's number entry or its `+`/`−` buttons.
* `specs/008-trustworthy-stock-age/`'s carve-out, which still governs every receipt where the
  operator does not tick the box.
