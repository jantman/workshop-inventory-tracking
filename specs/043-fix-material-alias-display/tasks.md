---

description: "Task list for 043: fix material alias display and conflict detection"
---

# Tasks: Fix Material Alias Display and Conflict Detection

**Input**: Design documents from `specs/043-fix-material-alias-display/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/admin-materials.md](contracts/admin-materials.md), [quickstart.md](quickstart.md)

**Tests**: Included. FR-010 requires them and constitution Principle IV requires behavior changes to land with tests. Write each story's tests first and confirm they fail against the current code.

**Organization**: Tasks are grouped by user story. The two stories touch different methods of the same service file, and their tests share one new test file, so they run one after the other rather than in parallel.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)

## Conventions for every task

- Invoke nox through the repository venv, with Python 3.13 on `PATH`:
  `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s <session>`. Never run `pytest` directly.
- Keep the surrounding style: legacy `session.query(...)`, type hints on new methods, no reformatting of untouched lines.
- Read aliases only through `MaterialTaxonomy.aliases_list` (`app/database.py:673`), never by iterating `MaterialTaxonomy.aliases`.

---

## Phase 1: Setup

None. The project, dependencies and test fixtures already exist, and no schema change is needed.

## Phase 2: Foundational

None. `MaterialTaxonomy.aliases_list` already exists and is the only shared building block. Neither story is blocked by the other.

---

## Phase 3: User Story 1 - Read a material's aliases on the materials admin page (Priority: P1) 🎯 MVP

**Goal**: `/admin/materials` shows `(aliases: Oilite, Sintered Bronze, 841 Bronze)` instead of one entry per character.

**Independent Test**: With a material whose aliases are stored as `304 Stainless,SS304`, the admin page's node for it reads `(aliases: 304 Stainless, SS304)`, and `get_taxonomy_overview()` returns a `list` for that node's `aliases`.

### Tests for User Story 1 ⚠️ write first, confirm they fail

- [X] T001 [P] [US1] Create `tests/unit/test_material_aliases.py` with:
  - A module docstring naming feature 043.
  - `pytestmark = pytest.mark.unit`.
  - An `admin` fixture returning `MariaDBMaterialsAdminService(test_storage)`, the pattern at `tests/unit/test_clock_basis.py:154`.
  - A `seed(admin, *rows)` helper. Each row is a dict of `MaterialTaxonomy` column values. The helper inserts rows directly through `admin.Session()`, so aliases can be stored exactly as given, bypassing validation, and it commits and closes the session.
  - A `find_node(overview, name)` helper that walks the `children` lists and returns the node dict with that `name`.

  Then add `class TestOverviewAliases`. Seed a level-1 category `Alias Test Metals` (no parent), a level-2 family `Alias Test Bronzes` (parent `Alias Test Metals`), and these level-3 materials under that family. Call `admin.get_taxonomy_overview(include_inactive=True)` and assert:
  - (a) `Oil Embedded Bronze`, aliases `'Oilite, Sintered Bronze, 841 Bronze'`, gives `['Oilite', 'Sintered Bronze', '841 Bronze']`.
  - (b) `Test 304`, aliases `'304 Stainless,SS304'` (no space), gives `['304 Stainless', 'SS304']`.
  - (c) `Test Stray`, aliases `'Oilite2,, Sintered Two ,'`, gives `['Oilite2', 'Sintered Two']`.
  - (d) `Test Single`, aliases `'TIM'`, gives `['TIM']`, not `['T', 'I', 'M']`.
  - (e) `Test None`, aliases `None`, gives `[]`.
  - (f) `Test Inactive`, `active=False`, aliases `'Old Name, Older Name'`, gives `['Old Name', 'Older Name']`.

  One test method per case, named for what it proves. Cases (a), (b), (d) and (f) must fail before T003.

- [X] T002 [P] [US1] Add `test_material_aliases_render_as_whole_names` to `tests/e2e/test_admin_materials.py`, marked `@pytest.mark.e2e`, after `test_alias_conflict_prevention`:
  - Use `AdminMaterialsPage(page, live_server.url).navigate()`.
  - Assert with `expect(page.locator('.taxonomy-node[data-name="304"] > div small').first).to_have_text("(aliases: 304 Stainless, SS304)")`. The seed row at `tests/e2e/test_server.py:365` stores `304 Stainless,SS304`. The page is server-rendered, so this `expect` is the whole wait. Do not add `wait_for_timeout`, `time.sleep` or `networkidle` (CLAUDE.md, "Writing e2e tests").
  - Add a second assertion: `expect(page.locator('.taxonomy-node[data-name="Carbon Steel"] > div small')).to_have_count(0)` if `Carbon Steel` is seeded with no aliases. Confirm this against `tests/e2e/test_server.py` first, and pick another seeded material with `aliases` empty if not. This covers FR-003. It is safe as a negative assertion because the first `expect` has already established that the tree rendered.

### Implementation for User Story 1

- [X] T003 [US1] In `app/mariadb_materials_admin_service.py`, in `get_taxonomy_overview` (line 115), change `'aliases': material.aliases or [],` to `'aliases': material.aliases_list,`. T001 should now pass. Make no other change in this method.
- [X] T004 [US1] In `app/main/routes.py`, delete `_normalize_taxonomy_aliases` (lines 1291–1305) and, in `api_taxonomy`, delete the comment block and `_normalize_taxonomy_aliases(taxonomy)` call (lines 1332–1336). Depends on T003: without it `/api/taxonomy` would start returning strings. Then run `grep -rn "_normalize_taxonomy_aliases" app/ tests/`; it must return nothing. If a test references it, delete that test only if it exercised the function directly. A test of `/api/taxonomy` output stays.
- [X] T005 [US1] Run `nox -s tests`. All tests must pass, including every `TestOverviewAliases` case.

**Checkpoint**: User Story 1 is complete. The reported bug is fixed and shippable on its own. The e2e test (T002) is run in the final phase with the whole suite.

---

## Phase 4: User Story 2 - Alias conflicts are judged on whole aliases (Priority: P2)

**Goal**: The live check (`validate_add_request`) and the save check (`_validate_add_request`, via `add_taxonomy_entry`) apply one rule: a new alias conflicts if, trimmed and compared case-insensitively, it equals an existing material's name or an existing whole alias ([data-model.md § Validation rule](data-model.md#validation-rule)).

**Independent Test**: With `Oil Embedded Bronze` holding `Oilite, Sintered Bronze, 841 Bronze`, the alias `Oilite` is refused by both paths and `Bronze` is accepted by both.

### Tests for User Story 2 ⚠️ write first, confirm they fail

- [ ] T006 [US2] In `tests/unit/test_material_aliases.py` (same file as T001, so not parallel with it), add `class TestAliasConflicts`.
  - **Seed:** via `seed(...)`, the category and family from T001; material `Oil Embedded Bronze` with aliases `'Oilite, Sintered Bronze, 841 Bronze'`; and a material *named* `Alias Test Carbon Steel` with no aliases.
  - **Cases:** use one `@pytest.mark.parametrize('alias, conflicts', [...])` with these rows:

    | Alias | Conflicts? |
    |---|---|
    | `'Oilite'` | `True` |
    | `'OILITE'` | `True` |
    | `' Oilite '` | `True` |
    | `'Sintered Bronze'` | `True` |
    | `'Bronze'` | `False` |
    | `'841'` | `False` |
    | `'Alias Test Carbon Steel'` | `True` |
    | `'alias test carbon steel'` | `True` |

  - **Request:** for each row, build `TaxonomyAddRequest(name=f'Conflict Probe {i}', level=3, parent='Alias Test Bronzes', aliases=[alias])`, with a unique name per row (use the parametrize index or derive it from the alias).
  - **Live-path test:** `ok, errors = admin.validate_add_request(req)`. Assert `any('conflicts' in e for e in errors) == conflicts`.
  - **Save-path test:** `ok, message = admin.add_taxonomy_entry(req)`. Assert `ok is (not conflicts)`. When `conflicts` is true, also assert `'conflicts' in message`.
  - **Agreement test (FR-006):** for each row, the two paths' refusals must agree.

  Pre-fix, the live path fails the `True` rows except the name rows, and the save path fails `'Bronze'`, `'841'` and the lowercase name row on SQLite.

### Implementation for User Story 2

- [ ] T007 [US2] In `app/mariadb_materials_admin_service.py`:
  - Change the import to `from sqlalchemy import create_engine, func`.
  - Add a private method on `MariaDBMaterialsAdminService`, placed just above `_validate_add_request`: `def _find_alias_conflict(self, session, alias: str) -> Optional[str]:`. Its docstring cites data-model.md's validation rule and says that both validators call it so they cannot disagree (FR-006).
  - Behavior:
    - `wanted = alias.strip()`. If it is empty, return `None`.
    - Query `session.query(MaterialTaxonomy).filter(func.lower(MaterialTaxonomy.name) == wanted.lower()).first()`. If there is a match, return `f"Alias '{wanted}' conflicts with existing material '{match.name}'"`. Use `func.lower`, not `ilike`: `ilike` treats `%` and `_` in an alias as wildcards.
    - Then iterate `session.query(MaterialTaxonomy).filter(MaterialTaxonomy.aliases.isnot(None)).all()`. If `wanted.lower()` is in `[a.lower() for a in material.aliases_list]`, return `f"Alias '{wanted}' conflicts with existing alias for '{material.name}'"`.
    - Otherwise return `None`.
  - Keep the existing live-path wording. `add_material.html:196` filters errors on `'alias'`/`'conflicts'`, and `test_alias_conflict_prevention` asserts `"conflicts"`.
- [ ] T008 [US2] In `app/mariadb_materials_admin_service.py`, in `validate_add_request`, replace the body of the `if request.aliases:` block (lines 399–419, from the name query through the `break`) with a loop that calls `self._find_alias_conflict(session, alias)` for each alias and appends any non-`None` result to `errors`. Remove the stale "JSON array searching" comment.
- [ ] T009 [US2] In `app/mariadb_materials_admin_service.py`, in `_validate_add_request`, replace the `if request.aliases:` block (lines 209–220, the `MaterialTaxonomy.name == alias` query and the `aliases.like(f'%{alias}%')` query) with a loop that calls `self._find_alias_conflict(session, alias)` and raises `ValidationError(conflict)` on the first non-`None` result. The error still reaches the user through the `flash(message, 'error')` in `app/admin/routes.py:94`.
- [ ] T010 [US2] Run `nox -s tests`. All must pass, including every `TestAliasConflicts` row and all of `TestOverviewAliases`.

**Checkpoint**: Both stories are complete. The live and save checks give the same verdicts.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T011 Run the regression guard from [quickstart.md](quickstart.md): `grep -n "material.aliases or \[\]\|aliases.like(\|_normalize_taxonomy_aliases" app/` must return nothing. Also run `grep -n "in \[a.lower() for a in material.aliases\]" app/`, which must return nothing.
- [ ] T012 Run the e2e suite detached, because it outlasts the Bash tool's 10-minute cap: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup venv/bin/nox -s e2e > <scratchpad>/e2e.log 2>&1 &`. Let the harness report when it exits instead of polling, and allow up to 20 minutes. All tests must pass, including T002's new test, the unchanged `test_alias_conflict_prevention`, and `tests/e2e/test_api_client.py::test_get_taxonomy_aliases_are_lists`, which guards FR-009. Then `git status` must show no changes the run made itself; the e2e session writes no screenshots.
- [ ] T013 Confirm that no file under `app/templates/**`, `app/static/css/**` or `app/static/js/**` changed (`git diff --name-only main... -- app/templates app/static`), which means no screenshots need regenerating. If one did change, run `nox -s screenshots_headless` and `nox -s screenshots_verify` and commit the results.
- [ ] T014 Hand the manual check in [quickstart.md § 3](quickstart.md) to the user: `Oil Embedded Bronze` on their real database, plus the `Oilite` and `Bronze` add-form checks. It needs their live data, so it is not automated here.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup and Foundational (Phases 1–2)**: empty.
- **US1 (Phase 3)**: can start immediately.
- **US2 (Phase 4)**: independent of US1 in behavior. It runs after US1 only because T006 adds to the file T001 creates and T007–T009 edit the same service file as T003.
- **Polish (Phase 5)**: after both stories.

