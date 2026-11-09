"""MCP tools for catalog products (070): search, read, add, edit, count, flag, move, labels.

Each tool calls the ``CatalogService`` method the product pages and JSON APIs
call, or the product route helper the page uses (``_move_products``,
``_print_product_label``), so validation is the web's. ``ValidationError`` and
``ItemNotFoundError`` become tool errors with the service's message.

Author: Jason Antman, 2026.
"""

from typing import Any

from app.catalog_service import CatalogService
from app.database import Product
from app.exceptions import ItemNotFoundError, ValidationError
from app.mcp.item_tools import LABEL_PROPERTIES, label_outcome
from app.mcp.tools import (
    PAGING_PROPERTIES,
    ToolError,
    integer,
    nullable_string,
    paginate,
    product_detail,
    product_summary,
    schema,
    string,
    tool,
)
from app.models import IdentifierType
from app.product.routes import (
    LabelPrintError,
    _get_catalog_service,
    _move_products,
    _print_product_label,
)

PRODUCT_REF_PROPERTIES = {
    'code': string('The product\'s internal code (WIT plus ten characters, on its label).'),
    'product_id': integer('The product\'s numeric ID (as in its web page URL).'),
}

PRODUCT_LIST = {
    'type': 'array',
    'minItems': 1,
    'items': {'type': ['string', 'integer']},
    'description': 'Products, each an internal code (string) or a product ID (integer).',
}


def _load(service: CatalogService, product_id: int) -> Product:
    product = service.get_product(product_id)
    if product is None:
        raise ToolError(f'Product {product_id} not found')
    return product


def _by_code(service: CatalogService, code: str) -> Product:
    normalized = code.strip().upper()
    found = service.find_product_by_identifier(normalized, id_type=IdentifierType.INTERNAL.value)
    if found is None:
        raise ToolError(f'No product carries the code {code}')
    return _load(service, found.id)


def _resolve_product(service: CatalogService, args: dict) -> Product:
    """The product ``code`` or ``product_id`` names; exactly one must be given."""
    has_code = args.get('code') is not None
    has_id = args.get('product_id') is not None
    if has_code == has_id:
        raise ToolError('Give exactly one of code or product_id')
    if has_code:
        return _by_code(service, args['code'])
    return _load(service, args['product_id'])


def _resolve_reference(service: CatalogService, reference: Any) -> Product:
    """A product named by a code (string) or an ID (integer)."""
    if isinstance(reference, str):
        return _by_code(service, reference)
    return _load(service, reference)


def _detail(service: CatalogService, product_id: int) -> dict:
    product = _load(service, product_id)
    return product_detail(product, service.get_latest_purchase(product_id))


