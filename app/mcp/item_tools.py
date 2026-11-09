"""MCP tools for inventory items (070): search, read, add, edit, shorten, move, labels.

Every write goes through the helper the matching web route uses
(``_process_item_creation``, ``_edit_item_from_form``, ``_shorten_from_form``,
``_move_items``, ``_print_item_label``), so validation, audit logging and the
item-history invariants are the web's (research.md R4).

Author: Jason Antman, 2026.
"""

from datetime import datetime
from typing import Any, Optional

from app.main.routes import (
    SearchFilterError,
    _build_search_filter,
    _edit_item_from_form,
    _fit_to_dict,
    _get_inventory_service,
    _item_to_form_data,
    _move_items,
    _normalize_json_item_payload,
    _parse_dimension_value,
    _parse_requested_piece,
    _print_item_label,
    _process_item_creation,
    _shorten_from_form,
)
from app.models import ItemShape, ItemType, ThreadHandedness, ThreadSeries
from app.mcp.tools import (
    PAGING_PROPERTIES,
    ToolError,
    boolean,
    history_row,
    integer,
    item_detail,
    item_dimensions,
    item_summary,
    measurement,
    measurement_property,
    nullable_string,
    paginate,
    schema,
    string,
    tool,
)

ITEM_TYPES = [t.value for t in ItemType]
ITEM_SHAPES = [s.value for s in ItemShape]
THREAD_SERIES_NAMES = [s.name for s in ThreadSeries]

JA_ID = string('The item\'s JA ID: "JA" and six digits, e.g. JA000123 (any case).')

_DIMENSION_FIELDS = ('length', 'width', 'thickness', 'wall_thickness')


def _ja_id(value: str) -> str:
    return value.strip().upper()


def _item_field_properties(nullable: bool) -> dict:
    """The Add Item field set, shared by add_items and edit_item.

    On edit (``nullable``) a null clears an optional field.
    """
    text = nullable_string if nullable else string
    return {
        'item_type': string('Item type.', enum=ITEM_TYPES),
        'shape': string('Cross-section shape.', enum=ITEM_SHAPES),
        'material': string('Material, one of list_materials.'),
        'location': string('Storage location.'),
        'sub_location': text('Bin, drawer or shelf within the location.'),
        'length': measurement_property('Length.', nullable),
        'width': measurement_property('Width; the diameter for Round stock.', nullable),
        'thickness': measurement_property('Thickness.', nullable),
        'wall_thickness': measurement_property('Wall thickness (tube).', nullable),
        'weight': measurement_property('Weight.', nullable),
        'thread_series': text(f'Thread series, one of {", ".join(THREAD_SERIES_NAMES)}.'),
        'thread_handedness': {
            'type': ['string', 'null'] if nullable else 'string',
            'enum': [h.value for h in ThreadHandedness] + ([None] if nullable else []),
            'description': 'RH or LH (default RH when a series is given).',
        },
        'thread_size': text('Thread size, e.g. 1/4-20 or M10x1.5.'),
        'purchase_date': text('Purchase date, YYYY-MM-DD.'),
        'purchase_price': {
            'type': ['string', 'number', 'null'] if nullable else ['string', 'number'],
            'description': 'Purchase price in dollars.',
        },
        'purchase_location': text('Where it was bought.'),
        'vendor': text('Vendor.'),
        'vendor_part_number': text('Vendor part number.'),
        'notes': text('Free-text notes.'),
        'precision': boolean('Has precision (ground or certified) dimensions.'),
        'active': boolean('In current inventory. Default true on add.'),
    }


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

def _range_value(name: str, value: Any) -> Optional[str]:
    """A range bound through the web form's measurement parser."""
    if value is None:
        return None
    try:
        return _parse_dimension_value(measurement(value))
    except ValueError:
        raise ToolError(f"Argument '{name}' is not a measurement: {value!r}")


_SEARCH_PROPERTIES = {
    'material': string('Material; matches it and every material beneath it in the taxonomy.'),
    'item_type': string('Item type.', enum=ITEM_TYPES),
    'shape': string('Cross-section shape.', enum=ITEM_SHAPES),
    'location': string('Text the location contains.'),
    'notes': string('Text the notes contain.'),
    'ja_id': JA_ID,
    'thread_size': string('Text the thread size contains.'),
    'thread_series': string(f'Thread series, one of {", ".join(THREAD_SERIES_NAMES)}.'),
    'precision': boolean('Only precision (true) or only non-precision (false) stock.'),
    'include_inactive': boolean('Include items no longer in inventory (default false).'),
    **PAGING_PROPERTIES,
}
for _field in _DIMENSION_FIELDS:
    _label = _field.replace('_', ' ')
    _SEARCH_PROPERTIES[f'{_field}_min'] = measurement_property(f'Minimum {_label}.')
    _SEARCH_PROPERTIES[f'{_field}_max'] = measurement_property(f'Maximum {_label}.')


