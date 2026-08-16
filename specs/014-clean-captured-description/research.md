# Phase 0 Research: Clean Captured Description

Seven decisions. The spec left no `NEEDS CLARIFICATION` markers, so none of these resolve a question put to the owner — they resolve *how*, and each one records what was rejected so a reviewer can see the alternative was looked at rather than missed.

---

## 1. Read from a clone, not from the node

**Decision**: Before reading text from a region, `cloneNode(true)` it and remove the non-content elements from the clone. Never remove anything from a node that is part of a real document.

**Rationale**: `canonicalDocument()` returns one of two things — a detached document parsed by `DOMParser` (the normal path), or `{doc: document, url: location.href}`, the operator's live page (the fallback path, taken whenever the canonical fetch fails). Stripping in place would be harmless on the first and would silently edit the page the operator is looking at on the second. FR-003 exists for exactly that fallback. A clone makes the two paths behave identically, which is also what makes the fixture-driven test meaningful.

There is a second, less obvious reason. `descriptionImages(block)` reads `img.naturalWidth` as its last resort for establishing an image's dimensions. On a detached clone, images are never fetched and `naturalWidth` is 0, so a clone would quietly change which images pass the size filter. **`descriptionImages()` must go on receiving the original block.** Cloning only for text reading keeps that true without a special case.

