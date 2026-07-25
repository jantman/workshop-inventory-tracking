"""
Free-form tag normalization utilities (Story 3.3).

This module is the single source of truth for the canonical form of a Product
tag and for parsing the operator's comma-separated tag list. It is a PURE
module: standard library only, no Flask/DB/framework imports, no I/O. Its only
failure signal is `InvalidTagError`, a plain `ValueError` subclass. The service
layer (`app/mariadb_catalog_service.py`) and the product form route are its only
callers; templates and JavaScript never re-derive this logic (AD-4, FR16).

The canonical form
------------------
A tag is a single free-form label. Canonical means, exactly:

- surrounding whitespace stripped,
- internal whitespace runs collapsed to one space,
- lowercase,
- at most `MAX_TAG_LENGTH` characters,
- never containing `TAG_SEPARATOR`.

Normalization only ever shortens or lowercases. It never rewrites the contents
of a tag: no slugging, no space-to-hyphen, no Unicode folding beyond
`str.lower()`. `'heat sink'` stays two words, because the operator's own
vocabulary IS the tag set — there is nothing to slug it for.

"Free-form" describes the VOCABULARY (nothing is pre-populated, no schema
constrains what a tag may say), not the storage. A canonical form is forced by
two invariants anyway: "a tag is unique per Product" is meaningless if `SSR`
and `ssr` are separate rows, and "filtering by a tag returns exactly the tagged
Products" is false if the filter is case-sensitive against values typed on
different days.

Blank is not an error
---------------------
Tags are optional and a Product may carry none. `''`, `'   '`, `','` and `None`
all mean "no tags": `normalize_tag` yields None and `parse_tag_list` yields an
empty list, never an exception. The only rejections are a caller-type fault (a
non-string that is not None), a tag longer than the column could store, and a
tag containing the separator.

The separator can never appear inside a tag
-------------------------------------------
The product form carries tags as ONE comma-separated string — the only shape
`request.form.to_dict()` round-trips — so a tag containing `,` could not
survive the round trip. `normalize_tag` therefore REJECTS it rather than
silently truncating or storing it.

Note what that does NOT protect: every field the form submits reaches
`parse_tag_list`, which splits FIRST, so a comma typed inside a tag is two
tags, not an error — `'1,000 lb rated'` is stored as `'1'` and `'000 lb rated'`.
That is the separator doing its job, and the only alternative is refusing a
field the operator can see nothing wrong with. The rejection guards the OTHER
caller shape: a list argument (`set_product_tags(id, ['a,b'])`), where a comma
means the caller split wrongly and splitting again would silently invent a tag
it never asked for.

Future extensibility:
--------------------
Nothing further is planned here. A tag rename, merge or delete, should one ever
be specified, would belong in the service — it is a decision about rows, not a
property of a tag string.
"""

from typing import List, Optional

# The one separator between tags in the operator's single form field.
TAG_SEPARATOR = ','

# Mirrors the product_tags.tag column width. A canonical tag longer than this
# could not be stored, so it is rejected here rather than truncated (silently
# or by the database).
MAX_TAG_LENGTH = 64

# How many tags one Product may carry. Not a storage limit — the table would
# hold any number — but a guard against a paste accident becoming hundreds of
# rows the operator then has to remove one form field at a time.
MAX_TAGS_PER_PRODUCT = 50

# Separator-and-whitespace budget per tag in the raw field, used only by the
# pre-split ceiling below. One separator plus room for the padding a person
# actually types around it (' , ', a trailing space, a stray tab).
MAX_FIELD_PADDING_PER_TAG = 8

# Ceiling on the raw tag field, checked BEFORE splitting it. Sized so no list
# of MAX_TAGS_PER_PRODUCT legal tags can hit it, however the operator spaces
# their commas.
MAX_TAG_FIELD_LENGTH = (
    MAX_TAG_LENGTH + MAX_FIELD_PADDING_PER_TAG) * MAX_TAGS_PER_PRODUCT


class InvalidTagError(ValueError):
    """
    Raised when a value cannot be normalized to a tag: a non-string input
    (other than None), a canonical result longer than `MAX_TAG_LENGTH`, a tag
    containing `TAG_SEPARATOR`, or a list carrying more than
    `MAX_TAGS_PER_PRODUCT` distinct tags. A plain `ValueError` subclass so this
    module stays free of any app/framework dependency; callers translate it if
    they need a domain error.

    Note that "normalizes to nothing" is NOT a failure — blank input yields
    None (see the module docstring).

    Its messages are written to be shown to the operator verbatim: the product
    form renders them on the `tags` field.
    """


