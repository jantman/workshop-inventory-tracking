"""
SQL text-safety utilities (Stories 3.1-4.3; DW-42, DW-77, DW-95).

This module is the single source of truth for the three questions a `LIKE`
pattern built from user text has to answer before it is built: how a literal
piece of text is escaped so it cannot act as a wildcard, whether the text can
reach the database intact and mean what it says at all, and how much of it a
pattern may carry.

"Single source of truth" is a statement about these rules, not yet a census of
the callers: the suggestion, product-search, scan-resolution and category-
rename patterns are built here, while `InventoryService.search_items` and
`app/mariadb_materials_admin_service.py` still interpolate user text into
`ilike()` with no escaping and no storability check at all. Those predate this
module and carry both defects it closes; they are named here, and carried as
deferred work, so that this module cannot be read as a census it is not.

It is a PURE module in the sense `app/utils/category.py` documents: standard
library only, no Flask/DB/framework imports, no I/O, and no failure signal of
its own — it raises nothing it defines.

Both functions take a `str` and only a `str`. That is a caller obligation, not
a validated argument: they are called per row and per keystroke on text that
has already been typed as a string by the layer above, and a `TypeError` out of
`None.replace` is a more useful report of a wiring mistake than a `False` that
quietly answers "unstorable" for an argument that was never text. The two
service guards test `isinstance(..., str)` themselves precisely because their
arguments are request-shaped and may legitimately be `None`.

Why it is its own module
------------------------
Every caller of these rules is somewhere that cannot import the others.
`app/mariadb_catalog_service.py` and `app/mariadb_inventory_service.py` sit on
opposite sides of the AD-1 service seam and must never import each other, and
`app/utils/category.py` — where the first escaper happened to land, because
Story 3.2 needed one — scopes itself to the canonical form of a materialized
category path, so escaping a vendor name has no business depending on it. The
result was three independent copies of one four-line function, agreeing today
and free to drift tomorrow (DW-42). A sibling pure module is the one seam all
three can reach, and it gives `is_storable_text` and SEARCH_QUERY_MAX_LENGTH a
home both services can reach too. For the NUL/surrogate guard that is what lets
one rule cover all seven fields of the one suggestions endpoint instead of two.
For the length bound the two callers are NOT the two halves of that endpoint:
they are `CatalogService.search_products` and
`InventoryService.get_field_value_suggestions`, the two places that build a
`LIKE` pattern out of a free-text query, one on each side of the seam. The
suggestions endpoint's catalog half arrives at its own bound a different way —
`normalize_category_path` (512) and `normalize_tag` (64) reject over-length
input before any pattern exists — and so is deliberately not a caller here.
None of this is a census either: the `ilike()` interpolations named in the
paragraph above are still outside every rule in this module, the length rule
now included.

Nothing here knows anything about a dialect: escaping is a property of the
`LIKE` grammar, and the storability and length rules below are stated against
the two backends this application runs (SQLite in the test suite, MariaDB in
production).
"""


# Longest run of operator text any caller here will build a LIKE pattern from.
# Not a cleaning rule and not a second copy of the scan trim (`MAX_SCAN_LENGTH`
# lives in app/utils/scan_input.py): it is a database-safety bound, because a
# LIKE pattern has a length limit that a search box or an autocomplete input
# has no reason to respect. SQLite raises `OperationalError: LIKE or GLOB
# pattern too complex` past SQLITE_MAX_LIKE_PATTERN_LENGTH (50000, and
# `escape_like_literal` doubles the query's metacharacters on the way there),
# which would break NFR8's "no scan text raises" on the only backend the suite
# runs. 4096 is far under that on both backends and coincides with the route's
# own scan cap, so no scan can reach it.
#
# It lives HERE rather than on either service because two callers ask it:
# `CatalogService.search_products`, which named it first, and
# `InventoryService.get_field_value_suggestions`, which was missing the length
# half of the same guard pair (DW-95). Those two sit on opposite sides of the
# AD-1 seam and must never import each other, so mirroring the number into the
# second one would recreate exactly the drift DW-42 closed for the escaper —
# two numbers agreeing today and free to disagree tomorrow, with the
# disagreement visible only as one endpoint accepting text the other refuses.
#
# The rule is INCLUSIVE, and every caller states it as `len(text) > this`: a
# query of exactly this many characters is still queried. Callers answer
# over-length text with the no-match answer rather than truncating it, for the
# reason `is_storable_text`'s callers do: a truncated pattern answers a
# DIFFERENT question — it returns rows that do not contain the query — and a
# plausible wrong answer is worse than an empty right one.
SEARCH_QUERY_MAX_LENGTH = 4096


# The character `escape_like_literal` prefixes to every LIKE metacharacter it
# finds. Every caller MUST pass it as the `escape=` argument of the LIKE the
# pattern is built for — a pattern escaped with a character the statement never
# declares is worse than no escaping at all, because the escape characters then
# match literally.
LIKE_ESCAPE_CHAR = '\\'


