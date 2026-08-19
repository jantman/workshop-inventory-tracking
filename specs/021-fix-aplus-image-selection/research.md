# Phase 0 Research: A+ Description Images

**Feature**: [spec.md](spec.md) | **Date**: 2026-08-19

**Method**: FR-014. Chrome driven against amazon.com signed in as the owner, 2026-08-19. Every
finding below was read out of the **fetched** `/dp/<ASIN>` document parsed with `DOMParser` — the
same document `canonicalDocument()` hands the reader, not the rendered tab — so what is recorded
here is what the capture agent actually sees. Three listings probed: `B0FX4PDW6M` (the motivating
case), `B09GM8FB3X` and `B0DMNXC4CD` (the regression guards).

---

## 1. The cause: `#aplus` is not unique, and the wrong one wins

**Decision**: Both halves of issue #94 are one defect. `descriptionBlock()` is reading the vendor's
brand-story block and never reads the product description at all.

`B0FX4PDW6M` carries **two elements with `id="aplus"`**. They are siblings under
`#Desktop-Detailed-Evaluation-Zone`, and the brand story comes first in document order:

| Document order | Parent | `img` elements | Text |
|---|---|---|---|
| 1st `#aplus` | `#aplusBrandStory_feature_div` | **126** | 16,879 ch |
| 2nd `#aplus` | `#aplus_feature_div` | **10** | 27,904 ch |

`DESCRIPTION_CONTAINERS` is `['#productDescription', '#aplus', '#aplus_feature_div']` and
`descriptionBlock()` returns the first container with text. `#productDescription` is absent on this
listing, so it calls `doc.querySelector('#aplus')` — which by definition returns the **first match in
document order**, the one inside the brand story. Verified directly:

```text
descriptionBlockChoosesSelector: "#aplus"
chosenIsInsideBrandStory:        true
```

`#aplus_feature_div` is third in the list and is never reached, because the loop already returned.

That one line explains everything issue #94 reported:

- **The over-capture** is the brand story's 126 images (60 unique) — the vendor's other products.
  They are not getting past the size filter; they *are* the block being read.
- **The under-capture** is the entire product description, images and all. The 1464×600
  specification JPEG is in `#aplus_feature_div`, which is never opened.

**Rationale for calling this the cause rather than a cause**: simulating the current algorithm
against the real document reproduces the reported symptom exactly — 61 description images stored,
none of them the spec table. Simulating it against `#aplus_feature_div` produces 7, all of them the
product's own. There is no residual to explain.

**Alternatives considered**: the issue's three candidates were each checked against the markup and
are dealt with in §2, §3 and §4. None of them is load-bearing.

---

## 2. The issue's first candidate — lazy loading — is real, but is not why the image is missing

**Decision**: Handle it anyway, for a different reason than the one the issue gives.

Lazy loading is present exactly as issue #94 predicted. Three of the ten images in
`#aplus_feature_div` carry `class="a-lazy-loaded"`, a placeholder `src`
(`.../common/grey-pixel.gif`) and the real address in `data-src`.

But it is **not** why the spec table was missed, because Amazon pairs every lazy image with a
`<noscript>` twin carrying the same address in a plain `src`:

```text
0 src=PLACEHOLDER ds=261e0f1f… lazy=a-lazy-loaded   inNoscript=false
1 src=261e0f1f…   ds=-         lazy=-               inNoscript=true
```

`DOMParser` parses `<noscript>` content into real elements (its scripting flag is off), so
`querySelectorAll('img')` finds all three twins. Every image in the block is reachable through a
plain `src` today. Reading `data-src` recovers nothing that the twins do not already provide.

**It still has to be handled**, because of what the current code does with the placeholder:
`/^https?:/` passes on `grey-pixel.gif`, it has no dimension token and no `width`/`height`, so
`knownEdges()` returns `[]`, and FR-019's keep-on-unknown rule keeps it. **The capture is storing a
1×1 grey GIF as a product attachment.** `.gif` is in `_KNOWN_EXTENSIONS`
(`app/services/listing_images.py:45`), so nothing downstream rejects it. This happens on every A+
listing with lazy images — one placeholder on `B09GM8FB3X`, one on `B0DMNXC4CD` — and has been
happening since 007 shipped. It is unreported, and the probe found it.

**Alternatives considered**: dropping only elements with `class="a-lazy-loaded"` — rejected, it
keys on a class name rather than on the thing that is wrong (a placeholder address), and the
`<noscript>` twin means the image survives either way. Preferring `data-src` and rejecting the
known placeholder addresses does both jobs with one rule and is robust to the twins disappearing.

