# Phase 0 Research: Gallery Image Counts

**Feature**: [spec.md](spec.md) | **Date**: 2026-08-20

**Method**: FR-001 through FR-005. Chrome driven against amazon.com signed in as the owner, with the
owner present, 2026-08-20. Every count below was read out of the **fetched** `/dp/<ASIN>` document
parsed with `DOMParser` — the same document `canonicalDocument()` hands the reader — and the two
headline listings were additionally measured against the live rendered tab to confirm the two paths
agree. All six of #57's ASINs were probed: the two the issue names, and the other four once the
first two showed the cause was not listing-specific.

**Admissibility (FR-004)**: every fetch returned HTTP 200 with the listing's own `#productTitle`
present and correct. No robot check, no redirect away from the ASIN. `B0CKXJLP4B` resolved to
`?th=1` (its default variant), which is recorded in §4 because it matters.

---

## 0. The answer in one table

Read 2026-08-20. **"Gallery"** is the number of entries in the listing's own gallery data — the
figure 007 FR-003 is about. **"Agent today"** is what `galleryFrom()` actually returns against this
document. **"Whole page"** is every distinct `hiRes` address anywhere in the document, family-wide.

| ASIN | Gallery entries | of which `hiRes` null | **Agent today** | Thumbnails | Whole page | #80 §1b expected |
|---|---|---|---|---|---|---|
| `B0CKXJLP4B` | **7** | 0 | **14** | 7 | 14 | 14 |
| `B099F4X4Q9` | **7** | 2 | **12** | 7 | 16 | 16 |
| `B01N4OSKWE` | **3** | 0 | **6** | 3 | 3 | 3 |
| `B0DMNXC4CD` | **7** | 0 | **14** | 7 | 7 | ≥ 7 |
| `B09GM8FB3X` | **8** | 2 | **14** | 7 | 11 | ≥ 11 |
| `B0FX4PDW6M` | **7** | 0 | **14** | 6 | 9 | ≥ 9 |

Two things fall out of that table and they are the whole of this feature:

1. **The "Whole page" column reproduces #80 §1b's expected column exactly, six for six** — 14, 16,
   3, 7, 11, 9. §1b's numbers are not aged. They were measuring a different thing from the start.
2. **The "Agent today" column is roughly double the gallery**, never short of it. The reported
   symptom was a shortfall; what is actually happening is an over-collection of low-resolution
   duplicates.

---

## 1. The cause: the JSON parse has never run, on any listing

**Decision**: `initialImageArray()` cannot match real Amazon markup. Every capture since feature 007
shipped has been answered by `sweepImageAddresses()`, the fallback that exists for the case where
the block "is not shaped the way this expects".

The agent looks for the array with:

```js
const marker = text.slice(anchor).search(/["']initial["']\s*:\s*\[/);
```

which requires the `[` to follow `initial':` directly. What the listing actually serves is:

```js
'colorImages': { 'initial': A.$.parseJSON('[{"hiRes":"https://m.media-amazon.com/images/I/81flPsAWG-L._AC_SL1500_.jpg", …
```

The array is the argument of a `parseJSON` call, inside a **single-quoted JavaScript string**. There
is a function name and a quote between the colon and the bracket, so the marker search returns `-1`
and `initialImageArray()` returns `null` before it parses anything.

Measured on all six listings, from the fetched document:

```text
B0CKXJLP4B  MARKER_MISS      B0DMNXC4CD  MARKER_MISS      B09GM8FB3X  MARKER_MISS
B099F4X4Q9  MARKER_MISS      B01N4OSKWE  MARKER_MISS      B0FX4PDW6M  MARKER_MISS
```

Six for six, including on the live rendered document as well as the fetched one. There is no listing
in the probe set on which the parse path executes.

**Rationale for calling this the cause rather than a cause**: simulating the current algorithm
against each real document reproduces the "Agent today" column exactly, and parsing the `parseJSON`
payload by hand produces the "Gallery" column exactly. Nothing is left over.

