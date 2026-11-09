"""Tool registry, argument checking and result shapes for the MCP server (070).

A tool is a :class:`Tool` entry in :data:`TOOLS`, added by the :func:`tool`
decorator in the handler modules. Handlers take the checked arguments and
return a JSON-serializable dict; a business failure raises :class:`ToolError`,
which the endpoint reports as a tool result with ``isError: true``.

The entity shapes (``item_summary`` and friends) are data-model.md's.
Measurements leave as exact decimal strings and never pass through float.

Author: Jason Antman, 2026.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Optional

from app.database import InventoryItem, Product

Handler = Callable[[dict], dict]


class ToolError(Exception):
    """A tool call that failed for a reason the assistant can act on.

    Args:
        message: what went wrong, in the words the web would use.
        details: per-field or per-item errors, when the operation reports them.
    """

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


@dataclass(frozen=True)
class Tool:
    """One registered MCP tool."""

    name: str
    title: str
    description: str
    input_schema: dict
    read_only: bool
    handler: Handler
    destructive: bool = False
    idempotent: bool = False

    def to_listing(self) -> dict:
        """The tool as ``tools/list`` describes it."""
        annotations: dict[str, Any] = {'title': self.title, 'readOnlyHint': self.read_only}
        if not self.read_only:
            annotations['destructiveHint'] = self.destructive
            if self.idempotent:
                annotations['idempotentHint'] = True
        return {
            'name': self.name,
            'title': self.title,
            'description': self.description,
            'inputSchema': self.input_schema,
            'annotations': annotations,
        }


TOOLS: list[Tool] = []


def tool(
    name: str,
    title: str,
    description: str,
    input_schema: dict,
    read_only: bool,
    destructive: bool = False,
    idempotent: bool = False,
) -> Callable[[Handler], Handler]:
    """Register the decorated function as a tool's handler."""

    def register(handler: Handler) -> Handler:
        TOOLS.append(Tool(name, title, description, input_schema, read_only,
                          handler, destructive, idempotent))
        return handler

    return register


def get_tool(name: str) -> Optional[Tool]:
    """The registered tool called ``name``, or None."""
    for entry in TOOLS:
        if entry.name == name:
            return entry
    return None


# --------------------------------------------------------------------------
# Schema building
# --------------------------------------------------------------------------

def schema(properties: dict, required: tuple[str, ...] = ()) -> dict:
    """An input schema: an object with exactly these properties."""
    result: dict[str, Any] = {
        'type': 'object',
        'properties': properties,
        'additionalProperties': False,
    }
    if required:
        result['required'] = list(required)
    return result


def string(description: str, **extra: Any) -> dict:
    """A string property."""
    return {'type': 'string', 'description': description, **extra}


def nullable_string(description: str) -> dict:
    """A string property that also accepts null (meaning clear it)."""
    return {'type': ['string', 'null'], 'description': description}


def integer(description: str, **extra: Any) -> dict:
    """An integer property."""
    return {'type': 'integer', 'description': description, **extra}


def boolean(description: str, **extra: Any) -> dict:
    """A boolean property."""
    return {'type': 'boolean', 'description': description, **extra}


def measurement_property(description: str, nullable: bool = False) -> dict:
    """A measurement property: a decimal or fraction string, or a JSON number."""
    types = ['string', 'number', 'null'] if nullable else ['string', 'number']
    return {
        'type': types,
        'description': f'{description} Inches (weight: pounds); "1/2", "1 1/4", "0.375" or a number.',
    }


PAGING_PROPERTIES = {
    'limit': integer('Most results to return (default 50, max 200).', minimum=1, maximum=200),
    'offset': integer('Results to skip before the first returned (default 0).', minimum=0),
}


# --------------------------------------------------------------------------
# Argument checking (a JSON Schema subset)
# --------------------------------------------------------------------------

_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    'string': lambda v: isinstance(v, str),
    # bool is an int subclass; true is not a number here.
    'integer': lambda v: isinstance(v, int) and not isinstance(v, bool),
    'number': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    'boolean': lambda v: isinstance(v, bool),
    'array': lambda v: isinstance(v, list),
    'object': lambda v: isinstance(v, dict),
    'null': lambda v: v is None,
}


def _check_value(value: Any, spec: dict, path: str) -> None:
    """Check one value against its property schema; raise ToolError naming ``path``."""
    types = spec.get('type')
    if types is not None:
        allowed = types if isinstance(types, list) else [types]
        if not any(_TYPE_CHECKS[t](value) for t in allowed):
            raise ToolError(f"Argument '{path}' must be {' or '.join(allowed)}")

    if value is None:
        return

    if 'enum' in spec and value not in spec['enum']:
        choices = ', '.join(repr(c) for c in spec['enum'])
        raise ToolError(f"Argument '{path}' must be one of: {choices}")

    if _TYPE_CHECKS['number'](value):
        if 'minimum' in spec and value < spec['minimum']:
            raise ToolError(f"Argument '{path}' must be at least {spec['minimum']}")
        if 'maximum' in spec and value > spec['maximum']:
            raise ToolError(f"Argument '{path}' must be at most {spec['maximum']}")

    if isinstance(value, list):
        if 'minItems' in spec and len(value) < spec['minItems']:
            raise ToolError(f"Argument '{path}' must have at least {spec['minItems']} entry")
        if 'items' in spec:
            for index, entry in enumerate(value):
                _check_value(entry, spec['items'], f'{path}[{index}]')

    if isinstance(value, dict) and 'properties' in spec:
        _check_object(value, spec, path)


