# Quickstart: McMaster Order Details Checklist

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e   # ~20 min; run detached
```

Expected: the new McMaster/DigiKey order-page tests in
`tests/unit/test_order_product_details.py` and `tests/e2e/test_order_product_details.py`
pass, and the existing Amazon checklist tests pass unmodified.

## Manual (against a running app)

1. Capture a McMaster order (or record two McMaster purchases under one order reference
   on products with no specifications).
2. Open `/products/orders/McMaster-Carr/<order>`. Expect "2 of 2 product(s) still need
   details", a "missing" badge per line, and **Open listing** →
   `https://www.mcmaster.com/<part>/` in a new tab.
3. Capture that McMaster product page with the extension, choose details-only. Expect to
   return to the order with "1 of 2" and that line reading "captured".
4. Open a DigiKey order page: no checklist.
5. Open an Amazon order page: checklist unchanged, links to `amazon.com/dp/<ASIN>`.