**Why it was never noticed**: the fallback is silent. `galleryFrom()` sweeps and returns a plausible
number, and no line of code and no line of output distinguishes "parsed the gallery" from "swept the
script". This is spec FR-009's justification, arrived at from the other direction.

---

## 2. What the sweep returns, and why it is roughly double

`sweepImageAddresses()` matches `hiRes` **and** `large`, one address per match, in document order:

```js
const pattern = /["'](?:hiRes|large)["']\s*:\s*"(https?:[^"]+)"/g;
```

One gallery entry names both, so one photograph yields two addresses. They are not two spellings of
one file — Amazon gives each rendition its own asset id, so they survive `withoutTransform()` as
distinct addresses and survive the server's content-hash dedupe as distinct bytes:

| | Address (`m.media-amazon.com/images/I/…`) | Retrieved 2026-08-20 |
|---|---|---|
| `hiRes`, as named | `81flPsAWG-L._AC_SL1500_.jpg` | 1446 × 1500, 345,670 bytes |
| `hiRes`, token stripped — **what is stored** | `81flPsAWG-L.jpg` | **1601 × 1601, 358,055 bytes** |
| `large`, as named | `512DrDtlPkL._AC_.jpg` | 471 × 488, 55,407 bytes |
| `large`, token stripped — **also stored** | `512DrDtlPkL.jpg` | **500 × 500, 62,467 bytes** |

So each captured photograph is stored twice: once as the 1601×1601 original, and once as a 500×500
copy of the same picture under a different filename. `store_listing_images()` has no reason to
suppress the second — it is a different address, it returns 200, it is a supported type, and its
bytes hash differently, so `upload_product_attachment_if_new` stores it.

The count arithmetic checks out on every listing: **entries + (entries − `hiRes` nulls)**. For
`B099F4X4Q9`, 7 + 5 = 12. For `B09GM8FB3X`, 8 + 6 = 14.

**The `hiRes: null` case is the bitter part.** `initialImageArray()`'s own docstring says the array
is "bracket-matched and parsed rather than pattern-matched, because entries whose `hiRes` is null
still name a usable `large` and a regex sweep for one key at a time cannot pair them up." That
reasoning is correct, and the code implementing it has never executed. Two of the six listings carry
`hiRes: null` entries — `B099F4X4Q9` (2 of 7) and `B09GM8FB3X` (2 of 8) — which is exactly the case
the parse was written for.

---

## 3. Where #80 §1b's numbers came from

**Decision**: §1b's expected column is the count of distinct `hiRes` addresses in the **whole
document**, which on a listing with variants includes every sibling variant's images. It is not the
gallery of the ASIN being captured, and it never was.

Issue #57's table is headed *"hi-res URLs in page data"*, and its finding 1 reads: "On two of six the
data carries more than twice what the thumbnail strip shows (16 vs 7, 14 vs 7)." Both of those are
reproduced today by sweeping the document for `hiRes` and counting unique addresses:

```text
B0CKXJLP4B   unique hiRes anywhere in the document: 14   gallery: 7   thumbnails: 7
B099F4X4Q9   unique hiRes anywhere in the document: 16   gallery: 7   thumbnails: 7
```

`B0CKXJLP4B`'s second `colorImages` block is keyed by variant — `2pcsN16R8`, `3pcsN16R8`, `2pcsN8R2`,
`10pcsN16R8`, `3pcsN8R2`, `5pcsN16R8`, `2pcsN16`, `1pcsN16R8` — one lead image each. Seven gallery
images for the pack the operator is buying, plus eight pack-variant lead images, deduped to 14.
`B099F4X4Q9` is the same shape with size variants (`15.3x15.5mm 30pcs` and siblings) and reaches 16.

**This makes two of §1b's instructions wrong, not stale:**

* **The expected counts.** 14 and 16 describe the variation family. The item being captured has 7.
* **The inference in B1** — "Seeing the *thumbnail* number instead means the gallery is being read
  from the DOM rather than the page's inline data." On both of these listings the gallery and the
  thumbnail strip are both 7, so the thumbnail number **is** the right answer and always was. The
  check as written can only be failed by being correct.

