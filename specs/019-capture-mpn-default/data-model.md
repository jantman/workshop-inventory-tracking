# Phase 1 Data Model: The Captured Listing Fills In the Manufacturer Part Number

**Feature**: `specs/019-capture-mpn-default` | **Date**: 2026-08-18

## No schema change

**There is no Alembic revision in this feature.** No table, no column, no index, no constraint. If a
migration appears in the diff, the plan has been misread.

Everything this feature reads and writes already exists:

| Thing | Where it lives | What changes |
|---|---|---|
| `Product.manufacturer_part_number` | `app/database.py:838`, `String(100)`, nullable | Nothing. Same column, same width, same nullability, same writer. |
| `Product.specifications` | existing specification rows | Nothing. No row is filtered, hidden, moved or removed on account of its name (FR-008). |
| `ListingCapture.specifications` | `app/models.py:621`, `List[Dict[str, str]]`, not persisted | Nothing. Read, never modified. |
| `LISTING_CAPTURE_VERSION` | `app/models.py:599`, currently `1` | **Not bumped.** The payload shape is unchanged, so a cached bookmarklet keeps working — see [research.md](./research.md) §1. |

## Entities

### `ListingCapture` (existing, `app/models.py:603`)

An in-flight dataclass, not persisted, built only by `from_json`. It gains one method and no fields.

```python
def manufacturer_part_number(self) -> Optional[str]:
    """The part number this listing's own rows name, or None."""
```

**Contract** (FR-001 through FR-004):

- Walks `PART_NUMBER_ROW_NAMES` in order. For each name, walks `self.specifications` in captured
  order and returns the first row whose normalized name equals it **and** whose value is usable.
- A row's name is normalized with `normalized_row_name` — trimmed, internal whitespace collapsed,
  upper-cased.
- A value is usable when, with surrounding whitespace removed, it is non-empty and at most
  `MANUFACTURER_PART_NUMBER_MAX_LENGTH` characters. An unusable row is passed over and the walk
  continues; it does not end the search.
- Returns the value with surrounding whitespace removed and nothing else altered.
- Returns `None` when no row qualifies, including when `specifications` is empty.
- **Pure.** No I/O, no request, no database, no mutation of `self`. Safe to call from a template
  and safe to call more than once per request.

### Module constants (new, `app/models.py`)

```python
PART_NUMBER_ROW_NAMES = (
    'MANUFACTURER PART NUMBER',
    'MFR PART NUMBER',
    'PART NUMBER',
    'MODEL NUMBER',
    'ITEM MODEL NUMBER',
)

MANUFACTURER_PART_NUMBER_MAX_LENGTH = 100
```

- `PART_NUMBER_ROW_NAMES` is a **tuple**, because order is the specification (FR-002), and its
  entries are stored already normalized so they compare directly against `normalized_row_name(...)`.
  A test asserts each entry is its own normalized form, so a typo cannot make one permanently
  unmatchable.
- `MANUFACTURER_PART_NUMBER_MAX_LENGTH` mirrors the `String(100)` at `app/database.py:838`. It
  carries a comment naming that line. It does **not** replace the existing `maxlength="100"`
  attributes in the two templates; see [research.md](./research.md) §4.

### `normalized_row_name` (new, `app/models.py`)

```python
def normalized_row_name(name: Optional[str]) -> str:
    """A specification row's name, folded for comparison against a fixed list."""
```

Trims, collapses internal whitespace runs, upper-cases. Lifted verbatim from the body of
`_is_barcode_row_name` (`app/catalog_service.py:2541`), which is rewritten to call it. **Two
callers, one implementation** — FR-001. `app/catalog_service.py` already imports from `.models`, so
no new dependency edge is created.

Do not merge this with `_fold` (`app/catalog_service.py:2536`). They answer different questions and
`_fold` deliberately does not collapse internal whitespace; see [research.md](./research.md) §2.

## State and lifecycle

None. The derived value has no lifecycle: it exists for the duration of one render, and is either
submitted by the operator or it is not. Nothing records that a stored part number was derived rather
than typed, and nothing downstream may treat a derived one differently — it is a default, not an
assertion.

## Validation rules

| Rule | Source | Where enforced |
|---|---|---|
| Recognized names, folded, in priority order | FR-001, FR-002 | `PART_NUMBER_ROW_NAMES` + `normalized_row_name` |
| Non-empty after trimming | FR-003 | `ListingCapture.manufacturer_part_number` |
| At most 100 characters | FR-003 | `ListingCapture.manufacturer_part_number` |
| Trimmed, otherwise unaltered | FR-004 | `ListingCapture.manufacturer_part_number` |
| Operator's value wins; empty counts as a value, absent does not | FR-005 | `app/product/routes.py`, `product_capture` POST |
| Redisplay what was submitted, not the default | FR-006 | `app/templates/product/capture.html`, presence test |
| Capture form only | FR-010 | Nothing added to `_form_product_fields`; `_form_fields.html` untouched |

No new exception type. Nothing here can fail: an unusable row yields `None`, and `None` is the
ordinary case for every capture that carries no part-number row (FR-009).
