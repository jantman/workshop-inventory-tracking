# Phase 1 Data Model: Order Capture Confirmation

One new column, one new in-memory type, and three existing fields that change hands. Nothing else in the schema moves.

## `purchases.listing_url` — the new column

```python
# app/database.py, on Purchase, next to listing_title
listing_url = Column(String(1000), nullable=True)
```

| Property | Value | Why |
|---|---|---|
| Nullable | yes | A purchase recorded by hand through `purchase_add` has no listing. So does every row that predates this feature and whose notes never held a URL. Absent is an ordinary state. |
| Length | 1000 | Vendor listing URLs with tracking segments run long; Amazon's routinely pass 200 characters. 1000 is generous without being a `TEXT`, which would be harder to compare and impossible to index if that ever changed. |
| Indexed | no | Argued in [research.md](./research.md#why-listing_url-is-not-indexed). Also physically awkward: 1000 × utf8mb4 = 4000 bytes, over InnoDB's 3072-byte key limit. |
| Default | none | Not `''`. Unlike `product_identifiers.vendor`, nothing here depends on NULL-vs-empty behaving a particular way in a unique index, because there is no unique index. |

It is exposed on `Purchase.to_dict()` as `listing_url`, alongside `listing_title`. That is additive to the JSON shape; nothing reading the dict today loses a key.

### Why it is not `purchases.notes`

`capture_order` currently passes `notes=url` (`app/catalog_service.py:948`), so for a captured purchase the notes field *is* the URL. The receive screen renders that same field as an editable textarea (`app/templates/product/receive.html:92`) with the label "Notes". The two facts have been sharing a column, and the shared column belongs to the one the operator is invited to overwrite.

After this feature, `capture_order` writes the URL to `listing_url` and leaves `notes` alone. Notes become the operator's notes.

## Migration `b1a0c0d10008`

Parent revision: `b1a0c0d10007` (the current head, structured product specifications).

### Upgrade

1. `op.add_column('purchases', sa.Column('listing_url', sa.String(1000), nullable=True))`
2. Backfill, in one statement wrapped in `sa.text(...)` as the technology constraints require:

   ```sql
   UPDATE purchases
      SET listing_url = notes
    WHERE listing_url IS NULL
      AND notes LIKE 'http%'
   ```

   `LIKE 'http%'` is the whole test. It is not trying to validate a URL — it is recovering the specific thing `capture_order` wrote, which is a bare URL and nothing else. A notes field that begins with a URL and continues with prose is not a captured URL and is left alone, at the cost of one purchase not participating in duplicate detection. Notes are **not** cleared: the backfill copies, it does not move, so nothing the operator wrote is destroyed and the upgrade is safe to re-run.

### Downgrade

1. Fold the value back to where it used to live, for rows that would otherwise lose it:

   ```sql
   UPDATE purchases
      SET notes = listing_url
    WHERE listing_url IS NOT NULL
      AND (notes IS NULL OR notes = '')
   ```

2. `op.drop_column('purchases', 'listing_url')`

### Reversibility

The round trip is lossless for every row the feature created: capture writes the URL to `listing_url` and nothing to `notes`, so `notes` is empty when the downgrade runs and the URL lands back exactly where the pre-feature code would have put it. Upgrading again re-reads it.

One case is not lossless, and is stated rather than glossed: a purchase captured after this feature whose notes the operator has since written into keeps those notes and loses the separate URL on downgrade. Overwriting the operator's prose to preserve a URL would be the worse trade, and the URL is recoverable from the listing while the prose is not.

**No test suite exercises this.** `tests/conftest.py:51` and `tests/e2e/test_server.py:62` both build the schema with `Base.metadata.create_all`, so Alembic never runs under `nox`. The round-trip in [quickstart.md](./quickstart.md#3-exercise-the-migration-both-ways) is the only coverage this migration gets, it runs against a disposable MariaDB container, and it is a required step.

## `CaptureAssessment` — the new in-memory type

A `@dataclass` in `app/models.py`, where the project's domain types live. It is never persisted and has no table.

```python
@dataclass
class CaptureAssessment:
    """What capture found that it will not decide on its own."""
    duplicate_purchase_id: Optional[int] = None
    duplicate_order_date: Optional[datetime] = None
    duplicate_vendor: Optional[str] = None

    matched_product_id: Optional[int] = None
    matched_product_description: Optional[str] = None
    matched_product_manufacturer: Optional[str] = None
    matched_product_part_number: Optional[str] = None

    @property
    def has_duplicate(self) -> bool: ...
    @property
    def has_uncorroborated_match(self) -> bool: ...
```

**Why plain values and not the ORM rows.** Not because scalars would break — `CatalogService` sets `expire_on_commit=False` precisely so a returned object stays readable after its session closes. The hazard is narrower and worth naming exactly: a **relationship** that was not eagerly loaded raises on first touch, and a display-only object handed to a template has no business carrying that hazard. Copying the four strings and two ids the warning panels actually render also makes the assessment serializable for the JSON representation of `/api/capture` with no second shaping step.

**Both flags can be true at once.** A capture can be both a probable repeat *and* land on a recycled identifier; the template renders two panels and the service requires both decisions before writing. Nothing about the two questions is exclusive.

## Fields that change hands

### `products.description`

Unchanged in shape — `String(255)`, `nullable=False`, validated by `_validate_description` (`app/catalog_service.py:1795`) against `MAX_DESCRIPTION_LENGTH = 255`. What changes is who writes it and when:

| Before | After |
|---|---|
| Set from the listing title at capture, for a newly created product only. Never touched when attaching to an existing product. | Set from the operator's `description` at capture when supplied, falling back to the listing title (FR-003). When attaching to an existing product, the operator's description **replaces** that product's, if they changed it (FR-005). Editable again at receipt (FR-022). |

Reusing `_validate_description` is what makes FR-006 (refuse over-length, never truncate) and FR-024 (refuse blank at receipt) fall out with no new validation code — it already raises `ValidationError` for both, with the field named.

Note the deliberate reversal of `test_attaching_does_not_overwrite_the_operators_own_description` (`tests/unit/test_capture.py:155`). That test protects the operator's wording from *the vendor's* wording, which is still correct and still holds when the description field is left blank. It does not protect the operator's wording from the operator, which is what FR-005 asks for. The test is rewritten to assert the narrower, still-true property.

### `products.manufacturer` and `products.manufacturer_part_number`

Both already exist and are already editable through `update_product`. Capture starts writing them on product creation, and reads them — from the *matched* product — to evaluate corroboration. Capture never overwrites them on an existing product: a mismatch there is the signal that something is wrong, and silently overwriting the evidence would destroy the signal.

### `purchases.notes`

Stops receiving the listing URL from capture. Otherwise unchanged, including the receive screen's ability to replace it.

## Every reader of the fields this feature repurposes

Enumerated so that nothing changes meaning silently.

| Reader | Reads | Effect |
|---|---|---|
| `app/catalog_service.py:948` (`capture_order`) | writes `notes=url` | **Changed** — writes `listing_url=url`, leaves notes alone. |
| `app/catalog_service.py:951` (`_find_captured_purchase`) | `vendor`, `vendor_item_id`, `order_date` | **Changed** — gains a `listing_url` fallback branch and returns `None` only when neither an item id nor a URL is available. |
| `app/catalog_service.py:1023` (`receive_purchase`) | `notes` param | Unchanged. Still replaces notes when supplied. |
| `app/templates/product/receive.html:92` | `purchase.notes` | Unchanged markup; for newly captured purchases the box is now empty instead of holding a URL. |
| `Purchase.to_dict` (`app/database.py:1059`) | all columns | **Changed** — gains `listing_url`. Additive. |
| `app/api_client.py` | — | Does not touch purchases or capture. No contract impact. |
| `tests/unit/test_capture.py:75` | `AMAZON_URL in purchase.notes` | **Rewritten** to assert `purchase.listing_url`. |

## State, such as it is

There is no status column and no state machine. A purchase is outstanding when `received_date IS NULL` and received otherwise, exactly as before (`Purchase.is_outstanding`, `app/database.py:1054`). This feature adds no state to a purchase; the "unconfirmed capture" is not a state of anything, because it is not a row.

The one transition worth naming is the one that is *not* a transition. Re-submitting the receive form on an already-received purchase is guarded for exactly two things — `received_date` itself, and the product-side effects (the tracked count and the manual low flag) — and is *not* guarded for quantity, price or notes, which are amended whenever supplied. The description joins that second group (FR-025), so its assignment sits outside the `if not already_received:` block in `receive_purchase`. That is the single easiest thing in this feature to put in the wrong place.

A consequence for the template: `app/templates/product/receive.html:52` currently tells the operator "This purchase was already received on *date*. Submitting again changes nothing." That sentence is already an overstatement of what the code does, and this feature makes it plainly wrong. It is corrected to say what re-submitting does and does not change.
