# Contract: `CatalogService` and `app/exceptions`

Two methods change signature, one private helper changes shape, two helpers are new, and one exception is added. Everything else in `CatalogService` is untouched.

## New: `CaptureDecisionRequired`

```python
# app/exceptions.py
class CaptureDecisionRequired(WorkshopInventoryError):
    """Capture found something only the operator can settle. Nothing was written.

    Carries the assessment so the caller can render the question. This is a step
    in a flow, not a failure: it is raised on the ordinary path whenever a
    capture would otherwise have guessed.
    """
    def __init__(self, message: str, assessment: CaptureAssessment) -> None: ...

    assessment: CaptureAssessment
```

**Guarantee**: when this is raised, no product, purchase, or identifier has been created or modified. The service performs its detection before it opens a write.

**Deliberately not given a global error handler.** `app/error_handlers.py` registers handlers for `ValidationError`, `StorageError`, `ItemNotFoundError`, `AuthenticationError`, `ConfigurationError`, 500 and 404 — there is no handler for `WorkshopInventoryError` itself. An unhandled `CaptureDecisionRequired` therefore reaches the 500 page, which is the right outcome: every caller has to say what the question looks like.

## Changed: `capture_order`

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
    # -- new: what the operator writes while the listing is on screen
    description: Optional[str] = None,
    manufacturer: Optional[str] = None,
    manufacturer_part_number: Optional[str] = None,
    # -- new: decisions the operator has already made
    acknowledged_duplicate_of: Optional[int] = None,
    attach_to: Optional[Union[int, str]] = None,
) -> Purchase:
```

Every existing parameter keeps its name, position and meaning. A caller passing only the old arguments still works, and still creates a product and a purchase — but now raises instead of guessing when it would previously have guessed.

### Order of operations

1. **Validate.** `vendor` required (unchanged). `unit_price` through `_validate_price`, `quantity` through `_validate_purchase_quantity`, `order_date` through `_parse_datetime` defaulting to midnight today — all unchanged. `description`, when not `None`, through `_validate_description`, which raises `ValidationError` for blank and for over-255 (FR-006).
2. **Detect a duplicate** via `_find_captured_purchase`.
3. **Resolve the product** — attach, create, or ask.
4. **Raise** `CaptureDecisionRequired` if step 2 or step 3 produced an unanswered question. Nothing has been written at this point.
5. **Write**: create or update the product, then `record_purchase(..., listing_url=url)`.

### `acknowledged_duplicate_of`

| Value | Detected duplicate | Result |
|---|---|---|
| `None` | none | Proceed. |
| `None` | purchase `N` | **Raise**, assessment names `N`. |
| `N` | purchase `N` | Proceed — the operator saw this one and said it is a separate order (FR-014, FR-015). |
| `N` | purchase `M` (`M != N`) | **Raise**, assessment names `M`. The acknowledgement was for a different row and is stale. |
| `N` | none | Proceed. Nothing to warn about. |

### `attach_to`

| Value | Meaning |
|---|---|
| `None` | Decide automatically: create when there is no match, attach when the match is corroborated, **raise** otherwise. |
| `'new'` | Create a product regardless of any match (FR-020). Always honoured; never stale. |
| `int` | Attach to that product. Honoured when it equals the currently detected match. If it names a product that no longer exists, fall back to creating one and log it — the spec's stated edge case. If it names a *different* existing product from the detected match, **raise**: the decision is stale. |

### The corroboration rule (FR-019)

```python
def _corroborates(product, manufacturer, part_number) -> bool:
    return bool(
        manufacturer and part_number
        and _fold(manufacturer) == _fold(product.manufacturer)
        and _fold(part_number) == _fold(product.manufacturer_part_number)
    )

def _fold(value: Optional[str]) -> str:
    return (value or '').strip().casefold()
