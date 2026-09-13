# Research: Fix Material Alias Display and Conflict Detection

No NEEDS CLARIFICATION items came out of the Technical Context. This document records the
root cause and the design decisions, with the alternatives that were rejected.

## Root cause

`MaterialTaxonomy.aliases` (`app/database.py:633`) is a `Text` column holding a comma-separated
string. `add_taxonomy_entry` writes it as `', '.join(aliases)`; seed and import data write it
as `','.join(...)`. The model already provides the correct reader, `aliases_list`
(`app/database.py:673`): split on `,`, strip each entry, drop the empty ones. Nothing in the
admin service uses it.

| Site | Code | Effect |
|------|------|--------|
| `get_taxonomy_overview`, `mariadb_materials_admin_service.py:115` | `'aliases': material.aliases or []` | The tree gets a `str`. Jinja's `join(', ')` iterates the characters, giving the reported `O, i, l, i, t, e, ,, , S, ...`. |
| `validate_add_request`, line 417 (live check, `POST /admin/api/materials/validate`) | `alias.lower() in [a.lower() for a in material.aliases]` | The list comprehension iterates characters, so only a one-character alias can ever match. Real duplicates pass. |
| `_validate_add_request`, lines 216–220 (on-save check, called by `add_taxonomy_entry`) | `MaterialTaxonomy.aliases.like(f'%{alias}%')` | A substring match. `Bronze` is refused because `Sintered Bronze` exists, and `841` because `841 Bronze` exists. |

`/api/taxonomy` returns correct lists only because `_normalize_taxonomy_aliases`
(`app/main/routes.py:1291`) converts the strings after `get_taxonomy_overview` returns. Its own
docstring describes the defect it is working around.

## Decision 1: Parse aliases with `MaterialTaxonomy.aliases_list`

- **Decision**: `get_taxonomy_overview` emits `'aliases': material.aliases_list`. Both
  validators read existing aliases through `aliases_list` as well.
- **Rationale**: It already exists and does exactly what FR-002 asks for (trim, drop empty
  entries). It handles both stored separators, `','` and `', '`. Using it means there is one
  parser.
- **Alternatives considered**:
  - *A Jinja filter that splits in the template.* Rejected: it fixes only the display, leaves
    the service returning a string, and would add a template change that requires regenerating
    screenshots.
  - *`to_dict()`'s `aliases.split(',')`.* Rejected: it does not trim, so `'Oilite, Sintered Bronze'`
    would come back as `['Oilite', ' Sintered Bronze']`. `to_dict()` is left alone because no
    caller of it for `MaterialTaxonomy` was found.
  - *Changing the column to JSON.* Rejected: it needs a schema change and a data migration to
    fix what is a read-side bug (FR-008, Principle I).

## Decision 2: One private helper for alias conflicts, shared by both validators

- **Decision**: Add `_find_alias_conflict(session, alias) -> Optional[str]` to
  `MariaDBMaterialsAdminService`. It returns a conflict message, or `None` if there is no
  conflict. After trimming the alias and lower-casing it for comparison, it checks two things:
  1. whether any material's **name** equals the alias, ignoring case, and
  2. whether any material's `aliases_list` contains the alias, ignoring case.

  `validate_add_request` appends the message to its `errors` list. `_validate_add_request`
  raises `ValidationError` with it. Each keeps its existing way of reporting; only the
  comparison is shared.
- **Rationale**: FR-006 requires both paths to reach the same verdict. They currently disagree
  in two different ways, and two copies of the logic would drift apart again. A helper with two
  callers is justified under Principle I.
- **Name comparison**: the live path uses `name.ilike(alias)`, and the save path uses
  `name == alias`. The two agree on MariaDB, whose default collation ignores case, but not on
  SQLite. The helper uses the case-insensitive form so the verdict is the same on both. This
  keeps FR-007 (a name conflict is still refused) and removes a difference between the two
  paths that would otherwise show up in unit tests.
- **Alternatives considered**:
  - *Fix each site in place.* Rejected: that keeps two implementations of one rule, which is
    exactly how they came to disagree.
  - *Match whole aliases in SQL* (`FIND_IN_SET`, or a `REGEXP` on comma boundaries). Rejected:
    it is MariaDB-specific (unit tests run on SQLite), it cannot trim whitespace inside the stored
    string, and it offers no advantage at this row count.

## Decision 3: Delete `_normalize_taxonomy_aliases`

- **Decision**: Remove the function and its one call in `api_taxonomy`.
- **Rationale**: Once `get_taxonomy_overview` emits lists, the function's `isinstance(aliases, str)`
  branch can never run. It split, trimmed and dropped empties exactly as `aliases_list` does, so
  the API output is identical (FR-009). The existing e2e test
  `tests/e2e/test_api_client.py::test_get_taxonomy_aliases_are_lists` guards that output.
- **Alternatives considered**: *Keep it as a safety net.* Rejected: dead code that implies the
  service might return a string is misleading, and simplicity rules out defensive code for a
  case that cannot occur.

## Decision 4: No template change

- **Decision**: Leave `app/templates/admin/taxonomy_node.html` unchanged.
- **Rationale**: `{% if category.aliases %}` is false for an empty list, and `join(', ')` over a
  list gives `Oilite, Sintered Bronze, 841 Bronze`, which satisfies FR-001 and FR-003. Leaving
  templates and static files untouched also means no screenshots need regenerating.

## Decision 5: Test placement

- **Unit tests** (`tests/unit/test_material_aliases.py`, new): build
  `MariaDBMaterialsAdminService(test_storage)` the way `tests/unit/test_clock_basis.py:154` does,
  seed `MaterialTaxonomy` rows directly, and assert:
  - The overview emits lists, trimmed and without empty entries.
  - Both the `','` and `', '` separators work.
  - A material without aliases gets `[]`.
  - The spec's User Story 2 cases (exact, case, whitespace, fragment, name) give the same result
    through both `validate_add_request` and `add_taxonomy_entry`.
- **E2E test** (added to `tests/e2e/test_admin_materials.py`): the seeded material `304` has
  aliases stored as `304 Stainless,SS304`, with no space after the comma. The test asserts that
  its tree node renders `(aliases: 304 Stainless, SS304)`. The page is server-rendered, so
  `expect(locator).to_have_text(...)` after `goto()` is the complete wait. There is no JavaScript
  region to wait for and no fixed delay.
- **Rationale**: Unit tests cover the rules cheaply. A single e2e test proves the page, which is
  where the reported bug appears. The conflict cases do not need e2e coverage, because the
  existing `test_alias_conflict_prevention` already exercises the form path end to end.

## Not addressed (as the spec's Assumptions say)

- `/api/materials/hierarchy` (`app/main/routes.py:1409`) still returns the raw string. No
  consumer reads `aliases` from it (`app/static/js` contains no reference).
- Duplicate aliases already in the database are neither detected nor repaired.
