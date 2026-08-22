# Quickstart: DigiKey Order Capture and Receiving

**Feature**: `specs/024-digikey-order-capture/`

How to validate this feature. Three sections: what the automated suites prove, what only a
real DigiKey account and a real bag can prove, and the gate that runs before any of it.

Commands assume the repository virtualenv and pyenv's 3.13 on `PATH`:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
```

---

## 0. The gate — run this first, before any code

**This is `T001`, and everything downstream depends on its answer** ([research §2](./research.md)).

1. Register an application at `developer.digikey.com`, subscribe it to **Product Information**
   and **Order Status**, and put the credentials in `.env`:

   ```
   DIGIKEY_CLIENT_ID=…
   DIGIKEY_CLIENT_SECRET=…
   ```

2. Get a 2-legged token and read back a real sales order — a number from a DigiKey order
   confirmation email, or from the `1K` field of a bag label:

   ```bash
   TOKEN=$(curl -s -X POST https://api.digikey.com/v1/oauth2/token \
     -d "client_id=$DIGIKEY_CLIENT_ID" \
     -d "client_secret=$DIGIKEY_CLIENT_SECRET" \
     -d "grant_type=client_credentials" | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')

   curl -s "https://api.digikey.com/orderstatus/v4/salesorder/<SALES_ORDER_NUMBER>" \
     -H "Authorization: Bearer $TOKEN" \
     -H "X-DIGIKEY-Client-Id: $DIGIKEY_CLIENT_ID" \
     -H "Accept: application/json" | python3 -m json.tool
   ```

3. Read the answer:

   | Result | What it means |
   |---|---|
   | The order comes back with its line items | Build as planned |
   | `401` / `403`, or an empty order | Switch to the 3-legged flow — [research §2](./research.md); one extra module, no other change |
   | A refusal naming the account type | **Stop and report.** User Story 1 may not be buildable for this account; that is a finding for the user, not something to route around |

4. Do the same for a part, and record both responses as test fixtures:

   ```bash
   curl -s "https://api.digikey.com/products/v4/search/1866-3032-ND/productdetails" \
     -H "Authorization: Bearer $TOKEN" -H "X-DIGIKEY-Client-Id: $DIGIKEY_CLIENT_ID" \
     -H "Accept: application/json" > tests/fixtures/digikey/productdetails.json
   ```

   **Redact before committing**: `ShippingAddress`, `BillingAddress`, `Email`, `CustomerId`,
   `BillingAccount`, `PaymentMethod`. The client never reads them and no test should carry
   them.

5. Confirm the two field-name questions [research §5](./research.md) leaves open: does the
   v4 sales-order response carry an order date, and do its line-item field names match the v3
   record? Whatever the fixtures say is what the client's mapping is written from.

---

## 1. Migration

```bash
venv/bin/python manage.py db migrate -m "add supplier_order_reference to purchases"
venv/bin/python manage.py db upgrade
venv/bin/python manage.py db downgrade -1   # Constitution V: the downgrade must be exercised
venv/bin/python manage.py db upgrade
```

**Check the drift trap.** The unit suite builds its schema with `create_all` and never runs
Alembic, so a column added to only one of `app/database.py` and the revision passes
`nox -s tests` and fails on the real database:

```bash
grep -n "supplier_order_reference" app/database.py migrations/versions/*.py
```

Both must match — same name, same type, same nullability, same index.

---

## 2. Unit suite

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
```

Runs with the network blocked (`--blockage`), so every DigiKey call is served from the recorded
fixtures. What it proves:

| File | Proves |
|---|---|
| `tests/unit/test_digikey_client.py` | The recorded JSON becomes the right dataclasses; **prices are `Decimal`, never `float`**; a missing field costs that field and nothing else; each failure state raises the exception [contracts/digikey-api.md](./contracts/digikey-api.md) §5 names |
| `tests/unit/test_digikey_capture.py` | The four `OrderLineState` values are assigned correctly; a re-capture of an unchanged order writes nothing (FR-012, SC-003); an excluded line writes nothing (FR-007); an unresolved conflict refuses the whole capture (FR-015); a line with no MPN still captures (FR-016) |
| `tests/unit/test_digikey_capture.py` (atomicity) | A failure part-way through a 24-line order leaves the product and purchase counts unchanged (FR-039, SC-009) |
| `tests/unit/test_scan_resolution.py` | The `receive` outcome for a label matching an outstanding line; the order-line lookup running **before** the MPN lookup; unchanged behaviour when nothing matches (FR-024, FR-025) |

The price assertion is the one to write first and never delete:

```python
assert order.lines[0].unit_price == Decimal('1.53')
assert isinstance(order.lines[0].unit_price, Decimal)
```

---

## 3. E2E suite

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e
```

**Give this a 15-minute timeout on the tool running it** (Constitution IV). The suite runs in
about 8m 15s warm; the margin is for a cold start.

DigiKey is played by a stdlib `ThreadingHTTPServer` on a loopback port serving the recorded
fixtures, with `DIGIKEY_API_BASE` pointed at it — the same shape
`tests/e2e/test_product_page_capture.py` already uses to play Amazon's image host.

| Scenario | Requirement |
|---|---|
| Enter a sales order number → the review lists every line, and the database is untouched | FR-003, FR-004 |
| Confirm → one outstanding purchase per included line, with the right quantity and price | FR-008, SC-002 |
| A line whose MPN is already cataloged shows as matched and attaches | FR-005, SC-005 |
| Exclude a line → no product, no purchase, every other line captured | FR-007 |
| Re-capture the same order → nothing new is recorded | FR-012, SC-003 |
| Scan a bag label for an outstanding line → lands on that line's receive screen with the label's quantity | FR-019, FR-020, SC-004 |
| Confirm the receipt → received, count up, flag cleared | FR-021 |
| Scan the same bag again → "already received", nothing received twice | FR-023 |
| The order screen shows *n* of *m* outstanding | FR-018, SC-007 |
| With `DIGIKEY_CLIENT_ID` unset, every DigiKey screen states it and no other screen changes | FR-036, FR-037, SC-008 |

**Waiting rules apply** (Constitution IV, and the "Writing e2e tests" section of `CLAUDE.md`).
Two that bite specifically here:

- The review page is server-rendered, so `expect(rows).to_have_count(n)` is a complete signal.
  The **capture confirmation** is not: it does network work before redirecting, so wait for the
  captured-order screen's heading, not for the button's own state.
- The scan box fires a `fetch` and then navigates on `data.url`. `click()` returning is not the
  end of it — wait for the receive screen's own content.

Seed through `live_server.add_test_data([...])` for anything that is not the subject of the
test. Driving the capture form to create fixtures for a receiving test costs seconds per line.

---

## 4. Screenshots

This feature adds templates, so documentation screenshots are a merge gate (Constitution,
Development Workflow):

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify
```

Commit the new order-review and captured-order screenshots alongside the templates. Screenshots
churn on every run, so review the diff and commit only what actually changed.

Remember `nox -s e2e` must leave the working tree clean — it excludes screenshot tests
(`-m "e2e and not screenshot"`) for exactly this reason.

---

## 5. What only reality can prove

These cannot run in CI. Do them by hand before calling the feature done, and record the results
in the spec directory the way `specs/023-restore-forwarded-port/` did.

1. **Capture a real order.** Place or pick a real DigiKey order, capture it by its sales order
   number, and reconcile the review line by line against the DigiKey order page: same lines,
   same quantities, same prices, same currency.
2. **Receive a real bag.** Scan a real bag label with the real wedge. This is the only check
   that proves the scanner transmits the `GS` separators — if it does not, the scan arrives as
   one run-together string and nothing matches (research §4, R4). This is a pre-existing
   property of the scanner, but this feature is the first that fails visibly without it.
3. **Two shipments.** Receive a partially shipped order and confirm the remainder still reads
   as outstanding on the order screen.
4. **A backordered or cancelled line.** Re-capture an order that changed after capture and
   confirm FR-013 and FR-014 behave: the new line is offered, the changed quantity is shown
   against the recorded one, and a vanished line is reported rather than deleted.
5. **Revoke the credentials** (or corrupt `DIGIKEY_CLIENT_SECRET`) and confirm the message
   distinguishes an authorization problem from DigiKey being down (FR-038).