---

## 3. The issue's second candidate — "a container that isn't read" — is right, with the wrong mechanism

**Decision**: Read every description container, not the first with text.

Issue #94 guessed the spec-table module lived "in a sibling A+ div (`#aplus3p_feature_div`,
`#aplusBrandStory`)" that `DESCRIPTION_CONTAINERS` does not list. The container list is not the
problem — `#aplus_feature_div` **is** in the list. The problem is that `descriptionBlock()` returns
the first match and a duplicated `id` makes the second entry unreachable.

The relationship between the two selectors differs per listing, which is why the fix cannot be "just
use `#aplus_feature_div`" and cannot be "just reorder the list":

| Listing | `#aplus` inside `#aplus_feature_div`? | Brand story | Effect today |
|---|---|---|---|
| `B0FX4PDW6M` | No — a *second*, separate `#aplus` | 126 imgs, 1,836 ch of prose | **Wrong block read** |
| `B09GM8FB3X` | Yes (same block, same 22 imgs) | present but **empty** | Correct block, by luck |
| `B0DMNXC4CD` | Yes (same block, same 4 imgs) | present but **empty** | Correct block, by luck |

On two of three listings the brand-story div exists and is empty, so the defect is invisible. It
bites only when the vendor has actually published a brand story. Reordering the list would fix
`B0FX4PDW6M` and would remain a coin-toss on the next listing that nests things differently;
gathering every container and excluding the brand story by subtree is decided by structure rather
than by which selector happened to sort first.

---

## 4. The issue's third candidate — a misleading `width`/`height` — does not occur

**Decision**: No change to `knownEdges()`. The 300-pixel rule is not implicated anywhere.

No image in any of the three `#aplus_feature_div` blocks carries `width` or `height` attributes at
all. Their addresses carry a **double-underscore** transform token —
`.__CR0,0,1464,600_PT0_SX1464_V1___.` — which matches neither of `knownEdges()`'s single-underscore
patterns, so it returns `[]` and FR-019 keeps the image. That is the correct outcome by accident,
and it is left alone: the images are 1464×600, they should be kept, and they are kept.

`withoutTransform()`'s `/\._[^./]*_\./` **does** match the double-underscore token and strips it
correctly. Confirmed by loading three of the stripped addresses:

```text
261e0f1f 1464x600     eee9f851 1464x600     bdc74706 1464x600
```

1464×600 is exactly the dimension #80 item 10 named for the image that went missing. The fix
recovers it at full resolution, satisfying FR-007 with no code change.

**Alternatives considered**: extending `knownEdges()` to parse the double-underscore token —
rejected under Principle I. It would let the reader *establish* 1464×600, which changes nothing:
1464 and 600 both clear 300, so the image is kept either way. Machinery with no behavioral
difference.

---

## 5. The brand story's real identity

**Decision**: Exclude the `#aplusBrandStory_feature_div` subtree.

Issue #94 offered `.aplus-brand-story-card` and `#aplusBrandStory` "from memory of the markup, not
from this page". The real container is **`#aplusBrandStory_feature_div`**. Its contents use
`apm-brand-story-*` and `a-carousel-*` class names (`apm-brand-story-carousel-container`,
`aplus-brand-story-hero`, `apm-brand-story-background-image`, …); there is no
`.aplus-brand-story-card` and no bare `#aplusBrandStory`.

The `_feature_div` wrapper is the right handle rather than any of the inner classes: it is one
stable id, it wraps the whole region including the `#aplus` clone that causes the defect, and it is
present-but-empty on listings without a brand story, so testing for it is safe everywhere.

Its prose is the company's marketing bio, not the product:

> From the brand — As a global leader in advanced display solutions, ELECROW is at the forefront of
> the evolution of HMI interactive screens…

against the real description, which opens with the specification table as text:

> Product description … Specification of 5.79inch E-Paper HMI Display Size 5.79 inch MCU
> ESP32-S3-WROOM-1-N8R8，up to 240 MHz

**This falsifies spec FR-011 and the "description text is out of scope" assumption** — see §7.

---

## 6. Simulated before/after on all three listings

The current algorithm and the proposed one, both run against the real fetched documents:

