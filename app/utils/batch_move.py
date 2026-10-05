"""
Request handling shared by the two batch-move endpoints.

``POST /api/inventory/batch-move`` moves inventory items and
``POST /api/products/batch-move`` moves products. They take the same request
body, apply the same rule to the destination and answer with the same response,
so those three things live here once. What differs -- how the thing being moved
is found and saved, and the item route's audit trail -- stays in each route.
"""

from typing import Optional


def parse_moves(data) -> list:
    """Return the request's ``moves`` list.

    Raises:
        ValueError: ``'Invalid request data'`` when the body or its ``moves`` key
            is missing, ``'No moves provided'`` when ``moves`` is empty or not a
            list. The message is what the endpoint returns with its 400.
    """
    if not data or 'moves' not in data:
        raise ValueError('Invalid request data')

    moves = data['moves']
    if not moves or not isinstance(moves, list):
        raise ValueError('No moves provided')

    return moves


def destination(location: str, sub_location: Optional[str]) -> tuple[str, Optional[str]]:
    """Where a move puts its subject: ``(location, sub_location)``.

    Moving always replaces the sub-location. A move that names none -- absent,
    ``None`` or blank -- clears it, because a sub-location belongs to the old
    location and is meaningless at the new one.
    """
    if sub_location and sub_location.strip():
        return location.strip(), sub_location.strip()
    return location.strip(), None


def batch_result(moved_count: int, total: int, failed: list) -> dict:
    """The response body for a batch move.

    ``success`` means *every* move succeeded; a partial batch reports how many
    failed in ``error`` and names each one in ``failed_moves``.
    """
    result = {
        'success': len(failed) == 0,
        'moved_count': moved_count,
        'total_count': total,
        'failed_moves': failed,
    }
    if failed:
        result['error'] = f'{len(failed)} items failed to move'
    return result
