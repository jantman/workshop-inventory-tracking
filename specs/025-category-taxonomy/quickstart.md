# Phase 1 — Validation guide

How to prove the feature works. Commands run from the repository root against the project
virtualenv, per the constitution.

## Prerequisites

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"   # nox needs python3.13 on PATH
```

Use the venv binaries by path (`venv/bin/nox`, `venv/bin/python`); do not source the activate
script.

## Automated gates

```bash
venv/bin/nox -s tests     # unit suite; sub-second, network blocked
venv/bin/nox -s e2e       # ~14 minutes warm — see the timeout note below
venv/bin/nox -s lint      # advisory
```

**The E2E session outlasts a 10-minute agent bash timeout.** Run it detached and poll:

```bash
nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

Budget 20 minutes if the environment is cold — it pulls the MariaDB image and installs
Playwright browsers.

### What the unit suite must prove

| Check | Requirement |
|---|---|
| Every path in `CATEGORY_PATHS` is already canonical, ≤ 3 segments, ≤ 512 chars, with its parent also present, no duplicates | [data-model.md](./data-model.md) invariants; FR-004, FR-013 |
| The branch paths parsed from `docs/category-taxonomy.md` equal `CATEGORY_PATHS` exactly | FR-019 — the record and the reference data cannot be left disagreeing |
| The keys parsed from the record's registry equal `SPECIFICATION_KEYS` | FR-019, SC-010 |
| No parent has more than 20 direct children; max depth 3 | SC-003 |
| `list_categories()` on an **empty** catalog returns all 142 branches | FR-012, SC-009 |
| `list_categories()` returns an in-use path the taxonomy does not name | FR-015, FR-017 |
| A path both offered and in use appears exactly once | FR-018 |
| `list_categories(prefix=…)` filters the union, not just the in-use half | contract |
| `category_tree()` yields `count: 0, in_taxonomy: true` for an unoccupied branch, and `in_taxonomy: false` for a typed-in path | [data-model.md](./data-model.md) state table |
| `list_specification_names()` on an empty catalog returns the record's keys | SC-010 |
| `rename_category` on an unoccupied branch still refuses | D4 — existing behavior must not regress |

### What the E2E suite must prove

Seed through `live_server.add_test_data`, not through the form — the form is not what is under
test here. Wait on observable state; no `wait_for_timeout`, no `networkidle`.

1. **Filing into an unoccupied branch.** With no product in `fasteners/machine screws & bolts/
   socket head cap`, open the add-product form and confirm the branch is offered by the
   datalist; save; confirm the stored path is that string exactly. Covers FR-012, FR-013,
   SC-008, SC-009.
2. **One branch, not two.** With a product already in a taxonomy branch, the browse page shows
   that branch once. Covers FR-018. Establish the list region with `expect(...)` before any
   `count()` — the tree is rendered server-side but the assertion is a negative one, and a
   negative assertion against a region that has not settled passes for the wrong reason.
3. **The rename control.** A branch with products shows Rename; an unoccupied branch does not.
   Covers D4.
4. **A path outside the tree still saves.** Covers FR-015.

## Manual validation

1. **Fresh eyes on the browse page.** `/products/categories` should read as the taxonomy, not
   as a list of what happens to be in use. Confirm the rewritten copy no longer claims there is
   "nothing here to set up".
2. **Filing a real product.** Take one of the products captured during the issue #80
   verification, file it, and confirm SC-008 holds: the branch is chosen without opening
   anything other than the screen being filed on.
3. **The three probes.** Confirm each is reachable in the datalist by typing a fragment:
   `socket head cap`, `lever`, `esp32`.

## Screenshots

`app/templates/product/categories.html` changes, so the documentation screenshots must be
regenerated and committed with the change:

```bash
venv/bin/nox -s screenshots_headless
venv/bin/nox -s screenshots_verify
```

Screenshots churn on every run for reasons unrelated to the change. **Review the diff and
commit only the images this feature actually altered** — a wholesale commit of the churn
destroys the review signal. `nox -s e2e` excludes screenshot tests, so an E2E run must leave
the working tree clean; if it does not, that is a bug in the run, not in this feature.

## Definition of done

- `nox -s tests` and `nox -s e2e` green.
- Every branch of `docs/category-taxonomy.md` selectable on the filing screen with no product
  in it (SC-009).
- No category path in the catalog that the record does not name, except paths that predate the
  tree (SC-006).
- The record, `app/utils/catalog_taxonomy.py` and the paths on products agree, with the first
  two enforced by test and the third visible on the browse page (FR-019).
