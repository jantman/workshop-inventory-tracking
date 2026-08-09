# Phase 1 Data Model: Product Page Capture

## One migration, and one column that was waiting

This feature adds no table, no column, no index and no constraint. It changes **one column type** — `product_specifications.value` from `TEXT` to `MEDIUMTEXT`, on revision `b1a0c0d10009` — so that FR-006 can hold without an exception. Head moves `b1a0c0d10008` → `b1a0c0d10009`.

That is a small footprint for a feature that stores a dozen images, twenty specification rows and a description per capture, so here is every value it writes and the column it lands in.

| What the capture produces | Where it goes | Exists since |
|---|---|---|
| Listing title | `purchases.listing_title` | `b1a0c0d10002` |
| Vendor item identifier | `purchases.vendor_item_id`, and `product_identifiers` when free | `b1a0c0d10002`, `b1a0c0d10003` |
| Listing address | `purchases.listing_url` | `b1a0c0d10008` (feature 006) |
| Unit price | `purchases.unit_price` (`Numeric`) | `b1a0c0d10002` |
| Brand | `products.manufacturer` | `b1a0c0d10001` |
| Product-information rows | `product_specifications` (name, value, display_order) | `b1a0c0d10007` (#71) |
| Description text | `product_specifications`, one row named `Description` | `b1a0c0d10007`, **widened by `b1a0c0d10009`** |
| Gallery and description images | `photos` (three renditions) + `product_attachments` | `8213852b0b94`, `b1a0c0d10005` |
| Image content hash | `photos.sha256_hash` | `8213852b0b94` — **created, indexed, never written** |

The last row is the only one that changes anything about how the schema is *used*. `8213852b0b94` created the column, created `ix_photos_sha256_hash` over it, and its own data migration wrote `sha256_hash=None,  # Will be populated on future uploads`. `app/photo_service.py:114` carries the same note as `# Optional: can add hash calculation later`. FR-018 is that note being honoured; it needs no DDL.

The attachment cap FR-012 raises is `PhotoService.MAX_ATTACHMENTS_PER_PRODUCT`, a class constant with no database counterpart.

### Revision `b1a0c0d10009` — widen the specification value

**Model.** `ProductSpecification.value` gains a dialect variant, following the pattern `Photo.medium_data` already uses at `app/database.py:707`:

```python
value = Column(Text().with_variant(MEDIUMTEXT, 'mysql'), nullable=False)
```

Under SQLite — the unit suite — this stays `TEXT`, which is unbounded there anyway, so the fixtures are unaffected and the suite proves nothing about the widening. That is expected: the limit being lifted is a MariaDB limit.

**Upgrade.** `ALTER TABLE product_specifications MODIFY value MEDIUMTEXT NOT NULL`. No data migration — a widening cannot fail on existing rows, because every value already fits the larger type. `NOT NULL` is restated because MariaDB's `MODIFY` replaces the whole column definition and would otherwise silently make it nullable.

**Downgrade.** Narrowing is the direction that can lose data, so it refuses rather than truncating:

1. `SELECT id, product_id FROM product_specifications WHERE LENGTH(value) > 65535`
2. If any row comes back, raise, naming the ids and their products. Do not `MODIFY`.
3. Otherwise `ALTER TABLE product_specifications MODIFY value TEXT NOT NULL`.

`LENGTH` counts bytes, which is what the type bounds; `CHAR_LENGTH` counts characters and would under-report multi-byte text into a false pass.

### Reversibility

The round trip is lossless in the ordinary case and refuses in the case where it would not be. A database with no oversized value downgrades cleanly and re-upgrades to the same state. A database with one does not downgrade at all, and says which rows are in the way, so the operator can shorten or delete them and try again. That is the correct trade under Principle I's carve-out: simplicity never licenses losing data.

One consequence worth recording, because it is a fix this feature gets for free. `b1a0c0d10007`'s downgrade folds specification rows back into the old `products.specifications TEXT` column, and would meet the same overflow. Alembic downgrades newest-first, so `b1a0c0d10009`'s guard fires before `b1a0c0d10007` runs at all. It does not close the whole hole — `b1a0c0d10007` concatenates *every* row of a product into one `TEXT`, so many large rows could still overflow together — but that is pre-existing and out of this feature's scope.

### Existing photos keep a null hash

Only uploads from this change onward get a hash. Existing rows stay null, and null never matches, so:

- **A captured image is never wrongly skipped.** A null-hashed row cannot claim to be a duplicate of anything.
- **A captured image can be stored alongside a hand-uploaded copy of itself** that predates this change. The operator deletes one.

No backfill is written. It would mean reading every `original_data` blob in the table — the 20 MB-capped originals — to fix a cosmetic duplicate on a set of photographs that predate the feature entirely. If that duplicate ever becomes annoying, deleting the older attachment costs one click, and that annoyance would be the measurement Principle I asks for.

---

## New domain types

Both are `@dataclass` types in `app/models.py`, where the layering puts domain types and their validation. Neither is persisted; both exist only between the form and the services.

### `ListingCapture`

What the extractor found, after parsing and validation. Built by `ListingCapture.from_json(raw)`.

| Field | Type | Notes |
|---|---|---|
| `source_url` | `str` | The canonical listing address the agent read from. |
| `vendor_item_id` | `Optional[str]` | ASIN where the address yielded one. |
| `listing_title` | `Optional[str]` | |
| `price` | `Optional[str]` | **A string, deliberately.** See below. |
| `brand` | `Optional[str]` | Becomes `products.manufacturer` on a newly created product. |
| `description_text` | `Optional[str]` | Uncapped. `b1a0c0d10009` gives it 16,777,215 bytes to land in. |
| `specifications` | `list[dict[str, str]]` | `{'name', 'value'}`, already merged across the page's sections by the agent. |
| `images` | `list[str]` | Addresses, gallery first, already size-filtered by the agent. |

**Validation lives on the dataclass**, in `from_json`, and it is correctness validation rather than defensive validation:

- A payload that is absent, empty, or not a JSON object yields `None` — not an error. FR-007 requires a capture with no extraction to behave exactly as it does today, and the commonest reason for a missing payload is that the operator used the paste-a-URL form, which has no agent.
- A payload whose `version` is not `1` yields `None`, with a log line. A stale cached agent is the only way this can happen and the cache-buster makes it near-impossible; degrading beats raising on a page the operator cannot fix.
- Entries that are not `{'name', 'value'}` string pairs are dropped, not raised on. The alternative is one malformed row costing the operator the whole listing.
- `images` entries that are not `http`/`https` strings are dropped for the same reason.

**Why `price` is a string.** JSON has one number type and it is an IEEE double. `24.99` crossing a JSON boundary as a number is a `float` before any Python in this repository sees it, and Principle III has no in-transit exemption. It stays a string through the payload, through the hidden form field, through `capture_order`'s `unit_price` parameter, and becomes a `Decimal` in `_validate_price` — which is the same path a hand-typed price already takes. Nothing new is needed for this to be true; it just has to not be broken.

### `ImageCaptureResult`

What the fetcher did, so the route can tell the operator (FR-017, FR-020, FR-021, FR-022).

| Field | Type | Meaning |
|---|---|---|
| `stored` | `int` | Attachments created. |
| `duplicates` | `int` | Skipped: this content is already stored on the product, whether by an earlier capture or a moment ago by this one. |
| `skipped` | `int` | Refused by type or size. |
| `failed` | `int` | Could not be retrieved. |
| `cap_reached` | `bool` | Stopped at `MAX_ATTACHMENTS_PER_PRODUCT`. |

Plain counts and one flag. There is no per-image error list because nothing would consume it: the operator's next action is the same whether one image failed for a timeout or a 404.

---

## Specification merge semantics

The one genuinely new rule in the data model. It applies to captured rows only; the product form keeps replace-on-write.

Given the product's existing rows `E` and the captured rows `C`:

1. Validate `C` through the existing `_validate_specifications`, which trims, drops blank rows, enforces the 100-character name limit, and refuses a duplicate name *within* `C`.
2. Fold every name in `E` and in `C` with `str.lower()`, **in Python**. Never in SQL — the deployment's collation folds accents too, so `Volt` and `Vôlt` would be one name on MariaDB and two under the unit suite.
3. Keep a captured row only when its folded name is absent from `E`.
4. Append the survivors, continuing `display_order` from `max(E.display_order) + 1`, so existing rows do not move.

**Consequences, stated rather than discovered:**

- A captured value never overwrites an existing one (FR-010), and no existing row is removed (FR-011). A capture is strictly additive to specifications.
- Recapturing an unchanged listing onto the same product adds nothing the second time.
- The description row is subject to the same rule: a product that already has a `Description` specification keeps the one it has. So the description of the *first* capture wins, which is the same rule as everything else and is what "the operator's value wins" means when the operator has not touched it.
- A captured row whose name exceeds 100 characters is refused by `_validate_specifications`, and per FR-008's acceptance scenario 8 the rest still land — so the merge validates row by row rather than failing the batch.

---

## Image storage path

Per captured address, in order:

1. **Address seen already in this capture?** Skip without fetching — network economy only, not the correctness rule. It is still *counted* as whatever that address came to the first time, because a second mention of an unreachable address is a second failure and not a duplicate of anything. Only a repeat of something actually stored counts as a duplicate.
2. **Fetch** with a fixed timeout. Non-200, timeout, or connection failure → `failed += 1`, continue.
3. **Content type** not in `PhotoService.SUPPORTED_TYPES` → `skipped += 1`, continue.
4. **Size** over `MAX_FILE_SIZE` (20 MB) → `skipped += 1`, continue.
5. **SHA-256 of the retrieved bytes.** Already among this product's attachments → `duplicates += 1`, continue.
6. **Store** via `PhotoService.upload_product_attachment_if_new`, which writes the `Photo` (three renditions plus the hash) and the `ProductAttachment`. On `ValueError` naming the cap → `cap_reached = True`, stop.

The hash is taken over the bytes as retrieved, which is what `_process_photo` stores as `original_data` — it returns `original_bytes = file_data` unchanged (`app/photo_service.py:486`). Hashing the thumbnail or the medium rendition would be hashing a Pillow output, which is not stable across Pillow versions.

**Filenames** are derived, not taken from the address: `{vendor_item_id or 'listing'}-{index:02d}{ext}`. Amazon's image filenames are opaque hashes and the attachment card shows filenames today. FR-013 replaces that card with a thumbnail grid, but the filename remains what a download is called.

---

## What is not modelled

- **No record of where an image came from.** No `source_url` column on `photos` or `product_attachments`. Nothing in the spec asks which address an image arrived from, dedupe is by content rather than address, and a column nothing reads is the speculative generality Principle I prohibits.
- **No capture record.** An unconfirmed capture is a form. A confirmed one is a purchase, which already carries the listing address, title and date. There is no third thing.
- **No distinction between a gallery image and a description image.** The size filter runs in the browser where the dimensions are knowable, so the payload is one flat list and the server never needs the distinction. This is what allows FR-019's carve-out — gallery images are exempt from the filter — to be true without the server being trusted to honour it.
