# Quickstart: Bulk Set Category

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e   # detached; ~20 min
```

Covered by `tests/unit/test_bulk_set_category.py` and `tests/e2e/test_bulk_set_category.py`.

## Manual

1. **Products**: tick two products and choose **Set Category**. Type `ele` and check that
   existing categories are suggested. Enter `Tools / Hand` and confirm. The page reloads with
   "Set category "tools/hand" on 2 products.", both rows show `tools/hand`, nothing is ticked,
   and any filters are still applied.
2. **Blank**: open the dialog and confirm with nothing typed. An error shows in the dialog,
   and the boxes stay ticked after you cancel.
3. **Order page**: open a captured order, tick two lines (including two lines for the same
   product if there are any), and set a category. The flash counts distinct products, nothing
   is ticked, and receipt state is unchanged.
4. **Outstanding Products**: tick lines from two orders and set a category. Both products
   change and both lines are still listed.

See [contracts/set-category.md](./contracts/set-category.md) for the endpoint and element ids.
