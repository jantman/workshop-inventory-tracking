# Contract: MCP endpoint and tools (070)

## Endpoint

`POST /mcp` — MCP Streamable HTTP, stateless, JSON responses (research R1–R3).

| Request | Response |
|---|---|
| JSON-RPC request (`id` present), supported method | `200`, `Content-Type: application/json`, one JSON-RPC response |
| JSON-RPC notification (no `id`) | `202`, empty body |
| Body not JSON | `200`, JSON-RPC error `-32700` (id `null`) |
| JSON array (batch) or not a JSON-RPC object | JSON-RPC error `-32600` |
| Unknown method | JSON-RPC error `-32601` |
| `MCP-Protocol-Version` header present and unsupported | `400`, JSON-RPC error `-32600` naming supported versions |
| `GET /mcp`, `DELETE /mcp` | `405` |

### `initialize`

Result:

```json
{
  "protocolVersion": "<client's if supported, else 2025-11-25>",
  "capabilities": {"tools": {"listChanged": false}},
  "serverInfo": {"name": "workshop-inventory-tracking", "version": "<app __version__>"},
  "instructions": "<short text: what items vs products are, JA ID and product code formats, that measurements are inches as exact decimal strings>"
}
```

Supported versions: `2025-11-25`, `2025-06-18`, `2025-03-26`.

### `ping` → `{}`

### `tools/list` → `{"tools": [ {name, title, description, inputSchema, annotations} ]}`

No pagination (`nextCursor` omitted). `annotations.readOnlyHint` is `true` for read tools
and `false` for the rest; write tools also carry `destructiveHint: false` except
`shorten_item` (`true`: it retires the current row into history) and `idempotentHint` where
true (moves, set-category, set-count, set-flag).

### `tools/call` `{name, arguments}`

- Unknown `name` → JSON-RPC error `-32602`.
- Otherwise result `{content: [{type: "text", text}], structuredContent, isError}`.
  `text` is `structuredContent` as indented JSON. On failure `isError: true` and
  `structuredContent = {"error": "<message>"}` (plus `"details"` when the underlying
  operation reports per-field or per-item errors).
- Argument checking: required arguments missing, unknown arguments, or wrong JSON types
  → `isError: true`, error names the argument. Nothing is written.

## Conventions

- **Measurements** are inches (weight: pounds). Inputs accept a JSON string (`"1/2"`,
  `"1 1/4"`, `"0.375"`) or number; they pass through the same parser as the web form.
  Outputs are decimal strings.
- **Items** are addressed by `ja_id` (`JA` + 6 digits; case-insensitive input).
- **Products** are addressed by `code` (internal code) or `product_id` (integer); exactly
  one is required.
- **Paging**: `limit` (default 50, max 200), `offset` (default 0); results carry
  `total`, `returned`, `offset`, `has_more`.

## Tools

### Inventory items

| Tool | RO | Arguments (required **bold**) | Result |
|---|---|---|---|
| `search_items` | ✓ | `material` (hierarchical), `item_type`, `shape`, `location` (text), `notes` (text), `ja_id`, `length_min/max`, `width_min/max`, `thickness_min/max`, `wall_thickness_min/max`, `thread_size`, `thread_series`, `precision` (bool), `include_inactive` (bool, default false), `limit`, `offset` | `{total, returned, offset, has_more, items: [ItemSummary]}` |
| `get_item` | ✓ | **`ja_id`** | `{item: ItemDetail, history: [HistoryRow]}`; not found → error |
| `find_stock` | ✓ | **`material`**, **`shape`** (`Rectangular`/`Round`), part dimensions and `<dim>_tolerance` as the Find Stock page takes them | the page's fit list: `{fits: [ {item: ItemSummary, …fit fields} ]}` |
| `add_items` | | **`item_type`**, **`shape`**, **`material`**, **`location`**, dimensions, thread fields, `sub_location`, purchase fields, `vendor`, `vendor_part_number`, `notes`, `precision`, `quantity` (default 1) — the `POST /api/inventory/items` field set | `{created_ja_ids: [...]}`; validation failure → error with `details` (per-index errors) |
| `edit_item` | | **`ja_id`** + any of the add fields + `active` | `{item: ItemDetail, changed_fields: [...]}` |
| `shorten_item` | | **`ja_id`**, **`new_length`**, `cut_date` (YYYY-MM-DD), `notes` | `{ja_id, original_length, new_length}` |
| `move_items` | | **`ja_ids`** (array, ≥1), **`location`**, `sub_location` | `{moved, total, failed: [{ja_id, error}]}`; `isError` only when none moved |
| `print_item_labels` | | **`ja_ids`** (array), **`label_type`**, `label_count` (1–99, default 1) | `{printed: [ja_id], failed: [{ja_id, error}]}` |

### Products

| Tool | RO | Arguments | Result |
|---|---|---|---|
| `search_products` | ✓ | `query` (text and identifiers), `category` (subtree), `tag`, `stock` (as the Products page filter), `spec_name`, `spec_value`, `missing` (`category`/`location`/`either`), `limit`, `offset` | `{total, returned, offset, has_more, products: [ProductSummary]}` |
| `get_product` | ✓ | `code` \| `product_id` | `{product: ProductDetail}` |
| `get_reorder_list` | ✓ | — | `{products: [ {product: ProductSummary, reason, on_order} ]}` |
| `add_product` | | **`description`**, `manufacturer`, `manufacturer_part_number`, `category_path`, `location`, `sub_location`, `quantity`, `reorder_threshold`, `notes`, `specifications` ([{name, value}]), `tags` ([str]), `identifiers` ([{type, value, vendor?}]) | `{product: ProductDetail}` |
| `edit_product` | | `code` \| `product_id` + any `update_product` field | `{product: ProductDetail}` |
| `set_product_category` | | **`products`** (array of codes or ids), **`category_path`** | `{category_path, products: [ProductSummary]}` (all-or-nothing, as the web) |
| `set_product_count` | | `code` \| `product_id`, **`quantity`** (int ≥ 0, or `null` = stop tracking) | `{product: ProductDetail}` |
| `adjust_product_count` | | `code` \| `product_id`, **`delta`** (non-zero int) | `{product: ProductDetail, previous_quantity}`; untracked or result < 0 → error |
| `set_product_stock_flag` | | `code` \| `product_id`, **`flag`** (`low`/`out`/`null`) | `{product: ProductDetail}` |
| `move_products` | | **`products`** (array of codes), **`location`**, `sub_location` | `{moved, total, failed: [{code, error}]}` |
| `print_product_labels` | | **`products`** (array of codes or ids), **`label_type`**, `label_count` | `{printed: [code], failed: [{code, error}]}` |

### Reference lookups (all read-only)

| Tool | Arguments | Result |
|---|---|---|
| `list_label_types` | — | `{label_types: [...]}` |
| `list_materials` | — | `{materials: [...]}` (active materials the Add form accepts) |
| `list_item_types_and_shapes` | — | `{item_types: [...], shapes: [...], requirements: {...}}` (required dimensions per type/shape) |
| `list_locations` | `location` (when given: sub-locations used within it), `query`, `limit` | `{field, values: [...]}` |
| `list_product_categories` | `prefix` | `{categories: [...]}` |

## Entity shapes

See [data-model.md](../data-model.md).
