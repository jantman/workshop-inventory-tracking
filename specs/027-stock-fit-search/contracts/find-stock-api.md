# Contract: Find Stock Routes

**Feature**: [../spec.md](../spec.md) | **Decisions**: [../research.md](../research.md) D9, D11, D15

Two routes, named after the pair the advanced search already uses — `/inventory/search` and
`/api/inventory/search` (`app/main/routes.py:979`, `:2021`).

---

## `GET /inventory/find-stock`

Renders `app/templates/inventory/find-stock.html`. No parameters. The page carries the form
and an empty results region; nothing is searched until the operator submits.

---

## `POST /api/inventory/find-stock`

CSRF-exempt, consistent with `api_advanced_search` (`app/main/routes.py:2022`). Accepts and
returns JSON.

### Request

Every dimension is a string carrying an exact decimal, as the existing search's range values
are. Tolerance keys are flat and suffixed, matching the existing `length_min` / `length_max`
convention.

**Rectangular request**

```json
{
  "material": "Steel",
  "shape": "Rectangular",
  "length": "4.0",
  "width": "3.0",
  "thickness": "0.5",
  "length_tolerance": "0.02",
  "width_tolerance": null,
  "thickness_tolerance": null
}
```

**Round request**

```json
{
  "material": "Steel",
  "shape": "Round",
  "diameter": "2.0",
  "length": "2.0",
  "diameter_tolerance": null,
  "length_tolerance": "0.02"
}
```

| Field | Required | Notes |
|---|---|---|
| `material` | yes | Matched hierarchically via `InventoryService.get_material_descendants()`, exactly as the advanced search does (`app/main/routes.py:2092-2095`). |
| `shape` | yes | `"Rectangular"` or `"Round"`. Any other value is a 400. |
| `length`, `width`, `thickness` | rectangular only, all three | |
| `diameter`, `length` | round only, both | |
| `*_tolerance` | no | Absent or `null` means the dimension is exact (FR-015). |

There is no `active` parameter — see D15.

### Success response — 200

```json
{
  "success": true,
  "items": [ /* … */ ],
  "total_count": 3,
  "considered": 41,
  "skipped_incomplete": 2,
  "skipped_hollow": 5,
  "search_criteria": { /* the request, echoed */ }
}
```

`items` are ordered by the sort key in [fit-rules.md §4](./fit-rules.md). Each entry carries
**every field `/api/inventory/search` already returns** — `ja_id`, `display_name`,
`item_type`, `shape`, `material`, `dimensions`, `thread`, `location`, `sub_location`,
`purchase_date`, `purchase_price`, `purchase_location`, `vendor`, `vendor_part_number`,
`notes`, `precision`, `active`, `date_added`, `last_modified`, `photo_count`
(`app/main/routes.py:2141-2166`) — so the shared table renders it unchanged, plus one added
key:

```json
"fit": {
  "within_tolerance": false,
  "tolerance_dimensions": [],
  "orientation": "upright",
  "item_cross_section": "3.0000 × 3.0000",
  "requested_cross_section": "2.0000 × 2.0000",
  "excess": ["1.0000", "1.0000"]
}
```

| Key | Meaning |
|---|---|
| `within_tolerance` | `true` when the item fits only after tolerance is applied (FR-018). |
| `tolerance_dimensions` | The load-bearing dimensions from [fit-rules.md §5](./fit-rules.md), named as the operator sees them (`Length`, `Diameter`, …). Empty unless `within_tolerance`. |
| `orientation` | Which rule and orientation fitted, for the operator to picture the cut. |
| `item_cross_section`, `requested_cross_section`, `excess` | Exact decimal strings. No area, no `PI` (fit-rules §6). |

The three counters answer SC-006:

| Counter | Counts |
|---|---|
| `considered` | Active rows whose material is in the requested hierarchy — everything the search looked at. |
| `skipped_incomplete` | Of those, rows lacking a dimension the fit test needs (envelope rule E6). |
| `skipped_hollow` | Of those, rows carrying a `wall_thickness` (envelope rule E1). |

### Error responses — 400

The shape matches the existing endpoint's errors (`app/main/routes.py:2050-2057`):

```json
{ "success": false, "message": "…", "items": [], "total_count": 0 }
```

| Condition | Message names |
|---|---|
| `material` absent or empty | the missing material (FR-004) |
| `shape` absent or not one of the two | the offending value |
| a dimension the shape needs is absent | that dimension (FR-004) |
| a dimension is zero, negative or unparseable | that dimension (FR-005) |
| a tolerance is negative | that dimension (FR-017) |
| a tolerance is ≥ the dimension it applies to | that dimension (FR-017) |

A 500 returns the same shape with a generic message and the traceback logged, as
`api_advanced_search` does (`:2177`).

---

## Shared results table

`app/templates/inventory/_item_table.html` gains one optional key and
`app/static/js/components/inventory-table.js` the matching one (D10):

| Macro `config` key | JS `config` key | Default | Effect |
|---|---|---|---|
| `show_fit_column` | `showFitColumn` | absent / `false` | Adds one `Fit` header and one `<td>` per row, rendered from `item.fit`. Sortable via a `case 'fit'` in `getSortValue()` returning the sort key's second term. |

`list.html` and `search.html` pass neither and MUST render byte-identically (FR-028). The
server's ordering survives first render without new code because `setItems()` calls
`render()` and never `sortBy()` (`inventory-table.js:83-88`) — FR-029 needs a test, not an
implementation.