@tool(
    name='search_items',
    title='Search inventory items',
    description=(
        'Search metal stock (inventory items) by material (hierarchical), type, shape, '
        'dimension ranges (width is the diameter for Round stock), thread, location or '
        'notes text. Current inventory only unless include_inactive is true. '
        'Returns item summaries with paging.'
    ),
    input_schema=schema(_SEARCH_PROPERTIES),
    read_only=True,
)
def search_items(args: dict) -> dict:
    data: dict[str, Any] = {}
    for key in ('material', 'item_type', 'shape', 'location', 'notes', 'ja_id',
                'thread_size', 'thread_series', 'precision'):
        if key in args:
            data[key] = args[key]
    for field in _DIMENSION_FIELDS:
        for bound in ('min', 'max'):
            key = f'{field}_{bound}'
            if args.get(key) is not None:
                data[key] = _range_value(key, args[key])
    if args.get('include_inactive'):
        data['active'] = ''

    service = _get_inventory_service()
    try:
        search_filter = _build_search_filter(service, data)
    except SearchFilterError as e:
        raise ToolError(str(e))
    items = service.search_items(search_filter)

    page, paging = paginate(items, args.get('limit'), args.get('offset'))
    return {**paging, 'items': [item_summary(item) for item in page]}


@tool(
    name='get_item',
    title='Get an inventory item',
    description=(
        'Full details of one inventory item by JA ID, active or not, with its history: '
        'every stored row oldest first, including the rows retired by shortening.'
    ),
    input_schema=schema({'ja_id': JA_ID}, required=('ja_id',)),
    read_only=True,
)
def get_item(args: dict) -> dict:
    ja_id = _ja_id(args['ja_id'])
    service = _get_inventory_service()
    item = service.get_canonical_item(ja_id)
    if item is None:
        raise ToolError(f'Item {ja_id} not found')
    return {
        'item': item_detail(item),
        'history': [history_row(row) for row in service.get_item_history(ja_id)],
    }


_PIECE_DIMENSIONS = ('length', 'width', 'thickness', 'diameter')


def _piece_value(value: Any) -> Any:
    """A requested dimension through the form's parser, so fractions work.

    Left as given when it does not parse, for ``_parse_requested_piece`` to
    refuse with its own message.
    """
    if value is None:
        return None
    text = measurement(value)
    try:
        return _parse_dimension_value(text) or text
    except ValueError:
        return text


_FIND_STOCK_PROPERTIES = {
    'material': string('Material; stock in it or beneath it in the taxonomy is considered.'),
    'shape': string('Shape of the part.', enum=['Rectangular', 'Round']),
}
for _name in _PIECE_DIMENSIONS:
    _FIND_STOCK_PROPERTIES[_name] = measurement_property(
        f'Part {_name}. Rectangular needs length, width, thickness; Round needs diameter, length.'
    )
    _FIND_STOCK_PROPERTIES[f'{_name}_tolerance'] = measurement_property(
        f'How much smaller than the {_name} the stock may be; blank means exact.'
    )


@tool(
    name='find_stock',
    title='Find stock for a part',
    description=(
        'What could this part be cut from? Given a material, shape and part dimensions '
        '(optional per-dimension tolerances), returns the active stock it fits in, best '
        'fit first, as the Find Stock page does.'
    ),
    input_schema=schema(_FIND_STOCK_PROPERTIES, required=('material', 'shape')),
    read_only=True,
)
def find_stock(args: dict) -> dict:
    material = args['material'].strip()
    if not material:
        raise ToolError('Material is required')

    data: dict[str, Any] = {'shape': args['shape']}
    for name in _PIECE_DIMENSIONS:
        if name in args:
            data[name] = _piece_value(args[name])
        if f'{name}_tolerance' in args:
            data[f'{name}_tolerance'] = _piece_value(args[f'{name}_tolerance'])

    piece, message = _parse_requested_piece(data)
    if piece is None:
        raise ToolError(message)

    result = _get_inventory_service().find_stock(material, piece)
    return {
        'fits': [{'item': item_summary(item), **_fit_to_dict(fit)} for item, fit in result.items],
        'considered': result.considered,
        'skipped_incomplete': result.skipped_incomplete,
        'skipped_hollow': result.skipped_hollow,
    }


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------

