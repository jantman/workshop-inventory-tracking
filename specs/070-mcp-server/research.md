# Research: MCP Server (070)

## R1 — Transport: Streamable HTTP served by the Flask app

**Decision**: Serve MCP's *Streamable HTTP* transport at `POST /mcp` from a new `mcp`
blueprint in the existing Flask app. Stateless: every POST carries one JSON-RPC message and,
for a request, gets one `application/json` response. No `Mcp-Session-Id`, no SSE stream.
`GET /mcp` and `DELETE /mcp` answer `405 Method Not Allowed`. A notification (no `id`) is
acknowledged with `202 Accepted` and no body.

**Rationale**: The issue asks for "this application" to serve the endpoint. The transport
spec lets a server answer a POSTed request with plain `application/json` instead of an SSE
stream, and lets it answer `GET` with 405 when it offers no server-initiated stream. Every
tool here is a quick synchronous database call, so nothing needs streaming, progress or
server-to-client requests. That reduces the protocol to four JSON-RPC methods on a sync WSGI
route, which runs unchanged under gunicorn, the Flask dev server and the e2e live server.

**Alternatives considered**:

- *Official `mcp` Python SDK (FastMCP).* It is ASGI (Starlette, uvicorn, anyio, pydantic,
  httpx, sse-starlette). Mounting it beside a WSGI Flask app means a second server process
  or an ASGI/WSGI bridge, a new deployment shape, and half a dozen new dependencies to serve
  four methods. Principle I ("dependencies must earn their place") rejects that.
- *A separate stdio program.* Claude Code could launch it locally, but it would need its
  own database configuration on the workstation and would not be "the application serving
  an endpoint". Claude Desktop is covered by a stdio↔HTTP bridge instead (R6).

## R2 — Protocol revisions

**Decision**: Support `2025-11-25`, `2025-06-18` and `2025-03-26`. On `initialize`, if the
client's `protocolVersion` is one of these, echo it; otherwise answer with `2025-11-25`
(the spec's negotiation rule: the server replies with a version it supports and the client
decides whether to continue). Requests after initialization may carry an
`MCP-Protocol-Version` header; an unsupported value gets `400`. A missing header is
accepted (the spec says to assume `2025-03-26`).

Methods: `initialize`, `notifications/initialized` (and any other notification: 202),
`ping`, `tools/list`, `tools/call`. Anything else: JSON-RPC `-32601 Method not found`.
A JSON array body (JSON-RPC batching, dropped from the protocol in 2025-06-18) gets
`-32600 Invalid Request`. Unparseable JSON: `-32700`.

**Rationale**: These three revisions are the ones current Claude Code and `mcp-remote`
negotiate. They do not differ in anything this server uses except `structuredContent`
(added 2025-06-18), which older clients ignore as an unknown field.

## R3 — Tool results

**Decision**: `tools/call` returns `{content: [{type: "text", text: <JSON text>}],
structuredContent: <object>, isError: bool}`. The text block is the same object serialized
as indented JSON, so a client that only reads text gets everything. Business failures
(validation, not found, printer error, bad arguments) return `isError: true` with an
`error` message — not a JSON-RPC error — so the assistant sees and can correct them
(spec FR-005). JSON-RPC errors are reserved for protocol problems: unknown tool name
(`-32602`), malformed request.

No `outputSchema` is declared; it would duplicate the contract for no client benefit.

## R4 — Reusing the web operations (parity, spec FR-006)

**Decision**: Tools call the exact code the web operations use.

