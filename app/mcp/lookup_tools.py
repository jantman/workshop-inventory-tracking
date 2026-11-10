"""MCP reference lookups (070): the valid values other tools take.

Read-only. Each answers from the source the matching web form uses: the label
printer's types, the materials taxonomy the Add form validates against, the
type/shape requirements table, the field-suggestion vocabulary and the catalog's
category list.

Author: Jason Antman, 2026.
"""

from app.main.routes import _get_storage_backend, _get_valid_materials
from app.mcp.tools import integer, schema, string, tool
from app.models import ItemShape, ItemType
from app.product.routes import _get_catalog_service
from app.services.label_printer import get_available_label_types
from app.services.vocabulary import VocabularyService
from app.taxonomy import type_shape_validator


@tool(
    name='list_label_types',
    title='List label types',
    description='The label stocks the printer supports, for print_item_labels and print_product_labels.',
    input_schema=schema({}),
    read_only=True,
)
def list_label_types(args: dict) -> dict:
    return {'label_types': get_available_label_types()}


@tool(
    name='list_materials',
    title='List materials',
    description='The active materials an inventory item may be given (add_items, edit_item).',
    input_schema=schema({}),
    read_only=True,
)
def list_materials(args: dict) -> dict:
    return {'materials': _get_valid_materials()}


@tool(
    name='list_item_types_and_shapes',
    title='List item types and shapes',
    description=(
        'Inventory item types and shapes, and for each type the shapes it may have with '
        'the dimensions each combination requires.'
    ),
    input_schema=schema({}),
    read_only=True,
)
def list_item_types_and_shapes(args: dict) -> dict:
    return {
        'item_types': [t.value for t in ItemType],
        'shapes': [s.value for s in ItemShape],
        'requirements': type_shape_validator.requirements_by_name(),
    }


@tool(
    name='list_locations',
    title='List locations',
    description=(
        'Locations already in use (items and products), or, given a location, the '
        'sub-locations used within it. query narrows to values containing it.'
    ),
    input_schema=schema({
        'location': string('List the sub-locations used within this location instead.'),
        'query': string('Text the values contain.'),
        'limit': integer('Most values to return (default and max 50).', minimum=1, maximum=50),
    }),
    read_only=True,
)
def list_locations(args: dict) -> dict:
    location = (args.get('location') or '').strip() or None
    field = 'sub_location' if location else 'location'
    values = VocabularyService(_get_storage_backend()).suggest(
        field,
        query=(args.get('query') or '').strip() or None,
        limit=args.get('limit', 50),
        location=location,
    )
    return {'field': field, 'values': values}


@tool(
    name='list_product_categories',
    title='List product categories',
    description='Product category paths in use or named by the taxonomy, optionally under a prefix.',
    input_schema=schema({'prefix': string('Only categories starting with this path.')}),
    read_only=True,
)
def list_product_categories(args: dict) -> dict:
    return {'categories': _get_catalog_service().list_categories(args.get('prefix'))}
