---
title: 'Execute the pure app/utils doctests in a dedicated nox session'
type: 'chore'
created: '2026-07-26'
status: 'done'
baseline_revision: '9e3962f5a85ea84ce0d61c4abb0b6ac8a7eca20c'
final_revision: '65cd9964448b2f8eca0a2c7f8053c799dd993b23'
review_loop_iteration: 0
followup_review_recommended: false # Pass 2: 5 patches (1 medium, 4 low) — one narrowed CI `if:` condition plus four prose corrections. No production code, test code, or session definition changed this pass (`git diff -- pytest.ini app/ noxfile.py` empty); no behavior, API, security, or data impact. Pass 2 also found and corrected pass 1's remaining rationale defect, so the two passes are converging rather than turning up new classes of finding.
context: ['{project-root}/_bmad-output/project-context.md']
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** Eight modules under `app/utils/` carry 20 `>>>` docstring examples (`category.py` 5 docstrings, `location_validator.py` 3, `gtin.py` 3, `tag.py` 3, `internal_id.py` 2, `gs1.py` 2, `ecia.py` 1, `scan_router.py` 1) and nothing executes them: `pytest.ini` has no `--doctest-modules` in `addopts`, `noxfile.py` has no session that enables it, and there is no `setup.cfg` or `pyproject.toml` at all (verified). AD-4 makes these pure modules the single source of truth for identifier/encoding/classification logic — and makes the `category.py` docstrings the contract Epic 8's faceting builds on — so their examples are prose that can rot silently. Only one of them is pinned by a hand-written test (`test_the_matrix_pattern_is_22_characters`).

**Approach:** Add a dedicated `doctests` nox session that runs `pytest --doctest-modules` scoped to `app/utils` only, add it to the default session list, and add a CI step so PRs run it. Scoping to a path rather than putting `--doctest-modules` in `pytest.ini`'s `addopts` keeps collection off the rest of the tree (routes, services, ORM), which is the reason DW-45 called this a repo-wide configuration decision rather than one story's addopts change.

## Boundaries & Constraints

**Always:**
- The doctest run is scoped by an explicit `app/utils` path argument, so it covers the whole pure-utils package and picks up new modules added there without editing the session.
- The session installs `requirements.txt` and `requirements-test.txt` and logs `pip freeze`, matching every other session in `noxfile.py`.
- The doctests must pass unmodified. If an example fails, fix the *example or the docstring prose* only when it is demonstrably wrong about behavior the code already has; changing production behavior to satisfy a docstring is a Block If.
- `nox -s tests`, `nox -s coverage` and `nox -s e2e` keep their current behavior — no new flags, no changed markers.

**Block If:**
- A doctest failure reveals an actual behavior discrepancy in a pure util (i.e. the code, not the example, is wrong). Report it; do not silently change production logic.
- A module under `app/utils` cannot be imported by the collector (import-time error), since that would mean making the session green requires either changing module structure or narrowing scope.

