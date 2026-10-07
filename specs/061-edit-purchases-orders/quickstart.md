# Quickstart: Edit Purchases and Orders

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests -- tests/unit/test_purchase_edit.py
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e -- tests/e2e/test_purchase_edit.py
```

## Manual

1. Open a product with a captured order line. In Purchase History click the pencil; change the
   quantity and unit price; save. The row shows the new values; the product's count is unchanged.
2. Open that order (Products → Captured Orders). Click a line's pencil, fix its pack size and
   pack price, save. You land back on the order; the line is still listed, same position.
3. Record a purchase on a product by hand with no order number. Edit it, set the order number
   of an existing order from the same vendor, save. The order page now lists it.
4. On the order page click **Edit Order**; change the order date; save. Every line shows it.
   Change the order number to another order's number: refused, nothing changed.
5. Try a quantity of 0, a pack size of 1, a received date before the order date: each refused
   with the message, values still in the form.
