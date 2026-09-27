# Quickstart: McMaster Details-Only Capture

## Automated

```bash
nox -s tests -- tests/unit/test_mcmaster_details_only.py tests/unit/test_mcmaster_routes.py \
  tests/unit/test_order_product_details.py
nox -s tests          # full unit suite
nox -s e2e            # detached; ~20 min warm (see CLAUDE.md)
```

Expected: all pass. `test_mcmaster_details_only.py`'s US1 tests fail on `main`.

## Manual (the reported case)

1. With the extension installed, capture a McMaster order containing part *P* and confirm it.
2. Open `https://www.mcmaster.com/P/` and capture it.
3. **Expect**: the confirmation page names the product the order created and offers
   "add the listing's details, record no purchase", with the order named (044 FR-009) —
   not only "This is a separate order — record it anyway".
4. Choose details-only and submit. **Expect**: the listing's specification rows and photos on
   the product; no new purchase on it; you are returned to the order.
5. Reverse direction: capture a product page for a part *Q* not yet in the catalog, recording
   the purchase, then capture it again. **Expect**: details-only is offered for the product
   the first capture made, and that product's part number reads as a *Distributor*
   identifier for McMaster-Carr on its product page.
