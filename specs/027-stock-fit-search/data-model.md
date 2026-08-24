# Phase 1 Data Model: Stock Fit Search

**Feature**: [spec.md](./spec.md) | **Contracts**: [fit-rules.md](./contracts/fit-rules.md), [find-stock-api.md](./contracts/find-stock-api.md)

**Nothing here is persisted.** No table, no column, no Alembic revision (D12). Every type
below lives for the duration of one HTTP request. The database side of this feature is one
`SELECT` the service already knows how to build.

---

## 1. Types

All measurements are `decimal.Decimal`. Constitution Principle III forbids `float` anywhere
in this feature, including in comparison.

### `RequestedPiece` — `app/utils/fit.py`

What the operator needs. Frozen dataclass; not stored.

| Field | Type | Rule |
|---|---|---|
| `shape` | `ItemShape` | `RECTANGULAR` or `ROUND` only. Any other value is rejected before construction (FR-002). |
| `dimensions` | `dict[str, Decimal]` | Rectangular: `length`, `width`, `thickness`. Round: `diameter`, `length`. Exactly the keys the shape requires; no more, no fewer (FR-004). |
| `tolerances` | `dict[str, Decimal]` | Subset of the same keys. A key absent means that dimension is exact (FR-015). |

**Validation** (all raise before any search runs):

| Rule | Requirement |
|---|---|
| every required dimension present | FR-004 |
| every dimension `> 0` | FR-005 |
| every tolerance `>= 0` | FR-017 |
| every tolerance `<` the dimension it applies to | FR-017 |

**Derived**: `effective(name)` returns `dimensions[name] - tolerances.get(name, 0)`.

### `Envelope` — `app/utils/fit.py`

The solid an inventory row describes, derived at read time by
[fit-rules.md §1](./contracts/fit-rules.md). Frozen dataclass, one of two kinds.

| Field | Type | Notes |
|---|---|---|
| `kind` | `BOX` \| `CYLINDER` | Two kinds is the whole model (D2). |
| `a`, `b`, `c` | `Decimal` | `BOX` only — no ordering implied by the field names; the rules sort. |
| `diameter`, `height` | `Decimal` | `CYLINDER` only. |

Derivation returns `None` with a reason instead of an envelope in two cases:

| Reason | Condition | Counted as |
|---|---|---|
| `HOLLOW` | `wall_thickness` recorded (rule E1) | `skipped_hollow` |
| `INCOMPLETE` | a field the matching rule needs is `NULL` (rule E6) | `skipped_incomplete` |

### `Fit` — `app/utils/fit.py`

The outcome for one candidate. Only produced when the piece fits.

| Field | Type | Source |
|---|---|---|
| `within_tolerance` | `bool` | fit-rules §5 |
| `tolerance_dimensions` | `list[str]` | fit-rules §5.3, labelled through `taxonomy.field_label` |
| `orientation` | `str` | which rule and orientation fitted |
| `item_cross_section` | `tuple[Decimal, ...]` | winning orientation, exact |
| `requested_cross_section` | `tuple[Decimal, ...]` | winning orientation, exact |
| `removed_area` | `Decimal` | sort key term 2 only — never displayed (fit-rules §6) |
| `axial_extent` | `Decimal` | sort key term 3 |

### `FindStockResult` — `app/mariadb_inventory_service.py`

What the service hands the route.

| Field | Type |
|---|---|
| `items` | `list[tuple[InventoryItem, Fit]]`, ordered by fit-rules §4 |
| `considered` | `int` |
| `skipped_incomplete` | `int` |
| `skipped_hollow` | `int` |

---

## 2. Where each measurement comes from

The fit test reads four existing columns and never writes any of them. All are
`Numeric(10, 4), nullable=True` (`app/database.py:37-40`) with positive-value check
constraints that permit `NULL` (`:85-89`).

| Column | Read as | By envelope rule |
|---|---|---|
| `length` | axial extent of a bar; one box dimension | E3, E4, E5 |
| `width` | diameter of a round; across-flats of a hex; one box dimension | E2, E3, E4, E5 |
| `thickness` | height of a disc; one box dimension | E2, E5 |
| `wall_thickness` | presence only — never a magnitude | E1 |

`weight`, `precision`, thread fields and everything else are passed through to the results
untouched.

---

## 3. State transitions

None. Nothing in this feature mutates an item, so Constitution Principle VI's lifecycle and
history invariants are not engaged: no row is added, deactivated, shortened or re-parented.
The single query filters to `active == True` (D15), which is Principle VI's rule that
"queries that present current inventory MUST filter to active rows".

---

## 4. Every path touched

| File | Change |
|---|---|
| `app/utils/fit.py` | **NEW** — envelope derivation, four fit rules, sort key. Pure; imports only `app/models.py` enums and `decimal`. |
| `app/mariadb_inventory_service.py` | **CHANGED** — `find_stock(request) -> FindStockResult`. One query: `active == True` and `material.in_(descendants)`. Reuses `get_material_descendants()` (`:705`). `search_active_items` is not touched (FR-026). |
| `app/main/routes.py` | **CHANGED** — `GET /inventory/find-stock` renders the page; `POST /api/inventory/find-stock` parses, validates, calls the service, jsonifies. No ORM, no SQL (Principle II). |
| `app/templates/inventory/find-stock.html` | **NEW** — the form, and the shared table macro with `show_fit_column=True`. |
| `app/templates/inventory/_item_table.html` | **CHANGED** — one optional `show_fit_column` header. Default off; `list.html` and `search.html` unchanged. |
| `app/templates/base.html` | **CHANGED** — one nav entry under Inventory, beside "Search Items" (`:53`). |
| `app/static/js/inventory-find-stock.js` | **NEW** — form submit, `fetch`, `InventoryTable.setItems()`, the counters line. Imports the same `InventoryTable` as `inventory-search.js:12`. |
| `app/static/js/components/inventory-table.js` | **CHANGED** — `showFitColumn` config, one `<td>` in `createRow()`, one `case 'fit'` in `getSortValue()`. |
| `tests/unit/test_fit.py` | **NEW** — the tables in fit-rules §1 and §3, enumerated; the taxonomy-agreement test (D3). |
| `tests/unit/test_mariadb_inventory_service.py` | **CHANGED** — ordering, counters, hierarchical material, active-only. |
| `tests/unit/test_routes.py` | **CHANGED** — the six 400 cases and the success payload. |
| `tests/e2e/test_find_stock.py` | **NEW** — the acceptance scenarios worth driving through a browser. |
| `tests/e2e/pages/find_stock_page.py` | **NEW** — page object, reusing `InventoryTableMixin`. |
| `tests/e2e/screenshot_config.yaml` | **CHANGED** — a `find_stock_form` entry beside `search_form` (`:166`). |
| `docs/user-manual.md` | **CHANGED** — a section for the new search. |
| `docs/images/screenshots/` | **CHANGED** — regenerated (D14). |

No migration. No change to `app/models.py`, `app/taxonomy.py`, `app/database.py`,
`app/storage.py` or `app/mariadb_storage.py`.
