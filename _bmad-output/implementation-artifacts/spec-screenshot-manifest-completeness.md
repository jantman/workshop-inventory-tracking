---
title: 'Screenshot manifest completeness (DW-58)'
type: 'bugfix'
created: '2026-07-27'
status: 'done'
baseline_revision: 'ce58351e33e6e8b10414832607cca567b7792d2b'
final_revision: '15dcc04eeb2de5ba97ccf6b051b8fb497ce1574f'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** `docs/images/screenshots/metadata.json` records exactly one screenshot (`user-manual/batch_operations_menu.png`) even though a full run writes twelve, because `ScreenshotGenerator` is rebuilt per test by a function-scoped autouse fixture and `save_metadata()` truncates the file with only that test's captures. Nothing reads the manifest, so `nox -s screenshots_verify` cannot tell a complete regeneration from a partial one, nor a stale PNG from a missing one.

**Approach:** Accumulate manifest entries across the whole pytest session so the file records every capture the run wrote (filename, capture type, timestamp, viewport, hide-selectors); make `tests/e2e/screenshot_config.yaml` a truthful declaration of the expected capture set by tagging each definition `required` / `conditional` / `planned`; and add a real verifier module that `nox -s screenshots_verify` runs to cross-check manifest ↔ on-disk PNGs ↔ configured set, on top of the existing size/mode checks.

## Boundaries & Constraints

**Always:**
- `ScreenshotGenerator`'s existing public API (`capture_full_page`, `capture_element`, `capture_viewport`, `save_metadata`, `get_screenshot_count`, `get_metadata`, `self.metadata`) keeps working when constructed as `ScreenshotGenerator(page)` — the shared manifest is an optional constructor argument.
- Manifest output is deterministic: entries sorted by `filename`, one entry per filename (a re-capture replaces, never duplicates), file ends with a newline.
- Every manifest entry carries `filename`, `capture_type`, `timestamp`, and a `details` dict that always contains `viewport_size` and `hide_selectors` keys (null allowed), for all three capture methods.
- The verifier keeps the current quality gate intact: at least one PNG present, every PNG < 500 KB and RGB/RGBA.
- `nox -s screenshots_verify` must exit 0 against the committed tree at the end of this work.

**Block If:**
- A full `nox -s screenshots_headless` run cannot be made to produce a manifest covering all `required` captures (e.g. the e2e harness cannot start here). Do not hand-write or synthesize `metadata.json` content.

