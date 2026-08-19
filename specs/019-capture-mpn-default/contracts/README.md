# Phase 1 Contracts: The Captured Listing Fills In the Manufacturer Part Number

**No HTTP contract change.** No new endpoint, no new route, no new request or response field, no
JSON shape altered, and no bump to `LISTING_CAPTURE_VERSION`. The bookmarklet's payload is
byte-identical before and after this feature, which is what lets an operator with a cached
bookmarklet keep capturing.

What follows is the internal surface the feature adds, and the two existing contracts it leans on.

---

## New: `ListingCapture.manufacturer_part_number`

```python
def manufacturer_part_number(self) -> Optional[str]:
    """The part number this listing's own rows name, or None.

    A default for the confirmation form, never an assertion about the product.
    """
```

- Returns the value of the highest-priority usable row named in `PART_NUMBER_ROW_NAMES`, trimmed.
  Priority is by position in that tuple, **not** by position in `self.specifications`; among rows
  sharing a name, the first in captured order wins (FR-002).
- Returns `None` when no row qualifies — the ordinary case, not an error (FR-009).
- **Pure and total.** No I/O, no exceptions, no mutation. It is called from a Jinja template, so it
  must stay that way: if it ever needs a database session, the design in
  [research.md](../research.md) §1 has been misread.
- Callers: `app/templates/product/capture.html` (render) and `app/product/routes.py`
  `product_capture` (write fallback). Nothing else.

## New: `normalized_row_name`

```python
def normalized_row_name(name: Optional[str]) -> str:
    """A specification row's name, folded for comparison against a fixed list."""
```

Trim, collapse internal whitespace, upper-case. `None` folds to `''`.

**This is a move, not a new rule.** The body comes out of `_is_barcode_row_name`
(`app/catalog_service.py:2541`), which now calls it. Behavior for barcode names is unchanged and
`tests/unit/test_capture.py` should stay green untouched — if it does not, the move was not verbatim.

## New: module constants

```python
PART_NUMBER_ROW_NAMES: tuple[str, ...]      # five names, pre-normalized, priority order
MANUFACTURER_PART_NUMBER_MAX_LENGTH = 100   # mirrors app/database.py:838
```

Both in `app/models.py`. `PART_NUMBER_ROW_NAMES` entries are stored in their own normalized form; a
test asserts that, because an entry that is not normalized can never match anything and would fail
silently.

---

## Changed: the confirmation form's Manufacturer Part Number field

`app/templates/product/capture.html`, the `manufacturer_part_number` input.

**Was**: `value="{{ form_data.get('manufacturer_part_number') or '' }}"`

**Becomes** a presence test on the key rather than a truthiness test on the value, falling back to
`listing.manufacturer_part_number()`.

The contract this states, and the reason the test is on presence:

| Render path | key in `form_data` | Field shows |
|---|---|---|
| Bookmarklet lands (`api_capture`, form body) | absent | the listing's part number |
| Paste-a-URL GET | absent | the listing's part number, or empty when there is no listing |
| Re-render after a capture question | present | exactly what was submitted, **empty included** |
| Re-render after a validation refusal | present | exactly what was submitted, **empty included** |

**The empty-included rows are the contract.** A cleared field that comes back filled is the failure
this feature exists to avoid (FR-006).

**Not changed, deliberately**: the `manufacturer` field two lines above, and the unit price field
below. Both still use `or`, and both still re-apply their default over a cleared field on re-render.
That is a known wart, it is out of scope by a stated spec assumption, and it must not appear in this
diff.

## Changed: `product_capture`'s write path

`app/product/routes.py`, `product_capture` POST branch. `manufacturer_part_number` joins
`manufacturer` and `unit_price` in the absent-versus-empty fallback that already sits at lines
415–421:

```python
manufacturer_part_number = request.form.get('manufacturer_part_number')
if listing is not None:
    if manufacturer_part_number is None:
        manufacturer_part_number = listing.manufacturer_part_number()
```

**Absent, not merely empty** (FR-005). The confirmation form always submits the field, so an empty
arrival is a field the operator *cleared*, and clearing is a decision. The existing comment at that
site already says this; the new field is covered by it.

---

## Unchanged, and relied upon

### `CatalogService.capture_order`

Signature untouched. It already takes `manufacturer_part_number`; this feature only changes what is
handed to it. Its existing rule that **capture never writes a manufacturer or part number onto a
product that already exists** (`app/catalog_service.py`, the `else` branch at line 1213) stays
exactly as it is — a mismatch there is the evidence the recycled-identifier question depends on.

### `CatalogService.merge_specifications`

Untouched, and deliberately not consulted. Unlike 016, this feature does not condition on whether a
row survived the merge; see [research.md](../research.md) §6.

### The ordinary product create and edit forms

`app/templates/product/_form_fields.html` and `_form_product_fields` in `app/product/routes.py` get
**no** derivation (FR-010). A part-number-named row typed by hand does not populate anything; the
operator typing a row is already looking at the field.

### `/api/capture` with a JSON body

Unchanged. That representation calls `capture_order` without a `listing`, so it has no rows to
derive from and nothing to apply. See [research.md](../research.md) §7.
