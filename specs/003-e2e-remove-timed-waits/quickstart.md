# Quickstart: Validating the Wait Removal

**Feature**: `specs/003-e2e-remove-timed-waits` | **Date**: 2026-08-06

How to verify each success criterion. Commands assume a warm environment; discard the first run
after a clean checkout.

## Prerequisites

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"   # nox pins 3.13; system Python is 3.14
source venv/bin/activate
docker ps                                                # the MariaDB testcontainer needs Docker
```

Give `nox -s e2e` **at least a 15-minute tool timeout** (Constitution §IV).

## Rebuild the probe first (C0)

**SC-001's instrument is not in the tree.** Feature 002 kept `_probe.py` in a session scratchpad and
only a stale `.pyc` survives under `tests/e2e/__pycache__/`. Until it is rebuilt, the feature's
headline number cannot be measured — so this is the first task, not the last.

It is a pytest plugin that wraps `wait_for_timeout`, `wait_for_load_state`, `goto`,
`wait_for_selector` and `wait_for_function`, accumulates wall clock per category, and prints a
`BLOCKING-CALL PROBE` summary at session end. Keep it out of the suite:

```bash
# tests/e2e/_probe.py is NOT committed — it is loaded explicitly and deleted after
nox -s e2e -- -p tests.e2e._probe --reruns=0 --durations=0 2>&1 | tee /tmp/probe.log
grep -A10 "BLOCKING-CALL PROBE" /tmp/probe.log
rm tests/e2e/_probe.py
```

Re-confirm the baseline before changing anything. Expect the `wait_for_timeout` line to read close
to **121.6s across 212 executions**. If it does not, the tree has moved and every target below needs
restating against what you measured.

## SC-001 — wait time under 60s

Same command as above, after each change set. Reference points:

| Point | Expected `wait_for_timeout` |
|---|---|
| Baseline | 121.6s (n=212) |
| After C1 (Population A) | **~34s — target already met** |
| After C2–C4 | ~0s plus justified survivors |
| Target | under 60s |

Measured against **execution time**, never the sum of literal arguments — the two differ by 2.14×
across the gate and 4.5× in `test_copy_item_photos.py`.

## SC-002 — suite under 8m 45s

```bash
nox -s e2e -- --durations=0 --reruns=0 2>&1 | tee /tmp/e2e-run.log
tail -3 /tmp/e2e-run.log
```

| Point | Wall clock |
|---|---|
| Baseline | ~585s (9m 45s) |
| After C1 | ~510s (8m 30s) — target already met |
| Target | ≤ 525s (8m 45s) |

## SC-003, SC-004 — no unjustified survivors

```bash
# Every remaining site, with the comment above it
grep -rn -B3 "wait_for_timeout\|time\.sleep" tests/e2e/ --include="*.py"
```

Every hit must be either absent or preceded by a comment naming the condition that cannot be
observed. `tests/e2e/test_server.py`'s polling loop is out of scope (FR-004).

Produce the survivor list required by SC-004 as part of the final commit message.

## SC-005 — coverage not traded away

```bash
nox -s e2e -- --collect-only -q --reruns=0 | tail -3     # expect 362, 0 skipped
git diff main -- tests/e2e/ | grep -E "^-.*(assert |expect\()"
```

The second command is the important one. Every removed `assert`/`expect(` must be accounted for —
moved verbatim, or replaced by something checking the same thing. This matters most in
`test_shorten_items.py`, `test_toggle_item_status.py` and `test_history_functionality.py`, which
cover the Constitution §VI invariants: FR-010 permits changing *how* they wait and nothing else.

## SC-006, SC-007 — stability

Three clean consecutive runs suite-wide:

```bash
for i in 1 2 3; do nox -s e2e -- --reruns=0 -q 2>&1 | tail -2; done
```

**Ten** for the previously-reverted files — the higher bar exists because the last attempt produced
solutions that passed once and raced intermittently:

```bash
for i in $(seq 10); do
  nox -s e2e -- tests/e2e/test_move_items_sub_location.py tests/e2e/test_copy_item_photos.py \
      tests/e2e/test_photo_upload.py tests/e2e/test_photo_upload_bug.py --reruns=0 -q 2>&1 | tail -1
done
```

`--reruns=0` is what makes any of this meaningful.

## SC-008 — every test passes alone

```bash
nox -s e2e -- --collect-only -q --reruns=0 | grep "::" > /tmp/all-tests.txt
while read -r t; do
  nox -s e2e -- "$t" --reruns=0 -q >/dev/null 2>&1 || echo "FAILS ALONE: $t"
done < /tmp/all-tests.txt
```

Slow — well over an hour. Run once before merge.

## SC-009 — screenshots

```bash
git status --porcelain docs/images/screenshots/    # expect empty
nox -s e2e -- --reruns=0 -q
git status --porcelain docs/images/screenshots/    # expect STILL empty

nox -s screenshots_headless                        # expect faster than before
nox -s screenshots_verify
git checkout -- docs/images/screenshots/
```

`screenshots_verify` is the guard against capturing a Bootstrap fade mid-transition.

## SC-010 — no navigation-readiness wait

```bash
grep -rn "networkidle" tests/e2e/ | wc -l          # expect 0, unchanged
```

## SC-011, SC-014, SC-015, SC-016 — the documentation move

```bash
# SC-014: nothing sends a contributor into 002 to learn how to write a test.
grep -rn "e2e-test-authoring" CLAUDE.md docs/ _bmad-output/ tests/ .specify/memory/
# expect: no hits, or only hits pointing at the new home

# SC-016: history citations survive
grep -rn "002-e2e-test-performance" docs/development-testing-guide.md .specify/memory/constitution.md
# expect: the 22m27s baseline references still present

# SC-011: no grandfathering language anywhere
grep -rni "grandfather" CLAUDE.md .specify/memory/constitution.md docs/ _bmad-output/
# expect: no hits
```

SC-015 (no sentence in both the constitution and `CLAUDE.md`) is a read, not a grep.

## SC-012, SC-013 — the guidance actually teaches

Write one new e2e test against a multi-step asynchronous flow using **only** `CLAUDE.md` and the
constitution — without opening the converted test files. It must contain no fixed wait, pass, and
add no measurable time. Then check each documented pattern names a real call site this feature
converted; a pattern with nothing behind it was invented rather than learned (SC-012).
