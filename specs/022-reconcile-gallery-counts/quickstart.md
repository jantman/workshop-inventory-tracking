# Quickstart: Re-deriving Every Number in This Feature

**Feature**: [spec.md](spec.md) | **Date**: 2026-08-20

Every figure this feature records was read from a live listing on 2026-08-20 and **will age**. This
page exists so the next person can re-read them in five minutes instead of reconstructing how they
were arrived at — which is the archaeology that produced issue #95 in the first place.

Spec SC-007: a verifier should be able to tell which number they should be comparing against, when
it was last confirmed, and how to re-derive it, without opening a browser first.

---

## A. The three numbers, and which one is the requirement

Do not compare a total against a total. On five of the six probed listings the gallery count and the
thumbnail count are the same number, so a total tells you almost nothing.

| Number | What it is | Is it the requirement? |
|---|---|---|
| **Gallery entries** | Entries in the listing's own `colorImages.initial` array, for the item being captured | **Yes.** 007 FR-003, and the contract |
| Thumbnails on screen | What the strip renders | No. Usually equal to the gallery; equality proves nothing either way |
| Whole-document `hiRes` | Every distinct `hiRes` address anywhere in the page, family-wide | **No, and this is the trap.** It is where #80 §1b's expected numbers came from |

---

## B. Read the gallery count from a listing (2 minutes)

Open the listing in Chrome, signed in, and paste this into the console. It reads the **fetched**
`/dp/<ASIN>` document — the one `canonicalDocument()` gives the reader — not the rendered tab.

```js
(async (asin) => {
  const doc = new DOMParser().parseFromString(
    await (await fetch(location.origin + '/dp/' + asin, { credentials: 'same-origin' })).text(),
    'text/html');
  for (const s of doc.querySelectorAll('script')) {
    const t = s.textContent || '';
    const ci = t.indexOf('colorImages');
    if (ci === -1) continue;
    const pj = t.indexOf("parseJSON('", ci);
    const q = pj !== -1 && pj - ci < 80 ? pj + 11 : t.indexOf('[', ci);
    let end = q; while (end < t.length && t[end] !== "'") end++;
    const entries = JSON.parse(t.slice(q, pj !== -1 ? end : undefined));
    return { asin, galleryEntries: entries.length,
             hiResNull: entries.filter(e => !e.hiRes).length,
             variants: entries.map(e => e.variant),
             thumbnails: doc.querySelectorAll('#altImages li.imageThumbnail').length };
  }
})('B0CKXJLP4B')
```

**Expected on 2026-08-20**: `{galleryEntries: 7, hiResNull: 0, thumbnails: 7}`.

If `galleryEntries` has moved, that is the listing changing, not a defect — record the new number
with today's date and move on. If the script throws where it did not before, the listing's markup
shape has changed and that **is** a defect: see §E.

---

## C. Check a capture against it

1. Serve the app over HTTPS and open `/products/capture`; re-drag the bookmarklet if you have not
   since the last time the app's address changed (#80 §0).
2. Click it on the listing.
3. On the confirmation page, read the **"What the listing yielded"** panel's image count *before*
   pressing Capture. It renders `listing.images | length` — the raw payload count.

**It must equal `galleryEntries` from §B, plus any description images on an A+ listing.** For the
three plain-description listings it must equal `galleryEntries` exactly.

| ASIN | Expected panel count (plain listings) | Before this feature |
|---|---|---|
| `B0CKXJLP4B` | **7** | 14 |
| `B099F4X4Q9` | **7** | 12 |
| `B01N4OSKWE` | **3** | 6 |

For `B0DMNXC4CD`, `B09GM8FB3X` and `B0FX4PDW6M` the gallery floors are **7, 8 and 7**; the panel
shows those plus the description images #94's feature selects, so treat them as floors.

---

## D. The FR-004 original-resolution check

Re-measured 2026-08-20 and **unchanged from #57's 2026-08-09 figures**.

Anchor: `B0CKXJLP4B`, first gallery entry, filename stem **`81flPsAWG-L`**.

| Address | Dimensions | Bytes | Meaning |
|---|---|---|---|
| `81flPsAWG-L.jpg` | 1601 × 1601 | 358,055 | **The original. This is what must be stored.** |
| `81flPsAWG-L._AC_SL1500_.jpg` | 1446 × 1500 | 345,670 | The tokened rendition — the FR-004 failure |
| `512DrDtlPkL.jpg` | 500 × 500 | 62,467 | The `large` twin — stored in error before this feature |

Name the stem when you check. "Check a stored original" is ambiguous while a product captured before
this feature carries both `81flPsAWG-L` and `512DrDtlPkL`, and measuring the wrong one gives
500 × 500, which looks like a failure and is not one.

```js
// paste on the listing, with the browser signed in
(async (u) => { const r = await fetch(u); const b = await r.blob();
  const i = await createImageBitmap(b); return { bytes: b.size, w: i.width, h: i.height }; })
('https://m.media-amazon.com/images/I/81flPsAWG-L.jpg')
```

Against a captured product, `identify` the file or read `Photo.file_size`.

---

## E. Confirm the parse path is alive

The defect this feature fixes was invisible because a fallback answered silently. This is how you
tell, in ten seconds, that the fallback is *not* what answered:

1. Capture any listing with the console open.
2. `capture-agent` must **not** log that it fell back to a swept reading.

If it does, the listing's gallery markup has changed shape again and the counts in §B and §C will be
roughly double. That is the exact failure that ran undetected for a whole release. Treat one line in
the console as the check, not the count — the count looks plausible when it is wrong.

---

## F. Recognising the duplicates on products captured before this feature

Every product captured since feature 007 shipped carries roughly twice the gallery images it should,
half of them ~500-pixel copies. Nothing is lost or corrupt; the extras are just noise.

* They are the **same picture**, visibly smaller.
* They sit **next to** their original in the grid — the old reading emitted `hiRes`, `large`,
  `hiRes`, `large`, and the stored filename index follows that order, so `…-00` and `…-01` are one
  photograph, `…-02` and `…-03` the next.
* Remove them with bulk photo deletion (#96): **Select all**, untick the originals, **Delete
  Selected**. Nothing automated does this and nothing should — deciding from a stored row alone
  which copy is the twin needs a listing that may since have changed.

Re-capturing does not remove them: `merge_specifications` and the attachment dedupe are
already-present-wins, so the old rows stay. Delete, then re-capture if you want the gallery clean.

---

## G. What no suite can check

* **That the fixture still resembles Amazon.** The e2e suite drives the real agent against
  `tests/e2e/fixtures/amazon_listing.html`. Before this feature that fixture wrote the gallery block
  as a bare array literal, which no real listing does — so the suite exercised a parse path that had
  never once run in production, and passed throughout. It now carries the `A.$.parseJSON('…')` form.
  A fixture cannot fail when the vendor changes; only §B and §E can.
* **The variation family.** `B0CKXJLP4B` publishes eight sibling pack sizes. Nothing automated
  notices if a future reading starts collecting them.
* **Whether the stored image is the picture you wanted.** Only a person looking at it.
