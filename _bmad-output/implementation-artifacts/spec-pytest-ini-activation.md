---
title: 'Activate pytest.ini and reconcile the marker registry'
type: 'chore'
created: '2026-07-28'
status: 'done'
baseline_revision: '4fff157a973f36f5c79f82f72565a5a63850fb75'
final_revision: 'cb86048ea7b89f087c0aac2d156c7eddcfe1018c'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** `pytest.ini:1` declares `[tool:pytest]` — a `setup.cfg` section name — so pytest reports `configfile: pytest.ini` while reading nothing from it; `testpaths`, `addopts`, `markers`, `norecursedirs` and `minversion` are all inert (DW-102). Consequently `--strict-markers` is declared but not enforced, and the `screenshot` marker used 16 times in `tests/e2e/test_screenshot_generation.py` is registered nowhere (DW-105), so simply renaming the section would turn `nox -s screenshots` red.

**Approach:** Rename the section to `[pytest]`, and in the same pass make `pytest.ini` the single source of truth for markers (dropping the never-used `database` marker, keeping `screenshot`), remove the now-duplicate `pytest_configure` registration from `tests/conftest.py`, and repair `norecursedirs` so activating it does not lose pytest's built-in exclusions. Then correct the stale "pytest.ini is inert" claims in `noxfile.py` docstrings and `_bmad-output/project-context.md`.

## Boundaries & Constraints

**Always:**
- Every marker used anywhere in `tests/` must be registered in `pytest.ini`'s `markers` list — `unit`, `integration`, `e2e`, `screenshot` are all in active use; `slow` is registered today and stays.
- `norecursedirs` must retain pytest's built-in exclusions (`*.egg .* _darcs build CVS dist node_modules venv {arch}`) in addition to `migrations` — setting the key *replaces* the defaults, and dropping the `.*` pattern would expose `.nox/`, `.git/` and `.claude/skills/**/scripts/tests/test_*.py` to collection.
- Marker registration lives in exactly one place after this change (`pytest.ini`), not two.
- All existing nox sessions keep their explicit command-line flags and path arguments; do not move flags out of `noxfile.py` into `addopts`.

**Block If:**
- A nox session fails for a reason that cannot be fixed inside the files named in the Code Map (i.e. the activation exposes a genuine pre-existing test defect requiring product/behavior decisions).

