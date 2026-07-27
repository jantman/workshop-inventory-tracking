---
title: 'Give the scan trim rule a single home as a pure util (DW-59)'
type: 'refactor'
created: '2026-07-27'
status: 'done'
baseline_revision: '035b272bdcd708c3ab52d007522cba313c900305'
final_revision: 'b231bc5e4172980133803acac83e859e75d5d046'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** Epic 4's most load-bearing invariant — the exact set of characters trimmed off a captured scan — lives as the private symbols `_SCAN_TRIM` / `_clean_scan_input` (plus `MAX_SCAN_LENGTH`) inside the 4,700-line `app/main/routes.py`, so `tests/unit/test_scan_routes.py` already reaches across modules for an underscore-prefixed name and every future consumer must do the same or restate the rule. A second copy of the rule lives in JavaScript as `ScanCapture.stripOuter`, and no fast test compares the two character sets.

**Approach:** Move the three symbols into a new pure module under `app/utils/` with public names, have `app/main/routes.py` import them, re-aim every prose reference that names the old home, and add a fast unit test that reads the JS regex character class out of `app/static/js/scan-capture.js` and asserts it is exactly the Python trim set — so the two copies cannot drift silently. Behavior does not change.

## Boundaries & Constraints

**Always:**
- The trim set stays exactly `' \t\r\n'`. GS (`\x1d`), RS (`\x1e`), EOT (`\x04`), FS/US (`\x1c`/`\x1f`), VT/FF, NBSP and BOM are all preserved, as today. `MAX_SCAN_LENGTH` stays `4096`.
- The new module is PURE on the AD-4 pattern (`gtin.py`, `gs1.py`, `ecia.py`): standard library only — no Flask, no `current_app`, no config, no SQLAlchemy, no I/O, no `app.*` imports.
- Every observable behavior of `POST /api/scan` is byte-identical: same responses, same log lines, same error envelope.
- `app/static/js/scan-capture.js` changes by COMMENT ONLY — the regex literals in `stripOuter` are not edited, so the rendered UI is unchanged and no screenshot regeneration is warranted.
- Docstring examples added under `app/utils/` are executed by `nox -s doctests`; any `>>>` example must pass.

**Block If:**
- Making the move behavior-preserving would require widening or narrowing the trim set, or changing what `/api/scan` returns or logs.

