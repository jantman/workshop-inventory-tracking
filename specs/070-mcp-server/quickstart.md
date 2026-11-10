# Quickstart / Validation: MCP Server (070)

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests      # protocol + every tool, SQLite
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e        # includes tests/e2e/test_mcp_server.py (run detached, ~20 min)
```

Expected: all pass; `git status` clean afterwards.

## Manual protocol check against a running instance

1. Start the app locally (dev server, MariaDB or the e2e-style SQLite config), with
   `DISABLE_LABEL_PRINTING=true` unless a printer is attached.
2. Raw handshake:

   ```bash
   curl -s -X POST http://localhost:5000/mcp -H 'Content-Type: application/json' \
     -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
   ```

   Expect `result.protocolVersion == "2025-06-18"` and `capabilities.tools`.
3. Official SDK client (scratch venv, not a project dependency): connect with
   `mcp.client.streamable_http.streamablehttp_client("http://localhost:5000/mcp")`,
   `initialize()`, `list_tools()` — expect every tool in the contract — and
   `call_tool("search_items", {})`.
4. Claude Code: `claude mcp add --transport http workshop-inventory http://localhost:5000/mcp`,
   then `/mcp` shows the server connected with its tools; ask "what items are in location X".

## Expected outcomes per story

- US1: search/get tools return what the Inventory and Products pages show.
- US2: add → new JA IDs visible in the list; shorten → item history shows the retired row;
  move → new location on the item page.
- US3: count/flag/category changes visible on the product page with fresh ages.
- US4: with printing disabled, the app log shows the label that would have printed.
