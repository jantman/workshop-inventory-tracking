# Quickstart: Products Table Location Columns and Width

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e -- -k "product_search"
```

## Manual (dev server with a few products)

1. Create products: (a) category + location "Shelf A" + sub-location "Bin 3";
   (b) category, no location; (c) no category, location only.
2. Open **Products → All Products** at 1920×915. Expect columns
   `Description | Manufacturer | Category | Location | Sub-location | Quantity`, the
   table spanning nearly the full window, and no horizontal scroll bar on the table.
3. Open **Products → Needs Action**. Expect (b) and (c); (b) has a blank Location cell.
4. Resize to 768px and 390px: filters stack, the table scrolls inside its card, the
   page itself does not scroll sideways.
5. Open any other page (e.g. a product detail): width unchanged.