The verifier's own observation in issue #95 — "I also only see 7 images on the page" — was right, and
was the most reliable number in the whole report.

**Alternatives considered.** That #57 double-counted by matching `hiRes` and `large` was the leading
hypothesis going in (7 × 2 = 14 is suggestive). It is wrong: `B01N4OSKWE` would then have been 6 and
#57 recorded 3, and `B09GM8FB3X` would have been 16 rather than 11. Whole-page unique `hiRes` fits
all six exactly; nothing else tried fits more than two.

---

## 4. The variant question (FR-003)

**Decision**: both headline listings publish per-variant image sets, and the fetched document names
the **default** variant's gallery, not necessarily the one the operator is looking at.

`B0CKXJLP4B` is a variation family ("Set name: 3pcsN16R8", eight pack options). The tab the owner
opened redirected to `/dp/B0CKXJLP4B?th=1`, and `canonicalDocument()` fetches
`location.origin + '/dp/' + asin` — **without** `th=1` or any variant selector. Both returned the
same seven-entry gallery today, so nothing is currently mis-attributed, and the ASIN is itself the
variant identifier, which is what makes that safe.

It is recorded because it is the one thing that could make a correct count move later, and because a
future reader comparing two captures of "the same listing" needs to know the family exists. No code
change is required for it and none is proposed: spec FR-007 is satisfied as things stand.

---

## 5. The FR-004 anchor is intact — no re-anchoring needed

**Decision**: US4's re-establishment is a **no-op**. Measured from the CDN on 2026-08-20:

```text
81flPsAWG-L._AC_SL1500_.jpg   1446 × 1500   345,670 bytes   (the tokened rendition)
81flPsAWG-L.jpg               1601 × 1601   358,055 bytes   (the original)
```

Identical to what #57 recorded on 2026-08-09 and to what `capture-agent.js:405` says in its comment.
`B0CKXJLP4B` still publishes that image, it is still the first gallery entry, and #80 §1b's B4 check
can be run and passed or failed exactly as written. Nothing in FR-017 needs to change a number; what
it needs is for the check to keep saying which figure means what, and it already does.

**One correction B4 does need**: it says "check a stored original", and today *half* the stored
images are 500 × 500 renditions. A verifier who measures the wrong one sees 500 × 500 / 62,467 and
has no way to tell that from the FR-004 failure mode (1446 × 1500 / 345,670). Once §6's fix lands,
every stored gallery image is an original again and the ambiguity goes away — but B4 should name the
image by its filename stem, not by "a stored original".

---

## 6. What the fix is

**Decision**: read the array wherever the listing puts it, and take **one** address per gallery
entry. Two changes in `app/static/js/capture-agent.js`, both inside the gallery section:

* **`initialImageArray()`** must find the array when it is the argument of a `parseJSON` call inside
  a quoted string, as well as when it is a bare literal. The bracket-matching and `JSON.parse` that
  follow are correct as they stand and are not touched — the payload inside the quotes is plain JSON
  and parses cleanly, verified on all six listings.
* **`sweepImageAddresses()`** must stop emitting two addresses per entry. It is the last resort for a
  block this does not understand, and a last resort that doubles every gallery is worse than one that
  returns the `hiRes` addresses alone — a missed `hiRes: null` entry costs one image, where today's
  behaviour costs a duplicate on every image. With the parse working, this path stops being reached
  on any known listing anyway.

**Expected effect**, from the probe's numbers — every listing loses its low-resolution twins and
nothing else:

| ASIN | Today | After | What is lost |
|---|---|---|---|
| `B0CKXJLP4B` | 14 | **7** | 7 × 500 px duplicates |
| `B099F4X4Q9` | 12 | **7** | 5 × duplicates; the 2 `hiRes: null` entries keep their `large` |
| `B01N4OSKWE` | 6 | **3** | 3 × duplicates |
| `B0DMNXC4CD` | 14 | **7** | 7 × duplicates |
| `B09GM8FB3X` | 14 | **8** | 6 × duplicates |
| `B0FX4PDW6M` | 14 | **7** | 7 × duplicates |

