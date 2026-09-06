# Quickstart: verifying typed count entry

How to convince yourself this works, by test and by hand. Commands assume the repository
virtualenv and pyenv's Python 3.13, per `CLAUDE.md`.

## Automated

### Unit

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
```

Sub-second. `tests/unit/test_typed_quantity.py` covers everything that can be asserted without a
browser:

- **`received_total` in the detail context** — a product with two received purchases of 60 and 40
  yields 100; one received and one outstanding yields only the received one; a received purchase
  with a `NULL` quantity contributes nothing but does not suppress the others; no purchases yields
  0.
- **What is rendered from it** — the received line appears on an untracked product with a non-zero
  total, and does *not* appear when the total is zero, when there are no received purchases, or
  when the product is being counted (FR-013, FR-014).
- **The absolute-set path** — `PATCH /api/products/<id>/quantity` with `{"quantity": 40}` sets 40
  on a product previously at 3, and stamps the count date. This asserts the behavior the whole
  feature rests on; it was already possible and was never exercised from a test that resembles
  what the UI now sends.
- **The tri-state is still distinguishable** — `{"quantity": 0}` leaves the product counted, and
  only `{"quantity": null}` stops it (FR-005). The existing assertions in
  `tests/unit/test_stock_status.py` cover the service layer; these cover the endpoint.

### E2E

```bash
# needs 15+ minutes; run detached, it outlasts a 10-minute tool cap
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

`tests/e2e/test_typed_quantity.py` drives the page:

- Type 40 into `#quantity-input` on a product counted at 3, press `#quantity-set-btn`, and
  `#quantity-value` reads 40. The page reloads on success, so the rendered value is the completion
  signal and cannot predate the request (`CLAUDE.md` pattern C).
- Type 12 on an untracked product, press `#start-tracking-btn`, and it becomes counted at 12.
- Press `#start-tracking-btn` with the field untouched and it still starts at zero —
  `#quantity-value` shows the "None on hand" badge. This is the existing behavior, re-asserted
  because the field now sits next to that button.
- Clear the field on a counted product, press `#quantity-set-btn`, and `#stock-alert` appears while
  `#quantity-value` is unchanged. No reload happens on a refusal, so the alert is the signal.
- Correct the entry after that refusal and commit again, without reloading (FR-008).
- `#received-total` states 100 on an untracked product with 100 received, and is absent on a
  counted one — the absent case establishes `#quantity-value` with a positive `expect()` first, so
  it cannot pass against a page that has not rendered.

`tests/e2e/test_touch_readiness.py` gains `#quantity-set-btn` in the existing 44px selector list.
The two tests that tap through the steppers are unchanged and must stay green — they are what
proves the typed entry did not displace them.

### Screenshots

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify
git status --short docs/images/screenshots/
```

`tests/e2e/screenshot_config.yaml` has no product-detail entry, so expect no content change.
Screenshot bytes churn between runs regardless of content — inspect the diff and commit only what
actually changed.

## By hand

```bash
venv/bin/python -m flask --app app run
```

Then, on a product page (`/products/<id>`):

1. **The reported defect.** On a product that is not being counted, type `40` into the on-hand
   field and press **Start counting this**. The count reads 40 immediately, with a fresh "counted
   just now". Previously this required forty presses of `+`.
2. **Setting an existing count.** With the product counted at 40, type `12` and press **Set**. It
   reads 12.
3. **Re-verifying.** Press **Set** again without changing the field. The count is still 12 and the
   age resets to "just now" — the operator has looked again, which is what a count date means
   (FR-003).
4. **The steppers still work.** Press `−`. It reads 11. Press it down to 0 and once more: it stays
   at 0 and does not go negative.
5. **Zero is not "stop counting".** Type `0`, press **Set**. It shows the "None on hand" badge and
   **Stop counting this** is still the button offered — the product is counted, with none on hand.
6. **An empty field is refused.** Clear the field and press **Set**. A message appears in the card
   and the count is untouched. Correct it and press **Set** again without reloading; it commits.
7. **A negative or fractional entry is refused** the same way, with a message naming what is wrong.
8. **The received total.** Press **Stop counting this**, then record and receive a purchase of 100
   for this product. Back on the product page — untracked — the card states that 100 have been
   received. It is text: nothing is pre-filled, and pressing **Start counting this** with an empty
   field still starts at zero. Type `100` if that is what the shelf holds; type what the shelf
   actually holds if it is not.
9. **And it is gone once counted.** With a count in place, the received line is absent, because
   receiving already adds to a count and saying it twice invites double-counting.

### On a handheld

Open the same page on a phone, or in a browser's device emulation. Every control on the Stock card
is still thumb-sized, `+` and `−` still work by tapping, and tapping the on-hand field raises the
numeric keypad rather than the full keyboard. Nothing on the card requires a physical keyboard.
