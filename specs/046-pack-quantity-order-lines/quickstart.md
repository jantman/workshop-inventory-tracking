# Quickstart: Proving Feature 046 Works

All commands run from the repository root through the main checkout's virtualenv, using `nox`
only (Constitution IV). Put Python 3.13 on `PATH` first:

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
NOX=/home/jantman/GIT/workshop-inventory-tracking/venv/bin/nox
```

Design references, not repeated here: the arithmetic and the override rule are in
[`contracts/pack-conversion.md`](./contracts/pack-conversion.md); what the two columns mean and who
may write them is in [`contracts/purchase-pack-fields.md`](./contracts/purchase-pack-fields.md);
the model changes are in [`data-model.md`](./data-model.md).

---

## 1. Red first: the reported defect

Before any production change, write the unit test for SC-001 and watch it fail.

Build an `AmazonOrder` payload with one line — ASIN `B0PACK100`, title
`Widget Screws (Pack of 100)`, quantity `1`, unit price `13.23` — run it through
`capture_order_lines`, and assert the resulting purchase holds **quantity 100 at 0.13**.

On today's code it records **1 at 13.23**. That failure is the issue, and it belongs in the PR.

```bash
$NOX -s tests -- tests/unit/test_pack_conversion.py
```

A second red test for US4: POST the confirmation form to `/products/capture` with `pack_price=13.23`,
`pack_size=100`, `packs=1` and no typed quantity. Today the route drops all three and records a
NULL quantity; it must record 100.

---

## 2. Migration, both directions

The schema change is the one part no test exercises against the real database
(research R9 — the unit suite builds its schema with `create_all` and never runs Alembic, so
model/revision drift passes `nox -s tests` and fails on MariaDB).

```bash
venv/bin/python manage.py db upgrade head
venv/bin/python manage.py db downgrade -1     # must succeed
venv/bin/python manage.py db upgrade head
```

Then confirm, against MariaDB:

- `purchases` has `pack_size` `int NULL` and `pack_price` `decimal(10,2) NULL`
- **every pre-existing row holds NULL in both** (FR-032) —
  `SELECT COUNT(*) FROM purchases WHERE pack_size IS NOT NULL;` returns `0`
- the column types match `app/database.py` exactly

---

## 3. Unit scenarios (`nox -s tests`)

| Scenario | Proves |
|---|---|
| The eight rows of the worked table in `contracts/pack-conversion.md` | C1–C4, FR-005, FR-006, FR-009 |
| `packs=None` yields `quantity=None`; `pack_price=None` yields `unit_price=None` — a pack size invents neither | FR-009 |
| `pack_size=1` gives byte-identical quantity and price to no pack at all | FR-002, C4 |
| `price_rounds` is true for 13.23÷100 and false for 12.00÷100 | FR-008 |
| `pack_size_from_title`: each recognised form returns its count | FR-019 |
| `pack_size_from_title` returns None for `M3 x 12mm`, `12V`, `1/4-20`, a bare number, a count of 0 or 1, and a title naming two different counts | FR-022 |
| Precedence: operator → listing's structured `pack_size` → title → 1 | FR-018, FR-019, FR-021 |
| Override detection: untouched quantity follows the pack size; changed quantity wins; both branches agree when JS already converted | R3, FR-007 |
| Pack size 0, blank, negative, fractional → `ValidationError` naming the line, never coerced to 1 | FR-011 |
| A refused pack size writes **nothing for any line** of the order | FR-013 |
| `_amazon_line_fields` returns the pack fields only when the pack exceeds 1; NULL otherwise | FR-028, FR-031, P2 |
| `_mcmaster_line_fields` now returns `pack_size`/`pack_price`; NULL for "Each" and for **"Pairs"** | FR-030, and the writers table |
| McMaster's converted quantity and price are unchanged from before this feature | FR-039 |
| `capture_order` stores the listing page's pack and derives the quantity | FR-023, FR-028 |
| `_apply_order_change` writes the pack fields alongside quantity and price | P-writers |
| `receive_purchase` amends quantity and leaves both pack columns untouched | R7, FR-033 |
| `ReviewedLine.has_change` compares **converted** values — a pack line against a matching recorded purchase reports no change | FR-010 |
| A DigiKey line's fields are byte-identical to before | FR-040 |
| A payload captured before this feature reads identically through `from_payload` | data-model, payload compatibility |
| `AmazonOrderLine.missing_fields` still never reports a missing quantity | preserved behaviour |

The whole suite must still run in under a second. Nothing here does I/O.

---

## 4. End to end (`nox -s e2e`, detached)

The suite takes about 17 minutes warm and outlasts the Bash tool's 10-minute cap, so run it
detached and wait on the log rather than on a timeout:

```bash
nohup $NOX -s e2e > /tmp/claude-e2e.log 2>&1 &
```

Journeys go in `tests/e2e/test_amazon_order.py` and `tests/e2e/test_product_page_capture.py`.

| Journey | Proves |
|---|---|
| Review a pack line, set pack size to 100 → the quantity input reads `100` and the price input `0.13` before confirming | US1 §1 |
| Confirm it → the product's purchase reads 100 at 0.13 | SC-001 |
| Leave a line's pack size alone → its purchase is what the order stated | FR-002, SC-005 |
| A line whose title names `Pack of 100` arrives pre-filled and marked as a guess; clearing it sticks across a re-render | US3, FR-020, FR-021 |
| A mixed order shows plainly which lines are converted and which are not | US2, SC-004 |
| An inexact division shows the rounding note on that line | FR-008 |
| A pack size of `0` is refused, the message names the line, and **every** other entry survives the re-render | FR-011, FR-012 |
| Capture page: a pack listing fills Quantity from the pack, and typing over it sticks | US4, FR-023, FR-025 |
| A captured pack order's page shows the vendor's line beside the catalog's | US5, FR-034 |

### Waiting rules for these tests

Constitution IV and `CLAUDE.md` bind here; the shape of this feature hits three of the named
patterns directly.

- **Pattern E — a snapshot read behind a derived value.** The whole feature is "a number changes
  in an input". `expect(field).to_have_value("100")` polls; `field.input_value()` does not and
  will read the pre-conversion value on a slow machine. Never assert with `input_value()`,
  `text_content()` or `count()` against a converted row.
- **Pattern F — a positive marker, not the absence of one.** Assert the *converted* marking is
  present on a converted line, not that it is absent on an unconverted one; the absent form also
  passes against a row that has not rendered.
- **Seed through `live_server.add_test_data`** for everything except the capture forms themselves,
  which are what is under test here.
- Zero `wait_for_timeout` executions today. Adding one puts back what two features were spent
  removing.

---

## 5. Screenshots

`app/templates/**` and `app/static/js/**` both change, so the screenshot gate applies:

```bash
$NOX -s screenshots_headless
$NOX -s screenshots_verify
```

Regenerated screenshots are committed with the UI change; CI blocks merge on stale ones. Measure
the churn before committing — screenshots come from two sources and churn on every run, so commit
only the ones this change actually altered.

---

## 6. Documentation

```bash
grep -n "Neither pack field is stored" docs/user-manual.md    # must return nothing when done
grep -ric "catalogue" README.md docs/ app/ tests/             # must return nothing
```

Checklist (research R10):

- [ ] `docs/user-manual.md:1228` *"When it is sold as a pack"* — the *"Neither pack field is
      stored"* sentence is gone (FR-035), and the Quantity description matches the page (FR-037)
- [ ] A new passage covers the Amazon review's pack size, stating that a suggested one is a guess
      the operator is answerable for (FR-036)
- [ ] `:1643` and `:1808` say McMaster's pack is now kept, not discarded (FR-038)
- [ ] The three code comments asserting *"neither is recorded anywhere"* / *"not stored"* are
      corrected — `app/models.py` (`ListingCapture`), `app/templates/product/capture.html`,
      `app/templates/product/order_review.html`
- [ ] `specs/` is untouched, including `specs/029-whole-order-capture/research.md` §5 whose
      finding this reverses — it is a frozen record

---

## 7. By hand, once, against the real thing

The reported order is `111-1533738-5610601`, four lines, every one a multi-item pack. This is the
check that closes the issue.

1. Open that order's details page and click the capture bookmarklet.
2. Each line arrives with a pack size — pre-filled where its title names one, marked as a guess.
3. Correct any the titles got wrong, against the boxes.
4. Confirm.
5. Each product's purchase reads the items actually received at a per-item price, and each
   product page's stock is in items.
6. Open the captured order: each line shows Amazon's own *1 pack of N at $P* beside the catalog's
   *N items at $U*, and the pack prices add up to what the card was charged.

**Then the regression that matters**: capture any order with **no** pack lines and confirm the
records are exactly what they would have been before this feature (SC-005).
