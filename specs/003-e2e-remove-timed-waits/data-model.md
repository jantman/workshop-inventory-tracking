# Data Model

**Feature**: `specs/003-e2e-remove-timed-waits` | **Date**: 2026-08-06

This feature changes no database schema and no application data. The entities below are the units
the work counts, tracks and reports against — they exist in the test suite and in the documentation
set, not in MariaDB.

## Wait site

A single `page.wait_for_timeout(...)` or `time.sleep(...)` call in `tests/e2e/`.

| Field | Values |
|---|---|
| Location | file, line |
| Population | A (ordinary in-gate) \| B1 (move) \| B2 (photo) \| C (screenshot, out of gate) |
| Literal cost | the argument, in ms |
| Executions per run | 1 if inline in a test body; N if inside a helper, where N is its call count |
| Disposition | `converted` \| `justified` \| `open` |

**Invariant**: at completion, no site is `open`. Every site is either gone or carries a call-site
comment naming the condition that cannot be observed (FR-001, SC-003).

**Counting rule**: a site's contribution to SC-001 is `literal × executions`, not `literal`. The two
diverge by 2.14× across the gate and by 4.5× in `test_copy_item_photos.py`.

### Population census (2026-08-06)

| Population | Files | Sites | Literal | Est. executed |
|---|---:|---:|---:|---:|
| A | 17 | 42 | 37.9s | ~87.5s |
| B1 | 1 | 42 | 10.2s | ~10.2s (all inline, 1.0×) |
| B2 | 3 | 15 | 13.1s | ~23.9s |
| **In gate** | **21** | **99** | **61.2s** | **121.6s** (measured) |
| C | 1 | 28 | 20.0s | not in gate |

One further `time.sleep(0.1)` exists in `tests/e2e/test_server.py`, inside a server-startup polling
loop. It re-checks an observable condition, so it is a readiness poll and not a wait site (FR-004).

## Readiness signal

An observable property of the running application that certifies an action completed. Enumerated in
[contracts/readiness-signals.md](./contracts/readiness-signals.md).

| Field | Values |
|---|---|
| Element | a selector present in the served DOM |
| Certifies | the transition or completion it proves |
| Timing | `synchronous` \| `post-await` |
| Sufficiency | `complete` \| `partial` — partial signals must be paired |

**Invariant**: a signal may not be settable before the work it certifies has completed. A
`synchronous` signal is invalid for any completion behind an `await`.

**Invariant**: an action whose signals are all `partial` requires every one of them to be awaited.
The move page's finalise-previous branch is the only known instance.

## Documentation location

| Location | Role today | Role after |
|---|---|---|
| `.specify/memory/constitution.md` §IV | states the rule, points at the contract | states the rule and its exception — governance |
| `CLAUDE.md` | short version, points at the contract | **normative source** for practice |
| `docs/development-testing-guide.md` | summary, points at the contract | summary, points at `CLAUDE.md` |
| `_bmad-output/project-context.md` | summary, points at the contract | summary, points at `CLAUDE.md` |
| `tests/e2e/waits.py` docstring | points at the contract | points at `CLAUDE.md` |
| `specs/002-.../contracts/e2e-test-authoring.md` | normative source | superseded; no live pointers |

**Invariant** (FR-023, SC-014): zero live documents direct a contributor into
`specs/002-e2e-test-performance/` to learn how to write a test.

**Invariant** (FR-025, SC-016): references citing feature 002 as *history* — the 22m 27s baseline,
the removal of the navigation-readiness wait — are preserved. The two surviving instances are
`docs/development-testing-guide.md:74` and `.specify/memory/constitution.md:14`.

**Invariant** (FR-022, SC-015): no sentence appears in both the constitution and `CLAUDE.md`.

## Measurement

| Field | Value |
|---|---|
| Instrument | the blocking-call probe, `_probe.py`, loaded via `-p tests.e2e._probe` |
| Baseline | 121.6s across 212 executions |
| Target | under 60s (SC-001) |
| Invalid substitute | summing literal arguments — understates by 2.14× |

**Invariant**: every reported figure is taken with `--reruns=0`. A retried pass is
indistinguishable from a clean one otherwise, which is what SC-006 and SC-007 exist to catch.