**Never:**
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md` — the orchestrator records resolution.
- Do not change the `--doctest-modules app/utils` path argument in `noxfile.py::doctests`; it remains load-bearing.
- Do not add `--doctest-modules` or any per-session flag to `addopts`.
- Do not "fix" unrelated test failures or reformat files beyond the changes described here.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Config is read | `pytest --collect-only` from repo root | Header shows `configfile: pytest.ini` **and** a `testpaths: tests` line | No error expected |
| Strict markers enforced | A test decorated `@pytest.mark.typo` | Collection **errors** with `'typo' not found in 'markers' configuration option` | Error is the correct outcome |
| Registered marker set | `pytest --markers` | Lists `unit`, `integration`, `e2e`, `slow`, `screenshot`; each appears exactly once | No error expected |
| `database` marker gone | `pytest --markers` | `database` is absent (used by no test) | No error expected |
| Screenshot selection still works | `nox -s screenshots_headless` | The 16 `@pytest.mark.screenshot` tests are selected and run | No `PytestUnknownMarkWarning`, no strict-marker error |
| No-path sessions confined | `nox -s tests` / `coverage` / `e2e` (no path arg) | Collection confined to `tests/` via `testpaths`; same test set as before | No error expected |
| Doctest session unaffected | `nox -s doctests` | Explicit `app/utils` arg overrides `testpaths`; only `app/utils` doctests run | No error expected |

</intent-contract>

## Code Map

- `pytest.ini` -- the whole point: section header rename plus `markers` and `norecursedirs` repair.
- `tests/conftest.py:199-216` -- `pytest_configure` registers `unit`/`e2e`/`slow`/`integration` via `addinivalue_line`; becomes a duplicate registry once the ini is live. Remove it (and the vestigial `pytest_plugins = []` comment block header stays coherent).
- `noxfile.py:48-51` -- `doctests` docstring paragraph asserting pytest.ini reads nothing; now false.
- `noxfile.py:133-139` -- `integration` session comment asserting "pytest.ini's testpaths never applies"; now false.
- `_bmad-output/project-context.md:55` -- Testing Rules bullet stating pytest.ini is inert and `--strict-markers` is not in force; now false and must be rewritten.
- `tests/e2e/test_screenshot_generation.py` -- the only consumer of `@pytest.mark.screenshot` (16 uses); no edits expected, it is the regression target.
- `tests/integration/conftest.py:88-110` -- `pytest_collection_modifyitems` structurally applies the `integration` marker; must keep working (marker stays registered).

## Tasks & Acceptance

**Execution:**
- [x] `pytest.ini` -- change the section header from `[tool:pytest]` to `[pytest]`; remove `database` from `markers`; replace `norecursedirs` with pytest's default list plus `migrations` -- activates the file without silently narrowing collection exclusions.
- [x] `tests/conftest.py` -- delete the `pytest_configure` function and its four `addinivalue_line` marker calls (keep every other hook and fixture, including `pytest_runtest_makereport`) -- `pytest.ini` is now the single marker registry; leaving both would double-register.
- [x] `noxfile.py` -- rewrite the `doctests` docstring paragraph and the `integration` inline comment that describe pytest.ini as inert, so they state the current truth (the explicit path args remain load-bearing for scoping, but for their own reasons) -- stale comments about a fixed defect are actively misleading.
- [x] `_bmad-output/project-context.md` -- rewrite the Testing Rules markers bullet: markers are registered in `pytest.ini`, `--strict-markers` *is* in force, `addopts`/`testpaths` *do* apply -- the file currently documents the bug as the rule.
- [x] Run the full verification matrix below and fix any fallout that lands inside the Code Map files -- activation turns on five settings at once and the acceptance bar is green sessions, not just a clean diff.

**Acceptance Criteria:**
- Given the renamed section, when `nox -s tests` runs, then it passes with the same test count as before the change and pytest's header reports `testpaths: tests`.
- Given `--strict-markers` is now in force, when `nox -s coverage`, `nox -s doctests`, `nox -s e2e` and `nox -s screenshots_headless` run, then all pass and none emits a `PytestUnknownMarkWarning` or a strict-marker collection error.
- Given `tests/conftest.py` no longer registers markers, when `pytest --markers` runs, then `unit`, `integration`, `e2e`, `slow` and `screenshot` each appear exactly once and `database` does not appear.
- Given the repaired `norecursedirs`, when collection runs from the repo root with no path argument, then no file under `.claude/`, `.nox/`, `venv/` or `migrations/` is collected.
- Given the documentation edits, when `noxfile.py` and `_bmad-output/project-context.md` are read, then no sentence claims `pytest.ini` is unread, that `addopts`/`testpaths` do not apply, or that `--strict-markers` is not enforced.

## Spec Change Log

## Review Triage Log

### 2026-07-28 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 1, low 8)
- defer: 1: (high 0, medium 1, low 0)
- reject: 9
- addressed_findings:
  - `[medium]` `[patch]` Nothing asserted that the ini was actually being read — the defect class this story exists to fix was silent for the file's entire life and got written into `project-context.md` as intended behaviour. Added `tests/unit/test_pytest_config.py`: six tripwire tests asserting `inipath` is `pytest.ini`, `testpaths == ["tests"]`, `--strict-markers`/`--strict-config` are in force, all five markers are registered, and `norecursedirs` retains `.*`/`venv`/`migrations`.
  - `[low]` `[patch]` The newly-live `--color=yes` forced ANSI escapes into every piped/captured run and broke this spec's own `pytest --markers | grep -E '^@pytest\.mark\.'` verification command (`^` never matched, so an empty result read as a pass). Removed it from `addopts`; pytest's default auto-detection keeps colour interactively and drops it in CI/nohup logs.
  - `[low]` `[patch]` A misspelled key in `pytest.ini` would still be silently ignored — the same failure class as the `[tool:pytest]` header. Added `--strict-config` to `addopts`.
  - `[low]` `[patch]` `python_classes = Test* *Test` was a newly-live *widening* of class collection beyond pytest's default, matched nothing in the repo, and contradicted `project-context.md`'s Layout bullet. Narrowed to `Test*`; collection verified byte-identical.
  - `[low]` `[patch]` `pytest_plugins = []` was left behind as an orphaned no-op, and `pytest_plugins` in a non-top-level conftest is a documented pytest error (`_check_non_top_pytest_plugins`) — safe today only because `testpaths` makes `tests/conftest.py` an initial conftest. Deleted it.
  - `[low]` `[patch]` The `norecursedirs` comment warned that the key replaces pytest's defaults but never said which entries were the defaults and which were project extras, defeating the audit it existed to enable, and overstated the risk (`.git/` holds no collectible `.py`). Rewrote it to quote the default list verbatim and name the three extras; reordered the value to match.
  - `[low]` `[patch]` The shipped `norecursedirs` deviated from the Design Notes target by adding `*.egg-info` and `__pycache__` with no record. Deviation is deliberate (preserves the pre-existing file's entries; both are inert for collection since `python_files` only ever matches `.py`) and is now documented in the file itself and here.
  - `[low]` `[patch]` `_bmad-output/project-context.md` documented the new mechanism but none of its consequences, and claimed flatly that command-line flags "override" the ini — false for counting flags, where each session's `-v` stacks with the ini's `--verbose` to give `-vv`. Added a dedicated bullet covering suppressed warning summaries (and how to see them), `--strict-config`, and add-vs-override semantics.
  - `[low]` `[patch]` `_bmad-output/project-context.md`'s Layout bullet omitted `tests/integration/` and restated collection globs that the now-live ini owns. Updated to name all three tiers, both file globs, and `norecursedirs` as the exclusion mechanism.
  - `[low]` `[reject→noted]` Both DW-105 and this spec's I/O matrix say "16 `@pytest.mark.screenshot` tests"; the true count is **15** — one of the 16 grep hits is prose in the module docstring of `tests/e2e/test_screenshot_generation.py`. Verified by collection (`15 tests collected`) and by the session itself (14 passed + 1 skipped). The figure sits inside the read-only `<intent-contract>`, so it is corrected here rather than edited there.

Rejected (noise or out of scope): a claimed fallback need for `pytest_configure` when pytest is invoked with `-c other.ini` (contradicts the contract's single-source-of-truth constraint, and the project rule is nox-only); dropping the unused `slow` marker (the contract explicitly keeps it); rewriting the five stale "pytest.ini is inert" sentences in the completed `spec-pure-util-doctest-session.md` (historical record, not living documentation); the still-`open` status of DW-102/DW-105 in the ledger (the orchestrator owns that, and this run is forbidden from editing it); the `norecursedirs` acceptance criterion being shadowed by `testpaths` (true of the AC's wording, but the setting was verified separately with an explicit-path collection); "a future test file outside `tests/` would be silently uncollected" (that is what `testpaths` is for); the untracked status of this spec file; and two Blind Hunter claims that `nox -s e2e`, `coverage` and `screenshots_headless` were never run — all three were run green in this session, and the regenerated screenshots were reverted.

### 2026-07-28 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 1, low 5)
- defer: 1: (high 0, medium 1, low 0)
- reject: 9
- addressed_findings:
  - `[medium]` `[patch]` The workaround this change itself documented for inspecting suppressed warnings — `--override-ini="addopts=--tb=short"` — turned two of its own tripwire tests red, because `--override-ini` *replaces* the whole option string and so silently drops `--strict-markers`/`--strict-config`. Reproduced (`2 failed, 4 passed`). The documented command now repeats the flags it must keep (`--override-ini="addopts=--verbose --tb=short --strict-markers --strict-config"`, verified `7 passed`), and both `project-context.md` and the test module's docstring state why replacement semantics make this necessary.
  - `[low]` `[patch]` `test_norecursedirs_keeps_the_builtin_exclusions` guarded 3 of the 12 entries whose preservation is the entire point of restating the list — deleting `*.egg`, `_darcs`, `build`, `CVS`, `dist`, `node_modules`, `{arch}`, `*.egg-info` or `__pycache__` left it green. Now asserts pytest's full default set (confirmed verbatim against `_pytest.main.pytest_addoption`) plus the three project extras, both as named module constants.
  - `[low]` `[patch]` `test_every_marker_used_by_the_suite_is_registered` asserted a hardcoded five-name literal and never scanned anything, so the case its own docstring used to justify it — a *new* marker added tomorrow — slipped straight through. Split in two: the literal assertion kept under an accurate name (`test_markers_selected_by_nox_sessions_are_registered`), plus a new `test_every_marker_used_in_the_suite_is_registered` that scans `tests/**/*.py` for marker applications and diffs them against the live registry (which at runtime carries pytest's and the plugins' markers too, so builtins need no allowlist).
  - `[low]` `[patch]` `test_pytest_ini_is_the_active_configfile` asserted only `inipath.name == "pytest.ini"`, which any `pytest.ini` anywhere on disk satisfies — including one shadowing the real file. Now compares against `pytestconfig.rootpath / "pytest.ini"`.
  - `[low]` `[patch]` The `norecursedirs` rationale was inverted in both `pytest.ini` and the test docstring: they claimed dropping `.*` would expose `.nox/` "to any collection run given an explicit path", but an explicitly named directory *bypasses* `norecursedirs` (verified in a scratch tree: `pytest .nox` collects, `pytest .` does not). Reworded to name the real trigger (`pytest .`, i.e. recursion from the repo root) and to record that `testpaths = tests` keeps every nox session away from the root, making the setting defence in depth rather than load-bearing.
  - `[low]` `[patch]` The new "how flags combine" rule in `project-context.md` was wrong for store-type options: it said per-session flags "extend" `addopts`, when only counting options accumulate — `--tb=short` sits in `addopts` *and* in five sessions, and the command-line value simply wins. Rewritten to separate counting options, store options and path arguments, and to state that a store-type flag in `addopts` sets an overridable default rather than composing.

Deferred (appended to the ledger as DW-238): `--disable-warnings` went from inert to enforced by this activation, so every session now hides its warning detail — including three live `datetime.utcnow()` deprecations in `app/photo_service.py`, which is production code.

Rejected (noise or out of scope): the `-vv` verbosity escalation and the now-redundant per-session `-v`/`--tb=short` flags (the contract explicitly requires sessions keep their flags, and the Design Notes accept the stacking by name); `test_testpaths_is_read_from_the_ini` asserting `== ["tests"]` being "brittle" (exactness is the point, and the AC names the value); the absence of tripwires for `python_files`/`python_classes`/`python_functions`/`minversion` (any one assertion detects the ini going unread, which is the property under guard) and the `python_classes` narrowing being undocumented (it is, in the previous pass's triage log); `minversion = 7.0` being unreachable against the pinned pytest 9.1.1 (a pre-existing setting the contract preserves); `--color=yes` being removed without an in-file comment (documented in the previous triage log; annotating an absent setting is noise); the `slow` marker having no producer or consumer (the contract explicitly keeps it); stale "pytest.ini is inert" prose in two *completed* spec files (historical record — re-raised from the previous pass, which rejected it for the same reason); `test_strict_markers_is_in_force` checking the parsed option rather than driving a real collection failure end to end (a `pytester` subprocess for a flag whose value is the enabling mechanism, already probed manually with a bogus marker in the previous pass); and the tripwire not running under `nox -s doctests` (it runs in `tests` and `coverage`, both of which are in the default session list, so a regression still turns CI red).

### 2026-07-29 — Review pass (follow-up 2)
- intent_gap: 0
- bad_spec: 0
- patch: 7: (high 0, medium 1, low 6)
- defer: 0
- reject: 5
- addressed_findings:
  - `[medium]` `[patch]` The `doctests` docstring in `noxfile.py` had its *second* paragraph corrected by the previous pass while its *first* paragraph — "Without it pytest collects from the rootdir and would import every module in the tree looking for doctests" — was left stating the pre-activation truth, so the two paragraphs three lines apart now contradicted each other. With `testpaths = tests` live, dropping the `app/utils` argument does not scan the tree: it runs the whole unit/e2e suite under `--doctest-modules` and collects zero doctests from `app/` (verified: `pytest --doctest-modules --collect-only -q` → 4010 items, none under `app/`). Rewritten to name the real failure mode — a green session that tested nothing it exists for — which is a quieter and more dangerous outcome than the import explosion it used to warn about.
  - `[low]` `[patch]` The justification for keeping the `.*` glob, in both `pytest.ini` and the tripwire docstring, claimed `.nox/` "holds full installed copies of this suite". False — there is no `setup.py`/`pyproject.toml`/`setup.cfg`, so the project is never installed into the nox virtualenvs. The hazard is real but third-party: 276 `test_*.py` files under `.nox/*/lib/python3.13/site-packages/`. A false rationale in a comment is the exact defect class that produced DW-102, so both sites now state the verified reason.
  - `[low]` `[patch]` `test_norecursedirs_keeps_the_builtin_exclusions` compared the ini against a *frozen* copy of pytest's defaults with a subset check, which can only ever detect an entry being deleted from `pytest.ini` — never a future pytest release *adding* a built-in exclusion, which is the drift nobody would think to re-audit and which would silently falsify the ini's "repeated verbatim" claim. Now also asserts the frozen copy equals pytest's live default (`pytestconfig._parser._inidict["norecursedirs"][2]`, private but loud if it moves), with a failure message naming both files to update. Mutation-verified: removing one entry from the frozen constant turns it red.
  - `[low]` `[patch]` The marker scan required a literal `@`, so the `pytestmark = ...`, `marks=...` and `add_marker(...)` forms were invisible to it — and `tests/integration/conftest.py:110` already applies `integration` via `add_marker`, so the hole was reachable today, not hypothetical. Dropped the `@` from the pattern (the self-match guard still holds; scan output gains `integration` and no unregistered names). Mutation-verified with a `pytestmark`-applied bogus marker. The pattern change also made the module's own explanatory comment a false positive on first run — caught by the test itself, and the comments now name the marker forms without spelling any out.
  - `[low]` `[patch]` `MARKERS_SELECTED_BY_NOX` was false for 2 of its 5 members: the only `-m` expressions in `noxfile.py` are `not e2e and not integration`, `e2e`, `integration` and `screenshot` — `unit` and `slow` are selected on by nothing. Renamed to `PROJECT_MARKERS` with a comment that draws the distinction, so the constant no longer justifies itself with a reason that never applied to two of its entries.
  - `[low]` `[patch]` The acceptance criterion "`unit`, `integration`, `e2e`, `slow` and `screenshot` each appear **exactly once**" — the story's single-source-of-truth invariant — had no tripwire, because `_registered_marker_names` returned a `set` that deduplicated double-registration away. Restoring `pytest_configure` in `tests/conftest.py` would have left all seven tests green. Added `_registered_marker_name_list` and turned the subset check into a per-marker occurrence count. Mutation-verified by re-adding an `addinivalue_line("markers", "unit: ...")` to `tests/conftest.py`.
  - `[low]` `[patch]` `_bmad-output/project-context.md`'s Layout bullet stated the `norecursedirs` exclusion flatly, dropping the caveat that `pytest.ini` and the tripwire both carefully record — the key filters *recursion* only, so naming such a path directly still collects it (`pytest --collect-only .nox/tests/lib/python3.13/site-packages` → 103 tests, 21 errors). The agent-facing doc now carries the caveat too.

Rejected (noise or out of scope): the claim that the tripwire's "`screenshot` was used 15 times" contradicts the 16 in DW-105 (the 16th grep hit is prose in `tests/e2e/test_screenshot_generation.py:5`; 15 is the decorator count and the collected-test count — settled in the first pass); the `python_classes` narrowing lacking an in-file comment (re-raised from the previous pass, which rejected it — it is recorded in that pass's triage log and is inert, no class matching `*Test` exists); DW-238's title saying "three" while its `location` field lists five `utcnow()` call sites (the entry's own `evidence` field already distinguishes the 3 that warn under the unit suite from the 5 that exist, and this run is forbidden from editing existing ledger entries); `test_pytest_ini_is_the_active_configfile` being weaker than its "*this repo's* pytest.ini" docstring because pytest derives `rootdir` from the ini's own directory (true in the default case, but not under an explicit `--rootdir`, and the test's stated purpose — catching migration to `setup.cfg`/`pyproject.toml`/`tox.ini` — is intact); and `assert pytestconfig.inipath is not None` being dead code ahead of the `==` on the next line (it is, but it yields a clearer failure message for the migration case the test exists to catch).

## Design Notes

Why the `norecursedirs` repair is not scope creep: pytest's `norecursedirs` default is `*.egg .* _darcs build CVS dist node_modules venv {arch}`. The current ini value replaces that with a hand-written list whose `.git`/`.tox`/`.env` entries are all subsumed by the default `.*` glob — but which *omits* `.*`, `build`, `dist` and `node_modules`. Activating it as written would newly expose `.nox/` (which contains full installed test suites) and `.claude/skills/**/scripts/tests/test_*.py` to any bare-rootdir collection. Target value:

```ini
norecursedirs = *.egg .* _darcs build CVS dist node_modules venv {arch} migrations
```

Marker decision (DW-105): `screenshot` is used 16 times and must be registered — it goes in the ini. `database` is used by zero tests and registered by nothing today, so it is dropped rather than added. `slow` is unused but *is* registered today, so keeping it preserves the status quo. Registering markers in the ini (rather than adding two more `addinivalue_line` calls) is strictly better because `tests/conftest.py` is not loaded when collecting `app/utils` in the `doctests` session, whereas the ini applies to every invocation.

Accepted consequence: every nox session already passes `-v`, and `addopts` also carries `--verbose`, so verbosity now stacks to `-vv`. This is cosmetic (more detailed assertion output) and preserves the ini author's declared intent; do not remove `-v` from the sessions or `--verbose` from `addopts` to avoid it.

## Verification

**Commands:**
- `venv/bin/python -m pytest --collect-only -q 2>&1 | head -5` -- expected: header includes `configfile: pytest.ini` and `testpaths: tests`.
- `venv/bin/python -m pytest --markers 2>&1 | grep -E '^@pytest\.mark\.(unit|integration|e2e|slow|screenshot|database)'` -- expected: five lines, one each for `unit`/`integration`/`e2e`/`slow`/`screenshot`, no `database`, no duplicates.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: exit 0, test count unchanged from a pre-change baseline.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: exit 0, collection confined to `app/utils`.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s coverage` -- expected: exit 0.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` -- expected: exit 0. Needs a 20-minute harness timeout; run detached (nohup + poll) because it outlasts the 10-minute Bash cap.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless` -- expected: exit 0, the 16 `screenshot`-marked tests selected. Revert any regenerated PNGs/`metadata.json` afterwards (`git checkout -- docs/images/screenshots`) unless they are genuinely stale.
- `git status --porcelain` at the end -- expected: only the intended source/doc edits, no incidental screenshot or coverage-artifact churn.

