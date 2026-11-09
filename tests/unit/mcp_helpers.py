"""Shared helpers for the MCP server unit tests (070).

Author: Jason Antman, 2026.
"""

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import sessionmaker

from app.database import InventoryItem, MaterialTaxonomy
from app.mariadb_inventory_service import InventoryService


def rpc(client: Any, method: str, params: Optional[dict] = None, message_id: Any = 1,
        headers: Optional[dict] = None) -> Any:
    """POST one JSON-RPC request to /mcp and return the response."""
    body: dict[str, Any] = {'jsonrpc': '2.0', 'id': message_id, 'method': method}
    if params is not None:
        body['params'] = params
    return client.post('/mcp', json=body, headers=headers or {})


def call(client: Any, name: str, arguments: Optional[dict] = None) -> dict:
    """Call a tool and return its result (``content``, ``structuredContent``, ``isError``)."""
    response = rpc(client, 'tools/call', {'name': name, 'arguments': arguments or {}})
    assert response.status_code == 200, response.data
    body = response.get_json()
    assert 'result' in body, body
    return body['result']


def ok(client: Any, name: str, arguments: Optional[dict] = None) -> dict:
    """Call a tool that must succeed and return its structured content."""
    result = call(client, name, arguments)
    assert result['isError'] is False, result['structuredContent']
    return result['structuredContent']


def fails(client: Any, name: str, arguments: Optional[dict] = None) -> dict:
    """Call a tool that must fail and return its structured content."""
    result = call(client, name, arguments)
    assert result['isError'] is True, result['structuredContent']
    return result['structuredContent']


def seed_materials(storage: Any, *names: str) -> None:
    """Put level-1 materials in the taxonomy, so material validation is on."""
    session = sessionmaker(bind=storage.engine)()
    try:
        for order, name in enumerate(names):
            session.add(MaterialTaxonomy(name=name, level=1, active=True, sort_order=order))
        session.commit()
    finally:
        session.close()


def seed_item(storage: Any, ja_id: str, **fields: Any) -> None:
    """Store one active item: a 36" x 1" round steel bar unless overridden."""
    values: dict[str, Any] = {
        'item_type': 'Bar', 'shape': 'Round', 'material': 'Steel',
        'length': Decimal('36'), 'width': Decimal('1'), 'location': 'Rack A',
    }
    values.update(fields)
    InventoryService(storage).add_item(InventoryItem(ja_id=ja_id, **values))


def item_count(storage: Any) -> int:
    """How many item rows (active or not) are stored."""
    session = sessionmaker(bind=storage.engine)()
    try:
        return session.query(InventoryItem).count()
    finally:
        session.close()
