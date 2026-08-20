# Contract: The Gallery Reading

**Feature**: [spec.md](spec.md) | **Date**: 2026-08-20

What a capture must produce for the gallery half of a listing, stated so it can be checked against a
**listing** rather than against the code that produced it. Every clause below is checkable in a
browser console on any Amazon product page in a couple of minutes; [quickstart.md](quickstart.md)
gives the commands.

This is not a wire format. The payload's `images` key is unchanged — a flat list of strings, gallery
and description images together, in that order ([data-model.md](data-model.md)). What is contracted
is *membership*: which addresses belong in that list.

## The reading

> The gallery reading is **one address per gallery entry the listing publishes for the item being
> captured — no more, no fewer** — each naming the largest rendition that entry offers, with its
> transform token stripped.

### 1. One entry, one address

For each entry in the listing's gallery array, exactly one address is emitted.

* `hiRes` when it is a usable address.
* `large` when `hiRes` is `null`. The entry is **not** skipped: 4 of the 39 entries across the six
  probed listings are in this state and each is a photograph the operator would otherwise lose.
* `thumb` never.
* Never two addresses for one entry. Two addresses on one entry are two sizes of one photograph, not
  two photographs, and storing both stores the same picture twice under different filenames.

### 2. No more than the item's own gallery

The reading covers the gallery of the item being captured. It does **not** extend to:

* Other members of the variation family. `B0CKXJLP4B` publishes eight sibling pack sizes with a lead
  image each; those are pictures of a different purchase.
* Any `hiRes` address found elsewhere in the document. Sweeping the document is how #80 §1b's
  expected counts came to be wrong (research §3) and it must not become how the capture works.

### 3. Original resolution, no silent substitute

Each emitted address has its transform token stripped, so it names the source file (007 FR-004).
There is no fallback to the tokened address: an address that fails after stripping is reported as a
failed image. Unchanged by this feature and restated here because clause 1's "largest rendition"
must not be read as licensing a smaller one.

### 4. Structure is found, not assumed

The gallery array is located wherever the listing puts it. As served on all six probed listings on
2026-08-20, that is as the argument of a function call inside a quoted string:

```js
'colorImages': { 'initial': A.$.parseJSON('[{"hiRes":"…","thumb":"…","large":"…","variant":"MAIN"}, …]')
```

A reading that requires the array to be a bare literal finds nothing here. Both forms must be
handled; neither may be assumed.

### 5. Failure is loud, degradation is not silent

If the gallery array cannot be located or cannot be parsed, the capture still completes and still
carries whatever else it read — a structural surprise costs images, never the capture (spec FR-009,
mirroring 007's rule for descriptions). But it must be **visible** that a lesser reading answered.
The whole of issue #95 exists because a silent fallback produced a plausible number for an entire
release.

## Checkable consequences

Read from the fetched `/dp/<ASIN>` document on 2026-08-20. The middle column is the contract; the
right column is what the reading produces today and is what changes.

| ASIN | Contract: gallery entries | Today | Thumbnails | Whole-document `hiRes` (**not** the contract) |
|---|---|---|---|---|
| `B0CKXJLP4B` | 7 | 14 | 7 | 14 |
| `B099F4X4Q9` | 7 | 12 | 7 | 16 |
| `B01N4OSKWE` | 3 | 6 | 3 | 3 |
| `B0DMNXC4CD` | 7 | 14 | 7 | 7 |
| `B09GM8FB3X` | 8 | 14 | 7 | 11 |
| `B0FX4PDW6M` | 7 | 14 | 6 | 9 |

**On the coincidences in this table, which are what made issue #95 hard:**

* **Gallery equals thumbnails on five of six.** A reading that returned the thumbnail strip would be
  indistinguishable from a correct one by count alone on those five. #80 §1b's B1 tells a verifier
  the opposite — that matching the thumbnail count proves a DOM read — and that inference is wrong
  (spec FR-023). Count is not sufficient evidence; the addresses are.
* **`B0CKXJLP4B`'s whole-document count (14) equals what the broken reading emits (14)**, from two
  entirely unrelated causes. B1 as written passes today for the wrong reason.
* **`B01N4OSKWE` and `B0DMNXC4CD` have no variants**, so whole-document and gallery agree and #57's
  figures for them were accidentally right.

A check that discriminates has to compare the reading against the entries, not a total against a
total. That is what [quickstart.md](quickstart.md) is for.