**Alternatives considered and rejected:**

* **Match the whole page for `hiRes`, to make the capture agree with §1b's 14.** This is what the
  numbers superficially ask for and it is exactly wrong: it would capture the vendor's other pack
  sizes as photographs of the item bought. §1b is what changes here, not the extractor.
* **Dedupe by asset id or by fetched byte size.** Treats the symptom. The two addresses are two
  different files and no address-level rule distinguishes "the same photo at 500 px" from "a second
  photo"; the entry already told us, and the entry is what should be read.
* **Drop `sweepImageAddresses()` entirely now that the parse works.** Tempting under Principle I, and
  declined: the parse is one listing-shape change away from failing again, and this feature is the
  direct result of not noticing when that happened. Keep the fallback, make it emit one address per
  entry, and make it say so (FR-009).
* **Parse with a JavaScript evaluator instead of string-matching.** No. The document is untrusted
  third-party markup, the payload is plain JSON once located, and `JSON.parse` already handles it.

---

## 7. The suite passed throughout, and why

`tests/e2e/fixtures/amazon_listing.html` writes the block as:

```js
'colorImages': { 'initial': [
  {"hiRes":"…","thumb":"…","large":"…","variant":"MAIN"},
```

— a bare array literal, which is the one shape `initialImageArray()` can find. The fixture exercises
the parse path; production has only ever exercised the sweep. The fixture's six entries include one
with `"hiRes":null`, so the suite even covers the `large`-fallback logic — on a path that never runs
against a real listing.

This is the same failure feature 021 found in the A+ fixture, one feature later: markup written to
make a test pass rather than copied from what the vendor serves. Spec FR-019 is therefore specific —
the fixture must carry `A.$.parseJSON('…')` — and the honest test is that reverting the fix must turn
the suite red.

---

## 8. What the probe did *not* settle

**The "Captured 7" in issue #95 is not reproducible today, on either listing.** Against both the
fetched and the live document, `galleryFrom()` returns 14 for `B0CKXJLP4B` and 12 for `B099F4X4Q9`,
and the confirmation panel renders `listing.images | length` — the raw payload count — so it would
read 14 and 12 rather than 7 and 7.

Recorded as unresolved rather than explained away. The candidates, in the order they are worth
testing, and all of them cheap once the app is running:

1. **The panel was not what was read.** "Captured 7" may be a count of what ended on the product, and
   `B0CKXJLP4B` had been captured before in the same pass (#80 §1c C1 asks for exactly that) — a
   re-capture stores nothing new and reports duplicates.
2. **The listing changed between 2026-08-16-ish and today.** Possible and unfalsifiable after the
   fact, which is precisely why every number in this document carries its date.
3. **A capture that fell back to the live tab under a different page state.** Ruled out for today —
   both paths were measured and agree — but not for the day it was observed.

**This does not block the fix.** The defect established in §1 and §2 is present on all six listings
today, is independent of which number the verifier read, and is fixed the same way regardless. The
first task of implementation is to run one real capture and record what the panel says, which settles
this as a by-product.

---

## 9. Consequences for data already captured

Every product captured since feature 007 shipped carries **roughly twice the gallery images it should**,
half of them 500 px copies. They are real attachments with real bytes; nothing is corrupt and nothing
is lost.

The remedy is the operator's, not this feature's, and the spec says so: no hand-editing of the
database. Bulk photo deletion (#96, PR #102) is the tool, and the low-resolution copies are
recognisable — same picture, visibly smaller, and they sort adjacent to their originals because the
sweep emits them in `hiRes`, `large`, `hiRes`, `large` order and the filename index follows. Worth a
line in the quickstart, and worth mentioning in #80 §1b so the next pass does not read the duplicates
as a capture bug of their own.