def escape_like_literal(value: str) -> str:
    r"""
    Return `value` with every `LIKE` metacharacter escaped against
    LIKE_ESCAPE_CHAR, so the text matches literally.

    So a query like `10%` matches the stored string `10%` instead of acting as
    a wildcard, and `power_supplies` cannot match `powerxsupplies`. The caller
    MUST pass LIKE_ESCAPE_CHAR as the `escape=` argument of the LIKE it builds
    (in the ORM: `column.like(pattern, escape=LIKE_ESCAPE_CHAR)`).

    The escape character is replaced FIRST and the two wildcards after it. Any
    other order re-escapes the escape characters this function just inserted,
    which doubles them and makes the pattern match a literal backslash where
    the caller meant a literal `%`.

    This is deliberately NOT idempotent: escaping an already-escaped value
    escapes its escape characters again, which is correct — the input is
    literal text, not a pattern. Callers pass raw text exactly once.

    Args:
        value: Literal text to embed in a LIKE pattern.

    Returns:
        The same text with `\`, `%` and `_` each prefixed by
        LIKE_ESCAPE_CHAR. Wildcards the CALLER wants live (the surrounding
        `%…%`) are concatenated by the caller, after this returns.

    Examples:
        Text carrying no metacharacter comes back untouched, and each of the
        two wildcards is prefixed where it stands:

        >>> print(escape_like_literal('plain text'))
        plain text
        >>> print(escape_like_literal('10%'))
        10\%
        >>> print(escape_like_literal('power_supplies'))
        power\_supplies

        The escape character is a metacharacter too, so a backslash the caller
        typed comes back doubled — otherwise it would escape whatever followed
        it in the pattern:

        >>> print(escape_like_literal('a\\b'))
        a\\b

        This next case is the FIRST/after rule above, made executable: the
        input's own backslash is doubled and the `%` is escaped exactly once,
        so the pattern matches those two characters literally. Escaping `%`
        first would instead double the backslash this function had just
        inserted and leave the `%` live as a wildcard.

        >>> print(escape_like_literal('\\%'))
        \\\%

        And applying the function twice escapes the escapes it inserted the
        first time — the deliberate non-idempotency above, seen from the
        output side rather than argued for in prose:

        >>> print(escape_like_literal(escape_like_literal('10%')))
        10\\\%

        The examples `print` rather than echo the value because a bare
        expression shows the `repr`, which doubles every backslash on its own
        account — and exactly which backslashes THIS function inserted is what
        the whole docstring is about. For the same reason this docstring is a
        RAW string: without the `r` prefix Python collapses every backslash
        pair above before doctest ever sees it, changing both the example
        inputs and the expected outputs, and `nox -s doctests` goes red for a
        reason that has nothing to do with this function. `is_storable_text`
        below is deliberately NOT raw — its prose spells `\\x00` and needs the
        escape — so do not "make the module consistent" in either direction.
    """
    return (
        value.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
        .replace('%', LIKE_ESCAPE_CHAR + '%')
        .replace('_', LIKE_ESCAPE_CHAR + '_')
    )


def is_storable_text(value: str) -> bool:
    """
    Whether `value` can reach the database intact and mean what it says
    (Story 4.3, NFR8). Two character classes make that false:

    - An UNPAIRED SURROGATE, which Python permits in a `str` but which has no
      UTF-8 encoding, so a driver raises `UnicodeEncodeError` when binding it
      as a parameter. A caller that must not raise on arbitrary text has to
      answer such a query without querying.
    - A NUL (`\\x00`). It binds without error, but SQLite's `LIKE` reads its
      pattern as a C string and stops at the first NUL, so the pattern that
      actually runs is a PREFIX of the one built — and since every pattern
      here is wrapped in `%…%`, a leading NUL degenerates to the bare `%` that
      matches EVERY row. Verified: with five products stored,
      `search_products('\\x00')` returned all five, and `'a\\x00b'` ran as
      `'%a'` and returned the rows *ending* in `a`. Both are the silent
      wrong-answer failure that `search_products`' length bound refuses to
      make by truncating; NUL was making it one character class over. The
      divergence is backend-specific in the direction the unit suite cannot
      see — PyMySQL escapes `\\0` in the emitted literal, so MariaDB compares
      the whole pattern and answers nothing.

    In both cases the honest answer is the no-match one, reached without a
    query: no value this application MEANS to store can equal or contain text
    that cannot be sent or cannot be compared whole.

    Read that as a premise about intent, not as an enforced invariant. Nothing
    on the write path refuses such text today — `create_product`, `add_item`
    and their update siblings never ask this question — so a row carrying a NUL
    can exist, and for that row this predicate answers "no match" by rule
    rather than by fact. It is deferred work, and enforcing the same rule at
    the write boundary is what would make the premise true. Every caller below
    is a READ, where "nothing matches" is at worst an under-answer; that is the
    reason the asymmetry is tolerable in the meantime and not the reason it is
    right.

    The surrogate half is observed under SQLite, the only backend any test in
    this repo runs the services against; PyMySQL encodes bound parameters to
    the connection charset and is expected to raise the same way, but that is
    inferred rather than measured, and the absent MariaDB coverage is an open
    ledger entry.

    Args:
        value: Text a caller is about to send to the database.

    Returns:
        True when the text can be bound and compared whole; False otherwise.
    """
    if '\x00' in value:
        return False
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True
