# Quickstart: validating the handheld screens

## 1. Unit tests

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
```

Expected:
- `tests/unit/test_scan_routes.py`: the existing cases are unchanged. The new cases return
  `/h/…` URLs for `item`, `product` and the three `receive` landings when `handheld: true`,
  and desktop URLs for `create` and `search`.
- `tests/unit/test_handheld_routes.py`:
  - every GET in `contracts/handheld-routes.md` renders 200, or 404 where the contract says so
  - `/h/item/<missing>` and `/h/item/<inactive>` render their stated messages with the
    desktop link
  - `/h/orders` lists only orders with outstanding lines, with correct counts
  - `POST /h/receive/<id>` receives the purchase and redirects to `/h/product/<pid>`
  - `POST /h/shorten` shortens and keeps history (inactive row retained)
  - `POST /h/orders/<v>/<o>/receive` receives exactly the posted ids
- The existing `test_product_routes.py`, `test_mcmaster_routes.py` and
  `test_order_receive.py` pass unchanged after the helper extractions.

## 2. E2E tests

The full suite takes **about 17 minutes warm**, more than the 10-minute Bash cap, so run it
detached and poll:

```bash
# just the new handheld tests (minutes, not a quarter-hour)
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup venv/bin/nox -s e2e -- \
    tests/e2e/test_handheld_landing.py tests/e2e/test_handheld_product.py \
    tests/e2e/test_handheld_move.py tests/e2e/test_handheld_item.py \
    tests/e2e/test_handheld_shorten.py tests/e2e/test_handheld_receive.py \
    tests/e2e/test_handheld_orders.py \
    > "$SCRATCH/e2e-handheld.log" 2>&1 &

# or by keyword
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup venv/bin/nox -s e2e -- -k handheld \
    > "$SCRATCH/e2e-handheld.log" 2>&1 &

# the whole suite, before merge (FR-025 / SC-006: every desktop test passes unchanged)
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup venv/bin/nox -s e2e \
    > "$SCRATCH/e2e-full.log" 2>&1 &
```

`$SCRATCH` is the session scratchpad. Check the log tail for the pytest summary line.

Every handheld test uses the `handheld_page` fixture: a 360×512 viewport with
`has_touch=True` and `is_mobile=True`. Scans are delivered as `page.keyboard.type(code)`
followed by `page.keyboard.press("Enter")`, with nothing tapped first. Each screen's test
calls `assert_handheld_layout(page, scan, primary)` (FR-006, FR-007).

| File | Scenarios |
|---|---|
| `test_handheld_landing.py` | US1 1–6: a JA ID goes to `/h/item/…`; a WIT code and a retail GTIN go to `/h/product/…`; a single-line distributor label goes to `/h/receive/…`; an unknown GTIN goes to the desktop create form; free text goes to the desktop search; the landing layout; a scan from `/h/product/…` lands like a scan from the landing page. |
| `test_handheld_product.py` | US2 1–8: tap −, + and Set; Start and Stop counting; Low, Out and Clear (`waits.wait_for_stock_flag`), each checked on `/products/<id>`; label modal with `#product-label-print-confirm` in the viewport (FR-016); attach a file; select, Delete Selected and the in-page confirm; Move gives `/h/move?kind=products` with the product pending; Order button(s). |
| `test_handheld_move.py` | US3 1–5: two items, a location each, Validate and Execute through the in-page confirm, locations checked; `>>DONE<<`; an unknown ID is rejected while `#barcode-input` stays in the viewport and focused; the products variant; a 10-move queue with Execute still in the viewport. |
| `test_handheld_item.py` | US4 1–6: summary; label modal; add a photo (cards to_have_count) and delete it through the in-page confirm; Shorten and Move hand-offs; missing and inactive JA IDs. |
| `test_handheld_shorten.py` | US5 1–3: shorten a 1000 mm item to 600 mm; history retained (`/api/items/<ja>/history` shows the inactive row); a longer-than-current length is refused as on desktop. |
| `test_handheld_receive.py` | US6 1–5: single-line label with the label's Q pre-filled; Receive with "counted" updates the count as on desktop; multiple candidates go to `/h/receive/choose` with no receipt; nothing outstanding gives the message and nothing received twice; Receive from the product screen. |
| `test_handheld_orders.py` | US7 1–5: an order with 3 outstanding lines; select 2 cards and Receive Selected, exactly those 2 received; received lines have no checkbox; `/h/orders` lists only orders with outstanding lines; the product screen's Order button. |

Every test also asserts `inputmode="none"` on its scan entry. One test in
`test_handheld_landing.py` covers the keyboard button: tap it, `inputmode` becomes `text` and
the input is focused; type a code and press Enter; `inputmode` is back to `none` (FR-029). On
the Move page, the same test also checks `#manual-entry-mode` is checked while typing and
cleared after.

## 3. Desktop identity (FR-025)

The `base.html` blocks and the two partials extracted from `detail.html` must render the same
HTML. Before and after the change, on the same seeded database:

```bash
# with the dev server running on :5000
for u in / /inventory /inventory/move /inventory/shorten /products /products/1 /products/move; do
  curl -s "http://127.0.0.1:5000$u" | sed 's/csrf_token.*value="[^"]*"//; s/content="[^"]*"//' \
    | tr -s ' \n' > "$SCRATCH/$(echo $u | tr / _).html"
done
# repeat into a second directory after the change, then diff -r the two
```

The expected diff is whitespace only. The `.form-text` help in the product label modal gains
`d-none d-sm-block`, and that is the one intended markup change. The other checks:
- Screenshots: `nox -s screenshots_headless`. Desktop images should not change materially;
  commit only real changes.
- The full e2e suite passes with no desktop test edited.

## 4. Manual check in a desktop browser at handheld size

Use Chrome DevTools device mode at 360×512 with touch. Open `/h/`, then:
1. Type `JA000001` and press Enter. The item screen opens with no sideways scroll, and Label,
   Photos, Shorten and Move are visible.
2. Home. Type a product's `WIT…` code and press Enter. The product screen opens with − and +
   visible; tap +.
3. Move items: scan a JA ID, then `M1-A`, then `>>DONE<<`. Validate, Execute and confirm in
   the page. No browser dialog appears.
4. Open the same product on `/products/<id>` at desktop width. The label modal still shows
   both help lines.

## 5. On the device (TC52): gate before calling it done

1. DataWedge Profile0: **Keystroke output → Basic data formatting → Send ENTER key** is on.
   Code128, DataMatrix and QR are enabled.
2. Bookmark `http://<host>:5000/h/` on the home screen and set it as Chrome's home page.
3. Scan a JA ID label on `/h/` and confirm the item screen opens with **no soft keyboard**.
   This is FR-029's unverified assumption: that keystrokes reach an `inputmode="none"` field.
   If scans do not arrive, enable the DataWedge keyboard option and record the finding in
   research.md.
4. Scan a WIT label. Tap +. The keyboard stays down and focus returns to the scan entry.
5. Tap the keyboard button. The keyboard rises. Type a code and press Enter. The keyboard
   drops.
6. Move: scan JA ID, location, then a printed `>>DONE<<`. Validate and Execute.
7. Scan a **DigiKey 2D bag label** on `/h/`. It must reach `/h/receive/…` or the order
   screen. If it lands on search with a mangled scan, the control-character path in
   research.md D11 is the cause.
8. Item photos: Add opens Android's chooser with the camera offered.
