# Contract: reading text off a listing page

The whole feature. Four functions in the "Reading the page" section of `app/static/js/capture-agent.js`, replacing one.

Nothing crosses a machine boundary here — the payload schema in `specs/007-product-page-capture/contracts/capture-payload.md` is **unchanged**. What changes is what `description_text` and each `specifications[].value` contain. This document is the contract between these helpers and the rest of the agent, and its test table is the test table.

---

## Today

```js
/** Trimmed, whitespace-collapsed text, or '' -- never null, never a throw. */
function textOf(node) {
    if (!node) {
        return '';
    }
    return (node.textContent || '').replace(/\s+/g, ' ').trim();
}
```

Two defects, both in that one expression: `textContent` includes stylesheet and script text, and `/\s+/g` erases every boundary the reader can see.

---

## The four functions

### `contentClone(node) -> Element`

A detached deep copy of `node` with every non-content element removed from it.

- Removes: `style`, `script`, `noscript`, `template`.
- **The original is never touched.** `canonicalDocument()` falls back to the operator's live `document` whenever the canonical fetch fails, so a removal in place would edit the page they are looking at (FR-003).
- Callers that need the *original* — `descriptionImages()` above all — must go on receiving it. `knownEdges()` reads `img.naturalWidth`, which is 0 on a detached clone, so passing it a clone would silently change which images survive the size filter.

### `proseFrom(clone) -> string`

The walk. Takes an already-cleaned clone, returns normalized text.

```
for each child node:
    text node      -> append its data with /\s+/g collapsed to ' '
    <br>           -> append '\n'
    block element  -> append '\n\n', recurse, append '\n\n'
    anything else  -> recurse
```

Block elements: **`P`, `DIV`, `LI`, `TR`, `H1`–`H6`.** One module-level list, matched on `nodeName` (which is upper-case for HTML elements). Not configurable — Principle I.

The separator is emitted on **both** sides of a block, which is what makes `Intro<div>Boxed</div>` two paragraphs rather than `IntroBoxed`. The doubling that produces is what step 3 below exists to fold.

**A newline inside a text node is not a line break.** Markup is indented; a paragraph's own text is full of source newlines the reader never sees. Collapsing each text node's whitespace *as it is appended* is what guarantees that every newline in the output is one this walk deliberately emitted.

Then normalize, in this exact order:

| # | Operation | Why |
|---|---|---|
| 1 | `replace(/[^\S\n]+/g, ' ')` | Collapse the double spaces that form where two neighbours each contributed one. `\s` would eat the newlines. |
| 2 | `replace(/ *\n */g, '\n')` | Strip spaces either side of a newline, so a "blank" line is genuinely empty. |
| 3 | `replace(/\n{3,}/g, '\n\n')` | Fold runs of newlines to at most one blank line (FR-007). |
| 4 | `trim()` | Leading and trailing whitespace off the whole value (FR-008). |

Step 2 **must** precede step 3, or a line holding only spaces survives the fold. That is the spec's "whitespace-only block" edge case.

### `proseOf(node) -> string`

`node ? proseFrom(contentClone(node)) : ''`. The public form for the description and for specification values.

### `textOf(node) -> string`

`proseOf(node).replace(/\s+/g, ' ').trim()`.

**Its contract is unchanged from today**: one line, runs collapsed, trimmed, `''` for a missing node, never `null`, never a throw. Only its *content* changes — non-content text is gone. Nothing downstream of it needs re-reasoning.

---

## Who calls which

| Call site | Helper | Why |
|---|---|---|
| `priceFrom` | `textOf` | One token; the digit extraction has no newline case. |
| `brandFrom` | `textOf` | Matches `^Visit the (.+?) Store$` and `^Brand:\s*(.+)$`. JavaScript's `.` does not match `\n`, so a newline would silently stop both matching. |
| `titleFrom` | `textOf` | One line by definition. |
| `descriptionBlock` — the emptiness test | `textOf` | Only truthiness is read. The stripping is what earns FR-004. |
| `rowsFrom` — specification **names** (both shapes) | `textOf` | FR-009. Names are folded case- and whitespace-insensitively twice over — by `specificationsFrom` and again by `CatalogService.merge_specifications`. A newline in a name makes two spellings of one name. |
| `rowsFrom` — table-cell **value** | `proseOf` | FR-009. |
| `rowsFrom` — detail-bullet **value** | see below | FR-009. |
| `extract` — `description_text` | `proseOf` | FR-005 to FR-008. |