**Never:**
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`.
- Do not delete the seven aspirational capture definitions from `screenshot_config.yaml`; they are planned work, not dead config.
- Do not change what the screenshot tests capture, add new captures, or make conditional captures unconditional.
- Do not wire `screenshots_verify` into `nox.options.sessions`.
- Do not rewrite `docs/images/screenshots/VERIFICATION.md` (a stale hand-written 2025 report; out of scope).
- Do not add a `screenshot` marker registration or touch `pytest.ini` (tracked separately as DW-102).

## I/O & Edge-Case Matrix

Verifier input = (`docs/images/screenshots/` tree, `metadata.json`, `screenshot_config.yaml`). Output = list of issue strings; empty ⇒ exit 0, non-empty ⇒ printed and exit 1.

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Complete run | Manifest lists every on-disk PNG; all `required` outputs present | No issues; summary prints counts incl. skipped `conditional` and `planned` | No error expected |
| Partial regeneration | A `required` config output has no manifest entry | Issue: `<output>: required capture missing from manifest` | exit 1 |
| Stale/orphan PNG | PNG on disk with no manifest entry | Issue: `<file>: on disk but not recorded in manifest` | exit 1 |
| Recorded but missing file | Manifest entry whose PNG does not exist | Issue: `<file>: recorded in manifest but missing on disk` | exit 1 |
| Unconfigured capture | Manifest filename matching no config `output` | Issue: `<file>: not declared in screenshot_config.yaml` | exit 1 |
| Planned capture appeared | Manifest entry for a `capture_status: planned` output | Issue: `<name>: captured but marked planned; update capture_status` | exit 1 |
| Conditional skipped | `conditional` output absent from manifest and disk | Reported as an informational note only | No error expected |
| Missing/corrupt manifest | `metadata.json` absent or not valid JSON | Issue naming the file and cause | exit 1 |
| Malformed entry | Entry lacking `filename`/`capture_type`/`timestamp`, or `details` lacking `viewport_size`/`hide_selectors` | Issue naming the entry index and missing key | exit 1 |
| Duplicate entries | Two manifest entries with the same `filename` | Issue: `<file>: duplicate manifest entry` | exit 1 |
| Bad config | Missing/invalid `capture_status`, or two definitions sharing an `output` | Issue naming the definition | exit 1 |

</intent-contract>

## Code Map

- `tests/e2e/screenshot_generator.py` -- `ScreenshotGenerator`; `self.metadata` built fresh in `__init__` (:31), appended in `_record_screenshot` (:269), truncate-written in `save_metadata` (:288). All three change.
- `tests/e2e/test_screenshot_generation.py` -- function-scoped autouse fixture `setup_screenshot_generator` (:32-39) that discards accumulation; 14 capture call sites, 9 unconditional and 5 guarded by runtime `if`/`try`.
- `tests/e2e/screenshot_config.yaml` -- 20 capture definitions; currently read by nothing at runtime. Gains `capture_status` on every entry plus one new `label_printing` entry.
- `tests/e2e/screenshot_config_loader.py` -- `ScreenshotConfig` accessors + `validate_config`; the verifier reads config through this.
- `tests/e2e/screenshot_verifier.py` -- NEW. Verification logic, importable and runnable as `python -m tests.e2e.screenshot_verifier`.
- `noxfile.py:264-321` -- `screenshots_verify`, currently an inline `python -c` string installing only Pillow.
- `tests/unit/test_screenshot_infrastructure.py` -- existing unit tests for generator + config; extended here.
- `docs/images/screenshots/GENERATION_GUIDE.md` -- generation/verification docs; never mentions the manifest today.

## Tasks & Acceptance

**Execution:**
- [x] `tests/e2e/screenshot_generator.py` -- add a module-level `new_manifest()` helper and an optional `manifest=None` constructor arg that, when given, is shared instead of creating a fresh dict; normalise `_record_screenshot` to always emit `viewport_size` and `hide_selectors` in `details` and to replace-by-filename instead of appending duplicates; make `save_metadata` sort entries by filename and write a trailing newline -- so the manifest is a complete, stable, per-run inventory.
- [x] `tests/e2e/test_screenshot_generation.py` -- add a session-scoped `screenshot_manifest` fixture returning `new_manifest()`, and have the autouse fixture pass it into `ScreenshotGenerator` -- so every test's captures land in one manifest that is rewritten in full after each test.
- [x] `tests/e2e/screenshot_config.yaml` -- add `capture_status` to every definition (`required` for the 9 unconditional captures, `conditional` for `bulk_creation_preview`, `photo_copy_workflow`, `history_view`, `batch_selection_options`, `planned` for the 7 with no capture code); fix `batch_selection_options.output` to `user-manual/batch_operations_menu.png`; add a `label_printing` definition (`conditional`, output `user-manual/label_printing.png`, test `test_screenshot_label_printing`); correct the five `test:` values that name non-existent methods on required/conditional entries -- so the configured set is a truthful contract the verifier can assert against.
- [x] `tests/e2e/screenshot_verifier.py` -- NEW: `verify(screenshot_dir, config) -> list[str]` implementing every row of the I/O matrix plus the existing size/mode checks, and a `main()` that prints issues or a summary and exits 0/1 -- so verification is real code, unit-testable, not an inline string.
- [x] `noxfile.py` -- replace the inline `python -c` body of `screenshots_verify` with `session.install("Pillow", "PyYAML")` + `session.run("python", "-m", "tests.e2e.screenshot_verifier")`, keeping the docstring accurate about the new checks -- so the session exercises the tested module.
- [x] `tests/unit/test_screenshot_infrastructure.py` -- add unit tests for: manifest sharing across two generators, replace-by-filename, `details` normalisation for all three capture types, sorted/newline-terminated `save_metadata`, every config entry having a valid `capture_status` and unique `output`, `test:` values on required/conditional entries naming real methods in `test_screenshot_generation.py`, and one test per I/O-matrix row driving `verify()` against a `tmp_path` fixture tree -- so each failure mode is covered.
- [x] `docs/images/screenshots/GENERATION_GUIDE.md` -- document the `metadata.json` format, the `capture_status` field, and what `nox -s screenshots_verify` now enforces -- so the guide stops being the de-facto manifest.
- [x] Regenerate the manifest by running `nox -s screenshots_headless` and commit the resulting `docs/images/screenshots/metadata.json`; restore any PNG whose bytes changed but whose content did not -- so the committed manifest is a real generator artifact, never hand-written.

**Acceptance Criteria:**
- Given a full screenshot run, when it completes, then `metadata.json` contains one entry per PNG written by that run (12 at present) rather than one entry total.
- Given two `ScreenshotGenerator` instances constructed with the same manifest object, when each captures a different file, then a single `save_metadata()` call writes both entries.
- Given the committed tree, when `nox -s screenshots_verify` runs, then it exits 0 and reports the manifest, on-disk and configured counts, listing skipped `conditional` and outstanding `planned` captures as notes.
- Given a PNG is deleted from `docs/images/screenshots/` without regenerating, when `nox -s screenshots_verify` runs, then it exits 1 naming that file as recorded-but-missing.
- Given the committed tree, when `nox -s tests` runs, then it passes, including the new screenshot-infrastructure tests.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 1, medium 1, low 7)
- defer: 9: (high 1, medium 4, low 4)
- reject: 8: (high 0, medium 0, low 8)
- addressed_findings:
  - `[high]` `[patch]` A `conditional` capture whose PNG is already committed hard-failed verification as an orphan whenever its runtime guard did not fire — the common case for `history_view`, `bulk_creation_preview` and `batch_operations_menu`, which all have committed PNGs. The I/O matrix's "Conditional skipped" row only covered absence from *both* manifest and disk, so the implementation was spec-conformant but the resulting behavior contradicted what `conditional` means. `_verify_cross_references` now exempts `conditional` outputs from the orphan check and `build_notes` explains the retained PNG instead; covered by a new `test_conditional_png_on_disk_without_manifest_entry_is_not_an_orphan`, and the pre-existing orphan test was re-pointed at a genuinely undeclared leftover file.
  - `[medium]` `[patch]` A malformed config (`screenshots:` with no value, or a non-mapping definition) raised `TypeError`/`AttributeError` out of `ScreenshotConfig.validate_config()` instead of being reported; an unparseable YAML file tracebacked out of `main()`. `_verify_config` now shape-checks before delegating to the loader, a `definitions()` helper gives every other consumer a filtered view, and `main()` catches config load failures.
  - `[low]` `[patch]` `capture_type` was documented as a closed vocabulary but only checked for presence — added `VALID_CAPTURE_TYPES` validation.
  - `[low]` `[patch]` A non-string `filename` in a manifest entry was silently dropped, surfacing later as a misleading orphan/missing error — now reported directly.
  - `[low]` `[patch]` `list_png_files` globbed `**/*.png` case-sensitively, so a `.PNG` file escaped every check — now matches on lowercased suffix and skips directories.
  - `[low]` `[patch]` `_print_report` re-globbed the tree, re-`stat`ed every file, and re-loaded the manifest while discarding its error list, so a manifest that became unreadable between passes printed "Manifest entries: 0" beside a success banner — it now receives the values `verify()` already computed and tolerates a file vanishing mid-`stat`.
  - `[low]` `[patch]` `build_notes` printed "planned capture outstanding (no capture code yet)" for a planned capture that *was* in the manifest, contradicting the failure reported alongside it — now suppressed when the output is recorded.
  - `[low]` `[patch]` `save_metadata`'s docstring claimed the manifest was "byte-stable" across runs, which the per-run `generated_at`/`timestamp` fields make false — reworded to claim only stable entry ordering.
  - `[low]` `[patch]` `GENERATION_GUIDE.md` asserted "There is no hand-maintained list of screenshots" while the stale `VERIFICATION.md` sits in the same directory; listed sort-order and trailing-newline under "Guarantees the verifier relies on" though neither is checked; gave two different regeneration commands; and documented neither the filtered-run manifest-truncation hazard nor the manual `rm` needed after an `output` rename. All corrected.

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 1, low 8)
- defer: 5: (high 0, medium 2, low 3)
- reject: 11: (high 0, medium 0, low 11)
- addressed_findings:
  - `[medium]` `[patch]` A `screenshot_config.yaml` whose document root is a list or a scalar rather than a mapping raised `AttributeError` straight out of `verify()` — the one failure mode `definitions()`'s docstring explicitly promised would "yield findings rather than a traceback". The previous pass's shape check called `get_all_screenshots()` unguarded before testing anything. A new `_raw_screenshots()` helper asks without raising, `_verify_config` reports the root shape and returns, and `_collect` stops before reading `config.get_metadata_filename()` (which would raise the same way). Covered by `test_non_mapping_config_root_is_reported` and `test_scalar_config_root_is_reported_by_main`.
  - `[low]` `[patch]` A definition whose `output` was a YAML list or mapping crashed the whole run with `TypeError: unhashable type` when it reached the `configured_outputs` set comprehension. A new `_output_of()` accessor is now the single reader of the field, `_verify_config` reports the bad type by name, and every consumer skips such a definition.
  - `[low]` `[patch]` `output: ""` passed `validate_config()`'s presence check but is falsy, so the required/planned/declared cross-checks were all silently skipped for that definition and the only symptom was its PNG being reported as an orphan. Now reported as `<name>: output is empty`.
  - `[low]` `[patch]` `_verify_quality` called `path.stat()` unguarded on a listing taken moments earlier, so a PNG removed by a concurrent generation run tracebacked — while `_print_report`'s identical `stat()` was guarded by the previous pass. Now guarded symmetrically.
  - `[low]` `[patch]` A `details` value that was present but not an object (e.g. a list from a hand edit) was reported as `missing required key 'details'`, sending the reader to look for a key that is right there. Absent and wrong-typed are now distinguished, matching the adjacent `capture_type` and `filename` checks.
  - `[low]` `[patch]` `_print_report`'s docstring claimed it used the values `verify()` had already computed "so the report cannot disagree with the issues it accompanies", but `main()` re-globbed the tree and re-read the manifest to produce them, discarding the second read's error list. The design the docstring described is now real: `_collect()` does one pass and returns `(issues, disk_files, recorded)`, `verify()` keeps its spec'd list-only contract as a thin wrapper, and `main()` uses `_collect()`.
  - `[low]` `[patch]` `GENERATION_GUIDE.md` stated that `test` naming a real method is "enforced by `nox -s screenshots_verify` and by `tests/unit/test_screenshot_infrastructure.py`" — the verify session performs no such check (correctly: the I/O matrix does not ask for it), so the guide sent readers to a command that cannot catch a renamed test. Reworded to attribute that rule to `nox -s tests` alone. Also corrected "`filename` is a string relative to `docs/images/screenshots/`" under "Checked by the verifier", where only stringness is checked.
  - `[low]` `[patch]` `docs/development-testing-guide.md` still described `screenshots_verify` as the three-item size/format/mode gate, which this work replaced, and described the screenshot session's output as a bare PNG count with no mention of the manifest. Both sections updated and pointed at `GENERATION_GUIDE.md`.
  - `[low]` `[patch]` `test_capturing_definitions_name_real_test_methods` collected every `FunctionDef` in the module, so `test: "setup_screenshot_generator"` or `test: "_load_inventory_data"` would have passed — weak for the only check binding the config to real capture code. Now requires a `test_` prefix.

### 2026-07-27 — Review pass (follow-up 2)
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 1, low 5)
- defer: 3: (high 0, medium 0, low 3)
- reject: 8: (high 0, medium 1, low 7)
- addressed_findings:
  - `[medium]` `[patch]` A `config:` section holding a scalar or list, and a non-string `config.metadata_filename`, both tracebacked straight out of `verify()` and `main()` (`AttributeError: 'str' object has no attribute 'get'` / `TypeError: unsupported operand type(s) for /`). The previous pass hardened the document root and the `screenshots` key, but `_collect` then read `config.get_metadata_filename()` unguarded — `get_config_value` does `data['config'].get(...)`, so the sibling section had the same hole. A new `_metadata_filename()` asks without raising, `_verify_config` reports the bad section or value, and `_collect` bails before touching the manifest path. Covered by `test_non_mapping_config_section_is_reported`, `test_non_string_metadata_filename_is_reported` and `test_main_survives_a_non_mapping_config_section`.
  - `[low]` `[patch]` A `metadata.json` containing non-UTF-8 bytes raised `UnicodeDecodeError` past `load_manifest`'s handlers — it is a `ValueError` but neither a `JSONDecodeError` nor an `OSError` — so the I/O matrix's "Missing/corrupt manifest" row produced a traceback instead of an issue. Now caught alongside `JSONDecodeError`.
  - `[low]` `[patch]` A manifest entry with `"filename": ""` passed the stringness check and was carried into `recorded`, emitting `': recorded in manifest but missing on disk'` and `': not declared in screenshot_config.yaml'` — two issues naming nothing. Asymmetric with the `output: ""` case the previous pass fixed on the config side; now reported as `manifest entry N: 'filename' is empty` and excluded from `manifest_filenames`.
  - `[low]` `[patch]` The `definition N` fallback label used the *filtered* index while the shape check beside it used the raw one, so a malformed config could report `definition 0 must be a mapping` and `definition 0: missing or invalid capture_status` about two different entries. Both loops now share one index space.
  - `[low]` `[patch]` `get_metadata()`'s `self.metadata.copy()` is shallow, so it handed out the live session-shared `screenshots` list — harmless when the list was per-test, but a caller's sort/pop/clear now changes what every later `save_metadata()` writes. The list is copied too.
  - `[low]` `[patch]` The `screenshots_verify` docstring in `noxfile.py` and the matching section of `docs/development-testing-guide.md` stated the manifest↔disk rule as holding "in both directions" without the `conditional` exemption that actually governs it — `GENERATION_GUIDE.md` carries the caveat, these two did not, so a reader would expect an orphan conditional PNG to fail the gate. Both corrected.

## Design Notes

The three `capture_status` values encode why a configured capture may legitimately be absent, which is what makes "manifest covers the configured set" assertable at all: `required` captures are written unconditionally by an existing test and must appear; `conditional` ones sit behind runtime DOM guards (`if page.locator(...).count() > 0`, `try/except: return`) and may be absent; `planned` ones have no capture code yet and must be absent. Without this the assertion could only ever be red — the YAML declares 20 outputs while the tests write 14.

Manifest accumulation is in-memory and session-scoped rather than a read-merge of the existing file on save. Merging from disk would make a partial regeneration indistinguishable from a full one — the exact defect being fixed — whereas an in-memory accumulator rewritten in full after each test yields a manifest that means "what this run wrote", and is still crash-tolerant.

```python
def new_manifest() -> Dict:
    return {'generated_at': datetime.now().isoformat(), 'screenshots': []}

# in ScreenshotGenerator.__init__
self.metadata = new_manifest() if manifest is None else manifest
```

## Verification

**Commands:**
- `venv/bin/nox -s tests` -- expected: all unit tests pass, including the new `test_screenshot_infrastructure.py` cases (prefix with `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`).
- `venv/bin/nox -s screenshots_headless` -- expected: completes and writes a `metadata.json` with one entry per PNG produced (long-running; run detached with a 20-minute allowance).
- `venv/bin/nox -s screenshots_verify` -- expected: exit 0 with a summary; re-running after `rm` of one PNG exits 1 naming it.

**Manual checks (if no CLI):**
- `git diff docs/images/screenshots/metadata.json` shows a multi-entry manifest sorted by filename with a trailing newline; no PNG shows a content change in the diff.

## Auto Run Result

Status: done

### Summary

Third review pass over the DW-58 work (baseline `ce58351`). No intent gaps and no spec defects — the change still satisfies the intent contract, and `nox -s screenshots_verify` still exits 0 against the committed tree with a 12-entry manifest matching 12 PNGs and 21 declared captures.

Six patches, all in the verifier's error-reporting paths. The one that mattered closes the last member of the crash family the previous two passes worked through: a malformed `config:` section (or a non-string `metadata_filename`) tracebacked out of both `verify()` and `main()` instead of being reported. Prior passes had shape-checked the document root and the `screenshots` list; the sibling `config` mapping had the identical hole one line later. Four smaller misreport paths were closed with it, plus two documentation lines that stated the manifest↔disk rule without the `conditional` exemption that actually governs it.

### Files changed

- `tests/e2e/screenshot_verifier.py` — new `_metadata_filename()` (reads the configured manifest name without raising, reports a bad `config:` section or a non-string value); `_collect()` bails before building the manifest path when it is unusable; `load_manifest()` treats `UnicodeDecodeError` as corrupt-manifest; `_verify_entries()`/`manifest_filenames()` name an empty `filename` instead of echoing a blank subject; `_verify_config()`'s two loops share one definition index space.
- `tests/e2e/screenshot_generator.py` — `get_metadata()` copies the session-shared `screenshots` list, not just the outer dict.
- `tests/unit/test_screenshot_infrastructure.py` — +7 tests, one per patched path.
- `noxfile.py`, `docs/development-testing-guide.md` — the `conditional` orphan-check exemption added to both statements of the both-directions rule.

### Review findings

Patches applied: 6 (0 high, 1 medium, 5 low). Items deferred: 3 — DW-170 (`wait_for` selectors in the config disagree with what eight capture tests actually wait on), DW-171 (`metadata_filename`/`generate_metadata` honoured by the verifier, ignored by the generator), DW-172 (`add_item_form_readme` tagged `planned` while its `test:` names an existing test). All three appended to the ledger as new entries; no existing entry was modified or re-opened. Items rejected: 8 — chiefly findings already tracked by the previous pass's own deferrals (DW-166 for the `conditional` staleness hole, DW-167 for a zero-capture session leaving the prior manifest in place) and exotic states outside the I/O matrix (symlinked/traversing paths, non-PNG configured outputs, duplicate definition `name`s, a verify run racing a concurrent generation run).

### Verification performed

- `nox -s tests` — 2819 passed, 427 deselected (was 2812 before this pass's 7 new tests).
- `nox -s doctests` — 21 passed.
- `nox -s screenshots_verify` — exit 0: 12 manifest entries, 12 PNGs on disk, 21 configured captures (9 required / 5 conditional / 7 planned), 9 informational notes. Unchanged from the previous pass.
- Negative check on a copy of the tree with `user-manual/move_items.png` removed — exit 1 reporting `recorded in manifest but missing on disk`.
- All five patched failure modes were reproduced as tracebacks/blank-subject issues against the pre-patch code and re-run after the fix; each is now a named issue and each has a unit test.
- `nox -s screenshots_headless` was not re-run: no capture behaviour changed, so the committed `metadata.json` is untouched and remains the artifact of the real run at `acec422`.

### Residual risks

- The three deferred entries are all truthfulness gaps in `screenshot_config.yaml` rather than verifier defects: the file is now the declared contract, and its `wait_for` values (DW-170) and one `capture_status` (DW-172) still misdescribe the tests.
- `conditional` captures remain outside the completeness guarantee (DW-166) and the verifier still runs only on demand (DW-165) — both unchanged by this pass.
- Config-shape hardening has now consumed a patch in each of three consecutive passes, each time in a sibling of the previously fixed accessor. The remaining unguarded readers are the ones the verifier does not call (`get_default_viewport`, `get_optimization_quality`, `get_screenshots_by_category`); if a future change reads any of them, the same guard is needed.

