# Quickstart: Bulk Receive and Bulk Label Printing on the Order Page

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests   # unit: test_order_bulk_receive.py
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e     # e2e: test_order_bulk_actions.py (run detached, ~20 min)
```

## Manual

1. Open any captured order with several outstanding lines, e.g.
   `/products/orders/Amazon/<order>`.
2. Tick two lines, leave the date blank, press **Receive**. Expect: back on the same page,
   "Received 2 line(s).", those two show *received* today, the rest *outstanding*, and a
   counted product's quantity risen by its ordered quantity (count date unchanged).
3. Tick a received line and an outstanding one, set a date, **Receive**. Expect
   "Received 1 line(s). 1 already received, skipped."
4. Tick an outstanding line and set a date before the order date. Expect an error and no
   change.
5. Tick two lines naming the same product plus one other, press **Print Labels**. Expect the
   dialog to list two products; printing sends two label requests.

Contract details: [contracts/order-bulk-actions.md](./contracts/order-bulk-actions.md).
