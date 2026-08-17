# Phase 1 Quickstart: validating a captured barcode becomes a scannable identifier

How to prove this feature works — automated first, then by hand for the two things a test suite
cannot show you.

## Prerequisites

Project commands run against the repository virtualenv, and `nox` needs Python 3.13 on `PATH`:

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
```

Invoke the venv binaries by path — `venv/bin/nox`, `venv/bin/python`. Never bare `pytest`
(Principle IV).

## Automated

```bash
venv/bin/nox -s tests    # fast; the classification matrix lives here
venv/bin/nox -s e2e      # give the tool a 15-minute timeout; runs ~8m15s warm
```

Both must be green before merge. `nox -s e2e` must leave the working tree clean — this feature
changes no template, CSS or JavaScript, so **no screenshots should be regenerated**. If
`git status` is dirty after an E2E run, something outside this feature's scope was touched.

### What the unit suite proves (`tests/unit/test_capture.py`)

The whole classification matrix, one test per row, plus the name-folding rules:

| Case | Expected |
|---|---|
| `UPC` row, valid barcode, new product | one `GTIN` identifier holding the 14-digit key; the row also present as a specification |
| `EAN`, `GTIN`, `ISBN`, `GTIN-13`, `UPC-A` rows | promote exactly as `UPC` does |
| `upc`, `  UPC  ` | promote (fold case and whitespace) |
| `Manufacturer UPC`, `UPC Code` | do **not** promote (whole-name match) |
| One digit altered so the check digit fails | no identifier; specification row present; `validation_overridden` never set |
| All-zero value | no identifier |
| `978…` ISBN-13 | promotes. ISBN-10 (10 digits, may end `X`) does not |
| Two space-separated codes in one value | no identifier |
| `UPC` (12 digits) and `EAN` (same code, leading zero) in one listing | exactly one identifier, and one report entry |
| Barcode already on another product | no identifier on the captured product; the other product's row untouched; report says `taken` with that product's id |
| Same listing captured twice onto the same product | still exactly one identifier; no error |
| Product already lists a `UPC` row | captured row dropped as today; **no identifier**; report says `not_examined` |
| Listing with no barcode-named row | byte-for-byte today's behavior; report is empty |

Also assert the negative that is easy to lose: a refused or collided promotion does not fail the
capture — the purchase, the other specification rows, the description and the images all land
(FR-011).

### What the E2E suite proves (`tests/e2e/test_product_page_capture.py`)

The two claims unit tests cannot make:

1. **Capture → identifier → scan.** Capture the fixture listing, confirm it, open the product, see
   the `GTIN` in `#identifier-list`, then put that barcode through the find-by-code path and land on
   the product. (`tests/e2e/test_wedge_scan.py` has the scan pattern to copy.)
2. **The operator is told.** The confirmation page carries the message.

Waiting rules — both pages are server-rendered, so this is the easy case:

- `expect(landed.locator(".alert")).to_contain_text("00012345678905")` for the message.
- `expect(landed.locator("#identifier-list")).to_contain_text("GTIN")` for the identifier.
- Before asserting an identifier is **absent** (the bad-check-digit test), establish the region with
  a positive `expect` first — a `count()` against a page that has not loaded reads zero and passes
  for the wrong reason (`CLAUDE.md`).
- No `wait_for_timeout`, no `time.sleep`, no `wait_for_load_state("networkidle")`.

Seed with `live_server.add_test_data([...])` for the collision test's pre-existing product; drive the
capture form only where the capture is the subject.

## By hand

Worth doing once, because the point of the feature is a physical box and a scanner.

1. Start the app against a scratch database and open the capture form (`/products/capture`).
2. Capture a listing that publishes a UPC — `B01N4OSKWE` is the issue's own case.
   **Read this before you do:** that product already exists in the live catalog **with a `UPC`
   specification row**, and a row the merge drops is not promoted. Against the real catalog you will
   correctly get `not examined` and no identifier. To see the promotion, capture onto a product that
   does not already list a `UPC` row — a scratch database, or after deleting that row.
3. On the confirmation page, look for the barcode line above the image tally.
4. Open the product. The `GTIN` should be in the **Identifiers** card, and the `UPC` row should
   *also* still be in the specification list — both, always (FR-005).
5. Scan the barcode off the box, or type it into the scan box. You should land on that product.
6. Now the refusal: edit the fixture or the listing so one digit of the barcode changes, capture
   again onto a fresh product, and confirm you get a specification row, no identifier, and a message
   saying it was not recorded. There should be no prompt offering to store it anyway — if you are
   offered one, FR-004 has been violated.

## Rollback

Nothing to migrate, so rollback is `git revert`. Any `GTIN` identifiers already promoted stay
behind and remain correct — they are ordinary identifier rows, indistinguishable from ones typed by
hand, and the find-by-code path resolves them either way.