**Alternatives considered**:
- *Strip in place and put it back.* Removing nodes and re-inserting them is more code, is not exception-safe (FR-015 — a throw mid-restore leaves the operator's page mangled), and buys nothing.
- *Filter during the walk instead of removing.* Workable, and slightly cheaper. Rejected because the same removal has to serve the detail-bullet path (decision 6), where a node is removed for a different reason; one clone-and-remove step that both use is simpler than two filters.
- *Cost.* A clone of an A+ block is a few hundred nodes, once per capture. Principle I forbids optimizing that without a measurement, and there is none.

---

## 2. An explicit recursive walk, not `innerText`

**Decision**: Build the text with a recursive walk over the clone's child nodes, appending text-node content and emitting separators at boundaries.

**Rationale**: This is not a preference. `innerText` is defined in terms of *rendered* text — it requires layout — and returns the same thing as `textContent` (or empty) for an element not being rendered. The document capture normally reads is produced by `DOMParser`: detached, never attached to a browsing context, never laid out. `innerText` would return `''` there and something else again on the live-page fallback, which is the worst of both worlds: the extraction would behave differently depending on whether the canonical fetch succeeded.

`textContent`, which the code uses today, has the opposite problem — it is defined without regard to rendering, which is precisely why it returns the stylesheet's text.

**Alternatives considered**:
- *`innerText`.* Rejected above. Worth recording because it is the obvious first idea and it looks right until you notice which document is being read.
- *Regex over `innerHTML`.* Turning `<br>` into `\n` with a pattern and then stripping tags. Rejected: comments, attribute values containing `<`, and CDATA-ish script bodies all break it, and "strip the tags with a regex" is the classic wrong answer.
- *`Range.toString()` / `TreeWalker`.* `TreeWalker` is a reasonable shape for this and was close. Rejected because the recursion has to know when it is *leaving* an element in order to emit the closing boundary, and a `TreeWalker` makes that the caller's bookkeeping. Plain recursion expresses "separator, children, separator" in one line each.

---

## 3. One walker, two wrappers

**Decision**:

```
proseOf(node)  -> stripped, line structure preserved, normalized
textOf(node)   -> proseOf(node) with all whitespace collapsed to single spaces
```

`textOf` keeps its current contract exactly: one line, runs collapsed, trimmed, `''` for a missing node, never null, never a throw. Callers move as follows:

| Caller | Helper | Why |
|---|---|---|
| `priceFrom` | `textOf` | A price is one token. A newline would break the digit extraction. |
| `brandFrom` | `textOf` | Matches `^Visit the (.+?) Store$` and `^Brand:\s*(.+)$`. JavaScript's `.` does not match `\n`, so a newline in the byline would silently stop both patterns matching and the brand would come through raw. |
| `titleFrom` | `textOf` | A product title is one line by definition. |
| `descriptionBlock` (the emptiness test) | `textOf` | Only its truthiness is used; collapsing is free and the stripping is what matters (decision 5). |
| specification **names** | `textOf` | FR-009. Names are folded case- and whitespace-insensitively by `specificationsFrom` and again by `CatalogService.merge_specifications`; a newline in a name would make two spellings of one name. |
| specification **values** | `proseOf` | FR-009. |
| the description | `proseOf` | FR-005 to FR-008. |

**Rationale**: FR-001 has to reach every caller and FR-005 to FR-008 must reach only two. Defining the narrow one in terms of the broad one gives that with a single walk implementation and no flag parameter. `textOf`'s signature and contract do not change, so nothing downstream of it has to be re-reasoned.

**Alternatives considered**:
- *One function with a `preserveLines` boolean.* A boolean parameter that changes the shape of a return value is the thing that makes call sites unreadable, and Principle I's "prefer boring, obvious code" points the other way. Two named functions, one implemented in terms of the other, say what they do at the call site.
- *Give everything line structure.* Rejected: it breaks `brandFrom` outright and makes specification names unmergeable. FR-009 exists because of this.

---

## 4. The boundary set and the normalization order

**Decision**: Two element sets, both module-level constants read once.

- **Line break** — `BR`. Emits exactly one `\n`.
- **Block boundary** — `P`, `DIV`, `LI`, `TR`, `H1`, `H2`, `H3`, `H4`, `H5`, `H6`. Emits `\n\n` *before* and *after* its children.
- **Non-content** — removed from the clone: `style`, `script`, `noscript`, `template`.

**A newline in a text node is not a line break.** This is the trap in the whole design and it has to be handled at collection, not in normalization. Markup is indented, so a paragraph's own text routinely contains source newlines that the reader never sees. If those survive, the very first fixture paragraph comes out broken across two lines for no reason the page shows. So **each text node's content is collapsed with `/\s+/g → ' '` as it is appended**, and every newline in the result is one this walk deliberately emitted.

Then normalize, in this order — the order is load-bearing and is part of the contract:

1. `replace(/[^\S\n]+/g, ' ')` — collapse the runs of spaces that form where two neighbours each contributed one, leaving newlines alone. (`\s` here would eat the newlines this feature exists to produce.)
2. `replace(/ *\n */g, '\n')` — drop the spaces that end up either side of a newline, so a "blank" line is genuinely empty.
3. `replace(/\n{3,}/g, '\n\n')` — fold any run of three or more newlines to exactly two, so nesting never produces more than one blank line (FR-007).
4. `trim()` — leading and trailing whitespace off the whole value (FR-008).

Step 2 must come before step 3, or a line holding only spaces defeats the fold — which is exactly the "whitespace-only block" edge case in the spec.

**Rationale on the sets**: the boundary list is the one the issue prescribes, and FR-006 names the same things. Emitting the separator on *both* sides of a block element is what makes `text<div>more</div>` come out as two paragraphs rather than `textmore`; the fold in step 3 cleans up the doubling, which is why the issue's "runs of 3+ newlines folded to 2" is in the prescription at all.

`template` is in the removal list for completeness rather than necessity: the HTML parser puts a template's children into its `content` fragment, so `textContent` on a `<template>` element is already `''`. It costs one word in a selector and removes the need for the next reader to work that out.

**Alternatives considered**:
- *`<li>` emits a single newline instead of a paragraph break.* This is the one place where the prescription produces output some readers will not like: a bullet list comes out with a blank line between every item. It was considered seriously. Rejected because the issue prescribes the paragraph break explicitly, FR-006 names list items among the block boundaries, and the result is loose but never *wrong*. If the owner dislikes it once they see a real captured list, it is a one-element move from the block set to the break set and one test-table row.
- *A wider block set* (`UL`, `OL`, `TABLE`, `SECTION`, `ARTICLE`, `BLOCKQUOTE`, `HR`). Rejected: `DIV` and `P` already dominate A+ markup, every one of these contains something already in the set, and the fold makes the extra separators invisible. Speculative generality (Principle I).
- *Treating any element with a block `display` as a boundary.* Requires computed style, which requires layout, which the detached document does not have. Same wall as `innerText`.

---

## 5. FR-004 falls out of decision 1 — but is not free

**Decision**: Leave `descriptionBlock()`'s `if (block && textOf(block))` test exactly as it is.

**Rationale**: Once `textOf` strips non-content nodes, a block whose only text was a stylesheet and a script evaluates to `''`, the test fails, and the loop moves on to the next container in `DESCRIPTION_CONTAINERS` — which is precisely FR-004, with no new code. `extract()`'s `if (description)` guard then covers "no block at all".

**But it must be tested, not assumed.** It is a behavior that emerges from a change somewhere else, which is exactly the kind of thing that quietly stops being true. `quickstart.md` and the test table in the contract both carry a case for it.

**Alternatives considered**: an explicit post-strip emptiness check inside `descriptionBlock`. Rejected as a second implementation of the same rule — `textOf` already answers "is there any prose here".

---

## 6. Remove the bold node instead of slicing by its length

**Decision**: In `rowsFrom`'s detail-bullet shape, extract the value by cloning the list item, removing the `.a-text-bold` element from the clone, and reading the remainder — rather than the current `whole.slice(textOf(bold).length)`.

**Rationale**: The existing arithmetic assumes the name's text is a *prefix* of the item's text, character for character. That holds today because both sides are single-line, whitespace-collapsed strings and the bold span comes first. It stops holding the moment either side can contain a newline, and FR-009 puts specification values on `proseOf`. The failure would not be an exception — it would be values silently sliced at the wrong offset, which is the worst kind.

Removing the node is also shorter, does not care whether the bold span is the first child, and reuses the clone-and-remove step decision 1 already introduces.

**Alternatives considered**:
- *Leave the detail-bullet path on single-line extraction.* Tempting — detail bullets genuinely are one line ("Date First Available : March 1, 2024") and the contaminated `Customer Reviews` row came from a table cell, not a bullet. Rejected because it would make FR-009 true for some specification values and not others, with the distinction invisible at the call site and undocumented anywhere a future reader would look.
- *Compute the offset from `proseOf(bold)` instead.* Keeps the arithmetic and adds a second way for it to be subtly wrong. Removing the node removes the class of bug.

---

## 7. No JavaScript unit-test seam; prove it through the payload

**Decision**: Test every extraction requirement by driving a capture against an enriched fixture and asserting on the `listing` JSON in the confirmation form's hidden field. Do not add a JavaScript test runner.

**Rationale**: `capture-agent.js` is a self-executing IIFE with no exports — by design, since it is appended into a vendor's page by a loader. Unit-testing `proseOf` in isolation means either exporting it (adding a module system to a file that is deliberately a plain script) or adding Node plus a test runner plus a DOM shim. The Technology Constraints section makes "introducing a frontend framework or build step" a constitutional amendment, and a test runner for one function is not a case for amending the constitution.

What makes the alternative acceptable is that the assertion is already precise: `test_the_rich_description_is_kept_and_its_furniture_is_not` reads `input[name='listing']`, parses the JSON, and asserts on `images` exactly. The same read gives `description_text` and `specifications` as exact strings. So one capture run can carry the entire test table — every boundary case in one fixture, one assertion per case against the parsed payload — for the cost of one browser round trip rather than one per case.

**What this costs, stated rather than hidden**: the walker is only ever exercised against markup someone wrote by hand. It cannot fail when Amazon changes theirs. That is the same limitation `specs/007-product-page-capture/research.md` records under "The risk that is not mitigated", and it is why decision 8 exists.

**Alternatives considered**:
- *Node plus jsdom plus a runner.* Rejected: build step, dependency, constitutional amendment, for one function.
- *`page.evaluate` against the fixture to call the helper directly.* Would need the helper exposed on `window`, i.e. a test-only export in production code. Rejected — the payload assertion is just as precise and leaves the file alone.
- *One e2e test per case.* Rejected on cost: each capture is a full browser flow. One fixture carrying every case, asserted case by case against one parsed payload, is the same coverage in a fraction of the wall clock. The suite's 8m 13s is a budget worth protecting.

---

## 8. The live-markup review is optional and does not block

**Decision**: Implement against the prescription in the issue. Treat driving the owner's Chrome against `B0DMNXC4CD`, `B09GM8FB3X` and `B0FX4PDW6M` as a **fixture-fidelity** step: worth doing, done *with* the owner present, and not a prerequisite for any code.

**Rationale**: The issue itself says the cause is established and the work is buildable now. What a live A+ block can tell us is whether the fixture is shaped like the real thing — how the stylesheets sit relative to the prose, whether the copy is in paragraphs or in table cells, how deep the nesting goes. That changes the *fixture*, and possibly one entry in the boundary set. It does not change the design.

Sequencing it as a prerequisite would block the whole feature on the owner being at their desk, for information that can be folded in afterwards at the cost of one fixture edit and one test-table row.

**How it would run, if run**: with the owner, in their browser, on those three listings. Anything learned goes back into `tests/e2e/fixtures/amazon_listing_aplus.html` as markup shaped like the real thing — the fixture's existing header comment is the model for recording *why* each piece is there.

**Alternatives considered**:
- *Block on it.* Rejected above.
- *Skip it entirely.* Rejected: the current fixture's A+ block contains no stylesheet, no script, no `<br>`, and no nesting deeper than two. Shipping a walker whose only evidence is markup written to make the walker pass is a weak position, and the owner has the real pages open anyway.
