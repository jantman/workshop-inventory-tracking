# Quickstart: The Captured Listing Fills In the Manufacturer Part Number

**Feature**: `specs/019-capture-mpn-default` | **Date**: 2026-08-18

How to prove this feature works, from a clean checkout. Commands assume the repository
virtualenv and the repository root as the working directory.

## Prerequisites

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"   # nox needs 3.13 on PATH
venv/bin/nox --list                                      # sanity check
```

Docker must be running for `e2e` (MariaDB) and for `screenshots_headless`.

## 1. The rule itself — no app, no database, no browser

This is the payoff of putting the derivation on `ListingCapture`: the whole of FR-001 through FR-004
is checkable in under a second.

```bash
venv/bin/nox -s tests -- tests/unit/test_capture.py -k part_number
```

**Expected**: green, and fast. Covers each recognized name, priority order beating page order, the
internal-whitespace fold, empty and whitespace-only values passed over, the 100-character ceiling,
and a listing with no rows returning `None`.

Sanity-check it by hand if you want to see it:

```bash
venv/bin/python -c "
from app.models import ListingCapture
listing = ListingCapture(
    source_url='https://example.invalid/dp/B0CZ72JRHP',
    specifications=[
        {'name': 'Model Number', 'value': 'MKT-7700'},
        {'name': 'Mfr  Part Number', 'value': '  7700-B  '},
    ],
)
print(repr(listing.manufacturer_part_number()))
"
```

**Expected**: `'7700-B'` — the higher-priority name wins even though it is second on the page, and
the internal double space in the row's name does not stop it matching.

## 2. The route rules — absent versus empty, and redisplay

```bash
venv/bin/nox -s tests -- tests/unit/test_capture.py -k 'part_number and (form or cleared)'
```

**Expected**: green. Covers FR-005 (a POST carrying the payload and no field falls back to the
derived value; a POST carrying an empty field does not) and FR-006 (a re-render after a capture
question redisplays a cleared field as cleared).

## 3. The whole unit suite

```bash
venv/bin/nox -s tests
```

**Expected**: green, in about a second, with the network blocked. `TestWhichRowNamesMeanABarcode`
(`tests/unit/test_capture.py:1762`) must pass **untouched** — `normalized_row_name` is a verbatim
move out of `_is_barcode_row_name`, so any change in barcode-row behavior means the move was not
verbatim.

## 4. End to end, through the bookmarklet

```bash
# 15-minute timeout required (Constitution IV); run detached, it outlasts a 10-minute cap
nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

Or just this feature's tests, which is what you want while iterating:

```bash
venv/bin/nox -s e2e -- tests/e2e/test_product_page_capture.py -k part_number
```

**Expected**: the fixture listing (`tests/e2e/fixtures/amazon_listing.html`, which gains a
part-number row for this feature) is captured through the bookmarklet, and the confirmation form's
Manufacturer Part Number field already holds the fixture's value with nothing typed into it.
Submitting stores it; clearing it first stores nothing.

## 5. Screenshots

`app/templates/product/capture.html` is edited, so the constitution's screenshot gate applies.

```bash
venv/bin/nox -s screenshots_headless
git status --short docs/images/screenshots/
venv/bin/nox -s screenshots_verify
```

**Expected**: `screenshots_verify` passes, and
`docs/images/screenshots/user-manual/order_capture.png` shows the confirmation form. That is the
capture page's screenshot — 018 regenerated the same file when it last edited this template.
Screenshots churn on every run regardless of the change, so inspect what actually differs and commit
only `order_capture.png` plus anything whose content genuinely moved — not the whole directory.

## 6. By hand, against the two listings from the issue

The end this feature was built for. Requires the app served over TLS for the bookmarklet, per
`tests/e2e/test_product_page_capture.py`'s module docstring.

1. Open `https://www.amazon.com/dp/B0CZ72JRHP` and run the bookmarklet.
2. On the confirmation page, **Manufacturer Part Number is already filled** — this is SC-001.
3. Scroll to the product information rows: the row it came from is still listed (SC-005).
4. Clear the field and submit. The product stores no part number (SC-003).
5. Repeat with `https://www.amazon.com/dp/B0FX4PDW6M`.

## Failure signatures worth recognizing

| Symptom | Almost certainly |
|---|---|
| Field is empty on a listing that has the row | The name is not in `PART_NUMBER_ROW_NAMES` in its normalized form. Print `normalized_row_name(row['name'])` and compare. |
| Field refills itself after you clear it and the capture asks a question | The template is testing truthiness (`or`) instead of key presence. That is FR-006. |
| `manufacturer` or the unit price changed behavior | Out of scope and must not be in the diff. Revert that hunk. |
| Barcode-row tests fail | `normalized_row_name` was not a verbatim move. Diff it against the old `_is_barcode_row_name` body. |
| A capture fails at the end with a data-too-long error | The length ceiling is missing or is being applied before trimming (FR-003). |
