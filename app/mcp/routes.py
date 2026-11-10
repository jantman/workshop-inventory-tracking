"""``POST /mcp``: MCP Streamable HTTP, stateless, JSON responses (070).

contracts/mcp-endpoint.md is the specification this implements. Each POST
carries one JSON-RPC message; a request gets one ``application/json``
response, a notification a bare 202. There is no session and no SSE stream, so
``GET`` and ``DELETE`` answer 405 (Flask does that for a POST-only route).

Author: Jason Antman, 2026.
"""

import json
import traceback
from typing import Any

from flask import current_app, request
from werkzeug.wrappers import Response

from app import __version__
from app.mcp import bp
from app.mcp.tools import TOOLS, ToolError, check_arguments, get_tool

# Imported for their side effect: each module registers its tools, in the
# order tools/list presents them.
from app.mcp import item_tools, product_tools, lookup_tools  # noqa: E402,F401

SUPPORTED_PROTOCOL_VERSIONS = ('2025-11-25', '2025-06-18', '2025-03-26')
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

SERVER_NAME = 'workshop-inventory-tracking'

INSTRUCTIONS = (
    "Workshop inventory for one hobby shop. Two kinds of thing are tracked. "
    "Inventory items are pieces of metal stock (bar, plate, tube, threaded rod...), "
    "each addressed by a JA ID: 'JA' plus six digits, e.g. JA000123. "
    "Products are catalog entries for everything else (parts, supplies), each addressed "
    "by its internal code (WIT plus ten characters, printed on its label) or its numeric "
    "product_id. Measurements are inches (weight in pounds) and are exact decimals: "
    "results give them as decimal strings, and inputs accept strings such as \"1/2\", "
    "\"1 1/4\" or \"0.375\" (or numbers). Writes apply the same validation as the web "
    "pages; a refused write changes nothing and the tool result says why. Use the "
    "list_* tools to find valid materials, types, shapes, locations, categories and "
    "label types."
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def _json_response(body: Any, status: int = 200) -> Response:
    return current_app.response_class(
        json.dumps(body), status=status, mimetype='application/json'
    )


def _error(message_id: Any, code: int, message: str, status: int = 200) -> Response:
    return _json_response({
        'jsonrpc': '2.0',
        'id': message_id,
        'error': {'code': code, 'message': message},
    }, status)


def _result(message_id: Any, result: dict) -> Response:
    return _json_response({'jsonrpc': '2.0', 'id': message_id, 'result': result})


def _initialize(params: dict) -> dict:
    requested = params.get('protocolVersion')
    version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
    return {
        'protocolVersion': version,
        'capabilities': {'tools': {'listChanged': False}},
        'serverInfo': {'name': SERVER_NAME, 'version': __version__},
        'instructions': INSTRUCTIONS,
    }


def _tool_result(structured: dict, is_error: bool) -> dict:
    # Round-tripped through JSON so the structured content is exactly what the
    # text block says.
    text = json.dumps(structured, indent=2, default=str)
    return {
        'content': [{'type': 'text', 'text': text}],
        'structuredContent': json.loads(text),
        'isError': is_error,
    }


def _call_tool(name: str, arguments: Any) -> dict:
    """Run one tool; every failure becomes an ``isError`` result."""
    entry = get_tool(name)
    try:
        checked = check_arguments(entry.input_schema, arguments)
        return _tool_result(entry.handler(checked), False)
    except ToolError as e:
        failure: dict[str, Any] = {'error': e.message}
        if e.details is not None:
            failure['details'] = e.details
        return _tool_result(failure, True)
    except Exception as e:
        current_app.logger.error(
            f'MCP tool {name} failed: {e}\n{traceback.format_exc()}'
        )
        return _tool_result({'error': f'Unexpected error: {e}'}, True)


@bp.route('/mcp', methods=['POST'])
def mcp_endpoint() -> Response:
    """Handle one JSON-RPC message from an MCP client."""
    header_version = request.headers.get('MCP-Protocol-Version')
    if header_version is not None and header_version not in SUPPORTED_PROTOCOL_VERSIONS:
        return _error(None, INVALID_REQUEST,
                      f'Unsupported MCP-Protocol-Version {header_version!r}; supported: '
                      f'{", ".join(SUPPORTED_PROTOCOL_VERSIONS)}', status=400)

    try:
        message = json.loads(request.get_data(as_text=True))
    except ValueError:
        return _error(None, PARSE_ERROR, 'Parse error: body is not JSON')

    if isinstance(message, list):
        return _error(None, INVALID_REQUEST, 'Batch requests are not supported')
    if not isinstance(message, dict) or message.get('jsonrpc') != '2.0':
        return _error(message.get('id') if isinstance(message, dict) else None,
                      INVALID_REQUEST, 'Invalid Request: not a JSON-RPC 2.0 message')

    method = message.get('method')
    if method is None and 'id' in message and ('result' in message or 'error' in message):
        # A response to a server-to-client request. This server sends none,
        # but the transport says such a POST is acknowledged with 202.
        return Response(status=202)
    if not isinstance(method, str):
        return _error(message.get('id'), INVALID_REQUEST, 'Invalid Request: no method')

    if 'id' not in message:
        # A notification (notifications/initialized and the like): nothing to answer.
        return Response(status=202)

    message_id = message['id']
    params = message.get('params') or {}
    if not isinstance(params, dict):
        return _error(message_id, INVALID_PARAMS, 'params must be an object')

    if method == 'initialize':
        return _result(message_id, _initialize(params))
    if method == 'ping':
        return _result(message_id, {})
    if method == 'tools/list':
        return _result(message_id, {'tools': [entry.to_listing() for entry in TOOLS]})
    if method == 'tools/call':
        name = params.get('name')
        if not isinstance(name, str) or get_tool(name) is None:
            return _error(message_id, INVALID_PARAMS, f'Unknown tool: {name}')
        return _result(message_id, _call_tool(name, params.get('arguments')))

    return _error(message_id, METHOD_NOT_FOUND, f'Method not found: {method}')