**Never:**
- Do not add `--doctest-modules` to `pytest.ini` `addopts`, and do not create `setup.cfg` or `pyproject.toml` to hold it — that would collect doctests from every module in the tree.
- Do not add `# doctest: SKIP` / `+ELLIPSIS` directives to make a failing example pass, and do not delete an example to make the session green.
- Do not rewrite the deliberately-illustrative grammar in `scan_router.classify`'s examples (AD-16: the module holds no literal default for the AI or token half; the examples pass both explicitly and are self-contained).
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`.
- Do not extend doctest execution to `app/services/`, `app/main/`, `app/admin/` or the model/ORM layer.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Doctests green today | Current tree, `nox -s doctests` | 20 doctest items collected from `app/utils`, all pass, exit 0 | No error expected |
| Broken example | One `>>>` expected-output line edited to a wrong value | Session fails, naming the module and function | Rejection is the expected outcome |
| Scope holds | Session run | No test item is collected from outside `app/utils` (no route/service/ORM module imported for doctests) | No error expected |
| New pure util added | A new `app/utils/*.py` with a `>>>` example | Covered automatically, no `noxfile.py` edit needed | No error expected |
| Doctests all removed | No `>>>` examples anywhere under `app/utils` | pytest collects nothing → exit code 5 → session red | Rejection is the expected outcome |
| Path typo in session | Session points at a nonexistent path | pytest exits 4 → session red, not silently green | Rejection is the expected outcome |

</intent-contract>

## Code Map

- `noxfile.py` -- sessions are plain `@nox.session(python=DEFAULT_PYTHON)` functions that `session.install(...)` both requirement files, `session.run("pip", "freeze")`, then `session.run("python", "-m", "pytest", ...)` with `*session.posargs`. `nox.options.sessions = ["tests", "coverage"]` at :245 is the default list. New session goes here.
- `.github/workflows/test.yml` -- `unit-tests` job runs `nox -s tests` (:39-41 region, step "Run unit tests"). The new CI step goes in this job, after it, reusing the same pip cache.
- `pytest.ini` -- declares `testpaths = tests` and an `addopts` of `--verbose --tb=short --strict-markers --disable-warnings --color=yes`, **none of which is in force**: the section header is `[tool:pytest]`, a `setup.cfg` section name, so pytest reports the file as `configfile` but reads nothing from it (verified by A/B test; deferred as DW-102). Consequence for this work: the explicit `app/utils` path argument is the *only* thing scoping collection, and every flag must be passed on the command line. Not modified.
- `app/utils/category.py` -- 5 doctest'd functions (`normalize_category_path`, `is_descendant_path`, `descendant_like_pattern`, `rewrite_category_path`, `ancestor_paths`); uses the relative import `from .sql_text import ...` at :59.
- `app/utils/{gtin,internal_id,tag,location_validator,ecia,gs1,scan_router}.py` -- the other seven doctest-carrying modules. `scan_router.py` is the only one importing `app.models`, which pulls in `app/__init__.py` (Flask, flask_wtf) — importable because the session installs `requirements.txt`.
- `app/utils/{__init__,sql_text}.py` -- no doctests; `__init__.py` is a bare docstring with no imports or side effects, so no double-collection.

## Tasks & Acceptance

**Execution:**
- [x] `noxfile.py` -- add a `doctests` session that installs both requirement files, logs `pip freeze`, and runs `python -m pytest --doctest-modules --blockage app/utils --tb=short` plus `*session.posargs`; add `"doctests"` to `nox.options.sessions`. `--blockage` (pytest-blockage, already in `requirements-test.txt`) asserts the AD-4 purity claim at runtime — a pure util that opens a socket fails rather than passing quietly. The explicit `app/utils` path is what keeps `--doctest-modules` from collecting the whole tree — and it is load-bearing rather than merely overriding `testpaths`, because `pytest.ini` is not read at all (DW-102), so without the path pytest would collect from the rootdir.
- [x] `.github/workflows/test.yml` -- add a "Run doctests" step to the `unit-tests` job running `nox -s doctests`, so a rotted example fails a PR rather than only a local default run.
- [x] Verify by mutation -- temporarily corrupt one expected-output line in `app/utils/category.py` and one in `app/utils/scan_router.py`, confirm the session goes red and names the offending function, then restore both and confirm green. Record the observed output in the run result; leave no mutation in the tree.

**Acceptance Criteria:**
- Given the current tree, when `nox -s doctests` runs, then it exits 0 having collected and passed 20 doctest items from `app/utils`.
- Given a deliberately wrong expected-output line in an `app/utils` docstring, when `nox -s doctests` runs, then it exits non-zero and the failure output names the containing module and function.
- Given the doctests session, when its collected item list is inspected, then every item's path is under `app/utils/` and no route, service, or ORM module contributes an item.
- Given a bare `nox` invocation, when the default sessions run, then `doctests` runs alongside `tests` and `coverage`.
- Given the existing suites, when `nox -s tests` runs, then it is green and its collected-test count is unchanged from before this work.
- Given `pytest.ini`, when it is diffed after this work, then it is unmodified — no `--doctest-modules` in `addopts`.

## Spec Change Log

## Review Triage Log

### 2026-07-26 — Review pass 1
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 0, medium 2, low 6)
- defer: 2: (high 0, medium 1, low 1)
- reject: 11: (high 0, medium 0, low 11)
- addressed_findings:
  - `[medium]` `[patch]` The session docstring justified the explicit path as "overrides `testpaths` in pytest.ini" — false, and the spec's Code Map repeated it. `pytest.ini` declares `[tool:pytest]`, a `setup.cfg` section name, so pytest reports it as `configfile` while reading **nothing** from it. Verified by A/B test in a scratch dir with the project's own pytest 9.1.1 (`[tool:pytest]` → no `testpaths:` header line, `addopts`' `--verbose` not applied, unregistered marker warns instead of erroring; `[pytest]` → all four take effect). Corroborated in-repo: the session's own output was compact dots despite `addopts` declaring `--verbose`. The implementation was already correct — the path argument is in fact *more* load-bearing than claimed, since without it pytest collects from the rootdir — so this was a rationale defect, not a code defect. Docstring rewritten to state the real reason; the Code Map entry and the task rationale in this spec corrected; the underlying repo-wide config defect deferred as DW-102.
  - `[medium]` `[patch]` The CI "Run doctests" step had no `if:`, so GitHub Actions skips it whenever `Run unit tests` fails — hiding doctest regressions on exactly the runs where full signal matters most. Added `if: '!cancelled()'`; verified the workflow still parses and that the condition lands on the right step.
  - `[low]` `[patch]` The `test-summary` job reports `needs.unit-tests.result` under the heading `### Unit Tests:`, so a doctest-only failure was surfaced to the PR as "Unit Tests: ❌ FAILED", pointing readers at the wrong suite. Heading is now "Unit Tests & Doctests" with a comment naming both.
  - `[low]` `[patch]` The session passed no `-v` while its sibling `tests` session does, and (per the finding above) there is no `addopts` fallback — so CI output was bare per-file dots. Added `-v`; output now names each doctest node (`app/utils/gtin.py::app.utils.gtin.compute_check_digit PASSED`).
  - `[low]` `[patch]` The docstring called these "pure utility modules" while the collector imports them package-qualified as `app.utils.X`, which executes `app/__init__.py` → `config.py` → `load_dotenv`. A malformed `.env` therefore fails the session at collection for all ten files, including `sql_text.py`, which has no doctests. Docstring now states the AD-4 sense of "pure" and names the import-time dependency.
  - `[low]` `[patch]` `README.md:72-74` and `docs/development-testing-guide.md` enumerate the project's test commands and neither mentioned the new session. Both updated; the guide gains a full `#### 3. Doctests` entry (renumbering coverage to `#### 4`) recording the scope, the auto-pickup property, and why `python -m doctest <file>` is not an equivalent check.
  - `[low]` `[patch]` `_bmad-output/project-context.md` — the file that briefs future agents — became actively wrong: its session list omitted `doctests` and it stated "default = `tests`, `coverage`". Both corrected, plus a new rule stating the `app/utils`-only boundary, plus a caveat on its `--strict-markers` claim pointing at DW-102 (that stale claim is what made the false rationale plausible in the first place).
  - `[low]` `[patch]` The final hunk rewrote `noxfile.py`'s last line and left the file still ending without a newline, so every future diff would keep carrying the `\ No newline at end of file` marker. Added.

### 2026-07-26 — Review pass 2
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 1, low 4)
- defer: 3: (high 0, medium 0, low 3)
- reject: 15: (high 0, medium 0, low 15)
- addressed_findings:
  - `[medium]` `[patch]` The single sentence justifying the whole approach was false. `docs/development-testing-guide.md` claimed `python -m doctest app/utils/<module>.py` raises `ImportError` "while the command still looks successful" — verified wrong: it prints a full traceback and **exits 1**. (`python -m doctest app/utils/gtin.py` exits 0 and does run its examples, so the per-file runner is not uniformly broken either.) The runner choice is still correct, but for the other reason: `python -m doctest` takes one file at a time, so covering the package means enumerating all eight modules by hand and a newly added `app/utils/*.py` stays silently uncovered — and `category.py` cannot be run that way at all. Docs note rewritten; the same false claim corrected in this spec's Design Notes (prose only — no code implication, so patched rather than looped back as bad_spec).
  - `[low]` `[patch]` "20 examples" was a miscount of the wrong unit. pytest collects 20 *items*, one per docstring; there are 51 individual `>>>` examples (`grep -c '>>>' app/utils/*.py`). Reworded to "20 doctest items — one per docstring, 51 individual `>>>` examples". The `**Runtime**: <0.1 seconds` line also buried the real cost inside "(plus environment setup)"; it now states the ~20 s wall-clock for a warm session.
  - `[low]` `[patch]` The CI step's `if: '!cancelled()'` was far broader than its own comment ("runs even when the unit tests fail"). It is also true when `checkout`, `setup-python`, the `apt-get` step, or `pip install nox` failed, in which case the doctests step runs into a half-built environment and emits a second, misleading failure on top of the real one. Gave the unit-tests step `id: unit_tests` and narrowed the condition to `success() || steps.unit_tests.conclusion == 'failure'`; comment now says why it is deliberately not `!cancelled()`. Re-parsed with PyYAML to confirm the `id` and `if` land on the right steps.
  - `[low]` `[patch]` The docs change was half-applied: `docs/development-testing-guide.md`'s "Running Tests During Development" list still read "Quick validation: `nox -s tests`" / "Full validation: `nox -s tests && nox -s e2e`", so a developer following the prescribed workflow to the letter never ran doctests. Added as step 2 and to the full-validation chain, renumbering coverage to 4.
  - `[low]` `[patch]` The `project-context.md` marker bullet this story rewrote was left self-contradicting: it told agents to "register any new marker before using it" while pointing at `pytest.ini`, the file it simultaneously admits pytest reads nothing from. Registration actually happens in `tests/conftest.py::pytest_configure`, which registers only four of the six markers `pytest.ini` lists (`database` and `screenshot` are registered nowhere — deferred as DW-105). Bullet rewritten to name the real registration site and state plainly that `--strict-markers` is declared but not in force.

## Design Notes

`python -m doctest app/utils/category.py` — the invocation DW-45/DW-66 reach for — is *not* a viable runner here: it imports the file as a top-level module, so `category.py`'s relative `from .sql_text import ...` raises `ImportError: attempted relative import with no known parent package` and **zero tests run**. (Corrected in review pass 2: it exits **1** with a traceback, so it fails loudly rather than looking successful — the earlier claim that the command "still looks like it did something" was wrong, verified by running it.) The disqualifying property is the other one: `python -m doctest` takes one file at a time, so covering the package means enumerating all eight modules by hand and a newly added `app/utils/*.py` stays silently uncovered until someone remembers to add it — and one of those eight cannot be run this way at all. pytest's `--doctest-modules` imports package-qualified, discovers the package, and handles all eight modules including `category.py` (verified: `pytest --doctest-modules app/utils -q` → `20 passed`). The runner choice is therefore load-bearing, not incidental.

The examples were checked for non-determinism before committing to running them in CI: `internal_id.generate_internal_id` uses `secrets` but its example asserts only length and alphabet membership; `gs1.encode` compares with `==` rather than reprinting the `\x1d` FNC1 byte; nothing depends on time, filesystem, network, locale, or app config; no module uses a `# doctest:` directive today.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: `20 passed`, exit 0, every item path under `app/utils/`.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, same test count as before this work.
- `venv/bin/python -m pytest --doctest-modules --blockage app/utils -q` -- fast iteration only; the authoritative run is the nox session.
- `git diff -- pytest.ini` -- expected: empty.

## Auto Run Result

Status: done

**Summary.** Follow-up review pass (pass 2) over the same change: the 20 `>>>` docstring examples in `app/utils/`'s eight pure modules are executed by a dedicated `nox -s doctests` session (`pytest -v --doctest-modules --blockage app/utils --tb=short`), in the default session list and running as its own CI step. No code was re-derived this pass — `noxfile.py`, `pytest.ini` and `app/` are byte-identical to the pass-1 result. The five patches are one CI condition and four prose corrections.

The pass's substantive find was that the sentence justifying the entire approach was false. The docs claimed `python -m doctest app/utils/<module>.py` fails "while the command still looks successful"; running it shows a traceback and exit **1**. The approach survives on the correct reason — per-file invocation cannot discover the package, so a newly added `app/utils/*.py` stays uncovered, and `category.py`'s relative import cannot be run that way at all — so the fix was to state that reason rather than to change the runner. Same shape as pass 1's `testpaths` finding: a rationale defect sitting on top of correct code.

**Files changed this pass:**
- `.github/workflows/test.yml` — `Run unit tests` gains `id: unit_tests`; the doctests step's condition narrowed from `!cancelled()` to `success() || steps.unit_tests.conclusion == 'failure'`, so a failed *setup* step no longer produces a second misleading failure.
- `docs/development-testing-guide.md` — `python -m doctest` note corrected; "20 examples" → "20 doctest items (one per docstring, 51 individual `>>>` examples)"; runtime line now states real wall-clock; "Running Tests During Development" workflow list now includes `nox -s doctests`.
- `_bmad-output/project-context.md` — marker bullet rewritten to name `tests/conftest.py::pytest_configure` as the real registration site and to state that `--strict-markers` is declared but not in force.
- `_bmad-output/implementation-artifacts/spec-pure-util-doctest-session.md` — Design Notes corrected; pass-2 triage entry appended.
- `_bmad-output/implementation-artifacts/deferred-work.md` — three new entries appended (DW-104, DW-105, DW-106); no existing entry read back, modified, or re-opened.

**Review findings breakdown:** 5 patched (1 medium, 4 low), 3 deferred, 15 rejected. Notable rejections: the `coverage` job being skipped on a doctest-only failure (`needs: unit-tests` — the same gating already applied to unit-test failures; changing it is a repo-wide CI policy decision, not this story's); the cost of a fourth nox environment installing Playwright and testcontainers for 0.08 s of assertions (the spec's Always list requires matching every sibling session's install block, and the cost is now stated in the docs instead of hidden); `--blockage` as cargo cult (the spec justifies it explicitly as a runtime assertion of the AD-4 purity claim); propagating the DW-102 caveat to three prose sites instead of renaming the `pytest.ini` section (the spec's Never list forbids touching `pytest.ini`); `session.posargs` widening rather than narrowing, exit-5-on-empty-collection being "opaque", and the absence of a `doctest_optionflags` home (all three settled in pass 1 or already recorded as residual risks); a `PYTHONPYCACHEPREFIX` guard against stale `.pyc` files (CPython invalidates by mtime+size; the reviewer's own occurrence traced to concurrent editing, not to the session); the `unit-test-artifacts` upload step now covering two suites (cosmetic); and `test-summary` rendering `❌ FAILED` for a `skipped`/`cancelled` job (pre-existing ternary, unrelated to this change).

**Deferred — appended to the ledger as new entries only:**
- DW-104 `[low]` — `app/utils/sql_text.py` documents its LIKE-escaping contract, ordering guarantee and non-idempotency entirely in prose with zero `>>>` examples, so the module with the subtlest semantics contributes nothing to the session that now covers its package.
- DW-105 `[low]` — `database` and `screenshot` are declared in `pytest.ini` but registered by no `pytest_configure`; harmless while `pytest.ini` is inert, but closing DW-102 activates `--strict-markers` and turns `nox -s screenshots` red, so the two should be resolved together.
- DW-106 `[low]` — `README.md` advertises "Unit Tests: 66/66" and "E2E Tests: 20/20" under a "100% success rates" heading; actual collection is 2571 non-e2e and 367 e2e.

**Verification:**
- `nox -s doctests` — **20 passed**, exit 0, 0.08 s, 19 s wall-clock; `-v` output confirms all 20 node IDs are under `app/utils/` and no route, service, or ORM module contributes an item.
- `python -m doctest app/utils/category.py` → traceback, **exit 1**; `python -m doctest app/utils/gtin.py` → **exit 0**, examples run. This is what falsified the docs claim.
- `grep -c '>>>' app/utils/*.py` → 51 total across 8 modules; `sql_text.py` and `__init__.py` at 0. Confirms both the 20-items-vs-51-examples correction and DW-104.
- `tests/conftest.py:203-216` registers exactly four markers; `pytest.ini` lists six; `noxfile.py:175,213` run `-m screenshot`. Confirms DW-105.
- `pytest tests/ --collect-only -q` → **2938 collected**; `-m e2e` → **367/2938 (2571 deselected)**. Confirms DW-106.
- `.github/workflows/test.yml` re-parsed with PyYAML: `id: unit_tests` on the unit-tests step, the new `if:` on the doctests step and nowhere else, `if: failure()` on the artifact upload unchanged.
- `git diff -- pytest.ini app/ noxfile.py` — empty. No production code, no test code, and no session definition changed in this pass.

**Residual risks:**
- Carried from pass 1 and unchanged: the session's scoping depends on `pytest.ini` being inert, and fixing DW-102 activates `--strict-markers`, `norecursedirs` and `testpaths` across the other sessions at once — fallout unassessed, and DW-105 is now a known part of it.
- Doctest collection imports the `app` package, so an import-time failure in `app/__init__.py`, `config.py`, or a malformed `.env` fails this session for reasons unrelated to any docstring. Documented in the session docstring rather than worked around.
- The narrowed CI condition was verified by YAML parse and expression review, not by an actual failing CI run; the `steps.unit_tests.conclusion == 'failure'` branch is exercised only when the unit suite genuinely breaks.
- A doctest-only failure still reports as one red `unit-tests` job and skips the `coverage` job. The summary heading names both suites, but separate per-suite PR status would require splitting `doctests` into its own job — rejected as out of scope.
- `session.posargs` is appended after `app/utils`, so a path passed manually widens rather than narrows the run. Only `-k` narrows.
- `ecia.parse_fields` and the `tag.py` examples assert on dict/list repr order; deterministic on CPython today, but an order-changing refactor would fail them on ordering alone.
