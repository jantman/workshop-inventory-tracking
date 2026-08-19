# Quickstart: validating the A+ image fix

**Feature**: [spec.md](spec.md) | **Phase**: 1

Prerequisites: `venv/` present, `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"` for nox, Docker
available for the MariaDB container the e2e session starts.

## 1. The automated suite

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests      # fast, expected unchanged
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e        # where the coverage is
```

`nox -s e2e` runs about 8m15s warm and **outruns the 10-minute bash cap** — run it detached with
`nohup` and poll, and give the tool a 15-minute timeout if running it in the foreground.

The suite must leave the working tree clean. If `docs/images/screenshots/` changed, a screenshot
test leaked into the e2e selection — that is a bug in the selection, not something to commit.

## 2. What must not move

`test_the_rich_description_is_kept_and_its_furniture_is_not` carries four assertions that are
#91's "nothing else moved" guard — the listing title, brand, price and the exact ordered list of
specification names. **This feature must not change any of them.** If they need touching, something
has gone wrong with block selection that is not visible in the image list.

The furniture cases in the same fixture — the 1×1 spacer, the 970×20 rule, the 16×16 bullet, the
150 px mark — must still be excluded. They are the evidence that the 300-pixel rule survived
(spec FR-005).

## 3. The fixture actually exhibits the defect

FR-015 is not satisfied by a test passing. Check the fixture itself:

```bash
grep -n 'aplusBrandStory_feature_div\|id="aplus"\|a-lazy-loaded\|noscript\|__CR0,0' \
  tests/e2e/fixtures/amazon_listing_aplus.html
```

Expect: a `#aplusBrandStory_feature_div` containing an `id="aplus"` that appears **before** the
real block, the real block inside `#aplus_feature_div`, a lazy image with its `<noscript>` twin, and
a double-underscore transform token.

**The ordering is the point.** Reverse the two blocks in the fixture and the new tests must still
pass while the old bug becomes unreproducible — that is how you know the fixture, not the fix, was
doing the work. Put it back afterwards.

## 4. Reverting the fix must fail the suite (SC-006)

Two separate reverts, because the defect has two halves:

- Remove the `isCrossSell` check → a test asserting the cross-sell images are absent must fail.
- Restore `descriptionBlock()`'s first-match-wins → a test asserting the real block's images are
  present must fail.

If either revert leaves the suite green, that half is untested.

## 5. The real-listing check — the one no suite can do

Capture each of the three listings through the bookmarklet against the running app and read the
confirmation page's image count *before* confirming. Recorded from the Phase 0 simulation against
the real fetched documents:

| Listing | Description images before | after | Total reported (with gallery) |
|---|---|---|---|
| `B0FX4PDW6M` | 61 | **7** | ≥ 7, well under 20 (SC-003) |
| `B09GM8FB3X` | 15 | **14** | ≥ 11 (SC-004) |
| `B0DMNXC4CD` | 3 | **2** | ≥ 7 (SC-004) |

Each of the latter two loses exactly one image and it must be the grey placeholder — every real
image they capture today they must still capture (spec FR-013 as amended).

On `B0FX4PDW6M` specifically:

- The captured images include the **1464×600 specification table** (SC-001).
- **No picture of another ELECROW product** appears (SC-002). Nothing to delete by hand.
- The captured **description** opens with the product's own text — "Specification of 5.79inch
  E-Paper HMI Display…" — and **not** "From the brand — As a global leader in advanced display
  solutions…" (spec FR-011 as amended, SC-005).

That last one is the amended requirement. If the description still reads as the company's marketing
bio, the block selection is only half fixed.

## 6. Screenshots

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify
```

`capture-agent.js` is never loaded by an application template, so this is expected to be a no-op.
Run it to establish that rather than assume it. Screenshots churn every run from two sources —
measure any diff before committing an image, and do not regenerate reflexively.