def normalize_tag(value: Optional[str]) -> Optional[str]:
    """
    Return the canonical form of a single tag, or None when the value carries
    no tag.

    Steps: strip surrounding whitespace; collapse every internal whitespace run
    to one space; lowercase.

    Args:
        value: A tag as typed, or None.

    Returns:
        The canonical tag, or None when nothing is left after normalization
        (blank, whitespace-only, or None input).

    Raises:
        InvalidTagError: if `value` is neither a string nor None, if it
            contains TAG_SEPARATOR, or if the canonical result is longer than
            MAX_TAG_LENGTH.

    Examples:
        >>> normalize_tag('  SSR  Relay ')
        'ssr relay'
        >>> normalize_tag('   ') is None
        True
    """
    if value is None:
        return None
    if not isinstance(value, str):
        # Non-str input (int, list, bytes, Decimal, ...) is a caller-type
        # fault, not form data: every HTML form field arrives as a string.
        # Failing here rather than on a bare AttributeError from .split()
        # keeps this module's single failure signal honest.
        raise InvalidTagError(
            f'Tag must be a string or None, got '
            f'{type(value).__name__}: {value!r}.')

    if TAG_SEPARATOR in value:
        # Rejected, never split: see the module docstring. parse_tag_list
        # splits BEFORE calling here, so this only ever fires for a caller
        # that handed a whole list to the single-tag entry point.
        raise InvalidTagError(
            f"A tag cannot contain '{TAG_SEPARATOR}' — that is the separator "
            f'between tags.')

    # str.split() with no argument splits on runs of any whitespace and drops
    # empty pieces, so stripping and collapsing are one step.
    normalized = ' '.join(value.split()).lower()
    if not normalized:
        return None
    if len(normalized) > MAX_TAG_LENGTH:
        raise InvalidTagError(
            f'Tag is too long: {len(normalized)} characters '
            f'(max {MAX_TAG_LENGTH}).')
    return normalized


def parse_tag_list(value: Optional[str]) -> List[str]:
    """
    Return the canonical tags carried by a comma-separated string, in
    first-seen order (Story 3.3, FR16).

    De-duplication happens on the CANONICAL form, so "a tag is unique per
    Product" holds before the database is ever asked — `'SSR, ssr'` is one tag,
    not a uniqueness violation the operator has to decode from an error page.
    Blank entries are dropped rather than rejected, so trailing and doubled
    separators are ordinary typing noise.

    Args:
        value: The whole tag field as typed, or None.

    Returns:
        The canonical tags, de-duplicated, in the order first seen. Empty when
        the value carries no tag at all.

    Raises:
        InvalidTagError: if `value` is neither a string nor None, if the whole
            field is longer than MAX_TAG_FIELD_LENGTH, if any tag is longer
            than MAX_TAG_LENGTH, or if more than MAX_TAGS_PER_PRODUCT distinct
            tags are given.

    Examples:
        >>> parse_tag_list(' SSR, rectifier ,, ssr ')
        ['ssr', 'rectifier']
        >>> parse_tag_list(',')
        []
    """
    if value is None:
        return []
    if not isinstance(value, str):
        raise InvalidTagError(
            f'Tags must be a string or None, got '
            f'{type(value).__name__}: {value!r}.')

    # Bounded before the split, not after: the count check below runs on the
    # DE-DUPLICATED list, so a body of 'a,a,a,...' passes it however long it is
    # while still allocating one list element per separator on the way. The
    # ceiling is measured on the RAW string, which normalization has not
    # trimmed yet, so it budgets MAX_FIELD_PADDING_PER_TAG characters of
    # separator-and-whitespace noise per tag on top of the tags themselves —
    # more than any list a person types can carry. Padding beyond that is
    # refused as too long even though trimming would have shortened it; the
    # alternative is no ceiling at all.
    if len(value) > MAX_TAG_FIELD_LENGTH:
        raise InvalidTagError(
            f'The tag field is too long: {len(value)} characters (max '
            f'{MAX_TAG_FIELD_LENGTH}). At most {MAX_TAGS_PER_PRODUCT} tags of '
            f'{MAX_TAG_LENGTH} characters each are allowed.')

    tags: List[str] = []
    seen = set()
    for piece in value.split(TAG_SEPARATOR):
        tag = normalize_tag(piece)
        if tag is None or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)

    if len(tags) > MAX_TAGS_PER_PRODUCT:
        raise InvalidTagError(
            f'Too many tags: {len(tags)} (max {MAX_TAGS_PER_PRODUCT} per '
            f'product).')
    return tags


def format_tag_list(tags) -> str:
    """
    Return a tag list as the one comma-separated string the form field holds.

    The inverse of `parse_tag_list` for round-tripping stored tags back onto
    the edit form. Values are emitted as given — the caller passes canonical
    tags (everything stored is canonical), so nothing is re-normalized here.

    Args:
        tags: An iterable of canonical tags, or None.

    Returns:
        The tags joined by the separator and one space, or '' when there are
        none.

    Examples:
        >>> format_tag_list(['ssr', 'rectifier'])
        'ssr, rectifier'
        >>> format_tag_list(None)
        ''
    """
    if not tags:
        return ''
    return (TAG_SEPARATOR + ' ').join(tags)