```

Both values required, both compared case-insensitively after trimming, both in Python. A matched product carrying no manufacturer can never corroborate, because `_fold(None)` is `''` and a truthy `manufacturer` cannot fold to `''`. Why this is not a `WHERE` clause: [research.md](../research.md#the-collation-question).

### Product resolution, in full

| Item id | `attach_to` | Match found | Corroborated | Outcome |
|---|---|---|---|---|
| absent | `None` | — | — | Create (FR-021). |
| present | `None` | no | — | Create (FR-021). |
| present | `None` | yes | yes | Attach silently (FR-019). |
| present | `None` | yes | no | **Raise** (FR-017, FR-018). |
| any | `'new'` | — | — | Create; the matched product, its identifiers and its history are untouched (FR-020). |
| any | `int` | — | — | Attach to it, or create if it has vanished. |

When a product is created, its `description` is the operator's, falling back to the listing title, falling back to the existing `f"{vendor} item {item_id or 'without an identifier'}"` string (FR-003). It carries `manufacturer` and `manufacturer_part_number` when supplied, and the `VENDOR` identifier when there is an item id — all as today.

When attaching to an existing product, the operator's `description` replaces that product's description if it differs (FR-005); a blank or omitted description leaves it alone. `manufacturer` and `manufacturer_part_number` are **never** written to an existing product: a mismatch there is the evidence, and overwriting evidence is how the corruption this feature prevents would come back.

### Raises

- `ValidationError` — missing vendor, bad price, bad quantity, unparseable date, blank or over-length description.
- `CaptureDecisionRequired` — an unacknowledged duplicate, or an uncorroborated identifier match.
- `ItemNotFoundError` — not raised for a vanished `attach_to`; that falls back to creating.

## Changed: `_find_captured_purchase`

```python
def _find_captured_purchase(
    self,
    vendor: str,
    vendor_item_id: Optional[str],
    listing_url: Optional[str],
    order_date: datetime,
) -> Optional[Purchase]:
```

Same one-day window as today (`day_start` at midnight, `day_end` a day later), so time of day still does not matter. What changes is the key:

- `vendor_item_id` present → match on `vendor` + `vendor_item_id` + the day. Unchanged behaviour.
- `vendor_item_id` absent, `listing_url` present → match on `vendor` + `listing_url` + the day (FR-013).
- Neither → `None`. Nothing to recognize, and that stays true.

It remains a private read that returns a row or nothing. Its meaning changes at the call site, not here: the result used to short-circuit the write, and now feeds a question.

## Changed: `receive_purchase`

```python
def receive_purchase(
    self,
    purchase_id: int,
    received_date: Optional[datetime] = None,
    quantity: Optional[int] = None,
    unit_price: Optional[Any] = None,
    notes: Optional[str] = None,
    description: Optional[str] = None,   # new
) -> Purchase:
```

- `description=None` — the product's description is not touched. Every existing caller, including `tests/unit/test_stock_status.py`, keeps its current behaviour.
- `description` supplied — validated through `_validate_description` **before the session opens**, so a blank or over-length value refuses the whole submission and leaves both the description and the received state alone (FR-024). Applied to the product only when it differs from the current value (FR-026).
- The assignment sits **outside** the `if not already_received:` block, so a description correction lands on an already-received purchase while the received date, the tracked count and the manual low flag stay untouched (FR-025).

Everything else — the receipt-order validation, the quantity and price amendments, the count increment, the manual-flag clear — is unchanged.

## Changed: `record_purchase`

Gains `listing_url: Optional[str] = None`, stored on the new column. Positioned after `listing_title`, which is the field it belongs with. No other change; `notes` keeps its current meaning and is no longer where `capture_order` puts the URL.

## New: `CaptureAssessment`

Defined in `app/models.py`; shape and rationale in [data-model.md](../data-model.md#captureassessment--the-new-in-memory-type). It carries ids and display strings, never ORM rows, so a template can render it after the service's session has closed.

## What does not change

`create_product`, `update_product`, `find_product_by_identifier`, `get_product`, `get_purchase`, `search_products`, and every tag, category, specification and label method. `app/api_client.py` touches none of this and needs no change — its `__all__` surface is unaffected.
