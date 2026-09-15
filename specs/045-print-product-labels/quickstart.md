# Quickstart & Validation: Print labels for selected products

How to run this feature, what to check by hand, and — the part that matters most — the observable
condition behind every wait in the new E2E module, so nobody has to reach for a fixed delay.

## Prerequisites

The virtualenv lives in the **main checkout**, not in this worktree, and nox needs Python 3.13 on
PATH:

```bash
export NOXPATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
VENV=/home/jantman/GIT/workshop-inventory-tracking/venv    # adjust if elsewhere
```

No migration to apply — this feature changes no schema.

## Running it by hand

```bash
PATH="$NOXPATH" $VENV/bin/python -m flask run   # or however the app is normally started
```

Then, at `/products`:

1. Add two or three products (`/products/new`) if the catalog is empty.
2. Confirm every row now has a checkbox in the **first** column, and the header has a select-all
   checkbox.
3. With nothing ticked, the **Print Labels** action is disabled and the count badge reads `0`.
4. Tick two rows. The badge reads `2` and the action becomes available.
5. Open the dialog. It lists the two products by description, offers **all six** stocks, and shows a
   count input defaulted to `1`.
6. Choose a stock, set the count to `3`, print. The progress line names each product in turn and the
   completion line reads `Complete: 6 labels for 2 products, 0 failed`.
7. Close and reopen the dialog: the count is back to `1`, no progress bar, no stale messages.
8. Set the count to `0` (or `abc`, or `100`) and print: the warning names the 1–99 range, the
   progress bar never appears, and **nothing** is sent.

Label output itself is short-circuited when `TESTING` or `DISABLE_LABEL_PRINTING` is set — see
`app/services/product_label.py:433`.

## The regression check that matters most

The refactor moves working code out of `inventory-list.js`. Before claiming the feature works,
confirm the page it was taken from is unchanged:

```bash
PATH="$NOXPATH" $VENV/bin/nox -s e2e -- tests/e2e/test_bulk_label_printing_list.py
```

That module asserts the inventory list's dialog in detail, including its exact progress and
completion wording. It must pass **without being edited**. An edit to it is a signal that the
extraction changed behaviour, not that the test was wrong.

## Full suites

```bash
PATH="$NOXPATH" $VENV/bin/nox -s tests          # fast, under a second
PATH="$NOXPATH" $VENV/bin/nox -s e2e            # ~20 min warm — run detached, see below
```

The E2E suite outlasts a 10-minute agent bash timeout. Run it detached and poll:

```bash
nohup env PATH="$NOXPATH" $VENV/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

Screenshots are a separate session and are **not** part of `nox -s e2e` — an E2E run must leave the
working tree clean:

```bash
PATH="$NOXPATH" $VENV/bin/nox -s screenshots_headless
PATH="$NOXPATH" $VENV/bin/nox -s screenshots_verify
```

The products-list screenshot legitimately changes (new column, new button). Other screenshots churn
between runs without meaning anything — check what actually differs before committing, and commit
only the ones this change explains.

## Waiting conditions for the new E2E module

Per `CLAUDE.md`, every wait names an element. These are the conditions, each with the reason it is
the right one. `tests/e2e/test_bulk_label_printing_products.py` should need nothing beyond them.

| Action | Wait on | Why this one |
|---|---|---|
| Page loaded, ready to tick | `expect(page.locator("#product-table tbody tr")).to_have_count(n)` | The table is **server-rendered**, so it is present at `load` — but establish it anyway before any `count()` / `is_checked()` read, per the snapshot rule. |
| Tick a row | `expect(page.locator("#product-selected-count")).to_have_text("2")` | The badge is written synchronously by the change handler. Don't read `is_checked()` without establishing this first. |
| Selection empty → action disabled | `expect(btn).to_be_disabled()` | A **positive** assertion that polls. `not_to_be_enabled()` on an element the handler has never touched would pass trivially. |
| Open the dialog | `waits.wait_for_modal_shown(page, "productBulkLabelPrintingModal")` | Already in `tests/e2e/waits.py:234`. Bootstrap's show is animated; the modal element exists in the DOM before it is usable. |
| Stocks loaded | `waits.wait_for_select_populated(page, "product-bulk-label-type")` | Already in `waits.py:337`. `open()` awaits `GET /api/labels/types` and appends options **after** the await — pattern C, render-implies-completion. The option count is a complete signal. |
| Stock chosen → print armed | `expect(page.locator("#product-bulk-print-all-btn")).to_be_enabled()` | The change handler clears `disabled`. Positive, and cannot hold before the handler ran. |
| Run started | `expect(page.locator("#product-bulk-print-progress")).to_be_visible()` | The progress region loses `d-none` as the first thing `printAll()` does after the count passes. |
| Run finished | `expect(page.locator("#product-bulk-print-done-btn")).to_be_visible()` | The Done button is revealed **after** the loop's last `await`. Pattern C again — it cannot appear before every POST has settled. Prefer it over asserting on the status text, which changes several times during the run. |
| Completion wording | `expect(page.locator("#product-bulk-print-status")).to_have_text(re.compile(r"^Complete: "))` | Only after the Done button is visible; before that the same element is holding per-product progress. |
| Refused count printed nothing | `expect(errors).to_be_visible()` **and** `expect(progress).to_be_hidden()` | **Two** conditions, not one. The warning alone does not prove nothing printed; the progress region staying hidden is what does. Pattern B — one action, two things to establish. |
| Nothing was actually posted | a request-capture fixture on `**/api/products/*/label`, asserted **after** the two waits above | `test_bulk_label_printing_list.py:448` already does exactly this for the item endpoint; copy its shape. A bare "no requests yet" assertion would pass against a run that simply hadn't started. |
| Dialog closed | `waits.wait_for_modal_hidden(page, "productBulkLabelPrintingModal")` | Already in `waits.py:255`. Reopening before the hide transition finishes gives a dialog in an indeterminate state. |
| Reset on reopen | `expect(page.locator("#product-bulk-label-count")).to_have_value("1")` | Assert on the value, not on the absence of the old one. |

### Two traps specific to this page

- **Seed through `live_server.add_test_data([...])` where possible.** Driving `/products/new` costs
  about three seconds per product; a test needing five products pays fifteen seconds for setup that
  is not what it is testing. Drive the form only when the form is the subject.
- **A negative assertion about a product's absence from the table must establish the table first.**
  The rows are server-rendered so this is less dangerous here than on the inventory list, but the
  rule is unconditional: `expect(rows).to_have_count(n)` before any `count()`-shaped read.

## Acceptance mapping

| Requirement | Validated by |
|---|---|
| FR-001, FR-002, FR-003 | Manual steps 2–4; E2E selection tests |
| FR-004 | Manual step 3; `to_be_disabled()` assertion |
| FR-005, SC-006 | E2E asserting all six stocks, matching `test_label_print.py`'s existing check |
| FR-006, FR-007, SC-005 | Manual step 8; the refused-count test with its two waits and the request capture |
| FR-008, FR-009, SC-003 | Holds by construction — the same endpoint the product detail page uses. Cover with a test asserting the POST body per product. |
| FR-010, FR-011, FR-012, SC-004 | E2E with one product made to fail (route-abort or a deleted id) |
| FR-013 | Manual step 7; reset-on-reopen test |
| **FR-014** | `test_bulk_label_printing_list.py` and `test_label_print.py` passing **unedited** |
| FR-015 | E2E: filter the list, confirm the badge reflects only listed products |
| SC-001, SC-002 | Manual step 6; the count-multiplication test |