## Auto Run Result

Status: done

### Implemented change

Third review pass over an already-implemented story; no new implementation was derived. The underlying change activated `pytest.ini` by renaming its `[tool:pytest]` section (a `setup.cfg` section name) to `[pytest]`, making `testpaths`, `addopts`, `markers`, `norecursedirs` and `minversion` live for the first time, and reconciled the marker registry in the same pass. This pass found no intent gaps and no spec defects. Every finding was an accuracy or coverage defect in the *rationale and tripwires* the change ships with — a stale docstring paragraph the previous pass half-corrected, a fabricated justification for the `.*` glob, and three tripwires that could not detect the drift they were written to catch. Seven patches applied, confined to one `noxfile.py` docstring, `pytest.ini` comment text, one `project-context.md` bullet, and the tripwire test module.

### Files changed

- `noxfile.py` — rewrote the first paragraph of the `doctests` docstring, which still described pre-activation behavior and contradicted the paragraph the previous pass corrected three lines below it. No code change.
- `pytest.ini` — corrected the `norecursedirs` rationale: `.nox/` holds third-party test suites in its session virtualenvs, not copies of this project's suite. No settings changed.
- `tests/unit/test_pytest_config.py` — marker scan no longer requires a leading `@` (so `pytestmark`/`marks=`/`add_marker` forms are covered); `norecursedirs` tripwire now pins the frozen default copy against pytest's live default; `MARKERS_SELECTED_BY_NOX` renamed to `PROJECT_MARKERS` with a truthful comment; the subset marker check became a per-marker exactly-once count, giving the single-source-of-truth invariant its first tripwire.
- `_bmad-output/project-context.md` — Layout bullet now carries the "recursion only" caveat on `norecursedirs` that `pytest.ini` and the test already stated.
- `_bmad-output/implementation-artifacts/deferred-work.md` — **not touched** this pass (nothing deferred).

