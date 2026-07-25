"""
Category path normalization utilities (Stories 3.1, 3.2).

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

The segment-boundary predicate
-----------------------------
Story 3.2 (rename with descendants) adds the segment-boundary prefix predicate
(`path = X OR path LIKE 'X/%'`) promised above, as `is_descendant_path` plus the
SQL half `descendant_like_pattern`, and the per-path rewrite built on it
(`rewrite_category_path`). Epic 8's faceted filtering calls the same three, so
prefix matching has exactly one implementation and `thermal/heat` can never
match `thermal/heatgun-parts` in one place but not another. `ancestor_paths`
completes the set: it is how a caller recovers the interior nodes of a tree
that is stored only as its leaves.

Unlike `normalize_category_path`, which takes a value as typed, those four take
paths that are ALREADY canonical (as everything stored in
`products.category_path` is) and reject anything else as a caller fault.

Future extensibility:
--------------------
Nothing further is planned here. A category *delete* or *merge*, should one ever
be specified, would belong in the service — it is a decision about rows, not a
property of a path string.
"""

from typing import List, Optional

# The one separator between path segments.
CATEGORY_PATH_SEPARATOR = '/'

# Mirrors the products.category_path column width. A normalized value longer
# than this could not be stored, so it is rejected here rather than truncated
# (silently or by the database).
MAX_CATEGORY_PATH_LENGTH = 512

# The escape character `descendant_like_pattern` prefixes to every literal LIKE
# metacharacter it finds. Every caller MUST pass it as the `escape=` argument of
# the LIKE it builds the pattern for — a pattern escaped with a character the
# statement never declares is worse than no escaping at all, because the
# backslashes then match literally.
CATEGORY_LIKE_ESCAPE_CHAR = '\\'


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


def _require_canonical(value: Optional[str], role: str) -> str:
    """
    Guard for the three segment-boundary helpers below: return `value`, or
    raise if it is not a usable canonical path.

    They all take paths that are already canonical (the service normalizes
    before calling, and every stored path is canonical), so a None, a blank or
    a non-string here is a caller fault rather than operator input — and an
    empty ancestor in particular would make `descendant_like_pattern` produce
    `'/%'`, which matches nothing but reads as if it should match everything.
    Full canonicality is NOT re-derived: this is a cheap guard, not a second
    implementation of `normalize_category_path`.
    """
    if not isinstance(value, str):
        raise InvalidCategoryPathError(
            f'{role} must be a canonical category path string, got '
            f'{type(value).__name__}: {value!r}.')
    if not value:
        raise InvalidCategoryPathError(f'{role} must not be blank.')
    return value


def is_descendant_path(candidate: str, ancestor: str) -> bool:
    """
    Return True when `candidate` is at or under `ancestor` in the category
    tree (Story 3.2, FR17, AD-4).

    This is THE segment-boundary containment rule for the whole application —
    the rename's subtree, its collision check, and Epic 8's category facet all
    ask this one function. "At or under" is inclusive: a path is a descendant
    of itself, because a rename (or a filter) that carried the subtree but not
    the node itself would be nonsense.

    A raw `candidate.startswith(ancestor)` is exactly what this exists to
    prevent: it reports `'thermal/heatgun-parts'` as living under
    `'thermal/heat'`. Containment holds only on a segment boundary.

    Args:
        candidate: An already-canonical path (typically a stored
            products.category_path).
        ancestor: An already-canonical path to test containment against.

    Returns:
        True if `candidate == ancestor` or `candidate` starts with
        `ancestor` followed by the separator; False otherwise.

    Raises:
        InvalidCategoryPathError: if either argument is not a non-empty
            string — canonical paths are neither blank nor non-strings.

    Examples:
        >>> is_descendant_path('a/b/c', 'a/b')
        True
        >>> is_descendant_path('a/b', 'a/b')
        True
        >>> is_descendant_path('thermal/heatgun-parts', 'thermal/heat')
        False
    """
    candidate = _require_canonical(candidate, 'Candidate path')
    ancestor = _require_canonical(ancestor, 'Ancestor path')
    return (candidate == ancestor
            or candidate.startswith(ancestor + CATEGORY_PATH_SEPARATOR))


