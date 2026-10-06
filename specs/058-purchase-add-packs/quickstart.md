# Quickstart: Pack Quantity on Record a Purchase

## Automated

```bash
venv/bin/nox -s tests     # unit: tests/unit/test_purchase_add_packs.py
venv/bin/nox -s e2e       # e2e: tests/e2e/test_purchase_add_packs.py (run detached; ~20 min)
```

## Manual

1. Open a product and choose **Record a Purchase**.
2. Enter Vendor `Acme`, Packs Bought `2`, Paid for the Pack `13.23` and Units in the Pack
   `100`. You should see Quantity become `200`, and Unit Price `0.13` with a "Rounded to the
   cent" note.
3. Save. The purchase history shows 200 at 0.13. The receive page for that purchase says
   "Ordered as packs of 100, 13.23 each."
4. Record another purchase, typing only Quantity `5` and Unit Price `2.00`. It records 5
   at 2.00, and the receive page mentions no pack.

See [contracts/purchase-add-form.md](./contracts/purchase-add-form.md) for the exact rules.
