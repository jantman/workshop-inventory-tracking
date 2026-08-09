# Contract: service surface

Changed and new methods. Existing signatures keep their meaning; every change below is additive with a default that preserves current behaviour.

---

## `CatalogService.capture_order` — one new parameter

```python
def capture_order(
    self,
    vendor: str,
    vendor_item_id: Optional[str] = None,
    listing_title: Optional[str] = None,
    url: Optional[str] = None,
    unit_price: Optional[Any] = None,
    quantity: Optional[int] = None,
    order_date: Optional[datetime] = None,
    description: Optional[str] = None,
    manufacturer: Optional[str] = None,
    manufacturer_part_number: Optional[str] = None,
    acknowledged_duplicate_of: Optional[Any] = None,
    attach_to: Optional[Any] = None,
    listing: Optional[ListingCapture] = None,      # NEW
) -> Purchase:
```

`listing=None` is exactly today's behaviour, which is what keeps the paste-a-URL form and the JSON representation of `/api/capture` working untouched.

**Where it takes effect.** After the product is resolved — which is after both decision questions have been settled and after the product has been created or attached to — and before `record_purchase`. That ordering matters: the merge target is not known until the recycled-identifier question is answered, so applying the listing any earlier would mean applying it to the wrong product or refusing to apply it at all.

**What it does, in order:**

1. If `listing.specifications` is non-empty, `merge_specifications(product.id, listing.specifications)`.
2. If `listing.description_text` is set, merge one further row `{'name': 'Description', 'value': text}` through the same call, so it obeys the same "already present wins" rule.
3. Nothing else. The brand reaches `products.manufacturer` through the existing `manufacturer` parameter, which the route fills from `listing.brand` when the operator has not typed one; the price reaches `unit_price` the same way. **`capture_order` never fetches an image.**

**What it does not do, and why.** It does not write `manufacturer` onto an *existing* product, because `capture_order` already deliberately does not (`app/catalog_service.py:1046`): a mismatch there is the evidence the recycled-identifier question depends on, and a capture that silently corrected it would destroy the signal.

**Raises**: unchanged — `ValidationError`, `CaptureDecisionRequired`. Both still raise before anything is written.

---

## `CatalogService.merge_specifications` — new

```python
def merge_specifications(
    self, product_id: int, entries: List[Dict[str, str]]
) -> int:
    """Add captured specification rows without disturbing what is there.

    Returns the number of rows added.
    """
```

Additive only. The rule and its consequences are in [data-model.md](../data-model.md#specification-merge-semantics); the contract is:

- Validates `entries` through the existing `_validate_specifications`, row by row rather than as a batch, so one over-length name costs one row.
- Compares folded names **in Python**, never in SQL.
- A captured name already present on the product is dropped whole — value included.
- Appends survivors after the highest existing `display_order`, so no existing row moves.
- Removes nothing, ever. This is the FR-011 invariant, and it is a property of the method rather than of its callers.
- Returns the count added; `0` is an ordinary outcome, not a failure.
- **Raises** `ItemNotFoundError` if the product does not exist.

`update_product(specifications=[...])` is unchanged and still replaces. The two are not variants of each other: the form posts a complete set, a capture posts an incomplete one.

---

## `PhotoService` — one constant, one changed method, one new method

### `MAX_ATTACHMENTS_PER_PRODUCT: 25 → 100`

FR-012. The comment already at `app/photo_service.py:53` explains why it is a separate constant from `MAX_PHOTOS_PER_ITEM`; that reasoning is unchanged and `MAX_PHOTOS_PER_ITEM` stays at 10.

### `_upload_attachment` — now populates `sha256_hash`

```python
photo = Photo(
    ...,
    sha256_hash=hashlib.sha256(file_data).hexdigest(),   # was: not set
)
```

Hashed over the bytes as received, which is what `_process_photo` returns as `original_data` unchanged. One line, one import, and it closes the note the column has carried since `8213852b0b94`. Every attachment path benefits, including the hand-upload and paste paths — not only capture.

`upload_photo` (inventory item photos) is **not** changed. Its `sha256_hash=None` at line 114 stays as it is: nothing deduplicates item photos, and changing it would be a change no requirement asks for.

### `upload_product_attachment_if_new` — new

```python
def upload_product_attachment_if_new(
    self, product_id: int, file_data: bytes, filename: str, content_type: str
) -> Optional[ProductAttachment]:
    """Attach unless this product already holds these exact bytes.

    Returns None when the content is already present.
    """
```

- Computes the hash, looks for a `ProductAttachment` on this product whose `Photo.sha256_hash` matches, and returns `None` if one exists.
- Otherwise delegates to `upload_product_attachment`, so validation, processing, the cap and the error contract are shared rather than reimplemented.
- **Raises** `ValueError` for the cap and for a refused type or size, matching `upload_product_attachment`. The caller distinguishes the cap by the message, which is how the existing route already treats it.

The dedupe query is scoped to the product. A different product holding the same bytes gets its own attachment row pointing at its own `Photo` — cross-product blob sharing is a storage optimization nothing has asked for.

---

## `app/services/listing_images.py` — new module

```python
def store_listing_images(
    product_id: int,
    urls: List[str],
    storage_backend,
    timeout: float = 10.0,
) -> ImageCaptureResult:
    """Retrieve captured image addresses and attach them to a product."""
```

The only place in `app/` that makes an outbound HTTP request to a third party.

**Contract:**

- Never raises for a per-image problem. Every failure mode is a counter on `ImageCaptureResult` (FR-020).
- Processes addresses in order, skipping an address already seen in this call.
- Stops on the cap, sets `cap_reached`, and returns what it managed (FR-022).
- Returns counts only. See [data-model.md](../data-model.md#imagecaptureresult) for the fields and [data-model.md](../data-model.md#image-storage-path) for the per-image sequence.
- Takes the storage backend rather than creating one, matching how the routes already construct `PhotoService`.
- `timeout` is a parameter with a default rather than a config setting, because a configuration knob for a value nobody will change is the speculative generality Principle I prohibits. It is a parameter at all so the unit tests can assert it is passed to `requests.get`.

**What it is not.** Not a class — there is no state to hold. Not a retry loop — a failed image is reported, and the operator can add it by hand or capture again. Not concurrent — see [research.md](../research.md#why-image-retrieval-is-synchronous).
