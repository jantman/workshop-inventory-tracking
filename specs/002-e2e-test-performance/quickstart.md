# Quickstart: Validating the E2E Performance Work

**Feature**: `specs/002-e2e-test-performance` | **Date**: 2026-08-05

How to reproduce the baseline and verify each Success Criterion. Every command here was actually
run to produce [research.md](./research.md).

## Prerequisites

```bash
# nox sessions pin Python 3.13; the system Python is 3.14
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
source venv/bin/activate

docker ps        # the MariaDB testcontainer needs a working Docker daemon
```

Give the `e2e` session **at least a 15-minute tool timeout** (Constitution Principle IV, amended to
that figure by this work). The suite itself runs in well under 10 minutes warm; the margin covers a
cold start that has to pull the MariaDB image and download Playwright browsers.

Runs must be **warm** — dependencies installed, Playwright browsers present, MariaDB image pulled —
or cold-start noise swamps the measurement. Discard the first run after a clean checkout.

## Measuring wall clock (SC-001, SC-002)

`--reruns=0` is essential. The default `--reruns=3` lets a flaky test cost up to 4× and makes
timings meaningless.

```bash
nox -s e2e -- --durations=0 --reruns=0 2>&1 | tee /tmp/e2e-run.log
tail -3 /tmp/e2e-run.log
```

Reference results on the maintainer's machine:

| Run | Wall clock | Result |
|---|---|---|
| Baseline (2026-08-05) | **1347.58s (22m27s)** | 376 passed, 1 skipped |
| After C1 only | 981.83s (16m21s) | 370 passed, 6 failed, 1 skipped |
| After C1 + C3 | 859.32s (14m19s) | 362 passed |
| **After C1 + C2 + C3 (delivered)** | **~585s (9m45s)** | **362 passed** |
| Target (SC-001) | ≤600s (10m00s) | met |

Per-phase breakdown from the same log:

```bash
grep -E "^[0-9.]+s +(call|setup|teardown)" /tmp/e2e-run.log \
  | awk '{t=$1;sub("s","",t);T[$2]+=t;n[$2]++} END {for(p in T) printf "%-9s %8.1fs n=%d\n",p,T[p],n[p]}'
```

Baseline was `call 1245.7s / setup 90.8s / teardown 6.4s`. `call` is the number this feature moves.

## Attributing time to blocking calls (SC-008)

The probe used for the assessment is in the session scratchpad as `_probe.py`. To re-run it, drop
it at `tests/e2e/_probe.py` and load it explicitly — **delete it afterwards; it is not part of the
suite**:

```bash
cp /path/to/_probe.py tests/e2e/_probe.py
nox -s e2e -- -p tests.e2e._probe --reruns=0 --durations=0 2>&1 | tee /tmp/e2e-probe.log
grep -A10 "BLOCKING-CALL PROBE" /tmp/e2e-probe.log
rm tests/e2e/_probe.py
```

It wraps `wait_for_timeout`, `wait_for_load_state`, `goto`, `wait_for_selector` and
`wait_for_function` and reports accumulated wall clock per category.

Reference figures for the `wait_for_timeout` line, which is what SC-008 is measured against
(**not** the sum of literal arguments in the source):

| Point | `wait_for_timeout` | `networkidle` |
|---|---|---|
| Baseline | 423.9s (n=479) | ~302s |
| Delivered | **121.6s (n=212)** | **0** |
| SC-008 target | under 60s | n/a |

SC-008 is **not met**: 121.6s against a 60s target. The remainder sits in the files listed
as deferred in [plan.md](./plan.md); read that before assuming the work is finished.

## Verifying coverage was not traded away (SC-003, SC-004)

```bash
# Collected count, no execution
nox -s e2e -- --collect-only -q --reruns=0 | tail -3

# Nothing newly skipped
grep -E "SKIPPED|skipped" /tmp/e2e-run.log

# No assertions lost: review the diff, not the count
git diff main -- tests/e2e/ | grep -E "^-.*(assert |expect\()" 
```

The last command is the important one. Any removed `assert` or `expect(` must be accounted for —
either moved verbatim elsewhere, or replaced by an equivalent that checks the same thing. A removed
assertion with no replacement violates FR-011.

## Verifying isolation (SC-006) and localization (SC-007)

Every test must pass alone:

```bash
nox -s e2e -- tests/e2e/test_add_item.py::test_add_basic_item_workflow --reruns=0
```

Sweep the whole suite one test at a time (slow — expect well over an hour; run it once before
merge, not routinely):

```bash
nox -s e2e -- --collect-only -q --reruns=0 | grep "::" > /tmp/all-tests.txt
while read -r t; do
  nox -s e2e -- "$t" --reruns=0 -q >/dev/null 2>&1 || echo "FAILS ALONE: $t"
done < /tmp/all-tests.txt
```

For SC-007, break one behaviour deliberately — for example make the inventory list route return an
empty set — run the full suite, and confirm the failures all relate to that behaviour and each
reproduces on its own.

## Verifying stability (SC-005)

Three consecutive green runs with no retry consumed:

```bash
for i in 1 2 3; do
  echo "=== run $i ==="
  nox -s e2e -- --reruns=0 -q 2>&1 | tail -2
done
```

`--reruns=0` is what makes this meaningful: with retries enabled a flaky test still reports as
passed. Any failure here means the work introduced flakiness, which FR-014 forbids.

## Verifying the screenshot split (C3, FR-015)

The e2e gate must no longer generate screenshots, and must no longer dirty the working tree:

```bash
git status --porcelain docs/images/screenshots/   # expect empty
nox -s e2e -- --reruns=0 -q
git status --porcelain docs/images/screenshots/   # expect STILL empty
```

Before this change the baseline run left `metadata.json`, `history_view.png`, and
`search_results.png` modified.

Screenshot generation itself must still work:

```bash
nox -s screenshots_headless
nox -s screenshots_verify
git checkout -- docs/images/screenshots/   # discard regenerated images if unchanged in substance
```

## Verifying the documentation (SC-009, SC-010)

```bash
# The new conventions are present in all three places
grep -l "wait_for_timeout\|networkidle" CLAUDE.md docs/development-testing-guide.md _bmad-output/project-context.md

# No stale guidance survives (FR-018)
grep -rn "networkidle" CLAUDE.md docs/ _bmad-output/ | grep -v "do not use\|never\|avoid"
```

The second command should return nothing. Any remaining passage that *recommends* `networkidle` or
fixed sleeps is a failure of FR-018 — adding new guidance beside stale guidance does not satisfy it.

For SC-010, write one new test following only
[`contracts/e2e-test-authoring.md`](./contracts/e2e-test-authoring.md) and confirm it adds no
measurable time to the suite total.