_ADD_PROPERTIES = {
    **_item_field_properties(nullable=False),
    'quantity': integer('How many identical items to create, each with its own JA ID (default 1).',
                        minimum=1, maximum=100),
}


def _check_item_inputs(supplied: dict, thread_series: Any) -> None:
    """Refuse inputs the form parser would silently drop.

    The web form cannot send these (a date picker, and thread fields shown only
    once a series is chosen), so the parser never had to refuse them; an
    assistant can, and would otherwise be told the call succeeded.
    """
    purchase_date = supplied.get('purchase_date')
    if purchase_date:
        try:
            datetime.strptime(str(purchase_date), '%Y-%m-%d')
        except ValueError:
            raise ToolError(f'Invalid purchase_date {purchase_date!r}: use YYYY-MM-DD')
    has_series = bool(thread_series) and str(thread_series) != 'None'
    for key in ('thread_size', 'thread_handedness'):
        if supplied.get(key) and not has_series:
            raise ToolError(f'{key} needs thread_series: an item without a thread series stores no thread fields')


@tool(
    name='add_items',
    title='Add inventory items',
    description=(
        'Add one or more identical pieces of metal stock. JA IDs are allocated by the '
        'server and returned. Required dimensions depend on type and shape '
        '(list_item_types_and_shapes); material must be one of list_materials. '
        'Created active unless active is false.'
    ),
    input_schema=schema(_ADD_PROPERTIES,
                        required=('item_type', 'shape', 'material', 'location')),
    read_only=False,
)
def add_items(args: dict) -> dict:
    _check_item_inputs(args, args.get('thread_series'))
    body = dict(args)
    body.setdefault('active', True)
    if 'quantity' in body:
        body['quantity_to_create'] = body.pop('quantity')
    try:
        normalized = _normalize_json_item_payload(body)
    except ValueError as e:
        raise ToolError(str(e))

    # The allocation POST /api/inventory/items makes before delegating: the
    # next free JA ID, which a bulk add's own loop then treats as its floor.
    service = _get_inventory_service()
    normalized['ja_id'] = f'JA{service.get_max_ja_id_number() + 1:06d}'

    result = _process_item_creation(normalized)
    if result['status'] == 'ok':
        return {'created_ja_ids': result['created_ja_ids'], 'message': result['message']}
    if result['status'] == 'partial':
        return {'created_ja_ids': result['created_ja_ids'], 'message': result['message'],
                'errors': result['errors']}
    raise ToolError(result['message'], details=result['errors'])


def _form_value(value: Any) -> str:
    return '' if value is None else measurement(value)


@tool(
    name='edit_item',
    title='Edit an inventory item',
    description=(
        'Change fields of one inventory item by JA ID. Only the fields given change; '
        'null clears an optional field. The same validation as the Edit Item page '
        'applies. Use shorten_item, not this, to record a cut (it keeps history).'
    ),
    input_schema=schema({'ja_id': JA_ID, **_item_field_properties(nullable=True)},
                        required=('ja_id',)),
    read_only=False,
)
def edit_item(args: dict) -> dict:
    ja_id = _ja_id(args['ja_id'])
    service = _get_inventory_service()
    item = service.get_canonical_item(ja_id)
    if item is None:
        raise ToolError(f'Item {ja_id} not found')

    form_data = _item_to_form_data(item)
    for key, value in args.items():
        if key == 'ja_id':
            continue
        if key in ('active', 'precision'):
            # Checkbox semantics: present as 'on' when set, absent when not.
            if value:
                form_data[key] = 'on'
            else:
                form_data.pop(key, None)
        else:
            form_data[key] = _form_value(value)

    _check_item_inputs(args, form_data.get('thread_series'))
    outcome = _edit_item_from_form(ja_id, item, form_data)
    if outcome['status'] != 'ok':
        message = outcome['message']
        if outcome.get('detail'):
            message = f"{message} ({outcome['detail']})"
        raise ToolError(message)

    changed = sorted(k for k in outcome['changes'] if k != 'last_modified')
    return {'item': item_detail(outcome['item']), 'changed_fields': changed}