### The detail-bullet value

Today the value is sliced out of the item's text by the name's character length:

```js
const whole = textOf(items[i]);
const name = tidyName(textOf(bold));
const value = whole.slice(textOf(bold).length).replace(/^[\s:]+/, '').trim();
```

That assumes the name's text is a character-for-character prefix of the item's text. It stops being true the moment either side can hold a newline, and the failure mode is not an exception — it is values silently sliced at the wrong offset.

Replace the arithmetic with a removal:

```js
const clone = contentClone(items[i]);
const boldInClone = clone.querySelector('.a-text-bold');
if (boldInClone) { boldInClone.remove(); }
const value = proseFrom(clone).replace(/^[\s:]+/, '');
```

Shorter, indifferent to whether the bold span is the first child, and it reuses the clone the stripping already needs.

---

## Guarantees

- **G1** — Neither helper throws for any input, including `null`, an empty element, or a subtree of nothing but scripts (FR-015).
- **G2** — Neither helper mutates any node reachable from the document passed in (FR-003).
- **G3** — `textOf` returns a string containing no `\n`, for every input.
- **G4** — `proseOf` returns a string with no leading or trailing whitespace, no line with leading or trailing spaces, and no run of more than two consecutive newlines.
- **G5** — Every `\n` in a `proseOf` result corresponds to a `<br>` or a block boundary in the source. None comes from source indentation.
- **G6** — For any node containing no `<br>` and no block element, `proseOf(node) === textOf(node)`. This is what makes SC-003 — the plain-description listings unchanged — a property rather than a hope.

---

## Test table

One enriched `amazon_listing_aplus.html` carries every case. One capture run, then one assertion per row against the parsed `listing` payload — `json.loads(landed.locator("input[name='listing']").input_value())`.

| # | Source, inside the captured region | Expected in the payload | Requirement |
|---|---|---|---|
| 1 | `<style>.aplus-module{margin:0;padding:0}</style>` before the prose | none of it present | FR-001 |
| 2 | `<script>var m=1;function go(){return m}</script>` between paragraphs | none of it present | FR-001 |
| 3 | `<noscript>Enable JavaScript</noscript>` | `Enable JavaScript` absent | FR-001 |
| 4 | `<p>Line one<br>Line two</p>` | `Line one\nLine two` | FR-005 |
| 5 | `<h4>Built for the workshop</h4><p>Extruded …</p>` | `Built for the workshop\n\nExtruded …` | FR-006 |
| 6 | `<ul><li>6mm slot</li><li>Clear anodised</li></ul>` | `6mm slot\n\nClear anodised` | FR-006 |
| 7 | `<div><div><div><p>A</p></div></div></div><p>B</p>` | `A\n\nB` — exactly one blank line | FR-007 |
| 8 | A paragraph whose source is indented across three lines | one line, single spaces | FR-008, G5 |
| 9 | `<div>   </div>` between two paragraphs | no extra blank line | FR-007 |
| 10 | `<li>Item<br>continued</li>` | `Item\ncontinued` | FR-005 |
| 11 | The whole `#aplus` block replaced by only a `<style>` and a `<script>` | capture reports no description; the *other* container is read if present | FR-004 |
| 12 | The plain `#productDescription` fixture, unchanged | `description_text` identical to today's, character for character | FR-010, SC-003, G6 |
| 13 | A `Customer Reviews` table cell holding a rating plus an inline `<style>` and `<script>` | value is the rating text only | US3, FR-002 |
| 14 | A table cell whose value spans two `<p>` elements | value contains the paragraph break | FR-009 |
| 15 | A `<th>` name cell containing a `<br>` | name is one line, and the row still merges as one name | FR-009 |
| 16 | Every other field on the same capture | title, brand, price, image list, and the set of specification names identical to today's | FR-014, SC-006 |

Cases 11 and 12 want their own fixtures or their own capture, since 11 removes the block the other cases live in.
