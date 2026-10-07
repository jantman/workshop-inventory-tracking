# Quickstart: verifying free-text product locations

Run the product move e2e tests:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e -- tests/e2e/test_product_move.py
```

Expected: all pass, including the new scenarios:

1. **Preselected** (`/products/move?code=<WIT…>`, or the product page's Move button): scanning
   `eShop Shelf3` queues the product for `eShop Shelf3`, a following `Top Bin` becomes its
   sub-location, and executing records both.
2. **Hand-scanned**: code, `WoodshopShelf`, `Drawer 2`, `>>DONE<<` queues a row for
   `WoodshopShelf` / `Drawer 2`.
3. **Still refused**: free text before any code, and a JA label, are both refused. No product-page
   warning mentions `M*, T*, or Other`.
4. **Item page**: `tests/e2e/test_move_items*.py` and `test_bulk_move_handoff.py` pass unchanged.