def descendant_like_pattern(ancestor: str) -> str:
    """
    Return the SQL `LIKE` pattern matching every STRICT descendant of
    `ancestor` (Story 3.2, FR17, AD-4).

    The SQL half of `is_descendant_path`: a query selects the subtree with
    `column == ancestor` OR `column.like(descendant_like_pattern(ancestor),
    escape=CATEGORY_LIKE_ESCAPE_CHAR)`. The node itself is deliberately NOT
    matched by the pattern — equality covers it, and folding it in would need
    an alternation SQL `LIKE` does not have.

    Every literal `%`, `_` and escape character in the ancestor is escaped:
    normalization never rewrites segment contents, so a canonical path may
    genuinely contain `%` or `_`, and an unescaped `_` would silently match any
    single character. The caller MUST pass CATEGORY_LIKE_ESCAPE_CHAR as the
    `escape=` argument.

    Args:
        ancestor: An already-canonical path.

    Returns:
        The escaped `LIKE` pattern for the ancestor's strict descendants.

    Raises:
        InvalidCategoryPathError: if `ancestor` is not a non-empty string.

    Examples:
        >>> descendant_like_pattern('a/b')
        'a/b/%'
        >>> descendant_like_pattern('power_supplies/50%')
        'power\\\\_supplies/50\\\\%/%'
    """
    ancestor = _require_canonical(ancestor, 'Ancestor path')
    escaped = (
        ancestor.replace(CATEGORY_LIKE_ESCAPE_CHAR,
                         CATEGORY_LIKE_ESCAPE_CHAR * 2)
        .replace('%', CATEGORY_LIKE_ESCAPE_CHAR + '%')
        .replace('_', CATEGORY_LIKE_ESCAPE_CHAR + '_')
    )
    return f'{escaped}{CATEGORY_PATH_SEPARATOR}%'


def rewrite_category_path(path: str, old_root: str, new_root: str) -> str:
    """
    Return `path` with its `old_root` prefix replaced by `new_root` (Story
    3.2, FR17).

    The per-row half of a rename-with-descendants: the node itself becomes
    `new_root`, and every descendant keeps its own suffix under the new root.
    Both roots are already canonical and `new_root` is canonical too, so the
    result is canonical by construction — the suffix is carried across
    untouched, never re-normalized.

    Args:
        path: An already-canonical path at or under `old_root`.
        old_root: The already-canonical path being renamed.
        new_root: The already-canonical path it becomes.

    Returns:
        The rewritten canonical path.

    Raises:
        InvalidCategoryPathError: if any argument is not a non-empty string,
            if `path` is not at or under `old_root` (a caller fault — the
            caller selects the subtree before rewriting it), or if the result
            would not fit MAX_CATEGORY_PATH_LENGTH.

    Examples:
        >>> rewrite_category_path('a/b/c', 'a/b', 'x/y')
        'x/y/c'
        >>> rewrite_category_path('a/b', 'a/b', 'x/y')
        'x/y'
    """
    new_root = _require_canonical(new_root, 'New root path')
    if not is_descendant_path(path, old_root):
        raise InvalidCategoryPathError(
            f'{path!r} is not at or under {old_root!r}, so it cannot be '
            f'rewritten onto {new_root!r}.')

    # The suffix is '' for the node itself and '/rest' for a descendant, so a
    # single concatenation covers both cases without a separator special case.
    rewritten = new_root + path[len(old_root):]
    if len(rewritten) > MAX_CATEGORY_PATH_LENGTH:
        raise InvalidCategoryPathError(
            f'Renaming {path!r} would produce a category path of '
            f'{len(rewritten)} characters (max {MAX_CATEGORY_PATH_LENGTH}).')
    return rewritten


def ancestor_paths(path: str) -> List[str]:
    """
    Return every PROPER ancestor of `path`, shallowest first (Story 3.2).

    The tree has no node table: it is only the set of paths products are filed
    at, so a product at `a/b/c` is the sole evidence that the interior nodes
    `a` and `a/b` exist. Anything presenting the tree — the category listing,
    and later Epic 8's facet — has to recover those interior nodes, and this is
    the one place that splits a path to do it.

    Args:
        path: An already-canonical path.

    Returns:
        The proper ancestors, outermost first. Empty for a single-segment
        path, which has no ancestor. `path` itself is never included.

    Raises:
        InvalidCategoryPathError: if `path` is not a non-empty string.

    Examples:
        >>> ancestor_paths('a/b/c')
        ['a', 'a/b']
        >>> ancestor_paths('a')
        []
    """
    path = _require_canonical(path, 'Path')
    segments = path.split(CATEGORY_PATH_SEPARATOR)
    return [CATEGORY_PATH_SEPARATOR.join(segments[:depth])
            for depth in range(1, len(segments))]
