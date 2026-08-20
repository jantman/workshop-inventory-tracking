# Contract: the description reader

**Feature**: [spec.md](spec.md) | **Phase**: 1 | **File**: `app/static/js/capture-agent.js`

The obligations the reader must meet after this change. Each is stated so it can be failed by a
test rather than inspected by eye.

## `isCrossSell(node)` → boolean

- **C-1**: Returns true for any node inside `#aplusBrandStory_feature_div`, at any depth, including
  the container itself.
- **C-2**: Returns false when no such container exists on the page. It must not throw, and must not
  treat "container absent" as "everything is cross-sell". Two of the three probed listings carry the
  container present-but-empty; a listing without one at all must behave identically to one with an
  empty one.

## `addressOf(img)` → string

- **C-3**: Returns the `data-src` value when the element has one, else the `src` value, else `''`.
- **C-4**: Returns `''` for a known deferred-loading placeholder address, whichever attribute it
  came from. A placeholder must never be stored in place of the image it stands for.
- **C-5**: Performs no resolution, fetching or measurement. It reads attributes and returns a
  string; it must be safe against a detached document with no layout.

## `descriptionBlocks(doc)` → array of elements

- **C-6**: Returns every element matching `DESCRIPTION_CONTAINERS` that has text. **Every** match,
  not the first — `querySelectorAll`, because a page may carry two elements with `id="aplus"` and
  `querySelector` cannot see the second.
  *(Corrected during implementation: this originally said "in document order", which is wrong.
  Ordering is by `DESCRIPTION_CONTAINERS`, then document order within each selector. The list's
  order is a **precedence** — 007 put `#productDescription` first so the plain form wins if a page
  ever carries both — and whole-document order would silently hand that precedence to whichever
  block the page laid out first. The distinction is load-bearing because C-15 takes the text from
  `blocks[0]`.)*
- **C-7**: Excludes any block for which `isCrossSell` is true.
- **C-8**: Returns `[]` rather than null when nothing qualifies. The caller must be able to iterate
  unconditionally.
- **C-9**: May return blocks that contain one another. Deduplication is the caller's job, not
  this function's, and the caller already has a `seen` map.

## `descriptionImages(blocks)` → array of addresses

- **C-10**: Skips an image for which `isCrossSell` is true, **before** any size test. A cross-sell
  image that clears 300 px on both edges must still be skipped — this is the over-capture half of
  the defect and the assertion that catches its return.
- **C-11**: Skips an image whose `addressOf` is empty or does not match `/^https?:/`.
- **C-12**: Applies `knownEdges()` and `MIN_DESCRIPTION_EDGE` exactly as today, to the address
  `addressOf` returned. An image with no establishable dimensions is **kept** (007 FR-019).
  *(Implementation note: honoring "to the address `addressOf` returned" required `knownEdges()` to
  take that address as a parameter instead of reading `src` itself — for a deferred-loading image
  `src` names the grey placeholder, so the rule would have been measuring the wrong picture. The
  rule is unchanged: same two patterns, same threshold, same keep-on-unknown clause. It has one
  call site.)*
- **C-13**: Returns addresses with the resolution token stripped by `withoutTransform()`, unchanged.
- **C-14**: Returns each address at most once even when the same image is reachable from two
  overlapping blocks.

## The call site

- **C-15**: `description_text` is taken from the **first** block `descriptionBlocks` returns, not
  from all of them concatenated. 007 FR-005 stands: whichever form the description takes, and never
  a requirement that both be present.
- **C-16**: A cross-sell region's prose is never `description_text`. This is C-7 seen from the
  payload side, and it is what changes `B0FX4PDW6M` from the vendor's company bio to the product's
  own description.
- **C-17**: Images are gathered from **all** returned blocks.
- **C-18**: When `descriptionBlocks` returns `[]`, the payload carries no `description_text` and no
  description images, and the capture still succeeds with its gallery and specifications intact
  (007 FR-007).

## Failure behavior

- **C-19**: No function above may throw for any document. A selector that stops matching costs
  images or the description; it must never cost the capture. This is the same obligation 007 and
  020 placed on every reader in this file, and it is why none of them uses an optional-chaining or
  regex construct that can fault on unexpected markup.
