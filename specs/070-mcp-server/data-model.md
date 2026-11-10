# Data Model: MCP Server (070)

No schema change. No migration. The feature adds no table, column or stored state; every
tool reads or writes the existing `inventory_items` and catalog tables through the existing
services. The entities below are the **shapes tools return**, built from the existing
domain objects.

## Tool (in-code registry entry)

| Field | Meaning |
|---|---|
| `name` | snake_case tool name (contract) |
| `title` | human label |
| `description` | when an assistant should use it; mentions units and identifiers |
| `input_schema` | JSON Schema object (`type: object`, `properties`, `required`, `additionalProperties: false`) |
| `read_only` | drives `annotations.readOnlyHint` |
| `handler` | `Callable[[dict], dict]` returning the structured result, raising `ToolError` for a business failure |

## ItemSummary

`ja_id`, `display_name`, `item_type`, `shape`, `material`, `dimensions` (`length`, `width`,
`thickness`, `wall_thickness`, `weight` — decimal strings or null), `thread`
(`series`, `handedness`, `size` or null), `location`, `sub_location`, `active`, `precision`.

## ItemDetail

ItemSummary plus `notes`, `purchase_date`, `purchase_price`, `purchase_location`, `vendor`,
`vendor_part_number`, `date_added`, `last_modified`.

## HistoryRow

`active`, `dimensions`, `location`, `sub_location`, `notes`, `date_added`, `last_modified`,
oldest first. Invariant surfaced, not enforced here: exactly one row has `active: true`
for an item in current inventory (constitution VI).

## ProductSummary

`product_id`, `code` (internal code), `description`, `category_path`, `location`,
`sub_location`, `quantity` (int or null), `quantity_tracked` (bool),
`quantity_counted_at` (ISO UTC or null), `stock_status` (`low`/`out`/null),
`stock_status_set_at`.

## ProductDetail

ProductSummary plus `manufacturer`, `manufacturer_part_number`, `reorder_threshold`,
`notes`, `tags`, `specifications` ([{name, value}]), `identifiers` ([{type, value, vendor}]),
`latest_purchase` (vendor, date, unit price, or null). Built from `Product.to_dict(...)`
where it already carries the field.

## Validation rules (all delegated)

| Rule | Owner |
|---|---|
| Required fields, type/shape dimension requirements, material in taxonomy, quantity range on add | `_process_item_creation` / `_edit_item_from_form` (main routes) |
| Shortened length < current length, > 0 | `InventoryService.shorten_item` / `_execute_shortening_operation` |
| Move: location required, sub-location replaced/cleared | `_move_items`, `destination()` |
| Category path normalization, depth, blank refused | `CatalogService.set_category` / `_validate_category_path` |
| Quantity non-negative integer or null | `CatalogService.set_quantity` |
| Stock flag value | `CatalogService.set_stock_status` |
| Label type known, count 1–99 | `_print_item_label` / product label helper |
| Tool argument types, required, unknown keys | MCP registry (JSON-Schema subset check) |
