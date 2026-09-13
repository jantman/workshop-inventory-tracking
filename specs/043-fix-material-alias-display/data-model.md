# Data Model: Material Aliases

No schema change. This document records how the existing column is to be read and compared.

## MaterialTaxonomy (existing, `app/database.py`)

| Field | Type | Notes |
|-------|------|-------|
| `name` | `String(100)`, unique | Canonical material name |
| `level` | `Integer` 1–3 | 1 = category, 2 = family, 3 = material |
| `aliases` | `Text`, nullable | **Comma-separated** alternative names. Written as `', '.join(...)` by the admin form and as `','.join(...)` by seed/import data. `NULL` when there are none. |
| `aliases_list` | property (read/write) | Parsed form: split on `,`, strip each entry, drop empties. **The only sanctioned way to read aliases.** |

## Alias representation at each boundary

| Boundary | Representation after this change |
|----------|---------------------------|
| Database column | Unchanged: comma-separated text or `NULL` |
| `get_taxonomy_overview()` material node, `aliases` key | `list[str]`, from `aliases_list`, which is `[]` when there are none. Was: raw `str`, or `[]` for `NULL`. |
| Admin page (`taxonomy_node.html`) | `(aliases: A, B, C)`, or nothing if the list is empty |
| `GET /api/taxonomy` | `list[str]`, the same as before, now produced by the service instead of a post-processing step in the route |
| `GET /api/materials/hierarchy` | Unchanged raw string (out of scope, and nothing consumes it) |

## Alias identity (comparison rules)

Two aliases are **the same alias** when they are equal after trimming surrounding whitespace
and ignoring letter case. Each alias is compared as a whole; a fragment of an alias never
matches it.

| New alias | Existing data | Same? | Why |
|-----------|---------------|-------|-----|
| `Oilite` | alias `Oilite` | yes | exact match |
| `oilite` | alias `Oilite` | yes | case is ignored |
| ` Oilite ` | alias `Oilite` | yes | surrounding whitespace is trimmed |
| `Bronze` | alias `Sintered Bronze` | no | fragment, not a whole alias |
| `841` | alias `841 Bronze` | no | fragment, not a whole alias |
| `Carbon Steel` | material *named* `Carbon Steel` | yes, conflict | an alias may not equal any material's name (FR-007) |

## Validation rule

A new material's alias is refused if it is the same alias as:

- any existing material's name, or
- any alias of any existing material, active or inactive.

Both the live check and the on-save check apply this one rule, implemented once
(`_find_alias_conflict`).

Inactive materials are included because the current live check already includes them (it
filters only on `aliases IS NOT NULL`), and because a name reused by a reactivated material
would be just as ambiguous.
