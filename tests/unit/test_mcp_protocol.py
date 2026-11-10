"""Protocol tests for the MCP endpoint (070): contracts/mcp-endpoint.md.

Author: Jason Antman, 2026.
"""

import json

import pytest

from app import __version__
from tests.unit.mcp_helpers import call, rpc

CONTRACT_TOOLS = {
    'search_items', 'get_item', 'find_stock', 'add_items', 'edit_item', 'shorten_item',
    'move_items', 'print_item_labels',
    'search_products', 'get_product', 'get_reorder_list', 'add_product', 'edit_product',
    'set_product_category', 'set_product_count', 'adjust_product_count',
    'set_product_stock_flag', 'move_products', 'print_product_labels',
    'list_label_types', 'list_materials', 'list_item_types_and_shapes', 'list_locations',
    'list_product_categories',
}

READ_ONLY_TOOLS = {
    'search_items', 'get_item', 'find_stock', 'search_products', 'get_product',
    'get_reorder_list', 'list_label_types', 'list_materials', 'list_item_types_and_shapes',
    'list_locations', 'list_product_categories',
}


def _initialize(client, version):
    return rpc(client, 'initialize', {
        'protocolVersion': version,
        'capabilities': {},
        'clientInfo': {'name': 'pytest', 'version': '0'},
    })


@pytest.mark.unit
class TestInitialize:
    @pytest.mark.parametrize('version', ['2025-11-25', '2025-06-18', '2025-03-26'])
    def test_supported_version_is_echoed(self, client, version):
        response = _initialize(client, version)
        assert response.status_code == 200
        assert response.content_type == 'application/json'
        body = response.get_json()
        assert body['jsonrpc'] == '2.0'
        assert body['id'] == 1
        result = body['result']
        assert result['protocolVersion'] == version
        assert result['capabilities'] == {'tools': {'listChanged': False}}
        assert result['serverInfo'] == {'name': 'workshop-inventory-tracking',
                                        'version': __version__}
        assert 'JA ID' in result['instructions']

    def test_unknown_version_gets_latest(self, client):
        result = _initialize(client, '2024-01-01').get_json()['result']
        assert result['protocolVersion'] == '2025-11-25'

    def test_no_session_id_is_issued(self, client):
        assert 'Mcp-Session-Id' not in _initialize(client, '2025-06-18').headers


