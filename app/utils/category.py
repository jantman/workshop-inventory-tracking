"""
Category paths -- canonical form and subtree matching.

A category is a materialized path: a ``/``-separated string of arbitrary depth
stored on the product itself.  There is no categories table, so an empty category
cannot exist -- creating a category means typing it on a product, and removing the
last product in a category removes the category.  For this workshop that is the
correct behaviour, and it removes a table, its CRUD, and its orphan-cleanup story.

Normalization only lowercases and shortens.  It never slugs, hyphenates, or folds
Unicode: the operator's own vocabulary *is* the taxonomy, and
``Power Supplies/DC DC`` has nothing to be slugged for.

Pure module: standard library only.  No Flask, no database, no config.
"""

from typing import Optional

SEPARATOR = "/"

# LIKE wildcards that must not be honoured when they appear inside a real
# category name.
_LIKE_ESCAPE_CHAR = "\\"
_LIKE_SPECIAL = ("\\", "%", "_")


def canonical(path: Optional[str]) -> Optional[str]:
    """Return the canonical form of a category path.

    Blank input, whitespace, a bare separator and ``None`` all mean "no
    category" and are answered with ``None`` rather than an error -- a product
    without a category is an ordinary product, not a mistake.

    Args:
        path: The raw category path as typed.

    Returns:
        The canonical path (lowercase, separator-joined, no empty segments), or
        None for "no category".
    """
    if path is None:
        return None
    if not isinstance(path, str):
        raise TypeError(f"path must be a str or None, got {type(path).__name__}")

    segments = [segment.strip() for segment in path.split(SEPARATOR)]
    segments = [segment.lower() for segment in segments if segment.strip()]

    if not segments:
        return None

    return SEPARATOR.join(segments)


def segments(path: Optional[str]) -> list:
    """Split a canonical path into its segments.

    Args:
        path: A category path, canonical or not.

    Returns:
        The list of segments; empty for "no category".
    """
    canonical_path = canonical(path)
    if canonical_path is None:
        return []
    return canonical_path.split(SEPARATOR)


def is_descendant(candidate: Optional[str], ancestor: Optional[str]) -> bool:
    """Report whether ``candidate`` is ``ancestor`` or lives beneath it.

    The boundary is the separator, not the character count: filtering on ``foo``
    matches ``foo`` and ``foo/bar`` but not ``foo-bar``, which is a different
    category that merely starts with the same letters.

    Args:
        candidate: The category path being tested.
        ancestor: The category path being filtered on.

    Returns:
        True when the candidate is within the ancestor's subtree.
    """
    candidate_path = canonical(candidate)
    ancestor_path = canonical(ancestor)

    if ancestor_path is None:
        # Filtering on "no category" selects everything; the caller decides
        # whether to filter at all.
        return True
    if candidate_path is None:
        return False

    return candidate_path == ancestor_path or candidate_path.startswith(
        ancestor_path + SEPARATOR
    )


def descendant_like_pattern(ancestor: str) -> str:
    """Build the LIKE pattern matching an ancestor's strict descendants.

    Pairs with an equality test on the ancestor itself:
    ``path = :ancestor OR path LIKE :pattern ESCAPE '\\'``.  Wildcards appearing
    inside a real category name are escaped, so a category literally named
    ``100%`` does not match everything.

    Args:
        ancestor: The canonical ancestor path.

    Returns:
        The LIKE pattern, for use with ``escape='\\'``.
    """
    escaped = ancestor
    for special in _LIKE_SPECIAL:
        escaped = escaped.replace(special, _LIKE_ESCAPE_CHAR + special)
    return escaped + SEPARATOR + "%"
