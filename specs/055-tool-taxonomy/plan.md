# Implementation Plan: Tool, Chemical and Mechanical Categories in the Default Taxonomy

**Branch**: `robot-army/issue-182-add-tool-categories-to-default-taxonomy` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/055-tool-taxonomy/spec.md` (approved by the owner 2026-09-27)

## Summary

Add the approved branches and specification keys to the shipped defaults:

- **124 new branches.** Three roots (`tools`, `adhesives & chemicals`, `mechanical`) with their
  subtrees, plus six leaves under `fasteners/pins & clips`.
- **35 new specification keys.**

The work is a data change in two places that a unit test keeps in exact agreement:

- `DEFAULT_CATEGORY_PATHS` / `DEFAULT_SPECIFICATION_KEYS` in `app/utils/catalog_taxonomy.py`;
- `docs/category-taxonomy.md`, the record.

The unit test's `ROOTS` constant grows from three roots to six. No schema change, no migration,
no new code path, no template or JavaScript change.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: None new. The data is two existing tuples of strings.

**Storage**: MariaDB, untouched. Categories are materialized paths on the product and the
taxonomy is a suggestion list, so no rows are written (025 design).

**Testing**:
- `nox -s tests`: `tests/unit/test_catalog_taxonomy.py` already enforces shape (canonical,
  ≤3 segments, sorted, parents present, ≤20 children) and record agreement.
- `nox -s e2e`: `tests/e2e/test_category_taxonomy.py` covers offering an unoccupied branch.
- Screenshots: `nox -s screenshots_headless`.

**Target Platform**: Linux server, LAN browser

**Project Type**: Server-rendered web application

**Performance Goals**: N/A. The suggestion list grows from 142 to 266 paths, and from 39 to 74
keys, on a single-user LAN app.

**Constraints**:
- The record parser in the unit test reads branch rows only under `## <root>` headings, and
  reads keys only from the registry table directly under `## Specification keys`, stopping at
  the first `###`. The record's new tables must keep those shapes, and the key-meaning table
  must sit under a `###` heading so it is not read as registry keys.
- Existing branches and keys are never renamed or removed (FR-003).

**Scale/Scope**: One module's two tuples, one document, one test constant, one screenshot.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| I. Simplicity First | ✅ Pure data additions to existing tuples. No new module, no loader change, no configuration. |
| II. Layered Architecture | ✅ No code path changes; the service already reads the tuples. |
| III. Exact Numerics | ✅ Not touched. |
| IV. Test Discipline | ✅ The existing shape and agreement tests cover the new data. The only test edit is `ROOTS`, which grows to six. One probe test is added: the new branches and keys are offered, and the `pins & clips` exclusion is gone. Run through `nox`. |
| V. MariaDB Source of Truth | ✅ No schema change; nothing written. |
| VI. Item History Invariants | ✅ Not touched (catalog side only). |
| Technology Constraints | ✅ Nothing new. |
| Screenshots gate | ⚠️→✅ No template, CSS or JS changes, so the gate does not formally apply. But `user-manual/category_tree.png` renders taxonomy branches and is not full-page, and `adhesives & chemicals` now sorts first, so the shot changes. Regenerate, commit only that file if it is the only real change (measure churn against a baseline), and pass `screenshots_verify`. |
| Threat model | ✅ N/A. |

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/055-tool-taxonomy/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── tasks.md          # /speckit-tasks
```

No `contracts/`: no endpoint, form or API changes shape.

### Source Code (repository root)

```text
app/utils/catalog_taxonomy.py        # DEFAULT_CATEGORY_PATHS, DEFAULT_SPECIFICATION_KEYS
docs/category-taxonomy.md            # the record: new root sections, fasteners edits, keys, scope
tests/unit/test_catalog_taxonomy.py  # ROOTS → six roots; probe test for new entries
docs/images/screenshots/user-manual/category_tree.png  # regenerated
```

**Structure Decision**: Existing files only.

## Complexity Tracking

None.