**Never:**
- Do not move `_SCAN_LOG_CHARS`. It bounds what the *route* writes to its log, is used nowhere else, and is not a property of the scan-text rule.
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md` — the orchestrator records resolution.
- Do not "fix" the known GS/RS asymmetry between `gs1.decode` and the cleaner (DW-67 / DW-11 item (c)), do not absorb leading separators, and do not add a compatibility alias for `_clean_scan_input` in `app/main/routes.py` — the point of the move is that there is one name in one place.
- Do not reformat, restructure or otherwise touch unrelated parts of `app/main/routes.py`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Trimmed characters | `'  0123 \r\n'` | `'0123'` | No error expected |
| Interior whitespace | `'a b\tc'` | unchanged | No error expected |
| ISO/IEC 15434 envelope | `'[)>\x1e06\x1dP123\x1e\x04'` | unchanged — bare `str.strip()` would eat the RS | No error expected |
| Non-trim control chars | `'\x0bP123\x0c'`, `'\x00'`, `'\x1c\x1f'` | unchanged | No error expected |
| Whitespace-only | `'   '` | `''` (route then answers 400 `raw must not be empty`) | Unchanged 400 envelope |
| JS/Python drift | `stripOuter`'s regex class widened or narrowed | Unit test fails naming both sides | Test failure, not runtime error |
| JS shape changed | `stripOuter` renamed or its regexes restructured | Unit test fails loudly rather than silently matching nothing | Assertion message says the anchor is gone |

</intent-contract>

## Code Map

- `app/main/routes.py:1795-1819` -- current home of `MAX_SCAN_LENGTH`, `_SCAN_TRIM`, `_SCAN_LOG_CHARS`, `_clean_scan_input`; call sites at `:2219-2234`.
- `app/utils/` -- destination package; `ecia.py` and `gtin.py` show the pure-module docstring/style pattern to match.
- `app/static/js/scan-capture.js:423-427` -- `stripOuter`, the JS copy of the rule; comment names the old home.
- `tests/unit/test_scan_routes.py:30-32,96-151` -- imports the private helper; `TestCleanScanInput` is the rule's existing unit coverage.
- `tests/unit/test_keydown_focus_guards.py`, `tests/unit/test_toast_markup.py` -- the repo's precedent for asserting JS *source* structure from a fast unit test (no JS harness exists).
- `tests/e2e/test_wedge_scan.py:290-346` -- existing behavioral end-to-end comparison of the two copies; the new unit test is its fast tripwire, not its replacement.
- Prose references naming the old location: `app/utils/scan_router.py:68,85`, `app/mariadb_catalog_service.py:111,1991,2168,2368`, `app/request_limits.py:6`, `config.py:119`, `tests/unit/test_scan_router.py:837,847,866`, `tests/unit/test_scan_resolution.py:1598`, `tests/unit/test_ecia.py:329`, `tests/e2e/test_wedge_scan.py:291,321`.

## Tasks & Acceptance

**Execution:**
- [x] `app/utils/scan_input.py` -- create the pure module holding `MAX_SCAN_LENGTH = 4096`, `SCAN_TRIM = ' \t\r\n'` and `clean_scan_input(value)`, carrying the existing comments' reasoning (why the set is explicit rather than a bare `str.strip()`, why the bound exists) in a module docstring on the `ecia.py`/`gtin.py` pattern, plus doctest examples that pin the envelope and control-character cases -- gives the invariant one public home a consumer can import without reaching for a private name.
- [x] `app/main/routes.py` -- delete the three moved definitions, import `MAX_SCAN_LENGTH`/`clean_scan_input` from `app.utils.scan_input` alongside the other pure-util imports, update the two call sites, keep `_SCAN_LOG_CHARS` where it is with a comment saying why it stayed -- the route becomes a consumer of the rule rather than its owner.
- [x] `tests/unit/test_scan_trim_rule.py` -- new source tripwire: extract `stripOuter`'s regex character class(es) from `app/static/js/scan-capture.js`, decode the JS escapes, and assert the resulting character set equals `set(SCAN_TRIM)`; also pin the Python literal itself and assert loudly if the JS anchor is missing -- makes the two copies impossible to drift apart without a fast test going red.
- [x] `tests/unit/test_scan_routes.py` -- import `clean_scan_input`/`MAX_SCAN_LENGTH` from `app.utils.scan_input`, update the docstrings naming `_SCAN_TRIM`, and keep every existing `TestCleanScanInput` assertion intact -- the rule's coverage moves with it and proves behavior is unchanged.
- [x] `app/utils/scan_router.py`, `app/mariadb_catalog_service.py`, `app/request_limits.py`, `config.py`, `app/static/js/scan-capture.js`, `tests/unit/test_scan_router.py`, `tests/unit/test_scan_resolution.py`, `tests/unit/test_ecia.py`, `tests/e2e/test_wedge_scan.py` -- comment/docstring only: re-aim references from `app/main/routes.py`'s `_clean_scan_input`/`_SCAN_TRIM` to `app.utils.scan_input`'s `clean_scan_input`/`SCAN_TRIM` -- stale location references are exactly the defect DW-59 records.

**Acceptance Criteria:**
- Given the new module, when a consumer imports the trim rule, then `from app.utils.scan_input import SCAN_TRIM, clean_scan_input, MAX_SCAN_LENGTH` succeeds with no Flask app context and no database.
- Given `app/main/routes.py`, when it is searched for `_SCAN_TRIM` or `def _clean_scan_input`, then neither appears — while `MAX_SCAN_LENGTH` and `_SCAN_LOG_CHARS` are still resolvable names in that module.
- Given the JS `stripOuter` regex class is edited to add or drop a character, when `nox -s tests` runs, then the new unit test fails and its message names both the JS set and the Python set.
- Given `POST /api/scan` with any body, when the full unit suite runs, then every pre-existing assertion in `tests/unit/test_scan_routes.py` still passes unchanged in meaning.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 12: (high 0, medium 2, low 10)
- defer: 0
- reject: 4: (high 0, medium 0, low 4)
- addressed_findings:
  - `[medium]` `[patch]` The new tripwire could not see the likeliest form of the regression it exists to catch: the blank gate switching to `this.input.value.trim()` leaves `stripOuter` correct but dead. Added an assertion that `app/static/js/scan-capture.js` still contains the verbatim blank-gate call, and widened the `.trim(` ban from the function body to the whole file. Verified by mutating the real file — the fast suite now goes red.
  - `[medium]` `[patch]` `CHARACTER_CLASS`'s trailing `[^/\n]*` silently swallowed anything after the class inside a regex literal, so `/^[ \t\r\n]+|^\s+/` — an alternation widening the client rule to the entire Unicode whitespace set — compared equal to `SCAN_TRIM` and passed. Extraction now full-matches each literal against its expected shape (`/^[...]+/` then `/[...]+$/`), with `test_an_alternation_outside_the_class_is_an_assertion` and `test_two_leading_rules_are_an_assertion` as self-tests. Verified by mutating the real file.
  - `[low]` `[patch]` The tripwire's honest-limits paragraph claimed "a `stripOuter` rewritten to `return value;` passes every test below", which is false (it fails the extraction). Rewritten to state the limits that are real: string-level reading only, and no proof the gate honors the answer.
  - `[low]` `[patch]` `docs/development-testing-guide.md:104` still said 20 doctest items / 51 examples across a module list without `scan_input.py`. Updated to the measured 21 items / 62 examples.
  - `[low]` `[patch]` `tests/unit/test_scan_router.py:539` still read "The endpoint's MAX_SCAN_LENGTH" while its twin in `test_ecia.py` was re-aimed. Re-aimed to `app.utils.scan_input.MAX_SCAN_LENGTH`.
  - `[low]` `[patch]` `app/utils/scan_input.py`'s purity claim overreached — "imported by ... a script with no app context" is untrue, since a package-qualified import still runs `app/__init__.py` (Flask + `config`). Narrowed to a claim about the module's own body.
  - `[low]` `[patch]` `clean_scan_input`'s docstring said a non-`str` raises `AttributeError`; `bytes` reaches `bytes.strip` and raises `TypeError`. Both are now documented, with the note that the transport rejects a non-`str` before this is reachable.
  - `[low]` `[patch]` The `\s` sentinel in `JS_ESCAPES` — the file's named primary threat — was only ever exercised against the real file, where no `\s` exists, so it was vacuously true. Added `test_the_unicode_shorthand_sentinel_actually_fails` against a fabricated source.
  - `[low]` `[patch]` The new pure util had no test module, breaking the one-file-per-util convention (`test_ecia.py`, `test_gtin.py`, …) and leaving its coverage in a route test file. `TestCleanScanInput` moved verbatim to `tests/unit/test_scan_input.py`, joined by an AST purity test; both `test_scan_routes.py` and `scan_input.py` re-aimed to it.
  - `[low]` `[patch]` A duplicated `stripOuter` definition, or a third `.replace()` whose argument is not a regex literal, would have gone unnoticed. Added count assertions for both, plus `test_a_duplicated_function_is_an_assertion_not_a_silent_pass`.
  - `[low]` `[patch]` Comment rewrapping left orphaned half-lines mid-sentence in `config.py` and `app/mariadb_catalog_service.py`. Re-flowed.
  - `[low]` `[patch]` The module docstring said `scan-capture.js` "carries a mirrored copy of it" where "it" covered both bounds. Clarified that only the trim set is mirrored, and stated why `MAX_SCAN_LENGTH` deliberately is not.

Rejected: the claim that `from app.utils.scan_input import ...` re-creates the forbidden compatibility alias (the alias was for the removed `_clean_scan_input`; the file already mixes import styles, and module-style would break this spec's own AC that `routes.MAX_SCAN_LENGTH` stays resolvable); that DW-59 itself is unresolved in the ledger (the orchestrator owns that, per the Never list); that the client lacking a `maxlength` is a defect (pre-existing, and a visible 400 beats a silent truncation); and a speculative note that one loop would pass vacuously if a helper assertion were later softened.

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 0, medium 3, low 5)
- defer: 0
- reject: 6: (high 0, medium 0, low 6)
- addressed_findings:
  - `[medium]` `[patch]` A regex flag changed the rule while the character class kept reading correctly, and the tripwire stepped over it. Verified against the real file: `/[ \t\r\n]+$/y` matches only at `lastIndex` and trims nothing; `/^[ \t\r\n]+/m` strips after every newline. `REGEX_LITERAL`'s flag suffix widened to `[a-z]*` so any flag — including `d`/`v`, which the old `[gimsuy]*` left outside the match entirely — is captured, and `LEADING_RULE`/`TRAILING_RULE` now permit none, so a flagged literal fails the shape check by name.
  - `[medium]` `[patch]` Correct character classes proved nothing about the rule being applied. Three forms passed every assertion with the trim dead, each confirmed against the extractor: a `value.replace(...)` whose result is dropped (JS strings are immutable, so the leading trim simply never happens), a replacement argument that is not `''` (`stripOuter('   ')` then returns `' '` — truthy, so the blank gate never fires), and `return value;` after a correct chain. Added `RETURN_SHAPE`, which full-matches the whole returned expression. Verified by mutating the real file.
  - `[medium]` `[patch]` `BLANK_GATE in source` — the guard that exists to catch the gate being bypassed — was still satisfied after the gate line was commented out, the cheapest possible way to disable it. Replaced with `BLANK_GATE_STATEMENT`, anchored to the start of a line. The same change drops the pin on the argument expression, so hoisting `this.input.value` into a local no longer reports a behavior-preserving edit as a reintroduced bug.
  - `[low]` `[patch]` The `.trim(` ban missed the one-ended forms. `trimStart`/`trimEnd` carry the same Unicode whitespace set and are exactly what a "fix" to half the rule reaches for. Banned alongside `trimLeft`/`trimRight`.
  - `[low]` `[patch]` `tests/unit/test_scan_router.py:873` pointed at `tests/unit/test_scan_routes.py::TestCleanScanInput` — a class this same change moved to `tests/unit/test_scan_input.py`. A stale location reference introduced by the change that exists to remove them. Re-aimed.
  - `[low]` `[patch]` `tests/unit/test_scan_trim_rule.py`'s module docstring was not raw, so its `\s` raised a `SyntaxWarning` (a `SyntaxError` in a future Python) and its `\t\r\n` became real control characters — corrupting the one paragraph explaining why the extraction is strict, in a file about two copies being spelled identically. Opened as `r"""`.
  - `[low]` `[patch]` `TestPurity` asserted `imports == []`, stricter than the contract the module states ("standard library only") and than every sibling it cites — `from typing import Optional` would have turned it red with a message claiming a dependency for every consumer. Now bans `app.*`, relative and third-party imports only, and names the offending module and line instead of printing raw AST node reprs.
  - `[low]` `[patch]` `app/utils/scan_input.py` named `category.py` as a precedent for "no `app.*` imports"; `category.py` imports `.sql_text`. Removed from the list, with the exception stated rather than implied.

Rejected: pinning the two `.replace()` calls in leading-then-trailing order (documented as the invariant, and the alarm names the literal it found); the file-wide `.trim(` ban firing on a comment (a deliberate, documented trade from the previous pass — narrowing it re-opens the hole it closed); duplication between the doctest examples and `TestCleanScanInput` (the spec asked for both, and a doctest is documentation); past-tense narration of the move in four comments (the spec asked for the `_SCAN_LOG_CHARS` one by name); the AC "`MAX_SCAN_LENGTH` stays resolvable in `routes`" having no test (a grep-level acceptance, verified at review time); and, again, the import style at `app/main/routes.py:30` — adjudicated in the previous pass and unchanged since.

### 2026-07-27 — Review pass (follow-up 2)
- intent_gap: 0
- bad_spec: 0
- patch: 7: (high 0, medium 2, low 5)
- defer: 0
- reject: 9: (high 0, medium 0, low 9)
- addressed_findings:
  - `[medium]` `[patch]` The blank-gate liveness check was defeated by a block comment. The previous pass anchored `BLANK_GATE_STATEMENT` to the start of a line specifically because "commenting the gate out is cheaper still" — but a line anchor only defeats `//`; wrapping the gate in `/* … */` leaves its own line untouched and still matching. Verified against the real file: `_blank_gate_is_live` returned `True` with the gate dead. The search now runs over comment-stripped source (`JS_COMMENT`), scoped to this check so the deliberately comment-inclusive `.trim(` ban is unaffected, and `test_a_commented_out_blank_gate_is_not_live` now exercises both comment forms.
  - `[medium]` `[patch]` A guarded early return skipped the trim while every assertion stayed green. `RETURN_SHAPE` was applied with `.search()`, which constrains the chain but not what sits above it, so `if (value.length < 2) return value;` ahead of a correct chain passed — unlike the three forms the previous pass closed, this is live code no linter flags. Verified against the real file. The pattern is now full-matched against the function's entire body, making the chain the only statement there is; added `test_an_early_return_before_the_chain_is_an_assertion`.
  - `[low]` `[patch]` `.trim ()` — a space before the paren — evaded the `JS_TRIM_CALLS` substring test while being the same Unicode-whitespace call. Replaced with the `JS_TRIM_CALL` regex tolerating whitespace; the failure message still names the offending method. Verified by mutating the real file.
  - `[low]` `[patch]` `app/main/routes.py:26-29` contradicted `app/utils/scan_input.py:73-77` — two comments added by this same change disagreeing on whether `scan-capture.js` mirrors the length bound. The route comment said the rule is "what a captured scan is trimmed of and how long it may be … scan-capture.js mirrors it"; the docstring correctly says `MAX_SCAN_LENGTH` is deliberately not mirrored (confirmed: `#scan-input` carries no `maxlength`). Re-aimed the route comment to the trim set, with the reason the bound stays server-side.
  - `[low]` `[patch]` `scan_input.py`'s purity claim called `category.py` "the one sibling deliberately left off that list". `scan_router.py` — named as a consumer twelve lines below — imports `app.models` plus three sibling utils. Restated as the set of modules to follow rather than an inventory of the package.
  - `[low]` `[patch]` The doctest justified showing a bare data record on the claim that the format-06 header literal "is spelled in exactly one place in this tree". True of `app/`; eight test files spell it, including `test_scan_input.py` added by this same change. Scoped the claim to `app/`.
  - `[low]` `[patch]` `TestPurity` walked only `Import`/`ImportFrom` nodes while its failure message asserted a categorical no-dependency property, so `importlib.import_module('app.x')` or `__import__` in a function body would have passed. Both reviewers flagged it independently; the walk now also flags those call forms.

Rejected: the file-wide `.trim(` ban being a landmine on unrelated code or firing on a comment (adjudicated in the previous pass — narrowing it re-opens the hole it closed); that no test pins `_SCAN_TRIM`/`_clean_scan_input` being absent from `routes.py` (a grep-level acceptance verified at review time, the same adjudication the twin AC got last pass); the bare-name import at `app/main/routes.py:30` (adjudicated in both prior passes, unchanged since); duplication between the doctests and `TestCleanScanInput` (adjudicated — the spec asked for both); ticket/past-tense narration in source comments (adjudicated — the spec asked for the `_SCAN_LOG_CHARS` comment by name); CRLF/reformatting brittleness of `MEMBER_END` (speculative — Linux-only repo, no `.gitattributes`, and the failure is loud); the cost/benefit argument that the 554-line tripwire should be replaced by generating the JS class from `SCAN_TRIM` (a design alternative the Approach and Design Notes chose against, not a defect); `String.prototype.trim.call` evading the ban (speculative); and a second `\s` trim copy elsewhere in `scan-capture.js` (speculative — the gate check already pins that the gate routes through `stripOuter`).

Also noted and not counted: commit `ebb4463` carries a `deferred-work.md` edit marking DW-59 done. That is the orchestrator's own bookkeeping swept into the commit, not an edit made by this work, and the ledger is orchestrator-owned per the Never list.

## Design Notes

The JS side is asserted as *text*, not executed — this repo has no JS unit harness (see `tests/unit/test_keydown_focus_guards.py`'s own statement of that limit). Follow its shape: anchor on a marker that must exist, assert loudly when the anchor is gone, and pin the invariant rather than an identifier. Extract the class body from each regex literal in `stripOuter` and decode the two-character escapes before comparing:

```python
# `/^[ \t\r\n]+/` and `/[ \t\r\n]+$/` -> {' ', '\t', '\r', '\n'}
JS_ESCAPES = {'\\t': '\t', '\\r': '\r', '\\n': '\n', '\\\\': '\\'}
```

Both regex literals must be found and both must decode to the same set, so a change to only the leading or only the trailing rule is caught too.

`app/utils/scan_input.py` is a name choice, not a requirement of the ledger entry; what the entry requires is a pure module under `app/utils/` that the route imports.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, including the new `tests/unit/test_scan_trim_rule.py` and an unchanged `TestCleanScanInput`.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: green; the new module's `>>>` examples are collected and pass.
- `grep -n "_SCAN_TRIM\|_clean_scan_input" app/main/routes.py` -- expected: no matches.
- `git diff --stat app/static/js/scan-capture.js` -- expected: comment-line changes only; no change inside `stripOuter`'s function body.

**Manual checks (if no CLI):**
- `tests/e2e/test_wedge_scan.py` is not run here (the e2e session needs ~20 minutes and no executable JS or server behavior changed); confirm by inspection that its edits are docstring text only.

## Auto Run Result

Status: done

**Change.** The scan trim rule has one home. `MAX_SCAN_LENGTH`, `SCAN_TRIM` and `clean_scan_input` live in the pure util `app/utils/scan_input.py`; `app/main/routes.py` imports and consumes them, and `_SCAN_LOG_CHARS` stays behind as the route's own logging policy. A fast source tripwire pins the JavaScript copy (`ScanCapture.stripOuter`) against the Python set, so the two cannot drift without `nox -s tests` going red. No runtime behavior changed: the trim set is still exactly `' \t\r\n'` and `/api/scan` answers byte-identically.

This third pass changed no production behavior either. It closed two more verified false-pass holes in the tripwire — a blank gate disabled with a block comment, and a guarded early return that skips the trim — and this time by closing the *classes* rather than enumerating members of them: the return chain must now be `stripOuter`'s entire body, so there is nowhere left to put a bypass, and the gate check reads comment-stripped source. It also corrected three prose claims that were factually wrong, including two comments added by this change that contradicted each other.

**Files changed**
- `app/utils/scan_input.py` (new) — the pure module: two constants, `clean_scan_input`, and the reasoning that used to sit in route comments, with 11 doctest examples.
- `tests/unit/test_scan_trim_rule.py` (new) — reads `stripOuter` out of `scan-capture.js`, full-matches its entire body and both regex literals, decodes the JS escapes and compares each character set to `SCAN_TRIM`; guards the blank gate as a live, uncommented statement and fails loudly whenever it cannot read what it is checking. 14 self-tests cover its own alarms.
- `tests/unit/test_scan_input.py` (new) — `TestCleanScanInput` moved here verbatim, plus an AST purity test banning non-stdlib imports, static and dynamic.
- `app/main/routes.py` — three definitions removed, import added, two call sites updated.
- `tests/unit/test_scan_routes.py` — re-aimed to the new home; the trim-rule class moved out, endpoint conduct stays.
- `app/utils/scan_router.py`, `app/mariadb_catalog_service.py`, `app/request_limits.py`, `config.py`, `app/static/js/scan-capture.js`, `tests/unit/test_scan_router.py`, `tests/unit/test_scan_resolution.py`, `tests/unit/test_ecia.py`, `tests/e2e/test_wedge_scan.py` — comment/docstring only, re-aimed off `app/main/routes.py`.
- `docs/development-testing-guide.md` — doctest coverage line updated to the measured 21 items / 62 examples.

**Review.** Across three passes: 27 patches applied (7 medium, 20 low), 0 deferred, 19 rejected, no intent gaps and no spec loopbacks. This pass contributed 7 patches (2 medium, 5 low) and 9 rejections; 6 of those rejections were re-raises of findings already adjudicated in earlier passes. See the Review Triage Log above.

**Verification**
- `nox -s tests` — 2669 passed, 427 deselected.
- `nox -s doctests` — 21 passed.
- Mutation-tested against the real `scan-capture.js`, restoring it byte-identically each time (`git diff --exit-code` clean afterwards). Three mutations, each turning the fast suite red and each of which passed green before this pass: the blank gate wrapped in `/* … */`, a guarded `if (value.length < 2) return value;` inside `stripOuter`, and a spaced `.trim ()` call at the gate.
- `grep -n "_SCAN_TRIM\|_clean_scan_input" app/main/routes.py` — no matches; repo-wide, neither old name survives outside `_bmad-output/`.
- `routes.MAX_SCAN_LENGTH` (4096) and `routes._SCAN_LOG_CHARS` (512) still resolve; `from app.utils.scan_input import ...` imports with no app context.
- `git diff` on `app/static/js/scan-capture.js` since the baseline — comment lines only; `stripOuter`'s body is byte-identical.
- `nox -s e2e` not run (~20 minutes, and no executable JS or server behavior changed). No screenshot regeneration: the only JS edit is a comment.

**Residual risks**
- The tripwire reads source text and executes no JavaScript, so it proves the rule is spelled identically on both sides, is applied to the returned value as the function's only statement, and is consulted by a live gate — not that a browser behaves accordingly. A gate that calls `stripOuter` and ignores the answer still passes. `tests/e2e/test_wedge_scan.py` remains the behavioral proof and was not run in this session.
- Three consecutive review passes have each found a new way the tripwire could silently pass. This pass's fix is structural rather than enumerative, which should end that pattern, but the hit rate is why a follow-up review is still recommended.
- The known `gs1.decode` / cleaner GS-RS asymmetry (DW-67, DW-11 item (c)) is untouched and still open by design.

