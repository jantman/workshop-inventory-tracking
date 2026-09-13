# Implementation Plan: Fix Material Alias Display and Conflict Detection

**Branch**: `speckit/043-fix-material-alias-display` | **Date**: 2026-09-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/043-fix-material-alias-display/spec.md`

## Summary

`MaterialTaxonomy.aliases` is a comma-separated `Text` column. Three places read it as though
it were already a list of names, so each one iterates the string's characters:

1. `get_taxonomy_overview` (`app/mariadb_materials_admin_service.py:115`) puts the raw string
   into the tree. `taxonomy_node.html:17` then runs `|join(', ')` over the string, which
   produces `O, i, l, i, t, e, ...`. `/api/taxonomy` already works around this with
   `_normalize_taxonomy_aliases` (`app/main/routes.py:1291`). The admin page has no such fix.
2. `validate_add_request` (line 417), the live check behind `POST /admin/api/materials/validate`,
   runs `alias in [a.lower() for a in material.aliases]`. That tests the alias against single
   characters, so it only ever catches one-character aliases.
3. `_validate_add_request` (line 219), the on-save check, uses `aliases LIKE '%alias%'`, a
   substring match. It rejects `Bronze` because `Sintered Bronze` exists.

The fix is to read aliases in all three places through the parser the model already has,
`MaterialTaxonomy.aliases_list`, which splits on commas, trims each alias and drops empty
entries. Both validation paths will make their alias comparison through one small private
helper, so they cannot disagree again (FR-006). With the tree now carrying real lists, the
`/api/taxonomy` workaround is dead code and is removed. The template is already correct once it
receives a list, so no template, CSS or JS changes are needed.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x, SQLAlchemy 2.0.x (legacy `Query` API), Jinja2

**Storage**: MariaDB, table `material_taxonomy`, column `aliases` (`Text`, comma-separated). No schema change and no data migration (FR-008).

**Testing**: pytest through nox. Unit tests (`nox -s tests`) run against SQLite via the `test_storage` fixture. E2E tests (`nox -s e2e`) use Playwright against the live server.

**Target Platform**: Linux server, single user on the LAN

**Project Type**: Server-rendered Flask web application

**Performance Goals**: None. The taxonomy has a few hundred rows at most; the conflict check scans every row that has aliases, which is what the live check already does.

**Constraints**: The output of `/api/taxonomy` must not change (FR-009). Stored alias text must not change (FR-008).

**Scale/Scope**: Two app files change (`mariadb_materials_admin_service.py`, `main/routes.py`), plus one new unit-test file and one new e2e test.

No NEEDS CLARIFICATION items remain. See [research.md](research.md).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| I. Simplicity First | **Pass.** Reuses the existing `aliases_list` property instead of adding a parser. Adds one private helper, which has two callers and exists so the two checks cannot diverge. Deletes the `/api/taxonomy` workaround. No new dependency, configuration option or layer. |
| II. Layered Architecture | **Pass.** All changes are in the service layer and its route caller. No ORM queries are added to routes; the route change is a deletion. |
| III. Exact Numerics | Not applicable; aliases are text. |
| IV. Test Discipline | **Pass.** Unit tests cover the parsing and both validation paths. One e2e test covers the rendered page. E2E waits use `expect()` on server-rendered nodes, with no fixed waits. Both `nox -s tests` and `nox -s e2e` must pass. |
| V. MariaDB Source of Truth | **Pass.** No schema change, no Alembic revision, no data rewrite. |
| VI. Item Lifecycle Invariants | Not applicable; inventory items are not touched. |
| Workflow gates | **Pass.** Work happens on a feature branch and merges through a PR. No files under `app/templates/**`, `app/static/**` change, so screenshots do not need regenerating. |

**Post-design re-check**: still passes. The design in [research.md](research.md) and
[data-model.md](data-model.md) adds nothing beyond what this table lists.

## Project Structure

### Documentation (this feature)

```text
specs/043-fix-material-alias-display/
├── plan.md              # This file
├── research.md          # Phase 0: root cause and decisions
├── data-model.md        # Phase 1: alias representation and comparison rules
├── quickstart.md        # Phase 1: validation guide
├── contracts/
│   └── admin-materials.md   # Page display, validate endpoint, unchanged taxonomy API
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
app/
├── database.py                        # MaterialTaxonomy.aliases_list — reused, unchanged
├── mariadb_materials_admin_service.py # overview emits lists; both validators share one alias check
├── main/routes.py                     # remove _normalize_taxonomy_aliases and its call
└── templates/admin/taxonomy_node.html # unchanged (already correct for a list)

tests/
├── unit/test_material_aliases.py      # new: overview lists, live + save conflict rules
└── e2e/test_admin_materials.py        # add: seeded `304` renders "aliases: 304 Stainless, SS304"
```

**Structure Decision**: This is the existing single Flask app, so no new modules are needed.
The unit tests go in a new file named after the behavior, following the convention in
`tests/unit/`. The e2e test joins the existing admin-materials file so it can reuse
`AdminMaterialsPage`.

## Complexity Tracking

No violations. This section is intentionally empty.