| Listing | Description images today | of which placeholder | Proposed | Real images lost |
|---|---|---|---|---|
| `B0FX4PDW6M` | **61** | 1 grey pixel | **7** | **none** |
| `B09GM8FB3X` | 15 | 1 grey pixel | 14 | **none** |
| `B0DMNXC4CD` | 3 | 1 grey pixel | 2 | **none** |

The 61 is the number #80 §1b warned about ("anything near 57 means the size filter is not
working") — and the size filter is working perfectly. It was the wrong block.

The only thing any listing loses is the grey-pixel placeholder. `B09GM8FB3X` and `B0DMNXC4CD` each
drop from *n* to *n*−1 for that reason and for no other; every real image they capture today they
still capture. That is a **correction to spec SC-004 and FR-013**, which as written forbid any
reduction — see §7.

Gallery images are untouched throughout, so total reported counts are these plus 6, 7 and 7.

---

## 7. Corrections the probe forces on the specification

Two requirements written before the markup was known are wrong, and one assumption is falsified.
All three are amended in `spec.md`; they are recorded here because the amendment must be traceable
to the observation that caused it.

| Spec item | As written | Why it cannot stand | Amended to |
|---|---|---|---|
| **FR-011** | "MUST NOT change the captured description text" | The defect *is* that the wrong block is read. Fixing which block is read necessarily changes `description_text` on `B0FX4PDW6M` — from the vendor's company bio to the product's actual description, which is what the operator wanted all along. Holding FR-011 would forbid the fix. | The description text MUST be read from the same corrected block; the brand story's prose MUST NOT be captured as the product's description. |
| **FR-013 / SC-004** | "MUST NOT lose any image they capture today" | Every A+ listing with lazy images captures a 1×1 grey placeholder today. The fix drops it. That is a gain. | Carve out the placeholder explicitly: no *real* image may be lost. |
| **Assumption: "Description text is out of scope"** | Scoped out to avoid regressing #91 | #91 cleaned *how* text is stripped, which is orthogonal and untouched here. The block *selection* is this defect. Excluding text from scope would leave `B0FX4PDW6M` with a company bio as its description and the spec table still missing from `description_text`. | Removed. Text and images move together because they come from the same block. |

**#91 is not at risk.** It changed `proseFrom`/`proseOf` — the stripping. Nothing here touches those
functions; the same stripping runs on a different block. The three pre-#91 assertions in
`test_the_rich_description_is_kept_and_its_furniture_is_not` (title, brand, price, specification
names) are unaffected and stay as the "nothing else moved" guard.

---

## 8. What the fixture must gain

FR-015 requires the fixture to carry the real shapes. `amazon_listing_aplus.html` today has none of
them — which is precisely why a passing suite shipped this bug. It needs:

1. **A `#aplusBrandStory_feature_div` containing its own `<div id="aplus">`** that comes *before*
   the real one in document order, holding large cross-sell images and its own prose. Without the
   duplicate `id` in the earlier position, the fixture cannot exhibit the defect at all.
2. **A `#aplus_feature_div` wrapping the real `<div id="aplus">`** — the nesting that
   `B09GM8FB3X` and `B0DMNXC4CD` have, so both structural variants are covered.
3. **A lazy image**: `src` pointing at a grey-pixel placeholder, `class="a-lazy-loaded"`, real
   address in `data-src`, plus its `<noscript>` twin.
4. **A double-underscore transform token** (`.__CR0,0,1464,600_PT0_SX1464_V1___.jpg`) on at least
   one image, so `withoutTransform()`'s handling of the real token shape is covered rather than
   assumed.

The existing furniture images (1×1 spacer, 970×20 rule, 16×16 bullet, 150px mark) stay exactly as
they are: they are what proves the 300-pixel rule still works after the block selection changes.

---

## 9. Decisions carried into Phase 1

| Decision | Rationale |
|---|---|
| Gather images from **all** description containers, deduplicated | FR-003. Handles both nestings without depending on selector order. |
| Exclude the `#aplusBrandStory_feature_div` subtree before anything else | FR-004/FR-005. Position, not size. One stable id. |
| Take `data-src` in preference to a placeholder `src`; reject known placeholder addresses | §2. Kills the stored grey pixel, and survives the `<noscript>` twins going away. |
| Read description **text** from the corrected block too | §5, §7. Same root cause; splitting them would leave the reported symptom half-fixed. |
| `knownEdges()`, `MIN_DESCRIPTION_EDGE` and `withoutTransform()` unchanged | §4. Nothing about the size rule is implicated. |
| No server-side change | The filter runs in the browser by design (007); the payload contract does not change. |
