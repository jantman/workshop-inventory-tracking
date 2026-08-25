# Quickstart: validating McMaster-Carr Order and Product Capture

**Feature**: 028-mcmaster-order-capture

How to prove this works. Automated checks first, then the two things no test in this repository
can reach.

---

## Prerequisite: the fixtures

**Nothing in this feature can be built or validated until two saved McMaster pages exist.** They
are an input, not an artifact of the work — see research.md §5.

| File | Save from | Must show |
|---|---|---|
| `tests/e2e/fixtures/mcmaster_order.html` | one order in McMaster's **order history** | several lines, with part numbers, descriptions, quantities and prices. More than one line, and ideally one pack-priced line. |
| `tests/e2e/fixtures/mcmaster_product.html` | one product page | the part number, the description, the price, a pack size, and the specification table |

Save as complete HTML from the browser, with the page fully rendered — McMaster builds its
pages client-side, so "view source" gets you a shell and not the document the agent will read.

**Scrub the order page before committing it.** It carries the ship-to address, and possibly a
name, a phone number, or the last digits of a card. None of it is read by this feature and none
of it belongs in the repository. Part numbers, descriptions, quantities and prices are the
fixture; the rest comes out.

---

## Setup

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
venv/bin/python manage.py db upgrade      # the order_line_number rename
venv/bin/python manage.py db current      # confirm it is at head
```

The migration must also be reversible (Constitution V) — exercise both directions once, against
the real database, before trusting it:

```bash
venv/bin/python manage.py db downgrade -1
venv/bin/python manage.py db upgrade
```

---

## Automated checks

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
venv/bin/nox -s tests     # sub-second; network blocked
venv/bin/nox -s lint
```

E2E **outlasts a ten-minute agent bash timeout** — about 13m 45s warm, longer cold. Run it
detached and poll; see `CLAUDE.md`.

```bash
nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

Two properties of the run matter as much as the pass:

* **The working tree must be clean afterwards.** `e2e` selects `-m "e2e and not screenshot"`
  precisely so a test run does not rewrite `docs/images/screenshots/`.
* **No new `wait_for_timeout` anywhere.** The suite executes zero and must go on executing zero.
  `grep -rn "wait_for_timeout\|time.sleep" tests/e2e/` is the check.

---

## Walking the feature by hand

Start the app on the LAN over the address the operator really uses. **The bookmarklet must be
re-dragged from `/products/capture` on that address** if it has never been dragged — its
addresses are absolute and fixed when that page renders.

### US1 — capture a whole order (FR-001…FR-020a)

1. Open one of your McMaster orders in order history. Click the bookmarklet.
2. A new tab lands on the review. Check: every line you can see on McMaster's page is here;
   the count of lines read matches; the order number and date are right; **nothing has been
   written** — leave the tab open and confirm the product list is unchanged in another tab.
3. For a pack-priced line, check the packs, the pack size and the pack price are shown, and that
   the quantity is **units** (packs × pack size) at the per-unit price. If the division is not
   even, the page says so.
4. Write descriptions for the new lines. Untick one line. Confirm.
5. Check: one outstanding purchase per included line, each carrying `McMaster-Carr`, the order
   number, the quantity and the unit price. The unticked line produced nothing.
6. **Abandon test**: click the bookmarklet again, then close the tab without confirming. The
   product and purchase counts must be unchanged.
7. **Re-capture test**: click the bookmarklet on the same order page. Every line reads as
   already captured, and confirming records nothing (SC-003).

### US2 — capture one product (FR-021…FR-026)

1. Open a McMaster product page. Click the bookmarklet.
2. Check the confirmation form arrives carrying the part number, description, price, pack size,
   specifications and image, with nothing typed.
3. Write your own label description over McMaster's. Capture.
4. Check the product carries a `DISTRIBUTOR` identifier scoped to `McMaster-Carr` and that
   searching or scanning that part number finds it.
5. **Paste-a-URL check** (FR-025): paste a McMaster product address into `/products/capture`
   with no bookmarklet. The vendor reads `McMaster-Carr` and the part number is filled in.

### US3 — receive (FR-027…FR-032b)

1. Open the captured order. Check every line's state and the outstanding count.
2. Scan the part number of one outstanding line. You land on **its receipt**, not on the product
   page. Amend the quantity to what actually arrived and confirm.
3. Check the purchase is received, a counted product's quantity rose by the amended amount, and
   any manual low/out flag cleared.
4. Scan the same part number again. It falls through to ordinary behaviour — nothing is
   received twice.
5. **Two-candidate check**: capture a second order containing the same part, then scan it. The
   chooser appears with both, and the catalog picks neither.
6. **Mark-received check**: receive a line from the order screen instead of by scanning. Same
   result.

### US4 — degradation (FR-036…FR-039)

Copy `mcmaster_order.html`, strip the price markup from the copy, serve it, and capture:
every line still reads, the prices are blank and editable, and the review says prices could not
be read. Then strip everything and check the "this page yielded no order" statement appears —
not an empty review, and not an error page.

---

## The two things no test here can reach

Both are stated rather than hidden, exactly as feature 007 stated them.

**1. The cross-origin transport.** The e2e harness serves fixtures from the application's own
origin, because Chrome's Private Network Access rules stop a public origin from loading a
subresource from a LAN address — the test would be measuring that policy, not this feature. So
the real path (McMaster over HTTPS submitting a form to this app over plain HTTP on the LAN) is
only ever exercised by the manual walk above. **If the bookmarklet does nothing when clicked on
a real McMaster page, check the scheme and the port in its address first** — a proxy that does
not send `X-Forwarded-Proto` or `X-Forwarded-Port` hands out a bookmarklet pointing at nothing
(issues #89 and #114).

**2. McMaster changing their markup.** A test against a saved page proves the reader reads that
page. Nothing in this design fails when McMaster redesigns; the containment is FR-036 (a lost
field costs that field alone) and FR-004/FR-037 (the review says how many lines it read and what
came back thin). Containment, not prevention.

---

## Regression checks — the ones that decide SC-010

The existing suites are the assertion. Run them and read them as this feature's own:

| Suite | Proves |
|---|---|
| `tests/e2e/test_product_page_capture.py` | the Amazon bookmarklet path is untouched |
| `tests/e2e/test_order_capture.py` | the paste-a-URL path and vendor derivation |
| `tests/e2e/test_digikey_order.py`, `test_digikey_part.py`, `test_digikey_receive.py` | the DigiKey paths, including through the column rename |
| `tests/e2e/test_ecia_scan.py` | ECIA label scanning is unchanged by the new free-text branch |
| `tests/unit/test_digikey_capture.py` | line-to-purchase pairing survives the rename |

Also confirm by hand that scanning an Amazon ASIN still opens its product page rather than
anything new.
