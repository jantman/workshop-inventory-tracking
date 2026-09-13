# Quickstart: Validating the Alias Fix

## Prerequisites

- The repository `venv/` is present. Invoke binaries through it (`venv/bin/nox`); don't
  activate it.
- `python3.13` is on `PATH` for nox:
  `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`.

## 1. Unit tests

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
```

Expected: everything passes, including `tests/unit/test_material_aliases.py`, which covers:

- The overview node's `aliases` is a `list` for both stored separators, and `[]` when there
  are none (see [contract §1](contracts/admin-materials.md)).
- Every row of the conflict table in [contract §2](contracts/admin-materials.md) gets the same
  verdict from `validate_add_request` (live) and from `add_taxonomy_entry` (save).

## 2. E2E tests

The suite outlasts the Bash tool's 10-minute cap, so run it detached and wait for it to exit.
It takes about 14 minutes warm; allow 20 if the environment is cold.

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &
```

Expected: all pass, including:

- The new test that the seeded `304` node on `/admin/materials` reads
  `(aliases: 304 Stainless, SS304)`.
- `test_alias_conflict_prevention`, which is unchanged and still refused on the name
  `Carbon Steel`.
- `test_get_taxonomy_aliases_are_lists`, which is unchanged and shows `/api/taxonomy` output is
  the same as before.

Afterwards `git status` must be clean. The e2e session does not write screenshots.

## 3. Manual check against real data

1. Start the app against the real database and open `/admin/materials`.
2. Find `Oil Embedded Bronze`. It must read `(aliases: Oilite, Sintered Bronze, 841 Bronze)`.
3. Open **Add Material** under any family and type `Oilite` into Aliases. The field must be
   flagged as conflicting while you type. Submit anyway: the save must also be refused.
4. Replace the alias with `Bronze`. No alias conflict is reported. Cancel instead of saving,
   unless you actually want the material.

## Regression guard

```bash
grep -n "material.aliases or \[\]\|aliases.like(\|_normalize_taxonomy_aliases" app/
```

Must return nothing.