### Review findings

7 patches applied (1 medium, 6 low), 0 deferred, 5 rejected. Full breakdown in the Review Triage Log above. No intent gaps, no spec defects, no loopback.

### Verification performed

- `nox -s tests` — 3542 passed, 2 skipped, 466 deselected. Count unchanged from the previous pass (a test was renamed and strengthened, none added or removed).
- `nox -s doctests` — 22 passed, collection still confined to `app/utils`.
- All three new/strengthened tripwires were **mutation-tested**, not just run green: re-adding an `addinivalue_line("markers", "unit: ...")` to `tests/conftest.py` turns the exactly-once test red; removing one entry from `PYTEST_DEFAULT_NORECURSEDIRS` turns the live-default equality red; a `pytestmark`-applied bogus marker in an uncollected file under `tests/` turns the scan red. All mutations reverted and the module re-verified at 7 passed.
- The `@`-less scan pattern immediately failed on this module's own new comment text, which independently confirms the scan reaches every `.py` file under `tests/`; comments reworded and re-verified.
- Claims checked against the filesystem rather than trusted: no `setup.py`/`pyproject.toml`/`setup.cfg` exists (so the project is never installed into `.nox`); 276 third-party `test_*.py` under `.nox/*/site-packages`; 4 files matching `.claude/skills/**/scripts/tests/test_*.py`; 16 textual `@pytest.mark.screenshot` hits of which line 5 is prose, giving 15 decorators; every `-m` expression in `noxfile.py` enumerated; no duplicate names in the live 20-entry marker registry.
- `nox -s coverage`, `e2e` and `screenshots_headless` were **not** re-run this pass. They were green in earlier passes, and this pass changed only comment/docstring text, one doc bullet and one unit test module — no live pytest setting was altered. `pytest.ini` still parses under `--strict-config` (proven by every run above staying green).
- `git status --porcelain` — only the four intended files plus this spec; no screenshot or coverage-artifact churn, and `tests/conftest.py` is clean after the mutation test.

### Residual risks

- The `norecursedirs` upgrade tripwire reads `pytestconfig._parser._inidict`, a private pytest attribute. If pytest relocates it the test raises rather than silently passing, which is the correct failure direction for a tripwire, but it will need a one-line fix on some future pytest upgrade.
- The marker scan is still textual and now matches dotted marker references without a leading `@`, so it has a slightly larger prose false-positive surface under `tests/`. This is documented in the test's docstring and the failure names the offending file and marker.
- DW-238 (blanket `--disable-warnings` hiding 3 live `utcnow()` deprecations in `app/photo_service.py`) remains the one known live consequence of activation that is unaddressed.
- Each of the three passes has found roughly seven real accuracy defects, which reflects how comment-dense this change is; a fourth pass would likely find more prose nits. Consequence has decayed sharply though — pass 1's medium was "no tripwire exists at all", pass 2's was "the documented workaround breaks its own tests", and this pass's was "a docstring paragraph is stale" — which is why no follow-up is recommended.

