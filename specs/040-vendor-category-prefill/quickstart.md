# Quickstart: Proving the Four Doors Are Shut

## Prerequisites

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
```

Run everything through `nox`, never `pytest` directly (Constitution IV).

## By test

```bash
venv/bin/nox -s tests          # unit suite, network blocked; under a second
venv/bin/nox -s lint
venv/bin/nox -s e2e            # ~14 minutes warm; run it detached and poll
```

The `e2e` session outlasts a 10-minute agent bash timeout. Run it with `nohup`/background and
poll, or a passing run reports as a false timeout.

### What the tests must show

| Door | Test | Assertion |
|---|---|---|
| Order capture | `tests/unit/test_digikey_capture.py` | A product created by capturing an order has an empty `category_path`, while its manufacturer and specification rows are still filled |
| Enrichment | `tests/unit/test_order_enrichment.py` | A matched product with a blank category still has a blank category after capture; its manufacturer and specifications were filled |
| Single-part page | `tests/unit/test_product_routes.py` + `tests/e2e/test_digikey_part.py` | The rendered page has exactly one `category_path` input, visible and empty; the part's category still appears in the read-only detail list; creating without typing yields an uncategorized product |
| Scan prefill | `tests/unit/test_product_routes.py` | The Add Product form opened by a scan of an unknown part has an empty Category input, while its other pre-loaded values are unchanged |

## By hand

Start the app and drive it as the operator would.

1. **Order capture.** Open `/products/categories` and note the tree. Capture a DigiKey order with
   at least one line whose part detail states a category. Reopen `/products/categories`: the tree
   is identical. Open one of the created products: Manufacturer is filled, the specification rows
   are there, and no Category row is shown at all.
2. **Single-part capture.** Products → Capture a DigiKey Part. Look up a part. "What DigiKey says"
   still lists their Category. Below, the form now has an empty Category box with the shop's own
   suggestions in its dropdown. Create without typing → the product is uncategorized. Do it again
   typing `electronics/power/power supplies` → that is the product's category, and the tree gains
   that branch and no other.
3. **Enrichment.** Create a product by hand carrying a manufacturer part number that appears in a
   DigiKey order, leaving its category blank. Capture that order. The product gains the
   manufacturer and the specification rows; its category is still blank.
4. **Scan prefill.** Scan (or hand-build the URL for) a bag whose part the catalog does not hold.
   The Add Product form opens carrying the description, part numbers and specifications, and an
   **empty** Category box.

## What must not happen

- No capture asks a new question, shows a new warning, or fails because a category is absent.
- No category already recorded on an existing product changes.
- `/products/categories` gains no branch that nobody typed.
- Running a test session leaves the working tree clean — screenshot tests are excluded from `e2e`.
