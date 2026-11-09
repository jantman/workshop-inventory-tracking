"""E2E: the MCP endpoint over real HTTP against the live server (070).

Adds, shortens and moves an item through MCP tool calls, then checks in the
browser that the inventory list and the item's history show the result:
the new location, and the shortened row active with the original retained as
an inactive history row (constitution VI).

Author: Jason Antman, 2026.
"""

from typing import Any

import pytest
import requests
from playwright.sync_api import expect

from tests.e2e.pages.inventory_list_page import InventoryListPage


def _rpc(base_url: str, method: str, params: dict, message_id: int) -> dict:
    response = requests.post(
        f'{base_url}/mcp',
        json={'jsonrpc': '2.0', 'id': message_id, 'method': method, 'params': params},
        headers={'Accept': 'application/json, text/event-stream'},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert 'result' in body, body
    return body['result']


def _tool(base_url: str, name: str, arguments: dict[str, Any], message_id: int) -> dict:
    result = _rpc(base_url, 'tools/call', {'name': name, 'arguments': arguments}, message_id)
    assert result['isError'] is False, result['structuredContent']
    return result['structuredContent']


@pytest.mark.e2e
def test_mcp_add_shorten_move_shows_in_history(page, live_server):
    url = live_server.url

    init = _rpc(url, 'initialize', {
        'protocolVersion': '2025-06-18',
        'capabilities': {},
        'clientInfo': {'name': 'e2e', 'version': '0'},
    }, 1)
    assert init['protocolVersion'] == '2025-06-18'

    created = _tool(url, 'add_items', {
        'item_type': 'Bar', 'shape': 'Round', 'material': 'Carbon Steel',
        'location': 'Rack A', 'length': '36', 'width': '1',
    }, 2)['created_ja_ids']
    assert len(created) == 1
    ja_id = created[0]

    shortened = _tool(url, 'shorten_item', {'ja_id': ja_id, 'new_length': '24 1/2',
                                            'notes': 'cut via MCP'}, 3)
    assert (shortened['original_length'], shortened['new_length']) == ('36', '24.5')

    moved = _tool(url, 'move_items', {'ja_ids': [ja_id], 'location': 'Rack Z'}, 4)
    assert moved['moved'] == 1

    list_page = InventoryListPage(page, url)
    list_page.navigate()
    row = page.locator(f'#inventory-table-body tr:has-text("{ja_id}")')
    expect(row).to_contain_text('Rack Z')

    page.locator(f'button[onclick*="showItemHistory(\'{ja_id}\')"]').click()
    expect(page.locator('#item-history-modal')).to_be_visible()

    timeline = page.locator('#history-modal-body .timeline-item')
    expect(timeline).to_have_count(2)
    expect(page.locator('#history-modal-body .timeline-item-inactive')).to_contain_text('L: 36"')
    active = page.locator('#history-modal-body .timeline-item-active')
    expect(active).to_contain_text('L: 24.5"')
    expect(active).to_contain_text('cut via MCP')
