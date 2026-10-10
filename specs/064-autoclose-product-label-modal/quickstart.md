# Quickstart: verifying the auto-close

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e -- \
  tests/e2e/test_label_print.py tests/e2e/test_bulk_label_printing_products.py \
  tests/e2e/test_order_bulk_actions.py tests/e2e/test_outstanding_products.py
```

## By hand (TESTING mode short-circuits the printer)

1. **Product detail**: open a product, choose **Print Label**, pick a stock, and press
   **Print**. The success message shows, and about 2 s later the dialog closes. Reopen it: no
   message, and the count is 1.
2. **Products**: tick two products, choose **Print Labels**, pick a stock, and print. You see
   `Complete: 2 labels for 2 products, 0 failed`, then the dialog closes.
3. **Order page** and **Outstanding Products**: same as step 2, from the line checkboxes.
4. **Failure**: with the printer unreachable (or a failing request), the bulk dialog stays
   open showing the failures until **Done** is pressed.
5. **Inventory list** bulk print: still waits for **Done**, unchanged.
