# Quickstart: Outstanding Products Page

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests    # unit: tests/unit/test_outstanding_products.py
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e      # e2e: tests/e2e/test_outstanding_products.py (run detached; ~20 min)
```

## Manual check

1. Record two outstanding purchases on two different orders (different vendors), plus one
   outstanding purchase with no order number. Receive one line of one of the orders.
2. Open **Products → Outstanding Products**. The three outstanding lines are listed, and
   the received line is not. The two order lines link to their order pages, and the third
   row reads "no order" and comes last.
3. Tick one line from each order, set the received date to a date after both order dates,
   and press **Receive Selected**. The page reloads with "Received 2 line(s).", and those
   rows are gone. On each order page the line shows as received on that date. A tracked
   product's count has risen by the ordered quantity.
4. Tick two lines and press **Print Labels**. The dialog lists their products, and
   printing sends one label per product.
5. Tick a line whose order date is after the date you enter, then receive. The page shows
   "Nothing was received: …" and every row is unchanged.

See [contracts/outstanding-page.md](./contracts/outstanding-page.md) for exact ids and
messages.