def _service_call(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a service write, turning its refusals into tool errors."""
    try:
        return func(*args, **kwargs)
    except (ValidationError, ItemNotFoundError) as e:
        raise ToolError(e.message)


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

@tool(
    name='search_products',
    title='Search products',
    description=(
        'Search the product catalog by text (description, specifications, manufacturer, '
        'part numbers, notes and every identifier, including internal codes), category '
        'subtree, tag, stock state, specification, or missing category/location. '
        'At most 500 matches are considered; results are paged.'
    ),
    input_schema=schema({
        'query': string('Free text, or an identifier such as a part number or code.'),
        'category': string('Category path; matches it and its sub-categories.'),
        'tag': string('Tag name.'),
        'stock': string('Stock state, as the Products page filter.',
                        enum=['low', 'on-order', 'tracked', 'untracked', 'none-on-hand']),
        'spec_name': string('Specification name (whole, case-insensitive).'),
        'spec_value': string('With spec_name: text the value contains.'),
        'missing': string('Only products still missing this.',
                          enum=['category', 'location', 'either']),
        **PAGING_PROPERTIES,
    }),
    read_only=True,
)
def search_products(args: dict) -> dict:
    products = _get_catalog_service().search_products(
        query=args.get('query'),
        category=args.get('category'),
        tag=args.get('tag'),
        stock=args.get('stock'),
        spec_name=args.get('spec_name'),
        spec_value=args.get('spec_value'),
        missing=args.get('missing'),
    )
    page, paging = paginate(products, args.get('limit'), args.get('offset'))
    return {**paging, 'products': [product_summary(p) for p in page]}


@tool(
    name='get_product',
    title='Get a product',
    description=(
        'Full details of one product by internal code or product ID: identifiers, '
        'category, specifications, tags, quantity with when it was counted, low/out flag '
        'with when it was set, location, and the latest purchase.'
    ),
    input_schema=schema(PRODUCT_REF_PROPERTIES),
    read_only=True,
)
def get_product(args: dict) -> dict:
    service = _get_catalog_service()
    product = _resolve_product(service, args)
    return {'product': product_detail(product, service.get_latest_purchase(product.id))}


@tool(
    name='get_reorder_list',
    title='Get the reorder list',
    description=(
        'Products that need buying: counted below their reorder threshold, or flagged '
        'low/out. on_order says whether an order for one is already outstanding.'
    ),
    input_schema=schema({}),
    read_only=True,
)
def get_reorder_list(args: dict) -> dict:
    service = _get_catalog_service()
    entries = []
    for entry in service.get_reorder_products():
        product = entry['product']
        reasons = []
        if entry['is_threshold_low']:
            reasons.append('below reorder threshold')
        if entry['is_manually_low']:
            reasons.append(f'flagged {product.stock_status}')
        entries.append({
            # Reloaded: the reorder query does not load identifiers, and the
            # summary carries the internal code.
            'product': product_summary(_load(service, product.id)),
            'reason': '; '.join(reasons),
            'on_order': entry['is_on_order'],
        })
    return {'products': entries}


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------

_SPECIFICATIONS = {
    'type': 'array',
    'description': 'Specifications in display order.',
    'items': schema({'name': string('Name.'), 'value': string('Value.')},
                    required=('name', 'value')),
}

_EDITABLE_PROPERTIES = {
    'description': string('The product\'s description (its name in the catalog).'),
    'manufacturer': nullable_string('Manufacturer.'),
    'manufacturer_part_number': nullable_string('Manufacturer part number.'),
    'category_path': nullable_string('Category path, e.g. "electronics/ics/op-amps".'),
    'location': nullable_string('Storage location.'),
    'sub_location': nullable_string('Bin or drawer within the location.'),
    'notes': nullable_string('Notes.'),
    'reorder_threshold': {'type': ['integer', 'null'], 'minimum': 0,
                          'description': 'Reorder when the count falls to this; needs a count.'},
}


@tool(
    name='add_product',
    title='Add a product',
    description=(
        'Add a product to the catalog. Only the description is required. Returns the '
        'product with its new internal code. quantity omitted means the count is not tracked.'
    ),
    input_schema=schema({
        **_EDITABLE_PROPERTIES,
        'quantity': {'type': ['integer', 'null'], 'minimum': 0,
                     'description': 'Count on hand; omit or null for not tracked.'},
        'specifications': _SPECIFICATIONS,
        'tags': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Tag names.'},
        'identifiers': {
            'type': 'array',
            'description': 'Identifiers to attach.',
            'items': schema({
                'type': string('Identifier type.',
                               enum=[t.value for t in IdentifierType
                                     if t is not IdentifierType.INTERNAL]),
                'value': string('Identifier value.'),
                'vendor': string('Vendor, for VENDOR and DISTRIBUTOR identifiers.'),
            }, required=('type', 'value')),
        },
    }, required=('description',)),
    read_only=False,
)
def add_product(args: dict) -> dict:
    service = _get_catalog_service()
    fields = dict(args)
    if 'identifiers' in fields:
        fields['identifiers'] = [
            {'id_type': i['type'], 'value': i['value'], 'vendor': i.get('vendor')}
            for i in fields['identifiers']
        ]
    product = _service_call(service.create_product, **fields)
    return {'product': _detail(service, product.id)}


@tool(
    name='edit_product',
    title='Edit a product',
    description=(
        'Change fields of one product (by code or product_id). Only the fields given '
        'change; null clears an optional field. specifications, when given, replaces the '
        'whole set. Counts, flags and moves have their own tools.'
    ),
    input_schema=schema({**PRODUCT_REF_PROPERTIES, **_EDITABLE_PROPERTIES,
                         'specifications': _SPECIFICATIONS}),
    read_only=False,
)
def edit_product(args: dict) -> dict:
    service = _get_catalog_service()
    product = _resolve_product(service, args)
    fields = {k: v for k, v in args.items() if k not in PRODUCT_REF_PROPERTIES}
    if not fields:
        raise ToolError('No fields to change were given')
    _service_call(service.update_product, product.id, **fields)
    return {'product': _detail(service, product.id)}


@tool(
    name='set_product_category',
    title='Set product category',
    description=(
        'Give one or more products the same category. All or nothing: if any product is '
        'unknown or the category is invalid, nothing changes. A new category path is created.'
    ),
    input_schema=schema({
        'products': PRODUCT_LIST,
        'category_path': string('The category path to set; blank is refused.'),
    }, required=('products', 'category_path')),
    read_only=False,
    idempotent=True,
)
def set_product_category(args: dict) -> dict:
    service = _get_catalog_service()
    products = [_resolve_reference(service, ref) for ref in args['products']]
    report = _service_call(service.set_category, [p.id for p in products], args['category_path'])
    return {
        'category_path': report['category_path'],
        'products': [product_summary(_load(service, p.id)) for p in products],
    }


@tool(
    name='set_product_count',
    title='Record a product count',
    description=(
        'Record how many of a product are on hand (a fresh count, which resets its age), '
        'or null to stop tracking the count.'
    ),
    input_schema=schema({
        **PRODUCT_REF_PROPERTIES,
        'quantity': {'type': ['integer', 'null'], 'minimum': 0,
                     'description': 'Count on hand, or null for not tracked.'},
    }, required=('quantity',)),
    read_only=False,
    idempotent=True,
)
def set_product_count(args: dict) -> dict:
    service = _get_catalog_service()
    product = _resolve_product(service, args)
    _service_call(service.set_quantity, product.id, args['quantity'])
    return {'product': _detail(service, product.id)}


@tool(
    name='adjust_product_count',
    title='Adjust a product count',
    description=(
        'Add to or take from a tracked product count, as the +/- buttons on the product '
        'page do (a fresh count). Refused for an untracked product or below zero.'
    ),
    input_schema=schema({
        **PRODUCT_REF_PROPERTIES,
        'delta': integer('Signed amount to add (negative to take away); not zero.'),
    }, required=('delta',)),
    read_only=False,
)
def adjust_product_count(args: dict) -> dict:
    delta = args['delta']
    if delta == 0:
        raise ToolError("Argument 'delta' must not be zero")
    service = _get_catalog_service()
    product = _resolve_product(service, args)
    previous = product.quantity
    if previous is None:
        raise ToolError('This product\'s count is not tracked; record a count with set_product_count first')
    if previous + delta < 0:
        raise ToolError(f'The count would go below zero ({previous} {delta:+d})')
    _service_call(service.set_quantity, product.id, previous + delta)
    return {'product': _detail(service, product.id), 'previous_quantity': previous}


@tool(
    name='set_product_stock_flag',
    title='Set product low/out flag',
    description='Flag a product low or out, or clear the flag with null. Independent of any count.',
    input_schema=schema({
        **PRODUCT_REF_PROPERTIES,
        'flag': {'type': ['string', 'null'], 'enum': ['low', 'out', None],
                 'description': '"low", "out", or null to clear.'},
    }, required=('flag',)),
    read_only=False,
    idempotent=True,
)
def set_product_stock_flag(args: dict) -> dict:
    service = _get_catalog_service()
    product = _resolve_product(service, args)
    _service_call(service.set_stock_status, product.id, args['flag'])
    return {'product': _detail(service, product.id)}


@tool(
    name='move_products',
    title='Move products',
    description=(
        'Move one or more products (by internal code) to a location. The sub-location is '
        'replaced: give one, or the old one is cleared. Reports each product that could '
        'not be moved; the rest still move.'
    ),
    input_schema=schema({
        'products': {'type': 'array', 'minItems': 1, 'items': {'type': 'string'},
                     'description': 'Internal codes of the products to move.'},
        'location': string('Destination location.'),
        'sub_location': nullable_string('Destination sub-location; omitted or null clears it.'),
    }, required=('products', 'location')),
    read_only=False,
    idempotent=True,
)
def move_products(args: dict) -> dict:
    result = _move_products([
        {'code': code, 'new_location': args['location'],
         'new_sub_location': args.get('sub_location')}
        for code in args['products']
    ])
    outcome = {
        'moved': result['moved_count'],
        'total': result['total_count'],
        'failed': result['failed_moves'],
    }
    if outcome['moved'] == 0:
        raise ToolError('No products were moved', details=outcome)
    return outcome


@tool(
    name='print_product_labels',
    title='Print product labels',
    description='Print labels (description, code barcode, provenance) for one or more products.',
    input_schema=schema({'products': PRODUCT_LIST, **LABEL_PROPERTIES},
                        required=('products', 'label_type')),
    read_only=False,
)
def print_product_labels(args: dict) -> dict:
    service = _get_catalog_service()
    printed: list[str] = []
    failed: list[dict] = []
    for reference in args['products']:
        try:
            product = _resolve_reference(service, reference)
        except ToolError as e:
            failed.append({'code': reference, 'error': e.message})
            continue
        try:
            _print_product_label(service, product, args['label_type'], args.get('label_count', 1))
            printed.append(product.internal_code)
        except ValueError as e:
            failed.append({'code': product.internal_code, 'error': str(e)})
        except LabelPrintError as e:
            failed.append({'code': product.internal_code, 'error': f'Failed to print label: {e}'})
    return label_outcome(printed, failed)