@pytest.mark.unit
class TestMessages:
    def test_notification_is_accepted_with_no_body(self, client):
        response = client.post('/mcp', json={'jsonrpc': '2.0',
                                             'method': 'notifications/initialized'})
        assert response.status_code == 202
        assert response.data == b''

    def test_ping(self, client):
        body = rpc(client, 'ping', message_id='abc').get_json()
        assert body == {'jsonrpc': '2.0', 'id': 'abc', 'result': {}}

    def test_unknown_method(self, client):
        body = rpc(client, 'resources/list').get_json()
        assert body['error']['code'] == -32601

    def test_body_not_json(self, client):
        response = client.post('/mcp', data='{not json', content_type='application/json')
        assert response.status_code == 200
        body = response.get_json()
        assert body['id'] is None
        assert body['error']['code'] == -32700

    def test_batch_is_refused(self, client):
        response = client.post('/mcp', json=[{'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}])
        assert response.get_json()['error']['code'] == -32600

    def test_not_a_jsonrpc_object(self, client):
        response = client.post('/mcp', json={'id': 1, 'method': 'ping'})
        assert response.get_json()['error']['code'] == -32600

    def test_unsupported_protocol_header(self, client):
        response = rpc(client, 'ping', headers={'MCP-Protocol-Version': '1999-01-01'})
        assert response.status_code == 400
        body = response.get_json()
        assert body['error']['code'] == -32600
        assert '2025-06-18' in body['error']['message']

    def test_supported_protocol_header(self, client):
        response = rpc(client, 'ping', headers={'MCP-Protocol-Version': '2025-06-18'})
        assert response.status_code == 200

    @pytest.mark.parametrize('method', ['get', 'delete'])
    def test_get_and_delete_are_not_allowed(self, client, method):
        assert getattr(client, method)('/mcp').status_code == 405

    def test_no_csrf_token_needed(self, app, client):
        # TestConfig may disable CSRF; the blueprint must be exempt regardless.
        app.config['WTF_CSRF_ENABLED'] = True
        assert rpc(client, 'ping').status_code == 200


@pytest.mark.unit
class TestToolsList:
    def test_lists_every_contract_tool(self, client):
        tools = rpc(client, 'tools/list').get_json()['result']['tools']
        names = [t['name'] for t in tools]
        assert len(names) == 24
        assert set(names) == CONTRACT_TOOLS

    def test_each_tool_is_described(self, client):
        for entry in rpc(client, 'tools/list').get_json()['result']['tools']:
            assert entry['description'], entry['name']
            assert entry['title'], entry['name']
            schema = entry['inputSchema']
            assert schema['type'] == 'object', entry['name']
            assert schema['additionalProperties'] is False, entry['name']
            assert entry['annotations']['readOnlyHint'] is (entry['name'] in READ_ONLY_TOOLS)

    def test_write_annotations(self, client):
        tools = {t['name']: t for t in rpc(client, 'tools/list').get_json()['result']['tools']}
        assert tools['shorten_item']['annotations']['destructiveHint'] is True
        assert tools['add_items']['annotations']['destructiveHint'] is False
        assert tools['move_items']['annotations']['idempotentHint'] is True
        assert 'destructiveHint' not in tools['get_item']['annotations']


@pytest.mark.unit
class TestToolsCall:
    def test_unknown_tool_is_a_protocol_error(self, client):
        body = rpc(client, 'tools/call', {'name': 'delete_everything'}).get_json()
        assert body['error']['code'] == -32602

    def test_result_text_matches_structured_content(self, client):
        result = call(client, 'list_label_types')
        assert result['isError'] is False
        assert result['content'][0]['type'] == 'text'
        assert json.loads(result['content'][0]['text']) == result['structuredContent']

    def test_missing_required_argument(self, client):
        result = call(client, 'get_item', {})
        assert result['isError'] is True
        assert 'ja_id' in result['structuredContent']['error']

    def test_unknown_argument(self, client):
        result = call(client, 'get_item', {'ja_id': 'JA000001', 'colour': 'red'})
        assert result['isError'] is True
        assert 'colour' in result['structuredContent']['error']

    def test_wrong_type(self, client):
        result = call(client, 'search_items', {'limit': 'ten'})
        assert result['isError'] is True
        assert 'limit' in result['structuredContent']['error']

    def test_boolean_is_not_an_integer(self, client):
        result = call(client, 'search_items', {'limit': True})
        assert result['isError'] is True

    def test_enum_is_enforced(self, client):
        result = call(client, 'search_items', {'shape': 'Oval'})
        assert result['isError'] is True
        assert 'shape' in result['structuredContent']['error']

    def test_maximum_is_enforced(self, client):
        result = call(client, 'search_items', {'limit': 201})
        assert result['isError'] is True
        assert 'limit' in result['structuredContent']['error']

    def test_nested_array_entries_are_checked(self, client):
        result = call(client, 'move_items', {'ja_ids': ['JA000001', 7], 'location': 'X'})
        assert result['isError'] is True
        assert 'ja_ids[1]' in result['structuredContent']['error']

    def test_arguments_must_be_an_object(self, client):
        body = rpc(client, 'tools/call', {'name': 'get_item', 'arguments': ['JA000001']}).get_json()
        assert body['result']['isError'] is True

    def test_unexpected_exception_is_a_tool_error(self, client, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError('database on fire')
        monkeypatch.setattr('app.mcp.lookup_tools.get_available_label_types', boom)
        result = call(client, 'list_label_types')
        assert result['isError'] is True
        assert 'database on fire' in result['structuredContent']['error']