@tool(
    name='shorten_item',
    title='Shorten an inventory item',
    description=(
        'Record that a piece was cut down to a new, shorter length. The JA ID stays the '
        'same; the previous row is retired into the item\'s history (see get_item). '
        'new_length must be shorter than the current length.'
    ),
    input_schema=schema({
        'ja_id': JA_ID,
        'new_length': measurement_property('The length remaining after the cut.'),
        'cut_date': string('Date of the cut, YYYY-MM-DD (default today).'),
        'notes': string('Notes about the cut.'),
    }, required=('ja_id', 'new_length')),
    read_only=False,
    destructive=True,
)
def shorten_item(args: dict) -> dict:
    ja_id = _ja_id(args['ja_id'])
    service = _get_inventory_service()
    before = service.get_item(ja_id)

    form_data = {
        'source_ja_id': ja_id,
        'new_length': measurement(args['new_length']),
        # The tool call is the operator's confirmation.
        'confirm_operation': 'on',
    }
    if args.get('cut_date'):
        form_data['cut_date'] = args['cut_date']
    if args.get('notes'):
        form_data['shortening_notes'] = args['notes']

    outcome = _shorten_from_form(form_data)
    if not outcome['success']:
        raise ToolError(outcome['error'] or outcome['message'])

    after = service.get_item(ja_id)
    return {
        'ja_id': ja_id,
        'original_length': item_dimensions(before)['length'] if before else None,
        'new_length': item_dimensions(after)['length'] if after else None,
    }


@tool(
    name='move_items',
    title='Move inventory items',
    description=(
        'Move one or more inventory items to a location. The sub-location is replaced: '
        'give one, or the old one is cleared. Reports each item that could not be moved; '
        'the rest still move.'
    ),
    input_schema=schema({
        'ja_ids': {'type': 'array', 'items': JA_ID, 'minItems': 1,
                   'description': 'JA IDs to move.'},
        'location': string('Destination location.'),
        'sub_location': nullable_string('Destination sub-location; omitted or null clears it.'),
    }, required=('ja_ids', 'location')),
    read_only=False,
    idempotent=True,
)
def move_items(args: dict) -> dict:
    moves = [
        {'ja_id': _ja_id(ja_id), 'new_location': args['location'],
         'new_sub_location': args.get('sub_location')}
        for ja_id in args['ja_ids']
    ]
    result = _move_items(moves)
    outcome = {
        'moved': result['moved_count'],
        'total': result['total_count'],
        'failed': result['failed_moves'],
    }
    if outcome['moved'] == 0:
        raise ToolError('No items were moved', details=outcome)
    return outcome


# --------------------------------------------------------------------------
# Labels
# --------------------------------------------------------------------------

def label_outcome(printed: list, failed: list) -> dict:
    """The labels result, or a ToolError when nothing printed."""
    if not printed:
        messages = {entry['error'] for entry in failed}
        message = messages.pop() if len(messages) == 1 else 'No labels were printed'
        raise ToolError(message, details={'printed': printed, 'failed': failed})
    return {'printed': printed, 'failed': failed}


LABEL_PROPERTIES = {
    'label_type': string('Label stock, one of list_label_types.'),
    'label_count': integer('Copies of each label, 1-99 (default 1).', minimum=1, maximum=99),
}


@tool(
    name='print_item_labels',
    title='Print item labels',
    description='Print barcode labels for one or more inventory items on the shop label printer.',
    input_schema=schema({
        'ja_ids': {'type': 'array', 'items': JA_ID, 'minItems': 1,
                   'description': 'JA IDs to print a label for.'},
        **LABEL_PROPERTIES,
    }, required=('ja_ids', 'label_type')),
    read_only=False,
)
def print_item_labels(args: dict) -> dict:
    service = _get_inventory_service()
    printed: list[str] = []
    failed: list[dict] = []
    for raw in args['ja_ids']:
        ja_id = _ja_id(raw)
        if service.get_canonical_item(ja_id) is None:
            failed.append({'ja_id': ja_id, 'error': f'Item {ja_id} not found'})
            continue
        try:
            _print_item_label(ja_id, args['label_type'].strip(), args.get('label_count', 1))
            printed.append(ja_id)
        except ValueError as e:
            failed.append({'ja_id': ja_id, 'error': str(e)})
        except Exception as e:
            failed.append({'ja_id': ja_id, 'error': f'Failed to print label: {e}'})
    return label_outcome(printed, failed)
