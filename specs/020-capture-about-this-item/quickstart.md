# Quickstart: validating the "About this item" capture

**Feature**: `specs/020-capture-about-this-item` | **Date**: 2026-08-19

How to prove this feature works. Automated checks first, then the one thing no local test can
cover — the real vendor page.

## Prerequisites

- The repository virtualenv at `venv/` (Principle: project commands run against it). Invoke its
  binaries by path; do not `source venv/bin/activate`.
- `python3.13` on `PATH` for nox's env creation:

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
```

- Docker running, for the MariaDB container the e2e session brings up.

## 1. Unit suite

```bash
venv/bin/nox -s tests
```

Expected: green, in under a second of test time. **This feature adds nothing here.** The change is
entirely in `app/static/js/capture-agent.js`; there is no Python behavior to unit-test, and adding a
Python test that asserts something about a JavaScript file would be theatre. If a unit test does
change, something has gone wrong with the scope.

## 2. End-to-end suite

```bash
venv/bin/nox -s e2e
```

**Give this at least a 15-minute timeout** (constitution, Principle IV) — it installs Playwright
browsers and retries with `--reruns=3`. It runs about 8m15s warm, which exceeds the default 10-minute
command cap, so run it detached and poll rather than blocking on it.

The session must leave the working tree clean. If `git status` is dirty afterwards, a screenshot
test leaked into the selection.

New coverage to expect in `tests/e2e/test_product_page_capture.py`:

| Scenario | Proves |
|----------|--------|
| The bullets arrive as one `About this item` row, one bullet per line | US1 / FR-001..FR-004 |
| The row is first in the payload's `specifications` | FR-010, contract C-3 |
| The heading and the "See more product details" link are absent from the value | FR-005, R-1 |
| A fixture with no bullet list yields no row and captures otherwise unchanged | US4 / FR-008, FR-012 |
| Re-capturing the same listing leaves exactly one row, with the first capture's value | US2 / FR-009 |
| The stored value renders on its own lines and edits without flattening | FR-013 |

The existing exact-order assertion on `payload["specifications"]` (around line 508) will need
`"About this item"` at the front. That assertion is a "nothing else moved" guard from #91 — update
it, do not loosen it to a membership check.

## 3. Screenshot gate

```bash
venv/bin/nox -s screenshots_verify
```

`capture-agent.js` is under `app/static/js/**`, which the constitution's workflow section says
requires regenerating documentation screenshots. It is also never loaded by any template in this
application — the bookmarklet injects it into a *vendor's* page — so no screenshot can depend on it.
Run the verify session to establish that rather than assert it.

If it reports staleness, check whether the diff has anything to do with this change before
regenerating; screenshots in this repository churn between runs for unrelated reasons, so measure
the churn before committing any image.

## 4. The manual check that matters

Nothing local can fail when Amazon changes their markup — the e2e fixture is hand-written and served
from this application's own origin (see the module docstring of `test_product_page_capture.py` for
why it has to be). So the feature is not validated until it has run against the real thing.

1. Start the application and load the capture bookmarklet as usual.
2. Open `https://www.amazon.com/dp/B01N4OSKWE` and fire the bookmarklet.
3. On the confirmation form, check the specification row count includes the new row, then submit.
4. On the product page, confirm an `About this item` row exists and that its value contains, each on
   its own line, the five bullets — in particular the dimensions:
   `Main Body Size: 15 x 7 x 7mm/0.59"x0.28"x0.28"(L*W*H)`. **This is SC-001**, and it is the
   difference the issue is about: those dimensions appear nowhere else on that listing.
5. Repeat for `https://www.amazon.com/dp/B0FX4PDW6M`. Six bullets. **SC-002.**
6. Capture `B01N4OSKWE` a second time onto the same product and confirm there is still exactly one
   `About this item` row. **SC-004.**
7. Capture any listing with no About this item section and confirm no row appears and nothing else
   changed. **SC-005.**

As of 2026-08-19 both listings carried the markup described in research.md §1. If step 4 comes back
empty, read the live page before touching the reader — the selector may simply have moved, which is
the risk FR-011 bounds rather than removes.

## Reference

- Payload shape and its guarantees: [`contracts/listing-payload.md`](contracts/listing-payload.md)
- The reader's obligations: [`contracts/bullets-reader.md`](contracts/bullets-reader.md)
- Why no visibility test and no migration: [`research.md`](research.md), [`data-model.md`](data-model.md)