def _check_object(value: dict, spec: dict, path: str) -> None:
    """Check an object's keys and each property's value."""
    properties = spec.get('properties', {})
    prefix = f'{path}.' if path else ''

    if spec.get('additionalProperties') is False:
        unknown = sorted(set(value) - set(properties))
        if unknown:
            names = ', '.join(f"'{prefix}{name}'" for name in unknown)
            raise ToolError(f'Unknown argument(s): {names}')

    for name in spec.get('required', []):
        if name not in value:
            raise ToolError(f"Missing required argument '{prefix}{name}'")

    for name, entry in value.items():
        if name in properties:
            _check_value(entry, properties[name], f'{prefix}{name}')


def check_arguments(input_schema: dict, arguments: Any) -> dict:
    """Check a call's arguments against the tool's input schema.

    Enforces required keys, ``additionalProperties: false``, JSON types,
    ``enum``, ``minimum``/``maximum``, ``minItems`` and array ``items``.

    Returns:
        The arguments (``{}`` when the call sent none).

    Raises:
        ToolError: naming the first offending argument.
    """
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ToolError('Tool arguments must be a JSON object')
    _check_object(arguments, input_schema, '')
    return arguments


# --------------------------------------------------------------------------
# Shared conversions
# --------------------------------------------------------------------------

def measurement(value: Any) -> Optional[str]:
    """A measurement argument as the text the web form would have posted.

    JSON numbers are turned into their decimal text with ``str()``; nothing is
    computed in float. None stays None.
    """
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def paginate(rows: list, limit: Optional[int], offset: Optional[int]) -> tuple[list, dict]:
    """One page of ``rows`` and the paging fields every search result carries."""
    limit = 50 if limit is None else limit
    offset = 0 if offset is None else offset
    page = rows[offset:offset + limit]
    return page, {
        'total': len(rows),
        'returned': len(page),
        'offset': offset,
        'has_more': offset + len(page) < len(rows),
    }


def _decimal_text(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else str(value)


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if value is not None else None


def item_dimensions(item: InventoryItem) -> dict:
    """An item's measurements as exact decimal strings (null when not recorded)."""
    dimensions = item.dimensions
    return {
        'length': _decimal_text(dimensions.length),
        'width': _decimal_text(dimensions.width),
        'thickness': _decimal_text(dimensions.thickness),
        'wall_thickness': _decimal_text(dimensions.wall_thickness),
        'weight': _decimal_text(dimensions.weight),
    }


def _item_thread(item: InventoryItem) -> Optional[dict]:
    if not (item.thread_series or item.thread_handedness or item.thread_size):
        return None
    return {
        'series': item.thread_series,
        'handedness': item.thread_handedness,
        'size': item.thread_size,
    }


def item_summary(item: InventoryItem) -> dict:
    """ItemSummary (data-model.md)."""
    return {
        'ja_id': item.ja_id,
        'display_name': item.display_name,
        'item_type': item.item_type,
        'shape': item.shape,
        'material': item.material,
        'dimensions': item_dimensions(item),
        'thread': _item_thread(item),
        'location': item.location,
        'sub_location': item.sub_location,
        'active': bool(item.active),
        'precision': bool(item.precision),
    }


def item_detail(item: InventoryItem) -> dict:
    """ItemDetail: ItemSummary plus notes, purchase and timestamps."""
    result = item_summary(item)
    result.update({
        'notes': item.notes,
        'purchase_date': item.purchase_date.strftime('%Y-%m-%d') if item.purchase_date else None,
        'purchase_price': _decimal_text(item.purchase_price),
        'purchase_location': item.purchase_location,
        'vendor': item.vendor,
        'vendor_part_number': item.vendor_part,
        'date_added': _iso(item.date_added),
        'last_modified': _iso(item.last_modified),
    })
    return result


def history_row(item: InventoryItem) -> dict:
    """HistoryRow: one stored row of an item, active or retired."""
    return {
        'active': bool(item.active),
        'dimensions': item_dimensions(item),
        'location': item.location,
        'sub_location': item.sub_location,
        'notes': item.notes,
        'date_added': _iso(item.date_added),
        'last_modified': _iso(item.last_modified),
    }


def product_summary(product: Product) -> dict:
    """ProductSummary (data-model.md). Needs ``identifiers`` loaded."""
    return {
        'product_id': product.id,
        'code': product.internal_code,
        'description': product.description,
        'category_path': product.category_path,
        'location': product.location,
        'sub_location': product.sub_location,
        'quantity': product.quantity,
        'quantity_tracked': product.is_tracked,
        'quantity_counted_at': _iso(product.quantity_updated_at),
        'stock_status': product.stock_status,
        'stock_status_set_at': _iso(product.stock_status_updated_at),
    }


def product_detail(product: Product, latest_purchase: Any = None) -> dict:
    """ProductDetail. Needs what ``CatalogService.get_product`` loads."""
    result = product_summary(product)
    result.update({
        'manufacturer': product.manufacturer,
        'manufacturer_part_number': product.manufacturer_part_number,
        'reorder_threshold': product.reorder_threshold,
        'notes': product.notes,
        'tags': [tag.name for tag in product.tags],
        'specifications': [{'name': s.name, 'value': s.value} for s in product.specifications],
        'identifiers': [
            {'type': i.id_type, 'value': i.value, 'vendor': i.vendor or None}
            for i in product.identifiers
        ],
        'latest_purchase': None if latest_purchase is None else {
            'vendor': latest_purchase.vendor,
            'order_date': (latest_purchase.order_date.strftime('%Y-%m-%d')
                           if latest_purchase.order_date else None),
            'unit_price': _decimal_text(latest_purchase.unit_price),
        },
    })
    return result
