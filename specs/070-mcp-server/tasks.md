# Tasks: MCP Server (070)

**Input**: `specs/070-mcp-server/` — plan.md, spec.md, research.md, data-model.md, contracts/mcp-endpoint.md

**Tests**: required — constitution IV ("changes that alter behavior MUST land with tests") and VI (shorten path covered by e2e).

Run tests only via nox: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" <main checkout>/venv/bin/nox -s tests` (this worktree has no venv; use the main checkout's `venv/bin/nox`). The e2e session takes ~20 min — run it detached and poll.

## Phase 1: Setup

- [ ] T001 Create blueprint package `app/mcp/__init__.py` (blueprint `mcp`, imports `routes`) and register it in `app/create_app` in `app/__init__.py`, exempting it from CSRF (`csrf.exempt(mcp_bp)`)

## Phase 2: Foundational (protocol + registry; blocks all stories)

- [ ] T002 Implement the tool registry in `app/mcp/tools.py`: `Tool` dataclass (name, title, description, input_schema, read_only, destructive, idempotent, handler), `ToolError(message, details=None)`, `register()`/`TOOLS` list, and `check_arguments(schema, args)` enforcing required keys, `additionalProperties: false`, and JSON types (string/integer/number/boolean/array/object/null, `enum`, `minimum`/`maximum`, `oneOf`-free) — raising `ToolError` naming the argument. Shared helpers: `measurement(value) -> str` (JSON number → `str()`, never float math), `paginate(rows, limit, offset)` (default 50, max 200) returning `total/returned/offset/has_more`, and `item_summary(item)` / `item_detail(item)` / `history_row(item)` / `product_summary(product)` / `product_detail(product)` per data-model.md (decimal strings for dimensions; ISO timestamps)
- [ ] T003 Implement `POST /mcp` in `app/mcp/routes.py` per contracts/mcp-endpoint.md: JSON-RPC parse (-32700/-32600, batches refused), notifications → 202, `initialize` with version negotiation over `2025-11-25`/`2025-06-18`/`2025-03-26` and `instructions` text, `ping`, `tools/list` (with annotations), `tools/call` (unknown tool → -32602; `ToolError` and unexpected exceptions → `isError: true` result, unexpected ones logged with traceback), `MCP-Protocol-Version` header check (400), `GET`/`DELETE` → 405. Tool handler modules imported so they register
- [ ] T004 [P] Protocol unit tests in `tests/unit/test_mcp_protocol.py`: initialize (each supported version echoed; unknown → latest), notification 202, ping, tools/list contains all 24 contract tool names each with description + object schema + `readOnlyHint`, unknown method, unknown tool, bad JSON, batch array, bad header, GET 405, argument checking errors (missing / unknown / wrong type) return `isError`

## Phase 3: User Story 1 — look things up (P1) 🎯 MVP

- [ ] T005 [US1] Extract `_build_search_filter(data: dict) -> SearchFilter` (raises `ValueError` with the same messages) from `api_advanced_search` in `app/main/routes.py`; the route calls it and keeps its 400 responses unchanged
- [ ] T006 [US1] Item read tools in `app/mcp/item_tools.py`: `search_items` (maps tool args to the `_build_search_filter` dict; `include_inactive` → `active` key; pages the result), `get_item` (canonical item + `get_item_history`; not found → `ToolError`), `find_stock` (same parsing as `api_find_stock` — reuse `_parse_requested_piece` — and service `find_stock`)
- [ ] T007 [US1] Product read tools in `app/mcp/product_tools.py`: `_resolve_product(args)` (`code` via `find_product_by_identifier(code, IdentifierType.INTERNAL.value)` or `product_id` via `get_product`; exactly one required), `search_products` (service `search_products`, paged), `get_product`, `get_reorder_list` (`get_reorder_products`)
- [ ] T008 [P] [US1] Unit tests in `tests/unit/test_mcp_item_tools.py` (read part) and `tests/unit/test_mcp_product_tools.py` (read part): search filters incl. inactive rows excluded by default, paging/has_more, get_item with shortened history, not-found errors, product search by text/category, by code and id, reorder list

## Phase 4: User Story 2 — change items (P2)

