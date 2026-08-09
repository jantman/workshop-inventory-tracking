# Quickstart: Product Page Capture

How to run this feature, how to validate it, and the two things no suite can check.

## Prerequisites

```bash
source venv/bin/activate          # required before anything below
```

`nox` sessions pin Python 3.13; if the system Python is newer, put pyenv's 3.13 on `PATH` first.

**One migration.** `python manage.py db current` should read `b1a0c0d10008` before this change and `b1a0c0d10009` after it. Apply it with `python manage.py db upgrade`. It widens one column and moves no data — see [data-model.md](./data-model.md#revision-b1a0c0d10009--widen-the-specification-value). If any *other* revision appears, something was added that this plan says was not.

## Running the suites

```bash
nox -s tests      # sub-second; network blocked, so every requests.get must be mocked
nox -s e2e        # ~8-9 min warm; give the tool a 15-minute timeout
```

The e2e session needs two pieces of infrastructure this feature introduces, both test-only:

- **A fixture listing page.** `tests/e2e/fixtures/amazon_listing.html` is fulfilled through `page.route` against a fake listing address, so the extractor runs against a page with a gallery data block naming more images than there are thumbnails, both description forms, and several product-information containers. `page.route` is already used in this suite (`tests/e2e/test_label_printing.py:283`).
- **A local image host.** A stdlib `http.server` thread serving `tests/e2e/fixtures/images/` — six real JPEGs already in the repository. The payload's image addresses point at it, so the application performs a genuine HTTP fetch of genuine bytes from an origin the test controls.

Since UI files change, regenerate screenshots and commit them:

```bash
nox -s screenshots_headless && nox -s screenshots_verify
```

That diff carries no signal — regeneration is not byte-reproducible, as recorded in feature 006's plan — and the workflow that checks it is informational.

## Exercise the migration both ways

**Required, not optional.** Neither suite runs Alembic — `tests/conftest.py` and `tests/e2e/test_server.py` both build the schema with `Base.metadata.create_all` — and the widening is MariaDB-only, so SQLite could not exercise it even if they did. This revision has no automated coverage of any kind.

**Against a disposable container, never against the deployment.** Point `DATABASE_URL` at a throwaway MariaDB, not at whatever `.env` names.

```bash
docker run -d --name spec007-db -e MARIADB_ROOT_PASSWORD=test \
  -e MARIADB_DATABASE=workshop -p 3399:3306 mariadb:11
export DATABASE_URL='mysql+pymysql://root:test@127.0.0.1:3399/workshop'

python manage.py db upgrade b1a0c0d10008        # the state before this feature
```

Seed a specification row, then round-trip:

```sql
INSERT INTO products (description) VALUES ('round-trip probe');
INSERT INTO product_specifications (product_id, name, value, display_order)
  VALUES (LAST_INSERT_ID(), 'Description', REPEAT('x', 60000), 0);
```

```bash
python manage.py db upgrade                     # -> b1a0c0d10009
python manage.py db downgrade b1a0c0d10008      # must succeed: 60000 < 65535
python manage.py db upgrade                     # -> b1a0c0d10009 again
```

Confirm the type actually moved, in both directions:

```sql
SELECT DATA_TYPE FROM information_schema.COLUMNS
 WHERE TABLE_NAME = 'product_specifications' AND COLUMN_NAME = 'value';
-- mediumtext after upgrade, text after downgrade
SELECT LENGTH(value) FROM product_specifications;   -- 60000, unchanged throughout
```

Then check the guard, which is the part worth having:

```sql
UPDATE product_specifications SET value = REPEAT('x', 70000);
```

```bash
python manage.py db downgrade b1a0c0d10008
```

This **must fail**, naming the offending row's id and product, and must leave the column as `mediumtext` with the 70,000 bytes intact. A downgrade that silently truncates to 65,535 is the failure this guard exists to prevent, and a passing round-trip above does not test it — only this does.

```bash
docker rm -f spec007-db && unset DATABASE_URL
```

## Validating by hand

Start the app and open `/products/capture`.

### 1. The paste-a-URL path still works untouched

Paste any listing address and submit. This path sends no `listing` field, so it must behave exactly as it did before this feature. If anything here changed, FR-007 is broken.

### 2. Capture with a payload, without a browser

The confirmation form is an ordinary form, so the payload can be supplied by hand. This is the fastest way to exercise the whole server half without Amazon:

```bash
# with the app running locally
curl -sS -X POST http://localhost:5000/api/capture \
  --data-urlencode 'url=https://www.amazon.com/dp/B0CKXJLP4B' \
  --data-urlencode 'listing_title=Test Listing' \
  --data-urlencode 'listing={"version":1,"source_url":"https://www.amazon.com/dp/B0CKXJLP4B",
    "vendor_item_id":"B0CKXJLP4B","price":"24.99","brand":"Acme",
    "description_text":"A description.",
    "specifications":[{"name":"Material","value":"6061 Aluminium"}],
    "images":["http://localhost:8000/steel_rod_sample.jpg"]}' \
  | grep -c 'name="listing"'
```

Expect the rendered confirmation form, with the payload echoed back in the hidden field. Nothing is written by this request — check that no product appeared. Then submit that form from the browser and confirm the write.

Serve the image with `python -m http.server 8000 --directory tests/e2e/fixtures/images` so the fetch has something real to retrieve.

### 3. Check each requirement that is easy to get wrong

| Check | Expect |
|---|---|
| Confirm a capture, then capture the same listing again onto the same product | No image stored twice; the specification count unchanged (FR-010, FR-018) |
| Edit a specification by hand, then re-capture | Your value survives; nothing removed (FR-010, FR-011) |
| Close the confirmation tab without submitting | No product, no purchase, no rows in `photos` (FR-014, FR-015) |
| Trigger the duplicate question, answer it | Images and specifications land intact (FR-016) |
| Point one image address at something that 404s | Capture succeeds; flash names the count that failed (FR-020) |
| Open a product with attachments | A thumbnail grid, not a filename list (FR-013) |
| Copy an image, open a product, press Ctrl+V | It uploads and appears (FR-023) |
| Paste ordinary text on a product page | Nothing happens, no error (FR-023) |

Verify the write directly where the UI would flatter you:

```sql
SELECT name, value FROM product_specifications WHERE product_id = ? ORDER BY display_order;
SELECT p.filename, p.sha256_hash FROM photos p
  JOIN product_attachments a ON a.photo_id = p.id WHERE a.product_id = ?;
```

Every row created by this feature must carry a non-null `sha256_hash`. Rows that predate it stay null, by design.

## What no suite can check

Two things, and both must be done by hand against the real thing before this ships. Neither CI nor a fixture can substitute, because both are about the vendor rather than about this code.

### A. The bookmarklet reaches the app from an Amazon page

Requires TLS. Open `/products/capture` **over https**, drag the bookmarklet again — the addresses are baked in at render time, so one dragged from the http page keeps pointing at http and dies under `upgrade-insecure-requests` (issue #54). Then, on a real listing:

1. Click it. A new tab must open on this app's confirmation page, pre-filled.
2. The browser console must show no `securitypolicyviolation`. If Amazon has started restricting `script-src` since issue #57's probing, this is where it surfaces, and the extension fallback in [research.md](./research.md#where-the-extraction-code-runs) becomes live.
3. Edit `capture-agent.js`, reload the listing, click again. The change must take effect with no re-drag (FR-024).

### B. The extractor reads a real listing correctly

Against at least the six ASINs probed in issue #57 — `B0CKXJLP4B`, `B0DMNXC4CD`, `B01N4OSKWE`, `B099F4X4Q9`, `B09GM8FB3X`, `B0FX4PDW6M` — because between them they cover every structural variation found: both description forms, all four product-information container types, and the two listings whose page data names more than twice what the thumbnail strip shows.

For each, before confirming, the confirmation page's summary must report:

- **an image count matching the "hi-res URLs in page data" column** of issue #57's table (14, 7, 3, 16, 11, 9) — not the thumbnail count;
- **a description** on all six;
- **specification rows** in the range that issue's table records.

Then confirm one and check a stored image is the original: `identify` it, or read `Photo.file_size`. For `B0CKXJLP4B` the original is 1601×1601 at 358,055 bytes, against 1446×1500 at 345,670 for the tokened rendition. Getting the smaller one means the transform token is not being stripped and FR-004 is not met.

Also click it once on an Amazon **order-details** page. The capture must fall back to today's behaviour rather than extracting page furniture. It will still create a product called "Order Details" — that is issue #56 point 4, which this feature does not fix and must not worsen.
