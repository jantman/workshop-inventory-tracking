"""
Category path normalization utilities (Story 3.1).

This module is the single source of truth for the canonical form of a
materialized category path. It is a PURE module: standard library only, no
Flask/DB/framework imports, no I/O. Its only failure signal is
`InvalidCategoryPathError`, a plain `ValueError` subclass. The service layer
(`app/mariadb_catalog_service.py`) is the sole caller on the write path;
routes, templates and JavaScript never re-derive this logic (AD-4, FR13).

The canonical form
------------------
A category is a `/`-separated materialized path of arbitrary depth. Canonical
means, exactly:

- lowercase,
- `/`-separated with no leading or trailing separator,
- no empty segments,
- each segment stripped of surrounding whitespace.

Normalization only ever shortens or lowercases. It never rewrites the contents
of a segment: no space-to-hyphen, no slugging, no Unicode folding beyond
`str.lower()`. `'Power Supplies/DC DC'` stays two words per segment, because the
operator's own vocabulary is the taxonomy — there is nothing to slug it for.

Blank is not an error
---------------------
Every string either normalizes to a path or to nothing. `''`, `'   '`, `'/'`
and `None` all mean "no category" and yield `None`, never an exception: the
category field is optional and the catalog must stay fully usable with no
taxonomy at all. The only rejections are a caller-type fault (a non-string that
is not `None`) and a result that could not be stored in the 512-character
column.

Future extensibility:
--------------------
Story 3.2 (rename with descendants) and Epic 8 (faceted filtering) will add the
segment-boundary prefix predicate (`path = X OR path LIKE 'X/%'`) here, so that
prefix matching also has exactly one implementation. It is deliberately absent
until a requirement needs it.
"""

from typing import Optional

# The one separator between path segments.
CATEGORY_PATH_SEPARATOR = '/'

# Mirrors the products.category_path column width. A normalized value longer
# than this could not be stored, so it is rejected here rather than truncated
# (silently or by the database).
MAX_CATEGORY_PATH_LENGTH = 512


class InvalidCategoryPathError(ValueError):
    """
    Raised when a value cannot be normalized to a category path: a non-string
    input (other than None), or a normalized result that exceeds
    `MAX_CATEGORY_PATH_LENGTH`. A plain `ValueError` subclass so this module
    stays free of any app/framework dependency; callers translate it if they
    need a domain error.

    Note that "normalizes to nothing" is NOT a failure — blank input yields
    None (see the module docstring).
    """


def normalize_category_path(value: Optional[str]) -> Optional[str]:
    """
    Return the canonical form of a category path, or None when the value
    carries no category.

    Steps: split on `/`; strip surrounding whitespace from every segment; drop
    empty segments (which absorbs leading, trailing and repeated separators);
    rejoin with a single `/`; lowercase.

    Args:
        value: A category path as typed, or None.

    Returns:
        The canonical path, or None when nothing is left after normalization
        (blank, whitespace-only, separators-only, or None input).

    Raises:
        InvalidCategoryPathError: if `value` is neither a string nor None, or
            if the normalized result is longer than MAX_CATEGORY_PATH_LENGTH.

    Examples:
        >>> normalize_category_path('  /Electronics // Power/DC-DC Converters/ ')
        'electronics/power/dc-dc converters'
        >>> normalize_category_path('electronics/power')
        'electronics/power'
        >>> normalize_category_path('   ') is None
        True
    """
    if value is None:
        return None
    if not isinstance(value, str):
        # Non-str input (int, list, bytes, Decimal, ...) is a caller-type
        # fault, not scan/form data: every HTML form field arrives as a
        # string. Failing here rather than on a bare AttributeError from
        # .split() keeps this module's single failure signal honest.
        raise InvalidCategoryPathError(
            f'Category path must be a string or None, got '
            f'{type(value).__name__}: {value!r}.')

    segments = [segment.strip()
                for segment in value.split(CATEGORY_PATH_SEPARATOR)]
    segments = [segment for segment in segments if segment]
    if not segments:
        return None

    normalized = CATEGORY_PATH_SEPARATOR.join(segments).lower()
    if len(normalized) > MAX_CATEGORY_PATH_LENGTH:
        raise InvalidCategoryPathError(
            f'Category path is too long: {len(normalized)} characters '
            f'(max {MAX_CATEGORY_PATH_LENGTH}).')
    return normalized