### Task graph

```text
T001 ─┐
      ├─> T003 ─> T004 ─> T005 ─> T006 ─> T007 ─> T008 ─> T009 ─> T010 ─> T011 ─> T012 ─> T013 ─> T014
T002 ─┘                                                                              (T002 runs here)
```

### Within each story

- Tests first (T001/T002, then T006), confirmed failing.
- Service change, then its route cleanup (T003 before T004).
- Shared helper before its callers (T007 before T008 and T009).

### Parallel Opportunities

- **T001 ∥ T002**: different files (`tests/unit/test_material_aliases.py` and `tests/e2e/test_admin_materials.py`), no shared state.
- Nothing else. Every remaining task edits `app/mariadb_materials_admin_service.py` or `tests/unit/test_material_aliases.py`, or depends on one that does.

## Parallel Example: User Story 1

```bash
# Write both US1 tests together:
Task: "T001 unit tests for overview alias lists in tests/unit/test_material_aliases.py"
Task: "T002 e2e test that seeded 304 renders whole aliases in tests/e2e/test_admin_materials.py"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. T001–T005: the reported bug is fixed and unit-tested.
2. **Stop and validate**: run T012's e2e suite, and T014 against real data if desired.
3. Can be shipped alone. US2 is a separate, smaller PR if you want it split out.

### Incremental Delivery (recommended: one PR)

1. US1 (T001–T005), then US2 (T006–T010), then Polish (T011–T014).
2. The stories share a root cause and a file, so one PR on `speckit/043-fix-material-alias-display` is the simpler review. Commit once per story checkpoint.

## Notes

- 14 tasks: 5 for US1, 5 for US2, 4 for polish.
- The template needs no change. If you find yourself editing `taxonomy_node.html`, the service is not returning a list; fix it there.
- Existing duplicate aliases in the real database are out of scope (spec Assumptions).
