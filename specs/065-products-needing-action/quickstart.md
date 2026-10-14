# Quickstart: Products Needing Action

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -r -s e2e -- tests/e2e/test_product_search.py
```

## Manual

1. Have four products: one with category and location, one with no category, one with no
   location, one with neither.
2. Open **Products → Needs Action**. Expect the last three, with the *Missing* filter showing
   "Category or location".
3. Change *Missing* to "No category" and apply: the two without a category.
   "No location": the two without a location.
4. On "No category", tick a product, **Set Category**, apply. After the list reloads, the
   product is gone from it.
5. `/products?missing=banana` shows an error naming the valid values.

Contract: [contracts/missing-filter.md](contracts/missing-filter.md).
