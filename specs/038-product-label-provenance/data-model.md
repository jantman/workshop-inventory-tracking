# Phase 1 Data Model: Product label provenance

No database entity changes. No Alembic revision. This document describes the *content model of a
composed label* — what goes on it, in what order, and how much of the label each part is allowed
to occupy.

## Source records (existing, unchanged)

### `Product` (`app/database.py`)

| Field | Type | Optional | Use here |
|-------|------|----------|----------|
| `description` | `String` | no | The description band — unchanged |
| `internal_code` | `String` | no | The Code128 symbol and its human-readable text — unchanged |
| `manufacturer` | `String(200)` | **yes** | **New on the label**: first field of the identity line |
| `manufacturer_part_number` | `String(100)` | **yes** | **New on the label**: second field of the identity line |

Both new fields are `nullable=True` and are independently absent. They may also be present as an
empty or whitespace-only string, which is treated as absent.

### `Purchase` (most recent, via `ProductCatalogService.get_latest_purchase`)

| Field | Optional | Use here |
|-------|----------|----------|
| `vendor` | no in practice | First field of the purchase line — unchanged |
| `order_date` | yes | Second field, `%Y-%m-%d` — unchanged |
| `unit_price` | yes | Third field, **now suffixed `ea`** |

`unit_price` is a `Decimal`. It is rendered with `str()` and never participates in arithmetic.

A product may have no purchase at all, in which case the purchase line is absent — but, unlike
today, that no longer implies the whole provenance band is absent.

## The provenance lines

Provenance is a list of 0, 1 or 2 strings. Fields within a line are joined by two spaces, which is
the existing separator; a field that is absent, empty, or whitespace-only contributes nothing and
takes its separator with it (FR-003).

| Line | Order of fields | Present when |
|------|-----------------|--------------|
| 1 — identity | `manufacturer`, `manufacturer_part_number` | either field is non-empty |
| 2 — purchase | `vendor`, `order_date`, `unit_price` + ` ea` | a purchase exists |

### The eight combinations (SC-003)

| manufacturer | part number | purchase | Lines drawn | Example |
|---|---|---|---|---|
| — | — | — | 0 | *(no provenance band; byte-identical to today — SC-006)* |
| — | — | ✓ | 1 | `Amazon  2026-01-14  $6.50 ea` |
| ✓ | — | — | 1 | `MEAN WELL` |
| — | ✓ | — | 1 | `IRM-05-5` |
| ✓ | ✓ | — | 1 | `MEAN WELL  IRM-05-5` |
| ✓ | — | ✓ | 2 | `MEAN WELL` / `Amazon  2026-01-14  $6.50 ea` |
| — | ✓ | ✓ | 2 | `IRM-05-5` / `Amazon  2026-01-14  $6.50 ea` |
| ✓ | ✓ | ✓ | 2 | `MEAN WELL  IRM-05-5` / `Amazon  2026-01-14  $6.50 ea` |

No row produces a blank field, a doubled separator, or a trailing separator.

## The label's vertical budget

A panel is divided top to bottom into description, provenance, and code. The code band's share is
the thing being protected (FR-006).

Let `H` be the panel height and `N` the number of provenance lines.

```
provenance_height  = int(H * PROVENANCE_BAND) * N                        # 0 when N == 0
description_height = int(H * (DESCRIPTION_BAND + PROVENANCE_BAND)) - provenance_height  if N > 0
                     int(H * DESCRIPTION_BAND)                                          if N == 0
code_height        = H - description_height - provenance_height
```

with the existing constants `DESCRIPTION_BAND = 0.38` and `PROVENANCE_BAND = 0.14`.

| N | description | provenance | code | vs. today |
|---|---|---|---|---|
| 0 | 0.38 H | 0 | 0.62 H | identical |
| 1 | 0.38 H | 0.14 H | 0.48 H | identical |
| 2 | 0.24 H | 0.28 H | 0.48 H | code unchanged; description yields |

The invariant to test: **`code_height` for N=2 is not less than `code_height` for N=1**, on every
entry in `LABEL_TYPES` (SC-004).

### Type sizing within the provenance band

All provenance lines are drawn at **one** font size, fitted to the widest line. Two lines at
different sizes read as a mistake, and fitting to the widest is what guarantees every line fits.
With N=1 the widest line is the only line, so the fitted size is exactly what is fitted today —
this is the second half of why the one-line case is unchanged.

Each line is drawn into its own `int(H * PROVENANCE_BAND)` slice, and each is truncated with the
existing ellipsis marker if it still exceeds the usable width at the minimum size (FR-007).

## Print request

| Field | Type | Optional | Default | Range |
|-------|------|----------|---------|-------|
| `label_type` | string | no | — | a key of `LABEL_TYPES` |
| `label_count` | integer | **yes** | `1` | 1–99 inclusive, whole numbers only; `bool` rejected |

`label_count` maps onto `print_product_label`'s existing `num_copies` parameter, which already
multiplies the composed image before handing it to the printer. Nothing downstream changes.
