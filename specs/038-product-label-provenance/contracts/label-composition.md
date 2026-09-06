# Contract: label composition service

`app/services/product_label.py`. Three public functions change. This module is internal to the
application — the contract that matters is to its two callers (`app/product/routes.py` and the
unit tests), not to anything outside the repository.

## `format_provenance`

### Before

```python
def format_provenance(purchase) -> Optional[str]
```

Returned one string, or `None` when `purchase` was `None`.

### After

```python
def format_provenance(
    purchase,
    manufacturer: Optional[str] = None,
    part_number: Optional[str] = None,
) -> List[str]
```

Returns a list of 0, 1 or 2 lines. Never `None`.

| Input | Output |
|-------|--------|
| `purchase=None, manufacturer=None, part_number=None` | `[]` |
| `purchase=None, manufacturer='MEAN WELL', part_number='IRM-05-5'` | `['MEAN WELL  IRM-05-5']` |
| `purchase=<Amazon, 2026-01-14, 6.50>, manufacturer=None, part_number=None` | `['Amazon  2026-01-14  $6.50 ea']` |
| both | `['MEAN WELL  IRM-05-5', 'Amazon  2026-01-14  $6.50 ea']` |

Rules:

- Fields within a line join with two spaces. An absent, empty or whitespace-only field contributes
  nothing and no separator.
- `unit_price` renders as `f"${price} ea"` where `price` is `str(Decimal)`. Never a `float`.
  `Decimal('0')` is a price and prints; `None` does not.
- `order_date` renders `%Y-%m-%d`.
- A line that would be empty is not emitted, so the list never contains `''`.

**Breaking change**: the return type. There is one production call site and one test class; both
are updated in this feature.

## `compose_product_label`

The `provenance: Optional[str] = None` parameter becomes
`provenance_lines: Optional[Sequence[str]] = None`.

Renamed rather than widened, deliberately: `str` satisfies `Sequence[str]`, so a widened parameter
would accept a string and silently draw one line per character. The rename makes every stale call
site a `TypeError` at import-test time instead of a wrong label at print time.

Everything else about the function is unchanged: same arguments, same PNG `BytesIO` return, same
dimensions per stock, same flag-mode duplication.

Behaviour:

- `None` or `[]` → no provenance band. The composed image is byte-identical to today's
  no-provenance output.
- One line → byte-identical to today's single-string output.
- Two lines → the code band's height is unchanged from the one-line case; the description band
  yields the difference.

## `print_product_label`

Same rename: `provenance` → `provenance_lines`. `num_copies: int = 1` is unchanged and already
does the right thing — it was simply never passed a value other than 1.

The TESTING / DISABLE_LABEL_PRINTING short-circuit is unchanged and continues to log what it would
have printed. **No test reaches `LpPrinter.print_images()`.** The log line now reports the
provenance lines as a list.
