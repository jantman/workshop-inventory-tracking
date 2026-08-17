# Phase 1 Contracts: A Captured Barcode Becomes a Scannable Identifier

No HTTP contract changes. No new endpoint, no new request or response field, no JSON shape altered.
What follows is the internal surface the feature adds or changes, and the existing contracts it
leans on unchanged.

## Changed: `CatalogService.merge_specifications`

```python
def merge_specifications(
    self, product_id: int, entries: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    """... Returns: the validated entries it appended, in order. Empty is ordinary."""
```

**Was** `-> int` (the count). `len()` of the new value is the old value, so `if added:` and the log
line are unchanged in meaning.

Callers: `_apply_listing` only, in application code. Two assertions in `tests/unit/test_capture.py`
(around lines 1162 and 1208) move from comparing a number to comparing `len(...)`.

Why it changes: it is the only place that knows which captured rows were actually added, and FR-003
turns on exactly that. See [research.md](./research.md) §2.

## New: `CatalogService.describe_captured_barcodes`

```python
def describe_captured_barcodes(
    self, product_id: int, listing: ListingCapture
) -> List[CapturedBarcode]:
    """What became of the listing's barcode-named rows. Reads; never writes."""
```

- Returns one entry per barcode-named row in `listing.specifications`, in listing order,
  **deduplicated by normalized key** (FR-009: equivalent forms are one barcode, so one line).
- Returns `[]` when the listing has no barcode-named row — the route then flashes nothing (FR-013).
- **Read-only.** It is called after the write and must stay that way; if it ever needs to write, the
  design in [research.md](./research.md) §3 has been misread.

`CapturedBarcode` fields and the outcome rules are in [data-model.md](./data-model.md).

## New: private promotion step

```python
def _promote_barcode_rows(self, product_id: int, added: List[Dict[str, str]]) -> None
```

Called by `_apply_listing` with `merge_specifications`' return value. Writes at most one identifier
per entry, swallows and logs `DuplicateItemError` and `ValidationError` (FR-011), and has **no
override parameter** — FR-004 is enforced by there being nothing to pass.

## Message shapes (the confirmation page)

One flash per capture, built by `_barcode_tally(notes)` next to `_image_tally`, following its rule:
everything that did not land is named. One sentence per note, joined with a space.

| Outcome | Sentence |
|---|---|
| `recorded` | `Barcode 00012345678905 is recorded on this product.` |
| `unusable` | `The listing's UPC value 01234567890X was not recorded: it is not a valid barcode. It is kept as a specification.` |
| `taken` | `Barcode 00012345678905 was not recorded: product 42 (12V 3A PSU) already holds it. It is kept as a specification.` |
| `not_examined` | `The listing's UPC row was not examined, because this product already lists a UPC row.` |

Category: `'success'` when every note is `recorded`, `'warning'` otherwise. The exact wording is not
a contract — the E2E tests should assert on a distinctive fragment (the barcode value, `not
recorded`, `not examined`), not on a whole sentence, so that rewording does not break them.

## Reused unchanged — do not reimplement

| Contract | Where | Used for |
|---|---|---|
| `gtin.normalize_and_validate(value) -> Optional[str]` | `app/utils/gtin.py` | FR-002, the whole of "is this a barcode" |
| `CatalogService.add_identifier(product_id, id_type, value)` | `app/catalog_service.py` | The write, including the same-product no-op (FR-007) and the other-product refusal (FR-006) |
| `DuplicateItemError` (`.item_id`) | `app/exceptions.py` | Raised by `add_identifier` when another product holds the value; the write path catches it, logs the id and moves on |
| `CatalogService.find_product_by_identifier(value, id_type)` | `app/catalog_service.py` | Classifying a row for the report — and where the `taken` message gets the holder's description, since it returns the `Product` |
| `uq_identifier_type_value_vendor` | `product_identifiers` | "One product per barcode" as a database property |
| `POST /products/capture` | `app/product/routes.py` | The capture write path; request and response unchanged |
| `POST /api/scan` and the find-by-code path | `app/product/routes.py` | Resolving the promoted barcode. **Untouched** — it already resolves `GTIN` identifiers, which is the reason this feature is worth building |

## Explicitly not part of any contract

- `POST /api/capture` (the JSON representation) never passes a `listing`, so no capture through it
  can promote anything. Its response shape does not gain a barcode field.
- No template, CSS or JavaScript changes, so there are no new DOM hooks and no screenshot
  regeneration. E2E tests use the existing `#identifier-list` on the product detail page and the
  existing flash-message region.