| Tool area | Existing logic | How the tool reaches it |
|---|---|---|
| Item reads, search | `InventoryService.get_item`, `get_item_history`, `search_items(SearchFilter)`, `find_stock` | direct service calls; search filter built by the same parsing the `/api/inventory/search` route uses (extract `_build_search_filter(data)` from `api_advanced_search` if it is inline) |
| Add items | `_normalize_json_item_payload` + `_process_item_creation` (main/routes.py) | called as-is — this is precisely what `POST /api/inventory/items` does |
| Edit item | inline in `inventory_edit` POST | **extract** the validate-parse-update-audit body into `_edit_item_from_form(item, form_data) -> (success, error)`; the route and the tool both call it. Tool builds `form_data` from the current item (`_item_to_form_data`) overlaid with the supplied fields |
| Shorten | `handle_shorten_post` → `_execute_shortening_operation` | **extract** the validation+audit+execute part of `handle_shorten_post` into `_shorten_from_form(form_data) -> dict`; route keeps its flash/redirect wrapper |
| Move items | inline loop in `batch_move_items` | **extract** the loop into `_move_items(moves) -> dict` (returns `batch_result(...)`); route keeps parse + jsonify |
| Item labels | validation inline in `print_label` | **extract** `_print_item_label(data) -> dict` raising `ValueError` on bad input |
| Products | `CatalogService` methods (`search_products`, `get_product`, `find_product_by_identifier`, `create_product`, `update_product`, `set_category`, `set_quantity`, `set_stock_status`, `move_product`, `get_reorder_products`) | direct service calls; `ValidationError` / `ItemNotFoundError` map to tool errors |
| Product labels | composition inline in `api_print_product_label` | **extract** `_print_product_label(product, label_type, label_count) -> dict` in product routes |
| Lookups | `get_available_label_types()`, `InventoryService.get_valid_materials()`, `VocabularyService.suggest`, `CatalogService.list_categories`, `ItemType`/`ItemShape` enums | direct calls |

Extractions are mechanical moves of existing lines into named functions in the same
module; behavior of the web routes is unchanged and covered by their existing unit and
e2e tests. The MCP blueprint imports these helpers from `app.main.routes` /
`app.product.routes`. Moving them into a service module would be the tidier layering but a
much larger diff for no behavioral gain; not done here (Principle I).

**Adjust count** (`adjust_product_count`) has no server-side counterpart: the web **+**/**−**
buttons compute the new value in the browser and PATCH an absolute quantity. The tool does
the same — read quantity, refuse if untracked or if the result would go below zero, then
`set_quantity(new)` — so the count's age resets exactly as a button press does.

**Categorize**: `set_category` is called directly; the route's `flash()` is a page-side
effect and is not reproduced.

## R5 — Identifiers in tool inputs

Items by JA ID (`JA000123`, case-insensitive, upper-cased as the routes do). Products by
`code` (the internal code printed on the label) **or** `product_id` (the integer ID the web
URLs use); every product tool accepts either, one required. Results always carry both.

## R6 — Clients

- **Claude Code**: `claude mcp add --transport http workshop-inventory http://<host>:<port>/mcp`.
- **Claude Desktop**: custom remote connectors are brokered through Anthropic's cloud and
  cannot reach a LAN-only address, so Desktop uses the `mcp-remote` stdio bridge in
  `claude_desktop_config.json`: `npx mcp-remote http://<host>:<port>/mcp --allow-http`
  (`--allow-http` because the target is plain HTTP and not localhost).

## R7 — CSRF, authentication, Origin

The blueprint is `csrf.exempt` (non-browser JSON-RPC clients carry no token), like the
existing JSON API endpoints in `main`. No authentication, per the constitution's threat
model. The transport spec asks servers to validate `Origin` against DNS rebinding; that
attack needs a browser on the LAN visiting a hostile site, which is the same exposure the
existing CSRF-exempt `/api/inventory/*` endpoints already have. Not added (constitution:
no hardening against imagined attackers); recorded here so the omission is a decision.

## R8 — Paging and size

Search tools take `limit` (default 50, max 200) and `offset` (default 0), applied to the
service's result list, and return `total`, `returned`, `offset`, `has_more`. Product search
already caps at 500 in the service; the tool pages within that.

## R9 — Testing

- Unit (`tests/unit/test_mcp_*.py`, SQLite via the existing `client` fixture): protocol
  handshake/negotiation/errors; every tool's success path and its main refusal; parity
  checks that a tool and the corresponding route produce the same stored row.
  `TESTING` already short-circuits label printing, so print tools are tested via their
  return value and by patching the printer function to record calls.
- E2E (`tests/e2e/test_mcp_server.py`): against the live server, drive MCP over real HTTP
  (`requests`): initialize, add an item, shorten it, then open the item's history in the
  browser and assert the history rows (constitution VI: shorten paths covered by e2e for
  history behavior). Waits are `expect(...)` only.
- Protocol conformance check (manual, quickstart): connect the official `mcp` Python SDK
  client (scratch venv, not a project dependency) and Claude Code to a running instance.
