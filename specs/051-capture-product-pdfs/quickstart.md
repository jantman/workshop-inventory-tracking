# Quickstart: Capture Product PDFs

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" ../../GIT/workshop-inventory-tracking/venv/bin/nox -s tests
# e2e runs ~17 minutes: run detached and wait for it
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup ../../GIT/workshop-inventory-tracking/venv/bin/nox -s e2e > e2e.log 2>&1 &
```

Expected: the new unit tests in `tests/unit/test_listing_images.py` and the payload tests
pass; the McMaster and Amazon e2e tests show the PDF in the payload and as a stored
attachment.

## By hand — against the real sites (SC-001, SC-002)

1. Load the unpacked extension from `extension/` and point it at a running instance.
2. Open `https://www.mcmaster.com/91074A329/`. Set the CAD picker to **3-D PDF** so the
   capture has to open it. Click the extension.
3. On the confirmation form, the image count includes one more file than the page's
   photographs. The CAD picker on the McMaster tab still shows **3-D PDF** and is closed.
4. Capture. The flash reads "Stored N images and 1 PDF". The product's attachments include a
   one-page PDF drawing of the washer.
5. Capture the same page again onto the same product (details-only): the tally reports the
   drawing as already stored; no second copy appears.
6. Open an Amazon listing with "Product guides and documents" (e.g. `/dp/B000O3LUEI`) and
   capture it. Each distinct manual PDF is attached once.

## Results

**Real McMaster page (T016, SC-001)** — 2026-09-27, `https://www.mcmaster.com/91074A329/`
in the owner's Chrome, CAD picker showing **3-D PDF**. The new reader's functions, copied
verbatim from `extension/capture-agent.js`, returned a `data:application/pdf;base64,…`
address decoding to 105,558 bytes beginning `%PDF-1.4`, one page — the washer's 2-D
drawing, not the 3-D PDF that was selected. Afterwards the picker still read *3-D PDF*,
`aria-expanded="false"`, and no option list was left in the DOM. The whole read took about
one second. The full extension was not loaded into that browser, so the round trip through
the application was exercised by the e2e suite rather than by hand.