- [ ] T009 [US2] Extract from `inventory_edit` POST in `app/main/routes.py` `_edit_item_from_form(item, form_data) -> tuple[bool, str | None, InventoryItem | None]` holding the validation (required fields, `_missing_dimensions_error`, material in taxonomy), `_parse_item_from_form`, `update_item`, read-back and audit logging; the route keeps flash/redirect/re-render behavior identical. Add `_item_to_form_data(item) -> dict[str, str]` producing the edit form's field set from an item (dimensions as exact strings, `active`/`precision` as `'on'`, thread fields, purchase date `YYYY-MM-DD`, `vendor_part_number` from `vendor_part`)
- [ ] T010 [US2] Extract `_shorten_from_form(form_data) -> dict` from `handle_shorten_post` in `app/main/routes.py` (required-field check, audit input/success/error, `_execute_shortening_operation`); `handle_shorten_post` keeps the confirm check, flashes and redirects
- [ ] T011 [US2] Extract the per-move loop of `batch_move_items` into `_move_items(moves: list[dict]) -> dict` (returns `batch_result(...)`, including audit logging) in `app/main/routes.py`; the route keeps parse/400/500 handling
- [ ] T012 [US2] Item write tools in `app/mcp/item_tools.py`: `add_items` (args → `_normalize_json_item_payload` (quantity → `quantity_to_create`) → `_process_item_creation`; non-success → `ToolError` with per-index `details`), `edit_item` (canonical item → `_item_to_form_data` overlaid with supplied args → `_edit_item_from_form`; returns `changed_fields`), `shorten_item` (builds form dict → `_shorten_from_form`; returns original/new length as strings), `move_items` (→ `_move_items`; `isError` only when nothing moved)
- [ ] T013 [P] [US2] Unit tests in `tests/unit/test_mcp_item_tools.py` (write part): add creates N items with returned IDs; invalid material / missing dimension writes nothing and returns the web message; parity — the same payload through `POST /api/inventory/items` and `add_items` yields equal stored fields; edit changes only supplied fields and keeps exact decimals (e.g. `"1 1/4"`); shorten keeps one active row + retained history and refuses a longer length; move multiple IDs with one unknown reports per-item and moves the rest; sub-location replaced/cleared

## Phase 5: User Story 3 — manage products (P2)

- [ ] T014 [US3] Product write tools in `app/mcp/product_tools.py`: `add_product` (`create_product`, incl. `sub_location`), `edit_product` (`update_product(**supplied)`), `set_product_category` (resolve each to id → `set_category`), `set_product_count` (`set_quantity`), `adjust_product_count` (refuse untracked / below zero; `set_quantity(current+delta)`), `set_product_stock_flag` (`set_stock_status`), `move_products` (per code `move_product`, collect failures). `ValidationError`/`ItemNotFoundError` → `ToolError(e.message)`
- [ ] T015 [P] [US3] Unit tests in `tests/unit/test_mcp_product_tools.py` (write part): add returns code; edit touches only supplied fields; set category on several (new category created; blank refused, nothing changed); count set / null / adjust ± with age stamped, untracked and negative refusals; flag set/clear with age; move products with an unknown code

## Phase 6: User Story 4 — print labels (P3)

- [ ] T016 [US4] Extract `_print_item_label(ja_id, label_type, label_count) -> dict` (validation raising `ValueError`) from `print_label` in `app/main/routes.py`, and `_print_product_label(product, label_type, label_count) -> dict` from `api_print_product_label` in `app/product/routes.py`; routes keep their responses
- [ ] T017 [US4] Tools `print_item_labels` (`app/mcp/item_tools.py`) and `print_product_labels` (`app/mcp/product_tools.py`), per-subject outcomes
- [ ] T018 [P] [US4] Unit tests: patch the printer functions to record calls; assert label type/count passed, bad type lists valid types, count outside 1–99 refused, unknown ID reported

## Phase 7: User Story 5 — reference lookups (P3)

- [ ] T019 [US5] `app/mcp/lookup_tools.py`: `list_label_types`, `list_materials` (`get_valid_materials`), `list_item_types_and_shapes` (`ItemType`, `ItemShape`, `type_shape_validator.requirements_by_name()`), `list_locations` (`VocabularyService.suggest('location' | 'sub_location', ...)`), `list_product_categories` (`list_categories(prefix)`)
- [ ] T020 [P] [US5] Unit tests for the lookup tools in `tests/unit/test_mcp_protocol.py` or a new `tests/unit/test_mcp_lookup_tools.py`

## Phase 8: Polish & cross-cutting

- [ ] T021 E2E `tests/e2e/test_mcp_server.py`: over real HTTP to the live server — initialize, `add_items` (or seed via `live_server.add_test_data`), `shorten_item`, `move_items`; then open the item's page/history in the browser and `expect()` the new length, location and retained history row. No fixed waits
- [ ] T022 [P] Docs: `docs/user-manual.md` new "## MCP Server" section (what it is, Claude Code `claude mcp add --transport http …`, Claude Desktop via `mcp-remote … --allow-http`, tool list by area, no-auth/LAN note, what is out of scope) + TOC entry; one line in `README.md`
- [ ] T023 Run `nox -s tests`; run `nox -s e2e` detached; confirm working tree clean; protocol check against a running dev instance with the official `mcp` SDK client in a scratch venv (quickstart.md)
- [ ] T024 Spelling check: `grep -ric "catalogue" README.md docs/ app/ tests/` returns nothing

## Dependencies

- T001 → T002 → T003 → all stories. T004 after T003.
- US1 (T005–T008) is the MVP. US2–US5 depend only on Phase 2 and are independent of each other; T012 depends on T009–T011; T017 on T016.
- T021 after T012. T023 last.

## Parallel opportunities

- Test tasks marked [P] run beside the next story's implementation.
- US3 (product tools) and US2 (item tools) touch different files except `app/main/routes.py`, which only US2/US4 edit.

## Implementation strategy

MVP = Phases 1–3 (connect + read). Then US2 and US3, then labels and lookups, then e2e/docs.
